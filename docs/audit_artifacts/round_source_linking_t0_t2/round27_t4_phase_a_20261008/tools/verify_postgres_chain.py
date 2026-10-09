#!/usr/bin/env python3
"""T4 Phase A: PostgreSQL chain verification against the isolated T4 instance (http://127.0.0.1:8002, loopback only).

  submit       -- through the production API job path (POST /api/research, offline mode -- the instance has real execution and the
                  Week 2 LLM switched off): V1 the NVDA 10-02 run's 12 saved agent outputs (a frozen-input recompute), V4 a
                  deliberately broken input, labelled SIMULATED, to produce a real failed/partial state. Polls each to a terminal state.
  snapshot L   -- every run in the instance's history: detail, status, graph, conflicts, agent outputs, key evidence trace, artifacts
  compare A B  -- two snapshots must be identical (history reopened after the instance restart)
  export       -- GET /api/research/{run_id}/export for every run: the ZIP's files against its artifact_manifest.json and the run dir
  consistency  -- run_id / input / hash: DB row <-> run dir <-> metadata; V1 raw outputs == the 10-02 run's; derived runs' lineage and
                  input hashes == their base; metadata.run_environment (database, code identity, execution type, effective config)
  migrations   -- schema_migrations rows and tables of comqutor_alpha_t4_test

    python verify_postgres_chain.py <phase> [args] --out-dir 01_postgres
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
API = "http://127.0.0.1:8002"
T4_ROOT = REPO / "outputs" / "t4_runs"
NVDA_SOURCE = REPO / "outputs" / "runs" / "034a0a60-430e-41f8-8321-03a11389707a"
V1_RUN_ID = "t4-frozen-nvda-034a0a60-20261008"
V4_RUN_ID = "t4-simulated-failure-20261008"
VOLATILE = {"elapsed_seconds", "eta_status", "estimated_remaining_seconds_min", "estimated_remaining_seconds_max", "eta_sample_count",
            "computed_at", "updated_at"}
client = httpx.Client(base_url=API, timeout=60, trust_env=False)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strip_volatile(value):
    if isinstance(value, dict):
        return {k: _strip_volatile(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [_strip_volatile(v) for v in value]
    return value


def _poll(run_id: str, timeout: float = 600) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/research/{run_id}/status").json()
        if body.get("status") in ("completed", "partial", "failed"):
            return body
        time.sleep(2)
    return {"status": "TIMEOUT_WAITING", "run_id": run_id}


def submit(out_dir: Path) -> dict:
    raw = json.loads((NVDA_SOURCE / "raw_agent_outputs.json").read_text(encoding="utf-8"))["agent_outputs"]
    v1_outputs = [{k: r[k] for k in ("agent", "tradingagents_agent", "source_field", "raw_output")} for r in raw]
    # V4: the input is broken on purpose (SIMULATED): every agent output empty -- whatever the production pipeline does with it is the state
    v4_outputs = [{"agent": "market_agent", "tradingagents_agent": "market_agent", "source_field": "SIMULATED_FAILURE_INJECTION", "raw_output": ""}]
    result = {}
    for label, run_id, outputs in (("V1_frozen_nvda", V1_RUN_ID, v1_outputs), ("V4_simulated_failure", V4_RUN_ID, v4_outputs)):
        response = client.post("/api/research", json={"ticker": "NVDA", "run_id": run_id, "offline_raw_agent_outputs": outputs})
        terminal = _poll(run_id) if response.status_code in (200, 202) else None
        result[label] = {"run_id": run_id, "http_status": response.status_code, "submission": response.json(), "terminal": terminal,
                         "submitted_outputs_sha256": _sha(json.dumps(outputs, sort_keys=True, ensure_ascii=False).encode("utf-8"))}
    return result


def _history() -> list[dict]:
    return client.get("/api/research", params={"limit": 50}).json().get("items", [])


def snapshot(label: str, out_dir: Path) -> dict:
    runs = {}
    for item in _history():
        rid = item["run_id"]
        runs[rid] = {name: _strip_volatile(client.get(path).json()) for name, path in (
            ("history_item", None), ("detail", f"/api/research/{rid}"), ("status", f"/api/research/{rid}/status"),
            ("graph", f"/api/research/{rid}/graph"), ("conflicts", f"/api/research/{rid}/conflicts"),
            ("agent_outputs", f"/api/research/{rid}/agent-outputs"), ("evidence_trace_key", f"/api/research/{rid}/evidence-trace?scope=key"),
            ("artifacts", f"/api/research/{rid}/artifacts")) if path}
        runs[rid]["history_item"] = _strip_volatile(item)
    (out_dir / f"snapshot_{label}.json").write_text(json.dumps(runs, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {"label": label, "runs": sorted(runs), "statuses": {rid: r["history_item"].get("status") for rid, r in runs.items()}}


def compare(a: str, b: str, out_dir: Path) -> dict:
    """Runs present in both snapshots must be identical; a run only in one of them is listed, not compared (the interrupted
    SIMULATED run is queued/running before the restart and only reaches its terminal state through the restart itself)."""
    left = json.loads((out_dir / f"snapshot_{a}.json").read_text(encoding="utf-8"))
    right = json.loads((out_dir / f"snapshot_{b}.json").read_text(encoding="utf-8"))
    common = sorted(set(left) & set(right))
    diffs = {rid: [name for name in set(left[rid]) | set(right[rid])
                   if json.dumps(left[rid].get(name), sort_keys=True) != json.dumps(right[rid].get(name), sort_keys=True)] for rid in common}
    diffs = {rid: names for rid, names in diffs.items() if names}
    return {"compared": [a, b], "common_runs": common, "only_in_first": sorted(set(left) - set(right)),
            "only_in_second": sorted(set(right) - set(left)), "identical": not diffs, "differences": diffs}


V5_RUN_ID = "t4-simulated-interrupted-20261008"


def submit_interrupt(out_dir: Path) -> dict:
    """SIMULATED failure injection: a frozen-input run is submitted and the caller restarts the instance while it is still running;
    the production startup reconciliation must then mark it failed. Returns as soon as the run is observed running."""
    raw = json.loads((NVDA_SOURCE / "raw_agent_outputs.json").read_text(encoding="utf-8"))["agent_outputs"][:11]
    outputs = [{k: r[k] for k in ("agent", "tradingagents_agent", "source_field", "raw_output")} for r in raw]
    response = client.post("/api/research", json={"ticker": "NVDA", "run_id": V5_RUN_ID, "offline_raw_agent_outputs": outputs})
    observed = []
    for _ in range(60):
        body = client.get(f"/api/research/{V5_RUN_ID}/status").json()
        observed.append({k: body.get(k) for k in ("status", "stage", "progress_percent")})
        if body.get("status") == "running" and (body.get("progress_percent") or 0) > 0:
            break
        time.sleep(1)
    return {"run_id": V5_RUN_ID, "http_status": response.status_code, "submission": response.json(), "observed_before_restart": observed[-3:],
            "note": "SIMULATED: the restart that follows is the injected failure"}


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
                manifest_name = next((n for n in names if n.endswith("artifact_manifest.json")), None)
                manifest = json.loads(zf.read(manifest_name)) if manifest_name else {}
                prefix = manifest_name[: -len("artifact_manifest.json")] if manifest_name else ""
                checks = []
                for art in manifest.get("artifacts", []):
                    if not art.get("exists"):
                        continue
                    member = prefix + art["path"]
                    in_zip = member in names
                    zip_sha = _sha(zf.read(member)) if in_zip else None
                    disk = T4_ROOT / rid / art["path"]
                    checks.append({"path": art["path"], "in_zip": in_zip, "zip_matches_manifest": zip_sha == art.get("sha256"),
                                   "disk_matches_manifest": disk.is_file() and _sha(disk.read_bytes()) == art.get("sha256")})
            entry.update({"zip_sha256": _sha(response.content), "members": len(names), "manifest_artifacts": len(checks),
                          "all_in_zip": all(c["in_zip"] for c in checks), "all_zip_match_manifest": all(c["zip_matches_manifest"] for c in checks),
                          "all_disk_match_manifest": all(c["disk_matches_manifest"] for c in checks),
                          "artifact_completeness": manifest.get("artifact_completeness"),
                          "mismatches": [c for c in checks if not (c["in_zip"] and c["zip_matches_manifest"] and c["disk_matches_manifest"])]})
        else:
            entry["body"] = response.json()
        results[rid] = entry
    return results


def _db_rows() -> dict:
    import sqlalchemy as sa

    url = subprocess.run([sys.executable, str(HERE / "create_t4_databases.py"), "--print-url-for", "comqutor_alpha_t4_test"],
                         capture_output=True, text=True, check=True).stdout.strip()
    engine = sa.create_engine(url)
    with engine.connect() as conn:
        conn.execute(sa.text("SET TRANSACTION READ ONLY"))
        runs = {r.run_id: dict(r._mapping) for r in conn.execute(sa.text(
            "select run_id, ticker, status, execution_mode, error_code, created_at, completed_at from research_runs"))}
        counts = {t: int(conn.execute(sa.text(f"select count(*) from {t}")).scalar()) for t in (
            "research_runs", "agent_outputs", "structure_graphs", "alpha_matches", "alpha_activations", "alpha_conflicts", "research_run_progress")}
    return {"research_runs": runs, "table_counts": counts}


def consistency(out_dir: Path) -> dict:
    db = _db_rows()
    checks = {}
    for rid, row in db["research_runs"].items():
        run_dir = T4_ROOT / rid
        metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8")) if (run_dir / "metadata.json").is_file() else {}
        env = metadata.get("run_environment") or {}
        entry = {"db_status": row["status"], "db_ticker": row["ticker"], "run_dir_exists": run_dir.is_dir(),
                 "metadata_run_id_matches": metadata.get("run_id") == rid, "metadata_ticker_matches": metadata.get("ticker") == row["ticker"],
                 "run_environment": {"execution_type": env.get("execution_type"), "database": env.get("database"),
                                     "code_identity_status": (env.get("code_identity") or {}).get("status"),
                                     "git_head": (env.get("code_identity") or {}).get("git_head"),
                                     "week2_enabled": ((env.get("effective_config") or {}).get("week2_semantic") or {}).get("enabled")}}
        if rid == V1_RUN_ID:
            mine = json.loads((run_dir / "raw_agent_outputs.json").read_text(encoding="utf-8"))["agent_outputs"]
            source = json.loads((NVDA_SOURCE / "raw_agent_outputs.json").read_text(encoding="utf-8"))["agent_outputs"]
            entry["raw_outputs_equal_source_run"] = [m["raw_output"] for m in mine] == [s["raw_output"] for s in source]
            entry["agents_equal_source_run"] = [m["agent"] for m in mine] == [s["agent"] for s in source]
            entry["raw_output_sha256_equal"] = (_sha("".join(m["raw_output"] for m in mine).encode("utf-8"))
                                                == _sha("".join(s["raw_output"] for s in source).encode("utf-8")))
        if metadata.get("based_on_run_id"):
            base = T4_ROOT / metadata["based_on_run_id"]
            original = REPO / "outputs" / "runs" / metadata["based_on_run_id"]
            entry["lineage"] = {"based_on_run_id": metadata["based_on_run_id"], "root_research_run_id": metadata.get("root_research_run_id"),
                                "input_alpha_matches_sha256_equals_base": metadata.get("input_alpha_matches_sha256") == _sha((base / "alpha_matches.json").read_bytes()),
                                "base_copy_alpha_matches_equals_original": _sha((base / "alpha_matches.json").read_bytes()) == _sha((original / "alpha_matches.json").read_bytes()),
                                "base_run_environment_recorded_as": metadata.get("based_on_run_environment")}
        checks[rid] = entry
    return {"table_counts": db["table_counts"], "runs": checks}


def migrations(out_dir: Path) -> dict:
    import sqlalchemy as sa

    url = subprocess.run([sys.executable, str(HERE / "create_t4_databases.py"), "--print-url-for", "comqutor_alpha_t4_test"],
                         capture_output=True, text=True, check=True).stdout.strip()
    engine = sa.create_engine(url)
    with engine.connect() as conn:
        conn.execute(sa.text("SET TRANSACTION READ ONLY"))
        rows = [dict(r._mapping) for r in conn.execute(sa.text("select version, applied_at from schema_migrations order by applied_at, version"))]
        tables = sorted(conn.execute(sa.text("select tablename from pg_tables where schemaname='public'")).scalars())
    return {"schema_migrations": rows, "tables": tables}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=("submit", "submit_interrupt", "snapshot", "compare", "export", "consistency", "migrations"))
    ap.add_argument("args", nargs="*")
    ap.add_argument("--out-dir", required=True)
    ns = ap.parse_args(argv)
    out_dir = Path(ns.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {"submit": lambda: submit(out_dir), "submit_interrupt": lambda: submit_interrupt(out_dir), "export": lambda: export(out_dir), "consistency": lambda: consistency(out_dir),
              "migrations": lambda: migrations(out_dir), "snapshot": lambda: snapshot(ns.args[0], out_dir),
              "compare": lambda: compare(ns.args[0], ns.args[1], out_dir)}[ns.phase]()
    name = f"{ns.phase}{'_' + '_'.join(ns.args) if ns.args else ''}_result.json"
    (out_dir / name).write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, default=str)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
