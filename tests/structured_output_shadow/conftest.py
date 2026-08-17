from __future__ import annotations

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

