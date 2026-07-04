"""Generate a short, original one-line synopsis for each opportunity.

Deliberately rule-based rather than LLM-generated: no external API key,
no per-request cost, no latency, and no dependency that could break the
whole ingest pipeline if a provider has an outage. It reads worse than a
well-tuned language model, but it is honest, free, and always available —
in line with wanting this to be sustainable, not something that quietly
becomes a recurring bill or a single point of failure.

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


def build_synopsis(
    title: str,
    opportunity_type: str,
    field: str | None = None,
    location: str | None = None,
    deadline: str | None = None,
    description: str | None = None,
) -> str:
    """Build a short, original sentence describing this opportunity from
    its already-parsed fields — not a copy of the source's own text.
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

    sentence = " ".join(parts) + "."

    if deadline and deadline != "Rolling":
        sentence += f" Deadline: {deadline}."
    elif deadline == "Rolling":
        sentence += " Applications are accepted on a rolling basis."

    return sentence
