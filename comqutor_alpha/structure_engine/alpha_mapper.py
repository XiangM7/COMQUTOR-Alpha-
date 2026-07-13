"""Deterministic Week 2 alpha mapper for structured COMQUTOR claims."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.alpha_library.alpha_schema import AlphaDefinition
from comqutor_alpha.storage.file_store import load_json_record, save_json_record
from comqutor_alpha.structure_engine.claim_semantics import (
    OPPORTUNITY_ALPHA_IDS,
    RISK_ALPHA_IDS,
    alpha_relation,
    analyze_claim_semantics,
    semantic_score_for_relation,
)
from comqutor_alpha.structure_engine.factor_normalizer import (
    extract_known_factors_from_text,
    normalize_factor_label,
    normalize_text,
    term_in_text,
)
from comqutor_alpha.structure_engine.structure_schema import clamp_score, normalize_direction


SCHEMA_VERSION = "week2.alpha_matches.v1"
DEFAULT_MIN_MATCH_SCORE = 0.38
DEFAULT_AMBIGUITY_DELTA = 0.14
DEFAULT_SECONDARY_DELTA = 0.25
DEFAULT_CLASSIFIER_TIMEOUT_SECONDS = 5.0
MAX_CLASSIFIER_CANDIDATES = 3

POSITIVE_ALPHA_IDS = OPPORTUNITY_ALPHA_IDS

GENERIC_KEYWORD_WEIGHTS = {
    "ai": 0.35,
    "gpu": 0.35,
    "nvidia": 0.20,
    "nvda": 0.20,
    "chip": 0.35,
    "revenue": 0.35,
    "valuation": 0.50,
    "recession": 0.50,
    "inference": 0.55,
    "momentum": 0.45,
    "datacenter": 0.55,
    "data center": 0.55,
    "capex": 0.45,
}

# Weights for each factor's contribution to the alpha score.
FACTOR_ALPHA_WEIGHTS = {
    "AI Demand": {"A101": 1.0, "A301": 0.45, "A601": 0.25},
    "AI CapEx": {"A101": 0.85, "A103": 0.75, "A301": 0.35},
    "GPU Demand": {"A101": 0.85, "A301": 0.75, "A201": 0.35},
    "Datacenter CapEx": {"A103": 1.0, "A101": 0.35},
    "AI Infrastructure": {"A103": 1.0, "A301": 0.35, "A101": 0.25},
    "Revenue Growth": {"A301": 1.0, "A101": 0.25},
    "Valuation Risk": {"A304": 1.0},
    "Recession Risk": {"A501": 1.0},
    "Liquidity Expansion": {"A003": 1.0, "A001": 0.25},
    "Narrative Momentum": {"A601": 1.0},
    "Semiconductor Cycle": {"A201": 1.0, "A301": 0.25},
    "Rate Cut Cycle": {"A001": 1.0, "A003": 0.2},
    "Inference Demand": {"A102": 1.0, "A101": 0.25},
}

# Iterate over text values, normalizing them.
def _iter_text_values(values: Iterable[Any]) -> list[str]:
    return [str(item) for item in values if str(item or "").strip()]

# Extract alpha terms from an AlphaDefinition.
def _alpha_terms(alpha: AlphaDefinition) -> list[tuple[str, float]]:
    terms: list[tuple[str, float]] = []
    terms.extend((term, 1.0) for term in alpha.keywords)
    terms.extend((term, 0.85) for term in alpha.trigger_signals)
    terms.extend((term, 0.75) for term in alpha.confirmation_signals)
    terms.extend((term, 0.35) for term in (alpha.name_en, alpha.core_thesis))
    return [(term, weight) for term, weight in terms if str(term).strip()]

# Compute the keyword score for a claim against an alpha definition.
def keyword_score(claim: str, alpha: AlphaDefinition) -> float:
    """Score direct phrase evidence between a claim and one alpha definition."""
    text = normalize_text(claim)
    if not text:
        return 0.0

    matched_weight = 0.0
    for term, weight in _alpha_terms(alpha):
        normalized_term = normalize_text(term)
        if term_in_text(normalized_term, text):
            specificity = GENERIC_KEYWORD_WEIGHTS.get(normalized_term, 1.0)
            matched_weight += weight * specificity

    # One highly specific term should matter, while many repeated taxonomy terms
    # should not make every AI sentence a perfect match.
    return clamp_score(matched_weight / 2.6)


def _record_factors(record: Mapping[str, Any]) -> list[str]:
    # Explicit record factors may be raw aliases ("AI demand", "artificial
    # intelligence demand") rather than the canonical label, so normalize
    # them the same way claim text is normalized instead of dropping them.
    raw_factors = _iter_text_values(record.get("factors") or [])
    candidate_factors = [normalize_factor_label(factor) for factor in raw_factors]
    candidate_factors.extend(extract_known_factors_from_text(str(record.get("claim") or "")))

    seen = set()
    normalized = []
    for factor in candidate_factors:
        if factor in FACTOR_ALPHA_WEIGHTS and factor not in seen:
            normalized.append(factor)
            seen.add(factor)
    return normalized

# Compute the factor score for a claim against an alpha definition.
def factor_score(record: Mapping[str, Any], alpha: AlphaDefinition) -> float:
    """Score explicit factor compatibility between a structured claim and an alpha."""
    scores = []
    for factor in _record_factors(record):
        weight = FACTOR_ALPHA_WEIGHTS.get(factor, {}).get(alpha.alpha_id)
        if weight is not None:
            scores.append(float(weight))
    if not scores:
        return 0.0
    return clamp_score(max(scores))

# Compute the direction score for a claim against an alpha definition.
def direction_score(record: Mapping[str, Any], alpha: AlphaDefinition) -> float:
    direction = normalize_direction(record.get("direction"))
    relation = alpha_relation(record.get("claim"), alpha.alpha_id)
    if relation == "risk_relief" and alpha.alpha_id in RISK_ALPHA_IDS:
        return 1.0
    if relation == "invalidation" and alpha.alpha_id in POSITIVE_ALPHA_IDS:
        return 1.0
    if relation == "conditional":
        return 0.65
    if relation == "mention":
        return 0.0
    if direction == "positive" and alpha.alpha_id in POSITIVE_ALPHA_IDS:
        return 1.0
    if direction == "negative" and alpha.alpha_id in RISK_ALPHA_IDS:
        return 1.0
    if direction == "neutral":
        return 0.35
    return 0.0

# Compute the overall candidate score for a claim against an alpha definition.
def _candidate_score(record: Mapping[str, Any], alpha: AlphaDefinition) -> dict[str, Any]:
    claim = str(record.get("claim") or "")
    keyword = keyword_score(claim, alpha)
    factor = factor_score(record, alpha)
    direction = direction_score(record, alpha)
    relation = alpha_relation(claim, alpha.alpha_id)
    semantic = semantic_score_for_relation(relation) if keyword > 0 or factor > 0 else 0.0
    semantics = analyze_claim_semantics(claim)
    eligible = keyword > 0 or factor > 0
    rejection_reason = None
    if relation == "mention":
        eligible = False
        rejection_reason = "candidate is only mentioned or appears in an unmapped context"
    elif semantics.taxonomy_gap_context == "technical_market_state" and factor == 0:
        eligible = False
        rejection_reason = "technical market state is outside the MVP-10 taxonomy"

    score = clamp_score(
        (0.50 * keyword)
        + (0.30 * factor)
        + (0.08 * direction)
        + (0.12 * semantic)
    )
    return {
        "alpha_id": alpha.alpha_id,
        "alpha_name": alpha.name_en,
        "score": score,
        "keyword_score": keyword,
        "factor_score": factor,
        "direction_score": direction,
        "semantic_score": semantic,
        "relation": relation,
        "eligible": eligible,
        "rejection_reason": rejection_reason,
    }

# Sort candidate scores by descending score and ascending alpha_id for tie-breaking.
def _sort_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        candidates,
        key=lambda item: (not item.get("eligible", False), -item["score"], item["alpha_id"]),
    )

# Extract the set of conflicting alpha IDs for a given alpha definition.
def _conflict_ids(alpha: AlphaDefinition) -> set[str]:
    return {conflict.alpha_id for conflict in alpha.conflict_alphas}


def _directions_oppose(left_id: str, right_id: str) -> bool:
    return (left_id in POSITIVE_ALPHA_IDS and right_id in RISK_ALPHA_IDS) or (
        left_id in RISK_ALPHA_IDS and right_id in POSITIVE_ALPHA_IDS
    )


def _candidate_implication(candidate: Mapping[str, Any]) -> str:
    alpha_id = str(candidate.get("alpha_id") or "")
    relation = str(candidate.get("relation") or "")
    if relation == "mixed":
        return "mixed"
    if alpha_id in RISK_ALPHA_IDS:
        return "positive" if relation == "risk_relief" else "negative"
    if alpha_id in POSITIVE_ALPHA_IDS:
        return "negative" if relation == "invalidation" else "positive"
    return "unknown"


def _classifier_metadata(enabled: bool, status: str, used: bool = False) -> dict[str, Any]:
    return {"enabled": bool(enabled), "used": bool(used), "status": status}


def _apply_optional_classifier(
    result: dict[str, Any],
    record: Mapping[str, Any],
    taxonomy: Mapping[str, AlphaDefinition],
    classifier: Callable[..., Mapping[str, Any]] | None,
    classifier_enabled: bool,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Apply an injected classifier that enforces the supplied timeout.

    Provider adapters must raise ``TimeoutError`` when that deadline expires.
    No provider object, raw response, exception text, or credentials are added
    to the returned artifact.
    """
    if not classifier_enabled:
        result["classifier"] = _classifier_metadata(False, "disabled")
        return result
    if result["match_status"] == "no_match":
        result["classifier"] = _classifier_metadata(True, "blocked_by_deterministic_no_match")
        return result
    if result["match_status"] != "ambiguous":
        result["classifier"] = _classifier_metadata(True, "not_needed")
        return result
    if classifier is None:
        result["classifier"] = _classifier_metadata(True, "unavailable")
        return result

    candidates = [
        {
            "alpha_id": item["alpha_id"],
            "alpha_name": item["alpha_name"],
            "score": item["score"],
            "relation": item["relation"],
        }
        for item in result.get("eligible_candidates", [])[:MAX_CLASSIFIER_CANDIDATES]
    ]
    allowed_ids = {item["alpha_id"] for item in candidates}
    request = {
        "claim": str(record.get("claim") or ""),
        "direction": normalize_direction(record.get("direction")),
        "allowed_alpha_ids": sorted(allowed_ids),
        "candidates": candidates,
    }

    try:
        response = classifier(request, timeout_seconds=timeout_seconds)
    except TimeoutError:
        result["classifier"] = _classifier_metadata(True, "timeout", used=True)
        return result
    except Exception:
        result["classifier"] = _classifier_metadata(True, "error", used=True)
        return result

    if not isinstance(response, Mapping):
        result["classifier"] = _classifier_metadata(True, "invalid_output", used=True)
        return result

    status = str(response.get("match_status") or "").strip().lower()
    alpha_id = str(response.get("alpha_id") or "").strip()
    if status == "matched" and alpha_id in allowed_ids:
        alpha = taxonomy[alpha_id]
        selected = next(
            item for item in result["eligible_candidates"] if item["alpha_id"] == alpha_id
        )
        result.update(
            {
                "matched_alpha": alpha_id,
                "matched_alpha_name": alpha.name_en,
                "match_status": "matched",
                "score": selected["score"],
                "keyword_score": selected["keyword_score"],
                "factor_score": selected["factor_score"],
                "direction_score": selected["direction_score"],
                "reason": "optional classifier selected from deterministic eligible candidates",
                "secondary_alphas": [
                    item["alpha_id"] for item in candidates if item["alpha_id"] != alpha_id
                ],
            }
        )
        result["classifier"] = _classifier_metadata(True, "applied", used=True)
        return result
    if status == "ambiguous" and not alpha_id:
        result["classifier"] = _classifier_metadata(True, "confirmed_ambiguous", used=True)
        return result
    if status == "no_match" and not alpha_id:
        result.update(
            {
                "matched_alpha": None,
                "matched_alpha_name": None,
                "match_status": "no_match",
                "reason": "optional classifier declined all deterministic eligible candidates",
                "secondary_alphas": [],
            }
        )
        result["classifier"] = _classifier_metadata(True, "applied", used=True)
        return result

    result["classifier"] = _classifier_metadata(True, "invalid_output", used=True)
    return result

# Map a structured claim record to the best matching alpha definition, returning a detailed match result.
def map_claim_to_alpha(
    record: Mapping[str, Any],
    taxonomy: Mapping[str, AlphaDefinition] | None = None,
    *,
    min_score: float = DEFAULT_MIN_MATCH_SCORE,
    ambiguity_delta: float = DEFAULT_AMBIGUITY_DELTA,
    classifier: Callable[..., Mapping[str, Any]] | None = None,
    classifier_enabled: bool = False,
    classifier_timeout_seconds: float = DEFAULT_CLASSIFIER_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    taxonomy = taxonomy or load_alpha_taxonomy()
    candidates = _sort_candidates([_candidate_score(record, alpha) for alpha in taxonomy.values()])
    eligible_candidates = [
        item for item in candidates if item.get("eligible") and item["score"] >= min_score
    ]
    top = eligible_candidates[0] if eligible_candidates else None
    second = eligible_candidates[1] if len(eligible_candidates) > 1 else None
    semantics = analyze_claim_semantics(record.get("claim"))

    status = "no_match"
    reason = "top score below minimum match threshold"
    matched_alpha = None
    matched_alpha_name = None

    if top:
        conflicting_close = False
        opposing_pair = False
        if second is not None:
            top_alpha = taxonomy[top["alpha_id"]]
            second_id = second["alpha_id"]
            top_implication = _candidate_implication(top)
            second_implication = _candidate_implication(second)
            semantic_opposition = {top_implication, second_implication} == {
                "positive",
                "negative",
            }
            taxonomy_opposition = second_id in _conflict_ids(top_alpha) or _directions_oppose(
                top["alpha_id"], second_id
            )
            opposing_pair = semantic_opposition or (semantics.mixed and taxonomy_opposition)
            conflicting_close = (
                opposing_pair
                and top["score"] - second["score"] <= (ambiguity_delta + 0.08)
            )
        explicit_mixed_conflict = bool(semantics.mixed and second and opposing_pair)
        if conflicting_close or explicit_mixed_conflict:
            status = "ambiguous"
            reason = "opposing alpha candidates are too close to force a single match"
        else:
            status = "matched"
            reason = "top eligible alpha passed semantic and score checks"
            matched_alpha = top["alpha_id"]
            matched_alpha_name = top["alpha_name"]
    elif any(item["score"] >= min_score for item in candidates):
        reason = "high-scoring candidates were rejected as mention-only or outside taxonomy"

    plausible_candidates = eligible_candidates[:3]
    secondary_alphas = []
    if top and status == "matched":
        secondary_alphas = [
            item["alpha_id"]
            for item in plausible_candidates[1:]
            if top["score"] - item["score"] <= DEFAULT_SECONDARY_DELTA
        ]

    result = {
        "run_id": record.get("run_id"),
        "ticker": record.get("ticker"),
        "agent": record.get("agent"),
        "source_agent_output_id": record.get("source_agent_output_id")
        or record.get("agent_output_id"),
        "claim": record.get("claim"),
        "direction": normalize_direction(record.get("direction")),
        "matched_alpha": matched_alpha,
        "matched_alpha_name": matched_alpha_name,
        "score": top["score"] if top else 0.0,
        "keyword_score": top["keyword_score"] if top else 0.0,
        "factor_score": top["factor_score"] if top else 0.0,
        "direction_score": top["direction_score"] if top else 0.0,
        "candidate_scores": candidates[:5],
        "eligible_candidates": plausible_candidates,
        "plausible_alphas": [item["alpha_id"] for item in plausible_candidates],
        "secondary_alphas": secondary_alphas,
        "match_status": status,
        "reason": reason,
        "assertion_status": semantics.assertion_status,
        "semantic_polarity": semantics.semantic_polarity,
        "taxonomy_gap_context": semantics.taxonomy_gap_context,
    }
    return _apply_optional_classifier(
        result,
        record,
        taxonomy,
        classifier,
        classifier_enabled,
        classifier_timeout_seconds,
    )

# Map a list of structured claim records to their best matching alpha definitions, returning a list of match results.
def map_structured_records(
    records: Iterable[Mapping[str, Any]],
    taxonomy: Mapping[str, AlphaDefinition] | None = None,
    *,
    classifier: Callable[..., Mapping[str, Any]] | None = None,
    classifier_enabled: bool = False,
    classifier_timeout_seconds: float = DEFAULT_CLASSIFIER_TIMEOUT_SECONDS,
) -> list[dict[str, Any]]:
    taxonomy = taxonomy or load_alpha_taxonomy()
    results = []
    for record in records:
        if not isinstance(record, Mapping) or str(record.get("claim") or "").lower() == "unknown":
            continue
        results.append(
            map_claim_to_alpha(
                record,
                taxonomy,
                classifier=classifier,
                classifier_enabled=classifier_enabled,
                classifier_timeout_seconds=classifier_timeout_seconds,
            )
        )
    return results

# Build the final alpha matches payload from structured agent outputs, including metadata and match results.
def build_alpha_matches_payload(
    structured_payload: Mapping[str, Any],
    taxonomy: Mapping[str, AlphaDefinition] | None = None,
    *,
    classifier: Callable[..., Mapping[str, Any]] | None = None,
    classifier_enabled: bool = False,
    classifier_timeout_seconds: float = DEFAULT_CLASSIFIER_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    taxonomy = taxonomy or load_alpha_taxonomy()
    records = structured_payload.get("records", [])
    if not isinstance(records, list):
        records = []
    return {
        "schema_version": SCHEMA_VERSION,
        "mapper_version": "week2.semantic_mapper.v2",
        "run_id": structured_payload.get("run_id"),
        "ticker": structured_payload.get("ticker"),
        "matches": map_structured_records(
            records,
            taxonomy,
            classifier=classifier,
            classifier_enabled=classifier_enabled,
            classifier_timeout_seconds=classifier_timeout_seconds,
        ),
    }

# Save the alpha matches for a given run ID, loading structured agent outputs and saving the resulting matches payload.
def save_alpha_matches(
    run_id,
    output_root="outputs/runs",
    *,
    classifier: Callable[..., Mapping[str, Any]] | None = None,
    classifier_enabled: bool = False,
    classifier_timeout_seconds: float = DEFAULT_CLASSIFIER_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    structured_payload = load_json_record(
        run_id,
        "structured_agent_outputs.json",
        output_root=output_root,
    )
    payload = build_alpha_matches_payload(
        structured_payload,
        classifier=classifier,
        classifier_enabled=classifier_enabled,
        classifier_timeout_seconds=classifier_timeout_seconds,
    )
    save_json_record(run_id, "alpha_matches.json", payload, output_root=output_root)
    return payload
