"""Admin authentication primitives — password hashing and signed
session cookies. Deliberately stdlib-only (hashlib/hmac), no new
dependency, consistent with this project's preference for the smallest
tool that's actually correct (see the lightweight migrations system in
app/migrations.py for the same philosophy).

Password hashing: PBKDF2-HMAC-SHA256, a NIST-recommended KDF built into
every Python install. Stored format is `pbkdf2$<iterations>$<salt_hex>$<hash_hex>`
so the iteration count can be raised later without breaking existing
hashes. Generate one with `scripts/hash_admin_password.py`.

Session cookie: `<expiry_unix_ts>.<hmac_hex>`, signed with
SESSION_SECRET_KEY. Not a JWT — there's exactly one claim (an admin is
logged in, until this timestamp), so a full JWT library would be
unused complexity for this project's actual need (a single admin
account, not a multi-tenant auth system).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

_PBKDF2_ITERATIONS = 600_000  # OWASP 2023 minimum recommendation for PBKDF2-SHA256
_SESSION_TTL_SECONDS = 12 * 60 * 60  # 12 hours — re-login after, no silent renewal


def hash_password(plaintext: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", plaintext.encode(), bytes.fromhex(salt), _PBKDF2_ITERATIONS)
    return f"pbkdf2${_PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(plaintext: str, stored_hash: str) -> bool:
    try:
        scheme, iterations_s, salt, expected_hex = stored_hash.split("$")
        if scheme != "pbkdf2":
            return False
        iterations = int(iterations_s)
    except (ValueError, AttributeError):
        return False

    actual = hashlib.pbkdf2_hmac("sha256", plaintext.encode(), bytes.fromhex(salt), iterations)
    return hmac.compare_digest(actual.hex(), expected_hex)


def create_session_token(secret_key: str) -> str:
    expiry = int(time.time()) + _SESSION_TTL_SECONDS
    signature = _sign(str(expiry), secret_key)
    return f"{expiry}.{signature}"


def verify_session_token(token: str | None, secret_key: str) -> bool:
    if not token or "." not in token:
        return False
    expiry_s, signature = token.split(".", 1)
    if not hmac.compare_digest(_sign(expiry_s, secret_key), signature):
        return False
    try:
        expiry = int(expiry_s)
    except ValueError:
        return False
    return time.time() < expiry


def _sign(value: str, secret_key: str) -> str:
    return hmac.new(secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()
