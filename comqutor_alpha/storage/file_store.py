"""File-backed persistence for local COMQUTOR validation."""

from __future__ import annotations

import json
from pathlib import Path


def run_dir_for(run_id, output_root="outputs/runs"):
    return Path(output_root) / str(run_id)


def save_json_record(run_id, filename, data, output_root="outputs/runs"):
    run_dir = run_dir_for(run_id, output_root)
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / filename
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_json_record(run_id, filename, output_root="outputs/runs"):
    path = run_dir_for(run_id, output_root) / filename
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def list_runs(output_root="outputs/runs"):
    root = Path(output_root)
    if not root.exists():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir())

