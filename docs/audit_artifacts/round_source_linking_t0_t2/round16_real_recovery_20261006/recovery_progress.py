#!/usr/bin/env python3
"""Read-only progress report for a running / finished recovery execution.

Counts come from the REAL request/response audit log (never a fixed stage percentage):
  requests_sent           audited requests (each reached the transport; failed ones count)
  responses_saved         audited responses
  completed_select        valid response selecting an Alpha
  completed_none          valid NONE (a completed classification)
  failed                  a response was saved but is not a valid classification
  unknown_inflight        request audited, no response saved (never auto-resent)
  cache_served_or_unsent  planned claims with no audited request yet
Usage: recovery_progress.py [execution_id]   (default: the newest outputs/runs/recovery-* directory)
"""
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
SCRIPT = REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round12_alpha_classifier_audit_fix_20261006/recover_alpha_classification.py"
spec = importlib.util.spec_from_file_location("recover_progress_view", SCRIPT)
recover = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recover)

runs = recover.OUTPUT_ROOT
if len(sys.argv) > 1:
    execution_id = sys.argv[1]
else:
    candidates = sorted((p for p in runs.glob("recovery-*") if p.is_dir()), key=lambda p: p.stat().st_mtime)
    if not candidates:
        print(json.dumps({"error": "no recovery-* execution directory yet"}))
        sys.exit(0)
    execution_id = candidates[-1].name

from comqutor_alpha.structure_engine.week2_llm import PROVIDER_REQUEST_AUDIT_ARTIFACT_PATH, PROVIDER_RESPONSE_AUDIT_ARTIFACT_PATH


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


execution_dir = runs / execution_id
requests = read(execution_dir / PROVIDER_REQUEST_AUDIT_ARTIFACT_PATH)
responses = read(execution_dir / PROVIDER_RESPONSE_AUDIT_ARTIFACT_PATH)
states = recover.reconcile_claim_states_from_audit_log(runs, execution_id)
states.pop("__multi_attempt_warnings__", None)
plan_ids = [cid for stage in recover.build_recovery_plan() for cid in stage["claim_ids"]]
by_state = Counter()
for cid in plan_ids:
    info = states.get(cid)
    if info is None:
        by_state["cache_served_or_unsent"] += 1
    elif info["state"] == "success":
        by_state["completed_select" if info["decision"].get("decision") == "select" else "completed_none"] += 1
    else:
        by_state[info["state"]] += 1
usage = Counter()
for record in responses:
    try:
        u = json.loads(record["body"]).get("usage") or {}
    except Exception:
        continue
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        usage[key] += int(u.get(key) or 0)
statuses = Counter(str(r.get("status_code")) for r in responses)
tasks = Counter(str(r.get("task")) for r in requests)
checkpoint = execution_dir / "checkpoint_recovery.json"
report = {
    "execution_id": execution_id,
    "requests_sent": len(requests),
    "responses_saved": len(responses),
    "request_cap": recover.HARD_REQUEST_CAP,
    "requests_remaining_under_cap": recover.HARD_REQUEST_CAP - len(requests),
    "planned_claims": len(plan_ids),
    **{k: by_state.get(k, 0) for k in ("completed_select", "completed_none", "failed", "unknown_inflight", "cache_served_or_unsent")},
    "http_status_codes": dict(statuses),
    "request_tasks": dict(tasks),
    "usage_tokens": dict(usage),
    "checkpoint_completed": len(json.loads(checkpoint.read_text()).get("completed_claim_ids", {})) if checkpoint.exists() else 0,
    "finalized": (execution_dir / "recovery_lineage.json").exists(),
}
print(json.dumps(report))
