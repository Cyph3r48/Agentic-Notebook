"""Conversation and message persistence operations."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Message


class ChatRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_conversation(
        self,
        *,
        user_id: UUID,
        title: str | None,
        model: str,
    ) -> Conversation:
        row = Conversation(
            user_id=user_id,
            title=title,
            model=model,
            metadata_json={},
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def list_conversations_for_user(self, user_id: UUID) -> Sequence[Conversation]:
        return (
            await self.session.scalars(
                select(Conversation).where(Conversation.user_id == user_id).order_by(Conversation.updated_at.desc())
            )
        ).all()

    async def list_conversations_for_user_paginated(
        self,
        *,
        user_id: UUID,
        limit: int,
        offset: int,
        model: str | None = None,
        sort: str = "desc",
    ) -> Sequence[Conversation]:
        order = desc(Conversation.updated_at) if sort == "desc" else asc(Conversation.updated_at)
        query = select(Conversation).where(Conversation.user_id == user_id)
        if model:
            query = query.where(Conversation.model == model)
        return (
            await self.session.scalars(
                query.order_by(order)
                .offset(offset)
                .limit(limit)
            )
        ).all()

    async def get_conversation_for_user(self, *, conversation_id: UUID, user_id: UUID) -> Conversation | None:
        return await self.session.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )

    async def delete_conversation(self, row: Conversation) -> None:
        await self.session.delete(row)
        await self.session.commit()

    async def update_conversation_title(self, row: Conversation, *, title: str | None) -> None:
        row.title = title
        await self.session.commit()
        await self.session.refresh(row)

    async def create_message(
        self,
        *,
        conversation_id: UUID,
        role: str,
        content: str,
        model: str | None = None,
        tokens_used: int | None = None,
        sources: list[dict] | None = None,
        context_documents: list[UUID] | None = None,
        metadata: dict | None = None,
    ) -> Message:
        row = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            model=model,
            tokens_used=tokens_used,
            sources=sources or [],
            context_documents=context_documents,
            metadata_json=metadata or {},
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def list_messages_for_conversation(self, *, conversation_id: UUID) -> Sequence[Message]:
        return (
            await self.session.scalars(
                select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc())
            )
        ).all()

    async def list_messages_for_conversation_paginated(
        self,
        *,
        conversation_id: UUID,
        limit: int,
        offset: int,
        role: str | None = None,
        has_sources: bool | None = None,
        sort: str = "asc",
    ) -> Sequence[Message]:
        order = asc(Message.created_at) if sort == "asc" else desc(Message.created_at)
        query = select(Message).where(Message.conversation_id == conversation_id)
        if role:
            query = query.where(Message.role == role)
        if has_sources is True:
            query = query.where(func.jsonb_array_length(Message.sources) > 0)
        if has_sources is False:
            query = query.where(func.jsonb_array_length(Message.sources) == 0)
        return (
            await self.session.scalars(
                query.order_by(order)
                .offset(offset)
                .limit(limit)
            )
        ).all()
