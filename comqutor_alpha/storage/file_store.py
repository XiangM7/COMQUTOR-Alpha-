"""File-backed persistence helpers for local COMQUTOR validation."""

from __future__ import annotations

import contextlib
import json
import os
import re
from pathlib import Path
from uuid import uuid4

# Constants for validating run IDs and allowed artifact filenames.
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
ALLOWED_ARTIFACT_FILENAMES = {
    "metadata.json",
    "raw_agent_outputs.json",
    "structured_agent_outputs.json",
    "alpha_matches.json",
    "extracted_structures.json",
    "structure_graph.json",
    "entity_alpha_exposures.json",
    "week3_pipeline_status.json",
    "run_audit.json",
    "final_report.md",
    "research_response.json",
    "market_data_snapshot.json",
    "data_sanity.json",
    "tradingagents_comqutor_vocabulary_snapshot.json",
}
ALLOWED_ARTIFACT_PATHS = {
    *ALLOWED_ARTIFACT_FILENAMES,
    "error_logs/structured_output_adapter_errors.jsonl",
    "error_logs/week2_llm_errors.jsonl",
    "error_logs/week2_pipeline_errors.jsonl",
    "error_logs/week3_pipeline_errors.jsonl",
}

# Validate and normalize a request run_id.
def validate_run_id_for_path(run_id) -> str:
    if run_id is None:
        raise ValueError("INVALID_RUN_ID: run_id is required")

    value = str(run_id)
    stripped = value.strip()
    if not stripped:
        raise ValueError("INVALID_RUN_ID: run_id is empty")
    if value != stripped:
        raise ValueError("INVALID_RUN_ID: run_id must not contain leading or trailing whitespace")
    if ".." in value or "/" in value or "\\" in value:
        raise ValueError("INVALID_RUN_ID: run_id must not contain path traversal characters")
    if Path(value).is_absolute():
        raise ValueError("INVALID_RUN_ID: run_id must not be an absolute path")
    if not RUN_ID_PATTERN.fullmatch(value):
        raise ValueError("INVALID_RUN_ID: run_id may contain only letters, numbers, underscore, or dash")
    return value

# Validate an artifact filename against the allowed set.
def validate_artifact_filename(filename) -> str:
    value = str(filename or "")
    if "/" in value or "\\" in value or ".." in value:
        raise ValueError("INVALID_ARTIFACT_FILENAME: filename must not contain path separators")
    if value not in ALLOWED_ARTIFACT_FILENAMES:
        raise ValueError(f"INVALID_ARTIFACT_FILENAME: unsupported artifact filename {value!r}")
    return value


# Validate an artifact path against the small allowlist of run-local artifacts.
def validate_artifact_path(artifact_path) -> str:
    value = str(artifact_path or "").strip()
    if not value:
        raise ValueError("INVALID_ARTIFACT_PATH: artifact path is required")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError("INVALID_ARTIFACT_PATH: artifact path must stay inside the run directory")
    if value not in ALLOWED_ARTIFACT_PATHS:
        raise ValueError(f"INVALID_ARTIFACT_PATH: unsupported artifact path {value!r}")
    return value

# Resolve the output root directory, using the provided argument, environment variable, or default path.
def resolve_output_root(output_root=None) -> Path:
    if output_root is not None:
        return Path(output_root).expanduser().resolve()

    env_output_root = os.environ.get("COMQUTOR_OUTPUT_DIR")
    if env_output_root:
        return Path(env_output_root).expanduser().resolve()

    return (Path.cwd() / "outputs" / "runs").resolve()

# Get the run directory for a given run_id, ensuring it is within the output root.
def run_dir_for(run_id, output_root="outputs/runs"):
    safe_run_id = validate_run_id_for_path(run_id)
    root = resolve_output_root(output_root)
    run_dir = (root / safe_run_id).resolve()
    try:
        run_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("INVALID_RUN_DIR: resolved run directory escapes output_root") from exc
    return run_dir


# Resolve a safe artifact path for a run, ensuring the final path stays under that run directory.
def artifact_path_for(run_id, artifact_path, output_root="outputs/runs"):
    run_dir = run_dir_for(run_id, output_root)
    safe_artifact_path = validate_artifact_path(artifact_path)
    path = (run_dir / safe_artifact_path).resolve()
    try:
        path.relative_to(run_dir)
    except ValueError as exc:
        raise ValueError("INVALID_ARTIFACT_PATH: resolved artifact escapes run directory") from exc
    return path

# Atomically write text to a file, ensuring the parent directory exists and using a temporary file for safety.
def atomic_write_text(path, text, encoding="utf-8") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        tmp_path.write_text(text, encoding=encoding)
        with contextlib.suppress(AttributeError, NotImplementedError, OSError):
            os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
        with contextlib.suppress(AttributeError, NotImplementedError, OSError):
            os.chmod(path, 0o600)
        return path
    finally:
        if tmp_path.exists():
            with contextlib.suppress(OSError):
                tmp_path.unlink()

# Save a JSON record to the run directory, ensuring atomic write and proper encoding.
def save_json_record(run_id, filename, data, output_root="outputs/runs"):
    run_dir = run_dir_for(run_id, output_root)
    filename = validate_artifact_filename(filename)
    return atomic_write_text(
        run_dir / filename,
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

# Load a JSON record from the run directory, raising an error if it does not exist.
def load_json_record(run_id, filename, output_root="outputs/runs"):
    path = run_dir_for(run_id, output_root) / validate_artifact_filename(filename)
    with path.open(encoding="utf-8") as f:
        return json.load(f)

# Load a JSON record from the run directory if it exists, returning an empty dict if not.
def load_json_record_if_exists(run_id, filename, output_root="outputs/runs"):
    path = run_dir_for(run_id, output_root) / validate_artifact_filename(filename)
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


# Atomically append a JSONL record to an allowlisted run-local artifact.
def append_jsonl_record(run_id, artifact_path, data, output_root="outputs/runs"):
    path = artifact_path_for(run_id, artifact_path, output_root)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    line = json.dumps(data, ensure_ascii=False, default=str) + "\n"
    return atomic_write_text(path, existing + line, encoding="utf-8")

# List all valid run_ids in the output root directory, ignoring invalid directories.
def list_runs(output_root="outputs/runs"):
    root = resolve_output_root(output_root)
    if not root.exists():
        return []
    run_ids = []
    for path in root.iterdir():
        if not path.is_dir():
            continue
        try:
            run_ids.append(validate_run_id_for_path(path.name))
        except ValueError:
            continue
    return sorted(run_ids)
