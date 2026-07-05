#!/usr/bin/env python
"""Safety-net tool for bulk-setting `review_status` on existing rows
(added 2026-07-05 with the moderation gate — see app/routes/moderation.py,
app/scrapers/opportunity_scraper.py, app/scrapers/rss_ingest.py).

Two uses:

1. Defensive repair: any row with a NULL/missing `review_status` (should
   not happen given the column's NOT NULL DEFAULT, but this covers rows
   written before the migration ran, or via any path that bypassed the
   ORM default) is reported and force-approved — never left in limbo.
2. Bulk moderation action scoped by `--source`/`--type`, e.g. to approve
   an entire trusted source retroactively, or push a source back to
   pending for re-review.

Usage (same pattern as the other scripts/ tools — run as a module from
`backend/` with the venv active):

    .\\.venv\\Scripts\\python.exe -m scripts.backfill_review_status
    .\\.venv\\Scripts\\python.exe -m scripts.backfill_review_status --apply
    .\\.venv\\Scripts\\python.exe -m scripts.backfill_review_status --set-approved \
        --source "Example Feed" --apply
    .\\.venv\\Scripts\\python.exe -m scripts.backfill_review_status --set-pending --type job --apply

Requires DATABASE_URL to point at the target database, e.g.:

    $env:DATABASE_URL = "<paste the Render Postgres URL>?sslmode=require"
    .\\.venv\\Scripts\\python.exe -m scripts.backfill_review_status --apply
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

logger = logging.getLogger("backfill_review_status")


@dataclass(frozen=True)
class ReviewStatusRow:
    id: int
    title: str
    current_status: str | None
    new_status: str


def find_null_review_status_rows(db: Session) -> list[ReviewStatusRow]:
    """Defensive check: rows with a missing/NULL review_status, which
    should force-approve (they predate the moderation gate entirely, so
    treating them as low-trust-pending would be a regression — they were
    already live and trusted before this feature existed). Read-only.
    """
    rows = (
        db.query(Opportunity)
        .filter(Opportunity.review_status.is_(None))
        .all()
    )
    return [
        ReviewStatusRow(id=r.id, title=r.title, current_status=r.review_status, new_status="approved")
        for r in rows
    ]


def find_scoped_rows(
    db: Session,
    new_status: str,
    source: str | None = None,
    opportunity_type: str | None = None,
) -> list[ReviewStatusRow]:
    """Rows matching the optional --source/--type filters that don't
    already have `new_status`. Read-only.
    """
    q = db.query(Opportunity).filter(Opportunity.review_status != new_status)
    if source:
        q = q.filter(Opportunity.source_name.ilike(f"%{source}%"))
    if opportunity_type:
        q = q.filter(Opportunity.opportunity_type == opportunity_type.lower())

    rows = q.all()
    return [
        ReviewStatusRow(id=r.id, title=r.title, current_status=r.review_status, new_status=new_status)
        for r in rows
    ]


def apply_review_status(db: Session, rows: list[ReviewStatusRow]) -> None:
    if not rows:
        return
    by_status: dict[str, list[int]] = {}
    for row in rows:
        by_status.setdefault(row.new_status, []).append(row.id)

    for new_status, ids in by_status.items():
        matched = db.query(Opportunity).filter(Opportunity.id.in_(ids)).all()
        for r in matched:
            r.review_status = new_status
    db.commit()


def _print_report(rows: list[ReviewStatusRow], applied: bool) -> None:
    if not rows:
        print("No matching rows found — nothing to do.")
        return

    verb = "Updated" if applied else "Would update"
    print(f"{verb} {len(rows)} opportunity record(s):")
    for row in rows:
        title = row.title if len(row.title) <= 60 else row.title[:57] + "..."
        print(f"  [{row.id:>5}] {row.current_status or 'NULL':<10} -> {row.new_status:<10} {title}")

    if not applied:
        print("\nDry run only — no changes were written. Re-run with --apply to commit these changes.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bulk-set review_status on existing opportunity rows.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--apply", action="store_true", help="Write the changes. Default is dry-run.")
    parser.add_argument(
        "--set-approved", action="store_true", help="Set review_status='approved' on matching rows."
    )
    parser.add_argument(
        "--set-pending", action="store_true", help="Set review_status='pending' on matching rows."
    )
    parser.add_argument("--source", default=None, help="Scope to source_name containing this text.")
    parser.add_argument("--type", dest="opportunity_type", default=None, help="Scope to opportunity_type.")
    args = parser.parse_args(argv)

    if args.set_approved and args.set_pending:
        parser.error("--set-approved and --set-pending are mutually exclusive.")

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    elif isinstance(sys.stdout, io.TextIOWrapper):  # pragma: no cover
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    db = SessionLocal()
    try:
        rows: list[ReviewStatusRow] = []

        # Defensive pass always runs: NULL/missing review_status is
        # force-approved regardless of which scoped flag was requested.
        null_rows = find_null_review_status_rows(db)
        rows.extend(null_rows)

        if args.set_approved:
            rows.extend(
                find_scoped_rows(db, "approved", source=args.source, opportunity_type=args.opportunity_type)
            )
        elif args.set_pending:
            rows.extend(
                find_scoped_rows(db, "pending", source=args.source, opportunity_type=args.opportunity_type)
            )

        if args.apply:
            apply_review_status(db, rows)
        _print_report(rows, applied=args.apply)
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
