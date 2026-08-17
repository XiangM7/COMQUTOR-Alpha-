"""Run-local, fail-soft orchestration for semantic-call persistence and cache use."""

from __future__ import annotations

import logging
import math
import re
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from comqutor_alpha.llm_runtime.cache import (
    LLMResponseCache,
    NullLLMResponseCache,
    build_llm_cache_key,
)
from comqutor_alpha.llm_runtime.canonical_json import sha256_canonical_json
from comqutor_alpha.llm_runtime.contracts import (
    SEMANTIC_CALL_SCHEMA_VERSION,
    cache_entry_from_record,
    redact_sensitive_text,
    validate_cache_entry,
)
from comqutor_alpha.llm_runtime.errors import CacheCorruptionError
from comqutor_alpha.llm_runtime.manifest import (
    build_semantic_manifest,
    write_semantic_manifest_atomic,
)
from comqutor_alpha.llm_runtime.recorder import SemanticCallRecorder

logger = logging.getLogger(__name__)

UNKNOWN_PROVIDER_OR_MODEL = "UNKNOWN_NOT_INSTRUMENTED"

_SENSITIVE_KEY_NAMES = frozenset(
    {
        "apikey",
        "authorization",
        "cookie",
        "password",
        "secret",
        "accesstoken",
        "refreshtoken",
        "privatekey",
    }
)
_HIDDEN_REASONING_KEY_NAMES = frozenset(
    {"chainofthought", "hiddenreasoning", "reasoningtrace", "internalreasoning"}
)


@dataclass
class SemanticCallTrace:
    """Opaque logical-call state allocated before cache or Provider work."""

    call_id: str
    call_sequence: int
    task: str
    prompt_version: str
    prompt_sha256: str
    input_schema_version: str
    output_schema_version: str
    taxonomy_version: str | None
    input_payload: dict[str, Any]
    input_sha256: str
    cache_key: str
    started_at: str
    started_monotonic: float
    cache_hit: bool = False
    cache_error_code: str | None = None
    finalized: bool = False


@dataclass(frozen=True)
class SemanticCallStart:
    trace_handle: SemanticCallTrace | None
    cached_candidate: Any | None
    cache_error_code: str | None = None


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z]", "", value.lower())


def _sanitize_payload(value: Any) -> tuple[Any, int]:
    """Return canonical-JSON-safe data with secrets/reasoning removed."""

    if isinstance(value, str):
        clean_value = redact_sensitive_text(value)
        return clean_value, int(clean_value != value)
    if value is None or isinstance(value, (bool, int)):
        return value, 0
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("SEMANTIC_RUNTIME_NON_FINITE_INPUT")
        return value, 0
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        redacted_count = 0
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("SEMANTIC_RUNTIME_NON_STRING_INPUT_KEY")
            normalized = _normalized_key(key)
            if normalized in _SENSITIVE_KEY_NAMES or normalized in _HIDDEN_REASONING_KEY_NAMES:
                redacted_count += 1
                continue
            clean_item, nested_count = _sanitize_payload(item)
            sanitized[key] = clean_item
            redacted_count += nested_count
        if redacted_count:
            sanitized["_redacted_sensitive_field_count"] = redacted_count
        return sanitized, redacted_count
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        sanitized_items = []
        redacted_count = 0
        for item in value:
            clean_item, nested_count = _sanitize_payload(item)
            sanitized_items.append(clean_item)
            redacted_count += nested_count
        return sanitized_items, redacted_count
    raise TypeError(f"SEMANTIC_RUNTIME_UNSUPPORTED_INPUT_TYPE:{type(value).__name__}")


class SemanticRuntimeSession:
    """Own one recorder/cache pair for all Week2 semantic calls in a run.

    All observability failures are contained here. Methods report success or
    return ``None`` but never change or replace the caller's business result.
    """

    def __init__(
        self,
        *,
        run_id: str,
        output_directory: str | Path,
        execution_mode: str,
        provider: str | None = None,
        model: str | None = None,
        profile_id: str | None = None,
        cache: LLMResponseCache | None = None,
        cache_ttl_seconds: int | None = None,
        recorder: SemanticCallRecorder | None = None,
        clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
        fsync: bool = False,
    ) -> None:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("SEMANTIC_RUNTIME_RUN_ID_INVALID")
        directory = Path(output_directory)
        if not directory.is_dir():
            raise ValueError("SEMANTIC_RUNTIME_OUTPUT_DIRECTORY_MISSING")
        if cache_ttl_seconds is not None and (
            not isinstance(cache_ttl_seconds, int)
            or isinstance(cache_ttl_seconds, bool)
            or cache_ttl_seconds <= 0
        ):
            raise ValueError("SEMANTIC_RUNTIME_CACHE_TTL_INVALID")

        self.run_id = run_id
        self.output_directory = directory.resolve()
        self.execution_mode = execution_mode
        self.provider = str(provider or UNKNOWN_PROVIDER_OR_MODEL)
        self.model = str(model or UNKNOWN_PROVIDER_OR_MODEL)
        self.profile_id = str(profile_id).strip() if profile_id is not None else None
        if self.profile_id == "":
            raise ValueError("SEMANTIC_RUNTIME_PROFILE_ID_INVALID")
        self.cache = cache or NullLLMResponseCache()
        self.cache_ttl_seconds = cache_ttl_seconds
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._monotonic = monotonic or time.monotonic
        self._lock = threading.Lock()
        self._next_sequence = 0
        self._outstanding_call_ids: set[str] = set()
        self._degraded_reason_codes: list[str] = []
        self._artifact_incomplete = False
        self._finalized = False
        self._manifest_path: Path | None = None
        self.created_at = self._timestamp()
        self.recorder = recorder or SemanticCallRecorder(
            run_id=run_id,
            output_directory=self.output_directory,
            mode=execution_mode,
            clock=self._clock,
            fsync=fsync,
            allow_run_artifacts=True,
        )
        try:
            self.recorder.ensure_artifact()
        except Exception as exc:  # fail-soft observability boundary
            self._mark_degraded("SEMANTIC_RECORDER_INITIALIZATION_FAILED", exc, incomplete=True)

    def _timestamp(self) -> str:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("SEMANTIC_RUNTIME_CLOCK_MUST_BE_TIMEZONE_AWARE")
        return value.isoformat()

    def _mark_degraded(
        self,
        reason_code: str,
        exc: BaseException | None = None,
        *,
        incomplete: bool = False,
    ) -> None:
        with self._lock:
            if reason_code not in self._degraded_reason_codes:
                self._degraded_reason_codes.append(reason_code)
            self._artifact_incomplete = self._artifact_incomplete or incomplete
        logger.warning(
            "semantic runtime degraded (run_id=%s, reason_code=%s, exc_type=%s)",
            self.run_id,
            reason_code,
            type(exc).__name__ if exc is not None else "None",
        )

    @property
    def degraded(self) -> bool:
        with self._lock:
            return bool(self._degraded_reason_codes)

    @property
    def incomplete(self) -> bool:
        with self._lock:
            return self._artifact_incomplete

    @property
    def degraded_reason_codes(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._degraded_reason_codes)

    @property
    def manifest_path(self) -> Path | None:
        return self._manifest_path

    def report_degraded(self, reason_code: str) -> None:
        """Record a stable non-artifact degradation such as cache rejection."""

        self._mark_degraded(reason_code)

    def _allocate_trace(
        self,
        *,
        task: str,
        prompt_version: str,
        prompt_sha256: str,
        input_schema_version: str,
        output_schema_version: str,
        taxonomy_version: str | None,
        input_payload: Mapping[str, Any],
    ) -> SemanticCallTrace:
        clean_payload, redacted_count = _sanitize_payload(dict(input_payload))
        if not isinstance(clean_payload, dict):  # defensive; input root is a mapping
            raise TypeError("SEMANTIC_RUNTIME_INPUT_NOT_OBJECT")
        if redacted_count:
            self._mark_degraded(
                "SEMANTIC_RUNTIME_INPUT_REDACTED",
                incomplete=True,
            )
        input_sha256 = sha256_canonical_json(clean_payload)
        cache_key = build_llm_cache_key(
            task=task,
            prompt_version=prompt_version,
            prompt_sha256=prompt_sha256,
            provider=self.provider,
            model=self.model,
            input_schema_version=input_schema_version,
            output_schema_version=output_schema_version,
            input_sha256=input_sha256,
            taxonomy_version=taxonomy_version,
            run_id=self.run_id,
        )
        with self._lock:
            sequence = self._next_sequence
            self._next_sequence += 1
            call_id = f"{self.run_id}:semantic:{sequence}:{uuid.uuid4().hex}"
            self._outstanding_call_ids.add(call_id)
        return SemanticCallTrace(
            call_id=call_id,
            call_sequence=sequence,
            task=task,
            prompt_version=prompt_version,
            prompt_sha256=prompt_sha256,
            input_schema_version=input_schema_version,
            output_schema_version=output_schema_version,
            taxonomy_version=taxonomy_version,
            input_payload=clean_payload,
            input_sha256=input_sha256,
            cache_key=cache_key,
            started_at=self._timestamp(),
            started_monotonic=self._monotonic(),
        )

    def start_call(
        self,
        *,
        task: str,
        prompt_version: str,
        prompt_sha256: str,
        input_schema_version: str,
        output_schema_version: str,
        input_payload: Mapping[str, Any],
        taxonomy_version: str | None = None,
    ) -> SemanticCallStart:
        try:
            trace = self._allocate_trace(
                task=task,
                prompt_version=prompt_version,
                prompt_sha256=prompt_sha256,
                input_schema_version=input_schema_version,
                output_schema_version=output_schema_version,
                taxonomy_version=taxonomy_version,
                input_payload=input_payload,
            )
        except Exception as exc:
            self._mark_degraded("SEMANTIC_RUNTIME_CALL_START_FAILED", exc, incomplete=True)
            return SemanticCallStart(None, None, "SEMANTIC_RUNTIME_CALL_START_FAILED")

        try:
            entry = self.cache.get(trace.cache_key)
        except CacheCorruptionError as exc:
            trace.cache_error_code = exc.reason_code
            self._mark_degraded(exc.reason_code, exc)
            return SemanticCallStart(trace, None, exc.reason_code)
        except Exception as exc:
            trace.cache_error_code = "SEMANTIC_CACHE_READ_FAILED"
            self._mark_degraded("SEMANTIC_CACHE_READ_FAILED", exc)
            return SemanticCallStart(trace, None, trace.cache_error_code)
        if entry is None:
            return SemanticCallStart(trace, None)

        if not isinstance(entry, Mapping):
            to_dict = getattr(entry, "to_dict", None)
            if callable(to_dict):
                try:
                    entry = to_dict()
                except Exception as exc:
                    trace.cache_error_code = "SEMANTIC_CACHE_ENTRY_INVALID"
                    self._mark_degraded(trace.cache_error_code, exc)
                    return SemanticCallStart(trace, None, trace.cache_error_code)
            if not isinstance(entry, Mapping):
                trace.cache_error_code = "SEMANTIC_CACHE_ENTRY_INVALID"
                self._mark_degraded(trace.cache_error_code)
                return SemanticCallStart(trace, None, trace.cache_error_code)
        cache_validation = validate_cache_entry(
            entry,
            expected_cache_key=trace.cache_key,
        )
        if not cache_validation.valid:
            trace.cache_error_code = cache_validation.reason_codes[0]
            self._mark_degraded(trace.cache_error_code)
            return SemanticCallStart(trace, None, trace.cache_error_code)
        expected = {
            "task": trace.task,
            "prompt_sha256": trace.prompt_sha256,
            "input_sha256": trace.input_sha256,
            "provider": self.provider,
            "model": self.model,
            "output_schema_version": trace.output_schema_version,
        }
        if any(entry.get(key) != value for key, value in expected.items()):
            trace.cache_error_code = "SEMANTIC_CACHE_IDENTITY_MISMATCH"
            self._mark_degraded(trace.cache_error_code)
            return SemanticCallStart(trace, None, trace.cache_error_code)
        trace.cache_hit = True
        return SemanticCallStart(trace, entry.get("validated_output"))

    def _claim_finalization(self, trace: SemanticCallTrace) -> bool:
        with self._lock:
            if trace.finalized:
                return False
            trace.finalized = True
            self._outstanding_call_ids.discard(trace.call_id)
            return True

    def finalize_call(
        self,
        trace: SemanticCallTrace | None,
        *,
        provider_status: str,
        retry_count: int,
        validation_status: str,
        accepted_candidate: Any | None,
        fallback_used: bool,
        fallback_reason: str | None,
        error_code: str | None,
        execution_policy: Mapping[str, Any] | None = None,
        token_usage: Mapping[str, int | None] | None = None,
    ) -> bool:
        if trace is None or not self._claim_finalization(trace):
            if trace is not None:
                self._mark_degraded("SEMANTIC_CALL_FINALIZED_TWICE", incomplete=True)
            return False
        try:
            safe_candidate = None
            if accepted_candidate is not None:
                safe_candidate, redacted_count = _sanitize_payload(accepted_candidate)
                if redacted_count:
                    self._mark_degraded(
                        "SEMANTIC_RUNTIME_OUTPUT_REDACTED",
                        incomplete=True,
                    )
            completed_at = self._timestamp()
            latency_ms = max(
                0.0,
                (self._monotonic() - trace.started_monotonic) * 1000.0,
            )
            safe_token_usage = {
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
            }
            if token_usage is not None:
                for key in safe_token_usage:
                    value = token_usage.get(key)
                    if value is not None and (
                        not isinstance(value, int) or isinstance(value, bool) or value < 0
                    ):
                        raise ValueError("SEMANTIC_RUNTIME_TOKEN_USAGE_INVALID")
                    safe_token_usage[key] = value

            record = {
                "schema_version": SEMANTIC_CALL_SCHEMA_VERSION,
                "call_id": trace.call_id,
                "run_id": self.run_id,
                "call_sequence": trace.call_sequence,
                "task": trace.task,
                "execution_mode": self.execution_mode,
                "prompt_version": trace.prompt_version,
                "prompt_sha256": trace.prompt_sha256,
                "input_schema_version": trace.input_schema_version,
                "output_schema_version": trace.output_schema_version,
                "provider": self.provider,
                "model": self.model,
                "taxonomy_version": trace.taxonomy_version,
                "input_payload": trace.input_payload,
                "input_sha256": trace.input_sha256,
                "raw_output_text": None,
                "raw_output_sha256": None,
                "validated_output": safe_candidate,
                "validated_output_sha256": (
                    sha256_canonical_json(safe_candidate)
                    if safe_candidate is not None
                    else None
                ),
                "started_at": trace.started_at,
                "completed_at": completed_at,
                "latency_ms": latency_ms,
                "token_usage": safe_token_usage,
                "cache": {"cache_key": trace.cache_key, "hit": trace.cache_hit},
                "retry_count": retry_count,
                "validation_status": validation_status,
                "provider_status": provider_status,
                "fallback_used": fallback_used,
                "fallback_reason": fallback_reason,
                "error_code": error_code,
                "error_message": None,
            }
            if execution_policy is not None:
                record["execution_policy"] = dict(execution_policy)
            if self.profile_id is not None:
                record["profile_id"] = self.profile_id
            self.recorder.append(record)
        except Exception as exc:
            self._mark_degraded("SEMANTIC_RECORDER_APPEND_FAILED", exc, incomplete=True)
            return False

        cache_eligible = (
            validation_status == "accepted"
            and provider_status == "success"
            and accepted_candidate is not None
            and not fallback_used
            and not trace.cache_hit
            and not self.incomplete
        )
        if cache_eligible:
            try:
                entry = cache_entry_from_record(
                    record,
                    created_at=completed_at,
                    source_run_id=self.run_id,
                )
                self.cache.put(trace.cache_key, entry, ttl_seconds=self.cache_ttl_seconds)
            except Exception as exc:
                self._mark_degraded("SEMANTIC_CACHE_WRITE_FAILED", exc)
        return True

    def finalize_manifest(self, *, complete: bool) -> Path | None:
        with self._lock:
            if self._finalized:
                return self._manifest_path
            self._finalized = True
            has_outstanding_calls = bool(self._outstanding_call_ids)
        if has_outstanding_calls:
            self._mark_degraded(
                "SEMANTIC_RUNTIME_UNRESOLVED_CALLS",
                incomplete=True,
            )
        recorder_closed = False
        try:
            integrity = self.recorder.verify_integrity()
            if not integrity.valid:
                self._mark_degraded(
                    "SEMANTIC_RECORDER_INTEGRITY_FAILED",
                    incomplete=True,
                )
            try:
                self.recorder.close()
                recorder_closed = True
            except Exception as exc:
                self._mark_degraded(
                    "SEMANTIC_RECORDER_CLOSE_FAILED",
                    exc,
                    incomplete=True,
                )
            effective_complete = bool(complete and not self.incomplete)
            finalized_at = self._timestamp() if effective_complete else None
            manifest = build_semantic_manifest(
                run_id=self.run_id,
                calls_path=self.recorder.calls_path,
                complete=effective_complete,
                created_at=self.created_at,
                finalized_at=finalized_at,
            )
            self._manifest_path = write_semantic_manifest_atomic(
                manifest=manifest,
                output_directory=self.output_directory,
                allow_run_artifacts=True,
            )
            return self._manifest_path
        except Exception as exc:
            self._mark_degraded("SEMANTIC_MANIFEST_FINALIZATION_FAILED", exc, incomplete=True)
            return None
        finally:
            if not recorder_closed:
                try:
                    self.recorder.close()
                except Exception as exc:
                    self._mark_degraded("SEMANTIC_RECORDER_CLOSE_FAILED", exc, incomplete=True)
