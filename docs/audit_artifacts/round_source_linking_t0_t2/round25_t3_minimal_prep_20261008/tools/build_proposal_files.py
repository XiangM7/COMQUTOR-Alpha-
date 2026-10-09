#!/usr/bin/env python3
"""Round 25 (T3 prep), deliverable 6: write the unified request budget (06_proposal/budget.json) and an UNSIGNED plan template
(06_proposal/authorized_plan_TEMPLATE.json) from the zero-call sizing and the driver's proposed configuration. Zero calls, zero network.

The template carries authorized=false and an empty authorized_by: t3_joint_sample_driver.py predict refuses it as it is. To authorize, the
owner fills both, changes nothing else (or states every change), and passes the file's sha256 on the command line.

    python build_proposal_files.py --sizing <06_proposal/request_sizing_zero_call.json> --out-dir <06_proposal>
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
sys.path.insert(0, str(REPO))
AUDIT = REPO / "docs/audit_artifacts/round_source_linking_t0_t2"
PACKAGE = HERE.parent
MANIFEST = PACKAGE / "04_joint_sample/joint_sample_v3_manifest.json"

_spec = importlib.util.spec_from_file_location("t3_joint_sample_driver_for_proposal", AUDIT / "t3_joint_sample_driver.py")
assert _spec is not None and _spec.loader is not None
driver = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = driver
_spec.loader.exec_module(driver)

from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizing", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    out_dir = Path(args.out_dir)
    budget_path, plan_path = out_dir / "budget.json", out_dir / "authorized_plan_TEMPLATE.json"
    for path in (budget_path, plan_path):
        if path.exists():
            print("refusing: output exists", path, file=sys.stderr)
            return 2
    sizing = json.loads(Path(args.sizing).read_text(encoding="utf-8"))
    config = driver.FrozenConfig()
    cs, alpha, stance = sizing["content_support_verification"], sizing["alpha_classifier"], sizing["evidence_stance_classifier"]
    if (cs["requests"], alpha["requests"], stance["requests_upper_bound"]) != tuple(config.max_requests[t] for t in driver.TASKS):
        print("refusing: the proposed request caps differ from the zero-call sizing", file=sys.stderr)
        return 3
    budget = {
        "schema_version": "t3_round25_request_budget.v1",
        "unit": "provider requests actually sent; every sent request counts -- success, failure, timeout and truncation alike",
        "per_task": {
            "content_support_verification": {
                "reusable_saved_results": 0,
                "why_none_reusable": ("the 5 saved LLM verdicts on these claims (c904d4cc) record no model, prompt, budget or raw response -- the task "
                                      "never reaches the call ledger (not in llm_runtime.contracts.SEMANTIC_TASKS); none of the 17 claims is resolved "
                                      "by the deterministic data-fact verifier"),
                "new_requests": cs["requests"], "exact": True, "items": cs["items"], "batch_size": config.content_support_batch_size,
                "not_requested": cs["full_chain_samples_not_submitted_by_production_rules"],
                "not_requested_partial_chain_samples": 15,
            },
            "alpha_classifier": {
                "reused_saved_production_answers": alpha.get("reused_saved_production_answers", 0), "reused_from": alpha.get("reused_from"),
                "new_requests": alpha["requests"], "exact": True, "new_request_samples": alpha.get("new_request_samples"),
                "new_request_reasons": alpha.get("new_request_reasons"),
            },
            "evidence_stance_classifier": {
                "reusable_saved_results": 0,
                "why_none_reusable": "no saved LLM stance exists for these claims (budget_exhausted in 034a0a60 and 1bad76a7; not run in c904d4cc)",
                "new_requests_upper_bound": stance["requests_upper_bound"], "exact": False, "basis": stance["basis"],
            },
            "other_tasks": {"new_requests": 0, "why": "no Fresh run, no adapter / structure-extractor / TradingAgents request; the five links need none"},
        },
        "total_requests_upper_bound": cs["requests"] + alpha["requests"] + stance["requests_upper_bound"],
        "hard_caps": dict(config.max_requests),
        "cap_mechanism": ("each task has its own production gateway whose call budget (max_calls) reserves one call per attempt; with application "
                          "retries 0 and SDK retries 0 the cap is the exact number of requests that task can send; a request refused locally "
                          "(input too large) is not sent and not reserved"),
        "usage_accounting": ("reported only from the provider's own usage fields per request; a request with no usage (e.g. timeout) is reported as "
                             "usage missing, never estimated; a timed-out request may still be processed and billed by the provider"),
        "cost_reference_not_a_guarantee": {
            "price_table": "comqutor_alpha/llm/cost_basis.py, deepseek-v4-flash, USD per 1M tokens: off-peak 0.15 in / 0.60 out, peak 0.30 in / 1.20 out (queried 2026-09-30 by the repo, not re-checked)",
            "alpha_classifier_7_requests_saved_usage": "per request in deployed runs: prompt <= 2,236 tokens, completion p50 267 / p95 2,400 / max 8,566",
            "content_support_17_requests_saved_usage": "Phase C (older prompt, smaller payload): prompt 1,887-3,042, completion up to the 8,192 cap; today's payloads are up to 46,064 characters, so prompt tokens will be larger -- not estimated",
            "evidence_stance_up_to_5_requests_saved_usage": "no saved stance request ever recorded usage -- not estimated",
            "statement": "no dollar total is given; actual usage is read back from each response after the run",
        },
    }
    plan = {
        "authorized": False,
        "authorized_by": "",
        "authorization_reference": "",
        "execution_id": "t3joint-<UTC timestamp>-<8 hex>",
        "out_dir": "outputs/t3_joint_evaluations",
        "manifest": str(MANIFEST.relative_to(REPO)),
        "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        "prompt_identity_sha256": {t: Week2LLMGateway.prompt_identity_sha256(t) for t in driver.TASKS},
        "config": asdict(config),
        "note": "UNSIGNED TEMPLATE -- predict refuses it until authorized=true and authorized_by is filled; its sha256 must be passed as --plan-sha256",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    budget_path.write_text(json.dumps(budget, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"total_requests_upper_bound": budget["total_requests_upper_bound"], "hard_caps": budget["hard_caps"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
