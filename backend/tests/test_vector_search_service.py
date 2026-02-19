from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.config import settings
from app.services.vector_search_service import VectorSearchService


class _FakeSession:
    pass


@pytest.mark.asyncio
async def test_index_document_chunks_returns_empty_when_vector_indexing_disabled(monkeypatch):
    service = VectorSearchService(_FakeSession())
    original_enabled = settings.VECTOR_INDEXING_ENABLED
    settings.VECTOR_INDEXING_ENABLED = False

    async def fail_embed(_inputs):
        raise AssertionError("embedding should not run when vector indexing is disabled")

    monkeypatch.setattr(service, "_embed_texts", fail_embed)
    try:
        id_map = await service.index_document_chunks(
            user_id=uuid4(),
            document_id=uuid4(),
            original_filename="a.txt",
            chunks=[{"chunk_index": 0, "content": "hello", "metadata_json": {}}],
        )
    finally:
        settings.VECTOR_INDEXING_ENABLED = original_enabled

    assert id_map == {}


@pytest.mark.asyncio
async def test_delete_document_points_is_noop_when_vector_indexing_disabled(monkeypatch):
    service = VectorSearchService(_FakeSession())
    original_enabled = settings.VECTOR_INDEXING_ENABLED
    settings.VECTOR_INDEXING_ENABLED = False

    def fail_client(*_args, **_kwargs):
        raise AssertionError("qdrant client should not be constructed when vector indexing is disabled")

    monkeypatch.setattr("app.services.vector_search_service.AsyncQdrantClient", fail_client)
    try:
        await service.delete_document_points(user_id=uuid4(), document_id=uuid4())
    finally:
        settings.VECTOR_INDEXING_ENABLED = original_enabled


@pytest.mark.asyncio
async def test_search_qdrant_returns_empty_when_vector_indexing_disabled(monkeypatch):
    service = VectorSearchService(_FakeSession())
    original_enabled = settings.VECTOR_INDEXING_ENABLED
    settings.VECTOR_INDEXING_ENABLED = False

    async def fail_embed(_query):
        raise AssertionError("query embedding should not run when vector indexing is disabled")

    monkeypatch.setattr(service, "_embed_query", fail_embed)
    try:
        results = await service._search_qdrant(user_id=uuid4(), query="hello", limit=5, offset=0)
    finally:
        settings.VECTOR_INDEXING_ENABLED = original_enabled

    assert results == []


@pytest.mark.asyncio
async def test_index_document_chunks_returns_id_map_when_enabled(monkeypatch):
    service = VectorSearchService(_FakeSession())
    original_enabled = settings.VECTOR_INDEXING_ENABLED
    settings.VECTOR_INDEXING_ENABLED = True

    async def fake_embed_texts(inputs):
        return [[0.1, 0.2] for _ in inputs]

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            self.upsert_calls = []

        async def upsert(self, *, collection_name, points, wait):
            self.upsert_calls.append((collection_name, points, wait))

        async def close(self):
            return None

        async def get_collection(self, _name):
            return {"status": "ok"}

    async def fake_ensure_collection(_client):
        return None

    fake_client = _FakeClient()

    def build_client(*_args, **_kwargs):
        return fake_client

    monkeypatch.setattr(service, "_embed_texts", fake_embed_texts)
    monkeypatch.setattr(service, "_ensure_collection", fake_ensure_collection)
    monkeypatch.setattr("app.services.vector_search_service.AsyncQdrantClient", build_client)

    document_id = uuid4()
    try:
        id_map = await service.index_document_chunks(
            user_id=uuid4(),
            document_id=document_id,
            original_filename="notes.txt",
            chunks=[
                {
                    "chunk_index": 0,
                    "content": "alpha",
                    "content_hash": "h1",
                    "metadata_json": {"start": 0, "end": 5},
                },
                {
                    "chunk_index": 1,
                    "content": "beta",
                    "content_hash": "h2",
                    "metadata_json": {"start": 6, "end": 10},
                },
            ],
        )
    finally:
        settings.VECTOR_INDEXING_ENABLED = original_enabled

    assert id_map == {0: f"{document_id}:0", 1: f"{document_id}:1"}
    assert len(fake_client.upsert_calls) == 1
