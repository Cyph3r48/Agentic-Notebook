"""Re-index: embed every stored document chunk again with the active embedding model.

Chunks are already in Postgres, so a model change costs embedding time, not re-reading or re-sanitizing files.
Progress lives in the database (`system_settings["reindex"]`) so it survives a page reload and can be shown in
Settings. One job runs at a time; a job that has not reported progress for `STALE_AFTER_SECONDS` is treated as dead
and may be restarted. The job runs inside the API process, which is fine for one worker; with several workers it
should move to a task queue.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from loguru import logger

STATE_KEY = "reindex"
STALE_AFTER_SECONDS = 300
BATCH_SIZE = 50
# A systemic problem (the embedding service is down, the key was revoked) fails every document; stop early.
MAX_CONSECUTIVE_FAILURES = 3


class ReindexAlreadyRunning(Exception):
    """A re-index is already in progress."""


class ReindexNotPossible(Exception):
    """Re-indexing cannot start. The message is safe to show."""


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def _idle() -> dict[str, Any]:
    return {
        "state": "idle", "total": 0, "done": 0, "failed": 0,
        "started_at": None, "updated_at": None, "finished_at": None, "error": None,
    }


class ReindexService:
    def __init__(self, settings_repo, document_repo, memory, *, now: Callable[[], datetime] | None = None):
        self.settings_repo = settings_repo
        self.document_repo = document_repo
        self.memory = memory
        self._now = now or (lambda: datetime.now(tz=timezone.utc))

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    async def status(self) -> dict[str, Any]:
        row = await self.settings_repo.get(STATE_KEY)
        state = {**_idle(), **(row.value if row else {})}
        if state["state"] == "running" and self._is_stale(state):
            state["state"] = "stalled"  # reported, not rewritten: a new start may take over
        return state

    def _is_stale(self, state: dict[str, Any]) -> bool:
        updated = state.get("updated_at")
        if not updated:
            return True
        return self._now() - datetime.fromisoformat(updated) > timedelta(seconds=STALE_AFTER_SECONDS)

    async def _save(self, state: dict[str, Any]) -> None:
        state["updated_at"] = _iso(self._now())
        await self.settings_repo.put_value(STATE_KEY, state)

    # ------------------------------------------------------------------
    # Start and run
    # ------------------------------------------------------------------

    async def start(self) -> dict[str, Any]:
        """Record that a job is starting. The work itself is `run()`, normally in a background task."""
        from app.core.config import settings

        if not settings.VECTOR_INDEXING_ENABLED:
            raise ReindexNotPossible("Vector indexing is off (VECTOR_INDEXING_ENABLED=false), so there is nothing to index into")
        current = await self.status()
        if current["state"] == "running":
            raise ReindexAlreadyRunning("A re-index is already running")

        total = await self.document_repo.count_completed()
        started = self._now()
        state = {**_idle(), "state": "running" if total else "done", "total": total, "started_at": _iso(started)}
        if not total:
            state["finished_at"] = _iso(started)
        await self._save(state)
        return state

    async def run(self) -> dict[str, Any]:
        """Embed every completed document's chunks into the active index, updating progress as it goes."""
        state = await self.status()
        if state["state"] != "running":
            return state
        consecutive = 0
        after = None
        try:
            while True:
                ids = await self.document_repo.completed_ids_after(after, BATCH_SIZE)
                if not ids:
                    break
                for document_id in ids:
                    after = document_id
                    await self._save(state)  # heartbeat: one large document can take a while
                    error = await self._index_document(document_id)
                    if error is None:
                        consecutive = 0
                        state["done"] += 1
                    else:
                        consecutive += 1
                        state["failed"] += 1
                        state["error"] = state["error"] or error
                    await self._save(state)
                    if consecutive >= MAX_CONSECUTIVE_FAILURES:
                        state.update(state="failed", finished_at=_iso(self._now()))
                        await self._save(state)
                        logger.warning("Re-index stopped after {n} failures in a row: {error}", n=consecutive, error=state["error"])
                        return state
        except Exception as exc:
            # Anything unexpected must not leave the job "running" forever.
            state.update(state="failed", finished_at=_iso(self._now()), error=state["error"] or f"Unexpected error ({type(exc).__name__})")
            await self._save(state)
            logger.exception("Re-index crashed")
            return state

        # A job where nothing worked is a failure, not a finished job.
        everything_failed = state["failed"] > 0 and state["done"] == 0
        state.update(state="failed" if everything_failed else "done", finished_at=_iso(self._now()))
        await self._save(state)
        logger.info("Re-index finished done={done} failed={failed}", done=state["done"], failed=state["failed"])
        return state

    async def _index_document(self, document_id) -> str | None:
        """Index one document. Returns None on success, else a safe error message."""
        document = await self.document_repo.get_by_id(document_id)
        if document is None or document.status != "completed":
            return None
        chunks = await self.document_repo.chunks_for_document(document_id)
        if not chunks:
            return None
        outcome = await self.memory.ingest(
            user_id=document.user_id,
            document_id=document.id,
            original_filename=document.original_filename,
            chunks=[
                {
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "content_hash": chunk.content_hash,
                    "metadata_json": chunk.metadata_json or {},
                }
                for chunk in chunks
            ],
        )
        if outcome.vector_indexed is not True:
            return outcome.error or "Vector indexing is off"
        metadata = {k: v for k, v in (document.metadata_json or {}).items() if k != "vector_index_error"}
        metadata.update(vector_indexed=True, vector_index=outcome.index)
        await self.document_repo.update_document(document, metadata_json=metadata)
        return None


async def run_reindex_in_background() -> None:
    """Entry point for a FastAPI background task: builds its own database session."""
    from app.core.database import SessionLocal
    from app.repositories import DocumentRepository, SystemSettingsRepository
    from app.services.memory.registry import get_memory_provider

    async with SessionLocal() as session:
        service = ReindexService(SystemSettingsRepository(session), DocumentRepository(session), get_memory_provider(session))
        await service.run()
