"""Phase 1B.1 evaluation-only Provider-zero Shadow exact replay validator.

This is NOT the production Exact Semantic Replay mode defined by ADR-007 /
``exact_semantic_replay_artifact_contract_v1.md`` (that mode consumes a live
run's ``structured_agent_outputs.json``/``alpha_matches.json``/
``extracted_structures.json`` and reruns deterministic Graph/Activation/
Exposure/Conflict). This module instead re-verifies one persisted Phase
1B.1 provider-smoke bundle (four reports, Shadow-only) against the exact
same deterministic identity/validation functions Phase 1A/1B.1 already use
-- with zero Provider, Gateway, network, Redis, or database calls, and
without reinterpreting natural language or regenerating a Claim.

Never imported by a live route, the current Adapter/Mapper/Extractor,
production Replay, or TradingAgents.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from comqutor_alpha.llm_runtime.canonical_json import sha256_canonical_json
from comqutor_alpha.llm_runtime.contracts import validate_semantic_call_records
from comqutor_alpha.llm_runtime.manifest import verify_semantic_manifest
from comqutor_alpha.structure_engine.structured_output_shadow_prompt import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v2 import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v3 import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V3_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v4 import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v4_1 import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_1,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v4_2 import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_2,
)
from comqutor_alpha.structure_engine.structured_output_shadow_review import (
    compare_legacy_and_shadow,
)
from comqutor_alpha.structure_engine.structured_output_shadow_schema import (
    assign_deterministic_claim_ids,
    sha256_text,
    validate_shadow_bundle,
)

# The only prompt (version, sha256) pairs Phase 1 Master has ever frozen and
# authorized. This is a drift-DETECTION allowlist, not a leniency relaxation:
# it still fails closed on any unknown prompt identity -- it now
# simply recognizes the legitimately frozen prompts (v1;
# the Phase 1 Master prompt-size fix's v2; the Phase 1 Master evidence-
# alignment fix's v3; v3's own markdown-formatting-fidelity follow-up, v4;
# the additive v4.1 candidate-binding experiment; and v4.2, the Product
# Owner's final canonical-duplicate-occurrence simplification that removed
# candidate binding from the active path) instead of hardcoding only the
# first one(s) that ever existed. v4.2's SHA256 is deliberately identical to
# v4's (byte-identical prompt text -- only the deterministic resolver's
# duplicate-match policy differs), so this set legitimately contains two
# different version strings mapped to the same hash; that is not a
# collision bug.
KNOWN_PROMPT_IDENTITY_PAIRS = frozenset(
    {
        (STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION, STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256),
        (STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2, STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256),
        (STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3, STRUCTURED_OUTPUT_SHADOW_PROMPT_V3_SHA256),
        (STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4, STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256),
        (
            STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_1,
            STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256,
        ),
        (
            STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_2,
            STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256,
        ),
    }
)
KNOWN_PROMPT_VERSIONS = frozenset(version for version, _sha in KNOWN_PROMPT_IDENTITY_PAIRS)
KNOWN_PROMPT_HASHES = frozenset(sha for _version, sha in KNOWN_PROMPT_IDENTITY_PAIRS)

SHADOW_EXACT_REPLAY_STATUS_PASS = "PASS"
SHADOW_EXACT_REPLAY_STATUS_FAIL = "FAIL"

REASON_ARTIFACT_MISSING = "PHASE1B1_REPLAY_ARTIFACT_MISSING"
REASON_MANIFEST_INVALID = "PHASE1B1_REPLAY_MANIFEST_INVALID"
REASON_CALLS_INVALID = "PHASE1B1_REPLAY_CALLS_INVALID"
REASON_REPORT_HASH_MISMATCH = "PHASE1B1_REPLAY_REPORT_HASH_MISMATCH"
REASON_PROMPT_IDENTITY_MISMATCH = "PHASE1B1_REPLAY_PROMPT_IDENTITY_MISMATCH"
REASON_VALIDATION_NOT_REPRODUCIBLE = "PHASE1B1_REPLAY_VALIDATION_NOT_REPRODUCIBLE"
REASON_IDENTITY_NOT_STABLE = "PHASE1B1_REPLAY_IDENTITY_NOT_STABLE"
REASON_COMPARISON_NOT_REPRODUCIBLE = "PHASE1B1_REPLAY_COMPARISON_NOT_REPRODUCIBLE"
REASON_BINDING_AMBIGUOUS = "PHASE1B1_REPLAY_BINDING_AMBIGUOUS"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_calls_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    payload = path.read_bytes()
    if not payload:
        return records
    if not payload.endswith(b"\n"):
        raise ValueError("PHASE1B1_REPLAY_CALLS_TAIL_CORRUPTED")
    for line in payload.splitlines():
        if not line:
            raise ValueError("PHASE1B1_REPLAY_CALLS_MIDDLE_CORRUPTED")
        records.append(json.loads(line.decode("utf-8")))
    return records


def verify_phase1b1_shadow_exact_replay(bundle_dir: str | Path) -> dict[str, Any]:
    """Re-verify one persisted Phase 1B.1 smoke bundle.

    Returns the full ``shadow_exact_replay_audit.json`` content. Never
    raises for an ordinary artifact defect -- every failure is reported as a
    stable reason code in the returned dict, with
    ``final_status=FAIL``. Only genuinely unexpected errors (e.g. an
    unreadable path outside the expected shape) propagate.
    """
    directory = Path(bundle_dir)
    reason_codes: list[str] = []
    checks: dict[str, Any] = {}

    calls_path = directory / "llm_semantic_calls.jsonl"
    manifest_path = directory / "llm_semantic_manifest.json"
    reports_dir = directory / "reports"
    required_top = [calls_path, manifest_path, reports_dir]
    missing = [str(p.relative_to(directory)) for p in required_top if not p.exists()]
    if missing:
        reason_codes.append(REASON_ARTIFACT_MISSING)
        checks["missing_top_level_artifacts"] = missing
        return _finalize(directory, reason_codes, checks)

    manifest_result = verify_semantic_manifest(manifest_path)
    checks["manifest_valid"] = manifest_result.valid
    checks["manifest_reason_codes"] = list(manifest_result.reason_codes)
    if not manifest_result.valid:
        reason_codes.append(REASON_MANIFEST_INVALID)

    try:
        call_records = _read_calls_jsonl(calls_path)
    except ValueError as exc:
        reason_codes.append(str(exc))
        call_records = []
    calls_validation = validate_semantic_call_records(call_records)
    checks["calls_valid"] = calls_validation.valid
    checks["calls_reason_codes"] = list(calls_validation.reason_codes)
    if not calls_validation.valid:
        reason_codes.append(REASON_CALLS_INVALID)

    checks["record_count"] = len(call_records)
    checks["unique_call_ids"] = len({record.get("call_id") for record in call_records}) == len(
        call_records
    )
    if not checks["unique_call_ids"]:
        reason_codes.append(REASON_BINDING_AMBIGUOUS)

    prompt_versions = {record.get("prompt_version") for record in call_records}
    prompt_hashes = {record.get("prompt_sha256") for record in call_records}
    checks["prompt_version_stable"] = prompt_versions <= KNOWN_PROMPT_VERSIONS
    checks["prompt_hash_stable"] = prompt_hashes <= KNOWN_PROMPT_HASHES
    if not (checks["prompt_version_stable"] and checks["prompt_hash_stable"]):
        reason_codes.append(REASON_PROMPT_IDENTITY_MISMATCH)

    report_family_dirs = sorted(p for p in reports_dir.iterdir() if p.is_dir()) if reports_dir.exists() else []
    per_report_checks: list[dict[str, Any]] = []
    bindings: dict[tuple[str, str], list[str]] = {}
    for family_dir in report_family_dirs:
        entry, binding_key = _verify_one_report_directory(family_dir, family_dir.name, reason_codes)
        if binding_key is not None:
            bindings.setdefault(binding_key, []).append(family_dir.name)
        per_report_checks.append(entry)

    ambiguous_bindings = {key: dirs for key, dirs in bindings.items() if len(dirs) > 1}
    checks["unique_bindings"] = not ambiguous_bindings
    if ambiguous_bindings:
        reason_codes.append(REASON_BINDING_AMBIGUOUS)
    checks["per_report"] = per_report_checks
    checks["report_count"] = len(report_family_dirs)

    return _finalize(directory, reason_codes, checks)


def _verify_one_report_directory(
    report_dir: Path, label: str, reason_codes: list[str]
) -> tuple[dict[str, Any], tuple[str, str] | None]:
    """Re-verify one ``<family>/`` (or ``<ticker>/<family>/``) report
    directory's hash/identity/validation/comparison reproducibility.

    Appends any failure reason codes to the caller's shared ``reason_codes``
    list (so both the single-ticker and multi-ticker callers accumulate one
    unified reason set) and returns ``(entry, binding_key_or_none)``.
    """
    entry: dict[str, Any] = {"report_dir": label}
    snapshot_path = report_dir / "source_report_snapshot.json"
    bundle_path = report_dir / "shadow_bundle.json"
    candidates_path = report_dir / "candidate_segments.json"
    legacy_path = report_dir / "legacy_claims_snapshot.json"
    comparison_path = report_dir / "legacy_vs_shadow_comparison.json"
    required = [snapshot_path, bundle_path, candidates_path, legacy_path, comparison_path]
    missing_report = [str(p.name) for p in required if not p.exists()]
    if missing_report:
        entry["missing_artifacts"] = missing_report
        entry["report_identity_valid"] = False
        reason_codes.append(REASON_ARTIFACT_MISSING)
        return entry, None

    snapshot = _load_json(snapshot_path)
    bundle = _load_json(bundle_path)
    candidates = _load_json(candidates_path)
    legacy = _load_json(legacy_path)
    saved_comparison = _load_json(comparison_path)

    report_text = str(snapshot.get("report_text") or "")
    recomputed_report_hash = sha256_text(report_text)
    entry["report_identity_valid"] = recomputed_report_hash == bundle.get("source_report_sha256")
    if not entry["report_identity_valid"]:
        reason_codes.append(REASON_REPORT_HASH_MISMATCH)

    candidate_segment_ids = [
        str(item.get("candidate_segment_id") or "") for item in candidates if isinstance(item, Mapping)
    ]
    bundle_prompt_version = str(bundle.get("prompt_version") or STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION)
    bundle_prompt_sha256 = str(bundle.get("prompt_sha256") or STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256)
    recomputed_validation = validate_shadow_bundle(
        assign_deterministic_claim_ids(bundle),
        source_report=report_text,
        run_id=str(bundle.get("run_id") or ""),
        ticker=str(bundle.get("ticker") or ""),
        agent=str(bundle.get("agent") or ""),
        agent_output_id=str(bundle.get("agent_output_id") or ""),
        prompt_version=bundle_prompt_version,
        prompt_sha256=bundle_prompt_sha256,
        factor_vocabulary=snapshot.get("factor_vocabulary") or [],
        allowed_source_refs=snapshot.get("allowed_source_refs") or [],
        allowed_candidate_segment_ids=candidate_segment_ids,
    )
    saved_status = (bundle.get("validation_summary") or {}).get("status")
    entry["validation_reproducible"] = (
        recomputed_validation.status == saved_status
        and recomputed_validation.valid == bool((bundle.get("validation_summary") or {}).get("valid"))
    )
    if not entry["validation_reproducible"]:
        reason_codes.append(REASON_VALIDATION_NOT_REPRODUCIBLE)

    recomputed_ids = sorted(
        str(claim.get("shadow_claim_id") or "")
        for claim in assign_deterministic_claim_ids(bundle).get("claims") or []
    )
    saved_ids = sorted(str(claim.get("shadow_claim_id") or "") for claim in bundle.get("claims") or [])
    entry["stable_identity"] = recomputed_ids == saved_ids
    if not entry["stable_identity"]:
        reason_codes.append(REASON_IDENTITY_NOT_STABLE)

    recomputed_comparison = compare_legacy_and_shadow(legacy, bundle)
    entry["comparison_reproducible"] = recomputed_comparison == saved_comparison
    if not entry["comparison_reproducible"]:
        reason_codes.append(REASON_COMPARISON_NOT_REPRODUCIBLE)

    binding_key = (str(bundle.get("run_id") or ""), str(bundle.get("agent_output_id") or ""))
    return entry, binding_key


def verify_phase1_master_shadow_exact_replay(bundle_dir: str | Path) -> dict[str, Any]:
    """Re-verify one persisted Phase 1 Master evaluation bundle.

    Identical contract to :func:`verify_phase1b1_shadow_exact_replay` (same
    reason codes, same PASS/FAIL semantics, same zero Provider/Gateway/
    network/Redis/DB guarantee) but for the Master's ``reports/<ticker>/
    <family>/`` layout instead of Phase 1B.1's flat ``reports/<family>/``.
    Never reinterprets ticker directory names as family names -- each
    report directory is discovered by walking exactly two levels under
    ``reports/``.

    Each Master evaluation stage (Smoke/Pilot/Core Evaluation) runs its own
    self-contained ``SemanticRuntimeSession`` under ``semantic_runtime/
    <stage>/`` -- one calls file cannot be shared/appended-to across stages
    because ``SemanticCallRecorder`` enforces a single run_id and strictly
    increasing call_sequence per file. This function therefore discovers and
    independently verifies every ``semantic_runtime/*/`` subdirectory rather
    than expecting one top-level calls/manifest pair.
    """
    directory = Path(bundle_dir)
    reason_codes: list[str] = []
    checks: dict[str, Any] = {}

    reports_dir = directory / "reports"
    runtime_root = directory / "semantic_runtime"
    stage_dirs = (
        sorted({path.parent for path in runtime_root.rglob("llm_semantic_calls.jsonl")})
        if runtime_root.exists()
        else []
    )
    required_top = [runtime_root, reports_dir]
    missing = [str(p.relative_to(directory)) for p in required_top if not p.exists()]
    if missing or not stage_dirs:
        reason_codes.append(REASON_ARTIFACT_MISSING)
        checks["missing_top_level_artifacts"] = missing or ["semantic_runtime/<no stage subdirectories found>"]
        return _finalize(directory, reason_codes, checks)

    all_prompt_versions: set[str] = set()
    all_prompt_hashes: set[str] = set()
    all_call_ids: set[str] = set()
    call_records_by_agent_output_id: dict[str, list[dict[str, Any]]] = {}
    total_record_count = 0
    stage_checks: dict[str, Any] = {}
    for stage_dir in stage_dirs:
        calls_path = stage_dir / "llm_semantic_calls.jsonl"
        manifest_path = stage_dir / "llm_semantic_manifest.json"
        stage_entry: dict[str, Any] = {}
        stage_missing = [str(p.name) for p in (calls_path, manifest_path) if not p.exists()]
        if stage_missing:
            stage_entry["missing_artifacts"] = stage_missing
            reason_codes.append(REASON_ARTIFACT_MISSING)
            stage_checks[str(stage_dir.relative_to(runtime_root))] = stage_entry
            continue

        manifest_result = verify_semantic_manifest(manifest_path)
        stage_entry["manifest_valid"] = manifest_result.valid
        stage_entry["manifest_reason_codes"] = list(manifest_result.reason_codes)
        if not manifest_result.valid:
            reason_codes.append(REASON_MANIFEST_INVALID)

        try:
            call_records = _read_calls_jsonl(calls_path)
        except ValueError as exc:
            reason_codes.append(str(exc))
            call_records = []
        calls_validation = validate_semantic_call_records(call_records)
        stage_entry["calls_valid"] = calls_validation.valid
        stage_entry["calls_reason_codes"] = list(calls_validation.reason_codes)
        if not calls_validation.valid:
            reason_codes.append(REASON_CALLS_INVALID)

        stage_entry["record_count"] = len(call_records)
        total_record_count += len(call_records)
        stage_call_ids = {record.get("call_id") for record in call_records}
        if len(stage_call_ids) != len(call_records) or not stage_call_ids.isdisjoint(all_call_ids):
            reason_codes.append(REASON_BINDING_AMBIGUOUS)
        all_call_ids |= stage_call_ids

        all_prompt_versions |= {v for v in (record.get("prompt_version") for record in call_records) if v}
        all_prompt_hashes |= {v for v in (record.get("prompt_sha256") for record in call_records) if v}
        for record in call_records:
            payload = record.get("input_payload")
            if not isinstance(payload, Mapping):
                continue
            agent_output_id = str(payload.get("agent_output_id") or "")
            if agent_output_id:
                call_records_by_agent_output_id.setdefault(agent_output_id, []).append(record)
        stage_checks[str(stage_dir.relative_to(runtime_root))] = stage_entry

    checks["stages"] = stage_checks
    checks["record_count"] = total_record_count
    checks["unique_call_ids"] = len(all_call_ids) == total_record_count
    if not checks["unique_call_ids"]:
        reason_codes.append(REASON_BINDING_AMBIGUOUS)

    checks["prompt_versions_seen"] = sorted(all_prompt_versions)
    checks["prompt_version_stable"] = all_prompt_versions <= KNOWN_PROMPT_VERSIONS
    checks["prompt_hash_stable"] = all_prompt_hashes <= KNOWN_PROMPT_HASHES
    if not (checks["prompt_version_stable"] and checks["prompt_hash_stable"]):
        reason_codes.append(REASON_PROMPT_IDENTITY_MISMATCH)

    ticker_dirs = sorted(p for p in reports_dir.iterdir() if p.is_dir()) if reports_dir.exists() else []
    per_report_checks: list[dict[str, Any]] = []
    bindings: dict[tuple[str, str], list[str]] = {}
    report_count = 0
    for ticker_dir in ticker_dirs:
        family_dirs = sorted(p for p in ticker_dir.iterdir() if p.is_dir())
        for family_dir in family_dirs:
            report_count += 1
            label = f"{ticker_dir.name}/{family_dir.name}"
            entry, binding_key = _verify_one_master_report_directory(
                family_dir,
                label,
                call_records_by_agent_output_id,
                reason_codes,
            )
            entry["ticker"] = ticker_dir.name
            entry["agent_family"] = family_dir.name
            if binding_key is not None:
                bindings.setdefault(binding_key, []).append(label)
            per_report_checks.append(entry)

    ambiguous_bindings = {key: dirs for key, dirs in bindings.items() if len(dirs) > 1}
    checks["unique_bindings"] = not ambiguous_bindings
    if ambiguous_bindings:
        reason_codes.append(REASON_BINDING_AMBIGUOUS)
    checks["per_report"] = per_report_checks
    checks["report_count"] = report_count
    checks["ticker_count"] = len(ticker_dirs)

    result = _finalize(directory, reason_codes, checks)
    result["schema_version"] = "comqutor.phase1_master.shadow_exact_replay_audit.v1"
    return result


def _verify_one_master_report_directory(
    report_dir: Path,
    label: str,
    records_by_agent_output_id: Mapping[str, list[dict[str, Any]]],
    reason_codes: list[str],
) -> tuple[dict[str, Any], tuple[str, str] | None]:
    """Apply the corrected per-report replay gate.

    Accepted/valid-empty/abstained semantic outputs must reproduce exactly.
    Deterministic validation rejections reproduce their rejection. Provider
    errors/timeouts are auditable terminal records, not accepted outputs and
    therefore not falsely classified as replay implementation failures.
    """

    snapshot_path = report_dir / "source_report_snapshot.json"
    bundle_path = report_dir / "shadow_bundle.json"
    if not (snapshot_path.exists() and bundle_path.exists()):
        reason_codes.append(REASON_ARTIFACT_MISSING)
        return {
            "report_dir": label,
            "replay_status": "FAIL",
            "replay_failure_reason": REASON_ARTIFACT_MISSING,
        }, None

    snapshot = _load_json(snapshot_path)
    bundle = _load_json(bundle_path)
    agent_output_id = str(
        bundle.get("agent_output_id") or snapshot.get("agent_output_id") or ""
    )
    bound_records = list(records_by_agent_output_id.get(agent_output_id) or [])
    if len(bound_records) != 1:
        reason_codes.append(REASON_BINDING_AMBIGUOUS)
        return {
            "report_dir": label,
            "agent_output_id": agent_output_id,
            "provider_status": None,
            "validation_status": None,
            "accepted_output_hash": None,
            "replay_status": "FAIL",
            "replay_failure_reason": REASON_BINDING_AMBIGUOUS,
        }, None

    record = bound_records[0]
    provider_status = str(record.get("provider_status") or "")
    validation_status = str(record.get("validation_status") or "")
    entry: dict[str, Any] = {
        "report_dir": label,
        "agent_output_id": agent_output_id,
        "provider_status": provider_status,
        "validation_status": validation_status,
        "accepted_output_hash": record.get("validated_output_sha256"),
        "replay_failure_reason": None,
    }
    binding_key = (str(bundle.get("run_id") or ""), agent_output_id)

    if validation_status == "accepted":
        strict_entry, strict_binding = _verify_one_report_directory(
            report_dir, label, reason_codes
        )
        entry.update(strict_entry)
        candidate_path = report_dir / "provider_candidate.json"
        candidate_hash_matches = False
        if candidate_path.exists():
            candidate = _load_json(candidate_path)
            candidate_hash_matches = (
                sha256_canonical_json(candidate)
                == record.get("validated_output_sha256")
            )
        entry["accepted_output_hash_valid"] = candidate_hash_matches
        if not candidate_hash_matches:
            reason_codes.append(REASON_VALIDATION_NOT_REPRODUCIBLE)
        replay_ok = all(
            bool(entry.get(key))
            for key in (
                "report_identity_valid",
                "validation_reproducible",
                "stable_identity",
                "comparison_reproducible",
                "accepted_output_hash_valid",
            )
        )
        entry["replay_status"] = "PASS" if replay_ok else "FAIL"
        if not replay_ok:
            entry["replay_failure_reason"] = REASON_VALIDATION_NOT_REPRODUCIBLE
        return entry, strict_binding

    if validation_status == "rejected" and provider_status == "success":
        candidate_path = report_dir / "provider_candidate.json"
        candidates_path = report_dir / "candidate_segments.json"
        if not (candidate_path.exists() and candidates_path.exists()):
            reason_codes.append(REASON_ARTIFACT_MISSING)
            entry["replay_status"] = "FAIL"
            entry["replay_failure_reason"] = REASON_ARTIFACT_MISSING
            return entry, binding_key
        candidate = _load_json(candidate_path)
        candidates = _load_json(candidates_path)
        candidate_segment_ids = [
            str(item.get("candidate_segment_id") or "")
            for item in candidates
            if isinstance(item, Mapping)
        ]
        validation = validate_shadow_bundle(
            assign_deterministic_claim_ids(candidate),
            source_report=str(snapshot.get("report_text") or ""),
            run_id=str(bundle.get("run_id") or ""),
            ticker=str(bundle.get("ticker") or ""),
            agent=str(bundle.get("agent") or ""),
            agent_output_id=agent_output_id,
            prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
            prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
            factor_vocabulary=snapshot.get("factor_vocabulary") or [],
            allowed_source_refs=snapshot.get("allowed_source_refs") or [],
            allowed_candidate_segment_ids=candidate_segment_ids,
        )
        rejection_reproduced = not validation.valid
        entry["rejection_reproduced"] = rejection_reproduced
        entry["replay_status"] = "REPRODUCED_REJECTION" if rejection_reproduced else "FAIL"
        if not rejection_reproduced:
            reason_codes.append(REASON_VALIDATION_NOT_REPRODUCIBLE)
            entry["replay_failure_reason"] = REASON_VALIDATION_NOT_REPRODUCIBLE
        return entry, binding_key

    entry["auditable_terminal_record"] = provider_status in {
        "timeout",
        "provider_error",
        "budget_exhausted",
        "not_called",
    }
    entry["replay_status"] = (
        "AUDITABLE_NO_ACCEPTED_OUTPUT"
        if entry["auditable_terminal_record"]
        else "FAIL"
    )
    if entry["replay_status"] == "FAIL":
        reason_codes.append(REASON_VALIDATION_NOT_REPRODUCIBLE)
        entry["replay_failure_reason"] = REASON_VALIDATION_NOT_REPRODUCIBLE
    return entry, binding_key


def _finalize(directory: Path, reason_codes: list[str], checks: dict[str, Any]) -> dict[str, Any]:
    unique_reasons = list(dict.fromkeys(reason_codes))
    final_status = SHADOW_EXACT_REPLAY_STATUS_PASS if not unique_reasons else SHADOW_EXACT_REPLAY_STATUS_FAIL
    return {
        "schema_version": "comqutor.phase1b1.shadow_exact_replay_audit.v1",
        "bundle_directory": str(directory),
        "provider_zero_evidence": {
            "provider_calls_made": 0,
            "gateway_calls_made": 0,
            "provider_factory_calls_made": 0,
            "network_calls_made": 0,
            "redis_calls_made": 0,
            "database_writes_made": 0,
            "note": (
                "This module never imports tradingagents, a Provider factory, "
                "Week2LLMGateway, or a network/Redis/DB client -- Provider-zero "
                "is an import-graph and code-path guarantee, not merely an "
                "observed absence."
            ),
        },
        "checks": checks,
        "reason_codes": unique_reasons,
        "final_status": final_status,
    }


__all__ = [
    "REASON_ARTIFACT_MISSING",
    "REASON_BINDING_AMBIGUOUS",
    "REASON_CALLS_INVALID",
    "REASON_COMPARISON_NOT_REPRODUCIBLE",
    "REASON_IDENTITY_NOT_STABLE",
    "REASON_MANIFEST_INVALID",
    "REASON_PROMPT_IDENTITY_MISMATCH",
    "REASON_REPORT_HASH_MISMATCH",
    "REASON_VALIDATION_NOT_REPRODUCIBLE",
    "SHADOW_EXACT_REPLAY_STATUS_FAIL",
    "SHADOW_EXACT_REPLAY_STATUS_PASS",
    "verify_phase1_master_shadow_exact_replay",
    "verify_phase1b1_shadow_exact_replay",
]
