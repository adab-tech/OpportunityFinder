"""Deadline extraction shared by the scraper and RSS ingest paths.

Previously this logic lived only on BaseScraper (instance method), so RSS
feed entries — now the majority of ingested data — never had a deadline
extracted at all. Pulling it out into a plain function lets both paths
use it without instantiating a scraper.
"""

import re

# Ordinal suffixes ("23rd", "1st", "2nd", "3rd", "4th"...) are common in
# real listings ("Application Deadline: September 23rd, 2026") and were
# previously unmatched because \d{1,2} was expected to be followed
# immediately by a comma or space.
_ORDINAL = r"(?:st|nd|rd|th)?"

_DEADLINE_PATTERNS = [
    rf"application\s+deadline[:\s]+([A-Za-z]+ \d{{1,2}}{_ORDINAL},?\s+\d{{4}})",
    rf"deadline\s+for\s+applications?[:\s]+([A-Za-z]+ \d{{1,2}}{_ORDINAL},?\s+\d{{4}})",
    rf"deadline[:\s]+([A-Za-z]+ \d{{1,2}}{_ORDINAL},?\s+\d{{4}})",
    rf"apply\s+by[:\s]+([A-Za-z]+ \d{{1,2}}{_ORDINAL},?\s+\d{{4}})",
    rf"closing\s+date[:\s]+([A-Za-z]+ \d{{1,2}}{_ORDINAL},?\s+\d{{4}})",
    rf"applications?\s+(?:due|close)[:\s]+([A-Za-z]+ \d{{1,2}}{_ORDINAL},?\s+\d{{4}})",
    rf"submission\s+deadline[:\s]+([A-Za-z]+ \d{{1,2}}{_ORDINAL},?\s+\d{{4}})",
    rf"due\s+date[:\s]+([A-Za-z]+ \d{{1,2}}{_ORDINAL},?\s+\d{{4}})",
    # "Deadline: 29 June 2026" (day-month-year order, common in RSS ledes)
    rf"deadline[:\s]+(\d{{1,2}}{_ORDINAL}\s+[A-Za-z]+\s+\d{{4}})",
    rf"application\s+deadline[:\s]+(\d{{1,2}}{_ORDINAL}\s+[A-Za-z]+\s+\d{{4}})",
    # Bare dates as a last resort, only used if no labelled deadline is found.
    rf"(\d{{1,2}}{_ORDINAL}\s+[A-Za-z]{{3,9}}\s+\d{{4}})",
    r"(\d{4}-\d{2}-\d{2})",
    r"(\d{1,2}/\d{1,2}/\d{4})",
]

# Explicitly-worded "no fixed deadline" phrases some listings use — treat
# these as a known non-date signal rather than leaving the field blank
# with no explanation.
_ROLLING_PATTERNS = [
    r"rolling\s+(?:basis|admission|deadline|applications?)",
    r"applications?\s+(?:are\s+)?open\s+year[\s-]round",
    r"no\s+fixed\s+deadline",
    r"until\s+(?:the\s+)?position\s+is\s+filled",
    r"deadline[:\s]+varying",
    r"varying\s+(?:by|per)\s+(?:country|region|programme|program)",
]


def extract_deadline(text: str) -> str | None:
    """Extract a deadline date string (or "Rolling") from raw text.

    Checked in priority order: an explicitly labelled deadline phrase
    beats a bare date, and a bare date beats a "rolling" phrase — a
    listing that says both "deadline: 1 May 2026" and "rolling basis"
    elsewhere should report the concrete date.
    """
    if not text:
        return None

    for pattern in _DEADLINE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()[:100]

    for pattern in _ROLLING_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return "Rolling"

    return None
