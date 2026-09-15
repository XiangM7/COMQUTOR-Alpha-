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

import threading
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from comqutor_alpha.alpha_library.alpha_schema import AlphaDefinition
from comqutor_alpha.structure_engine.evidence_stance import (
    CLASSIFIER_VERSION as DETERMINISTIC_CLASSIFIER_VERSION,
    SUPPORTS_COUNTER_ALPHA,
    VALID_EVIDENCE_STANCES,
    canonical_conflict_partners,
)
from comqutor_alpha.structure_engine.week2_llm import resolve_evidence_stance_concurrency

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
    candidate dicts.

    John Requirement B, Phase B2 Slice 2A: this is the ONE piece of state
    ``apply_llm_stance_upgrade`` mutates that is genuinely SHARED across
    batches (unlike each item's own ``candidate`` dict, which belongs to
    exactly one batch). Under bounded concurrency, multiple worker threads
    can call ``record_llm``/``record_fallback``/increment the counters
    below at the same time -- a plain ``+=``/dict-increment is not
    guaranteed atomic across threads, so every mutating method is
    lock-protected. This is the minimum synchronization needed to keep
    these counts accurate; it adds no behavior change for the existing
    concurrency=1 (serial) case."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
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
        with self._lock:
            self.llm_result_count += 1

    def record_fallback(self, reason: str) -> None:
        with self._lock:
            self.deterministic_fallback_count += 1
            if reason in self.fallback_reason_counts:
                self.fallback_reason_counts[reason] += 1

    def record_batch_started(self) -> None:
        with self._lock:
            self.batch_count += 1

    def record_provider_attempt(self, real_attempts: int) -> None:
        with self._lock:
            self.logical_provider_calls += 1
            self.real_provider_attempts += max(0, int(real_attempts))

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


def _invoke_batch(
    batch: list[StanceRequestItem],
    llm_gateway: Any,
) -> tuple[Any | None, Exception | None]:
    """Phase 1 (John Requirement B, Phase B2 Slice 2A): issue the Provider
    request only -- the part safe to run concurrently across batches. Never
    raises; an exception is captured and returned so phase 2 can apply the
    exact same fail-soft fallback the original single-phase implementation
    used, regardless of which phase raised it."""
    try:
        payload = {"items": [item.payload for item in batch]}
        invocation = llm_gateway.invoke_json_with_trace(LLM_TASK_NAME, payload, _validate_batch_shape)
        return invocation, None
    except Exception as exc:
        return None, exc


def _finalize_batch(
    batch: list[StanceRequestItem],
    taxonomy: Mapping[str, AlphaDefinition],
    llm_gateway: Any,
    stats: StanceRunStats,
    invocation: Any | None,
    invoke_error: Exception | None,
) -> None:
    """Phase 2: gateway finalization (recorder/cache bookkeeping) and
    per-item result application. John Requirement B, Phase B2 Slice 2A:
    this phase must be called in ascending call_sequence order across
    batches (never in raw completion order) -- SemanticCallRecorder.append
    requires call_sequence to increase strictly for each run, and phase 1's
    concurrent execution means batches can finish, and therefore reach
    phase 2, in a different order than their sequence numbers were
    allocated in. The concurrent orchestration below sorts by each
    invocation's own trace_handle.call_sequence before calling this
    function, restoring the exact ordering the recorder (and downstream
    exact-replay validation, which enforces the identical invariant)
    already requires -- serial callers (concurrency<=1) call this
    immediately after phase 1 for each batch in turn, which is already in
    order by construction."""
    stats.record_batch_started()
    requested_by_key = {(item.claim_id, item.target_alpha_id): item for item in batch}
    try:
        if invoke_error is not None:
            raise invoke_error
        stats.record_provider_attempt(int(getattr(invocation, "provider_attempt_count", 0) or 0))

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


def _process_batch(
    batch: list[StanceRequestItem],
    taxonomy: Mapping[str, AlphaDefinition],
    llm_gateway: Any,
    stats: StanceRunStats,
) -> None:
    """Serial (concurrency<=1) path: phase 1 then phase 2 for one batch,
    back to back -- byte-for-byte the original single-phase behavior, since
    a single batch's own phase 2 always immediately follows its own phase
    1 with no other batch's work interleaved."""
    invocation, invoke_error = _invoke_batch(batch, llm_gateway)
    _finalize_batch(batch, taxonomy, llm_gateway, stats, invocation, invoke_error)


def _process_batches_concurrently(
    batches: list[list[StanceRequestItem]],
    taxonomy: Mapping[str, AlphaDefinition],
    llm_gateway: Any,
    stats: StanceRunStats,
    concurrency: int,
) -> None:
    """John Requirement B, Phase B2 Slice 2A: bounded concurrency for
    independent stance batches, mirroring alpha_mapper's own
    ``_classify_alpha_concurrent_with_llm`` pattern exactly.

    Safety, verified against the actual code (not assumed):
    - Batches are independent: each batch reads only the immutable
      ``taxonomy`` and writes onto its own items' ``candidate`` dicts,
      which are never shared with any other batch (``build_stance_request_
      items`` emits exactly one ``StanceRequestItem`` per retained
      (claim_id, target_alpha_id) pair, so no two batches ever reference
      the same candidate object).
    - No output-order dependency: results are written IN PLACE onto the
      pre-existing candidate dicts referenced from ``matches`` -- there is
      no list this function appends to or reorders, so the completion
      order of batches can never change the final artifact's order.
    - The only shared mutable state is ``stats`` -- already made
      thread-safe above (every mutating method is lock-protected).
    - Week2LLMGateway's call-budget counter and error logger, and
      SemanticRuntimeSession's cache/trace bookkeeping, are already
      lock-protected (the same infrastructure alpha_classifier's own
      concurrency=4 already relies on in production) -- concurrent workers
      cannot overshoot the shared call budget, corrupt the shared error
      log, or corrupt the semantic-call recorder.
    - No cross-batch cancellation: every submitted batch runs to
      completion (success or its own fail-soft fallback) independently --
      one batch's failure never discards or alters another batch's
      already-applied result.
    - Retry budget is not multiplied by concurrency: each batch's own
      ``invoke_json_with_trace`` call performs its own bounded retry loop
      exactly as it does when called serially; concurrency changes only
      how many batches are in flight at once, never how many attempts any
      one batch gets.
    - Deterministic recorder ordering: phase 1 (``_invoke_batch``, which
      allocates each batch's ``call_sequence`` and performs the actual
      Provider request) runs concurrently and can COMPLETE in a different
      order than sequence numbers were allocated in. Phase 2
      (``_finalize_batch``, which calls the gateway's
      ``finalize_semantic_invocation`` and therefore
      ``SemanticCallRecorder.append``) is run here in the MAIN thread only,
      strictly in ascending ``trace_handle.call_sequence`` order -- exactly
      the invariant ``SemanticCallRecorder.append`` (and downstream
      exact-replay validation) already requires for every task, not a new
      rule introduced by this slice. This was verified necessary by direct
      testing: dispatching phase 1 AND phase 2 together inside worker
      threads (naively mirroring alpha_classifier's own concurrent
      pattern) reproducibly triggered ``RECORDER_SEQUENCE_NOT_MONOTONIC``
      once batch completion order diverged from allocation order -- a
      latent race in the shared concurrent-dispatch pattern that this
      slice's own testing surfaced and fixes locally, without touching
      ``session.py``, ``recorder.py``, or alpha_classifier's own code path.
    """
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="comqutor-evidence-stance") as executor:
        futures = [executor.submit(_invoke_batch, batch, llm_gateway) for batch in batches]
        completed = [future.result() for future in futures]  # (invocation, invoke_error) per batch, submission order

    def _sequence_key(pair: tuple[Any | None, Exception | None]) -> float:
        invocation, _ = pair
        trace = getattr(invocation, "trace_handle", None)
        sequence = getattr(trace, "call_sequence", None)
        # A batch with no trace (llm_gateway had no attached semantic_runtime,
        # or trace allocation itself failed) never reaches the recorder, so
        # its relative position cannot violate the sequence invariant --
        # ordered last is an arbitrary-but-safe placement, never a
        # correctness issue.
        return sequence if isinstance(sequence, int) else float("inf")

    for (batch, (invocation, invoke_error)) in sorted(
        zip(batches, completed), key=lambda pair: _sequence_key(pair[1])
    ):
        _finalize_batch(batch, taxonomy, llm_gateway, stats, invocation, invoke_error)


def apply_llm_stance_upgrade(
    matches: Sequence[Mapping[str, Any]],
    taxonomy: Mapping[str, AlphaDefinition],
    *,
    llm_gateway: Any = None,
    concurrency: int | None = None,
) -> StanceRunStats:
    """Section 5/15: ``result = try_llm_stance(...); if valid(result): return
    result; else: return existing_deterministic_stance(...)`` -- applied per
    (claim_id, target_alpha_id), across the whole run, in batches of up to
    ``BATCH_SIZE``. When ``llm_gateway`` is ``None`` (the default -- every
    existing caller, and Architecture Replay, which never passes one), this
    is a guaranteed zero-cost no-op: ``matches`` is left exactly as
    ``map_structured_records`` already produced it.

    ``concurrency`` (John Requirement B, Phase B2 Slice 2A): number of
    batches to process at once. ``None`` (the default) resolves to
    ``week2_llm.resolve_evidence_stance_concurrency()`` -- the same
    env-var-overridable, centrally-defined resolution pattern already used
    for ``alpha_classifier``. ``concurrency <= 1`` (or a single batch)
    reproduces the exact prior serial behavior with zero functional
    change -- only ``concurrency > 1`` with more than one batch dispatches
    through the bounded ThreadPoolExecutor path."""
    stats = StanceRunStats()
    if llm_gateway is None:
        return stats
    stats.llm_gateway_used = True
    items = build_stance_request_items(matches, taxonomy)
    stats.requested_count = len(items)
    batches = chunk_items(items, BATCH_SIZE)
    if concurrency is None:
        concurrency = resolve_evidence_stance_concurrency()
    if concurrency <= 1 or len(batches) <= 1:
        for batch in batches:
            _process_batch(batch, taxonomy, llm_gateway, stats)
    else:
        _process_batches_concurrently(batches, taxonomy, llm_gateway, stats, concurrency)
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
