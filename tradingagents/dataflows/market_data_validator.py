"""Deterministic market-data verification snapshot.

The market analyst is an LLM that can confabulate exact numbers — citing a
Bollinger band or a "historically validated bounce" that the underlying data
doesn't support (#830). This module computes a ground-truth snapshot (latest
OHLCV row on or before the analysis date, common indicators, recent closes)
the analyst is told to treat as the source of truth for any exact numeric
claim. Deterministic, no LLM involved.
"""

from __future__ import annotations

from collections.abc import Iterable
from importlib.metadata import PackageNotFoundError, version

import pandas as pd
from stockstats import wrap

from comqutor_alpha.source_provenance import fragment_id_for, make_source_id
from tradingagents.dataflows.source_capture import record_source
from tradingagents.dataflows.stockstats_utils import load_ohlcv

try:
    _STOCKSTATS_VERSION = version("stockstats")
except PackageNotFoundError:  # pragma: no cover -- defensive only; stockstats is a hard dependency
    _STOCKSTATS_VERSION = "unknown"

# yfinance's own OHLCV rows are tz-naive by the time they reach this module
# (tradingagents.dataflows.y_finance strips tz info for display; the local
# CSV cache stores plain dates) -- this is the STANDARD assumed convention
# for a yfinance-sourced US-listed equity/ETF (Eastern, matching NYSE/NASDAQ
# trading hours), consistent with how every other module in this codebase
# already treats a yfinance "Date" value, never independently re-verified
# per instrument. Recorded explicitly here (never silently omitted) so a
# reader of the captured source record knows the convention assumed rather
# than guessing it.
_ASSUMED_MARKET_DATA_TIMEZONE = "America/New_York"

# A fixed, common indicator set so the snapshot is the same shape every run.
DEFAULT_SNAPSHOT_INDICATORS: tuple[str, ...] = (
    "close_10_ema", "close_50_sma", "close_200_sma",
    "rsi", "boll", "boll_ub", "boll_lb",
    "macd", "macds", "macdh", "atr",
)


def _verified_rows(symbol: str, curr_date: str) -> pd.DataFrame:
    """OHLCV on or before curr_date, date-sorted. Raises if nothing usable.

    ``load_ohlcv`` already normalizes the Date column and filters out
    look-ahead rows, but we re-apply the cutoff defensively — this is a
    verification path, so it must not trust its input to be pre-filtered.
    """
    data = load_ohlcv(symbol, curr_date)
    if data is None or data.empty:
        raise ValueError(f"No OHLCV data available for {symbol}.")

    df = data.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    df = df[df["Date"] <= pd.to_datetime(curr_date)].sort_values("Date")
    if df.empty:
        raise ValueError(f"No OHLCV rows on or before {curr_date} for {symbol}.")
    return df


def _fmt(value) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int,)):
        return str(value)
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _market_snapshot_source_ids(symbol: str, latest_date: str) -> tuple[str, str]:
    """Deterministic (source_id, fragment_id) pair for one symbol's verified
    snapshot as of one latest_date -- the SAME real functions (and the SAME
    id scheme) tradingagents.dataflows.yfinance_news already uses for the
    news chain, computed independently here (never imported state) so the
    id embedded in this call's own returned text is guaranteed to match
    what build_source_registry computes later from the captured record,
    by construction (both are pure functions of the same inputs)."""
    source_id = make_source_id(
        source_type="market",
        name="Yahoo Finance",
        title=f"{symbol.upper()} verified market snapshot {latest_date}",
        url="",
    )
    return source_id, fragment_id_for(source_id, 0)


def _capture_market_snapshot_source(
    *, symbol: str, curr_date: str, latest_date: str, ohlcv: dict[str, str],
    indicator_values: dict[str, str], excerpt: str, window_start: str, row_count: int,
    indicator_names: tuple[str, ...], verified_rows: pd.DataFrame | None = None,
) -> None:
    """Side-channel only (see tradingagents.dataflows.source_capture's own
    module docstring) -- registers this already-computed, deterministic
    verified-snapshot excerpt for source-traceability persistence. Never
    changes what build_verified_market_snapshot returns to the caller.

    ``calculation_method``/``calculation_version``/``calculation_params``
    (derived-indicator source chain, 2026-09-29): the indicator VALUES
    themselves are derived (stockstats, computed from the OHLCV window
    below) -- rather than duplicate the entire multi-row series inline
    (load_ohlcv caches up to 5 years per symbol), calculation_params
    records the exact INPUT SCOPE (symbol, date window, row count) plus the
    library version, which together with the same underlying OHLCV data
    source is sufficient to independently reproduce the identical values --
    proven directly in tests/test_t1_market_data_source_linking.py's own
    reproducibility test.

    T1 closeout (Round 22): that "same underlying OHLCV data source" is not
    something a saved run can rely on, so ``verified_rows`` -- the exact,
    date-sorted frame the indicators were computed from -- is now saved IN
    FULL (every row, not the last N) as a ``derived_inputs`` entry of the
    run's capture container (written as ``derived_inputs.json``), together
    with the method, library version, indicator definitions and the
    data-processing settings. ``calculation_params`` only gains two pointer
    keys (``input_series_artifact``, ``input_series_sha256``); the series
    itself stays out of the registry so the public source projections that
    copy ``calculation_params`` into every linked claim do not balloon.
    """
    calculation_params = {
        "symbol": symbol.upper(),
        "as_of_date": curr_date,
        "window_start": window_start,
        "window_end": latest_date,
        "row_count": row_count,
        "indicator_names": list(indicator_names),
    }
    if verified_rows is not None:
        try:
            from comqutor_alpha.capture_artifacts import DERIVED_INPUTS_FILENAME, build_ohlcv_input_record
            from tradingagents.dataflows.source_capture import aux_capture_active, record_aux
            from tradingagents.dataflows.stockstats_utils import ohlcv_processing_settings

            if aux_capture_active():
                source_id, _fragment_id = _market_snapshot_source_ids(symbol, latest_date)
                entry = build_ohlcv_input_record(
                    source_id=source_id, symbol=symbol, as_of_date=latest_date, requested_analysis_date=curr_date,
                    frame=verified_rows, indicator_names=indicator_names, indicator_values=indicator_values,
                    stockstats_version=_STOCKSTATS_VERSION, timezone_assumed=_ASSUMED_MARKET_DATA_TIMEZONE,
                    processing=ohlcv_processing_settings(),
                )
                calculation_params["input_series_artifact"] = DERIVED_INPUTS_FILENAME
                calculation_params["input_series_sha256"] = entry["series"]["sha256"]
                record_aux("derived_inputs", entry)
        except Exception:  # noqa: BLE001 -- a capture side-channel must never change or fail the snapshot
            calculation_params.pop("input_series_artifact", None)
            calculation_params.pop("input_series_sha256", None)
    record_source(
        {
            "source_type": "market",
            "name": "Yahoo Finance",
            "title": f"{symbol.upper()} verified market snapshot {latest_date}",
            "url": "",
            "published_at": f"{latest_date}T00:00:00",
            "provider": "yfinance",
            "excerpt": excerpt,
            "instrument": symbol.upper(),
            "observation_date": latest_date,
            "timezone": _ASSUMED_MARKET_DATA_TIMEZONE,
            "unit": "USD",
            "data_snapshot": {"ohlcv": ohlcv, "indicators": indicator_values, "requested_analysis_date": curr_date},
            "calculation_method": "stockstats",
            "calculation_version": f"stockstats=={_STOCKSTATS_VERSION}",
            "calculation_params": calculation_params,
        }
    )


def build_verified_market_snapshot(
    symbol: str,
    curr_date: str,
    look_back_days: int = 30,
    indicators: Iterable[str] | None = None,
) -> str:
    """Render a ground-truth snapshot: latest OHLCV row, indicators, recent closes."""
    # `df` keeps the original capitalized OHLCV columns (Open/High/Low/Close/
    # Volume); stockstats `wrap()` lowercases columns and adds indicator
    # columns, so read raw prices from `df` and indicators from `stock_df`.
    df = _verified_rows(symbol, curr_date)
    stock_df = wrap(df.copy())

    selected = tuple(indicators or DEFAULT_SNAPSHOT_INDICATORS)
    indicator_values: dict[str, str] = {}
    for name in selected:
        try:
            stock_df[name]  # triggers stockstats calculation
            indicator_values[name] = _fmt(stock_df.iloc[-1][name])
        except Exception as exc:  # noqa: BLE001 — one bad indicator shouldn't sink the snapshot
            indicator_values[name] = f"N/A ({type(exc).__name__})"

    latest = df.iloc[-1]
    latest_date = _fmt(latest["Date"])
    window = max(1, min(int(look_back_days), 30))
    recent = df.tail(window)

    ohlcv = {field: _fmt(latest.get(field)) for field in ("Open", "High", "Low", "Close", "Volume")}
    # Market-data source chain (2026-09-29, reuses the SAME source_registry/
    # gate/review/API/export machinery the news chain already wired -- the
    # deterministic excerpt below is what content_hash/fragment_id anchor
    # to, so it intentionally covers only the STABLE facts (latest row +
    # indicators), never the "recent closes" window (whose length varies
    # with look_back_days and would otherwise make the same real snapshot
    # hash differently depending on how it was called).
    excerpt = "; ".join(
        [f"{symbol.upper()} {latest_date} OHLCV " + " ".join(f"{k}={v}" for k, v in ohlcv.items())]
        + [f"{name}={value}" for name, value in indicator_values.items()]
    )
    source_id, fragment_id = _market_snapshot_source_ids(symbol, latest_date)
    _capture_market_snapshot_source(
        symbol=symbol, curr_date=curr_date, latest_date=latest_date,
        ohlcv=ohlcv, indicator_values=indicator_values, excerpt=excerpt,
        window_start=_fmt(df.iloc[0]["Date"]), row_count=len(df), indicator_names=selected,
        verified_rows=df,
    )
    # The marker is embedded INLINE, BEFORE the sentence's own closing
    # period (never on its own isolated line, and never preceded by
    # sentence-ending punctuation) -- structured_output_adapter's
    # deterministic sentence splitter treats a period as a segment
    # boundary, so a marker placed AFTER one splits into its OWN separate,
    # content-free segment (correctly dropped by the downstream claim-
    # quality filter as NON_SUBSTANTIVE before it would ever reach a public
    # API response). Keeping it inside the same sentence as the real,
    # numeric verified fact is what actually lets "the record id survives
    # into the claim" hold in practice, not merely in the raw persisted
    # artifact.
    #
    # ``moved`` is a real, data-derived intraday direction word (Close vs
    # Open on the SAME verified row -- never invented commentary, never
    # hardcoded to a fixed direction): claim_quality.py's own
    # STATE_OR_CHANGE_TERMS vocabulary ("rose"/"fell") requires an actual
    # directional/state-change signal to classify a claim as ANALYTICAL
    # rather than CONTEXT_ONLY -- a flat/unchanged close honestly has no
    # such signal and falls back to a neutral phrasing.
    close_value, open_value = latest.get("Close"), latest.get("Open")
    if pd.notna(close_value) and pd.notna(open_value) and close_value > open_value:
        moved = "rose to"
    elif pd.notna(close_value) and pd.notna(open_value) and close_value < open_value:
        moved = "fell to"
    else:
        moved = "was little changed at"
    summary_sentence = (
        f"Verified snapshot: {symbol.upper()}'s close {moved} {ohlcv['Close']} on {latest_date} "
        f"(Open {ohlcv['Open']}, High {ohlcv['High']}, Low {ohlcv['Low']}, Volume {ohlcv['Volume']}) "
        f"[source_id: {source_id}] [fragment_id: {fragment_id}]."
    )

    lines = [
        f"## Verified market data snapshot for {symbol.upper()}",
        "",
        summary_sentence,
        "",
        f"- Requested analysis date: {curr_date}",
        f"- Latest trading row used: {latest_date}",
        "- Rows after the requested analysis date are excluded before verification.",
        "",
        "### Latest verified OHLCV row",
        "",
        "| Field | Value |",
        "|---|---:|",
    ]
    for field in ("Open", "High", "Low", "Close", "Volume"):
        lines.append(f"| {field} | {_fmt(latest.get(field))} |")

    lines += ["", "### Verified technical indicators (latest row)", "",
              "| Indicator | Value |", "|---|---:|"]
    for name, value in indicator_values.items():
        lines.append(f"| {name} | {value} |")

    lines += ["", f"### Recent verified closes (last {len(recent)} rows)", "",
              "| Date | Close |", "|---|---:|"]
    for _, row in recent.iterrows():
        lines.append(f"| {_fmt(row['Date'])} | {_fmt(row.get('Close'))} |")

    lines += [
        "",
        "Use this snapshot as the source of truth for exact OHLCV, price-level, "
        "and indicator-value claims. If another tool output conflicts with it, "
        "flag the discrepancy rather than inventing a reconciled number. Do not "
        "claim historical validation, support/resistance bounces, or exact "
        "percentage moves unless directly supported by tool output with concrete "
        "dates and prices.",
    ]
    return "\n".join(lines)
