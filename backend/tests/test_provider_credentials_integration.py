"""Needs the Docker stack (Postgres with migrations applied): set RUN_DB_INTEGRATION_TESTS=1."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

pytestmark = []
if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
    pytestmark.append(pytest.mark.skip(reason="Set RUN_DB_INTEGRATION_TESTS=1 to run DB integration tests"))


@pytest.mark.asyncio
async def test_provider_credentials_round_trip_and_unique_constraint(master_key):
    from sqlalchemy.exc import IntegrityError

    from app.core.database import SessionLocal
    from app.core.secret_box import get_secret_box
    from app.models import ProviderCredential, User
    from app.repositories import CredentialRepository

    async with SessionLocal() as session:
        user = User(email=f"{uuid4().hex}@example.test", username=uuid4().hex[:20], password_hash="x")
        session.add(user)
        await session.commit()
        await session.refresh(user)

        context = f"{user.id}:anthropic"
        token = get_secret_box().encrypt("sk-ant-integration-0001", context=context)
        repo = CredentialRepository(session)
        await repo.upsert(user_id=user.id, provider="anthropic", api_key_encrypted=token, key_hint="0001", replace_key=True)

        row = await repo.get(user_id=user.id, provider="anthropic")
        assert row.key_hint == "0001" and "sk-ant-integration" not in row.api_key_encrypted
        assert get_secret_box().decrypt(row.api_key_encrypted, context=context) == "sk-ant-integration-0001"

        # a second save updates the same row instead of adding one
        await repo.upsert(user_id=user.id, provider="anthropic", base_url=None, replace_url=True)
        assert len(await repo.list_for_user(user_id=user.id)) == 1

        session.add(ProviderCredential(user_id=user.id, provider="anthropic"))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

        assert await repo.delete(user_id=user.id, provider="anthropic") is True
        await session.delete(user)
        await session.commit()
