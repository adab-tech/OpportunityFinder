#!/usr/bin/env python
"""One-time helper: generate a fresh TOTP secret for the optional admin
2FA second factor, and print both the value to paste into
ADMIN_TOTP_SECRET and an `otpauth://` provisioning URI you can turn
into a QR code (paste it into any online QR generator — see below) or
hand straight to an authenticator app that accepts a pasted URI.

Usage (run as a module from `backend/` with the venv active):

    .\\.venv\\Scripts\\python.exe -m scripts.generate_admin_totp_secret

Then:
  1. Paste ADMIN_TOTP_SECRET into your deployment's environment
     variables (Render dashboard, or a local .env for dev).
  2. Get the secret into your authenticator app (Google Authenticator,
     Authy, 1Password, etc.) one of two ways:
       - Turn the printed otpauth:// URI into a QR code with any online
         QR generator (e.g. https://www.qr-code-generator.com/) and
         scan it, or
       - Choose "enter setup key manually" in the app and type in the
         secret yourself.
  3. Restart the app with ADMIN_TOTP_SECRET set. From then on,
     /admin/login also requires the current 6-digit code from the app.

Leaving ADMIN_TOTP_SECRET unset (the default) keeps login exactly as
it was before this existed: email + password only. There is no
disable/recovery flow beyond unsetting the env var and restarting —
this is a single-operator tool, not a multi-user product.
"""

import sys

from app.config import settings
from app.security import generate_totp_secret, totp_provisioning_uri


def main() -> int:
    secret = generate_totp_secret()
    account_email = settings.ADMIN_EMAIL or "admin@example.org"

    # CodeQL flags this as clear-text logging of a secret (py/clear-text-
    # logging-sensitive-data) — accurate, but unavoidable by design: unlike
    # hash_admin_password.py, which only ever prints a one-way PBKDF2 hash,
    # there is no derived value to substitute here. An authenticator app
    # needs the literal shared secret to generate matching codes, so a
    # provisioning tool for it has to display the real value at least once.
    # Run this only in a local, interactive terminal you trust — not piped
    # to a file, not in a CI job, not in a session with shell history or
    # scrollback shared with anyone else.
    print("Caution: the secret below is shown in clear text. Only run this in a")
    print("local, interactive terminal you trust — not piped to a file or a")
    print("logged CI job, and not in a session anyone else can see or replay.")
    print()
    print("ADMIN_TOTP_SECRET=" + secret)  # lgtm[py/clear-text-logging-sensitive-data]
    print()
    print("Scan this as a QR code, or paste it directly into an app that accepts a URI:")
    print(totp_provisioning_uri(secret, account_email))  # lgtm[py/clear-text-logging-sensitive-data]
    if not settings.ADMIN_EMAIL:
        print()
        print(
            "Note: ADMIN_EMAIL isn't set in this environment, so the URI above uses "
            f"the placeholder '{account_email}' as the account label — that's only a "
            "display name inside the authenticator app, it doesn't need to match. "
            "Re-run this after setting ADMIN_EMAIL if you'd rather it show the real address."
        )
    print()
    print("Paste ADMIN_TOTP_SECRET into your deployment's environment variables and")
    print("restart. Nothing about existing sessions or the admin password changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
