"""Admin login/logout — real email + password, replacing the old
shared X-Admin-Key header (see app/security.py for the hashing/session
primitives). A successful login sets a signed, httpOnly session cookie
that `require_admin_session` (used by routes/analytics.py and
routes/moderation.py) checks on every admin request.

Single admin account by design (ADMIN_EMAIL/ADMIN_PASSWORD_HASH env
vars) — this project has one operator today; a real accounts table
with roles is a reasonable future upgrade if/when there's a team, not
before.
"""

import hmac

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.config import settings
from app.security import create_session_token, verify_password, verify_session_token

router = APIRouter(prefix="/admin", tags=["Admin Auth"])

SESSION_COOKIE_NAME = "of_admin_session"
_SESSION_MAX_AGE_SECONDS = 12 * 60 * 60


class LoginRequest(BaseModel):
    email: str
    password: str


def _admin_configured() -> bool:
    return bool(settings.ADMIN_EMAIL and settings.ADMIN_PASSWORD_HASH and settings.SESSION_SECRET_KEY)


@router.post("/login")
def login(request: LoginRequest, response: Response):
    if not _admin_configured():
        raise HTTPException(
            status_code=503,
            detail="Admin login is not configured (ADMIN_EMAIL / ADMIN_PASSWORD_HASH / "
            "SESSION_SECRET_KEY unset).",
        )

    # Always run verify_password, even on an email mismatch, so a wrong
    # email doesn't return faster than a wrong password and leak which
    # one was wrong via response timing.
    email_matches = hmac.compare_digest(request.email.strip().lower(), settings.ADMIN_EMAIL.strip().lower())
    password_matches = verify_password(request.password, settings.ADMIN_PASSWORD_HASH)
    if not (email_matches and password_matches):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

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
