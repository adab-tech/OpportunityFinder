"""DB-backed cooldown/lockout limiters — no Redis or other external
dependency, consistent with this project's smallest-tool-that-works
philosophy (see the stdlib-only session auth in app/security.py).

State lives in the `rate_limit_cooldowns` / `rate_limit_lockouts` tables
(app/models.py) rather than a process-local dict. It used to be an
in-memory dict, which was fine for throughput (this app runs as a single
instance — see render.yaml's one `web` service) but wrong for
durability: a plain Python dict resets to empty on every process
restart (a deploy, a crash, Render's free-tier idle-then-wake cycle),
so a login lockout or an email-spam cooldown could be trivially bypassed
just by waiting for, or triggering, a restart. Persisting to the same
database the rest of the app already uses (SQLite locally, Postgres in
production) fixes that, and as a side effect would also be correct if
this ever ran as multiple instances sharing one DB.

Concurrency: every write here is a compare-and-swap against a `version`
column rather than a plain read-then-write, because a naive read/modify/
write from two concurrent requests has exactly the same "two logins both
read not-locked-out before either records a failure" race that the
in-memory dict had (a bare dict mutation is not atomic across requests
either, but this matters more once it's a fresh read+write per request
instead of one shared process-wide object). Each write is attempted as
an UPDATE ... WHERE id = :id AND version = :expected_version; a
concurrent writer that got there first changes the row's version, so a
stale writer's UPDATE matches zero rows and is told to retry against a
fresh read. The very first row for a given key is created with a plain
INSERT guarded by a UNIQUE(namespace, key) constraint — a concurrent
double-insert raises IntegrityError on the loser, which then falls
through to the same compare-and-swap path against the row the winner
just created. Neither SQLite nor Postgres needs any dialect-specific
feature for this (no SELECT ... FOR UPDATE, no INSERT ... ON CONFLICT) —
just a unique constraint and a conditional UPDATE, both portable.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import RateLimitCooldown, RateLimitLockout

# Bounded retry count for the compare-and-swap loops below. A retry only
# happens when a genuinely concurrent request updates the same row
# between our read and our write; real contention converges in one or
# two retries. This bound exists purely so a bug can never spin forever.
_MAX_CAS_RETRIES = 10


def _aware(dt: datetime) -> datetime:
    """SQLite has no native timezone-aware datetime type — a value
    written as aware UTC can come back naive on some driver/version
    combinations. Treat a naive value as UTC (the only timezone this
    module ever writes) rather than let a naive/aware comparison raise.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


class RateLimitedError(Exception):
    """Raised when `key` was already allowed within its cooldown window."""


class CooldownLimiter:
    """Rejects a second call for the same key within `seconds` of the
    first allowed call. Used to stop a single email address from being
    used to trigger unlimited notification emails (see
    app/services/subscribers.py) — this app has no login, so email
    address is the only identity a caller controls, and every
    save/alert action currently sends mail to it with no other limit.
    Also used for the global "Find new" scrape-trigger cooldown (see
    app/routes/scraper.py).
    """

    def __init__(
        self,
        seconds: float,
        *,
        namespace: str,
        session_factory: Callable[[], Session] = SessionLocal,
    ):
        self._seconds = seconds
        self._namespace = namespace
        self._session_factory = session_factory

    def _get_row(self, db: Session, key: str) -> RateLimitCooldown | None:
        return (
            db.query(RateLimitCooldown)
            .filter(RateLimitCooldown.namespace == self._namespace, RateLimitCooldown.key == key)
            .one_or_none()
        )

    def check(self, key: str) -> None:
        """Raise RateLimitedError if `key` is still within its cooldown
        window; otherwise record this call as the new last-seen time.
        """
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=self._seconds)
        db = self._session_factory()
        try:
            for _ in range(_MAX_CAS_RETRIES):
                row = self._get_row(db, key)

                if row is None:
                    # Never seen before: always allowed. Insert guarded by
                    # UNIQUE(namespace, key) — a concurrent first call for
                    # the same key can only let one INSERT through.
                    db.add(RateLimitCooldown(namespace=self._namespace, key=key, last_seen_at=now, version=0))
                    try:
                        db.commit()
                        return
                    except IntegrityError:
                        db.rollback()
                        continue  # lost the insert race; row exists now, retry as an update

                if _aware(row.last_seen_at) > cutoff:
                    raise RateLimitedError()

                updated = (
                    db.query(RateLimitCooldown)
                    .filter(RateLimitCooldown.id == row.id, RateLimitCooldown.version == row.version)
                    .update({"last_seen_at": now, "version": row.version + 1}, synchronize_session=False)
                )
                db.commit()
                if updated:
                    return
                # else: a concurrent call updated this row between our read
                # and our write (version no longer matches) — retry fresh.

            raise RuntimeError(
                f"CooldownLimiter: exceeded {_MAX_CAS_RETRIES} retries under contention for key={key!r}"
            )
        finally:
            db.close()

    def seconds_remaining(self, key: str) -> int:
        """How many seconds until `key` would be allowed again. 0 if it
        is allowed right now (or has never been seen).
        """
        db = self._session_factory()
        try:
            row = self._get_row(db, key)
        finally:
            db.close()
        if row is None:
            return 0
        elapsed = (datetime.now(UTC) - _aware(row.last_seen_at)).total_seconds()
        return max(0, int(self._seconds - elapsed))


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

    def __init__(
        self,
        max_attempts: int,
        window_seconds: float,
        lockout_seconds: float,
        *,
        namespace: str = "login_attempt",
        session_factory: Callable[[], Session] = SessionLocal,
    ):
        self._max_attempts = max_attempts
        self._window = window_seconds
        self._lockout = lockout_seconds
        self._namespace = namespace
        self._session_factory = session_factory

    def _get_row(self, db: Session, key: str) -> RateLimitLockout | None:
        return (
            db.query(RateLimitLockout)
            .filter(RateLimitLockout.namespace == self._namespace, RateLimitLockout.key == key)
            .one_or_none()
        )

    def check(self, key: str) -> None:
        """Raise LockedOutError if `key` is currently locked out."""
        db = self._session_factory()
        try:
            row = self._get_row(db, key)
        finally:
            db.close()
        if row is not None and row.locked_until is not None and _aware(row.locked_until) > datetime.now(UTC):
            raise LockedOutError()

    def record_failure(self, key: str) -> None:
        now = datetime.now(UTC)
        db = self._session_factory()
        try:
            for _ in range(_MAX_CAS_RETRIES):
                row = self._get_row(db, key)

                if row is None:
                    db.add(
                        RateLimitLockout(
                            namespace=self._namespace,
                            key=key,
                            failure_count=1,
                            first_failure_at=now,
                            locked_until=None,
                            version=0,
                        )
                    )
                    try:
                        db.commit()
                        return
                    except IntegrityError:
                        db.rollback()
                        continue  # lost the insert race; row exists now, retry as an update

                count = row.failure_count
                first_failure_at = row.first_failure_at
                if first_failure_at is None:
                    count, first_failure_at = 0, now
                elif (now - _aware(first_failure_at)).total_seconds() > self._window:
                    count, first_failure_at = 0, now
                count += 1

                values: dict = {"version": row.version + 1}
                if count >= self._max_attempts:
                    values["locked_until"] = now + timedelta(seconds=self._lockout)
                    values["failure_count"] = 0
                    values["first_failure_at"] = None
                else:
                    values["failure_count"] = count
                    values["first_failure_at"] = first_failure_at

                updated = (
                    db.query(RateLimitLockout)
                    .filter(RateLimitLockout.id == row.id, RateLimitLockout.version == row.version)
                    .update(values, synchronize_session=False)
                )
                db.commit()
                if updated:
                    return

            raise RuntimeError(
                f"LoginAttemptLimiter: exceeded {_MAX_CAS_RETRIES} retries under contention for key={key!r}"
            )
        finally:
            db.close()

    def record_success(self, key: str) -> None:
        db = self._session_factory()
        try:
            db.query(RateLimitLockout).filter(
                RateLimitLockout.namespace == self._namespace, RateLimitLockout.key == key
            ).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()

    def seconds_remaining(self, key: str) -> int:
        db = self._session_factory()
        try:
            row = self._get_row(db, key)
        finally:
            db.close()
        if row is None or row.locked_until is None:
            return 0
        return max(0, int((_aware(row.locked_until) - datetime.now(UTC)).total_seconds()))
