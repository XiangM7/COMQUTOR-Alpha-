"""Week 2 alpha mapping with deterministic admissibility and optional LLM selection."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, TypeVar

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
    alpha_positive_requirement_satisfied,
    alpha_relation,
    alpha_specific_invalidation_matched,
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
from comqutor_alpha.structure_engine.week2_llm import call_with_timeout, resolve_alpha_classifier_concurrency

SCHEMA_VERSION = "week2.alpha_matches.v2"
MAPPER_VERSION = "week2.alpha_mapper.v2"
DEFAULT_MIN_MATCH_SCORE = 0.35
DEFAULT_AMBIGUITY_DELTA = 0.14
DEFAULT_SECONDARY_DELTA = 0.25
DEFAULT_CLASSIFIER_TIMEOUT_SECONDS = 5.0
# Step 5A execution-capacity repair: bounded batch size for the Pure-LLM
# alpha_classifier_batch task (comqutor_alpha.structure_engine.week2_llm).
# Revised down from an initial 40 to 15 after a real controlled-Provider
# validation against QQQ (874 claims, docs/audit_artifacts/
# week2_runtime_capacity_repair_v0.1.2.1.md) showed batch=40 only completed
# within the 45s timeout for 5/22 batches (200/874 = 22.9% coverage,
# WEEK2_LLM_TIMEOUT on the rest) -- a semantic decision per claim requires
# real completion-token generation for each item in the batch, so larger
# batches take proportionally longer wall-clock time to finish, unlike the
# lighter entities/factors-only claim_batch_enrichment task
# (LLM_CLAIM_BATCH_SIZE=64) this was originally sized to match. 15 is small
# enough that even DeepSeek's slower single-claim tail latency (p90 ~3.5s
# per claim, Step-4 evidence) stays comfortably inside the timeout. Must
# stay in sync with week2_llm.ALPHA_CLASSIFIER_BATCH_SIZE, which duplicates
# this value only for its own call-budget formula math.
ALPHA_CLASSIFIER_BATCH_SIZE = 15

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


def _alpha_taxonomy_request_block(taxonomy: Mapping[str, AlphaDefinition]) -> list[dict[str, Any]]:
    return [
        {"alpha_id": alpha.alpha_id, "alpha_name": alpha.name_en, "definition": alpha.core_thesis}
        for alpha in sorted(taxonomy.values(), key=lambda item: item.alpha_id)
    ]


# Pure-LLM Alpha semantic authority (Alpha Mapper Pure-LLM Semantic Authority
# task): the LLM is the ONLY source of the semantic Alpha result. It sees the
# FULL canonical taxonomy, unrestricted by deterministic candidate
# generation/eligibility/score threshold/AI hard gate, and must resolve to
# exactly one of two successful outcomes -- "selected" (exactly one
# canonical Alpha) or "none" (no canonical Alpha materially fits). There is
# no successful "cannot decide"/"defer" outcome: semantic ambiguity between
# two plausible Alphas is not itself grounds for "none" (see the prompt).
# Deterministic logic is NEVER a fallback source for the semantic result --
# it remains a diagnostic/counterfactual only (map_claim_to_alpha's
# deterministic_top_alpha/deterministic_match_status fields). Every
# operational failure (disabled, unavailable, timeout, malformed/invalid
# output, unknown Alpha ID, provider error) returns outcome="unavailable",
# never a deterministic Alpha standing in as the semantic answer.
# Step 5A Section 10/11: the gateway trace path (Week2LLMGateway.
# invoke_json_with_trace) already distinguishes WHY a call failed
# (invocation.error_code), but until this repair every non-accepted outcome
# was collapsed to the single fallback_reason "invalid_output" regardless of
# cause -- the exact defect that made a 98%-UNAVAILABLE run indistinguishable
# from a handful of real malformed responses. This maps the gateway's own
# error taxonomy onto a stable, still-UNAVAILABLE-only fallback_reason
# vocabulary (never NONE, never a deterministic stand-in -- see
# _classify_alpha_with_llm's Pure-LLM-authority docstring above).
_GATEWAY_ERROR_CODE_TO_FALLBACK_REASON: dict[str, str] = {
    "WEEK2_LLM_TIMEOUT": "provider_timeout",
    "WEEK2_LLM_CALL_BUDGET_EXHAUSTED": "call_budget_exhausted",
    "WEEK2_LLM_RATE_LIMIT": "provider_rate_limited",
    "WEEK2_LLM_TRANSPORT_ERROR": "provider_error",
    "WEEK2_LLM_PROVIDER_ERROR": "provider_error",
    "WEEK2_LLM_INVALID_JSON": "invalid_output",
    "WEEK2_LLM_VALIDATION_FAILED": "invalid_output",
    "WEEK2_LLM_INPUT_TOO_LARGE": "input_too_large",
}


def _gateway_error_to_fallback_reason(error_code: str | None) -> str:
    return _GATEWAY_ERROR_CODE_TO_FALLBACK_REASON.get(error_code or "", "invalid_output")


def _classify_alpha_with_llm(
    record: Mapping[str, Any],
    taxonomy: Mapping[str, AlphaDefinition],
    classifier: Callable[..., Mapping[str, Any]] | None,
    classifier_enabled: bool,
    timeout_seconds: float,
    llm_gateway: Any = None,
) -> dict[str, Any]:
    def _unavailable(reason: str) -> dict[str, Any]:
        return {"outcome": "unavailable", "alpha_id": None, "fallback_reason": reason, "diagnostic": _classifier_metadata(True, reason, used=True)}

    if not classifier_enabled:
        return {"outcome": "unavailable", "alpha_id": None, "fallback_reason": "disabled", "diagnostic": _classifier_metadata(False, "disabled")}
    if classifier is None and llm_gateway is None:
        return _unavailable("unavailable")

    allowed_ids = set(taxonomy)
    request = {
        "claim": str(record.get("claim") or ""),
        "evidence": str(record.get("evidence") or ""),
        "ticker": str(record.get("ticker") or ""),
        "factors": _record_factors(record),
        "direction": normalize_direction(record.get("direction")),
        "alpha_taxonomy": _alpha_taxonomy_request_block(taxonomy),
    }

    try:
        if llm_gateway is not None:
            def validate_response(payload):
                if set(payload) != {"decision", "selected_alpha_id"}:
                    raise ValueError("classifier response has unexpected fields")
                decision = str(payload.get("decision") or "").strip().lower()
                selected_alpha_id = payload.get("selected_alpha_id")
                if decision == "none":
                    if selected_alpha_id not in (None, ""):
                        raise ValueError("none decision must not include a selected_alpha_id")
                    return {"outcome": "none", "alpha_id": ""}
                if decision == "select":
                    selected_alpha_id = str(selected_alpha_id or "").strip()
                    if selected_alpha_id in allowed_ids:
                        return {"outcome": "selected", "alpha_id": selected_alpha_id}
                    raise ValueError("classifier selected an Alpha ID outside the canonical taxonomy")
                raise ValueError("classifier response used an unrecognized decision value")

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
                    return _unavailable(_gateway_error_to_fallback_reason(invocation.error_code))
            if response is None:
                return _unavailable("invalid_output")
        else:
            response = call_with_timeout(
                lambda: classifier(request, timeout_seconds=timeout_seconds),
                timeout_seconds,
            )
    except TimeoutError:
        return _unavailable("provider_timeout")
    except Exception:
        return _unavailable("provider_error")

    if not isinstance(response, Mapping):
        return _unavailable("invalid_output")
    if set(response) != {"outcome", "alpha_id"}:
        return _unavailable("invalid_output")

    outcome = str(response.get("outcome") or "").strip().lower()
    alpha_id = str(response.get("alpha_id") or "").strip()
    if outcome == "selected" and alpha_id in allowed_ids:
        return {"outcome": "selected", "alpha_id": alpha_id, "fallback_reason": None, "diagnostic": _classifier_metadata(True, "llm_selected", used=True)}
    if outcome == "selected" and alpha_id not in allowed_ids:
        return _unavailable("invalid_alpha_id")
    if outcome == "none" and not alpha_id:
        return {"outcome": "none", "alpha_id": None, "fallback_reason": None, "diagnostic": _classifier_metadata(True, "llm_none", used=True)}

    return _unavailable("invalid_output")


_ChunkItem = TypeVar("_ChunkItem")


def _chunk_records(items: list[_ChunkItem], batch_size: int) -> list[list[_ChunkItem]]:
    return [items[start : start + batch_size] for start in range(0, len(items), batch_size)]


def _stable_claim_id(record: Mapping[str, Any], fallback_index: int) -> str:
    return str(record.get("claim_id") or record.get("agent_output_id") or f"__record_index_{fallback_index}__")


def _classify_alpha_batch_with_llm(
    claim_id_record_pairs: list[tuple[str, Mapping[str, Any]]],
    taxonomy: Mapping[str, AlphaDefinition],
    llm_gateway: Any,
) -> dict[str, dict[str, Any]]:
    """Batched sibling of ``_classify_alpha_with_llm`` (Step 5A execution-
    capacity repair): one Provider call classifies up to
    ``ALPHA_CLASSIFIER_BATCH_SIZE`` claims at once, against the IDENTICAL
    semantic decision criteria (week2_llm.py's ``alpha_classifier_batch``
    prompt is copied verbatim from ``alpha_classifier`` v3 -- only the I/O
    envelope changed, one claim per call -> many claims per call). Returns
    one outcome dict per claim_id, in the exact shape
    ``_classify_alpha_with_llm`` returns, so ``map_claim_to_alpha`` can
    consume either interchangeably via ``llm_outcome_override``.

    Row-level validation salvage (Section 6): a single malformed decision
    item does not invalidate the whole batch -- only that claim_id is left
    at its ``unavailable``/``invalid_output`` default while every other,
    well-formed row in the same batch is still accepted. Only a
    fundamentally malformed response (not an object, missing the decisions
    array, wrong length) invalidates the whole batch, because in that case
    no row can safely be attributed to any specific claim_id. No row may
    ever inherit another row's answer -- results are built into a fresh,
    per-claim_id dict, never merged/overwritten across rows.
    """
    allowed_ids = set(taxonomy)
    claim_ids = [claim_id for claim_id, _ in claim_id_record_pairs]
    id_to_record: dict[str, Mapping[str, Any]] = dict(claim_id_record_pairs)
    request_claims: list[dict[str, Any]] = [
        {
            "claim_id": claim_id,
            "claim": str(record.get("claim") or ""),
            "evidence": str(record.get("evidence") or ""),
            "ticker": str(record.get("ticker") or ""),
            "factors": _record_factors(record),
            "direction": normalize_direction(record.get("direction")),
        }
        for claim_id, record in claim_id_record_pairs
    ]
    request = {"alpha_taxonomy": _alpha_taxonomy_request_block(taxonomy), "claims": request_claims}

    def _row_unavailable(reason: str) -> dict[str, Any]:
        return {"outcome": "unavailable", "alpha_id": None, "fallback_reason": reason, "diagnostic": _classifier_metadata(True, reason, used=True)}

    def validate_response(payload: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(payload, Mapping) or set(payload) != {"decisions"}:
            raise ValueError("batch classifier response has unexpected top-level fields")
        decisions = payload.get("decisions")
        if not isinstance(decisions, list) or len(decisions) != len(request_claims):
            raise ValueError("decisions count must match input claim count exactly")

        results: dict[str, dict[str, Any]] = {cid: _row_unavailable("invalid_output") for cid in claim_ids}
        seen: set[str] = set()
        for item in decisions:
            if not isinstance(item, Mapping) or set(item) != {"claim_id", "decision", "selected_alpha_id"}:
                continue  # row-level: unidentifiable/malformed row, leave its (or any) claim_id at the default
            claim_id = item.get("claim_id")
            if not isinstance(claim_id, str) or claim_id not in id_to_record or claim_id in seen:
                continue  # row-level: unknown/duplicate claim_id, never overwrite another row's answer
            seen.add(claim_id)
            decision = str(item.get("decision") or "").strip().lower()
            selected_alpha_id = item.get("selected_alpha_id")
            if decision == "none":
                if selected_alpha_id in (None, ""):
                    results[claim_id] = {"outcome": "none", "alpha_id": None, "fallback_reason": None, "diagnostic": _classifier_metadata(True, "llm_none", used=True)}
                continue  # else: malformed (none + non-null alpha_id) -- leave at unavailable default
            if decision == "select":
                selected_alpha_id = str(selected_alpha_id or "").strip()
                if selected_alpha_id in allowed_ids:
                    results[claim_id] = {"outcome": "selected", "alpha_id": selected_alpha_id, "fallback_reason": None, "diagnostic": _classifier_metadata(True, "llm_selected", used=True)}
                else:
                    results[claim_id] = _row_unavailable("invalid_alpha_id")
                continue
            # else: unrecognized decision value -- leave at unavailable default
        return results

    if not callable(getattr(llm_gateway, "invoke_json_with_trace", None)):
        # No batching capability on this gateway -- caller must not route
        # here for such a gateway; fail closed per-claim rather than guess.
        return {cid: _row_unavailable("unavailable") for cid in claim_ids}

    invocation = llm_gateway.invoke_json_with_trace("alpha_classifier_batch", request, validate_response)
    if invocation.validation_accepted:
        llm_gateway.finalize_semantic_invocation(invocation, accepted=True)
        return invocation.validated_output
    llm_gateway.finalize_semantic_invocation(
        invocation,
        accepted=False,
        fallback_reason=(invocation.error_code or "WEEK2_LLM_ALPHA_CLASSIFIER_BATCH_FALLBACK"),
    )
    reason = _gateway_error_to_fallback_reason(invocation.error_code)
    return {cid: _row_unavailable(reason) for cid in claim_ids}


def _classify_alpha_concurrent_with_llm(
    claim_id_record_pairs: list[tuple[str, Mapping[str, Any]]],
    taxonomy: Mapping[str, AlphaDefinition],
    classifier: Callable[..., Mapping[str, Any]] | None,
    classifier_enabled: bool,
    timeout_seconds: float,
    llm_gateway: Any,
    concurrency: int,
) -> dict[str, dict[str, Any]]:
    """Step 5A Section 4 (multi-claim batching DEFERRED for v0.1.2.1 -- see
    docs/audit_artifacts/week2_runtime_capacity_repair_v0.1.2.1.md): the
    proven-reliable semantic unit is restored -- one claim, the FULL
    canonical taxonomy, one LLM call. Execution capacity instead comes from
    running independent single-claim calls with bounded concurrency, never
    from combining claims into one request.

    Safety (Section 5), verified against the existing architecture rather
    than assumed:
    - One claim_id maps to exactly one final result: results are collected
      into a dict keyed by claim_id, never by list position or completion
      order.
    - No cross-claim state: each worker calls ``_classify_alpha_with_llm``
      with its own independent ``record``/request: nothing is shared or
      mutated across calls.
    - Week2LLMGateway._reserve_call (the shared call-budget counter) and
      ._log (the shared error-log writer) are both protected by the
      gateway's own ``threading.Lock`` (see week2_llm.py), so concurrent
      workers cannot overshoot the budget, double-count it, or corrupt the
      shared error log -- verified by reading that code, not assumed.
    - Retry budget is not multiplied by concurrency: each worker's own
      ``invoke_json_with_trace`` call performs its OWN bounded retry loop,
      each attempt independently reserving one unit of the SAME shared,
      lock-protected counter -- concurrency changes only how many
      claims are in flight at once, never how many attempts any one claim
      gets.
    - No cancellation-on-first-failure: every submitted claim runs to
      completion (success or its own failure) independently; one claim's
      timeout/error never discards another claim's already-completed
      result.
    """
    if concurrency <= 1 or len(claim_id_record_pairs) <= 1:
        return {
            claim_id: _classify_alpha_with_llm(
                record, taxonomy, classifier, classifier_enabled, timeout_seconds, llm_gateway
            )
            for claim_id, record in claim_id_record_pairs
        }

    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="comqutor-alpha-classifier") as executor:
        future_to_claim_id = {
            executor.submit(
                _classify_alpha_with_llm,
                record,
                taxonomy,
                classifier,
                classifier_enabled,
                timeout_seconds,
                llm_gateway,
            ): claim_id
            for claim_id, record in claim_id_record_pairs
        }
        for future in as_completed(future_to_claim_id):
            claim_id = future_to_claim_id[future]
            results[claim_id] = future.result()
    return results


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
    llm_outcome_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """``llm_outcome_override`` (Step 5A): when supplied, this claim's LLM
    semantic outcome was already computed by a batched call
    (``_classify_alpha_batch_with_llm``) -- skip the single-claim
    ``_classify_alpha_with_llm`` call entirely and use the override
    directly. ``None`` (the default) preserves the exact original
    single-call-per-claim behavior for every existing caller."""
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

    # Pure-LLM Alpha semantic authority: the deterministic computation above
    # (candidates/eligible_candidates/top/second/status/matched_alpha) is
    # captured here as a diagnostic/counterfactual ONLY -- it never becomes
    # the semantic result, including on any LLM operational failure. The
    # LLM is consulted regardless of what deterministic scoring concluded,
    # and its own outcome ("selected" / "none" / "unavailable") is the SOLE
    # source of the top-level match_status/matched_alpha/matched_alpha_name
    # below -- deterministic logic is never a semantic fallback source.
    deterministic_top_alpha = matched_alpha
    deterministic_match_status = status

    if llm_outcome_override is not None:
        llm_outcome = llm_outcome_override
    else:
        llm_outcome = _classify_alpha_with_llm(
            record,
            taxonomy,
            classifier,
            classifier_enabled or llm_gateway is not None,
            classifier_timeout_seconds,
            llm_gateway,
        )
    if llm_outcome["outcome"] == "selected":
        alpha = taxonomy[llm_outcome["alpha_id"]]
        status = "matched"
        matched_alpha = llm_outcome["alpha_id"]
        matched_alpha_name = alpha.name_en
        reason = "llm semantic classifier selected from full canonical taxonomy"
        alpha_match_method = "llm"
        alpha_match_fallback_reason = None
    elif llm_outcome["outcome"] == "none":
        status = "no_match"
        matched_alpha = None
        matched_alpha_name = None
        reason = "llm semantic classifier determined no canonical Alpha materially fits"
        alpha_match_method = "llm"
        alpha_match_fallback_reason = None
    else:
        status = "unavailable"
        matched_alpha = None
        matched_alpha_name = None
        reason = f"llm semantic classifier unavailable: {llm_outcome['fallback_reason']}"
        alpha_match_method = "llm_unavailable"
        alpha_match_fallback_reason = llm_outcome["fallback_reason"]

    # v0.2 QQQ A001 mapping remediation (Step 7A): a narrow, taxonomy-native
    # exception to Pure-LLM Alpha semantic authority above. Root cause (see
    # docs/audit_artifacts/v0_2_acceptance_adjudication.json Case A):
    # Activation Scorer v2's evidence_quality/agent_independence components
    # are direction-blind once a claim carries a given matched_alpha -- they
    # count claim volume/agent breadth, not net directional support -- so
    # when the LLM classifier pools evidence that explicitly asserts an
    # Alpha's own core thesis is FALSE (e.g. "93% probability of NO Fed rate
    # cuts", "72% probability of a Fed rate hike" for A001's Rate Cut Cycle
    # thesis) into that Alpha's matched_alpha bucket, that pooled volume
    # alone can push the Alpha to an official detected level with no
    # genuine supporting evidence. This check runs AFTER the semantic
    # classifier (or, when disabled, the deterministic top candidate) has
    # produced a final matched_alpha, and vetoes it back to no_match only
    # when that SPECIFIC alpha_id has its own explicit, high-precision
    # invalidation pattern registered (currently only A001; see
    # claim_semantics.ALPHA_SPECIFIC_INVALIDATION_PATTERNS) and that pattern
    # fires for this claim's text. It deliberately never uses the broader,
    # lower-precision multi-Alpha `_INVALIDATION_PATTERN` (headwind/demand-
    # weakens/etc.), is keyed only by alpha_id -- never by ticker or
    # run_id -- and is a no-op for every Alpha without a registered pattern,
    # so it cannot silently suppress legitimate matches elsewhere. This is a
    # deliberate, narrow, evidence-driven exception to the "LLM is the ONLY
    # source of the semantic Alpha result" invariant documented above, not a
    # reintroduction of deterministic logic as a general fallback authority.
    if matched_alpha is not None and alpha_specific_invalidation_matched(text, matched_alpha):
        status = "no_match"
        matched_alpha = None
        matched_alpha_name = None
        reason = (
            "alpha-specific invalidation evidence explicitly contradicts this Alpha's own "
            "core thesis; overriding semantic classifier selection to no_match"
        )
        alpha_specific_invalidation_override = True
    else:
        alpha_specific_invalidation_override = False

    # v0.2 QQQ A001 mapping remediation (Step 7A.2): Alpha-Specific Positive
    # Requirement gate, complementary to the negative veto immediately
    # above (never a replacement for it -- both must pass). Root cause (see
    # docs/audit_artifacts/v0_2_qqq_a001_residual_mapping_audit.json): an
    # independent row-level audit of the 29 claims that survived the
    # Step-7A negative veto found ZERO genuine positive A001 evidence among
    # them (0/29) -- the dominant residual pattern was generic rate-context
    # commentary (headwinds, repricing, sensitivity framing) that never
    # asserts the OPPOSITE of A001's thesis (so the negative veto never
    # fires) but also never asserts the thesis ITSELF. A pure negative
    # blocklist cannot close this gap without unbounded enumeration, so a
    # matched Alpha with its own registered positive-requirement classifier
    # (currently only A001; see claim_semantics.
    # ALPHA_POSITIVE_REQUIREMENT_CLASSIFIERS) must now also affirmatively
    # clear that classifier before the match survives. Runs after the
    # negative veto so it only evaluates a still-live matched_alpha; is a
    # no-op (always satisfied) for every Alpha without a registered
    # classifier, so it cannot silently suppress legitimate matches
    # elsewhere. Same deliberate, narrow, evidence-driven exception to the
    # "LLM is the ONLY source of the semantic Alpha result" invariant as
    # the negative veto -- not a reintroduction of deterministic logic as a
    # general fallback authority.
    if matched_alpha is not None and not alpha_positive_requirement_satisfied(text, matched_alpha):
        status = "no_match"
        matched_alpha = None
        matched_alpha_name = None
        reason = (
            "this Alpha's own positive-requirement semantic gate was not satisfied "
            "(no affirmative directional evidence for its core thesis); overriding "
            "semantic classifier selection to no_match"
        )
        alpha_positive_requirement_override = True
    else:
        alpha_positive_requirement_override = False

    # Sprint 2, Track B1: classify Evidence Stance for every candidate now
    # that the FINAL `matched_alpha` is known (needed for the
    # supports_counter_alpha check, and to resolve conflict partners
    # relative to the semantic -- not merely deterministic -- match) --
    # attaches additive fields onto the SAME dict objects that
    # candidate_scores/top_candidates/eligible_candidates below reference,
    # so every view reads one identical, non-drifting result per candidate.
    # `candidates` always has one entry per taxonomy Alpha (see the
    # `_candidate_score(...) for alpha in taxonomy.values()` comprehension
    # above), so the matched Alpha's own entry always exists somewhere in
    # it even when the LLM selected an Alpha deterministic scoring ranked
    # far outside the top 5 -- `stance_scope` is widened to that Alpha's own
    # index so it is never skipped, and `candidate_scores` below is likewise
    # widened so every downstream reader that looks up "the matched Alpha's
    # own candidate diagnostics" by scanning eligible_candidates/
    # top_candidates/candidate_scores (B1's own LLM upgrade pass, B2
    # admissibility, B4 activation, and the audit/evidence-review exporter
    # all do exactly this -- see the dependency audit) keeps finding it.
    matched_alpha_index = next(
        (index for index, item in enumerate(candidates) if item["alpha_id"] == matched_alpha),
        None,
    ) if matched_alpha else None
    stance_scope = max(5, len(eligible_candidates))
    if matched_alpha_index is not None:
        stance_scope = max(stance_scope, matched_alpha_index + 1)
    _attach_evidence_stance(
        candidates[:stance_scope],
        {**record, "matched_alpha": matched_alpha},
        taxonomy,
    )
    matched_candidate = next(
        (item for item in candidates if item["alpha_id"] == matched_alpha), None
    ) if (status == "matched" and matched_alpha) else None

    candidate_scores = candidates[:5]
    if matched_candidate is not None and matched_alpha not in {
        item["alpha_id"] for item in candidate_scores
    }:
        candidate_scores = candidate_scores + [matched_candidate]

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
        "score": matched_candidate["score"] if matched_candidate else 0.0,
        "keyword_score": matched_candidate["keyword_score"] if matched_candidate else 0.0,
        "factor_score": matched_candidate["factor_score"] if matched_candidate else 0.0,
        "direction_score": matched_candidate["direction_score"] if matched_candidate else 0.0,
        "candidate_scores": candidate_scores,
        "top_candidates": candidates[:3],
        "eligible_candidates": plausible_candidates,
        "plausible_alphas": [item["alpha_id"] for item in plausible_candidates],
        "secondary_alphas": secondary_alphas,
        "match_status": status,
        "reason": reason,
        # v0.2 QQQ A001 mapping remediation (Step 7A): additive-only
        # diagnostic -- True exactly when the deterministic alpha-specific
        # invalidation veto above fired (overriding a semantic-classifier
        # "selected" or deterministic-fallback result back to no_match).
        # False (never fabricated) whenever the veto did not apply,
        # including for every Alpha without a registered pattern.
        "alpha_specific_invalidation_override": alpha_specific_invalidation_override,
        # v0.2 QQQ A001 mapping remediation (Step 7A.2): additive-only
        # diagnostic -- True exactly when the positive-requirement gate
        # above fired (overriding a semantic-classifier "selected" or
        # deterministic-fallback result back to no_match because it failed
        # to clear that Alpha's own registered positive-requirement
        # classifier). False (never fabricated) whenever the gate did not
        # apply, including for every Alpha without a registered classifier.
        "alpha_positive_requirement_override": alpha_positive_requirement_override,
        # Pure-LLM Alpha semantic authority: which semantic authority
        # produced `matched_alpha` -- always "llm" for a genuine LLM
        # decision, whether it selected an Alpha (match_status="matched") or
        # determined no Alpha materially fits (match_status="no_match");
        # "llm_unavailable" only when no LLM decision could be obtained at
        # all (disabled, provider timeout/error, malformed/invalid output,
        # unknown Alpha ID) -- deterministic scoring is never the value's
        # source. Mirrors B1's existing stance_method/stance_fallback_reason
        # naming convention rather than inventing a parallel vocabulary.
        "alpha_match_method": alpha_match_method,
        "alpha_match_fallback_reason": alpha_match_fallback_reason,
        # Pure-LLM Alpha semantic authority: the deterministic mapper's own
        # conclusion, captured BEFORE the LLM outcome is applied above --
        # diagnostic/counterfactual only, never a semantic fallback source.
        # deterministic_top_alpha mirrors matched_alpha's shape (an Alpha ID
        # or None); deterministic_match_status mirrors match_status's
        # vocabulary ("matched"/"no_match"/"ambiguous").
        "deterministic_top_alpha": deterministic_top_alpha,
        "deterministic_match_status": deterministic_match_status,
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
        "classifier": llm_outcome["diagnostic"],
    }
    return result

# Map a list of structured claim records to their best matching alpha definitions, returning a list of match results.
def map_structured_records(
    records: Iterable[Mapping[str, Any]],
    taxonomy: Mapping[str, AlphaDefinition] | None = None,
    *,
    classifier: Callable[..., Mapping[str, Any]] | None = None,
    classifier_enabled: bool = False,
    classifier_timeout_seconds: float = DEFAULT_CLASSIFIER_TIMEOUT_SECONDS,
    llm_gateway: Any = None,
    use_batched_classifier: bool = False,
    concurrency: int = 1,
) -> list[dict[str, Any]]:
    """``use_batched_classifier`` (Step 5A execution-capacity repair):
    multi-claim batching (``_classify_alpha_batch_with_llm``, bounded
    batches of ``ALPHA_CLASSIFIER_BATCH_SIZE``) was evaluated and DEFERRED
    for v0.1.2.1 -- a real controlled-Provider validation against DeepSeek
    deepseek-v4-flash showed multi-item structured completions are
    unreliable regardless of batch size or timeout (see
    docs/audit_artifacts/week2_runtime_capacity_repair_v0.1.2.1.md). The
    code path is kept (still offline-tested) for a future release against a
    provider/model proven reliable for it, but defaults to ``False`` --
    single-claim semantics are the current production path.

    ``concurrency`` (Step 5A Section 4, default 1): when > 1 and an
    ``llm_gateway`` exposing ``invoke_json_with_trace`` is supplied,
    independent single-claim classifications run concurrently via
    ``_classify_alpha_concurrent_with_llm`` (bounded worker pool -- see its
    own docstring for the verified concurrency-safety properties this
    relies on). Legacy gateways/callables that only implement the older
    ``invoke_json`` seam (every existing unit test's fake gateway, and the
    raw ``classifier`` callable path) are entirely unaffected -- concurrency
    only ever applies to the real trace-capable gateway."""
    taxonomy = taxonomy or load_alpha_taxonomy()
    eligible_records: list[Mapping[str, Any]] = [
        record
        for record in records
        # Unified Claim Admissibility Sprint: the shared quality gate
        # replaces the old bare "claim == 'unknown'" placeholder check --
        # every quality class (analytical, context_only-as-Alpha-context,
        # non_substantive) is now judged the same way every other consumer
        # judges it, via claim_quality.is_claim_eligible().
        if isinstance(record, Mapping) and is_claim_eligible(record, CONSUMER_MAPPING)
    ]

    gateway_supports_trace = llm_gateway is not None and callable(
        getattr(llm_gateway, "invoke_json_with_trace", None)
    )
    batching_active = use_batched_classifier and gateway_supports_trace
    concurrency_active = (not batching_active) and gateway_supports_trace and int(concurrency) > 1

    llm_outcome_by_claim_id: dict[str, dict[str, Any]] = {}
    claim_id_record_pairs: list[tuple[str, Mapping[str, Any]]] = []
    if batching_active:
        claim_id_record_pairs = [
            (_stable_claim_id(record, index), record) for index, record in enumerate(eligible_records)
        ]
        for batch in _chunk_records(claim_id_record_pairs, ALPHA_CLASSIFIER_BATCH_SIZE):
            llm_outcome_by_claim_id.update(_classify_alpha_batch_with_llm(batch, taxonomy, llm_gateway))
    elif concurrency_active:
        claim_id_record_pairs = [
            (_stable_claim_id(record, index), record) for index, record in enumerate(eligible_records)
        ]
        llm_outcome_by_claim_id = _classify_alpha_concurrent_with_llm(
            claim_id_record_pairs,
            taxonomy,
            classifier,
            # Matches map_claim_to_alpha's own single-call OR logic: a
            # supplied llm_gateway always implies "consult the classifier",
            # regardless of the raw classifier_enabled flag (which exists
            # for the non-gateway raw-callable path).
            classifier_enabled or llm_gateway is not None,
            classifier_timeout_seconds,
            llm_gateway,
            int(concurrency),
        )

    outcome_lookup_active = batching_active or concurrency_active
    results = []
    for index, record in enumerate(eligible_records):
        override = (
            llm_outcome_by_claim_id.get(_stable_claim_id(record, index)) if outcome_lookup_active else None
        )
        results.append(
            map_claim_to_alpha(
                record,
                taxonomy,
                classifier=classifier,
                classifier_enabled=classifier_enabled,
                classifier_timeout_seconds=classifier_timeout_seconds,
                llm_gateway=llm_gateway,
                llm_outcome_override=override,
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
    use_batched_classifier: bool = False,
    concurrency: int | None = None,
) -> dict[str, Any]:
    taxonomy = taxonomy or load_alpha_taxonomy()
    records = structured_payload.get("records", [])
    if not isinstance(records, list):
        records = []
    # Step 5A Section 4/10: resolved here (the production-facing layer),
    # not hardcoded in map_structured_records, so COMQUTOR_WEEK2_LLM_
    # CONCURRENCY stays the single source of truth every real caller picks
    # up automatically -- explicit callers/tests can still override it.
    resolved_concurrency = concurrency if concurrency is not None else resolve_alpha_classifier_concurrency()
    matches = map_structured_records(
        records,
        taxonomy,
        classifier=classifier,
        classifier_enabled=classifier_enabled,
        classifier_timeout_seconds=classifier_timeout_seconds,
        llm_gateway=llm_gateway,
        use_batched_classifier=use_batched_classifier,
        concurrency=resolved_concurrency,
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
    use_batched_classifier: bool = False,
    concurrency: int | None = None,
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
        use_batched_classifier=use_batched_classifier,
        concurrency=concurrency,
    )
    save_json_record(run_id, "alpha_matches.json", payload, output_root=output_root)
    return payload
