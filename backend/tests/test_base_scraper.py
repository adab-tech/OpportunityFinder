import socket
from unittest.mock import MagicMock, patch

from app.scrapers.base_scraper import BaseScraper, resolves_to_public_address


class TestResolvesToPublicAddress:
    def test_no_hostname_is_rejected(self):
        assert resolves_to_public_address("not-a-url") is False

    def test_unresolvable_host_is_rejected(self):
        with patch("app.scrapers.base_scraper.socket.getaddrinfo", side_effect=socket.gaierror):
            assert resolves_to_public_address("https://nonexistent.invalid/") is False

    def test_loopback_address_is_rejected(self):
        with patch(
            "app.scrapers.base_scraper.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
        ):
            assert resolves_to_public_address("https://sneaky.example/") is False

    def test_private_address_is_rejected(self):
        with patch(
            "app.scrapers.base_scraper.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443))],
        ):
            assert resolves_to_public_address("https://sneaky.example/") is False

    def test_link_local_metadata_address_is_rejected(self):
        # 169.254.169.254 is the AWS/GCP/Azure cloud metadata endpoint —
        # the canonical SSRF target this check exists to block.
        with patch(
            "app.scrapers.base_scraper.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80))],
        ):
            assert resolves_to_public_address("http://sneaky.example/") is False

    def test_public_address_is_accepted(self):
        with patch(
            "app.scrapers.base_scraper.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
        ):
            assert resolves_to_public_address("https://example.org/") is True


def _redirect_response(location):
    resp = MagicMock()
    resp.is_redirect = True
    resp.is_permanent_redirect = False
    resp.headers = {"Location": location}
    return resp


def _ok_response(text="<html><body>ok</body></html>", content_type="text/html"):
    resp = MagicMock()
    resp.is_redirect = False
    resp.is_permanent_redirect = False
    resp.raise_for_status.return_value = None
    resp.headers = {"Content-Type": content_type}
    resp.text = text
    return resp


class TestFetchPageSSRF:
    def test_initial_url_not_public_is_skipped(self):
        scraper = BaseScraper()
        with patch("app.scrapers.base_scraper.resolves_to_public_address", return_value=False):
            with patch.object(scraper.session, "get") as mock_get:
                result = scraper.fetch_page("http://169.254.169.254/latest/meta-data/", delay=False)
        assert result is None
        mock_get.assert_not_called()

    def test_redirect_to_private_address_is_rejected(self):
        scraper = BaseScraper()
        with patch.object(scraper, "_can_fetch", return_value=True):
            with patch(
                "app.scrapers.base_scraper.resolves_to_public_address",
                side_effect=[True, False],
            ):
                with patch.object(
                    scraper.session,
                    "get",
                    return_value=_redirect_response("http://169.254.169.254/"),
                ):
                    result = scraper.fetch_page("https://example.org/redirector", delay=False)
        assert result is None

    def test_normal_page_is_fetched(self):
        scraper = BaseScraper()
        with patch("app.scrapers.base_scraper.resolves_to_public_address", return_value=True):
            with patch.object(scraper, "_can_fetch", return_value=True):
                with patch.object(scraper.session, "get", return_value=_ok_response()):
                    result = scraper.fetch_page("https://example.org/page", delay=False)
        assert result is not None
        assert result.body.get_text() == "ok"

    def test_too_many_redirects_gives_up(self):
        scraper = BaseScraper()
        with patch.object(scraper, "_can_fetch", return_value=True):
            with patch("app.scrapers.base_scraper.resolves_to_public_address", return_value=True):
                with patch.object(
                    scraper.session,
                    "get",
                    return_value=_redirect_response("https://example.org/next"),
                ):
                    result = scraper.fetch_page("https://example.org/loop", delay=False)
        assert result is None
