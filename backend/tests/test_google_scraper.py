from unittest.mock import MagicMock, patch

from app.scrapers.google_scraper import GoogleScraper


class TestYouComSearch:
    def test_no_api_key_returns_empty(self):
        scraper = GoogleScraper()
        with patch("app.scrapers.google_scraper.settings") as mock_settings:
            mock_settings.YOU_API_KEY = None
            assert scraper._search_via_you_com("scholarship", 10) == []

    def test_parses_hits_key(self):
        scraper = GoogleScraper()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "hits": [
                {"url": "https://example.org/scholarship-1"},
                {"url": "https://example.org/scholarship-2"},
            ]
        }
        mock_response.raise_for_status.return_value = None

        with patch("app.scrapers.google_scraper.settings") as mock_settings:
            mock_settings.YOU_API_KEY = "fake-key"
            with patch("app.scrapers.google_scraper.requests.get", return_value=mock_response) as mock_get:
                urls = scraper._search_via_you_com("scholarship", 10)

        assert urls == ["https://example.org/scholarship-1", "https://example.org/scholarship-2"]
        # Confirm the API key is sent as a header, not a URL param
        _, kwargs = mock_get.call_args
        assert kwargs["headers"]["X-API-Key"] == "fake-key"

    def test_parses_results_key_fallback(self):
        scraper = GoogleScraper()
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": [{"url": "https://example.org/x"}]}
        mock_response.raise_for_status.return_value = None

        with patch("app.scrapers.google_scraper.settings") as mock_settings:
            mock_settings.YOU_API_KEY = "fake-key"
            with patch("app.scrapers.google_scraper.requests.get", return_value=mock_response):
                urls = scraper._search_via_you_com("scholarship", 10)

        assert urls == ["https://example.org/x"]

    def test_request_error_returns_empty_not_raises(self):
        scraper = GoogleScraper()
        with patch("app.scrapers.google_scraper.settings") as mock_settings:
            mock_settings.YOU_API_KEY = "fake-key"
            with patch("app.scrapers.google_scraper.requests.get", side_effect=Exception("network error")):
                assert scraper._search_via_you_com("scholarship", 10) == []

    def test_unrecognized_shape_returns_empty_not_raises(self):
        scraper = GoogleScraper()
        mock_response = MagicMock()
        mock_response.json.return_value = {"hits": [{"unexpected": "shape"}]}
        mock_response.raise_for_status.return_value = None

        with patch("app.scrapers.google_scraper.settings") as mock_settings:
            mock_settings.YOU_API_KEY = "fake-key"
            with patch("app.scrapers.google_scraper.requests.get", return_value=mock_response):
                assert scraper._search_via_you_com("scholarship", 10) == []


class TestSearchPriorityOrder:
    def test_you_com_used_when_google_not_configured(self):
        scraper = GoogleScraper()
        with patch("app.scrapers.google_scraper.settings") as mock_settings:
            mock_settings.GOOGLE_API_KEY = None
            mock_settings.GOOGLE_CSE_ID = None
            mock_settings.YOU_API_KEY = "fake-key"
            with patch.object(
                scraper, "_search_via_you_com", return_value=["https://example.org/a"]
            ) as mock_you:
                with patch.object(scraper, "_search_via_library") as mock_lib:
                    results = scraper.search("scholarship", 10)

        mock_you.assert_called_once()
        mock_lib.assert_not_called()
        assert results == ["https://example.org/a"]

    def test_google_takes_priority_over_you_com(self):
        scraper = GoogleScraper()
        with patch("app.scrapers.google_scraper.settings") as mock_settings:
            mock_settings.GOOGLE_API_KEY = "g-key"
            mock_settings.GOOGLE_CSE_ID = "g-cse"
            mock_settings.YOU_API_KEY = "you-key"
            with patch.object(
                scraper, "_search_via_api", return_value=["https://example.org/google"]
            ) as mock_google:
                with patch.object(scraper, "_search_via_you_com") as mock_you:
                    results = scraper.search("scholarship", 10)

        mock_google.assert_called_once()
        mock_you.assert_not_called()
        assert results == ["https://example.org/google"]

    def test_falls_back_to_library_when_no_apis_return_results(self):
        scraper = GoogleScraper()
        with patch("app.scrapers.google_scraper.settings") as mock_settings:
            mock_settings.GOOGLE_API_KEY = None
            mock_settings.GOOGLE_CSE_ID = None
            mock_settings.YOU_API_KEY = "you-key"
            with patch.object(scraper, "_search_via_you_com", return_value=[]):
                with patch.object(
                    scraper, "_search_via_library", return_value=["https://example.org/lib"]
                ) as mock_lib:
                    results = scraper.search("scholarship", 10)

        mock_lib.assert_called_once()
        assert results == ["https://example.org/lib"]
