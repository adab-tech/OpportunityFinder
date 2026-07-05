from unittest.mock import MagicMock, patch

from app.scrapers.google_scraper import GoogleScraper


class TestYouComSearch:
    def test_no_api_key_returns_empty(self):
        scraper = GoogleScraper()
        with patch("app.scrapers.google_scraper.settings") as mock_settings:
            mock_settings.YOU_API_KEY = None
            assert scraper._search_via_you_com("scholarship", 10) == []

    def test_parses_web_results(self):
        scraper = GoogleScraper()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": {
                "web": [
                    {"url": "https://example.org/scholarship-1", "title": "A"},
                    {"url": "https://example.org/scholarship-2", "title": "B"},
                ]
            }
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
        assert kwargs["params"]["count"] == 10

    def test_news_results_are_ignored(self):
        # Deliberate: news results were the dominant source of off-topic
        # content (sports, local council stories) since You.com's news
        # classifier fires on generic words like "grant" regardless of
        # context. Only `web` should ever be used.
        scraper = GoogleScraper()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": {
                "web": [{"url": "https://example.org/web-1"}],
                "news": [{"url": "https://example.org/news-1"}],
            }
        }
        mock_response.raise_for_status.return_value = None

        with patch("app.scrapers.google_scraper.settings") as mock_settings:
            mock_settings.YOU_API_KEY = "fake-key"
            with patch("app.scrapers.google_scraper.requests.get", return_value=mock_response):
                urls = scraper._search_via_you_com("scholarship", 10)

        assert urls == ["https://example.org/web-1"]

    def test_no_web_or_news_key_returns_empty(self):
        scraper = GoogleScraper()
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": {}}
        mock_response.raise_for_status.return_value = None

        with patch("app.scrapers.google_scraper.settings") as mock_settings:
            mock_settings.YOU_API_KEY = "fake-key"
            with patch("app.scrapers.google_scraper.requests.get", return_value=mock_response):
                assert scraper._search_via_you_com("scholarship", 10) == []

    def test_request_error_returns_empty_not_raises(self):
        scraper = GoogleScraper()
        with patch("app.scrapers.google_scraper.settings") as mock_settings:
            mock_settings.YOU_API_KEY = "fake-key"
            with patch("app.scrapers.google_scraper.requests.get", side_effect=Exception("network error")):
                assert scraper._search_via_you_com("scholarship", 10) == []

    def test_count_is_capped_at_100(self):
        scraper = GoogleScraper()
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": {"web": []}}
        mock_response.raise_for_status.return_value = None

        with patch("app.scrapers.google_scraper.settings") as mock_settings:
            mock_settings.YOU_API_KEY = "fake-key"
            with patch("app.scrapers.google_scraper.requests.get", return_value=mock_response) as mock_get:
                scraper._search_via_you_com("scholarship", 500)

        _, kwargs = mock_get.call_args
        assert kwargs["params"]["count"] == 100


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
