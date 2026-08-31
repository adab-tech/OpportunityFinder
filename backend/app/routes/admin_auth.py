"""Admin login/logout — real email + password, replacing the old
shared X-Admin-Key header (see app/security.py for the hashing/session
primitives). A successful login sets a signed, httpOnly session cookie
that `require_admin_session` (used by routes/analytics.py and
routes/moderation.py) checks on every admin request.

Single admin account by design (ADMIN_EMAIL/ADMIN_PASSWORD_HASH env
vars) — this project has one operator today; a real accounts table
with roles is a reasonable future upgrade if/when there's a team, not
before.

Optional TOTP second factor: if ADMIN_TOTP_SECRET is set, `/login`
also requires a valid 6-digit `totp_code` in the same request (one
step, not a separate endpoint — this is a single-admin tool, a second
round trip would just be more code for no real benefit). Unset means
login is exactly what it was before this existed: email + password
only. `GET /login-methods` is a public, pre-auth check so the login
form knows whether to render the code field at all.
"""

import hmac

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.config import settings
from app.security import create_session_token, verify_password, verify_session_token, verify_totp_code
from app.services.rate_limit import LockedOutError, LoginAttemptLimiter

router = APIRouter(prefix="/admin", tags=["Admin Auth"])

SESSION_COOKIE_NAME = "of_admin_session"
_SESSION_MAX_AGE_SECONDS = 12 * 60 * 60

# Keyed by submitted email, not caller IP — there's exactly one valid
# admin account (see module docstring), so this directly protects it
# regardless of how many source addresses an attacker spreads across.
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 15 * 60
_LOGIN_LOCKOUT_SECONDS = 15 * 60
# Persisted in the DB (app/models.py RateLimitLockout), not process
# memory — see app/services/rate_limit.py's module docstring for why.
_login_limiter = LoginAttemptLimiter(
    max_attempts=_LOGIN_MAX_ATTEMPTS,
    window_seconds=_LOGIN_WINDOW_SECONDS,
    lockout_seconds=_LOGIN_LOCKOUT_SECONDS,
    namespace="admin_login",
)


class LoginRequest(BaseModel):
    email: str
    password: str
    totp_code: str | None = None


def _admin_configured() -> bool:
    return bool(settings.ADMIN_EMAIL and settings.ADMIN_PASSWORD_HASH and settings.SESSION_SECRET_KEY)


def _totp_configured() -> bool:
    return bool(settings.ADMIN_TOTP_SECRET)


# Refuses a second login with the exact same TOTP code that most
# recently succeeded — a shoulder-surfed or log-leaked code shouldn't be
# replayable. Not required by RFC 6238 and not requested as a hard
# requirement, but cheap enough to be worth doing (see app/security.py's
# module docstring). A single `str | None`, not a set with expiry,
# because there is exactly one admin account to protect; reused module-
# level state the same way `_login_limiter` is.
_last_used_totp_code: str | None = None


@router.get("/login-methods")
def login_methods():
    """Public, pre-auth check: does /login require a TOTP code? The
    server is the only side that knows whether ADMIN_TOTP_SECRET is
    set, so the login form calls this first to decide whether to show
    that field at all. Reveals only a boolean — no account details —
    which is an acceptable trade for a single-operator tool on an
    unlisted URL, not a public-facing product surface.
    """
    return {"totp_required": _totp_configured()}


@router.post("/login")
def login(request: LoginRequest, response: Response):
    global _last_used_totp_code

    if not _admin_configured():
        raise HTTPException(
            status_code=503,
            detail="Admin login is not configured (ADMIN_EMAIL / ADMIN_PASSWORD_HASH / "
            "SESSION_SECRET_KEY unset).",
        )

    login_key = request.email.strip().lower()
    try:
        _login_limiter.check(login_key)
    except LockedOutError:
        wait = _login_limiter.seconds_remaining(login_key)
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {wait}s.",
        ) from None

    # Always run verify_password (and, when configured, verify_totp_code),
    # even on an email mismatch, so a wrong email doesn't return faster
    # than a wrong password/code and leak which one was wrong via
    # response timing.
    email_matches = hmac.compare_digest(login_key, settings.ADMIN_EMAIL.strip().lower())
    password_matches = verify_password(request.password, settings.ADMIN_PASSWORD_HASH)
    totp_required = _totp_configured()
    if totp_required:
        totp_matches = verify_totp_code(request.totp_code, settings.ADMIN_TOTP_SECRET)
        # Reject replay of the exact code that just succeeded, even if
        # it's still within its valid window.
        if request.totp_code is not None and request.totp_code == _last_used_totp_code:
            totp_matches = False
    else:
        totp_matches = True

    if not (email_matches and password_matches and totp_matches):
        _login_limiter.record_failure(login_key)
        if totp_required:
            detail = "Invalid email, password, or authentication code."
        else:
            detail = "Invalid email or password."
        raise HTTPException(status_code=401, detail=detail)

    if totp_required:
        _last_used_totp_code = request.totp_code

    _login_limiter.record_success(login_key)
    token = create_session_token(settings.SESSION_SECRET_KEY)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="strict",
        max_age=_SESSION_MAX_AGE_SECONDS,
        path="/",
    )
    return {"status": "ok"}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"status": "ok"}


@router.get("/session")
def check_session(request: Request):
    """Lets the admin page silently check "am I still logged in?" on
    load without prompting for credentials again.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    valid = bool(settings.SESSION_SECRET_KEY) and verify_session_token(token, settings.SESSION_SECRET_KEY)
    return {"authenticated": valid}


def require_admin_session(request: Request) -> None:
    """Shared FastAPI dependency for every admin-only endpoint (analytics
    summary, moderation queue). Fails closed: unset SESSION_SECRET_KEY or
    missing/expired/invalid cookie both mean "not authenticated" — no
    ambiguity between "not configured" and "wrong session" is exposed
    here (unlike /login, which does distinguish 503 vs 401, since a
    logged-out visitor hitting these directly gets no useful signal
    either way).
    """
    if not settings.SESSION_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Admin session auth is not configured.")
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not verify_session_token(token, settings.SESSION_SECRET_KEY):
        raise HTTPException(status_code=401, detail="Not authenticated. Please log in again.")
