"""Real, enforced request-count budget for the TradingAgents Research Agent
LLM layer (2026-09-30, fifth follow-up round).

Confirmed empirically before writing this module: raising an exception
inside a LangChain callback handler (``on_chat_model_start`` etc.) does
**not** stop the underlying Provider call -- LangChain catches and logs
callback exceptions, then proceeds with the real request anyway. A
callback-based "budget enforcement" would therefore be a fake guarantee.
The only mechanism that actually prevents a call is intercepting the chat
model's own ``invoke``/``bind_tools().invoke()`` call chain directly, which
this module does via a minimal, in-place class swap -- never a callback,
never a parallel Runnable reimplementation.

Also confirmed empirically: no analyst/researcher/trader/risk-management
node anywhere in ``tradingagents/`` wraps its own LLM ``.invoke()`` call in
a ``try``/``except`` of any kind -- a ``ResearchAgentBudgetExceeded`` raised
from inside the wrapped model therefore propagates all the way up through
LangGraph's own node execution and ``.stream()`` loop uncaught, exactly the
same way any other real Provider exception already does today. This is what
makes "stop before the next request, never swallowed by an upper layer"
achievable here, unlike the semantic Alpha-classification path (see
``t3_diagnostic_evaluation_driver.py``'s own history this round), where the
existing ``_classify_alpha_with_llm`` intentionally catches every exception
around its own gateway call -- a real, different design that this module's
approach was deliberately NOT modeled on for that other call site.
"""

from __future__ import annotations

import threading
from typing import Any


class ResearchAgentBudgetExceeded(Exception):
    """Raised before a real Provider request would exceed the configured budget."""


class RequestBudgetGuard:
    """Thread-safe counter. ``reserve()`` must be called immediately before
    every real attempt (including a retry), never after -- reserving after
    the fact cannot prevent the request that already happened."""

    def __init__(self, max_actual_requests: int) -> None:
        self.max_actual_requests = int(max_actual_requests)
        self._lock = threading.Lock()
        self.actual_requests_made = 0
        self.stop_reason: str | None = None

    def remaining(self) -> int:
        with self._lock:
            return max(self.max_actual_requests - self.actual_requests_made, 0)

    def reserve(self) -> None:
        with self._lock:
            if self.actual_requests_made >= self.max_actual_requests:
                if self.stop_reason is None:
                    self.stop_reason = (
                        f"RequestBudgetGuard: reached max_actual_requests={self.max_actual_requests}"
                    )
                raise ResearchAgentBudgetExceeded(self.stop_reason)
            self.actual_requests_made += 1


def wrap_chat_model_with_budget_guard(chat_model: Any, guard: RequestBudgetGuard, *, max_retries: int = 0) -> Any:
    """Mutates ``chat_model`` IN PLACE via a dynamic ``__class__`` reassignment
    -- never a copy or a newly-constructed instance, so every already-applied
    field (max_tokens, temperature, api_key, ...) survives untouched
    (confirmed directly against a real ``ChatOpenAI``/``ChatAnthropic``-
    subclass instance before this module was written). Works identically
    whether ``chat_model`` is called directly or via
    ``chat_model.bind_tools(tools).invoke(...)`` -- LangChain's own
    ``bind_tools`` returns a binding whose ``.invoke()`` delegates straight
    back to this same instance's own ``.invoke()`` (confirmed empirically),
    so no separate handling is needed for the bound-tools call shape every
    real TradingAgents analyst actually uses.

    Retries happen HERE, at this wrapper's own level, specifically so every
    retry attempt is counted against the SAME guard -- the underlying
    Provider SDK's own internal retry (if the client were left with its
    default ``max_retries``) would be invisible to any wrapper sitting above
    it, which is exactly the "SDK-internal retry cannot be counted" gap a
    purely observational (callback-based) approach cannot close. Whoever
    constructs ``chat_model`` is responsible for having set its own
    ``max_retries=0`` (already the caller's job, not this function's) so
    retries are not attempted twice at two different layers.
    """
    real_cls = type(chat_model)

    def _guarded_invoke(self: Any, *args: Any, **kwargs: Any) -> Any:
        attempt = 0
        last_exc: BaseException | None = None
        while attempt <= max_retries:
            guard.reserve()
            try:
                return real_cls.invoke(self, *args, **kwargs)
            except ResearchAgentBudgetExceeded:
                raise
            except Exception as exc:  # noqa: BLE001 -- deliberately broad: a
                # transient Provider failure is retried up to max_retries,
                # exactly mirroring what an unconfigured client's own
                # internal retry would already have done -- just now visible
                # to and counted by this guard.
                last_exc = exc
                attempt += 1
                continue
        assert last_exc is not None  # loop only exits early via return/raise above
        raise last_exc

    guarded_cls = type(f"BudgetGuarded{real_cls.__name__}", (real_cls,), {"invoke": _guarded_invoke})
    chat_model.__class__ = guarded_cls
    return chat_model
