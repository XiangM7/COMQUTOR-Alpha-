"""Deterministic checker tests for Data Sanity v1: market availability,
OHLCV integrity, corporate actions, extreme adjusted returns, and reported
price cross-checks. Every fixture is hand-built -- zero network, zero
pandas (the checker operates on plain dicts)."""

from __future__ import annotations

import datetime as dt

from comqutor_alpha.data_sanity.checker import (
    check_corporate_actions,
    check_extreme_returns,
    check_market_availability,
    check_ohlcv_integrity,
    check_reported_prices,
)
from comqutor_alpha.data_sanity.schema import (
    ANALYSIS_DATE_IN_FUTURE,
    ANALYSIS_DATE_NON_TRADING_DAY,
    CAPITAL_GAIN_IN_ANALYSIS_WINDOW,
    DIVIDEND_IN_ANALYSIS_WINDOW,
    DUPLICATE_MARKET_DATE,
    EXTREME_ADJUSTED_DAILY_RETURN,
    INVALID_CLOSE_OUTSIDE_RANGE,
    INVALID_HIGH_LOW_RANGE,
    INVALID_OPEN_OUTSIDE_RANGE,
    MARKET_DATA_STALE_BEFORE_ANALYSIS_DATE,
    MISSING_REQUIRED_OHLCV_COLUMN,
    NEGATIVE_VOLUME,
    NO_MARKET_DATA_AVAILABLE,
    NO_SESSION_ON_OR_BEFORE_ANALYSIS_DATE,
    NON_FINITE_OHLC_VALUE,
    NON_POSITIVE_PRICE,
    NULL_OHLC_VALUE,
    POSSIBLE_PRICE_ADJUSTMENT_CONVENTION_MISMATCH,
    REPORTED_PRICE_MISMATCH,
    REPORTED_PRICE_OUTSIDE_DAILY_RANGE,
    REPORTED_PRICE_SESSION_NOT_FOUND,
    REVERSE_SPLIT_IN_ANALYSIS_WINDOW,
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    STOCK_SPLIT_IN_ANALYSIS_WINDOW,
    UNSORTED_MARKET_DATES,
)


def _row(date, **overrides):
    base = {
        "date": date,
        "open": 100.0,
        "high": 105.0,
        "low": 95.0,
        "close": 102.0,
        "adjusted_close": 102.0,
        "volume": 1000,
        "dividend": 0.0,
        "stock_split": 0.0,
        "capital_gain": 0.0,
    }
    base.update(overrides)
    return base


def _codes(warnings):
    return [w["code"] for w in warnings]


class TestMarketAvailability:
    def test_exact_analysis_date_has_exact_session(self):
        rows = [_row("2026-07-24")]
        result = check_market_availability(rows, dt.date(2026, 7, 24), dt.date(2026, 7, 24))
        assert result["analysis_date_has_exact_session"] is True
        assert result["last_available_session"] == "2026-07-24"
        assert _codes(result["warnings"]) == []

    def test_weekend_analysis_date_within_grace_is_info(self):
        # Friday session, Saturday analysis_date -- 1 calendar day gap.
        rows = [_row("2026-07-24")]
        result = check_market_availability(rows, dt.date(2026, 7, 25), dt.date(2026, 7, 25))
        assert result["analysis_date_has_exact_session"] is False
        assert _codes(result["warnings"]) == [ANALYSIS_DATE_NON_TRADING_DAY]
        assert result["warnings"][0]["severity"] == SEVERITY_INFO

    def test_nearest_session_within_four_days_is_info(self):
        rows = [_row("2026-07-20")]
        result = check_market_availability(rows, dt.date(2026, 7, 24), dt.date(2026, 7, 24))
        assert _codes(result["warnings"]) == [ANALYSIS_DATE_NON_TRADING_DAY]

    def test_stale_session_beyond_four_days_is_warning(self):
        rows = [_row("2026-07-18")]
        result = check_market_availability(rows, dt.date(2026, 7, 24), dt.date(2026, 7, 24))
        assert _codes(result["warnings"]) == [MARKET_DATA_STALE_BEFORE_ANALYSIS_DATE]
        assert result["warnings"][0]["severity"] == SEVERITY_WARNING
        assert result["warnings"][0]["details"]["gap_calendar_days"] == 6

    def test_future_analysis_date_is_warning(self):
        rows = [_row("2026-07-24")]
        result = check_market_availability(rows, dt.date(2026, 8, 1), dt.date(2026, 7, 24))
        assert ANALYSIS_DATE_IN_FUTURE in _codes(result["warnings"])

    def test_empty_data_is_critical(self):
        result = check_market_availability([], dt.date(2026, 7, 24), dt.date(2026, 7, 24))
        assert _codes(result["warnings"]) == [NO_MARKET_DATA_AVAILABLE]
        assert result["warnings"][0]["severity"] == SEVERITY_CRITICAL
        assert result["last_available_session"] is None

    def test_no_prior_session_is_critical(self):
        rows = [_row("2026-08-01")]
        result = check_market_availability(rows, dt.date(2026, 7, 24), dt.date(2026, 8, 1))
        assert _codes(result["warnings"]) == [NO_SESSION_ON_OR_BEFORE_ANALYSIS_DATE]
        assert result["warnings"][0]["severity"] == SEVERITY_CRITICAL
        assert result["last_available_session"] is None

    def test_saturday_with_no_bar_is_never_treated_as_a_data_error_alone(self):
        rows = [_row("2026-07-24")]
        result = check_market_availability(rows, dt.date(2026, 7, 25), dt.date(2026, 7, 25))
        assert all(w["severity"] != SEVERITY_CRITICAL for w in result["warnings"])


class TestOhlcvIntegrity:
    def test_clean_rows_produce_no_warnings(self):
        rows = [_row("2026-07-20"), _row("2026-07-21")]
        assert check_ohlcv_integrity(rows) == []

    def test_missing_required_column(self):
        row = _row("2026-07-20")
        del row["volume"]
        assert _codes(check_ohlcv_integrity([row])) == [MISSING_REQUIRED_OHLCV_COLUMN]

    def test_null_ohlc_value(self):
        assert _codes(check_ohlcv_integrity([_row("2026-07-20", close=None)])) == [NULL_OHLC_VALUE]

    def test_non_finite_ohlc_value(self):
        assert _codes(check_ohlcv_integrity([_row("2026-07-20", high=float("nan"))])) == [NON_FINITE_OHLC_VALUE]

    def test_non_positive_price(self):
        # low is widened so the non-positive open is still within [low, high]
        # -- isolating NON_POSITIVE_PRICE from INVALID_OPEN_OUTSIDE_RANGE.
        assert _codes(check_ohlcv_integrity([_row("2026-07-20", open=0.0, low=-1.0)])) == [NON_POSITIVE_PRICE]

    def test_negative_volume(self):
        assert _codes(check_ohlcv_integrity([_row("2026-07-20", volume=-5)])) == [NEGATIVE_VOLUME]

    def test_duplicate_market_date(self):
        rows = [_row("2026-07-20"), _row("2026-07-20")]
        assert _codes(check_ohlcv_integrity(rows)) == [DUPLICATE_MARKET_DATE]

    def test_unsorted_market_dates(self):
        rows = [_row("2026-07-21"), _row("2026-07-20")]
        assert _codes(check_ohlcv_integrity(rows)) == [UNSORTED_MARKET_DATES]

    def test_invalid_high_low_range(self):
        assert _codes(check_ohlcv_integrity([_row("2026-07-20", high=90.0, low=95.0)])) == [INVALID_HIGH_LOW_RANGE]

    def test_invalid_open_outside_range(self):
        assert _codes(check_ohlcv_integrity([_row("2026-07-20", open=200.0)])) == [INVALID_OPEN_OUTSIDE_RANGE]

    def test_invalid_close_outside_range(self):
        assert _codes(check_ohlcv_integrity([_row("2026-07-20", close=1.0)])) == [INVALID_CLOSE_OUTSIDE_RANGE]

    def test_missing_adjusted_close_does_not_fail_canonical_ohlcv(self):
        row = _row("2026-07-20")
        row["adjusted_close"] = None
        assert check_ohlcv_integrity([row]) == []


class TestCorporateActions:
    def test_stock_split(self):
        warnings, counts = check_corporate_actions([_row("2026-07-20", stock_split=4.0)])
        assert _codes(warnings) == [STOCK_SPLIT_IN_ANALYSIS_WINDOW]
        assert warnings[0]["severity"] == SEVERITY_INFO
        assert "Yahoo Finance reports" in warnings[0]["message"]
        assert counts["split_event_count"] == 1

    def test_reverse_split(self):
        warnings, counts = check_corporate_actions([_row("2026-07-20", stock_split=0.5)])
        assert _codes(warnings) == [REVERSE_SPLIT_IN_ANALYSIS_WINDOW]
        assert counts["reverse_split_event_count"] == 1

    def test_dividend(self):
        warnings, counts = check_corporate_actions([_row("2026-07-20", dividend=0.25)])
        assert _codes(warnings) == [DIVIDEND_IN_ANALYSIS_WINDOW]
        assert counts["dividend_event_count"] == 1

    def test_capital_gain(self):
        warnings, counts = check_corporate_actions([_row("2026-07-20", capital_gain=1.5)])
        assert _codes(warnings) == [CAPITAL_GAIN_IN_ANALYSIS_WINDOW]
        assert counts["capital_gain_event_count"] == 1

    def test_no_action(self):
        warnings, counts = check_corporate_actions([_row("2026-07-20")])
        assert warnings == []
        assert all(v == 0 for v in counts.values())

    def test_action_messages_never_claim_independent_confirmation(self):
        warnings, _ = check_corporate_actions([_row("2026-07-20", stock_split=4.0, dividend=0.25)])
        for warning in warnings:
            assert "COMQUTOR independently confirmed" not in warning["message"]


class TestExtremeReturns:
    def _pair(self, prev_close, curr_close):
        return [
            _row("2026-07-20", adjusted_close=prev_close),
            _row("2026-07-21", adjusted_close=curr_close),
        ]

    def test_39_percent_no_warning(self):
        warnings, status = check_extreme_returns(self._pair(100.0, 139.0))
        assert warnings == []
        assert status == "ok"

    def test_40_percent_warning(self):
        warnings, _ = check_extreme_returns(self._pair(100.0, 140.0))
        assert _codes(warnings) == [EXTREME_ADJUSTED_DAILY_RETURN]
        assert warnings[0]["severity"] == SEVERITY_WARNING

    def test_79_percent_warning(self):
        warnings, _ = check_extreme_returns(self._pair(100.0, 179.0))
        assert warnings[0]["severity"] == SEVERITY_WARNING

    def test_80_percent_critical(self):
        warnings, _ = check_extreme_returns(self._pair(100.0, 180.0))
        assert warnings[0]["severity"] == SEVERITY_CRITICAL

    def test_negative_return_also_triggers(self):
        warnings, _ = check_extreme_returns(self._pair(100.0, 55.0))
        assert warnings[0]["severity"] == SEVERITY_WARNING
        assert warnings[0]["details"]["return_percent"] < 0

    def test_negative_return_beyond_eighty_percent_is_critical(self):
        warnings, _ = check_extreme_returns(self._pair(100.0, 15.0))
        assert warnings[0]["severity"] == SEVERITY_CRITICAL
        assert warnings[0]["details"]["return_percent"] < 0

    def test_split_event_does_not_suppress_extreme_return_warning(self):
        rows = [
            _row("2026-07-20", adjusted_close=100.0),
            _row("2026-07-21", adjusted_close=145.0, stock_split=4.0),
        ]
        warnings, _ = check_extreme_returns(rows)
        assert _codes(warnings) == [EXTREME_ADJUSTED_DAILY_RETURN]

    def test_no_usable_adjusted_close_is_unavailable(self):
        rows = [_row("2026-07-20", adjusted_close=None)]
        warnings, status = check_extreme_returns(rows)
        assert warnings == []
        assert status == "unavailable"

    def test_warning_details_do_not_carry_full_ohlcv(self):
        warnings, _ = check_extreme_returns(self._pair(100.0, 145.0))
        assert set(warnings[0]["details"]) == {"date", "previous_date", "return_percent"}


class TestReportedPriceComparison:
    def _rows(self):
        return [_row("2026-07-20", open=100.0, close=102.0, low=98.0, high=104.0)]

    def test_exact_match_no_warning(self):
        extraction = {
            "claim_id": "c1", "reported_date": "2026-07-20", "reported_price": 100.0,
            "price_semantics": "open", "date_resolution": "explicit_year",
        }
        assert check_reported_prices([extraction], self._rows()) == []

    def test_within_five_percent_no_warning(self):
        extraction = {
            "claim_id": "c1", "reported_date": "2026-07-20", "reported_price": 104.0,
            "price_semantics": "open", "date_resolution": "explicit_year",
        }
        assert check_reported_prices([extraction], self._rows()) == []

    def test_beyond_five_percent_is_warning(self):
        extraction = {
            "claim_id": "c1", "reported_date": "2026-07-20", "reported_price": 108.0,
            "price_semantics": "open", "date_resolution": "explicit_year",
        }
        warnings = check_reported_prices([extraction], self._rows())
        assert _codes(warnings) == [REPORTED_PRICE_MISMATCH]
        assert warnings[0]["severity"] == SEVERITY_WARNING

    def test_beyond_fifty_percent_is_critical(self):
        extraction = {
            "claim_id": "c1", "reported_date": "2026-07-20", "reported_price": 200.0,
            "price_semantics": "close", "date_resolution": "explicit_year",
        }
        warnings = check_reported_prices([extraction], self._rows())
        assert warnings[0]["code"] == REPORTED_PRICE_MISMATCH
        assert warnings[0]["severity"] == SEVERITY_CRITICAL

    def test_within_daily_range_no_warning(self):
        extraction = {
            "claim_id": "c1", "reported_date": "2026-07-20", "reported_price": 103.0,
            "price_semantics": "reached", "date_resolution": "explicit_year",
        }
        assert check_reported_prices([extraction], self._rows()) == []

    def test_outside_daily_range_is_warning(self):
        extraction = {
            "claim_id": "c1", "reported_date": "2026-07-20", "reported_price": 115.0,
            "price_semantics": "peaked", "date_resolution": "explicit_year",
        }
        warnings = check_reported_prices([extraction], self._rows())
        assert _codes(warnings) == [REPORTED_PRICE_OUTSIDE_DAILY_RANGE]
        assert warnings[0]["severity"] == SEVERITY_WARNING

    def test_outside_daily_range_by_fifty_percent_is_critical(self):
        extraction = {
            "claim_id": "c1", "reported_date": "2026-07-20", "reported_price": 300.0,
            "price_semantics": "fell_to", "date_resolution": "explicit_year",
        }
        warnings = check_reported_prices([extraction], self._rows())
        assert warnings[0]["severity"] == SEVERITY_CRITICAL

    def test_non_trading_day_forward_limit_within_three_days_matches(self):
        # reported_date is a Sunday with no session; nearest prior session
        # (Friday, 2 days back) is within the 3-day grace window.
        rows = [_row("2026-07-17", open=100.0, close=100.0, low=98.0, high=101.0)]
        extraction = {
            "claim_id": "c1", "reported_date": "2026-07-19", "reported_price": 100.0,
            "price_semantics": "open", "date_resolution": "explicit_year",
        }
        warnings = check_reported_prices([extraction], rows)
        assert warnings == []

    def test_unmatched_session_beyond_three_days(self):
        rows = [_row("2026-07-10", open=100.0)]
        extraction = {
            "claim_id": "c1", "reported_date": "2026-07-20", "reported_price": 100.0,
            "price_semantics": "open", "date_resolution": "explicit_year",
        }
        warnings = check_reported_prices([extraction], rows)
        assert _codes(warnings) == [REPORTED_PRICE_SESSION_NOT_FOUND]
        assert warnings[0]["severity"] == SEVERITY_WARNING

    def test_split_window_adds_adjustment_convention_warning(self):
        rows = [_row("2026-07-20", open=100.0, close=102.0, low=98.0, high=104.0, stock_split=4.0)]
        extraction = {
            "claim_id": "c1", "reported_date": "2026-07-20", "reported_price": 400.0,
            "price_semantics": "open", "date_resolution": "explicit_year",
        }
        warnings = check_reported_prices([extraction], rows)
        codes = _codes(warnings)
        assert REPORTED_PRICE_MISMATCH in codes
        assert POSSIBLE_PRICE_ADJUSTMENT_CONVENTION_MISMATCH in codes
        adjustment_warning = next(w for w in warnings if w["code"] == POSSIBLE_PRICE_ADJUSTMENT_CONVENTION_MISMATCH)
        assert adjustment_warning["details"]["split_ratio"] == 4.0
        assert adjustment_warning["severity"] == SEVERITY_WARNING

    def test_mismatch_never_auto_resolved_or_rewritten(self):
        extraction = {
            "claim_id": "c1", "reported_date": "2026-07-20", "reported_price": 108.0,
            "price_semantics": "open", "date_resolution": "explicit_year",
        }
        original = dict(extraction)
        check_reported_prices([extraction], self._rows())
        assert extraction == original

    def test_warning_details_contain_required_fields_only_safe(self):
        extraction = {
            "claim_id": "c1", "reported_date": "2026-07-20", "reported_price": 108.0,
            "price_semantics": "open", "date_resolution": "explicit_year",
        }
        warnings = check_reported_prices([extraction], self._rows())
        details = warnings[0]["details"]
        assert set(details) == {
            "claim_id", "reported_date", "matched_session", "price_semantics",
            "reported_price", "external_reference", "relative_difference_percent", "date_resolution",
        }
        assert "source_text" not in details
