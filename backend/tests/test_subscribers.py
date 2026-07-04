from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import AlertSubscription, Opportunity, SavedOpportunity, Subscriber
from app.services import subscribers as svc
from app.services.email_sender import ConsoleEmailSender, EmailMessage

client = TestClient(app)

_TEST_EMAIL = "test-subscriber@example.org"
_TEST_URL = "https://example.org/test-subscriber-opportunity"


def _cleanup(db):
    db.query(SavedOpportunity).filter(
        SavedOpportunity.subscriber_id.in_(
            db.query(Subscriber.id).filter(Subscriber.email == _TEST_EMAIL)
        )
    ).delete(synchronize_session=False)
    db.query(AlertSubscription).filter(
        AlertSubscription.subscriber_id.in_(
            db.query(Subscriber.id).filter(Subscriber.email == _TEST_EMAIL)
        )
    ).delete(synchronize_session=False)
    db.query(Subscriber).filter(Subscriber.email == _TEST_EMAIL).delete()
    db.query(Opportunity).filter(Opportunity.url == _TEST_URL).delete()
    db.commit()


def _make_opportunity(db) -> Opportunity:
    opp = Opportunity(
        title="Test Opportunity For Saving",
        opportunity_type="scholarship",
        url=_TEST_URL,
        source_name="Test",
        is_active=True,
    )
    db.add(opp)
    db.commit()
    db.refresh(opp)
    return opp


class TestConsoleEmailSender:
    def test_send_always_succeeds(self, caplog):
        sender = ConsoleEmailSender()
        message = EmailMessage(to="a@b.com", subject="Hi", html_body="<p>hi</p>", text_body="hi")
        assert sender.send(message) is True


class TestSubscriberService:
    def setup_method(self):
        self.db = SessionLocal()
        _cleanup(self.db)
        self.opp = _make_opportunity(self.db)

    def teardown_method(self):
        _cleanup(self.db)
        self.db.close()

    def test_get_or_create_subscriber_is_idempotent(self):
        first = svc.get_or_create_subscriber(self.db, _TEST_EMAIL)
        second = svc.get_or_create_subscriber(self.db, _TEST_EMAIL.upper())  # case-insensitive
        assert first.id == second.id

    def test_save_opportunity_creates_subscriber_and_save(self):
        result = svc.save_opportunity(self.db, _TEST_EMAIL, self.opp.id)
        assert result is not None
        saved = svc.list_saved_opportunities(
            self.db, svc.get_or_create_subscriber(self.db, _TEST_EMAIL).manage_token
        )
        assert any(o.id == self.opp.id for o in saved)

    def test_save_opportunity_missing_id_returns_none(self):
        result = svc.save_opportunity(self.db, _TEST_EMAIL, 99999999)
        assert result is None

    def test_save_opportunity_twice_is_idempotent(self):
        first = svc.save_opportunity(self.db, _TEST_EMAIL, self.opp.id)
        second = svc.save_opportunity(self.db, _TEST_EMAIL, self.opp.id)
        assert first.id == second.id

    def test_unsave_removes_it(self):
        svc.save_opportunity(self.db, _TEST_EMAIL, self.opp.id)
        subscriber = svc.get_or_create_subscriber(self.db, _TEST_EMAIL)
        removed = svc.unsave_opportunity(self.db, subscriber.manage_token, self.opp.id)
        assert removed is True
        assert svc.list_saved_opportunities(self.db, subscriber.manage_token) == []

    def test_list_saved_with_invalid_token_returns_none(self):
        assert svc.list_saved_opportunities(self.db, "not-a-real-token") is None

    def test_create_and_list_alert(self):
        svc.create_alert(self.db, _TEST_EMAIL, opportunity_type="scholarship", keyword="AI")
        subscriber = svc.get_or_create_subscriber(self.db, _TEST_EMAIL)
        alerts = svc.list_alerts(self.db, subscriber.manage_token)
        assert len(alerts) == 1
        assert alerts[0].keyword == "AI"

    def test_delete_alert(self):
        alert = svc.create_alert(self.db, _TEST_EMAIL, keyword="AI")
        subscriber = svc.get_or_create_subscriber(self.db, _TEST_EMAIL)
        removed = svc.delete_alert(self.db, subscriber.manage_token, alert.id)
        assert removed is True
        assert svc.list_alerts(self.db, subscriber.manage_token) == []

    def test_alert_digest_matches_new_opportunity_by_keyword(self):
        alert = svc.create_alert(self.db, _TEST_EMAIL, keyword="Test Opportunity")
        # Backdate created_at so our opportunity (created above, before the
        # alert) counts as "new" relative to the alert's window.
        alert.created_at = datetime.now(UTC) - timedelta(days=1)
        self.db.commit()

        stats = svc.run_alert_digest(self.db)
        assert stats["digests_sent"] >= 1
        assert stats["matches_total"] >= 1

    def test_alert_digest_no_match_still_updates_last_notified(self):
        alert = svc.create_alert(self.db, _TEST_EMAIL, keyword="ZzzNoMatchQueryZzz")
        svc.run_alert_digest(self.db)
        self.db.refresh(alert)
        assert alert.last_notified_at is not None


class TestSubscriberRoutes:
    def setup_method(self):
        self.db = SessionLocal()
        _cleanup(self.db)
        self.opp = _make_opportunity(self.db)

    def teardown_method(self):
        _cleanup(self.db)
        self.db.close()

    def test_save_via_api(self):
        response = client.post("/api/v1/saved", json={"email": _TEST_EMAIL, "opportunity_id": self.opp.id})
        assert response.status_code == 200
        assert response.json()["status"] == "saved"

    def test_save_invalid_opportunity_returns_404(self):
        response = client.post("/api/v1/saved", json={"email": _TEST_EMAIL, "opportunity_id": 999999999})
        assert response.status_code == 404

    def test_save_invalid_email_returns_422(self):
        response = client.post("/api/v1/saved", json={"email": "not-an-email", "opportunity_id": self.opp.id})
        assert response.status_code == 422

    def test_list_saved_via_manage_token(self):
        client.post("/api/v1/saved", json={"email": _TEST_EMAIL, "opportunity_id": self.opp.id})
        subscriber = svc.get_or_create_subscriber(self.db, _TEST_EMAIL)
        response = client.get(f"/api/v1/saved/{subscriber.manage_token}")
        assert response.status_code == 200
        assert any(o["id"] == self.opp.id for o in response.json())

    def test_list_saved_invalid_token_returns_404(self):
        response = client.get("/api/v1/saved/not-a-real-token")
        assert response.status_code == 404

    def test_create_alert_via_api(self):
        response = client.post("/api/v1/alerts", json={"email": _TEST_EMAIL, "keyword": "AI"})
        assert response.status_code == 200
        assert response.json()["status"] == "created"

    def test_delete_alert_via_api(self):
        client.post("/api/v1/alerts", json={"email": _TEST_EMAIL, "keyword": "AI"})
        subscriber = svc.get_or_create_subscriber(self.db, _TEST_EMAIL)
        alerts = client.get(f"/api/v1/alerts/{subscriber.manage_token}").json()
        alert_id = alerts[0]["id"]
        response = client.delete(f"/api/v1/alerts/{subscriber.manage_token}/{alert_id}")
        assert response.status_code == 200
