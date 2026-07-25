"""The yfinance market-data provider seam.

``YFinanceMarketDataProvider`` is the only piece of this package that talks
to yfinance/the network. Everything else (checker, pipeline, tests) depends
only on the plain ``get_history_rows(ticker, start_date, end_exclusive) ->
list[dict]`` contract, so tests inject a fake provider and never touch a
real socket.

``normalize_history_frames`` is a pure function over two already-fetched
pandas DataFrames (the "canonical" ``auto_adjust=False`` snapshot and the
"adjusted" ``auto_adjust=True`` snapshot) -- it is exercised directly in
tests with small hand-built DataFrames, still with zero network I/O.
"""

from __future__ import annotations

import datetime as dt

from comqutor_alpha.data_sanity.schema import (
    DATA_SANITY_PROVIDER_UNAVAILABLE,
    MAX_SOURCE_TEXT_CHARS,  # noqa: F401 -- re-exported for convenience of callers
    finite_int_or_none,
    finite_or_none,
)

MAX_SNAPSHOT_ROWS = 450

# Query-time yfinance parameters, explicit everywhere -- never relying on
# yfinance's own defaults.
CANONICAL_QUERY_KWARGS = {
    "interval": "1d",
    "actions": True,
    "auto_adjust": False,
    "repair": False,
}
ADJUSTED_QUERY_KWARGS = {
    "interval": "1d",
    "actions": False,
    "auto_adjust": True,
    "repair": False,
}


class MarketDataProviderError(Exception):
    """Safe provider-boundary error: a stable reason code only, never the
    raw provider/network exception message, URL, cookie, or credential."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _row_date_str(index_value) -> str:
    # yfinance returns a tz-aware DatetimeIndex (exchange-local time, e.g.
    # America/New_York) -- .date() takes the local calendar date directly,
    # which is the actual trading-session date, never UTC-shifted.
    value = index_value
    date_obj = value.date() if hasattr(value, "date") else value
    if isinstance(date_obj, dt.datetime):
        date_obj = date_obj.date()
    return date_obj.isoformat()


def normalize_history_frames(canonical_df, adjusted_df) -> list[dict]:
    """Turn the two raw yfinance DataFrames into the ``market_data_snapshot.
    json`` ``rows`` list: JSON-finite, plain ``YYYY-MM-DD`` dates, ascending,
    capped at ``MAX_SNAPSHOT_ROWS``. Never returns a DataFrame repr, a
    timezone object, or provider-internal metadata."""
    if canonical_df is None or len(canonical_df) == 0:
        return []

    adjusted_close_by_date: dict[str, object] = {}
    if adjusted_df is not None and len(adjusted_df) > 0:
        for index_value, adj_row in adjusted_df.iterrows():
            adjusted_close_by_date[_row_date_str(index_value)] = adj_row.get("Close")

    rows: list[dict] = []
    for index_value, row in canonical_df.iterrows():
        date_str = _row_date_str(index_value)
        rows.append(
            {
                "date": date_str,
                "open": finite_or_none(row.get("Open")),
                "high": finite_or_none(row.get("High")),
                "low": finite_or_none(row.get("Low")),
                "close": finite_or_none(row.get("Close")),
                "adjusted_close": finite_or_none(adjusted_close_by_date.get(date_str)),
                "volume": finite_int_or_none(row.get("Volume")),
                "dividend": finite_or_none(row.get("Dividends", 0.0)) or 0.0,
                "stock_split": finite_or_none(row.get("Stock Splits", 0.0)) or 0.0,
                "capital_gain": finite_or_none(row.get("Capital Gains", 0.0)) or 0.0,
            }
        )

    # Deduplicate by date (last write wins) and sort ascending -- defensive
    # even though a real yfinance response is already unique/sorted; the
    # snapshot artifact itself must never carry a corrupted ordering.
    by_date = {row["date"]: row for row in rows}
    ordered = sorted(by_date.values(), key=lambda row: row["date"])
    if len(ordered) > MAX_SNAPSHOT_ROWS:
        ordered = ordered[-MAX_SNAPSHOT_ROWS:]
    return ordered


class YFinanceMarketDataProvider:
    """Production provider. Every fetch failure (network, timeout, rate
    limit, invalid response, missing dependency, normalization failure) maps
    to ``MarketDataProviderError(DATA_SANITY_PROVIDER_UNAVAILABLE)`` -- the
    raw exception never reaches a log line, API response, or artifact."""

    provider_name = "yfinance"

    def __init__(self, timeout_seconds: int = 15) -> None:
        self.timeout_seconds = timeout_seconds

    def provider_version(self) -> str:
        try:
            import yfinance as yf

            return str(getattr(yf, "__version__", "unknown"))
        except Exception:
            return "unknown"

    def get_history_rows(
        self, ticker: str, start_date: dt.date, end_exclusive: dt.date
    ) -> list[dict]:
        try:
            import yfinance as yf
        except Exception as exc:
            raise MarketDataProviderError(DATA_SANITY_PROVIDER_UNAVAILABLE) from exc

        try:
            handle = yf.Ticker(str(ticker))
            canonical_df = handle.history(
                start=start_date.isoformat(),
                end=end_exclusive.isoformat(),
                timeout=self.timeout_seconds,
                **CANONICAL_QUERY_KWARGS,
            )
            adjusted_df = handle.history(
                start=start_date.isoformat(),
                end=end_exclusive.isoformat(),
                timeout=self.timeout_seconds,
                **ADJUSTED_QUERY_KWARGS,
            )
        except Exception as exc:
            raise MarketDataProviderError(DATA_SANITY_PROVIDER_UNAVAILABLE) from exc

        try:
            return normalize_history_frames(canonical_df, adjusted_df)
        except Exception as exc:
            raise MarketDataProviderError(DATA_SANITY_PROVIDER_UNAVAILABLE) from exc
