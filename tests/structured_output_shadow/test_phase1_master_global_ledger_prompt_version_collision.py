"""Phase 1 Master prompt-size fix: regression test for a real bug found
during the actual v2 resume attempt. ``_append_global_provider_ledger``
dedupes by ``event_id`` alone; when the SAME agent_output_id is legitimately
re-attempted under a different prompt version (the exact v1->v2 retry this
fix performs), an event_id built from agent_output_id alone collides with
the earlier attempt's already-recorded event and the real new attempt is
silently dropped from the append-only global ledger -- undercounting real
Provider spend without raising any error. No Provider calls; in-memory
JSONL file only.
"""

from __future__ import annotations

import importlib
import json

master = importlib.import_module("scripts.run_phase1_master")


def test_same_report_under_two_prompt_versions_both_recorded(tmp_path, monkeypatch):
    ledger_path = tmp_path / "phase1_global_provider_call_ledger.jsonl"
    monkeypatch.setattr(master, "GLOBAL_PROVIDER_LEDGER_PATH", ledger_path)

    agent_output_id = "run-x:fundamental_agent:fundamentals_report"
    v1_event = {
        "schema_version": "comqutor.phase1_global_provider_call_ledger.v1",
        "event_id": f"phase1_master:anthropic:{agent_output_id}:structured_adapter.claim_extraction_shadow.v1",
        "report_id": agent_output_id,
        "prompt_version": "structured_adapter.claim_extraction_shadow.v1",
        "outcome": "timeout",
    }
    v2_event = {
        "schema_version": "comqutor.phase1_global_provider_call_ledger.v1",
        "event_id": f"phase1_master:anthropic:{agent_output_id}:structured_adapter.claim_extraction_shadow.v2",
        "report_id": agent_output_id,
        "prompt_version": "structured_adapter.claim_extraction_shadow.v2",
        "outcome": "provider_error",
    }
    master._append_global_provider_ledger(v1_event)
    master._append_global_provider_ledger(v2_event)

    lines = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 2
    prompt_versions = {entry["prompt_version"] for entry in lines}
    assert prompt_versions == {
        "structured_adapter.claim_extraction_shadow.v1",
        "structured_adapter.claim_extraction_shadow.v2",
    }


def test_true_duplicate_of_the_same_prompt_version_attempt_is_still_deduped(tmp_path, monkeypatch):
    ledger_path = tmp_path / "phase1_global_provider_call_ledger.jsonl"
    monkeypatch.setattr(master, "GLOBAL_PROVIDER_LEDGER_PATH", ledger_path)

    agent_output_id = "run-x:news_agent:news_report"
    event = {
        "schema_version": "comqutor.phase1_global_provider_call_ledger.v1",
        "event_id": f"phase1_master:anthropic:{agent_output_id}:structured_adapter.claim_extraction_shadow.v2",
        "report_id": agent_output_id,
        "prompt_version": "structured_adapter.claim_extraction_shadow.v2",
        "outcome": "success",
    }
    master._append_global_provider_ledger(event)
    master._append_global_provider_ledger(dict(event))  # genuine re-invocation, same identity

    lines = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 1
