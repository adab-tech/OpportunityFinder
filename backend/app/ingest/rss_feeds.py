"""Curated RSS/Atom feeds — stable, polite data sources for production ingest.

Every URL here has been manually verified to return HTTP 200 with parseable
entries. Where a source publishes per-category feeds (scholarships/
fellowships/grants/jobs as separate URLs), prefer those over the site's
generic feed: the type is then guaranteed correct instead of guessed.
Only use "mixed" (per-entry classification via keywords.detect_opportunity_type)
for sites that bundle several opportunity types into a single feed.
"""

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
        "url": "https://opportunitydesk.org/category/fellowships/feed/",
        "opportunity_type": "fellowship",
        "source_name": "Opportunity Desk",
        "field": "International Development",
        "location": "International",
    },
    {
        "url": "https://opportunitydesk.org/category/grants/feed/",
        "opportunity_type": "grant",
        "source_name": "Opportunity Desk",
        "field": "International Development",
        "location": "International",
    },
    {
        # Opportunity Desk's scholarships/jobs category feeds return no
        # entries, so fall back to the generic feed (mixed) for that coverage.
        "url": "https://opportunitydesk.org/feed/",
        "opportunity_type": "mixed",
        "source_name": "Opportunity Desk",
        "field": "International Development",
        "location": "International",
    },
    {
        "url": "https://afterschoolafrica.com/category/fellowships/feed/",
        "opportunity_type": "fellowship",
        "source_name": "AfterSchool Africa",
        "field": "International Development",
        "location": "Africa",
    },
    {
        # AfterSchool Africa's scholarships category feed is unreliable
        # (intermittently empty), so use the generic feed as a mixed
        # fallback rather than assuming everything is a scholarship.
        "url": "https://afterschoolafrica.com/feed/",
        "opportunity_type": "mixed",
        "source_name": "AfterSchool Africa",
        "field": "International Development",
        "location": "Africa",
    },
    {
        "url": "https://www.opportunitiesforafricans.com/category/scholarships/feed/",
        "opportunity_type": "scholarship",
        "source_name": "Opportunities for Africans",
        "field": "International Development",
        "location": "Africa",
    },
    {
        "url": "https://www.opportunitiesforafricans.com/category/fellowships/feed/",
        "opportunity_type": "fellowship",
        "source_name": "Opportunities for Africans",
        "field": "International Development",
        "location": "Africa",
    },
    {
        "url": "https://www.opportunitiesforafricans.com/category/grants/feed/",
        "opportunity_type": "grant",
        "source_name": "Opportunities for Africans",
        "field": "International Development",
        "location": "Africa",
    },
    {
        "url": "https://www.opportunitiesforafricans.com/category/jobs/feed/",
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
