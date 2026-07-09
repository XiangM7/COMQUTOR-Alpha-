"""Deterministic Week 2 structure extraction from structured claim records."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from comqutor_alpha.storage.file_store import load_json_record, save_json_record
from comqutor_alpha.structure_engine.alpha_mapper import FACTOR_ALIASES, normalize_text
from comqutor_alpha.structure_engine.structure_schema import clamp_score


SCHEMA_VERSION = "week2.extracted_structures.v1"

CAUSAL_WORDS = (
    "drive",
    "drives",
    "driven",
    "increase",
    "increases",
    "raise",
    "raises",
    "boost",
    "boosts",
    "fuel",
    "fuels",
    "lead to",
    "leads to",
    "push",
    "pushes",
    "expand",
    "expands",
)
SUPPORT_WORDS = ("support", "supports", "reinforce", "reinforces", "confirm", "confirms", "helps")
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

CAUSAL_FACTOR_RULES = (
    ("AI Demand", "GPU Demand", "ai_demand_to_gpu_demand"),
    ("AI CapEx", "GPU Demand", "ai_capex_to_gpu_demand"),
    ("GPU Demand", "Revenue Growth", "gpu_demand_to_revenue_growth"),
)
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


def _term_in_text(term: str, text: str) -> bool:
    term = normalize_text(term)
    if not term:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None


def normalize_factor_label(value: Any) -> str:
    text = normalize_text(value)
    if not text:
        return "Unknown"
    for factor, aliases in FACTOR_ALIASES.items():
        terms = (factor, *aliases)
        if any(normalize_text(term) == text for term in terms):
            return factor
    return " ".join(part.capitalize() for part in text.split())


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

    text = normalize_text(record.get("claim"))
    for factor, aliases in FACTOR_ALIASES.items():
        if any(_term_in_text(alias, text) for alias in aliases):
            factors.append(factor)

    seen = set()
    result = []
    for factor in factors:
        if factor not in seen:
            result.append(factor)
            seen.add(factor)
    return result


def _has_any(text: str, terms: Iterable[str]) -> bool:
    return any(_term_in_text(term, text) for term in terms)


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
        "source_claim": claim,
        "source_record_id": record_id,
        "source_agent_output_id": record.get("source_agent_output_id"),
    }


def _extract_edges(record: Mapping[str, Any], factors: list[str]) -> list[dict[str, Any]]:
    text = normalize_text(record.get("claim"))
    if len(factors) < 2 or not text:
        return []

    edges = []
    has_causal_language = _has_any(text, CAUSAL_WORDS)
    for source, target, rule_name in CAUSAL_FACTOR_RULES:
        if source in factors and target in factors and has_causal_language:
            edges.append(
                _edge(
                    source,
                    target,
                    "causal",
                    rule_name,
                    record,
                    f"{source} and {target} appear with causal language.",
                    0.82,
                )
            )

    if _has_any(text, SUPPORT_WORDS):
        causal_pairs = {(edge["source_label"], edge["target_label"]) for edge in edges}
        for index, source in enumerate(factors):
            for target in factors[index + 1 :]:
                source_label = _display_label(source, record.get("ticker"))
                target_label = _display_label(target, record.get("ticker"))
                if (source_label, target_label) in causal_pairs:
                    continue
                if source in RISK_FACTORS or target in RISK_FACTORS:
                    continue
                edges.append(
                    _edge(
                        source,
                        target,
                        "supportive",
                        "supportive_language_between_factors",
                        record,
                        "Factors appear with supportive language.",
                        0.66,
                    )
                )
                break

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
