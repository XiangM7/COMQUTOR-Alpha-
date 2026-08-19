#!/usr/bin/env python3
"""QA Closure v0.1.2 Item 5 CLI: build the Neutral / Unclassified Findings
audit for one already-saved run's ``unclassified_findings.json``.

Example:
    python scripts/build_neutral_unclassified_audit.py \\
        --run-id 07ddc074-9ab2-4b16-8957-acbf94012144 \\
        --output docs/audit_artifacts/neutral_unclassified_audit_msft_07ddc074.json

Offline only: reads the run's own already-saved ``unclassified_findings.json``
from disk (never recomputes it, never calls the Alpha Mapper/Evidence
Stance/Evidence Fact grouping/B1-B5, never calls a Provider/LLM). Exit code
policy:
  0  audit built and written successfully.
  2  invalid CLI arguments.
  3  the run's unclassified_findings.json does not exist or fails to load.
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

from comqutor_alpha.api.unclassified_findings import ARTIFACT_FILENAME  # noqa: E402
from comqutor_alpha.evaluation.neutral_unclassified_audit import (  # noqa: E402
    DEFAULT_TOP_N,
    build_neutral_unclassified_audit,
)
from comqutor_alpha.storage.file_store import load_json_record_if_exists  # noqa: E402

EXIT_OK = 0
EXIT_INVALID_ARGS = 2
EXIT_SOURCE_UNAVAILABLE = 3


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-id", required=True, help="Saved run whose unclassified_findings.json to audit.")
    parser.add_argument("--source-output-root", default="outputs/runs")
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    parser.add_argument("--output", required=True, help="Where to write the audit JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.top_n <= 0:
        print("ERROR: --top-n must be a positive integer.", file=sys.stderr)
        return EXIT_INVALID_ARGS

    payload = load_json_record_if_exists(args.run_id, ARTIFACT_FILENAME, output_root=args.source_output_root)
    if not isinstance(payload, dict) or not isinstance(payload.get("findings"), list):
        print(
            f"ERROR: {ARTIFACT_FILENAME} not found or malformed for run {args.run_id!r} "
            f"under {args.source_output_root!r}.",
            file=sys.stderr,
        )
        return EXIT_SOURCE_UNAVAILABLE

    audit = build_neutral_unclassified_audit(payload, top_n=args.top_n)
    audit["generated_at"] = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    audit["source_artifact_path"] = str(Path(args.source_output_root) / args.run_id / ARTIFACT_FILENAME)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"neutral_unclassified_audit written to: {output_path}")
    print(f"run_id={audit['run_id']} ticker={audit['ticker']} audited_count={audit['audited_count']}")
    print(f"matches_source_artifact_total_count={audit['audited_count_matches_source_artifact']}")
    print("provider_calls=0 tradingagents_calls=0")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
