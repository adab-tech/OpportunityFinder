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


class LockedOutError(Exception):
    """Raised when `key` is currently locked out after too many failures."""


class LoginAttemptLimiter:
    """Locks a key out after too many failed attempts in a row.

    Keyed by the submitted email rather than caller IP: this app has
    exactly one valid admin account (single-admin by design — see
    routes/admin_auth.py), so locking out repeated failures against
    that one email directly protects the real target regardless of how
    many source IPs an attacker spreads requests across. A wrong email
    can never succeed anyway, so tracking those separately costs
    nothing.
    """

    def __init__(self, max_attempts: int, window_seconds: float, lockout_seconds: float):
        self._max_attempts = max_attempts
        self._window = window_seconds
        self._lockout = lockout_seconds
        self._lock = threading.Lock()
        self._failures: dict[str, tuple[int, float]] = {}  # key -> (count, first_failure_at)
        self._locked_until: dict[str, float] = {}

    def check(self, key: str) -> None:
        """Raise LockedOutError if `key` is currently locked out."""
        now = time.monotonic()
        with self._lock:
            locked_until = self._locked_until.get(key)
            if locked_until is not None and now < locked_until:
                raise LockedOutError()

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            count, first_failure_at = self._failures.get(key, (0, now))
            if now - first_failure_at > self._window:
                count, first_failure_at = 0, now
            count += 1
            if count >= self._max_attempts:
                self._locked_until[key] = now + self._lockout
                self._failures.pop(key, None)
            else:
                self._failures[key] = (count, first_failure_at)

    def record_success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)

    def seconds_remaining(self, key: str) -> int:
        with self._lock:
            locked_until = self._locked_until.get(key)
        if locked_until is None:
            return 0
        return max(0, int(locked_until - time.monotonic()))
