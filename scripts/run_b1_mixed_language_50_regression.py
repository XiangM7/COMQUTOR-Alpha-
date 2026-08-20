#!/usr/bin/env python3
"""QA Closure v0.1.2 -- B1 Mixed/Contrastive Language Improvement: re-run the
same 50-row sample through the CURRENT production B1 path
(``evidence_stance_llm.apply_llm_stance_upgrade``, the real, unmodified
production function) now that ``week2_llm.py``'s
``evidence_stance_classifier`` prompt has been extended with target-relative
mixed-language resolution guidance.

A pure prompt change cannot be proven from the old, frozen
``b1_llm_stance_50_validation_after_parser_fix.csv`` -- that artifact is
BEFORE evidence and stays untouched as the baseline. This script produces
the AFTER evidence: same 50 sample_ids, same synthetic-match construction
pattern as the original validation script, same gateway/model/budget
discipline, but through the now-updated prompt text.

Mirrors scripts/run_b1_llm_stance_50_validation.py's safety posture: never
invoked automatically, real Provider calls only behind --execute, hard
budget of 5 logical calls (50 rows / 10 per batch), max_retries=0.
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
from comqutor_alpha.structure_engine import (  # noqa: E402
    evidence_stance as es,
    evidence_stance_llm as esl,
)
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway  # noqa: E402

SAMPLE_PATH = REPO_ROOT / "docs" / "evidence_review_sample_records.json"
OUTPUT_JSON_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "b1_mixed_language_50_regression_raw.json"
CALL_LOG_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "b1_mixed_language_provider_call_log.json"

EXPECTED_RECORD_COUNT = 50
MAX_LOGICAL_CALLS = 5
MAX_REAL_PROVIDER_ATTEMPTS = 5
TIMEOUT_SECONDS = 60.0


def _load_sample() -> list[dict[str, Any]]:
    data = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    return data["records"]


def _build_synthetic_matches(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Identical construction to run_b1_llm_stance_50_validation.py's own
    helper: one synthetic match per row, the row's own already-recorded
    deterministic.v1 fields as the starting (fallback) candidate values."""
    matches = []
    for row in records:
        alpha_id = row["target_alpha_id"]
        candidate = {
            "alpha_id": alpha_id,
            "alpha_name": row.get("target_alpha_name"),
            "evidence_stance": row.get("evidence_stance"),
            "counter_alpha_id": row.get("counter_alpha_id"),
            "stance_reason_codes": list(row.get("stance_reason_codes") or []),
            "stance_confidence_band": row.get("stance_confidence_band"),
            "requires_manual_review": bool(row.get("requires_manual_review")),
            "evidence_stance_version": es.CLASSIFIER_VERSION,
            "stance_method": None,
            "stance_fallback_reason": None,
        }
        matches.append(
            {
                "run_id": row.get("run_id"),
                "ticker": row.get("ticker"),
                "claim_id": row.get("claim_id"),
                "source_agent_output_id": row.get("source_agent_output_id"),
                "claim": row.get("claim"),
                "evidence": row.get("evidence"),
                "factors": [],
                "matched_alpha": alpha_id,
                "matched_alpha_name": row.get("target_alpha_name"),
                "secondary_alphas": [],
                "match_status": "matched",
                "candidate_scores": [candidate],
                "_sample_id": row.get("sample_id"),
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

    records = _load_sample()
    if len(records) != EXPECTED_RECORD_COUNT:
        print(f"ERROR: expected {EXPECTED_RECORD_COUNT} records, found {len(records)}", file=sys.stderr)
        return 1

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
        provider=profile.llm_provider,
        model=profile.quick_think_llm,
        base_url=profile.backend_url,
        timeout=TIMEOUT_SECONDS,
        max_retries=0,
    )
    model = client.get_llm()

    gateway = Week2LLMGateway(
        model,
        run_id="b1-mixed-language-50-regression",
        output_root=str(REPO_ROOT / "outputs" / "runs"),
        timeout_seconds=TIMEOUT_SECONDS,
        max_retries=0,
        max_calls=MAX_REAL_PROVIDER_ATTEMPTS,
        provider=profile.llm_provider,
        model_name=profile.quick_think_llm,
    )

    taxonomy = load_alpha_taxonomy()
    matches = _build_synthetic_matches(records)

    started = time.monotonic()
    # The real, unmodified production function -- picks up the updated
    # week2_llm._TASK_INSTRUCTIONS["evidence_stance_classifier"] text
    # automatically, since that dict is read at call time, not imported by
    # value anywhere.
    stats = esl.apply_llm_stance_upgrade(matches, taxonomy, llm_gateway=gateway)
    elapsed = time.monotonic() - started

    rows_out = []
    for match in matches:
        candidate = match["candidate_scores"][0]
        rows_out.append(
            {
                "sample_id": match["_sample_id"],
                "claim_id": match["claim_id"],
                "ticker": match["ticker"],
                "target_alpha_id": match["matched_alpha"],
                "after_b1_stance": candidate.get("evidence_stance"),
                "after_b1_counter_alpha_id": candidate.get("counter_alpha_id"),
                "after_b1_stance_method": candidate.get("stance_method"),
                "after_b1_fallback_reason": candidate.get("stance_fallback_reason"),
            }
        )

    OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON_PATH.write_text(json.dumps(rows_out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    call_log = {
        "provider": profile.llm_provider,
        "model_name": profile.quick_think_llm,
        "temperature": "production default (Week2LLMGateway does not override temperature; provider/model default applies, identical setting used by the original 50-row validation and its parser-fix rerun)",
        "prompt_version": "evidence_stance.llm_classifier.v2",
        "batch_count": stats.batch_count,
        "logical_provider_calls": stats.logical_provider_calls,
        "real_provider_attempts": stats.real_provider_attempts,
        "retries_used": 0,
        "llm_result_count": stats.llm_result_count,
        "deterministic_fallback_count": stats.deterministic_fallback_count,
        "fallback_reason_counts": stats.fallback_reason_counts,
        "invalid_llm_output_admitted": stats.invalid_llm_output_admitted,
        "elapsed_seconds": round(elapsed, 2),
    }
    CALL_LOG_PATH.write_text(json.dumps(call_log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(call_log, indent=2))
    print(f"\nWrote {len(rows_out)} rows -> {OUTPUT_JSON_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
