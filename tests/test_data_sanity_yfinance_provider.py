"""Provider normalization + provider-boundary tests for Data Sanity v1.

Zero real network: ``normalize_history_frames`` is exercised with small
hand-built pandas DataFrames, and ``YFinanceMarketDataProvider``'s own
exception-mapping is exercised by monkeypatching ``yfinance.Ticker`` to
raise -- never a real request.
"""

from __future__ import annotations

import datetime as dt
import json
import math

import pandas as pd
import pytest

from comqutor_alpha.data_sanity.yfinance_provider import (
    MAX_SNAPSHOT_ROWS,
    MarketDataProviderError,
    YFinanceMarketDataProvider,
    normalize_history_frames,
)


def _canonical_df(rows):
    index = pd.DatetimeIndex([r["date"] for r in rows], tz="America/New_York")
    return pd.DataFrame(
        {
            "Open": [r.get("open", 1.0) for r in rows],
            "High": [r.get("high", 1.0) for r in rows],
            "Low": [r.get("low", 1.0) for r in rows],
            "Close": [r.get("close", 1.0) for r in rows],
            "Volume": [r.get("volume", 100) for r in rows],
            "Dividends": [r.get("dividend", 0.0) for r in rows],
            "Stock Splits": [r.get("stock_split", 0.0) for r in rows],
            "Capital Gains": [r.get("capital_gain", 0.0) for r in rows],
        },
        index=index,
    )


def _adjusted_df(rows):
    index = pd.DatetimeIndex([r["date"] for r in rows], tz="America/New_York")
    return pd.DataFrame(
        {
            "Open": [r.get("open", 1.0) for r in rows],
            "High": [r.get("high", 1.0) for r in rows],
            "Low": [r.get("low", 1.0) for r in rows],
            "Close": [r.get("adjusted_close", r.get("close", 1.0)) for r in rows],
            "Volume": [r.get("volume", 100) for r in rows],
        },
        index=index,
    )


class TestNormalizeHistoryFrames:
    def test_normal_ohlcv_round_trips(self):
        canonical = _canonical_df(
            [{"date": "2026-07-20", "open": 90.0, "high": 96.0, "low": 89.0, "close": 95.0, "volume": 1000}]
        )
        adjusted = _adjusted_df([{"date": "2026-07-20", "adjusted_close": 94.5}])
        rows = normalize_history_frames(canonical, adjusted)
        assert rows == [
            {
                "date": "2026-07-20",
                "open": 90.0,
                "high": 96.0,
                "low": 89.0,
                "close": 95.0,
                "adjusted_close": 94.5,
                "volume": 1000,
                "dividend": 0.0,
                "stock_split": 0.0,
                "capital_gain": 0.0,
            }
        ]

    def test_nan_converted_to_null(self):
        canonical = _canonical_df([{"date": "2026-07-20"}])
        canonical.loc[canonical.index[0], "Close"] = float("nan")
        canonical.loc[canonical.index[0], "Volume"] = float("nan")
        adjusted = _adjusted_df([{"date": "2026-07-20", "adjusted_close": float("nan")}])
        rows = normalize_history_frames(canonical, adjusted)
        assert rows[0]["close"] is None
        assert rows[0]["volume"] is None
        assert rows[0]["adjusted_close"] is None

    def test_timezone_aware_index_normalizes_to_local_calendar_date(self):
        # America/New_York local midnight bars -- .date() must take the
        # exchange-local calendar date, never a UTC-shifted one.
        index = pd.DatetimeIndex(["2026-03-10"], tz="America/New_York")
        canonical = pd.DataFrame(
            {
                "Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0], "Volume": [1],
                "Dividends": [0.0], "Stock Splits": [0.0], "Capital Gains": [0.0],
            },
            index=index,
        )
        rows = normalize_history_frames(canonical, None)
        assert rows[0]["date"] == "2026-03-10"

    def test_action_columns_captured(self):
        canonical = _canonical_df(
            [{"date": "2026-06-01", "dividend": 0.25, "stock_split": 4.0, "capital_gain": 1.5}]
        )
        rows = normalize_history_frames(canonical, None)
        assert rows[0]["dividend"] == 0.25
        assert rows[0]["stock_split"] == 4.0
        assert rows[0]["capital_gain"] == 1.5

    def test_more_than_450_rows_truncated_to_most_recent_450(self):
        dates = [(dt.date(2020, 1, 1) + dt.timedelta(days=i)).isoformat() for i in range(500)]
        canonical = _canonical_df([{"date": d, "close": i * 1.0} for i, d in enumerate(dates)])
        rows = normalize_history_frames(canonical, None)
        assert len(rows) == MAX_SNAPSHOT_ROWS
        assert rows[0]["date"] == dates[-MAX_SNAPSHOT_ROWS]
        assert rows[-1]["date"] == dates[-1]
        assert rows == sorted(rows, key=lambda r: r["date"])

    def test_json_finite_end_to_end(self):
        canonical = _canonical_df([{"date": "2026-07-20"}])
        canonical.loc[canonical.index[0], "High"] = float("inf")
        rows = normalize_history_frames(canonical, None)
        serialized = json.dumps(rows)
        assert "Infinity" not in serialized
        assert "NaN" not in serialized
        reloaded = json.loads(serialized)
        assert reloaded[0]["high"] is None

    def test_empty_canonical_returns_empty_list(self):
        empty = pd.DataFrame()
        assert normalize_history_frames(empty, None) == []
        assert normalize_history_frames(None, None) == []


class TestYFinanceMarketDataProviderBoundary:
    def test_underlying_exception_maps_to_stable_reason_code(self, monkeypatch):
        import yfinance as yf

        class _RaisingTicker:
            def __init__(self, *_args, **_kwargs):
                pass

            def history(self, *_args, **_kwargs):
                raise RuntimeError("connection reset by peer at https://query1.finance.yahoo.com/secret")

        monkeypatch.setattr(yf, "Ticker", _RaisingTicker)
        provider = YFinanceMarketDataProvider(timeout_seconds=5)
        with pytest.raises(MarketDataProviderError) as exc_info:
            provider.get_history_rows("MU", dt.date(2026, 1, 1), dt.date(2026, 2, 1))
        # The raw exception text (which could carry a URL) never leaks into
        # the stable reason code.
        assert "query1.finance.yahoo.com" not in exc_info.value.reason_code
        assert exc_info.value.reason_code == "DATA_SANITY_PROVIDER_UNAVAILABLE"

    def test_timeout_like_exception_maps_to_stable_reason_code(self, monkeypatch):
        import yfinance as yf

        class _TimeoutError(Exception):
            pass

        class _TimingOutTicker:
            def __init__(self, *_args, **_kwargs):
                pass

            def history(self, *_args, **_kwargs):
                raise _TimeoutError("Read timed out")

        monkeypatch.setattr(yf, "Ticker", _TimingOutTicker)
        provider = YFinanceMarketDataProvider(timeout_seconds=1)
        with pytest.raises(MarketDataProviderError) as exc_info:
            provider.get_history_rows("MU", dt.date(2026, 1, 1), dt.date(2026, 2, 1))
        assert exc_info.value.reason_code == "DATA_SANITY_PROVIDER_UNAVAILABLE"

    def test_explicit_query_kwargs_never_rely_on_defaults(self, monkeypatch):
        import yfinance as yf

        calls = []

        class _RecordingTicker:
            def __init__(self, ticker, *_args, **_kwargs):
                self.ticker = ticker

            def history(self, **kwargs):
                calls.append(kwargs)
                return pd.DataFrame()

        monkeypatch.setattr(yf, "Ticker", _RecordingTicker)
        provider = YFinanceMarketDataProvider(timeout_seconds=7)
        provider.get_history_rows("MU", dt.date(2026, 1, 1), dt.date(2026, 2, 1))

        assert len(calls) == 2
        canonical_call, adjusted_call = calls
        assert canonical_call["interval"] == "1d"
        assert canonical_call["actions"] is True
        assert canonical_call["auto_adjust"] is False
        assert canonical_call["repair"] is False
        assert canonical_call["timeout"] == 7
        assert adjusted_call["interval"] == "1d"
        assert adjusted_call["actions"] is False
        assert adjusted_call["auto_adjust"] is True
        assert adjusted_call["repair"] is False
        assert adjusted_call["timeout"] == 7

    def test_no_secrets_in_error_boundary(self, monkeypatch):
        """The provider error object carries only a stable reason code --
        never cookies, session state, or request headers."""
        import yfinance as yf

        class _RaisingTicker:
            def __init__(self, *_args, **_kwargs):
                pass

            def history(self, *_args, **_kwargs):
                raise RuntimeError("Cookie: sessionid=abc123; Authorization: Bearer sk-secret")

        monkeypatch.setattr(yf, "Ticker", _RaisingTicker)
        provider = YFinanceMarketDataProvider()
        with pytest.raises(MarketDataProviderError) as exc_info:
            provider.get_history_rows("MU", dt.date(2026, 1, 1), dt.date(2026, 2, 1))
        assert "sk-secret" not in str(exc_info.value)
        assert "sessionid" not in str(exc_info.value)
        assert str(exc_info.value) == "DATA_SANITY_PROVIDER_UNAVAILABLE"


def test_finite_helpers_reject_nan_and_infinity():
    from comqutor_alpha.data_sanity.schema import finite_int_or_none, finite_or_none

    assert finite_or_none(float("nan")) is None
    assert finite_or_none(float("inf")) is None
    assert finite_or_none(float("-inf")) is None
    assert finite_or_none(None) is None
    assert finite_or_none(5) == 5.0
    assert finite_int_or_none(float("nan")) is None
    assert finite_int_or_none(1500.0) == 1500
    assert math.isfinite(finite_or_none(3.14))
