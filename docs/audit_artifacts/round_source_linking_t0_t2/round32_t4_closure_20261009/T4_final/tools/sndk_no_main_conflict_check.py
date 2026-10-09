#!/usr/bin/env python3
"""T4 round 32: SNDK historical "no main conflict" -- read-only check that the database row, the saved artifacts and the page /
API of the FINAL-code demo instance agree. Starts no research, writes nothing under outputs/.

Runs: the historical SNDK run 52c23371 (outputs/runs, original) and its Round 27 re-evaluation
dependency-20261008T213350Z-89497ab9 (persisted in comqutor_alpha_t4_test; served here from the restored demo copy).

    python sndk_no_main_conflict_check.py --out 06_frozen_checks/sndk_no_main_conflict.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import httpx
import sqlalchemy as sa

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
API = "http://127.0.0.1:8005"
ORIGINAL = REPO / "outputs" / "runs" / "52c23371-c374-4064-a91c-20c599ffa79c"
DERIVED_ID = "dependency-20261008T213350Z-89497ab9"
DEMO_ROOT = REPO / "outputs" / "t4_r32_demo_runs"


def tree(d: Path) -> dict[str, str]:
    return {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.rglob("*")) if p.is_file()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    before = tree(ORIGINAL)
    url = subprocess.run([sys.executable, str(HERE / "create_r32_databases.py"), "--print-url-for", "comqutor_alpha_t4_r32_demo_test"],
                         capture_output=True, text=True, check=True).stdout.strip()
    engine = sa.create_engine(url)
    with engine.connect() as conn:
        conn.execute(sa.text("SET TRANSACTION READ ONLY"))
        row = conn.execute(sa.text("select run_id, ticker, status, execution_mode, completed_at from research_runs where run_id = :r"), {"r": DERIVED_ID}).mappings().first()
        conflict_rows = [dict(r) for r in conn.execute(sa.text("select * from alpha_conflicts where run_id = :r"), {"r": DERIVED_ID}).mappings()]
    saved_derived = json.loads((DEMO_ROOT / DERIVED_ID / "conflicts.json").read_text(encoding="utf-8"))
    saved_original = json.loads((ORIGINAL / "conflicts.json").read_text(encoding="utf-8"))
    client = httpx.Client(base_url=API, timeout=120, trust_env=False)
    detail = client.get(f"/api/research/{DERIVED_ID}").json()
    conflicts_api = client.get(f"/api/research/{DERIVED_ID}/conflicts").json()
    ready = client.get("/ready").json()

    def admitted(payload):
        return payload.get("admitted_conflict_count")

    doc = {
        "database_row": {k: str(v) for k, v in dict(row).items()} if row else None,
        "database_conflict_rows": len(conflict_rows),
        "database_conflict_outcomes": dict(__import__("collections").Counter(str(r.get("outcome")) for r in conflict_rows)),
        "database_main_conflict_rows": sum(1 for r in conflict_rows if r.get("is_main_conflict")),
        "saved_artifacts": {"derived_conflicts_json": {"admitted_conflict_count": admitted(saved_derived), "main_conflict": saved_derived.get("main_conflict")},
                            "original_52c23371_conflicts_json": {"admitted_conflict_count": admitted(saved_original), "main_conflict": saved_original.get("main_conflict")}},
        "api_final_code": {"code_identity": {k: (ready.get("code_identity") or {}).get(k) for k in ("tracked_diff_sha256", "untracked_runtime_source_sha256")},
                           "status": detail.get("status"), "main_conflict": detail.get("main_conflict"), "conflict_status": detail.get("conflict_status"),
                           "conflicts_route_main_conflict": conflicts_api.get("main_conflict"), "conflicts_route_admitted": len(conflicts_api.get("conflicts") or [])},
        "page_evidence": "07_demo/recording_final scene 10_sndk_no_main_conflict (video + screens/10_sndk_no_main_conflict.png)",
        "original_run_unchanged": tree(ORIGINAL) == before,
    }
    doc["all_agree_no_main_conflict"] = (doc["database_main_conflict_rows"] == 0 and "admitted" not in doc["database_conflict_outcomes"]
                                         and doc["api_final_code"]["main_conflict"] is None and saved_derived.get("main_conflict") is None
                                         and saved_original.get("main_conflict") is None and admitted(saved_derived) == 0
                                         and doc["api_final_code"]["conflicts_route_main_conflict"] is None)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(doc, ensure_ascii=False, default=str)[:2000])
    return 0 if doc["all_agree_no_main_conflict"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
