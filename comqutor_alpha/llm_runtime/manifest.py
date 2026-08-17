"""Self-verifying manifest for offline semantic-call artifacts."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from comqutor_alpha.llm_runtime.canonical_json import canonical_json_bytes, sha256_bytes
from comqutor_alpha.llm_runtime.contracts import (
    PROVIDER_CALLED_STATUSES,
    validate_semantic_call_records,
)
from comqutor_alpha.llm_runtime.errors import (
    ManifestIntegrityError,
    ValidationIssue,
    ValidationResult,
    validation_failure,
    validation_success,
)
from comqutor_alpha.llm_runtime.recorder import SEMANTIC_CALLS_FILENAME

SEMANTIC_MANIFEST_SCHEMA_VERSION = "comqutor.semantic_manifest.v1"
SEMANTIC_MANIFEST_FILENAME = "llm_semantic_manifest.json"

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
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


def _aware_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _protected_output_kind(directory: Path) -> str | None:
    repository_root = Path(__file__).resolve().parents[2]
    resolved = directory.resolve()
    for kind, protected in (
        ("runs", repository_root / "outputs/runs"),
        ("replays", repository_root / "outputs/replays"),
    ):
        try:
            resolved.relative_to(protected.resolve())
        except ValueError:
            continue
        return kind
    return None


def _read_calls(calls_path: Path) -> tuple[bytes, list[dict[str, Any]]]:
    if not calls_path.is_file():
        raise ManifestIntegrityError(
            "SEMANTIC_MANIFEST_CALLS_FILE_MISSING",
            "Semantic calls file is missing",
            path=str(calls_path),
        )
    payload = calls_path.read_bytes()
    if payload and not payload.endswith(b"\n"):
        raise ManifestIntegrityError(
            "SEMANTIC_MANIFEST_CALLS_TAIL_CORRUPTED",
            "Semantic calls JSONL ends with a partial line",
            path=str(calls_path),
        )
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(payload.splitlines(), start=1):
        if not line:
            raise ManifestIntegrityError(
                "SEMANTIC_MANIFEST_CALLS_MIDDLE_CORRUPTED",
                f"Semantic calls JSONL has an empty line at {line_number}",
                path=str(calls_path),
            )
        try:
            decoded = line.decode("utf-8")
            record = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ManifestIntegrityError(
                "SEMANTIC_MANIFEST_CALLS_MIDDLE_CORRUPTED",
                f"Semantic calls JSONL has invalid data at line {line_number}",
                path=str(calls_path),
            ) from exc
        if not isinstance(record, dict):
            raise ManifestIntegrityError(
                "SEMANTIC_MANIFEST_CALL_NOT_OBJECT",
                f"Semantic call at line {line_number} is not an object",
                path=str(calls_path),
            )
        records.append(record)
    validation = validate_semantic_call_records(records)
    if not validation.valid:
        raise ManifestIntegrityError(
            "SEMANTIC_MANIFEST_CALL_RECORD_INVALID",
            f"Semantic calls fail validation: {','.join(validation.reason_codes)}",
            path=str(calls_path),
        )
    return payload, records


def build_semantic_manifest(
    *,
    run_id: str,
    calls_path: str | Path,
    complete: bool,
    created_at: str,
    finalized_at: str | None = None,
) -> dict[str, Any]:
    """Derive a v1 manifest exclusively from a validated calls file."""

    if not isinstance(run_id, str) or not run_id.strip():
        raise ManifestIntegrityError("SEMANTIC_MANIFEST_RUN_ID_INVALID", "run_id is required")
    path = Path(calls_path)
    if path.name != SEMANTIC_CALLS_FILENAME:
        raise ManifestIntegrityError(
            "SEMANTIC_MANIFEST_CALLS_FILENAME_INVALID",
            f"Calls file must be named {SEMANTIC_CALLS_FILENAME}",
        )
    if not isinstance(complete, bool):
        raise ManifestIntegrityError(
            "SEMANTIC_MANIFEST_COMPLETE_INVALID",
            "complete must be boolean",
        )
    if not _aware_timestamp(created_at):
        raise ManifestIntegrityError(
            "SEMANTIC_MANIFEST_CREATED_AT_INVALID",
            "created_at must be a timezone-aware ISO timestamp",
        )
    if finalized_at is not None and not _aware_timestamp(finalized_at):
        raise ManifestIntegrityError(
            "SEMANTIC_MANIFEST_FINALIZED_AT_INVALID",
            "finalized_at must be null or a timezone-aware ISO timestamp",
        )
    if complete and finalized_at is None:
        raise ManifestIntegrityError(
            "SEMANTIC_MANIFEST_FINALIZED_AT_REQUIRED",
            "A complete manifest requires finalized_at",
        )
    if not complete and finalized_at is not None:
        raise ManifestIntegrityError(
            "SEMANTIC_MANIFEST_FINALIZED_AT_UNEXPECTED",
            "An incomplete manifest cannot be finalized",
        )

    payload, records = _read_calls(path)
    wrong_run = [record["call_id"] for record in records if record["run_id"] != run_id]
    if wrong_run:
        raise ManifestIntegrityError(
            "SEMANTIC_MANIFEST_RUN_ID_MISMATCH",
            "Every semantic call must match the manifest run_id",
        )

    # Preserve the exact pre-Phase-1 manifest shape for live runs that use
    # only the original three tasks. The evaluation-only Shadow task appears
    # only when at least one such record is actually present.
    original_tasks = {"structured_adapter", "alpha_classifier", "structure_extractor"}
    observed_tasks = {str(record["task"]) for record in records}
    manifest_tasks = original_tasks | (observed_tasks - original_tasks)
    task_counts = dict.fromkeys(sorted(manifest_tasks), 0)
    for record in records:
        task_counts[record["task"]] += 1
    exact_replay_ready = bool(
        complete
        and finalized_at is not None
        and records
        and all(
            record["validation_status"] == "accepted"
            and record["validated_output"] is not None
            and record["validated_output_sha256"] is not None
            and record["fallback_used"] is False
            and record["provider_status"] not in {
                "timeout",
                "provider_error",
                "budget_exhausted",
            }
            for record in records
        )
    )
    return {
        "schema_version": SEMANTIC_MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "calls_file": SEMANTIC_CALLS_FILENAME,
        "calls_file_sha256": sha256_bytes(payload),
        "record_count": len(records),
        "tasks": task_counts,
        "accepted_count": sum(record["validation_status"] == "accepted" for record in records),
        "rejected_count": sum(record["validation_status"] == "rejected" for record in records),
        "fallback_count": sum(record["fallback_used"] for record in records),
        "cache_hit_count": sum(record["cache"]["hit"] for record in records),
        "provider_call_count": sum(
            1 + record["retry_count"]
            for record in records
            if record["provider_status"] in PROVIDER_CALLED_STATUSES
        ),
        "prompt_versions": sorted({record["prompt_version"] for record in records}),
        "models": sorted({record["model"] for record in records}),
        "complete": complete,
        "exact_replay_ready": exact_replay_ready,
        "created_at": created_at,
        "finalized_at": finalized_at,
    }


def verify_semantic_manifest(manifest_path: str | Path) -> ValidationResult:
    """Verify manifest schema, JSONL integrity, derived counts, and hashes."""

    path = Path(manifest_path)
    if not path.is_file():
        return validation_failure(
            ValidationIssue(
                "SEMANTIC_MANIFEST_FILE_MISSING",
                "Semantic manifest file is missing",
                str(path),
            )
        )
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return validation_failure(
            ValidationIssue("SEMANTIC_MANIFEST_JSON_INVALID", str(exc), str(path))
        )
    if not isinstance(manifest, dict):
        return validation_failure(
            ValidationIssue("SEMANTIC_MANIFEST_NOT_OBJECT", "Manifest must be an object", str(path))
        )
    missing = sorted(_MANIFEST_FIELDS - manifest.keys())
    unknown = sorted(manifest.keys() - _MANIFEST_FIELDS)
    if missing or unknown:
        issues = [
            ValidationIssue(
                "SEMANTIC_MANIFEST_REQUIRED_FIELD_MISSING",
                "Required field is missing",
                f"$.{field}",
            )
            for field in missing
        ]
        issues.extend(
            ValidationIssue(
                "SEMANTIC_MANIFEST_UNKNOWN_FIELD",
                "Unknown field is not allowed",
                f"$.{field}",
            )
            for field in unknown
        )
        return validation_failure(*issues)
    if manifest["schema_version"] != SEMANTIC_MANIFEST_SCHEMA_VERSION:
        return validation_failure(
            ValidationIssue(
                "SEMANTIC_MANIFEST_SCHEMA_VERSION_INVALID",
                "Unsupported manifest schema version",
                "$.schema_version",
            )
        )
    if manifest["calls_file"] != SEMANTIC_CALLS_FILENAME:
        return validation_failure(
            ValidationIssue(
                "SEMANTIC_MANIFEST_CALLS_FILENAME_INVALID",
                "Manifest calls_file is not the v1 filename",
                "$.calls_file",
            )
        )
    if not isinstance(manifest["calls_file_sha256"], str) or not _SHA256_PATTERN.fullmatch(
        manifest["calls_file_sha256"]
    ):
        return validation_failure(
            ValidationIssue(
                "SEMANTIC_MANIFEST_CALLS_HASH_FORMAT_INVALID",
                "calls_file_sha256 must be lowercase SHA-256",
                "$.calls_file_sha256",
            )
        )
    try:
        expected = build_semantic_manifest(
            run_id=manifest["run_id"],
            calls_path=path.parent / manifest["calls_file"],
            complete=manifest["complete"],
            created_at=manifest["created_at"],
            finalized_at=manifest["finalized_at"],
        )
    except (KeyError, TypeError, ManifestIntegrityError) as exc:
        reason_code = getattr(exc, "reason_code", "SEMANTIC_MANIFEST_FIELD_TYPE_INVALID")
        return validation_failure(ValidationIssue(reason_code, str(exc), str(path)))

    issues: list[ValidationIssue] = []
    for field in sorted(_MANIFEST_FIELDS):
        if manifest[field] != expected[field]:
            reason_code = (
                "SEMANTIC_MANIFEST_CALLS_HASH_MISMATCH"
                if field == "calls_file_sha256"
                else "SEMANTIC_MANIFEST_DERIVED_FIELD_MISMATCH"
            )
            issues.append(
                ValidationIssue(
                    reason_code,
                    f"Manifest field does not match calls artifact: {field}",
                    f"$.{field}",
                )
            )
    return validation_success() if not issues else validation_failure(*issues)


def write_semantic_manifest_atomic(
    *,
    manifest: Mapping[str, Any],
    output_directory: str | Path,
    fsync: bool = False,
    allow_run_artifacts: bool = False,
) -> Path:
    """Validate and atomically replace ``llm_semantic_manifest.json``."""

    directory = Path(output_directory)
    if not directory.is_dir():
        raise ManifestIntegrityError(
            "SEMANTIC_MANIFEST_OUTPUT_DIRECTORY_MISSING",
            "Manifest output directory must already exist",
        )
    protected_kind = _protected_output_kind(directory)
    if protected_kind == "replays" or (protected_kind == "runs" and not allow_run_artifacts):
        raise ManifestIntegrityError(
            "SEMANTIC_MANIFEST_PROTECTED_OUTPUT_DIRECTORY_FORBIDDEN",
            "Semantic manifests require explicit live-run authorization and never write replay artifacts",
        )
    value = dict(manifest)
    expected = build_semantic_manifest(
        run_id=value.get("run_id"),
        calls_path=directory / SEMANTIC_CALLS_FILENAME,
        complete=value.get("complete"),
        created_at=value.get("created_at"),
        finalized_at=value.get("finalized_at"),
    )
    if value != expected:
        raise ManifestIntegrityError(
            "SEMANTIC_MANIFEST_CONTENT_MISMATCH",
            "Manifest content is not the exact derived v1 representation",
        )

    destination = directory / SEMANTIC_MANIFEST_FILENAME
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{SEMANTIC_MANIFEST_FILENAME}.",
        suffix=".tmp",
        dir=directory,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(canonical_json_bytes(value) + b"\n")
            handle.flush()
            if fsync:
                os.fsync(handle.fileno())
        os.replace(temporary_path, destination)
        if fsync:
            directory_descriptor = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    verification = verify_semantic_manifest(destination)
    if not verification.valid:
        raise ManifestIntegrityError(
            verification.reason_codes[0],
            f"Written manifest failed verification: {','.join(verification.reason_codes)}",
            path=str(destination),
        )
    return destination
