"""Track D: Historical Architecture Replay service tests.

Uses small, synthetic ``raw_agent_outputs.json`` fixtures under ``tmp_path``
so these tests never touch the real ``outputs/runs/`` tree and never call a
real Provider. Real-historical-run acceptance (MSFT/SNDK) is covered
separately by the sprint's replay/audit run, not by this hermetic suite.
"""

from __future__ import annotations

import json

import pytest

from comqutor_alpha.replay.cli import main as replay_cli_main
from comqutor_alpha.replay.pipeline import (
    ReplaySourceIncompleteError,
    run_structure_replay,
)

RUN_ID = "test-source-run-0001"


def _write_source_run(base_dir, *, ticker="MSFT", claim_text=None, extra_agent_outputs=None):
    run_dir = base_dir / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)

    claim_text = claim_text or (
        "AI CapEx spending is driving strong AI Demand growth this quarter. "
        "Revenue guidance was raised for the coming year. "
        "Cloud infrastructure investment continues to accelerate across hyperscalers."
    )
    agent_outputs = [
        {
            "agent_output_id": f"{RUN_ID}:market_agent:market_report",
            "run_id": RUN_ID,
            "ticker": ticker,
            "agent": "market_agent",
            "tradingagents_agent": "Market Analyst",
            "source_field": "market_report",
            "source_path": "market_report",
            "source_candidates": ["market_report"],
            "raw_output": claim_text,
        }
    ]
    if extra_agent_outputs:
        agent_outputs.extend(extra_agent_outputs)

    raw_payload = {
        "schema_version": "week1.raw_agent_outputs.v1",
        "run_id": RUN_ID,
        "ticker": ticker,
        "agent_outputs": agent_outputs,
    }
    (run_dir / "raw_agent_outputs.json").write_text(json.dumps(raw_payload), encoding="utf-8")

    metadata = {
        "run_id": RUN_ID,
        "ticker": ticker,
        "trade_date": "2026-07-01",
        "profile_id": "comqutor_anthropic_medium_sonnet46_v1",
        "created_at": "2026-07-01T00:00:00Z",
        "config": {"llm_provider": "anthropic", "quick_think_llm": "claude-sonnet-4-6", "deep_think_llm": "claude-sonnet-4-6"},
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return run_dir


@pytest.mark.unit
class TestReplayCore:
    def test_replay_creates_new_run_from_valid_source(self, tmp_path):
        _write_source_run(tmp_path)
        result = run_structure_replay(
            RUN_ID,
            source_output_root=str(tmp_path),
            replay_output_root=str(tmp_path / "replays"),
        )
        assert result.status == "completed"
        assert result.replay_run_id != RUN_ID
        assert result.output_dir is not None
        structured = json.loads((tmp_path / "replays" / result.replay_run_id / "structured_agent_outputs.json").read_text())
        assert len(structured["records"]) >= 1

    def test_missing_raw_outputs_raises_source_incomplete(self, tmp_path):
        run_dir = tmp_path / RUN_ID
        run_dir.mkdir(parents=True)
        (run_dir / "metadata.json").write_text("{}", encoding="utf-8")
        with pytest.raises(ReplaySourceIncompleteError):
            run_structure_replay(RUN_ID, source_output_root=str(tmp_path))

    def test_replay_ignores_stale_structured_output_in_source_dir(self, tmp_path):
        run_dir = _write_source_run(tmp_path)
        # A deliberately wrong/stale structured_agent_outputs.json sitting in the
        # source dir must never be read as replay input.
        (run_dir / "structured_agent_outputs.json").write_text(
            json.dumps({"records": [{"claim_id": "poisoned", "claim": "SHOULD NEVER APPEAR"}]}),
            encoding="utf-8",
        )
        result = run_structure_replay(RUN_ID, source_output_root=str(tmp_path), replay_output_root=str(tmp_path / "replays"))
        structured = json.loads((tmp_path / "replays" / result.replay_run_id / "structured_agent_outputs.json").read_text())
        claim_ids = {r["claim_id"] for r in structured["records"]}
        assert "poisoned" not in claim_ids

    def test_source_hash_and_mtime_unchanged(self, tmp_path):
        run_dir = _write_source_run(tmp_path)
        raw_path = run_dir / "raw_agent_outputs.json"
        before_bytes = raw_path.read_bytes()
        before_mtime = raw_path.stat().st_mtime_ns

        result = run_structure_replay(RUN_ID, source_output_root=str(tmp_path), replay_output_root=str(tmp_path / "replays"))

        assert result.source_raw_sha256_before == result.source_raw_sha256_after
        assert raw_path.read_bytes() == before_bytes
        assert raw_path.stat().st_mtime_ns == before_mtime
        assert result.status == "completed"

    def test_new_run_id_generated_each_call(self, tmp_path):
        _write_source_run(tmp_path)
        r1 = run_structure_replay(RUN_ID, source_output_root=str(tmp_path), replay_output_root=str(tmp_path / "replays"))
        r2 = run_structure_replay(RUN_ID, source_output_root=str(tmp_path), replay_output_root=str(tmp_path / "replays"))
        assert r1.replay_run_id != r2.replay_run_id

    def test_replay_does_not_overwrite_source_files(self, tmp_path):
        run_dir = _write_source_run(tmp_path)
        (run_dir / "structure_graph.json").write_text(json.dumps({"edges": ["untouched"]}), encoding="utf-8")
        before = (run_dir / "structure_graph.json").read_text()
        run_structure_replay(RUN_ID, source_output_root=str(tmp_path), replay_output_root=str(tmp_path / "replays"))
        assert (run_dir / "structure_graph.json").read_text() == before

    def test_provider_and_tradingagents_call_counts_are_zero(self, tmp_path):
        _write_source_run(tmp_path)
        result = run_structure_replay(RUN_ID, source_output_root=str(tmp_path), replay_output_root=str(tmp_path / "replays"))
        assert result.tradingagents_calls == 0
        assert result.llm_provider_calls == 0
        assert result.market_data_provider_calls == 0
        assert result.database_writes == 0

    def test_lineage_metadata_fields_present(self, tmp_path):
        _write_source_run(tmp_path)
        result = run_structure_replay(RUN_ID, source_output_root=str(tmp_path), replay_output_root=str(tmp_path / "replays"))
        metadata = json.loads((tmp_path / "replays" / result.replay_run_id / "metadata.json").read_text())
        required = [
            "run_type", "replay_run_id", "source_run_id", "source_ticker", "source_trade_date",
            "source_raw_artifact_path", "source_raw_sha256", "source_raw_output_count",
            "source_profile_id", "source_provider", "source_models", "source_created_at",
            "replay_created_at", "replay_mode", "pipeline_git_head", "pipeline_worktree_dirty",
            "pipeline_version", "claim_adapter_version", "taxonomy_version", "alias_version",
            "relation_grammar_version", "graph_schema_version", "activation_version",
            "tradingagents_calls", "llm_provider_calls", "market_data_provider_calls", "database_writes",
        ]
        for key in required:
            assert key in metadata, f"missing lineage field: {key}"
        assert metadata["run_type"] == "architecture_replay"
        assert metadata["tradingagents_calls"] == 0
        assert metadata["llm_provider_calls"] == 0
        assert metadata["market_data_provider_calls"] == 0

    def test_direction_unknown_claim_still_eligible_downstream(self, tmp_path):
        # A pure factual/data claim with no directional verb -> direction=unknown,
        # must still reach structured records (never silently dropped).
        _write_source_run(
            tmp_path,
            claim_text="The reported figure was 42.0 million units in the filing period.",
        )
        result = run_structure_replay(RUN_ID, source_output_root=str(tmp_path), replay_output_root=str(tmp_path / "replays"))
        structured = json.loads((tmp_path / "replays" / result.replay_run_id / "structured_agent_outputs.json").read_text())
        directions = {r.get("direction") for r in structured["records"]}
        assert "unknown" in directions or "neutral" in directions

    def test_two_identical_replays_are_deterministic(self, tmp_path):
        _write_source_run(tmp_path)
        run_structure_replay(
            RUN_ID, source_output_root=str(tmp_path), replay_output_root=str(tmp_path / "replays"), replay_run_id="fixed-a"
        )
        run_structure_replay(
            RUN_ID, source_output_root=str(tmp_path), replay_output_root=str(tmp_path / "replays"), replay_run_id="fixed-b"
        )
        s1 = json.loads((tmp_path / "replays" / "fixed-a" / "structured_agent_outputs.json").read_text())
        s2 = json.loads((tmp_path / "replays" / "fixed-b" / "structured_agent_outputs.json").read_text())
        claims_1 = [(r["claim"], r["direction"]) for r in s1["records"]]
        claims_2 = [(r["claim"], r["direction"]) for r in s2["records"]]
        assert claims_1 == claims_2

    def test_output_directory_not_reused(self, tmp_path):
        _write_source_run(tmp_path)
        run_structure_replay(
            RUN_ID, source_output_root=str(tmp_path), replay_output_root=str(tmp_path / "replays"), replay_run_id="dup-run"
        )
        with pytest.raises(FileExistsError):
            run_structure_replay(
                RUN_ID, source_output_root=str(tmp_path), replay_output_root=str(tmp_path / "replays"), replay_run_id="dup-run"
            )

    def test_persist_false_writes_nothing(self, tmp_path):
        _write_source_run(tmp_path)
        result = run_structure_replay(
            RUN_ID, source_output_root=str(tmp_path), replay_output_root=str(tmp_path / "replays"), persist=False
        )
        assert result.output_dir is None
        assert not (tmp_path / "replays").exists()


@pytest.mark.unit
class TestReplayComparison:
    def test_comparison_counts_are_accurate(self, tmp_path):
        run_dir = _write_source_run(tmp_path)
        (run_dir / "structured_agent_outputs.json").write_text(
            json.dumps({"records": [{"claim_id": "old:1"}, {"claim_id": "old:2"}]}), encoding="utf-8"
        )
        (run_dir / "extracted_structures.json").write_text(
            json.dumps({"nodes": [{"id": "ai_demand"}], "edges": []}), encoding="utf-8"
        )
        (run_dir / "structure_graph.json").write_text(
            json.dumps({"edges": [], "activation": {"alphas": [{"alpha_id": "A001", "status": "inactive"}]}}),
            encoding="utf-8",
        )
        result = run_structure_replay(RUN_ID, source_output_root=str(tmp_path), replay_output_root=str(tmp_path / "replays"))
        comp = result.comparison
        assert comp["before_claim_count"] == 2
        assert comp["after_claim_count"] >= 1
        assert comp["before_factor_count"] == 1

    def test_new_and_removed_edges_carry_provenance(self, tmp_path):
        run_dir = _write_source_run(tmp_path)
        # "before" extracted has one edge that "after" (this source text) will not reproduce.
        (run_dir / "extracted_structures.json").write_text(
            json.dumps(
                {
                    "nodes": [],
                    "edges": [
                        {
                            "source_record_id": "gone:1",
                            "source_label": "AI Demand",
                            "target_label": "Revenue Growth",
                            "rule_name": "forward_transitive_causal",
                            "source_claim": "stale claim",
                            "edge_type": "causal",
                            "assertion_status": "asserted",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "structure_graph.json").write_text(json.dumps({"edges": [], "activation": {"alphas": []}}), encoding="utf-8")
        result = run_structure_replay(RUN_ID, source_output_root=str(tmp_path), replay_output_root=str(tmp_path / "replays"))
        for edge in result.comparison["removed_edges"]:
            assert edge["claim_id"]
            assert edge["source_factor"]
            assert edge["target_factor"]
            assert edge["relation"]


@pytest.mark.unit
class TestReplayCLI:
    def test_cli_runs_end_to_end(self, tmp_path, capsys):
        _write_source_run(tmp_path)
        exit_code = replay_cli_main(
            [
                "--source-run-id", RUN_ID,
                "--source-output-root", str(tmp_path),
                "--output-root", str(tmp_path / "replays"),
            ]
        )
        assert exit_code == 0
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "completed"
        assert out["source_artifact_hash_unchanged"] is True
        assert out["provider_calls"] == 0

    def test_cli_ticker_mismatch_fails(self, tmp_path, capsys):
        _write_source_run(tmp_path, ticker="MSFT")
        exit_code = replay_cli_main(
            [
                "--source-run-id", RUN_ID,
                "--source-output-root", str(tmp_path),
                "--output-root", str(tmp_path / "replays"),
                "--ticker", "SNDK",
            ]
        )
        assert exit_code == 3
