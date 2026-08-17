"""Week 2 alpha mapping with deterministic admissibility and optional LLM selection."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from comqutor_alpha.alpha_library.alpha_loader import build_keyword_index, load_alpha_taxonomy
from comqutor_alpha.alpha_library.alpha_schema import AlphaDefinition
from comqutor_alpha.storage.file_store import load_json_record, save_json_record
from comqutor_alpha.structure_engine.ai_alpha_discriminator import (
    AI_ALPHA_IDS,
    AiAlphaGateResult,
    evaluate_ai_alpha_gates,
)
from comqutor_alpha.structure_engine.claim_quality import (
    CONSUMER_MAPPING,
    is_claim_eligible,
)
from comqutor_alpha.structure_engine.claim_semantics import (
    OPPORTUNITY_ALPHA_IDS,
    RISK_ALPHA_IDS,
    alpha_relation,
    analyze_claim_semantics,
    semantic_score_for_relation,
)
from comqutor_alpha.structure_engine.evidence_stance import (
    CLASSIFIER_VERSION as EVIDENCE_STANCE_VERSION,
    classify_evidence_stance,
)
from comqutor_alpha.structure_engine.evidence_stance_llm import apply_llm_stance_upgrade
from comqutor_alpha.structure_engine.factor_normalizer import (
    extract_known_factors_from_text,
    normalize_factor_label,
    normalize_text,
    term_in_text,
)
from comqutor_alpha.structure_engine.structure_schema import clamp_score, normalize_direction
from comqutor_alpha.structure_engine.week2_llm import call_with_timeout

SCHEMA_VERSION = "week2.alpha_matches.v2"
MAPPER_VERSION = "week2.alpha_mapper.v2"
DEFAULT_MIN_MATCH_SCORE = 0.35
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


def _record_text(record: Mapping[str, Any]) -> str:
    claim = str(record.get("claim") or "").strip()
    evidence = str(record.get("evidence") or "").strip()
    if not evidence or normalize_text(evidence) == normalize_text(claim):
        return claim
    return f"{claim} {evidence}"

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


def _indexed_keyword_matches(
    text: str,
    keyword_index: Mapping[str, set[str]],
) -> dict[str, list[str]]:
    normalized = normalize_text(text)
    matches: dict[str, list[str]] = {}
    for term, alpha_ids in keyword_index.items():
        if not term_in_text(term, normalized):
            continue
        for alpha_id in alpha_ids:
            matches.setdefault(alpha_id, []).append(term)
    return {alpha_id: sorted(set(terms)) for alpha_id, terms in matches.items()}


def _record_factors(record: Mapping[str, Any]) -> list[str]:
    # Explicit record factors may be raw aliases ("AI demand", "artificial
    # intelligence demand") rather than the canonical label, so normalize
    # them the same way claim text is normalized instead of dropping them.
    raw_factors = _iter_text_values(record.get("factors") or [])
    candidate_factors = [normalize_factor_label(factor) for factor in raw_factors]
    candidate_factors.extend(extract_known_factors_from_text(_record_text(record)))

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
    relation = alpha_relation(_record_text(record), alpha.alpha_id)
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
def _candidate_score(
    record: Mapping[str, Any],
    alpha: AlphaDefinition,
    keyword_matches: Mapping[str, list[str]],
    ai_gate_results: Mapping[str, AiAlphaGateResult] | None = None,
) -> dict[str, Any]:
    text = _record_text(record)
    keyword = keyword_score(text, alpha)
    factor = factor_score(record, alpha)
    direction = direction_score(record, alpha)
    relation = alpha_relation(text, alpha.alpha_id)
    semantic = semantic_score_for_relation(relation) if keyword > 0 or factor > 0 else 0.0
    semantics = analyze_claim_semantics(text)
    matched_factors = [
        factor_name
        for factor_name in _record_factors(record)
        if alpha.alpha_id in FACTOR_ALPHA_WEIGHTS.get(factor_name, {})
    ]
    matched_keywords = keyword_matches.get(alpha.alpha_id, [])

    # AI Alpha Mapper Discrimination Sprint: for A101/A102/A103, the
    # independent hard gate (a dedicated anchor phrase plus a locally
    # co-occurring change predicate) is the authoritative eligibility
    # signal, replacing the generic keyword/factor recall check for these
    # three Alphas only. Generic AI/cloud/capex/datacenter terms and the
    # taxonomy's cross-weighted FACTOR_ALPHA_WEIGHTS credit still feed the
    # *score* below exactly as before, but can never by themselves grant
    # admission. Every other Alpha's eligibility logic is completely
    # unchanged.
    ai_gate_passed = None
    if alpha.alpha_id in AI_ALPHA_IDS:
        gate = (ai_gate_results or {}).get(alpha.alpha_id)
        ai_gate_passed = bool(gate and gate.passed)
        eligible = ai_gate_passed
        rejection_reason = None
        if relation == "mention":
            eligible = False
            rejection_reason = "candidate is only mentioned or appears in an unmapped context"
        elif not ai_gate_passed:
            rejection_reason = (
                "AI alpha hard gate not satisfied: missing an alpha-specific "
                "anchor phrase with a locally co-occurring change predicate"
            )
    else:
        eligible = bool(matched_keywords) or factor > 0
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
        "matched_keywords": matched_keywords,
        "matched_factors": matched_factors,
        # Additive diagnostic only: null for every non-AI alpha, and for
        # A101/A102/A103 records whether the independent hard gate passed.
        "ai_gate_passed": ai_gate_passed,
    }

# Sprint 2 (Alpha-Relative Evidence Stance Classification), Track B1: attach
# the shadow Evidence Stance verdict onto every candidate dict IN PLACE, once
# per (claim, alpha) pair, so candidate_scores/top_candidates/eligible_
# candidates -- all list slices of these SAME dict objects -- read the
# identical result rather than each re-classifying independently ("不得分别
# 重新分类导致结果漂移"). Purely additive keys; never reads or writes score,
# eligible, relation, or any other admission/scoring field.
def _attach_evidence_stance(
    candidates: list[dict[str, Any]],
    stance_record: Mapping[str, Any],
    taxonomy: Mapping[str, AlphaDefinition],
) -> None:
    for candidate in candidates:
        stance = classify_evidence_stance(
            record=stance_record,
            target_alpha_id=candidate["alpha_id"],
            candidate=candidate,
            taxonomy=taxonomy,
        )
        candidate["evidence_stance"] = stance.evidence_stance
        candidate["counter_alpha_id"] = stance.counter_alpha_id
        candidate["stance_reason_codes"] = list(stance.stance_reason_codes)
        candidate["stance_confidence_band"] = stance.stance_confidence_band
        candidate["requires_manual_review"] = stance.requires_manual_review
        candidate["evidence_stance_version"] = EVIDENCE_STANCE_VERSION
        # B1 LLM upgrade (Sprint 2 follow-on): default provenance for every
        # stance-bearing candidate is "deterministic, LLM never attempted".
        # apply_llm_stance_upgrade() below overwrites these two fields only
        # for the <=3 retained-scope candidates it actually processes.
        candidate["stance_method"] = None
        candidate["stance_fallback_reason"] = None


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
    llm_gateway: Any = None,
) -> dict[str, Any]:
    """Apply selection only after deterministic candidate admissibility."""
    if not classifier_enabled:
        result["classifier"] = _classifier_metadata(False, "disabled")
        return result
    if result["match_status"] == "no_match":
        result["classifier"] = _classifier_metadata(True, "blocked_by_deterministic_no_match")
        return result
    if len(result.get("eligible_candidates", [])) < 2:
        result["classifier"] = _classifier_metadata(True, "not_needed")
        return result
    if classifier is None and llm_gateway is None:
        result["classifier"] = _classifier_metadata(True, "unavailable")
        return result

    candidates = [
        {
            "alpha_id": item["alpha_id"],
            "alpha_name": item["alpha_name"],
            "score": item["score"],
            "relation": item["relation"],
            "score_components": {
                "keyword": item["keyword_score"],
                "factor": item["factor_score"],
                "direction": item["direction_score"],
                "semantic": item["semantic_score"],
            },
            "matched_keywords": item.get("matched_keywords", []),
            "matched_factors": item.get("matched_factors", []),
            "taxonomy": {
                "core_thesis": taxonomy[item["alpha_id"]].core_thesis,
                "trigger_signals": taxonomy[item["alpha_id"]].trigger_signals,
                "confirmation_signals": taxonomy[item["alpha_id"]].confirmation_signals,
            },
        }
        for item in result.get("eligible_candidates", [])[:MAX_CLASSIFIER_CANDIDATES]
    ]
    allowed_ids = {item["alpha_id"] for item in candidates}
    request = {
        "claim": str(record.get("claim") or ""),
        "evidence": str(record.get("evidence") or ""),
        "factors": _record_factors(record),
        "direction": normalize_direction(record.get("direction")),
        "allowed_alpha_ids": sorted(allowed_ids),
        "candidates": candidates,
    }

    try:
        if llm_gateway is not None:
            def validate_response(payload):
                if set(payload) != {"decision", "selected_alpha_id"}:
                    raise ValueError("classifier response has unexpected fields")
                decision = str(payload.get("decision") or "").strip().lower()
                selected_alpha_id = payload.get("selected_alpha_id")
                if decision == "defer" and selected_alpha_id in (None, ""):
                    return {"match_status": "ambiguous", "alpha_id": ""}
                selected_alpha_id = str(selected_alpha_id or "").strip()
                if decision == "select" and selected_alpha_id in allowed_ids:
                    return {"match_status": "matched", "alpha_id": selected_alpha_id}
                raise ValueError("classifier response violates the candidate contract")

            if getattr(llm_gateway, "semantic_runtime", None) is None or not callable(
                getattr(llm_gateway, "invoke_json_with_trace", None)
            ):
                response = llm_gateway.invoke_json(
                    "alpha_classifier",
                    request,
                    validate_response,
                )
            else:
                invocation = llm_gateway.invoke_json_with_trace(
                    "alpha_classifier",
                    request,
                    validate_response,
                )
                if invocation.validation_accepted:
                    llm_gateway.finalize_semantic_invocation(invocation, accepted=True)
                    response = invocation.validated_output
                else:
                    llm_gateway.finalize_semantic_invocation(
                        invocation,
                        accepted=False,
                        fallback_reason=(
                            invocation.error_code or "WEEK2_LLM_ALPHA_CLASSIFIER_FALLBACK"
                        ),
                    )
                    response = None
            if response is None:
                result["classifier"] = _classifier_metadata(True, "fallback", used=True)
                return result
        else:
            response = call_with_timeout(
                lambda: classifier(request, timeout_seconds=timeout_seconds),
                timeout_seconds,
            )
    except TimeoutError:
        result["classifier"] = _classifier_metadata(True, "timeout", used=True)
        return result
    except Exception:
        result["classifier"] = _classifier_metadata(True, "error", used=True)
        return result

    if not isinstance(response, Mapping):
        result["classifier"] = _classifier_metadata(True, "invalid_output", used=True)
        return result
    if set(response) != {"match_status", "alpha_id"}:
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
        result.update(
            {
                "matched_alpha": None,
                "matched_alpha_name": None,
                "match_status": "ambiguous",
                "reason": "optional classifier deferred among admissible candidates",
                "secondary_alphas": [],
            }
        )
        result["classifier"] = _classifier_metadata(True, "confirmed_ambiguous", used=True)
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
    llm_gateway: Any = None,
) -> dict[str, Any]:
    taxonomy = taxonomy or load_alpha_taxonomy()
    text = _record_text(record)
    keyword_matches = _indexed_keyword_matches(text, build_keyword_index(taxonomy))
    # Computed once per claim (not once per alpha): the three AI Alpha hard
    # gates are independent of each other and of every other alpha in the
    # taxonomy, and never consult a taxonomy relation graph -- Alpha
    # relations remain exclusively a Structure Graph concept, never a
    # Mapper propagation mechanism.
    ai_gate_results = evaluate_ai_alpha_gates(text)
    candidates = _sort_candidates(
        [
            _candidate_score(record, alpha, keyword_matches, ai_gate_results)
            for alpha in taxonomy.values()
        ]
    )
    # For A101/A102/A103, the independent hard gate (boolean) is the
    # complete admission decision -- min_score was calibrated for the old
    # keyword/factor recall mechanism these three Alphas no longer use for
    # eligibility, and re-applying it here would silently reopen exactly
    # the weak-recall gap this Sprint closes. Every other Alpha keeps the
    # unchanged `eligible and score >= min_score` requirement.
    eligible_candidates = [
        item
        for item in candidates
        if item.get("eligible") and (item["alpha_id"] in AI_ALPHA_IDS or item["score"] >= min_score)
    ]
    top = eligible_candidates[0] if eligible_candidates else None
    second = eligible_candidates[1] if len(eligible_candidates) > 1 else None
    semantics = analyze_claim_semantics(_record_text(record))

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

    # Sprint 2, Track B1: classify Evidence Stance for every candidate now
    # that `matched_alpha` is known (needed for the supports_counter_alpha
    # check) -- attaches additive fields onto the SAME dict objects that
    # candidate_scores/top_candidates/eligible_candidates below reference,
    # so every view reads one identical, non-drifting result per candidate.
    # `candidates` is sorted eligible-first (see _sort_candidates), so
    # eligible_candidates is always a prefix of it -- classifying
    # candidates[:max(5, len(eligible_candidates))] fully covers
    # candidate_scores (candidates[:5]), top_candidates (candidates[:3]),
    # and eligible_candidates without wastefully classifying every one of
    # the taxonomy's other alphas for every single claim.
    stance_scope = max(5, len(eligible_candidates))
    _attach_evidence_stance(
        candidates[:stance_scope],
        {**record, "matched_alpha": matched_alpha},
        taxonomy,
    )
    matched_candidate = next(
        (item for item in candidates if item["alpha_id"] == matched_alpha), None
    ) if (status == "matched" and matched_alpha) else None

    result = {
        "run_id": record.get("run_id"),
        "ticker": record.get("ticker"),
        "agent": record.get("agent"),
        "claim_id": record.get("claim_id") or record.get("agent_output_id"),
        "source_agent_output_id": record.get("source_agent_output_id")
        or record.get("agent_output_id"),
        "claim": record.get("claim"),
        "evidence": record.get("evidence"),
        "factors": _record_factors(record),
        "direction": normalize_direction(record.get("direction")),
        "matched_alpha": matched_alpha,
        "matched_alpha_name": matched_alpha_name,
        "score": top["score"] if top else 0.0,
        "keyword_score": top["keyword_score"] if top else 0.0,
        "factor_score": top["factor_score"] if top else 0.0,
        "direction_score": top["direction_score"] if top else 0.0,
        "candidate_scores": candidates[:5],
        "top_candidates": candidates[:3],
        "eligible_candidates": plausible_candidates,
        "plausible_alphas": [item["alpha_id"] for item in plausible_candidates],
        "secondary_alphas": secondary_alphas,
        "match_status": status,
        "reason": reason,
        "assertion_status": semantics.assertion_status,
        "semantic_polarity": semantics.semantic_polarity,
        "taxonomy_gap_context": semantics.taxonomy_gap_context,
        # Additive diagnostic (Independent Multi-Match): every AI Alpha
        # (A101/A102/A103) that independently passed its own hard gate AND
        # cleared min_score, regardless of which one is the single top
        # `matched_alpha`. Existing consumers reading `matched_alpha`/
        # `secondary_alphas` are unaffected -- this is a new field only.
        "ai_alpha_matches": sorted(
            item["alpha_id"] for item in eligible_candidates if item["alpha_id"] in AI_ALPHA_IDS
        ),
        # Sprint 2, Track B1: the matched Alpha's own Evidence Stance
        # verdict, copied from the same candidate dict candidate_scores/
        # top_candidates/eligible_candidates already carry -- null (not a
        # fabricated default) whenever match_status != "matched", per spec
        # section 10 ("candidate-level stance必须仍存在，matched_evidence_
        # stance可以为null").
        "matched_evidence_stance": matched_candidate["evidence_stance"] if matched_candidate else None,
        "matched_counter_alpha_id": matched_candidate["counter_alpha_id"] if matched_candidate else None,
        "matched_stance_reason_codes": matched_candidate["stance_reason_codes"] if matched_candidate else None,
        "matched_stance_confidence_band": matched_candidate["stance_confidence_band"] if matched_candidate else None,
        "matched_stance_requires_manual_review": (
            matched_candidate["requires_manual_review"] if matched_candidate else None
        ),
        # Unified Claim Admissibility Sprint: carried through unchanged from
        # the structured record so Activation/Conflict can read the
        # adapter's own authoritative classification via
        # claim_quality.is_claim_eligible() without recomputing it from a
        # possibly-narrower (Mapper-filtered) factor list.
        "claim_quality": record.get("claim_quality"),
    }
    return _apply_optional_classifier(
        result,
        record,
        taxonomy,
        classifier,
        classifier_enabled or llm_gateway is not None,
        classifier_timeout_seconds,
        llm_gateway,
    )

# Map a list of structured claim records to their best matching alpha definitions, returning a list of match results.
def map_structured_records(
    records: Iterable[Mapping[str, Any]],
    taxonomy: Mapping[str, AlphaDefinition] | None = None,
    *,
    classifier: Callable[..., Mapping[str, Any]] | None = None,
    classifier_enabled: bool = False,
    classifier_timeout_seconds: float = DEFAULT_CLASSIFIER_TIMEOUT_SECONDS,
    llm_gateway: Any = None,
) -> list[dict[str, Any]]:
    taxonomy = taxonomy or load_alpha_taxonomy()
    results = []
    for record in records:
        # Unified Claim Admissibility Sprint: the shared quality gate
        # replaces the old bare "claim == 'unknown'" placeholder check --
        # every quality class (analytical, context_only-as-Alpha-context,
        # non_substantive) is now judged the same way every other consumer
        # judges it, via claim_quality.is_claim_eligible().
        if not isinstance(record, Mapping) or not is_claim_eligible(record, CONSUMER_MAPPING):
            continue
        results.append(
            map_claim_to_alpha(
                record,
                taxonomy,
                classifier=classifier,
                classifier_enabled=classifier_enabled,
                classifier_timeout_seconds=classifier_timeout_seconds,
                llm_gateway=llm_gateway,
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
    llm_gateway: Any = None,
) -> dict[str, Any]:
    taxonomy = taxonomy or load_alpha_taxonomy()
    records = structured_payload.get("records", [])
    if not isinstance(records, list):
        records = []
    matches = map_structured_records(
        records,
        taxonomy,
        classifier=classifier,
        classifier_enabled=classifier_enabled,
        classifier_timeout_seconds=classifier_timeout_seconds,
        llm_gateway=llm_gateway,
    )
    # B1 LLM upgrade: additive post-pass over the already-computed matches.
    # When llm_gateway is None (every existing caller's default, and
    # Architecture Replay, which never passes one) this is a zero-cost
    # no-op and `matches` is unchanged from map_structured_records's own
    # output -- see evidence_stance_llm.apply_llm_stance_upgrade.
    apply_llm_stance_upgrade(matches, taxonomy, llm_gateway=llm_gateway)
    return {
        "schema_version": SCHEMA_VERSION,
        "mapper_version": MAPPER_VERSION,
        "minimum_match_score": DEFAULT_MIN_MATCH_SCORE,
        "run_id": structured_payload.get("run_id"),
        "ticker": structured_payload.get("ticker"),
        "matches": matches,
    }

# Save the alpha matches for a given run ID, loading structured agent outputs and saving the resulting matches payload.
def save_alpha_matches(
    run_id,
    output_root="outputs/runs",
    *,
    classifier: Callable[..., Mapping[str, Any]] | None = None,
    classifier_enabled: bool = False,
    classifier_timeout_seconds: float = DEFAULT_CLASSIFIER_TIMEOUT_SECONDS,
    llm_gateway: Any = None,
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
        llm_gateway=llm_gateway,
    )
    save_json_record(run_id, "alpha_matches.json", payload, output_root=output_root)
    return payload
