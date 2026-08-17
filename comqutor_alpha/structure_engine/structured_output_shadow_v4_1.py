"""v4.1 deterministic candidate binding and rejected-output forensics.

This additive protocol keeps v4 semantic extraction rules unchanged. It adds
only caller-owned candidate identity to each evidence quote and never accepts
Provider-created offsets, fuzzy matches, semantic disambiguation, or a first-
match fallback.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from comqutor_alpha.structure_engine.structured_output_shadow import (
    SemanticInvoker,
    build_candidate_segments,
    candidate_segment_id,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v4_1 import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_1,
    build_shadow_prompt_input_v4_1,
)
from comqutor_alpha.structure_engine.structured_output_shadow_schema import (
    SHADOW_INVOKER_ERROR,
    SHADOW_JSON_INVALID,
    SHADOW_OUTPUT_TOO_LARGE,
    SHADOW_UNAPPROVED_FIELD,
    STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION,
    assign_deterministic_claim_ids,
    build_failure_bundle,
    sha256_text,
    validate_shadow_bundle,
)

SHADOW_INPUT_SCHEMA_VERSION_V4_1 = "comqutor.structured_claim_shadow_input.v4.1"
SHADOW_PROVIDER_PROPOSAL_SCHEMA_VERSION_V4_1 = (
    "comqutor.structured_claim_shadow_provider_proposal.v4.1"
)
REJECTED_FORENSIC_SCHEMA_VERSION = "comqutor.structured_claim_shadow_rejected_forensic.v1"

DEFAULT_MAX_CLAIMS = 128
DEFAULT_MAX_INPUT_BYTES = 500_000
DEFAULT_MAX_OUTPUT_BYTES = 1_000_000

RESOLUTION_UNIQUE_EXACT_MATCH = "UNIQUE_EXACT_MATCH"
RESOLUTION_DISAMBIGUATED_VIA_CANDIDATE = "DISAMBIGUATED_VIA_CANDIDATE_BINDING"
RESOLUTION_NO_EXACT_MATCH = "NO_EXACT_MATCH"
RESOLUTION_CANDIDATE_REQUIRED = "AMBIGUOUS_CANDIDATE_REQUIRED"
RESOLUTION_CANDIDATE_UNKNOWN = "CANDIDATE_ID_UNKNOWN"
RESOLUTION_CANDIDATE_SOURCE_MISMATCH = "CANDIDATE_SOURCE_IDENTITY_MISMATCH"
RESOLUTION_CANDIDATE_LOCAL_ZERO = "CANDIDATE_LOCAL_NO_EXACT_MATCH"
RESOLUTION_CANDIDATE_LOCAL_MULTIPLE = "CANDIDATE_LOCAL_MULTIPLE_MATCHES"
RESOLUTION_INVALID_EVIDENCE = "INVALID_SUPPORTING_EVIDENCE"

RESOLUTION_STATUSES_LOCATED = frozenset(
    {RESOLUTION_UNIQUE_EXACT_MATCH, RESOLUTION_DISAMBIGUATED_VIA_CANDIDATE}
)


def _sha256_canonical_json(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return sha256_text(payload)


def _find_all_occurrences(report: str, quote: str) -> list[int]:
    if not quote:
        return []
    positions: list[int] = []
    cursor = 0
    while True:
        position = report.find(quote, cursor)
        if position < 0:
            return positions
        positions.append(position)
        cursor = position + 1


def build_candidate_manifest_v4_1(
    *,
    source_report: str,
    run_id: str,
    ticker: str,
    agent: str,
    agent_output_id: str,
    candidate_segments: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Build the only candidate identities the Provider may select.

    Malformed, wrong-agent, non-exact, or multi-span candidates are excluded,
    so returning one of their IDs later is deterministically unknown/rejected.
    """

    source_hash = sha256_text(source_report)
    manifest: list[dict[str, Any]] = []
    seen: set[str] = set()
    for segment in candidate_segments:
        index = segment.get("candidate_index")
        claim_hint = segment.get("claim_hint")
        supplied_id = segment.get("candidate_segment_id")
        spans = segment.get("source_spans")
        if (
            not isinstance(index, int)
            or isinstance(index, bool)
            or not isinstance(claim_hint, str)
            or not isinstance(supplied_id, str)
            or supplied_id != candidate_segment_id(agent_output_id, index, claim_hint)
            or not isinstance(spans, list)
            or len(spans) != 1
        ):
            continue
        span = spans[0]
        if not isinstance(span, Mapping):
            continue
        start, end, exact_quote = span.get("start"), span.get("end"), span.get("exact_quote")
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or not (0 <= start < end <= len(source_report))
            or not isinstance(exact_quote, str)
            or source_report[start:end] != exact_quote
            or supplied_id in seen
        ):
            continue
        seen.add(supplied_id)
        manifest.append(
            {
                "candidate_id": supplied_id,
                "run_id": str(run_id),
                "ticker": str(ticker),
                "agent": str(agent),
                "agent_output_id": str(agent_output_id),
                "source_report_sha256": source_hash,
                "source_start": start,
                "source_end": end,
                "candidate_text_sha256": sha256_text(exact_quote),
            }
        )
    return manifest


def build_shadow_request_v4_1(
    *,
    source_report: str,
    run_id: str,
    ticker: str,
    agent: str,
    agent_output_id: str,
    candidate_manifest: Sequence[Mapping[str, Any]],
    factor_vocabulary: Sequence[str],
) -> dict[str, Any]:
    return {
        "input_schema_version": SHADOW_INPUT_SCHEMA_VERSION_V4_1,
        "run_id": str(run_id),
        "ticker": str(ticker),
        "agent": str(agent),
        "agent_output_id": str(agent_output_id),
        "source_report_sha256": sha256_text(source_report),
        "factor_vocabulary": sorted({str(value) for value in factor_vocabulary}),
        "candidate_hints": [deepcopy(dict(item)) for item in candidate_manifest],
        "agent_report_boundary": "BEGIN_UNTRUSTED_AGENT_REPORT",
        "agent_report": source_report,
        "agent_report_end_boundary": "END_UNTRUSTED_AGENT_REPORT",
    }


@dataclass(frozen=True)
class ResolvedEvidenceV4_1:
    quote: str
    status: str
    global_offsets: tuple[int, ...]
    selected_candidate_id: str | None
    candidate_source_start: int | None
    candidate_source_end: int | None
    candidate_local_offsets: tuple[int, ...]
    resolved_start: int | None
    resolved_end: int | None
    rejection_reason: str | None

    @property
    def located(self) -> bool:
        return self.status in RESOLUTION_STATUSES_LOCATED

    def to_diagnostic(
        self,
        *,
        claim_index: int,
        evidence_index: int,
        source_report_sha256: str,
    ) -> dict[str, Any]:
        return {
            "claim_index": claim_index,
            "evidence_index": evidence_index,
            "quote": self.quote,
            "quote_sha256": sha256_text(self.quote),
            "global_exact_match_count": len(self.global_offsets),
            "global_exact_match_offsets": list(self.global_offsets),
            "selected_candidate_id": self.selected_candidate_id,
            "candidate_source_start": self.candidate_source_start,
            "candidate_source_end": self.candidate_source_end,
            "candidate_local_match_count": len(self.candidate_local_offsets),
            "candidate_local_match_offsets": list(self.candidate_local_offsets),
            "resolution_status": self.status,
            "rejection_reason": self.rejection_reason,
            "source_report_sha256": source_report_sha256,
        }


def resolve_supporting_evidence_v4_1(
    *,
    report: str,
    evidence: Any,
    candidate_manifest: Mapping[str, Mapping[str, Any]],
    source_report_sha256: str,
    run_id: str,
    ticker: str,
    agent: str,
    agent_output_id: str,
) -> ResolvedEvidenceV4_1:
    """Resolve one quote with exact global matching and strict local binding."""

    if not isinstance(evidence, Mapping):
        return ResolvedEvidenceV4_1(
            "", RESOLUTION_INVALID_EVIDENCE, (), None, None, None, (), None, None,
            "SHADOW_SUPPORTING_EVIDENCE_INVALID",
        )
    quote = evidence.get("quote")
    selected = evidence.get("candidate_id")
    if not isinstance(quote, str) or not quote or not (
        selected is None or isinstance(selected, str)
    ):
        return ResolvedEvidenceV4_1(
            quote if isinstance(quote, str) else "",
            RESOLUTION_INVALID_EVIDENCE,
            (),
            selected if isinstance(selected, str) else None,
            None,
            None,
            (),
            None,
            None,
            "SHADOW_SUPPORTING_EVIDENCE_INVALID",
        )

    global_offsets = tuple(_find_all_occurrences(report, quote))
    if not global_offsets:
        return ResolvedEvidenceV4_1(
            quote, RESOLUTION_NO_EXACT_MATCH, (), selected, None, None, (), None, None,
            "SHADOW_QUOTE_NOT_EXACT",
        )

    candidate_start = None
    candidate_end = None
    local_offsets: tuple[int, ...] = ()
    if selected is not None:
        candidate = candidate_manifest.get(selected)
        if candidate is None:
            return ResolvedEvidenceV4_1(
                quote, RESOLUTION_CANDIDATE_UNKNOWN, global_offsets, selected, None, None, (),
                None, None, "SHADOW_CANDIDATE_ID_UNKNOWN",
            )
        expected_identity = {
            "run_id": str(run_id),
            "ticker": str(ticker),
            "agent": str(agent),
            "agent_output_id": str(agent_output_id),
            "source_report_sha256": source_report_sha256,
        }
        if any(candidate.get(key) != value for key, value in expected_identity.items()):
            return ResolvedEvidenceV4_1(
                quote, RESOLUTION_CANDIDATE_SOURCE_MISMATCH, global_offsets, selected, None, None,
                (), None, None, "SHADOW_CANDIDATE_SOURCE_IDENTITY_MISMATCH",
            )
        candidate_start = candidate.get("source_start")
        candidate_end = candidate.get("source_end")
        if (
            not isinstance(candidate_start, int)
            or isinstance(candidate_start, bool)
            or not isinstance(candidate_end, int)
            or isinstance(candidate_end, bool)
            or not (0 <= candidate_start < candidate_end <= len(report))
            or candidate.get("candidate_text_sha256")
            != sha256_text(report[candidate_start:candidate_end])
        ):
            return ResolvedEvidenceV4_1(
                quote, RESOLUTION_CANDIDATE_SOURCE_MISMATCH, global_offsets, selected, None, None,
                (), None, None, "SHADOW_CANDIDATE_SOURCE_IDENTITY_MISMATCH",
            )
        local_offsets = tuple(
            offset
            for offset in global_offsets
            if candidate_start <= offset and offset + len(quote) <= candidate_end
        )

    if len(global_offsets) == 1:
        if selected is None:
            start = global_offsets[0]
            return ResolvedEvidenceV4_1(
                quote, RESOLUTION_UNIQUE_EXACT_MATCH, global_offsets, None, None, None, (),
                start, start + len(quote), None,
            )
        if len(local_offsets) == 1:
            start = local_offsets[0]
            return ResolvedEvidenceV4_1(
                quote, RESOLUTION_UNIQUE_EXACT_MATCH, global_offsets, selected, candidate_start,
                candidate_end, local_offsets, start, start + len(quote), None,
            )
        status = RESOLUTION_CANDIDATE_LOCAL_ZERO if not local_offsets else RESOLUTION_CANDIDATE_LOCAL_MULTIPLE
        return ResolvedEvidenceV4_1(
            quote, status, global_offsets, selected, candidate_start, candidate_end, local_offsets,
            None, None, "SHADOW_CANDIDATE_LOCAL_MATCH_COUNT_INVALID",
        )

    if selected is None:
        return ResolvedEvidenceV4_1(
            quote, RESOLUTION_CANDIDATE_REQUIRED, global_offsets, None, None, None, (), None, None,
            "SHADOW_DUPLICATE_QUOTE_CANDIDATE_REQUIRED",
        )
    if len(local_offsets) == 1:
        start = local_offsets[0]
        return ResolvedEvidenceV4_1(
            quote, RESOLUTION_DISAMBIGUATED_VIA_CANDIDATE, global_offsets, selected,
            candidate_start, candidate_end, local_offsets, start, start + len(quote), None,
        )
    status = RESOLUTION_CANDIDATE_LOCAL_ZERO if not local_offsets else RESOLUTION_CANDIDATE_LOCAL_MULTIPLE
    return ResolvedEvidenceV4_1(
        quote, status, global_offsets, selected, candidate_start, candidate_end, local_offsets,
        None, None, "SHADOW_CANDIDATE_LOCAL_MATCH_COUNT_INVALID",
    )


def _bounded_string_list(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _bounded_candidate_payload_v4_1(
    proposal: Mapping[str, Any], *, preserve_abstention_notes: bool
) -> dict[str, Any]:

    claims: list[dict[str, Any]] = []
    for raw_claim in proposal.get("claims") or []:
        if not isinstance(raw_claim, Mapping):
            continue
        evidence_items = []
        for raw_evidence in raw_claim.get("supporting_evidence") or []:
            if isinstance(raw_evidence, Mapping):
                evidence_items.append(
                    {
                        "quote": raw_evidence.get("quote")
                        if isinstance(raw_evidence.get("quote"), str)
                        else "",
                        "candidate_id": raw_evidence.get("candidate_id")
                        if isinstance(raw_evidence.get("candidate_id"), str)
                        else None,
                    }
                )
        confidence = raw_claim.get("confidence")
        claims.append(
            {
                "claim": raw_claim.get("claim") if isinstance(raw_claim.get("claim"), str) else "",
                "supporting_evidence": evidence_items,
                "entities": _bounded_string_list(raw_claim.get("entities")),
                "factors": _bounded_string_list(raw_claim.get("factors")),
                "direction": raw_claim.get("direction")
                if isinstance(raw_claim.get("direction"), str)
                else "",
                "confidence": confidence if isinstance(confidence, (int, float)) else None,
            }
        )
    abstentions = []
    for raw in proposal.get("abstentions") or []:
        if isinstance(raw, Mapping):
            abstentions.append(
                {
                    "candidate_ids": _bounded_string_list(raw.get("candidate_ids")),
                    "reason_code": raw.get("reason_code")
                    if isinstance(raw.get("reason_code"), str)
                    else "",
                    "notes": (
                        raw.get("notes")
                        if preserve_abstention_notes and isinstance(raw.get("notes"), str)
                        else ""
                    ),
                }
            )
    return {"claims": claims, "abstentions": abstentions}


def bounded_rejected_candidate_payload_v4_1(proposal: Mapping[str, Any]) -> dict[str, Any]:
    """Retain strict forensic fields and discard optional free-form notes/prose."""

    return _bounded_candidate_payload_v4_1(
        proposal, preserve_abstention_notes=False
    )


def bounded_provider_proposal_v4_1(proposal: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the exact v4.1 wire fields while preserving contract notes."""

    return _bounded_candidate_payload_v4_1(
        proposal, preserve_abstention_notes=True
    )


def provider_proposal_shape_valid_v4_1(proposal: Mapping[str, Any]) -> bool:
    """Reject fields outside the frozen wire shape; never silently admit them."""

    if set(proposal) - {"claims", "abstentions"}:
        return False
    claims = proposal.get("claims")
    if isinstance(claims, list):
        claim_fields = {
            "claim",
            "supporting_evidence",
            "entities",
            "factors",
            "direction",
            "confidence",
        }
        for claim in claims:
            if not isinstance(claim, Mapping) or set(claim) - claim_fields:
                return False
            evidence = claim.get("supporting_evidence")
            if isinstance(evidence, list) and any(
                not isinstance(item, Mapping) or set(item) - {"quote", "candidate_id"}
                for item in evidence
            ):
                return False
    abstentions = proposal.get("abstentions")
    return not (
        isinstance(abstentions, list)
        and any(
            not isinstance(item, Mapping)
            or set(item) - {"candidate_ids", "reason_code", "notes"}
            for item in abstentions
        )
    )


def normalize_v4_1_proposal_to_canonical_bundle(
    proposal: Mapping[str, Any],
    *,
    source_report: str,
    run_id: str,
    ticker: str,
    agent: str,
    agent_output_id: str,
    candidate_manifest: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source_hash = sha256_text(source_report)
    manifest_by_id = {
        str(item["candidate_id"]): dict(item)
        for item in candidate_manifest
        if isinstance(item, Mapping) and isinstance(item.get("candidate_id"), str)
    }
    diagnostics: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    raw_claims = proposal.get("claims")
    if isinstance(raw_claims, list):
        for claim_index, raw_claim in enumerate(raw_claims):
            if not isinstance(raw_claim, Mapping):
                continue
            spans = []
            selected_candidate_ids = []
            evidence_items = raw_claim.get("supporting_evidence")
            if isinstance(evidence_items, list):
                for evidence_index, evidence in enumerate(evidence_items):
                    resolved = resolve_supporting_evidence_v4_1(
                        report=source_report,
                        evidence=evidence,
                        candidate_manifest=manifest_by_id,
                        source_report_sha256=source_hash,
                        run_id=run_id,
                        ticker=ticker,
                        agent=agent,
                        agent_output_id=agent_output_id,
                    )
                    diagnostics.append(
                        resolved.to_diagnostic(
                            claim_index=claim_index,
                            evidence_index=evidence_index,
                            source_report_sha256=source_hash,
                        )
                    )
                    spans.append(
                        {
                            "start": resolved.resolved_start if resolved.located else None,
                            "end": resolved.resolved_end if resolved.located else None,
                            "exact_quote": resolved.quote if resolved.located else "",
                        }
                    )
                    if (
                        resolved.selected_candidate_id in manifest_by_id
                        and resolved.selected_candidate_id not in selected_candidate_ids
                    ):
                        selected_candidate_ids.append(resolved.selected_candidate_id)
            evidence_text = " ".join(str(item.get("exact_quote") or "") for item in spans)
            claims.append(
                {
                    "shadow_claim_id": "",
                    "claim": raw_claim.get("claim") if isinstance(raw_claim.get("claim"), str) else "",
                    "evidence": evidence_text,
                    "source_spans": spans,
                    "entities": _bounded_string_list(raw_claim.get("entities")),
                    "factors": _bounded_string_list(raw_claim.get("factors")),
                    "direction": raw_claim.get("direction"),
                    "confidence": raw_claim.get("confidence"),
                    "source_type": "unknown",
                    "source_refs": [],
                    "candidate_segment_ids": selected_candidate_ids,
                    "extraction_status": "proposed",
                }
            )
    abstentions = []
    for raw in proposal.get("abstentions") or []:
        if not isinstance(raw, Mapping):
            continue
        known_ids = [item for item in _bounded_string_list(raw.get("candidate_ids")) if item in manifest_by_id]
        abstentions.append(
            {
                "candidate_segment_ids": known_ids,
                "reason_code": raw.get("reason_code") if isinstance(raw.get("reason_code"), str) else "",
                "notes": raw.get("notes") if isinstance(raw.get("notes"), str) else "",
            }
        )
    return (
        {
            "schema_version": STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION,
            "run_id": str(run_id),
            "ticker": str(ticker),
            "agent": str(agent),
            "agent_output_id": str(agent_output_id),
            "source_report_sha256": source_hash,
            "prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_1,
            "prompt_sha256": STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256,
            "claims": claims,
            "abstentions": abstentions,
            "validation_summary": {},
            "shadow_only": True,
            "production_authority": False,
        },
        diagnostics,
    )


class StructuredOutputShadowParserV4_1:
    def __init__(
        self,
        semantic_invoker: SemanticInvoker | Callable[..., Any],
        *,
        factor_vocabulary: Sequence[str] | None = None,
        prompt_builder: Callable[[Mapping[str, Any]], str] = build_shadow_prompt_input_v4_1,
        max_claims: int = DEFAULT_MAX_CLAIMS,
        max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    ) -> None:
        if semantic_invoker is None:
            raise ValueError("semantic_invoker is required; v4.1 never constructs a Provider")
        if factor_vocabulary is None:
            from comqutor_alpha.structure_engine.factor_normalizer import FACTOR_ALIASES

            factor_vocabulary = tuple(FACTOR_ALIASES.keys())
        self.semantic_invoker = semantic_invoker
        self.factor_vocabulary = tuple(factor_vocabulary)
        self.prompt_builder = prompt_builder
        self.max_claims = int(max_claims)
        self.max_input_bytes = int(max_input_bytes)
        self.max_output_bytes = int(max_output_bytes)
        self.last_resolution_diagnostics: list[dict[str, Any]] = []
        self.last_rejected_candidate_payload: dict[str, Any] | None = None
        self.last_candidate_manifest: list[dict[str, Any]] = []
        self.last_request: dict[str, Any] | None = None
        self.last_wire_shape_valid = True

    def _failure(
        self,
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
            prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_1,
            prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256,
            status=status,
            reason_code=reason_code,
            message=message,
        )

    def _invoke(self, prompt: str, request: Mapping[str, Any]) -> Any:
        method = getattr(self.semantic_invoker, "invoke", None)
        if callable(method):
            return method(prompt=prompt, request=request)
        if callable(self.semantic_invoker):
            return self.semantic_invoker(prompt=prompt, request=request)
        raise TypeError("semantic_invoker must be callable or implement invoke")

    def parse_report_shadow_v4_1(
        self,
        *,
        source_report: str,
        run_id: str,
        ticker: str,
        agent: str,
        agent_output_id: str,
        candidate_segments: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.last_resolution_diagnostics = []
        self.last_rejected_candidate_payload = None
        self.last_candidate_manifest = []
        self.last_request = None
        self.last_wire_shape_valid = True
        if not isinstance(source_report, str):
            source_report = str(source_report or "")
        if len(source_report.encode("utf-8")) > self.max_input_bytes:
            return self._failure(
                source_report, run_id, ticker, agent, agent_output_id, "input_too_large",
                SHADOW_OUTPUT_TOO_LARGE, "source report exceeds the configured offline input limit",
            )
        candidates = (
            [deepcopy(dict(item)) for item in candidate_segments]
            if candidate_segments is not None
            else build_candidate_segments(source_report, agent_output_id=agent_output_id)[0]
        )
        manifest = build_candidate_manifest_v4_1(
            source_report=source_report,
            run_id=run_id,
            ticker=ticker,
            agent=agent,
            agent_output_id=agent_output_id,
            candidate_segments=candidates,
        )
        self.last_candidate_manifest = manifest
        request = build_shadow_request_v4_1(
            source_report=source_report,
            run_id=run_id,
            ticker=ticker,
            agent=agent,
            agent_output_id=agent_output_id,
            candidate_manifest=manifest,
            factor_vocabulary=self.factor_vocabulary,
        )
        self.last_request = request
        try:
            raw_output = self._invoke(self.prompt_builder(request), request)
        except Exception as exc:
            return self._failure(
                source_report, run_id, ticker, agent, agent_output_id, "parser_error",
                SHADOW_INVOKER_ERROR, f"injected semantic invoker failed: {type(exc).__name__}",
            )
        if isinstance(raw_output, (bytes, bytearray)):
            try:
                raw_output = bytes(raw_output).decode("utf-8")
            except UnicodeDecodeError:
                raw_output = None
        if isinstance(raw_output, str):
            if len(raw_output.encode("utf-8")) > self.max_output_bytes:
                return self._failure(
                    source_report, run_id, ticker, agent, agent_output_id, "validation_rejected",
                    SHADOW_OUTPUT_TOO_LARGE, "semantic proposal exceeds the configured output limit",
                )
            try:
                proposal = json.loads(raw_output)
            except json.JSONDecodeError:
                proposal = None
        else:
            proposal = deepcopy(raw_output)
        if not isinstance(proposal, Mapping):
            return self._failure(
                source_report, run_id, ticker, agent, agent_output_id, "parser_error",
                SHADOW_JSON_INVALID, "semantic proposal is not a strict JSON object",
            )
        wire_shape_valid = provider_proposal_shape_valid_v4_1(proposal)
        self.last_wire_shape_valid = wire_shape_valid
        bounded_proposal = bounded_provider_proposal_v4_1(proposal)
        canonical, diagnostics = normalize_v4_1_proposal_to_canonical_bundle(
            bounded_proposal,
            source_report=source_report,
            run_id=run_id,
            ticker=ticker,
            agent=agent,
            agent_output_id=agent_output_id,
            candidate_manifest=manifest,
        )
        self.last_resolution_diagnostics = diagnostics
        proposal_with_ids = assign_deterministic_claim_ids(canonical)
        validation = validate_shadow_bundle(
            proposal_with_ids,
            source_report=source_report,
            run_id=run_id,
            ticker=ticker,
            agent=agent,
            agent_output_id=agent_output_id,
            prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_1,
            prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256,
            factor_vocabulary=self.factor_vocabulary,
            allowed_source_refs=(),
            allowed_candidate_segment_ids=[item["candidate_id"] for item in manifest],
            max_claims=self.max_claims,
            max_output_bytes=self.max_output_bytes,
        )
        if not validation.valid or not wire_shape_valid:
            self.last_rejected_candidate_payload = (
                bounded_rejected_candidate_payload_v4_1(proposal)
            )
            summary = validation.to_summary()
            if not wire_shape_valid:
                reasons = list(summary.get("reason_codes") or [])
                if SHADOW_UNAPPROVED_FIELD not in reasons:
                    reasons.append(SHADOW_UNAPPROVED_FIELD)
                summary["reason_codes"] = reasons
                summary["valid"] = False
                summary["status"] = "validation_rejected"
            first_code = (
                summary["reason_codes"][0]
                if summary.get("reason_codes")
                else SHADOW_JSON_INVALID
            )
            failure = self._failure(
                source_report, run_id, ticker, agent, agent_output_id, "validation_rejected",
                first_code, "semantic proposal rejected by deterministic validation",
            )
            failure["validation_summary"] = summary
            return failure
        accepted = deepcopy(dict(proposal_with_ids))
        accepted["validation_summary"] = validation.to_summary()
        accepted["shadow_only"] = True
        accepted["production_authority"] = False
        return accepted


def build_rejected_forensic_record_v4_1(
    *,
    parser: StructuredOutputShadowParserV4_1,
    bundle: Mapping[str, Any],
    provider: str,
    model: str,
    semantic_call_id: str | None,
) -> dict[str, Any] | None:
    proposal = parser.last_rejected_candidate_payload
    request = parser.last_request
    if proposal is None or request is None:
        return None
    summary = bundle.get("validation_summary") if isinstance(bundle, Mapping) else {}
    reason_codes = list(summary.get("reason_codes") or []) if isinstance(summary, Mapping) else []
    return {
        "schema_version": REJECTED_FORENSIC_SCHEMA_VERSION,
        "classification": "REJECTED_CANDIDATE",
        "non_authoritative": True,
        "forensic_only": True,
        "admitted_claim_count": 0,
        "run_id": request["run_id"],
        "ticker": request["ticker"],
        "agent": request["agent"],
        "agent_output_id": request["agent_output_id"],
        "source_report_sha256": request["source_report_sha256"],
        "factor_vocabulary": list(request.get("factor_vocabulary") or []),
        "request_sha256": _sha256_canonical_json(request),
        "prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_1,
        "prompt_sha256": STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256,
        "provider": provider,
        "model": model,
        "semantic_call_id": semantic_call_id,
        "parsed_candidate_payload": deepcopy(proposal),
        "parsed_candidate_payload_sha256": _sha256_canonical_json(proposal),
        "candidate_manifest": deepcopy(parser.last_candidate_manifest),
        "resolver_diagnostics": deepcopy(parser.last_resolution_diagnostics),
        "wire_shape_reason_codes": (
            [] if parser.last_wire_shape_valid else [SHADOW_UNAPPROVED_FIELD]
        ),
        "final_rejection_reason_codes": reason_codes,
    }


def replay_rejected_forensic_record_v4_1(
    record: Mapping[str, Any], *, source_report: str
) -> dict[str, Any]:
    """Provider-zero deterministic reproduction of a parsed rejection."""

    reasons: list[str] = []
    proposal = record.get("parsed_candidate_payload")
    manifest = record.get("candidate_manifest")
    if not isinstance(proposal, Mapping) or not isinstance(manifest, list):
        return {"status": "FAIL", "reason_codes": ["REJECTED_REPLAY_ARTIFACT_INVALID"], "provider_calls": 0}
    if record.get("source_report_sha256") != sha256_text(source_report):
        reasons.append("REJECTED_REPLAY_SOURCE_HASH_MISMATCH")
    if record.get("parsed_candidate_payload_sha256") != _sha256_canonical_json(proposal):
        reasons.append("REJECTED_REPLAY_PAYLOAD_HASH_MISMATCH")
    replay_request = build_shadow_request_v4_1(
        source_report=source_report,
        run_id=str(record.get("run_id") or ""),
        ticker=str(record.get("ticker") or ""),
        agent=str(record.get("agent") or ""),
        agent_output_id=str(record.get("agent_output_id") or ""),
        candidate_manifest=manifest,
        factor_vocabulary=[
            item for item in record.get("factor_vocabulary") or [] if isinstance(item, str)
        ],
    )
    if record.get("request_sha256") != _sha256_canonical_json(replay_request):
        reasons.append("REJECTED_REPLAY_REQUEST_HASH_MISMATCH")
    canonical, diagnostics = normalize_v4_1_proposal_to_canonical_bundle(
        proposal,
        source_report=source_report,
        run_id=str(record.get("run_id") or ""),
        ticker=str(record.get("ticker") or ""),
        agent=str(record.get("agent") or ""),
        agent_output_id=str(record.get("agent_output_id") or ""),
        candidate_manifest=manifest,
    )
    validated = validate_shadow_bundle(
        assign_deterministic_claim_ids(canonical),
        source_report=source_report,
        run_id=str(record.get("run_id") or ""),
        ticker=str(record.get("ticker") or ""),
        agent=str(record.get("agent") or ""),
        agent_output_id=str(record.get("agent_output_id") or ""),
        prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_1,
        prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256,
        factor_vocabulary=[
            item for item in record.get("factor_vocabulary") or [] if isinstance(item, str)
        ],
        allowed_source_refs=(),
        allowed_candidate_segment_ids=[
            item["candidate_id"]
            for item in manifest
            if isinstance(item, Mapping) and isinstance(item.get("candidate_id"), str)
        ],
    )
    reproduced_reasons = list(validated.reason_codes)
    for reason in record.get("wire_shape_reason_codes") or []:
        if isinstance(reason, str) and reason not in reproduced_reasons:
            reproduced_reasons.append(reason)
    expected_reasons = list(record.get("final_rejection_reason_codes") or [])
    if not reproduced_reasons or reproduced_reasons != expected_reasons:
        reasons.append("REJECTED_REPLAY_REASON_NOT_REPRODUCIBLE")
    if diagnostics != list(record.get("resolver_diagnostics") or []):
        reasons.append("REJECTED_REPLAY_DIAGNOSTICS_NOT_REPRODUCIBLE")
    return {
        "status": "PASS" if not reasons else "FAIL",
        "reason_codes": reasons,
        "reproduced_rejection_reason_codes": reproduced_reasons,
        "resolver_diagnostics_equal": diagnostics == list(record.get("resolver_diagnostics") or []),
        "provider_calls": 0,
        "provider_zero": True,
    }


__all__ = [
    "REJECTED_FORENSIC_SCHEMA_VERSION",
    "SHADOW_INPUT_SCHEMA_VERSION_V4_1",
    "SHADOW_PROVIDER_PROPOSAL_SCHEMA_VERSION_V4_1",
    "StructuredOutputShadowParserV4_1",
    "bounded_provider_proposal_v4_1",
    "bounded_rejected_candidate_payload_v4_1",
    "build_candidate_manifest_v4_1",
    "build_rejected_forensic_record_v4_1",
    "build_shadow_request_v4_1",
    "normalize_v4_1_proposal_to_canonical_bundle",
    "provider_proposal_shape_valid_v4_1",
    "replay_rejected_forensic_record_v4_1",
    "resolve_supporting_evidence_v4_1",
]
