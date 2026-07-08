"""File-backed persistence helpers for local COMQUTOR validation."""

from __future__ import annotations

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
    "final_report.md",
    "research_response.json",
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

# Atomically write text to a file, ensuring the parent directory exists and using a temporary file for safety.
def atomic_write_text(path, text, encoding="utf-8") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        tmp_path.write_text(text, encoding=encoding)
        try:
            os.chmod(tmp_path, 0o600)
        except (AttributeError, NotImplementedError, OSError):
            pass
        os.replace(tmp_path, path)
        try:
            os.chmod(path, 0o600)
        except (AttributeError, NotImplementedError, OSError):
            pass
        return path
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

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
