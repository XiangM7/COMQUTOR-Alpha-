"""Structure Correctness Sprint tests.

Covers the Week 1a claim-quality boundary (boilerplate/disclaimer filtering,
deterministic dedupe), the Week 2 edge-extraction fixes (participial
"driven by", negative-direction causal verbs, memory/storage-demand
vocabulary), the Week 3 evidence-provenance enrichment, the Week 4 conflict
bull/bear evidence rebuild, and the additive run_audit.json artifact.

The SNDK fixture below is a sanitized, minimal excerpt-style fixture -- a
handful of short sentences shaped like the real run's claims, never the full
report.
"""

import json

from comqutor_alpha.api.routes_research import (
    RUN_AUDIT_SCHEMA_VERSION,
    _attach_conflict_evidence,
    build_run_audit_payload,
    write_run_audit_artifact,
)
from comqutor_alpha.graph_engine.graph_builder import build_structure_graph
from comqutor_alpha.graph_engine.pipeline import build_and_score_structure_graph
from comqutor_alpha.structure_engine.structure_extractor import (
    extract_structures_from_records,
)
from comqutor_alpha.structure_engine.structured_output_adapter import (
    FILTER_REASON_BOILERPLATE,
    FILTER_REASON_DISCLAIMER,
    adapt_raw_agent_outputs,
    classify_filtered_claim,
    dedupe_structured_records,
    extract_claim_segments_with_audit,
    normalize_claim_for_dedupe,
)

# ---------------------------------------------------------------------------
# Phase 1: boilerplate / disclaimer filtering
# ---------------------------------------------------------------------------


def test_pure_meta_commentary_is_filtered():
    for text in (
        "I now have all the data needed to compile a comprehensive report.",
        "Let me synthesize everything.",
        "I will now compile the findings.",
        "Here is the comprehensive report.",
    ):
        assert classify_filtered_claim(text) == FILTER_REASON_BOILERPLATE, text


def test_now_prefixed_report_generation_narration_is_filtered():
    """Analyst Findings Display Cleanup: reproduces the real MU run's
    "Now let me compile the comprehensive analysis report." leaking into
    structured claims. The fix generalizes the existing meta-commentary
    pattern to a leading "now" before "let me"/"let's"/etc, rather than
    hardcoding this one sentence."""
    for text in (
        "Now let me compile the comprehensive analysis report.",
        "Now let me compile the report.",
        "Let me now compile the findings.",
        "Now I will compile the report.",
        "I can now compile the final analysis.",
        "Let me synthesize the findings.",
        "I can now provide the comprehensive report.",
    ):
        assert classify_filtered_claim(text) == FILTER_REASON_BOILERPLATE, text


def test_based_on_the_data_sentence_with_real_claim_is_kept():
    for text in (
        "Based on the data, revenue grew 20% quarter over quarter.",
        "The analysis shows strong AI infrastructure demand supporting revenue growth.",
        "The report indicates valuation risk remains elevated.",
        "Based on the data, MU revenue grew 20%.",
        "The report indicates that demand supports revenue growth.",
        "I believe valuation risk remains elevated.",
        "Let me explain why MU margins may decline.",
    ):
        assert classify_filtered_claim(text) is None, text


def test_direction_unknown_is_never_a_filter_condition():
    """The boilerplate/transition filter operates purely on sentence text --
    it must never consult or be influenced by a claim's inferred direction.
    A substantive but direction-neutral sentence survives the filter, and a
    meta-commentary sentence is dropped regardless of what direction it
    would otherwise infer to."""
    assert classify_filtered_claim("Market conditions for MU remain mixed and hard to call.") is None
    assert (
        classify_filtered_claim("Now let me compile the comprehensive analysis report.")
        == FILTER_REASON_BOILERPLATE
    )


def test_unknown_direction_claim_is_not_removed_by_extraction():
    """A meaningful claim that infers direction=unknown must still reach
    structured records -- only meta-commentary/transition/disclaimer
    sentences are ever dropped at the extraction boundary."""
    raw_record = {
        "agent": "market_agent",
        "agent_output_id": "run1:market_agent:market_report",
        "raw_output": "From a May 1st open, the stock surged 25%.",
    }
    records = adapt_raw_agent_outputs(raw_record, "run1", "SNDK")
    assert len(records) == 1
    assert records[0]["direction"] == "unknown"
    assert "surged 25%" in records[0]["claim"]


def test_disclaimer_in_same_paragraph_only_removes_disclaimer_sentence():
    raw = (
        "AI infrastructure demand is accelerating. "
        "Datacenter demand supports revenue growth. "
        "This is not investment advice."
    )
    segments, filtered = extract_claim_segments_with_audit(raw)
    claims = [segment["claim"] for segment in segments]
    assert claims == [
        "AI infrastructure demand is accelerating.",
        "Datacenter demand supports revenue growth.",
    ]
    assert [item["reason_code"] for item in filtered] == [FILTER_REASON_DISCLAIMER]


def test_filtered_text_never_reaches_structured_records():
    raw_record = {
        "agent": "market_agent",
        "agent_output_id": "run1:market_agent:market_report",
        "raw_output": (
            "I now have all the data needed to compile a comprehensive report.\n\n"
            "Revenue accelerated 25% on datacenter storage demand strength."
        ),
    }
    audit: list = []
    records = adapt_raw_agent_outputs(raw_record, "run1", "SNDK", filter_audit=audit)
    claims = [record["claim"] for record in records]
    assert all("compile a comprehensive report" not in claim for claim in claims)
    assert any("Revenue accelerated 25%" in claim for claim in claims)
    assert any(item["reason_code"] == FILTER_REASON_BOILERPLATE for item in audit)


# ---------------------------------------------------------------------------
# Phase 2: dedupe
# ---------------------------------------------------------------------------


def _claim_record(claim, *, agent="news_agent", source="s1", claim_id, confidence=0.5,
                  claim_index=0, direction="positive", assertion_status="asserted"):
    return {
        "claim_id": claim_id,
        "agent": agent,
        "source_agent_output_id": source,
        "claim": claim,
        "evidence": claim,
        "confidence": confidence,
        "claim_index": claim_index,
        "direction": direction,
        "assertion_status": assertion_status,
    }


def test_same_source_duplicate_claims_are_merged():
    records = [
        _claim_record("Revenue accelerated on AI demand.", claim_id="c1"),
        _claim_record("Revenue accelerated on AI demand.", claim_id="c2", claim_index=1),
    ]
    deduped, removed = dedupe_structured_records(records)
    assert removed == 1
    assert len(deduped) == 1
    assert deduped[0]["duplicate_count"] == 2


def test_claims_with_different_numbers_are_not_merged():
    records = [
        _claim_record("Revenue increased 10%.", claim_id="c1"),
        _claim_record("Revenue increased 20%.", claim_id="c2", claim_index=1),
    ]
    deduped, removed = dedupe_structured_records(records)
    assert removed == 0
    assert len(deduped) == 2


def test_cross_agent_agreement_keeps_both_records_with_provenance():
    records = [
        _claim_record("AI demand drives GPU demand.", agent="news_agent", source="s1", claim_id="c1"),
        _claim_record(
            "AI demand drives GPU demand.", agent="market_agent", source="s2", claim_id="c2"
        ),
    ]
    deduped, removed = dedupe_structured_records(records)
    assert removed == 0
    assert len(deduped) == 2
    assert deduped[0]["duplicate_group_id"] == deduped[1]["duplicate_group_id"]
    assert deduped[0]["merged_agents"] == ["market_agent", "news_agent"]
    # Identity semantics untouched.
    assert {record["claim_id"] for record in deduped} == {"c1", "c2"}


def test_normalization_preserves_numbers_and_direction_words():
    assert normalize_claim_for_dedupe("Revenue increased 10%.") != normalize_claim_for_dedupe(
        "Revenue increased 20%."
    )
    assert normalize_claim_for_dedupe("  “Revenue GREW  5%.”  ") == normalize_claim_for_dedupe(
        '"revenue grew 5%."'
    )


def test_duplicate_claims_do_not_inflate_matched_evidence():
    """A same-agent duplicate is removed before mapping, so activation's
    MatchedEvidence can never count the same fact twice."""
    records = [
        _claim_record("Valuation risk is elevated after the rally.", claim_id="c1"),
        _claim_record(
            "Valuation risk is elevated after the rally.", claim_id="c2", claim_index=1
        ),
    ]
    deduped, removed = dedupe_structured_records(records)
    assert removed == 1
    assert [record["claim_id"] for record in deduped] == ["c1"]


# ---------------------------------------------------------------------------
# Phase 3: edge extraction
# ---------------------------------------------------------------------------


def _structured(claim, *, claim_id="run1:news_agent:news_report:claim:1",
                source="run1:news_agent:news_report", agent="news_agent"):
    return {
        "run_id": "run1",
        "ticker": "SNDK",
        "agent": agent,
        "claim": claim,
        "evidence": claim,
        "entities": ["SNDK"],
        "factors": [],
        "direction": "positive",
        "confidence": 0.8,
        "claim_id": claim_id,
        "agent_output_id": claim_id,
        "source_agent_output_id": source,
    }


def test_explicit_driving_relation_generates_edge():
    payload = extract_structures_from_records(
        [
            _structured(
                "AI infrastructure demand driving memory and storage demand from the "
                "AI data center buildout is the fundamental bull thesis."
            )
        ]
    )
    assert payload["edges"], "explicit 'driving' relation must produce an edge"
    edge = payload["edges"][0]
    assert edge["source_label"] == "AI Infrastructure"
    assert edge["edge_type"] == "causal"
    assert edge["assertion_status"] == "asserted"


def test_negative_direction_causal_verb_generates_conditional_edge():
    payload = extract_structures_from_records(
        [
            _structured(
                "Renewed AI capex skepticism could reduce forward memory demand forecasts."
            )
        ]
    )
    causal = [edge for edge in payload["edges"] if edge["edge_type"] == "causal"]
    assert causal, "'could reduce' must produce a (conditional) causal edge"
    assert all(edge["assertion_status"] == "conditional" for edge in causal)


def test_participial_driven_by_without_auxiliary_generates_edge():
    payload = extract_structures_from_records(
        [_structured("Storage demand strength, driven by hyperscaler AI capex, is broad.")]
    )
    causal = [edge for edge in payload["edges"] if edge["edge_type"] == "causal"]
    assert causal
    assert causal[0]["source_label"] == "AI CapEx"
    assert causal[0]["target_label"] == "Semiconductor Cycle"


def test_increased_by_number_is_not_treated_as_passive_relation():
    payload = extract_structures_from_records(
        [_structured("Memory demand increased by 20% while storage demand stayed flat.")]
    )
    # "increased by 20%" is a magnitude, not an inverted causal relation.
    assert all(edge["edge_type"] != "causal" for edge in payload["edges"])


def test_vague_coexistence_still_produces_no_edge():
    payload = extract_structures_from_records(
        [_structured("Both memory demand and storage demand were mentioned in the call.")]
    )
    assert payload["edges"] == []


def test_sndk_style_fixture_produces_nonzero_edges():
    """Minimal sanitized SNDK-shaped fixture: three independent explicit
    relations must produce at least three admissible edges."""
    records = [
        _structured(
            "AI infrastructure demand driving memory and storage demand from the "
            "AI data center buildout is the fundamental bull thesis.",
            claim_id="run1:sentiment_agent:sentiment_report:claim:1",
            source="run1:sentiment_agent:sentiment_report",
            agent="sentiment_agent",
        ),
        _structured(
            "IBM's warning about enterprise AI ROI could reduce forward memory demand "
            "forecasts.",
            claim_id="run1:news_agent:news_report:claim:2",
            source="run1:news_agent:news_report",
            agent="news_agent",
        ),
        _structured(
            "Enterprise AI adoption velocity feeding into hyperscaler capex revision "
            "risk is the key transmission channel.",
            claim_id="run1:research_manager:investment_plan:claim:3",
            source="run1:research_manager:investment_plan",
            agent="research_manager",
        ),
    ]
    payload = extract_structures_from_records(records)
    assert len(payload["edges"]) >= 3
    for edge in payload["edges"]:
        assert edge["source_record_id"]
        assert edge["source_agent_output_id"]
        assert edge["evidence"]


def test_graph_builder_preserves_legal_extracted_edges_with_provenance():
    records = [
        _structured(
            "AI infrastructure demand driving memory and storage demand from the "
            "AI data center buildout is the fundamental bull thesis."
        )
    ]
    extracted = extract_structures_from_records(records)
    assert extracted["edges"]
    matches_payload = {"run_id": "run1", "ticker": "SNDK", "matches": []}
    graph = build_structure_graph(matches_payload, extracted)
    assert graph["graph_metrics"]["edge_count"] == len(
        {(e["source"], e["target"], e["edge_type"]) for e in extracted["edges"]}
    )
    rejected = graph["graph_metrics"]["rejected_edges"]
    assert all(count == 0 for count in rejected.values())
    for edge in graph["edges"]:
        assert edge["claim_ids"]
        assert edge["source_agent_output_ids"]
        assert edge["evidence"]
        assert 0.0 <= edge["weight"] <= 1.0


# ---------------------------------------------------------------------------
# Phase 4: alpha evidence provenance
# ---------------------------------------------------------------------------


def _matches_payload_with_one_committed_claim():
    return {
        "schema_version": "week2.alpha_matches.v2",
        "run_id": "run1",
        "ticker": "SNDK",
        "matches": [
            {
                "run_id": "run1",
                "ticker": "SNDK",
                "agent": "news_agent",
                "claim_id": "run1:news_agent:news_report:claim:1",
                "source_agent_output_id": "run1:news_agent:news_report",
                "claim": "Valuation risk is elevated after the vertical rally.",
                "evidence": "Valuation risk is elevated after the vertical rally.",
                "direction": "negative",
                "matched_alpha": "A304",
                "matched_alpha_name": "Multiple Compression",
                "score": 0.72,
                "match_status": "matched",
                "assertion_status": "asserted",
                "semantic_polarity": "activation",
                "eligible_candidates": [
                    {
                        "alpha_id": "A304",
                        "relation": "activation",
                        "matched_keywords": ["valuation risk"],
                        "matched_factors": ["Valuation Risk"],
                    }
                ],
            }
        ],
    }


def test_activation_alphas_carry_full_evidence_provenance():
    matches_payload = _matches_payload_with_one_committed_claim()
    extracted = {"run_id": "run1", "ticker": "SNDK", "nodes": [], "edges": []}
    graph_payload = build_and_score_structure_graph(matches_payload, extracted)
    a304 = next(a for a in graph_payload["activation"]["alphas"] if a["alpha_id"] == "A304")
    assert a304["evidence_detail"], "committed evidence must carry provenance detail"
    detail = a304["evidence_detail"][0]
    assert detail["claim_id"] == "run1:news_agent:news_report:claim:1"
    assert detail["claim"].startswith("Valuation risk is elevated")
    assert detail["agent"] == "news_agent"
    assert detail["source_agent_output_id"] == "run1:news_agent:news_report"
    assert detail["match_score"] == 0.72
    assert detail["relation"] == "activation"
    assert detail["matched_keywords"] == ["valuation risk"]
    assert detail["matched_factors"] == ["Valuation Risk"]
    assert detail["assertion_status"] == "asserted"
    assert detail["direction"] == "negative"


# ---------------------------------------------------------------------------
# Phase 5: conflict bull/bear evidence
# ---------------------------------------------------------------------------


class _FakeRepository:
    def __init__(self, rows):
        self._rows = rows

    def get_alpha_matches(self, run_id):
        return self._rows


def _conflict_result_fixture():
    conflict = {
        "conflict_id": "A101__A304",
        "alpha_a": "A101",
        "alpha_b": "A304",
        "bull_alpha_id": "A101",
        "bear_alpha_id": "A304",
        "bull_structure": {
            "alpha_id": "A101",
            "claim_ids": ["run1:news_agent:news_report:claim:1"],
            "evidence": ["AI demand tailwind protects the downside."],
            "match_scores": [0.61],
            "agents": ["news_agent"],
        },
        "bear_structure": {
            "alpha_id": "A304",
            "claim_ids": ["run1:aggressive_risk_analyst:risk:claim:2"],
            "evidence": ["Multiple compression headwind is structural."],
            "match_scores": [0.76],
            "agents": ["aggressive_risk_analyst"],
        },
    }
    return {"conflicts": [conflict], "main_conflict": dict(conflict)}


def test_conflict_evidence_attaches_both_sides_with_agent_and_relation():
    rows = [
        {
            "claim_id": "run1:news_agent:news_report:claim:1",
            "agent": "news_agent",
            "claim_text": "AI demand tailwind protects the downside.",
            "match_score": 0.61,
            "candidate_scores": [{"alpha_id": "A101", "relation": "activation"}],
        },
        {
            "claim_id": "run1:aggressive_risk_analyst:risk:claim:2",
            "agent": "aggressive_risk_analyst",
            "claim_text": "Multiple compression headwind is structural.",
            "match_score": 0.76,
            "candidate_scores": [{"alpha_id": "A304", "relation": "activation"}],
        },
    ]
    result = _conflict_result_fixture()
    _attach_conflict_evidence(result, _FakeRepository(rows), "run1")

    for target in (result["conflicts"][0], result["main_conflict"]):
        bull = target["bull_evidence"]
        bear = target["bear_evidence"]
        assert bull and bear
        assert bull[0]["claim_id"] == "run1:news_agent:news_report:claim:1"
        assert bull[0]["claim_text"] == "AI demand tailwind protects the downside."
        assert bull[0]["agent"] == "news_agent"
        assert bull[0]["match_score"] == 0.61
        assert bull[0]["relation"] == "activation"
        assert bear[0]["agent"] == "aggressive_risk_analyst"
        assert bear[0]["relation"] == "activation"


def test_conflict_evidence_degrades_to_structure_arrays_without_match_rows():
    result = _conflict_result_fixture()
    _attach_conflict_evidence(result, _FakeRepository([]), "run1")
    bull = result["conflicts"][0]["bull_evidence"]
    assert bull[0]["claim_text"] == "AI demand tailwind protects the downside."
    assert bull[0]["match_score"] == 0.61


# ---------------------------------------------------------------------------
# Phase 6: run_audit.json
# ---------------------------------------------------------------------------


def _write_json(run_dir, name, payload):
    (run_dir / name).write_text(json.dumps(payload), encoding="utf-8")


def _seed_audit_run(tmp_path, run_id="runaudit1"):
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    _write_json(run_dir, "metadata.json", {"run_id": run_id, "ticker": "SNDK", "agents": ["a", "b"]})
    _write_json(
        run_dir,
        "raw_agent_outputs.json",
        {"run_id": run_id, "ticker": "SNDK", "agent_outputs": [{}, {}]},
    )
    _write_json(
        run_dir,
        "structured_agent_outputs.json",
        {
            "run_id": run_id,
            "ticker": "SNDK",
            "records": [{"claim_id": "c1"}, {"claim_id": "c2"}, {"claim_id": "c3"}],
            "metadata": {
                "raw_claim_count": 5,
                "boilerplate_removed_count": 2,
                "disclaimer_removed_count": 1,
                "duplicate_removed_count": 2,
            },
        },
    )
    _write_json(
        run_dir,
        "alpha_matches.json",
        {
            "run_id": run_id,
            "ticker": "SNDK",
            "matches": [
                {"match_status": "matched"},
                {"match_status": "matched"},
                {"match_status": "ambiguous"},
                {"match_status": "no_match"},
            ],
        },
    )
    _write_json(
        run_dir,
        "structure_graph.json",
        {
            "run_id": run_id,
            "ticker": "SNDK",
            "graph_metrics": {
                "node_count": 4,
                "edge_count": 0,
                "rejected_edges": {"self_loop": 1, "dangling_reference": 0},
            },
            "activation": {
                "alphas": [
                    {"alpha_id": "A101", "status": "regime_level", "activation_score": 91.0},
                    {"alpha_id": "A102", "status": "dominant", "activation_score": 80.0},
                    {"alpha_id": "A001", "status": "watch", "activation_score": 40.0},
                ]
            },
        },
    )
    return run_dir


def test_run_audit_counts_come_from_real_artifacts(tmp_path):
    run_id = "runaudit1"
    _seed_audit_run(tmp_path, run_id)
    audit = build_run_audit_payload(run_id, tmp_path, conflict_count=3)

    assert audit["schema_version"] == RUN_AUDIT_SCHEMA_VERSION
    assert audit["run_id"] == run_id
    assert audit["ticker"] == "SNDK"
    assert audit["raw_agent_output_count"] == 2
    assert audit["raw_claim_count"] == 5
    assert audit["boilerplate_removed_count"] == 2
    assert audit["disclaimer_removed_count"] == 1
    assert audit["duplicate_removed_count"] == 2
    assert audit["valid_claim_count"] == 3
    assert audit["matched_alpha_count"] == 2
    assert audit["ambiguous_alpha_count"] == 1
    assert audit["no_match_count"] == 1
    assert audit["graph_node_count"] == 4
    assert audit["graph_edge_count"] == 0
    assert audit["rejected_edge_count"] == 1
    assert audit["dominant_alpha_count"] == 1
    assert audit["regime_level_alpha_count"] == 1
    assert audit["conflict_count"] == 3
    assert "BOILERPLATE_REMOVED" in audit["warnings"]
    assert "DUPLICATES_REMOVED" in audit["warnings"]
    assert "NO_GRAPH_EDGES" in audit["warnings"]
    assert "INSUFFICIENT_STRUCTURAL_RELATIONS" in audit["warnings"]
    assert "HIGH_ACTIVATION_WITHOUT_GRAPH_SUPPORT" in audit["warnings"]


def test_run_audit_artifact_is_written_additively(tmp_path):
    run_id = "runaudit1"
    run_dir = _seed_audit_run(tmp_path, run_id)
    before = sorted(path.name for path in run_dir.iterdir())
    write_run_audit_artifact(run_id, tmp_path, conflict_count=0)
    after = sorted(path.name for path in run_dir.iterdir())
    assert set(after) - set(before) == {"run_audit.json"}
    written = json.loads((run_dir / "run_audit.json").read_text(encoding="utf-8"))
    assert written["schema_version"] == RUN_AUDIT_SCHEMA_VERSION
    # No existing artifact was modified.
    assert json.loads((run_dir / "structure_graph.json").read_text(encoding="utf-8"))[
        "graph_metrics"
    ]["edge_count"] == 0
