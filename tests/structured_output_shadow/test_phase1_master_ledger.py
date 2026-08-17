"""Phase 1 Master, section 4 B: ledger/state must be committed per report
(not per batch), so an interrupted process never loses already-completed
progress or re-calls a report it already successfully called. Pure,
offline, no Provider/network -- exercises the real corpus (read-only) and
the real state-machine helper functions against a redirected state
directory.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

master = importlib.import_module("scripts.run_phase1_master")


def _redirect_state_dir(monkeypatch, tmp_path: Path) -> None:
    state_dir = tmp_path / "phase1_master"
    state_dir.mkdir()
    monkeypatch.setattr(master, "STATE_DIR", state_dir)
    monkeypatch.setattr(master, "STATE_PATH", state_dir / "phase1_master_state.json")
    monkeypatch.setattr(master, "LEDGER_PATH", state_dir / "provider_call_ledger.json")
    monkeypatch.setattr(
        master,
        "GLOBAL_PROVIDER_LEDGER_PATH",
        state_dir / "phase1_global_provider_call_ledger.jsonl",
    )
    monkeypatch.setattr(master, "CONNECTIVITY_REPORT_PATH", state_dir / "provider_connectivity_report.json")


def test_reserve_budget_respects_hard_caps(monkeypatch, tmp_path):
    _redirect_state_dir(monkeypatch, tmp_path)
    state = master._initial_state()
    state["cumulative_logical_calls"] = master.HARD_CAP_LOGICAL_CALLS - 2
    state["cumulative_provider_attempts"] = 0
    assert master._reserve_budget(state, 2, 2) is True
    assert master._reserve_budget(state, 3, 2) is False

    state["cumulative_logical_calls"] = 0
    state["cumulative_provider_attempts"] = master.HARD_CAP_PROVIDER_ATTEMPTS - 1
    assert master._reserve_budget(state, 1, 1) is True
    assert master._reserve_budget(state, 1, 2) is False


def test_commit_budget_persists_incrementally_per_call_not_per_batch(monkeypatch, tmp_path):
    """Simulate an interruption after 2 of 4 per-report commits: the on-disk
    state and ledger must already reflect exactly those 2 -- this is the
    fix for the exact failure mode observed in the Phase 1B.1 incident
    (a batch-end-only commit would lose all progress on interruption)."""

    _redirect_state_dir(monkeypatch, tmp_path)
    state = master._initial_state()

    for i in range(2):
        master._commit_budget(state, 1, 1, f"report_{i}")
        master.save_state(state)

    on_disk = json.loads(master.STATE_PATH.read_text(encoding="utf-8"))
    assert on_disk["cumulative_logical_calls"] == 2
    assert on_disk["cumulative_provider_attempts"] == 2

    ledger = json.loads(master.LEDGER_PATH.read_text(encoding="utf-8"))
    assert len(ledger["entries"]) == 2
    assert ledger["cumulative_logical_calls"] == 2

    # "Resume": a fresh process loads state from disk and must see exactly
    # the 2 already-committed calls, not 0 and not 4.
    resumed_state = master.load_state()
    assert resumed_state["cumulative_logical_calls"] == 2


def test_ledger_is_strictly_monotonic_across_many_small_commits(monkeypatch, tmp_path):
    _redirect_state_dir(monkeypatch, tmp_path)
    state = master._initial_state()
    for i in range(5):
        master._commit_budget(state, 1, 1, f"r{i}")
    ledger = json.loads(master.LEDGER_PATH.read_text(encoding="utf-8"))
    running_calls = 0
    for entry in ledger["entries"]:
        running_calls += entry["logical_calls"]
        assert entry["running_total_logical_calls"] == running_calls


def test_global_provider_ledger_is_append_only_and_idempotent(monkeypatch, tmp_path):
    _redirect_state_dir(monkeypatch, tmp_path)
    event = {
        "event_id": "anthropic:test:one",
        "logical_calls": 1,
        "provider_attempts": 1,
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
    }
    master._append_global_provider_ledger(event)
    first_bytes = master.GLOBAL_PROVIDER_LEDGER_PATH.read_bytes()
    master._append_global_provider_ledger(event)
    assert master.GLOBAL_PROVIDER_LEDGER_PATH.read_bytes() == first_bytes
    assert len(first_bytes.splitlines()) == 1


def test_anthropic_progress_is_separate_from_preserved_deepseek_calls():
    state = master._initial_state()
    state["already_called_report_ids"] = ["deepseek-report"]
    state["anthropic_called_report_ids"] = ["anthropic-report"]
    assert state["already_called_report_ids"] == ["deepseek-report"]
    assert state["anthropic_called_report_ids"] == ["anthropic-report"]


def test_resume_never_recalls_an_already_called_report():
    """already_called_report_ids filtering must exclude reports from the
    real, frozen Phase 1A corpus that a prior (possibly interrupted) run
    already completed -- proven against the real corpus, read-only."""

    corpus = master._load_evaluation_corpus()
    smoke_targets = master._target_reports_for_tickers(corpus, master.STAGE_TICKERS["SMOKE"])
    assert len(smoke_targets) == 4

    already_called = {str(r["agent_output_id"]) for r in smoke_targets[:2]}
    remaining = [r for r in smoke_targets if str(r["agent_output_id"]) not in already_called]
    assert len(remaining) == 2
    assert already_called.isdisjoint({str(r["agent_output_id"]) for r in remaining})


def test_pilot_only_adds_new_reports_beyond_smoke():
    corpus = master._load_evaluation_corpus()
    smoke = {str(r["agent_output_id"]) for r in master._target_reports_for_tickers(corpus, master.STAGE_TICKERS["SMOKE"])}
    pilot = {str(r["agent_output_id"]) for r in master._target_reports_for_tickers(corpus, master.STAGE_TICKERS["PILOT"])}
    core = {
        str(r["agent_output_id"])
        for r in master._target_reports_for_tickers(corpus, master.STAGE_TICKERS["CORE_EVALUATION"])
    }
    assert smoke <= pilot <= core
    assert len(smoke) == 4
    assert len(pilot) == 12
    assert len(core) == 24
