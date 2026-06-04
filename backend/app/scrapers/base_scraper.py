"""
Base HTTP scraper with user-agent rotation, robots.txt compliance,
rate limiting, and common text-extraction helpers.
"""

import re
import time
import random
import logging
from typing import Optional, Dict
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

from app.config import settings
from app.scrapers.keywords import FIELD_KEYWORDS

logger = logging.getLogger(__name__)


class BaseScraper:
    def __init__(self):
        self.ua = UserAgent()
        self.session = requests.Session()
        self._robot_cache: Dict[str, RobotFileParser] = {}

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _get_headers(self) -> Dict[str, str]:
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
                rp = RobotFileParser()
                rp.set_url(robots_url)
                rp.read()
                self._robot_cache[robots_url] = rp
            return self._robot_cache[robots_url].can_fetch("*", url)
        except Exception:
            return True  # allow if robots.txt is unreachable

    def fetch_page(self, url: str, delay: bool = True) -> Optional[BeautifulSoup]:
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
                return BeautifulSoup(response.text, "lxml")
            except requests.RequestException as exc:
                logger.warning(f"Attempt {attempt + 1}/{settings.MAX_RETRIES} failed for {url}: {exc}")
                if attempt < settings.MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)

        return None

    # ------------------------------------------------------------------
    # Text extraction helpers
    # ------------------------------------------------------------------

    def get_page_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Return the best title found on the page."""
        for selector in ["h1", "h2", ".entry-title", ".post-title", "title"]:
            el = soup.select_one(selector)
            if el:
                text = " ".join(el.get_text().split())
                if len(text) >= 5:
                    return text[:500]
        return None

    def get_page_description(self, soup: BeautifulSoup) -> Optional[str]:
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

    def extract_deadline(self, text: str) -> Optional[str]:
        """Extract a deadline date string from raw page text."""
        if not text:
            return None

        patterns = [
            r'deadline[:\s]+([A-Za-z]+ \d{1,2},?\s+\d{4})',
            r'apply\s+by[:\s]+([A-Za-z]+ \d{1,2},?\s+\d{4})',
            r'closing\s+date[:\s]+([A-Za-z]+ \d{1,2},?\s+\d{4})',
            r'applications?\s+(?:due|close)[:\s]+([A-Za-z]+ \d{1,2},?\s+\d{4})',
            r'submission\s+deadline[:\s]+([A-Za-z]+ \d{1,2},?\s+\d{4})',
            r'due\s+date[:\s]+([A-Za-z]+ \d{1,2},?\s+\d{4})',
            r'(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})',
            r'(\d{4}-\d{2}-\d{2})',
            r'(\d{1,2}/\d{1,2}/\d{4})',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()[:100]

        return None

    def extract_field(self, text: str) -> Optional[str]:
        """Detect the academic/professional field from text."""
        text_lower = text.lower()
        for field, keywords in FIELD_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                return field
        return None

    def extract_location(self, text: str) -> Optional[str]:
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
