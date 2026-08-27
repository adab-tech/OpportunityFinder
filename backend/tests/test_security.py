"""Regression tests for security hardening (path traversal, URL sanitisation)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
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
    """

    def setup_method(self):
        from app.routes import scraper as scraper_route

        self.scraper_route = scraper_route
        self._prior_cooldown = scraper_route._MANUAL_TRIGGER_COOLDOWN_SECONDS
        self._prior_last = scraper_route._last_triggered_at
        scraper_route._MANUAL_TRIGGER_COOLDOWN_SECONDS = 100
        scraper_route._last_triggered_at = 0.0

    def teardown_method(self):
        self.scraper_route._MANUAL_TRIGGER_COOLDOWN_SECONDS = self._prior_cooldown
        self.scraper_route._last_triggered_at = self._prior_last

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
        self.scraper_route._last_triggered_at -= self.scraper_route._MANUAL_TRIGGER_COOLDOWN_SECONDS + 1
        self.scraper_route._enforce_cooldown()  # must not raise
