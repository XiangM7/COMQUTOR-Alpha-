#!/usr/bin/env python3
"""Reads the saved classification-recovery run THROUGH THE REAL RUNNING SERVICE (http://127.0.0.1:8000): GET only."""
import hashlib, io, json, sys, urllib.request, zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from comqutor_alpha.classification_recovery import snapshot_directory_hashes

BASE = "http://127.0.0.1:8000"
PARENT = "recovery-20261007T053635Z-26d6cd1a"
ROOT = "c904d4cc-dc09-495c-aec5-b056979948e1"
HERE = Path(__file__).resolve().parent
result = {"service": BASE, "method": "GET only", "checks": {}}


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return r.status, r.headers.get("content-type"), r.read()


def check(name, ok, **info):
    result["checks"][name] = {"ok": bool(ok), **info}
    print(("PASS " if ok else "FAIL ") + name, json.dumps(info, default=str)[:300], flush=True)


ready = json.loads(get("/ready")[2])
check("service_ready", ready["status"] == "ready" and ready["database"] == "ready", ready={k: ready.get(k) for k in ("status", "database", "job_manager", "real_execution")})
d = json.loads(get(f"/api/research/{PARENT}")[2]); o = json.loads(get(f"/api/research/{ROOT}")[2])
check("recovery_run_response", d["status"] == "completed" and d["lineage"]["based_on_run_id"] == ROOT and d["alpha_classification_status"] == "incomplete"
      and d["alpha_classification_completion"]["call_failure_count"] == 1, lineage=d["lineage"], completion=d["alpha_classification_completion"], summary=d["summary"])
check("original_run_still_incomplete", o["alpha_classification_status"] == "incomplete" and o["alpha_classification_completion"]["call_failure_count"] == 973 and "lineage" not in o,
      completion=o["alpha_classification_completion"], status=o["status"])
hist = {r["run_id"]: r for r in json.loads(get("/api/research?ticker=AMD&limit=50")[2])["items"]}
check("history_lists_both", hist.get(PARENT, {}).get("status") == "completed" and ROOT in hist, recovery=hist.get(PARENT, {}).get("status"), original=hist.get(ROOT, {}).get("status"))
st = json.loads(get(f"/api/research/{PARENT}/status")[2]); check("status_route", st["status"] == "completed", status=st["status"])
ao_p = json.loads(get(f"/api/research/{PARENT}/agent-outputs")[2]); ao_o = json.loads(get(f"/api/research/{ROOT}/agent-outputs")[2])
strip = lambda rows: [{k: v for k, v in r.items() if k != "run_id"} for r in rows]
check("agent_outputs_equal_apart_from_run_id", ao_p["count"] == ao_o["count"] > 0 and strip(ao_p["structured_agent_outputs"]) == strip(ao_o["structured_agent_outputs"]), count=ao_p["count"])
listing = json.loads(get(f"/api/research/{PARENT}/artifacts")[2])
check("artifact_listing", listing["artifact_completeness"] == "pass" and listing["ticker_consistency"] == "pass", artifacts=len(listing["artifacts"]))
entries = {e["artifact_name"]: e for e in listing["artifacts"]}
disk = REPO / "outputs" / "runs" / PARENT
check("manifest_hashes_match_disk", all(hashlib.sha256((disk / n).read_bytes()).hexdigest() == e["sha256"] for n, e in entries.items() if e.get("exists")))
code, _, body = get(f"/api/research/{PARENT}/artifacts/recovery_lineage.json")
lineage = json.loads(body)
check("lineage_download", code == 200 and lineage == json.loads((disk / "recovery_lineage.json").read_text()) and len(lineage["claim_identity_map"]) == 975, counts=lineage["classification_source_counts"])
code, ctype, body = get(f"/api/research/{PARENT}/export")
zf = zipfile.ZipFile(io.BytesIO(body))
mismatch = [n for n in zf.namelist() if zf.read(n) != (disk / n).read_bytes()]
matches = json.loads(zf.read("alpha_matches.json"))["matches"]
check("export_zip_byte_identical_to_files", code == 200 and ctype == "application/zip" and not mismatch and len(matches) == 975, members=len(zf.namelist()), bytes=len(body), mismatch=mismatch)
for ep in ("graph", "conflicts", "entity-exposures", "evidence-stances"):
    c, _, b = get(f"/api/research/{PARENT}/{ep}")
    check(f"route_{ep}", c == 200 and json.loads(b).get("status") in ("ok", "ready", None), http=c)
before = json.loads((HERE / "root_run_hashes_before_direction.json").read_text())
check("original_run_directory_unchanged", snapshot_directory_hashes(REPO / "outputs" / "runs" / ROOT) == before, files=len(before))
before_p = json.loads((HERE / "parent_run_hashes_before_direction.json").read_text())
check("recovery_run_directory_unchanged", snapshot_directory_hashes(disk) == before_p, files=len(before_p))
(HERE / "live_service_verification_result.json").write_text(json.dumps(result, indent=2, default=str))
bad = [k for k, v in result["checks"].items() if not v["ok"]]
print("FAILED CHECKS:", bad or "none"); sys.exit(1 if bad else 0)
