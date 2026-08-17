"""Read-only repository verifier for the Phase 0.6A offline foundation.

Repository content is never written. The round-trip check writes only inside a
system temporary directory and uses an injected in-memory Redis-like client.
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = REPO_ROOT / "docs/audit_artifacts/phase0_6a"
START_SNAPSHOT = PHASE_DIR / "worktree_start_snapshot.json"
DIRTY_MANIFEST = PHASE_DIR / "preexisting_dirty_file_manifest.json"
SOURCE_BEFORE = PHASE_DIR / "source_artifact_integrity_before.json"
SOURCE_AFTER = PHASE_DIR / "source_artifact_integrity_after.json"

PASS = "PASS"
BLOCKED = "BLOCKED"
FAIL = "FAIL"

RUNTIME_FILES = (
    "comqutor_alpha/llm_runtime/__init__.py",
    "comqutor_alpha/llm_runtime/cache.py",
    "comqutor_alpha/llm_runtime/canonical_json.py",
    "comqutor_alpha/llm_runtime/contracts.py",
    "comqutor_alpha/llm_runtime/errors.py",
    "comqutor_alpha/llm_runtime/manifest.py",
    "comqutor_alpha/llm_runtime/recorder.py",
)
REQUIRED_OUTPUTS = (
    *RUNTIME_FILES,
    "tests/llm_runtime/__init__.py",
    "tests/llm_runtime/fakes.py",
    "tests/llm_runtime/test_canonical_json.py",
    "tests/llm_runtime/test_contracts.py",
    "tests/llm_runtime/test_cache_key.py",
    "tests/llm_runtime/test_null_cache.py",
    "tests/llm_runtime/test_redis_cache_adapter.py",
    "tests/llm_runtime/test_recorder.py",
    "tests/llm_runtime/test_manifest.py",
    "tests/llm_runtime/test_corruption.py",
    "tests/llm_runtime/test_no_production_importers.py",
    "docs/specs/llm_semantic_call_contract_v1.md",
    "docs/specs/exact_semantic_replay_artifact_contract_v1.md",
    "docs/adr/ADR-005-llm-execution-substrate.md",
    "scripts/verify_phase0_6a.py",
    "docs/audit_artifacts/phase0_6a/worktree_start_snapshot.json",
    "docs/audit_artifacts/phase0_6a/preexisting_dirty_file_manifest.json",
    "docs/audit_artifacts/phase0_6a/source_artifact_integrity_before.json",
    "docs/audit_artifacts/phase0_6a/worktree_end_snapshot.json",
    "docs/audit_artifacts/phase0_6a/source_artifact_integrity_after.json",
    "docs/audit_artifacts/phase0_6a/preexisting_dirty_file_comparison.json",
    "docs/audit_artifacts/phase0_6a/allowed_diff_report.json",
    "docs/audit_artifacts/phase0_6a/test_results.json",
    "docs/audit_artifacts/phase0_6a/phase0_6a_gate_report.json",
    "docs/audit_artifacts/phase0_6a/phase0_6a_completion_report.md",
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str


def result(name: str, ok: bool, detail: str, *, blocked: bool = False) -> CheckResult:
    return CheckResult(name, PASS if ok else (BLOCKED if blocked else FAIL), detail)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def git_output(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
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


def current_tree(relative_directory: str) -> list[dict[str, Any]]:
    root = REPO_ROOT / relative_directory
    records: list[dict[str, Any]] = []
    if root.is_dir():
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


def baseline_records(section: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "relative_path": item["relative_path"],
            "size_bytes": item["size_bytes"],
            "sha256": item["sha256"],
            "mtime_ns": item["mtime_ns"],
        }
        for item in section.get("files", [])
    ]


def verify_file_records(records: list[dict[str, Any]]) -> list[str]:
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
        if "mtime_ns" in record and stat.st_mtime_ns != record["mtime_ns"]:
            errors.append(f"mtime:{relative}")
    return errors


def protected_record(relative: str) -> dict[str, Any] | None:
    if not START_SNAPSHOT.is_file():
        return None
    snapshot = load_json(START_SNAPSHOT)
    records = {item["relative_path"]: item for item in snapshot["protected_runtime_files"]}
    return records.get(relative)


def check_canonical_plan_and_phase0_5() -> CheckResult:
    if not START_SNAPSHOT.is_file():
        return CheckResult("canonical_plan_and_phase0_5_unchanged", BLOCKED, "start snapshot missing")
    snapshot = load_json(START_SNAPSHOT)
    records = snapshot.get("phase0_files", []) + snapshot.get("phase0_5_files", [])
    errors = verify_file_records(records)
    plan = REPO_ROOT / "docs/specs/COMQUTOR_Alpha_Development_Plan_v1.0.docx"
    manifest_path = REPO_ROOT / "docs/specs/development_plan_v1.0_manifest.json"
    if not plan.is_file() or not manifest_path.is_file():
        errors.append("canonical_plan_or_manifest_missing")
    else:
        manifest = load_json(manifest_path)
        actual = sha256(plan)
        if actual != manifest.get("repository_sha256") or actual != manifest.get("source_sha256"):
            errors.append("canonical_plan_manifest_sha_mismatch")
    return result(
        "canonical_plan_and_phase0_5_unchanged",
        not errors,
        f"records={len(records)}; errors={errors}",
    )


def check_adr_001_through_004() -> CheckResult:
    if not START_SNAPSHOT.is_file():
        return CheckResult("adr_001_through_004_unchanged", BLOCKED, "start snapshot missing")
    snapshot = load_json(START_SNAPSHOT)
    wanted = {
        f"docs/adr/ADR-00{number}-{suffix}.md"
        for number, suffix in (
            (1, "semantic-authority"),
            (2, "tradingagents-boundary"),
            (3, "replay-semantics"),
            (4, "evidence-stance-provenance"),
        )
    }
    records = [item for item in snapshot.get("phase0_5_files", []) if item["relative_path"] in wanted]
    errors = verify_file_records(records)
    if {item["relative_path"] for item in records} != wanted:
        errors.append("ADR baseline set incomplete")
    return result("adr_001_through_004_unchanged", not errors, f"errors={errors}")


def check_adr_005() -> CheckResult:
    path = REPO_ROOT / "docs/adr/ADR-005-llm-execution-substrate.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    required = (
        "ACCEPTED_FOR_OFFLINE_FOUNDATION",
        "NOT_INTEGRATED",
        "NO_PRODUCTION_AUTHORITY",
        "SOURCE_FROZEN",
        "APPROVED_PROJECT_DECISION",
        "CURRENT_IMPLEMENTATION",
    )
    missing = [token for token in required if token not in text]
    return result("adr_005_status_and_provenance", path.is_file() and not missing, f"missing={missing}")


def check_runtime_files() -> CheckResult:
    missing = [relative for relative in RUNTIME_FILES if not (REPO_ROOT / relative).is_file()]
    return result("llm_runtime_files_exist", not missing, f"missing={missing}")


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def check_production_importers() -> CheckResult:
    runtime = REPO_ROOT / "comqutor_alpha/llm_runtime"
    importers: list[str] = []
    for root_name in ("comqutor_alpha", "tradingagents"):
        for path in (REPO_ROOT / root_name).rglob("*.py"):
            if runtime in path.parents:
                continue
            if any(module.startswith("comqutor_alpha.llm_runtime") for module in imported_modules(path)):
                importers.append(path.relative_to(REPO_ROOT).as_posix())
    return result("current_production_importer_count_zero", not importers, f"importers={importers}")


def check_protected(relative_paths: tuple[str, ...], name: str) -> CheckResult:
    errors: list[str] = []
    for relative in relative_paths:
        record = protected_record(relative)
        if record is None:
            errors.append(f"baseline_missing:{relative}")
        else:
            errors.extend(verify_file_records([record]))
    return result(name, not errors, f"errors={errors}", blocked=not START_SNAPSHOT.is_file())


def check_week2_gateway() -> CheckResult:
    return check_protected(
        ("comqutor_alpha/structure_engine/week2_llm.py",),
        "week2_gateway_unchanged",
    )


def check_adapter_mapper_extractor() -> CheckResult:
    return check_protected(
        (
            "comqutor_alpha/structure_engine/structured_output_adapter.py",
            "comqutor_alpha/structure_engine/alpha_mapper.py",
            "comqutor_alpha/structure_engine/structure_extractor.py",
        ),
        "adapter_mapper_extractor_unchanged",
    )


def check_canonical_prompt() -> CheckResult:
    return check_protected(
        (
            "comqutor_alpha/llm/canonical_prompt_injection.py",
            "comqutor_alpha/structure_engine/canonical_relation_prompt.py",
        ),
        "canonical_prompt_injection_unchanged",
    )


def check_replay_pipeline() -> CheckResult:
    return check_protected(("comqutor_alpha/replay/pipeline.py",), "replay_pipeline_unchanged")


def check_llm_default() -> CheckResult:
    path = REPO_ROOT / "comqutor_alpha/structure_engine/week2_llm.py"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    exact_gate = 'if not _enabled(os.environ.get("COMQUTOR_WEEK2_LLM_ENABLED")):' in text
    protected = check_week2_gateway()
    return result(
        "week2_llm_default_opt_in_unchanged",
        protected.status == PASS and exact_gate,
        f"week2_hash={protected.status}; explicit_opt_in_gate={exact_gate}",
    )


def check_output_tree(section: str, relative: str, name: str) -> CheckResult:
    if not SOURCE_BEFORE.is_file() or not SOURCE_AFTER.is_file():
        return CheckResult(name, BLOCKED, "before/after proof missing")
    before = load_json(SOURCE_BEFORE)[section]
    after = load_json(SOURCE_AFTER)[section]
    before_records = baseline_records(before)
    after_records = baseline_records(after)
    current_records = current_tree(relative)
    errors = []
    if before_records != after_records:
        errors.append("before_after_mismatch")
    if before_records != current_records:
        errors.append("baseline_current_mismatch")
    return result(name, not errors, f"files={len(current_records)}; errors={errors}")


def check_outputs_runs() -> CheckResult:
    return check_output_tree("outputs_runs", "outputs/runs", "outputs_runs_unchanged")


def check_outputs_replays() -> CheckResult:
    return check_output_tree("outputs_replays", "outputs/replays", "outputs_replays_unchanged")


def check_preexisting_dirty() -> CheckResult:
    if not DIRTY_MANIFEST.is_file():
        return CheckResult("preexisting_dirty_files_unchanged", BLOCKED, "baseline missing")
    baseline = load_json(DIRTY_MANIFEST)
    records = baseline.get("files", [])
    errors = verify_file_records(records)
    return result(
        "preexisting_dirty_files_unchanged",
        not errors,
        f"files={len(records)}; errors={errors}",
    )


def check_runtime_has_no_io_factories() -> CheckResult:
    forbidden = {
        "anthropic",
        "boto3",
        "cohere",
        "google.generativeai",
        "httpx",
        "openai",
        "psycopg",
        "psycopg2",
        "redis",
        "requests",
        "socket",
        "sqlalchemy",
        "urllib.request",
    }
    violations: list[str] = []
    for relative in RUNTIME_FILES:
        path = REPO_ROOT / relative
        if not path.is_file():
            continue
        for module in imported_modules(path):
            if any(module == root or module.startswith(f"{root}.") for root in forbidden):
                violations.append(f"{relative}:{module}")
    return result("llm_runtime_no_network_provider_db_side_effect", not violations, f"violations={violations}")


def check_schema_versions() -> CheckResult:
    from comqutor_alpha.llm_runtime.cache import LLM_CACHE_KEY_VERSION
    from comqutor_alpha.llm_runtime.contracts import (
        LLM_CACHE_ENTRY_SCHEMA_VERSION,
        SEMANTIC_CALL_SCHEMA_VERSION,
    )
    from comqutor_alpha.llm_runtime.manifest import SEMANTIC_MANIFEST_SCHEMA_VERSION

    actual = {
        "semantic_call": SEMANTIC_CALL_SCHEMA_VERSION,
        "cache_entry": LLM_CACHE_ENTRY_SCHEMA_VERSION,
        "cache_key": LLM_CACHE_KEY_VERSION,
        "manifest": SEMANTIC_MANIFEST_SCHEMA_VERSION,
    }
    expected = {
        "semantic_call": "comqutor.semantic_call.v1",
        "cache_entry": "comqutor.llm_cache_entry.v1",
        "cache_key": "comqutor.llm_cache_key.v1",
        "manifest": "comqutor.semantic_manifest.v1",
    }
    return result("contract_schema_versions", actual == expected, f"actual={actual}")


def check_offline_round_trip() -> CheckResult:
    from comqutor_alpha.llm_runtime.cache import RedisLLMResponseCache, build_llm_cache_key
    from comqutor_alpha.llm_runtime.canonical_json import (
        sha256_canonical_json,
        sha256_text,
    )
    from comqutor_alpha.llm_runtime.contracts import (
        SEMANTIC_CALL_SCHEMA_VERSION,
        cache_entry_from_record,
    )
    from comqutor_alpha.llm_runtime.manifest import (
        build_semantic_manifest,
        verify_semantic_manifest,
        write_semantic_manifest_atomic,
    )
    from comqutor_alpha.llm_runtime.recorder import SemanticCallRecorder

    class FakeClient:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}
            self.calls = 0

        def get(self, key: str) -> str | None:
            self.calls += 1
            return self.values.get(key)

        def set(self, key: str, value: str, *, ex: int | None = None) -> None:
            del ex
            self.calls += 1
            self.values[key] = value

        def delete(self, key: str) -> None:
            self.calls += 1
            self.values.pop(key, None)

        def ping(self) -> bool:
            self.calls += 1
            return True

    payload = {"ticker": "AAPL"}
    output = {"claims": []}
    prompt_hash = sha256_text("prompt")
    input_hash = sha256_canonical_json(payload)
    cache_key = build_llm_cache_key(
        task="structured_adapter",
        prompt_version="prompt.v1",
        prompt_sha256=prompt_hash,
        provider="fake-provider",
        model="fake-model",
        input_schema_version="input.v1",
        output_schema_version="output.v1",
        input_sha256=input_hash,
    )
    raw = '{"claims":[]}'
    record = {
        "schema_version": SEMANTIC_CALL_SCHEMA_VERSION,
        "call_id": "verify-call-0",
        "run_id": "verify-run",
        "call_sequence": 0,
        "task": "structured_adapter",
        "execution_mode": "test",
        "prompt_version": "prompt.v1",
        "prompt_sha256": prompt_hash,
        "input_schema_version": "input.v1",
        "output_schema_version": "output.v1",
        "provider": "fake-provider",
        "model": "fake-model",
        "taxonomy_version": None,
        "input_payload": payload,
        "input_sha256": input_hash,
        "raw_output_text": raw,
        "raw_output_sha256": sha256_text(raw),
        "validated_output": output,
        "validated_output_sha256": sha256_canonical_json(output),
        "started_at": "2026-01-01T00:00:00+00:00",
        "completed_at": "2026-01-01T00:00:00.001000+00:00",
        "latency_ms": 1,
        "token_usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        "cache": {"cache_key": cache_key, "hit": False},
        "retry_count": 0,
        "validation_status": "accepted",
        "provider_status": "success",
        "fallback_used": False,
        "fallback_reason": None,
        "error_code": None,
        "error_message": None,
    }
    with tempfile.TemporaryDirectory(prefix="phase0_6a_verify_") as directory_name:
        directory = Path(directory_name)
        recorder = SemanticCallRecorder(
            run_id="verify-run", output_directory=directory, mode="test"
        )
        recorder.append(record)
        if recorder.read_all() != [record] or not recorder.verify_integrity().valid:
            return CheckResult("json_jsonl_manifest_round_trip", FAIL, "recorder round-trip failed")
        entry = cache_entry_from_record(record, created_at="2026-01-01T00:00:01+00:00")
        fake = FakeClient()
        cache = RedisLLMResponseCache(fake)
        if fake.calls != 0:
            return CheckResult("json_jsonl_manifest_round_trip", FAIL, "constructor performed client I/O")
        cache.put(cache_key, entry, ttl_seconds=60)
        if cache.get(cache_key) != entry.to_dict():
            return CheckResult("json_jsonl_manifest_round_trip", FAIL, "cache round-trip failed")
        manifest = build_semantic_manifest(
            run_id="verify-run",
            calls_path=recorder.calls_path,
            complete=True,
            created_at="2026-01-01T00:00:01+00:00",
            finalized_at="2026-01-01T00:00:02+00:00",
        )
        manifest_path = write_semantic_manifest_atomic(
            manifest=manifest,
            output_directory=directory,
        )
        verification = verify_semantic_manifest(manifest_path)
        return result(
            "json_jsonl_manifest_round_trip",
            verification.valid,
            f"reason_codes={verification.reason_codes}; temp_only=True",
        )


def check_source_artifacts() -> CheckResult:
    if not START_SNAPSHOT.is_file():
        return CheckResult("source_artifacts_unchanged", BLOCKED, "start snapshot missing")
    snapshot = load_json(START_SNAPSHOT)
    records = snapshot.get("phase0_files", []) + snapshot.get("phase0_5_files", [])
    errors = verify_file_records(records)
    missing = snapshot.get("phase0_missing", []) + snapshot.get("phase0_5_missing", [])
    if missing:
        errors.append(f"baseline_missing={missing}")
    return result("source_artifacts_unchanged", not errors, f"records={len(records)}; errors={errors}")


def allowed_phase_path(relative: str) -> bool:
    return (
        relative.startswith("comqutor_alpha/llm_runtime/")
        or relative.startswith("tests/llm_runtime/")
        or relative.startswith("docs/audit_artifacts/phase0_6a/")
        or relative == "docs/specs/llm_semantic_call_contract_v1.md"
        or relative == "docs/specs/exact_semantic_replay_artifact_contract_v1.md"
        or relative == "docs/adr/ADR-005-llm-execution-substrate.md"
        or relative == "scripts/verify_phase0_6a.py"
    )


def check_allowed_diff() -> CheckResult:
    if not DIRTY_MANIFEST.is_file():
        return CheckResult("phase0_6a_changes_only_allowed_paths", BLOCKED, "dirty baseline missing")
    baseline = load_json(DIRTY_MANIFEST)
    preexisting = {record["relative_path"] for record in baseline.get("files", [])}
    additions = sorted(status_paths() - preexisting)
    disallowed = [relative for relative in additions if not allowed_phase_path(relative)]
    return result(
        "phase0_6a_changes_only_allowed_paths",
        not disallowed,
        f"phase_additions={len(additions)}; disallowed={disallowed}",
    )


def check_required_outputs() -> CheckResult:
    missing = [relative for relative in REQUIRED_OUTPUTS if not (REPO_ROOT / relative).is_file()]
    return result(
        "phase0_6a_required_outputs_exist",
        not missing,
        f"missing={missing}",
        blocked=bool(missing),
    )


def check_branch_and_head() -> CheckResult:
    if not START_SNAPSHOT.is_file():
        return CheckResult("branch_and_head_unchanged", BLOCKED, "start snapshot missing")
    snapshot = load_json(START_SNAPSHOT)
    branch = git_output("branch", "--show-current").strip()
    head = git_output("rev-parse", "HEAD").strip()
    ok = branch == snapshot["branch"] and head == snapshot["head"]
    return result("branch_and_head_unchanged", ok, f"branch={branch}; head={head}")


CHECKS: tuple[Callable[[], CheckResult], ...] = (
    check_canonical_plan_and_phase0_5,
    check_adr_001_through_004,
    check_adr_005,
    check_runtime_files,
    check_production_importers,
    check_week2_gateway,
    check_adapter_mapper_extractor,
    check_canonical_prompt,
    check_replay_pipeline,
    check_llm_default,
    check_outputs_runs,
    check_outputs_replays,
    check_preexisting_dirty,
    check_runtime_has_no_io_factories,
    check_schema_versions,
    check_offline_round_trip,
    check_source_artifacts,
    check_allowed_diff,
    check_required_outputs,
    check_branch_and_head,
)


def main() -> int:
    results: list[CheckResult] = []
    for check in CHECKS:
        try:
            check_result = check()
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            check_result = CheckResult(check.__name__, FAIL, f"{type(exc).__name__}: {exc}")
        results.append(check_result)
        print(f"[{check_result.status}] {check_result.name}: {check_result.detail}")

    if any(item.status == FAIL for item in results):
        gate, exit_code = FAIL, 1
    elif any(item.status == BLOCKED for item in results):
        gate, exit_code = BLOCKED, 2
    else:
        gate, exit_code = PASS, 0
    print(f"PHASE_0_6A_OFFLINE_FOUNDATION: {gate}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
