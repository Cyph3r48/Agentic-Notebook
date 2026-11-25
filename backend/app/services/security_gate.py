"""Puts the SMC layers on the request path.

- Layer 1 (PI Guard) and layer 3 (Resolver) screen text that is about to reach the model: retrieved chunks are
  checked against their stored hash and scanned for injection; a chunk that fails is withheld, never shown.
- Layer 4 (tool whitelist) gates the memory search. No model-callable tools exist yet; the agent loop must send
  every tool through `check_tool`.
- Layer 5 (audit) records what was refused, with metadata only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from fastapi import Request

from app.services import audit
from app.services.memory import MemoryChunk
from app.services.smc_service import SMCService


@dataclass
class Quarantined:
    document_id: str
    chunk_index: int
    reason: str  # "integrity" or "prompt_injection"
    patterns: list[str] = field(default_factory=list)


@dataclass
class ScreenResult:
    kept: list[MemoryChunk]
    quarantined: list[Quarantined]


class SecurityGate:
    @staticmethod
    def screen_chunks(chunks: list[MemoryChunk]) -> ScreenResult:
        """Layer 3 then layer 1 on every retrieved chunk. Pure: no I/O."""
        kept: list[MemoryChunk] = []
        quarantined: list[Quarantined] = []
        for chunk in chunks:
            if not SMCService.hash_matches(chunk.content, chunk.content_hash):
                quarantined.append(Quarantined(chunk.document_id, chunk.chunk_index, "integrity"))
                continue
            scan = SMCService.scan_text(chunk.content)
            if scan.flagged:
                quarantined.append(Quarantined(chunk.document_id, chunk.chunk_index, "prompt_injection", scan.patterns))
                continue
            kept.append(chunk)
        return ScreenResult(kept, quarantined)

    @staticmethod
    def screen_message(text: str):
        """Layer 1 on the user's own message."""
        return SMCService.scan_text(text)

    @staticmethod
    async def check_tool(tool: str, role: str, user_id: UUID | None, request: Request | None = None) -> bool:
        """Layer 4. A refusal is audited."""
        allowed = await SMCService.check_tool_permission(tool, role)
        if not allowed:
            await audit.record(
                request, "tool_denied", user_id=user_id, details={"tool": tool, "role": role},
                flagged=True, flag_reason="TOOL_WHITELIST refused the tool", layer="TOOL_WHITELIST",
            )
        return allowed

    @staticmethod
    async def audit_quarantine(request: Request | None, user_id: UUID | None, result: ScreenResult) -> None:
        """One flagged audit row per withheld chunk: which chunk and why, never its text."""
        for item in result.quarantined:
            layer = "RESOLVER" if item.reason == "integrity" else "PI_GUARD"
            await audit.record(
                request,
                "chunk_quarantined",
                user_id=user_id,
                resource_type="document",
                resource_id=_as_uuid(item.document_id),
                details={"chunk_index": item.chunk_index, "reason": item.reason, "patterns": item.patterns},
                flagged=True,
                flag_reason=f"{layer} withheld a retrieved chunk",
                layer=layer,
            )

    @staticmethod
    async def audit_user_message(request: Request | None, user_id: UUID | None, scan: Any, blocked: bool) -> None:
        await audit.record(
            request,
            "pi_guard_user_message",
            user_id=user_id,
            details={"patterns": scan.patterns, "risk_score": scan.risk_score, "blocked": blocked},
            flagged=True,
            flag_reason="PI_GUARD flagged the user's message",
            layer="PI_GUARD",
        )


def _as_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except (TypeError, ValueError):
        return None
