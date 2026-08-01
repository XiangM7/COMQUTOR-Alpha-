"""Deterministic parsing/validation of the ``COMQUTOR_CANONICAL_RELATIONS``
block TradingAgents agents append to their own report text (per
``canonical_relation_prompt.py``'s injected output-format contract).

Not an LLM call: this module only ever parses and validates text an agent
already produced in its one existing call. Two responsibilities, kept
separate on purpose:

1. :func:`split_human_text_and_canonical_block` -- deterministically removes
   the machine-readable block from an agent's raw report text so claim
   segmentation (``structured_output_adapter.py``) only ever sees the human
   prose, never JSON syntax/field names as claim text.
2. :func:`validate_canonical_relations` -- validates each relation the block
   proposed against the real production vocabulary
   (``canonical_vocabulary.py``) and the agent's own report text, returning
   both accepted and rejected records with a stable rejection reason code.
   A relation this validates as accepted becomes a *candidate* edge only --
   it still must pass every existing Graph admission guard
   (``graph_builder._normalize_and_merge_edges``) exactly like a
   deterministically-extracted relation.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from comqutor_alpha.structure_engine.canonical_relation_prompt import (
    RELATION_BLOCK_MARKER,
    RELATION_BLOCK_SCHEMA_VERSION,
)
from comqutor_alpha.structure_engine.factor_normalizer import factor_mention_span, normalize_text

VALID_ASSERTION_STATUSES = frozenset({"asserted", "hedged", "conditional", "hypothetical"})
# Only "asserted" ever becomes a candidate edge -- hedged/conditional/
# hypothetical relations are still recorded (for audit) but never handed to
# the Graph as a candidate edge, matching "hypothetical 不得成为 admitted
# edge" and the same treatment the deterministic grammar already gives
# conditional/negated relations (down-weighted, never silently promoted).
ADMISSIBLE_ASSERTION_STATUSES = frozenset({"asserted"})

MAX_RELATIONS_PER_BLOCK = 64
_JSON_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_BARE_OBJECT_PATTERN = re.compile(r"(\{.*\})", re.DOTALL)


@dataclass(frozen=True)
class ParsedCanonicalBlock:
    human_text: str
    found: bool
    raw_block_text: str | None = None
    schema_version: str | None = None
    raw_relations: list[Any] = field(default_factory=list)
    parse_error: str | None = None


def split_human_text_and_canonical_block(raw_text: Any) -> ParsedCanonicalBlock:
    """Split ``raw_text`` into (human report prose, parsed machine block).

    Never rewrites the human prose beyond removing the marker line and its
    trailing block: on any parse failure, everything from the marker onward
    is still excluded from ``human_text`` (it is unambiguously not prose the
    agent intended as part of its report), but the returned relations list
    is empty and ``parse_error`` records why -- callers must treat this
    exactly like "no relations were validated", never fail the run.
    """
    text = raw_text if isinstance(raw_text, str) else ("" if raw_text is None else str(raw_text))
    marker_index = text.find(RELATION_BLOCK_MARKER)
    if marker_index == -1:
        return ParsedCanonicalBlock(human_text=text, found=False)

    human_text = text[:marker_index].rstrip()
    remainder = text[marker_index + len(RELATION_BLOCK_MARKER) :]

    fence_match = _JSON_FENCE_PATTERN.search(remainder)
    block_text = fence_match.group(1) if fence_match else None
    if block_text is None:
        bare_match = _BARE_OBJECT_PATTERN.search(remainder)
        block_text = bare_match.group(1) if bare_match else None

    if block_text is None:
        return ParsedCanonicalBlock(
            human_text=human_text,
            found=True,
            raw_block_text=remainder.strip()[:2000],
            parse_error="NO_JSON_OBJECT_FOUND",
        )

    try:
        parsed = json.loads(block_text)
    except (json.JSONDecodeError, ValueError):
        return ParsedCanonicalBlock(
            human_text=human_text,
            found=True,
            raw_block_text=block_text[:2000],
            parse_error="INVALID_JSON",
        )

    if not isinstance(parsed, dict):
        return ParsedCanonicalBlock(
            human_text=human_text,
            found=True,
            raw_block_text=block_text[:2000],
            parse_error="NOT_A_JSON_OBJECT",
        )

    raw_relations = parsed.get("relations")
    if not isinstance(raw_relations, list):
        raw_relations = []
        parse_error = "MISSING_RELATIONS_ARRAY"
    else:
        parse_error = None

    return ParsedCanonicalBlock(
        human_text=human_text,
        found=True,
        raw_block_text=block_text[:2000],
        schema_version=parsed.get("schema_version") if isinstance(parsed.get("schema_version"), str) else None,
        raw_relations=raw_relations[:MAX_RELATIONS_PER_BLOCK],
        parse_error=parse_error,
    )


def _factor_ids(vocabulary: dict[str, Any]) -> frozenset[str]:
    return frozenset(str(f.get("factor_id")) for f in vocabulary.get("factors") or [])


def _relation_types(vocabulary: dict[str, Any]) -> frozenset[str]:
    return frozenset(str(r.get("relation_type")) for r in vocabulary.get("relations") or [])


def _display_name(vocabulary: dict[str, Any], factor_id: str) -> str:
    for f in vocabulary.get("factors") or []:
        if f.get("factor_id") == factor_id:
            return str(f.get("display_name") or factor_id)
    return factor_id


def _display_phrase(vocabulary: dict[str, Any], relation_type: str) -> str:
    for r in vocabulary.get("relations") or []:
        if r.get("relation_type") == relation_type:
            return str(r.get("display_phrase") or relation_type)
    return relation_type


def _alias_overlap(source_factor: str, target_factor: str, evidence_quote: str) -> bool:
    """True when the source and target factor's own mention spans overlap
    within the evidence quote -- the same "one span, two different factors'
    aliases both match it" ambiguity ``relation_grammar._ambiguous_factors``
    guards against for deterministic candidates, applied here to LLM-sourced
    candidates via the same underlying alias data
    (``factor_normalizer.factor_mention_span``, never a second copy)."""
    normalized = normalize_text(evidence_quote)
    source_span = factor_mention_span(source_factor, normalized)
    target_span = factor_mention_span(target_factor, normalized)
    if source_span is None or target_span is None:
        return False
    return source_span[0] < target_span[1] and target_span[0] < source_span[1]


def _valid_confidence(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not (0.0 <= number <= 1.0):
        return None
    return number


def validate_canonical_relations(
    parsed: ParsedCanonicalBlock,
    *,
    vocabulary: dict[str, Any],
    agent_report_text: str,
    agent: str,
    run_id: str | None,
    ticker: str | None,
    source_agent_output_id: str | None,
) -> list[dict[str, Any]]:
    """Validate every raw relation in ``parsed`` against the real production
    vocabulary and the agent's own report text. Returns one record per raw
    relation (accepted or rejected) plus, when the block itself failed to
    parse, zero records (nothing to validate) -- the caller always treats a
    block-level parse failure identically to "no canonical relations": the
    deterministic Structure Extractor path is unaffected either way.
    """
    if not parsed.found:
        return []

    records: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str, str]] = set()

    if parsed.parse_error is not None or parsed.schema_version != RELATION_BLOCK_SCHEMA_VERSION:
        reason = "schema_invalid"
        # A block-level failure (bad JSON, wrong/missing schema_version)
        # still yields one auditable rejection record per raw relation item
        # actually present, so an operator can tell "the agent tried and got
        # the schema wrong" apart from "the agent found nothing to report".
        for index, raw in enumerate(parsed.raw_relations):
            records.append(
                _rejected_record(
                    index, raw, reason, agent=agent, run_id=run_id, ticker=ticker,
                    source_agent_output_id=source_agent_output_id,
                )
            )
        if not parsed.raw_relations and parsed.parse_error is not None:
            records.append(
                _rejected_record(
                    0, None, reason, agent=agent, run_id=run_id, ticker=ticker,
                    source_agent_output_id=source_agent_output_id,
                )
            )
        return records

    factor_ids = _factor_ids(vocabulary)
    relation_types = _relation_types(vocabulary)

    for index, raw in enumerate(parsed.raw_relations):
        if not isinstance(raw, dict):
            records.append(
                _rejected_record(
                    index, raw, "schema_invalid", agent=agent, run_id=run_id, ticker=ticker,
                    source_agent_output_id=source_agent_output_id,
                )
            )
            continue

        source_factor_id = str(raw.get("source_factor_id") or "").strip()
        target_factor_id = str(raw.get("target_factor_id") or "").strip()
        relation_type = str(raw.get("relation_type") or "").strip()
        evidence_quote = str(raw.get("evidence_quote") or "").strip()
        assertion_status = str(raw.get("assertion_status") or "").strip().lower()
        confidence = _valid_confidence(raw.get("confidence"))

        reason = None
        if source_factor_id not in factor_ids:
            reason = "unknown_source_factor"
        elif target_factor_id not in factor_ids:
            reason = "unknown_target_factor"
        elif relation_type not in relation_types:
            reason = "invalid_relation_type"
        elif source_factor_id == target_factor_id:
            reason = "self_edge"
        elif not evidence_quote or evidence_quote not in agent_report_text:
            reason = "evidence_not_found"
        elif confidence is None:
            reason = "invalid_confidence"
        elif assertion_status not in VALID_ASSERTION_STATUSES:
            reason = "invalid_assertion_status"
        elif _alias_overlap(source_factor_id, target_factor_id, evidence_quote):
            reason = "alias_overlap"
        else:
            key = (agent, evidence_quote, source_factor_id, relation_type + ":" + target_factor_id)
            if key in seen_keys:
                reason = "duplicate_relation"
            else:
                seen_keys.add(key)

        if reason is not None:
            records.append(
                _rejected_record(
                    index, raw, reason, agent=agent, run_id=run_id, ticker=ticker,
                    source_agent_output_id=source_agent_output_id,
                )
            )
            continue

        source_display = _display_name(vocabulary, source_factor_id)
        target_display = _display_name(vocabulary, target_factor_id)
        phrase = _display_phrase(vocabulary, relation_type)
        canonical_sentence = f"{source_display} {phrase} {target_display}."
        relation_id = "canrel_" + hashlib.sha1(
            f"{source_agent_output_id}:{index}:{source_factor_id}:{relation_type}:{target_factor_id}".encode()
        ).hexdigest()[:16]

        records.append(
            {
                "relation_id": relation_id,
                "run_id": run_id,
                "ticker": ticker,
                "agent": agent,
                "source_agent_output_id": source_agent_output_id,
                "source_factor_id": source_factor_id,
                "source_factor_display_name": source_display,
                "relation_type": relation_type,
                "relation_display_phrase": phrase,
                "target_factor_id": target_factor_id,
                "target_factor_display_name": target_display,
                "canonical_sentence": canonical_sentence,
                "evidence_quote": evidence_quote,
                "assertion_status": assertion_status,
                "confidence": confidence,
                "schema_version": RELATION_BLOCK_SCHEMA_VERSION,
                "taxonomy_version": vocabulary.get("taxonomy_version"),
                "taxonomy_sha256": vocabulary.get("taxonomy_sha256"),
                "relation_registry_version": vocabulary.get("relation_registry_version"),
                "validation_status": "accepted",
                "validation_rejection_reasons": [],
                "extraction_path": "tradingagents_canonical_output",
                "candidate_edge_created": assertion_status in ADMISSIBLE_ASSERTION_STATUSES,
            }
        )

    return records


LINEAGE_STATUS_RESOLVED = "resolved"
LINEAGE_STATUS_UNRESOLVED = "unresolved"
LINEAGE_STATUS_AMBIGUOUS = "ambiguous"
LINEAGE_STATUS_NOT_APPLICABLE = "not_applicable"

LINEAGE_METHOD_EXACT = "exact"
LINEAGE_METHOD_NORMALIZED_EXACT = "normalized_exact"
LINEAGE_METHOD_CONTAINMENT = "containment"
LINEAGE_METHOD_NONE = "none"

LINEAGE_REASON_SOURCE_CLAIM_NOT_FOUND = "SOURCE_CLAIM_NOT_FOUND"
LINEAGE_REASON_MULTIPLE_EQUALLY_STRONG_CANDIDATES = "MULTIPLE_EQUALLY_STRONG_CONTAINMENT_CANDIDATES"


def _normalize_whitespace(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _lineage_tie_break_key(record: Mapping[str, Any]) -> tuple[int, int, str]:
    claim_text = str(record.get("claim") or "")
    claim_index = record.get("claim_index")
    return (
        len(claim_text),
        int(claim_index) if isinstance(claim_index, int) else 0,
        str(record.get("claim_id") or ""),
    )


def _lineage_resolved(record: Mapping[str, Any], method: str) -> dict[str, Any]:
    return {
        "source_claim_ids": [str(record.get("claim_id"))],
        "lineage_status": LINEAGE_STATUS_RESOLVED,
        "lineage_method": method,
        "lineage_reasons": [],
    }


def _resolve_containment(candidates: list[Mapping[str, Any]], method: str) -> dict[str, Any]:
    shortest_length = min(len(str(c.get("claim") or "")) for c in candidates)
    tied = [c for c in candidates if len(str(c.get("claim") or "")) == shortest_length]
    if len(tied) == 1:
        return _lineage_resolved(tied[0], method)
    tied_sorted = sorted(tied, key=lambda c: (c.get("claim_index") or 0, str(c.get("claim_id") or "")))
    return {
        "source_claim_ids": [str(c.get("claim_id")) for c in tied_sorted],
        "lineage_status": LINEAGE_STATUS_AMBIGUOUS,
        "lineage_method": method,
        "lineage_reasons": [LINEAGE_REASON_MULTIPLE_EQUALLY_STRONG_CANDIDATES],
    }


def _resolve_one_relation_lineage(
    evidence_quote: str, claim_records: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Deterministically resolve which of ``claim_records`` (this same
    canonical relation's own source_agent_output's real, segmented,
    Alpha-Mapper-eligible claims) backs ``evidence_quote``. Never uses an
    LLM, never an unbounded semantic embedding, never crosses ticker/run/
    agent boundaries (``claim_records`` is already scoped to exactly one
    source_agent_output_id by the caller)."""
    normalized_quote = _normalize_whitespace(evidence_quote)
    if not normalized_quote:
        return {
            "source_claim_ids": [],
            "lineage_status": LINEAGE_STATUS_UNRESOLVED,
            "lineage_method": LINEAGE_METHOD_NONE,
            "lineage_reasons": [LINEAGE_REASON_SOURCE_CLAIM_NOT_FOUND],
        }

    exact = [c for c in claim_records if str(c.get("claim") or "") == evidence_quote]
    if exact:
        winner = min(exact, key=_lineage_tie_break_key)
        return _lineage_resolved(winner, LINEAGE_METHOD_EXACT)

    normalized_exact = [
        c for c in claim_records if _normalize_whitespace(c.get("claim")) == normalized_quote
    ]
    if normalized_exact:
        winner = min(normalized_exact, key=_lineage_tie_break_key)
        return _lineage_resolved(winner, LINEAGE_METHOD_NORMALIZED_EXACT)

    quote_in_claim = [
        c for c in claim_records if normalized_quote in _normalize_whitespace(c.get("claim"))
    ]
    if quote_in_claim:
        return _resolve_containment(quote_in_claim, LINEAGE_METHOD_CONTAINMENT)

    claim_in_quote = [
        c
        for c in claim_records
        if _normalize_whitespace(c.get("claim")) and _normalize_whitespace(c.get("claim")) in normalized_quote
    ]
    if claim_in_quote:
        return _resolve_containment(claim_in_quote, LINEAGE_METHOD_CONTAINMENT)

    return {
        "source_claim_ids": [],
        "lineage_status": LINEAGE_STATUS_UNRESOLVED,
        "lineage_method": LINEAGE_METHOD_NONE,
        "lineage_reasons": [LINEAGE_REASON_SOURCE_CLAIM_NOT_FOUND],
    }


def resolve_relation_source_claims(
    relations: list[dict[str, Any]],
    claim_records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Attach ``source_claim_ids``/``lineage_status``/``lineage_method``/
    ``lineage_reasons`` to every relation record. ``claim_records`` must
    already be scoped to exactly this one source_agent_output_id's own real,
    Alpha-Mapper-eligible structured claims (never a cross-agent or
    cross-run candidate pool) -- the relation's own ``relation_id`` is never
    used or returned as a substitute claim_id here.

    Only ``validation_status == "accepted"`` relations are ever resolved
    against real claim text; a rejected relation never became a candidate
    edge in the first place, so its lineage is reported as
    ``not_applicable`` rather than spending a lookup on it.
    """
    resolved: list[dict[str, Any]] = []
    for relation in relations:
        if not isinstance(relation, dict):
            resolved.append(relation)
            continue
        if relation.get("validation_status") != "accepted":
            resolved.append(
                {
                    **relation,
                    "source_claim_ids": [],
                    "lineage_status": LINEAGE_STATUS_NOT_APPLICABLE,
                    "lineage_method": LINEAGE_METHOD_NONE,
                    "lineage_reasons": [],
                }
            )
            continue
        lineage = _resolve_one_relation_lineage(
            str(relation.get("evidence_quote") or ""), claim_records
        )
        resolved.append({**relation, **lineage})
    return resolved


def _rejected_record(
    index: int,
    raw: Any,
    reason: str,
    *,
    agent: str,
    run_id: str | None,
    ticker: str | None,
    source_agent_output_id: str | None,
) -> dict[str, Any]:
    raw_dict = raw if isinstance(raw, dict) else {}
    relation_id = "canrel_" + hashlib.sha1(
        f"{source_agent_output_id}:{index}:rejected:{reason}".encode()
    ).hexdigest()[:16]
    return {
        "relation_id": relation_id,
        "run_id": run_id,
        "ticker": ticker,
        "agent": agent,
        "source_agent_output_id": source_agent_output_id,
        "source_factor_id": raw_dict.get("source_factor_id"),
        "source_factor_display_name": None,
        "relation_type": raw_dict.get("relation_type"),
        "relation_display_phrase": None,
        "target_factor_id": raw_dict.get("target_factor_id"),
        "target_factor_display_name": None,
        "canonical_sentence": None,
        "evidence_quote": raw_dict.get("evidence_quote"),
        "assertion_status": raw_dict.get("assertion_status"),
        "confidence": raw_dict.get("confidence"),
        "schema_version": RELATION_BLOCK_SCHEMA_VERSION,
        "taxonomy_version": None,
        "taxonomy_sha256": None,
        "relation_registry_version": None,
        "validation_status": "rejected",
        "validation_rejection_reasons": [reason],
        "extraction_path": "tradingagents_canonical_output",
        "candidate_edge_created": False,
    }


__all__ = [
    "VALID_ASSERTION_STATUSES",
    "ADMISSIBLE_ASSERTION_STATUSES",
    "LINEAGE_STATUS_RESOLVED",
    "LINEAGE_STATUS_UNRESOLVED",
    "LINEAGE_STATUS_AMBIGUOUS",
    "LINEAGE_STATUS_NOT_APPLICABLE",
    "LINEAGE_METHOD_EXACT",
    "LINEAGE_METHOD_NORMALIZED_EXACT",
    "LINEAGE_METHOD_CONTAINMENT",
    "LINEAGE_METHOD_NONE",
    "LINEAGE_REASON_SOURCE_CLAIM_NOT_FOUND",
    "LINEAGE_REASON_MULTIPLE_EQUALLY_STRONG_CANDIDATES",
    "ParsedCanonicalBlock",
    "split_human_text_and_canonical_block",
    "validate_canonical_relations",
    "resolve_relation_source_claims",
]
