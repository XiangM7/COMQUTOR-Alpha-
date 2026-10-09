"""Phase C (2026-10-06): the REAL script that executes the limited,
21-claim real LLM content-support verification against the already-
completed AMD run. Requires the explicit ``--execute`` CLI flag to make
any real Provider call -- mirrors the exact, already-proven safety pattern
``scripts/run_day4i_candidate3_final_validation.py`` uses ("BLOCKED: pass
--execute to actually make Provider calls"). Without ``--execute`` this
script only runs every preflight check and prints what it WOULD do, zero
Provider calls.

Every budget-safety parameter below reaches the REAL client construction
(comqutor_alpha.structure_engine.week2_llm.build_server_week2_llm_gateway
-> tradingagents.llm_clients.create_llm_client), confirmed by direct code
reading AND by a live (zero-cost) gateway-construction check this script
performs before ever sending a real request:

  - COMQUTOR_WEEK2_LLM_MAX_RETRIES=0 -> Week2LLMGateway.max_retries=0 ->
    invoke_json_with_trace's own retry loop runs range(1, 0+2) = exactly
    ONE real attempt per claim.
  - COMQUTOR_WEEK2_LLM_MAX_CALLS=21 -> Week2LLMGateway's own _reserve_call()
    budget -- a real, hard global ceiling.
  - Client-level max_retries=0 is already unconditionally hardcoded in
    build_server_week2_llm_gateway's own client_kwargs for every caller.
  - max_tokens=4096 passed as an explicit keyword argument.

These env vars are set AFTER load_dotenv() specifically so they win over
whatever .env may also define -- the same "explicit override must be set
last" principle the documented 2026-10-02 production-DB-write incident
established for COMQUTOR_DATABASE_URL, applied here to the semantic-layer
flags instead (this script touches no database at all).

Scope statement: a LIMITED, one-time semantic verification of 21 ALREADY-
SAVED AMD claims from run_id 1bad76a7-72ac-4c8b-8189-2e5c0f1a6105 -- NOT a
Fresh Run (no new market/news data fetched), NOT a T3 overall-accuracy
evaluation. The 21 claims are the full, already-published list in
round9_llm_content_support_20261006/01_amd_21_analytical_claims_raw.json,
used verbatim -- never swapped, trimmed, or reordered because of an
expected outcome.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

ORIGINAL_RUN_ID = "1bad76a7-72ac-4c8b-8189-2e5c0f1a6105"
# 2026-10-06 correction (found during this script's own first --execute
# attempt, zero real Provider calls made -- requested_count was 0 because
# this file was being read from): the ORIGINAL frozen run's own
# structured_agent_outputs.json still shows these 21 claims as
# source_link_status=TIME_INVALID -- round7's evidence_cutoff_at fix was
# NEVER written back into that original file (correctly -- history is
# never overwritten). The already-computed, zero-new-fetch, pure
# re-annotation execution below is where these claims genuinely show
# VALID -- it is itself derived ONLY from the original run's own saved
# data (round8's own harness), so reading it is not "new material", it is
# the correct frozen input for this exact proposal.
REEVAL_RUN_ID = "automated-eligibility-reeval-20261005T190101Z-d9b7fdba"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "runs"
ROUND10_DIR = Path(__file__).resolve().parent
EXPECTED_SOURCE_ID = "src_5bd8a947130d1949"

# Hashes of the REEVAL_RUN_ID files actually read for the 21 claims (the
# ones with source_link_status=VALID) -- any drift means this already-
# computed re-annotation artifact changed since this script was written,
# and this script refuses to proceed rather than verify against a
# different file than the one the proposal was built from. The ORIGINAL
# run's own metadata.json (analysis_date) is still read directly from
# ORIGINAL_RUN_ID, unchanged.
EXPECTED_HASHES = {
    "structured_agent_outputs.json": "f65cbe928b82b096451733da88ee99d1ecd031dea234d93dd2bb7878c80f9031",
    "source_registry.json": "e7b728e65ab1b9836ee5ecd9a99ce788ef397853967a5c3ecf10cc800f83e815",
}
EXPECTED_ORIGINAL_METADATA_HASH = "eef173af99fb45a4932d1e4fa372b2706b612f99ef64bf06512fef5b1e42b395"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fail(message: str) -> None:
    print(f"PREFLIGHT_FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def run_preflight() -> dict:
    """Every check must pass before a single real request is sent. Returns
    the frozen snapshot this run will use. Raises/exits on any mismatch --
    never proceeds past a failed check."""
    original_dir = OUTPUT_ROOT / ORIGINAL_RUN_ID
    reeval_dir = OUTPUT_ROOT / REEVAL_RUN_ID
    for filename, expected_hash in EXPECTED_HASHES.items():
        path = reeval_dir / filename
        if not path.exists():
            _fail(f"missing re-annotation input file: {filename}")
        actual_hash = _sha256(path)
        if actual_hash != expected_hash:
            _fail(
                f"input hash drift on {filename}: expected {expected_hash}, got {actual_hash} "
                "-- the re-annotation artifact changed since this script was written, refusing to proceed"
            )
    original_metadata_path = original_dir / "metadata.json"
    actual_original_metadata_hash = _sha256(original_metadata_path)
    if actual_original_metadata_hash != EXPECTED_ORIGINAL_METADATA_HASH:
        _fail(
            f"original run's metadata.json hash drift: expected {EXPECTED_ORIGINAL_METADATA_HASH}, "
            f"got {actual_original_metadata_hash} -- refusing to proceed"
        )
    print("PREFLIGHT: re-annotation artifact + original metadata hashes match exactly.")

    claims_path = ROUND10_DIR.parent / "round9_llm_content_support_20261006" / "01_amd_21_analytical_claims_raw.json"
    frozen_claims = json.loads(claims_path.read_text())
    if len(frozen_claims) != 21:
        _fail(f"expected exactly 21 frozen claims, found {len(frozen_claims)}")

    structured = json.loads((reeval_dir / "structured_agent_outputs.json").read_text())
    sources = json.loads((reeval_dir / "source_registry.json").read_text())["sources"]
    structured_by_id = {r["claim_id"]: r for r in structured["records"]}

    frozen_claim_ids = {c["claim_id"] for c in frozen_claims}
    missing = frozen_claim_ids - set(structured_by_id)
    if missing:
        _fail(f"{len(missing)} frozen claim_id(s) no longer resolve in structured_agent_outputs.json: {missing}")

    records = [structured_by_id[c["claim_id"]] for c in frozen_claims]
    for record in records:
        if record.get("linked_source_id") not in (EXPECTED_SOURCE_ID, f"{EXPECTED_SOURCE_ID}:frag:0"):
            _fail(
                f"claim {record['claim_id']} links to {record.get('linked_source_id')!r}, "
                f"not the proposed candidate {EXPECTED_SOURCE_ID!r} -- scope drift, refusing to proceed"
            )
        if record.get("source_link_status") != "VALID":
            _fail(
                f"claim {record['claim_id']} has source_link_status={record.get('source_link_status')!r}, "
                "not VALID -- this claim is not actually eligible to submit, refusing to proceed"
            )

    source = next((s for s in sources if s["source_id"] == EXPECTED_SOURCE_ID), None)
    if source is None:
        _fail(f"candidate source {EXPECTED_SOURCE_ID} not found in source_registry.json")
    print(f"PREFLIGHT: all 21 claims are source_link_status=VALID and link only to the proposed candidate {EXPECTED_SOURCE_ID}.")
    print(f"PREFLIGHT: candidate source content_hash = {source['content_hash']}")

    analysis_date = json.loads(original_metadata_path.read_text()).get("analysis_date")
    from comqutor_alpha.source_provenance import resolve_evidence_cutoff_at

    evidence_cutoff_at, evidence_cutoff_basis = resolve_evidence_cutoff_at(analysis_date, sources)
    print(f"PREFLIGHT: analysis_date={analysis_date}, evidence_cutoff_at={evidence_cutoff_at} ({evidence_cutoff_basis})")

    git_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    git_dirty = bool(
        subprocess.run(["git", "status", "--short"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    )
    print(f"PREFLIGHT: git HEAD={git_commit}, working tree dirty={git_dirty}")

    return {
        "frozen_claims": frozen_claims,
        "records": records,
        "sources": sources,
        "candidate_source_content_hash": source["content_hash"],
        "analysis_date": analysis_date,
        "evidence_cutoff_at": evidence_cutoff_at,
        "evidence_cutoff_basis": evidence_cutoff_basis,
        "git_commit": git_commit,
        "git_dirty": git_dirty,
    }


def verify_live_client_config(
    execution_id: str,
    *,
    max_calls: str = "21",
    max_tokens: int = 4096,
    enable_request_response_audit: bool = True,
    _base_transport_for_testing: object = None,
    _gateway_output_root_for_testing: object = None,
) -> object:
    """Zero-cost: constructs the REAL gateway (no .invoke() call made yet)
    and inspects its ACTUAL constructed attributes -- never trusts the
    proposal document alone. Exits if the gateway cannot be built or its
    real attributes do not match the required budget exactly.

    ``enable_request_response_audit`` (2026-10-06 fix): on by default for
    every REAL execution from now on -- the first real --execute run had
    no wire-level request/response audit at all, which is why the actual
    request bodies for its 5 real calls could never be recovered after the
    fact. ``_base_transport_for_testing`` is forwarded to
    build_server_week2_llm_gateway untouched -- production (main()) never
    passes it; only the dedicated fixed-response test does, to fake ONLY
    the lowest HTTP layer while every real function on this path (this
    function, create_llm_client, the real Gateway retry/budget loop) runs
    unmodified."""
    import os

    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
    except ImportError:
        _fail("python-dotenv not available -- cannot load real API credentials safely")

    # Explicit overrides AFTER load_dotenv, so these specific values win
    # over whatever .env also defines for these same names.
    os.environ["COMQUTOR_WEEK2_LLM_ENABLED"] = "1"
    os.environ["COMQUTOR_WEEK2_LLM_PROVIDER"] = "deepseek"
    os.environ["COMQUTOR_WEEK2_LLM_MODEL"] = "deepseek-v4-flash"
    os.environ["COMQUTOR_WEEK2_LLM_MAX_RETRIES"] = "0"
    os.environ["COMQUTOR_WEEK2_LLM_MAX_CALLS"] = max_calls

    from comqutor_alpha.structure_engine.week2_llm import build_server_week2_llm_gateway

    gateway = build_server_week2_llm_gateway(
        "phase-c-amd-21-claim-verification",
        _gateway_output_root_for_testing or OUTPUT_ROOT,
        max_tokens=max_tokens,
        execution_id=execution_id,
        enable_request_response_audit=enable_request_response_audit,
        _base_transport_for_testing=_base_transport_for_testing,
    )
    if gateway is None:
        _fail(
            "build_server_week2_llm_gateway returned None -- COMQUTOR_WEEK2_LLM_ENABLED/PROVIDER/MODEL "
            "not correctly resolved, or client construction failed -- refusing to proceed"
        )
    if gateway.max_retries != 0:
        _fail(f"live gateway.max_retries={gateway.max_retries}, expected 0 -- refusing to proceed")
    if gateway.max_calls != int(max_calls):
        _fail(f"live gateway.max_calls={gateway.max_calls}, expected exactly {max_calls} -- refusing to proceed")
    if gateway.provider != "deepseek" or gateway.model_name != "deepseek-v4-flash":
        _fail(f"live gateway provider/model mismatch: {gateway.provider}/{gateway.model_name}")
    print(f"LIVE CHECK: real gateway constructed -- provider={gateway.provider}, model={gateway.model_name}, "
          f"max_retries={gateway.max_retries}, max_calls={gateway.max_calls}, "
          f"DEEPSEEK_API_KEY present={'DEEPSEEK_API_KEY' in os.environ}")
    return gateway


def run(
    args: argparse.Namespace,
    *,
    _base_transport_for_testing: object = None,
    _gateway_output_root_for_testing: object = None,
    _results_dir_for_testing: object = None,
) -> dict | None:
    """The script's real logic, factored out of main() so a fixed-response
    test can exercise this EXACT function (not a reimplementation of it)
    with only the lowest HTTP transport faked. main() below calls this with
    _base_transport_for_testing=None always -- production never fakes
    anything. Returns the saved result dict when --execute ran, else None.

    2026-10-06 fix: the ORIGINAL 04_phase_c_real_results.json (the first,
    all-5-requests-truncated real execution) is now a permanently frozen,
    read-only historical record -- this function NEVER writes to that path
    again. Every real --execute run (this one included, going forward)
    gets its own execution_id and its own file under executions/, so a
    second real run can never silently overwrite the first one's evidence."""
    snapshot = run_preflight()
    execution_id = args.execution_id or f"phase-c-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    gateway = verify_live_client_config(
        execution_id, max_calls=str(args.max_calls), max_tokens=args.max_tokens,
        _base_transport_for_testing=_base_transport_for_testing,
        _gateway_output_root_for_testing=_gateway_output_root_for_testing,
    )

    from comqutor_alpha.structure_engine.content_support_llm import build_content_support_request_items

    dry_run_items = build_content_support_request_items(snapshot["records"], snapshot["sources"])
    print(f"DRY RUN (zero cost): build_content_support_request_items would submit {len(dry_run_items)}/21 claims.")
    if len(dry_run_items) != 21:
        skipped = {c["claim_id"] for c in snapshot["frozen_claims"]} - {i.claim_id for i in dry_run_items}
        _fail(
            f"expected all 21 claims to be eligible for submission, only {len(dry_run_items)} would be -- "
            f"skipped: {skipped} -- refusing to proceed until this is understood"
        )

    if not args.execute:
        print("BLOCKED: pass --execute to actually make Provider calls. All preflight checks passed; zero Provider calls made.")
        return None

    if args.target_claim_ids:
        wanted = set(args.target_claim_ids)
        records = [r for r in snapshot["records"] if r["claim_id"] in wanted]
        missing = wanted - {r["claim_id"] for r in records}
        if missing:
            _fail(f"--target-claim-id value(s) not found among the 21 frozen claims: {missing}")
    else:
        records = snapshot["records"]

    from comqutor_alpha.structure_engine.content_support_llm import (
        apply_llm_content_support_verification,
    )

    # 2026-10-06 fix: the first real --execute run on this script tried to
    # force batch_size=1 (one real request per claim, for independent
    # per-claim diagnosability) by reassigning the module's own BATCH_SIZE
    # attribute after import. That silently had NO effect: chunk_items(
    # items, size: int = BATCH_SIZE)'s default is bound ONCE, at function
    # DEFINITION time, so the module-attribute reassignment never reached
    # it -- confirmed offline, zero-cost, in
    # tests/test_content_support_llm_phase_c_batch_size_fix.py
    # (test_chunk_items_own_default_is_bound_at_definition_time_not_read_live
    # reproduces the exact real [5, 5, 5, 5, 1]-claim batch shape this bug
    # produced). The real fix is the explicit batch_size= keyword parameter
    # apply_llm_content_support_verification now accepts.
    updated_records, stats = apply_llm_content_support_verification(
        records, snapshot["sources"], llm_gateway=gateway, batch_size=1
    )

    executions_dir = Path(_results_dir_for_testing) if _results_dir_for_testing else (ROUND10_DIR / "executions")
    executions_dir.mkdir(parents=True, exist_ok=True)
    out_path = executions_dir / f"{execution_id}.json"
    result = {
        "based_on_run_id": ORIGINAL_RUN_ID,
        "execution_id": execution_id,
        "executed_at": datetime.now(UTC).isoformat(),
        "candidate_source_content_hash": snapshot["candidate_source_content_hash"],
        "analysis_date": snapshot["analysis_date"],
        "evidence_cutoff_at": snapshot["evidence_cutoff_at"],
        "evidence_cutoff_basis": snapshot["evidence_cutoff_basis"],
        "git_commit": snapshot["git_commit"],
        "git_dirty": snapshot["git_dirty"],
        "claim_count": len(records),
        "max_calls": args.max_calls,
        "max_tokens": args.max_tokens,
        "stats": stats.to_dict(),
        "records": updated_records,
    }
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"execution_id={execution_id}")
    print(f"requested_count={stats.requested_count}")
    print(f"llm_verified_count={stats.llm_verified_count}")
    print(f"fallback_count={stats.fallback_count}")
    print(f"fallback_reason_counts={stats.fallback_reason_counts}")
    print(f"status_counts={stats.status_counts}")
    print(f"real_provider_attempts={stats.real_provider_attempts} (must be <= {args.max_calls}, never retried)")
    print(f"results saved to {out_path}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Actually make real Provider calls.")
    parser.add_argument("--max-calls", type=int, default=21, help="Global hard call-budget cap for this execution.")
    parser.add_argument("--max-tokens", type=int, default=4096, help="max_tokens forwarded to the real client.")
    parser.add_argument(
        "--target-claim-id", dest="target_claim_ids", action="append", default=[],
        help="Restrict this execution to only these already-frozen claim_id(s) (repeatable). "
             "Default (omitted): all 21.",
    )
    parser.add_argument(
        "--execution-id", default=None,
        help="Explicit execution_id (default: auto-generated timestamp+random suffix).",
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
