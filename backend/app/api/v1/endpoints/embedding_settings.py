"""Choose the embedding model for the whole system (admin only). Responses never contain a key."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import get_current_user, get_embedding_settings_service, require_roles
from app.core.secret_box import SecretsNotConfigured
from app.models import User
from app.schemas.embedding_settings import EmbeddingCandidate, EmbeddingSettingsResponse, EmbeddingTestResult
from app.services.embedding_settings_service import EmbeddingProbeFailed, EmbeddingSettingsService

router = APIRouter(prefix="/settings/embedding")


@router.get("", response_model=EmbeddingSettingsResponse)
async def get_embedding_settings(
    response: Response,
    current_user: User = Depends(get_current_user),
    service: EmbeddingSettingsService = Depends(get_embedding_settings_service),
) -> EmbeddingSettingsResponse:
    """Anyone signed in can see which model embeds their documents; only an admin can change it."""
    response.headers["Cache-Control"] = "no-store"
    return await service.get()


@router.post("/test", response_model=EmbeddingTestResult)
async def test_embedding_settings(
    candidate: EmbeddingCandidate,
    response: Response,
    admin: User = Depends(require_roles("admin")),
    service: EmbeddingSettingsService = Depends(get_embedding_settings_service),
) -> EmbeddingTestResult:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await service.test(candidate)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("", response_model=EmbeddingSettingsResponse)
async def apply_embedding_settings(
    candidate: EmbeddingCandidate,
    response: Response,
    admin: User = Depends(require_roles("admin")),
    service: EmbeddingSettingsService = Depends(get_embedding_settings_service),
) -> EmbeddingSettingsResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await service.apply(candidate, admin.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except EmbeddingProbeFailed as exc:
        # Nothing was saved: the previous choice stays active.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Not saved. {exc}") from exc
    except SecretsNotConfigured as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
