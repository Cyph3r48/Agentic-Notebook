"""Chat endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user
from app.core.config import settings
from app.models import User
from app.repositories import ChatRepository, SearchRepository
from app.schemas.chat import (
    ChatTurnResponse,
    ConversationCreateRequest,
    ConversationResponse,
    ConversationUpdateRequest,
    MessageCreateRequest,
    MessageResponse,
)


router = APIRouter(prefix="/chat")


def _snippet(text: str, *, limit: int = 220) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


@router.post("/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreateRequest,
    request: Request,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
) -> ConversationResponse:
    chat_repo = ChatRepository(session)
    row = await chat_repo.create_conversation(
        user_id=current_user.id,
        title=payload.title,
        model=payload.model or settings.DEFAULT_MODEL,
    )
    logger.bind(
        request_id=getattr(request.state, "request_id", None),
        action="chat_create_conversation",
        user_id=str(current_user.id),
        conversation_id=str(row.id),
    ).info("Conversation created")
    return ConversationResponse(
        id=str(row.id),
        title=row.title,
        model=row.model,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    request: Request,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
) -> list[ConversationResponse]:
    rows = await ChatRepository(session).list_conversations_for_user(current_user.id)
    logger.bind(
        request_id=getattr(request.state, "request_id", None),
        action="chat_list_conversations",
        user_id=str(current_user.id),
    ).info("Conversations listed count={count}", count=len(rows))
    return [
        ConversationResponse(
            id=str(row.id),
            title=row.title,
            model=row.model,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    request: Request,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
) -> ConversationResponse:
    chat_repo = ChatRepository(session)
    row = await chat_repo.get_conversation_for_user(conversation_id=conversation_id, user_id=current_user.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    logger.bind(
        request_id=getattr(request.state, "request_id", None),
        action="chat_get_conversation",
        user_id=str(current_user.id),
        conversation_id=str(conversation_id),
    ).info("Conversation fetched")
    return ConversationResponse(
        id=str(row.id),
        title=row.title,
        model=row.model,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    request: Request,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    chat_repo = ChatRepository(session)
    row = await chat_repo.get_conversation_for_user(conversation_id=conversation_id, user_id=current_user.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    await chat_repo.delete_conversation(row)
    logger.bind(
        request_id=getattr(request.state, "request_id", None),
        action="chat_delete_conversation",
        user_id=str(current_user.id),
        conversation_id=str(conversation_id),
    ).info("Conversation deleted")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: UUID,
    payload: ConversationUpdateRequest,
    request: Request,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
) -> ConversationResponse:
    chat_repo = ChatRepository(session)
    row = await chat_repo.get_conversation_for_user(conversation_id=conversation_id, user_id=current_user.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    await chat_repo.update_conversation_title(row, title=payload.title)
    logger.bind(
        request_id=getattr(request.state, "request_id", None),
        action="chat_update_conversation",
        user_id=str(current_user.id),
        conversation_id=str(conversation_id),
    ).info("Conversation updated")
    return ConversationResponse(
        id=str(row.id),
        title=row.title,
        model=row.model,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/conversations/{conversation_id}/messages", response_model=ChatTurnResponse)
async def send_message(
    conversation_id: UUID,
    payload: MessageCreateRequest,
    request: Request,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
) -> ChatTurnResponse:
    chat_repo = ChatRepository(session)
    conversation = await chat_repo.get_conversation_for_user(
        conversation_id=conversation_id,
        user_id=current_user.id,
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    user_message = await chat_repo.create_message(
        conversation_id=conversation.id,
        role="user",
        content=payload.content,
        model=conversation.model,
    )

    sources: list[dict] = []
    assistant_text = "Message received. RAG lookup is disabled for this request."
    if payload.use_rag:
        search_results = await SearchRepository(session).search_chunks(
            user_id=current_user.id,
            query=payload.content,
            limit=3,
        )
        sources = [
            {
                "document_id": row["document_id"],
                "original_filename": row["original_filename"],
                "chunk_index": row["chunk_index"],
                "score": row["score"],
                "snippet": _snippet(row["content"]),
            }
            for row in search_results
        ]
        if sources:
            bullet_lines = [
                f"- {source['original_filename']}#{source['chunk_index']}: {source['snippet']}"
                for source in sources[:3]
            ]
            assistant_text = "I found relevant context in your documents:\n" + "\n".join(bullet_lines)
        else:
            assistant_text = "I could not find relevant context in your uploaded documents."

    context_documents = list({UUID(source["document_id"]) for source in sources}) if sources else None
    assistant_message = await chat_repo.create_message(
        conversation_id=conversation.id,
        role="assistant",
        content=assistant_text,
        model=conversation.model,
        sources=sources,
        context_documents=context_documents,
    )

    logger.bind(
        request_id=getattr(request.state, "request_id", None),
        action="chat_send_message",
        user_id=str(current_user.id),
        conversation_id=str(conversation.id),
        use_rag=payload.use_rag,
        source_count=len(sources),
    ).info("Message processed")

    return ChatTurnResponse(
        conversation_id=str(conversation.id),
        user_message=MessageResponse(
            id=str(user_message.id),
            conversation_id=str(user_message.conversation_id),
            role=user_message.role,
            content=user_message.content,
            model=user_message.model,
            sources=list(user_message.sources or []),
            created_at=user_message.created_at,
        ),
        assistant_message=MessageResponse(
            id=str(assistant_message.id),
            conversation_id=str(assistant_message.conversation_id),
            role=assistant_message.role,
            content=assistant_message.content,
            model=assistant_message.model,
            sources=list(assistant_message.sources or []),
            created_at=assistant_message.created_at,
        ),
    )


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: UUID,
    request: Request,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
) -> list[MessageResponse]:
    chat_repo = ChatRepository(session)
    conversation = await chat_repo.get_conversation_for_user(
        conversation_id=conversation_id,
        user_id=current_user.id,
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    rows = await chat_repo.list_messages_for_conversation(conversation_id=conversation_id)
    logger.bind(
        request_id=getattr(request.state, "request_id", None),
        action="chat_list_messages",
        user_id=str(current_user.id),
        conversation_id=str(conversation_id),
    ).info("Messages listed count={count}", count=len(rows))
    return [
        MessageResponse(
            id=str(row.id),
            conversation_id=str(row.conversation_id),
            role=row.role,
            content=row.content,
            model=row.model,
            sources=list(row.sources or []),
            created_at=row.created_at,
        )
        for row in rows
    ]
