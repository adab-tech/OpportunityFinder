"""Minimal in-process cooldown limiter — no Redis or other external
dependency, consistent with this project's smallest-tool-that-works
philosophy (see the stdlib-only session auth in app/security.py).

Single-process deployment (see render.yaml — one web service, no
horizontal scaling), so an in-memory dict is sufficient here; it would
need to move to a shared store if this ever runs behind multiple
worker processes or replicas.
"""

from __future__ import annotations

import threading
import time


class RateLimitedError(Exception):
    """Raised when `key` was already allowed within its cooldown window."""


class CooldownLimiter:
    """Rejects a second call for the same key within `seconds` of the
    first allowed call. Used to stop a single email address from being
    used to trigger unlimited notification emails (see
    app/services/subscribers.py) — this app has no login, so email
    address is the only identity a caller controls, and every
    save/alert action currently sends mail to it with no other limit.
    """

    def __init__(self, seconds: float):
        self._seconds = seconds
        self._last_seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        """Raise RateLimitedError if `key` is still within its cooldown
        window; otherwise record this call as the new last-seen time.
        """
        now = time.monotonic()
        with self._lock:
            last = self._last_seen.get(key)
            if last is not None and now - last < self._seconds:
                raise RateLimitedError()
            self._last_seen[key] = now
