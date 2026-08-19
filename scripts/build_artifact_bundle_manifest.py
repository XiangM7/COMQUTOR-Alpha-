#!/usr/bin/env python3
"""QA Closure v0.1.2 Item 6 CLI: audit (and, unless --check-only, safely
complete) the nine-artifact A2 bundle for each of the six regression
tickers' currently-selected saved run.

Example:
    python scripts/build_artifact_bundle_manifest.py \\
        --output docs/audit_artifacts/artifact_bundle_manifest.json

Reads the selected run_id per ticker from the existing
``outputs/regression/regression_report.json`` (QA Item 1's own runner
output) -- never guesses/hardcodes a run_id. Idempotent: a file already
present is never overwritten; re-running after every gap is already
closed reports the same complete_original/complete_reconstructed state
with zero additional writes. Zero Provider/TradingAgents calls anywhere
in this script's own code or import graph.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.evaluation.artifact_bundle_audit import (  # noqa: E402
    build_bundle_manifest,
    check_artifact_bundle,
    reconstruct_missing_artifacts,
)

EXIT_OK = 0
EXIT_INVALID_ARGS = 2
EXIT_REGRESSION_REPORT_UNAVAILABLE = 3


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--regression-report", default="outputs/regression/regression_report.json")
    parser.add_argument("--source-output-root", default="outputs/runs")
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--check-only", action="store_true", help="Report completeness only; never write any file."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    report_path = Path(args.regression_report)
    if not report_path.exists():
        print(f"ERROR: regression report not found at {report_path}.", file=sys.stderr)
        return EXIT_REGRESSION_REPORT_UNAVAILABLE
    report = json.loads(report_path.read_text(encoding="utf-8"))
    selected = {r["ticker"]: r.get("run_id") for r in report.get("results", []) if r.get("run_id")}
    if not selected:
        print("ERROR: regression report has no ticker/run_id results.", file=sys.stderr)
        return EXIT_REGRESSION_REPORT_UNAVAILABLE

    tickers_by_manifest: dict[str, dict] = {}
    for ticker, run_id in selected.items():
        before = check_artifact_bundle(run_id, ticker, args.source_output_root)
        reconstruction = None
        if before["missing_artifacts"] and not args.check_only:
            reconstruction = reconstruct_missing_artifacts(run_id, ticker, args.source_output_root, dry_run=False)
        elif before["missing_artifacts"]:
            reconstruction = reconstruct_missing_artifacts(run_id, ticker, args.source_output_root, dry_run=True)
        manifest = build_bundle_manifest(
            run_id, ticker, args.source_output_root, pre_existing=before["present_artifacts"], reconstruction=reconstruction
        )
        tickers_by_manifest[ticker] = manifest
        print(
            f"{ticker}: {manifest['present_count']}/{manifest['required_count']} "
            f"status={manifest['bundle_status']} reconstructed={manifest['reconstructed_artifacts']}"
        )

    output = {
        "schema_version": "artifact_bundle_manifest.v1",
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "regression_report_path": str(report_path),
        "check_only": args.check_only,
        "tickers": tickers_by_manifest,
        "provider_calls": 0,
        "tradingagents_calls": 0,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"\nartifact_bundle_manifest written to: {output_path}")
    print("provider_calls=0 tradingagents_calls=0")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
