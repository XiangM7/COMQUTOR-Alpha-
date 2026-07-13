"""Shared deterministic factor-label normalization for the Week 2 structure engine.

alpha_mapper.py and structure_extractor.py both need to turn free-text factor
aliases ("artificial intelligence demand") into the same canonical label
("AI Demand"). Keeping that logic here (instead of one module importing it
from the other) keeps the two modules independent and avoids a circular
import between them.
"""

from __future__ import annotations

import re
from typing import Any

# Mapping of canonical factor labels to known aliases (case-insensitive, whitespace-insensitive).
FACTOR_ALIASES = {
    "AI Demand": (
        "ai demand",
        "artificial intelligence demand",
        "ai training demand",
        "model training demand",
    ),
    "AI CapEx": (
        "ai capex",
        "ai capital spending",
        "cloud capex",
        "hyperscaler capex",
        "infrastructure spending",
    ),
    "GPU Demand": (
        "gpu demand",
        "accelerator demand",
        "compute demand",
        "demand for accelerators",
        "demand for gpus",
    ),
    "Datacenter CapEx": (
        "datacenter capex",
        "data center capex",
        "datacenter spending",
        "data center spending",
        "power and cooling",
        "networking orders",
        "server demand",
        "ai infrastructure spending",
        "data center infrastructure",
    ),
    "AI Infrastructure": (
        "ai infrastructure",
        "sovereign ai",
        "government ai infrastructure",
        "defense ai infrastructure",
    ),
    "Revenue Growth": (
        "revenue growth",
        "revenue acceleration",
        "sales growth",
        "guidance raised",
        "beat and raise",
        "eps revisions",
        "addressable market",
        "revenue runway",
        "booked revenue",
    ),
    "Valuation Risk": (
        "valuation risk",
        "rich valuation",
        "high valuation",
        "multiple compression",
        "priced for perfection",
        "expensive growth",
    ),
    "Recession Risk": (
        "recession risk",
        "economic slowdown",
        "credit spreads",
        "widening spreads",
        "pmi weaken",
        "default risk",
    ),
    "Liquidity Expansion": (
        "liquidity expansion",
        "liquidity improves",
        "cash moves into risk assets",
        "reserves rise",
        "money supply",
        "risk appetite",
    ),
    "Narrative Momentum": (
        "narrative momentum",
        "investor attention",
        "media attention",
        "crowded trade",
        "reflexive flows",
        "theme flows",
        "price momentum",
    ),
    "Semiconductor Cycle": (
        "semiconductor cycle",
        "chip cycle",
        "inventory recovery",
        "inventory improves",
        "chip demand",
        "wafer orders",
        "asp stabilizes",
    ),
    "Rate Cut Cycle": (
        "rate cut",
        "falling rates",
        "lower rates",
        "fed cut",
        "easing cycle",
        "discount rates fall",
        "treasury yields fall",
    ),
    "Inference Demand": (
        "inference demand",
        "inference workload",
        "enterprise ai",
        "ai agents",
        "token generation",
        "copilot usage",
    ),
}

# Mapping of canonical factor labels to their corresponding alpha weights.
def normalize_text(value: Any) -> str:
    """Lowercase and collapse a value down to plain alphanumeric words."""
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9%$]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()

# Check if a term is present in a normalized text.
def term_in_text(term: str, text: str) -> bool:
    """Whole word/phrase match of a normalized term inside already-normalized text."""
    term = normalize_text(term)
    if not term:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None

# Normalize a raw factor string to its canonical label.
def normalize_factor_label(value: Any) -> str:
    """Map a raw factor string (canonical name or known alias) to its canonical label.

    Unknown but non-empty values fall back to a title-cased rendering rather
    than being silently dropped; empty values return "Unknown".
    """
    text = normalize_text(value)
    if not text:
        return "Unknown"
    for factor, aliases in FACTOR_ALIASES.items():
        terms = (factor, *aliases)
        if any(normalize_text(term) == text for term in terms):
            return factor
    return " ".join(part.capitalize() for part in text.split())

# Extract known factors from free text.
def extract_known_factors_from_text(text: Any) -> list[str]:
    """Return canonical factor labels whose aliases appear in free text."""
    normalized = normalize_text(text)
    if not normalized:
        return []
    factors = []
    for factor, aliases in FACTOR_ALIASES.items():
        if any(term_in_text(alias, normalized) for alias in aliases):
            factors.append(factor)
    return factors

# Find the earliest mention of a factor or its aliases in normalized text.
def factor_mention_start(factor: str, text: str) -> int | None:
    """Return the earliest character offset where `factor` (or an alias) is
    mentioned in already-normalized `text`, or None if it is not mentioned.
    """
    aliases = (factor, *FACTOR_ALIASES.get(factor, ()))
    starts = []
    for alias in aliases:
        alias_norm = normalize_text(alias)
        if not alias_norm:
            continue
        match = re.search(rf"(?<![a-z0-9]){re.escape(alias_norm)}(?![a-z0-9])", text)
        if match:
            starts.append(match.start())
    return min(starts) if starts else None


def factor_mention_span(factor: str, text: str) -> tuple[int, int] | None:
    """Return the earliest mention span for a canonical factor or alias."""
    aliases = (factor, *FACTOR_ALIASES.get(factor, ()))
    matches = []
    for alias in aliases:
        alias_norm = normalize_text(alias)
        if not alias_norm:
            continue
        match = re.search(rf"(?<![a-z0-9]){re.escape(alias_norm)}(?![a-z0-9])", text)
        if match:
            matches.append((match.start(), match.end()))
    return min(matches, key=lambda item: item[0]) if matches else None
