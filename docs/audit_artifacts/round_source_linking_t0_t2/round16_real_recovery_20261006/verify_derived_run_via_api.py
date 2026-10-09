#!/usr/bin/env python3
"""Read-only verification of the REAL derived recovery run through the real API routes.

The routes run in-process (FastAPI TestClient, current code) against the real isolated test database and the real
outputs/runs directory -- GET requests only, no lifespan (no startup reconciliation, no job manager), no write.
This is NOT the always-on backend process: that process was stopped for a refresh and its relaunch was refused by
the permission system, so it is reported separately.

Checks: derived run response / status / History / agent-outputs / artifacts / lineage download / Export ZIP
(every member byte-compared with the file on disk), the original run still `incomplete`, and the original run
directory hash-identical to the snapshot taken before the real recovery.
"""
import hashlib
import io
import json
import os
import sys
import zipfile
from pathlib import Path

from dotenv import dotenv_values

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
EXECUTION_ID = sys.argv[1]
ORIGINAL_ID = "c904d4cc-dc09-495c-aec5-b056979948e1"

os.environ["COMQUTOR_DATABASE_URL"] = dotenv_values(REPO / ".env")["COMQUTOR_TEST_DATABASE_URL"]
os.environ["COMQUTOR_OUTPUT_DIR"] = str(REPO / "outputs" / "runs")
os.environ.pop("COMQUTOR_REQUIRE_DATABASE_NAME", None)

from fastapi.testclient import TestClient

import comqutor_alpha.api.main as main_module
from comqutor_alpha.classification_recovery import snapshot_directory_hashes

client = TestClient(main_module.app)
runs = REPO / "outputs" / "runs"
result = {"mode": "in-process real routes, real isolated DB, read-only GET", "checks": {}}


def check(name, ok, **info):
    result["checks"][name] = {"ok": bool(ok), **info}
    print(("PASS " if ok else "FAIL ") + name, json.dumps(info, default=str)[:300], flush=True)


derived = client.get(f"/api/research/{EXECUTION_ID}").json()
original = client.get(f"/api/research/{ORIGINAL_ID}").json()
dc, oc = derived["alpha_classification_completion"], original["alpha_classification_completion"]
check("derived_response", derived["status"] == "completed" and derived["lineage"]["based_on_run_id"] == ORIGINAL_ID,
      status=derived["status"], lineage=derived["lineage"], graph=derived["structure_graph_status"], conflict=derived["conflict_status"],
      classification_status=derived["alpha_classification_status"], completion=dc,
      dominant_alphas=len(derived["dominant_alphas"]), main_conflict=bool(derived["main_conflict"]), summary=derived["summary"])
check("derived_discloses_incomplete_classification", dc["complete"] is False and dc["call_failure_count"] == 1 and derived["alpha_classification_status"] == "incomplete", completion=dc)
check("original_run_still_incomplete", original["alpha_classification_status"] == "incomplete" and oc["call_failure_count"] == 973 and "lineage" not in original,
      completion=oc, status=original["status"])
status = client.get(f"/api/research/{EXECUTION_ID}/status").json()
check("derived_status_route", status["status"] == "completed", status=status.get("status"), execution_mode=status.get("request_execution_mode") or status.get("execution_mode"))
history = {row["run_id"]: row for row in client.get("/api/research?ticker=AMD&limit=50").json()["items"]}
check("history_lists_both_runs", history.get(EXECUTION_ID, {}).get("status") == "completed" and ORIGINAL_ID in history,
      derived=history.get(EXECUTION_ID, {}).get("status"), original=history.get(ORIGINAL_ID, {}).get("status"))
ao_d = client.get(f"/api/research/{EXECUTION_ID}/agent-outputs").json()
ao_o = client.get(f"/api/research/{ORIGINAL_ID}/agent-outputs").json()
strip = lambda rows: [{k: v for k, v in r.items() if k != "run_id"} for r in rows]
check("agent_outputs_equal_apart_from_run_id", ao_d["count"] == ao_o["count"] > 0 and strip(ao_d["structured_agent_outputs"]) == strip(ao_o["structured_agent_outputs"]),
      derived_count=ao_d["count"], original_count=ao_o["count"])
listing = client.get(f"/api/research/{EXECUTION_ID}/artifacts").json()
entries = {e["artifact_name"]: e for e in listing["artifacts"]}
check("artifact_listing", listing["artifact_completeness"] == "pass" and listing["ticker_consistency"] == "pass"
      and entries["recovery_lineage.json"]["status"] == "valid" and entries["evidence_stance_followup_manifest.json"]["status"] == "valid",
      artifact_completeness=listing["artifact_completeness"], ticker_consistency=listing["ticker_consistency"], artifacts=len(entries))
manifest_ok = all(
    hashlib.sha256((runs / EXECUTION_ID / name).read_bytes()).hexdigest() == e["sha256"] for name, e in entries.items() if e.get("exists"))
check("manifest_hashes_match_files_on_disk", manifest_ok, entries=len(entries))
lineage_dl = client.get(f"/api/research/{EXECUTION_ID}/artifacts/recovery_lineage.json")
lineage_disk = json.loads((runs / EXECUTION_ID / "recovery_lineage.json").read_text())
check("lineage_download", lineage_dl.status_code == 200 and lineage_dl.json() == lineage_disk and len(lineage_disk["claim_identity_map"]) == 975,
      status_code=lineage_dl.status_code, counts=lineage_disk["classification_source_counts"], amendments=len(lineage_disk.get("amendments", [])))
export = client.get(f"/api/research/{EXECUTION_ID}/export")
archive = zipfile.ZipFile(io.BytesIO(export.content))
members = archive.namelist()
mismatch = [n for n in members if archive.read(n) != (runs / EXECUTION_ID / n).read_bytes()]
exported_matches = json.loads(archive.read("alpha_matches.json"))["matches"]
check("export_zip", export.status_code == 200 and not mismatch and len(exported_matches) == 975
      and {m["run_id"] for m in exported_matches} == {EXECUTION_ID} and "recovery_lineage.json" in members,
      status_code=export.status_code, members=len(members), bytes_mismatch=mismatch, zip_bytes=len(export.content),
      exported_matches=len(exported_matches), failed_in_export=sum(1 for m in exported_matches if m.get("alpha_match_method") != "llm"))
result["export_member_sha256"] = {n: hashlib.sha256(archive.read(n)).hexdigest() for n in members}

before = json.loads((HERE / "original_run_hashes_before_real_recovery.json").read_text())
after = snapshot_directory_hashes(runs / ORIGINAL_ID)
check("original_run_directory_byte_identical", before == after, files=len(after), changed=sorted(k for k in before if before.get(k) != after.get(k)),
      added=sorted(set(after) - set(before)), removed=sorted(set(before) - set(after)))

(HERE / "api_verification_result.json").write_text(json.dumps(result, indent=2, default=str))
failed = [name for name, c in result["checks"].items() if not c["ok"]]
print("FAILED CHECKS:", failed or "none")
sys.exit(1 if failed else 0)
