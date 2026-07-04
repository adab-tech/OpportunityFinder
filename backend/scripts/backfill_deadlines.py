#!/usr/bin/env python
"""One-time data-quality repair: backfill missing deadlines on rows that
were ingested before RSS entries had deadline extraction applied (fixed
2026-07-04 — see app/scrapers/deadline_utils.py and rss_ingest.py).

Only touches rows where deadline IS NULL; never overwrites an existing
value. Safe to re-run at any time — a second run is always a no-op for
rows already backfilled.

Usage (same pattern as scripts/reclassify_opportunities.py — run as a
module from `backend/` with the venv active):

    # Dry run: prints what WOULD change, writes nothing.
    .\\.venv\\Scripts\\python.exe -m scripts.backfill_deadlines

    # Apply the corrections (single transaction, all-or-nothing).
    .\\.venv\\Scripts\\python.exe -m scripts.backfill_deadlines --apply

Requires DATABASE_URL to point at the target database, e.g.:

    $env:DATABASE_URL = "<paste the Render Postgres URL>"
    .\\.venv\\Scripts\\python.exe -m scripts.backfill_deadlines --apply
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Opportunity
from app.scrapers.deadline_utils import extract_deadline

logger = logging.getLogger("backfill_deadlines")


@dataclass(frozen=True)
class Backfill:
    id: int
    title: str
    source_name: str | None
    deadline: str


def find_backfills(db: Session) -> list[Backfill]:
    """Return rows with a null deadline where one can now be extracted
    from the stored title + description. Read-only.
    """
    rows = db.query(Opportunity).filter(Opportunity.deadline.is_(None)).all()

    backfills: list[Backfill] = []
    for row in rows:
        combined = f"{row.title} {row.description or ''}"
        deadline = extract_deadline(combined)
        if deadline:
            backfills.append(
                Backfill(id=row.id, title=row.title, source_name=row.source_name, deadline=deadline)
            )
    return backfills


def apply_backfills(db: Session, backfills: list[Backfill]) -> None:
    """Apply the given backfills in a single transaction."""
    if not backfills:
        return
    ids_to_deadline = {b.id: b.deadline for b in backfills}
    rows = db.query(Opportunity).filter(Opportunity.id.in_(ids_to_deadline)).all()
    for row in rows:
        row.deadline = ids_to_deadline[row.id]
    db.commit()


def _print_report(backfills: list[Backfill], applied: bool) -> None:
    if not backfills:
        print("No missing deadlines could be backfilled — nothing to do.")
        return

    verb = "Backfilled" if applied else "Would backfill"
    print(f"{verb} {len(backfills)} opportunity record(s):\n")
    for b in backfills:
        title = b.title if len(b.title) <= 60 else b.title[:57] + "..."
        print(f"  [{b.id:>5}] -> {b.deadline:<24} ({b.source_name})  {title}")

    if not applied:
        print("\nDry run only — no changes were written. Re-run with --apply to commit these changes.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill missing deadlines from stored title/description text.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the backfilled deadlines to the database. Without this flag, only a report is printed.",
    )
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
