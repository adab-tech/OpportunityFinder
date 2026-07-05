"""Regression tests for the admin moderation queue (app/routes/moderation.py).

Covers: pending opportunities never leak into public endpoints, the
admin-key gate (unset -> 503, wrong key -> 401), approve/reject/bulk-approve
transitions, and that reject also deactivates the row.
"""

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Opportunity
from app.scrapers.opportunity_scraper import OpportunityScraper
from app.scrapers.rss_ingest import RssIngestor

client = TestClient(app)

_TEST_URL_PREFIX = "https://example.org/moderation-test-"


def _cleanup(db):
    db.query(Opportunity).filter(Opportunity.url.like(f"{_TEST_URL_PREFIX}%")).delete(
        synchronize_session=False
    )
    db.commit()


def _make_pending(db, suffix: str, **overrides) -> Opportunity:
    defaults = dict(
        title=f"Pending Test Opportunity {suffix}",
        opportunity_type="grant",
        url=f"{_TEST_URL_PREFIX}{suffix}",
        source_name="Test Web Search",
        is_active=True,
        review_status="pending",
    )
    defaults.update(overrides)
    opp = Opportunity(**defaults)
    db.add(opp)
    db.commit()
    db.refresh(opp)
    return opp


class TestIngestSetsReviewStatus:
    def setup_method(self):
        self.db = SessionLocal()
        _cleanup(self.db)

    def teardown_method(self):
        _cleanup(self.db)
        self.db.close()

    def test_rss_ingest_sets_approved(self):
        url = f"{_TEST_URL_PREFIX}rss-approved"
        fake_feed = SimpleNamespace(
            bozo=False,
            entries=[
                SimpleNamespace(
                    title="RSS Sourced Fellowship Moderation Test",
                    link=url,
                    summary="A curated-feed opportunity.",
                )
            ],
        )
        spec = {
            "url": "https://example.org/moderation-test-feed.xml",
            "opportunity_type": "fellowship",
            "source_name": "Example",
            "field": "STEM",
            "location": "International",
        }
        with patch("app.scrapers.rss_ingest.feedparser.parse", return_value=fake_feed):
            with patch("app.scrapers.rss_ingest.RSS_FEEDS", [spec]):
                RssIngestor(self.db).run(max_entries_per_feed=5)

        row = self.db.query(Opportunity).filter(Opportunity.url == url).first()
        assert row is not None
        assert row.review_status == "approved"

    def test_opportunity_scraper_sets_pending(self):
        scraper = OpportunityScraper(self.db)
        data = {
            "title": "Web Discovered Scholarship Moderation Test",
            "description": "A scholarship found via web search.",
            "opportunity_type": "scholarship",
            "field": "STEM",
            "location": "International",
            "deadline": None,
            "deadline_at": date.today() + timedelta(days=60),
            "url": f"{_TEST_URL_PREFIX}scraper-pending",
            "source_name": "example.org",
        }
        assert scraper._save(data) is True

        row = self.db.query(Opportunity).filter(Opportunity.url == data["url"]).first()
        assert row is not None
        assert row.review_status == "pending"


class TestModerationAdminGate:
    def setup_method(self):
        self.db = SessionLocal()
        _cleanup(self.db)

    def teardown_method(self):
        _cleanup(self.db)
        self.db.close()

    def test_pending_list_requires_admin_key_when_unconfigured(self):
        response = client.get("/api/v1/admin/moderation/pending")
        assert response.status_code == 503

    def test_pending_list_rejects_wrong_key(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "ADMIN_API_KEY", "correct-key")
        response = client.get(
            "/api/v1/admin/moderation/pending", headers={"X-Admin-Key": "wrong-key"}
        )
        assert response.status_code == 401

    def test_approve_requires_admin_key(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "ADMIN_API_KEY", "correct-key")
        opp = _make_pending(self.db, "gate-approve")
        response = client.post(f"/api/v1/admin/moderation/{opp.id}/approve")
        assert response.status_code == 401  # ADMIN_API_KEY configured but header missing -> unauthorized

    def test_bulk_approve_requires_admin_key(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "ADMIN_API_KEY", "correct-key")
        response = client.post(
            "/api/v1/admin/moderation/bulk-approve",
            json={"ids": [1]},
            headers={"X-Admin-Key": "wrong-key"},
        )
        assert response.status_code == 401


class TestPendingNeverPublic:
    def setup_method(self):
        self.db = SessionLocal()
        _cleanup(self.db)

    def teardown_method(self):
        _cleanup(self.db)
        self.db.close()

    def test_pending_excluded_from_public_listing(self):
        _make_pending(self.db, "hidden-from-listing")
        response = client.get("/api/v1/opportunities/", params={"per_page": 100})
        assert response.status_code == 200
        titles = [row["title"] for row in response.json()["data"]]
        assert "Pending Test Opportunity hidden-from-listing" not in titles

    def test_pending_excluded_from_single_lookup(self):
        opp = _make_pending(self.db, "hidden-from-lookup")
        response = client.get(f"/api/v1/opportunities/{opp.id}")
        assert response.status_code == 404

    def test_rejected_excluded_from_public_listing(self):
        opp = _make_pending(self.db, "hidden-rejected", review_status="rejected")
        response = client.get(f"/api/v1/opportunities/{opp.id}")
        assert response.status_code == 404


class TestModerationActions:
    def setup_method(self):
        self.db = SessionLocal()
        _cleanup(self.db)
        from app.config import settings

        self._prior_key = settings.ADMIN_API_KEY
        settings.ADMIN_API_KEY = "test-admin-key"

    def teardown_method(self):
        from app.config import settings

        settings.ADMIN_API_KEY = self._prior_key
        _cleanup(self.db)
        self.db.close()

    def _headers(self):
        return {"X-Admin-Key": "test-admin-key"}

    def test_pending_list_returns_pending_rows(self):
        opp = _make_pending(self.db, "listed")
        response = client.get("/api/v1/admin/moderation/pending", headers=self._headers())
        assert response.status_code == 200
        body = response.json()
        ids = [row["id"] for row in body["data"]]
        assert opp.id in ids

    def test_approve_transitions_status_and_makes_publicly_visible(self):
        opp = _make_pending(self.db, "approve-me")
        response = client.post(
            f"/api/v1/admin/moderation/{opp.id}/approve", headers=self._headers()
        )
        assert response.status_code == 200
        assert response.json()["review_status"] == "approved"

        public = client.get(f"/api/v1/opportunities/{opp.id}")
        assert public.status_code == 200

    def test_reject_transitions_status_and_deactivates(self):
        opp = _make_pending(self.db, "reject-me")
        response = client.post(
            f"/api/v1/admin/moderation/{opp.id}/reject", headers=self._headers()
        )
        assert response.status_code == 200
        assert response.json()["review_status"] == "rejected"

        self.db.refresh(opp)
        assert opp.is_active is False

        public = client.get(f"/api/v1/opportunities/{opp.id}")
        assert public.status_code == 404

    def test_approve_unknown_id_returns_404(self):
        response = client.post(
            "/api/v1/admin/moderation/999999999/approve", headers=self._headers()
        )
        assert response.status_code == 404

    def test_bulk_approve_updates_all_ids(self):
        opp1 = _make_pending(self.db, "bulk-1")
        opp2 = _make_pending(self.db, "bulk-2")
        response = client.post(
            "/api/v1/admin/moderation/bulk-approve",
            json={"ids": [opp1.id, opp2.id]},
            headers=self._headers(),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["updated"] == 2
        assert sorted(body["ids"]) == sorted([opp1.id, opp2.id])

        self.db.refresh(opp1)
        self.db.refresh(opp2)
        assert opp1.review_status == "approved"
        assert opp2.review_status == "approved"

    def test_bulk_approve_ignores_unknown_ids(self):
        opp = _make_pending(self.db, "bulk-with-unknown")
        response = client.post(
            "/api/v1/admin/moderation/bulk-approve",
            json={"ids": [opp.id, 999999999]},
            headers=self._headers(),
        )
        assert response.status_code == 200
        assert response.json()["updated"] == 1
