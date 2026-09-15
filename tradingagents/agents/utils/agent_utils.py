import functools
import logging
import queue
import threading
import time
from collections.abc import Mapping
from concurrent.futures import Future
from concurrent.futures import TimeoutError as _FutureTimeoutError
from typing import Any

import yfinance as yf
from langchain_core.messages import HumanMessage, RemoveMessage

# Import tools from separate utility files
from tradingagents.agents.utils.core_stock_tools import get_stock_data
from tradingagents.agents.utils.fundamental_data_tools import (
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
)
from tradingagents.agents.utils.macro_data_tools import get_macro_indicators
from tradingagents.agents.utils.market_data_validation_tools import get_verified_market_snapshot
from tradingagents.agents.utils.news_data_tools import (
    get_global_news,
    get_insider_transactions,
    get_news,
)
from tradingagents.agents.utils.prediction_markets_tools import get_prediction_markets
from tradingagents.agents.utils.technical_indicators_tools import get_indicators

# Public surface: the data tools are imported here so agents and the graph
# import them from one place, plus the instrument/language helpers defined below.
__all__ = [
    "get_stock_data",
    "get_indicators",
    "get_fundamentals",
    "get_balance_sheet",
    "get_cashflow",
    "get_income_statement",
    "get_news",
    "get_global_news",
    "get_insider_transactions",
    "get_macro_indicators",
    "get_prediction_markets",
    "get_verified_market_snapshot",
    "build_instrument_context",
    "resolve_instrument_identity",
    "get_instrument_context_from_state",
    "get_language_instruction",
    "create_msg_delete",
]

logger = logging.getLogger(__name__)


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Applied to every agent whose output reaches the saved report —
    analysts, researchers, debaters, research manager, trader, and
    portfolio manager — so a non-English run produces a fully localized
    report rather than a mix of languages.
    """
    from tradingagents.dataflows.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


def _clean_identity_value(value: Any) -> str | None:
    """Return a trimmed string, or None for empty / placeholder-ish values."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or cleaned.lower() in {"none", "n/a", "nan", "null"}:
        return None
    return cleaned


class _DaemonThreadPool:
    """A small, fixed-size worker pool built on daemon threads only.

    ``concurrent.futures.ThreadPoolExecutor`` was tried first and rejected:
    besides a ``with ThreadPoolExecutor(...) as executor:`` block's
    ``__exit__`` blocking on ``shutdown(wait=True)`` (bounding the caller is
    not enough if cleanup then waits for the stuck worker anyway), the
    ``concurrent.futures.thread`` module itself registers a process-exit
    ``atexit`` hook that joins *every* worker thread of *every*
    ``ThreadPoolExecutor`` ever created -- so a lookup that genuinely never
    returns (a stalled socket, or this module's own "never returns" test
    fake) would hang the *entire process* at shutdown, not just this one
    call. This was caught empirically: the test suite for this hardening
    itself hung past its own timeout using a plain ``ThreadPoolExecutor``.

    Plain ``threading.Thread(daemon=True)`` workers sidestep that: daemon
    threads are abandoned (not joined) at interpreter exit, so a stuck
    lookup can never block process shutdown. Using a small FIXED pool
    (rather than one new daemon thread per call) additionally guarantees no
    unbounded thread growth under repeated timeouts -- exactly the property
    ``future.result(timeout=...)`` alone does not provide.
    """

    def __init__(self, max_workers: int, thread_name_prefix: str) -> None:
        self._max_workers = max_workers
        self._queue: queue.Queue = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._shutdown = False
        for i in range(max_workers):
            worker = threading.Thread(
                target=self._run, daemon=True, name=f"{thread_name_prefix}-{i}"
            )
            worker.start()
            self._threads.append(worker)

    def _run(self) -> None:
        while True:
            fn, args, fut = self._queue.get()
            if not fut.set_running_or_notify_cancel():
                continue
            try:
                result = fn(*args)
            except BaseException as exc:  # noqa: BLE001 — relay to the Future
                fut.set_exception(exc)
            else:
                fut.set_result(result)

    def submit(self, fn, *args) -> Future:
        fut: Future = Future()
        self._queue.put((fn, args, fut))
        return fut


# Bounded, shared, long-lived pool for the identity lookup below -- created
# once at import time (starts its fixed daemon-thread workers immediately;
# they sit idle on an empty queue until the first lookup, no import-time
# network activity) and never shut down. ``future.result(timeout=...)``
# bounds the caller's wait independent of whether the submitted task ever
# completes; the pool's own daemon threads bound *process* shutdown
# independent of whether a lookup ever completes (see _DaemonThreadPool).
_INSTRUMENT_IDENTITY_EXECUTOR = _DaemonThreadPool(
    max_workers=4, thread_name_prefix="instrument-identity-lookup"
)
# 10-15s target (John Requirement B follow-up, docs/audit_artifacts/
# v0_2_instrument_identity_timeout_fix.json): this lookup is best-effort,
# non-critical, and already fail-open by design, so a short bound costs
# nothing on the (overwhelmingly common) fast path -- empirically ~1s -- and
# caps the rare slow/stalled path far below the ~900s previously observed in
# three independent live runs that never reached the semantic pipeline.
_INSTRUMENT_IDENTITY_TIMEOUT_SECONDS = 12.0


def _fetch_yf_info(ticker: str) -> dict:
    """The actual (blocking, potentially slow or stalled) Yahoo Finance call.

    Extracted to its own function so tests can substitute a fake (including
    one that never returns) without touching the bounding/fail-open logic in
    ``resolve_instrument_identity`` itself. ``ticker`` here is already the
    normalized/canonical symbol.
    """
    return yf.Ticker(ticker).info or {}


@functools.lru_cache(maxsize=256)
def resolve_instrument_identity(ticker: str) -> dict:
    """Resolve deterministic identity metadata (company name, sector, …) for a ticker.

    This exists to stop the pipeline from hallucinating a *different* company
    when a chart pattern suggests a different industry than the real one
    (#814): without a ground-truth name, the market analyst would pattern-match
    the price action to a narrative and invent an identity that then cascaded
    through every downstream agent.

    Best-effort by design: if yfinance is unavailable, rate-limited, or doesn't
    recognise the ticker, we return ``{}`` and the caller falls back to
    ticker-only context rather than failing before analysis starts. Cached so
    the lookup happens at most once per ticker per process.

    The symbol is normalized first (e.g. ``XAUUSD`` -> ``GC=F``) so identity
    resolves for the same instrument the price path actually fetches (#983).

    Hard-bounded (John Requirement B follow-up): the actual yfinance call
    runs in a bounded worker pool with a ``_INSTRUMENT_IDENTITY_TIMEOUT_SECONDS``
    wall-clock cap, so a stalled Yahoo Finance connection can never block this
    function -- or the research pipeline calling it -- for more than that
    bound. A timeout is treated exactly like any other failure: fail open,
    return ``{}}``.
    """
    from tradingagents.dataflows.symbol_utils import normalize_symbol

    canonical = normalize_symbol(ticker)
    start = time.monotonic()
    logger.info(
        "tradingagents_diagnostic stage=INSTRUMENT_IDENTITY_START ticker=%s "
        "elapsed=0.0s timeout=%.1fs",
        ticker, _INSTRUMENT_IDENTITY_TIMEOUT_SECONDS,
    )
    future = _INSTRUMENT_IDENTITY_EXECUTOR.submit(_fetch_yf_info, canonical)
    try:
        info = future.result(timeout=_INSTRUMENT_IDENTITY_TIMEOUT_SECONDS) or {}
        if not isinstance(info, dict):
            # A malformed (non-dict) response is treated the same as an
            # empty one -- fail open, never guess/invent identity data.
            info = {}
    except _FutureTimeoutError:
        elapsed = time.monotonic() - start
        logger.warning(
            "tradingagents_diagnostic stage=INSTRUMENT_IDENTITY_TIMEOUT ticker=%s "
            "elapsed=%.3fs timeout=%.1fs",
            ticker, elapsed, _INSTRUMENT_IDENTITY_TIMEOUT_SECONDS,
        )
        logger.info(
            "tradingagents_diagnostic stage=INSTRUMENT_IDENTITY_END ticker=%s "
            "elapsed=%.3fs status=timeout",
            ticker, elapsed,
        )
        return {}
    except Exception as exc:  # noqa: BLE001 — fail open, never block the run
        elapsed = time.monotonic() - start
        logger.debug("Could not resolve instrument identity for %s: %s", ticker, exc)
        logger.info(
            "tradingagents_diagnostic stage=INSTRUMENT_IDENTITY_FAIL_OPEN ticker=%s "
            "elapsed=%.3fs exc_type=%s",
            ticker, elapsed, type(exc).__name__,
        )
        logger.info(
            "tradingagents_diagnostic stage=INSTRUMENT_IDENTITY_END ticker=%s "
            "elapsed=%.3fs status=fail_open",
            ticker, elapsed,
        )
        return {}

    elapsed = time.monotonic() - start
    logger.info(
        "tradingagents_diagnostic stage=INSTRUMENT_IDENTITY_SUCCESS ticker=%s elapsed=%.3fs",
        ticker, elapsed,
    )

    identity: dict[str, str] = {}
    company_name = _clean_identity_value(info.get("longName")) or _clean_identity_value(
        info.get("shortName")
    )
    if company_name:
        identity["company_name"] = company_name
    for source_key, target_key in (
        ("sector", "sector"),
        ("industry", "industry"),
        ("exchange", "exchange"),
        ("quoteType", "quote_type"),
    ):
        value = _clean_identity_value(info.get(source_key))
        if value:
            identity[target_key] = value
    logger.info(
        "tradingagents_diagnostic stage=INSTRUMENT_IDENTITY_END ticker=%s "
        "elapsed=%.3fs status=success",
        ticker, time.monotonic() - start,
    )
    return identity


def build_instrument_context(
    ticker: str,
    asset_type: str = "stock",
    identity: Mapping[str, str] | None = None,
) -> str:
    """Describe the exact instrument so agents preserve identity and ticker.

    When ``identity`` is provided (resolved deterministically via
    :func:`resolve_instrument_identity`), the company name and business
    classification are injected so agents anchor to the real company rather
    than pattern-matching the price chart to a wrong one (#814).
    """
    is_crypto = asset_type == "crypto"
    instrument_label = "asset" if is_crypto else "instrument"
    context = (
        f"The {instrument_label} to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`, `-USD`)."
    )

    details = []
    if identity:
        name = identity.get("company_name") or identity.get("name")
        if name:
            details.append(f"{'Name' if is_crypto else 'Company'}: {name}")
        sector, industry = identity.get("sector"), identity.get("industry")
        if sector and industry:
            details.append(f"Business classification: {sector} / {industry}")
        elif sector:
            details.append(f"Sector: {sector}")
        elif industry:
            details.append(f"Industry: {industry}")
        if identity.get("exchange"):
            details.append(f"Exchange: {identity['exchange']}")

    if details:
        context += (
            f" Resolved identity: {'; '.join(details)}. "
            "Do not substitute a different company or ticker unless a tool "
            "result explicitly disproves this resolved identity."
        )

    if is_crypto:
        context += (
            " Treat it as a crypto asset rather than a company, and do not "
            "assume company fundamentals are available."
        )
    return context


def get_instrument_context_from_state(state: Mapping[str, Any]) -> str:
    """Return the instrument context for the current run.

    Prefers the identity-resolved context computed once at run start and
    stored on the state (see ``TradingAgentsGraph.resolve_instrument_context``).
    Falls back to a ticker-only context — with no network lookup — when the
    state was constructed without it (bare programmatic states, tests), so a
    consumer is never forced to make a yfinance call mid-graph.
    """
    context = state.get("instrument_context")
    if isinstance(context, str) and context.strip():
        return context
    return build_instrument_context(
        str(state["company_of_interest"]),
        state.get("asset_type", "stock"),
    )


def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add a context-anchored placeholder.

        The placeholder must not be a bare ``"Continue"``: some
        OpenAI-compatible providers interpret that literally as the user task
        and produce output about the word "continue" instead of analysing the
        instrument (#888). Anchoring it to the resolved instrument context and
        date keeps the next analyst on-task even if the provider treats the
        placeholder as a standalone request.
        """
        messages = state["messages"]
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        instrument_context = get_instrument_context_from_state(state)
        trade_date = state.get("trade_date", "the requested date")
        placeholder = HumanMessage(
            content=(
                f"Proceed with your assigned analysis for this workflow. "
                f"{instrument_context} The analysis date is {trade_date}."
            )
        )
        return {"messages": removal_operations + [placeholder]}

    return delete_messages



