"""Deterministic Data Sanity checks over already-fetched market rows and
(optionally) extracted reported-price mentions.

Every function here is a pure function over plain dicts/lists -- no
filesystem, no network, no yfinance import. This is what makes the checks
independently testable with hand-crafted (including deliberately malformed)
fixtures.
"""

from __future__ import annotations

import datetime as dt
import math

from comqutor_alpha.data_sanity.schema import (
    ANALYSIS_DATE_IN_FUTURE,
    ANALYSIS_DATE_NON_TRADING_DAY,
    CAPITAL_GAIN_IN_ANALYSIS_WINDOW,
    DIVIDEND_IN_ANALYSIS_WINDOW,
    DUPLICATE_MARKET_DATE,
    EXTREME_ADJUSTED_DAILY_RETURN,
    EXTREME_RETURN_CRITICAL_THRESHOLD,
    EXTREME_RETURN_WARNING_THRESHOLD,
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
    NON_TRADING_DAY_GRACE_CALENDAR_DAYS,
    NULL_OHLC_VALUE,
    POSSIBLE_PRICE_ADJUSTMENT_CONVENTION_MISMATCH,
    PRICE_SEMANTICS_CLOSE,
    PRICE_SEMANTICS_OPEN,
    RANGE_COMPARISON_SEMANTICS,
    REPORTED_PRICE_MISMATCH,
    REPORTED_PRICE_MISMATCH_CRITICAL_THRESHOLD,
    REPORTED_PRICE_MISMATCH_WARNING_THRESHOLD,
    REPORTED_PRICE_OUTSIDE_DAILY_RANGE,
    REPORTED_PRICE_RANGE_HIGH_FACTOR,
    REPORTED_PRICE_RANGE_LOW_FACTOR,
    REPORTED_PRICE_SESSION_GRACE_CALENDAR_DAYS,
    REPORTED_PRICE_SESSION_NOT_FOUND,
    REQUIRED_OHLCV_FIELDS,
    REVERSE_SPLIT_IN_ANALYSIS_WINDOW,
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    STATUS_CRITICAL,
    STATUS_OK,
    STATUS_WARNING,
    STOCK_SPLIT_IN_ANALYSIS_WINDOW,
    UNSORTED_MARKET_DATES,
    new_warning,
)

_MAX_DETAIL_DATES = 20


def check_market_availability(rows: list[dict], analysis_date: dt.date, current_utc_date: dt.date) -> dict:
    """Returns ``{"warnings", "last_available_session", "analysis_date_has_exact_session"}``.

    Never treats a weekend/holiday with no bar as a data error on its own --
    only genuine unavailability (empty result, no prior session at all, or a
    prior session stale by more than the grace window) is flagged.
    """
    warnings: list[dict] = []
    analysis_date_str = analysis_date.isoformat()

    if not rows:
        warnings.append(
            new_warning(
                NO_MARKET_DATA_AVAILABLE,
                SEVERITY_CRITICAL,
                "Yahoo Finance returned no market data for this ticker and query window.",
                {"analysis_date": analysis_date_str},
            )
        )
        return {
            "warnings": warnings,
            "last_available_session": None,
            "analysis_date_has_exact_session": False,
        }

    if analysis_date > current_utc_date:
        warnings.append(
            new_warning(
                ANALYSIS_DATE_IN_FUTURE,
                SEVERITY_WARNING,
                "The research run's analysis_date is later than the current date.",
                {"analysis_date": analysis_date_str, "current_utc_date": current_utc_date.isoformat()},
            )
        )

    sessions_on_or_before = [row for row in rows if row.get("date") and row["date"] <= analysis_date_str]
    if not sessions_on_or_before:
        warnings.append(
            new_warning(
                NO_SESSION_ON_OR_BEFORE_ANALYSIS_DATE,
                SEVERITY_CRITICAL,
                "Yahoo Finance reports no trading session on or before the analysis date.",
                {"analysis_date": analysis_date_str},
            )
        )
        return {
            "warnings": warnings,
            "last_available_session": None,
            "analysis_date_has_exact_session": False,
        }

    last_row = max(sessions_on_or_before, key=lambda row: row["date"])
    last_available_session = last_row["date"]
    exact = last_available_session == analysis_date_str
    if not exact:
        gap_days = (analysis_date - dt.date.fromisoformat(last_available_session)).days
        if gap_days <= NON_TRADING_DAY_GRACE_CALENDAR_DAYS:
            warnings.append(
                new_warning(
                    ANALYSIS_DATE_NON_TRADING_DAY,
                    SEVERITY_INFO,
                    "The analysis date has no trading session (weekend/holiday); "
                    "the nearest prior session is used as the reference.",
                    {"analysis_date": analysis_date_str, "last_available_session": last_available_session},
                )
            )
        else:
            warnings.append(
                new_warning(
                    MARKET_DATA_STALE_BEFORE_ANALYSIS_DATE,
                    SEVERITY_WARNING,
                    "The most recent available trading session is more than "
                    f"{NON_TRADING_DAY_GRACE_CALENDAR_DAYS} calendar days before the analysis date.",
                    {
                        "analysis_date": analysis_date_str,
                        "last_available_session": last_available_session,
                        "gap_calendar_days": gap_days,
                    },
                )
            )

    return {
        "warnings": warnings,
        "last_available_session": last_available_session,
        "analysis_date_has_exact_session": exact,
    }


def _dedupe_sorted(dates) -> list[str]:
    return sorted({d for d in dates if d is not None})


def check_ohlcv_integrity(rows: list[dict]) -> list[dict]:
    """All OHLCV integrity violations are treated as critical -- they mean
    the market data itself cannot be trusted for comparison, not merely that
    a threshold was crossed."""
    warnings: list[dict] = []

    seen_counts: dict[str, int] = {}
    prev_date = None
    unsorted = False
    for row in rows:
        date = row.get("date")
        seen_counts[date] = seen_counts.get(date, 0) + 1
        if prev_date is not None and date is not None and date < prev_date:
            unsorted = True
        prev_date = date if date is not None else prev_date

    duplicate_dates = [date for date, count in seen_counts.items() if count > 1]
    if duplicate_dates:
        warnings.append(
            new_warning(
                DUPLICATE_MARKET_DATE,
                SEVERITY_CRITICAL,
                "The same market date appears more than once in the retrieved data.",
                {"dates": _dedupe_sorted(duplicate_dates)[:_MAX_DETAIL_DATES], "count": len(duplicate_dates)},
            )
        )
    if unsorted:
        warnings.append(
            new_warning(
                UNSORTED_MARKET_DATES,
                SEVERITY_CRITICAL,
                "Retrieved market dates are not in ascending order.",
                {},
            )
        )

    missing_dates: list[str] = []
    null_dates: list[str] = []
    non_finite_dates: list[str] = []
    non_positive_dates: list[str] = []
    negative_volume_dates: list[str] = []
    high_low_dates: list[str] = []
    open_range_dates: list[str] = []
    close_range_dates: list[str] = []

    for row in rows:
        date = row.get("date")
        values: dict[str, float] = {}
        row_incomplete = False
        for field in REQUIRED_OHLCV_FIELDS:
            if field not in row:
                missing_dates.append(date)
                row_incomplete = True
                continue
            value = row[field]
            if value is None:
                null_dates.append(date)
                continue
            if isinstance(value, bool):
                non_finite_dates.append(date)
                continue
            if isinstance(value, (int, float)) and not math.isfinite(value):
                non_finite_dates.append(date)
                continue
            if not isinstance(value, (int, float)):
                non_finite_dates.append(date)
                continue
            values[field] = float(value)
        if row_incomplete:
            continue

        for field in ("open", "high", "low", "close"):
            if field in values and values[field] <= 0:
                non_positive_dates.append(date)
        if "volume" in values and values["volume"] < 0:
            negative_volume_dates.append(date)

        has_range = "high" in values and "low" in values
        if has_range and values["high"] < values["low"]:
            high_low_dates.append(date)
            continue
        if has_range and "open" in values and not (values["low"] <= values["open"] <= values["high"]):
            open_range_dates.append(date)
        if has_range and "close" in values and not (values["low"] <= values["close"] <= values["high"]):
            close_range_dates.append(date)

    def _emit(code: str, dates: list[str], message: str) -> None:
        if not dates:
            return
        unique = _dedupe_sorted(dates)
        warnings.append(
            new_warning(code, SEVERITY_CRITICAL, message, {"dates": unique[:_MAX_DETAIL_DATES], "count": len(unique)})
        )

    _emit(MISSING_REQUIRED_OHLCV_COLUMN, missing_dates, "A required OHLCV column is missing for one or more rows.")
    _emit(NULL_OHLC_VALUE, null_dates, "A required OHLCV field is null for one or more rows.")
    _emit(NON_FINITE_OHLC_VALUE, non_finite_dates, "A required OHLCV field is not a finite number for one or more rows.")
    _emit(NON_POSITIVE_PRICE, non_positive_dates, "A price field is not strictly positive for one or more rows.")
    _emit(NEGATIVE_VOLUME, negative_volume_dates, "Volume is negative for one or more rows.")
    _emit(INVALID_HIGH_LOW_RANGE, high_low_dates, "High is less than Low for one or more rows.")
    _emit(INVALID_OPEN_OUTSIDE_RANGE, open_range_dates, "Open falls outside [Low, High] for one or more rows.")
    _emit(INVALID_CLOSE_OUTSIDE_RANGE, close_range_dates, "Close falls outside [Low, High] for one or more rows.")

    return warnings


def check_corporate_actions(rows: list[dict]) -> tuple[list[dict], dict]:
    """Info-only event signals -- never data errors. Yahoo Finance's actions
    data is not claimed to cover every corporate action (mergers, ticker
    changes, delistings are not guaranteed to appear here)."""
    warnings: list[dict] = []
    counts = {
        "split_event_count": 0,
        "reverse_split_event_count": 0,
        "dividend_event_count": 0,
        "capital_gain_event_count": 0,
    }
    for row in rows:
        date = row.get("date")
        split = row.get("stock_split") or 0.0
        if split > 1:
            counts["split_event_count"] += 1
            warnings.append(
                new_warning(
                    STOCK_SPLIT_IN_ANALYSIS_WINDOW,
                    SEVERITY_INFO,
                    "Yahoo Finance reports a stock split in the analysis window. "
                    "This is not a data anomaly and does not cover every possible corporate action.",
                    {"date": date, "stock_split": split},
                )
            )
        elif 0 < split < 1:
            counts["reverse_split_event_count"] += 1
            warnings.append(
                new_warning(
                    REVERSE_SPLIT_IN_ANALYSIS_WINDOW,
                    SEVERITY_INFO,
                    "Yahoo Finance reports a reverse stock split in the analysis window. "
                    "This is not a data anomaly and does not cover every possible corporate action.",
                    {"date": date, "stock_split": split},
                )
            )
        dividend = row.get("dividend") or 0.0
        if dividend > 0:
            counts["dividend_event_count"] += 1
            warnings.append(
                new_warning(
                    DIVIDEND_IN_ANALYSIS_WINDOW,
                    SEVERITY_INFO,
                    "Yahoo Finance reports a dividend in the analysis window. This is not a data anomaly.",
                    {"date": date, "dividend": dividend},
                )
            )
        capital_gain = row.get("capital_gain") or 0.0
        if capital_gain > 0:
            counts["capital_gain_event_count"] += 1
            warnings.append(
                new_warning(
                    CAPITAL_GAIN_IN_ANALYSIS_WINDOW,
                    SEVERITY_INFO,
                    "Yahoo Finance reports a capital gain distribution in the analysis window. "
                    "This is not a data anomaly.",
                    {"date": date, "capital_gain": capital_gain},
                )
            )
    return warnings, counts


def check_extreme_returns(rows: list[dict]) -> tuple[list[dict], str]:
    """Uses only adjusted daily close. Returns ``(warnings, check_status)``
    where ``check_status`` is ``"ok"`` or ``"unavailable"`` (no usable
    adjusted-close series at all). An extreme return only means "requires
    review" -- it is never asserted to mean the data itself is wrong, and a
    same-day corporate action never suppresses it."""
    usable = [row for row in rows if row.get("adjusted_close") is not None and row.get("date")]
    if not usable:
        return [], "unavailable"

    usable_sorted = sorted(usable, key=lambda row: row["date"])
    warnings: list[dict] = []
    previous = None
    for row in usable_sorted:
        if previous is not None and previous["adjusted_close"]:
            daily_return = row["adjusted_close"] / previous["adjusted_close"] - 1
            # Round before threshold comparison so an exact boundary value
            # (e.g. precisely -40%) is never missed due to binary
            # floating-point representation error.
            magnitude = round(abs(daily_return), 9)
            severity = None
            if magnitude >= EXTREME_RETURN_CRITICAL_THRESHOLD:
                severity = SEVERITY_CRITICAL
            elif magnitude >= EXTREME_RETURN_WARNING_THRESHOLD:
                severity = SEVERITY_WARNING
            if severity is not None:
                warnings.append(
                    new_warning(
                        EXTREME_ADJUSTED_DAILY_RETURN,
                        severity,
                        "Adjusted daily close return exceeds the review threshold. "
                        "This flags the move for review; it does not mean the data is wrong.",
                        {
                            "date": row["date"],
                            "previous_date": previous["date"],
                            "return_percent": round(daily_return * 100, 4),
                        },
                    )
                )
        previous = row
    return warnings, "ok"


def _nearest_prior_session(rows_by_date: dict[str, dict], reported_date: str):
    if reported_date in rows_by_date:
        return reported_date
    target = dt.date.fromisoformat(reported_date)
    for offset in range(1, REPORTED_PRICE_SESSION_GRACE_CALENDAR_DAYS + 1):
        candidate = (target - dt.timedelta(days=offset)).isoformat()
        if candidate in rows_by_date:
            return candidate
    return None


def _split_events_between(rows_by_date: dict[str, dict], start: str, end: str):
    lo, hi = (start, end) if start <= end else (end, start)
    events = []
    for date, row in rows_by_date.items():
        if lo <= date <= hi:
            split = row.get("stock_split") or 0.0
            if split and split != 1:
                events.append((date, split))
    return sorted(events)


def check_reported_prices(reported_prices: list[dict], rows: list[dict]) -> list[dict]:
    """Cross-checks explicit date+price mentions extracted from structured
    claims against the corresponding market session. Never rewrites the
    reported price, never auto-resolves a mismatch, never guesses a
    comparison target for an unmatched session."""
    warnings: list[dict] = []
    rows_by_date = {row["date"]: row for row in rows if row.get("date")}

    for extraction in reported_prices or []:
        reported_date = extraction.get("reported_date")
        reported_price = extraction.get("reported_price")
        price_semantics = extraction.get("price_semantics")
        claim_id = extraction.get("claim_id")
        date_resolution = extraction.get("date_resolution")
        if not reported_date or reported_price is None:
            continue

        matched_session = _nearest_prior_session(rows_by_date, reported_date)
        if matched_session is None:
            warnings.append(
                new_warning(
                    REPORTED_PRICE_SESSION_NOT_FOUND,
                    SEVERITY_WARNING,
                    "No trading session was found within the allowed window for a reported price's date.",
                    {
                        "claim_id": claim_id,
                        "reported_date": reported_date,
                        "price_semantics": price_semantics,
                        "date_resolution": date_resolution,
                    },
                )
            )
            continue

        session_row = rows_by_date[matched_session]
        mismatch_code = None
        mismatch_severity = None
        external_reference = None
        relative_difference = None

        if price_semantics in (PRICE_SEMANTICS_OPEN, PRICE_SEMANTICS_CLOSE):
            field = "open" if price_semantics == PRICE_SEMANTICS_OPEN else "close"
            external_reference = session_row.get(field)
            if external_reference:
                relative_difference = abs(reported_price - external_reference) / abs(external_reference)
                if relative_difference >= REPORTED_PRICE_MISMATCH_CRITICAL_THRESHOLD:
                    mismatch_code, mismatch_severity = REPORTED_PRICE_MISMATCH, SEVERITY_CRITICAL
                elif relative_difference > REPORTED_PRICE_MISMATCH_WARNING_THRESHOLD:
                    mismatch_code, mismatch_severity = REPORTED_PRICE_MISMATCH, SEVERITY_WARNING
        elif price_semantics in RANGE_COMPARISON_SEMANTICS:
            low = session_row.get("low")
            high = session_row.get("high")
            if low is not None and high is not None:
                range_low = low * REPORTED_PRICE_RANGE_LOW_FACTOR
                range_high = high * REPORTED_PRICE_RANGE_HIGH_FACTOR
                if reported_price < range_low or reported_price > range_high:
                    boundary = range_low if reported_price < range_low else range_high
                    external_reference = boundary
                    relative_difference = abs(reported_price - boundary) / abs(boundary) if boundary else None
                    if relative_difference is not None and relative_difference >= REPORTED_PRICE_MISMATCH_CRITICAL_THRESHOLD:
                        mismatch_code, mismatch_severity = REPORTED_PRICE_OUTSIDE_DAILY_RANGE, SEVERITY_CRITICAL
                    else:
                        mismatch_code, mismatch_severity = REPORTED_PRICE_OUTSIDE_DAILY_RANGE, SEVERITY_WARNING

        if mismatch_code is None:
            continue

        warnings.append(
            new_warning(
                mismatch_code,
                mismatch_severity,
                "A price mentioned in a structured analyst claim does not match the external market reference.",
                {
                    "claim_id": claim_id,
                    "reported_date": reported_date,
                    "matched_session": matched_session,
                    "price_semantics": price_semantics,
                    "reported_price": reported_price,
                    "external_reference": external_reference,
                    "relative_difference_percent": round(relative_difference * 100, 4)
                    if relative_difference is not None
                    else None,
                    "date_resolution": date_resolution,
                },
            )
        )

        split_events = _split_events_between(rows_by_date, reported_date, matched_session)
        if split_events:
            split_date, split_ratio = split_events[0]
            warnings.append(
                new_warning(
                    POSSIBLE_PRICE_ADJUSTMENT_CONVENTION_MISMATCH,
                    SEVERITY_WARNING,
                    "A stock split occurred near this reported price's date -- the mismatch may reflect a "
                    "split-adjustment convention difference rather than a factual error. This is not "
                    "automatically resolved.",
                    {
                        "claim_id": claim_id,
                        "reported_date": reported_date,
                        "matched_session": matched_session,
                        "split_date": split_date,
                        "split_ratio": split_ratio,
                    },
                )
            )

    return warnings


def _overall_status(warning_count: int, critical_count: int) -> str:
    if critical_count > 0:
        return STATUS_CRITICAL
    if warning_count > 0:
        return STATUS_WARNING
    return STATUS_OK


def run_checks(
    *,
    rows: list[dict],
    analysis_date: dt.date,
    current_utc_date: dt.date,
    reported_prices: list[dict],
    reported_price_checks_available: bool,
) -> dict:
    """Assembles every check into the core ``data_sanity.json`` payload
    (everything except the run/provider envelope fields, which the pipeline
    module owns)."""
    availability = check_market_availability(rows, analysis_date, current_utc_date)
    ohlcv_warnings = check_ohlcv_integrity(rows)
    action_warnings, action_counts = check_corporate_actions(rows)
    return_warnings, return_check_status = check_extreme_returns(rows)

    checks = [
        {"name": "market_availability", "status": "ok"},
        {"name": "ohlcv_integrity", "status": "ok"},
        {"name": "corporate_actions", "status": "ok"},
        {"name": "extreme_daily_return", "status": return_check_status},
    ]

    reported_price_warnings: list[dict] = []
    if reported_price_checks_available:
        reported_price_warnings = check_reported_prices(reported_prices, rows)
        checks.append(
            {
                "name": "reported_price_cross_check",
                "status": "ok",
                "evaluated_count": len(reported_prices),
            }
        )
    else:
        checks.append(
            {
                "name": "reported_price_cross_check",
                "status": "skipped",
                "reason_code": "NO_STRUCTURED_CLAIMS",
            }
        )

    all_warnings = [
        *availability["warnings"],
        *ohlcv_warnings,
        *action_warnings,
        *return_warnings,
        *reported_price_warnings,
    ]
    warning_count = sum(1 for w in all_warnings if w["severity"] == SEVERITY_WARNING)
    critical_count = sum(1 for w in all_warnings if w["severity"] == SEVERITY_CRITICAL)
    extreme_return_count = sum(1 for w in return_warnings if w["code"] == EXTREME_ADJUSTED_DAILY_RETURN)
    reported_price_check_count = len(reported_prices) if reported_price_checks_available else 0

    return {
        "status": _overall_status(warning_count, critical_count),
        "last_available_session": availability["last_available_session"],
        "analysis_date_has_exact_session": availability["analysis_date_has_exact_session"],
        "summary": {
            "warning_count": warning_count,
            "critical_count": critical_count,
            "ohlcv_row_count": len(rows),
            "reported_price_check_count": reported_price_check_count,
            "split_event_count": action_counts["split_event_count"],
            "reverse_split_event_count": action_counts["reverse_split_event_count"],
            "dividend_event_count": action_counts["dividend_event_count"],
            "capital_gain_event_count": action_counts["capital_gain_event_count"],
            "extreme_return_count": extreme_return_count,
        },
        "checks": checks,
        "warnings": all_warnings,
    }
