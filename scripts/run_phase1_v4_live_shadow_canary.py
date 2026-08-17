#!/usr/bin/env python3
"""Run the pre-registered Phase 1 v4 live-shadow Canary exactly once.

This is an audit/execution entrypoint, not production runtime code.  It uses
the real integrated live-shadow hook with the frozen v4 Provider path, four
pre-registered reports, one sequential Provider attempt per report, and no
retries.  It never authorizes primary mode or production cutover.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from copy import deepcopy
from datetime import UTC, datetime
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
from comqutor_alpha.llm_runtime.canonical_json import (  # noqa: E402
    sha256_canonical_json,
)
from comqutor_alpha.llm_runtime.manifest import verify_semantic_manifest  # noqa: E402
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession  # noqa: E402
from comqutor_alpha.research_profiles import (  # noqa: E402
    ANTHROPIC_PROFILE_ID,
    get_research_profile,
)
from comqutor_alpha.storage.file_store import load_json_record  # noqa: E402
from comqutor_alpha.structure_engine.structured_output_live_shadow import (  # noqa: E402
    SHADOW_COMPARISON_FILENAME,
    SHADOW_OUTPUT_FILENAME,
    SHADOW_VALIDATION_FILENAME,
    ShadowAttemptResult,
    resolve_structured_adapter_mode,
    verify_live_shadow_exact_replay,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v4 import (  # noqa: E402
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4,
)
from comqutor_alpha.structure_engine.structured_output_shadow_v4 import (  # noqa: E402
    summarize_resolution_log,
)
from scripts.run_phase1_master import (  # noqa: E402
    HARD_CAP_LOGICAL_CALLS,
    HARD_CAP_PROVIDER_ATTEMPTS,
    _commit_budget,
    load_state,
    save_state,
    transition,
)

CONTRACT_PATH = (
    REPO_ROOT
    / "docs/audit_artifacts/phase1_master/"
    "phase1_v4_live_shadow_canary_execution_contract.json"
)
RESULT_PATH = (
    REPO_ROOT
    / "docs/audit_artifacts/phase1_master/phase1_v4_live_shadow_canary_runtime_result.json"
)
APPROVAL_ENV = "COMQUTOR_PHASE1_LIVE_SHADOW_CANARY_APPROVED"
EGRESS_ENV = "COMQUTOR_PHASE1_LIVE_SHADOW_CANARY_DATA_EGRESS_APPROVED"
TIME_KEYS = frozenset(
    {"timestamp", "created_at", "updated_at", "generated_at", "completed_at"}
)
AUTHORITATIVE_ARTIFACTS = (
    "structured_agent_outputs.json",
    "alpha_matches.json",
    "extracted_structures.json",
    "structure_graph.json",
    "alpha_activations.json",
    "conflicts.json",
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    staging.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(staging, path)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _without_times(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_times(item)
            for key, item in value.items()
            if key not in TIME_KEYS
        }
    if isinstance(value, list):
        return [_without_times(item) for item in value]
    return value


def _load_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if contract.get("status") != "PRE_REGISTERED_BEFORE_PROVIDER_CALLS":
        raise RuntimeError("CANARY_EXECUTION_CONTRACT_NOT_PRE_REGISTERED")
    if contract.get("logical_call_cap") != 4 or contract.get("provider_attempt_cap") != 4:
        raise RuntimeError("CANARY_EXECUTION_CAP_INVALID")
    if contract.get("retry_count") != 0 or len(contract.get("slots") or []) != 4:
        raise RuntimeError("CANARY_EXECUTION_POLICY_INVALID")
    if contract.get("prompt_version") != STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4:
        raise RuntimeError("CANARY_PROMPT_VERSION_MISMATCH")
    if contract.get("prompt_sha256") != STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256:
        raise RuntimeError("CANARY_PROMPT_HASH_MISMATCH")
    if contract.get("production_authority") != "LEGACY_ADAPTER":
        raise RuntimeError("CANARY_PRODUCTION_AUTHORITY_INVALID")
    return contract


def _verify_source_and_build_payload(contract: dict[str, Any]) -> tuple[dict[str, Any], str]:
    source_path = REPO_ROOT / str(contract["source_artifact"])
    source_hash_before = _sha256_file(source_path)
    raw = json.loads(source_path.read_text(encoding="utf-8"))
    by_id = {
        str(item.get("agent_output_id")): item
        for item in raw.get("agent_outputs") or []
        if isinstance(item, dict)
    }
    selected: list[dict[str, Any]] = []
    for expected_slot, slot in enumerate(contract["slots"], start=1):
        if slot.get("slot") != expected_slot:
            raise RuntimeError("CANARY_SLOT_ORDER_DRIFT")
        record = by_id.get(str(slot["source_agent_output_id"]))
        if record is None:
            raise RuntimeError("CANARY_SOURCE_REPORT_MISSING")
        report = str(record.get("raw_output") or "")
        if _sha256_text(report) != slot.get("source_report_sha256"):
            raise RuntimeError("CANARY_SOURCE_REPORT_HASH_MISMATCH")
        if record.get("agent") != slot.get("agent"):
            raise RuntimeError("CANARY_SOURCE_AGENT_MISMATCH")
        selected.append(
            {
                "agent": record["agent"],
                "tradingagents_agent": record.get("tradingagents_agent") or record["agent"],
                "source_field": record.get("source_field") or "canary_source_report",
                "raw_output": report,
            }
        )
    payload = {
        "run_id": contract["canary_run_id"],
        "ticker": contract["ticker"],
        "analysis_date": "2026-08-10",
        "selected_analysts": ["fundamentals", "news", "sentiment", "market"],
        "offline_raw_agent_outputs": selected,
    }
    return payload, source_hash_before


def _prepare_run(payload: dict[str, Any], output_root: Path) -> Path:
    _run_id, run_dir = _create_offline_run(deepcopy(payload), output_root)
    return Path(run_dir)


def _read_artifact(run_dir: Path, filename: str) -> dict[str, Any]:
    return json.loads((run_dir / filename).read_text(encoding="utf-8"))


def _authoritative_snapshot(run_dir: Path) -> dict[str, Any]:
    return {
        name: _without_times(_read_artifact(run_dir, name))
        for name in AUTHORITATIVE_ARTIFACTS
    }


class CanaryExecutor:
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

        profile = get_research_profile(ANTHROPIC_PROFILE_ID)
        if (
            profile.profile_id != self.profile_id
            or profile.llm_provider != self.provider
            or profile.quick_think_llm != self.model
        ):
            raise RuntimeError("CANARY_PROVIDER_IDENTITY_DRIFT")

        runtime_dir = shadow_run_dir / "structured_adapter_shadow_runtime"
        runtime_dir.mkdir(parents=True, exist_ok=False)
        self.runtime_dir = runtime_dir
        self.session = SemanticRuntimeSession(
            run_id=shadow_run_dir.name,
            output_directory=runtime_dir,
            execution_mode="shadow",
            provider=self.provider,
            model=self.model,
            profile_id=self.profile_id,
        )

        # The frozen provider seam is 180s/one transient retry.  This later,
        # stricter Canary authorization explicitly narrows retry_count to 0.
        # The override is process-local and occurs before gateway creation;
        # no production source, prompt, model, timeout, or parser is changed.
        if provider_module.STRUCTURED_CLAIM_SHADOW_MAX_RETRIES != 1:
            raise RuntimeError("CANARY_FROZEN_RETRY_BASELINE_DRIFT")
        provider_module.STRUCTURED_CLAIM_SHADOW_MAX_RETRIES = 0
        self.provider_module = provider_module
        self.gateway, gateway_info = provider_module.build_phase1_master_provider_gateway(
            profile=profile,
            run_id=shadow_run_dir.name,
            output_root=shadow_run_dir.parent,
            logical_call_limit=4,
            semantic_runtime=self.session,
        )
        if gateway_info.timeout_seconds != float(contract["timeout_seconds"]):
            raise RuntimeError("CANARY_TIMEOUT_DRIFT")
        if gateway_info.max_retries != 0 or self.gateway.max_retries != 0:
            raise RuntimeError("CANARY_ZERO_RETRY_NOT_ENFORCED")
        if gateway_info.max_provider_attempts != 4 or self.gateway.max_calls != 4:
            raise RuntimeError("CANARY_PROVIDER_ATTEMPT_CAP_NOT_ENFORCED")

    def _record(
        self,
        *,
        context: Any,
        slot: dict[str, Any],
        started_at: str,
        ended_at: str,
        latency_ms: float,
        bundle: dict[str, Any] | None,
        invocation: Any,
        resolution_log: list[dict[str, Any]],
        attempt_count: int,
        unexpected_error: BaseException | None,
    ) -> dict[str, Any]:
        if attempt_count > 1:
            raise RuntimeError("CANARY_PROVIDER_ATTEMPT_CAP_BREACHED")
        retry_count = int(getattr(invocation, "retry_count", 0) or 0)
        if retry_count != 0:
            raise RuntimeError("CANARY_RETRY_OCCURRED")

        trace = getattr(invocation, "trace_handle", None)
        validation = (bundle or {}).get("validation_summary") or {}
        current_structured = _without_times(
            _read_artifact(self.shadow_run_dir, "structured_agent_outputs.json")
        )
        legacy_pre_downstream_unchanged = current_structured == self.legacy_structured_snapshot
        result = {
            "schema_version": "comqutor.phase1_v4.live_shadow_canary_slot.v1",
            "canary_id": self.contract["canary_id"],
            "logical_call_number": int(slot["slot"]),
            "provider_attempt_number": sum(
                int(item.get("provider_attempt_count") or 0) for item in self.results
            )
            + attempt_count,
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
            "prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4,
            "prompt_sha256": STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256,
            "provider": self.provider,
            "model": self.model,
            "profile_id": self.profile_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "latency_ms": round(latency_ms, 3),
            "provider_called": bool(getattr(invocation, "provider_called", attempt_count > 0)),
            "provider_response_received": bool(
                getattr(invocation, "response_received", False)
            ),
            "provider_status": getattr(invocation, "provider_status", "execution_error"),
            "provider_attempt_count": attempt_count,
            "retry_count": retry_count,
            "attempt_history": [
                dict(item) for item in (getattr(invocation, "attempt_history", ()) or ())
            ],
            "token_usage": (
                dict(invocation.token_usage)
                if invocation is not None and invocation.token_usage
                else None
            ),
            "cost_usd": None,
            "cost_note": "Provider pricing is not frozen in repository; token usage retained",
            "parser_status": validation.get("status", "parser_error"),
            "validator_valid": bool(validation.get("valid", False)),
            "reason_codes": list(validation.get("reason_codes") or []),
            "shadow_status": "accepted" if validation.get("valid") is True else "rejected",
            "claim_count": len((bundle or {}).get("claims") or []),
            "evidence_resolution": summarize_resolution_log(resolution_log),
            "legacy_isolation_pre_downstream": legacy_pre_downstream_unchanged,
            "production_authority": "LEGACY_ADAPTER",
            "sidecar_paths": [
                SHADOW_OUTPUT_FILENAME,
                SHADOW_VALIDATION_FILENAME,
                SHADOW_COMPARISON_FILENAME,
            ],
            "unexpected_error_type": (
                type(unexpected_error).__name__ if unexpected_error is not None else None
            ),
            "exact_replay": "PENDING_RUN_LEVEL_SIDECAR_FINALIZATION",
        }
        slot_path = (
            self.shadow_run_dir.parent.parent
            / "slot_results"
            / f"{int(slot['slot']):02d}-{slot['family']}.json"
        )
        _write_json(slot_path, result)

        self.results.append(result)
        self.state["live_shadow_canary_progress"]["slot_results"] = self.results
        self.state["live_shadow_canary_progress"]["logical_calls_used"] = len(self.results)
        self.state["live_shadow_canary_progress"]["provider_attempts_used"] = sum(
            int(item.get("provider_attempt_count") or 0) for item in self.results
        )
        self.state["live_shadow_canary_progress"]["last_recorded_at"] = ended_at
        _commit_budget(
            self.state,
            1,
            attempt_count,
            f"live_shadow_canary:{self.contract['canary_id']}:{slot['family']}",
            global_event={
                "schema_version": "comqutor.phase1_global_provider_call_ledger.v1",
                "event_id": (
                    f"phase1_master:live_shadow_canary:{self.contract['canary_id']}:"
                    f"{slot['source_agent_output_id']}:"
                    f"{STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4}"
                ),
                "recorded_at": ended_at,
                "source_phase": "PHASE_1_MASTER",
                "stage": "LIVE_SHADOW_CANARY",
                "task": "structured_claim_shadow",
                "report_id": slot["source_agent_output_id"],
                "prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4,
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
            raise RuntimeError("CANARY_LOGICAL_CALL_CAP_BREACHED")
        slot = self.slot_by_agent.get(str(context.agent))
        if slot is None or int(slot["slot"]) != len(self.results) + 1:
            raise RuntimeError("CANARY_RUNTIME_SLOT_ORDER_DRIFT")
        if _sha256_text(context.source_report) != slot["source_report_sha256"]:
            raise RuntimeError("CANARY_RUNTIME_SOURCE_HASH_MISMATCH")

        started_at = _now()
        started_monotonic = time.monotonic()
        calls_before = self.gateway.call_count
        bundle: dict[str, Any] | None = None
        invocation = None
        resolution_log: list[dict[str, Any]] = []
        unexpected_error: BaseException | None = None
        try:
            bundle, invoker, _candidates, resolution_log = (
                self.provider_module.run_real_provider_shadow_smoke_for_report_v4(
                    gateway=self.gateway,
                    source_report=context.source_report,
                    run_id=context.run_id,
                    ticker=context.ticker,
                    agent=context.agent,
                    agent_output_id=context.agent_output_id,
                    factor_vocabulary=list(context.factor_vocabulary),
                )
            )
            invocation = invoker.last_invocation
        except Exception as exc:
            unexpected_error = exc
        ended_at = _now()
        latency_ms = (time.monotonic() - started_monotonic) * 1000.0
        attempt_count = self.gateway.call_count - calls_before
        result = self._record(
            context=context,
            slot=slot,
            started_at=started_at,
            ended_at=ended_at,
            latency_ms=latency_ms,
            bundle=bundle,
            invocation=invocation,
            resolution_log=resolution_log,
            attempt_count=attempt_count,
            unexpected_error=unexpected_error,
        )
        if unexpected_error is not None:
            raise unexpected_error
        if bundle is None:
            raise RuntimeError("CANARY_BUNDLE_MISSING")
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
            resolution_log=tuple(resolution_log),
        )

    def finalize(self) -> Path | None:
        return self.session.finalize_manifest(complete=len(self.results) == 4)


def _initialize_state(contract: dict[str, Any], artifact_root: Path) -> dict[str, Any]:
    state = load_state()
    progress = state.get("live_shadow_canary_progress")
    resuming_pre_provider = (
        state.get("current_state") == "LIVE_SHADOW_CANARY"
        and isinstance(progress, dict)
        and progress.get("canary_id") == contract["canary_id"]
        and progress.get("status") == "PRE_REGISTERED"
        and int(progress.get("logical_calls_used") or 0) == 0
        and int(progress.get("provider_attempts_used") or 0) == 0
        and not progress.get("slot_results")
    )
    if resuming_pre_provider:
        return state
    if state.get("current_state") != "LIVE_SHADOW_INTEGRATION":
        raise RuntimeError("CANARY_START_STATE_INVALID")
    if state.get("production_authority") != "LEGACY_ADAPTER":
        raise RuntimeError("CANARY_PRODUCTION_AUTHORITY_CHANGED")
    if state.get("cumulative_logical_calls") + 4 > HARD_CAP_LOGICAL_CALLS:
        raise RuntimeError("CANARY_MASTER_LOGICAL_BUDGET_INSUFFICIENT")
    if state.get("cumulative_provider_attempts") + 4 > HARD_CAP_PROVIDER_ATTEMPTS:
        raise RuntimeError("CANARY_MASTER_PROVIDER_BUDGET_INSUFFICIENT")
    state["live_shadow_canary_progress"] = {
        "status": "PRE_REGISTERED",
        "canary_id": contract["canary_id"],
        "execution_contract": str(CONTRACT_PATH.relative_to(REPO_ROOT)),
        "artifact_root": str(artifact_root.relative_to(REPO_ROOT)),
        "logical_call_cap": 4,
        "provider_attempt_cap": 4,
        "retry_count": 0,
        "logical_calls_used": 0,
        "provider_attempts_used": 0,
        "slot_results": [],
        "production_authority": "LEGACY_ADAPTER",
        "cutover_authorized": False,
    }
    transition(
        state,
        "LIVE_SHADOW_CANARY",
        {
            "canary_id": contract["canary_id"],
            "execution_contract_pre_registered": True,
            "slots": [item["family"] for item in contract["slots"]],
            "logical_call_cap": 4,
            "provider_attempt_cap": 4,
            "retry_count": 0,
            "production_authority_unchanged": "LEGACY_ADAPTER",
        },
    )
    return state


def run_canary() -> dict[str, Any]:
    contract = _load_contract()
    if RESULT_PATH.exists():
        raise RuntimeError("CANARY_ALREADY_EXECUTED_RESULT_EXISTS")
    if os.environ.get(APPROVAL_ENV, "").strip().lower() != "true":
        raise RuntimeError("CANARY_EXECUTION_APPROVAL_MISSING")
    if os.environ.get(EGRESS_ENV, "").strip().lower() != "true":
        raise RuntimeError("CANARY_DATA_EGRESS_APPROVAL_MISSING")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("CANARY_ANTHROPIC_CREDENTIAL_MISSING")

    payload, source_hash_before = _verify_source_and_build_payload(contract)
    artifact_root = REPO_ROOT / str(contract["artifact_root"])
    if artifact_root.exists():
        raise RuntimeError("CANARY_ARTIFACT_ROOT_ALREADY_EXISTS")
    artifact_root.mkdir(parents=True)
    legacy_root = artifact_root / "legacy"
    shadow_root = artifact_root / "shadow"
    legacy_root.mkdir()
    shadow_root.mkdir()
    state = _initialize_state(contract, artifact_root)

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
    executor = CanaryExecutor(
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

    shadow_ids = {
        str(item.get("claim_id"))
        for item in shadow_output.get("records") or []
        if isinstance(item, dict) and item.get("claim_id")
    }
    downstream_text = json.dumps(
        {
            key: shadow_snapshot[key]
            for key in AUTHORITATIVE_ARTIFACTS
            if key != "structured_agent_outputs.json"
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    shadow_reached_downstream = any(claim_id in downstream_text for claim_id in shadow_ids)

    reports_by_agent = {
        str(item.get("agent")): item
        for item in validation.get("reports") or []
        if isinstance(item, dict)
    }
    finalized_slots: list[dict[str, Any]] = []
    accepted_count = 0
    passed_count = 0
    for result in executor.results:
        sidecar = reports_by_agent.get(str(result["agent"]), {})
        accepted = sidecar.get("accepted") is True and int(sidecar.get("shadow_claim_count") or 0) > 0
        if accepted:
            accepted_count += 1
        resolution = result["evidence_resolution"]
        provenance_pass = (
            accepted
            and int(resolution.get("no_exact_match") or 0) == 0
            and int(resolution.get("ambiguous_multiple_match") or 0) == 0
            and int(resolution.get("invalid_quote") or 0) == 0
        )
        replay_status = "PASS" if accepted and replay.get("status") == "PASS" else (
            "NOT_APPLICABLE" if not accepted else "FAIL"
        )
        slot_pass = all(
            (
                result["provider_response_received"],
                result["provider_status"] == "success",
                accepted,
                provenance_pass,
                result["legacy_isolation_pre_downstream"],
                authoritative_equal,
                response_equal,
                not shadow_reached_downstream,
                replay_status == "PASS",
            )
        )
        passed_count += int(slot_pass)
        finalized = {
            **result,
            "sidecar_accepted": accepted,
            "sidecar_reason_codes": list(sidecar.get("reason_codes") or []),
            "claim_count": int(sidecar.get("shadow_claim_count") or 0),
            "provenance": "PASS" if provenance_pass else "FAIL",
            "legacy_isolation": "PASS" if authoritative_equal and response_equal else "FAIL",
            "shadow_reached_authoritative_downstream": shadow_reached_downstream,
            "exact_replay": replay_status,
            "slot_status": "PASS" if slot_pass else "FAIL",
        }
        finalized_slots.append(finalized)
        slot_path = (
            artifact_root
            / "slot_results"
            / f"{int(result['logical_call_number']):02d}-{result['family']}.json"
        )
        _write_json(slot_path, finalized)

    manifest_verification = (
        verify_semantic_manifest(manifest_path).__dict__
        if manifest_path is not None
        else {"valid": False, "reason_codes": ["CANARY_SEMANTIC_MANIFEST_MISSING"]}
    )
    source_hash_after = _sha256_file(REPO_ROOT / str(contract["source_artifact"]))
    logical_calls_used = len(executor.results)
    provider_attempts_used = sum(
        int(item.get("provider_attempt_count") or 0) for item in executor.results
    )
    status = (
        "PASS"
        if passed_count == 4
        and logical_calls_used == 4
        and provider_attempts_used <= 4
        and replay.get("status") == "PASS"
        and manifest_verification.get("valid") is True
        and source_hash_before == source_hash_after
        else "FAIL"
    )
    result = {
        "schema_version": "comqutor.phase1_v4.live_shadow_canary_runtime_result.v1",
        "canary_id": contract["canary_id"],
        "status": status,
        "started_from_state": "LIVE_SHADOW_INTEGRATION",
        "production_authority": "LEGACY_ADAPTER",
        "provider": contract["provider"],
        "model": contract["model"],
        "prompt_version": contract["prompt_version"],
        "prompt_sha256": contract["prompt_sha256"],
        "logical_calls_used": logical_calls_used,
        "provider_attempts_used": provider_attempts_used,
        "retries_used": sum(int(item.get("retry_count") or 0) for item in executor.results),
        "slots_planned": 4,
        "slots_executed": logical_calls_used,
        "slots_accepted": accepted_count,
        "slots_passed": passed_count,
        "per_slot_results": finalized_slots,
        "authoritative_artifacts_equal": authoritative_equal,
        "api_response_equal": response_equal,
        "shadow_output_reached_authoritative_downstream": shadow_reached_downstream,
        "exact_replay": replay,
        "semantic_manifest_verification": manifest_verification,
        "source_artifact_unchanged": source_hash_before == source_hash_after,
        "legacy_snapshot_sha256": sha256_canonical_json(legacy_snapshot),
        "shadow_snapshot_sha256": sha256_canonical_json(shadow_snapshot),
        "comparison_artifact_sha256": sha256_canonical_json(comparison),
        "runtime_artifact_root": str(artifact_root.relative_to(REPO_ROOT)),
        "completed_at": _now(),
        "production_cutover": "NOT_RUN",
    }
    _write_json(artifact_root / "canary_runtime_result.json", result)
    _write_json(RESULT_PATH, result)

    state["live_shadow_canary_progress"] = {
        **state["live_shadow_canary_progress"],
        "status": status,
        "completed_at": result["completed_at"],
        "logical_calls_used": logical_calls_used,
        "provider_attempts_used": provider_attempts_used,
        "slots_passed": passed_count,
        "slots_accepted": accepted_count,
        "exact_replay": replay.get("status"),
        "exact_replay_provider_calls": replay.get("provider_calls"),
        "production_authority": "LEGACY_ADAPTER",
        "ready_for_production_cutover": status == "PASS",
        "production_cutover": "NOT_RUN",
        "runtime_result": str(RESULT_PATH.relative_to(REPO_ROOT)),
    }
    state["production_authority"] = "LEGACY_ADAPTER"
    state["next_action"] = (
        "READY_FOR_PRODUCTION_CUTOVER; stop until a separate product-owner instruction."
        if status == "PASS"
        else "LIVE_SHADOW_CANARY_FAILED; production cutover is not authorized."
    )
    save_state(state)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-provider-canary", action="store_true")
    args = parser.parse_args()
    if not args.execute_provider_canary:
        print("CANARY_NOT_EXECUTED: pass --execute-provider-canary")
        return 2
    try:
        result = run_canary()
    except Exception as exc:
        print(f"LIVE_SHADOW_CANARY_EXECUTION_ERROR={type(exc).__name__}")
        print(str(exc))
        return 1
    print(f"LIVE_SHADOW_CANARY={result['status']}")
    print(f"CANARY_SLOTS_PASSED={result['slots_passed']}/4")
    print(f"LIVE_CANARY_LOGICAL_CALLS_USED={result['logical_calls_used']}/4")
    print(f"REAL_PROVIDER_ATTEMPTS_USED={result['provider_attempts_used']}/4")
    print(f"RETRIES_USED={result['retries_used']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
