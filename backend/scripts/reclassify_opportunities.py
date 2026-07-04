#!/usr/bin/env python
"""One-time data-quality repair: reclassify opportunities that were saved
under a feed's old, overly broad hardcoded opportunity_type.

Background
----------
Before 2026-07-04, the RSS feeds for AfterSchool Africa and Opportunities
for Africans were configured as single generic feeds with one fixed
opportunity_type ("scholarship" and "job" respectively), even though both
sites publish scholarships, fellowships, grants, *and* jobs. Anything
already ingested under that config may carry the wrong label — e.g. a
real scholarship stored with opportunity_type="job".

This script re-runs app.scrapers.keywords.detect_opportunity_type against
the *stored* title of every row from the affected sources and reports (or
applies) corrections. It never touches rows whose current type already
looks right, and it never downgrades a confident label to "other" — it
only relabels when the title contains an unambiguous signal for a
*different* concrete type.

Usage
-----
Run as a module (not as a bare script) so `app` and `scripts` both resolve
on the path — from the `backend/` directory with the venv active:

    # Safe by default: prints what WOULD change, writes nothing.
    .\\.venv\\Scripts\\python.exe -m scripts.reclassify_opportunities

    # Apply the corrections (single transaction, all-or-nothing).
    .\\.venv\\Scripts\\python.exe -m scripts.reclassify_opportunities --apply

    # Limit to specific sources (comma-separated, matches source_name).
    .\\.venv\\Scripts\\python.exe -m scripts.reclassify_opportunities \
        --sources "AfterSchool Africa,Opportunities for Africans"

Requires DATABASE_URL to be set to the target database (defaults to
whatever app.config.Settings resolves — i.e. the same env the API uses).
To run against production:

    $env:DATABASE_URL = "<paste the Render Postgres URL>"
    .\\.venv\\Scripts\\python.exe -m scripts.reclassify_opportunities --apply
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
from app.scrapers.keywords import detect_opportunity_type

logger = logging.getLogger("reclassify")

# Only these sources ever had a "one fixed type for a multi-category site"
# bug. Restricting to them avoids touching rows from feeds/scrapers that
# were always classified per-entry correctly (e.g. ReliefWeb, Scholars4Dev).
AFFECTED_SOURCES = ("AfterSchool Africa", "Opportunities for Africans")

# Detected type must be one of these to justify an override — "other" is
# never confident enough to replace an existing concrete label.
CONFIDENT_TYPES = {"scholarship", "fellowship", "grant", "job"}


@dataclass(frozen=True)
class Correction:
    id: int
    title: str
    source_name: str | None
    old_type: str
    new_type: str


def find_corrections(db: Session, sources: tuple[str, ...] = AFFECTED_SOURCES) -> list[Correction]:
    """Return the list of rows whose stored type disagrees with what the
    title-keyword classifier would assign today. Read-only — makes no changes.
    """
    rows = (
        db.query(Opportunity)
        .filter(or_(*(Opportunity.source_name == s for s in sources)))
        .all()
    )

    corrections: list[Correction] = []
    for row in rows:
        detected = detect_opportunity_type(row.title, default="other")
        if detected in CONFIDENT_TYPES and detected != row.opportunity_type:
            corrections.append(
                Correction(
                    id=row.id,
                    title=row.title,
                    source_name=row.source_name,
                    old_type=row.opportunity_type,
                    new_type=detected,
                )
            )
    return corrections


def apply_corrections(db: Session, corrections: list[Correction]) -> None:
    """Apply the given corrections in a single transaction."""
    if not corrections:
        return
    ids_to_type = {c.id: c.new_type for c in corrections}
    rows = db.query(Opportunity).filter(Opportunity.id.in_(ids_to_type)).all()
    for row in rows:
        row.opportunity_type = ids_to_type[row.id]
    db.commit()


def _print_report(corrections: list[Correction], applied: bool) -> None:
    if not corrections:
        print("No mislabeled opportunities found — nothing to do.")
        return

    verb = "Corrected" if applied else "Would correct"
    print(f"{verb} {len(corrections)} opportunity record(s):\n")
    for c in corrections:
        title = c.title if len(c.title) <= 70 else c.title[:67] + "..."
        print(f"  [{c.id:>5}] {c.old_type:>11} -> {c.new_type:<11} ({c.source_name})  {title}")

    if not applied:
        print("\nDry run only — no changes were written. Re-run with --apply to commit these changes.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reclassify opportunities mislabeled by an old single-type feed config.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the corrections to the database. Without this flag, only a report is printed.",
    )
    parser.add_argument(
        "--sources",
        type=str,
        default=None,
        help=f"Comma-separated source_name values to check (default: {', '.join(AFFECTED_SOURCES)}).",
    )
    args = parser.parse_args(argv)

    sources = tuple(s.strip() for s in args.sources.split(",")) if args.sources else AFFECTED_SOURCES

    # Titles routinely contain non-ASCII characters (e.g. "Master's",
    # "Böll"); the default Windows console codepage mangles them, so
    # force UTF-8 for this process's stdout/stderr regardless of platform.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    elif isinstance(sys.stdout, io.TextIOWrapper):  # pragma: no cover
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    db = SessionLocal()
    try:
        corrections = find_corrections(db, sources=sources)
        if args.apply:
            apply_corrections(db, corrections)
        _print_report(corrections, applied=args.apply)
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
