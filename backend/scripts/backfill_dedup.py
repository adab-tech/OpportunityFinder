#!/usr/bin/env python
"""One-time data-quality repair for cross-source duplicates (added
2026-07-04 — see app/scrapers/dedup.py).

Two things this does:
  1. Populates `title_normalized` on rows ingested before that column
     existed (required before duplicate groups can even be detected).
  2. Finds groups of active rows that share the same normalized title
     (the same opportunity reposted by two different aggregators under
     different URLs) and deactivates all but the earliest-seen one —
     never deletes, so nothing is lost and it's fully reversible by
     flipping is_active back to true.

Dry-run by default; --apply required to write anything. Safe to re-run.

Usage (same pattern as the other scripts/ tools — run as a module from
`backend/` with the venv active):

    .\\.venv\\Scripts\\python.exe -m scripts.backfill_dedup
    .\\.venv\\Scripts\\python.exe -m scripts.backfill_dedup --apply

Requires DATABASE_URL to point at the target database, e.g.:

    $env:DATABASE_URL = "<paste the Render Postgres URL>"
    .\\.venv\\Scripts\\python.exe -m scripts.backfill_dedup --apply
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Opportunity
from app.scrapers.dedup import normalize_title

logger = logging.getLogger("backfill_dedup")


@dataclass(frozen=True)
class NormalizationBackfill:
    id: int
    title_normalized: str


@dataclass(frozen=True)
class DuplicateGroup:
    title_normalized: str
    keep_id: int
    keep_title: str
    deactivate_ids: list[int] = field(default_factory=list)


def find_normalization_backfills(db: Session) -> list[NormalizationBackfill]:
    rows = db.query(Opportunity).filter(Opportunity.title_normalized.is_(None)).all()
    return [NormalizationBackfill(id=r.id, title_normalized=normalize_title(r.title)) for r in rows]


def apply_normalization_backfills(db: Session, backfills: list[NormalizationBackfill]) -> None:
    if not backfills:
        return
    by_id = {b.id: b.title_normalized for b in backfills}
    rows = db.query(Opportunity).filter(Opportunity.id.in_(by_id)).all()
    for row in rows:
        row.title_normalized = by_id[row.id]
    db.commit()


def find_duplicate_groups(db: Session) -> list[DuplicateGroup]:
    """Group active rows by title_normalized; any group with more than
    one row is a set of duplicates. The earliest-scraped row in each
    group is kept active, the rest are marked for deactivation.
    """
    rows = (
        db.query(Opportunity)
        .filter(Opportunity.is_active.is_(True), Opportunity.title_normalized.isnot(None))
        .order_by(Opportunity.scraped_at.asc())
        .all()
    )

    by_normalized: dict[str, list[Opportunity]] = defaultdict(list)
    for row in rows:
        if row.title_normalized:
            by_normalized[row.title_normalized].append(row)

    groups: list[DuplicateGroup] = []
    for title_normalized, group_rows in by_normalized.items():
        if len(group_rows) < 2:
            continue
        keep, *rest = group_rows  # already ordered earliest-first
        groups.append(
            DuplicateGroup(
                title_normalized=title_normalized,
                keep_id=keep.id,
                keep_title=keep.title,
                deactivate_ids=[r.id for r in rest],
            )
        )
    return groups


def apply_duplicate_groups(db: Session, groups: list[DuplicateGroup]) -> None:
    if not groups:
        return
    all_deactivate_ids = [i for g in groups for i in g.deactivate_ids]
    rows = db.query(Opportunity).filter(Opportunity.id.in_(all_deactivate_ids)).all()
    for row in rows:
        row.is_active = False
    db.commit()


def _print_report(
    normalization_backfills: list[NormalizationBackfill],
    groups: list[DuplicateGroup],
    applied: bool,
) -> None:
    verb = "Backfilled" if applied else "Would backfill"
    print(f"{verb} title_normalized on {len(normalization_backfills)} row(s).\n")

    if not groups:
        print("No cross-source duplicate groups found.")
        return

    verb2 = "Deactivated" if applied else "Would deactivate"
    total_dupes = sum(len(g.deactivate_ids) for g in groups)
    print(f"{verb2} {total_dupes} duplicate row(s) across {len(groups)} group(s):\n")
    for g in groups:
        title = g.keep_title if len(g.keep_title) <= 55 else g.keep_title[:52] + "..."
        print(f"  Kept [{g.keep_id:>5}]  {title}")
        print(f"    -> deactivating: {g.deactivate_ids}")

    if not applied:
        print("\nDry run only — no changes were written. Re-run with --apply to commit these changes.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill title_normalized and deactivate cross-source duplicate opportunities.",
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
        normalization_backfills = find_normalization_backfills(db)
        if args.apply:
            apply_normalization_backfills(db, normalization_backfills)

        groups = find_duplicate_groups(db)
        if args.apply:
            apply_duplicate_groups(db, groups)

        _print_report(normalization_backfills, groups, applied=args.apply)
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
