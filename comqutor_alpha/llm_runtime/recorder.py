"""Append-only semantic-call JSONL recorder for offline artifact tests."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from comqutor_alpha.llm_runtime.canonical_json import canonical_json_bytes
from comqutor_alpha.llm_runtime.contracts import (
    EXECUTION_MODES,
    SemanticCallRecord,
    validate_semantic_call_record,
    validate_semantic_call_records,
)
from comqutor_alpha.llm_runtime.errors import (
    ContractValidationError,
    RecorderIntegrityError,
    ValidationIssue,
    ValidationResult,
    validation_failure,
    validation_success,
)

SEMANTIC_CALLS_FILENAME = "llm_semantic_calls.jsonl"


class SemanticCallRecorder:
    """Thread-serialized append-only recorder.

    Callers remain responsible for allocating strictly increasing sequence
    numbers. One recorder instance is safe for concurrent threads; cross-process
    writes are intentionally unsupported in v1.
    """

    def __init__(
        self,
        *,
        run_id: str,
        output_directory: str | Path,
        mode: str,
        clock: Callable[[], datetime] | None = None,
        fsync: bool = False,
        allow_run_artifacts: bool = False,
    ) -> None:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("RECORDER_RUN_ID_INVALID")
        if mode not in EXECUTION_MODES:
            raise ValueError("RECORDER_MODE_INVALID")
        directory = Path(output_directory)
        if not directory.is_dir():
            raise ValueError("RECORDER_OUTPUT_DIRECTORY_MISSING")
        resolved = directory.resolve()
        repository_root = Path(__file__).resolve().parents[2]
        protected_directories = (repository_root / "outputs/replays",)
        if not allow_run_artifacts:
            protected_directories = (
                repository_root / "outputs/runs",
                *protected_directories,
            )
        for protected in protected_directories:
            try:
                resolved.relative_to(protected.resolve())
            except ValueError:
                continue
            raise ValueError("RECORDER_PROTECTED_OUTPUT_DIRECTORY_FORBIDDEN")

        self.run_id = run_id
        self.output_directory = resolved
        self.mode = mode
        self.calls_path = resolved / SEMANTIC_CALLS_FILENAME
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._fsync = bool(fsync)
        self._lock = threading.Lock()
        self._closed = False
        self._last_sequence = -1
        self._call_ids: set[str] = set()
        if self.calls_path.exists():
            records = self._read_all_unlocked()
            if records:
                self._last_sequence = records[-1]["call_sequence"]
                self._call_ids = {record["call_id"] for record in records}

    def ensure_artifact(self) -> Path:
        """Create an empty append-only artifact without truncating history."""

        with self._lock:
            if self._closed:
                raise RecorderIntegrityError("RECORDER_CLOSED", "Recorder is closed")
            with self.calls_path.open("ab") as handle:
                handle.flush()
                if self._fsync:
                    os.fsync(handle.fileno())
            return self.calls_path

    def append(self, record: Mapping[str, Any] | SemanticCallRecord) -> None:
        with self._lock:
            if self._closed:
                raise RecorderIntegrityError("RECORDER_CLOSED", "Recorder is closed")
            value = record.to_dict() if isinstance(record, SemanticCallRecord) else dict(record)
            result = validate_semantic_call_record(value)
            if not result.valid:
                raise ContractValidationError(result)
            if value["run_id"] != self.run_id:
                raise RecorderIntegrityError(
                    "RECORDER_RUN_ID_MISMATCH",
                    "Record run_id differs from recorder run_id",
                )
            if value["execution_mode"] != self.mode:
                raise RecorderIntegrityError(
                    "RECORDER_MODE_MISMATCH",
                    "Record execution_mode differs from recorder mode",
                )
            if value["call_id"] in self._call_ids:
                raise RecorderIntegrityError(
                    "RECORDER_DUPLICATE_CALL_ID",
                    "Duplicate call_id is forbidden",
                )
            if value["call_sequence"] <= self._last_sequence:
                raise RecorderIntegrityError(
                    "RECORDER_SEQUENCE_NOT_MONOTONIC",
                    "call_sequence must increase strictly",
                )

            line = canonical_json_bytes(value) + b"\n"
            with self.calls_path.open("ab") as handle:
                handle.write(line)
                handle.flush()
                if self._fsync:
                    os.fsync(handle.fileno())
            self._last_sequence = value["call_sequence"]
            self._call_ids.add(value["call_id"])

    def _read_all_unlocked(self) -> list[dict[str, Any]]:
        if not self.calls_path.exists():
            return []
        payload = self.calls_path.read_bytes()
        if not payload:
            return []
        if not payload.endswith(b"\n"):
            raise RecorderIntegrityError(
                "RECORDER_TAIL_CORRUPTED",
                "JSONL file ends with a partial or corrupt line",
            )
        records: list[dict[str, Any]] = []
        for index, line in enumerate(payload.splitlines(), start=1):
            if not line:
                raise RecorderIntegrityError(
                    "RECORDER_MIDDLE_LINE_CORRUPTED",
                    f"Empty JSONL line at {index}",
                )
            try:
                decoded = line.decode("utf-8")
                value = json.loads(decoded)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RecorderIntegrityError(
                    "RECORDER_MIDDLE_LINE_CORRUPTED",
                    f"Invalid JSONL line at {index}",
                ) from exc
            if not isinstance(value, dict):
                raise RecorderIntegrityError(
                    "RECORDER_RECORD_NOT_OBJECT",
                    f"JSONL line {index} is not an object",
                )
            records.append(value)

        result = validate_semantic_call_records(records)
        if not result.valid:
            raise RecorderIntegrityError(
                result.reason_codes[0],
                f"JSONL records failed validation: {','.join(result.reason_codes)}",
            )
        for index, record in enumerate(records, start=1):
            if record["run_id"] != self.run_id:
                raise RecorderIntegrityError(
                    "RECORDER_RUN_ID_MISMATCH",
                    f"JSONL line {index} has the wrong run_id",
                )
            if record["execution_mode"] != self.mode:
                raise RecorderIntegrityError(
                    "RECORDER_MODE_MISMATCH",
                    f"JSONL line {index} has the wrong mode",
                )
        return records

    def read_all(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._read_all_unlocked()

    def verify_integrity(self) -> ValidationResult:
        with self._lock:
            try:
                self._read_all_unlocked()
            except RecorderIntegrityError as exc:
                return validation_failure(
                    ValidationIssue(exc.reason_code, str(exc), exc.path)
                )
            return validation_success()

    def record_count(self) -> int:
        return len(self.read_all())

    def close(self) -> None:
        with self._lock:
            self._closed = True

    @property
    def clock(self) -> Callable[[], datetime]:
        return self._clock
