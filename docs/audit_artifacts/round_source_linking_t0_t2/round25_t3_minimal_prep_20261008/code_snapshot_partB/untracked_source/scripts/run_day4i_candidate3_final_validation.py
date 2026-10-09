#!/usr/bin/env python3
"""Day 4I ONE-SHOT INDEPENDENT FINAL VALIDATION: run the REAL, CURRENT,
frozen Candidate 3 Pure-LLM Alpha Mapper (map_claim_to_alpha) against every
one of the 150 frozen Final Gold rows
(docs/audit_artifacts/v0_2_alpha_final_gold_v1.json), exercising the actual
production Alpha semantic path (classifier_enabled=True, a real
Week2LLMGateway/Provider client -- never a simulated/deterministic
stand-in).

This is the ONE AND ONLY planned evaluation pass over the Final Gold. It
never touches the Development Gold. Modeled byte-for-byte on the harness
logic of scripts/run_day4g_candidate3_baseline_dev.py -- only the input join
table and output file names differ. No setting (temperature, retries,
timeout, chunking) is changed relative to that prior harness.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy  # noqa: E402
from comqutor_alpha.research_profiles import (  # noqa: E402
    ANTHROPIC_PROFILE_ID,
    ResearchProfileError,
    get_research_profile,
)
from comqutor_alpha.structure_engine.alpha_mapper import map_claim_to_alpha  # noqa: E402
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway  # noqa: E402

JOIN_TABLE_PATH = Path("/tmp/final_gold_join.json")

TIMEOUT_SECONDS = 60.0
CHUNK_SIZE = 100


def _structured_record_for(run_id: str, claim_id: str, cache: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if run_id not in cache:
        payload = json.loads((REPO_ROOT / "outputs" / "runs" / run_id / "structured_agent_outputs.json").read_text(encoding="utf-8"))
        cache[run_id] = {r["claim_id"]: r for r in payload["records"]}
    return cache[run_id].get(claim_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="0 = all rows; >0 = dry-run against only the first N rows")
    parser.add_argument("--profile-id", default=ANTHROPIC_PROFILE_ID)
    args = parser.parse_args(argv)

    if not args.execute:
        print("BLOCKED: pass --execute to actually make Provider calls.", file=sys.stderr)
        return 1

    output_path = REPO_ROOT / "docs" / "audit_artifacts" / "v0_2_candidate3_final_system_alpha_raw.json"
    provider_audit_path = REPO_ROOT / "docs" / "audit_artifacts" / "v0_2_candidate3_final_provider_audit.json"

    rows = json.loads(JOIN_TABLE_PATH.read_text(encoding="utf-8"))
    if args.limit:
        rows = rows[: args.limit]
    n = len(rows)
    print(f"Loaded {n} Final Gold join rows (limit={args.limit or 'none'}).")

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    try:
        profile = get_research_profile(args.profile_id)
    except ResearchProfileError as exc:
        print(f"BLOCKED: {exc.reason_code}", file=sys.stderr)
        return 1

    from tradingagents.llm_clients import create_llm_client

    client = create_llm_client(
        provider=profile.llm_provider, model=profile.quick_think_llm, base_url=profile.backend_url,
        timeout=TIMEOUT_SECONDS, max_retries=0,
    )
    model = client.get_llm()

    taxonomy = load_alpha_taxonomy()
    structured_cache: dict[str, dict[str, Any]] = {}

    results: dict[str, Any] = {}
    started_total = time.monotonic()
    missing_records: list[str] = []
    total_calls = 0

    for chunk_start in range(0, n, CHUNK_SIZE):
        chunk = rows[chunk_start : chunk_start + CHUNK_SIZE]
        gateway = Week2LLMGateway(
            model, run_id=f"day4i-candidate3-final-validation-chunk{chunk_start // CHUNK_SIZE}",
            output_root=str(REPO_ROOT / "outputs" / "runs"),
            timeout_seconds=TIMEOUT_SECONDS, max_retries=0, max_calls=len(chunk),
            provider=profile.llm_provider, model_name=profile.quick_think_llm,
        )
        for row in chunk:
            record = _structured_record_for(row["run_id"], row["claim_id"], structured_cache)
            if record is None:
                missing_records.append(row["final_gold_slot"])
                continue

            row_started = time.monotonic()
            try:
                llm_result = map_claim_to_alpha(record, taxonomy, classifier_enabled=True, llm_gateway=gateway)
                row_error = None
            except Exception as exc:  # noqa: BLE001 -- record and continue, never fabricate
                llm_result = {}
                row_error = repr(exc)
            row_elapsed = time.monotonic() - row_started

            results[row["final_gold_slot"]] = {
                "final_gold_slot": row["final_gold_slot"],
                "source_sample_id": row["source_sample_id"],
                "provenance": row["provenance"],
                "claim_id": row["claim_id"],
                "run_id": row["run_id"],
                "ticker": row["ticker"],
                "gold_label": row["gold_label"],
                "system_matched_alpha_id": llm_result.get("matched_alpha"),
                "system_matched_alpha_name": llm_result.get("matched_alpha_name"),
                "match_status": llm_result.get("match_status"),
                "reason": llm_result.get("reason"),
                "alpha_match_method": llm_result.get("alpha_match_method"),
                "alpha_match_fallback_reason": llm_result.get("alpha_match_fallback_reason"),
                "classifier": llm_result.get("classifier"),
                "score": llm_result.get("score"),
                "deterministic_top_alpha": llm_result.get("deterministic_top_alpha"),
                "deterministic_match_status": llm_result.get("deterministic_match_status"),
                "row_elapsed_seconds": round(row_elapsed, 3),
                "row_error": row_error,
            }
        total_calls += gateway.call_count

    elapsed_total = time.monotonic() - started_total

    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    selected_count = sum(1 for r in results.values() if r["alpha_match_method"] == "llm" and r["match_status"] == "matched")
    none_count = sum(1 for r in results.values() if r["alpha_match_method"] == "llm" and r["match_status"] == "no_match")
    unavailable_count = sum(1 for r in results.values() if r["alpha_match_method"] == "llm_unavailable")
    error_count = sum(1 for r in results.values() if r.get("row_error"))
    fallback_reason_counts: dict[str, int] = {}
    for r in results.values():
        reason = r.get("alpha_match_fallback_reason")
        if reason:
            fallback_reason_counts[reason] = fallback_reason_counts.get(reason, 0) + 1

    provider_audit = {
        "phase": "day4i_candidate3_ONE_SHOT_INDEPENDENT_FINAL_VALIDATION",
        "provider": profile.llm_provider,
        "model_name": profile.quick_think_llm,
        "temperature": "production default (unmodified)",
        "rows_total": n,
        "rows_with_missing_structured_record": missing_records,
        "rows_with_row_error": error_count,
        "logical_provider_calls": total_calls,
        "real_provider_attempts": total_calls,
        "chunk_count": (n + CHUNK_SIZE - 1) // CHUNK_SIZE,
        "chunk_size": CHUNK_SIZE,
        "retries_used": 0,
        "cache_hit_count": 0,
        "semantic_select_count": selected_count,
        "semantic_none_count": none_count,
        "unavailable_count": unavailable_count,
        "unavailable_fallback_reason_counts": fallback_reason_counts,
        "rows_evaluated": len(results),
        "rows_unevaluated": n - len(results),
        "elapsed_seconds": round(elapsed_total, 2),
    }
    provider_audit_path.write_text(json.dumps(provider_audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(provider_audit, indent=2))
    print(f"\nWrote {len(results)} rows -> {output_path}")
    if missing_records:
        print(f"WARNING: {len(missing_records)} rows had no structured record: {missing_records}")
    if len(results) != n:
        print(f"WARNING: rows_evaluated ({len(results)}) != rows_total ({n})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
