from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import AlertSubscription, Opportunity, SavedOpportunity, Subscriber
from app.services import subscribers as svc
from app.services.email_sender import ConsoleEmailSender, EmailMessage
from app.services.rate_limit import RateLimitedError

client = TestClient(app)

_TEST_EMAIL = "test-subscriber@example.org"
_TEST_URL = "https://example.org/test-subscriber-opportunity"
_TEST_URL_2 = "https://example.org/test-subscriber-opportunity-2"


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
    db.query(Opportunity).filter(Opportunity.url.in_([_TEST_URL, _TEST_URL_2])).delete(
        synchronize_session=False
    )
    db.commit()


def _make_opportunity(db, url: str = _TEST_URL) -> Opportunity:
    opp = Opportunity(
        title="Test Opportunity For Saving",
        opportunity_type="scholarship",
        url=url,
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


def _reset_rate_limiters():
    svc._alert_limiter._last_seen.clear()
    svc._save_limiter._last_seen.clear()


class TestSubscriberService:
    def setup_method(self):
        self.db = SessionLocal()
        _cleanup(self.db)
        _reset_rate_limiters()
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
        _reset_rate_limiters()
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


class TestEmailBombingProtection:
    """Neither /saved nor /alerts requires login (by design), so an email
    address is the only identity a caller controls — and both actions
    send that address a real email. Without a per-email cooldown, either
    endpoint could be used to mail-bomb an arbitrary victim.
    """

    def setup_method(self):
        self.db = SessionLocal()
        _cleanup(self.db)
        _reset_rate_limiters()
        self.opp = _make_opportunity(self.db, _TEST_URL)
        self.opp2 = _make_opportunity(self.db, _TEST_URL_2)

    def teardown_method(self):
        _cleanup(self.db)
        self.db.close()

    def test_second_alert_for_same_email_is_rate_limited(self):
        svc.create_alert(self.db, _TEST_EMAIL, keyword="AI")
        with pytest.raises(RateLimitedError):
            svc.create_alert(self.db, _TEST_EMAIL, keyword="ML")

    def test_second_alert_via_api_returns_429(self):
        first = client.post("/api/v1/alerts", json={"email": _TEST_EMAIL, "keyword": "AI"})
        assert first.status_code == 200
        second = client.post("/api/v1/alerts", json={"email": _TEST_EMAIL, "keyword": "ML"})
        assert second.status_code == 429

    def test_different_emails_are_not_rate_limited_against_each_other(self):
        svc.create_alert(self.db, _TEST_EMAIL, keyword="AI")
        # A different address must never be blocked by someone else's cooldown.
        svc.create_alert(self.db, "someone-else@example.org", keyword="AI")
        db2 = SessionLocal()
        try:
            db2.query(AlertSubscription).filter(
                AlertSubscription.subscriber_id.in_(
                    db2.query(Subscriber.id).filter(Subscriber.email == "someone-else@example.org")
                )
            ).delete(synchronize_session=False)
            db2.query(Subscriber).filter(Subscriber.email == "someone-else@example.org").delete()
            db2.commit()
        finally:
            db2.close()

    def test_second_new_save_for_same_email_is_rate_limited(self):
        svc.save_opportunity(self.db, _TEST_EMAIL, self.opp.id)
        with pytest.raises(RateLimitedError):
            svc.save_opportunity(self.db, _TEST_EMAIL, self.opp2.id)

    def test_repeat_save_of_same_opportunity_is_not_rate_limited(self):
        # A duplicate save of the SAME item is a no-op that never emails,
        # so it must not consume (or trip) the cooldown.
        first = svc.save_opportunity(self.db, _TEST_EMAIL, self.opp.id)
        second = svc.save_opportunity(self.db, _TEST_EMAIL, self.opp.id)
        assert first.id == second.id
