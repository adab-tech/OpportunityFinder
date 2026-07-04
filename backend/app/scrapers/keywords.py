"""
SEO-optimized keyword queries and curated seed sites for each opportunity type.
Queries are crafted using Google search operators to surface high-quality results.
"""

from datetime import UTC, datetime

# ---------------------------------------------------------------------------
# Primary Google search query templates per opportunity type.
# "{year}" is substituted with the current year and the next year at query
# build time (see build_google_queries) so these never go stale — a
# hardcoded "2026" would silently stop matching real listings once 2027
# rolls around, since most program pages label themselves by intake year.
# ---------------------------------------------------------------------------
OPPORTUNITY_KEYWORD_TEMPLATES: dict[str, list[str]] = {
    "scholarship": [
        '"scholarship" "apply now" "{year}"',
        '"fully funded scholarship" "international students" {year}',
        '"scholarship application" "open" "deadline" {year}',
        '"masters scholarship" "{year}" "apply"',
        '"phd scholarship" "{year}" "fully funded"',
        '"undergraduate scholarship" "{year}" "apply"',
        '"scholarship" "call for applications" "{year}"',
        '"merit scholarship" "{year}" "applications open"',
        '"government scholarship" "{year}" "apply online"',
        '"scholarship" "tuition" "stipend" "{year}"',
        '"postgraduate scholarship" "deadline" "{year}"',
        '"women scholarship" "{year}" "apply"',
        '"scholarship" "United States" "apply" "{year}"',
        '"scholarship" "Europe" "apply" "{year}"',
        '"scholarship" "Asia" "apply" "{year}"',
        '"scholarship" "Latin America" "apply" "{year}"',
        '"scholarship" "Middle East" "apply" "{year}"',
    ],
    "fellowship": [
        '"fellowship" "applications open" "{year}"',
        '"research fellowship" "call for applications" {year}',
        '"postdoctoral fellowship" "deadline" "{year}"',
        '"fellowship program" "apply now" "{year}"',
        '"visiting fellowship" "{year}" "apply"',
        '"fellowship" "stipend" "{year}" "international"',
        '"leadership fellowship" "applications" "{year}"',
        '"fellowship" "emerging leaders" "{year}"',
        '"professional fellowship" "apply" "{year}"',
        '"community fellowship" "{year}" "applications"',
        '"fellowship" "United States" "apply" "{year}"',
        '"fellowship" "Europe" "apply" "{year}"',
        '"fellowship" "Asia" "apply" "{year}"',
        '"fellowship" "Latin America" "apply" "{year}"',
    ],
    "grant": [
        '"grant" "call for proposals" "{year}"',
        '"research grant" "applications open" {year}',
        '"small grant" "deadline" "{year}"',
        '"innovation grant" "apply" "{year}"',
        '"community grant" "call for applications" "{year}"',
        '"seed grant" "research" "{year}"',
        '"grant funding" "proposals" "deadline" "{year}"',
        '"project grant" "applications" "open" "{year}"',
        '"travel grant" "apply" "{year}"',
        '"arts grant" "{year}" "applications"',
        '"grant" "United States" "apply" "{year}"',
        '"grant" "Europe" "apply" "{year}"',
        '"grant" "Asia" "apply" "{year}"',
    ],
    "job": [
        '"job opening" "apply now" "{year}"',
        '"now hiring" "application deadline" {year}',
        '"career opportunity" "vacancy" "{year}"',
        '"internship" "paid" "apply" "{year}"',
        '"entry level" "job" "apply" "{year}"',
        '"remote job" "hiring" "apply" "{year}"',
        '"nonprofit" "job opening" "{year}"',
        '"international organization" "vacancy" "{year}"',
        '"united nations" "vacancy" "{year}"',
        '"NGO" "job" "apply" "{year}"',
        '"consultancy" "apply" "{year}"',
        '"junior position" "apply" "{year}"',
        '"remote job" "United States" "apply" "{year}"',
        '"job opening" "Europe" "apply" "{year}"',
        '"job opening" "Asia" "apply" "{year}"',
    ],
}


def _current_and_next_year() -> tuple[int, int]:
    year = datetime.now(UTC).year
    return year, year + 1

# ---------------------------------------------------------------------------
# Curated seed sites with consistent listing pages
# ---------------------------------------------------------------------------
OPPORTUNITY_SITES: dict[str, list[str]] = {
    "scholarship": [
        "https://opportunitydesk.org/category/scholarships/",
        "https://www.scholars4dev.com/category/scholarships/",
        "https://www.opportunitiesforafricans.com/category/scholarships/",
        "https://afterschoolafrica.com/scholarships/",
        "https://www.unjobs.org/themes/scholarships",
    ],
    "fellowship": [
        "https://opportunitydesk.org/category/fellowships/",
        "https://www.opportunitiesforafricans.com/category/fellowships/",
        "https://afterschoolafrica.com/fellowships/",
        "https://www.youthop.com/fellowships",
    ],
    "grant": [
        "https://opportunitydesk.org/category/grants/",
        "https://www.opportunitiesforafricans.com/category/grants/",
        "https://afterschoolafrica.com/grants/",
        "https://www.youthop.com/grants",
    ],
    "job": [
        "https://opportunitydesk.org/category/jobs/",
        "https://www.opportunitiesforafricans.com/category/jobs/",
        "https://reliefweb.int/jobs",
        "https://www.devex.com/jobs",
    ],
}

# ---------------------------------------------------------------------------
# Field detection keyword map
# ---------------------------------------------------------------------------
FIELD_KEYWORDS: dict[str, list[str]] = {
    "STEM": ["science", "technology", "engineering", "mathematics", "physics",
             "chemistry", "biology", "computer", "data", "statistics"],
    "Medicine & Health": ["medicine", "health", "medical", "nursing", "pharmacy",
                          "public health", "dentistry", "epidemiology", "clinical"],
    "Arts & Design": ["art", "design", "music", "visual", "creative", "performing",
                      "film", "theatre", "architecture"],
    "Humanities": ["history", "philosophy", "literature", "linguistics",
                   "cultural studies", "humanities", "archaeology"],
    "Social Sciences": ["psychology", "sociology", "anthropology",
                        "political science", "social work", "gender studies"],
    "Business": ["business", "management", "finance", "economics",
                 "entrepreneurship", "MBA", "accounting", "marketing"],
    "Law": ["law", "legal", "justice", "policy", "human rights", "governance"],
    "Engineering": ["civil engineering", "mechanical", "electrical",
                    "aerospace", "chemical engineering"],
    "Education": ["education", "teaching", "pedagogy", "curriculum",
                  "early childhood", "higher education"],
    "Environment": ["environment", "climate", "sustainability", "ecology",
                    "conservation", "renewable", "green"],
    "Agriculture": ["agriculture", "farming", "food security",
                    "agri", "livestock", "rural development"],
    "Journalism & Media": ["journalism", "media", "communication",
                           "broadcasting", "digital media"],
    "International Development": ["development", "humanitarian", "international",
                                  "NGO", "nonprofit", "aid", "governance"],
}

# ---------------------------------------------------------------------------
# Opportunity-type detection keywords — used to classify entries from
# "mixed" feeds that bundle scholarships, fellowships, grants, and jobs
# together under one RSS stream (e.g. opportunitiesforyouth.org).
# Order matters: checked top-to-bottom, first match wins.
# ---------------------------------------------------------------------------
TYPE_KEYWORDS: dict[str, list[str]] = {
    "scholarship": ["scholarship", "scholarships"],
    "fellowship": ["fellowship", "fellowships", "fellow program",
                   "award", "awards", "prize", "prizes"],
    "grant": ["grant", "grants", "funding opportunity", "call for proposals"],
    # Generic role words (e.g. "officer", "career") are deliberately excluded —
    # they also appear in fellowship/award and grant titles and caused
    # false positives (a research award was mislabeled as a job).
    "job": ["job", "jobs", "vacancy", "vacancies", "hiring", "internship",
            "recruitment", "position available", "now hiring"],
}


def detect_opportunity_type(text: str, default: str = "other") -> str:
    """Classify free text (usually a title) into an opportunity type."""
    text_lower = text.lower()
    for opp_type, kws in TYPE_KEYWORDS.items():
        if any(kw in text_lower for kw in kws):
            return opp_type
    return default


def build_google_queries(opportunity_type: str, extra_keywords: list[str] = None) -> list[str]:
    """Return a list of optimized Google queries for the given opportunity type.

    Each template is expanded for both the current year and next year, so
    listings labelled either way (e.g. a scholarship advertised in 2026
    for a 2027 intake) are covered without editing this file every January.
    """
    templates = OPPORTUNITY_KEYWORD_TEMPLATES.get(opportunity_type, [])
    current_year, next_year = _current_and_next_year()

    queries = [t.format(year=current_year) for t in templates]
    queries += [t.format(year=next_year) for t in templates]

    if extra_keywords:
        for kw in extra_keywords:
            queries.append(f'"{opportunity_type}" "{kw}" "apply"')
    return queries
