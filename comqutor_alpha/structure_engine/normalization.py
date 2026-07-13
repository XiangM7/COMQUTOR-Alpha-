"""Deterministic label normalization with explicit, reviewable synonyms."""

from __future__ import annotations

import re
import unicodedata

_NON_WORD = re.compile(r"[^a-z0-9]+")
_SPACE = re.compile(r"\s+")
_SYNONYMS = {
    "ai capital spending": "ai capex",
    "artificial intelligence capex": "ai capex",
    "ai capex": "ai capex",
    "data center": "datacenter",
    "data centers": "datacenter",
    "datacenters": "datacenter",
    "gpu demands": "gpu demand",
    "graphics processor demand": "gpu demand",
    "sales growth": "revenue growth",
    "top line growth": "revenue growth",
}


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = _NON_WORD.sub(" ", normalized)
    return _SPACE.sub(" ", normalized).strip()


def canonicalize_label(value: str) -> str:
    normalized = normalize_text(value)
    return _SYNONYMS.get(normalized, normalized)


def stable_node_id(value: str) -> str:
    canonical = canonicalize_label(value)
    if not canonical:
        raise ValueError("node label is empty after normalization")
    return canonical.replace(" ", "-")


def phrase_matches(text: str, phrase: str) -> bool:
    normalized_text = f" {normalize_text(text)} "
    normalized_phrase = normalize_text(phrase)
    return bool(normalized_phrase) and f" {normalized_phrase} " in normalized_text
