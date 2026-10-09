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


# ---------------------------------------------------------------------------
# Round 2 (2026-10-04): full-table capture -- the Agent receives EVERY line
# item x EVERY period via the plain CSV dump, not only the one summary row.
# These fixtures deliberately include a line item that is NOT one of
# _BALANCE_SHEET_LINE_ITEM_CANDIDATES/_INCOME_STATEMENT_LINE_ITEM_CANDIDATES,
# so these tests prove non-summary rows are also captured and referenceable,
# not just the one row the summary sentence already covered.
# ---------------------------------------------------------------------------


def _multi_row_balance_sheet_df():
    columns = [pd.Timestamp("2026-04-30"), pd.Timestamp("2026-01-31")]
    return pd.DataFrame(
        {
            columns[0]: {"Total Assets": 1.2e11, "Cash And Cash Equivalents": 4.5e10, "Ordinary Shares Number": 2.47e10},
            columns[1]: {"Total Assets": 1.1e11, "Cash And Cash Equivalents": 4.0e10, "Ordinary Shares Number": 2.46e10},
        }
    )


def _multi_row_income_statement_df():
    columns = [pd.Timestamp("2026-04-30"), pd.Timestamp("2026-01-31")]
    return pd.DataFrame(
        {
            columns[0]: {"Total Revenue": 3.0e10, "Diluted EPS": 1.22},
            columns[1]: {"Total Revenue": 2.8e10, "Diluted EPS": 1.14},
        }
    )


class TestFullTableCaptureScenarioE_NonSummaryRowsAreAlsoCapturedAndReferenceable:
    def test_balance_sheet_captures_every_real_line_item_not_only_the_summary_row(self, tmp_path, monkeypatch):
        """'Cash And Cash Equivalents' and 'Ordinary Shares Number' are NOT
        in _BALANCE_SHEET_LINE_ITEM_CANDIDATES (only 'Total Assets' is the
        summary row here) -- this proves they are captured anyway, each
        period-complete and each with its own real, correctly-classified
        unit (a share COUNT is never lumped in as a bare currency amount)."""
        report_text, captured = _capture_real_balance_sheet(monkeypatch, df=_multi_row_balance_sheet_df())
        assert len(captured) == 1  # still one source record per call -- multiple rows share it, never split
        source = captured[0]
        all_items = source["data_snapshot"]["all_line_items"]
        units = source["data_snapshot"]["line_item_units"]

        # The summary row (unchanged behavior).
        assert all_items["Total Assets"] == {"2026-04-30": 1.2e11, "2026-01-31": 1.1e11}
        assert units["Total Assets"] == "UNKNOWN_CURRENCY"

        # A real, non-summary currency row -- period-complete.
        assert all_items["Cash And Cash Equivalents"] == {"2026-04-30": 4.5e10, "2026-01-31": 4.0e10}
        assert units["Cash And Cash Equivalents"] == "UNKNOWN_CURRENCY"

        # A real, non-summary SHARE-COUNT row -- must not be classified as a
        # currency amount just because every other row in this table is one.
        assert all_items["Ordinary Shares Number"] == {"2026-04-30": 2.47e10, "2026-01-31": 2.46e10}
        assert units["Ordinary Shares Number"] == "shares"

        # The Agent's own report text genuinely contains every real row
        # (the full CSV dump), proving these are not values this test
        # invented independently of what the tool actually returned.
        assert "Cash And Cash Equivalents" in report_text
        assert "Ordinary Shares Number" in report_text
        assert "45000000000.0" in report_text or "4.5e+10" in report_text.replace(",", "")

        # Round 2 finding (2026-10-04, NOT papered over): this statement's
        # excerpt now joins every row's text with " | " so content-match
        # CAN resolve a non-summary row -- but only for an EXACT, unwrapped
        # restatement of that row's own formatted substring. Confirmed by
        # direct test of match_evidence_to_source_candidates
        # (source_provenance.py:826-866, unmodified, out of this round's
        # scope): it requires the WHOLE excerpt to be a substring of the
        # claim (or vice versa) -- there is no partial/fuzzy overlap. A
        # claim with ANY real wrapping prose around that same exact text
        # (e.g. "NVDA's cash position remains a key balance-sheet
        # strength: ...underscoring ample liquidity") breaks BOTH
        # directions of that substring check against the combined,
        # multi-row excerpt and resolves NOT_PROVIDED. This is the real,
        # pre-existing, identified break point for a realistically-
        # paraphrased restatement of a non-summary row via content-match
        # alone -- it is a structural property of the exact-substring
        # matcher, not something this round's capture work (which only
        # touches y_finance.py) can or should fix.
        #
        # The REAL, reliable mechanism a production agent actually uses for
        # ANY row in this statement (summary or not) is the SAME
        # [source_id: ...] [fragment_id: ...] marker _statement_summary_
        # sentence already appends to the full report text (see
        # TestCashflowAndIncomeStatementScenarioD above) -- fragment-level,
        # not excerpt-text-level, so it does not depend on exact-substring
        # overlap. This mirrors the already-established, already-passing
        # pattern in TestFinancialDataScenarioB_GateAndReviewIntegration
        # (test_t1_financial_source_chain.py): a real agent combines the
        # verified figure with its own analytical prose IN THE SAME
        # sentence as the marker, and that marker is what resolves it.
        marker_match = re.search(r"\[source_id: [^\]]+\] \[fragment_id: [^\]]+\]", report_text)
        assert marker_match, "expected the real balance sheet report to carry a source/fragment marker"
        marker_text = marker_match.group(0)

        agent_outputs = [
            {
                "agent": "fundamental_agent",
                "agent_output_id": f"{RUN_ID}:fundamental_agent:fundamentals_report",
                "raw_output": (
                    "NVDA's cash position remains a key balance-sheet strength, with cash and "
                    f"equivalents holding near $45.0 billion as of the latest quarter {marker_text}"
                ),
            }
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, captured_sources=captured)
        save_structured_agent_outputs(_run_dir(tmp_path), llm_gateway=None)

        # Reload from DISK (not the in-memory `captured`/fixture objects) --
        # proves this round-trips through real persistence, not memory.
        persisted = json.loads((_run_dir(tmp_path) / "structured_agent_outputs.json").read_text())
        cash_claim = next(r for r in persisted["records"] if "cash and" in r["claim"])
        assert cash_claim["source_link_status"] == "VALID", (
            "expected the non-summary 'Cash And Cash Equivalents' row to be locatable via the real "
            "marker mechanism -- if this fails, the break point is in marker extraction/validation, "
            "not in data_snapshot capture (already proven present above)"
        )
        assert cash_claim["source_link_method"] == "ORIGINAL_AGENT_MARKER_CITED"

        registry = json.loads((_run_dir(tmp_path) / "source_registry.json").read_text())
        reloaded_source = registry["sources"][0]
        # validate_source_reference (source_provenance.py, unmodified) always
        # sets linked_source_id to the resolved SOURCE's bare source_id --
        # never the fragment_id -- regardless of whether the candidate
        # resolved by fragment_id or by source_id lookup. A pre-existing,
        # documented convention, not something either round touched.
        assert cash_claim["linked_source_id"] == reloaded_source["source_id"]
        assert reloaded_source["data_snapshot"]["all_line_items"]["Ordinary Shares Number"]["2026-04-30"] == 2.47e10

    def test_income_statement_classifies_per_share_rows_correctly_not_as_currency(self, tmp_path, monkeypatch):
        """'Diluted EPS' is NOT in _INCOME_STATEMENT_LINE_ITEM_CANDIDATES
        ('Total Revenue' is the summary row here) -- proves it is captured
        with its real per-share unit, never silently treated as a bare
        currency amount the way every other row in this statement type
        genuinely is."""
        _, captured = _capture_real_income_statement(monkeypatch, df=_multi_row_income_statement_df())
        source = captured[0]
        all_items = source["data_snapshot"]["all_line_items"]
        units = source["data_snapshot"]["line_item_units"]

        assert all_items["Diluted EPS"] == {"2026-04-30": 1.22, "2026-01-31": 1.14}
        assert units["Diluted EPS"] == "UNKNOWN_CURRENCY_per_share"
        assert units["Total Revenue"] == "UNKNOWN_CURRENCY"
