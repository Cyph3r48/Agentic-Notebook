"""Memory backend status and re-indexing."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.api.deps import get_current_user, get_memory_provider, get_reindex_service, require_roles
from app.models import User
from app.schemas.memory import (
    MemoryComponentHealth,
    MemoryEmbeddingInfo,
    MemoryHealthResponse,
    ReindexStatus,
)
from app.services.memory import MemoryProvider
from app.services.memory.reindex import (
    ReindexAlreadyRunning,
    ReindexNotPossible,
    ReindexService,
    run_reindex_in_background,
)

router = APIRouter(prefix="/memory")


@router.get("/health", response_model=MemoryHealthResponse)
async def memory_health(
    current_user: User = Depends(get_current_user),
    memory: MemoryProvider = Depends(get_memory_provider),
    reindex: ReindexService = Depends(get_reindex_service),
) -> MemoryHealthResponse:
    report = await memory.health()
    total = in_index = None
    if report.embedding:
        total, in_index = await memory.index_counts(report.embedding["identity"])
    return MemoryHealthResponse(
        status=report.status,
        backend=report.backend,
        vector_enabled=report.vector_enabled,
        detail=report.detail,
        components={
            name: MemoryComponentHealth(ok=part.ok, detail=part.detail) for name, part in report.components.items()
        },
        last_error=report.last_error,
        last_error_at=report.last_error_at,
        embedding=MemoryEmbeddingInfo(**report.embedding) if report.embedding else None,
        documents_total=total,
        documents_in_index=in_index,
        reindex=ReindexStatus(**await reindex.status()),
    )


@router.get("/reindex", response_model=ReindexStatus)
async def reindex_status(
    current_user: User = Depends(get_current_user),
    reindex: ReindexService = Depends(get_reindex_service),
) -> ReindexStatus:
    return ReindexStatus(**await reindex.status())


@router.post("/reindex", response_model=ReindexStatus, status_code=status.HTTP_202_ACCEPTED)
async def start_reindex(
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_roles("admin")),
    reindex: ReindexService = Depends(get_reindex_service),
) -> ReindexStatus:
    """Embed every stored chunk again with the active embedding model (admin only). Runs in the background."""
    try:
        state = await reindex.start()
    except ReindexAlreadyRunning as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ReindexNotPossible as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if state["state"] == "running":
        background_tasks.add_task(run_reindex_in_background)
    return ReindexStatus(**state)
