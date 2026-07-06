#!/usr/bin/env python
"""One-time helper: turn a chosen admin password into the
ADMIN_PASSWORD_HASH value you paste into your deployment's environment
variables (Render dashboard, or a local .env for dev). The plaintext
password is never written anywhere by this script — only the hash is
printed, and only to your own terminal.

Usage (run as a module from `backend/` with the venv active):

    .\\.venv\\Scripts\\python.exe -m scripts.hash_admin_password

You'll be prompted for the password (input is hidden). Copy the printed
hash into ADMIN_PASSWORD_HASH, and set ADMIN_EMAIL + a random
SESSION_SECRET_KEY alongside it — all three are required for admin
login to work (see app/routes/admin_auth.py).

A good SESSION_SECRET_KEY is any long random string, e.g. generate one
with:

    .\\.venv\\Scripts\\python.exe -c "import secrets; print(secrets.token_hex(32))"
"""

import getpass
import sys

from app.security import hash_password


def main() -> int:
    password = getpass.getpass("Choose an admin password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords did not match. Nothing was generated.")
        return 1
    if len(password) < 12:
        print("Warning: that password is under 12 characters. Consider something longer.")

    print("\nADMIN_PASSWORD_HASH=" + hash_password(password))
    print("\nPaste that (with your ADMIN_EMAIL and a SESSION_SECRET_KEY) into your")
    print("deployment's environment variables. The password itself is not stored anywhere.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
