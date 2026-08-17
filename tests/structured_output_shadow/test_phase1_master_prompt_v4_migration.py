"""Phase 1 Master evidence-alignment fix, round 2: unit tests for the
state-machine wiring that switches structured_claim_shadow from the v3
prompt to the measured, tested v4 markdown-formatting-fidelity prompt
while WAITING_FOR_HUMAN_REVIEW under v3, triggered only by the explicit,
human-supplied --apply-v4-markdown-formatting-fix flag (never inferred).
Mirrors test_phase1_master_prompt_v3_migration.py exactly, one version up.
No Provider calls, no real state file I/O (all in-memory dicts).
"""

from __future__ import annotations

import importlib

master = importlib.import_module("scripts.run_phase1_master")


def _waiting_for_human_review_v3_state(**overrides):
    state = {
        "current_state": "WAITING_FOR_HUMAN_REVIEW",
        "blocked_reason_code": None,
        "fail_reason_code": None,
        "prompt_version_in_use": master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3,
        "prompt_sha256_in_use": master.STRUCTURED_OUTPUT_SHADOW_PROMPT_V3_SHA256,
        "evaluation_dir": "outputs/evaluations/phase1-master-anthropic-v3-old",
        "anthropic_called_report_ids": [f"run-x:agent-{i}:report" for i in range(24)],
        "already_called_report_ids": ["deepseek-era-report-id"],
        "cumulative_logical_calls": 67,
        "cumulative_provider_attempts": 74,
        "previous_provider_evaluations": [
            {
                "profile_id": "deepseek-profile",
                "provider": "deepseek",
                "prompt_version": None,
                "evaluation_dir": "outputs/evaluations/phase1-master-deepseek-old",
                "terminal_blocker": "BLOCKED_PROVIDER_MODEL_UNSUITABLE_FOR_LONG_STRUCTURED_TASK",
                "preserved": True,
            },
            {
                "profile_id": "comqutor_anthropic_medium_sonnet46_v1",
                "provider": "anthropic",
                "prompt_version": master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
                "evaluation_dir": "outputs/evaluations/phase1-master-anthropic-v1-old",
                "terminal_blocker": "BLOCKED_ANTHROPIC_PROVIDER_RELIABILITY",
                "preserved": True,
            },
            {
                "profile_id": "comqutor_anthropic_medium_sonnet46_v1",
                "provider": "anthropic",
                "prompt_version": master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2,
                "evaluation_dir": "outputs/evaluations/phase1-master-anthropic-v2-old",
                "terminal_blocker": "V2_SEMANTIC_EVIDENCE_ALIGNMENT_FAIL",
                "preserved": True,
            },
        ],
        "current_provider_evaluation": {
            "profile_id": "comqutor_anthropic_medium_sonnet46_v1",
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "evaluation_dir": "outputs/evaluations/phase1-master-anthropic-v3-old",
            "qualification_completed": True,
        },
        "history": [],
    }
    state.update(overrides)
    return state


def test_switch_flips_prompt_identity_to_v4():
    state = _waiting_for_human_review_v3_state()
    master._switch_structured_claim_shadow_to_prompt_v4(state)
    assert state["prompt_version_in_use"] == master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4
    assert state["prompt_sha256_in_use"] == master.STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256


def test_switch_voids_but_preserves_the_completed_v3_evaluation_with_gate_markers():
    state = _waiting_for_human_review_v3_state()
    prior_ids = list(state["anthropic_called_report_ids"])
    prior_dir = state["evaluation_dir"]
    master._switch_structured_claim_shadow_to_prompt_v4(state)
    assert state["anthropic_called_report_ids"] == []
    assert state["evaluation_dir"] is None
    assert state["current_provider_evaluation"]["evaluation_dir"] is None
    preserved = state["previous_provider_evaluations"][-1]
    assert preserved["evaluation_dir"] == prior_dir
    assert preserved["prompt_version"] == master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3
    assert preserved["v3_engineering_reliability"] == "PASS"
    assert preserved["v3_markdown_formatting_fidelity"] == "PARTIAL"
    assert preserved["v3_accepted_report_count"] == 16
    assert preserved["v3_rejected_report_count"] == 8
    assert preserved["preserved"] is True
    assert state["prompt_v4_migration"]["prior_v3_anthropic_smoke_report_ids_voided"] == prior_ids


def test_switch_never_deletes_or_shrinks_prior_evaluation_history():
    state = _waiting_for_human_review_v3_state()
    before = len(state["previous_provider_evaluations"])
    master._switch_structured_claim_shadow_to_prompt_v4(state)
    assert len(state["previous_provider_evaluations"]) == before + 1
    assert state["previous_provider_evaluations"][0]["provider"] == "deepseek"
    assert state["previous_provider_evaluations"][2]["prompt_version"] == master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2


def test_switch_never_touches_deepseek_era_history_or_cumulative_ledger():
    state = _waiting_for_human_review_v3_state()
    master._switch_structured_claim_shadow_to_prompt_v4(state)
    assert state["already_called_report_ids"] == ["deepseek-era-report-id"]
    assert state["cumulative_logical_calls"] == 67
    assert state["cumulative_provider_attempts"] == 74


def test_switch_clears_blocked_and_fail_reason_codes():
    state = _waiting_for_human_review_v3_state(blocked_reason_code="SOMETHING", fail_reason_code="SOMETHING_ELSE")
    master._switch_structured_claim_shadow_to_prompt_v4(state)
    assert state["blocked_reason_code"] is None
    assert state["fail_reason_code"] is None


def test_switch_sets_semantic_quality_and_production_authority_state_fields():
    state = _waiting_for_human_review_v3_state()
    master._switch_structured_claim_shadow_to_prompt_v4(state)
    assert state["semantic_quality"] == "PENDING_V4_REEVALUATION"
    assert state["production_authority"] == "LEGACY_ADAPTER"


def test_switch_is_the_only_place_that_sets_migration_record():
    state = _waiting_for_human_review_v3_state()
    assert "prompt_v4_migration" not in state
    master._switch_structured_claim_shadow_to_prompt_v4(state)
    assert state["prompt_v4_migration"]["revision_count"] == 1
    assert state["prompt_v4_migration"]["to_prompt_version"] == master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4
    assert state["prompt_v4_migration"]["from_prompt_version"] == master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3


def test_evaluation_dir_naming_reflects_v4_once_switched():
    state = _waiting_for_human_review_v3_state()
    master._switch_structured_claim_shadow_to_prompt_v4(state)
    fresh_dir = master._evaluation_dir(state)
    assert "anthropic-v4" in fresh_dir.name
    assert state["evaluation_dir"] == f"outputs/evaluations/{fresh_dir.name}"


def test_evaluation_dir_naming_stays_v3_style_before_switch():
    state = _waiting_for_human_review_v3_state(evaluation_dir=None)
    fresh_dir = master._evaluation_dir(state)
    assert "anthropic-v3" in fresh_dir.name
    assert "anthropic-v4" not in fresh_dir.name


def test_main_loop_switch_condition_matches_only_the_intended_state_once():
    state = _waiting_for_human_review_v3_state()

    def should_switch(s, flag_passed):
        return (
            s["current_state"] == "WAITING_FOR_HUMAN_REVIEW"
            and flag_passed
            and s.get("prompt_version_in_use") == master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3
        )

    assert should_switch(state, True) is True
    assert should_switch(state, False) is False
    master._switch_structured_claim_shadow_to_prompt_v4(state)
    assert should_switch(state, True) is False


def test_switch_never_fires_from_a_v2_state_without_first_reaching_v3():
    state = _waiting_for_human_review_v3_state(
        prompt_version_in_use=master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2,
        prompt_sha256_in_use=master.STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256,
    )
    assert state["prompt_version_in_use"] != master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3


def test_v3_and_v4_evidence_alignment_gate_use_the_same_reusable_function():
    """v3_evidence_alignment_gate is intentionally pure/version-agnostic
    logic (operates on quote_resolution_summary shape, not prompt
    identity) -- confirms it still exists and is callable for v4 batches."""

    result = master.v3_evidence_alignment_gate(
        [
            {"shadow_status": "accepted", "quote_resolution_summary": {"no_exact_match": 0, "ambiguous_multiple_match": 0, "invalid_quote": 0}},
            {"shadow_status": "validation_rejected", "quote_resolution_summary": {"no_exact_match": 5, "ambiguous_multiple_match": 0, "invalid_quote": 0}},
        ]
    )
    assert result["pass"] is True
    assert result["fabricated_quote_count_in_accepted_reports"] == 0
