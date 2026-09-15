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


__all__ = [
    "CANONICAL_ISSUER_ALIASES",
    "ETF_ENTITY_HANDLING_DEFERRED",
    "company_names_for_ticker",
]
