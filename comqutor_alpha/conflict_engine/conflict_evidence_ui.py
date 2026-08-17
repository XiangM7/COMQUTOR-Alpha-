"""B5 Conflict Radar Evidence UI (task B5_CONFLICT_RADAR_EVIDENCE_UI).

Presentation and audit layer only:

    B1 = semantic authority (final evidence_stance per (claim, alpha))
    B2 = deterministic conflict admissibility authority (unique supporting
         Evidence Facts per side, ticker-specific requirement, score>=50)
    B4 = Alpha level classification authority
    B5 = this module -- presents B1's stance results and B2's already-
         computed admissibility detail accurately, auditably; never
         re-judges Evidence semantics, never modifies ConflictScore, never
         changes admitted/main conflict, never calls a Provider.

This module recomputes nothing B1/B2 already decided. It is layered
strictly on top of ``conflict_admissibility.py`` (reuses
``ALPHA_SCORE_THRESHOLD``/``MIN_SUPPORTING_EVIDENCE_PER_SIDE``/
``MIN_TICKER_SPECIFIC_SUPPORT_PER_SIDE`` and the already-computed
``AdmissibilityResult`` for Missing Evidence/Qualification Gaps) and
``conflict_detector.py`` (reuses the caller's own already-gathered
``bull_qualifying``/``bear_qualifying`` claim pools -- built by
``_gather_qualifying_evidence``, which already treats a claim as
"relevant to alpha_id" via broad ``candidate_scores`` membership, not only
the claim's own winning ``matched_alpha`` -- and the caller's own
``_group_qualifying_claims_into_facts``, injected as ``group_into_facts``
exactly like ``evaluate_conflict_admissibility`` already receives it, so
this module never duplicates the Evidence Fact Index grouping algorithm).

Stance lookup only ever reads ``candidate_scores[].evidence_stance``
(the same final field B1's LLM-upgrade-or-deterministic-fallback pipeline
already writes) -- never re-interpreted, never regex-guessed.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from comqutor_alpha.conflict_engine.conflict_admissibility import (
    ALPHA_SCORE_THRESHOLD,
    MIN_SUPPORTING_EVIDENCE_PER_SIDE,
    MIN_TICKER_SPECIFIC_SUPPORT_PER_SIDE,
    AdmissibilityResult,
    SideAdmissibility,
)
from comqutor_alpha.conflict_engine.invalidation_registry import (
    DEFAULT_INVALIDATION_REGISTRY_PATH,
    InvalidationRegistry,
    load_invalidation_registry,
)
from comqutor_alpha.graph_engine.activation_scorer_v2 import _is_ticker_specific
from comqutor_alpha.structure_engine.evidence_stance import (
    OPPOSES_ALPHA,
    SUPPORTS_ALPHA,
    SUPPORTS_COUNTER_ALPHA,
)

EVIDENCE_UI_SCHEMA_VERSION = "conflict_evidence_ui.v1"

BULL = "bull"
BEAR = "bear"

# Missing Evidence reason codes (task section 7) -- deterministic, computed
# solely from B2's own already-computed AdmissibilityResult; never a new
# admissibility threshold.
REASON_INSUFFICIENT_SUPPORTING_EVIDENCE = "INSUFFICIENT_SUPPORTING_EVIDENCE"
REASON_NO_TICKER_SPECIFIC_SUPPORTING_EVIDENCE = "NO_TICKER_SPECIFIC_SUPPORTING_EVIDENCE"
REASON_NO_ADMISSIBLE_SUPPORTING_POLARITY = "NO_ADMISSIBLE_SUPPORTING_POLARITY"

# Qualification gap reason codes (task section 7 -- explicitly NOT Missing
# Evidence: an activation-score shortfall is a qualification concern, never
# an evidence-content concern).
REASON_ALPHA_SCORE_BELOW_THRESHOLD = "ALPHA_SCORE_BELOW_THRESHOLD"


def _candidate_record_for_alpha(record: Mapping[str, Any], alpha_id: str) -> Mapping[str, Any] | None:
    """The full candidate dict for (record, alpha_id) -- same pool-search
    order as ``conflict_admissibility.stance_for_alpha`` (eligible_
    candidates / top_candidates / candidate_scores), but returns the whole
    object (never just the stance string) so display-only provenance
    (counter_alpha_id/stance_method/evidence_stance_version/...) can be
    read alongside the stance without a second, differently-shaped lookup.
    Never re-derives evidence_stance itself -- only locates the exact same
    B1-written object B2 already trusts."""
    for pool_key in ("eligible_candidates", "top_candidates", "candidate_scores"):
        pool = record.get(pool_key)
        if not isinstance(pool, list):
            continue
        for candidate in pool:
            if isinstance(candidate, Mapping) and str(candidate.get("alpha_id")) == alpha_id:
                return candidate
    return None


def _alpha_matches_by_claim_id(alpha_matches: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    # Same normalized-whitespace key as conflict_admissibility.py's own
    # index -- a raw key here would silently miss a qualifying claim
    # whenever the surviving canonical record carries non-normalized
    # whitespace in its claim_id.
    return {
        " ".join(str(record.get("claim_id") or "").split()): record
        for record in alpha_matches
        if isinstance(record, Mapping) and str(record.get("claim_id") or "").strip()
    }


def _sort_key(item: Mapping[str, Any]) -> tuple[bool, float, str]:
    """Deterministic display order (task section 15): ticker-specific
    first, then representative match score descending, then
    evidence_fact_group_id ascending -- never a frontend-local order."""
    return (
        not item["ticker_specific"],
        -item["representative_match_score"],
        item["evidence_fact_group_id"],
    )


def _evidence_items_for_stance(
    qualifying_claims: Sequence[Mapping[str, Any]],
    alpha_matches_by_claim_id: Mapping[str, Mapping[str, Any]],
    *,
    target_alpha_id: str,
    wanted_stance: str,
    counter_alpha_id_filter: str | None,
    ticker: str,
    group_into_facts: Callable[[list[dict[str, Any]]], Any],
) -> list[dict[str, Any]]:
    """One stance-filtered, fact-grouped Evidence list -- the shared
    engine behind Bull/Bear Evidence (wanted_stance=supports_alpha) and
    Counter Evidence Case A (wanted_stance=opposes_alpha) / Case B
    (wanted_stance=supports_counter_alpha, counter_alpha_id_filter=the
    conflict's OTHER alpha). Reuses the caller's own qualifying-claim pool
    and grouping function verbatim -- never a second Evidence Fact Index,
    never a second dedup pass."""
    matched: list[tuple[dict[str, Any], Mapping[str, Any]]] = []
    for claim in qualifying_claims:
        record = alpha_matches_by_claim_id.get(str(claim.get("claim_id") or ""))
        if record is None:
            continue
        candidate = _candidate_record_for_alpha(record, target_alpha_id)
        if candidate is None:
            continue
        if candidate.get("evidence_stance") != wanted_stance:
            continue
        if counter_alpha_id_filter is not None and candidate.get("counter_alpha_id") != counter_alpha_id_filter:
            continue
        matched.append((dict(claim), candidate))

    if not matched:
        return []

    claims_only = [claim for claim, _ in matched]
    candidate_by_claim_id = {claim["claim_id"]: candidate for claim, candidate in matched}
    fact_summary = group_into_facts(claims_only)

    items: list[dict[str, Any]] = []
    for group_id, members in zip(fact_summary.fact_group_ids, fact_summary.fact_groups, strict=True):
        representative = max(members, key=lambda c: c["match_score"])
        representative_candidate = candidate_by_claim_id.get(representative["claim_id"], {})
        item: dict[str, Any] = {
            "evidence_fact_group_id": group_id,
            "representative_claim_id": representative["claim_id"],
            "member_claim_ids": sorted(c["claim_id"] for c in members),
            "evidence_text": representative["evidence"],
            "agents": sorted({c["agent"] for c in members if c.get("agent")}),
            "source_agent_output_ids": sorted(
                {c["source_agent_output_id"] for c in members if c.get("source_agent_output_id")}
            ),
            "target_alpha_id": target_alpha_id,
            "evidence_stance": wanted_stance,
            "stance_method": representative_candidate.get("stance_method"),
            "evidence_stance_version": representative_candidate.get("evidence_stance_version"),
            "stance_confidence_band": representative_candidate.get("stance_confidence_band"),
            "ticker_specific": any(_is_ticker_specific(m, ticker, (), {}) for m in members),
            "representative_match_score": representative["match_score"],
        }
        if wanted_stance == SUPPORTS_COUNTER_ALPHA:
            item["supports_counter_alpha_id"] = representative_candidate.get("counter_alpha_id")
        items.append(item)

    items.sort(key=_sort_key)
    return items


def _bull_or_bear_evidence(
    qualifying_claims: Sequence[Mapping[str, Any]],
    alpha_matches_by_claim_id: Mapping[str, Mapping[str, Any]],
    *,
    alpha_id: str,
    ticker: str,
    group_into_facts: Callable[[list[dict[str, Any]]], Any],
) -> list[dict[str, Any]]:
    return _evidence_items_for_stance(
        qualifying_claims,
        alpha_matches_by_claim_id,
        target_alpha_id=alpha_id,
        wanted_stance=SUPPORTS_ALPHA,
        counter_alpha_id_filter=None,
        ticker=ticker,
        group_into_facts=group_into_facts,
    )


def _counter_evidence_against(
    qualifying_claims: Sequence[Mapping[str, Any]],
    alpha_matches_by_claim_id: Mapping[str, Mapping[str, Any]],
    *,
    target_alpha_id: str,
    other_alpha_id: str,
    ticker: str,
    group_into_facts: Callable[[list[dict[str, Any]]], Any],
) -> list[dict[str, Any]]:
    """Counter Evidence against ``target_alpha_id`` (task section 5):
    Case A (opposes_alpha(target)) plus Case B (supports_counter_alpha
    with counter_alpha_id == the conflict's OTHER side) -- an unrelated
    counter_alpha_id never qualifies. mentions_alpha/neutral_background
    are excluded by construction (neither wanted_stance value here)."""
    case_a = _evidence_items_for_stance(
        qualifying_claims,
        alpha_matches_by_claim_id,
        target_alpha_id=target_alpha_id,
        wanted_stance=OPPOSES_ALPHA,
        counter_alpha_id_filter=None,
        ticker=ticker,
        group_into_facts=group_into_facts,
    )
    for item in case_a:
        item["counter_target_alpha_id"] = target_alpha_id

    case_b = _evidence_items_for_stance(
        qualifying_claims,
        alpha_matches_by_claim_id,
        target_alpha_id=target_alpha_id,
        wanted_stance=SUPPORTS_COUNTER_ALPHA,
        counter_alpha_id_filter=other_alpha_id,
        ticker=ticker,
        group_into_facts=group_into_facts,
    )
    for item in case_b:
        item["counter_target_alpha_id"] = target_alpha_id

    # Dedup key task section 6: evidence_fact_group_id + counter_target_
    # alpha_id -- Case A/B use disjoint stance filters so a genuine claim
    # can never match both, but the combined key is the documented
    # contract regardless of that structural guarantee.
    seen: set[tuple[str, str]] = set()
    combined: list[dict[str, Any]] = []
    for item in (*case_a, *case_b):
        key = (item["evidence_fact_group_id"], item["counter_target_alpha_id"])
        if key in seen:
            continue
        seen.add(key)
        combined.append(item)
    combined.sort(key=_sort_key)
    return combined


def _missing_evidence_for_side(
    side: SideAdmissibility, *, side_label: str, has_any_qualifying_evidence: bool
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if side.supporting_evidence_count < MIN_SUPPORTING_EVIDENCE_PER_SIDE:
        items.append(
            {
                "side": side_label,
                "alpha_id": side.alpha_id,
                "missing_reason_code": REASON_INSUFFICIENT_SUPPORTING_EVIDENCE,
                "current_value": side.supporting_evidence_count,
                "required_value": MIN_SUPPORTING_EVIDENCE_PER_SIDE,
                "deficit": MIN_SUPPORTING_EVIDENCE_PER_SIDE - side.supporting_evidence_count,
            }
        )
        # Evidence exists (any polarity) but none of it is admissible
        # support -- a more specific diagnosis than a bare zero count,
        # never a replacement for INSUFFICIENT_SUPPORTING_EVIDENCE above.
        if side.supporting_evidence_count == 0 and has_any_qualifying_evidence:
            items.append(
                {
                    "side": side_label,
                    "alpha_id": side.alpha_id,
                    "missing_reason_code": REASON_NO_ADMISSIBLE_SUPPORTING_POLARITY,
                    "current_value": 0,
                    "required_value": 1,
                    "deficit": 1,
                }
            )
    if side.ticker_specific_support_count < MIN_TICKER_SPECIFIC_SUPPORT_PER_SIDE:
        items.append(
            {
                "side": side_label,
                "alpha_id": side.alpha_id,
                "missing_reason_code": REASON_NO_TICKER_SPECIFIC_SUPPORTING_EVIDENCE,
                "current_value": side.ticker_specific_support_count,
                "required_value": MIN_TICKER_SPECIFIC_SUPPORT_PER_SIDE,
                "deficit": MIN_TICKER_SPECIFIC_SUPPORT_PER_SIDE - side.ticker_specific_support_count,
            }
        )
    return items


def _qualification_gap_for_side(side: SideAdmissibility, *, side_label: str) -> dict[str, Any] | None:
    if side.score is None or side.score < ALPHA_SCORE_THRESHOLD:
        return {
            "side": side_label,
            "alpha_id": side.alpha_id,
            "gap_reason_code": REASON_ALPHA_SCORE_BELOW_THRESHOLD,
            "current_value": side.score,
            "required_value": ALPHA_SCORE_THRESHOLD,
        }
    return None


_REGISTRY_CACHE: InvalidationRegistry | None = None


def _cached_registry(registry_path: str | None) -> InvalidationRegistry:
    global _REGISTRY_CACHE
    if registry_path is not None:
        return load_invalidation_registry(registry_path)
    if _REGISTRY_CACHE is None:
        _REGISTRY_CACHE = load_invalidation_registry(DEFAULT_INVALIDATION_REGISTRY_PATH)
    return _REGISTRY_CACHE


def build_conflict_evidence_ui(
    *,
    run_id: str,
    ticker: str,
    bull_alpha_id: str,
    bear_alpha_id: str,
    bull_alpha_name: str | None,
    bear_alpha_name: str | None,
    bull_qualifying: Sequence[Mapping[str, Any]],
    bear_qualifying: Sequence[Mapping[str, Any]],
    alpha_matches: Sequence[Mapping[str, Any]],
    admissibility: AdmissibilityResult,
    group_into_facts: Callable[[list[dict[str, Any]]], Any],
    invalidation_registry_path: str | None = None,
) -> dict[str, Any]:
    """The single B5 entry point (task section 11). Called once per
    fully-evaluated candidate pair (whether ultimately admitted or
    B2-suppressed) -- never re-derives bull/bear identity, activation
    score, qualifying evidence, Evidence Fact grouping, or admissibility;
    every one of those is consumed exactly as already computed by
    ``conflict_detector``/``conflict_admissibility``.
    """
    alpha_matches_by_claim_id = _alpha_matches_by_claim_id(alpha_matches)

    bull_evidence = _bull_or_bear_evidence(
        bull_qualifying,
        alpha_matches_by_claim_id,
        alpha_id=bull_alpha_id,
        ticker=ticker,
        group_into_facts=group_into_facts,
    )
    bear_evidence = _bull_or_bear_evidence(
        bear_qualifying,
        alpha_matches_by_claim_id,
        alpha_id=bear_alpha_id,
        ticker=ticker,
        group_into_facts=group_into_facts,
    )
    # Counter Evidence searches the UNION of both sides' already-qualifying
    # pools (never a third, wider, unrelated-to-this-pair search): B1's own
    # stance classification attaches a verdict for every candidate in a
    # claim's candidate_scores list, not only its winning matched_alpha, so
    # a claim whose home is bear_alpha_id can legitimately also carry an
    # opposes_alpha/supports_counter_alpha verdict for bull_alpha_id (task
    # section 6's "same fact, two Alpha-relative roles"). Deduped by
    # claim_id first -- qualifying_a/qualifying_b are disjoint by
    # construction (one matched_alpha each), but a defensive union guards
    # against ever double-counting if that ever changed.
    combined_qualifying_by_id = {
        str(claim.get("claim_id") or ""): claim for claim in (*bull_qualifying, *bear_qualifying)
    }
    combined_qualifying = list(combined_qualifying_by_id.values())
    counter_against_bull = _counter_evidence_against(
        combined_qualifying,
        alpha_matches_by_claim_id,
        target_alpha_id=bull_alpha_id,
        other_alpha_id=bear_alpha_id,
        ticker=ticker,
        group_into_facts=group_into_facts,
    )
    counter_against_bear = _counter_evidence_against(
        combined_qualifying,
        alpha_matches_by_claim_id,
        target_alpha_id=bear_alpha_id,
        other_alpha_id=bull_alpha_id,
        ticker=ticker,
        group_into_facts=group_into_facts,
    )
    counter_evidence = sorted((*counter_against_bull, *counter_against_bear), key=_sort_key)

    missing_evidence = [
        *_missing_evidence_for_side(
            admissibility.bull, side_label=BULL, has_any_qualifying_evidence=bool(bull_qualifying)
        ),
        *_missing_evidence_for_side(
            admissibility.bear, side_label=BEAR, has_any_qualifying_evidence=bool(bear_qualifying)
        ),
    ]
    qualification_gaps = [
        gap
        for gap in (
            _qualification_gap_for_side(admissibility.bull, side_label=BULL),
            _qualification_gap_for_side(admissibility.bear, side_label=BEAR),
        )
        if gap is not None
    ]

    registry = _cached_registry(invalidation_registry_path)
    invalidation_conditions = {
        "bull_alpha": registry.entry_for(bull_alpha_id, bull_alpha_name).to_dict(),
        "bear_alpha": registry.entry_for(bear_alpha_id, bear_alpha_name).to_dict(),
    }

    return {
        "schema_version": EVIDENCE_UI_SCHEMA_VERSION,
        "bull_evidence": bull_evidence,
        "bear_evidence": bear_evidence,
        "counter_evidence": counter_evidence,
        "missing_evidence": missing_evidence,
        "qualification_gaps": qualification_gaps,
        "invalidation_conditions": invalidation_conditions,
    }


__all__ = [
    "EVIDENCE_UI_SCHEMA_VERSION",
    "REASON_ALPHA_SCORE_BELOW_THRESHOLD",
    "REASON_INSUFFICIENT_SUPPORTING_EVIDENCE",
    "REASON_NO_ADMISSIBLE_SUPPORTING_POLARITY",
    "REASON_NO_TICKER_SPECIFIC_SUPPORTING_EVIDENCE",
    "build_conflict_evidence_ui",
]
