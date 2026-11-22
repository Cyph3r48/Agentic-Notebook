"""Needs Postgres with migrations applied: set RUN_DB_INTEGRATION_TESTS=1 (run this file in its own process)."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

pytestmark = []
if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
    pytestmark.append(pytest.mark.skip(reason="Set RUN_DB_INTEGRATION_TESTS=1 to run DB integration tests"))


@pytest.mark.asyncio
async def test_settings_preferences_and_index_queries_against_real_postgres():
    from app.core.database import SessionLocal
    from app.models import Document, DocumentChunk, User
    from app.repositories import (
        DocumentRepository,
        ModelPreferenceRepository,
        SystemSettingsRepository,
    )

    key = f"test-{uuid4().hex[:12]}"
    async with SessionLocal() as session:
        user = User(email=f"{uuid4().hex}@example.test", username=uuid4().hex[:20], password_hash="x")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

        # ---- system settings: put replaces everything, put_value keeps the secret and the editor
        settings_repo = SystemSettingsRepository(session)
        assert await settings_repo.get(key) is None
        await settings_repo.put(key, {"provider": "ollama", "dim": 768}, secret_encrypted="gAAAA-token", updated_by=user_id)
        await settings_repo.put_value(key, {"state": "running", "done": 2})
        row = await settings_repo.get(key)
        assert row.value == {"state": "running", "done": 2}
        assert row.secret_encrypted == "gAAAA-token" and row.updated_by == user_id
        await settings_repo.put(key, {"provider": "tei"})
        row = await settings_repo.get(key)
        assert row.secret_encrypted is None and row.updated_by is None  # put replaces the whole row

        # ---- model preferences: save replaces the whole row
        prefs = ModelPreferenceRepository(session)
        assert await prefs.get(user_id=user_id) is None
        await prefs.save(user_id=user_id, default_provider="openai", default_model="o3", enabled_models={"openai": ["o3"]})
        await prefs.save(user_id=user_id, default_provider=None, default_model=None, enabled_models=None)
        saved = await prefs.get(user_id=user_id)
        assert (saved.default_provider, saved.default_model, saved.enabled_models) == (None, None, None)

        # ---- index bookkeeping over documents and chunks
        identity, other = f"tei__a-{uuid4().hex[:6]}__1024", f"ollama__b-{uuid4().hex[:6]}__768"
        docs = []
        for index_name, status in ((identity, "completed"), (other, "completed"), (None, "completed"), (identity, "failed")):
            metadata = {"vector_index": index_name} if index_name else {}
            doc = Document(
                user_id=user_id, filename=f"{uuid4().hex}.txt", original_filename="x.txt", file_type="txt", file_size=1,
                content_hash=uuid4().hex, storage_path="/nowhere", metadata_json=metadata, status=status,
            )
            session.add(doc)
            docs.append(doc)
        await session.commit()
        for doc in docs:
            await session.refresh(doc)
        session.add_all(
            DocumentChunk(document_id=docs[0].id, chunk_index=i, content=f"c{i}", content_hash=f"h{i}", metadata_json={})
            for i in (2, 0, 1)
        )
        await session.commit()

        repo = DocumentRepository(session)
        # The identity is unique to this run: only the completed document in that index counts, not the failed one.
        assert await repo.count_in_index(identity) == 1
        assert await repo.count_in_index(other) == 1
        assert await repo.count_in_index(f"nothing-{uuid4().hex}") == 0
        assert [c.chunk_index for c in await repo.chunks_for_document(docs[0].id)] == [0, 1, 2]

        # paging walks every completed document exactly once, in id order
        seen, after = [], None
        while True:
            page = await repo.completed_ids_after(after, 2)
            if not page:
                break
            seen.extend(page)
            after = page[-1]
        assert seen == sorted(seen) and len(seen) == len(set(seen)) == await repo.count_completed()
        assert {docs[0].id, docs[1].id, docs[2].id} <= set(seen) and docs[3].id not in seen

        # ---- clean up
        for doc in docs:
            await session.delete(doc)
        await session.delete(await settings_repo.get(key))
        await session.delete(await prefs.get(user_id=user_id))
        await session.commit()
        await session.refresh(user)
        await session.delete(user)
        await session.commit()
