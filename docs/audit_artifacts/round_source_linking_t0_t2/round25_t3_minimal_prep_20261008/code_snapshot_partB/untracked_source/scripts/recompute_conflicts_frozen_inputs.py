#!/usr/bin/env python3
"""Frozen-input conflict recompute (T0 execution type "冻结输入重算"): re-run ONLY the deterministic conflict detector on saved runs' own saved
alpha_activations.json + alpha_matches.json under the current taxonomy, and set the result beside what each run saved. No model, search, fetch or replay;
nothing is written into any run directory; the output directory must be new or empty.

    python scripts/recompute_conflicts_frozen_inputs.py --out-dir docs/audit_artifacts/.../frozen_input_recompute
    python scripts/recompute_conflicts_frozen_inputs.py --out-dir /tmp/x --run MSFT=<run_id> --taxonomy path/to/taxonomy.yaml

Exit codes: 0 all recomputed | 2 --out-dir already holds files / bad arguments | 3 some run could not be recomputed.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.regression import (  # noqa: E402
    formal_acceptance_report,
    frozen_input_conflict_recompute,
)


def _parse_run(value: str) -> tuple[str, str]:
    ticker, sep, run_id = value.partition("=")
    if not sep or not ticker or not run_id:
        raise argparse.ArgumentTypeError(f"--run expects TICKER=RUN_ID, got {value!r}")
    return ticker.upper(), run_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--runs-root", default=str(REPO_ROOT / "outputs" / "runs"))
    parser.add_argument("--run", action="append", type=_parse_run, metavar="TICKER=RUN_ID", help="default: the six pinned historical runs")
    parser.add_argument("--taxonomy", help="default: the repository's alpha_taxonomy_v1.yaml")
    parser.add_argument("--execution-id")
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        print(f"refusing: {out_dir} already holds files; choose a new --out-dir", file=sys.stderr)
        return 2
    now = datetime.now(UTC)
    document = frozen_input_conflict_recompute.recompute_saved_runs(
        dict(args.run) if args.run else dict(formal_acceptance_report.DEFAULT_SIX_TICKER_RUNS),
        runs_root=args.runs_root,
        execution_id=args.execution_id or "frozen-input-recompute-" + now.strftime("%Y%m%dT%H%M%SZ"),
        taxonomy_path=args.taxonomy,
        generated_at=now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )
    paths = frozen_input_conflict_recompute.write_outputs(document, out_dir)
    for ticker, entry in document["tickers"].items():
        if entry["status"] != "RECOMPUTED":
            print(f"{ticker:5} {entry['run_id'][:8]}  {entry['status']}  {entry.get('error') or entry.get('missing') or ''}")
            continue
        print(f"{ticker:5} {entry['run_id'][:8]}  saved={entry['saved']['admitted']} -> recomputed={entry['recomputed']['admitted']}  main {entry['saved']['main_conflict']} -> {entry['recomputed']['main_conflict']}")
    for label, path in paths.items():
        print(f"wrote {label}: {path}")
    return 3 if any(e["status"] != "RECOMPUTED" for e in document["tickers"].values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
