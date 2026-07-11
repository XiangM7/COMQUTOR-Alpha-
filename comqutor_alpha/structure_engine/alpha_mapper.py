"""Deterministic Week 2 alpha mapper for structured COMQUTOR claims."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.alpha_library.alpha_schema import AlphaDefinition
from comqutor_alpha.storage.file_store import load_json_record, save_json_record
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

POSITIVE_ALPHA_IDS = {"A001", "A003", "A101", "A102", "A103", "A201", "A301", "A601"}
RISK_ALPHA_IDS = {"A304", "A501"}

# Weights for each factor's contribution to the alpha score.
FACTOR_ALPHA_WEIGHTS = {
    "AI Demand": {"A101": 1.0, "A301": 0.45, "A601": 0.25},
    "AI CapEx": {"A101": 0.85, "A103": 0.75, "A301": 0.35},
    "GPU Demand": {"A101": 0.85, "A301": 0.75, "A201": 0.35},
    "Datacenter CapEx": {"A103": 1.0, "A101": 0.35},
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
            matched_weight += weight

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
    score = clamp_score((0.58 * keyword) + (0.34 * factor) + (0.08 * direction))
    return {
        "alpha_id": alpha.alpha_id,
        "alpha_name": alpha.name_en,
        "score": score,
        "keyword_score": keyword,
        "factor_score": factor,
        "direction_score": direction,
    }

# Sort candidate scores by descending score and ascending alpha_id for tie-breaking.
def _sort_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(candidates, key=lambda item: (-item["score"], item["alpha_id"]))

# Extract the set of conflicting alpha IDs for a given alpha definition.
def _conflict_ids(alpha: AlphaDefinition) -> set[str]:
    return {conflict.alpha_id for conflict in alpha.conflict_alphas}

# Map a structured claim record to the best matching alpha definition, returning a detailed match result.
def map_claim_to_alpha(
    record: Mapping[str, Any],
    taxonomy: Mapping[str, AlphaDefinition] | None = None,
    *,
    min_score: float = DEFAULT_MIN_MATCH_SCORE,
    ambiguity_delta: float = DEFAULT_AMBIGUITY_DELTA,
) -> dict[str, Any]:
    taxonomy = taxonomy or load_alpha_taxonomy()
    candidates = _sort_candidates([_candidate_score(record, alpha) for alpha in taxonomy.values()])
    top = candidates[0] if candidates else None
    second = candidates[1] if len(candidates) > 1 else None

    status = "no_match"
    reason = "top score below minimum match threshold"
    matched_alpha = None
    matched_alpha_name = None

    if top and top["score"] >= min_score:
        too_close = second is not None and second["score"] >= min_score and (
            top["score"] - second["score"] <= ambiguity_delta
        )
        conflicting_close = False
        if second is not None:
            top_alpha = taxonomy[top["alpha_id"]]
            second_id = second["alpha_id"]
            conflicting_close = (
                second["score"] >= min_score
                and second_id in _conflict_ids(top_alpha)
                and top["score"] - second["score"] <= (ambiguity_delta + 0.08)
            )
        if too_close or conflicting_close:
            status = "ambiguous"
            reason = "top alpha candidates are too close to force a single match"
        else:
            status = "matched"
            reason = "top alpha score passed threshold and separation checks"
            matched_alpha = top["alpha_id"]
            matched_alpha_name = top["alpha_name"]

    return {
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
        "match_status": status,
        "reason": reason,
    }

# Map a list of structured claim records to their best matching alpha definitions, returning a list of match results.
def map_structured_records(
    records: Iterable[Mapping[str, Any]],
    taxonomy: Mapping[str, AlphaDefinition] | None = None,
) -> list[dict[str, Any]]:
    taxonomy = taxonomy or load_alpha_taxonomy()
    results = []
    for record in records:
        if not isinstance(record, Mapping) or str(record.get("claim") or "").lower() == "unknown":
            continue
        results.append(map_claim_to_alpha(record, taxonomy))
    return results

# Build the final alpha matches payload from structured agent outputs, including metadata and match results.
def build_alpha_matches_payload(
    structured_payload: Mapping[str, Any],
    taxonomy: Mapping[str, AlphaDefinition] | None = None,
) -> dict[str, Any]:
    taxonomy = taxonomy or load_alpha_taxonomy()
    records = structured_payload.get("records", [])
    if not isinstance(records, list):
        records = []
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": structured_payload.get("run_id"),
        "ticker": structured_payload.get("ticker"),
        "matches": map_structured_records(records, taxonomy),
    }

# Save the alpha matches for a given run ID, loading structured agent outputs and saving the resulting matches payload.
def save_alpha_matches(run_id, output_root="outputs/runs") -> dict[str, Any]:
    structured_payload = load_json_record(
        run_id,
        "structured_agent_outputs.json",
        output_root=output_root,
    )
    payload = build_alpha_matches_payload(structured_payload)
    save_json_record(run_id, "alpha_matches.json", payload, output_root=output_root)
    return payload
