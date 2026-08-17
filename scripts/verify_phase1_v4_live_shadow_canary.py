#!/usr/bin/env python3
"""Provider-zero verifier for the completed Phase 1 v4 live Canary."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.api.routes_research import build_research_response  # noqa: E402
from comqutor_alpha.llm_runtime.manifest import verify_semantic_manifest  # noqa: E402
from comqutor_alpha.structure_engine.structured_output_live_shadow import (  # noqa: E402
    verify_live_shadow_exact_replay,
)
from scripts.run_phase1_v4_live_shadow_canary import (  # noqa: E402
    CONTRACT_PATH,
    RESULT_PATH,
    _authoritative_snapshot,
    _sha256_file,
    _without_times,
)

STATE_DIR = REPO_ROOT / "docs/audit_artifacts/phase1_master"
STATE_PATH = STATE_DIR / "phase1_master_state.json"
LEDGER_PATH = STATE_DIR / "provider_call_ledger.json"
GLOBAL_LEDGER_PATH = STATE_DIR / "phase1_global_provider_call_ledger.jsonl"
SECRET_PATTERNS = (
    re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)authorization\s*[:=]\s*bearer\s+\S+"),
    re.compile(r'(?i)"(?:api[_-]?key|password|secret)"\s*:\s*"(?!\[REDACTED\])[^"\s]{6,}"'),
    re.compile(r"(?i)(?:chain[_-]?of[_-]?thought|hidden[_-]?reasoning|<thinking>)"),
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _global_events() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in GLOBAL_LEDGER_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _response_diff(left: Any, right: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(left, dict) and isinstance(right, dict):
        result: dict[str, Any] = {}
        for key in sorted(set(left) | set(right)):
            path = f"{prefix}.{key}" if prefix else key
            result.update(_response_diff(left.get(key), right.get(key), path))
        return result
    if left != right:
        return {prefix: {"legacy": left, "shadow": right}}
    return {}


def _secret_scan(paths: list[Path]) -> tuple[bool, str]:
    violations: list[str] = []
    for path in paths:
        if not path.is_file() or path.suffix not in {".json", ".jsonl", ".md", ".csv"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            violations.append(str(path.relative_to(REPO_ROOT)))
    return not violations, "clean" if not violations else f"violations={violations}"


def main() -> int:
    contract = _load(CONTRACT_PATH)
    result = _load(RESULT_PATH)
    state = _load(STATE_PATH)
    ledger = _load(LEDGER_PATH)
    artifact_root = REPO_ROOT / str(contract["artifact_root"])
    run_id = str(contract["canary_run_id"])
    legacy_root = artifact_root / "legacy"
    shadow_root = artifact_root / "shadow"
    shadow_run_dir = shadow_root / run_id
    runtime_dir = shadow_run_dir / "structured_adapter_shadow_runtime"

    replay = verify_live_shadow_exact_replay(shadow_run_dir)
    manifest = verify_semantic_manifest(runtime_dir / "llm_semantic_manifest.json")
    legacy_snapshot = _authoritative_snapshot(legacy_root / run_id)
    shadow_snapshot = _authoritative_snapshot(shadow_run_dir)
    legacy_response = _without_times(build_research_response(run_id, output_root=legacy_root))
    shadow_response = _without_times(build_research_response(run_id, output_root=shadow_root))
    response_diff = _response_diff(legacy_response, shadow_response)

    canary_events = [
        item
        for item in _global_events()
        if item.get("stage") == "LIVE_SHADOW_CANARY"
        and item.get("event_id", "").startswith(
            f"phase1_master:live_shadow_canary:{contract['canary_id']}:"
        )
    ]
    slot_results = result.get("per_slot_results") or []
    source_path = REPO_ROOT / str(contract["source_artifact"])
    scan_paths = [
        CONTRACT_PATH,
RESULT_PATH,
        STATE_DIR / "phase1_v4_live_shadow_canary_report.json",
        STATE_DIR / "phase1_v4_live_shadow_canary_report.md",
        STATE_PATH,
        STATE_DIR / "phase1_v4_live_shadow_canary_pre_provider_incident.json",
        *artifact_root.rglob("*"),
    ]
    secret_ok, secret_detail = _secret_scan(scan_paths)

    checks: list[tuple[str, Callable[[], tuple[bool, str]]]] = [
        (
            "execution_contract_fixed",
            lambda: (
                len(contract.get("slots") or []) == 4
                and contract.get("logical_call_cap") == 4
                and contract.get("provider_attempt_cap") == 4
                and contract.get("retry_count") == 0,
                "4 fixed slots; 4/4 caps; zero retry",
            ),
        ),
        (
            "canary_outcome_honest",
            lambda: (
                result.get("status") == "FAIL"
                and result.get("slots_accepted") == 3
                and result.get("slots_passed") == 0,
                f"status={result.get('status')} accepted={result.get('slots_accepted')} strict_passed={result.get('slots_passed')}",
            ),
        ),
        (
            "provider_budget_exact",
            lambda: (
                result.get("logical_calls_used") == 4
                and result.get("provider_attempts_used") == 4
                and result.get("retries_used") == 0
                and len(slot_results) == 4,
                "logical=4 attempts=4 retries=0",
            ),
        ),
        (
            "provider_identity_stable",
            lambda: (
                result.get("provider") == "anthropic"
                and result.get("model") == "claude-sonnet-4-6"
                and all(item.get("provider_attempt_count") == 1 for item in slot_results)
                and all(item.get("retry_count") == 0 for item in slot_results),
                "anthropic/claude-sonnet-4-6; one attempt per slot",
            ),
        ),
        (
            "technical_rejection_reproduced",
            lambda: (
                slot_results[3].get("family") == "technical"
                and slot_results[3].get("sidecar_accepted") is False
                and "SHADOW_SOURCE_SPAN_INVALID"
                in (slot_results[3].get("sidecar_reason_codes") or [])
                and (slot_results[3].get("evidence_resolution") or {}).get(
                    "ambiguous_multiple_match"
                )
                == 1,
                "technical rejected; one ambiguous exact match; fail closed",
            ),
        ),
        (
            "accepted_provenance_clean",
            lambda: (
                all(item.get("provenance") == "PASS" for item in slot_results[:3])
                and sum(int(item.get("claim_count") or 0) for item in slot_results[:3]) == 57,
                "3 accepted slots; 57 claims; no unresolved/fabricated evidence admitted",
            ),
        ),
        (
            "authoritative_downstream_equal",
            lambda: (
                legacy_snapshot == shadow_snapshot
                and result.get("shadow_output_reached_authoritative_downstream") is False,
                "Claims/Mapper/Extractor/Graph/Activation/Conflict equal; no Shadow IDs downstream",
            ),
        ),
        (
            "production_response_change_detected",
            lambda: (
                response_diff
                == {
                    "artifacts.week2_llm_error_logs": {
                        "legacy": False,
                        "shadow": True,
                    }
                },
                f"diff={response_diff}",
            ),
        ),
        (
            "exact_replay_provider_zero",
            lambda: (
                replay.get("status") == "PASS"
                and replay.get("accepted_report_count") == 3
                and replay.get("provider_calls") == 0,
                f"status={replay.get('status')} accepted={replay.get('accepted_report_count')} provider_calls={replay.get('provider_calls')}",
            ),
        ),
        (
            "semantic_manifest_valid",
            lambda: (
                manifest.valid,
                "valid" if manifest.valid else f"issues={manifest.issues}",
            ),
        ),
        (
            "master_and_global_ledgers_exact",
            lambda: (
                state.get("cumulative_logical_calls") == 95
                and state.get("cumulative_provider_attempts") == 102
                and ledger.get("cumulative_logical_calls") == 95
                and ledger.get("cumulative_provider_attempts") == 102
                and len(canary_events) == 4
                and len({item.get("event_id") for item in canary_events}) == 4,
                "state/ledger=95/102; four unique Canary events",
            ),
        ),
        (
            "production_authority_legacy",
            lambda: (
                state.get("production_authority") == "LEGACY_ADAPTER"
                and (state.get("live_shadow_canary_progress") or {}).get(
                    "ready_for_production_cutover"
                )
                is False,
                "LEGACY_ADAPTER; cutover not ready",
            ),
        ),
        (
            "source_artifact_unchanged",
            lambda: (
                result.get("source_artifact_unchanged") is True
                and _sha256_file(source_path)
                == _sha256_file(
                    REPO_ROOT
                    / "outputs/runs/0e044e37-862c-43be-871c-31012cd660e7/"
                    "raw_agent_outputs.json"
                ),
                "historical raw source unchanged",
            ),
        ),
        ("secret_and_hidden_reasoning_scan", lambda: (secret_ok, secret_detail)),
    ]

    failed = 0
    for name, check in checks:
        ok, detail = check()
        failed += int(not ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    print(f"TOTAL={len(checks)} PASS={len(checks) - failed} FAIL={failed}")
    print("PHASE1_V4_LIVE_SHADOW_CANARY_VERIFIER: " + ("PASS" if failed == 0 else "FAIL"))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
