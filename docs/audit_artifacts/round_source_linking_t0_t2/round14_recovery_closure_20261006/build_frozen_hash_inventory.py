#!/usr/bin/env python3
"""Frozen-hash change inventory (round 14, section 2).

Keeps every OLD pin exactly as the tests have it (this script reads them, it
never edits a test or a pinned value) and adds what the pins cannot say:
  * for each pinned file: pinned hash, HEAD blob hash, current hash,
    working-tree mtime, and whether the AMD classification/audit repair
    thread (assistant edits on 2026-10-06 from 12:58 local) touched it;
  * which tests pin it and what each pin comparison yields;
  * the repair thread's own change list with its verification evidence.

This is a technical change inventory. It is NOT a re-approval by John or any
human, and it does not claim the pinned baselines have been re-certified.
"""
import hashlib, json, os, subprocess, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
OUT = Path(__file__).parent / "frozen_hash_change_inventory.json"
TRANSCRIPT_EDITS = Path(os.environ.get("ASSISTANT_EDITS_JSON", ""))

PINS = {  # file -> [(test group, pinned sha256)]
    "comqutor_alpha/structure_engine/alpha_mapper.py": [("evidence_review_v2::case17, high_value_unclassified::case10, step10, step11, msft_a102::a6, shadow::source_integrity", "506a228eb10e0b77b2058c9eaa327ae0ec44ba36b1515e5e6400187ffe65a6fd")],
    "comqutor_alpha/structure_engine/week2_llm.py": [("shadow::source_integrity", "5c9106a3e51c63ffbff957c2dee6778442cc503fb00eccba049f35e7669569b1")],
    "comqutor_alpha/structure_engine/structured_output_adapter.py": [("shadow::source_integrity", "9e6995707bfa8ce4975eb58f5bb4b4fa6100a2bdbf8b50b5b4ad97c200215a3c")],
    "comqutor_alpha/structure_engine/structure_extractor.py": [("shadow::source_integrity", "5254cdf157c7d5ed88a7b06db34a9f0e3104259dde4fe5c52ecd922710fec416")],
    "comqutor_alpha/structure_engine/evidence_stance.py": [("evidence_review_v2::case17", "9ae3aaeb14b453672445eeb6db6dccc6f526e3bc84bfec2776625436c27e14a6")],
    "comqutor_alpha/structure_engine/evidence_stance_llm.py": [("evidence_review_v2::case17", "282577a54c97e1bd8d962eb793f41baf2cf30930ba0ce178000834eed3307a58")],
    "comqutor_alpha/graph_engine/activation_scorer_v2.py": [("evidence_review_v2::case17, step10, step11", "c1b0a479a1d06c94811004c2ea62d95598427ea4541e0f770a5d4633e642911e")],
    "comqutor_alpha/conflict_engine/conflict_detector.py": [("evidence_review_v2::case17, step10, step11, msft_a102::a6", "f07604bc61a713f7ed3db4cb4db5b6ae9091487cf83c85e40b68696f9c3874da")],
    "comqutor_alpha/graph_engine/alpha_level_classifier.py": [("evidence_review_v2::case17, step10, step11", "3cf25b42cbc91d8976978d89c45cbab45859accd37c6a8f8731ff42eabb1da85")],
    "comqutor_alpha/graph_engine/evidence_source_role.py": [("evidence_review_v2::case17, step10, step11", "4835e4e2d83b8438bf23d1a9c35123072439d5f501146b77d8d038585d47ae99")],
    "comqutor_alpha/graph_engine/alpha_display_normalizer.py": [("evidence_review_v2::case17, step10, step11", "f63cb9d63a157ab2d817d66d071b94f6b967809d871bc3bb067a2afa9d7ebeea")],
    "comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml": [
        ("evidence_review_v2::case17, high_value_unclassified::case10, step10, step11", "c031168c726cd424252cd9ee0491e55f335b5966694a326e0bcdfeeab1e7939c"),
        ("msft_a102::a6", "18a0dc6b5de7bbae3541272fbd66fa1172e62eed172fd86e97a72e1a40d90972"),
    ],
    "comqutor_alpha/conflict_engine/conflict_schema.py": [("msft_a102::a6", "58466213a20810a062d98551866d4e4895f97771792ccaf6d08991655f28969e")],
    "comqutor_alpha/conflict_engine/conflict_admissibility.py": [("msft_a102::a6", "0b795d4b2ee36fe11496b6766a83196b81d8afaec6c83f15cae2dbd0699b1f41")],
}
HEAD_PIN_TEST = {"test_j3_semantic_benchmark_j2_v0_2.py::test_e42": "b5837e80a4550fc35165d0013a8ef0f27ccb4c8f"}

REPAIR_THREAD_CHANGES = [
    {"round": 11, "files": ["comqutor_alpha/structure_engine/week2_llm.py"],
     "change": "Shared _audited_http_client_kwarg(): the default client AND every per-task override client (alpha_classifier, content_support_verification) now route through AuditingTransport (overrides previously bypassed audit entirely).",
     "evidence": ["tests/test_alpha_classifier_audit_concurrency_fix.py::test_alpha_classifier_override_client_is_audited", "::test_content_support_override_client_is_still_audited_after_refactor"]},
    {"round": 13, "files": ["comqutor_alpha/structure_engine/week2_llm.py", "comqutor_alpha/structure_engine/alpha_mapper.py", "comqutor_alpha/structure_engine/structured_output_adapter.py"],
     "change": "Per-attempt audit identity via contextvars (explicitly propagated across call_with_timeout's worker thread) replacing the single shared pending-attempt dict; audit-JSONL writes serialized under the Gateway lock (read-modify-write race lost 5 of 8 records); the round-11 forced-serial concurrency shims removed from alpha_mapper and structured_output_adapter.",
     "evidence": ["tests/test_week2_llm_true_concurrent_audit.py (8 tests)", "tests/test_alpha_classifier_audit_concurrency_fix.py (4 tests)", "full 973-claim fake-HTTP recovery at concurrency=4"]},
    {"round": 14, "files": ["comqutor_alpha/structure_engine/week2_llm.py", "comqutor_alpha/structure_engine/alpha_mapper.py", "comqutor_alpha/llm_runtime/session.py", "comqutor_alpha/llm_runtime/contracts.py"],
     "change": "Out-of-band claim_id -> semantic_call_id -> attempt_id -> request/response identity chain (explicit claim_ids= keyword on invoke_json_with_trace/start_call, stored on the trace; optional claim_ids on semantic records; optional cache.source_call_id / cache-entry source_call_id). Nothing added to the model payload, prompt, or cache key.",
     "evidence": ["tests/test_claim_identity_traceability.py::test_claim_ids_never_change_the_real_request_body (byte-identical request body)", "capture_effective_request_config.py: prompt identity and both original request-input hashes unchanged vs the original real calls", "tests/llm_runtime/* unchanged and passing"]},
    {"round": 14, "files": ["comqutor_alpha/structure_engine/alpha_mapper.py", "comqutor_alpha/api/routes_research.py"],
     "change": "Read-only classification-completion disclosure (valid select / valid NONE / call failure / not executed), shared 4-state status in the API response and run summary; 'audit_unavailable' fallback reason for Gateway audit refusals (previously mislabeled 'invalid_output').",
     "evidence": ["tests/test_alpha_classification_completion.py", "tests/test_recovery_downstream_zero_model_calls.py"]},
]


# Which (file, pinned-hash-group) each pin TEST compares, read from the tests themselves.
TAX_A = "c031168c726cd424252cd9ee0491e55f335b5966694a326e0bcdfeeab1e7939c"
TAX_B = "18a0dc6b5de7bbae3541272fbd66fa1172e62eed172fd86e97a72e1a40d90972"
PIN_TESTS = {
    "test_step10_final_e2e_qa.py::test_production_semantic_files_unchanged_during_step10": ["alpha_mapper.py", "activation_scorer_v2.py", "conflict_detector.py", "alpha_level_classifier.py", "evidence_source_role.py", "alpha_display_normalizer.py", ("alpha_taxonomy_v1.yaml", TAX_A)],
    "test_step11_provider_health_rerun.py::test_production_semantic_files_unchanged_during_step11": ["alpha_mapper.py", "activation_scorer_v2.py", "conflict_detector.py", "alpha_level_classifier.py", "evidence_source_role.py", "alpha_display_normalizer.py", ("alpha_taxonomy_v1.yaml", TAX_A)],
    "test_high_value_unclassified_recovery.py::test_case10_production_semantic_artifacts_are_not_modified": ["alpha_mapper.py", ("alpha_taxonomy_v1.yaml", TAX_A)],
    "test_msft_a102_a304_taxonomy_adjudication.py::TestSectionAAllOutcomes::test_a6_b1_b2_b3_b4_invariant_modules_are_byte_identical": [("alpha_taxonomy_v1.yaml", TAX_B), "alpha_mapper.py", "conflict_schema.py", "conflict_admissibility.py", "conflict_detector.py"],
    "structured_output_shadow/test_source_integrity.py::test_current_semantic_components_match_approved_phase1_master_baseline": ["structured_output_adapter.py", "week2_llm.py", "alpha_mapper.py", "structure_extractor.py"],
    "test_evidence_review_v2.py::test_case17[alpha_mapper.py]": ["alpha_mapper.py"],
    "test_evidence_review_v2.py::test_case17[evidence_stance_llm.py]": ["evidence_stance_llm.py"],
    "test_evidence_review_v2.py::test_case17[alpha_taxonomy_v1.yaml]": [("alpha_taxonomy_v1.yaml", TAX_A)],
    "test_evidence_review_v2.py::test_case17[conflict_detector.py]": ["conflict_detector.py"],
    "test_evidence_review_v2.py::test_case17[activation_scorer_v2.py]": ["activation_scorer_v2.py"],
}


def per_test_verdicts(files):
    by_name = {}
    for f, info in files.items():
        by_name.setdefault(f.split("/")[-1], []).append((f, info))
    out = {}
    for test, entries in PIN_TESTS.items():
        rows = []
        for entry in entries:
            name, want = (entry, None) if isinstance(entry, str) else entry
            f, info = by_name[name][0]
            pin = next(p for p in info["pins"] if want is None or p["pinned_sha256"] == want)
            pre_hash = info.get("pre_repair_thread_sha256_recorded")
            rows.append({
                "file": f, "thread_edited": info["edited_by_repair_thread_(from_2026-10-06_12:58)"] or pre_hash is not None,
                "pin_matches_current": pin["pin_equals_current"], "pin_matches_head_blob": pin["pin_equals_head_blob"],
                # Strongest evidence available: did the pin already fail against the RECORDED
                # state immediately before the repair thread touched the file?
                "pin_matches_recorded_pre_thread_state": (pin["pinned_sha256"] == pre_hash) if pre_hash else None,
            })
        mismatching = [r for r in rows if not r["pin_matches_current"]]
        # Would this test still fail if the repair thread's own files matched their pins?
        # A thread-edited file's pin "already failed before the thread" when it does not match the recorded
        # pre-thread state (or, where none was recorded, the committed HEAD blob).
        still_fails_without_thread = [
            r for r in mismatching
            if (not r["thread_edited"])
            or (r["pin_matches_recorded_pre_thread_state"] is False)
            or (r["pin_matches_recorded_pre_thread_state"] is None and not r["pin_matches_head_blob"])
        ]
        out[test] = {
            "compares": rows,
            "mismatching_now": [r["file"] for r in mismatching],
            "of_which_edited_by_repair_thread": [r["file"] for r in mismatching if r["thread_edited"]],
            "fails_even_at_committed_HEAD_or_on_files_the_thread_never_edited": [r["file"] for r in still_fails_without_thread],
            "verdict": (
                "would STILL fail with the repair thread's edits removed (pin already unmet at HEAD, or mismatch is on a file the thread did not edit)"
                if still_fails_without_thread else
                "fails ONLY because of repair-thread edits"
            ),
        }
    return out


# Recorded pre-repair-thread states (Claude Code file-history backups taken
# before the thread's first edit to each file; each verified by diffing
# against the next recorded version -- the delta is exactly the thread's own
# edits). structured_output_adapter.py has no cleanly isolated pre-thread
# snapshot (its one thread edit was a comment + a since-removed concurrency
# override, made between two other recorded versions), so it is listed as
# not recorded rather than reconstructed.
FH = Path.home() / ".claude/file-history/8d38fcbd-98ee-4ff6-b804-8855e3f6b189"
PRE_THREAD_BACKUPS = {
    "comqutor_alpha/structure_engine/alpha_mapper.py": FH / "60ccb681d0ed547b@v6",
    "comqutor_alpha/structure_engine/week2_llm.py": FH / "3bf6612f604a7651@v17",
    "comqutor_alpha/llm_runtime/contracts.py": FH / "7dcb1eacbb377004@v5",
    "comqutor_alpha/llm_runtime/session.py": FH / "c6d1ccde9b659efc@v3",
    "comqutor_alpha/api/routes_research.py": FH / "6997f2f4f1787e8e@v11",
}


def sha(b): return hashlib.sha256(b).hexdigest()


def head_blob(path):
    p = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=REPO, capture_output=True)
    return sha(p.stdout) if p.returncode == 0 else None


def edit_dates():
    if not TRANSCRIPT_EDITS.exists():
        return {}
    import collections, datetime
    d = json.loads(TRANSCRIPT_EDITS.read_text())
    by = collections.defaultdict(list)
    for ts, _tool, path in d["edits"]:
        if path:
            by[path.replace(str(REPO) + "/", "")].append(
                (datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")) - datetime.timedelta(hours=7)).replace(tzinfo=None))
    return by


def main():
    edits = edit_dates()
    thread_start = __import__("datetime").datetime(2026, 10, 6, 12, 58)
    files = {}
    for f, groups in PINS.items():
        cur = sha((REPO / f).read_bytes()); hd = head_blob(f)
        times = sorted(edits.get(f, []))
        touched_by_thread = [t.strftime("%m-%d %H:%M") for t in times if t >= thread_start]
        pre = PRE_THREAD_BACKUPS.get(f)
        pre_hash = sha(pre.read_bytes()) if pre is not None and pre.exists() else None
        files[f] = {
            "current_sha256": cur, "head_blob_sha256": hd,
            "pre_repair_thread_sha256_recorded": pre_hash,
            "pre_repair_thread_snapshot": (
                f"claude-file-history {pre.name}" if pre_hash else
                ("not recorded (no cleanly isolated snapshot)" if f.endswith("structured_output_adapter.py") else "n/a: not edited by the repair thread")
            ),
            "mtime_local": time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(REPO / f))),
            "last_assistant_edit_local": times[-1].strftime("%Y-%m-%d %H:%M") if times else None,
            "edited_by_repair_thread_(from_2026-10-06_12:58)": bool(touched_by_thread) or f in PRE_THREAD_BACKUPS or f.endswith("structured_output_adapter.py"),
            "repair_thread_edit_count": len(touched_by_thread),
            "pins": [{"tests": g, "pinned_sha256": h, "pin_equals_head_blob": h == hd, "pin_equals_current": h == cur} for g, h in groups],
        }
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    report = {
        "statement": "Old pins are untouched and still enforced. This inventory is a technical record only; it is NOT a re-approval by John or any human reviewer.",
        "git_head": head,
        "head_pin_tests": {k: {"hardcoded_head": v, "actual_head": head, "matches": v == head} for k, v in HEAD_PIN_TEST.items()},
        "pinned_files": files,
        "per_test_verdicts": per_test_verdicts(files),
        "repair_thread_changes": REPAIR_THREAD_CHANGES,
        "internal_contradictions_in_existing_pins": [
            "alpha_taxonomy_v1.yaml is pinned to c031168c... by evidence_review_v2::case17 / high_value_unclassified::case10 / step10 / step11 but to 18a0dc6b... by msft_a102::a6 -- both groups cannot pass at once, in any working-tree state.",
        ],
    }
    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk in ("edited_by_repair_thread_(from_2026-10-06_12:58)", "pins")} for k, v in files.items()}, indent=1)[:2500])
    print("written:", OUT)


if __name__ == "__main__":
    main()
