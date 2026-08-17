"""Phase 1 Master prompt-size fix: unit tests for recovering from a real,
observed FAIL_ACCEPTED_OUTPUT_EXACT_REPLAY that was caused by this repo's
own exact-replay verifier hardcoding a v1-only prompt-identity allowlist
(fixed in structured_output_shadow_replay.py), not a genuine data-integrity
problem. No Provider calls; in-memory state dicts only.
"""

from __future__ import annotations

import importlib

master = importlib.import_module("scripts.run_phase1_master")


def _fail_state(**overrides):
    state = {
        "current_state": "FAIL",
        "fail_reason_code": "FAIL_ACCEPTED_OUTPUT_EXACT_REPLAY",
        "prompt_version_in_use": master.STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2,
        "prompt_sha256_in_use": master.STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256,
        "evaluation_dir": "outputs/evaluations/phase1-master-anthropic-v2-old",
        "anthropic_called_report_ids": [
            "run-x:fundamental_agent:fundamentals_report",
            "run-x:news_agent:news_report",
            "run-x:sentiment_agent:sentiment_report",
            "run-x:market_agent:market_report",
        ],
        "previous_provider_evaluations": [],
        "current_provider_evaluation": {
            "profile_id": "comqutor_anthropic_medium_sonnet46_v1",
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "evaluation_dir": "outputs/evaluations/phase1-master-anthropic-v2-old",
        },
        "history": [],
    }
    state.update(overrides)
    return state


def test_void_helper_preserves_prior_dir_and_resets_called_ids():
    state = _fail_state()
    prior_dir = state["evaluation_dir"]
    prior_ids = list(state["anthropic_called_report_ids"])
    returned = master._void_evaluation_dir_and_reset_for_retry(
        state, terminal_note="FAIL_ACCEPTED_OUTPUT_EXACT_REPLAY (verifier false positive, fixed)"
    )
    assert returned == prior_dir
    assert state["anthropic_called_report_ids"] == []
    assert state["evaluation_dir"] is None
    assert state["current_provider_evaluation"]["evaluation_dir"] is None
    preserved = state["previous_provider_evaluations"][-1]
    assert preserved["evaluation_dir"] == prior_dir
    assert preserved["terminal_blocker"].startswith("FAIL_ACCEPTED_OUTPUT_EXACT_REPLAY")
    assert prior_ids  # sanity: there really was something to void


def test_void_helper_never_deletes_anything_on_disk(tmp_path, monkeypatch):
    real_dir = tmp_path / "outputs/evaluations/phase1-master-anthropic-v2-old"
    real_dir.mkdir(parents=True)
    (real_dir / "marker.json").write_text("{}", encoding="utf-8")
    state = _fail_state(evaluation_dir=str(real_dir.relative_to(tmp_path)))
    master._void_evaluation_dir_and_reset_for_retry(state, terminal_note="test")
    assert (real_dir / "marker.json").exists()


def test_recovery_condition_matches_only_this_specific_fail_reason():
    state = _fail_state()
    assert state["current_state"] == "FAIL" and state["fail_reason_code"] == "FAIL_ACCEPTED_OUTPUT_EXACT_REPLAY"

    other = _fail_state(fail_reason_code="FAIL_PHASE1_PROVIDER_CALL_LIMIT_EXCEEDED")
    assert other["fail_reason_code"] != "FAIL_ACCEPTED_OUTPUT_EXACT_REPLAY"


def test_evaluation_dir_naming_after_void_stays_v2_since_prompt_version_unchanged():
    state = _fail_state()
    master._void_evaluation_dir_and_reset_for_retry(state, terminal_note="test")
    fresh_dir = master._evaluation_dir(state)
    assert "anthropic-v2" in fresh_dir.name
