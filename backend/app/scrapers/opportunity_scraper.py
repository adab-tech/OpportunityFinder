"""
Main scraping orchestrator.
Combines Google search discovery with direct site scraping,
deduplicates by URL, and persists results to the database.
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Opportunity
from app.scrapers.base_scraper import BaseScraper
from app.scrapers.google_scraper import GoogleScraper
from app.scrapers.keywords import OPPORTUNITY_SITES, build_google_queries
from app.scrapers.rss_ingest import RssIngestor
from app.scrapers.url_utils import clean_url

logger = logging.getLogger(__name__)


class OpportunityScraper:
    def __init__(self, db: Session):
        self.db = db
        self.base = BaseScraper()
        self.google = GoogleScraper()
        self.stats = {"scraped": 0, "saved": 0, "errors": 0}

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    def _url_exists(self, url: str) -> bool:
        return (
            self.db.query(Opportunity).filter(Opportunity.url == url).first()
            is not None
        )

    def _save(self, data: dict[str, Any]) -> bool:
        """Persist one opportunity; silently skip duplicates, unsafe URLs, or empty titles."""
        url = clean_url(data.get("url"))
        title = (data.get("title") or "").strip()
        if not url or not title or len(title) < 5:
            return False
        if self._url_exists(url):
            return False

        try:
            opp = Opportunity(
                title=title[:500],
                description=(data.get("description") or "")[:2000] or None,
                opportunity_type=data.get("opportunity_type", "other"),
                field=data.get("field"),
                location=data.get("location"),
                deadline=data.get("deadline"),
                url=url[:2000],
                source_name=data.get("source_name"),
                tags=data.get("tags"),
            )
            self.db.add(opp)
            self.db.commit()
            self.stats["saved"] += 1
            return True
        except Exception as exc:
            logger.error(f"DB save error: {exc}")
            self.db.rollback()
            self.stats["errors"] += 1
            return False

    # ------------------------------------------------------------------
    # Page parsing
    # ------------------------------------------------------------------

    def _parse_page(self, url: str, opportunity_type: str) -> dict[str, Any] | None:
        """Fetch URL and extract opportunity metadata."""
        soup = self.base.fetch_page(url)
        if not soup:
            return None

        self.stats["scraped"] += 1
        full_text = soup.get_text(separator=" ")

        title = self.base.get_page_title(soup)
        description = self.base.get_page_description(soup)
        combined = f"{title or ''} {description or ''} {full_text[:3000]}"

        return {
            "title": title,
            "description": description,
            "opportunity_type": opportunity_type,
            "field": self.base.extract_field(combined),
            "location": self.base.extract_location(combined),
            "deadline": self.base.extract_deadline(full_text),
            "url": url,
            "source_name": self.base.get_domain_name(url),
        }

    # ------------------------------------------------------------------
    # Scraping strategies
    # ------------------------------------------------------------------

    def scrape_via_google(
        self,
        opportunity_type: str,
        extra_keywords: list[str] | None = None,
        max_count: int = 20,
    ) -> int:
        """Discover URLs through Google search and scrape each one."""
        queries = build_google_queries(opportunity_type, extra_keywords)
        count = 0
        seen: set = set()

        for query in queries:
            if count >= max_count:
                break
            logger.info(f"[Google] Query: {query}")
            urls = self.google.search(query, num_results=settings.MAX_RESULTS_PER_QUERY)

            for url in urls:
                if count >= max_count:
                    break
                if url in seen or self._url_exists(url):
                    continue
                seen.add(url)

                data = self._parse_page(url, opportunity_type)
                if data and self._save(data):
                    count += 1
                    logger.info(f"  ✓ Saved: {data['title'][:70]}")

        return count

    def scrape_known_sites(self, opportunity_type: str) -> int:
        """Scrape curated listing pages and follow article links."""
        count = 0
        for site_url in OPPORTUNITY_SITES.get(opportunity_type, []):
            logger.info(f"[Site] Scraping: {site_url}")
            soup = self.base.fetch_page(site_url)
            if not soup:
                continue

            # Extract article links from common CMS patterns
            links = []
            for a in soup.select(
                "article a, .entry-title a, h2 a, h3 a, .post-title a, .listing-title a"
            ):
                href = a.get("href", "")
                if href.startswith("http") and not self._url_exists(href):
                    links.append(href)

            for url in links[:10]:          # max 10 articles per listing page
                data = self._parse_page(url, opportunity_type)
                if data and self._save(data):
                    count += 1
                    logger.info(f"  ✓ Saved: {data['title'][:70]}")

        return count

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(
        self,
        opportunity_types: list[str] | None = None,
        extra_keywords: list[str] | None = None,
        max_results: int = 50,
    ) -> dict:
        """Run the full scraping pipeline for all requested types."""
        if not opportunity_types:
            opportunity_types = ["scholarship", "fellowship", "grant", "job"]

        rss_stats = RssIngestor(self.db).run(
            max_entries_per_feed=settings.RSS_MAX_ENTRIES_PER_FEED
        )
        logger.info("RSS ingest → %s new items (%s)", rss_stats.get("saved", 0), rss_stats)

        max_per_type = max(10, max_results // len(opportunity_types))

        for opp_type in opportunity_types:
            logger.info(f"=== Starting scrape: {opp_type.upper()} ===")

            direct = self.scrape_known_sites(opp_type)
            logger.info(f"  Known sites → {direct} new items")

            via_google = self.scrape_via_google(opp_type, extra_keywords, max_per_type)
            logger.info(f"  Google search → {via_google} new items")

        logger.info(f"Scrape complete. Stats: {self.stats}")
        return self.stats
