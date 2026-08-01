"""Regime Evidence Integrity Shadow Layer.

Product Findings Closure and Regime Evidence Integrity Sprint, Track B.

Pure functions only: no I/O, no database, no network, no Provider/LLM calls,
no API response generation. A read-only, internal, additive shadow analysis
layered on top of Activation v2's already-admitted evidence
(``graph_engine/activation_scorer_v2.py``, entirely untouched by this
module) -- never recomputes, overrides, or otherwise changes John's
production Activation score, status, or regime gate.

Why this exists: the same real fact can legitimately support multiple
Alphas (an AI-infrastructure-demand claim can be genuine evidence for both
A101 and A103), but multiple paraphrases of that ONE fact across different
agents must not be counted as multiple INDEPENDENT pieces of evidence. This
module:

1. builds deterministic Evidence Groups across an alpha's admitted matches
   (:func:`build_evidence_groups`);
2. attributes each group to a primary Alpha and zero or more secondary
   Alphas (:func:`build_evidence_groups` again -- attribution is computed
   per group, not as a separate pass);
3. computes per-Alpha overlap metrics (:func:`compute_alpha_evidence_metrics`);
4. evaluates a shadow regime verdict using the SAME frozen threshold
   constants John's production gate already uses
   (``activation_scorer_v2.REGIME_GATE_MIN_*``), with only the
   evidence-count input substituted for the group-deduplicated count
   (:func:`evaluate_shadow_regime_verdict`);
5. assembles the full additive sidecar payload for one run
   (:func:`build_alpha_evidence_integrity_payload`).

Complexity: candidates are bucketed by a blocking key (ticker, factor
signature, assertion status, numeric/date signature) before any pairwise
comparison, so near-match comparison is bounded within (typically small)
buckets -- never an unbounded O(n^2) scan of the full candidate pool.

Grouping is a pure function of its inputs and is order-independent:
processing candidates in a different order produces the same groups (a
union-find keyed by claim_id, merged via priority-ordered passes, each pass
itself iterating in a stable, sorted order).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from comqutor_alpha.graph_engine.activation_scorer_v2 import (
    REGIME_GATE_MIN_DISTINCT_AGENTS,
    REGIME_GATE_MIN_LOCAL_EDGES,
    REGIME_GATE_MIN_LOCAL_STRUCTURE_SUPPORT,
    REGIME_GATE_MIN_SCORE,
    REGIME_GATE_MIN_TICKER_SPECIFIC,
    REGIME_GATE_MIN_UNIQUE_EVIDENCE,
)
from comqutor_alpha.graph_engine.evidence_fact_index import (
    ALPHA_ACTIVATION_EVIDENCE_V1,
    EvidenceFactCandidate,
    date_signature as _date_signature,
    event_signature as _event_signature,
    evidence_fact_group_id,
    factor_signature as _factor_signature,
    group_evidence_candidates,
    numeric_signature as _numeric_signature,
    relation_triple_index as _relation_triple_index,
    select_supporting_alpha_claims,
    token_set as _token_set,
)

EVIDENCE_INTEGRITY_SCHEMA_VERSION = "week_regime_evidence_integrity.v1"

# ---------------------------------------------------------------------------
# Shadow regime verdict statuses.
# ---------------------------------------------------------------------------

STATUS_CONSISTENT = "CONSISTENT"
STATUS_OVERLAP_RISK = "OVERLAP_RISK"
STATUS_INSUFFICIENT_PRIMARY_EVIDENCE = "INSUFFICIENT_PRIMARY_EVIDENCE"
STATUS_UNVERIFIED_EXPOSURE = "UNVERIFIED_EXPOSURE"
STATUS_NOT_REGIME_CANDIDATE = "NOT_REGIME_CANDIDATE"
VALID_INTEGRITY_STATUSES = frozenset(
    {
        STATUS_CONSISTENT,
        STATUS_OVERLAP_RISK,
        STATUS_INSUFFICIENT_PRIMARY_EVIDENCE,
        STATUS_UNVERIFIED_EXPOSURE,
        STATUS_NOT_REGIME_CANDIDATE,
    }
)

_REGIME_LEVEL_STATUS = "regime_level"

# ---------------------------------------------------------------------------
# Signature helpers and grouping algorithm now live in the shared
# ``evidence_fact_index`` module (Structure Integrity Repair Sprint, Track
# 2) -- imported above, never redefined here, so this shadow layer and
# production Activation scoring can never again silently diverge on "what
# counts as one independent fact."
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Candidate assembly.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Candidate:
    claim_id: str
    agent: str
    source_agent_output_id: str
    claim_text: str
    matched_alpha: str
    match_score: float
    factors: tuple[str, ...]
    assertion_status: str
    semantic_polarity: str
    duplicate_group_id: str | None
    relation_triple: tuple[str, str, str, str] | None
    factor_signature: str
    numeric_signature: str
    date_signature: str
    event_signature: str
    token_set: frozenset[str]
    # claim+evidence combined text used for signature derivation (matches
    # the shared Evidence Fact Index's own single signature-computation
    # pass) -- kept as its own field since ``claim_text`` above is used
    # for display/output, not only for grouping.
    signature_text: str


def _duplicate_group_index(
    structured_records: Iterable[Mapping[str, Any]] | None,
) -> dict[str, str]:
    index: dict[str, str] = {}
    for record in structured_records or ():
        if not isinstance(record, Mapping):
            continue
        claim_id = str(record.get("claim_id") or "")
        group_id = record.get("duplicate_group_id")
        if claim_id and isinstance(group_id, str) and group_id.strip():
            index[claim_id] = group_id.strip()
    return index


def _build_candidates(
    alpha_matches_payload: Mapping[str, Any],
    *,
    graph_edges: Sequence[Mapping[str, Any]] | None,
    structured_records: Iterable[Mapping[str, Any]] | None,
) -> list[_Candidate]:
    """Build one candidate per (alpha, eligible claim) pair.

    Eligibility Evidence Integrity Completion Sprint, Track A: delegates
    entirely to the shared canonical selector
    (``evidence_fact_index.select_supporting_alpha_claims``), called once
    per distinct matched alpha in this run's matches -- never a separately
    re-derived filter. This is what makes production Activation and this
    shadow layer agree on which raw claims are even eligible in the first
    place, not merely on how eligible claims are grouped.
    """
    matches = alpha_matches_payload.get("matches") if isinstance(alpha_matches_payload, Mapping) else None
    if not isinstance(matches, list):
        return []

    duplicate_group_ids = _duplicate_group_index(structured_records)
    relation_triples = _relation_triple_index(graph_edges)

    alpha_ids = sorted(
        {
            str(record.get("matched_alpha") or "").strip()
            for record in matches
            if isinstance(record, Mapping)
            and record.get("match_status") == "matched"
            and str(record.get("matched_alpha") or "").strip()
        }
    )

    candidates: list[_Candidate] = []
    seen_claim_ids: set[str] = set()
    for matched_alpha in alpha_ids:
        eligible_records, _excluded, _warnings = select_supporting_alpha_claims(
            matches, matched_alpha, policy_version=ALPHA_ACTIVATION_EVIDENCE_V1
        )
        for record in eligible_records:
            claim_id = str(record.get("claim_id") or "").strip()
            if not claim_id or claim_id in seen_claim_ids:
                continue
            seen_claim_ids.add(claim_id)

            claim_text = str(record.get("claim") or record.get("evidence") or "")
            factors = tuple(str(f) for f in (record.get("factors") or []) if str(f or "").strip())
            assertion_status = str(record.get("assertion_status") or "unknown").strip().lower()
            semantic_polarity = str(record.get("semantic_polarity") or "unknown").strip().lower()
            combined_text = f"{claim_text} {record.get('evidence') or ''}"

            candidates.append(
                _Candidate(
                claim_id=claim_id,
                agent=str(record.get("agent") or "").strip(),
                source_agent_output_id=str(record.get("source_agent_output_id") or "").strip(),
                claim_text=claim_text,
                matched_alpha=matched_alpha,
                match_score=float(record.get("score") or 0.0),
                factors=factors,
                assertion_status=assertion_status,
                semantic_polarity=semantic_polarity,
                duplicate_group_id=duplicate_group_ids.get(claim_id),
                relation_triple=relation_triples.get(claim_id),
                factor_signature=_factor_signature(factors),
                numeric_signature=_numeric_signature(combined_text),
                date_signature=_date_signature(combined_text),
                event_signature=_event_signature(combined_text),
                token_set=_token_set(claim_text),
                signature_text=combined_text,
            )
        )
    return sorted(candidates, key=lambda c: c.claim_id)


# ---------------------------------------------------------------------------
# Deterministic grouping -- delegates entirely to the shared, canonical
# Evidence Fact Index (``evidence_fact_index.group_evidence_candidates``).
# This module contributes no grouping logic of its own; it only adapts its
# own ``_Candidate`` shape to/from the shared ``EvidenceFactCandidate``
# shape, so this shadow layer and production Activation scoring can never
# again silently apply two different grouping algorithms to the same claims.
# ---------------------------------------------------------------------------


def _group_candidates(candidates: Sequence[_Candidate], ticker: str) -> list[list[_Candidate]]:
    if not candidates:
        return []
    by_claim_id = {c.claim_id: c for c in candidates}
    shared_candidates = [
        EvidenceFactCandidate(
            claim_id=c.claim_id,
            claim_text=c.signature_text,
            factors=c.factors,
            assertion_status=c.assertion_status,
            semantic_polarity=c.semantic_polarity,
            duplicate_group_id=c.duplicate_group_id,
            relation_triple=c.relation_triple,
        )
        for c in candidates
    ]
    grouped = group_evidence_candidates(shared_candidates, ticker)
    return [
        [by_claim_id[member.claim_id] for member in members] for members in grouped
    ]


# ---------------------------------------------------------------------------
# Evidence group assembly + primary/secondary attribution.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceGroup:
    evidence_group_id: str
    run_id: str
    ticker: str
    claim_ids: tuple[str, ...]
    agents: tuple[str, ...]
    source_refs: tuple[str, ...]
    factor_signature: str
    relation_signature: str | None
    numeric_signature: str
    assertion_status: str
    semantic_polarity: str
    supported_alpha_ids: tuple[str, ...]
    primary_alpha_id: str | None
    secondary_alpha_ids: tuple[str, ...]
    group_confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)




def _attribute_primary_secondary(members: Sequence[_Candidate]) -> tuple[str | None, tuple[str, ...]]:
    """Primary Alpha selection, in the spec's stated priority order:

    1. already Mapper-admitted -- trivially true for every member here
       (only ``match_status == "matched"`` candidates ever reach this
       function);
    2. higher existing match score;
    3. more alpha-specific matched factors (also stands in for priority 4,
       "relation endpoints more directly tied to alpha factors": a claim
       matched on more of an alpha's own factors is, by construction, more
       directly tied to that alpha's factor set -- no ticker-specific or
       alpha-specific keyword rule is added);
    4. stable alpha_id tie-break.

    Never introduces a ticker-specific or alpha-specific rule -- every
    input here already came from the existing, frozen Mapper admission.
    """
    by_alpha: dict[str, list[_Candidate]] = {}
    for member in members:
        by_alpha.setdefault(member.matched_alpha, []).append(member)
    if not by_alpha:
        return None, ()

    def _strength(alpha_id: str) -> tuple[float, int]:
        members_for_alpha = by_alpha[alpha_id]
        best_score = max(m.match_score for m in members_for_alpha)
        most_factors = max(len(m.factors) for m in members_for_alpha)
        return (best_score, most_factors)

    ordered_alphas = sorted(
        by_alpha, key=lambda alpha_id: (-_strength(alpha_id)[0], -_strength(alpha_id)[1], alpha_id)
    )
    return ordered_alphas[0], tuple(ordered_alphas[1:])


def build_evidence_groups(
    alpha_matches_payload: Mapping[str, Any],
    *,
    run_id: str,
    ticker: str,
    graph_edges: Sequence[Mapping[str, Any]] = (),
    structured_records: Iterable[Mapping[str, Any]] | None = None,
) -> list[EvidenceGroup]:
    """Build deterministic, cross-Alpha Evidence Groups from one run's
    already quality-filtered, Mapper-admitted claims.

    Every group is attributed a primary Alpha and zero or more secondary
    Alphas; no admitted Alpha association is ever dropped -- a group
    supporting multiple Alphas keeps every one of them, split only into
    primary/secondary metadata. Deterministic and input-order independent.
    """
    candidates = _build_candidates(
        alpha_matches_payload, graph_edges=graph_edges, structured_records=structured_records
    )
    grouped = _group_candidates(candidates, ticker)

    results: list[EvidenceGroup] = []
    for members in grouped:
        claim_ids = tuple(sorted({m.claim_id for m in members}))
        agents = tuple(sorted({m.agent for m in members if m.agent}))
        source_refs = tuple(sorted({m.source_agent_output_id for m in members if m.source_agent_output_id}))
        # A group can legitimately mix members whose individual assertion
        # status/polarity/numeric signature differ only when they were
        # merged via priority 1/2 (duplicate_group_id or an identical
        # relation triple, both of which are authoritative regardless of
        # surface text); report the majority/first-sorted value rather than
        # requiring uniformity that priority-1/2 merges do not guarantee.
        assertion_statuses = sorted({m.assertion_status for m in members})
        semantic_polarities = sorted({m.semantic_polarity for m in members})
        factor_signatures = sorted({m.factor_signature for m in members if m.factor_signature})
        numeric_signatures = sorted({m.numeric_signature for m in members if m.numeric_signature})
        relation_triples = sorted({m.relation_triple for m in members if m.relation_triple})

        primary_alpha_id, secondary_alpha_ids = _attribute_primary_secondary(members)
        supported_alpha_ids = tuple(
            sorted({m.matched_alpha for m in members if m.matched_alpha})
        )
        group_confidence = round(max((m.match_score for m in members), default=0.0), 4)

        results.append(
            EvidenceGroup(
                evidence_group_id=evidence_fact_group_id(run_id, ticker, claim_ids),
                run_id=run_id,
                ticker=ticker,
                claim_ids=claim_ids,
                agents=agents,
                source_refs=source_refs,
                factor_signature=factor_signatures[0] if len(factor_signatures) == 1 else "|".join(factor_signatures),
                relation_signature=(
                    ">".join(relation_triples[0]) if len(relation_triples) == 1 else None
                ),
                numeric_signature=numeric_signatures[0] if len(numeric_signatures) == 1 else "|".join(numeric_signatures),
                assertion_status=assertion_statuses[0] if len(assertion_statuses) == 1 else "mixed",
                semantic_polarity=semantic_polarities[0] if len(semantic_polarities) == 1 else "mixed",
                supported_alpha_ids=supported_alpha_ids,
                primary_alpha_id=primary_alpha_id,
                secondary_alpha_ids=secondary_alpha_ids,
                group_confidence=group_confidence,
            )
        )

    return sorted(results, key=lambda g: g.evidence_group_id)


# ---------------------------------------------------------------------------
# Per-Alpha evidence metrics.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AlphaEvidenceMetrics:
    alpha_id: str
    raw_evidence_claim_count: int
    deduplicated_claim_count: int
    independent_evidence_group_count: int
    primary_evidence_group_count: int
    secondary_evidence_group_count: int
    distinct_agent_count: int
    distinct_source_ref_count: int
    structured_relation_group_count: int
    overlap_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_alpha_evidence_metrics(
    alpha_id: str,
    groups: Sequence[EvidenceGroup],
    candidates_for_alpha: Sequence[_Candidate],
) -> AlphaEvidenceMetrics:
    raw_evidence_claim_count = len(candidates_for_alpha)

    # "Obvious duplicate" tier only (exact duplicate_group_id or byte-
    # identical claim text) -- deliberately coarser than the full grouping
    # below, so raw >= deduplicated >= independent are three genuinely
    # different, all-preserved numbers (spec: "不得用一个覆盖另一个").
    exact_dup_keys = {
        c.duplicate_group_id or f"text:{c.claim_text.strip().lower()}" for c in candidates_for_alpha
    }
    deduplicated_claim_count = len(exact_dup_keys)

    supporting_groups = [g for g in groups if alpha_id in g.supported_alpha_ids]
    primary_groups = [g for g in supporting_groups if g.primary_alpha_id == alpha_id]
    secondary_groups = [g for g in supporting_groups if alpha_id in g.secondary_alpha_ids]
    structured_relation_groups = [g for g in supporting_groups if g.relation_signature]

    independent_evidence_group_count = len(supporting_groups)
    distinct_agent_count = len({c.agent for c in candidates_for_alpha if c.agent})
    distinct_source_ref_count = len(
        {c.source_agent_output_id for c in candidates_for_alpha if c.source_agent_output_id}
    )
    overlap_ratio = round(
        1.0 - independent_evidence_group_count / max(raw_evidence_claim_count, 1), 4
    )

    return AlphaEvidenceMetrics(
        alpha_id=alpha_id,
        raw_evidence_claim_count=raw_evidence_claim_count,
        deduplicated_claim_count=deduplicated_claim_count,
        independent_evidence_group_count=independent_evidence_group_count,
        primary_evidence_group_count=len(primary_groups),
        secondary_evidence_group_count=len(secondary_groups),
        distinct_agent_count=distinct_agent_count,
        distinct_source_ref_count=distinct_source_ref_count,
        structured_relation_group_count=len(structured_relation_groups),
        overlap_ratio=overlap_ratio,
    )


# ---------------------------------------------------------------------------
# Shadow regime verdict.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ShadowRegimeVerdict:
    alpha_id: str
    production_status: str
    production_regime_eligible: bool
    shadow_regime_eligible: bool | None
    shadow_regime_failures: tuple[str, ...]
    regime_evidence_integrity_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _evaluate_shadow_gate(
    *,
    activation_score: float,
    independent_evidence_group_count: int,
    distinct_agents: int,
    ticker_specific_count: int,
    local_edge_count: int,
    local_structure_raw: float,
    integrity_warnings: Sequence[str],
) -> tuple[bool, list[str]]:
    """Re-evaluates John's own seven frozen regime-qualification thresholds
    (imported, not redefined) with exactly one input substituted:
    ``independent_evidence_group_count`` in place of production's own
    (already per-alpha semantically deduplicated) ``unique_evidence_count``.
    Every other input is production's own already-computed value -- this
    function does not, and must not, alter John's production gate itself
    (``activation_scorer_v2._evaluate_regime_gate``), which stays
    byte-for-byte unchanged and is never called from here."""
    failures: list[str] = []
    if activation_score < REGIME_GATE_MIN_SCORE:
        failures.append("SCORE_BELOW_REGIME_THRESHOLD")
    if independent_evidence_group_count < REGIME_GATE_MIN_UNIQUE_EVIDENCE:
        failures.append("INSUFFICIENT_INDEPENDENT_EVIDENCE_FOR_REGIME")
    if distinct_agents < REGIME_GATE_MIN_DISTINCT_AGENTS:
        failures.append("INSUFFICIENT_SUPPORTING_AGENTS_FOR_REGIME")
    if ticker_specific_count < REGIME_GATE_MIN_TICKER_SPECIFIC:
        failures.append("INSUFFICIENT_TICKER_SPECIFIC_EVIDENCE_FOR_REGIME")
    if local_edge_count < REGIME_GATE_MIN_LOCAL_EDGES:
        failures.append("NO_LOCAL_STRUCTURE_FOR_REGIME")
    if local_structure_raw < REGIME_GATE_MIN_LOCAL_STRUCTURE_SUPPORT:
        failures.append("INSUFFICIENT_LOCAL_STRUCTURE_STRENGTH_FOR_REGIME")
    if integrity_warnings:
        failures.append("EVIDENCE_INTEGRITY_WARNING")
    return (not failures), failures


def evaluate_shadow_regime_verdict(
    *,
    alpha_id: str,
    production_alpha_result: Mapping[str, Any],
    independent_evidence_group_count: int,
    primary_evidence_group_count: int,
    exposure_value: float | None,
) -> ShadowRegimeVerdict:
    """Compute the shadow regime verdict for one alpha.

    Priority order (evaluated in this exact sequence):

    1. production status != "regime_level" -> NOT_REGIME_CANDIDATE. Shadow
       analysis is only meaningful once production itself already believes
       an alpha is regime-level -- evaluating exposure/overlap for an
       alpha nowhere near regime level would be diagnostic noise.
    2. exposure_value is None -> UNVERIFIED_EXPOSURE (never assumes 0, 1,
       or fabricates a seed).
    3. exposure is available: re-evaluate the seven gates with
       independent_evidence_group_count substituted for unique_evidence_count.
       A failure (necessarily the evidence-count gate, since every other
       input is pinned to production's own already-passing value) ->
       OVERLAP_RISK.
    4. shadow gate passes but primary_evidence_group_count itself falls
       short of the same evidence threshold (the alpha only reaches the
       bar by counting groups where it is a *secondary* attribution) ->
       INSUFFICIENT_PRIMARY_EVIDENCE. Diagnostic only -- does not flip
       shadow_regime_eligible to False and is never treated as a new gate.
    5. otherwise -> CONSISTENT.
    """
    production_status = str(production_alpha_result.get("status") or "unknown")
    production_regime_eligible = production_status == _REGIME_LEVEL_STATUS

    if not production_regime_eligible:
        return ShadowRegimeVerdict(
            alpha_id=alpha_id,
            production_status=production_status,
            production_regime_eligible=False,
            shadow_regime_eligible=None,
            shadow_regime_failures=(),
            regime_evidence_integrity_status=STATUS_NOT_REGIME_CANDIDATE,
        )

    if exposure_value is None:
        return ShadowRegimeVerdict(
            alpha_id=alpha_id,
            production_status=production_status,
            production_regime_eligible=True,
            shadow_regime_eligible=None,
            shadow_regime_failures=(),
            regime_evidence_integrity_status=STATUS_UNVERIFIED_EXPOSURE,
        )

    activation_score = float(production_alpha_result.get("activation_score") or 0.0)
    distinct_agents = int(production_alpha_result.get("distinct_supporting_agents") or 0)
    ticker_specific_count = int(production_alpha_result.get("ticker_specific_evidence_count") or 0)
    local_edge_count = int(production_alpha_result.get("local_edge_count") or 0)
    local_structure_raw = float(
        (production_alpha_result.get("components") or {}).get("local_structure_support", {}).get("raw") or 0.0
    )
    integrity_warnings = production_alpha_result.get("evidence_integrity_warnings") or ()

    shadow_passed, shadow_failures = _evaluate_shadow_gate(
        activation_score=activation_score,
        independent_evidence_group_count=independent_evidence_group_count,
        distinct_agents=distinct_agents,
        ticker_specific_count=ticker_specific_count,
        local_edge_count=local_edge_count,
        local_structure_raw=local_structure_raw,
        integrity_warnings=integrity_warnings,
    )

    if not shadow_passed:
        status = STATUS_OVERLAP_RISK
    elif primary_evidence_group_count < REGIME_GATE_MIN_UNIQUE_EVIDENCE:
        status = STATUS_INSUFFICIENT_PRIMARY_EVIDENCE
    else:
        status = STATUS_CONSISTENT

    return ShadowRegimeVerdict(
        alpha_id=alpha_id,
        production_status=production_status,
        production_regime_eligible=True,
        shadow_regime_eligible=shadow_passed,
        shadow_regime_failures=tuple(shadow_failures),
        regime_evidence_integrity_status=status,
    )


# ---------------------------------------------------------------------------
# Top-level orchestration: one run's full additive sidecar payload.
# ---------------------------------------------------------------------------


def build_alpha_evidence_integrity_payload(
    *,
    run_id: str,
    ticker: str,
    alpha_matches_payload: Mapping[str, Any],
    activation_v2_alphas: Sequence[Mapping[str, Any]],
    graph_edges: Sequence[Mapping[str, Any]] = (),
    structured_records: Iterable[Mapping[str, Any]] | None = None,
    exposure_by_alpha: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Assemble the full, additive Evidence Integrity sidecar for one run.

    Pure function of its inputs; performs no I/O and never mutates any
    argument. Intended to be embedded as an internal, versioned
    ``alpha_evidence_integrity`` block inside ``run_audit.json`` (never a
    public Research API field, never surfaced in Agent Findings) or written
    to a standalone ``evidence_integrity.json`` sidecar -- the choice of
    where to persist this payload is the caller's, not this module's.
    """
    exposure_by_alpha = exposure_by_alpha or {}
    candidates = _build_candidates(
        alpha_matches_payload, graph_edges=graph_edges, structured_records=structured_records
    )
    groups = build_evidence_groups(
        alpha_matches_payload,
        run_id=run_id,
        ticker=ticker,
        graph_edges=graph_edges,
        structured_records=structured_records,
    )
    candidates_by_alpha: dict[str, list[_Candidate]] = {}
    for c in candidates:
        candidates_by_alpha.setdefault(c.matched_alpha, []).append(c)

    alpha_entries: list[dict[str, Any]] = []
    for production_alpha in sorted(activation_v2_alphas, key=lambda a: str(a.get("alpha_id"))):
        alpha_id = str(production_alpha.get("alpha_id"))
        alpha_candidates = candidates_by_alpha.get(alpha_id, ())
        metrics = compute_alpha_evidence_metrics(alpha_id, groups, alpha_candidates)
        primary_groups = [
            g.to_dict() for g in groups if g.primary_alpha_id == alpha_id
        ]
        secondary_groups = [
            g.to_dict() for g in groups if alpha_id in g.secondary_alpha_ids
        ]
        verdict = evaluate_shadow_regime_verdict(
            alpha_id=alpha_id,
            production_alpha_result=production_alpha,
            independent_evidence_group_count=metrics.independent_evidence_group_count,
            primary_evidence_group_count=metrics.primary_evidence_group_count,
            exposure_value=exposure_by_alpha.get(alpha_id),
        )
        alpha_entries.append(
            {
                "alpha_id": alpha_id,
                "production_score": production_alpha.get("activation_score"),
                "production_status": production_alpha.get("status"),
                "metrics": metrics.to_dict(),
                "primary_evidence_groups": primary_groups,
                "secondary_evidence_groups": secondary_groups,
                "shadow_regime_verdict": verdict.to_dict(),
            }
        )

    return {
        "schema_version": EVIDENCE_INTEGRITY_SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "evidence_groups": [g.to_dict() for g in groups],
        "alphas": alpha_entries,
    }


__all__ = [
    "EVIDENCE_INTEGRITY_SCHEMA_VERSION",
    "STATUS_CONSISTENT",
    "STATUS_OVERLAP_RISK",
    "STATUS_INSUFFICIENT_PRIMARY_EVIDENCE",
    "STATUS_UNVERIFIED_EXPOSURE",
    "STATUS_NOT_REGIME_CANDIDATE",
    "VALID_INTEGRITY_STATUSES",
    "EvidenceGroup",
    "AlphaEvidenceMetrics",
    "ShadowRegimeVerdict",
    "build_evidence_groups",
    "compute_alpha_evidence_metrics",
    "evaluate_shadow_regime_verdict",
    "build_alpha_evidence_integrity_payload",
]
