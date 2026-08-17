#!/usr/bin/env python3
"""Sprint 3, Track J3: export the independent-LLM blind review packet and
its comparison reference from the existing, already-verified 50-row
Evidence review sample.

    python scripts/export_j3_llm_review_packet.py

Export-only: never executes a new LLM review, never modifies any stance,
never re-samples. Writes:

    docs/audit_artifacts/j3_llm_blind_review_packet.json
    docs/audit_artifacts/j3_llm_comparison_reference.json
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.evaluation.j3_review_packet_export import (  # noqa: E402
    J3SourceSampleMismatchError,
    export_j3_review_packets,
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    try:
        summary = export_j3_review_packets(created_at=_utc_now_iso())
    except J3SourceSampleMismatchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"source_sample_path: {summary['source_sample_path']}")
    print(f"source_sample_sha256: {summary['source_sample_sha256']}")
    print(f"stance_comparison_path: {summary['stance_comparison_path']}")
    print(f"stance_comparison_sha256: {summary['stance_comparison_sha256']}")
    print(f"row_count: {summary['row_count']}")
    print(f"historical_summary: {summary['historical_summary']}")
    print(f"blind_packet_output_path: {summary['blind_packet_output_path']}")
    print(f"comparison_reference_output_path: {summary['comparison_reference_output_path']}")
    print("provider_calls=0 tradingagents_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
