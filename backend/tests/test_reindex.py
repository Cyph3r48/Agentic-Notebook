from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_reindex_service
from app.api.v1.endpoints import memory as memory_endpoints
from app.core.config import settings
from app.services.memory import IngestOutcome
from app.services.memory import reindex as reindex_module
from app.services.memory.reindex import ReindexAlreadyRunning, ReindexNotPossible, ReindexService

IDENTITY = "ollama__embeddinggemma-abc123__768"


class _Settings:
    """In-memory SystemSettingsRepository (only what ReindexService uses)."""

    def __init__(self):
        self.rows: dict = {}
        self.writes = 0

    async def get(self, key):
        return self.rows.get(key)

    async def put_value(self, key, value):
        self.writes += 1
        self.rows[key] = SimpleNamespace(key=key, value=dict(value))
        return self.rows[key]


class _Docs:
    """In-memory DocumentRepository (only what ReindexService uses)."""

    def __init__(self):
        self.docs: dict[UUID, SimpleNamespace] = {}
        self.chunks: dict[UUID, list] = {}

    def add(self, *, user_id=None, status="completed", n_chunks=2, metadata=None, name="doc.txt"):
        doc = SimpleNamespace(
            id=uuid4(), user_id=user_id or uuid4(), original_filename=name, status=status, metadata_json=metadata or {}
        )
        self.docs[doc.id] = doc
        self.chunks[doc.id] = [
            SimpleNamespace(chunk_index=i, content=f"{name} chunk {i}", content_hash=f"h{i}", metadata_json={"start": i})
            for i in range(n_chunks)
        ]
        return doc

    async def count_completed(self):
        return sum(1 for d in self.docs.values() if d.status == "completed")

    async def completed_ids_after(self, after, limit):
        ids = sorted(d.id for d in self.docs.values() if d.status == "completed")
        return [i for i in ids if after is None or i > after][:limit]

    async def get_by_id(self, document_id):
        return self.docs.get(document_id)

    async def chunks_for_document(self, document_id):
        return self.chunks.get(document_id, [])

    async def update_document(self, row, *, metadata_json=None, **kwargs):
        if metadata_json is not None:
            row.metadata_json = metadata_json


class _Memory:
    def __init__(self):
        self.calls: list[dict] = []
        self.fail_for: dict[UUID, str] = {}
        self.disabled = False
        self.crash_for: set[UUID] = set()

    async def ingest(self, *, user_id, document_id, original_filename, chunks):
        self.calls.append({"user_id": user_id, "document_id": document_id, "name": original_filename, "chunks": chunks})
        if document_id in self.crash_for:
            raise RuntimeError("boom")
        if self.disabled:
            return IngestOutcome(vector_indexed="disabled")
        if document_id in self.fail_for:
            return IngestOutcome(vector_indexed=False, error=self.fail_for[document_id])
        return IngestOutcome(id_map={}, vector_indexed=True, index=IDENTITY)


class _Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def _vectors_on(monkeypatch):
    monkeypatch.setattr(settings, "VECTOR_INDEXING_ENABLED", True)


@pytest.fixture
def world():
    return SimpleNamespace(settings=_Settings(), docs=_Docs(), memory=_Memory(), clock=_Clock())


def _service(world):
    return ReindexService(world.settings, world.docs, world.memory, now=world.clock)


# ---------------------------------------------------------------- the job


@pytest.mark.asyncio
async def test_every_completed_document_is_indexed_and_marked_with_the_index_it_is_in(world):
    a = world.docs.add(name="a.txt", metadata={"vector_indexed": False, "vector_index_error": "Qdrant: could not connect", "keep": 1})
    b = world.docs.add(name="b.txt")
    service = _service(world)

    started = await service.start()
    final = await service.run()

    assert started["state"] == "running" and started["total"] == 2
    assert (final["state"], final["done"], final["failed"]) == ("done", 2, 0)
    assert a.metadata_json == {"vector_indexed": True, "vector_index": IDENTITY, "keep": 1}  # the old error is cleared
    assert b.metadata_json["vector_index"] == IDENTITY


@pytest.mark.asyncio
async def test_each_document_is_indexed_for_its_own_owner_with_its_own_chunks(world):
    alice, bob = uuid4(), uuid4()
    da = world.docs.add(user_id=alice, name="alice.txt", n_chunks=3)
    db = world.docs.add(user_id=bob, name="bob.txt", n_chunks=1)
    service = _service(world)
    await service.start()

    await service.run()

    by_doc = {c["document_id"]: c for c in world.memory.calls}
    assert by_doc[da.id]["user_id"] == alice and by_doc[db.id]["user_id"] == bob
    assert [c["content"] for c in by_doc[da.id]["chunks"]] == ["alice.txt chunk 0", "alice.txt chunk 1", "alice.txt chunk 2"]
    assert by_doc[da.id]["chunks"][1] == {
        "chunk_index": 1, "content": "alice.txt chunk 1", "content_hash": "h1", "metadata_json": {"start": 1},
    }


@pytest.mark.asyncio
async def test_running_it_again_is_safe_and_repeats_the_work_idempotently(world):
    world.docs.add()
    service = _service(world)
    await service.start()
    await service.run()
    await service.start()

    final = await service.run()

    assert final["state"] == "done" and final["done"] == 1 and len(world.memory.calls) == 2


@pytest.mark.asyncio
async def test_documents_that_are_not_completed_and_documents_without_chunks_are_skipped_cleanly(world):
    world.docs.add(status="failed")
    world.docs.add(status="processing")
    world.docs.add(n_chunks=0)
    done = world.docs.add()
    service = _service(world)

    started = await service.start()
    final = await service.run()

    assert started["total"] == 2  # only completed documents count
    assert final["state"] == "done" and final["failed"] == 0
    assert [c["document_id"] for c in world.memory.calls] == [done.id]


@pytest.mark.asyncio
async def test_a_document_that_fails_is_counted_and_skipped_and_the_others_still_finish(world):
    docs = [world.docs.add(name=f"{i}.txt") for i in range(4)]
    bad = sorted(docs, key=lambda d: d.id)[1]
    world.memory.fail_for[bad.id] = "Embeddings: returned HTTP 500"
    service = _service(world)
    await service.start()

    final = await service.run()

    assert (final["state"], final["done"], final["failed"]) == ("done", 3, 1)
    assert final["error"] == "Embeddings: returned HTTP 500"
    assert "vector_index" not in bad.metadata_json


@pytest.mark.asyncio
async def test_repeated_failures_stop_the_job_early_instead_of_grinding_through_everything(world):
    for i in range(8):
        d = world.docs.add(name=f"{i}.txt")
        world.memory.fail_for[d.id] = "Embeddings: could not connect"
    service = _service(world)
    await service.start()

    final = await service.run()

    assert final["state"] == "failed" and final["failed"] == reindex_module.MAX_CONSECUTIVE_FAILURES
    assert final["error"] == "Embeddings: could not connect"
    assert len(world.memory.calls) == reindex_module.MAX_CONSECUTIVE_FAILURES  # the rest were not even tried


@pytest.mark.asyncio
async def test_a_success_in_between_resets_the_failure_streak(world):
    docs = sorted((world.docs.add(name=f"{i}.txt") for i in range(5)), key=lambda d: d.id)
    for d in (docs[0], docs[1], docs[3], docs[4]):
        world.memory.fail_for[d.id] = "Embeddings: timed out"
    service = _service(world)
    await service.start()

    final = await service.run()

    assert final["state"] == "done" and (final["done"], final["failed"]) == (1, 4)


@pytest.mark.asyncio
async def test_an_unexpected_crash_marks_the_job_failed_rather_than_leaving_it_running(world):
    d = world.docs.add()
    world.memory.crash_for.add(d.id)
    service = _service(world)
    await service.start()

    final = await service.run()

    assert final["state"] == "failed" and "Unexpected error (RuntimeError)" in final["error"]
    assert (await service.status())["state"] == "failed"


@pytest.mark.asyncio
async def test_progress_is_saved_as_it_goes_and_large_libraries_are_paged(world, monkeypatch):
    monkeypatch.setattr(reindex_module, "BATCH_SIZE", 2)
    for i in range(5):
        world.docs.add(name=f"{i}.txt")
    service = _service(world)
    await service.start()

    final = await service.run()

    assert final["done"] == 5 and len(world.memory.calls) == 5
    assert world.settings.writes >= 6  # at least one write per document, plus start and finish


@pytest.mark.asyncio
async def test_run_without_a_started_job_does_nothing(world):
    world.docs.add()

    final = await _service(world).run()

    assert final["state"] == "idle" and world.memory.calls == []


@pytest.mark.asyncio
async def test_an_empty_library_finishes_at_once(world):
    started = await _service(world).start()

    assert started["state"] == "done" and started["total"] == 0 and started["finished_at"]


@pytest.mark.asyncio
async def test_a_memory_backend_with_indexing_off_is_reported_as_failed(world):
    world.docs.add()
    world.memory.disabled = True
    service = _service(world)
    await service.start()

    final = await service.run()

    assert final["state"] == "failed" and final["error"] == "Vector indexing is off"


# ---------------------------------------------------------------- one at a time


@pytest.mark.asyncio
async def test_a_second_start_while_one_is_running_is_refused(world):
    world.docs.add()
    service = _service(world)
    await service.start()

    with pytest.raises(ReindexAlreadyRunning):
        await service.start()


@pytest.mark.asyncio
async def test_a_job_that_stopped_reporting_is_stalled_and_may_be_taken_over(world):
    world.docs.add()
    service = _service(world)
    await service.start()
    world.clock.now += timedelta(seconds=reindex_module.STALE_AFTER_SECONDS + 1)

    assert (await service.status())["state"] == "stalled"
    restarted = await service.start()

    assert restarted["state"] == "running" and (await service.status())["state"] == "running"


@pytest.mark.asyncio
async def test_a_finished_job_does_not_block_the_next_one(world):
    world.docs.add()
    service = _service(world)
    await service.start()
    await service.run()

    assert (await service.start())["state"] == "running"


@pytest.mark.asyncio
async def test_start_is_refused_when_vector_indexing_is_off(world, monkeypatch):
    monkeypatch.setattr(settings, "VECTOR_INDEXING_ENABLED", False)

    with pytest.raises(ReindexNotPossible, match="Vector indexing is off"):
        await _service(world).start()


# ---------------------------------------------------------------- HTTP


def _client(service, *, role="admin"):
    app = FastAPI()
    app.include_router(memory_endpoints.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4(), role=role)
    app.dependency_overrides[get_reindex_service] = lambda: service
    return TestClient(app)


def test_only_an_admin_can_start_a_reindex_and_the_work_runs_in_the_background(world, monkeypatch):
    world.docs.add()
    ran = []

    async def fake_background():
        ran.append(True)

    monkeypatch.setattr(memory_endpoints, "run_reindex_in_background", fake_background)

    with _client(_service(world), role="user") as client:
        assert client.post("/memory/reindex").status_code == 403
    with _client(_service(world), role="admin") as client:
        response = client.post("/memory/reindex")

    assert response.status_code == 202 and response.json()["state"] == "running" and response.json()["total"] == 1
    assert ran == [True]


def test_a_second_start_is_a_409_and_an_empty_library_starts_no_background_work(world, monkeypatch):
    ran = []

    async def fake_background():
        ran.append(True)

    monkeypatch.setattr(memory_endpoints, "run_reindex_in_background", fake_background)

    with _client(_service(world)) as client:
        empty = client.post("/memory/reindex")
    world.docs.add()
    with _client(_service(world)) as client:
        first = client.post("/memory/reindex")
        second = client.post("/memory/reindex")

    assert empty.json()["state"] == "done" and first.status_code == 202 and second.status_code == 409
    assert ran == [True]  # only the real job was queued


def test_starting_with_vectors_off_is_a_400(world, monkeypatch):
    monkeypatch.setattr(settings, "VECTOR_INDEXING_ENABLED", False)

    with _client(_service(world)) as client:
        response = client.post("/memory/reindex")

    assert response.status_code == 400 and "Vector indexing is off" in response.json()["detail"]


def test_anyone_signed_in_can_read_the_status(world):
    with _client(_service(world), role="user") as client:
        response = client.get("/memory/reindex")

    assert response.status_code == 200 and response.json()["state"] == "idle"
