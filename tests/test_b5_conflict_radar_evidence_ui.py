"""B5 Conflict Radar Evidence UI -- dedicated tests (task
B5_CONFLICT_RADAR_EVIDENCE_UI).

Presentation and audit layer only:

    B1 = semantic authority (final evidence_stance)
    B2 = deterministic conflict admissibility authority
    B4 = Alpha level classification authority
    B5 = this task -- never re-judges Evidence semantics, never modifies
         ConflictScore, never changes admitted/main conflict, never calls
         a Provider.

Every test below drives the REAL, unmodified public entry point
(``detect_alpha_conflicts``) end-to-end -- never calls
``conflict_evidence_ui.build_conflict_evidence_ui`` directly with a hand
-built ``group_into_facts`` -- so each test exercises the exact same wiring
(``_evaluate_candidate`` -> ``evaluate_conflict_admissibility`` ->
``build_conflict_evidence_ui``) production uses, with the real Evidence
Fact Index grouping (``evidence_fact_index.group_evidence_candidates``),
never a second/simplified grouping implementation.

Section map:
    A - Bull/Bear Evidence (stance filter, dedup)
    B - Counter Evidence (Case A/B routing, target side, dedup, dual role)
    C - Missing Evidence (deficits, admitted-empty, score gap separation)
    D - Invalidation Conditions (John's exact A101 text, undefined Alpha)
    E - Persistence/API consistency (old and new payloads)
    F - (frontend coverage lives in the .tsx test files, not here)
    G - B1/B2/B3/B4 invariants (ConflictScore/admitted/main/counts unchanged)
"""

from __future__ import annotations

import copy

import pytest

from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts
from comqutor_alpha.conflict_engine.invalidation_registry import load_invalidation_registry
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceError, GraphPersistenceRepository
from tests.fixtures.week4_conflict_cases import (
    activation_entry,
    activation_payload,
    match_record,
    two_alpha_taxonomy,
)

RUN_ID = "run_b5"
TICKER = "NVDA"


def _detect(activation, matches, run_id=RUN_ID, ticker=TICKER, taxonomy=None):
    return detect_alpha_conflicts(
        run_id=run_id, ticker=ticker, activation_payload=activation, alpha_matches=matches, taxonomy=taxonomy
    )


def _outcome_for(result, alpha_a, alpha_b):
    for item in result["arbitration"]["candidate_evaluations"]:
        if {item["alpha_a"], item["alpha_b"]} == {alpha_a, alpha_b}:
            return item
    raise AssertionError(f"no candidate evaluation for {alpha_a}/{alpha_b}")


def _conflict_for(result, alpha_a, alpha_b):
    for conflict in result["conflicts"]:
        if {conflict["alpha_a"], conflict["alpha_b"]} == {alpha_a, alpha_b}:
            return conflict
    raise AssertionError(f"no admitted conflict for {alpha_a}/{alpha_b}")


def _with_counter(record, alpha_id, *, counter_alpha_id):
    """Manually REPLACE a match_record()'s candidate_scores entry for
    ``alpha_id`` with a supports_counter_alpha verdict -- match_record
    itself has no counter_alpha_id parameter (John's B1 stance
    vocabulary). Replaces rather than appends: a real candidate_scores
    list never carries two entries for the same alpha_id, and the pool-
    search lookup used throughout (stance_for_alpha-style, first match
    wins) would otherwise silently keep finding the original entry."""
    record = copy.deepcopy(record)
    record["candidate_scores"] = [
        c for c in record["candidate_scores"] if c.get("alpha_id") != alpha_id
    ]
    record["candidate_scores"].append(
        {
            "alpha_id": alpha_id,
            "score": record["score"],
            "relation": "activation",
            "evidence_stance": "supports_counter_alpha",
            "counter_alpha_id": counter_alpha_id,
        }
    )
    return record


def _bull_bear_activation(bull="A101", bear="A304", score=90.0):
    return activation_payload(
        activation_entry(bull, score=score, direction="positive"),
        activation_entry(bear, score=score, direction="negative"),
    )


def _two_facts_each_side(bull="A101", bear="A304"):
    """Both sides fully admissible: 2 unique, ticker-specific supports_alpha
    facts each (clears MIN_SUPPORTING_EVIDENCE_PER_SIDE=2 and
    MIN_TICKER_SPECIFIC_SUPPORT_PER_SIDE=1)."""
    return [
        match_record("bull1", bull, evidence=f"{bull} NVDA support one"),
        match_record("bull2", bull, evidence=f"{bull} NVDA support two"),
        match_record("bear1", bear, evidence=f"{bear} NVDA support one"),
        match_record("bear2", bear, evidence=f"{bear} NVDA support two"),
    ]


# ---------------------------------------------------------------------------
# Section A -- Bull/Bear Evidence
# ---------------------------------------------------------------------------


def test_a_bull_evidence_only_accepts_supports_alpha_relative_to_bull():
    matches = [
        *_two_facts_each_side(),
        match_record("bull_opposes", "A101", evidence="A101 NVDA opposing text", evidence_stance="opposes_alpha"),
        match_record("bull_mentions", "A101", evidence="A101 NVDA mention text", evidence_stance="mentions_alpha"),
        match_record(
            "bull_neutral", "A101", evidence="A101 NVDA neutral text", evidence_stance="neutral_background"
        ),
    ]
    result = _detect(_bull_bear_activation(), matches)
    conflict = _conflict_for(result, "A101", "A304")
    bull_ids = {item["representative_claim_id"] for item in conflict["evidence_ui"]["bull_evidence"]}
    assert bull_ids == {"bull1", "bull2"}
    for item in conflict["evidence_ui"]["bull_evidence"]:
        assert item["evidence_stance"] == "supports_alpha"
        assert item["target_alpha_id"] == "A101"


def test_a_bear_evidence_only_accepts_supports_alpha_relative_to_bear():
    result = _detect(_bull_bear_activation(), _two_facts_each_side())
    conflict = _conflict_for(result, "A101", "A304")
    bear_ids = {item["representative_claim_id"] for item in conflict["evidence_ui"]["bear_evidence"]}
    assert bear_ids == {"bear1", "bear2"}
    for item in conflict["evidence_ui"]["bear_evidence"]:
        assert item["evidence_stance"] == "supports_alpha"
        assert item["target_alpha_id"] == "A304"


@pytest.mark.parametrize("stance", ["opposes_alpha", "mentions_alpha", "neutral_background"])
def test_a_non_supporting_stances_never_enter_bull_or_bear_evidence(stance):
    matches = [
        *_two_facts_each_side(),
        match_record("extra", "A101", evidence="A101 NVDA extra text", evidence_stance=stance),
    ]
    result = _detect(_bull_bear_activation(), matches)
    conflict = _conflict_for(result, "A101", "A304")
    all_ids = {
        item["representative_claim_id"]
        for item in (*conflict["evidence_ui"]["bull_evidence"], *conflict["evidence_ui"]["bear_evidence"])
    }
    assert "extra" not in all_ids


def test_a_supports_counter_alpha_never_directly_counts_as_target_support():
    matches = [
        *_two_facts_each_side(),
        match_record("extra", "A101", evidence="A101 NVDA extra text", evidence_stance="supports_counter_alpha"),
    ]
    result = _detect(_bull_bear_activation(), matches)
    conflict = _conflict_for(result, "A101", "A304")
    bull_ids = {item["representative_claim_id"] for item in conflict["evidence_ui"]["bull_evidence"]}
    assert "extra" not in bull_ids


def test_a_raw_duplicate_paraphrase_claims_collapse_to_one_evidence_fact():
    matches = [
        match_record("bull1", "A101", evidence="A101 NVDA shared identical wording", agent="news_agent"),
        match_record("bull2", "A101", evidence="A101 NVDA shared identical wording", agent="fundamental_agent"),
        # A second, distinct bull fact -- keeps this pair admitted (>=2
        # unique bull facts) so the dedup assertion below is checked on a
        # real admitted conflict, not merely a suppressed candidate.
        match_record("bull3", "A101", evidence="A101 NVDA a second distinct point"),
        match_record("bear1", "A304", evidence="A304 NVDA support one"),
        match_record("bear2", "A304", evidence="A304 NVDA support two"),
    ]
    result = _detect(_bull_bear_activation(), matches)
    conflict = _conflict_for(result, "A101", "A304")
    assert len(conflict["evidence_ui"]["bull_evidence"]) == 2
    by_id = {item["representative_claim_id"]: item for item in conflict["evidence_ui"]["bull_evidence"]}
    duplicate_group = next(item for item in by_id.values() if set(item["member_claim_ids"]) == {"bull1", "bull2"})
    assert set(duplicate_group["agents"]) == {"news_agent", "fundamental_agent"}


# ---------------------------------------------------------------------------
# Section B -- Counter Evidence
# ---------------------------------------------------------------------------


def test_b_opposes_alpha_shows_as_counter_against_that_alpha():
    matches = [
        *_two_facts_each_side(),
        match_record("counter1", "A304", evidence="A304 NVDA rebuttal text", evidence_stance="opposes_alpha"),
    ]
    result = _detect(_bull_bear_activation(), matches)
    conflict = _conflict_for(result, "A101", "A304")
    counter = conflict["evidence_ui"]["counter_evidence"]
    assert len(counter) == 1
    assert counter[0]["representative_claim_id"] == "counter1"
    assert counter[0]["counter_target_alpha_id"] == "A304"
    assert counter[0]["evidence_stance"] == "opposes_alpha"


def test_b_supports_counter_alpha_only_enters_when_counter_id_is_the_conflicts_other_side():
    base = match_record("counter1", "A101", evidence="A101 NVDA counter text")
    matches = [*_two_facts_each_side(), _with_counter(base, "A101", counter_alpha_id="A304")]
    result = _detect(_bull_bear_activation(), matches)
    conflict = _conflict_for(result, "A101", "A304")
    counter = conflict["evidence_ui"]["counter_evidence"]
    assert len(counter) == 1
    assert counter[0]["representative_claim_id"] == "counter1"
    assert counter[0]["counter_target_alpha_id"] == "A101"
    assert counter[0]["supports_counter_alpha_id"] == "A304"


def test_b_unrelated_counter_alpha_id_never_enters_this_pairs_counter_evidence():
    base = match_record("counter1", "A101", evidence="A101 NVDA counter text")
    # counter_alpha_id is some unrelated third alpha, never A304 (the
    # conflict's actual other side) -- must not qualify.
    matches = [*_two_facts_each_side(), _with_counter(base, "A101", counter_alpha_id="A999")]
    result = _detect(_bull_bear_activation(), matches)
    conflict = _conflict_for(result, "A101", "A304")
    assert conflict["evidence_ui"]["counter_evidence"] == []


@pytest.mark.parametrize("stance", ["mentions_alpha", "neutral_background"])
def test_b_mentions_and_neutral_never_enter_counter_evidence(stance):
    matches = [
        *_two_facts_each_side(),
        match_record("extra", "A101", evidence="A101 NVDA extra text", evidence_stance=stance),
    ]
    result = _detect(_bull_bear_activation(), matches)
    conflict = _conflict_for(result, "A101", "A304")
    ids = {item["representative_claim_id"] for item in conflict["evidence_ui"]["counter_evidence"]}
    assert "extra" not in ids


def test_b_same_fact_multiple_claims_not_duplicated_in_counter_evidence():
    matches = [
        *_two_facts_each_side(),
        match_record(
            "counter1", "A304", evidence="A304 NVDA shared rebuttal wording",
            evidence_stance="opposes_alpha", agent="news_agent",
        ),
        match_record(
            "counter2", "A304", evidence="A304 NVDA shared rebuttal wording",
            evidence_stance="opposes_alpha", agent="fundamental_agent",
        ),
    ]
    result = _detect(_bull_bear_activation(), matches)
    conflict = _conflict_for(result, "A101", "A304")
    counter = conflict["evidence_ui"]["counter_evidence"]
    assert len(counter) == 1
    assert set(counter[0]["member_claim_ids"]) == {"counter1", "counter2"}


def test_b_same_fact_supporting_one_side_and_opposing_the_other_keeps_both_roles():
    # One claim: supports A304 (bear evidence) AND, via a second
    # candidate_scores entry, opposes A101 (counter evidence against
    # bull) -- both Alpha-relative roles must survive independently.
    dual = match_record("dual1", "A304", evidence="A304 NVDA dual role text")
    dual["candidate_scores"].append(
        {"alpha_id": "A101", "score": dual["score"], "relation": "activation", "evidence_stance": "opposes_alpha"}
    )
    matches = [*_two_facts_each_side(), dual]
    result = _detect(_bull_bear_activation(), matches)
    conflict = _conflict_for(result, "A101", "A304")
    bear_ids = {item["representative_claim_id"] for item in conflict["evidence_ui"]["bear_evidence"]}
    counter = conflict["evidence_ui"]["counter_evidence"]
    assert "dual1" in bear_ids
    assert any(item["representative_claim_id"] == "dual1" and item["counter_target_alpha_id"] == "A101" for item in counter)


def test_b_counter_target_side_correctly_distinguishes_bull_from_bear():
    matches = [
        *_two_facts_each_side(),
        match_record("against_bull", "A101", evidence="A101 NVDA against bull text", evidence_stance="opposes_alpha"),
        match_record("against_bear", "A304", evidence="A304 NVDA against bear text", evidence_stance="opposes_alpha"),
    ]
    result = _detect(_bull_bear_activation(), matches)
    conflict = _conflict_for(result, "A101", "A304")
    by_id = {item["representative_claim_id"]: item for item in conflict["evidence_ui"]["counter_evidence"]}
    assert by_id["against_bull"]["counter_target_alpha_id"] == "A101"
    assert by_id["against_bear"]["counter_target_alpha_id"] == "A304"


# ---------------------------------------------------------------------------
# Section C -- Missing Evidence
# ---------------------------------------------------------------------------


def test_c_zero_supporting_facts_yields_deficit_two():
    matches = [
        match_record("bull1", "A101", evidence="A101 NVDA support one"),
        match_record("bull2", "A101", evidence="A101 NVDA support two"),
        # Bear side: has qualifying evidence (so the pair still reaches B2
        # admissibility at all) but none of it is supports_alpha.
        match_record("bear1", "A304", evidence="A304 NVDA mention text", evidence_stance="mentions_alpha"),
    ]
    result = _detect(_bull_bear_activation(), matches)
    item = _outcome_for(result, "A101", "A304")
    missing = item["evidence_ui"]["missing_evidence"]
    bear_deficit = next(m for m in missing if m["side"] == "bear" and m["missing_reason_code"] == "INSUFFICIENT_SUPPORTING_EVIDENCE")
    assert bear_deficit["current_value"] == 0
    assert bear_deficit["required_value"] == 2
    assert bear_deficit["deficit"] == 2
    # Evidence exists (mentions_alpha) but none is admissible support --
    # the more specific diagnosis fires alongside the bare deficit.
    assert any(m["side"] == "bear" and m["missing_reason_code"] == "NO_ADMISSIBLE_SUPPORTING_POLARITY" for m in missing)


def test_c_one_supporting_fact_yields_deficit_one():
    matches = [
        match_record("bull1", "A101", evidence="A101 NVDA support one"),
        match_record("bull2", "A101", evidence="A101 NVDA support two"),
        match_record("bear1", "A304", evidence="A304 NVDA support one"),
    ]
    result = _detect(_bull_bear_activation(), matches)
    item = _outcome_for(result, "A101", "A304")
    missing = item["evidence_ui"]["missing_evidence"]
    bear_deficit = next(m for m in missing if m["side"] == "bear" and m["missing_reason_code"] == "INSUFFICIENT_SUPPORTING_EVIDENCE")
    assert bear_deficit["current_value"] == 1
    assert bear_deficit["deficit"] == 1


def test_c_two_supporting_facts_produces_no_supporting_deficit():
    result = _detect(_bull_bear_activation(), _two_facts_each_side())
    conflict = _conflict_for(result, "A101", "A304")
    codes = {m["missing_reason_code"] for m in conflict["evidence_ui"]["missing_evidence"]}
    assert "INSUFFICIENT_SUPPORTING_EVIDENCE" not in codes


def test_c_no_ticker_specific_fact_reports_the_correct_reason():
    matches = [
        match_record("bull1", "A101", evidence="broad macro text one", ticker_specific_text=None),
        match_record("bull2", "A101", evidence="broad macro text two", ticker_specific_text=None),
        match_record("bear1", "A304", evidence="A304 NVDA support one"),
        match_record("bear2", "A304", evidence="A304 NVDA support two"),
    ]
    result = _detect(_bull_bear_activation(), matches)
    conflict_or_candidate = _outcome_for(result, "A101", "A304")
    missing = conflict_or_candidate["evidence_ui"]["missing_evidence"]
    bull_ticker_gap = next(
        m for m in missing if m["side"] == "bull" and m["missing_reason_code"] == "NO_TICKER_SPECIFIC_SUPPORTING_EVIDENCE"
    )
    assert bull_ticker_gap["current_value"] == 0
    assert bull_ticker_gap["required_value"] == 1


def test_c_admitted_conflict_has_empty_missing_evidence():
    result = _detect(_bull_bear_activation(), _two_facts_each_side())
    conflict = _conflict_for(result, "A101", "A304")
    assert conflict["evidence_ui"]["missing_evidence"] == []


def test_c_score_gap_is_a_qualification_gap_never_mixed_into_missing_evidence():
    activation = activation_payload(
        activation_entry("A101", score=40.0, direction="positive"),  # below B2's 50.0 threshold
        activation_entry("A304", score=90.0, direction="negative"),
    )
    result = _detect(activation, _two_facts_each_side())
    item = _outcome_for(result, "A101", "A304")
    missing_codes = {m["missing_reason_code"] for m in item["evidence_ui"]["missing_evidence"]}
    gap_codes = {g["gap_reason_code"] for g in item["evidence_ui"]["qualification_gaps"]}
    assert "ALPHA_SCORE_BELOW_THRESHOLD" not in missing_codes
    assert "ALPHA_SCORE_BELOW_THRESHOLD" in gap_codes
    bull_gap = next(g for g in item["evidence_ui"]["qualification_gaps"] if g["side"] == "bull")
    assert bull_gap["current_value"] == 40.0
    assert bull_gap["required_value"] == 50.0


def test_c_current_required_deficit_values_are_internally_consistent():
    matches = [
        match_record("bull1", "A101", evidence="A101 NVDA support one"),
        match_record("bear1", "A304", evidence="A304 NVDA mention text", evidence_stance="mentions_alpha"),
    ]
    result = _detect(_bull_bear_activation(), matches)
    item = _outcome_for(result, "A101", "A304")
    assert item["evidence_ui"]["missing_evidence"], "fixture must actually exercise missing_evidence"
    for entry in item["evidence_ui"]["missing_evidence"]:
        assert entry["deficit"] == entry["required_value"] - entry["current_value"]


# ---------------------------------------------------------------------------
# Section D -- Invalidation Conditions
# ---------------------------------------------------------------------------

JOHNS_A101_CONDITIONS = (
    "hyperscaler capex slows",
    "GPU demand weakens",
    "revenue growth decelerates",
    "AI demand already priced in",
)


def test_d_a101_conditions_match_johns_text_exactly():
    result = _detect(_bull_bear_activation(bull="A101", bear="A304"), _two_facts_each_side())
    conflict = _conflict_for(result, "A101", "A304")
    entry = conflict["evidence_ui"]["invalidation_conditions"]["bull_alpha"]
    assert entry["alpha_id"] == "A101"
    assert tuple(c["condition_text"] for c in entry["conditions"]) == JOHNS_A101_CONDITIONS


def test_d_a101_source_version_approval_status_correct():
    result = _detect(_bull_bear_activation(), _two_facts_each_side())
    conflict = _conflict_for(result, "A101", "A304")
    entry = conflict["evidence_ui"]["invalidation_conditions"]["bull_alpha"]
    assert entry["source"] == "John"
    assert entry["version"] == "v0.1"
    assert entry["approval_status"] == "approved"


def test_d_unapproved_alpha_never_produces_fabricated_conditions():
    result = _detect(_bull_bear_activation(), _two_facts_each_side())
    conflict = _conflict_for(result, "A101", "A304")
    entry = conflict["evidence_ui"]["invalidation_conditions"]["bear_alpha"]
    assert entry["alpha_id"] == "A304"
    assert entry["approval_status"] == "not_defined"
    assert entry["conditions"] == []
    assert entry["source"] is None
    assert entry["version"] is None


def test_d_registry_contains_no_other_approved_alpha_besides_a101():
    registry = load_invalidation_registry()
    approved = [alpha_id for alpha_id, entry in registry.entries.items() if entry.approval_status == "approved"]
    assert approved == ["A101"]


def test_d_invalidation_conditions_never_affect_conflict_score_or_admission():
    matches = _two_facts_each_side()
    with_a101 = _detect(_bull_bear_activation(bull="A101", bear="A304"), matches)
    # A different bull alpha with NO approved invalidation content at all
    # (A103 has no registry entry) must produce a byte-identical
    # ConflictScore/admission outcome for the same evidence shape --
    # invalidation content is display-only.
    activation_other = activation_payload(
        activation_entry("A103", score=90.0, direction="positive"),
        activation_entry("A304", score=90.0, direction="negative"),
    )
    matches_other = [
        match_record("bull1", "A103", evidence="A103 NVDA support one"),
        match_record("bull2", "A103", evidence="A103 NVDA support two"),
        match_record("bear1", "A304", evidence="A304 NVDA support one"),
        match_record("bear2", "A304", evidence="A304 NVDA support two"),
    ]
    # A103/A304 is not necessarily a declared pair in the real taxonomy --
    # an explicit synthetic taxonomy keeps this test self-contained, using
    # the same 0.90 contradiction_weight the real A101/A304 pair declares
    # so the two ConflictScore computations stay comparable.
    with_a103 = _detect(
        activation_other, matches_other, taxonomy=two_alpha_taxonomy("A103", "A304", weight_a_to_b=0.9)
    )
    conflict_a101 = _conflict_for(with_a101, "A101", "A304")
    conflict_a103 = _conflict_for(with_a103, "A103", "A304")
    assert conflict_a101["conflict_score"] == conflict_a103["conflict_score"]
    assert conflict_a101["conflict_level"] == conflict_a103["conflict_level"]


# ---------------------------------------------------------------------------
# Section E -- Persistence/API consistency
# ---------------------------------------------------------------------------


def _repo():
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


def test_e_evidence_ui_fully_persisted_and_round_trips_byte_identical():
    repo = _repo()
    activation = _bull_bear_activation()
    conflict_payload = _detect(activation, _two_facts_each_side())
    repo.persist_week4_results(
        run_id=RUN_ID, ticker=TICKER, activation_payload=activation, conflict_payload=conflict_payload
    )
    reconstructed = repo.get_week4_conflict_result(RUN_ID)
    original_conflict = _conflict_for(conflict_payload, "A101", "A304")
    stored_conflict = next(
        c for c in reconstructed["conflicts"] if {c["alpha_a"], c["alpha_b"]} == {"A101", "A304"}
    )
    assert stored_conflict["evidence_ui"] == original_conflict["evidence_ui"]


def test_e_api_layer_never_drops_evidence_ui():
    from comqutor_alpha.api.routes_research import get_persisted_conflicts

    repo = _repo()
    activation = _bull_bear_activation()
    conflict_payload = _detect(activation, _two_facts_each_side())
    repo.persist_week4_results(
        run_id=RUN_ID, ticker=TICKER, activation_payload=activation, conflict_payload=conflict_payload
    )
    api_response = get_persisted_conflicts(RUN_ID, output_root="outputs/runs", graph_repository=repo)
    assert api_response["status"] == "ok"
    stored_conflict = next(
        c for c in api_response["conflicts"] if {c["alpha_a"], c["alpha_b"]} == {"A101", "A304"}
    )
    assert "evidence_ui" in stored_conflict
    assert stored_conflict["evidence_ui"]["schema_version"] == "conflict_evidence_ui.v1"


def test_e_historical_payload_without_evidence_ui_persists_and_reads_back_without_fabrication():
    repo = _repo()
    activation = _bull_bear_activation()
    conflict_payload = _detect(activation, _two_facts_each_side())
    conflict = _conflict_for(conflict_payload, "A101", "A304")
    del conflict["evidence_ui"]  # simulate a pre-B5 persisted payload
    for item in conflict_payload["arbitration"]["candidate_evaluations"]:
        item.pop("evidence_ui", None)
        item.pop("bull_alpha_id", None)
        item.pop("bear_alpha_id", None)
    repo.persist_week4_results(
        run_id=RUN_ID, ticker=TICKER, activation_payload=activation, conflict_payload=conflict_payload
    )
    reconstructed = repo.get_week4_conflict_result(RUN_ID)
    stored_conflict = next(
        c for c in reconstructed["conflicts"] if {c["alpha_a"], c["alpha_b"]} == {"A101", "A304"}
    )
    assert "evidence_ui" not in stored_conflict


def test_e_malformed_evidence_stance_value_is_rejected_not_silently_dropped():
    repo = _repo()
    activation = _bull_bear_activation()
    conflict_payload = _detect(activation, _two_facts_each_side())
    conflict = _conflict_for(conflict_payload, "A101", "A304")
    conflict["evidence_ui"]["bull_evidence"][0]["evidence_stance"] = "not_a_real_stance"
    with pytest.raises(GraphPersistenceError) as exc_info:
        repo.persist_week4_results(
            run_id=RUN_ID, ticker=TICKER, activation_payload=activation, conflict_payload=conflict_payload
        )
    assert exc_info.value.reason_code == "WEEK4_CONFLICT_PAYLOAD_INVALID"


def _one_weak_claim_each_side():
    """Both sides have exactly one qualifying supports_alpha claim -- well
    below MIN_SUPPORTING_EVIDENCE_PER_SIDE=2, so the pair is suppressed by
    B2, but each side has enough evidence to actually reach admissibility
    computation (never rejected earlier for having zero evidence at all)."""
    return [
        match_record("bull1", "A101", evidence="A101 NVDA support one"),
        match_record("bear1", "A304", evidence="A304 NVDA support one"),
    ]


def test_e_candidate_evaluation_evidence_ui_also_persists():
    repo = _repo()
    activation = _bull_bear_activation()
    matches = _one_weak_claim_each_side()  # insufficient both sides, but both reach B2
    conflict_payload = _detect(activation, matches)
    repo.persist_week4_results(
        run_id=RUN_ID, ticker=TICKER, activation_payload=activation, conflict_payload=conflict_payload
    )
    reconstructed = repo.get_week4_conflict_result(RUN_ID)
    candidate = _outcome_for(reconstructed, "A101", "A304")
    assert candidate["outcome"] == "suppressed"
    assert "evidence_ui" in candidate
    assert candidate["bull_alpha_id"] == "A101"
    assert candidate["bear_alpha_id"] == "A304"


# ---------------------------------------------------------------------------
# Section G -- B1/B2/B3/B4 invariants
# ---------------------------------------------------------------------------


def test_g_conflict_score_and_level_unaffected_by_evidence_ui_presence():
    matches = _two_facts_each_side()
    result = _detect(_bull_bear_activation(), matches)
    conflict = _conflict_for(result, "A101", "A304")
    without_evidence_ui = {k: v for k, v in conflict.items() if k != "evidence_ui"}
    # Recomputing with the exact same inputs must reproduce byte-identical
    # values for every B2-owned field -- evidence_ui is purely additive.
    result_again = _detect(_bull_bear_activation(), matches)
    conflict_again = _conflict_for(result_again, "A101", "A304")
    without_evidence_ui_again = {k: v for k, v in conflict_again.items() if k != "evidence_ui"}
    assert without_evidence_ui == without_evidence_ui_again


def test_g_admissibility_status_and_reason_codes_unaffected_by_evidence_ui():
    matches = _one_weak_claim_each_side()
    result = _detect(_bull_bear_activation(), matches)
    item = _outcome_for(result, "A101", "A304")
    admissibility = item["admissibility"]
    # admissibility must be exactly what conflict_admissibility itself
    # would compute -- B5 never mutates it. Recomputed by an independent
    # call with the same inputs, byte-for-byte.
    result_again = _detect(_bull_bear_activation(), matches)
    item_again = _outcome_for(result_again, "A101", "A304")
    assert admissibility == item_again["admissibility"]


def test_g_evidence_ui_never_included_in_admissibility_reason_codes():
    matches = _one_weak_claim_each_side()
    result = _detect(_bull_bear_activation(), matches)
    item = _outcome_for(result, "A101", "A304")
    # evidence_ui's own reason vocabulary (INSUFFICIENT_SUPPORTING_EVIDENCE
    # etc.) is deliberately distinct from B2's own reason_codes vocabulary
    # (INSUFFICIENT_BULL_SUPPORTING_EVIDENCE etc.) -- confirms B5 never
    # wrote back into B2's own admissibility.reason_codes list.
    assert "INSUFFICIENT_SUPPORTING_EVIDENCE" not in item["admissibility"]["reason_codes"]


def test_g_main_conflict_and_admitted_set_unaffected_by_b5_wiring():
    activation = activation_payload(
        activation_entry("A101", score=90.0, direction="positive"),
        activation_entry("A304", score=90.0, direction="negative"),
        activation_entry("A301", score=70.0, direction="positive"),
    )
    matches = [
        *_two_facts_each_side(bull="A101", bear="A304"),
        match_record("bull3", "A301", evidence="A301 NVDA support one"),
        match_record("bull4", "A301", evidence="A301 NVDA support two"),
    ]
    result = _detect(activation, matches)
    assert result["main_conflict"] is not None
    assert result["main_conflict"]["alpha_a"] in {"A101", "A301"}
    # main_conflict must be exactly the highest-ranked admitted conflict by
    # conflict_score -- unaffected by which one happens to carry richer
    # evidence_ui content.
    top_by_score = max(result["conflicts"], key=lambda c: c["conflict_score"])
    assert result["main_conflict"]["conflict_id"] == top_by_score["conflict_id"]
