"""T1 source-linking / evidence-support chain -- FINANCIAL STATEMENTS
(get_balance_sheet/get_cashflow/get_income_statement), 2026-09-29 follow-up
per direct user instruction: complete source registration and reference
passing for these three entry points rather than excluding them from
John's task scope over the disclosure-timing ambiguity already found and
recorded when only get_fundamentals was wired.

The real ambiguity (yfinance exposes only each statement's fiscal PERIOD
END date, never a real disclosure/filing date) is handled HONESTLY, not
avoided: observation_date carries the true period end; published_at is
deliberately left None; and a NEW, dedicated eligibility check
(comqutor_alpha.source_provenance.compute_verified_support_eligibility's
DISCLOSURE_TIME_UNKNOWN reason code, added specifically for this follow-up)
excludes such a record from OFFICIAL verified support regardless of review
outcome -- proven directly below by reviewing one as SUPPORTS and
confirming it still never counts officially.

Exercises the REAL production functions:
    tradingagents.dataflows.y_finance.get_balance_sheet/get_cashflow/
    get_income_statement (monkeypatching only the external yf.Ticker
    boundary) -> source_capture -> source_registry.json ->
    save_structured_agent_outputs (llm_gateway=None, deterministic) ->
    compute_verified_support_eligibility / classify_verified_support_
    diagnostic.

Zero Provider calls, zero network, zero TradingAgents graph invocation.
"""

from __future__ import annotations

import json
import re

import pandas as pd

import tradingagents.dataflows.y_finance as y_finance
from comqutor_alpha.api.agent_output_reader import get_agent_outputs_response
from comqutor_alpha.source_provenance import build_source_registry
from comqutor_alpha.storage.file_store import save_json_record
from comqutor_alpha.structure_engine.structured_output_adapter import save_structured_agent_outputs
from tradingagents.dataflows.source_capture import source_capture_scope

RUN_ID = "t1-financial-statement-e2e-run"
TICKER = "NVDA"
ANALYSIS_DATE = "2026-08-10"


class _FakeTicker:
    def __init__(self, *, quarterly_balance_sheet=None, quarterly_cashflow=None, quarterly_income_stmt=None):
        self.quarterly_balance_sheet = quarterly_balance_sheet
        self.quarterly_cashflow = quarterly_cashflow
        self.quarterly_income_stmt = quarterly_income_stmt


def _balance_sheet_df():
    columns = [pd.Timestamp("2026-04-30"), pd.Timestamp("2026-01-31")]
    return pd.DataFrame({columns[0]: {"Total Assets": 1.2e11}, columns[1]: {"Total Assets": 1.1e11}})


def _cashflow_df():
    columns = [pd.Timestamp("2026-04-30"), pd.Timestamp("2026-01-31")]
    return pd.DataFrame({columns[0]: {"Free Cash Flow": 2.5e10}, columns[1]: {"Free Cash Flow": 2.2e10}})


def _income_statement_df():
    columns = [pd.Timestamp("2026-04-30"), pd.Timestamp("2026-01-31")]
    return pd.DataFrame({columns[0]: {"Total Revenue": 3.0e10}, columns[1]: {"Total Revenue": 2.8e10}})


def _capture_real_balance_sheet(monkeypatch, *, ticker=TICKER, curr_date=ANALYSIS_DATE, df=None):
    monkeypatch.setattr(
        y_finance.yf, "Ticker", lambda symbol: _FakeTicker(quarterly_balance_sheet=df if df is not None else _balance_sheet_df())
    )
    with source_capture_scope() as sink:
        report_text = y_finance.get_balance_sheet(ticker, freq="quarterly", curr_date=curr_date)
    return report_text, list(sink)


def _capture_real_cashflow(monkeypatch, *, ticker=TICKER, curr_date=ANALYSIS_DATE, df=None):
    monkeypatch.setattr(
        y_finance.yf, "Ticker", lambda symbol: _FakeTicker(quarterly_cashflow=df if df is not None else _cashflow_df())
    )
    with source_capture_scope() as sink:
        report_text = y_finance.get_cashflow(ticker, freq="quarterly", curr_date=curr_date)
    return report_text, list(sink)


def _capture_real_income_statement(monkeypatch, *, ticker=TICKER, curr_date=ANALYSIS_DATE, df=None):
    monkeypatch.setattr(
        y_finance.yf, "Ticker", lambda symbol: _FakeTicker(quarterly_income_stmt=df if df is not None else _income_statement_df())
    )
    with source_capture_scope() as sink:
        report_text = y_finance.get_income_statement(ticker, freq="quarterly", curr_date=curr_date)
    return report_text, list(sink)


def _write_run_fixture(tmp_path, *, agent_outputs, captured_sources, analysis_date=ANALYSIS_DATE, run_id=RUN_ID):
    save_json_record(
        run_id, "metadata.json",
        {"run_id": run_id, "ticker": TICKER, "analysis_date": analysis_date},
        output_root=str(tmp_path),
    )
    save_json_record(
        run_id, "raw_agent_outputs.json",
        {"schema_version": "raw.v1", "run_id": run_id, "ticker": TICKER, "agent_outputs": agent_outputs},
        output_root=str(tmp_path),
    )
    registry = None
    if captured_sources:
        registry = build_source_registry(
            run_id=run_id, ticker=TICKER, retrieved_at="2026-08-10T00:00:00Z", captured_records=captured_sources
        )
        save_json_record(run_id, "source_registry.json", registry, output_root=str(tmp_path))
    return registry


def _run_dir(tmp_path, run_id=RUN_ID):
    return tmp_path / run_id


class TestBalanceSheetScenarioA_ValidLinkPropagatesEndToEnd:
    def test_real_balance_sheet_snapshot_produces_a_valid_link_through_the_real_pipeline(self, tmp_path, monkeypatch):
        report_text, captured = _capture_real_balance_sheet(monkeypatch)
        assert len(captured) == 1
        source = captured[0]
        assert source["source_type"] == "financial"
        assert source["instrument"] == TICKER
        assert source["observation_date"] == "2026-04-30"  # the TRUE fiscal period end
        assert source["published_at"] is None  # deliberately unknown, never self-completed
        # 2026-10-04 (T1 financial-data fix round): corrected from a
        # hardcoded "USD" -- yfinance's statement DataFrames carry no
        # currency metadata at all, and fetching it would require a new
        # Provider call this function does not make, so it is now honestly
        # reported as unknown rather than assumed.
        assert source["unit"] == "UNKNOWN_CURRENCY"
        assert source["data_snapshot"]["line_item"] == "Total Assets"
        assert source["data_snapshot"]["value"] == 1.2e11
        # The full period series (not only the latest value) is now saved,
        # so the stated comparison below can be independently recomputed.
        assert source["data_snapshot"]["periods"] == {"2026-04-30": 1.2e11, "2026-01-31": 1.1e11}
        assert source["data_snapshot"]["comparison"]["delta"] == 1.0e10

        agent_outputs = [
            {
                "agent": "fundamental_agent",
                "agent_output_id": f"{RUN_ID}:fundamental_agent:fundamentals_report",
                "raw_output": report_text,
            }
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, captured_sources=captured)
        save_structured_agent_outputs(_run_dir(tmp_path), llm_gateway=None)

        persisted = json.loads((_run_dir(tmp_path) / "structured_agent_outputs.json").read_text())
        linked = [r for r in persisted["records"] if r.get("source_link_status") == "VALID"]
        assert linked, "expected the real balance-sheet snapshot to produce a VALID-linked claim"
        record = linked[0]

        response = get_agent_outputs_response(RUN_ID, output_root=str(tmp_path))
        api_record = next(r for r in response["structured_agent_outputs"] if r["claim_id"] == record["claim_id"])
        assert api_record["source_link_status"] == "VALID"
        assert api_record["linked_source"]["instrument"] == TICKER
        assert api_record["linked_source"]["observation_date"] == "2026-04-30"
        assert api_record["linked_source"]["published_at"] is None


class TestFinancialStatementScenarioB_DisclosureTimeUnknownNeverPromotedToOfficialSupport:
    def test_even_a_full_human_reviewed_supports_verdict_never_counts_as_officially_verified(
        self, tmp_path, monkeypatch
    ):
        """The core requirement this follow-up exists to prove: a record
        with published_at=None (disclosure timing genuinely unknown) must
        NEVER be promoted to officially verified support, no matter how
        the human review resolves -- distinct from, and independent of,
        whether the reference itself is valid/resolvable/current."""
        from comqutor_alpha.source_provenance import (
            SOURCE_LINK_VALID,
            apply_content_support_review,
            classify_verified_support_diagnostic,
            compute_verified_support_eligibility,
        )

        _, captured = _capture_real_balance_sheet(monkeypatch)
        registry = build_source_registry(
            run_id=RUN_ID, ticker=TICKER, retrieved_at="2026-08-10T00:00:00Z", captured_records=captured
        )
        source = registry["sources"][0]
        assert source["published_at"] is None

        record = {
            "claim_id": f"{RUN_ID}:fundamental_agent:claim:1",
            "run_id": RUN_ID, "ticker": TICKER, "agent": "fundamental_agent",
            "claim": "NVDA's balance sheet remains strong per verified total assets data.",
            "evidence": "NVDA's balance sheet remains strong per verified total assets data.",
            "entities": [], "factors": [], "direction": "positive", "confidence": 0.8,
            "source_link_status": SOURCE_LINK_VALID,
            "linked_source_id": source["fragment_id"],
        }
        reviewed = apply_content_support_review(
            record, status="SUPPORTS", reviewer="analyst_a",
            rationale="matches the verified balance sheet's own reported total assets",
            reviewed_at="2026-08-10T12:00:00Z", sources=registry["sources"],
        )
        assert reviewed["content_support_review"]["content_hash"] == source["content_hash"]

        eligibility = compute_verified_support_eligibility(reviewed, registry["sources"])
        assert eligibility["eligible"] is False
        assert eligibility["reason_code"] == "DISCLOSURE_TIME_UNKNOWN"

        diagnostic = classify_verified_support_diagnostic(reviewed, registry["sources"])
        assert diagnostic["category"] == "DISCLOSURE_TIME_UNKNOWN"


class TestFinancialStatementScenarioC_InvalidReferencesAreRejected:
    def test_a_forged_marker_that_does_not_resolve_in_this_runs_registry_is_never_trusted(self, tmp_path, monkeypatch):
        _, captured = _capture_real_balance_sheet(monkeypatch)
        agent_outputs = [
            {
                "agent": "fundamental_agent",
                "agent_output_id": f"{RUN_ID}:fundamental_agent:fundamentals_report",
                "raw_output": (
                    "NVDA is showing strong revenue growth momentum "
                    "[fragment_id: src_deadbeefdeadbeef:frag:0]."
                ),
            }
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, captured_sources=captured)
        save_structured_agent_outputs(_run_dir(tmp_path), llm_gateway=None)

        persisted = json.loads((_run_dir(tmp_path) / "structured_agent_outputs.json").read_text())
        forged = next(r for r in persisted["records"] if "deadbeef" in r["claim"])
        assert forged["source_link_status"] == "NOT_PROVIDED"
        assert forged["linked_source_id"] is None
        assert forged["content_support_status"] == "NOT_APPLICABLE"


class TestCashflowAndIncomeStatementScenarioD_TheOtherTwoEntryPointsAreWiredTheSameWay:
    def test_cashflow_snapshot_links_with_observation_date_and_unknown_published_at(self, tmp_path, monkeypatch):
        report_text, captured = _capture_real_cashflow(monkeypatch)
        assert len(captured) == 1
        source = captured[0]
        assert source["source_type"] == "financial"
        assert source["observation_date"] == "2026-04-30"
        assert source["published_at"] is None
        assert source["data_snapshot"]["line_item"] == "Free Cash Flow"
        marker_match = re.search(r"\[source_id: [^\]]+\] \[fragment_id: [^\]]+\]", report_text)
        assert marker_match, "expected the real cash flow report to carry a source/fragment marker"

    def test_income_statement_snapshot_links_with_observation_date_and_unknown_published_at(self, tmp_path, monkeypatch):
        report_text, captured = _capture_real_income_statement(monkeypatch)
        assert len(captured) == 1
        source = captured[0]
        assert source["source_type"] == "financial"
        assert source["observation_date"] == "2026-04-30"
        assert source["published_at"] is None
        assert source["data_snapshot"]["line_item"] == "Total Revenue"
        marker_match = re.search(r"\[source_id: [^\]]+\] \[fragment_id: [^\]]+\]", report_text)
        assert marker_match, "expected the real income statement report to carry a source/fragment marker"
