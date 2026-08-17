"""Phase 1 Master prompt-size fix: additive v2 minimal-request path for the
offline Structured Output Shadow parser.

This module never replaces or modifies ``structured_output_shadow.py`` /
``structured_output_shadow_schema.py`` / ``structured_output_adapter.py``. It
reuses, unchanged:

- the candidate-segment source (``build_candidate_segments`` ->
  ``extract_claim_segments_with_audit``),
- the canonical bundle schema (``comqutor.structured_claim_shadow.v1``), and
- the sole deterministic admission authority (``validate_shadow_bundle``).

What v2 changes is only what crosses the wire to the Provider and back: the
Provider is asked for a strictly smaller proposal shape (claim,
``source_spans{start,end}``, entities, factors, direction, confidence,
optional candidate lineage), and every field the deterministic layer already
independently owns and verifies -- identity, hashes, stable Claim IDs,
``exact_quote``, ``evidence`` text, ``shadow_only``, ``production_authority``
-- is spliced in by :func:`normalize_v2_proposal_to_canonical_bundle` before
the unchanged validator ever sees it. See
``docs/audit_artifacts/phase1_master/prompt_audit/`` for the measured
root-cause audit and ``llm_vs_deterministic_responsibility_matrix.md`` for the
justification behind every field kept, dropped, or moved.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from typing import Any

from comqutor_alpha.structure_engine.structured_output_shadow import (
    SemanticInvoker,
    build_candidate_segments,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v2 import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2,
    build_shadow_prompt_input_v2,
)
from comqutor_alpha.structure_engine.structured_output_shadow_schema import (
    SHADOW_INVOKER_ERROR,
    SHADOW_JSON_INVALID,
    SHADOW_OUTPUT_TOO_LARGE,
    STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION,
    assign_deterministic_claim_ids,
    build_failure_bundle,
    sha256_text,
    validate_shadow_bundle,
)

SHADOW_INPUT_SCHEMA_VERSION_V2 = "comqutor.structured_claim_shadow_input.v2"
SHADOW_PROVIDER_PROPOSAL_SCHEMA_VERSION_V2 = "comqutor.structured_claim_shadow_provider_proposal.v2"

DEFAULT_MAX_CLAIMS = 128
DEFAULT_MAX_INPUT_BYTES = 500_000
DEFAULT_MAX_OUTPUT_BYTES = 1_000_000


def _valid_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def select_located_candidate_hints(
    candidate_segments: Sequence[Mapping[str, Any]],
) -> list[dict[str, int]]:
    """Compact, offset-only hints for the subset of candidates that have a
    verified, exact, locatable source span (typically a minority -- 21/163
    for the frozen NVDA fundamental Smoke report; see
    ``v1_root_cause_report.md``, "Second-worst finding"). A candidate with no
    verified location contributes nothing to the wire payload; the model
    still has the one full copy of the report to find it in."""

    hints: list[dict[str, int]] = []
    for segment in candidate_segments:
        spans = segment.get("source_spans") or []
        if not spans:
            continue
        span = spans[0]
        start, end = span.get("start"), span.get("end")
        if isinstance(start, int) and not isinstance(start, bool) and isinstance(end, int) and not isinstance(end, bool):
            hints.append({"id": int(segment["candidate_index"]), "start": start, "end": end})
    return hints


def build_shadow_request_v2(
    *,
    source_report: str,
    run_id: str,
    ticker: str,
    agent: str,
    agent_output_id: str,
    candidate_segments: Sequence[Mapping[str, Any]],
    factor_vocabulary: Sequence[str],
) -> dict[str, Any]:
    """Build the minimal v2 wire request. Deliberately excludes every field
    the deterministic normalizer/validator layer already owns or never
    needed from the model in the first place: hashes, prompt identity,
    candidate contract bookkeeping/full IDs/text/section/authority-flag, and
    ``allowed_source_refs`` (v2's Provider-facing claim shape carries no
    ``source_refs`` field -- see the responsibility matrix)."""

    return {
        "input_schema_version": SHADOW_INPUT_SCHEMA_VERSION_V2,
        "run_id": str(run_id),
        "ticker": str(ticker),
        "agent": str(agent),
        "agent_output_id": str(agent_output_id),
        "factor_vocabulary": sorted({str(value) for value in factor_vocabulary}),
        "candidate_hints": select_located_candidate_hints(candidate_segments),
        "agent_report_boundary": "BEGIN_UNTRUSTED_AGENT_REPORT",
        "agent_report": source_report,
        "agent_report_end_boundary": "END_UNTRUSTED_AGENT_REPORT",
    }


def _normalize_span(report: str, raw_span: Any) -> dict[str, Any]:
    """Pass raw ``start``/``end`` straight through untouched -- never
    repaired, never fuzzy-matched. ``validate_shadow_bundle`` remains the
    sole authority that rejects invalid offsets (negative, inverted,
    out-of-range, or wrong type). ``exact_quote`` is computed only when both
    offsets are plain ints so a malformed type can never raise here; the
    validator's own type check then rejects it on the same grounds a
    malformed v1 proposal would have been rejected."""

    if not isinstance(raw_span, Mapping):
        return {"start": None, "end": None, "exact_quote": ""}
    start, end = raw_span.get("start"), raw_span.get("end")
    quote = ""
    if isinstance(start, int) and not isinstance(start, bool) and isinstance(end, int) and not isinstance(end, bool):
        try:
            quote = report[start:end]
        except (TypeError, ValueError):
            quote = ""
    return {"start": start, "end": end, "exact_quote": quote}


def _reconstruct_evidence(spans: Sequence[Mapping[str, Any]]) -> str:
    """One of validate_shadow_bundle._evidence_is_provenanced's own accepted
    bounded combinations: the single quote when there is one span, else the
    space-joined concatenation of every span's exact_quote, in order."""

    quotes = [str(span.get("exact_quote") or "") for span in spans]
    if len(quotes) == 1:
        return quotes[0]
    return " ".join(quotes)


def normalize_v2_proposal_to_canonical_bundle(
    proposal: Mapping[str, Any],
    *,
    source_report: str,
    run_id: str,
    ticker: str,
    agent: str,
    agent_output_id: str,
    candidate_index_to_id: Mapping[int, str],
) -> dict[str, Any]:
    """Upgrade a minimal v2 Provider proposal into the exact, UNCHANGED
    ``comqutor.structured_claim_shadow.v1`` bundle shape.
    ``assign_deterministic_claim_ids``/``validate_shadow_bundle`` are never
    modified or duplicated here -- this function only fills in, from
    caller-owned inputs (never from the proposal), every field the Provider
    used to be asked to copy: identity, source hash, ``exact_quote``,
    ``evidence``, ``shadow_claim_id`` (always ``""`` -- ignored downstream
    exactly as v1's is), ``source_type``/``source_refs`` defaults,
    ``shadow_only``, ``production_authority``.

    Never raises on malformed input: any wrong-shaped nested value (a
    non-mapping claim, a non-list ``source_spans``) degrades to an
    empty/placeholder value that the unchanged validator then rejects on its
    own terms -- exactly as a malformed v1 proposal would be rejected, not a
    new failure mode.
    """

    raw_claims = proposal.get("claims")
    raw_abstentions = proposal.get("abstentions")

    def _resolve_candidate_ids(raw: Any) -> list[str]:
        if not isinstance(raw, list):
            return []
        return [
            candidate_index_to_id[value]
            for value in raw
            if isinstance(value, int) and not isinstance(value, bool) and value in candidate_index_to_id
        ]

    claims: list[dict[str, Any]] = []
    if isinstance(raw_claims, list):
        for raw_claim in raw_claims:
            if not isinstance(raw_claim, Mapping):
                continue
            raw_spans = raw_claim.get("source_spans")
            spans = (
                [_normalize_span(source_report, span) for span in raw_spans]
                if isinstance(raw_spans, list)
                else []
            )
            claims.append(
                {
                    "shadow_claim_id": "",
                    "claim": raw_claim.get("claim") if isinstance(raw_claim.get("claim"), str) else "",
                    "evidence": _reconstruct_evidence(spans),
                    "source_spans": spans,
                    "entities": (
                        raw_claim.get("entities") if _valid_string_list(raw_claim.get("entities")) else []
                    ),
                    "factors": (
                        raw_claim.get("factors") if _valid_string_list(raw_claim.get("factors")) else []
                    ),
                    "direction": raw_claim.get("direction"),
                    "confidence": raw_claim.get("confidence"),
                    "source_type": "unknown",
                    "source_refs": [],
                    "candidate_segment_ids": _resolve_candidate_ids(raw_claim.get("candidate_ids")),
                    "extraction_status": "proposed",
                }
            )

    abstentions: list[dict[str, Any]] = []
    if isinstance(raw_abstentions, list):
        for raw_abstention in raw_abstentions:
            if not isinstance(raw_abstention, Mapping):
                continue
            abstentions.append(
                {
                    "candidate_segment_ids": _resolve_candidate_ids(raw_abstention.get("candidate_ids")),
                    "reason_code": (
                        raw_abstention.get("reason_code")
                        if isinstance(raw_abstention.get("reason_code"), str)
                        else ""
                    ),
                    "notes": (
                        raw_abstention.get("notes") if isinstance(raw_abstention.get("notes"), str) else ""
                    ),
                }
            )

    return {
        "schema_version": STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION,
        "run_id": str(run_id),
        "ticker": str(ticker),
        "agent": str(agent),
        "agent_output_id": str(agent_output_id),
        "source_report_sha256": sha256_text(source_report),
        "prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2,
        "prompt_sha256": STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256,
        "claims": claims,
        "abstentions": abstentions,
        "validation_summary": {},
        "shadow_only": True,
        "production_authority": False,
    }


class StructuredOutputShadowParserV2:
    """v2 sibling of ``StructuredOutputShadowParser``: identical offline,
    fail-soft, validator-is-sole-authority design; only the wire request and
    the Provider-facing response shape are smaller. See module docstring."""

    def __init__(
        self,
        semantic_invoker: SemanticInvoker | Callable[..., Any],
        *,
        factor_vocabulary: Sequence[str] | None = None,
        prompt_builder: Callable[[Mapping[str, Any]], str] = build_shadow_prompt_input_v2,
        max_claims: int = DEFAULT_MAX_CLAIMS,
        max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    ) -> None:
        if semantic_invoker is None:
            raise ValueError("semantic_invoker is required; v2 never constructs a Provider")
        self.semantic_invoker = semantic_invoker
        if factor_vocabulary is None:
            from comqutor_alpha.structure_engine.factor_normalizer import FACTOR_ALIASES

            factor_vocabulary = tuple(FACTOR_ALIASES.keys())
        self.factor_vocabulary = tuple(factor_vocabulary)
        self.prompt_builder = prompt_builder
        self.max_claims = int(max_claims)
        self.max_input_bytes = int(max_input_bytes)
        self.max_output_bytes = int(max_output_bytes)

    def _invoke(self, *, prompt: str, request: Mapping[str, Any]) -> Any:
        invoker = self.semantic_invoker
        method = getattr(invoker, "invoke", None)
        if callable(method):
            return method(prompt=prompt, request=request)
        if callable(invoker):
            return invoker(prompt=prompt, request=request)
        raise TypeError("semantic_invoker must be callable or implement invoke")

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
            prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2,
            prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256,
            status=status,
            reason_code=reason_code,
            message=message,
        )

    def parse_report_shadow_v2(
        self,
        *,
        source_report: str,
        run_id: str,
        ticker: str,
        agent: str,
        agent_output_id: str,
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
            candidates, _filtered = build_candidate_segments(source_report, agent_output_id=agent_output_id)
        else:
            candidates = [deepcopy(dict(segment)) for segment in candidate_segments]
        candidate_index_to_id = {
            int(segment["candidate_index"]): str(segment["candidate_segment_id"]) for segment in candidates
        }

        request = build_shadow_request_v2(
            source_report=source_report,
            run_id=run_id,
            ticker=ticker,
            agent=agent,
            agent_output_id=agent_output_id,
            candidate_segments=candidates,
            factor_vocabulary=self.factor_vocabulary,
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

        try:
            canonical = normalize_v2_proposal_to_canonical_bundle(
                proposal,
                source_report=source_report,
                run_id=run_id,
                ticker=ticker,
                agent=agent,
                agent_output_id=agent_output_id,
                candidate_index_to_id=candidate_index_to_id,
            )
        except Exception as exc:
            return self._failure(
                source_report=source_report,
                run_id=run_id,
                ticker=ticker,
                agent=agent,
                agent_output_id=agent_output_id,
                status="parser_error",
                reason_code=SHADOW_JSON_INVALID,
                message=f"v2 proposal normalization failed: {type(exc).__name__}",
            )

        proposal_with_ids = assign_deterministic_claim_ids(canonical)
        validation = validate_shadow_bundle(
            proposal_with_ids,
            source_report=source_report,
            run_id=run_id,
            ticker=ticker,
            agent=agent,
            agent_output_id=agent_output_id,
            prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2,
            prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256,
            factor_vocabulary=self.factor_vocabulary,
            allowed_source_refs=(),
            allowed_candidate_segment_ids=[str(segment["candidate_segment_id"]) for segment in candidates],
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
        accepted["shadow_only"] = True
        accepted["production_authority"] = False
        return accepted


def parse_report_shadow_v2(
    *,
    semantic_invoker: SemanticInvoker | Callable[..., Any],
    source_report: str,
    run_id: str,
    ticker: str,
    agent: str,
    agent_output_id: str,
    factor_vocabulary: Sequence[str] | None = None,
    candidate_segments: Sequence[Mapping[str, Any]] | None = None,
    max_claims: int = DEFAULT_MAX_CLAIMS,
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
) -> dict[str, Any]:
    parser = StructuredOutputShadowParserV2(
        semantic_invoker,
        factor_vocabulary=factor_vocabulary,
        max_claims=max_claims,
        max_input_bytes=max_input_bytes,
        max_output_bytes=max_output_bytes,
    )
    return parser.parse_report_shadow_v2(
        source_report=source_report,
        run_id=run_id,
        ticker=ticker,
        agent=agent,
        agent_output_id=agent_output_id,
        candidate_segments=candidate_segments,
    )


__all__ = [
    "DEFAULT_MAX_CLAIMS",
    "DEFAULT_MAX_INPUT_BYTES",
    "DEFAULT_MAX_OUTPUT_BYTES",
    "SHADOW_INPUT_SCHEMA_VERSION_V2",
    "SHADOW_PROVIDER_PROPOSAL_SCHEMA_VERSION_V2",
    "StructuredOutputShadowParserV2",
    "build_shadow_request_v2",
    "normalize_v2_proposal_to_canonical_bundle",
    "parse_report_shadow_v2",
    "select_located_candidate_hints",
]
