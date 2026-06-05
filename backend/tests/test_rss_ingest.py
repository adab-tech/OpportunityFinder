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
