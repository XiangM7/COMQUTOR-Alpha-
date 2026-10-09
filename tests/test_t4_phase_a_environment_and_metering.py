"""T4 Phase A (2026-10-08): the instance-identity, run-environment, partial-status and LLM-usage-report additions.

Covers, without any network or PostgreSQL server (DSNs below are parsed, never connected):

* ``COMQUTOR_REQUIRE_DATABASE_DIALECT`` -- a missing URL or a URL of another backend is refused, never the SQLite fallback;
* ``describe_database`` / ``/ready`` identity fields never carry a credential;
* ``build_run_environment`` -- the three execution types, no credential, code identity present;
* the "completed" status additionally requires fault-free Alpha classification (one call failure -> partial);
* ``build_usage_report`` -- one record per HTTP request (ledger attempts, never top-level last-attempt usage), the
  (task, attempt_id) identity across gateways, the audit task-name join, outcome labels, null for unreported token kinds,
  usage-missing requests are "not estimable" (never zero cost), provider correction kept side by side;
* ``estimate_cost_with_cache_split``;
* ``scripts/start_live_comqutor.sh`` keeps a caller's job timeout / port / origin over ``.env`` and defaults to 8000 / 5175.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SECRET = "s3cr3t-pw-should-never-appear"
PG_URL = f"postgresql+psycopg://user:{SECRET}@127.0.0.1:1/comqutor_alpha_t4_unit_test"


# ---------------------------------------------------------------------------
# A. forced PostgreSQL requirement and credential-free description
# ---------------------------------------------------------------------------


def test_required_dialect_refuses_a_missing_url_instead_of_falling_back_to_sqlite(monkeypatch, tmp_path):
    from comqutor_alpha.storage.db.engine import DatabaseConfigurationError, resolve_database_url

    monkeypatch.delenv("COMQUTOR_DATABASE_URL", raising=False)
    monkeypatch.setenv("COMQUTOR_REQUIRE_DATABASE_DIALECT", "postgresql")
    with pytest.raises(DatabaseConfigurationError) as exc:
        resolve_database_url(str(tmp_path))
    assert exc.value.reason_code == "REQUIRED_DATABASE_URL_MISSING"


def test_required_dialect_refuses_a_url_of_another_backend(monkeypatch, tmp_path):
    from comqutor_alpha.storage.db.engine import DatabaseConfigurationError, resolve_database_url

    monkeypatch.setenv("COMQUTOR_DATABASE_URL", f"sqlite:///{tmp_path / 'x.db'}")
    monkeypatch.setenv("COMQUTOR_REQUIRE_DATABASE_DIALECT", "postgresql")
    with pytest.raises(DatabaseConfigurationError) as exc:
        resolve_database_url(str(tmp_path))
    assert exc.value.reason_code == "DATABASE_DIALECT_MISMATCH"


def test_required_dialect_accepts_a_matching_url_and_unset_keeps_the_sqlite_fallback(monkeypatch, tmp_path):
    from comqutor_alpha.storage.db.engine import resolve_database_url

    monkeypatch.setenv("COMQUTOR_DATABASE_URL", PG_URL)
    monkeypatch.setenv("COMQUTOR_REQUIRE_DATABASE_DIALECT", "postgresql")
    assert resolve_database_url(str(tmp_path)) == PG_URL
    monkeypatch.delenv("COMQUTOR_REQUIRE_DATABASE_DIALECT")
    monkeypatch.delenv("COMQUTOR_DATABASE_URL")
    monkeypatch.delenv("COMQUTOR_ENV", raising=False)
    assert resolve_database_url(str(tmp_path)).startswith("sqlite:///")


def test_describe_database_returns_backend_and_name_only():
    from comqutor_alpha.storage.db.engine import describe_database

    described = describe_database(PG_URL)
    assert described == {"dialect": "postgresql", "database": "comqutor_alpha_t4_unit_test"}
    assert SECRET not in json.dumps(described)
    assert describe_database("::not a url::") == {"dialect": None, "database": None}


def _week2_env(monkeypatch, *, profile: str | None):
    monkeypatch.setenv("COMQUTOR_DATABASE_URL", PG_URL)
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "true")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MAX_CALLS", "1800")
    monkeypatch.setenv("DEEPSEEK_API_KEY", SECRET)
    if profile is None:
        monkeypatch.delenv("COMQUTOR_WEEK2_LLM_PROFILE", raising=False)
    else:
        monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROFILE", profile)


def test_ready_identity_fields_show_database_profile_and_code_without_credentials(monkeypatch, tmp_path):
    from comqutor_alpha.api.routes_system import _instance_identity_fields

    _week2_env(monkeypatch, profile="t3_verified_20261008")
    fields = _instance_identity_fields(str(tmp_path))
    assert fields["database_backend"] == {"dialect": "postgresql", "database": "comqutor_alpha_t4_unit_test", "reason": None}
    assert fields["week2_semantic"]["execution_profile"] == "t3_verified_20261008"
    assert fields["week2_semantic"]["max_calls"] == 1800
    assert fields["week2_semantic"]["request_response_audit"] is True
    assert fields["code_identity"]["status"] in {"known", "unknown"}
    assert SECRET not in json.dumps(fields)


def test_ready_identity_fields_report_an_unknown_profile_instead_of_failing(monkeypatch, tmp_path):
    from comqutor_alpha.api.routes_system import _instance_identity_fields

    _week2_env(monkeypatch, profile="no_such_profile")
    fields = _instance_identity_fields(str(tmp_path))
    assert fields["week2_semantic"]["execution_profile"] is None
    assert fields["week2_semantic"]["profile_error"] == "WEEK2_LLM_PROFILE_UNKNOWN"


# ---------------------------------------------------------------------------
# run environment block
# ---------------------------------------------------------------------------


def test_run_environment_records_type_database_code_and_effective_config_without_credentials(monkeypatch, tmp_path):
    from comqutor_alpha import run_environment as env

    _week2_env(monkeypatch, profile="t3_verified_20261008")
    monkeypatch.setenv("COMQUTOR_RESEARCH_AGENT_MAX_ACTUAL_REQUESTS", "100")
    monkeypatch.setenv("COMQUTOR_RESEARCH_AGENT_MAX_RETRIES", "0")
    block = env.build_run_environment(env.EXECUTION_TYPE_FRESH_RUN, str(tmp_path))
    assert block["schema_version"] == env.SCHEMA_VERSION
    assert block["execution_type"] == "fresh_run"
    assert block["database"] == {"status": "known", "dialect": "postgresql", "database": "comqutor_alpha_t4_unit_test"}
    assert block["code_identity"]["status"] in {"known", "unknown"}
    week2 = block["effective_config"]["week2_semantic"]
    assert week2["execution_profile"] == "t3_verified_20261008"
    assert week2["tasks"]["content_support_verification"]["client_read_timeout_seconds"] == 120.0
    assert week2["tasks"]["content_support_verification"]["batch_size"] == 1
    assert week2["tasks"]["alpha_classifier"]["concurrency"] == 4
    assert block["effective_config"]["research_agents"]["max_actual_requests"] == "100"
    assert SECRET not in json.dumps(block, default=str)


def test_run_environment_rejects_an_unknown_execution_type_and_the_wrapper_never_raises(monkeypatch, tmp_path):
    from comqutor_alpha import run_environment as env

    with pytest.raises(ValueError):
        env.build_run_environment("something_else", str(tmp_path))
    assert env.EXECUTION_TYPES == {"fresh_run", "frozen_input_recompute", "old_result_reevaluation"}
    recorded = env.run_environment_or_unavailable("something_else", str(tmp_path))
    assert recorded["status"] == "unavailable" and recorded["reason"] == "ValueError"


def test_run_environment_database_is_unavailable_not_guessed_when_the_requirement_fails(monkeypatch, tmp_path):
    from comqutor_alpha.run_environment import database_backend

    monkeypatch.delenv("COMQUTOR_DATABASE_URL", raising=False)
    monkeypatch.setenv("COMQUTOR_REQUIRE_DATABASE_DIALECT", "postgresql")
    assert database_backend(str(tmp_path)) == {"status": "unavailable", "reason": "REQUIRED_DATABASE_URL_MISSING", "dialect": None,
                                               "database": None}


# ---------------------------------------------------------------------------
# "completed" requires fault-free Alpha classification
# ---------------------------------------------------------------------------


def _alpha_match(method, fallback, matched_alpha=None):
    return {"claim_id": f"c:{method}:{fallback}:{matched_alpha}", "alpha_match_method": method,
            "alpha_match_fallback_reason": fallback, "matched_alpha": matched_alpha}


def _status_for(tmp_path, monkeypatch, matches):
    from comqutor_alpha.api import routes_research as rr

    run_id = "t4-status-run"
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(json.dumps({"run_id": run_id, "ticker": "NVDA"}))
    for name in ("raw_agent_outputs", "structured_agent_outputs", "extracted_structures"):
        (run_dir / f"{name}.json").write_text("{}")
    (run_dir / "alpha_matches.json").write_text(json.dumps({"matches": matches}))
    (run_dir / "structure_graph.json").write_text("{}")
    (run_dir / "week3_pipeline_status.json").write_text(json.dumps({"outcome": "success"}))
    (run_dir / "run_audit.json").write_text(json.dumps({"ticker_consistency": "pass"}))
    (run_dir / "artifact_manifest.json").write_text(json.dumps({"artifact_completeness": "pass"}))
    monkeypatch.setattr(rr, "_load_week4_response_fields", lambda *a, **k: ([], None, "ready", False, True))
    return rr.build_research_response(run_id, output_root=str(tmp_path))["status"]


def test_completed_when_every_gate_passes_and_classification_has_no_fault(tmp_path, monkeypatch):
    assert _status_for(tmp_path, monkeypatch, [_alpha_match("llm", None, None), _alpha_match("llm", None, "A304")]) == "completed"


def test_one_alpha_call_failure_makes_an_otherwise_complete_run_partial(tmp_path, monkeypatch):
    matches = [_alpha_match("llm", None, "A304"), _alpha_match("llm_unavailable", "provider_error")]
    assert _status_for(tmp_path, monkeypatch, matches) == "partial"


def test_a_deliberately_disabled_classifier_is_not_a_fault(tmp_path, monkeypatch):
    assert _status_for(tmp_path, monkeypatch, [_alpha_match("llm_unavailable", "disabled")]) == "completed"


# ---------------------------------------------------------------------------
# LLM usage report
# ---------------------------------------------------------------------------


def _usage(prompt, completion, hit=None, miss=None):
    out = {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}
    if hit is not None:
        out.update({"prompt_cache_hit_tokens": hit, "prompt_cache_miss_tokens": miss})
    return out


def _attempt(attempt_id, number, status, usage=None, error_code=None):
    return {"attempt_id": attempt_id, "attempt_number": number, "provider_status": status, "raw_usage": usage, "error_code": error_code}


def _ledger_record(task, call_id, attempts, *, status=None, cache_hit=False, error_code=None):
    last = attempts[-1] if attempts else {}
    return {"run_id": "r1", "task": task, "call_id": call_id, "provider": "openai", "model": "deepseek-v4-flash",
            "provider_status": status or last.get("provider_status"), "error_code": error_code,
            "token_usage": {"prompt_tokens": 1} if last.get("raw_usage") else None, "cache": {"hit": cache_hit},
            "request_attempts": attempts, "provider_response": {}}


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


@pytest.fixture
def usage_report(tmp_path):
    from comqutor_alpha.llm.run_usage_report import UsageSources, build_usage_report

    ledger = tmp_path / "llm_semantic_calls.jsonl"
    _write_jsonl(ledger, [
        # a retried call: two requests, top-level usage repeats only the last
        _ledger_record("alpha_classifier", "a1", [_attempt("att-1", 1, "timeout"), _attempt("att-2", 2, "success", _usage(1000, 100, 600, 400))]),
        # the same attempt id in another task's gateway is a different request
        _ledger_record("content_support_verification", "c1", [_attempt("att-1", 1, "success", _usage(2000, 300))]),
        # a transport error after send: outcome unknown, usage missing, cost not estimable
        _ledger_record("evidence_stance_classifier", "s1", [_attempt("att-9", 1, "provider_error", None, "WEEK2_LLM_TRANSPORT_ERROR")]),
        # refused before sending and a cache hit: logical calls with no request
        _ledger_record("alpha_classifier", "a2", [], status="budget_exhausted", error_code="WEEK2_LLM_BUDGET_EXHAUSTED"),
        _ledger_record("alpha_classifier", "a3", [], status="success", cache_hit=True),
    ])
    audit = tmp_path / "error_logs"
    _write_jsonl(audit / "week2_llm_provider_request_audit.jsonl", [
        {"task": "alpha_classifier", "attempt_id": "att-2", "created_at": "t0", "body": json.dumps({"model": "deepseek-v4-flash"})},
        # the adapter's gateway task name maps to the ledger's semantic task; this one has no ledger attempt -> counted once
        {"task": "claim_batch_enrichment", "attempt_id": "att-1", "created_at": "t1", "execution_id": "r1",
         "body": json.dumps({"model": "deepseek-v4-flash"})},
    ])
    _write_jsonl(audit / "week2_llm_provider_response_audit.jsonl", [
        {"task": "alpha_classifier", "attempt_id": "att-2", "status_code": 200, "created_at": "t0b",
         "body": json.dumps({"id": "req-xyz", "model": "deepseek-v4-flash", "usage": _usage(1000, 100, 600, 400)})},
        {"task": "claim_batch_enrichment", "attempt_id": "att-1", "status_code": 200, "created_at": "t1b",
         "body": json.dumps({"id": "req-adp", "model": "deepseek-v4-flash", "usage": _usage(5000, 800)})},
    ])
    agents = tmp_path / "tradingagents_llm_calls.jsonl"
    _write_jsonl(agents, [
        {"run_id": "r1", "agent_label": "news_analyst", "provider": "openai", "model": "deepseek-v4-flash", "success": True,
         "retry_count": 0, "provider_call_id": "p1", "token_usage": {"input_tokens": 3000, "output_tokens": 500}},
        {"run_id": "r1", "agent_label": "market_analyst", "provider": "openai", "model": "deepseek-v4-flash", "success": False,
         "error_type": "ReadTimeout", "retry_count": 0, "provider_call_id": "p2", "token_usage": None},
    ])
    return build_usage_report(UsageSources(run_id="r1", agent_calls=agents, semantic_ledgers=[ledger], audit_dirs=[audit]))


def test_usage_report_counts_one_record_per_http_request(usage_report):
    week2 = usage_report["totals"]["week2_semantic"]
    assert week2["logical_calls"] == 5
    assert week2["budget_reservations"] == 5  # att-1/att-2 alpha, att-1 content support, att-9 stance, att-1 adapter (audit only)
    assert week2["retries"] == 1
    assert week2["served_from_cache"] == 1
    assert week2["not_sent"] == 1 and week2["not_sent_reasons"] == {"WEEK2_LLM_BUDGET_EXHAUSTED": 1}
    assert usage_report["deduplication"]["audit_only_requests"] == 1
    assert usage_report["deduplication"]["ledger_records_where_top_level_usage_is_last_attempt_only"] == 1


def test_usage_report_keys_attempts_by_task_and_joins_the_adapter_task_name(usage_report):
    keys = sorted((r["step"], r["attempt_id"]) for r in usage_report["requests"] if r["layer"] == "week2_semantic")
    assert keys == [("alpha_classifier", "att-1"), ("alpha_classifier", "att-2"), ("content_support_verification", "att-1"),
                    ("evidence_stance_classifier", "att-9"), ("structured_adapter", "att-1")]
    retried = next(r for r in usage_report["requests"] if r["attempt_id"] == "att-2")
    assert retried["provider_request_id"] == "req-xyz" and retried["model_returned"] == "deepseek-v4-flash" and retried["is_retry"]


def test_usage_report_outcomes_and_missing_usage_is_never_zero_cost(usage_report):
    week2 = usage_report["totals"]["week2_semantic"]
    assert week2["outcomes"] == {"success": 3, "failure": 0, "timeout": 1, "unknown": 1}
    assert week2["requests_missing_usage"] == 2
    assert week2["cost_estimate_usd"]["requests_not_estimable"] == 2
    unknown = next(r for r in usage_report["requests"] if r["attempt_id"] == "att-9")
    assert unknown["outcome"] == "unknown" and unknown["tokens"]["input"] is None
    assert unknown["cost"] == {"status": "not_estimable", "reason": "usage_missing", "usd_off_peak_floor": None, "usd_peak_ceiling": None}


def test_usage_report_uses_null_for_a_token_kind_no_request_reported(usage_report):
    agents = usage_report["totals"]["research_agent"]
    assert agents["tokens_known"]["input"] == 3000
    assert agents["tokens_known"]["cache_hit"] is None
    assert agents["outcomes"]["timeout"] == 1 and agents["requests_missing_usage"] == 1


def test_usage_report_keeps_the_reported_client_provider_beside_the_resolved_one(usage_report):
    assert all(r["provider_reported"] in ("openai", None) for r in usage_report["requests"])
    assert all(r["provider_resolved"] == "deepseek" for r in usage_report["requests"])
    (correction,) = usage_report["corrections"]
    assert correction["reported"] == "openai" and correction["resolved"] == "deepseek"
    assert correction["requests"] == 6  # every request with a reported provider (the audit-only row has none)


def test_write_run_usage_report_reads_only_the_run_directory_and_writes_one_file(tmp_path):
    from comqutor_alpha.llm.run_usage_report import REPORT_FILENAME, write_run_usage_report

    run_dir = tmp_path / "run-x"
    _write_jsonl(run_dir / "llm_semantic_calls.jsonl",
                 [_ledger_record("alpha_classifier", "a1", [_attempt("att-1", 1, "success", _usage(100, 10))])])
    before = {p.name: p.read_bytes() for p in run_dir.iterdir()}
    report = write_run_usage_report(run_dir)
    assert report["run_id"] == "run-x"
    assert sorted(p.name for p in run_dir.iterdir()) == sorted([*before, REPORT_FILENAME])
    assert all((run_dir / name).read_bytes() == data for name, data in before.items())


# ---------------------------------------------------------------------------
# cost with cache split
# ---------------------------------------------------------------------------


def test_cost_split_prices_cache_hits_at_the_cache_rate_and_the_openai_label_still_resolves():
    from comqutor_alpha.llm.cost_basis import estimate_cost_with_cache_split

    split = estimate_cost_with_cache_split("openai", "deepseek-v4-flash", cache_miss_input_tokens=400_000, cache_hit_input_tokens=600_000,
                                           output_tokens=100_000)
    unsplit = estimate_cost_with_cache_split("openai", "deepseek-v4-flash", cache_miss_input_tokens=1_000_000, cache_hit_input_tokens=None,
                                             output_tokens=100_000)
    assert split.usd == pytest.approx(0.4 * 0.15 + 0.6 * 0.003 + 0.1 * 0.60)
    assert split.usd_ceiling == pytest.approx(0.4 * 0.30 + 0.6 * 0.006 + 0.1 * 1.20)
    assert unsplit.usd == pytest.approx(0.15 + 0.06)
    assert split.usd < unsplit.usd


def test_cost_split_never_prices_without_tokens_or_an_unknown_model():
    from comqutor_alpha.llm.cost_basis import estimate_cost_with_cache_split

    assert estimate_cost_with_cache_split("deepseek", "deepseek-v4-flash", cache_miss_input_tokens=None, cache_hit_input_tokens=None,
                                          output_tokens=10).usd is None
    assert estimate_cost_with_cache_split("x", "unknown-model", cache_miss_input_tokens=1, cache_hit_input_tokens=None,
                                          output_tokens=1).usd is None


# ---------------------------------------------------------------------------
# live launcher: caller overrides and defaults (env resolution only; stops before the port check and the preflight)
# ---------------------------------------------------------------------------

REAL_SCRIPT = REPO_ROOT / "scripts" / "start_live_comqutor.sh"
STEP6_MARKER = "# --- 6. refuse to start if the port is already occupied"


def _run_launcher_env_resolution(tmp_path: Path, extra_env: dict[str, str], env_file_lines: list[str]) -> dict[str, str]:
    fake_env = tmp_path / "fake.env"
    fake_env.write_text("\n".join(env_file_lines) + "\n")
    capture = tmp_path / "captured.txt"
    content = REAL_SCRIPT.read_text()
    assert content.count('"$REPO_ROOT/.env"') == 2 and content.count(STEP6_MARKER) == 1
    patched = content.replace('"$REPO_ROOT/.env"', f'"{fake_env}"')
    capture_cmd = (f'echo "PORT=$COMQUTOR_API_PORT" > "{capture}"; echo "CORS=$COMQUTOR_CORS_ORIGINS" >> "{capture}"; '
                   f'echo "JOB_TIMEOUT=${{COMQUTOR_JOB_TIMEOUT_SECONDS:-}}" >> "{capture}"; '
                   f'echo "RETRIES=${{COMQUTOR_WEEK2_LLM_MAX_RETRIES:-}}" >> "{capture}"; exit 0')
    patched = patched.replace(STEP6_MARKER, capture_cmd + "\n" + STEP6_MARKER)
    patched_path = REAL_SCRIPT.parent / "._test_t4_start_live_comqutor_env_resolution.sh"
    patched_path.write_text(patched)
    try:
        env = {k: v for k, v in os.environ.items()
               if k not in {"COMQUTOR_LIVE_API_PORT", "COMQUTOR_LIVE_FRONTEND_ORIGIN", "COMQUTOR_JOB_TIMEOUT_SECONDS",
                            "COMQUTOR_WEEK2_LLM_MAX_RETRIES", "COMQUTOR_API_PORT", "COMQUTOR_CORS_ORIGINS"}}
        env.update(extra_env)
        result = subprocess.run(["bash", str(patched_path)], env=env, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
        return dict(re.match(r"(\w+)=(.*)", line).groups() for line in capture.read_text().splitlines())
    finally:
        patched_path.unlink(missing_ok=True)


@pytest.mark.skipif(not (REPO_ROOT / ".venv" / "bin" / "activate").exists(), reason="requires the real project venv")
def test_launcher_defaults_to_the_permanent_port_and_origin_and_takes_env_values(tmp_path):
    captured = _run_launcher_env_resolution(tmp_path, {}, ["COMQUTOR_JOB_TIMEOUT_SECONDS=7200", "COMQUTOR_WEEK2_LLM_MAX_RETRIES=1"])
    assert captured == {"PORT": "8000", "CORS": "http://127.0.0.1:5175", "JOB_TIMEOUT": "7200", "RETRIES": "1"}


@pytest.mark.skipif(not (REPO_ROOT / ".venv" / "bin" / "activate").exists(), reason="requires the real project venv")
def test_launcher_keeps_a_callers_job_timeout_port_and_origin_over_env(tmp_path):
    captured = _run_launcher_env_resolution(
        tmp_path,
        {"COMQUTOR_LIVE_API_PORT": "8002", "COMQUTOR_LIVE_FRONTEND_ORIGIN": "http://127.0.0.1:5177",
         "COMQUTOR_JOB_TIMEOUT_SECONDS": "14400", "COMQUTOR_WEEK2_LLM_MAX_RETRIES": "0"},
        ["COMQUTOR_JOB_TIMEOUT_SECONDS=7200", "COMQUTOR_WEEK2_LLM_MAX_RETRIES=1"],
    )
    assert captured == {"PORT": "8002", "CORS": "http://127.0.0.1:5177", "JOB_TIMEOUT": "14400", "RETRIES": "0"}


def test_a_legacy_record_without_classification_method_is_not_a_fault(tmp_path, monkeypatch):
    # deterministic-era schema: no alpha_match_method at all -- no classification request was ever made
    assert _status_for(tmp_path, monkeypatch, [{"claim_id": "c1", "match_status": "no_match", "score": 0.0}]) == "completed"


def test_a_real_failure_next_to_legacy_records_still_makes_the_run_partial(tmp_path, monkeypatch):
    matches = [{"claim_id": "c1", "match_status": "no_match"}, _alpha_match("llm_unavailable", "provider_timeout")]
    assert _status_for(tmp_path, monkeypatch, matches) == "partial"
