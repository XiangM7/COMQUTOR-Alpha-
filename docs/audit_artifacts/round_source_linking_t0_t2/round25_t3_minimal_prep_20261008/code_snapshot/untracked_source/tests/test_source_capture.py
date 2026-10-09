"""John MVP Final Gap Closure -- Structured External Source Traceability.

Proves the data-acquisition-boundary capture (tradingagents.dataflows.
source_capture, and its use in yfinance_news.py) never changes what a
dataflow function returns to the calling agent, and that capture is
opt-in/no-op outside an active scope. Deterministic, offline, no network.
"""

from __future__ import annotations

import pytest

import tradingagents.dataflows.yfinance_news as ynews
from tradingagents.dataflows.source_capture import record_source, source_capture_scope


class _FakeTicker:
    def __init__(self, articles):
        self._articles = articles

    def get_news(self, count=None):
        return self._articles


def _flat_article(title, publisher, link, epoch_ts):
    return {"title": title, "publisher": publisher, "link": link, "providerPublishTime": epoch_ts, "summary": "s"}


def _epoch(date_str):
    import time
    from datetime import datetime

    return int(time.mktime(datetime.strptime(date_str, "%Y-%m-%d").timetuple()))


@pytest.mark.unit
def test_record_source_outside_any_scope_is_a_silent_noop():
    # No source_capture_scope active anywhere -- must never raise.
    record_source({"source_type": "news", "name": "X", "title": "Y", "url": "z"})


@pytest.mark.unit
def test_scope_yields_only_items_recorded_inside_it():
    with source_capture_scope() as sink:
        record_source({"source_type": "news", "name": "A"})
        assert sink == [{"source_type": "news", "name": "A"}]
    # Recording after the scope has exited must not resurrect the same list.
    record_source({"source_type": "news", "name": "B"})
    assert sink == [{"source_type": "news", "name": "A"}]


@pytest.mark.unit
def test_nested_scopes_do_not_leak_into_each_other():
    with source_capture_scope() as outer:
        record_source({"source_type": "news", "name": "outer-item"})
        with source_capture_scope() as inner:
            record_source({"source_type": "news", "name": "inner-item"})
        assert inner == [{"source_type": "news", "name": "inner-item"}]
        assert outer == [{"source_type": "news", "name": "outer-item"}]
        record_source({"source_type": "news", "name": "outer-item-2"})
    assert outer == [{"source_type": "news", "name": "outer-item"}, {"source_type": "news", "name": "outer-item-2"}]


@pytest.mark.unit
def test_get_news_yfinance_returns_byte_identical_text_regardless_of_capture(monkeypatch):
    articles = [_flat_article("A Real Headline", "Reuters", "https://reuters.com/x", _epoch("2025-05-05"))]
    monkeypatch.setattr(ynews.yf, "Ticker", lambda symbol: _FakeTicker(articles))
    monkeypatch.setattr(ynews, "normalize_symbol", lambda ticker: ticker)

    without_capture = ynews.get_news_yfinance("NVDA", "2025-05-01", "2025-05-09")
    with source_capture_scope():
        with_capture = ynews.get_news_yfinance("NVDA", "2025-05-01", "2025-05-09")

    assert without_capture == with_capture
    assert "A Real Headline" in without_capture


@pytest.mark.unit
def test_get_news_yfinance_captures_real_title_publisher_link_date(monkeypatch):
    articles = [_flat_article("A Real Headline About NVDA", "Reuters", "https://reuters.com/x", _epoch("2025-05-05"))]
    monkeypatch.setattr(ynews.yf, "Ticker", lambda symbol: _FakeTicker(articles))
    monkeypatch.setattr(ynews, "normalize_symbol", lambda ticker: ticker)

    with source_capture_scope() as sink:
        ynews.get_news_yfinance("NVDA", "2025-05-01", "2025-05-09")

    assert len(sink) == 1
    captured = sink[0]
    assert captured["source_type"] == "news"
    assert captured["name"] == "Reuters"
    assert captured["title"] == "A Real Headline About NVDA"
    assert captured["url"] == "https://reuters.com/x"
    assert captured["published_at"] == "2025-05-05T00:00:00"
    assert captured["provider"] == "yfinance"


@pytest.mark.unit
def test_get_news_yfinance_also_captures_the_real_summary_as_excerpt(monkeypatch):
    # T1 source-linking chain (COMQUTOR Alpha next-round task, 2026-09-26):
    # the same summary text already embedded verbatim in the report string
    # is additionally captured so comqutor_alpha.source_provenance can
    # compute a content hash / fragment_id for it -- still never changing
    # what the caller prints (see the byte-identical-text test above).
    articles = [
        _flat_article("A Real Headline About NVDA", "Reuters", "https://reuters.com/x", _epoch("2025-05-05"))
    ]
    articles[0]["summary"] = "NVDA reported record data center revenue this quarter."
    monkeypatch.setattr(ynews.yf, "Ticker", lambda symbol: _FakeTicker(articles))
    monkeypatch.setattr(ynews, "normalize_symbol", lambda ticker: ticker)

    with source_capture_scope() as sink:
        report_text = ynews.get_news_yfinance("NVDA", "2025-05-01", "2025-05-09")

    assert sink[0]["excerpt"] == "NVDA reported record data center revenue this quarter."
    # Still byte-present in the report text -- capture never subtracts it.
    assert "NVDA reported record data center revenue this quarter." in report_text


@pytest.mark.unit
def test_articles_filtered_out_of_the_window_are_never_captured(monkeypatch):
    # #992/#1007 look-ahead safety must still apply identically to capture:
    # an article the report itself excludes must not appear in the registry
    # either (never a source for a claim that was never shown).
    future_article = _flat_article("Future Headline", "Reuters", "https://x", _epoch("2025-06-01"))
    monkeypatch.setattr(ynews.yf, "Ticker", lambda symbol: _FakeTicker([future_article]))
    monkeypatch.setattr(ynews, "normalize_symbol", lambda ticker: ticker)

    with source_capture_scope() as sink:
        out = ynews.get_news_yfinance("NVDA", "2025-05-01", "2025-05-09")

    assert "Future Headline" not in out
    assert sink == []


@pytest.mark.unit
def test_no_news_found_captures_nothing(monkeypatch):
    monkeypatch.setattr(ynews.yf, "Ticker", lambda symbol: _FakeTicker([]))
    monkeypatch.setattr(ynews, "normalize_symbol", lambda ticker: ticker)

    with source_capture_scope() as sink:
        out = ynews.get_news_yfinance("NVDA", "2025-05-01", "2025-05-09")

    assert "No news found" in out
    assert sink == []
