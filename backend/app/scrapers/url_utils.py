"""URL sanitisation shared by all ingest paths (scraper, RSS, seeds)."""

from urllib.parse import urlparse

_ALLOWED_SCHEMES = {"http", "https"}
MAX_URL_LENGTH = 2000


def clean_url(raw: str | None) -> str | None:
    """Return a trimmed, scheme-validated URL or None if unsafe/invalid.

    Rejects anything that is not plain http(s) — e.g. javascript:, data:,
    file: — so a hostile feed entry can never become a clickable link.
    """
    if not raw:
        return None
    url = raw.strip()
    if not url or len(url) > MAX_URL_LENGTH:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES or not parsed.netloc:
        return None
    return url
