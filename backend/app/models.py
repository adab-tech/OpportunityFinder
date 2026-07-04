import secrets

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


def _generate_manage_token() -> str:
    """URL-safe token identifying a subscriber without a password."""
    return secrets.token_urlsafe(32)


class Opportunity(Base):
    __tablename__ = "opportunities"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    # Original one-line synopsis we generate — the primary text shown on
    # cards, so people aren't just reading copy-pasted third-party text.
    # See app/scrapers/synopsis.py.
    summary = Column(String(300))
    # scholarship | fellowship | grant | job | other
    opportunity_type = Column(String(50), nullable=False, index=True)
    # STEM, Medicine, Arts, etc.
    field = Column(String(200), index=True)
    location = Column(String(200))
    deadline = Column(String(100))
    # Parsed from `deadline` when possible (see deadline_utils.parse_deadline_date)
    # so the frontend can show a day countdown instead of making people
    # read and calculate it themselves. Null when the deadline is "Rolling"
    # or couldn't be confidently parsed.
    deadline_at = Column(Date, nullable=True, index=True)
    url = Column(String(2000), unique=True, nullable=False)
    source_name = Column(String(200))
    tags = Column(String(500))           # comma-separated
    is_active = Column(Boolean, default=True)
    scraped_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Opportunity {self.title[:60]}>"


class Subscriber(Base):
    """A user identified only by email — no password. Everything the
    subscriber can manage (saved opportunities, alert subscriptions) is
    reached through their unique, unguessable manage_token (emailed to
    them), never through a login form.
    """

    __tablename__ = "subscribers"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(320), unique=True, nullable=False, index=True)
    manage_token = Column(String(64), unique=True, nullable=False, default=_generate_manage_token, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    saved_opportunities = relationship(
        "SavedOpportunity", back_populates="subscriber", cascade="all, delete-orphan"
    )
    alert_subscriptions = relationship(
        "AlertSubscription", back_populates="subscriber", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Subscriber {self.email}>"


class SavedOpportunity(Base):
    __tablename__ = "saved_opportunities"
    __table_args__ = (
        UniqueConstraint("subscriber_id", "opportunity_id", name="uq_saved_subscriber_opportunity"),
    )

    id = Column(Integer, primary_key=True, index=True)
    subscriber_id = Column(
        Integer, ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    opportunity_id = Column(
        Integer, ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    saved_at = Column(DateTime(timezone=True), server_default=func.now())

    subscriber = relationship("Subscriber", back_populates="saved_opportunities")
    opportunity = relationship("Opportunity")


class AlertSubscription(Base):
    """A saved search: notify this subscriber by email when new
    opportunities matching these (optional) filters are ingested.
    """

    __tablename__ = "alert_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    subscriber_id = Column(
        Integer, ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    opportunity_type = Column(String(50), nullable=True)
    field = Column(String(200), nullable=True)
    location = Column(String(200), nullable=True)
    keyword = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_notified_at = Column(DateTime(timezone=True), nullable=True)

    subscriber = relationship("Subscriber", back_populates="alert_subscriptions")


class AnalyticsEvent(Base):
    """Minimal, self-hosted visitor analytics — no third-party tracker,
    no cookies, no PII. `client_id` is a random UUID the frontend
    generates and stores in localStorage purely to distinguish repeat
    visitors from new ones in aggregate counts; it identifies a browser,
    never a person.
    """

    __tablename__ = "analytics_events"

    id = Column(Integer, primary_key=True, index=True)
    # pageview | search | filter_type | filter_field | filter_location |
    # apply_click | save_click | alert_create
    event_type = Column(String(50), nullable=False, index=True)
    client_id = Column(String(64), nullable=False, index=True)
    value = Column(String(200), nullable=True)  # search term, filter value, etc.
    opportunity_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
