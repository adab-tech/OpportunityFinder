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

Optional TOTP second factor (RFC 6238): a plain stdlib implementation
(hmac/hashlib/struct/base64), same reasoning as the rest of this
module — `pyotp` would be one more dependency for ~30 lines of very
standard math. Verified against the RFC 6238 Appendix B test vectors
(SHA1, 8-digit truncation) before shipping; this implementation truncates
to 6 digits instead, which is the same HOTP value mod 10**6, per the
RFC's truncation function. Only active when `ADMIN_TOTP_SECRET` is set
(see app/config.py) — unset means login is password-only, unchanged
from before this existed.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

_PBKDF2_ITERATIONS = 600_000  # OWASP 2023 minimum recommendation for PBKDF2-SHA256
_SESSION_TTL_SECONDS = 12 * 60 * 60  # 12 hours — re-login after, no silent renewal

_TOTP_DIGITS = 6
_TOTP_STEP_SECONDS = 30
_TOTP_WINDOW_STEPS = 1  # accept one step before/after, for clock drift


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


def generate_totp_secret() -> str:
    """A fresh random base32 secret — 20 bytes (160 bits), the size RFC
    4226 recommends for HMAC-SHA1-based one-time passwords, and long
    enough that base32-encoding it (8 bits -> 5 bits per char) needs no
    `=` padding (160 / 5 = 32 chars exactly). Used by
    scripts/generate_admin_totp_secret.py.
    """
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def totp_provisioning_uri(secret: str, account_email: str, issuer: str = "OpportunityFinder Admin") -> str:
    """An `otpauth://` URI an authenticator app can import (by pasting it
    in, or by turning it into a QR code with any online generator — no
    QR library needed here). See RFC "Key Uri Format"
    (https://github.com/google/google-authenticator/wiki/Key-Uri-Format).
    """
    label = urllib.parse.quote(f"{issuer}:{account_email}")
    params = {
        "secret": secret,
        "issuer": issuer,
        "algorithm": "SHA1",
        "digits": _TOTP_DIGITS,
        "period": _TOTP_STEP_SECONDS,
    }
    return f"otpauth://totp/{label}?{urllib.parse.urlencode(params)}"


def _decode_base32_secret(secret: str) -> bytes | None:
    # Authenticator apps and humans copy-pasting secrets routinely drop
    # padding and/or lowercase it; base64.b32decode is strict about both.
    cleaned = secret.strip().replace(" ", "").upper()
    padded = cleaned + "=" * (-len(cleaned) % 8)
    try:
        return base64.b32decode(padded)
    except ValueError:  # binascii.Error subclasses ValueError
        return None


def _hotp(key: bytes, counter: int) -> str:
    """RFC 4226 HOTP: HMAC-SHA1 over the counter, dynamically truncated
    to `_TOTP_DIGITS` decimal digits.
    """
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF
    return str(truncated % (10**_TOTP_DIGITS)).zfill(_TOTP_DIGITS)


def verify_totp_code(code: str | None, secret: str, at: float | None = None) -> bool:
    """RFC 6238 TOTP verification. Accepts the code for the current
    30-second time step plus one step before/after (`_TOTP_WINDOW_STEPS`)
    to tolerate ordinary clock drift between server and phone — standard
    TOTP practice, e.g. Google Authenticator's own reference server does
    the same. `at` is only for tests; real callers always use "now".
    """
    if not code or not code.isdigit() or len(code) != _TOTP_DIGITS:
        return False
    key = _decode_base32_secret(secret)
    if not key:
        return False

    counter = int(at if at is not None else time.time()) // _TOTP_STEP_SECONDS
    for offset in range(-_TOTP_WINDOW_STEPS, _TOTP_WINDOW_STEPS + 1):
        if hmac.compare_digest(_hotp(key, counter + offset), code):
            return True
    return False
