"""
Application-level exceptions and response schema helpers.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class AppError(Exception):
    message: str
    status_code: int = 400
    error: str = "Bad Request"
    details: dict[str, Any] | None = None


def error_payload(
    *,
    error: str,
    message: str,
    request_id: str | None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": error,
        "message": message,
        "request_id": request_id,
    }
    if details:
        payload["details"] = details
    return payload
