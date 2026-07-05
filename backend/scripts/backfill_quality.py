#!/usr/bin/env python
"""One-time data-quality repair: deactivate already-live opportunities
whose title fails the low-quality/off-topic check (added 2026-07-05 —
see app/scrapers/quality.py). This is for rows ingested before that
filter existed — page-navigation chrome, listicle/roundup articles,
past-tense "who already won" announcements, and off-topic content
(sports trades, gaming patch notes, local politics) that leaked in via
web/You.com search discovery.

Same check the ingest paths (opportunity_scraper.py, rss_ingest.py) now
run before saving anything new, exposed here as a dry-run/--apply script
so you can see exactly what it's about to hide before committing to it.

Usage (same pattern as the other scripts/ tools — run as a module from
`backend/` with the venv active):

    .\\.venv\\Scripts\\python.exe -m scripts.backfill_quality
    .\\.venv\\Scripts\\python.exe -m scripts.backfill_quality --apply

Requires DATABASE_URL to point at the target database, e.g.:

    $env:DATABASE_URL = "<paste the Render Postgres URL>?sslmode=require"
    .\\.venv\\Scripts\\python.exe -m scripts.backfill_quality --apply
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
from app.scrapers.quality import is_low_quality_title

logger = logging.getLogger("backfill_quality")


@dataclass(frozen=True)
class LowQualityRow:
    id: int
    title: str


def find_low_quality_active_rows(db: Session) -> list[LowQualityRow]:
    """Return currently-active rows whose title fails the quality check. Read-only."""
    rows = db.query(Opportunity).filter(Opportunity.is_active.is_(True)).all()
    return [
        LowQualityRow(id=row.id, title=row.title)
        for row in rows
        if is_low_quality_title(row.title)
    ]


def apply_deactivations(db: Session, low_quality: list[LowQualityRow]) -> None:
    if not low_quality:
        return
    ids = [r.id for r in low_quality]
    rows = db.query(Opportunity).filter(Opportunity.id.in_(ids)).all()
    for row in rows:
        row.is_active = False
    db.commit()


def _print_report(low_quality: list[LowQualityRow], applied: bool) -> None:
    if not low_quality:
        print("No low-quality active opportunities found — nothing to do.")
        return

    verb = "Deactivated" if applied else "Would deactivate"
    print(f"{verb} {len(low_quality)} opportunity record(s):\n")

    for r in low_quality:
        title = r.title if len(r.title) <= 70 else r.title[:67] + "..."
        print(f"  [{r.id:>5}] {title}")

    if not applied:
        print("\nDry run only — no changes were written. Re-run with --apply to commit these changes.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deactivate already-live opportunities whose title fails the quality/off-topic check.",
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
        low_quality = find_low_quality_active_rows(db)
        if args.apply:
            apply_deactivations(db, low_quality)
        _print_report(low_quality, applied=args.apply)
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
