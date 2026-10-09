#!/usr/bin/env python3
"""T4 round 32: a DERIVED verification execution of the second NVDA Fresh run (12591384) on the FINAL code -- zero provider,
search or data calls.

What runs: the production research pipeline (``routes_research.run_research_request``: Week 2 claim extraction / enrichment,
content support, Alpha classification, evidence stance, structure extraction, Structure Graph, activation, conflicts, formal
acceptance, artifact finalization, usage report, PostgreSQL persistence through ``build_write_repository_from_env``), started
from the based-on run's saved Week 1 materials (raw agent outputs, source registry, derived inputs, provider response audit).

What is replaced: only the bottom HTTP transport of the production Week 2 gateway. Every request the final code makes is
matched to the based-on run's own saved request (wire audit ``body``; the only normalisation is the run id inside claim ids,
since the derived execution has its own id) and answered with that request's SAVED response body (run id rebased back). A
request that timed out in the Fresh run times out again here (``httpx.ReadTimeout``) -- including the one whose response
arrived after the 45 s limit; a request the Fresh run never sent cannot be matched and must not be sent now. Any request
without a saved counterpart fails loudly and is counted. No new model answer is produced or synthesised.

It is NOT a new real model execution: metadata.run_environment.execution_type is ``old_result_reevaluation`` and
``derived_execution`` names the based-on run, the purpose and the transport replay. The research-agent layer is not re-run
(its call log is not copied, so this execution's usage report covers the replayed Week 2 layer only).

Outputs: the execution directory under --output-root, a PostgreSQL research run in comqutor_alpha_t4_r32_verify_test, and
--report (matching statistics, empty-database migration evidence, timings).

    python run_with_network_trap.py replay_fresh2_final_code.py --output-root outputs/t4_r32_verify_runs --report 05_replay/replay_report.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
sys.path.insert(0, str(REPO))
BASE_RUN_ID = "12591384-0b26-470d-a99d-a49c00be440b"
BASE_DIR = REPO / "outputs" / "t4_runs" / BASE_RUN_ID
VERIFY_DB = "comqutor_alpha_t4_r32_verify_test"
WEEK1_FILES = ("raw_agent_outputs.json", "source_registry.json", "derived_inputs.json", "provider_response_audit.json",
               "tradingagents_comqutor_vocabulary_snapshot.json")
TIMEOUT_HOLD_SECONDS = 50  # > the shared 45 s limit of claim_batch_enrichment in the frozen profile
FROZEN_WEEK2_ENV = {  # round28 04_refreeze/frozen_config.json process_environment_allowlisted (Week 2 part)
    "COMQUTOR_WEEK2_LLM_ENABLED": "true", "COMQUTOR_WEEK2_LLM_PROFILE": "t3_verified_20261008", "COMQUTOR_WEEK2_LLM_PROVIDER": "deepseek",
    "COMQUTOR_WEEK2_LLM_MODEL": "deepseek-v4-flash", "COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS": "45", "COMQUTOR_WEEK2_LLM_MAX_RETRIES": "0",
    "COMQUTOR_WEEK2_LLM_MAX_CALLS": "1800",
}


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.is_file() else []


class SavedResponseTransport:
    """Answers each request with the based-on run's saved response for the identical request body."""

    def __init__(self, execution_id: str) -> None:
        import httpx

        self.httpx = httpx
        self.execution_id = execution_id
        requests = _jsonl(BASE_DIR / "error_logs" / "week2_llm_provider_request_audit.jsonl")
        responses = {r["attempt_id"]: r for r in _jsonl(BASE_DIR / "error_logs" / "week2_llm_provider_response_audit.jsonl")}
        ledger = _jsonl(BASE_DIR / "llm_semantic_calls.jsonl")
        attempt_status = {a["attempt_id"]: a.get("provider_status") for r in ledger for a in (r.get("request_attempts") or [])}
        self.by_body: dict[str, list[dict]] = defaultdict(list)
        for req in requests:
            status = attempt_status.get(req["attempt_id"])
            response = responses.get(req["attempt_id"])
            self.by_body[req["body"]].append({"attempt_id": req["attempt_id"], "task": req["task"], "ledger_status": status,
                                              "response_body": response["body"] if response and status == "success" else None})
        self.lock = threading.Lock()
        self.next_index: Counter = Counter()
        self.replies_rebased: Counter = Counter()
        self.served = Counter()
        self.timeouts_replayed = Counter()
        self.reused_identical_body = Counter()
        self.unmatched: list[dict] = []
        self.used_attempts: list[str] = []

    def handler(self, request):
        body = request.content.decode("utf-8")
        normalized = body.replace(self.execution_id, BASE_RUN_ID)
        with self.lock:
            candidates = self.by_body.get(normalized)
            if not candidates:
                self.unmatched.append({"sha_prefix": __import__("hashlib").sha256(body.encode()).hexdigest()[:16], "length": len(body)})
                raise RuntimeError("REPLAY_UNMATCHED_REQUEST: no saved request with this body")
            index = self.next_index[normalized]
            if index < len(candidates):
                self.next_index[normalized] = index + 1
            else:  # more identical requests than the Fresh run sent: the same saved answer again, counted
                index = len(candidates) - 1
                self.reused_identical_body[candidates[index]["task"]] += 1
            entry = candidates[index]
            self.used_attempts.append(entry["attempt_id"])
        if entry["ledger_status"] == "timeout":
            # timed out in the based-on run (incl. the one whose 200 arrived after the limit): hold the request past the
            # task's 45 s limit so the gateway's own wall-clock deadline fires exactly as it did (attempt 2 raised at once,
            # which the gateway records as a provider error -- superseded)
            with self.lock:
                self.timeouts_replayed[entry["task"]] += 1
            time.sleep(TIMEOUT_HOLD_SECONDS)
            raise self.httpx.ReadTimeout("replayed timeout: this request timed out in the based-on run", request=request)
        with self.lock:
            self.served[entry["task"]] += 1
        # the inverse of the request normalisation, and only where it applied: claim ids keep the based-on run's id in a
        # derived execution (classification_recovery.rebase_run_id rewrites run_id fields only), so a reply is rebased only
        # when its request actually carried the execution id (attempt 1 of this tool rebased every reply -- superseded)
        reply = entry["response_body"]
        if self.execution_id in body:
            reply = reply.replace(BASE_RUN_ID, self.execution_id)
            with self.lock:
                self.replies_rebased[entry["task"]] += 1
        return self.httpx.Response(200, content=reply.encode("utf-8"), headers={"content-type": "application/json"})


def _db_tables(url: str) -> list[str]:
    import sqlalchemy as sa

    engine = sa.create_engine(url)
    with engine.connect() as conn:
        conn.execute(sa.text("SET TRANSACTION READ ONLY"))
        return sorted(conn.execute(sa.text("select tablename from pg_tables where schemaname='public'")).scalars())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-root", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args(argv)
    output_root = (REPO / args.output_root).resolve() if not Path(args.output_root).is_absolute() else Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    url = subprocess.run([sys.executable, str(HERE / "create_r32_databases.py"), "--print-url-for", VERIFY_DB],
                         capture_output=True, text=True, check=True).stdout.strip()
    tables_before = _db_tables(url)
    for name in list(os.environ):
        if name.startswith(("COMQUTOR_WEEK2_", "COMQUTOR_RESEARCH_AGENT_")):
            del os.environ[name]
    os.environ.update({**FROZEN_WEEK2_ENV, "COMQUTOR_DATABASE_URL": url, "COMQUTOR_REQUIRE_DATABASE_NAME": VERIFY_DB,
                       "COMQUTOR_REQUIRE_DATABASE_DIALECT": "postgresql", "COMQUTOR_DATA_SANITY_ENABLED": "false",
                       "COMQUTOR_REAL_TRADINGAGENTS_ENABLED": "false", "DEEPSEEK_API_KEY": "replay-not-a-key"})

    import httpx

    from comqutor_alpha.api.routes_research import run_research_request
    from comqutor_alpha.classification_recovery import rebase_run_id
    from comqutor_alpha.run_environment import build_run_environment
    from comqutor_alpha.storage.db.repository import build_write_repository_from_env

    execution_id = f"t4r32-replay-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    transport = SavedResponseTransport(execution_id)
    original_transport = httpx.HTTPTransport
    httpx.HTTPTransport = lambda *a, **k: httpx.MockTransport(transport.handler)  # the only replaced component
    repository = build_write_repository_from_env(str(output_root))  # first use of the empty database: migrations run here
    tables_after_migration = _db_tables(url)

    def runner(payload, output_root):
        run_dir = Path(output_root) / execution_id
        run_dir.mkdir(parents=True)
        copied = {}
        for name in WEEK1_FILES:
            source = BASE_DIR / name
            if source.is_file():
                data = rebase_run_id(json.loads(source.read_text(encoding="utf-8")), base_run_id=BASE_RUN_ID, execution_id=execution_id)
                (run_dir / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                copied[name] = __import__("hashlib").sha256(source.read_bytes()).hexdigest()
        base_meta = json.loads((BASE_DIR / "metadata.json").read_text(encoding="utf-8"))
        metadata = {k: v for k, v in base_meta.items() if k not in ("run_environment", "created_at")}
        metadata.update({
            "run_id": execution_id,
            "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "based_on_run_id": BASE_RUN_ID,
            "run_environment": build_run_environment("old_result_reevaluation", str(output_root)),
            "based_on_run_environment": base_meta.get("run_environment"),
            "derived_execution": {
                "purpose": "T4 round 32: final-code consumption of the based-on run's saved responses (verification, not research)",
                "based_on_run_id": BASE_RUN_ID,
                "provider_calls": 0, "searches": 0, "data_fetches": 0,
                "transport": "every Week 2 request answered at the HTTP transport with the based-on run's saved response for the "
                             "identical request body (run id normalised); saved timeouts replayed as timeouts; nothing synthesised",
                "not_re_run": "research agents (TradingAgents); data sanity (disabled: it fetches live market data)",
                "copied_week1_inputs_sha256": copied,
            },
        })
        (run_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        return str(run_dir)

    # The production lifecycle (research_lifecycle): claim a research_runs row, then execute_claimed_research_run marks it
    # running, runs the pipeline (here with the runner seam above) and records the terminal status -- the same path the API's
    # job worker uses. (Attempt 3 called run_research_request directly and therefore left no research_runs row -- superseded.)
    from comqutor_alpha.research_lifecycle import _pipeline_identity, execute_claimed_research_run

    base_meta = json.loads((BASE_DIR / "metadata.json").read_text(encoding="utf-8"))
    claim = repository.claim_research_run(
        run_id=execution_id,
        request_fingerprint=__import__("hashlib").sha256(json.dumps(
            {"execution_type": "old_result_reevaluation", "based_on_run_id": BASE_RUN_ID, "execution_id": execution_id}, sort_keys=True).encode()).hexdigest(),
        ticker="NVDA", analysis_date=base_meta.get("analysis_date"), selected_analysts=list(base_meta.get("selected_analysts") or []),
        execution_mode="replay", provider_identity="deepseek", model_identity="deepseek-v4-flash", pipeline_identity=_pipeline_identity(),
        force_refresh=False,
    )
    if claim.get("disposition") != "created":
        raise SystemExit(f"research run claim not created: {claim.get('disposition')}")

    def executor(payload, *, output_root, graph_repository):
        return run_research_request(payload, runner=runner, output_root=output_root, graph_repository=graph_repository)

    started = time.time()
    try:
        response = execute_claimed_research_run(execution_id, {"ticker": "NVDA"}, output_root=str(output_root), graph_repository=repository,
                                                disposition="created", ticker="NVDA", executor=executor)
    finally:
        httpx.HTTPTransport = original_transport
    elapsed = round(time.time() - started, 1)
    saved_total = sum(len(v) for v in transport.by_body.values())
    report = {
        "execution_id": execution_id, "based_on_run_id": BASE_RUN_ID, "output_root": str(output_root.relative_to(REPO)),
        "database": VERIFY_DB, "tables_before": tables_before, "tables_after_migration": tables_after_migration,
        "status": response.get("status"), "run_status_recorded": response.get("run_status"), "elapsed_seconds": elapsed,
        "replay": {"saved_requests_in_based_on_run": len(_jsonl(BASE_DIR / "error_logs" / "week2_llm_provider_request_audit.jsonl")),
                   "requests_answered_with_saved_response": dict(transport.served), "timeouts_replayed": dict(transport.timeouts_replayed),
                   "identical_body_reused": dict(transport.reused_identical_body), "unmatched_requests": transport.unmatched,
                   "replies_with_run_id_rebased": dict(transport.replies_rebased),
                   "distinct_saved_bodies": len(transport.by_body), "saved_attempts_indexed": saved_total,
                   "requests_made": len(transport.used_attempts) + len(transport.unmatched)},
        "response_summary": {k: response.get(k) for k in ("status", "structure_graph_status", "conflict_status", "alpha_classification_status",
                                                          "alpha_classification_completion", "summary", "main_conflict")},
        "stage_disclosure_degraded": (response.get("stage_disclosure") or {}).get("degraded_stages"),
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("execution_id", "status", "elapsed_seconds", "replay")}, ensure_ascii=False, default=str))
    return 0 if not transport.unmatched else 1


if __name__ == "__main__":
    raise SystemExit(main())
