#!/usr/bin/env python3
"""QA Closure v0.1.2 -- Item 2 Blind Holdout #2, Phase 3: run the CURRENT,
frozen production B1 v3 path (evidence_stance_llm.apply_llm_stance_upgrade,
the real, unmodified production function) against all rows of the frozen
Holdout #2 CSV. Real Provider calls, BATCH_SIZE=10 batches (production
default, unmodified). Never invoked automatically; --execute required.
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
from comqutor_alpha.structure_engine import evidence_stance_llm as esl  # noqa: E402
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway  # noqa: E402

HOLDOUT_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout_141_v2.csv"
OUTPUT_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout2_system_stance.csv"
CALL_LOG_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout2_provider_call_log.json"

TIMEOUT_SECONDS = 60.0

CSV_FIELDS = [
    "sample_id", "claim_id", "target_alpha_id", "current_b1_stance", "current_b1_counter_alpha_id",
    "current_b1_stance_method", "current_b1_fallback_reason", "prompt_version", "model", "provider",
]


def _load_holdout_rows() -> list[dict[str, Any]]:
    with HOLDOUT_CSV_PATH.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _build_synthetic_matches(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches = []
    for row in rows:
        alpha_id = row["target_alpha_id"]
        candidate = {
            "alpha_id": alpha_id, "alpha_name": row.get("system_matched_alpha_name"),
            "evidence_stance": None, "counter_alpha_id": None, "stance_reason_codes": [],
            "stance_confidence_band": None, "requires_manual_review": False,
            "evidence_stance_version": None, "stance_method": None, "stance_fallback_reason": None,
        }
        matches.append(
            {
                "run_id": row["source_run_id"], "ticker": row["ticker"], "claim_id": row["claim_id"],
                "source_agent_output_id": row["claim_id"], "claim": row["claim"], "evidence": row["evidence"],
                "factors": [], "matched_alpha": alpha_id, "matched_alpha_name": row.get("system_matched_alpha_name"),
                "secondary_alphas": [], "match_status": "matched", "candidate_scores": [candidate],
                "_sample_id": row["sample_id"],
            }
        )
    return matches


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--profile-id", default=ANTHROPIC_PROFILE_ID)
    args = parser.parse_args(argv)

    if not args.execute:
        print("BLOCKED: pass --execute to actually make Provider calls.", file=sys.stderr)
        return 1

    rows = _load_holdout_rows()
    n = len(rows)
    print(f"Loaded {n} frozen Holdout #2 rows.")

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

    max_calls = (n + esl.BATCH_SIZE - 1) // esl.BATCH_SIZE
    gateway = Week2LLMGateway(
        model, run_id="item2-blind-holdout2-b1", output_root=str(REPO_ROOT / "outputs" / "runs"),
        timeout_seconds=TIMEOUT_SECONDS, max_retries=0, max_calls=max_calls,
        provider=profile.llm_provider, model_name=profile.quick_think_llm,
    )

    taxonomy = load_alpha_taxonomy()
    matches = _build_synthetic_matches(rows)

    started = time.monotonic()
    stats = esl.apply_llm_stance_upgrade(matches, taxonomy, llm_gateway=gateway)
    elapsed = time.monotonic() - started

    out_rows = []
    for match in matches:
        candidate = match["candidate_scores"][0]
        out_rows.append(
            {
                "sample_id": match["_sample_id"], "claim_id": match["claim_id"], "target_alpha_id": match["matched_alpha"],
                "current_b1_stance": candidate.get("evidence_stance"),
                "current_b1_counter_alpha_id": candidate.get("counter_alpha_id") or "",
                "current_b1_stance_method": candidate.get("stance_method"),
                "current_b1_fallback_reason": candidate.get("stance_fallback_reason") or "",
                "prompt_version": "evidence_stance.llm_classifier.v3",
                "model": profile.quick_think_llm, "provider": profile.llm_provider,
            }
        )

    with OUTPUT_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(out_rows)

    call_log = {
        "provider": profile.llm_provider, "model_name": profile.quick_think_llm,
        "temperature": "production default (unmodified)", "prompt_version": "evidence_stance.llm_classifier.v3",
        "batch_count": stats.batch_count, "logical_provider_calls": stats.logical_provider_calls,
        "real_provider_attempts": stats.real_provider_attempts, "retries_used": 0,
        "llm_result_count": stats.llm_result_count, "deterministic_fallback_count": stats.deterministic_fallback_count,
        "fallback_reason_counts": stats.fallback_reason_counts, "invalid_llm_output_admitted": stats.invalid_llm_output_admitted,
        "elapsed_seconds": round(elapsed, 2),
    }
    CALL_LOG_PATH.write_text(json.dumps({"phase3_b1_evaluation": call_log}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(call_log, indent=2))
    print(f"\nWrote {len(out_rows)} rows -> {OUTPUT_CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
