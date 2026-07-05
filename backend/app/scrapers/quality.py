"""Content-relevance filtering for scraped/searched opportunities.

Broader web/search discovery (Google, You.com) surfaces two distinct
failure modes that a plain junk-blocklist doesn't catch:

1. Completely off-topic content — sports scores, video game patch
   notes, local council stories, stock market news, election coverage
   — that happens to match a search query because it contains an
   ambiguous word like "grant" (used as a verb: "county grants
   extension") or "deadline" (a sports trade deadline).
2. Real opportunity-adjacent pages that aren't a specific, actionable
   listing: page-navigation chrome ("Breadcrumb", "Quick Links"),
   roundup/listicle blog posts ("50+ Scholarships for College
   Students", "Top Remote Tech Jobs"), and past-tense announcements
   about who already won ("Bush Foundation announces fellowship
   recipients").

Earlier version of this module also *required* the title to contain
scholarship/grant/fellowship vocabulary to be accepted. That was wrong:
real, specific, well-known programs (Fulbright Foreign Student Program,
Erasmus Mundus Joint Masters, NSF CAREER, Google Africa Applied AI Lab,
named foundation grants, real job postings) routinely don't repeat that
vocabulary in their title at all — they came from an opportunity-focused
feed or a targeted search query, so relevance is already established by
context, not by title wording. Requiring it killed far more real listings
than it caught junk. Off-topic content is instead recognized by concrete
negative signals (sports/gaming/local-politics/markets phrasing) below.

Deliberately biased toward false negatives over false positives: it's
better to let a handful of low-value pages through than to reject a
real listing that doesn't happen to use scholarship vocabulary.
"""

import re

# Signals of a generic informational/meta page about a topic in general,
# not one specific opportunity — reject regardless of other signals.
_GENERIC_INFO_PAGE_SIGNALS = (
    "timeline", "planning guide", "complete guide", "guide and list",
    "updated guide", "deadlines and timelines", "database",
)

# Past-tense announcements about who already won — not an open call,
# unless a forward-looking cue is also present (e.g. an article that
# both recaps last year's winners and links to this year's open call).
_ANNOUNCEMENT_SIGNALS = ("awarded", "recipients", "recipient", "announces", "announced", "winner", "winners")
_FORWARD_LOOKING_SIGNALS = ("apply", "application", "call for", "deadline", "open")

# Concrete off-topic content that search discovery surfaces because a
# generic word ("grant", "deadline", "award") coincides with the query,
# even though the story has nothing to do with an opportunity listing:
# sports trades/scores, video game updates, local politics/council
# stories, markets/finance news, entertainment coverage.
_OFF_TOPIC_SIGNALS = (
    "trade deadline", "lockout", "playoffs", "quarterback", "touchdown",
    "box score", "series win", "tier list", "patch notes",
    "homeless encampment", "zoning board", "property tax", "city council",
    "county council", "ballot measure", "retirement watch", "senator",
    "stock market news", "worth the risk", "book adaptations",
    "résumé claimed", "resume claimed", "military honors",
)

# Page-navigation chrome, category labels, and other non-listing pages —
# not opportunities at all.
_EXACT_BLOCKLIST = {
    "please wait", "breadcrumb", "quick links", "mobile navigation",
    "main navigation", "sidebar", "scholarship", "scholarships", "fellowship",
    "fellowships", "grant", "grants", "job", "jobs", "internship",
    "internships", "call for applications", "grants for ngos",
    "what are you looking for", "what are you looking for?",
    "costs & financial aid", "costs and financial aid",
    "scholarship programs", "fighting student debt",
    "the scholarship collective", "the scholarship collective ®",
    "opportunities", "careers and opportunities", "entry-level opportunities",
    "entry level opportunities", "program components", "javascript is disabled",
    "find a job", "start your career with impact", "shape america's future",
}

_BROWSING_RE = re.compile(r"^browsing:?\s", re.IGNORECASE)
_AUTHOR_RE = re.compile(r"^author:\s", re.IGNORECASE)
_SIGNUP_RE = re.compile(r"^sign\s+up\s+(to|for)\b", re.IGNORECASE)

# A listicle/roundup almost always starts with either a small count
# ("15", "22", "44") or a large count with "+" ("50+", "8317+") followed
# somewhere shortly after by a plural opportunity/job noun. A bare 4-digit
# year at the start (e.g. "2026 Kresge Fellowships") is NOT a listicle —
# distinguished by requiring either <=3 digits or an explicit "+".
_LISTICLE_NUMERIC_RE = re.compile(
    r"^(?:\d{1,3}(?!\d)|\d[\d,]*\+)\b.{0,60}?\b(scholarships|fellowships|grants|programs|opportunities|jobs|careers)\b",
    re.IGNORECASE,
)
_TOP_BEST_RE = re.compile(
    r"\b(top|best)\b.{0,80}?\b(scholarships|fellowships|grants|programs|jobs|careers)\b", re.IGNORECASE
)
_LIST_OF_RE = re.compile(r"\blist\s+of\s+(scholarships|fellowships|grants|programs)\b", re.IGNORECASE)
# Generic "state of the job market" roundup articles — not one specific
# listing, e.g. "20 Jobs That Will Be in Demand in 2026", "2026 Workforce
# Forecast: Where the Jobs Will Be", "These 12 careers are your best chance".
_JOB_MARKET_ROUNDUP_RE = re.compile(
    r"\b(jobs? (that will be|for)|workforce forecast|best chance to get a job|"
    r"most in-demand|fastest-growing industries|in-demand jobs|best time of year to apply)\b",
    re.IGNORECASE,
)


def _is_past_announcement(normalized: str) -> bool:
    has_announcement = any(sig in normalized for sig in _ANNOUNCEMENT_SIGNALS)
    if not has_announcement:
        return False
    has_forward_looking = any(sig in normalized for sig in _FORWARD_LOOKING_SIGNALS)
    return not has_forward_looking


def is_low_quality_title(title: str) -> bool:
    """True if this title should be rejected: page-navigation chrome, a
    roundup/listicle article, a past-tense "here's who already won"
    announcement, concrete off-topic content (sports/gaming/local-
    politics/markets), or a generic "state of the job market" piece.
    """
    if not title or len(title.strip()) < 3:
        return True
    normalized = title.strip().lower()

    if normalized in _EXACT_BLOCKLIST:
        return True
    if _BROWSING_RE.match(normalized) or _AUTHOR_RE.match(normalized) or _SIGNUP_RE.match(normalized):
        return True
    if _LISTICLE_NUMERIC_RE.search(normalized):
        return True
    if _TOP_BEST_RE.search(normalized):
        return True
    if _LIST_OF_RE.search(normalized):
        return True
    if _JOB_MARKET_ROUNDUP_RE.search(normalized):
        return True
    if any(signal in normalized for signal in _GENERIC_INFO_PAGE_SIGNALS):
        return True
    if any(signal in normalized for signal in _OFF_TOPIC_SIGNALS):
        return True
    if _is_past_announcement(normalized):
        return True

    return False
