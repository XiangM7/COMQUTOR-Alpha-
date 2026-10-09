#!/usr/bin/env python3
"""2026-10-06 (round 13, scenario 8): drives
recover_alpha_classification.run_full_fake_transport_recovery against the
REAL, FULL 973-claim needs_recovery set from the frozen c904d4cc run, with
genuine concurrency=4, in two phases:

Phase 1: processes the first 3 batches (75 claims), then deliberately
raises a simulated crash -- proving the checkpoint survives an abrupt stop
mid-run.

Phase 2: calls the SAME function again, same checkpoint/send-count files,
with no crash this time, running to full completion.

Verifies, from the real on-disk artifacts only (batches_submitted.jsonl,
the real request-audit JSONL, checkpoint_full.json) -- not from in-process
state that could hide a bug:
  - every one of the 973 needs-recovery claims was SUBMITTED to
    map_structured_records EXACTLY once total across both phases (never
    zero, never more than one -- proving checkpoint-based resume does not
    re-send already-checkpointed claims under genuine concurrency)
  - real Provider-transport sends are <= 973 (the Gateway's own semantic
    cache legitimately reduces this when genuine duplicate-content claims
    exist -- confirmed real, not treated as a bug) and never exceed it
  - the checkpoint's own completed_claim_ids reaches all 973
  - merging the 973 recovered + the 2 already-valid originals produces
    exactly 975 unique claim_ids with zero duplicates and zero omissions
    against the original run's own 975-claim structured_agent_outputs.json

Zero real Provider calls (httpx.MockTransport throughout). Reads the
original c904d4cc run read-only; writes only under its own scratch dir.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROUND12_DIR = Path(__file__).resolve().parents[1] / "round12_alpha_classifier_audit_fix_20261006"
sys.path.insert(0, str(ROUND12_DIR))

SCRATCH_DIR = Path(__file__).resolve().parent / "full_recovery_scratch"
SCRATCH_DIR.mkdir(exist_ok=True)
os.environ["COMQUTOR_RECOVERY_FULL_TEST_DIR"] = str(SCRATCH_DIR)

import recover_alpha_classification as recover  # noqa: E402

NEW_RUN_ID = "c904d4cc-dc09-495c-aec5-b056979948e1-recovery-full-scale-test"


def main() -> None:
    scope = recover.compute_recovery_scope()
    print(f"needs_recovery_count (authoritative, from real alpha_matches.json): {scope['needs_recovery_count']}")
    print(f"valid_llm_results_count: {scope['valid_llm_results_count']}")
    print(f"total_claims: {scope['total_claims']}")
    assert scope["other_buckets"] == {}, f"unexpected buckets, aborting: {scope['other_buckets']}"

    print("\n=== PHASE 1: process first 3 batches (75 claims), then simulated crash ===")
    try:
        recover.run_full_fake_transport_recovery(NEW_RUN_ID, simulate_crash_after_batches=3)
        print("ERROR: expected a simulated RuntimeError crash, but none was raised")
        sys.exit(1)
    except RuntimeError as exc:
        print(f"Phase 1 stopped as expected: {exc}")

    checkpoint_path = SCRATCH_DIR / "checkpoint_full.json"
    request_audit_path = SCRATCH_DIR / NEW_RUN_ID / "error_logs" / "week2_llm_provider_request_audit.jsonl"
    checkpoint_after_phase1 = json.loads(checkpoint_path.read_text())

    def count_real_sends() -> int:
        """Total real transport sends across however many phases have run
        so far (the request-audit JSONL accumulates on disk across the
        in-process RuntimeError in phase 1, since it is a real file, not
        in-memory state). This is an AGGREGATE proof, not a per-claim one --
        see the finding recorded just below for why."""
        if not request_audit_path.exists():
            return 0
        return len([ln for ln in request_audit_path.read_text().splitlines() if ln.strip()])

    # FINDING (2026-10-06, round 13, scenario 8): the real alpha_classifier
    # payload built by alpha_mapper._classify_alpha_with_llm (claim/
    # evidence/ticker/factors/direction/alpha_taxonomy) never includes a
    # "claim_id" or "items" key, so _extract_claim_ids(payload) returns []
    # for EVERY real alpha_classifier request -- in this test and in every
    # real production run, including the original c904d4cc. The request-
    # audit JSONL's claim_ids field is therefore never populated for this
    # task; it is NOT a regression from this round's contextvar identity
    # fix (attempt_id identity is unaffected and still correctly unique --
    # see test_week2_llm_true_concurrent_audit.py), but it is a genuine,
    # pre-existing gap in this task's own forensic traceability, worth
    # fixing in a future round (e.g. adding claim_id to the payload dict
    # read by _extract_claim_ids, not the LLM-facing `request` dict). This
    # round does not change alpha_classifier's prompt/payload shape (out of
    # scope, would be a model-input change), so this test verifies resume
    # correctness in AGGREGATE (total real sends never exceeds the true
    # total) rather than by per-claim claim_ids attribution. A per-claim
    # proof via request-body hashing was considered and rejected: 16 of the
    # 973 real claims are genuine, exact duplicate (claim, evidence,
    # ticker, factors, direction) tuples (confirmed by direct inspection),
    # so body-hash identity would reintroduce the exact same kind of
    # silent-misattribution risk this round's own fix exists to eliminate.
    sends_after_phase1 = count_real_sends()
    print(f"After phase 1: checkpoint has {len(checkpoint_after_phase1['completed_claim_ids'])} completed claims; "
          f"real request-audit log shows {sends_after_phase1} total real sends "
          "(claim_ids is always [] for this task -- see FINDING in this script's own comments)")
    assert sends_after_phase1 == len(checkpoint_after_phase1["completed_claim_ids"]), (
        "phase 1's own real sends must exactly match its own checkpointed count, no more"
    )

    print("\n=== PHASE 2: resume from the SAME checkpoint, run to full completion ===")
    result = recover.run_full_fake_transport_recovery(NEW_RUN_ID, simulate_crash_after_batches=None)
    print(f"Phase 2 result: {json.dumps({k: v for k, v in result.items() if k != 'valid_llm_results_claim_ids'}, indent=2)}")

    final_checkpoint = json.loads(checkpoint_path.read_text())
    total_sends_both_phases = count_real_sends()

    print("\n=== VERIFICATION ===")
    assert len(final_checkpoint["completed_claim_ids"]) == scope["needs_recovery_count"], (
        f"expected all {scope['needs_recovery_count']} needs-recovery claims completed, "
        f"got {len(final_checkpoint['completed_claim_ids'])}"
    )
    print(f"[OK] checkpoint reached all {len(final_checkpoint['completed_claim_ids'])} needs-recovery claims")

    # Real transport sends alone (955 of 973) are LOWER than needs_recovery_
    # count -- this is the Gateway's own semantic-call cache legitimately
    # collapsing genuine duplicate-content claims (16 real duplicate
    # (claim, evidence, ticker, factors, direction) tuples exist among the
    # 973 -- confirmed by direct inspection) to fewer real Provider sends,
    # which is correct, intended behavior, not a resume-correctness defect.
    # It must never EXCEED the true count, though -- that would mean a
    # claim was sent more than once.
    assert total_sends_both_phases <= scope["needs_recovery_count"], (
        f"{total_sends_both_phases} real transport sends exceeds the true needs-recovery count of "
        f"{scope['needs_recovery_count']} -- some claim was sent more than once"
    )
    print(f"[OK] {total_sends_both_phases} real transport sends total (<= {scope['needs_recovery_count']}, "
          "the reduction being the semantic cache legitimately deduplicating real duplicate-content claims)")

    # The authoritative, cache-insensitive resume-correctness proof: every
    # claim_id that was ever SUBMITTED to map_structured_records (logged
    # independently of whether the semantic cache then avoided a real send)
    # appears in exactly one batch, total, across both phases.
    batches_submitted_path = SCRATCH_DIR / "batches_submitted.jsonl"
    submitted_claim_ids: list[str] = []
    for line in batches_submitted_path.read_text().splitlines():
        if line.strip():
            submitted_claim_ids.extend(json.loads(line)["claim_ids"])
    from collections import Counter
    submission_counts = Counter(submitted_claim_ids)
    resubmitted = {cid: n for cid, n in submission_counts.items() if n != 1}
    assert not resubmitted, (
        f"RESUME CORRECTNESS FAILURE: {len(resubmitted)} claim_ids were submitted to "
        f"map_structured_records a number of times other than exactly once across phase 1 + "
        f"phase 2 (checkpoint-skip did not work): {dict(list(resubmitted.items())[:10])}"
    )
    assert set(submission_counts.keys()) == set(scope["needs_recovery_claim_ids"]), (
        "submitted claim_id set does not exactly match the true needs-recovery claim_id set"
    )
    print(f"[OK] every one of {len(submission_counts)} needs-recovery claims was submitted to "
          "map_structured_records EXACTLY ONCE total across both phases -- phase 2's own "
          f"checkpoint-skip correctly excluded all {sends_after_phase1} of phase 1's already-done claims")

    # Merge: the checkpoint's own recovered results + the 2 already-valid
    # originals must reconstruct the full, non-duplicated 975-claim set.
    recovered_ids = set(final_checkpoint["completed_claim_ids"].keys())
    valid_ids = set(scope["valid_llm_results_claim_ids"])
    assert recovered_ids.isdisjoint(valid_ids), "recovered and already-valid claim sets must never overlap"
    merged_ids = recovered_ids | valid_ids
    assert len(merged_ids) == scope["total_claims"], (
        f"merged recovered+valid claim count ({len(merged_ids)}) does not equal the original "
        f"run's own total_claims ({scope['total_claims']})"
    )
    print(f"[OK] merged recovered ({len(recovered_ids)}) + already-valid ({len(valid_ids)}) = "
          f"{len(merged_ids)} unique claim_ids, exactly matching the original run's {scope['total_claims']}")

    original_matches = json.loads((recover.ORIGINAL_DIR / "alpha_matches.json").read_text())
    original_claim_ids = {m["claim_id"] for m in original_matches["matches"]}
    assert merged_ids == original_claim_ids, "merged set must be claim-for-claim identical to the original run's set"
    print("[OK] merged claim_id set is claim-for-claim identical to the original c904d4cc run's 975 claims "
          "-- zero omissions, zero extras")

    recovered_methods = {v["alpha_match_method"] for v in final_checkpoint["completed_claim_ids"].values()}
    assert recovered_methods == {"llm"}, (
        f"every recovered claim must get a real, completed LLM classification (method='llm'), "
        f"got methods={recovered_methods}"
    )
    print("[OK] every recovered claim got alpha_match_method='llm' (no provider_error survived at full scale)")

    print("\nFULL-SCALE RECOVERY INTEGRATION TEST: PASSED")


if __name__ == "__main__":
    main()
