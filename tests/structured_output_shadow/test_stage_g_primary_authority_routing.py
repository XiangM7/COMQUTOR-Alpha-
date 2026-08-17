"""Phase 1 §5.1 Stage G: real primary-authority routing tests. Validates
the NEW routing functionality only (mode resolution -> authority selection
-> downstream dataflow) -- not another v4.2 semantic/provenance
qualification (that is already covered by test_shadow_v4_2_deterministic_
provenance.py and the real 99/99 offline replay). Provider/network calls:
zero throughout, including the "real stored v4.2 result" integration test,
which reuses an already-persisted result from the real, completed Final
Live Canary rather than calling a Provider again.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from comqutor_alpha.api.routes_research import run_research_request
from comqutor_alpha.structure_engine.structured_output_live_shadow import (
    AUTHORITY_LEGACY,
    FALLBACK_EMPTY_OR_NON_SUBSTANTIVE,
    FALLBACK_NO_REPORTS_ATTEMPTED,
    FALLBACK_REPORT_REJECTED,
    FALLBACK_SIDECAR_UNAVAILABLE,
    MODE_LEGACY,
    MODE_PRIMARY,
    MODE_SHADOW,
    SHADOW_OUTPUT_FILENAME,
    SHADOW_VALIDATION_FILENAME,
    ShadowAttemptResult,
    resolve_structured_adapter_mode,
    select_primary_authority,
)
from comqutor_alpha.structure_engine.structured_output_shadow_v4_2 import (
    StructuredOutputShadowParserV4_2,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FOUR_FAMILY_FIXTURE = REPO_ROOT / "outputs/runs/0e044e37-862c-43be-871c-31012cd660e7/raw_agent_outputs.json"
FOUR_FAMILY_AGENTS = {"fundamental_agent", "news_agent", "sentiment_agent", "market_agent"}
REAL_CANARY_SHADOW_DIR = (
    REPO_ROOT
    / "outputs/canaries/phase1-v4-2-final-live-canary-20260811T005455Z/shadow/"
    "phase1-v4-2-final-live-canary-nvda"
)


def _outputs() -> list[dict[str, str]]:
    payload = json.loads(FOUR_FAMILY_FIXTURE.read_text(encoding="utf-8"))
    return [
        {"agent": item["agent"], "raw_output": item["raw_output"]}
        for item in payload["agent_outputs"]
        if item.get("agent") in FOUR_FAMILY_AGENTS
    ]


def _payload(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "ticker": "NVDA",
        "analysis_date": "2026-08-11",
        "selected_analysts": ["fundamentals", "news", "sentiment", "market"],
        "offline_raw_agent_outputs": _outputs(),
    }


def _run(tmp_path: Path, name: str, *, mode: str, executor=None):
    response = run_research_request(
        _payload(name),
        output_root=tmp_path,
        structured_adapter_mode=mode,
        structured_adapter_shadow_executor=executor,
    )
    assert response["status"] == "completed"
    return response, tmp_path / name


class LocalV4_2Executor:
    """Real v4.2 parser/resolver, fake (offline) semantic_invoker only --
    mirrors test_live_shadow_integration.py's LocalV4Executor pattern one
    version up. Every accepted bundle is produced by the REAL
    StructuredOutputShadowParserV4_2, never hand-built JSON pretending to
    be a validated bundle."""

    provider = "fixture-provider"
    model = "recorded-v4.2-fixture"
    profile_id = "offline-fixture"

    def __init__(self, mode: str = "accepted") -> None:
        self.mode = mode
        self.calls = []

    def execute(self, context):
        self.calls.append(context)
        if self.mode == "timeout":
            raise TimeoutError("simulated timeout")

        class Invoker:
            def invoke(_self, *, prompt, request):
                if self.mode == "malformed":
                    return "not-json{{"
                if self.mode == "unresolved":
                    return {
                        "claims": [
                            {
                                "claim": "Unsupported claim.",
                                "supporting_quotes": ["text absent from source report"],
                                "entities": [],
                                "factors": [],
                                "direction": "unknown",
                                "confidence": 0.5,
                            }
                        ],
                        "abstentions": [],
                    }
                if self.mode == "empty":
                    return {"claims": [], "abstentions": []}
                # A real, unique sentence from the report -- exercises the
                # actual global-exact-search resolver, not a stub.
                first_line = next(
                    line.strip() for line in context.source_report.splitlines() if line.strip()
                )
                return {
                    "claims": [
                        {
                            "claim": first_line,
                            "supporting_quotes": [first_line],
                            "entities": [],
                            "factors": [],
                            "direction": "neutral",
                            "confidence": 0.8,
                        }
                    ],
                    "abstentions": [],
                }

        parser = StructuredOutputShadowParserV4_2(Invoker(), factor_vocabulary=context.factor_vocabulary)
        bundle = parser.parse_report_shadow_v4_2(
            source_report=context.source_report,
            run_id=context.run_id,
            ticker=context.ticker,
            agent=context.agent,
            agent_output_id=context.agent_output_id,
        )
        if self.mode == "identity_mismatch":
            bundle = deepcopy(bundle)
            bundle["ticker"] = "TSM"
        return ShadowAttemptResult(
            bundle=bundle,
            provider=self.provider,
            model=self.model,
            profile_id=self.profile_id,
            semantic_call_id=f"fixture-v4.2:{len(self.calls)}",
            provider_called=False,
            provider_status="fixture",
            retry_count=0,
            resolution_log=tuple(parser.last_resolution_log),
        )


# ---------------------------------------------------------------------------
# TEST 1 -- legacy mode
# ---------------------------------------------------------------------------


def test_1_legacy_mode_is_authoritative_unchanged(tmp_path):
    executor = LocalV4_2Executor()
    response, run_dir = _run(tmp_path, "legacy-run", mode="legacy", executor=executor)
    assert executor.calls == []
    assert not (run_dir / SHADOW_OUTPUT_FILENAME).exists()
    routing = json.loads((run_dir / "structured_adapter_authority_routing.json").read_text())
    assert routing["effective_mode"] == "legacy"
    assert routing["authoritative_adapter"] == AUTHORITY_LEGACY
    assert routing["primary_attempted"] is False


# ---------------------------------------------------------------------------
# TEST 2 -- shadow mode
# ---------------------------------------------------------------------------


def test_2_shadow_mode_stays_non_authoritative(tmp_path):
    executor = LocalV4_2Executor()
    response, run_dir = _run(tmp_path, "shadow-run", mode="shadow", executor=executor)
    assert len(executor.calls) == 4
    legacy_before = json.loads((run_dir / "structured_agent_outputs.json").read_text())
    shadow_output = json.loads((run_dir / SHADOW_OUTPUT_FILENAME).read_text())
    assert shadow_output["shadow_only"] is True
    assert shadow_output["production_authority"] is False
    # Legacy's own authoritative file was never overwritten by Shadow.
    assert legacy_before.get("adapter_version") != "structured_adapter.claim_extraction_shadow.v4.2"
    routing = json.loads((run_dir / "structured_adapter_authority_routing.json").read_text())
    assert routing["effective_mode"] == "shadow"
    assert routing["authoritative_adapter"] == AUTHORITY_LEGACY
    assert routing["primary_attempted"] is False


# ---------------------------------------------------------------------------
# TEST 3 -- primary + v4.2 success
# ---------------------------------------------------------------------------


def test_3_primary_success_authority_is_v4_2(tmp_path):
    executor = LocalV4_2Executor(mode="accepted")
    response, run_dir = _run(tmp_path, "primary-success", mode="primary", executor=executor)
    assert len(executor.calls) == 4
    routing = json.loads((run_dir / "structured_adapter_authority_routing.json").read_text())
    assert routing["effective_mode"] == "primary"
    assert routing["primary_attempted"] is True
    assert routing["primary_succeeded"] is True
    assert routing["fallback_used"] is False
    assert routing["authoritative_adapter"] == "structured_adapter.claim_extraction_shadow.v4.2"
    assert routing["active_protocol"] == "structured_adapter.claim_extraction_shadow.v4.2"


# ---------------------------------------------------------------------------
# TEST 4 -- primary + Provider transport failure
# ---------------------------------------------------------------------------


def test_4_primary_provider_failure_falls_back_to_legacy(tmp_path):
    executor = LocalV4_2Executor(mode="timeout")
    response, run_dir = _run(tmp_path, "primary-timeout", mode="primary", executor=executor)
    routing = json.loads((run_dir / "structured_adapter_authority_routing.json").read_text())
    assert routing["authoritative_adapter"] == AUTHORITY_LEGACY
    assert routing["fallback_used"] is True


# ---------------------------------------------------------------------------
# TEST 5 -- primary + parse failure
# ---------------------------------------------------------------------------


def test_5_primary_parse_failure_falls_back_to_legacy(tmp_path):
    executor = LocalV4_2Executor(mode="malformed")
    response, run_dir = _run(tmp_path, "primary-malformed", mode="primary", executor=executor)
    routing = json.loads((run_dir / "structured_adapter_authority_routing.json").read_text())
    assert routing["authoritative_adapter"] == AUTHORITY_LEGACY
    assert routing["fallback_used"] is True


# ---------------------------------------------------------------------------
# TEST 6 -- primary + empty/non-substantive
# ---------------------------------------------------------------------------


def test_6_primary_empty_output_falls_back_to_legacy(tmp_path):
    executor = LocalV4_2Executor(mode="empty")
    response, run_dir = _run(tmp_path, "primary-empty", mode="primary", executor=executor)
    routing = json.loads((run_dir / "structured_adapter_authority_routing.json").read_text())
    assert routing["authoritative_adapter"] == AUTHORITY_LEGACY
    assert routing["fallback_used"] is True


# ---------------------------------------------------------------------------
# TEST 7 -- primary + provenance rejection (NO_EXACT_MATCH Evidence)
# ---------------------------------------------------------------------------


def test_7_primary_provenance_rejection_falls_back_to_legacy(tmp_path):
    executor = LocalV4_2Executor(mode="unresolved")
    response, run_dir = _run(tmp_path, "primary-unresolved", mode="primary", executor=executor)
    routing = json.loads((run_dir / "structured_adapter_authority_routing.json").read_text())
    assert routing["authoritative_adapter"] == AUTHORITY_LEGACY
    assert routing["fallback_used"] is True
    # Provenance logic itself was not touched: still zero-match -> reject.
    validation = json.loads((run_dir / SHADOW_VALIDATION_FILENAME).read_text())
    assert validation["accepted_report_count"] == 0


# ---------------------------------------------------------------------------
# TEST 8 -- primary + identity failure
# ---------------------------------------------------------------------------


def test_8_primary_identity_failure_falls_back_to_legacy(tmp_path):
    executor = LocalV4_2Executor(mode="identity_mismatch")
    response, run_dir = _run(tmp_path, "primary-identity", mode="primary", executor=executor)
    routing = json.loads((run_dir / "structured_adapter_authority_routing.json").read_text())
    assert routing["authoritative_adapter"] == AUTHORITY_LEGACY
    assert routing["fallback_used"] is True


# ---------------------------------------------------------------------------
# TEST 9 -- primary + v4.2 runtime exception at the Shadow boundary
# ---------------------------------------------------------------------------


class _RaisingExecutor:
    def execute(self, context):
        raise RuntimeError("simulated structured adapter runtime exception")


def test_9_primary_runtime_exception_at_shadow_boundary_falls_back_to_legacy(tmp_path):
    executor = _RaisingExecutor()
    # The whole request must still complete -- the exception is contained
    # at the existing, pre-existing per-report Shadow execution boundary
    # (run_live_shadow_sidecar's own _invoke_executor try/except converts
    # a raised executor exception into that report's rejection, exactly
    # as it already did before Stage G -- this test proves Stage G's NEW
    # routing correctly treats that pre-existing rejection as "v4.2 did
    # not unanimously succeed", not that it invented new exception
    # handling of its own).
    response, run_dir = _run(tmp_path, "primary-exception", mode="primary", executor=executor)
    routing = json.loads((run_dir / "structured_adapter_authority_routing.json").read_text())
    assert routing["authoritative_adapter"] == AUTHORITY_LEGACY
    assert routing["fallback_used"] is True
    assert routing["fallback_reason"] == FALLBACK_REPORT_REJECTED


def test_9b_a_bug_in_stage_g_routing_itself_is_not_swallowed(tmp_path, monkeypatch):
    # Fail-soft covers only the v4.2 Shadow attempt itself. A genuine bug
    # in the NEW Stage G routing/authority-selection code (as opposed to a
    # v4.2 Shadow execution failure) must propagate normally, not be
    # silently absorbed into "Legacy wins" -- select_primary_authority is
    # called UNGUARDED (no try/except) in _run_week1_week2_artifact_
    # pipeline, unlike the Shadow sidecar call itself and the routing-
    # metadata write, which are each independently, narrowly guarded.
    import comqutor_alpha.api.routes_research as routes_research_module

    def _broken_select_primary_authority(*args, **kwargs):
        raise RuntimeError("simulated Stage G routing bug")

    monkeypatch.setattr(
        routes_research_module, "select_primary_authority", _broken_select_primary_authority
    )
    from comqutor_alpha.api.routes_research import _create_offline_run

    _run_id, created_dir = _create_offline_run(_payload("stage-g-bug"), tmp_path)
    with pytest.raises(RuntimeError, match="simulated Stage G routing bug"):
        routes_research_module._run_week1_week2_artifact_pipeline(
            Path(created_dir),
            None,
            structured_adapter_mode_decision=resolve_structured_adapter_mode("primary"),
            structured_adapter_shadow_executor=LocalV4_2Executor(mode="accepted"),
        )


# ---------------------------------------------------------------------------
# TEST 10 -- single authority per request, for every mode
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["legacy", "shadow", "primary"])
def test_10_exactly_one_authoritative_adapter_selected(tmp_path, mode):
    executor = LocalV4_2Executor(mode="accepted")
    _response, run_dir = _run(tmp_path, f"single-authority-{mode}", mode=mode, executor=executor)
    routing = json.loads((run_dir / "structured_adapter_authority_routing.json").read_text())
    # Exactly one of these two is true -- never both, never neither.
    assert (routing["authoritative_adapter"] == AUTHORITY_LEGACY) != (
        routing["authoritative_adapter"] == "structured_adapter.claim_extraction_shadow.v4.2"
    )


# ---------------------------------------------------------------------------
# TEST 11 -- downstream actually consumes the selected authority (dataflow,
# not just metadata)
# ---------------------------------------------------------------------------


def test_11a_primary_success_downstream_receives_v4_2_records(tmp_path):
    executor = LocalV4_2Executor(mode="accepted")
    _response, run_dir = _run(tmp_path, "downstream-v4-2", mode="primary", executor=executor)
    structured = json.loads((run_dir / "structured_agent_outputs.json").read_text())
    assert structured["adapter_version"] == "structured_adapter.claim_extraction_shadow.v4.2"
    assert structured["production_authority"] is True
    assert structured["shadow_only"] is False
    assert len(structured["records"]) == 4
    for record in structured["records"]:
        assert record["extraction_method"] in (
            "structured_llm_adapter_v4_2_shadow",
            "structured_llm_adapter_v4_shadow",
        )


def test_11b_primary_failure_downstream_receives_legacy_records(tmp_path):
    executor = LocalV4_2Executor(mode="unresolved")
    _response, run_dir = _run(tmp_path, "downstream-legacy", mode="primary", executor=executor)
    structured = json.loads((run_dir / "structured_agent_outputs.json").read_text())
    assert structured.get("adapter_version") != "structured_adapter.claim_extraction_shadow.v4.2"
    assert structured.get("production_authority") is not True
    legacy_only_run_dir = tmp_path / "downstream-legacy-legacy-baseline"
    _run(legacy_only_run_dir.parent, "downstream-legacy-legacy-baseline", mode="legacy")
    baseline = json.loads((legacy_only_run_dir / "structured_agent_outputs.json").read_text())
    assert {r["claim"] for r in structured["records"]} == {r["claim"] for r in baseline["records"]}


# ---------------------------------------------------------------------------
# TEST 12 -- primary no longer unconditionally degrades
# ---------------------------------------------------------------------------


def test_12_primary_mode_no_longer_degrades_unconditionally():
    decision = resolve_structured_adapter_mode("primary")
    assert decision.effective_mode == MODE_PRIMARY
    assert decision.shadow_enabled is True
    assert decision.reason_code is None
    # legacy/shadow behavior is completely unchanged.
    assert resolve_structured_adapter_mode("legacy").effective_mode == MODE_LEGACY
    assert resolve_structured_adapter_mode("shadow").effective_mode == MODE_SHADOW
    # The bare, no-override default is deliberately UNCHANGED (still
    # legacy) -- see structured_output_live_shadow.py's own docstring for
    # why: dozens of existing tests call this with no override and assert
    # zero Provider construction.
    assert resolve_structured_adapter_mode().effective_mode == MODE_LEGACY


# ---------------------------------------------------------------------------
# TEST 13 -- replay / verification stays zero-Provider
# ---------------------------------------------------------------------------


def test_13_authority_routing_metadata_write_makes_no_provider_call(tmp_path):
    executor = LocalV4_2Executor(mode="accepted")
    _response, run_dir = _run(tmp_path, "replay-zero-provider", mode="primary", executor=executor)
    routing = json.loads((run_dir / "structured_adapter_authority_routing.json").read_text())
    assert routing["primary_succeeded"] is True
    assert len(executor.calls) == 4  # all four via the injected fixture, never a real Provider


# ---------------------------------------------------------------------------
# Real stored v4.2 result integration (section 13): reuse the actual
# persisted output of the real, completed Final Live Canary. No Provider
# call is made anywhere in this test.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not REAL_CANARY_SHADOW_DIR.exists(), reason="real Final Live Canary artifact not present"
)
def test_real_stored_v4_2_canary_result_becomes_authoritative_via_select_primary_authority():
    shadow_output = json.loads((REAL_CANARY_SHADOW_DIR / SHADOW_OUTPUT_FILENAME).read_text())
    validation = json.loads((REAL_CANARY_SHADOW_DIR / SHADOW_VALIDATION_FILENAME).read_text())
    assert shadow_output["adapter_version"] == "structured_adapter.claim_extraction_shadow.v4.2"
    assert len(shadow_output["records"]) == 118  # the real Canary's TOTAL_LIVE_CLAIMS
    assert validation["accepted_report_count"] == 4
    assert validation["rejected_report_count"] == 0

    mode_decision = resolve_structured_adapter_mode("primary")
    decision = select_primary_authority(
        REAL_CANARY_SHADOW_DIR, mode_decision=mode_decision, validation_payload=validation
    )
    assert decision.primary_attempted is True
    assert decision.primary_succeeded is True
    assert decision.fallback_used is False
    assert decision.authoritative_adapter == "structured_adapter.claim_extraction_shadow.v4.2"
    assert decision.authoritative_payload is not None
    assert len(decision.authoritative_payload["records"]) == 118
    assert decision.authoritative_payload["production_authority"] is True
    assert decision.authoritative_payload["shadow_only"] is False


def test_real_stored_v4_2_canary_result_with_one_rejection_injected_falls_back():
    """Same real accepted sidecar content, but with a synthetically
    injected single rejection in the (copied) validation summary -- proves
    the unanimous-acceptance rule using the SAME real records, not a
    different fixture."""

    validation = json.loads((REAL_CANARY_SHADOW_DIR / SHADOW_VALIDATION_FILENAME).read_text())
    injected = deepcopy(validation)
    injected["accepted_report_count"] = 3
    injected["rejected_report_count"] = 1
    mode_decision = resolve_structured_adapter_mode("primary")
    decision = select_primary_authority(
        REAL_CANARY_SHADOW_DIR, mode_decision=mode_decision, validation_payload=injected
    )
    assert decision.primary_succeeded is False
    assert decision.fallback_used is True
    assert decision.fallback_reason == FALLBACK_REPORT_REJECTED
    assert decision.authoritative_adapter == AUTHORITY_LEGACY
    assert decision.authoritative_payload is None


# ---------------------------------------------------------------------------
# select_primary_authority unit tests: non-primary no-op, missing sidecar,
# no reports attempted.
# ---------------------------------------------------------------------------


def test_select_primary_authority_is_a_noop_outside_primary_mode(tmp_path):
    for mode_str in ("legacy", "shadow"):
        mode_decision = resolve_structured_adapter_mode(mode_str)
        decision = select_primary_authority(tmp_path, mode_decision=mode_decision, validation_payload={"reports": [], "accepted_report_count": 0, "rejected_report_count": 0})
        assert decision.primary_attempted is False
        assert decision.authoritative_adapter == AUTHORITY_LEGACY


def test_select_primary_authority_missing_validation_payload_falls_back(tmp_path):
    mode_decision = resolve_structured_adapter_mode("primary")
    decision = select_primary_authority(tmp_path, mode_decision=mode_decision, validation_payload=None)
    assert decision.fallback_used is True
    assert decision.fallback_reason == FALLBACK_SIDECAR_UNAVAILABLE


def test_select_primary_authority_zero_reports_attempted_falls_back(tmp_path):
    mode_decision = resolve_structured_adapter_mode("primary")
    decision = select_primary_authority(
        tmp_path,
        mode_decision=mode_decision,
        validation_payload={"reports": [], "accepted_report_count": 0, "rejected_report_count": 0},
    )
    assert decision.fallback_used is True
    assert decision.fallback_reason == FALLBACK_NO_REPORTS_ATTEMPTED


def test_select_primary_authority_empty_records_in_sidecar_falls_back(tmp_path):
    from comqutor_alpha.storage.file_store import save_json_record

    run_dir = tmp_path / "empty-sidecar-run"
    run_dir.mkdir()
    save_json_record(
        run_dir.name,
        SHADOW_OUTPUT_FILENAME,
        {
            "schema_version": "x",
            "adapter_version": "structured_adapter.claim_extraction_shadow.v4.2",
            "run_id": run_dir.name,
            "ticker": "NVDA",
            "records": [],
            "shadow_only": True,
            "production_authority": False,
            "selected_authority": AUTHORITY_LEGACY,
        },
        output_root=str(tmp_path),
    )
    mode_decision = resolve_structured_adapter_mode("primary")
    decision = select_primary_authority(
        run_dir,
        mode_decision=mode_decision,
        validation_payload={"reports": [{}], "accepted_report_count": 1, "rejected_report_count": 0},
    )
    assert decision.fallback_used is True
    assert decision.fallback_reason == FALLBACK_EMPTY_OR_NON_SUBSTANTIVE
