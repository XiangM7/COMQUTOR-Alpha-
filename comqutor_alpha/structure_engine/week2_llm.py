"""Controlled JSON-only LLM access for COMQUTOR Week 1-2 extraction tasks."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any, TypeVar

from comqutor_alpha.llm_runtime.canonical_json import sha256_text
from comqutor_alpha.llm_runtime.contracts import EXECUTION_POLICY_SCHEMA_VERSION
from comqutor_alpha.llm_runtime.session import SemanticCallTrace, SemanticRuntimeSession
from comqutor_alpha.storage.file_store import append_jsonl_record, validate_artifact_path

ERROR_LOG_ARTIFACT_PATH = "error_logs/week2_llm_errors.jsonl"
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_RETRIES = 1
DEFAULT_MAX_CALLS = 32
MAX_SERVER_RETRIES = 2
MAX_SERVER_CALLS = 100
MAX_PROMPT_PAYLOAD_CHARS = 60_000
# Phase 1B.1 only: invoke_prebuilt_json_prompt's own bound, sized for the
# Shadow prompt's shape (frozen instructions + full verbatim untrusted
# report + candidate-segment hints, which the Shadow contract's own
# StructuredOutputShadowParser already allows up to 500,000 report bytes)
# -- deliberately not MAX_PROMPT_PAYLOAD_CHARS, which is sized for the three
# existing tasks' compact JSON-only payloads and is unrelated to this one.
MAX_PREBUILT_PROMPT_CHARS = 2_000_000
# Phase 1 Master task-level execution policy override bound (invoke_prebuilt_
# json_prompt only): an outer safety clamp, never itself a target value --
# the product-owner-approved structured_claim_shadow policy (90s/0 retries)
# is well inside it. Never applied to the shared Gateway constructor
# defaults or to the three existing tasks' invoke_json(_with_trace) calls.
MAX_TASK_TIMEOUT_SECONDS = 300.0

T = TypeVar("T")

_TASK_INSTRUCTIONS = {
    "claim_batch_enrichment": (
        "Enrich each already-segmented claim in the supplied segments array. Return one JSON "
        "object with a claims array containing exactly one item per input segment, matched by "
        "segment_id. Each item must contain segment_id, claim, evidence, source_section, "
        "entities, factors, direction, and confidence. claim, evidence, and source_section must "
        "be returned byte-for-byte identical to the input segment with that segment_id -- never "
        "rewritten, merged with another segment, or split. Never omit a segment_id and never "
        "invent one that was not supplied."
    ),
    "alpha_classifier": (
        "Select at most one alpha from allowed_alpha_ids, or defer when the supplied admissible "
        "candidates cannot be distinguished. Return one JSON object with decision set to select "
        "or defer and selected_alpha_id set to an allowed ID or null. Do not create candidates, "
        "change admissibility, or provide a trading decision."
    ),
    "structure_extractor": (
        "Extract only evidence-backed relations between supplied allowed_factors. Return one JSON "
        "object with an edges array. Each edge must contain source_factor, target_factor, edge_type "
        "(causal, supportive, or conflicting), assertion_status (asserted, conditional, negated, "
        "mixed, or unknown), and confidence. Return an empty array when no relation is stated."
    ),
    "evidence_stance_classifier": (
        "For each item, classify only the Evidence's stance toward its own target_alpha_id -- never "
        "toward any other Alpha. Distinguish genuinely endorsing or rebutting the target Alpha's "
        "thesis from merely mentioning its subject matter, and read negation, rebuttal, "
        "qualification, conditional language, risk relief, and already-priced-in arguments on their "
        "actual meaning. Only report supports_counter_alpha when the Evidence itself materially "
        "supports one of the supplied counter_alphas' own thesis -- never merely because it opposes "
        "target_alpha_id. Return one JSON object with an items array containing exactly one result "
        "per input item, matched by claim_id and target_alpha_id, each with stance set to exactly "
        "one of supports_alpha, opposes_alpha, mentions_alpha, neutral_background, or "
        "supports_counter_alpha, and counter_alpha_id set to the supported counter Alpha's id only "
        "when stance is supports_counter_alpha, omitted otherwise. Use only the supplied claim_id, "
        "target_alpha_id, and counter Alpha ids -- never invent one."
    ),
}

_SHARED_JSON_ONLY_PROMPT_PREFIX = (
    "You are a constrained COMQUTOR extraction component. Return strict JSON only, with "
    "no markdown and no hidden reasoning. "
)
_INPUT_JSON_SEPARATOR = "\nINPUT_JSON:\n"
_PROMPT_IDENTITY_SEPARATOR = r"\nINPUT_JSON:\n"
_TASK_RUNTIME_METADATA = {
    "claim_batch_enrichment": {
        "semantic_task": "structured_adapter",
        "prompt_version": "week2.claim_batch_enrichment.v1",
        "input_schema_version": "week2.claim_batch_enrichment.input.v1",
        "output_schema_version": "week2.claim_batch_enrichment.output.v1",
        "taxonomy_version": None,
    },
    "alpha_classifier": {
        "semantic_task": "alpha_classifier",
        "prompt_version": "week2.alpha_classifier.v1",
        "input_schema_version": "week2.alpha_classifier.input.v1",
        "output_schema_version": "week2.alpha_classifier.output.v1",
        "taxonomy_version": "alpha_taxonomy_v1",
    },
    "structure_extractor": {
        "semantic_task": "structure_extractor",
        "prompt_version": "week2.structure_extractor.v1",
        "input_schema_version": "week2.structure_extractor.input.v1",
        "output_schema_version": "week2.structure_extractor.output.v1",
        "taxonomy_version": None,
    },
    "evidence_stance_classifier": {
        "semantic_task": "evidence_stance_classifier",
        "prompt_version": "evidence_stance.llm_classifier.v1",
        "input_schema_version": "evidence_stance.llm_classifier.input.v1",
        "output_schema_version": "evidence_stance.llm_classifier.output.v1",
        "taxonomy_version": "alpha_taxonomy_v1",
    },
}


@dataclass(frozen=True)
class Week2LLMInvocation:
    parsed_output: dict[str, Any] | None
    validated_output: Any | None
    trace_handle: SemanticCallTrace | None
    cache_hit: bool
    provider_called: bool
    provider_status: str
    retry_count: int
    provider_attempt_count: int
    validation_attempted: bool
    validation_accepted: bool
    error_code: str | None = None
    cache_error_code: str | None = None
    # Populated only by invoke_prebuilt_json_prompt when a caller supplies an
    # explicit per-call execution policy override; always None (unchanged)
    # for invoke_json/invoke_json_with_trace and for invoke_prebuilt_json_
    # prompt calls that don't pass an override.
    effective_timeout_seconds: float | None = None
    effective_max_retries: int | None = None
    execution_policy_source: str | None = None
    # Evaluation-only observability for the prebuilt Shadow seam. Existing
    # Week2 tasks leave these additive fields at their defaults.
    response_received: bool = False
    token_usage: Mapping[str, int | None] | None = None
    attempt_history: tuple[Mapping[str, Any], ...] = ()


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def call_with_timeout(function: Callable[[], T], timeout_seconds: float) -> T:
    """Run a blocking provider call with a caller-side wall-clock deadline."""
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="comqutor-week2-llm")
    future = executor.submit(function)
    try:
        return future.result(timeout=max(float(timeout_seconds), 0.01))
    except FutureTimeoutError as exc:
        future.cancel()
        raise TimeoutError("Week 2 LLM call timed out") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


# Real-Provider diagnostic finding (disclosed in full in
# docs/audit_artifacts/phase1_master/prompt_audit/
# v2_json_format_diagnostic_findings.json, and reconfirmed by the B1 Evidence
# Stance live 50-row validation): claude-sonnet-4-6 reliably wraps its JSON
# response in a ```json ... ``` markdown code fence for some task shapes,
# even though the shared JSON-only prompt prefix explicitly says "Return
# strict JSON only, with no markdown". The content INSIDE the fence is
# well-formed JSON -- the only defect is the envelope, not the model's
# semantic judgment. This regex strips exactly one whole-response leading/
# trailing fence and nothing else; if the content is not fence-wrapped, or
# what remains after stripping is still not valid JSON, this returns the
# input unchanged -- json.loads immediately below remains the sole,
# unweakened, fail-closed JSON authority. Never fuzzy-matches or repairs
# content INSIDE the JSON itself.
#
# This was originally implemented, model-specific-diagnosed, and tested only
# for the separate structured_claim_shadow gateway path
# (structured_output_shadow_provider._MarkdownFenceStrippingModel). It lives
# here, at the shared Week2LLMGateway parsing boundary every task's response
# passes through (invoke_json_with_trace, invoke_prebuilt_json_prompt, and
# the legacy path all call _strict_json_object), so every current and future
# named Week2 task benefits uniformly -- structured_output_shadow_provider.py
# now imports this same function instead of defining a second copy.
_MARKDOWN_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*\n(.*)\n```\s*$", re.DOTALL)


def strip_markdown_json_fence(text: str) -> str:
    match = _MARKDOWN_JSON_FENCE_RE.match(text.strip())
    return match.group(1) if match else text


def _strict_json_object(response: Any) -> dict[str, Any]:
    if isinstance(response, Mapping):
        return dict(response)
    content = response if isinstance(response, str) else getattr(response, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise ValueError("missing JSON response content")
    parsed = json.loads(strip_markdown_json_fence(content))
    if not isinstance(parsed, dict):
        raise ValueError("JSON response must be an object")
    return parsed


def _response_token_usage(response: Any) -> dict[str, int | None] | None:
    """Extract non-secret token counters from common Provider message shapes."""

    usage = getattr(response, "usage_metadata", None)
    if not isinstance(usage, Mapping):
        metadata = getattr(response, "response_metadata", None)
        if isinstance(metadata, Mapping):
            usage = metadata.get("usage") or metadata.get("token_usage")
    if not isinstance(usage, Mapping):
        return None

    def _count(*names: str) -> int | None:
        for name in names:
            value = usage.get(name)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                return value
        return None

    input_tokens = _count("input_tokens", "prompt_tokens", "input_token_count")
    output_tokens = _count("output_tokens", "completion_tokens", "output_token_count")
    total_tokens = _count("total_tokens", "total_token_count")
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _provider_status_code(exc: BaseException) -> int | None:
    for candidate in (exc, getattr(exc, "response", None)):
        value = getattr(candidate, "status_code", None)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def _transient_provider_error_reason(exc: BaseException) -> str | None:
    """Return a stable retry reason only for explicitly transient failures."""

    status_code = _provider_status_code(exc)
    if status_code == 429:
        return "HTTP_429"
    if status_code is not None and 500 <= status_code <= 599:
        return "HTTP_5XX"
    if isinstance(exc, (ConnectionError, OSError)):
        return "TRANSIENT_PROVIDER_TRANSPORT"
    class_name = type(exc).__name__.lower()
    if any(
        token in class_name
        for token in (
            "connecterror",
            "connectionerror",
            "networkerror",
            "remoteprotocolerror",
            "transporterror",
        )
    ):
        return "TRANSIENT_PROVIDER_TRANSPORT"
    return None


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(number, minimum), maximum)


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(number, minimum), maximum)


def _enabled(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def week2_llm_enabled() -> bool:
    """Return the existing explicit opt-in flag without changing its default."""

    return _enabled(os.environ.get("COMQUTOR_WEEK2_LLM_ENABLED"))


class Week2LLMGateway:
    """Strict JSON gateway with bounded retries, timeout, and per-run call budget."""

    def __init__(
        self,
        model: Any,
        *,
        run_id: str,
        output_root: Any,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        max_calls: int = DEFAULT_MAX_CALLS,
        provider: str | None = None,
        model_name: str | None = None,
        semantic_runtime: SemanticRuntimeSession | None = None,
        error_log_artifact_path: str = ERROR_LOG_ARTIFACT_PATH,
    ) -> None:
        self._model = model
        self.run_id = str(run_id)
        self.output_root = output_root
        self.timeout_seconds = max(float(timeout_seconds), 0.01)
        self.max_retries = min(max(int(max_retries), 0), MAX_SERVER_RETRIES)
        self.max_calls = min(max(int(max_calls), 1), MAX_SERVER_CALLS)
        self._call_count = 0
        self._budget_exhaustion_logged = False
        self._lock = Lock()
        self.provider = str(provider or "UNKNOWN_NOT_INSTRUMENTED")
        self.model_name = str(model_name or "UNKNOWN_NOT_INSTRUMENTED")
        self.semantic_runtime = semantic_runtime
        self.error_log_artifact_path = validate_artifact_path(error_log_artifact_path)

    @property
    def call_count(self) -> int:
        with self._lock:
            return self._call_count

    def _reserve_call(self) -> bool:
        with self._lock:
            if self._call_count >= self.max_calls:
                return False
            self._call_count += 1
            return True

    def _log(self, task: str, error_code: str, attempt: int) -> None:
        append_jsonl_record(
            self.run_id,
            self.error_log_artifact_path,
            {
                "run_id": self.run_id,
                "task": task,
                "error_code": error_code,
                "attempt": attempt,
                "created_at": _now(),
            },
            output_root=self.output_root,
        )

    def _log_budget_exhausted_once(self, task: str, attempt: int) -> None:
        with self._lock:
            if self._budget_exhaustion_logged:
                return
            self._budget_exhaustion_logged = True
        self._log(task, "WEEK2_LLM_CALL_BUDGET_EXHAUSTED", attempt)

    def _log_runtime_error(self, task: str, error_code: str) -> None:
        """Keep cache/recording diagnostics outside the business-result path."""

        try:
            self._log(task, error_code, 0)
        except Exception:
            if self.semantic_runtime is not None:
                self.semantic_runtime.report_degraded(
                    "SEMANTIC_RUNTIME_ERROR_LOG_FAILED"
                )

    def attach_semantic_runtime(self, semantic_runtime: SemanticRuntimeSession) -> None:
        if not isinstance(semantic_runtime, SemanticRuntimeSession):
            raise TypeError("semantic_runtime must be a SemanticRuntimeSession")
        if semantic_runtime.run_id != self.run_id:
            raise ValueError("SEMANTIC_RUNTIME_RUN_ID_MISMATCH")
        self.semantic_runtime = semantic_runtime

    @staticmethod
    def prompt_identity_text(task: str) -> str:
        instruction = _TASK_INSTRUCTIONS.get(task)
        if instruction is None:
            raise ValueError(f"Unsupported Week 2 LLM task: {task}")
        return f"{_SHARED_JSON_ONLY_PROMPT_PREFIX}{instruction}{_PROMPT_IDENTITY_SEPARATOR}"

    @staticmethod
    def _provider_prompt_prefix(task: str) -> str:
        instruction = _TASK_INSTRUCTIONS.get(task)
        if instruction is None:
            raise ValueError(f"Unsupported Week 2 LLM task: {task}")
        return f"{_SHARED_JSON_ONLY_PROMPT_PREFIX}{instruction}{_INPUT_JSON_SEPARATOR}"

    @classmethod
    def prompt_identity_sha256(cls, task: str) -> str:
        return sha256_text(cls.prompt_identity_text(task))

    def _start_semantic_call(
        self,
        task: str,
        payload: Mapping[str, Any],
    ) -> tuple[SemanticCallTrace | None, Any | None, str | None]:
        if self.semantic_runtime is None:
            return None, None, None
        metadata = _TASK_RUNTIME_METADATA[task]
        started = self.semantic_runtime.start_call(
            task=metadata["semantic_task"],
            prompt_version=metadata["prompt_version"],
            prompt_sha256=self.prompt_identity_sha256(task),
            input_schema_version=metadata["input_schema_version"],
            output_schema_version=metadata["output_schema_version"],
            taxonomy_version=metadata["taxonomy_version"],
            input_payload=payload,
        )
        return started.trace_handle, started.cached_candidate, started.cache_error_code

    def invoke_json_with_trace(
        self,
        task: str,
        payload: Mapping[str, Any],
        validator: Callable[[Mapping[str, Any]], T],
    ) -> Week2LLMInvocation:
        """Run one logical request while leaving persistence finalization to its caller."""

        instruction = _TASK_INSTRUCTIONS.get(task)
        if instruction is None:
            raise ValueError(f"Unsupported Week 2 LLM task: {task}")
        serialized = json.dumps(dict(payload), ensure_ascii=False, default=str)
        prompt = f"{self._provider_prompt_prefix(task)}{serialized}"
        trace, cached_candidate, cache_error_code = self._start_semantic_call(task, payload)

        if cached_candidate is not None:
            try:
                if not isinstance(cached_candidate, Mapping):
                    raise TypeError("cached task candidate must be an object")
                validated = validator(cached_candidate)
            except Exception:
                cache_error_code = "WEEK2_LLM_CACHE_VALIDATION_FAILED"
                if trace is not None:
                    trace.cache_hit = False
                    trace.cache_error_code = cache_error_code
                if self.semantic_runtime is not None:
                    self.semantic_runtime.report_degraded(cache_error_code)
                self._log_runtime_error(task, cache_error_code)
            else:
                return Week2LLMInvocation(
                    parsed_output=dict(cached_candidate),
                    validated_output=validated,
                    trace_handle=trace,
                    cache_hit=True,
                    provider_called=False,
                    provider_status="not_called",
                    retry_count=0,
                    provider_attempt_count=0,
                    validation_attempted=True,
                    validation_accepted=True,
                    cache_error_code=cache_error_code,
                )
        elif cache_error_code is not None:
            self._log_runtime_error(task, "WEEK2_LLM_CACHE_READ_FAILED")

        if len(serialized) > MAX_PROMPT_PAYLOAD_CHARS:
            self._log(task, "WEEK2_LLM_INPUT_TOO_LARGE", 0)
            return Week2LLMInvocation(
                parsed_output=None,
                validated_output=None,
                trace_handle=trace,
                cache_hit=False,
                provider_called=False,
                provider_status="not_called",
                retry_count=0,
                provider_attempt_count=0,
                validation_attempted=False,
                validation_accepted=False,
                error_code="WEEK2_LLM_INPUT_TOO_LARGE",
                cache_error_code=cache_error_code,
            )

        provider_attempts = 0
        validation_attempted = False
        last_parsed: dict[str, Any] | None = None
        last_provider_status = "provider_error"
        last_error_code: str | None = "WEEK2_LLM_PROVIDER_ERROR"
        for attempt in range(1, self.max_retries + 2):
            if not self._reserve_call():
                self._log_budget_exhausted_once(task, attempt)
                if provider_attempts == 0:
                    last_provider_status = "budget_exhausted"
                    last_error_code = "WEEK2_LLM_CALL_BUDGET_EXHAUSTED"
                break
            provider_attempts += 1
            try:
                response = call_with_timeout(
                    lambda: self._model.invoke(prompt),
                    self.timeout_seconds,
                )
                last_parsed = _strict_json_object(response)
                validation_attempted = True
                validated = validator(last_parsed)
                return Week2LLMInvocation(
                    parsed_output=last_parsed,
                    validated_output=validated,
                    trace_handle=trace,
                    cache_hit=False,
                    provider_called=True,
                    provider_status="success",
                    retry_count=max(0, provider_attempts - 1),
                    provider_attempt_count=provider_attempts,
                    validation_attempted=True,
                    validation_accepted=True,
                    cache_error_code=cache_error_code,
                )
            except TimeoutError:
                last_provider_status = "timeout"
                last_error_code = "WEEK2_LLM_TIMEOUT"
            except json.JSONDecodeError:
                last_provider_status = "provider_error"
                last_error_code = "WEEK2_LLM_INVALID_JSON"
            except (TypeError, ValueError, KeyError):
                last_provider_status = "success"
                last_error_code = "WEEK2_LLM_VALIDATION_FAILED"
            except Exception:
                last_provider_status = "provider_error"
                last_error_code = "WEEK2_LLM_PROVIDER_ERROR"
            self._log(task, last_error_code, attempt)

        return Week2LLMInvocation(
            parsed_output=last_parsed,
            validated_output=None,
            trace_handle=trace,
            cache_hit=False,
            provider_called=provider_attempts > 0,
            provider_status=last_provider_status,
            retry_count=max(0, provider_attempts - 1),
            provider_attempt_count=provider_attempts,
            validation_attempted=validation_attempted,
            validation_accepted=False,
            error_code=last_error_code,
            cache_error_code=cache_error_code,
        )

    def invoke_prebuilt_json_prompt(
        self,
        *,
        task: str,
        prompt: str,
        prompt_version: str,
        prompt_sha256: str,
        input_schema_version: str,
        output_schema_version: str,
        payload_for_identity: Mapping[str, Any],
        validator: Callable[[Mapping[str, Any]], T],
        taxonomy_version: str | None = None,
        max_prompt_chars: int = MAX_PREBUILT_PROMPT_CHARS,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        execution_policy_source: str | None = None,
    ) -> Week2LLMInvocation:
        """Send an already-fully-built prompt through the existing retry/
        timeout/budget/semantic-runtime machinery, without touching the fixed
        ``_TASK_INSTRUCTIONS``/``_TASK_RUNTIME_METADATA`` tables the three
        existing Week2 tasks (``claim_batch_enrichment``, ``alpha_classifier``,
        ``structure_extractor``) use for their own prompt/version identity.

        Phase 1B.1 evaluation-CLI-only seam: the caller supplies the frozen
        Phase 1A Shadow prompt text verbatim (never built or altered here) and
        its own prompt/schema identity. This method never reads
        ``_TASK_INSTRUCTIONS`` and therefore cannot silently reuse or drift
        one of the three existing task prompts. By default, retry, timeout,
        and the per-run call budget are the same ``self.max_retries``/
        ``self.timeout_seconds``/``self._reserve_call()`` the three existing
        tasks already use -- no new retry behavior is introduced.

        ``timeout_seconds``/``max_retries`` (Phase 1 Master task-level
        execution policy, section 3): when explicitly supplied by the
        caller, they override the Gateway's shared instance defaults for
        THIS call only -- ``self.timeout_seconds``/``self.max_retries``
        (the constructor defaults shared by every other call, including the
        three existing tasks) are never mutated. Never derived from Provider
        output or report text; always a literal caller-supplied value.
        """
        effective_timeout = self.timeout_seconds
        if timeout_seconds is not None:
            effective_timeout = min(max(float(timeout_seconds), 0.01), MAX_TASK_TIMEOUT_SECONDS)
        effective_retries = self.max_retries
        if max_retries is not None:
            effective_retries = min(max(int(max_retries), 0), MAX_SERVER_RETRIES)

        trace: SemanticCallTrace | None = None
        cached_candidate: Any | None = None
        cache_error_code: str | None = None
        if self.semantic_runtime is not None:
            started = self.semantic_runtime.start_call(
                task=task,
                prompt_version=prompt_version,
                prompt_sha256=prompt_sha256,
                input_schema_version=input_schema_version,
                output_schema_version=output_schema_version,
                taxonomy_version=taxonomy_version,
                input_payload=payload_for_identity,
            )
            trace, cached_candidate, cache_error_code = (
                started.trace_handle,
                started.cached_candidate,
                started.cache_error_code,
            )

        if cached_candidate is not None:
            try:
                if not isinstance(cached_candidate, Mapping):
                    raise TypeError("cached task candidate must be an object")
                validated = validator(cached_candidate)
            except Exception:
                cache_error_code = "WEEK2_LLM_CACHE_VALIDATION_FAILED"
                if trace is not None:
                    trace.cache_hit = False
                    trace.cache_error_code = cache_error_code
                if self.semantic_runtime is not None:
                    self.semantic_runtime.report_degraded(cache_error_code)
                self._log_runtime_error(task, cache_error_code)
            else:
                return Week2LLMInvocation(
                    parsed_output=dict(cached_candidate),
                    validated_output=validated,
                    trace_handle=trace,
                    cache_hit=True,
                    provider_called=False,
                    provider_status="not_called",
                    retry_count=0,
                    provider_attempt_count=0,
                    validation_attempted=True,
                    validation_accepted=True,
                    cache_error_code=cache_error_code,
                    effective_timeout_seconds=effective_timeout,
                    effective_max_retries=effective_retries,
                    execution_policy_source=execution_policy_source,
                )
        elif cache_error_code is not None:
            self._log_runtime_error(task, "WEEK2_LLM_CACHE_READ_FAILED")

        if len(prompt) > max_prompt_chars:
            self._log(task, "WEEK2_LLM_INPUT_TOO_LARGE", 0)
            return Week2LLMInvocation(
                parsed_output=None,
                validated_output=None,
                trace_handle=trace,
                cache_hit=False,
                provider_called=False,
                provider_status="not_called",
                retry_count=0,
                provider_attempt_count=0,
                validation_attempted=False,
                validation_accepted=False,
                error_code="WEEK2_LLM_INPUT_TOO_LARGE",
                cache_error_code=cache_error_code,
                effective_timeout_seconds=effective_timeout,
                effective_max_retries=effective_retries,
                execution_policy_source=execution_policy_source,
            )

        provider_attempts = 0
        validation_attempted = False
        last_parsed: dict[str, Any] | None = None
        last_provider_status = "provider_error"
        last_error_code: str | None = "WEEK2_LLM_PROVIDER_ERROR"
        response_received = False
        token_usage: dict[str, int | None] | None = None
        attempt_history: list[dict[str, Any]] = []
        for attempt in range(1, effective_retries + 2):
            if not self._reserve_call():
                self._log_budget_exhausted_once(task, attempt)
                if provider_attempts == 0:
                    last_provider_status = "budget_exhausted"
                    last_error_code = "WEEK2_LLM_CALL_BUDGET_EXHAUSTED"
                    attempt_history.append(
                        {
                            "attempt": attempt,
                            "status": "budget_exhausted",
                            "retry_eligible": False,
                            "retry_reason": None,
                            "retry_delay_seconds": None,
                            "error_code": last_error_code,
                        }
                    )
                break
            provider_attempts += 1
            try:
                response = call_with_timeout(
                    lambda: self._model.invoke(prompt),
                    effective_timeout,
                )
                response_received = True
                token_usage = _response_token_usage(response)
            except TimeoutError:
                last_provider_status = "timeout"
                last_error_code = "WEEK2_LLM_TIMEOUT"
                retry_reason = "TIMEOUT"
                should_retry = attempt <= effective_retries
                attempt_history.append(
                    {
                        "attempt": attempt,
                        "status": "timeout",
                        "retry_eligible": True,
                        "retry_reason": retry_reason,
                        "retry_delay_seconds": 0.0 if should_retry else None,
                        "error_code": last_error_code,
                    }
                )
                self._log(task, last_error_code, attempt)
                if should_retry:
                    continue
                break
            except Exception as exc:
                last_provider_status = "provider_error"
                last_error_code = "WEEK2_LLM_PROVIDER_ERROR"
                retry_reason = _transient_provider_error_reason(exc)
                should_retry = retry_reason is not None and attempt <= effective_retries
                attempt_history.append(
                    {
                        "attempt": attempt,
                        "status": "provider_error",
                        "retry_eligible": retry_reason is not None,
                        "retry_reason": retry_reason,
                        "retry_delay_seconds": 0.0 if should_retry else None,
                        "error_code": last_error_code,
                    }
                )
                self._log(task, last_error_code, attempt)
                if should_retry:
                    continue
                break

            try:
                last_parsed = _strict_json_object(response)
            except (json.JSONDecodeError, TypeError, ValueError):
                last_provider_status = "provider_error"
                last_error_code = "WEEK2_LLM_INVALID_JSON"
                attempt_history.append(
                    {
                        "attempt": attempt,
                        "status": "invalid_json",
                        "retry_eligible": False,
                        "retry_reason": None,
                        "retry_delay_seconds": None,
                        "error_code": last_error_code,
                    }
                )
                self._log(task, last_error_code, attempt)
                break

            validation_attempted = True
            try:
                validated = validator(last_parsed)
            except (TypeError, ValueError, KeyError):
                last_provider_status = "success"
                last_error_code = "WEEK2_LLM_VALIDATION_FAILED"
                attempt_history.append(
                    {
                        "attempt": attempt,
                        "status": "validation_rejected",
                        "retry_eligible": False,
                        "retry_reason": None,
                        "retry_delay_seconds": None,
                        "error_code": last_error_code,
                    }
                )
                self._log(task, last_error_code, attempt)
                break
            else:
                attempt_history.append(
                    {
                        "attempt": attempt,
                        "status": "success",
                        "retry_eligible": False,
                        "retry_reason": None,
                        "retry_delay_seconds": None,
                        "error_code": None,
                    }
                )
                return Week2LLMInvocation(
                    parsed_output=last_parsed,
                    validated_output=validated,
                    trace_handle=trace,
                    cache_hit=False,
                    provider_called=True,
                    provider_status="success",
                    retry_count=max(0, provider_attempts - 1),
                    provider_attempt_count=provider_attempts,
                    validation_attempted=True,
                    validation_accepted=True,
                    cache_error_code=cache_error_code,
                    effective_timeout_seconds=effective_timeout,
                    effective_max_retries=effective_retries,
                    execution_policy_source=execution_policy_source,
                    response_received=True,
                    token_usage=token_usage,
                    attempt_history=tuple(attempt_history),
                )

        return Week2LLMInvocation(
            parsed_output=last_parsed,
            validated_output=None,
            trace_handle=trace,
            cache_hit=False,
            provider_called=provider_attempts > 0,
            provider_status=last_provider_status,
            retry_count=max(0, provider_attempts - 1),
            provider_attempt_count=provider_attempts,
            validation_attempted=validation_attempted,
            validation_accepted=False,
            error_code=last_error_code,
            cache_error_code=cache_error_code,
            effective_timeout_seconds=effective_timeout,
            effective_max_retries=effective_retries,
            execution_policy_source=execution_policy_source,
            response_received=response_received,
            token_usage=token_usage,
            attempt_history=tuple(attempt_history),
        )

    def finalize_semantic_invocation(
        self,
        invocation: Week2LLMInvocation,
        *,
        accepted: bool,
        fallback_reason: str | None = None,
    ) -> None:
        """Persist/cache after the task-specific caller accepts or rejects."""

        if self.semantic_runtime is None or invocation.trace_handle is None:
            return
        execution_policy = None
        if invocation.execution_policy_source is not None:
            execution_policy = {
                "schema_version": EXECUTION_POLICY_SCHEMA_VERSION,
                "effective_timeout_seconds": invocation.effective_timeout_seconds,
                "effective_max_retries": invocation.effective_max_retries,
                "execution_policy_source": invocation.execution_policy_source,
                "first_attempt_status": (
                    invocation.attempt_history[0].get("status")
                    if invocation.attempt_history
                    else None
                ),
                "retry_reason": next(
                    (
                        item.get("retry_reason")
                        for item in invocation.attempt_history
                        if item.get("retry_delay_seconds") is not None
                    ),
                    None,
                ),
                "retry_delay_seconds": next(
                    (
                        item.get("retry_delay_seconds")
                        for item in invocation.attempt_history
                        if item.get("retry_delay_seconds") is not None
                    ),
                    None,
                ),
                "final_status": (
                    invocation.attempt_history[-1].get("status")
                    if invocation.attempt_history
                    else invocation.provider_status
                ),
                "attempt_history": [dict(item) for item in invocation.attempt_history],
            }
        try:
            if accepted:
                self.semantic_runtime.finalize_call(
                    invocation.trace_handle,
                    provider_status=invocation.provider_status,
                    retry_count=invocation.retry_count,
                    validation_status="accepted",
                    accepted_candidate=invocation.parsed_output,
                    fallback_used=False,
                    fallback_reason=None,
                    error_code=None,
                    execution_policy=execution_policy,
                    token_usage=invocation.token_usage,
                )
                return

            validation_status = "rejected" if invocation.validation_attempted else "not_run"
            reason = fallback_reason or invocation.error_code or "WEEK2_LLM_DETERMINISTIC_FALLBACK"
            persisted_error_code = (
                invocation.error_code
                if invocation.provider_status in {"timeout", "provider_error", "budget_exhausted"}
                else (
                    invocation.error_code if invocation.provider_status == "not_called" else None
                )
            )
            self.semantic_runtime.finalize_call(
                invocation.trace_handle,
                provider_status=invocation.provider_status,
                retry_count=invocation.retry_count,
                validation_status=validation_status,
                accepted_candidate=None,
                fallback_used=True,
                fallback_reason=reason,
                error_code=persisted_error_code,
                execution_policy=execution_policy,
                token_usage=invocation.token_usage,
            )
        except Exception:
            self.semantic_runtime.report_degraded(
                "SEMANTIC_CALL_FINALIZATION_FAILED"
            )

    def _invoke_json_legacy(
        self,
        task: str,
        payload: Mapping[str, Any],
        validator: Callable[[Mapping[str, Any]], T],
    ) -> T | None:
        """The pre-Phase-0.6B execution path, retained byte-for-byte in behavior."""

        instruction = _TASK_INSTRUCTIONS.get(task)
        if instruction is None:
            raise ValueError(f"Unsupported Week 2 LLM task: {task}")

        serialized = json.dumps(dict(payload), ensure_ascii=False, default=str)
        if len(serialized) > MAX_PROMPT_PAYLOAD_CHARS:
            self._log(task, "WEEK2_LLM_INPUT_TOO_LARGE", 0)
            return None
        prompt = f"{self._provider_prompt_prefix(task)}{serialized}"

        for attempt in range(1, self.max_retries + 2):
            if not self._reserve_call():
                self._log_budget_exhausted_once(task, attempt)
                return None
            try:
                response = call_with_timeout(
                    lambda: self._model.invoke(prompt),
                    self.timeout_seconds,
                )
                parsed = _strict_json_object(response)
                return validator(parsed)
            except TimeoutError:
                error_code = "WEEK2_LLM_TIMEOUT"
            except json.JSONDecodeError:
                error_code = "WEEK2_LLM_INVALID_JSON"
            except (TypeError, ValueError, KeyError):
                error_code = "WEEK2_LLM_VALIDATION_FAILED"
            except Exception:
                error_code = "WEEK2_LLM_PROVIDER_ERROR"
            self._log(task, error_code, attempt)
        return None

    def invoke_json(
        self,
        task: str,
        payload: Mapping[str, Any],
        validator: Callable[[Mapping[str, Any]], T],
    ) -> T | None:
        if self.semantic_runtime is None:
            return self._invoke_json_legacy(task, payload, validator)
        invocation = self.invoke_json_with_trace(task, payload, validator)
        accepted = invocation.validation_accepted
        self.finalize_semantic_invocation(invocation, accepted=accepted)
        return invocation.validated_output if accepted else None


def _log_configuration_error(run_id: str, output_root: Any, error_code: str) -> None:
    append_jsonl_record(
        run_id,
        ERROR_LOG_ARTIFACT_PATH,
        {
            "run_id": run_id,
            "task": "gateway_initialization",
            "error_code": error_code,
            "attempt": 0,
            "created_at": _now(),
        },
        output_root=output_root,
    )


def build_server_week2_llm_gateway(run_id: str, output_root: Any) -> Week2LLMGateway | None:
    """Build the existing TradingAgents provider only after explicit server opt-in."""
    if not week2_llm_enabled():
        return None

    provider = (
        os.environ.get("COMQUTOR_WEEK2_LLM_PROVIDER")
        or os.environ.get("TRADINGAGENTS_LLM_PROVIDER")
        or ""
    ).strip()
    model_name = (
        os.environ.get("COMQUTOR_WEEK2_LLM_MODEL")
        or os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM")
        or ""
    ).strip()
    if not provider or not model_name:
        _log_configuration_error(run_id, output_root, "WEEK2_LLM_CONFIG_INCOMPLETE")
        return None

    timeout_seconds = _bounded_float(
        os.environ.get("COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS"),
        DEFAULT_TIMEOUT_SECONDS,
        1.0,
        120.0,
    )
    max_retries = _bounded_int(
        os.environ.get("COMQUTOR_WEEK2_LLM_MAX_RETRIES"),
        DEFAULT_MAX_RETRIES,
        0,
        MAX_SERVER_RETRIES,
    )
    max_calls = _bounded_int(
        os.environ.get("COMQUTOR_WEEK2_LLM_MAX_CALLS"),
        DEFAULT_MAX_CALLS,
        1,
        MAX_SERVER_CALLS,
    )
    base_url = (
        os.environ.get("COMQUTOR_WEEK2_LLM_BASE_URL")
        or os.environ.get("TRADINGAGENTS_LLM_BACKEND_URL")
        or None
    )

    try:
        from tradingagents.llm_clients import create_llm_client

        client = create_llm_client(
            provider=provider,
            model=model_name,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=0,
        )
        model = client.get_llm()
    except Exception:
        _log_configuration_error(run_id, output_root, "WEEK2_LLM_INITIALIZATION_FAILED")
        return None

    return Week2LLMGateway(
        model,
        run_id=run_id,
        output_root=output_root,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        max_calls=max_calls,
        provider=provider,
        model_name=model_name,
    )
