"""
Google search wrapper.
Priority order:
  1. Google Custom Search JSON API  (requires GOOGLE_API_KEY + GOOGLE_CSE_ID in .env)
  2. googlesearch-python library     (scrapes public Google results, no key needed)
  3. Direct fallback                 (raw HTTP to google.com, last resort)
"""

import logging
import random
import time
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

from app.config import settings

logger = logging.getLogger(__name__)

# Domains whose pages are never relevant opportunity listings
EXCLUDE_DOMAINS = {
    "google.com", "youtube.com", "wikipedia.org", "twitter.com",
    "facebook.com", "instagram.com", "tiktok.com", "reddit.com",
    "amazon.com", "ebay.com", "linkedin.com",
}


class GoogleScraper:
    """Returns a list of URLs relevant to a given query string."""

    def __init__(self):
        self.ua = UserAgent()

    # ------------------------------------------------------------------
    # Search strategies
    # ------------------------------------------------------------------

    def _search_via_api(self, query: str, num: int) -> list[str]:
        """Google Custom Search JSON API (100 free queries/day)."""
        if not settings.GOOGLE_API_KEY or not settings.GOOGLE_CSE_ID:
            return []
        try:
            params = {
                "key": settings.GOOGLE_API_KEY,
                "cx": settings.GOOGLE_CSE_ID,
                "q": query,
                "num": min(num, 10),
            }
            r = requests.get(
                "https://www.googleapis.com/customsearch/v1",
                params=params,
                timeout=10,
            )
            r.raise_for_status()
            return [item["link"] for item in r.json().get("items", []) if "link" in item]
        except Exception as exc:
            logger.warning(f"Google API search failed: {exc}")
            return []

    def _search_via_library(self, query: str, num: int) -> list[str]:
        """Use googlesearch-python (public Google scrape, polite)."""
        try:
            from googlesearch import search
            return list(search(query, num_results=num, sleep_interval=2))
        except ImportError:
            logger.warning("googlesearch-python not installed — falling back to direct search")
            return self._search_direct(query, num)
        except Exception as exc:
            logger.warning(f"googlesearch-python error: {exc}")
            return []

    def _search_direct(self, query: str, num: int) -> list[str]:
        """Raw HTTP fallback — parse Google SERP HTML."""
        headers = {
            "User-Agent": self.ua.random,
            "Accept-Language": "en-US,en;q=0.9",
        }
        try:
            time.sleep(random.uniform(2, 4))
            url = f"https://www.google.com/search?q={quote_plus(query)}&num={num}"
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code != 200:
                return []
            soup = BeautifulSoup(r.text, "lxml")
            urls: list[str] = []
            for a in soup.select("a[href]"):
                href = a["href"]
                if href.startswith("/url?q="):
                    target = href.split("/url?q=")[1].split("&")[0]
                    if target.startswith("http") and "google.com" not in target:
                        urls.append(target)
                        if len(urls) >= num:
                            break
            return urls
        except Exception as exc:
            logger.warning(f"Direct Google search failed: {exc}")
            return []

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def search(self, query: str, num_results: int = 10) -> list[str]:
        """Return up to num_results URLs for the query, filtered for relevance."""
        # Prefer API when configured
        if settings.GOOGLE_API_KEY and settings.GOOGLE_CSE_ID:
            results = self._search_via_api(query, num_results)
            if results:
                return self._filter(results)

        results = self._search_via_library(query, num_results)
        return self._filter(results)

    def _filter(self, urls: list[str]) -> list[str]:
        """Remove social-media, search-engine and other irrelevant URLs."""
        return [
            u for u in urls
            if not any(d in u.lower() for d in EXCLUDE_DOMAINS)
        ]
