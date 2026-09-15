import json
from collections import defaultdict, Counter
from datetime import datetime
import statistics

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

results = {}
for label, run_id in RUNS.items():
    audit = json.load(open(f"outputs/runs/{run_id}/run_audit.json"))
    manifest = json.load(open(f"outputs/runs/{run_id}/llm_semantic_manifest.json"))
    recs = [json.loads(l) for l in open(f"outputs/runs/{run_id}/llm_semantic_calls.jsonl")]
    by_task = defaultdict(list)
    for r in recs: by_task[r["task"]].append(r)

    task_stats = {}
    for task, rs in by_task.items():
        lat = sorted(r["latency_ms"] for r in rs)
        n = len(lat)
        def pct(p):
            idx = min(n-1, int(round(p/100*(n-1))))
            return lat[idx]
        task_start = min(parse(r["started_at"]) for r in rs)
        task_end = max(parse(r["completed_at"]) for r in rs)
        task_stats[task] = {
            "count": n,
            "sum_latency_s": round(sum(lat)/1000,1),
            "mean_ms": round(statistics.mean(lat)),
            "median_ms": round(statistics.median(lat)),
            "p50_ms": round(pct(50)), "p90_ms": round(pct(90)), "p95_ms": round(pct(95)),
            "max_ms": round(max(lat)),
            "task_span_s": round((task_end-task_start).total_seconds(),1),
            "retry_calls": sum(r.get("retry_count",0) for r in rs),
            "fallback_calls": sum(1 for r in rs if r.get("fallback_used")),
            "timeouts": sum(1 for r in rs if r.get("error_code")=="TIMEOUT" or (r.get("error_message") and "timeout" in str(r.get("error_message")).lower())),
            "validation_rejections": sum(1 for r in rs if r.get("validation_status")=="rejected"),
        }
    overall_span = (max(parse(r["completed_at"]) for r in recs) - min(parse(r["started_at"]) for r in recs)).total_seconds()
    results[label] = {
        "run_id": run_id,
        "raw_claim_count": audit.get("raw_claim_count"),
        "valid_claim_count": audit.get("valid_claim_count"),
        "analytical_claim_count": audit.get("analytical_claim_count"),
        "semantic_record_count": manifest.get("record_count"),
        "provider_call_count": manifest.get("provider_call_count"),
        "cache_hit_count": manifest.get("cache_hit_count"),
        "fallback_count": manifest.get("fallback_count"),
        "rejected_count": manifest.get("rejected_count"),
        "overall_semantic_span_s": round(overall_span,1),
        "task_stats": task_stats,
    }

print(json.dumps(results, indent=2))
