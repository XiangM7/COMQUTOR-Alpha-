"""Focused W7 final-closure acceptance tests. No provider or network calls."""

from __future__ import annotations

import pytest

from comqutor_alpha import server_execution
from comqutor_alpha.api.routes_research import validate_ticker
from comqutor_alpha.research_lifecycle import (
    build_research_request_fingerprint,
    build_research_request_identity,
    execute_claimed_research_run,
    mark_research_run_failed_consistently,
    prepare_research_submission,
)
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository

PUBLIC_ANALYSTS = ["market", "sentiment", "news", "fundamentals"]
SERVER_IDENTITY = {
    "provider_identity": "anthropic",
    "model_identity": "claude-sonnet-4-6:claude-sonnet-4-6",
    "profile_id": "comqutor_anthropic_medium_sonnet46_v1",
}


def _repo() -> GraphPersistenceRepository:
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


def _offline_payload(marker: str = "one") -> dict:
    return {
        "ticker": "NVDA",
        "analysis_date": "2026-07-16",
        "selected_analysts": list(reversed(PUBLIC_ANALYSTS)),
        "offline_raw_agent_outputs": [{"agent": "market", "raw_output": marker}],
    }


@pytest.mark.parametrize("ticker", ["SPY", "NVDA", "0700.HK", "BTC-USD", "GC=F", "^GSPC", "BRK.B"])
def test_ticker_contract_accepts_cli_and_safe_yahoo_symbols(ticker):
    assert validate_ticker(ticker) == ticker


@pytest.mark.parametrize(
    "ticker",
    [
        "",
        "../NVDA",
        "NVDA/TEST",
        "NVDA\\TEST",
        "https://example.com/NVDA",
        "NVDA\n",
        "NV\x00DA",
        " NVDA",
        "NV DA",
        "/tmp/NVDA",
        "TICKER-THAT-IS-DEFINITELY-LONGER-THAN-32-CHARS",
    ],
)
def test_ticker_contract_rejects_paths_controls_spaces_urls_and_overlength(ticker):
    with pytest.raises(ValueError, match="INVALID_TICKER"):
        validate_ticker(ticker)


def test_asset_type_uses_tradingagents_cli_classifier():
    assert server_execution.resolve_asset_type("NVDA") == "stock"
    assert server_execution.resolve_asset_type("BTC-USD") == "crypto"


def test_canonical_analysts_drive_identity_and_fingerprint():
    first = build_research_request_identity(_offline_payload())
    second_payload = _offline_payload()
    second_payload["selected_analysts"] = ["news", "market", "news", "fundamentals", "sentiment"]
    second = build_research_request_identity(second_payload)

    assert first["selected_analysts"] == PUBLIC_ANALYSTS
    assert second["selected_analysts"] == PUBLIC_ANALYSTS
    assert build_research_request_fingerprint(first) == build_research_request_fingerprint(second)


def test_real_submission_overrides_client_asset_type_and_resolves_date_once(monkeypatch):
    repo = _repo()
    calls = []
    original = server_execution.resolve_real_analysis_date

    def record_date(value):
        calls.append(value)
        return original(value)

    monkeypatch.setattr(server_execution, "resolve_real_analysis_date", record_date)
    prepared = prepare_research_submission(
        {
            "ticker": "NVDA",
            "analysis_date": "2026-07-15",
            "selected_analysts": ["news", "market"],
            "asset_type": "crypto",
        },
        graph_repository=repo,
        server_execution_identity=SERVER_IDENTITY,
    )

    assert "claim" in prepared
    assert calls == ["2026-07-15"]
    assert prepared["execution_payload"]["asset_type"] == "stock"
    assert prepared["execution_payload"]["selected_analysts"] == ["market", "news"]
    persisted = repo.get_research_run_record(prepared["claim"]["run_id"])
    assert persisted["selected_analysts"] == ["market", "news"]


def test_crypto_fundamentals_rejected_before_claim():
    repo = _repo()
    prepared = prepare_research_submission(
        {
            "ticker": "BTC-USD",
            "analysis_date": "2026-07-15",
            "selected_analysts": ["market", "fundamentals"],
        },
        graph_repository=repo,
        server_execution_identity=SERVER_IDENTITY,
    )

    assert prepared["response"]["error_code"] == "INVALID_ANALYST_SELECTION"
    assert repo.list_research_run_records() == []


def test_crypto_submission_with_cli_supported_analysts_is_claimed_as_crypto():
    repo = _repo()
    prepared = prepare_research_submission(
        {
            "ticker": "BTC-USD",
            "analysis_date": "2026-07-15",
            "selected_analysts": ["news", "market", "sentiment"],
        },
        graph_repository=repo,
        server_execution_identity=SERVER_IDENTITY,
    )

    assert "claim" in prepared
    assert prepared["execution_payload"]["asset_type"] == "crypto"
    assert prepared["execution_payload"]["selected_analysts"] == [
        "market",
        "sentiment",
        "news",
    ]


@pytest.mark.parametrize("analysts", [[], ["market", "social"], ["market", "unknown"]])
def test_invalid_public_analysts_rejected_before_claim(analysts):
    repo = _repo()
    prepared = prepare_research_submission(
        {**_offline_payload(), "selected_analysts": analysts},
        graph_repository=repo,
    )
    assert prepared["response"]["error_code"] == "INVALID_ANALYST_SELECTION"
    assert repo.list_research_run_records() == []


def test_failed_retry_claims_a_new_run_without_reviving_the_old_one():
    repo = _repo()
    first = prepare_research_submission(_offline_payload(), graph_repository=repo)
    old_run_id = first["claim"]["run_id"]
    repo.initialize_research_progress(old_run_id, profile_id="offline_fixture_v1", total_units=15)
    assert mark_research_run_failed_consistently(
        repo,
        old_run_id,
        error_code="RESEARCH_TIMEOUT",
        error_message="Research run exceeded the configured timeout.",
    )

    retry = prepare_research_submission(_offline_payload(), graph_repository=repo)
    new_run_id = retry["claim"]["run_id"]
    assert new_run_id != old_run_id
    assert repo.get_research_run_record(old_run_id)["status"] == "failed"
    assert repo.get_research_run_record(new_run_id)["status"] == "queued"


def test_failure_transaction_preserves_percent_and_terminal_rows():
    repo = _repo()
    prepared = prepare_research_submission(_offline_payload(), graph_repository=repo)
    run_id = prepared["claim"]["run_id"]
    repo.initialize_research_progress(run_id, profile_id="offline_fixture_v1", total_units=15)
    repo.update_research_progress(
        run_id,
        progress_percent=64,
        current_stage="risk_review",
        completed_units=6,
    )

    assert mark_research_run_failed_consistently(
        repo,
        run_id,
        error_code="RESEARCH_WORKER_CRASHED",
        error_message="Worker process failed.",
    )
    lifecycle = repo.get_research_run_record(run_id)
    progress = repo.get_research_progress(run_id)
    assert lifecycle["status"] == progress["current_stage"] == "failed"
    assert lifecycle["active_fingerprint"] is None
    assert progress["progress_percent"] == 64

    assert not mark_research_run_failed_consistently(
        repo,
        run_id,
        error_code="SERVER_SHUTDOWN",
        error_message="Server is shutting down.",
    )
    assert not repo.mark_research_progress_completed(run_id)
    assert not repo.update_research_progress(
        run_id,
        progress_percent=99,
        current_stage="result_assembly",
        completed_units=14,
    )
    assert repo.get_research_run_record(run_id)["error_code"] == "RESEARCH_WORKER_CRASHED"
    assert repo.get_research_progress(run_id)["current_stage"] == "failed"


def test_provider_style_failure_uses_consistent_terminal_helper(tmp_path):
    repo = _repo()
    prepared = prepare_research_submission(
        _offline_payload("provider-failure"),
        graph_repository=repo,
    )
    claim = prepared["claim"]

    def failed_executor(_payload, **_kwargs):
        return {
            "run_id": claim["run_id"],
            "ticker": "NVDA",
            "status": "failed",
            "error_code": "INTERNAL_ERROR",
            "message": "Research request failed.",
        }

    result = execute_claimed_research_run(
        claim["run_id"],
        prepared["execution_payload"],
        output_root=tmp_path,
        graph_repository=repo,
        disposition=claim["disposition"],
        ticker="NVDA",
        executor=failed_executor,
    )

    assert result["run_status"] == "failed"
    assert repo.get_research_run_record(claim["run_id"])["status"] == "failed"
    assert repo.get_research_progress(claim["run_id"])["current_stage"] == "failed"
