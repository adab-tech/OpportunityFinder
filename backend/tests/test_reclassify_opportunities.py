from app.database import SessionLocal
from app.models import Opportunity
from scripts.reclassify_opportunities import apply_corrections, find_corrections

AFFECTED_SOURCE = "AfterSchool Africa"


def _make_row(db, **kwargs):
    defaults = dict(
        title="Placeholder",
        opportunity_type="scholarship",
        url=f"https://example.org/{kwargs.get('title', 'x')}",
        source_name=AFFECTED_SOURCE,
        is_active=True,
    )
    defaults.update(kwargs)
    row = Opportunity(**defaults)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class TestFindCorrections:
    def setup_method(self):
        self.db = SessionLocal()
        self.db.query(Opportunity).filter(Opportunity.source_name == AFFECTED_SOURCE).delete()
        self.db.commit()

    def teardown_method(self):
        self.db.query(Opportunity).filter(Opportunity.source_name == AFFECTED_SOURCE).delete()
        self.db.commit()
        self.db.close()

    def test_detects_mislabeled_row(self):
        row = _make_row(
            self.db,
            title="Global NGO Job Vacancy: Program Coordinator",
            opportunity_type="scholarship",  # wrong — old feed hardcoded this
            url="https://example.org/mislabeled-job",
        )
        corrections = find_corrections(self.db, sources=(AFFECTED_SOURCE,))
        ids = {c.id: c.new_type for c in corrections}
        assert row.id in ids
        assert ids[row.id] == "job"

    def test_correctly_labeled_row_is_untouched(self):
        row = _make_row(
            self.db,
            title="Fully Funded Scholarship for African Students",
            opportunity_type="scholarship",
            url="https://example.org/correctly-labeled",
        )
        corrections = find_corrections(self.db, sources=(AFFECTED_SOURCE,))
        ids = {c.id for c in corrections}
        assert row.id not in ids

    def test_ambiguous_title_never_downgrades_to_other(self):
        row = _make_row(
            self.db,
            title="Announcement About an Upcoming Program",
            opportunity_type="grant",
            url="https://example.org/ambiguous",
        )
        corrections = find_corrections(self.db, sources=(AFFECTED_SOURCE,))
        ids = {c.id for c in corrections}
        assert row.id not in ids  # "other" is never confident enough to override

    def test_unaffected_source_is_ignored(self):
        row = _make_row(
            self.db,
            title="Job Vacancy Mislabeled as Scholarship",
            opportunity_type="scholarship",
            source_name="ReliefWeb",
            url="https://example.org/unaffected-source",
        )
        corrections = find_corrections(self.db, sources=(AFFECTED_SOURCE,))
        ids = {c.id for c in corrections}
        assert row.id not in ids


class TestApplyCorrections:
    def setup_method(self):
        self.db = SessionLocal()
        self.db.query(Opportunity).filter(Opportunity.source_name == AFFECTED_SOURCE).delete()
        self.db.commit()

    def teardown_method(self):
        self.db.query(Opportunity).filter(Opportunity.source_name == AFFECTED_SOURCE).delete()
        self.db.commit()
        self.db.close()

    def test_dry_run_writes_nothing(self):
        row = _make_row(
            self.db,
            title="Job Vacancy: Regional Officer",
            opportunity_type="scholarship",
            url="https://example.org/dry-run-check",
        )
        find_corrections(self.db, sources=(AFFECTED_SOURCE,))  # dry run: never calls apply_corrections
        self.db.expire_all()
        refreshed = self.db.get(Opportunity, row.id)
        assert refreshed.opportunity_type == "scholarship"

    def test_apply_writes_the_correction(self):
        row = _make_row(
            self.db,
            title="Job Vacancy: Regional Officer",
            opportunity_type="scholarship",
            url="https://example.org/apply-check",
        )
        corrections = find_corrections(self.db, sources=(AFFECTED_SOURCE,))
        apply_corrections(self.db, corrections)

        self.db.expire_all()
        refreshed = self.db.get(Opportunity, row.id)
        assert refreshed.opportunity_type == "job"

    def test_apply_with_empty_corrections_is_a_no_op(self):
        apply_corrections(self.db, [])  # must not raise
