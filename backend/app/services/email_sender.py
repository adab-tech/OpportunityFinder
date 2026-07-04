"""Pluggable email delivery for alert/save confirmations.

No email provider is required to run this app. By default, emails are
logged (ConsoleEmailSender) so every code path — save/alert signup,
manage links, weekly digests — works end-to-end with zero setup. Set
RESEND_API_KEY to switch to real delivery via Resend
(https://resend.com) with no code changes.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

import requests

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    html_body: str
    text_body: str


class EmailSender(ABC):
    @abstractmethod
    def send(self, message: EmailMessage) -> bool:
        """Return True if the message was accepted for delivery."""


class ConsoleEmailSender(EmailSender):
    """Fallback sender: logs the full email instead of delivering it.

    This is what runs whenever RESEND_API_KEY is not configured, so the
    whole saved-opportunities/alerts feature is fully testable and usable
    (via the server log) before anyone signs up for an email provider.
    """

    def send(self, message: EmailMessage) -> bool:
        logger.info(
            "EMAIL (console fallback — set RESEND_API_KEY to send for real)\n"
            "  To: %s\n  Subject: %s\n  ---\n%s",
            message.to,
            message.subject,
            message.text_body,
        )
        return True


class ResendEmailSender(EmailSender):
    """Delivers via the Resend API (https://resend.com/docs/api-reference)."""

    _ENDPOINT = "https://api.resend.com/emails"

    def __init__(self, api_key: str, from_address: str):
        self._api_key = api_key
        self._from_address = from_address

    def send(self, message: EmailMessage) -> bool:
        try:
            response = requests.post(
                self._ENDPOINT,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "from": self._from_address,
                    "to": [message.to],
                    "subject": message.subject,
                    "html": message.html_body,
                    "text": message.text_body,
                },
                timeout=10,
            )
            response.raise_for_status()
            return True
        except requests.RequestException as exc:
            logger.error("Resend email send failed for %s: %s", message.to, exc)
            return False


def get_email_sender() -> EmailSender:
    if settings.RESEND_API_KEY:
        return ResendEmailSender(settings.RESEND_API_KEY, settings.ALERT_FROM_EMAIL)
    return ConsoleEmailSender()
