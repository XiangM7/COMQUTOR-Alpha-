"""Phase 1 Master evidence-alignment fix, round 2: additive v4 markdown-
formatting-fidelity path for the offline Structured Output Shadow parser.

This module never replaces or modifies ``structured_output_shadow.py`` (v1),
``structured_output_shadow_v2.py``, ``structured_output_shadow_v3.py``, or
``structured_output_shadow_schema.py``. It reuses, unchanged:

- the candidate-segment source (``build_candidate_segments`` ->
  ``extract_claim_segments_with_audit``),
- the canonical bundle schema (``comqutor.structured_claim_shadow.v1``), and
- the sole deterministic admission authority (``validate_shadow_bundle``).

v3's real 24-report evaluation proved the EvidenceQuoteResolver design
(verbatim quotes, exact string match only, never fuzzy) works exactly as
intended -- zero fabricated or unresolved quotes were ever admitted -- but
measured a real cost: 8 of 24 reports (33.3%) were rejected outright.
Offline root-cause analysis of that real, persisted evaluation data (zero
Provider calls) found 31 of 33 individual quote-resolution failures (94%)
traced to one precise, mechanical cause: the model reliably dropped or
repositioned Markdown emphasis characters (``**bold**``) when copying a
phrase, because v3's prompt never told it those characters are literal
report content. v4 is deliberately, exactly identical to v3 in every way
EXCEPT the prompt text it sends (see
``structured_output_shadow_prompt_v4.py`` for the new FORMATTING RULES
section) -- this module is a full, independent sibling of
``structured_output_shadow_v3.py`` (duplicated rather than imported, so v4
never depends on v3's internals drifting underneath it, matching this
codebase's established v1/v2/v3 convention) with only the prompt/schema
identity constants swapped. The EvidenceQuoteResolver algorithm itself is
unchanged: exact deterministic string matching only, never fuzzy matching,
embedding search, Levenshtein repair, semantic nearest-neighbor matching,
approximate substring matching, or a second LLM pass to fix a bad quote.
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
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v4 import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4,
    build_shadow_prompt_input_v4,
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

SHADOW_INPUT_SCHEMA_VERSION_V4 = "comqutor.structured_claim_shadow_input.v4"
SHADOW_PROVIDER_PROPOSAL_SCHEMA_VERSION_V4 = "comqutor.structured_claim_shadow_provider_proposal.v4"

DEFAULT_MAX_CLAIMS = 128
DEFAULT_MAX_INPUT_BYTES = 500_000
DEFAULT_MAX_OUTPUT_BYTES = 1_000_000

# ---------------------------------------------------------------------------
# EvidenceQuoteResolver: the sole, exact-match-only, never-fuzzy authority
# that turns a Provider-proposed verbatim quote into a source span.
# Byte-identical algorithm to v3's -- only the prompt that produces the
# quotes fed into it changes in v4.
# ---------------------------------------------------------------------------

RESOLUTION_UNIQUE_EXACT_MATCH = "UNIQUE_EXACT_MATCH"
RESOLUTION_DISAMBIGUATED_VIA_CANDIDATE = "DISAMBIGUATED_VIA_CANDIDATE_HINT"
RESOLUTION_NO_EXACT_MATCH = "NO_EXACT_MATCH"
RESOLUTION_AMBIGUOUS_MULTIPLE_MATCH = "AMBIGUOUS_MULTIPLE_MATCH"
RESOLUTION_INVALID_QUOTE = "INVALID_QUOTE"

RESOLUTION_STATUSES_LOCATED = frozenset(
    {RESOLUTION_UNIQUE_EXACT_MATCH, RESOLUTION_DISAMBIGUATED_VIA_CANDIDATE}
)
RESOLUTION_STATUSES = frozenset(
    {
        RESOLUTION_UNIQUE_EXACT_MATCH,
        RESOLUTION_DISAMBIGUATED_VIA_CANDIDATE,
        RESOLUTION_NO_EXACT_MATCH,
        RESOLUTION_AMBIGUOUS_MULTIPLE_MATCH,
        RESOLUTION_INVALID_QUOTE,
    }
)


@dataclass(frozen=True)
class ResolvedQuote:
    """Result of one :func:`resolve_supporting_quote` lookup. ``start``/
    ``end`` are only ever populated for the two LOCATED statuses -- every
    other status carries no location, by construction, so a caller can
    never accidentally treat a rejected quote as located."""

    status: str
    quote: str
    start: int | None
    end: int | None
    match_count: int

    def to_summary(self, *, claim_index: int, quote_index: int) -> dict[str, Any]:
        return {
            "claim_index": claim_index,
            "quote_index": quote_index,
            "status": self.status,
            "match_count": self.match_count,
        }


def _find_all_occurrences(report: str, quote: str) -> list[int]:
    """Every exact occurrence of ``quote`` in ``report``, including
    overlapping ones (advances the search by 1 char, not ``len(quote)``, so
    an overlapping repeat is never silently undercounted -- ambiguity must
    never be hidden by a stride that skips a real match)."""

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


def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def resolve_supporting_quote(
    *,
    report: str,
    quote: Any,
    candidate_hint_spans: Sequence[tuple[int, int]] = (),
) -> ResolvedQuote:
    """The sole authority that turns one Provider-proposed
    ``supporting_quotes`` entry into a located span.

    Exact deterministic string matching ONLY -- never fuzzy matching,
    embedding search, Levenshtein repair, semantic nearest-neighbor
    matching, approximate substring matching, and never a second LLM pass
    to fix an offset (there is no offset to fix: v4 never accepts one from
    the model in the first place).

    - Not a non-empty string -> ``INVALID_QUOTE``.
    - Zero exact occurrences -> ``NO_EXACT_MATCH`` (a fabricated, malformed,
      or (the v3->v4 finding) formatting-stripped quote; rejected, never
      repaired).
    - Exactly one exact occurrence -> ``UNIQUE_EXACT_MATCH``.
    - More than one exact occurrence: if exactly one occurrence overlaps
      the union of the caller-supplied ``candidate_hint_spans`` (the
      located source spans of the specific candidate segment(s) the
      Provider's claim itself referenced via ``candidate_ids``), that
      occurrence is used (``DISAMBIGUATED_VIA_CANDIDATE_HINT``) -- this is
      deterministic disambiguation using caller-owned location data the
      model itself pointed to, never a semantic guess and never a default
      "first match". Otherwise -> ``AMBIGUOUS_MULTIPLE_MATCH`` (rejected;
      never defaults to the first occurrence).
    """

    if not isinstance(quote, str) or quote == "":
        return ResolvedQuote(
            RESOLUTION_INVALID_QUOTE, quote if isinstance(quote, str) else "", None, None, 0
        )

    positions = _find_all_occurrences(report, quote)
    if not positions:
        return ResolvedQuote(RESOLUTION_NO_EXACT_MATCH, quote, None, None, 0)
    if len(positions) == 1:
        start = positions[0]
        return ResolvedQuote(RESOLUTION_UNIQUE_EXACT_MATCH, quote, start, start + len(quote), 1)

    if candidate_hint_spans:
        overlapping = [
            start
            for start in positions
            if any(
                _overlaps(start, start + len(quote), hint_start, hint_end)
                for hint_start, hint_end in candidate_hint_spans
            )
        ]
        if len(overlapping) == 1:
            start = overlapping[0]
            return ResolvedQuote(
                RESOLUTION_DISAMBIGUATED_VIA_CANDIDATE, quote, start, start + len(quote), len(positions)
            )

    return ResolvedQuote(RESOLUTION_AMBIGUOUS_MULTIPLE_MATCH, quote, None, None, len(positions))


def summarize_resolution_log(resolution_log: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Aggregate per-quote resolution records by status. Used by
    ``scripts/run_phase1_master.py``'s v4 Smoke gate ("zero fabricated
    quote admitted" / "zero unresolved quote admitted") and by
    ``report_result.json`` diagnostics; never persisted inside the
    canonical Shadow bundle itself."""

    counts = {
        "total": len(resolution_log),
        "unique_exact_match": 0,
        "disambiguated_via_candidate": 0,
        "no_exact_match": 0,
        "ambiguous_multiple_match": 0,
        "invalid_quote": 0,
    }
    key_by_status = {
        RESOLUTION_UNIQUE_EXACT_MATCH: "unique_exact_match",
        RESOLUTION_DISAMBIGUATED_VIA_CANDIDATE: "disambiguated_via_candidate",
        RESOLUTION_NO_EXACT_MATCH: "no_exact_match",
        RESOLUTION_AMBIGUOUS_MULTIPLE_MATCH: "ambiguous_multiple_match",
        RESOLUTION_INVALID_QUOTE: "invalid_quote",
    }
    for entry in resolution_log:
        key = key_by_status.get(str(entry.get("status")))
        if key:
            counts[key] += 1
    return counts


# ---------------------------------------------------------------------------
# Wire request -- identical compression properties to v2/v3.
# ---------------------------------------------------------------------------


def _valid_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def select_located_candidate_hints(
    candidate_segments: Sequence[Mapping[str, Any]],
) -> list[dict[str, int]]:
    """Compact, offset-only hints for the subset of candidates that have a
    verified, exact, locatable source span. Identical in shape and intent
    to v2/v3's own ``select_located_candidate_hints``, but deliberately
    duplicated rather than imported: v4 must never depend on an earlier
    version's internals drifting underneath it."""

    hints: list[dict[str, int]] = []
    for segment in candidate_segments:
        spans = segment.get("source_spans") or []
        if not spans:
            continue
        span = spans[0]
        start, end = span.get("start"), span.get("end")
        if (
            isinstance(start, int)
            and not isinstance(start, bool)
            and isinstance(end, int)
            and not isinstance(end, bool)
        ):
            hints.append({"id": int(segment["candidate_index"]), "start": start, "end": end})
    return hints


def build_shadow_request_v4(
    *,
    source_report: str,
    run_id: str,
    ticker: str,
    agent: str,
    agent_output_id: str,
    candidate_segments: Sequence[Mapping[str, Any]],
    factor_vocabulary: Sequence[str],
) -> dict[str, Any]:
    """Build the minimal v4 wire request. Byte-for-byte the same
    compression properties as v2/v3 (report sent exactly once; candidate
    segments reduced to ``{id,start,end}`` hints for the located subset
    only; no hashes, no prompt identity, no full candidate text/section/
    authority-flag, no ``allowed_source_refs``). v4's Provider-facing claim
    shape is byte-identical to v3's (``supporting_quotes``, never offsets)
    -- only the fixed instruction text differs (module docstring)."""

    return {
        "input_schema_version": SHADOW_INPUT_SCHEMA_VERSION_V4,
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


# ---------------------------------------------------------------------------
# Normalization: Provider proposal -> canonical bundle (unchanged schema).
# ---------------------------------------------------------------------------


def _reconstruct_evidence(spans: Sequence[Mapping[str, Any]]) -> str:
    """One of ``validate_shadow_bundle``'s own accepted bounded
    combinations: the single quote when there is one span, else the
    space-joined concatenation of every span's ``exact_quote``, in order."""

    quotes = [str(span.get("exact_quote") or "") for span in spans]
    if len(quotes) == 1:
        return quotes[0]
    return " ".join(quotes)


def _span_from_resolved(resolved: ResolvedQuote) -> dict[str, Any]:
    if resolved.status in RESOLUTION_STATUSES_LOCATED and resolved.start is not None and resolved.end is not None:
        return {"start": resolved.start, "end": resolved.end, "exact_quote": resolved.quote}
    return {"start": None, "end": None, "exact_quote": ""}


def normalize_v4_proposal_to_canonical_bundle(
    proposal: Mapping[str, Any],
    *,
    source_report: str,
    run_id: str,
    ticker: str,
    agent: str,
    agent_output_id: str,
    candidate_index_to_id: Mapping[int, str],
    candidate_index_to_spans: Mapping[int, Sequence[tuple[int, int]]] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Upgrade a minimal v4 Provider proposal into the exact, UNCHANGED
    ``comqutor.structured_claim_shadow.v1`` bundle shape, resolving every
    ``supporting_quotes`` entry through :func:`resolve_supporting_quote`
    first. Byte-identical logic to
    ``structured_output_shadow_v3.normalize_v3_proposal_to_canonical_bundle``
    -- only the ``prompt_version``/``prompt_sha256`` stamped onto the
    bundle differ.

    Returns ``(bundle, resolution_log)``. The bundle is exactly the same
    canonical shape v1/v2/v3 already produce -- never a new field, never a
    new admission path. ``resolution_log`` is a flat, bundle-EXTERNAL list
    of per-quote resolution records for Phase 1 Master's own evidence-
    alignment gate diagnostics; it is never persisted inside the canonical
    bundle itself (the canonical schema does not change).

    Never raises on malformed input: any wrong-shaped nested value degrades
    to an empty/placeholder value that the unchanged validator then rejects
    on its own terms. A claim whose ``supporting_quotes`` contains ANY
    quote that fails to resolve gets an invalid placeholder span
    (``start=None, end=None``) for that entry; ``validate_shadow_bundle``
    (unchanged) is the sole authority that then rejects the WHOLE bundle
    for it -- the same bundle-level, all-or-nothing admission v1/v2/v3
    already use.
    """

    raw_claims = proposal.get("claims")
    raw_abstentions = proposal.get("abstentions")
    candidate_index_to_spans = dict(candidate_index_to_spans or {})
    known_candidate_indices = set(candidate_index_to_id) | set(candidate_index_to_spans)
    resolution_log: list[dict[str, Any]] = []

    def _resolve_candidate_indices(raw: Any) -> list[int]:
        if not isinstance(raw, list):
            return []
        return [
            value
            for value in raw
            if isinstance(value, int) and not isinstance(value, bool) and value in known_candidate_indices
        ]

    def _candidate_ids_for(indices: Sequence[int]) -> list[str]:
        return [candidate_index_to_id[index] for index in indices if index in candidate_index_to_id]

    claims: list[dict[str, Any]] = []
    if isinstance(raw_claims, list):
        for claim_index, raw_claim in enumerate(raw_claims):
            if not isinstance(raw_claim, Mapping):
                continue
            candidate_indices = _resolve_candidate_indices(raw_claim.get("candidate_ids"))
            hint_spans: list[tuple[int, int]] = [
                (int(span[0]), int(span[1]))
                for index in candidate_indices
                for span in candidate_index_to_spans.get(index, [])
            ]
            raw_quotes = raw_claim.get("supporting_quotes")
            spans: list[dict[str, Any]] = []
            if isinstance(raw_quotes, list):
                for quote_index, raw_quote in enumerate(raw_quotes):
                    resolved = resolve_supporting_quote(
                        report=source_report, quote=raw_quote, candidate_hint_spans=hint_spans
                    )
                    resolution_log.append(resolved.to_summary(claim_index=claim_index, quote_index=quote_index))
                    spans.append(_span_from_resolved(resolved))
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
                    "candidate_segment_ids": _candidate_ids_for(candidate_indices),
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
                    "candidate_segment_ids": _candidate_ids_for(
                        _resolve_candidate_indices(raw_abstention.get("candidate_ids"))
                    ),
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

    bundle = {
        "schema_version": STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION,
        "run_id": str(run_id),
        "ticker": str(ticker),
        "agent": str(agent),
        "agent_output_id": str(agent_output_id),
        "source_report_sha256": sha256_text(source_report),
        "prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4,
        "prompt_sha256": STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256,
        "claims": claims,
        "abstentions": abstentions,
        "validation_summary": {},
        "shadow_only": True,
        "production_authority": False,
    }
    return bundle, resolution_log


class StructuredOutputShadowParserV4:
    """v4 sibling of ``StructuredOutputShadowParser``/``...V2``/``...V3``:
    identical offline, fail-soft, validator-is-sole-authority design; only
    the fixed instruction text sent to the Provider differs (module
    docstring). See ``StructuredOutputShadowParserV3`` for the identical
    design this duplicates.

    ``last_resolution_log`` is reset to ``[]`` at the start of every
    :meth:`parse_report_shadow_v4` call and populated only once
    normalization actually runs -- callers that need per-quote resolution
    diagnostics (e.g. the real-Provider smoke runner) read it after the
    call; callers that only need the bundle can ignore it entirely.
    """

    def __init__(
        self,
        semantic_invoker: SemanticInvoker | Callable[..., Any],
        *,
        factor_vocabulary: Sequence[str] | None = None,
        prompt_builder: Callable[[Mapping[str, Any]], str] = build_shadow_prompt_input_v4,
        max_claims: int = DEFAULT_MAX_CLAIMS,
        max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    ) -> None:
        if semantic_invoker is None:
            raise ValueError("semantic_invoker is required; v4 never constructs a Provider")
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
            prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4,
            prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256,
            status=status,
            reason_code=reason_code,
            message=message,
        )

    def parse_report_shadow_v4(
        self,
        *,
        source_report: str,
        run_id: str,
        ticker: str,
        agent: str,
        agent_output_id: str,
        candidate_segments: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.last_resolution_log = []
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
        candidate_index_to_spans: dict[int, list[tuple[int, int]]] = {}
        for segment in candidates:
            located: list[tuple[int, int]] = []
            for span in segment.get("source_spans") or []:
                start, end = span.get("start"), span.get("end")
                if (
                    isinstance(start, int)
                    and not isinstance(start, bool)
                    and isinstance(end, int)
                    and not isinstance(end, bool)
                ):
                    located.append((start, end))
            if located:
                candidate_index_to_spans[int(segment["candidate_index"])] = located

        request = build_shadow_request_v4(
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
            canonical, resolution_log = normalize_v4_proposal_to_canonical_bundle(
                proposal,
                source_report=source_report,
                run_id=run_id,
                ticker=ticker,
                agent=agent,
                agent_output_id=agent_output_id,
                candidate_index_to_id=candidate_index_to_id,
                candidate_index_to_spans=candidate_index_to_spans,
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
                message=f"v4 proposal normalization failed: {type(exc).__name__}",
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
            prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4,
            prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256,
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


def parse_report_shadow_v4(
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
    parser = StructuredOutputShadowParserV4(
        semantic_invoker,
        factor_vocabulary=factor_vocabulary,
        max_claims=max_claims,
        max_input_bytes=max_input_bytes,
        max_output_bytes=max_output_bytes,
    )
    return parser.parse_report_shadow_v4(
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
    "RESOLUTION_AMBIGUOUS_MULTIPLE_MATCH",
    "RESOLUTION_DISAMBIGUATED_VIA_CANDIDATE",
    "RESOLUTION_INVALID_QUOTE",
    "RESOLUTION_NO_EXACT_MATCH",
    "RESOLUTION_STATUSES",
    "RESOLUTION_STATUSES_LOCATED",
    "RESOLUTION_UNIQUE_EXACT_MATCH",
    "SHADOW_INPUT_SCHEMA_VERSION_V4",
    "SHADOW_PROVIDER_PROPOSAL_SCHEMA_VERSION_V4",
    "ResolvedQuote",
    "StructuredOutputShadowParserV4",
    "build_shadow_request_v4",
    "normalize_v4_proposal_to_canonical_bundle",
    "parse_report_shadow_v4",
    "resolve_supporting_quote",
    "select_located_candidate_hints",
    "summarize_resolution_log",
]
