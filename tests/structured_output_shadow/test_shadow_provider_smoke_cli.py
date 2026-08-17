"""Phase 1B.1: scripts/run_phase1b1_provider_smoke.py CLI, offline only.

No test in this file ever sets COMQUTOR_PHASE1B1_PROVIDER_SMOKE_APPROVED to
"true" combined with a real Provider path -- authorized-path tests patch
``create_llm_client`` to a FakeModel, never touching a real network.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

cli = importlib.import_module("scripts.run_phase1b1_provider_smoke")


@pytest.fixture(autouse=True)
def _clean_approval_env(monkeypatch):
    monkeypatch.delenv(cli.APPROVAL_ENV_VAR, raising=False)


def test_selection_is_deterministic_across_repeated_calls():
    corpus = cli._load_evaluation_corpus()
    first = cli.select_four_reports(corpus)
    second = cli.select_four_reports(corpus)
    assert first["ticker"] == second["ticker"]
    assert {k: v["agent_output_id"] for k, v in first["selected_reports"].items()} == {
        k: v["agent_output_id"] for k, v in second["selected_reports"].items()
    }


def test_selection_covers_all_four_target_families():
    corpus = cli._load_evaluation_corpus()
    selection = cli.select_four_reports(corpus)
    assert set(selection["selected_reports"].keys()) == set(cli.TARGET_FAMILY_ORDER)


def test_selection_prefers_nvda_when_fully_covered():
    corpus = cli._load_evaluation_corpus()
    selection = cli.select_four_reports(corpus)
    assert selection["ticker"] == "NVDA"  # first in target_tickers order per the real corpus


def test_max_provider_calls_above_four_fails_before_any_call(tmp_path, capsys):
    exit_code = cli.main(
        [
            "--research-profile",
            "comqutor_deepseek_default_v1",
            "--max-provider-calls",
            "5",
            "--output-dir",
            str(tmp_path / "out"),
            "--execute-provider-smoke",
        ]
    )
    assert exit_code == 1
    assert cli.FAIL_PROVIDER_CALL_LIMIT_EXCEEDED in capsys.readouterr().out


def test_invalid_research_profile_is_blocked(tmp_path, capsys):
    output_dir = REPO_ROOT / "outputs/evaluations" / f"test-invalid-profile-{tmp_path.name}"
    try:
        exit_code = cli.main(
            [
                "--research-profile",
                "not_a_real_profile",
                "--max-provider-calls",
                "4",
                "--output-dir",
                str(output_dir.relative_to(REPO_ROOT)),
                "--execute-provider-smoke",
            ]
        )
        assert exit_code == 1
        assert cli.BLOCKED_RESEARCH_PROFILE_INVALID in capsys.readouterr().out
    finally:
        import shutil

        shutil.rmtree(output_dir, ignore_errors=True)


def test_output_dir_outside_allowed_root_is_blocked(capsys):
    exit_code = cli.main(
        [
            "--research-profile",
            "comqutor_deepseek_default_v1",
            "--max-provider-calls",
            "4",
            "--output-dir",
            "outputs/runs/escape-attempt",
            "--execute-provider-smoke",
        ]
    )
    assert exit_code == 1
    assert cli.BLOCKED_OUTPUT_DIRECTORY_INVALID in capsys.readouterr().out
    assert not (REPO_ROOT / "outputs/runs/escape-attempt").exists()


def test_output_dir_traversal_is_blocked(capsys):
    exit_code = cli.main(
        [
            "--research-profile",
            "comqutor_deepseek_default_v1",
            "--max-provider-calls",
            "4",
            "--output-dir",
            "outputs/evaluations/../../etc",
            "--execute-provider-smoke",
        ]
    )
    assert exit_code == 1
    assert cli.BLOCKED_OUTPUT_DIRECTORY_INVALID in capsys.readouterr().out


def test_no_authorization_blocks_with_zero_provider_calls(tmp_path, capsys, monkeypatch):
    output_dir = REPO_ROOT / "outputs/evaluations" / f"test-noauth-{tmp_path.name}"

    def _boom(**_kwargs):
        raise AssertionError("create_llm_client must never be called without authorization")

    monkeypatch.setattr("tradingagents.llm_clients.create_llm_client", _boom)
    try:
        exit_code = cli.main(
            [
                "--research-profile",
                "comqutor_deepseek_default_v1",
                "--max-provider-calls",
                "4",
                "--output-dir",
                str(output_dir.relative_to(REPO_ROOT)),
                # note: --execute-provider-smoke intentionally omitted
            ]
        )
        assert exit_code == 0
        out = capsys.readouterr().out
        assert cli.BLOCKED_PROVIDER_SMOKE_NOT_AUTHORIZED in out
        result = json.loads((output_dir / "real_provider_smoke_result.json").read_text())
        assert result["provider_calls_made"] == 0
        assert result["status"] == cli.BLOCKED_PROVIDER_SMOKE_NOT_AUTHORIZED
    finally:
        import shutil

        shutil.rmtree(output_dir, ignore_errors=True)


def test_execute_flag_without_env_var_still_blocks(tmp_path, capsys, monkeypatch):
    output_dir = REPO_ROOT / "outputs/evaluations" / f"test-flag-only-{tmp_path.name}"

    def _boom(**_kwargs):
        raise AssertionError("create_llm_client must never be called")

    monkeypatch.setattr("tradingagents.llm_clients.create_llm_client", _boom)
    monkeypatch.delenv(cli.APPROVAL_ENV_VAR, raising=False)
    try:
        exit_code = cli.main(
            [
                "--research-profile",
                "comqutor_deepseek_default_v1",
                "--max-provider-calls",
                "4",
                "--output-dir",
                str(output_dir.relative_to(REPO_ROOT)),
                "--execute-provider-smoke",
            ]
        )
        assert exit_code == 0
        assert cli.BLOCKED_PROVIDER_SMOKE_NOT_AUTHORIZED in capsys.readouterr().out
    finally:
        import shutil

        shutil.rmtree(output_dir, ignore_errors=True)


class _FakeAuthorizedModel:
    def __init__(self):
        self.calls = 0

    def invoke(self, prompt):
        self.calls += 1
        # Echo back a genuinely valid, empty Shadow bundle by reusing the
        # exact identity fields embedded in the dynamic request JSON (after
        # the frozen prompt's SHADOW_REQUEST_JSON: marker) -- this proves
        # the fake exercises real request/response wiring, not a canned
        # response independent of what was actually asked.
        request = json.loads(prompt.split("SHADOW_REQUEST_JSON:\n", 1)[1])
        payload = {
            "schema_version": request["output_schema_version"],
            "run_id": request["run_id"],
            "ticker": request["ticker"],
            "agent": request["agent"],
            "agent_output_id": request["agent_output_id"],
            "source_report_sha256": request["source_report_sha256"],
            "prompt_version": request["prompt_version"],
            "prompt_sha256": request["prompt_sha256"],
            "claims": [],
            "abstentions": [],
            "validation_summary": {},
            "shadow_only": True,
            "production_authority": False,
        }
        return SimpleNamespace(content=json.dumps(payload))


def test_fully_authorized_run_with_fake_client_writes_complete_bundle(tmp_path, monkeypatch):
    monkeypatch.setenv(cli.APPROVAL_ENV_VAR, "true")
    fake_model = _FakeAuthorizedModel()
    monkeypatch.setattr(
        "tradingagents.llm_clients.create_llm_client",
        lambda **_kwargs: SimpleNamespace(get_llm=lambda: fake_model),
    )
    output_dir = REPO_ROOT / "outputs/evaluations" / f"test-authorized-{tmp_path.name}"
    try:
        exit_code = cli.main(
            [
                "--research-profile",
                "comqutor_deepseek_default_v1",
                "--max-provider-calls",
                "4",
                "--output-dir",
                str(output_dir.relative_to(REPO_ROOT)),
                "--execute-provider-smoke",
            ]
        )
        assert exit_code == 0
        assert fake_model.calls == 4  # exactly 4 logical calls, one per family
        assert (output_dir / "llm_semantic_calls.jsonl").exists()
        assert (output_dir / "llm_semantic_manifest.json").exists()
        assert (output_dir / "phase1b1_shadow_review.csv").exists()
        assert (output_dir / "shadow_exact_replay_audit.json").exists()
        replay_audit = json.loads((output_dir / "shadow_exact_replay_audit.json").read_text())
        assert replay_audit["final_status"] == "PASS", replay_audit["reason_codes"]
        for family in ("fundamental", "news", "sentiment", "technical"):
            assert (output_dir / "reports" / family / "shadow_bundle.json").exists()
        result = json.loads((output_dir / "real_provider_smoke_result.json").read_text())
        assert result["status"] == "COMPLETED"
        assert result["provider_calls_made"] == 4
        # No staging directory left behind after successful atomic promotion.
        assert not any(p.name.startswith(".") for p in output_dir.parent.iterdir())
    finally:
        import shutil

        shutil.rmtree(output_dir, ignore_errors=True)
