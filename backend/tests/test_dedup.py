from types import SimpleNamespace
from unittest.mock import patch

from app.database import SessionLocal
from app.models import Opportunity
from app.scrapers.dedup import normalize_title
from app.scrapers.rss_ingest import RssIngestor

_TEST_URL_PREFIX = "https://example.org/dedup-test-"


def _cleanup(db):
    db.query(Opportunity).filter(Opportunity.url.like(f"{_TEST_URL_PREFIX}%")).delete(
        synchronize_session=False
    )
    db.commit()


class TestNormalizeTitle:
    def test_lowercases_and_strips_punctuation(self):
        assert normalize_title("DAAD Scholarship 2026!") == "daad scholarship 2026"

    def test_collapses_whitespace(self):
        assert normalize_title("Fully   Funded    Scholarship") == "fully funded scholarship"

    def test_identical_after_normalization(self):
        a = normalize_title("DAAD 2026 Study Scholarships – Postgraduate Studies")
        b = normalize_title("daad 2026 study scholarships postgraduate studies")
        assert a == b

    def test_keeps_year_digits(self):
        # Deliberately does not strip years — a 2026 cohort and a 2027
        # cohort of the same program are genuinely different opportunities.
        assert "2026" in normalize_title("DAAD Scholarship 2026")
        assert normalize_title("DAAD Scholarship 2026") != normalize_title("DAAD Scholarship 2027")


class TestCrossSourceDedup:
    def setup_method(self):
        self.db = SessionLocal()
        _cleanup(self.db)

    def teardown_method(self):
        _cleanup(self.db)
        self.db.close()

    def _fake_feed(self, title, url):
        return SimpleNamespace(
            bozo=False,
            entries=[SimpleNamespace(title=title, link=url, summary="A description.")],
        )

    def test_same_title_different_url_is_skipped_as_duplicate(self):
        title = "DAAD 2026 Study Scholarships for Postgraduate Studies"
        url_a = f"{_TEST_URL_PREFIX}source-a"
        url_b = f"{_TEST_URL_PREFIX}source-b"
        spec = {
            "url": "https://example.org/feed.xml",
            "opportunity_type": "scholarship",
            "source_name": "Source A",
            "field": "STEM",
            "location": "International",
        }

        with patch("app.scrapers.rss_ingest.feedparser.parse", return_value=self._fake_feed(title, url_a)):
            with patch("app.scrapers.rss_ingest.RSS_FEEDS", [spec]):
                stats_a = RssIngestor(self.db).run(max_entries_per_feed=5)
        assert stats_a["saved"] == 1

        spec_b = {**spec, "source_name": "Source B"}
        with patch("app.scrapers.rss_ingest.feedparser.parse", return_value=self._fake_feed(title, url_b)):
            with patch("app.scrapers.rss_ingest.RSS_FEEDS", [spec_b]):
                stats_b = RssIngestor(self.db).run(max_entries_per_feed=5)

        assert stats_b["saved"] == 0
        assert stats_b["duplicates"] == 1
        # Only the first copy should exist
        rows = self.db.query(Opportunity).filter(Opportunity.url.like(f"{_TEST_URL_PREFIX}%")).all()
        assert len(rows) == 1

    def test_different_titles_are_both_saved(self):
        url_a = f"{_TEST_URL_PREFIX}distinct-a"
        url_b = f"{_TEST_URL_PREFIX}distinct-b"
        spec = {
            "url": "https://example.org/feed.xml",
            "opportunity_type": "scholarship",
            "source_name": "Source A",
            "field": "STEM",
            "location": "International",
        }

        with patch(
            "app.scrapers.rss_ingest.feedparser.parse",
            return_value=self._fake_feed("Completely Different Scholarship One", url_a),
        ):
            with patch("app.scrapers.rss_ingest.RSS_FEEDS", [spec]):
                RssIngestor(self.db).run(max_entries_per_feed=5)

        with patch(
            "app.scrapers.rss_ingest.feedparser.parse",
            return_value=self._fake_feed("Totally Unrelated Fellowship Two", url_b),
        ):
            with patch("app.scrapers.rss_ingest.RSS_FEEDS", [spec]):
                stats = RssIngestor(self.db).run(max_entries_per_feed=5)

        assert stats["saved"] == 1
        assert stats["duplicates"] == 0
