"""v4.2 deterministic global-exact-match Evidence provenance -- candidate
binding removed from the active runtime entirely.

Product Owner final decision, made from a real, persisted root-cause
diagnosis of the failed v4.1 final Re-Canary
(``docs/audit_artifacts/phase1_master/phase1_v4_1_location_root_cause.md``):
of 61 rejected Evidence items, 58 (95%) were already globally unique,
correctly-copied quotes that failed ONLY because the model additionally
supplied an optional ``candidate_id`` whose registered span did not happen
to contain that already-unique quote. Only 3/99 items were genuine
duplicate exact quotes, and the v4.1 resolver handled all 3 correctly
(safe rejection, since no candidate was supplied). Zero fabricated
Evidence, zero source-identity mismatch, zero canonical-relation-block
contamination, and zero candidate-window overlap were found anywhere in
that data.

The repair implemented here is exactly what that diagnosis calls for: the
Provider is never asked to identify WHERE its Evidence quote is located
-- not a candidate_id, not an offset, not a segment number, nothing.
COMQUTOR's own deterministic resolver is the sole location authority:

    matches = every exact character-for-character occurrence of the quote
              in the complete, immutable, hashed source report
    0 matches   -> REJECT (NO_EXACT_MATCH)
    1 match     -> ACCEPT that occurrence (UNIQUE_EXACT_MATCH)
    N>1 matches -> ACCEPT the occurrence with the smallest start offset
                   (DUPLICATE_ACCEPTED_EARLIEST_OCCURRENCE); every offset,
                   the total count, and the selection policy are recorded

This is not a claim about which occurrence the model "intended" -- only
that this exact text provably exists in this exact source report, and the
earliest occurrence is COMQUTOR's deterministic, reproducible provenance
location for it every time the same source+quote pair is resolved again.
Which occurrence was selected NEVER drives any semantic field (direction,
factor, entities, claim text) -- it is a provenance-location detail only.

No candidate/segment concept appears anywhere in this module's wire
request, wire response, resolver signature, or forensic records --
provably so: this module never imports ``build_candidate_segments`` and
carries no field named ``candidate_id``/``candidate_ids``/
``candidate_manifest``/``candidate_hints`` anywhere. The following active
v4.1 failure modes are consequently unreachable here because the concepts
they depend on do not exist in this module at all:
``CANDIDATE_LOCAL_NO_EXACT_MATCH``, ``CANDIDATE_ID_UNKNOWN``,
``CANDIDATE_SOURCE_IDENTITY_MISMATCH``, ``AMBIGUOUS_CANDIDATE_REQUIRED``.

Absolutely still forbidden: fuzzy matching, whitespace/Markdown
normalization before matching, embedding or semantic search, Levenshtein
repair, nearest-sentence selection, a second LLM pass to repair a quote,
or any location-selection model other than the one above. Exact-match
provenance remains, as always, distinct from semantic support -- this
module never marks a claim's evidence "semantically correct" merely
because it resolved; that judgment is reserved for human/AI review.
Prompt text is a genuine, small, anchored delta from v4 (see
``structured_output_shadow_prompt_v4_2.py``) that removes every
candidate/offset/segment-related instruction and wire field; the
semantic extraction rules themselves are otherwise unchanged. v4 and
v4.1 both remain frozen and are never modified.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from comqutor_alpha.structure_engine.structured_output_shadow import SemanticInvoker
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v4_2 import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_2,
    build_shadow_prompt_input_v4_2,
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

SHADOW_INPUT_SCHEMA_VERSION_V4_2 = "comqutor.structured_claim_shadow_input.v4.2"
SHADOW_PROVIDER_PROPOSAL_SCHEMA_VERSION_V4_2 = (
    "comqutor.structured_claim_shadow_provider_proposal.v4.2"
)
REJECTED_FORENSIC_SCHEMA_VERSION_V4_2 = (
    "comqutor.structured_claim_shadow_rejected_forensic.v4.2"
)

DEFAULT_MAX_CLAIMS = 128
DEFAULT_MAX_INPUT_BYTES = 500_000
DEFAULT_MAX_OUTPUT_BYTES = 1_000_000

SELECTION_POLICY_UNIQUE_EXACT_OCCURRENCE = "UNIQUE_EXACT_OCCURRENCE"
SELECTION_POLICY_FIRST_EXACT_OCCURRENCE = "FIRST_EXACT_OCCURRENCE"

RESOLUTION_UNIQUE_EXACT_MATCH = "UNIQUE_EXACT_MATCH"
RESOLUTION_DUPLICATE_ACCEPTED_EARLIEST_OCCURRENCE = (
    "DUPLICATE_ACCEPTED_EARLIEST_OCCURRENCE"
)
RESOLUTION_NO_EXACT_MATCH = "NO_EXACT_MATCH"
RESOLUTION_INVALID_QUOTE = "INVALID_QUOTE"

# Both statuses below produce a real, located span -- a duplicate exact
# quote is an ACCEPT outcome in v4.2, never a rejection.
RESOLUTION_STATUSES_LOCATED = frozenset(
    {RESOLUTION_UNIQUE_EXACT_MATCH, RESOLUTION_DUPLICATE_ACCEPTED_EARLIEST_OCCURRENCE}
)
RESOLUTION_STATUSES = frozenset(
    {
        RESOLUTION_UNIQUE_EXACT_MATCH,
        RESOLUTION_DUPLICATE_ACCEPTED_EARLIEST_OCCURRENCE,
        RESOLUTION_NO_EXACT_MATCH,
        RESOLUTION_INVALID_QUOTE,
    }
)

# v4.1 candidate-binding-only failure codes, listed here ONLY so a reader/
# test can prove by inspection that none of them can ever be produced by
# this module -- they are string literals, never referenced by any live
# code path below, and no function in this module accepts, requires, or
# validates against any candidate identifier or manifest.
INACTIVE_V4_1_CANDIDATE_ONLY_FAILURE_MODES = frozenset(
    {
        "CANDIDATE_LOCAL_NO_EXACT_MATCH",
        "CANDIDATE_ID_UNKNOWN",
        "CANDIDATE_SOURCE_IDENTITY_MISMATCH",
        "AMBIGUOUS_CANDIDATE_REQUIRED",
        "CANDIDATE_LOCAL_MULTIPLE_MATCHES",
    }
)


def _find_all_occurrences(report: str, quote: str) -> list[int]:
    """Every exact occurrence of ``quote`` in ``report``, including
    overlapping ones (advances the search by 1 char, not ``len(quote)``) --
    byte-identical algorithm to v1-v4.1's own helper, duplicated rather
    than imported so v4.2 never depends on a sibling's internals drifting
    underneath it (this codebase's established versioning convention)."""

    if not quote:
        return []
    positions: list[int] = []
    cursor = 0
    while True:
        index = report.find(quote, cursor)
        if index < 0:
            break
        positions.append(index)
        cursor = index + 1
    return positions


@dataclass(frozen=True)
class ResolvedQuoteV4_2:
    """Result of one :func:`resolve_supporting_quote_v4_2` lookup. ``start``/
    ``end`` are populated for both LOCATED statuses -- including a resolved
    duplicate -- never for ``NO_EXACT_MATCH``/``INVALID_QUOTE``. This
    dataclass has no candidate/segment field of any kind."""

    status: str
    quote: str
    start: int | None
    end: int | None
    exact_match_count: int
    exact_match_offsets: tuple[int, ...]
    selected_match_index: int | None
    selection_policy: str | None
    duplicate_exact_quote: bool

    def to_diagnostic(self, *, claim_index: int, quote_index: int) -> dict[str, Any]:
        return {
            "claim_index": claim_index,
            "quote_index": quote_index,
            "status": self.status,
            "exact_match_count": self.exact_match_count,
            "exact_match_offsets": list(self.exact_match_offsets),
            "selected_match_index": self.selected_match_index,
            "selected_start": self.start,
            "selected_end": self.end,
            "selection_policy": self.selection_policy,
            "duplicate_exact_quote": self.duplicate_exact_quote,
        }


def resolve_supporting_quote_v4_2(*, report: str, quote: Any) -> ResolvedQuoteV4_2:
    """The sole authority that turns one Provider-proposed
    ``supporting_quotes`` entry into a located span.

    Signature deliberately has no candidate/segment/hint parameter of any
    kind -- the decision depends only on ``report`` and ``quote``, full
    stop. Never fuzzy, never normalized, never semantic, never a second
    LLM pass, never a location the caller has to guess about.

    - Not a non-empty string -> ``INVALID_QUOTE``.
    - Zero exact occurrences -> ``NO_EXACT_MATCH`` (rejected, never
      repaired).
    - Exactly one exact occurrence -> ``UNIQUE_EXACT_MATCH``.
    - More than one exact occurrence -> ACCEPT the occurrence with the
      smallest start offset (``DUPLICATE_ACCEPTED_EARLIEST_OCCURRENCE``);
      every offset and the total count are recorded in the diagnostic.
      This is a deterministic PROVENANCE choice only -- it never implies
      the model "intended" that occurrence, and the selected occurrence
      never drives any semantic field.
    """

    if not isinstance(quote, str) or quote == "":
        return ResolvedQuoteV4_2(
            RESOLUTION_INVALID_QUOTE,
            quote if isinstance(quote, str) else "",
            None,
            None,
            0,
            (),
            None,
            None,
            False,
        )

    offsets = tuple(_find_all_occurrences(report, quote))
    if not offsets:
        return ResolvedQuoteV4_2(
            RESOLUTION_NO_EXACT_MATCH, quote, None, None, 0, (), None, None, False
        )

    selected_start = min(offsets)
    selected_index = offsets.index(selected_start)
    duplicate = len(offsets) > 1
    if duplicate:
        status = RESOLUTION_DUPLICATE_ACCEPTED_EARLIEST_OCCURRENCE
        policy = SELECTION_POLICY_FIRST_EXACT_OCCURRENCE
    else:
        status = RESOLUTION_UNIQUE_EXACT_MATCH
        policy = SELECTION_POLICY_UNIQUE_EXACT_OCCURRENCE
    return ResolvedQuoteV4_2(
        status,
        quote,
        selected_start,
        selected_start + len(quote),
        len(offsets),
        offsets,
        selected_index,
        policy,
        duplicate,
    )


def summarize_resolution_log_v4_2(
    resolution_log: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    """Aggregate per-quote resolution records by status, plus duplicate
    counters used by offline/real-evidence replay reporting."""

    counts = {
        "total": len(resolution_log),
        "unique_exact_match": 0,
        "duplicate_accepted_earliest_occurrence": 0,
        "no_exact_match": 0,
        "invalid_quote": 0,
        "duplicate_quotes_seen": 0,
        "duplicate_quotes_canonically_resolved": 0,
    }
    key_by_status = {
        RESOLUTION_UNIQUE_EXACT_MATCH: "unique_exact_match",
        RESOLUTION_DUPLICATE_ACCEPTED_EARLIEST_OCCURRENCE: "duplicate_accepted_earliest_occurrence",
        RESOLUTION_NO_EXACT_MATCH: "no_exact_match",
        RESOLUTION_INVALID_QUOTE: "invalid_quote",
    }
    for entry in resolution_log:
        key = key_by_status.get(str(entry.get("status")))
        if key:
            counts[key] += 1
        if entry.get("duplicate_exact_quote"):
            counts["duplicate_quotes_seen"] += 1
            if entry.get("status") == RESOLUTION_DUPLICATE_ACCEPTED_EARLIEST_OCCURRENCE:
                counts["duplicate_quotes_canonically_resolved"] += 1
    return counts


# ---------------------------------------------------------------------------
# Wire request/response -- NO candidate/segment/offset field anywhere.
# ---------------------------------------------------------------------------


def build_shadow_request_v4_2(
    *,
    source_report: str,
    run_id: str,
    ticker: str,
    agent: str,
    agent_output_id: str,
    factor_vocabulary: Sequence[str],
) -> dict[str, Any]:
    """Minimal v4.2 wire request. No ``candidate_hints`` field -- there is
    no candidate concept for the Provider to be shown or asked about."""

    return {
        "input_schema_version": SHADOW_INPUT_SCHEMA_VERSION_V4_2,
        "run_id": str(run_id),
        "ticker": str(ticker),
        "agent": str(agent),
        "agent_output_id": str(agent_output_id),
        "factor_vocabulary": sorted({str(value) for value in factor_vocabulary}),
        "agent_report_boundary": "BEGIN_UNTRUSTED_AGENT_REPORT",
        "agent_report": source_report,
        "agent_report_end_boundary": "END_UNTRUSTED_AGENT_REPORT",
    }


_CLAIM_FIELDS_V4_2 = frozenset(
    {"claim", "supporting_quotes", "entities", "factors", "direction", "confidence"}
)
_ABSTENTION_FIELDS_V4_2 = frozenset({"reason_code", "notes"})


def provider_proposal_shape_valid_v4_2(proposal: Mapping[str, Any]) -> bool:
    """Reject any wire field outside the frozen v4.2 shape -- including a
    ``candidate_id``/``candidate_ids`` field, which is not part of this
    shape at all and is therefore rejected the same as any other
    unapproved field. Generic wire-shape hardening (kept from the good
    forensic-persistence work done for v4.1, with every candidate-specific
    field removed)."""

    if set(proposal) - {"claims", "abstentions"}:
        return False
    claims = proposal.get("claims")
    if isinstance(claims, list):
        for claim in claims:
            if not isinstance(claim, Mapping) or set(claim) - _CLAIM_FIELDS_V4_2:
                return False
            quotes = claim.get("supporting_quotes")
            if isinstance(quotes, list) and any(not isinstance(item, str) for item in quotes):
                return False
    abstentions = proposal.get("abstentions")
    return not (
        isinstance(abstentions, list)
        and any(
            not isinstance(item, Mapping) or set(item) - _ABSTENTION_FIELDS_V4_2
            for item in abstentions
        )
    )


def _bounded_string_list(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _bounded_proposal_v4_2(
    proposal: Mapping[str, Any], *, preserve_abstention_notes: bool
) -> dict[str, Any]:
    claims: list[dict[str, Any]] = []
    for raw_claim in proposal.get("claims") or []:
        if not isinstance(raw_claim, Mapping):
            continue
        confidence = raw_claim.get("confidence")
        claims.append(
            {
                "claim": raw_claim.get("claim") if isinstance(raw_claim.get("claim"), str) else "",
                "supporting_quotes": _bounded_string_list(raw_claim.get("supporting_quotes")),
                "entities": _bounded_string_list(raw_claim.get("entities")),
                "factors": _bounded_string_list(raw_claim.get("factors")),
                "direction": raw_claim.get("direction")
                if isinstance(raw_claim.get("direction"), str)
                else "",
                "confidence": confidence if isinstance(confidence, (int, float)) else None,
            }
        )
    abstentions: list[dict[str, Any]] = []
    for raw in proposal.get("abstentions") or []:
        if isinstance(raw, Mapping):
            abstentions.append(
                {
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


def bounded_provider_proposal_v4_2(proposal: Mapping[str, Any]) -> dict[str, Any]:
    return _bounded_proposal_v4_2(proposal, preserve_abstention_notes=True)


def bounded_rejected_candidate_payload_v4_2(proposal: Mapping[str, Any]) -> dict[str, Any]:
    return _bounded_proposal_v4_2(proposal, preserve_abstention_notes=False)


def _reconstruct_evidence(quotes: Sequence[str]) -> str:
    if len(quotes) == 1:
        return quotes[0]
    return " ".join(quotes)


def _span_from_resolved(resolved: ResolvedQuoteV4_2) -> dict[str, Any]:
    if resolved.status in RESOLUTION_STATUSES_LOCATED and resolved.start is not None and resolved.end is not None:
        return {"start": resolved.start, "end": resolved.end, "exact_quote": resolved.quote}
    return {"start": None, "end": None, "exact_quote": ""}


def normalize_v4_2_proposal_to_canonical_bundle(
    proposal: Mapping[str, Any],
    *,
    source_report: str,
    run_id: str,
    ticker: str,
    agent: str,
    agent_output_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Upgrade a v4.2 Provider proposal into the exact, UNCHANGED
    ``comqutor.structured_claim_shadow.v1`` bundle shape, resolving every
    ``supporting_quotes`` entry through :func:`resolve_supporting_quote_v4_2`
    -- no candidate/segment parameter accepted or consulted anywhere in
    this function. Every claim's ``candidate_segment_ids`` is always
    ``[]``: there is no candidate concept left to populate it with, by
    design, not by omission.

    Returns ``(bundle, resolution_log)``. Never raises on malformed input:
    a claim whose ``supporting_quotes`` contains any quote that fails to
    resolve gets an invalid placeholder span (``start=None, end=None``);
    the unchanged ``validate_shadow_bundle`` is the sole authority that
    then rejects the WHOLE bundle for it -- the same bundle-level,
    all-or-nothing admission v1-v4.1 already use.
    """

    raw_claims = proposal.get("claims")
    raw_abstentions = proposal.get("abstentions")
    resolution_log: list[dict[str, Any]] = []

    claims: list[dict[str, Any]] = []
    if isinstance(raw_claims, list):
        for claim_index, raw_claim in enumerate(raw_claims):
            if not isinstance(raw_claim, Mapping):
                continue
            raw_quotes = raw_claim.get("supporting_quotes")
            spans: list[dict[str, Any]] = []
            quote_texts: list[str] = []
            if isinstance(raw_quotes, list):
                for quote_index, raw_quote in enumerate(raw_quotes):
                    resolved = resolve_supporting_quote_v4_2(report=source_report, quote=raw_quote)
                    resolution_log.append(
                        resolved.to_diagnostic(claim_index=claim_index, quote_index=quote_index)
                    )
                    spans.append(_span_from_resolved(resolved))
                    if resolved.status in RESOLUTION_STATUSES_LOCATED:
                        quote_texts.append(resolved.quote)
            claims.append(
                {
                    "shadow_claim_id": "",
                    "claim": raw_claim.get("claim") if isinstance(raw_claim.get("claim"), str) else "",
                    "evidence": _reconstruct_evidence(quote_texts) if quote_texts else "",
                    "source_spans": spans,
                    "entities": _bounded_string_list(raw_claim.get("entities")),
                    "factors": _bounded_string_list(raw_claim.get("factors")),
                    "direction": raw_claim.get("direction"),
                    "confidence": raw_claim.get("confidence"),
                    "source_type": "unknown",
                    "source_refs": [],
                    "candidate_segment_ids": [],
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
                    "candidate_segment_ids": [],
                    "reason_code": raw_abstention.get("reason_code")
                    if isinstance(raw_abstention.get("reason_code"), str)
                    else "",
                    "notes": raw_abstention.get("notes")
                    if isinstance(raw_abstention.get("notes"), str)
                    else "",
                }
            )

    bundle = {
        "schema_version": STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION,
        "run_id": str(run_id),
        "ticker": str(ticker),
        "agent": str(agent),
        "agent_output_id": str(agent_output_id),
        "source_report_sha256": sha256_text(source_report),
        "prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_2,
        "prompt_sha256": STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256,
        "claims": claims,
        "abstentions": abstentions,
        "validation_summary": {},
        "shadow_only": True,
        "production_authority": False,
    }
    return bundle, resolution_log


class StructuredOutputShadowParserV4_2:
    """v4.2 sibling of ``StructuredOutputShadowParserV4``: identical
    offline, fail-soft, validator-is-sole-authority design; the
    deterministic resolver's duplicate-match policy is the only semantic
    difference (see module docstring). Never imports or calls
    ``build_candidate_segments`` -- there is no candidate concept anywhere
    in this class. Also carries v4.1's rejected-forensic-persistence
    improvement (``last_rejected_candidate_payload`` etc.), with every
    candidate-manifest-specific field removed."""

    def __init__(
        self,
        semantic_invoker: SemanticInvoker | Callable[..., Any],
        *,
        factor_vocabulary: Sequence[str] | None = None,
        prompt_builder: Callable[[Mapping[str, Any]], str] = build_shadow_prompt_input_v4_2,
        max_claims: int = DEFAULT_MAX_CLAIMS,
        max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    ) -> None:
        if semantic_invoker is None:
            raise ValueError("semantic_invoker is required; v4.2 never constructs a Provider")
        self.semantic_invoker = semantic_invoker
        if factor_vocabulary is None:
            from comqutor_alpha.structure_engine.factor_normalizer import FACTOR_ALIASES

            factor_vocabulary = tuple(FACTOR_ALIASES.keys())
        self.factor_vocabulary = tuple(factor_vocabulary)
        self.prompt_builder = prompt_builder
        self.max_claims = int(max_claims)
        self.max_input_bytes = int(max_input_bytes)
        self.max_output_bytes = int(max_output_bytes)
        self.last_resolution_log: list[dict[str, Any]] = []
        self.last_rejected_candidate_payload: dict[str, Any] | None = None
        self.last_request: dict[str, Any] | None = None
        self.last_wire_shape_valid = True

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
            prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_2,
            prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256,
            status=status,
            reason_code=reason_code,
            message=message,
        )

    def parse_report_shadow_v4_2(
        self,
        *,
        source_report: str,
        run_id: str,
        ticker: str,
        agent: str,
        agent_output_id: str,
    ) -> dict[str, Any]:
        self.last_resolution_log = []
        self.last_rejected_candidate_payload = None
        self.last_request = None
        self.last_wire_shape_valid = True

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

        request = build_shadow_request_v4_2(
            source_report=source_report,
            run_id=run_id,
            ticker=ticker,
            agent=agent,
            agent_output_id=agent_output_id,
            factor_vocabulary=self.factor_vocabulary,
        )
        self.last_request = request
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

        wire_shape_valid = provider_proposal_shape_valid_v4_2(proposal)
        self.last_wire_shape_valid = wire_shape_valid
        bounded_proposal = bounded_provider_proposal_v4_2(proposal)

        try:
            canonical, resolution_log = normalize_v4_2_proposal_to_canonical_bundle(
                bounded_proposal,
                source_report=source_report,
                run_id=run_id,
                ticker=ticker,
                agent=agent,
                agent_output_id=agent_output_id,
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
                message=f"v4.2 proposal normalization failed: {type(exc).__name__}",
            )
        self.last_resolution_log = resolution_log

        proposal_with_ids = assign_deterministic_claim_ids(canonical)
        validation = validate_shadow_bundle(
            proposal_with_ids,
            source_report=source_report,
            run_id=run_id,
            ticker=ticker,
            agent=agent,
            agent_output_id=agent_output_id,
            prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_2,
            prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256,
            factor_vocabulary=self.factor_vocabulary,
            allowed_source_refs=(),
            allowed_candidate_segment_ids=None,
            max_claims=self.max_claims,
            max_output_bytes=self.max_output_bytes,
        )
        if not validation.valid or not wire_shape_valid:
            self.last_rejected_candidate_payload = bounded_rejected_candidate_payload_v4_2(proposal)
            summary = validation.to_summary()
            if not wire_shape_valid:
                reasons = list(summary.get("reason_codes") or [])
                if SHADOW_UNAPPROVED_FIELD not in reasons:
                    reasons.append(SHADOW_UNAPPROVED_FIELD)
                summary["reason_codes"] = reasons
                summary["valid"] = False
                summary["status"] = "validation_rejected"
            first_code = summary["reason_codes"][0] if summary.get("reason_codes") else SHADOW_JSON_INVALID
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
            failure["validation_summary"] = summary
            return failure

        accepted = deepcopy(dict(proposal_with_ids))
        accepted["validation_summary"] = validation.to_summary()
        accepted["shadow_only"] = True
        accepted["production_authority"] = False
        return accepted


def build_rejected_forensic_record_v4_2(
    *,
    parser: StructuredOutputShadowParserV4_2,
    bundle: Mapping[str, Any],
    provider: str,
    model: str,
    semantic_call_id: str | None,
) -> dict[str, Any] | None:
    """v4.2 sibling of ``build_rejected_forensic_record_v4_1`` -- same good
    forensic-persistence property (a rejected raw Provider proposal is
    never lost), with every candidate-manifest-specific field removed."""

    proposal = parser.last_rejected_candidate_payload
    request = parser.last_request
    if proposal is None or request is None:
        return None
    summary = bundle.get("validation_summary") if isinstance(bundle, Mapping) else {}
    reason_codes = list(summary.get("reason_codes") or []) if isinstance(summary, Mapping) else []
    return {
        "schema_version": REJECTED_FORENSIC_SCHEMA_VERSION_V4_2,
        "classification": "REJECTED_PROPOSAL",
        "non_authoritative": True,
        "forensic_only": True,
        "admitted_claim_count": 0,
        "run_id": request["run_id"],
        "ticker": request["ticker"],
        "agent": request["agent"],
        "agent_output_id": request["agent_output_id"],
        "source_report_sha256": sha256_text(request.get("agent_report", "")),
        "factor_vocabulary": list(request.get("factor_vocabulary") or []),
        "prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_2,
        "prompt_sha256": STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256,
        "provider": provider,
        "model": model,
        "semantic_call_id": semantic_call_id,
        "parsed_proposal": deepcopy(proposal),
        "parsed_proposal_sha256": sha256_text(
            json.dumps(proposal, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        ),
        "resolver_diagnostics": deepcopy(parser.last_resolution_log),
        "wire_shape_reason_codes": [] if parser.last_wire_shape_valid else [SHADOW_UNAPPROVED_FIELD],
        "final_rejection_reason_codes": reason_codes,
    }


def replay_rejected_forensic_record_v4_2(
    record: Mapping[str, Any], *, source_report: str
) -> dict[str, Any]:
    """Provider-zero deterministic reproduction of a parsed v4.2 rejection."""

    reasons: list[str] = []
    proposal = record.get("parsed_proposal")
    if not isinstance(proposal, Mapping):
        return {
            "status": "FAIL",
            "reason_codes": ["REJECTED_REPLAY_ARTIFACT_INVALID"],
            "provider_calls": 0,
        }
    if record.get("source_report_sha256") != sha256_text(source_report):
        reasons.append("REJECTED_REPLAY_SOURCE_HASH_MISMATCH")
    expected_payload_hash = sha256_text(
        json.dumps(proposal, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    if record.get("parsed_proposal_sha256") != expected_payload_hash:
        reasons.append("REJECTED_REPLAY_PAYLOAD_HASH_MISMATCH")
    canonical, diagnostics = normalize_v4_2_proposal_to_canonical_bundle(
        proposal,
        source_report=source_report,
        run_id=str(record.get("run_id") or ""),
        ticker=str(record.get("ticker") or ""),
        agent=str(record.get("agent") or ""),
        agent_output_id=str(record.get("agent_output_id") or ""),
    )
    validated = validate_shadow_bundle(
        assign_deterministic_claim_ids(canonical),
        source_report=source_report,
        run_id=str(record.get("run_id") or ""),
        ticker=str(record.get("ticker") or ""),
        agent=str(record.get("agent") or ""),
        agent_output_id=str(record.get("agent_output_id") or ""),
        prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_2,
        prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256,
        factor_vocabulary=[item for item in record.get("factor_vocabulary") or [] if isinstance(item, str)],
        allowed_source_refs=(),
        allowed_candidate_segment_ids=None,
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
    "DEFAULT_MAX_CLAIMS",
    "DEFAULT_MAX_INPUT_BYTES",
    "DEFAULT_MAX_OUTPUT_BYTES",
    "INACTIVE_V4_1_CANDIDATE_ONLY_FAILURE_MODES",
    "REJECTED_FORENSIC_SCHEMA_VERSION_V4_2",
    "RESOLUTION_DUPLICATE_ACCEPTED_EARLIEST_OCCURRENCE",
    "RESOLUTION_INVALID_QUOTE",
    "RESOLUTION_NO_EXACT_MATCH",
    "RESOLUTION_STATUSES",
    "RESOLUTION_STATUSES_LOCATED",
    "RESOLUTION_UNIQUE_EXACT_MATCH",
    "SELECTION_POLICY_FIRST_EXACT_OCCURRENCE",
    "SELECTION_POLICY_UNIQUE_EXACT_OCCURRENCE",
    "SHADOW_INPUT_SCHEMA_VERSION_V4_2",
    "SHADOW_PROVIDER_PROPOSAL_SCHEMA_VERSION_V4_2",
    "ResolvedQuoteV4_2",
    "StructuredOutputShadowParserV4_2",
    "build_rejected_forensic_record_v4_2",
    "build_shadow_request_v4_2",
    "bounded_provider_proposal_v4_2",
    "bounded_rejected_candidate_payload_v4_2",
    "normalize_v4_2_proposal_to_canonical_bundle",
    "provider_proposal_shape_valid_v4_2",
    "replay_rejected_forensic_record_v4_2",
    "resolve_supporting_quote_v4_2",
    "summarize_resolution_log_v4_2",
]
