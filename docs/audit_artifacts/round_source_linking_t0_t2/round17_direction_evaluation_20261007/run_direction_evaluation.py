#!/usr/bin/env python3
"""Round 17: real direction (evidence_stance_classifier) judgments for the recovered AMD classification, then a derived
evaluation run saved through the verified derived-run path.

Default / --dry-run: ZERO Provider calls. Rebuilds the work list with the production request builder, reconciles it
with the saved manifest and the REAL classification ledger, captures the actual request shape over a fake transport,
proves the audit mount / task allowlist / cap / zero-retry with the same fake transport, and writes
preflight_result.json.

--execute: refused unless the operator's shell exports COMQUTOR_DIRECTION_REAL_EXECUTION_ACK bound to this exact plan
and the environment equals the frozen one (judged against the shell snapshot taken before any repo import).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_LAUNCH_ENV = dict(os.environ)  # what the operator's SHELL exported, before the repo import can run load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))
HERE = Path(__file__).resolve().parent

ROOT_RUN_ID = "c904d4cc-dc09-495c-aec5-b056979948e1"
PARENT_RUN_ID = "recovery-20261007T053635Z-26d6cd1a"
OUTPUT_ROOT = (REPO_ROOT / "outputs" / "runs").resolve()
PARENT_DIR = OUTPUT_ROOT / PARENT_RUN_ID
ROOT_DIR = OUTPUT_ROOT / ROOT_RUN_ID
HARD_REQUEST_CAP = 17
EXPECTED_MODEL = "deepseek-v4-flash"
EXPECTED_TIMEOUT_SECONDS = 45.0
FROZEN_CONCURRENCY = 4
ACK_ENV = "COMQUTOR_DIRECTION_REAL_EXECUTION_ACK"
REQUIRED_ENV = {
    "COMQUTOR_WEEK2_LLM_ENABLED": "1",
    "COMQUTOR_WEEK2_LLM_PROVIDER": "deepseek",
    "COMQUTOR_WEEK2_LLM_MODEL": EXPECTED_MODEL,
    "COMQUTOR_WEEK2_LLM_MAX_RETRIES": "0",
    "COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS": "45",
    "COMQUTOR_WEEK2_STANCE_CONCURRENCY": "4",
}
# Change the request shape / endpoint or belong to a different task's experiment; must be absent from the launch shell.
FORBIDDEN_ENV = (
    "COMQUTOR_WEEK2_ALPHA_CLASSIFIER_MAX_TOKENS",
    "COMQUTOR_WEEK2_CONTENT_SUPPORT_MAX_TOKENS",
    "COMQUTOR_WEEK2_LLM_BASE_URL",
)


# ---------------------------------------------------------------------------
# Inputs and the frozen plan
# ---------------------------------------------------------------------------


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_inputs():
    from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
    from comqutor_alpha.direction_evaluation import build_direction_plan

    parent = json.loads((PARENT_DIR / "alpha_matches.json").read_text())
    manifest_path = PARENT_DIR / "evidence_stance_followup_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    taxonomy = load_alpha_taxonomy()
    return parent, manifest, manifest_path, taxonomy, build_direction_plan(parent, taxonomy)


def frozen_plan_sha256(plan, manifest_path: Path) -> str:
    from comqutor_alpha.direction_evaluation import plan_sha256

    return plan_sha256(plan, {
        "root_run_id": ROOT_RUN_ID, "parent_run_id": PARENT_RUN_ID,
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "hard_request_cap": HARD_REQUEST_CAP, "model": EXPECTED_MODEL, "timeout_seconds": EXPECTED_TIMEOUT_SECONDS,
        "stance_concurrency": FROZEN_CONCURRENCY, "retries": {"client_level": 0, "application_level": 0},
        "request_response_audit": True, "allowed_tasks": ["evidence_stance_classifier"],
        "first_batch_gate": "no further batch is scheduled unless batch 0 produced a protocol-valid response",
    })


def expected_ack(plan, manifest_path: Path) -> str:
    return f"direction-{len(plan.items)}-pairs-{len(plan.batches)}-requests-plan-{frozen_plan_sha256(plan, manifest_path)[:16]}"


def environment_problems(prior_sent: int, environ) -> list[str]:
    problems = [f"{k} must be exported as {v!r} (found {environ.get(k)!r})" for k, v in REQUIRED_ENV.items() if environ.get(k) != v]
    try:
        max_calls = int(environ.get("COMQUTOR_WEEK2_LLM_MAX_CALLS", ""))
        if not 1 <= max_calls <= HARD_REQUEST_CAP - prior_sent:
            problems.append(f"COMQUTOR_WEEK2_LLM_MAX_CALLS={max_calls} must be between 1 and {HARD_REQUEST_CAP - prior_sent}")
    except ValueError:
        problems.append("COMQUTOR_WEEK2_LLM_MAX_CALLS must be exported explicitly as an integer")
    problems.extend(f"{n} is exported but the direction run must keep the existing request shape (unset it)" for n in FORBIDDEN_ENV if environ.get(n))
    if not environ.get("DEEPSEEK_API_KEY"):
        problems.append("DEEPSEEK_API_KEY is not exported")
    url = environ.get("COMQUTOR_DATABASE_URL")
    if not url:
        problems.append("COMQUTOR_DATABASE_URL must be exported explicitly (the isolated database)")
    else:
        from sqlalchemy.engine import make_url

        name = make_url(url).database or ""
        if not name.endswith("_test"):
            problems.append(f"database {name!r} does not end in _test")
        if environ.get("COMQUTOR_REQUIRE_DATABASE_NAME") != name:
            problems.append(f"COMQUTOR_REQUIRE_DATABASE_NAME must be exported as {name!r}")
    return problems


# ---------------------------------------------------------------------------
# Zero-call preflight
# ---------------------------------------------------------------------------


def classification_decisions() -> dict[str, dict]:
    """claim_id -> the REAL model decision, from the semantic-call ledgers (the recovery's own, plus the original
    run's two valid results) -- independent of alpha_matches.json."""
    decisions: dict[str, dict] = {}
    for ledger in (ROOT_DIR / "llm_semantic_calls.jsonl", PARENT_DIR / "llm_semantic_calls.jsonl"):
        for call in _read_jsonl(ledger):
            out = call.get("validated_output")
            if call.get("task") == "alpha_classifier" and call.get("validation_status") == "accepted" and isinstance(out, dict):
                for claim_id in call.get("claim_ids") or []:
                    decisions[claim_id] = out
        # the original run predates claim_ids on its records: bind its two results by recorded claim text
    return decisions


def verify_plan(plan, parent, manifest, taxonomy) -> dict:
    from comqutor_alpha.direction_evaluation import payload_sha256

    structured = {r["claim_id"]: r for r in json.loads((ROOT_DIR / "structured_agent_outputs.json").read_text())["records"]}
    parent_matches = {m["claim_id"]: m for m in parent["matches"]}
    decisions = classification_decisions()
    out: dict = {}
    manifest_pairs = [(i["claim_id"], i["target_alpha_id"], i["request_payload_sha256"]) for i in manifest["items"]]
    plan_pairs = [(i.claim_id, i.target_alpha_id, payload_sha256(i.payload)) for i in plan.items]
    out["pairs_equal_manifest_in_order"] = manifest_pairs == plan_pairs
    out["pairs_total"] = len(plan_pairs)
    out["manifest_counts"] = {k: manifest[k] for k in ("matched_claims", "pairs_total", "pairs_reusable_from_base_run", "pairs_needing_request", "items_per_request", "independent_request_budget")}
    batch_sizes = [len(b) for b in plan.batches]
    out["batch_sizes"] = batch_sizes
    out["batches_equal_manifest_budget_and_cap"] = len(batch_sizes) == manifest["independent_request_budget"] == HARD_REQUEST_CAP
    out["reusable_pairs"] = manifest["pairs_reusable_from_base_run"]
    mismatches = []
    for item in plan.items:
        record = structured.get(item.claim_id)
        match = parent_matches.get(item.claim_id)
        decision = decisions.get(item.claim_id)
        if record is None or match is None:
            mismatches.append((item.claim_id, "missing record"))
        elif item.payload["claim"] != str(record.get("claim") or "") or item.payload["evidence"] != str(record.get("evidence") or ""):
            mismatches.append((item.claim_id, "claim/evidence text differs from the original structured record"))
        elif match.get("claim") != record.get("claim") or match.get("evidence") != record.get("evidence"):
            mismatches.append((item.claim_id, "alpha_matches text differs from the original structured record"))
        elif not decision or decision.get("decision") != "select" or decision.get("selected_alpha_id") != item.target_alpha_id or match.get("matched_alpha") != item.target_alpha_id:
            mismatches.append((item.claim_id, f"target alpha {item.target_alpha_id} != real classification {decision}"))
        elif match.get("secondary_alphas"):
            mismatches.append((item.claim_id, "secondary alphas present (pair count would differ)"))
    out["identity_mismatches"] = mismatches
    selected = {cid for cid, d in decisions.items() if d.get("decision") == "select"}
    pair_claims = {i.claim_id for i in plan.items}
    overridden = {cid for cid in selected if not parent_matches[cid].get("matched_alpha")}
    out["real_classification_model_selections"] = len(selected)
    out["selections_with_a_matched_alpha"] = len(selected - overridden)
    # The production mapper's own gates turn some model selections into no_match BEFORE matching; those claims are
    # not direction candidates by production design (retained_target_alpha_ids reads matched_alpha only).
    out["model_selections_overridden_to_no_match_by_mapper_gates"] = {
        "count": len(overridden),
        "by_alpha": {a: sum(1 for c in overridden if decisions[c]["selected_alpha_id"] == a) for a in sorted({decisions[c]["selected_alpha_id"] for c in overridden})},
        "reasons": {r: sum(1 for c in overridden if parent_matches[c].get("reason") == r) for r in sorted({parent_matches[c].get("reason") for c in overridden})},
        "all_have_a_recorded_gate_reason": all("overriding semantic classifier selection to no_match" in (parent_matches[c].get("reason") or "") for c in overridden),
    }
    out["pairs_cover_exactly_the_matched_selections"] = (selected - overridden) == pair_claims
    out["parent_llm_selected_alpha_id_matches_ledger"] = {m["claim_id"] for m in parent["matches"] if m.get("llm_selected_alpha_id")} == selected
    out["unclassified_timeout_claim_in_pairs"] = any(c.endswith("news_agent:news_report:claim:105") for c in pair_claims)
    out["ok"] = bool(out["pairs_equal_manifest_in_order"] and out["batches_equal_manifest_budget_and_cap"] and not mismatches
                     and out["pairs_cover_exactly_the_matched_selections"] and out["parent_llm_selected_alpha_id_matches_ledger"]
                     and out["model_selections_overridden_to_no_match_by_mapper_gates"]["all_have_a_recorded_gate_reason"] and out["reusable_pairs"] == 0 and not out["unclassified_timeout_claim_in_pairs"])
    return out


def fake_transport_proofs(plan, taxonomy) -> dict:
    """Over a fake httpx transport only: the real request shape, the audit mount, the task allowlist, the cap, the
    stop rules' inputs and zero retries. No network."""
    import httpx

    from comqutor_alpha.classification_recovery import STANCE_TASK, RecoveryTaskNotAllowedError, TaskAllowlistGateway
    from comqutor_alpha.direction_evaluation import audit_paths, preflight_direction_gateway, read_jsonl, request_wire_problem
    from comqutor_alpha.llm_runtime.cache import InMemoryLLMResponseCache
    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
    from comqutor_alpha.structure_engine import evidence_stance_llm as esl
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway, build_server_week2_llm_gateway

    saved_env = {k: os.environ.get(k) for k in list(REQUIRED_ENV) + ["COMQUTOR_WEEK2_LLM_MAX_CALLS", "DEEPSEEK_API_KEY", *FORBIDDEN_ENV]}
    os.environ.update({**REQUIRED_ENV, "COMQUTOR_WEEK2_LLM_MAX_CALLS": str(HARD_REQUEST_CAP), "DEEPSEEK_API_KEY": "preflight-not-a-real-key"})
    for name in FORBIDDEN_ENV:
        os.environ.pop(name, None)
    proofs: dict = {}
    try:
        for mode in ("ok", "http500"):
            sends: list[dict] = []

            def handler(request, mode=mode, sends=sends):
                body = json.loads(request.content)
                sends.append(body)
                if mode == "http500":
                    return httpx.Response(500, json={"error": {"message": "boom"}})
                prompt = body["messages"][0]["content"]
                payload = json.JSONDecoder().raw_decode(prompt[prompt.rfind('{"items"'):])[0]
                items = [{"claim_id": i["claim_id"], "target_alpha_id": i["target_alpha_id"], "stance": "mentions_alpha"} for i in payload["items"]]
                return httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 0, "model": EXPECTED_MODEL,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps({"items": items})}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})

            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                run_id = f"direction-preflight-{mode}"
                gateway = build_server_week2_llm_gateway(run_id, root, enable_request_response_audit=True, _base_transport_for_testing=httpx.MockTransport(handler))
                (root / run_id).mkdir(exist_ok=True)
                gateway.attach_semantic_runtime(SemanticRuntimeSession(run_id=run_id, output_directory=str(root / run_id), execution_mode="live",
                    provider=gateway.provider, model=gateway.model_name, cache=InMemoryLLMResponseCache()))
                effective = preflight_direction_gateway(gateway, hard_cap=HARD_REQUEST_CAP, prior_sent=0, concurrency=FROZEN_CONCURRENCY,
                                                        expected_model=EXPECTED_MODEL, expected_timeout=EXPECTED_TIMEOUT_SECONDS)
                guarded = TaskAllowlistGateway(gateway, allowed_tasks=(STANCE_TASK,))
                refused = False
                try:
                    guarded.invoke_json_with_trace("alpha_classifier", {"claim": "x"}, lambda p: p)
                except RecoveryTaskNotAllowedError:
                    refused = True
                import copy
                batch = esl.chunk_items(esl.build_stance_request_items(copy.deepcopy(plan.matches), taxonomy), esl.BATCH_SIZE)[0]
                stats = esl.StanceRunStats()
                esl._process_batch(batch, taxonomy, guarded, stats)
                req_path, resp_path = audit_paths(root, run_id)
                requests, responses = read_jsonl(req_path), read_jsonl(resp_path)
                if mode == "ok":
                    request = requests[0]
                    body = json.loads(request["body"])
                    explicit_sent = sorted(body)
                    proofs["request_shape"] = {
                        "url": request["url"], "method": request["method"], "body_keys": explicit_sent, "stream": body.get("stream"),
                        "model": body.get("model"), "message_roles": [m["role"] for m in body["messages"]], "prompt_chars": len(body["messages"][0]["content"]),
                        "wire_headers_checked": {k: v for k, v in request["headers"].items() if k.lower() in ("x-stainless-read-timeout", "x-stainless-retry-count")},
                        "wire_problem": request_wire_problem(request, expected_model=EXPECTED_MODEL, expected_timeout=EXPECTED_TIMEOUT_SECONDS),
                        "explicitly_sent_parameters": ["model", "stream=false", "messages (one user message: the production prompt + the batch items)"],
                        "client_side_explicit": {"read_timeout_seconds": 45.0, "client_max_retries": 0, "application_max_retries": 0},
                        "not_sent_so_provider_defaults_apply": ["max_tokens", "temperature", "top_p", "thinking", "reasoning_effort", "response_format", "stop"],
                    }
                    proofs["effective_gateway_config"] = effective
                    proofs["audit_mounted"] = {"request_records": len(requests), "response_records": len(responses), "task": requests[0]["task"],
                                               "claim_ids_per_request": len(requests[0]["claim_ids"]), "semantic_call_id_present": bool(requests[0]["semantic_call_id"])}
                    proofs["allowlist_refuses_classification_task"] = {"refused": refused, "requests_sent_for_it": len([r for r in requests if r["task"] != STANCE_TASK])}
                    proofs["ledger_identity"] = {"prompt_version": "evidence_stance.llm_classifier.v3", "prompt_sha256": Week2LLMGateway.prompt_identity_sha256(STANCE_TASK)}
                else:
                    proofs["zero_retries_on_http_500"] = {"requests_sent": len(sends), "audited_requests": len(requests), "stats": stats.to_dict()["fallback_reason_counts"],
                                                          "all_items_fell_back_to_deterministic": all(i.candidate.get("stance_method") == "deterministic_fallback" for i in batch)}
    finally:
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    proofs["ok"] = bool(
        proofs["request_shape"]["wire_problem"] is None
        and proofs["allowlist_refuses_classification_task"] == {"refused": True, "requests_sent_for_it": 0}
        and proofs["zero_retries_on_http_500"]["requests_sent"] == 1
        and proofs["audit_mounted"]["request_records"] == 1 and proofs["audit_mounted"]["response_records"] == 1
    )
    return proofs


def code_and_input_hashes() -> dict:
    from comqutor_alpha.alpha_library.alpha_loader import TAXONOMY_PATH
    from comqutor_alpha.classification_recovery import snapshot_directory_hashes

    files = ["comqutor_alpha/direction_evaluation.py", "comqutor_alpha/classification_recovery.py", "comqutor_alpha/structure_engine/evidence_stance_llm.py",
             "comqutor_alpha/structure_engine/evidence_stance.py", "comqutor_alpha/structure_engine/week2_llm.py", "comqutor_alpha/structure_engine/alpha_mapper.py",
             "comqutor_alpha/graph_engine/activation_scorer_v2.py", "comqutor_alpha/conflict_engine/conflict_detector.py", "comqutor_alpha/graph_engine/pipeline.py",
             "comqutor_alpha/api/routes_research.py", "comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml"]
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()
    return {
        "git_head": head,
        "note": "the working tree carries uncommitted changes (this project's rounds are uncommitted); the per-file hashes below are the real code identity",
        "code_sha256": {f: hashlib.sha256((REPO_ROOT / f).read_bytes()).hexdigest() for f in files},
        "taxonomy_file_sha256": hashlib.sha256(Path(TAXONOMY_PATH).read_bytes()).hexdigest(),
        "parent_run_files": len(snapshot_directory_hashes(PARENT_DIR)),
        "root_run_files": len(snapshot_directory_hashes(ROOT_DIR)),
    }


def run_dry_run() -> int:
    parent, manifest, manifest_path, taxonomy, plan = load_inputs()
    from comqutor_alpha.direction_evaluation import plan_signature

    result = {"zero_provider_calls": True, "root_run_id": ROOT_RUN_ID, "parent_run_id": PARENT_RUN_ID}
    result["plan_verification"] = verify_plan(plan, parent, manifest, taxonomy)
    result["frozen_plan_sha256"] = frozen_plan_sha256(plan, manifest_path)
    result["ack"] = {"env_var": ACK_ENV, "value": expected_ack(plan, manifest_path)}
    result["fake_transport_proofs"] = fake_transport_proofs(plan, taxonomy)
    result["hashes"] = code_and_input_hashes()
    result["required_environment"] = {**REQUIRED_ENV, "COMQUTOR_WEEK2_LLM_MAX_CALLS": f"<= {HARD_REQUEST_CAP} minus requests already audited",
                                      "forbidden_in_launch_shell": list(FORBIDDEN_ENV)}
    result["frozen_rules"] = {
        "authorized": "at most 17 actual Provider requests, only evidence_stance_classifier, for the 162 (claim, Alpha) pairs in the saved manifest, batches of at most 10",
        "not_authorized": "alpha_classifier, content re-verification, research agents, search, data fetch, Fresh Run; the timed-out classification claim is not retried",
        "request_config": "existing production direction-task configuration: model deepseek-v4-flash, application and client retries 0, the shared 45 s Week2 timeout, "
                          "no max_tokens / thinking / reasoning_effort / response_format sent (provider defaults), production prompt evidence_stance.llm_classifier.v3 and its schemas",
        "execution_order": "batch 0 alone (the protocol check), then the remaining 16 batches in groups of 4 (stance concurrency 4), a checkpoint after every group",
        "first_batch_gate": "no further batch is scheduled unless batch 0 produced a protocol-valid response (a valid neutral answer passes; a timeout / transport failure / unparseable response does not). Reading of 'verify the first batch, then continue'.",
        "stop_rules": {
            "local_audit_failure": "request/response audit could not be persisted", "auth_failure": "HTTP 401/403",
            "task_isolation_violation": "a task other than evidence_stance_classifier was attempted or audited",
            "identity_failure": "an audited request carries no claim ids", "config_failure": "an audited request differs from the frozen URL / body shape / model / read-timeout / retry-count",
            "call_cap_would_be_exceeded": "audited-so-far (all processes) + gateway count + the next group > 17", "first_batch_gate_failed": "see above"},
        "stop_semantics": "a stop schedules no new batch; batches in flight finish and are individually finalized; nothing is retried or re-parameterised",
        "outcomes": "a failed batch is saved as the production deterministic fallback with its real reason (never neutral, never a determined direction, never a success); "
                    "an audited-but-unsaved batch is unknown and never resent; a valid neutral is a real result and is not retried",
        "confidence": "the direction task does not ask the model for a confidence; production clears the confidence band for an LLM result, so none is reported or invented",
        "derived_run": "new direction-* execution based on the recovery run, with the original c904 run recorded as root; created only if no stop rule fired",
    }
    result["batch_layout"] = [{"batch": s["batch_index"], "pairs": len(s["pairs"])} for s in plan_signature(plan)]
    result["ok"] = bool(result["plan_verification"]["ok"] and result["fake_transport_proofs"]["ok"])
    (HERE / "preflight_result.json").write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps({k: result[k] for k in ("ok", "frozen_plan_sha256", "ack")}, indent=1))
    print("plan_verification:", json.dumps({k: v for k, v in result["plan_verification"].items() if k != "identity_mismatches"}, default=str)[:600])
    print("fake_transport_proofs ok:", result["fake_transport_proofs"]["ok"])
    print(f"wrote {HERE / 'preflight_result.json'}")
    return 0 if result["ok"] else 1


# ---------------------------------------------------------------------------
# Real execution
# ---------------------------------------------------------------------------


def execute_direction(*, plan, taxonomy, parent, gateway, output_root: Path, parent_id: str, root_id: str, execution_id: str,
                      checkpoint_origin: str, hard_cap: int, repository=None, expected_model=EXPECTED_MODEL,
                      expected_timeout=EXPECTED_TIMEOUT_SECONDS, concurrency=FROZEN_CONCURRENCY, plan_hash: str | None = None) -> dict:
    """Preflight the gateway -> run the batches -> save the per-pair results -> (if the first-batch protocol check
    passed and no stop rule fired) finalize the derived evaluation run. A stopped run keeps its checkpoint and audit
    and creates no derived run."""
    from comqutor_alpha.classification_recovery import (
        DIRECTION_EXECUTION_MODE, DIRECTION_EXECUTION_TYPE, DIRECTION_LINEAGE_FILENAME, DIRECTION_RESULTS_FILENAME,
        finalize_classification_recovery_execution)
    from comqutor_alpha.direction_evaluation import (
        audit_paths, collect_direction_results, load_checkpoint, preflight_direction_gateway, read_jsonl, run_direction_batches)
    from comqutor_alpha.storage.file_store import save_json_record

    output_root = Path(output_root)
    execution_dir = output_root / execution_id
    execution_dir.mkdir(parents=True, exist_ok=True)
    req_path, _ = audit_paths(output_root, execution_id)
    prior_sent = len(read_jsonl(req_path))
    effective = preflight_direction_gateway(gateway, hard_cap=hard_cap, prior_sent=prior_sent, concurrency=concurrency,
                                            expected_model=expected_model, expected_timeout=expected_timeout)
    outcome = run_direction_batches(
        plan, taxonomy, gateway=gateway, run_output_root=output_root, execution_id=execution_id,
        checkpoint_path=execution_dir / "checkpoint_direction.json", hard_cap=hard_cap, concurrency=concurrency,
        expected_model=expected_model, expected_timeout=expected_timeout)
    runtime = getattr(gateway, "semantic_runtime", None)
    if runtime is not None:
        runtime.finalize_manifest(complete=outcome["stop_reason"] is None)
    checkpoint = load_checkpoint(execution_dir / "checkpoint_direction.json")
    results = collect_direction_results(plan, run_output_root=output_root, execution_id=execution_id, base_run_id=parent_id,
                                        root_run_id=root_id, checkpoint=checkpoint, effective_config=effective)
    results["outcome"] = outcome
    results["plan_sha256"] = plan_hash
    if outcome["stop_reason"] is not None:
        # Kept beside the checkpoint for the report; deliberately NOT a run artifact (no derived run is created).
        (execution_dir / "direction_results_when_stopped.json").write_text(json.dumps(results, indent=2, default=str))
        return {"outcome": outcome, "results_summary": results["completion"], "finalized": None}

    save_json_record(execution_id, DIRECTION_RESULTS_FILENAME, results, output_root=output_root)
    claim_pairs: dict[str, list[dict]] = {}
    for pair in results["pairs"]:
        claim_pairs.setdefault(pair["claim_id"], []).append(pair)
    claim_sources = {}
    for claim_id, pairs in claim_pairs.items():
        claim_sources[claim_id] = ("direction_llm_result" if all(p["is_llm_result"] for p in pairs)
                                   else "direction_not_obtained_deterministic_fallback")
    payload = {**parent, "matches": plan.matches}
    finalized = finalize_classification_recovery_execution(
        parent_id, execution_id, assembled_alpha_matches=payload,
        recovery_provenance={
            "checkpoint_origin": checkpoint_origin, "claim_sources": claim_sources, "plan_sha256": plan_hash, "hard_request_cap": hard_cap,
            "effective_config": effective, "direction_outcome": outcome, "direction_completion": results["completion"],
        },
        output_root=output_root, graph_repository=repository,
        execution_type=DIRECTION_EXECUTION_TYPE, execution_mode=DIRECTION_EXECUTION_MODE, lineage_filename=DIRECTION_LINEAGE_FILENAME,
        assembled_transformation="assembled_from_direction_results", root_run_id=root_id,
        lineage_extras={"completeness": {
            "classification": "inherited verbatim from the parent run (see its recovery_lineage.json); unchanged by this execution",
            "direction": results["completion"],
            "downstream_evaluation": "recomputed by the production pipeline from the saved results; see summary / run_audit",
        }})
    return {"outcome": outcome, "results_summary": results["completion"], "finalized": finalized}


def run_real_direction(execution_id: str | None, environ=None) -> int:
    environ = os.environ if environ is None else environ
    parent, manifest, manifest_path, taxonomy, plan = load_inputs()
    given = environ.get(ACK_ENV, "")
    if not given or given != expected_ack(plan, manifest_path):
        print(f"BLOCKED: {ACK_ENV} is {'not set' if not given else 'not valid for the current frozen plan'}. This script has sent nothing.", file=sys.stderr)
        return 1
    check = verify_plan(plan, parent, manifest, taxonomy)
    if not check["ok"]:
        print("BLOCKED: the work list no longer reconciles with the manifest / real classification: " + json.dumps(check, default=str)[:600], file=sys.stderr)
        return 1

    from comqutor_alpha.direction_evaluation import audit_paths, new_direction_execution_id, read_jsonl
    from comqutor_alpha.llm_runtime.cache import InMemoryLLMResponseCache
    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
    from comqutor_alpha.storage.db.repository import build_write_repository_from_env
    from comqutor_alpha.structure_engine.week2_llm import build_server_week2_llm_gateway

    resuming = execution_id is not None
    execution_id = execution_id or new_direction_execution_id()
    execution_dir = OUTPUT_ROOT / execution_id
    if not execution_id.startswith("direction-") or execution_dir.exists() != resuming:
        print(f"BLOCKED: execution id / directory state invalid for {'resume' if resuming else 'a new run'}: {execution_dir}", file=sys.stderr)
        return 1
    if (execution_dir / "direction_lineage.json").exists():
        print("BLOCKED: this execution is already finalized", file=sys.stderr)
        return 1
    prior_sent = len(read_jsonl(audit_paths(OUTPUT_ROOT, execution_id)[0]))
    problems = environment_problems(prior_sent, environ)
    if problems:
        print("BLOCKED: environment does not match the frozen configuration:\n  - " + "\n  - ".join(problems), file=sys.stderr)
        return 1

    hashes_before = code_and_input_hashes()
    from comqutor_alpha.classification_recovery import snapshot_directory_hashes

    protected_before = {"parent": snapshot_directory_hashes(PARENT_DIR), "root": snapshot_directory_hashes(ROOT_DIR)}
    execution_dir.mkdir(parents=True, exist_ok=True)
    gateway = build_server_week2_llm_gateway(execution_id, OUTPUT_ROOT, enable_request_response_audit=True)
    if gateway is None:
        print("BLOCKED: the production gateway builder returned no gateway", file=sys.stderr)
        return 1
    gateway.attach_semantic_runtime(SemanticRuntimeSession(run_id=execution_id, output_directory=str(execution_dir), execution_mode="live",
        provider=gateway.provider, model=gateway.model_name, cache=InMemoryLLMResponseCache()))
    repository = build_write_repository_from_env(str(OUTPUT_ROOT))
    from sqlalchemy.engine import make_url

    parsed = make_url(environ["COMQUTOR_DATABASE_URL"])
    print(f"[direction] execution_id={execution_id} parent={PARENT_RUN_ID} root={ROOT_RUN_ID} prior_sent={prior_sent} cap={HARD_REQUEST_CAP}", flush=True)
    print(f"[direction] database={parsed.drivername}://{parsed.host}:{parsed.port}/{parsed.database}", flush=True)
    result = execute_direction(
        plan=plan, taxonomy=taxonomy, parent=parent, gateway=gateway, output_root=OUTPUT_ROOT, parent_id=PARENT_RUN_ID, root_id=ROOT_RUN_ID,
        execution_id=execution_id, checkpoint_origin="real", hard_cap=HARD_REQUEST_CAP, repository=repository,
        plan_hash=frozen_plan_sha256(plan, manifest_path))
    result["hashes_at_start"] = hashes_before
    result["protected_runs_unchanged"] = {
        "parent": snapshot_directory_hashes(PARENT_DIR) == protected_before["parent"],
        "root": snapshot_directory_hashes(ROOT_DIR) == protected_before["root"]}
    report = HERE / f"direction_execution_report_{execution_id}.json"
    report.write_text(json.dumps(result, indent=2, default=str))
    outcome = result["outcome"]
    print(f"[direction] stop_reason={outcome['stop_reason']} requests_audited_total={outcome['requests_audited_total']} "
          f"batch_states={outcome['batch_states']} never_scheduled={outcome['batches_never_scheduled']}")
    print(f"[direction] completion={json.dumps(result['results_summary'])}")
    print(f"[direction] report: {report}")
    if result["finalized"] is None:
        print("[direction] STOPPED before finalization; no derived run was created. Failed / unknown batches are never auto-resent.", file=sys.stderr)
        return 2
    print(f"[direction] derived run: {result['finalized']}")
    return 0 if result["finalized"].get("status") == "ok" else 3


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true", help=f"real run; refused unless {ACK_ENV} matches the frozen plan")
    parser.add_argument("--execution-id", default=None, help="resume an existing direction-* execution (with --execute)")
    args = parser.parse_args()
    if args.execute:
        sys.exit(run_real_direction(args.execution_id, environ=_LAUNCH_ENV))
    sys.exit(run_dry_run())
