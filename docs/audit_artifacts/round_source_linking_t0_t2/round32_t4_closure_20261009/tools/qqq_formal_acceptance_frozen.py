#!/usr/bin/env python3
"""T4 round 32: QQQ on frozen input through the existing formal acceptance entry, on the final code. Read-only on outputs/runs,
zero network (sockets stubbed below), starts no research.

Entry: comqutor_alpha.regression.formal_acceptance_report.evaluate_saved_run (the unified formal-acceptance entry for a saved
run; it calls acceptance_engine.run_formal_acceptance). Input: the saved QQQ run 0d890564 (the run Round 24's six-ticker
evaluation used). Every item of the verdict is sorted into: executed with a verdict (pass / fail), not evaluable (and why),
contract rule not executed for this ticker, configuration error, or artifact incompleteness -- nothing is turned into PASS.

    python qqq_formal_acceptance_frozen.py --out 06_frozen_checks/qqq_formal_acceptance.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
sys.path.insert(0, str(REPO))
attempts: list[str] = []


def _refuse(name):
    def stub(*a, **k):
        attempts.append(name)
        raise RuntimeError("network attempted: " + name)
    return stub


socket.socket.connect = _refuse("connect")
socket.socket.connect_ex = _refuse("connect_ex")
socket.create_connection = _refuse("create_connection")
socket.getaddrinfo = _refuse("getaddrinfo")
urllib.request.urlopen = _refuse("urlopen")

QQQ_RUN = "0d890564-2479-4361-94e8-25c48af3b9a8"
RUNS_ROOT = REPO / "outputs" / "runs"


def _tree(directory: Path) -> dict[str, str]:
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directory.rglob("*")) if p.is_file()}


def main(argv=None) -> int:
    from comqutor_alpha.regression.formal_acceptance_report import evaluate_saved_run

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    run_dir = RUNS_ROOT / QQQ_RUN
    before = _tree(run_dir)
    entry = evaluate_saved_run(ticker="QQQ", run_id=QQQ_RUN, runs_root=RUNS_ROOT)
    after = _tree(run_dir)
    verdict = entry.get("verdict") or {}
    rules = verdict.get("effective_rules") or {}
    families = verdict.get("rule_family_results") or {}
    sorted_items = {
        "contract_rules_executed": [
            {"rule_id": r.get("rule_id"), "family": r.get("family"), "blocking": r.get("blocking"), "verdict": r.get("verdict"),
             "reason_code": r.get("reason_code"), "evidence_trigger": {k: (r.get("evidence_trigger") or {}).get(k) for k in
                                                                       ("state", "strength", "source", "matrix_run_id", "evaluated_run_id", "reason_code")},
             "detail": r.get("detail")}
            for r in verdict.get("contract_rule_results") or []],
        "contract_rules_not_executed_for_ticker": (verdict.get("coverage") or {}).get("contract_rules_not_executed_for_ticker"),
        "not_evaluable": [r for r in verdict.get("review_reasons") or [] if r.get("verdict") == "not_evaluable"],
        "needs_review_other": [r for r in verdict.get("review_reasons") or [] if r.get("verdict") != "not_evaluable"],
        "failures_research_does_not_match": verdict.get("failure_reasons"),
        "config_error": verdict.get("config_error_reason_code"),
        "semantic_input_error": verdict.get("semantic_input_reason_code"),
        "artifact_completeness": entry.get("artifact_completeness"),
        "artifact_missing_files": entry.get("artifact_missing_files"),
        "diagnostic_findings": verdict.get("diagnostic_findings"),
        "undeclared_admitted_conflicts": verdict.get("undeclared_admitted_conflicts"),
    }
    doc = {
        "entry": "comqutor_alpha.regression.formal_acceptance_report.evaluate_saved_run -> acceptance_engine.run_formal_acceptance",
        "ticker": "QQQ", "run_id": QQQ_RUN, "input": "saved (frozen) run outputs/runs/" + QQQ_RUN + " -- no research started, nothing re-fetched",
        "network_attempts": len(attempts), "run_dir_unchanged": before == after, "files_read_hashed": len(before),
        "status": entry.get("status"), "formal_status": verdict.get("formal_status"),
        "stance_source": entry.get("stance_source"), "admitted_conflicts": entry.get("admitted_conflicts"), "main_conflict": entry.get("main_conflict"),
        "effective_rules": rules,
        "rule_family_results": families,
        "release": verdict.get("release"),
        "coverage": verdict.get("coverage"),
        "items_sorted": sorted_items,
        "verdict_full": verdict,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: doc[k] for k in ("status", "formal_status", "network_attempts", "run_dir_unchanged", "admitted_conflicts", "main_conflict")},
                     ensure_ascii=False, default=str))
    print(json.dumps({k: (v if not isinstance(v, list) else len(v)) for k, v in sorted_items.items() if k not in ("diagnostic_findings",)}, ensure_ascii=False, default=str)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
