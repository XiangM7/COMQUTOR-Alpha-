import math
from datetime import datetime
from typing import Annotated

import pandas as pd
import yfinance as yf
from dateutil.relativedelta import relativedelta

from comqutor_alpha.source_provenance import fragment_id_for, make_source_id

from .source_capture import record_source
from .stockstats_utils import (
    StockstatsUtils,
    _assert_ohlcv_not_stale,
    filter_financials_by_date,
    load_ohlcv,
    yf_retry,
)
from .symbol_utils import NoMarketDataError, normalize_symbol


def get_YFin_data_online(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
):

    datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    # Resolve broker/forex symbols to Yahoo's convention (XAUUSD+ -> GC=F).
    canonical = normalize_symbol(symbol)
    ticker = yf.Ticker(canonical)

    # yfinance treats ``end`` as EXCLUSIVE, so it would drop the requested
    # end_date row (and the current day when end_date is today). Request one day
    # past end_date so the requested range is actually inclusive (#986/#987).
    end_inclusive = (end_dt + relativedelta(days=1)).strftime("%Y-%m-%d")
    data = yf_retry(lambda: ticker.history(start=start_date, end=end_inclusive))

    # Empty result means the symbol is unknown/delisted. Raise a typed error
    # instead of returning prose: the routing layer turns it into a single
    # unambiguous "no data" signal so the agent never fabricates a price.
    if data.empty:
        raise NoMarketDataError(
            symbol, canonical, f"no rows between {start_date} and {end_date}"
        )

    # Remove timezone info from index for cleaner output
    if data.index.tz is not None:
        data.index = data.index.tz_localize(None)

    # Reject a stale frame (e.g. a year-old partial response) before it is
    # formatted into the report. Raises NoMarketDataError, which the router
    # turns into one clear unavailable signal (#1021).
    _assert_ohlcv_not_stale(data, end_date, symbol, canonical)

    # Round numerical values to 2 decimal places for cleaner display
    numeric_columns = ["Open", "High", "Low", "Close", "Adj Close"]
    for col in numeric_columns:
        if col in data.columns:
            data[col] = data[col].round(2)

    # Convert DataFrame to CSV string
    csv_string = data.to_csv()

    # Add header information; note the resolved symbol when it differs so the
    # agent (and user) can see which instrument was actually priced.
    label = canonical if canonical == symbol.upper() else f"{canonical} (from {symbol})"
    header = f"# Stock data for {label} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(data)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string

def get_stock_stats_indicators_window(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[
        str, "The current trading date you are trading on, YYYY-mm-dd"
    ],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:

    best_ind_params = {
        # Moving Averages
        "close_50_sma": (
            "50 SMA: A medium-term trend indicator. "
            "Usage: Identify trend direction and serve as dynamic support/resistance. "
            "Tips: It lags price; combine with faster indicators for timely signals."
        ),
        "close_200_sma": (
            "200 SMA: A long-term trend benchmark. "
            "Usage: Confirm overall market trend and identify golden/death cross setups. "
            "Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries."
        ),
        "close_10_ema": (
            "10 EMA: A responsive short-term average. "
            "Usage: Capture quick shifts in momentum and potential entry points. "
            "Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals."
        ),
        # MACD Related
        "macd": (
            "MACD: Computes momentum via differences of EMAs. "
            "Usage: Look for crossovers and divergence as signals of trend changes. "
            "Tips: Confirm with other indicators in low-volatility or sideways markets."
        ),
        "macds": (
            "MACD Signal: An EMA smoothing of the MACD line. "
            "Usage: Use crossovers with the MACD line to trigger trades. "
            "Tips: Should be part of a broader strategy to avoid false positives."
        ),
        "macdh": (
            "MACD Histogram: Shows the gap between the MACD line and its signal. "
            "Usage: Visualize momentum strength and spot divergence early. "
            "Tips: Can be volatile; complement with additional filters in fast-moving markets."
        ),
        # Momentum Indicators
        "rsi": (
            "RSI: Measures momentum to flag overbought/oversold conditions. "
            "Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. "
            "Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis."
        ),
        # Volatility Indicators
        "boll": (
            "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. "
            "Usage: Acts as a dynamic benchmark for price movement. "
            "Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals."
        ),
        "boll_ub": (
            "Bollinger Upper Band: Typically 2 standard deviations above the middle line. "
            "Usage: Signals potential overbought conditions and breakout zones. "
            "Tips: Confirm signals with other tools; prices may ride the band in strong trends."
        ),
        "boll_lb": (
            "Bollinger Lower Band: Typically 2 standard deviations below the middle line. "
            "Usage: Indicates potential oversold conditions. "
            "Tips: Use additional analysis to avoid false reversal signals."
        ),
        "atr": (
            "ATR: Averages true range to measure volatility. "
            "Usage: Set stop-loss levels and adjust position sizes based on current market volatility. "
            "Tips: It's a reactive measure, so use it as part of a broader risk management strategy."
        ),
        # Volume-Based Indicators
        "vwma": (
            "VWMA: A moving average weighted by volume. "
            "Usage: Confirm trends by integrating price action with volume data. "
            "Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses."
        ),
        "mfi": (
            "MFI: The Money Flow Index is a momentum indicator that uses both price and volume to measure buying and selling pressure. "
            "Usage: Identify overbought (>80) or oversold (<20) conditions and confirm the strength of trends or reversals. "
            "Tips: Use alongside RSI or MACD to confirm signals; divergence between price and MFI can indicate potential reversals."
        ),
    }

    if indicator not in best_ind_params:
        raise ValueError(
            f"Indicator {indicator} is not supported. Please choose from: {list(best_ind_params.keys())}"
        )

    end_date = curr_date
    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_date_dt - relativedelta(days=look_back_days)

    # Optimized: Get stock data once and calculate indicators for all dates
    try:
        indicator_data = _get_stock_stats_bulk(symbol, indicator, curr_date)

        # Generate the date range we need
        current_dt = curr_date_dt
        date_values = []

        while current_dt >= before:
            date_str = current_dt.strftime('%Y-%m-%d')

            # Look up the indicator value for this date
            if date_str in indicator_data:
                indicator_value = indicator_data[date_str]
            else:
                indicator_value = "N/A: Not a trading day (weekend or holiday)"

            date_values.append((date_str, indicator_value))
            current_dt = current_dt - relativedelta(days=1)

        # Build the result string
        ind_string = ""
        for date_str, value in date_values:
            ind_string += f"{date_str}: {value}\n"

    except NoMarketDataError:
        raise  # Unknown/delisted symbol — let the router emit the sentinel
    except Exception as e:
        print(f"Error getting bulk stockstats data: {e}")
        # Fallback to original implementation if bulk method fails
        ind_string = ""
        curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        while curr_date_dt >= before:
            indicator_value = get_stockstats_indicator(
                symbol, indicator, curr_date_dt.strftime("%Y-%m-%d")
            )
            ind_string += f"{curr_date_dt.strftime('%Y-%m-%d')}: {indicator_value}\n"
            curr_date_dt = curr_date_dt - relativedelta(days=1)

    result_str = (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {end_date}:\n\n"
        + ind_string
        + "\n\n"
        + best_ind_params.get(indicator, "No description available.")
    )

    return result_str


def _get_stock_stats_bulk(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to calculate"],
    curr_date: Annotated[str, "current date for reference"]
) -> dict:
    """
    Optimized bulk calculation of stock stats indicators.
    Fetches data once and calculates indicator for all available dates.
    Returns dict mapping date strings to indicator values.
    """
    from stockstats import wrap

    data = load_ohlcv(symbol, curr_date)
    df = wrap(data)
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

    # Calculate the indicator for all rows at once
    df[indicator]  # This triggers stockstats to calculate the indicator

    # Create a dictionary mapping date strings to indicator values
    result_dict = {}
    for _, row in df.iterrows():
        date_str = row["Date"]
        indicator_value = row[indicator]

        # Handle NaN/None values
        if pd.isna(indicator_value):
            result_dict[date_str] = "N/A"
        else:
            result_dict[date_str] = str(indicator_value)

    return result_dict


def get_stockstats_indicator(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[
        str, "The current trading date you are trading on, YYYY-mm-dd"
    ],
) -> str:

    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    curr_date = curr_date_dt.strftime("%Y-%m-%d")

    try:
        indicator_value = StockstatsUtils.get_stock_stats(
            symbol,
            indicator,
            curr_date,
        )
    except NoMarketDataError:
        raise  # Unknown/delisted symbol — let the router emit the sentinel
    except Exception as e:
        print(
            f"Error getting stockstats indicator data for indicator {indicator} on {curr_date}: {e}"
        )
        return ""

    return str(indicator_value)


# T1 financial-data fix round (2026-10-04, John task-sheet section 3): ONE
# canonical field table drives BOTH the text get_fundamentals shows the
# Agent AND the fields captured into the source registry -- the two can
# never drift apart ("output one set, save another") by construction.
# (provider .info key, display label, unit kind, stable snake_case snapshot key)
# unit kind vocabulary:
#   "currency"            -- a monetary amount, in the ticker's own reporting currency
#   "per_share_currency"  -- a monetary amount per share, same currency
#   "ratio"               -- dimensionless
#   "percent_fraction"    -- yfinance's own 0..1 fraction convention, never rescaled
#   "text"                -- non-numeric
_FUNDAMENTALS_FIELD_TABLE: tuple[tuple[str, str, str, str], ...] = (
    ("longName", "Name", "text", "name"),
    ("sector", "Sector", "text", "sector"),
    ("industry", "Industry", "text", "industry"),
    ("marketCap", "Market Cap", "currency", "market_cap"),
    ("trailingPE", "PE Ratio (TTM)", "ratio", "trailing_pe"),
    ("forwardPE", "Forward PE", "ratio", "forward_pe"),
    ("pegRatio", "PEG Ratio", "ratio", "peg_ratio"),
    ("priceToBook", "Price to Book", "ratio", "price_to_book"),
    ("trailingEps", "EPS (TTM)", "per_share_currency", "trailing_eps"),
    ("forwardEps", "Forward EPS", "per_share_currency", "forward_eps"),
    ("dividendYield", "Dividend Yield", "percent_fraction", "dividend_yield"),
    ("beta", "Beta", "ratio", "beta"),
    ("fiftyTwoWeekHigh", "52 Week High", "currency", "fifty_two_week_high"),
    ("fiftyTwoWeekLow", "52 Week Low", "currency", "fifty_two_week_low"),
    ("fiftyDayAverage", "50 Day Average", "currency", "fifty_day_average"),
    ("twoHundredDayAverage", "200 Day Average", "currency", "two_hundred_day_average"),
    ("totalRevenue", "Revenue (TTM)", "currency", "total_revenue"),
    ("grossProfits", "Gross Profit", "currency", "gross_profit"),
    ("ebitda", "EBITDA", "currency", "ebitda"),
    ("netIncomeToCommon", "Net Income", "currency", "net_income"),
    ("profitMargins", "Profit Margin", "percent_fraction", "profit_margin"),
    ("operatingMargins", "Operating Margin", "percent_fraction", "operating_margin"),
    ("returnOnEquity", "Return on Equity", "percent_fraction", "return_on_equity"),
    ("returnOnAssets", "Return on Assets", "percent_fraction", "return_on_assets"),
    ("debtToEquity", "Debt to Equity", "ratio", "debt_to_equity"),
    ("currentRatio", "Current Ratio", "ratio", "current_ratio"),
    ("bookValue", "Book Value", "per_share_currency", "book_value_per_share"),
    ("freeCashflow", "Free Cash Flow", "currency", "free_cash_flow"),
)


def _json_safe_number(value):
    """Converts a raw provider/pandas/numpy numeric value to a plain,
    JSON-safe Python float, preserving 0 distinctly from missing. Standard
    JSON cannot represent NaN/Infinity -- both become ``None`` here (treated
    as "not provided", never silently coerced to 0 and never left as a
    non-standard float that would corrupt a persisted artifact). Returns
    ``None`` for ``None`` input; returns the input unchanged if it is not
    numeric at all (e.g. a text field passed in by mistake)."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _unit_label(unit_kind: str, currency: str | None) -> str:
    """Per-field unit label for ``data_snapshot["field_units"]`` -- currency
    fields use the ticker's own real reported currency when known, never a
    hardcoded assumption; ``UNKNOWN_CURRENCY`` only when the provider
    genuinely did not say."""
    if unit_kind == "currency":
        return currency or "UNKNOWN_CURRENCY"
    if unit_kind == "per_share_currency":
        return f"{currency}_per_share" if currency else "UNKNOWN_CURRENCY_per_share"
    if unit_kind == "percent_fraction":
        return "fraction_0_to_1"
    if unit_kind == "ratio":
        return "ratio"
    return "text"


def _fundamentals_source_ids(canonical: str, retrieved_at_str: str) -> tuple[str, str]:
    """Deterministic (source_id, fragment_id) for one fundamentals fetch --
    the SAME make_source_id/fragment_id_for functions the news and market
    chains already use, computed independently here (never imported state)
    so it matches, by construction, what build_source_registry computes
    later from the captured record."""
    source_id = make_source_id(
        source_type="financial",
        name="Yahoo Finance",
        title=f"{canonical} fundamentals snapshot {retrieved_at_str}",
        url="",
    )
    return source_id, fragment_id_for(source_id, 0)


def _fundamentals_summary_sentence(canonical: str, info: dict, retrieved_at_dt: datetime) -> str:
    """Financial-data source chain (2026-09-29, reuses the SAME source_
    registry/gate/review/API/export machinery the news/market chains
    already wired -- no parallel system).

    Financial-data timing caveat (DELIBERATE scope boundary, never silently
    papered over): yfinance's own balance-sheet/cashflow/income-statement
    endpoints expose only a FISCAL PERIOD END date as their column identity
    -- never a real disclosure/filing date -- and conflating a report
    period with its actual public-disclosure time would be a genuine
    look-ahead risk this module does not attempt to paper over with a
    guessed offset (see ``_statement_summary_sentence``). get_fundamentals's
    own `.info` fields (market cap, trailing PE, etc.) are different in
    kind: they are CURRENT, live-computed ratios (trailing-twelve-month
    based), not a specific past fiscal disclosure -- so the one honest
    temporal anchor available is "as retrieved right now", used as
    published_at below, exactly like a live quote.

    2026-10-04 (T1 financial-data fix round, John task-sheet section 3):
    every field actually present in this SAME already-fetched ``info`` dict
    (per ``_FUNDAMENTALS_FIELD_TABLE`` -- the SAME table ``get_fundamentals``
    uses to build the Agent-visible text) is now captured into
    ``data_snapshot``, each under its own stable key with its own unit
    classification -- not just market_cap/trailing_pe. Currency is read
    from this same ``info`` dict's own ``currency``/``financialCurrency``
    field (zero additional Provider calls); ``UNKNOWN_CURRENCY`` when the
    provider did not say, never assumed to be USD. Exactly one source
    record is still produced per call (multiple fields sharing one
    fragment, never split into separate sources -- see John task-sheet
    section 3 point 6); each field is individually locatable inside it by
    its own key in ``data_snapshot``/``field_units``, not only by a vague
    overall title. No automatic valuation judgment ("remains elevated",
    "cheap", "expensive") is generated any more: a bare non-zero P/E is not
    evidence of being high or low without an explicit comparison baseline,
    which this function does not have (section 3 point 8) -- the summary
    states retrieved facts neutrally.
    """
    currency = info.get("currency") or info.get("financialCurrency")
    present_fields: list[tuple[str, str, object, str]] = []
    for provider_key, display_label, unit_kind, snapshot_key in _FUNDAMENTALS_FIELD_TABLE:
        raw_value = info.get(provider_key)
        if raw_value is None:
            continue
        value = _json_safe_number(raw_value) if unit_kind != "text" else raw_value
        if value is None and unit_kind != "text":
            continue  # genuinely NaN/Infinity at the provider boundary -- treated as not provided, never as 0
        present_fields.append((snapshot_key, display_label, value, _unit_label(unit_kind, currency)))

    if not present_fields:
        return ""

    retrieved_at_str = retrieved_at_dt.strftime("%Y-%m-%d %H:%M:%S")
    source_id, fragment_id = _fundamentals_source_ids(canonical, retrieved_at_str)

    excerpt_parts = [f"{canonical} fundamentals as retrieved on {retrieved_at_str}"]
    data_snapshot: dict[str, object] = {"currency": currency}
    field_units: dict[str, str] = {}
    for snapshot_key, display_label, value, unit_label in present_fields:
        excerpt_parts.append(f"{display_label}={value}")
        data_snapshot[snapshot_key] = value
        field_units[snapshot_key] = unit_label
    data_snapshot["field_units"] = field_units
    excerpt = " ".join(excerpt_parts)

    record_source(
        {
            "source_type": "financial",
            "name": "Yahoo Finance",
            "title": f"{canonical} fundamentals snapshot {retrieved_at_str}",
            "url": "",
            # Deliberately the RETRIEVAL timestamp, never a fiscal period
            # end date -- see this function's own docstring.
            "published_at": retrieved_at_dt.isoformat(),
            "provider": "yfinance",
            "excerpt": excerpt,
            "instrument": canonical,
            "observation_date": retrieved_at_dt.strftime("%Y-%m-%d"),
            # Mixed-unit report (currency fields alongside dimensionless
            # ratios and percent-fractions) -- no single honest top-level
            # "unit" value; see data_snapshot["field_units"] for the real,
            # per-field unit, never fabricated as a blanket "USD".
            "unit": None,
            "data_snapshot": data_snapshot,
        }
    )

    market_cap = data_snapshot.get("market_cap")
    trailing_pe = data_snapshot.get("trailing_pe")
    currency_label = currency or "UNKNOWN_CURRENCY"
    clauses = []
    if market_cap is not None:
        clauses.append(f"{canonical}'s market capitalization stood at {market_cap} ({currency_label})")
    if trailing_pe is not None:
        clauses.append(f"trailing P/E (TTM) was {trailing_pe}")
    if not clauses:
        clauses.append(f"{len(present_fields)} verified fundamentals field(s) were captured")
    body = "; ".join(clauses)
    return (
        f"Verified fundamentals: {body} as of {retrieved_at_str} "
        f"[source_id: {source_id}] [fragment_id: {fragment_id}]."
    )


def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date (not used for yfinance)"] = None
):
    """Get company fundamentals overview from yfinance.

    2026-10-04 (T1 financial-data fix round): the displayed field list below
    and the fields captured into the source registry
    (``_fundamentals_summary_sentence``) are now built by iterating the SAME
    ``_FUNDAMENTALS_FIELD_TABLE`` -- never two independently-maintained
    lists that could silently drift apart. A value that is genuinely
    NaN/Infinity at the provider boundary is treated as not provided (never
    printed as literal "nan"/"inf" text, never coerced to 0).
    """
    canonical = normalize_symbol(ticker)
    try:
        ticker_obj = yf.Ticker(canonical)
        info = yf_retry(lambda: ticker_obj.info)

        if not info:
            raise NoMarketDataError(ticker, canonical, "no fundamentals returned")

        lines = []
        for provider_key, display_label, unit_kind, _snapshot_key in _FUNDAMENTALS_FIELD_TABLE:
            raw_value = info.get(provider_key)
            if raw_value is None:
                continue
            display_value = _json_safe_number(raw_value) if unit_kind != "text" else raw_value
            if display_value is None and unit_kind != "text":
                continue
            lines.append(f"{display_label}: {display_value}")

        # yfinance returns a stub dict (e.g. {"trailingPegRatio": None}) for
        # unknown symbols, so `info` is truthy but every field is empty. Treat
        # "no usable fields" as no data rather than emitting a bare header the
        # agent might fabricate around.
        if not lines:
            raise NoMarketDataError(ticker, canonical, "no fundamental fields returned")

        retrieved_at_dt = datetime.now()
        retrieved_at_str = retrieved_at_dt.strftime("%Y-%m-%d %H:%M:%S")
        header = f"# Company Fundamentals for {canonical}\n"
        header += f"# Data retrieved on: {retrieved_at_str}\n\n"

        summary_sentence = _fundamentals_summary_sentence(canonical, info, retrieved_at_dt)

        return header + "\n".join(lines) + ("\n\n" + summary_sentence if summary_sentence else "")

    except NoMarketDataError:
        raise
    except Exception as e:
        return f"Error retrieving fundamentals for {ticker}: {str(e)}"


# Financial-STATEMENT source chain (2026-09-29, extends the get_fundamentals
# chain to the three statement endpoints John's own task explicitly asked
# not to leave excluded just because of the disclosure-timing ambiguity --
# see _statement_summary_sentence's own docstring for how that ambiguity is
# actually handled, not papered over). One well-known, usually-present line
# item per statement is enough to prove the chain end-to-end; not every
# line item on every statement is individually source-linked.
_BALANCE_SHEET_LINE_ITEM_CANDIDATES = ("Total Assets", "Stockholders Equity", "Total Liab")
_CASHFLOW_LINE_ITEM_CANDIDATES = (
    "Free Cash Flow",
    "Operating Cash Flow",
    "Cash Flow From Continuing Operating Activities",
)
_INCOME_STATEMENT_LINE_ITEM_CANDIDATES = ("Total Revenue", "Net Income", "Operating Income")


def _pick_first_present_row(data, candidates: tuple[str, ...]):
    """First candidate row name that exists in `data` and has at least one
    non-null value -- never guesses at a name not in this specific
    ticker's own real reported line items."""
    for name in candidates:
        if name in data.index:
            row = data.loc[name].dropna()
            if not row.empty:
                return name, row
    return None, None


def _period_relationship_label(current_label: str, prior_label: str) -> str:
    """Names the relationship between two statement periods ONLY when the
    real calendar gap matches a recognized convention -- never assumes
    'quarter-over-quarter' or 'year-over-year' merely because two periods
    happen to be adjacent columns in the same row (John task-sheet section
    5 point 2: 'only compare periods whose meaning and basis are genuinely
    comparable... do not call the two most recent available periods
    sequential/QoQ or YoY unless the period relationship actually satisfies
    that name'). Falls back to stating both periods literally."""
    try:
        gap_days = abs((pd.Timestamp(current_label) - pd.Timestamp(prior_label)).days)
    except (TypeError, ValueError):
        return f"{current_label} vs {prior_label}"
    if 80 <= gap_days <= 100:
        return f"sequential quarter-over-quarter, {current_label} vs {prior_label}"
    if 355 <= gap_days <= 375:
        return f"year-over-year, {current_label} vs {prior_label}"
    return f"{current_label} vs {prior_label} (gap of {gap_days} days)"


# Round 2 (2026-10-04): a small, well-known, stable set of yfinance
# statement line items that are NOT a monetary amount -- not verified
# against a live call this round (zero network), but these are documented,
# stable field names, not a per-value guess. Every OTHER line item in a
# balance sheet / cash flow / income statement is a monetary amount BY
# DEFINITION of what these three statements are; that is a structural fact
# about the statement type, not an assumption about any individual field.
_PER_SHARE_STATEMENT_LINE_ITEMS = frozenset({"Basic EPS", "Diluted EPS"})
_SHARE_COUNT_STATEMENT_LINE_ITEMS = frozenset(
    {"Basic Average Shares", "Diluted Average Shares", "Ordinary Shares Number", "Share Issued", "Treasury Shares Number"}
)
_RATIO_STATEMENT_LINE_ITEMS = frozenset({"Tax Rate For Calcs"})


def _statement_line_item_unit_kind(line_item: str) -> str:
    """Real unit classification for one statement line item -- never
    defaults every row to a bare currency amount without checking the small,
    known set of non-monetary exceptions first (John task-sheet round-2
    point 1: 'do not treat every statement row as an amount by default')."""
    if line_item in _PER_SHARE_STATEMENT_LINE_ITEMS:
        return "per_share_currency"
    if line_item in _SHARE_COUNT_STATEMENT_LINE_ITEMS:
        return "share_count"
    if line_item in _RATIO_STATEMENT_LINE_ITEMS:
        return "ratio_fraction"
    return "currency"


def _statement_unit_label(unit_kind: str) -> str:
    """Per-line-item unit label. ``UNKNOWN_CURRENCY`` expresses ONLY that
    the currency denomination is unknown (no new Provider call was made to
    fetch it) -- it never stands in for not knowing the metric's TYPE, which
    is instead determined structurally by ``_statement_line_item_unit_kind``
    above."""
    if unit_kind == "currency":
        return "UNKNOWN_CURRENCY"
    if unit_kind == "per_share_currency":
        return "UNKNOWN_CURRENCY_per_share"
    if unit_kind == "share_count":
        return "shares"
    if unit_kind == "ratio_fraction":
        return "fraction_0_to_1"
    return "unknown"


def _statement_source_ids(record_title: str) -> tuple[str, str]:
    """Deterministic (source_id, fragment_id) for one statement-line-item
    fetch -- the SAME make_source_id/fragment_id_for functions every other
    chain uses, keyed off the exact same title string the captured record
    itself carries (see the macro chain's own title/source_id mismatch bug
    and fix -- never two independently-reconstructed copies of what must be
    identical input)."""
    source_id = make_source_id(source_type="financial", name="Yahoo Finance", title=record_title, url="")
    return source_id, fragment_id_for(source_id, 0)


def _capture_all_line_items(full_table) -> tuple[dict[str, dict[str, object]], dict[str, str]]:
    """Round 2 (2026-10-04, John task-sheet round-2 point 1): the Agent is
    given the FULL table (every line item x every period, already
    date-filtered by the caller) via the plain CSV dump
    (``get_balance_sheet``/``get_cashflow``/``get_income_statement``'s own
    ``data.to_csv()``) -- but until now only ONE summary line item's row was
    ever captured into the source registry. This captures every real row
    the Agent actually received, using the SAME already-fetched
    ``full_table`` (zero new Provider request), each line item tagged with
    its own real unit kind (never defaulted to a bare currency amount
    without checking the known non-monetary exceptions first)."""
    all_line_items: dict[str, dict[str, object]] = {}
    line_item_units: dict[str, str] = {}
    for line_item_name in full_table.index:
        row_values: dict[str, object] = {}
        for col in full_table.columns:
            period_label = pd.Timestamp(col).strftime("%Y-%m-%d")
            row_values[period_label] = _json_safe_number(full_table.loc[line_item_name, col])
        all_line_items[str(line_item_name)] = row_values
        line_item_units[str(line_item_name)] = _statement_unit_label(_statement_line_item_unit_kind(str(line_item_name)))
    return all_line_items, line_item_units


def _statement_summary_sentence(
    *, statement_type: str, canonical: str, freq: str, line_item: str, row, full_table=None
) -> str:
    """Financial-STATEMENT source chain (2026-09-29, reuses the SAME
    source_registry/gate/review/API/export machinery every other chain
    already wired -- no parallel system).

    Disclosure-timing scope (John's own explicit instruction: don't exclude
    this entry point over the ambiguity, handle it honestly instead):
    yfinance's balance sheet/cashflow/income statement expose ONLY each
    column's fiscal PERIOD END date -- never a real disclosure/filing date.
    ``observation_date`` below is set to that period end (the TRUE report
    period, never conflated with disclosure time), while ``published_at``
    is deliberately left None -- never self-completed from the period end.
    A None ``published_at`` flows through to
    comqutor_alpha.source_provenance.compute_verified_support_eligibility's
    own DISCLOSURE_TIME_UNKNOWN check (2026-09-29), which excludes this
    record from OFFICIAL verified support regardless of review outcome,
    while still letting it be captured, linked via marker, and shown as
    research text/candidates/content-support-reviewable evidence -- exactly
    the "flag as time-eligibility-unknown, never silently promoted" contract
    John's task requires, without excluding the entry point itself.

    2026-10-04 (T1 financial-data fix round, John task-sheet section 4-5):
    ``row`` (a pandas Series, one entry per fiscal period this tool call
    actually returned for ``line_item``, already date-filtered by the
    caller) is now saved in full under ``data_snapshot["periods"]`` -- not
    only the latest value -- so any stated comparison below can be
    independently recomputed from the saved data alone. ``unit`` is no
    longer hardcoded "USD": yfinance's statement DataFrames carry no
    currency metadata at all, and fetching it would require a new Provider
    call this function does not make, so it is honestly "UNKNOWN_CURRENCY"
    (never assumed). The rose/fell/unchanged/cannot-compare wording is
    derived strictly from what two real, comparable (same statement, same
    freq -- ``row`` only ever spans one DataFrame, never mixes annual and
    quarterly) periods actually contain; a single available period, an
    unchanged value, or a genuinely non-comparable prior value each get
    their own honest, distinct phrasing -- never a default "remained
    elevated" guess (the prior bug this round fixes).

    Round 2 (2026-10-04, John task-sheet round-2 point 1): ``full_table``
    (the SAME already-fetched, already-date-filtered DataFrame the caller's
    own ``data.to_csv()`` dump gives the Agent in full) is now captured
    entirely into ``data_snapshot["all_line_items"]``/``["line_item_units"]``
    -- every row the Agent actually received, not only the one summary
    ``line_item``. ``full_table=None`` (never happens from the three real
    callers below, kept only so this function stays independently testable)
    degrades to the pre-round-2 summary-only capture.
    """
    periods_desc = sorted(row.index, key=lambda c: pd.Timestamp(c), reverse=True)
    latest_period = periods_desc[0]
    latest_value = _json_safe_number(row[latest_period])
    period_label = pd.Timestamp(latest_period).strftime("%Y-%m-%d")

    all_periods: dict[str, object] = {}
    for col in periods_desc:
        all_periods[pd.Timestamp(col).strftime("%Y-%m-%d")] = _json_safe_number(row[col])

    comparison = None
    prior_period_label = None
    prior_value = None
    if len(periods_desc) > 1:
        prior_period_label = pd.Timestamp(periods_desc[1]).strftime("%Y-%m-%d")
        prior_value = all_periods.get(prior_period_label)
        if latest_value is not None and prior_value is not None:
            comparison = {
                "current_period": period_label,
                "current_value": latest_value,
                "prior_period": prior_period_label,
                "prior_value": prior_value,
                "delta": latest_value - prior_value,
                "method": "current_value_minus_prior_value",
                "period_relationship": _period_relationship_label(period_label, prior_period_label),
            }

    record_title = f"{canonical} {statement_type} {line_item} snapshot {period_label} ({freq})"
    source_id, fragment_id = _statement_source_ids(record_title)
    excerpt_parts = [
        f"{canonical} {statement_type} ({freq}) {line_item}: "
        + "; ".join(f"{p}={v}" for p, v in all_periods.items())
    ]

    data_snapshot: dict[str, object] = {
        "statement_type": statement_type,
        "line_item": line_item,
        "value": latest_value,  # kept for backward compatibility: the latest period's own value
        "freq": freq,
        "periods": all_periods,  # every period this tool call actually returned, not only the latest
        "comparison": comparison,  # None when fewer than 2 genuinely comparable periods exist
    }

    if full_table is not None:
        all_line_items, line_item_units = _capture_all_line_items(full_table)
        data_snapshot["all_line_items"] = all_line_items
        data_snapshot["line_item_units"] = line_item_units
        # Extend the excerpt to cover every OTHER real row the Agent also
        # received (not only the summary line_item above) -- so a claim
        # that restates a non-summary row's own real value can still be
        # found by match_evidence_to_source_candidates' real, existing
        # exact-substring mechanism (never a fabricated marker injected into
        # the plain CSV text itself, which this round does not touch).
        for other_name, other_periods in all_line_items.items():
            if other_name == line_item:
                continue  # already included in excerpt_parts[0] above
            excerpt_parts.append(
                f"{canonical} {statement_type} ({freq}) {other_name}: "
                + "; ".join(f"{p}={v}" for p, v in other_periods.items())
            )

    excerpt = " | ".join(excerpt_parts)
    record_source(
        {
            "source_type": "financial",
            "name": "Yahoo Finance",
            "title": record_title,
            "url": "",
            "published_at": None,
            "provider": "yfinance",
            "excerpt": excerpt,
            "instrument": canonical,
            "observation_date": period_label,
            # yfinance's statement DataFrames carry no currency metadata;
            # fetching it would require a new Provider call this function
            # does not make -- honestly unknown, never assumed USD. This is
            # the SUMMARY line_item's own unit; see
            # data_snapshot["line_item_units"] for every other row's real,
            # individually-classified unit (per-share/share-count/ratio
            # exceptions are never lumped in as a bare currency amount).
            "unit": "UNKNOWN_CURRENCY",
            "data_snapshot": data_snapshot,
        }
    )

    if comparison is None:
        if len(periods_desc) <= 1:
            body = f"{canonical}'s {line_item} was {latest_value} as of {period_label} ({freq}); no prior period was available for comparison"
        else:
            body = (
                f"{canonical}'s {line_item} as of {period_label} ({freq}) is {latest_value}; "
                f"the prior period's value ({prior_period_label}) is not comparable, so no trend is stated"
            )
    elif comparison["delta"] > 0:
        body = (
            f"{canonical}'s {line_item} rose to {latest_value} as of {period_label}, from {prior_value} "
            f"as of {prior_period_label} ({comparison['period_relationship']})"
        )
    elif comparison["delta"] < 0:
        body = (
            f"{canonical}'s {line_item} fell to {latest_value} as of {period_label}, from {prior_value} "
            f"as of {prior_period_label} ({comparison['period_relationship']})"
        )
    else:
        body = (
            f"{canonical}'s {line_item} was unchanged at {latest_value}, comparing {period_label} to "
            f"{prior_period_label} ({comparison['period_relationship']})"
        )

    return f"Verified {statement_type}: {body} ({freq}) [source_id: {source_id}] [fragment_id: {fragment_id}]."


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get balance sheet data from yfinance."""
    canonical = normalize_symbol(ticker)
    try:
        ticker_obj = yf.Ticker(canonical)

        if freq.lower() == "quarterly":
            data = yf_retry(lambda: ticker_obj.quarterly_balance_sheet)
        else:
            data = yf_retry(lambda: ticker_obj.balance_sheet)

        data = filter_financials_by_date(data, curr_date)

        if data.empty:
            raise NoMarketDataError(ticker, canonical, "no balance sheet data")

        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()

        # Add header information
        header = f"# Balance Sheet data for {canonical} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        line_item, row = _pick_first_present_row(data, _BALANCE_SHEET_LINE_ITEM_CANDIDATES)
        summary_sentence = (
            _statement_summary_sentence(statement_type="balance sheet", canonical=canonical, freq=freq, line_item=line_item, row=row, full_table=data)
            if line_item is not None
            else ""
        )

        return header + csv_string + ("\n\n" + summary_sentence if summary_sentence else "")

    except NoMarketDataError:
        raise
    except Exception as e:
        return f"Error retrieving balance sheet for {ticker}: {str(e)}"


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get cash flow data from yfinance."""
    canonical = normalize_symbol(ticker)
    try:
        ticker_obj = yf.Ticker(canonical)

        if freq.lower() == "quarterly":
            data = yf_retry(lambda: ticker_obj.quarterly_cashflow)
        else:
            data = yf_retry(lambda: ticker_obj.cashflow)

        data = filter_financials_by_date(data, curr_date)

        if data.empty:
            raise NoMarketDataError(ticker, canonical, "no cash flow data")

        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()

        # Add header information
        header = f"# Cash Flow data for {canonical} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        line_item, row = _pick_first_present_row(data, _CASHFLOW_LINE_ITEM_CANDIDATES)
        summary_sentence = (
            _statement_summary_sentence(statement_type="cash flow", canonical=canonical, freq=freq, line_item=line_item, row=row, full_table=data)
            if line_item is not None
            else ""
        )

        return header + csv_string + ("\n\n" + summary_sentence if summary_sentence else "")

    except NoMarketDataError:
        raise
    except Exception as e:
        return f"Error retrieving cash flow for {ticker}: {str(e)}"


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get income statement data from yfinance."""
    canonical = normalize_symbol(ticker)
    try:
        ticker_obj = yf.Ticker(canonical)

        if freq.lower() == "quarterly":
            data = yf_retry(lambda: ticker_obj.quarterly_income_stmt)
        else:
            data = yf_retry(lambda: ticker_obj.income_stmt)

        data = filter_financials_by_date(data, curr_date)

        if data.empty:
            raise NoMarketDataError(ticker, canonical, "no income statement data")

        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()

        # Add header information
        header = f"# Income Statement data for {canonical} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        line_item, row = _pick_first_present_row(data, _INCOME_STATEMENT_LINE_ITEM_CANDIDATES)
        summary_sentence = (
            _statement_summary_sentence(statement_type="income statement", canonical=canonical, freq=freq, line_item=line_item, row=row, full_table=data)
            if line_item is not None
            else ""
        )

        return header + csv_string + ("\n\n" + summary_sentence if summary_sentence else "")

    except NoMarketDataError:
        raise
    except Exception as e:
        return f"Error retrieving income statement for {ticker}: {str(e)}"


def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol of the company"]
):
    """Get insider transactions data from yfinance."""
    canonical = normalize_symbol(ticker)
    try:
        ticker_obj = yf.Ticker(canonical)
        data = yf_retry(lambda: ticker_obj.insider_transactions)

        # Empty is normal here (many valid symbols have no insider filings),
        # so report it plainly rather than treating the symbol as invalid.
        if data is None or data.empty:
            return f"No insider transactions reported for symbol '{canonical}'"

        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()

        # Add header information
        header = f"# Insider Transactions data for {canonical}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving insider transactions for {ticker}: {str(e)}"
