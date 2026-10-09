#!/usr/bin/env python3
"""Unified formal acceptance entry for runs that are already saved (COMQUTOR Alpha next-round task sheet, T2, "第三，统一正式验收入口").

Reads each named run's own persisted artifacts (read-only), runs the six-rule-family acceptance engine on them with the rule files YOU name, and
writes, from that one result: the verdict JSON, the resolved effective_rules, and every table as Markdown. No Provider call, no replay, no
recompute, no write into any run directory. The output directory must be new or empty - a delivered verdict file is never overwritten.

    python scripts/run_formal_acceptance.py --out-dir docs/audit_artifacts/.../six_ticker                 # the six pinned historical runs
    python scripts/run_formal_acceptance.py --out-dir /tmp/x --run AMD=<run_id> --taxonomy path/to/taxonomy.yaml --labels-v2 path/to/labels.yaml

Exit codes: 0 every run evaluated | 2 --out-dir already holds files / bad arguments | 3 some run could not be evaluated
(RUN_NOT_FOUND) or some verdict is a config_error.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import yaml  # noqa: E402

from comqutor_alpha.regression import formal_acceptance_report as report  # noqa: E402

DEFAULT_BASELINE = REPO_ROOT / "docs" / "audit_artifacts" / "v0_2_john_frozen_gold_baseline.yaml"


def _parse_run(value: str) -> tuple[str, str]:
    ticker, sep, run_id = value.partition("=")
    if not sep or not ticker or not run_id:
        raise argparse.ArgumentTypeError(f"--run expects TICKER=RUN_ID, got {value!r}")
    return ticker.upper(), run_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", required=True, help="new or empty directory for the three output files")
    parser.add_argument("--runs-root", default=str(REPO_ROOT / "outputs" / "runs"), help="directory holding the saved run directories (read-only)")
    parser.add_argument("--run", action="append", type=_parse_run, metavar="TICKER=RUN_ID", help="repeatable; default: the six pinned historical runs")
    parser.add_argument("--taxonomy", help="taxonomy file (default: the repository's alpha_taxonomy_v1.yaml)")
    parser.add_argument("--labels-v2", help="v0.2 label file (default: the repository's)")
    parser.add_argument("--labels-v1", help="v0.1 label file, read for the dominance guard (default: the repository's)")
    parser.add_argument(
        "--baseline",
        default=str(DEFAULT_BASELINE),
        help="John's frozen baseline, for the allowed_main_conflicts table; pass 'none' to leave that table out",
    )
    parser.add_argument("--execution-id", help="default: formal-acceptance-<UTC timestamp>")
    args = parser.parse_args(argv)

    runs = dict(args.run) if args.run else dict(report.DEFAULT_SIX_TICKER_RUNS)
    baseline_pairs = None
    if args.baseline.lower() != "none":
        baseline_pairs = yaml.safe_load(Path(args.baseline).read_text(encoding="utf-8"))["allowed_main_conflicts"]
    execution_id = args.execution_id or "formal-acceptance-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    out_dir = Path(args.out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        print(f"refusing: {out_dir} already holds files; choose a new --out-dir (verdict files are never overwritten)", file=sys.stderr)
        return 2

    document = report.evaluate_saved_runs(
        runs,
        runs_root=args.runs_root,
        execution_id=execution_id,
        taxonomy_path=args.taxonomy,
        label_v2_path=args.labels_v2,
        label_v1_path=args.labels_v1,
        baseline_pairs=baseline_pairs,
    )
    paths = report.write_outputs(document, out_dir)

    for ticker, entry in document["tickers"].items():
        verdict = entry.get("verdict") or {}
        print(f"{ticker:5} {entry['run_id'][:8]}  {verdict.get('formal_status') or entry['status']:<26} admitted={entry.get('admitted_conflicts')}")
    for label, path in paths.items():
        print(f"wrote {label}: {path}")
    broken = [
        t
        for t, e in document["tickers"].items()
        if e["status"] != "EVALUATED" or (e.get("verdict") or {}).get("formal_status") == "config_error"
    ]
    return 3 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
