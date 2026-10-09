#!/usr/bin/env python3
"""Record the NVDA / QQQ disputes on their own (T2 sign-off: "NVDA、QQQ 尚未关闭的具体争议继续单独记录，不能通过换一个成功 run 消除").

Evaluates EVERY saved run of the named tickers under the current rule files (Type A re-evaluation, read-only, zero Provider calls) and lists each run's
verdict and every review / failure reason, so a later PASS cannot stand in for an earlier open item.

    python scripts/build_open_review_ledger.py --out-dir docs/audit_artifacts/.../open_review_ledger                 # NVDA and QQQ
    python scripts/build_open_review_ledger.py --out-dir /tmp/x --tickers NVDA QQQ AMD --closure-records records.json

--closure-records: a JSON list of {ticker, run_id, family, subject, decided_by, decided_at, decision, reference}. None exist today.
Exit codes: 0 written | 2 --out-dir already holds files.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.regression import open_review_ledger as ledger_module  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--runs-root", default=str(REPO_ROOT / "outputs" / "runs"))
    parser.add_argument("--tickers", nargs="+", default=["NVDA", "QQQ"])
    parser.add_argument("--closure-records", help="JSON file with recorded review decisions (default: none exist)")
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        print(f"refusing: {out_dir} already holds files; choose a new --out-dir", file=sys.stderr)
        return 2
    records = json.loads(Path(args.closure_records).read_text(encoding="utf-8")) if args.closure_records else []
    ledger = ledger_module.build_open_review_ledger(
        [t.upper() for t in args.tickers],
        runs_root=args.runs_root,
        generated_at=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        closure_records=records,
    )
    paths = ledger_module.write_outputs(ledger, out_dir)
    for ticker, block in ledger["tickers"].items():
        latest = block["latest_run"] or {}
        print(f"{ticker}: {block['runs_total']} saved runs, {block['open_item_count']} open items; latest {(latest.get('run_id') or '')[:8]} -> {latest.get('formal_status')}")
    for label, path in paths.items():
        print(f"wrote {label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
