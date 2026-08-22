#!/usr/bin/env python3
"""H4 Reviewer-v2 Development Re-Review, Phase 1: two-stage material-fit
independent blind Alpha reviewer over the exact frozen 200-row Holdout #4
CSV (docs/audit_artifacts/item2_blind_holdout4_frozen.csv).

This is a DEVELOPMENT RE-REVIEW of already-consumed H4 data, not a new
blind acceptance holdout. It exists to correct a discovered reviewer-
protocol defect (forced-choice bias: judging "which Alpha is closest"
instead of "does any Alpha materially fit first").

The reviewer is blind to everything: original reviewer_expected_alpha_id/
confidence, system matched Alpha, deterministic Alpha, correctness, the old
confusion matrix, and the official H4 result. It sees only sample_id/
ticker/claim/evidence + the full canonical taxonomy -- the exact same input
shape as the original H4 reviewer (scripts/run_item2_blind_holdout4_alpha_
review.py), so the ONLY variable that changed is the reviewing protocol
itself, not the information available to it.

Frozen prompt (see item2_h4_reviewer_v2_dev_freeze.json, written before any
call here) is never altered after the first call.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
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
OUTPUT_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_h4_reviewer_v2_dev_alpha_review.json"
PROVIDER_AUDIT_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_h4_reviewer_v2_dev_provider_audit.json"

BATCH_SIZE = 10
MAX_ATTEMPTS_PER_BATCH = 3
TIMEOUT_SECONDS = 120.0
REVIEW_SOURCE = "independent_llm_h4_reviewer_v2_dev"
REVIEWER_PROMPT_VERSION = "item2_h4_reviewer_v2_dev.material_fit_alpha_reviewer.v1"

VALID_CONFIDENCE = frozenset({"high", "medium", "low"})

# Frozen BEFORE any reviewer-v2 call; never altered after the first call
# (task spec section 11/27).
INSTRUCTIONS = """You are an independent, blind semantic reviewer for a financial research system called COMQUTOR. \
You are shown a batch of items, each one (ticker, claim, evidence) extracted from analyst debate transcripts. You \
are NOT told what any system, model, or prior reviewer previously judged about any item -- no such information \
exists in your input, and none should be assumed. Judge each item completely independently; do not let one item's \
judgment influence another's.

For EACH item, follow this exact two-stage procedure against the FULL canonical Alpha taxonomy below.

STAGE 1 -- MATERIAL-FIT GATE. Ask: does the Claim/Evidence materially express, support, oppose, instantiate, or \
directly reason about the core causal/economic mechanism of at least one canonical Alpha? A shared word is NOT \
enough. A generic bullish/bearish statement is NOT enough. A technical indicator (moving average, RSI, MACD, \
breakout level, uptrend/downtrend) is NOT automatically an Alpha. A stock-specific recommendation is NOT \
automatically an Alpha. A catalyst or a price move mentioned on its own is NOT automatically an Alpha. The Evidence \
must materially correspond to the Alpha's economic/causal thesis, not merely resemble one of its keywords or \
confirmation signals. Interpret each Alpha's taxonomy entry hierarchically: its core_thesis (the causal/economic \
mechanism) has semantic priority; trigger/confirmation signals and keywords only help you recognize that thesis, \
they do NOT independently create a match when the core mechanism itself is absent. For example, technical momentum \
alone (a rising moving average, a positive MACD, an RSI breakout, a price uptrend, a technical breakout) does NOT \
by itself establish the Narrative Momentum Alpha -- that Alpha requires material evidence of its own mechanism \
(investor attention, narrative/story/theme attention, crowded positioning, sentiment-driven participation, media/ \
social attention, flows chasing a theme, or reflexive feedback between attention/flows/price); a technical trend \
can CONFIRM that Alpha once its own mechanism is present, but cannot substitute for it. Apply this same principle \
to every Alpha in the taxonomy: never convert a signal or keyword into a semantic thesis match without the actual \
mechanism being present. If NO canonical Alpha materially fits under this test, stop here: reviewer_v2_material_fit \
= false and reviewer_v2_expected_alpha_id = "NONE". NONE is a valid, complete semantic result -- it is not a \
failure and not a penalty for abstaining.

STAGE 2 -- SINGLE BEST (only when Stage 1 finds at least one materially-fitting Alpha). Compare every Alpha that \
materially fits. If exactly one fits, select it. If more than one materially fits, compare them directly against \
each other and select the SINGLE BEST one -- a difficult or close classification between two or more materially- \
fitting Alphas is still a classification task, and NONE is not a way to avoid choosing between them. Uncertainty \
about WHICH valid Alpha is best is a completely different situation from uncertainty about WHETHER any Alpha \
exists at all -- only the second one justifies NONE. Do not become biased toward NONE either: when the Evidence \
clearly expresses a canonical Alpha's own mechanism, select that Alpha even if the wording is short or the claim \
is stated plainly (for example, "cloud providers are sharply raising AI capex, increasing accelerator demand" or \
"enterprise AI agent adoption is driving inference workload growth" or "rich valuation leaves little room for \
disappointment and creates downside multiple risk" each clearly express a real Alpha mechanism and must not become \
NONE merely because they are brief). The governing rule is: material mechanism present -> select the Alpha; no \
material mechanism -> NONE. It is never "when uncertain, always NONE."

reviewer_v2_alpha_confidence describes your confidence in the semantic judgment AFTER applying the material-fit \
gate -- it must never itself decide the outcome. Low confidence does not automatically mean NONE, and high \
confidence does not automatically mean a specific Alpha; all four combinations (a specific Alpha at low confidence, \
NONE at low confidence, a specific Alpha at high confidence, NONE at high confidence) are valid, ordinary outcomes.

For each item return exactly:
- sample_id: echoed back exactly as given
- reviewer_v2_material_fit: true or false (Stage 1 result)
- reviewer_v2_expected_alpha_id: one canonical alpha_id from the taxonomy below when material_fit is true, or \
"NONE" when material_fit is false -- these two fields must always agree (material_fit=false requires \
expected_alpha_id="NONE"; material_fit=true requires a real canonical alpha_id, never "NONE")
- reviewer_v2_alpha_confidence: one of "high", "medium", "low"
- reviewer_v2_alpha_reason: one or two sentences, naming which stage drove the decision

CANONICAL ALPHA TAXONOMY (pick reviewer_v2_expected_alpha_id from these IDs, or "NONE"):
{taxonomy_block}

Respond with ONLY a single JSON object, no prose, no markdown fence, of exactly this shape:
{{"results": [{{"sample_id": "...", "reviewer_v2_material_fit": true, "reviewer_v2_expected_alpha_id": "...", \
"reviewer_v2_alpha_confidence": "...", "reviewer_v2_alpha_reason": "..."}}, ...]}}

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
            parsed = _invoke(model, prompt, call_log, f"reviewer_v2_batch_{batch_index}")
        except ReviewError:
            malformed_batches.append(f"reviewer_v2_batch_{batch_index}")
            raise
        batch_results = parsed.get("results")
        if not isinstance(batch_results, list):
            malformed_batches.append(f"reviewer_v2_batch_{batch_index}")
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
        material_fit = item.get("reviewer_v2_material_fit")
        if not isinstance(material_fit, bool):
            raise ReviewError("INVALID_MATERIAL_FIT", f"{sid}: {material_fit!r}")
        expected_alpha = item.get("reviewer_v2_expected_alpha_id")
        if material_fit:
            if expected_alpha not in known_alpha_ids:
                raise ReviewError("INVARIANT_VIOLATION_MATERIAL_FIT_TRUE_NEEDS_REAL_ALPHA", f"{sid}: {expected_alpha!r}")
        else:
            if expected_alpha != "NONE":
                raise ReviewError("INVARIANT_VIOLATION_MATERIAL_FIT_FALSE_NEEDS_NONE", f"{sid}: {expected_alpha!r}")
        confidence = item.get("reviewer_v2_alpha_confidence")
        if confidence not in VALID_CONFIDENCE:
            raise ReviewError("INVALID_CONFIDENCE", f"{sid}: {confidence!r}")
        out_results[sid] = {
            "sample_id": sid,
            "reviewer_v2_material_fit": material_fit,
            "reviewer_v2_expected_alpha_id": expected_alpha,
            "reviewer_v2_alpha_confidence": confidence,
            "reviewer_v2_alpha_reason": item.get("reviewer_v2_alpha_reason") or "",
            "review_source": REVIEW_SOURCE,
        }

    if len(out_results) != n:
        raise ReviewError("OUTPUT_ROW_COUNT_UNEXPECTED", str(len(out_results)))

    OUTPUT_PATH.write_text(json.dumps(out_results, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    call_summary = {
        "phase": "h4_reviewer_v2_dev_alpha_review",
        "provider": profile.llm_provider, "model_name": profile.quick_think_llm, "temperature": 0,
        "reviewer_prompt_version": REVIEWER_PROMPT_VERSION,
        "prompt_template_sha256": hashlib.sha256(INSTRUCTIONS.encode("utf-8")).hexdigest(),
        "total_logical_calls": len({c["call_tag"] for c in call_log}),
        "total_provider_attempts": len(call_log),
        "malformed_batches": malformed_batches,
        "human_review_performed": False,
        "calls": call_log,
    }
    existing_audit = json.loads(PROVIDER_AUDIT_PATH.read_text(encoding="utf-8")) if PROVIDER_AUDIT_PATH.exists() else {}
    existing_audit["h4_reviewer_v2_dev_alpha_review"] = call_summary
    PROVIDER_AUDIT_PATH.write_text(json.dumps(existing_audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Wrote {len(out_results)} rows -> {OUTPUT_PATH}")
    print(f"{call_summary['total_logical_calls']} logical calls, {call_summary['total_provider_attempts']} attempts, malformed_batches={len(malformed_batches)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
