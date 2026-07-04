"""Generate a short, original one-line synopsis for each opportunity.

Deliberately rule-based rather than LLM-generated: no external API key,
no per-request cost, no latency, and no dependency that could break the
whole ingest pipeline if a provider has an outage. In line with wanting
this to be sustainable, not something that quietly becomes a recurring
bill or a single point of failure.

Design note: type, field, and location are already shown as separate
badges/tags on each card, and the deadline is already shown as its own
countdown badge. Restating all of that inside the summary sentence too
("A grant in International Development open to applicants in Africa
worth $12,000. Deadline: 19 January 2018.") is pure redundancy — it
looks generic because it *is* generic, just re-serializing fields the
reader can already see. The real job of this function is to surface
what the source text actually says the opportunity is *for*, stripped
of ad boilerplate — the structured-field sentence is only a fallback
for the rare case where no usable description text exists at all.

If you want AI-generated summaries later, this function's signature is a
natural place to swap in an LLM call — every caller already treats the
description as call-once-at-ingest-time text, not something recomputed
on every page view.
"""

import re

_AMOUNT_RE = re.compile(
    r"(up to\s+)?([$£€¥]|KES|USD|GBP|EUR)\s?[\d,]+(?:\.\d+)?(?:\s?(?:million|k|K))?",
)

_TYPE_PHRASING = {
    "scholarship": "A scholarship",
    "fellowship": "A fellowship",
    "grant": "A grant",
    "job": "A job opening",
    "other": "An opportunity",
}

# Sentences that are pure ad/RSS boilerplate, not substance — skip past
# these rather than presenting them as "what this opportunity is about".
_BOILERPLATE_STARTS = (
    "application deadline",
    "the post ",
    "applications are now open",
    "applications open",
    "apply now",
    "deadline:",
    "closing date",
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WORDPRESS_FOOTER_RE = re.compile(r"\s*the post .*? appeared first on .*?\.?\s*$", re.IGNORECASE)


def extract_funding_amount(text: str | None) -> str | None:
    """Pull a funding figure like "$50,000" or "up to €25,000" out of free
    text, so the synopsis can state it plainly instead of hiding it in a
    paragraph the reader has to scan for.
    """
    if not text:
        return None
    match = _AMOUNT_RE.search(text)
    if not match:
        return None
    return match.group(0).strip()


def extract_meaningful_sentence(description: str | None, max_length: int = 220) -> str | None:
    """Return the first substantive sentence from raw description text,
    skipping ad/RSS boilerplate ("Applications are now open for...",
    WordPress's "The post X appeared first on Y" footer, a leading
    deadline restatement). Returns None if nothing usable is found.
    """
    if not description:
        return None

    cleaned = _WORDPRESS_FOOTER_RE.sub("", description).strip()
    if not cleaned:
        return None

    for sentence in _SENTENCE_SPLIT_RE.split(cleaned):
        sentence = sentence.strip()
        if len(sentence) < 40:
            continue
        if sentence.lower().startswith(_BOILERPLATE_STARTS):
            continue
        if len(sentence) > max_length:
            sentence = sentence[: max_length - 1].rsplit(" ", 1)[0] + "…"
        return sentence

    return None


def _structural_fallback(
    title: str,
    opportunity_type: str,
    field: str | None,
    location: str | None,
    description: str | None,
) -> str:
    """Used only when no usable description text exists at all (e.g. a
    bare listing with just a title). Deliberately does not restate the
    deadline — that's already its own badge on the card.
    """
    subject = _TYPE_PHRASING.get(opportunity_type, _TYPE_PHRASING["other"])

    parts = [subject]
    if field:
        parts.append(f"in {field}")
    if location and location.lower() not in {"international", "global"}:
        parts.append(f"open to applicants in {location}")
    else:
        parts.append("open internationally")

    amount = extract_funding_amount(title) or extract_funding_amount(description)
    if amount:
        parts.append(f"worth {amount}")

    return " ".join(parts) + "."


def build_synopsis(
    title: str,
    opportunity_type: str,
    field: str | None = None,
    location: str | None = None,
    deadline: str | None = None,  # noqa: ARG001 — kept for call-site compatibility
    description: str | None = None,
) -> str:
    """Build a short, original sentence describing what this opportunity
    is actually for — preferring real substance from the source text
    (cleaned of ad boilerplate) over restating fields already shown
    elsewhere on the card as badges.
    """
    meaningful = extract_meaningful_sentence(description)
    if meaningful:
        return meaningful

    return _structural_fallback(title, opportunity_type, field, location, description)
