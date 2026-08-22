#!/usr/bin/env python3
"""QA Closure v0.1.2 -- Item 2 Blind Holdout #4, Phase 3: independent blind
Alpha reviewer.

A genuinely separate Provider call sequence/session from the production
Pure-LLM Alpha inference phase -- its own gateway/client construction, no
shared conversation context, no cached prior answers, no shared prompt text
(task spec section 11). The reviewer sees ONLY sample_id/ticker/claim/
evidence and the FULL canonical 10-Alpha taxonomy -- never
current_matched_alpha, never deterministic_top_alpha, never any production
score/candidate/rank/eligibility/AI-gate/fallback/B1/match_status field, and
never any historical Holdout label (task spec section 11).

The reviewer prompt below is frozen before this script is ever run against
real H4 data and is not altered after seeing any result (task spec section
13). Adapted from the proven Holdout #3 reviewer script/prompt
(scripts/run_item2_blind_holdout3_alpha_review.py), with one deliberate
wording addition: an explicit "select the single best Alpha rather than
abstaining merely because more than one plausibly fits" instruction (task
spec section 12), matching the level of precision the production
alpha_classifier v3 prompt itself was given -- so the reviewer is held to
the same semantic standard as the system it is measuring, rather than being
more (or less) willing to defer to NONE on a close call.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.research_profiles import (  # noqa: E402
    ANTHROPIC_PROFILE_ID,
    ResearchProfileError,
    get_research_profile,
)
from comqutor_alpha.structure_engine.week2_llm import strip_markdown_json_fence  # noqa: E402

FROZEN_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout4_frozen.csv"
TAXONOMY_PATH = REPO_ROOT / "comqutor_alpha" / "alpha_library" / "alpha_taxonomy_v1.yaml"
OUTPUT_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout4_alpha_review.json"
PROVIDER_AUDIT_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout4_provider_audit.json"

BATCH_SIZE = 10
MAX_ATTEMPTS_PER_BATCH = 3
TIMEOUT_SECONDS = 120.0
REVIEW_SOURCE = "independent_llm_blind_holdout4"
REVIEWER_PROMPT_VERSION = "item2_blind_holdout4.independent_alpha_reviewer.v1"

VALID_CONFIDENCE = frozenset({"high", "medium", "low"})

# Frozen BEFORE any reviewer inference is run; never altered after seeing a
# result (task spec section 13).
INSTRUCTIONS = """You are an independent, blind semantic reviewer for a financial research system called COMQUTOR. \
You are shown a batch of items, each one (ticker, claim, evidence) extracted from analyst debate transcripts. You \
are NOT told what any system, model, or prior reviewer previously judged about any item -- no such information \
exists in your input, and none should be assumed. You are NOT told which Alpha (if any) any system matched this \
evidence to -- you must judge this completely fresh, from the evidence text and the taxonomy alone. Judge each \
item completely independently; do not let one item's judgment influence another's.

For each item, classify the Evidence semantically against the FULL canonical Alpha taxonomy below. Choose the \
single Alpha whose thesis/mechanism is the BEST semantic fit -- never merely because keywords overlap. Several \
Alphas can share overlapping keywords or topics; for overlapping Alpha families, judge the actual causal/economic \
thesis expressed in the Evidence, not surface word overlap. If more than one Alpha plausibly fits, compare them \
directly against each other and select the SINGLE BEST one -- a difficult or close classification is still a \
classification task, and expected_alpha_id="NONE" is not a way to avoid choosing between two or more plausible \
Alphas; do not abstain merely because the choice is close. Return expected_alpha_id = "NONE" only when no \
canonical Alpha materially fits well enough to justify a semantic mapping -- do not force generic or background \
Evidence into an Alpha merely because a related one exists in the taxonomy.

For each item return exactly:
- sample_id: echoed back exactly as given
- expected_alpha_id: one canonical alpha_id from the taxonomy below, or "NONE"
- confidence: one of "high", "medium", "low"
- reason: one or two sentences

CANONICAL ALPHA TAXONOMY (pick expected_alpha_id from these IDs, or "NONE"):
{taxonomy_block}

Respond with ONLY a single JSON object, no prose, no markdown fence, of exactly this shape:
{{"results": [{{"sample_id": "...", "expected_alpha_id": "...", "confidence": "...", "reason": "..."}}, ...]}}

ITEMS TO REVIEW ({count} items):
{items_block}
"""


class ReviewError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _load_frozen_rows() -> list[dict[str, Any]]:
    with FROZEN_CSV_PATH.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _load_taxonomy() -> list[dict[str, Any]]:
    return yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))["alphas"]


def _taxonomy_prompt_block(alphas: list[dict[str, Any]]) -> str:
    return "\n".join(f"- {alpha['alpha_id']} ({alpha['name_en']}): {alpha['core_thesis']}" for alpha in alphas)


def _items_block(rows: list[dict[str, Any]]) -> str:
    parts = []
    for row in rows:
        parts.append(f'sample_id: {row["sample_id"]}\nticker: {row["ticker"]}\nclaim: {row["claim"]}\nevidence: {row["evidence"]}\n---')
    return "\n".join(parts)


def _parse_json_response(content: str) -> dict[str, Any]:
    parsed = json.loads(strip_markdown_json_fence(content).strip())
    if not isinstance(parsed, dict):
        raise ValueError("response is not a JSON object")
    return parsed


def _invoke(model, prompt: str, call_log: list[dict[str, Any]], call_tag: str) -> dict[str, Any]:
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS_PER_BATCH + 1):
        started = time.monotonic()
        try:
            response = model.invoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            parsed = _parse_json_response(content)
            call_log.append({"call_tag": call_tag, "attempt": attempt, "status": "OK", "elapsed_seconds": round(time.monotonic() - started, 2)})
            return parsed
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            call_log.append(
                {"call_tag": call_tag, "attempt": attempt, "status": "RETRY" if attempt < MAX_ATTEMPTS_PER_BATCH else "FAILED",
                 "error_type": type(exc).__name__, "elapsed_seconds": round(time.monotonic() - started, 2)}
            )
    raise ReviewError("LLM_CALL_FAILED_AFTER_RETRIES", f"{call_tag}: {type(last_error).__name__}: {last_error}")


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
    taxonomy_alphas = _load_taxonomy()
    known_alpha_ids = {a["alpha_id"] for a in taxonomy_alphas}
    taxonomy_block = _taxonomy_prompt_block(taxonomy_alphas)

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

    # Independent client construction -- no session/conversation state
    # shared with the production Alpha inference phase's own gateway/client
    # instance.
    client = create_llm_client(
        provider=profile.llm_provider, model=profile.quick_think_llm, base_url=profile.backend_url,
        timeout=TIMEOUT_SECONDS, max_retries=0, temperature=0, max_tokens=8000,
    )
    model = client.get_llm()
    call_log: list[dict[str, Any]] = []
    malformed_batches: list[str] = []

    results_by_id: dict[str, dict[str, Any]] = {}
    batches = [rows[i : i + BATCH_SIZE] for i in range(0, n, BATCH_SIZE)]
    for batch_index, batch in enumerate(batches):
        prompt = INSTRUCTIONS.format(taxonomy_block=taxonomy_block, count=len(batch), items_block=_items_block(batch))
        try:
            parsed = _invoke(model, prompt, call_log, f"alpha_review_batch_{batch_index}")
        except ReviewError:
            malformed_batches.append(f"alpha_review_batch_{batch_index}")
            raise
        batch_results = parsed.get("results")
        if not isinstance(batch_results, list):
            malformed_batches.append(f"alpha_review_batch_{batch_index}")
            raise ReviewError("BATCH_MALFORMED", f"batch {batch_index}: no 'results' list")
        expected_ids = {r["sample_id"] for r in batch}
        seen_ids: set[str] = set()
        for item in batch_results:
            sid = item.get("sample_id")
            if sid not in expected_ids:
                raise ReviewError("BATCH_UNKNOWN_SAMPLE_ID", f"batch {batch_index}: {sid!r}")
            if sid in seen_ids:
                raise ReviewError("BATCH_DUPLICATE_SAMPLE_ID", f"batch {batch_index}: {sid!r}")
            seen_ids.add(sid)
            results_by_id[sid] = item
        if seen_ids != expected_ids:
            raise ReviewError("BATCH_INCOMPLETE", f"batch {batch_index}: missing={sorted(expected_ids - seen_ids)}")

    out_results: dict[str, Any] = {}
    for row in rows:
        sid = row["sample_id"]
        item = results_by_id[sid]
        expected_alpha = item.get("expected_alpha_id")
        if expected_alpha != "NONE" and expected_alpha not in known_alpha_ids:
            raise ReviewError("INVALID_ALPHA_ID", f"{sid}: {expected_alpha!r}")
        confidence = item.get("confidence")
        if confidence not in VALID_CONFIDENCE:
            raise ReviewError("INVALID_CONFIDENCE", f"{sid}: {confidence!r}")
        out_results[sid] = {
            "sample_id": sid,
            "reviewer_expected_alpha_id": expected_alpha,
            "confidence": confidence,
            "reason": item.get("reason") or "",
            "review_source": REVIEW_SOURCE,
        }

    if len(out_results) != n:
        raise ReviewError("OUTPUT_ROW_COUNT_UNEXPECTED", str(len(out_results)))

    OUTPUT_PATH.write_text(json.dumps(out_results, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    call_summary = {
        "phase": "holdout4_independent_alpha_reviewer",
        "provider": profile.llm_provider, "model_name": profile.quick_think_llm, "temperature": 0,
        "reviewer_prompt_version": REVIEWER_PROMPT_VERSION,
        "total_logical_calls": len({c["call_tag"] for c in call_log}),
        "total_provider_attempts": len(call_log),
        "malformed_batches": malformed_batches,
        "human_review_performed": False,
        "calls": call_log,
    }
    existing_audit = json.loads(PROVIDER_AUDIT_PATH.read_text(encoding="utf-8")) if PROVIDER_AUDIT_PATH.exists() else {}
    existing_audit["holdout4_independent_alpha_reviewer"] = call_summary
    PROVIDER_AUDIT_PATH.write_text(json.dumps(existing_audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Wrote {len(out_results)} rows -> {OUTPUT_PATH}")
    print(f"{call_summary['total_logical_calls']} logical calls, {call_summary['total_provider_attempts']} attempts, malformed_batches={len(malformed_batches)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
