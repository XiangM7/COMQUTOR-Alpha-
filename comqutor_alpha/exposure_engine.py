"""Exposure Engine v1 -- pure computational core (W4.4).

Implements exactly the Development Plan's Exposure formula::

    exposure = historical_mapping * 0.50
               + current_evidence * 0.30
               + agent_confidence * 0.20

The formula functions remain pure and deterministic: callers explicitly
supply historical mapping, current evidence, and agent confidence. The
productization helpers later in this module consume an already-validated
seed bundle plus canonical Evidence Fact summaries, attach additive runtime
records, and implement the separately gated qualification ceiling. They do
not read files, call Providers, or change the numeric Activation score.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from comqutor_alpha.alpha_library.alpha_loader import EXPECTED_ALPHA_IDS

EXPOSURE_FORMULA_VERSION = "week4.exposure_score.mvp_v1"

# APPROVED formula weights (Development Plan): historical_mapping 50%,
# current_evidence 30%, agent_confidence 20%. Not a tunable/config value --
# a frozen constant, exactly like W4.1's CONFLICT_FORMULA_VERSION weights.
EXPOSURE_WEIGHTS = {
    "historical_mapping": 0.50,
    "current_evidence": 0.30,
    "agent_confidence": 0.20,
}

ENTITY_EXPOSURE_ARTIFACT_SCHEMA_VERSION = "entity_alpha_exposure.run.v1"
DOMINANT_EXPOSURE_THRESHOLD = 0.30
REGIME_EXPOSURE_THRESHOLD = 0.60
OVERRIDE_MIN_TICKER_FACTS = 4
OVERRIDE_MIN_DISTINCT_AGENTS = 3
OVERRIDE_MIN_LOCAL_EDGES = 1
OVERRIDE_MIN_MEAN_MATCH_SCORE = 0.80

EXPOSURE_BELOW_DOMINANT_THRESHOLD = "EXPOSURE_BELOW_DOMINANT_THRESHOLD"
EXPOSURE_BELOW_REGIME_THRESHOLD = "EXPOSURE_BELOW_REGIME_THRESHOLD"
EXPOSURE_SEED_MISSING = "EXPOSURE_SEED_MISSING"
EXPOSURE_QUALIFICATION_APPLIED = "EXPOSURE_QUALIFICATION_APPLIED"


class ExposureInputError(Exception):
    """Safe input-contract violation: carries a stable reason code only.
    Never carries the raw offending value or payload."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _require_unit_interval_number(value: Any, reason_code: str) -> float:
    """Finite number in [0.0, 1.0]. ``bool``/``str``/``None``/out-of-range
    are all rejected outright -- never coerced, never clamped. A caller
    that passes an out-of-range or wrongly-typed value has a bug; silently
    "fixing" it would hide that bug instead of surfacing it."""
    if isinstance(value, bool):
        raise ExposureInputError(reason_code)
    if not isinstance(value, (int, float)):
        raise ExposureInputError(reason_code)
    number = float(value)
    if not math.isfinite(number):
        raise ExposureInputError(reason_code)
    if not (0.0 <= number <= 1.0):
        raise ExposureInputError(reason_code)
    return number


def calculate_exposure(
    *,
    historical_mapping,
    current_evidence,
    agent_confidence,
) -> dict[str, Any]:
    """Compute one Alpha's exposure score for one entity/ticker.

    Pure function of its three inputs; raises :class:`ExposureInputError`
    (``INVALID_EXPOSURE_INPUT``) for any input that is not a finite number
    in ``[0.0, 1.0]``. ``exposure_score`` is exactly the sum of the three
    ``components[*]["contribution"]`` values -- no additional conflict
    penalty, ranking bonus, or ticker-specific correction is ever applied.
    """
    historical = _require_unit_interval_number(historical_mapping, "INVALID_EXPOSURE_INPUT")
    evidence = _require_unit_interval_number(current_evidence, "INVALID_EXPOSURE_INPUT")
    confidence = _require_unit_interval_number(agent_confidence, "INVALID_EXPOSURE_INPUT")

    historical_contribution = historical * EXPOSURE_WEIGHTS["historical_mapping"]
    evidence_contribution = evidence * EXPOSURE_WEIGHTS["current_evidence"]
    confidence_contribution = confidence * EXPOSURE_WEIGHTS["agent_confidence"]

    exposure_score = historical_contribution + evidence_contribution + confidence_contribution

    return {
        "formula_version": EXPOSURE_FORMULA_VERSION,
        "exposure_score": exposure_score,
        "components": {
            "historical_mapping": {
                "raw": historical,
                "weight": EXPOSURE_WEIGHTS["historical_mapping"],
                "contribution": historical_contribution,
            },
            "current_evidence": {
                "raw": evidence,
                "weight": EXPOSURE_WEIGHTS["current_evidence"],
                "contribution": evidence_contribution,
            },
            "agent_confidence": {
                "raw": confidence,
                "weight": EXPOSURE_WEIGHTS["agent_confidence"],
                "contribution": confidence_contribution,
            },
        },
    }


def _require_ticker(ticker: Any) -> str:
    if not isinstance(ticker, str) or not ticker.strip():
        raise ExposureInputError("INVALID_TICKER")
    return ticker


def _require_alpha_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ExposureInputError("INVALID_EXPOSURE_INPUT")
    for key in value:
        if not isinstance(key, str) or not key.strip():
            raise ExposureInputError("INVALID_EXPOSURE_INPUT")
    return value


def compute_entity_alpha_exposures(
    *,
    ticker,
    historical_mapping,
    current_evidence,
    agent_confidence,
    taxonomy=None,
) -> dict[str, Any]:
    """Compute exposure scores for every Alpha declared by
    ``historical_mapping`` for one ticker.

    ``historical_mapping`` decides which Alphas this ticker outputs at all;
    ``current_evidence`` and ``agent_confidence`` must declare a value for
    exactly that same ``alpha_id`` set -- no missing component is ever
    defaulted to 0, and no Alpha absent from ``historical_mapping`` is ever
    auto-added just because it happens to appear in one of the other two
    mappings. Every ``alpha_id`` must belong to the valid Alpha ID universe.

    ``taxonomy=None`` (the default) validates against ``EXPECTED_ALPHA_IDS``
    -- the static MVP-10 identifier constant, imported without ever calling
    ``load_alpha_taxonomy()`` or otherwise touching
    ``alpha_taxonomy_v1.yaml``. An explicit ``taxonomy`` mapping is a
    testing seam only, never a hardcoded substitute weight table; it must
    be a ``Mapping`` with non-empty string keys, validated the same way
    ``historical_mapping``/``current_evidence``/``agent_confidence`` are.

    Pure function: no filesystem, database, network, or environment access
    of any kind -- not even to read the frozen Alpha taxonomy YAML. Does
    not read a formal exposure seed. Does not mutate any input mapping.
    Output ``exposures`` is always sorted by ``alpha_id``, so input
    iteration order never affects the result.
    """
    safe_ticker = _require_ticker(ticker)
    historical = _require_alpha_mapping(historical_mapping)
    evidence = _require_alpha_mapping(current_evidence)
    confidence = _require_alpha_mapping(agent_confidence)

    if taxonomy is None:
        valid_alpha_ids = set(EXPECTED_ALPHA_IDS)
    else:
        valid_alpha_ids = set(_require_alpha_mapping(taxonomy))

    alpha_ids = set(historical)
    if set(evidence) != alpha_ids or set(confidence) != alpha_ids:
        raise ExposureInputError("EXPOSURE_INPUT_SET_MISMATCH")

    if alpha_ids - valid_alpha_ids:
        raise ExposureInputError("UNKNOWN_ALPHA_ID")

    exposures = []
    for alpha_id in sorted(alpha_ids):
        result = calculate_exposure(
            historical_mapping=historical[alpha_id],
            current_evidence=evidence[alpha_id],
            agent_confidence=confidence[alpha_id],
        )
        exposures.append(
            {
                "alpha_id": alpha_id,
                "exposure_score": result["exposure_score"],
                "components": result["components"],
            }
        )

    return {
        "formula_version": EXPOSURE_FORMULA_VERSION,
        "ticker": safe_ticker,
        "exposures": exposures,
    }


def calculate_runtime_exposure_inputs(evidence_summary: Mapping[str, Any] | None) -> dict[str, Any]:
    """Calculate per-run inputs from canonical unique Evidence Facts.

    ``evidence_summary`` is produced from Activation v2's already-grouped
    Evidence Fact Index. This function never groups raw claims and therefore
    cannot create a second claim-deduplication implementation.
    """
    summary = evidence_summary if isinstance(evidence_summary, Mapping) else {}
    raw_facts = summary.get("facts")
    facts = raw_facts if isinstance(raw_facts, list) else []
    ticker_facts: list[Mapping[str, Any]] = []
    agent_scores: dict[str, float] = {}
    for fact in facts:
        if not isinstance(fact, Mapping):
            continue
        if fact.get("ticker_specific") is True:
            score = _require_unit_interval_number(
                fact.get("representative_match_score"), "INVALID_EXPOSURE_INPUT"
            )
            ticker_facts.append({**fact, "representative_match_score": score})
        representatives = fact.get("agent_representatives")
        if not isinstance(representatives, list):
            continue
        for representative in representatives:
            if not isinstance(representative, Mapping):
                continue
            agent = str(representative.get("agent") or "").strip()
            if not agent:
                continue
            confidence = _require_unit_interval_number(
                representative.get("confidence"), "INVALID_EXPOSURE_INPUT"
            )
            agent_scores[agent] = max(agent_scores.get(agent, 0.0), confidence)

    ticker_specific_fact_count = len(ticker_facts)
    mean_match_score = (
        sum(float(fact["representative_match_score"]) for fact in ticker_facts)
        / ticker_specific_fact_count
        if ticker_specific_fact_count
        else 0.0
    )
    ticker_specific_fact_ratio = min(ticker_specific_fact_count / 4.0, 1.0)
    current_evidence = min(1.0, max(0.0, ticker_specific_fact_ratio * mean_match_score))
    agent_confidence = (
        sum(agent_scores.values()) / len(agent_scores) if agent_scores else 0.0
    )
    unique_count = summary.get("unique_evidence_fact_count", len(facts))
    local_edge_count = summary.get("qualifying_local_edge_count", 0)
    if isinstance(unique_count, bool) or not isinstance(unique_count, int) or unique_count < 0:
        raise ExposureInputError("INVALID_EXPOSURE_INPUT")
    if isinstance(local_edge_count, bool) or not isinstance(local_edge_count, int) or local_edge_count < 0:
        raise ExposureInputError("INVALID_EXPOSURE_INPUT")
    return {
        "current_evidence": current_evidence,
        "agent_confidence": min(1.0, max(0.0, agent_confidence)),
        "unique_evidence_fact_count": unique_count,
        "ticker_specific_fact_count": ticker_specific_fact_count,
        "distinct_supporting_agent_count": len(agent_scores),
        "qualifying_local_edge_count": local_edge_count,
        "mean_representative_match_score": mean_match_score,
        "ticker_specific_fact_ratio": ticker_specific_fact_ratio,
        "representative_fact_group_ids": [
            str(fact.get("evidence_fact_group_id") or "") for fact in ticker_facts
        ],
    }


def _public_entity_exposure(record: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "historical_mapping",
        "current_evidence",
        "agent_confidence",
        "final_exposure",
        "seed_version",
        "seed_effective_date",
        "seed_approval_status",
        "mode",
        "exposure_status",
        "would_block_dominant",
        "would_block_regime_level",
        "override_candidate",
        "qualification_effect_applied",
        "unique_evidence_fact_count",
        "ticker_specific_fact_count",
        "distinct_supporting_agent_count",
        "reason_codes",
    )
    return {field: deepcopy(record.get(field)) for field in fields}


_LEVEL_RANK = {"inactive": 0, "watch": 1, "active": 2, "dominant": 3, "regime_level": 4}


def _cap_status(status: str, ceiling: str) -> str:
    if status not in _LEVEL_RANK or ceiling not in _LEVEL_RANK:
        return status
    return ceiling if _LEVEL_RANK[status] > _LEVEL_RANK[ceiling] else status


def compute_run_entity_alpha_exposures(
    *,
    run_id: str,
    ticker: str,
    activation_payload: Mapping[str, Any],
    seed_bundle: Any,
    mode_decision: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Attach Entity Exposure and return (activation, run artifact).

    Shadow mode is observational: score/status/dominant membership are
    byte-for-byte unchanged. Enforced mode changes only the final status
    qualification ceiling after the signed manifest gate has allowed it;
    ``activation_score`` is never modified.
    """
    activation = deepcopy(dict(activation_payload))
    entries = activation.get("alphas")
    if not isinstance(entries, list):
        raise ExposureInputError("INVALID_EXPOSURE_INPUT")

    manifest = seed_bundle.manifest
    effective_mode = mode_decision.effective_mode
    before_scores = {str(entry.get("alpha_id")): entry.get("activation_score") for entry in entries}
    before_levels = {str(entry.get("alpha_id")): entry.get("status") for entry in entries}
    records: list[dict[str, Any]] = []

    for entry in sorted(entries, key=lambda item: str(item.get("alpha_id") or "")):
        alpha_id = str(entry.get("alpha_id") or "")
        evidence_summary = entry.pop("_exposure_evidence", None)
        if effective_mode == "off":
            entry.pop("entity_exposure", None)
            continue
        runtime = calculate_runtime_exposure_inputs(evidence_summary)
        historical = seed_bundle.historical_mapping(ticker, alpha_id)
        reasons = list(mode_decision.reason_codes)
        if historical is None:
            final_exposure = None
            exposure_status = "missing_seed"
            reasons.append("SEED_ENTRY_MISSING")
        else:
            final_exposure = calculate_exposure(
                historical_mapping=historical,
                current_evidence=runtime["current_evidence"],
                agent_confidence=runtime["agent_confidence"],
            )["exposure_score"]
            exposure_status = "computed"

        would_block_dominant = (
            final_exposure is not None and final_exposure < DOMINANT_EXPOSURE_THRESHOLD
        )
        would_block_regime = (
            final_exposure is not None and final_exposure < REGIME_EXPOSURE_THRESHOLD
        )
        override_candidate = (
            runtime["ticker_specific_fact_count"] >= OVERRIDE_MIN_TICKER_FACTS
            and runtime["distinct_supporting_agent_count"] >= OVERRIDE_MIN_DISTINCT_AGENTS
            and runtime["qualifying_local_edge_count"] >= OVERRIDE_MIN_LOCAL_EDGES
            and runtime["mean_representative_match_score"] >= OVERRIDE_MIN_MEAN_MATCH_SCORE
        )
        qualification_applied = False

        if effective_mode == "enforced":
            if final_exposure is None:
                entry["status"] = _cap_status(str(entry.get("status") or ""), "active")
                reasons.extend([EXPOSURE_SEED_MISSING, EXPOSURE_QUALIFICATION_APPLIED])
                qualification_applied = True
            elif final_exposure < DOMINANT_EXPOSURE_THRESHOLD:
                entry["status"] = _cap_status(str(entry.get("status") or ""), "active")
                reasons.extend(
                    [
                        EXPOSURE_BELOW_DOMINANT_THRESHOLD,
                        EXPOSURE_BELOW_REGIME_THRESHOLD,
                        EXPOSURE_QUALIFICATION_APPLIED,
                    ]
                )
                qualification_applied = True
            elif final_exposure < REGIME_EXPOSURE_THRESHOLD:
                entry["status"] = _cap_status(str(entry.get("status") or ""), "dominant")
                reasons.extend(
                    [EXPOSURE_BELOW_REGIME_THRESHOLD, EXPOSURE_QUALIFICATION_APPLIED]
                )
                qualification_applied = True

        record = {
            "run_id": run_id,
            "ticker": ticker,
            "alpha_id": alpha_id,
            "seed_version": manifest.seed_version,
            "seed_effective_date": manifest.effective_date,
            "seed_approval_status": manifest.approval_status,
            "historical_mapping": historical,
            "current_evidence": runtime["current_evidence"],
            "agent_confidence": runtime["agent_confidence"],
            "final_exposure": final_exposure,
            "unique_evidence_fact_count": runtime["unique_evidence_fact_count"],
            "ticker_specific_fact_count": runtime["ticker_specific_fact_count"],
            "distinct_supporting_agent_count": runtime["distinct_supporting_agent_count"],
            "mode": effective_mode,
            "exposure_status": exposure_status,
            "would_block_dominant": would_block_dominant,
            "would_block_regime_level": would_block_regime,
            "override_candidate": override_candidate,
            "qualification_effect_applied": qualification_applied,
            "reason_codes": sorted(set(reasons)),
            "provenance": {
                "formula_version": EXPOSURE_FORMULA_VERSION,
                "evidence_fact_index_version": (
                    evidence_summary.get("evidence_fact_index_version")
                    if isinstance(evidence_summary, Mapping)
                    else None
                ),
                "representative_fact_group_ids": runtime["representative_fact_group_ids"],
                "mean_representative_match_score": runtime[
                    "mean_representative_match_score"
                ],
                "ticker_specific_fact_ratio": runtime["ticker_specific_fact_ratio"],
                "qualifying_local_edge_count": runtime["qualifying_local_edge_count"],
            },
        }
        entry["entity_exposure"] = _public_entity_exposure(record)
        records.append(record)

    if effective_mode == "enforced":
        by_alpha = {str(entry.get("alpha_id")): entry for entry in entries}
        dominant = []
        for original in activation.get("dominant_alphas") or []:
            alpha_id = str(original.get("alpha_id") or "")
            entry = by_alpha.get(alpha_id)
            if entry and entry.get("status") in {"dominant", "regime_level"}:
                updated = deepcopy(original)
                updated["status"] = entry["status"]
                dominant.append(updated)
        activation["dominant_alphas"] = dominant

    after_scores = {str(entry.get("alpha_id")): entry.get("activation_score") for entry in entries}
    after_levels = {str(entry.get("alpha_id")): entry.get("status") for entry in entries}
    artifact = {
        "schema_version": ENTITY_EXPOSURE_ARTIFACT_SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "requested_mode": mode_decision.requested_mode,
        "mode": effective_mode,
        "mode_reason_codes": list(mode_decision.reason_codes),
        "seed_manifest": manifest.to_dict(),
        "records": records,
        "activation_invariants": {
            "scores_unchanged": before_scores == after_scores,
            "levels_unchanged": before_levels == after_levels,
            "shadow_mode_did_not_alter_activation": (
                effective_mode != "shadow" or before_levels == after_levels
            ),
        },
    }
    return activation, artifact


__all__ = [
    "EXPOSURE_FORMULA_VERSION",
    "EXPOSURE_WEIGHTS",
    "ENTITY_EXPOSURE_ARTIFACT_SCHEMA_VERSION",
    "ExposureInputError",
    "calculate_exposure",
    "calculate_runtime_exposure_inputs",
    "compute_entity_alpha_exposures",
    "compute_run_entity_alpha_exposures",
]
