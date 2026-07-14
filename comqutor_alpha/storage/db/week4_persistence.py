"""Pure validation, whitelisting, and reconstruction for Week 4 persistence."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

from comqutor_alpha.conflict_engine.conflict_schema import (
    CONFLICT_FORMULA_VERSION,
    CONFLICT_SCHEMA_VERSION,
)
from comqutor_alpha.graph_engine.graph_schema import ACTIVATION_FORMULA_VERSION

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
_ACTIVATION_COMPONENTS = frozenset(
    {
        "matched_evidence",
        "agent_agreement",
        "graph_coherence",
        "recency",
        "direction_strength",
    }
)
_ACTIVATION_COMPONENT_FIELDS = frozenset(
    {
        "raw",
        "weight",
        "contribution",
        "unique_committed_claims",
        "unique_ambiguous_claims",
        "weighted_evidence_sum",
        "saturation",
        "ambiguous_weight",
        "distinct_agents",
        "denominator",
        "denominator_source",
        "agents",
        "scope",
        "evidence_gated",
        "age_days",
        "fallback",
        "reason",
        "decay_window_days",
        "qualifying_claim_count",
        "average_signed_strength",
        "mixed_direction_evidence",
    }
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


def _fail(reason_code: str) -> None:
    raise Week4PersistenceDataError(reason_code)


def _text(value: Any, reason_code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(reason_code)
    return value.strip()


def _number(value: Any, minimum: float, maximum: float, reason_code: str) -> float:
    if isinstance(value, bool):
        _fail(reason_code)
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        _fail(reason_code)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        _fail(reason_code)
    return number


def _integer(value: Any, reason_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
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


def _whitelist_activation_components(value: Any) -> dict[str, Any]:
    reason = WEEK4_ACTIVATION_PAYLOAD_INVALID
    if not isinstance(value, Mapping):
        _fail(reason)
    components: dict[str, Any] = {}
    for name in sorted(_ACTIVATION_COMPONENTS):
        if name not in value:
            continue
        component = value[name]
        if not isinstance(component, Mapping):
            _fail(reason)
        components[name] = _json_copy(
            {key: component[key] for key in sorted(_ACTIVATION_COMPONENT_FIELDS) if key in component},
            reason,
        )
    return components


def _whitelist_activation(entry: Mapping[str, Any]) -> dict[str, Any]:
    reason = WEEK4_ACTIVATION_PAYLOAD_INVALID
    activation = {key: entry[key] for key in _ACTIVATION_FIELDS if key in entry}
    activation["alpha_id"] = _text(entry.get("alpha_id"), reason)
    activation["alpha_name"] = _text(entry.get("alpha_name"), reason)
    activation["activation_score"] = _number(entry.get("activation_score"), 0.0, 100.0, reason)
    activation["status"] = _text(entry.get("status"), reason)
    activation["direction"] = _text(entry.get("direction"), reason)
    activation["components"] = _whitelist_activation_components(entry.get("components"))
    activation["evidence_count"] = _integer(entry.get("evidence_count"), reason)
    activation["distinct_supporting_agents"] = _integer(
        entry.get("distinct_supporting_agents"), reason
    )
    activation["claim_ids"] = _string_list(entry.get("claim_ids"), reason)
    activation["evidence"] = _string_list(entry.get("evidence"), reason)
    activation["reason_codes"] = _string_list(entry.get("reason_codes"), reason)
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
    if activation_payload.get("formula_version") != ACTIVATION_FORMULA_VERSION:
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
                "formula_version": ACTIVATION_FORMULA_VERSION,
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
    if outcome == "admitted" and reason_codes:
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


def build_week4_rows(
    *,
    run_id: str,
    ticker: str,
    activation_payload: Mapping[str, Any],
    conflict_payload: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return (
        build_activation_rows(run_id, ticker, activation_payload),
        build_conflict_rows(run_id, ticker, conflict_payload),
    )


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
