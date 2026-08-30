"""Regression tests for app/services/email_sender.py's provider senders
and get_email_sender()'s selection priority (Resend > Brevo > SendGrid >
console)."""

from unittest.mock import MagicMock, patch

import requests

from app.services.email_sender import (
    BrevoEmailSender,
    ConsoleEmailSender,
    EmailMessage,
    ResendEmailSender,
    SendGridEmailSender,
    get_email_sender,
)

_MESSAGE = EmailMessage(
    to="subscriber@example.org",
    subject="New matches this week",
    html_body="<p>hi</p>",
    text_body="hi",
)


class TestResendEmailSender:
    def test_send_posts_expected_payload(self):
        sender = ResendEmailSender("fake-resend-key", "Global Opportunities <alerts@globalopportunities.app>")
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None

        with patch("app.services.email_sender.requests.post", return_value=mock_response) as mock_post:
            assert sender.send(_MESSAGE) is True

        _, kwargs = mock_post.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer fake-resend-key"
        assert kwargs["json"]["from"] == "Global Opportunities <alerts@globalopportunities.app>"
        assert kwargs["json"]["to"] == ["subscriber@example.org"]
        assert kwargs["json"]["subject"] == "New matches this week"

    def test_send_returns_false_on_request_failure(self):
        sender = ResendEmailSender("fake-resend-key", "alerts@globalopportunities.app")
        with patch("app.services.email_sender.requests.post", side_effect=requests.RequestException("boom")):
            assert sender.send(_MESSAGE) is False


class TestBrevoEmailSender:
    def test_send_posts_expected_payload_with_split_sender(self):
        sender = BrevoEmailSender(
            "fake-brevo-key", "Global Opportunities <alerts@globalopportunities.app>"
        )
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None

        with patch("app.services.email_sender.requests.post", return_value=mock_response) as mock_post:
            assert sender.send(_MESSAGE) is True

        _, kwargs = mock_post.call_args
        assert kwargs["headers"]["api-key"] == "fake-brevo-key"
        assert kwargs["json"]["sender"] == {
            "email": "alerts@globalopportunities.app",
            "name": "Global Opportunities",
        }
        assert kwargs["json"]["to"] == [{"email": "subscriber@example.org"}]
        assert kwargs["json"]["htmlContent"] == "<p>hi</p>"
        assert kwargs["json"]["textContent"] == "hi"

    def test_sender_without_a_display_name_omits_name_field(self):
        sender = BrevoEmailSender("fake-brevo-key", "alerts@globalopportunities.app")
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None

        with patch("app.services.email_sender.requests.post", return_value=mock_response) as mock_post:
            sender.send(_MESSAGE)

        _, kwargs = mock_post.call_args
        assert kwargs["json"]["sender"] == {"email": "alerts@globalopportunities.app"}

    def test_send_returns_false_on_request_failure(self):
        sender = BrevoEmailSender("fake-brevo-key", "alerts@globalopportunities.app")
        with patch("app.services.email_sender.requests.post", side_effect=requests.RequestException("boom")):
            assert sender.send(_MESSAGE) is False


class TestSendGridEmailSender:
    def test_send_posts_expected_payload_with_split_sender(self):
        sender = SendGridEmailSender(
            "fake-sendgrid-key", "Global Opportunities <alerts@globalopportunities.app>"
        )
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None

        with patch("app.services.email_sender.requests.post", return_value=mock_response) as mock_post:
            assert sender.send(_MESSAGE) is True

        _, kwargs = mock_post.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer fake-sendgrid-key"
        assert kwargs["json"]["personalizations"] == [{"to": [{"email": "subscriber@example.org"}]}]
        assert kwargs["json"]["from"] == {
            "email": "alerts@globalopportunities.app",
            "name": "Global Opportunities",
        }
        assert kwargs["json"]["subject"] == "New matches this week"
        assert {"type": "text/plain", "value": "hi"} in kwargs["json"]["content"]
        assert {"type": "text/html", "value": "<p>hi</p>"} in kwargs["json"]["content"]

    def test_sender_without_a_display_name_omits_name_field(self):
        sender = SendGridEmailSender("fake-sendgrid-key", "alerts@globalopportunities.app")
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None

        with patch("app.services.email_sender.requests.post", return_value=mock_response) as mock_post:
            sender.send(_MESSAGE)

        _, kwargs = mock_post.call_args
        assert kwargs["json"]["from"] == {"email": "alerts@globalopportunities.app"}

    def test_send_returns_false_on_request_failure(self):
        sender = SendGridEmailSender("fake-sendgrid-key", "alerts@globalopportunities.app")
        with patch("app.services.email_sender.requests.post", side_effect=requests.RequestException("boom")):
            assert sender.send(_MESSAGE) is False


class TestGetEmailSender:
    def test_defaults_to_console_when_no_key_configured(self):
        with patch("app.services.email_sender.settings") as mock_settings:
            mock_settings.RESEND_API_KEY = None
            mock_settings.BREVO_API_KEY = None
            mock_settings.SENDGRID_API_KEY = None
            assert isinstance(get_email_sender(), ConsoleEmailSender)

    def test_uses_brevo_when_only_brevo_key_set(self):
        with patch("app.services.email_sender.settings") as mock_settings:
            mock_settings.RESEND_API_KEY = None
            mock_settings.BREVO_API_KEY = "fake-brevo-key"
            mock_settings.SENDGRID_API_KEY = None
            mock_settings.ALERT_FROM_EMAIL = "alerts@globalopportunities.app"
            assert isinstance(get_email_sender(), BrevoEmailSender)

    def test_uses_sendgrid_when_only_sendgrid_key_set(self):
        with patch("app.services.email_sender.settings") as mock_settings:
            mock_settings.RESEND_API_KEY = None
            mock_settings.BREVO_API_KEY = None
            mock_settings.SENDGRID_API_KEY = "fake-sendgrid-key"
            mock_settings.ALERT_FROM_EMAIL = "alerts@globalopportunities.app"
            assert isinstance(get_email_sender(), SendGridEmailSender)

    def test_resend_takes_priority_over_brevo_and_sendgrid(self):
        with patch("app.services.email_sender.settings") as mock_settings:
            mock_settings.RESEND_API_KEY = "fake-resend-key"
            mock_settings.BREVO_API_KEY = "fake-brevo-key"
            mock_settings.SENDGRID_API_KEY = "fake-sendgrid-key"
            mock_settings.ALERT_FROM_EMAIL = "alerts@globalopportunities.app"
            assert isinstance(get_email_sender(), ResendEmailSender)

    def test_brevo_takes_priority_over_sendgrid(self):
        with patch("app.services.email_sender.settings") as mock_settings:
            mock_settings.RESEND_API_KEY = None
            mock_settings.BREVO_API_KEY = "fake-brevo-key"
            mock_settings.SENDGRID_API_KEY = "fake-sendgrid-key"
            mock_settings.ALERT_FROM_EMAIL = "alerts@globalopportunities.app"
            assert isinstance(get_email_sender(), BrevoEmailSender)
