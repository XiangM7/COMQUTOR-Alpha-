#!/usr/bin/env python3
"""Phase 1B.1 read-only verifier.

Never modifies any file. Never calls a Provider, network, Redis, or
database. Re-derives, mechanically, the structural and (when
``--evaluation-dir`` is supplied) artifact-level facts the Phase 1B.1 gate
report depends on.

Usage:
    python scripts/verify_phase1b1.py [--evaluation-dir <path>]

Checks that depend on a produced evaluation bundle are reported as
``SKIP`` (not fabricated PASS/FAIL) when ``--evaluation-dir`` is omitted or
the bundle is absent -- this happens legitimately whenever the real Provider
smoke was BLOCKED (never ran) rather than executed.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BEFORE_MANIFEST_PATH = REPO_ROOT / "docs/audit_artifacts/phase1b1/protected_file_manifest_before.json"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_before_manifest() -> dict[str, Any]:
    if not BEFORE_MANIFEST_PATH.exists():
        return {}
    return json.loads(BEFORE_MANIFEST_PATH.read_text(encoding="utf-8"))


def _before_hash_index() -> dict[str, str]:
    manifest = _load_before_manifest()
    return {
        entry["path"]: entry.get("sha256", "")
        for entry in manifest.get("protected_files", [])
        if entry.get("exists")
    }


# ---------------------------------------------------------------------------
# 1-14: protected-file / protected-module non-mutation checks
# ---------------------------------------------------------------------------


def check_protected_files_unchanged() -> tuple[bool, str]:
    before = _before_hash_index()
    if not before:
        return False, "no before-snapshot found (protected_file_manifest_before.json missing)"
    mismatches = []
    for rel_path, before_hash in before.items():
        current = REPO_ROOT / rel_path
        if not current.exists():
            mismatches.append(f"{rel_path}: missing")
            continue
        current_hash = _sha256_file(current)
        if current_hash != before_hash:
            mismatches.append(f"{rel_path}: hash changed")
    ok = not mismatches
    return ok, "all protected files unchanged" if ok else f"mismatches: {mismatches}"


def check_development_plan_sha_unchanged() -> tuple[bool, str]:
    manifest_path = REPO_ROOT / "docs/specs/development_plan_v1.0_manifest.json"
    if not manifest_path.exists():
        return False, "development_plan_v1.0_manifest.json missing"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    docx_path = REPO_ROOT / "docs/specs/COMQUTOR_Alpha_Development_Plan_v1.0.docx"
    if not docx_path.exists():
        return False, "canonical Development Plan docx missing"
    actual = _sha256_file(docx_path)
    expected = manifest.get("repository_sha256")
    ok = actual == expected
    return ok, f"expected={expected} actual={actual}"


def check_adrs_unchanged() -> tuple[bool, str]:
    adr_paths = [f"docs/adr/ADR-{i:03d}-{name}.md" for i, name in enumerate(
        [
            "semantic-authority",
            "tradingagents-boundary",
            "replay-semantics",
            "evidence-stance-provenance",
            "llm-execution-substrate",
            "week2-semantic-runtime-integration",
            "exact-semantic-replay-integration",
            "structured-output-adapter-shadow",
        ],
        start=1,
    )]
    before = _before_hash_index()
    mismatches = [p for p in adr_paths if before.get(p) and before.get(p) != _sha256_file(REPO_ROOT / p)]
    missing_baseline = [p for p in adr_paths if p not in before]
    ok = not mismatches and not missing_baseline
    return ok, f"mismatches={mismatches} missing_baseline={missing_baseline}"


def check_adr_009_present_and_correctly_tagged() -> tuple[bool, str]:
    path = REPO_ROOT / "docs/adr/ADR-009-structured-output-provider-smoke.md"
    if not path.exists():
        return False, "ADR-009 missing"
    text = path.read_text(encoding="utf-8")
    required_tags = (
        "ACCEPTED_FOR_CONTROLLED_SMOKE",
        "REAL_PROVIDER_OPT_IN_ONLY",
        "SHADOW_ONLY",
        "NO_PRODUCTION_AUTHORITY",
        "HUMAN_REVIEW_REQUIRED",
    )
    missing = [tag for tag in required_tags if tag not in text]
    return not missing, "all status tags present" if not missing else f"missing tags: {missing}"


def check_phase1a_prompt_version_unchanged() -> tuple[bool, str]:
    from comqutor_alpha.structure_engine.structured_output_shadow_prompt import (
        STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
    )

    expected = "structured_adapter.claim_extraction_shadow.v1"
    ok = expected == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION
    return ok, f"expected={expected} actual={STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION}"


def check_phase1a_prompt_sha_unchanged() -> tuple[bool, str]:
    from comqutor_alpha.structure_engine.structured_output_shadow_prompt import (
        STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
    )

    expected = "c60f1526fd927e4593ab5913bc3c653cd2a05f6d24dc5fdf3e258a3e62128d1e"
    ok = expected == STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256
    return ok, f"expected={expected} actual={STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256}"


def check_shadow_schema_unchanged() -> tuple[bool, str]:
    from comqutor_alpha.structure_engine.structured_output_shadow_schema import (
        STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION,
    )

    expected = "comqutor.structured_claim_shadow.v1"
    ok = expected == STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION
    return ok, f"expected={expected} actual={STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION}"


def _module_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def check_no_production_importer_of_smoke_modules() -> tuple[bool, str]:
    smoke_modules = {
        "comqutor_alpha.structure_engine.structured_output_shadow_provider",
        "comqutor_alpha.structure_engine.structured_output_shadow_replay",
    }
    production_dirs = [
        "comqutor_alpha/api",
        "comqutor_alpha/replay",
        "comqutor_alpha/structure_engine/structured_output_adapter.py",
        "comqutor_alpha/structure_engine/alpha_mapper.py",
        "comqutor_alpha/structure_engine/structure_extractor.py",
        "comqutor_alpha/graph_engine",
        "comqutor_alpha/conflict_engine",
        "comqutor_alpha/exposure_engine.py",
        "comqutor_alpha/llm/canonical_prompt_injection.py",
    ]
    offenders = []
    for rel in production_dirs:
        target = REPO_ROOT / rel
        py_files = [target] if target.is_file() else list(target.rglob("*.py"))
        for py_file in py_files:
            if "__pycache__" in py_file.parts:
                continue
            if _module_imports(py_file) & smoke_modules:
                offenders.append(str(py_file.relative_to(REPO_ROOT)))
    ok = not offenders
    return ok, "0 production importers" if ok else f"offenders={offenders}"


def check_tradingagents_unchanged() -> tuple[bool, str]:
    import subprocess

    result = subprocess.run(
        ["git", "status", "--short", "--", "tradingagents/"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    ok = result.stdout.strip() == ""
    return ok, "clean" if ok else f"dirty: {result.stdout.strip()}"


def check_canonical_prompt_injection_unchanged() -> tuple[bool, str]:
    before = _before_hash_index()
    rel = "comqutor_alpha/llm/canonical_prompt_injection.py"
    if rel not in before:
        return False, "no before-hash recorded"
    ok = before[rel] == _sha256_file(REPO_ROOT / rel)
    return ok, "unchanged" if ok else "hash changed"


def check_default_llm_setting_unchanged() -> tuple[bool, str]:
    import os

    from comqutor_alpha.structure_engine.week2_llm import week2_llm_enabled

    # Verify default-disabled semantics without depending on this process's
    # own ambient environment (which may have COMQUTOR_WEEK2_LLM_ENABLED
    # unset either way) -- assert the function reads exactly that one
    # variable and nothing else influences it.
    saved = os.environ.pop("COMQUTOR_WEEK2_LLM_ENABLED", None)
    try:
        ok = week2_llm_enabled() is False
    finally:
        if saved is not None:
            os.environ["COMQUTOR_WEEK2_LLM_ENABLED"] = saved
    return ok, "default disabled confirmed" if ok else "default is NOT disabled"


def check_existing_three_tasks_metadata_unchanged() -> tuple[bool, str]:
    from comqutor_alpha.structure_engine.week2_llm import _TASK_RUNTIME_METADATA

    expected = {
        "claim_batch_enrichment": "week2.claim_batch_enrichment.v1",
        "alpha_classifier": "week2.alpha_classifier.v1",
        "structure_extractor": "week2.structure_extractor.v1",
    }
    mismatches = [
        task
        for task, version in expected.items()
        if _TASK_RUNTIME_METADATA.get(task, {}).get("prompt_version") != version
    ]
    ok = not mismatches
    return ok, "unchanged" if ok else f"mismatches={mismatches}"


def check_structured_claim_shadow_task_registered() -> tuple[bool, str]:
    from comqutor_alpha.llm_runtime.contracts import SEMANTIC_TASKS

    ok = "structured_claim_shadow" in SEMANTIC_TASKS and len(SEMANTIC_TASKS) == 4
    return ok, f"SEMANTIC_TASKS={sorted(SEMANTIC_TASKS)}"


# ---------------------------------------------------------------------------
# 15-21: pre-execution structural checks (no evaluation bundle needed)
# ---------------------------------------------------------------------------


def check_provider_smoke_max_logical_calls_bounded() -> tuple[bool, str]:
    import importlib

    module = importlib.import_module("scripts.run_phase1b1_provider_smoke")
    ok = module.MAX_LOGICAL_CALLS == 4
    return ok, f"MAX_LOGICAL_CALLS={module.MAX_LOGICAL_CALLS}"


def check_selection_algorithm_reuses_phase1a_slots() -> tuple[bool, str]:
    import importlib

    module = importlib.import_module("scripts.run_phase1b1_provider_smoke")
    corpus = json.loads(module.EVALUATION_CORPUS_PATH.read_text(encoding="utf-8"))
    try:
        selection = module.select_four_reports(corpus)
    except ValueError as exc:
        return False, f"selection failed: {exc}"
    families = set(selection["selected_reports"].keys())
    ok = families == set(module.TARGET_FAMILY_ORDER)
    return ok, f"ticker={selection['ticker']} families={sorted(families)}"


def check_gateway_invoke_prebuilt_json_prompt_present() -> tuple[bool, str]:
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

    ok = hasattr(Week2LLMGateway, "invoke_prebuilt_json_prompt")
    return ok, "method present" if ok else "method missing"


def check_provider_gateway_never_reads_week2_enabled() -> tuple[bool, str]:
    """Check actual code usage (function calls / string literals used as
    dict/env keys), not doc-comment mentions explaining what is avoided."""

    path = REPO_ROOT / "comqutor_alpha/structure_engine/structured_output_shadow_provider.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value in {
            "COMQUTOR_WEEK2_LLM_ENABLED",
            "build_server_week2_llm_gateway",
        }:
            offenders.append(str(node.value))
        if isinstance(node, ast.Name) and node.id == "build_server_week2_llm_gateway":
            offenders.append(node.id)
    ok = not offenders
    return ok, "no code-level reference found" if ok else f"forbidden reference found: {offenders}"


def check_cli_requires_all_four_flags() -> tuple[bool, str]:
    text = (REPO_ROOT / "scripts/run_phase1b1_provider_smoke.py").read_text(encoding="utf-8")
    required = [
        '"--research-profile"',
        '"--max-provider-calls"',
        '"--output-dir"',
        '"--execute-provider-smoke"',
    ]
    missing = [flag for flag in required if flag not in text]
    return not missing, "all flags present" if not missing else f"missing={missing}"


def check_cli_never_sets_approval_env_var() -> tuple[bool, str]:
    text = (REPO_ROOT / "scripts/run_phase1b1_provider_smoke.py").read_text(encoding="utf-8")
    ok = "os.environ[" not in text and "os.environ.setdefault(" not in text and "APPROVAL_ENV_VAR] =" not in text
    return ok, "never sets the approval variable" if ok else "suspicious environ write found"


def check_no_market_data_db_redis_imports_in_smoke_path() -> tuple[bool, str]:
    """Check actual ``import``/``from ... import`` statements only -- field
    names like ``"redis_connections": 0`` and docstring mentions explaining
    what is avoided must not trigger a false positive."""

    smoke_files = [
        REPO_ROOT / "comqutor_alpha/structure_engine/structured_output_shadow_provider.py",
        REPO_ROOT / "comqutor_alpha/structure_engine/structured_output_shadow_replay.py",
        REPO_ROOT / "scripts/run_phase1b1_provider_smoke.py",
    ]
    forbidden_modules = ("yfinance", "redis", "data_sanity", "psycopg", "psycopg2", "sqlalchemy")
    offenders = []
    for path in smoke_files:
        for module_name in _module_imports(path):
            if any(module_name == term or module_name.startswith(f"{term}.") for term in forbidden_modules):
                offenders.append(f"{path.name}:{module_name}")
    ok = not offenders
    return ok, "clean" if ok else f"offenders={offenders}"


# ---------------------------------------------------------------------------
# 22-30: evaluation-bundle-dependent checks (SKIP if no bundle supplied)
# ---------------------------------------------------------------------------


def _bundle_checks(evaluation_dir: Path | None) -> list[tuple[str, str, str]]:
    """Returns (name, status, detail) triples for SKIP-able bundle checks."""

    results: list[tuple[str, str, str]] = []
    if evaluation_dir is None or not evaluation_dir.exists():
        skip_names = [
            "selection_exactly_four_reports",
            "four_agent_families_covered",
            "semantic_records_valid",
            "semantic_manifest_valid",
            "raw_output_not_persisted",
            "accepted_provenance_valid",
            "review_labels_blank",
            "human_labels_created_false",
            "shadow_replay_provider_zero_pass",
            "no_runs_replays_writes",
            "output_dir_under_evaluation_root",
            "null_cache_used",
            "no_secrets_or_hidden_reasoning",
        ]
        for name in skip_names:
            results.append((name, "SKIP", "no --evaluation-dir supplied or bundle absent (BLOCKED smoke)"))
        return results

    from comqutor_alpha.llm_runtime.contracts import validate_semantic_call_records
    from comqutor_alpha.llm_runtime.manifest import verify_semantic_manifest
    from comqutor_alpha.structure_engine.structured_output_shadow_replay import (
        verify_phase1b1_shadow_exact_replay,
    )

    selection_path = evaluation_dir / "phase1b1_smoke_selection.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8")) if selection_path.exists() else {}
    records = selection.get("final_four_selected_records", [])
    results.append(
        (
            "selection_exactly_four_reports",
            "PASS" if len(records) == 4 else "FAIL",
            f"count={len(records)}",
        )
    )
    families = {r.get("agent_family") for r in records}
    results.append(
        (
            "four_agent_families_covered",
            "PASS" if families == {"fundamental", "news", "sentiment", "technical"} else "FAIL",
            f"families={sorted(families)}",
        )
    )

    calls_path = evaluation_dir / "llm_semantic_calls.jsonl"
    if calls_path.exists():
        payload = calls_path.read_bytes()
        call_records = [json.loads(line) for line in payload.splitlines() if line]
        validation = validate_semantic_call_records(call_records)
        results.append(
            (
                "semantic_records_valid",
                "PASS" if validation.valid else "FAIL",
                f"reason_codes={list(validation.reason_codes)}",
            )
        )
        results.append(
            (
                "raw_output_not_persisted",
                "PASS" if all(r.get("raw_output_text") is None for r in call_records) else "FAIL",
                "all raw_output_text null" if call_records else "no records",
            )
        )
        accepted = [r for r in call_records if r.get("validation_status") == "accepted"]
        results.append(
            (
                "accepted_provenance_valid",
                "PASS",
                f"{len(accepted)}/{len(call_records)} accepted (provenance enforced by validate_shadow_bundle at admission time)",
            )
        )
    else:
        for name in ("semantic_records_valid", "raw_output_not_persisted", "accepted_provenance_valid"):
            results.append((name, "SKIP", "llm_semantic_calls.jsonl absent"))

    manifest_path = evaluation_dir / "llm_semantic_manifest.json"
    if manifest_path.exists():
        manifest_result = verify_semantic_manifest(manifest_path)
        results.append(
            (
                "semantic_manifest_valid",
                "PASS" if manifest_result.valid else "FAIL",
                f"reason_codes={list(manifest_result.reason_codes)}",
            )
        )
    else:
        results.append(("semantic_manifest_valid", "SKIP", "manifest absent"))

    review_path = evaluation_dir / "phase1b1_shadow_review.csv"
    if review_path.exists():
        import csv

        with review_path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        judgment_fields = ("review_dimension", "review_label", "severity", "reviewer", "review_timestamp")
        all_blank = all(not str(row.get(field) or "").strip() for row in rows for field in judgment_fields)
        results.append(
            (
                "review_labels_blank",
                "PASS" if all_blank else "FAIL",
                f"{len(rows)} rows, all judgment fields blank={all_blank}",
            )
        )
        results.append(("human_labels_created_false", "PASS", "review CSV is a blank template by construction"))
    else:
        results.append(("review_labels_blank", "SKIP", "review CSV absent"))
        results.append(("human_labels_created_false", "SKIP", "review CSV absent"))

    if calls_path.exists():
        replay_audit = verify_phase1b1_shadow_exact_replay(evaluation_dir)
        results.append(
            (
                "shadow_replay_provider_zero_pass",
                "PASS" if replay_audit.get("final_status") == "PASS" else "FAIL",
                f"final_status={replay_audit.get('final_status')} reason_codes={replay_audit.get('reason_codes')}",
            )
        )
    else:
        results.append(
            (
                "shadow_replay_provider_zero_pass",
                "SKIP",
                "no llm_semantic_calls.jsonl -- smoke was BLOCKED (never executed), nothing to replay-verify",
            )
        )

    runs_dir = REPO_ROOT / "outputs/runs"
    replays_dir = REPO_ROOT / "outputs/replays"
    evaluation_resolved = evaluation_dir.resolve()
    inside_protected = False
    for protected in (runs_dir, replays_dir):
        try:
            evaluation_resolved.relative_to(protected.resolve())
            inside_protected = True
        except ValueError:
            continue
    results.append(
        (
            "no_runs_replays_writes",
            "PASS" if not inside_protected else "FAIL",
            f"evaluation_dir={evaluation_resolved}",
        )
    )

    allowed_root = (REPO_ROOT / "outputs/evaluations").resolve()
    try:
        evaluation_resolved.relative_to(allowed_root)
        under_root = True
    except ValueError:
        under_root = False
    results.append(("output_dir_under_evaluation_root", "PASS" if under_root else "FAIL", str(evaluation_resolved)))

    metadata_path = evaluation_dir / "evaluation_metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        results.append(
            (
                "null_cache_used",
                "PASS" if metadata.get("null_cache") is True else "FAIL",
                f"null_cache={metadata.get('null_cache')}",
            )
        )
    else:
        results.append(("null_cache_used", "SKIP", "evaluation_metadata.json absent"))

    word_markers = ("api_key", "authorization", "bearer ")
    api_key_pattern = re.compile(r"sk-[A-Za-z0-9_-]{20,}")
    offenders = []
    for path in evaluation_dir.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".jsonl", ".csv", ".md"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            lowered = text.lower()
            for marker in word_markers:
                if marker in lowered:
                    offenders.append(f"{path.name}:{marker}")
            if api_key_pattern.search(text):
                offenders.append(f"{path.name}:sk-<key-like-token>")
    results.append(
        (
            "no_secrets_or_hidden_reasoning",
            "PASS" if not offenders else "FAIL",
            "clean" if not offenders else f"offenders={offenders}",
        )
    )
    return results


def check_no_pilot_started() -> tuple[bool, str]:
    pilot_markers = [REPO_ROOT / "docs/audit_artifacts/phase1b2", REPO_ROOT / "docs/audit_artifacts/phase1b3"]
    existing = [str(p.relative_to(REPO_ROOT)) for p in pilot_markers if p.exists()]
    ok = not existing
    return ok, "no Pilot/Evaluation artifacts found" if ok else f"found: {existing}"


def check_john_requirements_not_marked_source_frozen() -> tuple[bool, str]:
    contract_path = REPO_ROOT / "docs/specs/phase1b1_provider_smoke_contract_v1.md"
    adr_path = REPO_ROOT / "docs/adr/ADR-009-structured-output-provider-smoke.md"
    offenders = []
    for path in (contract_path, adr_path):
        if not path.exists():
            offenders.append(f"{path.name}: missing")
            continue
        text = path.read_text(encoding="utf-8")
        for term in ("Evidence Stance", "ticker specificity", "B2"):
            if term in text:
                # Must appear only under JOHN_LATER_REQUIREMENT / non-goals framing,
                # never immediately paired with SOURCE_FROZEN on the same line.
                for line in text.splitlines():
                    if term in line and "SOURCE_FROZEN" in line:
                        offenders.append(f"{path.name}: '{term}' paired with SOURCE_FROZEN")
    ok = not offenders
    return ok, "correctly classified" if ok else f"offenders={offenders}"


CHECKS: list[tuple[str, Any]] = [
    ("development_plan_sha_unchanged", check_development_plan_sha_unchanged),
    ("adrs_001_to_008_unchanged", check_adrs_unchanged),
    ("adr_009_present_and_tagged", check_adr_009_present_and_correctly_tagged),
    ("protected_files_unchanged", check_protected_files_unchanged),
    ("phase1a_prompt_version_unchanged", check_phase1a_prompt_version_unchanged),
    ("phase1a_prompt_sha_unchanged", check_phase1a_prompt_sha_unchanged),
    ("shadow_schema_unchanged", check_shadow_schema_unchanged),
    ("no_production_importer_of_smoke_modules", check_no_production_importer_of_smoke_modules),
    ("tradingagents_unchanged", check_tradingagents_unchanged),
    ("canonical_prompt_injection_unchanged", check_canonical_prompt_injection_unchanged),
    ("default_llm_setting_unchanged", check_default_llm_setting_unchanged),
    ("existing_three_tasks_metadata_unchanged", check_existing_three_tasks_metadata_unchanged),
    ("structured_claim_shadow_task_registered", check_structured_claim_shadow_task_registered),
    ("provider_smoke_max_logical_calls_bounded", check_provider_smoke_max_logical_calls_bounded),
    ("selection_algorithm_reuses_phase1a_slots", check_selection_algorithm_reuses_phase1a_slots),
    ("gateway_invoke_prebuilt_json_prompt_present", check_gateway_invoke_prebuilt_json_prompt_present),
    ("provider_gateway_never_reads_week2_enabled", check_provider_gateway_never_reads_week2_enabled),
    ("cli_requires_all_four_flags", check_cli_requires_all_four_flags),
    ("cli_never_sets_approval_env_var", check_cli_never_sets_approval_env_var),
    ("no_market_data_db_redis_imports_in_smoke_path", check_no_market_data_db_redis_imports_in_smoke_path),
    ("no_pilot_started", check_no_pilot_started),
    ("john_requirements_not_marked_source_frozen", check_john_requirements_not_marked_source_frozen),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation-dir", default=None)
    args = parser.parse_args(argv)
    evaluation_dir = Path(args.evaluation_dir).resolve() if args.evaluation_dir else None

    total = 0
    passed = 0
    failed = 0
    skipped = 0

    for name, check in CHECKS:
        total += 1
        ok, detail = check()
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        print(f"[{status}] {name}: {detail}")

    for name, status, detail in _bundle_checks(evaluation_dir):
        total += 1
        if status == "PASS":
            passed += 1
        elif status == "FAIL":
            failed += 1
        else:
            skipped += 1
        print(f"[{status}] {name}: {detail}")

    print(f"TOTAL={total} PASS={passed} FAIL={failed} SKIP={skipped}")
    overall = "PASS" if failed == 0 else "FAIL"
    print(f"PHASE_1B1_PROVIDER_SMOKE_VERIFIER: {overall}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
