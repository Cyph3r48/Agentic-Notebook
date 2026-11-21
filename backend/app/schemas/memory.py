"""Schemas for the memory health report. Details are fixed strings: no URLs, keys or content."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class MemoryComponentHealth(BaseModel):
    ok: bool
    detail: str


class MemoryHealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down", "disabled"]
    backend: str
    vector_enabled: bool
    detail: str
    components: dict[str, MemoryComponentHealth] = {}
    last_error: str | None = None
    last_error_at: datetime | None = None
