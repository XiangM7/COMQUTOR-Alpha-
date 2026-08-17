"""CLI for the two explicit Provider-zero replay modes.

Example::

    python -m comqutor_alpha.replay --source-run-id 61f3e019-... \
        --mode EXACT_SEMANTIC_REPLAY
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from comqutor_alpha.replay.exact_semantic import run_exact_semantic_replay
from comqutor_alpha.replay.modes import ReplayMode
from comqutor_alpha.replay.pipeline import (
    DEFAULT_REPLAY_OUTPUT_ROOT,
    DEFAULT_SOURCE_OUTPUT_ROOT,
    ReplaySourceIncompleteError,
    run_structure_replay,
)
from comqutor_alpha.replay.source_bundle import ExactReplayError

_LEGACY_RAW_MODE_ALIAS = "structure-only"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m comqutor_alpha.replay",
        description="Run Exact Semantic Replay from saved semantic decisions, or the "
        "separate raw-rebuild diagnostic. Neither mode invokes a Provider.",
    )
    parser.add_argument("--source-run-id", required=True, help="The completed run to replay.")
    parser.add_argument(
        "--mode",
        default=_LEGACY_RAW_MODE_ALIAS,
        choices=[
            _LEGACY_RAW_MODE_ALIAS,
            ReplayMode.EXACT_SEMANTIC_REPLAY.value,
            ReplayMode.RAW_REBUILD_DIAGNOSTIC.value,
        ],
        help="Explicit replay mode; structure-only remains a compatibility alias for raw rebuild.",
    )
    parser.add_argument(
        "--output-root",
        default=DEFAULT_REPLAY_OUTPUT_ROOT,
        help=f"Where to write the new replay run directory (default: {DEFAULT_REPLAY_OUTPUT_ROOT}).",
    )
    parser.add_argument(
        "--source-output-root",
        default=DEFAULT_SOURCE_OUTPUT_ROOT,
        help=f"Where the source run lives (default: {DEFAULT_SOURCE_OUTPUT_ROOT}).",
    )
    parser.add_argument("--replay-run-id", default=None, help="Override the generated replay_run_id.")
    parser.add_argument(
        "--no-persist", dest="persist", action="store_false", help="Compute the replay but do not write files."
    )
    parser.add_argument(
        "--comparison",
        dest="comparison",
        action="store_true",
        default=True,
        help="Build replay_comparison.json against the source run's existing artifacts (default).",
    )
    parser.add_argument(
        "--no-comparison", dest="comparison", action="store_false", help="Skip building the comparison artifact."
    )
    parser.add_argument(
        "--ticker",
        default=None,
        help="Verification only: asserts the source run's ticker matches; never changes the source ticker.",
    )
    parser.add_argument(
        "--strict",
        dest="strict",
        action="store_true",
        default=True,
        help="Exit non-zero if the replay status is not 'completed' (default).",
    )
    parser.add_argument("--no-strict", dest="strict", action="store_false")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    exact_mode = args.mode == ReplayMode.EXACT_SEMANTIC_REPLAY.value
    try:
        if exact_mode:
            result = run_exact_semantic_replay(
                Path(args.source_output_root) / args.source_run_id,
                args.output_root,
                replay_id=args.replay_run_id,
                persist=args.persist,
            )
        else:
            result = run_structure_replay(
                args.source_run_id,
                source_output_root=args.source_output_root,
                replay_output_root=args.output_root,
                replay_run_id=args.replay_run_id,
                persist=args.persist,
                comparison=args.comparison,
            )
    except ReplaySourceIncompleteError as exc:
        print(json.dumps({"status": "REPLAY_SOURCE_INCOMPLETE", "error": str(exc)}, indent=2))
        return 2
    except ExactReplayError as exc:
        print(
            json.dumps(
                {
                    "status": "EXACT_SEMANTIC_REPLAY_BLOCKED",
                    "reason_code": exc.reason_code,
                    "artifact": exc.artifact,
                },
                indent=2,
            )
        )
        return 2

    payload = result.to_dict()

    if args.ticker:
        # Verification only -- confirms the source run matches the ticker the
        # caller expects; never changes source_ticker or the source run itself.
        from comqutor_alpha.storage.file_store import load_json_record

        source_metadata = load_json_record(
            args.source_run_id, "metadata.json", output_root=args.source_output_root
        )
        actual_ticker = str(source_metadata.get("ticker") or "").upper()
        if actual_ticker != str(args.ticker).upper():
            print(
                json.dumps(
                    {
                        "status": "TICKER_MISMATCH",
                        "expected": str(args.ticker).upper(),
                        "actual": actual_ticker,
                    },
                    indent=2,
                )
            )
            return 3

    if not exact_mode and payload.get("comparison"):
        comp = payload["comparison"]
        summary = {
            "source_run_id": payload["source_run_id"],
            "replay_run_id": payload["replay_run_id"],
            "status": payload["status"],
            "source_artifact_hash_unchanged": payload["source_raw_sha256_before"] == payload["source_raw_sha256_after"],
            "claim_count_before": comp["before_claim_count"],
            "claim_count_after": comp["after_claim_count"],
            "factor_count_before": comp["before_factor_count"],
            "factor_count_after": comp["after_factor_count"],
            "candidate_edges_before": comp["before_candidate_edge_count"],
            "candidate_edges_after": comp["after_candidate_edge_count"],
            "admitted_edges_before": comp["before_admitted_edge_count"],
            "admitted_edges_after": comp["after_admitted_edge_count"],
            "activation_count_before": comp["before_activation_count"],
            "activation_count_after": comp["after_activation_count"],
            "conflict_count_after": comp["after_conflict_count"],
            "provider_calls": (
                payload["tradingagents_calls"]
                + payload["llm_provider_calls"]
                + payload["market_data_provider_calls"]
            ),
            "output_path": payload["output_dir"],
        }
        print(json.dumps(summary, indent=2))
    else:
        print(json.dumps(payload, indent=2))

    if args.strict and result.status != "completed":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
