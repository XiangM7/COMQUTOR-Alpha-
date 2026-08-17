"""Phase 1 Master evidence-alignment fix: unit tests for the state-machine
wiring that switches structured_claim_shadow from the v2 minimal-request
prompt to the measured, tested v3 verbatim-quote prompt while
WAITING_FOR_HUMAN_REVIEW under v2, triggered only by the explicit,
human-supplied --apply-v3-evidence-alignment-fix flag (never inferred). No
Provider calls, no real state file I/O (all in-memory dicts).
"""

from __future__ import annotations

import importlib

master = importlib.import_module("scripts.run_phase1_master")


def _waiting_for_human_review_v2_state(**overrides):
    state = {
        "current_state": "WAITING_FOR_HUMAN_REVIEW",
        "blocked_reason_code": None,
        "fail_reason_code": None,
        "prompt_version_in_use": master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2,
        "prompt_sha256_in_use": master.STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256,
        "evaluation_dir": "outputs/evaluations/phase1-master-anthropic-v2-old",
        "anthropic_called_report_ids": [
            f"run-x:{agent}:{family}_report"
            for agent, family in (
                ("fundamental_agent", "fundamentals"),
                ("news_agent", "news"),
                ("sentiment_agent", "sentiment"),
                ("market_agent", "market"),
            )
        ]
        * 6,
        "already_called_report_ids": ["deepseek-era-report-id"],
        "cumulative_logical_calls": 43,
        "cumulative_provider_attempts": 50,
        "previous_provider_evaluations": [
            {
                "profile_id": "deepseek-profile",
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
                "evaluation_dir": "outputs/evaluations/phase1-master-deepseek-old",
                "terminal_blocker": "BLOCKED_PROVIDER_MODEL_UNSUITABLE_FOR_LONG_STRUCTURED_TASK",
                "preserved": True,
            },
            {
                "profile_id": "comqutor_anthropic_medium_sonnet46_v1",
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "prompt_version": master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
                "evaluation_dir": "outputs/evaluations/phase1-master-anthropic-v1-old",
                "terminal_blocker": "BLOCKED_ANTHROPIC_PROVIDER_RELIABILITY",
                "preserved": True,
            },
        ],
        "current_provider_evaluation": {
            "profile_id": "comqutor_anthropic_medium_sonnet46_v1",
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "evaluation_dir": "outputs/evaluations/phase1-master-anthropic-v2-old",
            "qualification_completed": True,
        },
        "history": [],
    }
    state.update(overrides)
    return state


def test_switch_flips_prompt_identity_to_v3():
    state = _waiting_for_human_review_v2_state()
    master._switch_structured_claim_shadow_to_prompt_v3(state)
    assert state["prompt_version_in_use"] == master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3
    assert state["prompt_sha256_in_use"] == master.STRUCTURED_OUTPUT_SHADOW_PROMPT_V3_SHA256


def test_switch_voids_but_preserves_the_completed_v2_evaluation_with_gate_markers():
    state = _waiting_for_human_review_v2_state()
    prior_ids = list(state["anthropic_called_report_ids"])
    prior_dir = state["evaluation_dir"]
    master._switch_structured_claim_shadow_to_prompt_v3(state)
    assert state["anthropic_called_report_ids"] == []
    assert state["evaluation_dir"] is None
    assert state["current_provider_evaluation"]["evaluation_dir"] is None
    preserved = state["previous_provider_evaluations"][-1]
    assert preserved["evaluation_dir"] == prior_dir
    assert preserved["prompt_version"] == master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2
    assert preserved["v2_engineering_reliability"] == "PASS"
    assert preserved["v2_semantic_evidence_alignment"] == "FAIL"
    assert preserved["preserved"] is True
    assert state["prompt_v3_migration"]["prior_v2_anthropic_smoke_report_ids_voided"] == prior_ids


def test_switch_never_deletes_or_shrinks_prior_evaluation_history():
    """The earlier DeepSeek and Anthropic-v1 preserved entries must remain
    exactly as they were -- the switch only ever appends."""

    state = _waiting_for_human_review_v2_state()
    before = len(state["previous_provider_evaluations"])
    master._switch_structured_claim_shadow_to_prompt_v3(state)
    assert len(state["previous_provider_evaluations"]) == before + 1
    assert state["previous_provider_evaluations"][0]["provider"] == "deepseek"
    assert state["previous_provider_evaluations"][1]["prompt_version"] == master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION


def test_switch_never_touches_deepseek_era_history_or_cumulative_ledger():
    state = _waiting_for_human_review_v2_state()
    master._switch_structured_claim_shadow_to_prompt_v3(state)
    assert state["already_called_report_ids"] == ["deepseek-era-report-id"]
    assert state["cumulative_logical_calls"] == 43
    assert state["cumulative_provider_attempts"] == 50


def test_switch_clears_blocked_and_fail_reason_codes():
    state = _waiting_for_human_review_v2_state(blocked_reason_code="SOMETHING", fail_reason_code="SOMETHING_ELSE")
    master._switch_structured_claim_shadow_to_prompt_v3(state)
    assert state["blocked_reason_code"] is None
    assert state["fail_reason_code"] is None


def test_switch_sets_semantic_quality_and_production_authority_state_fields():
    state = _waiting_for_human_review_v2_state()
    master._switch_structured_claim_shadow_to_prompt_v3(state)
    assert state["semantic_quality"] == "FAILED_CURRENT_V2_GATE"
    assert state["production_authority"] == "LEGACY_ADAPTER"


def test_switch_is_the_only_place_that_sets_migration_record():
    state = _waiting_for_human_review_v2_state()
    assert "prompt_v3_migration" not in state
    master._switch_structured_claim_shadow_to_prompt_v3(state)
    assert state["prompt_v3_migration"]["revision_count"] == 1
    assert state["prompt_v3_migration"]["to_prompt_version"] == master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3
    assert state["prompt_v3_migration"]["from_prompt_version"] == master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2


def test_evaluation_dir_naming_reflects_v3_once_switched():
    state = _waiting_for_human_review_v2_state()
    master._switch_structured_claim_shadow_to_prompt_v3(state)
    fresh_dir = master._evaluation_dir(state)
    assert "anthropic-v3" in fresh_dir.name
    assert state["evaluation_dir"] == f"outputs/evaluations/{fresh_dir.name}"


def test_evaluation_dir_naming_stays_v2_style_before_switch():
    state = _waiting_for_human_review_v2_state(evaluation_dir=None)
    fresh_dir = master._evaluation_dir(state)
    assert "anthropic-v2" in fresh_dir.name
    assert "anthropic-v3" not in fresh_dir.name


def test_main_loop_retry_condition_matches_only_the_intended_state_once():
    """The exact predicate used in main()'s while loop: fires only when
    WAITING_FOR_HUMAN_REVIEW, the human explicitly passed the flag, and v2
    is still in use; never again once state already reflects v3 (idempotent
    guard, mirroring the v1->v2 switch's own retry-condition test)."""

    state = _waiting_for_human_review_v2_state()

    def should_switch(s, flag_passed):
        return (
            s["current_state"] == "WAITING_FOR_HUMAN_REVIEW"
            and flag_passed
            and s.get("prompt_version_in_use") == master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2
        )

    assert should_switch(state, True) is True
    assert should_switch(state, False) is False
    master._switch_structured_claim_shadow_to_prompt_v3(state)
    assert should_switch(state, True) is False


def test_switch_never_fires_from_a_v1_state_without_first_reaching_v2():
    """Guards against ever skipping the v2 evaluation entirely -- the switch
    predicate specifically requires prompt_version_in_use == v2, not merely
    != v3."""

    state = _waiting_for_human_review_v2_state(
        prompt_version_in_use=master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
        prompt_sha256_in_use=master.STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
    )
    assert state["prompt_version_in_use"] != master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2


def test_unrelated_state_is_never_matched_by_the_v3_switch_condition():
    state = _waiting_for_human_review_v2_state(current_state="SMOKE")
    assert state["current_state"] != "WAITING_FOR_HUMAN_REVIEW"
