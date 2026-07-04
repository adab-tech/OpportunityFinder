"""
SEO-optimized keyword queries and curated seed sites for each opportunity type.
Queries are crafted using Google search operators to surface high-quality results.
"""


# ---------------------------------------------------------------------------
# Primary Google search queries per opportunity type
# ---------------------------------------------------------------------------
OPPORTUNITY_KEYWORDS: dict[str, list[str]] = {
    "scholarship": [
        '"scholarship" "apply now" "2026"',
        '"fully funded scholarship" "international students" 2026',
        '"scholarship application" "open" "deadline" 2026',
        '"masters scholarship" "2026" "apply"',
        '"phd scholarship" "2026" "fully funded"',
        '"undergraduate scholarship" "2026" "apply"',
        '"scholarship" "call for applications" "2026"',
        '"merit scholarship" "2026" "applications open"',
        '"government scholarship" "2026" "apply online"',
        '"scholarship" "tuition" "stipend" "2026"',
        '"postgraduate scholarship" "deadline" "2026"',
        '"women scholarship" "2026" "apply"',
    ],
    "fellowship": [
        '"fellowship" "applications open" "2026"',
        '"research fellowship" "call for applications" 2026',
        '"postdoctoral fellowship" "deadline" "2026"',
        '"fellowship program" "apply now" "2026"',
        '"visiting fellowship" "2026" "apply"',
        '"fellowship" "stipend" "2026" "international"',
        '"leadership fellowship" "applications" "2026"',
        '"fellowship" "emerging leaders" "2026"',
        '"professional fellowship" "apply" "2026"',
        '"community fellowship" "2026" "applications"',
    ],
    "grant": [
        '"grant" "call for proposals" "2026"',
        '"research grant" "applications open" 2026',
        '"small grant" "deadline" "2026"',
        '"innovation grant" "apply" "2026"',
        '"community grant" "call for applications" "2026"',
        '"seed grant" "research" "2026"',
        '"grant funding" "proposals" "deadline" "2026"',
        '"project grant" "applications" "open" "2026"',
        '"travel grant" "apply" "2026"',
        '"arts grant" "2026" "applications"',
    ],
    "job": [
        '"job opening" "apply now" "2026"',
        '"now hiring" "application deadline" 2026',
        '"career opportunity" "vacancy" "2026"',
        '"internship" "paid" "apply" "2026"',
        '"entry level" "job" "apply" "2026"',
        '"remote job" "hiring" "apply" "2026"',
        '"nonprofit" "job opening" "2026"',
        '"international organization" "vacancy" "2026"',
        '"united nations" "vacancy" "2026"',
        '"NGO" "job" "apply" "2026"',
        '"consultancy" "apply" "2026"',
        '"junior position" "apply" "2026"',
    ],
}

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
    """Return a list of optimized Google queries for the given opportunity type."""
    queries = list(OPPORTUNITY_KEYWORDS.get(opportunity_type, []))
    if extra_keywords:
        for kw in extra_keywords:
            queries.append(f'"{opportunity_type}" "{kw}" "apply"')
    return queries
