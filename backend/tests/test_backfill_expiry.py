from datetime import date, timedelta

from app.database import SessionLocal
from app.models import Opportunity
from scripts.backfill_expiry import apply_deactivations, find_expired_active_rows

_TEST_URL_PREFIX = "https://example.org/backfill-expiry-test-"


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


class TestFindExpiredActiveRows:
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

    def test_finds_past_deadline_row(self):
        row = _make_row(
            self.db, title="Past Deadline Row", deadline_at=date.today() - timedelta(days=5)
        )
        expired = find_expired_active_rows(self.db)
        ids = {e.id: e.reason for e in expired}
        assert row.id in ids
        assert ids[row.id] == "past_deadline"

    def test_finds_stale_title_year_row(self):
        stale_year = date.today().year - 4
        row = _make_row(self.db, title=f"Old Program {stale_year}", deadline_at=None)
        expired = find_expired_active_rows(self.db)
        ids = {e.id: e.reason for e in expired}
        assert row.id in ids
        assert ids[row.id] == "stale_title_year"

    def test_skips_future_deadline_row(self):
        row = _make_row(
            self.db, title="Future Deadline Row", deadline_at=date.today() + timedelta(days=10)
        )
        expired = find_expired_active_rows(self.db)
        ids = {e.id for e in expired}
        assert row.id not in ids

    def test_skips_already_inactive_row(self):
        row = _make_row(
            self.db,
            title="Already Inactive Row",
            deadline_at=date.today() - timedelta(days=5),
            is_active=False,
        )
        expired = find_expired_active_rows(self.db)
        ids = {e.id for e in expired}
        assert row.id not in ids


class TestApplyDeactivations:
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

    def test_dry_run_writes_nothing(self):
        row = _make_row(
            self.db, title="Dry Run Expiry Check", deadline_at=date.today() - timedelta(days=1)
        )
        find_expired_active_rows(self.db)  # dry run: never calls apply_deactivations
        self.db.expire_all()
        assert self.db.get(Opportunity, row.id).is_active is True

    def test_apply_deactivates(self):
        row = _make_row(
            self.db, title="Apply Expiry Check", deadline_at=date.today() - timedelta(days=1)
        )
        expired = find_expired_active_rows(self.db)
        apply_deactivations(self.db, expired)
        self.db.expire_all()
        assert self.db.get(Opportunity, row.id).is_active is False

    def test_apply_with_empty_list_is_a_no_op(self):
        apply_deactivations(self.db, [])  # must not raise
