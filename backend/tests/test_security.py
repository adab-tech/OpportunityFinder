"""Regression tests for security hardening (path traversal, URL sanitisation)."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import RateLimitCooldown
from app.scrapers.url_utils import clean_url

client = TestClient(app)


class TestStaticFileContainment:
    def test_encoded_traversal_is_blocked(self):
        # %2F-encoded "../" must never escape the frontend folder
        response = client.get("/..%2Fbackend%2Fapp%2Fconfig.py")
        assert response.status_code in (200, 404)
        assert "BaseSettings" not in response.text

    def test_plain_traversal_is_blocked(self):
        response = client.get("/../backend/app/config.py")
        assert "BaseSettings" not in response.text

    def test_dotenv_not_served(self):
        response = client.get("/..%2Fbackend%2F.env")
        assert "DATABASE_URL" not in response.text

    def test_index_still_served(self):
        response = client.get("/")
        assert response.status_code == 200
        assert "Global Opportunities" in response.text

    def test_static_asset_still_served(self):
        response = client.get("/js/app.js")
        assert response.status_code == 200
        assert "API_BASE" in response.text


class TestUrlSanitisation:
    def test_https_allowed(self):
        assert clean_url("https://example.org/x") == "https://example.org/x"

    def test_http_allowed(self):
        assert clean_url("http://example.org") == "http://example.org"

    def test_javascript_rejected(self):
        assert clean_url("javascript:alert(1)") is None

    def test_data_uri_rejected(self):
        assert clean_url("data:text/html,<script>alert(1)</script>") is None

    def test_file_rejected(self):
        assert clean_url("file:///etc/passwd") is None

    def test_empty_and_none_rejected(self):
        assert clean_url("") is None
        assert clean_url(None) is None
        assert clean_url("   ") is None

    def test_overlong_rejected(self):
        assert clean_url("https://example.org/" + "a" * 3000) is None


class TestScrapeRequestValidation:
    def test_max_results_capped(self):
        response = client.post(
            "/api/v1/scraper/run",
            json={"max_results": 10_000},
        )
        assert response.status_code == 422

    def test_zero_max_results_rejected(self):
        response = client.post(
            "/api/v1/scraper/run",
            json={"max_results": 0},
        )
        assert response.status_code == 422


class TestScrapeCooldown:
    """The "Find new" button on the public homepage calls /scraper/run
    with no login required, by design. Without a floor between requests,
    a scripted caller could trigger runs back-to-back forever, burning
    through the metered You.com API or the Google CSE daily quota — see
    app/routes/scraper.py::_enforce_cooldown. Tested at the unit level,
    not through the full endpoint, since a real trigger runs the actual
    scrape pipeline (network calls) via FastAPI's BackgroundTasks, which
    the existing TestScrapeRequestValidation tests above also avoid by
    only ever sending invalid (422-rejected) bodies.

    Cooldown state now lives in the DB (RateLimitCooldown), not a
    process-local float — see app/services/rate_limit.py.
    """

    def setup_method(self):
        from app.routes import scraper as scraper_route

        self.scraper_route = scraper_route
        self._prior_seconds = scraper_route._scrape_cooldown_limiter._seconds
        scraper_route._scrape_cooldown_limiter._seconds = 100
        self._clear_cooldown_row()

    def teardown_method(self):
        self.scraper_route._scrape_cooldown_limiter._seconds = self._prior_seconds
        self._clear_cooldown_row()

    def _clear_cooldown_row(self):
        db = SessionLocal()
        try:
            db.query(RateLimitCooldown).filter(
                RateLimitCooldown.namespace == "scrape_trigger",
                RateLimitCooldown.key == self.scraper_route._SCRAPE_COOLDOWN_KEY,
            ).delete()
            db.commit()
        finally:
            db.close()

    def test_first_call_is_allowed(self):
        self.scraper_route._enforce_cooldown()  # must not raise

    def test_immediate_second_call_is_rejected(self):
        from fastapi import HTTPException

        self.scraper_route._enforce_cooldown()
        with pytest.raises(HTTPException) as exc_info:
            self.scraper_route._enforce_cooldown()
        assert exc_info.value.status_code == 429

    def test_call_after_cooldown_elapses_is_allowed(self):
        self.scraper_route._enforce_cooldown()
        # Simulate the cooldown having already elapsed.
        db = SessionLocal()
        try:
            row = (
                db.query(RateLimitCooldown)
                .filter(
                    RateLimitCooldown.namespace == "scrape_trigger",
                    RateLimitCooldown.key == self.scraper_route._SCRAPE_COOLDOWN_KEY,
                )
                .one()
            )
            row.last_seen_at = row.last_seen_at - timedelta(
                seconds=self.scraper_route._scrape_cooldown_limiter._seconds + 1
            )
            db.commit()
        finally:
            db.close()
        self.scraper_route._enforce_cooldown()  # must not raise

    def test_fresh_limiter_instance_still_sees_prior_cooldown(self):
        """The actual bug being fixed: an in-memory float reset to None
        on every process restart, silently undoing an in-progress
        cooldown. Simulate a restart by constructing a brand new
        CooldownLimiter pointed at the same DB and confirming it still
        rejects an immediate second call.
        """
        from app.services.rate_limit import CooldownLimiter, RateLimitedError

        self.scraper_route._enforce_cooldown()
        fresh_limiter = CooldownLimiter(
            self.scraper_route._scrape_cooldown_limiter._seconds, namespace="scrape_trigger"
        )
        with pytest.raises(RateLimitedError):
            fresh_limiter.check(self.scraper_route._SCRAPE_COOLDOWN_KEY)
