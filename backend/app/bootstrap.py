"""Populate an empty database and kick off a background scrape on first run."""

import logging
import threading
from typing import Any, Dict, List

from app.database import SessionLocal
from app.models import Opportunity
from app.scrapers.opportunity_scraper import OpportunityScraper
from app.scrapers.rss_ingest import RssIngestor
from app.config import settings

logger = logging.getLogger(__name__)

# Curated, real public opportunity pages (stable listing / program hubs).
CURATED_SEEDS: List[Dict[str, Any]] = [
    {
        "title": "Fulbright Foreign Student Program",
        "description": "Graduate study in the United States for international students.",
        "opportunity_type": "scholarship",
        "field": "International Development",
        "location": "USA",
        "url": "https://foreign.fulbrightonline.org/",
        "source_name": "Fulbright",
    },
    {
        "title": "Chevening Scholarships",
        "description": "UK government scholarships for future leaders from eligible countries.",
        "opportunity_type": "scholarship",
        "field": "International Development",
        "location": "UK",
        "url": "https://www.chevening.org/apply/",
        "source_name": "Chevening",
    },
    {
        "title": "DAAD Scholarships",
        "description": "Funding for study and research in Germany.",
        "opportunity_type": "scholarship",
        "field": "Education",
        "location": "Germany",
        "url": "https://www.daad.de/en/study-and-research-in-germany/scholarships/",
        "source_name": "DAAD",
    },
    {
        "title": "Erasmus Mundus Joint Masters",
        "description": "EU-funded international master's programs across Europe.",
        "opportunity_type": "scholarship",
        "field": "Education",
        "location": "Europe",
        "url": "https://www.eacea.ec.europa.eu/scholarships/emjmd-catalogue_en",
        "source_name": "European Commission",
    },
    {
        "title": "Commonwealth Scholarships",
        "description": "Scholarships for citizens of Commonwealth countries.",
        "opportunity_type": "scholarship",
        "field": "International Development",
        "location": "International",
        "url": "https://cscuk.fcdo.gov.uk/scholarships/",
        "source_name": "Commonwealth",
    },
    {
        "title": "Rhodes Scholarships at Oxford",
        "description": "Postgraduate awards for outstanding students at the University of Oxford.",
        "opportunity_type": "scholarship",
        "field": "Humanities",
        "location": "UK",
        "url": "https://www.rhodeshouse.ox.ac.uk/scholarships/the-rhodes-scholarship/",
        "source_name": "Rhodes Trust",
    },
    {
        "title": "Gates Cambridge Scholarship",
        "description": "Full-cost scholarships for graduate study at the University of Cambridge.",
        "opportunity_type": "scholarship",
        "field": "STEM",
        "location": "UK",
        "url": "https://www.gatescambridge.org/apply",
        "source_name": "Gates Cambridge",
    },
    {
        "title": "Scholars4Dev — Latest Scholarships",
        "description": "Updated listings of international scholarships for developing-country students.",
        "opportunity_type": "scholarship",
        "field": "International Development",
        "location": "International",
        "url": "https://www.scholars4dev.com/category/scholarships/",
        "source_name": "Scholars4Dev",
    },
    {
        "title": "Opportunity Desk — Fellowships",
        "description": "Curated fellowship opportunities worldwide.",
        "opportunity_type": "fellowship",
        "field": "International Development",
        "location": "International",
        "url": "https://opportunitydesk.org/category/fellowships/",
        "source_name": "Opportunity Desk",
    },
    {
        "title": "AfterSchool Africa — Fellowships",
        "description": "Fellowship programs for African students and professionals.",
        "opportunity_type": "fellowship",
        "field": "International Development",
        "location": "Africa",
        "url": "https://afterschoolafrica.com/fellowships/",
        "source_name": "AfterSchool Africa",
    },
    {
        "title": "Opportunity Desk — Grants",
        "description": "Grant calls for nonprofits, researchers, and social ventures.",
        "opportunity_type": "grant",
        "field": "International Development",
        "location": "International",
        "url": "https://opportunitydesk.org/category/grants/",
        "source_name": "Opportunity Desk",
    },
    {
        "title": "ReliefWeb Jobs",
        "description": "Humanitarian and development job openings globally.",
        "opportunity_type": "job",
        "field": "International Development",
        "location": "International",
        "url": "https://reliefweb.int/jobs",
        "source_name": "ReliefWeb",
    },
    {
        "title": "Devex Jobs",
        "description": "International development and global health careers.",
        "opportunity_type": "job",
        "field": "International Development",
        "location": "International",
        "url": "https://www.devex.com/jobs",
        "source_name": "Devex",
    },
    {
        "title": "UN Careers Portal",
        "description": "United Nations staff and consultant vacancies.",
        "opportunity_type": "job",
        "field": "International Development",
        "location": "International",
        "url": "https://careers.un.org/",
        "source_name": "United Nations",
    },
    {
        "title": "Opportunities for Africans — Jobs",
        "description": "Jobs and internships relevant to African professionals.",
        "opportunity_type": "job",
        "field": "International Development",
        "location": "Africa",
        "url": "https://www.opportunitiesforafricans.com/category/jobs/",
        "source_name": "Opportunities for Africans",
    },
]


def seed_curated_opportunities(db) -> int:
    added = 0
    for row in CURATED_SEEDS:
        url = row["url"].strip()
        if db.query(Opportunity).filter(Opportunity.url == url).first():
            continue
        db.add(
            Opportunity(
                title=row["title"][:500],
                description=(row.get("description") or "")[:2000],
                opportunity_type=row["opportunity_type"],
                field=row.get("field"),
                location=row.get("location"),
                url=url[:2000],
                source_name=row.get("source_name"),
                is_active=True,
            )
        )
        added += 1
    if added:
        db.commit()
    return added


def run_rss_ingest() -> None:
    db = SessionLocal()
    try:
        stats = RssIngestor(db).run(
            max_entries_per_feed=settings.RSS_MAX_ENTRIES_PER_FEED
        )
        logger.info("Startup RSS ingest finished: %s", stats)
    except Exception as exc:
        logger.error("Startup RSS ingest failed: %s", exc)
    finally:
        db.close()


def run_background_scrape(max_results: int = 40) -> None:
    db = SessionLocal()
    try:
        scraper = OpportunityScraper(db)
        stats = scraper.run(max_results=max_results)
        logger.info("Background scrape finished: %s", stats)
    except Exception as exc:
        logger.error("Background scrape failed: %s", exc)
    finally:
        db.close()


def run_startup_tasks() -> None:
    db = SessionLocal()
    try:
        total = db.query(Opportunity).filter(Opportunity.is_active == True).count()
        if total == 0:
            seeded = seed_curated_opportunities(db)
            logger.info("Seeded %s curated opportunities.", seeded)
            total = db.query(Opportunity).filter(Opportunity.is_active == True).count()

        threading.Thread(target=run_rss_ingest, daemon=True).start()

        if total < 25:
            threading.Thread(
                target=run_background_scrape,
                kwargs={"max_results": 40},
                daemon=True,
            ).start()
            logger.info("Started background scrape (current total=%s).", total)
    finally:
        db.close()
