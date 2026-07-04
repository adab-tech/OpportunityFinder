"""Ingest opportunities from curated RSS/Atom feeds."""

import logging
import re
from html import unescape
from typing import Any

import feedparser
from sqlalchemy.orm import Session

from app.ingest.rss_feeds import RSS_FEEDS
from app.models import Opportunity
from app.scrapers.url_utils import clean_url

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")


def _plain_text(value: str | None, limit: int = 2000) -> str | None:
    if not value:
        return None
    text = unescape(_TAG_RE.sub(" ", value))
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    return text[:limit]


class RssIngestor:
    def __init__(self, db: Session):
        self.db = db
        self.stats: dict[str, int] = {"feeds": 0, "entries": 0, "saved": 0, "errors": 0}

    def _url_exists(self, url: str) -> bool:
        return (
            self.db.query(Opportunity).filter(Opportunity.url == url).first()
            is not None
        )

    def _save(self, data: dict[str, Any]) -> bool:
        url = clean_url(data.get("url"))
        title = (data.get("title") or "").strip()
        if not url or not title or len(title) < 5:
            return False
        if self._url_exists(url):
            return False

        try:
            self.db.add(
                Opportunity(
                    title=title[:500],
                    description=_plain_text(data.get("description")),
                    opportunity_type=data.get("opportunity_type", "other"),
                    field=data.get("field"),
                    location=data.get("location"),
                    url=url[:2000],
                    source_name=data.get("source_name"),
                    is_active=True,
                )
            )
            self.db.commit()
            self.stats["saved"] += 1
            return True
        except Exception as exc:
            logger.error("RSS save error: %s", exc)
            self.db.rollback()
            self.stats["errors"] += 1
            return False

    def _entry_from_feed(self, entry: Any, spec: dict[str, str]) -> dict[str, Any] | None:
        link = (getattr(entry, "link", None) or "").strip()
        title = _plain_text(getattr(entry, "title", None), limit=500)
        if not link or not title:
            return None

        summary = (
            getattr(entry, "summary", None)
            or getattr(entry, "description", None)
            or ""
        )

        return {
            "title": title,
            "description": _plain_text(summary),
            "opportunity_type": spec["opportunity_type"],
            "field": spec.get("field"),
            "location": spec.get("location"),
            "url": link,
            "source_name": spec.get("source_name"),
        }

    def run(self, max_entries_per_feed: int = 25) -> dict[str, int]:
        for spec in RSS_FEEDS:
            feed_url = spec["url"]
            try:
                parsed = feedparser.parse(
                    feed_url,
                    request_headers={"User-Agent": "OpportunityFinder/1.0 (+https://github.com/adab-tech/OpportunityFinder)"},
                )
                if getattr(parsed, "bozo", False) and not parsed.entries:
                    logger.warning("RSS parse issue for %s: %s", feed_url, parsed.get("bozo_exception"))
                    continue

                self.stats["feeds"] += 1
                for entry in parsed.entries[:max_entries_per_feed]:
                    self.stats["entries"] += 1
                    row = self._entry_from_feed(entry, spec)
                    if row:
                        self._save(row)
            except Exception as exc:
                logger.error("RSS feed failed %s: %s", feed_url, exc)
                self.stats["errors"] += 1

        logger.info("RSS ingest complete: %s", self.stats)
        return self.stats
