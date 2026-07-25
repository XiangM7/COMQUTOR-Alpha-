"""Deterministic, regex-only extraction of explicit "date + USD price"
mentions from ``structured_agent_outputs.json`` records.

No LLM, no ticker guessing, no percentage/EPS/revenue/market-cap/price-target
misclassification. A sentence with no explicit ``$`` price or no explicit
date is simply skipped -- this module never guesses a comparison target.
"""

from __future__ import annotations

import datetime as dt
import re

from comqutor_alpha.data_sanity.schema import (
    DATE_RESOLUTION_ANALYSIS_YEAR_INFERRED,
    DATE_RESOLUTION_EXPLICIT_YEAR,
    DATE_RESOLUTION_PREVIOUS_YEAR_INFERRED,
    MAX_SOURCE_TEXT_CHARS,
    PRICE_SEMANTICS_CLOSE,
    PRICE_SEMANTICS_FELL_TO,
    PRICE_SEMANTICS_GENERIC,
    PRICE_SEMANTICS_OPEN,
    PRICE_SEMANTICS_PEAKED,
    PRICE_SEMANTICS_REACHED,
    PRICE_SEMANTICS_TRADED,
)

# Sentences carrying any of these are never treated as a historical stock
# price mention, regardless of how price-like the $ amount looks -- EPS,
# revenue, market cap, and price targets are not historical trade prices,
# and a bare percentage is never a price.
_DISQUALIFYING_TERMS = (
    "eps",
    "earnings per share",
    "revenue",
    "market cap",
    "price target",
    "%",
)

_MONTH_ALT = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?"
    r"|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_MONTH_LOOKUP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
_ISO_DATE = r"\d{4}-\d{2}-\d{2}"
_MONTH_DAY_YEAR = rf"{_MONTH_ALT}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s*\d{{4}})?"
_DATE_ALT = rf"(?:{_ISO_DATE}|{_MONTH_DAY_YEAR})"
_PRICE = r"\$\s?\d{1,6}(?:\.\d{1,4})?"

_VERB_TO_SEMANTICS = {
    "opened at": PRICE_SEMANTICS_OPEN,
    "open of": PRICE_SEMANTICS_OPEN,
    "closed at": PRICE_SEMANTICS_CLOSE,
    "close of": PRICE_SEMANTICS_CLOSE,
    "traded at": PRICE_SEMANTICS_TRADED,
    "reached": PRICE_SEMANTICS_REACHED,
    "peaked at": PRICE_SEMANTICS_PEAKED,
    "fell to": PRICE_SEMANTICS_FELL_TO,
}

_VERB_PRICE_DATE_PATTERN = re.compile(
    r"(?i)\b(opened at|open of|closed at|close of|traded at|reached|peaked at|fell to)\s+"
    rf"\$\s?(\d{{1,6}}(?:\.\d{{1,4}})?)\s+on\s+({_DATE_ALT})\b"
)
_DATE_FIRST_PATTERN = re.compile(
    rf"(?i)\b(?:on\s+)?({_DATE_ALT})\b[^.$]{{0,40}}?\b(open|close)\s+was\s+\$\s?(\d{{1,6}}(?:\.\d{{1,4}})?)"
)
_BARE_PRICE_DATE_PATTERN = re.compile(
    rf"(?i)\$\s?(\d{{1,6}}(?:\.\d{{1,4}})?)\s+on\s+({_DATE_ALT})\b"
)


def _is_disqualified(sentence: str) -> bool:
    lowered = sentence.lower()
    return any(term in lowered for term in _DISQUALIFYING_TERMS)


def _split_sentences(text: str) -> list[str]:
    collapsed = re.sub(r"\s+", " ", text or "").strip()
    if not collapsed:
        return []
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", collapsed) if s.strip()]


def _parse_date_text(date_text: str, analysis_date: dt.date):
    """Returns ``(date, date_resolution)`` or ``None`` if unparseable."""
    text = date_text.strip()
    iso_match = re.fullmatch(_ISO_DATE, text)
    if iso_match:
        year, month, day = (int(part) for part in text.split("-"))
        try:
            return dt.date(year, month, day), DATE_RESOLUTION_EXPLICIT_YEAR
        except ValueError:
            return None

    md_match = re.fullmatch(
        rf"({_MONTH_ALT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s*(\d{{4}}))?",
        text,
        re.IGNORECASE,
    )
    if not md_match:
        return None
    month_name, day_str, year_str = md_match.groups()
    month = _MONTH_LOOKUP.get(month_name.lower().rstrip("."))
    if month is None:
        return None
    day = int(day_str)

    if year_str:
        try:
            return dt.date(int(year_str), month, day), DATE_RESOLUTION_EXPLICIT_YEAR
        except ValueError:
            return None

    # No explicit year: rule 1 use analysis_date.year, rule 2 if that lands
    # after analysis_date, fall back to the previous year -- always recorded
    # as inferred, never silently treated as an explicit date.
    try:
        candidate = dt.date(analysis_date.year, month, day)
    except ValueError:
        return None
    if candidate > analysis_date:
        try:
            candidate = dt.date(analysis_date.year - 1, month, day)
        except ValueError:
            return None
        return candidate, DATE_RESOLUTION_PREVIOUS_YEAR_INFERRED
    return candidate, DATE_RESOLUTION_ANALYSIS_YEAR_INFERRED


def _match_price_date(sentence: str):
    """Returns ``(price, price_semantics, date_text)`` or ``None``."""
    match = _VERB_PRICE_DATE_PATTERN.search(sentence)
    if match:
        verb, price_str, date_text = match.groups()
        return float(price_str), _VERB_TO_SEMANTICS[verb.lower()], date_text

    match = _DATE_FIRST_PATTERN.search(sentence)
    if match:
        date_text, verb, price_str = match.groups()
        semantics = PRICE_SEMANTICS_OPEN if verb.lower() == "open" else PRICE_SEMANTICS_CLOSE
        return float(price_str), semantics, date_text

    match = _BARE_PRICE_DATE_PATTERN.search(sentence)
    if match:
        price_str, date_text = match.groups()
        return float(price_str), PRICE_SEMANTICS_GENERIC, date_text

    return None


def extract_reported_prices(structured_records, analysis_date: dt.date) -> list[dict]:
    """Pure, deterministic extraction over already-persisted structured
    claim records. Never raises on malformed input -- unparseable records
    are simply skipped. Ticker is never guessed or attached here; every
    record in a run's structured_agent_outputs.json already belongs to that
    run's single ticker."""
    results: list[dict] = []
    for record in structured_records or []:
        if not isinstance(record, dict):
            continue
        claim_id = record.get("claim_id")
        agent = record.get("agent")
        claim_text = str(record.get("claim") or "")
        evidence_text = str(record.get("evidence") or "")
        combined = claim_text if claim_text == evidence_text else f"{claim_text} {evidence_text}".strip()

        for sentence in _split_sentences(combined):
            if _is_disqualified(sentence):
                continue
            matched = _match_price_date(sentence)
            if matched is None:
                continue
            price, semantics, date_text = matched
            resolved = _parse_date_text(date_text, analysis_date)
            if resolved is None:
                continue
            reported_date, date_resolution = resolved
            results.append(
                {
                    "claim_id": claim_id,
                    "source_agent": agent,
                    "reported_date": reported_date.isoformat(),
                    "date_resolution": date_resolution,
                    "reported_price": price,
                    "price_semantics": semantics,
                    "source_text": sentence[:MAX_SOURCE_TEXT_CHARS],
                }
            )
    return results
