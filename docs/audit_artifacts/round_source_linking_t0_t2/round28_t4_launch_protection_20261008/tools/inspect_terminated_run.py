#!/usr/bin/env python3
"""T4 round 28: what a terminated run (job timeout / worker killed) kept, and a ZERO-CALL rebuild of its completed
Alpha results through the real stage code. The original run directory is only read.

Inventory (from the files only):
  * completed   -- semantic-ledger records accepted with a validated output whose sha256 matches (per call, appended at
                   the moment each call finished; a half-written last line fails to parse or fails its hash and is
                   reported, never used);
  * failed      -- ledger records with a provider error / timeout / rejected output;
  * not sent    -- ledger records refused before sending (budget exhausted, provider stop, input too large);
  * in flight   -- request-audit rows (written before forwarding) with no response row and no ledger record: sent,
                   outcome unknown (possibly billed) -- never re-sent;
  * never reached -- claims of structured_agent_outputs.json with no ledger record and no audit row.

Rebuild: a scratch copy of the run directory (the original ledger is set aside there as *.original), an
InMemoryLLMResponseCache seeded ONLY with the completed ledger records (contracts.cache_entry_from_record -- the
same entry a live run caches), a real Week2LLMGateway whose budget is already spent (a miss is refused unsent) and
whose model raises if ever invoked, and the production ``save_alpha_matches``. Completed claims come back from the
cache; every other claim stays unavailable (never NONE). The rebuilt file is a PARTIAL stage result, labelled so.

    python run_with_network_trap.py inspect_terminated_run.py --run-dir <run dir> --rebuild-root <new dir> --out <json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
sys.path.insert(0, str(REPO))

NOT_SENT_STATUSES = {"budget_exhausted", "not_called"}


def _canonical_sha(value) -> str:
    from comqutor_alpha.llm_runtime.canonical_json import sha256_canonical_json

    return sha256_canonical_json(value)


def _read_jsonl(path: Path) -> tuple[list[dict], list[int]]:
    rows, bad = [], []
    if not path.is_file():
        return rows, bad
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except ValueError:
            bad.append(number)
            continue
        if isinstance(value, dict):
            rows.append(value)
        else:
            bad.append(number)
    return rows, bad


def inventory(run_dir: Path) -> dict:
    ledger, bad_lines = _read_jsonl(run_dir / "llm_semantic_calls.jsonl")
    requests, bad_req = _read_jsonl(run_dir / "error_logs" / "week2_llm_provider_request_audit.jsonl")
    responses, bad_resp = _read_jsonl(run_dir / "error_logs" / "week2_llm_provider_response_audit.jsonl")
    classified: dict[str, list] = {"completed": [], "failed": [], "not_sent": [], "served_from_cache": [], "hash_mismatch": []}
    ledger_attempts = set()
    for r in ledger:
        for a in r.get("request_attempts") or []:
            if a.get("attempt_id"):
                ledger_attempts.add(a["attempt_id"])
        item = {"task": r.get("task"), "call_id": r.get("call_id"), "claim_ids": r.get("claim_ids"), "input_sha256": r.get("input_sha256"),
                "prompt_sha256": r.get("prompt_sha256"), "provider_status": r.get("provider_status"), "validation_status": r.get("validation_status"),
                "error_code": r.get("error_code"), "validated_output": r.get("validated_output")}
        if r.get("validated_output") is not None and _canonical_sha(r["validated_output"]) != r.get("validated_output_sha256"):
            classified["hash_mismatch"].append(item)
        elif (r.get("cache") or {}).get("hit"):
            classified["served_from_cache"].append(item)
        elif r.get("validation_status") == "accepted" and r.get("provider_status") == "success" and r.get("validated_output") is not None:
            classified["completed"].append(item)
        elif r.get("provider_status") in NOT_SENT_STATUSES and not r.get("request_attempts"):
            classified["not_sent"].append(item)
        else:
            classified["failed"].append(item)
    answered = {r.get("attempt_id") for r in responses}
    in_flight = [{"attempt_id": r.get("attempt_id"), "task": r.get("task"), "claim_ids": r.get("claim_ids"), "sent_at": r.get("created_at"),
                  "body_sha256": r.get("body_sha256")}
                 for r in requests if r.get("attempt_id") not in answered and r.get("attempt_id") not in ledger_attempts]
    claims: list[str] = []
    structured_path = run_dir / "structured_agent_outputs.json"
    if structured_path.is_file():
        structured = json.loads(structured_path.read_text(encoding="utf-8"))
        claims = [r["claim_id"] for r in structured.get("records") or [] if isinstance(r, dict) and r.get("claim_id")]
    touched = {c for r in ledger if r.get("task") == "alpha_classifier" for c in (r.get("claim_ids") or [])}
    touched |= {c for r in requests if r.get("task") == "alpha_classifier" for c in (r.get("claim_ids") or [])}
    never_reached = [c for c in claims if c not in touched]
    stage_artifacts = {name: (run_dir / name).is_file() for name in ("raw_agent_outputs.json", "structured_agent_outputs.json", "alpha_matches.json",
                                                                       "extracted_structures.json", "evidence_stance_audit.json", "structure_graph.json",
                                                                       "artifact_manifest.json", "llm_usage_report.json")}
    return {
        "run_dir": str(run_dir),
        "stage_artifacts_present": stage_artifacts,
        "ledger": {"records": len(ledger), "unparseable_lines": bad_lines,
                   "by_category": {k: len(v) for k, v in classified.items()},
                   "by_task_and_category": dict(Counter(f"{i['task']}:{k}" for k, v in classified.items() for i in v))},
        "audit": {"requests": len(requests), "responses": len(responses), "unparseable_request_lines": bad_req, "unparseable_response_lines": bad_resp},
        "completed": classified["completed"],
        "failed": classified["failed"],
        "not_sent": classified["not_sent"],
        "in_flight_unknown": in_flight,
        "alpha_claims_total": len(claims),
        "alpha_claims_never_reached": never_reached,
    }


class _NeverSendModel:
    calls = 0

    def invoke(self, prompt):
        _NeverSendModel.calls += 1
        raise RuntimeError("REBUILD_ZERO_CALL: a request was about to be made")


def _rebuild_setup(run_dir: Path, rebuild_root: Path):
    """Scratch copy, ledger-seeded cache, and a real gateway that cannot send (budget spent; model raises)."""
    from comqutor_alpha.llm_runtime.cache import InMemoryLLMResponseCache
    from comqutor_alpha.llm_runtime.contracts import cache_entry_from_record
    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

    run_id = run_dir.name
    target = rebuild_root / run_id
    shutil.copytree(run_dir, target)
    original_ledger = target / "llm_semantic_calls.jsonl"
    if original_ledger.is_file():
        original_ledger.rename(target / "llm_semantic_calls.original.jsonl")
    ledger, _ = _read_jsonl(target / "llm_semantic_calls.original.jsonl")
    cache = InMemoryLLMResponseCache()
    seeded = 0
    for record in ledger:
        if record.get("validation_status") == "accepted" and record.get("provider_status") == "success" and record.get("validated_output") is not None \
                and not (record.get("cache") or {}).get("hit") and _canonical_sha(record["validated_output"]) == record.get("validated_output_sha256"):
            entry = cache_entry_from_record(record, created_at=record["completed_at"], source_run_id=run_id)
            cache.put(record["cache"]["cache_key"], entry)
            seeded += 1
    provider = next((r.get("provider") for r in ledger if r.get("provider")), "deepseek")
    model = next((r.get("model") for r in ledger if r.get("model")), "deepseek-v4-flash")
    gateway = Week2LLMGateway(_NeverSendModel(), run_id=run_id, output_root=str(rebuild_root), max_calls=1, provider=provider, model_name=model)
    gateway._call_count = gateway.max_calls  # budget already spent: a cache miss is refused unsent
    session = SemanticRuntimeSession(run_id=run_id, output_directory=target, execution_mode="live", provider=provider, model=model, cache=cache)
    gateway.attach_semantic_runtime(session)
    return run_id, target, gateway, session, seeded


def rebuild_structured_adapter(run_dir: Path, rebuild_root: Path, inv: dict) -> dict:
    """The structured-adapter stage (claim extraction / enrichment / content support), whose stage file
    structured_agent_outputs.json is only written when the whole stage ends."""
    from comqutor_alpha.structure_engine.structured_output_adapter import save_structured_agent_outputs

    run_id, target, gateway, session, seeded = _rebuild_setup(run_dir, rebuild_root)
    save_structured_agent_outputs(target, llm_gateway=gateway)
    session.finalize_manifest(complete=False)
    (target / "structured_agent_outputs.REBUILD_NOTE.json").write_text(json.dumps(
        {"partial_rebuild": True, "basis": "zero-call rebuild of a terminated run from its own semantic ledger; NOT a complete stage result",
         "source_run_dir": str(run_dir)}, indent=1) + "\n", encoding="utf-8")
    records = json.loads((target / "structured_agent_outputs.json").read_text(encoding="utf-8")).get("records") or []
    by_claim = {r.get("claim_id"): r for r in records}
    expected = {}
    for item in inv["completed"]:
        if item["task"] == "content_support_verification":
            for answer in (item["validated_output"] or {}).get("items") or []:
                expected[answer.get("claim_id")] = answer.get("status")
    comparison = [{"claim_id": cid, "ledger_status": status,
                   "rebuilt_llm_status": ((by_claim.get(cid) or {}).get("content_support_llm_detail") or {}).get("llm_status"),
                   "agrees": ((by_claim.get(cid) or {}).get("content_support_llm_detail") or {}).get("llm_status") == status}
                  for cid, status in expected.items()]
    others = [r for r in records if r.get("claim_id") not in expected]
    return {
        "stage": "structured_adapter (content support)",
        "rebuild_dir": str(target),
        "cache_entries_seeded": seeded,
        "model_invocations": _NeverSendModel.calls,
        "records": len(records),
        "completed_claims_compared": comparison,
        "all_completed_claims_agree": bool(comparison) and all(c["agrees"] for c in comparison),
        "other_records_with_an_llm_verdict": sum(1 for r in others if r.get("content_support_llm_detail")),
        "other_records_fallback_reasons": dict(Counter(str(r.get("content_support_llm_fallback_reason")) for r in others)),
        "rebuilt_file_sha256": hashlib.sha256((target / "structured_agent_outputs.json").read_bytes()).hexdigest(),
        "label": "PARTIAL zero-call rebuild; claims without a completed ledger verdict stay unverified",
    }


def rebuild_alpha(run_dir: Path, rebuild_root: Path, inv: dict) -> dict:
    from comqutor_alpha.structure_engine.alpha_mapper import compute_alpha_classification_completion, save_alpha_matches

    run_id, target, gateway, session, seeded = _rebuild_setup(run_dir, rebuild_root)
    payload = save_alpha_matches(run_id, output_root=str(rebuild_root), llm_gateway=gateway)
    session.finalize_manifest(complete=False)
    marker = {"partial_rebuild": True, "basis": "zero-call rebuild of a terminated run from its own semantic ledger; NOT a complete stage result",
              "source_run_dir": str(run_dir)}
    (target / "alpha_matches.REBUILD_NOTE.json").write_text(json.dumps(marker, indent=1) + "\n", encoding="utf-8")
    matches = payload.get("matches") or []
    completed_by_claim = {tuple(i["claim_ids"] or ()): i["validated_output"] for i in inv["completed"] if i["task"] == "alpha_classifier"}
    comparison = []
    for m in matches:
        expected = completed_by_claim.get((m.get("claim_id"),))
        if expected is None:
            continue
        expected_alpha = expected.get("selected_alpha_id") if expected.get("decision") == "select" else None
        comparison.append({"claim_id": m.get("claim_id"), "ledger_decision": expected, "rebuilt_method": m.get("alpha_match_method"),
                           "rebuilt_llm_selected_alpha_id": m.get("llm_selected_alpha_id"), "rebuilt_fallback_reason": m.get("alpha_match_fallback_reason"),
                           "agrees": m.get("alpha_match_method") == "llm" and m.get("alpha_match_fallback_reason") is None
                           and (m.get("llm_selected_alpha_id") or None) == expected_alpha})
    unavailable = [m for m in matches if (m.get("claim_id"),) not in completed_by_claim]
    return {
        "rebuild_dir": str(target),
        "cache_entries_seeded": seeded,
        "model_invocations": _NeverSendModel.calls,
        "matches": len(matches),
        "completed_claims_compared": comparison,
        "all_completed_claims_agree": bool(comparison) and all(c["agrees"] for c in comparison),
        "other_claims": dict(Counter(f"{m.get('alpha_match_method')}|{m.get('alpha_match_fallback_reason')}" for m in unavailable)),
        "other_claims_never_valid_none": all(not (m.get("alpha_match_method") == "llm" and m.get("alpha_match_fallback_reason") is None) for m in unavailable),
        "completion": compute_alpha_classification_completion(payload),
        "rebuilt_file_sha256": hashlib.sha256((target / "alpha_matches.json").read_bytes()).hexdigest(),
        "label": "PARTIAL zero-call rebuild; the scratch ledger records the cache hits and the refused misses",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--rebuild-root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--stage", choices=("alpha", "structured_adapter"), default="alpha")
    ap.add_argument("--profile", help="Week 2 execution profile the run used (default: metadata.run_environment of the run)")
    args = ap.parse_args(argv)
    run_dir, rebuild_root = Path(args.run_dir), Path(args.rebuild_root)
    # The rebuild must build the same requests as the run did (same batch sizes, same per-task settings), or the ledger-seeded
    # cache cannot match: the run's own recorded execution profile is used.
    import os

    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8")) if (run_dir / "metadata.json").is_file() else {}
    recorded = (((metadata.get("run_environment") or {}).get("effective_config") or {}).get("week2_semantic") or {}).get("execution_profile")
    profile = args.profile or recorded
    for name in ("COMQUTOR_WEEK2_CONTENT_SUPPORT_BATCH_SIZE", "COMQUTOR_WEEK2_LLM_PROFILE"):
        os.environ.pop(name, None)
    if profile:
        os.environ["COMQUTOR_WEEK2_LLM_PROFILE"] = profile
    if rebuild_root.exists():
        print("refusing: rebuild root exists", file=sys.stderr)
        return 2
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in run_dir.rglob("*") if p.is_file()}
    inv = inventory(run_dir)
    rebuild_root.mkdir(parents=True)
    rebuilt = (rebuild_structured_adapter if args.stage == "structured_adapter" else rebuild_alpha)(run_dir, rebuild_root, inv)
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in run_dir.rglob("*") if p.is_file()}
    report = {"inventory": inv, "zero_call_rebuild": rebuilt, "execution_profile_used_for_rebuild": profile,
              "profile_source": "argument" if args.profile else ("metadata.run_environment" if recorded else None),
              "original_run_dir_unchanged": before == after}
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"by_category": inv["ledger"]["by_category"], "in_flight_unknown": len(inv["in_flight_unknown"]),
                      "never_reached": len(inv["alpha_claims_never_reached"]), "stage_artifacts_present": inv["stage_artifacts_present"],
                      "rebuild": {k: rebuilt.get(k) for k in ("stage", "cache_entries_seeded", "model_invocations", "all_completed_claims_agree",
                                                              "other_claims", "other_claims_never_valid_none", "other_records_with_an_llm_verdict",
                                                              "other_records_fallback_reasons")},
                      "original_run_dir_unchanged": report["original_run_dir_unchanged"]}, indent=1, default=str))
    return 0 if rebuilt["all_completed_claims_agree"] and rebuilt["model_invocations"] == 0 and report["original_run_dir_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
