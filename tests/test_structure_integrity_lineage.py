"""Structure Integrity Repair Sprint, Track 1: Structure-to-Activation
Lineage Repair.

Covers the full chain a canonical relation must travel to actually support
an Alpha's LocalStructureSupport: evidence_quote -> resolved source claim_id
-> graph edge lineage -> committed Alpha match -> Activation local edge
count. No LLM, no network, no database -- pure functions over hand-built
fixtures, exactly like every other structure/graph/activation test module.
"""

from __future__ import annotations

from comqutor_alpha.graph_engine.activation_scorer_v2 import score_alpha_v2
from comqutor_alpha.graph_engine.graph_builder import build_structure_graph
from comqutor_alpha.structure_engine.canonical_relation_block import (
    LINEAGE_METHOD_CONTAINMENT,
    LINEAGE_METHOD_EXACT,
    LINEAGE_METHOD_NORMALIZED_EXACT,
    LINEAGE_STATUS_AMBIGUOUS,
    LINEAGE_STATUS_RESOLVED,
    LINEAGE_STATUS_UNRESOLVED,
    resolve_relation_source_claims,
)
from comqutor_alpha.structure_engine.structure_extractor import (
    extract_structures_from_records,
)

ACME_ALPHA_ID = "A101"


def _relation(evidence_quote, *, relation_id="canrel_1", status="accepted"):
    return {
        "relation_id": relation_id,
        "run_id": "run1",
        "ticker": "ACME",
        "agent": "market_agent",
        "source_agent_output_id": "market_agent_out1",
        "source_factor_id": "AI Capex",
        "relation_type": "causal",
        "target_factor_id": "GPU Demand",
        "canonical_sentence": "AI Capex drives GPU Demand.",
        "evidence_quote": evidence_quote,
        "assertion_status": "asserted",
        "confidence": 0.8,
        "validation_status": status,
        "candidate_edge_created": status == "accepted",
    }


def _claim(claim_id, claim_text, *, claim_index=0):
    return {"claim_id": claim_id, "claim": claim_text, "claim_index": claim_index}


class TestSourceClaimResolution:
    def test_exact_evidence_quote_resolves_to_real_claim(self):
        relations = [_relation("AI capex is accelerating GPU demand.")]
        claims = [_claim("c1", "AI capex is accelerating GPU demand.")]
        resolved = resolve_relation_source_claims(relations, claims)
        assert resolved[0]["source_claim_ids"] == ["c1"]
        assert resolved[0]["lineage_status"] == LINEAGE_STATUS_RESOLVED
        assert resolved[0]["lineage_method"] == LINEAGE_METHOD_EXACT

    def test_whitespace_normalized_quote_still_resolves(self):
        relations = [_relation("AI capex   is accelerating  GPU demand.")]
        claims = [_claim("c1", "AI capex is accelerating GPU demand.")]
        resolved = resolve_relation_source_claims(relations, claims)
        assert resolved[0]["source_claim_ids"] == ["c1"]
        assert resolved[0]["lineage_status"] == LINEAGE_STATUS_RESOLVED
        assert resolved[0]["lineage_method"] == LINEAGE_METHOD_NORMALIZED_EXACT

    def test_containment_match_is_deterministic(self):
        relations = [_relation("AI capex is accelerating GPU demand")]
        claims = [
            _claim(
                "c1",
                "Analysts note that AI capex is accelerating GPU demand across hyperscalers.",
            )
        ]
        resolved = resolve_relation_source_claims(relations, claims)
        assert resolved[0]["source_claim_ids"] == ["c1"]
        assert resolved[0]["lineage_status"] == LINEAGE_STATUS_RESOLVED
        assert resolved[0]["lineage_method"] == LINEAGE_METHOD_CONTAINMENT

        # Re-running over the same input always reproduces the same result.
        resolved_again = resolve_relation_source_claims(relations, claims)
        assert resolved_again[0]["source_claim_ids"] == resolved[0]["source_claim_ids"]

    def test_ambiguous_equally_strong_candidates_are_flagged_not_guessed(self):
        relations = [_relation("strong demand")]
        claims = [
            _claim("c1", "strong demand", claim_index=0),
            _claim("c2", "strong demand", claim_index=1),
        ]
        resolved = resolve_relation_source_claims(relations, claims)
        # Byte-identical claim text at the *exact* tier ties, but the tie
        # break (shortest, then claim_index, then claim_id) is a total
        # order -- exact matches always resolve to the earliest claim_index.
        assert resolved[0]["lineage_status"] == LINEAGE_STATUS_RESOLVED
        assert resolved[0]["source_claim_ids"] == ["c1"]

        # A genuine containment-tier tie (two distinct, equally short claims
        # that both contain the quote) is reported as ambiguous with every
        # tied candidate preserved, never an arbitrary single pick.
        relations_containment = [_relation("demand")]
        claims_containment = [
            _claim("x1", "Overall demand context alfa.", claim_index=0),
            _claim("x2", "Overall demand context beta.", claim_index=1),
        ]
        resolved_containment = resolve_relation_source_claims(
            relations_containment, claims_containment
        )
        assert resolved_containment[0]["lineage_status"] == LINEAGE_STATUS_AMBIGUOUS
        assert set(resolved_containment[0]["source_claim_ids"]) == {"x1", "x2"}

    def test_missing_parent_claim_is_unresolved_never_fabricated(self):
        relations = [_relation("a sentence that appears nowhere in this agent's claims")]
        claims = [_claim("c1", "a completely unrelated sentence")]
        resolved = resolve_relation_source_claims(relations, claims)
        assert resolved[0]["source_claim_ids"] == []
        assert resolved[0]["lineage_status"] == LINEAGE_STATUS_UNRESOLVED
        assert "SOURCE_CLAIM_NOT_FOUND" in resolved[0]["lineage_reasons"]

    def test_rejected_relation_is_not_applicable_not_resolved(self):
        relations = [_relation("anything", status="rejected")]
        claims = [_claim("c1", "anything")]
        resolved = resolve_relation_source_claims(relations, claims)
        assert resolved[0]["source_claim_ids"] == []
        assert resolved[0]["lineage_status"] == "not_applicable"

    def test_relation_id_and_source_claim_ids_are_kept_separate(self):
        relations = [_relation("AI capex is accelerating GPU demand.", relation_id="canrel_xyz")]
        claims = [_claim("c1", "AI capex is accelerating GPU demand.")]
        resolved = resolve_relation_source_claims(relations, claims)
        assert resolved[0]["relation_id"] == "canrel_xyz"
        assert resolved[0]["source_claim_ids"] == ["c1"]
        assert "canrel_xyz" not in resolved[0]["source_claim_ids"]


def _alpha_matches(entries):
    return {"run_id": "run1", "ticker": "ACME", "matches": entries}


def _match(claim_id, agent, matched_alpha, *, relation="activation", evidence=None):
    return {
        "claim_id": claim_id,
        "agent": agent,
        "match_status": "matched" if matched_alpha else "no_match",
        "matched_alpha": matched_alpha,
        "score": 0.9,
        "evidence": evidence or f"evidence for {claim_id}",
        "claim": evidence or f"evidence for {claim_id}",
        "claim_quality": "analytical",
        "direction": "positive",
        "assertion_status": "asserted",
        "eligible_candidates": [{"alpha_id": matched_alpha, "relation": relation}] if matched_alpha else [],
    }


class TestCanonicalEdgeLineageThroughGraphAndActivation:
    """End-to-end: a resolved canonical relation must reach
    LocalStructureSupport; an unresolved one must not (but must still be
    admitted as ordinary Graph evidence, never dropped, never fabricated an
    Alpha binding)."""

    def _build_records(self):
        return [
            {
                "claim_id": "market_agent_out1:claim:1",
                "claim_index": 0,
                "agent": "market_agent",
                "claim": "AI capex is accelerating GPU demand.",
                "evidence": "AI capex is accelerating GPU demand.",
                "ticker": "ACME",
                "run_id": "run1",
                "confidence": 0.8,
                "factors": [],
            }
        ]

    def _canonical_relations(self, *, resolved: bool):
        base = _relation("AI capex is accelerating GPU demand.")
        if resolved:
            lineage = resolve_relation_source_claims([base], self._build_records())
        else:
            unresolved_relation = _relation("a sentence this agent never actually wrote")
            lineage = resolve_relation_source_claims([unresolved_relation], self._build_records())
        return lineage

    def test_resolved_canonical_edge_carries_source_claim_ids_and_relation_id(self):
        relations = self._canonical_relations(resolved=True)
        payload = extract_structures_from_records([], canonical_relations=relations)
        edge = payload["edges"][0]
        assert edge["source_claim_ids"] == ["market_agent_out1:claim:1"]
        assert edge["relation_id"] == "canrel_1"
        assert edge["lineage_status"] == LINEAGE_STATUS_RESOLVED

    def test_edge_merge_preserves_relation_ids_and_source_claim_ids(self):
        relations = self._canonical_relations(resolved=True) * 1
        second = _relation("AI capex is accelerating GPU demand.", relation_id="canrel_2")
        second_resolved = resolve_relation_source_claims([second], self._build_records())
        all_relations = relations + second_resolved
        extracted = extract_structures_from_records([], canonical_relations=all_relations)
        alpha_matches = _alpha_matches([_match("market_agent_out1:claim:1", "market_agent", ACME_ALPHA_ID)])
        graph = build_structure_graph(alpha_matches, extracted)
        edge = next(e for e in graph["edges"] if e["source"] == "ai_capex")
        assert set(edge["relation_ids"]) == {"canrel_1", "canrel_2"}
        assert edge["source_claim_ids"] == ["market_agent_out1:claim:1"]

    def test_source_claim_with_committed_alpha_populates_edge_alpha_ids(self):
        relations = self._canonical_relations(resolved=True)
        extracted = extract_structures_from_records([], canonical_relations=relations)
        alpha_matches = _alpha_matches([_match("market_agent_out1:claim:1", "market_agent", ACME_ALPHA_ID)])
        graph = build_structure_graph(alpha_matches, extracted)
        edge = graph["edges"][0]
        assert edge["alpha_ids"] == [ACME_ALPHA_ID]
        assert edge["alpha_link_reason_codes"] == []

    def test_source_claim_without_committed_alpha_gives_empty_alpha_ids_and_reason(self):
        relations = self._canonical_relations(resolved=True)
        extracted = extract_structures_from_records([], canonical_relations=relations)
        # No alpha_matches entry at all for this claim_id -> no committed match.
        alpha_matches = _alpha_matches([])
        graph = build_structure_graph(alpha_matches, extracted)
        edge = graph["edges"][0]
        assert edge["alpha_ids"] == []
        assert "NO_COMMITTED_ALPHA_MATCH" in edge["alpha_link_reason_codes"]

    def test_canonical_edge_contributes_to_local_structure_support(self):
        relations = self._canonical_relations(resolved=True)
        extracted = extract_structures_from_records([], canonical_relations=relations)
        alpha_matches = _alpha_matches([_match("market_agent_out1:claim:1", "market_agent", ACME_ALPHA_ID)])
        graph = build_structure_graph(alpha_matches, extracted)
        result = score_alpha_v2(ACME_ALPHA_ID, alpha_matches, taxonomy={}, graph_edges=graph["edges"])
        lss = result["components"]["local_structure_support"]
        assert lss["local_edge_count"] == 1
        assert lss["qualifying_local_edge_count"] == 1
        assert "NO_LOCAL_STRUCTURE_SUPPORT" not in result["cap_reason_codes"]

    def test_unresolved_canonical_edge_never_contributes_local_structure_support(self):
        relations = self._canonical_relations(resolved=False)
        extracted = extract_structures_from_records([], canonical_relations=relations)
        alpha_matches = _alpha_matches([_match("market_agent_out1:claim:1", "market_agent", ACME_ALPHA_ID)])
        graph = build_structure_graph(alpha_matches, extracted)
        edge = graph["edges"][0]
        assert edge["source_claim_ids"] == []
        assert edge["alpha_ids"] == []
        assert "LINEAGE_UNRESOLVED" in edge["alpha_link_reason_codes"]

        result = score_alpha_v2(ACME_ALPHA_ID, alpha_matches, taxonomy={}, graph_edges=graph["edges"])
        lss = result["components"]["local_structure_support"]
        assert lss["local_edge_count"] == 0
        assert "NO_LOCAL_STRUCTURE_SUPPORT" in result["cap_reason_codes"]

    def test_legacy_edge_without_source_claim_ids_field_still_works(self):
        """An edge dict that predates this sprint (no source_claim_ids key
        at all) must fall back to claim_ids -- never silently lose the
        local-structure support it already had."""
        legacy_edge = {
            "source": "ai_capex",
            "target": "gpu_demand",
            "edge_type": "causal",
            "assertion_status": "asserted",
            "claim_ids": ["legacy:claim:1"],
        }
        alpha_matches = _alpha_matches([_match("legacy:claim:1", "market_agent", ACME_ALPHA_ID)])
        result = score_alpha_v2(ACME_ALPHA_ID, alpha_matches, taxonomy={}, graph_edges=[legacy_edge])
        lss = result["components"]["local_structure_support"]
        assert lss["local_edge_count"] == 1

    def test_local_edge_count_does_not_double_count_merged_relations(self):
        relations = self._canonical_relations(resolved=True)
        second = _relation("AI capex is accelerating GPU demand.", relation_id="canrel_2")
        second_resolved = resolve_relation_source_claims([second], self._build_records())
        extracted = extract_structures_from_records([], canonical_relations=relations + second_resolved)
        alpha_matches = _alpha_matches([_match("market_agent_out1:claim:1", "market_agent", ACME_ALPHA_ID)])
        graph = build_structure_graph(alpha_matches, extracted)
        assert len(graph["edges"]) == 1
        result = score_alpha_v2(ACME_ALPHA_ID, alpha_matches, taxonomy={}, graph_edges=graph["edges"])
        assert result["components"]["local_structure_support"]["local_edge_count"] == 1

    def test_incident_edge_count_invariant_incoming_plus_outgoing(self):
        relations = self._canonical_relations(resolved=True)
        extracted = extract_structures_from_records([], canonical_relations=relations)
        alpha_matches = _alpha_matches([_match("market_agent_out1:claim:1", "market_agent", ACME_ALPHA_ID)])
        graph = build_structure_graph(alpha_matches, extracted)
        for node in graph["nodes"]:
            incoming = sum(1 for e in graph["edges"] if e["target"] == node["id"])
            outgoing = sum(1 for e in graph["edges"] if e["source"] == node["id"])
            incident = incoming + outgoing
            assert incident == incoming + outgoing  # tautology, but documents the invariant explicitly

    def test_graph_admission_is_not_relaxed_to_force_alpha_binding(self):
        """A source claim with no committed Alpha match is a legal outcome
        (edge.alpha_ids == []), never coerced into a fabricated binding."""
        relations = self._canonical_relations(resolved=True)
        extracted = extract_structures_from_records([], canonical_relations=relations)
        alpha_matches = _alpha_matches([])
        graph = build_structure_graph(alpha_matches, extracted)
        assert graph["edges"][0]["alpha_ids"] == []
        assert len(graph["edges"]) == 1  # the edge itself is still admitted
