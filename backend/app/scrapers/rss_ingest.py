"""Ingest opportunities from curated RSS/Atom feeds."""

import logging
import re
from html import unescape
from typing import Any

import feedparser
from sqlalchemy.orm import Session

from app.ingest.rss_feeds import RSS_FEEDS
from app.models import Opportunity
from app.scrapers.deadline_utils import extract_deadline, parse_deadline_date
from app.scrapers.dedup import normalize_title
from app.scrapers.expiry import is_expired
from app.scrapers.keywords import detect_opportunity_type
from app.scrapers.quality import is_low_quality_title
from app.scrapers.synopsis import build_synopsis
from app.scrapers.url_utils import clean_url

logger = logging.getLogger(__name__)

_BLOCK_TAG_RE = re.compile(r"<\s*(br|/p|/div|/li)\s*/?\s*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _plain_text(value: str | None, limit: int = 2000) -> str | None:
    if not value:
        return None
    # Convert block-level HTML boundaries into a sentence break *before*
    # stripping tags — otherwise "Letter of Intent Deadline Date: X<br
    # />Program Guidelines: Y<br /><p>The actual description..." collapses
    # into one run-on sentence with no punctuation to split on, and the
    # synopsis generator can't tell where the real content starts.
    text = _BLOCK_TAG_RE.sub(". ", value)
    text = unescape(_TAG_RE.sub(" ", text))
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\.\s*\.", ".", text)  # collapse ". ." runs from adjacent boundaries
    if not text:
        return None
    return text[:limit]


class RssIngestor:
    def __init__(self, db: Session):
        self.db = db
        self.stats: dict[str, int] = {
            "feeds": 0, "entries": 0, "saved": 0, "errors": 0, "duplicates": 0,
        }

    def _url_exists(self, url: str) -> bool:
        return (
            self.db.query(Opportunity).filter(Opportunity.url == url).first()
            is not None
        )

    def _is_cross_source_duplicate(self, title_normalized: str) -> bool:
        """True if an active opportunity with the same normalized title
        already exists (a repost of the same listing under a different
        URL from another aggregator) — see app/scrapers/dedup.py.
        """
        return (
            self.db.query(Opportunity)
            .filter(
                Opportunity.title_normalized == title_normalized,
                Opportunity.is_active.is_(True),
            )
            .first()
            is not None
        )

    def _save(self, data: dict[str, Any]) -> bool:
        url = clean_url(data.get("url"))
        title = (data.get("title") or "").strip()
        if not url or not title or len(title) < 5:
            return False
        if is_low_quality_title(title):
            return False
        if self._url_exists(url):
            return False

        title_normalized = normalize_title(title)
        if self._is_cross_source_duplicate(title_normalized):
            self.stats["duplicates"] += 1
            return False

        deadline_at = data.get("deadline_at")
        # Never activate something that's already expired — a stale
        # deadline or an old year baked into the title (e.g. a 2019
        # recruitment post with no parseable deadline anywhere on the
        # page) must not show, full stop.
        active = not is_expired(deadline_at, title)

        try:
            self.db.add(
                Opportunity(
                    title=title[:500],
                    title_normalized=title_normalized,
                    description=_plain_text(data.get("description")),
                    summary=data.get("summary"),
                    opportunity_type=data.get("opportunity_type", "other"),
                    field=data.get("field"),
                    location=data.get("location"),
                    deadline=data.get("deadline"),
                    deadline_at=deadline_at,
                    url=url[:2000],
                    source_name=data.get("source_name"),
                    is_active=active,
                    # Curated RSS feeds are a pre-vetted trust tier —
                    # explicit, not just relying on the column default, so
                    # a future reader doesn't have to guess.
                    review_status="approved",
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

        raw_summary = (
            getattr(entry, "summary", None)
            or getattr(entry, "description", None)
            or ""
        )

        opportunity_type = spec["opportunity_type"]
        if opportunity_type == "mixed":
            opportunity_type = detect_opportunity_type(title)

        plain_description = _plain_text(raw_summary)
        deadline = extract_deadline(f"{title} {plain_description or ''}")
        field = spec.get("field")
        location = spec.get("location")

        return {
            "title": title,
            "description": plain_description,
            "summary": build_synopsis(
                title, opportunity_type, field, location, deadline, plain_description
            ),
            "opportunity_type": opportunity_type,
            "field": field,
            "location": location,
            "deadline": deadline,
            "deadline_at": parse_deadline_date(deadline),
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
