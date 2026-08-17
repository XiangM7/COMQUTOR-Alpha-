#!/usr/bin/env python3
"""Phase 1B.1 — Controlled Real-Provider Shadow Smoke CLI.

Runs at most 4 real-Provider Shadow calls (one report per Agent family:
fundamental, news, sentiment, technical) against a deterministically
selected single ticker from the Phase 1A evaluation corpus, through the
frozen ``structured_adapter.claim_extraction_shadow.v1`` prompt.

Never invoked automatically; never invokes a Provider unless every one of
these is true:

- ``--execute-provider-smoke`` is passed,
- ``--research-profile``, ``--max-provider-calls`` (<=4), and
  ``--output-dir`` are all supplied,
- the environment variable ``COMQUTOR_PHASE1B1_PROVIDER_SMOKE_APPROVED`` is
  exactly the string ``"true"``.

This script never reads that variable's absence as an error to work around,
never infers authorization from ``COMQUTOR_WEEK2_LLM_ENABLED``, and never
sets the approval variable itself. When any authorization input is missing,
it performs zero Provider calls and reports a stable ``BLOCKED_*`` status.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.llm_runtime.cache import NullLLMResponseCache  # noqa: E402
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession  # noqa: E402
from comqutor_alpha.research_profiles import (  # noqa: E402
    ResearchProfileError,
    get_research_profile,
)
from comqutor_alpha.structure_engine.factor_normalizer import FACTOR_ALIASES  # noqa: E402
from comqutor_alpha.structure_engine.structured_output_adapter import (  # noqa: E402
    adapt_raw_agent_outputs,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt import (  # noqa: E402
    STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
)
from comqutor_alpha.structure_engine.structured_output_shadow_provider import (  # noqa: E402
    ProviderSmokeAuthorizationError,
    build_real_provider_gateway,
    run_real_provider_shadow_smoke_for_report,
)
from comqutor_alpha.structure_engine.structured_output_shadow_replay import (  # noqa: E402
    verify_phase1b1_shadow_exact_replay,
)
from comqutor_alpha.structure_engine.structured_output_shadow_review import (  # noqa: E402
    build_blank_review_rows,
    compare_legacy_and_shadow,
    render_blank_review_csv,
)

EVALUATION_CORPUS_PATH = REPO_ROOT / "docs/audit_artifacts/phase1a/evaluation_corpus_inventory.json"
TARGET_FAMILY_ORDER = ("fundamental", "news", "sentiment", "technical")
APPROVAL_ENV_VAR = "COMQUTOR_PHASE1B1_PROVIDER_SMOKE_APPROVED"
MAX_LOGICAL_CALLS = 4

BLOCKED_PROVIDER_SMOKE_NOT_AUTHORIZED = "BLOCKED_PROVIDER_SMOKE_NOT_AUTHORIZED"
BLOCKED_RESEARCH_PROFILE_INVALID = "BLOCKED_RESEARCH_PROFILE_INVALID"
BLOCKED_OUTPUT_DIRECTORY_INVALID = "BLOCKED_OUTPUT_DIRECTORY_INVALID"
BLOCKED_PROVIDER_CREDENTIALS_MISSING = "BLOCKED_PROVIDER_CREDENTIALS_MISSING"
BLOCKED_PROVIDER_UNAVAILABLE = "BLOCKED_PROVIDER_UNAVAILABLE"
FAIL_PROVIDER_CALL_LIMIT_EXCEEDED = "FAIL_PROVIDER_CALL_LIMIT_EXCEEDED"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-profile", required=True)
    parser.add_argument("--max-provider-calls", required=True, type=int)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--execute-provider-smoke", action="store_true", default=False)
    return parser.parse_args(argv)


def _validate_output_dir(raw: str) -> Path:
    """Require an unambiguous path under ``outputs/evaluations/`` with no
    traversal/symlink escape, that either does not exist or is empty."""

    candidate = Path(raw)
    resolved = (candidate if candidate.is_absolute() else REPO_ROOT / candidate).resolve()
    allowed_root = (REPO_ROOT / "outputs/evaluations").resolve()
    try:
        resolved.relative_to(allowed_root)
    except ValueError as exc:
        raise ValueError(BLOCKED_OUTPUT_DIRECTORY_INVALID) from exc
    if resolved == allowed_root:
        raise ValueError(BLOCKED_OUTPUT_DIRECTORY_INVALID)
    if resolved.is_symlink():
        raise ValueError(BLOCKED_OUTPUT_DIRECTORY_INVALID)
    if resolved.exists() and (not resolved.is_dir() or any(resolved.iterdir())):
        raise ValueError(BLOCKED_OUTPUT_DIRECTORY_INVALID)
    return resolved


def _load_evaluation_corpus() -> dict[str, Any]:
    return json.loads(EVALUATION_CORPUS_PATH.read_text(encoding="utf-8"))


def select_four_reports(corpus: dict[str, Any]) -> dict[str, Any]:
    """Deterministically select one report per Agent family from a single
    ticker, reusing Phase 1A's own already-deterministic per-slot selection
    (``coverage[*].selected_agent_output_id``) rather than re-deriving a
    second, potentially divergent tie-break rule."""

    coverage_by_ticker: dict[str, dict[str, dict[str, Any]]] = {}
    for entry in corpus.get("coverage") or []:
        ticker = str(entry.get("ticker") or "")
        family = str(entry.get("agent_family") or "")
        coverage_by_ticker.setdefault(ticker, {})[family] = entry

    reports_by_agent_output_id = {
        str(report.get("agent_output_id")): report for report in corpus.get("reports") or []
    }

    exclusion_decisions: list[dict[str, Any]] = []
    for ticker in corpus.get("target_tickers") or []:
        families = coverage_by_ticker.get(ticker, {})
        complete = all(
            families.get(family, {}).get("slot_covered") is True
            and families.get(family, {}).get("target_slot") is True
            for family in TARGET_FAMILY_ORDER
        )
        if not complete:
            exclusion_decisions.append(
                {"ticker": ticker, "excluded": True, "reason": "incomplete_family_coverage"}
            )
            continue

        selected: dict[str, dict[str, Any]] = {}
        for family in TARGET_FAMILY_ORDER:
            agent_output_id = str(families[family].get("selected_agent_output_id") or "")
            report = reports_by_agent_output_id.get(agent_output_id)
            if report is None or not report.get("eligible_for_phase1_shadow"):
                complete = False
                break
            selected[family] = report
        if not complete:
            exclusion_decisions.append(
                {"ticker": ticker, "excluded": True, "reason": "selected_report_not_eligible"}
            )
            continue

        return {
            "selection_algorithm": (
                "First ticker in target_tickers order (NVDA, QQQ, MSFT, SNDK, TSM, AMD) "
                "with all four target Agent families slot_covered=true; per-family report "
                "reused verbatim from Phase 1A evaluation_corpus_inventory.json "
                "coverage[*].selected_agent_output_id (eligible_for_phase1_shadow=true, "
                "required_metadata_exists=true, non-empty, deterministic ascending "
                "source_run_id/agent_output_id/report_path tie-break already applied by "
                "Phase 1A's own corpus scan)."
            ),
            "ticker": ticker,
            "selected_reports": selected,
            "exclusion_decisions": exclusion_decisions,
        }
    raise ValueError("PHASE1B1_NO_TICKER_WITH_COMPLETE_FAMILY_COVERAGE")


def _load_raw_report(run_id: str, agent_output_id: str) -> dict[str, Any]:
    raw_path = REPO_ROOT / "outputs/runs" / run_id / "raw_agent_outputs.json"
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    for entry in payload.get("agent_outputs") or []:
        if str(entry.get("agent_output_id")) == agent_output_id:
            return entry
    raise ValueError(f"PHASE1B1_REPORT_NOT_FOUND_IN_RAW_OUTPUTS:{agent_output_id}")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _write_blocked_result(output_dir: Path, reason: str, *, detail: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        output_dir / "real_provider_smoke_result.json",
        {
            "schema_version": "comqutor.phase1b1.real_provider_smoke_result.v1",
            "generated_at": _now_iso(),
            "status": reason,
            "provider_calls_made": 0,
            "detail": detail,
        },
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    if args.max_provider_calls < 1 or args.max_provider_calls > MAX_LOGICAL_CALLS:
        print(FAIL_PROVIDER_CALL_LIMIT_EXCEEDED)
        return 1

    try:
        output_dir = _validate_output_dir(args.output_dir)
    except ValueError:
        print(BLOCKED_OUTPUT_DIRECTORY_INVALID)
        return 1

    try:
        profile = get_research_profile(args.research_profile)
    except ResearchProfileError:
        print(BLOCKED_RESEARCH_PROFILE_INVALID)
        _write_blocked_result(
            output_dir, BLOCKED_RESEARCH_PROFILE_INVALID, detail={"research_profile": args.research_profile}
        )
        return 1

    corpus = _load_evaluation_corpus()
    selection = select_four_reports(corpus)
    selection_record = {
        "schema_version": "comqutor.phase1b1.smoke_selection.v1",
        "generated_at": _now_iso(),
        "selection_algorithm": selection["selection_algorithm"],
        "ticker": selection["ticker"],
        "exclusion_decisions": selection["exclusion_decisions"],
        "final_four_selected_records": [
            {
                "agent_family": family,
                "agent": report.get("agent"),
                "agent_output_id": report.get("agent_output_id"),
                "source_run_id": report.get("source_run_id"),
                "report_path": report.get("report_path"),
                "report_sha256": report.get("report_sha256"),
                "report_character_count": report.get("report_length"),
            }
            for family, report in selection["selected_reports"].items()
        ],
    }
    print(f"selected ticker: {selection['ticker']}")
    for family, report in selection["selected_reports"].items():
        print(f"  {family}: {report.get('agent_output_id')} ({report.get('report_length')} chars)")

    logical_call_limit = min(args.max_provider_calls, len(selection["selected_reports"]))
    max_provider_attempts = logical_call_limit * 2  # (1 + DEFAULT_MAX_RETRIES), printed precisely below

    approved = os.environ.get(APPROVAL_ENV_VAR, "") == "true"
    print(f"selected research profile: {profile.profile_id} ({profile.display_name})")
    print(f"provider: {profile.llm_provider}")
    print(f"model: {profile.quick_think_llm}")
    print(f"maximum logical calls: {logical_call_limit}")
    print(f"maximum provider attempts (derived): {max_provider_attempts}")
    print("retry policy: Week2LLMGateway default (unchanged)")
    print(f"output directory: {output_dir}")
    print(f"execute-provider-smoke flag: {args.execute_provider_smoke}")
    print(f"{APPROVAL_ENV_VAR} set to 'true': {approved}")

    if not (args.execute_provider_smoke and approved):
        print(BLOCKED_PROVIDER_SMOKE_NOT_AUTHORIZED)
        output_dir.mkdir(parents=True, exist_ok=True)
        _write_json(output_dir / "phase1b1_smoke_selection.json", selection_record)
        _write_blocked_result(
            output_dir,
            BLOCKED_PROVIDER_SMOKE_NOT_AUTHORIZED,
            detail={
                "execute_provider_smoke_flag": args.execute_provider_smoke,
                "approval_env_var_name": APPROVAL_ENV_VAR,
                "approval_env_var_equals_true": approved,
            },
        )
        return 0

    staging_dir = output_dir.parent / f".{output_dir.name}.staging-{uuid.uuid4().hex}"
    staging_dir.mkdir(parents=True, exist_ok=False)
    try:
        _run_authorized_smoke(
            profile=profile,
            selection=selection,
            selection_record=selection_record,
            logical_call_limit=logical_call_limit,
            max_provider_attempts=max_provider_attempts,
            staging_dir=staging_dir,
        )
    except ProviderSmokeAuthorizationError as exc:
        shutil.rmtree(staging_dir, ignore_errors=True)
        status = (
            BLOCKED_PROVIDER_CREDENTIALS_MISSING
            if exc.reason_code == "PHASE1B1_PROVIDER_CLIENT_INITIALIZATION_FAILED"
            else BLOCKED_PROVIDER_UNAVAILABLE
        )
        print(status)
        _write_blocked_result(output_dir, status, detail={"reason_code": exc.reason_code})
        return 0
    except Exception as exc:  # any unexpected failure: never leave a fake-success dir
        shutil.rmtree(staging_dir, ignore_errors=True)
        print(f"FAIL_UNEXPECTED_ERROR:{type(exc).__name__}")
        raise

    os.rename(staging_dir, output_dir)
    print("PHASE_1B_1_PROVIDER_SMOKE: bundle written")
    print(str(output_dir))
    return 0


def _run_authorized_smoke(
    *,
    profile: Any,
    selection: dict[str, Any],
    selection_record: dict[str, Any],
    logical_call_limit: int,
    max_provider_attempts: int,
    staging_dir: Path,
) -> None:
    evaluation_id = f"phase1b1-smoke-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    session = SemanticRuntimeSession(
        run_id=evaluation_id,
        output_directory=staging_dir,
        execution_mode="shadow",
        provider=profile.llm_provider,
        model=profile.quick_think_llm,
        cache=NullLLMResponseCache(),
    )
    gateway, gateway_info = build_real_provider_gateway(
        profile=profile,
        run_id=evaluation_id,
        output_root=staging_dir,
        logical_call_limit=logical_call_limit,
        semantic_runtime=session,
    )

    reports_dir = staging_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    per_report_results: list[dict[str, Any]] = []
    review_rows: list[dict[str, str]] = []

    for call_index, (family, report_meta) in enumerate(selection["selected_reports"].items()):
        if call_index >= logical_call_limit:
            break
        run_id = str(report_meta["source_run_id"])
        agent_output_id = str(report_meta["agent_output_id"])
        raw_record = _load_raw_report(run_id, agent_output_id)
        report_text = str(raw_record.get("raw_output") or "")
        ticker = str(report_meta.get("ticker") or selection["ticker"])
        agent = str(report_meta.get("agent") or raw_record.get("agent") or "")

        legacy_records = adapt_raw_agent_outputs(raw_record, evaluation_id, ticker, llm_gateway=None)

        bundle, invoker, candidate_segments = run_real_provider_shadow_smoke_for_report(
            gateway=gateway,
            source_report=report_text,
            run_id=evaluation_id,
            ticker=ticker,
            agent=agent,
            agent_output_id=agent_output_id,
            factor_vocabulary=list(FACTOR_ALIASES.keys()),
            source_metadata={
                "source_path": raw_record.get("source_path") or "",
                "source_field": raw_record.get("source_field") or "",
                "source_refs": [],
            },
        )
        comparison = compare_legacy_and_shadow(legacy_records, bundle)

        family_dir = reports_dir / family
        family_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            family_dir / "source_report_snapshot.json",
            {
                "run_id": run_id,
                "agent_output_id": agent_output_id,
                "agent": agent,
                "ticker": ticker,
                "report_text": report_text,
                "report_sha256": report_meta.get("report_sha256"),
                "factor_vocabulary": list(FACTOR_ALIASES.keys()),
                "allowed_source_refs": [],
            },
        )
        _write_json(family_dir / "candidate_segments.json", candidate_segments)
        _write_json(family_dir / "shadow_bundle.json", bundle)
        _write_json(
            family_dir / "validation_report.json",
            bundle.get("validation_summary") or {},
        )
        _write_json(family_dir / "legacy_claims_snapshot.json", legacy_records)
        _write_json(family_dir / "legacy_vs_shadow_comparison.json", comparison)

        review_rows.extend(
            build_blank_review_rows(comparison=comparison, legacy_outputs=legacy_records, shadow_bundle=bundle)
        )

        invocation = invoker.last_invocation
        per_report_results.append(
            {
                "agent_family": family,
                "agent_output_id": agent_output_id,
                "provider_status": invocation.provider_status if invocation else "not_called",
                "validation_accepted": invocation.validation_accepted if invocation else False,
                "provider_attempt_count": invocation.provider_attempt_count if invocation else 0,
                "retry_count": invocation.retry_count if invocation else 0,
                "shadow_status": (bundle.get("validation_summary") or {}).get("status"),
                "claim_count": len(bundle.get("claims") or []),
                "abstention_count": len(bundle.get("abstentions") or []),
            }
        )

    manifest_path = session.finalize_manifest(complete=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path else {}

    _write_json(staging_dir / "phase1b1_smoke_selection.json", selection_record)
    _write_json(
        staging_dir / "evaluation_metadata.json",
        {
            "schema_version": "comqutor.phase1b1.evaluation_metadata.v1",
            "evaluation_id": evaluation_id,
            "generated_at": _now_iso(),
            "research_profile_id": gateway_info.research_profile_id,
            "provider": gateway_info.provider,
            "model": gateway_info.model,
            "logical_call_limit": gateway_info.logical_call_limit,
            "max_retries": gateway_info.max_retries,
            "max_provider_attempts": gateway_info.max_provider_attempts,
            "timeout_seconds": gateway_info.timeout_seconds,
            "prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
            "prompt_sha256": STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
            "ticker": selection["ticker"],
            "null_cache": True,
        },
    )
    _write_json(
        staging_dir / "provider_usage_summary.json",
        {
            "schema_version": "comqutor.phase1b1.provider_usage_summary.v1",
            "logical_calls_made": len(per_report_results),
            "provider_attempt_count_total": sum(r["provider_attempt_count"] for r in per_report_results),
            "gateway_call_count": gateway.call_count,
            "max_provider_attempts_allowed": max_provider_attempts,
            "per_report": per_report_results,
            "market_data_calls": 0,
            "redis_connections": 0,
            "database_writes": 0,
        },
    )

    review_csv = render_blank_review_csv(review_rows)
    (staging_dir / "phase1b1_shadow_review.csv").write_text(review_csv, encoding="utf-8")
    (staging_dir / "phase1b1_shadow_review_instructions.md").write_text(
        _review_instructions_text(), encoding="utf-8"
    )

    replay_audit = verify_phase1b1_shadow_exact_replay(staging_dir)
    _write_json(staging_dir / "shadow_exact_replay_audit.json", replay_audit)

    _write_json(
        staging_dir / "artifact_manifest.json",
        {
            "schema_version": "comqutor.phase1b1.artifact_manifest.v1",
            "generated_at": _now_iso(),
            "files": sorted(
                str(p.relative_to(staging_dir)) for p in staging_dir.rglob("*") if p.is_file()
            ),
        },
    )
    _write_json(
        staging_dir / "real_provider_smoke_result.json",
        {
            "schema_version": "comqutor.phase1b1.real_provider_smoke_result.v1",
            "generated_at": _now_iso(),
            "status": "COMPLETED",
            "provider_calls_made": len(per_report_results),
            "semantic_manifest": manifest,
            "replay_final_status": replay_audit.get("final_status"),
        },
    )


def _review_instructions_text() -> str:
    return """# Phase 1B.1 Shadow Review Instructions

## How to view the source report
Open `reports/<family>/source_report_snapshot.json` and read `report_text`
verbatim -- this is the exact untrusted Agent report both Legacy and Shadow
saw.

## How to compare Legacy and Shadow
`reports/<family>/legacy_claims_snapshot.json` holds the current
deterministic Adapter's output for this same report.
`reports/<family>/shadow_bundle.json` holds the real-Provider Shadow
proposal (or a fail-soft bundle if the Provider/validator did not admit
one). `reports/<family>/legacy_vs_shadow_comparison.json` holds navigation
signals only -- never a quality judgment.

## How to fill in `phase1b1_shadow_review.csv`
1. Verify `source_report_sha256` matches the snapshot before reviewing.
2. Pick exactly one `review_dimension` per row (claim_boundary,
   evidence_pairing, semantic_fidelity, entity_extraction,
   factor_extraction, direction, overall_disposition) and one label from
   `structured_output_adapter_review_contract_v1.md`'s allowed set.
3. Mark negation/modality/attribution/temporal issues under
   `semantic_fidelity` using `negation_error`/`modality_error`/
   `attribution_error`/`temporal_error`.
4. Assign `severity` (critical/major/minor/none) based on downstream risk,
   not on whether Legacy and Shadow differ.
5. Record `reviewer` and a timezone-aware `review_timestamp`.
6. If uncertain, use the `uncertain` label -- never force a conclusion.

No automated signal may be copied into a human judgment column. Blank
values mean NOT_REVIEWED, not acceptance.
"""


if __name__ == "__main__":
    raise SystemExit(main())
