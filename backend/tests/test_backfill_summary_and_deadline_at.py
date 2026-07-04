from datetime import date

from app.database import SessionLocal
from app.models import Opportunity
from scripts.backfill_summary_and_deadline_at import apply_backfills, find_backfills

_TEST_URL_PREFIX = "https://example.org/backfill-summary-test-"


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

    def test_finds_row_missing_summary(self):
        row = _make_row(self.db, title="Missing Summary Row", summary=None)
        backfills = find_backfills(self.db)
        ids = {b.id: b for b in backfills}
        assert row.id in ids
        assert ids[row.id].new_summary is not None

    def test_finds_row_missing_deadline_at(self):
        row = _make_row(self.db, title="Has Deadline Text", deadline="1 May 2026", deadline_at=None,
                         summary="already has one")
        backfills = find_backfills(self.db)
        ids = {b.id: b for b in backfills}
        assert row.id in ids
        assert ids[row.id].new_deadline_at == "2026-05-01"

    def test_row_with_both_already_set_is_skipped(self):
        row = _make_row(
            self.db,
            title="Fully Backfilled Row",
            summary="Already summarized.",
            deadline="1 May 2026",
            deadline_at=date(2026, 5, 1),
        )
        backfills = find_backfills(self.db)
        ids = {b.id for b in backfills}
        assert row.id not in ids

    def test_row_with_no_deadline_text_skips_deadline_at(self):
        row = _make_row(self.db, title="No Deadline Text", deadline=None, deadline_at=None, summary="x")
        backfills = find_backfills(self.db)
        ids = {b.id: b for b in backfills}
        assert row.id not in ids  # summary already set, no deadline text to parse


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

    def test_apply_writes_summary_and_deadline_at(self):
        row = _make_row(
            self.db,
            title="Apply Check Row",
            opportunity_type="grant",
            deadline="1 May 2026",
            deadline_at=None,
        )
        backfills = find_backfills(self.db)
        apply_backfills(self.db, backfills)

        self.db.expire_all()
        refreshed = self.db.get(Opportunity, row.id)
        assert refreshed.summary is not None
        assert refreshed.deadline_at == date(2026, 5, 1)

    def test_apply_with_empty_list_is_a_no_op(self):
        apply_backfills(self.db, [])  # must not raise
