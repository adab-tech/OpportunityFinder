from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import AnalyticsEvent
from app.services import analytics as svc

client = TestClient(app)

_TEST_CLIENT_ID = "test-client-id-abc123"


def _cleanup(db):
    db.query(AnalyticsEvent).filter(AnalyticsEvent.client_id == _TEST_CLIENT_ID).delete()
    db.commit()


class TestRecordEvent:
    def setup_method(self):
        self.db = SessionLocal()
        _cleanup(self.db)

    def teardown_method(self):
        _cleanup(self.db)
        self.db.close()

    def test_valid_event_is_recorded(self):
        svc.record_event(self.db, "pageview", _TEST_CLIENT_ID)
        rows = self.db.query(AnalyticsEvent).filter(AnalyticsEvent.client_id == _TEST_CLIENT_ID).all()
        assert len(rows) == 1
        assert rows[0].event_type == "pageview"

    def test_invalid_event_type_is_ignored(self):
        svc.record_event(self.db, "not-a-real-event", _TEST_CLIENT_ID)
        rows = self.db.query(AnalyticsEvent).filter(AnalyticsEvent.client_id == _TEST_CLIENT_ID).all()
        assert len(rows) == 0

    def test_empty_client_id_is_ignored(self):
        svc.record_event(self.db, "pageview", "")
        # nothing to assert on client_id since it's empty; just must not raise

    def test_search_event_records_value(self):
        svc.record_event(self.db, "search", _TEST_CLIENT_ID, value="AI fellowship")
        row = self.db.query(AnalyticsEvent).filter(AnalyticsEvent.client_id == _TEST_CLIENT_ID).first()
        assert row.value == "AI fellowship"


class TestGetSummary:
    def setup_method(self):
        self.db = SessionLocal()
        _cleanup(self.db)
        svc.record_event(self.db, "pageview", _TEST_CLIENT_ID)
        svc.record_event(self.db, "search", _TEST_CLIENT_ID, value="scholarship")
        svc.record_event(self.db, "filter_type", _TEST_CLIENT_ID, value="fellowship")

    def teardown_method(self):
        _cleanup(self.db)
        self.db.close()

    def test_summary_counts_events(self):
        summary = svc.get_summary(self.db, days=7)
        assert summary["total_events"] >= 3
        assert summary["unique_visitors"] >= 1
        assert summary["event_counts"].get("pageview", 0) >= 1

    def test_summary_includes_top_searches(self):
        summary = svc.get_summary(self.db, days=7)
        values = [item["value"] for item in summary["top_searches"]]
        assert "scholarship" in values


class TestAnalyticsRoutes:
    def teardown_method(self):
        db = SessionLocal()
        _cleanup(db)
        db.close()

    def test_event_endpoint_accepts_valid_event(self):
        response = client.post(
            "/api/v1/analytics/event",
            json={"event_type": "pageview", "client_id": _TEST_CLIENT_ID},
        )
        assert response.status_code == 204

    def test_event_endpoint_silently_ignores_invalid_type(self):
        response = client.post(
            "/api/v1/analytics/event",
            json={"event_type": "bogus", "client_id": _TEST_CLIENT_ID},
        )
        assert response.status_code == 204

    def test_summary_requires_admin_key_when_unconfigured(self):
        response = client.get("/api/v1/analytics/summary")
        assert response.status_code == 503

    def test_summary_rejects_wrong_key_when_configured(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "ADMIN_API_KEY", "correct-key")
        response = client.get("/api/v1/analytics/summary", headers={"X-Admin-Key": "wrong-key"})
        assert response.status_code == 401

    def test_summary_succeeds_with_correct_key(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "ADMIN_API_KEY", "correct-key")
        response = client.get("/api/v1/analytics/summary", headers={"X-Admin-Key": "correct-key"})
        assert response.status_code == 200
        assert "total_events" in response.json()
