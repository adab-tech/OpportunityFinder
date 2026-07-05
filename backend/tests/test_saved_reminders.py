from datetime import UTC, datetime, timedelta

from app.database import SessionLocal
from app.models import Opportunity, SavedOpportunity, Subscriber
from app.services import subscribers as svc

_TEST_EMAIL = "reminder-test@example.org"
_TEST_URL_PREFIX = "https://example.org/reminder-test-"


def _cleanup(db):
    db.query(SavedOpportunity).filter(
        SavedOpportunity.subscriber_id.in_(
            db.query(Subscriber.id).filter(Subscriber.email == _TEST_EMAIL)
        )
    ).delete(synchronize_session=False)
    db.query(Subscriber).filter(Subscriber.email == _TEST_EMAIL).delete()
    db.query(Opportunity).filter(Opportunity.url.like(f"{_TEST_URL_PREFIX}%")).delete(
        synchronize_session=False
    )
    db.commit()


def _make_saved(db, deadline_at, reminder_sent_at=None, url_suffix="a"):
    opp = Opportunity(
        title=f"Reminder Test Opportunity {url_suffix}",
        opportunity_type="scholarship",
        url=f"{_TEST_URL_PREFIX}{url_suffix}",
        deadline="some date",
        deadline_at=deadline_at,
        source_name="Test",
        is_active=True,
    )
    db.add(opp)
    db.commit()
    db.refresh(opp)

    subscriber = svc.get_or_create_subscriber(db, _TEST_EMAIL)
    saved = SavedOpportunity(
        subscriber_id=subscriber.id, opportunity_id=opp.id, reminder_sent_at=reminder_sent_at
    )
    db.add(saved)
    db.commit()
    db.refresh(saved)
    return saved


class TestRunSavedDeadlineReminders:
    def setup_method(self):
        self.db = SessionLocal()
        _cleanup(self.db)
        self.today = datetime.now(UTC).date()

    def teardown_method(self):
        _cleanup(self.db)
        self.db.close()

    def test_reminds_when_deadline_within_horizon(self):
        saved = _make_saved(self.db, deadline_at=self.today + timedelta(days=2), url_suffix="soon")
        stats = svc.run_saved_deadline_reminders(self.db)
        assert stats["reminders_sent"] >= 1
        self.db.refresh(saved)
        assert saved.reminder_sent_at is not None

    def test_no_reminder_when_deadline_far_away(self):
        saved = _make_saved(self.db, deadline_at=self.today + timedelta(days=30), url_suffix="far")
        svc.run_saved_deadline_reminders(self.db)
        self.db.refresh(saved)
        assert saved.reminder_sent_at is None

    def test_no_reminder_when_deadline_already_passed(self):
        saved = _make_saved(self.db, deadline_at=self.today - timedelta(days=1), url_suffix="passed")
        svc.run_saved_deadline_reminders(self.db)
        self.db.refresh(saved)
        assert saved.reminder_sent_at is None

    def test_no_reminder_when_no_deadline_at(self):
        saved = _make_saved(self.db, deadline_at=None, url_suffix="nodate")
        svc.run_saved_deadline_reminders(self.db)
        self.db.refresh(saved)
        assert saved.reminder_sent_at is None

    def test_does_not_remind_twice(self):
        already_reminded_at = datetime.now(UTC) - timedelta(days=1)
        saved = _make_saved(
            self.db,
            deadline_at=self.today + timedelta(days=1),
            reminder_sent_at=already_reminded_at,
            url_suffix="already-reminded",
        )
        stats = svc.run_saved_deadline_reminders(self.db)
        self.db.refresh(saved)
        # Should not have been touched by this run — already reminded.
        # SQLite returns naive datetimes, so strip tzinfo from both sides
        # before comparing to avoid a tz-aware-vs-naive comparison error
        # unrelated to the behavior under test.
        assert saved.reminder_sent_at.replace(tzinfo=None) == already_reminded_at.replace(tzinfo=None)
        assert stats["checked"] == 0  # excluded from the query entirely (reminder_sent_at is set)

    def test_deadline_exactly_today_is_reminded(self):
        saved = _make_saved(self.db, deadline_at=self.today, url_suffix="today")
        svc.run_saved_deadline_reminders(self.db)
        self.db.refresh(saved)
        assert saved.reminder_sent_at is not None

    def test_deadline_exactly_at_horizon_boundary_is_reminded(self):
        saved = _make_saved(self.db, deadline_at=self.today + timedelta(days=3), url_suffix="boundary")
        svc.run_saved_deadline_reminders(self.db)
        self.db.refresh(saved)
        assert saved.reminder_sent_at is not None

    def test_deadline_one_day_past_horizon_is_not_reminded(self):
        saved = _make_saved(self.db, deadline_at=self.today + timedelta(days=4), url_suffix="past-horizon")
        svc.run_saved_deadline_reminders(self.db)
        self.db.refresh(saved)
        assert saved.reminder_sent_at is None
