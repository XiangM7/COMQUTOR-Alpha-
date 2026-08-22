"""Exact Semantic Replay -- B1 evidence_stance_classifier artifact binding.

A B1 call does not produce its own artifact: its result mutates candidate
diagnostic dicts already inside alpha_matches.json's matches[].
candidate_scores. These tests build small, fully synthetic bundles (never
the live pipeline, never a Provider call) so each binding scenario is
exact and deterministic -- see semantic_binding.py::_bind_evidence_stance.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.llm_runtime.canonical_json import sha256_canonical_json
from comqutor_alpha.replay.semantic_binding import (
    build_semantic_binding_audit,
    verify_semantic_bindings,
)
from comqutor_alpha.replay.source_bundle import (
    EXACT_REPLAY_SEMANTIC_TASK_UNSUPPORTED,
    EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH,
    ExactReplayError,
    ExactSemanticSourceBundle,
)
from comqutor_alpha.structure_engine.evidence_stance_llm import LLM_CLASSIFIER_VERSION, LLM_TASK_NAME
from comqutor_alpha.structure_engine.week2_llm import _TASK_RUNTIME_METADATA, Week2LLMGateway

RUN_ID = "synthetic-b1-binding"
TICKER = "NVDA"


def _candidate(alpha_id: str, **overrides) -> dict:
    base = {
        "alpha_id": alpha_id,
        "alpha_name": load_alpha_taxonomy()[alpha_id].name_en,
        "score": 0.5,
        "keyword_score": 0.5,
        "factor_score": 0.0,
        "direction_score": 0.0,
        "semantic_score": 0.0,
        "relation": "activation",
        "eligible": True,
        "rejection_reason": None,
        "matched_keywords": [],
        "matched_factors": [],
        "ai_gate_passed": None,
        "evidence_stance": "neutral_background",
        "counter_alpha_id": None,
        "stance_reason_codes": [],
        "stance_confidence_band": None,
        "requires_manual_review": False,
        "evidence_stance_version": "evidence_stance.deterministic.v1",
        "stance_method": None,
        "stance_fallback_reason": None,
    }
    base.update(overrides)
    return base


def _match(claim_id: str, candidates: list[dict], *, matched_alpha: str | None = None, **overrides) -> dict:
    base = {
        "claim_id": claim_id,
        "ticker": TICKER,
        "claim": f"claim text for {claim_id}",
        "evidence": f"evidence text for {claim_id}",
        "candidate_scores": candidates,
        "matched_alpha": matched_alpha,
        "match_status": "matched" if matched_alpha else "no_match",
    }
    base.update(overrides)
    return base


def _stance_identity() -> dict:
    metadata = _TASK_RUNTIME_METADATA[LLM_TASK_NAME]
    return {
        "prompt_version": metadata["prompt_version"],
        "prompt_sha256": Week2LLMGateway.prompt_identity_sha256(LLM_TASK_NAME),
        "input_schema_version": metadata["input_schema_version"],
        "output_schema_version": metadata["output_schema_version"],
        "taxonomy_version": metadata["taxonomy_version"],
    }


def _stance_call(request_items: list[dict], response_items: list[dict], *, call_id: str = "call-1", **overrides) -> dict:
    input_payload = {"items": request_items}
    validated_output = {"items": response_items}
    record = {
        "call_id": call_id,
        "run_id": RUN_ID,
        "task": LLM_TASK_NAME,
        "input_payload": input_payload,
        "input_sha256": sha256_canonical_json(input_payload),
        "validated_output": validated_output,
        "validated_output_sha256": sha256_canonical_json(validated_output),
        **_stance_identity(),
    }
    record.update(overrides)
    return record


def _request_item(claim_id: str, target_alpha_id: str) -> dict:
    alpha = load_alpha_taxonomy()[target_alpha_id]
    return {
        "claim_id": claim_id,
        "target_alpha_id": target_alpha_id,
        "ticker": TICKER,
        "claim": f"claim text for {claim_id}",
        "evidence": f"evidence text for {claim_id}",
        "target_alpha_name": alpha.name_en,
        "target_alpha_definition": alpha.core_thesis,
    }


def _bundle(matches: list[dict], calls: list[dict]) -> ExactSemanticSourceBundle:
    return ExactSemanticSourceBundle(
        source_directory=Path("/nonexistent"),
        source_run_id=RUN_ID,
        ticker=TICKER,
        metadata={},
        raw_agent_outputs={},
        semantic_manifest={},
        semantic_calls=tuple(calls),
        structured_agent_outputs={"records": []},
        alpha_matches={"matches": matches},
        extracted_structures={"edges": []},
        structure_graph={},
        entity_alpha_exposures={},
        conflicts={},
        run_audit={},
        artifact_manifest={},
        source_files=(),
    )


# ---------------------------------------------------------------------------
# A. Single-item successful B1 binding
# ---------------------------------------------------------------------------


def test_a_single_item_successful_binding():
    candidate = _candidate(
        "A304",
        evidence_stance="supports_alpha",
        stance_method="llm",
        stance_fallback_reason=None,
        evidence_stance_version=LLM_CLASSIFIER_VERSION,
    )
    match = _match("C1", [candidate], matched_alpha="A304")
    call = _stance_call(
        [_request_item("C1", "A304")],
        [{"claim_id": "C1", "target_alpha_id": "A304", "stance": "supports_alpha"}],
    )
    audit = build_semantic_binding_audit(_bundle([match], [call]))
    assert audit["final_status"] == "PASS"
    assert "evidence_stance:C1:A304" in {
        key for binding in audit["bindings"] for key in binding["artifact_decision_keys"]
    }


# ---------------------------------------------------------------------------
# B. Wrong persisted stance
# ---------------------------------------------------------------------------


def test_b_wrong_persisted_stance_fails_closed():
    candidate = _candidate(
        "A304",
        evidence_stance="opposes_alpha",  # persisted differs from the semantic call's own "supports_alpha"
        stance_method="llm",
        stance_fallback_reason=None,
        evidence_stance_version=LLM_CLASSIFIER_VERSION,
    )
    match = _match("C1", [candidate], matched_alpha="A304")
    call = _stance_call(
        [_request_item("C1", "A304")],
        [{"claim_id": "C1", "target_alpha_id": "A304", "stance": "supports_alpha"}],
    )
    bundle = _bundle([match], [call])
    audit = build_semantic_binding_audit(bundle)
    assert audit["final_status"] == "FAIL"
    assert any("C1:A304" in item for item in audit["artifact_decision_mismatches"])
    with pytest.raises(ExactReplayError) as caught:
        verify_semantic_bindings(bundle)
    assert caught.value.reason_code == "EXACT_REPLAY_SEMANTIC_OUTPUT_MISMATCH"


# ---------------------------------------------------------------------------
# C. Wrong target Alpha (candidate not found)
# ---------------------------------------------------------------------------


def test_c_target_alpha_candidate_not_found_fails_closed():
    candidate = _candidate("A301", evidence_stance="supports_alpha", stance_method="llm", evidence_stance_version=LLM_CLASSIFIER_VERSION)
    match = _match("C1", [candidate], matched_alpha="A301")  # only A301 present
    call = _stance_call(
        [_request_item("C1", "A101")],  # requests A101, which does not exist on this claim
        [{"claim_id": "C1", "target_alpha_id": "A101", "stance": "supports_alpha"}],
    )
    audit = build_semantic_binding_audit(_bundle([match], [call]))
    assert audit["final_status"] == "FAIL"
    assert any("C1:A101" in item for item in audit["missing_bindings"])


# ---------------------------------------------------------------------------
# D. Counter Alpha binding
# ---------------------------------------------------------------------------


def test_d_counter_alpha_binds_when_stance_and_id_both_match():
    taxonomy = load_alpha_taxonomy()
    conflict_ids = {c.alpha_id for c in taxonomy["A101"].conflict_alphas}
    assert conflict_ids, "A101 must have a canonical conflict partner for this test to be meaningful"
    counter_id = sorted(conflict_ids)[0]

    candidate = _candidate(
        "A101",
        evidence_stance="supports_counter_alpha",
        counter_alpha_id=counter_id,
        stance_method="llm",
        evidence_stance_version=LLM_CLASSIFIER_VERSION,
    )
    match = _match("C1", [candidate], matched_alpha="A101")
    call = _stance_call(
        [_request_item("C1", "A101")],
        [{"claim_id": "C1", "target_alpha_id": "A101", "stance": "supports_counter_alpha", "counter_alpha_id": counter_id}],
    )
    audit = build_semantic_binding_audit(_bundle([match], [call]))
    assert audit["final_status"] == "PASS"


def test_d_counter_alpha_id_mismatch_fails_closed():
    taxonomy = load_alpha_taxonomy()
    conflict_ids = sorted(c.alpha_id for c in taxonomy["A101"].conflict_alphas)
    counter_id = conflict_ids[0]

    candidate = _candidate(
        "A101",
        evidence_stance="supports_counter_alpha",
        counter_alpha_id="A999_WRONG",  # persisted counter differs from the semantic call's own id
        stance_method="llm",
        evidence_stance_version=LLM_CLASSIFIER_VERSION,
    )
    match = _match("C1", [candidate], matched_alpha="A101")
    call = _stance_call(
        [_request_item("C1", "A101")],
        [{"claim_id": "C1", "target_alpha_id": "A101", "stance": "supports_counter_alpha", "counter_alpha_id": counter_id}],
    )
    audit = build_semantic_binding_audit(_bundle([match], [call]))
    assert audit["final_status"] == "FAIL"
    assert any("C1:A101" in item for item in audit["artifact_decision_mismatches"])


# ---------------------------------------------------------------------------
# E. Mention / neutral classes -- exact five-class semantics, not collapsed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stance", ["mentions_alpha", "neutral_background", "supports_alpha", "opposes_alpha"])
def test_e_each_of_the_five_classes_binds_distinctly(stance):
    candidate = _candidate(
        "A304",
        evidence_stance=stance,
        stance_method="llm",
        evidence_stance_version=LLM_CLASSIFIER_VERSION,
    )
    match = _match("C1", [candidate], matched_alpha="A304" if stance in {"supports_alpha", "opposes_alpha"} else None)
    call = _stance_call(
        [_request_item("C1", "A304")],
        [{"claim_id": "C1", "target_alpha_id": "A304", "stance": stance}],
    )
    audit = build_semantic_binding_audit(_bundle([match], [call]))
    assert audit["final_status"] == "PASS"


def test_e_mentions_and_neutral_are_not_interchangeable():
    """A persisted mentions_alpha must not satisfy an expected neutral_background, and vice versa."""
    candidate = _candidate("A304", evidence_stance="mentions_alpha", stance_method="llm", evidence_stance_version=LLM_CLASSIFIER_VERSION)
    match = _match("C1", [candidate])
    call = _stance_call(
        [_request_item("C1", "A304")],
        [{"claim_id": "C1", "target_alpha_id": "A304", "stance": "neutral_background"}],
    )
    audit = build_semantic_binding_audit(_bundle([match], [call]))
    assert audit["final_status"] == "FAIL"
    assert any("C1:A304" in item for item in audit["artifact_decision_mismatches"])


# ---------------------------------------------------------------------------
# F. Batch call -- one call binds multiple artifact locations
# ---------------------------------------------------------------------------


def test_f_batch_call_binds_all_items_across_different_claims():
    candidate_1 = _candidate("A304", evidence_stance="supports_alpha", stance_method="llm", evidence_stance_version=LLM_CLASSIFIER_VERSION)
    candidate_2 = _candidate("A101", evidence_stance="opposes_alpha", stance_method="llm", evidence_stance_version=LLM_CLASSIFIER_VERSION)
    candidate_3 = _candidate("A301", evidence_stance="mentions_alpha", stance_method="llm", evidence_stance_version=LLM_CLASSIFIER_VERSION)
    matches = [
        _match("C1", [candidate_1], matched_alpha="A304"),
        _match("C2", [candidate_2]),
        _match("C3", [candidate_3]),
    ]
    call = _stance_call(
        [_request_item("C1", "A304"), _request_item("C2", "A101"), _request_item("C3", "A301")],
        [
            {"claim_id": "C1", "target_alpha_id": "A304", "stance": "supports_alpha"},
            {"claim_id": "C2", "target_alpha_id": "A101", "stance": "opposes_alpha"},
            {"claim_id": "C3", "target_alpha_id": "A301", "stance": "mentions_alpha"},
        ],
    )
    audit = build_semantic_binding_audit(_bundle(matches, [call]))
    assert audit["final_status"] == "PASS"
    bound_keys = {key for binding in audit["bindings"] for key in binding["artifact_decision_keys"]}
    assert bound_keys == {"evidence_stance:C1:A304", "evidence_stance:C2:A101", "evidence_stance:C3:A301"}
    assert len(audit["bindings"]) == 1  # one call, three decision keys


# ---------------------------------------------------------------------------
# G. One item in batch missing / inconsistent -> whole batch fails closed
# ---------------------------------------------------------------------------


def test_g_one_missing_response_item_with_inconsistent_artifact_fails_the_whole_batch():
    good_candidate = _candidate("A304", evidence_stance="supports_alpha", stance_method="llm", evidence_stance_version=LLM_CLASSIFIER_VERSION)
    # C2/A101 was requested but never returned by the response; production
    # would stamp deterministic_fallback + missing_result -- here the
    # artifact is deliberately left inconsistent (stance_method="llm",
    # as if a result had been applied) to prove this is caught.
    inconsistent_candidate = _candidate("A101", evidence_stance="opposes_alpha", stance_method="llm", evidence_stance_version=LLM_CLASSIFIER_VERSION)
    matches = [
        _match("C1", [good_candidate], matched_alpha="A304"),
        _match("C2", [inconsistent_candidate]),
    ]
    call = _stance_call(
        [_request_item("C1", "A304"), _request_item("C2", "A101")],
        [{"claim_id": "C1", "target_alpha_id": "A304", "stance": "supports_alpha"}],  # C2/A101 missing
    )
    audit = build_semantic_binding_audit(_bundle(matches, [call]))
    assert audit["final_status"] == "FAIL"
    assert any("C2:A101" in item for item in audit["artifact_decision_mismatches"])
    # The call must not register as bound at all -- a partially-correct
    # batch is not a partial pass (task spec section 7).
    assert not any(call["call_id"] == binding["call_id"] for binding in audit["bindings"])


def test_g_one_missing_response_item_correctly_recorded_as_fallback_still_requires_full_batch():
    """Even when the missing item's provenance IS correctly stamped
    deterministic_fallback/missing_result, the call binds -- proving the
    prior test's failure is about inconsistency, not mere absence."""
    good_candidate = _candidate("A304", evidence_stance="supports_alpha", stance_method="llm", evidence_stance_version=LLM_CLASSIFIER_VERSION)
    fallback_candidate = _candidate(
        "A101",
        stance_method="deterministic_fallback",
        stance_fallback_reason="missing_result",
        evidence_stance_version="evidence_stance.deterministic.v1",
    )
    matches = [
        _match("C1", [good_candidate], matched_alpha="A304"),
        _match("C2", [fallback_candidate]),
    ]
    call = _stance_call(
        [_request_item("C1", "A304"), _request_item("C2", "A101")],
        [{"claim_id": "C1", "target_alpha_id": "A304", "stance": "supports_alpha"}],
    )
    audit = build_semantic_binding_audit(_bundle(matches, [call]))
    assert audit["final_status"] == "PASS"


# ---------------------------------------------------------------------------
# H. Matched Alpha mirror consistency (candidate-level is canonical)
# ---------------------------------------------------------------------------


def test_h_binding_uses_candidate_level_even_when_matched_level_mirror_is_stale():
    """A known, pre-existing artifact quirk: matched_evidence_stance is
    computed before B1's LLM upgrade runs and is not re-synced afterward,
    so it can legitimately diverge from the candidate-level canonical
    value once B1 changes the matched Alpha's stance. Binding must succeed
    based on candidate-level data regardless (task spec section 6)."""
    candidate = _candidate(
        "A304",
        evidence_stance="opposes_alpha",  # the real, current, LLM-upgraded value
        stance_method="llm",
        evidence_stance_version=LLM_CLASSIFIER_VERSION,
    )
    match = _match(
        "C1",
        [candidate],
        matched_alpha="A304",
        matched_evidence_stance="supports_alpha",  # deliberately stale mirror, frozen pre-upgrade
    )
    call = _stance_call(
        [_request_item("C1", "A304")],
        [{"claim_id": "C1", "target_alpha_id": "A304", "stance": "opposes_alpha"}],
    )
    audit = build_semantic_binding_audit(_bundle([match], [call]))
    assert audit["final_status"] == "PASS"


# ---------------------------------------------------------------------------
# I. Non-matched candidate still binds at candidate level
# ---------------------------------------------------------------------------


def test_i_stance_for_a_non_matched_candidate_binds_correctly():
    # matched_candidate deliberately has no B1 stance of its own (stance_
    # method stays None/deterministic default) -- this test is only about
    # A101 (a non-matched candidate) binding correctly on its own terms.
    matched_candidate = _candidate("A304", evidence_stance="mentions_alpha")
    secondary_candidate = _candidate("A101", evidence_stance="mentions_alpha", stance_method="llm", evidence_stance_version=LLM_CLASSIFIER_VERSION)
    match = _match("C1", [matched_candidate, secondary_candidate], matched_alpha="A304")
    call = _stance_call(
        [_request_item("C1", "A101")],  # A101 is not matched_alpha (A304 is)
        [{"claim_id": "C1", "target_alpha_id": "A101", "stance": "mentions_alpha"}],
    )
    audit = build_semantic_binding_audit(_bundle([match], [call]))
    assert audit["final_status"] == "PASS"


# ---------------------------------------------------------------------------
# J. Provenance -- stance_method="llm" requires the full provenance set
# ---------------------------------------------------------------------------


def test_j_llm_provenance_requires_correct_evidence_stance_version_too():
    """Correct stance and stance_method alone are not sufficient -- the
    provenance fields _apply_llm_result always stamps together must also
    be internally consistent."""
    candidate = _candidate(
        "A304",
        evidence_stance="supports_alpha",
        stance_method="llm",
        evidence_stance_version="evidence_stance.llm.v0_stale",  # wrong version, everything else correct
    )
    match = _match("C1", [candidate], matched_alpha="A304")
    call = _stance_call(
        [_request_item("C1", "A304")],
        [{"claim_id": "C1", "target_alpha_id": "A304", "stance": "supports_alpha"}],
    )
    audit = build_semantic_binding_audit(_bundle([match], [call]))
    assert audit["final_status"] == "FAIL"
    assert any("C1:A304" in item for item in audit["artifact_decision_mismatches"])


def test_j_llm_provenance_requires_manual_review_reset():
    candidate = _candidate(
        "A304",
        evidence_stance="supports_alpha",
        stance_method="llm",
        evidence_stance_version=LLM_CLASSIFIER_VERSION,
        requires_manual_review=True,  # _apply_llm_result always resets this to False
    )
    match = _match("C1", [candidate], matched_alpha="A304")
    call = _stance_call(
        [_request_item("C1", "A304")],
        [{"claim_id": "C1", "target_alpha_id": "A304", "stance": "supports_alpha"}],
    )
    audit = build_semantic_binding_audit(_bundle([match], [call]))
    assert audit["final_status"] == "FAIL"


# ---------------------------------------------------------------------------
# K. Version mismatch -- a real identity mismatch stays version_mismatches
# ---------------------------------------------------------------------------


def test_k_wrong_prompt_version_is_a_real_version_mismatch():
    candidate = _candidate("A304", evidence_stance="supports_alpha", stance_method="llm", evidence_stance_version=LLM_CLASSIFIER_VERSION)
    match = _match("C1", [candidate], matched_alpha="A304")
    call = _stance_call(
        [_request_item("C1", "A304")],
        [{"claim_id": "C1", "target_alpha_id": "A304", "stance": "supports_alpha"}],
        prompt_version="evidence_stance.llm_classifier.v2",  # stale/wrong on purpose
    )
    bundle = _bundle([match], [call])
    audit = build_semantic_binding_audit(bundle)
    assert audit["final_status"] == "FAIL"
    assert call["call_id"] in audit["version_mismatches"]
    with pytest.raises(ExactReplayError) as caught:
        verify_semantic_bindings(bundle)
    assert caught.value.reason_code == EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH


# ---------------------------------------------------------------------------
# L. Unknown semantic task -- unsupported, never falsely a version mismatch
# ---------------------------------------------------------------------------


def test_l_unknown_task_is_unsupported_not_a_version_mismatch():
    call = _stance_call(
        [_request_item("C1", "A304")],
        [{"claim_id": "C1", "target_alpha_id": "A304", "stance": "supports_alpha"}],
        task="some_future_semantic_task",
        # Deliberately valid-looking identity fields, to prove an
        # unsupported task is never misreported as a version mismatch
        # merely because it happens to carry plausible-looking identity.
        prompt_version="some_future_task.v1",
        prompt_sha256="0" * 64,
        input_schema_version="some_future_task.input.v1",
        output_schema_version="some_future_task.output.v1",
        taxonomy_version=None,
    )
    bundle = _bundle([], [call])
    audit = build_semantic_binding_audit(bundle)
    assert audit["final_status"] == "FAIL"
    assert call["call_id"] in audit["unsupported_tasks"]
    assert call["call_id"] not in audit["version_mismatches"]
    with pytest.raises(ExactReplayError) as caught:
        verify_semantic_bindings(bundle)
    assert caught.value.reason_code == EXACT_REPLAY_SEMANTIC_TASK_UNSUPPORTED


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
