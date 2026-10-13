"""Negation and condition of a TradingAgents canonical relation, read from its own evidence quote, under
``alpha_evidence_consumption.v2`` (2026-10-13).

The canonical-relation validator (``structure_engine.canonical_relation_block``) trusts the agent's own ``assertion_status``, and
Week 2 creates an ``asserted`` candidate edge for every relation the agent declared asserted. The saved NVDA run shows the agent
mapping "A no-cut regime means discount rates stay elevated, which mechanically compresses ..." to
``Rate Cut Cycle -causal-> Valuation Risk``: the graph then states that a rate-cut cycle causes valuation risk -- a cut that the
statement says is NOT happening. Under the contract, Week 3 re-reads every canonical relation's quote before building the graph:

* an endpoint factor the quote negates ("no-cut regime", "no rate cuts", "will not cut") -> ``EVIDENCE_NEGATES_<SOURCE|TARGET>``;
* a quote carrying the text rule's own conditional markers (if / unless / could / may / might / would / potentially) ->
  ``EVIDENCE_CONDITIONAL`` (the canonical contract admits only asserted relations as edges).

Such a relation is withheld from the graph (subtract only: no edge is ever added or re-typed, and the saved Week 2 artifacts are
never rewritten). Every decision -- withheld or kept -- is reported with its quote, so the change is traceable. The graph has no
"negated factor" node, so representing the statement correctly would need a new graph vocabulary; withholding is the minimal
change that stops the graph from asserting the opposite of the evidence.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from comqutor_alpha.structure_engine.claim_semantics import _CONDITIONAL_PATTERN
from comqutor_alpha.structure_engine.factor_normalizer import normalize_text

CANONICAL_EDGE_SCOPE_POLICY_VERSION = "canonical_edge_scope.v1"
CANONICAL_RULE_NAME = "tradingagents_canonical_relation"

REASON_NEGATES_SOURCE = "EVIDENCE_NEGATES_SOURCE_FACTOR"
REASON_NEGATES_TARGET = "EVIDENCE_NEGATES_TARGET_FACTOR"
REASON_CONDITIONAL = "EVIDENCE_CONDITIONAL"

_NEGATORS = frozenset({"no", "not", "zero", "without", "never", "non"})
_CONTRACTION_STEMS = frozenset({"won", "don", "doesn", "didn", "isn", "aren", "wasn", "weren", "can", "couldn", "wouldn", "shouldn"})
# words of a display name that name the kind of factor rather than the factor itself
_GENERIC_WORDS = frozenset({"cycle", "risk", "regime", "level", "trend", "the", "and", "of"})


def _endpoint_terms(display_name: Any, factor_id: Any) -> list[str]:
    name = normalize_text(display_name or str(factor_id or "").replace("_", " "))
    words = [w for w in name.split() if len(w) >= 3 and w not in _GENERIC_WORDS]
    return sorted({name, *words} - {""}, key=lambda term: (-len(term), term))


def _negated_occurrence(tokens: list[str], term: str) -> bool:
    """True when an occurrence of ``term`` is directly negated: a negator one or two tokens before it ("no cut", "not a cut",
    "no rate cut", "won t cut"), never "not only"."""
    words = term.split()
    for index in range(len(tokens) - len(words) + 1):
        if tokens[index:index + len(words)] != words:
            continue
        for back in (1, 2):
            position = index - back
            if position < 0:
                break
            token = tokens[position]
            if token in _NEGATORS and tokens[position + 1] != "only":
                return True
            if token == "t" and position > 0 and tokens[position - 1] in _CONTRACTION_STEMS:
                return True
    return False


def relation_scope(relation: Mapping[str, Any]) -> dict[str, Any]:
    """The decision for one accepted canonical relation: withheld, with its reasons, or kept."""
    quote = str(relation.get("evidence_quote") or "")
    normalized = normalize_text(quote)
    tokens = normalized.split()
    reasons: list[str] = []
    negated_endpoints: list[str] = []
    for side, reason in (("source", REASON_NEGATES_SOURCE), ("target", REASON_NEGATES_TARGET)):
        terms = _endpoint_terms(relation.get(f"{side}_factor_display_name"), relation.get(f"{side}_factor_id"))
        negated = [term for term in terms if _negated_occurrence(tokens, term)]
        if negated:
            reasons.append(reason)
            negated_endpoints.append(f"{relation.get(f'{side}_factor_id')}:{negated[0]}")
    conditional_markers = sorted({m.group(0) for m in _CONDITIONAL_PATTERN.finditer(normalized)})
    if conditional_markers:
        reasons.append(REASON_CONDITIONAL)
    return {
        "relation_id": relation.get("relation_id"),
        "source_factor_id": relation.get("source_factor_id"),
        "relation_type": relation.get("relation_type"),
        "target_factor_id": relation.get("target_factor_id"),
        "evidence_quote": quote,
        "withheld": bool(reasons),
        "reasons": reasons,
        "negated_endpoints": negated_endpoints,
        "conditional_markers": conditional_markers,
    }


def apply_canonical_edge_scope(
    extracted_structures_payload: Mapping[str, Any], canonical_relations: Sequence[Mapping[str, Any]] | None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """A copy of the extracted structures without the canonical edges whose relation is withheld, and the run-level report.

    Only edges built by the canonical-relation rule are ever removed; a factor node is dropped only when every record it came
    from is a withheld relation. The input payload is not modified."""
    payload = copy.deepcopy(dict(extracted_structures_payload))
    decisions = [
        relation_scope(relation)
        for relation in canonical_relations or ()
        if isinstance(relation, Mapping) and relation.get("candidate_edge_created") and relation.get("relation_id")
    ]
    withheld_ids = {d["relation_id"] for d in decisions if d["withheld"]}
    edges = payload.get("edges") if isinstance(payload.get("edges"), list) else []
    kept_edges = [
        edge for edge in edges
        if not (isinstance(edge, Mapping) and edge.get("rule_name") == CANONICAL_RULE_NAME and edge.get("relation_id") in withheld_ids)
    ]
    removed_edges = len(edges) - len(kept_edges)
    payload["edges"] = kept_edges
    nodes = payload.get("nodes") if isinstance(payload.get("nodes"), list) else []
    kept_nodes = []
    for node in nodes:
        records = node.get("source_records") if isinstance(node, Mapping) else None
        if isinstance(records, list) and records and all(str(r) in withheld_ids for r in records):
            continue
        kept_nodes.append(node)
    payload["nodes"] = kept_nodes
    summary = {
        "policy": CANONICAL_EDGE_SCOPE_POLICY_VERSION,
        "canonical_relations_checked": len(decisions),
        "withheld_relation_count": len(withheld_ids),
        "withheld_candidate_edges": removed_edges,
        "withheld_nodes": len(nodes) - len(kept_nodes),
        "withheld": [d for d in decisions if d["withheld"]],
        "kept_relation_ids": sorted(d["relation_id"] for d in decisions if not d["withheld"]),
    }
    return payload, summary
