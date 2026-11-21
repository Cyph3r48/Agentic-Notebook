"""Search endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from loguru import logger

from app.api.deps import get_current_user, get_memory_provider
from app.models import User
from app.schemas.search import SearchRequest, SearchResponse, SearchResultItem
from app.services.memory import MemoryProvider


router = APIRouter(prefix="/search")


@router.post("", response_model=SearchResponse)
async def search_documents(
    payload: SearchRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    memory: MemoryProvider = Depends(get_memory_provider),
) -> SearchResponse:
    outcome = await memory.search(
        user_id=current_user.id,
        query=payload.query,
        limit=payload.limit,
        offset=payload.offset,
        min_score=payload.min_score,
    )

    logger.bind(
        request_id=getattr(request.state, "request_id", None),
        action="search_documents",
        user_id=str(current_user.id),
    ).info(
        "Search completed query_length={query_length} results={count} mode={mode} limit={limit} offset={offset} min_score={min_score}",
        query_length=len(payload.query),
        count=len(outcome.results),
        mode=outcome.mode,
        limit=payload.limit,
        offset=payload.offset,
        min_score=payload.min_score,
    )

    return SearchResponse(
        query=payload.query,
        results=[
            SearchResultItem(
                document_id=item.document_id,
                original_filename=item.original_filename,
                chunk_index=item.chunk_index,
                content=item.content,
                score=item.score,
            )
            for item in outcome.results
        ],
        mode=outcome.mode,
        degraded_reason=outcome.degraded_reason,
    )
