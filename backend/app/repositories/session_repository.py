"""Refresh-session persistence operations."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Session


class SessionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_session(
        self,
        *,
        user_id: UUID,
        session_token: str,
        expires_at: datetime,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Session:
        row = Session(
            user_id=user_id,
            session_token=session_token,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def get_by_token_and_user(self, *, token: str, user_id: UUID) -> Session | None:
        return await self.session.scalar(
            select(Session).where(
                Session.session_token == token,
                Session.user_id == user_id,
            )
        )

    async def rotate_session_token(self, row: Session, *, token: str, expires_at: datetime) -> None:
        row.session_token = token
        row.expires_at = expires_at
        await self.session.commit()

    async def delete_by_token(self, token: str) -> None:
        await self.session.execute(delete(Session).where(Session.session_token == token))
        await self.session.commit()

    async def delete(self, row: Session) -> None:
        await self.session.delete(row)
        await self.session.commit()

