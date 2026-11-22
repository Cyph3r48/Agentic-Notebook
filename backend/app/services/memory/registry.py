"""Chooses the memory backend named by MEMORY_BACKEND."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.memory.base import MemoryBackendUnavailable, MemoryProvider
from app.services.memory.builtin import BuiltinMemoryProvider


def validate_memory_backend() -> None:
    """Raise MemoryBackendUnavailable when the configured backend has no adapter."""
    if settings.MEMORY_BACKEND != "builtin":
        raise MemoryBackendUnavailable(
            f"MEMORY_BACKEND={settings.MEMORY_BACKEND} is not implemented yet. Use MEMORY_BACKEND=builtin."
        )


def get_memory_provider(session: AsyncSession) -> MemoryProvider:
    validate_memory_backend()
    return BuiltinMemoryProvider(session)
