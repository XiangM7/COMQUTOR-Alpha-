"""Per-ticker A4 regression evaluation core (task sections 8-12).

For one ticker: reprocesses the selected saved run via the existing,
zero-Provider Architecture Replay path
(``comqutor_alpha.replay.pipeline.run_structure_replay``), reads the
replay's own freshly-computed Alpha/Graph/Conflict results, and compares
them against J2's provisional expectations. Never re-runs TradingAgents,
never calls an LLM/Provider, never mutates the source run's own
directory (Architecture Replay itself already guarantees this and
verifies it via a source-artifact hash/size/mtime check), never modifies
B1-B5/A3 thresholds, scoring, admissibility, or taxonomy -- every
comparison here reads already-computed values only.

Architecture Replay always calls ``build_alpha_matches_payload`` with no
``llm_gateway`` (see its own docstring: "Architecture Replay, which never
passes one"), so B1's LLM stance upgrade is always a zero-cost no-op here
-- every regression result's ``stance_source`` is therefore always
``"deterministic_baseline"``, never ``"llm_semantic"``/``"mixed"``. This
is reported honestly, not hidden: a saved run's *own* already-persisted
``alpha_matches.json`` may have been produced with live LLM stance, but
this module never reads that file -- only the fresh, zero-Provider
replay output.
"""

from __future__ import annotations

from typing import Any

from comqutor_alpha.audit.ticker_consistency import (
    audit_ticker_consistency,
    resolve_expected_ticker,
)
from comqutor_alpha.conflict_engine.conflict_admissibility import ADMITTED, CANDIDATE
from comqutor_alpha.conflict_engine.conflict_schema import canonical_pair_key, conflict_id
from comqutor_alpha.replay.pipeline import (
    DEFAULT_SOURCE_OUTPUT_ROOT,
    ReplaySourceIncompleteError,
    run_structure_replay,
)
from comqutor_alpha.storage.file_store import load_json_record_if_exists
from comqutor_alpha.structure_engine.evidence_stance import (
    SUPPORTS_ALPHA,
    SUPPORTS_COUNTER_ALPHA,
    VALID_EVIDENCE_STANCES,
)
from comqutor_alpha.structure_engine.evidence_stance_llm import STANCE_METHOD_LLM

STANCE_METHOD_DETERMINISTIC_FALLBACK = "deterministic_fallback"

STANCE_SOURCE_LLM_SEMANTIC = "llm_semantic"
STANCE_SOURCE_DETERMINISTIC_BASELINE = "deterministic_baseline"
STANCE_SOURCE_MIXED = "mixed"
STANCE_SOURCE_UNAVAILABLE = "unavailable"

OFFLINE_REPROCESS_PATH_UNAVAILABLE = "OFFLINE_REPROCESS_PATH_UNAVAILABLE"

_MAX_ERROR_DETAILS = 50


# ---------------------------------------------------------------------------
# Alpha comparison (task section 9)
# ---------------------------------------------------------------------------


def _alpha_ids(entries: Any) -> list[str]:
    ids: set[str] = set()
    for entry in entries or ():
        if isinstance(entry, dict) and entry.get("alpha_id"):
            ids.add(str(entry["alpha_id"]))
    return sorted(ids)


def detected_alpha_sets(graph_payload: dict[str, Any]) -> dict[str, list[str]]:
    """Reads B4's own already-computed, already-split collections off the
    structure graph payload -- never re-derives qualification. B4's
    top-level ``dominant_alphas`` keeps its A2-frozen blended meaning
    (dominant OR regime_level); a pure dominant-only list is recovered by
    set difference against the pure ``regime_level_alphas`` collection,
    never by re-classifying anything."""
    active = _alpha_ids(graph_payload.get("active_alphas"))
    dominant_or_regime = _alpha_ids(graph_payload.get("dominant_alphas"))
    regime_level = _alpha_ids(graph_payload.get("regime_level_alphas"))
    dominant_only = sorted(set(dominant_or_regime) - set(regime_level))
    candidate = _alpha_ids(graph_payload.get("candidate_alphas"))
    blocked = _alpha_ids(graph_payload.get("blocked_alphas"))
    detected = sorted(set(active) | set(dominant_only) | set(regime_level))
    return {
        "active_alphas": active,
        "dominant_alphas": dominant_only,
        "regime_level_alphas": regime_level,
        "candidate_alphas": candidate,
        "blocked_alphas": blocked,
        "detected_alphas": detected,
    }


def alpha_comparison(label_block: dict[str, Any] | None, detected: dict[str, list[str]]) -> dict[str, Any]:
    """Task section 9's exact comparison rules. A conditional alpha's
    presence never counts as unexpected; its absence never counts as
    missing."""
    positive = set(label_block.get("expected_positive_alphas") or ()) if label_block else set()
    negative = set(label_block.get("expected_negative_alphas") or ()) if label_block else set()
    conditional = set(label_block.get("conditional_alphas") or ()) if label_block else set()
    expected = positive | negative
    detected_set = set(detected["detected_alphas"])

    missing_expected = sorted(expected - detected_set)
    unexpected_alphas = sorted(detected_set - positive - negative - conditional)

    return {
        "expected_positive_alphas": sorted(positive),
        "expected_negative_alphas": sorted(negative),
        "conditional_alphas": sorted(conditional),
        "expected_alphas": sorted(expected),
        "missing_expected": missing_expected,
        "unexpected_alphas": unexpected_alphas,
    }


# ---------------------------------------------------------------------------
# Conflict comparison (task section 11)
# ---------------------------------------------------------------------------


def _conflict_pair_id(alpha_a: Any, alpha_b: Any) -> str | None:
    if not alpha_a or not alpha_b:
        return None
    a, b = canonical_pair_key(str(alpha_a), str(alpha_b))
    return conflict_id(a, b)


def conflict_comparison(label_block: dict[str, Any] | None, conflict_payload: dict[str, Any]) -> dict[str, Any]:
    """Reads B2's already-computed admitted/candidate/main_conflict --
    never a second admissibility evaluation. ``main_conflict`` must
    already come from ``conflicts`` (conflict_detector's own contract:
    ``main_conflict = conflicts[0] if conflicts else None``); this is
    independently re-verified here, never assumed."""
    admitted = [c for c in (conflict_payload.get("conflicts") or ()) if isinstance(c, dict)]
    admitted_ids = sorted({c.get("conflict_id") for c in admitted if c.get("conflict_id")})

    arbitration = conflict_payload.get("arbitration") or {}
    candidate_status: dict[str, dict[str, Any]] = {}
    for item in arbitration.get("candidate_evaluations") or ():
        if not isinstance(item, dict):
            continue
        pair_id = _conflict_pair_id(item.get("alpha_a"), item.get("alpha_b"))
        if pair_id is None:
            continue
        admissibility = item.get("admissibility") or {}
        candidate_status[pair_id] = {
            "status": admissibility.get("status"),
            "reason_codes": list(admissibility.get("reason_codes") or ()),
        }
    candidate_ids = sorted(pair for pair, info in candidate_status.items() if info["status"] == CANDIDATE)

    main_conflict = conflict_payload.get("main_conflict")
    main_conflict_id = main_conflict.get("conflict_id") if isinstance(main_conflict, dict) else None
    main_conflict_in_admitted = main_conflict_id in admitted_ids if main_conflict_id else True

    allowed = sorted(label_block.get("allowed_main_conflicts") or ()) if label_block else []
    main_conflict_match = (main_conflict_id in allowed) if (allowed and main_conflict_id) else (
        False if allowed else None
    )

    expected_pair_status: dict[str, str] = {}
    candidate_failure_reasons: dict[str, list[str]] = {}
    for pair in allowed:
        if pair in admitted_ids:
            expected_pair_status[pair] = ADMITTED
        elif pair in candidate_status:
            expected_pair_status[pair] = CANDIDATE
            candidate_failure_reasons[pair] = candidate_status[pair]["reason_codes"]
        else:
            expected_pair_status[pair] = "not_reached"

    return {
        "admitted_conflicts": admitted_ids,
        "candidate_conflicts": candidate_ids,
        "main_conflict": main_conflict_id,
        "main_conflict_in_admitted": main_conflict_in_admitted,
        "allowed_main_conflicts": allowed,
        "main_conflict_match": main_conflict_match,
        "expected_pair_status": expected_pair_status,
        "candidate_failure_reasons": candidate_failure_reasons,
    }


# ---------------------------------------------------------------------------
# Dominance guard (task section 10) -- human-review flag only, never an
# automatic semantic judgment, never a B4 classification change.
# ---------------------------------------------------------------------------


def _v2_alpha_entries(graph_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    versions = graph_payload.get("activation_versions") or {}
    v2 = versions.get("v2") or {}
    alphas = v2.get("alphas")
    entries = alphas if isinstance(alphas, list) else []
    return {str(e["alpha_id"]): e for e in entries if isinstance(e, dict) and e.get("alpha_id")}


def dominance_guard_flags(
    label_block: dict[str, Any] | None,
    graph_payload: dict[str, Any],
    exposure_seed_for_ticker: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    guard_map = (label_block or {}).get("should_not_be_dominant_without_strong_evidence") or {}
    if not guard_map:
        return []
    entries = _v2_alpha_entries(graph_payload)
    exposures = (exposure_seed_for_ticker or {}).get("exposures") or {}
    flags: list[dict[str, Any]] = []
    for alpha_id in sorted(guard_map):
        entry = entries.get(alpha_id)
        if entry is None:
            continue
        status = entry.get("status")
        if status not in ("dominant", "regime_level"):
            continue
        flags.append(
            {
                "alpha_id": alpha_id,
                "qualified_level": status,
                "expected_evidence_condition": guard_map[alpha_id],
                "actual_supporting_fact_count": entry.get("unique_evidence_count"),
                "ticker_specific_fact_count": entry.get("ticker_specific_evidence_count"),
                "graph_support": entry.get("local_edge_count"),
                "exposure_state": exposures.get(alpha_id),
                "review_status": "dominance_guard_review_required",
            }
        )
    return flags


# ---------------------------------------------------------------------------
# Evidence polarity contract-integrity checks (task section 12) -- never a
# claim of B1 semantic accuracy.
# ---------------------------------------------------------------------------


def evidence_polarity_errors(alpha_matches_payload: dict[str, Any], conflict_payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    matches = alpha_matches_payload.get("matches") or ()

    for match in matches:
        if not isinstance(match, dict):
            continue
        claim_id = match.get("claim_id")
        for candidate in match.get("candidate_scores") or ():
            if not isinstance(candidate, dict) or "evidence_stance" not in candidate:
                continue
            stance = candidate.get("evidence_stance")
            alpha_id = candidate.get("alpha_id")
            if stance not in VALID_EVIDENCE_STANCES:
                errors.append(
                    {"code": "INVALID_STANCE_VOCABULARY", "claim_id": claim_id, "alpha_id": alpha_id, "value": stance}
                )
                continue
            counter_alpha_id = candidate.get("counter_alpha_id")
            if stance == SUPPORTS_COUNTER_ALPHA:
                if not counter_alpha_id or counter_alpha_id == alpha_id:
                    errors.append(
                        {
                            "code": "ILLEGAL_COUNTER_ALPHA_ID",
                            "claim_id": claim_id,
                            "alpha_id": alpha_id,
                            "counter_alpha_id": counter_alpha_id,
                        }
                    )
            elif counter_alpha_id:
                errors.append(
                    {
                        "code": "UNEXPECTED_COUNTER_ALPHA_ID",
                        "claim_id": claim_id,
                        "alpha_id": alpha_id,
                        "counter_alpha_id": counter_alpha_id,
                    }
                )

        matched_alpha = match.get("matched_alpha")
        if matched_alpha:
            matching = [
                c for c in (match.get("candidate_scores") or ()) if isinstance(c, dict) and c.get("alpha_id") == matched_alpha
            ]
            if len(matching) != 1:
                errors.append(
                    {
                        "code": "MATCHED_ALPHA_CANDIDATE_IDENTITY_MISMATCH",
                        "claim_id": claim_id,
                        "matched_alpha": matched_alpha,
                        "candidate_count": len(matching),
                    }
                )
            elif matching[0].get("evidence_stance") != match.get("matched_evidence_stance"):
                errors.append(
                    {
                        "code": "MATCHED_EVIDENCE_STANCE_PROMOTION_MISMATCH",
                        "claim_id": claim_id,
                        "matched_alpha": matched_alpha,
                    }
                )

    for conflict in conflict_payload.get("conflicts") or ():
        if not isinstance(conflict, dict):
            continue
        evidence_ui = conflict.get("evidence_ui") or {}
        for side_key in ("bull_evidence", "bear_evidence"):
            for item in evidence_ui.get(side_key) or ():
                if not isinstance(item, dict):
                    continue
                if item.get("evidence_stance") != SUPPORTS_ALPHA:
                    errors.append(
                        {
                            "code": "SUPPORTING_POOL_NON_SUPPORTS_ALPHA_FACT",
                            "conflict_id": conflict.get("conflict_id"),
                            "side": side_key,
                            "claim_id": item.get("claim_id"),
                            "evidence_stance": item.get("evidence_stance"),
                        }
                    )

    return {
        "evidence_polarity_errors": len(errors),
        "evidence_polarity_error_scope": "contract_integrity_only",
        "evidence_polarity_error_details": errors[:_MAX_ERROR_DETAILS],
        "semantic_polarity_accuracy": None,
        "semantic_polarity_review_status": "PENDING_J3_HUMAN_REVIEW",
    }


def stance_source(alpha_matches_payload: dict[str, Any]) -> str:
    llm_count = 0
    fallback_count = 0
    never_attempted_count = 0
    total = 0
    for match in alpha_matches_payload.get("matches") or ():
        if not isinstance(match, dict):
            continue
        for candidate in match.get("candidate_scores") or ():
            if not isinstance(candidate, dict) or "evidence_stance" not in candidate:
                continue
            total += 1
            method = candidate.get("stance_method")
            if method == STANCE_METHOD_LLM:
                llm_count += 1
            elif method == STANCE_METHOD_DETERMINISTIC_FALLBACK:
                fallback_count += 1
            else:
                never_attempted_count += 1
    if total == 0:
        return STANCE_SOURCE_UNAVAILABLE
    if llm_count > 0 and (fallback_count > 0 or never_attempted_count > 0):
        return STANCE_SOURCE_MIXED
    if llm_count > 0:
        return STANCE_SOURCE_LLM_SEMANTIC
    return STANCE_SOURCE_DETERMINISTIC_BASELINE


# ---------------------------------------------------------------------------
# Per-ticker orchestration
# ---------------------------------------------------------------------------


def evaluate_ticker(
    ticker: str,
    selection: dict[str, Any],
    label_block: dict[str, Any] | None,
    *,
    source_output_root: str = DEFAULT_SOURCE_OUTPUT_ROOT,
    replay_output_root: str,
    exposure_seed_for_ticker: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluates one ticker end-to-end. ``selection`` is the result of
    :func:`comqutor_alpha.regression.run_selection.select_run_for_ticker`.
    Never calls a Provider (Architecture Replay's own contract);
    ``comparison=False`` since A4 needs no claim/edge-level diagnostic
    diff (Replay's own -- Alpha/Conflict comparison is this module's
    job, not Replay's)."""
    base: dict[str, Any] = {
        "ticker": str(ticker).upper(),
        "run_id": selection.get("run_id"),
        "analysis_date": selection.get("analysis_date"),
        "run_selection_status": selection.get("run_selection_status"),
        "artifact_completeness": selection.get("file_artifact_completeness"),
        "database_record_status": selection.get("database_record_status"),
    }

    if selection.get("run_selection_status") != "selected":
        base.update(
            {
                "offline_reprocess_status": "not_attempted",
                "expected_positive_alphas": sorted((label_block or {}).get("expected_positive_alphas") or ()),
                "expected_negative_alphas": sorted((label_block or {}).get("expected_negative_alphas") or ()),
                "conditional_alphas": sorted((label_block or {}).get("conditional_alphas") or ()),
                "expected_alphas": sorted(
                    {*((label_block or {}).get("expected_positive_alphas") or ()), *((label_block or {}).get("expected_negative_alphas") or ())}
                ),
                "detected_alphas": [],
                "active_alphas": [],
                "dominant_alphas": [],
                "regime_level_alphas": [],
                "candidate_alphas": [],
                "blocked_alphas": [],
                "missing_expected": [],
                "unexpected_alphas": [],
                "allowed_main_conflicts": sorted((label_block or {}).get("allowed_main_conflicts") or ()),
                "admitted_conflicts": [],
                "candidate_conflicts": [],
                "main_conflict": None,
                "main_conflict_match": None,
                "dominance_guard_review_required": [],
                "graph_nodes": 0,
                "graph_edges": 0,
                "evidence_polarity_errors": 0,
                "evidence_polarity_error_scope": "contract_integrity_only",
                "semantic_polarity_accuracy": None,
                "semantic_polarity_review_status": "PENDING_J3_HUMAN_REVIEW",
                "ticker_consistency": "not_available",
                "stance_source": STANCE_SOURCE_UNAVAILABLE,
                "artifact_hashes": {},
                "evaluation_authority": "provisional",
            }
        )
        return base

    source_run_id = selection["run_id"]
    try:
        replay_result = run_structure_replay(
            source_run_id,
            source_output_root=source_output_root,
            replay_output_root=replay_output_root,
            comparison=False,
        )
    except ReplaySourceIncompleteError:
        base["offline_reprocess_status"] = OFFLINE_REPROCESS_PATH_UNAVAILABLE
        return base

    if replay_result.status != "completed":
        base["offline_reprocess_status"] = OFFLINE_REPROCESS_PATH_UNAVAILABLE
        base["offline_reprocess_error"] = replay_result.error
        return base

    base["offline_reprocess_status"] = "completed"
    base["replay_run_id"] = replay_result.replay_run_id
    base["provider_calls"] = replay_result.llm_provider_calls
    base["tradingagents_calls"] = replay_result.tradingagents_calls
    base["artifact_hashes"] = {
        "source_raw_agent_outputs_sha256_before": replay_result.source_raw_sha256_before,
        "source_raw_agent_outputs_sha256_after": replay_result.source_raw_sha256_after,
        "source_raw_artifact_unchanged": replay_result.source_raw_sha256_before == replay_result.source_raw_sha256_after,
    }

    graph_payload = load_json_record_if_exists(
        replay_result.replay_run_id, "structure_graph.json", output_root=replay_output_root
    )
    # conflicts.json (not the replay-only legacy conflict_results.json) --
    # the same A2 canonical export finalize_completed_run_artifacts writes
    # for a live run, already on file_store's artifact allowlist.
    conflict_payload = load_json_record_if_exists(
        replay_result.replay_run_id, "conflicts.json", output_root=replay_output_root
    )
    alpha_matches_payload = load_json_record_if_exists(
        replay_result.replay_run_id, "alpha_matches.json", output_root=replay_output_root
    )
    structured_payload = load_json_record_if_exists(
        replay_result.replay_run_id, "structured_agent_outputs.json", output_root=replay_output_root
    )

    detected = detected_alpha_sets(graph_payload)
    alpha_cmp = alpha_comparison(label_block, detected)
    conflict_cmp = conflict_comparison(label_block, conflict_payload)
    dominance_flags = dominance_guard_flags(label_block, graph_payload, exposure_seed_for_ticker)
    polarity = evidence_polarity_errors(alpha_matches_payload, conflict_payload)

    metadata = load_json_record_if_exists(
        replay_result.replay_run_id, "metadata.json", output_root=replay_output_root
    )
    expected_ticker, expected_ticker_source = resolve_expected_ticker(
        metadata_ticker=metadata.get("ticker") if isinstance(metadata, dict) else None,
        raw_agent_outputs_ticker=structured_payload.get("ticker") if isinstance(structured_payload, dict) else None,
    )
    ticker_audit = audit_ticker_consistency(
        run_id=replay_result.replay_run_id,
        expected_ticker=expected_ticker or str(ticker).upper(),
        expected_ticker_source=expected_ticker_source or "unspecified",
        artifacts={
            "metadata": metadata,
            "structured_agent_outputs": structured_payload,
            "alpha_matches": alpha_matches_payload,
        },
    )

    graph_metrics = graph_payload.get("graph_metrics") or {}

    base.update(
        {
            **alpha_cmp,
            "detected_alphas": detected["detected_alphas"],
            "active_alphas": detected["active_alphas"],
            "dominant_alphas": detected["dominant_alphas"],
            "regime_level_alphas": detected["regime_level_alphas"],
            "candidate_alphas": detected["candidate_alphas"],
            "blocked_alphas": detected["blocked_alphas"],
            **conflict_cmp,
            "dominance_guard_review_required": dominance_flags,
            "graph_nodes": int(graph_metrics.get("node_count") or len(graph_payload.get("nodes") or ())),
            "graph_edges": int(graph_metrics.get("edge_count") or len(graph_payload.get("edges") or ())),
            **polarity,
            "ticker_consistency": ticker_audit.get("ticker_consistency"),
            "stance_source": stance_source(alpha_matches_payload),
            "evaluation_authority": "provisional",
        }
    )
    return base


__all__ = [
    "STANCE_SOURCE_LLM_SEMANTIC",
    "STANCE_SOURCE_DETERMINISTIC_BASELINE",
    "STANCE_SOURCE_MIXED",
    "STANCE_SOURCE_UNAVAILABLE",
    "OFFLINE_REPROCESS_PATH_UNAVAILABLE",
    "detected_alpha_sets",
    "alpha_comparison",
    "conflict_comparison",
    "dominance_guard_flags",
    "evidence_polarity_errors",
    "stance_source",
    "evaluate_ticker",
]
