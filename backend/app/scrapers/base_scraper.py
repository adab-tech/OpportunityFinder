"""
Base HTTP scraper with user-agent rotation, robots.txt compliance,
rate limiting, and common text-extraction helpers.
"""

import logging
import random
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

from app.config import settings
from app.scrapers.deadline_utils import extract_deadline
from app.scrapers.keywords import FIELD_KEYWORDS

logger = logging.getLogger(__name__)


class BaseScraper:
    def __init__(self):
        self.ua = UserAgent()
        self.session = requests.Session()
        self._robot_cache: dict[str, RobotFileParser] = {}

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _get_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.ua.random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

    def _can_fetch(self, url: str) -> bool:
        """Return True if robots.txt permits fetching this URL."""
        try:
            parsed = urlparse(url)
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            if robots_url not in self._robot_cache:
                # Fetch with an explicit timeout — RobotFileParser.read()
                # uses urllib without one and can hang a scrape thread.
                rp = RobotFileParser()
                resp = self.session.get(robots_url, timeout=settings.REQUEST_TIMEOUT)
                if resp.status_code >= 400:
                    rp.allow_all = True
                else:
                    rp.parse(resp.text.splitlines())
                self._robot_cache[robots_url] = rp
            return self._robot_cache[robots_url].can_fetch("*", url)
        except Exception:
            return True  # allow if robots.txt is unreachable

    def fetch_page(self, url: str, delay: bool = True) -> BeautifulSoup | None:
        """Fetch a URL and return a parsed BeautifulSoup tree, or None on failure."""
        if not self._can_fetch(url):
            logger.info(f"Skipping {url} — blocked by robots.txt")
            return None

        if delay:
            time.sleep(settings.REQUEST_DELAY_SECONDS + random.uniform(0.5, 2.0))

        for attempt in range(settings.MAX_RETRIES):
            try:
                response = self.session.get(
                    url,
                    headers=self._get_headers(),
                    timeout=settings.REQUEST_TIMEOUT,
                    allow_redirects=True,
                )
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "")
                if content_type and "html" not in content_type and "xml" not in content_type:
                    logger.info(f"Skipping {url} — non-HTML content ({content_type})")
                    return None
                return BeautifulSoup(response.text, "lxml")
            except requests.RequestException as exc:
                logger.warning(f"Attempt {attempt + 1}/{settings.MAX_RETRIES} failed for {url}: {exc}")
                if attempt < settings.MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)

        return None

    # ------------------------------------------------------------------
    # Text extraction helpers
    # ------------------------------------------------------------------

    def get_page_title(self, soup: BeautifulSoup) -> str | None:
        """Return the best title found on the page."""
        for selector in ["h1", "h2", ".entry-title", ".post-title", "title"]:
            el = soup.select_one(selector)
            if el:
                text = " ".join(el.get_text().split())
                if len(text) >= 5:
                    return text[:500]
        return None

    def get_page_description(self, soup: BeautifulSoup) -> str | None:
        """Return the best description: meta > og > first paragraph."""
        # meta description
        meta = soup.find("meta", {"name": "description"})
        if meta and meta.get("content"):
            return str(meta["content"])[:1000]

        # og:description
        og = soup.find("meta", {"property": "og:description"})
        if og and og.get("content"):
            return str(og["content"])[:1000]

        # first substantial paragraph
        for p in soup.find_all("p"):
            text = " ".join(p.get_text().split())
            if len(text) >= 80:
                return text[:1000]

        return None

    def extract_deadline(self, text: str) -> str | None:
        """Extract a deadline date string from raw page text."""
        return extract_deadline(text)

    def extract_field(self, text: str) -> str | None:
        """Detect the academic/professional field from text."""
        text_lower = text.lower()
        for field, keywords in FIELD_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                return field
        return None

    def extract_location(self, text: str) -> str | None:
        """Extract a country or region indicator from text."""
        locations = [
            "Global", "Worldwide", "International", "Online", "Remote",
            "USA", "United States", "UK", "United Kingdom", "Canada",
            "Australia", "Germany", "France", "Netherlands", "Sweden",
            "Switzerland", "Japan", "China", "India", "Brazil",
            "South Africa", "Kenya", "Nigeria", "Ghana", "Ethiopia",
            "Africa", "Europe", "Asia", "Latin America",
        ]
        text_lower = text.lower()
        for loc in locations:
            if loc.lower() in text_lower:
                return loc
        return None

    def get_domain_name(self, url: str) -> str:
        """Return the clean domain (without www.) from a URL."""
        domain = urlparse(url).netloc
        return domain[4:] if domain.startswith("www.") else domain
