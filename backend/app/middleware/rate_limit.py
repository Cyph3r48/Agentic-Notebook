"""
Simple in-process rate limiting middleware.
"""

from collections import defaultdict, deque
from time import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        now = time()
        window_start = now - 60

        ip_requests = self._requests[client_ip]
        while ip_requests and ip_requests[0] < window_start:
            ip_requests.popleft()

        if len(ip_requests) >= settings.RATE_LIMIT_PER_MINUTE:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too many requests",
                    "message": "Rate limit exceeded. Try again shortly.",
                    "request_id": getattr(request.state, "request_id", None),
                },
            )

        ip_requests.append(now)
        return await call_next(request)
