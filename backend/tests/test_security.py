"""Regression tests for security hardening (path traversal, URL sanitisation)."""

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
        assert "OpportunityFinder" in response.text

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
