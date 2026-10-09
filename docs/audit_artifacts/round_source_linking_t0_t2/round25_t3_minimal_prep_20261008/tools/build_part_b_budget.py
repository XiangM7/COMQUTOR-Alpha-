#!/usr/bin/env python3
"""Round 25 part B, item 3: the unified request budget, from the zero-call sizing, the frozen plan template and the collection list.

    python build_part_b_budget.py --out <B3_budget/budget.json>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out)
    if out.exists():
        print("refusing: output exists", out, file=sys.stderr)
        return 2
    sizing = json.loads((PACKAGE / "B3_budget" / "request_sizing.json").read_text(encoding="utf-8"))
    plan = json.loads((PACKAGE / "B4_execution" / "authorized_plan_TEMPLATE.json").read_text(encoding="utf-8"))
    collection = json.loads((PACKAGE / "B1_samples_v4" / "collection_list.json").read_text(encoding="utf-8"))
    caps = plan["config"]["max_requests"]
    cs, alpha, stance = sizing["content_support_verification"], sizing["alpha_classifier"], sizing["evidence_stance_classifier"]
    assert (cs["requests"], alpha["requests"], stance["requests_upper_bound"]) == (caps["content_support_verification"], caps["alpha_classifier"], caps["evidence_stance_classifier"])
    budget = {
        "schema_version": "t3_round25_part_b_budget.v1",
        "unit": "requests actually sent to an external service; every sent request counts -- success, failure, timeout and truncation alike; nothing is retried",
        "A_prediction_execution": {
            "content_support_verification": {"new_requests": cs["requests"], "exact": True, "reused_saved_results": 0,
                                             "why_no_reuse": "no saved content-support result on these claims has a verifiable model / prompt / source-hash identity",
                                             "claims_production_does_not_send": cs["samples_not_submitted_by_production_rules"]},
            "alpha_classifier": {"new_requests": alpha["requests"], "exact": True,
                                 "historical_answers": "33 saved production answers bound to the same request are exported for comparison only"},
            "evidence_stance_classifier": {"new_requests_upper_bound": stance["requests_upper_bound"], "exact": False,
                                           "upper_bound_by_run": stance["upper_bound_by_run"], "basis": stance["basis"]},
            "other_tasks": {"new_requests": 0, "why": "no Fresh, no agent re-run, no adapter / structure-extractor request"},
            "total_upper_bound": cs["requests"] + alpha["requests"] + stance["requests_upper_bound"],
            "hard_caps": caps,
        },
        "B_material_collection": {
            "requests_cap": collection["request_cap_total"], "items": [{k: c[k] for k in ("id", "object", "source", "request_cap", "samples")} for c in collection["items"]],
            "authorized_separately": "plan.collection.authorized -- the prediction execution does not depend on it",
        },
        "total_external_requests_upper_bound": cs["requests"] + alpha["requests"] + stance["requests_upper_bound"] + collection["request_cap_total"],
        "offline_steps": ["sample freezing and materials (done)", "frozen requests and plan template (done)", "preflight with full rehearsal (done; repeated by predict before sending)",
                          "historical comparison export (done)", "L4 eligibility (pure local functions inside predict)", "scoring after review"],
        "usage_accounting": ("only from each response's own usage fields (saved verbatim in the response audit); a request without usage (timeout, refusal) is "
                             "reported as usage missing, never estimated; a timed-out request may still be processed and billed by the provider"),
        "cost": "no dollar total is given; the repo's price table (comqutor_alpha/llm/cost_basis.py) applies to the usage actually returned",
    }
    out.write_text(json.dumps(budget, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"prediction_upper_bound": budget["A_prediction_execution"]["total_upper_bound"], "collection_cap": collection["request_cap_total"],
                      "total": budget["total_external_requests_upper_bound"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
