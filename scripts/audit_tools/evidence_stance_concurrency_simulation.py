import json, heapq
from datetime import datetime

RUNS = {
    "NVDA": "57d7b4c4-dbb9-4134-b962-ee2a873941cc",
    "QQQ_historical": "f88c8956-cb62-48aa-9951-89f8e8a95f83",
    "MSFT": "43472ace-454f-4c69-892c-adca91c25be7",
    "SNDK": "e8e0f398-7b26-4462-8135-a1410ea5b335",
    "TSM": "dfc7ceb3-3584-4514-bd84-6c371aab3e95",
    "AMD": "949f685a-3945-4fd0-b7b9-362b37c90721",
    "QQQ_postfix": "f239a53f-4ebe-455c-bb76-5f5485903901",
}

def parse(ts): return datetime.fromisoformat(ts)

def makespan(durations_s, workers):
    """List-scheduling simulation: workers process jobs in the given order,
    each worker picks the next job as soon as it's free (greedy), which is
    the standard longest-processing-time-agnostic simulation for a bounded
    worker pool given a fixed submission order (matches ThreadPoolExecutor's
    own behavior when all jobs are submitted at once)."""
    if not durations_s:
        return 0.0
    workers = max(1, workers)
    heap = [0.0] * min(workers, len(durations_s))
    for d in durations_s:
        finish_time = heapq.heappop(heap) + d
        heapq.heappush(heap, finish_time)
    return max(heap)

results = {}
for label, run_id in RUNS.items():
    recs = [json.loads(l) for l in open(f"outputs/runs/{run_id}/llm_semantic_calls.jsonl")]
    stance = sorted([r for r in recs if r["task"] == "evidence_stance_classifier"], key=lambda r: r["call_sequence"])
    durations = [r["latency_ms"] / 1000.0 for r in stance]
    actual_span = (max(parse(r["completed_at"]) for r in stance) - min(parse(r["started_at"]) for r in stance)).total_seconds() if stance else 0.0
    sim = {c: round(makespan(durations, c), 1) for c in (1, 2, 4, 6, 8)}
    results[label] = {"n_calls": len(stance), "actual_serial_span_s": round(actual_span,1), "sum_latency_s": round(sum(durations),1), "sim_makespan": sim, "max_call_s": round(max(durations),1) if durations else 0}
    print(label, "n=", len(stance), "actual_span=", round(actual_span,1), "sim:", sim, "max_call=", round(max(durations),1) if durations else 0)

json.dump(results, open("/tmp/stance_concurrency_sim_results.json","w"), indent=2)
