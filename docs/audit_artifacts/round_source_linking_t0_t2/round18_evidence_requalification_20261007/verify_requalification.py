#!/usr/bin/env python3
"""Verifies the re-qualification execution through the real API routes and the real Export ZIP; GET only.

usage: verify_requalification.py <execution_id> [--live http://127.0.0.1:8000]
  default : in-process FastAPI routes (CURRENT code) against the real isolated database and run directory
  --live  : the same reads against the running service process (which may predate this round's code)
"""
import hashlib, io, json, os, sys, urllib.request, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
EXEC = sys.argv[1]
LIVE = sys.argv[sys.argv.index("--live") + 1] if "--live" in sys.argv else None
PARENT, ROOT = "recovery-20261007T053635Z-26d6cd1a", "c904d4cc-dc09-495c-aec5-b056979948e1"
runs = REPO / "outputs" / "runs"
result = {"mode": f"live service {LIVE}" if LIVE else "in-process real routes, real isolated DB (current code)", "method": "GET only", "checks": {}}

if LIVE:
    def get(path):
        with urllib.request.urlopen(LIVE + path, timeout=60) as r:
            return r.status, r.headers.get("content-type"), r.read()
else:
    from dotenv import dotenv_values
    os.environ["COMQUTOR_DATABASE_URL"] = dotenv_values(REPO / ".env")["COMQUTOR_TEST_DATABASE_URL"]
    os.environ["COMQUTOR_OUTPUT_DIR"] = str(runs)
    os.environ.pop("COMQUTOR_REQUIRE_DATABASE_NAME", None)
    from fastapi.testclient import TestClient
    import comqutor_alpha.api.main as main_module
    _client = TestClient(main_module.app)

    def get(path):
        r = _client.get(path)
        return r.status_code, r.headers.get("content-type"), r.content

from comqutor_alpha.classification_recovery import snapshot_directory_hashes


def check(name, ok, **info):
    result["checks"][name] = {"ok": bool(ok), **info}
    print(("PASS " if ok else "FAIL ") + name, json.dumps(info, default=str)[:260], flush=True)


J = lambda path: json.loads(get(path)[2])
disk = runs / EXEC
resp = J(f"/api/research/{EXEC}")
art = json.loads((disk / "evidence_eligibility_requalification.json").read_text())
lineage = resp.get("lineage") or {}
check("response_completed_with_lineage", resp["status"] == "completed" and resp["structure_graph_status"] == "ready" and resp["conflict_status"] == "ready"
      and lineage.get("based_on_run_id") == PARENT and lineage.get("root_research_run_id") == ROOT and lineage.get("execution_type") == "alpha_evidence_requalification",
      status=resp["status"], lineage=lineage)
check("requalification_summary_matches_artifact", lineage.get("requalification_summary") == art["summary"], eligible_after=(lineage.get("requalification_summary") or {}).get("eligibility_reason_counts_after", {}).get("ELIGIBLE"))
check("classification_incompleteness_still_disclosed", resp["alpha_classification_status"] == "incomplete" and resp["alpha_classification_completion"]["call_failure_count"] == 1,
      completion=resp["alpha_classification_completion"], note=resp["summary"][:160])
parent_resp = J(f"/api/research/{PARENT}"); root_resp = J(f"/api/research/{ROOT}")
check("parent_and_original_responses_unchanged", parent_resp["alpha_classification_status"] == "incomplete" and root_resp["alpha_classification_status"] == "incomplete"
      and root_resp["alpha_classification_completion"]["call_failure_count"] == 973 and "lineage" not in root_resp, parent_lineage=parent_resp.get("lineage"))
hist = {r["run_id"]: r for r in J("/api/research?ticker=AMD&limit=50")["items"]}
check("history_lists_all_three", all(hist.get(r, {}).get("status") == "completed" for r in (EXEC, PARENT, ROOT)), statuses={k: hist.get(k, {}).get("status") for k in (EXEC, PARENT, ROOT)})
graph = J(f"/api/research/{EXEC}/graph")
act_art = json.loads((disk / "alpha_activations.json").read_text())["activation_versions"]["v2_verified"]["alphas"]
a301 = next(a for a in act_art if a["alpha_id"] == "A301")
graph_alphas = ((graph.get("graph") or graph).get("activation") or {}).get("alphas") or ((graph.get("graph") or graph).get("activation_versions", {}).get("v2_verified", {}).get("alphas")) or []
a301_api = next((a for a in graph_alphas if a.get("alpha_id") == "A301"), None)
check("graph_route_score_equals_artifact", graph.get("status") == "ok" and a301_api is not None and a301_api["activation_score"] == a301["activation_score"] == 21.3056,
      api_score=(a301_api or {}).get("activation_score"), artifact_score=a301["activation_score"], level=(a301_api or {}).get("activation_level"))
exp = J(f"/api/research/{EXEC}/entity-exposures")
exp_a301 = next((r for r in (exp.get("records") or exp.get("exposures") or []) if r.get("alpha_id") == "A301"), None)
check("exposure_route_equals_artifact", exp_a301 is not None and exp_a301["final_exposure"] == a301["entity_exposure"]["final_exposure"] == 0.5, api=(exp_a301 or {}).get("final_exposure"))
conf = J(f"/api/research/{EXEC}/conflicts")
check("conflicts_route_equals_artifact", conf.get("status") == "ok" and not conf.get("conflicts") and conf.get("main_conflict") is None
      and json.loads((disk / "conflicts.json").read_text())["arbitration"]["rejected_count"] == 8, status=conf.get("status"))
ao = J(f"/api/research/{EXEC}/agent-outputs")
ao_parent = J(f"/api/research/{PARENT}/agent-outputs")
strip = lambda rows: [{k: v for k, v in r.items() if k not in ("run_id",)} for r in rows]
diag_keys = sorted({k for r in ao["structured_agent_outputs"] for k in r if "verified" in k.lower() or "support" in k.lower()})
check("agent_outputs_same_claims_as_parent", ao["count"] == ao_parent["count"] and [r["claim_id"] for r in ao["structured_agent_outputs"]] == [r["claim_id"] for r in ao_parent["structured_agent_outputs"]], count=ao["count"], diagnostic_keys=diag_keys)
listing = J(f"/api/research/{EXEC}/artifacts")
entries = {e["artifact_name"]: e for e in listing["artifacts"]}
check("artifact_listing_complete_and_hashes_match", listing["artifact_completeness"] == "pass" and listing["ticker_consistency"] == "pass"
      and all(hashlib.sha256((disk / n).read_bytes()).hexdigest() == e["sha256"] for n, e in entries.items() if e.get("exists"))
      and entries["requalification_lineage.json"]["status"] == "valid" and entries["evidence_eligibility_requalification.json"]["status"] == "valid", artifacts=len(entries))
code, _, body = get(f"/api/research/{EXEC}/artifacts/requalification_lineage.json")
lin = json.loads(body)
check("lineage_download", code == 200 and lin == json.loads((disk / "requalification_lineage.json").read_text()) and len(lin["claim_identity_map"]) == 975
      and lin["lineage_chain"][1]["run_id"] == PARENT and lin["lineage_chain"][2]["run_id"] == ROOT, chain=[c["run_id"][:24] for c in lin["lineage_chain"]])
code, ctype, body = get(f"/api/research/{EXEC}/export")
zf = zipfile.ZipFile(io.BytesIO(body))
mismatch = [n for n in zf.namelist() if zf.read(n) != (disk / n).read_bytes()]
exported_registry = json.loads(zf.read("source_registry.json"))["sources"]
original_registry = json.loads((runs / ROOT / "source_registry.json").read_text())["sources"]
with_block = [s["source_id"] for s in exported_registry if "availability" in s]
check("export_zip_byte_identical_and_registry_annotated", code == 200 and ctype == "application/zip" and not mismatch and len(with_block) == 3
      and all("availability" not in s for s in original_registry), members=len(zf.namelist()), bytes=len(body), mismatch=mismatch, annotated=with_block)
exported_matches = json.loads(zf.read("alpha_matches.json"))["matches"]
parent_matches = json.loads((runs / PARENT / "alpha_matches.json").read_text())["matches"]
norm = lambda ms: [{k: v for k, v in m.items() if k != "run_id"} for m in ms]
check("classification_reused_verbatim_in_export", norm(exported_matches) == norm(parent_matches) and len(exported_matches) == 975, matches=len(exported_matches))
check("published_at_never_backfilled", all(s["published_at"] is None for s in exported_registry if s["source_id"] in with_block) and
      [s.get("published_at") for s in exported_registry if "availability" not in s] == [s.get("published_at") for s in original_registry if s["source_id"] not in with_block])
check("exported_scores_equal_artifacts", json.loads(zf.read("alpha_activations.json")) == json.loads((disk / "alpha_activations.json").read_text()))

for label, rid in (("original_run", ROOT), ("recovery_run", PARENT)):
    before = json.loads((HERE / f"{'root' if rid == ROOT else 'parent'}_run_hashes_before_requalification.json").read_text())
    check(f"{label}_directory_byte_identical", snapshot_directory_hashes(runs / rid) == before, files=len(before))

(HERE / ("live_service_requalification_verification.json" if LIVE else "api_requalification_verification.json")).write_text(json.dumps(result, indent=2, default=str))
bad = [k for k, v in result["checks"].items() if not v["ok"]]
print("FAILED CHECKS:", bad or "none")
sys.exit(1 if bad else 0)
