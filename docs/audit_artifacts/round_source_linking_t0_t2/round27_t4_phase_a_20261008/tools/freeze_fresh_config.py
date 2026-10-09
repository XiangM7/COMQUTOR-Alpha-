#!/usr/bin/env python3
"""T4 Phase A: freeze the configuration of the RUNNING NVDA Fresh Run instance (zero provider requests; loopback /ready only).

Reads what the instance itself reports and runs on -- never what a launcher merely intended:

* ``GET http://127.0.0.1:8002/ready`` -- database backend/name, Week 2 profile, real-execution and live-semantic readiness,
  the code identity the process computed when it started;
* the instance process's own environment (``ps eww <pid>``), filtered to an allowlist of non-secret keys; credentials are
  recorded as present/absent only and the database URL as backend + name only;
* the per-task Week 2 configuration resolved by the production resolver (``describe_server_week2_effective_config``) in a
  subprocess given exactly that allowlisted environment;
* a code snapshot -- ``git diff HEAD --binary`` and the untracked runtime source files -- whose sha256 values must equal the
  process's code identity, else the freeze is REFUSED (the code changed after the instance started);
* Week 2 prompt identities (``Week2LLMGateway.prompt_identity_sha256``) compared with the T3-verified pins;
* the request caps / stop rules of 04_fresh_prep/budget.json, which the process environment must match.

    python freeze_fresh_config.py --pid <8002 pid> --out-dir 04_fresh_prep
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
T4 = HERE.parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
sys.path.insert(0, str(REPO))

READY_URL = "http://127.0.0.1:8002/ready"
EXPECTED = {"database": "comqutor_alpha_t4_test", "dialect": "postgresql", "week2_profile": "t3_verified_20261008", "port": "8002",
            "cors": "http://127.0.0.1:5177"}
T3_PROMPT_PINS = {  # round25_t3_minimal_prep_20261008/01_config_comparison.md; the T3 execution's signed plan
    "content_support_verification": "6abae47b6a6a52966f74f3bf9a3189f6898e21764a8a92f3d18779d9943a1f06",
    "alpha_classifier": "ac48723f",
    "evidence_stance_classifier": "d9455fd5ff33",
}
ENV_ALLOWLIST = (
    "COMQUTOR_API_HOST", "COMQUTOR_API_PORT", "COMQUTOR_CORS_ORIGINS", "COMQUTOR_OUTPUT_DIR",
    "COMQUTOR_REQUIRE_DATABASE_NAME", "COMQUTOR_REQUIRE_DATABASE_DIALECT", "COMQUTOR_ENV",
    "COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "COMQUTOR_REAL_FORCE_REFRESH_ENABLED", "COMQUTOR_DATA_SANITY_ENABLED",
    "COMQUTOR_JOB_TIMEOUT_SECONDS", "COMQUTOR_JOB_MAX_WORKERS",
    "COMQUTOR_RESEARCH_AGENT_MAX_ACTUAL_REQUESTS", "COMQUTOR_RESEARCH_AGENT_MAX_RETRIES",
    "COMQUTOR_WEEK2_LLM_ENABLED", "COMQUTOR_WEEK2_LLM_PROFILE", "COMQUTOR_WEEK2_LLM_PROVIDER", "COMQUTOR_WEEK2_LLM_MODEL",
    "COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS", "COMQUTOR_WEEK2_LLM_MAX_RETRIES", "COMQUTOR_WEEK2_LLM_MAX_CALLS",
    "COMQUTOR_WEEK2_LLM_ENABLE_REQUEST_AUDIT", "COMQUTOR_WEEK2_CONTENT_SUPPORT_BATCH_SIZE", "COMQUTOR_WEEK2_CONTENT_SUPPORT_MAX_TOKENS",
    "COMQUTOR_WEEK2_ALPHA_CLASSIFIER_MAX_TOKENS", "COMQUTOR_WEEK2_LLM_CONCURRENCY", "COMQUTOR_WEEK2_STANCE_CONCURRENCY",
    "TRADINGAGENTS_LLM_PROVIDER", "TRADINGAGENTS_QUICK_THINK_LLM", "TRADINGAGENTS_DEEP_THINK_LLM",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
)
PRESENCE_ONLY = ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "COMQUTOR_WEEK2_LLM_BASE_URL", "TRADINGAGENTS_LLM_BACKEND_URL")
RUNTIME_SOURCE_ROOTS = ("comqutor_alpha", "tradingagents")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(*args: str, text: bool = True):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=text, check=True, timeout=120).stdout


def _process_env(pid: int) -> dict[str, str]:
    out = subprocess.run(["ps", "eww", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, check=True).stdout
    env = {}
    for match in re.finditer(r"(?:^|\s)([A-Z][A-Z0-9_]*)=(\S*)", out):
        env.setdefault(match.group(1), match.group(2))
    return env


def _code_snapshot(out_dir: Path, identity: dict) -> dict:
    snap = out_dir / "code_snapshot"
    snap.mkdir(parents=True, exist_ok=True)
    diff_text = _git("diff", "HEAD", "--binary")
    diff_bytes = diff_text.encode("utf-8")
    (snap / "tracked_diff_vs_HEAD.diff").write_bytes(diff_bytes)
    untracked = sorted(p for p in _git("ls-files", "--others", "--exclude-standard", "--", *RUNTIME_SOURCE_ROOTS).splitlines()
                       if p and "__pycache__" not in p)
    files = [p for p in untracked if (REPO / p).is_file()]
    listing = "".join(f"{p}\0{_sha((REPO / p).read_bytes())}\n" for p in files)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for p in files:
            tar.add(REPO / p, arcname=p)
    (snap / "untracked_runtime_source.tar.gz").write_bytes(buf.getvalue())
    (snap / "untracked_runtime_source_files.txt").write_text("".join(f"{_sha((REPO / p).read_bytes())}  {p}\n" for p in files), encoding="utf-8")
    (snap / "git_status_porcelain.txt").write_text(_git("status", "--porcelain=v1", "--untracked-files=all"), encoding="utf-8")
    snapshot = {"git_head": _git("rev-parse", "HEAD").strip(), "tracked_diff_sha256": _sha(diff_bytes),
                "tracked_diff_bytes": len(diff_bytes), "changed_tracked_files": len(_git("diff", "HEAD", "--name-only").splitlines()),
                "untracked_runtime_source_files": len(files), "untracked_runtime_source_sha256": _sha(listing.encode("utf-8")),
                "files": {"tracked_diff": "code_snapshot/tracked_diff_vs_HEAD.diff",
                          "untracked_runtime_source": "code_snapshot/untracked_runtime_source.tar.gz",
                          "untracked_listing": "code_snapshot/untracked_runtime_source_files.txt",
                          "git_status": "code_snapshot/git_status_porcelain.txt"}}
    snapshot["matches_running_process"] = {k: snapshot[k] == identity.get(k) for k in ("git_head", "tracked_diff_sha256", "untracked_runtime_source_sha256")}
    return snapshot


def _effective_week2(env_allowed: dict[str, str]) -> dict:
    child_env = {k: v for k, v in os.environ.items() if not k.startswith(("COMQUTOR_", "TRADINGAGENTS_"))}
    child_env.update({k: v for k, v in env_allowed.items() if k.startswith(("COMQUTOR_", "TRADINGAGENTS_"))})
    child_env["DEEPSEEK_API_KEY"] = "freeze-presence-only"
    code = ("import json\nfrom comqutor_alpha.structure_engine.week2_llm import describe_server_week2_effective_config\n"
            "from comqutor_alpha.run_environment import research_agent_effective_config\n"
            "print(json.dumps({'week2': describe_server_week2_effective_config(), 'agents': research_agent_effective_config()}))")
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=child_env, capture_output=True, text=True, check=True, timeout=120).stdout
    return json.loads(out.strip().splitlines()[-1])


def _prompt_identities() -> dict:
    from comqutor_alpha.structure_engine.week2_llm import _TASK_RUNTIME_METADATA, Week2LLMGateway

    out = {}
    for task in ("content_support_verification", "alpha_classifier", "evidence_stance_classifier", "claim_batch_enrichment", "structure_extractor"):
        sha = Week2LLMGateway.prompt_identity_sha256(task)
        meta = _TASK_RUNTIME_METADATA[task]
        pin = T3_PROMPT_PINS.get(task)
        out[task] = {"prompt_sha256": sha, "prompt_version": meta.get("prompt_version"),
                     "input_schema_version": meta.get("input_schema_version"), "output_schema_version": meta.get("output_schema_version"),
                     "taxonomy_version": meta.get("taxonomy_version"),
                     "t3_verified_pin": pin, "equals_t3_pin": (sha.startswith(pin) if pin else None)}
    agents = sorted(p for p in (REPO / "tradingagents").rglob("*.py") if "__pycache__" not in p.parts)
    listing = "".join(f"{p.relative_to(REPO)}\0{_sha(p.read_bytes())}\n" for p in agents)
    out["research_agents_tradingagents_source"] = {"files": len(agents), "sha256_of_path_and_file_sha_listing": _sha(listing.encode("utf-8")),
                                                   "note": "TradingAgents prompts live in this source tree; no separate prompt registry"}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    out_dir = Path(args.out_dir)
    ready = json.loads(urllib.request.build_opener(urllib.request.ProxyHandler({})).open(READY_URL, timeout=10).read())
    raw_env = _process_env(args.pid)
    env_allowed = {k: raw_env[k] for k in ENV_ALLOWLIST if k in raw_env}
    presence = {k: (k in raw_env and raw_env[k] != "") for k in PRESENCE_ONLY}
    from comqutor_alpha.storage.db.engine import describe_database

    db_env = describe_database(raw_env["COMQUTOR_DATABASE_URL"]) if raw_env.get("COMQUTOR_DATABASE_URL") else {"dialect": None, "database": None}
    budget = json.loads((T4 / "04_fresh_prep" / "budget.json").read_text(encoding="utf-8"))
    caps = budget["proposed_caps_for_owner_confirmation"]
    identity = ready.get("code_identity") or {}
    snapshot = _code_snapshot(out_dir, identity)
    effective = _effective_week2(env_allowed)
    checks = {
        "ready_status_ready": ready.get("status") == "ready",
        "real_execution_configured": ready.get("real_execution") == "configured",
        "live_semantic_pipeline_ready": ready.get("live_semantic_pipeline") == "ready",
        "database_is_t4_postgresql": (ready.get("database_backend") or {}).get("dialect") == EXPECTED["dialect"]
                                     and (ready.get("database_backend") or {}).get("database") == EXPECTED["database"],
        "process_env_database_is_t4_postgresql": db_env == {"dialect": EXPECTED["dialect"], "database": EXPECTED["database"]},
        "process_requires_t4_database": env_allowed.get("COMQUTOR_REQUIRE_DATABASE_NAME") == EXPECTED["database"]
                                        and env_allowed.get("COMQUTOR_REQUIRE_DATABASE_DIALECT") == EXPECTED["dialect"],
        "week2_profile_selected": (ready.get("week2_semantic") or {}).get("execution_profile") == EXPECTED["week2_profile"]
                                  and effective["week2"]["execution_profile"] == EXPECTED["week2_profile"],
        "week2_enabled": (ready.get("week2_semantic") or {}).get("enabled") is True,
        "port_and_origin": env_allowed.get("COMQUTOR_API_PORT") == EXPECTED["port"] and env_allowed.get("COMQUTOR_CORS_ORIGINS") == EXPECTED["cors"],
        "week2_max_calls_equals_cap": str(caps["week2_max_calls"]) == env_allowed.get("COMQUTOR_WEEK2_LLM_MAX_CALLS")
                                      and (ready.get("week2_semantic") or {}).get("max_calls") == caps["week2_max_calls"],
        "agent_request_cap_equals_cap": str(caps["research_agent_max_actual_requests"]) == env_allowed.get("COMQUTOR_RESEARCH_AGENT_MAX_ACTUAL_REQUESTS"),
        "agent_retries_zero": env_allowed.get("COMQUTOR_RESEARCH_AGENT_MAX_RETRIES") == "0",
        "week2_retries_zero": effective["week2"]["gateway_max_retries"] == 0
                              and all(t.get("application_retries") == 0 for t in effective["week2"]["tasks"].values()),
        "job_timeout_equals_cap": env_allowed.get("COMQUTOR_JOB_TIMEOUT_SECONDS") == str(caps["job_timeout_seconds"]),
        "single_job_worker": env_allowed.get("COMQUTOR_JOB_MAX_WORKERS") == "1",
        "force_refresh_off": env_allowed.get("COMQUTOR_REAL_FORCE_REFRESH_ENABLED") == "false",
        "request_response_audit_on": effective["week2"]["request_response_audit"] is True,
        "provider_credential_present": presence["DEEPSEEK_API_KEY"],
        "no_proxy_override": not any(k in env_allowed for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")),
        "code_snapshot_matches_running_process": all(snapshot["matches_running_process"].values()),
    }
    prompts = _prompt_identities()
    checks["week2_prompts_equal_t3_pins"] = all(v["equals_t3_pin"] for k, v in prompts.items() if isinstance(v, dict) and v.get("t3_verified_pin"))
    doc = {
        "schema": "t4.fresh_run_frozen_config.v1",
        "frozen_at": datetime.now(UTC).isoformat(),
        "ticker": "NVDA",
        "who_starts_the_run": "the project owner, by clicking Start Research on http://127.0.0.1:5177/research -- never a script, API call or recorder",
        "instance": {"api": "http://127.0.0.1:8002", "web": "http://127.0.0.1:5177/research", "pid": args.pid,
                     "output_root": env_allowed.get("COMQUTOR_OUTPUT_DIR")},
        "ready": ready,
        "process_environment_allowlisted": env_allowed,
        "process_credentials_present": presence,
        "process_database": db_env,
        "effective_config": effective,
        "prompt_identities": prompts,
        "code_identity_reported_by_process": identity,
        "code_snapshot": snapshot,
        "caps_and_stop_rules": {"caps": caps, "hard_guards": budget["hard_guards"], "no_usd_guard": budget["no_usd_guard"],
                                "absolute_cost_bound_at_caps_usd": budget["absolute_cost_bound_at_caps_usd"]},
        "checks": checks,
        "all_checks_pass": all(checks.values()),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, ensure_ascii=False, indent=1, default=str) + "\n"
    for secret_key in PRESENCE_ONLY + ("COMQUTOR_DATABASE_URL",):
        value = raw_env.get(secret_key)
        if value and len(value) > 6 and value in text:
            print(f"REFUSED: the value of {secret_key} would have been written", file=sys.stderr)
            return 4
    (out_dir / "frozen_config.json").write_text(text, encoding="utf-8")
    print(json.dumps({"all_checks_pass": doc["all_checks_pass"], "failed": [k for k, v in checks.items() if not v],
                      "code": {"head": snapshot["git_head"][:7], "tracked_diff_sha256": snapshot["tracked_diff_sha256"][:12],
                               "untracked": snapshot["untracked_runtime_source_sha256"][:12]},
                      "frozen_config_sha256": _sha(text.encode("utf-8"))}, indent=1))
    return 0 if doc["all_checks_pass"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
