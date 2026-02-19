"""Chat endpoints."""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from loguru import logger
from starlette.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user
from app.core.config import settings
from app.models import User
from app.repositories import ChatRepository
from app.schemas.chat import (
    ChatTurnResponse,
    ConversationCreateRequest,
    ConversationResponse,
    ConversationUpdateRequest,
    MessageCreateRequest,
    MessageResponse,
)
from app.services.llm_service import LLMService
from app.services.vector_search_service import VectorSearchService


router = APIRouter(prefix="/chat")


def _snippet(text: str, *, limit: int = 220) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _estimate_tokens(text: str) -> int:
    return max(int(len(text.split()) * 1.3), 1)


def _resolve_model(model: str | None) -> str:
    selected = (model or settings.DEFAULT_MODEL).strip()
    if not selected:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Model is required")
    if selected.lower().startswith("claude-"):
        allowed = {settings.CLAUDE_SONNET_MODEL, settings.CLAUDE_OPUS_MODEL}
        if selected not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported Anthropic model. Allowed: {sorted(allowed)}",
            )
    return selected


def _as_message_response(message) -> MessageResponse:
    return MessageResponse(
        id=str(message.id),
        conversation_id=str(message.conversation_id),
        role=message.role,
        content=message.content,
        model=message.model,
        tokens_used=getattr(message, "tokens_used", None),
        sources=list(message.sources or []),
        metadata=dict(message.metadata_json or {}),
        created_at=message.created_at,
    )


async def _process_chat_turn(
    *,
    chat_repo: ChatRepository,
    current_user: User,
    conversation,
    payload: MessageCreateRequest,
    session: AsyncSession,
) -> ChatTurnResponse:
    user_message = await chat_repo.create_message(
        conversation_id=conversation.id,
        role="user",
        content=payload.content,
        model=conversation.model,
        tokens_used=_estimate_tokens(payload.content),
        metadata={"rag_used": payload.use_rag},
    )

    sources: list[dict] = []
    context_lines: list[str] = []
    if payload.use_rag:
        search_results = await VectorSearchService(session).search(
            user_id=current_user.id,
            query=payload.content,
            limit=3,
            offset=0,
            min_score=0.1,
        )
        sources = [
            {
                "source_id": f"{row['document_id']}:{row['chunk_index']}",
                "document_id": row["document_id"],
                "original_filename": row["original_filename"],
                "chunk_index": row["chunk_index"],
                "rank": rank,
                "score": row["score"],
                "snippet": _snippet(row["content"]),
                "content_hash": row.get("content_hash"),
                "span_start": row.get("span_start"),
                "span_end": row.get("span_end"),
            }
            for rank, row in enumerate(search_results, start=1)
        ]
        context_lines = [f"{source['original_filename']}#{source['chunk_index']}: {source['snippet']}" for source in sources]

    assistant_text, llm_metadata = await LLMService.generate_chat_reply(
        model=conversation.model,
        user_message=payload.content,
        context_lines=context_lines,
    )
    context_documents = list({UUID(source["document_id"]) for source in sources}) if sources else None
    assistant_message = await chat_repo.create_message(
        conversation_id=conversation.id,
        role="assistant",
        content=assistant_text,
        model=conversation.model,
        tokens_used=int(llm_metadata.get("token_estimate", _estimate_tokens(assistant_text))),
        sources=sources,
        context_documents=context_documents,
        metadata={
            **llm_metadata,
            "rag_used": payload.use_rag,
            "source_count": len(sources),
        },
    )

    return ChatTurnResponse(
        conversation_id=str(conversation.id),
        user_message=_as_message_response(user_message),
        assistant_message=_as_message_response(assistant_message),
    )


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
        model=_resolve_model(payload.model),
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
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    model: str | None = Query(default=None),
    sort: str = Query(default="desc", pattern="^(asc|desc)$"),
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
) -> list[ConversationResponse]:
    rows = await ChatRepository(session).list_conversations_for_user_paginated(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        model=model,
        sort=sort,
    )
    logger.bind(
        request_id=getattr(request.state, "request_id", None),
        action="chat_list_conversations",
        user_id=str(current_user.id),
    ).info(
        "Conversations listed count={count} limit={limit} offset={offset} model={model} sort={sort}",
        count=len(rows),
        limit=limit,
        offset=offset,
        model=model,
        sort=sort,
    )
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

    turn = await _process_chat_turn(
        chat_repo=chat_repo,
        current_user=current_user,
        conversation=conversation,
        payload=payload,
        session=session,
    )

    logger.bind(
        request_id=getattr(request.state, "request_id", None),
        action="chat_send_message",
        user_id=str(current_user.id),
        conversation_id=str(conversation.id),
        use_rag=payload.use_rag,
        source_count=len(turn.assistant_message.sources),
    ).info("Message processed")
    return turn


@router.post("/conversations/{conversation_id}/messages/stream")
async def stream_message(
    conversation_id: UUID,
    payload: MessageCreateRequest,
    request: Request,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    chat_repo = ChatRepository(session)
    conversation = await chat_repo.get_conversation_for_user(conversation_id=conversation_id, user_id=current_user.id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    async def _events():
        user_message = await chat_repo.create_message(
            conversation_id=conversation.id,
            role="user",
            content=payload.content,
            model=conversation.model,
            tokens_used=_estimate_tokens(payload.content),
            metadata={"rag_used": payload.use_rag},
        )
        sources: list[dict] = []
        context_lines: list[str] = []
        if payload.use_rag:
            search_results = await VectorSearchService(session).search(
                user_id=current_user.id,
                query=payload.content,
                limit=3,
                offset=0,
                min_score=0.1,
            )
            sources = [
                {
                    "source_id": f"{row['document_id']}:{row['chunk_index']}",
                    "document_id": row["document_id"],
                    "original_filename": row["original_filename"],
                    "chunk_index": row["chunk_index"],
                    "rank": rank,
                    "score": row["score"],
                    "snippet": _snippet(row["content"]),
                    "content_hash": row.get("content_hash"),
                    "span_start": row.get("span_start"),
                    "span_end": row.get("span_end"),
                }
                for rank, row in enumerate(search_results, start=1)
            ]
            context_lines = [f"{source['original_filename']}#{source['chunk_index']}: {source['snippet']}" for source in sources]

        accumulated = ""
        stream_error_type: str | None = None
        try:
            async for delta in LLMService.stream_chat_reply(
                model=conversation.model,
                user_message=payload.content,
                context_lines=context_lines,
            ):
                accumulated += delta
                yield f"event: delta\ndata: {json.dumps({'text': delta})}\n\n"
        except Exception as exc:
            logger.warning(
                "Chat stream provider failed conversation_id={conversation_id}: {error}",
                conversation_id=str(conversation.id),
                error=str(exc),
            )
            stream_error_type = "provider_stream_error"
            if context_lines:
                accumulated = "I found relevant context in your documents:\n" + "\n".join(context_lines[:3])
            else:
                accumulated = "I could not find relevant context in your uploaded documents."

        if not accumulated:
            accumulated = "I could not find relevant context in your uploaded documents."
        context_documents = list({UUID(source["document_id"]) for source in sources}) if sources else None
        assistant_metadata = {
            "provider": "anthropic" if LLMService.is_anthropic_model(conversation.model) else "ollama",
            "model": conversation.model,
            "rag_used": payload.use_rag,
            "source_count": len(sources),
            "token_estimate": _estimate_tokens(accumulated),
            "total_tokens": _estimate_tokens(accumulated),
        }
        if stream_error_type:
            assistant_metadata["error_type"] = stream_error_type
        assistant_message = await chat_repo.create_message(
            conversation_id=conversation.id,
            role="assistant",
            content=accumulated,
            model=conversation.model,
            tokens_used=int(assistant_metadata["total_tokens"]),
            sources=sources,
            context_documents=context_documents,
            metadata=assistant_metadata,
        )
        message_payload = {
            "conversation_id": str(conversation.id),
            "user_message_id": str(user_message.id),
            "assistant_message_id": str(assistant_message.id),
            "sources": sources,
            "metadata": assistant_metadata,
        }
        yield f"event: message\ndata: {json.dumps(message_payload)}\n\n"
        yield "event: done\ndata: {}\n\n"

    logger.bind(
        request_id=getattr(request.state, "request_id", None),
        action="chat_stream_message",
        user_id=str(current_user.id),
        conversation_id=str(conversation.id),
    ).info("Message stream generated")
    return StreamingResponse(_events(), media_type="text/event-stream")


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    role: str | None = Query(default=None, pattern="^(user|assistant|system)$"),
    has_sources: bool | None = Query(default=None),
    sort: str = Query(default="asc", pattern="^(asc|desc)$"),
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

    rows = await chat_repo.list_messages_for_conversation_paginated(
        conversation_id=conversation_id,
        limit=limit,
        offset=offset,
        role=role,
        has_sources=has_sources,
        sort=sort,
    )
    logger.bind(
        request_id=getattr(request.state, "request_id", None),
        action="chat_list_messages",
        user_id=str(current_user.id),
        conversation_id=str(conversation_id),
    ).info(
        "Messages listed count={count} limit={limit} offset={offset} role={role} has_sources={has_sources} sort={sort}",
        count=len(rows),
        limit=limit,
        offset=offset,
        role=role,
        has_sources=has_sources,
        sort=sort,
    )
    return [
        _as_message_response(row)
        for row in rows
    ]


@router.get("/models")
async def list_chat_models() -> dict:
    return await LLMService.list_models()


@router.get("/providers/health")
async def provider_health() -> dict:
    return await LLMService.provider_health()
