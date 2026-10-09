#!/usr/bin/env python3
"""Round 24: re-derives the numbers and facts the Chinese report quotes (statuses of the six pinned runs, the 76-run transition counts, the Alpha facts of the
contract rules, the Step-4 reproduction) from the JSON outputs of this directory, so a number in the prose cannot drift from the data.

    python check_report_numbers.py            # writes report_numbers_check.json next to the report; exit 0 only when every check holds
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # the Round 24 directory


def load(rel):
    return json.loads((HERE / rel).read_text(encoding="utf-8"))


def rule(entry, rule_id):
    return next(r for r in entry["verdict"]["contract_rule_results"] if r["rule_id"] == rule_id)


def main() -> int:
    report = (HERE / "01_中文简明验收报告_T2.md").read_text(encoding="utf-8")
    six = load("six_ticker/formal_acceptance_verdicts.json")["tickers"]
    bound = load("matrix_bound_runs/formal_acceptance_verdicts.json")["tickers"]
    delta = load("before_after/delta_all_saved_runs.json")
    research = load("before_after/research_facts_unchanged.json")
    checks: list[tuple[str, bool]] = []

    def ok(name, condition):
        checks.append((name, bool(condition)))

    for ticker, status in {"NVDA": "needs_review", "QQQ": "needs_review", "SNDK": "pass", "MSFT": "needs_review", "TSM": "needs_review", "AMD": "needs_review"}.items():
        ok(f"{ticker}: formal_status is {status}", six[ticker]["verdict"]["formal_status"] == status)
        ok(f"{ticker}: run id prefix is in the report", six[ticker]["run_id"][:8] in report)
    ok("76 runs compared", delta["runs_compared"] == 76)
    ok("transition counts", delta["transitions"] == {"needs_review -> pass": 2, "pass -> fail": 1, "pass -> needs_review": 15})
    ok("18 status changes", delta["runs_whose_formal_status_changed"] == 18)
    ok("15 reason-only changes", delta["runs_whose_reasons_changed_but_status_did_not"] == 15)
    ok("research facts unchanged", research["research_unchanged"] is True)

    a101 = rule(six["NVDA"], "NVDA-A101-AI-GROWTH")["alpha_recognition"][0]
    a304 = rule(six["NVDA"], "NVDA-A304-VALUATION-RISK")["alpha_recognition"][0]
    msft = rule(six["MSFT"], "MSFT-A102-DIRECT-INFERENCE-TRIGGER")["alpha_recognition"][0]
    amd = {c["alpha_id"]: (c["activation_level"], c["activation_score"]) for c in rule(six["AMD"], "AMD-AI-GROWTH-VS-VALUATION")["component_alphas"]}
    ok("NVDA A101: 21 claims, candidate 48.5501", (a101["claims_matched_to_this_alpha"], a101["activation_level"], a101["activation_score"]) == (21, "candidate", 48.5501))
    ok("NVDA A304: 76 claims, dominant 71.7302", (a304["claims_matched_to_this_alpha"], a304["activation_level"], a304["activation_score"]) == (76, "dominant", 71.7302))
    ok("MSFT A102: 6 claims, candidate 41.9468", (msft["claims_matched_to_this_alpha"], msft["activation_level"], msft["activation_score"]) == (6, "candidate", 41.9468))
    ok("AMD components", amd == {"A101": ("active", 58.5954), "A201": ("active", 62.5918), "A301": ("active", 65.2271), "A304": ("dominant", 81.5323)})
    ok("every contract rule of the pinned NVDA / MSFT / AMD runs is not_evaluable", all(r["verdict"] == "not_evaluable" for t in ("NVDA", "MSFT", "AMD") for r in six[t]["verdict"]["contract_rule_results"]))
    ok("NVDA pinned: release unresolved, blocks nothing", six["NVDA"]["verdict"]["release"]["release_status"] == "unresolved" and six["NVDA"]["verdict"]["release"]["blocks_release"] is False)

    nvda_rules = bound["NVDA"]["verdict"]["contract_rule_results"]
    msft_rule = bound["MSFT"]["verdict"]["contract_rule_results"][0]
    amd_rule = bound["AMD"]["verdict"]["contract_rule_results"][0]
    ok("bound NVDA: three rules PASS, John's rows PASS", [r["verdict"] for r in nvda_rules] == ["pass"] * 3 and [r["john_result"] for r in nvda_rules] == ["PASS"] * 3)
    ok("bound NVDA: A101 active 70.0 with 62 claims", (nvda_rules[0]["alpha_recognition"][0]["activation_level"], nvda_rules[0]["alpha_recognition"][0]["activation_score"], nvda_rules[0]["alpha_recognition"][0]["claims_matched_to_this_alpha"]) == ("active", 70.0, 62))
    ok("bound MSFT: A102 FAIL, non-blocking, blocks nothing, John FAIL", msft_rule["verdict"] == "fail" and msft_rule["blocking"] is False and bound["MSFT"]["verdict"]["release"]["blocks_release"] is False and msft_rule["john_result"] == "FAIL")
    ok("bound MSFT: A102 candidate 34.9674 with 8 claims", (msft_rule["alpha_recognition"][0]["activation_level"], msft_rule["alpha_recognition"][0]["activation_score"], msft_rule["alpha_recognition"][0]["claims_matched_to_this_alpha"]) == ("candidate", 34.9674, 8))
    ok("bound AMD: composite PASS, John PASS", amd_rule["verdict"] == "pass" and amd_rule["john_result"] == "PASS")

    document = {"checks": [{"check": name, "ok": ok_} for name, ok_ in checks], "all_ok": all(c for _, c in checks)}
    (HERE / "report_numbers_check.json").write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    failed = [name for name, ok_ in checks if not ok_]
    print(json.dumps({"checks": len(checks), "failed": failed}, ensure_ascii=False))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
