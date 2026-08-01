"""Shared constants, reason codes, and small deterministic helpers for the
Data Sanity Cross-Check v1 artifacts (``market_data_snapshot.json`` and
``data_sanity.json``). Nothing here calls yfinance or touches the filesystem.
"""

from __future__ import annotations

import math

MARKET_DATA_SNAPSHOT_SCHEMA_VERSION = "comqutor.market_data_snapshot.v1"
DATA_SANITY_SCHEMA_VERSION = "comqutor.data_sanity.v1"

PROVIDER_NAME = "yfinance"

# ---------------------------------------------------------------------------
# Statuses
# ---------------------------------------------------------------------------

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_CRITICAL = "critical"
STATUS_UNAVAILABLE = "unavailable"
STATUS_DISABLED = "disabled"
# Only ever used by the API layer for historical runs that predate this
# feature and never had a data_sanity.json written -- never written into the
# artifact itself.
STATUS_NOT_AVAILABLE = "not_available"

VALID_DATA_SANITY_STATUSES = frozenset(
    {STATUS_OK, STATUS_WARNING, STATUS_CRITICAL, STATUS_UNAVAILABLE, STATUS_DISABLED}
)

# ---------------------------------------------------------------------------
# Severities
# ---------------------------------------------------------------------------

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"

VALID_SEVERITIES = frozenset({SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_CRITICAL})

_SEVERITY_RANK = {SEVERITY_INFO: 0, SEVERITY_WARNING: 1, SEVERITY_CRITICAL: 2}


def higher_severity(a: str, b: str) -> str:
    """The more severe of two severities. Unknown values rank lowest."""
    return a if _SEVERITY_RANK.get(a, -1) >= _SEVERITY_RANK.get(b, -1) else b


# ---------------------------------------------------------------------------
# Reason codes -- input contract
# ---------------------------------------------------------------------------

TICKER_METADATA_MISMATCH = "TICKER_METADATA_MISMATCH"
INVALID_ANALYSIS_DATE_FOR_DATA_SANITY = "INVALID_ANALYSIS_DATE_FOR_DATA_SANITY"

# ---------------------------------------------------------------------------
# Reason codes -- market availability
# ---------------------------------------------------------------------------

NO_MARKET_DATA_AVAILABLE = "NO_MARKET_DATA_AVAILABLE"
ANALYSIS_DATE_IN_FUTURE = "ANALYSIS_DATE_IN_FUTURE"
ANALYSIS_DATE_NON_TRADING_DAY = "ANALYSIS_DATE_NON_TRADING_DAY"
MARKET_DATA_STALE_BEFORE_ANALYSIS_DATE = "MARKET_DATA_STALE_BEFORE_ANALYSIS_DATE"
NO_SESSION_ON_OR_BEFORE_ANALYSIS_DATE = "NO_SESSION_ON_OR_BEFORE_ANALYSIS_DATE"

# Non-trading-day gating: an analysis_date whose nearest prior session is
# within this many calendar days is just a weekend/holiday (info); beyond it,
# the data is considered stale relative to the analysis date (warning).
NON_TRADING_DAY_GRACE_CALENDAR_DAYS = 4

# ---------------------------------------------------------------------------
# Reason codes -- OHLCV integrity
# ---------------------------------------------------------------------------

MISSING_REQUIRED_OHLCV_COLUMN = "MISSING_REQUIRED_OHLCV_COLUMN"
NULL_OHLC_VALUE = "NULL_OHLC_VALUE"
NON_FINITE_OHLC_VALUE = "NON_FINITE_OHLC_VALUE"
NON_POSITIVE_PRICE = "NON_POSITIVE_PRICE"
NEGATIVE_VOLUME = "NEGATIVE_VOLUME"
DUPLICATE_MARKET_DATE = "DUPLICATE_MARKET_DATE"
UNSORTED_MARKET_DATES = "UNSORTED_MARKET_DATES"
INVALID_HIGH_LOW_RANGE = "INVALID_HIGH_LOW_RANGE"
INVALID_OPEN_OUTSIDE_RANGE = "INVALID_OPEN_OUTSIDE_RANGE"
INVALID_CLOSE_OUTSIDE_RANGE = "INVALID_CLOSE_OUTSIDE_RANGE"

REQUIRED_OHLCV_FIELDS = ("open", "high", "low", "close", "volume")

# ---------------------------------------------------------------------------
# Reason codes -- corporate actions (info-only event signals, never errors)
# ---------------------------------------------------------------------------

STOCK_SPLIT_IN_ANALYSIS_WINDOW = "STOCK_SPLIT_IN_ANALYSIS_WINDOW"
REVERSE_SPLIT_IN_ANALYSIS_WINDOW = "REVERSE_SPLIT_IN_ANALYSIS_WINDOW"
DIVIDEND_IN_ANALYSIS_WINDOW = "DIVIDEND_IN_ANALYSIS_WINDOW"
CAPITAL_GAIN_IN_ANALYSIS_WINDOW = "CAPITAL_GAIN_IN_ANALYSIS_WINDOW"

# ---------------------------------------------------------------------------
# Reason codes -- extreme adjusted daily return
# ---------------------------------------------------------------------------

EXTREME_ADJUSTED_DAILY_RETURN = "EXTREME_ADJUSTED_DAILY_RETURN"
EXTREME_RETURN_WARNING_THRESHOLD = 0.40
EXTREME_RETURN_CRITICAL_THRESHOLD = 0.80

# ---------------------------------------------------------------------------
# Reason codes -- reported price extraction / cross-check
# ---------------------------------------------------------------------------

REPORTED_PRICE_SESSION_NOT_FOUND = "REPORTED_PRICE_SESSION_NOT_FOUND"
REPORTED_PRICE_MISMATCH = "REPORTED_PRICE_MISMATCH"
REPORTED_PRICE_OUTSIDE_DAILY_RANGE = "REPORTED_PRICE_OUTSIDE_DAILY_RANGE"
POSSIBLE_PRICE_ADJUSTMENT_CONVENTION_MISMATCH = "POSSIBLE_PRICE_ADJUSTMENT_CONVENTION_MISMATCH"

REPORTED_PRICE_SESSION_GRACE_CALENDAR_DAYS = 3
REPORTED_PRICE_MISMATCH_WARNING_THRESHOLD = 0.05
REPORTED_PRICE_MISMATCH_CRITICAL_THRESHOLD = 0.50
REPORTED_PRICE_RANGE_LOW_FACTOR = 0.95
REPORTED_PRICE_RANGE_HIGH_FACTOR = 1.05

DATE_RESOLUTION_EXPLICIT_YEAR = "explicit_year"
DATE_RESOLUTION_ANALYSIS_YEAR_INFERRED = "analysis_year_inferred"
DATE_RESOLUTION_PREVIOUS_YEAR_INFERRED = "previous_year_inferred"

PRICE_SEMANTICS_OPEN = "open"
PRICE_SEMANTICS_CLOSE = "close"
PRICE_SEMANTICS_REACHED = "reached"
PRICE_SEMANTICS_PEAKED = "peaked"
PRICE_SEMANTICS_FELL_TO = "fell_to"
PRICE_SEMANTICS_TRADED = "traded"
PRICE_SEMANTICS_GENERIC = "generic"
# Compared via Low/High range, not an exact single reference value.
RANGE_COMPARISON_SEMANTICS = frozenset(
    {
        PRICE_SEMANTICS_REACHED,
        PRICE_SEMANTICS_PEAKED,
        PRICE_SEMANTICS_FELL_TO,
        PRICE_SEMANTICS_TRADED,
        PRICE_SEMANTICS_GENERIC,
    }
)

MAX_SOURCE_TEXT_CHARS = 500

# ---------------------------------------------------------------------------
# Numeric semantic role (Structure Integrity Repair Sprint, Track 3).
#
# A ``price_semantics`` value (open/close/traded/reached/peaked/fell_to/
# generic) describes *how* a dollar figure was phrased; ``semantic_role``
# additionally answers *what kind of number it actually is* -- a technical
# indicator (moving average, oscillator, support/resistance level) is never
# a market price, no matter how price-like its surrounding verb reads, and
# must never be compared against a day's OHLC range.
# ---------------------------------------------------------------------------

SEMANTIC_ROLE_OBSERVED_MARKET_PRICE = "OBSERVED_MARKET_PRICE"
SEMANTIC_ROLE_OPEN_PRICE = "OPEN_PRICE"
SEMANTIC_ROLE_CLOSE_PRICE = "CLOSE_PRICE"
SEMANTIC_ROLE_HISTORICAL_TRADE_PRICE = "HISTORICAL_TRADE_PRICE"
SEMANTIC_ROLE_MOVING_AVERAGE = "MOVING_AVERAGE"
SEMANTIC_ROLE_TECHNICAL_LEVEL = "TECHNICAL_LEVEL"
SEMANTIC_ROLE_UNKNOWN = "UNKNOWN"

# Only a role that genuinely denotes an actual traded market price is ever
# eligible for a daily-OHLC-range comparison.
DAILY_RANGE_ELIGIBLE_SEMANTIC_ROLES = frozenset(
    {
        SEMANTIC_ROLE_OBSERVED_MARKET_PRICE,
        SEMANTIC_ROLE_OPEN_PRICE,
        SEMANTIC_ROLE_CLOSE_PRICE,
        SEMANTIC_ROLE_HISTORICAL_TRADE_PRICE,
    }
)

DAILY_RANGE_SKIP_REASON_TECHNICAL_INDICATOR = "TECHNICAL_INDICATOR"
DAILY_RANGE_SKIP_REASON_NUMERIC_ROLE_UNRESOLVED = "NUMERIC_ROLE_UNRESOLVED"

# ---------------------------------------------------------------------------
# Reason codes -- provider failure (non-blocking contract)
# ---------------------------------------------------------------------------

DATA_SANITY_PROVIDER_UNAVAILABLE = "DATA_SANITY_PROVIDER_UNAVAILABLE"

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def finite_or_none(value):
    """NaN/Infinity/non-numeric -> None; everything else passes through as a
    plain float. Never raises -- the snapshot/checker must be able to run
    against noisy provider output."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def finite_int_or_none(value):
    numeric = finite_or_none(value)
    if numeric is None:
        return None
    return int(numeric)


def new_warning(code: str, severity: str, message: str, details: dict | None = None) -> dict:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "details": details or {},
    }
