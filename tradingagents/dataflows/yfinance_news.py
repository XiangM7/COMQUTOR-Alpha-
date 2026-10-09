"""yfinance-based news data fetching functions."""

import contextlib
from datetime import datetime

import yfinance as yf
from dateutil.relativedelta import relativedelta

from comqutor_alpha.source_provenance import fragment_id_for, make_source_id

from .config import get_config
from .source_capture import record_source
from .stockstats_utils import yf_retry
from .symbol_utils import normalize_symbol

# T1 source-linking chain, original-agent-input follow-up (2026-09-28):
# `tradingagents.dataflows.source_capture`'s own module docstring documents
# its earlier, narrower invariant -- capture is a side-channel that "never
# changes what the caller prints into the report text". This function does
# NOT touch that module or that invariant; it is a SEPARATE, newly
# authorized capability of THIS function's own text-building logic (the
# caller was always the one deciding what goes into news_str). Computing
# `source_id`/`fragment_id` here, with the EXACT SAME deterministic
# functions comqutor_alpha.source_provenance.build_source_record uses at
# persistence time, guarantees the marker embedded in the tool message the
# ORIGINAL research agent actually reads is byte-identical to the id that
# will later exist in source_registry.json -- never a locally-invented
# scheme that could drift out of sync with the real registry.
#
# This DOES make the original research agent's own input carry a real
# source_id/fragment_id for the first time (previously only the LATER,
# separate extraction-stage enrichment call received this via
# `candidate_sources` -- see structured_output_adapter.py's own "AGENT-
# STAGE COVERAGE" note). It does NOT prove the agent's own free-text report
# preserves the marker verbatim when it paraphrases/summarizes -- an LLM
# may drop it. That compliance rate is unmeasured here; see
# `structure_extractor`'s new `extract_source_marker_from_text` (T1 follow-
# up) for the deterministic, offline check of whether a marker survived
# into a claim's own segmented text, and never claim this function alone
# proves real-model citation behavior.
def _source_reference_marker(data: dict) -> str | None:
    source_id = make_source_id(
        source_type="news",
        name=data.get("publisher") or "",
        title=data.get("title") or "",
        url=data.get("link") or "",
    )
    if not data.get("summary"):
        return f"[source_id: {source_id}]"
    fragment_id = fragment_id_for(source_id, 0)
    return f"[source_id: {source_id}] [fragment_id: {fragment_id}]"


def _capture_news_source(data: dict) -> None:
    """Side-channel only: registers this already-extracted article's real
    title/publisher/link/date/summary for source-traceability persistence.
    Never changes what the caller prints into the report text -- see
    ``tradingagents.dataflows.source_capture``'s own module docstring for
    why this is safe to call unconditionally.

    ``excerpt`` (T1 source-linking chain, COMQUTOR Alpha next-round task,
    2026-09-26): the SAME ``summary`` string already embedded verbatim into
    the report text below (``news_str += f"{data['summary']}\\n"``) --
    genuinely upstream-supplied by yfinance, never LLM-paraphrased, never
    re-derived. Capturing it here does not change what the caller prints;
    it only additionally persists that exact text so
    ``comqutor_alpha.source_provenance`` can compute a content hash and a
    locatable ``fragment_id`` for it (see that module's ``build_source_
    record``)."""
    published_at = data["pub_date"].isoformat() if data.get("pub_date") is not None else None
    record_source(
        {
            "source_type": "news",
            "name": data.get("publisher"),
            "title": data.get("title"),
            "url": data.get("link"),
            "published_at": published_at,
            "provider": "yfinance",
            "excerpt": data.get("summary"),
        }
    )


def _extract_article_data(article: dict) -> dict:
    """Extract article data from yfinance news format (handles nested 'content' structure)."""
    # Handle nested content structure
    if "content" in article:
        content = article["content"]
        title = content.get("title", "No title")
        summary = content.get("summary", "")
        provider = content.get("provider", {})
        publisher = provider.get("displayName", "Unknown")

        # Get URL from canonicalUrl or clickThroughUrl
        url_obj = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
        link = url_obj.get("url", "")

        # Get publish date
        pub_date_str = content.get("pubDate", "")
        pub_date = None
        if pub_date_str:
            with contextlib.suppress(ValueError, AttributeError):
                pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))

        return {
            "title": title,
            "summary": summary,
            "publisher": publisher,
            "link": link,
            "pub_date": pub_date,
        }
    else:
        # Fallback for flat structure. Parse the epoch publish time so flat
        # articles are date-filterable too (otherwise they bypass the
        # historical window and leak future news, #992/#1007).
        pub_date = None
        ts = article.get("providerPublishTime")
        if ts:
            with contextlib.suppress(ValueError, OSError, TypeError):
                pub_date = datetime.fromtimestamp(ts)
        return {
            "title": article.get("title", "No title"),
            "summary": article.get("summary", ""),
            "publisher": article.get("publisher", "Unknown"),
            "link": article.get("link", ""),
            "pub_date": pub_date,
        }


def _in_news_window(pub_date, start_dt, end_dt) -> bool:
    """Whether an article belongs in the [start_dt, end_dt] window.

    Dated articles are kept only if they fall in the window. An undated article
    is kept only when the window reaches the present (live run) — in a
    historical/backtest window it's excluded, since we can't prove it isn't
    future news (look-ahead safety, #992/#1007).
    """
    if pub_date is not None:
        naive = pub_date.replace(tzinfo=None) if hasattr(pub_date, "replace") else pub_date
        return start_dt <= naive <= end_dt + relativedelta(days=1)
    return end_dt >= datetime.now() - relativedelta(days=1)


# The provider fields ``_extract_article_data`` actually reads, per response shape. Pinned by a test that changes each field
# and checks the parsed result moves (and that ``description`` -- not read -- does not), so this record cannot drift.
_PARSER_FIELDS_READ = {
    "nested (the article has a 'content' object)": [
        "content.title", "content.summary", "content.provider.displayName",
        "content.canonicalUrl.url | content.clickThroughUrl.url", "content.pubDate",
    ],
    "flat": ["title", "summary", "publisher", "link", "providerPublishTime"],
    "not read": ["content.description (and every other field)"],
}


def _record_provider_response(tool: str, request: dict, raw_items: list, per_article: list) -> None:
    """T1 closeout (Round 22): save the SANITIZED raw provider response next to what the parser read from it, in the run's
    capture container (written as ``provider_response_audit.json``). A side channel only: it never changes what the caller
    returns, never raises, and is a no-op outside a capture scope. Zero extra provider calls -- it only re-reads the
    already-fetched response."""
    try:
        from comqutor_alpha.capture_artifacts import build_news_response_entry

        from .source_capture import aux_capture_active, record_aux

        if not aux_capture_active():
            return
        record_aux(
            "provider_responses",
            build_news_response_entry(
                tool=tool, request=request, raw_items=raw_items, per_article=per_article,
                parser="tradingagents.dataflows.yfinance_news._extract_article_data",
                parser_fields_read=_PARSER_FIELDS_READ,
                library_version=getattr(yf, "__version__", None),
            ),
        )
    except Exception:  # noqa: BLE001 -- see the docstring: a capture side channel must never affect the tool
        return


def get_news_yfinance(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    """
    Retrieve news for a specific stock ticker using yfinance.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        Formatted string containing news articles
    """
    article_limit = get_config()["news_article_limit"]
    # Query Yahoo with the canonical symbol, like every other yfinance path —
    # a raw broker/forex/crypto alias (XAUUSD, BTCUSD) otherwise silently
    # returns no news. Keep the user's ticker in the report header.
    canonical = normalize_symbol(ticker)
    resolved = "" if canonical == ticker else f" (resolved to {canonical})"
    try:
        stock = yf.Ticker(canonical)
        news = yf_retry(lambda: stock.get_news(count=article_limit))
        request_info = {"symbol": canonical, "count": article_limit, "start_date": start_date, "end_date": end_date}

        if not news:
            _record_provider_response("get_news_yfinance", request_info, [], [])
            return f"No news found for {ticker}{resolved}"

        # Parse date range for filtering
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        news_str = ""
        filtered_count = 0
        per_article: list[dict] = []

        for article in news:
            data = _extract_article_data(article)

            # Keep only articles within the requested window (look-ahead safe).
            in_window = _in_news_window(data["pub_date"], start_dt, end_dt)
            per_article.append({"in_window": in_window, "captured_as_source": in_window, "parsed": data})
            if not in_window:
                continue

            news_str += f"### {data['title']} (source: {data['publisher']})\n"
            news_str += f"{_source_reference_marker(data)}\n"
            if data["summary"]:
                news_str += f"{data['summary']}\n"
            if data["link"]:
                news_str += f"Link: {data['link']}\n"
            news_str += "\n"
            filtered_count += 1
            _capture_news_source(data)

        _record_provider_response("get_news_yfinance", request_info, list(news), per_article)

        if filtered_count == 0:
            return f"No news found for {ticker}{resolved} between {start_date} and {end_date}"

        return f"## {ticker}{resolved} News, from {start_date} to {end_date}:\n\n{news_str}"

    except Exception as e:
        return f"Error fetching news for {ticker}: {str(e)}"


def _record_global_search_response(query: str, limit: int, curr_date: str, look_back_days: int, search: object) -> None:
    """Per-query raw response of the global-news search (see :func:`_record_provider_response`). Whether an item is later
    kept as a source depends on cross-query de-duplication and the limit, so ``captured_as_source`` is left unknown here --
    ``source_registry.json`` says what was captured."""
    try:
        raw_items = list(getattr(search, "news", None) or [])
        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_dt = curr_dt - relativedelta(days=look_back_days)
        per_article = []
        for article in raw_items:
            data = _extract_article_data(article)
            per_article.append({"in_window": _in_news_window(data["pub_date"], start_dt, curr_dt), "captured_as_source": None, "parsed": data})
        _record_provider_response(
            "get_global_news_yfinance", {"query": query, "news_count": limit, "enable_fuzzy_query": True, "curr_date": curr_date,
                                         "look_back_days": look_back_days}, raw_items, per_article,
        )
    except Exception:  # noqa: BLE001 -- capture side channel, never affects the tool
        return


def get_global_news_yfinance(
    curr_date: str,
    look_back_days: int | None = None,
    limit: int | None = None,
) -> str:
    """
    Retrieve global/macro economic news using yfinance Search.

    Args:
        curr_date: Current date in yyyy-mm-dd format
        look_back_days: Number of days to look back. ``None`` falls back to
            ``global_news_lookback_days`` from the active config.
        limit: Maximum number of articles to return. ``None`` falls back to
            ``global_news_article_limit`` from the active config.

    Returns:
        Formatted string containing global news articles
    """
    config = get_config()
    if look_back_days is None:
        look_back_days = config["global_news_lookback_days"]
    if limit is None:
        limit = config["global_news_article_limit"]
    search_queries = config["global_news_queries"]

    all_news = []
    seen_titles = set()

    try:
        for query in search_queries:
            search = yf_retry(lambda q=query: yf.Search(
                query=q,
                news_count=limit,
                enable_fuzzy_query=True,
            ))

            _record_global_search_response(query, limit, curr_date, look_back_days, search)

            if search.news:
                for article in search.news:
                    # Handle both flat and nested structures
                    if "content" in article:
                        data = _extract_article_data(article)
                        title = data["title"]
                    else:
                        title = article.get("title", "")

                    # Deduplicate by title
                    if title and title not in seen_titles:
                        seen_titles.add(title)
                        all_news.append(article)

            if len(all_news) >= limit:
                break

        if not all_news:
            return f"No global news found for {curr_date}"

        # Calculate date range
        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_dt = curr_dt - relativedelta(days=look_back_days)
        start_date = start_dt.strftime("%Y-%m-%d")

        news_str = ""
        kept = 0
        for article in all_news[:limit]:
            # Extract uniformly (flat + nested) and apply the same look-ahead-safe
            # window filter, so flat articles can't leak future news (#1007).
            data = _extract_article_data(article)
            if not _in_news_window(data["pub_date"], start_dt, curr_dt):
                continue
            news_str += f"### {data['title']} (source: {data['publisher']})\n"
            if data["summary"]:
                news_str += f"{data['summary']}\n"
            if data["link"]:
                news_str += f"Link: {data['link']}\n"
            news_str += "\n"
            kept += 1
            _capture_news_source(data)

        # All candidates fell outside the window -> say so rather than return an
        # empty-bodied report (#993).
        if kept == 0:
            return f"No global news found between {start_date} and {curr_date}"

        return f"## Global Market News, from {start_date} to {curr_date}:\n\n{news_str}"

    except Exception as e:
        return f"Error fetching global news: {str(e)}"
