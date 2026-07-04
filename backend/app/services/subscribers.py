"""Business logic for saved opportunities and alert subscriptions.

Kept separate from the route handlers so it can be unit-tested directly
against a database session, without going through FastAPI/TestClient.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AlertSubscription, Opportunity, SavedOpportunity, Subscriber
from app.services.email_sender import EmailMessage, get_email_sender

logger = logging.getLogger(__name__)


def get_or_create_subscriber(db: Session, email: str) -> Subscriber:
    email = email.strip().lower()
    subscriber = db.query(Subscriber).filter(Subscriber.email == email).first()
    if subscriber:
        return subscriber
    subscriber = Subscriber(email=email)
    db.add(subscriber)
    db.commit()
    db.refresh(subscriber)
    return subscriber


def get_subscriber_by_token(db: Session, manage_token: str) -> Subscriber | None:
    return db.query(Subscriber).filter(Subscriber.manage_token == manage_token).first()


def manage_url(subscriber: Subscriber) -> str:
    return f"{settings.public_base_url().rstrip('/')}/manage/{subscriber.manage_token}"


def _send_manage_link_email(subscriber: Subscriber, subject: str, intro: str) -> None:
    link = manage_url(subscriber)
    text = f"{intro}\n\nManage your saved opportunities and alerts here:\n{link}\n"
    html = f"<p>{intro}</p><p><a href=\"{link}\">{link}</a></p>"
    message = EmailMessage(to=subscriber.email, subject=subject, html_body=html, text_body=text)
    get_email_sender().send(message)


def save_opportunity(db: Session, email: str, opportunity_id: int) -> SavedOpportunity | None:
    """Save an opportunity for this email. Returns None if the opportunity
    doesn't exist; is a no-op (returns the existing row) if already saved.
    """
    opportunity = db.query(Opportunity).filter(Opportunity.id == opportunity_id).first()
    if not opportunity:
        return None

    subscriber = get_or_create_subscriber(db, email)
    existing = (
        db.query(SavedOpportunity)
        .filter(
            SavedOpportunity.subscriber_id == subscriber.id,
            SavedOpportunity.opportunity_id == opportunity_id,
        )
        .first()
    )
    if existing:
        return existing

    saved = SavedOpportunity(subscriber_id=subscriber.id, opportunity_id=opportunity_id)
    db.add(saved)
    db.commit()
    db.refresh(saved)

    _send_manage_link_email(
        subscriber,
        subject="Opportunity saved",
        intro=f'You saved "{opportunity.title}".',
    )
    return saved


def unsave_opportunity(db: Session, manage_token: str, opportunity_id: int) -> bool:
    subscriber = get_subscriber_by_token(db, manage_token)
    if not subscriber:
        return False
    deleted = (
        db.query(SavedOpportunity)
        .filter(
            SavedOpportunity.subscriber_id == subscriber.id,
            SavedOpportunity.opportunity_id == opportunity_id,
        )
        .delete()
    )
    db.commit()
    return deleted > 0


def list_saved_opportunities(db: Session, manage_token: str) -> list[Opportunity] | None:
    """Returns None if the token doesn't match any subscriber."""
    subscriber = get_subscriber_by_token(db, manage_token)
    if not subscriber:
        return None
    return (
        db.query(Opportunity)
        .join(SavedOpportunity, SavedOpportunity.opportunity_id == Opportunity.id)
        .filter(SavedOpportunity.subscriber_id == subscriber.id)
        .order_by(SavedOpportunity.saved_at.desc())
        .all()
    )


def create_alert(
    db: Session,
    email: str,
    opportunity_type: str | None = None,
    field: str | None = None,
    location: str | None = None,
    keyword: str | None = None,
) -> AlertSubscription:
    subscriber = get_or_create_subscriber(db, email)
    alert = AlertSubscription(
        subscriber_id=subscriber.id,
        opportunity_type=opportunity_type,
        field=field,
        location=location,
        keyword=keyword,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    filters_desc = ", ".join(
        f"{label}: {value}"
        for label, value in [
            ("type", opportunity_type),
            ("field", field),
            ("location", location),
            ("keyword", keyword),
        ]
        if value
    ) or "all new opportunities"
    _send_manage_link_email(
        subscriber,
        subject="Alert created",
        intro=f"You'll be emailed weekly when new opportunities match: {filters_desc}.",
    )
    return alert


def list_alerts(db: Session, manage_token: str) -> list[AlertSubscription] | None:
    subscriber = get_subscriber_by_token(db, manage_token)
    if not subscriber:
        return None
    return (
        db.query(AlertSubscription)
        .filter(AlertSubscription.subscriber_id == subscriber.id)
        .order_by(AlertSubscription.created_at.desc())
        .all()
    )


def delete_alert(db: Session, manage_token: str, alert_id: int) -> bool:
    subscriber = get_subscriber_by_token(db, manage_token)
    if not subscriber:
        return False
    deleted = (
        db.query(AlertSubscription)
        .filter(AlertSubscription.id == alert_id, AlertSubscription.subscriber_id == subscriber.id)
        .delete()
    )
    db.commit()
    return deleted > 0


def _matching_opportunities(db: Session, alert: AlertSubscription, since: datetime):
    q = db.query(Opportunity).filter(Opportunity.scraped_at > since, Opportunity.is_active.is_(True))
    if alert.opportunity_type:
        q = q.filter(Opportunity.opportunity_type == alert.opportunity_type)
    if alert.field:
        q = q.filter(Opportunity.field == alert.field)
    if alert.location:
        q = q.filter(Opportunity.location.ilike(f"%{alert.location}%"))
    if alert.keyword:
        term = f"%{alert.keyword}%"
        q = q.filter(or_(Opportunity.title.ilike(term), Opportunity.description.ilike(term)))
    return q.order_by(Opportunity.scraped_at.desc()).all()


def run_alert_digest(db: Session) -> dict[str, int]:
    """For every alert subscription, email a digest of opportunities
    ingested since the subscriber's last notification (or since the alert
    was created, if never notified). Returns summary stats.
    """
    stats = {"alerts_checked": 0, "digests_sent": 0, "matches_total": 0}
    sender = get_email_sender()
    now = datetime.now(UTC)

    alerts = db.query(AlertSubscription).all()
    for alert in alerts:
        stats["alerts_checked"] += 1
        since = alert.last_notified_at or alert.created_at
        matches = _matching_opportunities(db, alert, since)
        if not matches:
            alert.last_notified_at = now
            continue

        subscriber = alert.subscriber
        lines = [f"- {opp.title} ({opp.url})" for opp in matches[:20]]
        text = (
            f"{len(matches)} new opportunity(ies) matching your alert:\n\n"
            + "\n".join(lines)
            + f"\n\nManage your alerts: {manage_url(subscriber)}\n"
        )
        html_items = "".join(f'<li><a href="{opp.url}">{opp.title}</a></li>' for opp in matches[:20])
        html = f"<p>{len(matches)} new opportunity(ies) matching your alert:</p><ul>{html_items}</ul>"

        sent = sender.send(
            EmailMessage(
                to=subscriber.email,
                subject=f"{len(matches)} new opportunities matching your alert",
                html_body=html,
                text_body=text,
            )
        )
        if sent:
            alert.last_notified_at = now
            stats["digests_sent"] += 1
            stats["matches_total"] += len(matches)

    db.commit()
    logger.info("Alert digest run complete: %s", stats)
    return stats
