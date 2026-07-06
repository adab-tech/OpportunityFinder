"""Regression tests for the admin email/password login system
(app/security.py, app/routes/admin_auth.py) — replaces the old shared
X-Admin-Key header with a real account and a signed session cookie.
"""

from fastapi.testclient import TestClient

from app.main import app
from app.security import create_session_token, hash_password, verify_password, verify_session_token

client = TestClient(app)


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


class TestLoginEndpoint:
    def setup_method(self):
        from app.config import settings

        self._prior = (settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD_HASH, settings.SESSION_SECRET_KEY)

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
