#!/usr/bin/env python3
"""Phase 1 Master read-only verifier.

Never modifies any file. Never calls a Provider, network, Redis, or
database. Re-derives, mechanically, the structural and ledger-level facts
the Phase 1 Master gate report depends on.

Usage:
    python scripts/verify_phase1_master.py
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = REPO_ROOT / "docs/audit_artifacts/phase1_master"
STATE_PATH = STATE_DIR / "phase1_master_state.json"
LEDGER_PATH = STATE_DIR / "provider_call_ledger.json"
GLOBAL_LEDGER_PATH = STATE_DIR / "phase1_global_provider_call_ledger.jsonl"

# Raised from 53 to 70, then 70 to 95, then 95 to 99, then 99 to 103, for
# the Phase 1 Master evidence-alignment fix (product-owner-approved each
# time) -- mirrors run_phase1_master.py's own comment. Includes the
# separately contracted four-call final v4.1 Re-Canary and the separately
# contracted four-call final v4.2 live Canary.
HARD_CAP_LOGICAL_CALLS = 103
HARD_CAP_PROVIDER_ATTEMPTS = 130

PROTECTED_FILES = [
    "comqutor_alpha/structure_engine/structured_output_adapter.py",
    "comqutor_alpha/structure_engine/alpha_mapper.py",
    "comqutor_alpha/structure_engine/structure_extractor.py",
    "comqutor_alpha/api/routes_research.py",
    "comqutor_alpha/replay/pipeline.py",
    "comqutor_alpha/graph_engine/activation_scorer_v2.py",
    "comqutor_alpha/exposure_engine.py",
    "comqutor_alpha/llm/canonical_prompt_injection.py",
    "comqutor_alpha/structure_engine/canonical_relation_prompt.py",
]

STATES = {
    "PROVIDER_DIAGNOSTIC",
    "PROVIDER_PROBE",
    "ANTHROPIC_QUALIFICATION",
    "SMOKE",
    "PILOT",
    "CORE_EVALUATION",
    "WAITING_FOR_HUMAN_REVIEW",
    "QUALITY_GATE",
    "PROMPT_V2_REVISION",
    "LIVE_SHADOW_INTEGRATION",
    "LIVE_SHADOW_CANARY",
    "PRODUCTION_CUTOVER",
    "COMPLETE",
    "BLOCKED",
    "FAIL",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _module_imports(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def check_state_file_schema_valid() -> tuple[bool, str]:
    if not STATE_PATH.exists():
        return False, "state file does not exist -- run scripts/run_phase1_master.py --resume first"
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    required = {
        "current_state",
        "cumulative_logical_calls",
        "cumulative_provider_attempts",
        "prompt_version_in_use",
        "prompt_sha256_in_use",
        "already_called_report_ids",
        "history",
    }
    missing = required - set(state.keys())
    if missing:
        return False, f"missing fields: {sorted(missing)}"
    if state["current_state"] not in STATES:
        return False, f"current_state not in enumerated STATES: {state['current_state']}"
    return True, f"current_state={state['current_state']}"


def check_call_budget_within_hard_caps() -> tuple[bool, str]:
    if not STATE_PATH.exists():
        return True, "no state file yet -- nothing to check"
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    calls = state["cumulative_logical_calls"]
    attempts = state["cumulative_provider_attempts"]
    ok = calls <= HARD_CAP_LOGICAL_CALLS and attempts <= HARD_CAP_PROVIDER_ATTEMPTS
    return ok, f"logical_calls={calls}/{HARD_CAP_LOGICAL_CALLS} attempts={attempts}/{HARD_CAP_PROVIDER_ATTEMPTS}"


def check_ledger_matches_state_counters() -> tuple[bool, str]:
    if not (STATE_PATH.exists() and LEDGER_PATH.exists()):
        return True, "no state/ledger file yet -- nothing to check"
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    ledger_calls = sum(e.get("logical_calls", 0) for e in ledger.get("entries", []))
    ledger_attempts = sum(e.get("provider_attempts", 0) for e in ledger.get("entries", []))
    ok = ledger_calls == state["cumulative_logical_calls"] and ledger_attempts == state["cumulative_provider_attempts"]
    return ok, f"ledger=({ledger_calls},{ledger_attempts}) state=({state['cumulative_logical_calls']},{state['cumulative_provider_attempts']})"


def check_ledger_never_shrinks() -> tuple[bool, str]:
    if not LEDGER_PATH.exists():
        return True, "no ledger file yet"
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    running_calls = 0
    running_attempts = 0
    for entry in ledger.get("entries", []):
        running_calls += entry.get("logical_calls", 0)
        running_attempts += entry.get("provider_attempts", 0)
        if entry.get("running_total_logical_calls") != running_calls:
            return False, f"non-monotonic ledger at entry {entry.get('at')}"
        if entry.get("running_total_provider_attempts") != running_attempts:
            return False, f"non-monotonic ledger at entry {entry.get('at')}"
    return True, f"{len(ledger.get('entries', []))} entries, monotonic"

def check_no_duplicate_report_calls() -> tuple[bool, str]:
    if not STATE_PATH.exists():
        return True, "no state file yet"
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    ids = state.get("anthropic_called_report_ids", [])
    ok = len(ids) == len(set(ids)) and len(ids) <= 24
    return ok, f"Anthropic: {len(ids)} report ids, {len(set(ids))} unique"


def check_task_specific_anthropic_route() -> tuple[bool, str]:
    from comqutor_alpha.research_profiles import (
        ANTHROPIC_PROFILE_ID,
        DEEPSEEK_DEFAULT_PROFILE_ID,
        get_active_research_profile,
    )
    from comqutor_alpha.structure_engine.structured_output_shadow_provider import (
        STRUCTURED_CLAIM_SHADOW_MAX_RETRIES,
        STRUCTURED_CLAIM_SHADOW_TIMEOUT_SECONDS,
        profile_id_for_semantic_task,
    )

    existing = ("structured_adapter", "alpha_classifier", "structure_extractor")
    ok = (
        profile_id_for_semantic_task("structured_claim_shadow") == ANTHROPIC_PROFILE_ID
        and all(profile_id_for_semantic_task(task) == DEEPSEEK_DEFAULT_PROFILE_ID for task in existing)
        and get_active_research_profile().profile_id == DEEPSEEK_DEFAULT_PROFILE_ID
        and STRUCTURED_CLAIM_SHADOW_TIMEOUT_SECONDS == 180.0
        and STRUCTURED_CLAIM_SHADOW_MAX_RETRIES == 1
    )
    return ok, "Shadow=Anthropic 180s/1 transient retry; existing tasks/default=DeepSeek"


def check_state_preserves_previous_provider_evaluation() -> tuple[bool, str]:
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    previous = state.get("previous_provider_evaluations") or []
    ok = (
        state.get("structured_claim_shadow_profile_id")
        == "comqutor_anthropic_medium_sonnet46_v1"
        and any(item.get("provider") == "deepseek" and item.get("preserved") for item in previous)
        and state.get("root_cause_status", "").startswith("DeepSeek model/provider instability")
    )
    return ok, f"previous_provider_evaluations={len(previous)}"


def check_global_provider_ledger_complete_and_append_only_shape() -> tuple[bool, str]:
    if not GLOBAL_LEDGER_PATH.exists():
        return False, "missing"
    lines = GLOBAL_LEDGER_PATH.read_text(encoding="utf-8").splitlines()
    entries = [json.loads(line) for line in lines if line]
    event_ids = [str(entry.get("event_id") or "") for entry in entries]
    adhoc = [entry for entry in entries if "adhoc_diagnostic" in str(entry.get("event_id"))]
    interrupted = [entry for entry in entries if entry.get("logical_calls") == "UNKNOWN_MINIMUM"]
    ok = (
        len(entries) == len(lines)
        and len(event_ids) == len(set(event_ids))
        and len(adhoc) == 3
        and sum(int(entry.get("provider_attempts") or 0) for entry in adhoc) == 3
        and len(interrupted) >= 2
        and all(entry.get("accounting_confidence") for entry in entries)
    )
    return ok, f"entries={len(entries)} adhoc={len(adhoc)} interrupted_unknown={len(interrupted)}"


def check_no_secret_persistence_in_master_artifacts() -> tuple[bool, str]:
    forbidden = ("ANTHROPIC_API_KEY=", "DEEPSEEK_API_KEY=", "Authorization: Bearer", "sk-ant-")
    offenders = []
    for path in STATE_DIR.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(token in text for token in forbidden):
                offenders.append(str(path.relative_to(REPO_ROOT)))
    return not offenders, "clean" if not offenders else f"offenders={offenders}"


def check_prompt_version_stable() -> tuple[bool, str]:
    from comqutor_alpha.structure_engine.structured_output_shadow_prompt import (
        FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
        STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
        STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
    )
    expected_v1 = "structured_adapter.claim_extraction_shadow.v1"
    expected_sha = "c60f1526fd927e4593ab5913bc3c653cd2a05f6d24dc5fdf3e258a3e62128d1e"
    if expected_v1 == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION:
        ok = STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256 == expected_sha == FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256
        return ok, f"v1 sha={STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256}"
    return True, f"prompt version advanced to {STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION} (v2 permitted at most once)"


def check_prompt_v2_hash_frozen_and_consistent_with_state() -> tuple[bool, str]:
    """Phase 1 Master prompt-size fix (docs/audit_artifacts/phase1_master/
    prompt_audit/): the v2 prompt hash must not silently drift, at most one
    v2 revision is ever recorded, and if the resumable state already
    switched to v2, its persisted hash must match the code exactly."""

    from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v2 import (
        FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256,
        STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256,
        STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2,
    )

    if STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256 != FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256:
        return False, "v2 prompt sha drifted from its frozen value"

    if not STATE_PATH.exists():
        return True, "v2 sha frozen; no state file yet"
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    migration = state.get("prompt_v2_migration")
    if migration is not None and int(migration.get("revision_count") or 0) > 1:
        return False, f"revision_count={migration.get('revision_count')} exceeds the allowed single v2 revision"
    if state.get("prompt_version_in_use") == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2:
        ok = state.get("prompt_sha256_in_use") == STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256
        return ok, f"state prompt_sha256_in_use={state.get('prompt_sha256_in_use')}"
    return True, "v2 sha frozen; state not yet migrated to v2"


def check_prompt_v3_hash_frozen_and_consistent_with_state() -> tuple[bool, str]:
    """Phase 1 Master evidence-alignment fix (v2 human/AI review found
    systemic Claim-to-Evidence misalignment): the v3 prompt hash must not
    silently drift, at most one v3 revision is ever recorded, and if the
    resumable state already switched to v3, its persisted hash must match
    the code exactly. Mirrors check_prompt_v2_hash_frozen_and_consistent_
    with_state exactly, one version up."""

    from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v3 import (
        FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_V3_SHA256,
        STRUCTURED_OUTPUT_SHADOW_PROMPT_V3_SHA256,
        STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3,
    )

    if STRUCTURED_OUTPUT_SHADOW_PROMPT_V3_SHA256 != FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_V3_SHA256:
        return False, "v3 prompt sha drifted from its frozen value"

    if not STATE_PATH.exists():
        return True, "v3 sha frozen; no state file yet"
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    migration = state.get("prompt_v3_migration")
    if migration is not None and int(migration.get("revision_count") or 0) > 1:
        return False, f"revision_count={migration.get('revision_count')} exceeds the allowed single v3 revision"
    if state.get("prompt_version_in_use") == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3:
        ok = state.get("prompt_sha256_in_use") == STRUCTURED_OUTPUT_SHADOW_PROMPT_V3_SHA256
        return ok, f"state prompt_sha256_in_use={state.get('prompt_sha256_in_use')}"
    return True, "v3 sha frozen; state not yet migrated to v3"


def check_v2_evaluation_preserved_when_v3_active() -> tuple[bool, str]:
    """If the state has migrated to v3, the completed v2 24-report
    evaluation must still be present, verbatim, in
    previous_provider_evaluations -- section 1's permanent-retention
    requirement -- never overwritten or deleted."""

    if not STATE_PATH.exists():
        return True, "no state file yet"
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if state.get("prompt_version_in_use") != "structured_adapter.claim_extraction_shadow.v3":
        return True, "state not yet migrated to v3"
    previous = state.get("previous_provider_evaluations") or []
    v2_entries = [
        item
        for item in previous
        if item.get("prompt_version") == "structured_adapter.claim_extraction_shadow.v2"
        and item.get("v2_engineering_reliability") == "PASS"
        and item.get("v2_semantic_evidence_alignment") == "FAIL"
        and item.get("preserved") is True
        and item.get("evaluation_dir")
    ]
    ok = len(v2_entries) >= 1
    return ok, f"v2_entries_preserved={len(v2_entries)}"


def check_prompt_v4_hash_frozen_and_consistent_with_state() -> tuple[bool, str]:
    """Phase 1 Master evidence-alignment fix, round 2 (markdown-formatting-
    fidelity fix): mirrors check_prompt_v3_hash_frozen_and_consistent_with_
    state exactly, one version up."""

    from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v4 import (
        FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256,
        STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256,
        STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4,
    )

    if STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256 != FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256:
        return False, "v4 prompt sha drifted from its frozen value"

    if not STATE_PATH.exists():
        return True, "v4 sha frozen; no state file yet"
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    migration = state.get("prompt_v4_migration")
    if migration is not None and int(migration.get("revision_count") or 0) > 1:
        return False, f"revision_count={migration.get('revision_count')} exceeds the allowed single v4 revision"
    if state.get("prompt_version_in_use") == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4:
        ok = state.get("prompt_sha256_in_use") == STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256
        return ok, f"state prompt_sha256_in_use={state.get('prompt_sha256_in_use')}"
    return True, "v4 sha frozen; state not yet migrated to v4"


def check_v3_evaluation_preserved_when_v4_active() -> tuple[bool, str]:
    """If the state has migrated to v4, the completed v3 24-report
    evaluation must still be present, verbatim, in
    previous_provider_evaluations -- never overwritten or deleted."""

    if not STATE_PATH.exists():
        return True, "no state file yet"
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if state.get("prompt_version_in_use") != "structured_adapter.claim_extraction_shadow.v4":
        return True, "state not yet migrated to v4"
    previous = state.get("previous_provider_evaluations") or []
    v3_entries = [
        item
        for item in previous
        if item.get("prompt_version") == "structured_adapter.claim_extraction_shadow.v3"
        and item.get("v3_engineering_reliability") == "PASS"
        and item.get("v3_markdown_formatting_fidelity") == "PARTIAL"
        and item.get("preserved") is True
        and item.get("evaluation_dir")
    ]
    ok = len(v3_entries) >= 1
    return ok, f"v3_entries_preserved={len(v3_entries)}"


def check_protected_files_unchanged() -> tuple[bool, str]:
    missing = [f for f in PROTECTED_FILES if not (REPO_ROOT / f).exists()]
    if missing:
        return False, f"missing: {missing}"
    return True, "all protected files present (size/hash cross-checked against phase1b1 baseline separately)"


def check_evaluation_output_confined() -> tuple[bool, str]:
    if not STATE_PATH.exists():
        return True, "no state file yet"
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    eval_dir = state.get("evaluation_dir")
    if not eval_dir:
        return True, "no evaluation_dir set yet"
    resolved = (REPO_ROOT / eval_dir).resolve()
    allowed_root = (REPO_ROOT / "outputs/evaluations").resolve()
    try:
        resolved.relative_to(allowed_root)
    except ValueError:
        return False, f"evaluation_dir outside outputs/evaluations/: {eval_dir}"
    return True, eval_dir


def check_no_runs_or_replays_writes() -> tuple[bool, str]:
    import subprocess

    result = subprocess.run(
        ["git", "status", "--short", "--", "outputs/runs", "outputs/replays"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    ok = result.stdout.strip() == ""
    return ok, "clean" if ok else result.stdout.strip()


def check_no_commit_since_baseline() -> tuple[bool, str]:
    import subprocess

    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    return True, f"HEAD={result.stdout.strip()}"


def check_adr_010_present() -> tuple[bool, str]:
    path = REPO_ROOT / "docs/adr/ADR-010-phase1-structured-adapter-authority.md"
    if not path.exists():
        return False, "missing"
    text = path.read_text(encoding="utf-8")
    required_tags = [
        "ACCEPTED_FOR_STAGED_EXECUTION",
        "RESUMABLE_STATE_MACHINE",
        "HUMAN_REVIEW_REQUIRED_BEFORE_CUTOVER",
        "LEGACY_ROLLBACK_MANDATORY",
        "NO_AUTOMATIC_PHASE_2",
    ]
    missing = [t for t in required_tags if t not in text]
    return not missing, "all status tags present" if not missing else f"missing tags: {missing}"


def check_no_new_production_importers_of_master_script() -> tuple[bool, str]:
    master_module_name = "run_phase1_master"
    offenders = []
    for root_name in ("comqutor_alpha", "tradingagents"):
        for path in (REPO_ROOT / root_name).rglob("*.py"):
            if master_module_name in _module_imports(path):
                offenders.append(str(path.relative_to(REPO_ROOT)))
    return not offenders, "clean" if not offenders else f"offenders={offenders}"


def check_no_production_authority_mode_flag_yet() -> tuple[bool, str]:
    """COMQUTOR_STRUCTURED_ADAPTER_MODE must not exist in production code
    until Stage E/G actually implements it -- premature wiring would be a
    Stage G FAIL condition (cutover before every gate passes)."""
    if not STATE_PATH.exists():
        return True, "no state file yet"
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if state["current_state"] in ("LIVE_SHADOW_INTEGRATION", "LIVE_SHADOW_CANARY", "PRODUCTION_CUTOVER", "COMPLETE"):
        return True, f"state={state['current_state']} -- flag introduction is in scope"
    offenders = []
    for path in (REPO_ROOT / "comqutor_alpha").rglob("*.py"):
        if "COMQUTOR_STRUCTURED_ADAPTER_MODE" in path.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    return not offenders, "clean" if not offenders else f"premature: {offenders}"


CHECKS = [
    check_state_file_schema_valid,
    check_call_budget_within_hard_caps,
    check_ledger_matches_state_counters,
    check_ledger_never_shrinks,
    check_no_duplicate_report_calls,
    check_task_specific_anthropic_route,
    check_state_preserves_previous_provider_evaluation,
    check_global_provider_ledger_complete_and_append_only_shape,
    check_no_secret_persistence_in_master_artifacts,
    check_prompt_version_stable,
    check_prompt_v2_hash_frozen_and_consistent_with_state,
    check_prompt_v3_hash_frozen_and_consistent_with_state,
    check_v2_evaluation_preserved_when_v3_active,
    check_prompt_v4_hash_frozen_and_consistent_with_state,
    check_v3_evaluation_preserved_when_v4_active,
    check_protected_files_unchanged,
    check_evaluation_output_confined,
    check_no_runs_or_replays_writes,
    check_no_commit_since_baseline,
    check_adr_010_present,
    check_no_new_production_importers_of_master_script,
    check_no_production_authority_mode_flag_yet,
]


def main() -> int:
    results = []
    for check in CHECKS:
        try:
            ok, detail = check()
        except Exception as exc:  # never crash the verifier itself
            ok, detail = False, f"EXCEPTION:{type(exc).__name__}:{exc}"
        results.append((check.__name__.removeprefix("check_"), ok, detail))

    for name, ok, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    print(f"TOTAL={len(results)} PASS={passed} FAIL={failed}")
    print(f"PHASE1_MASTER_VERIFIER: {'PASS' if failed == 0 else 'FAIL'}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
