"""Run environment record (2026-10-08, T4): what a new run actually ran on.

``build_run_environment`` returns one block written into a new run's
``metadata.json``: the database backend and name, the process's code
identity, the execution type (John's three: Fresh Run, frozen-input
recompute, old-result re-evaluation) and the effective configuration of the
research agents and the Week 2 semantic gateway. Never a credential, a DSN
or an API key. A value that cannot be determined is recorded as unknown with
a reason; historical runs, which have no such block, are never backfilled.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "comqutor.run_environment.v1"

EXECUTION_TYPE_FRESH_RUN = "fresh_run"
EXECUTION_TYPE_FROZEN_INPUT_RECOMPUTE = "frozen_input_recompute"
EXECUTION_TYPE_OLD_RESULT_REEVALUATION = "old_result_reevaluation"
EXECUTION_TYPES = frozenset({EXECUTION_TYPE_FRESH_RUN, EXECUTION_TYPE_FROZEN_INPUT_RECOMPUTE, EXECUTION_TYPE_OLD_RESULT_REEVALUATION})

_REPO_ROOT = Path(__file__).resolve().parents[1]
_RUNTIME_SOURCE_ROOTS = ("comqutor_alpha", "tradingagents")
_identity_lock = threading.Lock()
_identity_cache: dict[str, Any] | None = None


def _git(*args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=_REPO_ROOT, capture_output=True, text=True, check=True, timeout=60)
    return completed.stdout


def process_code_identity() -> dict[str, Any]:
    """Git HEAD, sha256 of the complete tracked diff against HEAD and of the
    untracked runtime source files, computed once per process (the code a
    process runs is the code it loaded). ``status: unknown`` when git is not
    available -- never a guessed version."""
    global _identity_cache
    with _identity_lock:
        if _identity_cache is not None:
            return dict(_identity_cache)
        try:
            head = _git("rev-parse", "HEAD").strip()
            tracked_diff = _git("diff", "HEAD", "--binary")
            untracked = sorted(
                p for p in _git("ls-files", "--others", "--exclude-standard", "--", *_RUNTIME_SOURCE_ROOTS).splitlines()
                if p and "__pycache__" not in p
            )
            listing = "".join(f"{p}\0{hashlib.sha256((_REPO_ROOT / p).read_bytes()).hexdigest()}\n" for p in untracked if (_REPO_ROOT / p).is_file())
            identity: dict[str, Any] = {
                "status": "known",
                "git_head": head,
                "uncommitted_changes": bool(tracked_diff) or bool(untracked),
                "tracked_diff_sha256": hashlib.sha256(tracked_diff.encode("utf-8")).hexdigest(),
                "untracked_runtime_source_files": len(untracked),
                "untracked_runtime_source_sha256": hashlib.sha256(listing.encode("utf-8")).hexdigest(),
            }
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            identity = {"status": "unknown", "reason": type(exc).__name__}
        identity["computed_at"] = datetime.now(UTC).isoformat()
        _identity_cache = identity
        return dict(identity)


def database_backend(output_root: Any = None) -> dict[str, Any]:
    from comqutor_alpha.storage.db.engine import DatabaseConfigurationError, describe_database, resolve_database_url

    try:
        return {"status": "known", **describe_database(resolve_database_url(output_root))}
    except DatabaseConfigurationError as exc:
        return {"status": "unavailable", "reason": exc.reason_code, "dialect": None, "database": None}


def research_agent_effective_config() -> dict[str, Any]:
    out: dict[str, Any] = {
        "max_actual_requests": os.environ.get("COMQUTOR_RESEARCH_AGENT_MAX_ACTUAL_REQUESTS") or None,
        "max_retries": os.environ.get("COMQUTOR_RESEARCH_AGENT_MAX_RETRIES") or None,
    }
    try:
        from comqutor_alpha.research_profiles import get_active_research_profile

        profile = get_active_research_profile()
        out.update({"profile_id": profile.profile_id, "provider": profile.llm_provider, "quick_model": profile.quick_think_llm,
                    "deep_model": profile.deep_think_llm, "thinking": profile.deepseek_thinking,
                    "max_debate_rounds": profile.max_debate_rounds, "max_risk_discuss_rounds": profile.max_risk_discuss_rounds})
    except Exception as exc:
        out["profile_status"] = f"unavailable: {type(exc).__name__}"
    return out


def run_environment_or_unavailable(execution_type: str, output_root: Any = None) -> dict[str, Any]:
    """``build_run_environment`` for a metadata writer: recording the
    environment must never fail the run itself, so an unexpected error is
    recorded as such instead."""
    try:
        return build_run_environment(execution_type, output_root)
    except Exception as exc:
        return {"schema_version": SCHEMA_VERSION, "execution_type": execution_type, "status": "unavailable", "reason": type(exc).__name__}


def build_run_environment(execution_type: str, output_root: Any = None) -> dict[str, Any]:
    if execution_type not in EXECUTION_TYPES:
        raise ValueError(f"unknown execution_type: {execution_type}")
    from comqutor_alpha.structure_engine.week2_llm import describe_server_week2_effective_config

    return {
        "schema_version": SCHEMA_VERSION,
        "recorded_at": datetime.now(UTC).isoformat(),
        "execution_type": execution_type,
        "database": database_backend(output_root),
        "code_identity": process_code_identity(),
        "effective_config": {
            "research_agents": research_agent_effective_config(),
            "week2_semantic": describe_server_week2_effective_config(),
        },
    }


__all__ = [
    "EXECUTION_TYPES",
    "EXECUTION_TYPE_FRESH_RUN",
    "EXECUTION_TYPE_FROZEN_INPUT_RECOMPUTE",
    "EXECUTION_TYPE_OLD_RESULT_REEVALUATION",
    "SCHEMA_VERSION",
    "build_run_environment",
    "database_backend",
    "process_code_identity",
    "research_agent_effective_config",
    "run_environment_or_unavailable",
]
