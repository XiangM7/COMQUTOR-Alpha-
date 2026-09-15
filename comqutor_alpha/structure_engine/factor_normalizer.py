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

# Bump whenever FACTOR_ALIASES (or its matching semantics) changes in a way
# that could alter which factor an alias phrase resolves to -- consumed by
# the architecture-replay lineage metadata (comqutor_alpha/replay/pipeline.py)
# so a replay can tell whether alias resolution differs from a prior run.
ALIAS_VERSION = "structure_engine.factor_aliases.v1"

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
        "data center buildout",
        "datacenter buildout",
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
        # Memory/storage demand-side vocabulary of the same commodity semis
        # cycle (generic industry terms, not ticker-specific). Deliberately
        # narrow: pricing-side phrasings are not aliased to avoid flooding
        # the alpha mapper's factor scores.
        "memory demand",
        "storage demand",
    ),
    "Rate Cut Cycle": (
        "rate cut",
        "falling rates",
        "lower rates",
        "fed cut",
        "easing cycle",
        "discount rates fall",
        "discount rates are easing",
        "treasury yields fall",
        "treasury yields are falling",
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

# v0.1.3 MSFT A304 Negation-Aware Structure Extraction: bounded, generic
# regex mention patterns for factor concepts whose adverse-direction
# phrasing cannot be captured by a literal-substring alias, because a
# variable, unbounded noun (a product/segment name, e.g. "Azure", "cloud",
# "subscription") sits between the qualifier and the anchor word (see
# docs/audit_artifacts/v0_1_3_msft_a304_negation_extraction_fix.md's
# canonical case: "Any slowdown in Azure growth could trigger multiple
# compression" -- "slowdown in <company-specific segment> growth" can never
# be enumerated as a finite literal-alias list). Deliberately narrow and
# corpus-validated (89-claim keyword blast-radius scan across all six
# authoritative runs found exactly 2 affected claims, 1 producing a new
# edge) -- NOT a general NLP parser, and NEVER ticker/ or ID-specific.
# Checked ONLY in addition to (never instead of) FACTOR_ALIASES above, by
# both extract_known_factors_from_text() (whole-claim factor detection,
# here) and relation_grammar._factor_spans() (clause-local span location,
# imported from here) -- one shared source of truth, per this module's own
# stated purpose of keeping factor_normalizer.py and structure_extractor.py
# aligned without a circular import.
#
# Deliberately excludes bare "slow"/"weak" (too broad, see the audit) and
# "growth is slowing" (would fire on its own negation, "growth is NOT
# slowing", with no compensating benefit -- no required positive test needs
# it). Only forms that (a) correspond to the existing "Revenue Growth"
# canonical factor and (b) are either the literal audit case or one of its
# closest, evidence-backed variants are included.
FACTOR_ALIAS_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "Revenue Growth": (
        re.compile(r"\bslowdown in\b(?:\s+\w+){0,3}\s+growth\b"),
        re.compile(r"\bgrowth slowdown\b"),
        re.compile(r"\bdecelerating\b(?:\s+\w+){0,3}\s+growth\b"),
        re.compile(r"\bgrowth deceleration\b"),
        re.compile(r"\bgrowth deterioration\b"),
        re.compile(r"\bslower\b(?:\s+\w+){0,3}\s+growth\b"),
        re.compile(r"\bweaker\b(?:\s+\w+){0,3}\s+growth\b"),
    ),
}


def _factor_alias_pattern_spans(factor: str, normalized_text: str) -> list[tuple[int, int]]:
    """Every match span for `factor`'s regex-based alias patterns (if any)
    against already-normalized text. Additive to, never a replacement for,
    the literal FACTOR_ALIASES lookups every caller already performs."""
    return [
        (match.start(), match.end())
        for pattern in FACTOR_ALIAS_PATTERNS.get(factor, ())
        for match in pattern.finditer(normalized_text)
    ]


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
        if any(term_in_text(alias, normalized) for alias in aliases) or _factor_alias_pattern_spans(
            factor, normalized
        ):
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
    starts.extend(start for start, _end in _factor_alias_pattern_spans(factor, text))
    return min(starts) if starts else None


def factor_mention_span(factor: str, text: str) -> tuple[int, int] | None:
    """Return the earliest mention span for a canonical factor or alias."""
    aliases = (factor, *FACTOR_ALIASES.get(factor, ()))
    matches = list(_factor_alias_pattern_spans(factor, text))
    for alias in aliases:
        alias_norm = normalize_text(alias)
        if not alias_norm:
            continue
        match = re.search(rf"(?<![a-z0-9]){re.escape(alias_norm)}(?![a-z0-9])", text)
        if match:
            matches.append((match.start(), match.end()))
    return min(matches, key=lambda item: item[0]) if matches else None
