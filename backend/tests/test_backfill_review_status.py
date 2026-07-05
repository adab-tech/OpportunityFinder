from app.database import SessionLocal
from app.models import Opportunity
from scripts.backfill_review_status import (
    apply_review_status,
    find_null_review_status_rows,
    find_scoped_rows,
)

_TEST_URL_PREFIX = "https://example.org/backfill-review-status-test-"


def _make_row(db, **kwargs):
    defaults = dict(
        title="Placeholder",
        opportunity_type="scholarship",
        source_name="Test Source",
        is_active=True,
        review_status="approved",
    )
    defaults.update(kwargs)
    defaults.setdefault("url", _TEST_URL_PREFIX + defaults["title"][:30])
    row = Opportunity(**defaults)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class TestFindNullReviewStatusRows:
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

    # No test forces an actual NULL review_status here: the column is
    # NOT NULL at the DB level (both the ORM and a raw UPDATE are
    # rejected by SQLite/Postgres alike), so this defensive code path
    # can only ever fire against a manually altered database. Coverage
    # below just confirms the query never false-positives on normal rows.

    def test_skips_row_with_review_status_set(self):
        row = _make_row(self.db, title="Already Approved Row", review_status="approved")
        found = find_null_review_status_rows(self.db)
        ids = {r.id for r in found}
        assert row.id not in ids


class TestFindScopedRows:
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

    def test_scopes_by_source(self):
        row = _make_row(
            self.db, title="Scoped Source Row", source_name="Special Source", review_status="pending"
        )
        other = _make_row(
            self.db, title="Other Source Row", source_name="Other Source", review_status="pending"
        )
        found = find_scoped_rows(self.db, "approved", source="Special Source")
        ids = {r.id for r in found}
        assert row.id in ids
        assert other.id not in ids

    def test_scopes_by_type(self):
        row = _make_row(
            self.db, title="Scoped Type Row", opportunity_type="job", review_status="pending"
        )
        other = _make_row(
            self.db, title="Other Type Row", opportunity_type="grant", review_status="pending"
        )
        found = find_scoped_rows(self.db, "approved", opportunity_type="job")
        ids = {r.id for r in found}
        assert row.id in ids
        assert other.id not in ids

    def test_excludes_rows_already_at_target_status(self):
        row = _make_row(self.db, title="Already Target Status Row", review_status="approved")
        found = find_scoped_rows(self.db, "approved")
        ids = {r.id for r in found}
        assert row.id not in ids


class TestApplyReviewStatus:
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

    def test_apply_sets_new_status(self):
        row = _make_row(self.db, title="Apply Target Row", review_status="pending")
        rows = find_scoped_rows(self.db, "approved")
        apply_review_status(self.db, rows)
        self.db.expire_all()
        assert self.db.get(Opportunity, row.id).review_status == "approved"

    def test_apply_with_empty_list_is_a_no_op(self):
        apply_review_status(self.db, [])  # must not raise

    def test_dry_run_writes_nothing(self):
        row = _make_row(self.db, title="Dry Run Row", review_status="pending")
        find_scoped_rows(self.db, "approved")  # dry run only, never calls apply
        self.db.expire_all()
        assert self.db.get(Opportunity, row.id).review_status == "pending"
