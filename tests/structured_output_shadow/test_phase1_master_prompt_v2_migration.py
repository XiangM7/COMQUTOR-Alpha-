"""Phase 1 Master prompt-size fix: unit tests for the state-machine wiring
that switches structured_claim_shadow from the frozen v1 prompt to the
measured, tested v2 minimal-request prompt on BLOCKED_ANTHROPIC_PROVIDER_
RELIABILITY, and reuses it for every subsequent report (Smoke/Pilot/Core).
No Provider calls, no real state file I/O (all in-memory dicts).
"""

from __future__ import annotations

import importlib

master = importlib.import_module("scripts.run_phase1_master")


def _blocked_state(**overrides):
    state = {
        "current_state": "BLOCKED",
        "blocked_reason_code": "BLOCKED_ANTHROPIC_PROVIDER_RELIABILITY",
        "prompt_version_in_use": master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
        "prompt_sha256_in_use": master.STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
        "evaluation_dir": "outputs/evaluations/phase1-master-anthropic-old",
        "anthropic_called_report_ids": [
            "run-x:fundamental_agent:fundamentals_report",
            "run-x:news_agent:news_report",
            "run-x:sentiment_agent:sentiment_report",
            "run-x:market_agent:market_report",
        ],
        "already_called_report_ids": ["deepseek-era-report-id"],
        "cumulative_logical_calls": 15,
        "cumulative_provider_attempts": 22,
        "previous_provider_evaluations": [],
        "current_provider_evaluation": {
            "profile_id": "comqutor_anthropic_medium_sonnet46_v1",
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "evaluation_dir": "outputs/evaluations/phase1-master-anthropic-old",
            "qualification_completed": True,
        },
        "history": [],
    }
    state.update(overrides)
    return state


def test_switch_flips_prompt_identity_to_v2():
    state = _blocked_state()
    master._switch_structured_claim_shadow_to_prompt_v2(state)
    assert state["prompt_version_in_use"] == master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2
    assert state["prompt_sha256_in_use"] == master.STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256


def test_switch_voids_but_preserves_prior_anthropic_attempt():
    state = _blocked_state()
    prior_ids = list(state["anthropic_called_report_ids"])
    prior_dir = state["evaluation_dir"]
    master._switch_structured_claim_shadow_to_prompt_v2(state)
    assert state["anthropic_called_report_ids"] == []
    assert state["evaluation_dir"] is None
    assert state["current_provider_evaluation"]["evaluation_dir"] is None
    preserved = state["previous_provider_evaluations"][-1]
    assert preserved["evaluation_dir"] == prior_dir
    assert preserved["terminal_blocker"] == "BLOCKED_ANTHROPIC_PROVIDER_RELIABILITY"
    assert state["prompt_v2_migration"]["prior_anthropic_smoke_report_ids_voided"] == prior_ids


def test_switch_never_touches_deepseek_era_history_or_cumulative_ledger():
    state = _blocked_state()
    master._switch_structured_claim_shadow_to_prompt_v2(state)
    assert state["already_called_report_ids"] == ["deepseek-era-report-id"]
    assert state["cumulative_logical_calls"] == 15
    assert state["cumulative_provider_attempts"] == 22


def test_switch_clears_blocked_reason_code():
    state = _blocked_state()
    master._switch_structured_claim_shadow_to_prompt_v2(state)
    assert state["blocked_reason_code"] is None


def test_switch_is_the_only_place_that_sets_migration_record():
    state = _blocked_state()
    assert "prompt_v2_migration" not in state
    master._switch_structured_claim_shadow_to_prompt_v2(state)
    assert state["prompt_v2_migration"]["revision_count"] == 1
    assert state["prompt_v2_migration"]["to_prompt_version"] == master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2


def test_evaluation_dir_naming_reflects_v2_once_switched():
    state = _blocked_state()
    master._switch_structured_claim_shadow_to_prompt_v2(state)
    fresh_dir = master._evaluation_dir(state)
    assert "anthropic-v2" in fresh_dir.name
    assert state["evaluation_dir"] == f"outputs/evaluations/{fresh_dir.name}"


def test_evaluation_dir_naming_stays_v1_style_before_switch():
    state = _blocked_state(evaluation_dir=None)
    fresh_dir = master._evaluation_dir(state)
    assert "anthropic-v2" not in fresh_dir.name
    assert fresh_dir.name.startswith("phase1-master-anthropic-")


def test_main_loop_retry_condition_matches_only_the_reliability_blocker_once():
    """The exact predicate used in main()'s while loop: fires once (v1 in
    use), never again once state already reflects v2 (idempotent guard)."""

    state = _blocked_state()

    def should_retry(s):
        return (
            s["current_state"] == "BLOCKED"
            and s.get("blocked_reason_code") == "BLOCKED_ANTHROPIC_PROVIDER_RELIABILITY"
            and s.get("prompt_version_in_use") != master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2
        )

    assert should_retry(state) is True
    master._switch_structured_claim_shadow_to_prompt_v2(state)
    assert should_retry(state) is False


def test_unrelated_blocker_is_never_matched_by_the_v2_retry_condition():
    state = _blocked_state(blocked_reason_code="BLOCKED_RESEARCH_PROFILE_INVALID")
    assert state["blocked_reason_code"] != "BLOCKED_ANTHROPIC_PROVIDER_RELIABILITY"
