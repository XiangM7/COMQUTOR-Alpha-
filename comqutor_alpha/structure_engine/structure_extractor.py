"""Deterministic Week 2 structure extraction from structured claim records."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from comqutor_alpha.storage.file_store import load_json_record, save_json_record
from comqutor_alpha.structure_engine.claim_semantics import analyze_claim_semantics
from comqutor_alpha.structure_engine.factor_normalizer import (
    extract_known_factors_from_text,
    factor_mention_span,
    normalize_factor_label,
    normalize_text,
    term_in_text,
)
from comqutor_alpha.structure_engine.structure_schema import clamp_score


SCHEMA_VERSION = "week2.extracted_structures.v1"

CONFLICT_WORDS = (
    "but",
    "however",
    "despite",
    "although",
    "while",
    "yet",
    "offset",
    "conflict",
    "downside risk",
)
ACTIVE_CAUSAL_PATTERN = re.compile(
    r"\b(drive|drives|raise|raises|boost|boosts|fuel|fuels|lead to|leads to|"
    r"push|pushes|increase|increases|expand|expands)\b"
)
ACTIVE_SUPPORT_PATTERN = re.compile(
    r"\b(support|supports|reinforce|reinforces|confirm|confirms|help|helps)\b"
)
PASSIVE_RELATION_PATTERN = re.compile(
    r"\b(?:is|are|was|were|be|been|being)\s+"
    r"(?P<verb>driven|raised|boosted|increased|supported|reinforced)\s+by\b"
)
NEGATED_RELATION_PATTERN = re.compile(
    r"\b(no|not|never|does not|do not|did not|fails? to|failed to|without)\b"
)
CONDITIONAL_MODAL_PATTERN = re.compile(r"\b(could|may|might|would)\b")

# Broad causal ordering avoids a brittle list of exact pairs while still
# refusing economically reversed edges such as GPU Demand -> AI Demand.
CAUSAL_RANK = {
    "AI Demand": 1,
    "AI CapEx": 1,
    "Inference Demand": 1,
    "Rate Cut Cycle": 1,
    "Liquidity Expansion": 1,
    "Semiconductor Cycle": 1,
    "Datacenter CapEx": 2,
    "AI Infrastructure": 2,
    "GPU Demand": 2,
    "Narrative Momentum": 2,
    "Revenue Growth": 3,
    "Valuation Risk": 3,
    "Recession Risk": 3,
}
GROWTH_FACTORS = {
    "AI Demand",
    "AI CapEx",
    "GPU Demand",
    "Revenue Growth",
    "Liquidity Expansion",
    "Narrative Momentum",
    "Semiconductor Cycle",
    "Inference Demand",
}
RISK_FACTORS = {"Valuation Risk", "Recession Risk"}


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

    factors.extend(extract_known_factors_from_text(record.get("claim")))

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
    value = record.get("source_agent_output_id") or record.get("agent_output_id")
    return str(value) if value else None


def _make_node(factor: str, record: Mapping[str, Any]) -> dict[str, Any]:
    ticker = record.get("ticker")
    label = _display_label(factor, ticker)
    return {
        "id": _slug(label),
        "label": label,
        "canonical_factor": factor,
        "node_type": "factor",
        "source_records": [_source_record_id(record)] if _source_record_id(record) else [],
        "evidence": [str(record.get("claim") or "")],
        "score": clamp_score(record.get("confidence", 0.0)),
    }


def _merge_node(existing: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    existing["score"] = clamp_score(max(existing.get("score", 0.0), node.get("score", 0.0)))
    for key in ("source_records", "evidence"):
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
        "source_agent_output_id": record.get("source_agent_output_id"),
    }


def _plausible_causal_direction(source: str, target: str) -> bool:
    source_rank = CAUSAL_RANK.get(source)
    target_rank = CAUSAL_RANK.get(target)
    return source_rank is not None and target_rank is not None and source_rank < target_rank


def _assertion_status(text: str, bridge: str) -> str:
    if NEGATED_RELATION_PATTERN.search(bridge):
        return "negated"
    semantics = analyze_claim_semantics(text)
    if semantics.conditional:
        return "conditional"
    return "asserted"


def _relation_confidence(edge_type: str, assertion_status: str) -> float:
    if assertion_status == "negated":
        return 0.35
    if assertion_status == "conditional":
        return 0.58
    return 0.84 if edge_type == "causal" else 0.68


def _relation_reason(edge_type: str, assertion_status: str, passive: bool = False) -> str:
    voice = "passive" if passive else "active"
    article = "an" if voice == "active" else "a"
    if assertion_status == "negated":
        return f"The claim explicitly negates {article} {voice} {edge_type} relation."
    if assertion_status == "conditional":
        return f"The claim states a conditional {voice} {edge_type} relation."
    return f"The claim states an asserted {voice} {edge_type} relation."


def _extract_edges(record: Mapping[str, Any], factors: list[str]) -> list[dict[str, Any]]:
    text = normalize_text(record.get("claim"))
    if len(factors) < 2 or not text:
        return []

    edges = []
    mentions = []
    for factor in factors:
        span = factor_mention_span(factor, text)
        if span is not None:
            mentions.append((factor, span[0], span[1]))
    mentions.sort(key=lambda item: item[1])

    for left_index, (left_factor, _left_start, left_end) in enumerate(mentions):
        for right_factor, right_start, _right_end in mentions[left_index + 1 :]:
            bridge = text[left_end:right_start]
            passive_match = PASSIVE_RELATION_PATTERN.search(bridge)
            if passive_match:
                source, target = right_factor, left_factor
                verb = passive_match.group("verb")
                edge_type = "supportive" if verb in {"supported", "reinforced"} else "causal"
                if edge_type == "causal" and not _plausible_causal_direction(source, target):
                    continue
                status = _assertion_status(text, bridge)
                edges.append(
                    _edge(
                        source,
                        target,
                        edge_type,
                        "passive_relation_between_factors",
                        record,
                        _relation_reason(edge_type, status, passive=True),
                        _relation_confidence(edge_type, status),
                        status,
                    )
                )
                continue

            relation_matches = [
                (match.start(), "causal") for match in ACTIVE_CAUSAL_PATTERN.finditer(bridge)
            ]
            relation_matches.extend(
                (match.start(), "supportive")
                for match in ACTIVE_SUPPORT_PATTERN.finditer(bridge)
            )
            if relation_matches:
                _position, edge_type = max(relation_matches, key=lambda item: item[0])
                if edge_type == "causal" and not _plausible_causal_direction(
                    left_factor, right_factor
                ):
                    continue
                if edge_type == "supportive" and (
                    left_factor in RISK_FACTORS or right_factor in RISK_FACTORS
                ):
                    continue
                status = _assertion_status(text, bridge)
                edges.append(
                    _edge(
                        left_factor,
                        right_factor,
                        edge_type,
                        f"active_{edge_type}_between_factors",
                        record,
                        _relation_reason(edge_type, status),
                        _relation_confidence(edge_type, status),
                        status,
                    )
                )
                continue

            semantics = analyze_claim_semantics(text)
            if (
                semantics.conditional
                and text.startswith("if ")
                and CONDITIONAL_MODAL_PATTERN.search(text[right_start:])
                and _plausible_causal_direction(left_factor, right_factor)
            ):
                edges.append(
                    _edge(
                        left_factor,
                        right_factor,
                        "causal",
                        "if_then_relation_between_factors",
                        record,
                        _relation_reason("causal", "conditional"),
                        _relation_confidence("causal", "conditional"),
                        "conditional",
                    )
                )

    if _has_any(text, CONFLICT_WORDS):
        for risk_factor in [factor for factor in factors if factor in RISK_FACTORS]:
            for growth_factor in [factor for factor in factors if factor in GROWTH_FACTORS]:
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


def extract_structures_from_records(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str, str, str | None], dict[str, Any]] = {}
    run_id = None
    ticker = None

    for record in records:
        if not isinstance(record, Mapping):
            continue
        run_id = run_id or record.get("run_id")
        ticker = ticker or record.get("ticker")
        factors = _extract_factors(record)
        for factor in factors:
            node = _make_node(factor, record)
            if node["id"] in nodes:
                _merge_node(nodes[node["id"]], node)
            else:
                nodes[node["id"]] = node

        for edge in _extract_edges(record, factors):
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
            key=lambda item: (item["edge_type"], item["source"], item["target"]),
        ),
        "metadata": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "extractor": "deterministic_week2_rules",
            "extractor_version": "week2.relation_semantics.v2",
        },
    }


def build_extracted_structures_payload(structured_payload: Mapping[str, Any]) -> dict[str, Any]:
    records = structured_payload.get("records", [])
    if not isinstance(records, list):
        records = []
    payload = extract_structures_from_records(records)
    payload["run_id"] = structured_payload.get("run_id") or payload.get("run_id")
    payload["ticker"] = structured_payload.get("ticker") or payload.get("ticker")
    return payload


def save_extracted_structures(run_id, output_root="outputs/runs") -> dict[str, Any]:
    structured_payload = load_json_record(
        run_id,
        "structured_agent_outputs.json",
        output_root=output_root,
    )
    payload = build_extracted_structures_payload(structured_payload)
    save_json_record(run_id, "extracted_structures.json", payload, output_root=output_root)
    return payload
