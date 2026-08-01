"""Canonical COMQUTOR factor/relation vocabulary manifest.

Single deterministic builder over the *existing* production registries --
never a second, hand-maintained taxonomy. Factors come from
``factor_normalizer.FACTOR_ALIASES`` (the same dict the Structure Extractor
and Alpha Mapper already resolve every claim against); relation types come
from ``structure_schema.VALID_EDGE_TYPES`` (the same 3-value set
``graph_builder`` already admits edges against). This module only adds the
*descriptive* metadata (display phrase, definition, directionality) that
those registries do not carry today, plus deterministic versioning so a
prompt/vocabulary snapshot can always be tied back to the exact registry
content that produced it.

Used by ``comqutor_alpha.llm.canonical_prompt_injection`` to build the
COMQUTOR Structure Output Contract appended to existing TradingAgents
prompts, and by ``comqutor_alpha.structure_engine.canonical_relation_block``
to validate the machine-readable relation block the LLM returns.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from comqutor_alpha.structure_engine.factor_normalizer import ALIAS_VERSION, FACTOR_ALIASES
from comqutor_alpha.structure_engine.relation_grammar import (
    GROWTH_FACTORS,
    RELATION_GRAMMAR_VERSION,
    RISK_FACTORS,
)
from comqutor_alpha.structure_engine.structure_schema import VALID_EDGE_TYPES

# Bump whenever RELATION_DEFINITIONS' content changes in a way that could
# alter what an agent is told a relation type means -- mirrors
# ``factor_normalizer.ALIAS_VERSION``'s versioning discipline for the same
# reason (auditability of what vocabulary a given run actually saw).
RELATION_REGISTRY_VERSION = "structure_engine.canonical_relation_registry.v1"

TAXONOMY_VERSION = ALIAS_VERSION

# Descriptive metadata for the 3 production edge types (structure_schema.
# VALID_EDGE_TYPES). The *types themselves* are never redefined here -- only
# the display phrase / definition / directionality every LLM-facing prompt
# and the relation registry report need and that no existing module stores.
RELATION_DEFINITIONS: dict[str, dict[str, Any]] = {
    "causal": {
        "display_phrase": "drives",
        "definition": "The source factor causes, drives, or otherwise produces a change (increase or decrease) in the target factor.",
        "directional": True,
    },
    "supportive": {
        "display_phrase": "supports",
        "definition": "The source factor reinforces, confirms, or lends support to the target factor without asserting direct causation.",
        "directional": True,
    },
    "conflicting": {
        "display_phrase": "conflicts with",
        "definition": "The source (a risk factor) is contrasted against the target (a growth/demand factor) in the same claim.",
        "directional": False,
    },
}

if set(RELATION_DEFINITIONS) != VALID_EDGE_TYPES:
    raise RuntimeError(
        "canonical_vocabulary.RELATION_DEFINITIONS has drifted from "
        "structure_schema.VALID_EDGE_TYPES -- update RELATION_DEFINITIONS."
    )


def _factor_category(factor: str) -> str:
    if factor in RISK_FACTORS:
        return "risk"
    if factor in GROWTH_FACTORS:
        return "growth"
    return "neutral"


def _factor_description(factor: str, category: str) -> str:
    if category == "risk":
        return f"A risk factor: {factor} represents downside/valuation pressure tracked by COMQUTOR."
    if category == "growth":
        return f"A growth/demand factor: {factor} represents upside demand or expansion tracked by COMQUTOR."
    return f"A macro/liquidity factor: {factor} is tracked by COMQUTOR's structure graph."


def compute_taxonomy_sha256() -> str:
    """Deterministic sha256 over ``FACTOR_ALIASES``' real content (sorted
    keys/aliases so key ordering never changes the hash) -- no such hash
    existed anywhere in the codebase before this module."""
    canonical = {factor: sorted(aliases) for factor, aliases in sorted(FACTOR_ALIASES.items())}
    payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_canonical_relation_vocabulary() -> dict[str, Any]:
    """Deterministic vocabulary manifest built fresh from the real
    production registries every call -- never cached/hand-copied. Factor
    ``factor_id`` is the canonical display label itself: this codebase has
    no separate opaque factor-id field (confirmed by direct audit of
    ``factor_normalizer.py``/``structure_extractor.py`` -- display names
    double as the canonical identifier everywhere edges/nodes are built).
    """
    factors = []
    for factor, aliases in sorted(FACTOR_ALIASES.items()):
        category = _factor_category(factor)
        factors.append(
            {
                "factor_id": factor,
                "display_name": factor,
                "aliases": list(aliases),
                "description": _factor_description(factor, category),
                "category": category,
            }
        )

    relations = [
        {
            "relation_type": relation_type,
            "display_phrase": meta["display_phrase"],
            "definition": meta["definition"],
            "directional": meta["directional"],
        }
        for relation_type, meta in sorted(RELATION_DEFINITIONS.items())
    ]

    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "taxonomy_sha256": compute_taxonomy_sha256(),
        "relation_registry_version": RELATION_REGISTRY_VERSION,
        "relation_grammar_version": RELATION_GRAMMAR_VERSION,
        "factor_registry_source": "comqutor_alpha.structure_engine.factor_normalizer.FACTOR_ALIASES",
        "alias_registry_source": "comqutor_alpha.structure_engine.factor_normalizer.FACTOR_ALIASES",
        "relation_registry_source": "comqutor_alpha.structure_engine.structure_schema.VALID_EDGE_TYPES",
        "factors": factors,
        "relations": relations,
    }


__all__ = [
    "RELATION_REGISTRY_VERSION",
    "TAXONOMY_VERSION",
    "RELATION_DEFINITIONS",
    "compute_taxonomy_sha256",
    "build_canonical_relation_vocabulary",
]
