from __future__ import annotations

import datetime as dt
from copy import deepcopy
from typing import Any

import pytest

from comqutor_alpha.structure_engine.structured_output_shadow_prompt import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
)
from comqutor_alpha.structure_engine.structured_output_shadow_schema import (
    assign_deterministic_claim_ids,
    build_shadow_bundle,
    sha256_text,
)

import comqutor_alpha.data_sanity.pipeline as data_sanity_pipeline


class FakeSemanticInvoker:
    def __init__(self, output: Any = None, *, error: Exception | None = None) -> None:
        self.output = output
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def invoke(self, *, prompt: str, request: dict[str, Any]) -> Any:
        self.calls.append({"prompt": prompt, "request": deepcopy(request)})
        if self.error is not None:
            raise self.error
        return deepcopy(self.output)


def span_for(report: str, quote: str, occurrence: int = 0) -> dict[str, Any]:
    start = -1
    offset = 0
    for _index in range(occurrence + 1):
        start = report.index(quote, offset)
        offset = start + len(quote)
    return {"start": start, "end": start + len(quote), "exact_quote": quote}


def claim_for(
    report: str,
    quote: str,
    *,
    claim: str | None = None,
    spans: list[dict[str, Any]] | None = None,
    evidence: str | None = None,
    candidate_ids: list[str] | None = None,
    entities: list[str] | None = None,
    factors: list[str] | None = None,
    direction: str = "unknown",
    source_type: str = "unknown",
    source_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "shadow_claim_id": "",
        "claim": claim or quote,
        "evidence": evidence or quote,
        "source_spans": spans or [span_for(report, quote)],
        "entities": entities or [],
        "factors": factors or [],
        "direction": direction,
        "confidence": 0.8,
        "source_type": source_type,
        "source_refs": source_refs or [],
        "candidate_segment_ids": candidate_ids or [],
        "extraction_status": "proposed",
    }


def bundle_for(
    report: str,
    *,
    claims: list[dict[str, Any]] | None = None,
    abstentions: list[dict[str, Any]] | None = None,
    run_id: str = "run-shadow-1",
    ticker: str = "NVDA",
    agent: str = "news_agent",
    agent_output_id: str = "run-shadow-1:news_agent:news_report",
) -> dict[str, Any]:
    bundle = build_shadow_bundle(
        run_id=run_id,
        ticker=ticker,
        agent=agent,
        agent_output_id=agent_output_id,
        source_report_sha256=sha256_text(report),
        prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
        prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
        claims=claims or [],
        abstentions=abstentions or [],
    )
    return assign_deterministic_claim_ids(bundle)


@pytest.fixture
def report() -> str:
    return "GPU demand increased in June. Revenue growth remained strong."


def v2_span_for(report: str, quote: str, occurrence: int = 0) -> dict[str, Any]:
    """Provider-facing v2 span: offsets only, no exact_quote (the caller
    reconstructs it -- see structured_output_shadow_v2._normalize_span)."""

    located = span_for(report, quote, occurrence)
    return {"start": located["start"], "end": located["end"]}


def v2_claim(
    *,
    claim: str,
    spans: list[dict[str, Any]],
    entities: list[str] | None = None,
    factors: list[str] | None = None,
    direction: str = "unknown",
    confidence: float = 0.8,
    candidate_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Minimal Provider-facing v2 claim proposal
    (comqutor.structured_claim_shadow_provider_proposal.v2)."""

    payload: dict[str, Any] = {
        "claim": claim,
        "source_spans": spans,
        "entities": entities or [],
        "factors": factors or [],
        "direction": direction,
        "confidence": confidence,
    }
    if candidate_ids is not None:
        payload["candidate_ids"] = candidate_ids
    return payload


def v2_abstention(
    *, reason_code: str = "NO_RELIABLE_CLAIM", notes: str = "", candidate_ids: list[int] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"reason_code": reason_code, "notes": notes}
    if candidate_ids is not None:
        payload["candidate_ids"] = candidate_ids
    return payload


def v2_proposal(
    *, claims: list[dict[str, Any]] | None = None, abstentions: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {"claims": claims or [], "abstentions": abstentions or []}


def v3_claim(
    *,
    claim: str,
    supporting_quotes: list[str],
    entities: list[str] | None = None,
    factors: list[str] | None = None,
    direction: str = "unknown",
    confidence: float = 0.8,
    candidate_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Minimal Provider-facing v3 claim proposal
    (comqutor.structured_claim_shadow_provider_proposal.v3): verbatim
    quotes, never offsets -- the caller resolves each quote deterministically
    (see structured_output_shadow_v3.resolve_supporting_quote)."""

    payload: dict[str, Any] = {
        "claim": claim,
        "supporting_quotes": supporting_quotes,
        "entities": entities or [],
        "factors": factors or [],
        "direction": direction,
        "confidence": confidence,
    }
    if candidate_ids is not None:
        payload["candidate_ids"] = candidate_ids
    return payload


def v3_abstention(
    *, reason_code: str = "NO_RELIABLE_CLAIM", notes: str = "", candidate_ids: list[int] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"reason_code": reason_code, "notes": notes}
    if candidate_ids is not None:
        payload["candidate_ids"] = candidate_ids
    return payload


def v3_proposal(
    *, claims: list[dict[str, Any]] | None = None, abstentions: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {"claims": claims or [], "abstentions": abstentions or []}


def v4_claim(
    *,
    claim: str,
    supporting_quotes: list[str],
    entities: list[str] | None = None,
    factors: list[str] | None = None,
    direction: str = "unknown",
    confidence: float = 0.8,
    candidate_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Minimal Provider-facing v4 claim proposal
    (comqutor.structured_claim_shadow_provider_proposal.v4): byte-identical
    shape to v3's -- only the fixed instruction the model receives differs
    (structured_output_shadow_prompt_v4's FORMATTING RULES section)."""

    payload: dict[str, Any] = {
        "claim": claim,
        "supporting_quotes": supporting_quotes,
        "entities": entities or [],
        "factors": factors or [],
        "direction": direction,
        "confidence": confidence,
    }
    if candidate_ids is not None:
        payload["candidate_ids"] = candidate_ids
    return payload


def v4_abstention(
    *, reason_code: str = "NO_RELIABLE_CLAIM", notes: str = "", candidate_ids: list[int] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"reason_code": reason_code, "notes": notes}
    if candidate_ids is not None:
        payload["candidate_ids"] = candidate_ids
    return payload


def v4_proposal(
    *, claims: list[dict[str, Any]] | None = None, abstentions: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {"claims": claims or [], "abstentions": abstentions or []}


# ---------------------------------------------------------------------------
# Network-leak fix (COMQUTOR Alpha next-round task, 2026-09-26): every test
# under this package that calls comqutor_alpha.api.routes_research.
# run_research_request (test_live_shadow_integration.py) unconditionally
# also runs the Data Sanity Cross-Check sidecar stage
# (comqutor_alpha.data_sanity.pipeline.run_data_sanity_stage --
# comqutor_alpha/api/routes_research.py's own
# ``with contextlib.suppress(Exception): run_data_sanity_stage(run_id,
# output_root)`` call site). When COMQUTOR_DATA_SANITY_ENABLED leaks in from
# a developer's local .env (tests/conftest.py's own load_dotenv side
# effect), that stage's own _run_data_sanity_stage_inner genuinely
# constructs a real YFinanceMarketDataProvider and calls get_history_rows --
# a real HTTPS request to Yahoo Finance (reproduced: a live TCP connection
# to *.ycpi.vip.deb.yahoo.com:https, whose failure/success is then silently
# swallowed by run_data_sanity_stage's own by-design blanket exception
# handling, so the test still passed either way).
#
# Two independent layers below, so a regression here is impossible to miss:
#
#   1. A fixed, deterministic fake provider is injected at the actual
#      external-fetch boundary
#      (comqutor_alpha.data_sanity.pipeline.YFinanceMarketDataProvider) --
#      so even if Data Sanity is genuinely enabled for a test in this
#      package (today it never should be: tests/conftest.py's
#      _isolate_database_env now also strips COMQUTOR_DATA_SANITY_ENABLED),
#      the pipeline exercises its real, already-tested empty-history code
#      path instead of touching a socket.
#   2. An executable network block: any real outbound socket.socket.connect
#      /connect_ex attempted during a test in this package is recorded and
#      raises immediately, and the fixture's own teardown asserts zero
#      attempts were recorded -- so an unexpected outbound connection (Data
#      Sanity, an LLM Provider call, or anything else) fails that test
#      immediately and loudly, never silently degrades to "unavailable" and
#      passes anyway.
# ---------------------------------------------------------------------------


class _FixedEmptyMarketDataProvider:
    """Deterministic stand-in for
    comqutor_alpha.data_sanity.yfinance_provider.YFinanceMarketDataProvider
    -- same public contract (get_history_rows/provider_version), zero
    imports of yfinance, zero network. Returns an empty row list, the same
    legitimate "provider had nothing for this window" outcome
    run_checks/normalize_history_frames already handle (see
    tests/test_data_sanity_yfinance_provider.py)."""

    provider_name = "yfinance-test-fixture"

    def __init__(self, timeout_seconds: int = 15) -> None:
        self.timeout_seconds = timeout_seconds

    def provider_version(self) -> str:
        return "test-fixture-no-network"

    def get_history_rows(self, ticker: str, start_date: dt.date, end_exclusive: dt.date) -> list[dict]:
        return []


@pytest.fixture(autouse=True)
def _fixed_market_data_provider(monkeypatch):
    monkeypatch.setattr(
        data_sanity_pipeline, "YFinanceMarketDataProvider", _FixedEmptyMarketDataProvider
    )


# 2026-09-26 follow-up: the connect-blocking logic itself is now factored
# out into tests/_network_guard.py (shared with this round's new
# tests/test_source_linking_pipeline.py -- "network block must cover every
# test package actually exercised this round, not only this one") --
# OutboundNetworkBlockedError is re-exported here unchanged so existing
# references to this module's own name keep working.
from tests._network_guard import (  # noqa: E402
    OutboundNetworkBlockedError,
    network_guard,
)


@pytest.fixture(autouse=True)
def _block_real_network(network_guard):
    yield network_guard
