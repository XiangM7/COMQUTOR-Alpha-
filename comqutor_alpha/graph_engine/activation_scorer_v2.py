"""Activation v2: evidence-local-structure scorer.

Frozen specification: ``activation.v2.evidence_local_structure.v1``.

Six components (weights sum to exactly 1.0):

    EvidenceQuality        35%
    AgentIndependence      20%
    LocalStructureSupport  20%
    TickerSpecificity      10%
    Recency                10%
    DirectionConsistency    5%

Design goals relative to Activation v1 (which is preserved unchanged in
``activation_scorer.py``):

- semantic deduplication: one independent fact counts once for
  EvidenceQuality no matter how many agents repeat it (agent provenance is
  preserved separately in AgentIndependence);
- alpha-local structure support: only graph edges whose ``claim_ids``
  intersect this alpha's own qualifying claims count -- a global coherence
  score can never lift an alpha with no structural support of its own;
- explicit score caps with stable reason codes;
- an explicit regime qualification gate above the score bands.

Deterministic and order-independent: every aggregation is keyed by a
canonical identity and sorted before summation/serialization. NaN/Infinity
inputs are rejected per-claim/per-edge (recorded as evidence integrity
warnings), never propagated into a score.

No ticker-specific branches: every constant below applies to every ticker.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from typing import Any

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.alpha_library.alpha_schema import AlphaDefinition
from comqutor_alpha.graph_engine.graph_schema import (
    MVP_ALPHA_IDS,
    clamp_percent,
    is_finite_number,
)
from comqutor_alpha.structure_engine.claim_semantics import RISK_ALPHA_IDS

ACTIVATION_V2_FORMULA_VERSION = "activation.v2.evidence_local_structure.v1"

ACTIVATION_V2_WEIGHTS = {
    "evidence_quality": 0.35,
    "agent_independence": 0.20,
    "local_structure_support": 0.20,
    "ticker_specificity": 0.10,
    "recency": 0.10,
    "direction_consistency": 0.05,
}

# EvidenceQuality
EVIDENCE_QUALITY_SATURATION = 4.0
QUALIFYING_RELATIONS = frozenset({"activation", "conditional", "mixed"})
RELATION_WEIGHTS = {"activation": 1.00, "conditional": 0.65, "mixed": 0.40}
ASSERTION_WEIGHTS = {"asserted": 1.00, "conditional": 0.70, "mixed": 0.50, "negated": 0.00}

# AgentIndependence
AGENT_COVERAGE_DENOMINATOR = 3
CROSS_AGENT_CONFIRMATION_DENOMINATOR = 2
AGENT_COVERAGE_SHARE = 0.70
CROSS_AGENT_CONFIRMATION_SHARE = 0.30

# LocalStructureSupport
LOCAL_STRUCTURE_SATURATION = 2.0
EDGE_CONTRIBUTIONS = {
    ("causal", "asserted"): 1.00,
    ("supportive", "asserted"): 0.80,
    ("causal", "conditional"): 0.50,
    ("supportive", "conditional"): 0.40,
    ("causal", "mixed"): 0.25,
    ("supportive", "mixed"): 0.25,
}

# Recency (same deterministic decay as v1)
RECENCY_DECAY_WINDOW_DAYS = 90
RECENCY_FALLBACK_SCORE = 50.0

# DirectionConsistency
DIRECTION_SIGNED_RELATIONS = {
    "activation": 1.0,
    "conditional": 0.4,
    "mixed": 0.0,
    "invalidation": -1.0,
    "risk_relief": -1.0,
}

# Score caps (value, stable reason code). "eligible_cap" is the minimum of
# every cap whose trigger condition holds; it is reported even when it does
# not actually reduce the score (see cap_was_binding below) -- an eligible
# ceiling is not the same claim as "this score was capped."
CAP_INSUFFICIENT_UNIQUE_EVIDENCE = (60.0, "INSUFFICIENT_UNIQUE_EVIDENCE")
CAP_INSUFFICIENT_AGENT_INDEPENDENCE = (70.0, "INSUFFICIENT_AGENT_INDEPENDENCE")
CAP_NO_TICKER_SPECIFIC_EVIDENCE = (60.0, "NO_TICKER_SPECIFIC_EVIDENCE")
CAP_NO_LOCAL_STRUCTURE_SUPPORT = (70.0, "NO_LOCAL_STRUCTURE_SUPPORT")
CAP_KEYWORD_ONLY_SUPPORT = (65.0, "KEYWORD_ONLY_SUPPORT")
REASON_NO_QUALIFYING_EVIDENCE = "NO_QUALIFYING_EVIDENCE"

# Regime qualification gate (applies only to scores in the regime band).
# Exactly seven gates, each with its own unique, stable reason code, checked
# and reported in this fixed order -- never a dict/set iteration order.
REGIME_GATE_MIN_SCORE = 86.0
REGIME_GATE_MIN_UNIQUE_EVIDENCE = 4
REGIME_GATE_MIN_DISTINCT_AGENTS = 3
REGIME_GATE_MIN_TICKER_SPECIFIC = 2
REGIME_GATE_MIN_LOCAL_EDGES = 1
REGIME_GATE_MIN_LOCAL_STRUCTURE_SUPPORT = 40.0

REGIME_REASON_SCORE_BELOW_THRESHOLD = "SCORE_BELOW_REGIME_THRESHOLD"
REGIME_REASON_INSUFFICIENT_UNIQUE_EVIDENCE = "INSUFFICIENT_UNIQUE_EVIDENCE_FOR_REGIME"
REGIME_REASON_INSUFFICIENT_SUPPORTING_AGENTS = "INSUFFICIENT_SUPPORTING_AGENTS_FOR_REGIME"
REGIME_REASON_INSUFFICIENT_TICKER_SPECIFIC_EVIDENCE = (
    "INSUFFICIENT_TICKER_SPECIFIC_EVIDENCE_FOR_REGIME"
)
REGIME_REASON_NO_LOCAL_STRUCTURE = "NO_LOCAL_STRUCTURE_FOR_REGIME"
REGIME_REASON_INSUFFICIENT_LOCAL_STRUCTURE_STRENGTH = (
    "INSUFFICIENT_LOCAL_STRUCTURE_STRENGTH_FOR_REGIME"
)
REGIME_REASON_EVIDENCE_INTEGRITY_WARNING = "EVIDENCE_INTEGRITY_WARNING"

# v2 status bands: 0..30 inactive, (30..50] watch, (50..70] active,
# (70..85] dominant, (85..100] regime_candidate (resolved by the gate to
# regime_level or dominant -- "regime_candidate" is never a final status).
_V2_BAND_UPPER_BOUNDS = (
    (30.0, "inactive"),
    (50.0, "watch"),
    (70.0, "active"),
    (85.0, "dominant"),
    (100.0, "regime_candidate"),
)


def activation_status_band_v2(score) -> str:
    clamped = clamp_percent(score)
    for upper_bound, status in _V2_BAND_UPPER_BOUNDS:
        if clamped <= upper_bound:
            return status
    return "regime_candidate"


# ---------------------------------------------------------------------------
# Semantic grouping helpers
# ---------------------------------------------------------------------------

_QUOTE_TRANSLATION = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "«": '"', "»": '"'})
_NUMBER_TOKEN_PATTERN = re.compile(r"\d+(?:[.,]\d+)*%?")


def _normalize_claim_text(text: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    normalized = normalized.translate(_QUOTE_TRANSLATION).lower()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.strip(" \t\"'.,;:!?()[]")


def _numeric_signature(normalized_text: str) -> str:
    return "|".join(sorted(_NUMBER_TOKEN_PATTERN.findall(normalized_text)))


def _semantic_group_key(record: Mapping[str, Any], duplicate_group_ids: Mapping[str, str]) -> str:
    claim_id = str(record.get("claim_id") or "")
    group_id = duplicate_group_ids.get(claim_id)
    if group_id:
        return f"group:{group_id}"
    normalized = _normalize_claim_text(record.get("claim") or record.get("evidence"))
    return "text:" + "\x1f".join(
        (
            normalized,
            str(record.get("assertion_status") or "unknown"),
            str(record.get("semantic_polarity") or "unknown"),
            _numeric_signature(normalized),
        )
    )


def _relation_for_match(record: Mapping[str, Any], alpha_id: str) -> str:
    for pool_key in ("eligible_candidates", "top_candidates", "candidate_scores"):
        pool = record.get(pool_key)
        if not isinstance(pool, list):
            continue
        for candidate in pool:
            if isinstance(candidate, Mapping) and str(candidate.get("alpha_id")) == alpha_id:
                return str(candidate.get("relation") or "unknown").strip().lower()
    return "unknown"


def _candidate_for_match(record: Mapping[str, Any], alpha_id: str) -> Mapping[str, Any] | None:
    for pool_key in ("eligible_candidates", "top_candidates", "candidate_scores"):
        pool = record.get(pool_key)
        if not isinstance(pool, list):
            continue
        for candidate in pool:
            if isinstance(candidate, Mapping) and str(candidate.get("alpha_id")) == alpha_id:
                return candidate
    return None


def _token_boundary_match(term: str, text: str) -> bool:
    """Whole-token match of ``term`` inside ``text`` -- never a substring."""
    term = _normalize_claim_text(term)
    if not term:
        return False
    normalized = _normalize_claim_text(text)
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", normalized) is not None


def _is_ticker_specific(
    record: Mapping[str, Any],
    ticker: str | None,
    company_names: Sequence[str],
    entities_by_claim: Mapping[str, Sequence[str]],
) -> bool:
    """A claim is ticker-specific only when it verifiably points at the
    ticker or the resolved company by name (token-boundary, never a bare
    substring). Structured-claim entity lists are consulted first, but an
    entity equal to the ticker only counts when the ticker/company actually
    appears in the claim text -- upstream extraction appends the run ticker
    to every claim's entities unconditionally, so entity presence alone is
    not evidence of specificity. Pure sector/macro statements never
    qualify."""
    text = str(record.get("claim") or record.get("evidence") or "")
    if not text:
        return False
    terms: list[str] = []
    if ticker:
        terms.append(str(ticker))
    terms.extend(str(name) for name in company_names if str(name).strip())
    claim_id = str(record.get("claim_id") or "")
    for entity in entities_by_claim.get(claim_id, ()):  # structured entities first
        entity = str(entity)
        if ticker and entity.upper() == str(ticker).upper():
            continue  # auto-appended run ticker: verified via text below
        if company_names and entity in company_names:
            terms.append(entity)
    return any(_token_boundary_match(term, text) for term in terms)


# ---------------------------------------------------------------------------
# Evidence gathering
# ---------------------------------------------------------------------------


def _gather_qualifying_evidence(
    alpha_matches_payload: Mapping[str, Any],
    alpha_id: str,
    duplicate_group_ids: Mapping[str, str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return (qualifying records, evidence integrity warnings).

    Qualifying evidence: committed match for this alpha with non-empty
    claim_id/evidence, a finite match score in [0,1], relation in
    {activation, conditional, mixed}, and assertion_status != negated.
    Deduplicated by claim_id first (repeated rows can never double count).
    """
    matches = (
        alpha_matches_payload.get("matches") if isinstance(alpha_matches_payload, Mapping) else None
    )
    if not isinstance(matches, list):
        return [], []

    warnings: list[str] = []
    by_claim_id: dict[str, dict[str, Any]] = {}
    for record in matches:
        if not isinstance(record, Mapping):
            continue
        if record.get("match_status") != "matched":
            continue
        if str(record.get("matched_alpha") or "") != alpha_id:
            continue
        claim_id = str(record.get("claim_id") or "").strip()
        evidence_text = str(record.get("evidence") or record.get("claim") or "").strip()
        if not claim_id or not evidence_text:
            continue
        score = record.get("score", None)
        if not is_finite_number(score) or not 0.0 <= float(score) <= 1.0:
            warnings.append("NON_FINITE_OR_OUT_OF_RANGE_MATCH_SCORE")
            continue
        relation = _relation_for_match(record, alpha_id)
        if relation not in QUALIFYING_RELATIONS:
            continue
        assertion_status = str(record.get("assertion_status") or "unknown").strip().lower()
        if assertion_status == "negated":
            continue
        if claim_id in by_claim_id:
            continue
        by_claim_id[claim_id] = {
            "claim_id": claim_id,
            "agent": str(record.get("agent") or "").strip(),
            "evidence": evidence_text,
            "claim": str(record.get("claim") or evidence_text),
            "match_score": float(score),
            "relation": relation,
            "assertion_status": assertion_status,
            "semantic_group": _semantic_group_key(record, duplicate_group_ids),
            "record": record,
        }
    return [by_claim_id[claim_id] for claim_id in sorted(by_claim_id)], sorted(set(warnings))


def _group_evidence(qualifying: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in qualifying:
        groups.setdefault(item["semantic_group"], []).append(item)
    return groups


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------


def _evidence_quality_component(
    groups: Mapping[str, list[dict[str, Any]]],
) -> tuple[float, dict[str, Any]]:
    contributions: list[float] = []
    for group_key in sorted(groups):
        members = groups[group_key]
        best = 0.0
        for member in members:
            contribution = (
                member["match_score"]
                * RELATION_WEIGHTS.get(member["relation"], 0.0)
                * ASSERTION_WEIGHTS.get(member["assertion_status"], 0.0)
            )
            best = max(best, contribution)
        contributions.append(best)
    unique_sum = sum(contributions)
    raw = min(100.0, unique_sum / EVIDENCE_QUALITY_SATURATION * 100.0)
    return clamp_percent(raw), {
        "unique_semantic_groups": len(groups),
        "unique_contribution_sum": round(unique_sum, 4),
        "saturation": EVIDENCE_QUALITY_SATURATION,
    }


def _agent_independence_component(
    groups: Mapping[str, list[dict[str, Any]]],
) -> tuple[float, dict[str, Any]]:
    agents = sorted({m["agent"] for members in groups.values() for m in members if m["agent"]})
    multi_agent_groups = sum(
        1
        for members in groups.values()
        if len({m["agent"] for m in members if m["agent"]}) >= 2
    )
    agent_coverage = min(len(agents) / AGENT_COVERAGE_DENOMINATOR, 1.0) * 100.0
    cross_agent_confirmation = (
        min(multi_agent_groups / CROSS_AGENT_CONFIRMATION_DENOMINATOR, 1.0) * 100.0
    )
    raw = (
        agent_coverage * AGENT_COVERAGE_SHARE
        + cross_agent_confirmation * CROSS_AGENT_CONFIRMATION_SHARE
    )
    return clamp_percent(raw), {
        "distinct_agents": len(agents),
        "agents": agents,
        "agent_coverage": round(agent_coverage, 4),
        "cross_agent_confirmed_groups": multi_agent_groups,
        "cross_agent_confirmation": round(cross_agent_confirmation, 4),
        "coverage_denominator": AGENT_COVERAGE_DENOMINATOR,
        "confirmation_denominator": CROSS_AGENT_CONFIRMATION_DENOMINATOR,
    }


def _edge_contribution(edge_type: str, assertion_status: str) -> float:
    return EDGE_CONTRIBUTIONS.get((edge_type, assertion_status), 0.0)


def _local_structure_component(
    qualifying: list[dict[str, Any]],
    graph_edges: Sequence[Mapping[str, Any]],
) -> tuple[float, dict[str, Any]]:
    alpha_claim_ids = {item["claim_id"] for item in qualifying}
    unique_edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in graph_edges or ():
        if not isinstance(edge, Mapping):
            continue
        edge_claims = {str(c) for c in (edge.get("claim_ids") or []) if str(c or "").strip()}
        if not edge_claims & alpha_claim_ids:
            continue
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        edge_type = str(edge.get("edge_type") or "unknown").strip().lower()
        assertion_status = str(edge.get("assertion_status") or "unknown").strip().lower()
        key = (source, target, edge_type)
        contribution = _edge_contribution(edge_type, assertion_status)
        existing = unique_edges.get(key)
        if existing is None or contribution > existing["contribution"]:
            unique_edges[key] = {
                "key": key,
                "assertion_status": assertion_status,
                "contribution": contribution,
                "claim_ids": edge_claims & alpha_claim_ids,
            }

    ordered = [unique_edges[key] for key in sorted(unique_edges)]
    contribution_sum = sum(edge["contribution"] for edge in ordered)
    raw = min(100.0, contribution_sum / LOCAL_STRUCTURE_SATURATION * 100.0)
    local_claim_ids = sorted({c for edge in ordered for c in edge["claim_ids"]})
    return clamp_percent(raw), {
        "local_edge_count": len(ordered),
        "asserted_local_edge_count": sum(
            1 for e in ordered if e["assertion_status"] == "asserted"
        ),
        "conditional_local_edge_count": sum(
            1 for e in ordered if e["assertion_status"] == "conditional"
        ),
        "local_edge_ids": [f"{key[0]}->{key[1]}:{key[2]}" for key in sorted(unique_edges)],
        "local_claim_ids": local_claim_ids,
        "unique_edge_contribution_sum": round(contribution_sum, 4),
        "saturation": LOCAL_STRUCTURE_SATURATION,
    }


def _ticker_specificity_component(
    groups: Mapping[str, list[dict[str, Any]]],
    *,
    ticker: str | None,
    company_names: Sequence[str],
    entities_by_claim: Mapping[str, Sequence[str]],
) -> tuple[float, dict[str, Any]]:
    total = len(groups)
    if total == 0:
        return 0.0, {
            "ticker_specific_evidence_count": 0,
            "total_unique_evidence_count": 0,
        }
    specific = 0
    for group_key in sorted(groups):
        members = groups[group_key]
        if any(
            _is_ticker_specific(m["record"], ticker, company_names, entities_by_claim)
            for m in members
        ):
            specific += 1
    raw = specific / total * 100.0
    return clamp_percent(raw), {
        "ticker_specific_evidence_count": specific,
        "total_unique_evidence_count": total,
    }


def _parse_reference_date(value: Any):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _recency_component(run_timestamp: Any, as_of: Any) -> tuple[float, dict[str, Any]]:
    run_date = _parse_reference_date(run_timestamp)
    as_of_date = _parse_reference_date(as_of) if as_of is not None else run_date
    if run_date is None or as_of_date is None:
        return RECENCY_FALLBACK_SCORE, {
            "age_days": None,
            "fallback": True,
            "reason": "missing or unparseable run_timestamp/as_of",
        }
    # A future run_timestamp is clamped to age 0: it can never score above a
    # genuinely fresh run.
    age_days = max(0, (as_of_date - run_date).days)
    raw = clamp_percent(100.0 * max(0.0, 1.0 - age_days / RECENCY_DECAY_WINDOW_DAYS))
    return raw, {
        "age_days": age_days,
        "decay_window_days": RECENCY_DECAY_WINDOW_DAYS,
        "fallback": False,
    }


def _gather_direction_evidence(
    alpha_matches_payload: Mapping[str, Any],
    alpha_id: str,
    duplicate_group_ids: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    """All committed (matched) evidence for this alpha -- including
    counter-evidence relations -- deduplicated to one entry per semantic
    group (highest match score wins within a group)."""
    matches = (
        alpha_matches_payload.get("matches") if isinstance(alpha_matches_payload, Mapping) else None
    )
    groups: dict[str, dict[str, Any]] = {}
    if not isinstance(matches, list):
        return groups
    for record in matches:
        if not isinstance(record, Mapping):
            continue
        if record.get("match_status") != "matched":
            continue
        if str(record.get("matched_alpha") or "") != alpha_id:
            continue
        score = record.get("score", None)
        if not is_finite_number(score) or not 0.0 <= float(score) <= 1.0:
            continue
        relation = _relation_for_match(record, alpha_id)
        if relation not in DIRECTION_SIGNED_RELATIONS:
            continue
        key = _semantic_group_key(record, duplicate_group_ids)
        candidate = {"relation": relation, "match_score": float(score)}
        existing = groups.get(key)
        if existing is None or candidate["match_score"] > existing["match_score"]:
            groups[key] = candidate
    return groups


def _direction_consistency_component(
    direction_groups: Mapping[str, dict[str, Any]],
) -> tuple[float, dict[str, Any]]:
    weighted_sum = 0.0
    weight_total = 0.0
    for key in sorted(direction_groups):
        entry = direction_groups[key]
        signed = DIRECTION_SIGNED_RELATIONS[entry["relation"]]
        weighted_sum += signed * entry["match_score"]
        weight_total += entry["match_score"]
    if weight_total <= 0.0:
        return 0.0, {"qualifying_group_count": 0, "weighted_signed_average": 0.0}
    average = weighted_sum / weight_total
    raw = clamp_percent((average + 1.0) / 2.0 * 100.0)
    return raw, {
        "qualifying_group_count": len(direction_groups),
        "weighted_signed_average": round(average, 4),
    }


def _direction_label_v2(direction_meta: Mapping[str, Any], alpha_id: str) -> str:
    """Market-direction label, kept separate from the numeric consistency
    score. A confirmed risk alpha (A304/A501) is bearish; risk relief on a
    risk alpha is bullish."""
    if direction_meta.get("qualifying_group_count", 0) == 0:
        return "unknown"
    average = float(direction_meta.get("weighted_signed_average", 0.0))
    is_risk = alpha_id in RISK_ALPHA_IDS
    if average > 0.15:
        return "negative" if is_risk else "positive"
    if average < -0.15:
        return "positive" if is_risk else "negative"
    return "mixed"


# ---------------------------------------------------------------------------
# Caps and regime gate
# ---------------------------------------------------------------------------


def _keyword_only_support(qualifying: list[dict[str, Any]], local_edge_count: int) -> bool:
    """True only when the match diagnostics *prove* every qualifying match
    is keyword-only (factor and semantic components present and exactly
    zero) and there is no local structure. Missing diagnostic fields mean
    "not proven" -- the cap is never applied on a guess."""
    if not qualifying or local_edge_count > 0:
        return False
    for item in qualifying:
        record = item["record"]
        factor_score = record.get("factor_score", None)
        if not is_finite_number(factor_score) or float(factor_score) != 0.0:
            return False
        keyword_score = record.get("keyword_score", None)
        if not is_finite_number(keyword_score) or float(keyword_score) <= 0.0:
            return False
        candidate = _candidate_for_match(record, str(record.get("matched_alpha")))
        if candidate is None or "semantic_score" not in candidate:
            return False
        semantic_score = candidate.get("semantic_score")
        if not is_finite_number(semantic_score) or float(semantic_score) != 0.0:
            return False
    return True


def _apply_caps(
    uncapped_score: float,
    *,
    unique_evidence_count: int,
    distinct_agents: int,
    ticker_specific_count: int,
    local_edge_count: int,
    keyword_only: bool,
) -> tuple[float, float | None, bool, list[str], list[str]]:
    """Returns (activation_score, eligible_cap, cap_was_binding,
    cap_reason_codes, binding_cap_reason_codes).

    ``eligible_cap`` is the minimum value among every cap whose condition
    holds (``None`` if none hold). ``cap_was_binding`` is true only when an
    eligible cap exists AND it actually reduced the score
    (``uncapped_score > eligible_cap``) -- an eligible ceiling above the
    uncapped score changes nothing and must never be reported as "capped."
    ``binding_cap_reason_codes`` lists only the reason codes of caps whose
    value equals ``eligible_cap`` (there may be ties), and is empty whenever
    ``cap_was_binding`` is false.
    """
    caps: list[tuple[float, str]] = []
    if unique_evidence_count < 2:
        caps.append(CAP_INSUFFICIENT_UNIQUE_EVIDENCE)
    if distinct_agents < 2:
        caps.append(CAP_INSUFFICIENT_AGENT_INDEPENDENCE)
    if ticker_specific_count == 0:
        caps.append(CAP_NO_TICKER_SPECIFIC_EVIDENCE)
    if local_edge_count == 0:
        caps.append(CAP_NO_LOCAL_STRUCTURE_SUPPORT)
    if keyword_only:
        caps.append(CAP_KEYWORD_ONLY_SUPPORT)

    if not caps:
        return uncapped_score, None, False, [], []

    eligible_cap = min(value for value, _reason in caps)
    cap_reason_codes = [reason for _value, reason in sorted(caps)]
    cap_was_binding = uncapped_score > eligible_cap
    if cap_was_binding:
        activation_score = min(uncapped_score, eligible_cap)
        binding_cap_reason_codes = sorted(
            reason for value, reason in caps if value == eligible_cap
        )
    else:
        activation_score = uncapped_score
        binding_cap_reason_codes = []
    return activation_score, eligible_cap, cap_was_binding, cap_reason_codes, binding_cap_reason_codes


def _evaluate_regime_gate(
    *,
    activation_score: float,
    unique_evidence_count: int,
    distinct_agents: int,
    ticker_specific_count: int,
    local_edge_count: int,
    local_structure_raw: float,
    integrity_warnings: Sequence[str],
) -> tuple[bool, list[str]]:
    """Evaluate the seven frozen regime-qualification gates, in this exact
    fixed order (never a dict/set iteration order):

    1. activation_score >= 86
    2. unique_evidence_count >= 4
    3. distinct_supporting_agents >= 3
    4. ticker_specific_evidence_count >= 2
    5. local_edge_count >= 1
    6. LocalStructureSupport raw score >= 40
    7. no evidence integrity warning

    Each has exactly one stable reason code; there is no synonym for any
    gate. All seven pass => regime_gate_passed=True, regime_gate_failures=[].
    """
    failures: list[str] = []
    if activation_score < REGIME_GATE_MIN_SCORE:
        failures.append(REGIME_REASON_SCORE_BELOW_THRESHOLD)
    if unique_evidence_count < REGIME_GATE_MIN_UNIQUE_EVIDENCE:
        failures.append(REGIME_REASON_INSUFFICIENT_UNIQUE_EVIDENCE)
    if distinct_agents < REGIME_GATE_MIN_DISTINCT_AGENTS:
        failures.append(REGIME_REASON_INSUFFICIENT_SUPPORTING_AGENTS)
    if ticker_specific_count < REGIME_GATE_MIN_TICKER_SPECIFIC:
        failures.append(REGIME_REASON_INSUFFICIENT_TICKER_SPECIFIC_EVIDENCE)
    if local_edge_count < REGIME_GATE_MIN_LOCAL_EDGES:
        failures.append(REGIME_REASON_NO_LOCAL_STRUCTURE)
    if local_structure_raw < REGIME_GATE_MIN_LOCAL_STRUCTURE_SUPPORT:
        failures.append(REGIME_REASON_INSUFFICIENT_LOCAL_STRUCTURE_STRENGTH)
    if integrity_warnings:
        failures.append(REGIME_REASON_EVIDENCE_INTEGRITY_WARNING)
    return (not failures), failures


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _duplicate_group_index(structured_records: Iterable[Mapping[str, Any]] | None) -> dict[str, str]:
    index: dict[str, str] = {}
    for record in structured_records or ():
        if not isinstance(record, Mapping):
            continue
        claim_id = str(record.get("claim_id") or "")
        group_id = record.get("duplicate_group_id")
        if claim_id and isinstance(group_id, str) and group_id.strip():
            index[claim_id] = group_id.strip()
    return index


def _entities_index(
    structured_records: Iterable[Mapping[str, Any]] | None,
) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for record in structured_records or ():
        if not isinstance(record, Mapping):
            continue
        claim_id = str(record.get("claim_id") or "")
        entities = record.get("entities")
        if claim_id and isinstance(entities, list):
            index[claim_id] = [str(e) for e in entities if str(e or "").strip()]
    return index


def score_alpha_v2(
    alpha_id: str,
    alpha_matches_payload: Mapping[str, Any],
    taxonomy: Mapping[str, AlphaDefinition],
    *,
    graph_edges: Sequence[Mapping[str, Any]] = (),
    ticker: str | None = None,
    company_names: Sequence[str] = (),
    structured_records: Iterable[Mapping[str, Any]] | None = None,
    run_timestamp: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Score exactly one MVP alpha under Activation v2."""
    alpha_def = taxonomy.get(alpha_id)
    duplicate_group_ids = _duplicate_group_index(structured_records)
    entities_by_claim = _entities_index(structured_records)

    qualifying, integrity_warnings = _gather_qualifying_evidence(
        alpha_matches_payload, alpha_id, duplicate_group_ids
    )
    groups = _group_evidence(qualifying)

    evidence_quality_raw, evidence_quality_meta = _evidence_quality_component(groups)
    agent_independence_raw, agent_meta = _agent_independence_component(groups)
    local_raw, local_meta = _local_structure_component(qualifying, graph_edges)
    ticker_raw, ticker_meta = _ticker_specificity_component(
        groups,
        ticker=ticker,
        company_names=company_names,
        entities_by_claim=entities_by_claim,
    )
    recency_raw, recency_meta = _recency_component(run_timestamp, as_of)
    direction_groups = _gather_direction_evidence(
        alpha_matches_payload, alpha_id, duplicate_group_ids
    )
    direction_raw, direction_meta = _direction_consistency_component(direction_groups)

    has_qualifying_evidence = len(groups) > 0
    # Recency is a run-level signal: with no qualifying evidence its
    # contribution is zero (and the whole score is zero anyway).
    recency_contribution = (
        round(recency_raw * ACTIVATION_V2_WEIGHTS["recency"], 4) if has_qualifying_evidence else 0.0
    )

    components = {
        "evidence_quality": {
            "raw": evidence_quality_raw,
            "weight": ACTIVATION_V2_WEIGHTS["evidence_quality"],
            "contribution": round(
                evidence_quality_raw * ACTIVATION_V2_WEIGHTS["evidence_quality"], 4
            ),
            **evidence_quality_meta,
        },
        "agent_independence": {
            "raw": agent_independence_raw,
            "weight": ACTIVATION_V2_WEIGHTS["agent_independence"],
            "contribution": round(
                agent_independence_raw * ACTIVATION_V2_WEIGHTS["agent_independence"], 4
            ),
            **agent_meta,
        },
        "local_structure_support": {
            "raw": local_raw,
            "weight": ACTIVATION_V2_WEIGHTS["local_structure_support"],
            "contribution": round(local_raw * ACTIVATION_V2_WEIGHTS["local_structure_support"], 4),
            **local_meta,
        },
        "ticker_specificity": {
            "raw": ticker_raw,
            "weight": ACTIVATION_V2_WEIGHTS["ticker_specificity"],
            "contribution": round(ticker_raw * ACTIVATION_V2_WEIGHTS["ticker_specificity"], 4),
            **ticker_meta,
        },
        "recency": {
            "raw": recency_raw,
            "weight": ACTIVATION_V2_WEIGHTS["recency"],
            "contribution": recency_contribution,
            "evidence_gated": not has_qualifying_evidence,
            **recency_meta,
        },
        "direction_consistency": {
            "raw": direction_raw,
            "weight": ACTIVATION_V2_WEIGHTS["direction_consistency"],
            "contribution": round(
                direction_raw * ACTIVATION_V2_WEIGHTS["direction_consistency"], 4
            ),
            **direction_meta,
        },
    }

    unique_evidence_count = len(groups)
    distinct_agents = agent_meta["distinct_agents"]
    ticker_specific_count = ticker_meta["ticker_specific_evidence_count"]
    local_edge_count = local_meta["local_edge_count"]

    uncapped_score = clamp_percent(sum(c["contribution"] for c in components.values()))

    cap_reason_codes: list[str]
    binding_cap_reason_codes: list[str]
    if not has_qualifying_evidence:
        activation_score = 0.0
        uncapped_score = 0.0
        eligible_cap = None
        cap_was_binding = False
        cap_reason_codes = [REASON_NO_QUALIFYING_EVIDENCE]
        binding_cap_reason_codes = []
    else:
        keyword_only = _keyword_only_support(qualifying, local_edge_count)
        (
            activation_score,
            eligible_cap,
            cap_was_binding,
            cap_reason_codes,
            binding_cap_reason_codes,
        ) = _apply_caps(
            uncapped_score,
            unique_evidence_count=unique_evidence_count,
            distinct_agents=distinct_agents,
            ticker_specific_count=ticker_specific_count,
            local_edge_count=local_edge_count,
            keyword_only=keyword_only,
        )
    activation_score = clamp_percent(activation_score)

    band = activation_status_band_v2(activation_score)
    regime_gate_passed = False
    regime_gate_failures: list[str] = []
    if band == "regime_candidate":
        regime_gate_passed, regime_gate_failures = _evaluate_regime_gate(
            activation_score=activation_score,
            unique_evidence_count=unique_evidence_count,
            distinct_agents=distinct_agents,
            ticker_specific_count=ticker_specific_count,
            local_edge_count=local_edge_count,
            local_structure_raw=local_raw,
            integrity_warnings=integrity_warnings,
        )
        status = "regime_level" if regime_gate_passed else "dominant"
    else:
        status = "inactive" if not has_qualifying_evidence else band

    direction = _direction_label_v2(direction_meta, alpha_id)
    evidence_texts = sorted({item["evidence"] for item in qualifying if item["evidence"]})
    claim_ids = sorted({item["claim_id"] for item in qualifying})

    return {
        "alpha_id": alpha_id,
        "alpha_name": alpha_def.name_en if alpha_def else alpha_id,
        "formula_version": ACTIVATION_V2_FORMULA_VERSION,
        "activation_score": activation_score,
        "uncapped_score": uncapped_score,
        "eligible_cap": eligible_cap,
        "cap_was_binding": cap_was_binding,
        "cap_reason_codes": cap_reason_codes,
        "binding_cap_reason_codes": binding_cap_reason_codes,
        "status": status,
        "direction": direction,
        "components": components,
        "evidence_count": unique_evidence_count,
        "unique_evidence_count": unique_evidence_count,
        "distinct_supporting_agents": distinct_agents,
        "ticker_specific_evidence_count": ticker_specific_count,
        "local_edge_count": local_edge_count,
        "regime_gate_passed": regime_gate_passed,
        "regime_gate_failures": regime_gate_failures,
        "evidence_integrity_warnings": list(integrity_warnings),
        "claim_ids": claim_ids,
        "evidence": evidence_texts,
        "reason_codes": list(cap_reason_codes),
    }


def score_alpha_activations_v2(
    alpha_matches_payload: Mapping[str, Any],
    *,
    graph_edges: Sequence[Mapping[str, Any]] = (),
    ticker: str | None = None,
    company_names: Sequence[str] = (),
    structured_records: Iterable[Mapping[str, Any]] | None = None,
    taxonomy: Mapping[str, AlphaDefinition] | None = None,
    run_timestamp: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Score every MVP-10 alpha under Activation v2. Deterministic and
    order-independent; adding a graph edge unrelated to an alpha's own
    qualifying claims never changes that alpha's score."""
    taxonomy = taxonomy or load_alpha_taxonomy()
    structured_records = list(structured_records or ())
    alphas = [
        score_alpha_v2(
            alpha_id,
            alpha_matches_payload,
            taxonomy,
            graph_edges=graph_edges,
            ticker=ticker,
            company_names=company_names,
            structured_records=structured_records,
            run_timestamp=run_timestamp,
            as_of=as_of,
        )
        for alpha_id in sorted(MVP_ALPHA_IDS)
    ]
    dominant = [a for a in alphas if a["status"] in ("dominant", "regime_level")]
    dominant.sort(key=lambda a: (-a["activation_score"], a["alpha_id"]))
    return {
        "formula_version": ACTIVATION_V2_FORMULA_VERSION,
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


__all__ = [
    "ACTIVATION_V2_FORMULA_VERSION",
    "ACTIVATION_V2_WEIGHTS",
    "activation_status_band_v2",
    "score_alpha_v2",
    "score_alpha_activations_v2",
]
