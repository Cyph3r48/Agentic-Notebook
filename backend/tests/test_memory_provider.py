from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from loguru import logger
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qdrant
from qdrant_client.http.exceptions import ResponseHandlingException

from app.core.config import settings
from app.services.memory import MemoryBackendUnavailable, get_memory_provider, validate_memory_backend
from app.services.memory import builtin
from app.services.memory.builtin import BuiltinMemoryProvider

DIM = 3
SECRET_URL = "http://user:hunter2@qdrant.internal:6333"


class _SharedClient:
    """One in-memory Qdrant for a whole test; close() is counted instead of destroying the data."""

    def __init__(self):
        self.client = AsyncQdrantClient(":memory:")
        self.closed = 0

    def __getattr__(self, name):
        return getattr(self.client, name)

    async def close(self):
        self.closed += 1


class _Embedder:
    """Stands in for TEI: 'alpha' -> x axis, 'beta' -> y axis, anything else -> z axis."""

    def __init__(self):
        self.mode = "ok"  # ok | down | http500 | badshape | badsize
        self.embed_calls: list[int] = []

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            if self.mode == "down":
                raise httpx.ConnectError("connection refused", request=request)
            if self.mode == "http500":
                return httpx.Response(500, json={"error": "boom"})
            if request.url.path == "/health":
                return httpx.Response(200)
            inputs = json.loads(request.content)["inputs"]
            self.embed_calls.append(len(inputs))
            if self.mode == "badshape":
                return httpx.Response(200, json={"vectors": []})
            if self.mode == "badsize":
                return httpx.Response(200, json=[[1.0, 0.0] for _ in inputs])
            return httpx.Response(200, json=[self._vector(text) for text in inputs])

        return httpx.MockTransport(handler)

    @staticmethod
    def _vector(text: str) -> list[float]:
        if "alpha" in text:
            return [1.0, 0.0, 0.0]
        if "beta" in text:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]


class _Session:
    """Only here so SearchRepository can be built; keyword search is replaced in the tests."""


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setattr(settings, "VECTOR_INDEXING_ENABLED", True)
    monkeypatch.setattr(settings, "EMBEDDING_DIM", DIM)
    monkeypatch.setattr(settings, "QDRANT_COLLECTION", "test_docs")
    monkeypatch.setattr(settings, "QDRANT_URL", SECRET_URL)
    monkeypatch.setattr(settings, "EMBEDDING_URL", "http://tei.internal:80")
    builtin.reset_status()
    yield
    builtin.reset_status()


@pytest.fixture
def warnings_log():
    messages: list[str] = []
    sink_id = logger.add(lambda message: messages.append(str(message)), level="WARNING")
    yield messages
    logger.remove(sink_id)


@pytest.fixture
def world():
    return SimpleNamespace(qdrant=_SharedClient(), embedder=_Embedder(), keyword_rows=[], keyword_calls=0)


def _provider(world, *, qdrant_factory=None) -> BuiltinMemoryProvider:
    provider = BuiltinMemoryProvider(
        _Session(),
        qdrant_factory=qdrant_factory or (lambda: world.qdrant),
        embed_transport=world.embedder.transport(),
    )

    async def fake_keyword(**kwargs):
        world.keyword_calls += 1
        return list(world.keyword_rows)

    provider.keyword_repo.search_chunks = fake_keyword
    return provider


def _chunks(*texts: str) -> list[dict]:
    return [
        {"chunk_index": i, "content": text, "content_hash": f"h{i}", "metadata_json": {"start": i * 10, "end": i * 10 + 9}}
        for i, text in enumerate(texts)
    ]


def _failing_factory(exc: BaseException, counter: dict | None = None):
    def factory():
        if counter is not None:
            counter["built"] = counter.get("built", 0) + 1
        raise exc

    return factory


CONNECT_ERROR = ResponseHandlingException(httpx.ConnectError(f"cannot reach {SECRET_URL}"))


# ---- vectors disabled -------------------------------------------------------


@pytest.mark.asyncio
async def test_disabled_vectors_touch_nothing_and_search_uses_keywords(monkeypatch, world):
    monkeypatch.setattr(settings, "VECTOR_INDEXING_ENABLED", False)
    counter: dict = {}
    provider = _provider(world, qdrant_factory=_failing_factory(AssertionError("no client expected"), counter))
    world.keyword_rows = [
        {"document_id": str(uuid4()), "original_filename": "a.txt", "chunk_index": 0, "content": "kw", "score": 0.4}
    ]

    ingest = await provider.ingest(user_id=uuid4(), document_id=uuid4(), original_filename="a.txt", chunks=_chunks("alpha"))
    outcome = await provider.search(user_id=uuid4(), query="alpha", limit=3)
    await provider.delete(user_id=uuid4(), document_id=uuid4())
    health = await provider.health()

    assert ingest.vector_indexed == "disabled" and ingest.id_map == {}
    assert outcome.mode == "keyword" and [r.content for r in outcome.results] == ["kw"]
    assert health.status == "disabled" and health.vector_enabled is False
    assert counter == {} and world.embedder.embed_calls == []


# ---- ingest -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_indexes_chunks_with_valid_point_ids_and_stable_payload(world):
    provider = _provider(world)
    user_id, document_id = uuid4(), uuid4()

    outcome = await provider.ingest(
        user_id=user_id, document_id=document_id, original_filename="notes.txt", chunks=_chunks("alpha one", "beta two")
    )

    assert outcome.vector_indexed is True and outcome.error is None
    assert set(outcome.id_map) == {0, 1}
    for point_id in outcome.id_map.values():
        UUID(point_id)  # Qdrant accepts only UUIDs or integers as point ids
    points, _ = await world.qdrant.client.scroll("test_docs", limit=10, with_payload=True)
    payload = next(p.payload for p in points if p.payload["chunk_index"] == 1)
    assert payload == {
        "user_id": str(user_id),
        "document_id": str(document_id),
        "original_filename": "notes.txt",
        "chunk_index": 1,
        "content": "beta two",
        "content_hash": "h1",
        "span_start": 10,
        "span_end": 19,
    }
    assert world.qdrant.closed >= 1


@pytest.mark.asyncio
async def test_point_ids_are_stable_so_reingest_replaces_rather_than_duplicates(world):
    provider = _provider(world)
    user_id, document_id = uuid4(), uuid4()
    for _ in range(2):
        await provider.ingest(user_id=user_id, document_id=document_id, original_filename="a.txt", chunks=_chunks("alpha"))

    assert (await world.qdrant.client.count("test_docs")).count == 1


@pytest.mark.asyncio
async def test_ingest_embeds_in_batches_of_32(world):
    provider = _provider(world)

    outcome = await provider.ingest(
        user_id=uuid4(), document_id=uuid4(), original_filename="big.txt", chunks=_chunks(*[f"alpha {i}" for i in range(70)])
    )

    assert outcome.vector_indexed is True
    assert world.embedder.embed_calls == [32, 32, 6]


@pytest.mark.asyncio
async def test_ingest_failure_is_reported_not_raised_and_never_leaks_the_url(world, warnings_log):
    provider = _provider(world, qdrant_factory=_failing_factory(CONNECT_ERROR))

    outcome = await provider.ingest(user_id=uuid4(), document_id=uuid4(), original_filename="a.txt", chunks=_chunks("alpha"))

    assert outcome.vector_indexed is False
    assert outcome.error == "Qdrant: could not connect"
    assert any("Qdrant: could not connect" in line for line in warnings_log)
    everything = " ".join(warnings_log) + str(outcome.error)
    assert "hunter2" not in everything and "qdrant.internal" not in everything
    health = await _provider(world).health()
    assert health.last_error == "Qdrant: could not connect" and health.last_error_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("down", "Embeddings: could not connect"),
        ("http500", "Embeddings: returned HTTP 500"),
        ("badshape", "Embeddings: unexpected response format"),
        ("badsize", f"Embeddings: model returns size 2 but EMBEDDING_DIM is {DIM}"),
    ],
)
async def test_embedding_failures_have_specific_safe_messages(world, warnings_log, mode, expected):
    world.embedder.mode = mode
    provider = _provider(world)

    outcome = await provider.ingest(user_id=uuid4(), document_id=uuid4(), original_filename="a.txt", chunks=_chunks("alpha"))

    assert outcome.vector_indexed is False and outcome.error == expected
    assert any(expected in line for line in warnings_log)


@pytest.mark.asyncio
async def test_ingest_refuses_a_collection_with_the_wrong_vector_size(world):
    await world.qdrant.client.create_collection(
        "test_docs", vectors_config=qdrant.VectorParams(size=7, distance=qdrant.Distance.COSINE)
    )
    provider = _provider(world)

    outcome = await provider.ingest(user_id=uuid4(), document_id=uuid4(), original_filename="a.txt", chunks=_chunks("alpha"))

    assert outcome.vector_indexed is False
    assert outcome.error == f"Qdrant: collection vectors have size 7 but EMBEDDING_DIM is {DIM}"


@pytest.mark.asyncio
async def test_client_is_closed_even_when_a_call_raises(world):
    class _Exploding(_SharedClient):
        async def upsert(self, **kwargs):
            raise RuntimeError("boom")

    exploding = _Exploding()
    provider = _provider(world, qdrant_factory=lambda: exploding)

    outcome = await provider.ingest(user_id=uuid4(), document_id=uuid4(), original_filename="a.txt", chunks=_chunks("alpha"))

    assert outcome.vector_indexed is False
    assert exploding.closed == 1


# ---- search -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_returns_vector_hits_with_spans(world):
    provider = _provider(world)
    user_id, document_id = uuid4(), uuid4()
    await provider.ingest(
        user_id=user_id, document_id=document_id, original_filename="notes.txt", chunks=_chunks("alpha one", "beta two")
    )

    outcome = await provider.search(user_id=user_id, query="alpha question", limit=3)

    assert outcome.mode == "vector" and outcome.degraded_reason is None
    assert [r.chunk_index for r in outcome.results][0] == 0
    top = outcome.results[0]
    assert (top.document_id, top.original_filename, top.content_hash) == (str(document_id), "notes.txt", "h0")
    assert (top.span_start, top.span_end) == (0, 9)
    assert world.keyword_calls == 0


@pytest.mark.asyncio
async def test_search_only_returns_the_callers_documents(world):
    provider = _provider(world)
    owner, stranger = uuid4(), uuid4()
    await provider.ingest(user_id=owner, document_id=uuid4(), original_filename="mine.txt", chunks=_chunks("alpha secret"))

    outcome = await provider.search(user_id=stranger, query="alpha", limit=5)

    assert outcome.results == []  # nothing from the owner; empty vector result falls through to keywords
    assert outcome.mode == "keyword"


@pytest.mark.asyncio
async def test_min_score_filters_vector_hits_and_empty_result_falls_back_to_keywords(world):
    provider = _provider(world)
    user_id = uuid4()
    await provider.ingest(user_id=user_id, document_id=uuid4(), original_filename="a.txt", chunks=_chunks("alpha one"))
    world.keyword_rows = [
        {"document_id": str(uuid4()), "original_filename": "k.txt", "chunk_index": 0, "content": "kw", "score": 0.3}
    ]

    # 'beta' is orthogonal to 'alpha' (score 0), so a threshold above 0 removes it.
    outcome = await provider.search(user_id=user_id, query="beta", limit=3, min_score=0.5)

    assert outcome.mode == "keyword"
    assert [r.original_filename for r in outcome.results] == ["k.txt"]


@pytest.mark.asyncio
async def test_search_before_any_upload_uses_keywords_without_error(world):
    provider = _provider(world)

    outcome = await provider.search(user_id=uuid4(), query="alpha", limit=3)

    assert outcome.mode == "keyword" and outcome.degraded_reason is None


@pytest.mark.asyncio
async def test_vector_failure_falls_back_to_keywords_and_says_so(world, warnings_log):
    provider = _provider(world, qdrant_factory=_failing_factory(CONNECT_ERROR))
    world.keyword_rows = [
        {"document_id": str(uuid4()), "original_filename": "k.txt", "chunk_index": 2, "content": "kw", "score": 0.3,
         "content_hash": "x", "span_start": 1, "span_end": 5}
    ]

    outcome = await provider.search(user_id=uuid4(), query="super private question", limit=3)

    assert outcome.mode == "keyword_fallback"
    assert outcome.degraded_reason == "Qdrant: could not connect"
    assert outcome.results[0].chunk_index == 2 and outcome.results[0].span_end == 5
    assert any("Qdrant: could not connect" in line for line in warnings_log)
    assert not any("super private question" in line or "hunter2" in line for line in warnings_log)


@pytest.mark.asyncio
async def test_timeout_is_reported_as_a_timeout_not_a_connection_error(world):
    provider = _provider(world, qdrant_factory=_failing_factory(ResponseHandlingException(httpx.ReadTimeout("slow"))))

    outcome = await provider.search(user_id=uuid4(), query="alpha", limit=3)

    assert outcome.degraded_reason == "Qdrant: timed out"


@pytest.mark.asyncio
async def test_a_working_vector_call_clears_the_recorded_error(world):
    broken = _provider(world, qdrant_factory=_failing_factory(CONNECT_ERROR))
    await broken.search(user_id=uuid4(), query="alpha", limit=3)
    assert (await _provider(world).health()).last_error == "Qdrant: could not connect"

    await _provider(world).search(user_id=uuid4(), query="alpha", limit=3)

    assert (await _provider(world).health()).last_error is None


# ---- delete -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_removes_only_that_document(world):
    provider = _provider(world)
    user_id, keep, drop = uuid4(), uuid4(), uuid4()
    await provider.ingest(user_id=user_id, document_id=keep, original_filename="keep.txt", chunks=_chunks("alpha"))
    await provider.ingest(user_id=user_id, document_id=drop, original_filename="drop.txt", chunks=_chunks("alpha"))

    await provider.delete(user_id=user_id, document_id=drop)

    points, _ = await world.qdrant.client.scroll("test_docs", limit=10, with_payload=True)
    assert [p.payload["document_id"] for p in points] == [str(keep)]


@pytest.mark.asyncio
async def test_delete_does_not_let_another_user_remove_a_document(world):
    provider = _provider(world)
    owner, document_id = uuid4(), uuid4()
    await provider.ingest(user_id=owner, document_id=document_id, original_filename="a.txt", chunks=_chunks("alpha"))

    await provider.delete(user_id=uuid4(), document_id=document_id)

    assert (await world.qdrant.client.count("test_docs")).count == 1


@pytest.mark.asyncio
async def test_delete_with_vector_store_down_logs_a_warning_and_does_not_raise(world, warnings_log):
    provider = _provider(world, qdrant_factory=_failing_factory(CONNECT_ERROR))

    await provider.delete(user_id=uuid4(), document_id=uuid4())

    assert any("Qdrant: could not connect" in line for line in warnings_log)


@pytest.mark.asyncio
async def test_delete_before_any_collection_exists_is_a_quiet_no_op(world, warnings_log):
    await _provider(world).delete(user_id=uuid4(), document_id=uuid4())

    assert warnings_log == []


# ---- health -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_ok_when_both_parts_work_and_collection_is_missing_yet(world):
    health = await _provider(world).health()

    assert health.status == "ok" and health.backend == "builtin" and health.vector_enabled is True
    assert health.components["qdrant"].ok and "created on the first upload" in health.components["qdrant"].detail
    assert health.components["embeddings"].ok


@pytest.mark.asyncio
async def test_health_degraded_when_only_qdrant_is_down(world):
    health = await _provider(world, qdrant_factory=_failing_factory(CONNECT_ERROR)).health()

    assert health.status == "degraded"
    assert health.components["qdrant"].detail == "Qdrant: could not connect"
    assert health.components["embeddings"].ok


@pytest.mark.asyncio
async def test_health_degraded_when_only_embeddings_are_down(world):
    world.embedder.mode = "down"

    health = await _provider(world).health()

    assert health.status == "degraded"
    assert health.components["embeddings"].detail == "Embeddings: could not connect"
    assert health.components["qdrant"].ok


@pytest.mark.asyncio
async def test_health_down_when_both_are_down(world):
    world.embedder.mode = "down"

    health = await _provider(world, qdrant_factory=_failing_factory(CONNECT_ERROR)).health()

    assert health.status == "down"


@pytest.mark.asyncio
async def test_health_flags_a_collection_that_does_not_match_embedding_dim(world):
    await world.qdrant.client.create_collection(
        "test_docs", vectors_config=qdrant.VectorParams(size=9, distance=qdrant.Distance.COSINE)
    )

    health = await _provider(world).health()

    assert health.status == "degraded"
    assert "size 9" in health.components["qdrant"].detail


@pytest.mark.asyncio
async def test_health_flags_an_embedding_model_with_the_wrong_size(world):
    world.embedder.mode = "badsize"

    health = await _provider(world).health()

    assert health.status == "degraded"
    assert "EMBEDDING_DIM" in health.components["embeddings"].detail


@pytest.mark.asyncio
async def test_health_never_contains_the_configured_urls(world):
    world.embedder.mode = "down"

    health = await _provider(world, qdrant_factory=_failing_factory(CONNECT_ERROR)).health()

    text = repr(health)
    assert "hunter2" not in text and "qdrant.internal" not in text and "tei.internal" not in text


# ---- registry ---------------------------------------------------------------


def test_builtin_is_the_default_backend():
    assert settings.MEMORY_BACKEND == "builtin"
    assert isinstance(get_memory_provider(_Session()), BuiltinMemoryProvider)


@pytest.mark.parametrize("name", ["smc", "http"])
def test_backends_without_an_adapter_fail_with_a_clear_message(monkeypatch, name):
    monkeypatch.setattr(settings, "MEMORY_BACKEND", name)

    with pytest.raises(MemoryBackendUnavailable, match=f"MEMORY_BACKEND={name} is not implemented"):
        validate_memory_backend()
    with pytest.raises(MemoryBackendUnavailable):
        get_memory_provider(_Session())
