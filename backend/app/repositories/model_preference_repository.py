"""Persistence for per-user model preferences."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserModelPreference


class ModelPreferenceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, *, user_id: UUID) -> UserModelPreference | None:
        return await self.session.scalar(select(UserModelPreference).where(UserModelPreference.user_id == user_id))

    async def save(
        self,
        *,
        user_id: UUID,
        default_provider: str | None,
        default_model: str | None,
        enabled_models: dict[str, list[str]] | None,
    ) -> UserModelPreference:
        """Replace the whole preference row for this user."""
        row = await self.get(user_id=user_id)
        if row is None:
            row = UserModelPreference(user_id=user_id)
            self.session.add(row)
        row.default_provider = default_provider
        row.default_model = default_model
        row.enabled_models = enabled_models
        await self.session.commit()
        await self.session.refresh(row)
        return row
