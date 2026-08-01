"""Pure validation, whitelisting, and reconstruction for Week 4 persistence.

2026-07-14 W4.2 Correctness Patch: closes two gaps in the initial
implementation (see docs/week4_persistence_report.md's "W4.2 Correctness
Patch" section for the full history) --

1. ``build_activation_rows``/``build_conflict_rows`` were each internally
   self-consistent but were never cross-checked against each other: nothing
   stopped an admitted conflict row's embedded activation snapshot
   (``components.activation_a/b``, ``bull_structure``/``bear_structure``)
   from silently disagreeing with the activation rows built from a
   *different* activation_payload in the same call. ``build_week4_rows``
   now calls ``_validate_week4_snapshot`` after building both row sets and
   before returning either.
2. The activation component whitelist validated field *names* against one
   shared set across all five components, without validating each field's
   *type*/range per component. It is now a typed, per-component schema.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, NoReturn

from comqutor_alpha.conflict_engine.conflict_schema import (
    CONFLICT_FORMULA_VERSION,
    CONFLICT_SCHEMA_VERSION,
)
from comqutor_alpha.graph_engine.activation_scorer_v2 import (
    ACTIVATION_V2_FORMULA_VERSION,
)
from comqutor_alpha.graph_engine.graph_schema import ACTIVATION_FORMULA_VERSION

# Activation payloads accepted for persistence: the frozen v1 formula and
# the versioned Activation v2 formula. The row's formula_version column
# records whichever version the payload actually declared.
SUPPORTED_ACTIVATION_FORMULA_VERSIONS = frozenset(
    {ACTIVATION_FORMULA_VERSION, ACTIVATION_V2_FORMULA_VERSION}
)

WEEK4_ACTIVATION_PAYLOAD_INVALID = "WEEK4_ACTIVATION_PAYLOAD_INVALID"
WEEK4_CONFLICT_PAYLOAD_INVALID = "WEEK4_CONFLICT_PAYLOAD_INVALID"
WEEK4_RUN_ID_MISMATCH = "WEEK4_RUN_ID_MISMATCH"
WEEK4_TICKER_MISMATCH = "WEEK4_TICKER_MISMATCH"
WEEK4_CONFLICT_DATA_INCONSISTENT = "WEEK4_CONFLICT_DATA_INCONSISTENT"
DB_DATA_CORRUPTED = "DB_DATA_CORRUPTED"

_OUTCOMES = frozenset({"admitted", "suppressed", "rejected"})
_CONFLICT_LEVELS = frozenset({"low", "medium", "medium_high", "high"})
_ACTIVATION_FIELDS = (
    "alpha_id",
    "alpha_name",
    "activation_score",
    "status",
    "direction",
    "components",
    "evidence_count",
    "distinct_supporting_agents",
    "claim_ids",
    "evidence",
    "reason_codes",
)
_CANDIDATE_FIELDS = ("alpha_a", "alpha_b", "outcome", "reason_codes", "evidence_audit")
_CONFLICT_FIELDS = (
    "conflict_id",
    "alpha_a",
    "alpha_b",
    "bull_alpha_id",
    "bear_alpha_id",
    "bull_structure",
    "bear_structure",
    "components",
    "alpha_a_strength",
    "alpha_b_strength",
    "evidence_strength",
    "conflict_score",
    "conflict_level",
    "reason_codes",
    "explanation",
)
_STRUCTURE_FIELDS = (
    "alpha_id",
    "alpha_name",
    "activation_score",
    "status",
    "direction",
    "claim_ids",
    "source_agent_output_ids",
    "agents",
    "evidence",
    "match_scores",
)
_COMPONENT_FIELDS = (
    "activation_a",
    "activation_b",
    "minimum_activation",
    "contradiction_weight",
    "alpha_a_evidence_strength",
    "alpha_b_evidence_strength",
    "evidence_strength",
)


class Week4PersistenceDataError(Exception):
    """Internal safe validation error translated by the public repository."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _fail(reason_code: str) -> NoReturn:
    raise Week4PersistenceDataError(reason_code)


def _text(value: Any, reason_code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(reason_code)
    return value.strip()


def _number(value: Any, minimum: float, maximum: float, reason_code: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(reason_code)
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        _fail(reason_code)
    return number


def _positive_number(value: Any, reason_code: str) -> float:
    """Finite, strictly > 0, no upper bound (e.g. evidence-strength saturation)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(reason_code)
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        _fail(reason_code)
    return number


def _nonnegative_number(value: Any, reason_code: str) -> float:
    """Finite, >= 0, no upper bound (e.g. a multi-claim weighted evidence sum)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(reason_code)
    number = float(value)
    if not math.isfinite(number) or number < 0:
        _fail(reason_code)
    return number


def _integer(value: Any, reason_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(reason_code)
    return value


def _positive_integer(value: Any, reason_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail(reason_code)
    return value


def _optional_integer(value: Any, reason_code: str) -> int | None:
    if value is None:
        return None
    return _integer(value, reason_code)


def _bool(value: Any, reason_code: str) -> bool:
    if not isinstance(value, bool):
        _fail(reason_code)
    return value


def _json_copy(value: Any, reason_code: str) -> Any:
    try:
        serialized = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        return json.loads(serialized)
    except (TypeError, ValueError, OverflowError):
        _fail(reason_code)


def _string_list(value: Any, reason_code: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        _fail(reason_code)
    return list(value)


def _agents_list(value: Any, reason_code: str) -> list[str]:
    """agent_agreement.agents: list[non-empty str], no nested dict/list,
    normalized to a sorted/deduped form -- never dependent on raw input
    order (2026-07-14 Correctness Patch, section 十)."""
    if not isinstance(value, list):
        _fail(reason_code)
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            _fail(reason_code)
        cleaned.append(item.strip())
    return sorted(set(cleaned))


# ---------------------------------------------------------------------------
# Typed, per-component activation whitelist (2026-07-14 Correctness Patch,
# sections 七-十四). Each of the five official components gets its own
# schema -- allowed field *names* AND *types/ranges* -- rather than one
# shared field-name set applied uniformly with no type enforcement. Unknown
# components are dropped silently (not an error); unknown fields within a
# known component are dropped silently; known fields with the wrong type
# (nested dict/list where a scalar is expected, NaN/Infinity, a bool where
# an int is expected, a string "true" where a bool is expected, ...) fail
# the whole persist attempt with WEEK4_ACTIVATION_PAYLOAD_INVALID.
# ---------------------------------------------------------------------------


def _whitelist_common_component_fields(component: Mapping[str, Any], reason: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if "raw" in component:
        result["raw"] = _number(component["raw"], 0.0, 100.0, reason)
    if "weight" in component:
        result["weight"] = _number(component["weight"], 0.0, 1.0, reason)
    if "contribution" in component:
        result["contribution"] = _number(component["contribution"], 0.0, 100.0, reason)
    return result


def _whitelist_matched_evidence(component: Mapping[str, Any], reason: str) -> dict[str, Any]:
    result = _whitelist_common_component_fields(component, reason)
    if "unique_committed_claims" in component:
        result["unique_committed_claims"] = _integer(component["unique_committed_claims"], reason)
    if "unique_ambiguous_claims" in component:
        result["unique_ambiguous_claims"] = _integer(component["unique_ambiguous_claims"], reason)
    if "weighted_evidence_sum" in component:
        # Not bounded to 1: a multi-claim weighted sum can legitimately
        # exceed 1 before the formula's own saturation division.
        result["weighted_evidence_sum"] = _nonnegative_number(component["weighted_evidence_sum"], reason)
    if "saturation" in component:
        result["saturation"] = _positive_number(component["saturation"], reason)
    if "ambiguous_weight" in component:
        result["ambiguous_weight"] = _number(component["ambiguous_weight"], 0.0, 1.0, reason)
    return result


def _whitelist_agent_agreement(component: Mapping[str, Any], reason: str) -> dict[str, Any]:
    result = _whitelist_common_component_fields(component, reason)
    if "distinct_agents" in component:
        result["distinct_agents"] = _integer(component["distinct_agents"], reason)
    if "denominator" in component:
        result["denominator"] = _integer(component["denominator"], reason)
    if "denominator_source" in component:
        result["denominator_source"] = _text(component["denominator_source"], reason)
    if "agents" in component:
        result["agents"] = _agents_list(component["agents"], reason)
    return result


def _whitelist_graph_coherence(component: Mapping[str, Any], reason: str) -> dict[str, Any]:
    result = _whitelist_common_component_fields(component, reason)
    if "scope" in component:
        result["scope"] = _text(component["scope"], reason)
    if "evidence_gated" in component:
        result["evidence_gated"] = _bool(component["evidence_gated"], reason)
    return result


def _whitelist_recency(component: Mapping[str, Any], reason: str) -> dict[str, Any]:
    result = _whitelist_common_component_fields(component, reason)
    if "evidence_gated" in component:
        result["evidence_gated"] = _bool(component["evidence_gated"], reason)
    if "age_days" in component:
        result["age_days"] = _optional_integer(component["age_days"], reason)
    if "fallback" in component:
        result["fallback"] = _bool(component["fallback"], reason)
    if "reason" in component:
        result["reason"] = _text(component["reason"], reason)
    if "decay_window_days" in component:
        result["decay_window_days"] = _positive_integer(component["decay_window_days"], reason)
    return result


def _whitelist_direction_strength(component: Mapping[str, Any], reason: str) -> dict[str, Any]:
    result = _whitelist_common_component_fields(component, reason)
    if "qualifying_claim_count" in component:
        result["qualifying_claim_count"] = _integer(component["qualifying_claim_count"], reason)
    if "average_signed_strength" in component:
        result["average_signed_strength"] = _number(component["average_signed_strength"], -1.0, 1.0, reason)
    if "mixed_direction_evidence" in component:
        result["mixed_direction_evidence"] = _bool(component["mixed_direction_evidence"], reason)
    return result


# --- Activation v2 component whitelisters (additive; same typed style) ---


def _whitelist_evidence_quality(component: Mapping[str, Any], reason: str) -> dict[str, Any]:
    result = _whitelist_common_component_fields(component, reason)
    if "unique_semantic_groups" in component:
        result["unique_semantic_groups"] = _integer(component["unique_semantic_groups"], reason)
    if "unique_contribution_sum" in component:
        result["unique_contribution_sum"] = _nonnegative_number(
            component["unique_contribution_sum"], reason
        )
    if "saturation" in component:
        result["saturation"] = _positive_number(component["saturation"], reason)
    return result


def _whitelist_agent_independence(component: Mapping[str, Any], reason: str) -> dict[str, Any]:
    result = _whitelist_common_component_fields(component, reason)
    if "distinct_agents" in component:
        result["distinct_agents"] = _integer(component["distinct_agents"], reason)
    if "agents" in component:
        result["agents"] = _agents_list(component["agents"], reason)
    if "agent_coverage" in component:
        result["agent_coverage"] = _number(component["agent_coverage"], 0.0, 100.0, reason)
    if "cross_agent_confirmed_groups" in component:
        result["cross_agent_confirmed_groups"] = _integer(
            component["cross_agent_confirmed_groups"], reason
        )
    if "cross_agent_confirmation" in component:
        result["cross_agent_confirmation"] = _number(
            component["cross_agent_confirmation"], 0.0, 100.0, reason
        )
    if "coverage_denominator" in component:
        result["coverage_denominator"] = _positive_integer(component["coverage_denominator"], reason)
    if "confirmation_denominator" in component:
        result["confirmation_denominator"] = _positive_integer(
            component["confirmation_denominator"], reason
        )
    return result


def _whitelist_local_structure_support(component: Mapping[str, Any], reason: str) -> dict[str, Any]:
    result = _whitelist_common_component_fields(component, reason)
    for field in (
        "local_edge_count",
        "asserted_local_edge_count",
        "conditional_local_edge_count",
        # Structure Integrity Repair Sprint, Track 1 (additive): "how many
        # graph edges touch this alpha" vs "how many the frozen formula
        # actually counted" -- two honest, separate numbers.
        "incident_graph_edge_count",
        "qualifying_local_edge_count",
        "nonqualifying_local_edge_count",
    ):
        if field in component:
            result[field] = _integer(component[field], reason)
    for field in ("local_edge_ids", "local_claim_ids", "local_edge_exclusion_reasons"):
        if field in component:
            result[field] = _string_list(component[field], reason)
    if "unique_edge_contribution_sum" in component:
        result["unique_edge_contribution_sum"] = _nonnegative_number(
            component["unique_edge_contribution_sum"], reason
        )
    if "saturation" in component:
        result["saturation"] = _positive_number(component["saturation"], reason)
    return result


def _whitelist_ticker_specificity(component: Mapping[str, Any], reason: str) -> dict[str, Any]:
    result = _whitelist_common_component_fields(component, reason)
    if "ticker_specific_evidence_count" in component:
        result["ticker_specific_evidence_count"] = _integer(
            component["ticker_specific_evidence_count"], reason
        )
    if "total_unique_evidence_count" in component:
        result["total_unique_evidence_count"] = _integer(
            component["total_unique_evidence_count"], reason
        )
    return result


def _whitelist_direction_consistency(component: Mapping[str, Any], reason: str) -> dict[str, Any]:
    result = _whitelist_common_component_fields(component, reason)
    if "qualifying_group_count" in component:
        result["qualifying_group_count"] = _integer(component["qualifying_group_count"], reason)
    if "weighted_signed_average" in component:
        result["weighted_signed_average"] = _number(
            component["weighted_signed_average"], -1.0, 1.0, reason
        )
    return result


_COMPONENT_WHITELISTERS = {
    "matched_evidence": _whitelist_matched_evidence,
    "agent_agreement": _whitelist_agent_agreement,
    "graph_coherence": _whitelist_graph_coherence,
    "recency": _whitelist_recency,
    "direction_strength": _whitelist_direction_strength,
    # Activation v2 components.
    "evidence_quality": _whitelist_evidence_quality,
    "agent_independence": _whitelist_agent_independence,
    "local_structure_support": _whitelist_local_structure_support,
    "ticker_specificity": _whitelist_ticker_specificity,
    "direction_consistency": _whitelist_direction_consistency,
}


# Component names are version-specific, not a union: an entry's OWN
# formula_version gates which component names it may contain, so a v1 entry
# can never smuggle a v2-only component (or vice versa) even though both
# whitelisters happen to be registered in the same dispatch table below.
# "recency" is the one component whose shape is identical in both formulas
# (Activation v2 reuses v1's deterministic recency logic verbatim), so it is
# the only name allowed under either version.
_V1_ONLY_COMPONENT_NAMES = frozenset(
    {"matched_evidence", "agent_agreement", "graph_coherence", "direction_strength"}
)
_V2_ONLY_COMPONENT_NAMES = frozenset(
    {
        "evidence_quality",
        "agent_independence",
        "local_structure_support",
        "ticker_specificity",
        "direction_consistency",
    }
)
_SHARED_COMPONENT_NAMES = frozenset({"recency"})
_V1_ALLOWED_COMPONENT_NAMES = _V1_ONLY_COMPONENT_NAMES | _SHARED_COMPONENT_NAMES
_V2_ALLOWED_COMPONENT_NAMES = _V2_ONLY_COMPONENT_NAMES | _SHARED_COMPONENT_NAMES

# Per-alpha additive fields that only ever appear on an Activation v2 entry.
# Present on a v1 (or formula_version-absent legacy) entry, they are
# rejected outright -- a v1 entry smuggling v2-shaped fields is exactly the
# "one union schema accepts either version's fields" defect this whitelist
# must not have.
_V2_ONLY_ACTIVATION_FIELDS = frozenset(
    {
        "uncapped_score",
        "eligible_cap",
        "cap_was_binding",
        "cap_reason_codes",
        "binding_cap_reason_codes",
        "unique_evidence_count",
        "ticker_specific_evidence_count",
        "local_edge_count",
        "regime_gate_passed",
        "regime_gate_failures",
        "evidence_integrity_warnings",
        # Evidence Integrity Completion Sprint, Track C: additive raw/
        # unique-fact/agent/overlap transparency fields.
        "raw_supporting_claim_count",
        "unique_evidence_fact_count",
        "distinct_supporting_agent_count",
        "evidence_overlap_ratio",
        "high_overlap_warning",
    }
)


def _whitelist_activation_components(value: Any, allowed_names: frozenset[str]) -> dict[str, Any]:
    reason = WEEK4_ACTIVATION_PAYLOAD_INVALID
    if not isinstance(value, Mapping):
        _fail(reason)
    if not set(value) <= allowed_names:
        _fail(reason)
    components: dict[str, Any] = {}
    for name in sorted(allowed_names):
        if name not in value:
            continue
        component = value[name]
        if not isinstance(component, Mapping):
            _fail(reason)
        whitelister = _COMPONENT_WHITELISTERS[name]
        components[name] = _json_copy(whitelister(component, reason), reason)
    return components


def _whitelist_activation(entry: Mapping[str, Any]) -> dict[str, Any]:
    reason = WEEK4_ACTIVATION_PAYLOAD_INVALID
    activation = {key: entry[key] for key in _ACTIVATION_FIELDS if key in entry}
    activation["alpha_id"] = _text(entry.get("alpha_id"), reason)
    activation["alpha_name"] = _text(entry.get("alpha_name"), reason)
    activation["activation_score"] = _number(entry.get("activation_score"), 0.0, 100.0, reason)
    activation["status"] = _text(entry.get("status"), reason)
    activation["direction"] = _text(entry.get("direction"), reason)

    # formula_version gates everything else on this entry: absent means a
    # legacy v1 row (no v2 fields ever existed for those); present must be
    # one of the two supported formulas, never an arbitrary string.
    formula_version = entry.get("formula_version")
    if formula_version is None:
        is_v2 = False
    elif formula_version in SUPPORTED_ACTIVATION_FORMULA_VERSIONS:
        is_v2 = formula_version == ACTIVATION_V2_FORMULA_VERSION
    else:
        _fail(reason)

    allowed_component_names = _V2_ALLOWED_COMPONENT_NAMES if is_v2 else _V1_ALLOWED_COMPONENT_NAMES
    activation["components"] = _whitelist_activation_components(
        entry.get("components"), allowed_component_names
    )
    activation["evidence_count"] = _integer(entry.get("evidence_count"), reason)
    activation["distinct_supporting_agents"] = _integer(
        entry.get("distinct_supporting_agents"), reason
    )
    activation["claim_ids"] = _string_list(entry.get("claim_ids"), reason)
    activation["evidence"] = _string_list(entry.get("evidence"), reason)
    activation["reason_codes"] = _string_list(entry.get("reason_codes"), reason)

    if not is_v2:
        # A v1 (or formula_version-absent) entry must not carry any v2-only
        # additive field -- reject rather than silently drop.
        if any(field in entry for field in _V2_ONLY_ACTIVATION_FIELDS):
            _fail(reason)
        return _json_copy(activation, reason)

    activation["formula_version"] = _text(entry["formula_version"], reason)
    if "uncapped_score" in entry:
        activation["uncapped_score"] = _number(entry["uncapped_score"], 0.0, 100.0, reason)
    if "eligible_cap" in entry:
        eligible_cap = entry["eligible_cap"]
        activation["eligible_cap"] = (
            None if eligible_cap is None else _number(eligible_cap, 0.0, 100.0, reason)
        )
    if "cap_was_binding" in entry:
        activation["cap_was_binding"] = _bool(entry["cap_was_binding"], reason)
    for field in (
        "cap_reason_codes",
        "binding_cap_reason_codes",
        "regime_gate_failures",
        "evidence_integrity_warnings",
    ):
        if field in entry:
            activation[field] = _string_list(entry[field], reason)
    for field in (
        "unique_evidence_count",
        "ticker_specific_evidence_count",
        "local_edge_count",
        "raw_supporting_claim_count",
        "unique_evidence_fact_count",
        "distinct_supporting_agent_count",
    ):
        if field in entry:
            activation[field] = _integer(entry[field], reason)
    if "evidence_overlap_ratio" in entry:
        activation["evidence_overlap_ratio"] = _number(entry["evidence_overlap_ratio"], 0.0, 1.0, reason)
    if "high_overlap_warning" in entry:
        activation["high_overlap_warning"] = _bool(entry["high_overlap_warning"], reason)
    if "regime_gate_passed" in entry:
        activation["regime_gate_passed"] = _bool(entry["regime_gate_passed"], reason)
    return _json_copy(activation, reason)


def build_activation_rows(
    run_id: str,
    ticker: str,
    activation_payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    reason = WEEK4_ACTIVATION_PAYLOAD_INVALID
    run_id = _text(run_id, reason)
    ticker = _text(ticker, reason)
    if not isinstance(activation_payload, Mapping):
        _fail(reason)
    formula_version = activation_payload.get("formula_version")
    if formula_version not in SUPPORTED_ACTIVATION_FORMULA_VERSIONS:
        _fail(reason)
    embedded_run_id = activation_payload.get("run_id")
    if embedded_run_id not in (None, "") and embedded_run_id != run_id:
        _fail(WEEK4_RUN_ID_MISMATCH)
    embedded_ticker = activation_payload.get("ticker")
    if embedded_ticker not in (None, "") and embedded_ticker != ticker:
        _fail(WEEK4_TICKER_MISMATCH)
    entries = activation_payload.get("alphas")
    if not isinstance(entries, list):
        _fail(reason)

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rank, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            _fail(reason)
        activation = _whitelist_activation(entry)
        alpha_id = activation["alpha_id"]
        if alpha_id in seen:
            _fail(reason)
        seen.add(alpha_id)
        rows.append(
            {
                "run_id": run_id,
                "ticker": ticker,
                "alpha_id": alpha_id,
                "alpha_name": activation["alpha_name"],
                "activation_score": activation["activation_score"],
                "status": activation["status"],
                "direction": activation["direction"],
                "formula_version": formula_version,
                "activation_rank": rank,
                "activation_json": activation,
            }
        )
    return rows


def _whitelist_audit_side(value: Any, expected_alpha_id: str) -> dict[str, Any]:
    reason = WEEK4_CONFLICT_PAYLOAD_INVALID
    if not isinstance(value, Mapping):
        _fail(reason)
    alpha_id = _text(value.get("alpha_id"), reason)
    if alpha_id != expected_alpha_id:
        _fail(WEEK4_CONFLICT_DATA_INCONSISTENT)
    qualifying_ids = _string_list(value.get("qualifying_claim_ids"), reason)
    # Candidate Reason-Code Contract (Correctness Patch, section 十五):
    # qualifying_claim_ids must be sorted, unique, and every item non-empty.
    if any(not item.strip() for item in qualifying_ids):
        _fail(reason)
    if len(qualifying_ids) != len(set(qualifying_ids)):
        _fail(WEEK4_CONFLICT_DATA_INCONSISTENT)
    qualifying_count = _integer(value.get("qualifying_count"), reason)
    if qualifying_count != len(qualifying_ids) or qualifying_ids != sorted(qualifying_ids):
        _fail(WEEK4_CONFLICT_DATA_INCONSISTENT)
    raw_excluded = value.get("excluded")
    if not isinstance(raw_excluded, list):
        _fail(reason)
    excluded: list[dict[str, Any]] = []
    for item in raw_excluded:
        if not isinstance(item, Mapping):
            _fail(reason)
        claim_id = item.get("claim_id")
        if claim_id is not None and not isinstance(claim_id, str):
            _fail(reason)
        excluded.append(
            {
                "claim_id": claim_id,
                "reason_code": _text(item.get("reason_code"), reason),
            }
        )
    expected_order = sorted(excluded, key=lambda item: (item["claim_id"] or "", item["reason_code"]))
    excluded_count = _integer(value.get("excluded_count"), reason)
    if excluded != expected_order or excluded_count != len(excluded):
        _fail(WEEK4_CONFLICT_DATA_INCONSISTENT)
    return {
        "alpha_id": alpha_id,
        "qualifying_claim_ids": qualifying_ids,
        "qualifying_count": qualifying_count,
        "excluded": excluded,
        "excluded_count": len(excluded),
    }


def _whitelist_evidence_audit(value: Any, alpha_a: str, alpha_b: str) -> dict[str, Any]:
    reason = WEEK4_CONFLICT_PAYLOAD_INVALID
    if not isinstance(value, Mapping):
        _fail(reason)
    return {
        "alpha_a": _whitelist_audit_side(value.get("alpha_a"), alpha_a),
        "alpha_b": _whitelist_audit_side(value.get("alpha_b"), alpha_b),
    }


def _whitelist_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    reason = WEEK4_CONFLICT_PAYLOAD_INVALID
    alpha_a = _text(candidate.get("alpha_a"), reason)
    alpha_b = _text(candidate.get("alpha_b"), reason)
    if alpha_a >= alpha_b:
        _fail(WEEK4_CONFLICT_DATA_INCONSISTENT)
    outcome = candidate.get("outcome")
    if outcome not in _OUTCOMES:
        _fail(reason)
    reason_codes = _string_list(candidate.get("reason_codes"), reason)
    # Candidate Reason-Code Contract (Correctness Patch, section 十五):
    # admitted <-> empty reason_codes; suppressed/rejected <-> at least one;
    # no duplicate reason codes on any candidate; every code non-empty
    # (already enforced by _string_list's own emptiness check via _text
    # semantics -- but _string_list itself does not require non-empty
    # strings, so it is checked explicitly here).
    if any(not code.strip() for code in reason_codes):
        _fail(reason)
    if len(reason_codes) != len(set(reason_codes)):
        _fail(WEEK4_CONFLICT_DATA_INCONSISTENT)
    if outcome == "admitted" and reason_codes:
        _fail(WEEK4_CONFLICT_DATA_INCONSISTENT)
    if outcome in ("suppressed", "rejected") and not reason_codes:
        _fail(WEEK4_CONFLICT_DATA_INCONSISTENT)
    whitelisted = {
        key: candidate[key] for key in _CANDIDATE_FIELDS if key in candidate
    }
    whitelisted.update(
        {
            "alpha_a": alpha_a,
            "alpha_b": alpha_b,
            "outcome": outcome,
            "reason_codes": reason_codes,
            "evidence_audit": _whitelist_evidence_audit(
                candidate.get("evidence_audit"), alpha_a, alpha_b
            ),
        }
    )
    return _json_copy(whitelisted, reason)


def _whitelist_structure(value: Any) -> dict[str, Any]:
    reason = WEEK4_CONFLICT_PAYLOAD_INVALID
    if not isinstance(value, Mapping):
        _fail(reason)
    structure = {key: value[key] for key in _STRUCTURE_FIELDS if key in value}
    structure["alpha_id"] = _text(value.get("alpha_id"), reason)
    structure["alpha_name"] = _text(value.get("alpha_name"), reason)
    structure["activation_score"] = _number(value.get("activation_score"), 0.0, 100.0, reason)
    structure["status"] = _text(value.get("status"), reason)
    structure["direction"] = _text(value.get("direction"), reason)
    for key in ("claim_ids", "source_agent_output_ids", "agents", "evidence"):
        structure[key] = _string_list(value.get(key), reason)
    raw_scores = value.get("match_scores")
    if not isinstance(raw_scores, list):
        _fail(reason)
    structure["match_scores"] = [
        _number(score, 0.0, 1.0, reason) for score in raw_scores
    ]
    # Evidence Integrity Completion Sprint, Track B (additive, optional --
    # a legacy conflict payload predating this field simply has none).
    if "evidence_facts" in value:
        raw_facts = value.get("evidence_facts")
        if not isinstance(raw_facts, list):
            _fail(reason)
        facts = []
        for item in raw_facts:
            if not isinstance(item, Mapping):
                _fail(reason)
            facts.append(
                {
                    "evidence_fact_group_id": _text(item.get("evidence_fact_group_id"), reason),
                    "representative_claim_id": _text(item.get("representative_claim_id"), reason),
                    "member_claim_ids": _string_list(item.get("member_claim_ids"), reason),
                    "supporting_agents": _string_list(item.get("supporting_agents"), reason),
                    "grouping_method": _text(item.get("grouping_method"), reason),
                }
            )
        structure["evidence_facts"] = facts
    return _json_copy(structure, reason)


def _whitelist_components(value: Any) -> dict[str, float]:
    reason = WEEK4_CONFLICT_PAYLOAD_INVALID
    if not isinstance(value, Mapping) or any(key not in value for key in _COMPONENT_FIELDS):
        _fail(reason)
    return {
        "activation_a": _number(value["activation_a"], 0.0, 100.0, reason),
        "activation_b": _number(value["activation_b"], 0.0, 100.0, reason),
        "minimum_activation": _number(value["minimum_activation"], 0.0, 100.0, reason),
        "contradiction_weight": _number(value["contradiction_weight"], 0.0, 1.0, reason),
        "alpha_a_evidence_strength": _number(
            value["alpha_a_evidence_strength"], 0.0, 1.0, reason
        ),
        "alpha_b_evidence_strength": _number(
            value["alpha_b_evidence_strength"], 0.0, 1.0, reason
        ),
        "evidence_strength": _number(value["evidence_strength"], 0.0, 1.0, reason),
    }


def _whitelist_conflict(conflict: Mapping[str, Any]) -> dict[str, Any]:
    reason = WEEK4_CONFLICT_PAYLOAD_INVALID
    alpha_a = _text(conflict.get("alpha_a"), reason)
    alpha_b = _text(conflict.get("alpha_b"), reason)
    if alpha_a >= alpha_b or conflict.get("conflict_id") != f"{alpha_a}__{alpha_b}":
        _fail(WEEK4_CONFLICT_DATA_INCONSISTENT)
    bull_id = _text(conflict.get("bull_alpha_id"), reason)
    bear_id = _text(conflict.get("bear_alpha_id"), reason)
    if bull_id == bear_id or {bull_id, bear_id} != {alpha_a, alpha_b}:
        _fail(WEEK4_CONFLICT_DATA_INCONSISTENT)
    level = conflict.get("conflict_level")
    if level not in _CONFLICT_LEVELS:
        _fail(reason)
    components = _whitelist_components(conflict.get("components"))
    alpha_a_strength = _number(conflict.get("alpha_a_strength"), 0.0, 1.0, reason)
    alpha_b_strength = _number(conflict.get("alpha_b_strength"), 0.0, 1.0, reason)
    evidence_strength = _number(conflict.get("evidence_strength"), 0.0, 1.0, reason)
    if (
        alpha_a_strength != components["alpha_a_evidence_strength"]
        or alpha_b_strength != components["alpha_b_evidence_strength"]
        or evidence_strength != components["evidence_strength"]
    ):
        _fail(WEEK4_CONFLICT_DATA_INCONSISTENT)
    reason_codes = _string_list(conflict.get("reason_codes"), reason)
    if reason_codes:
        _fail(WEEK4_CONFLICT_DATA_INCONSISTENT)

    bull_structure = _whitelist_structure(conflict.get("bull_structure"))
    bear_structure = _whitelist_structure(conflict.get("bear_structure"))
    if (
        bull_structure["alpha_id"] != bull_id
        or bear_structure["alpha_id"] != bear_id
        or bull_structure["direction"] != "positive"
        or bear_structure["direction"] != "negative"
    ):
        _fail(WEEK4_CONFLICT_DATA_INCONSISTENT)

    whitelisted = {key: conflict[key] for key in _CONFLICT_FIELDS if key in conflict}
    whitelisted.update(
        {
            "conflict_id": f"{alpha_a}__{alpha_b}",
            "alpha_a": alpha_a,
            "alpha_b": alpha_b,
            "bull_alpha_id": bull_id,
            "bear_alpha_id": bear_id,
            "bull_structure": bull_structure,
            "bear_structure": bear_structure,
            "components": components,
            "alpha_a_strength": alpha_a_strength,
            "alpha_b_strength": alpha_b_strength,
            "evidence_strength": evidence_strength,
            "conflict_score": _number(conflict.get("conflict_score"), 0.0, 100.0, reason),
            "conflict_level": level,
            "reason_codes": reason_codes,
            "explanation": _text(conflict.get("explanation"), reason),
            # Evidence Integrity Completion Sprint, Track B: additive
            # fact-level evidence statistics for each side, plus the
            # dual-side integrity check outcome.
            "bull_raw_claim_count": _integer(conflict.get("bull_raw_claim_count"), reason),
            "bull_unique_fact_count": _integer(conflict.get("bull_unique_fact_count"), reason),
            "bull_distinct_agent_count": _integer(conflict.get("bull_distinct_agent_count"), reason),
            "bull_overlap_ratio": _number(conflict.get("bull_overlap_ratio"), 0.0, 1.0, reason),
            "bull_fact_group_ids": _string_list(conflict.get("bull_fact_group_ids"), reason),
            "bear_raw_claim_count": _integer(conflict.get("bear_raw_claim_count"), reason),
            "bear_unique_fact_count": _integer(conflict.get("bear_unique_fact_count"), reason),
            "bear_distinct_agent_count": _integer(conflict.get("bear_distinct_agent_count"), reason),
            "bear_overlap_ratio": _number(conflict.get("bear_overlap_ratio"), 0.0, 1.0, reason),
            "bear_fact_group_ids": _string_list(conflict.get("bear_fact_group_ids"), reason),
            "shared_fact_group_ids": _string_list(conflict.get("shared_fact_group_ids"), reason),
            "shared_fact_group_count": _integer(conflict.get("shared_fact_group_count"), reason),
            "shared_fact_resolution": _text(conflict.get("shared_fact_resolution"), reason),
        }
    )
    return _json_copy(whitelisted, reason)


def build_conflict_rows(
    run_id: str,
    ticker: str,
    conflict_payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    reason = WEEK4_CONFLICT_PAYLOAD_INVALID
    run_id = _text(run_id, reason)
    ticker = _text(ticker, reason)
    if not isinstance(conflict_payload, Mapping):
        _fail(reason)
    if conflict_payload.get("schema_version") != CONFLICT_SCHEMA_VERSION:
        _fail(reason)
    if conflict_payload.get("formula_version") != CONFLICT_FORMULA_VERSION:
        _fail(reason)
    if conflict_payload.get("run_id") != run_id:
        _fail(WEEK4_RUN_ID_MISMATCH)
    if conflict_payload.get("ticker") != ticker:
        _fail(WEEK4_TICKER_MISMATCH)

    raw_conflicts = conflict_payload.get("conflicts")
    arbitration = conflict_payload.get("arbitration")
    if not isinstance(raw_conflicts, list) or not isinstance(arbitration, Mapping):
        _fail(reason)
    raw_candidates = arbitration.get("candidate_evaluations")
    if not isinstance(raw_candidates, list):
        _fail(reason)

    conflicts: list[dict[str, Any]] = []
    conflict_by_pair: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}
    for rank, raw_conflict in enumerate(raw_conflicts):
        if not isinstance(raw_conflict, Mapping):
            _fail(reason)
        conflict = _whitelist_conflict(raw_conflict)
        pair = (conflict["alpha_a"], conflict["alpha_b"])
        if pair in conflict_by_pair:
            _fail(WEEK4_CONFLICT_DATA_INCONSISTENT)
        conflicts.append(conflict)
        conflict_by_pair[pair] = (rank, conflict)

    raw_main = conflict_payload.get("main_conflict")
    if conflicts:
        if not isinstance(raw_main, Mapping):
            _fail(WEEK4_CONFLICT_DATA_INCONSISTENT)
        if _whitelist_conflict(raw_main) != conflicts[0]:
            _fail(WEEK4_CONFLICT_DATA_INCONSISTENT)
    elif raw_main is not None:
        _fail(WEEK4_CONFLICT_DATA_INCONSISTENT)

    candidates: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    outcome_counts = {"admitted": 0, "suppressed": 0, "rejected": 0}
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, Mapping):
            _fail(reason)
        candidate = _whitelist_candidate(raw_candidate)
        pair = (candidate["alpha_a"], candidate["alpha_b"])
        if pair in seen_pairs:
            _fail(WEEK4_CONFLICT_DATA_INCONSISTENT)
        seen_pairs.add(pair)
        outcome = candidate["outcome"]
        outcome_counts[outcome] += 1
        has_conflict = pair in conflict_by_pair
        if (outcome == "admitted") != has_conflict:
            _fail(WEEK4_CONFLICT_DATA_INCONSISTENT)
        candidates.append(candidate)

    if set(conflict_by_pair) != {
        (candidate["alpha_a"], candidate["alpha_b"])
        for candidate in candidates
        if candidate["outcome"] == "admitted"
    }:
        _fail(WEEK4_CONFLICT_DATA_INCONSISTENT)
    if _integer(arbitration.get("declared_pair_count"), reason) != len(candidates):
        _fail(WEEK4_CONFLICT_DATA_INCONSISTENT)
    for outcome in _OUTCOMES:
        if _integer(arbitration.get(f"{outcome}_count"), reason) != outcome_counts[outcome]:
            _fail(WEEK4_CONFLICT_DATA_INCONSISTENT)

    rows: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: (item["alpha_a"], item["alpha_b"])):
        pair = (candidate["alpha_a"], candidate["alpha_b"])
        admitted = conflict_by_pair.get(pair)
        conflict_rank, conflict = admitted if admitted is not None else (None, None)
        components = conflict["components"] if conflict is not None else {}
        rows.append(
            {
                "run_id": run_id,
                "ticker": ticker,
                "alpha_a": pair[0],
                "alpha_b": pair[1],
                "outcome": candidate["outcome"],
                "bull_alpha_id": conflict["bull_alpha_id"] if conflict else None,
                "bear_alpha_id": conflict["bear_alpha_id"] if conflict else None,
                "conflict_score": conflict["conflict_score"] if conflict else None,
                "conflict_level": conflict["conflict_level"] if conflict else None,
                "contradiction_weight": components.get("contradiction_weight"),
                "evidence_strength": conflict["evidence_strength"] if conflict else None,
                "minimum_activation": components.get("minimum_activation"),
                "is_main_conflict": conflict_rank == 0,
                "conflict_rank": conflict_rank,
                "reason_codes": candidate["reason_codes"],
                "evidence_audit": candidate["evidence_audit"],
                "candidate_json": candidate,
                "conflict_json": conflict,
                "schema_version": CONFLICT_SCHEMA_VERSION,
                "formula_version": CONFLICT_FORMULA_VERSION,
            }
        )
    return rows


def _validate_week4_snapshot(
    activation_rows: Sequence[Mapping[str, Any]],
    conflict_rows: Sequence[Mapping[str, Any]],
) -> None:
    """Cross-Payload Snapshot Validation (2026-07-14 Correctness Patch,
    sections 三-六): every *admitted* conflict row's embedded activation
    snapshot must actually match the activation rows built in the same
    ``build_week4_rows`` call -- i.e. both payloads describe the same
    underlying Week 3 activation computation, not two payloads that happen
    to share a run_id/ticker/version but disagree on the numbers.

    Pure function: reads ``activation_rows``/``conflict_rows`` (the
    already-built, already-individually-validated canonical rows -- never
    re-reads either raw payload), never touches the database, never
    mutates its inputs. Called by ``build_week4_rows`` before it returns,
    so a mismatch is caught before ``persist_week4_results`` ever opens a
    transaction.

    This does not re-decide contradiction_weight/evidence_strength/
    conflict_score/ranking -- those are trusted as already-correct W4.1
    Conflict Detector output; this only checks internal consistency between
    the two payloads being persisted together.
    """
    reason = WEEK4_CONFLICT_DATA_INCONSISTENT
    activation_by_alpha_id = {row["alpha_id"]: row for row in activation_rows}

    for row in conflict_rows:
        if row["outcome"] != "admitted":
            continue
        alpha_a, alpha_b = row["alpha_a"], row["alpha_b"]
        activation_a = activation_by_alpha_id.get(alpha_a)
        activation_b = activation_by_alpha_id.get(alpha_b)
        if activation_a is None or activation_b is None:
            _fail(reason)

        conflict = row["conflict_json"]
        components = conflict["components"]
        if components["activation_a"] != activation_a["activation_score"]:
            _fail(reason)
        if components["activation_b"] != activation_b["activation_score"]:
            _fail(reason)
        if components["minimum_activation"] != min(
            activation_a["activation_score"], activation_b["activation_score"]
        ):
            _fail(reason)

        bull_id = conflict["bull_alpha_id"]
        bear_id = conflict["bear_alpha_id"]
        if {bull_id, bear_id} != {alpha_a, alpha_b}:
            _fail(reason)
        bull_activation = activation_by_alpha_id.get(bull_id)
        bear_activation = activation_by_alpha_id.get(bear_id)
        if bull_activation is None or bear_activation is None:
            _fail(reason)

        bull_structure = conflict["bull_structure"]
        if (
            bull_structure["alpha_id"] != bull_id
            or bull_structure["alpha_name"] != bull_activation["alpha_name"]
            or bull_structure["activation_score"] != bull_activation["activation_score"]
            or bull_structure["status"] != bull_activation["status"]
            or bull_structure["direction"] != bull_activation["direction"]
            or bull_structure["direction"] != "positive"
        ):
            _fail(reason)

        bear_structure = conflict["bear_structure"]
        if (
            bear_structure["alpha_id"] != bear_id
            or bear_structure["alpha_name"] != bear_activation["alpha_name"]
            or bear_structure["activation_score"] != bear_activation["activation_score"]
            or bear_structure["status"] != bear_activation["status"]
            or bear_structure["direction"] != bear_activation["direction"]
            or bear_structure["direction"] != "negative"
        ):
            _fail(reason)


def build_week4_rows(
    *,
    run_id: str,
    ticker: str,
    activation_payload: Mapping[str, Any],
    conflict_payload: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    activation_rows = build_activation_rows(run_id, ticker, activation_payload)
    conflict_rows = build_conflict_rows(run_id, ticker, conflict_payload)
    _validate_week4_snapshot(activation_rows, conflict_rows)
    return activation_rows, conflict_rows


def _stored_candidate(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail(DB_DATA_CORRUPTED)
    raw = _json_copy(value, DB_DATA_CORRUPTED)
    try:
        validated = _whitelist_candidate(value)
    except Week4PersistenceDataError:
        _fail(DB_DATA_CORRUPTED)
    if validated != raw:
        _fail(DB_DATA_CORRUPTED)
    return validated


def _stored_conflict(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail(DB_DATA_CORRUPTED)
    raw = _json_copy(value, DB_DATA_CORRUPTED)
    try:
        validated = _whitelist_conflict(value)
    except Week4PersistenceDataError:
        _fail(DB_DATA_CORRUPTED)
    if validated != raw:
        _fail(DB_DATA_CORRUPTED)
    return validated


def reconstruct_conflict_result(
    run_id: str,
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    if not rows:
        return None
    try:
        expected_run_id = _text(run_id, DB_DATA_CORRUPTED)
        pairs: set[tuple[str, str]] = set()
        ranks: set[int] = set()
        candidates: list[dict[str, Any]] = []
        ranked_conflicts: list[tuple[int, dict[str, Any]]] = []
        main_conflicts: list[dict[str, Any]] = []
        schema_versions: set[str] = set()
        formula_versions: set[str] = set()
        tickers: set[str] = set()

        for row in rows:
            if not isinstance(row, Mapping) or row.get("run_id") != expected_run_id:
                _fail(DB_DATA_CORRUPTED)
            pair = (_text(row.get("alpha_a"), DB_DATA_CORRUPTED), _text(row.get("alpha_b"), DB_DATA_CORRUPTED))
            if pair[0] >= pair[1] or pair in pairs:
                _fail(DB_DATA_CORRUPTED)
            pairs.add(pair)
            schema_versions.add(_text(row.get("schema_version"), DB_DATA_CORRUPTED))
            formula_versions.add(_text(row.get("formula_version"), DB_DATA_CORRUPTED))
            tickers.add(_text(row.get("ticker"), DB_DATA_CORRUPTED))

            candidate_copy = _stored_candidate(row.get("candidate_json"))
            if (
                candidate_copy.get("alpha_a") != pair[0]
                or candidate_copy.get("alpha_b") != pair[1]
                or candidate_copy.get("outcome") != row.get("outcome")
                or candidate_copy.get("reason_codes") != row.get("reason_codes")
                or candidate_copy.get("evidence_audit") != row.get("evidence_audit")
            ):
                _fail(DB_DATA_CORRUPTED)
            candidates.append(candidate_copy)

            admitted = row.get("outcome") == "admitted"
            conflict = row.get("conflict_json")
            conflict_rank = row.get("conflict_rank")
            is_main = row.get("is_main_conflict") is True
            admitted_fields = (
                row.get("bull_alpha_id"),
                row.get("bear_alpha_id"),
                row.get("conflict_score"),
                row.get("conflict_level"),
                row.get("contradiction_weight"),
                row.get("evidence_strength"),
                row.get("minimum_activation"),
            )
            if admitted:
                if not isinstance(conflict_rank, int):
                    _fail(DB_DATA_CORRUPTED)
                if conflict_rank < 0 or conflict_rank in ranks or any(value is None for value in admitted_fields):
                    _fail(DB_DATA_CORRUPTED)
                ranks.add(conflict_rank)
                conflict_copy = _stored_conflict(conflict)
                if (
                    conflict_copy.get("alpha_a") != pair[0]
                    or conflict_copy.get("alpha_b") != pair[1]
                    or conflict_copy.get("bull_alpha_id") != row.get("bull_alpha_id")
                    or conflict_copy.get("bear_alpha_id") != row.get("bear_alpha_id")
                    or conflict_copy.get("conflict_score") != row.get("conflict_score")
                    or conflict_copy.get("conflict_level") != row.get("conflict_level")
                    or conflict_copy.get("evidence_strength") != row.get("evidence_strength")
                    or conflict_copy.get("components", {}).get("contradiction_weight")
                    != row.get("contradiction_weight")
                    or conflict_copy.get("components", {}).get("minimum_activation")
                    != row.get("minimum_activation")
                ):
                    _fail(DB_DATA_CORRUPTED)
                ranked_conflicts.append((conflict_rank, conflict_copy))
                if is_main:
                    main_conflicts.append(conflict_copy)
            elif (
                conflict is not None
                or conflict_rank is not None
                or is_main
                or any(value is not None for value in admitted_fields)
                or row.get("outcome") not in {"suppressed", "rejected"}
            ):
                _fail(DB_DATA_CORRUPTED)

        if (
            schema_versions != {CONFLICT_SCHEMA_VERSION}
            or formula_versions != {CONFLICT_FORMULA_VERSION}
            or len(tickers) != 1
        ):
            _fail(DB_DATA_CORRUPTED)
        ranked_conflicts.sort(key=lambda item: item[0])
        if [rank for rank, _ in ranked_conflicts] != list(range(len(ranked_conflicts))):
            _fail(DB_DATA_CORRUPTED)
        conflicts = [conflict for _, conflict in ranked_conflicts]
        if conflicts:
            if len(main_conflicts) != 1 or main_conflicts[0] != conflicts[0]:
                _fail(DB_DATA_CORRUPTED)
            main_conflict = conflicts[0]
        else:
            if main_conflicts:
                _fail(DB_DATA_CORRUPTED)
            main_conflict = None

        candidates.sort(key=lambda item: (item["alpha_a"], item["alpha_b"]))
        counts = {
            outcome: sum(candidate["outcome"] == outcome for candidate in candidates)
            for outcome in _OUTCOMES
        }
        return {
            "schema_version": CONFLICT_SCHEMA_VERSION,
            "formula_version": CONFLICT_FORMULA_VERSION,
            "run_id": expected_run_id,
            "ticker": next(iter(tickers)),
            "conflicts": conflicts,
            "main_conflict": main_conflict,
            "arbitration": {
                "declared_pair_count": len(candidates),
                "admitted_count": counts["admitted"],
                "suppressed_count": counts["suppressed"],
                "rejected_count": counts["rejected"],
                "candidate_evaluations": candidates,
            },
        }
    except Week4PersistenceDataError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError):
        _fail(DB_DATA_CORRUPTED)


__all__ = [
    "DB_DATA_CORRUPTED",
    "WEEK4_ACTIVATION_PAYLOAD_INVALID",
    "WEEK4_CONFLICT_DATA_INCONSISTENT",
    "WEEK4_CONFLICT_PAYLOAD_INVALID",
    "WEEK4_RUN_ID_MISMATCH",
    "WEEK4_TICKER_MISMATCH",
    "Week4PersistenceDataError",
    "build_week4_rows",
    "reconstruct_conflict_result",
]
