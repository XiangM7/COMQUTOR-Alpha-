"""T1 closeout (Round 22): two additive, present-only capture artifacts written next to ``source_registry.json``.

``derived_inputs.json``
    The COMPLETE input window a derived value was computed from -- not a row count, not the last N rows. For the market
    snapshot that is every OHLCV row ``stockstats`` saw (time index, columns, units, ascending order, the exact numbers),
    plus the method / library version / indicator definitions / data-processing settings, the saved outputs, and a
    sha256 of the series. :func:`recompute_ohlcv_indicators` rebuilds the indicators from those saved inputs ALONE
    (no provider call, no cache, no later data) and compares them with the saved outputs.

``provider_response_audit.json``
    The raw provider response (e.g. the yfinance article dicts), with secret-looking values and sensitive URL parameters
    redacted, next to what COMQUTOR's own parser read from each item. It exists so that "the provider supplied no summary"
    and "the parser did not read the field that carries it" can be told apart FOR A RUN THAT SAVES IT. It says nothing
    about runs that did not (they stay "cannot be distinguished").

Both artifacts are additive and present-only: a run without them is byte-for-byte what it was, nothing is backfilled
onto a historical run, and no existing field of ``source_registry.json`` changes meaning (the registry only gains
pointer keys inside ``calculation_params``). Pure functions only; zero network.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

DERIVED_INPUTS_FILENAME = "derived_inputs.json"
DERIVED_INPUTS_SCHEMA_VERSION = "derived_inputs.v1"
PROVIDER_RESPONSE_AUDIT_FILENAME = "provider_response_audit.json"
PROVIDER_RESPONSE_AUDIT_SCHEMA_VERSION = "provider_response_audit.v1"

CAPTURE_ARTIFACT_FILENAMES = (DERIVED_INPUTS_FILENAME, PROVIDER_RESPONSE_AUDIT_FILENAME)

# ---------------------------------------------------------------------------
# Derived inputs: the OHLCV window behind the market snapshot's technical indicators
# ---------------------------------------------------------------------------

OHLCV_COLUMNS: tuple[str, ...] = ("Open", "High", "Low", "Close", "Volume")
OHLCV_UNITS: dict[str, str] = {
    "Open": "USD (split/dividend adjusted when auto_adjust is true)",
    "High": "USD (split/dividend adjusted when auto_adjust is true)",
    "Low": "USD (split/dividend adjusted when auto_adjust is true)",
    "Close": "USD (split/dividend adjusted when auto_adjust is true)",
    "Volume": "shares",
}
TIME_INDEX_FORMAT = "YYYY-MM-DD"

# What the stockstats default indicator names mean, as verified numerically against stockstats==0.6.8 in
# tests/test_t1_closeout_capture_artifacts.py (COMQUTOR passes no overrides). A definition here that stops being true for
# the pinned library fails that test instead of silently drifting.
STOCKSTATS_DEFAULT_INDICATOR_DEFINITIONS: dict[str, dict[str, Any]] = {
    "close_10_ema": {"definition": "EMA of Close, span=10, adjust=False"},
    "close_50_sma": {"definition": "simple moving average of Close, window=50"},
    "close_200_sma": {"definition": "simple moving average of Close, window=200"},
    "rsi": {"definition": "stockstats rsi_14 (window=14)"},
    "boll": {"definition": "simple moving average of Close, window=20"},
    "boll_ub": {"definition": "boll + 2 x sample standard deviation (ddof=1) of Close over 20 periods"},
    "boll_lb": {"definition": "boll - 2 x sample standard deviation (ddof=1) of Close over 20 periods"},
    "macd": {"definition": "EMA(Close, span=12, adjust=False) - EMA(Close, span=26, adjust=False)"},
    "macds": {"definition": "EMA(macd, span=9, adjust=False)"},
    "macdh": {"definition": "macd - macds"},
    "atr": {"definition": "stockstats atr_14 (window=14)"},
}


def _json_number(value: Any) -> float | int | None:
    """A JSON-safe number: NaN / infinity / non-numbers -> ``None`` (never an invalid ``NaN`` token)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _volume_number(value: Any) -> float | int | None:
    number = _json_number(value)
    if number is not None and float(number).is_integer():
        return int(number)
    return number


def series_sha256(series: Mapping[str, Any]) -> str:
    """sha256 over the canonical JSON of the series' defining parts (time index, columns, rows) -- not of the
    descriptive extras around them, so the hash changes if and only if an input number changes."""
    payload = {"time_index": series.get("time_index"), "columns": list(series.get("columns") or []), "rows": series.get("rows") or []}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def format_indicator_value(value: Any) -> str:
    """The exact text form the market snapshot stores an indicator in (``market_data_validator._fmt``): two decimals,
    ``N/A`` for a missing value. Kept equal to that function by a test."""
    if value is None:
        return "N/A"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(number):
        return "N/A"
    return f"{number:.2f}"


def build_ohlcv_input_record(
    *,
    source_id: str,
    symbol: str,
    as_of_date: str,
    requested_analysis_date: str,
    frame: Any,
    indicator_names: Sequence[str],
    indicator_values: Mapping[str, str],
    stockstats_version: str,
    timezone_assumed: str,
    processing: Mapping[str, Any],
) -> dict[str, Any]:
    """One ``derived_inputs.json`` entry from the pandas frame (columns ``Date`` + OHLCV) the indicators were computed
    from. ``frame`` is exactly the verified, date-sorted frame the snapshot used -- every row of it is saved."""
    rows: list[list[Any]] = []
    for _, record in frame.iterrows():
        stamp = record["Date"]
        label = stamp.strftime("%Y-%m-%d") if hasattr(stamp, "strftime") else str(stamp)
        rows.append([label, *(_json_number(record.get(c)) if c != "Volume" else _volume_number(record.get(c)) for c in OHLCV_COLUMNS)])
    dates = [r[0] for r in rows]
    series: dict[str, Any] = {
        "time_index": {"name": "Date", "format": TIME_INDEX_FORMAT, "timezone_assumed": timezone_assumed,
                       "order": "ascending" if dates == sorted(dates) else "as_used_not_ascending"},
        "columns": list(OHLCV_COLUMNS),
        "units": dict(OHLCV_UNITS),
        "row_count": len(rows),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "rows": rows,
    }
    series["sha256"] = series_sha256(series)
    return {
        "input_id": f"{source_id}#ohlcv_window",
        "source_id": source_id,
        "kind": "ohlcv_window",
        "instrument": symbol.upper(),
        "requested_analysis_date": requested_analysis_date,
        "as_of_row_date": as_of_date,
        "series": series,
        "method": {
            "library": "stockstats",
            "version": f"stockstats=={stockstats_version}" if not str(stockstats_version).startswith("stockstats==") else stockstats_version,
            "call": "stockstats.wrap(frame.copy())[indicator].iloc[-1]",
            "indicators": list(indicator_names),
            "parameters": {
                "overrides": "none -- the library defaults apply",
                "definitions": {n: STOCKSTATS_DEFAULT_INDICATOR_DEFINITIONS.get(n, {"definition": "not documented here"}) for n in indicator_names},
            },
        },
        "processing": dict(processing),
        "outputs": {
            "as_of_row_date": as_of_date,
            "indicators": dict(indicator_values),
            "value_format": "two decimals, 'N/A' when missing (market_data_validator._fmt)",
        },
    }


def build_derived_inputs_artifact(*, run_id: str, ticker: str, entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """``derived_inputs.json``; one entry per distinct input record (same ``input_id`` -> the first one wins)."""
    seen: dict[str, dict[str, Any]] = {}
    for entry in entries:
        seen.setdefault(str(entry.get("input_id")), dict(entry))
    inputs = [seen[key] for key in sorted(seen)]
    return {
        "schema_version": DERIVED_INPUTS_SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "input_count": len(inputs),
        "scope_note": (
            "Every row of the input window a derived value was computed from, saved when the run captured it. A run "
            "written before this artifact existed has none and is NOT backfilled: its derived values keep their method, "
            "version and window parameters only."
        ),
        "inputs": inputs,
    }


def recompute_ohlcv_indicators(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Rebuild the indicators of one ``ohlcv_window`` entry from its SAVED series alone and compare them with the saved
    outputs. ``status``: ``REPRODUCED`` (every available indicator equal), ``MISMATCH``, ``SERIES_HASH_MISMATCH`` or
    ``NOT_RECOMPUTABLE`` (library missing, empty series, unsupported kind). Never reads anything but ``entry``."""
    result: dict[str, Any] = {"input_id": entry.get("input_id"), "status": "NOT_RECOMPUTABLE", "indicators": {}}
    series = entry.get("series")
    if entry.get("kind") != "ohlcv_window" or not isinstance(series, Mapping) or not series.get("rows"):
        result["reason"] = "no saved ohlcv series on this entry"
        return result
    result["series_hash_ok"] = series_sha256(series) == series.get("sha256")
    if not result["series_hash_ok"]:
        result["status"] = "SERIES_HASH_MISMATCH"
        result["reason"] = "the saved series does not hash to its recorded sha256 (it was altered or damaged)"
        return result
    try:
        import pandas as pd
        from stockstats import wrap
        from importlib.metadata import version as _dist_version
    except Exception as exc:  # pragma: no cover -- both are hard dependencies
        result["reason"] = f"recomputation library unavailable: {type(exc).__name__}"
        return result

    columns = ["Date", *series["columns"]]
    frame = pd.DataFrame(series["rows"], columns=columns)
    frame["Date"] = pd.to_datetime(frame["Date"])
    saved_version = str((entry.get("method") or {}).get("version") or "")
    try:
        current_version = f"stockstats=={_dist_version('stockstats')}"
    except Exception:  # pragma: no cover
        current_version = "unknown"
    result["library_version_saved"] = saved_version
    result["library_version_now"] = current_version
    result["version_match"] = saved_version == current_version

    stock_df = wrap(frame.copy())
    saved_outputs = (entry.get("outputs") or {}).get("indicators") or {}
    mismatched: list[str] = []
    unavailable: list[str] = []
    for name in (entry.get("method") or {}).get("indicators") or []:
        saved = saved_outputs.get(name)
        try:
            stock_df[name]  # triggers the stockstats calculation, exactly as the snapshot did
            recomputed = format_indicator_value(stock_df.iloc[-1][name])
        except Exception as exc:  # noqa: BLE001 -- mirrors the snapshot's own per-indicator guard
            recomputed = f"N/A ({type(exc).__name__})"
        if isinstance(saved, str) and saved.startswith("N/A"):
            unavailable.append(name)
            result["indicators"][name] = {"saved": saved, "recomputed": recomputed, "match": None, "note": "not available when saved"}
            continue
        match = saved == recomputed
        result["indicators"][name] = {"saved": saved, "recomputed": recomputed, "match": match}
        if not match:
            mismatched.append(name)
    result["mismatched"] = mismatched
    result["unavailable_when_saved"] = unavailable
    result["status"] = "REPRODUCED" if not mismatched else "MISMATCH"
    return result


def recompute_derived_inputs(artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute every entry of a ``derived_inputs.json`` payload; a compact run-level verdict plus the per-entry detail."""
    details = [recompute_ohlcv_indicators(e) for e in artifact.get("inputs") or [] if isinstance(e, Mapping)]
    statuses = Counter(d["status"] for d in details)
    return {"entries": len(details), "status_counts": dict(statuses), "all_reproduced": bool(details) and set(statuses) == {"REPRODUCED"}, "details": details}


# ---------------------------------------------------------------------------
# Provider response audit: sanitized raw provider response next to what the parser read
# ---------------------------------------------------------------------------

REDACTED = "[REDACTED]"
MAX_STRING_CHARS = 50_000
_MAX_DEPTH = 40

# Same standard as the Round-19 credential scan (docs/audit_artifacts/.../credential_scan.py).
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{24,}"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*['\"]?(?!<redacted|REDACTED|\*|None|null|\s)[A-Za-z0-9_\-/+=]{16,}"),
    re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^:\s/]+:(?!<redacted>|REDACTED|\*)[^@\s<]{3,}@"),
)
_SENSITIVE_NAME = re.compile(
    r"(?i)^(?:.*[_\-.])?(?:token|access[_-]?token|refresh[_-]?token|api[_-]?key|apikey|key|secret|password|passwd|authorization|"
    r"auth|cookie|set-cookie|crumb|session|sessionid|signature|sig|jwt|bearer|x-amz-signature|x-amz-credential|x-amz-security-token)"
    r"(?:[_\-.].*)?$"
)
_URL = re.compile(r"https?://[^\s\"'<>)\]]+")


class _Report:
    def __init__(self) -> None:
        self.redacted_values = 0
        self.redacted_url_parts = 0
        self.truncated_strings = 0

    def as_dict(self) -> dict[str, int]:
        return {"redacted_values": self.redacted_values, "redacted_url_parts": self.redacted_url_parts, "truncated_strings": self.truncated_strings}


def _redact_url(url: str, report: _Report) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    netloc = parts.netloc
    if "@" in netloc:  # user:password@host
        netloc = netloc.rsplit("@", 1)[1]
        report.redacted_url_parts += 1
    query = parts.query
    if query:
        pairs = parse_qsl(query, keep_blank_values=True)
        changed = False
        cleaned: list[tuple[str, str]] = []
        for name, value in pairs:
            if _SENSITIVE_NAME.match(name) and value:
                cleaned.append((name, REDACTED))
                changed = True
                report.redacted_url_parts += 1
            else:
                cleaned.append((name, value))
        if changed:
            query = urlencode(cleaned, safe="[]")
    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))


def _sanitize_string(text: str, report: _Report) -> str:
    def url_sub(match: re.Match[str]) -> str:
        return _redact_url(match.group(0), report)

    out = _URL.sub(url_sub, text)
    for pattern in _SECRET_PATTERNS:
        out, n = pattern.subn(REDACTED, out)
        report.redacted_values += n
    if len(out) > MAX_STRING_CHARS:
        report.truncated_strings += 1
        out = out[:MAX_STRING_CHARS] + f"...[TRUNCATED {len(out) - MAX_STRING_CHARS} chars]"
    return out


def _sanitize(value: Any, report: _Report, depth: int) -> Any:
    if depth > _MAX_DEPTH:
        return "[MAX_DEPTH]"
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else value
    if isinstance(value, str):
        return _sanitize_string(value, report)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return f"[BINARY {len(value)} bytes]"
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            if _SENSITIVE_NAME.match(name) and item not in (None, "", False):
                out[name] = REDACTED
                report.redacted_values += 1
            else:
                out[name] = _sanitize(item, report, depth + 1)
        return out
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_sanitize(item, report, depth + 1) for item in value]
    return _sanitize_string(str(value), report)


def sanitize_provider_value(value: Any) -> tuple[Any, dict[str, int]]:
    """Redact secret-looking values and sensitive URL parameters of a raw provider response; returns the sanitized copy
    and a count of what was redacted. The input is never mutated."""
    report = _Report()
    return _sanitize(value, report, 0), report.as_dict()


# Keys that carry article body text in the shapes the news provider is known to return (nested ``content`` and flat).
BODY_LIKE_KEYS = frozenset({"summary", "description", "body", "text", "snippet", "abstract", "excerpt", "content_text", "article", "html"})
_TITLE_KEYS = frozenset({"title", "headline"})
CLASSIFICATION_SUMMARY_PRESENT = "SUMMARY_PRESENT"
CLASSIFICATION_SUMMARY_EMPTY_OTHER_TEXT_PRESENT = "SUMMARY_EMPTY_BUT_OTHER_TEXT_FIELDS_NON_EMPTY"
CLASSIFICATION_NO_TEXT_BEYOND_TITLE = "NO_TEXT_FIELDS_BEYOND_TITLE"
CLASSIFICATIONS = (CLASSIFICATION_SUMMARY_PRESENT, CLASSIFICATION_SUMMARY_EMPTY_OTHER_TEXT_PRESENT, CLASSIFICATION_NO_TEXT_BEYOND_TITLE)


def text_field_inventory(raw: Any, *, _path: str = "", _out: dict[str, int] | None = None, _depth: int = 0) -> dict[str, int]:
    """``{dotted path: length}`` of every non-empty string leaf that is a title, a body-like field, or long free text
    (URLs and ids excluded) -- measured on the RAW value, before any redaction or truncation."""
    out: dict[str, int] = {} if _out is None else _out
    if _depth > _MAX_DEPTH:
        return out
    if isinstance(raw, Mapping):
        for key, item in raw.items():
            text_field_inventory(item, _path=f"{_path}.{key}" if _path else str(key), _out=out, _depth=_depth + 1)
    elif isinstance(raw, (list, tuple)):
        for index, item in enumerate(raw):
            text_field_inventory(item, _path=f"{_path}[{index}]", _out=out, _depth=_depth + 1)
    elif isinstance(raw, str) and raw.strip() and not raw.lstrip().startswith(("http://", "https://")):
        key = _path.rsplit(".", 1)[-1].split("[", 1)[0].lower()
        if key in BODY_LIKE_KEYS or key in _TITLE_KEYS or len(raw) > 200:
            out[_path] = len(raw)
    return out


def classify_article_text(*, parsed_summary_length: int, raw_text_fields: Mapping[str, int]) -> str:
    """A factual description of one raw article's text fields. It does NOT say why a field is empty: the first value means
    the parser got a summary; the second that no summary was parsed although another body-like field has text (a parse
    omission is possible and must be examined, it is not thereby proven); the third that the response carried no text
    beyond the title."""
    if parsed_summary_length > 0:
        return CLASSIFICATION_SUMMARY_PRESENT
    others = [p for p, n in raw_text_fields.items()
              if n > 0 and p.rsplit(".", 1)[-1].split("[", 1)[0].lower() not in _TITLE_KEYS and p.rsplit(".", 1)[-1].lower() != "summary"]
    return CLASSIFICATION_SUMMARY_EMPTY_OTHER_TEXT_PRESENT if others else CLASSIFICATION_NO_TEXT_BEYOND_TITLE


def build_news_response_entry(
    *,
    tool: str,
    request: Mapping[str, Any],
    raw_items: Sequence[Any],
    per_article: Sequence[Mapping[str, Any]],
    parser: str,
    parser_fields_read: Mapping[str, Sequence[str]],
    library_version: str | None,
    captured_at_utc: str | None = None,
) -> dict[str, Any]:
    """One ``provider_response_audit.json`` entry for one provider call. ``per_article[i]`` describes ``raw_items[i]``:
    ``{"in_window": bool|None, "captured_as_source": bool|None, "parsed": {"title": str, "summary": str, ...}}``."""
    sanitized_items, report = sanitize_provider_value(list(raw_items))
    parse_rows: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_items):
        info = per_article[index] if index < len(per_article) else {}
        parsed = info.get("parsed") or {}
        inventory = text_field_inventory(raw)
        summary_length = len(str(parsed.get("summary") or ""))
        parse_rows.append({
            "index": index,
            "in_window": info.get("in_window"),
            "captured_as_source": info.get("captured_as_source"),
            "parsed_title_length": len(str(parsed.get("title") or "")),
            "parsed_summary_length": summary_length,
            "raw_text_fields": inventory,
            "classification": classify_article_text(parsed_summary_length=summary_length, raw_text_fields=inventory),
        })
    safe_request, _ = sanitize_provider_value(dict(request))
    return {
        "tool": tool,
        "provider": "yfinance",
        "provider_library_version": library_version,
        "captured_at_utc": captured_at_utc or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "request": safe_request,
        "response": {"article_count": len(sanitized_items), "articles": sanitized_items, "sanitization": report},
        "parse": {
            "parser": parser,
            "fields_read": {k: list(v) for k, v in parser_fields_read.items()},
            "articles": parse_rows,
        },
    }


def build_provider_response_artifact(*, run_id: str, ticker: str, entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    article_total = 0
    for entry in entries:
        for row in (entry.get("parse") or {}).get("articles") or []:
            counts[row.get("classification")] += 1
            article_total += 1
    return {
        "schema_version": PROVIDER_RESPONSE_AUDIT_SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "entry_count": len(entries),
        "article_count": article_total,
        "classification_counts": {c: counts.get(c, 0) for c in CLASSIFICATIONS},
        "scope_note": (
            "Raw provider responses as returned, with secret-looking values and sensitive URL parameters redacted "
            "(see each entry's response.sanitization), next to what the parser read from each item. The classification "
            "describes which text fields were non-empty; it does not by itself say why a field is empty. Runs that did "
            "not save this file cannot answer that question and are not backfilled."
        ),
        "entries": [dict(e) for e in entries],
    }


__all__ = [
    "BODY_LIKE_KEYS",
    "CAPTURE_ARTIFACT_FILENAMES",
    "CLASSIFICATIONS",
    "DERIVED_INPUTS_FILENAME",
    "DERIVED_INPUTS_SCHEMA_VERSION",
    "OHLCV_COLUMNS",
    "PROVIDER_RESPONSE_AUDIT_FILENAME",
    "PROVIDER_RESPONSE_AUDIT_SCHEMA_VERSION",
    "STOCKSTATS_DEFAULT_INDICATOR_DEFINITIONS",
    "build_derived_inputs_artifact",
    "build_news_response_entry",
    "build_ohlcv_input_record",
    "build_provider_response_artifact",
    "classify_article_text",
    "format_indicator_value",
    "recompute_derived_inputs",
    "recompute_ohlcv_indicators",
    "sanitize_provider_value",
    "series_sha256",
    "text_field_inventory",
]
