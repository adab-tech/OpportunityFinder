"""Regression tests for admin listing management
(app/routes/admin_listings.py) — search/list ALL opportunities
regardless of status, edit any field, deactivate/reactivate.
"""

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Opportunity
from app.security import create_session_token

client = TestClient(app)

_TEST_URL_PREFIX = "https://example.org/admin-listings-test-"


def _cleanup(db):
    db.query(Opportunity).filter(Opportunity.url.like(f"{_TEST_URL_PREFIX}%")).delete(
        synchronize_session=False
    )
    db.commit()


def _make_row(db, suffix: str, **overrides) -> Opportunity:
    defaults = dict(
        title=f"Admin Listings Test {suffix}",
        opportunity_type="grant",
        url=f"{_TEST_URL_PREFIX}{suffix}",
        source_name="Test Source",
        is_active=True,
        review_status="approved",
    )
    defaults.update(overrides)
    opp = Opportunity(**defaults)
    db.add(opp)
    db.commit()
    db.refresh(opp)
    return opp


class TestAdminListingsAuth:
    def test_list_requires_session_when_unconfigured(self):
        response = client.get("/api/v1/admin/opportunities/")
        assert response.status_code == 503

    def test_list_rejects_missing_session(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "SESSION_SECRET_KEY", "test-secret")
        response = client.get("/api/v1/admin/opportunities/")
        assert response.status_code == 401


class TestAdminListingsActions:
    def setup_method(self):
        from app.config import settings

        self.db = SessionLocal()
        _cleanup(self.db)
        self._prior_secret = settings.SESSION_SECRET_KEY
        settings.SESSION_SECRET_KEY = "test-secret"
        self._token = create_session_token("test-secret")

    def teardown_method(self):
        from app.config import settings

        settings.SESSION_SECRET_KEY = self._prior_secret
        _cleanup(self.db)
        self.db.close()

    def _cookies(self):
        return {"of_admin_session": self._token}

    def test_list_shows_inactive_and_pending_rows_too(self):
        active = _make_row(self.db, "active-row")
        inactive = _make_row(self.db, "inactive-row", is_active=False)
        pending = _make_row(self.db, "pending-row", review_status="pending")

        response = client.get(
            "/api/v1/admin/opportunities/", params={"per_page": 100}, cookies=self._cookies()
        )
        assert response.status_code == 200
        ids = {row["id"] for row in response.json()["data"]}
        assert {active.id, inactive.id, pending.id} <= ids

    def test_search_filters_by_title(self):
        _make_row(self.db, "findme-unique-xyz")
        response = client.get(
            "/api/v1/admin/opportunities/",
            params={"search": "findme-unique-xyz"},
            cookies=self._cookies(),
        )
        assert response.status_code == 200
        assert response.json()["total"] == 1

    def test_update_edits_fields(self):
        opp = _make_row(self.db, "edit-me", title="Original Title")
        response = client.patch(
            f"/api/v1/admin/opportunities/{opp.id}",
            json={"title": "Corrected Title", "location": "Updated Location"},
            cookies=self._cookies(),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["title"] == "Corrected Title"
        assert body["location"] == "Updated Location"

        self.db.refresh(opp)
        assert opp.title == "Corrected Title"
        assert opp.title_normalized == "corrected title"  # dedup key kept in sync

    def test_update_unknown_id_returns_404(self):
        response = client.patch(
            "/api/v1/admin/opportunities/999999999",
            json={"title": "Doesn't matter"},
            cookies=self._cookies(),
        )
        assert response.status_code == 404

    def test_deactivate_sets_inactive(self):
        opp = _make_row(self.db, "deactivate-me")
        response = client.post(
            f"/api/v1/admin/opportunities/{opp.id}/deactivate", cookies=self._cookies()
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False
        self.db.refresh(opp)
        assert opp.is_active is False

    def test_reactivate_sets_active(self):
        opp = _make_row(self.db, "reactivate-me", is_active=False)
        response = client.post(
            f"/api/v1/admin/opportunities/{opp.id}/reactivate", cookies=self._cookies()
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is True
        self.db.refresh(opp)
        assert opp.is_active is True
