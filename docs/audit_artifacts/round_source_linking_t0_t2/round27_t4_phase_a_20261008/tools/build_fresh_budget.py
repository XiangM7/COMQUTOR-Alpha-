#!/usr/bin/env python3
"""T4 Phase A: NVDA Fresh Run request budget, stop rules, duration and cost ESTIMATES (zero network).

Inputs (all already saved): the derived usage reports of 03_metering/ (per-request tokens and cost by step), the full-budget rehearsal on
the 10-02 NVDA agent outputs (request counts per task under the current pipeline), the T3 execution's measured request durations, and the
claim counts of the saved NVDA runs. The new run's claim count is unknown, so every figure is given for a range of claim counts; nothing
here promises the budget is enough. Request caps are the only hard guards -- there is no USD guard, so the cost figures are estimates,
not a cap.

    python build_fresh_budget.py --out 04_fresh_prep/budget.json
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
T4 = HERE.parent
D = HERE.parents[1]
METERING = T4 / "03_metering"
PROPOSED = {"week2_max_calls": 1800, "research_agent_max_actual_requests": 100, "research_agent_max_retries": 0, "week2_retries": 0,
            "job_timeout_seconds": 14400}
NVDA_HISTORY_CLAIMS = {"2026-07-17": 681, "2026-07-30": 2173, "2026-07-31": 652, "2026-08-11": 863, "2026-08-14": 743, "2026-08-22": 794,
                       "2026-08-25": 768, "2026-08-27": 822, "2026-08-28": 716, "2026-09-01": 786, "2026-09-02": 776, "2026-09-04": 733,
                       "2026-09-16": 978, "2026-09-17": 1102, "2026-10-02": 1040}


def _per_request(reports: list[str], layer_step: str) -> dict:
    tokens, floor, ceiling, n = {"input": 0, "output": 0}, 0.0, 0.0, 0
    for name in reports:
        report = json.loads((METERING / f"usage_report_{name}.json").read_text(encoding="utf-8"))
        for r in report["requests"]:
            if f"{r['layer']}:{r['step']}" != layer_step and not (layer_step == "research_agent:*" and r["layer"] == "research_agent"):
                continue
            if r["cost"].get("status") != "estimated":
                continue
            n += 1
            tokens["input"] += r["tokens"]["input"]
            tokens["output"] += r["tokens"]["output"]
            floor += r["cost"]["usd_off_peak_floor"]
            ceiling += r["cost"]["usd_peak_ceiling"] or 0
    return {"sample_requests": n, "avg_input_tokens": round(tokens["input"] / n) if n else None,
            "avg_output_tokens": round(tokens["output"] / n) if n else None,
            "avg_usd_off_peak_floor": round(floor / n, 6) if n else None, "avg_usd_peak_ceiling": round(ceiling / n, 6) if n else None,
            "from": reports}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    rehearsal = json.loads((T4 / "04_fresh_prep" / "rehearsal_full.json").read_text(encoding="utf-8"))
    durations = json.loads((D / "round25_t3_minimal_prep_20261008/C_execution_results/request_durations_from_checkpoint.json").read_text(encoding="utf-8"))["by_task"]
    unit = {
        "content_support_verification": _per_request(["t3joint-20261008T170322Z-bd99811e"], "week2_semantic:content_support_verification"),
        "alpha_classifier": _per_request(["amd_recovery-20261007T053635Z-26d6cd1a", "t3joint-20261008T170322Z-bd99811e"], "week2_semantic:alpha_classifier"),
        "evidence_stance_classifier": _per_request(["nvda_034a0a60_2026-10-02", "amd_1bad76a7_2026-10-05", "t3joint-20261008T170322Z-bd99811e"], "week2_semantic:evidence_stance_classifier"),
        "structured_adapter": _per_request(["nvda_034a0a60_2026-10-02", "amd_1bad76a7_2026-10-05", "amd_c904d4cc_2026-10-06"], "week2_semantic:structured_adapter"),
        "structure_extractor": _per_request(["nvda_034a0a60_2026-10-02", "amd_1bad76a7_2026-10-05", "amd_c904d4cc_2026-10-06"], "week2_semantic:structure_extractor"),
        "research_agent": _per_request(["nvda_034a0a60_2026-10-02", "amd_1bad76a7_2026-10-05", "amd_c904d4cc_2026-10-06"], "research_agent:*"),
    }
    seen = rehearsal["requests_by_task"]
    rehearsal_claims = rehearsal["alpha_classification_completion"]["total_claims"]
    ratios = {"content_support_per_claim": [round(seen["content_support_verification"] / rehearsal_claims, 4), 0.16],
              "matched_per_claim": [0.13, 0.30], "stance_targets_per_matched": [1, 3]}
    scenarios = {}
    for claims in (800, 1040, 1300, 1600, 2173):
        low = {"structured_adapter": seen["claim_batch_enrichment"], "content_support_verification": math.ceil(ratios["content_support_per_claim"][0] * claims),
               "alpha_classifier": claims, "evidence_stance_classifier": math.ceil(ratios["matched_per_claim"][0] * claims * 1 / 10),
               "structure_extractor": seen["structure_extractor"]}
        high = {"structured_adapter": 10, "content_support_verification": math.ceil(ratios["content_support_per_claim"][1] * claims),
                "alpha_classifier": claims, "evidence_stance_classifier": math.ceil(ratios["matched_per_claim"][1] * claims * 3 / 10),
                "structure_extractor": 20}
        agent_low, agent_high = 20, 40

        def cost(counts: dict, agents: int, key: str) -> float:
            return round(sum(counts[t] * (unit[t][key] or 0) for t in counts) + agents * (unit["research_agent"][key] or 0), 2)

        def hours(counts: dict, cs_seconds: float, alpha_seconds: float) -> float:
            # content support runs serially; alpha at concurrency 4; stance at 4; plus ~0.5 h for the research agents and the rest
            return round((counts["content_support_verification"] * cs_seconds + counts["alpha_classifier"] * alpha_seconds / 4
                          + counts["evidence_stance_classifier"] * 16 / 4) / 3600 + 0.5, 2)

        total_low, total_high = sum(low.values()), sum(high.values())
        scenarios[str(claims)] = {
            "week2_requests": {"low": low, "high": high, "total_low": total_low, "total_high": total_high},
            "fits_week2_cap": {"low": total_low <= PROPOSED["week2_max_calls"], "high": total_high <= PROPOSED["week2_max_calls"]},
            "research_agent_requests": [agent_low, agent_high],
            "cost_estimate_usd": {"off_peak_floor_low": cost(low, agent_low, "avg_usd_off_peak_floor"),
                                  "off_peak_floor_high": cost(high, agent_high, "avg_usd_off_peak_floor"),
                                  "peak_ceiling_high": cost(high, agent_high, "avg_usd_peak_ceiling")},
            "wall_hours_estimate": {"at_t3_median": hours(low, durations["content_support_verification"]["p50"], durations["alpha_classifier"]["p50"]),
                                    "at_t3_max_high_counts": hours(high, durations["content_support_verification"]["max"], durations["alpha_classifier"]["max"])},
        }
    cap_cost = round(PROPOSED["week2_max_calls"] * max(u["avg_usd_peak_ceiling"] or 0 for k, u in unit.items() if k != "research_agent")
                     + PROPOSED["research_agent_max_actual_requests"] * (unit["research_agent"]["avg_usd_peak_ceiling"] or 0), 2)
    doc = {
        "proposed_caps_for_owner_confirmation": PROPOSED,
        "hard_guards": {"week2_max_calls": "shared Week 2 budget: a request is reserved before it is sent; past the cap every further call is "
                                           "refused unsent (budget_exhausted) and the run is saved partial (rehearsal_budget60.json)",
                        "research_agent_max_actual_requests": "research-agent request cap (runners/request_budget.py), retries 0",
                        "job_timeout_seconds": "the job manager terminates the run at this wall time and records it failed (allowed range 30-14400)",
                        "retries": "both layers 0 (profile + COMQUTOR_RESEARCH_AGENT_MAX_RETRIES=0); unknown outcomes are never resent"},
        "no_usd_guard": "there is no dollar cap in the product; the cost figures below are estimates, not limits",
        "claim_count_unknown": {"nvda_history": NVDA_HISTORY_CLAIMS, "note": "the new run's claim count is only known after the research agents finish"},
        "per_request_unit_costs": unit,
        "ratios_used": ratios,
        "measured_durations_t3": durations,
        "scenarios_by_claim_count": scenarios,
        "absolute_cost_bound_at_caps_usd": {"value": cap_cost, "how": "every Week 2 request at the costliest step's average peak cost + every "
                                                                      "research-agent request at its average peak cost -- an unrealistic bound"},
        "pricing": "comqutor_alpha.llm.cost_basis (DeepSeek deepseek-v4-flash, docs queried 2026-09-30); estimates, not billed amounts",
    }
    Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"unit": {k: (v["sample_requests"], v["avg_usd_off_peak_floor"], v["avg_usd_peak_ceiling"]) for k, v in unit.items()},
                      "scenarios": {k: {"total": (v["week2_requests"]["total_low"], v["week2_requests"]["total_high"]), "fits": v["fits_week2_cap"],
                                        "usd": v["cost_estimate_usd"], "hours": v["wall_hours_estimate"]} for k, v in scenarios.items()},
                      "cap_cost": cap_cost}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
