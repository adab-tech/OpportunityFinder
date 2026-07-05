#!/usr/bin/env python
"""One-time data-quality repair: deactivate opportunities that are
already expired but are currently showing as active (added 2026-07-05
— see app/scrapers/expiry.py). This is the direct fix for old scraped
listing pages (e.g. "Total E&P Nigeria CPFA Limited Recruitment 2019")
that were ingested before expiry checking existed.

Same logic as the ongoing scheduled sweep
(app/services/maintenance.deactivate_expired_opportunities), exposed
here as a dry-run/--apply script so you can see exactly what it's about
to hide before committing to it, and re-run it any time.

Usage (same pattern as the other scripts/ tools — run as a module from
`backend/` with the venv active):

    .\\.venv\\Scripts\\python.exe -m scripts.backfill_expiry
    .\\.venv\\Scripts\\python.exe -m scripts.backfill_expiry --apply

Requires DATABASE_URL to point at the target database, e.g.:

    $env:DATABASE_URL = "<paste the Render Postgres URL>?sslmode=require"
    .\\.venv\\Scripts\\python.exe -m scripts.backfill_expiry --apply
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Opportunity
from app.scrapers.expiry import is_expired

logger = logging.getLogger("backfill_expiry")


@dataclass(frozen=True)
class ExpiredRow:
    id: int
    title: str
    reason: str  # "past_deadline" | "stale_title_year"


def find_expired_active_rows(db: Session) -> list[ExpiredRow]:
    """Return currently-active rows that should be deactivated. Read-only."""
    today = date.today()
    rows = db.query(Opportunity).filter(Opportunity.is_active.is_(True)).all()

    expired: list[ExpiredRow] = []
    for row in rows:
        if row.deadline_at is not None:
            if row.deadline_at < today:
                expired.append(ExpiredRow(id=row.id, title=row.title, reason="past_deadline"))
        elif is_expired(None, row.title, today):
            expired.append(ExpiredRow(id=row.id, title=row.title, reason="stale_title_year"))
    return expired


def apply_deactivations(db: Session, expired: list[ExpiredRow]) -> None:
    if not expired:
        return
    ids = [e.id for e in expired]
    rows = db.query(Opportunity).filter(Opportunity.id.in_(ids)).all()
    for row in rows:
        row.is_active = False
    db.commit()


def _print_report(expired: list[ExpiredRow], applied: bool) -> None:
    if not expired:
        print("No expired-but-active opportunities found — nothing to do.")
        return

    verb = "Deactivated" if applied else "Would deactivate"
    past_deadline = [e for e in expired if e.reason == "past_deadline"]
    stale_title = [e for e in expired if e.reason == "stale_title_year"]
    print(f"{verb} {len(expired)} opportunity record(s):")
    print(f"  {len(past_deadline)} with a deadline already past")
    print(f"  {len(stale_title)} with no parseable deadline but a stale year in the title\n")

    for e in expired:
        title = e.title if len(e.title) <= 60 else e.title[:57] + "..."
        print(f"  [{e.id:>5}] ({e.reason:<17}) {title}")

    if not applied:
        print("\nDry run only — no changes were written. Re-run with --apply to commit these changes.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deactivate opportunities that are already expired but currently showing as active.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--apply", action="store_true", help="Write the changes. Default is dry-run.")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    elif isinstance(sys.stdout, io.TextIOWrapper):  # pragma: no cover
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    db = SessionLocal()
    try:
        expired = find_expired_active_rows(db)
        if args.apply:
            apply_deactivations(db, expired)
        _print_report(expired, applied=args.apply)
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
