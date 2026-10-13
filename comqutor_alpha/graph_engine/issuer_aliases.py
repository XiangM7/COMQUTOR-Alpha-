"""Canonical ticker -> issuer name/alias registry (P0/P1 Evidence
Correctness Fix, Phase 1).

P1 (company_names propagation): a static, deterministic, auditable
ticker -> issuer-name/product-alias table. Its sole intended production
consumer is ``graph_engine/pipeline.py``, which passes
``company_names_for_ticker(ticker)`` into
``activation_scorer_v2.score_alpha_activations_v2`` so a claim naming the
issuer by its real name ("Microsoft") rather than its ticker symbol
("MSFT") can be recognized as ticker-specific evidence by the existing,
unmodified ``_is_ticker_specific``/``_token_boundary_match`` matching
semantics in ``activation_scorer_v2.py``.

Deliberately NOT a general-purpose entity/company database: it covers only
the tickers this system currently runs against, and is extended by adding
one entry when a new ticker is onboarded -- never by loosening matching
semantics or growing into an open-ended lookup service.

QQQ is intentionally absent. An ETF has no single "issuer legal name" in
the sense this registry models (its real economic exposure runs through
named constituents, an entirely different, deliberately out-of-scope
problem -- see ``ETF_ENTITY_HANDLING_DEFERRED`` below and
``docs/audit_artifacts/v0_1_3_a102_cross_company_integrity_audit.md``'s
ETF Special Case section). Treating a constituent mention as QQQ-direct
evidence is explicitly NOT done here.

P0 (evidence ownership gate): this module also exposes the full alias
table keyed by ticker so ``activation_scorer_v2.py`` can determine whether
a claim's only named issuer is a DIFFERENT ticker this system itself
covers -- the narrow, deterministic signal used by
``_foreign_issuer_only_reason`` (see that function's docstring for the
full three-condition contract). This registry is read-only data; it
contains no matching logic of its own.
"""

from __future__ import annotations

import re

CANONICAL_ISSUER_ALIASES: dict[str, tuple[str, ...]] = {
    "NVDA": ("NVIDIA", "NVIDIA Corporation"),
    "MSFT": ("Microsoft", "Microsoft Corporation"),
    "AMD": (
        "Advanced Micro Devices",
        "Advanced Micro Devices, Inc.",
        "Ryzen",
        "Instinct",
        "Epyc",
    ),
    "TSM": (
        "TSMC",
        "Taiwan Semiconductor Manufacturing",
        "Taiwan Semiconductor Manufacturing Company",
        "Taiwan Semiconductor",
    ),
    "SNDK": ("SanDisk", "SanDisk Corporation"),
    # QQQ: no entry -- see module docstring. Absence is a safe, explicit
    # no-op (company_names_for_ticker returns () ), never an error.
}

# Documents, for audit purposes, that ETF constituent-ownership modeling is
# a distinct, deliberately out-of-scope problem this registry does not
# attempt to solve (Section 7/16 of the P0/P1 correctness-fix task).
ETF_ENTITY_HANDLING_DEFERRED = True


def company_names_for_ticker(ticker: str | None) -> tuple[str, ...]:
    """Canonical alias lookup -- the intended production entry point for
    P1. Returns an empty tuple for any ticker not in the registry
    (including QQQ); absence is a safe, explicit no-op."""
    return CANONICAL_ISSUER_ALIASES.get(str(ticker or "").strip().upper(), ())


# ---------------------------------------------------------------------------
# T1 follow-up migration (round 36): the same registry split into the two kinds of name the consumption contract
# treats differently. ``CANONICAL_ISSUER_ALIASES`` and ``company_names_for_ticker`` above are UNCHANGED, so every
# existing caller (legacy Activation scoring, the foreign-issuer veto) behaves exactly as before.
#
# * An ISSUER NAME ("Advanced Micro Devices", "NVIDIA") names the company itself; its presence in a claim is
#   name-level target evidence on its own.
# * A PRODUCT ALIAS ("Ryzen", "Epyc", "Instinct") names something the company sells. It counts only with explicit product
#   context, because some of them are ordinary English words ("Your instinct is going to be hold") and the registry
#   gives no approval for treating a bare word as the company. Matching is CASE-SENSITIVE.
# ---------------------------------------------------------------------------
PRODUCT_ALIAS_NAMES: dict[str, tuple[str, ...]] = {"AMD": ("Ryzen", "Instinct", "Epyc")}

# Fixed matching conditions (company_attribution.name.v1). Each pattern is applied to the claim text AS WRITTEN (not lower-cased).
#   Ryzen    -- the capitalised brand token (not an English word).
#   Epyc     -- "EPYC" or "Epyc" (not an English word).
#   Instinct -- the capitalised word AND an explicit product context directly after it: a model code ("Instinct MI300X",
#               "Instinct MI 325X") or a product noun ("Instinct GPUs", "Instinct data-center accelerators",
#               "Instinct series"). A capitalised "Instinct" without such a context, and any lower-case "instinct", never match.
PRODUCT_ALIAS_CONTEXT: dict[str, dict[str, re.Pattern[str]]] = {
    "AMD": {
        "Ryzen": re.compile(r"\bRyzen\b"),
        "Epyc": re.compile(r"\b(?:EPYC|Epyc)\b"),
        "Instinct": re.compile(
            r"\bInstinct\s+MI\s?-?\d{2,4}[A-Za-z]{0,2}\b"
            r"|\bInstinct\s+(?:data[- ]?center\s+|AI\s+)?(?:GPUs?|accelerators?|series|platform|family)\b"
        ),
    }
}


def issuer_names_for_ticker(ticker: str | None) -> tuple[str, ...]:
    """The registry's company names for ``ticker`` WITHOUT its product aliases (derived, so the two views cannot drift)."""
    key = str(ticker or "").strip().upper()
    products = set(PRODUCT_ALIAS_NAMES.get(key, ()))
    return tuple(name for name in CANONICAL_ISSUER_ALIASES.get(key, ()) if name not in products)


def product_alias_patterns_for_ticker(ticker: str | None) -> dict[str, re.Pattern[str]]:
    return dict(PRODUCT_ALIAS_CONTEXT.get(str(ticker or "").strip().upper(), {}))


__all__ = [
    "CANONICAL_ISSUER_ALIASES",
    "ETF_ENTITY_HANDLING_DEFERRED",
    "PRODUCT_ALIAS_CONTEXT",
    "PRODUCT_ALIAS_NAMES",
    "company_names_for_ticker",
    "issuer_names_for_ticker",
    "product_alias_patterns_for_ticker",
]
