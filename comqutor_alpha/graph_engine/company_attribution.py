"""Company attribution by NAME PRESENCE (``company_attribution.name.v1``; T1 follow-up migration, round 36).

What this decides, and what it does not
---------------------------------------
It decides ONE thing: does the claim's own text contain the target company's name? ``ticker_specific`` in the result means
exactly that -- *the target name is present* -- and nothing more. It does NOT decide who the claim is about. A sentence such
as "nvidia-backed Firmus is set to postpone its IPO" contains "nvidia" and is therefore reported as name-present, although
its subject is another company. That is a documented, known limitation: ``subject_determined`` is always ``False`` and every
positive result carries the limit ``NAME_PRESENCE_NOT_SUBJECT``. Deciding the subject would need a model judgment and is out of
scope for this version.

Fixed matching conditions (the approved name口径)
-------------------------------------------------
1. the ticker symbol, whole-token, case-insensitive (the long-standing ``_is_ticker_specific`` matching);
2. an approved issuer name from ``issuer_aliases.issuer_names_for_ticker`` ("Advanced Micro Devices", "NVIDIA", ...),
   whole-token, case-insensitive -- so the full name and the symbol are equivalent at every entry point;
3. a PRODUCT alias ("Ryzen", "Epyc", "Instinct") only with explicit product context, case-sensitive
   (``issuer_aliases.PRODUCT_ALIAS_CONTEXT``). A bare or lower-case "instinct" never counts.

Never evidence of attribution: the run's ticker, the structured ``entities`` list (upstream appends the run ticker to every
claim), the search query, the source provider, or a linked source's instrument. Source-object attribution
(``TARGET_BY_SOURCE_OBJECT``) is NOT part of this version and is disabled.

A claim that names only OTHER covered companies is ``OTHER_COMPANY_NAMED_ONLY`` and is not target-specific.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from comqutor_alpha.graph_engine.issuer_aliases import (
    CANONICAL_ISSUER_ALIASES,
    issuer_names_for_ticker,
    product_alias_patterns_for_ticker,
)

COMPANY_ATTRIBUTION_POLICY_VERSION = "company_attribution.name.v1"

CATEGORY_SYMBOL = "TARGET_NAME_SYMBOL"
CATEGORY_ISSUER = "TARGET_NAME_ISSUER"
CATEGORY_PRODUCT = "PRODUCT_ALIAS_WITH_CONTEXT"
CATEGORY_OTHER_ONLY = "OTHER_COMPANY_NAMED_ONLY"
CATEGORY_NONE = "NO_TARGET_NAME"
TARGET_NAME_CATEGORIES = frozenset({CATEGORY_SYMBOL, CATEGORY_ISSUER, CATEGORY_PRODUCT})
ALL_CATEGORIES = TARGET_NAME_CATEGORIES | {CATEGORY_OTHER_ONLY, CATEGORY_NONE}

LIMIT_NAME_PRESENCE = "NAME_PRESENCE_NOT_SUBJECT"
LIMIT_OTHER_COVERED_COMPANY_NAMED = "OTHER_COVERED_COMPANY_ALSO_NAMED"


def attribution_text(record: Mapping[str, Any]) -> str:
    """The text the attribution is read from: the claim, else its evidence -- the same choice the legacy predicate makes."""
    return str(record.get("claim") or record.get("evidence") or "")


def _token_match(term: str, text: str) -> bool:
    # The shared whole-token matcher (normalisation + (?<![a-z0-9])term(?![a-z0-9])), imported lazily so this module and the
    # scorer, which reads the result, never import each other at module load.
    from comqutor_alpha.graph_engine.activation_scorer_v2 import (  # noqa: PLC0415
        _token_boundary_match,
    )

    return _token_boundary_match(term, text)


def _other_covered_companies(ticker: str, text: str) -> list[str]:
    named = []
    for other in sorted(CANONICAL_ISSUER_ALIASES):
        if other == ticker:
            continue
        if _token_match(other, text) or any(_token_match(name, text) for name in issuer_names_for_ticker(other)):
            named.append(other)
    return named


def resolve_name_attribution(record: Mapping[str, Any], ticker: str | None) -> dict[str, Any]:
    ticker_key = str(ticker or "").strip().upper()
    text = attribution_text(record)
    basis: list[dict[str, str]] = []
    if ticker_key and _token_match(ticker_key, text):
        basis.append({"kind": "symbol", "term": ticker_key})
    for name in issuer_names_for_ticker(ticker_key):
        if _token_match(name, text):
            basis.append({"kind": "issuer_name", "term": name})
    for alias, pattern in product_alias_patterns_for_ticker(ticker_key).items():
        if pattern.search(text):
            basis.append({"kind": "product_alias", "term": alias})

    kinds = {item["kind"] for item in basis}
    others = _other_covered_companies(ticker_key, text) if text else []
    if "symbol" in kinds:
        category = CATEGORY_SYMBOL
    elif "issuer_name" in kinds:
        category = CATEGORY_ISSUER
    elif "product_alias" in kinds:
        category = CATEGORY_PRODUCT
    elif others:
        category = CATEGORY_OTHER_ONLY
    else:
        category = CATEGORY_NONE

    specific = category in TARGET_NAME_CATEGORIES
    limits: list[str] = []
    if specific:
        limits.append(LIMIT_NAME_PRESENCE)
        if others:
            limits.append(LIMIT_OTHER_COVERED_COMPANY_NAMED)
    return {
        "policy": COMPANY_ATTRIBUTION_POLICY_VERSION,
        "category": category,
        "ticker_specific": specific,  # == "the target's name is present"; consumers read this field
        "subject_determined": False,
        "basis": basis,
        "other_issuers_named": others,
        "limits": limits,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


__all__ = [
    "ALL_CATEGORIES",
    "CATEGORY_ISSUER",
    "CATEGORY_NONE",
    "CATEGORY_OTHER_ONLY",
    "CATEGORY_PRODUCT",
    "CATEGORY_SYMBOL",
    "COMPANY_ATTRIBUTION_POLICY_VERSION",
    "LIMIT_NAME_PRESENCE",
    "LIMIT_OTHER_COVERED_COMPANY_NAMED",
    "TARGET_NAME_CATEGORIES",
    "attribution_text",
    "resolve_name_attribution",
]
