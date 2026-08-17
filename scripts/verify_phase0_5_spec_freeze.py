"""Read-only verification for the Phase 0.5 specification freeze.

The verifier imports no production module, performs no network/Provider/DB
operation, and writes no file. It compares the current repository with the
Phase 0.5 start baselines and prints one terminal gate:

    PHASE_0_5_SPEC_FREEZE: PASS | BLOCKED | FAIL

Run from any directory with ``python scripts/verify_phase0_5_spec_freeze.py``.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = REPO_ROOT / "docs/audit_artifacts/phase0_5"
MANIFEST_PATH = REPO_ROOT / "docs/specs/development_plan_v1.0_manifest.json"
CANONICAL_PLAN_PATH = REPO_ROOT / "docs/specs/COMQUTOR_Alpha_Development_Plan_v1.0.docx"
START_SNAPSHOT_PATH = PHASE_DIR / "worktree_start_snapshot.json"
DIRTY_MANIFEST_PATH = PHASE_DIR / "preexisting_dirty_file_manifest.json"
PHASE0_HASHES_PATH = PHASE_DIR / "phase0_original_file_hashes.json"
SOURCE_BEFORE_PATH = PHASE_DIR / "source_artifact_integrity_before.json"
SOURCE_AFTER_PATH = PHASE_DIR / "source_artifact_integrity_after.json"

PASS = "PASS"
BLOCKED = "BLOCKED"
FAIL = "FAIL"

ADR_REQUIREMENTS = {
    "docs/adr/ADR-001-semantic-authority.md": (
        "Status:",
        "ACCEPTED_FOR_FUTURE_IMPLEMENTATION",
        "NOT_YET_ENFORCED_IN_PRODUCTION",
    ),
    "docs/adr/ADR-002-tradingagents-boundary.md": (
        "Status:",
        "ACCEPTED_FOR_FUTURE_IMPLEMENTATION",
        "CURRENT_CODE_DIVERGES",
        "RUNTIME_CHANGE_DEFERRED",
    ),
    "docs/adr/ADR-003-replay-semantics.md": (
        "Status:",
        "ACCEPTED_FOR_FUTURE_IMPLEMENTATION",
        "CURRENT_REPLAY_PARTIAL",
    ),
    "docs/adr/ADR-004-evidence-stance-provenance.md": (
        "Status:",
        "RECORDED",
        "NO_PRODUCTION_AUTHORITY",
    ),
}

REQUIRED_OUTPUTS = (
    "docs/specs/COMQUTOR_Alpha_Development_Plan_v1.0.docx",
    "docs/specs/development_plan_v1.0_manifest.json",
    "docs/specs/development_plan_v1.0_reference_index.md",
    "docs/specs/README.md",
    "docs/specs/semantic_authority_matrix.csv",
    "docs/specs/current_vs_target_semantic_architecture.md",
    "docs/specs/future_semantic_phase_contract.md",
    "docs/specs/product_decisions_and_unknowns.md",
    *ADR_REQUIREMENTS,
    "docs/development_plan_llm_boundary_audit_reconciliation.md",
    "docs/audit_artifacts/phase0_5/worktree_start_snapshot.json",
    "docs/audit_artifacts/phase0_5/preexisting_dirty_file_manifest.json",
    "docs/audit_artifacts/phase0_5/reconciled_compliance_matrix.csv",
    "docs/audit_artifacts/phase0_5/phase0_original_file_hashes.json",
    "docs/audit_artifacts/phase0_5/source_artifact_integrity_before.json",
    "docs/audit_artifacts/phase0_5/source_artifact_integrity_after.json",
    "docs/audit_artifacts/phase0_5/phase0_5_gate_report.json",
    "docs/audit_artifacts/phase0_5/phase0_5_completion_report.md",
    "scripts/verify_phase0_5_spec_freeze.py",
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str


def _result(name: str, ok: bool, detail: str, *, blocked: bool = False) -> CheckResult:
    return CheckResult(name, PASS if ok else (BLOCKED if blocked else FAIL), detail)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path.relative_to(REPO_ROOT)}")
    return value


def _git_status_paths() -> set[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "-uall"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    paths: set[str] = set()
    for line in result.stdout.splitlines():
        value = line[3:]
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        paths.add(value)
    return paths


def _tree_records(relative_dir: str) -> list[dict[str, Any]]:
    directory = REPO_ROOT / relative_dir
    records = []
    if directory.is_dir():
        for path in sorted(item for item in directory.rglob("*") if item.is_file()):
            stat = path.stat()
            records.append(
                {
                    "relative_path": path.relative_to(REPO_ROOT).as_posix(),
                    "size_bytes": stat.st_size,
                    "sha256": _sha256(path),
                    "mtime_ns": stat.st_mtime_ns,
                }
            )
    return records


def _normalized_tree(tree: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "relative_path": item["relative_path"],
            "size_bytes": item["size_bytes"],
            "sha256": item["sha256"],
            "mtime_ns": item["mtime_ns"],
        }
        for item in tree.get("files", [])
    ]


def check_canonical_plan_exists() -> CheckResult:
    exists = CANONICAL_PLAN_PATH.is_file()
    return _result(
        "canonical_development_plan_exists",
        exists,
        str(CANONICAL_PLAN_PATH.relative_to(REPO_ROOT)),
        blocked=not exists,
    )


def check_manifest_sha() -> CheckResult:
    if not MANIFEST_PATH.is_file() or not CANONICAL_PLAN_PATH.is_file():
        return CheckResult("canonical_manifest_sha_matches", BLOCKED, "manifest or DOCX missing")
    manifest = _load_json(MANIFEST_PATH)
    actual = _sha256(CANONICAL_PLAN_PATH)
    expected = manifest.get("repository_sha256")
    source_expected = manifest.get("source_sha256")
    ok = bool(actual == expected == source_expected)
    return _result(
        "canonical_manifest_sha_matches",
        ok,
        f"actual={actual}; repository_sha256={expected}; source_sha256={source_expected}",
    )


def check_manifest_byte_identical() -> CheckResult:
    if not MANIFEST_PATH.is_file():
        return CheckResult("manifest_byte_identical_true", BLOCKED, "manifest missing")
    manifest = _load_json(MANIFEST_PATH)
    source_path = Path(str(manifest.get("source_path", "")))
    repository_hash = _sha256(CANONICAL_PLAN_PATH) if CANONICAL_PLAN_PATH.is_file() else None
    source_hash = _sha256(source_path) if source_path.is_file() else None
    ok = bool(
        manifest.get("byte_identical") is True
        and manifest.get("content_modified") is False
        and manifest.get("canonical") is True
        and repository_hash == source_hash == manifest.get("source_sha256")
    )
    detail = f"flag={manifest.get('byte_identical')}; source_available={source_path.is_file()}"
    return _result("manifest_byte_identical_true", ok, detail, blocked=source_hash is None)


def check_adrs_exist() -> CheckResult:
    missing = [path for path in ADR_REQUIREMENTS if not (REPO_ROOT / path).is_file()]
    return _result("adr_001_through_004_exist", not missing, f"missing={missing}")


def check_adr_statuses() -> CheckResult:
    errors = []
    for relative, tokens in ADR_REQUIREMENTS.items():
        path = REPO_ROOT / relative
        if not path.is_file():
            errors.append(f"{relative}: missing")
            continue
        text = path.read_text(encoding="utf-8")
        absent = [token for token in tokens if token not in text]
        if absent:
            errors.append(f"{relative}: absent={absent}")
    return _result("all_adrs_contain_required_status", not errors, f"errors={errors}")


def check_authority_matrix() -> CheckResult:
    path = REPO_ROOT / "docs/specs/semantic_authority_matrix.csv"
    return _result("semantic_authority_matrix_exists", path.is_file(), str(path.relative_to(REPO_ROOT)))


def check_current_and_target_architecture() -> CheckResult:
    path = REPO_ROOT / "docs/specs/current_vs_target_semantic_architecture.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    ok = "## CURRENT" in text and "## TARGET" in text
    return _result("architecture_has_current_and_target", ok, "CURRENT and TARGET headings required")


def check_reconciled_verdicts() -> CheckResult:
    path = PHASE_DIR / "reconciled_compliance_matrix.csv"
    if not path.is_file():
        return CheckResult("reconciled_verdicts", FAIL, "matrix missing")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = {row["requirement_id"]: row for row in csv.DictReader(handle, strict=True)}
    expected = {
        "DP-5.1": ("phase0_5_reconciled_status", "PARTIAL"),
        "DP-5.2": ("validation_status", "PRODUCT_VALIDATION_MISSING"),
        "DP-5.3-FUNCTION": ("functional_status", "PARTIAL"),
        "DP-5.3-INTEGRATION": ("integration_status", "DIVERGED_MAJOR"),
        "TA-BOUNDARY": ("phase0_5_reconciled_status", "CURRENT_IMPLEMENTATION_DIVERGED_MAJOR"),
        "REPLAY-SEMANTICS": ("phase0_5_reconciled_status", "PARTIAL"),
    }
    errors = []
    for row_id, (field, value) in expected.items():
        if rows.get(row_id, {}).get(field) != value:
            errors.append(f"{row_id}.{field}!={value}")
    dp51 = rows.get("DP-5.1", {})
    if dp51.get("validation_status") != "SEMANTIC_QUALITY_UNPROVEN":
        errors.append("DP-5.1.validation_status!=SEMANTIC_QUALITY_UNPROVEN")
    return _result("reconciled_verdicts", not errors, f"errors={errors}")


def check_phase0_hashes() -> CheckResult:
    if not PHASE0_HASHES_PATH.is_file():
        return CheckResult("original_phase0_hashes_unchanged", BLOCKED, "baseline missing")
    baseline = _load_json(PHASE0_HASHES_PATH)
    errors = []
    for record in baseline.get("files", []):
        path = REPO_ROOT / record["relative_path"]
        if not path.is_file():
            errors.append(f"missing:{record['relative_path']}")
        elif path.stat().st_size != record["size_bytes"] or _sha256(path) != record["sha256"]:
            errors.append(f"changed:{record['relative_path']}")
    if baseline.get("missing"):
        errors.append(f"baseline_missing={baseline['missing']}")
    return _result("original_phase0_hashes_unchanged", not errors, f"errors={errors}")


def check_preexisting_dirty_files() -> CheckResult:
    if not DIRTY_MANIFEST_PATH.is_file():
        return CheckResult("preexisting_dirty_worktree_preserved", BLOCKED, "baseline missing")
    baseline = _load_json(DIRTY_MANIFEST_PATH)
    errors = []
    for record in baseline.get("files", []):
        path = REPO_ROOT / record["relative_path"]
        if not path.is_file():
            errors.append(f"missing:{record['relative_path']}")
            continue
        stat = path.stat()
        if (
            stat.st_size != record["size_bytes"]
            or _sha256(path) != record["sha256"]
            or stat.st_mtime_ns != record["mtime_ns"]
        ):
            errors.append(f"changed:{record['relative_path']}")
    return _result("preexisting_dirty_worktree_preserved", not errors, f"errors={errors}")


def check_source_artifacts() -> CheckResult:
    if not SOURCE_BEFORE_PATH.is_file() or not SOURCE_AFTER_PATH.is_file():
        return CheckResult("outputs_runs_and_replays_unchanged", BLOCKED, "before/after proof missing")
    before = _load_json(SOURCE_BEFORE_PATH)
    after = _load_json(SOURCE_AFTER_PATH)
    errors = []
    for key, relative in (("outputs_runs", "outputs/runs"), ("outputs_replays", "outputs/replays")):
        before_records = _normalized_tree(before.get(key, {}))
        after_records = _normalized_tree(after.get(key, {}))
        current_records = _tree_records(relative)
        if before_records != after_records:
            errors.append(f"before_after_mismatch:{relative}")
        if before_records != current_records:
            errors.append(f"baseline_current_mismatch:{relative}")
    return _result("outputs_runs_and_replays_unchanged", not errors, f"errors={errors}")


def check_evidence_stance_provenance() -> CheckResult:
    paths = (
        REPO_ROOT / "docs/adr/ADR-004-evidence-stance-provenance.md",
        REPO_ROOT / "docs/development_plan_llm_boundary_audit_reconciliation.md",
    )
    ok = all(
        path.is_file()
        and "JOHN_LATER_REQUIREMENT" in path.read_text(encoding="utf-8")
        and "SHADOW" in path.read_text(encoding="utf-8")
        for path in paths
    )
    return _result("evidence_stance_provenance", ok, "JOHN_LATER_REQUIREMENT and SHADOW required")


def _check_protected_file(relative_path: str) -> tuple[bool, str]:
    if not START_SNAPSHOT_PATH.is_file():
        return False, "start snapshot missing"
    snapshot = _load_json(START_SNAPSHOT_PATH)
    records = {item["relative_path"]: item for item in snapshot.get("protected_runtime_files", [])}
    record = records.get(relative_path)
    path = REPO_ROOT / relative_path
    if not record or not path.is_file():
        return False, "baseline or file missing"
    stat = path.stat()
    ok = (
        stat.st_size == record["size_bytes"]
        and stat.st_mtime_ns == record["mtime_ns"]
        and _sha256(path) == record["sha256"]
    )
    return ok, f"sha256={_sha256(path)}; baseline={record['sha256']}"


def check_canonical_prompt_unchanged() -> CheckResult:
    paths = (
        "comqutor_alpha/llm/canonical_prompt_injection.py",
        "comqutor_alpha/structure_engine/canonical_relation_prompt.py",
    )
    details = []
    ok = True
    for relative in paths:
        item_ok, detail = _check_protected_file(relative)
        ok = ok and item_ok
        details.append(f"{relative}:{detail}")
    return _result("canonical_prompt_files_unchanged", ok, "; ".join(details))


def check_week2_default_unchanged() -> CheckResult:
    relative = "comqutor_alpha/structure_engine/week2_llm.py"
    hash_ok, hash_detail = _check_protected_file(relative)
    text = (REPO_ROOT / relative).read_text(encoding="utf-8")
    gate_ok = (
        'if not _enabled(os.environ.get("COMQUTOR_WEEK2_LLM_ENABLED")):' in text
        and "return None" in text
    )
    return _result(
        "week2_llm_default_unchanged",
        hash_ok and gate_ok,
        f"hash={hash_detail}; explicit_opt_in_gate={gate_ok}",
    )


def _allowed_phase_path(relative: str) -> bool:
    return (
        relative.startswith("docs/specs/")
        or relative.startswith("docs/adr/")
        or relative.startswith("docs/audit_artifacts/phase0_5/")
        or relative == "docs/development_plan_llm_boundary_audit_reconciliation.md"
        or relative == "scripts/verify_phase0_5_spec_freeze.py"
        or relative.startswith("tests/audit/")
    )


def check_allowed_paths_only() -> CheckResult:
    if not DIRTY_MANIFEST_PATH.is_file():
        return CheckResult("phase0_5_changes_only_allowed_paths", BLOCKED, "dirty baseline missing")
    baseline = _load_json(DIRTY_MANIFEST_PATH)
    preexisting = {record["relative_path"] for record in baseline.get("files", [])}
    additions = sorted(_git_status_paths() - preexisting)
    disallowed = [path for path in additions if not _allowed_phase_path(path)]
    return _result(
        "phase0_5_changes_only_allowed_paths",
        not disallowed,
        f"phase_additions={len(additions)}; disallowed={disallowed}",
    )


def check_required_outputs() -> CheckResult:
    missing = [relative for relative in REQUIRED_OUTPUTS if not (REPO_ROOT / relative).is_file()]
    return _result("required_outputs_exist", not missing, f"missing={missing}")


def check_json_and_csv() -> CheckResult:
    errors = []
    json_paths = sorted((REPO_ROOT / "docs/specs").glob("*.json")) + sorted(PHASE_DIR.glob("*.json"))
    for path in json_paths:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"json:{path.relative_to(REPO_ROOT)}:{exc}")
    csv_paths = (
        REPO_ROOT / "docs/specs/semantic_authority_matrix.csv",
        PHASE_DIR / "reconciled_compliance_matrix.csv",
    )
    for path in csv_paths:
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle, strict=True))
            width = len(rows[0]) if rows else 0
            if not rows or width == 0 or any(len(row) != width for row in rows):
                errors.append(f"csv:{path.relative_to(REPO_ROOT)}:non_uniform_rows")
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            errors.append(f"csv:{path.relative_to(REPO_ROOT)}:{exc}")
    return _result("phase0_5_json_and_csv_valid", not errors, f"errors={errors}")


def check_internal_references() -> CheckResult:
    references = (
        "docs/specs/development_plan_v1.0_manifest.json",
        "docs/specs/development_plan_v1.0_reference_index.md",
        "docs/specs/semantic_authority_matrix.csv",
        "docs/specs/current_vs_target_semantic_architecture.md",
        "docs/specs/future_semantic_phase_contract.md",
        "docs/specs/product_decisions_and_unknowns.md",
        "docs/adr/ADR-001-semantic-authority.md",
        "docs/adr/ADR-002-tradingagents-boundary.md",
        "docs/adr/ADR-003-replay-semantics.md",
        "docs/adr/ADR-004-evidence-stance-provenance.md",
        "docs/audit_artifacts/phase0_5/phase0_original_file_hashes.json",
    )
    missing = [relative for relative in references if not (REPO_ROOT / relative).exists()]
    return _result("document_internal_references_exist", not missing, f"missing={missing}")


def check_head_unchanged() -> CheckResult:
    if not START_SNAPSHOT_PATH.is_file():
        return CheckResult("branch_and_head_unchanged", BLOCKED, "start snapshot missing")
    snapshot = _load_json(START_SNAPSHOT_PATH)
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    ok = branch == snapshot.get("branch") and head == snapshot.get("head")
    return _result("branch_and_head_unchanged", ok, f"branch={branch}; head={head}")


CHECKS: tuple[Callable[[], CheckResult], ...] = (
    check_canonical_plan_exists,
    check_manifest_sha,
    check_manifest_byte_identical,
    check_adrs_exist,
    check_adr_statuses,
    check_authority_matrix,
    check_current_and_target_architecture,
    check_reconciled_verdicts,
    check_phase0_hashes,
    check_preexisting_dirty_files,
    check_source_artifacts,
    check_evidence_stance_provenance,
    check_canonical_prompt_unchanged,
    check_week2_default_unchanged,
    check_allowed_paths_only,
    check_required_outputs,
    check_json_and_csv,
    check_internal_references,
    check_head_unchanged,
)


def main() -> int:
    results = []
    for check in CHECKS:
        try:
            result = check()
        except (OSError, ValueError, KeyError, json.JSONDecodeError, csv.Error) as exc:
            result = CheckResult(check.__name__, FAIL, f"{type(exc).__name__}: {exc}")
        results.append(result)
        print(f"[{result.status}] {result.name}: {result.detail}")

    if any(result.status == FAIL for result in results):
        gate = FAIL
        exit_code = 1
    elif any(result.status == BLOCKED for result in results):
        gate = BLOCKED
        exit_code = 2
    else:
        gate = PASS
        exit_code = 0
    print(f"PHASE_0_5_SPEC_FREEZE: {gate}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
