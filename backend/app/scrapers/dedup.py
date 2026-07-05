"""Cross-source duplicate detection.

The same opportunity is frequently reposted verbatim by multiple
aggregator sites under different URLs (e.g. a DAAD scholarship
announcement copied by both Opportunity Desk and Opportunities for
Africans). The existing unique constraint on `url` only catches exact
re-scrapes of the same page — it does nothing for a genuine repost
under a different URL, which shows up to a user as the same
opportunity appearing twice and quietly erodes trust in the listings.

This is deliberately conservative: an *exact* normalized-title match
(case/punctuation/whitespace-insensitive), not fuzzy similarity
scoring. Fuzzy matching risks merging two genuinely different
opportunities (e.g. a 2026 cohort and a 2027 cohort of the same
program have different titles and must stay distinct) — an exact
match on the normalized title only fires when the source text was
copied verbatim, which is the common real-world case.
"""

import re

_NON_ALNUM_RE = re.compile(r"[^a-z0-9\s]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation, and collapse whitespace so titles
    that differ only in case or punctuation compare equal. Deliberately
    keeps year digits — stripping them would risk conflating two
    genuinely different cohorts of the same program.
    """
    normalized = _NON_ALNUM_RE.sub("", title.lower())
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized[:600]
