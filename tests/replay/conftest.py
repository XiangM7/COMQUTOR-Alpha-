from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

import comqutor_alpha.api.routes_research as routes_research
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway


class OfflineSemanticModel:
    """Prompt-aware Provider double used only while producing a live fixture.

    ``alpha_decision`` controls the alpha_classifier branch's response --
    "select" (default, the taxonomy's own first alpha_id, sorted, stable
    across runs) for a genuine, bindable MATCHED decision, or "none" for a
    genuine, bindable semantic-NONE decision. Both are real, valid LLM
    decisions under Pure-LLM Alpha semantic authority -- never a defer/
    fallback stand-in."""

    def __init__(self, *, alpha_decision: str = "select") -> None:
        self.calls = 0
        assert alpha_decision in ("select", "none")
        self._alpha_decision = alpha_decision

    def invoke(self, prompt: str):
        self.calls += 1
        payload = json.loads(prompt.split("\nINPUT_JSON:\n", 1)[1])
        if "segments" in payload:
            claims = [
                {
                    **segment,
                    "entities": ["NVIDIA", "GPU"],
                    "factors": [
                        "AI Demand",
                        "GPU Demand",
                        "Revenue Growth",
                        "Valuation Risk",
                    ],
                    "direction": "positive",
                    "confidence": 0.91,
                }
                for segment in payload["segments"]
            ]
            return _Response(json.dumps({"claims": claims}))
        if "alpha_taxonomy" in payload:
            if self._alpha_decision == "none":
                return _Response(json.dumps({"decision": "none", "selected_alpha_id": None}))
            # Pure-LLM Alpha Semantic Authority: "defer" is no longer a
            # recognized decision value -- the mock returns a genuine,
            # deterministic "select" (the taxonomy's own first alpha_id,
            # sorted, so this is stable across runs) so the fixture exercises
            # a real, bindable semantic decision and matched_alpha stays
            # non-null (B1's stance upgrade still has a real Alpha to
            # evaluate; see eligible_live_source's own comment below).
            first_alpha_id = payload["alpha_taxonomy"][0]["alpha_id"]
            return _Response(
                json.dumps({"decision": "select", "selected_alpha_id": first_alpha_id})
            )
        if "allowed_factors" in payload:
            factors = payload["allowed_factors"]
            edges = []
            if len(factors) >= 2:
                edges.append(
                    {
                        "source_factor": factors[0],
                        "target_factor": factors[1],
                        "edge_type": "causal",
                        "assertion_status": "asserted",
                        "confidence": 0.87,
                    }
                )
            return _Response(json.dumps({"edges": edges}))
        if "items" in payload:
            items = [
                {
                    "claim_id": item["claim_id"],
                    "target_alpha_id": item["target_alpha_id"],
                    "stance": "neutral_background",
                }
                for item in payload["items"]
            ]
            return _Response(json.dumps({"items": items}))
        raise AssertionError("unexpected semantic task")


class _Response:
    def __init__(self, content: str) -> None:
        self.content = content


class OfflineMemoryRepository:
    """Repository-shaped double with no connection, SQL, or external state."""

    def __init__(self) -> None:
        self.graphs: dict[str, dict] = {}
        self.conflicts: dict[str, dict] = {}

    def persist_agent_outputs(self, **kwargs) -> None:
        del kwargs

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


def file_tree_snapshot(directory: Path) -> dict[str, tuple[int, str, int]]:
    import hashlib

    return {
        path.relative_to(directory).as_posix(): (
            path.stat().st_size,
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_mtime_ns,
        )
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


@pytest.fixture
def eligible_live_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    run_id = "eligible-live-source"
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "true")
    monkeypatch.setattr(
        routes_research,
        "run_data_sanity_stage",
        lambda *args, **kwargs: None,
    )
    model = OfflineSemanticModel()
    gateway = Week2LLMGateway(
        model,
        run_id=run_id,
        output_root=tmp_path,
        timeout_seconds=0.1,
        max_retries=0,
        max_calls=32,
        provider="offline-fixture-provider",
        model_name="offline-fixture-model",
    )
    response = routes_research.run_research_request(
        {
            "run_id": run_id,
            "ticker": "NVDA",
            "analysis_date": "2026-06-30",
            "selected_analysts": ["news"],
            "offline_raw_agent_outputs": [
                {
                    "agent": "news_agent",
                    "raw_output": (
                        "AI demand drives GPU demand and revenue growth while "
                        "valuation risk creates downside."
                    ),
                }
            ],
        },
        output_root=tmp_path,
        week2_llm_gateway=gateway,
        graph_repository=OfflineMemoryRepository(),
    )
    assert response["status"] == "completed"
    # 4, not the pre-Alpha-Authority-Migration 3: the Alpha classifier's
    # mock response is a genuine select (see the "alpha_taxonomy" branch
    # above) -- a real, non-null matched_alpha -- so B1's own LLM stance
    # upgrade legitimately fires a 4th call where it previously never ran at
    # all. Not a bug; see the Alpha Mapper Authority Migration, Post-
    # Migration Registry Cleanup, and Pure-LLM Alpha Semantic Authority
    # reports.
    assert model.calls == 4
    source_dir = tmp_path / run_id
    manifest = json.loads(
        (source_dir / "llm_semantic_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["complete"] is True
    assert manifest["exact_replay_ready"] is True
    assert manifest["tasks"] == {
        "alpha_classifier": 1,
        "evidence_stance_classifier": 1,
        "structure_extractor": 1,
        "structured_adapter": 1,
    }
    return source_dir


@pytest.fixture
def eligible_live_source_alpha_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Same shape as ``eligible_live_source``, except the Alpha classifier's
    mock response is a genuine, bindable decision=none -- Pure-LLM Alpha
    Production Boundary Hardening test M (Exact Semantic Replay with a
    recorded NONE decision)."""
    run_id = "eligible-live-source-alpha-none"
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "true")
    monkeypatch.setattr(
        routes_research,
        "run_data_sanity_stage",
        lambda *args, **kwargs: None,
    )
    model = OfflineSemanticModel(alpha_decision="none")
    gateway = Week2LLMGateway(
        model,
        run_id=run_id,
        output_root=tmp_path,
        timeout_seconds=0.1,
        max_retries=0,
        max_calls=32,
        provider="offline-fixture-provider",
        model_name="offline-fixture-model",
    )
    response = routes_research.run_research_request(
        {
            "run_id": run_id,
            "ticker": "NVDA",
            "analysis_date": "2026-06-30",
            "selected_analysts": ["news"],
            "offline_raw_agent_outputs": [
                {
                    "agent": "news_agent",
                    "raw_output": (
                        "AI demand drives GPU demand and revenue growth while "
                        "valuation risk creates downside."
                    ),
                }
            ],
        },
        output_root=tmp_path,
        week2_llm_gateway=gateway,
        graph_repository=OfflineMemoryRepository(),
    )
    assert response["status"] == "completed"
    # 3, not 4: decision=none means matched_alpha stays null, so B1's own
    # LLM stance upgrade has nothing to request for this claim
    # (evidence_stance_llm.retained_target_alpha_ids: "a claim with
    # matched_alpha = null contributes nothing") -- it legitimately never
    # fires a 4th call, unlike eligible_live_source's select case.
    assert model.calls == 3
    source_dir = tmp_path / run_id
    manifest = json.loads(
        (source_dir / "llm_semantic_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["complete"] is True
    assert manifest["exact_replay_ready"] is True
    assert manifest["tasks"] == {
        "alpha_classifier": 1,
        "structure_extractor": 1,
        "structured_adapter": 1,
    }
    return source_dir
