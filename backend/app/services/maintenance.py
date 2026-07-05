"""Scheduled housekeeping: deactivate opportunities that have expired
since they were ingested.

The query-level filter in routes/opportunities.py (`_not_expired`) is
the real guarantee that a passed deadline is never shown — this sweep
exists so `is_active` stays an accurate signal for everything else that
reads it (the alert digest, the admin analytics, future features),
rather than a flag that's only correct at ingest time and silently goes
stale as calendar days pass.
"""

import logging
from datetime import date

from sqlalchemy.orm import Session

from app.models import Opportunity
from app.scrapers.expiry import is_expired

logger = logging.getLogger(__name__)


def deactivate_expired_opportunities(db: Session) -> dict[str, int]:
    today = date.today()

    # Definitive case: a parsed deadline that has now passed.
    past_deadline = (
        db.query(Opportunity)
        .filter(Opportunity.is_active.is_(True), Opportunity.deadline_at < today)
        .all()
    )

    # Heuristic case: no parsed deadline, but the title carries a year
    # that's now in the past (only re-checked for undated rows, since a
    # parsed deadline is always trusted over the title heuristic).
    undated_candidates = (
        db.query(Opportunity)
        .filter(Opportunity.is_active.is_(True), Opportunity.deadline_at.is_(None))
        .all()
    )
    stale_by_title = [row for row in undated_candidates if is_expired(None, row.title, today)]

    to_deactivate = past_deadline + stale_by_title
    for row in to_deactivate:
        row.is_active = False
    if to_deactivate:
        db.commit()

    stats = {
        "deactivated_past_deadline": len(past_deadline),
        "deactivated_stale_title": len(stale_by_title),
    }
    logger.info("Expired-opportunity sweep complete: %s", stats)
    return stats
