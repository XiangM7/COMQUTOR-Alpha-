import json

import pytest

from comqutor_alpha.structure_engine.structure_extractor import (
    extract_structures_from_records,
    normalize_factor_label,
    save_extracted_structures,
)


def _record(claim, factors=None, confidence=0.8, *, claim_id=None, raw_id=None, evidence=None):
    raw_id = raw_id or f"source:{abs(hash(claim))}"
    return {
        "run_id": "run1",
        "ticker": "NVDA",
        "agent": "news_agent",
        "claim": claim,
        "evidence": evidence or claim,
        "entities": ["NVDA"],
        "factors": factors or [],
        "direction": "positive",
        "confidence": confidence,
        "claim_id": claim_id or f"{raw_id}:claim:1",
        "agent_output_id": claim_id or f"{raw_id}:claim:1",
        "source_agent_output_id": raw_id,
    }


def _has_edge(payload, source_label, target_label, edge_type):
    return any(
        edge["source_label"] == source_label
        and edge["target_label"] == target_label
        and edge["edge_type"] == edge_type
        for edge in payload["edges"]
    )


def test_extracts_ai_demand_to_gpu_demand_edge():
    payload = extract_structures_from_records(
        [_record("AI demand drives GPU demand as model training expands.")]
    )

    assert _has_edge(payload, "AI Demand", "GPU Demand", "causal")


def test_extracts_ai_capex_to_gpu_demand_edge():
    payload = extract_structures_from_records(
        [_record("Hyperscaler AI capex raises GPU demand for accelerator clusters.")]
    )

    assert _has_edge(payload, "AI CapEx", "GPU Demand", "causal")


def test_extracts_gpu_demand_to_nvda_revenue_growth_edge():
    payload = extract_structures_from_records(
        [_record("GPU demand drives revenue growth at NVDA as customer orders rise.")]
    )

    assert _has_edge(payload, "GPU Demand", "NVDA Revenue Growth", "causal")


def test_extracts_supportive_edge():
    payload = extract_structures_from_records(
        [_record("Liquidity expansion supports narrative momentum in AI stocks.")]
    )

    assert _has_edge(payload, "Liquidity Expansion", "Narrative Momentum", "supportive")


def test_extracts_conflicting_edge():
    payload = extract_structures_from_records(
        [_record("AI demand is strong, but rich valuation creates downside risk.")]
    )

    assert _has_edge(payload, "Valuation Risk", "AI Demand", "conflicting")


def test_duplicate_factor_normalization_merges_nodes():
    payload = extract_structures_from_records(
        [
            _record("AI demand is improving.", factors=["AI demand"]),
            _record(
                "Artificial intelligence demand is improving.",
                factors=["artificial intelligence demand"],
            ),
        ]
    )
    labels = [node["label"] for node in payload["nodes"]]

    assert normalize_factor_label("artificial intelligence demand") == "AI Demand"
    assert labels.count("AI Demand") == 1


def test_ambiguous_text_does_not_hallucinate_causal_edge():
    payload = extract_structures_from_records(
        [_record("AI demand and GPU demand are both mentioned without a clear relationship.")]
    )

    assert payload["nodes"]
    assert payload["edges"] == []


def test_reversed_causal_phrasing_does_not_emit_wrong_direction_edge():
    """"GPU demand drives AI demand" mentions both factors plus causal
    language ("drives"), but in the reversed order from the canonical
    AI Demand -> GPU Demand rule. The extractor must not emit that edge
    (in either direction) rather than hallucinate the canonical direction.
    """
    payload = extract_structures_from_records(
        [_record("GPU demand drives AI demand as model usage rises.")]
    )

    assert not _has_edge(payload, "AI Demand", "GPU Demand", "causal")
    assert not _has_edge(payload, "GPU Demand", "AI Demand", "causal")
    labels = {node["label"] for node in payload["nodes"]}
    assert labels == {"AI Demand", "GPU Demand"}


def test_extracts_passive_causal_relation_in_canonical_direction():
    payload = extract_structures_from_records(
        [_record("GPU demand is driven by AI capex.")]
    )

    edge = next(edge for edge in payload["edges"] if edge["edge_type"] == "causal")
    assert edge["source_label"] == "AI CapEx"
    assert edge["target_label"] == "GPU Demand"
    assert edge["assertion_status"] == "asserted"


def test_conditional_causal_relation_is_not_asserted():
    payload = extract_structures_from_records(
        [_record("If AI capex rises, GPU demand could increase.")]
    )

    edge = next(edge for edge in payload["edges"] if edge["edge_type"] == "causal")
    assert edge["assertion_status"] == "conditional"
    assert edge["confidence"] < 0.84


def test_negated_causal_relation_is_marked_negated():
    payload = extract_structures_from_records(
        [_record("AI capex does not drive GPU demand.")]
    )

    edge = next(edge for edge in payload["edges"] if edge["edge_type"] == "causal")
    assert edge["assertion_status"] == "negated"
    assert edge["confidence"] < 0.5


def test_no_evidence_causal_phrase_is_not_asserted():
    payload = extract_structures_from_records(
        [_record("There is no evidence that AI demand drives GPU demand.")]
    )

    assert all(edge["assertion_status"] != "asserted" for edge in payload["edges"])


def test_vague_coexistence_does_not_hallucinate_causal_edge():
    payload = extract_structures_from_records(
        [_record("Both AI capex and GPU demand were mentioned in the same earnings call.")]
    )

    assert payload["nodes"]
    assert payload["edges"] == []


def test_same_raw_output_keeps_edges_from_distinct_claims():
    raw_id = "run1:news_agent:news_report"
    payload = extract_structures_from_records(
        [
            _record(
                "AI demand drives GPU demand in training workloads.",
                claim_id=f"{raw_id}:claim:1",
                raw_id=raw_id,
            ),
            _record(
                "AI demand drives GPU demand across cloud workloads.",
                claim_id=f"{raw_id}:claim:2",
                raw_id=raw_id,
            ),
        ]
    )

    edges = [edge for edge in payload["edges"] if edge["edge_type"] == "causal"]
    assert len(edges) == 2
    assert {edge["source_record_id"] for edge in edges} == {
        f"{raw_id}:claim:1",
        f"{raw_id}:claim:2",
    }
    assert all(edge["source_agent_output_id"] == raw_id for edge in edges)
    assert all(edge["evidence"] for edge in edges)


def test_legacy_v1_identity_remains_traceable():
    record = _record("AI demand drives GPU demand.")
    record.pop("claim_id")
    record.pop("source_agent_output_id")
    record["agent_output_id"] = "legacy_raw_output_id"

    payload = extract_structures_from_records([record])

    assert payload["edges"][0]["source_record_id"] == "legacy_raw_output_id"
    assert payload["edges"][0]["source_agent_output_id"] == "legacy_raw_output_id"


def test_driven_by_compound_object_list_does_not_fabricate_edge_between_siblings():
    """MU run 0ba23540-0623-4d05-a670-098fbbfec1d1, claim
    fundamental_agent:fundamentals_report:claim:14 (Structure Extractor
    Relation Coverage Sprint audit): "Micron has undergone a historic
    earnings inflection, driven primarily by AI-related HBM (High
    Bandwidth Memory) demand, DRAM pricing recovery, and data center
    spending acceleration." Two known factors are present (Datacenter
    CapEx, Semiconductor Cycle), but they are syntactic siblings -- both
    are co-objects of one shared "driven by" predicate whose real target
    ("earnings inflection") is not a taxonomy factor. Neither factor
    causes or supports the other; asserting an edge between them would
    fabricate a source/target relation the claim never states. Must stay
    at 0 edges even though a relation predicate and 2 factors are both
    present in the same claim.
    """
    payload = extract_structures_from_records(
        [
            _record(
                "Micron has undergone a historic earnings inflection, driven "
                "primarily by AI-related HBM (High Bandwidth Memory) demand, "
                "DRAM pricing recovery, and data center spending acceleration.",
                factors=["Datacenter CapEx", "Semiconductor Cycle"],
            )
        ]
    )

    assert payload["edges"] == []


def test_overlapping_factor_aliases_for_one_phrase_do_not_self_relate():
    """AMD run 66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1, claim
    news_agent:news_report:claim:17: "Investors are increasingly
    scrutinizing the heavy AI infrastructure spending by hyperscalers...,
    questioning whether returns on investment justify the capital
    outlay." "AI CapEx", "Datacenter CapEx", and "AI Infrastructure" all
    match the same "AI infrastructure spending" phrase span -- they are
    three aliases of one mention, not two distinct related concepts, and
    "scrutinizing"/"questioning" are not relation predicates. Must not
    self-relate the overlapping aliases into an edge.
    """
    payload = extract_structures_from_records(
        [
            _record(
                "Investors are increasingly scrutinizing the heavy AI "
                "infrastructure spending by hyperscalers, questioning whether "
                "returns on investment justify the capital outlay.",
                factors=["AI CapEx", "Datacenter CapEx", "AI Infrastructure"],
            )
        ]
    )

    assert payload["edges"] == []


def test_conjunctive_condition_list_does_not_imply_causal_pair():
    """MU run 0ba23540-0623-4d05-a670-098fbbfec1d1, claim
    research_manager:investment_plan:claim:15: several distinct
    conditions ("...hyperscaler capex pause, and rate-driven multiple
    compression...") are listed as needing to "arrive simultaneously" --
    a conjunctive list of co-occurring conditions, not one factor causing
    another. Must not treat list-membership as a causal or supportive
    relation between AI CapEx and Valuation Risk.
    """
    payload = extract_structures_from_records(
        [
            _record(
                "Samsung yield recovery, HBM oversupply, CXMT competition, "
                "hyperscaler capex pause, and rate-driven multiple compression "
                "all need to arrive simultaneously and severely to bring "
                "forward EPS down.",
                factors=["AI CapEx", "Valuation Risk"],
            )
        ]
    )

    assert payload["edges"] == []


def test_low_risk_supportive_language_stays_blocked_by_existing_risk_factor_guard():
    """AMD run 66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1, claim
    news_agent:news_report:claim:55: "Recession Risk Remains Low: US
    recession probability at just 10% means the macro backdrop remains
    supportive for enterprise/cloud capex." Even though this expresses a
    real supportive relationship in natural language, Recession Risk is a
    RISK_FACTORS member and the existing (frozen, unmodified) guard in
    _extract_edges deliberately refuses supportive edges touching a risk
    factor, because the claim's true polarity is "LOW risk supports
    capex", not "Recession Risk supports capex". This regression guard
    documents that the existing risk-factor exclusion is doing its job
    and must not be loosened by future relation-phrase additions.
    """
    payload = extract_structures_from_records(
        [
            _record(
                "US recession probability at just 10% means the macro backdrop "
                "remains supportive for enterprise and cloud capex.",
                factors=["AI CapEx", "Recession Risk"],
            )
        ]
    )

    assert payload["edges"] == []


def test_single_factor_relation_claim_cannot_produce_an_edge():
    """AMD run 66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1, claim
    news_agent:news_report:claim:58: "...whether Lisa Su's AI demand
    confidence translates into revenue beats that can justify the
    elevated valuation." Only one known taxonomy factor (AI Demand) is
    present in this claim -- "revenue beats" is not covered by any
    Revenue Growth alias. _extract_edges requires >= 2 known factors in
    the same claim; a relation phrase alone can never substitute for a
    resolvable second factor. Documents that this claim's zero-edge
    result is correctly driven by taxonomy/alias coverage, not a
    relation-phrase gap, and is out of this Sprint's scope (fixing it
    would require editing the factor_normalizer.py alias table shared
    with the AI Alpha Mapper).
    """
    payload = extract_structures_from_records(
        [
            _record(
                "The key event to watch is AMD's upcoming earnings report, "
                "which will be the definitive test of whether Lisa Su's AI "
                "demand confidence translates into revenue beats that can "
                "justify the elevated valuation.",
                factors=["AI Demand"],
            )
        ]
    )

    assert payload["edges"] == []


def test_full_stop_causal_acceptance_sentence():
    payload = extract_structures_from_records([_record("AI Demand drives Revenue Growth.")])
    assert _has_edge(payload, "AI Demand", "NVDA Revenue Growth", "causal")


def test_reverse_passive_with_adverb_acceptance_sentence():
    payload = extract_structures_from_records(
        [_record("Revenue Growth is driven primarily by AI Demand.")]
    )
    assert _has_edge(payload, "AI Demand", "NVDA Revenue Growth", "causal")


def test_forward_multiword_acceptance_sentence():
    payload = extract_structures_from_records(
        [_record("AI CapEx translates into Datacenter CapEx.")]
    )
    assert _has_edge(payload, "AI CapEx", "Datacenter CapEx", "causal")


def test_reverse_multiword_benefits_from_acceptance_sentence():
    payload = extract_structures_from_records(
        [_record("Revenue Growth benefits from AI Demand.")]
    )
    assert _has_edge(payload, "AI Demand", "NVDA Revenue Growth", "causal")


def test_forward_multiword_pressure_acceptance_sentence():
    payload = extract_structures_from_records(
        [_record("Recession Risk puts pressure on Revenue Growth.")]
    )
    assert _has_edge(payload, "Recession Risk", "NVDA Revenue Growth", "causal")


def test_conditional_acceptance_sentence():
    payload = extract_structures_from_records(
        [_record("If AI Demand remains strong, Revenue Growth could accelerate.")]
    )
    edge = next(e for e in payload["edges"] if e["edge_type"] == "causal")
    assert edge["source_label"] == "AI Demand"
    assert edge["target_label"] == "NVDA Revenue Growth"
    assert edge["assertion_status"] == "conditional"


def test_with_embedded_supportive_acceptance_sentence():
    payload = extract_structures_from_records(
        [_record("With AI Demand supporting Revenue Growth, the outlook improves.")]
    )
    assert _has_edge(payload, "AI Demand", "NVDA Revenue Growth", "supportive")


@pytest.mark.parametrize(
    "sentence",
    [
        "AI Demand discusses Revenue Growth.",
        "AI Demand includes Revenue Growth.",
        "AI Demand follows Revenue Growth.",
        "AI Demand compares Revenue Growth.",
        "AI Demand mentions Revenue Growth.",
        "AI Demand and Revenue Growth remain important.",
        "Revenue Growth increased by 20 percent.",
        "AI Demand compared to Revenue Growth.",
        "AI Demand correlated with Revenue Growth.",
        "AI Demand moved with Revenue Growth.",
        "If AI Demand and Revenue Growth remain strong, the outlook is uncertain.",
        "Could AI Demand drive Revenue Growth?",
    ],
)
def test_negative_grammar_variants_produce_no_edge(sentence):
    payload = extract_structures_from_records([_record(sentence)])
    assert payload["edges"] == []


def test_common_object_of_unresolvable_subject_does_not_relate_two_factors():
    """"Higher rates" is not a resolvable factor; the claim must stay at 0
    edges rather than fabricating a Revenue Growth <-> Valuation Risk edge
    out of the two objects of a shared predicate."""
    payload = extract_structures_from_records(
        [
            _record(
                "Higher rates pressure Revenue Growth and Valuation Risk.",
                factors=["Revenue Growth", "Valuation Risk"],
            )
        ]
    )
    assert payload["edges"] == []


def test_new_relation_families_preserve_full_provenance():
    raw_id = "run1:news_agent:news_report"
    payload = extract_structures_from_records(
        [
            _record(
                "AI CapEx translates into Datacenter CapEx.",
                claim_id=f"{raw_id}:claim:1",
                raw_id=raw_id,
            )
        ]
    )
    edge = next(e for e in payload["edges"] if e["edge_type"] == "causal")
    assert edge["source_record_id"] == f"{raw_id}:claim:1"
    assert edge["source_agent_output_id"] == raw_id
    assert edge["evidence"]
    assert edge["source_claim"]


# ---------------------------------------------------------------------------
# Unified Claim Admissibility and Context-Only Routing Sprint
# ---------------------------------------------------------------------------


def test_direction_unknown_analytical_relation_claim_still_enters_structure_graph():
    """Spec test #1: a claim tagged analytical whose direction is unknown
    (an unresolved stock direction, not the same thing as "no relation")
    must still produce nodes and edges -- claim_quality is a separate
    concern from direction, and structure eligibility never depends on it
    for ANALYTICAL claims."""
    record = _record("AI infrastructure demand drives storage demand.")
    record["direction"] = "unknown"
    record["claim_quality"] = "analytical"

    payload = extract_structures_from_records([record])

    assert _has_edge(payload, "AI Infrastructure", "Semiconductor Cycle", "causal")


def test_non_substantive_claim_contributes_no_node_or_edge():
    """Spec test #5 (negative side): a non_substantive claim -- even one
    whose text superficially mentions two factors -- must never seed a
    Structure Graph node or edge."""
    record = _record("AI demand drives GPU demand as model training expands.")
    record["claim_quality"] = "non_substantive"

    payload = extract_structures_from_records([record])

    assert payload["nodes"] == []
    assert payload["edges"] == []


def test_context_only_claim_without_a_relation_contributes_nothing():
    """CONTEXT_ONLY is only eligible for Structure when relation extraction
    finds a legal relation for this specific claim -- a bare factual mention
    of a single factor must not seed a node on its own."""
    record = _record("The company reported quarterly revenue of $2.3 billion.")
    record["factors"] = ["Revenue Growth"]
    record["claim_quality"] = "context_only"

    payload = extract_structures_from_records([record])

    assert payload["nodes"] == []
    assert payload["edges"] == []


def test_context_only_claim_with_a_legal_relation_still_contributes():
    """The converse: a CONTEXT_ONLY claim whose evidence *does* contain a
    legal, resolvable relation is still admitted -- context_only routing
    must never throw away real structural signal."""
    record = _record("AI CapEx translates into Datacenter CapEx.")
    record["claim_quality"] = "context_only"

    payload = extract_structures_from_records([record])

    assert _has_edge(payload, "AI CapEx", "Datacenter CapEx", "causal")


def test_save_extracted_structures_writes_week2_artifact(tmp_path):
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    (run_dir / "structured_agent_outputs.json").write_text(
        json.dumps(
            {
                "schema_version": "week1a.structured_agent_outputs.v1",
                "run_id": "run1",
                "ticker": "NVDA",
                "records": [_record("GPU demand drives revenue growth at NVDA.")],
            }
        ),
        encoding="utf-8",
    )

    payload = save_extracted_structures("run1", output_root=tmp_path)

    assert payload["schema_version"] == "week2.extracted_structures.v2"
    assert _has_edge(payload, "GPU Demand", "NVDA Revenue Growth", "causal")
    assert (run_dir / "extracted_structures.json").exists()
