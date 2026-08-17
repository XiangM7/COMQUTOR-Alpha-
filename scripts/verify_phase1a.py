"""Read-only verifier for Phase 1A Structured Output Adapter Shadow foundation."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
PHASE_DIR = REPO_ROOT / "docs/audit_artifacts/phase1a"
PHASE0_PROTECTED = REPO_ROOT / "docs/audit_artifacts/phase0_6c/protected_file_manifest_before.json"
PHASE0_SOURCE = REPO_ROOT / "docs/audit_artifacts/phase0_6c/source_artifact_integrity_before.json"
START_SNAPSHOT = PHASE_DIR / "worktree_start_snapshot.json"

PASS = "PASS"
BLOCKED = "BLOCKED"
FAIL = "FAIL"

SHADOW_ALLOWED_PREFIXES = (
    "comqutor_alpha/structure_engine/structured_output_shadow",
    "tests/structured_output_shadow/",
    "docs/audit_artifacts/phase1a/",
)
SHADOW_ALLOWED_EXACT = {
    "scripts/build_phase1a_shadow_review_bundle.py",
    "scripts/verify_phase1a.py",
    "docs/adr/ADR-008-structured-output-adapter-shadow.md",
    "docs/specs/structured_output_adapter_shadow_contract_v1.md",
    "docs/specs/structured_output_adapter_review_contract_v1.md",
    "docs/specs/phase1_structured_output_quality_gate_proposal.md",
}

ADR_HASHES = {
    "docs/adr/ADR-001-semantic-authority.md": "d78f572304d3ca016103f94075bff8ff3602bbd3979785cd9c130f4086dc7570",
    "docs/adr/ADR-002-tradingagents-boundary.md": "b1125cc89ba2ae6b3f93916a8875748bb456883f286af548c1857e790f4b2c73",
    "docs/adr/ADR-003-replay-semantics.md": "c8e7a781c345de7645d4c2be48b7770ed1d3211823fc90119ef105d2a0a97f35",
    "docs/adr/ADR-004-evidence-stance-provenance.md": "9db7ec3c76f15582ce6f77a95721bd9e57663abc0a760376c61a66e7e9d1a0ef",
    "docs/adr/ADR-005-llm-execution-substrate.md": "9d24b65d67027d6865d8b9d1d6928b78e72d9353de0f784b53ce1326840ec4f1",
    "docs/adr/ADR-006-week2-semantic-runtime-integration.md": "71556c9f9924dd60cfa99dc14122d48dd3dbcf5002788b61e86c959e2eac3ff4",
    "docs/adr/ADR-007-exact-semantic-replay-integration.md": "20411350c21530e59f25b37a55259c2c4720cb35ea793eca3c79870e76cae742",
}

REPLAY_HASHES = {
    "comqutor_alpha/replay/__init__.py": "0dce5cdb4129848eb96dea11b566e700d0ebc8815ec8c8665a9cf9eb21abc130",
    "comqutor_alpha/replay/cli.py": "6523dd0511e74069fcd37d55f914c58333ad01e9ecabc77f607fe6111193f394",
    "comqutor_alpha/replay/pipeline.py": "2f37e97f0579d7e9659704d85b6fa84c7f33b91bf28dcd5b7437650cdba78c8e",
    "comqutor_alpha/replay/exact_semantic.py": "e7b88686eaf99dc7bbb5560f4d49eebf15c81d2aa984a6b4cef9f3f59aed6f56",
    "comqutor_alpha/replay/modes.py": "0691520b9ffb67355e37f383cc5c66e6eb143fd32c9bc77991adaf7943d49ad7",
    "comqutor_alpha/replay/semantic_binding.py": "f10b0a11f59571035f96b051a83730081f18e0b57525e7e4869343cf600eb487",
    "comqutor_alpha/replay/source_bundle.py": "3a78b69b578f7897e45f75ac23746fffaca25763fb10ee151401282bf84abad4",
}


@dataclass(frozen=True)
class CheckResult:
    number: int
    name: str
    status: str
    detail: str


def result(number: int, name: str, ok: bool, detail: str, *, blocked: bool = False) -> CheckResult:
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
        raise ValueError(f"object required: {path}")
    return value


def verify_hash_map(values: Mapping[str, str]) -> list[str]:
    errors = []
    for relative, expected in values.items():
        path = REPO_ROOT / relative
        if not path.is_file():
            errors.append(f"missing:{relative}")
        elif sha256(path) != expected:
            errors.append(f"hash:{relative}")
    return errors


def protected_records(*categories: str) -> list[dict[str, Any]]:
    wanted = set(categories)
    return [
        item
        for item in load_json(PHASE0_PROTECTED).get("strict_files", [])
        if wanted.intersection(item.get("categories", []))
    ]


def verify_records(records: Sequence[Mapping[str, Any]], *, mtime: bool = True) -> list[str]:
    errors = []
    for record in records:
        relative = str(record["relative_path"])
        path = REPO_ROOT / relative
        if not path.is_file():
            errors.append(f"missing:{relative}")
            continue
        stat = path.stat()
        if stat.st_size != record["size_bytes"]:
            errors.append(f"size:{relative}")
        if sha256(path) != record["sha256"]:
            errors.append(f"hash:{relative}")
        if mtime and stat.st_mtime_ns != record["mtime_ns"]:
            errors.append(f"mtime:{relative}")
    return errors


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


def _allowed_phase1a_path(path: str) -> bool:
    return path in SHADOW_ALLOWED_EXACT or any(path.startswith(prefix) for prefix in SHADOW_ALLOWED_PREFIXES)


def _status_lines() -> list[str]:
    output = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return output.splitlines()


def _status_path(line: str) -> str:
    value = line[3:]
    return value.split(" -> ")[-1]


def _imports_shadow(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return False
    prefix = "comqutor_alpha.structure_engine.structured_output_shadow"
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and str(node.module or "").startswith(prefix):
            return True
        if isinstance(node, ast.Import) and any(alias.name.startswith(prefix) for alias in node.names):
            return True
    return False


def _production_importers() -> list[str]:
    roots = (
        "comqutor_alpha/api",
        "comqutor_alpha/replay",
        "comqutor_alpha/graph_engine",
        "comqutor_alpha/conflict_engine",
        "comqutor_alpha/exposure",
        "tradingagents",
    )
    files: list[Path] = []
    for root in roots:
        files.extend((REPO_ROOT / root).rglob("*.py"))
    files.extend(
        REPO_ROOT / path
        for path in (
            "comqutor_alpha/exposure_engine.py",
            "comqutor_alpha/structure_engine/structured_output_adapter.py",
            "comqutor_alpha/structure_engine/week2_llm.py",
            "comqutor_alpha/structure_engine/alpha_mapper.py",
            "comqutor_alpha/structure_engine/structure_extractor.py",
        )
    )
    return sorted(str(path.relative_to(REPO_ROOT)) for path in files if _imports_shadow(path))


def _valid_probe_bundle(report: str) -> tuple[dict[str, Any], dict[str, Any]]:
    from comqutor_alpha.structure_engine.structured_output_shadow_prompt import (
        STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
        STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
    )
    from comqutor_alpha.structure_engine.structured_output_shadow_schema import (
        assign_deterministic_claim_ids,
        build_shadow_bundle,
        sha256_text,
    )

    quote = report
    claim = {
        "shadow_claim_id": "",
        "claim": quote,
        "evidence": quote,
        "source_spans": [{"start": 0, "end": len(report), "exact_quote": report}],
        "entities": [],
        "factors": [],
        "direction": "unknown",
        "confidence": 0.5,
        "source_type": "unknown",
        "source_refs": [],
        "candidate_segment_ids": [],
        "extraction_status": "proposed",
    }
    bundle = build_shadow_bundle(
        run_id="phase1a-probe",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="phase1a-probe:news_agent:news_report",
        source_report_sha256=sha256_text(report),
        prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
        prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
        claims=[claim],
    )
    return bundle, assign_deterministic_claim_ids(bundle)


def check_01() -> CheckResult:
    plan = REPO_ROOT / "docs/specs/COMQUTOR_Alpha_Development_Plan_v1.0.docx"
    digest = sha256(plan) if plan.is_file() else "missing"
    return result(1, "development_plan_sha_unchanged", digest == "cabf3381aaa633b7b88035ab6df2d7dac0def3d5ddd337f6384f23f4c439a8d9", f"sha256={digest}", blocked=digest == "missing")


def check_02() -> CheckResult:
    errors = verify_hash_map(ADR_HASHES)
    return result(2, "adr_001_through_007_unchanged", not errors, f"errors={errors}")


def check_03() -> CheckResult:
    path = REPO_ROOT / "docs/adr/ADR-008-structured-output-adapter-shadow.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    required = {"ACCEPTED_FOR_OFFLINE_SHADOW", "NOT_LIVE_INTEGRATED", "NO_PRODUCTION_AUTHORITY", "SEMANTIC_QUALITY_UNPROVEN"}
    missing = sorted(token for token in required if token not in text)
    return result(3, "adr_008_status", path.is_file() and not missing, f"missing={missing}")


def check_04() -> CheckResult:
    from comqutor_alpha.structure_engine.structured_output_shadow_schema import (
        STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION,
    )

    ok = STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION == "comqutor.structured_claim_shadow.v1"
    return result(4, "shadow_schema_version", ok, STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION)


def check_05() -> CheckResult:
    from comqutor_alpha.structure_engine.structured_output_shadow_prompt import (
        FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
        STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
        STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
    )

    ok = STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION == "structured_adapter.claim_extraction_shadow.v1" and STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256 == FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256
    return result(5, "prompt_version_and_hash_frozen", ok, f"version={STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION}; sha256={STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256}")


def check_06() -> CheckResult:
    _raw, bundle = _valid_probe_bundle("GPU demand rose.")
    return result(6, "shadow_only_forced_true", bundle.get("shadow_only") is True, f"shadow_only={bundle.get('shadow_only')}")


def check_07() -> CheckResult:
    _raw, bundle = _valid_probe_bundle("GPU demand rose.")
    return result(7, "production_authority_forced_false", bundle.get("production_authority") is False, f"production_authority={bundle.get('production_authority')}")


def check_08() -> CheckResult:
    from comqutor_alpha.structure_engine.structured_output_shadow_prompt import (
        STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
        STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
    )
    from comqutor_alpha.structure_engine.structured_output_shadow_schema import (
        validate_shadow_bundle,
    )

    report = "GPU demand rose."
    _raw, bundle = _valid_probe_bundle(report)
    bundle["claims"][0]["source_spans"][0]["exact_quote"] = "wrong"
    validation = validate_shadow_bundle(bundle, source_report=report, run_id="phase1a-probe", ticker="NVDA", agent="news_agent", agent_output_id="phase1a-probe:news_agent:news_report", prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION, prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256, factor_vocabulary=())
    return result(8, "source_span_validation", "SHADOW_SOURCE_SPAN_INVALID" in validation.reason_codes, f"codes={validation.reason_codes}")


def check_09() -> CheckResult:
    from comqutor_alpha.structure_engine.structured_output_shadow_schema import (
        generate_shadow_claim_id,
    )

    kwargs = {"run_id": "r", "agent_output_id": "a", "claim": "claim", "source_spans": [{"start": 0, "end": 5, "exact_quote": "claim"}]}
    first = generate_shadow_claim_id(**kwargs)
    ok = first == generate_shadow_claim_id(**kwargs) and first != generate_shadow_claim_id(**{**kwargs, "claim": "changed"})
    return result(9, "stable_claim_identity", ok, first)


def check_10() -> CheckResult:
    from comqutor_alpha.structure_engine.structured_output_shadow_prompt import (
        STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
        STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
    )
    from comqutor_alpha.structure_engine.structured_output_shadow_schema import (
        validate_shadow_bundle,
    )

    report = "GPU demand rose."
    _raw, bundle = _valid_probe_bundle(report)
    bundle["claims"][0]["evidence"] = "invented fact"
    validation = validate_shadow_bundle(bundle, source_report=report, run_id="phase1a-probe", ticker="NVDA", agent="news_agent", agent_output_id="phase1a-probe:news_agent:news_report", prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION, prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256, factor_vocabulary=())
    return result(10, "evidence_provenance_fail_closed", "SHADOW_EVIDENCE_NOT_PROVENANCED" in validation.reason_codes, f"codes={validation.reason_codes}")


def check_11() -> CheckResult:
    path = REPO_ROOT / "docs/specs/structured_output_adapter_review_contract_v1.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    required = {"Claim boundary", "Evidence pairing", "Semantic fidelity", "Overall disposition", "not a gold set"}
    missing = sorted(token for token in required if token not in text)
    return result(11, "review_contract_exists", path.is_file() and not missing, f"missing={missing}")


def check_12() -> CheckResult:
    path = REPO_ROOT / "docs/specs/phase1_structured_output_quality_gate_proposal.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    required = {"`SOURCE_FROZEN`", "`APPROVED_PROJECT_DECISION` safety gates", "`PROPOSED_EXTENSION` semantic targets", "REQUIRES_INDEPENDENT_APPROVAL_BEFORE_CUTOVER"}
    missing = sorted(token for token in required if token not in text)
    return result(12, "quality_gate_provenance", path.is_file() and not missing, f"missing={missing}")


def _category_check(number: int, name: str, *categories: str) -> CheckResult:
    records = protected_records(*categories)
    errors = verify_records(records)
    return result(number, name, bool(records) and not errors, f"records={len(records)}; errors={errors[:8]}")


def check_13() -> CheckResult:
    records = [item for item in protected_records("live_week2_path") if item["relative_path"].endswith("structured_output_adapter.py")]
    errors = verify_records(records)
    return result(13, "current_adapter_unchanged", len(records) == 1 and not errors, f"errors={errors}")


def check_14() -> CheckResult:
    records = [item for item in protected_records("live_week2_path") if item["relative_path"].endswith("week2_llm.py")]
    errors = verify_records(records)
    return result(14, "week2_gateway_unchanged", len(records) == 1 and not errors, f"errors={errors}")


def check_15() -> CheckResult:
    records = [item for item in protected_records("live_week2_path") if item["relative_path"].endswith(("alpha_mapper.py", "structure_extractor.py"))]
    errors = verify_records(records)
    return result(15, "mapper_extractor_unchanged", len(records) == 2 and not errors, f"errors={errors}")


def check_16() -> CheckResult:
    return _category_check(16, "live_routes_unchanged", "live_week2_path")


def check_17() -> CheckResult:
    errors = verify_hash_map(REPLAY_HASHES)
    return result(17, "replay_unchanged", not errors, f"errors={errors}")


def check_18() -> CheckResult:
    return _category_check(18, "llm_runtime_unchanged", "llm_runtime")


def check_19() -> CheckResult:
    return _category_check(19, "tradingagents_unchanged", "tradingagents")


def check_20() -> CheckResult:
    return _category_check(20, "canonical_prompt_injection_unchanged", "canonical_prompts")


def check_21() -> CheckResult:
    return _category_check(21, "deterministic_core_unchanged", "graph_engine", "conflict_engine", "exposure_engine")


def check_22() -> CheckResult:
    from comqutor_alpha.structure_engine.week2_llm import _enabled

    records = protected_records("live_week2_path")
    errors = verify_records(records)
    ok = not errors and _enabled(None) is False
    return result(
        22,
        "default_llm_setting_unchanged",
        ok,
        f"errors={errors}; unset_resolves_enabled={_enabled(None)}",
    )


def check_23() -> CheckResult:
    importers = _production_importers()
    return result(23, "live_production_importer_count_zero", not importers, f"count={len(importers)}; importers={importers}")


def _external_boundary_check(number: int, name: str, forbidden_tokens: Sequence[str]) -> CheckResult:
    paths = list((REPO_ROOT / "comqutor_alpha/structure_engine").glob("structured_output_shadow*.py"))
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    found = [token for token in forbidden_tokens if token in text]
    return result(number, name, not found, f"forbidden_import_tokens={found}; observed_calls=0")


def check_24() -> CheckResult:
    return _external_boundary_check(24, "provider_calls_zero", ("week2_llm import", "ProviderClient", "create_provider"))


def check_25() -> CheckResult:
    return _external_boundary_check(25, "network_connections_zero", ("import socket", "import requests", "import httpx", "urllib.request"))


def check_26() -> CheckResult:
    return _external_boundary_check(26, "redis_connections_zero", ("import redis", "RedisLLMResponseCache"))


def check_27() -> CheckResult:
    return _external_boundary_check(27, "database_writes_zero", ("import sqlalchemy", "create_engine", "Session("))


def _historical_check(number: int, key: str, name: str) -> CheckResult:
    fields = ("relative_path", "size_bytes", "sha256", "mtime_ns")
    expected = [
        {field: record[field] for field in fields}
        for record in load_json(PHASE0_SOURCE)[key]["files"]
    ]
    actual = current_tree(load_json(PHASE0_SOURCE)[key]["root"])
    ok = actual == expected
    return result(number, name, ok, f"expected={len(expected)}; actual={len(actual)}")


def check_28() -> CheckResult:
    return _historical_check(28, "outputs_runs", "historical_outputs_runs_unchanged")


def check_29() -> CheckResult:
    return _historical_check(29, "outputs_replays", "historical_outputs_replays_unchanged")


def check_30() -> CheckResult:
    start = load_json(START_SNAPSHOT)
    baseline = [line for line in _status_lines() if not _allowed_phase1a_path(_status_path(line))]
    digest = hashlib.sha256(("\n".join(baseline) + "\n").encode()).hexdigest()
    phase_paths = [_status_path(line) for line in _status_lines() if _allowed_phase1a_path(_status_path(line))]
    disallowed = [path for path in phase_paths if not _allowed_phase1a_path(path)]
    ok = digest == start.get("status_sha256") and not disallowed
    return result(30, "allowed_diff_scope", ok, f"baseline_sha256={digest}; phase1a_paths={len(phase_paths)}; disallowed={disallowed}")


def check_31() -> CheckResult:
    json_path = PHASE_DIR / "evaluation_corpus_inventory.json"
    csv_path = PHASE_DIR / "evaluation_corpus_coverage.csv"
    if not json_path.is_file() or not csv_path.is_file():
        return result(31, "evaluation_corpus_inventory", False, "inventory missing", blocked=True)
    payload = load_json(json_path)
    ok = payload.get("target_slot_count") == 24 and payload.get("phase1b_evaluation_corpus_ready") in {"YES", "PARTIAL", "NO"}
    return result(31, "evaluation_corpus_inventory", ok, f"eligible={payload.get('eligible_report_count')}; readiness={payload.get('phase1b_evaluation_corpus_ready')}")


def check_32() -> CheckResult:
    path = PHASE_DIR / "development_plan_acceptance_fixture_index.json"
    payload = load_json(path) if path.is_file() else {}
    fixtures = payload.get("fixtures") or []
    ok = bool(fixtures) and all(item.get("classification") == "SOURCE_FROZEN" and item.get("document_location") for item in fixtures)
    return result(32, "development_plan_acceptance_fixtures_traceable", ok, f"fixtures={len(fixtures)}", blocked=not path.is_file())


def check_33() -> CheckResult:
    from scripts.build_phase1a_shadow_review_bundle import validate_output_directory

    rejected = 0
    for value in ("outputs/runs/phase1a", "outputs/replays/phase1a", "docs/audit_artifacts/phase1a/../escape"):
        try:
            validate_output_directory(value)
        except ValueError:
            rejected += 1
    return result(33, "review_builder_rejects_historical_outputs", rejected == 3, f"rejected={rejected}/3")


def check_34() -> CheckResult:
    _raw, bundle = _valid_probe_bundle("GPU demand rose.")
    contract = (REPO_ROOT / "docs/specs/structured_output_adapter_shadow_contract_v1.md").read_text(encoding="utf-8")
    ok = bundle["shadow_only"] is True and bundle["production_authority"] is False and "NO_PRODUCTION_AUTHORITY" in contract
    return result(34, "all_shadow_outputs_no_production_authority", ok, f"shadow_only={bundle['shadow_only']}; production_authority={bundle['production_authority']}")


def check_35() -> CheckResult:
    paths = (
        REPO_ROOT / "docs/adr/ADR-008-structured-output-adapter-shadow.md",
        REPO_ROOT / "docs/specs/structured_output_adapter_shadow_contract_v1.md",
        REPO_ROOT / "docs/specs/phase1_structured_output_quality_gate_proposal.md",
    )
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    bad = [
        token
        for token in ("Evidence Stance is SOURCE_FROZEN", "ticker specificity is SOURCE_FROZEN", "B2 is SOURCE_FROZEN")
        if token in text
    ]
    ok = not bad and "Evidence Stance" in text and "outside" in text
    return result(35, "john_later_requirements_not_source_frozen", ok, f"misclassifications={bad}")


CHECKS: tuple[Callable[[], CheckResult], ...] = tuple(globals()[f"check_{number:02d}"] for number in range(1, 36))


def main() -> int:
    checks = []
    for check in CHECKS:
        try:
            checks.append(check())
        except Exception as exc:
            number = len(checks) + 1
            checks.append(CheckResult(number, check.__name__, FAIL, f"{type(exc).__name__}: {exc}"))
    for item in checks:
        print(f"[{item.number:02d}] {item.status} {item.name}: {item.detail}")
    if any(item.status == FAIL for item in checks):
        gate = FAIL
    elif any(item.status == BLOCKED for item in checks):
        gate = BLOCKED
    else:
        gate = PASS
    passed = sum(item.status == PASS for item in checks)
    print(f"Phase 1A checks: {passed}/{len(checks)} PASS")
    print(f"PHASE_1A_STRUCTURED_OUTPUT_SHADOW_FOUNDATION: {gate}")
    return 0 if gate == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
