"""Memory backend status."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_memory_provider
from app.models import User
from app.schemas.memory import MemoryComponentHealth, MemoryHealthResponse
from app.services.memory import MemoryProvider


router = APIRouter(prefix="/memory")


@router.get("/health", response_model=MemoryHealthResponse)
async def memory_health(
    current_user: User = Depends(get_current_user),
    memory: MemoryProvider = Depends(get_memory_provider),
) -> MemoryHealthResponse:
    report = await memory.health()
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
    )
