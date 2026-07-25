"""Week 4 deterministic Conflict Detector (W4.1).

Pure function of its inputs: no filesystem, no database, no environment
variables, no network, no randomness, no wall-clock reads. The same
semantic input always produces the exact same serialized output, because
every collection this module builds is deduplicated/sorted before it is
placed in the result.

Consumes exactly three structured boundaries -- never raw TradingAgents
text, never a prompt, never an LLM/provider response:

1. Week 3's activation payload (``score_alpha_activations()``'s return
   shape: ``{"alphas": [...], ...}``, i.e. ``structure_graph.json``'s
   ``activation`` key).
2. Week 2's ``alpha_matches`` records (``alpha_matches.json``'s ``matches``
   list -- the same record shape
   ``graph_engine.activation_scorer._gather_alpha_evidence`` already reads).
3. The Alpha taxonomy (``alpha_library.alpha_loader.load_alpha_taxonomy()``'s
   return shape).

Relation resolution reuses ``activation_scorer._relation_for_match`` --
Week 3's own canonical relation resolver -- directly, rather than
reimplementing an equivalent lookup. It is imported by its private name
deliberately: the alternative (copying its ~10 lines here) is exactly what
docs/week4_spec_freeze_audit.md and this task both explicitly forbid
("直接 import 现有 helper，不要复制同义实现").
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.conflict_engine.conflict_schema import (
    ADMISSIBLE_STATUSES,
    CONFLICT_FORMULA_VERSION,
    CONFLICT_SCHEMA_VERSION,
    EXCLUDED_DUPLICATE_CLAIM,
    EXCLUDED_EMPTY_EVIDENCE,
    EXCLUDED_INVALID_MATCH_SCORE,
    EXCLUDED_MISSING_CLAIM_ID,
    EXCLUDED_NON_COMMITTED_MATCH,
    EXCLUDED_UNSUPPORTED_RELATION,
    EXCLUDED_WRONG_ALPHA,
    QUALIFYING_RELATIONS,
    REASON_ACTIVATION_VERSION_MISMATCH,
    REASON_AMBIGUOUS_ONLY,
    REASON_ASYMMETRIC_CONTRADICTION_WEIGHT,
    REASON_BELOW_ACTIVATION_THRESHOLD,
    REASON_DIRECTION_ROLE_UNRESOLVED,
    REASON_DUPLICATE_CLAIM_CONFLICT,
    REASON_DUPLICATE_PAIR,
    REASON_INVALID_ACTIVATION_SCORE,
    REASON_INVALID_CONTRADICTION_WEIGHT,
    REASON_MISSING_LEFT_ACTIVATION,
    REASON_MISSING_LEFT_EVIDENCE,
    REASON_MISSING_RECIPROCAL_DECLARATION,
    REASON_MISSING_RIGHT_ACTIVATION,
    REASON_MISSING_RIGHT_EVIDENCE,
    REASON_NON_FINITE_SCORE_COMPONENT,
    REASON_PAIR_NOT_DECLARED,
    REASON_RUN_ID_MISMATCH,
    REASON_TICKER_MISMATCH,
    REASON_UNKNOWN_ACTIVATION_ALPHA,
    REASON_ZERO_EVIDENCE_STRENGTH,
    REJECTED_CLASS_REASONS,
    ConflictInputError,
    canonical_pair_key,
    clamp_percent,
    conflict_id,
    conflict_level,
    dedupe_stable,
    is_finite_number,
    resolve_bull_bear,
)
from comqutor_alpha.graph_engine.activation_scorer import _relation_for_match
from comqutor_alpha.graph_engine.activation_scorer_v2 import (
    ACTIVATION_V2_FORMULA_VERSION,
)
from comqutor_alpha.graph_engine.graph_schema import ACTIVATION_FORMULA_VERSION

# The detector consumes the run's *primary* activation payload: the frozen
# v1 formula (historical runs) or Activation v2 (new runs). The conflict
# score formula itself -- min(activation_a, activation_b) x
# contradiction_weight x evidence_strength -- is identical for both and is
# never changed by the activation version.
SUPPORTED_ACTIVATION_FORMULA_VERSIONS = frozenset(
    {ACTIVATION_FORMULA_VERSION, ACTIVATION_V2_FORMULA_VERSION}
)

# ---------------------------------------------------------------------------
# Taxonomy pair enumeration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _DeclaredPair:
    alpha_a: str
    alpha_b: str
    contradiction_weight: float | None
    reason_codes: tuple[str, ...] = ()


def _safe_contradiction_weight(value: Any) -> float | None:
    if not is_finite_number(value):
        return None
    weight = float(value)
    return weight if 0.0 <= weight <= 1.0 else None


def _enumerate_canonical_pairs(taxonomy: Mapping[str, Any]) -> list[_DeclaredPair]:
    """Validate directed declarations and emit deterministic undirected pairs."""
    if not isinstance(taxonomy, Mapping):
        raise ConflictInputError("SCHEMA_INVALID")

    alpha_ids: set[str] = set()
    alphas_by_id: dict[str, Any] = {}
    for raw_key, alpha in taxonomy.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise ConflictInputError("SCHEMA_INVALID")
        alpha_id = getattr(alpha, "alpha_id", None)
        if not isinstance(alpha_id, str) or not alpha_id.strip() or alpha_id != raw_key:
            raise ConflictInputError("SCHEMA_INVALID")
        conflicts = getattr(alpha, "conflict_alphas", None)
        if not isinstance(conflicts, Sequence) or isinstance(conflicts, (str, bytes)):
            raise ConflictInputError("SCHEMA_INVALID")
        alpha_ids.add(alpha_id)
        alphas_by_id[alpha_id] = alpha

    directed: dict[tuple[str, str], list[float | None]] = {}
    for source_id in sorted(alpha_ids):
        alpha = alphas_by_id[source_id]
        for conflict in alpha.conflict_alphas:
            target_id = getattr(conflict, "alpha_id", None)
            if not isinstance(target_id, str) or not target_id.strip():
                raise ConflictInputError("SCHEMA_INVALID")
            if target_id not in alpha_ids or target_id == source_id:
                raise ConflictInputError("SCHEMA_INVALID")
            weight = _safe_contradiction_weight(
                getattr(conflict, "contradiction_weight", None)
            )
            directed.setdefault((source_id, target_id), []).append(weight)

    canonical_keys = sorted(
        {canonical_pair_key(source_id, target_id) for source_id, target_id in directed}
    )
    pairs: list[_DeclaredPair] = []
    for alpha_a, alpha_b in canonical_keys:
        forward = directed.get((alpha_a, alpha_b), [])
        reverse = directed.get((alpha_b, alpha_a), [])
        reason_codes: list[str] = []

        if len(forward) > 1 or len(reverse) > 1:
            reason_codes.append(REASON_DUPLICATE_PAIR)
        if not forward or not reverse:
            reason_codes.append(REASON_MISSING_RECIPROCAL_DECLARATION)

        all_weights = [*forward, *reverse]
        if any(weight is None for weight in all_weights):
            reason_codes.append(REASON_INVALID_CONTRADICTION_WEIGHT)

        contradiction_weight = None
        if (
            len(forward) == 1
            and len(reverse) == 1
            and forward[0] is not None
            and reverse[0] is not None
        ):
            if forward[0] != reverse[0]:
                reason_codes.append(REASON_ASYMMETRIC_CONTRADICTION_WEIGHT)
            else:
                contradiction_weight = forward[0]

        pairs.append(
            _DeclaredPair(
                alpha_a=alpha_a,
                alpha_b=alpha_b,
                contradiction_weight=contradiction_weight,
                reason_codes=tuple(dedupe_stable(reason_codes)),
            )
        )
    return pairs


# ---------------------------------------------------------------------------
# Activation lookup
# ---------------------------------------------------------------------------


def _index_activations(
    activation_payload: Mapping[str, Any], taxonomy_ids: set[str]
) -> dict[str, Mapping[str, Any]]:
    """Build alpha_id -> activation entry, or raise ConflictInputError.

    Raised (never gracefully degraded) only for a structural contract
    violation of the whole payload: not a mapping with an "alphas" list, or
    a duplicate alpha_id within it. A single malformed *entry* inside an
    otherwise well-formed list is not raised here -- that is handled
    per-candidate (INVALID_ACTIVATION_SCORE/NON_FINITE_SCORE_COMPONENT) so
    one bad alpha entry cannot take down evaluation of the other five pairs.
    """
    if not isinstance(activation_payload, Mapping):
        raise ConflictInputError("SCHEMA_INVALID")
    if activation_payload.get("formula_version") not in SUPPORTED_ACTIVATION_FORMULA_VERSIONS:
        raise ConflictInputError(REASON_ACTIVATION_VERSION_MISMATCH)
    alphas = activation_payload.get("alphas")
    if not isinstance(alphas, list):
        raise ConflictInputError("SCHEMA_INVALID")

    index: dict[str, Mapping[str, Any]] = {}
    for entry in alphas:
        if not isinstance(entry, Mapping):
            raise ConflictInputError("SCHEMA_INVALID")
        alpha_id = entry.get("alpha_id")
        if not alpha_id or not str(alpha_id).strip():
            raise ConflictInputError("SCHEMA_INVALID")
        alpha_id = str(alpha_id)
        if alpha_id not in taxonomy_ids:
            raise ConflictInputError(REASON_UNKNOWN_ACTIVATION_ALPHA)
        if alpha_id in index:
            raise ConflictInputError("SCHEMA_INVALID")
        index[alpha_id] = entry
    return index


class _ActivationFields:
    __slots__ = ("score", "status", "direction", "name", "reason_codes")

    def __init__(self, score, status, direction, name, reason_codes: list[str]) -> None:
        self.score = score
        self.status = status
        self.direction = direction
        self.name = name
        self.reason_codes = reason_codes


def _extract_activation_fields(entry: Mapping[str, Any], alpha_id: str) -> _ActivationFields:
    reason_codes: list[str] = []
    raw_score = entry.get("activation_score")
    if not is_finite_number(raw_score):
        reason_codes.append(REASON_NON_FINITE_SCORE_COMPONENT)
        score = None
    else:
        score = float(raw_score)
        if not (0.0 <= score <= 100.0):
            reason_codes.append(REASON_INVALID_ACTIVATION_SCORE)
            score = None

    status = entry.get("status")
    status = str(status) if isinstance(status, str) and status else None

    direction = entry.get("direction")
    direction = str(direction) if isinstance(direction, str) and direction else None

    name = entry.get("alpha_name")
    name = str(name) if isinstance(name, str) and name else alpha_id

    return _ActivationFields(score, status, direction, name, reason_codes)


# ---------------------------------------------------------------------------
# Evidence gathering
# ---------------------------------------------------------------------------


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _stable_number(value: Any) -> tuple[str, float | str]:
    if is_finite_number(value):
        return "finite", float(value)
    return "invalid", _normalized_text(value)


def _normalized_alpha_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(sorted({_normalized_text(item) for item in value if _normalized_text(item)}))


def _candidate_relation_semantics(record: Mapping[str, Any]) -> tuple[tuple[str, str, str], ...]:
    semantics: list[tuple[str, str, str]] = []
    for pool_key in ("eligible_candidates", "top_candidates", "candidate_scores"):
        pool = record.get(pool_key)
        if not isinstance(pool, Sequence) or isinstance(pool, (str, bytes)):
            continue
        for candidate in pool:
            if not isinstance(candidate, Mapping):
                continue
            alpha_id = _normalized_text(candidate.get("alpha_id"))
            relation = _normalized_text(candidate.get("relation")).lower() or "unknown"
            if alpha_id:
                semantics.append((pool_key, alpha_id, relation))
    return tuple(sorted(semantics))


def _resolved_relation_semantics(record: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    alpha_ids = set(_normalized_alpha_list(record.get("plausible_alphas")))
    matched_alpha = _normalized_text(record.get("matched_alpha"))
    if matched_alpha:
        alpha_ids.add(matched_alpha)
    alpha_ids.update(item[1] for item in _candidate_relation_semantics(record))
    return tuple(
        (alpha_id, _relation_for_match(record, alpha_id)) for alpha_id in sorted(alpha_ids)
    )


def _claim_semantic_fingerprint(record: Mapping[str, Any]) -> tuple[Any, ...]:
    evidence = _normalized_text(record.get("evidence") or record.get("claim"))
    return (
        _normalized_text(record.get("match_status")).lower(),
        _normalized_text(record.get("matched_alpha")),
        _resolved_relation_semantics(record),
        _stable_number(record.get("score")),
        evidence,
        _normalized_text(record.get("source_agent_output_id")),
        _normalized_text(record.get("agent")),
        _normalized_alpha_list(record.get("plausible_alphas")),
        _candidate_relation_semantics(record),
        _normalized_text(record.get("run_id")),
        _normalized_text(record.get("ticker")),
    )


def _stable_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _stable_json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_stable_json_value(item) for item in value]
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if is_finite_number(value) else _normalized_text(value)
    return {"type": type(value).__name__}


def _canonical_record_key(record: Mapping[str, Any]) -> str:
    return json.dumps(
        _stable_json_value(record),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonicalize_alpha_matches(
    alpha_matches: Sequence[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], dict[str, int]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    missing_claim_id: list[Mapping[str, Any]] = []
    for record in alpha_matches:
        if not isinstance(record, Mapping):
            continue
        claim_id = _normalized_text(record.get("claim_id"))
        if claim_id:
            grouped.setdefault(claim_id, []).append(record)
        else:
            missing_claim_id.append(record)

    canonical: list[Mapping[str, Any]] = []
    duplicate_counts: dict[str, int] = {}
    for claim_id in sorted(grouped):
        records = grouped[claim_id]
        fingerprints = {_claim_semantic_fingerprint(record) for record in records}
        if len(fingerprints) != 1:
            raise ConflictInputError(REASON_DUPLICATE_CLAIM_CONFLICT)
        canonical.append(min(records, key=_canonical_record_key))
        if len(records) > 1:
            duplicate_counts[claim_id] = len(records) - 1

    canonical.extend(sorted(missing_claim_id, key=_canonical_record_key))
    canonical.sort(
        key=lambda record: (
            _normalized_text(record.get("claim_id")),
            _canonical_record_key(record),
        )
    )
    return canonical, duplicate_counts


def _claim_is_relevant_to_alpha(record: Mapping[str, Any], alpha_id: str) -> bool:
    if _normalized_text(record.get("matched_alpha")) == alpha_id:
        return True
    plausible = record.get("plausible_alphas")
    if (
        isinstance(plausible, Sequence)
        and not isinstance(plausible, (str, bytes))
        and alpha_id in {_normalized_text(item) for item in plausible}
    ):
        return True
    candidates = record.get("candidate_scores")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        return False
    for candidate in candidates:
        if (
            isinstance(candidate, Mapping)
            and _normalized_text(candidate.get("alpha_id")) == alpha_id
        ):
            return True
    return False


@dataclass(frozen=True)
class _EvidenceResult:
    qualifying: list[dict[str, Any]]
    excluded: list[dict[str, Any]]
    ambiguous_only: bool


def _gather_qualifying_evidence(
    alpha_id: str,
    alpha_matches: Sequence[Mapping[str, Any]],
    duplicate_counts: Mapping[str, int],
) -> _EvidenceResult:
    """Gather one Alpha's committed evidence and stable exclusion audit."""
    qualifying: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    relevant_count = 0
    only_ambiguous_exclusions = True

    for record in alpha_matches:
        if not isinstance(record, Mapping):
            continue
        if not _claim_is_relevant_to_alpha(record, alpha_id):
            continue
        relevant_count += 1

        claim_id = _normalized_text(record.get("claim_id"))
        if not claim_id:
            only_ambiguous_exclusions = False
            excluded.append({"claim_id": None, "reason_code": EXCLUDED_MISSING_CLAIM_ID})
            continue

        match_status = _normalized_text(record.get("match_status")).lower()
        if match_status != "matched":
            if match_status != "ambiguous":
                only_ambiguous_exclusions = False
            excluded.append({"claim_id": claim_id, "reason_code": EXCLUDED_NON_COMMITTED_MATCH})
        elif _normalized_text(record.get("matched_alpha")) != alpha_id:
            only_ambiguous_exclusions = False
            excluded.append({"claim_id": claim_id, "reason_code": EXCLUDED_WRONG_ALPHA})
        else:
            only_ambiguous_exclusions = False
            evidence_text = str(
                record.get("evidence") or record.get("claim") or ""
            ).strip()
            relation = _relation_for_match(record, alpha_id)
            raw_score = record.get("score")
            if not evidence_text:
                excluded.append(
                    {"claim_id": claim_id, "reason_code": EXCLUDED_EMPTY_EVIDENCE}
                )
            elif relation not in QUALIFYING_RELATIONS:
                excluded.append(
                    {
                        "claim_id": claim_id,
                        "reason_code": EXCLUDED_UNSUPPORTED_RELATION,
                    }
                )
            elif not is_finite_number(raw_score):
                excluded.append(
                    {
                        "claim_id": claim_id,
                        "reason_code": EXCLUDED_INVALID_MATCH_SCORE,
                    }
                )
            else:
                qualifying.append(
                    {
                        "claim_id": claim_id,
                        "match_score": clamp_percent(raw_score, 0.0, 1.0),
                        "evidence": evidence_text,
                        "source_agent_output_id": (
                            str(record.get("source_agent_output_id"))
                            if record.get("source_agent_output_id")
                            else None
                        ),
                        "agent": (
                            str(record.get("agent")) if record.get("agent") else None
                        ),
                    }
                )

        excluded.extend(
            {"claim_id": claim_id, "reason_code": EXCLUDED_DUPLICATE_CLAIM}
            for _ in range(duplicate_counts.get(claim_id, 0))
        )

    qualifying.sort(key=lambda c: c["claim_id"])
    excluded.sort(key=lambda c: (c["claim_id"] or "", c["reason_code"]))
    return _EvidenceResult(
        qualifying=qualifying,
        excluded=excluded,
        ambiguous_only=(
            not qualifying and relevant_count > 0 and only_ambiguous_exclusions
        ),
    )


def _mean_match_score(qualifying_claims: list[dict[str, Any]]) -> float:
    if not qualifying_claims:
        return 0.0
    return sum(c["match_score"] for c in qualifying_claims) / len(qualifying_claims)


# ---------------------------------------------------------------------------
# Identity (run_id/ticker) consistency
# ---------------------------------------------------------------------------


def _embedded_identity_mismatch(
    run_id: str,
    ticker: str,
    activation_payload: Mapping[str, Any],
    alpha_matches: Sequence[Mapping[str, Any]],
) -> str | None:
    """Defensive check: if any input happens to carry its own run_id/ticker
    (e.g. a caller passed database rows, which -- unlike the JSON artifact
    match records -- do carry a run_id column per row) and it disagrees with
    the run_id/ticker parameters, the whole call is a data-integrity
    problem, not a per-candidate one. Returns the first mismatch reason
    found, or None. The current real Week 2 JSON artifact shape never
    embeds either field per-record, so this is a no-op for the real
    pipeline and only fires for adversarial/synthetic input.
    """
    embedded_run_id = activation_payload.get("run_id") if isinstance(activation_payload, Mapping) else None
    if embedded_run_id not in (None, "") and str(embedded_run_id) != run_id:
        return REASON_RUN_ID_MISMATCH
    embedded_ticker = activation_payload.get("ticker") if isinstance(activation_payload, Mapping) else None
    if embedded_ticker not in (None, "") and str(embedded_ticker) != ticker:
        return REASON_TICKER_MISMATCH

    for record in alpha_matches:
        if not isinstance(record, Mapping):
            continue
        record_run_id = record.get("run_id")
        if record_run_id not in (None, "") and str(record_run_id) != run_id:
            return REASON_RUN_ID_MISMATCH
        record_ticker = record.get("ticker")
        if record_ticker not in (None, "") and str(record_ticker) != ticker:
            return REASON_TICKER_MISMATCH
    return None


# ---------------------------------------------------------------------------
# Candidate evaluation
# ---------------------------------------------------------------------------


def _classify_outcome(reason_codes: list[str]) -> str:
    if any(code in REJECTED_CLASS_REASONS for code in reason_codes):
        return "rejected"
    return "suppressed"


def _evidence_audit_side(alpha_id: str, evidence: _EvidenceResult) -> dict[str, Any]:
    return {
        "alpha_id": alpha_id,
        "qualifying_claim_ids": [claim["claim_id"] for claim in evidence.qualifying],
        "qualifying_count": len(evidence.qualifying),
        "excluded": evidence.excluded,
        "excluded_count": len(evidence.excluded),
    }


def _candidate_evidence_audit(
    alpha_a: str,
    alpha_b: str,
    evidence_a: _EvidenceResult,
    evidence_b: _EvidenceResult,
) -> dict[str, Any]:
    return {
        "alpha_a": _evidence_audit_side(alpha_a, evidence_a),
        "alpha_b": _evidence_audit_side(alpha_b, evidence_b),
    }


def _evaluate_candidate(
    alpha_a: str,
    alpha_b: str,
    contradiction_weight: float | None,
    pair_reason_codes: Sequence[str],
    *,
    activations_by_id: Mapping[str, Mapping[str, Any]],
    alpha_matches: Sequence[Mapping[str, Any]],
    duplicate_counts: Mapping[str, int],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Evaluate exactly one canonical candidate pair.

    Returns ``(audit_item, conflict_or_none)``. ``conflict_or_none`` is the
    full admitted-conflict dict (see ``detect_alpha_conflicts``'s output
    schema) when, and only when, ``audit_item["outcome"] == "admitted"``.
    """
    evidence_a = _gather_qualifying_evidence(alpha_a, alpha_matches, duplicate_counts)
    evidence_b = _gather_qualifying_evidence(alpha_b, alpha_matches, duplicate_counts)
    evidence_audit = _candidate_evidence_audit(alpha_a, alpha_b, evidence_a, evidence_b)
    reason_codes = list(pair_reason_codes)

    weight_ok = is_finite_number(contradiction_weight) and 0.0 <= float(contradiction_weight) <= 1.0
    if not weight_ok and not reason_codes:
        reason_codes.append(REASON_INVALID_CONTRADICTION_WEIGHT)

    entry_a = activations_by_id.get(alpha_a)
    entry_b = activations_by_id.get(alpha_b)
    if entry_a is None:
        reason_codes.append(REASON_MISSING_LEFT_ACTIVATION)
    if entry_b is None:
        reason_codes.append(REASON_MISSING_RIGHT_ACTIVATION)

    if entry_a is None or entry_b is None or not weight_ok or pair_reason_codes:
        reason_codes = dedupe_stable(reason_codes)
        return (
            _audit_item(
                alpha_a,
                alpha_b,
                _classify_outcome(reason_codes),
                reason_codes,
                evidence_audit,
            ),
            None,
        )

    fields_a = _extract_activation_fields(entry_a, alpha_a)
    fields_b = _extract_activation_fields(entry_b, alpha_b)
    reason_codes.extend(fields_a.reason_codes)
    reason_codes.extend(fields_b.reason_codes)

    if fields_a.score is None or fields_b.score is None:
        reason_codes = dedupe_stable(reason_codes)
        return (
            _audit_item(
                alpha_a,
                alpha_b,
                _classify_outcome(reason_codes),
                reason_codes,
                evidence_audit,
            ),
            None,
        )

    if fields_a.status not in ADMISSIBLE_STATUSES or fields_b.status not in ADMISSIBLE_STATUSES:
        reason_codes.append(REASON_BELOW_ACTIVATION_THRESHOLD)

    qualifying_a = evidence_a.qualifying
    qualifying_b = evidence_b.qualifying
    if not qualifying_a:
        reason_codes.append(
            REASON_AMBIGUOUS_ONLY
            if evidence_a.ambiguous_only
            else REASON_MISSING_LEFT_EVIDENCE
        )
    if not qualifying_b:
        reason_codes.append(
            REASON_AMBIGUOUS_ONLY
            if evidence_b.ambiguous_only
            else REASON_MISSING_RIGHT_EVIDENCE
        )

    strength_a_raw = _mean_match_score(qualifying_a)
    strength_b_raw = _mean_match_score(qualifying_b)
    evidence_strength_raw = (strength_a_raw + strength_b_raw) / 2.0
    if evidence_strength_raw <= 0.0:
        reason_codes.append(REASON_ZERO_EVIDENCE_STRENGTH)

    bull_id, bear_id = resolve_bull_bear(alpha_a, fields_a.direction, alpha_b, fields_b.direction)
    if bull_id is None:
        reason_codes.append(REASON_DIRECTION_ROLE_UNRESOLVED)

    reason_codes = dedupe_stable(reason_codes)
    if reason_codes:
        return (
            _audit_item(
                alpha_a,
                alpha_b,
                _classify_outcome(reason_codes),
                reason_codes,
                evidence_audit,
            ),
            None,
        )

    # Fully admitted: every condition satisfied.
    bull_fields, bull_qualifying = (fields_a, qualifying_a) if bull_id == alpha_a else (fields_b, qualifying_b)
    bear_fields, bear_qualifying = (fields_b, qualifying_b) if bull_id == alpha_a else (fields_a, qualifying_a)

    minimum_activation = min(fields_a.score, fields_b.score)
    conflict_score_raw = minimum_activation * float(contradiction_weight) * evidence_strength_raw
    score_public = clamp_percent(conflict_score_raw)
    level = conflict_level(score_public)

    components = {
        "activation_a": round(fields_a.score, 4),
        "activation_b": round(fields_b.score, 4),
        "minimum_activation": round(minimum_activation, 4),
        "contradiction_weight": round(float(contradiction_weight), 4),
        "alpha_a_evidence_strength": round(strength_a_raw, 4),
        "alpha_b_evidence_strength": round(strength_b_raw, 4),
        "evidence_strength": round(evidence_strength_raw, 4),
    }

    explanation = _build_explanation(bull_fields.name, bear_fields.name, level)

    conflict = {
        "conflict_id": conflict_id(alpha_a, alpha_b),
        "alpha_a": alpha_a,
        "alpha_b": alpha_b,
        "bull_alpha_id": bull_id,
        "bear_alpha_id": bear_id,
        "bull_structure": _structure_block(bull_id, bull_fields, "positive", bull_qualifying),
        "bear_structure": _structure_block(bear_id, bear_fields, "negative", bear_qualifying),
        "components": components,
        "alpha_a_strength": round(strength_a_raw, 4),
        "alpha_b_strength": round(strength_b_raw, 4),
        "evidence_strength": round(evidence_strength_raw, 4),
        "conflict_score": score_public,
        "conflict_level": level,
        "reason_codes": [],
        "explanation": explanation,
        # Internal (unrounded) sort keys -- never displayed as "the" score,
        # kept alongside so main-conflict arbitration never re-derives them
        # from the rounded public values (display rounding must not be able
        # to change the ranking).
        "_sort_conflict_score": conflict_score_raw,
        "_sort_evidence_strength": evidence_strength_raw,
        "_sort_minimum_activation": minimum_activation,
    }
    return _audit_item(alpha_a, alpha_b, "admitted", [], evidence_audit), conflict


def _structure_block(alpha_id: str, fields: _ActivationFields, direction: str, qualifying: list[dict[str, Any]]):
    return {
        "alpha_id": alpha_id,
        "alpha_name": fields.name,
        "activation_score": round(fields.score, 4),
        "status": fields.status,
        "direction": direction,
        "claim_ids": [c["claim_id"] for c in qualifying],
        "source_agent_output_ids": sorted(
            {c["source_agent_output_id"] for c in qualifying if c["source_agent_output_id"]}
        ),
        "agents": sorted({c["agent"] for c in qualifying if c["agent"]}),
        "evidence": [c["evidence"] for c in qualifying],
        "match_scores": [c["match_score"] for c in qualifying],
    }


def _build_explanation(bull_name: str, bear_name: str, level: str) -> str:
    return (
        f"{bull_name} and {bear_name} present a bull-vs-bear structural "
        f"tension in this run's Structure Graph, currently assessed at "
        f"{level} conflict level."
    )


def _audit_item(
    alpha_a: str,
    alpha_b: str,
    outcome: str,
    reason_codes: list[str],
    evidence_audit: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "alpha_a": alpha_a,
        "alpha_b": alpha_b,
        "outcome": outcome,
        "reason_codes": reason_codes,
        "evidence_audit": dict(evidence_audit),
    }


def _audit_without_evaluation(
    alpha_a: str,
    alpha_b: str,
    outcome: str,
    reason_codes: list[str],
    alpha_matches: Sequence[Mapping[str, Any]],
    duplicate_counts: Mapping[str, int],
) -> dict[str, Any]:
    evidence_a = _gather_qualifying_evidence(alpha_a, alpha_matches, duplicate_counts)
    evidence_b = _gather_qualifying_evidence(alpha_b, alpha_matches, duplicate_counts)
    return _audit_item(
        alpha_a,
        alpha_b,
        outcome,
        reason_codes,
        _candidate_evidence_audit(alpha_a, alpha_b, evidence_a, evidence_b),
    )


# ---------------------------------------------------------------------------
# Main-conflict arbitration
# ---------------------------------------------------------------------------


def _conflict_sort_key(conflict: Mapping[str, Any]) -> tuple[float, float, float, str]:
    # Main-Conflict Arbitration (APPROVED -- SPEC-FROZEN FOR W4.1, audit #12):
    # conflict_score desc, evidence_strength desc, minimum_activation desc,
    # canonical conflict ID asc. Negate the first three for a single
    # ascending sort.
    return (
        -conflict["_sort_conflict_score"],
        -conflict["_sort_evidence_strength"],
        -conflict["_sort_minimum_activation"],
        conflict["conflict_id"],
    )


def _finalize_conflict(conflict: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in conflict.items() if not key.startswith("_sort_")}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def detect_alpha_conflicts(
    *,
    run_id: str,
    ticker: str,
    activation_payload: Mapping[str, Any],
    alpha_matches: Sequence[Mapping[str, Any]],
    taxonomy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Deterministically evaluate every taxonomy-declared conflict pair for one run.

    Pure function: no filesystem/database/network/environment/randomness/
    wall-clock reads. Raises :class:`ConflictInputError` only for a
    structural contract violation of the whole call (empty run_id/ticker, a
    non-mapping activation_payload, alpha_matches not a sequence, a
    duplicate alpha_id within activation_payload). Everything else -- a
    specific pair lacking evidence, an alpha below threshold, an
    unresolvable bull/bear role -- is reported gracefully as a
    ``suppressed``/``rejected`` candidate in the returned dict, never an
    exception.
    """
    if not isinstance(run_id, str) or not run_id.strip():
        raise ConflictInputError("SCHEMA_INVALID")
    if not isinstance(ticker, str) or not ticker.strip():
        raise ConflictInputError("SCHEMA_INVALID")
    if not isinstance(alpha_matches, Sequence) or isinstance(alpha_matches, (str, bytes)):
        raise ConflictInputError("SCHEMA_INVALID")

    if taxonomy is None:
        taxonomy = load_alpha_taxonomy()
    declared_pairs = _enumerate_canonical_pairs(taxonomy)
    activations_by_id = _index_activations(activation_payload, set(taxonomy))
    canonical_matches, duplicate_counts = _canonicalize_alpha_matches(alpha_matches)

    mismatch_reason = _embedded_identity_mismatch(
        run_id, ticker, activation_payload, canonical_matches
    )
    if mismatch_reason is not None:
        candidate_evaluations = [
            _audit_without_evaluation(
                pair.alpha_a,
                pair.alpha_b,
                "rejected",
                [mismatch_reason],
                canonical_matches,
                duplicate_counts,
            )
            for pair in declared_pairs
        ]
        return _assemble_result(
            run_id,
            ticker,
            declared_pairs,
            [],
            candidate_evaluations,
            activation_formula_version=str(activation_payload.get("formula_version")),
        )

    candidate_evaluations: list[dict[str, Any]] = []
    admitted_conflicts: list[dict[str, Any]] = []
    for pair in declared_pairs:
        audit_item, conflict = _evaluate_candidate(
            pair.alpha_a,
            pair.alpha_b,
            pair.contradiction_weight,
            pair.reason_codes,
            activations_by_id=activations_by_id,
            alpha_matches=canonical_matches,
            duplicate_counts=duplicate_counts,
        )
        candidate_evaluations.append(audit_item)
        if conflict is not None:
            admitted_conflicts.append(conflict)

    admitted_conflicts.sort(key=_conflict_sort_key)
    return _assemble_result(
        run_id,
        ticker,
        declared_pairs,
        admitted_conflicts,
        candidate_evaluations,
        activation_formula_version=str(activation_payload.get("formula_version")),
    )


def _assemble_result(
    run_id: str,
    ticker: str,
    declared_pairs: list[_DeclaredPair],
    admitted_conflicts: list[dict[str, Any]],
    candidate_evaluations: list[dict[str, Any]],
    activation_formula_version: str | None = None,
) -> dict[str, Any]:
    conflicts = [_finalize_conflict(c) for c in admitted_conflicts]
    main_conflict = conflicts[0] if conflicts else None

    # candidate_evaluations is already emitted in declared_pairs' canonical
    # (alpha_a, alpha_b) sorted order (see _enumerate_canonical_pairs), so it
    # needs no further sorting to be stable/order-independent.
    suppressed_count = sum(1 for c in candidate_evaluations if c["outcome"] == "suppressed")
    rejected_count = sum(1 for c in candidate_evaluations if c["outcome"] == "rejected")

    return {
        "schema_version": CONFLICT_SCHEMA_VERSION,
        "formula_version": CONFLICT_FORMULA_VERSION,
        "activation_formula_version": activation_formula_version,
        "run_id": run_id,
        "ticker": ticker,
        "conflicts": conflicts,
        "main_conflict": main_conflict,
        "arbitration": {
            "declared_pair_count": len(declared_pairs),
            "admitted_count": len(conflicts),
            "suppressed_count": suppressed_count,
            "rejected_count": rejected_count,
            "candidate_evaluations": candidate_evaluations,
        },
    }


def evaluate_conflict_pair(
    alpha_id_1: str,
    alpha_id_2: str,
    *,
    activation_payload: Mapping[str, Any],
    alpha_matches: Sequence[Mapping[str, Any]],
    taxonomy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Optional single-pair evaluation helper.

    Evaluates exactly one candidate pair without needing the full six-pair
    enumeration. If the pair is not taxonomy-declared at all, returns a
    ``rejected`` audit item with ``PAIR_NOT_DECLARED`` -- the one situation
    that reason code exists for, since ``detect_alpha_conflicts`` itself
    never evaluates an undeclared pair in the first place.
    """
    if taxonomy is None:
        taxonomy = load_alpha_taxonomy()
    declared_pairs = {
        (pair.alpha_a, pair.alpha_b): pair for pair in _enumerate_canonical_pairs(taxonomy)
    }
    activations_by_id = _index_activations(activation_payload, set(taxonomy))
    canonical_matches, duplicate_counts = _canonicalize_alpha_matches(alpha_matches)
    alpha_a, alpha_b = canonical_pair_key(alpha_id_1, alpha_id_2)

    if (alpha_a, alpha_b) not in declared_pairs:
        return _audit_without_evaluation(
            alpha_a,
            alpha_b,
            "rejected",
            [REASON_PAIR_NOT_DECLARED],
            canonical_matches,
            duplicate_counts,
        )

    pair = declared_pairs[(alpha_a, alpha_b)]
    audit_item, conflict = _evaluate_candidate(
        alpha_a,
        alpha_b,
        pair.contradiction_weight,
        pair.reason_codes,
        activations_by_id=activations_by_id,
        alpha_matches=canonical_matches,
        duplicate_counts=duplicate_counts,
    )
    if conflict is not None:
        return {**audit_item, "conflict": _finalize_conflict(conflict)}
    return audit_item


__all__ = ["detect_alpha_conflicts", "evaluate_conflict_pair"]
