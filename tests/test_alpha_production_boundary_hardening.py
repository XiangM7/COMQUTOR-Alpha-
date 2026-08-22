"""Pure-LLM Alpha Production Boundary Hardening.

Alpha semantic result has exactly three conceptually distinct states:
MATCHED (LLM ran and selected one Alpha), NONE (LLM ran and explicitly
determined no canonical Alpha materially fits), and UNAVAILABLE (no valid
LLM semantic decision was obtained, for any configuration/operational
reason). Deterministic logic may never convert NONE or UNAVAILABLE into
matched_alpha.

This file covers the task spec's lettered tests A-N; several already had
direct coverage elsewhere and are not duplicated here:

- A (LLM select A101 -> matched A101): see
  tests/test_alpha_mapper_llm_authority.py::test_a_llm_selects_alpha_absent_from_deterministic_tier1_candidates
- B (LLM NONE + deterministic A304 -> semantic NONE, never A304): see
  tests/test_alpha_mapper_llm_authority.py::test_d_llm_none_with_deterministic_candidate_present_is_never_promoted
- C (LLM disabled + deterministic candidate present -> UNAVAILABLE, never
  the deterministic Alpha): see
  tests/test_alpha_mapper_llm_authority.py::test_l_b1_and_b2_existing_suites_are_unaffected_by_default
- E (Provider timeout -> UNAVAILABLE): see
  tests/test_alpha_mapper_llm_authority.py::test_f_timeout_reports_unavailable_without_leaking_details
- F (Malformed LLM output -> UNAVAILABLE): see
  tests/test_alpha_mapper_llm_authority.py::test_h_malformed_gateway_response_is_unavailable_not_deterministic
  and ::test_h_non_mapping_raw_classifier_response_is_unavailable_not_deterministic
- G (Invalid Alpha ID -> UNAVAILABLE): see
  tests/test_alpha_mapper_llm_authority.py::test_g_unknown_alpha_id_is_rejected_at_the_gateway_validator
  and ::test_g_unknown_alpha_id_from_a_raw_classifier_is_rejected
- L (Exact Semantic Replay with recorded select -> verifies matched Alpha):
  see tests/replay/test_exact_semantic_replay.py::test_eligible_exact_replay_is_atomic_byte_identical_and_source_read_only
- M (Exact Semantic Replay with recorded NONE -> verifies semantic NONE):
  see tests/replay/test_exact_semantic_replay.py::test_exact_replay_with_recorded_none_decision_preserves_semantic_none

D, H, I, J, K, N are new coverage added by this task, below.
"""

from __future__ import annotations

import json

import pytest

from comqutor_alpha.conflict_engine.conflict_admissibility import stance_for_alpha
from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts
from comqutor_alpha.graph_engine.activation_scorer_v2 import score_alpha_activations_v2
from comqutor_alpha.replay.pipeline import run_structure_replay
from comqutor_alpha.structure_engine.alpha_mapper import map_claim_to_alpha

_AI_DEMAND_RECORD_TEXT = "AI training demand is accelerating and GPU demand is rising for NVDA."
_AI_DEMAND_FACTORS = ["AI Demand", "GPU Demand"]


def _record(text, *, factors=None, direction="neutral", ticker="NVDA", run_id="run1"):
    return {
        "run_id": run_id,
        "ticker": ticker,
        "agent": "news_agent",
        "claim": text,
        "evidence": text,
        "factors": factors or [],
        "direction": direction,
        "confidence": 0.8,
        "source_agent_output_id": f"{run_id}:news_agent:news_report",
    }


def _ai_demand_record(**kwargs):
    return _record(_AI_DEMAND_RECORD_TEXT, factors=_AI_DEMAND_FACTORS, direction="positive", **kwargs)


# ---------------------------------------------------------------------------
# D. NO GATEWAY CONFIGURED -> UNAVAILABLE (distinct from "disabled": the
#    classifier IS enabled, but no classifier callable and no llm_gateway
#    object was actually supplied -- a wiring/configuration gap, not a
#    deliberate opt-out).
# ---------------------------------------------------------------------------


def test_d_classifier_enabled_but_no_gateway_or_classifier_configured_is_unavailable():
    record = _ai_demand_record()
    baseline = map_claim_to_alpha(record)  # classifier_enabled=False for comparison
    assert baseline["deterministic_top_alpha"] == "A101"

    result = map_claim_to_alpha(record, classifier_enabled=True)  # no classifier=, no llm_gateway=

    assert result["matched_alpha"] is None
    assert result["match_status"] == "unavailable"
    assert result["alpha_match_method"] == "llm_unavailable"
    assert result["alpha_match_fallback_reason"] == "unavailable"
    assert result["classifier"]["status"] == "unavailable"
    assert result["classifier"]["enabled"] is True
    # Distinct fallback_reason from the "disabled" (classifier_enabled=False)
    # case -- both are UNAVAILABLE, but for two different, distinguishable
    # configuration reasons.
    disabled_result = map_claim_to_alpha(record)
    assert disabled_result["alpha_match_fallback_reason"] == "disabled"
    assert disabled_result["alpha_match_fallback_reason"] != result["alpha_match_fallback_reason"]
    # Deterministic diagnostics remain fully preserved either way.
    assert result["deterministic_top_alpha"] == "A101"
    assert result["deterministic_match_status"] == "matched"


# ---------------------------------------------------------------------------
# H. NONE AND UNAVAILABLE SERIALIZE DIFFERENTLY IN ARTIFACTS/API.
# ---------------------------------------------------------------------------


def test_h_none_and_unavailable_serialize_differently():
    """A consumer reading only the persisted JSON (never Python identity)
    must be able to tell semantic NONE apart from operational UNAVAILABLE
    -- both have matched_alpha=None, but match_status/alpha_match_method/
    alpha_match_fallback_reason must differ, and that difference must
    survive a real json.dumps/json.loads round trip."""
    from tests.test_alpha_mapper_llm_authority import _FakeLLMGateway

    record = _ai_demand_record()

    none_result = map_claim_to_alpha(
        record, classifier_enabled=True,
        llm_gateway=_FakeLLMGateway(response={"decision": "none", "selected_alpha_id": None}),
    )
    unavailable_result = map_claim_to_alpha(
        record, classifier_enabled=True,
        llm_gateway=_FakeLLMGateway(raise_exc=RuntimeError("boom")),
    )

    # Both share the same "no Alpha" surface...
    assert none_result["matched_alpha"] is None
    assert unavailable_result["matched_alpha"] is None
    assert none_result["matched_alpha_name"] is None
    assert unavailable_result["matched_alpha_name"] is None

    # ...but are never the same serialized record.
    none_json = json.loads(json.dumps({k: v for k, v in none_result.items() if k not in ("candidate_scores", "top_candidates", "eligible_candidates")}))
    unavailable_json = json.loads(json.dumps({k: v for k, v in unavailable_result.items() if k not in ("candidate_scores", "top_candidates", "eligible_candidates")}))
    assert none_json["match_status"] != unavailable_json["match_status"]
    assert none_json["match_status"] == "no_match"
    assert unavailable_json["match_status"] == "unavailable"
    assert none_json["alpha_match_method"] == "llm"
    assert unavailable_json["alpha_match_method"] == "llm_unavailable"
    assert none_json["alpha_match_fallback_reason"] is None
    assert unavailable_json["alpha_match_fallback_reason"] is not None
    assert none_json["classifier"]["status"] != unavailable_json["classifier"]["status"]

    # The public evidence-stances API export (artifact_export.build_evidence_
    # stance_audit) passes match_status through verbatim -- confirm neither
    # state collapses there either.
    from comqutor_alpha.api.artifact_export import build_evidence_stance_audit
    from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy

    taxonomy = load_alpha_taxonomy()
    none_match = {**none_result, "claim_id": "c1", "candidate_scores": none_result["candidate_scores"]}
    unavailable_match = {**unavailable_result, "claim_id": "c2", "candidate_scores": unavailable_result["candidate_scores"]}
    audit = build_evidence_stance_audit(
        run_id="run1", ticker="NVDA",
        alpha_matches_payload={"matches": [none_match, unavailable_match]},
    )
    statuses_by_claim = {r["claim_id"]: r["match_status"] for r in audit["records"]}
    assert statuses_by_claim.get("c1") == "no_match"
    assert statuses_by_claim.get("c2") == "unavailable"
    assert statuses_by_claim["c1"] != statuses_by_claim["c2"]


# ---------------------------------------------------------------------------
# I / J. B2 / B4 RECEIVE NONE / UNAVAILABLE -> NO CRASH, NO INVENTED
#    CONFLICT OR ACTIVATION.
# ---------------------------------------------------------------------------


def test_i_b2_and_b4_receive_semantic_none_without_crash_or_invented_conflict():
    from tests.test_alpha_mapper_llm_authority import _FakeLLMGateway

    record = _ai_demand_record()
    none_result = map_claim_to_alpha(
        record, classifier_enabled=True,
        llm_gateway=_FakeLLMGateway(response={"decision": "none", "selected_alpha_id": None}),
    )
    assert none_result["match_status"] == "no_match"
    assert none_result["matched_alpha"] is None

    assert stance_for_alpha(none_result, "A101") is not None  # candidate-level B1 diagnostic still real
    assert stance_for_alpha(none_result, none_result["matched_alpha"]) is None  # never crashes on None

    payload = {"matches": [none_result]}
    activations = score_alpha_activations_v2(payload, ticker="NVDA")
    assert activations["dominant_alphas"] == []
    a101_activation = next(a for a in activations["alphas"] if a["alpha_id"] == "A101")
    assert a101_activation["evidence_count"] == 0

    conflict_result = detect_alpha_conflicts(
        run_id="run1", ticker="NVDA", activation_payload=activations, alpha_matches=[none_result],
    )
    assert conflict_result["conflicts"] == []
    assert conflict_result["main_conflict"] is None


def test_j_b2_and_b4_receive_unavailable_without_crash_or_invented_conflict():
    from tests.test_alpha_mapper_llm_authority import _FakeLLMGateway

    record = _ai_demand_record()
    unavailable_result = map_claim_to_alpha(
        record, classifier_enabled=True,
        llm_gateway=_FakeLLMGateway(raise_exc=RuntimeError("boom")),
    )
    assert unavailable_result["match_status"] == "unavailable"
    assert unavailable_result["matched_alpha"] is None

    assert stance_for_alpha(unavailable_result, "A101") is not None
    assert stance_for_alpha(unavailable_result, unavailable_result["matched_alpha"]) is None

    payload = {"matches": [unavailable_result]}
    activations = score_alpha_activations_v2(payload, ticker="NVDA")
    assert activations["dominant_alphas"] == []
    a101_activation = next(a for a in activations["alphas"] if a["alpha_id"] == "A101")
    assert a101_activation["evidence_count"] == 0

    conflict_result = detect_alpha_conflicts(
        run_id="run1", ticker="NVDA", activation_payload=activations, alpha_matches=[unavailable_result],
    )
    assert conflict_result["conflicts"] == []
    assert conflict_result["main_conflict"] is None


# ---------------------------------------------------------------------------
# K. ARCHITECTURE REPLAY WITHOUT LLM -> UNAVAILABLE + DETERMINISTIC
#    DIAGNOSTICS PRESERVED.
# ---------------------------------------------------------------------------


def test_k_architecture_replay_without_llm_gateway_is_unavailable_with_diagnostics(tmp_path):
    run_id = "arch-replay-boundary-0001"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    raw_payload = {
        "schema_version": "week1.raw_agent_outputs.v1",
        "run_id": run_id,
        "ticker": "NVDA",
        "agent_outputs": [
            {
                "agent_output_id": f"{run_id}:market_agent:market_report",
                "run_id": run_id,
                "ticker": "NVDA",
                "agent": "market_agent",
                "tradingagents_agent": "Market Analyst",
                "source_field": "market_report",
                "source_path": "market_report",
                "source_candidates": ["market_report"],
                "raw_output": (
                    "AI training demand is accelerating and GPU demand is rising for NVDA."
                ),
            }
        ],
    }
    (run_dir / "raw_agent_outputs.json").write_text(json.dumps(raw_payload), encoding="utf-8")
    metadata = {
        "run_id": run_id,
        "ticker": "NVDA",
        "trade_date": "2026-07-01",
        "profile_id": "comqutor_anthropic_medium_sonnet46_v1",
        "created_at": "2026-07-01T00:00:00Z",
        "config": {"llm_provider": "anthropic", "quick_think_llm": "claude-sonnet-4-6", "deep_think_llm": "claude-sonnet-4-6"},
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    result = run_structure_replay(
        run_id,
        source_output_root=str(tmp_path),
        replay_output_root=str(tmp_path / "replays"),
    )
    assert result.status == "completed"
    assert result.llm_provider_calls == 0

    matches = json.loads(
        (tmp_path / "replays" / result.replay_run_id / "alpha_matches.json").read_text()
    )["matches"]
    assert matches
    for match in matches:
        # Architecture Replay never wires an LLM gateway by design (see
        # replay/pipeline.py's module docstring) -- its Alpha semantic
        # state is always UNAVAILABLE, never a fabricated NONE and never
        # the deterministic scorer's own top candidate standing in as a
        # real semantic decision.
        assert match["matched_alpha"] is None
        assert match["match_status"] == "unavailable"
        assert match["alpha_match_method"] == "llm_unavailable"
        assert match["alpha_match_fallback_reason"] == "disabled"
    # Deterministic diagnostics remain fully computed and inspectable.
    ai_claim = next(m for m in matches if m["deterministic_top_alpha"] == "A101")
    assert ai_claim["deterministic_match_status"] == "matched"
    assert ai_claim["candidate_scores"]
    assert any(c["alpha_id"] == "A101" for c in ai_claim["eligible_candidates"])


# ---------------------------------------------------------------------------
# N. deterministic_top_alpha CAN NEVER POPULATE matched_alpha ON NONE OR
#    UNAVAILABLE PATHS -- exhaustive cross-check across every failure mode.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "make_llm_kwargs",
    [
        pytest.param(
            lambda gw: {"classifier_enabled": True, "llm_gateway": gw(response={"decision": "none", "selected_alpha_id": None})},
            id="semantic_none",
        ),
        pytest.param(
            lambda gw: {"classifier_enabled": True},  # no gateway/classifier at all
            id="no_gateway_configured",
        ),
        pytest.param(
            lambda gw: {},  # classifier_enabled defaults False
            id="disabled",
        ),
        pytest.param(
            lambda gw: {"classifier_enabled": True, "llm_gateway": gw(raise_exc=TimeoutError("t"))},
            id="provider_timeout",
        ),
        pytest.param(
            lambda gw: {"classifier_enabled": True, "llm_gateway": gw(raise_exc=RuntimeError("e"))},
            id="provider_error",
        ),
        pytest.param(
            lambda gw: {"classifier_enabled": True, "llm_gateway": gw(response={"decision": "select", "selected_alpha_id": "A999"})},
            id="invalid_alpha_id",
        ),
        pytest.param(
            lambda gw: {"classifier_enabled": True, "llm_gateway": gw(response={"decision": "bogus"})},
            id="malformed_output",
        ),
    ],
)
def test_n_deterministic_top_alpha_never_populates_matched_alpha(make_llm_kwargs):
    from tests.test_alpha_mapper_llm_authority import _FakeLLMGateway

    record = _ai_demand_record()  # deterministic_top_alpha will be A101
    kwargs = make_llm_kwargs(_FakeLLMGateway)
    result = map_claim_to_alpha(record, **kwargs)

    assert result["deterministic_top_alpha"] == "A101"
    assert result["match_status"] in {"no_match", "unavailable"}
    assert result["matched_alpha"] is None, (
        f"matched_alpha leaked the deterministic result on a "
        f"{result['match_status']} path: {result}"
    )
    assert result["matched_alpha"] != result["deterministic_top_alpha"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
