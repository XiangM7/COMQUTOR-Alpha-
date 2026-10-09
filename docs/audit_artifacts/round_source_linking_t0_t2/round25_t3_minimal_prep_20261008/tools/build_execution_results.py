#!/usr/bin/env python3
"""Round 25 part B execution: summarize one finished execution of t3_joint_sample_driver.py predict. Zero calls; reads only.

Per task it keeps apart: gateway budget reservations, HTTP requests actually forwarded (checkpoint), responses by HTTP status, valid
responses (200 with a parseable chat completion), truncations (finish_reason length), and successful judgments (validated results). Model
identity and usage come only from the response bodies; anything missing is counted as unknown, never estimated. Per sample it binds the
prediction to the request / response audit records (attempt ids, response sha256) and to the semantic ledger call (alpha).

    python build_execution_results.py --execution-dir outputs/t3_joint_evaluations/<id> --materials-dir outputs/t3_joint_evaluations/<id>-materials \
        --history <B3_budget/historical_alpha_answers_COMPARISON_ONLY.json> --out-dir <new dir>
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
PACKAGE = HERE.parent
MANIFEST = PACKAGE / "B1_samples_v4" / "joint_sample_v4_manifest.json"
FORM = PACKAGE / "B1_samples_v4" / "review_form_v4.json"
TASKS = ("content_support_verification", "alpha_classifier", "evidence_stance_classifier")

_spec = importlib.util.spec_from_file_location("t3_joint_sample_driver_for_results", REPO / "docs/audit_artifacts/round_source_linking_t0_t2/t3_joint_sample_driver.py")
assert _spec is not None and _spec.loader is not None
driver = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = driver
_spec.loader.exec_module(driver)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else []


def _completion(body_text: str) -> dict | None:
    try:
        body = json.loads(body_text)
    except ValueError:
        return None
    return body if isinstance(body, dict) and isinstance(body.get("choices"), list) and body["choices"] else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execution-dir", required=True)
    ap.add_argument("--materials-dir", required=True)
    ap.add_argument("--history", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    E, M, out = Path(args.execution_dir), Path(args.materials_dir), Path(args.out_dir)
    if out.exists() and any(out.iterdir()):
        print("refusing: output directory not empty", out, file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    plan = json.loads((E / "authorized_plan.json").read_text(encoding="utf-8"))
    eid = plan["execution_id"]
    summary_in = json.loads((E / "run_summary.json").read_text(encoding="utf-8"))
    predictions = {p["sample_id"]: p for p in _jsonl(E / "joint_predictions.jsonl")}
    task_audit = json.loads((E / "task_audit.json").read_text(encoding="utf-8"))
    manifest = {s["sample_id"]: s for s in json.loads(MANIFEST.read_text(encoding="utf-8"))["samples"]}
    history = json.loads(Path(args.history).read_text(encoding="utf-8"))["answers"]
    events = _jsonl(E / "checkpoint.jsonl")

    # ---------------- per task ----------------
    tasks: dict[str, dict] = {}
    audit: dict[str, dict] = {}
    for task in TASKS:
        base = E / task / eid
        req = _jsonl(base / "error_logs" / "week2_llm_provider_request_audit.jsonl")
        resp = _jsonl(base / "error_logs" / "week2_llm_provider_response_audit.jsonl")
        ledger = _jsonl(base / "llm_semantic_calls.jsonl")
        errors = _jsonl(base / "error_logs" / "week2_llm_errors.jsonl")
        audit[task] = {"request": {r["attempt_id"]: r for r in req}, "response": {r["attempt_id"]: r for r in resp}, "ledger": ledger}
        last: dict[str, dict] = {}
        for e in events:
            if e.get("task") == task and e.get("attempt_id") and e["event"] in ("sending", "response", "transport_error", "not_sent"):
                last[e["attempt_id"]] = e
        states = Counter()
        for e in last.values():
            if e["event"] == "not_sent":
                states["not_sent_refused_before_network"] += 1
            elif e["event"] == "response":
                states[f"http_{e['status_code']}"] += 1
            elif e["event"] == "transport_error":
                states[f"transport_error_{e.get('error_type')}"] += 1
            else:
                states["unknown_sent_no_outcome_recorded"] += 1
        forwarded = sum(n for s, n in states.items() if s != "not_sent_refused_before_network")
        finish, models, usage, usage_missing, valid = Counter(), Counter(), Counter(), 0, 0
        for r in resp:
            body = _completion(r.get("body", ""))
            if r.get("status_code") != 200 or body is None:
                continue
            valid += 1
            finish[str(body["choices"][0].get("finish_reason"))] += 1
            models[str(body.get("model") or "unknown")] += 1
            u = body.get("usage")
            if not isinstance(u, dict):
                usage_missing += 1
                continue
            usage["prompt_tokens"] += int(u.get("prompt_tokens") or 0)
            usage["completion_tokens"] += int(u.get("completion_tokens") or 0)
            usage["reasoning_tokens"] += int((u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
            usage["prompt_cache_hit_tokens"] += int(u.get("prompt_cache_hit_tokens") or 0)
            usage["responses_reporting_reasoning_tokens"] += 1 if (u.get("completion_tokens_details") or {}).get("reasoning_tokens") else 0
        tasks[task] = {
            "request_cap": plan["config"]["max_requests"][task],
            "gateway_budget_reservations": summary_in["gateway_reservations"].get(task),
            "attempts_reaching_the_transport": len(last),
            "http_requests_forwarded": forwarded,
            "attempt_states": dict(states),
            "valid_chat_completions": valid,
            "finish_reason": dict(finish),
            "truncated_finish_reason_length": finish.get("length", 0),
            "model_reported_by_responses": dict(models) or {"unknown": 0},
            "usage_from_responses": dict(usage), "responses_without_usage": usage_missing,
            "requests_without_any_response_record": forwarded - len(resp),
            "error_log_codes": dict(Counter(e.get("error_code") for e in errors)),
            "semantic_ledger_records": len(ledger) if task != "content_support_verification" else "not recorded (task not in the ledger registry); see request/response audit and task_audit.json",
        }
    stance_stats = task_audit.get("evidence_stance_classifier", {})
    tasks["evidence_stance_classifier"]["items"] = {
        "requested_pairs": sum(int(s.get("requested_count") or 0) for s in stance_stats.values() if isinstance(s, dict)),
        "llm_results": sum(int(s.get("llm_result_count") or 0) for s in stance_stats.values() if isinstance(s, dict)),
        "deterministic_fallbacks": sum(int(s.get("deterministic_fallback_count") or 0) for s in stance_stats.values() if isinstance(s, dict)),
        "fallback_reasons": dict(sum((Counter(s.get("fallback_reason_counts") or {}) for s in stance_stats.values() if isinstance(s, dict)), Counter())),
    }
    cs_stats = task_audit.get("content_support_verification", {})
    tasks["content_support_verification"]["items"] = {
        "requested": sum(int(s.get("requested_count") or 0) for s in cs_stats.values()),
        "llm_verified": sum(int(s.get("llm_verified_count") or 0) for s in cs_stats.values()),
        "fallbacks": sum(int(s.get("fallback_count") or 0) for s in cs_stats.values()),
        "fallback_reasons": dict(sum((Counter({k: v for k, v in (s.get("fallback_reason_counts") or {}).items() if v}) for s in cs_stats.values()), Counter())),
    }

    # ---------------- per sample ----------------
    def attempts_for(task: str, claim_id: str) -> list[dict]:
        found = []
        for attempt_id, r in audit[task]["request"].items():
            if claim_id in (r.get("claim_ids") or []):
                rs = audit[task]["response"].get(attempt_id)
                found.append({"attempt_id": attempt_id, "request_body_sha256": r.get("body_sha256"),
                              "response_status": rs.get("status_code") if rs else None, "response_body_sha256": rs.get("body_sha256") if rs else None})
        return found

    rows = []
    for sid, p in predictions.items():
        claim_id = manifest[sid]["claim_id"]
        ledger = [r for r in audit["alpha_classifier"]["ledger"] if claim_id in (r.get("claim_ids") or [])]
        hist = history.get(sid, {})
        hist_sel = (hist.get("validated_output") or {}).get("selected_alpha_id") if hist.get("status") == "HISTORICAL_ANSWER" else None
        rows.append({
            "sample_id": sid, "cell": p["cell"], "claim_id": claim_id, "run_id": manifest[sid]["run_id"], "claim_text": p["claim_text"],
            "material_status": manifest[sid]["material_status"], "action": manifest[sid]["action"],
            "L1_source_to_claim": {**{k: v for k, v in p["L1"].items() if k != "llm_detail"},
                                   "llm_detail": p["L1"].get("llm_detail"), "audit": attempts_for("content_support_verification", claim_id)},
            "L2_alpha": {"raw_model_selection": p["L2"].get("raw_selected_alpha"), "final_after_production_gates": p["L2"].get("predicted_alpha"),
                         "outcome_code": p["L2"]["outcome_code"], "classifier_status": p["L2"].get("classifier_status"),
                         "gate_overrides": p["L2"].get("override"), "fallback_reason": p["L2"].get("fallback_reason"),
                         "answer_source": p["L2"].get("answer_source"),
                         "ledger": [{"call_id": r.get("call_id"), "provider_status": r.get("provider_status"), "error_code": r.get("error_code"),
                                     "validated_output": r.get("validated_output"), "token_usage": r.get("token_usage")} for r in ledger],
                         "audit": attempts_for("alpha_classifier", claim_id),
                         "historical_answer_for_comparison_only": {"status": hist.get("status"), "selected_alpha_id": hist_sel, "ledger_run": hist.get("ledger_run")}},
            "L3_direction": {**p["L3"], "audit": attempts_for("evidence_stance_classifier", claim_id)},
            "L4_claim_eligibility": p["L4"],
            "reference_judgment": "PENDING_REVIEW",
        })

    # ---------------- links, materials, history ----------------
    links = {
        "L1": dict(Counter(r["L1_source_to_claim"]["status"] for r in rows)),
        "L1_content_support_status": dict(Counter(r["L1_source_to_claim"].get("content_support_status") for r in rows if r["L1_source_to_claim"]["status"] == "LLM_RESULT")),
        "L2_outcome": dict(Counter(r["L2_alpha"]["outcome_code"] for r in rows)),
        "L2_raw_selection": dict(Counter(str(r["L2_alpha"]["raw_model_selection"]) for r in rows)),
        "L2_final": dict(Counter(str(r["L2_alpha"]["final_after_production_gates"]) for r in rows)),
        "L2_selected_but_overridden_by_gates": [r["sample_id"] for r in rows if r["L2_alpha"]["outcome_code"] == "SELECTED_BUT_NOT_MATCHED"],
        "L3": dict(Counter(r["L3_direction"]["status"] for r in rows)),
        "L3_stance": dict(Counter(r["L3_direction"].get("stance") for r in rows if r["L3_direction"]["status"] == "LLM_RESULT")),
        "L4": dict(Counter(r["L4_claim_eligibility"]["status"] for r in rows)),
        "L4_activation_pool_eligible": dict(Counter(str(r["L4_claim_eligibility"].get("activation_pool_eligible")) for r in rows if r["L4_claim_eligibility"]["status"] == "DETERMINED")),
        "L4_conflict_side_eligible": dict(Counter(str(r["L4_claim_eligibility"].get("conflict_side_eligible")) for r in rows if r["L4_claim_eligibility"]["status"] == "DETERMINED")),
        "L4_failing_condition_kind": dict(Counter(str(r["L4_claim_eligibility"].get("failing_condition_kind")) for r in rows if r["L4_claim_eligibility"]["status"] == "DETERMINED")),
        "L4_verified_support_reason": dict(Counter(str((r["L4_claim_eligibility"].get("verified_support") or {}).get("reason_code")) for r in rows if r["L4_claim_eligibility"]["status"] == "DETERMINED")),
        "L4_selector_excluded_reason": dict(Counter(str((r["L4_claim_eligibility"].get("selector") or {}).get("excluded_reason")) for r in rows if r["L4_claim_eligibility"]["status"] == "DETERMINED")),
    }
    frozen_materials = json.loads((M / "review_materials_frozen.json").read_text(encoding="utf-8")) if (M / "review_materials_frozen.json").exists() else {}
    collected_for = set((frozen_materials.get("items") or {}).keys())
    coverage = Counter()
    for r in rows:
        status = r["material_status"]
        if status == "NO_MATERIAL" and r["sample_id"] in collected_for:
            status = "NO_RUN_MATERIAL__COLLECTED_FOR_THIS_VERIFICATION"
        coverage[status] += 1
    with_history = [r for r in rows if r["L2_alpha"]["historical_answer_for_comparison_only"]["status"] == "HISTORICAL_ANSWER"]
    same = sum(1 for r in with_history if (r["L2_alpha"]["raw_model_selection"] or None) == (r["L2_alpha"]["historical_answer_for_comparison_only"]["selected_alpha_id"] or None))
    score = driver.score(list(predictions.values()), json.loads(FORM.read_text(encoding="utf-8")))

    result = {
        "schema_version": "t3_round25_execution_results.v1", "execution_id": eid,
        "authorized_by": plan["authorized_by"], "authorization_reference": plan["authorization_reference"],
        "run_summary": {k: summary_in[k] for k in ("started_at", "finished_at", "guard_tripped", "request_caps")},
        "tasks": tasks,
        "model_requests_forwarded_total": sum(t["http_requests_forwarded"] for t in tasks.values()),
        "collection_requests_forwarded": json.loads((M / "collection_record.json").read_text(encoding="utf-8"))["requests_sent"],
        "links": links,
        "material_coverage_final": dict(coverage),
        "historical_comparison": {"samples_with_historical_answer": len(with_history), "same_raw_selection_as_history": same,
                                  "note": "consistency with earlier production answers; not accuracy, not this execution's evaluation"},
        "scoring": score,
        "notes": [
            "reservations, forwarded requests, valid responses and successful judgments are counted separately; they are not assumed equal",
            "a response reporting reasoning tokens shows only that this response reported reasoning usage; it does not confirm every server default",
            "no reference judgment with a named reviewer exists yet: no accuracy, precision or recall is computed",
        ],
    }
    (out / "execution_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    (out / "per_sample_results.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows), encoding="utf-8")
    print(json.dumps({"tasks": {t: {k: v for k, v in d.items() if k in ("gateway_budget_reservations", "http_requests_forwarded", "attempt_states", "valid_chat_completions", "truncated_finish_reason_length")} for t, d in tasks.items()},
                      "links": {k: links[k] for k in ("L1", "L2_outcome", "L3", "L4")}, "coverage": dict(coverage), "scoring": score.get("scoring_status")},
                     ensure_ascii=False, indent=1, default=str))
    print("results sha256", hashlib.sha256((out / "execution_results.json").read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
