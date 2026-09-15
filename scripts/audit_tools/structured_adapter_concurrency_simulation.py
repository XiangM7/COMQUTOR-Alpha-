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
    sa = sorted([r for r in recs if r["task"] == "structured_adapter"], key=lambda r: r["call_sequence"])
    # per-call durations (true batch-level independent unit)
    call_durations = [r["latency_ms"]/1000.0 for r in sa]
    # per-agent totals (agent-level unit: sum of that agent's own batches, since
    # within one agent, batches are still processed serially in this design)
    per_agent = {}
    for r in sa:
        agent = r["input_payload"].get("agent")
        per_agent.setdefault(agent, 0.0)
        per_agent[agent] += r["latency_ms"]/1000.0
    agent_durations = list(per_agent.values())
    actual_span = (max(parse(r["completed_at"]) for r in sa) - min(parse(r["started_at"]) for r in sa)).total_seconds() if sa else 0.0

    batch_sim = {c: round(makespan(call_durations, c), 1) for c in (1,2,4,6,8)}
    agent_sim = {c: round(makespan(agent_durations, c), 1) for c in (1,2,4,6,8)}
    results[label] = {
        "n_calls": len(sa), "n_agents": len(per_agent), "actual_span_s": round(actual_span,1),
        "batch_level_sim": batch_sim, "agent_level_sim": agent_sim,
        "agent_durations": {k: round(v,1) for k,v in per_agent.items()},
    }
    print(f"{label}: calls={len(sa)} agents={len(per_agent)} actual_span={round(actual_span,1)}")
    print(f"   batch-level sim: {batch_sim}")
    print(f"   agent-level sim: {agent_sim}")
    print(f"   per-agent totals: { {k: round(v,1) for k,v in per_agent.items()} }")

json.dump(results, open("/tmp/adapter_concurrency_sim_results.json","w"), indent=2)
