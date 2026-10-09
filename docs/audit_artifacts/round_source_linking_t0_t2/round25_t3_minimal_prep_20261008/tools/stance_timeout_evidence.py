#!/usr/bin/env python3
"""Round 25 (T3 prep), deliverable 6 input: what the saved runs really show about how long an evidence_stance_classifier request takes.
Read-only; scans every outputs/runs/*/llm_semantic_calls.jsonl.

Two facts decide what can be read from a ledger:
  * latency validity: in some ledgers every record carries the SAME completed_at (the moment the ledger was finalized), so latency_ms there
    is "start -> ledger finalize", not the request's duration. Such a ledger is marked SHARED_FINALIZE and its latencies are not used.
  * per-attempt timeout: read from the run's own error log, as the spacing between a request's attempt 1, 2 and 3 timestamps (the gateway
    logs each timed-out attempt when it times out); otherwise from a PER_REQUEST ledger as latency / attempts of the timed-out records.
A request counted as a first-attempt success = provider_status success with retry_count 0. Requests never sent (budget_exhausted,
not_called) are excluded.

    python stance_timeout_evidence.py --out <json>
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
TASK = "evidence_stance_classifier"


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _attempt_spacing(run_dir: Path) -> float | None:
    """The per-attempt timeout as the gap that recurs between timed-out attempts n and n+1 (attempt n+1 of the same request times out
    exactly one timeout later). Under concurrency the requests interleave, so every (attempt n, later attempt n+1) pair within 300 s is
    counted and the whole-second gap with the most support (+/- 1 s) is taken."""
    path = run_dir / "error_logs" / "week2_llm_errors.jsonl"
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    rows = [r for r in rows if r.get("task") == TASK and r.get("error_code") == "WEEK2_LLM_TIMEOUT"]
    by_attempt = {n: sorted(_ts(r["created_at"]) for r in rows if r.get("attempt") == n) for n in (1, 2, 3)}
    counts: Counter = Counter()
    for n in (1, 2):
        for t in by_attempt[n]:
            for later in by_attempt[n + 1]:
                gap = (later - t).total_seconds()
                if 0 < gap <= 300:
                    counts[round(gap)] += 1
    if not counts:
        return None
    best = max(counts, key=lambda v: (counts[v - 1] + counts[v] + counts[v + 1], counts[v]))
    return float(best)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out)
    if out.exists():
        print("refusing: output exists", out, file=sys.stderr)
        return 2
    runs = []
    for ledger in sorted(glob.glob(str(REPO / "outputs/runs/*/llm_semantic_calls.jsonl"))):
        run_dir = Path(ledger).parent
        records = []
        with open(ledger, encoding="utf-8") as fh:
            for line in fh:
                if f'"{TASK}"' in line:
                    r = json.loads(line)
                    if r.get("task") == TASK:
                        records.append(r)
        sent = [r for r in records if r.get("provider_status") in ("success", "timeout", "provider_error")]
        if not sent:
            continue
        ends = [str(r.get("completed_at"))[:19] for r in sent]
        shared = max(ends.count(e) for e in set(ends))
        validity = "SHARED_FINALIZE" if len(sent) > 1 and shared >= 0.5 * len(sent) else "PER_REQUEST"
        spacing = _attempt_spacing(run_dir)
        if spacing is not None:
            timeout_s, timeout_basis = spacing, "error-log attempt spacing"
        elif validity == "PER_REQUEST" and any(r["provider_status"] == "timeout" for r in sent):
            per = [r["latency_ms"] / 1000 / ((r.get("retry_count") or 0) + 1) for r in sent if r["provider_status"] == "timeout"]
            timeout_s, timeout_basis = round(statistics.median(per), 1), "ledger latency / attempts of timed-out requests"
        else:
            timeout_s, timeout_basis = None, "not determinable"
        first_ok = [r for r in sent if r["provider_status"] == "success" and not r.get("retry_count")]
        try:
            meta = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        runs.append({
            "run": run_dir.name,
            "ticker": meta.get("ticker"),
            "date": str(meta.get("created_at") or meta.get("started_at") or "")[:10] or None,
            "provider_model": dict(Counter(f"{r.get('provider')}/{r.get('model')}" for r in sent)),
            "prompt_version": dict(Counter(r.get("prompt_version") for r in sent)),
            "requests_sent": len(sent),
            "first_attempt_success": len(first_ok),
            "first_attempt_success_rate": round(len(first_ok) / len(sent), 3),
            "eventual_status": dict(Counter(r["provider_status"] for r in sent)),
            "per_attempt_timeout_s": timeout_s,
            "timeout_basis": timeout_basis,
            "latency_validity": validity,
            "first_attempt_success_latency_s": (
                {"n": len(first_ok), "p50": round(statistics.median(r["latency_ms"] for r in first_ok) / 1000, 1),
                 "max": round(max(r["latency_ms"] for r in first_ok) / 1000, 1)}
                if first_ok and validity == "PER_REQUEST" else "not usable (SHARED_FINALIZE ledger)" if first_ok else None),
        })
    usable = [r for r in runs if r["latency_validity"] == "PER_REQUEST" and isinstance(r["first_attempt_success_latency_s"], dict)]
    document = {
        "schema_version": "t3_round25_stance_timeout_evidence.v1",
        "runs": runs,
        "summary": {
            "runs_with_sent_stance_requests": len(runs),
            "per_attempt_timeouts_seen_s": dict(Counter(str(r["per_attempt_timeout_s"]) for r in runs)),
            "longest_measured_successful_request_s": max((r["first_attempt_success_latency_s"]["max"] for r in usable), default=None),
            "shared_finalize_ledgers": [r["run"] for r in runs if r["latency_validity"] == "SHARED_FINALIZE"],
            "reading": ("No saved run let a stance request run longer than its per-attempt timeout (20 s or 45 s; the 10-07 direction attempt 45 s), "
                        "so no saved measurement shows how long a request takes when allowed to run past 45 s. The long latencies in "
                        "SHARED_FINALIZE ledgers (up to 657 s) are start-to-ledger-finalize times, not request durations."),
        },
    }
    out.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(document["summary"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
