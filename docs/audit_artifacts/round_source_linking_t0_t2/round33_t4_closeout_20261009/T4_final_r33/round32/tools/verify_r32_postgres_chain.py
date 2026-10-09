#!/usr/bin/env python3
"""T4 round 32: PostgreSQL chain verification on the FINAL code, against the isolated verify instance
(http://127.0.0.1:8004, database comqutor_alpha_t4_r32_verify_test, output root outputs/t4_r32_verify_runs). Loopback only.

  migrations   -- schema_migrations rows and tables of the verify database (it was empty before the derived execution)
  snapshot L   -- every run in the instance's history: detail (incl. stage_disclosure), status, graph, conflicts, agent outputs,
                  key evidence trace, artifacts
  compare A B  -- two snapshots must be identical (history reopened after a normal stop + restart of the instance)
  export       -- GET /api/research/{run_id}/export: every manifest file in the ZIP, ZIP == manifest == run directory;
                  stage_disclosure.json in the ZIP equals the API's stage_disclosure
  consistency  -- DB row <-> run directory <-> metadata; the derived execution's lineage (based_on_run_id), its Week 1 inputs
                  equal the based-on run's (run id normalised), its source registry content hashes, run_environment
                  (database, final code identity, execution type old_result_reevaluation)

    python verify_r32_postgres_chain.py <phase> [args] --out-dir 03_postgres
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
API = "http://127.0.0.1:8004"
ROOT = REPO / "outputs" / "t4_r32_verify_runs"
BASE_RUN_ID = "12591384-0b26-470d-a99d-a49c00be440b"
BASE_DIR = REPO / "outputs" / "t4_runs" / BASE_RUN_ID
DB = "comqutor_alpha_t4_r32_verify_test"
VOLATILE = {"elapsed_seconds", "eta_status", "estimated_remaining_seconds_min", "estimated_remaining_seconds_max", "eta_sample_count",
            "computed_at", "updated_at"}
client = httpx.Client(base_url=API, timeout=120, trust_env=False)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strip(value):
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


def _url() -> str:
    return subprocess.run([sys.executable, str(HERE / "create_r32_databases.py"), "--print-url-for", DB], capture_output=True, text=True,
                          check=True).stdout.strip()


def _history() -> list[dict]:
    return client.get("/api/research", params={"limit": 50}).json().get("items", [])


def migrations(out_dir: Path) -> dict:
    import sqlalchemy as sa

    engine = sa.create_engine(_url())
    with engine.connect() as conn:
        conn.execute(sa.text("SET TRANSACTION READ ONLY"))
        rows = [dict(r._mapping) for r in conn.execute(sa.text("select version, applied_at from schema_migrations order by applied_at, version"))]
        tables = sorted(conn.execute(sa.text("select tablename from pg_tables where schemaname='public'")).scalars())
        dialect = conn.dialect.name
        name = conn.execute(sa.text("select current_database()")).scalar()
    return {"dialect": dialect, "database": name, "schema_migrations": rows, "tables": tables}


def snapshot(label: str, out_dir: Path) -> dict:
    ready = client.get("/ready").json()
    runs = {}
    for item in _history():
        rid = item["run_id"]
        runs[rid] = {name: _strip(client.get(path).json()) for name, path in (
            ("detail", f"/api/research/{rid}"), ("status", f"/api/research/{rid}/status"), ("graph", f"/api/research/{rid}/graph"),
            ("conflicts", f"/api/research/{rid}/conflicts"), ("agent_outputs", f"/api/research/{rid}/agent-outputs"),
            ("evidence_trace_key", f"/api/research/{rid}/evidence-trace?scope=key"), ("artifacts", f"/api/research/{rid}/artifacts"))}
        runs[rid]["history_item"] = _strip(item)
    (out_dir / f"snapshot_{label}.json").write_text(json.dumps(runs, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {"label": label, "ready": {k: ready.get(k) for k in ("status", "database_backend", "code_identity", "real_execution")},
            "runs": sorted(runs), "statuses": {rid: r["history_item"].get("status") for rid, r in runs.items()},
            "stage_disclosure_degraded": {rid: (r["detail"].get("stage_disclosure") or {}).get("degraded_stages") for rid, r in runs.items()}}


def compare(a: str, b: str, out_dir: Path) -> dict:
    left = json.loads((out_dir / f"snapshot_{a}.json").read_text(encoding="utf-8"))
    right = json.loads((out_dir / f"snapshot_{b}.json").read_text(encoding="utf-8"))
    common = sorted(set(left) & set(right))
    diffs = {rid: [n for n in set(left[rid]) | set(right[rid]) if json.dumps(left[rid].get(n), sort_keys=True) != json.dumps(right[rid].get(n), sort_keys=True)]
             for rid in common}
    diffs = {rid: names for rid, names in diffs.items() if names}
    return {"compared": [a, b], "common_runs": common, "only_in_first": sorted(set(left) - set(right)), "only_in_second": sorted(set(right) - set(left)),
            "identical": not diffs and set(left) == set(right), "differences": diffs}


def export(out_dir: Path) -> dict:
    results = {}
    (out_dir / "exports").mkdir(exist_ok=True)
    for item in _history():
        rid = item["run_id"]
        response = client.get(f"/api/research/{rid}/export")
        entry = {"http_status": response.status_code}
        if response.status_code == 200:
            (out_dir / "exports" / f"{rid}.zip").write_bytes(response.content)
            with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                names = zf.namelist()
                manifest = json.loads(zf.read("artifact_manifest.json"))
                checks = []
                for art in manifest.get("artifacts", []):
                    if not art.get("exists"):
                        continue
                    in_zip = art["path"] in names
                    zip_sha = _sha(zf.read(art["path"])) if in_zip else None
                    disk = ROOT / rid / art["path"]
                    checks.append({"path": art["path"], "in_zip": in_zip, "zip_matches_manifest": zip_sha == art.get("sha256"),
                                   "disk_matches_manifest": disk.is_file() and _sha(disk.read_bytes()) == art.get("sha256")})
                disclosure_zip = json.loads(zf.read("stage_disclosure.json")) if "stage_disclosure.json" in names else None
            api_disclosure = client.get(f"/api/research/{rid}").json().get("stage_disclosure")
            entry.update({"zip_sha256": _sha(response.content), "members": len(names), "manifest_artifacts": len(checks),
                          "all_in_zip": all(c["in_zip"] for c in checks), "all_zip_match_manifest": all(c["zip_matches_manifest"] for c in checks),
                          "all_disk_match_manifest": all(c["disk_matches_manifest"] for c in checks),
                          "artifact_completeness": manifest.get("artifact_completeness"),
                          "stage_disclosure_in_zip": disclosure_zip is not None,
                          "stage_disclosure_zip_equals_api": disclosure_zip == api_disclosure if disclosure_zip is not None else None,
                          "mismatches": [c for c in checks if not (c["in_zip"] and c["zip_matches_manifest"] and c["disk_matches_manifest"])]})
        else:
            entry["body"] = response.json()
        results[rid] = entry
    return results


def _db_rows() -> dict:
    import sqlalchemy as sa

    engine = sa.create_engine(_url())
    with engine.connect() as conn:
        conn.execute(sa.text("SET TRANSACTION READ ONLY"))
        runs = {r.run_id: dict(r._mapping) for r in conn.execute(sa.text(
            "select run_id, ticker, status, execution_mode, error_code, created_at, completed_at from research_runs"))}
        counts = {t: int(conn.execute(sa.text(f"select count(*) from {t}")).scalar()) for t in (
            "research_runs", "agent_outputs", "structure_graphs", "alpha_matches", "alpha_activations", "alpha_conflicts")}
        per_run = {rid: {t: int(conn.execute(sa.text(f"select count(*) from {t} where run_id = :r"), {"r": rid}).scalar())
                         for t in ("agent_outputs", "alpha_matches", "structure_graphs", "alpha_activations", "alpha_conflicts")} for rid in runs}
    return {"research_runs": runs, "table_counts": counts, "per_run_counts": per_run}


def consistency(out_dir: Path) -> dict:
    db = _db_rows()
    checks = {}
    for rid, row in db["research_runs"].items():
        run_dir = ROOT / rid
        metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
        env = metadata.get("run_environment") or {}
        structured = json.loads((run_dir / "structured_agent_outputs.json").read_text(encoding="utf-8"))
        entry = {"db_status": row["status"], "db_execution_mode": row["execution_mode"], "run_dir_exists": run_dir.is_dir(),
                 "metadata_run_id_matches": metadata.get("run_id") == rid, "metadata_ticker_matches": metadata.get("ticker") == row["ticker"],
                 "db_agent_outputs_equal_structured_records": db["per_run_counts"][rid]["agent_outputs"] == len(structured.get("records") or []),
                 "run_environment": {"execution_type": env.get("execution_type"), "database": env.get("database"),
                                     "code_identity": {k: (env.get("code_identity") or {}).get(k) for k in ("git_head", "tracked_diff_sha256", "untracked_runtime_source_sha256")}},
                 "derived_execution": metadata.get("derived_execution")}
        if metadata.get("based_on_run_id") == BASE_RUN_ID:
            def normalised(name: str) -> str:
                return (run_dir / name).read_text(encoding="utf-8").replace(rid, BASE_RUN_ID)
            base_raw = json.loads((BASE_DIR / "raw_agent_outputs.json").read_text(encoding="utf-8"))
            mine_raw = json.loads(normalised("raw_agent_outputs.json"))
            base_src = json.loads((BASE_DIR / "source_registry.json").read_text(encoding="utf-8"))
            mine_src = json.loads(normalised("source_registry.json"))
            entry["lineage"] = {
                "based_on_run_id": metadata["based_on_run_id"],
                "based_on_run_environment_code": ((metadata.get("based_on_run_environment") or {}).get("code_identity") or {}).get("tracked_diff_sha256"),
                "raw_agent_outputs_equal_based_on_run": mine_raw == base_raw,
                "raw_outputs_text_sha256_equal": _sha("".join(o["raw_output"] for o in mine_raw["agent_outputs"]).encode()) == _sha("".join(o["raw_output"] for o in base_raw["agent_outputs"]).encode()),
                "source_registry_equal_based_on_run": mine_src == base_src,
                "source_content_hashes_equal": sorted(s.get("content_hash") or "" for s in mine_src["sources"]) == sorted(s.get("content_hash") or "" for s in base_src["sources"]),
                "copied_week1_inputs_sha256_match_based_on_files": all(_sha((BASE_DIR / n).read_bytes()) == h for n, h in ((metadata.get("derived_execution") or {}).get("copied_week1_inputs_sha256") or {}).items()),
                "based_on_run_directory_unchanged": None,  # filled by the protected-file comparison (hash_proof/)
            }
        checks[rid] = entry
    return {"database": DB, "table_counts": db["table_counts"], "per_run_counts": db["per_run_counts"], "runs": checks}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=("migrations", "snapshot", "compare", "export", "consistency"))
    ap.add_argument("args", nargs="*")
    ap.add_argument("--out-dir", required=True)
    ns = ap.parse_args(argv)
    out_dir = Path(ns.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {"migrations": lambda: migrations(out_dir), "export": lambda: export(out_dir), "consistency": lambda: consistency(out_dir),
              "snapshot": lambda: snapshot(ns.args[0], out_dir), "compare": lambda: compare(ns.args[0], ns.args[1], out_dir)}[ns.phase]()
    name = f"{ns.phase}{'_' + '_'.join(ns.args) if ns.args else ''}_result.json"
    (out_dir / name).write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, default=str)[:2500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
