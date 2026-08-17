"""John's B2 Conflict Evidence Admissibility gate (Week 4 Conflict Core).

Layered strictly on top of the existing, unmodified W4.1 Conflict Detector:
this module never re-derives a candidate pair, an activation score, a
qualifying-evidence set, an Evidence Fact grouping, or a bull/bear role --
it only asks, of an already-fully-evaluated candidate, one further
deterministic question John specified: does each side have enough
*B1-stance-confirmed* evidence to be trusted as an admitted (not merely
candidate) structural conflict?

Consumes, never recomputes:
  * ``conflict_schema.resolve_bull_bear`` -- existing bull/bear identity.
  * the activation score already extracted by
    ``conflict_detector._extract_activation_fields`` (the same
    ``activation_score`` field the UI/API already treats as authoritative;
    already on a 0-100 scale, never rescaled here).
  * ``evidence_fact_index.group_evidence_candidates`` (via
    ``conflict_detector._group_qualifying_claims_into_facts``, called again
    here only on a *smaller, stance-filtered* subset of the SAME already-
    qualifying claim pool -- never a second grouping algorithm).
  * ``activation_scorer_v2._is_ticker_specific`` -- the real, existing,
    per-claim ticker-specificity check (token-boundary match of the ticker
    symbol against the claim/evidence text; explicitly guards against the
    exact "every claim's entities include the auto-appended run ticker"
    trap that made an earlier, different field always True). Reused with
    ``company_names=()``/``entities_by_claim={}`` -- the exact values the
    real production Activation v2 call site
    (``graph_engine.pipeline.score_and_assemble_structure_graph``) already
    passes; this module's use of the function is therefore behaviorally
    identical to production, not a new heuristic.

B1 stance is read, never re-interpreted: ``stance_for_alpha`` looks up the
already-attached ``candidate_scores[].evidence_stance`` for one
(claim_id, alpha_id) pair -- the SAME final field
``evidence_stance_llm.apply_llm_stance_upgrade`` writes (whether the winning
method was ``llm`` or ``deterministic_fallback``; this module never reads or
branches on ``stance_method``, matching John's explicit instruction that the
resolution method is not a new admissibility criterion). Only the literal
string ``"supports_alpha"`` counts as supporting evidence for that side;
``opposes_alpha``/``mentions_alpha``/``neutral_background``/
``supports_counter_alpha`` never do, and no other module (regex, keyword
semantics, direction semantics, ``alpha_relation``, or an LLM) is consulted.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from comqutor_alpha.graph_engine.activation_scorer_v2 import _is_ticker_specific
from comqutor_alpha.structure_engine.evidence_stance import SUPPORTS_ALPHA

ADMISSIBILITY_VERSION = "week4.conflict_admissibility.b2.v1"

ADMITTED = "admitted"
CANDIDATE = "candidate"

# John's B2 thresholds (task spec section 2) -- literal frozen constants,
# never tunable/config values, exactly like the Conflict Core's own
# CONFLICT_FORMULA_VERSION weights and ADMISSIBLE_STATUSES.
ALPHA_SCORE_THRESHOLD = 50.0
MIN_SUPPORTING_EVIDENCE_PER_SIDE = 2
MIN_TICKER_SPECIFIC_SUPPORT_PER_SIDE = 1

REASON_BULL_SCORE_BELOW_THRESHOLD = "BULL_SCORE_BELOW_THRESHOLD"
REASON_BEAR_SCORE_BELOW_THRESHOLD = "BEAR_SCORE_BELOW_THRESHOLD"
REASON_INSUFFICIENT_BULL_SUPPORTING_EVIDENCE = "INSUFFICIENT_BULL_SUPPORTING_EVIDENCE"
REASON_INSUFFICIENT_BEAR_SUPPORTING_EVIDENCE = "INSUFFICIENT_BEAR_SUPPORTING_EVIDENCE"
REASON_NO_BULL_TICKER_SPECIFIC_SUPPORT = "NO_BULL_TICKER_SPECIFIC_SUPPORT"
REASON_NO_BEAR_TICKER_SPECIFIC_SUPPORT = "NO_BEAR_TICKER_SPECIFIC_SUPPORT"
# Not currently reachable (the real ticker-specific signal is verified --
# see the module docstring), kept as a named, documented fail-closed
# escape hatch per task spec section 9/13: if a future caller ever supplies
# a ticker-specificity signal this module cannot verify, admission must
# fail closed to CANDIDATE rather than silently treat it as satisfied.
REASON_TICKER_SPECIFIC_EVIDENCE_UNVERIFIED = "TICKER_SPECIFIC_EVIDENCE_UNVERIFIED"

ALL_REASON_CODES = frozenset(
    {
        REASON_BULL_SCORE_BELOW_THRESHOLD,
        REASON_BEAR_SCORE_BELOW_THRESHOLD,
        REASON_INSUFFICIENT_BULL_SUPPORTING_EVIDENCE,
        REASON_INSUFFICIENT_BEAR_SUPPORTING_EVIDENCE,
        REASON_NO_BULL_TICKER_SPECIFIC_SUPPORT,
        REASON_NO_BEAR_TICKER_SPECIFIC_SUPPORT,
        REASON_TICKER_SPECIFIC_EVIDENCE_UNVERIFIED,
    }
)


def stance_for_alpha(record: Mapping[str, Any], alpha_id: str) -> str | None:
    """Read back the already-attached final B1 stance for ``alpha_id`` from
    whichever candidate pool the record carries it in -- the exact same
    pool-search pattern ``conflict_detector._relation_for_match``/
    ``evidence_fact_index.relation_for_match`` already use for ``relation``,
    applied to ``evidence_stance`` instead. Never recomputes/reinterprets
    stance; returns ``None`` when no candidate entry exists for this alpha
    (never defaults to a value that could look like support)."""
    for pool_key in ("eligible_candidates", "top_candidates", "candidate_scores"):
        pool = record.get(pool_key)
        if not isinstance(pool, list):
            continue
        for candidate in pool:
            if isinstance(candidate, Mapping) and str(candidate.get("alpha_id")) == alpha_id:
                stance = candidate.get("evidence_stance")
                return str(stance) if isinstance(stance, str) and stance else None
    return None


@dataclass(frozen=True)
class SideAdmissibility:
    alpha_id: str
    score: float | None
    supporting_evidence_count: int
    ticker_specific_support_count: int
    supporting_fact_group_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class AdmissibilityResult:
    status: str
    reason_codes: tuple[str, ...]
    bull: SideAdmissibility
    bear: SideAdmissibility

    def to_dict(self) -> dict[str, Any]:
        return {
            "admissibility_version": ADMISSIBILITY_VERSION,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "bull_score": self.bull.score,
            "bear_score": self.bear.score,
            "bull_supporting_evidence_count": self.bull.supporting_evidence_count,
            "bear_supporting_evidence_count": self.bear.supporting_evidence_count,
            "bull_ticker_specific_support_count": self.bull.ticker_specific_support_count,
            "bear_ticker_specific_support_count": self.bear.ticker_specific_support_count,
            "bull_supporting_fact_group_ids": list(self.bull.supporting_fact_group_ids),
            "bear_supporting_fact_group_ids": list(self.bear.supporting_fact_group_ids),
        }


def _stance_filtered_qualifying(
    qualifying_claims: Sequence[Mapping[str, Any]],
    alpha_matches_by_claim_id: Mapping[str, Mapping[str, Any]],
    alpha_id: str,
) -> list[dict[str, Any]]:
    """Only qualifying claims (conflict_detector's own already-admitted
    evidence pool -- never widened/narrowed here) whose FINAL B1 stance
    relative to ``alpha_id`` is exactly ``supports_alpha``. A claim with no
    B1 stance data at all (e.g. a pre-B1 record, or B1 simply never having
    run for this run) is not support -- an absent stance is never treated
    as an implicit supports_alpha."""
    kept = []
    for claim in qualifying_claims:
        claim_id = str(claim.get("claim_id") or "")
        record = alpha_matches_by_claim_id.get(claim_id)
        if record is None:
            continue
        if stance_for_alpha(record, alpha_id) == SUPPORTS_ALPHA:
            kept.append(dict(claim))
    return kept


def _evaluate_side(
    alpha_id: str,
    score: float | None,
    qualifying_claims: Sequence[Mapping[str, Any]],
    alpha_matches_by_claim_id: Mapping[str, Mapping[str, Any]],
    *,
    ticker: str,
    group_into_facts: Any,
    score_reason: str,
    evidence_reason: str,
    ticker_reason: str,
) -> SideAdmissibility:
    reason_codes: list[str] = []
    if score is None or score < ALPHA_SCORE_THRESHOLD:
        reason_codes.append(score_reason)

    supporting = _stance_filtered_qualifying(qualifying_claims, alpha_matches_by_claim_id, alpha_id)
    fact_summary = group_into_facts(supporting)
    supporting_evidence_count = len(fact_summary.fact_group_ids)
    if supporting_evidence_count < MIN_SUPPORTING_EVIDENCE_PER_SIDE:
        reason_codes.append(evidence_reason)

    ticker_specific_support_count = 0
    for members in fact_summary.fact_groups:
        if any(_is_ticker_specific(member, ticker, (), {}) for member in members):
            ticker_specific_support_count += 1
    if ticker_specific_support_count < MIN_TICKER_SPECIFIC_SUPPORT_PER_SIDE:
        reason_codes.append(ticker_reason)

    return SideAdmissibility(
        alpha_id=alpha_id,
        score=score,
        supporting_evidence_count=supporting_evidence_count,
        ticker_specific_support_count=ticker_specific_support_count,
        supporting_fact_group_ids=tuple(fact_summary.fact_group_ids),
        reason_codes=tuple(reason_codes),
    )


def evaluate_conflict_admissibility(
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
) -> AdmissibilityResult:
    """Evaluate John's B2 gate for one already-fully-evaluated existing
    conflict candidate.

    ``group_into_facts`` is the caller's own
    ``conflict_detector._group_qualifying_claims_into_facts`` (partially
    applied with ``run_id``/``ticker``) -- injected rather than imported
    here, so this module never needs to duplicate that function's ``run_id``
    parameter threading, and so the exact same Evidence Fact Index
    algorithm/id scheme conflict_detector already uses for its own
    ``bull_facts``/``bear_facts`` is reused for the stance-filtered subset,
    never a second grouping implementation.
    """
    # Keyed by the SAME normalized (whitespace-collapsed/stripped) claim_id
    # conflict_detector's own _gather_qualifying_evidence/
    # _canonicalize_alpha_matches use -- a raw, un-normalized key here would
    # silently fail to match a qualifying claim whenever the surviving
    # canonical record for a duplicated claim_id happens to carry
    # non-normalized whitespace (e.g. "  cA  "), dropping that claim out of
    # the stance lookup entirely rather than correctly finding its stance.
    alpha_matches_by_claim_id = {
        " ".join(str(record.get("claim_id") or "").split()): record
        for record in alpha_matches
        if isinstance(record, Mapping) and str(record.get("claim_id") or "").strip()
    }

    bull = _evaluate_side(
        bull_alpha_id,
        bull_score,
        bull_qualifying_claims,
        alpha_matches_by_claim_id,
        ticker=ticker,
        group_into_facts=group_into_facts,
        score_reason=REASON_BULL_SCORE_BELOW_THRESHOLD,
        evidence_reason=REASON_INSUFFICIENT_BULL_SUPPORTING_EVIDENCE,
        ticker_reason=REASON_NO_BULL_TICKER_SPECIFIC_SUPPORT,
    )
    bear = _evaluate_side(
        bear_alpha_id,
        bear_score,
        bear_qualifying_claims,
        alpha_matches_by_claim_id,
        ticker=ticker,
        group_into_facts=group_into_facts,
        score_reason=REASON_BEAR_SCORE_BELOW_THRESHOLD,
        evidence_reason=REASON_INSUFFICIENT_BEAR_SUPPORTING_EVIDENCE,
        ticker_reason=REASON_NO_BEAR_TICKER_SPECIFIC_SUPPORT,
    )

    reason_codes = tuple(bull.reason_codes) + tuple(bear.reason_codes)
    status = CANDIDATE if reason_codes else ADMITTED
    return AdmissibilityResult(status=status, reason_codes=reason_codes, bull=bull, bear=bear)


__all__ = [
    "ADMISSIBILITY_VERSION",
    "ADMITTED",
    "CANDIDATE",
    "ALPHA_SCORE_THRESHOLD",
    "MIN_SUPPORTING_EVIDENCE_PER_SIDE",
    "MIN_TICKER_SPECIFIC_SUPPORT_PER_SIDE",
    "REASON_BULL_SCORE_BELOW_THRESHOLD",
    "REASON_BEAR_SCORE_BELOW_THRESHOLD",
    "REASON_INSUFFICIENT_BULL_SUPPORTING_EVIDENCE",
    "REASON_INSUFFICIENT_BEAR_SUPPORTING_EVIDENCE",
    "REASON_NO_BULL_TICKER_SPECIFIC_SUPPORT",
    "REASON_NO_BEAR_TICKER_SPECIFIC_SUPPORT",
    "REASON_TICKER_SPECIFIC_EVIDENCE_UNVERIFIED",
    "ALL_REASON_CODES",
    "SideAdmissibility",
    "AdmissibilityResult",
    "stance_for_alpha",
    "evaluate_conflict_admissibility",
]
