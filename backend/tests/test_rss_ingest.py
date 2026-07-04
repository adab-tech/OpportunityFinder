from types import SimpleNamespace
from unittest.mock import patch

from app.database import SessionLocal
from app.models import Opportunity
from app.scrapers.rss_ingest import RssIngestor


def _fake_feed():
    return SimpleNamespace(
        bozo=False,
        entries=[
            SimpleNamespace(
                title="Test Fellowship 2026",
                link="https://example.org/fellowship-2026",
                summary="A short description of the program.",
            )
        ],
    )


def test_rss_ingest_saves_new_entry():
    db = SessionLocal()
    try:
        url = "https://example.org/fellowship-2026"
        db.query(Opportunity).filter(Opportunity.url == url).delete()
        db.commit()

        with patch("app.scrapers.rss_ingest.feedparser.parse", return_value=_fake_feed()):
            with patch("app.scrapers.rss_ingest.RSS_FEEDS", [
                {
                    "url": "https://example.org/feed.xml",
                    "opportunity_type": "fellowship",
                    "source_name": "Example",
                    "field": "STEM",
                    "location": "International",
                }
            ]):
                stats = RssIngestor(db).run(max_entries_per_feed=5)

        assert stats["saved"] >= 1
        row = db.query(Opportunity).filter(Opportunity.url == url).first()
        assert row is not None
        assert row.opportunity_type == "fellowship"
    finally:
        db.close()


def _fake_mixed_feed():
    return SimpleNamespace(
        bozo=False,
        entries=[
            SimpleNamespace(
                title="Acme Grant: Up to $50,000 for Community Organizations",
                link="https://example.org/mixed-grant",
                summary="Funding for grassroots groups.",
            ),
            SimpleNamespace(
                title="Communications Officer (Remote) — Global NGO Vacancy",
                link="https://example.org/mixed-job",
                summary="Full-time remote position.",
            ),
            SimpleNamespace(
                title="Fully Funded Scholarship for Graduate Students",
                link="https://example.org/mixed-scholarship",
                summary="Covers tuition and stipend.",
            ),
        ],
    )


def test_mixed_feed_classifies_each_entry_by_title():
    db = SessionLocal()
    try:
        urls = [
            "https://example.org/mixed-grant",
            "https://example.org/mixed-job",
            "https://example.org/mixed-scholarship",
        ]
        db.query(Opportunity).filter(Opportunity.url.in_(urls)).delete(synchronize_session=False)
        db.commit()

        with patch("app.scrapers.rss_ingest.feedparser.parse", return_value=_fake_mixed_feed()):
            with patch("app.scrapers.rss_ingest.RSS_FEEDS", [
                {
                    "url": "https://example.org/mixed-feed.xml",
                    "opportunity_type": "mixed",
                    "source_name": "Example Mixed",
                    "field": "International Development",
                    "location": "International",
                }
            ]):
                stats = RssIngestor(db).run(max_entries_per_feed=10)

        assert stats["saved"] == 3
        by_url = {
            row.url: row.opportunity_type
            for row in db.query(Opportunity).filter(Opportunity.url.in_(urls)).all()
        }
        assert by_url["https://example.org/mixed-grant"] == "grant"
        assert by_url["https://example.org/mixed-job"] == "job"
        assert by_url["https://example.org/mixed-scholarship"] == "scholarship"
    finally:
        db.close()
