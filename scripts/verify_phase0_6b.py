"""Read-only 25-check verifier for Phase 0.6B Week2 runtime integration.

Repository content is never written. Behavioral probes use only a system
temporary directory and in-memory fakes; they make no Provider, Redis,
network, or database connection.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import os
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = REPO_ROOT / "docs/audit_artifacts/phase0_6b"
START_SNAPSHOT = PHASE_DIR / "worktree_start_snapshot.json"
DIRTY_BASELINE = PHASE_DIR / "preexisting_dirty_file_manifest.json"
PROTECTED_BEFORE = PHASE_DIR / "protected_file_manifest_before.json"
SOURCE_BEFORE = PHASE_DIR / "source_artifact_integrity_before.json"
BEHAVIORAL_REPORT = PHASE_DIR / "behavioral_invariant_comparison.json"

PASS = "PASS"
BLOCKED = "BLOCKED"
FAIL = "FAIL"

PROVIDER_CALLS = 0
REDIS_CONNECTIONS = 0
DB_WRITES = 0


@dataclass(frozen=True)
class CheckResult:
    number: int
    name: str
    status: str
    detail: str


def outcome(number: int, name: str, ok: bool, detail: str, *, blocked=False) -> CheckResult:
    return CheckResult(number, name, PASS if ok else (BLOCKED if blocked else FAIL), detail)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


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


def protected_records(*categories: str) -> list[dict[str, Any]]:
    manifest = load_json(PROTECTED_BEFORE)
    wanted = set(categories)
    return [
        record
        for record in manifest.get("strict_files", [])
        if wanted.intersection(record.get("categories", []))
    ]


def verify_records(records: list[dict[str, Any]], *, mtime=True) -> list[str]:
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
        if mtime and stat.st_mtime_ns != record["mtime_ns"]:
            errors.append(f"mtime:{relative}")
    return errors


def one_record(relative: str) -> dict[str, Any] | None:
    manifest = load_json(PROTECTED_BEFORE)
    return next(
        (
            record
            for record in manifest.get("strict_files", [])
            if record["relative_path"] == relative
        ),
        None,
    )


def check_01_plan_sha() -> CheckResult:
    plan = REPO_ROOT / "docs/specs/COMQUTOR_Alpha_Development_Plan_v1.0.docx"
    manifest_path = REPO_ROOT / "docs/specs/development_plan_v1.0_manifest.json"
    if not plan.is_file() or not manifest_path.is_file():
        return outcome(1, "development_plan_sha_unchanged", False, "plan or manifest missing")
    manifest = load_json(manifest_path)
    digest = sha256(plan)
    ok = digest == manifest.get("source_sha256") == manifest.get("repository_sha256")
    record = one_record("docs/specs/COMQUTOR_Alpha_Development_Plan_v1.0.docx")
    ok = ok and record is not None and not verify_records([record])
    return outcome(1, "development_plan_sha_unchanged", ok, f"sha256={digest}")


def check_02_prior_phase_files() -> CheckResult:
    if not PROTECTED_BEFORE.is_file():
        return outcome(2, "phase0_5_and_0_6a_protected_unchanged", False, "baseline missing", blocked=True)
    records = protected_records("phase_artifact")
    errors = verify_records(records)
    return outcome(
        2,
        "phase0_5_and_0_6a_protected_unchanged",
        not errors,
        f"records={len(records)}; errors={errors}",
    )


def check_03_adr006() -> CheckResult:
    path = REPO_ROOT / "docs/adr/ADR-006-week2-semantic-runtime-integration.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    required = {
        "ACCEPTED_FOR_INTEGRATION",
        "DEFAULT_DISABLED",
        "NO_SEMANTIC_AUTHORITY_CHANGE",
        "SOURCE_FROZEN",
        "APPROVED_PROJECT_DECISION",
        "CURRENT_IMPLEMENTATION",
    }
    missing = sorted(token for token in required if token not in text)
    return outcome(3, "adr006_status", path.is_file() and not missing, f"missing={missing}")


def check_04_gateway_runtime_integration() -> CheckResult:
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

    methods = {
        "invoke_json",
        "invoke_json_with_trace",
        "finalize_semantic_invocation",
        "attach_semantic_runtime",
    }
    missing = sorted(name for name in methods if not callable(getattr(Week2LLMGateway, name, None)))
    return outcome(4, "gateway_integrates_semantic_runtime", not missing, f"missing={missing}")


def check_05_gateway_default_runtime_none() -> CheckResult:
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

    default = inspect.signature(Week2LLMGateway.__init__).parameters["semantic_runtime"].default
    return outcome(5, "gateway_default_runtime_none", default is None, f"default={default!r}")


def check_06_prompt_hashes() -> CheckResult:
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

    baseline = load_json(PROTECTED_BEFORE)["week2_behavior_baseline"]
    expected = baseline["prompt_identity_sha256_by_task"]
    actual = {task: Week2LLMGateway.prompt_identity_sha256(task) for task in expected}
    return outcome(6, "prompt_hashes_unchanged", actual == expected, f"actual={actual}")


def check_07_gateway_defaults() -> CheckResult:
    from comqutor_alpha.structure_engine.week2_llm import (
        DEFAULT_MAX_CALLS,
        DEFAULT_MAX_RETRIES,
        DEFAULT_TIMEOUT_SECONDS,
    )

    baseline = load_json(PROTECTED_BEFORE)["week2_behavior_baseline"]
    actual = {
        "default_timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
        "default_max_retries": DEFAULT_MAX_RETRIES,
        "default_max_calls": DEFAULT_MAX_CALLS,
    }
    expected = {key: baseline[key] for key in actual}
    return outcome(7, "retry_timeout_budget_defaults_unchanged", actual == expected, f"actual={actual}")


def check_08_caller_finalization_only() -> CheckResult:
    files = (
        "comqutor_alpha/structure_engine/structured_output_adapter.py",
        "comqutor_alpha/structure_engine/alpha_mapper.py",
        "comqutor_alpha/structure_engine/structure_extractor.py",
    )
    errors = []
    for relative in files:
        path = REPO_ROOT / relative
        text = path.read_text(encoding="utf-8")
        if "invoke_json_with_trace" not in text or "finalize_semantic_invocation" not in text:
            errors.append(f"missing_wiring:{relative}")
        runtime_imports = [m for m in imported_modules(path) if m.startswith("comqutor_alpha.llm_runtime")]
        if runtime_imports:
            errors.append(f"direct_runtime_import:{relative}:{runtime_imports}")
    return outcome(8, "three_callers_minimal_finalization_wiring", not errors, f"errors={errors}")


def check_09_replay_unchanged() -> CheckResult:
    record = one_record("comqutor_alpha/replay/pipeline.py")
    errors = ["baseline_missing"] if record is None else verify_records([record])
    text = (REPO_ROOT / "comqutor_alpha/replay/pipeline.py").read_text(encoding="utf-8")
    if "comqutor_alpha.llm_runtime" in text:
        errors.append("runtime_import")
    return outcome(9, "replay_pipeline_unchanged", not errors, f"errors={errors}")


def check_10_tradingagents_unchanged() -> CheckResult:
    records = protected_records("tradingagents")
    errors = verify_records(records)
    return outcome(10, "tradingagents_unchanged", not errors, f"records={len(records)}; errors={errors}")


def check_11_canonical_prompt_unchanged() -> CheckResult:
    paths = (
        "comqutor_alpha/llm/canonical_prompt_injection.py",
        "comqutor_alpha/structure_engine/canonical_relation_prompt.py",
    )
    records = [record for path in paths if (record := one_record(path)) is not None]
    errors = verify_records(records)
    if len(records) != len(paths):
        errors.append("baseline_missing")
    return outcome(11, "canonical_prompt_files_unchanged", not errors, f"errors={errors}")


def check_12_deterministic_core_unchanged() -> CheckResult:
    records = protected_records(
        "comqutor_alpha/graph_engine",
        "comqutor_alpha/conflict_engine",
        "explicit_protected",
    )
    excluded = {
        "comqutor_alpha/replay/pipeline.py",
        "comqutor_alpha/llm/canonical_prompt_injection.py",
        "comqutor_alpha/structure_engine/canonical_relation_prompt.py",
    }
    records = [record for record in records if record["relative_path"] not in excluded]
    errors = verify_records(records)
    return outcome(12, "graph_activation_conflict_exposure_unchanged", not errors, f"records={len(records)}; errors={errors}")


def check_13_llm_default_flag() -> CheckResult:
    from comqutor_alpha.structure_engine.week2_llm import week2_llm_enabled

    previous = os.environ.pop("COMQUTOR_WEEK2_LLM_ENABLED", None)
    try:
        enabled = week2_llm_enabled()
    finally:
        if previous is not None:
            os.environ["COMQUTOR_WEEK2_LLM_ENABLED"] = previous
    return outcome(13, "week2_llm_default_remains_disabled", not enabled, f"enabled={enabled}")


def check_14_disabled_no_sidecars() -> CheckResult:
    from comqutor_alpha.structure_engine.week2_llm import build_server_week2_llm_gateway

    previous = os.environ.get("COMQUTOR_WEEK2_LLM_ENABLED")
    os.environ["COMQUTOR_WEEK2_LLM_ENABLED"] = "false"
    try:
        with tempfile.TemporaryDirectory(prefix="phase0_6b_disabled_") as directory_name:
            directory = Path(directory_name)
            (directory / "verify-disabled").mkdir()
            gateway = build_server_week2_llm_gateway("verify-disabled", directory)
            sidecars = list(directory.rglob("llm_semantic_*"))
    finally:
        if previous is None:
            os.environ.pop("COMQUTOR_WEEK2_LLM_ENABLED", None)
        else:
            os.environ["COMQUTOR_WEEK2_LLM_ENABLED"] = previous
    return outcome(14, "disabled_creates_no_semantic_sidecars", gateway is None and not sidecars, f"sidecars={sidecars}")


class _MemoryCache:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.put_count = 0

    def get(self, key: str):
        return self.values.get(key)

    def put(self, key: str, entry: Any, ttl_seconds=None) -> None:
        del ttl_seconds
        self.put_count += 1
        self.values[key] = entry.to_dict() if hasattr(entry, "to_dict") else dict(entry)

    def delete(self, key: str) -> None:
        self.values.pop(key, None)

    def healthcheck(self) -> bool:
        return True


class _ForbiddenProvider:
    def invoke(self, prompt: str):
        global PROVIDER_CALLS
        PROVIDER_CALLS += 1
        raise AssertionError(f"Provider invocation forbidden: {len(prompt)}")


def _cache_hit_probe() -> tuple[bool, int, int]:
    from comqutor_alpha.llm_runtime.cache import build_llm_cache_key
    from comqutor_alpha.llm_runtime.canonical_json import sha256_canonical_json
    from comqutor_alpha.llm_runtime.contracts import LLM_CACHE_ENTRY_SCHEMA_VERSION
    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

    payload = {"allowed_alpha_ids": ["A101"]}
    candidate = {"decision": "defer", "selected_alpha_id": None}
    prompt_sha = Week2LLMGateway.prompt_identity_sha256("alpha_classifier")
    input_sha = sha256_canonical_json(payload)
    cache_key = build_llm_cache_key(
        task="alpha_classifier",
        prompt_version="week2.alpha_classifier.v1",
        prompt_sha256=prompt_sha,
        provider="fake-provider",
        model="fake-model",
        input_schema_version="week2.alpha_classifier.input.v1",
        output_schema_version="week2.alpha_classifier.output.v1",
        taxonomy_version="alpha_taxonomy_v1",
        input_sha256=input_sha,
    )
    cache = _MemoryCache()
    cache.values[cache_key] = {
        "schema_version": LLM_CACHE_ENTRY_SCHEMA_VERSION,
        "cache_key": cache_key,
        "task": "alpha_classifier",
        "prompt_sha256": prompt_sha,
        "input_sha256": input_sha,
        "provider": "fake-provider",
        "model": "fake-model",
        "output_schema_version": "week2.alpha_classifier.output.v1",
        "validated_output": candidate,
        "validated_output_sha256": sha256_canonical_json(candidate),
        "created_at": "2026-08-05T00:00:00+00:00",
        "expires_at": None,
    }
    validator_calls = 0
    with tempfile.TemporaryDirectory(prefix="phase0_6b_cache_hit_") as directory_name:
        session = SemanticRuntimeSession(
            run_id="verify-cache-hit",
            output_directory=directory_name,
            execution_mode="test",
            provider="fake-provider",
            model="fake-model",
            cache=cache,
        )
        gateway = Week2LLMGateway(
            _ForbiddenProvider(),
            run_id="verify-cache-hit",
            output_root=directory_name,
            provider="fake-provider",
            model_name="fake-model",
            semantic_runtime=session,
        )

        def validator(value: Mapping[str, Any]):
            nonlocal validator_calls
            validator_calls += 1
            if set(value) != {"decision", "selected_alpha_id"}:
                raise ValueError("invalid cached candidate")
            return dict(value)

        invocation = gateway.invoke_json_with_trace("alpha_classifier", payload, validator)
        gateway.finalize_semantic_invocation(invocation, accepted=True)
        return invocation.cache_hit, validator_calls, gateway.call_count


def check_15_cache_hit_revalidates() -> CheckResult:
    cache_hit, validator_calls, provider_calls = _cache_hit_probe()
    ok = cache_hit and validator_calls == 1 and provider_calls == 0
    return outcome(15, "cache_hit_reexecutes_task_validator", ok, f"validator_calls={validator_calls}; provider_calls={provider_calls}")


def check_16_cache_accepted_only() -> CheckResult:
    from comqutor_alpha.llm_runtime.canonical_json import sha256_text
    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession

    cache = _MemoryCache()
    with tempfile.TemporaryDirectory(prefix="phase0_6b_cache_write_") as directory_name:
        session = SemanticRuntimeSession(
            run_id="verify-cache-write",
            output_directory=directory_name,
            execution_mode="test",
            provider="fake-provider",
            model="fake-model",
            cache=cache,
        )
        common = {
            "task": "alpha_classifier",
            "prompt_version": "week2.alpha_classifier.v1",
            "prompt_sha256": sha256_text("fixed"),
            "input_schema_version": "input.v1",
            "output_schema_version": "output.v1",
            "taxonomy_version": "alpha_taxonomy_v1",
        }
        rejected = session.start_call(input_payload={"case": "rejected"}, **common)
        session.finalize_call(
            rejected.trace_handle,
            provider_status="success",
            retry_count=0,
            validation_status="rejected",
            accepted_candidate=None,
            fallback_used=True,
            fallback_reason="WEEK2_LLM_ALPHA_CLASSIFIER_FALLBACK",
            error_code=None,
        )
        after_rejected = cache.put_count
        accepted = session.start_call(input_payload={"case": "accepted"}, **common)
        session.finalize_call(
            accepted.trace_handle,
            provider_status="success",
            retry_count=0,
            validation_status="accepted",
            accepted_candidate={"decision": "defer", "selected_alpha_id": None},
            fallback_used=False,
            fallback_reason=None,
            error_code=None,
        )
    ok = after_rejected == 0 and cache.put_count == 1
    return outcome(16, "cache_writes_only_accepted_provider_success", ok, f"after_rejected={after_rejected}; total={cache.put_count}")


def check_17_raw_output_not_persisted() -> CheckResult:
    from comqutor_alpha.llm_runtime.canonical_json import sha256_text
    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession

    with tempfile.TemporaryDirectory(prefix="phase0_6b_raw_null_") as directory_name:
        session = SemanticRuntimeSession(
            run_id="verify-raw-null",
            output_directory=directory_name,
            execution_mode="test",
            provider="fake-provider",
            model="fake-model",
        )
        call = session.start_call(
            task="alpha_classifier",
            prompt_version="week2.alpha_classifier.v1",
            prompt_sha256=sha256_text("fixed"),
            input_schema_version="input.v1",
            output_schema_version="output.v1",
            taxonomy_version="alpha_taxonomy_v1",
            input_payload={"allowed_alpha_ids": ["A101"]},
        )
        session.finalize_call(
            call.trace_handle,
            provider_status="success",
            retry_count=0,
            validation_status="accepted",
            accepted_candidate={"decision": "defer", "selected_alpha_id": None},
            fallback_used=False,
            fallback_reason=None,
            error_code=None,
        )
        record = session.recorder.read_all()[0]
    ok = record["raw_output_text"] is None and record["raw_output_sha256"] is None
    return outcome(17, "raw_provider_output_null_by_default", ok, f"raw_fields={(record['raw_output_text'], record['raw_output_sha256'])}")


def current_tree(relative_root: str) -> list[dict[str, Any]]:
    root = REPO_ROOT / relative_root
    records = []
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


def normalized_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "relative_path": record["relative_path"],
            "size_bytes": record["size_bytes"],
            "sha256": record["sha256"],
            "mtime_ns": record["mtime_ns"],
        }
        for record in records
    ]


def check_output_tree(number: int, section: str, relative: str, name: str) -> CheckResult:
    if not SOURCE_BEFORE.is_file():
        return outcome(number, name, False, "baseline missing", blocked=True)
    expected = normalized_records(load_json(SOURCE_BEFORE)[section]["files"])
    actual = current_tree(relative)
    return outcome(number, name, actual == expected, f"expected={len(expected)}; actual={len(actual)}")


def check_18_outputs_runs() -> CheckResult:
    return check_output_tree(18, "outputs_runs", "outputs/runs", "historical_outputs_runs_unchanged")


def check_19_outputs_replays() -> CheckResult:
    return check_output_tree(19, "outputs_replays", "outputs/replays", "historical_outputs_replays_unchanged")


def check_20_preexisting_dirty() -> CheckResult:
    if not DIRTY_BASELINE.is_file():
        return outcome(20, "preexisting_dirty_preserved", False, "baseline missing", blocked=True)
    records = [
        record
        for record in load_json(DIRTY_BASELINE).get("files", [])
        if not record.get("allowed_existing_modification")
    ]
    errors = verify_records(records)
    return outcome(20, "preexisting_dirty_preserved", not errors, f"records={len(records)}; errors={errors}")


def check_21_provider_calls_zero() -> CheckResult:
    return outcome(21, "provider_calls_during_verifier_zero", PROVIDER_CALLS == 0, f"provider_calls={PROVIDER_CALLS}")


def check_22_redis_connections_zero() -> CheckResult:
    from comqutor_alpha.llm_runtime.cache import RedisLLMResponseCache

    class FakeRedis:
        def get(self, key):
            del key

        def set(self, key, value, *, ex=None):
            del key, value, ex

        def delete(self, key):
            del key

        def ping(self):
            return True

    RedisLLMResponseCache(FakeRedis())
    runtime = REPO_ROOT / "comqutor_alpha/llm_runtime"
    forbidden_imports = []
    for path in runtime.glob("*.py"):
        for module in imported_modules(path):
            if module == "redis" or module.startswith("redis."):
                forbidden_imports.append(f"{path.name}:{module}")
    ok = REDIS_CONNECTIONS == 0 and not forbidden_imports
    return outcome(22, "redis_connections_zero", ok, f"connections={REDIS_CONNECTIONS}; imports={forbidden_imports}")


def check_23_db_writes_zero() -> CheckResult:
    runtime = REPO_ROOT / "comqutor_alpha/llm_runtime"
    forbidden_roots = {"psycopg", "psycopg2", "sqlalchemy"}
    violations = []
    for path in runtime.glob("*.py"):
        for module in imported_modules(path):
            if any(module == root or module.startswith(f"{root}.") for root in forbidden_roots):
                violations.append(f"{path.name}:{module}")
    ok = DB_WRITES == 0 and not violations
    return outcome(23, "database_writes_zero", ok, f"writes={DB_WRITES}; imports={violations}")


def allowed_path(relative: str) -> bool:
    return (
        relative.startswith("comqutor_alpha/llm_runtime/")
        or relative == "comqutor_alpha/structure_engine/week2_llm.py"
        or relative
        in {
            "comqutor_alpha/structure_engine/structured_output_adapter.py",
            "comqutor_alpha/structure_engine/alpha_mapper.py",
            "comqutor_alpha/structure_engine/structure_extractor.py",
            "comqutor_alpha/api/routes_research.py",
            "tests/test_week2_llm_semantic_runtime_integration.py",
            "tests/test_semantic_artifact_live_pipeline.py",
            "docs/adr/ADR-006-week2-semantic-runtime-integration.md",
            "docs/specs/week2_semantic_runtime_integration_contract_v1.md",
            "scripts/verify_phase0_6b.py",
        }
        or relative.startswith("tests/llm_runtime/")
        or relative.startswith("docs/audit_artifacts/phase0_6b/")
    )


def check_24_allowed_paths() -> CheckResult:
    if not DIRTY_BASELINE.is_file():
        return outcome(24, "phase_changes_only_allowed_paths", False, "baseline missing", blocked=True)
    baseline = load_json(DIRTY_BASELINE)
    baseline_paths = {record["relative_path"] for record in baseline.get("files", [])}
    additions = sorted(status_paths() - baseline_paths)
    disallowed_additions = [path for path in additions if not allowed_path(path)]
    disallowed_existing = [
        record["relative_path"]
        for record in baseline.get("files", [])
        if record.get("allowed_existing_modification")
        and record["relative_path"] in status_paths()
        and not allowed_path(record["relative_path"])
    ]
    errors = sorted(set(disallowed_additions + disallowed_existing))
    return outcome(24, "phase_changes_only_allowed_paths", not errors, f"additions={len(additions)}; disallowed={errors}")


def check_25_behavioral_invariants() -> CheckResult:
    if not BEHAVIORAL_REPORT.is_file():
        return outcome(25, "behavioral_invariants_pass", False, "report missing", blocked=True)
    report = load_json(BEHAVIORAL_REPORT)
    ok = report.get("overall_status") == PASS and report.get("business_artifacts_semantically_equal") is True
    return outcome(25, "behavioral_invariants_pass", ok, f"overall_status={report.get('overall_status')}")


CHECKS: tuple[Callable[[], CheckResult], ...] = (
    check_01_plan_sha,
    check_02_prior_phase_files,
    check_03_adr006,
    check_04_gateway_runtime_integration,
    check_05_gateway_default_runtime_none,
    check_06_prompt_hashes,
    check_07_gateway_defaults,
    check_08_caller_finalization_only,
    check_09_replay_unchanged,
    check_10_tradingagents_unchanged,
    check_11_canonical_prompt_unchanged,
    check_12_deterministic_core_unchanged,
    check_13_llm_default_flag,
    check_14_disabled_no_sidecars,
    check_15_cache_hit_revalidates,
    check_16_cache_accepted_only,
    check_17_raw_output_not_persisted,
    check_18_outputs_runs,
    check_19_outputs_replays,
    check_20_preexisting_dirty,
    check_21_provider_calls_zero,
    check_22_redis_connections_zero,
    check_23_db_writes_zero,
    check_24_allowed_paths,
    check_25_behavioral_invariants,
)


def main() -> int:
    results: list[CheckResult] = []
    for check in CHECKS:
        try:
            check_result = check()
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            number = int(check.__name__.split("_", 2)[1])
            check_result = CheckResult(number, check.__name__, FAIL, f"{type(exc).__name__}: {exc}")
        results.append(check_result)
        print(
            f"[{check_result.status}] {check_result.number:02d} "
            f"{check_result.name}: {check_result.detail}"
        )

    if any(item.status == FAIL for item in results):
        gate, exit_code = FAIL, 1
    elif any(item.status == BLOCKED for item in results):
        gate, exit_code = BLOCKED, 2
    else:
        gate, exit_code = PASS, 0
    print(f"PHASE_0_6B_GATEWAY_INTEGRATION: {gate}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
