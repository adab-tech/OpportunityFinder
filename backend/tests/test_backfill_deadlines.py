from app.database import SessionLocal
from app.models import Opportunity
from scripts.backfill_deadlines import apply_backfills, find_backfills

_TEST_URL_PREFIX = "https://example.org/backfill-test-"


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


class TestFindBackfills:
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

    def test_finds_extractable_deadline_in_description(self):
        row = _make_row(
            self.db,
            title="Scholarship With Hidden Deadline",
            description="Application Deadline: September 23rd, 2026. Apply now.",
            deadline=None,
        )
        backfills = find_backfills(self.db)
        ids = {b.id: b.deadline for b in backfills}
        assert row.id in ids
        assert ids[row.id] == "September 23rd, 2026"

    def test_row_with_existing_deadline_is_never_touched(self):
        row = _make_row(
            self.db,
            title="Already Has A Deadline",
            description="Application Deadline: 1 May 2026.",
            deadline="Already Set",
        )
        backfills = find_backfills(self.db)
        ids = {b.id for b in backfills}
        assert row.id not in ids

    def test_row_with_no_extractable_deadline_is_skipped(self):
        row = _make_row(
            self.db,
            title="No Deadline Mentioned Anywhere",
            description="Just a general announcement about a program.",
            deadline=None,
        )
        backfills = find_backfills(self.db)
        ids = {b.id for b in backfills}
        assert row.id not in ids


class TestApplyBackfills:
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
            self.db,
            title="Dry Run Deadline Check",
            description="Deadline: 1 May 2026.",
            deadline=None,
        )
        find_backfills(self.db)  # dry run only, never calls apply_backfills
        self.db.expire_all()
        refreshed = self.db.get(Opportunity, row.id)
        assert refreshed.deadline is None

    def test_apply_writes_the_deadline(self):
        row = _make_row(
            self.db,
            title="Apply Deadline Check",
            description="Deadline: 1 May 2026.",
            deadline=None,
        )
        backfills = find_backfills(self.db)
        apply_backfills(self.db, backfills)

        self.db.expire_all()
        refreshed = self.db.get(Opportunity, row.id)
        assert refreshed.deadline == "1 May 2026"

    def test_apply_with_empty_list_is_a_no_op(self):
        apply_backfills(self.db, [])  # must not raise
