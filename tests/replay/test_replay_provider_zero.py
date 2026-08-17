from __future__ import annotations

import http.client
import json
import socket
from pathlib import Path

import pytest
import requests

import comqutor_alpha.replay.exact_semantic as exact_semantic
from comqutor_alpha.replay.source_bundle import (
    EXACT_REPLAY_OUTPUT_VALIDATION_FAILED,
    EXACT_REPLAY_STAGING_WRITE_FAILED,
    ExactReplayError,
)


def _forbidden(name: str):
    def fail(*args, **kwargs):
        del args, kwargs
        pytest.fail(f"forbidden Exact Replay side effect: {name}")

    return fail


def test_exact_replay_never_recomputes_semantics_or_calls_external_services(
    tmp_path: Path,
    eligible_live_source: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "comqutor_alpha.structure_engine.structured_output_adapter.adapt_run_outputs",
        _forbidden("adapt_run_outputs"),
    )
    monkeypatch.setattr(
        "comqutor_alpha.structure_engine.structured_output_adapter.adapt_raw_agent_outputs",
        _forbidden("adapt_raw_agent_outputs"),
    )
    monkeypatch.setattr(
        "comqutor_alpha.structure_engine.alpha_mapper.build_alpha_matches_payload",
        _forbidden("build_alpha_matches_payload"),
    )
    monkeypatch.setattr(
        "comqutor_alpha.structure_engine.structure_extractor.build_extracted_structures_payload",
        _forbidden("build_extracted_structures_payload"),
    )
    monkeypatch.setattr(
        "comqutor_alpha.structure_engine.week2_llm.Week2LLMGateway.invoke_json",
        _forbidden("Week2LLMGateway.invoke_json"),
    )
    monkeypatch.setattr(
        "comqutor_alpha.structure_engine.week2_llm.Week2LLMGateway.invoke_json_with_trace",
        _forbidden("Week2LLMGateway.invoke_json_with_trace"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.TradingAgentsGraph.propagate",
        _forbidden("TradingAgents"),
    )
    monkeypatch.setattr(
        "tradingagents.llm_clients.factory.create_llm_client",
        _forbidden("Provider factory"),
    )
    monkeypatch.setattr(socket.socket, "connect", _forbidden("socket"))
    monkeypatch.setattr(http.client.HTTPConnection, "connect", _forbidden("HTTP"))
    monkeypatch.setattr(requests.Session, "request", _forbidden("HTTP request"))
    monkeypatch.setattr(
        "comqutor_alpha.data_sanity.yfinance_provider.YFinanceMarketDataProvider.get_history_rows",
        _forbidden("market data"),
    )
    monkeypatch.setattr(
        "comqutor_alpha.storage.db.engine.create_engine",
        _forbidden("database connection"),
    )
    monkeypatch.setattr(
        "comqutor_alpha.storage.db.repository.GraphPersistenceRepository.persist_run",
        _forbidden("database write"),
    )

    result = exact_semantic.run_exact_semantic_replay(
        eligible_live_source,
        tmp_path / "provider-zero",
        replay_id="provider-zero-replay",
    )

    assert result.provider_calls == 0
    assert result.tradingagents_calls == 0
    assert result.market_data_calls == 0
    assert result.database_writes == 0
    metadata = json.loads(
        (Path(result.output_dir) / "metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["provider_zero"] is True
    assert [
        metadata["provider_calls"],
        metadata["tradingagents_calls"],
        metadata["market_data_calls"],
        metadata["database_writes"],
    ] == [0, 0, 0, 0]


@pytest.mark.parametrize(
    ("failure_point", "expected_code"),
    [
        ("write", EXACT_REPLAY_STAGING_WRITE_FAILED),
        ("validation", EXACT_REPLAY_OUTPUT_VALIDATION_FAILED),
        ("rename", EXACT_REPLAY_STAGING_WRITE_FAILED),
    ],
)
def test_atomic_failure_never_leaves_success_directory(
    tmp_path: Path,
    eligible_live_source: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
    expected_code: str,
) -> None:
    replay_id = f"atomic-{failure_point}"
    output_root = tmp_path / f"output-{failure_point}"
    if failure_point == "write":
        def fail_write(*args, **kwargs):
            del args, kwargs
            raise OSError("synthetic staging write failure")

        monkeypatch.setattr(
            exact_semantic,
            "_write_json",
            fail_write,
        )
    elif failure_point == "validation":
        def fail_validation(*args, **kwargs):
            del args, kwargs
            raise ExactReplayError(EXACT_REPLAY_OUTPUT_VALIDATION_FAILED)

        monkeypatch.setattr(exact_semantic, "_validate_staged_output", fail_validation)
    else:
        def fail_rename(*args, **kwargs):
            del args, kwargs
            raise OSError("synthetic atomic rename failure")

        monkeypatch.setattr(exact_semantic, "_atomic_promote", fail_rename)

    with pytest.raises(ExactReplayError) as caught:
        exact_semantic.run_exact_semantic_replay(
            eligible_live_source,
            output_root,
            replay_id=replay_id,
        )

    assert caught.value.reason_code == expected_code
    assert not (output_root / replay_id).exists()
    assert not list(output_root.glob(".exact-semantic-replay-staging-*"))
