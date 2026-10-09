"""Verified-support evidence gate (T1 follow-up, 2026-09-28) -- purely
ADDITIVE input-filtering wrappers around Activation v2 (``score_alpha_v2``)
and Conflict Admissibility (``evaluate_conflict_admissibility``).

Why this module exists (see ``comqutor_alpha.source_provenance``'s own
module docstring for the full two-axis model): a claim's ``evidence_stance``
(its OWN direction toward an Alpha -- supports/opposes/mentions/etc.) and a
linked source's ``content_support_status`` (whether that source's CONTENT
actually backs the claim's assertion, and whether that has been verified by
a real human review) are two independent axes. Before this module, nothing
in the real scoring/admissibility call chain read ``content_support_status``
or the review record at all -- a claim with an unreviewed, invalid, or
unlocatable source scored identically to one with a complete human review.
That is a correct default (an unreviewed candidate must still be
*displayable*), but it means no REAL eligibility gate existed anywhere in
the production chain.

This module adds one: every function here calls the real, UNMODIFIED,
already-frozen-or-not production function it wraps
(``comqutor_alpha.graph_engine.activation_scorer_v2.score_alpha_v2`` and
the frozen ``comqutor_alpha.conflict_engine.conflict_admissibility.
evaluate_conflict_admissibility``) -- it never reimplements or edits either
formula. It only FILTERS which claims are allowed to reach them, using
``comqutor_alpha.source_provenance.compute_verified_support_eligibility``
as the single source of truth for "is this claim's source-content link
VERIFIED." ``conflict_admissibility.py``/``conflict_schema.py`` remain under
this repository's frozen-file guard (see
``tests/test_j3_semantic_benchmark_j2_v0_2.py``'s ``frozen_paths``) -- this
module is why the gate could be added without touching either file.

Nothing here replaces the existing, unfiltered score/admissibility result a
caller already computes -- a caller that wants a "verified-only" view calls
these alongside its existing call, never instead of it. Reuses the existing
thresholds (``ALPHA_SCORE_THRESHOLD``, ``MIN_SUPPORTING_EVIDENCE_PER_SIDE``,
``MIN_TICKER_SPECIFIC_SUPPORT_PER_SIDE`` in ``conflict_admissibility.py``,
and Activation v2's own weights/saturations in ``activation_scorer_v2.py``)
unchanged -- this module defines no new threshold of its own.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.conflict_engine.conflict_admissibility import (
    AdmissibilityResult,
    evaluate_conflict_admissibility,
)
from comqutor_alpha.graph_engine.activation_scorer_v2 import (
    ACTIVATION_V2_WEIGHTS,
    score_alpha_v2,
)
from comqutor_alpha.graph_engine.graph_schema import MVP_ALPHA_IDS
from comqutor_alpha.source_provenance import (
    SOURCE_LINK_VALID,
    compute_verified_support_eligibility,
)

# Explicit, traceable rule-version identifiers (2026-09-28 "official result"
# escalation): a run computed under this gate must be able to name, in its
# own persisted artifact, EXACTLY which rule produced its official
# activation/admissibility result -- never an unlabeled recompute, and
# never backfilled onto a historical run that predates this gate entirely
# (a historical run simply lacks these fields/values, it is never rewritten
# to claim retroactive verification). ``ACTIVATION_V2_VERIFIED_FORMULA_
# VERSION`` is DELIBERATELY distinct from the underlying (unmodified,
# frozen-adjacent) ``ACTIVATION_V2_FORMULA_VERSION`` -- the scoring FORMULA
# is byte-identical; only the input evidence pool differs, but that
# difference must still be independently nameable.
ACTIVATION_V2_VERIFIED_FORMULA_VERSION = "activation.v2.evidence_local_structure.verified_gate.v1"
EVIDENCE_GATE_VERSION = "t1_verified_evidence_gate.v1"

# Explicit, persisted marker of WHICH EXECUTION RULE (required vs.
# opportunistic) governed this run's Activation/Conflict computation --
# distinct from EVIDENCE_GATE_VERSION (the gate FORMULA's own version,
# already present whenever a verified view exists at all, opportunistically
# or not). Written by score_and_assemble_structure_graph onto structure_
# graph.json's top level ONLY when a caller explicitly passed
# require_verified_evidence_gate=True -- so a run's own persisted artifact
# can always answer "was this run created under the mandatory-verification
# policy" without inferring it from behavior (2026-09-29 closing fix: the
# normal new-research production entrypoint now sets this, not just
# re-evaluation).
EVIDENCE_GATE_POLICY_VERSION = "t1_verified_evidence_gate_required_policy.v1"

EVIDENCE_GATE_SOURCES_UNAVAILABLE = "EVIDENCE_GATE_SOURCES_UNAVAILABLE"
EVIDENCE_GATE_STRUCTURED_RECORDS_UNAVAILABLE = "EVIDENCE_GATE_STRUCTURED_RECORDS_UNAVAILABLE"


class EvidenceGateInputError(Exception):
    """Raised when a caller explicitly REQUIRES the verified-support
    eligibility gate (``require_verified_evidence_gate=True`` --
    2026-09-28 closing fix, extended 2026-09-29 to the normal new-research
    production entrypoint) but this run's own ``sources``/
    ``structured_records`` could not be resolved -- never silently
    degrades to the old, unfiltered formula and reports an "official"
    result in that case. Distinct from a genuinely EMPTY sources list
    (``sources == []``): an empty-but-resolved list is valid input -- the
    gate runs normally and honestly reports zero verified evidence, which
    is a correct, non-error conclusion. ``structured_records is None``
    (``structured_agent_outputs.json`` itself missing or corrupted -- this
    artifact is REQUIRED for any run reaching Week 3) always raises.
    ``sources is None`` raises ONLY when ``structured_records`` actually
    contains at least one claim with ``source_link_status ==
    SOURCE_LINK_VALID`` (see ``requires_source_resolution`` below) -- a run
    with NO source-linked claims at all (every non-news chain; also every
    pre-existing offline fixture that predates source-linking entirely)
    never needed ``sources`` to resolve anything in the first place, so its
    absence is immaterial, not a failure: the gate simply never activates
    for that run (the v2/raw pool stays official, exactly as if
    ``require_verified_evidence_gate`` were ``False`` -- a "no source
    chain touched this run" non-event, not silently mistaken for "verified
    with zero evidence"). Whoever sets ``require_verified_evidence_gate=
    True`` is a caller for whom the gate is mandatory: today, both
    ``routes_research.trigger_content_support_reevaluation`` (every
    re-evaluation execution, by construction, always has at least one
    source-linked claim -- the one being reviewed) and
    ``routes_research.run_research_request`` (every normal new research
    execution)."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def requires_source_resolution(structured_records: Iterable[Mapping[str, Any]] | None) -> bool:
    """True iff at least one record in ``structured_records`` carries
    ``source_link_status == SOURCE_LINK_VALID`` -- i.e. this run actually
    has a claim that needs ``sources`` to resolve its review eligibility.
    A run with none (every non-news chain; every pre-source-linking
    fixture) has nothing for ``sources`` to resolve, so its absence is
    never treated as a gate-input failure -- see ``EvidenceGateInputError``.
    """
    for record in structured_records or ():
        if isinstance(record, Mapping) and record.get("source_link_status") == SOURCE_LINK_VALID:
            return True
    return False


__all__ = [
    "ACTIVATION_V2_VERIFIED_FORMULA_VERSION",
    "EVIDENCE_GATE_VERSION",
    "EVIDENCE_GATE_POLICY_VERSION",
    "EVIDENCE_GATE_SOURCES_UNAVAILABLE",
    "EVIDENCE_GATE_STRUCTURED_RECORDS_UNAVAILABLE",
    "EvidenceGateInputError",
    "requires_source_resolution",
    "index_structured_records_by_claim_id",
    "filter_verified_qualifying_claims",
    "score_alpha_v2_verified",
    "score_alpha_activations_v2_verified",
    "evaluate_conflict_admissibility_verified",
]


def index_structured_records_by_claim_id(
    structured_records: Iterable[Mapping[str, Any]] | None,
) -> dict[str, Mapping[str, Any]]:
    """Index this run's own persisted ``structured_agent_outputs.json``
    records by ``claim_id`` -- the only place ``source_link_status``/
    ``linked_source_id``/``content_support_review`` actually live (a
    qualifying-claim dict, as produced by ``_gather_qualifying_evidence``/
    ``_qualify_and_filter_evidence``, never carries them). Last record for a
    given claim_id wins; production never persists two records sharing one
    claim_id."""
    index: dict[str, Mapping[str, Any]] = {}
    for record in structured_records or ():
        if not isinstance(record, Mapping):
            continue
        claim_id = str(record.get("claim_id") or "").strip()
        if claim_id:
            index[claim_id] = record
    return index


def filter_verified_qualifying_claims(
    qualifying_claims: Sequence[Mapping[str, Any]],
    structured_records_by_claim_id: Mapping[str, Mapping[str, Any]],
    sources: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Return only the members of ``qualifying_claims`` whose own
    persisted record is VERIFIED-eligible per
    ``compute_verified_support_eligibility`` -- i.e. a real, resolvable,
    in-scope source link (``source_link_status == VALID``) bound to a
    genuine ``HUMAN_REVIEWED`` review of SUPPORTS/OPPOSES, for THIS exact
    claim, whose content hash has not changed since review.

    A qualifying claim with no matching structured record at all (should
    not happen in production -- every qualifying claim originates from a
    persisted record) is conservatively dropped, never treated as eligible
    by default.

    This never inspects or returns anything about ``evidence_stance`` --
    the claim's own bull/bear direction is a completely separate, untouched
    concern the caller (``_evaluate_side``/``_stance_filtered_qualifying``
    in ``conflict_admissibility.py``, or Activation v2's own relation
    handling) keeps computing exactly as today; a caller must not conflate
    "verified" with "supports."
    """
    verified: list[dict[str, Any]] = []
    for claim in qualifying_claims:
        claim_id = str(claim.get("claim_id") or "").strip()
        record = structured_records_by_claim_id.get(claim_id)
        if record is None:
            continue
        eligibility = compute_verified_support_eligibility(record, sources)
        if eligibility.get("eligible"):
            verified.append(dict(claim))
    return verified


def score_alpha_v2_verified(
    alpha_id: str,
    alpha_matches_payload: Mapping[str, Any],
    taxonomy: Mapping[str, Any],
    *,
    structured_records: Iterable[Mapping[str, Any]] | None,
    sources: list[dict[str, Any]] | None,
    graph_edges: Sequence[Mapping[str, Any]] = (),
    ticker: str | None = None,
    company_names: Sequence[str] = (),
    run_timestamp: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Verified-only counterpart of ``score_alpha_v2``: calls the SAME real,
    unmodified function, on the SAME ``taxonomy``/``graph_edges``/
    ``structured_records`` (needed for its own entities/confidence/
    duplicate-group indexing), but with ``alpha_matches_payload["matches"]``
    pre-filtered to only claim_ids whose structured record is
    verified-eligible. Every weight/saturation/threshold inside
    ``score_alpha_v2`` itself is untouched -- only its input evidence pool
    shrinks.
    """
    structured_records = list(structured_records or ())
    by_claim_id = index_structured_records_by_claim_id(structured_records)
    matches = alpha_matches_payload.get("matches") if isinstance(alpha_matches_payload, Mapping) else None
    verified_matches = []
    for match in matches or ():
        if not isinstance(match, Mapping):
            continue
        claim_id = str(match.get("claim_id") or "").strip()
        record = by_claim_id.get(claim_id)
        if record is None:
            continue
        eligibility = compute_verified_support_eligibility(record, sources)
        if eligibility.get("eligible"):
            verified_matches.append(match)
    verified_payload = dict(alpha_matches_payload)
    verified_payload["matches"] = verified_matches
    return score_alpha_v2(
        alpha_id,
        verified_payload,
        taxonomy,
        graph_edges=graph_edges,
        ticker=ticker,
        company_names=company_names,
        structured_records=structured_records,
        run_timestamp=run_timestamp,
        as_of=as_of,
    )


def score_alpha_activations_v2_verified(
    alpha_matches_payload: Mapping[str, Any],
    *,
    structured_records: Iterable[Mapping[str, Any]] | None,
    sources: list[dict[str, Any]] | None,
    graph_edges: Sequence[Mapping[str, Any]] = (),
    ticker: str | None = None,
    company_names: Sequence[str] = (),
    taxonomy: Mapping[str, Any] | None = None,
    run_timestamp: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Verified-only counterpart of ``activation_scorer_v2.
    score_alpha_activations_v2`` -- scores every MVP-10 alpha via
    ``score_alpha_v2_verified`` (see above) and assembles the SAME payload
    shape (``formula_version``/``weights``/``alphas``/``dominant_alphas``)
    that function already produces, so a caller can attach this as a
    distinctly-versioned activation view (``activation_versions
    ["v2_verified"]``) alongside the existing v1/v2 views.

    The top-level ``formula_version`` here is deliberately
    ``ACTIVATION_V2_VERIFIED_FORMULA_VERSION`` -- distinct from
    ``ACTIVATION_V2_FORMULA_VERSION`` -- so a consumer can always tell
    which rule governs THIS view by its own version string alone, per the
    2026-09-28 "official result must name its own rule version" escalation.
    This never touches ``score_alpha_v2`` itself: each PER-ALPHA entry's own
    internal ``formula_version`` field (set by that unmodified function)
    still correctly reads the underlying v2 formula id, because the
    scoring FORMULA is genuinely unchanged -- only the input evidence pool
    differs, and only this wrapper's own top-level label distinguishes that.
    """
    taxonomy = taxonomy or load_alpha_taxonomy()
    structured_records = list(structured_records or ())
    alphas = [
        score_alpha_v2_verified(
            alpha_id,
            alpha_matches_payload,
            taxonomy,
            structured_records=structured_records,
            sources=sources,
            graph_edges=graph_edges,
            ticker=ticker,
            company_names=company_names,
            run_timestamp=run_timestamp,
            as_of=as_of,
        )
        for alpha_id in sorted(MVP_ALPHA_IDS)
    ]
    dominant = [a for a in alphas if a["status"] in ("dominant", "regime_level")]
    dominant.sort(key=lambda a: (-a["activation_score"], a["alpha_id"]))
    return {
        "formula_version": ACTIVATION_V2_VERIFIED_FORMULA_VERSION,
        "weights": dict(ACTIVATION_V2_WEIGHTS),
        "run_timestamp": run_timestamp,
        "as_of": as_of if as_of is not None else run_timestamp,
        "alphas": alphas,
        "dominant_alphas": [
            {
                "alpha_id": a["alpha_id"],
                "alpha_name": a["alpha_name"],
                "activation_score": a["activation_score"],
                "status": a["status"],
                "direction": a["direction"],
                "evidence_summary": {
                    "evidence_count": a["evidence_count"],
                    "distinct_supporting_agents": a["distinct_supporting_agents"],
                },
            }
            for a in dominant
        ],
    }


def evaluate_conflict_admissibility_verified(
    *,
    bull_alpha_id: str,
    bear_alpha_id: str,
    bull_score: float | None,
    bear_score: float | None,
    bull_qualifying_claims: Sequence[Mapping[str, Any]],
    bear_qualifying_claims: Sequence[Mapping[str, Any]],
    alpha_matches: Sequence[Mapping[str, Any]],
    ticker: str,
    group_into_facts: Any,
    structured_records: Iterable[Mapping[str, Any]] | None,
    sources: list[dict[str, Any]] | None,
) -> AdmissibilityResult:
    """Verified-only counterpart of ``evaluate_conflict_admissibility``:
    calls the SAME real, unmodified, FROZEN function (never edited -- see
    module docstring), with ``bull_qualifying_claims``/
    ``bear_qualifying_claims`` pre-filtered to only verified-eligible
    claims. ``bull_score``/``bear_score`` are passed through as given by the
    caller (unchanged) -- pass ``score_alpha_v2_verified``'s own score here
    if the caller wants a fully verified-only admissibility view; passing
    the existing unfiltered score instead answers "would today's already-
    computed score still admit if only VERIFIED evidence counted."
    """
    structured_records = list(structured_records or ())
    by_claim_id = index_structured_records_by_claim_id(structured_records)
    verified_bull = filter_verified_qualifying_claims(bull_qualifying_claims, by_claim_id, sources)
    verified_bear = filter_verified_qualifying_claims(bear_qualifying_claims, by_claim_id, sources)
    return evaluate_conflict_admissibility(
        bull_alpha_id=bull_alpha_id,
        bear_alpha_id=bear_alpha_id,
        bull_score=bull_score,
        bear_score=bear_score,
        bull_qualifying_claims=verified_bull,
        bear_qualifying_claims=verified_bear,
        alpha_matches=alpha_matches,
        ticker=ticker,
        group_into_facts=group_into_facts,
    )
