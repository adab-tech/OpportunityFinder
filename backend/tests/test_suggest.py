"""Regression tests for the /opportunities/suggest autocomplete endpoint."""

from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Opportunity

client = TestClient(app)

_TEST_URL_PREFIX = "https://example.org/suggest-test-"


def _cleanup(db):
    db.query(Opportunity).filter(Opportunity.url.like(f"{_TEST_URL_PREFIX}%")).delete(
        synchronize_session=False
    )
    db.commit()


def _make(db, suffix: str, **overrides) -> Opportunity:
    defaults = dict(
        title=f"Suggest Fellowship {suffix}",
        opportunity_type="fellowship",
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


class TestSuggest:
    def setup_method(self):
        db = SessionLocal()
        _cleanup(db)
        db.close()

    def teardown_method(self):
        db = SessionLocal()
        _cleanup(db)
        db.close()

    def test_query_too_short_is_rejected(self):
        response = client.get("/api/v1/opportunities/suggest", params={"q": "a"})
        assert response.status_code == 422

    def test_matches_are_returned(self):
        db = SessionLocal()
        _make(db, "1")
        db.close()

        response = client.get("/api/v1/opportunities/suggest", params={"q": "Suggest Fellowship"})
        assert response.status_code == 200
        assert "Suggest Fellowship 1" in response.json()["suggestions"]

    def test_pending_opportunities_are_excluded(self):
        db = SessionLocal()
        _make(db, "2", review_status="pending")
        db.close()

        response = client.get("/api/v1/opportunities/suggest", params={"q": "Suggest Fellowship"})
        assert response.json()["suggestions"] == []

    def test_expired_opportunities_are_excluded(self):
        db = SessionLocal()
        _make(db, "3", deadline_at=date.today() - timedelta(days=1))
        db.close()

        response = client.get("/api/v1/opportunities/suggest", params={"q": "Suggest Fellowship"})
        assert response.json()["suggestions"] == []

    def test_limit_is_respected(self):
        db = SessionLocal()
        for i in range(5):
            _make(db, f"limit-{i}")
        db.close()

        response = client.get(
            "/api/v1/opportunities/suggest",
            params={"q": "Suggest Fellowship", "limit": 2},
        )
        assert len(response.json()["suggestions"]) <= 2
