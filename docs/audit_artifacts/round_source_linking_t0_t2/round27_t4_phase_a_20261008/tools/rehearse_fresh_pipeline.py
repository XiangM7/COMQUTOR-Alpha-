#!/usr/bin/env python3
"""T4 Phase A: zero-network rehearsal of the NVDA Fresh Run's production path (run under the network trap).

The production entry ``routes_research.run_research_request`` runs unchanged with the Fresh Run's own configuration (profile
t3_verified_20261008, Week 2 enabled, retries 0, audit on, the given Week 2 call budget, an isolated PostgreSQL rehearsal database).
Two things are replaced, nothing else:
  * the research-agent stage: its ``runner`` seam returns a new run directory holding the NVDA 10-02 run's saved agent outputs and
    sources (run ids rebased) -- TradingAgents and its data sources are NOT run;
  * the bottom HTTP transport: ``httpx.HTTPTransport`` (what build_server_week2_llm_gateway's audited clients wrap) answers fixed
    replies chosen from each request's own content -- alpha: by sha256 of the claim text, 1 in 10 HTTP 500, 1 in 10 a dropped connection
    after send (outcome unknown), 3 in 10 select A304, 5 in 10 none; content support cites the first 30 characters of the candidate's own
    excerpt; stance echoes supports_alpha; adapter echoes its segments; extractor returns no edges.
Checks: every request's task, timeout header and body keys; each alpha answer landed on the claim it was computed from (concurrency 4);
failures/unknown are classification failures, never NONE, and are not resent; the ledger/audit/progress rows exist; with a small budget the
remaining calls are refused unsent and the run is saved partial. Fixed replies prove wiring, not model quality.

    python run_with_network_trap.py rehearse_fresh_pipeline.py --label full --max-calls 2478 --work-dir <new dir> --out 04_fresh_prep/rehearsal_full.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import uuid
from collections import Counter
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
SOURCE_RUN = REPO / "outputs" / "runs" / "034a0a60-430e-41f8-8321-03a11389707a"
DB = "comqutor_alpha_t4_rehearsal_test"
COPIED = ("raw_agent_outputs.json", "source_registry.json", "market_data_snapshot.json", "derived_inputs.json", "provider_response_audit.json")


def _alpha_plan(claim: str) -> str:
    bucket = int(hashlib.sha256(claim.encode("utf-8")).hexdigest(), 16) % 10
    return "http_500" if bucket == 0 else "dropped_after_send" if bucket == 1 else "select" if bucket in (2, 3, 4) else "none"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--max-calls", type=int, required=True)
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    work = Path(args.work_dir)
    if work.exists():
        print("refusing: work dir exists", file=sys.stderr)
        return 2
    work.mkdir(parents=True)
    url = subprocess.run([sys.executable, str(HERE / "create_t4_databases.py"), "--print-url-for", DB], capture_output=True, text=True, check=True).stdout.strip()
    for name in list(os.environ):
        if name.startswith("COMQUTOR_WEEK2_") or name.startswith("COMQUTOR_RESEARCH_AGENT_"):
            os.environ.pop(name)
    os.environ.update({
        "COMQUTOR_DATABASE_URL": url, "COMQUTOR_REQUIRE_DATABASE_NAME": DB, "COMQUTOR_REQUIRE_DATABASE_DIALECT": "postgresql",
        "COMQUTOR_WEEK2_LLM_ENABLED": "true", "COMQUTOR_WEEK2_LLM_PROVIDER": "deepseek", "COMQUTOR_WEEK2_LLM_MODEL": "deepseek-v4-flash",
        "COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS": "45", "COMQUTOR_WEEK2_LLM_MAX_RETRIES": "0", "COMQUTOR_WEEK2_LLM_PROFILE": "t3_verified_20261008",
        "COMQUTOR_WEEK2_LLM_MAX_CALLS": str(args.max_calls), "COMQUTOR_DATA_SANITY_ENABLED": "false", "DEEPSEEK_API_KEY": "rehearsal-not-a-key",
    })
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

    prefixes = {task: Week2LLMGateway._provider_prompt_prefix(task) for task in (
        "claim_batch_enrichment", "alpha_classifier", "content_support_verification", "evidence_stance_classifier", "structure_extractor")}
    lock = threading.Lock()
    seen: list[dict] = []
    alpha_plan_by_claim: dict[str, str] = {}

    def _completion(body: dict, content: object) -> httpx.Response:
        return httpx.Response(200, json={"id": f"rehearsal-{uuid.uuid4()}", "object": "chat.completion", "created": 0, "model": "deepseek-flash",
                                         "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps(content)}, "finish_reason": "stop"}],
                                         "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110,
                                                   "prompt_cache_hit_tokens": 60, "prompt_cache_miss_tokens": 40}})

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        content = body["messages"][0]["content"]
        task = next((t for t, p in prefixes.items() if content.startswith(p)), "UNKNOWN_TASK")
        payload = json.loads(content[len(prefixes[task]):]) if task != "UNKNOWN_TASK" else {}
        with lock:
            seen.append({"task": task, "read_timeout": request.headers.get("x-stainless-read-timeout"),
                         "retry_count": request.headers.get("x-stainless-retry-count"), "body_keys": sorted(body), "model": body.get("model"),
                         "url": str(request.url)})
        if task == "alpha_classifier":
            plan = _alpha_plan(str(payload.get("claim") or ""))
            with lock:
                alpha_plan_by_claim[str(payload.get("claim") or "")] = plan
            if plan == "http_500":
                return httpx.Response(500, json={"error": {"message": "rehearsal injected server error"}})
            if plan == "dropped_after_send":
                raise httpx.RemoteProtocolError("rehearsal: connection dropped after the request was sent", request=request)
            return _completion(body, {"decision": "select", "selected_alpha_id": "A304"} if plan == "select" else {"decision": "none", "selected_alpha_id": None})
        if task == "claim_batch_enrichment":
            return _completion(body, {"claims": [{"segment_id": s["segment_id"], "claim": s["claim"], "evidence": s["evidence"],
                                                  "source_section": s["source_section"], "entities": [], "factors": [], "direction": "unknown",
                                                  "confidence": 0.0} for s in payload.get("segments", [])]})
        if task == "content_support_verification":
            items = []
            for item in payload.get("items", []):
                candidate = item["allowed_candidates"][0]
                items.append({"claim_id": item["claim_id"], "core_proposition": "rehearsal", "status": "SUPPORTS", "support_basis": "DIRECT_FACT",
                              "used_source_id": candidate["source_id"], "used_location": "excerpt",
                              "supporting_quote_or_data": (candidate.get("excerpt") or "")[:30], "inference_facts": [], "inference_assumptions": [],
                              "rationale": "rehearsal", "supported_proposition": item["proposition"], "unsupported_remainder": "",
                              "unsupported_remainder_materiality": "NONE"})
            return _completion(body, {"items": items})
        if task == "evidence_stance_classifier":
            return _completion(body, {"items": [{"claim_id": i["claim_id"], "target_alpha_id": i["target_alpha_id"], "stance": "supports_alpha",
                                                 "counter_alpha_id": None} for i in payload.get("items", [])]})
        if task == "structure_extractor":
            return _completion(body, {"edges": []})
        return httpx.Response(400, json={"error": {"message": "rehearsal: unrecognized task"}})

    httpx.HTTPTransport = lambda *a, **k: httpx.MockTransport(handler)  # the bottom transport only

    from comqutor_alpha.api.routes_research import run_research_request
    from comqutor_alpha.classification_recovery import rebase_run_id
    from comqutor_alpha.run_environment import EXECUTION_TYPE_FROZEN_INPUT_RECOMPUTE, run_environment_or_unavailable
    from comqutor_alpha.storage.db.repository import build_write_repository_from_env
    from comqutor_alpha.structure_engine.alpha_mapper import compute_alpha_classification_completion

    source_meta = json.loads((SOURCE_RUN / "metadata.json").read_text(encoding="utf-8"))
    source_run_id = SOURCE_RUN.name

    def runner(payload, output_root):
        run_id = f"t4-rehearsal-{args.label}-{uuid.uuid4().hex[:8]}"
        run_dir = Path(output_root) / run_id
        run_dir.mkdir(parents=True)
        for name in COPIED:
            if (SOURCE_RUN / name).is_file():
                data = json.loads((SOURCE_RUN / name).read_text(encoding="utf-8"))
                (run_dir / name).write_text(json.dumps(rebase_run_id(data, base_run_id=source_run_id, execution_id=run_id), ensure_ascii=False, indent=2),
                                            encoding="utf-8")
        metadata = {**{k: source_meta[k] for k in ("ticker", "analysis_date", "selected_analysts", "agents", "llm_provider", "quick_model",
                                                    "deep_model", "fact_dependency_contract") if k in source_meta},
                    "run_id": run_id, "source": "T4 rehearsal: saved agent outputs of 034a0a60 (TradingAgents not run)", "output_version": "week1a.v1",
                    "rehearsal": True, "based_on_run_id": source_run_id,
                    "run_environment": run_environment_or_unavailable(EXECUTION_TYPE_FROZEN_INPUT_RECOMPUTE, output_root)}
        (run_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(run_dir)

    repository = build_write_repository_from_env(str(work))
    response = run_research_request({"ticker": "NVDA", "selected_analysts": source_meta.get("selected_analysts")}, runner=runner,
                                    output_root=str(work), graph_repository=repository)
    run_id = response.get("run_id")
    run_dir = work / run_id
    matches = json.loads((run_dir / "alpha_matches.json").read_text(encoding="utf-8")).get("matches") or []
    misrouted, by_plan = [], Counter()
    for m in matches:
        claim = str(m.get("claim") or "")
        plan = alpha_plan_by_claim.get(claim)
        if plan is None:
            by_plan["not_requested"] += 1
            continue
        by_plan[plan] += 1
        selected = m.get("llm_selected_alpha_id")
        reason = m.get("alpha_match_fallback_reason")
        ok = ((plan in ("http_500", "dropped_after_send") and reason not in (None, "") and not m.get("matched_alpha"))
              or (plan == "select" and selected == "A304") or (plan == "none" and reason is None and not selected))
        if not ok:
            misrouted.append({"claim_id": m.get("claim_id"), "plan": plan, "selected": selected, "fallback_reason": reason})
    ledger = [json.loads(line) for line in (run_dir / "llm_semantic_calls.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    audit_rows = [json.loads(line) for line in (run_dir / "error_logs" / "week2_llm_provider_request_audit.jsonl").read_text(encoding="utf-8").splitlines()] \
        if (run_dir / "error_logs" / "week2_llm_provider_request_audit.jsonl").is_file() else []
    usage = json.loads((run_dir / "llm_usage_report.json").read_text(encoding="utf-8")) if (run_dir / "llm_usage_report.json").is_file() else {}
    by_task_headers = {}
    for row in seen:
        by_task_headers.setdefault(row["task"], Counter())[(row["read_timeout"], row["retry_count"], ",".join(row["body_keys"]), row["model"], row["url"])] += 1
    report = {
        "label": args.label, "week2_max_calls": args.max_calls, "run_id": run_id, "response_status": response.get("status"),
        "response_error_code": response.get("error_code"),
        "db_status": (repository.get_research_run_record(run_id) or {}).get("status"),
        "requests_seen_by_transport": len(seen), "requests_by_task": dict(Counter(r["task"] for r in seen)),
        "wire_shape_by_task": {t: [{"read_timeout": k[0], "retry_count": k[1], "body_keys": k[2], "model": k[3], "url": k[4], "requests": n}
                                   for k, n in c.items()] for t, c in by_task_headers.items()},
        "alpha_plans_applied": dict(by_plan), "alpha_misrouted_or_misrecorded": misrouted,
        "alpha_classification_completion": compute_alpha_classification_completion({"matches": matches}),
        "ledger_records_by_task_and_status": dict(Counter(f"{r['task']}:{r['provider_status']}" for r in ledger)),
        "ledger_attempts_total": sum(len(r.get("request_attempts") or []) for r in ledger),
        "audit_request_rows": len(audit_rows),
        "usage_report_totals": usage.get("totals", {}).get("week2_semantic"),
        "artifacts": sorted(p.name for p in run_dir.iterdir() if p.is_file()),
        "metadata_run_environment": json.loads((run_dir / "metadata.json").read_text(encoding="utf-8")).get("run_environment", {}).get("effective_config", {}).get("week2_semantic"),
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("label", "run_id", "response_status", "db_status", "requests_seen_by_transport", "requests_by_task",
                                             "alpha_plans_applied", "alpha_classification_completion", "ledger_records_by_task_and_status")}, default=str))
    print("misrouted:", len(misrouted))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
