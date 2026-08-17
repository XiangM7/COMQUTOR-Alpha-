"""Fail-closed, read-only loading for Exact Semantic Replay sources."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

EXACT_REPLAY_SEMANTIC_ARTIFACT_MISSING = "EXACT_REPLAY_SEMANTIC_ARTIFACT_MISSING"
EXACT_REPLAY_SEMANTIC_MANIFEST_INVALID = "EXACT_REPLAY_SEMANTIC_MANIFEST_INVALID"
EXACT_REPLAY_SEMANTIC_NOT_READY = "EXACT_REPLAY_SEMANTIC_NOT_READY"
EXACT_REPLAY_SEMANTIC_CALL_CORRUPTED = "EXACT_REPLAY_SEMANTIC_CALL_CORRUPTED"
EXACT_REPLAY_SEMANTIC_INPUT_MISMATCH = "EXACT_REPLAY_SEMANTIC_INPUT_MISMATCH"
EXACT_REPLAY_SEMANTIC_OUTPUT_MISMATCH = "EXACT_REPLAY_SEMANTIC_OUTPUT_MISMATCH"
EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH = "EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH"
EXACT_REPLAY_SEMANTIC_CALL_AMBIGUOUS = "EXACT_REPLAY_SEMANTIC_CALL_AMBIGUOUS"
EXACT_REPLAY_SEMANTIC_BINDING_MISSING = "EXACT_REPLAY_SEMANTIC_BINDING_MISSING"
EXACT_REPLAY_SEMANTIC_BINDING_ORPHAN = "EXACT_REPLAY_SEMANTIC_BINDING_ORPHAN"
EXACT_REPLAY_SEMANTIC_RUN_ID_MISMATCH = "EXACT_REPLAY_SEMANTIC_RUN_ID_MISMATCH"
EXACT_REPLAY_TICKER_IDENTITY_MISMATCH = "EXACT_REPLAY_TICKER_IDENTITY_MISMATCH"
EXACT_REPLAY_SOURCE_ARTIFACT_INVALID = "EXACT_REPLAY_SOURCE_ARTIFACT_INVALID"
EXACT_REPLAY_SOURCE_ARTIFACT_HASH_MISMATCH = (
    "EXACT_REPLAY_SOURCE_ARTIFACT_HASH_MISMATCH"
)
EXACT_REPLAY_STAGING_WRITE_FAILED = "EXACT_REPLAY_STAGING_WRITE_FAILED"
EXACT_REPLAY_OUTPUT_VALIDATION_FAILED = "EXACT_REPLAY_OUTPUT_VALIDATION_FAILED"
EXACT_REPLAY_PROVIDER_CALL_ATTEMPTED = "EXACT_REPLAY_PROVIDER_CALL_ATTEMPTED"
EXACT_REPLAY_DATABASE_WRITE_ATTEMPTED = "EXACT_REPLAY_DATABASE_WRITE_ATTEMPTED"
EXACT_REPLAY_MODE_FALLBACK_FORBIDDEN = "EXACT_REPLAY_MODE_FALLBACK_FORBIDDEN"

SEMANTIC_CALLS_FILENAME = "llm_semantic_calls.jsonl"
SEMANTIC_MANIFEST_FILENAME = "llm_semantic_manifest.json"
SEMANTIC_CALL_SCHEMA_VERSION = "comqutor.semantic_call.v1"
SEMANTIC_MANIFEST_SCHEMA_VERSION = "comqutor.semantic_manifest.v1"

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_CACHE_KEY_PATTERN = re.compile(r"^comqutor:llm:v1:[0-9a-f]{64}$")
_ERROR_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_HOME_PATH_PATTERN = re.compile(
    r"(?:(?:/Users|/home)/[^/\s]+/[^\s,;]*|[A-Za-z]:\\Users\\[^\\\s]+\\[^\s,;]*)"
)
_SENSITIVE_TEXT_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(
        r"(?i)\b(api[_-]?key|authorization|password|secret|access[_-]?token|refresh[_-]?token)"
        r"\s*[\"']?\s*[:=]\s*[\"']?[^\s,;\"'}]+"
    ),
    re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{6,}\b"),
    _HOME_PATH_PATTERN,
)
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
_SEMANTIC_TASKS = frozenset(
    {"structured_adapter", "alpha_classifier", "structure_extractor"}
)
_PROVIDER_CALLED_STATUSES = frozenset({"success", "timeout", "provider_error"})
_RECORD_FIELDS = frozenset(
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
_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "calls_file",
        "calls_file_sha256",
        "record_count",
        "tasks",
        "accepted_count",
        "rejected_count",
        "fallback_count",
        "cache_hit_count",
        "provider_call_count",
        "prompt_versions",
        "models",
        "complete",
        "exact_replay_ready",
        "created_at",
        "finalized_at",
    }
)

_JSON_ARTIFACTS = (
    "metadata.json",
    SEMANTIC_MANIFEST_FILENAME,
    "raw_agent_outputs.json",
    "structured_agent_outputs.json",
    "alpha_matches.json",
    "extracted_structures.json",
    "structure_graph.json",
    "entity_alpha_exposures.json",
    "conflicts.json",
    "run_audit.json",
    "artifact_manifest.json",
)
REQUIRED_SOURCE_ARTIFACTS = (*_JSON_ARTIFACTS, SEMANTIC_CALLS_FILENAME)
SEMANTIC_ARTIFACT_COPY_FILENAMES = (
    SEMANTIC_CALLS_FILENAME,
    SEMANTIC_MANIFEST_FILENAME,
    "structured_agent_outputs.json",
    "alpha_matches.json",
    "extracted_structures.json",
)

_SUPPORTED_ARTIFACT_SCHEMAS = {
    "structured_agent_outputs.json": "week1a.structured_agent_outputs.v2",
    "alpha_matches.json": "week2.alpha_matches.v2",
    "extracted_structures.json": "week2.extracted_structures.v2",
    "structure_graph.json": "week3.structure_graph.v2",
    "entity_alpha_exposures.json": "entity_alpha_exposure.run.v1",
    "conflicts.json": "conflicts.export.v1",
    "artifact_manifest.json": "artifact_manifest.export.v1",
}
_SUPPORTED_CALL_IDENTITIES = {
    "structured_adapter": {
        "prompt_version": "week2.claim_batch_enrichment.v1",
        "prompt_sha256": "c6822099e2171c6fbad72c36bf2881bcd59bd4d4ad2fc20e10ab62af50b5bfd9",
        "input_schema_version": "week2.claim_batch_enrichment.input.v1",
        "output_schema_version": "week2.claim_batch_enrichment.output.v1",
        "taxonomy_version": None,
    },
    "alpha_classifier": {
        "prompt_version": "week2.alpha_classifier.v1",
        "prompt_sha256": "f21a9a14007e7b1e5d60cba99671c9daa68f0a8dba4e539930782913c88a3e30",
        "input_schema_version": "week2.alpha_classifier.input.v1",
        "output_schema_version": "week2.alpha_classifier.output.v1",
        "taxonomy_version": "alpha_taxonomy_v1",
    },
    "structure_extractor": {
        "prompt_version": "week2.structure_extractor.v1",
        "prompt_sha256": "326622a1786be03909e3d6dbcfca5069fe3cd4b31f0aab2da36bf8be324edbbc",
        "input_schema_version": "week2.structure_extractor.input.v1",
        "output_schema_version": "week2.structure_extractor.output.v1",
        "taxonomy_version": None,
    },
}


class ExactReplayError(RuntimeError):
    """A stable, secret-free Exact Replay failure."""

    def __init__(
        self,
        reason_code: str,
        *,
        artifact: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.reason_code = reason_code
        self.artifact = artifact
        self.details = dict(details or {})
        suffix = f":{artifact}" if artifact else ""
        super().__init__(f"{reason_code}{suffix}")


@dataclass(frozen=True)
class SourceFileSnapshot:
    relative_path: str
    size_bytes: int
    sha256: str
    mtime_ns: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "mtime_ns": self.mtime_ns,
        }


@dataclass(frozen=True)
class ExactSemanticSourceBundle:
    source_directory: Path
    source_run_id: str
    ticker: str
    metadata: dict[str, Any]
    raw_agent_outputs: dict[str, Any]
    semantic_manifest: dict[str, Any]
    semantic_calls: tuple[dict[str, Any], ...]
    structured_agent_outputs: dict[str, Any]
    alpha_matches: dict[str, Any]
    extracted_structures: dict[str, Any]
    structure_graph: dict[str, Any]
    entity_alpha_exposures: dict[str, Any]
    conflicts: dict[str, Any]
    run_audit: dict[str, Any]
    artifact_manifest: dict[str, Any]
    source_files: tuple[SourceFileSnapshot, ...]

    def artifact_path(self, filename: str) -> Path:
        if filename not in REQUIRED_SOURCE_ARTIFACTS:
            raise ExactReplayError(
                EXACT_REPLAY_SOURCE_ARTIFACT_INVALID,
                artifact=filename,
            )
        path = self.source_directory / filename
        _require_safe_file(path, self.source_directory, filename)
        return path


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _validate_json_value(value: Any, ancestors: set[int] | None = None) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite JSON number")
        return
    active = ancestors if ancestors is not None else set()
    if isinstance(value, dict):
        identity = id(value)
        if identity in active or any(not isinstance(key, str) for key in value):
            raise ValueError("invalid canonical JSON object")
        active.add(identity)
        try:
            for item in value.values():
                _validate_json_value(item, active)
        finally:
            active.remove(identity)
        return
    if isinstance(value, list):
        identity = id(value)
        if identity in active:
            raise ValueError("invalid canonical JSON array")
        active.add(identity)
        try:
            for item in value:
                _validate_json_value(item, active)
        finally:
            active.remove(identity)
        return
    raise ValueError("unsupported canonical JSON value")


def sha256_canonical_json(value: Any) -> str:
    """Frozen semantic-artifact hash without importing the live runtime."""

    _validate_json_value(value)
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _aware_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _nonnegative_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _contains_sensitive_value(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z]", "", str(key).lower())
            if normalized in _SENSITIVE_KEYS or _contains_sensitive_value(item):
                return True
    elif isinstance(value, list):
        return any(_contains_sensitive_value(item) for item in value)
    elif isinstance(value, str):
        return any(pattern.search(value) for pattern in _SENSITIVE_TEXT_PATTERNS)
    return False


def _record_contract_errors(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if set(record) != _RECORD_FIELDS:
        errors.append("SEMANTIC_RECORD_FIELDS_INVALID")
        return errors
    if record.get("schema_version") != SEMANTIC_CALL_SCHEMA_VERSION:
        errors.append("SEMANTIC_SCHEMA_VERSION_INVALID")
    for key in (
        "call_id",
        "run_id",
        "prompt_version",
        "input_schema_version",
        "output_schema_version",
        "provider",
        "model",
    ):
        if not isinstance(record.get(key), str) or not record[key].strip():
            errors.append(f"SEMANTIC_STRING_REQUIRED:{key}")
    if not _nonnegative_int(record.get("call_sequence")):
        errors.append("SEMANTIC_CALL_SEQUENCE_INVALID")
    if record.get("task") not in _SEMANTIC_TASKS:
        errors.append("SEMANTIC_TASK_INVALID")
    if record.get("execution_mode") not in {"live", "shadow", "replay_fixture", "test"}:
        errors.append("SEMANTIC_EXECUTION_MODE_INVALID")
    taxonomy = record.get("taxonomy_version")
    if taxonomy is not None and (not isinstance(taxonomy, str) or not taxonomy.strip()):
        errors.append("SEMANTIC_TAXONOMY_VERSION_INVALID")
    for key in ("prompt_sha256", "input_sha256"):
        if not isinstance(record.get(key), str) or not _SHA256_PATTERN.fullmatch(
            record[key]
        ):
            errors.append(f"SEMANTIC_SHA256_FORMAT_INVALID:{key}")
    input_payload = record.get("input_payload")
    if not isinstance(input_payload, dict):
        errors.append("SEMANTIC_INPUT_NOT_OBJECT")
    else:
        try:
            actual = sha256_canonical_json(input_payload)
        except (TypeError, ValueError):
            errors.append("SEMANTIC_INPUT_NOT_CANONICAL_JSON")
        else:
            if actual != record.get("input_sha256"):
                errors.append("SEMANTIC_INPUT_HASH_MISMATCH")
    if record.get("raw_output_text") is not None or record.get("raw_output_sha256") is not None:
        errors.append("SEMANTIC_RAW_OUTPUT_NOT_NULL")
    output = record.get("validated_output")
    output_hash = record.get("validated_output_sha256")
    if output is None:
        if output_hash is not None:
            errors.append("SEMANTIC_VALIDATED_HASH_WITHOUT_OUTPUT")
    else:
        try:
            actual_output = sha256_canonical_json(output)
        except (TypeError, ValueError):
            errors.append("SEMANTIC_OUTPUT_NOT_CANONICAL_JSON")
        else:
            if actual_output != output_hash:
                errors.append("SEMANTIC_OUTPUT_HASH_MISMATCH")
    started = _aware_timestamp(record.get("started_at"))
    completed = _aware_timestamp(record.get("completed_at"))
    if started is None or completed is None or completed < started:
        errors.append("SEMANTIC_TIMESTAMP_INVALID")
    if not _nonnegative_number(record.get("latency_ms")):
        errors.append("SEMANTIC_LATENCY_INVALID")
    if not _nonnegative_int(record.get("retry_count")):
        errors.append("SEMANTIC_RETRY_COUNT_INVALID")
    token_usage = record.get("token_usage")
    token_keys = {"input_tokens", "output_tokens", "total_tokens"}
    if not isinstance(token_usage, dict) or set(token_usage) != token_keys:
        errors.append("SEMANTIC_TOKEN_USAGE_INVALID")
    elif any(
        value is not None and not _nonnegative_int(value)
        for value in token_usage.values()
    ):
        errors.append("SEMANTIC_TOKEN_COUNT_INVALID")
    elif all(_nonnegative_int(token_usage[key]) for key in token_keys) and (
        token_usage["total_tokens"]
        != token_usage["input_tokens"] + token_usage["output_tokens"]
    ):
        errors.append("SEMANTIC_TOKEN_TOTAL_MISMATCH")
    cache = record.get("cache")
    if (
        not isinstance(cache, dict)
        or set(cache) != {"cache_key", "hit"}
        or not isinstance(cache.get("cache_key"), str)
        or not _CACHE_KEY_PATTERN.fullmatch(cache["cache_key"])
        or not isinstance(cache.get("hit"), bool)
    ):
        errors.append("SEMANTIC_CACHE_INVALID")
    validation = record.get("validation_status")
    provider = record.get("provider_status")
    fallback = record.get("fallback_used")
    if validation not in {"accepted", "rejected", "not_run"}:
        errors.append("SEMANTIC_VALIDATION_STATUS_INVALID")
    if provider not in {
        "success",
        "timeout",
        "provider_error",
        "budget_exhausted",
        "not_called",
    }:
        errors.append("SEMANTIC_PROVIDER_STATUS_INVALID")
    if not isinstance(fallback, bool):
        errors.append("SEMANTIC_FALLBACK_FLAG_INVALID")
    if fallback is True and (
        not isinstance(record.get("fallback_reason"), str)
        or not record["fallback_reason"].strip()
    ):
        errors.append("SEMANTIC_FALLBACK_REASON_REQUIRED")
    if fallback is False and record.get("fallback_reason") is not None:
        errors.append("SEMANTIC_FALLBACK_REASON_UNEXPECTED")
    if validation == "accepted" and output is None:
        errors.append("SEMANTIC_ACCEPTED_OUTPUT_MISSING")
    if validation in {"rejected", "not_run"} and output is not None:
        errors.append("SEMANTIC_UNACCEPTED_OUTPUT_PRESENT")
    cache_hit = cache.get("hit") if isinstance(cache, dict) else None
    if cache_hit is True and (
        provider != "not_called"
        or validation != "accepted"
        or record.get("retry_count") != 0
        or fallback is not False
    ):
        errors.append("SEMANTIC_CACHE_HIT_STATUS_INVALID")
    error_code = record.get("error_code")
    if error_code is not None and (
        not isinstance(error_code, str) or not _ERROR_CODE_PATTERN.fullmatch(error_code)
    ):
        errors.append("SEMANTIC_ERROR_CODE_INVALID")
    if provider in {"timeout", "provider_error", "budget_exhausted"} and not error_code:
        errors.append("SEMANTIC_ERROR_CODE_REQUIRED")
    if provider == "success" and (
        error_code is not None or record.get("error_message") is not None
    ):
        errors.append("SEMANTIC_SUCCESS_ERROR_UNEXPECTED")
    error_message = record.get("error_message")
    if error_message is not None and not isinstance(error_message, str):
        errors.append("SEMANTIC_ERROR_MESSAGE_INVALID")
    if _contains_sensitive_value(record):
        errors.append("SEMANTIC_SENSITIVE_VALUE_FORBIDDEN")
    return errors


def _call_collection_errors(records: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    last_sequence: dict[str, int] = {}
    for record in records:
        errors.extend(_record_contract_errors(record))
        call_id = record.get("call_id")
        if isinstance(call_id, str):
            if call_id in seen_ids:
                errors.append("SEMANTIC_DUPLICATE_CALL_ID")
            seen_ids.add(call_id)
        run_id = record.get("run_id")
        sequence = record.get("call_sequence")
        if isinstance(run_id, str) and _nonnegative_int(sequence):
            previous = last_sequence.get(run_id)
            if previous is not None and sequence <= previous:
                errors.append("SEMANTIC_CALL_SEQUENCE_NOT_MONOTONIC")
            last_sequence[run_id] = sequence
    return errors


def _require_source_directory(source_run_dir: str | Path) -> Path:
    lexical = Path(source_run_dir).expanduser()
    if ".." in lexical.parts:
        raise ExactReplayError(EXACT_REPLAY_SOURCE_ARTIFACT_INVALID)
    if not lexical.exists() or not lexical.is_dir() or lexical.is_symlink():
        raise ExactReplayError(EXACT_REPLAY_SOURCE_ARTIFACT_INVALID)
    return lexical.resolve()


def _require_safe_file(path: Path, source_directory: Path, artifact: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ExactReplayError(
            EXACT_REPLAY_SOURCE_ARTIFACT_INVALID,
            artifact=artifact,
        )
    try:
        path.resolve().relative_to(source_directory)
    except ValueError as exc:
        raise ExactReplayError(
            EXACT_REPLAY_SOURCE_ARTIFACT_INVALID,
            artifact=artifact,
        ) from exc


def _snapshot_source_directory(source_directory: Path) -> tuple[SourceFileSnapshot, ...]:
    snapshots: list[SourceFileSnapshot] = []
    for path in sorted(source_directory.rglob("*")):
        if path.is_symlink():
            raise ExactReplayError(
                EXACT_REPLAY_SOURCE_ARTIFACT_INVALID,
                artifact=path.relative_to(source_directory).as_posix(),
            )
        if not path.is_file():
            continue
        _require_safe_file(path, source_directory, path.name)
        payload = path.read_bytes()
        stat = path.stat()
        snapshots.append(
            SourceFileSnapshot(
                relative_path=path.relative_to(source_directory).as_posix(),
                size_bytes=len(payload),
                sha256=_sha256_bytes(payload),
                mtime_ns=stat.st_mtime_ns,
            )
        )
    return tuple(snapshots)


def _load_json(path: Path, source_directory: Path, artifact: str) -> dict[str, Any]:
    _require_safe_file(path, source_directory, artifact)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExactReplayError(
            (
                EXACT_REPLAY_SEMANTIC_MANIFEST_INVALID
                if artifact == SEMANTIC_MANIFEST_FILENAME
                else EXACT_REPLAY_SOURCE_ARTIFACT_INVALID
            ),
            artifact=artifact,
        ) from exc
    if not isinstance(value, dict):
        raise ExactReplayError(
            EXACT_REPLAY_SOURCE_ARTIFACT_INVALID,
            artifact=artifact,
        )
    return value


def _load_calls(path: Path, source_directory: Path) -> tuple[dict[str, Any], ...]:
    _require_safe_file(path, source_directory, SEMANTIC_CALLS_FILENAME)
    try:
        payload = path.read_bytes()
        if not payload or not payload.endswith(b"\n"):
            raise ValueError("calls file is empty or has a partial tail")
        records: list[dict[str, Any]] = []
        for line in payload.splitlines():
            if not line:
                raise ValueError("calls file contains an empty line")
            item = json.loads(line.decode("utf-8"))
            if not isinstance(item, dict):
                raise ValueError("semantic call is not an object")
            records.append(item)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ExactReplayError(
            EXACT_REPLAY_SEMANTIC_CALL_CORRUPTED,
            artifact=SEMANTIC_CALLS_FILENAME,
        ) from exc
    errors = _call_collection_errors(records)
    if errors:
        if "SEMANTIC_SCHEMA_VERSION_INVALID" in errors:
            raise ExactReplayError(
                EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH,
                artifact=SEMANTIC_CALLS_FILENAME,
            )
        raise ExactReplayError(
            EXACT_REPLAY_SEMANTIC_CALL_CORRUPTED,
            artifact=SEMANTIC_CALLS_FILENAME,
            details={"reason_codes": sorted(set(errors))},
        )
    return tuple(records)


def _derived_manifest(
    source_directory: Path,
    manifest: dict[str, Any],
    calls: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    if set(manifest) != _MANIFEST_FIELDS:
        raise ExactReplayError(EXACT_REPLAY_SEMANTIC_MANIFEST_INVALID)
    if manifest.get("calls_file") != SEMANTIC_CALLS_FILENAME:
        raise ExactReplayError(EXACT_REPLAY_SEMANTIC_MANIFEST_INVALID)
    calls_payload = (source_directory / SEMANTIC_CALLS_FILENAME).read_bytes()
    if not isinstance(manifest.get("calls_file_sha256"), str) or not _SHA256_PATTERN.fullmatch(
        manifest["calls_file_sha256"]
    ):
        raise ExactReplayError(EXACT_REPLAY_SEMANTIC_MANIFEST_INVALID)
    created_at = manifest.get("created_at")
    finalized_at = manifest.get("finalized_at")
    if (
        _aware_timestamp(created_at) is None
        or _aware_timestamp(finalized_at) is None
        or manifest.get("complete") is not True
    ):
        raise ExactReplayError(EXACT_REPLAY_SEMANTIC_MANIFEST_INVALID)
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id or any(
        record.get("run_id") != run_id for record in calls
    ):
        raise ExactReplayError(EXACT_REPLAY_SEMANTIC_MANIFEST_INVALID)
    task_counts = dict.fromkeys(sorted(_SEMANTIC_TASKS), 0)
    for record in calls:
        task_counts[str(record["task"])] += 1
    exact_ready = bool(
        calls
        and all(
            record["validation_status"] == "accepted"
            and record["validated_output"] is not None
            and record["validated_output_sha256"] is not None
            and record["fallback_used"] is False
            and record["provider_status"]
            not in {"timeout", "provider_error", "budget_exhausted"}
            for record in calls
        )
    )
    return {
        "schema_version": SEMANTIC_MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "calls_file": SEMANTIC_CALLS_FILENAME,
        "calls_file_sha256": _sha256_bytes(calls_payload),
        "record_count": len(calls),
        "tasks": task_counts,
        "accepted_count": sum(
            record["validation_status"] == "accepted" for record in calls
        ),
        "rejected_count": sum(
            record["validation_status"] == "rejected" for record in calls
        ),
        "fallback_count": sum(bool(record["fallback_used"]) for record in calls),
        "cache_hit_count": sum(bool(record["cache"]["hit"]) for record in calls),
        "provider_call_count": sum(
            1 + int(record["retry_count"])
            for record in calls
            if record["provider_status"] in _PROVIDER_CALLED_STATUSES
        ),
        "prompt_versions": sorted({str(record["prompt_version"]) for record in calls}),
        "models": sorted({str(record["model"]) for record in calls}),
        "complete": True,
        "exact_replay_ready": exact_ready,
        "created_at": created_at,
        "finalized_at": finalized_at,
    }


def _validate_manifest(
    source_directory: Path,
    manifest: dict[str, Any],
    calls: tuple[dict[str, Any], ...] | None = None,
) -> None:
    if manifest.get("schema_version") != SEMANTIC_MANIFEST_SCHEMA_VERSION:
        raise ExactReplayError(EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH)
    # Readiness is a first-class eligibility gate.  Report it directly even
    # though the manifest's self-verifier will also reject a forged readiness
    # flag for an otherwise-ready calls file.
    if manifest.get("complete") is not True or manifest.get("exact_replay_ready") is not True:
        raise ExactReplayError(EXACT_REPLAY_SEMANTIC_NOT_READY)
    if calls is None:
        raise ExactReplayError(EXACT_REPLAY_SEMANTIC_MANIFEST_INVALID)
    expected = _derived_manifest(source_directory, manifest, calls)
    mismatched = sorted(
        field for field in _MANIFEST_FIELDS if manifest.get(field) != expected.get(field)
    )
    if mismatched:
        call_corruption = "calls_file_sha256" in mismatched
        raise ExactReplayError(
            (
                EXACT_REPLAY_SEMANTIC_CALL_CORRUPTED
                if call_corruption
                else EXACT_REPLAY_SEMANTIC_MANIFEST_INVALID
            ),
            artifact=SEMANTIC_MANIFEST_FILENAME,
            details={"mismatched_fields": mismatched},
        )


def _validate_call_versions(calls: tuple[dict[str, Any], ...]) -> None:
    for record in calls:
        if record.get("schema_version") != SEMANTIC_CALL_SCHEMA_VERSION:
            raise ExactReplayError(EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH)
        task = record.get("task")
        expected = _SUPPORTED_CALL_IDENTITIES.get(str(task))
        if expected is None or any(record.get(key) != value for key, value in expected.items()):
            raise ExactReplayError(
                EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH,
                details={"task": task, "call_id": record.get("call_id")},
            )
        if record.get("execution_mode") != "live":
            raise ExactReplayError(EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH)
        if (
            record.get("validation_status") != "accepted"
            or record.get("validated_output") is None
            or record.get("fallback_used") is not False
            or record.get("provider_status")
            in {"timeout", "provider_error", "budget_exhausted"}
        ):
            raise ExactReplayError(EXACT_REPLAY_SEMANTIC_NOT_READY)


def _identity(payload: dict[str, Any]) -> tuple[str, str]:
    return str(payload.get("run_id") or ""), str(payload.get("ticker") or "").upper()


def _validate_source_identity(
    *,
    source_directory: Path,
    payloads: dict[str, dict[str, Any]],
    calls: tuple[dict[str, Any], ...],
) -> tuple[str, str]:
    metadata = payloads["metadata.json"]
    source_run_id, ticker = _identity(metadata)
    if not source_run_id or source_directory.name != source_run_id:
        raise ExactReplayError(EXACT_REPLAY_SEMANTIC_RUN_ID_MISMATCH)
    if not ticker:
        raise ExactReplayError(EXACT_REPLAY_TICKER_IDENTITY_MISMATCH)

    for filename, payload in payloads.items():
        if filename == SEMANTIC_MANIFEST_FILENAME:
            artifact_run_id = str(payload.get("run_id") or "")
            artifact_ticker = ticker
        else:
            artifact_run_id, artifact_ticker = _identity(payload)
        if artifact_run_id != source_run_id:
            raise ExactReplayError(
                EXACT_REPLAY_SEMANTIC_RUN_ID_MISMATCH,
                artifact=filename,
            )
        if (
            filename not in {SEMANTIC_MANIFEST_FILENAME, "run_audit.json"}
            and (not artifact_ticker or artifact_ticker != ticker)
        ):
            raise ExactReplayError(
                EXACT_REPLAY_TICKER_IDENTITY_MISMATCH,
                artifact=filename,
            )

    for record in calls:
        if record.get("run_id") != source_run_id:
            raise ExactReplayError(EXACT_REPLAY_SEMANTIC_RUN_ID_MISMATCH)

    structured = payloads["structured_agent_outputs.json"].get("records")
    matches = payloads["alpha_matches.json"].get("matches")
    if not isinstance(structured, list) or not isinstance(matches, list):
        raise ExactReplayError(EXACT_REPLAY_SOURCE_ARTIFACT_INVALID)
    for record in (*structured, *matches):
        if not isinstance(record, dict):
            raise ExactReplayError(EXACT_REPLAY_SOURCE_ARTIFACT_INVALID)
        if str(record.get("run_id") or "") != source_run_id:
            raise ExactReplayError(EXACT_REPLAY_SEMANTIC_RUN_ID_MISMATCH)
        if str(record.get("ticker") or "").upper() != ticker:
            raise ExactReplayError(EXACT_REPLAY_TICKER_IDENTITY_MISMATCH)
    return source_run_id, ticker


def _validate_artifact_contracts(payloads: dict[str, dict[str, Any]]) -> None:
    for filename, expected_schema in _SUPPORTED_ARTIFACT_SCHEMAS.items():
        if payloads[filename].get("schema_version") != expected_schema:
            raise ExactReplayError(
                EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH,
                artifact=filename,
            )
    if payloads["artifact_manifest.json"].get("artifact_completeness") != "pass":
        raise ExactReplayError(
            EXACT_REPLAY_SOURCE_ARTIFACT_INVALID,
            artifact="artifact_manifest.json",
        )

    structured = payloads["structured_agent_outputs.json"]
    alpha_matches = payloads["alpha_matches.json"]
    extracted = payloads["extracted_structures.json"]
    if structured.get("adapter_version") != "week1.claim_extraction.v2":
        raise ExactReplayError(EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH)
    if alpha_matches.get("mapper_version") != "week2.alpha_mapper.v2":
        raise ExactReplayError(EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH)
    metadata = extracted.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("extractor_version") != "week2.structure_extractor.v2":
        raise ExactReplayError(EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH)
    if not isinstance(extracted.get("nodes"), list) or not isinstance(extracted.get("edges"), list):
        raise ExactReplayError(EXACT_REPLAY_SOURCE_ARTIFACT_INVALID)


def _validate_manifest_artifact_hashes(
    source_directory: Path,
    artifact_manifest: dict[str, Any],
) -> None:
    entries = artifact_manifest.get("artifacts")
    if not isinstance(entries, list):
        raise ExactReplayError(EXACT_REPLAY_SOURCE_ARTIFACT_INVALID)
    by_name = {
        str(entry.get("artifact_name")): entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("artifact_name")
    }
    for filename in (
        "structured_agent_outputs.json",
        "alpha_matches.json",
        "structure_graph.json",
        "entity_alpha_exposures.json",
        "conflicts.json",
    ):
        entry = by_name.get(filename)
        if entry is None or entry.get("status") != "valid":
            raise ExactReplayError(
                EXACT_REPLAY_SOURCE_ARTIFACT_INVALID,
                artifact=filename,
            )
        actual = _sha256_bytes((source_directory / filename).read_bytes())
        if entry.get("sha256") != actual:
            raise ExactReplayError(
                EXACT_REPLAY_SOURCE_ARTIFACT_HASH_MISMATCH,
                artifact=filename,
            )


def load_exact_semantic_source_bundle(
    source_run_dir: str | Path,
) -> ExactSemanticSourceBundle:
    """Load and verify one eligible live run without modifying it."""

    source_directory = _require_source_directory(source_run_dir)
    missing = [name for name in REQUIRED_SOURCE_ARTIFACTS if not (source_directory / name).exists()]
    if missing:
        raise ExactReplayError(
            EXACT_REPLAY_SEMANTIC_ARTIFACT_MISSING,
            artifact=missing[0],
            details={"missing_artifacts": missing},
        )

    before = _snapshot_source_directory(source_directory)
    payloads = {
        filename: _load_json(source_directory / filename, source_directory, filename)
        for filename in _JSON_ARTIFACTS
    }
    calls = _load_calls(source_directory / SEMANTIC_CALLS_FILENAME, source_directory)
    _validate_manifest(
        source_directory,
        payloads[SEMANTIC_MANIFEST_FILENAME],
        calls,
    )
    _validate_call_versions(calls)
    source_run_id, ticker = _validate_source_identity(
        source_directory=source_directory,
        payloads=payloads,
        calls=calls,
    )
    _validate_artifact_contracts(payloads)
    _validate_manifest_artifact_hashes(
        source_directory,
        payloads["artifact_manifest.json"],
    )
    after = _snapshot_source_directory(source_directory)
    if before != after:
        raise ExactReplayError(EXACT_REPLAY_SOURCE_ARTIFACT_HASH_MISMATCH)

    return ExactSemanticSourceBundle(
        source_directory=source_directory,
        source_run_id=source_run_id,
        ticker=ticker,
        metadata=payloads["metadata.json"],
        raw_agent_outputs=payloads["raw_agent_outputs.json"],
        semantic_manifest=payloads[SEMANTIC_MANIFEST_FILENAME],
        semantic_calls=calls,
        structured_agent_outputs=payloads["structured_agent_outputs.json"],
        alpha_matches=payloads["alpha_matches.json"],
        extracted_structures=payloads["extracted_structures.json"],
        structure_graph=payloads["structure_graph.json"],
        entity_alpha_exposures=payloads["entity_alpha_exposures.json"],
        conflicts=payloads["conflicts.json"],
        run_audit=payloads["run_audit.json"],
        artifact_manifest=payloads["artifact_manifest.json"],
        source_files=before,
    )


def verify_source_bundle_unchanged(bundle: ExactSemanticSourceBundle) -> bool:
    """Recheck path, size, hash, and mtime for every source-run file."""

    current = _snapshot_source_directory(bundle.source_directory)
    if current != bundle.source_files:
        raise ExactReplayError(EXACT_REPLAY_SOURCE_ARTIFACT_HASH_MISMATCH)
    return True


__all__ = [
    "ExactReplayError",
    "ExactSemanticSourceBundle",
    "SourceFileSnapshot",
    "REQUIRED_SOURCE_ARTIFACTS",
    "SEMANTIC_ARTIFACT_COPY_FILENAMES",
    "load_exact_semantic_source_bundle",
    "verify_source_bundle_unchanged",
    "sha256_canonical_json",
    "EXACT_REPLAY_SEMANTIC_ARTIFACT_MISSING",
    "EXACT_REPLAY_SEMANTIC_MANIFEST_INVALID",
    "EXACT_REPLAY_SEMANTIC_NOT_READY",
    "EXACT_REPLAY_SEMANTIC_CALL_CORRUPTED",
    "EXACT_REPLAY_SEMANTIC_INPUT_MISMATCH",
    "EXACT_REPLAY_SEMANTIC_OUTPUT_MISMATCH",
    "EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH",
    "EXACT_REPLAY_SEMANTIC_CALL_AMBIGUOUS",
    "EXACT_REPLAY_SEMANTIC_BINDING_MISSING",
    "EXACT_REPLAY_SEMANTIC_BINDING_ORPHAN",
    "EXACT_REPLAY_SEMANTIC_RUN_ID_MISMATCH",
    "EXACT_REPLAY_TICKER_IDENTITY_MISMATCH",
    "EXACT_REPLAY_SOURCE_ARTIFACT_INVALID",
    "EXACT_REPLAY_SOURCE_ARTIFACT_HASH_MISMATCH",
    "EXACT_REPLAY_STAGING_WRITE_FAILED",
    "EXACT_REPLAY_OUTPUT_VALIDATION_FAILED",
    "EXACT_REPLAY_PROVIDER_CALL_ATTEMPTED",
    "EXACT_REPLAY_DATABASE_WRITE_ATTEMPTED",
    "EXACT_REPLAY_MODE_FALLBACK_FORBIDDEN",
]
