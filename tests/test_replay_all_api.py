"""Tests for POST /api/replay-all -- one-click batch replay of every saved
TradingAgents raw output. Uses small synthetic ``raw_agent_outputs.json``
fixtures under ``tmp_path`` so these tests never touch the real
``outputs/runs/`` tree and never call a real Provider.
"""

from __future__ import annotations

import json
import threading

import pytest

from comqutor_alpha.api.routes_replay_all import (
    _REPLAY_ALL_LOCK,
    _discover_source_runs,
    replay_all_saved_outputs,
)


def _write_source_run(base_dir, run_id, *, ticker="MSFT", claim_text=None, write_raw=True):
    run_dir = base_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if not write_raw:
        return run_dir
    claim_text = claim_text or (
        "AI CapEx spending is driving strong AI Demand growth this quarter. "
        "Revenue guidance was raised for the coming year."
    )
    raw_payload = {
        "schema_version": "week1.raw_agent_outputs.v1",
        "run_id": run_id,
        "ticker": ticker,
        "agent_outputs": [
            {
                "agent_output_id": f"{run_id}:market_agent:market_report",
                "run_id": run_id,
                "ticker": ticker,
                "agent": "market_agent",
                "tradingagents_agent": "Market Analyst",
                "source_field": "market_report",
                "source_path": "market_report",
                "source_candidates": ["market_report"],
                "raw_output": claim_text,
            }
        ],
    }
    (run_dir / "raw_agent_outputs.json").write_text(json.dumps(raw_payload), encoding="utf-8")
    return run_dir


@pytest.fixture(autouse=True)
def _release_lock_if_stuck():
    """Safety net: if a prior failing test left the module-level lock held,
    free it before and after this test so tests never interfere."""
    if _REPLAY_ALL_LOCK.locked():
        _REPLAY_ALL_LOCK.release()
    yield
    if _REPLAY_ALL_LOCK.locked():
        _REPLAY_ALL_LOCK.release()


@pytest.mark.unit
class TestDiscoverSourceRuns:
    def test_only_dirs_with_raw_agent_outputs_are_discovered(self, tmp_path):
        _write_source_run(tmp_path, "run-with-raw", ticker="SNDK")
        _write_source_run(tmp_path, "run-without-raw", write_raw=False)
        (tmp_path / "run-without-raw" / "structured_agent_outputs.json").write_text("{}", encoding="utf-8")

        discovered = _discover_source_runs(str(tmp_path))
        run_ids = [run_id for run_id, _ticker in discovered]
        assert "run-with-raw" in run_ids
        assert "run-without-raw" not in run_ids

    def test_corrupted_raw_json_is_skipped(self, tmp_path):
        run_dir = _write_source_run(tmp_path, "run-corrupt")
        (run_dir / "raw_agent_outputs.json").write_text("{not valid json", encoding="utf-8")

        discovered = _discover_source_runs(str(tmp_path))
        assert "run-corrupt" not in [run_id for run_id, _ in discovered]

    def test_non_directory_entries_are_skipped(self, tmp_path):
        (tmp_path / "stray_file.txt").write_text("hello", encoding="utf-8")
        discovered = _discover_source_runs(str(tmp_path))
        assert discovered == []

    def test_missing_root_returns_empty(self, tmp_path):
        assert _discover_source_runs(str(tmp_path / "does_not_exist")) == []

    def test_ticker_extracted_from_raw_payload(self, tmp_path):
        _write_source_run(tmp_path, "run-1", ticker="NVDA")
        discovered = _discover_source_runs(str(tmp_path))
        assert discovered == [("run-1", "NVDA")]


@pytest.mark.unit
class TestReplayAllSavedOutputs:
    def test_processes_only_runs_with_raw_agent_outputs(self, tmp_path):
        source_root = tmp_path / "runs"
        _write_source_run(source_root, "run-a", ticker="MSFT")
        _write_source_run(source_root, "run-b", write_raw=False)

        result = replay_all_saved_outputs(
            source_output_root=str(source_root), replay_output_root=str(tmp_path / "replays")
        )
        assert result["total_runs_found"] == 1
        assert result["results"][0]["source_run_id"] == "run-a"

    def test_one_run_failing_does_not_block_others(self, tmp_path, monkeypatch):
        source_root = tmp_path / "runs"
        _write_source_run(source_root, "run-ok-1", ticker="MSFT")
        _write_source_run(source_root, "run-boom", ticker="SNDK")
        _write_source_run(source_root, "run-ok-2", ticker="AMD")

        import comqutor_alpha.api.routes_replay_all as module

        real_run = module.run_structure_replay

        def _flaky(*, source_run_id, **kwargs):
            if source_run_id == "run-boom":
                raise RuntimeError("simulated pipeline crash")
            return real_run(source_run_id=source_run_id, **kwargs)

        monkeypatch.setattr(module, "run_structure_replay", _flaky)

        result = replay_all_saved_outputs(
            source_output_root=str(source_root), replay_output_root=str(tmp_path / "replays")
        )
        assert result["total_runs_found"] == 3
        assert result["completed_count"] == 2
        assert result["failed_count"] == 1
        statuses = {r["source_run_id"]: r["status"] for r in result["results"]}
        assert statuses["run-ok-1"] == "completed"
        assert statuses["run-boom"] == "failed"
        assert statuses["run-ok-2"] == "completed"
        boom_row = next(r for r in result["results"] if r["source_run_id"] == "run-boom")
        assert boom_row["error_code"] == "REPLAY_SERVICE_ERROR"
        assert "simulated pipeline crash" not in json.dumps(boom_row)

    def test_each_run_gets_independent_replay_run_id(self, tmp_path):
        source_root = tmp_path / "runs"
        _write_source_run(source_root, "run-a", ticker="MSFT")
        _write_source_run(source_root, "run-b", ticker="SNDK")

        result = replay_all_saved_outputs(
            source_output_root=str(source_root), replay_output_root=str(tmp_path / "replays")
        )
        replay_ids = [r["replay_run_id"] for r in result["results"]]
        assert len(replay_ids) == len(set(replay_ids)) == 2
        assert all(rid.startswith("replay-") for rid in replay_ids)

    def test_source_artifacts_unchanged(self, tmp_path):
        source_root = tmp_path / "runs"
        run_dir = _write_source_run(source_root, "run-a", ticker="MSFT")
        raw_path = run_dir / "raw_agent_outputs.json"
        before_bytes = raw_path.read_bytes()
        before_mtime = raw_path.stat().st_mtime_ns

        replay_all_saved_outputs(source_output_root=str(source_root), replay_output_root=str(tmp_path / "replays"))

        assert raw_path.read_bytes() == before_bytes
        assert raw_path.stat().st_mtime_ns == before_mtime

    def test_provider_and_tradingagents_calls_always_zero(self, tmp_path):
        source_root = tmp_path / "runs"
        _write_source_run(source_root, "run-a", ticker="MSFT")
        result = replay_all_saved_outputs(
            source_output_root=str(source_root), replay_output_root=str(tmp_path / "replays")
        )
        assert result["provider_calls"] == 0
        assert result["tradingagents_calls"] == 0

    def test_empty_source_root_returns_zero_runs(self, tmp_path):
        source_root = tmp_path / "runs"
        source_root.mkdir()
        result = replay_all_saved_outputs(
            source_output_root=str(source_root), replay_output_root=str(tmp_path / "replays")
        )
        assert result["total_runs_found"] == 0
        assert result["results"] == []
        assert result["status"] == "completed"


@pytest.mark.unit
class TestReplayAllApiRoute:
    def _client(self, tmp_path):
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient

        from comqutor_alpha.api.main import create_app

        source_root = tmp_path / "runs"
        source_root.mkdir()
        app = create_app(output_root=str(source_root), replay_output_root=str(tmp_path / "replays"))
        return TestClient(app), source_root

    def test_post_replay_all_returns_200_with_results(self, tmp_path):
        client, source_root = self._client(tmp_path)
        _write_source_run(source_root, "run-a", ticker="MSFT")
        with client:
            resp = client.post("/api/replay-all")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["total_runs_found"] == 1
        assert body["results"][0]["ticker"] == "MSFT"

    def test_concurrent_duplicate_request_returns_409(self, tmp_path):
        client, source_root = self._client(tmp_path)
        _write_source_run(source_root, "run-a", ticker="MSFT")

        acquired = _REPLAY_ALL_LOCK.acquire(blocking=False)
        assert acquired
        try:
            with client:
                resp = client.post("/api/replay-all")
            assert resp.status_code == 409
            assert resp.json()["error_code"] == "REPLAY_ALL_ALREADY_RUNNING"
        finally:
            _REPLAY_ALL_LOCK.release()

    def test_lock_released_after_completion_allows_next_request(self, tmp_path):
        client, source_root = self._client(tmp_path)
        _write_source_run(source_root, "run-a", ticker="MSFT")
        with client:
            first = client.post("/api/replay-all")
            second = client.post("/api/replay-all")
        assert first.status_code == 200
        assert second.status_code == 200

    def test_lock_released_even_if_batch_raises(self, tmp_path, monkeypatch):
        import comqutor_alpha.api.routes_replay_all as module

        client, source_root = self._client(tmp_path)
        _write_source_run(source_root, "run-a", ticker="MSFT")

        def _boom(**kwargs):
            raise RuntimeError("unexpected failure")

        monkeypatch.setattr(module, "replay_all_saved_outputs", _boom)
        with client, pytest.raises(RuntimeError):
            client.post("/api/replay-all")
        assert not module._REPLAY_ALL_LOCK.locked()

    def test_two_real_concurrent_requests_one_gets_409(self, tmp_path):
        client, source_root = self._client(tmp_path)
        for i in range(3):
            _write_source_run(source_root, f"run-{i}", ticker="MSFT")

        statuses: list[int] = []
        lock = threading.Lock()

        def _fire():
            resp = client.post("/api/replay-all")
            with lock:
                statuses.append(resp.status_code)

        with client:
            threads = [threading.Thread(target=_fire) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

        assert sorted(statuses) == [200, 409]
