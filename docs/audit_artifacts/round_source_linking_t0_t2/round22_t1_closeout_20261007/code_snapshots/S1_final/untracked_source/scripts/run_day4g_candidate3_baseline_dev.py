#!/usr/bin/env python3
"""Day 4G baseline Provider-backed development run: run the REAL, CURRENT
production Pure-LLM Alpha Mapper (map_claim_to_alpha) against every one of
the 100 frozen Development Gold rows (docs/audit_artifacts/v0_2_alpha_dev_gold_v1.json),
exercising the actual production Alpha semantic path (classifier_enabled=True,
a real Week2LLMGateway/Provider client -- never a simulated/deterministic
stand-in).

This is a DEVELOPMENT evaluation against the Development Gold only. It never
touches the sealed 150-sample final independent holdout.

Modeled directly on scripts/run_day4b_holdout4_system_alpha_postremediation.py
(same harness shape). The join table mapping each Gold sample_id to its
(run_id, claim_id, ticker) is read from /tmp/candidate3_dev_join.json, built
by joining v0_2_alpha_dev_gold_v1.json against
v0_2_alpha_dev_human_labels.json (original samples) and
v0_2_alpha_dev_replacement_log.json (round-1/round-2 reserve replacements).
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

JOIN_TABLE_PATH = Path("/tmp/candidate3_dev_join.json")

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
    parser.add_argument("--run-tag", default="baseline", help="tag used in output filenames and gateway run_id")
    args = parser.parse_args(argv)

    if not args.execute:
        print("BLOCKED: pass --execute to actually make Provider calls.", file=sys.stderr)
        return 1

    output_path = REPO_ROOT / "docs" / "audit_artifacts" / f"v0_2_candidate3_{args.run_tag}_dev_system_alpha_raw.json"
    provider_audit_path = REPO_ROOT / "docs" / "audit_artifacts" / f"v0_2_candidate3_{args.run_tag}_dev_provider_audit.json"

    rows = json.loads(JOIN_TABLE_PATH.read_text(encoding="utf-8"))
    if args.limit:
        rows = rows[: args.limit]
    n = len(rows)
    print(f"Loaded {n} Development Gold join rows (limit={args.limit or 'none'}).")

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
            model, run_id=f"day4g-candidate3-{args.run_tag}-dev-chunk{chunk_start // CHUNK_SIZE}",
            output_root=str(REPO_ROOT / "outputs" / "runs"),
            timeout_seconds=TIMEOUT_SECONDS, max_retries=0, max_calls=len(chunk),
            provider=profile.llm_provider, model_name=profile.quick_think_llm,
        )
        for row in chunk:
            record = _structured_record_for(row["run_id"], row["claim_id"], structured_cache)
            if record is None:
                missing_records.append(row["final_development_slot"])
                continue

            row_started = time.monotonic()
            llm_result = map_claim_to_alpha(record, taxonomy, classifier_enabled=True, llm_gateway=gateway)
            row_elapsed = time.monotonic() - row_started

            results[row["final_development_slot"]] = {
                "final_development_slot": row["final_development_slot"],
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
            }
        total_calls += gateway.call_count

    elapsed_total = time.monotonic() - started_total

    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    selected_count = sum(1 for r in results.values() if r["alpha_match_method"] == "llm" and r["match_status"] == "matched")
    none_count = sum(1 for r in results.values() if r["alpha_match_method"] == "llm" and r["match_status"] == "no_match")
    unavailable_count = sum(1 for r in results.values() if r["alpha_match_method"] == "llm_unavailable")
    fallback_reason_counts: dict[str, int] = {}
    for r in results.values():
        reason = r.get("alpha_match_fallback_reason")
        if reason:
            fallback_reason_counts[reason] = fallback_reason_counts.get(reason, 0) + 1

    provider_audit = {
        "phase": f"day4g_candidate3_{args.run_tag}_dev_alpha_inference",
        "provider": profile.llm_provider,
        "model_name": profile.quick_think_llm,
        "temperature": "production default (unmodified)",
        "rows_total": n,
        "rows_with_missing_structured_record": missing_records,
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
