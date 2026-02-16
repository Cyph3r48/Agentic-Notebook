"""Alembic migration helpers for application startup."""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config


def _alembic_config() -> Config:
    backend_root = Path(__file__).resolve().parents[2]
    config_path = backend_root / "alembic.ini"
    cfg = Config(str(config_path))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    return cfg


async def run_startup_migrations() -> None:
    cfg = _alembic_config()
    await asyncio.to_thread(command.upgrade, cfg, "head")

