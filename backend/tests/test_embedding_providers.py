from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import settings
from app.services.memory.embeddings import (
    MAX_DIM,
    EmbeddingConfig,
    EmbeddingFormatError,
    EmbeddingModelNotFound,
    OllamaCloudEmbeddings,
    OllamaEmbeddings,
    TeiEmbeddings,
    VectorPathError,
    bootstrap_config,
    build_embedding_provider,
    describe_error,
)

KEY = "ollama-embed-SENTINEL-1111"
SECRET_URL = "http://user:hunter2@embed.internal:11434"


class _Server:
    """A recording stand-in for an embedding service. `dim` is the vector size it returns."""

    def __init__(self, dim=64, kind="ollama"):
        self.dim, self.kind = dim, kind
        self.requests: list[httpx.Request] = []
        self.override = None

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            if self.override is not None:
                return self.override(request)
            if request.method == "GET":
                return httpx.Response(200)
            body = json.loads(request.content)
            inputs = body["input"] if self.kind == "ollama" else body["inputs"]
            inputs = [inputs] if isinstance(inputs, str) else inputs
            vectors = [[1.0] + [0.0] * (self.dim - 1) for _ in inputs]
            return httpx.Response(200, json={"embeddings": vectors} if self.kind == "ollama" else vectors)

        return httpx.MockTransport(handler)


def _ollama(server, **kwargs):
    config = EmbeddingConfig("ollama", "embeddinggemma", base_url="http://local-ollama.invalid:11434", **kwargs)
    return OllamaEmbeddings(config, server.transport())


def _cloud(server, **kwargs):
    kwargs.setdefault("api_key", KEY)
    return OllamaCloudEmbeddings(EmbeddingConfig("ollama_cloud", "embeddinggemma", **kwargs), server.transport())


def _tei(server, **kwargs):
    config = EmbeddingConfig("tei", "BAAI/bge-large-en-v1.5", base_url="http://tei.invalid:80", **kwargs)
    return TeiEmbeddings(config, server.transport())


# ---------------------------------------------------------------- identity


def test_identity_includes_provider_model_and_size_and_is_a_valid_collection_name(monkeypatch):
    monkeypatch.setattr(settings, "QDRANT_COLLECTION", "si_documents")
    config = EmbeddingConfig("ollama", "nomic-embed-text:latest", dim=768)

    name = config.collection_name()

    assert name.startswith("si_documents__ollama__nomic-embed-text-latest-") and name.endswith("__768")
    assert all(ch.isalnum() or ch in "_-" for ch in name)


def test_models_with_the_same_slug_get_different_identities():
    a = EmbeddingConfig("ollama", "org/model", dim=768)
    b = EmbeddingConfig("ollama", "org-model", dim=768)

    assert a.identity() != b.identity()


def test_the_same_model_at_another_size_or_provider_is_another_vector_space():
    base = EmbeddingConfig("ollama", "m", dim=768)

    assert base.identity() != base.with_dim(1024).identity()
    assert base.identity() != EmbeddingConfig("ollama_cloud", "m", dim=768).identity()
    assert base.identity() == EmbeddingConfig("ollama", "m", base_url="http://other:1", dim=768).identity()  # a URL is not identity


def test_identity_needs_the_size_and_the_key_never_shows_in_repr():
    with pytest.raises(ValueError, match="vector size is not known"):
        EmbeddingConfig("ollama", "m").identity()
    assert KEY not in repr(EmbeddingConfig("ollama_cloud", "m", api_key=KEY))


def test_the_factory_builds_each_provider_and_rejects_unknown_ones():
    assert isinstance(build_embedding_provider(EmbeddingConfig("tei", "m")), TeiEmbeddings)
    assert isinstance(build_embedding_provider(EmbeddingConfig("ollama", "m")), OllamaEmbeddings)
    assert isinstance(build_embedding_provider(EmbeddingConfig("ollama_cloud", "m")), OllamaCloudEmbeddings)
    with pytest.raises(VectorPathError, match="unknown provider"):
        build_embedding_provider(EmbeddingConfig("mystery", "m"))


@pytest.mark.parametrize(
    ("provider", "expected"),
    [("tei", ("tei", 1024)), ("ollama", ("ollama", None)), ("ollama_cloud", ("ollama_cloud", None))],
)
def test_bootstrap_config_follows_the_environment(monkeypatch, provider, expected):
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", provider)
    monkeypatch.setattr(settings, "EMBEDDING_DIM", 1024)

    config = bootstrap_config()

    assert (config.provider, config.dim) == expected
    assert config.api_key is None  # a key is never read from the environment for embeddings


# ---------------------------------------------------------------- Ollama (local)


@pytest.mark.asyncio
async def test_ollama_sends_the_model_and_a_list_of_inputs_to_api_embed_without_auth():
    server = _Server(dim=64)

    vectors = await _ollama(server).embed(["a", "b"])

    assert len(vectors) == 2 and len(vectors[0]) == 64
    request = server.requests[0]
    assert str(request.url) == "http://local-ollama.invalid:11434/api/embed"
    assert json.loads(request.content) == {"model": "embeddinggemma", "input": ["a", "b"]}
    assert "authorization" not in request.headers


@pytest.mark.asyncio
async def test_ollama_embeds_in_batches_of_32():
    server = _Server(dim=64)

    vectors = await _ollama(server).embed([f"t{i}" for i in range(70)])

    assert len(vectors) == 70
    assert [len(json.loads(r.content)["input"]) for r in server.requests] == [32, 32, 6]


@pytest.mark.asyncio
async def test_ollama_model_not_found_is_a_clear_safe_error():
    server = _Server()
    server.override = lambda request: httpx.Response(404, json={"error": f'model "embeddinggemma" not found {KEY}'})

    with pytest.raises(EmbeddingModelNotFound) as caught:
        await _ollama(server).embed(["x"])

    assert str(caught.value) == "Embeddings: the model was not found on the server"
    assert KEY not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"vectors": []}, "unexpected response format"),
        ({"embeddings": []}, "unexpected response format"),
        ({"embeddings": "nope"}, "unexpected response format"),
        ({"embeddings": [[0.1, 0.2]]}, "wrong number of vectors"),  # two inputs, one vector
    ],
)
async def test_ollama_rejects_malformed_answers(payload, message):
    server = _Server()
    server.override = lambda request: httpx.Response(200, json=payload)

    with pytest.raises(EmbeddingFormatError, match=message):
        await _ollama(server).embed(["a", "b"])


@pytest.mark.asyncio
async def test_a_vector_of_the_wrong_size_is_refused_when_the_index_size_is_known():
    server = _Server(dim=64)

    with pytest.raises(EmbeddingFormatError, match="returns size 64 but the index expects size 128"):
        await _ollama(server, dim=128).embed(["x"])


@pytest.mark.asyncio
async def test_probe_reports_the_vector_size_even_when_none_is_configured_or_a_wrong_one_is():
    server = _Server(dim=96)

    assert (await _ollama(server).probe()).dim == 96
    assert (await _ollama(server, dim=128).probe()).dim == 96  # the probe finds the truth, it does not check it
    assert (await _ollama(server).probe()).latency_ms >= 0


@pytest.mark.asyncio
@pytest.mark.parametrize("dim", [8, MAX_DIM + 1])
async def test_probe_rejects_sizes_that_cannot_be_an_embedding_model(dim):
    with pytest.raises(EmbeddingFormatError, match="outside the supported range"):
        await _ollama(_Server(dim=dim)).probe()


# ---------------------------------------------------------------- Ollama Cloud


@pytest.mark.asyncio
async def test_cloud_goes_to_ollama_com_with_the_bearer_key_and_ignores_a_saved_url():
    server = _Server()

    await _cloud(server, base_url="https://attacker.example").embed(["x"])

    request = server.requests[0]
    assert str(request.url) == "https://ollama.com/api/embed"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert not any("attacker" in str(r.url) for r in server.requests)


@pytest.mark.asyncio
async def test_cloud_without_a_key_sends_nothing():
    server = _Server()

    with pytest.raises(VectorPathError, match="no Ollama Cloud API key"):
        await _cloud(server, api_key=None).embed(["x"])
    result = await _cloud(server, api_key=None).health()

    assert result.ok is False and "no Ollama Cloud API key" in result.detail
    assert server.requests == []


@pytest.mark.asyncio
async def test_a_cloud_account_without_the_model_shows_up_as_model_not_found():
    server = _Server()
    server.override = lambda request: httpx.Response(404, json={"error": "model not found"})

    result = await _cloud(server).health()

    assert result.ok is False and result.detail == "Embeddings: the model was not found on the server"


@pytest.mark.asyncio
async def test_a_rejected_key_is_reported_by_status_not_by_content():
    server = _Server()
    server.override = lambda request: httpx.Response(401, json={"error": f"bad key {KEY}"})

    result = await _cloud(server).health()

    assert result.detail == "Embeddings: returned HTTP 401" and KEY not in result.detail


# ---------------------------------------------------------------- TEI


@pytest.mark.asyncio
async def test_tei_posts_inputs_to_embed_and_health_checks_first():
    server = _Server(dim=64, kind="tei")

    vectors = await _tei(server).embed(["a"])
    result = await _tei(server).health()

    assert len(vectors[0]) == 64 and result.ok is True
    posts = [r for r in server.requests if r.method == "POST"]
    assert (posts[0].url.host, posts[0].url.path) == ("tei.invalid", "/embed")
    assert json.loads(posts[0].content) == {"inputs": ["a"]}
    assert any(r.method == "GET" and r.url.path == "/health" for r in server.requests)


@pytest.mark.asyncio
async def test_tei_rejects_an_unexpected_shape():
    server = _Server(kind="tei")
    server.override = lambda request: httpx.Response(200, json={"vectors": []})

    with pytest.raises(EmbeddingFormatError, match="unexpected response format"):
        await _tei(server).embed(["a"])


@pytest.mark.asyncio
async def test_health_says_when_the_model_size_no_longer_matches_the_index():
    result = await _tei(_Server(dim=64, kind="tei"), dim=128).health()

    assert result.ok is False and "returns size 64 but the index expects size 128" in result.detail


# ---------------------------------------------------------------- safe messages


@pytest.mark.parametrize(
    ("exc", "message"),
    [
        (httpx.ConnectError(f"cannot reach {SECRET_URL}"), "Embeddings: could not connect"),
        (httpx.ReadTimeout("slow"), "Embeddings: timed out"),
        (RuntimeError(f"boom {SECRET_URL} {KEY}"), "Embeddings: failed (RuntimeError)"),
    ],
)
def test_error_descriptions_use_a_fixed_vocabulary(exc, message):
    text = describe_error("Embeddings", exc)

    assert text == message
    assert "hunter2" not in text and KEY not in text and "embed.internal" not in text
