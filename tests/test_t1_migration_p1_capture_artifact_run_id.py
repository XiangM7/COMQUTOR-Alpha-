"""T1 follow-up migration, P1 (2026-10-10): the two capture artifacts follow the run when its directory is relocated.

``save_comqutor_run_outputs`` writes ``derived_inputs.json`` and ``provider_response_audit.json`` under the writer's OWN
temporary run id. The streaming runner then moves the directory onto the lifecycle's claimed run id
(``_relocate_run_outputs``) and rewrites the embedded ``run_id`` of the files it knows about. Before this fix those two
artifacts were not on that list, so every real run kept the writer's temporary id inside them (the two real NVDA Fresh
Runs of 2026-10-09 show exactly that).

Everything here drives the REAL writer and the REAL relocation, through the streaming runner's ``graph_factory`` seam.
The fake graph calls the real market and news dataflow tools while the runner's capture scope is open, so the capture
fills exactly as in a real run. Inputs are SYNTHETIC (a seeded random-walk OHLCV frame, hand-built provider articles
returned by a fake ``yfinance``); this proves the mechanism, not any real-market behaviour. Zero network, zero Provider
calls.

Claims proven:
  * after relocation both artifacts carry the claimed run id, and so does every other JSON the runner relocates;
  * relocation changes NOTHING else in them: the file differs from the pre-relocation bytes by the run id string only,
    so source entries, content hashes, the input series and its hash, and the calculation lineage are untouched;
  * the relocated derived inputs still reproduce every saved indicator from the saved series alone;
  * no file of the relocated run keeps the temporary id (a generic guard: a future artifact written under the temporary
    id and forgotten by the relocation fails here as well);
  * an artifact that was not captured stays absent (no bogus ``{run_id}``-only file is created);
  * the partial-save-on-stop path relocates the same way;
  * the registry and the artifact manifest of the relocated run are still correct.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import tradingagents.dataflows.market_data_validator as validator
import tradingagents.dataflows.yfinance_news as ynews
from comqutor_alpha.adapters.tradingagents_output_writer import save_comqutor_run_outputs
from comqutor_alpha.api.artifact_export import build_and_write_artifact_manifest
from comqutor_alpha.capture_artifacts import (
    DERIVED_INPUTS_FILENAME,
    PROVIDER_RESPONSE_AUDIT_FILENAME,
    recompute_derived_inputs,
    series_sha256,
)
from comqutor_alpha.runners import tradingagents_runner as runner
from comqutor_alpha.runners.request_budget import ResearchAgentBudgetExceeded
from tradingagents.dataflows.source_capture import source_capture_scope

TICKER = "SYN"  # a synthetic instrument -- never a real-market validation sample
ANALYSIS_DATE = "2026-08-10"
CLAIMED_RUN_ID = "5b0e9c58-3a53-4d9a-bb1b-0f4c2a7d2e11"
PROFILE = "comqutor_anthropic_medium_sonnet46_v1"
CAPTURE_ARTIFACTS = (DERIVED_INPUTS_FILENAME, PROVIDER_RESPONSE_AUDIT_FILENAME)


# ---------------------------------------------------------------------------
# Synthetic inputs for the real dataflow tools
# ---------------------------------------------------------------------------


def _synthetic_ohlcv(rows: int = 320, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=ANALYSIS_DATE, periods=rows)
    close = 100 + np.cumsum(rng.normal(0, 1.0, rows))
    return pd.DataFrame({
        "Date": dates,
        "Open": close + rng.normal(0, 0.3, rows),
        "High": close + np.abs(rng.normal(1.0, 0.3, rows)),
        "Low": close - np.abs(rng.normal(1.0, 0.3, rows)),
        "Close": close,
        "Volume": rng.integers(1_000_000, 5_000_000, rows),
    })


class _FakeTicker:
    def __init__(self, articles):
        self._articles = articles

    def get_news(self, count=10):
        return list(self._articles)


def _article(title, *, summary="", pub="2025-05-05T12:00:00Z", url="https://example.com/a"):
    content = {"id": "n-" + title, "contentType": "STORY", "title": title, "summary": summary, "description": "", "pubDate": pub,
               "provider": {"displayName": "Wire"}, "canonicalUrl": {"url": url}}
    return {"id": "n-" + title, "content": content}


ARTICLES = [_article("With a summary", summary="Revenue rose on data-center demand."), _article("Title only")]


@pytest.fixture
def synthetic_tools(monkeypatch):
    frame = _synthetic_ohlcv()
    monkeypatch.setattr(validator, "load_ohlcv", lambda symbol, date: frame)
    monkeypatch.setattr(ynews.yf, "Ticker", lambda symbol: _FakeTicker(ARTICLES))
    monkeypatch.setattr(ynews, "normalize_symbol", lambda ticker: ticker)


def _call_market_tool():
    validator.build_verified_market_snapshot(TICKER, ANALYSIS_DATE)


def _call_news_tool():
    ynews.get_news_yfinance(TICKER, "2025-05-01", "2025-05-09")


# ---------------------------------------------------------------------------
# A fake streaming graph (the runner's graph_factory seam) whose stream() calls the real tools
# ---------------------------------------------------------------------------


class _Propagator:
    def create_initial_state(self, ticker, trade_date, **kwargs):
        return {"company_of_interest": ticker, "trade_date": trade_date}

    def get_graph_args(self):
        return {"stream_mode": "values", "config": {"recursion_limit": 100}}


class _CapturingCompiledGraph:
    def __init__(self, tools, chunks, stop_after=None):
        self._tools, self._chunks, self._stop_after = tools, chunks, stop_after

    def stream(self, init_state, **kwargs):
        for tool in self._tools:  # the runner has opened its capture scope around this generator
            tool()
        yield from self._chunks
        if self._stop_after is not None:
            raise self._stop_after


class _CapturingGraph:
    def __init__(self, tools, chunks, stop_after=None):
        self.propagator = _Propagator()
        self.graph = _CapturingCompiledGraph(tools, chunks, stop_after)

    def resolve_instrument_context(self, ticker, asset_type):
        return f"instrument-context:{ticker}:{asset_type}"


def _chunks():
    base = {"company_of_interest": TICKER, "messages": []}
    c1 = {**base, "market_report": "market findings"}
    c2 = {**c1, "news_report": "news findings"}
    c3 = {**c2, "investment_debate_state": {"bull_history": "bull", "bear_history": "bear", "judge_decision": "debate settled"},
          "investment_plan": "plan"}
    c4 = {**c3, "trader_investment_plan": "trader plan"}
    c5 = {**c4, "risk_debate_state": {"judge_decision": "risk settled", "aggressive_history": "a"}, "final_trade_decision": "decision text"}
    return [c1, c2, c3, c4, c5]


def _payload(run_id):
    return {
        "allow_real_tradingagents_run": True,
        "ticker": TICKER,
        "analysis_date": ANALYSIS_DATE,
        "asset_type": "stock",
        "selected_analysts": ["market", "news"],
        "config": {"llm_provider": "anthropic", "deep_think_llm": "claude-sonnet-4-6", "quick_think_llm": "claude-sonnet-4-6"},
        "profile_id": PROFILE,
        "run_id": run_id,
    }


@pytest.fixture
def relocation_spy(monkeypatch):
    """Records the writer's directory (name and every file's bytes) just before the real relocation runs."""
    seen: dict = {"calls": 0}
    real = runner._relocate_run_outputs

    def spy(temp_run_dir, target_run_id, output_root):
        temp = Path(temp_run_dir)
        seen["calls"] += 1
        seen["temp_run_id"] = temp.name
        seen["before"] = {p.name: p.read_bytes() for p in sorted(temp.iterdir()) if p.is_file()}
        return real(temp_run_dir, target_run_id, output_root)

    monkeypatch.setattr(runner, "_relocate_run_outputs", spy)
    return seen


def _run_streaming(tmp_path, tools, *, stop_after=None):
    graph = _CapturingGraph(tools, _chunks(), stop_after)
    return runner.run_streaming_tradingagents_research(
        _payload(CLAIMED_RUN_ID), output_root=str(tmp_path), graph_factory=lambda internal, config: graph
    )


def _files(run_dir: Path):
    return {p.relative_to(run_dir).as_posix(): p.read_bytes() for p in sorted(run_dir.rglob("*")) if p.is_file()}


# ---------------------------------------------------------------------------
# The normal completion path
# ---------------------------------------------------------------------------


def test_both_capture_artifacts_carry_the_claimed_run_id_after_the_streaming_runner_relocates_the_run(tmp_path, synthetic_tools, relocation_spy):
    run_dir = _run_streaming(tmp_path, [_call_market_tool, _call_news_tool])
    temp_id = relocation_spy["temp_run_id"]
    before = relocation_spy["before"]

    assert relocation_spy["calls"] == 1 and temp_id != CLAIMED_RUN_ID
    assert Path(run_dir).name == CLAIMED_RUN_ID and not (tmp_path / temp_id).exists()
    # the scenario is the real one: the writer saved both artifacts under its own temporary id
    for name in CAPTURE_ARTIFACTS:
        assert name in before, f"the writer did not save {name}: the capture did not fill"
        assert json.loads(before[name])["run_id"] == temp_id
        assert before[name].count(temp_id.encode()) == 1  # the temporary id occurs once: the top-level run_id field

    for name in CAPTURE_ARTIFACTS:
        assert json.loads((Path(run_dir) / name).read_text(encoding="utf-8"))["run_id"] == CLAIMED_RUN_ID
    for name in ("metadata.json", "raw_agent_outputs.json", "source_registry.json"):  # what the relocation already rewrote
        assert json.loads((Path(run_dir) / name).read_text(encoding="utf-8"))["run_id"] == CLAIMED_RUN_ID


def test_relocation_changes_nothing_in_the_capture_artifacts_except_the_run_id_string(tmp_path, synthetic_tools, relocation_spy):
    run_dir = Path(_run_streaming(tmp_path, [_call_market_tool, _call_news_tool]))
    temp_id, before = relocation_spy["temp_run_id"], relocation_spy["before"]

    for name in CAPTURE_ARTIFACTS:
        after = (run_dir / name).read_bytes()
        assert after == before[name].replace(temp_id.encode(), CLAIMED_RUN_ID.encode()), f"{name} changed by more than its run_id"

    # lineage: the series, its hash, and the recomputation of every saved indicator are exactly what the writer saved
    saved = json.loads((run_dir / DERIVED_INPUTS_FILENAME).read_text(encoding="utf-8"))
    entry = saved["inputs"][0]
    assert entry["series"]["row_count"] == 320 and entry["series"]["sha256"] == series_sha256(entry["series"])
    verdict = recompute_derived_inputs(saved)
    assert verdict["all_reproduced"] is True and verdict["status_counts"] == {"REPRODUCED": 1}
    audit = json.loads((run_dir / PROVIDER_RESPONSE_AUDIT_FILENAME).read_text(encoding="utf-8"))
    assert audit["article_count"] >= 1 and audit["entries"][0]["response"]["articles"]  # the raw response is still whole

    # the registry points at the same series by hash, and differs from its pre-relocation content by the run id only
    registry_after = json.loads((run_dir / "source_registry.json").read_text(encoding="utf-8"))
    registry_before = json.loads(before["source_registry.json"])
    assert registry_after["run_id"] == CLAIMED_RUN_ID and registry_before["run_id"] == temp_id
    assert {**registry_after, "run_id": temp_id} == registry_before
    market = next(s for s in registry_after["sources"] if s["source_type"] == "market")
    assert market["calculation_params"]["input_series_artifact"] == DERIVED_INPUTS_FILENAME
    assert market["calculation_params"]["input_series_sha256"] == entry["series"]["sha256"]


def test_every_file_the_relocation_does_not_deliberately_rewrite_is_byte_identical_and_none_keeps_the_temporary_id(
    tmp_path, synthetic_tools, relocation_spy
):
    run_dir = Path(_run_streaming(tmp_path, [_call_market_tool, _call_news_tool]))
    temp_id, before = relocation_spy["temp_run_id"], relocation_spy["before"]
    rewritten = {"metadata.json", "raw_agent_outputs.json", "source_registry.json", *CAPTURE_ARTIFACTS}

    after_files = _files(run_dir)
    for name, content in before.items():
        if name not in rewritten:
            assert after_files[name] == content, f"{name} was modified by the relocation"
    leaks = [name for name, content in after_files.items() if temp_id.encode() in content]
    assert leaks == [], f"files still carrying the writer's temporary run id: {leaks}"


def test_the_manifest_of_the_relocated_run_lists_both_capture_artifacts(tmp_path, synthetic_tools, relocation_spy):
    run_dir = Path(_run_streaming(tmp_path, [_call_market_tool, _call_news_tool]))
    manifest = build_and_write_artifact_manifest(run_id=run_dir.name, ticker=TICKER, output_root=tmp_path)
    listed = {a["artifact_name"] for a in manifest["artifacts"]}
    assert set(CAPTURE_ARTIFACTS) <= listed and manifest["run_id"] == CLAIMED_RUN_ID


# ---------------------------------------------------------------------------
# An artifact that was not captured stays absent
# ---------------------------------------------------------------------------


def test_a_capture_artifact_that_was_not_captured_is_not_created_by_the_relocation(tmp_path, synthetic_tools, relocation_spy):
    run_dir = Path(_run_streaming(tmp_path, [_call_market_tool]))  # market only: derived inputs, but no provider response
    assert (run_dir / DERIVED_INPUTS_FILENAME).is_file() and not (run_dir / PROVIDER_RESPONSE_AUDIT_FILENAME).exists()
    assert json.loads((run_dir / DERIVED_INPUTS_FILENAME).read_text(encoding="utf-8"))["run_id"] == CLAIMED_RUN_ID


def test_a_run_with_no_capture_at_all_gains_neither_artifact(tmp_path, synthetic_tools, relocation_spy):
    run_dir = Path(_run_streaming(tmp_path, []))
    assert relocation_spy["calls"] == 1
    assert not (run_dir / DERIVED_INPUTS_FILENAME).exists() and not (run_dir / PROVIDER_RESPONSE_AUDIT_FILENAME).exists()
    assert not (run_dir / "source_registry.json").exists()


# ---------------------------------------------------------------------------
# The partial-save-on-stop path relocates the same way
# ---------------------------------------------------------------------------


def test_the_partial_save_on_a_budget_stop_relocates_the_capture_artifacts_too(tmp_path, synthetic_tools, relocation_spy):
    with pytest.raises(ResearchAgentBudgetExceeded):
        _run_streaming(tmp_path, [_call_market_tool, _call_news_tool], stop_after=ResearchAgentBudgetExceeded("synthetic stop"))
    temp_id, before = relocation_spy["temp_run_id"], relocation_spy["before"]
    run_dir = tmp_path / CLAIMED_RUN_ID

    assert relocation_spy["calls"] == 1 and run_dir.is_dir() and not (tmp_path / temp_id).exists()
    assert json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))["stopped_reason"] == "RESEARCH_AGENT_REQUEST_BUDGET_EXCEEDED"
    for name in CAPTURE_ARTIFACTS:
        assert (run_dir / name).read_bytes() == before[name].replace(temp_id.encode(), CLAIMED_RUN_ID.encode())
    assert [n for n, content in _files(run_dir).items() if temp_id.encode() in content] == []


# ---------------------------------------------------------------------------
# The relocation function itself, straight after the real writer (no runner)
# ---------------------------------------------------------------------------


def test_relocating_the_writers_directory_directly_rewrites_both_artifacts_and_a_same_id_call_is_a_no_op(tmp_path, synthetic_tools):
    with source_capture_scope() as sink:
        _call_market_tool()
        _call_news_tool()
    written = save_comqutor_run_outputs(
        final_state={"market_report": "Market report text.", "final_trade_decision": "Final decision."},
        ticker=TICKER, config={"llm_provider": "openai"}, selected_analysts=["market"], analysis_date=ANALYSIS_DATE,
        output_root=tmp_path, captured_sources=sink,
    )
    before = {name: (written / name).read_bytes() for name in CAPTURE_ARTIFACTS}
    temp_id = written.name

    assert runner._relocate_run_outputs(written, temp_id, tmp_path) == written  # same id: nothing moves, nothing is rewritten
    assert {name: (written / name).read_bytes() for name in CAPTURE_ARTIFACTS} == before

    moved = runner._relocate_run_outputs(written, CLAIMED_RUN_ID, tmp_path)
    assert Path(moved).name == CLAIMED_RUN_ID
    for name in CAPTURE_ARTIFACTS:
        assert (Path(moved) / name).read_bytes() == before[name].replace(temp_id.encode(), CLAIMED_RUN_ID.encode())
