"""Versioned semantic-call and validated-cache-entry contracts.

This module is an offline schema/validation foundation. It does not create an
LLM, Redis, database, network, or production-pipeline dependency.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from comqutor_alpha.llm_runtime.canonical_json import sha256_canonical_json, sha256_text
from comqutor_alpha.llm_runtime.errors import (
    CanonicalJSONError,
    ContractValidationError,
    ValidationIssue,
    ValidationResult,
    validation_failure,
    validation_success,
)

SEMANTIC_CALL_SCHEMA_VERSION = "comqutor.semantic_call.v1"
LLM_CACHE_ENTRY_SCHEMA_VERSION = "comqutor.llm_cache_entry.v1"
# Phase 1 Master task-level execution policy (section 3): an OPTIONAL,
# additive sub-object on SemanticCallRecord. Never required -- every record
# persisted before this addition, and every record from a task that never
# supplies it, has no "execution_policy" key at all and validates exactly
# as before. Only structured_claim_shadow currently ever sets it.
EXECUTION_POLICY_SCHEMA_VERSION = "comqutor.semantic_call_execution_policy.v1"

SEMANTIC_TASKS = frozenset(
    {
        "structured_adapter",
        "alpha_classifier",
        "structure_extractor",
        # B1 Evidence Stance LLM upgrade (evidence_stance_llm.py,
        # LLM_TASK_NAME). A first-class live-pipeline semantic task, exactly
        # like the three above -- always used its own registered task name
        # in prompt/schema identity (week2_llm.py's _TASK_INSTRUCTIONS/
        # _TASK_RUNTIME_METADATA["evidence_stance_classifier"] predate this
        # entry), but was never added to this contract-level vocabulary.
        # Post-Alpha-Authority-Migration cleanup: registering it here (and
        # in replay/source_bundle.py's own copy of this set) is a pure
        # registry completion, not a semantic change -- it changes no
        # prompt, no schema, no B1 stance behavior.
        "evidence_stance_classifier",
        # Phase 1B.1: offline Shadow evaluation task only (see
        # structured_output_shadow_provider.py). Never used by the live
        # Adapter/Mapper/Extractor and never affects their existing
        # cache/manifest/task identity.
        "structured_claim_shadow",
    }
)
EXECUTION_MODES = frozenset({"live", "shadow", "replay_fixture", "test"})
VALIDATION_STATUSES = frozenset({"accepted", "rejected", "not_run"})
PROVIDER_STATUSES = frozenset(
    {"success", "timeout", "provider_error", "budget_exhausted", "not_called"}
)
PROVIDER_CALLED_STATUSES = frozenset({"success", "timeout", "provider_error"})

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ERROR_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_CACHE_KEY_PATTERN = re.compile(r"^comqutor:llm:v1:[0-9a-f]{64}$")
_HOME_PATH_PATTERN = re.compile(
    r"(?:(?:/Users|/home)/[^/\s]+/[^\s,;]*|[A-Za-z]:\\Users\\[^\\\s]+\\[^\s,;]*)"
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|authorization|password|secret|access[_-]?token|refresh[_-]?token)"
    r"\s*[\"']?\s*[:=]\s*[\"']?[^\s,;\"'}]+"
)
_SECRET_VALUE_PATTERN = re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{6,}\b")
_SENSITIVE_KEYS = frozenset(
    {
        "apikey",
        "authorization",
        "password",
        "secret",
        "accesstoken",
        "refreshtoken",
        "privatekey",
    }
)

_SEMANTIC_RECORD_FIELDS = frozenset(
    {
        "schema_version",
        "call_id",
        "run_id",
        "call_sequence",
        "task",
        "execution_mode",
        "prompt_version",
        "prompt_sha256",
        "input_schema_version",
        "output_schema_version",
        "provider",
        "model",
        "taxonomy_version",
        "input_payload",
        "input_sha256",
        "raw_output_text",
        "raw_output_sha256",
        "validated_output",
        "validated_output_sha256",
        "started_at",
        "completed_at",
        "latency_ms",
        "token_usage",
        "cache",
        "retry_count",
        "validation_status",
        "provider_status",
        "fallback_used",
        "fallback_reason",
        "error_code",
        "error_message",
    }
)

# Optional -- never counted as "missing" when absent, so every record
# persisted before this field existed still validates unchanged.
_OPTIONAL_SEMANTIC_RECORD_FIELDS = frozenset({"execution_policy", "profile_id"})
_EXECUTION_POLICY_FIELDS = frozenset(
    {"schema_version", "effective_timeout_seconds", "effective_max_retries", "execution_policy_source"}
)
_OPTIONAL_EXECUTION_POLICY_FIELDS = frozenset(
    {
        "first_attempt_status",
        "retry_reason",
        "retry_delay_seconds",
        "final_status",
        "attempt_history",
    }
)

_CACHE_ENTRY_FIELDS = frozenset(
    {
        "schema_version",
        "cache_key",
        "task",
        "prompt_sha256",
        "input_sha256",
        "provider",
        "model",
        "output_schema_version",
        "validated_output",
        "validated_output_sha256",
        "created_at",
        "expires_at",
        "source_run_id",
    }
)


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    def to_dict(self) -> dict[str, int | None]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True)
class CacheMetadata:
    cache_key: str
    hit: bool

    def to_dict(self) -> dict[str, str | bool]:
        return {"cache_key": self.cache_key, "hit": self.hit}


@dataclass(frozen=True)
class SemanticCallRecord:
    schema_version: str
    call_id: str
    run_id: str
    call_sequence: int
    task: str
    execution_mode: str
    prompt_version: str
    prompt_sha256: str
    input_schema_version: str
    output_schema_version: str
    provider: str
    model: str
    taxonomy_version: str | None
    input_payload: Mapping[str, Any]
    input_sha256: str
    raw_output_text: str | None
    raw_output_sha256: str | None
    validated_output: Any | None
    validated_output_sha256: str | None
    started_at: str
    completed_at: str
    latency_ms: int | float
    token_usage: TokenUsage
    cache: CacheMetadata
    retry_count: int
    validation_status: str
    provider_status: str
    fallback_used: bool
    fallback_reason: str | None
    error_code: str | None
    error_message: str | None
    # Optional, additive (see EXECUTION_POLICY_SCHEMA_VERSION above). Stays
    # None -- and is therefore omitted from to_dict() -- for every task that
    # never supplies it, so existing tasks' persisted shape is unchanged.
    execution_policy: Mapping[str, Any] | None = None
    profile_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        base = {
            "schema_version": self.schema_version,
            "call_id": self.call_id,
            "run_id": self.run_id,
            "call_sequence": self.call_sequence,
            "task": self.task,
            "execution_mode": self.execution_mode,
            "prompt_version": self.prompt_version,
            "prompt_sha256": self.prompt_sha256,
            "input_schema_version": self.input_schema_version,
            "output_schema_version": self.output_schema_version,
            "provider": self.provider,
            "model": self.model,
            "taxonomy_version": self.taxonomy_version,
            "input_payload": dict(self.input_payload),
            "input_sha256": self.input_sha256,
            "raw_output_text": self.raw_output_text,
            "raw_output_sha256": self.raw_output_sha256,
            "validated_output": self.validated_output,
            "validated_output_sha256": self.validated_output_sha256,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "latency_ms": self.latency_ms,
            "token_usage": self.token_usage.to_dict(),
            "cache": self.cache.to_dict(),
            "retry_count": self.retry_count,
            "validation_status": self.validation_status,
            "provider_status": self.provider_status,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }
        if self.execution_policy is not None:
            base["execution_policy"] = dict(self.execution_policy)
        if self.profile_id is not None:
            base["profile_id"] = self.profile_id
        return base


@dataclass(frozen=True)
class LLMCacheEntry:
    schema_version: str
    cache_key: str
    task: str
    prompt_sha256: str
    input_sha256: str
    provider: str
    model: str
    output_schema_version: str
    validated_output: Any
    validated_output_sha256: str
    created_at: str
    expires_at: str | None = None
    source_run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = {
            "schema_version": self.schema_version,
            "cache_key": self.cache_key,
            "task": self.task,
            "prompt_sha256": self.prompt_sha256,
            "input_sha256": self.input_sha256,
            "provider": self.provider,
            "model": self.model,
            "output_schema_version": self.output_schema_version,
            "validated_output": self.validated_output,
            "validated_output_sha256": self.validated_output_sha256,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }
        if self.source_run_id is not None:
            value["source_run_id"] = self.source_run_id
        return value


def redact_sensitive_text(value: str) -> str:
    """Redact credential-like material and full local home paths."""

    if not isinstance(value, str):
        raise TypeError("redact_sensitive_text requires str")
    redacted = _BEARER_PATTERN.sub("Bearer [REDACTED]", value)
    redacted = _SECRET_ASSIGNMENT_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", redacted)
    redacted = _SECRET_VALUE_PATTERN.sub("[REDACTED_SECRET]", redacted)
    return _HOME_PATH_PATTERN.sub("[REDACTED_HOME_PATH]", redacted)


def _record_mapping(record: Mapping[str, Any] | SemanticCallRecord) -> dict[str, Any]:
    return record.to_dict() if isinstance(record, SemanticCallRecord) else dict(record)


def _cache_entry_mapping(entry: Mapping[str, Any] | LLMCacheEntry) -> dict[str, Any]:
    return entry.to_dict() if isinstance(entry, LLMCacheEntry) else dict(entry)


def _issue(issues: list[ValidationIssue], code: str, message: str, path: str) -> None:
    issues.append(ValidationIssue(code, message, path))


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _nonnegative_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _secret_issues(value: Any, *, path: str = "$") -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z]", "", str(key).lower())
            if normalized in _SENSITIVE_KEYS:
                _issue(
                    issues,
                    "SEMANTIC_SECRET_FIELD_FORBIDDEN",
                    "Sensitive credential field is forbidden",
                    f"{path}.{key}",
                )
            issues.extend(_secret_issues(item, path=f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            issues.extend(_secret_issues(item, path=f"{path}[{index}]"))
    elif isinstance(value, str) and redact_sensitive_text(value) != value:
        _issue(
            issues,
            "SEMANTIC_SECRET_OR_HOME_PATH_UNREDACTED",
            "Credential-like text or a full local home path must be redacted",
            path,
        )
    return issues


def validate_semantic_call_record(
    record: Mapping[str, Any] | SemanticCallRecord,
) -> ValidationResult:
    """Validate one record and return all stable failure reason codes."""

    if not isinstance(record, (Mapping, SemanticCallRecord)):
        return validation_failure(
            ValidationIssue("SEMANTIC_RECORD_NOT_OBJECT", "Record must be an object", "$")
        )
    value = _record_mapping(record)
    issues: list[ValidationIssue] = []

    missing = sorted(_SEMANTIC_RECORD_FIELDS - value.keys())
    unknown = sorted(value.keys() - _SEMANTIC_RECORD_FIELDS - _OPTIONAL_SEMANTIC_RECORD_FIELDS)
    for key in missing:
        _issue(issues, "SEMANTIC_REQUIRED_FIELD_MISSING", "Required field is missing", f"$.{key}")
    for key in unknown:
        _issue(issues, "SEMANTIC_UNKNOWN_FIELD", "Unknown field is not allowed", f"$.{key}")
    if missing:
        return validation_failure(*issues)

    if value["schema_version"] != SEMANTIC_CALL_SCHEMA_VERSION:
        _issue(issues, "SEMANTIC_SCHEMA_VERSION_INVALID", "Unsupported schema version", "$.schema_version")
    for key in (
        "call_id",
        "run_id",
        "prompt_version",
        "input_schema_version",
        "output_schema_version",
        "provider",
        "model",
    ):
        if not _nonempty_string(value[key]):
            _issue(issues, "SEMANTIC_STRING_REQUIRED", "Non-empty string required", f"$.{key}")
    if "profile_id" in value and value["profile_id"] is not None and not _nonempty_string(value["profile_id"]):
        _issue(issues, "SEMANTIC_PROFILE_ID_INVALID", "profile_id must be a non-empty string", "$.profile_id")
    if not _nonnegative_int(value["call_sequence"]):
        _issue(
            issues,
            "SEMANTIC_CALL_SEQUENCE_INVALID",
            "call_sequence must be a non-negative integer",
            "$.call_sequence",
        )
    if value["task"] not in SEMANTIC_TASKS:
        _issue(issues, "SEMANTIC_TASK_INVALID", "Task is outside the fixed vocabulary", "$.task")
    if value["execution_mode"] not in EXECUTION_MODES:
        _issue(issues, "SEMANTIC_EXECUTION_MODE_INVALID", "Execution mode is invalid", "$.execution_mode")
    if value["taxonomy_version"] is not None and not _nonempty_string(value["taxonomy_version"]):
        _issue(
            issues,
            "SEMANTIC_TAXONOMY_VERSION_INVALID",
            "taxonomy_version must be null or a non-empty string",
            "$.taxonomy_version",
        )

    for key in ("prompt_sha256", "input_sha256"):
        if not isinstance(value[key], str) or not _SHA256_PATTERN.fullmatch(value[key]):
            _issue(issues, "SEMANTIC_SHA256_FORMAT_INVALID", "Lowercase SHA-256 required", f"$.{key}")

    if not isinstance(value["input_payload"], Mapping):
        _issue(issues, "SEMANTIC_INPUT_NOT_OBJECT", "input_payload must be an object", "$.input_payload")
    else:
        try:
            actual_input_hash = sha256_canonical_json(dict(value["input_payload"]))
        except (CanonicalJSONError, TypeError, ValueError) as exc:
            _issue(issues, "SEMANTIC_INPUT_NOT_CANONICAL_JSON", str(exc), "$.input_payload")
        else:
            if actual_input_hash != value["input_sha256"]:
                _issue(issues, "SEMANTIC_INPUT_HASH_MISMATCH", "input_sha256 does not match", "$.input_sha256")

    raw_text = value["raw_output_text"]
    raw_hash = value["raw_output_sha256"]
    if raw_text is None:
        if raw_hash is not None:
            _issue(issues, "SEMANTIC_RAW_HASH_WITHOUT_OUTPUT", "Raw hash requires raw text", "$.raw_output_sha256")
    elif not isinstance(raw_text, str):
        _issue(issues, "SEMANTIC_RAW_OUTPUT_TYPE_INVALID", "Raw output must be text or null", "$.raw_output_text")
    elif raw_hash != sha256_text(raw_text):
        _issue(issues, "SEMANTIC_RAW_OUTPUT_HASH_MISMATCH", "Raw output hash does not match", "$.raw_output_sha256")

    validated_output = value["validated_output"]
    validated_hash = value["validated_output_sha256"]
    if validated_output is None:
        if validated_hash is not None:
            _issue(
                issues,
                "SEMANTIC_VALIDATED_HASH_WITHOUT_OUTPUT",
                "Validated hash requires validated output",
                "$.validated_output_sha256",
            )
    else:
        try:
            actual_validated_hash = sha256_canonical_json(validated_output)
        except (CanonicalJSONError, TypeError, ValueError) as exc:
            _issue(issues, "SEMANTIC_VALIDATED_OUTPUT_NOT_CANONICAL_JSON", str(exc), "$.validated_output")
        else:
            if actual_validated_hash != validated_hash:
                _issue(
                    issues,
                    "SEMANTIC_VALIDATED_OUTPUT_HASH_MISMATCH",
                    "Validated output hash does not match",
                    "$.validated_output_sha256",
                )

    started = _timestamp(value["started_at"])
    completed = _timestamp(value["completed_at"])
    if started is None:
        _issue(issues, "SEMANTIC_STARTED_AT_INVALID", "Timezone-aware ISO timestamp required", "$.started_at")
    if completed is None:
        _issue(issues, "SEMANTIC_COMPLETED_AT_INVALID", "Timezone-aware ISO timestamp required", "$.completed_at")
    if started is not None and completed is not None and completed < started:
        _issue(
            issues,
            "SEMANTIC_TIMESTAMP_ORDER_INVALID",
            "completed_at cannot precede started_at",
            "$.completed_at",
        )
    if not _nonnegative_number(value["latency_ms"]):
        _issue(issues, "SEMANTIC_LATENCY_INVALID", "latency_ms must be non-negative", "$.latency_ms")
    if not _nonnegative_int(value["retry_count"]):
        _issue(issues, "SEMANTIC_RETRY_COUNT_INVALID", "retry_count must be non-negative", "$.retry_count")

    token_usage = value["token_usage"]
    token_values: dict[str, Any] = {}
    if not isinstance(token_usage, Mapping):
        _issue(issues, "SEMANTIC_TOKEN_USAGE_INVALID", "token_usage must be an object", "$.token_usage")
    else:
        token_values = dict(token_usage)
        expected_token_keys = {"input_tokens", "output_tokens", "total_tokens"}
        if set(token_values) != expected_token_keys:
            _issue(
                issues,
                "SEMANTIC_TOKEN_USAGE_FIELDS_INVALID",
                "token_usage fields must match the v1 schema",
                "$.token_usage",
            )
        for key in expected_token_keys:
            token = token_values.get(key)
            if token is not None and not _nonnegative_int(token):
                _issue(issues, "SEMANTIC_TOKEN_COUNT_INVALID", "Token counts must be non-negative integers", f"$.token_usage.{key}")
        input_tokens = token_values.get("input_tokens")
        output_tokens = token_values.get("output_tokens")
        total_tokens = token_values.get("total_tokens")
        if all(
            _nonnegative_int(item) for item in (input_tokens, output_tokens, total_tokens)
        ) and total_tokens != input_tokens + output_tokens:
            _issue(
                issues,
                "SEMANTIC_TOKEN_TOTAL_MISMATCH",
                "total_tokens must equal input_tokens + output_tokens",
                "$.token_usage.total_tokens",
            )

    cache = value["cache"]
    cache_values: dict[str, Any] = {}
    if not isinstance(cache, Mapping):
        _issue(issues, "SEMANTIC_CACHE_METADATA_INVALID", "cache must be an object", "$.cache")
    else:
        cache_values = dict(cache)
        if set(cache_values) != {"cache_key", "hit"}:
            _issue(issues, "SEMANTIC_CACHE_FIELDS_INVALID", "cache fields must match v1", "$.cache")
        if not isinstance(cache_values.get("cache_key"), str) or not _CACHE_KEY_PATTERN.fullmatch(
            cache_values.get("cache_key", "")
        ):
            _issue(issues, "SEMANTIC_CACHE_KEY_INVALID", "Versioned cache key required", "$.cache.cache_key")
        if not isinstance(cache_values.get("hit"), bool):
            _issue(issues, "SEMANTIC_CACHE_HIT_INVALID", "cache.hit must be boolean", "$.cache.hit")

    validation_status = value["validation_status"]
    provider_status = value["provider_status"]
    fallback_used = value["fallback_used"]
    if validation_status not in VALIDATION_STATUSES:
        _issue(issues, "SEMANTIC_VALIDATION_STATUS_INVALID", "Validation status is invalid", "$.validation_status")
    if provider_status not in PROVIDER_STATUSES:
        _issue(issues, "SEMANTIC_PROVIDER_STATUS_INVALID", "Provider status is invalid", "$.provider_status")
    if not isinstance(fallback_used, bool):
        _issue(issues, "SEMANTIC_FALLBACK_FLAG_INVALID", "fallback_used must be boolean", "$.fallback_used")
    if fallback_used is True and not _nonempty_string(value["fallback_reason"]):
        _issue(
            issues,
            "SEMANTIC_FALLBACK_REASON_REQUIRED",
            "fallback_used=true requires fallback_reason",
            "$.fallback_reason",
        )
    if fallback_used is False and value["fallback_reason"] is not None:
        _issue(
            issues,
            "SEMANTIC_FALLBACK_REASON_UNEXPECTED",
            "fallback_reason must be null when fallback is not used",
            "$.fallback_reason",
        )

    if validation_status == "accepted" and validated_output is None:
        _issue(
            issues,
            "SEMANTIC_ACCEPTED_OUTPUT_MISSING",
            "Accepted records require validated_output",
            "$.validated_output",
        )
    if validation_status in {"rejected", "not_run"} and validated_output is not None:
        _issue(
            issues,
            "SEMANTIC_UNACCEPTED_OUTPUT_PRESENT",
            "Rejected/not-run records cannot carry validated_output",
            "$.validated_output",
        )
    if provider_status == "success" and validation_status == "accepted" and validated_output is None:
        _issue(
            issues,
            "SEMANTIC_SUCCESS_ACCEPTED_OUTPUT_MISSING",
            "success + accepted requires validated_output",
            "$.validated_output",
        )
    if provider_status in {"timeout", "provider_error", "budget_exhausted"}:
        if validation_status == "accepted" and fallback_used is not True:
            _issue(
                issues,
                "SEMANTIC_PROVIDER_FAILURE_ACCEPTED_WITHOUT_FALLBACK",
                "Provider failure can be accepted only as an explicit fallback",
                "$.validation_status",
            )
        if not _nonempty_string(value["error_code"]):
            _issue(issues, "SEMANTIC_ERROR_CODE_REQUIRED", "Provider failure requires error_code", "$.error_code")
    if provider_status == "success" and (value["error_code"] is not None or value["error_message"] is not None):
        _issue(
            issues,
            "SEMANTIC_SUCCESS_ERROR_UNEXPECTED",
            "Successful provider call cannot carry an error",
            "$.error_code",
        )
    if provider_status == "not_called":
        if any(token_values.get(key) is not None for key in ("input_tokens", "output_tokens", "total_tokens")):
            _issue(
                issues,
                "SEMANTIC_NOT_CALLED_TOKEN_USAGE_FORBIDDEN",
                "not_called cannot report token usage",
                "$.token_usage",
            )
        if raw_text is not None:
            _issue(
                issues,
                "SEMANTIC_NOT_CALLED_RAW_OUTPUT_FORBIDDEN",
                "not_called cannot report raw Provider output",
                "$.raw_output_text",
            )

    cache_hit = cache_values.get("hit")
    if cache_hit is True:
        if provider_status != "not_called" or validation_status != "accepted":
            _issue(
                issues,
                "SEMANTIC_CACHE_HIT_STATUS_INVALID",
                "Cache hit requires not_called + accepted",
                "$.cache.hit",
            )
        if value["retry_count"] != 0 or fallback_used is not False:
            _issue(
                issues,
                "SEMANTIC_CACHE_HIT_EXECUTION_INVALID",
                "Cache hit cannot retry or use fallback",
                "$.cache.hit",
            )

    error_code = value["error_code"]
    if error_code is not None:
        if not isinstance(error_code, str) or not _ERROR_CODE_PATTERN.fullmatch(error_code):
            _issue(issues, "SEMANTIC_ERROR_CODE_INVALID", "Stable uppercase reason code required", "$.error_code")
        elif redact_sensitive_text(error_code) != error_code:
            _issue(issues, "SEMANTIC_ERROR_CODE_SECRET_FORBIDDEN", "error_code cannot contain a secret", "$.error_code")
    error_message = value["error_message"]
    if error_message is not None:
        if not isinstance(error_message, str):
            _issue(issues, "SEMANTIC_ERROR_MESSAGE_INVALID", "error_message must be text or null", "$.error_message")
        elif redact_sensitive_text(error_message) != error_message:
            _issue(
                issues,
                "SEMANTIC_ERROR_MESSAGE_NOT_REDACTED",
                "error_message contains unredacted sensitive material",
                "$.error_message",
            )

    if "execution_policy" in value:
        policy = value["execution_policy"]
        if policy is not None:
            if not isinstance(policy, Mapping):
                _issue(issues, "SEMANTIC_EXECUTION_POLICY_NOT_OBJECT", "execution_policy must be an object or null", "$.execution_policy")
            else:
                policy_missing = sorted(_EXECUTION_POLICY_FIELDS - policy.keys())
                policy_unknown = sorted(
                    policy.keys() - _EXECUTION_POLICY_FIELDS - _OPTIONAL_EXECUTION_POLICY_FIELDS
                )
                for key in policy_missing:
                    _issue(issues, "SEMANTIC_EXECUTION_POLICY_FIELD_MISSING", "Required field is missing", f"$.execution_policy.{key}")
                for key in policy_unknown:
                    _issue(issues, "SEMANTIC_EXECUTION_POLICY_UNKNOWN_FIELD", "Unknown field is not allowed", f"$.execution_policy.{key}")
                if not policy_missing:
                    if policy["schema_version"] != EXECUTION_POLICY_SCHEMA_VERSION:
                        _issue(
                            issues,
                            "SEMANTIC_EXECUTION_POLICY_SCHEMA_VERSION_INVALID",
                            "Unsupported execution_policy schema version",
                            "$.execution_policy.schema_version",
                        )
                    if not _nonempty_string(policy["execution_policy_source"]):
                        _issue(
                            issues,
                            "SEMANTIC_EXECUTION_POLICY_SOURCE_REQUIRED",
                            "execution_policy_source must be a non-empty string",
                            "$.execution_policy.execution_policy_source",
                        )
                    if not _nonnegative_number(policy["effective_timeout_seconds"]):
                        _issue(
                            issues,
                            "SEMANTIC_EXECUTION_POLICY_TIMEOUT_INVALID",
                            "effective_timeout_seconds must be non-negative",
                            "$.execution_policy.effective_timeout_seconds",
                        )
                    if not _nonnegative_int(policy["effective_max_retries"]):
                        _issue(
                            issues,
                            "SEMANTIC_EXECUTION_POLICY_RETRIES_INVALID",
                            "effective_max_retries must be a non-negative integer",
                            "$.execution_policy.effective_max_retries",
                        )
                if (
                    "retry_delay_seconds" in policy
                    and policy["retry_delay_seconds"] is not None
                    and not _nonnegative_number(policy["retry_delay_seconds"])
                ):
                    _issue(
                        issues,
                        "SEMANTIC_EXECUTION_POLICY_RETRY_DELAY_INVALID",
                        "retry_delay_seconds must be null or non-negative",
                        "$.execution_policy.retry_delay_seconds",
                    )
                for key in ("first_attempt_status", "retry_reason", "final_status"):
                    if key in policy and policy[key] is not None and not _nonempty_string(policy[key]):
                        _issue(
                            issues,
                            "SEMANTIC_EXECUTION_POLICY_STATUS_INVALID",
                            f"{key} must be null or a non-empty string",
                            f"$.execution_policy.{key}",
                        )
                if "attempt_history" in policy and not isinstance(policy["attempt_history"], list):
                    _issue(
                        issues,
                        "SEMANTIC_EXECUTION_POLICY_ATTEMPT_HISTORY_INVALID",
                        "attempt_history must be a list",
                        "$.execution_policy.attempt_history",
                    )

    issues.extend(_secret_issues(value))
    return validation_success() if not issues else validation_failure(*issues)


def validate_semantic_call_records(
    records: Sequence[Mapping[str, Any] | SemanticCallRecord],
) -> ValidationResult:
    """Validate an ordered collection, including identity and sequence invariants."""

    if not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray)):
        return validation_failure(
            ValidationIssue("SEMANTIC_RECORDS_NOT_SEQUENCE", "Records must be a sequence", "$")
        )
    issues: list[ValidationIssue] = []
    seen_ids: set[str] = set()
    last_sequence_by_run: dict[str, int] = {}
    for index, record in enumerate(records):
        result = validate_semantic_call_record(record)
        issues.extend(
            ValidationIssue(issue.reason_code, issue.message, f"$[{index}]{issue.path[1:] if issue.path else ''}")
            for issue in result.issues
        )
        if not isinstance(record, (Mapping, SemanticCallRecord)):
            continue
        value = _record_mapping(record)
        call_id = value.get("call_id")
        if isinstance(call_id, str):
            if call_id in seen_ids:
                _issue(
                    issues,
                    "SEMANTIC_DUPLICATE_CALL_ID",
                    "call_id must be unique within the artifact",
                    f"$[{index}].call_id",
                )
            seen_ids.add(call_id)
        run_id = value.get("run_id")
        sequence = value.get("call_sequence")
        if isinstance(run_id, str) and _nonnegative_int(sequence):
            previous = last_sequence_by_run.get(run_id)
            if previous is not None and sequence <= previous:
                _issue(
                    issues,
                    "SEMANTIC_CALL_SEQUENCE_NOT_MONOTONIC",
                    "call_sequence must increase strictly for each run",
                    f"$[{index}].call_sequence",
                )
            last_sequence_by_run[run_id] = sequence
    return validation_success() if not issues else validation_failure(*issues)


def validate_cache_entry(
    entry: Mapping[str, Any] | LLMCacheEntry,
    *,
    expected_cache_key: str | None = None,
) -> ValidationResult:
    """Validate one accepted-output cache entry and its content hash."""

    if not isinstance(entry, (Mapping, LLMCacheEntry)):
        return validation_failure(
            ValidationIssue("CACHE_ENTRY_NOT_OBJECT", "Cache entry must be an object", "$")
        )
    value = _cache_entry_mapping(entry)
    issues: list[ValidationIssue] = []
    required = _CACHE_ENTRY_FIELDS - {"source_run_id"}
    for key in sorted(required - value.keys()):
        _issue(issues, "CACHE_ENTRY_REQUIRED_FIELD_MISSING", "Required field is missing", f"$.{key}")
    for key in sorted(value.keys() - _CACHE_ENTRY_FIELDS):
        _issue(issues, "CACHE_ENTRY_UNKNOWN_FIELD", "Unknown field is not allowed", f"$.{key}")
    if required - value.keys():
        return validation_failure(*issues)

    if value["schema_version"] != LLM_CACHE_ENTRY_SCHEMA_VERSION:
        _issue(issues, "CACHE_ENTRY_SCHEMA_VERSION_INVALID", "Unsupported cache schema", "$.schema_version")
    if value["task"] not in SEMANTIC_TASKS:
        _issue(issues, "CACHE_ENTRY_TASK_INVALID", "Task is outside the fixed vocabulary", "$.task")
    cache_key = value["cache_key"]
    if not isinstance(cache_key, str) or not _CACHE_KEY_PATTERN.fullmatch(cache_key):
        _issue(issues, "CACHE_ENTRY_KEY_INVALID", "Versioned cache key required", "$.cache_key")
    if expected_cache_key is not None and cache_key != expected_cache_key:
        _issue(issues, "CACHE_ENTRY_KEY_MISMATCH", "Stored cache key differs from lookup key", "$.cache_key")
    for key in ("prompt_sha256", "input_sha256", "validated_output_sha256"):
        if not isinstance(value[key], str) or not _SHA256_PATTERN.fullmatch(value[key]):
            _issue(issues, "CACHE_ENTRY_SHA256_FORMAT_INVALID", "Lowercase SHA-256 required", f"$.{key}")
    for key in ("provider", "model", "output_schema_version"):
        if not _nonempty_string(value[key]):
            _issue(issues, "CACHE_ENTRY_STRING_REQUIRED", "Non-empty string required", f"$.{key}")
    if value["validated_output"] is None:
        _issue(
            issues,
            "CACHE_ENTRY_VALIDATED_OUTPUT_REQUIRED",
            "Only accepted validated output can be cached",
            "$.validated_output",
        )
    else:
        try:
            actual_hash = sha256_canonical_json(value["validated_output"])
        except (CanonicalJSONError, TypeError, ValueError) as exc:
            _issue(issues, "CACHE_ENTRY_OUTPUT_NOT_CANONICAL_JSON", str(exc), "$.validated_output")
        else:
            if actual_hash != value["validated_output_sha256"]:
                _issue(
                    issues,
                    "CACHE_ENTRY_OUTPUT_HASH_MISMATCH",
                    "validated_output_sha256 does not match",
                    "$.validated_output_sha256",
                )
    created = _timestamp(value["created_at"])
    expires = _timestamp(value["expires_at"]) if value["expires_at"] is not None else None
    if created is None:
        _issue(issues, "CACHE_ENTRY_CREATED_AT_INVALID", "Timezone-aware timestamp required", "$.created_at")
    if value["expires_at"] is not None and expires is None:
        _issue(issues, "CACHE_ENTRY_EXPIRES_AT_INVALID", "Timezone-aware timestamp required", "$.expires_at")
    if created is not None and expires is not None and expires <= created:
        _issue(issues, "CACHE_ENTRY_EXPIRY_ORDER_INVALID", "expires_at must follow created_at", "$.expires_at")
    if "run_id" in value:
        _issue(issues, "CACHE_ENTRY_RUN_ID_FORBIDDEN", "run_id cannot be part of the cache entry key contract", "$.run_id")
    if value.get("source_run_id") is not None and not _nonempty_string(value.get("source_run_id")):
        _issue(issues, "CACHE_ENTRY_SOURCE_RUN_ID_INVALID", "source_run_id must be non-empty", "$.source_run_id")
    issues.extend(_secret_issues(value))
    return validation_success() if not issues else validation_failure(*issues)


def cache_entry_from_record(
    record: Mapping[str, Any] | SemanticCallRecord,
    *,
    created_at: str,
    expires_at: str | None = None,
    source_run_id: str | None = None,
) -> LLMCacheEntry:
    """Create a cache entry only from a successful, accepted, non-fallback call."""

    result = validate_semantic_call_record(record)
    if not result.valid:
        raise ContractValidationError(result)
    value = _record_mapping(record)
    eligible = (
        value["validation_status"] == "accepted"
        and value["provider_status"] == "success"
        and value["fallback_used"] is False
        and value["cache"]["hit"] is False
        and value["validated_output"] is not None
    )
    if not eligible:
        raise ContractValidationError(
            validation_failure(
                ValidationIssue(
                    "CACHE_ENTRY_SOURCE_NOT_ELIGIBLE",
                    "Rejected, provider-error, fallback, or cache-hit records cannot create cache entries",
                    "$",
                )
            )
        )
    entry = LLMCacheEntry(
        schema_version=LLM_CACHE_ENTRY_SCHEMA_VERSION,
        cache_key=value["cache"]["cache_key"],
        task=value["task"],
        prompt_sha256=value["prompt_sha256"],
        input_sha256=value["input_sha256"],
        provider=value["provider"],
        model=value["model"],
        output_schema_version=value["output_schema_version"],
        validated_output=value["validated_output"],
        validated_output_sha256=value["validated_output_sha256"],
        created_at=created_at,
        expires_at=expires_at,
        source_run_id=source_run_id,
    )
    entry_result = validate_cache_entry(entry)
    if not entry_result.valid:
        raise ContractValidationError(entry_result)
    return entry
