"""Persistence for system-wide settings and job state."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SystemSetting


class SystemSettingsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, key: str) -> SystemSetting | None:
        return await self.session.scalar(select(SystemSetting).where(SystemSetting.key == key))

    async def put(
        self,
        key: str,
        value: dict,
        *,
        secret_encrypted: str | None = None,
        updated_by: UUID | None = None,
    ) -> SystemSetting:
        """Replace the whole row, secret included."""
        row = await self.get(key)
        if row is None:
            row = SystemSetting(key=key)
            self.session.add(row)
        row.value = value
        row.secret_encrypted = secret_encrypted
        row.updated_by = updated_by
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def put_value(self, key: str, value: dict) -> SystemSetting:
        """Replace only the value, keeping any secret and the last editor (used for progress records)."""
        row = await self.get(key)
        if row is None:
            row = SystemSetting(key=key)
            self.session.add(row)
        row.value = value
        await self.session.commit()
        await self.session.refresh(row)
        return row
