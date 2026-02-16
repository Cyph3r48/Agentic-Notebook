"""User persistence operations."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self.session.scalar(select(User).where(User.id == user_id))

    async def get_by_email(self, email: str) -> User | None:
        return await self.session.scalar(select(User).where(User.email == email))

    async def get_by_username(self, username: str) -> User | None:
        return await self.session.scalar(select(User).where(User.username == username))

    async def list_users(self) -> Sequence[User]:
        return (await self.session.scalars(select(User).order_by(User.created_at.desc()))).all()

    async def create_user(
        self,
        *,
        email: str,
        username: str,
        password_hash: str,
        full_name: str | None,
        role: str,
        is_active: bool = True,
        is_verified: bool = True,
    ) -> User:
        user = User(
            email=email,
            username=username,
            password_hash=password_hash,
            full_name=full_name,
            role=role,
            is_active=is_active,
            is_verified=is_verified,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def set_last_login(self, user: User, value: datetime) -> None:
        user.last_login = value
        await self.session.commit()

