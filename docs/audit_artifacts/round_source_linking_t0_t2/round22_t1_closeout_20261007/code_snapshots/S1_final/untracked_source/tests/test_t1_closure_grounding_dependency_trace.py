"""T1 closure: claim data grounding, derived-calculation reproduction, fact dependency and the evidence trace.

Everything here runs offline against a trimmed copy of REAL saved records of the AMD requalification execution
(``tests/fixtures/t1_closure_amd_excerpt.json``: the A301 trio 31/33/36, the restatement 29 and seven
portfolio_manager claims that cover each source-support status) -- not against a synthetic sample. The pipeline
tests drive the production entry (``routes_research._run_week3_graph_pipeline``) exactly like
``test_verified_evidence_gate_production_wiring.py``; nothing here sets a group id by hand.
"""

from __future__ import annotations

import copy
import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import comqutor_alpha.api.routes_research as routes_research
from comqutor_alpha.api.artifact_export import build_and_write_artifact_manifest
from comqutor_alpha.api.evidence_trace import (
    build_claim_trace,
    build_evidence_trace_artifact,
    build_key_conclusions,
    get_evidence_trace_response,
    key_conclusion_group,
    load_trace_context,
)
from comqutor_alpha.graph_engine.claim_data_grounding import (
    FACT_DEPENDENCY_CONTRACT,
    annotate_matches_with_data_points,
    dependency_anchors,
    extract_number_tokens,
    ground_claim,
    ground_records,
)
from comqutor_alpha.graph_engine.evidence_fact_index import EvidenceFactCandidate, group_evidence_candidates
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "t1_closure_amd_excerpt.json").read_text(encoding="utf-8"))
ROOT = "c904d4cc-dc09-495c-aec5-b056979948e1:"
FA = ROOT + "fundamental_agent:fundamentals_report:claim:"
PM = ROOT + "portfolio_manager:final_trade_decision:claim:"
SOURCES = FIXTURE["sources"]
SOURCES_BY_ID = {s["source_id"]: s for s in SOURCES}
RECORDS = {r["claim_id"]: r for r in FIXTURE["records"]}


def _ground(claim_id):
    return ground_claim(RECORDS[claim_id], SOURCES_BY_ID)


# ---------------------------------------------------------------------------
# Number tokens
# ---------------------------------------------------------------------------


def test_tokens_keep_stated_precision_and_drop_labels_dates_markers_and_small_integers():
    tokens = extract_number_tokens(
        "Revenue grew from $7,685M (Q2'25) to $11.5B on 2026-06-30 [fragment_id: src_582ac24bf4319648:frag:0]; "
        "margin 53.8% versus 3 peers in 2026, EPS $1.38."
    )
    assert [(t.raw, t.unit, t.decimals) for t in tokens] == [
        ("$7,685M", "m", 0), ("$11.5B", "b", 1), ("53.8%", "%", 1), ("$1.38", "", 2),
    ]
    millions = tokens[0].candidates[0]
    assert millions == (7_685_000_000.0, 500_000.0)  # half a million: the claim states whole millions
    billions = tokens[1].candidates[0]
    assert billions[0] == 11_500_000_000.0 and billions[1] == pytest.approx(50_000_000.0)  # half of 0.1B


def test_a_bare_integer_next_to_dollars_may_denote_millions_but_never_a_year():
    tokens = extract_number_tokens("Revenue (11,536 vs 7,685) in 2026.")
    assert [t.raw for t in tokens] == ["11,536", "7,685"]
    assert (11_536_000_000.0, 500_000.0) in tokens[0].candidates


# ---------------------------------------------------------------------------
# Grounding on the real saved records
# ---------------------------------------------------------------------------


def test_claim_31_grounds_to_five_total_revenue_observations_with_the_alias_recorded():
    grounding = _ground(FA + "31")
    assert [(p.label, p.period, p.value) for p in sorted(grounding.data_points, key=lambda p: p.period)] == [
        ("Total Revenue", "2025-06-30", 7_685_000_000.0), ("Total Revenue", "2025-09-30", 9_246_000_000.0),
        ("Total Revenue", "2025-12-31", 10_270_000_000.0), ("Total Revenue", "2026-03-31", 10_253_000_000.0),
        ("Total Revenue", "2026-06-30", 11_536_000_000.0),
    ]
    assert all(p.aliases == ("Operating Revenue",) and p.source_id == "src_582ac24bf4319648" for p in grounding.data_points)
    assert grounding.ambiguous_tokens == [] and grounding.unmatched_tokens == []
    assert grounding.stated_keys == grounding.input_keys


def test_claims_33_and_29_use_a_subset_of_31s_observations_and_36_uses_a_different_row():
    g31, g33, g29, g36 = (_ground(FA + n) for n in ("31", "33", "29", "36"))
    assert set(g33.stated_keys) < set(g31.stated_keys) and len(g33.stated_keys) == 2
    assert set(g29.stated_keys) < set(g31.stated_keys) and len(g29.stated_keys) == 2
    assert {p.label for p in g36.data_points} == {"Gross Profit"}
    assert not set(g36.stated_keys) & set(g31.stated_keys)  # same snapshot, different data: not the same fact


def test_a_number_matching_two_distinct_observations_is_ambiguous_and_creates_no_data_point():
    source = copy.deepcopy(SOURCES_BY_ID["src_582ac24bf4319648"])
    record = {**RECORDS[FA + "31"], "claim": "Revenue was about $10.3B in one of those quarters.", "linked_source_id": source["source_id"]}
    grounding = ground_claim(record, {source["source_id"]: source})
    assert grounding.data_points == []
    assert [a["token"] for a in grounding.ambiguous_tokens] == ["$10.3B"]  # 10.270B and 10.253B both round to 10.3B


def test_a_record_without_a_valid_link_grounds_to_nothing():
    unlinked = {**RECORDS[FA + "31"], "source_link_status": "NOT_PROVIDED"}
    assert ground_claim(unlinked, SOURCES_BY_ID).data_points == []
    assert ground_records([unlinked], SOURCES) == {}


def test_a_sign_word_before_a_number_grounds_the_negative_cell_but_a_dash_range_never_flips_a_sign():
    tokens = extract_number_tokens("Operating income swung from negative $134M to positive $1,990M; revenue $7,685M–$11,536M.")
    assert [(t.raw, t.explicit_sign) for t in tokens][:2] == [("negative $134M", "-"), ("$1,990M", "")]
    assert tokens[0].candidates[0] == (-134_000_000.0, 500_000.0)
    assert tokens[-1].candidates[0][0] > 0  # an en-dash in a range is not a minus sign
    grounding = _ground(PM + "4")  # "swung from negative $134M to positive $1,990M" + a revenue pair + two margins
    assert ("Operating Income", "2025-06-30", -134_000_000.0) in {(p.label, p.period, p.value) for p in grounding.data_points}
    assert ("Operating Income", "2026-06-30", 1_990_000_000.0) in {(p.label, p.period, p.value) for p in grounding.data_points}
    assert grounding.unmatched_tokens == []


def test_numbers_the_claim_states_but_no_saved_cell_holds_are_listed_while_calculated_percentages_are_not():
    assert _ground(PM + "4").unmatched_tokens == []  # 39.8% / 53.8% are accounted for by the reproduced margins
    assert _ground(PM + "10").unmatched_tokens == ["$1.38"]  # the cited snapshot holds forward EPS 15.72 and PEG 0.64, not this
    source = SOURCES_BY_ID["src_582ac24bf4319648"]
    record = {**RECORDS[PM + "4"], "claim": "Revenue reached $11,536M while net cash is $8.8B and the forward PE is 39.5x."}
    grounding = ground_claim(record, {source["source_id"]: source})
    assert [p.value for p in grounding.data_points] == [11_536_000_000.0]
    assert grounding.unmatched_tokens == ["$8.8B", "39.5x"]


# ---------------------------------------------------------------------------
# Derived calculations
# ---------------------------------------------------------------------------


def _derived(text):
    record = {**RECORDS[FA + "31"], "claim": text}
    return ground_claim(record, SOURCES_BY_ID)


def test_gross_margin_is_reproduced_from_the_saved_rows_with_inputs_formula_and_result():
    grounding = _derived("Gross margin reset from 39.8% to 53.8% [fragment_id: src_582ac24bf4319648:frag:0].")
    calcs = {c.stated_token: c for c in grounding.derived_calculations}
    assert set(calcs) == {"39.8%", "53.8%"}
    q2_26 = calcs["53.8%"]
    assert q2_26.metric == "gross_margin" and q2_26.status == "REPRODUCED"
    assert q2_26.computed == pytest.approx(6203 / 11536 * 100, abs=1e-3)
    assert {(i.label, i.period, i.value, i.role) for i in q2_26.inputs} == {
        ("Gross Profit", "2026-06-30", 6_203_000_000.0, "derived_input"),
        ("Total Revenue", "2026-06-30", 11_536_000_000.0, "derived_input"),
    }
    assert "arithmetic" in q2_26.scope_note.lower() and "does not verify" in q2_26.scope_note.lower()
    # the inputs are observations the claim relies on, even though it never states them
    assert len(grounding.input_keys) == 4 and grounding.stated_keys == ()


def test_percent_change_between_two_quoted_observations_is_reproduced_and_a_wrong_percent_is_not():
    good = _derived("Revenue rose +50.1% YoY ($11,536M vs $7,685M).")
    assert [(c.metric, c.comparison) for c in good.derived_calculations] == [("percent_change", "YoY")]
    bad = _derived("Revenue rose +80.0% YoY ($11,536M vs $7,685M).")
    assert bad.derived_calculations == [] and bad.unreproduced_percent_tokens == ["+80.0%"]


def test_a_margin_percent_that_matches_no_period_is_not_reported_as_reproduced():
    grounding = _derived("Gross margin was 45.0% in the latest quarter.")
    assert grounding.derived_calculations == [] and grounding.unreproduced_percent_tokens == ["45.0%"]


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def test_dependency_anchors_follow_the_stated_inputs_rule():
    groundings = {cid: _ground(cid) for cid in (FA + "29", FA + "31", FA + "33", FA + "36")}
    anchors = dependency_anchors({c: g.input_keys for c, g in groundings.items()}, {c: g.stated_keys for c, g in groundings.items()})
    assert anchors == {FA + "29": FA + "31", FA + "33": FA + "31"}  # 36 is not a derived expression of anything


def test_dependency_never_chains_two_unrelated_claims_through_a_shared_subset_and_needs_two_observations():
    stated = {"a1": {"o1", "o2", "o3"}, "a2": {"o1", "o2", "o4"}, "b": {"o1", "o2"}, "single": {"o1"}, "twin": {"o1", "o2", "o3"}}
    anchors = dependency_anchors(stated, stated)
    assert anchors["b"] == "a1"  # closest superset, smallest id on ties; never also a2 (a1 and a2 are not chained together)
    assert "single" not in anchors  # one shared number is "shares data", not "same fact" -- even when another claim states it alone
    assert anchors.get("twin") == "a1" and "a1" not in anchors  # equal sets of several observations: the smaller id anchors, one way only
    assert "a2" not in anchors


def test_two_claims_quoting_the_same_single_number_are_never_merged():
    assert dependency_anchors({"x": {"eps"}, "y": {"eps"}}, {"x": {"eps"}, "y": {"eps"}}) == {}


def test_a_claim_derived_from_two_different_claims_has_no_single_anchor():
    inputs = {"margin": {"rev", "gp"}, "revenue_claim": {"rev"}, "gp_claim": {"gp"}}
    assert dependency_anchors(inputs, {"revenue_claim": {"rev"}, "gp_claim": {"gp"}}) == {}


# ---------------------------------------------------------------------------
# The shared Evidence Fact Index
# ---------------------------------------------------------------------------


def _candidate(claim_id, polarity="activation", with_points=True):
    g = _ground(claim_id)
    return EvidenceFactCandidate(
        claim_id=claim_id, claim_text=RECORDS[claim_id]["claim"], assertion_status="asserted", semantic_polarity=polarity,
        linked_source_id="src_582ac24bf4319648" if False else None,
        data_stated=g.stated_keys if with_points else (), data_inputs=g.input_keys if with_points else (),
    )


def _groups(candidates):
    return sorted(sorted(c.claim_id.rsplit(":", 1)[1] for c in members) for members in group_evidence_candidates(candidates, "AMD"))


def test_derived_expressions_join_one_evidence_fact_and_other_data_stays_separate():
    ids = [FA + n for n in ("29", "31", "33", "36")]
    assert _groups([_candidate(c) for c in ids]) == [["29", "31", "33"], ["36"]]


def test_without_grounded_observations_the_index_groups_exactly_as_before():
    ids = [FA + n for n in ("29", "31", "33", "36")]
    assert _groups([_candidate(c, with_points=False) for c in ids]) == [["29"], ["31"], ["33"], ["36"]]


def test_an_opposite_polarity_is_a_contradiction_not_a_restatement():
    candidates = [_candidate(FA + "31"), _candidate(FA + "33", polarity="invalidation")]
    assert _groups(candidates) == [["31"], ["33"]]


# ---------------------------------------------------------------------------
# Production pipeline: the contract is opt-in, and legacy runs are untouched
# ---------------------------------------------------------------------------

TRIO = [FA + n for n in ("31", "33", "36")]


def _build_run(tmp_path, run_id, *, contract):
    run_dir = tmp_path / run_id
    run_dir.mkdir()

    def rebase(value):
        if isinstance(value, dict):
            return {k: (run_id if k == "run_id" else rebase(v)) for k, v in value.items()}
        if isinstance(value, list):
            return [rebase(v) for v in value]
        return value

    metadata = {"run_id": run_id, "ticker": "AMD", "analysis_date": FIXTURE["metadata"]["analysis_date"], "created_at": "2026-10-06T17:00:00Z"}
    if contract:
        metadata["fact_dependency_contract"] = FACT_DEPENDENCY_CONTRACT
    write = lambda name, data: (run_dir / name).write_text(json.dumps(data), encoding="utf-8")
    write("metadata.json", metadata)
    records = [rebase(r) for r in FIXTURE["records"]]
    write("structured_agent_outputs.json", {"run_id": run_id, "ticker": "AMD", "records": records})
    write("alpha_matches.json", {"run_id": run_id, "ticker": "AMD", "matches": [rebase(m) for m in FIXTURE["matches"]]})
    write("extracted_structures.json", {"run_id": run_id, "ticker": "AMD", "nodes": [], "edges": []})
    write("source_registry.json", {"schema_version": "source_registry.v2", "run_id": run_id, "ticker": "AMD", "source_count": len(SOURCES), "sources": SOURCES})
    write("raw_agent_outputs.json", {"run_id": run_id, "agent_outputs": [rebase(o) for o in FIXTURE["raw_outputs"]]})
    return run_dir


def _run_pipeline(run_dir):
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    routes_research._run_week3_graph_pipeline(run_dir, graph_repository=GraphPersistenceRepository(engine), require_verified_evidence_gate=True)
    return json.loads((run_dir / "structure_graph.json").read_text(encoding="utf-8"))


def _a301(graph):
    return next(a for a in graph["activation"]["alphas"] if a["alpha_id"] == "A301")


def test_a_newly_written_run_opts_in_to_the_fact_dependency_contract_and_an_old_run_does_not(tmp_path):
    from comqutor_alpha.adapters.tradingagents_output_writer import save_comqutor_run_outputs

    run_dir = save_comqutor_run_outputs(
        ticker="AMD", analysis_date="2026-10-06", final_state={"market_report": "Market report text.", "final_trade_decision": "Final decision."},
        output_root=tmp_path, selected_analysts=["market"], config={"llm_provider": "openai"},
    )
    new_metadata = json.loads((Path(run_dir) / "metadata.json").read_text(encoding="utf-8"))
    assert new_metadata["fact_dependency_contract"] == FACT_DEPENDENCY_CONTRACT
    assert "fact_dependency_contract" not in FIXTURE["metadata"]  # the saved AMD originals predate the field: legacy grouping, byte-identical


def test_legacy_run_keeps_three_separate_facts_and_the_dependency_contract_makes_it_two_with_the_same_score(tmp_path):
    legacy = _a301(_run_pipeline(_build_run(tmp_path, "t1_closure_legacy", contract=False)))
    graph = _run_pipeline(_build_run(tmp_path, "t1_closure_contract", contract=True))
    contract = _a301(graph)

    assert legacy["claim_ids"] == contract["claim_ids"] and len(contract["claim_ids"]) == 3  # every claim and citation kept
    assert legacy["unique_evidence_fact_count"] == 3
    assert contract["unique_evidence_fact_count"] == 2
    groups = {tuple(sorted(g["member_claim_ids"])) for g in contract["evidence_fact_groups"]}
    assert groups == {(FA + "31", FA + "33"), (FA + "36",)}
    # the score was already carried by claim 31 (max per fact); counting 33 as a second fact never added to it
    assert contract["activation_score"] == legacy["activation_score"] == pytest.approx(21.3056, abs=1e-4)
    assert graph["fact_dependency_contract"] == {"contract": FACT_DEPENDENCY_CONTRACT, "claims_with_grounded_observations": graph["fact_dependency_contract"]["claims_with_grounded_observations"]}
    assert graph["fact_dependency_contract"]["claims_with_grounded_observations"] >= 3


def test_legacy_run_has_no_contract_marker_and_no_trace_artifact(tmp_path):
    run_dir = _build_run(tmp_path, "t1_closure_legacy2", contract=False)
    graph = _run_pipeline(run_dir)
    assert "fact_dependency_contract" not in graph
    assert not (run_dir / "evidence_trace.json").exists()


def test_a_contract_run_writes_the_trace_artifact_lists_it_in_the_manifest_and_exports_it(tmp_path):
    run_dir = _build_run(tmp_path, "t1_closure_export", contract=True)
    _run_pipeline(run_dir)
    # finalize_completed_run_artifacts is called by the pipeline itself, and the manifest is written by the completion flow
    manifest = build_and_write_artifact_manifest(run_id=run_dir.name, ticker="AMD", output_root=tmp_path)
    assert (run_dir / "evidence_trace.json").exists()
    assert "evidence_trace.json" in {a["artifact_name"] for a in manifest["artifacts"] if a["exists"]}
    status, content_type, raw, _filename, _err = routes_research.get_run_export_bundle(run_dir.name, tmp_path)
    assert status == 200 and content_type == "application/zip"
    with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
        exported = json.loads(bundle.read("evidence_trace.json"))
    saved = json.loads((run_dir / "evidence_trace.json").read_text(encoding="utf-8"))
    assert exported == saved
    # the exported trace carries the same independent-fact count the scoring used
    a301 = next(a for a in saved["alphas"] if a["alpha_id"] == "A301")
    assert (a301["claims_in_pool"], a301["independent_facts"]) == (3, 2)
    assert saved["items"][FA + "33"]["dependency"]["depends_on"] == FA + "31"
    assert saved["items"][FA + "31"]["dependency"]["depended_by"] == [FA + "33"]


# ---------------------------------------------------------------------------
# The trace: four separate statuses
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def contract_ctx(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("t1_closure_trace")
    run_dir = _build_run(tmp_path, "t1_closure_trace", contract=True)
    _run_pipeline(run_dir)
    return load_trace_context(run_dir.name, tmp_path), tmp_path, run_dir.name


def _trace(contract_ctx, claim_id):
    return build_claim_trace(contract_ctx[0], claim_id)


def test_claim_31_trace_shows_the_material_its_location_and_the_four_statuses_separately(contract_ctx):
    trace = _trace(contract_ctx, FA + "31")
    assert trace["summary"] == {"source_support": "VERIFIED_SUPPORT", "alpha_match": "MATCHED", "stance": "RULE_ONLY", "scoring": "IN_OFFICIAL_POOL"}
    support = trace["source_support"]["content_support"]
    assert support["used_location"] == "excerpt and data_snapshot.periods for Total Revenue"
    assert "2026-06-30=11536000000.0" in support["supporting_quote_or_data"]
    assert (support["status"], support["method"], support["support_basis"]) == ("SUPPORTS", "LLM_CONTENT_SUPPORT_VERIFIED", "DIRECT_FACT")
    assert trace["source_support"]["eligibility"]["eligible"] is True
    assert trace["source_support"]["eligibility"]["time_basis"]["basis"] == "REGISTRY_WRITE_TIME_UPPER_BOUND"
    source = trace["sources"][0]
    assert source["role"] == "verified_basis" and source["has_saved_content"] and source["content_hash"]
    row = source["material_rows"][0]
    assert row["label"] == "Total Revenue" and [c["used"] for c in row["cells"]] == [True] * 5
    assert trace["claim"]["report_location"]["char_offset"] is not None
    assert "Revenue acceleration is dramatic" in trace["claim"]["report_location"]["paragraph"]
    # stance is a rule result, and the weight is a rule score: neither is presented as a model judgment
    assert trace["stance"]["method"] == "deterministic" and "never obtained" in trace["stance"]["reason"]
    assert trace["scoring"]["weight_contribution"] == pytest.approx(0.1873)


def test_a_zero_rule_score_is_reported_as_a_rule_score_not_as_a_model_judgment_of_zero(contract_ctx):
    trace = _trace(contract_ctx, FA + "36")
    scoring = trace["scoring"]
    assert scoring["status_code"] == "IN_POOL_ZERO_WEIGHT" and scoring["weight_contribution"] == 0.0
    assert "NOT a model judgment" in scoring["reason"]


def test_claims_merged_by_dependency_keep_their_own_citations_and_show_the_relationship(contract_ctx):
    t33 = _trace(contract_ctx, FA + "33")
    assert t33["sources"] and t33["sources"][0]["source_id"] == "src_582ac24bf4319648"
    assert t33["dependency"]["same_evidence_fact_members"] == [FA + "31", FA + "33"]
    assert t33["dependency"]["depends_on"] == FA + "31" and t33["dependency"]["depended_by"] == []
    assert _trace(contract_ctx, FA + "36")["dependency"]["same_evidence_fact_members"] == [FA + "36"]


def test_an_agent_writing_verified_never_substitutes_for_the_system_result(contract_ctx):
    verified_word = _trace(contract_ctx, PM + "3")
    assert verified_word["claim"]["agent_wording"]["self_labeled_verified"] is True
    assert verified_word["source_support"]["status_code"] == "NOT_LINKED"
    assert "not a system verification" in verified_word["claim"]["agent_wording"]["note"]
    claim_29 = _trace(contract_ctx, FA + "29")
    assert claim_29["claim"]["agent_wording"]["self_labeled_verified"] is True
    assert claim_29["source_support"]["status_code"] == "TECHNICAL_INCOMPLETE"
    assert "quote or data could not be located" in claim_29["source_support"]["reason"]
    assert _trace(contract_ctx, FA + "31")["claim"]["agent_wording"]["self_labeled_verified"] is False


@pytest.mark.parametrize(
    ("claim_id", "code", "needle"),
    [
        (PM + "4", "TECHNICAL_INCOMPLETE", "quote or data could not be located"),
        (PM + "44", "TECHNICAL_INCOMPLETE", "timed out"),
        (PM + "25", "PARTIAL_SUPPORT", "Not backed by the source"),
        (PM + "20", "MODEL_JUDGED_INSUFFICIENT", ""),
        (PM + "60", "BACKGROUND_ONLY", ""),
        (PM + "10", "VERIFIED_SUPPORT", ""),
        (PM + "3", "NOT_LINKED", "not verified"),
    ],
)
def test_each_source_support_failure_mode_has_its_own_code_and_reason(contract_ctx, claim_id, code, needle):
    status = _trace(contract_ctx, claim_id)["source_support"]
    assert status["status_code"] == code and needle in status["reason"]


def test_a_verified_claim_whose_relation_is_unresolved_is_reported_as_unresolved_not_as_unsupportive(contract_ctx):
    trace = _trace(contract_ctx, PM + "10")
    assert trace["summary"]["source_support"] == "VERIFIED_SUPPORT"
    assert trace["alpha_match"]["matched_alpha"] == "A304"
    assert trace["stance"]["status_code"] == "RELATION_UNRESOLVED" and trace["stance"]["relation"] == "mention"
    assert "No model stance judgment was obtained" in trace["stance"]["reason"]
    assert trace["scoring"]["not_scored_code"] == "RELATION_NOT_SUPPORTING" and not trace["scoring"]["in_official_pool"]
    assert [s["role"] for s in trace["sources"]][0] in {"verified_basis", "primary_link", "cited"}


def test_only_a_verification_that_actually_ran_names_a_source_it_used(contract_ctx):
    assert _trace(contract_ctx, FA + "31")["sources"][0]["role"] == "verified_basis"
    failed = _trace(contract_ctx, PM + "4")  # the verification timed out / its quote was not found: nothing was used
    assert failed["source_support"]["status_code"] == "TECHNICAL_INCOMPLETE"
    assert {s["role"] for s in failed["sources"]} <= {"primary_link", "cited"}


def test_a_reproduced_calculation_is_recorded_with_inputs_but_never_upgrades_the_claims_verification(contract_ctx):
    trace = _trace(contract_ctx, PM + "4")  # "gross margin reset from 39.8% to 53.8%" -- reproducible; verification incomplete
    calcs = trace["calculation"]["derived_calculations"]
    assert {c["stated_token"] for c in calcs} >= {"39.8%", "53.8%"} and all(c["status"] == "REPRODUCED" for c in calcs)
    assert all(i["content_hash"] for c in calcs for i in c["inputs"])
    assert "arithmetic" in trace["calculation"]["scope_note"]
    assert trace["calculation"]["numbers_not_found_in_saved_data"] == []
    assert _trace(contract_ctx, PM + "10")["calculation"]["numbers_not_found_in_saved_data"] == ["$1.38"]
    assert trace["source_support"]["status_code"] == "TECHNICAL_INCOMPLETE"  # the calculation holds; the claim is still not verified
    artifact = build_evidence_trace_artifact(contract_ctx[0].run_id, contract_ctx[1], ctx=contract_ctx[0])
    summary = artifact["calculations"]
    assert summary["reproduced_calculation_count"] >= 2 and "arithmetic only" in summary["scope_note"]
    assert PM + "4" in {c["claim_id"] for c in summary["calculations"]}


def test_key_conclusions_cover_the_final_decision_chain_with_all_four_statuses_per_row(contract_ctx):
    ctx = contract_ctx[0]
    key = build_key_conclusions(ctx)
    rows = [row for group in key["groups"] for row in group["rows"]]
    assert rows and {r["agent"] for r in rows} == {"portfolio_manager"}  # the fixture holds only PM decision-chain claims
    for row in rows:
        assert {"source_support", "alpha_match", "stance", "scoring"} <= row.keys()
        assert row["source_support"]["status_code"] and row["scoring"]["reason"]
    assert key["agent_wording_verified_count"] >= 1
    assert key["rule"].startswith("Claims written by the final-decision agents")
    assert key_conclusion_group(RECORDS[FA + "31"]) is None  # an analyst's claim is not part of the decision chain


def test_the_exported_artifact_holds_every_official_pool_claim_and_every_key_conclusion(contract_ctx):
    ctx = contract_ctx[0]
    artifact = build_evidence_trace_artifact(ctx.run_id, contract_ctx[1], ctx=ctx)
    assert set(TRIO) <= set(artifact["items"])
    assert {r["claim_id"] for g in artifact["key_conclusions"]["groups"] for r in g["rows"]} <= set(artifact["items"])
    assert artifact["schema_version"] == "evidence_trace.v1" and artifact["contracts"]["fact_dependency_contract"] == FACT_DEPENDENCY_CONTRACT


# ---------------------------------------------------------------------------
# API route
# ---------------------------------------------------------------------------


def test_evidence_trace_route_serves_one_claim_the_key_view_and_safe_errors(contract_ctx):
    from fastapi import FastAPI

    _ctx, root, run_id = contract_ctx
    app = FastAPI()  # the real router with the run's own output root; no lifespan, so no database or job manager is touched
    app.include_router(routes_research.router)
    app.state.output_root = str(root)
    client = TestClient(app)
    one = client.get(f"/api/research/{run_id}/evidence-trace", params={"claim_id": FA + "31"}).json()
    assert one["status"] == "ok" and one["item"]["summary"]["source_support"] == "VERIFIED_SUPPORT"
    assert one["item"] == build_claim_trace(contract_ctx[0], FA + "31")  # the route and the exported builder agree
    key = client.get(f"/api/research/{run_id}/evidence-trace", params={"scope": "key"}).json()
    assert key["status"] == "ok" and key["key_conclusions"]["claim_count"] >= 7
    assert client.get(f"/api/research/{run_id}/evidence-trace", params={"claim_id": "nope"}).json()["error_code"] == "CLAIM_NOT_FOUND"
    assert client.get("/api/research/no_such_run/evidence-trace").json()["error_code"] == "RUN_NOT_FOUND"
    assert get_evidence_trace_response("../x", root)["error_code"] == "INVALID_RUN_ID"
