#!/usr/bin/env python3
"""Round 21 item 4 -- verify (READ-ONLY) that John's original AMD 34-item acceptance list is intact and still re-derivable.

Nothing here writes to ``outputs/`` or to the Round 19 files; the only file written is this directory's
``amd34_list_integrity_result.json``.  Zero Provider / search / data-fetch calls (the production functions used are pure).

Checks
  H  the saved Round 19 json/csv still have the sha256 recorded in the Round 19 / Round 21 evidence
  R  the 34 evidence ids / sides / target alphas / agents / texts are re-derived from the HISTORICAL run's own admitted conflict
  M  the four linking mechanisms and the production eligibility function, re-run on that run's frozen material, give the saved result
  S  the three facts stay separate: historical adoption (true) / current eligibility (false + reason) / independent execution (未执行)
  U  materials that were never saved are labelled unverified, never "supported"; nothing is dropped, nothing is backfilled
  N  the newer AMD runs are not referenced anywhere in the list; no execution was ever derived from the historical run
  P  the historical run directory is byte-identical before and after this verification
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))

from comqutor_alpha.classification_recovery import snapshot_directory_hashes  # noqa: E402
from comqutor_alpha.source_provenance import (  # noqa: E402
    compute_verified_support_eligibility,
    extract_all_source_markers_from_text,
    match_evidence_to_source_candidates,
    match_evidence_to_source_candidates_normalized,
    resolve_external_source_for_claim,
    validate_source_reference,
)

R19 = REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round19_consumption_and_acceptance_20261007"
SAVED_JSON, SAVED_CSV = R19 / "amd_34_fixed_acceptance_list.json", R19 / "amd_34_fixed_acceptance_list.csv"
EXPECTED_SHA256 = {"json": "c44dbe344686d168df889ba59ac40ff92e3f18fbb96307c830ba74b2df685708",
                   "csv": "fb8d6d9a1f15a543202950c1b8aa57ea98e5d168dc3556c2ef52b20326fa7ef3"}
RUN_ID = "d5b60b8a-66b8-44c1-9f55-ee345e58c48d"
RUN = REPO / "outputs" / "runs" / RUN_ID
NEWER_AMD_MARKERS = ("c904d4cc", "recovery-2026", "requal-2026", "direction-2026", "dependency-2026")
jload = lambda p: json.loads(Path(p).read_text())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

checks: dict[str, dict] = {}


def record(name: str, ok: bool, **detail):
    checks[name] = {"ok": bool(ok), **detail}


before_hashes = snapshot_directory_hashes(RUN)

# --- H
saved = jload(SAVED_JSON)
items = saved["items"]
record("H_saved_files_unchanged", sha(SAVED_JSON) == EXPECTED_SHA256["json"] and sha(SAVED_CSV) == EXPECTED_SHA256["csv"],
       json_sha256=sha(SAVED_JSON), csv_sha256=sha(SAVED_CSV), expected=EXPECTED_SHA256)

# --- R : re-derive the 34 from the historical run's own admitted conflict
conflicts, registry, metadata, structured = (jload(RUN / n) for n in ("conflicts.json", "source_registry.json", "metadata.json", "structured_agent_outputs.json"))
sources, cutoff = registry["sources"], metadata["analysis_date"]
records = {r["claim_id"]: r for r in structured["records"]}
main = conflicts["main_conflict"]
rederived = []
for key, side in (("bull_evidence", "bull"), ("bear_evidence", "bear"), ("counter_evidence", "counter")):
    for entry in main["evidence_ui"].get(key) or []:
        rederived.append({"evidence_id": entry["representative_claim_id"], "side": side, "target_alpha_id": entry.get("target_alpha_id"),
                          "producing_agent": (entry.get("agents") or ["unknown"])[0],
                          "evidence_text": (records.get(entry["representative_claim_id"]) or {}).get("claim") or entry.get("evidence_text") or ""})
saved_view = [{k: i[k] for k in ("evidence_id", "side", "target_alpha_id", "producing_agent", "evidence_text")} for i in items]
record("R_34_rederived_from_historical_conflict", rederived == saved_view and len(items) == 34 and main["admissibility"]["status"] == "admitted",
       rederived_count=len(rederived), saved_count=len(items), conflict_id=main["conflict_id"], conflict_status=main["admissibility"]["status"],
       by_side=dict(Counter(i["side"] for i in items)), ordinals_contiguous=[i["n"] for i in items] == list(range(1, 35)))

# --- M : the mechanisms + eligibility, re-run on frozen material
mismatches = []
for item in items:
    text = item["evidence_text"]
    legacy_source, legacy_status = resolve_external_source_for_claim(claim=None, evidence=text, sources=sources)
    old_candidates = match_evidence_to_source_candidates(text, None, sources)
    markers = extract_all_source_markers_from_text(text, sources)
    normalized = match_evidence_to_source_candidates_normalized(text, None, sources, instrument="AMD")
    final, method = None, "NONE"
    if markers:
        v = validate_source_reference(markers[0], sources=sources, evidence_cutoff=cutoff)
        if v["source_link_status"] == "VALID":
            final, method = v, "ORIGINAL_AGENT_MARKER_CITED"
    if final is None:
        for cand, name in [(c, "CONTENT_MATCH_CANDIDATE") for c in old_candidates] + [(c, "NORMALIZED_FIELD_MATCH_CANDIDATE") for c in normalized["candidates"]]:
            v = validate_source_reference(cand, sources=sources, evidence_cutoff=cutoff)
            if v["source_link_status"] == "VALID":
                final, method = v, name
                break
    if final is None:
        final = validate_source_reference(None, sources=sources, evidence_cutoff=cutoff)
    elig = compute_verified_support_eligibility(records.get(item["evidence_id"]) or {}, sources)
    got = {"legacy": legacy_status, "link": final["source_link_status"], "method": method, "source": final.get("linked_source_id"),
           "eligible": bool(elig["eligible"]), "reason": elig["reason_code"]}
    want = {"legacy": item["mechanism_recomputed"]["legacy_title_match_status"], "link": item["post_fix_link_status"], "method": item["post_fix_link_method"],
            "source": item["current_source_id"], "eligible": item["eligible_under_current_rules"]["eligible"], "reason": item["eligible_under_current_rules"]["reason_code"]}
    if got != want:
        mismatches.append({"n": item["n"], "got": got, "want": want})
record("M_mechanisms_rerun_equal_saved", not mismatches, mismatches=mismatches,
       link_status=dict(Counter(i["post_fix_link_status"] for i in items)), eligibility=dict(Counter(i["eligible_under_current_rules"]["reason_code"] for i in items)))

# --- S : three separate facts
three_ok = all(i["historical_run_actually_adopted"]["adopted"] is True and i["eligible_under_current_rules"]["eligible"] is False
               and i["eligible_under_current_rules"]["reason_code"] and i["adopted_in_independent_execution"] == "未执行" for i in items)
record("S_three_facts_separate", three_ok and len({json.dumps([i["historical_run_actually_adopted"]["adopted"], i["eligible_under_current_rules"]["eligible"]]) for i in items}) == 1,
       adopted_in_historical_run=Counter(str(i["historical_run_actually_adopted"]["adopted"]) for i in items),
       eligible_under_current_rules=Counter(str(i["eligible_under_current_rules"]["eligible"]) for i in items),
       adopted_in_independent_execution=Counter(i["adopted_in_independent_execution"] for i in items),
       reading="adopted=true while eligible=false proves the fields are not derived from each other; 'eligible' is a recomputation, never an adoption")

# --- U : unverified is honest; nothing dropped
with open(SAVED_CSV, encoding="utf-8-sig", newline="") as fh:
    csv_rows = list(csv.DictReader(fh))
unverified_ok = all(i["post_fix_link_status"] == "NOT_PROVIDED" and i["content_support_review_result"] == "NOT_APPLICABLE" and i["current_source_id"] is None
                    and i["current_content_location"] is None and i["failure_reason_code"] and i["failure_reason_category"] in "BCD" for i in items)
record("U_unverified_stays_unverified_nothing_dropped", unverified_ok and len(csv_rows) == 34 and [r["原 evidence_id"] for r in csv_rows] == [i["evidence_id"] for i in items]
       and all(r["独立重算是否采用"] == "未执行" and r["按当前规则是否具备资格"] == "否" and r["历史运行是否实际采用"].startswith("是：") for r in csv_rows),
       csv_rows=len(csv_rows), john_categories=dict(Counter(i["failure_reason_category"] for i in items)),
       registry_material=saved["summary"]["registry_facts_reconfirmed_now"],
       registry_material_recomputed={"sources": len(sources), "with_excerpt": sum(1 for s in sources if s.get("excerpt")), "with_data_snapshot": sum(1 for s in sources if s.get("data_snapshot"))})

# --- N : no backfill from the newer AMD runs; no execution derived from the historical run
blob = SAVED_JSON.read_text() + SAVED_CSV.read_text(encoding="utf-8-sig")
referenced = [m for m in NEWER_AMD_MARKERS if m in blob]
derived_from_historical, scanned_runs, scanned_files = [], 0, 0
for run_dir in sorted((REPO / "outputs" / "runs").iterdir()):
    if run_dir.name == RUN_ID or not run_dir.is_dir():
        continue
    scanned_runs += 1
    # every top-level metadata / *lineage* / checkpoint / manifest json of every OTHER run directory (the derived-run entries all write one of these)
    for f in sorted({*run_dir.glob("metadata.json"), *run_dir.glob("*lineage*.json"), *run_dir.glob("checkpoint*.json"), *run_dir.glob("*manifest*.json")}):
        scanned_files += 1
        if RUN_ID in f.read_text(errors="replace"):
            derived_from_historical.append(f"{run_dir.name}/{f.name}")
record("N_no_backfill_and_no_independent_execution", not referenced and not derived_from_historical and scanned_runs >= 80,
       newer_amd_run_markers_found_in_list=referenced, other_runs_scanned=scanned_runs, files_scanned=scanned_files,
       other_runs_whose_metadata_lineage_checkpoint_or_manifest_mentions_the_historical_run=derived_from_historical)

# --- P : the historical run is untouched
after_hashes = snapshot_directory_hashes(RUN)
record("P_historical_run_read_only", before_hashes == after_hashes, files_hashed=len(before_hashes))

result = {"verified_at_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds"),
          "list": {"path": str(SAVED_JSON.relative_to(REPO)), "csv": str(SAVED_CSV.relative_to(REPO)), "schema_version": saved["schema_version"], "item_count": len(items)},
          "historical_run": {"run_id": RUN_ID, "evidence_cutoff": cutoff, "conflict": main["conflict_id"]},
          "zero_calls": "no Provider, search or data-fetch is possible in this script: only pure production functions on files read from disk",
          "all_checks_pass": all(c["ok"] for c in checks.values()), "checks": checks}
(HERE / "amd34_list_integrity_result.json").write_text(json.dumps(result, indent=1, ensure_ascii=False, default=str))
print(json.dumps({k: v["ok"] for k, v in checks.items()}, indent=1), "\nall_checks_pass:", result["all_checks_pass"])
sys.exit(0 if result["all_checks_pass"] else 2)
