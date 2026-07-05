"""End-to-end regression: an opportunity with a passed deadline must
never appear in any public API response, regardless of its is_active
flag — this is the guarantee, not a best-effort filter.
"""

from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Opportunity

client = TestClient(app)

_TEST_URL_PREFIX = "https://example.org/expired-never-shown-"


def _cleanup(db):
    db.query(Opportunity).filter(Opportunity.url.like(f"{_TEST_URL_PREFIX}%")).delete(
        synchronize_session=False
    )
    db.commit()


class TestExpiredNeverShownInListing:
    def setup_method(self):
        self.db = SessionLocal()
        _cleanup(self.db)

    def teardown_method(self):
        _cleanup(self.db)
        self.db.close()

    def test_past_deadline_excluded_even_if_flagged_active(self):
        # Deliberately is_active=True — the query filter must still hide
        # it. This is the "even if the sweep job hasn't run yet" case.
        self.db.add(
            Opportunity(
                title="Expired But Still Flagged Active",
                opportunity_type="grant",
                url=f"{_TEST_URL_PREFIX}past",
                source_name="Test",
                is_active=True,
                deadline_at=date.today() - timedelta(days=1),
            )
        )
        self.db.commit()

        response = client.get("/api/v1/opportunities/", params={"search": "Expired But Still Flagged"})
        assert response.status_code == 200
        titles = [item["title"] for item in response.json()["data"]]
        assert "Expired But Still Flagged Active" not in titles

    def test_future_deadline_is_shown(self):
        self.db.add(
            Opportunity(
                title="Future Deadline Still Open Grant",
                opportunity_type="grant",
                url=f"{_TEST_URL_PREFIX}future",
                source_name="Test",
                is_active=True,
                deadline_at=date.today() + timedelta(days=30),
            )
        )
        self.db.commit()

        response = client.get("/api/v1/opportunities/", params={"search": "Future Deadline Still Open"})
        assert response.status_code == 200
        titles = [item["title"] for item in response.json()["data"]]
        assert "Future Deadline Still Open Grant" in titles

    def test_expired_opportunity_returns_404_by_id(self):
        opp = Opportunity(
            title="Expired Single Lookup",
            opportunity_type="grant",
            url=f"{_TEST_URL_PREFIX}single",
            source_name="Test",
            is_active=True,
            deadline_at=date.today() - timedelta(days=1),
        )
        self.db.add(opp)
        self.db.commit()
        self.db.refresh(opp)

        response = client.get(f"/api/v1/opportunities/{opp.id}")
        assert response.status_code == 404

    def test_expired_excluded_from_stats_total(self):
        before = client.get("/api/v1/opportunities/stats").json()["total"]

        self.db.add(
            Opportunity(
                title="Expired Stats Check",
                opportunity_type="grant",
                url=f"{_TEST_URL_PREFIX}stats",
                source_name="Test",
                is_active=True,
                deadline_at=date.today() - timedelta(days=1),
            )
        )
        self.db.commit()

        after = client.get("/api/v1/opportunities/stats").json()["total"]
        assert after == before  # unchanged — the expired row must not be counted
