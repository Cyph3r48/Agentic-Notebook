"""Persistence for per-user provider credentials."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProviderCredential


class CredentialRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, *, user_id: UUID, provider: str) -> ProviderCredential | None:
        return await self.session.scalar(
            select(ProviderCredential).where(
                ProviderCredential.user_id == user_id,
                ProviderCredential.provider == provider,
            )
        )

    async def list_for_user(self, *, user_id: UUID) -> Sequence[ProviderCredential]:
        return (
            await self.session.scalars(select(ProviderCredential).where(ProviderCredential.user_id == user_id))
        ).all()

    async def upsert(
        self,
        *,
        user_id: UUID,
        provider: str,
        api_key_encrypted: str | None = None,
        key_hint: str | None = None,
        base_url: str | None = None,
        replace_key: bool = False,
        replace_url: bool = False,
    ) -> ProviderCredential:
        """Create or update the row. Fields are only touched when their `replace_*` flag is set."""
        row = await self.get(user_id=user_id, provider=provider)
        if row is None:
            row = ProviderCredential(user_id=user_id, provider=provider)
            self.session.add(row)
        if replace_key:
            row.api_key_encrypted = api_key_encrypted
            row.key_hint = key_hint
        if replace_url:
            row.base_url = base_url
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def delete(self, *, user_id: UUID, provider: str) -> bool:
        result = await self.session.execute(
            delete(ProviderCredential).where(
                ProviderCredential.user_id == user_id,
                ProviderCredential.provider == provider,
            )
        )
        await self.session.commit()
        return bool(result.rowcount)
