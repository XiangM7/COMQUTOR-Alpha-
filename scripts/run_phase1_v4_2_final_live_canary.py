#!/usr/bin/env python3
"""Execute the frozen four-slot v4.2 final live Canary exactly once.

v4.2 sibling of ``run_phase1_v4_1_final_recanary.py``: same one-shot,
sequential, zero-retry, Legacy-authority-preserving execution shape, with
every candidate/segment concept removed to match the active v4.2 protocol
(no candidate manifest, no candidate binding gate). A successful 4/4 result
only authorizes the separate local cutover edit performed after this
script finishes; this file never changes production authority itself.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.api.routes_research import (  # noqa: E402
    _create_offline_run,
    _run_week1_week2_artifact_pipeline,
    _run_week3_graph_pipeline,
    build_research_response,
)
from comqutor_alpha.llm_runtime.canonical_json import sha256_canonical_json  # noqa: E402
from comqutor_alpha.llm_runtime.manifest import verify_semantic_manifest  # noqa: E402
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession  # noqa: E402
from comqutor_alpha.research_profiles import get_research_profile  # noqa: E402
from comqutor_alpha.storage.file_store import load_json_record  # noqa: E402
from comqutor_alpha.structure_engine.structured_output_live_shadow import (  # noqa: E402
    SHADOW_COMPARISON_FILENAME,
    SHADOW_OUTPUT_FILENAME,
    SHADOW_VALIDATION_FILENAME,
    ShadowAttemptResult,
    resolve_structured_adapter_mode,
    verify_live_shadow_exact_replay,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v4_2 import (  # noqa: E402
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_2,
)
from comqutor_alpha.structure_engine.structured_output_shadow_v4_2 import (  # noqa: E402
    RESOLUTION_STATUSES_LOCATED,
)
from scripts.run_phase1_master import (  # noqa: E402
    HARD_CAP_LOGICAL_CALLS,
    HARD_CAP_PROVIDER_ATTEMPTS,
    _commit_budget,
    load_state,
    save_state,
)
from scripts.run_phase1_v4_live_shadow_canary import (  # noqa: E402
    AUTHORITATIVE_ARTIFACTS,
    _authoritative_snapshot,
    _now,
    _sha256_file,
    _sha256_text,
    _without_times,
    _write_json,
)

CONTRACT_PATH = REPO_ROOT / (
    "docs/audit_artifacts/phase1_master/"
    "phase1_v4_2_final_live_canary_execution_contract.json"
)
RESULT_PATH = REPO_ROOT / (
    "docs/audit_artifacts/phase1_master/"
    "phase1_v4_2_final_live_canary_runtime_result.json"
)
REPORT_JSON_PATH = REPO_ROOT / (
    "docs/audit_artifacts/phase1_master/phase1_v4_2_final_live_canary_report.json"
)
REPORT_MD_PATH = REPO_ROOT / (
    "docs/audit_artifacts/phase1_master/phase1_v4_2_final_live_canary_report.md"
)
APPROVAL_ENV = "COMQUTOR_PHASE1_V4_2_FINAL_CANARY_APPROVED"
EGRESS_ENV = "COMQUTOR_PHASE1_V4_2_FINAL_CANARY_DATA_EGRESS_APPROVED"


def _load_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    checks = (
        contract.get("status") == "PRE_REGISTERED_BEFORE_PROVIDER_CALLS",
        contract.get("logical_call_cap") == 4,
        contract.get("provider_attempt_cap") == 4,
        contract.get("retry_count") == 0,
        contract.get("subagents") == 0,
        len(contract.get("slots") or []) == 4,
        contract.get("prompt_version") == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_2,
        contract.get("prompt_sha256") == STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256,
        contract.get("production_authority_before_execution") == "LEGACY_ADAPTER",
    )
    if not all(checks):
        raise RuntimeError("FINAL_LIVE_CANARY_EXECUTION_CONTRACT_INVALID")
    expected_families = ["fundamental", "news", "sentiment", "technical"]
    if [item.get("family") for item in contract["slots"]] != expected_families:
        raise RuntimeError("FINAL_LIVE_CANARY_SLOT_ORDER_INVALID")
    return contract


def _payload_from_frozen_sources(contract: dict[str, Any]) -> tuple[dict[str, Any], str]:
    source_path = REPO_ROOT / str(contract["source_artifact"])
    source_file_hash = _sha256_file(source_path)
    raw = json.loads(source_path.read_text(encoding="utf-8"))
    by_id = {
        str(item.get("agent_output_id")): item
        for item in raw.get("agent_outputs") or []
        if isinstance(item, dict)
    }
    selected = []
    for expected_slot, slot in enumerate(contract["slots"], start=1):
        if slot.get("slot") != expected_slot:
            raise RuntimeError("FINAL_LIVE_CANARY_SLOT_ORDER_DRIFT")
        record = by_id.get(str(slot.get("source_agent_output_id")))
        if record is None:
            raise RuntimeError("FINAL_LIVE_CANARY_SOURCE_REPORT_MISSING")
        source_report = str(record.get("raw_output") or "")
        if _sha256_text(source_report) != slot.get("source_report_sha256"):
            raise RuntimeError("FINAL_LIVE_CANARY_SOURCE_REPORT_HASH_MISMATCH")
        if record.get("agent") != slot.get("agent"):
            raise RuntimeError("FINAL_LIVE_CANARY_SOURCE_AGENT_MISMATCH")
        selected.append(
            {
                "agent": record["agent"],
                "tradingagents_agent": record.get("tradingagents_agent") or record["agent"],
                "source_field": record.get("source_field") or "final_live_canary_source_report",
                "raw_output": source_report,
            }
        )
    return (
        {
            "run_id": contract["canary_run_id"],
            "ticker": contract["ticker"],
            "analysis_date": "2026-08-11",
            "selected_analysts": ["fundamentals", "news", "sentiment", "market"],
            "offline_raw_agent_outputs": selected,
        },
        source_file_hash,
    )


def _prepare_run(payload: dict[str, Any], output_root: Path) -> Path:
    _run_id, run_dir = _create_offline_run(deepcopy(payload), output_root)
    return Path(run_dir)


def _summarize_resolution(diagnostics: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    duplicate_count = 0
    zero_match_count = 0
    invalid_count = 0
    for item in diagnostics:
        status = str(item.get("status") or "MISSING")
        status_counts[status] = status_counts.get(status, 0) + 1
        if item.get("duplicate_exact_quote"):
            duplicate_count += 1
        if status == "NO_EXACT_MATCH":
            zero_match_count += 1
        if status not in RESOLUTION_STATUSES_LOCATED:
            invalid_count += 1
    return {
        "evidence_items": len(diagnostics),
        "status_counts": status_counts,
        "located_items": len(diagnostics) - invalid_count,
        "invalid_or_unresolved_items": invalid_count,
        "duplicate_exact_items": duplicate_count,
        "zero_match_items": zero_match_count,
    }


class FinalLiveCanaryExecutor:
    def __init__(
        self,
        *,
        contract: dict[str, Any],
        state: dict[str, Any],
        shadow_run_dir: Path,
        legacy_structured_snapshot: dict[str, Any],
    ) -> None:
        import comqutor_alpha.structure_engine.structured_output_shadow_provider as provider_module

        self.contract = contract
        self.state = state
        self.shadow_run_dir = shadow_run_dir
        self.legacy_structured_snapshot = legacy_structured_snapshot
        self.slot_by_agent = {str(item["agent"]): item for item in contract["slots"]}
        self.results: list[dict[str, Any]] = []
        self.provider = str(contract["provider"])
        self.model = str(contract["model"])
        self.profile_id = str(contract["profile_id"])
        self.provider_module = provider_module

        profile = get_research_profile(self.profile_id)
        if profile.llm_provider != self.provider or profile.quick_think_llm != self.model:
            raise RuntimeError("FINAL_LIVE_CANARY_PROVIDER_IDENTITY_DRIFT")
        self.runtime_dir = shadow_run_dir / "structured_adapter_shadow_runtime"
        self.runtime_dir.mkdir(parents=True, exist_ok=False)
        self.session = SemanticRuntimeSession(
            run_id=shadow_run_dir.name,
            output_directory=self.runtime_dir,
            execution_mode="shadow",
            provider=self.provider,
            model=self.model,
            profile_id=self.profile_id,
        )
        self.gateway, info = provider_module.build_phase1_master_provider_gateway(
            profile=profile,
            run_id=shadow_run_dir.name,
            output_root=shadow_run_dir.parent,
            logical_call_limit=4,
            semantic_runtime=self.session,
            max_retries=0,
        )
        if (
            info.timeout_seconds != float(contract["timeout_seconds"])
            or info.max_retries != 0
            or info.max_provider_attempts != 4
            or self.gateway.max_retries != 0
            or self.gateway.max_calls != 4
        ):
            raise RuntimeError("FINAL_LIVE_CANARY_EXECUTION_POLICY_DRIFT")

    def _persist_slot(
        self,
        *,
        context: Any,
        slot: dict[str, Any],
        started_at: str,
        ended_at: str,
        latency_ms: float,
        bundle: dict[str, Any] | None,
        invocation: Any,
        diagnostics: list[dict[str, Any]],
        forensic: dict[str, Any] | None,
        attempt_count: int,
        unexpected_error: BaseException | None,
    ) -> dict[str, Any]:
        if attempt_count > 1:
            raise RuntimeError("FINAL_LIVE_CANARY_PROVIDER_ATTEMPT_CAP_BREACHED")
        retry_count = int(getattr(invocation, "retry_count", 0) or 0)
        if retry_count != 0:
            raise RuntimeError("FINAL_LIVE_CANARY_RETRY_OCCURRED")
        trace = getattr(invocation, "trace_handle", None)
        validation = (bundle or {}).get("validation_summary") or {}
        current_legacy = _without_times(
            json.loads(
                (self.shadow_run_dir / "structured_agent_outputs.json").read_text(encoding="utf-8")
            )
        )
        result = {
            "schema_version": "comqutor.phase1_v4_2.final_live_canary_slot.v1",
            "canary_id": self.contract["canary_id"],
            "logical_call_number": int(slot["slot"]),
            "source_run_id": self.contract["source_run_id"],
            "canary_run_id": context.run_id,
            "ticker": context.ticker,
            "family": slot["family"],
            "agent": context.agent,
            "source_agent_output_id": slot["source_agent_output_id"],
            "canary_agent_output_id": context.agent_output_id,
            "source_report_sha256": _sha256_text(context.source_report),
            "request_sha256": getattr(trace, "input_sha256", None),
            "semantic_call_id": getattr(trace, "call_id", None),
            "prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_2,
            "prompt_sha256": STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256,
            "provider": self.provider,
            "model": self.model,
            "profile_id": self.profile_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "latency_ms": round(latency_ms, 3),
            "provider_called": bool(getattr(invocation, "provider_called", attempt_count > 0)),
            "provider_response_received": bool(getattr(invocation, "response_received", False)),
            "provider_status": getattr(invocation, "provider_status", "execution_error"),
            "provider_attempt_count": attempt_count,
            "retry_count": retry_count,
            "attempt_history": [dict(item) for item in (getattr(invocation, "attempt_history", ()) or ())],
            "token_usage": (
                dict(invocation.token_usage) if invocation is not None and invocation.token_usage else None
            ),
            "parser_status": validation.get("status", "parser_error"),
            "validator_valid": bool(validation.get("valid", False)),
            "reason_codes": list(validation.get("reason_codes") or []),
            "claim_count": len((bundle or {}).get("claims") or []),
            "evidence_resolution": _summarize_resolution(diagnostics),
            "resolution_diagnostics": diagnostics,
            "rejected_forensics": forensic,
            "legacy_isolation_pre_downstream": current_legacy == self.legacy_structured_snapshot,
            "unexpected_error_type": type(unexpected_error).__name__ if unexpected_error else None,
            "production_authority": "LEGACY_ADAPTER",
        }
        slot_path = (
            REPO_ROOT
            / str(self.contract["artifact_root"])
            / "slot_results"
            / f"{int(slot['slot']):02d}-{slot['family']}.json"
        )
        _write_json(slot_path, result)
        self.results.append(result)
        progress = self.state["final_v4_2_canary_progress"]
        progress["slot_results"] = self.results
        progress["logical_calls_used"] = len(self.results)
        progress["provider_attempts_used"] = sum(
            int(item.get("provider_attempt_count") or 0) for item in self.results
        )
        progress["last_recorded_at"] = ended_at
        _commit_budget(
            self.state,
            1,
            attempt_count,
            f"final_v4_2_canary:{self.contract['canary_id']}:{slot['family']}",
            global_event={
                "schema_version": "comqutor.phase1_global_provider_call_ledger.v1",
                "event_id": (
                    f"phase1_master:final_v4_2_canary:{self.contract['canary_id']}:"
                    f"{slot['source_agent_output_id']}:{STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_2}"
                ),
                "recorded_at": ended_at,
                "source_phase": "PHASE_1_MASTER",
                "stage": "FINAL_V4_2_CANARY",
                "task": "structured_claim_shadow",
                "report_id": slot["source_agent_output_id"],
                "prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_2,
                "ticker": context.ticker,
                "agent_family": slot["family"],
                "profile_id": self.profile_id,
                "provider": self.provider,
                "model": self.model,
                "logical_calls": 1,
                "provider_attempts": attempt_count,
                "outcome": result["provider_status"],
                "accounting_confidence": "EXACT",
                "master_contract_budget_counted": True,
                "retry_count": 0,
            },
        )
        save_state(self.state)
        return result

    def execute(self, context: Any) -> ShadowAttemptResult:
        if len(self.results) >= 4:
            raise RuntimeError("FINAL_LIVE_CANARY_LOGICAL_CALL_CAP_BREACHED")
        slot = self.slot_by_agent.get(str(context.agent))
        if slot is None or int(slot["slot"]) != len(self.results) + 1:
            raise RuntimeError("FINAL_LIVE_CANARY_RUNTIME_SLOT_ORDER_DRIFT")
        if _sha256_text(context.source_report) != slot["source_report_sha256"]:
            raise RuntimeError("FINAL_LIVE_CANARY_RUNTIME_SOURCE_HASH_MISMATCH")

        started_at = _now()
        start = time.monotonic()
        calls_before = self.gateway.call_count
        bundle = None
        invocation = None
        diagnostics: list[dict[str, Any]] = []
        forensic = None
        unexpected_error = None
        try:
            bundle, invoker, diagnostics, forensic = (
                self.provider_module.run_real_provider_shadow_smoke_for_report_v4_2(
                    gateway=self.gateway,
                    source_report=context.source_report,
                    run_id=context.run_id,
                    ticker=context.ticker,
                    agent=context.agent,
                    agent_output_id=context.agent_output_id,
                    factor_vocabulary=list(context.factor_vocabulary),
                    max_retries=0,
                )
            )
            invocation = invoker.last_invocation
        except Exception as exc:
            unexpected_error = exc
        result = self._persist_slot(
            context=context,
            slot=slot,
            started_at=started_at,
            ended_at=_now(),
            latency_ms=(time.monotonic() - start) * 1000.0,
            bundle=bundle,
            invocation=invocation,
            diagnostics=diagnostics,
            forensic=forensic,
            attempt_count=self.gateway.call_count - calls_before,
            unexpected_error=unexpected_error,
        )
        if unexpected_error is not None:
            raise unexpected_error
        if bundle is None:
            raise RuntimeError("FINAL_LIVE_CANARY_BUNDLE_MISSING")
        trace = invocation.trace_handle if invocation is not None else None
        return ShadowAttemptResult(
            bundle=bundle,
            provider=self.provider,
            model=self.model,
            profile_id=self.profile_id,
            semantic_call_id=getattr(trace, "call_id", None),
            provider_called=result["provider_called"],
            provider_status=result["provider_status"],
            retry_count=0,
            resolution_log=tuple(diagnostics),
            candidate_manifest=(),
            rejected_forensic_record=forensic,
        )

    def finalize(self) -> Path | None:
        return self.session.finalize_manifest(complete=len(self.results) == 4)


def _initialize_state(contract: dict[str, Any]) -> dict[str, Any]:
    state = load_state()
    budget = contract["budget"]
    if (
        state.get("production_authority") != "LEGACY_ADAPTER"
        or state.get("cumulative_logical_calls") != budget["logical_calls_before"]
        or state.get("cumulative_provider_attempts") != budget["provider_attempts_before"]
        or state.get("cumulative_logical_calls", 0) + 4 > HARD_CAP_LOGICAL_CALLS
        or state.get("cumulative_provider_attempts", 0) + 4 > HARD_CAP_PROVIDER_ATTEMPTS
    ):
        raise RuntimeError("FINAL_LIVE_CANARY_START_STATE_OR_BUDGET_INVALID")
    state["history"].append(
        {
            "at": _now(),
            "from_state": state.get("current_state"),
            "to_state": "FINAL_V4_2_CANARY",
            "detail": {
                "canary_id": contract["canary_id"],
                "execution_contract_pre_registered": True,
                "logical_call_cap": 4,
                "provider_attempt_cap": 4,
                "retry_count": 0,
                "production_authority": "LEGACY_ADAPTER",
            },
        }
    )
    state["current_state"] = "FINAL_V4_2_CANARY"
    state["final_v4_2_canary_progress"] = {
        "status": "PRE_REGISTERED",
        "canary_id": contract["canary_id"],
        "execution_contract": str(CONTRACT_PATH.relative_to(REPO_ROOT)),
        "artifact_root": contract["artifact_root"],
        "logical_call_cap": 4,
        "provider_attempt_cap": 4,
        "retry_count": 0,
        "logical_calls_used": 0,
        "provider_attempts_used": 0,
        "slot_results": [],
        "production_authority": "LEGACY_ADAPTER",
        "cutover_authorized": False,
    }
    save_state(state)
    return state


def run_canary() -> dict[str, Any]:
    contract = _load_contract()
    if RESULT_PATH.exists():
        raise RuntimeError("FINAL_LIVE_CANARY_ALREADY_EXECUTED")
    if os.environ.get(APPROVAL_ENV, "").strip().lower() != "true":
        raise RuntimeError("FINAL_LIVE_CANARY_APPROVAL_MISSING")
    if os.environ.get(EGRESS_ENV, "").strip().lower() != "true":
        raise RuntimeError("FINAL_LIVE_CANARY_DATA_EGRESS_APPROVAL_MISSING")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("FINAL_LIVE_CANARY_ANTHROPIC_CREDENTIAL_MISSING")

    payload, source_hash_before = _payload_from_frozen_sources(contract)
    artifact_root = REPO_ROOT / str(contract["artifact_root"])
    if artifact_root.exists():
        raise RuntimeError("FINAL_LIVE_CANARY_ARTIFACT_ROOT_ALREADY_EXISTS")
    artifact_root.mkdir(parents=True)
    legacy_root = artifact_root / "legacy"
    shadow_root = artifact_root / "shadow"
    legacy_root.mkdir()
    shadow_root.mkdir()
    state = _initialize_state(contract)

    legacy_run_dir = _prepare_run(payload, legacy_root)
    _run_week1_week2_artifact_pipeline(
        legacy_run_dir,
        None,
        structured_adapter_mode_decision=resolve_structured_adapter_mode("legacy"),
    )
    _run_week3_graph_pipeline(legacy_run_dir)
    legacy_snapshot = _authoritative_snapshot(legacy_run_dir)
    legacy_response = _without_times(
        build_research_response(contract["canary_run_id"], output_root=legacy_root)
    )

    shadow_run_dir = _prepare_run(payload, shadow_root)
    executor = FinalLiveCanaryExecutor(
        contract=contract,
        state=state,
        shadow_run_dir=shadow_run_dir,
        legacy_structured_snapshot=legacy_snapshot["structured_agent_outputs.json"],
    )
    _run_week1_week2_artifact_pipeline(
        shadow_run_dir,
        None,
        structured_adapter_mode_decision=resolve_structured_adapter_mode("shadow"),
        structured_adapter_shadow_executor=executor,
    )
    manifest_path = executor.finalize()
    _run_week3_graph_pipeline(shadow_run_dir)

    shadow_snapshot = _authoritative_snapshot(shadow_run_dir)
    shadow_response = _without_times(
        build_research_response(contract["canary_run_id"], output_root=shadow_root)
    )
    authoritative_equal = legacy_snapshot == shadow_snapshot
    response_equal = legacy_response == shadow_response
    replay = verify_live_shadow_exact_replay(shadow_run_dir)
    validation = load_json_record(
        contract["canary_run_id"], SHADOW_VALIDATION_FILENAME, output_root=shadow_root
    )
    shadow_output = load_json_record(
        contract["canary_run_id"], SHADOW_OUTPUT_FILENAME, output_root=shadow_root
    )
    comparison = load_json_record(
        contract["canary_run_id"], SHADOW_COMPARISON_FILENAME, output_root=shadow_root
    )
    reports_by_agent = {
        str(item.get("agent")): item for item in validation.get("reports") or [] if isinstance(item, dict)
    }
    shadow_ids = {
        str(item.get("claim_id"))
        for item in shadow_output.get("records") or []
        if isinstance(item, dict) and item.get("claim_id")
    }
    downstream_text = json.dumps(
        {key: shadow_snapshot[key] for key in AUTHORITATIVE_ARTIFACTS if key != "structured_agent_outputs.json"},
        ensure_ascii=False,
        sort_keys=True,
    )
    shadow_reached_downstream = any(item in downstream_text for item in shadow_ids)

    finalized_slots = []
    passed_count = 0
    accepted_count = 0
    duplicate_seen = False
    unresolved_admitted = 0
    identity_failure_admitted = 0
    candidate_field_seen_anywhere = False
    replay_run_pass = (
        replay.get("status") == "PASS"
        and replay.get("provider_calls") == 0
        and replay.get("accepted_report_count") == 4
    )
    for raw_result in executor.results:
        sidecar = reports_by_agent.get(str(raw_result["agent"]), {})
        accepted = sidecar.get("accepted") is True and int(sidecar.get("shadow_claim_count") or 0) > 0
        accepted_count += int(accepted)
        diagnostics = raw_result["resolution_diagnostics"]
        duplicate_seen = duplicate_seen or any(item.get("duplicate_exact_quote") for item in diagnostics)
        provenance_pass = bool(diagnostics) and all(
            item.get("status") in RESOLUTION_STATUSES_LOCATED for item in diagnostics
        )
        forensic = raw_result.get("rejected_forensics") or {}
        candidate_fields_seen = bool(
            forensic.get("wire_shape_reason_codes")
            and "SHADOW_UNAPPROVED_FIELD" in forensic["wire_shape_reason_codes"]
        )
        candidate_field_seen_anywhere = candidate_field_seen_anywhere or candidate_fields_seen
        identity_pass = all(
            (
                sidecar.get("run_id") == contract["canary_run_id"],
                sidecar.get("ticker") == contract["ticker"],
                sidecar.get("agent") == raw_result["agent"],
                sidecar.get("agent_output_id") == raw_result["canary_agent_output_id"],
                sidecar.get("source_report_sha256") == raw_result["source_report_sha256"],
                sidecar.get("prompt_version") == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_2,
                sidecar.get("prompt_sha256") == STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256,
            )
        )
        sidecar_persisted = bool(sidecar) and (
            sidecar.get("resolution_log") == raw_result["resolution_diagnostics"]
        )
        if accepted and not provenance_pass:
            unresolved_admitted += 1
        if accepted and not identity_pass:
            identity_failure_admitted += 1
        slot_pass = all(
            (
                raw_result["provider_response_received"],
                raw_result["provider_status"] == "success",
                raw_result["parser_status"] == "accepted",
                raw_result["validator_valid"],
                accepted,
                provenance_pass,
                identity_pass,
                sidecar_persisted,
                raw_result["legacy_isolation_pre_downstream"],
                authoritative_equal,
                response_equal,
                not shadow_reached_downstream,
                replay_run_pass,
            )
        )
        passed_count += int(slot_pass)
        finalized = {
            **raw_result,
            "sidecar_accepted": accepted,
            "sidecar_reason_codes": list(sidecar.get("reason_codes") or []),
            "candidate_fields_seen": candidate_fields_seen,
            "candidate_binding_exercised": False,
            "exact_provenance": "PASS" if provenance_pass else "FAIL",
            "identity_binding": "PASS" if identity_pass else "FAIL",
            "sidecar_persistence": "PASS" if sidecar_persisted else "FAIL",
            "legacy_isolation": "PASS" if authoritative_equal and response_equal else "FAIL",
            "shadow_reached_authoritative_downstream": shadow_reached_downstream,
            "exact_replay": "PASS" if replay_run_pass else "FAIL",
            "slot_status": "PASS" if slot_pass else "FAIL",
        }
        finalized_slots.append(finalized)
        _write_json(
            artifact_root / "slot_results" / f"{int(raw_result['logical_call_number']):02d}-{raw_result['family']}.json",
            finalized,
        )

    manifest = (
        verify_semantic_manifest(manifest_path).__dict__
        if manifest_path is not None
        else {"valid": False, "reason_codes": ["SEMANTIC_MANIFEST_MISSING"]}
    )
    logical_calls = len(executor.results)
    provider_attempts = sum(int(item.get("provider_attempt_count") or 0) for item in executor.results)
    status = (
        "PASS"
        if passed_count == 4
        and logical_calls == 4
        and provider_attempts == 4
        and manifest.get("valid") is True
        and source_hash_before == _sha256_file(REPO_ROOT / str(contract["source_artifact"]))
        and unresolved_admitted == 0
        and identity_failure_admitted == 0
        else "FAIL"
    )
    result = {
        "schema_version": "comqutor.phase1_v4_2.final_live_canary_runtime_result.v1",
        "canary_id": contract["canary_id"],
        "status": status,
        "production_authority": "LEGACY_ADAPTER",
        "production_cutover": "AUTHORIZED_PENDING_LOCAL_CUTOVER" if status == "PASS" else "NOT_RUN",
        "provider": contract["provider"],
        "model": contract["model"],
        "prompt_version": contract["prompt_version"],
        "prompt_sha256": contract["prompt_sha256"],
        "logical_calls_used": logical_calls,
        "provider_attempts_used": provider_attempts,
        "retries_used": sum(int(item.get("retry_count") or 0) for item in executor.results),
        "subagents": 0,
        "post_canary_provider_calls": 0,
        "slots_accepted": accepted_count,
        "slots_passed": passed_count,
        "per_slot_results": finalized_slots,
        "duplicate_exact_evidence_seen": duplicate_seen,
        "candidate_binding_active": False,
        "candidate_fields_seen_in_any_response": candidate_field_seen_anywhere,
        "ambiguous_or_unresolved_evidence_admitted": unresolved_admitted,
        "identity_failure_admitted": identity_failure_admitted,
        "authoritative_artifacts_equal": authoritative_equal,
        "api_response_equal": response_equal,
        "shadow_output_reached_authoritative_downstream": shadow_reached_downstream,
        "exact_replay": replay,
        "semantic_manifest_verification": manifest,
        "source_artifact_unchanged": source_hash_before == _sha256_file(REPO_ROOT / str(contract["source_artifact"])),
        "legacy_snapshot_sha256": sha256_canonical_json(legacy_snapshot),
        "shadow_snapshot_sha256": sha256_canonical_json(shadow_snapshot),
        "comparison_artifact_sha256": sha256_canonical_json(comparison),
        "runtime_artifact_root": contract["artifact_root"],
        "completed_at": _now(),
    }
    _write_json(artifact_root / "final_live_canary_runtime_result.json", result)
    _write_json(RESULT_PATH, result)
    progress = state["final_v4_2_canary_progress"]
    progress.update(
        {
            "status": status,
            "completed_at": result["completed_at"],
            "logical_calls_used": logical_calls,
            "provider_attempts_used": provider_attempts,
            "slots_passed": passed_count,
            "slots_accepted": accepted_count,
            "exact_replay": replay.get("status"),
            "exact_replay_provider_calls": replay.get("provider_calls"),
            "production_authority": "LEGACY_ADAPTER",
            "cutover_authorized": status == "PASS",
            "runtime_result": str(RESULT_PATH.relative_to(REPO_ROOT)),
        }
    )
    state["production_authority"] = "LEGACY_ADAPTER"
    state["next_action"] = (
        "FINAL_V4_2_CANARY_PASS; execute authorized local production cutover with zero further Provider calls."
        if status == "PASS"
        else "FINAL_V4_2_CANARY_FAIL; retain Legacy authority and stop Section 5.1."
    )
    save_state(state)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-provider-canary", action="store_true")
    args = parser.parse_args()
    if not args.execute_provider_canary:
        print("FINAL_LIVE_CANARY_NOT_EXECUTED: pass --execute-provider-canary")
        return 2
    try:
        result = run_canary()
    except Exception as exc:
        print(f"FINAL_V4_2_CANARY_EXECUTION_ERROR={type(exc).__name__}")
        print(str(exc))
        return 1
    print(f"FINAL_V4_2_CANARY={result['status']}")
    print(f"CANARY_SLOTS_PASSED={result['slots_passed']}/4")
    print(f"LOGICAL_CALLS={result['logical_calls_used']}/4")
    print(f"REAL_PROVIDER_ATTEMPTS={result['provider_attempts_used']}/4")
    print(f"RETRIES={result['retries_used']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
