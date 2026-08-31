"""Regression tests for the admin email/password login system
(app/security.py, app/routes/admin_auth.py) — replaces the old shared
X-Admin-Key header with a real account and a signed session cookie.
"""

import base64
import hashlib
import hmac as hmac_module
import struct
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import RateLimitLockout
from app.security import (
    create_session_token,
    generate_totp_secret,
    hash_password,
    totp_provisioning_uri,
    verify_password,
    verify_session_token,
    verify_totp_code,
)
from app.services.rate_limit import LockedOutError, LoginAttemptLimiter

client = TestClient(app)


def _clear_login_lockout_state():
    """Lockout state now lives in the DB (RateLimitLockout), not a
    process-local dict — clear it directly so one test's lockout never
    bleeds into the next. Safe to wipe the whole table: this runs
    against the throwaway per-test-session SQLite file (see
    tests/conftest.py), never the real dev/prod database.
    """
    db = SessionLocal()
    try:
        db.query(RateLimitLockout).delete()
        db.commit()
    finally:
        db.close()


def _totp_code(secret_b32: str, at: float, digits: int = 6) -> str:
    """Recreates RFC 6238 TOTP (HMAC-SHA1, dynamic truncation) from
    scratch, independently of app/security.py's implementation, so these
    tests actually confirm the production code against the spec rather
    than just asserting it agrees with itself.
    """
    key = base64.b32decode(secret_b32.upper())
    counter = int(at) // 30
    digest = hmac_module.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF
    return str(truncated % (10**digits)).zfill(digits)


class TestPasswordHashing:
    def test_correct_password_verifies(self):
        hashed = hash_password("correct horse battery staple")
        assert verify_password("correct horse battery staple", hashed) is True

    def test_wrong_password_fails(self):
        hashed = hash_password("correct horse battery staple")
        assert verify_password("wrong password", hashed) is False

    def test_hash_is_salted_differently_each_time(self):
        a = hash_password("same password")
        b = hash_password("same password")
        assert a != b
        assert verify_password("same password", a) is True
        assert verify_password("same password", b) is True

    def test_malformed_hash_fails_closed(self):
        assert verify_password("anything", "not-a-real-hash") is False


class TestSessionTokens:
    def test_valid_token_verifies(self):
        token = create_session_token("secret-key")
        assert verify_session_token(token, "secret-key") is True

    def test_wrong_secret_fails(self):
        token = create_session_token("secret-key")
        assert verify_session_token(token, "different-key") is False

    def test_malformed_token_fails_closed(self):
        assert verify_session_token("not-a-real-token", "secret-key") is False
        assert verify_session_token(None, "secret-key") is False
        assert verify_session_token("", "secret-key") is False

    def test_expired_token_fails(self):
        # A token signed for a timestamp in the past must not verify —
        # simulate by signing an already-expired expiry directly.
        import hashlib
        import hmac

        expired_expiry = "1000000000"  # September 2001, long expired
        signature = hmac.new(b"secret-key", expired_expiry.encode(), hashlib.sha256).hexdigest()
        token = f"{expired_expiry}.{signature}"
        assert verify_session_token(token, "secret-key") is False


class TestTotpVerification:
    """RFC 6238 TOTP second factor (app/security.py). The seed is the RFC
    6238 Appendix B SHA1 test-vector seed (the ASCII string
    "12345678901234567890"), base32-encoded since that's the format this
    codebase's TOTP functions take (the standard authenticator-app
    format) rather than raw bytes.
    """

    RFC_SECRET_B32 = base64.b32encode(b"12345678901234567890").decode()

    def test_matches_rfc_6238_test_vector_at_t59(self):
        # RFC 6238 Appendix B: T=59s -> counter 1 -> 8-digit HOTP
        # 94287082. This implementation truncates to 6 digits, which
        # RFC 6238's truncation function makes the same value mod 10**6:
        # 287082 (independently confirmed via _totp_code above).
        assert verify_totp_code("287082", self.RFC_SECRET_B32, at=59) is True

    def test_matches_rfc_6238_test_vector_at_t1111111109(self):
        # T=1111111109 -> 8-digit 07081804 -> 6-digit 081804.
        assert verify_totp_code("081804", self.RFC_SECRET_B32, at=1111111109) is True

    def test_wrong_code_is_rejected(self):
        assert verify_totp_code("000000", self.RFC_SECRET_B32, at=59) is False

    def test_code_from_adjacent_step_is_accepted_for_clock_drift(self):
        secret = generate_totp_secret()
        at = 1_700_000_000.0
        code_one_step_earlier = _totp_code(secret, at - 30)
        code_one_step_later = _totp_code(secret, at + 30)
        assert verify_totp_code(code_one_step_earlier, secret, at=at) is True
        assert verify_totp_code(code_one_step_later, secret, at=at) is True

    def test_code_two_steps_away_is_rejected(self):
        secret = generate_totp_secret()
        at = 1_700_000_000.0
        code_two_steps_earlier = _totp_code(secret, at - 60)
        assert verify_totp_code(code_two_steps_earlier, secret, at=at) is False

    def test_current_code_round_trips_for_a_freshly_generated_secret(self):
        secret = generate_totp_secret()
        at = 1_700_000_000.0
        assert verify_totp_code(_totp_code(secret, at), secret, at=at) is True

    def test_malformed_code_fails_closed(self):
        assert verify_totp_code(None, self.RFC_SECRET_B32, at=59) is False
        assert verify_totp_code("", self.RFC_SECRET_B32, at=59) is False
        assert verify_totp_code("12345", self.RFC_SECRET_B32, at=59) is False  # 5 digits
        assert verify_totp_code("abcdef", self.RFC_SECRET_B32, at=59) is False  # not digits

    def test_malformed_secret_fails_closed(self):
        assert verify_totp_code("287082", "not valid base32!!", at=59) is False

    def test_generated_secret_is_valid_base32_of_the_expected_length(self):
        secret = generate_totp_secret()
        decoded = base64.b32decode(secret)  # raises if not valid base32
        assert len(decoded) == 20

    def test_provisioning_uri_carries_the_secret_and_account(self):
        secret = generate_totp_secret()
        uri = totp_provisioning_uri(secret, "admin@example.org")
        assert uri.startswith("otpauth://totp/")
        assert f"secret={secret}" in uri
        assert "admin%40example.org" in uri  # URL-encoded @


class TestLoginEndpoint:
    def setup_method(self):
        from app.config import settings

        self._prior = (settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD_HASH, settings.SESSION_SECRET_KEY)
        _clear_login_lockout_state()

    def teardown_method(self):
        from app.config import settings

        settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD_HASH, settings.SESSION_SECRET_KEY = self._prior

    def _configure(self, monkeypatch, email="admin@example.org", password="a-strong-password-123"):
        from app.config import settings

        monkeypatch.setattr(settings, "ADMIN_EMAIL", email)
        monkeypatch.setattr(settings, "ADMIN_PASSWORD_HASH", hash_password(password))
        monkeypatch.setattr(settings, "SESSION_SECRET_KEY", "test-secret")

    def test_login_fails_when_unconfigured(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "ADMIN_EMAIL", None)
        response = client.post(
            "/api/v1/admin/login", json={"email": "a@b.com", "password": "whatever"}
        )
        assert response.status_code == 503

    def test_login_succeeds_and_sets_cookie(self, monkeypatch):
        self._configure(monkeypatch)
        response = client.post(
            "/api/v1/admin/login",
            json={"email": "admin@example.org", "password": "a-strong-password-123"},
        )
        assert response.status_code == 200
        assert "of_admin_session" in response.cookies

    def test_login_rejects_wrong_password(self, monkeypatch):
        self._configure(monkeypatch)
        response = client.post(
            "/api/v1/admin/login",
            json={"email": "admin@example.org", "password": "wrong-password"},
        )
        assert response.status_code == 401

    def test_login_rejects_wrong_email(self, monkeypatch):
        self._configure(monkeypatch)
        response = client.post(
            "/api/v1/admin/login",
            json={"email": "not-the-admin@example.org", "password": "a-strong-password-123"},
        )
        assert response.status_code == 401

    def test_login_email_check_is_case_insensitive(self, monkeypatch):
        self._configure(monkeypatch)
        response = client.post(
            "/api/v1/admin/login",
            json={"email": "ADMIN@EXAMPLE.ORG", "password": "a-strong-password-123"},
        )
        assert response.status_code == 200

    def test_login_unaffected_when_totp_secret_unset(self, monkeypatch):
        # ADMIN_TOTP_SECRET unset (the default, and explicitly so here)
        # must behave exactly like before this feature existed: no code
        # required, and a stray one submitted anyway is simply ignored.
        self._configure(monkeypatch)
        monkeypatch.setattr("app.config.settings.ADMIN_TOTP_SECRET", None)
        response = client.post(
            "/api/v1/admin/login",
            json={"email": "admin@example.org", "password": "a-strong-password-123", "totp_code": "000000"},
        )
        assert response.status_code == 200


class TestLoginMethodsEndpoint:
    def test_reports_totp_not_required_by_default(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "ADMIN_TOTP_SECRET", None)
        response = client.get("/api/v1/admin/login-methods")
        assert response.status_code == 200
        assert response.json() == {"totp_required": False}

    def test_reports_totp_required_when_secret_configured(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "ADMIN_TOTP_SECRET", generate_totp_secret())
        response = client.get("/api/v1/admin/login-methods")
        assert response.status_code == 200
        assert response.json() == {"totp_required": True}


class TestLoginWithTotp:
    """Login endpoint behavior once ADMIN_TOTP_SECRET is configured (see
    TestLoginEndpoint above for the unconfigured, password-only case).
    """

    def setup_method(self):
        from app.routes import admin_auth

        _clear_login_lockout_state()
        admin_auth._last_used_totp_code = None

    def teardown_method(self):
        from app.routes import admin_auth

        admin_auth._last_used_totp_code = None

    def _configure(self, monkeypatch, email="admin@example.org", password="a-strong-password-123"):
        from app.config import settings

        secret = generate_totp_secret()
        monkeypatch.setattr(settings, "ADMIN_EMAIL", email)
        monkeypatch.setattr(settings, "ADMIN_PASSWORD_HASH", hash_password(password))
        monkeypatch.setattr(settings, "SESSION_SECRET_KEY", "test-secret")
        monkeypatch.setattr(settings, "ADMIN_TOTP_SECRET", secret)
        return secret

    def test_login_fails_without_a_code(self, monkeypatch):
        self._configure(monkeypatch)
        response = client.post(
            "/api/v1/admin/login",
            json={"email": "admin@example.org", "password": "a-strong-password-123"},
        )
        assert response.status_code == 401

    def test_login_fails_with_a_wrong_code(self, monkeypatch):
        secret = self._configure(monkeypatch)
        # A code computed for a fixed timestamp far in the past (well
        # outside the ±1-step drift window around the real "now" the
        # server checks against) is guaranteed wrong.
        stale_code = _totp_code(secret, at=1_700_000_000.0)
        response = client.post(
            "/api/v1/admin/login",
            json={"email": "admin@example.org", "password": "a-strong-password-123", "totp_code": stale_code},
        )
        assert response.status_code == 401

    def test_login_succeeds_with_the_correct_code(self, monkeypatch):
        import time

        secret = self._configure(monkeypatch)
        code = _totp_code(secret, at=time.time())
        response = client.post(
            "/api/v1/admin/login",
            json={"email": "admin@example.org", "password": "a-strong-password-123", "totp_code": code},
        )
        assert response.status_code == 200
        assert "of_admin_session" in response.cookies

    def test_correct_password_with_wrong_code_does_not_leak_which_field_was_wrong(self, monkeypatch):
        # The error message must be identical (and generic) whether the
        # password or the code was wrong, so a correct-password guess
        # can't be confirmed via a different error message.
        self._configure(monkeypatch)
        wrong_password_resp = client.post(
            "/api/v1/admin/login",
            json={"email": "admin@example.org", "password": "wrong", "totp_code": "000000"},
        )
        wrong_code_resp = client.post(
            "/api/v1/admin/login",
            json={"email": "admin@example.org", "password": "a-strong-password-123", "totp_code": "000000"},
        )
        assert wrong_password_resp.status_code == wrong_code_resp.status_code == 401
        assert wrong_password_resp.json()["detail"] == wrong_code_resp.json()["detail"]

    def test_replaying_the_same_successful_code_is_rejected(self, monkeypatch):
        import time

        secret = self._configure(monkeypatch)
        code = _totp_code(secret, at=time.time())
        first = client.post(
            "/api/v1/admin/login",
            json={"email": "admin@example.org", "password": "a-strong-password-123", "totp_code": code},
        )
        assert first.status_code == 200

        second = client.post(
            "/api/v1/admin/login",
            json={"email": "admin@example.org", "password": "a-strong-password-123", "totp_code": code},
        )
        assert second.status_code == 401


class TestLoginLockout:
    """No lockout existed before this — an attacker could brute-force
    the single admin password with unlimited attempts. See
    app/services/rate_limit.py::LoginAttemptLimiter.
    """

    def setup_method(self):
        from app.config import settings
        from app.routes import admin_auth

        self.admin_auth = admin_auth
        self._prior = (settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD_HASH, settings.SESSION_SECRET_KEY)
        _clear_login_lockout_state()
        settings.ADMIN_EMAIL = "lockout-test@example.org"
        settings.ADMIN_PASSWORD_HASH = self._hash("a-strong-password-123")
        settings.SESSION_SECRET_KEY = "test-secret"

    def teardown_method(self):
        from app.config import settings

        settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD_HASH, settings.SESSION_SECRET_KEY = self._prior
        _clear_login_lockout_state()

    @staticmethod
    def _hash(password: str) -> str:
        from app.security import hash_password

        return hash_password(password)

    def _bad_login(self):
        return client.post(
            "/api/v1/admin/login",
            json={"email": "lockout-test@example.org", "password": "wrong-password"},
        )

    def test_locks_out_after_max_attempts(self):
        for _ in range(self.admin_auth._LOGIN_MAX_ATTEMPTS):
            response = self._bad_login()
            assert response.status_code == 401
        # One more, still within the window, now locked out.
        locked = self._bad_login()
        assert locked.status_code == 429

    def test_locked_out_rejects_even_the_correct_password(self):
        for _ in range(self.admin_auth._LOGIN_MAX_ATTEMPTS):
            self._bad_login()
        response = client.post(
            "/api/v1/admin/login",
            json={"email": "lockout-test@example.org", "password": "a-strong-password-123"},
        )
        assert response.status_code == 429

    def test_successful_login_resets_the_failure_count(self):
        for _ in range(self.admin_auth._LOGIN_MAX_ATTEMPTS - 1):
            self._bad_login()
        success = client.post(
            "/api/v1/admin/login",
            json={"email": "lockout-test@example.org", "password": "a-strong-password-123"},
        )
        assert success.status_code == 200
        # Failure count should be cleared, not still one shy of lockout.
        response = self._bad_login()
        assert response.status_code == 401

    def test_different_email_is_not_affected_by_another_lockout(self):
        for _ in range(self.admin_auth._LOGIN_MAX_ATTEMPTS):
            self._bad_login()
        # A wrong-but-different email must not be caught by the
        # lockout recorded for "lockout-test@example.org".
        response = client.post(
            "/api/v1/admin/login",
            json={"email": "someone-else@example.org", "password": "whatever"},
        )
        assert response.status_code == 401


class TestLockoutSurvivesRestart:
    """The actual bug being fixed: the old in-memory dicts reset to
    empty on every process restart, so a lockout could be trivially
    bypassed just by waiting for, or triggering, one (a deploy, a
    crash, Render's free-tier idle-then-wake cycle). Simulate a restart
    by throwing away the limiter instance and constructing a brand new
    one pointed at the same DB — it must still see the prior lockout,
    unlike an in-memory dict would.
    """

    def setup_method(self):
        _clear_login_lockout_state()

    def teardown_method(self):
        _clear_login_lockout_state()

    def test_fresh_instance_still_sees_prior_lockout(self):
        first_process_limiter = LoginAttemptLimiter(
            max_attempts=3, window_seconds=900, lockout_seconds=900, namespace="restart_test"
        )
        for _ in range(3):
            first_process_limiter.record_failure("attacker@example.org")

        # Simulate a restart: an entirely new LoginAttemptLimiter object,
        # as would be constructed fresh by a new Python process, but
        # backed by the same database.
        second_process_limiter = LoginAttemptLimiter(
            max_attempts=3, window_seconds=900, lockout_seconds=900, namespace="restart_test"
        )
        with pytest.raises(LockedOutError):
            second_process_limiter.check("attacker@example.org")

    def test_fresh_instance_correctly_unlocks_after_lockout_elapses(self):
        limiter = LoginAttemptLimiter(
            max_attempts=3, window_seconds=900, lockout_seconds=900, namespace="restart_test"
        )
        for _ in range(3):
            limiter.record_failure("attacker@example.org")

        db = SessionLocal()
        try:
            row = (
                db.query(RateLimitLockout)
                .filter(
                    RateLimitLockout.namespace == "restart_test",
                    RateLimitLockout.key == "attacker@example.org",
                )
                .one()
            )
            row.locked_until = row.locked_until - timedelta(seconds=901)
            db.commit()
        finally:
            db.close()

        fresh_limiter = LoginAttemptLimiter(
            max_attempts=3, window_seconds=900, lockout_seconds=900, namespace="restart_test"
        )
        fresh_limiter.check("attacker@example.org")  # must not raise


class TestSessionEndpoint:
    def setup_method(self):
        from app.config import settings

        self._prior = settings.SESSION_SECRET_KEY

    def teardown_method(self):
        from app.config import settings

        settings.SESSION_SECRET_KEY = self._prior

    def test_reports_not_authenticated_with_no_cookie(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "SESSION_SECRET_KEY", "test-secret")
        response = client.get("/api/v1/admin/session")
        assert response.status_code == 200
        assert response.json()["authenticated"] is False

    def test_reports_authenticated_with_valid_cookie(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "SESSION_SECRET_KEY", "test-secret")
        token = create_session_token("test-secret")
        response = client.get("/api/v1/admin/session", cookies={"of_admin_session": token})
        assert response.status_code == 200
        assert response.json()["authenticated"] is True


class TestLogoutEndpoint:
    def test_logout_clears_cookie(self):
        response = client.post("/api/v1/admin/logout")
        assert response.status_code == 200
        # Starlette represents a cleared cookie as a Set-Cookie with an
        # empty value / immediate expiry rather than omitting the header.
        assert "of_admin_session" in response.headers.get("set-cookie", "")
