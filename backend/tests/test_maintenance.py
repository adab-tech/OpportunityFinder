from datetime import date, timedelta

from app.database import SessionLocal
from app.models import Opportunity
from app.services.maintenance import deactivate_expired_opportunities

_TEST_URL_PREFIX = "https://example.org/maintenance-test-"


def _make_row(db, **kwargs):
    defaults = dict(
        title="Placeholder",
        opportunity_type="scholarship",
        source_name="Test Source",
        is_active=True,
    )
    defaults.update(kwargs)
    defaults.setdefault("url", _TEST_URL_PREFIX + defaults["title"][:30])
    row = Opportunity(**defaults)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class TestDeactivateExpiredOpportunities:
    def setup_method(self):
        self.db = SessionLocal()
        self.db.query(Opportunity).filter(Opportunity.url.like(f"{_TEST_URL_PREFIX}%")).delete(
            synchronize_session=False
        )
        self.db.commit()

    def teardown_method(self):
        self.db.query(Opportunity).filter(Opportunity.url.like(f"{_TEST_URL_PREFIX}%")).delete(
            synchronize_session=False
        )
        self.db.commit()
        self.db.close()

    def test_deactivates_row_with_past_deadline(self):
        row = _make_row(
            self.db,
            title="Past Deadline Grant",
            deadline_at=date.today() - timedelta(days=1),
        )
        stats = deactivate_expired_opportunities(self.db)
        self.db.expire_all()
        assert self.db.get(Opportunity, row.id).is_active is False
        assert stats["deactivated_past_deadline"] >= 1

    def test_keeps_row_with_future_deadline_active(self):
        row = _make_row(
            self.db,
            title="Future Deadline Grant",
            deadline_at=date.today() + timedelta(days=30),
        )
        deactivate_expired_opportunities(self.db)
        self.db.expire_all()
        assert self.db.get(Opportunity, row.id).is_active is True

    def test_deactivates_undated_row_with_stale_title_year(self):
        stale_year = date.today().year - 3
        row = _make_row(
            self.db,
            title=f"Old Recruitment Program {stale_year}",
            deadline_at=None,
        )
        stats = deactivate_expired_opportunities(self.db)
        self.db.expire_all()
        assert self.db.get(Opportunity, row.id).is_active is False
        assert stats["deactivated_stale_title"] >= 1

    def test_keeps_undated_row_with_no_year_active(self):
        row = _make_row(self.db, title="Evergreen Opportunity No Year", deadline_at=None)
        deactivate_expired_opportunities(self.db)
        self.db.expire_all()
        assert self.db.get(Opportunity, row.id).is_active is True

    def test_already_inactive_row_is_left_alone(self):
        row = _make_row(
            self.db,
            title="Already Inactive",
            deadline_at=date.today() - timedelta(days=1),
            is_active=False,
        )
        deactivate_expired_opportunities(self.db)
        self.db.expire_all()
        assert self.db.get(Opportunity, row.id).is_active is False
