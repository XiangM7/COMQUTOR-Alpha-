"""Cross-run Evaluation Harness CLI entry point.

    python -m comqutor_alpha.evaluation.cross_run \\
        --manifest evaluation/manifests/mvp_cases.yaml \\
        --output-dir outputs/evaluations/<evaluation_id>

Purely offline: never calls a Provider, never re-runs TradingAgents, never
mutates a source run or golden-case bundle. Exits non-zero when any
completed case has a failed *required* (non-manual) expectation.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from comqutor_alpha.evaluation.golden_case import GoldenCase, GoldenCaseError, load_golden_case
from comqutor_alpha.evaluation.metrics import aggregate_cross_run_metrics
from comqutor_alpha.evaluation.policy import load_policy
from comqutor_alpha.evaluation.runner import STATUS_PENDING_FIXTURE, CaseResult, run_case

EVALUATION_SCHEMA_VERSION = "comqutor_alpha.evaluation.cross_run.v1"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_evaluation_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"eval-{stamp}-{uuid4().hex[:8]}"


def load_manifest(manifest_path: Path) -> list[dict[str, Any]]:
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    cases = raw.get("cases") if isinstance(raw, dict) else None
    if not isinstance(cases, list):
        raise ValueError(f"MANIFEST_INVALID: {manifest_path} has no top-level 'cases' list")
    return cases


def _resolve_case(entry: dict[str, Any]) -> tuple[GoldenCase | None, CaseResult | None]:
    case_id = str(entry.get("case_id") or "")
    case_dir_raw = entry.get("case_dir")
    if not case_dir_raw:
        return None, CaseResult(
            case_id=case_id or "UNKNOWN",
            case_type=str(entry.get("case_type") or "unknown"),
            ticker=str(entry.get("ticker") or ""),
            status=STATUS_PENDING_FIXTURE,
            skipped_reason="MANIFEST_ENTRY_MISSING_CASE_DIR",
        )
    case_dir = Path(case_dir_raw)
    if not case_dir.exists():
        return None, CaseResult(
            case_id=case_id or case_dir.name,
            case_type=str(entry.get("case_type") or "unknown"),
            ticker=str(entry.get("ticker") or ""),
            status=STATUS_PENDING_FIXTURE,
            skipped_reason=f"GOLDEN_CASE_BUNDLE_NOT_PRESENT: {case_dir}",
        )
    try:
        case = load_golden_case(case_dir)
    except GoldenCaseError as exc:
        return None, CaseResult(
            case_id=case_id or case_dir.name,
            case_type=str(entry.get("case_type") or "unknown"),
            ticker=str(entry.get("ticker") or ""),
            status=STATUS_PENDING_FIXTURE,
            skipped_reason=str(exc),
        )
    return case, None


def run_evaluation(
    manifest_path: Path, output_dir: Path, *, policy_path: Path | None = None
) -> tuple[list[CaseResult], dict[str, Any]]:
    entries = load_manifest(manifest_path)
    policy = load_policy(policy_path) if policy_path else load_policy()

    results: list[CaseResult] = []
    for entry in entries:
        case, skipped_result = _resolve_case(entry)
        if skipped_result is not None:
            results.append(skipped_result)
            continue
        assert case is not None
        results.append(run_case(case, evaluation_output_root=str(output_dir)))

    metrics = aggregate_cross_run_metrics(results)
    metrics["policy_violations"] = policy.evaluate_operational_gates(metrics["operational"])
    return results, metrics


def write_outputs(output_dir: Path, evaluation_id: str, results: list[CaseResult], metrics: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    failed_required = [r for r in results if r.status == "completed" and not r.required_expectations_passed]
    total_provider_calls = sum(r.provider_calls for r in results)

    summary = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "evaluation_id": evaluation_id,
        "generated_at": _utc_now_iso(),
        "case_count": len(results),
        "cases_completed": sum(1 for r in results if r.status == "completed"),
        "cases_pending_fixture": sum(1 for r in results if r.status == STATUS_PENDING_FIXTURE),
        "cases_blocked": sum(1 for r in results if r.status == "blocked"),
        "cases_failed": sum(1 for r in results if r.status == "error"),
        "cases_with_failed_required_expectations": len(failed_required),
        "provider_calls": total_provider_calls,
        "source_artifacts_changed": False,
        "metrics": metrics,
    }
    (output_dir / "evaluation_summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

    case_dicts = [r.to_dict() for r in results]
    (output_dir / "case_results.json").write_text(json.dumps(case_dicts, indent=2, default=str) + "\n", encoding="utf-8")

    csv_path = output_dir / "case_results.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["case_id", "case_type", "ticker", "status", "required_expectations_passed", "skipped_reason", "error"])
        for r in results:
            writer.writerow(
                [
                    r.case_id,
                    r.case_type,
                    r.ticker,
                    r.status,
                    r.required_expectations_passed if r.status == "completed" else "",
                    r.skipped_reason or "",
                    r.error or "",
                ]
            )

    failures = [
        {
            "case_id": r.case_id,
            "status": r.status,
            "skipped_reason": r.skipped_reason,
            "error": r.error,
            "failed_expectations": [e.to_dict() for e in r.expectation_results if not e.passed and not e.manual],
        }
        for r in results
        if r.status != "completed" or not r.required_expectations_passed
    ]
    (output_dir / "failures.json").write_text(json.dumps(failures, indent=2, default=str) + "\n", encoding="utf-8")

    report_lines = [
        f"# Cross-run Evaluation Report ({evaluation_id})",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "## Operational correctness",
        f"- Cases: {summary['case_count']} total, {summary['cases_completed']} completed, "
        f"{summary['cases_pending_fixture']} pending_fixture, {summary['cases_blocked']} blocked, "
        f"{summary['cases_failed']} error",
        f"- Provider calls: {summary['provider_calls']} (must be 0)",
        f"- Policy violations: {metrics.get('policy_violations') or 'none'}",
        "",
        "## Structural correctness (per case, from expected.yaml)",
    ]
    for r in results:
        if r.status != "completed":
            report_lines.append(f"- {r.case_id}: SKIPPED ({r.status}: {r.skipped_reason or r.error})")
            continue
        status_label = "PASS" if r.required_expectations_passed else "FAIL"
        report_lines.append(f"- {r.case_id}: {status_label} ({len(r.expectation_results)} expectation(s) checked)")
        for expectation in r.expectation_results:
            if not expectation.passed and not expectation.manual:
                report_lines.append(f"    - FAILED {expectation.name}: {expectation.detail}")
    report_lines += [
        "",
        "## Semantic/domain correctness",
        "Not automatically verified by this harness -- see any `manual_review` expectations above",
        "and each case's own `manual_claim_labels.csv` (when present). A passing structural check",
        "is evidence the pipeline behaved consistently, not a claim that the investment thesis is",
        "correct.",
        "",
        "## Manually unverified expectations",
    ]
    manual_found = False
    for r in results:
        for expectation in r.expectation_results:
            if expectation.manual:
                manual_found = True
                report_lines.append(f"- {r.case_id}: {expectation.name}")
    if not manual_found:
        report_lines.append("- none declared")

    (output_dir / "evaluation_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="COMQUTOR offline cross-run evaluation harness")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--policy", type=Path, default=None)
    args = parser.parse_args(argv)

    evaluation_id = new_evaluation_id()
    results, metrics = run_evaluation(args.manifest, args.output_dir, policy_path=args.policy)
    write_outputs(args.output_dir, evaluation_id, results, metrics)

    failed_required = [r for r in results if r.status == "completed" and not r.required_expectations_passed]
    policy_violations = metrics.get("policy_violations") or []
    if failed_required or policy_violations:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["main", "run_evaluation", "write_outputs", "load_manifest", "new_evaluation_id", "EVALUATION_SCHEMA_VERSION"]
