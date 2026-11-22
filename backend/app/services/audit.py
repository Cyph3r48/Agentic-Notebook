"""Request-aware audit trail (layer 5).

Details must be metadata: sizes, ids, flags. As a second line of defence, keys that usually hold secrets or
user text are dropped before anything is written, so a careless call cannot put a password or a message in the log.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from fastapi import Request

from app.services.smc_service import SMCService

# Never written to the audit trail, whatever the caller passes.
_FORBIDDEN_KEYS = {
    "password", "current_password", "new_password", "api_key", "key", "token", "access_token", "refresh_token",
    "secret", "authorization", "content", "message", "text", "prompt", "snippet",
}


def scrub(details: dict[str, Any] | None) -> dict[str, Any] | None:
    if details is None:
        return None
    clean: dict[str, Any] = {}
    for name, value in details.items():
        if str(name).lower() in _FORBIDDEN_KEYS:
            continue
        clean[name] = scrub(value) if isinstance(value, dict) else value
    return clean


def request_context(request: Request | None) -> dict[str, Any]:
    """The request id, address and user agent for an audit row."""
    if request is None:
        return {}
    raw_id = getattr(getattr(request, "state", None), "request_id", None)
    try:
        request_id = UUID(str(raw_id)) if raw_id else uuid4()
    except ValueError:
        request_id = uuid4()
    client = request.client.host if request.client else None
    return {
        "request_id": request_id,
        "ip_address": client,
        "user_agent": request.headers.get("user-agent"),
    }


async def record(
    request: Request | None,
    action: str,
    *,
    user_id: UUID | None = None,
    resource_type: str | None = None,
    resource_id: UUID | None = None,
    details: dict[str, Any] | None = None,
    status_code: int | None = None,
    error: str | None = None,
    flagged: bool = False,
    flag_reason: str | None = None,
    layer: str = "AUDIT",
) -> None:
    """Write one audit row. Never raises."""
    await SMCService.audit_log(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_body=scrub(details),
        response_status=status_code,
        error_message=error,
        flagged=flagged,
        flag_reason=flag_reason,
        security_layer=layer,
        **request_context(request),
    )
