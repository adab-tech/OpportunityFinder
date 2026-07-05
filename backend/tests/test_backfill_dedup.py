from app.database import SessionLocal
from app.models import Opportunity
from scripts.backfill_dedup import (
    apply_duplicate_groups,
    apply_normalization_backfills,
    find_duplicate_groups,
    find_normalization_backfills,
)

_TEST_URL_PREFIX = "https://example.org/backfill-dedup-test-"


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


class TestFindNormalizationBackfills:
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

    def test_finds_row_missing_title_normalized(self):
        row = _make_row(self.db, title="Missing Normalized Title", title_normalized=None)
        backfills = find_normalization_backfills(self.db)
        ids = {b.id: b.title_normalized for b in backfills}
        assert row.id in ids
        assert ids[row.id] == "missing normalized title"

    def test_row_with_normalized_title_is_skipped(self):
        row = _make_row(self.db, title="Already Normalized", title_normalized="already normalized")
        backfills = find_normalization_backfills(self.db)
        ids = {b.id for b in backfills}
        assert row.id not in ids

    def test_apply_writes_normalized_title(self):
        row = _make_row(self.db, title="Apply Normalize Check", title_normalized=None)
        backfills = find_normalization_backfills(self.db)
        apply_normalization_backfills(self.db, backfills)
        self.db.expire_all()
        refreshed = self.db.get(Opportunity, row.id)
        assert refreshed.title_normalized == "apply normalize check"


class TestFindDuplicateGroups:
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

    def test_detects_duplicate_group_keeps_earliest(self):
        first = _make_row(
            self.db,
            title="Duplicate Test Scholarship",
            title_normalized="duplicate test scholarship",
            url=f"{_TEST_URL_PREFIX}first",
        )
        second = _make_row(
            self.db,
            title="Duplicate Test Scholarship",
            title_normalized="duplicate test scholarship",
            url=f"{_TEST_URL_PREFIX}second",
        )

        groups = find_duplicate_groups(self.db)
        matching = [g for g in groups if g.title_normalized == "duplicate test scholarship"]
        assert len(matching) == 1
        assert matching[0].keep_id == first.id
        assert matching[0].deactivate_ids == [second.id]

    def test_unique_title_is_not_a_duplicate_group(self):
        _make_row(
            self.db,
            title="Unique Solo Scholarship",
            title_normalized="unique solo scholarship",
            url=f"{_TEST_URL_PREFIX}solo",
        )
        groups = find_duplicate_groups(self.db)
        matching = [g for g in groups if g.title_normalized == "unique solo scholarship"]
        assert matching == []

    def test_inactive_row_does_not_count_toward_group(self):
        _make_row(
            self.db,
            title="Inactive Duplicate",
            title_normalized="inactive duplicate",
            url=f"{_TEST_URL_PREFIX}inactive-a",
            is_active=False,
        )
        _make_row(
            self.db,
            title="Inactive Duplicate",
            title_normalized="inactive duplicate",
            url=f"{_TEST_URL_PREFIX}inactive-b",
            is_active=True,
        )
        groups = find_duplicate_groups(self.db)
        matching = [g for g in groups if g.title_normalized == "inactive duplicate"]
        assert matching == []  # only one active row — not a duplicate group

    def test_apply_deactivates_the_later_duplicate(self):
        first = _make_row(
            self.db,
            title="Apply Dedup Check",
            title_normalized="apply dedup check",
            url=f"{_TEST_URL_PREFIX}apply-first",
        )
        second = _make_row(
            self.db,
            title="Apply Dedup Check",
            title_normalized="apply dedup check",
            url=f"{_TEST_URL_PREFIX}apply-second",
        )

        groups = find_duplicate_groups(self.db)
        apply_duplicate_groups(self.db, groups)

        self.db.expire_all()
        assert self.db.get(Opportunity, first.id).is_active is True
        assert self.db.get(Opportunity, second.id).is_active is False

    def test_apply_with_empty_list_is_a_no_op(self):
        apply_duplicate_groups(self.db, [])  # must not raise
