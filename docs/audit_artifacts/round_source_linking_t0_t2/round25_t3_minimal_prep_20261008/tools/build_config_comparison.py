#!/usr/bin/env python3
"""Round 25 (T3 prep), deliverable 1: the per-step model configuration comparison John's T3 section 1 asks for -- Structured Adapter, Alpha
Classifier, Polarity Classifier, Structure Extractor -- in three separate columns that are never merged:

  * historical evaluation configuration (the configuration a historical score was measured with)
  * what each real saved run ACTUALLY sent (re-derived here from the run's own llm_semantic_calls.jsonl, not from memory)
  * the configuration proposed for the next frozen execution (a proposal only; nothing is changed by this script)

Parameters a request did not carry are written as "not sent -> provider default"; anything that cannot be verified from saved records is
"unknown". Read-only, zero network; writes 01_config_comparison.json (the .md is written by hand from it).

    python build_config_comparison.py --out <json>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from call_profile import profile  # noqa: E402

from comqutor_alpha.structure_engine import week2_llm  # noqa: E402

TASKS = {
    "structured_adapter": "claim_batch_enrichment",
    "alpha_classifier": "alpha_classifier",
    "polarity_classifier": "evidence_stance_classifier",
    "structure_extractor": "structure_extractor",
    # not one of John's four steps, but link 1 of the joint chain ("source content -> claim") is judged by this production task
    "content_support_verification": "content_support_verification",
}
RUN_LOGS = {
    "034a0a60 (NVDA Fresh, 2026-10-02)": "outputs/runs/034a0a60-430e-41f8-8321-03a11389707a/llm_semantic_calls.jsonl",
    "1bad76a7 (AMD Fresh, 2026-10-05)": "outputs/runs/1bad76a7-72ac-4c8b-8189-2e5c0f1a6105/llm_semantic_calls.jsonl",
    "c904d4cc (AMD Fresh, 2026-10-06)": "outputs/runs/c904d4cc-dc09-495c-aec5-b056979948e1/llm_semantic_calls.jsonl",
    "recovery-20261007T053635Z (AMD classification recovery on c904d4cc's frozen inputs)": "outputs/runs/recovery-20261007T053635Z-26d6cd1a/llm_semantic_calls.jsonl",
    "direction-20261007T065826Z (stance attempt on the recovery run, round 17)": "outputs/runs/direction-20261007T065826Z-d311b8e2/llm_semantic_calls.jsonl",
    "t3live_20261001T014648Z (T3 v6 diagnostic, 40 samples)": "outputs/t3_evaluations/t3live_20261001T014648Z_1fb9c9d5/llm_semantic_calls.jsonl",
    "t3live_20261001T232716Z + 3 more (v7 dev verification, 19 samples)": "outputs/t3_prompt_v7_verification/t3live_20261001T232716Z_5d79176f/llm_semantic_calls.jsonl",
}

# the semantic call ledger records the claim-enrichment task under the step name, not under its prompt-metadata key
LOGGED_TASK_NAME = {"claim_batch_enrichment": "structured_adapter"}
# content_support_verification never reaches a run's semantic call ledger: the task is not in llm_runtime.contracts.SEMANTIC_TASKS, so the
# session cannot open a trace for it (SEMANTIC_RUNTIME_CALL_START_FAILED; found in round 25). What was saved is listed here from the error
# log and the Phase C request/response audit
CONTENT_SUPPORT_SAVED_EVIDENCE = {
    "c904d4cc (AMD Fresh, 2026-10-06)": "error log only: 259 WEEK2_LLM_CACHE_READ_FAILED, 42 WEEK2_LLM_TIMEOUT (45 s), 7 WEEK2_LLM_INPUT_TOO_LARGE, 1 validation failure; 152 saved LLM verdicts carry claim_id/source/content_hash but no model, prompt or raw response",
    "phase-c-amd-21-claim-verification (2026-10-05)": "27 audited requests for 21 AMD 1bad76a7 claims, max_tokens 8192 sent, p50 29 s / max 38 s, 6 finish_reason=length (truncated at 8192), prompt in the audit body",
}

HISTORICAL = {
    "alpha_classifier": [
        {
            "evaluation": "Candidate-3 final validation (150-sample Final Gold) -- the historical 82.67%",
            "provider_model": "anthropic / claude-sonnet-4-6",
            "prompt": "unknown version label; only classifier hash d53b2d7511f4c4a8... recorded",
            "path": "single (150 logical calls for 150 rows)",
            "max_tokens": "unknown (not recorded)",
            "temperature": "'production default (unmodified)' per the provider audit",
            "retries": "0 used",
            "evidence": ["docs/audit_artifacts/v0_2_candidate3_final_validation_result.json", "docs/audit_artifacts/v0_2_candidate3_final_provider_audit.json"],
            "score_applies_to_current_config": False,
            "why_not": "different provider and model (Anthropic Claude Sonnet 4.6 vs DeepSeek v4 Flash); prompt version unknown",
        },
        {
            "evaluation": "T3 v6 diagnostic run t3live_20261001T014648Z (40 samples, scored 2026-10-05 with labels whose reviewer is not recorded)",
            "provider_model": "deepseek / deepseek-v4-flash",
            "prompt": "week2.alpha_classifier.v6 (prompt identity bb2dbdf0...)",
            "path": "single",
            "max_tokens": "configured 200, but serialized as max_completion_tokens (a field DeepSeek does not document); how the server treated it is unknown -- mean output ~881 tokens, so 200 was not enforced",
            "retries": "0 used",
            "evidence": ["outputs/t3_evaluations/t3live_20261001T014648Z_1fb9c9d5/", "docs/audit_artifacts/round_source_linking_t0_t2/t3live_20261001T014648Z_1fb9c9d5_max_output_tokens_diagnostic.md"],
            "score_applies_to_current_config": False,
            "why_not": "v6 is not the deployed prompt (v7 is); the score stays v6's historical result",
        },
        {
            "evaluation": "v7 development verification (19 samples = 13 disagreement + 6 control, 24 requests, compared with ChatGPT AI_REVIEW only)",
            "provider_model": "deepseek / deepseek-v4-flash",
            "prompt": "week2.alpha_classifier.v7 (prompt identity ac48723f...)",
            "path": "single",
            "max_tokens": "200 (1 sample, truncated twice), 2048 (18 samples: 3 truncated), 4096 (3 re-tests)",
            "retries": "1 used (200-token smoke)",
            "evidence": ["docs/audit_artifacts/round_source_linking_t0_t2/t3_prompt_v7_limited_verification_final_index.md"],
            "score_applies_to_current_config": False,
            "why_not": "development material compared with an AI second opinion, never a reference standard; three token caps mixed",
        },
    ],
    "polarity_classifier": [
        {
            "evaluation": "Item-2 blind holdout #2 (H2) -- the historical 87.23%",
            "provider_model": "anthropic / claude-sonnet-4-6",
            "prompt": "evidence_stance.llm_classifier.v3 (the same version string as today)",
            "path": "batch (15 batches for 141 samples, consistent with BATCH_SIZE 10)",
            "max_tokens": "unknown (not recorded)",
            "evidence": ["docs/audit_artifacts/item2_blind_holdout2_summary.json", "docs/audit_artifacts/item2_blind_holdout2_provider_call_log.json"],
            "score_applies_to_current_config": False,
            "why_not": "different provider and model; prompt version and batch convention match",
        }
    ],
    "structured_adapter": [{"evaluation": "none found for this task (claim_batch_enrichment)", "score_applies_to_current_config": None}],
    "structure_extractor": [{"evaluation": "none found for this task", "score_applies_to_current_config": None}],
    "content_support_verification": [
        {
            "evaluation": "no accuracy evaluation; Phase C (2026-10-05) ran it on 21 AMD 1bad76a7 claims, 27 audited requests, max_tokens 8192 (6 hit the cap)",
            "evidence": ["outputs/runs/phase-c-amd-21-claim-verification/error_logs/"],
            "score_applies_to_current_config": None,
        }
    ],
}

CODE_NOW = {
    "provider_model": "deepseek / deepseek-v4-flash (.env COMQUTOR_WEEK2_LLM_PROVIDER / COMQUTOR_WEEK2_LLM_MODEL)",
    "timeout": ".env COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS=45 (the server gateway bounds it to 1-120 s: build_server_week2_llm_gateway); one shared value for every task",
    "application_retries": ".env COMQUTOR_WEEK2_LLM_MAX_RETRIES=1; evidence_stance_classifier gets max(value, 2) = 2 whenever the value is > 0 (_resolve_task_max_retries); an explicit 0 is respected",
    "sdk_retries": "0 (hard-coded max_retries=0 when the server gateway builds the client)",
    "unsent_parameters": "temperature, top_p, thinking, reasoning_effort, response_format, stop: not set by the client (langchain-openai 1.3.5 defaults are None) -> provider defaults; DeepSeek v4 Flash returned reasoning tokens, so its thinking mode was on by default",
    "cache": "semantic runtime cache key computed per call; the evaluation driver can pass NullLLMResponseCache (no cache)",
}
PER_TASK_CODE = {
    "claim_batch_enrichment": {"path": "batch (one call per agent report)", "max_tokens": "not sent -> provider default", "concurrency": "COMQUTOR_WEEK2_ADAPTER_CONCURRENCY (default 4)"},
    "alpha_classifier": {"path": "single (use_batched_classifier defaults to False at the production call site)", "max_tokens": "COMQUTOR_WEEK2_ALPHA_CLASSIFIER_MAX_TOKENS if set (not set in .env) -> otherwise not sent -> provider default", "concurrency": "COMQUTOR_WEEK2_LLM_CONCURRENCY (default 4, max 8)"},
    "evidence_stance_classifier": {"path": "batch of 10 (claim, Alpha) pairs; each matched claim contributes its matched Alpha plus up to 2 secondary Alphas", "max_tokens": "not sent -> provider default", "concurrency": "COMQUTOR_WEEK2_STANCE_CONCURRENCY (default 4, max 8)"},
    "structure_extractor": {"path": "single, per claim with >= 2 factors", "max_tokens": "not sent -> provider default", "concurrency": "unknown (not separately configurable)"},
    "content_support_verification": {"path": "batch of 5 claims (content_support_llm.BATCH_SIZE); the gateway refuses any request over 60,000 characters before sending (WEEK2_LLM_INPUT_TOO_LARGE)", "max_tokens": "COMQUTOR_WEEK2_CONTENT_SUPPORT_MAX_TOKENS if set (not set in .env) -> otherwise not sent", "concurrency": "serial (apply_llm_content_support_verification processes its batches one after another)", "call_ledger": "not recorded (task missing from llm_runtime.contracts.SEMANTIC_TASKS)"},
}

# the configuration proposed for the next frozen T3 execution: the defaults of t3_joint_sample_driver.FrozenConfig, restated per step;
# 06_execution_proposal.md gives the basis of each value and the owner decisions
NOT_EXECUTED = "not executed in the T3 joint batch: the five links read the saved claims as the adapter produced them; no request, nothing to freeze"
PROPOSED_FREEZE = {
    "structured_adapter": NOT_EXECUTED,
    "structure_extractor": "not one of the five links; not executed in the T3 joint batch; no request",
    "alpha_classifier": {
        "provider_model": "deepseek / deepseek-v4-flash", "prompt": "week2.alpha_classifier.v7 (prompt identity in current_code)",
        "path": "single, one claim per request", "max_tokens": "not sent (as deployed); 4096 is the alternative (owner decision D2)",
        "timeout_s": 45, "application_retries": 0, "sdk_retries": 0, "concurrency": 4, "cache": "none",
        "requests": "7 new (cap 7); 33 claims replay a saved production answer bound by prompt identity + input hash (zero requests)",
    },
    "polarity_classifier": {
        "provider_model": "deepseek / deepseek-v4-flash", "prompt": "evidence_stance.llm_classifier.v3 (prompt identity in current_code)",
        "path": "batches of 10 (claim, Alpha) items, production constant", "max_tokens": "not sent (as deployed)",
        "timeout_s": "120 proposed (deployed 45; owner decision D3 -- no saved measurement beyond 45 s exists)", "application_retries": 0,
        "sdk_retries": 0, "concurrency": 4, "cache": "none", "requests": "at most 5 (cap 5)",
    },
    "content_support_verification": {
        "provider_model": "deepseek / deepseek-v4-flash", "prompt": "content_support.llm.v2.1 (prompt identity in current_code)",
        "path": "ONE claim per request (deployed batch of 5 would overflow the 60,000-character input cap for 3 of 4 batches; owner decision D4)",
        "max_tokens": "not sent (as deployed); 8192 truncated 6 of 27 Phase C requests (owner decision D5)", "timeout_s": "120 proposed (deployed 45)",
        "application_retries": 0, "sdk_retries": 0, "concurrency": "serial", "cache": "none", "requests": "17 (cap 17)",
    },
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out)
    if out.exists():
        print("refusing: output exists", out, file=sys.stderr)
        return 2
    runs = {}
    for label, rel in RUN_LOGS.items():
        path = REPO / rel
        runs[label] = {"calls_file": rel, "tasks": profile(path) if path.exists() else "MISSING"}
    steps = {}
    for step, task in TASKS.items():
        meta = week2_llm._TASK_RUNTIME_METADATA[task]
        logged_task = LOGGED_TASK_NAME.get(task, task)
        steps[step] = {
            "task": task,
            "task_name_in_call_logs": logged_task,
            "current_code": {
                "prompt_version": meta["prompt_version"],
                "prompt_identity_sha256": week2_llm.Week2LLMGateway.prompt_identity_sha256(task),
                **PER_TASK_CODE[task],
            },
            "historical_evaluations": HISTORICAL[step],
            "proposed_freeze_for_t3_execution": PROPOSED_FREEZE[step],
            "real_runs": {label: (data["tasks"].get(logged_task) if isinstance(data["tasks"], dict) else data["tasks"]) for label, data in runs.items()},
        }
    document = {
        "schema_version": "t3_round25_config_comparison.v2",
        "code_identity": "HEAD 7a9aefa + the working-tree snapshot in code_snapshot/ (tracked diff + untracked source copies + hashes)",
        "real_runs_code_identity": "unknown: no working-tree snapshot was taken when 034a0a60, 1bad76a7, c904d4cc or the recovery run executed (release_manifest_v2 code_identity UNKNOWN_NO_SNAPSHOT_AT_EXECUTION); their prompt identities ARE recorded per call and equal today's",
        "shared_settings_now": CODE_NOW,
        "content_support_saved_evidence": CONTENT_SUPPORT_SAVED_EVIDENCE,
        "steps": steps,
    }
    out.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({s: {"prompt": v["current_code"]["prompt_version"], "sha": v["current_code"]["prompt_identity_sha256"][:12]} for s, v in steps.items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
