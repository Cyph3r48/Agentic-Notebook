"""Search endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user
from app.models import User
from app.schemas.search import SearchRequest, SearchResponse, SearchResultItem
from app.services.vector_search_service import VectorSearchService


router = APIRouter(prefix="/search")


@router.post("", response_model=SearchResponse)
async def search_documents(
    payload: SearchRequest,
    request: Request,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
) -> SearchResponse:
    items = await VectorSearchService(session).search(
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
        "Search completed query_length={query_length} results={count} limit={limit} offset={offset} min_score={min_score}",
        query_length=len(payload.query),
        count=len(items),
        limit=payload.limit,
        offset=payload.offset,
        min_score=payload.min_score,
    )

    return SearchResponse(
        query=payload.query,
        results=[SearchResultItem(**item) for item in items],
    )
