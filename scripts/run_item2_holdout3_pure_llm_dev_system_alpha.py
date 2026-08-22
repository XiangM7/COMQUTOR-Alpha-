#!/usr/bin/env python3
"""Alpha Mapper Pure-LLM Semantic Authority -- Holdout #3 Development
Re-Evaluation, Provider-call phase: run the CURRENT, frozen, unmodified
Pure-LLM-authority production Alpha Mapper (map_claim_to_alpha) against
every one of the SAME 152 frozen Holdout #3 rows used for the original
(now-consumed) blind evaluation, exercising the real, LLM-only semantic
path (classifier_enabled=True, a real Week2LLMGateway/Provider client).

Under Pure-LLM authority a single call now yields BOTH the LLM semantic
result (matched_alpha/match_status/alpha_match_method/...) AND the
deterministic counterfactual (deterministic_top_alpha/
deterministic_match_status) in the same result dict -- unlike the original
Holdout #3 script, no separate classifier_enabled=False call is needed to
recover the deterministic-only conclusion.

Chunks across multiple Week2LLMGateway instances from the start
(CHUNK_SIZE=100), since a single instance's MAX_SERVER_CALLS=100 ceiling
silently capped the very first Holdout #3 run at 100/152 attempts before
that bug was caught (task spec section 22's own explicit reminder).

Every diagnostic field captured here is for POST-evaluation audit only.
Reviewer labels are NOT re-derived here -- this script never calls, reads,
or influences the independent reviewer; see item2_blind_holdout3_alpha_
review.json (reused verbatim, per task spec section 21).
"""

from __future__ import annotations

import argparse
import csv
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

FROZEN_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout3_frozen.csv"
OUTPUT_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_holdout3_pure_llm_dev_system_alpha.json"
PROVIDER_AUDIT_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_holdout3_pure_llm_dev_provider_audit.json"

TIMEOUT_SECONDS = 60.0


def _load_frozen_rows() -> list[dict[str, Any]]:
    with FROZEN_CSV_PATH.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _structured_record_for(run_id: str, claim_id: str, cache: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if run_id not in cache:
        payload = json.loads((REPO_ROOT / "outputs" / "runs" / run_id / "structured_agent_outputs.json").read_text(encoding="utf-8"))
        cache[run_id] = {r["claim_id"]: r for r in payload["records"]}
    return cache[run_id].get(claim_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--profile-id", default=ANTHROPIC_PROFILE_ID)
    args = parser.parse_args(argv)

    if not args.execute:
        print("BLOCKED: pass --execute to actually make Provider calls.", file=sys.stderr)
        return 1

    rows = _load_frozen_rows()
    n = len(rows)
    print(f"Loaded {n} frozen Holdout #3 rows.")

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

    # Week2LLMGateway.__init__ hard-clamps max_calls to MAX_SERVER_CALLS
    # (100, an existing, unmodified production safety rail) per instance --
    # for 152 rows (one logical Alpha-classifier call each, unbatched) this
    # requires multiple gateway instances, each within that ceiling, so
    # every row genuinely gets an LLM attempt from the very first run
    # (task spec section 22's explicit reminder about the original Holdout
    # #3 run's MAX_SERVER_CALLS=100 bug).
    CHUNK_SIZE = 100
    taxonomy = load_alpha_taxonomy()
    structured_cache: dict[str, dict[str, Any]] = {}

    results: dict[str, Any] = {}
    started_total = time.monotonic()
    missing_records: list[str] = []
    total_calls = 0

    for chunk_start in range(0, n, CHUNK_SIZE):
        chunk = rows[chunk_start : chunk_start + CHUNK_SIZE]
        gateway = Week2LLMGateway(
            model, run_id=f"item2-holdout3-pure-llm-dev-chunk{chunk_start // CHUNK_SIZE}",
            output_root=str(REPO_ROOT / "outputs" / "runs"),
            timeout_seconds=TIMEOUT_SECONDS, max_retries=0, max_calls=len(chunk),
            provider=profile.llm_provider, model_name=profile.quick_think_llm,
        )
        for row in chunk:
            record = _structured_record_for(row["run_id"], row["claim_id"], structured_cache)
            if record is None:
                missing_records.append(row["sample_id"])
                continue

            row_started = time.monotonic()
            # Pure-LLM authority: one call now yields both the semantic
            # result AND the deterministic counterfactual
            # (deterministic_top_alpha/deterministic_match_status) --
            # unlike the original Holdout #3 script, no separate
            # classifier_enabled=False call is needed.
            llm_result = map_claim_to_alpha(record, taxonomy, classifier_enabled=True, llm_gateway=gateway)
            row_elapsed = time.monotonic() - row_started

            matched_candidate = next(
                (c for c in (llm_result.get("candidate_scores") or []) if c.get("alpha_id") == llm_result.get("matched_alpha")),
                None,
            )

            results[row["sample_id"]] = {
                "sample_id": row["sample_id"],
                "claim_id": row["claim_id"],
                "run_id": row["run_id"],
                "ticker": row["ticker"],
                "system_matched_alpha_id": llm_result.get("matched_alpha"),
                "system_matched_alpha_name": llm_result.get("matched_alpha_name"),
                "match_status": llm_result.get("match_status"),
                "reason": llm_result.get("reason"),
                "alpha_match_method": llm_result.get("alpha_match_method"),
                "alpha_match_fallback_reason": llm_result.get("alpha_match_fallback_reason"),
                "classifier": llm_result.get("classifier"),
                "score": llm_result.get("score"),
                "matched_candidate_ai_gate_passed": (matched_candidate or {}).get("ai_gate_passed"),
                "matched_candidate_eligible": (matched_candidate or {}).get("eligible"),
                "matched_candidate_rejection_reason": (matched_candidate or {}).get("rejection_reason"),
                "candidate_scores": [
                    {
                        "alpha_id": c.get("alpha_id"), "score": c.get("score"), "eligible": c.get("eligible"),
                        "relation": c.get("relation"), "ai_gate_passed": c.get("ai_gate_passed"),
                        "rejection_reason": c.get("rejection_reason"),
                    }
                    for c in (llm_result.get("candidate_scores") or [])
                ],
                "eligible_candidates": [c.get("alpha_id") for c in (llm_result.get("eligible_candidates") or [])],
                "deterministic_top_alpha": llm_result.get("deterministic_top_alpha"),
                "deterministic_match_status": llm_result.get("deterministic_match_status"),
                "row_elapsed_seconds": round(row_elapsed, 3),
            }
        total_calls += gateway.call_count

    elapsed_total = time.monotonic() - started_total

    OUTPUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    selected_count = sum(1 for r in results.values() if r["alpha_match_method"] == "llm" and r["match_status"] == "matched")
    none_count = sum(1 for r in results.values() if r["alpha_match_method"] == "llm" and r["match_status"] == "no_match")
    unavailable_count = sum(1 for r in results.values() if r["alpha_match_method"] == "llm_unavailable")
    fallback_reason_counts: dict[str, int] = {}
    for r in results.values():
        reason = r.get("alpha_match_fallback_reason")
        if reason:
            fallback_reason_counts[reason] = fallback_reason_counts.get(reason, 0) + 1

    provider_audit = {
        "phase": "holdout3_pure_llm_dev_production_alpha_inference",
        "provider": profile.llm_provider,
        "model_name": profile.quick_think_llm,
        "temperature": "production default (unmodified)",
        "prompt_version": "week2.alpha_classifier.v3",
        "output_schema_version": "week2.alpha_classifier.output.v2",
        "rows_total": n,
        "rows_with_missing_structured_record": missing_records,
        "logical_provider_calls": total_calls,
        "real_provider_attempts": total_calls,  # max_retries=0: exactly one attempt per logical call
        "chunk_count": (n + CHUNK_SIZE - 1) // CHUNK_SIZE,
        "chunk_size": CHUNK_SIZE,
        "retries_used": 0,
        "semantic_select_count": selected_count,
        "semantic_none_count": none_count,
        "unavailable_count": unavailable_count,
        "unavailable_fallback_reason_counts": fallback_reason_counts,
        "rows_evaluated": len(results),
        "rows_unevaluated": n - len(results),
        "elapsed_seconds": round(elapsed_total, 2),
    }
    existing_audit = json.loads(PROVIDER_AUDIT_PATH.read_text(encoding="utf-8")) if PROVIDER_AUDIT_PATH.exists() else {}
    existing_audit["holdout3_pure_llm_dev_production_alpha_inference"] = provider_audit
    PROVIDER_AUDIT_PATH.write_text(json.dumps(existing_audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(provider_audit, indent=2))
    print(f"\nWrote {len(results)} rows -> {OUTPUT_PATH}")
    if missing_records:
        print(f"WARNING: {len(missing_records)} rows had no structured record: {missing_records}")
    if len(results) != n:
        print(f"WARNING: rows_evaluated ({len(results)}) != rows_total ({n})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
