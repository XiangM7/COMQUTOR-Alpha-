"""Atomic, immutable JSON artifacts for reproducible COMQUTOR runs."""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID


class ArtifactStoreError(RuntimeError):
    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code


def _json_default(value: object) -> str:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"unsupported artifact value: {type(value).__name__}")


class ArtifactStore:
    """Write a run directory once, using temp-directory + atomic rename."""

    def __init__(self, root: Path | str):
        self.root = Path(root)

    @staticmethod
    def _validated_run_id(run_id: UUID | str) -> UUID:
        try:
            parsed = run_id if isinstance(run_id, UUID) else UUID(run_id)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ArtifactStoreError("invalid_run_id", "run_id must be a UUID") from exc
        if str(parsed) != str(run_id):
            raise ArtifactStoreError("invalid_run_id", "run_id must use canonical UUID form")
        return parsed

    def run_path(self, run_id: UUID | str) -> Path:
        return self.root / str(self._validated_run_id(run_id))

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        serialized = json.dumps(
            payload,
            default=_json_default,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        with path.open("x", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

    def write_initial_run(
        self,
        *,
        run_id: UUID | str,
        metadata: Mapping[str, Any],
        raw_reports: Sequence[Mapping[str, Any]],
        upstream_decision: Mapping[str, Any],
    ) -> Path:
        parsed = self._validated_run_id(run_id)
        self.root.mkdir(parents=True, exist_ok=True)
        final_dir = self.root / str(parsed)
        if final_dir.exists():
            raise ArtifactStoreError("duplicate_run_id", f"run already exists: {parsed}")

        temp_dir = self.root / f".tmp-{parsed}"
        if temp_dir.exists():
            raise ArtifactStoreError("stale_temp_run", f"temporary run exists: {parsed}")
        temp_dir.mkdir()
        try:
            self._write_json(temp_dir / "metadata.json", dict(metadata))
            self._write_json(temp_dir / "raw_agent_outputs.json", list(raw_reports))
            self._write_json(temp_dir / "upstream_decision.json", dict(upstream_decision))
            temp_dir.rename(final_dir)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        return final_dir

    def write_derived_artifact(
        self,
        *,
        run_id: UUID | str,
        filename: str,
        payload: Any,
    ) -> Path:
        if not re.fullmatch(r"[a-z][a-z0-9_]*\.json", filename):
            raise ArtifactStoreError("invalid_artifact_name", "artifact filename is unsafe")
        run_dir = self.run_path(run_id)
        if not run_dir.is_dir():
            raise ArtifactStoreError("missing_run", f"run does not exist: {run_id}")
        destination = run_dir / filename
        if destination.exists():
            raise ArtifactStoreError("duplicate_artifact", f"artifact already exists: {filename}")
        temporary = run_dir / f".{filename}.tmp"
        if temporary.exists():
            raise ArtifactStoreError("stale_temp_artifact", f"temporary artifact exists: {filename}")
        try:
            self._write_json(temporary, payload)
            try:
                os.link(temporary, destination)
            except FileExistsError as exc:
                raise ArtifactStoreError(
                    "duplicate_artifact", f"artifact already exists: {filename}"
                ) from exc
        finally:
            temporary.unlink(missing_ok=True)
        return destination
