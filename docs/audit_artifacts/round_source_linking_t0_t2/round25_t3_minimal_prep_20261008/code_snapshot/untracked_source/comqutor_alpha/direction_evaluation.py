"""Direction (``evidence_stance_classifier``) evaluation of a run whose Alpha classification is already saved.

2026-10-07 (round 17). The classification recovery left 162 matched claims whose stance toward their matched Alpha
is still the deterministic one the mapping step attaches. This module runs the production direction task for
exactly those (claim, Alpha) pairs and keeps everything auditable:

* the work list is rebuilt with the production request builder (``build_stance_request_items`` + ``chunk_items``);
* every batch goes through the production per-batch functions (``_process_batch`` /
  ``_process_batches_concurrently``), so a direction, a counter-Alpha or a fallback is only ever written by the
  production code -- nothing here sets a stance, a success state or a confidence;
* every Provider call goes through ``TaskAllowlistGateway`` (only ``evidence_stance_classifier``), with a request
  cap that also counts requests audited by earlier processes;
* the FIRST batch is a protocol check: if it does not produce a protocol-valid response, nothing else is
  scheduled (a timeout leaves no response to verify, and spending the remaining budget on a configuration that
  just failed would be a blind retry);
* a failure is never a neutral, a determined direction or a success: it stays the production deterministic
  fallback, stamped with its real reason, and is reported as such.

Zero Provider calls happen at import time or in any function that is not handed a gateway.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from comqutor_alpha.classification_recovery import STANCE_TASK, TaskAllowlistGateway, _canonical_json
from comqutor_alpha.structure_engine import evidence_stance_llm as esl
from comqutor_alpha.structure_engine import week2_llm

DIRECTION_RESULTS_SCHEMA_VERSION = "comqutor.evidence_stance_direction_results.v1"
CHECKPOINT_SCHEMA_VERSION = "comqutor.direction_checkpoint.v1"
AUTH_FAILURE_STATUS_CODES = frozenset({401, 403})


def new_direction_execution_id() -> str:
    from datetime import UTC, datetime
    from uuid import uuid4

    return f"direction-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"


# A response that was never obtained (or never parsed): the whole batch fell back for ONE of these reasons.
WHOLE_BATCH_FAILURE_REASONS = frozenset(
    {esl.FALLBACK_TIMEOUT, esl.FALLBACK_PROVIDER_ERROR, esl.FALLBACK_MALFORMED_RESPONSE}
)
EXPECTED_REQUEST_URL = "https://api.deepseek.com/chat/completions"
EXPECTED_REQUEST_BODY_KEYS = frozenset({"messages", "model", "stream"})


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


class DirectionPlan:
    """The matches (a private deep copy of the parent's), the production request items built from them, and the
    batches. ``items`` hold references to the candidate dicts inside ``matches``: the production functions write
    their results onto exactly those dicts."""

    def __init__(self, matches: list[dict], items: list[Any], batches: list[list[Any]]) -> None:
        self.matches = matches
        self.items = items
        self.batches = batches

    def batch_claim_ids(self, index: int) -> list[str]:
        return [item.claim_id for item in self.batches[index]]

    def pair_keys(self, index: int) -> list[tuple[str, str]]:
        return [(item.claim_id, item.target_alpha_id) for item in self.batches[index]]


def payload_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def build_direction_plan(parent_alpha_matches: Mapping[str, Any], taxonomy: Mapping[str, Any]) -> DirectionPlan:
    matches = copy.deepcopy(list(parent_alpha_matches.get("matches") or []))
    items = esl.build_stance_request_items(matches, taxonomy)
    return DirectionPlan(matches, items, esl.chunk_items(items, esl.BATCH_SIZE))


def plan_signature(plan: DirectionPlan) -> list[dict[str, Any]]:
    return [
        {
            "batch_index": index,
            "pairs": [
                {"claim_id": item.claim_id, "target_alpha_id": item.target_alpha_id, "request_payload_sha256": payload_sha256(item.payload)}
                for item in batch
            ],
        }
        for index, batch in enumerate(plan.batches)
    ]


def plan_sha256(plan: DirectionPlan, extra: Mapping[str, Any] | None = None) -> str:
    return hashlib.sha256(_canonical_json({"signature": plan_signature(plan), "extra": dict(extra or {})}).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Gateway preflight and the wire check
# ---------------------------------------------------------------------------


def preflight_direction_gateway(
    gateway: Any, *, hard_cap: int, prior_sent: int, concurrency: int, expected_model: str, expected_timeout: float
) -> dict[str, Any]:
    """Refuses (before any send) a Gateway that is not configured exactly as the frozen direction plan requires,
    and returns the EFFECTIVE configuration for the report."""
    problems = []
    if gateway.max_retries != 0:
        problems.append(f"application max_retries={gateway.max_retries} (must be 0)")
    stance_retries = week2_llm._resolve_task_max_retries(STANCE_TASK, gateway.max_retries)
    if stance_retries != 0:
        problems.append(f"effective evidence_stance_classifier retries={stance_retries} (must be 0)")
    if gateway.max_calls > hard_cap - prior_sent:
        problems.append(f"gateway max_calls={gateway.max_calls} exceeds the remaining cap {hard_cap - prior_sent}")
    if not getattr(gateway, "_audit_enabled", False):
        problems.append("request/response audit is not enabled")
    if concurrency != 4 or week2_llm.resolve_evidence_stance_concurrency() != concurrency:
        problems.append(f"stance concurrency requested={concurrency}, resolved={week2_llm.resolve_evidence_stance_concurrency()} (frozen value is 4)")
    if gateway.model_name != expected_model:
        problems.append(f"model={gateway.model_name!r} (frozen model is {expected_model!r})")
    if float(gateway.timeout_seconds) != float(expected_timeout):
        problems.append(f"timeout_seconds={gateway.timeout_seconds} (frozen value is {expected_timeout})")
    if gateway._resolve_task_model(STANCE_TASK) is not gateway._model:
        problems.append("a per-task model override is active for evidence_stance_classifier")
    if problems:
        raise RuntimeError("direction preflight refused to start: " + "; ".join(problems))
    return {
        "application_max_retries": gateway.max_retries,
        "effective_stance_task_retries": stance_retries,
        "gateway_max_calls": gateway.max_calls,
        "hard_request_cap": hard_cap,
        "requests_already_audited": prior_sent,
        "audit_enabled": True,
        "stance_concurrency": concurrency,
        "timeout_seconds": gateway.timeout_seconds,
        "provider": gateway.provider,
        "model": gateway.model_name,
        "per_task_model_override": None,
    }


def request_wire_problem(record: Mapping[str, Any], *, expected_model: str, expected_timeout: float) -> str | None:
    """What one AUDITED request actually carried against the frozen config; None when it matches."""
    try:
        body = json.loads(record["body"])
    except Exception:
        return "request body is not valid JSON"
    if str(record.get("url")) != EXPECTED_REQUEST_URL:
        return f"url={record.get('url')!r}"
    if set(body) != EXPECTED_REQUEST_BODY_KEYS or body.get("stream") is not False:
        return f"body keys={sorted(body)!r} stream={body.get('stream')!r}"
    if body.get("model") != expected_model:
        return f"model={body.get('model')!r}"
    headers = {str(k).lower(): str(v) for k, v in (record.get("headers") or {}).items()}
    if headers.get("x-stainless-read-timeout") != str(float(expected_timeout)):
        return f"read-timeout header={headers.get('x-stainless-read-timeout')!r}"
    if headers.get("x-stainless-retry-count") != "0":
        return f"retry-count header={headers.get('x-stainless-retry-count')!r}"
    return None


# ---------------------------------------------------------------------------
# Audit reading and checkpoint
# ---------------------------------------------------------------------------


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    path = Path(path)
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def audit_paths(run_output_root: Path, execution_id: str) -> tuple[Path, Path]:
    return (
        Path(run_output_root) / execution_id / week2_llm.PROVIDER_REQUEST_AUDIT_ARTIFACT_PATH,
        Path(run_output_root) / execution_id / week2_llm.PROVIDER_RESPONSE_AUDIT_ARTIFACT_PATH,
    )


def load_checkpoint(path: Path) -> dict[str, Any]:
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text())
    return {"schema_version": CHECKPOINT_SCHEMA_VERSION, "batches": {}}


def save_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(checkpoint, indent=2, default=str))
    tmp.replace(path)


def _pair_state(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stance": candidate.get("evidence_stance"),
        "counter_alpha_id": candidate.get("counter_alpha_id"),
        "method": candidate.get("stance_method"),
        "fallback_reason": candidate.get("stance_fallback_reason"),
        "version": candidate.get("evidence_stance_version"),
        "confidence_band": candidate.get("stance_confidence_band"),
        "reason_codes": list(candidate.get("stance_reason_codes") or []),
        "requires_manual_review": candidate.get("requires_manual_review"),
    }


def classify_batch_outcome(batch: Sequence[Any]) -> tuple[str, str | None]:
    """('valid_response' | 'failed', reason). A batch is a failed one only when EVERY item fell back for the same
    whole-batch reason (no response / unparseable). A parsed response whose items individually fell back
    (identity / vocabulary / missing) is still a valid response; those items are reported per pair."""
    states = [_pair_state(item.candidate) for item in batch]
    reasons = {s["fallback_reason"] for s in states}
    if all(s["method"] == esl.STANCE_METHOD_DETERMINISTIC_FALLBACK for s in states) and len(reasons) == 1:
        (reason,) = reasons
        if reason in WHOLE_BATCH_FAILURE_REASONS:
            return "failed", reason
    return "valid_response", None


def apply_checkpointed_batch(plan: DirectionPlan, index: int, record: Mapping[str, Any]) -> None:
    """Re-applies a saved batch result onto the candidates with the PRODUCTION helpers (a resume never invents a
    result). Unknown / unsent batches are left exactly as the parent run had them."""
    if record.get("state") not in ("valid_response", "failed"):
        return
    saved = {(p["claim_id"], p["target_alpha_id"]): p for p in record.get("pairs", [])}
    for item in plan.batches[index]:
        pair = saved.get((item.claim_id, item.target_alpha_id))
        if pair is None:
            continue
        if pair["method"] == esl.STANCE_METHOD_LLM:
            esl._apply_llm_result(item.candidate, pair["stance"], pair["counter_alpha_id"])
        else:
            esl._apply_fallback(item.candidate, pair["fallback_reason"])


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def run_direction_batches(
    plan: DirectionPlan,
    taxonomy: Mapping[str, Any],
    *,
    gateway: Any,
    run_output_root: Path,
    execution_id: str,
    checkpoint_path: Path,
    hard_cap: int,
    concurrency: int,
    expected_model: str,
    expected_timeout: float,
) -> dict[str, Any]:
    """Runs the plan with the frozen stop rules. Each stop prevents any NEW batch from being scheduled; batches
    already in flight finish and are individually finalized (in-flight calls are never claimed to be cancelled).

      local_audit_failure   the request/response audit could not be persisted
      auth_failure          a response was HTTP 401/403
      task_isolation_violation   a task other than evidence_stance_classifier was attempted or audited
      identity_failure      an audited request carries no claim ids
      config_failure        an audited request's URL / body shape / model / timeout / retry-count differs
      call_cap_would_be_exceeded  audited-so-far + gateway count + the next group > the cap
      first_batch_gate_failed     the first batch produced no protocol-valid response
    """
    guarded = gateway if isinstance(gateway, TaskAllowlistGateway) else TaskAllowlistGateway(gateway, allowed_tasks=(STANCE_TASK,))
    req_path, resp_path = audit_paths(run_output_root, execution_id)
    prior_sent = len(read_jsonl(req_path))
    checkpoint = load_checkpoint(checkpoint_path)
    for key, record in checkpoint["batches"].items():
        apply_checkpointed_batch(plan, int(key), record)

    # A request audited for a batch the checkpoint does not know (a crash between response and checkpoint): the
    # real Provider may have processed it; it is NEVER re-sent, and it is reported as unknown.
    audited_claim_lists = [r.get("claim_ids") for r in read_jsonl(req_path)]
    for index in range(len(plan.batches)):
        if str(index) not in checkpoint["batches"] and plan.batch_claim_ids(index) in audited_claim_lists:
            checkpoint["batches"][str(index)] = {"state": "unknown_inflight", "pairs": [], "note": "request audited, no saved result; never auto-resent"}

    groups: list[list[int]] = [[0]] if plan.batches else []
    rest = list(range(1, len(plan.batches)))
    groups.extend(rest[i : i + concurrency] for i in range(0, len(rest), concurrency))

    stop_reason: str | None = None
    stop_detail: dict[str, Any] | None = None
    groups_run = 0
    for group in groups:
        pending = [i for i in group if str(i) not in checkpoint["batches"]]
        if pending:
            if gateway.audit_write_failed:
                stop_reason, stop_detail = "local_audit_failure", {"before_group": groups_run + 1}
                break
            if prior_sent + gateway.call_count + len(pending) > hard_cap:
                stop_reason = "call_cap_would_be_exceeded"
                stop_detail = {"gateway_call_count": gateway.call_count, "prior_sent_by_earlier_processes": prior_sent,
                               "next_group": len(pending), "hard_cap": hard_cap}
                break
            req_before, resp_before = len(read_jsonl(req_path)), len(read_jsonl(resp_path))
            stats = esl.StanceRunStats()
            stats.llm_gateway_used = True
            batches = [plan.batches[i] for i in pending]
            if len(batches) == 1:
                esl._process_batch(batches[0], taxonomy, guarded, stats)
            else:
                esl._process_batches_concurrently(batches, taxonomy, guarded, stats, concurrency)
            groups_run += 1
            for i in pending:
                state, reason = classify_batch_outcome(plan.batches[i])
                checkpoint["batches"][str(i)] = {
                    "state": state, "failure_reason": reason, "claim_ids": plan.batch_claim_ids(i),
                    "pairs": [{"claim_id": item.claim_id, "target_alpha_id": item.target_alpha_id, **_pair_state(item.candidate)}
                              for item in plan.batches[i]],
                }
            save_checkpoint(checkpoint_path, checkpoint)

            new_requests = read_jsonl(req_path)[req_before:]
            new_responses = read_jsonl(resp_path)[resp_before:]
            auth_hits = sorted({r["status_code"] for r in new_responses if r.get("status_code") in AUTH_FAILURE_STATUS_CODES})
            wire_problems = sorted({p for r in new_requests if (p := request_wire_problem(r, expected_model=expected_model, expected_timeout=expected_timeout))})
            if gateway.audit_write_failed:
                stop_reason, stop_detail = "local_audit_failure", {"after_group": groups_run}
            elif auth_hits:
                stop_reason, stop_detail = "auth_failure", {"status_codes": auth_hits, "after_group": groups_run}
            elif guarded.refused_tasks or any(r.get("task") != STANCE_TASK for r in new_requests):
                stop_reason = "task_isolation_violation"
                stop_detail = {"refused_tasks": guarded.refused_tasks, "observed_request_tasks": sorted({str(r.get("task")) for r in new_requests}),
                               "after_group": groups_run}
            elif any(not r.get("claim_ids") for r in new_requests):
                stop_reason, stop_detail = "identity_failure", {"after_group": groups_run}
            elif wire_problems:
                stop_reason, stop_detail = "config_failure", {"problems": wire_problems, "after_group": groups_run}
            if stop_reason:
                break
        if group == [0] and checkpoint["batches"].get("0", {}).get("state") != "valid_response":
            first = checkpoint["batches"].get("0", {})
            stop_reason = "first_batch_gate_failed"
            stop_detail = {"state": first.get("state"), "failure_reason": first.get("failure_reason"),
                           "rule": "no further batch is scheduled unless the first batch produced a protocol-valid response"}
            break

    tasks_observed = Counter(str(r.get("task")) for r in read_jsonl(req_path))
    by_state = Counter(rec.get("state") for rec in checkpoint["batches"].values())
    return {
        "stop_reason": stop_reason,
        "stop_detail": stop_detail,
        "groups_run": groups_run,
        "batches_total": len(plan.batches),
        "batch_states": dict(by_state),
        "batches_never_scheduled": len(plan.batches) - len(checkpoint["batches"]),
        "requests_audited_total": sum(tasks_observed.values()),
        "request_tasks_observed": dict(tasks_observed),
        "refused_tasks": guarded.refused_tasks,
        "gateway_call_count": gateway.call_count,
        "hard_request_cap": hard_cap,
        "checkpoint_path": str(checkpoint_path),
    }


# ---------------------------------------------------------------------------
# Per-pair results
# ---------------------------------------------------------------------------


def _finish_reason_and_usage(response_record: Mapping[str, Any] | None) -> tuple[str | None, Mapping[str, Any] | None, str | None]:
    if not response_record:
        return None, None, None
    try:
        body = json.loads(response_record["body"])
        choice = (body.get("choices") or [{}])[0]
        return choice.get("finish_reason"), body.get("usage"), (choice.get("message") or {}).get("content")
    except Exception:
        return None, None, None


def collect_direction_results(
    plan: DirectionPlan,
    *,
    run_output_root: Path,
    execution_id: str,
    base_run_id: str,
    root_run_id: str,
    checkpoint: Mapping[str, Any],
    effective_config: Mapping[str, Any],
) -> dict[str, Any]:
    """The saved, auditable direction record: one entry per (claim, Alpha) pair joined to the semantic call, the
    audited attempt and the real response, plus the batch-level request/response facts and an honest completion
    summary. Reads only files this execution wrote."""
    req_path, resp_path = audit_paths(run_output_root, execution_id)
    requests = read_jsonl(req_path)
    responses = {r["attempt_id"]: r for r in read_jsonl(resp_path)}
    ledger = [c for c in read_jsonl(Path(run_output_root) / execution_id / "llm_semantic_calls.jsonl") if c.get("task") == STANCE_TASK]
    ledger_by_pair: dict[tuple[str, str], dict] = {}
    for call in ledger:
        for item in (call.get("input_payload") or {}).get("items") or []:
            ledger_by_pair[(item.get("claim_id"), item.get("target_alpha_id"))] = call
    request_by_call = {r.get("semantic_call_id"): r for r in requests}

    batches = []
    pairs = []
    for index, batch in enumerate(plan.batches):
        saved = checkpoint["batches"].get(str(index))
        call = ledger_by_pair.get((batch[0].claim_id, batch[0].target_alpha_id))
        request = request_by_call.get(call.get("call_id")) if call else None
        response = responses.get(request["attempt_id"]) if request else None
        finish_reason, usage, content = _finish_reason_and_usage(response)
        batches.append({
            "batch_index": index,
            "state": (saved or {}).get("state", "never_scheduled"),
            "failure_reason": (saved or {}).get("failure_reason"),
            "pair_count": len(batch),
            "semantic_call_id": call.get("call_id") if call else None,
            "attempt_id": request.get("attempt_id") if request else None,
            "request_claim_ids": request.get("claim_ids") if request else None,
            "provider_status": call.get("provider_status") if call else None,
            "validation_status": call.get("validation_status") if call else None,
            "error_code": call.get("error_code") if call else None,
            "latency_ms": call.get("latency_ms") if call else None,
            "retry_count": call.get("retry_count") if call else None,
            "http_status": response.get("status_code") if response else None,
            "finish_reason": finish_reason,
            "usage": usage,
            "request_body_sha256": request.get("body_sha256") if request else None,
            "response_body_sha256": response.get("body_sha256") if response else None,
            "raw_answer_chars": len(content) if isinstance(content, str) else None,
            "model": call.get("model") if call else None,
            "prompt_version": call.get("prompt_version") if call else None,
            "prompt_sha256": call.get("prompt_sha256") if call else None,
            "input_schema_version": call.get("input_schema_version") if call else None,
            "output_schema_version": call.get("output_schema_version") if call else None,
            "taxonomy_version": call.get("taxonomy_version") if call else None,
            "request_control": call.get("request_control") if call else None,
        })
        output = (call or {}).get("validated_output")
        answered = output.get("items") if isinstance(output, Mapping) else output
        validated = {(r.get("claim_id"), r.get("target_alpha_id")): r for r in (answered or []) if isinstance(r, Mapping)}
        for item in batch:
            candidate = item.candidate
            state = _pair_state(candidate)
            model_answer = validated.get((item.claim_id, item.target_alpha_id))
            pairs.append({
                "claim_id": item.claim_id,
                "target_alpha_id": item.target_alpha_id,
                "batch_index": index,
                "request_payload_sha256": payload_sha256(item.payload),
                "semantic_call_id": call.get("call_id") if call else None,
                "attempt_id": request.get("attempt_id") if request else None,
                "model_answer": dict(model_answer) if model_answer is not None else None,
                "final_stance": state["stance"],
                "counter_alpha_id": state["counter_alpha_id"],
                "method": state["method"],
                "method_version": state["version"],
                "fallback_reason": state["fallback_reason"],
                "confidence": None if state["method"] == esl.STANCE_METHOD_LLM else state["confidence_band"],
                "confidence_note": (
                    "the direction task does not ask the model for a confidence; production clears the confidence band for an LLM result"
                    if state["method"] == esl.STANCE_METHOD_LLM else "deterministic fallback value (not a model confidence)"
                ),
                "is_llm_result": state["method"] == esl.STANCE_METHOD_LLM,
            })
    llm = [p for p in pairs if p["is_llm_result"]]
    fallback = [p for p in pairs if p["method"] == esl.STANCE_METHOD_DETERMINISTIC_FALLBACK]
    never = [p for p in pairs if batches[p["batch_index"]]["state"] in ("never_scheduled", "unknown_inflight")]
    completion = {
        "pairs_total": len(pairs),
        "llm_results": len(llm),
        "deterministic_fallback": len(fallback),
        "fallback_by_reason": dict(Counter(p["fallback_reason"] for p in fallback)),
        "never_scheduled_or_unknown": len(never),
        "llm_stance_distribution": dict(Counter(p["final_stance"] for p in llm)),
        "complete": len(llm) == len(pairs) and not never,
        "batches": dict(Counter(b["state"] for b in batches)),
    }
    return {
        "schema_version": DIRECTION_RESULTS_SCHEMA_VERSION,
        "run_id": execution_id,
        "based_on_run_id": base_run_id,
        "root_research_run_id": root_run_id,
        "task": STANCE_TASK,
        "completion": completion,
        "effective_config": dict(effective_config),
        "batches": batches,
        "pairs": pairs,
        "unresolved_pairs": [{"claim_id": p["claim_id"], "target_alpha_id": p["target_alpha_id"], "reason": p["fallback_reason"] or "never_scheduled_or_unknown"}
                             for p in pairs if not p["is_llm_result"]],
    }


__all__ = [
    "new_direction_execution_id",
    "DirectionPlan",
    "build_direction_plan",
    "plan_signature",
    "plan_sha256",
    "payload_sha256",
    "preflight_direction_gateway",
    "request_wire_problem",
    "run_direction_batches",
    "classify_batch_outcome",
    "collect_direction_results",
    "load_checkpoint",
    "save_checkpoint",
    "apply_checkpointed_batch",
    "read_jsonl",
    "audit_paths",
]
