#!/usr/bin/env python3
"""T4 Phase A: derived LLM usage/cost reports for existing runs (zero network; original directories are only read).

Uses the production ``comqutor_alpha.llm.run_usage_report`` -- the same code a new run writes at finalization -- and writes each report
into the T4 directory, never into the run. Known gaps come from the earlier reconciliation records and are cited, never filled in.

    python build_usage_reports.py --out-dir 03_metering
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
RUNS = REPO / "outputs" / "runs"
T3 = REPO / "outputs" / "t3_joint_evaluations" / "t3joint-20261008T170322Z-bd99811e"
D = "docs/audit_artifacts/round_source_linking_t0_t2"


def targets():
    from comqutor_alpha.llm.run_usage_report import UsageSources, sources_for_run_dir

    nvda = sources_for_run_dir(RUNS / "034a0a60-430e-41f8-8321-03a11389707a")
    nvda.known_gaps = [f"{D}/nvda_run_request_reconciliation_and_audit_fix.md: the Week 2 ledger records 448 real attempts while about 688 "
                       "requests were actually made -- about 240 attempts lost their per-attempt record to the concurrent-audit bug fixed in "
                       "round 12/13; their usage and cost are unknown and are NOT in this report's totals. 400 alpha_classifier calls were "
                       "refused at the 700-call budget (not sent)."]
    amd_10_06 = sources_for_run_dir(RUNS / "c904d4cc-dc09-495c-aec5-b056979948e1")
    amd_10_06.known_gaps = [f"{D}/round12_alpha_classifier_audit_fix_20261006/: 973 of 975 alpha_classifier calls of this run failed inside the "
                            "audit layer (concurrent-attempt refusal) and left no semantic-ledger record; whether each reached the provider is "
                            "recorded there, not here."]
    t3 = UsageSources(
        run_id=T3.name,
        semantic_ledgers=[T3 / t / T3.name / "llm_semantic_calls.jsonl" for t in ("alpha_classifier", "evidence_stance_classifier")],
        audit_dirs=[T3 / t / T3.name / "error_logs" for t in ("content_support_verification", "alpha_classifier", "evidence_stance_classifier")],
        known_gaps=["content_support_verification was not in the semantic-call ledger at execution time (fixed in round 26); its 17 requests "
                    "come from the wire audit only."],
    )
    return {
        "nvda_034a0a60_2026-10-02": nvda,
        "amd_1bad76a7_2026-10-05": sources_for_run_dir(RUNS / "1bad76a7-72ac-4c8b-8189-2e5c0f1a6105"),
        "amd_c904d4cc_2026-10-06": amd_10_06,
        "amd_recovery-20261007T053635Z-26d6cd1a": sources_for_run_dir(RUNS / "recovery-20261007T053635Z-26d6cd1a"),
        "t3joint-20261008T170322Z-bd99811e": t3,
    }


def _tree(directory: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(Path(directory).rglob("*")):
        if p.is_file():
            h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    from comqutor_alpha.llm.run_usage_report import build_usage_report

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    index = {}
    for label, sources in targets().items():
        root = RUNS / sources.run_id if (RUNS / sources.run_id).is_dir() else T3
        before = _tree(root)
        report = build_usage_report(sources)
        after = _tree(root)
        (out / f"usage_report_{label}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
        t = report["totals"]
        index[label] = {"source_unchanged": before == after, "upstream_agents": report["upstream_agents"]["count"],
                        **{layer: {k: t[layer][k] for k in ("logical_calls", "actual_http_requests", "retries", "not_sent", "served_from_cache",
                                                            "outcomes", "requests_missing_usage", "usage_missing_ratio", "tokens_known",
                                                            "cost_estimate_usd")} for layer in ("research_agent", "week2_semantic")},
                        "corrections": report["corrections"], "deduplication": report["deduplication"], "known_gaps": report["known_gaps"]}
    (out / "usage_reports_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(index, ensure_ascii=False)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
