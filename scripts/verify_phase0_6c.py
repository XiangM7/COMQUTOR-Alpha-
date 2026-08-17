"""Read-only verifier for Phase 0.6C Exact Semantic Replay.

The repository and historical output trees are never written. The two small
failure probes use a system temporary directory and perform no Provider,
network, Redis, market-data, or database operation.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import os
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = REPO_ROOT / "docs/audit_artifacts/phase0_6c"
PROTECTED_BEFORE = PHASE_DIR / "protected_file_manifest_before.json"
DIRTY_BEFORE = PHASE_DIR / "preexisting_dirty_file_manifest.json"
SOURCE_BEFORE = PHASE_DIR / "source_artifact_integrity_before.json"
BEHAVIORAL = PHASE_DIR / "exact_replay_behavioral_comparison.json"
PROVIDER_EVIDENCE = PHASE_DIR / "exact_replay_provider_zero_evidence.json"

PASS = "PASS"
BLOCKED = "BLOCKED"
FAIL = "FAIL"


@dataclass(frozen=True)
class CheckResult:
    number: int
    name: str
    status: str
    detail: str


def result(
    number: int,
    name: str,
    condition: bool,
    detail: str,
    *,
    blocked: bool = False,
) -> CheckResult:
    status = PASS if condition else (BLOCKED if blocked else FAIL)
    return CheckResult(number, name, status, detail)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"object required: {path.name}")
    return payload


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_output(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def status_paths() -> set[str]:
    paths: set[str] = set()
    for line in git_output("status", "--porcelain=v1", "-uall").splitlines():
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.add(path)
    return paths


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def verify_records(records: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for record in records:
        relative = record["relative_path"]
        path = REPO_ROOT / relative
        if not path.is_file():
            errors.append(f"missing:{relative}")
            continue
        stat = path.stat()
        if stat.st_size != record["size_bytes"]:
            errors.append(f"size:{relative}")
        if sha256(path) != record["sha256"]:
            errors.append(f"sha256:{relative}")
        if stat.st_mtime_ns != record["mtime_ns"]:
            errors.append(f"mtime:{relative}")
    return errors


def protected_records(*categories: str) -> list[dict[str, Any]]:
    wanted = set(categories)
    return [
        item
        for item in load_json(PROTECTED_BEFORE).get("strict_files", [])
        if wanted.intersection(item.get("categories", []))
    ]


def current_tree(relative_root: str) -> list[dict[str, Any]]:
    root = REPO_ROOT / relative_root
    if not root.is_dir():
        return []
    records = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        stat = path.stat()
        records.append(
            {
                "relative_path": path.relative_to(REPO_ROOT).as_posix(),
                "size_bytes": stat.st_size,
                "sha256": sha256(path),
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    return records


def check_01_plan_sha() -> CheckResult:
    plan = REPO_ROOT / "docs/specs/COMQUTOR_Alpha_Development_Plan_v1.0.docx"
    manifest = load_json(REPO_ROOT / "docs/specs/development_plan_v1.0_manifest.json")
    digest = sha256(plan)
    ok = digest == manifest.get("source_sha256") == manifest.get("repository_sha256")
    return result(1, "development_plan_sha_unchanged", ok, f"sha256={digest}")


def check_02_prior_phases() -> CheckResult:
    records = protected_records(
        "phase0_6b_deliverable",
        "phase_audit_artifacts",
        "adr_001_through_006",
        "phase0_specification",
        "frozen_specs",
    )
    errors = verify_records(records)
    return result(2, "phase0_5_0_6a_0_6b_files_unchanged", not errors, f"records={len(records)}; errors={errors}")


def check_03_adr007() -> CheckResult:
    path = REPO_ROOT / "docs/adr/ADR-007-exact-semantic-replay-integration.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    required = {
        "ACCEPTED_FOR_IMPLEMENTATION",
        "PROVIDER_ZERO",
        "FAIL_CLOSED",
        "NO_LIVE_SEMANTIC_CHANGE",
        "SOURCE_FROZEN",
        "APPROVED_PROJECT_DECISION",
        "CURRENT_IMPLEMENTATION BEFORE 0.6C",
        "Current implementation after 0.6C",
    }
    missing = sorted(required - {token for token in required if token in text})
    return result(3, "adr007_status_and_provenance", path.is_file() and not missing, f"missing={missing}")


def check_04_contract() -> CheckResult:
    path = REPO_ROOT / "docs/specs/exact_semantic_replay_integration_contract_v1.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    required = {
        "EXACT_SEMANTIC_REPLAY",
        "RAW_REBUILD_DIAGNOSTIC",
        "Semantic binding algorithm",
        "Semantic authority, copy, and identity policy",
        "Provider-zero and side-effect guarantees",
        "Historical runs and backward compatibility",
        "Non-goals",
    }
    missing = sorted(token for token in required if token not in text)
    return result(4, "exact_replay_contract_exists", path.is_file() and not missing, f"missing={missing}")


def check_05_modes() -> CheckResult:
    from comqutor_alpha.replay.modes import ReplayMode

    actual = {item.value for item in ReplayMode}
    expected = {"EXACT_SEMANTIC_REPLAY", "RAW_REBUILD_DIAGNOSTIC"}
    return result(5, "two_explicit_replay_modes", actual == expected, f"modes={sorted(actual)}")


def check_06_raw_compatibility() -> CheckResult:
    from comqutor_alpha.replay.pipeline import ReplayResult, run_structure_replay

    parameters = inspect.signature(run_structure_replay).parameters
    required = {
        "source_run_id",
        "source_output_root",
        "replay_output_root",
        "replay_run_id",
        "persist",
        "comparison",
    }
    fields = ReplayResult.__dataclass_fields__
    ok = required.issubset(parameters) and {
        "replay_mode",
        "semantic_source",
        "provider_zero",
    }.issubset(fields)
    return result(6, "legacy_run_structure_replay_compatible", ok, f"parameters={list(parameters)}")


def exact_modules() -> tuple[Path, ...]:
    return tuple(
        REPO_ROOT / f"comqutor_alpha/replay/{name}.py"
        for name in ("exact_semantic", "source_bundle", "semantic_binding", "modes")
    )


def forbidden_import_check(number: int, name: str, roots: set[str]) -> CheckResult:
    violations = []
    for path in exact_modules():
        for module in imported_modules(path):
            if any(module == root or module.startswith(f"{root}.") for root in roots):
                violations.append(f"{path.name}:{module}")
    return result(number, name, not violations, f"violations={violations}")


def check_07_no_adapter() -> CheckResult:
    return forbidden_import_check(7, "exact_replay_does_not_import_adapter", {"comqutor_alpha.structure_engine.structured_output_adapter"})


def check_08_no_mapper() -> CheckResult:
    return forbidden_import_check(8, "exact_replay_does_not_import_alpha_mapper", {"comqutor_alpha.structure_engine.alpha_mapper"})


def check_09_no_extractor() -> CheckResult:
    return forbidden_import_check(9, "exact_replay_does_not_import_structure_extractor", {"comqutor_alpha.structure_engine.structure_extractor"})


def check_10_no_gateway() -> CheckResult:
    return forbidden_import_check(10, "exact_replay_does_not_import_week2_gateway", {"comqutor_alpha.structure_engine.week2_llm"})


def check_11_no_tradingagents() -> CheckResult:
    return forbidden_import_check(11, "exact_replay_does_not_import_tradingagents", {"tradingagents"})


def check_12_no_provider_network_market() -> CheckResult:
    roots = {"socket", "http", "requests", "httpx", "yfinance", "openai", "anthropic"}
    return forbidden_import_check(12, "exact_replay_no_provider_network_market_imports", roots)


def check_13_no_db_redis() -> CheckResult:
    roots = {"redis", "sqlalchemy", "psycopg", "comqutor_alpha.storage.db"}
    return forbidden_import_check(13, "exact_replay_no_database_or_redis_imports", roots)


def check_14_missing_fail_closed() -> CheckResult:
    from comqutor_alpha.replay.source_bundle import (
        EXACT_REPLAY_SEMANTIC_ARTIFACT_MISSING,
        ExactReplayError,
        load_exact_semantic_source_bundle,
    )

    reason = None
    with tempfile.TemporaryDirectory(prefix="phase0_6c_missing_") as directory:
        source = Path(directory) / "missing-source"
        source.mkdir()
        try:
            load_exact_semantic_source_bundle(source)
        except ExactReplayError as exc:
            reason = exc.reason_code
    return result(14, "missing_source_artifact_fails_closed", reason == EXACT_REPLAY_SEMANTIC_ARTIFACT_MISSING, f"reason={reason}")


def check_15_not_ready_fail_closed() -> CheckResult:
    from comqutor_alpha.llm_runtime.manifest import SEMANTIC_MANIFEST_SCHEMA_VERSION
    from comqutor_alpha.replay.source_bundle import (
        EXACT_REPLAY_SEMANTIC_NOT_READY,
        ExactReplayError,
        _validate_manifest,
    )

    reason = None
    try:
        _validate_manifest(
            Path(tempfile.gettempdir()),
            {
                "schema_version": SEMANTIC_MANIFEST_SCHEMA_VERSION,
                "complete": True,
                "exact_replay_ready": False,
            },
        )
    except ExactReplayError as exc:
        reason = exc.reason_code
    return result(15, "not_ready_manifest_fails_closed", reason == EXACT_REPLAY_SEMANTIC_NOT_READY, f"reason={reason}")


def check_16_no_raw_fallback() -> CheckResult:
    source = (REPO_ROOT / "comqutor_alpha/replay/exact_semantic.py").read_text(encoding="utf-8")
    forbidden = [token for token in ("run_structure_replay", "adapt_run_outputs", "build_alpha_matches_payload", "build_extracted_structures_payload") if token in source]
    return result(16, "exact_replay_never_falls_back_to_raw_rebuild", not forbidden, f"forbidden={forbidden}")


def check_17_binding_unique() -> CheckResult:
    report = load_json(BEHAVIORAL)
    binding = report.get("semantic_binding", {})
    ok = (
        binding.get("final_status") == PASS
        and binding.get("total_records") == binding.get("uniquely_bound_records") == 3
        and not any(binding.get(key) for key in ("orphan_records", "missing_bindings", "ambiguous_bindings"))
    )
    return result(17, "semantic_call_binding_unique", ok, f"binding={binding}")


def check_18_byte_copy() -> CheckResult:
    report = load_json(BEHAVIORAL)
    artifacts = report.get("semantic_artifacts", {})
    ok = len(artifacts) == 5 and all(
        item.get("byte_identical") is True
        and item.get("source_sha256") == item.get("copy_sha256")
        for item in artifacts.values()
    )
    source = (REPO_ROOT / "comqutor_alpha/replay/exact_semantic.py").read_text(encoding="utf-8")
    ok = ok and "shutil.copyfile" in source
    return result(18, "semantic_artifacts_copied_byte_identically", ok, f"artifact_count={len(artifacts)}")


def check_19_source_unchanged() -> CheckResult:
    report = load_json(BEHAVIORAL)
    ok = report.get("source_files_unchanged_by_path_size_sha256_mtime") is True
    return result(19, "exact_source_run_files_unchanged", ok, f"unchanged={ok}")


def check_output_tree(number: int, section: str, root: str, name: str) -> CheckResult:
    baseline = load_json(SOURCE_BEFORE)[section]
    expected = [
        {
            key: item[key]
            for key in ("relative_path", "size_bytes", "sha256", "mtime_ns")
        }
        for item in baseline.get("files", [])
    ]
    actual = current_tree(root)
    return result(number, name, actual == expected, f"expected={len(expected)}; actual={len(actual)}")


def check_20_runs_unchanged() -> CheckResult:
    return check_output_tree(20, "outputs_runs", "outputs/runs", "historical_outputs_runs_unchanged")


def check_21_replays_unchanged() -> CheckResult:
    return check_output_tree(21, "outputs_replays", "outputs/replays", "historical_outputs_replays_unchanged")


def category_check(number: int, name: str, *categories: str) -> CheckResult:
    records = protected_records(*categories)
    errors = verify_records(records)
    return result(number, name, bool(records) and not errors, f"records={len(records)}; errors={errors}")


def check_22_live_week2() -> CheckResult:
    return category_check(22, "live_week2_files_unchanged", "live_week2_path")


def check_23_llm_runtime() -> CheckResult:
    return category_check(23, "llm_runtime_unchanged", "llm_runtime")


def check_24_prompts() -> CheckResult:
    return category_check(24, "prompt_and_canonical_injection_unchanged", "canonical_prompts")


def check_25_deterministic_core() -> CheckResult:
    return category_check(25, "graph_activation_conflict_exposure_unchanged", "graph_engine", "conflict_engine", "exposure_engine")


def check_26_default_llm() -> CheckResult:
    from comqutor_alpha.structure_engine.week2_llm import week2_llm_enabled

    previous = os.environ.pop("COMQUTOR_WEEK2_LLM_ENABLED", None)
    try:
        enabled = week2_llm_enabled()
    finally:
        if previous is not None:
            os.environ["COMQUTOR_WEEK2_LLM_ENABLED"] = previous
    return result(26, "week2_llm_default_remains_disabled", not enabled, f"enabled={enabled}")


def check_27_behavioral() -> CheckResult:
    report = load_json(BEHAVIORAL)
    comparisons = report.get("downstream_comparisons", {})
    ok = (
        report.get("overall_status") == PASS
        and report.get("semantic_inputs_reused_exactly") is True
        and report.get("deterministic_downstream_equivalent") is True
        and set(comparisons) == {"graph", "activation", "exposure", "conflict"}
        and all(item.get("semantically_equivalent") is True for item in comparisons.values())
    )
    return result(27, "behavioral_comparison_pass", ok, f"components={sorted(comparisons)}")


def check_28_zero_calls() -> CheckResult:
    evidence = load_json(PROVIDER_EVIDENCE)
    zero_fields = (
        "provider_calls",
        "tradingagents_calls",
        "market_data_calls",
        "completed_network_connections",
        "redis_connections",
        "database_connections",
        "database_writes",
    )
    ok = evidence.get("status") == PASS and all(evidence.get(key) == 0 for key in zero_fields)
    return result(28, "provider_network_redis_database_zero", ok, f"counts={{{', '.join(f'{key}: {evidence.get(key)}' for key in zero_fields)}}}")


def allowed_path(path: str) -> bool:
    return (
        path in {
            "comqutor_alpha/replay/__init__.py",
            "comqutor_alpha/replay/cli.py",
            "comqutor_alpha/replay/pipeline.py",
            "comqutor_alpha/replay/exact_semantic.py",
            "comqutor_alpha/replay/modes.py",
            "comqutor_alpha/replay/semantic_binding.py",
            "comqutor_alpha/replay/source_bundle.py",
            "docs/adr/ADR-007-exact-semantic-replay-integration.md",
            "docs/specs/exact_semantic_replay_integration_contract_v1.md",
            "scripts/verify_phase0_6c.py",
        }
        or path.startswith("tests/replay/")
        or path.startswith("docs/audit_artifacts/phase0_6c/")
    )


def check_29_allowed_diff() -> CheckResult:
    baseline = load_json(DIRTY_BEFORE)
    baseline_paths = {item["relative_path"] for item in baseline.get("files", [])}
    additions = status_paths() - baseline_paths
    disallowed_additions = sorted(path for path in additions if not allowed_path(path))
    changed_existing = {
        "comqutor_alpha/replay/__init__.py",
        "comqutor_alpha/replay/cli.py",
        "comqutor_alpha/replay/pipeline.py",
    }
    disallowed_existing = sorted(path for path in changed_existing if not allowed_path(path))
    return result(29, "allowed_diff_scope", not disallowed_additions and not disallowed_existing, f"additions={len(additions)}; disallowed={disallowed_additions + disallowed_existing}")


def check_30_preexisting_dirty() -> CheckResult:
    records = [
        item
        for item in load_json(DIRTY_BEFORE).get("files", [])
        if not item.get("allowed_existing_modification")
    ]
    errors = verify_records(records)
    return result(30, "preexisting_worktree_preserved", not errors, f"records={len(records)}; errors={errors}")


CHECKS: tuple[Callable[[], CheckResult], ...] = (
    check_01_plan_sha,
    check_02_prior_phases,
    check_03_adr007,
    check_04_contract,
    check_05_modes,
    check_06_raw_compatibility,
    check_07_no_adapter,
    check_08_no_mapper,
    check_09_no_extractor,
    check_10_no_gateway,
    check_11_no_tradingagents,
    check_12_no_provider_network_market,
    check_13_no_db_redis,
    check_14_missing_fail_closed,
    check_15_not_ready_fail_closed,
    check_16_no_raw_fallback,
    check_17_binding_unique,
    check_18_byte_copy,
    check_19_source_unchanged,
    check_20_runs_unchanged,
    check_21_replays_unchanged,
    check_22_live_week2,
    check_23_llm_runtime,
    check_24_prompts,
    check_25_deterministic_core,
    check_26_default_llm,
    check_27_behavioral,
    check_28_zero_calls,
    check_29_allowed_diff,
    check_30_preexisting_dirty,
)


def main() -> int:
    results: list[CheckResult] = []
    for check in CHECKS:
        try:
            item = check()
        except Exception as exc:  # verifier boundary: report, never mutate
            number = int(check.__name__.split("_", 2)[1])
            item = CheckResult(number, check.__name__, FAIL, type(exc).__name__)
        results.append(item)
        print(f"[{item.status}] {item.number:02d} {item.name}: {item.detail}")

    if any(item.status == FAIL for item in results):
        gate, exit_code = FAIL, 1
    elif any(item.status == BLOCKED for item in results):
        gate, exit_code = BLOCKED, 2
    else:
        gate, exit_code = PASS, 0
    print(f"PHASE_0_6C_EXACT_SEMANTIC_REPLAY: {gate}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
