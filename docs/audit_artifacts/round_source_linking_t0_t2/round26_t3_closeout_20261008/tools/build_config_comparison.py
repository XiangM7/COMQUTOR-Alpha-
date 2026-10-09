#!/usr/bin/env python3
"""T3 closeout: effective configuration of the three measured tasks, read back from the REAL production gateway builder (zero network).

Three columns per task: (a) the deployed configuration -- the .env's own Week 2 keys (allowlisted, never secrets) with no profile, which
this closeout does not change; (b) the T3 execution's signed, frozen configuration; (c) the new opt-in profile t3_verified_20261008.
(a) and (c) are not described but measured: the gateway is built with build_server_week2_llm_gateway and each value is read from the
object (timeouts per task, effective retries per task, audit switch) or from the production resolvers (concurrency, content-support
batch size). No request is sent.

    python build_config_comparison.py --out-json 03_task_profile/config_before_after.json
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
PLAN = REPO / ("docs/audit_artifacts/round_source_linking_t0_t2/round25_t3_minimal_prep_20261008/B4_execution/"
               "authorized_plan_SIGNED_t3joint-20261008T170322Z-bd99811e.json")
TASKS = ("content_support_verification", "alpha_classifier", "evidence_stance_classifier")
# only these .env keys are read; values of any other key (credentials included) are never read or printed
ENV_ALLOWLIST = ("COMQUTOR_WEEK2_LLM_PROVIDER", "COMQUTOR_WEEK2_LLM_MODEL", "COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS", "COMQUTOR_WEEK2_LLM_MAX_RETRIES",
                 "COMQUTOR_WEEK2_LLM_MAX_CALLS", "COMQUTOR_WEEK2_LLM_CONCURRENCY", "COMQUTOR_WEEK2_STANCE_CONCURRENCY",
                 "COMQUTOR_WEEK2_LLM_ENABLE_REQUEST_AUDIT", "COMQUTOR_WEEK2_CONTENT_SUPPORT_BATCH_SIZE", "COMQUTOR_WEEK2_ALPHA_CLASSIFIER_MAX_TOKENS",
                 "COMQUTOR_WEEK2_CONTENT_SUPPORT_MAX_TOKENS", "COMQUTOR_WEEK2_LLM_PROFILE", "COMQUTOR_WEEK2_LLM_BASE_URL")


def _dotenv_allowlisted() -> dict[str, str]:
    out = {}
    for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() in ENV_ALLOWLIST:
            out[key.strip()] = value.split("#", 1)[0].strip()
    return out


def _measure(env: dict[str, str]) -> dict:
    from comqutor_alpha.structure_engine import content_support_llm, week2_llm
    from comqutor_alpha.structure_engine.week2_execution_profile import (
        resolve_week2_execution_profile,
    )

    saved = dict(os.environ)
    try:
        for key in ENV_ALLOWLIST:
            os.environ.pop(key, None)
        os.environ.update({"COMQUTOR_WEEK2_LLM_ENABLED": "1", "DEEPSEEK_API_KEY": "config-readback-not-a-key", **env})
        with tempfile.TemporaryDirectory() as tmp:
            gateway = week2_llm.build_server_week2_llm_gateway("config-readback", tmp)
        profile = resolve_week2_execution_profile()
        batch_env = os.environ.get("COMQUTOR_WEEK2_CONTENT_SUPPORT_BATCH_SIZE")
        batch = profile.content_support_batch_size if profile else (int(batch_env) if batch_env else content_support_llm.BATCH_SIZE)
        per_task = {}
        for task in TASKS:
            model = gateway._resolve_task_model(task)
            per_task[task] = {
                "client_read_timeout_seconds": getattr(model, "request_timeout", None),
                "application_timeout_seconds": gateway.task_timeout_seconds_for(task),
                "application_retries": week2_llm._resolve_task_max_retries(task, gateway.max_retries),
                "sdk_retries": getattr(model, "max_retries", None),
                "request_response_audit": gateway._audit_enabled,
                "max_tokens_sent": getattr(model, "max_tokens", None),
                "model": gateway.model_name,
            }
        per_task["content_support_verification"]["batch_size"] = batch
        per_task["alpha_classifier"]["path"] = "single (map_structured_records use_batched_classifier=False, the production default)"
        per_task["alpha_classifier"]["concurrency"] = week2_llm.resolve_alpha_classifier_concurrency()
        per_task["evidence_stance_classifier"]["batch_size"] = "10 (evidence_stance_llm.BATCH_SIZE, production constant)"
        per_task["evidence_stance_classifier"]["concurrency"] = week2_llm.resolve_evidence_stance_concurrency()
        return {"profile": gateway.execution_profile, "tasks": per_task,
                "other_tasks_shared_timeout_seconds": gateway.timeout_seconds, "gateway_max_retries": gateway.max_retries}
    finally:
        os.environ.clear()
        os.environ.update(saved)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-json", required=True)
    args = ap.parse_args(argv)
    dotenv = _dotenv_allowlisted()
    deployed = _measure(dotenv)
    profiled = _measure({**dotenv, "COMQUTOR_WEEK2_LLM_PROFILE": "t3_verified_20261008"})
    plan = json.loads(PLAN.read_text(encoding="utf-8"))["config"]
    execution = {task: {"client_read_timeout_seconds": plan["timeout_seconds"][task], "application_timeout_seconds": plan["timeout_seconds"][task],
                        "application_retries": plan["application_retries"], "sdk_retries": plan["sdk_retries"],
                        "request_response_audit": True, "max_tokens_sent": plan["max_tokens"][task], "model": plan["model"]} for task in TASKS}
    execution["content_support_verification"]["batch_size"] = plan["content_support_batch_size"]
    execution["alpha_classifier"]["concurrency"] = plan["alpha_classifier_concurrency"]
    execution["evidence_stance_classifier"]["concurrency"] = plan["stance_concurrency"]
    comparable = ("client_read_timeout_seconds", "application_timeout_seconds", "application_retries", "sdk_retries", "request_response_audit",
                  "max_tokens_sent", "model", "batch_size", "concurrency")
    differences = {task: {k: {"profile": profiled["tasks"][task].get(k), "execution": execution[task].get(k)}
                          for k in comparable if k in execution[task] and profiled["tasks"][task].get(k) != execution[task].get(k)} for task in TASKS}
    doc = {"dotenv_keys_read": sorted(dotenv), "dotenv_values": dotenv,
           "a_deployed_without_profile": deployed, "b_t3_execution_signed_config": execution, "c_profile_t3_verified_20261008": profiled,
           "profile_vs_execution_differences": differences, "profile_equals_execution": not any(differences.values()),
           "note": ("(a) is the configuration this closeout leaves in force for every deployment that does not select the profile (the running "
                    "service included). The execution's results are interpreted under (b), its own frozen configuration, never under (a) or (c).")}
    Path(args.out_json).write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"profile_equals_execution": doc["profile_equals_execution"], "differences": differences}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
