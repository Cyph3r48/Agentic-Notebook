"""Conversation and message persistence operations."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
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
        sources: list[dict] | None = None,
        context_documents: list[UUID] | None = None,
    ) -> Message:
        row = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            model=model,
            sources=sources or [],
            context_documents=context_documents,
            metadata_json={},
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
    ) -> Sequence[Message]:
        return (
            await self.session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
