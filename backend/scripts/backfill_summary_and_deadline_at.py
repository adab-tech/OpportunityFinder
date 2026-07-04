#!/usr/bin/env python
"""One-time data-quality repair: backfill the new `summary` and
`deadline_at` columns (added 2026-07-04) on rows ingested before they
existed.

Only touches rows where the target column IS NULL; never overwrites an
existing value. Safe to re-run at any time.

Usage (same pattern as the other scripts/ tools — run as a module from
`backend/` with the venv active):

    # Dry run: prints what WOULD change, writes nothing.
    .\\.venv\\Scripts\\python.exe -m scripts.backfill_summary_and_deadline_at

    # Apply the corrections (single transaction, all-or-nothing).
    .\\.venv\\Scripts\\python.exe -m scripts.backfill_summary_and_deadline_at --apply

Requires DATABASE_URL to point at the target database, e.g.:

    $env:DATABASE_URL = "<paste the Render Postgres URL>"
    .\\.venv\\Scripts\\python.exe -m scripts.backfill_summary_and_deadline_at --apply
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
from dataclasses import dataclass

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Opportunity
from app.scrapers.deadline_utils import parse_deadline_date
from app.scrapers.synopsis import build_synopsis

logger = logging.getLogger("backfill_summary_and_deadline_at")


@dataclass(frozen=True)
class Backfill:
    id: int
    title: str
    new_summary: str | None
    new_deadline_at: str | None  # ISO date string for display only


def find_backfills(db: Session) -> list[Backfill]:
    """Return rows missing `summary` and/or `deadline_at` where a value
    can now be computed. Read-only.
    """
    rows = (
        db.query(Opportunity)
        .filter(or_(Opportunity.summary.is_(None), Opportunity.deadline_at.is_(None)))
        .all()
    )

    backfills: list[Backfill] = []
    for row in rows:
        new_summary = None
        if row.summary is None:
            new_summary = build_synopsis(
                row.title, row.opportunity_type, row.field, row.location, row.deadline, row.description
            )

        new_deadline_at = None
        if row.deadline_at is None and row.deadline:
            new_deadline_at = parse_deadline_date(row.deadline)

        if new_summary or new_deadline_at:
            backfills.append(
                Backfill(
                    id=row.id,
                    title=row.title,
                    new_summary=new_summary,
                    new_deadline_at=new_deadline_at.isoformat() if new_deadline_at else None,
                )
            )
    return backfills


def apply_backfills(db: Session, backfills: list[Backfill]) -> None:
    if not backfills:
        return
    by_id = {b.id: b for b in backfills}
    rows = db.query(Opportunity).filter(Opportunity.id.in_(by_id)).all()
    for row in rows:
        b = by_id[row.id]
        if b.new_summary:
            row.summary = b.new_summary
        if b.new_deadline_at:
            row.deadline_at = parse_deadline_date(row.deadline)  # recompute as a date object
    db.commit()


def _print_report(backfills: list[Backfill], applied: bool) -> None:
    if not backfills:
        print("Nothing to backfill — all rows already have summary and deadline_at where possible.")
        return

    verb = "Backfilled" if applied else "Would backfill"
    print(f"{verb} {len(backfills)} opportunity record(s):\n")
    for b in backfills:
        title = b.title if len(b.title) <= 50 else b.title[:47] + "..."
        flags = []
        if b.new_summary:
            flags.append("summary")
        if b.new_deadline_at:
            flags.append(f"deadline_at={b.new_deadline_at}")
        print(f"  [{b.id:>5}] {', '.join(flags):<40} {title}")

    if not applied:
        print("\nDry run only — no changes were written. Re-run with --apply to commit these changes.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill summary and deadline_at on rows ingested before those columns existed.",
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
        backfills = find_backfills(db)
        if args.apply:
            apply_backfills(db, backfills)
        _print_report(backfills, applied=args.apply)
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
