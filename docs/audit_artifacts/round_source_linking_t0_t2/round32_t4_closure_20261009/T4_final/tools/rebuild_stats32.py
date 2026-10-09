#!/usr/bin/env python3
"""T4 round 32: rebuild every figure the final report quotes, OFFLINE and from the package's own files (standard library only;
no repository, no network, no database), and compare with report_figures.json.

Sources inside the package:
  references/T4_delivery_round31_20261009.zip  -- the verified Round 31 package (the two Fresh run directories inside it)
  runs/<derived execution id>/                 -- the final-code derived execution (replay of Fresh #2's saved responses)
  04_tests/*_junit.xml, *_command.txt          -- final test runs; 01_regressions/*.log -- reproductions
  03_postgres/*.json                           -- PostgreSQL chain results; 06_frozen_checks/*.json -- QQQ / AMD / SNDK

    python3 tools/rebuild_stats32.py            # exit 0 only if every figure matches and is cited verbatim in the report
"""
from __future__ import annotations

import io
import json
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent
FRESH2 = "12591384-0b26-470d-a99d-a49c00be440b"
FRESH1 = "fa642639-8d93-4f9a-9de1-2c4d789eade8"
ROUND31_ZIP = PKG / "references" / "T4_delivery_round31_20261009.zip"


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def jl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.is_file() else []


def junit(name: str) -> dict:
    root = ET.parse(PKG / "04_tests" / f"{name}_junit.xml").getroot()
    suites = [root] if root.tag == "testsuite" else list(root)
    tests = sum(int(s.get("tests", 0)) for s in suites)
    failures = sum(int(s.get("failures", 0)) for s in suites)
    errors = sum(int(s.get("errors", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    return {"passed": tests - failures - errors - skipped, "failed": failures + errors, "skipped": skipped}


def command(name: str) -> dict:
    text = (PKG / "04_tests" / f"{name}_command.txt").read_text(encoding="utf-8")
    return dict(re.findall(r"^([a-z_ ()]+): (.*)$", text, re.M))


def regression_log(label: str) -> tuple[str, int]:
    text = (PKG / "01_regressions" / f"{label}.log").read_text(encoding="utf-8")
    summary = re.findall(r"(\d+ (?:passed|failed)[^\n]*)", text)
    return (summary[-1] if summary else ""), int(re.findall(r"^exit_code: (\d+)", text, re.M)[-1])


def rebuild() -> dict:
    out: dict[str, object] = {}
    # --- final tests
    for g in ("new", "replay", "pg", "affected"):
        j = junit(g)
        for k, v in j.items():
            out[f"tests.{g}.{k}"] = v
        c = command(g)
        out[f"tests.{g}.code_unchanged"] = c.get("code_unchanged_during_group")
        out[f"tests.{g}.exit"] = int(c.get("group_exit_code", -1))
    fl = (PKG / "04_tests" / "frontend.log").read_text(encoding="utf-8")
    out["tests.frontend.exit_codes"] = re.findall(r"^exit_code: (\d+)", fl, re.M)
    out["tests.frontend.vitest_passed"] = int(re.findall(r"Tests\s+(\d+) passed", fl)[-1])
    # --- regressions
    for label in ("A_head_7a9aefa", "B_fresh_code_1b53b921_before_fix", "C_worktree_before_fix", "D_worktree_after_fix"):
        summary, code = regression_log(label)
        out[f"regression.{label}"] = summary.split(" in ")[0]
    neg = (PKG / "01_regressions" / "E_negative_controls.log").read_text(encoding="utf-8")
    out["regression.negative_controls_failed"] = len(re.findall(r"^1 failed", neg, re.M))
    # --- PostgreSQL chain
    mig = load(PKG / "03_postgres" / "migrations_result.json")
    out["pg.migrations"] = len(mig["schema_migrations"])
    out["pg.tables"] = len(mig["tables"])
    rep = load(PKG / "05_replay" / "replay_report.json")
    out["pg.tables_before_derived_execution"] = len(rep["tables_before"])
    cons = load(PKG / "03_postgres" / "consistency_result.json")
    out["pg.research_runs"] = cons["table_counts"]["research_runs"]
    out["pg.agent_outputs"] = cons["table_counts"]["agent_outputs"]
    cmp_ = load(PKG / "03_postgres" / "compare_pre_restart_post_restart_result.json")
    out["pg.restart_snapshots_identical"] = cmp_["identical"]
    pre, post = load(PKG / "03_postgres" / "export_pre_restart_result.json"), load(PKG / "03_postgres" / "export_post_restart_result.json")
    rid = next(iter(post))
    out["pg.export_manifest_files"] = post[rid]["manifest_artifacts"]
    out["pg.export_same_sha_after_restart"] = pre[rid]["zip_sha256"] == post[rid]["zip_sha256"]
    out["pg.export_stage_disclosure_equals_api"] = post[rid]["stage_disclosure_zip_equals_api"]
    # --- replay (recomputed from the run directories, not read from comparison.json)
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(ROUND31_ZIP) as zf:
        for name in zf.namelist():
            if name.startswith(f"T4_delivery/runs/{FRESH2}/") or name.startswith(f"T4_delivery/runs/{FRESH1}/"):
                zf.extract(name, tmp)
        fresh2 = Path(tmp) / "T4_delivery" / "runs" / FRESH2
        fresh1 = Path(tmp) / "T4_delivery" / "runs" / FRESH1
        ex = PKG / "runs" / rep["execution_id"]

        def norm(p: Path):
            return json.loads(p.read_text(encoding="utf-8").replace(ex.name, FRESH2))

        fr = {r["claim_id"]: r for r in load(fresh2 / "structured_agent_outputs.json")["records"]}
        dr = {r["claim_id"]: r for r in norm(ex / "structured_agent_outputs.json")["records"]}
        out["replay.requests_made"] = rep["replay"]["requests_made"]
        out["replay.unmatched"] = len(rep["replay"]["unmatched_requests"])
        out["replay.timeouts_replayed"] = sum(rep["replay"]["timeouts_replayed"].values())
        out["replay.claims"] = len(dr)
        changed = [c for c in fr if json.dumps(fr[c], sort_keys=True) != json.dumps({**dr[c], "run_id": fr[c].get("run_id"), "timestamp": fr[c].get("timestamp")}, sort_keys=True)]
        out["replay.claims_changed"] = len(changed)
        out["replay.claims_changed_only_fallback_reason"] = all(
            {k for k in set(fr[c]) | set(dr[c]) if fr[c].get(k) != dr[c].get(k)} <= {"content_support_llm_fallback_reason", "run_id", "timestamp"} for c in changed)
        out["replay.relabel"] = sorted(list(kv) for kv in Counter(f"{fr[c].get('content_support_llm_fallback_reason')}->{dr[c].get('content_support_llm_fallback_reason')}" for c in changed).items())
        fm = {m["claim_id"]: m for m in load(fresh2 / "alpha_matches.json")["matches"]}
        dm = {m["claim_id"]: m for m in norm(ex / "alpha_matches.json")["matches"]}
        out["replay.alpha_matches_identical"] = all(json.dumps({k: v for k, v in fm[c].items() if k != "run_id"}, sort_keys=True)
                                                    == json.dumps({k: v for k, v in dm[c].items() if k != "run_id"}, sort_keys=True) for c in fm)
        out["replay.raw_selected"] = sum(1 for m in dm.values() if m.get("llm_selected_alpha_id"))
        out["replay.final_matched"] = sum(1 for m in dm.values() if m.get("matched_alpha"))
        fg, dg = load(fresh2 / "structure_graph.json"), norm(ex / "structure_graph.json")

        def no_group_ids(value):
            # evidence-fact group ids hash (run_id, ticker, member claim ids): drop them and order groups by their members
            if isinstance(value, dict):
                return {k: no_group_ids(v) for k, v in value.items() if k not in ("evidence_fact_group_id", "evidence_fact_group_ids")}
            if isinstance(value, list):
                items = [no_group_ids(v) for v in value]
                if items and all(isinstance(v, dict) and "member_claim_ids" in v for v in items):
                    items.sort(key=lambda v: json.dumps(v["member_claim_ids"]))
                return items
            return value

        out["replay.activation_identical"] = json.dumps(no_group_ids((fg.get("activation") or {}).get("alphas")), sort_keys=True) == \
            json.dumps(no_group_ids((dg.get("activation") or {}).get("alphas")), sort_keys=True)
        out["replay.graph_metrics_identical"] = fg.get("graph_metrics") == dg.get("graph_metrics")
        fc, dc = load(fresh2 / "conflicts.json"), norm(ex / "conflicts.json")
        out["replay.admitted_conflicts"] = dc.get("admitted_conflict_count")
        out["replay.conflict_evaluations_identical"] = json.dumps((fc.get("arbitration") or {}).get("candidate_evaluations"), sort_keys=True) == \
            json.dumps((dc.get("arbitration") or {}).get("candidate_evaluations"), sort_keys=True)
        fl_, dl_ = jl(fresh2 / "llm_semantic_calls.jsonl"), [json.loads(x.replace(ex.name, FRESH2)) for x in (ex / "llm_semantic_calls.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        key = lambda r: f"{r['task']}|{json.dumps(r.get('input_payload'), sort_keys=True)}"  # noqa: E731
        out["replay.same_request_set"] = Counter(map(key, fl_)) == Counter(map(key, dl_))
        out["replay.prompt_identity_identical"] = sorted({(r["task"], r["prompt_sha256"]) for r in fl_}) == sorted({(r["task"], r["prompt_sha256"]) for r in dl_})
        # --- never-sent appendix, recomputed from the Fresh ledgers
        for label, d in (("run2", fresh2), ("run1", fresh1)):
            rows = [r for r in jl(d / "llm_semantic_calls.jsonl") if r.get("error_code") == "WEEK2_LLM_INPUT_TOO_LARGE"]
            out[f"not_sent.{label}.count"] = len(rows)
            out[f"not_sent.{label}.mislabelled_malformed"] = sum(1 for r in rows if r.get("fallback_reason") == "malformed_response")
            out[f"not_sent.{label}.with_attempts"] = sum(1 for r in rows if r.get("request_attempts"))
            out[f"not_sent.{label}.min_input_chars"] = min(len(json.dumps(r["input_payload"], ensure_ascii=False, default=str)) for r in rows)
    # --- frozen checks
    q = load(PKG / "06_frozen_checks" / "qqq_formal_acceptance.json")
    out["qqq.formal_status"] = q["formal_status"]
    out["qqq.rules_not_executed"] = len(q["items_sorted"]["contract_rules_not_executed_for_ticker"])
    out["qqq.network_attempts"] = q["network_attempts"]
    a = load(PKG / "06_frozen_checks" / "amd34_reference.json")
    out["amd.list_hashes_equal_round21"] = all(a["list_hashes_equal_round21_record"].values())
    s = load(PKG / "06_frozen_checks" / "sndk_no_main_conflict.json")
    out["sndk.all_agree_no_main_conflict"] = s["all_agree_no_main_conflict"]
    # --- demo
    sc = load(PKG / "07_demo" / "recording_final" / "scenes.json")
    out["demo.scenes_ok"] = sum(1 for x in sc["scenes"] if x["ok"])
    out["demo.scenes"] = len(sc["scenes"])
    out["demo.non_get_blocked"] = sc["safety"]["non_get_api_requests_blocked"]
    out["demo.export_sha256"] = sc["export_sha256"]
    return out


def main() -> int:
    rebuilt = rebuild()
    figures = load(PKG / "report_figures.json")
    report = (PKG / figures["report_file"]).read_text(encoding="utf-8")
    bad = 0
    for fig in figures["figures"]:
        got = rebuilt.get(fig["id"], "<not rebuilt>")
        ok = got == fig["value"] and fig["cited_as"] in report
        bad += not ok
        print("OK  " if ok else "FAIL", fig["id"], "report=", fig["value"], "rebuilt=", got, "" if fig["cited_as"] in report else f"NOT CITED: {fig['cited_as']!r}")
    print(f"figures: {len(figures['figures'])}, failing: {bad}")
    if "--json" in sys.argv:
        print(json.dumps(rebuilt, ensure_ascii=False, default=str))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
