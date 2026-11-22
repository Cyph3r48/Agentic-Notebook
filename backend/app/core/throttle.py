"""Lock a key for a while after too many failures (sign-in, current-password checks).

In memory, so it covers one worker; with several workers each keeps its own count. The limits come from settings
(`LOGIN_MAX_FAILURES`, `LOGIN_LOCK_SECONDS`) and are read on every call.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Callable

from app.core.config import settings


class FailureThrottle:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._locked_until: dict[str, float] = {}

    def locked_for(self, key: str) -> int:
        """Seconds left on a lock (rounded up), or 0 when the key is free."""
        until = self._locked_until.get(key)
        if until is None:
            return 0
        remaining = until - self._clock()
        if remaining <= 0:
            self._locked_until.pop(key, None)
            self._failures.pop(key, None)
            return 0
        return int(remaining) + 1

    def record_failure(self, key: str) -> bool:
        """Count a failure. Returns True when this one locked the key."""
        now = self._clock()
        window = settings.LOGIN_LOCK_SECONDS
        failures = self._failures[key]
        while failures and failures[0] < now - window:
            failures.popleft()
        failures.append(now)
        if len(failures) >= settings.LOGIN_MAX_FAILURES:
            self._locked_until[key] = now + window
            failures.clear()
            return True
        return False

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
        self._locked_until.pop(key, None)


login_throttle = FailureThrottle()
password_throttle = FailureThrottle()
