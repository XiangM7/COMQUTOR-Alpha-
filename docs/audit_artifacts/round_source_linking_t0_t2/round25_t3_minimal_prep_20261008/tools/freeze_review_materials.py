#!/usr/bin/env python3
"""Round 25 part B execution: fix the reviewer's material list BEFORE any prediction exists.

Reads the collection directory of the execution (<execution_id>-materials/), checks each collected market against the claim it is for
(market question and resolution definition, observation timestamps, granularity), keeps only points inside the requested window, and writes
review_materials_frozen.json next to the collection, with its own sha256 printed. The v4 review form itself is not changed; this file is its
addendum. Nothing here is written into the original runs, and nothing here is ever sent to a model.

    python freeze_review_materials.py --materials-dir outputs/t3_joint_evaluations/<execution_id>-materials
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
B1 = HERE.parent / "B1_samples_v4"
WINDOW = ("2026-09-24T00:00:00+00:00", "2026-10-07T00:00:00+00:00")
FILES = {"US recession by end of 2026": "02_clob_prices_history_us_recession_by_end_of_2026.json",
         "UK recession in 2026": "03_clob_prices_history_uk_recession_in_2026.json",
         "Japan recession in 2026": "04_clob_prices_history_japan_recession_in_2026.json"}
# what each sample claims, as of when (the run's start time; the news agent read live Gamma prices during the run)
CLAIMS = {
    "t3v3-037": {"run": "1bad76a7", "run_started_at": "2026-10-05T17:36:24Z", "claimed": "US 8% (-1.0pp week); UK 7%; Japan 4%",
                 "markets": ["US recession by end of 2026", "UK recession in 2026", "Japan recession in 2026"]},
    "t3v3-038": {"run": "034a0a60", "run_started_at": "2026-10-02T00:55:24Z", "claimed": "Japan recession in 2026: 4% Yes; volume $4K",
                 "markets": ["Japan recession in 2026"], "not_recoverable": ["the $4K traded volume as of that date (the market reports only its current cumulative volume)"]},
    "t3v3-039": {"run": "034a0a60", "run_started_at": "2026-10-02T00:55:24Z", "claimed": "8% and falling 2pp on the week (US)",
                 "markets": ["US recession by end of 2026"]},
    "t3v3-040": {"run": "1bad76a7", "run_started_at": "2026-10-05T17:36:24Z", "claimed": "recession odds are 8% and falling (US)",
                 "markets": ["US recession by end of 2026"]},
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--materials-dir", required=True)
    args = ap.parse_args(argv)
    mdir = Path(args.materials_dir)
    out = mdir / "review_materials_frozen.json"
    if out.exists():
        print("refusing: the material list is already frozen", out, file=sys.stderr)
        return 2
    record = json.loads((mdir / "collection_record.json").read_text(encoding="utf-8"))
    search = json.loads((mdir / "01_gamma_public_search.json").read_text(encoding="utf-8"))
    by_id = {str(m.get("id")): m for e in search.get("events", []) for m in e.get("markets", []) if isinstance(m, dict)}
    start, end = (datetime.fromisoformat(x) for x in WINDOW)
    markets = {}
    for question, fname in FILES.items():
        meta = record["markets"].get(question, {})
        if meta.get("status") != "COLLECTED":
            markets[question] = {"status": meta.get("status", "NOT_COLLECTED")}
            continue
        m = by_id[str(meta["market_id"])]
        history = json.loads((mdir / fname).read_text(encoding="utf-8"))["history"]
        points, excluded = [], []
        for p in history:
            t = datetime.fromtimestamp(int(p["t"]), tz=timezone.utc)
            (points if start <= t < end else excluded).append({"observed_at_utc": t.isoformat(), "yes_price": p["p"]})
        req = next(r for r in record["requests"] if r.get("file") == fname)
        markets[question] = {
            "status": "COLLECTED", "market_id": meta["market_id"], "question_as_listed": m.get("question"),
            "resolution_definition": m.get("description"), "resolves_by": m.get("endDate"), "outcomes": m.get("outcomes"),
            "granularity": "one point-in-time Yes price per day, sampled at about 00:00 UTC (CLOB prices-history, fidelity 1440 minutes); not a daily close or average",
            "points_in_window": points,
            "excluded_points": [{**e, "why": "outside the requested window (the API also returned the price at collection time)"} for e in excluded],
            "source": {"url": req["final_url"], "retrieved_at": req["retrieved_at"], "status_code": req["status_code"], "response_sha256": req["sha256"], "file": fname},
            "market_lookup": {"file": "01_gamma_public_search.json", "response_sha256": record["requests"][0]["sha256"], "retrieved_at": record["requests"][0]["retrieved_at"]},
        }
    items = {}
    for sid, c in CLAIMS.items():
        items[sid] = {
            "claim_as_of": f"run {c['run']}, started {c['run_started_at']}; the run's news agent read live Gamma prices during the run, so the matching value lies "
                           "between the daily points around that time",
            "claimed": c["claimed"],
            "material": [{"market": q, **{k: markets[q].get(k) for k in ("status", "question_as_listed", "resolution_definition", "resolves_by", "granularity", "points_in_window", "source")}}
                         for q in c["markets"]],
            "not_recoverable": c.get("not_recoverable", []),
            "note": ("collected on 2026-10-08 FOR THIS VERIFICATION and bound to its execution; this is not material the original run saved, and it was "
                     "not sent to any model"),
        }
    document = {
        "schema_version": "t3_review_materials_frozen.v1",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "frozen_before_prediction": True,
        "review_form": {"path": str((B1 / "review_form_v4.json").relative_to(REPO)), "sha256": _sha(B1 / "review_form_v4.json")},
        "collection_record_sha256": _sha(mdir / "collection_record.json"),
        "rule": "the reviewer receives review_form_v4.json plus these items, and nothing selected after the predictions exist",
        "markets": markets,
        "items": items,
    }
    out.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("frozen", out, _sha(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
