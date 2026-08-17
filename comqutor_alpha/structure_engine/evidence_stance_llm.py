"""Sprint 2, Track B1 LLM upgrade: batch LLM semantic stance classification.

Responsibility split (task spec section 3):

  * LLM = semantic authority. It answers exactly one question per item:
    "what stance does this Evidence express relative to this target Alpha?"
  * This module (program) = contract authority only. It checks identity
    (claim_id/target_alpha_id match the request), vocabulary (stance is one
    of the five existing values), and counter-Alpha legality (reuses the
    taxonomy's own canonical conflict registry -- never a second one). It
    never re-judges whether a structurally valid LLM stance "sounds right".
  * ``evidence_stance.classify_evidence_stance`` (deterministic.v1) = fail-
    soft fallback only, used per (claim_id, target_alpha_id) exactly when
    the LLM result for that specific pair is unavailable or invalid. It is
    not modified, not re-implemented, and not asked to arbitrate a
    structurally valid LLM answer.

This module never re-scores, re-admits, or re-groups anything, and -- like
``evidence_stance.py`` itself -- must never be imported by, or feed a value
back into, ``claim_semantics`` / ``claim_quality`` / ``alpha_mapper``
scoring: Evidence Stance (LLM or deterministic) stays a pure, additive
side-channel.

Reuses, never duplicates:
  * ``comqutor_alpha.structure_engine.week2_llm.Week2LLMGateway`` -- the
    same shared gateway, retry/timeout/budget machinery, and semantic-
    runtime cache/replay hooks every other Week 2 semantic task already
    uses, via one new registered task name (``evidence_stance_classifier``).
  * ``evidence_stance.canonical_conflict_partners`` -- the taxonomy's own
    ``conflict_alphas`` registry, for both building each item's
    ``counter_alphas`` context and validating a returned
    ``supports_counter_alpha`` result.
  * ``evidence_stance.VALID_EVIDENCE_STANCES`` -- the exact same five-value
    vocabulary; no sixth stance is introduced.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from comqutor_alpha.alpha_library.alpha_schema import AlphaDefinition
from comqutor_alpha.structure_engine.evidence_stance import (
    CLASSIFIER_VERSION as DETERMINISTIC_CLASSIFIER_VERSION,
    SUPPORTS_COUNTER_ALPHA,
    VALID_EVIDENCE_STANCES,
    canonical_conflict_partners,
)

LLM_CLASSIFIER_VERSION = "evidence_stance.llm.v1"
LLM_TASK_NAME = "evidence_stance_classifier"

# --- section 17: versioning / observability enum values ---------------------
STANCE_METHOD_LLM = "llm"
STANCE_METHOD_DETERMINISTIC_FALLBACK = "deterministic_fallback"

# --- section 16: fallback reason vocabulary ---------------------------------
FALLBACK_PROVIDER_ERROR = "provider_error"
FALLBACK_TIMEOUT = "timeout"
FALLBACK_MALFORMED_RESPONSE = "malformed_response"
FALLBACK_MISSING_RESULT = "missing_result"
FALLBACK_IDENTITY_MISMATCH = "identity_mismatch"
FALLBACK_INVALID_STANCE = "invalid_stance"
FALLBACK_INVALID_COUNTER_ALPHA = "invalid_counter_alpha"
FALLBACK_DUPLICATE_RESULT = "duplicate_result"

VALID_FALLBACK_REASONS = frozenset(
    {
        FALLBACK_PROVIDER_ERROR,
        FALLBACK_TIMEOUT,
        FALLBACK_MALFORMED_RESPONSE,
        FALLBACK_MISSING_RESULT,
        FALLBACK_IDENTITY_MISMATCH,
        FALLBACK_INVALID_STANCE,
        FALLBACK_INVALID_COUNTER_ALPHA,
        FALLBACK_DUPLICATE_RESULT,
    }
)

# --- section 6/8: scope and batching bounds ---------------------------------
MAX_TARGET_ALPHAS_PER_CLAIM = 3
BATCH_SIZE = 10

_REQUIRED_RESPONSE_ITEM_KEYS = frozenset({"claim_id", "target_alpha_id", "stance"})
_ALLOWED_RESPONSE_ITEM_KEYS = frozenset({"claim_id", "target_alpha_id", "stance", "counter_alpha_id"})


def retained_target_alpha_ids(match: Mapping[str, Any]) -> list[str]:
    """The PD-011 retained scope for one claim: authoritative ``matched_alpha``
    plus up to two ``secondary_alphas`` -- at most 3, never all 10 Alphas."""
    matched_alpha = str(match.get("matched_alpha") or "").strip()
    if not matched_alpha:
        return []
    targets = [matched_alpha]
    for alpha_id in match.get("secondary_alphas") or ():
        alpha_id = str(alpha_id or "").strip()
        if alpha_id and alpha_id not in targets:
            targets.append(alpha_id)
        if len(targets) >= MAX_TARGET_ALPHAS_PER_CLAIM:
            break
    return targets[:MAX_TARGET_ALPHAS_PER_CLAIM]


def _candidate_for_alpha(match: Mapping[str, Any], alpha_id: str) -> dict[str, Any] | None:
    for candidate in match.get("candidate_scores") or ():
        if isinstance(candidate, dict) and candidate.get("alpha_id") == alpha_id:
            return candidate
    return None


def _counter_alpha_context(alpha_id: str, taxonomy: Mapping[str, AlphaDefinition]) -> list[dict[str, str]]:
    context = []
    for partner_id in sorted(canonical_conflict_partners(alpha_id, taxonomy)):
        partner = taxonomy.get(partner_id)
        if partner is not None:
            context.append({"alpha_id": partner.alpha_id, "name": partner.name_en, "definition": partner.core_thesis})
    return context


def _request_payload(match: Mapping[str, Any], alpha_id: str, taxonomy: Mapping[str, AlphaDefinition]) -> dict[str, Any] | None:
    """Section 9: the minimum semantic context, and nothing the old
    classifier's own verdict could anchor the new one on (no existing
    stance/reason_codes/relation, no keyword/factor/direction/activation/
    conflict score, no candidate id, no source offset)."""
    alpha = taxonomy.get(alpha_id)
    if alpha is None:
        return None
    payload: dict[str, Any] = {
        "claim_id": str(match.get("claim_id") or ""),
        "target_alpha_id": alpha_id,
        "ticker": str(match.get("ticker") or ""),
        "claim": str(match.get("claim") or ""),
        "evidence": str(match.get("evidence") or ""),
        "target_alpha_name": alpha.name_en,
        "target_alpha_definition": alpha.core_thesis,
    }
    counter_alphas = _counter_alpha_context(alpha_id, taxonomy)
    if counter_alphas:
        payload["counter_alphas"] = counter_alphas
    factors = [str(f) for f in (match.get("factors") or ()) if str(f or "").strip()]
    if factors:
        payload["factors"] = factors
    return payload


class StanceRequestItem:
    """One (claim_id, target_alpha_id) request, paired with the already-
    computed candidate dict it will be written back onto (the same object
    ``alpha_mapper._attach_evidence_stance`` already mutated in place --
    single source of truth for every downstream reader, exactly like the
    deterministic candidate fields it sits beside)."""

    __slots__ = ("claim_id", "target_alpha_id", "payload", "candidate")

    def __init__(self, claim_id: str, target_alpha_id: str, payload: dict[str, Any], candidate: dict[str, Any]) -> None:
        self.claim_id = claim_id
        self.target_alpha_id = target_alpha_id
        self.payload = payload
        self.candidate = candidate


def build_stance_request_items(
    matches: Sequence[Mapping[str, Any]], taxonomy: Mapping[str, AlphaDefinition]
) -> list[StanceRequestItem]:
    """Collects every retained-scope (claim_id, target_alpha_id) request
    across the whole run's already-mapped claims. A claim with
    ``matched_alpha = null`` contributes nothing (section 8: no-match
    Claims never spend a Provider request; PD-014 is untouched)."""
    items: list[StanceRequestItem] = []
    for match in matches:
        if not isinstance(match, Mapping):
            continue
        claim_id = match.get("claim_id")
        if not claim_id:
            continue
        for alpha_id in retained_target_alpha_ids(match):
            candidate = _candidate_for_alpha(match, alpha_id)
            if candidate is None:
                continue
            payload = _request_payload(match, alpha_id, taxonomy)
            if payload is None:
                continue
            items.append(StanceRequestItem(str(claim_id), alpha_id, payload, candidate))
    return items


def chunk_items(items: Sequence[StanceRequestItem], size: int = BATCH_SIZE) -> list[list[StanceRequestItem]]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


def _validate_batch_shape(payload: Any) -> list[Any]:
    """Passed to ``Week2LLMGateway.invoke_json_with_trace`` as the batch-
    level structural validator only: is this parseable as a batch at all?
    Per-item identity/vocabulary/counter-Alpha legality (section 13) is
    deliberately NOT checked here, so one bad item can never fail the
    others (section 13.D) -- only a response that isn't even a
    ``{"items": [...]}`` shape fails the whole batch, because there is no
    way to salvage per-item results from an unparseable shape."""
    if not isinstance(payload, Mapping):
        raise TypeError("evidence_stance_classifier response must be a JSON object")
    items = payload.get("items")
    if not isinstance(items, list):
        raise TypeError("evidence_stance_classifier response missing an items array")
    return items


def _reason_from_invocation(invocation: Any) -> str:
    status = getattr(invocation, "provider_status", None)
    error_code = getattr(invocation, "error_code", None)
    if status == "timeout":
        return FALLBACK_TIMEOUT
    if error_code in {"WEEK2_LLM_INVALID_JSON", "WEEK2_LLM_VALIDATION_FAILED", "WEEK2_LLM_INPUT_TOO_LARGE"}:
        return FALLBACK_MALFORMED_RESPONSE
    return FALLBACK_PROVIDER_ERROR


def _validate_response_item(
    requested: StanceRequestItem, returned: Any, taxonomy: Mapping[str, AlphaDefinition]
) -> tuple[str | None, str | None, str | None]:
    """Section 13: identity, vocabulary, counter-Alpha legality only --
    never a semantic re-judgment. Returns ``(stance, counter_alpha_id,
    fallback_reason)``; ``fallback_reason`` is ``None`` iff accepted."""
    if not isinstance(returned, Mapping):
        return None, None, FALLBACK_INVALID_STANCE
    keys = set(returned.keys())
    if not _REQUIRED_RESPONSE_ITEM_KEYS.issubset(keys) or not keys.issubset(_ALLOWED_RESPONSE_ITEM_KEYS):
        return None, None, FALLBACK_INVALID_STANCE
    if str(returned.get("claim_id") or "") != requested.claim_id or str(
        returned.get("target_alpha_id") or ""
    ) != requested.target_alpha_id:
        return None, None, FALLBACK_IDENTITY_MISMATCH
    stance = returned.get("stance")
    if stance not in VALID_EVIDENCE_STANCES:
        return None, None, FALLBACK_INVALID_STANCE
    if stance == SUPPORTS_COUNTER_ALPHA:
        counter_alpha_id = returned.get("counter_alpha_id")
        if not counter_alpha_id:
            return None, None, FALLBACK_INVALID_COUNTER_ALPHA
        counter_alpha_id = str(counter_alpha_id)
        if counter_alpha_id not in canonical_conflict_partners(requested.target_alpha_id, taxonomy):
            return None, None, FALLBACK_INVALID_COUNTER_ALPHA
        return stance, counter_alpha_id, None
    return stance, None, None


def _apply_llm_result(candidate: dict[str, Any], stance: str, counter_alpha_id: str | None) -> None:
    candidate["evidence_stance"] = stance
    candidate["counter_alpha_id"] = counter_alpha_id
    # No LLM-produced reason-code taxonomy or confidence band exists (task
    # spec section 12 forbids asking for one) -- leaving the deterministic
    # classifier's own reason codes/band attached to a possibly different
    # LLM stance would misrepresent provenance, so they are cleared rather
    # than left stale.
    candidate["stance_reason_codes"] = []
    candidate["stance_confidence_band"] = None
    candidate["requires_manual_review"] = False
    candidate["stance_method"] = STANCE_METHOD_LLM
    candidate["stance_fallback_reason"] = None
    candidate["evidence_stance_version"] = LLM_CLASSIFIER_VERSION


def _apply_fallback(candidate: dict[str, Any], reason: str) -> None:
    """The candidate's ``evidence_stance``/``counter_alpha_id``/reason
    codes/band are already the correct deterministic.v1 values --
    ``alpha_mapper._attach_evidence_stance`` computed them unconditionally,
    before this module ever runs. Nothing is recomputed here; only the
    provenance fields are stamped."""
    candidate["stance_method"] = STANCE_METHOD_DETERMINISTIC_FALLBACK
    candidate["stance_fallback_reason"] = reason
    candidate["evidence_stance_version"] = DETERMINISTIC_CLASSIFIER_VERSION


class StanceRunStats:
    """Plain accumulator for the counts this Sprint's report/audit needs.
    Never itself a source of truth for any candidate's stance -- purely a
    tally of what ``apply_llm_stance_upgrade`` already wrote onto the
    candidate dicts."""

    def __init__(self) -> None:
        self.llm_gateway_used = False
        self.requested_count = 0
        self.llm_result_count = 0
        self.deterministic_fallback_count = 0
        self.fallback_reason_counts: dict[str, int] = dict.fromkeys(sorted(VALID_FALLBACK_REASONS), 0)
        self.batch_count = 0
        self.logical_provider_calls = 0
        self.real_provider_attempts = 0
        self.invalid_llm_output_admitted = 0

    def record_llm(self) -> None:
        self.llm_result_count += 1

    def record_fallback(self, reason: str) -> None:
        self.deterministic_fallback_count += 1
        if reason in self.fallback_reason_counts:
            self.fallback_reason_counts[reason] += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "llm_gateway_used": self.llm_gateway_used,
            "requested_count": self.requested_count,
            "llm_result_count": self.llm_result_count,
            "deterministic_fallback_count": self.deterministic_fallback_count,
            "fallback_reason_counts": dict(self.fallback_reason_counts),
            "batch_count": self.batch_count,
            "logical_provider_calls": self.logical_provider_calls,
            "real_provider_attempts": self.real_provider_attempts,
            "invalid_llm_output_admitted": self.invalid_llm_output_admitted,
        }


def _process_batch(
    batch: list[StanceRequestItem],
    taxonomy: Mapping[str, AlphaDefinition],
    llm_gateway: Any,
    stats: StanceRunStats,
) -> None:
    stats.batch_count += 1
    requested_by_key = {(item.claim_id, item.target_alpha_id): item for item in batch}
    try:
        payload = {"items": [item.payload for item in batch]}
        invocation = llm_gateway.invoke_json_with_trace(LLM_TASK_NAME, payload, _validate_batch_shape)
        stats.logical_provider_calls += 1
        stats.real_provider_attempts += max(0, int(getattr(invocation, "provider_attempt_count", 0) or 0))

        if not invocation.validation_accepted:
            reason = _reason_from_invocation(invocation)
            llm_gateway.finalize_semantic_invocation(invocation, accepted=False, fallback_reason=reason)
            for item in batch:
                _apply_fallback(item.candidate, reason)
                stats.record_fallback(reason)
            return

        llm_gateway.finalize_semantic_invocation(invocation, accepted=True)
        returned_items = invocation.validated_output or []

        by_key: dict[tuple[str, str], Any] = {}
        duplicate_keys: set[tuple[str, str]] = set()
        for returned in returned_items:
            if not isinstance(returned, Mapping):
                continue
            key = (str(returned.get("claim_id") or ""), str(returned.get("target_alpha_id") or ""))
            if key not in requested_by_key:
                continue  # extra unrequested result -- never admitted (section 13)
            if key in by_key:
                duplicate_keys.add(key)
            else:
                by_key[key] = returned

        for item in batch:
            key = (item.claim_id, item.target_alpha_id)
            if key in duplicate_keys:
                _apply_fallback(item.candidate, FALLBACK_DUPLICATE_RESULT)
                stats.record_fallback(FALLBACK_DUPLICATE_RESULT)
                continue
            returned = by_key.get(key)
            if returned is None:
                _apply_fallback(item.candidate, FALLBACK_MISSING_RESULT)
                stats.record_fallback(FALLBACK_MISSING_RESULT)
                continue
            stance, counter_alpha_id, reason = _validate_response_item(item, returned, taxonomy)
            if reason is not None:
                _apply_fallback(item.candidate, reason)
                stats.record_fallback(reason)
            else:
                _apply_llm_result(item.candidate, stance, counter_alpha_id)
                stats.record_llm()
    except Exception:
        # Fail-soft per task spec section 15: a bug/unexpected condition in
        # this batch's handling must never fail the research run or leave a
        # candidate without a usable stance -- fall back the whole batch to
        # its already-correct deterministic.v1 result.
        for item in batch:
            _apply_fallback(item.candidate, FALLBACK_PROVIDER_ERROR)
            stats.record_fallback(FALLBACK_PROVIDER_ERROR)


def apply_llm_stance_upgrade(
    matches: Sequence[Mapping[str, Any]],
    taxonomy: Mapping[str, AlphaDefinition],
    *,
    llm_gateway: Any = None,
) -> StanceRunStats:
    """Section 5/15: ``result = try_llm_stance(...); if valid(result): return
    result; else: return existing_deterministic_stance(...)`` -- applied per
    (claim_id, target_alpha_id), across the whole run, in batches of up to
    ``BATCH_SIZE``. When ``llm_gateway`` is ``None`` (the default -- every
    existing caller, and Architecture Replay, which never passes one), this
    is a guaranteed zero-cost no-op: ``matches`` is left exactly as
    ``map_structured_records`` already produced it."""
    stats = StanceRunStats()
    if llm_gateway is None:
        return stats
    stats.llm_gateway_used = True
    items = build_stance_request_items(matches, taxonomy)
    stats.requested_count = len(items)
    for batch in chunk_items(items, BATCH_SIZE):
        _process_batch(batch, taxonomy, llm_gateway, stats)
    return stats


__all__ = [
    "LLM_CLASSIFIER_VERSION",
    "LLM_TASK_NAME",
    "STANCE_METHOD_LLM",
    "STANCE_METHOD_DETERMINISTIC_FALLBACK",
    "FALLBACK_PROVIDER_ERROR",
    "FALLBACK_TIMEOUT",
    "FALLBACK_MALFORMED_RESPONSE",
    "FALLBACK_MISSING_RESULT",
    "FALLBACK_IDENTITY_MISMATCH",
    "FALLBACK_INVALID_STANCE",
    "FALLBACK_INVALID_COUNTER_ALPHA",
    "FALLBACK_DUPLICATE_RESULT",
    "VALID_FALLBACK_REASONS",
    "MAX_TARGET_ALPHAS_PER_CLAIM",
    "BATCH_SIZE",
    "StanceRequestItem",
    "StanceRunStats",
    "retained_target_alpha_ids",
    "build_stance_request_items",
    "chunk_items",
    "apply_llm_stance_upgrade",
]
