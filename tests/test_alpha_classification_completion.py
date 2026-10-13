"""2026-10-06 (round 14, section 6): classification-completion disclosure.

compute_alpha_classification_completion reads ONLY alpha_matches.json's own
persisted fields. build_research_response combines it with dominant_alphas
into one shared 4-state status. Neither re-runs classification nor mutates
any artifact.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from comqutor_alpha.structure_engine.alpha_mapper import compute_alpha_classification_completion

REPO_ROOT = Path(__file__).resolve().parents[1]
C904_DIR = REPO_ROOT / "outputs" / "runs" / "c904d4cc-dc09-495c-aec5-b056979948e1"


def _match(method, fallback, matched_alpha=None):
    return {
        "claim_id": f"c:{method}:{fallback}:{matched_alpha}",
        "alpha_match_method": method,
        "alpha_match_fallback_reason": fallback,
        "matched_alpha": matched_alpha,
    }


def test_valid_select_valid_none_failure_and_not_executed_are_four_distinct_buckets():
    payload = {"matches": [
        _match("llm", None, "A304"),
        _match("llm", None, None),
        _match("llm_unavailable", "provider_error"),
        _match("llm_unavailable", "provider_timeout"),
        _match("llm_unavailable", "disabled"),
        _match("llm_unavailable", "unavailable"),
        _match("llm_unavailable", "audit_unavailable"),
        _match("llm_unavailable", "call_budget_exhausted"),
        _match("llm_unavailable", "provider_rate_limited"),
        _match("llm_unavailable", "invalid_output"),
        _match("llm_unavailable", "output_truncated"),
    ]}
    result = compute_alpha_classification_completion(payload)
    # Real attempts that produced no usable result -> call failures;
    # claims no request was ever sent for -> not executed. Never merged,
    # never counted as a valid NONE.
    assert result == {
        "total_claims": 11,
        "valid_select_count": 1,
        "valid_none_count": 1,
        "call_failure_count": 5,   # provider_error, provider_timeout, rate_limited, invalid_output, output_truncated
        "not_executed_count": 4,   # disabled, unavailable, audit_unavailable, call_budget_exhausted
        "not_executed_configuration_count": 2,  # disabled, unavailable -- configuration, not faults
        "not_executed_fault_count": 2,          # audit_unavailable, call_budget_exhausted
        "complete": False,
        # 2026-10-13 (T3 019 / 027R / 028): a model selection a mapper gate vetoed is counted here, never as a valid NONE;
        # none of these records carries a vetoed selection
        "gate_overridden_selection_count": 0,
        "gate_overridden_by_gate": {"alpha_specific_invalidation": 0, "alpha_positive_requirement": 0, "other_gate": 0},
    }


def test_gateway_audit_failure_maps_to_its_own_reason_not_invalid_output():
    from comqutor_alpha.structure_engine.alpha_mapper import _gateway_error_to_fallback_reason

    assert _gateway_error_to_fallback_reason("WEEK2_LLM_AUDIT_WRITE_FAILED") == "audit_unavailable"
    # unchanged neighbours
    assert _gateway_error_to_fallback_reason("WEEK2_LLM_PROVIDER_ERROR") == "provider_error"
    assert _gateway_error_to_fallback_reason("WEEK2_LLM_INVALID_JSON") == "invalid_output"
    assert _gateway_error_to_fallback_reason(None) == "invalid_output"


def test_valid_none_alone_is_complete_not_a_failure():
    payload = {"matches": [_match("llm", None, None), _match("llm", None, None)]}
    result = compute_alpha_classification_completion(payload)
    assert result["complete"] is True
    assert result["valid_none_count"] == 2
    assert result["call_failure_count"] == 0


def test_any_call_failure_makes_it_incomplete():
    payload = {"matches": [_match("llm", None, None), _match("llm_unavailable", "provider_error")]}
    assert compute_alpha_classification_completion(payload)["complete"] is False


def test_empty_or_missing_payload_is_incomplete_never_complete():
    assert compute_alpha_classification_completion(None)["complete"] is False
    assert compute_alpha_classification_completion({})["complete"] is False
    assert compute_alpha_classification_completion({"matches": []})["complete"] is False


def test_does_not_mutate_input():
    payload = {"matches": [_match("llm", None, "A101")]}
    before = json.dumps(payload, sort_keys=True)
    compute_alpha_classification_completion(payload)
    assert json.dumps(payload, sort_keys=True) == before


@pytest.mark.skipif(not C904_DIR.exists(), reason="frozen c904d4cc run not present")
def test_real_c904d4cc_is_reported_incomplete_not_no_active():
    """The real frozen AMD run: 973 real call failures + 2 valid NONE. It
    must read as classification INCOMPLETE -- never as 'complete, no
    active Alpha', which is the misreading this disclosure exists to
    prevent."""
    payload = json.loads((C904_DIR / "alpha_matches.json").read_text())
    result = compute_alpha_classification_completion(payload)
    assert result["total_claims"] == 975
    assert result["call_failure_count"] == 973
    assert result["valid_none_count"] == 2
    assert result["valid_select_count"] == 0
    assert result["not_executed_count"] == 0
    assert result["complete"] is False


def _build_status(tmp_path, alpha_matches, dominant_alphas):
    """Drives the REAL build_research_response against a minimal on-disk
    run, with the Week4 DB-backed fields stubbed at their one seam so the
    test isolates the 4-state combination logic itself."""
    from comqutor_alpha.api import routes_research as rr

    run_id = "completion-test-run"
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(json.dumps({"run_id": run_id, "ticker": "AMD"}))
    (run_dir / "alpha_matches.json").write_text(json.dumps({"matches": alpha_matches}))
    (run_dir / "structure_graph.json").write_text("{}")
    return rr, run_id


@pytest.mark.parametrize(
    "matches,dominant,expected",
    [
        ([_match("llm_unavailable", "provider_error")], [], "incomplete"),
        ([_match("llm", None, None)], [], "complete_no_active"),
        ([_match("llm", None, "A304")], [], "complete_active_no_dominant"),
        ([_match("llm", None, "A304")], [{"alpha_id": "A304"}], "complete_has_dominant"),
        # dominant present but classification has gaps: gaps win -- never
        # report a clean 'complete' state over real call failures.
        ([_match("llm", None, "A304"), _match("llm_unavailable", "provider_error")],
         [{"alpha_id": "A304"}], "incomplete"),
    ],
)
def test_four_state_status_in_real_api_response(tmp_path, monkeypatch, matches, dominant, expected):
    rr, run_id = _build_status(tmp_path, matches, dominant)
    monkeypatch.setattr(
        rr, "_load_week4_response_fields",
        lambda *a, **k: (dominant, None, "ready", False, True),
    )
    # Week 3 'ready' marker so the Week 4 seam above is consulted.
    (tmp_path / run_id / "week3_pipeline_status.json").write_text(json.dumps({"outcome": "success"}))
    response = rr.build_research_response(run_id, output_root=str(tmp_path))
    assert response["alpha_classification_status"] == expected
    completion = response["alpha_classification_completion"]
    assert completion["total_claims"] == len(matches)


# ---------------------------------------------------------------------------
# Run-summary sentence (round 14, section 6)
# ---------------------------------------------------------------------------

from comqutor_alpha.api.routes_research import _build_research_summary  # noqa: E402

_DEFAULT_NOTHING_FOUND = (
    "No dominant Alpha structure or admitted conflict was identified for this research run."
)


def _completion(**overrides):
    base = {"total_claims": 975, "valid_select_count": 0, "valid_none_count": 2,
            "call_failure_count": 973, "not_executed_count": 0,
            "not_executed_configuration_count": 0, "not_executed_fault_count": 0, "complete": False}
    base.update(overrides)
    return base


def test_summary_never_says_nothing_exists_while_classification_is_incomplete():
    text = _build_research_summary("ready", None, [], alpha_classification_completion=_completion())
    assert "Alpha classification is incomplete" in text
    assert "973 of 975 claims have no usable classification result" in text
    assert "973 call failure(s), 0 not executed" in text
    assert "cannot yet be read as 'none exists'" in text
    assert text != _DEFAULT_NOTHING_FOUND


def test_summary_counts_fault_refused_sends_as_unresolved_but_not_a_deliberately_disabled_classifier():
    fault = _completion(total_claims=10, valid_none_count=0, call_failure_count=0,
                        not_executed_count=10, not_executed_fault_count=10)
    text = _build_summary_for(fault)
    assert "Alpha classification is incomplete" in text and "10 of 10 claims" in text and "0 call failure(s), 10 not executed" in text

    disabled = _completion(total_claims=10, valid_none_count=0, call_failure_count=0,
                           not_executed_count=10, not_executed_configuration_count=10)
    # A deliberately disabled/unconfigured classifier (offline/test runs) keeps the
    # established messages other behavior depends on; the structured status still
    # reports it as not complete.
    assert _build_summary_for(disabled) == _DEFAULT_NOTHING_FOUND


def _build_summary_for(completion, **kwargs):
    return _build_research_summary("ready", None, [], alpha_classification_completion=completion, **kwargs)


def test_established_evidence_gate_message_is_kept_for_a_disabled_classifier_and_yields_to_a_real_fault():
    gate = dict(evidence_gate_applied=True, has_verified_evidence=False)
    disabled = _completion(total_claims=10, valid_none_count=0, call_failure_count=0,
                           not_executed_count=10, not_executed_configuration_count=10)
    assert _build_summary_for(disabled, **gate).startswith("Verified evidence is currently insufficient")
    assert _build_summary_for(_completion(), **gate).startswith("Alpha classification is incomplete")


def test_summary_unchanged_when_classification_complete_or_param_omitted():
    complete = _completion(call_failure_count=0, valid_none_count=975, complete=True)
    assert _build_research_summary("ready", None, [], alpha_classification_completion=complete) == _DEFAULT_NOTHING_FOUND
    assert _build_research_summary("ready", None, []) == _DEFAULT_NOTHING_FOUND


def test_positive_findings_are_never_overridden_by_incompleteness():
    incomplete = _completion()
    assert _build_research_summary("ready", {"explanation": "A vs B"}, [{"alpha_id": "A1"}],
                                   alpha_classification_completion=incomplete) == "A vs B"
    assert "Dominant Alpha structures were identified" in _build_research_summary(
        "ready", None, [{"alpha_id": "A1"}], alpha_classification_completion=incomplete)
    assert _build_research_summary("not_ready", None, [], alpha_classification_completion=incomplete) == (
        "Conflict analysis is not ready for this research run.")


def test_zero_claims_is_not_reported_as_incomplete_in_the_summary():
    empty = _completion(total_claims=0, valid_none_count=0, call_failure_count=0, complete=False)
    assert _build_research_summary("ready", None, [], alpha_classification_completion=empty) == _DEFAULT_NOTHING_FOUND
