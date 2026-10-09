#!/usr/bin/env python3
"""AMD post-processing continuation (round 11, controlled continuation of
the crashed run 91d7c420-6197-46c3-93f9-bd42792c1ff7).

Calls ONLY real production functions, in the real production order, against
a NEW run_id whose directory is seeded with the ORIGINAL run's own
real captured materials (copied verbatim, hash-verified before and after).
TradingAgents is never invoked: run_research_request's own `runner`
extension point is used to hand it the pre-populated directory directly,
exactly the same way an offline/replay caller already can.

Does not reimplement claim extraction, content-support verification, Alpha
classification, activation scoring, or conflict detection -- every one of
those steps is the real, unmodified production function.

Usage:
    --seed-only NEW_RUN_ID      verify+copy inputs only, zero cost
    --dry-run NEW_RUN_ID        full chain, fake Provider transport, zero cost
    --run NEW_RUN_ID            full chain, real Provider calls, real spend
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

ORIGINAL_RUN_ID = "91d7c420-6197-46c3-93f9-bd42792c1ff7"
OUTPUT_ROOT = (REPO_ROOT / "outputs" / "runs").resolve()
ORIGINAL_DIR = OUTPUT_ROOT / ORIGINAL_RUN_ID

# Captured directly from the original run's own files before this script was
# written (see this round's own report) -- any mismatch means the read-only
# original materials changed since reconciliation; this script refuses to
# proceed rather than operate on unverified input.
EXPECTED_HASHES = {
    "raw_agent_outputs.json": "bbfad5312f08cd52e508cd9940f03d63ba81b11f68e5add9cb5032e8a6bf8bdb",
    "source_registry.json": "fa631e2b45e64008cd250425dd44c53160b2e30f9d1613f5735a9d38304af952",
    "metadata.json": "af1c53e12a9660ef0cc88cb74a2c9dea499af03bb2d8c3fa935b7c8b774d3ac4",
}

# Computed offline, zero-cost, from the original run's own real materials
# (11 raw agent outputs -> 19 total claim_batch_enrichment batch
# opportunities at LLM_CLAIM_BATCH_SIZE=64; see this round's own report for
# the full derivation). This is a deterministic UPPER BOUND on how many real
# Week2 requests the crashed first attempt could possibly have made --
# max_retries=0 means at most one real attempt per batch opportunity, and an
# agent's own batches abort after its first failure, so the true count is
# very likely lower, never higher.
WEEK2_BUDGET_TOTAL_CAP = 1500
WEEK2_BUDGET_CONSUMED_BEFORE_CRASH_UPPER_BOUND = 19
WEEK2_BUDGET_REMAINING = WEEK2_BUDGET_TOTAL_CAP - WEEK2_BUDGET_CONSUMED_BEFORE_CRASH_UPPER_BOUND


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_and_copy_inputs(new_run_id: str) -> Path:
    new_dir = OUTPUT_ROOT / new_run_id
    if new_dir.exists():
        raise RuntimeError(f"REFUSING_TO_OVERWRITE: {new_dir} already exists")
    for fname, expected in EXPECTED_HASHES.items():
        actual = _sha256(ORIGINAL_DIR / fname)
        if actual != expected:
            raise RuntimeError(
                f"HASH_MISMATCH: {fname} actual={actual} expected={expected} -- "
                "original run materials changed since reconciliation, refusing to proceed"
            )
    new_dir.mkdir(parents=True)
    for fname in EXPECTED_HASHES:
        shutil.copy(ORIGINAL_DIR / fname, new_dir / fname)
        copied_hash = _sha256(new_dir / fname)
        if copied_hash != EXPECTED_HASHES[fname]:
            raise RuntimeError(f"COPY_INTEGRITY_FAILURE: {fname} hash changed during copy")

    lineage = {
        "based_on_run_id": ORIGINAL_RUN_ID,
        "execution_kind": "post_processing_continuation",
        "reason": (
            "original run crashed inside structured_agent_outputs "
            "(WEEK2_LLM_AUDIT_CONCURRENT_ATTEMPT) before any claim was "
            "persisted; TradingAgents research is reused verbatim from the "
            "original run's own real captured materials, never re-executed"
        ),
        "original_run_input_hashes": EXPECTED_HASHES,
        "week2_budget_total_cap": WEEK2_BUDGET_TOTAL_CAP,
        "week2_budget_consumed_before_crash_upper_bound": WEEK2_BUDGET_CONSUMED_BEFORE_CRASH_UPPER_BOUND,
        "week2_budget_remaining_for_this_continuation": WEEK2_BUDGET_REMAINING,
        "research_agent_new_calls_this_continuation": 0,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (new_dir / "continuation_lineage.json").write_text(json.dumps(lineage, indent=2))
    print(f"Seeded {new_dir} from {ORIGINAL_DIR} (hash-verified both before and after copy).")
    print(f"Week2 remaining budget for this continuation: {WEEK2_BUDGET_REMAINING}")
    return new_dir


def _install_dry_run_transport() -> None:
    """Patches ONLY the underlying Provider/HTTP boundary (tradingagents.
    llm_clients.create_llm_client's own http_client kwarg), exactly the
    pattern already used in tests/test_week2_llm.py -- never a module-global
    mutation of business logic. Every real request gets a fast, uniform,
    invalid-JSON response, proving the ENTIRE new orchestration (claim ->
    gateway -> runner-bypass -> execute_claimed_research_run -> Week1/2 ->
    data sanity -> Week3/Conflict -> status transition) survives total LLM
    failure without crashing -- wiring proof only, never a stand-in for a
    real semantic result."""
    import httpx
    import tradingagents.llm_clients as llm_clients
    from tradingagents.llm_clients.factory import create_llm_client as real_create_llm_client

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-dry-run-wiring-check",
                "object": "chat.completion",
                "created": 0,
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "not valid json, dry-run wiring check only"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    mock_http_client = httpx.Client(transport=httpx.MockTransport(handler))

    def wrapped_factory(**kwargs):
        kwargs["http_client"] = mock_http_client
        return real_create_llm_client(**kwargs)

    llm_clients.create_llm_client = wrapped_factory


def run_continuation(new_run_id: str, new_dir: Path, *, dry_run: bool) -> dict:
    os.environ["COMQUTOR_WEEK2_LLM_MAX_CALLS"] = str(WEEK2_BUDGET_REMAINING)
    if dry_run:
        _install_dry_run_transport()

    from comqutor_alpha.storage.db.repository import build_write_repository_from_env
    from comqutor_alpha.research_lifecycle import (
        build_research_request_identity,
        build_research_request_fingerprint,
        execute_claimed_research_run,
    )
    from comqutor_alpha import server_execution
    from comqutor_alpha.structure_engine.week2_llm import build_server_week2_llm_gateway
    from comqutor_alpha.api.routes_research import run_research_request

    graph_repository = build_write_repository_from_env(OUTPUT_ROOT)

    ctx = server_execution.build_server_execution_context()
    if ctx["error"] is not None:
        raise RuntimeError(f"SERVER_EXECUTION_CONTEXT_ERROR: {ctx['error']}")

    working_payload = {
        "ticker": "AMD",
        "analysis_date": "2026-10-06",
        "selected_analysts": ["market", "news", "fundamentals"],
    }
    identity = build_research_request_identity(
        working_payload, server_execution_identity=ctx["execution_identity"]
    )
    fingerprint = build_research_request_fingerprint(identity)

    # force_refresh=True (2026-10-06, caught by this script's own sanity
    # check before any real spend): this exact ticker/analysis_date/
    # analysts/profile fingerprint already has a "completed" row from this
    # round's own earlier zero-cost dry run (91d7c420-dryrun-test-01, all
    # fake/invalid responses) -- claim_research_run's fingerprint-based
    # dedup would otherwise silently return that worthless dry-run result
    # as "reused_completed" for THIS run_id too, never claiming a fresh row
    # or making any real call at all.
    claim = graph_repository.claim_research_run(
        run_id=new_run_id,
        request_fingerprint=fingerprint,
        ticker=identity["ticker"],
        analysis_date=identity["analysis_date"],
        selected_analysts=identity["selected_analysts"],
        execution_mode=identity["execution_mode"],
        provider_identity=identity["provider_identity"],
        model_identity=identity["model_identity"],
        pipeline_identity=identity["pipeline_identity"],
        force_refresh=True,
    )
    print("claim_research_run disposition:", claim["disposition"])
    if claim["run_id"] != new_run_id or claim["disposition"] not in ("created", "force_refreshed"):
        raise RuntimeError(f"UNEXPECTED_CLAIM_DISPOSITION: {claim}")

    week2_gateway = build_server_week2_llm_gateway(new_run_id, OUTPUT_ROOT)
    if week2_gateway is None:
        raise RuntimeError("WEEK2_GATEWAY_UNAVAILABLE: week2 semantic pipeline is not ready")
    if week2_gateway.max_calls != WEEK2_BUDGET_REMAINING:
        raise RuntimeError(
            f"BUDGET_MISMATCH: gateway.max_calls={week2_gateway.max_calls} "
            f"expected={WEEK2_BUDGET_REMAINING}"
        )

    def _runner(payload, output_root):
        return str(new_dir)

    def _executor(payload, *, output_root, graph_repository):
        return run_research_request(
            payload,
            runner=_runner,
            output_root=output_root,
            week2_llm_gateway=week2_gateway,
            graph_repository=graph_repository,
            progress_reporter=None,
        )

    execution_payload = {
        "run_id": new_run_id,
        "ticker": identity["ticker"],
        "analysis_date": identity["analysis_date"],
        "selected_analysts": identity["selected_analysts"],
        "profile_id": str(ctx["execution_identity"].get("profile_id") or ""),
    }

    result = execute_claimed_research_run(
        run_id=new_run_id,
        execution_payload=execution_payload,
        output_root=OUTPUT_ROOT,
        graph_repository=graph_repository,
        disposition=claim["disposition"],
        ticker=identity["ticker"],
        executor=_executor,
    )
    print(json.dumps(result, indent=2, default=str))
    print("real Week2 calls actually made (gateway._call_count):", week2_gateway._call_count)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("new_run_id")
    parser.add_argument("--seed-only", action="store_true", help="only verify+copy inputs, do not run the pipeline")
    parser.add_argument("--dry-run", action="store_true", help="full chain, fake Provider transport, zero cost")
    parser.add_argument("--run", action="store_true", help="full chain, real Provider calls, real spend")
    args = parser.parse_args()

    if args.seed_only:
        verify_and_copy_inputs(args.new_run_id)
    elif args.dry_run:
        new_dir = verify_and_copy_inputs(args.new_run_id)
        run_continuation(args.new_run_id, new_dir, dry_run=True)
    elif args.run:
        new_dir = OUTPUT_ROOT / args.new_run_id
        if not new_dir.exists():
            new_dir = verify_and_copy_inputs(args.new_run_id)
        run_continuation(args.new_run_id, new_dir, dry_run=False)
    else:
        parser.print_help()
