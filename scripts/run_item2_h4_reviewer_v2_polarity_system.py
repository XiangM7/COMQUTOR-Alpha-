#!/usr/bin/env python3
"""H4 Reviewer-v2 Development Re-Review, Phase 3: run the CURRENT, frozen,
unmodified production B1 v3 path (evidence_stance_llm.apply_llm_stance_
upgrade -- the real production function, never a hand-rolled evaluator)
against the polarity-evaluable subset of H4 (rows where reviewer_v2_
material_fit=true), using reviewer_v2_expected_alpha_id as each row's
target Alpha. Same invocation pattern as the historical formal B1
evaluation (scripts/run_item2_blind_holdout2_b1.py, 123/141=87.23% PASS) --
only the target-Alpha values and the row set differ.

Does NOT change any B1 production rule. Real Provider calls, BATCH_SIZE
production default (unmodified).
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

FROZEN_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout4_frozen.csv"
REVIEWER_V2_ALPHA_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_h4_reviewer_v2_dev_alpha_review.json"
OUTPUT_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_h4_reviewer_v2_dev_polarity_system.json"
PROVIDER_AUDIT_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_h4_reviewer_v2_dev_provider_audit.json"

TIMEOUT_SECONDS = 60.0


def _load_evaluable_rows() -> list[dict[str, Any]]:
    with FROZEN_CSV_PATH.open(encoding="utf-8", newline="") as f:
        frozen_by_id = {r["sample_id"]: r for r in csv.DictReader(f)}
    alpha_v2 = json.loads(REVIEWER_V2_ALPHA_PATH.read_text(encoding="utf-8"))

    rows = []
    for sid, frozen in frozen_by_id.items():
        v2 = alpha_v2[sid]
        if not v2["reviewer_v2_material_fit"]:
            continue
        rows.append(
            {
                "sample_id": sid, "run_id": frozen["run_id"], "ticker": frozen["ticker"],
                "claim_id": frozen["claim_id"], "claim": frozen["claim"], "evidence": frozen["evidence"],
                "target_alpha_id": v2["reviewer_v2_expected_alpha_id"],
            }
        )
    rows.sort(key=lambda r: r["sample_id"])
    return rows


def _build_synthetic_matches(rows: list[dict[str, Any]], taxonomy) -> list[dict[str, Any]]:
    matches = []
    for row in rows:
        alpha_id = row["target_alpha_id"]
        alpha_def = taxonomy.get(alpha_id)
        candidate = {
            "alpha_id": alpha_id, "alpha_name": alpha_def.name_en if alpha_def else None,
            "evidence_stance": None, "counter_alpha_id": None, "stance_reason_codes": [],
            "stance_confidence_band": None, "requires_manual_review": False,
            "evidence_stance_version": None, "stance_method": None, "stance_fallback_reason": None,
        }
        matches.append(
            {
                "run_id": row["run_id"], "ticker": row["ticker"], "claim_id": row["claim_id"],
                "source_agent_output_id": row["claim_id"], "claim": row["claim"], "evidence": row["evidence"],
                "factors": [], "matched_alpha": alpha_id, "matched_alpha_name": candidate["alpha_name"],
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

    rows = _load_evaluable_rows()
    n = len(rows)
    print(f"Polarity-evaluable rows (reviewer_v2_material_fit=true): {n} / 200")

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
        model, run_id="item2-h4-reviewer-v2-dev-polarity", output_root=str(REPO_ROOT / "outputs" / "runs"),
        timeout_seconds=TIMEOUT_SECONDS, max_retries=0, max_calls=max_calls,
        provider=profile.llm_provider, model_name=profile.quick_think_llm,
    )

    taxonomy = load_alpha_taxonomy()
    matches = _build_synthetic_matches(rows, taxonomy)

    started = time.monotonic()
    stats = esl.apply_llm_stance_upgrade(matches, taxonomy, llm_gateway=gateway)
    elapsed = time.monotonic() - started

    out_results: dict[str, Any] = {}
    for match in matches:
        candidate = match["candidate_scores"][0]
        out_results[match["_sample_id"]] = {
            "sample_id": match["_sample_id"], "claim_id": match["claim_id"], "target_alpha_id": match["matched_alpha"],
            "system_b1_stance": candidate.get("evidence_stance"),
            "system_b1_counter_alpha_id": candidate.get("counter_alpha_id"),
            "system_b1_stance_method": candidate.get("stance_method"),
            "system_b1_fallback_reason": candidate.get("stance_fallback_reason"),
            "prompt_version": "evidence_stance.llm_classifier.v3",
            "model": profile.quick_think_llm, "provider": profile.llm_provider,
        }

    if len(out_results) != n:
        print(f"WARNING: rows_evaluated ({len(out_results)}) != rows_total ({n})", file=sys.stderr)

    OUTPUT_PATH.write_text(json.dumps(out_results, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    call_log = {
        "phase": "h4_reviewer_v2_dev_polarity_system",
        "provider": profile.llm_provider, "model_name": profile.quick_think_llm,
        "temperature": "production default (unmodified)", "prompt_version": "evidence_stance.llm_classifier.v3",
        "polarity_evaluable_count": n,
        "batch_count": stats.batch_count, "logical_provider_calls": stats.logical_provider_calls,
        "real_provider_attempts": stats.real_provider_attempts, "retries_used": 0,
        "llm_result_count": stats.llm_result_count, "deterministic_fallback_count": stats.deterministic_fallback_count,
        "fallback_reason_counts": stats.fallback_reason_counts, "invalid_llm_output_admitted": stats.invalid_llm_output_admitted,
        "elapsed_seconds": round(elapsed, 2),
    }
    existing_audit = json.loads(PROVIDER_AUDIT_PATH.read_text(encoding="utf-8")) if PROVIDER_AUDIT_PATH.exists() else {}
    existing_audit["h4_reviewer_v2_dev_polarity_system"] = call_log
    PROVIDER_AUDIT_PATH.write_text(json.dumps(existing_audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(call_log, indent=2))
    print(f"\nWrote {len(out_results)} rows -> {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
