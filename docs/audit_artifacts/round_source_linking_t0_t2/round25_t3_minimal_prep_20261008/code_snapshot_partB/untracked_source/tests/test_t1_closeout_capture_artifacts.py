"""T1 closeout (Round 22): the two additive capture artifacts -- ``derived_inputs.json`` and ``provider_response_audit.json``.

Everything here is OFFLINE and uses EXPLICITLY SYNTHETIC inputs (hand-built OHLCV frames, hand-built provider article dicts
returned by a fake ``yfinance``): it proves the saving / recomputation / redaction MECHANISM. It is not a real-market
validation sample and says nothing about what a real run's provider returns. Zero network, zero Provider calls.

Claims proven:
  derived inputs
    * the COMPLETE input window is saved (every row, time index, columns, units, ascending order) -- not a row count;
    * the saved inputs ALONE reproduce every saved indicator (no cache, no refetch, no original frame);
    * tampering is detected (hash) and a tampered-but-rehashed series no longer reproduces the saved outputs;
    * the recorded processing settings are the ones the code actually used (``load_ohlcv`` / ``_clean_dataframe``);
    * the recorded indicator definitions are true for the pinned library;
    * the registry only gains two pointer keys; legacy sources/runs without the artifact still load.
  provider responses
    * the raw response is saved, sanitized (secret patterns and sensitive URL parameters redacted), next to what the parser
      read; the tool's returned text is byte-identical with and without capture;
    * with-summary / empty-summary-with-description / title-only / flat shapes are each handled and classified factually;
    * the parser-field record equals the parser's real behaviour.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import tradingagents.dataflows.market_data_validator as validator
import tradingagents.dataflows.stockstats_utils as stockstats_utils
import tradingagents.dataflows.yfinance_news as ynews
from comqutor_alpha.adapters.tradingagents_output_writer import save_comqutor_run_outputs
from comqutor_alpha.api.artifact_export import build_and_write_artifact_manifest
from comqutor_alpha.capture_artifacts import (
    CLASSIFICATION_NO_TEXT_BEYOND_TITLE,
    CLASSIFICATION_SUMMARY_EMPTY_OTHER_TEXT_PRESENT,
    CLASSIFICATION_SUMMARY_PRESENT,
    CLASSIFICATIONS,
    DERIVED_INPUTS_FILENAME,
    PROVIDER_RESPONSE_AUDIT_FILENAME,
    STOCKSTATS_DEFAULT_INDICATOR_DEFINITIONS,
    build_derived_inputs_artifact,
    build_provider_response_artifact,
    format_indicator_value,
    recompute_derived_inputs,
    recompute_ohlcv_indicators,
    sanitize_provider_value,
    series_sha256,
)
from comqutor_alpha.source_provenance import build_source_registry, public_source_fields
from tradingagents.dataflows.source_capture import CapturedSources, record_aux, record_source, source_capture_scope

TICKER = "SYN"  # a synthetic instrument -- never a real-market validation sample
ANALYSIS_DATE = "2026-08-10"

# the same standard as the Round-19 credential scan
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"), re.compile(r"AIza[0-9A-Za-z_-]{30,}"), re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{24,}"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*['\"]?(?!<redacted|REDACTED|\*|None|null|\s)[A-Za-z0-9_\-/+=]{16,}"),
    re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^:\s/]+:(?!<redacted>|REDACTED|\*)[^@\s<]{3,}@"),
)


def _synthetic_ohlcv(rows: int = 320, seed: int = 11) -> pd.DataFrame:
    """320 business days: enough for the 200-day SMA. Random walk, fixed seed -- SYNTHETIC."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=ANALYSIS_DATE, periods=rows)
    close = 100 + np.cumsum(rng.normal(0, 1.0, rows))
    return pd.DataFrame({
        "Date": dates,
        "Open": close + rng.normal(0, 0.3, rows),
        "High": close + np.abs(rng.normal(1.0, 0.3, rows)),
        "Low": close - np.abs(rng.normal(1.0, 0.3, rows)),
        "Close": close,
        "Volume": rng.integers(1_000_000, 5_000_000, rows),
    })


def _capture_snapshot(monkeypatch, frame: pd.DataFrame | None = None):
    frozen = _synthetic_ohlcv() if frame is None else frame
    monkeypatch.setattr(validator, "load_ohlcv", lambda s, d: frozen)
    with source_capture_scope() as sink:
        text = validator.build_verified_market_snapshot(TICKER, ANALYSIS_DATE)
    return frozen, text, sink


# ---------------------------------------------------------------------------
# The capture container stays a plain list for every existing caller
# ---------------------------------------------------------------------------


def test_the_capture_container_is_still_a_plain_list_with_an_independent_aux_per_scope():
    with source_capture_scope() as outer:
        record_source({"source_type": "news", "name": "outer"})
        record_aux("derived_inputs", {"input_id": "outer"})
        with source_capture_scope() as inner:
            record_aux("derived_inputs", {"input_id": "inner"})
        assert inner.aux == {"derived_inputs": [{"input_id": "inner"}]}
    assert isinstance(outer, list) and isinstance(outer, CapturedSources)
    assert outer == [{"source_type": "news", "name": "outer"}]
    assert outer.aux == {"derived_inputs": [{"input_id": "outer"}]}
    record_aux("derived_inputs", {"input_id": "after"})  # outside any scope: a silent no-op
    assert outer.aux == {"derived_inputs": [{"input_id": "outer"}]}


# ---------------------------------------------------------------------------
# Derived inputs: complete window, recomputable from the saved inputs alone
# ---------------------------------------------------------------------------


def test_the_complete_input_window_is_saved_not_a_row_count_or_the_last_n_rows(monkeypatch):
    frozen, _text, sink = _capture_snapshot(monkeypatch)
    entries = sink.aux["derived_inputs"]
    assert len(entries) == 1
    series = entries[0]["series"]

    assert series["row_count"] == len(frozen) == len(series["rows"]) == 320  # every row, well beyond any "last 30"
    assert series["columns"] == ["Open", "High", "Low", "Close", "Volume"]
    assert series["time_index"] == {"name": "Date", "format": "YYYY-MM-DD", "timezone_assumed": "America/New_York", "order": "ascending"}
    assert series["units"]["Volume"] == "shares" and "USD" in series["units"]["Close"]
    assert series["first_date"] == frozen["Date"].iloc[0].strftime("%Y-%m-%d") and series["last_date"] == ANALYSIS_DATE
    dates = [row[0] for row in series["rows"]]
    assert dates == sorted(dates) and len(set(dates)) == len(dates)
    for saved, (_, original) in zip(series["rows"], frozen.iterrows(), strict=True):
        assert saved[1:5] == [float(original["Open"]), float(original["High"]), float(original["Low"]), float(original["Close"])]
        assert saved[5] == int(original["Volume"])
    assert series["sha256"] == series_sha256(series)


def test_the_registry_only_gains_two_pointer_keys_and_the_series_stays_out_of_it(monkeypatch):
    _frozen, _text, sink = _capture_snapshot(monkeypatch)
    source = sink[0]
    params = source["calculation_params"]
    assert params["input_series_artifact"] == DERIVED_INPUTS_FILENAME
    assert params["input_series_sha256"] == sink.aux["derived_inputs"][0]["series"]["sha256"]
    # the pre-existing keys are untouched, and nothing heavy leaked into the registry record
    assert {"symbol", "as_of_date", "window_start", "window_end", "row_count", "indicator_names"} <= set(params)
    assert "rows" not in json.dumps(source)
    registry = build_source_registry(run_id="r", ticker=TICKER, retrieved_at="2026-08-10T00:00:00Z", captured_records=list(sink))
    public = public_source_fields(registry["sources"][0])
    assert public["calculation_params"]["input_series_artifact"] == DERIVED_INPUTS_FILENAME
    assert len(json.dumps(public)) < 5_000  # what every linked claim's public source projection carries stays small


def test_the_saved_inputs_alone_reproduce_every_saved_indicator(monkeypatch, tmp_path):
    _frozen, _text, sink = _capture_snapshot(monkeypatch)
    artifact = build_derived_inputs_artifact(run_id="syn-run", ticker=TICKER, entries=sink.aux["derived_inputs"])
    # through a real file: the recomputation sees ONLY what was saved (no frame, no cache, no provider)
    path = tmp_path / DERIVED_INPUTS_FILENAME
    path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    reloaded = json.loads(path.read_text(encoding="utf-8"))

    verdict = recompute_derived_inputs(reloaded)
    assert verdict["all_reproduced"] is True and verdict["status_counts"] == {"REPRODUCED": 1}
    detail = verdict["details"][0]
    assert detail["series_hash_ok"] is True and detail["version_match"] is True
    assert set(detail["indicators"]) == set(validator.DEFAULT_SNAPSHOT_INDICATORS) and detail["mismatched"] == []
    saved = reloaded["inputs"][0]["outputs"]["indicators"]
    assert all(detail["indicators"][n]["recomputed"] == saved[n] and detail["indicators"][n]["match"] is True for n in saved)


def test_a_damaged_series_is_detected_and_a_rehashed_but_altered_series_no_longer_reproduces(monkeypatch):
    _frozen, _text, sink = _capture_snapshot(monkeypatch)
    entry = sink.aux["derived_inputs"][0]

    damaged = json.loads(json.dumps(entry))
    damaged["series"]["rows"][-1][4] += 10.0  # the last Close, hash NOT updated
    assert recompute_ohlcv_indicators(damaged)["status"] == "SERIES_HASH_MISMATCH"

    forged = json.loads(json.dumps(entry))
    forged["series"]["rows"][-1][4] += 10.0
    forged["series"]["sha256"] = series_sha256(forged["series"])  # consistent hash, different inputs
    verdict = recompute_ohlcv_indicators(forged)
    assert verdict["status"] == "MISMATCH" and "close_10_ema" in verdict["mismatched"]  # the recomputation really reads the series


def test_an_entry_without_a_series_is_not_recomputable_and_says_so():
    verdict = recompute_ohlcv_indicators({"input_id": "legacy", "kind": "ohlcv_window", "method": {"indicators": ["rsi"]}})
    assert verdict["status"] == "NOT_RECOMPUTABLE" and "no saved ohlcv series" in verdict["reason"]
    assert recompute_derived_inputs({"inputs": []}) == {"entries": 0, "status_counts": {}, "all_reproduced": False, "details": []}


def test_the_saved_indicator_text_format_equals_the_snapshots_own_format():
    for value in (618.5249, -0.0049, 0.0, 1e6 + 0.005, float("nan"), None, np.float64(53.77083)):
        assert format_indicator_value(value) == validator._fmt(value)


# ---- the recorded processing settings are the ones the code really used ---------------------------------------------


def test_the_recorded_download_settings_are_the_ones_load_ohlcv_actually_passes(monkeypatch, tmp_path):
    seen: dict = {}

    def fake_download(symbol, **kwargs):
        seen.update(kwargs)
        frame = _synthetic_ohlcv(40).set_index("Date")
        return frame

    monkeypatch.setattr(stockstats_utils, "get_config", lambda: {"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(stockstats_utils.yf, "download", fake_download)
    stockstats_utils.load_ohlcv("SYNTH", ANALYSIS_DATE)

    recorded = stockstats_utils.ohlcv_processing_settings()["provider_call"]
    assert seen["auto_adjust"] is recorded["auto_adjust"] is True
    assert seen["multi_level_index"] is recorded["multi_level_index"] is False and seen["progress"] is recorded["progress"] is False
    window_years = (pd.Timestamp(seen["end"]) - pd.Timestamp(seen["start"])).days / 365.25
    assert round(window_years) == stockstats_utils.OHLCV_WINDOW_YEARS == 5


def test_the_recorded_cleaning_steps_describe_what_the_cleaning_actually_does():
    messy = pd.DataFrame({
        "Date": ["2026-01-02", "not-a-date", "2026-01-06", "2026-01-07", "2026-01-08"],
        "Open": [10.0, 11.0, None, 13.0, 14.0],
        "High": [11.0, 12.0, 12.5, 14.0, 15.0],
        "Low": [9.0, 10.0, 11.0, 12.0, 13.0],
        "Close": [10.5, 11.5, 12.0, None, 14.5],
        "Volume": [100, 110, None, 130, 140],
    })
    cleaned = stockstats_utils._clean_dataframe(messy.copy())
    assert [d.strftime("%Y-%m-%d") for d in cleaned["Date"]] == ["2026-01-02", "2026-01-06", "2026-01-08"]  # unparseable Date, missing Close dropped
    assert cleaned["Open"].tolist() == [10.0, 10.0, 14.0]  # the gap on 01-06 was forward-filled
    assert cleaned["Volume"].tolist() == [100.0, 100.0, 140.0]
    steps = stockstats_utils.ohlcv_processing_settings()["cleaning"]
    assert len(steps) == 4 and "drop rows whose Date cannot be parsed" in steps[0] and "forward-fill" in steps[3]


def test_the_recorded_indicator_definitions_are_true_for_the_pinned_library():
    frame = _synthetic_ohlcv(400, seed=7)
    from stockstats import wrap

    stock = wrap(frame.copy())
    close = frame["Close"].reset_index(drop=True)

    def last(name):
        return float(stock[name].iloc[-1])

    ema = lambda series, span: series.ewm(span=span, adjust=False).mean()  # noqa: E731
    macd = ema(close, 12) - ema(close, 26)
    expected = {
        "close_10_ema": ema(close, 10).iloc[-1],
        "close_50_sma": close.rolling(50).mean().iloc[-1],
        "close_200_sma": close.rolling(200).mean().iloc[-1],
        "rsi": last("rsi_14"),
        "boll": close.rolling(20).mean().iloc[-1],
        "boll_ub": close.rolling(20).mean().iloc[-1] + 2 * close.rolling(20).std(ddof=1).iloc[-1],
        "boll_lb": close.rolling(20).mean().iloc[-1] - 2 * close.rolling(20).std(ddof=1).iloc[-1],
        "macd": macd.iloc[-1],
        "macds": ema(macd, 9).iloc[-1],
        "macdh": macd.iloc[-1] - ema(macd, 9).iloc[-1],
        "atr": last("atr_14"),
    }
    assert set(expected) == set(STOCKSTATS_DEFAULT_INDICATOR_DEFINITIONS) == set(validator.DEFAULT_SNAPSHOT_INDICATORS)
    for name, value in expected.items():
        assert last(name) == pytest.approx(float(value), rel=1e-6, abs=1e-6), name


# ---- legacy compatibility -----------------------------------------------------------------------------------------


def test_a_legacy_source_without_pointer_keys_still_builds_and_projects_exactly_as_before():
    legacy = {"source_type": "market", "name": "Yahoo Finance", "title": "OLD verified market snapshot 2026-01-02", "provider": "yfinance",
              "excerpt": "OLD 2026-01-02 OHLCV Open=1.00", "instrument": "OLD", "observation_date": "2026-01-02", "timezone": "America/New_York",
              "unit": "USD", "data_snapshot": {"ohlcv": {"Close": "1.00"}}, "calculation_method": "stockstats",
              "calculation_version": "stockstats==0.6.8", "calculation_params": {"symbol": "OLD", "row_count": 120, "indicator_names": ["rsi"]}}
    registry = build_source_registry(run_id="old", ticker="OLD", retrieved_at="2026-01-02T00:00:00Z", captured_records=[legacy])
    source = registry["sources"][0]
    assert source["calculation_params"] == legacy["calculation_params"]  # nothing added to a record that never had the pointer
    assert "input_series_artifact" not in public_source_fields(source)["calculation_params"]


def test_the_writer_saves_the_artifacts_only_when_captured_and_the_manifest_lists_only_those(tmp_path, monkeypatch):
    _frozen, _text, sink = _capture_snapshot(monkeypatch)
    final_state = {"market_report": "Market report text.", "final_trade_decision": "Final decision."}

    run_dir = save_comqutor_run_outputs(final_state=final_state, ticker=TICKER, config={"llm_provider": "openai"}, selected_analysts=["market"],
                                        analysis_date=ANALYSIS_DATE, output_root=tmp_path, captured_sources=sink)
    saved = json.loads((run_dir / DERIVED_INPUTS_FILENAME).read_text(encoding="utf-8"))
    assert saved["schema_version"] == "derived_inputs.v1" and saved["run_id"] == run_dir.name and saved["input_count"] == 1
    assert saved["inputs"][0]["series"]["row_count"] == 320
    assert not (run_dir / PROVIDER_RESPONSE_AUDIT_FILENAME).exists()  # nothing of that kind was captured
    manifest = build_and_write_artifact_manifest(run_id=run_dir.name, ticker=TICKER, output_root=tmp_path)
    listed = {a["artifact_name"] for a in manifest["artifacts"]}
    assert DERIVED_INPUTS_FILENAME in listed and PROVIDER_RESPONSE_AUDIT_FILENAME not in listed

    plain = save_comqutor_run_outputs(final_state=final_state, ticker=TICKER, config={"llm_provider": "openai"}, selected_analysts=["market"],
                                      analysis_date=ANALYSIS_DATE, output_root=tmp_path, captured_sources=[])
    assert not (plain / DERIVED_INPUTS_FILENAME).exists() and not (plain / PROVIDER_RESPONSE_AUDIT_FILENAME).exists()
    plain_listed = {a["artifact_name"] for a in build_and_write_artifact_manifest(run_id=plain.name, ticker=TICKER, output_root=tmp_path)["artifacts"]}
    assert not {DERIVED_INPUTS_FILENAME, PROVIDER_RESPONSE_AUDIT_FILENAME} & plain_listed  # a run without them lists nothing new


def test_the_trace_reports_the_saved_input_window_and_its_recomputation_and_a_run_without_it_as_not_saved(tmp_path, monkeypatch):
    """SYNTHETIC inputs attached to the market source of the real AMD excerpt fixture: proves the trace's reading of the artifact."""
    from comqutor_alpha.api.evidence_trace import build_claim_trace, load_trace_context

    amd = json.loads((Path(__file__).parent / "fixtures" / "t1_closure_amd_excerpt.json").read_text(encoding="utf-8"))
    market = next(src for src in amd["sources"] if src["source_type"] == "market")
    claim = next(r["claim_id"] for r in amd["records"] if r.get("linked_source_id") == market["source_id"])
    _frozen, _text, sink = _capture_snapshot(monkeypatch)
    entry = json.loads(json.dumps(sink.aux["derived_inputs"][0]))
    entry["source_id"], entry["input_id"] = market["source_id"], market["source_id"] + "#ohlcv_window"

    def write_run(run_id: str, *, with_artifact: bool) -> None:
        run_dir = tmp_path / run_id
        run_dir.mkdir()
        sources = json.loads(json.dumps(amd["sources"]))
        if with_artifact:
            next(src for src in sources if src["source_id"] == market["source_id"])["calculation_params"]["input_series_sha256"] = entry["series"]["sha256"]
            (run_dir / DERIVED_INPUTS_FILENAME).write_text(json.dumps(build_derived_inputs_artifact(run_id=run_id, ticker="AMD", entries=[entry])), encoding="utf-8")
        write = lambda name, data: (run_dir / name).write_text(json.dumps(data), encoding="utf-8")  # noqa: E731
        write("metadata.json", {"run_id": run_id, "ticker": "AMD", "analysis_date": amd["metadata"]["analysis_date"]})
        write("structured_agent_outputs.json", {"run_id": run_id, "ticker": "AMD", "records": amd["records"]})
        write("alpha_matches.json", {"run_id": run_id, "ticker": "AMD", "matches": amd["matches"]})
        write("source_registry.json", {"schema_version": "source_registry.v2", "run_id": run_id, "ticker": "AMD", "source_count": len(sources), "sources": sources})

    write_run("with-inputs", with_artifact=True)
    saved_view = next(v for v in (src["derived_inputs"] for src in build_claim_trace(load_trace_context("with-inputs", tmp_path), claim)["sources"]) if v)
    assert saved_view["status"] == "SAVED" and saved_view["row_count"] == 320 and saved_view["series_hash_ok"] is True
    assert saved_view["registry_pointer_matches"] is True
    assert saved_view["recomputation"]["status"] == "REPRODUCED" and saved_view["recomputation"]["indicators_checked"] == 11
    assert saved_view["recomputation"]["mismatched"] == []

    write_run("without-inputs", with_artifact=False)
    legacy_view = next(v for v in (src["derived_inputs"] for src in build_claim_trace(load_trace_context("without-inputs", tmp_path), claim)["sources"]) if v)
    assert legacy_view["status"] == "NOT_SAVED" and "Nothing is backfilled" in legacy_view["note"]
    assert legacy_view["method"] == "stockstats" and legacy_view["window_parameters"].get("row_count") is not None


# ---------------------------------------------------------------------------
# Provider response audit
# ---------------------------------------------------------------------------


class _FakeTicker:
    def __init__(self, articles):
        self._articles = articles

    def get_news(self, count=10):
        return list(self._articles)


def _nested(title, *, summary="", description="", pub="2025-05-05T12:00:00Z", url="https://example.com/a", extra=None):
    content = {"id": "n-" + title, "contentType": "STORY", "title": title, "summary": summary, "description": description, "pubDate": pub,
               "provider": {"displayName": "Wire"}, "canonicalUrl": {"url": url}}
    content.update(extra or {})
    return {"id": "n-" + title, "content": content}


def _flat(title, *, summary="", ts=1746446400, link="https://example.com/f"):
    return {"title": title, "summary": summary, "publisher": "Wire", "link": link, "providerPublishTime": ts}


def _run_news(monkeypatch, articles, *, capture):
    monkeypatch.setattr(ynews.yf, "Ticker", lambda symbol: _FakeTicker(articles))
    monkeypatch.setattr(ynews, "normalize_symbol", lambda t: t)
    if not capture:
        return ynews.get_news_yfinance(TICKER, "2025-05-01", "2025-05-09"), None
    with source_capture_scope() as sink:
        text = ynews.get_news_yfinance(TICKER, "2025-05-01", "2025-05-09")
    return text, sink


ARTICLES = [
    _nested("With a summary", summary="Revenue rose on data-center demand."),
    _nested("Empty summary, description present", summary="", description="<p>The company reported higher revenue and wider margins this quarter.</p>"),
    _nested("Title only"),
    _flat("Flat with a summary", summary="Flat-shape summary text."),
    _flat("Flat without a summary"),
    _nested("Outside the window", summary="Old news.", pub="2024-01-01T00:00:00Z"),
]


def test_the_news_tool_returns_byte_identical_text_with_and_without_the_audit_capture(monkeypatch):
    without, _ = _run_news(monkeypatch, ARTICLES, capture=False)
    with_capture, sink = _run_news(monkeypatch, ARTICLES, capture=True)
    assert without == with_capture
    assert "With a summary" in without and "Outside the window" not in without
    assert sink.aux["provider_responses"]  # and the capture did happen


def test_each_response_shape_is_classified_factually_and_the_registry_keeps_its_old_behaviour(monkeypatch):
    _text, sink = _run_news(monkeypatch, ARTICLES, capture=True)
    entry = sink.aux["provider_responses"][0]
    rows = {row["index"]: row for row in entry["parse"]["articles"]}
    assert entry["response"]["article_count"] == len(ARTICLES) == len(rows)
    assert rows[0]["classification"] == CLASSIFICATION_SUMMARY_PRESENT and rows[0]["parsed_summary_length"] > 0
    assert rows[1]["classification"] == CLASSIFICATION_SUMMARY_EMPTY_OTHER_TEXT_PRESENT and rows[1]["parsed_summary_length"] == 0
    assert any(path.endswith("description") and n > 0 for path, n in rows[1]["raw_text_fields"].items())
    assert rows[2]["classification"] == CLASSIFICATION_NO_TEXT_BEYOND_TITLE
    assert rows[3]["classification"] == CLASSIFICATION_SUMMARY_PRESENT  # flat shape
    assert rows[4]["classification"] == CLASSIFICATION_NO_TEXT_BEYOND_TITLE
    assert rows[5]["in_window"] is False and rows[5]["captured_as_source"] is False and rows[0]["captured_as_source"] is True
    assert set(CLASSIFICATIONS) == {CLASSIFICATION_SUMMARY_PRESENT, CLASSIFICATION_SUMMARY_EMPTY_OTHER_TEXT_PRESENT, CLASSIFICATION_NO_TEXT_BEYOND_TITLE}
    # the existing source capture is unchanged: an excerpt exists exactly when the parser got a summary
    by_title = {s["title"]: s for s in sink}
    assert by_title["With a summary"]["excerpt"] == "Revenue rose on data-center demand."
    assert not by_title["Empty summary, description present"]["excerpt"] and not by_title["Title only"]["excerpt"]
    assert "Outside the window" not in by_title


def test_the_raw_response_is_saved_whole_so_a_later_reader_can_tell_a_missing_summary_from_an_unread_field(monkeypatch):
    _text, sink = _run_news(monkeypatch, ARTICLES, capture=True)
    entry = sink.aux["provider_responses"][0]
    raw_article = entry["response"]["articles"][1]
    assert raw_article["content"]["summary"] == "" and "higher revenue and wider margins" in raw_article["content"]["description"]
    assert entry["provider"] == "yfinance" and entry["request"]["symbol"] == TICKER and entry["captured_at_utc"].endswith(("Z", "+00:00"))
    artifact = build_provider_response_artifact(run_id="syn", ticker=TICKER, entries=sink.aux["provider_responses"])
    # 3 with a summary (nested, flat, and the out-of-window one -- the audit covers every item the provider returned),
    # 1 empty summary with another text field, 2 with nothing beyond the title
    assert artifact["classification_counts"] == {CLASSIFICATION_SUMMARY_PRESENT: 3, CLASSIFICATION_SUMMARY_EMPTY_OTHER_TEXT_PRESENT: 1,
                                                 CLASSIFICATION_NO_TEXT_BEYOND_TITLE: 2}
    assert artifact["article_count"] == len(ARTICLES) == 6
    assert "does not by itself say why a field is empty" in artifact["scope_note"]  # no cause is claimed


def test_the_recorded_parser_fields_are_what_the_parser_really_reads():
    nested = _nested("T", summary="S", description="D")
    base = ynews._extract_article_data(nested)
    assert (base["title"], base["summary"], base["publisher"], base["link"]) == ("T", "S", "Wire", "https://example.com/a")
    for path, key, sentinel in (("content.title", "title", "T2"), ("content.summary", "summary", "S2"), ("content.provider.displayName", "publisher", "P2"),
                                ("content.canonicalUrl.url", "link", "https://example.com/changed")):
        changed = json.loads(json.dumps(nested))
        node = changed
        *parents, leaf = path.split(".")
        for part in parents:
            node = node[part]
        node[leaf] = sentinel
        assert ynews._extract_article_data(changed)[key] == sentinel, path
    only_description_changed = json.loads(json.dumps(nested))
    only_description_changed["content"]["description"] = "a completely different body"
    assert ynews._extract_article_data(only_description_changed) == base  # description is NOT read
    flat = _flat("T", summary="S")
    assert ynews._extract_article_data(flat)["summary"] == "S" and ynews._extract_article_data({**flat, "description": "D"}) == ynews._extract_article_data(flat)
    recorded = ynews._PARSER_FIELDS_READ
    assert "content.summary" in recorded["nested (the article has a 'content' object)"] and "content.description" not in recorded["nested (the article has a 'content' object)"]
    assert recorded["not read"] == ["content.description (and every other field)"]


def test_secrets_and_sensitive_url_parameters_are_redacted_but_the_content_is_kept(monkeypatch):
    secret_article = _nested(
        "AMD results beat", summary="",
        description="<p>Body text about revenue growth. Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789ABC end.</p>",
        url="https://example.com/a?id=7&token=SECRETVALUE123456&utm_source=rss",
        extra={"clickThroughUrl": {"url": "https://user:pass1234@example.com/b?apikey=ABCDEF1234567890&page=2"},
               "thumbnail": {"resolutions": [{"url": "https://img.example.com/x.png?X-Amz-Signature=deadbeefcafebabe&w=100"}]},
               "connection": "postgresql://svc:hunter2hunter2@db.internal/app"},
    )
    secret_article["api_key"] = "sk-abcdefghijklmnopqrstuvwxyz012345"
    secret_article["Authorization"] = "Bearer should-never-be-saved-0123456789"
    _text, sink = _run_news(monkeypatch, [secret_article], capture=True)
    artifact = build_provider_response_artifact(run_id="syn", ticker=TICKER, entries=sink.aux["provider_responses"])
    blob = json.dumps(artifact, ensure_ascii=False)

    for leaked in ("SECRETVALUE123456", "pass1234", "ABCDEF1234567890", "deadbeefcafebabe", "sk-abcdefghijklmnopqrstuvwxyz012345",
                   "abcdefghijklmnopqrstuvwxyz0123456789ABC", "should-never-be-saved", "hunter2hunter2"):
        assert leaked not in blob, leaked
    assert not [p.pattern for p in SECRET_PATTERNS if p.search(blob)]  # the same standard the Round-19 credential scan applies
    assert "utm_source=rss" in blob and "page=2" in blob and "AMD results beat" in blob and "Body text about revenue growth" in blob
    report = artifact["entries"][0]["response"]["sanitization"]
    assert report["redacted_values"] >= 3 and report["redacted_url_parts"] >= 4


def test_sanitization_never_mutates_its_input_and_handles_odd_values():
    original = {"url": "https://h.example/p?token=abcdef123456&q=1", "n": float("nan"), "when": pd.Timestamp("2026-01-02"), "blob": b"\x00\x01", "s": {1, 2}}
    snapshot = json.dumps(original, default=str)
    cleaned, report = sanitize_provider_value(original)
    assert json.dumps(original, default=str) == snapshot and report["redacted_url_parts"] == 1
    assert cleaned["n"] is None and cleaned["when"].startswith("2026-01-02") and cleaned["blob"].startswith("[BINARY")
    assert "token=%5BREDACTED%5D" in cleaned["url"] or "token=[REDACTED]" in cleaned["url"]
    assert "x" * 60_000 != sanitize_provider_value("x" * 60_000)[0] and sanitize_provider_value("x" * 60_000)[1]["truncated_strings"] == 1


def test_the_global_news_search_records_one_entry_per_query_without_changing_its_text(monkeypatch):
    class _Search:
        def __init__(self, query, news_count, enable_fuzzy_query):
            self.news = [_nested(f"Macro story for {query}", summary="Rates held steady.", pub="2026-08-09T10:00:00Z")]

    monkeypatch.setattr(ynews.yf, "Search", _Search)
    monkeypatch.setattr(ynews, "get_config", lambda: {"global_news_lookback_days": 7, "global_news_article_limit": 5, "global_news_queries": ["fed", "oil"],
                                                      "news_article_limit": 5})
    without = ynews.get_global_news_yfinance(ANALYSIS_DATE)
    with source_capture_scope() as sink:
        with_capture = ynews.get_global_news_yfinance(ANALYSIS_DATE)
    assert without == with_capture
    entries = sink.aux["provider_responses"]
    assert [e["request"]["query"] for e in entries] == ["fed", "oil"] and all(e["tool"] == "get_global_news_yfinance" for e in entries)
    assert all(e["parse"]["articles"][0]["captured_as_source"] is None for e in entries)  # dedupe/limit happen later: unknown here
