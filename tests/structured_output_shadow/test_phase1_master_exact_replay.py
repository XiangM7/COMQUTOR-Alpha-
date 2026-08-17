"""Phase 1 Master, section 5: generalized multi-ticker Provider-zero Shadow
exact replay verifier for the ``reports/<ticker>/<family>/`` bundle shape
(distinct from Phase 1B.1's flat ``reports/<family>/`` shape).

Builds small synthetic bundle directories by hand (never a real run) --
proves PASS across multiple tickers/families, and that a ticker directory
name is never mis-walked as if it were a family name.
"""

from __future__ import annotations

import json
import socket
from copy import deepcopy
from pathlib import Path

from conftest import bundle_for, claim_for

from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.structure_engine.structured_output_shadow_prompt import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
)
from comqutor_alpha.structure_engine.structured_output_shadow_replay import (
    REASON_ARTIFACT_MISSING,
    SHADOW_EXACT_REPLAY_STATUS_FAIL,
    SHADOW_EXACT_REPLAY_STATUS_PASS,
    verify_phase1_master_shadow_exact_replay,
)
from comqutor_alpha.structure_engine.structured_output_shadow_review import (
    compare_legacy_and_shadow,
)
from comqutor_alpha.structure_engine.structured_output_shadow_schema import (
    validate_shadow_bundle,
)

REPORT_BY_TICKER = {
    "NVDA": "GPU demand accelerated this quarter across every major hyperscaler.",
    "QQQ": "The index posted broad gains led by technology constituents.",
}


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _build_multi_ticker_bundle_dir(
    base: Path,
    *,
    run_id: str = "phase1-master-test",
    failed_ticker: str | None = None,
    failed_tickers: frozenset[str] = frozenset(),
) -> Path:
    for ticker, report in REPORT_BY_TICKER.items():
        for family in ("news",):
            agent_output_id = f"{run_id}:{ticker}:news_agent:news_report"
            claim = claim_for(report, report.split(".")[0] + ".")
            bundle = bundle_for(
                report,
                claims=[claim],
                run_id=run_id,
                ticker=ticker,
                agent="news_agent",
                agent_output_id=agent_output_id,
            )
            provider_candidate = deepcopy(bundle)
            validation = validate_shadow_bundle(
                bundle,
                source_report=report,
                run_id=run_id,
                ticker=ticker,
                agent="news_agent",
                agent_output_id=agent_output_id,
                prompt_version=bundle["prompt_version"],
                prompt_sha256=bundle["prompt_sha256"],
                factor_vocabulary=[],
            )
            bundle["validation_summary"] = validation.to_summary()
            assert validation.valid, validation.reason_codes

            runtime_dir = base / "semantic_runtime" / "smoke" / ticker.lower()
            runtime_dir.mkdir(parents=True)
            session = SemanticRuntimeSession(
                run_id=f"{run_id}-{ticker}",
                output_directory=runtime_dir,
                execution_mode="shadow",
                provider="anthropic",
                model="claude-sonnet-4-6",
                profile_id="comqutor_anthropic_medium_sonnet46_v1",
            )
            started = session.start_call(
                task="structured_claim_shadow",
                prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
                prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
                input_schema_version="comqutor.structured_claim_shadow_request.v1",
                output_schema_version="comqutor.structured_claim_shadow.v1",
                input_payload={"agent_output_id": agent_output_id},
            )
            if ticker == failed_ticker or ticker in failed_tickers:
                session.finalize_call(
                    started.trace_handle,
                    provider_status="timeout",
                    retry_count=1,
                    validation_status="not_run",
                    accepted_candidate=None,
                    fallback_used=True,
                    fallback_reason="WEEK2_LLM_TIMEOUT",
                    error_code="WEEK2_LLM_TIMEOUT",
                )
            else:
                session.finalize_call(
                    started.trace_handle,
                    provider_status="success",
                    retry_count=0,
                    validation_status="accepted",
                    accepted_candidate=provider_candidate,
                    fallback_used=False,
                    fallback_reason=None,
                    error_code=None,
                )
            session.finalize_manifest(complete=True)

            legacy: list = []
            comparison = compare_legacy_and_shadow(legacy, bundle)
            family_dir = base / "reports" / ticker / family
            _write_json(
                family_dir / "source_report_snapshot.json",
                {
                    "run_id": run_id,
                    "agent_output_id": agent_output_id,
                    "report_text": report,
                    "factor_vocabulary": [],
                    "allowed_source_refs": [],
                },
            )
            _write_json(family_dir / "candidate_segments.json", [])
            _write_json(family_dir / "provider_candidate.json", provider_candidate)
            _write_json(family_dir / "shadow_bundle.json", bundle)
            _write_json(family_dir / "validation_report.json", bundle["validation_summary"])
            _write_json(family_dir / "legacy_claims_snapshot.json", legacy)
            _write_json(family_dir / "legacy_vs_shadow_comparison.json", comparison)
    return base


def test_multi_ticker_bundle_replays_pass_with_zero_external_calls(tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("network access attempted during replay")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    bundle_dir = _build_multi_ticker_bundle_dir(tmp_path)
    audit = verify_phase1_master_shadow_exact_replay(bundle_dir)
    assert audit["final_status"] == SHADOW_EXACT_REPLAY_STATUS_PASS, audit["reason_codes"]
    assert audit["provider_zero_evidence"]["provider_calls_made"] == 0
    assert audit["checks"]["report_count"] == 2
    assert audit["checks"]["ticker_count"] == 2
    tickers_seen = {entry["ticker"] for entry in audit["checks"]["per_report"]}
    assert tickers_seen == {"NVDA", "QQQ"}


def test_ticker_directory_name_never_treated_as_family_name(tmp_path):
    """The old Phase 1B.1 (flat) verifier would silently mis-walk a ticker
    dir as if it were a family dir on this shape; the new one must not."""

    bundle_dir = _build_multi_ticker_bundle_dir(tmp_path)
    audit = verify_phase1_master_shadow_exact_replay(bundle_dir)
    report_dirs = {entry["report_dir"] for entry in audit["checks"]["per_report"]}
    assert report_dirs == {"NVDA/news", "QQQ/news"}
    assert "NVDA" not in report_dirs
    assert "QQQ" not in report_dirs


def test_missing_report_artifact_fails_closed_per_ticker(tmp_path):
    bundle_dir = _build_multi_ticker_bundle_dir(tmp_path)
    (bundle_dir / "reports" / "NVDA" / "news" / "shadow_bundle.json").unlink()
    audit = verify_phase1_master_shadow_exact_replay(bundle_dir)
    assert audit["final_status"] == SHADOW_EXACT_REPLAY_STATUS_FAIL
    assert REASON_ARTIFACT_MISSING in audit["reason_codes"]


def test_partial_provider_failure_is_auditable_without_failing_accepted_replay(tmp_path):
    bundle_dir = _build_multi_ticker_bundle_dir(tmp_path, failed_ticker="QQQ")
    audit = verify_phase1_master_shadow_exact_replay(bundle_dir)
    assert audit["final_status"] == SHADOW_EXACT_REPLAY_STATUS_PASS, audit["reason_codes"]
    per_ticker = {entry["ticker"]: entry for entry in audit["checks"]["per_report"]}
    assert per_ticker["NVDA"]["replay_status"] == "PASS"
    assert per_ticker["QQQ"]["replay_status"] == "AUDITABLE_NO_ACCEPTED_OUTPUT"
    assert per_ticker["QQQ"]["accepted_output_hash"] is None


def test_all_provider_failures_are_auditable_not_replay_defects(tmp_path):
    bundle_dir = _build_multi_ticker_bundle_dir(
        tmp_path,
        failed_tickers=frozenset(REPORT_BY_TICKER),
    )
    audit = verify_phase1_master_shadow_exact_replay(bundle_dir)
    assert audit["final_status"] == SHADOW_EXACT_REPLAY_STATUS_PASS
    assert audit["reason_codes"] == []
    assert {
        item["replay_status"] for item in audit["checks"]["per_report"]
    } == {"AUDITABLE_NO_ACCEPTED_OUTPUT"}
