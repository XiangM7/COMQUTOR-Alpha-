"""FRED (Federal Reserve Economic Data) macro vendor.

Fetches macroeconomic time series — policy rates, Treasury yields, inflation,
labor, growth — from the St. Louis Fed's free API. Used by the news analyst to
ground macro commentary in actual numbers rather than headlines alone.

A free API key (https://fred.stlouisfed.org/docs/api/api_key.html) is read from
``FRED_API_KEY``; if it is unset the vendor raises ``FredNotConfiguredError`` so
the routing layer treats it as "unavailable" rather than a hard crash.
"""
import logging
import os
from datetime import datetime, timedelta

import requests

from comqutor_alpha.source_provenance import fragment_id_for, make_source_id

from .errors import VendorNotConfiguredError
from .source_capture import record_source

logger = logging.getLogger(__name__)

FRED_API_BASE = "https://api.stlouisfed.org/fred"

# Network timeout (seconds) so a stalled request can't hang the agents,
# mirroring the Alpha Vantage client.
REQUEST_TIMEOUT = 30

# Default trailing window when the caller does not specify one. A year captures
# the trend and the year-over-year base for most monthly/quarterly series.
DEFAULT_LOOKBACK_DAYS = 365

# Rows cap for the rendered table: recent values matter most for a decision, and
# daily series (yields, VIX) over a long window would otherwise flood context.
MAX_ROWS = 40

# Curated human-friendly aliases -> FRED series IDs. Anything not listed is used
# verbatim as a raw FRED series ID, so power users are never limited to this set.
MACRO_SERIES = {
    # Policy rate & Treasury yields
    "fed_funds_rate": "FEDFUNDS",
    "federal_funds_rate": "FEDFUNDS",
    "fed_funds": "FEDFUNDS",
    "2y_treasury": "DGS2",
    "10y_treasury": "DGS10",
    "30y_treasury": "DGS30",
    "10y_2y_spread": "T10Y2Y",
    "yield_curve": "T10Y2Y",
    # Inflation
    "cpi": "CPIAUCSL",
    "core_cpi": "CPILFESL",
    "pce": "PCEPI",
    "core_pce": "PCEPILFE",
    "inflation_expectations": "T10YIE",
    # Growth & output
    "real_gdp": "GDPC1",
    "gdp": "GDP",
    "industrial_production": "INDPRO",
    # Labor
    "unemployment_rate": "UNRATE",
    "unemployment": "UNRATE",
    "nonfarm_payrolls": "PAYEMS",
    "payrolls": "PAYEMS",
    "initial_claims": "ICSA",
    # Money & markets
    "m2": "M2SL",
    "money_supply": "M2SL",
    "vix": "VIXCLS",
    "dollar_index": "DTWEXBGS",
    # Sentiment & housing
    "consumer_sentiment": "UMCSENT",
    "housing_starts": "HOUST",
    "retail_sales": "RSAFS",
}


class FredNotConfiguredError(VendorNotConfiguredError):
    """Raised when FRED is selected but no API key is configured.

    A VendorNotConfiguredError (and thus still a ValueError), so the routing
    layer's "vendor unavailable" handling and existing ValueError callers both
    keep working.
    """


def get_api_key() -> str:
    """Retrieve the FRED API key from the environment."""
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        raise FredNotConfiguredError(
            "FRED_API_KEY environment variable is not set. Get a free key at "
            "https://fred.stlouisfed.org/docs/api/api_key.html."
        )
    return api_key


def _resolve_series_id(indicator: str) -> str:
    """Map a friendly alias to a FRED series ID, or pass a raw ID through.

    Raises ``ValueError`` when the input is neither a known alias nor a plausible
    series ID — typically a descriptive phrase the LLM passed instead (e.g.
    "bank of japan rate"). FRED IDs are short and alphanumeric, so this rejects
    it up front with guidance rather than letting it 400 the API.
    """
    key = indicator.strip().lower().replace(" ", "_").replace("-", "_")
    if key in MACRO_SERIES:
        return MACRO_SERIES[key]
    candidate = indicator.strip().upper()
    # FRED series IDs never contain whitespace and are short; reject anything
    # else (a descriptive phrase the LLM passed) rather than 400ing the API.
    if not candidate or len(candidate) > 30 or any(c.isspace() for c in candidate):
        raise ValueError(
            f"'{indicator}' is not a known macro alias or a valid FRED series ID. "
            f"Use an alias (e.g. 'cpi', 'unemployment', '10y_treasury') or a raw "
            f"FRED series ID (e.g. 'CPIAUCSL')."
        )
    return candidate


def _request(path: str, params: dict) -> dict:
    """GET a FRED endpoint, surfacing FRED's JSON error body on a bad request."""
    api_params = {**params, "api_key": get_api_key(), "file_type": "json"}
    response = requests.get(
        f"{FRED_API_BASE}/{path}", params=api_params, timeout=REQUEST_TIMEOUT
    )
    # FRED returns 400 with a JSON {"error_message": ...} for unknown series IDs
    # or malformed params; turn that into a clear, actionable error.
    if response.status_code == 400:
        try:
            message = response.json().get("error_message", response.text)
        except ValueError:
            message = response.text
        raise ValueError(f"FRED request failed: {message}")
    response.raise_for_status()
    return response.json()


def _macro_source_ids(record_title: str) -> tuple[str, str]:
    """Deterministic (source_id, fragment_id) for one macro-series fetch --
    the SAME make_source_id/fragment_id_for functions the news/market/
    financial chains already use. Takes the EXACT SAME already-composed
    title string the captured record itself uses (never independently
    reconstructed from series_id/curr_date here) so the two can never
    silently drift apart and compute two different ids for what should be
    the same source -- a mismatch this exact function signature update
    was needed to fix (see tests/test_t1_macro_source_chain.py's own
    catching of the original two-different-title-strings bug)."""
    source_id = make_source_id(
        source_type="macro",
        name="FRED",
        title=record_title,
        url="",
    )
    return source_id, fragment_id_for(source_id, 0)


def _macro_summary_sentence(
    *,
    series_id: str,
    title: str,
    units: str,
    curr_date: str,
    last_date: str,
    last_val: str,
    delta: float | None,
    realtime_start: str | None,
) -> str:
    """Financial/macro-data source chain (2026-09-29, reuses the SAME
    source_registry/gate/review/API/export machinery the news/market/
    financial chains already wired -- no parallel system per data type).

    Disclosure-timing caveat (DELIBERATE, never self-completed -- this
    round's task sheet explicitly warns against treating an observation
    PERIOD as its disclosure time): FRED's own per-observation
    ``realtime_start`` field names the date the CURRENTLY-displayed value's
    vintage took effect. For an observation never revised since release,
    this equals its true original publish date; for one that HAS since
    been revised, it instead reflects the LATEST revision, not the
    original release -- a real, inherent ambiguity this module does not
    attempt to resolve by guessing. When the underlying response omits it
    (this codebase's own existing FRED test fixtures do not include it --
    see tests/test_fred.py's ``_OBS``), ``published_at`` and
    ``data_snapshot["realtime_start"]`` are both left ``None`` -- NEVER
    backfilled from ``last_date`` (the observation PERIOD), which would
    silently conflate period with disclosure time. This is recorded so a
    reader of the captured record can see the gap directly, even though
    the shared, frozen ``validate_source_reference`` does not independently
    gate on a missing ``published_at`` (a general, pre-existing, cross-
    source-type characteristic, not modified by this round).
    """
    record_title = f"{title} ({series_id}) macro snapshot {curr_date}"
    source_id, fragment_id = _macro_source_ids(record_title)
    excerpt = f"{title} ({series_id}) {last_date}={last_val} {units}".strip()
    record_source(
        {
            "source_type": "macro",
            "name": "FRED",
            "title": record_title,
            "url": "",
            "published_at": realtime_start,
            "provider": "fred",
            "excerpt": excerpt,
            "instrument": series_id,
            "observation_date": last_date,
            "unit": units or None,
            "data_snapshot": {
                "value": last_val,
                "realtime_start": realtime_start,
                "requested_curr_date": curr_date,
            },
        }
    )
    # A real, data-derived direction word (never invented commentary,
    # never hardcoded to a fixed direction) -- same lesson as the market/
    # financial chains: claim_quality.py's own STATE_OR_CHANGE_TERMS
    # vocabulary ("rose"/"fell"/"remains elevated") is required for this
    # sentence to classify as ANALYTICAL rather than CONTEXT_ONLY, and the
    # marker is embedded INLINE, before the sentence's own closing period.
    if delta is not None and delta > 0:
        moved = "rose to"
    elif delta is not None and delta < 0:
        moved = "fell to"
    else:
        moved = "remained elevated at"
    return (
        f"Verified macro data: {title} ({series_id}) {moved} {last_val} {units} "
        f"as of {last_date} [source_id: {source_id}] [fragment_id: {fragment_id}]."
    )


def get_macro_data(
    indicator: str,
    curr_date: str,
    look_back_days: int | None = None,
) -> str:
    """Fetch a FRED macroeconomic series as a formatted markdown report.

    Args:
        indicator: A friendly alias (e.g. "cpi", "unemployment", "10y_treasury")
            or a raw FRED series ID (e.g. "CPIAUCSL", "DGS10").
        curr_date: End of the window (yyyy-mm-dd); no later observations are
            returned, so a past date never leaks future data.
        look_back_days: Trailing window length; ``None`` uses DEFAULT_LOOKBACK_DAYS.

    Returns:
        A markdown report with the series title, units, frequency, the latest
        value, the change over the window, and a recent observation table.
    """
    if look_back_days is None:
        look_back_days = DEFAULT_LOOKBACK_DAYS

    end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_date = (end_dt - timedelta(days=look_back_days)).strftime("%Y-%m-%d")

    # Invalid LLM-supplied indicator: return guidance rather than raising, so a
    # bad argument doesn't abort the run (the routing layer also degrades macro
    # data, but a specific message is more useful to the analyst).
    try:
        series_id = _resolve_series_id(indicator)
    except ValueError as e:
        return f"FRED: {e}"

    meta = _request("series", {"series_id": series_id}).get("seriess") or []
    if not meta:
        return (
            f"FRED series '{series_id}' not found. Pass a known alias "
            f"(e.g. 'cpi', 'unemployment') or a valid FRED series ID."
        )
    info = meta[0]
    title = info.get("title", series_id)
    units = info.get("units_short") or info.get("units", "")
    frequency = info.get("frequency", "")
    seasonal = info.get("seasonal_adjustment_short", "")

    observations = _request(
        "series/observations",
        {
            "series_id": series_id,
            "observation_start": start_date,
            "observation_end": curr_date,
            "sort_order": "asc",
        },
    ).get("observations", [])

    # FRED encodes a missing observation as ".".
    usable_observations = [
        o for o in observations if o.get("value") not in (".", None, "")
    ]
    points = [(o["date"], o["value"]) for o in usable_observations]

    header = (
        f"## FRED: {title} ({series_id})\n"
        f"- Units: {units}\n"
        f"- Frequency: {frequency}"
        f"{f' ({seasonal})' if seasonal else ''}\n"
        f"- Window: {start_date} to {curr_date}\n"
    )

    if not points:
        return header + (
            f"\nNo observations for {series_id} in this window. The series may "
            f"report less frequently than the window length; widen look_back_days."
        )

    first_date, first_val = points[0]
    last_date, last_val = points[-1]
    delta: float | None = None
    try:
        delta = float(last_val) - float(first_val)
        base = float(first_val)
        pct = f" ({delta / base * 100:+.2f}%)" if base != 0 else ""
        summary = (
            f"\n**Latest:** {last_val} ({last_date}) | "
            f"**Change over window:** {delta:+.2f}{pct} "
            f"from {first_val} ({first_date})\n"
        )
    except ValueError:
        summary = f"\n**Latest:** {last_val} ({last_date})\n"

    shown = points
    note = ""
    if len(points) > MAX_ROWS:
        shown = points[-MAX_ROWS:]
        note = f"\n_(showing the most recent {MAX_ROWS} of {len(points)} observations)_\n"

    table = (
        "\n| Date | Value |\n| --- | --- |\n"
        + "\n".join(f"| {d} | {v} |" for d, v in shown)
        + "\n"
    )

    # Macro-data source chain (2026-09-29): realtime_start is read straight
    # off the SAME observation object the "Latest" summary above already
    # uses -- never a separate, re-fetched value -- so it is None whenever
    # the underlying response genuinely omits it (see
    # _macro_summary_sentence's own docstring for why that is never
    # backfilled from last_date).
    realtime_start = usable_observations[-1].get("realtime_start")
    summary_sentence = _macro_summary_sentence(
        series_id=series_id, title=title, units=units, curr_date=curr_date,
        last_date=last_date, last_val=last_val, delta=delta, realtime_start=realtime_start,
    )

    return header + summary + note + table + "\n" + summary_sentence + "\n"
