#!/usr/bin/env python3
"""T4 round 28: reproduce a REAL job timeout / worker termination on the production web path, zero provider calls.

A separate, throwaway API instance (127.0.0.1:8003 -- never 8000/8001/8002) is started with the probe's
sitecustomize on PYTHONPATH (fixed responses at the bottom HTTP transport, non-loopback sockets blocked), the
PostgreSQL rehearsal database comqutor_alpha_t4_rehearsal_test, Week 2 on with profile t3_verified_20261008, and a
short job timeout. One offline request (the saved NVDA 10-02 trader output) is POSTed to that probe instance through
the real API; the real job manager runs it in a spawned worker and terminates the worker at the timeout. Nothing is
sent to any provider; .env is not read (a dummy key satisfies the presence-only check).

    python run_termination_probe.py --plan calibrate --job-timeout 600 --max-calls 1800 --analysis-date 2026-09-01 --out-dir <dir>
    python run_termination_probe.py --plan hang --job-timeout 30 --max-calls <pre-alpha calls + 4> --analysis-date 2026-09-02 --out-dir <dir>
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
T4_TOOLS = REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round27_t4_phase_a_20261008/tools"
SOURCE_RUN = REPO / "outputs/runs/034a0a60-430e-41f8-8321-03a11389707a"
PORT = 8003
DB = "comqutor_alpha_t4_rehearsal_test"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", choices=("calibrate", "hang"), required=True)
    ap.add_argument("--job-timeout", type=int, required=True)
    ap.add_argument("--max-calls", type=int, required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--analysis-date", required=True, help="distinct per probe pass: an identical request would reuse the earlier run")
    args = ap.parse_args(argv)
    out = Path(args.out_dir)
    if out.exists():
        print("refusing: out dir exists", file=sys.stderr)
        return 2
    runs = out / "runs"
    runs.mkdir(parents=True)
    with httpx.Client(trust_env=False, timeout=2) as probe_client:
        try:
            probe_client.get(f"http://127.0.0.1:{PORT}/ready")
            print(f"refusing: port {PORT} is in use", file=sys.stderr)
            return 2
        except httpx.HTTPError:
            pass
    db_url = subprocess.run([sys.executable, str(T4_TOOLS / "create_t4_databases.py"), "--print-url-for", DB], capture_output=True, text=True,
                            check=True).stdout.strip()
    env = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", ""), "PYTHONPATH": str(HERE / "termination_probe"),
           "COMQUTOR_DATABASE_URL": db_url, "COMQUTOR_REQUIRE_DATABASE_NAME": DB, "COMQUTOR_REQUIRE_DATABASE_DIALECT": "postgresql",
           "COMQUTOR_OUTPUT_DIR": str(runs), "COMQUTOR_API_HOST": "127.0.0.1", "COMQUTOR_API_PORT": str(PORT),
           "COMQUTOR_REAL_TRADINGAGENTS_ENABLED": "false", "COMQUTOR_DATA_SANITY_ENABLED": "false",
           "COMQUTOR_WEEK2_LLM_ENABLED": "true", "COMQUTOR_WEEK2_LLM_PROVIDER": "deepseek", "COMQUTOR_WEEK2_LLM_MODEL": "deepseek-v4-flash",
           "COMQUTOR_WEEK2_LLM_PROFILE": "t3_verified_20261008", "COMQUTOR_WEEK2_LLM_MAX_RETRIES": "0", "COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS": "45",
           "COMQUTOR_WEEK2_LLM_MAX_CALLS": str(args.max_calls), "DEEPSEEK_API_KEY": "probe-not-a-key",
           "COMQUTOR_JOB_TIMEOUT_SECONDS": str(args.job_timeout), "COMQUTOR_JOB_MAX_WORKERS": "1",
           "R28_PROBE_LOG": str(out / "provider_requests.jsonl"), "R28_PROBE_NET_LOG": str(out / "blocked_network.jsonl"), "R28_PROBE_PLAN": args.plan}
    server_log = (out / "probe_server.log").open("w")
    server = subprocess.Popen([str(REPO / ".venv/bin/comqutor-api")], cwd=str(REPO), env=env, stdout=server_log, stderr=subprocess.STDOUT)
    record: dict = {"plan": args.plan, "job_timeout_seconds": args.job_timeout, "week2_max_calls": args.max_calls, "port": PORT, "database": DB,
                    "server_pid": server.pid}
    try:
        client = httpx.Client(base_url=f"http://127.0.0.1:{PORT}", trust_env=False, timeout=30)
        for _ in range(120):
            try:
                if client.get("/ready").status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        record["ready"] = client.get("/ready").json()
        trader = next(o for o in json.loads((SOURCE_RUN / "raw_agent_outputs.json").read_text(encoding="utf-8"))["agent_outputs"] if o["agent"] == "trader")
        body = {"ticker": "NVDA", "analysis_date": args.analysis_date, "offline_raw_agent_outputs": [{k: trader[k] for k in ("agent", "tradingagents_agent", "source_field", "raw_output")}]}
        submitted_at = time.time()
        submission = client.post("/api/research", json=body)
        record["submission"] = {"http_status": submission.status_code, "body": submission.json()}
        run_id = submission.json().get("run_id")
        record["run_id"] = run_id
        observed = []
        deadline = time.time() + args.job_timeout + 120
        while time.time() < deadline:
            status = client.get(f"/api/research/{run_id}/status").json()
            if not observed or observed[-1].get("stage") != status.get("stage") or observed[-1].get("status") != status.get("status"):
                observed.append({"t": round(time.time() - submitted_at, 2), "status": status.get("status"), "stage": status.get("stage"),
                                 "error_code": status.get("error_code")})
            if status.get("status") in ("completed", "partial", "failed"):
                break
            time.sleep(0.25)
        record["status_transitions"] = observed
        record["terminal_status"] = client.get(f"/api/research/{run_id}/status").json()
        time.sleep(2)
        record["response_after_termination"] = {k: v for k, v in client.get(f"/api/research/{run_id}").json().items()
                                                 if k in ("status", "error_code", "message", "artifacts", "alpha_classification_completion", "provider_stop")}
    finally:
        server.send_signal(signal.SIGTERM)
        try:
            server.wait(timeout=30)
        except subprocess.TimeoutExpired:
            server.kill()
        server_log.close()
    record["server_exit_code"] = server.returncode
    run_dir = runs / str(record.get("run_id"))
    record["run_dir_files"] = sorted(str(p.relative_to(run_dir)) for p in run_dir.rglob("*") if p.is_file()) if run_dir.is_dir() else []
    provider_log = [json.loads(line) for line in (out / "provider_requests.jsonl").read_text().splitlines()] if (out / "provider_requests.jsonl").is_file() else []
    record["provider_requests"] = {"total": len(provider_log), "by_task": {t: sum(1 for r in provider_log if r.get("task") == t) for t in sorted({r.get("task") for r in provider_log})},
                                   "held_open": [r for r in provider_log if r.get("held_open")]}
    record["blocked_non_loopback_connections"] = len((out / "blocked_network.jsonl").read_text().splitlines()) if (out / "blocked_network.jsonl").is_file() else 0
    (out / "probe_result.json").write_text(json.dumps(record, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: record.get(k) for k in ("plan", "run_id", "status_transitions", "provider_requests", "blocked_non_loopback_connections",
                                                  "server_exit_code")}, default=str, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
