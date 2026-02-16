"""Common API schemas used across endpoints."""

from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error: str
    message: str
    request_id: str | None = None
    details: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str = Field(description="health status")
    environment: str | None = None
    smc_enabled: bool | None = None
    version: str | None = None
