from app.database import SessionLocal
from app.models import Opportunity
from scripts.backfill_quality import apply_deactivations, find_low_quality_active_rows

_TEST_URL_PREFIX = "https://example.org/backfill-quality-test-"


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


class TestFindLowQualityActiveRows:
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

    def test_finds_low_quality_title_row(self):
        row = _make_row(self.db, title="Breadcrumb")
        found = find_low_quality_active_rows(self.db)
        ids = {r.id for r in found}
        assert row.id in ids

    def test_skips_legitimate_title_row(self):
        row = _make_row(self.db, title="Fulbright Foreign Student Program")
        found = find_low_quality_active_rows(self.db)
        ids = {r.id for r in found}
        assert row.id not in ids

    def test_skips_already_inactive_row(self):
        row = _make_row(self.db, title="Breadcrumb", is_active=False)
        found = find_low_quality_active_rows(self.db)
        ids = {r.id for r in found}
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
        row = _make_row(self.db, title="Breadcrumb")
        find_low_quality_active_rows(self.db)  # dry run: never calls apply_deactivations
        self.db.expire_all()
        assert self.db.get(Opportunity, row.id).is_active is True

    def test_apply_deactivates(self):
        row = _make_row(self.db, title="Breadcrumb")
        found = find_low_quality_active_rows(self.db)
        apply_deactivations(self.db, found)
        self.db.expire_all()
        assert self.db.get(Opportunity, row.id).is_active is False

    def test_apply_with_empty_list_is_a_no_op(self):
        apply_deactivations(self.db, [])  # must not raise
