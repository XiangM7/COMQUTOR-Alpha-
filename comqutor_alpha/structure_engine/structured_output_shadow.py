"""Offline, non-production Phase 1A Structured Output Shadow parser.

There is intentionally no Provider construction, environment lookup, cache,
network, database, route, replay, or artifact-writing code in this module.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from typing import Any, Protocol, runtime_checkable

from comqutor_alpha.structure_engine.factor_normalizer import FACTOR_ALIASES
from comqutor_alpha.structure_engine.structured_output_adapter import (
    extract_claim_segments_with_audit,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
    build_shadow_prompt_input,
)
from comqutor_alpha.structure_engine.structured_output_shadow_schema import (
    SHADOW_INPUT_SCHEMA_VERSION,
    SHADOW_INVOKER_ERROR,
    SHADOW_JSON_INVALID,
    SHADOW_OUTPUT_TOO_LARGE,
    STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION,
    assign_deterministic_claim_ids,
    build_failure_bundle,
    sha256_text,
    validate_shadow_bundle,
)

CANDIDATE_SEGMENT_SOURCE = (
    "comqutor_alpha.structure_engine.structured_output_adapter."
    "extract_claim_segments_with_audit"
)
CANDIDATE_SEGMENT_CONTRACT_VERSION = "comqutor.shadow_candidate_segment.v1"
DEFAULT_MAX_INPUT_BYTES = 500_000
DEFAULT_MAX_OUTPUT_BYTES = 1_000_000
DEFAULT_MAX_CLAIMS = 128


@runtime_checkable
class SemanticInvoker(Protocol):
    """Injected offline seam; Phase 1A tests use a fake implementation only."""

    def invoke(self, *, prompt: str, request: Mapping[str, Any]) -> Any: ...


def candidate_segment_id(agent_output_id: str, index: int, claim: str) -> str:
    """Return the existing stable, caller-owned candidate identity."""

    material = f"{CANDIDATE_SEGMENT_CONTRACT_VERSION}\n{agent_output_id}\n{index}\n{claim}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"{agent_output_id}:shadow-candidate:{digest[:20]}"


def _locate_exact_hint(report: str, evidence: str, cursor: int) -> tuple[int, int] | None:
    if not evidence:
        return None
    start = report.find(evidence, cursor)
    if start < 0:
        start = report.find(evidence)
    return None if start < 0 else (start, start + len(evidence))


def build_candidate_segments(
    source_report: str, *, agent_output_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Reuse the current public segment API strictly as read-only hints."""

    segments, filtered = extract_claim_segments_with_audit(source_report)
    candidates: list[dict[str, Any]] = []
    cursor = 0
    for index, segment in enumerate(segments):
        claim = str(segment.get("claim") or "")
        evidence = str(segment.get("evidence") or claim)
        located = _locate_exact_hint(source_report, evidence, cursor)
        spans: list[dict[str, Any]] = []
        if located is not None:
            start, end = located
            cursor = end
            spans.append({"start": start, "end": end, "exact_quote": source_report[start:end]})
        candidates.append(
            {
                "candidate_segment_id": candidate_segment_id(agent_output_id, index, claim),
                "candidate_index": index,
                "claim_hint": claim,
                "evidence_hint": evidence,
                "source_section": segment.get("source_section"),
                "source_spans": spans,
                "semantic_authority": False,
            }
        )
    return candidates, [dict(item) for item in filtered]


def _allowed_source_refs(source_metadata: Mapping[str, Any] | None) -> list[str]:
    if not source_metadata:
        return []
    refs: list[str] = []
    raw_refs = source_metadata.get("source_refs")
    if isinstance(raw_refs, list):
        refs.extend(str(value) for value in raw_refs if isinstance(value, str) and value.strip())
    for key in ("source_path", "source_field"):
        value = source_metadata.get(key)
        if isinstance(value, str) and value.strip():
            refs.append(value)
    return list(dict.fromkeys(refs))


def build_shadow_request(
    *,
    source_report: str,
    run_id: str,
    ticker: str,
    agent: str,
    agent_output_id: str,
    candidate_segments: Sequence[Mapping[str, Any]],
    factor_vocabulary: Sequence[str],
    source_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the deterministic request passed to an injected fake/invoker."""

    return {
        "input_schema_version": SHADOW_INPUT_SCHEMA_VERSION,
        "output_schema_version": STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION,
        "run_id": str(run_id),
        "ticker": str(ticker),
        "agent": str(agent),
        "agent_output_id": str(agent_output_id),
        "source_report_sha256": sha256_text(source_report),
        "prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
        "prompt_sha256": STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
        "candidate_segment_contract_version": CANDIDATE_SEGMENT_CONTRACT_VERSION,
        "candidate_segment_source": CANDIDATE_SEGMENT_SOURCE,
        "candidate_segments": [deepcopy(dict(segment)) for segment in candidate_segments],
        "factor_vocabulary": sorted({str(value) for value in factor_vocabulary}),
        "allowed_source_refs": _allowed_source_refs(source_metadata),
        "source_metadata": {
            "source_path": str((source_metadata or {}).get("source_path") or ""),
            "source_field": str((source_metadata or {}).get("source_field") or ""),
        },
        "agent_report_boundary": "BEGIN_UNTRUSTED_AGENT_REPORT",
        "agent_report": source_report,
        "agent_report_end_boundary": "END_UNTRUSTED_AGENT_REPORT",
    }


class StructuredOutputShadowParser:
    """Parse one report behind deterministic validation, entirely offline."""

    def __init__(
        self,
        semantic_invoker: SemanticInvoker | Callable[..., Any],
        *,
        factor_vocabulary: Sequence[str] | None = None,
        prompt_builder: Callable[[Mapping[str, Any]], str] = build_shadow_prompt_input,
        max_claims: int = DEFAULT_MAX_CLAIMS,
        max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    ) -> None:
        if semantic_invoker is None:
            raise ValueError("semantic_invoker is required; Phase 1A never constructs a Provider")
        self.semantic_invoker = semantic_invoker
        self.factor_vocabulary = tuple(factor_vocabulary or FACTOR_ALIASES.keys())
        self.prompt_builder = prompt_builder
        self.max_claims = int(max_claims)
        self.max_input_bytes = int(max_input_bytes)
        self.max_output_bytes = int(max_output_bytes)

    def _failure(
        self,
        *,
        source_report: str,
        run_id: str,
        ticker: str,
        agent: str,
        agent_output_id: str,
        status: str,
        reason_code: str,
        message: str,
    ) -> dict[str, Any]:
        return build_failure_bundle(
            run_id=run_id,
            ticker=ticker,
            agent=agent,
            agent_output_id=agent_output_id,
            source_report_sha256=sha256_text(source_report),
            prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
            prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
            status=status,
            reason_code=reason_code,
            message=message,
        )

    def _invoke(self, *, prompt: str, request: Mapping[str, Any]) -> Any:
        invoker = self.semantic_invoker
        method = getattr(invoker, "invoke", None)
        if callable(method):
            return method(prompt=prompt, request=request)
        if callable(invoker):
            return invoker(prompt=prompt, request=request)
        raise TypeError("semantic_invoker must be callable or implement invoke")

    def parse_report_shadow(
        self,
        *,
        source_report: str,
        run_id: str,
        ticker: str,
        agent: str,
        agent_output_id: str,
        source_metadata: Mapping[str, Any] | None = None,
        candidate_segments: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(source_report, str):
            return self._failure(
                source_report=str(source_report or ""),
                run_id=run_id,
                ticker=ticker,
                agent=agent,
                agent_output_id=agent_output_id,
                status="validation_rejected",
                reason_code=SHADOW_JSON_INVALID,
                message="source_report must be a string",
            )
        if len(source_report.encode("utf-8")) > self.max_input_bytes:
            return self._failure(
                source_report=source_report,
                run_id=run_id,
                ticker=ticker,
                agent=agent,
                agent_output_id=agent_output_id,
                status="input_too_large",
                reason_code=SHADOW_OUTPUT_TOO_LARGE,
                message="source report exceeds the configured offline input limit",
            )

        if candidate_segments is None:
            candidates, _filtered = build_candidate_segments(
                source_report, agent_output_id=agent_output_id
            )
        else:
            candidates = [deepcopy(dict(segment)) for segment in candidate_segments]
        request = build_shadow_request(
            source_report=source_report,
            run_id=run_id,
            ticker=ticker,
            agent=agent,
            agent_output_id=agent_output_id,
            candidate_segments=candidates,
            factor_vocabulary=self.factor_vocabulary,
            source_metadata=source_metadata,
        )
        prompt = self.prompt_builder(request)
        try:
            raw_output = self._invoke(prompt=prompt, request=request)
        except Exception as exc:  # fake timeout/error is deliberately fail-soft
            return self._failure(
                source_report=source_report,
                run_id=run_id,
                ticker=ticker,
                agent=agent,
                agent_output_id=agent_output_id,
                status="parser_error",
                reason_code=SHADOW_INVOKER_ERROR,
                message=f"injected semantic invoker failed: {type(exc).__name__}",
            )

        if isinstance(raw_output, (bytes, bytearray)):
            try:
                raw_output = bytes(raw_output).decode("utf-8")
            except UnicodeDecodeError:
                raw_output = None
        if isinstance(raw_output, str):
            if len(raw_output.encode("utf-8")) > self.max_output_bytes:
                return self._failure(
                    source_report=source_report,
                    run_id=run_id,
                    ticker=ticker,
                    agent=agent,
                    agent_output_id=agent_output_id,
                    status="validation_rejected",
                    reason_code=SHADOW_OUTPUT_TOO_LARGE,
                    message="semantic proposal exceeds the configured output limit",
                )
            try:
                proposal = json.loads(raw_output)
            except json.JSONDecodeError:
                proposal = None
        else:
            proposal = deepcopy(raw_output)
        if not isinstance(proposal, Mapping):
            return self._failure(
                source_report=source_report,
                run_id=run_id,
                ticker=ticker,
                agent=agent,
                agent_output_id=agent_output_id,
                status="parser_error",
                reason_code=SHADOW_JSON_INVALID,
                message="semantic proposal is not a strict JSON object",
            )

        proposal_with_ids = assign_deterministic_claim_ids(proposal)
        validation = validate_shadow_bundle(
            proposal_with_ids,
            source_report=source_report,
            run_id=run_id,
            ticker=ticker,
            agent=agent,
            agent_output_id=agent_output_id,
            prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
            prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
            factor_vocabulary=self.factor_vocabulary,
            allowed_source_refs=request["allowed_source_refs"],
            allowed_candidate_segment_ids=[
                str(segment.get("candidate_segment_id") or "") for segment in candidates
            ],
            max_claims=self.max_claims,
            max_output_bytes=self.max_output_bytes,
        )
        if not validation.valid:
            first_code = validation.reason_codes[0] if validation.reason_codes else SHADOW_JSON_INVALID
            failure = self._failure(
                source_report=source_report,
                run_id=run_id,
                ticker=ticker,
                agent=agent,
                agent_output_id=agent_output_id,
                status="validation_rejected",
                reason_code=first_code,
                message="semantic proposal rejected by deterministic validation",
            )
            failure["validation_summary"] = validation.to_summary()
            return failure

        accepted = deepcopy(dict(proposal_with_ids))
        accepted["validation_summary"] = validation.to_summary()
        # These are caller-owned invariants even after validation.
        accepted["shadow_only"] = True
        accepted["production_authority"] = False
        return accepted


def parse_report_shadow(
    *,
    semantic_invoker: SemanticInvoker | Callable[..., Any],
    source_report: str,
    run_id: str,
    ticker: str,
    agent: str,
    agent_output_id: str,
    factor_vocabulary: Sequence[str] | None = None,
    source_metadata: Mapping[str, Any] | None = None,
    candidate_segments: Sequence[Mapping[str, Any]] | None = None,
    max_claims: int = DEFAULT_MAX_CLAIMS,
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
) -> dict[str, Any]:
    parser = StructuredOutputShadowParser(
        semantic_invoker,
        factor_vocabulary=factor_vocabulary,
        max_claims=max_claims,
        max_input_bytes=max_input_bytes,
        max_output_bytes=max_output_bytes,
    )
    return parser.parse_report_shadow(
        source_report=source_report,
        run_id=run_id,
        ticker=ticker,
        agent=agent,
        agent_output_id=agent_output_id,
        source_metadata=source_metadata,
        candidate_segments=candidate_segments,
    )


__all__ = [
    "CANDIDATE_SEGMENT_CONTRACT_VERSION",
    "CANDIDATE_SEGMENT_SOURCE",
    "SemanticInvoker",
    "StructuredOutputShadowParser",
    "build_candidate_segments",
    "build_shadow_request",
    "candidate_segment_id",
    "parse_report_shadow",
]
