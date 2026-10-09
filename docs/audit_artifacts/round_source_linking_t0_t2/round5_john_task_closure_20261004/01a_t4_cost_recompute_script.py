"""Round 5 (2026-10-04), T4 Phase A item 1: retroactively recompute
TradingAgents-layer call cost for already-persisted historical runs, using
the FIXED comqutor_alpha.llm.cost_basis (model-name-based provider
disambiguation). Pure offline recomputation of already-fetched token
counts -- zero new Provider calls, zero writes to the original run
directory. Reports which runs' cost became resolvable and which remain
genuinely unresolvable (no pricing entry for that specific model)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

from comqutor_alpha.llm.cost_basis import estimate_cost_usd
from comqutor_alpha.runners.diagnostics import summarize_usage_records

CANDIDATE_RUN_DIRS = [
    Path("Outputs/runs/034a0a60-430e-41f8-8321-03a11389707a"),  # NVDA (current code, Fresh Run)
    Path("outputs/runs/d5b60b8a-66b8-44c1-9f55-ee345e58c48d"),  # AMD (historical)
]

results = {}
for run_dir in CANDIDATE_RUN_DIRS:
    calls_path = run_dir / "tradingagents_llm_calls.jsonl"
    before_summary_path = run_dir / "tradingagents_llm_usage_summary.json"
    if not calls_path.exists():
        results[str(run_dir)] = {"status": "NO_RAW_CALL_LOG_FOUND"}
        continue

    before_summary = json.loads(before_summary_path.read_text()) if before_summary_path.exists() else None
    raw_records = [json.loads(line) for line in calls_path.read_text().splitlines() if line.strip()]

    recomputed_records = []
    for record in raw_records:
        token_usage = record.get("token_usage") or {}
        cost = estimate_cost_usd(
            record.get("provider"), record.get("model"),
            token_usage.get("input_tokens"), token_usage.get("output_tokens"),
        )
        new_record = dict(record)
        new_record["cost_usd_BEFORE_FIX"] = record.get("cost_usd")
        new_record["cost_basis_BEFORE_FIX"] = record.get("cost_basis")
        new_record["cost_usd"] = cost.usd
        new_record["cost_basis"] = cost.basis
        recomputed_records.append(new_record)

    after_summary = summarize_usage_records(recomputed_records)
    results[str(run_dir)] = {
        "status": "RECOMPUTED",
        "call_count": len(raw_records),
        "total_cost_usd_BEFORE_FIX": before_summary.get("total_cost_usd") if before_summary else None,
        "total_cost_usd_AFTER_FIX": after_summary["total_cost_usd"],
        "cost_basis_notes_AFTER_FIX": after_summary["cost_basis_notes"],
        "per_provider_model_AFTER_FIX": after_summary["per_provider_model"],
    }

print(json.dumps(results, indent=2, default=str))
