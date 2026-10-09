#!/usr/bin/env python3
"""Round 19 -- verifies the RESTARTED live service (current code) against the execution's own files. GET requests only: no research, no POST, no review route.

usage: verify_live_service_round19.py <execution_id> [--base http://127.0.0.1:8000]
Writes live_service_verification_round19.json next to this script (never into the Round 18 folder).

Checks (each PASS/FAIL with its evidence):
  lineage + new artifacts readable; read-time vs stored eligibility; scores / status / Conflict equal to the derived artifacts; Export ZIP equals the files;
  original / recovery / direction / re-qualification run directories byte-identical to the hashes taken before this round.
"""
import collections, hashlib, io, json, sys, urllib.request, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
EXEC = sys.argv[1]
BASE = sys.argv[sys.argv.index("--base") + 1] if "--base" in sys.argv else "http://127.0.0.1:8000"
PARENT, ROOT = "recovery-20261007T053635Z-26d6cd1a", "c904d4cc-dc09-495c-aec5-b056979948e1"
runs = REPO / "outputs" / "runs"
disk = runs / EXEC
result = {"mode": f"live service {BASE} (restarted this round)", "method": "GET only", "checks": {}}

from comqutor_alpha.classification_recovery import snapshot_directory_hashes


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=120) as r:
        return r.status, r.headers.get("content-type"), r.read()


def J(path):
    return json.loads(get(path)[2])


def check(name, ok, **info):
    result["checks"][name] = {"ok": bool(ok), **info}
    print(("PASS " if ok else "FAIL ") + name, json.dumps(info, default=str, ensure_ascii=False)[:300], flush=True)


ready = J("/ready")
check("service_ready_with_isolated_database", ready["status"] == "ready" and ready["database"] == "ready", ready=ready)

resp = J(f"/api/research/{EXEC}")
art = json.loads((disk / "evidence_eligibility_requalification.json").read_text())
lineage = resp.get("lineage") or {}
check("lineage_block_present_and_correct", resp["status"] == "completed" and lineage.get("based_on_run_id") == PARENT and lineage.get("root_research_run_id") == ROOT
      and lineage.get("execution_type") == "alpha_evidence_requalification" and lineage.get("lineage_artifact") == "requalification_lineage.json", lineage={k: lineage.get(k) for k in ("based_on_run_id", "root_research_run_id", "execution_type", "lineage_artifact")})
check("requalification_summary_equals_artifact", lineage.get("requalification_summary") == art["summary"], eligible_after=(lineage.get("requalification_summary") or {}).get("eligibility_reason_counts_after", {}).get("ELIGIBLE"))
check("classification_incompleteness_still_disclosed", resp["alpha_classification_status"] == "incomplete" and resp["alpha_classification_completion"]["call_failure_count"] == 1, completion=resp["alpha_classification_completion"])
parent_resp, root_resp = J(f"/api/research/{PARENT}"), J(f"/api/research/{ROOT}")
check("parent_has_recovery_lineage_and_original_has_none", (parent_resp.get("lineage") or {}).get("execution_type") and "lineage" not in root_resp and root_resp["alpha_classification_completion"]["call_failure_count"] == 973,
      parent_lineage_type=(parent_resp.get("lineage") or {}).get("execution_type"))
hist = {r["run_id"]: r for r in J("/api/research?ticker=AMD&limit=50")["items"]}
check("history_lists_all_three_runs", all(hist.get(r, {}).get("status") == "completed" for r in (EXEC, PARENT, ROOT)), statuses={k[:28]: hist.get(k, {}).get("status") for k in (EXEC, PARENT, ROOT)})

# ---- read-time vs stored eligibility (the Round 18 contradiction: 6 of the 500 API-visible claims)
ao = J(f"/api/research/{EXEC}/agent-outputs")
claims = {c["claim_id"]: c for c in json.loads((HERE / "claims_975_list.json").read_text())["claims"]}
api_codes = {r["claim_id"]: (r.get("verified_support_diagnostic") or {}).get("detail_code") for r in ao["structured_agent_outputs"]}
mismatch = {cid: (code, claims[cid]["eligibility"]["code"]) for cid, code in api_codes.items() if code != claims[cid]["eligibility"]["code"] and not (code in (None, "ELIGIBLE") and claims[cid]["eligibility"]["code"] == "ELIGIBLE")}
stored24 = {row["claim_id"]: row.get("eligibility_after") or row.get("reason_after") for row in art["claims_requalified"]}
visible24 = {c: api_codes[c] for c in stored24 if c in api_codes}
analytical_total = sum(1 for c in claims.values() if c["quality"]["claim_quality"] == "analytical")
check("read_time_eligibility_equals_stored", not mismatch and ao["count"] == analytical_total, api_visible=ao["count"], analytical_claims_in_run=analytical_total, mismatches=len(mismatch), sample=list(mismatch.items())[:3],
      requalified_claims_visible_via_api=len(visible24), requalified_visible_api_codes=dict(collections.Counter(visible24.values())),
      note="the route returns the product-findings view = the analytical claims only; the other claims are in the artifacts and the Export")
check("api_claim_set_equals_parent", [r["claim_id"] for r in ao["structured_agent_outputs"]] == [r["claim_id"] for r in J(f"/api/research/{PARENT}/agent-outputs")["structured_agent_outputs"]])

# ---- scores / status / Conflict equal the derived artifacts
graph = J(f"/api/research/{EXEC}/graph")
act_art = json.loads((disk / "alpha_activations.json").read_text())["activation_versions"]["v2_verified"]["alphas"]
g = graph.get("graph") or graph
graph_alphas = (g.get("activation") or {}).get("alphas") or g.get("activation_versions", {}).get("v2_verified", {}).get("alphas") or []
api_by = {a["alpha_id"]: a for a in graph_alphas}
diffs = {a["alpha_id"]: (api_by.get(a["alpha_id"], {}).get("activation_score"), a["activation_score"]) for a in act_art if api_by.get(a["alpha_id"], {}).get("activation_score") != a["activation_score"]}
levels = {a["alpha_id"]: (api_by.get(a["alpha_id"], {}).get("activation_level"), a["activation_level"]) for a in act_art if api_by.get(a["alpha_id"], {}).get("activation_level") != a["activation_level"]}
check("graph_scores_and_levels_equal_artifact_for_all_10_alphas", graph.get("status") == "ok" and len(api_by) == 10 and not diffs and not levels, a301=api_by.get("A301", {}).get("activation_score"), level=api_by.get("A301", {}).get("activation_level"), score_diffs=diffs, level_diffs=levels)
exp = J(f"/api/research/{EXEC}/entity-exposures")
exp_rows = {r["alpha_id"]: r for r in (exp.get("records") or exp.get("exposures") or [])}
art_exp = {a["alpha_id"]: a["entity_exposure"]["final_exposure"] for a in act_art if a.get("entity_exposure")}
check("exposures_equal_artifact", all(exp_rows.get(k, {}).get("final_exposure") == v for k, v in art_exp.items()) and len(art_exp) >= 7, compared=len(art_exp), a301=exp_rows.get("A301", {}).get("final_exposure"))
conf = J(f"/api/research/{EXEC}/conflicts")
conf_art = json.loads((disk / "conflicts.json").read_text())
check("conflicts_equal_artifact", conf.get("status") == "ok" and not conf.get("conflicts") and conf.get("main_conflict") is None and conf_art["arbitration"]["rejected_count"] == 8 and conf_art["admitted_conflict_count"] == 0, admitted=conf_art["admitted_conflict_count"], rejected=conf_art["arbitration"]["rejected_count"])

# ---- artifacts, lineage download, Export
listing = J(f"/api/research/{EXEC}/artifacts")
entries = {e["artifact_name"]: e for e in listing["artifacts"]}
check("artifact_listing_complete_and_hashes_match", listing["artifact_completeness"] == "pass" and all(hashlib.sha256((disk / n).read_bytes()).hexdigest() == e["sha256"] for n, e in entries.items() if e.get("exists"))
      and entries["requalification_lineage.json"]["status"] == "valid" and entries["evidence_eligibility_requalification.json"]["status"] == "valid", artifacts=len(entries))
code, _, body = get(f"/api/research/{EXEC}/artifacts/requalification_lineage.json")
lin = json.loads(body)
check("new_artifacts_readable_lineage_download", code == 200 and lin == json.loads((disk / "requalification_lineage.json").read_text()) and len(lin["claim_identity_map"]) == 975 and lin["lineage_chain"][1]["run_id"] == PARENT and lin["lineage_chain"][2]["run_id"] == ROOT)
code, _, body = get(f"/api/research/{EXEC}/artifacts/evidence_eligibility_requalification.json")
check("new_artifacts_readable_eligibility_download", code == 200 and json.loads(body) == art, claims_requalified=len(art["claims_requalified"]))
code, ctype, body = get(f"/api/research/{EXEC}/export")
zf = zipfile.ZipFile(io.BytesIO(body))
bad = [n for n in zf.namelist() if zf.read(n) != (disk / n).read_bytes()]
exported_registry = json.loads(zf.read("source_registry.json"))["sources"]
original_registry = json.loads((runs / ROOT / "source_registry.json").read_text())["sources"]
annotated = [s["source_id"] for s in exported_registry if "availability" in s]
check("export_zip_byte_identical_to_execution_files", code == 200 and ctype == "application/zip" and not bad and len(annotated) == 3 and all("availability" not in s for s in original_registry), members=len(zf.namelist()), bytes=len(body), mismatching_members=bad, annotated_sources=annotated)
check("export_scores_equal_artifacts", json.loads(zf.read("alpha_activations.json")) == json.loads((disk / "alpha_activations.json").read_text()) and json.loads(zf.read("conflicts.json")) == conf_art)
check("published_at_never_backfilled", all(s["published_at"] is None for s in exported_registry if s["source_id"] in annotated))

# ---- history untouched (hashes taken before this round started)
for label, rid, fname in (("original_run", ROOT, "original"), ("recovery_run", PARENT, "recovery"), ("requalification_run", EXEC, "requalification")):
    before = json.loads((HERE / f"{fname}_run_hashes_before_round19.json").read_text())
    now = snapshot_directory_hashes(runs / rid)
    check(f"{label}_directory_byte_identical_to_before_round19", now == before, files=len(before), changed=sorted(k for k in set(now) | set(before) if now.get(k) != before.get(k)))
before = json.loads((HERE / "direction_run_hashes_before_round19.json").read_text())
check("direction_execution_directory_byte_identical_to_before_round19", snapshot_directory_hashes(runs / "direction-20261007T065826Z-d311b8e2") == before, files=len(before))

(HERE / "live_service_verification_round19.json").write_text(json.dumps(result, indent=2, default=str, ensure_ascii=False))
bad_checks = [k for k, v in result["checks"].items() if not v["ok"]]
print("FAILED CHECKS:", bad_checks or "none")
sys.exit(1 if bad_checks else 0)
