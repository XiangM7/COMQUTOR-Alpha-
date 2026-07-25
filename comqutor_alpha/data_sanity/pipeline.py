"""Orchestrates the Data Sanity Cross-Check v1 sidecar stage: reads a run's
own ``metadata.json``/``raw_agent_outputs.json``/``structured_agent_outputs.
json``, calls the (injectable) market-data provider at most once, and writes
``market_data_snapshot.json`` + ``data_sanity.json``.

``run_data_sanity_stage`` never raises and never blocks Research completion
-- every failure mode (disabled config, contract violation, provider
failure, unexpected internal error) degrades to a safe artifact with a
stable status/reason code instead of propagating.
"""

from __future__ import annotations

import datetime as dt
import os
import re

from comqutor_alpha.data_sanity.checker import run_checks
from comqutor_alpha.data_sanity.reported_price_extractor import extract_reported_prices
from comqutor_alpha.data_sanity.schema import (
    DATA_SANITY_PROVIDER_UNAVAILABLE,
    DATA_SANITY_SCHEMA_VERSION,
    INVALID_ANALYSIS_DATE_FOR_DATA_SANITY,
    MARKET_DATA_SNAPSHOT_SCHEMA_VERSION,
    PROVIDER_NAME,
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    STATUS_CRITICAL,
    STATUS_DISABLED,
    STATUS_UNAVAILABLE,
    TICKER_METADATA_MISMATCH,
    new_warning,
)
from comqutor_alpha.data_sanity.yfinance_provider import (
    MarketDataProviderError,
    YFinanceMarketDataProvider,
)
from comqutor_alpha.storage.file_store import (
    load_json_record_if_exists,
    save_json_record,
    validate_run_id_for_path,
)

DATA_SANITY_ENABLED_ENV = "COMQUTOR_DATA_SANITY_ENABLED"
DATA_SANITY_TIMEOUT_ENV = "COMQUTOR_DATA_SANITY_TIMEOUT_SECONDS"
DEFAULT_TIMEOUT_SECONDS = 15
_TIMEOUT_BOUNDS = (1, 60)
_BOOL_TRUE = frozenset({"true", "1", "yes", "on"})

MARKET_DATA_SNAPSHOT_ARTIFACT_FILENAME = "market_data_snapshot.json"
DATA_SANITY_ARTIFACT_FILENAME = "data_sanity.json"

# analysis_date - 400 calendar days .. min(analysis_date, current UTC date) + 1
QUERY_LOOKBACK_CALENDAR_DAYS = 400

_ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def is_data_sanity_enabled() -> bool:
    """Fail-closed: only the server process environment can enable this
    (there is no HTTP request field for it), and any unrecognized value
    keeps the safe default of disabled."""
    raw = os.environ.get(DATA_SANITY_ENABLED_ENV, "")
    if not raw.strip():
        return False
    return raw.strip().lower() in _BOOL_TRUE


def resolve_timeout_seconds() -> int:
    """Safe-degrade, never raises: a missing, malformed, or out-of-[1,60]
    value falls back to the default rather than starting an unbounded
    wait."""
    raw = os.environ.get(DATA_SANITY_TIMEOUT_ENV, "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    minimum, maximum = _TIMEOUT_BOUNDS
    if not (minimum <= value <= maximum):
        return DEFAULT_TIMEOUT_SECONDS
    return value


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_strict_iso_date(value) -> dt.date | None:
    if not isinstance(value, str) or not _ISO_DATE_PATTERN.fullmatch(value):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def _empty_summary() -> dict:
    return {
        "warning_count": 0,
        "critical_count": 0,
        "ohlcv_row_count": 0,
        "reported_price_check_count": 0,
        "split_event_count": 0,
        "reverse_split_event_count": 0,
        "dividend_event_count": 0,
        "capital_gain_event_count": 0,
        "extreme_return_count": 0,
    }


def _envelope(run_id, ticker, analysis_date, *, status, provider_version=None) -> dict:
    return {
        "schema_version": DATA_SANITY_SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "analysis_date": analysis_date,
        "provider": PROVIDER_NAME,
        "provider_version": provider_version,
        "retrieved_at": _utc_now_iso(),
        "status": status,
        "last_available_session": None,
        "analysis_date_has_exact_session": False,
        "summary": _empty_summary(),
        "checks": [],
        "warnings": [],
    }


def _disabled_payload(run_id, ticker, analysis_date) -> dict:
    return _envelope(run_id, ticker, analysis_date, status=STATUS_DISABLED)


def _contract_violation_payload(run_id, ticker, analysis_date, code: str, message: str) -> dict:
    payload = _envelope(run_id, ticker, analysis_date, status=STATUS_CRITICAL)
    payload["warnings"] = [new_warning(code, SEVERITY_CRITICAL, message, {})]
    payload["summary"]["critical_count"] = 1
    return payload


def _unavailable_payload(run_id, ticker, analysis_date) -> dict:
    payload = _envelope(run_id, ticker, analysis_date, status=STATUS_UNAVAILABLE)
    payload["warnings"] = [
        new_warning(
            DATA_SANITY_PROVIDER_UNAVAILABLE,
            SEVERITY_WARNING,
            "The external market-data provider was unavailable for this run. "
            "Research completion is not affected.",
            {},
        )
    ]
    payload["summary"]["warning_count"] = 1
    return payload


def _save(run_id, output_root, payload) -> dict:
    save_json_record(run_id, DATA_SANITY_ARTIFACT_FILENAME, payload, output_root=output_root)
    return payload


def _run_data_sanity_stage_inner(run_id, output_root, *, provider, current_utc_date) -> dict:
    metadata = load_json_record_if_exists(run_id, "metadata.json", output_root=output_root)
    raw_payload = load_json_record_if_exists(run_id, "raw_agent_outputs.json", output_root=output_root)

    if not is_data_sanity_enabled():
        ticker = metadata.get("ticker") or raw_payload.get("ticker")
        return _save(run_id, output_root, _disabled_payload(run_id, ticker, metadata.get("analysis_date")))

    metadata_ticker = metadata.get("ticker")
    raw_ticker = raw_payload.get("ticker")
    analysis_date_raw = metadata.get("analysis_date")

    # Ticker input contract: metadata.json is authoritative, with
    # raw_agent_outputs.json as the only allowed fallback -- never a guess
    # from natural-language final_state. Both present but disagreeing is a
    # hard stop, never a silent pick-one-and-continue.
    if metadata_ticker and raw_ticker and str(metadata_ticker).strip().upper() != str(raw_ticker).strip().upper():
        return _save(
            run_id,
            output_root,
            _contract_violation_payload(
                run_id,
                metadata_ticker,
                analysis_date_raw,
                TICKER_METADATA_MISMATCH,
                "metadata.json and raw_agent_outputs.json report different tickers for this run.",
            ),
        )

    ticker = metadata_ticker or raw_ticker
    if not ticker:
        return _save(run_id, output_root, _unavailable_payload(run_id, None, analysis_date_raw))

    parsed_analysis_date = _parse_strict_iso_date(analysis_date_raw)
    if parsed_analysis_date is None:
        return _save(
            run_id,
            output_root,
            _contract_violation_payload(
                run_id,
                ticker,
                analysis_date_raw,
                INVALID_ANALYSIS_DATE_FOR_DATA_SANITY,
                "analysis_date is missing or is not a strict YYYY-MM-DD date.",
            ),
        )

    current_date = current_utc_date or dt.datetime.now(dt.UTC).date()
    effective_end_date = min(parsed_analysis_date, current_date)
    start_date = parsed_analysis_date - dt.timedelta(days=QUERY_LOOKBACK_CALENDAR_DAYS)
    end_exclusive = effective_end_date + dt.timedelta(days=1)

    active_provider = provider or YFinanceMarketDataProvider(timeout_seconds=resolve_timeout_seconds())
    try:
        rows = active_provider.get_history_rows(ticker, start_date, end_exclusive)
    except MarketDataProviderError:
        return _save(run_id, output_root, _unavailable_payload(run_id, ticker, analysis_date_raw))
    except Exception:
        return _save(run_id, output_root, _unavailable_payload(run_id, ticker, analysis_date_raw))

    provider_version = None
    version_fn = getattr(active_provider, "provider_version", None)
    if callable(version_fn):
        try:
            provider_version = version_fn()
        except Exception:
            provider_version = None

    retrieved_at = _utc_now_iso()
    snapshot_payload = {
        "schema_version": MARKET_DATA_SNAPSHOT_SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "analysis_date": analysis_date_raw,
        "provider": PROVIDER_NAME,
        "provider_version": provider_version,
        "retrieved_at": retrieved_at,
        "query": {
            "start_date": start_date.isoformat(),
            "end_exclusive": end_exclusive.isoformat(),
            "interval": "1d",
            "auto_adjust": False,
            "repair": False,
        },
        "rows": rows,
    }
    save_json_record(run_id, MARKET_DATA_SNAPSHOT_ARTIFACT_FILENAME, snapshot_payload, output_root=output_root)

    structured_payload = load_json_record_if_exists(
        run_id, "structured_agent_outputs.json", output_root=output_root
    )
    reported_price_checks_available = bool(structured_payload)
    reported_prices: list[dict] = []
    if reported_price_checks_available:
        records = structured_payload.get("records")
        reported_prices = extract_reported_prices(
            records if isinstance(records, list) else [], parsed_analysis_date
        )

    core = run_checks(
        rows=rows,
        analysis_date=parsed_analysis_date,
        current_utc_date=current_date,
        reported_prices=reported_prices,
        reported_price_checks_available=reported_price_checks_available,
    )

    payload = {
        "schema_version": DATA_SANITY_SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "analysis_date": analysis_date_raw,
        "provider": PROVIDER_NAME,
        "provider_version": provider_version,
        "retrieved_at": retrieved_at,
        **core,
    }
    return _save(run_id, output_root, payload)


def run_data_sanity_stage(run_id, output_root, *, provider=None, current_utc_date=None) -> dict | None:
    """The only entrypoint external callers should use. Always attempts
    exactly one provider call (no retries); on any failure -- including a
    defect in this stage itself -- writes/returns a safe ``unavailable``
    artifact instead of raising, so a Data Sanity bug can never take down
    Research completion, delete artifacts, or affect Alpha Mapping, the
    Structure Graph, Activation, or Conflict detection."""
    try:
        safe_run_id = validate_run_id_for_path(run_id)
    except Exception:
        return None
    try:
        return _run_data_sanity_stage_inner(
            safe_run_id, output_root, provider=provider, current_utc_date=current_utc_date
        )
    except Exception:
        try:
            return _save(safe_run_id, output_root, _unavailable_payload(safe_run_id, None, None))
        except Exception:
            return None
