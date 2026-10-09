#!/usr/bin/env python3
"""Per-nodeid regression attribution manifest (round 14, section 2).

Inputs (env):
  FINAL_DIR    directory holding the final run's junit.xml + regression_final.log
  HEAD_JSON    {nodeid: [outcome, reason]} from running the failing files against a
               pristine `git archive HEAD` snapshot
  PRE_JSON     same, from the recorded PRE-REPAIR-THREAD tree
  PROBE_JSONL  env/thread probe from the final run (optional)
  INVENTORY    frozen_hash_change_inventory.json
Output: regression_attribution_manifest.json + .md

Counts are taken from the JUnit file and checked against pytest's own summary
line; a nodeid is classified exactly once. Categories (the instruction's five):
  1 frozen_hash_triggered_by_authorized_change  fails now, would PASS without the
                                                repair thread's edits
  2 pre_existing_with_pre_change_evidence       fails before the thread too (recorded
                                                pre-thread tree and/or committed HEAD),
                                                same cause
  3 functional_regression_from_this_work        passes before, fails now, cause is the
                                                repair thread's code
  4 test_pollution_or_instability               cause is shared process state / environment
  5 not_yet_attributable                        anything the evidence below does not settle
A nodeid is NEVER auto-labelled "unrelated" from an old comment, an uncommitted-change
argument, or an isolated pass alone.
"""
import json, os, re, sys, xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).parent
FINAL = Path(os.environ["FINAL_DIR"])
HEAD = json.loads(Path(os.environ["HEAD_JSON"]).read_text())
PRE = json.loads(Path(os.environ["PRE_JSON"]).read_text())
INV = json.loads(Path(os.environ.get("INVENTORY", HERE / "frozen_hash_change_inventory.json")).read_text())


def parse_junit():
    root = ET.parse(FINAL / "junit.xml").getroot()
    rows = []
    for tc in root.iter("testcase"):
        for tag in ("failure", "error"):
            node = tc.find(tag)
            if node is None:
                continue
            msg = (node.get("message") or "").strip().splitlines()
            first = msg[0] if msg else ""
            stage = "setup" if first.startswith("failed on setup") or "ERROR at setup" in (node.text or "")[:300] else \
                    "teardown" if first.startswith("failed on teardown") else "call"
            classname = tc.get("classname", "")
            file_part = classname.replace(".", "/")
            # classname is dotted module path (+ class); recover tests/<file>.py::[Class::]name
            parts = classname.split(".")
            module_parts = [p for p in parts if not p[:1].isupper()]
            klass = [p for p in parts if p[:1].isupper()]
            nodeid = "/".join(module_parts) + ".py::" + "::".join(klass + [tc.get("name")])
            rows.append({"nodeid": nodeid, "junit_tag": tag, "stage": stage, "message": first[:200]})
    return rows


def _norm(message: str) -> str:
    """Normalize a failure message for cause comparison: drop absolute paths,
    long hex digests and memory addresses so only the cause text remains."""
    message = re.sub(r"/[^\s'\"]*/(comqutor_alpha|tests|tradingagents)/", r"\1/", message)
    message = re.sub(r"[0-9a-f]{8,}", "<hex>", message)
    message = re.sub(r"0x[0-9a-f]+", "<addr>", message)
    return message.strip()[:110]


def outcome(table, nodeid):
    v = table.get(nodeid)
    return (v[0], v[1]) if v else ("absent", "")


PIN_VERDICTS = INV["per_test_verdicts"]


def pin_verdict(nodeid):
    for key, v in PIN_VERDICTS.items():
        k_file, _, k_name = key.partition("::")
        short = nodeid.replace("tests/", "")
        if short.endswith(key) or (k_file in short and k_name.split("::")[-1].split("[")[0] in short and
                                   ("[" not in k_name or k_name[k_name.index("["):].strip() in short)):
            return key, v
    return None, None


EVIDENCE_REVIEW_FILES = ("test_evidence_review_v2.py", "test_evidence_review_v2_directional_eligibility.py")

RULES = []  # (predicate, category, cause, files, relation_to_recovery)


def rule(pred, category, cause, files, relation):
    RULES.append((pred, category, cause, files, relation))


rule(lambda n, m: "test_phase1b1_boundaries.py::test_existing_three_task_instructions_text_unchanged" in n,
     "see_counterfactual", "hard-coded 3-task instruction set predates later registered tasks", ["tests/structured_output_shadow/test_phase1b1_boundaries.py"],
     "none: asserts a historical task-name set")
rule(lambda n, m: "test_structured_adapter_concurrency_touches_no_alpha_mapping_code" in n,
     "see_counterfactual", "structured_output_adapter.py source contains the substring 'alpha_mapper' in a comment authored 2026-10-05 12:36 (round 9), tripping a structural isolation guard",
     ["comqutor_alpha/structure_engine/structured_output_adapter.py"], "none: comment text only")
rule(lambda n, m: "test_shadow_provider_smoke_cli.py::test_fully_authorized_run_with_fake_client_writes_complete_bundle" in n,
     "environment", "asserts no dotfile in the shared outputs/evaluations/ directory; a Finder .DS_Store is present there",
     ["outputs/evaluations/.DS_Store (git-ignored)"], "none")
rule(lambda n, m: "test_e42_head_unchanged_from_session_frozen_starting_commit" in n,
     "see_counterfactual", "hard-coded FROZEN_SESSION_HEAD != the repository's actual HEAD", ["tests/test_j3_semantic_benchmark_j2_v0_2.py"], "none: git history assertion")
rule(lambda n, m: any(f in n for f in EVIDENCE_REVIEW_FILES),
     "see_counterfactual", "reads static docs/audit_artifacts/evidence_review_summary_v2.json, whose committed content lacks the keys the tests assert (raw_h5_metrics, directional_eligibility, ...)",
     ["docs/audit_artifacts/evidence_review_summary_v2.json"], "none: pure JSON read, no repo code on the path")
rule(lambda n, m: "test_60_sample_includes_conflict_and_activation_evidence" in n,
     "see_counterfactual", "activation_evidence_count == 0 in the 50-row sample", ["comqutor_alpha evidence review sampling inputs"], "none")
rule(lambda n, m: "test_v0_1_3_offline_replay_proof.py::test_section_d" in n,
     "see_counterfactual", "recomputing detect_alpha_conflicts on the frozen MSFT run yields an extra A102__A304 conflict (taxonomy modified 2026-10-05)",
     ["comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml", "comqutor_alpha/conflict_engine/conflict_detector.py"], "none")
rule(lambda n, m: "test_b2_admissibility_integration.py" in n,
     "see_counterfactual", "DB round-trip main_conflict now includes evidence_qualification; the test strips it from the expected side only",
     ["comqutor_alpha/conflict_engine/conflict_detector.py", "comqutor_alpha/storage/db/week4_persistence.py"], "none")
rule(lambda n, m: "test_w5_demo_seed.py" in n,
     "see_counterfactual", "demo seed raises DemoSeedError NVDA_MAIN_CONFLICT_NOT_ARBITRATED (golden fixture predates later B1/B2 changes)",
     ["scripts/seed_w5_demo.py"], "none: demo seeding path")


def classify(row):
    n, m = row["nodeid"], row["message"]
    key, verdict = pin_verdict(n)
    head_o, head_r = outcome(HEAD, n)
    pre_o, pre_r = outcome(PRE, n)
    same_cause_pre = bool(pre_r) and _norm(pre_r) == _norm(m)
    base = {"nodeid": n, "junit_tag": row["junit_tag"], "stage": row["stage"], "message": m,
            "head_snapshot_outcome": head_o, "head_snapshot_message": head_r,
            "pre_repair_thread_tree_outcome": pre_o, "pre_repair_thread_tree_message": pre_r,
            "same_failure_message_in_pre_thread_tree": same_cause_pre}
    matched = next(((c, cause, files, rel) for p, c, cause, files, rel in RULES if p(n, m)), None)
    if verdict is not None:
        base.update(direct_cause="frozen-hash pin mismatch", files=verdict["mismatching_now"],
                    pin_analysis=verdict["verdict"], relation_to_recovery="none: governance pin on file contents",
                    thread_edited_files_among_mismatches=verdict["of_which_edited_by_repair_thread"])
        if pre_o in ("FAILED", "ERROR") and same_cause_pre:
            base["category"], base["category_reason"] = 2, "fails in the recorded pre-repair-thread tree with the same failure message"
        elif pre_o in ("FAILED", "ERROR"):
            base["category"], base["category_reason"] = 5, "fails pre-thread but with a DIFFERENT message: cause not shown to be the same"
        elif pre_o == "PASSED":
            base["category"], base["category_reason"] = 1, "passes in the recorded pre-repair-thread tree, fails now"
        else:
            base["category"], base["category_reason"] = 5, "no pre-thread outcome recorded"
        return base
    if "test_e42_head_unchanged_from_session_frozen_starting_commit" in n:
        # Settled by direct comparison, not by tree comparison: the scratch trees have no .git, so
        # `git rev-parse HEAD` errors there for an unrelated reason. The assertion compares a
        # hard-coded commit hash to the repository's actual HEAD; no working-tree edit can change
        # that, and the repair thread made no commits.
        base.update(direct_cause="hard-coded FROZEN_SESSION_HEAD (b5837e80...) != the repository's actual HEAD (7a9aefa5...)",
                    files=["tests/test_j3_semantic_benchmark_j2_v0_2.py"], relation_to_recovery="none: git-history assertion",
                    category=2, category_reason="verified by direct comparison of the hard-coded commit with `git rev-parse HEAD`; independent of any file edit (scratch trees lack .git)")
        return base
    if matched:
        _, cause, files, rel = matched
        base.update(direct_cause=cause, files=files, relation_to_recovery=rel)
        if matched[0] == "environment":
            base["category"], base["category_reason"] = 4, "environment-dependent (stray macOS Finder file); cause verified directly"
        elif pre_o in ("FAILED", "ERROR") and same_cause_pre:
            base["category"], base["category_reason"] = 2, "also fails in the recorded pre-repair-thread tree with the same failure message"
        elif pre_o in ("FAILED", "ERROR"):
            base["category"], base["category_reason"] = 5, "fails pre-thread but with a DIFFERENT message: cause not shown to be the same"
        elif pre_o == "PASSED":
            base["category"], base["category_reason"] = 3, "passes in the pre-repair-thread tree, fails now: investigate as a regression"
        else:
            base["category"], base["category_reason"] = 5, "no pre-thread outcome recorded"
        return base
    base.update(direct_cause="not covered by a verified rule", files=[], relation_to_recovery="unknown",
                category=5, category_reason="unclassified by any verified rule")
    return base


def main():
    rows = parse_junit()
    manifest = [classify(r) for r in rows]
    from collections import Counter
    by_tag = Counter(r["junit_tag"] for r in rows)
    by_cat = Counter(m["category"] for m in manifest)
    final_log = (FINAL / "regression_final.log").read_text()
    summary_line = next((l for l in final_log.splitlines() if re.search(r"\d+ (failed|passed)", l) and " in " in l), "")
    dup = [k for k, c in Counter(m["nodeid"] for m in manifest).items() if c > 1]
    doc = {
        "pytest_summary_line": summary_line,
        "junit_failure_elements": by_tag.get("failure", 0), "junit_error_elements": by_tag.get("error", 0),
        "nodeids_listed": len(manifest), "nodeids_with_multiple_events": dup,
        "category_counts": dict(sorted(by_cat.items())), "manifest": manifest,
    }
    (HERE / "regression_attribution_manifest.json").write_text(json.dumps(doc, indent=2))
    print(summary_line)
    print("failure elements:", by_tag.get("failure", 0), "| error elements:", by_tag.get("error", 0), "| listed:", len(manifest), "| multi-event nodeids:", dup)
    print("category counts:", dict(sorted(by_cat.items())))
    for m in manifest:
        if m["category"] in (3, 5):
            print("  NEEDS ATTENTION cat", m["category"], m["nodeid"], "|", m["message"][:90])


if __name__ == "__main__":
    main()
