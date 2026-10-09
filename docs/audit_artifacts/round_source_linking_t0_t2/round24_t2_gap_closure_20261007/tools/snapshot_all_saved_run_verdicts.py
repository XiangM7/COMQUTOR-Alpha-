#!/usr/bin/env python3
"""Read-only: re-evaluates EVERY saved run of the six Gold tickers through the unified formal-acceptance entry and writes one compact JSON, so the same
script can be run on the code BEFORE and AFTER a change and the two files compared run by run. Zero network (trap), nothing written under outputs/.

    python snapshot_all_saved_run_verdicts.py --out <new file> [--runs-root outputs/runs] [--tickers NVDA QQQ ...]
"""
import argparse
import json
import socket
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[0]
for cand in (Path.cwd(), *Path(__file__).resolve().parents):
    if (cand / "comqutor_alpha").is_dir():
        REPO = cand
        break
sys.path.insert(0, str(REPO))

attempts = []


def _refuse(name):
    def stub(*a, **k):
        attempts.append(name)
        raise RuntimeError("network attempted: " + name)

    return stub


socket.socket.connect = _refuse("connect")
socket.socket.connect_ex = _refuse("connect_ex")
socket.create_connection = _refuse("create_connection")
socket.getaddrinfo = _refuse("getaddrinfo")
urllib.request.urlopen = _refuse("urlopen")

from comqutor_alpha.regression.formal_acceptance_report import evaluate_saved_run  # noqa: E402
from comqutor_alpha.regression.open_review_ledger import _sort_key  # noqa: E402
from comqutor_alpha.regression.run_selection import discover_candidate_runs  # noqa: E402

TICKERS = ("NVDA", "QQQ", "SNDK", "MSFT", "TSM", "AMD")


def _subject(x):
    return x.get("rule_id") or x.get("pair") or x.get("alpha_id") or ",".join(x.get("pairs") or ()) or ""


def compact(entry):
    v = entry.get("verdict") or {}
    fam = v.get("rule_family_results") or {}
    return {
        "status": entry.get("status"),
        "formal_status": v.get("formal_status"),
        "reason_code": v.get("config_error_reason_code") or v.get("semantic_input_reason_code"),
        "stance_source": entry.get("stance_source"),
        "artifact_completeness": entry.get("artifact_completeness"),
        "admitted_conflicts": entry.get("admitted_conflicts"),
        "failure_reasons": sorted([(r.get("family"), _subject(r)) for r in v.get("failure_reasons") or []]),
        "review_reasons": sorted([(r.get("family"), _subject(r), r.get("verdict")) for r in v.get("review_reasons") or []]),
        "must_detect": sorted([(r.get("pair"), r.get("verdict")) for r in fam.get("must_detect_if_evidence_present") or [] if isinstance(r, dict)]),
        "should_detect": sorted([(r.get("pair"), r.get("verdict")) for r in fam.get("should_detect_if_supported") or [] if isinstance(r, dict)]),
        "undeclared_admitted_conflicts": v.get("undeclared_admitted_conflicts"),
        "pass_is_vacuous": (v.get("coverage") or {}).get("pass_is_vacuous"),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--runs-root", default=str(REPO / "outputs" / "runs"))
    ap.add_argument("--tickers", nargs="+", default=list(TICKERS))
    ap.add_argument("--labels-v2")
    args = ap.parse_args(argv)
    out = Path(args.out)
    if out.exists():
        print("refusing: output exists", out, file=sys.stderr)
        return 2
    runs = {}
    for t in args.tickers:
        cands = sorted(discover_candidate_runs(t, args.runs_root), key=_sort_key)
        for c in cands:
            kw = {"label_v2_path": args.labels_v2} if args.labels_v2 else {}
            e = evaluate_saved_run(ticker=t, run_id=c["run_id"], runs_root=args.runs_root, **kw)
            runs[f"{t}:{c['run_id']}"] = {"ticker": t, "run_id": c["run_id"], "analysis_date": c.get("analysis_date"), **compact(e)}
    doc = {"runs_total": len(runs), "network_attempts": len(attempts), "runs": runs}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print("runs:", len(runs), "| network attempts:", len(attempts), "| wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
