"""Week 2 claim-level structure extraction with a deterministic fallback."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from comqutor_alpha.storage.file_store import load_json_record, save_json_record
from comqutor_alpha.structure_engine.claim_quality import (
    CONSUMER_STRUCTURE,
    is_claim_eligible,
)
from comqutor_alpha.structure_engine.claim_semantics import analyze_claim_semantics
from comqutor_alpha.structure_engine.factor_normalizer import (
    extract_known_factors_from_text,
    factor_mention_span,
    normalize_factor_label,
    normalize_text,
    term_in_text,
)
from comqutor_alpha.structure_engine.relation_grammar import (
    CONFLICT_WORDS,
    FORWARD_MULTIWORD_PATTERN,
    FORWARD_TRANSITIVE_CAUSAL_PATTERN,
    FORWARD_TRANSITIVE_SUPPORTIVE_PATTERN,
    REVERSE_MULTIWORD_PATTERN,
    REVERSE_PASSIVE_PATTERN,
    RelationCandidate,
    assertion_status_for,
    extract_relation_candidates,
    match_conflicting,
    plausible_causal_direction,
    relation_confidence,
    relation_reason,
)
from comqutor_alpha.structure_engine.structure_schema import (
    VALID_ASSERTION_STATUSES,
    VALID_EDGE_TYPES,
    clamp_score,
)

SCHEMA_VERSION = "week2.extracted_structures.v2"
EXTRACTOR_VERSION = "week2.structure_extractor.v2"
MAX_LLM_EDGES_PER_CLAIM = 32

# NOTE: CAUSAL_RANK, GROWTH_FACTORS, RISK_FACTORS, CONFLICT_WORDS, and the
# relation pattern/rule definitions now live in relation_grammar.py (the
# Structure Graph Deterministic Relation Grammar Sprint's dedicated,
# priority-ordered rule module); this module imports only what it directly
# uses (see relation_grammar.py for the full rule catalogue and CAUSAL_RANK).


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", normalize_text(value)).strip("_")
    return slug or "unknown"


def _display_label(factor: str, ticker: str | None) -> str:
    if factor == "Revenue Growth" and ticker:
        return f"{str(ticker).upper()} Revenue Growth"
    return factor


def _extract_factors(record: Mapping[str, Any]) -> list[str]:
    factors = []
    for factor in record.get("factors") or []:
        normalized = normalize_factor_label(factor)
        if normalized != "Unknown":
            factors.append(normalized)

    factors.extend(extract_known_factors_from_text(_record_text(record)))

    seen = set()
    result = []
    for factor in factors:
        if factor not in seen:
            result.append(factor)
            seen.add(factor)
    return result


def _has_any(text: str, terms: Iterable[str]) -> bool:
    return any(term_in_text(term, text) for term in terms)


def _source_record_id(record: Mapping[str, Any]) -> str | None:
    value = (
        record.get("claim_id")
        or record.get("agent_output_id")
        or record.get("source_agent_output_id")
    )
    return str(value) if value else None


def _source_agent_output_id(record: Mapping[str, Any]) -> str | None:
    value = record.get("source_agent_output_id")
    if value is None and not record.get("claim_id"):
        value = record.get("agent_output_id")
    return str(value) if value else None


def _record_source_claim_ids(record: Mapping[str, Any]) -> list[str]:
    """The real, segmented claim_id(s) this record's evidence traces back to.

    For an ordinary structured-claim record this is exactly its own
    claim_id (identical to ``_source_record_id``). A canonical-relation
    record instead carries pre-resolved lineage claim_ids (see
    ``canonical_relation_block.resolve_relation_source_claims``) -- its own
    synthetic ``relation_id`` (used as ``claim_id`` for legacy provenance
    display only) is never substituted here.
    """
    explicit = record.get("source_claim_ids")
    if explicit is not None:
        return [str(v) for v in explicit if str(v or "").strip()]
    record_id = _source_record_id(record)
    return [record_id] if record_id else []


def _record_text(record: Mapping[str, Any]) -> str:
    claim = str(record.get("claim") or "").strip()
    evidence = str(record.get("evidence") or "").strip()
    if not evidence or normalize_text(evidence) == normalize_text(claim):
        return claim
    return f"{claim} {evidence}"


def _evidence_text(record: Mapping[str, Any]) -> str:
    return str(record.get("evidence") or record.get("claim") or "").strip()


def _make_node(factor: str, record: Mapping[str, Any]) -> dict[str, Any]:
    ticker = record.get("ticker")
    label = _display_label(factor, ticker)
    return {
        "id": _slug(label),
        "label": label,
        "canonical_factor": factor,
        "node_type": "factor",
        "source_records": [_source_record_id(record)] if _source_record_id(record) else [],
        "source_claim_ids": _record_source_claim_ids(record),
        "source_agent_output_ids": (
            [_source_agent_output_id(record)]
            if _source_agent_output_id(record)
            else []
        ),
        "evidence": [str(record.get("evidence") or record.get("claim") or "")],
        "score": clamp_score(record.get("confidence", 0.0)),
    }


def _merge_node(existing: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    existing["score"] = clamp_score(max(existing.get("score", 0.0), node.get("score", 0.0)))
    for key in ("source_records", "source_claim_ids", "source_agent_output_ids", "evidence"):
        for value in node.get(key, []):
            if value and value not in existing[key]:
                existing[key].append(value)
    return existing


def _edge(
    source_factor: str,
    target_factor: str,
    edge_type: str,
    rule_name: str,
    record: Mapping[str, Any],
    reason: str,
    confidence: float,
    assertion_status: str = "asserted",
    extraction_method: str = "deterministic_rules",
) -> dict[str, Any]:
    ticker = record.get("ticker")
    source_label = _display_label(source_factor, ticker)
    target_label = _display_label(target_factor, ticker)
    claim = str(record.get("claim") or "")
    record_id = _source_record_id(record)
    return {
        "source": _slug(source_label),
        "target": _slug(target_label),
        "source_label": source_label,
        "target_label": target_label,
        "edge_type": edge_type,
        "confidence": clamp_score(confidence),
        "rule_name": rule_name,
        "reason": reason,
        "assertion_status": assertion_status,
        "source_claim": claim,
        "source_record_id": record_id,
        "source_claim_ids": _record_source_claim_ids(record),
        "relation_id": record.get("relation_id"),
        "lineage_status": record.get("lineage_status"),
        "lineage_method": record.get("lineage_method"),
        "lineage_reasons": list(record.get("lineage_reasons") or []),
        "source_agent_output_id": _source_agent_output_id(record),
        "evidence": str(record.get("evidence") or claim),
        "extraction_method": extraction_method,
    }


def _candidate_to_edge(
    candidate: RelationCandidate, text: str, record: Mapping[str, Any]
) -> dict[str, Any]:
    # self-loop / causal-rank / risk-factor-supportive guards are already
    # applied uniformly inside extract_relation_candidates -- every
    # RelationCandidate reaching this point is already admissible.
    status = assertion_status_for(text, candidate.bridge)
    return _edge(
        candidate.source,
        candidate.target,
        candidate.edge_type,
        candidate.rule_name,
        record,
        relation_reason(candidate.edge_type, status, passive=candidate.passive),
        relation_confidence(candidate.edge_type, status),
        status,
    )


def _extract_edges(record: Mapping[str, Any], factors: list[str]) -> list[dict[str, Any]]:
    evidence_text = _evidence_text(record)
    if len(factors) < 2 or not evidence_text:
        return []

    edges = [
        _candidate_to_edge(candidate, evidence_text, record)
        for candidate in extract_relation_candidates(evidence_text, factors)
    ]

    text = normalize_text(evidence_text)
    for risk_factor, growth_factor in match_conflicting(text, factors):
        edges.append(
            _edge(
                risk_factor,
                growth_factor,
                "conflicting",
                "risk_factor_conflicts_with_growth_factor",
                record,
                "A risk factor is contrasted with a growth or demand factor.",
                0.72,
                "mixed",
            )
        )

    return edges


def _llm_relation_is_evidence_backed(
    edge_type: str,
    source_factor: str,
    target_factor: str,
    text: str,
) -> bool:
    if factor_mention_span(source_factor, text) is None:
        return False
    if factor_mention_span(target_factor, text) is None:
        return False
    if edge_type == "causal":
        return bool(
            FORWARD_TRANSITIVE_CAUSAL_PATTERN.search(text)
            or FORWARD_MULTIWORD_PATTERN.search(text)
            or REVERSE_MULTIWORD_PATTERN.search(text)
            or REVERSE_PASSIVE_PATTERN.search(text)
        )
    if edge_type == "supportive":
        return bool(FORWARD_TRANSITIVE_SUPPORTIVE_PATTERN.search(text) or "supported by" in text)
    return _has_any(text, CONFLICT_WORDS)


def _validated_llm_edges(
    payload: Mapping[str, Any],
    record: Mapping[str, Any],
    factors: list[str],
) -> list[dict[str, Any]]:
    raw_edges = payload.get("edges")
    if set(payload) != {"edges"}:
        raise ValueError("structure response has unexpected fields")
    if not isinstance(raw_edges, list) or len(raw_edges) > MAX_LLM_EDGES_PER_CLAIM:
        raise ValueError("edges must be a bounded list")

    allowed = set(factors)
    text = normalize_text(_evidence_text(record))
    semantics = analyze_claim_semantics(text)
    edges = []
    required_fields = {
        "source_factor",
        "target_factor",
        "edge_type",
        "assertion_status",
        "confidence",
    }
    for item in raw_edges:
        if not isinstance(item, Mapping):
            raise ValueError("edge must be an object")
        if set(item) != required_fields:
            raise ValueError("edge fields do not match the strict schema")
        source_factor = normalize_factor_label(item.get("source_factor"))
        target_factor = normalize_factor_label(item.get("target_factor"))
        edge_type = str(item.get("edge_type") or "").strip().lower()
        assertion_status = str(item.get("assertion_status") or "unknown").strip().lower()
        if source_factor not in allowed or target_factor not in allowed:
            raise ValueError("edge factor is outside the deterministic factor set")
        if source_factor == target_factor or edge_type not in VALID_EDGE_TYPES:
            raise ValueError("invalid edge endpoints or type")
        if assertion_status not in VALID_ASSERTION_STATUSES:
            raise ValueError("invalid assertion status")
        try:
            confidence = float(item.get("confidence"))
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid edge confidence") from exc
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("edge confidence must be between zero and one")
        if not _llm_relation_is_evidence_backed(
            edge_type,
            source_factor,
            target_factor,
            text,
        ):
            raise ValueError("edge is not supported by relation evidence")
        if edge_type == "causal" and not plausible_causal_direction(
            source_factor,
            target_factor,
        ):
            raise ValueError("causal edge direction is not admissible")
        if semantics.negated:
            assertion_status = "negated"
        elif semantics.conditional and assertion_status == "asserted":
            assertion_status = "conditional"

        edges.append(
            _edge(
                source_factor,
                target_factor,
                edge_type,
                "llm_relation_validated",
                record,
                "Strict JSON relation passed deterministic evidence validation.",
                confidence,
                assertion_status,
                "llm_strict_json",
            )
        )
    return edges


def _canonical_relation_record(relation: Mapping[str, Any]) -> dict[str, Any]:
    """Adapt one validated TradingAgents-canonical-output relation (see
    canonical_relation_block.validate_canonical_relations) into the same
    lightweight ``record`` mapping shape ``_edge()``/``_make_node()`` already
    expect, so this function never re-implements edge/node construction --
    it only supplies a synthetic, report-level "claim" for it."""
    return {
        "ticker": relation.get("ticker"),
        "claim": relation.get("canonical_sentence") or "",
        "evidence": relation.get("evidence_quote") or "",
        "confidence": relation.get("confidence", 0.0),
        # Kept as ``claim_id`` for legacy provenance/audit display only
        # (``source_record_id`` on the resulting edge/node) -- never treated
        # as a real segmented claim. Real Alpha-Mapper-linkable lineage
        # lives in ``source_claim_ids`` below (see
        # ``canonical_relation_block.resolve_relation_source_claims``).
        "claim_id": relation.get("relation_id"),
        "relation_id": relation.get("relation_id"),
        "source_claim_ids": relation.get("source_claim_ids") or [],
        "lineage_status": relation.get("lineage_status"),
        "lineage_method": relation.get("lineage_method"),
        "lineage_reasons": relation.get("lineage_reasons") or [],
        "source_agent_output_id": relation.get("source_agent_output_id"),
    }


def _canonical_relation_edges_and_nodes(
    canonical_relations: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validated canonical relations become candidate edges directly from
    their already-validated (source_factor_id, relation_type,
    target_factor_id) triple -- never re-parsed from the deterministic
    ``canonical_sentence``, never re-guessed by relation_grammar. Only
    ``candidate_edge_created`` (asserted, never hedged/conditional/
    hypothetical) relations reach this point; every one of them still goes
    through the exact same run-level Graph admission guards as every other
    candidate edge (self-loop/dangling/invalid-type/invalid-weight/
    duplicate-merge in graph_builder.py) -- this function only builds the
    candidate, it never itself decides admission.
    """
    edges: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    for relation in canonical_relations:
        if not isinstance(relation, Mapping) or not relation.get("candidate_edge_created"):
            continue
        source_factor = relation.get("source_factor_id")
        target_factor = relation.get("target_factor_id")
        edge_type = relation.get("relation_type")
        if not source_factor or not target_factor or edge_type not in VALID_EDGE_TYPES:
            continue
        record = _canonical_relation_record(relation)
        edges.append(
            _edge(
                str(source_factor),
                str(target_factor),
                str(edge_type),
                "tradingagents_canonical_relation",
                record,
                "TradingAgents' own existing LLM call reported this relation via the "
                "COMQUTOR Structure Output Contract.",
                relation.get("confidence", 0.0),
                str(relation.get("assertion_status") or "asserted"),
                "tradingagents_canonical_output",
            )
        )
        nodes.append(_make_node(str(source_factor), record))
        nodes.append(_make_node(str(target_factor), record))
    return edges, nodes


def _llm_edges(llm_gateway: Any, record: Mapping[str, Any], factors: list[str]):
    if llm_gateway is None or len(factors) < 2:
        return None
    request = {
        "claim_id": _source_record_id(record),
        "claim": str(record.get("claim") or ""),
        "evidence": str(record.get("evidence") or ""),
        "allowed_factors": factors,
    }

    def validator(payload):
        return _validated_llm_edges(payload, record, factors)

    if getattr(llm_gateway, "semantic_runtime", None) is None or not callable(
        getattr(llm_gateway, "invoke_json_with_trace", None)
    ):
        return llm_gateway.invoke_json("structure_extractor", request, validator)

    invocation = llm_gateway.invoke_json_with_trace(
        "structure_extractor",
        request,
        validator,
    )
    if invocation.validation_accepted and invocation.validated_output:
        llm_gateway.finalize_semantic_invocation(invocation, accepted=True)
        return invocation.validated_output
    llm_gateway.finalize_semantic_invocation(
        invocation,
        accepted=False,
        fallback_reason=(
            invocation.error_code
            or (
                "WEEK2_LLM_EMPTY_RESULT_FALLBACK"
                if invocation.validation_accepted
                else "WEEK2_LLM_STRUCTURE_EXTRACTOR_FALLBACK"
            )
        ),
    )
    return invocation.validated_output if invocation.validation_accepted else None


def extract_structures_from_records(
    records: Iterable[Mapping[str, Any]],
    *,
    llm_gateway: Any = None,
    canonical_relations: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str, str, str | None], dict[str, Any]] = {}
    run_id = None
    ticker = None
    llm_edge_count = 0
    deterministic_edge_count = 0
    canonical_relation_edge_count = 0

    for record in records:
        if not isinstance(record, Mapping):
            continue
        run_id = run_id or record.get("run_id")
        ticker = ticker or record.get("ticker")
        factors = _extract_factors(record)

        extracted_edges = _llm_edges(llm_gateway, record, factors)
        if extracted_edges:
            edges_are_llm_sourced = True
        else:
            extracted_edges = _extract_edges(record, factors)
            edges_are_llm_sourced = False

        # Unified Claim Admissibility Sprint: non_substantive claims never
        # contribute a node or edge; a context_only claim contributes only
        # when relation extraction (just computed above) actually found a
        # legal relation for THIS claim's own evidence and factors -- a bare
        # factual mention alone must not seed a Structure Graph node.
        if not is_claim_eligible(record, CONSUMER_STRUCTURE, has_relation_candidate=bool(extracted_edges)):
            continue

        if edges_are_llm_sourced:
            llm_edge_count += len(extracted_edges)
        else:
            deterministic_edge_count += len(extracted_edges)

        for factor in factors:
            node = _make_node(factor, record)
            if node["id"] in nodes:
                _merge_node(nodes[node["id"]], node)
            else:
                nodes[node["id"]] = node

        for edge in extracted_edges:
            key = (
                edge["source"],
                edge["target"],
                edge["edge_type"],
                edge.get("source_record_id"),
            )
            edges.setdefault(key, edge)

    if canonical_relations:
        canonical_edges, canonical_nodes = _canonical_relation_edges_and_nodes(canonical_relations)
        canonical_relation_edge_count = len(canonical_edges)
        if run_id is None:
            run_id = next((r.get("run_id") for r in canonical_relations if isinstance(r, Mapping) and r.get("run_id")), None)
        if ticker is None:
            ticker = next((r.get("ticker") for r in canonical_relations if isinstance(r, Mapping) and r.get("ticker")), None)

        for node in canonical_nodes:
            if node["id"] in nodes:
                _merge_node(nodes[node["id"]], node)
            else:
                nodes[node["id"]] = node

        for edge in canonical_edges:
            key = (
                edge["source"],
                edge["target"],
                edge["edge_type"],
                edge.get("source_record_id"),
            )
            edges.setdefault(key, edge)

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "nodes": sorted(nodes.values(), key=lambda item: item["id"]),
        "edges": sorted(
            edges.values(),
            key=lambda item: (
                item["edge_type"],
                item["source"],
                item["target"],
                item.get("source_record_id") or "",
            ),
        ),
        "metadata": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "extractor": "llm_with_deterministic_validation_and_fallback",
            "extractor_version": EXTRACTOR_VERSION,
            "llm_enabled": llm_gateway is not None,
            "llm_edge_count": llm_edge_count,
            "deterministic_edge_count": deterministic_edge_count,
            "canonical_relation_edge_count": canonical_relation_edge_count,
        },
    }


def build_extracted_structures_payload(
    structured_payload: Mapping[str, Any],
    *,
    llm_gateway: Any = None,
) -> dict[str, Any]:
    records = structured_payload.get("records", [])
    if not isinstance(records, list):
        records = []
    canonical_relations = structured_payload.get("canonical_relations")
    if not isinstance(canonical_relations, list):
        canonical_relations = None
    payload = extract_structures_from_records(
        records, llm_gateway=llm_gateway, canonical_relations=canonical_relations
    )
    payload["run_id"] = structured_payload.get("run_id") or payload.get("run_id")
    payload["ticker"] = structured_payload.get("ticker") or payload.get("ticker")
    return payload


def save_extracted_structures(
    run_id,
    output_root="outputs/runs",
    *,
    llm_gateway: Any = None,
) -> dict[str, Any]:
    structured_payload = load_json_record(
        run_id,
        "structured_agent_outputs.json",
        output_root=output_root,
    )
    payload = build_extracted_structures_payload(
        structured_payload,
        llm_gateway=llm_gateway,
    )
    save_json_record(run_id, "extracted_structures.json", payload, output_root=output_root)
    return payload
