"""Detect opportunities that are already expired, so they never show —
not "usually hidden," never.

Two signals, checked in order:
  1. A parsed `deadline_at` in the past — definitive, always trusted.
  2. No parsed deadline, but the title itself carries an old year (e.g.
     "Total E&P Nigeria CPFA Limited Recruitment 2019") — many scraped
     listing pages are old blog posts about long-closed programs with no
     machine-parseable deadline anywhere on the page. A title year
     strictly before the current year is treated as a strong signal the
     posting is stale, since real ongoing programs are described by their
     current or upcoming intake year, not a past one.

This is deliberately a blunt, conservative check (only fires on an
explicit stale year, never guesses at undated/yearless titles) —
false negatives (a stale posting slips through) are far less harmful
than false positives (a genuinely open opportunity gets hidden).
"""

import re
from datetime import UTC, date
from datetime import datetime as _datetime

_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _current_year() -> int:
    return _datetime.now(UTC).year


def extract_years(text: str) -> list[int]:
    """All plausible 20xx years mentioned in the text."""
    return [int(y) for y in _YEAR_RE.findall(text or "")]


def is_stale_by_title(title: str, reference_year: int | None = None) -> bool:
    """True if the most recent year mentioned in the title is strictly
    before the reference year (defaults to the current year) — e.g. a
    title mentioning only 2019/2021 when it's now 2026. A title with no
    year at all, or one mentioning the current/a future year, is never
    considered stale by this check alone.
    """
    years = extract_years(title)
    if not years:
        return False
    reference_year = reference_year or _current_year()
    return max(years) < reference_year


def is_expired(deadline_at: date | None, title: str, reference_date: date | None = None) -> bool:
    """True if this opportunity should never be shown: its deadline has
    passed, or (absent a parsed deadline) its title carries a stale year.
    """
    reference_date = reference_date or date.today()
    if deadline_at is not None:
        return deadline_at < reference_date
    return is_stale_by_title(title, reference_year=reference_date.year)
