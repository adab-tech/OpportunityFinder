"""Self-hosted, privacy-conscious visitor analytics.

No third-party tracker (no Google Analytics, no cookies, no IP storage
at the application layer). The frontend generates a random client_id
once and stores it in localStorage — this distinguishes "a repeat
browser" from "a new one" in aggregate counts, but never identifies a
person, and nothing here is sold or shared.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import AnalyticsEvent

VALID_EVENT_TYPES = {
    "pageview",
    "search",
    "filter_type",
    "filter_field",
    "filter_location",
    "apply_click",
    "save_click",
    "alert_create",
}


def record_event(
    db: Session,
    event_type: str,
    client_id: str,
    value: str | None = None,
    opportunity_id: int | None = None,
) -> None:
    if event_type not in VALID_EVENT_TYPES or not client_id:
        return
    db.add(
        AnalyticsEvent(
            event_type=event_type,
            client_id=client_id[:64],
            value=(value or "")[:200] or None,
            opportunity_id=opportunity_id,
        )
    )
    db.commit()


def _top_values(db: Session, event_type: str, since: datetime, limit: int = 10) -> list[dict]:
    rows = (
        db.query(AnalyticsEvent.value, func.count(AnalyticsEvent.id))
        .filter(
            AnalyticsEvent.event_type == event_type,
            AnalyticsEvent.created_at >= since,
            AnalyticsEvent.value.isnot(None),
        )
        .group_by(AnalyticsEvent.value)
        .order_by(func.count(AnalyticsEvent.id).desc())
        .limit(limit)
        .all()
    )
    return [{"value": value, "count": count} for value, count in rows]


def get_summary(db: Session, days: int = 7) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)

    base = db.query(AnalyticsEvent).filter(AnalyticsEvent.created_at >= since)

    event_counts = dict(
        db.query(AnalyticsEvent.event_type, func.count(AnalyticsEvent.id))
        .filter(AnalyticsEvent.created_at >= since)
        .group_by(AnalyticsEvent.event_type)
        .all()
    )

    unique_visitors = (
        db.query(func.count(func.distinct(AnalyticsEvent.client_id)))
        .filter(AnalyticsEvent.created_at >= since)
        .scalar()
    ) or 0

    return {
        "period_days": days,
        "total_events": base.count(),
        "unique_visitors": unique_visitors,
        "event_counts": event_counts,
        "top_searches": _top_values(db, "search", since),
        "top_type_filters": _top_values(db, "filter_type", since),
        "top_field_filters": _top_values(db, "filter_field", since),
        "top_location_filters": _top_values(db, "filter_location", since),
    }
