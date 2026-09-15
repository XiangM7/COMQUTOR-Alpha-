import json
from datetime import datetime
from collections import defaultdict

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

def simulate_run(run_id):
    recs = [json.loads(l) for l in open(f"outputs/runs/{run_id}/llm_semantic_calls.jsonl")]
    recs.sort(key=lambda r: r["call_sequence"])

    cache = {}  # cache_key -> (completed_at, validated_output_sha256, task)
    simple_hits = 0
    inflight_only_duplicates = 0
    provider_calls_before = 0
    provider_calls_after = 0
    per_task = defaultdict(lambda: {"requests":0, "unique_keys": set(), "simple_hits":0, "inflight_only":0, "provider_calls_before":0, "provider_calls_after":0})

    for r in recs:
        key = r["cache"]["cache_key"]
        task = r["task"]
        retry_count = r.get("retry_count", 0)
        provider_status = r.get("provider_status")
        started = parse(r["started_at"])
        completed = parse(r["completed_at"])
        eligible = (
            r.get("validation_status") == "accepted"
            and provider_status == "success"
            and not r.get("fallback_used")
            and r.get("validated_output") is not None
        )
        was_real_provider_call = provider_status in ("success", "error", "provider_error", "timeout") or provider_status is not None
        real_calls_this_record = 1 + retry_count  # historical actual calls made (no cache existed)
        provider_calls_before += real_calls_this_record
        per_task[task]["requests"] += 1
        per_task[task]["unique_keys"].add(key)
        per_task[task]["provider_calls_before"] += real_calls_this_record

        if key in cache:
            cache_completed_at, cached_output_sha, cached_task = cache[key]
            if started >= cache_completed_at:
                # Simple completed-response cache would have served this one -- zero provider calls.
                simple_hits += 1
                per_task[task]["simple_hits"] += 1
                # output equivalence check
                if r.get("validated_output_sha256") != cached_output_sha:
                    print("MISMATCH", run_id, task, key)
            else:
                # Started before the original finished -- a simple exact-match
                # completed-response cache could NOT have served this one (the
                # earlier call hadn't finished yet); only single-flight
                # coalescing could avoid this specific duplicate call.
                inflight_only_duplicates += 1
                per_task[task]["inflight_only"] += 1
                provider_calls_after += real_calls_this_record
                per_task[task]["provider_calls_after"] += real_calls_this_record
                # this record's own successful completion can still populate the cache for FUTURE lookups
                if eligible:
                    cache[key] = (completed, r.get("validated_output_sha256"), task)
        else:
            provider_calls_after += real_calls_this_record
            per_task[task]["provider_calls_after"] += real_calls_this_record
            if eligible:
                cache[key] = (completed, r.get("validated_output_sha256"), task)

    return {
        "provider_calls_before": provider_calls_before,
        "provider_calls_after": provider_calls_after,
        "saved": provider_calls_before - provider_calls_after,
        "simple_hits": simple_hits,
        "inflight_only_duplicates": inflight_only_duplicates,
        "per_task": {t: {**v, "unique_keys": len(v["unique_keys"])} for t, v in per_task.items()},
    }

results = {}
for label, run_id in RUNS.items():
    results[label] = simulate_run(run_id)
    r = results[label]
    print(f"{label}: before={r['provider_calls_before']} after={r['provider_calls_after']} saved={r['saved']} simple_hits={r['simple_hits']} inflight_only={r['inflight_only_duplicates']}")

json.dump(results, open("/tmp/cache_simulation_results.json","w"), indent=2)
