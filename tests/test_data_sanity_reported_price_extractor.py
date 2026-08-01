"""Deterministic reported-price extraction tests. All fixtures are minimal
synthetic sentences (never a full real Provider report), and no LLM/network
is involved -- pure regex parsing."""

from __future__ import annotations

import datetime as dt

from comqutor_alpha.data_sanity.reported_price_extractor import extract_reported_prices
from comqutor_alpha.data_sanity.schema import (
    DAILY_RANGE_SKIP_REASON_TECHNICAL_INDICATOR,
    DATE_RESOLUTION_ANALYSIS_YEAR_INFERRED,
    DATE_RESOLUTION_EXPLICIT_YEAR,
    DATE_RESOLUTION_PREVIOUS_YEAR_INFERRED,
    PRICE_SEMANTICS_CLOSE,
    PRICE_SEMANTICS_GENERIC,
    PRICE_SEMANTICS_OPEN,
    PRICE_SEMANTICS_REACHED,
    SEMANTIC_ROLE_CLOSE_PRICE,
    SEMANTIC_ROLE_MOVING_AVERAGE,
    SEMANTIC_ROLE_OPEN_PRICE,
    SEMANTIC_ROLE_TECHNICAL_LEVEL,
)

ANALYSIS_DATE = dt.date(2026, 7, 24)


def _record(claim, evidence=None, claim_id="c1", agent="market_agent"):
    return {"claim_id": claim_id, "agent": agent, "claim": claim, "evidence": evidence or claim}


def _extract_one(claim):
    results = extract_reported_prices([_record(claim)], ANALYSIS_DATE)
    assert len(results) == 1, f"expected exactly one extraction for {claim!r}, got {results}"
    return results[0]


class TestRequiredFixtures:
    def test_opened_at_dollar_on_date(self):
        result = _extract_one("MU opened at $95.20 on May 1.")
        assert result["reported_price"] == 95.20
        assert result["price_semantics"] == PRICE_SEMANTICS_OPEN
        assert result["reported_date"] == "2026-05-01"
        assert result["date_resolution"] == DATE_RESOLUTION_ANALYSIS_YEAR_INFERRED

    def test_reached_dollar_on_date(self):
        result = _extract_one("MU reached $110.00 on June 25.")
        assert result["reported_price"] == 110.0
        assert result["price_semantics"] == PRICE_SEMANTICS_REACHED
        assert result["reported_date"] == "2026-06-25"

    def test_date_first_open_was_dollar(self):
        result = _extract_one("On May 1, MU's open was $95.20.")
        assert result["reported_price"] == 95.20
        assert result["price_semantics"] == PRICE_SEMANTICS_OPEN
        assert result["reported_date"] == "2026-05-01"

    def test_closed_at_dollar_explicit_iso_date(self):
        result = _extract_one("MU closed at $100 on 2026-07-20.")
        assert result["reported_price"] == 100.0
        assert result["price_semantics"] == PRICE_SEMANTICS_CLOSE
        assert result["reported_date"] == "2026-07-20"
        assert result["date_resolution"] == DATE_RESOLUTION_EXPLICIT_YEAR


class TestSemanticsCoverage:
    def test_open_of_semantics(self):
        result = _extract_one("MU's open of $95.20 on May 1.")
        assert result["price_semantics"] == PRICE_SEMANTICS_OPEN

    def test_close_of_semantics(self):
        result = _extract_one("MU's close of $101.50 on May 1.")
        assert result["price_semantics"] == PRICE_SEMANTICS_CLOSE

    def test_traded_at_semantics(self):
        result = _extract_one("MU traded at $103.00 on May 1.")
        assert result["price_semantics"] == "traded"

    def test_peaked_at_semantics(self):
        result = _extract_one("MU peaked at $112.00 on May 1.")
        assert result["price_semantics"] == "peaked"

    def test_fell_to_semantics(self):
        result = _extract_one("MU fell to $88.00 on May 1.")
        assert result["price_semantics"] == "fell_to"

    def test_bare_price_on_date_is_generic(self):
        result = _extract_one("MU traded around $99.00 on May 1.")
        assert result["price_semantics"] == PRICE_SEMANTICS_GENERIC

    def test_date_first_close_was_dollar(self):
        result = _extract_one("On May 1, MU's close was $99.00.")
        assert result["price_semantics"] == PRICE_SEMANTICS_CLOSE


class TestDateResolution:
    def test_explicit_year_recorded(self):
        result = _extract_one("MU opened at $95.20 on May 1, 2025.")
        assert result["date_resolution"] == DATE_RESOLUTION_EXPLICIT_YEAR
        assert result["reported_date"] == "2025-05-01"

    def test_analysis_year_inferred_when_date_not_after_analysis_date(self):
        result = _extract_one("MU opened at $95.20 on May 1.")
        assert result["date_resolution"] == DATE_RESOLUTION_ANALYSIS_YEAR_INFERRED
        assert result["reported_date"] == "2026-05-01"

    def test_previous_year_inferred_when_date_would_be_after_analysis_date(self):
        # analysis_date is 2026-07-24; "December 15" with no year would land
        # after it if taken as 2026, so the previous year must be used.
        result = _extract_one("MU opened at $95.20 on December 15.")
        assert result["date_resolution"] == DATE_RESOLUTION_PREVIOUS_YEAR_INFERRED
        assert result["reported_date"] == "2025-12-15"


class TestSkippedAndMisclassification:
    def test_no_date_is_skipped(self):
        assert extract_reported_prices([_record("MU opened at $95.20.")], ANALYSIS_DATE) == []

    def test_revenue_not_misidentified(self):
        assert extract_reported_prices(
            [_record("Revenue reached $9.3 billion on May 1.")], ANALYSIS_DATE
        ) == []

    def test_market_cap_not_misidentified(self):
        assert extract_reported_prices(
            [_record("MU market cap reached $150 billion on May 1.")], ANALYSIS_DATE
        ) == []

    def test_price_target_not_misidentified(self):
        assert extract_reported_prices(
            [_record("Analysts set a price target of $150 on May 1.")], ANALYSIS_DATE
        ) == []

    def test_eps_not_misidentified(self):
        assert extract_reported_prices(
            [_record("MU's Q2 EPS was $1.85 on May 1.")], ANALYSIS_DATE
        ) == []

    def test_percentage_not_misidentified(self):
        assert extract_reported_prices(
            [_record("MU shares rose 25% on May 1.")], ANALYSIS_DATE
        ) == []

    def test_claim_without_dollar_sign_never_extracted(self):
        assert extract_reported_prices(
            [_record("MU shares rose sharply on May 1.")], ANALYSIS_DATE
        ) == []


class TestOutputContract:
    def test_source_text_is_truncated_and_present(self):
        result = _extract_one("MU opened at $95.20 on May 1.")
        assert result["source_text"] == "MU opened at $95.20 on May 1."
        assert len(result["source_text"]) <= 500

    def test_claim_id_and_agent_preserved(self):
        results = extract_reported_prices(
            [_record("MU opened at $95.20 on May 1.", claim_id="claim-42", agent="news_agent")],
            ANALYSIS_DATE,
        )
        assert results[0]["claim_id"] == "claim-42"
        assert results[0]["source_agent"] == "news_agent"

    def test_no_ticker_field_is_ever_attached(self):
        result = _extract_one("MU opened at $95.20 on May 1.")
        assert "ticker" not in result

    def test_empty_records_list_returns_empty(self):
        assert extract_reported_prices([], ANALYSIS_DATE) == []

    def test_malformed_record_is_skipped_not_raised(self):
        assert extract_reported_prices([None, "not a dict", 42], ANALYSIS_DATE) == []


class TestNumericSemanticRole:
    """Structure Integrity Repair Sprint, Track 3: a technical indicator
    figure is classified as such and never treated as an observed market
    price eligible for a daily-OHLC-range comparison -- this is the fix for
    the real NVDA false positive (200 SMA misread as a market price)."""

    def test_sma_moving_average_not_daily_range_eligible(self):
        result = _extract_one(
            "The 200 SMA has been rising steadily (from $187.6 on June 1 to "
            "$192.86 today), indicating the longer-term trend is still up."
        )
        assert result["semantic_role"] == SEMANTIC_ROLE_MOVING_AVERAGE
        assert result["daily_range_check_eligible"] is False
        assert result["daily_range_skip_reason"] == DAILY_RANGE_SKIP_REASON_TECHNICAL_INDICATOR

    def test_fifty_day_moving_average_is_moving_average(self):
        result = _extract_one("The 50-day moving average is $95.20 on May 1.")
        assert result["semantic_role"] == SEMANTIC_ROLE_MOVING_AVERAGE
        assert result["daily_range_check_eligible"] is False

    def test_ema_not_daily_range_eligible(self):
        result = _extract_one("The EMA reached $103.00 on May 1.")
        assert result["semantic_role"] == SEMANTIC_ROLE_MOVING_AVERAGE
        assert result["daily_range_check_eligible"] is False

    def test_vwap_not_daily_range_eligible(self):
        result = _extract_one("VWAP fell to $88.00 on May 1.")
        assert result["semantic_role"] == SEMANTIC_ROLE_MOVING_AVERAGE
        assert result["daily_range_check_eligible"] is False

    def test_bollinger_band_not_daily_range_eligible(self):
        result = _extract_one("The upper Bollinger Band reached $112.00 on May 1.")
        assert result["semantic_role"] == SEMANTIC_ROLE_MOVING_AVERAGE
        assert result["daily_range_check_eligible"] is False

    def test_atr_not_daily_range_eligible(self):
        result = _extract_one("The ATR peaked at $12.00 on May 1.")
        assert result["semantic_role"] == SEMANTIC_ROLE_MOVING_AVERAGE
        assert result["daily_range_check_eligible"] is False

    def test_rsi_not_daily_range_eligible(self):
        result = _extract_one("The RSI reached $70.00 on May 1.")
        assert result["semantic_role"] == SEMANTIC_ROLE_MOVING_AVERAGE
        assert result["daily_range_check_eligible"] is False

    def test_support_level_not_daily_range_eligible(self):
        result = _extract_one("Key support reached $88.00 on May 1.")
        assert result["semantic_role"] == SEMANTIC_ROLE_TECHNICAL_LEVEL
        assert result["daily_range_check_eligible"] is False

    def test_resistance_level_not_daily_range_eligible(self):
        result = _extract_one("The resistance level reached $112.00 on May 1.")
        assert result["semantic_role"] == SEMANTIC_ROLE_TECHNICAL_LEVEL
        assert result["daily_range_check_eligible"] is False

    def test_closed_at_is_close_price_and_eligible(self):
        result = _extract_one("MU closed at $100 on 2026-07-20.")
        assert result["semantic_role"] == SEMANTIC_ROLE_CLOSE_PRICE
        assert result["daily_range_check_eligible"] is True
        assert result["daily_range_skip_reason"] is None

    def test_opened_at_is_open_price_and_eligible(self):
        result = _extract_one("MU opened at $95.20 on May 1.")
        assert result["semantic_role"] == SEMANTIC_ROLE_OPEN_PRICE
        assert result["daily_range_check_eligible"] is True
        assert result["daily_range_skip_reason"] is None
