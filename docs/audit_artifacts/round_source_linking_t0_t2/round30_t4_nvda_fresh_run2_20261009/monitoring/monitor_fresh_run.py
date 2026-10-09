#!/usr/bin/env python3
"""Read-only monitor of the owner-started NVDA Fresh Run on the T4 instance (GET /status over loopback + reading the run
directory). Prints one line on every status/stage change, a heartbeat with call counts every --heartbeat seconds, and exits
on a terminal status. Every line is also appended to monitoring/monitor_log.jsonl. It never POSTs anything."""
import argparse, collections, json, time, urllib.request
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--run-id", required=True)
ap.add_argument("--interval", type=float, default=30)
ap.add_argument("--heartbeat", type=float, default=600)
ap.add_argument("--max-seconds", type=float, default=1740)
a = ap.parse_args()
HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
RUN_DIR = REPO / "outputs" / "t4_runs" / a.run_id
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def counts():
    def jl(p):
        try:
            return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
        except (OSError, ValueError):
            return []
    led = jl(RUN_DIR / "llm_semantic_calls.jsonl")
    req = jl(RUN_DIR / "error_logs/week2_llm_provider_request_audit.jsonl")
    resp = jl(RUN_DIR / "error_logs/week2_llm_provider_response_audit.jsonl")
    return {"ledger": dict(collections.Counter(f"{r['task']}:{r['provider_status']}" for r in led)),
            "http_requests": dict(collections.Counter(r["task"] for r in req)), "responses": len(resp),
            "response_codes": dict(collections.Counter(str(r.get("status_code")) for r in resp)),
            "provider_stop": (RUN_DIR / "provider_stop.json").exists(),
            "files": sorted(p.name for p in RUN_DIR.iterdir() if p.is_file()) if RUN_DIR.is_dir() else []}


def emit(kind, payload):
    line = {"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "kind": kind, **payload}
    with open(HERE / "monitor_log.jsonl", "a") as f:
        f.write(json.dumps(line) + "\n")
    print(json.dumps(line), flush=True)


start, last, last_beat = time.time(), None, 0.0
while time.time() - start < a.max_seconds:
    try:
        s = json.load(opener.open(f"http://127.0.0.1:8002/api/research/{a.run_id}/status", timeout=10))
    except Exception as exc:
        emit("poll_error", {"error": type(exc).__name__})
        time.sleep(a.interval)
        continue
    key = (s.get("status"), s.get("stage"), s.get("current_stage"), s.get("progress_message"))
    if key != last:
        c = counts()
        emit("change", {"status": s.get("status"), "stage": s.get("stage"), "current_stage": s.get("current_stage"),
                        "progress": s.get("progress_percent"), "message": s.get("progress_message"), "error_code": s.get("error_code"),
                        "elapsed_s": s.get("elapsed_seconds"), "http_requests": c["http_requests"], "provider_stop": c["provider_stop"]})
        last = key
    if time.time() - last_beat >= a.heartbeat:
        c = counts()
        emit("heartbeat", {"status": s.get("status"), "current_stage": s.get("current_stage"), "progress": s.get("progress_percent"),
                           "elapsed_s": s.get("elapsed_seconds"), "http_requests": c["http_requests"], "responses": c["responses"],
                           "response_codes": c["response_codes"], "ledger": c["ledger"], "provider_stop": c["provider_stop"]})
        last_beat = time.time()
    if s.get("status") in ("completed", "partial", "failed"):
        emit("terminal", {"status": s.get("status"), "error_code": s.get("error_code"), "elapsed_s": s.get("elapsed_seconds"), "files": counts()["files"]})
        break
    time.sleep(a.interval)
