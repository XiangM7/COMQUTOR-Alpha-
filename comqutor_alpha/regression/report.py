"""``regression_report.json`` builder (task section 13).

Pure assembly: sums the per-ticker counters the evaluator/replay already
computed, decides the overall execution status, and writes the canonical
report file. Never recomputes anything a ticker's own result dict does
not already carry.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "regression_report.v1"
DEFAULT_REPORT_DIR = Path("outputs") / "regression"
DEFAULT_REPORT_PATH = DEFAULT_REPORT_DIR / "regression_report.json"

STATUS_COMPLETE = "complete"
STATUS_COVERAGE_PARTIAL = "coverage_partial"
STATUS_FAILED = "failed"

SIX_TICKER_LIVE_COVERAGE_PARTIAL = "SIX_TICKER_LIVE_COVERAGE_PARTIAL"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True, timeout=10
        )
        return result.stdout.strip()
    except Exception:
        return None


def build_regression_report(
    *,
    tickers_requested: list[str],
    label_version: str,
    label_status: str,
    evaluation_mode: str,
    results: list[dict[str, Any]],
    undeclared_conflict_pairs: dict[str, list[str]] | None = None,
    semantic_benchmark: dict[str, Any] | None = None,
    evaluation_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assembles the canonical top-level report. Provider/TradingAgents
    call totals are summed straight from each result's own already-tracked
    counters (Architecture Replay's own ``ReplayResult`` fields) -- never
    independently re-counted.

    ``semantic_benchmark``/``evaluation_contract`` are purely additive
    (task J3_SEMANTIC_BENCHMARK_INTEGRATION section 10): omitting either
    (the default) reproduces the exact pre-v0.2 report shape byte-for-byte
    -- an old consumer that has never heard of these two keys is
    unaffected. Never used to disguise ``provisional``/``conditional``/
    ``unresolved``/``not_evaluable`` as ``approved``/``pass``/``golden``;
    callers must pass through whatever honest status the evaluator/
    benchmark comparison already computed."""
    provider_calls = sum(int(r.get("provider_calls") or 0) for r in results)
    tradingagents_calls = sum(int(r.get("tradingagents_calls") or 0) for r in results)

    not_selected = [r for r in results if r.get("run_selection_status") != "selected"]
    not_completed = [
        r
        for r in results
        if r.get("run_selection_status") == "selected" and r.get("offline_reprocess_status") != "completed"
    ]
    crashed = any(r.get("crashed") for r in results)

    if crashed:
        overall_status = STATUS_FAILED
    elif not_selected or not_completed:
        overall_status = STATUS_COVERAGE_PARTIAL
    else:
        overall_status = STATUS_COMPLETE

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "head": _git("rev-parse", "HEAD"),
        "tickers_requested": tickers_requested,
        "label_version": label_version,
        "label_status": label_status,
        "evaluation_mode": evaluation_mode,
        "provider_calls": provider_calls,
        "tradingagents_calls": tradingagents_calls,
        "overall_execution_status": overall_status,
        "six_ticker_live_coverage": (
            SIX_TICKER_LIVE_COVERAGE_PARTIAL if (not_selected or not_completed) else "complete"
        ),
        "undeclared_conflict_pairs": undeclared_conflict_pairs or {},
        "formal_product_owner_acceptance": "pending",
        "results": results,
    }
    if semantic_benchmark is not None:
        report["semantic_benchmark"] = semantic_benchmark
    if evaluation_contract is not None:
        report["evaluation_contract"] = evaluation_contract
    return report


def write_regression_report(report: dict[str, Any], path: str | Path = DEFAULT_REPORT_PATH) -> Path:
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return resolved


__all__ = [
    "SCHEMA_VERSION",
    "DEFAULT_REPORT_PATH",
    "STATUS_COMPLETE",
    "STATUS_COVERAGE_PARTIAL",
    "STATUS_FAILED",
    "SIX_TICKER_LIVE_COVERAGE_PARTIAL",
    "build_regression_report",
    "write_regression_report",
]
