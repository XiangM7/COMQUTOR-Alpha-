from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

import comqutor_alpha.api.routes_research as routes_research
from comqutor_alpha.llm_runtime.manifest import verify_semantic_manifest
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway


class _Response:
    def __init__(self, content: str) -> None:
        self.content = content


class _SemanticModel:
    """Prompt-aware offline Provider double; it never touches a network."""

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, prompt: str) -> _Response:
        self.calls += 1
        payload = json.loads(prompt.split("\nINPUT_JSON:\n", 1)[1])
        if "segments" in payload:
            claims = []
            for segment in payload["segments"]:
                claims.append(
                    {
                        **segment,
                        "entities": ["AI", "GPU"],
                        "factors": ["AI Demand", "GPU Demand"],
                        "direction": "positive",
                        "confidence": 0.9,
                    }
                )
            return _Response(json.dumps({"claims": claims}))
        if "allowed_alpha_ids" in payload:
            return _Response(
                json.dumps({"decision": "defer", "selected_alpha_id": None})
            )
        if "allowed_factors" in payload:
            return _Response(json.dumps({"edges": []}))
        raise AssertionError("unexpected task payload")


class _MemoryRepository:
    """Repository-shaped in-memory double; no SQL engine or DB connection."""

    def __init__(self) -> None:
        self.graphs = {}
        self.conflicts = {}
        self.agent_outputs = {}

    def persist_agent_outputs(self, *, run_id, ticker, structured_payload) -> None:
        self.agent_outputs[run_id] = {
            "ticker": ticker,
            "structured_payload": deepcopy(structured_payload),
        }

    def persist_run(self, *, run_id, ticker, alpha_matches_payload, graph_payload) -> None:
        self.graphs[run_id] = {
            "ticker": ticker,
            "alpha_matches_payload": deepcopy(alpha_matches_payload),
            "graph_json": deepcopy(graph_payload),
        }

    def upsert_entity_alpha_exposures(self, **kwargs) -> None:
        del kwargs

    def persist_week4_results(
        self,
        *,
        run_id,
        ticker,
        activation_payload,
        conflict_payload,
    ) -> None:
        del ticker, activation_payload
        self.conflicts[run_id] = deepcopy(conflict_payload)

    def get_graph(self, run_id):
        return deepcopy(self.graphs.get(run_id))

    def get_week4_conflict_result(self, run_id):
        return deepcopy(self.conflicts.get(run_id))

    def get_research_run_record(self, run_id):
        del run_id
        return None


class _PersistenceFailingRepository(_MemoryRepository):
    def persist_agent_outputs(self, **kwargs) -> None:
        del kwargs
        raise OSError("synthetic persistence failure")


def _payload(run_id: str, *, empty: bool = False):
    outputs = []
    if not empty:
        outputs = [
            {
                "agent": "news_agent",
                "raw_output": "AI demand drives GPU demand.",
            }
        ]
    return {
        "run_id": run_id,
        "ticker": "NVDA",
        "analysis_date": "2026-06-30",
        "selected_analysts": ["news"],
        "offline_raw_agent_outputs": outputs,
    }


def _disable_data_sanity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes_research, "run_data_sanity_stage", lambda *args, **kwargs: None)


def _gateway(root: Path, run_id: str, model: _SemanticModel) -> Week2LLMGateway:
    return Week2LLMGateway(
        model,
        run_id=run_id,
        output_root=root,
        timeout_seconds=0.1,
        max_retries=0,
        max_calls=32,
        provider="fake-provider",
        model_name="fake-model",
    )


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _without_dynamic_metadata(value):
    if isinstance(value, dict):
        return {
            key: _without_dynamic_metadata(item)
            for key, item in value.items()
            if key
            not in {
                "created_at",
                "updated_at",
                "generated_at",
                "timestamp",
                "code_provenance",
            }
        }
    if isinstance(value, list):
        return [_without_dynamic_metadata(item) for item in value]
    return value


def test_default_disabled_live_run_creates_no_semantic_sidecars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_data_sanity(monkeypatch)
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "false")
    monkeypatch.setattr(
        "tradingagents.llm_clients.create_llm_client",
        lambda **kwargs: pytest.fail(f"Provider factory called: {kwargs}"),
    )

    response = routes_research.run_research_request(
        _payload("disabled-run"),
        output_root=tmp_path,
        graph_repository=_MemoryRepository(),
    )

    run_dir = tmp_path / "disabled-run"
    assert response["run_id"] == "disabled-run"
    assert not (run_dir / "llm_semantic_calls.jsonl").exists()
    assert not (run_dir / "llm_semantic_manifest.json").exists()
    assert "llm_semantic_calls" not in response["artifacts"]
    assert "llm_semantic_manifest" not in response["artifacts"]


def test_explicit_enabled_zero_call_run_writes_complete_fail_closed_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_data_sanity(monkeypatch)
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "true")
    model = _SemanticModel()
    gateway = _gateway(tmp_path, "zero-call-run", model)

    response = routes_research.run_research_request(
        _payload("zero-call-run", empty=True),
        output_root=tmp_path,
        week2_llm_gateway=gateway,
        graph_repository=_MemoryRepository(),
    )

    run_dir = tmp_path / "zero-call-run"
    manifest_path = run_dir / "llm_semantic_manifest.json"
    assert response["run_id"] == "zero-call-run"
    assert (run_dir / "llm_semantic_calls.jsonl").read_bytes() == b""
    manifest = _load(manifest_path)
    assert manifest["complete"] is True
    assert manifest["record_count"] == 0
    assert manifest["provider_call_count"] == 0
    assert manifest["exact_replay_ready"] is False
    assert model.calls == 0
    assert verify_semantic_manifest(manifest_path).valid


def test_abnormal_live_run_best_effort_finalizes_incomplete_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_data_sanity(monkeypatch)
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "true")
    model = _SemanticModel()
    gateway = _gateway(tmp_path, "failed-run", model)

    response = routes_research.run_research_request(
        _payload("failed-run"),
        output_root=tmp_path,
        week2_llm_gateway=gateway,
        graph_repository=_PersistenceFailingRepository(),
    )

    manifest = _load(tmp_path / "failed-run" / "llm_semantic_manifest.json")
    assert response["status"] == "failed"
    assert response["error_code"] == "AGENT_OUTPUTS_DB_WRITE_FAILED"
    assert manifest["complete"] is False
    assert manifest["exact_replay_ready"] is False
    assert manifest["record_count"] >= 1


def test_cache_miss_integration_adds_only_sidecars_not_business_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_data_sanity(monkeypatch)
    run_id = "behavior-invariant"
    legacy_root = tmp_path / "legacy"
    integrated_root = tmp_path / "integrated"
    legacy_root.mkdir()
    integrated_root.mkdir()
    legacy_model = _SemanticModel()
    integrated_model = _SemanticModel()

    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "false")
    legacy_response = routes_research.run_research_request(
        _payload(run_id),
        output_root=legacy_root,
        week2_llm_gateway=_gateway(legacy_root, run_id, legacy_model),
        graph_repository=_MemoryRepository(),
    )
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "true")
    integrated_response = routes_research.run_research_request(
        _payload(run_id),
        output_root=integrated_root,
        week2_llm_gateway=_gateway(integrated_root, run_id, integrated_model),
        graph_repository=_MemoryRepository(),
    )

    compared = (
        "structured_agent_outputs.json",
        "alpha_matches.json",
        "extracted_structures.json",
        "structure_graph.json",
        "conflicts.json",
    )
    for filename in compared:
        before = _without_dynamic_metadata(_load(legacy_root / run_id / filename))
        after = _without_dynamic_metadata(_load(integrated_root / run_id / filename))
        assert before == after, filename
    assert _without_dynamic_metadata(legacy_response) == _without_dynamic_metadata(
        integrated_response
    )
    assert legacy_model.calls == integrated_model.calls
    assert not (legacy_root / run_id / "llm_semantic_calls.jsonl").exists()
    assert (integrated_root / run_id / "llm_semantic_calls.jsonl").is_file()
    assert (integrated_root / run_id / "llm_semantic_manifest.json").is_file()
