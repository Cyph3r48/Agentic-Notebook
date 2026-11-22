"""Schemas for the memory health report. Details are fixed strings: no URLs, keys or content."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class MemoryComponentHealth(BaseModel):
    ok: bool
    detail: str


class MemoryEmbeddingInfo(BaseModel):
    provider: str
    model: str
    dim: int | None = None
    identity: str


class ReindexStatus(BaseModel):
    # idle | running | done | failed | stalled (running, but silent for too long to be trusted)
    state: Literal["idle", "running", "done", "failed", "stalled"]
    total: int = 0
    done: int = 0
    failed: int = 0
    started_at: str | None = None
    updated_at: str | None = None
    finished_at: str | None = None
    error: str | None = None


class MemoryHealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down", "disabled"]
    backend: str
    vector_enabled: bool
    detail: str
    components: dict[str, MemoryComponentHealth] = {}
    last_error: str | None = None
    last_error_at: datetime | None = None
    embedding: MemoryEmbeddingInfo | None = None
    documents_total: int | None = None
    documents_in_index: int | None = None
    reindex: ReindexStatus | None = None
