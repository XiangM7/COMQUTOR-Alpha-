"""Hard-bound tests for resolve_instrument_identity (John Requirement B
follow-up, docs/audit_artifacts/v0_2_instrument_identity_timeout_fix.json).

The critical property under test is REAL WALL-CLOCK RETURN BOUND: a fake
lookup that never returns must still make ``resolve_instrument_identity``
return (the fallback) within the configured timeout plus a small test
tolerance -- not merely raise/observe a TimeoutError while the caller then
waits for the underlying worker anyway. See the module docstring on
``_DaemonThreadPool`` in agent_utils.py for why a naive
``with ThreadPoolExecutor(...):`` block (or even a bare, never-shut-down one)
fails this property in a way that ``future.result(timeout=...)`` alone
cannot fix: ``concurrent.futures.thread`` registers a process-exit
``atexit`` hook that JOINS every worker thread of every ThreadPoolExecutor
ever created, so a genuinely-stuck task hangs the whole *process* at exit,
not just the one call. This was caught empirically while writing this very
test file.

Every test here that submits a task which NEVER returns uses its own
throwaway ``_DaemonThreadPool`` (swapped in via monkeypatching
``agent_utils._INSTRUMENT_IDENTITY_EXECUTOR``), never the shared,
module-level production pool. This mirrors reality: a pool exhausted by
several *simultaneous, truly-infinite* hangs is a deliberately-accepted,
inherent tradeoff of any fixed-size pool (the alternative -- unbounded
thread growth -- is explicitly what this design avoids), but it is also a
scenario a genuinely infinite test fake can trigger far more easily than
production ever would (yfinance's own calls carry ~30s-per-request internal
timeouts, so a real stall is bounded, just not by this codebase). Isolating
each such test's pool keeps that realistic, rare tradeoff from cross-
contaminating unrelated tests in the same run.
"""

from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import patch

import pytest

from comqutor_alpha.runners.tradingagents_runner import run_streaming_tradingagents_research
from tradingagents.agents.utils import agent_utils
from tradingagents.agents.utils.agent_utils import _DaemonThreadPool, resolve_instrument_identity

_TEST_TIMEOUT_SECONDS = 0.15  # per task spec: 0.1-0.2s test-mode bound


def _never_returns(_ticker):
    """A fake lookup that genuinely blocks forever (no timeout on the wait)."""
    threading.Event().wait()
    raise AssertionError("unreachable -- this fake must never return")


def _fresh_pool():
    """A throwaway pool for tests that submit genuinely-never-returning
    tasks, so exhausting it never affects the shared production pool other
    tests (and production code) rely on."""
    return _DaemonThreadPool(max_workers=4, thread_name_prefix="test-identity-lookup")


@pytest.mark.unit
class RealWallClockBoundTests(unittest.TestCase):
    def setUp(self):
        resolve_instrument_identity.cache_clear()
        self._patches = [
            patch.object(agent_utils, "_INSTRUMENT_IDENTITY_TIMEOUT_SECONDS", _TEST_TIMEOUT_SECONDS),
            patch.object(agent_utils, "_INSTRUMENT_IDENTITY_EXECUTOR", _fresh_pool()),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def test_hanging_lookup_returns_fallback_within_bound_plus_small_tolerance(self):
        with patch.object(agent_utils, "_fetch_yf_info", side_effect=_never_returns):
            start = time.monotonic()
            result = resolve_instrument_identity("NEVER-RETURNS-1")
            elapsed = time.monotonic() - start

        self.assertEqual(result, {})
        # The measured CALL itself must be bounded -- not merely a caught
        # TimeoutError while the caller silently waited longer afterward.
        self.assertLess(
            elapsed, _TEST_TIMEOUT_SECONDS + 1.0,
            f"resolve_instrument_identity took {elapsed:.3f}s -- the bound was not real",
        )

    def test_timeout_is_logged_with_stage_markers(self):
        with self.assertLogs("tradingagents.agents.utils.agent_utils", level="INFO") as cm:
            with patch.object(agent_utils, "_fetch_yf_info", side_effect=_never_returns):
                resolve_instrument_identity("NEVER-RETURNS-2")
        messages = "\n".join(cm.output)
        self.assertIn("stage=INSTRUMENT_IDENTITY_START", messages)
        self.assertIn("stage=INSTRUMENT_IDENTITY_TIMEOUT", messages)
        self.assertIn("stage=INSTRUMENT_IDENTITY_END", messages)
        self.assertIn("status=timeout", messages)
        self.assertNotIn("stage=INSTRUMENT_IDENTITY_SUCCESS", messages)


@pytest.mark.unit
class RepeatedTimeoutResourceLeakTests(unittest.TestCase):
    def setUp(self):
        resolve_instrument_identity.cache_clear()
        self._pool = _fresh_pool()
        self._patches = [
            patch.object(agent_utils, "_INSTRUMENT_IDENTITY_TIMEOUT_SECONDS", _TEST_TIMEOUT_SECONDS),
            patch.object(agent_utils, "_INSTRUMENT_IDENTITY_EXECUTOR", self._pool),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def test_multiple_hangs_each_return_promptly_no_growing_thread_pool(self):
        max_workers = self._pool._max_workers
        # Submit fewer hangs than max_workers so a worker remains free for the
        # "later successful lookup" check in the next test.
        hang_count = max(1, max_workers - 1)

        with patch.object(agent_utils, "_fetch_yf_info", side_effect=_never_returns):
            elapsed_times = []
            for i in range(hang_count):
                start = time.monotonic()
                result = resolve_instrument_identity(f"NEVER-RETURNS-REPEAT-{i}")
                elapsed_times.append(time.monotonic() - start)
                self.assertEqual(result, {})

        for elapsed in elapsed_times:
            self.assertLess(elapsed, _TEST_TIMEOUT_SECONDS + 1.0)

        # The pool is a fixed-size singleton -- it never grows past
        # max_workers no matter how many lookups (hung or not) are submitted.
        thread_count = len(self._pool._threads)
        self.assertLessEqual(thread_count, max_workers)

    def test_later_successful_lookup_still_works_after_prior_timeouts(self):
        max_workers = self._pool._max_workers
        hang_count = max(1, max_workers - 1)

        with patch.object(agent_utils, "_fetch_yf_info", side_effect=_never_returns):
            for i in range(hang_count):
                resolve_instrument_identity(f"NEVER-RETURNS-PRIOR-{i}")

        def _fast_success(_ticker):
            return {"longName": "Still Works Inc.", "quoteType": "EQUITY"}

        # Exactly one worker remains free (hang_count == max_workers - 1),
        # so this task is scheduled immediately rather than queued forever.
        with patch.object(agent_utils, "_fetch_yf_info", side_effect=_fast_success):
            start = time.monotonic()
            identity = resolve_instrument_identity("STILL-WORKS-AFTER-TIMEOUTS")
            elapsed = time.monotonic() - start

        self.assertEqual(identity["company_name"], "Still Works Inc.")
        self.assertLess(elapsed, 5.0)

    def test_process_remains_healthy_after_many_timeouts(self):
        # A generous number of sequential timeouts (well beyond max_workers,
        # exercised one at a time so each fully returns before the next is
        # submitted) must not degrade or crash the pool.
        with patch.object(agent_utils, "_fetch_yf_info", side_effect=_never_returns):
            for i in range(10):
                result = resolve_instrument_identity(f"NEVER-RETURNS-HEALTH-{i}")
                self.assertEqual(result, {})
        self.assertFalse(self._pool._shutdown)


@pytest.mark.unit
class SuccessPathParityTests(unittest.TestCase):
    """Old output == new output for the success path -- no semantic change.

    Uses the real, shared, module-level production pool (never swapped out
    here) -- these tests prove the production path itself, not an isolated
    fake pool.
    """

    def setUp(self):
        resolve_instrument_identity.cache_clear()

    def test_full_identity_fields_unchanged(self):
        with patch("tradingagents.agents.utils.agent_utils.yf.Ticker") as mock:
            mock.return_value.info = {
                "longName": "TOTO LTD.",
                "shortName": "TOTO",
                "sector": "Industrials",
                "industry": "Building Products & Equipment",
                "exchange": "PNK",
                "quoteType": "EQUITY",
            }
            identity = resolve_instrument_identity("totdy")
        mock.assert_called_once_with("TOTDY")
        self.assertEqual(
            identity,
            {
                "company_name": "TOTO LTD.",
                "sector": "Industrials",
                "industry": "Building Products & Equipment",
                "exchange": "PNK",
                "quote_type": "EQUITY",
            },
        )

    def test_success_emits_start_and_success_and_end_markers(self):
        with self.assertLogs("tradingagents.agents.utils.agent_utils", level="INFO") as cm:
            with patch("tradingagents.agents.utils.agent_utils.yf.Ticker") as mock:
                mock.return_value.info = {"longName": "Marker Co."}
                resolve_instrument_identity("MARKER-CO")
        messages = "\n".join(cm.output)
        self.assertIn("stage=INSTRUMENT_IDENTITY_START", messages)
        self.assertIn("stage=INSTRUMENT_IDENTITY_SUCCESS", messages)
        self.assertIn("stage=INSTRUMENT_IDENTITY_END", messages)
        self.assertIn("status=success", messages)
        self.assertNotIn("Marker Co.", messages)  # no content leakage


@pytest.mark.unit
class FailurePathTests(unittest.TestCase):
    """Every failure mode preserves the documented fail-open contract.

    Uses the real, shared, module-level production pool -- every fake here
    returns/raises promptly (no infinite hangs), so it never exhausts it.
    """

    def setUp(self):
        resolve_instrument_identity.cache_clear()

    def test_connection_exception_fails_open(self):
        with patch.object(
            agent_utils, "_fetch_yf_info", side_effect=ConnectionError("no route to host")
        ):
            self.assertEqual(resolve_instrument_identity("CONN-ERR"), {})

    def test_http_provider_exception_fails_open(self):
        class _FakeHTTPError(Exception):
            pass

        with patch.object(agent_utils, "_fetch_yf_info", side_effect=_FakeHTTPError("429")):
            self.assertEqual(resolve_instrument_identity("HTTP-ERR"), {})

    def test_malformed_response_fails_open(self):
        # A non-dict return from a pathological fake must still fail open
        # (not raise AttributeError from the identity-extraction code below).
        with patch.object(agent_utils, "_fetch_yf_info", return_value="not-a-dict"):
            self.assertEqual(resolve_instrument_identity("MALFORMED"), {})

    def test_empty_info_fails_open_to_empty_identity(self):
        with patch.object(agent_utils, "_fetch_yf_info", return_value={}):
            self.assertEqual(resolve_instrument_identity("EMPTY-INFO"), {})

    def test_none_info_fails_open_to_empty_identity(self):
        with patch.object(agent_utils, "_fetch_yf_info", return_value=None):
            self.assertEqual(resolve_instrument_identity("NONE-INFO"), {})

    def test_timeout_fails_open(self):
        # Isolated pool + short timeout, same as RealWallClockBoundTests --
        # this test alone submits a never-returning task, so it gets its own
        # throwaway pool rather than the shared production one.
        with patch.object(agent_utils, "_INSTRUMENT_IDENTITY_TIMEOUT_SECONDS", _TEST_TIMEOUT_SECONDS):
            with patch.object(agent_utils, "_INSTRUMENT_IDENTITY_EXECUTOR", _fresh_pool()):
                with patch.object(agent_utils, "_fetch_yf_info", side_effect=_never_returns):
                    self.assertEqual(resolve_instrument_identity("TIMEOUT-FAIL-OPEN"), {})

    def test_unexpected_exception_type_fails_open(self):
        with patch.object(agent_utils, "_fetch_yf_info", side_effect=KeyError("boom")):
            self.assertEqual(resolve_instrument_identity("UNEXPECTED-EXC"), {})

    def test_fail_open_never_becomes_research_failure(self):
        # resolve_instrument_identity itself must never raise -- every
        # documented failure mode returns {} rather than propagating.
        for exc in (
            ConnectionError("x"), TimeoutError("x"), ValueError("x"),
            RuntimeError("x"), OSError("x"),
        ):
            resolve_instrument_identity.cache_clear()
            with patch.object(agent_utils, "_fetch_yf_info", side_effect=exc):
                try:
                    result = resolve_instrument_identity(f"NO-RAISE-{type(exc).__name__}")
                except Exception as raised:  # noqa: BLE001
                    self.fail(f"resolve_instrument_identity raised {raised!r}, must fail open")
                self.assertEqual(result, {})


@pytest.mark.unit
class NonCriticalLookupIntegrationTests(unittest.TestCase):
    """Prove an identity-lookup timeout does not prevent TradingAgents setup
    continuation / STREAM_LOOP_START when the rest of the graph is healthy.
    """

    def setUp(self):
        resolve_instrument_identity.cache_clear()

    def _run(self, tmp_path, caplog_ctx):
        class _FakePropagator:
            def create_initial_state(self, ticker, trade_date, **kwargs):
                return {"company_of_interest": ticker, "trade_date": trade_date}

            def get_graph_args(self):
                return {"stream_mode": "values", "config": {"recursion_limit": 100}}

        class _FakeCompiledGraph:
            def stream(self, init_state, **kwargs):
                yield {
                    "company_of_interest": "QQQ",
                    "market_report": "m",
                    "sentiment_report": "s",
                    "news_report": "n",
                    "fundamentals_report": "f",
                    "investment_debate_state": {"judge_decision": "settled"},
                    "trader_investment_plan": "t",
                    "risk_debate_state": {"judge_decision": "settled"},
                    "final_trade_decision": "decision",
                }

        class _FakeGraph:
            def __init__(self):
                self.propagator = _FakePropagator()
                self.graph = _FakeCompiledGraph()

            def resolve_instrument_context(self, ticker, asset_type):
                # Calls the REAL identity resolver (patched to hang), exactly
                # as tradingagents/graph/trading_graph.py's own
                # resolve_instrument_context does.
                identity = resolve_instrument_identity(ticker)
                return f"instrument-context:{ticker}:{identity}"

        payload = {
            "allow_real_tradingagents_run": True,
            "ticker": "QQQ",
            "analysis_date": "2026-09-14",
            "asset_type": "stock",
            "selected_analysts": ["market", "sentiment", "news", "fundamentals"],
            "config": {"llm_provider": "anthropic", "deep_think_llm": "x", "quick_think_llm": "x"},
            "profile_id": "comqutor_test_profile",
            "run_id": "identity-timeout-integration",
        }
        return run_streaming_tradingagents_research(
            payload, output_root=str(tmp_path), graph_factory=lambda i, c: _FakeGraph(),
        )

    def test_setup_and_stream_loop_proceed_despite_identity_timeout(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_path:
            with patch.object(agent_utils, "_INSTRUMENT_IDENTITY_TIMEOUT_SECONDS", _TEST_TIMEOUT_SECONDS):
                with patch.object(agent_utils, "_INSTRUMENT_IDENTITY_EXECUTOR", _fresh_pool()):
                    with patch.object(agent_utils, "_fetch_yf_info", side_effect=_never_returns):
                        with self.assertLogs(
                            "comqutor_alpha.runners.tradingagents_runner", level="INFO"
                        ) as cm:
                            run_dir = self._run(tmp_path, None)

            messages = "\n".join(cm.output)
            self.assertIn("stage=INSTRUMENT_CONTEXT_START", messages)
            self.assertIn("stage=INSTRUMENT_CONTEXT_END", messages)
            self.assertIn("stage=STREAM_LOOP_START", messages)
            self.assertIn("stage=STREAM_CHUNK", messages)
            self.assertTrue(run_dir.exists())


if __name__ == "__main__":
    unittest.main()
