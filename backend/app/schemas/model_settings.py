"""Schemas for choosing which models a user sees and which one is the default."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ModelEntry(BaseModel):
    id: str
    name: str
    enabled: bool
    # False for a saved choice the provider no longer lists (or could not list just now). It is kept, not dropped.
    available: bool = True


class ProviderModels(BaseModel):
    id: str
    label: str
    configured: bool
    models: list[ModelEntry]


class DefaultModel(BaseModel):
    provider: str = Field(max_length=20)
    model: str = Field(max_length=100)


class ModelSettingsResponse(BaseModel):
    providers: list[ProviderModels]
    default: DefaultModel | None = None


class ModelSettingsUpdate(BaseModel):
    """The full state the user wants. `enabled_models` null means every model is enabled; `default` null means none."""

    enabled_models: dict[str, list[str]] | None = None
    default: DefaultModel | None = None
