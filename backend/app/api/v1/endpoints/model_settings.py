"""Choose which models appear in the chat list and which one is the default."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import get_current_user, get_model_settings_service
from app.models import User
from app.schemas.model_settings import ModelSettingsResponse, ModelSettingsUpdate
from app.services.model_settings_service import ModelSettingsService

router = APIRouter(prefix="/settings/models")


@router.get("", response_model=ModelSettingsResponse)
async def get_model_settings(
    response: Response,
    current_user: User = Depends(get_current_user),
    service: ModelSettingsService = Depends(get_model_settings_service),
) -> ModelSettingsResponse:
    response.headers["Cache-Control"] = "no-store"
    return await service.get(current_user.id)


@router.put("", response_model=ModelSettingsResponse)
async def update_model_settings(
    payload: ModelSettingsUpdate,
    response: Response,
    current_user: User = Depends(get_current_user),
    service: ModelSettingsService = Depends(get_model_settings_service),
) -> ModelSettingsResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await service.update(current_user.id, payload.enabled_models, payload.default)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
