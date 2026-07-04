"""Curated RSS/Atom feeds — stable, polite data sources for production ingest."""

from typing import TypedDict


class FeedSpec(TypedDict):
    url: str
    opportunity_type: str
    source_name: str
    field: str
    location: str


RSS_FEEDS: list[FeedSpec] = [
    {
        "url": "https://reliefweb.int/jobs/rss.xml",
        "opportunity_type": "job",
        "source_name": "ReliefWeb",
        "field": "International Development",
        "location": "International",
    },
    {
        "url": "https://www.scholars4dev.com/feed/",
        "opportunity_type": "scholarship",
        "source_name": "Scholars4Dev",
        "field": "International Development",
        "location": "International",
    },
    {
        "url": "https://opportunitydesk.org/feed/",
        "opportunity_type": "fellowship",
        "source_name": "Opportunity Desk",
        "field": "International Development",
        "location": "International",
    },
    {
        "url": "https://afterschoolafrica.com/feed/",
        "opportunity_type": "scholarship",
        "source_name": "AfterSchool Africa",
        "field": "International Development",
        "location": "Africa",
    },
    {
        "url": "https://www.opportunitiesforafricans.com/feed/",
        "opportunity_type": "job",
        "source_name": "Opportunities for Africans",
        "field": "International Development",
        "location": "Africa",
    },
    {
        # This feed bundles scholarships, fellowships, grants, and jobs
        # together — "mixed" tells the ingestor to classify each entry
        # individually by title keywords (see keywords.detect_opportunity_type).
        "url": "https://opportunitiesforyouth.org/feed/",
        "opportunity_type": "mixed",
        "source_name": "Opportunities For Youth",
        "field": "International Development",
        "location": "International",
    },
]
