#!/usr/bin/env python3
"""Sprint 2, Track J3 CLI: export a deterministic, stratified, 50-Evidence
human review sample.

Example:
    python scripts/export_evidence_review_sample.py \\
        --tickers NVDA QQQ MSFT SNDK TSM AMD \\
        --count 50 \\
        --output docs/evidence_review_sample.csv

Offline only: uses Architecture Replay (comqutor_alpha.replay.pipeline) to
build/reuse an artifact-complete bundle per ticker -- zero Provider/LLM/DB
calls. Re-running the exact same command reuses the already-produced
replay bundles and produces a byte-identical CSV (see
comqutor_alpha.evaluation.evidence_review_sample.SAMPLING_VERSION's stable
hash-based ordering).
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comqutor_alpha.evaluation.evidence_review_sample import (  # noqa: E402
    DEFAULT_TICKERS,
    DEFAULT_TOTAL_COUNT,
    build_evidence_review_sample,
    write_evidence_review_sample_csv,
    write_evidence_review_sample_manifest,
    write_evidence_review_sample_records_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="+", default=list(DEFAULT_TICKERS))
    parser.add_argument("--count", type=int, default=DEFAULT_TOTAL_COUNT)
    parser.add_argument("--output", default="docs/evidence_review_sample.csv")
    parser.add_argument("--source-output-root", default="outputs/runs")
    parser.add_argument("--replay-output-root", default="outputs/review_sample_replays")
    args = parser.parse_args()

    result = build_evidence_review_sample(
        tickers=tuple(args.tickers),
        count=args.count,
        source_output_root=args.source_output_root,
        replay_output_root=args.replay_output_root,
    )

    csv_path = Path(args.output)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_sha256 = write_evidence_review_sample_csv(result, csv_path)

    records_path = csv_path.with_name(csv_path.stem + "_records.json")
    write_evidence_review_sample_records_json(result, records_path)

    manifest_path = csv_path.with_name(csv_path.stem + "_manifest.json")
    write_evidence_review_sample_manifest(
        result,
        manifest_path,
        csv_sha256=csv_sha256,
        generated_at=dt.datetime.now(dt.timezone.utc).isoformat(),
    )

    print(f"verdict: {result.verdict}")
    print(f"requested_count: {result.requested_count}")
    print(f"actual_count: {result.actual_count}")
    print(f"ticker_distribution: {result.ticker_distribution}")
    print(f"stance_distribution: {result.stance_distribution}")
    print(f"quota_shortfalls: {result.quota_shortfalls}")
    print(f"manual_review_count: {result.manual_review_count}")
    print(f"activation_evidence_count: {result.activation_evidence_count}")
    print(f"conflict_evidence_count: {result.conflict_evidence_count}")
    print(f"csv_sha256: {csv_sha256}")
    print(f"csv: {csv_path}")
    print(f"records: {records_path}")
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
