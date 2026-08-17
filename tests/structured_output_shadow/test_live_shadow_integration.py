"""Phase 1 Stage E live-shadow wiring tests. Provider/network calls: zero."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from comqutor_alpha.api.routes_research import run_research_request
from comqutor_alpha.llm_runtime.cache import NullLLMResponseCache
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.structure_engine.structured_output_live_shadow import (
    SHADOW_COMPARISON_FILENAME,
    SHADOW_OUTPUT_FILENAME,
    SHADOW_VALIDATION_FILENAME,
    ShadowAttemptResult,
    resolve_structured_adapter_mode,
    verify_live_shadow_exact_replay,
)
from comqutor_alpha.structure_engine.structured_output_shadow import build_candidate_segments
from comqutor_alpha.structure_engine.structured_output_shadow_provider import (
    SHADOW_WEEK2_ERROR_LOG_ARTIFACT_PATH,
    run_real_provider_shadow_smoke_for_report_v4,
)
from comqutor_alpha.structure_engine.structured_output_shadow_v4 import (
    parse_report_shadow_v4,
)
from comqutor_alpha.structure_engine.structured_output_shadow_v4_1 import (
    StructuredOutputShadowParserV4_1,
    build_candidate_manifest_v4_1,
)
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

REPO_ROOT = Path(__file__).resolve().parents[2]
FOUR_FAMILY_FIXTURE = (
    REPO_ROOT
    / "outputs/runs/0e044e37-862c-43be-871c-31012cd660e7/raw_agent_outputs.json"
)
FOUR_FAMILY_AGENTS = {
    "fundamental_agent",
    "news_agent",
    "sentiment_agent",
    "market_agent",
}


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
        "analysis_date": "2026-08-10",
        "selected_analysts": ["fundamentals", "news", "sentiment", "market"],
        "offline_raw_agent_outputs": _outputs(),
    }


class LocalV4Executor:
    provider = "fixture-provider"
    model = "recorded-v4-fixture"
    profile_id = "offline-fixture"

    def __init__(self, mode: str = "accepted") -> None:
        self.mode = mode
        self.calls = []

    def execute(self, context):
        self.calls.append(context)
        if self.mode == "timeout":
            raise TimeoutError("simulated timeout")
        if self.mode == "malformed":
            proposal = "not-json{{"
        elif self.mode == "unresolved":
            proposal = {
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
        else:
            candidates, _filtered = build_candidate_segments(
                context.source_report,
                agent_output_id=context.agent_output_id,
            )
            candidate = next(item for item in candidates if item.get("source_spans"))
            proposal = {
                "claims": [
                    {
                        "claim": candidate["claim_hint"],
                        "supporting_quotes": [
                            candidate["source_spans"][0]["exact_quote"]
                        ],
                        "entities": [],
                        "factors": [],
                        "direction": "neutral",
                        "confidence": 0.8,
                    }
                ],
                "abstentions": [],
            }

        class Invoker:
            def invoke(_self, *, prompt, request):
                return deepcopy(proposal)

        bundle = parse_report_shadow_v4(
            semantic_invoker=Invoker(),
            source_report=context.source_report,
            run_id=context.run_id,
            ticker=context.ticker,
            agent=context.agent,
            agent_output_id=context.agent_output_id,
            factor_vocabulary=context.factor_vocabulary,
        )
        if self.mode == "identity_mismatch":
            bundle = deepcopy(bundle)
            bundle["ticker"] = "TSM"
        return ShadowAttemptResult(
            bundle=bundle,
            provider=self.provider,
            model=self.model,
            profile_id=self.profile_id,
            semantic_call_id=f"fixture:{len(self.calls)}",
            provider_called=False,
            provider_status="fixture",
            retry_count=0,
        )


class LocalV4_1Executor:
    """Accepted v4.1 candidate-bound fixture for live admission/replay."""

    def __init__(self) -> None:
        self.calls = []

    def execute(self, context):
        self.calls.append(context)
        candidates, _filtered = build_candidate_segments(
            context.source_report,
            agent_output_id=context.agent_output_id,
        )
        manifest = build_candidate_manifest_v4_1(
            source_report=context.source_report,
            run_id=context.run_id,
            ticker=context.ticker,
            agent=context.agent,
            agent_output_id=context.agent_output_id,
            candidate_segments=candidates,
        )
        candidate = manifest[0]
        quote = context.source_report[
            candidate["source_start"] : candidate["source_end"]
        ]

        class Invoker:
            def invoke(_self, *, prompt, request):
                return {
                    "claims": [
                        {
                            "claim": quote,
                            "supporting_evidence": [
                                {
                                    "quote": quote,
                                    "candidate_id": candidate["candidate_id"],
                                }
                            ],
                            "entities": [],
                            "factors": [],
                            "direction": "neutral",
                            "confidence": 0.8,
                        }
                    ],
                    "abstentions": [],
                }

        parser = StructuredOutputShadowParserV4_1(
            Invoker(), factor_vocabulary=context.factor_vocabulary
        )
        bundle = parser.parse_report_shadow_v4_1(
            source_report=context.source_report,
            run_id=context.run_id,
            ticker=context.ticker,
            agent=context.agent,
            agent_output_id=context.agent_output_id,
            candidate_segments=candidates,
        )
        return ShadowAttemptResult(
            bundle=bundle,
            provider="fixture-provider",
            model="recorded-v4.1-fixture",
            profile_id="offline-fixture",
            semantic_call_id=f"fixture-v4.1:{len(self.calls)}",
            provider_called=False,
            provider_status="fixture",
            retry_count=0,
            resolution_log=tuple(parser.last_resolution_diagnostics),
            candidate_manifest=tuple(parser.last_candidate_manifest),
        )


class GatewayFailureExecutor:
    """Offline real-Gateway-path executor for Shadow error isolation tests."""

    provider = "fixture-provider"
    model = "fixture-model"
    profile_id = "offline-fixture"

    class Model:
        def __init__(self, outcome: str) -> None:
            self.outcome = outcome

        def invoke(self, _prompt: str):
            if self.outcome == "provider_exception":
                raise RuntimeError("offline fixture provider exception")
            if self.outcome == "malformed":
                return SimpleNamespace(content="not-json{{")
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "claims": [
                            {
                                "claim": "Unsupported fixture claim.",
                                "supporting_quotes": ["quote absent from source"],
                                "entities": [],
                                "factors": [],
                                "direction": "unknown",
                                "confidence": 0.5,
                            }
                        ],
                        "abstentions": [],
                    }
                )
            )

    def __init__(self, run_dir: Path, outcome: str) -> None:
        self.run_dir = run_dir
        self.outcome = outcome
        self.session = None
        self.gateway = None

    def _initialize(self) -> None:
        runtime_dir = self.run_dir / "structured_adapter_shadow_runtime"
        runtime_dir.mkdir()
        self.session = SemanticRuntimeSession(
            run_id=self.run_dir.name,
            output_directory=runtime_dir,
            execution_mode="shadow",
            provider=self.provider,
            model=self.model,
            profile_id=self.profile_id,
            cache=NullLLMResponseCache(),
        )
        self.gateway = Week2LLMGateway(
            self.Model(self.outcome),
            run_id=self.run_dir.name,
            output_root=self.run_dir.parent,
            max_retries=0,
            max_calls=4,
            provider=self.provider,
            model_name=self.model,
            semantic_runtime=self.session,
            error_log_artifact_path=SHADOW_WEEK2_ERROR_LOG_ARTIFACT_PATH,
        )

    def execute(self, context):
        if self.gateway is None:
            self._initialize()
        assert self.gateway is not None
        bundle, invoker, _candidates, resolution_log = (
            run_real_provider_shadow_smoke_for_report_v4(
                gateway=self.gateway,
                source_report=context.source_report,
                run_id=context.run_id,
                ticker=context.ticker,
                agent=context.agent,
                agent_output_id=context.agent_output_id,
                factor_vocabulary=list(context.factor_vocabulary),
            )
        )
        invocation = invoker.last_invocation
        assert invocation is not None
        return ShadowAttemptResult(
            bundle=bundle,
            provider=self.provider,
            model=self.model,
            profile_id=self.profile_id,
            semantic_call_id=getattr(invocation.trace_handle, "call_id", None),
            provider_called=invocation.provider_called,
            provider_status=invocation.provider_status,
            retry_count=invocation.retry_count,
            resolution_log=tuple(resolution_log),
        )

    def close(self) -> None:
        assert self.session is not None
        self.session.finalize_manifest(complete=True)


def _read(run_dir: Path, name: str):
    return json.loads((run_dir / name).read_text())


def _without_runtime_timestamps(value):
    if isinstance(value, dict):
        return {
            key: _without_runtime_timestamps(item)
            for key, item in value.items()
            if key not in {"timestamp", "created_at", "updated_at", "generated_at", "completed_at"}
        }
    if isinstance(value, list):
        return [_without_runtime_timestamps(item) for item in value]
    return value


def _run(tmp_path: Path, name: str, *, mode: str, executor=None):
    response = run_research_request(
        _payload(name),
        output_root=tmp_path,
        structured_adapter_mode=mode,
        structured_adapter_shadow_executor=executor,
    )
    assert response["status"] == "completed"
    return response, tmp_path / name


def test_shadow_default_and_explicit_legacy_are_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("COMQUTOR_STRUCTURED_ADAPTER_MODE", raising=False)
    assert resolve_structured_adapter_mode().effective_mode == "legacy"
    executor = LocalV4Executor()
    _response, run_dir = _run(tmp_path, "shadow-disabled", mode="legacy", executor=executor)
    assert executor.calls == []
    for filename in (
        SHADOW_OUTPUT_FILENAME,
        SHADOW_VALIDATION_FILENAME,
        SHADOW_COMPARISON_FILENAME,
    ):
        assert not (run_dir / filename).exists()


def test_shadow_accepted_is_separate_and_four_family_legacy_outputs_are_identical(tmp_path):
    legacy_response, legacy_dir = _run(tmp_path / "legacy", "family-run", mode="legacy")
    executor = LocalV4Executor()
    shadow_response, shadow_dir = _run(
        tmp_path / "shadow", "family-run", mode="shadow", executor=executor
    )
    assert len(executor.calls) == 4
    assert {call.agent for call in executor.calls} == {
        "fundamental_agent",
        "news_agent",
        "sentiment_agent",
        "market_agent",
    }
    assert legacy_response == shadow_response
    for filename in (
        "structured_agent_outputs.json",
        "alpha_matches.json",
        "extracted_structures.json",
        "structure_graph.json",
        "alpha_activations.json",
        "conflicts.json",
    ):
        assert _without_runtime_timestamps(
            _read(legacy_dir, filename)
        ) == _without_runtime_timestamps(_read(shadow_dir, filename))

    shadow = _read(shadow_dir, SHADOW_OUTPUT_FILENAME)
    validation = _read(shadow_dir, SHADOW_VALIDATION_FILENAME)
    comparison = _read(shadow_dir, SHADOW_COMPARISON_FILENAME)
    assert len(shadow["records"]) == 4
    assert validation["accepted_report_count"] == 4
    assert validation["rejected_report_count"] == 0
    assert comparison["authoritative_downstream_changed"] is False
    assert shadow["production_authority"] is False
    shadow_ids = {record["claim_id"] for record in shadow["records"]}
    authoritative = "".join(
        json.dumps(_read(shadow_dir, name), sort_keys=True)
        for name in (
            "alpha_matches.json",
            "extracted_structures.json",
            "structure_graph.json",
            "alpha_activations.json",
            "conflicts.json",
        )
    )
    assert all(claim_id not in authoritative for claim_id in shadow_ids)


def test_malformed_shadow_fails_closed_without_affecting_legacy(tmp_path):
    _response, run_dir = _run(
        tmp_path, "shadow-malformed", mode="shadow", executor=LocalV4Executor("malformed")
    )
    validation = _read(run_dir, SHADOW_VALIDATION_FILENAME)
    assert validation["accepted_report_count"] == 0
    assert validation["rejected_report_count"] == 4
    assert _read(run_dir, SHADOW_OUTPUT_FILENAME)["records"] == []
    assert _read(run_dir, "structured_agent_outputs.json")["records"]


def test_unresolved_evidence_fails_closed(tmp_path):
    _response, run_dir = _run(
        tmp_path, "shadow-unresolved", mode="shadow", executor=LocalV4Executor("unresolved")
    )
    validation = _read(run_dir, SHADOW_VALIDATION_FILENAME)
    assert validation["accepted_report_count"] == 0


def test_rejected_forensics_are_persisted_only_on_rejected_sidecar_entries(tmp_path):
    class RejectedForensicExecutor(LocalV4Executor):
        def execute(self, context):
            attempt = super().execute(context)
            forensic = {
                "schema_version": "comqutor.structured_claim_shadow_rejected_forensic.v1",
                "classification": "REJECTED_CANDIDATE",
                "non_authoritative": True,
                "forensic_only": True,
                "admitted_claim_count": 0,
                "agent_output_id": context.agent_output_id,
            }
            return ShadowAttemptResult(
                bundle=attempt.bundle,
                provider=attempt.provider,
                model=attempt.model,
                profile_id=attempt.profile_id,
                semantic_call_id=attempt.semantic_call_id,
                provider_called=attempt.provider_called,
                provider_status=attempt.provider_status,
                retry_count=attempt.retry_count,
                resolution_log=attempt.resolution_log,
                rejected_forensic_record=forensic,
            )

    _response, run_dir = _run(
        tmp_path,
        "shadow-rejected-forensics",
        mode="shadow",
        executor=RejectedForensicExecutor("unresolved"),
    )
    validation = _read(run_dir, SHADOW_VALIDATION_FILENAME)
    assert validation["accepted_report_count"] == 0
    for entry in validation["reports"]:
        forensic = entry["rejected_forensics"]
        assert forensic["non_authoritative"] is True
        assert forensic["forensic_only"] is True
        assert forensic["admitted_claim_count"] == 0
        assert forensic["agent_output_id"] == entry["agent_output_id"]
    assert _read(run_dir, SHADOW_OUTPUT_FILENAME)["records"] == []
    assert any(item["reason_codes"] for item in validation["reports"])


def test_provider_exception_is_observable_and_never_escapes(tmp_path):
    response, run_dir = _run(
        tmp_path, "shadow-timeout", mode="shadow", executor=LocalV4Executor("timeout")
    )
    assert response["status"] == "completed"
    validation = _read(run_dir, SHADOW_VALIDATION_FILENAME)
    assert validation["accepted_report_count"] == 0
    assert all("SHADOW_INVOKER_ERROR" in item["reason_codes"] for item in validation["reports"])
    assert _read(run_dir, "structured_agent_outputs.json")["records"]


@pytest.mark.parametrize("outcome", ["validation_rejected", "provider_exception", "malformed"])
def test_gateway_shadow_failure_cannot_toggle_canonical_week2_error_metadata(
    tmp_path, outcome
):
    legacy_response, _legacy_dir = _run(
        tmp_path / "legacy", "shadow-error-isolation", mode="legacy"
    )
    shadow_dir = tmp_path / "shadow" / "shadow-error-isolation"
    executor = GatewayFailureExecutor(shadow_dir, outcome)
    shadow_response, _shadow_dir = _run(
        tmp_path / "shadow",
        "shadow-error-isolation",
        mode="shadow",
        executor=executor,
    )
    executor.close()

    assert legacy_response == shadow_response
    assert legacy_response["artifacts"]["week2_llm_error_logs"] is False
    assert shadow_response["artifacts"]["week2_llm_error_logs"] is False
    assert not (shadow_dir / "error_logs/week2_llm_errors.jsonl").exists()
    shadow_error_log = shadow_dir / SHADOW_WEEK2_ERROR_LOG_ARTIFACT_PATH
    assert shadow_error_log.exists()
    assert "structured_claim_shadow" in shadow_error_log.read_text(encoding="utf-8")
    validation = _read(shadow_dir, SHADOW_VALIDATION_FILENAME)
    assert validation["accepted_report_count"] == 0
    assert validation["rejected_report_count"] == 4


def test_identity_mismatch_fails_closed(tmp_path):
    _response, run_dir = _run(
        tmp_path,
        "shadow-identity",
        mode="shadow",
        executor=LocalV4Executor("identity_mismatch"),
    )
    validation = _read(run_dir, SHADOW_VALIDATION_FILENAME)
    assert validation["accepted_report_count"] == 0
    assert all(
        "SHADOW_IDENTITY_MISMATCH" in item["reason_codes"] for item in validation["reports"]
    )


def test_accepted_live_shadow_exact_replay_is_provider_zero(tmp_path, monkeypatch):
    executor = LocalV4Executor()
    _response, run_dir = _run(
        tmp_path, "shadow-replay", mode="shadow", executor=executor
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("provider/network code was invoked during exact replay")

    monkeypatch.setattr(executor, "execute", forbidden)
    replay = verify_live_shadow_exact_replay(run_dir)
    assert replay["status"] == "PASS", replay
    assert replay["accepted_report_count"] == 4
    assert replay["provider_calls"] == 0
    assert replay["provider_zero"] is True


def test_v4_1_candidate_manifest_is_admitted_persisted_and_replayed(tmp_path):
    executor = LocalV4_1Executor()
    _response, run_dir = _run(
        tmp_path, "shadow-v4-1-replay", mode="shadow", executor=executor
    )
    validation = _read(run_dir, SHADOW_VALIDATION_FILENAME)
    assert validation["accepted_report_count"] == 4
    assert all(item["candidate_manifest"] for item in validation["reports"])
    assert all(
        item["prompt_version"].endswith(".v4.1")
        for item in validation["reports"]
    )
    replay = verify_live_shadow_exact_replay(run_dir)
    assert replay["status"] == "PASS", replay
    assert replay["accepted_report_count"] == 4
    assert replay["provider_calls"] == 0


def test_primary_request_now_enables_real_shadow_execution_stage_g(tmp_path):
    """Supersedes this test's own former name/assertions
    (``test_primary_request_is_not_authorized_during_stage_e``): Stage G
    (real primary-authority routing, see
    ``structured_output_live_shadow.select_primary_authority`` and
    ``tests/structured_output_shadow/test_stage_g_primary_authority_
    routing.py``) intentionally supersedes the earlier Stage-E-only
    restriction this test used to encode. A requested ``"primary"`` mode
    now genuinely enables Shadow execution -- it is no longer silently
    degraded to legacy. Whether v4.2 becomes AUTHORITATIVE for a given run
    is a separate question, covered exhaustively by the Stage G test file;
    this test only re-confirms mode *resolution* is no longer degraded."""

    decision = resolve_structured_adapter_mode("primary")
    assert decision.effective_mode == "primary"
    assert decision.shadow_enabled is True
    assert decision.reason_code is None
    executor = LocalV4Executor()
    _response, run_dir = _run(tmp_path, "shadow-primary", mode="primary", executor=executor)
    assert len(executor.calls) == 4
    assert (run_dir / SHADOW_OUTPUT_FILENAME).exists()
