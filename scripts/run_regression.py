#!/usr/bin/env python3
"""A4 Regression Runner CLI (task A4_REGRESSION_RUNNER + J2_PROVISIONAL_LABELS).

    python scripts/run_regression.py --tickers NVDA QQQ MSFT SNDK TSM AMD

Reprocesses each ticker's most recent qualified saved run through the
existing, zero-Provider Architecture Replay path, compares the result
against J2's provisional labels, and writes
``outputs/regression/regression_report.json``.

Never starts the API or frontend. Never calls a Provider or TradingAgents
(this is Architecture Replay's own structural guarantee, independently
re-verified in the printed summary). Never runs LLM-driven analysis.

Exit code policy (task section 14 -- documented here, never silent):
  0   every requested ticker's regression evaluation ran to completion.
      This includes a "coverage_partial" run (one or more tickers had no
      qualified saved run, or a provisional expectation mismatch) --
      exit 0 there is NOT a silent pass: check
      ``overall_execution_status``/``six_ticker_live_coverage`` in the
      printed summary and the report file. A J2 provisional
      expected-vs-detected mismatch alone NEVER changes the exit code.
  2   invalid CLI arguments (unknown ticker, empty --tickers).
  3   the J2 label file failed to load/validate (LabelValidationError).
  4   the runner crashed, or any ticker's ticker-consistency check
      reported "fail", or a replayed run's own artifact integrity check
      failed (source raw artifact hash changed, or Architecture Replay's
      own identity-consistency guard blocked the replay).
  5   --labels-v2 was given but failed to load/validate.
  6   --semantic-benchmark was given but failed to load, or its
      comparison did not reproduce the historically-recorded J3-vs-B1-LLM-
      vs-deterministic numbers (J3SemanticComparisonMismatchError) --
      never silently reported as if it had.

--labels-v2/--semantic-benchmark are both opt-in and independent of
--tickers/--label-path: a v0.2 required_conflicts miss still never
overrides v0.1's own exit-code policy above by itself (task section 9's
"required miss -> fail" is a *report* status, evaluated per the
run_bound_expectations task section 7 defines -- it does not, on its
own, invent a new v0.1 exit-code trigger beyond the ones already listed).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.evaluation.j3_semantic_benchmark import (  # noqa: E402
    J3BenchmarkValidationError,
    load_j3_semantic_benchmark,
)
from comqutor_alpha.regression.evaluation_contract import apply_v2_contract  # noqa: E402
from comqutor_alpha.regression.evaluator import evaluate_ticker  # noqa: E402
from comqutor_alpha.regression.labels import (  # noqa: E402
    LabelValidationError,
    load_j2_labels,
    ticker_label,
)
from comqutor_alpha.regression.labels_v2 import (  # noqa: E402
    LabelV2ValidationError,
    load_j2_labels_v2,
    ticker_label_v2,
)
from comqutor_alpha.regression.report import (  # noqa: E402
    DEFAULT_REPORT_PATH,
    build_regression_report,
    write_regression_report,
)
from comqutor_alpha.regression.run_selection import select_run_for_ticker  # noqa: E402
from comqutor_alpha.regression.semantic_benchmark import (  # noqa: E402
    J3SemanticComparisonMismatchError,
    compare_j3_benchmark,
    load_stance_comparison_rows,
)

# Task section 14: "当前第一批只支持六个 ticker" -- the first-batch
# allowlist. An unrecognized ticker is a clear CLI error, never silently
# skipped or silently evaluated with no label.
SUPPORTED_TICKERS = ("NVDA", "QQQ", "MSFT", "SNDK", "TSM", "AMD")

EXIT_OK = 0
EXIT_INVALID_ARGS = 2
EXIT_LABEL_INVALID = 3
EXIT_RUNNER_FAILURE = 4
EXIT_LABEL_V2_INVALID = 5
EXIT_SEMANTIC_BENCHMARK_INVALID = 6

DEFAULT_REPLAY_OUTPUT_ROOT = str(REPO_ROOT / "outputs" / "regression" / "replays")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        required=True,
        metavar="TICKER",
        help=f"Tickers to regression-test. Supported (first batch): {', '.join(SUPPORTED_TICKERS)}.",
    )
    parser.add_argument(
        "--label-path",
        default=None,
        help="Override path to the J2 label YAML (default: comqutor_alpha/config/j2_provisional_regression_labels_v0.1.yaml).",
    )
    parser.add_argument(
        "--source-output-root",
        default="outputs/runs",
        help="Root directory of saved runs to select from (default: outputs/runs).",
    )
    parser.add_argument(
        "--replay-output-root",
        default=DEFAULT_REPLAY_OUTPUT_ROOT,
        help="Independent regression workspace Architecture Replay writes fresh reprocessed artifacts into "
        "(default: outputs/regression/replays). Never the source run's own directory.",
    )
    parser.add_argument(
        "--report-path",
        default=str(DEFAULT_REPORT_PATH),
        help=f"Where to write regression_report.json (default: {DEFAULT_REPORT_PATH}).",
    )
    parser.add_argument(
        "--labels-v2",
        default=None,
        metavar="PATH",
        help=(
            "Explicit opt-in: path to a J2 v0.2 evaluation-contract label file "
            "(e.g. comqutor_alpha/config/j2_provisional_regression_labels_v0.2.yaml). "
            "When given, the report gains an additive evaluation_contract block "
            "(required/conditional/product_decision_pending/not_evaluable per ticker), "
            "layered on top of the same v0.1 --label-path run -- v0.1 behavior and "
            "exit-code policy are unchanged either way. Omitting this flag never "
            "silently switches the default label version; the report always states "
            "the exact label_version(s) actually used."
        ),
    )
    parser.add_argument(
        "--semantic-benchmark",
        default=None,
        metavar="PATH",
        help=(
            "Explicit opt-in: path to the J3 provisional semantic benchmark JSON "
            "(e.g. comqutor_alpha/config/j3_provisional_semantic_benchmark_v0.1.json). "
            "When given, the report gains an additive semantic_benchmark block "
            "(independent-J3-vs-B1-LLM-vs-deterministic comparison). This is a "
            "fixed, offline, 50-row comparison -- independent of --tickers and of "
            "which saved runs are available -- never a new Provider call."
        ),
    )
    return parser.parse_args(argv)


def _normalize_tickers(raw_tickers: list[str]) -> tuple[list[str], list[str]]:
    """Uppercases, dedupes (reporting duplicates), and returns
    (normalized_unique_tickers, duplicate_tickers_reported)."""
    seen: list[str] = []
    duplicates: list[str] = []
    for raw in raw_tickers:
        normalized = str(raw).strip().upper()
        if normalized in seen:
            duplicates.append(normalized)
            continue
        seen.append(normalized)
    return seen, duplicates


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    tickers, duplicates = _normalize_tickers(args.tickers)
    if duplicates:
        print(f"NOTE: duplicate --tickers arguments ignored after first occurrence: {duplicates}", file=sys.stderr)
    if not tickers:
        print("ERROR: --tickers must name at least one ticker.", file=sys.stderr)
        return EXIT_INVALID_ARGS
    unknown = [t for t in tickers if t not in SUPPORTED_TICKERS]
    if unknown:
        print(
            f"ERROR: unsupported ticker(s) {unknown}. First-batch supported tickers: {list(SUPPORTED_TICKERS)}.",
            file=sys.stderr,
        )
        return EXIT_INVALID_ARGS

    try:
        labels = load_j2_labels(args.label_path)
    except LabelValidationError as exc:
        print(f"ERROR: J2 label file failed to load/validate: {exc.reason_code} {exc.detail}", file=sys.stderr)
        return EXIT_LABEL_INVALID

    undeclared = labels.get("undeclared_conflict_pairs") or {}
    for ticker, pairs in undeclared.items():
        print(
            f"NOTE: PREDICTED_CONFLICT_PAIR_NOT_DECLARED for {ticker}: {pairs} "
            "(not in the canonical conflict taxonomy -- kept in labels, real taxonomy result reported as-is).",
            file=sys.stderr,
        )

    # --labels-v2: explicit opt-in only -- the default label version never
    # silently changes (task section 11).
    labels_v2 = None
    if args.labels_v2:
        try:
            labels_v2 = load_j2_labels_v2(args.labels_v2)
        except LabelV2ValidationError as exc:
            print(f"ERROR: J2 v0.2 label file failed to load/validate: {exc.reason_code} {exc.detail}", file=sys.stderr)
            return EXIT_LABEL_V2_INVALID
        print(f"labels_v2_loaded: {labels_v2.get('label_version')} ({args.labels_v2})")

    # --semantic-benchmark: explicit opt-in only, independent of --tickers.
    semantic_benchmark_report = None
    if args.semantic_benchmark:
        try:
            benchmark = load_j3_semantic_benchmark(Path(args.semantic_benchmark))
            stance_rows = load_stance_comparison_rows()
            comparison = compare_j3_benchmark(benchmark, stance_rows)
        except (J3BenchmarkValidationError, J3SemanticComparisonMismatchError) as exc:
            print(f"ERROR: J3 semantic benchmark failed to load/compare: {exc}", file=sys.stderr)
            return EXIT_SEMANTIC_BENCHMARK_INVALID
        semantic_benchmark_report = {
            "benchmark_version": "v0.1",
            "benchmark_path": str(args.semantic_benchmark),
            "authority": benchmark.get("authority"),
            "human_review_performed": benchmark.get("human_review_performed"),
            "john_approved": benchmark.get("john_approved"),
            "row_count": benchmark.get("row_count"),
            "comparison": comparison,
        }
        print(
            f"semantic_benchmark_loaded: row_count={benchmark.get('row_count')} "
            f"vs_b1_llm_agreement={comparison['independent_vs_b1_llm_agreement_count']}/{comparison['row_count']} "
            f"vs_deterministic_agreement={comparison['independent_vs_deterministic_agreement_count']}/{comparison['row_count']}"
        )

    exposures_by_ticker: dict[str, dict] = {}
    try:
        import yaml

        exposure_seed_path = REPO_ROOT / "comqutor_alpha" / "config" / "entity_alpha_exposure_seed_v0.1.yaml"
        if exposure_seed_path.exists():
            exposures_by_ticker = yaml.safe_load(exposure_seed_path.read_text(encoding="utf-8")) or {}
    except Exception:
        exposures_by_ticker = {}

    results: list[dict] = []
    contract_results: list[dict] = []
    runner_failure = False
    for ticker in tickers:
        label_block = ticker_label(labels, ticker)
        selection = select_run_for_ticker(ticker, args.source_output_root)
        try:
            result = evaluate_ticker(
                ticker,
                selection,
                label_block,
                source_output_root=args.source_output_root,
                replay_output_root=args.replay_output_root,
                exposure_seed_for_ticker=exposures_by_ticker.get(ticker),
            )
        except Exception as exc:  # noqa: BLE001 -- a crash is a reportable, nonzero-exit condition, never silent
            result = {
                "ticker": ticker,
                "run_id": selection.get("run_id"),
                "run_selection_status": selection.get("run_selection_status"),
                "crashed": True,
                "crash_reason": f"{type(exc).__name__}: {exc}",
            }
            runner_failure = True

        if result.get("ticker_consistency") == "fail":
            runner_failure = True
        if result.get("artifact_hashes", {}).get("source_raw_artifact_unchanged") is False:
            runner_failure = True

        results.append(result)
        print(
            f"{ticker}: run_id={result.get('run_id')} "
            f"run_selection_status={result.get('run_selection_status')} "
            f"offline_reprocess_status={result.get('offline_reprocess_status')} "
            f"main_conflict_match={result.get('main_conflict_match')}"
        )

        # v0.2 contract application never changes `result` or `runner_failure`
        # above -- it only re-interprets the already-computed result (task
        # section 9). A required-conflict "fail" is a report-level status,
        # not a v0.1 exit-code trigger (see module docstring).
        if labels_v2 is not None:
            contract_results.append(
                apply_v2_contract(
                    ticker=ticker,
                    ticker_v2_label=ticker_label_v2(labels_v2, ticker),
                    evaluate_ticker_result=result,
                )
            )

    evaluation_contract_report = None
    if labels_v2 is not None:
        required_by_ticker = {
            r["ticker"]: r["required_conflict_results"] for r in contract_results if r["required_conflict_results"]
        }
        conditional_by_ticker = {
            r["ticker"]: r["conditional_conflict_results"]
            for r in contract_results
            if r["conditional_conflict_results"]
        }
        pending_by_ticker = {
            r["ticker"]: r["product_decision_pending_results"]
            for r in contract_results
            if r["product_decision_pending_results"]
        }
        not_evaluable_by_ticker = {
            r["ticker"]: {
                "reason": "run not selected/completed, or artifact_completeness != pass",
                "artifact_completeness": r["artifact_completeness"],
            }
            for r in contract_results
            if r["evaluation_status"] == "not_evaluable"
        }
        evaluation_contract_report = {
            "j2_label_version": labels_v2.get("label_version"),
            "required": required_by_ticker,
            "conditional": conditional_by_ticker,
            "product_decision_pending": pending_by_ticker,
            "not_evaluable": not_evaluable_by_ticker,
            "ticker_results": contract_results,
        }
        evaluated_count = sum(1 for r in contract_results if r["evaluation_status"] == "evaluated")
        required_fail_tickers = [r["ticker"] for r in contract_results if r["ticker_status"] == "fail"]
        print(
            f"evaluation_contract_applied: label_version={labels_v2.get('label_version')} "
            f"evaluated={evaluated_count}/{len(contract_results)} "
            f"required_conflict_fail_tickers={required_fail_tickers}"
        )

    report = build_regression_report(
        tickers_requested=tickers,
        label_version=labels.get("label_version"),
        label_status=labels.get("status"),
        evaluation_mode=labels.get("evaluation_mode"),
        results=results,
        undeclared_conflict_pairs=undeclared,
        semantic_benchmark=semantic_benchmark_report,
        evaluation_contract=evaluation_contract_report,
    )
    report_path = write_regression_report(report, args.report_path)
    print(f"regression_report.json written to: {report_path}")

    total_provider_calls = report["provider_calls"]
    total_tradingagents_calls = report["tradingagents_calls"]
    print(f"provider_calls={total_provider_calls} tradingagents_calls={total_tradingagents_calls}")
    print(f"overall_execution_status={report['overall_execution_status']} six_ticker_live_coverage={report['six_ticker_live_coverage']}")

    if runner_failure:
        return EXIT_RUNNER_FAILURE
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
