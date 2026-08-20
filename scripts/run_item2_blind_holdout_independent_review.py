#!/usr/bin/env python3
"""QA Closure v0.1.2 -- Item 2 NEW blind holdout: independent LLM reviewer.

Fresh judgment for all 8 required fields per row in ONE pass (unlike the
old 50-row set, there is no existing J3-equivalent benchmark to reuse here
-- this holdout is entirely new). The reviewer NEVER sees any system
output: no current_b1_stance, no matched_alpha_id/match_score/candidate
ranking/rejection_reason, no old development-set labels, no indication of
row difficulty. Only sample_id/ticker/claim/evidence/target_alpha_id
definition/legal counter Alphas (for the stance question) and the full
10-Alpha taxonomy (for the Alpha question, judged independently of
target_alpha_id) are shown.

Real Provider calls, temperature=0, batches of 10 (10 batches for 100
rows). Every batch validated fail-closed (row count, sample IDs, legal
vocabulary, legal Alpha IDs, legal counter relationships, no missing
judgment) before acceptance; a malformed batch is retried (same rows,
never resampled) up to 3 attempts.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import csv
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

HOLDOUT_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout_100.csv"
TAXONOMY_PATH = REPO_ROOT / "comqutor_alpha" / "alpha_library" / "alpha_taxonomy_v1.yaml"
OUTPUT_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout_independent_review.csv"
CALL_LOG_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout_provider_call_log.json"

EXPECTED_ROW_COUNT = 100
BATCH_SIZE = 10
MAX_ATTEMPTS_PER_BATCH = 3
TIMEOUT_SECONDS = 120.0
REVIEW_SOURCE = "independent_llm_blind_holdout"

VALID_STANCES = frozenset(
    {"supports_alpha", "opposes_alpha", "mentions_alpha", "neutral_background", "supports_counter_alpha"}
)
VALID_ADMISSIBLE = frozenset({"yes", "no", "conditional", "unclear"})
VALID_CONFIDENCE = frozenset({"high", "medium", "low"})

CSV_FIELDS = [
    "sample_id", "ticker", "target_alpha_id", "llm_expected_stance", "llm_counter_alpha_id",
    "llm_expected_alpha_id", "llm_should_be_admissible", "llm_too_generic", "llm_ticker_specific",
    "llm_duplicate", "llm_confidence", "llm_reason", "review_source",
]


class ReviewError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _load_holdout_rows() -> list[dict[str, Any]]:
    with HOLDOUT_CSV_PATH.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _load_taxonomy() -> list[dict[str, Any]]:
    return yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))["alphas"]


def _taxonomy_by_id(alphas: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {a["alpha_id"]: a for a in alphas}


def _taxonomy_prompt_block(alphas: list[dict[str, Any]]) -> str:
    lines = []
    for alpha in alphas:
        conflict_ids = [c["alpha_id"] for c in (alpha.get("conflict_alphas") or [])]
        lines.append(
            f"- {alpha['alpha_id']} ({alpha['name_en']}): {alpha['core_thesis']}"
            + (f" [canonical conflict Alphas: {', '.join(conflict_ids)}]" if conflict_ids else "")
        )
    return "\n".join(lines)


def _legal_counter_alphas(target_alpha_id: str, by_id: dict[str, dict[str, Any]]) -> list[str]:
    alpha = by_id.get(target_alpha_id)
    if not alpha:
        return []
    return [c["alpha_id"] for c in (alpha.get("conflict_alphas") or [])]


INSTRUCTIONS = """You are an independent, blind semantic reviewer for a financial research system called COMQUTOR. \
You are shown a batch of items, each one (ticker, claim, evidence, target Alpha) extracted from analyst debate \
transcripts. You are NOT told what any system, model, or prior reviewer previously judged about any item -- no \
such information exists in your input, and none should be assumed. Judge each item completely independently; do \
not let one item's judgment influence another's.

For EACH item, judge SEVEN things:

1. llm_expected_stance: relative to the item's OWN target_alpha_id (shown below with its name and definition), \
one of: supports_alpha, opposes_alpha, mentions_alpha, neutral_background, supports_counter_alpha. Distinguish \
genuinely endorsing or rebutting the target Alpha's thesis from merely mentioning its subject matter. Read \
negation, rebuttal, qualification, and conditional language on their actual meaning -- a claim can mention a \
topic while actually rebutting it. When Evidence contains both a positive and a negative element, identify which \
part actually bears on the target thesis and resolve from that part alone; use mentions_alpha/neutral_background \
only when the target thesis genuinely cannot be resolved either way.

2. llm_counter_alpha_id: only when llm_expected_stance is supports_counter_alpha, the id of the specific \
canonical counter Alpha the evidence supports (must be one of that item's own legal_counter_alphas, shown below); \
null otherwise. Only use this stance when the Evidence itself materially supports the counter Alpha's own thesis \
-- never merely because it opposes the target, and never merely because the evidence is mixed.

3. llm_expected_alpha_id: independently of target_alpha_id and of your answer to (1) -- which ONE canonical Alpha \
(from the FULL taxonomy below) this evidence most directly and substantively supports or opposes, based SOLELY on \
the evidence text and the taxonomy definitions. Return "NONE" only when the evidence genuinely does not \
meaningfully engage with any canonical Alpha's core thesis. Do not infer this from target_alpha_id -- judge fresh \
from the evidence and the taxonomy.

4. llm_should_be_admissible: relative to the llm_expected_alpha_id you just picked (if "NONE", this is always \
"no"), would this evidence be a legitimate, specific, decision-relevant piece of Bull/Bear evidence for that \
Alpha -- as opposed to vague opinion, speculation, or noise? One of: yes, no, conditional, unclear.

5. llm_too_generic: true if the evidence is generic/context-poor boilerplate that could not reliably support any \
specific Alpha-relative claim, false otherwise.

6. llm_ticker_specific: true only if the evidence has a genuine, direct, substantive link to the GIVEN ticker \
specifically -- not merely generic commentary that could equally apply to any peer company. false otherwise.

7. llm_confidence ("high"/"medium"/"low") and llm_reason (one or two sentences) for your OVERALL judgment on this \
item.

Rules:
- Do not classify based on keyword presence alone -- read the full meaning.
- Do not infer llm_expected_alpha_id from target_alpha_id or from anything other than the evidence text and the \
taxonomy definitions below.

CANONICAL ALPHA TAXONOMY (pick llm_expected_alpha_id from these IDs, or "NONE"):
{taxonomy_block}

Respond with ONLY a single JSON object, no prose, no markdown fence, of exactly this shape:
{{"results": [{{"sample_id": "...", "llm_expected_stance": "...", "llm_counter_alpha_id": null, \
"llm_expected_alpha_id": "...", "llm_should_be_admissible": "...", "llm_too_generic": true, \
"llm_ticker_specific": true, "llm_confidence": "...", "llm_reason": "..."}}, ...]}}

ITEMS TO REVIEW ({count} items):
{items_block}
"""

DUPLICATE_INSTRUCTIONS = """You are an independent reviewer identifying near-duplicate or paraphrase claims \
within a set of 100 (sample_id, ticker, claim, evidence) items pulled from analyst debate transcripts across six \
different tickers.

Two items are "duplicates/paraphrases of each other" only if they restate substantially the same underlying \
factual claim/evidence in different words -- not merely because they discuss the same broad topic, ticker, or \
Alpha. Items about genuinely different facts, even on the same topic, are NOT duplicates.

Group sample_ids into duplicate/paraphrase clusters. Only include clusters of size 2 or more. Any sample_id not \
listed in any cluster is implicitly not a duplicate of anything else in this set.

Respond with ONLY a single JSON object, no prose, no markdown fence, of exactly this shape:
{{"duplicate_clusters": [["holdout-008", "holdout-036"], ...]}}

ITEMS (100):
{items_block}
"""


def _items_block(rows: list[dict[str, Any]], by_id: dict[str, dict[str, Any]]) -> str:
    parts = []
    for row in rows:
        target = by_id.get(row["target_alpha_id"], {})
        legal_counters = _legal_counter_alphas(row["target_alpha_id"], by_id)
        parts.append(
            f'sample_id: {row["sample_id"]}\nticker: {row["ticker"]}\nclaim: {row["claim"]}\n'
            f'evidence: {row["evidence"]}\ntarget_alpha_id: {row["target_alpha_id"]} '
            f'({target.get("name_en", "?")}): {target.get("core_thesis", "?")}\n'
            f'legal_counter_alphas: {legal_counters}\n---'
        )
    return "\n".join(parts)


def _duplicate_items_block(rows: list[dict[str, Any]]) -> str:
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
                {
                    "call_tag": call_tag, "attempt": attempt,
                    "status": "RETRY" if attempt < MAX_ATTEMPTS_PER_BATCH else "FAILED",
                    "error_type": type(exc).__name__, "elapsed_seconds": round(time.monotonic() - started, 2),
                }
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

    rows = _load_holdout_rows()
    if len(rows) != EXPECTED_ROW_COUNT:
        print(f"ERROR: expected {EXPECTED_ROW_COUNT}, found {len(rows)}", file=sys.stderr)
        return 1

    taxonomy_alphas = _load_taxonomy()
    by_id = _taxonomy_by_id(taxonomy_alphas)
    known_alpha_ids = set(by_id.keys())
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

    results_by_id: dict[str, dict[str, Any]] = {}
    batches = [rows[i : i + BATCH_SIZE] for i in range(0, len(rows), BATCH_SIZE)]
    for batch_index, batch in enumerate(batches):
        prompt = INSTRUCTIONS.format(taxonomy_block=taxonomy_block, count=len(batch), items_block=_items_block(batch, by_id))
        parsed = _invoke(model, prompt, call_log, f"review_batch_{batch_index}")
        batch_results = parsed.get("results")
        if not isinstance(batch_results, list):
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

    dup_prompt = DUPLICATE_INSTRUCTIONS.format(items_block=_duplicate_items_block(rows))
    dup_parsed = _invoke(model, dup_prompt, call_log, "duplicate_clustering")
    clusters = dup_parsed.get("duplicate_clusters")
    if not isinstance(clusters, list):
        raise ReviewError("DUPLICATE_RESPONSE_MALFORMED")
    all_ids = {r["sample_id"] for r in rows}
    duplicate_ids: set[str] = set()
    for cluster in clusters:
        if not isinstance(cluster, list) or len(cluster) < 2:
            continue
        for sid in cluster:
            if sid not in all_ids:
                raise ReviewError("DUPLICATE_CLUSTER_UNKNOWN_SAMPLE_ID", str(sid))
            duplicate_ids.add(sid)

    out_rows = []
    for row in rows:
        sid = row["sample_id"]
        item = results_by_id[sid]
        stance = item.get("llm_expected_stance")
        if stance not in VALID_STANCES:
            raise ReviewError("INVALID_STANCE", f"{sid}: {stance!r}")
        counter_alpha_id = item.get("llm_counter_alpha_id")
        legal_counters = set(_legal_counter_alphas(row["target_alpha_id"], by_id))
        if stance == "supports_counter_alpha":
            if not counter_alpha_id or counter_alpha_id not in legal_counters:
                raise ReviewError("ILLEGAL_COUNTER_ALPHA", f"{sid}: {counter_alpha_id!r} not in {sorted(legal_counters)}")
        else:
            counter_alpha_id = None
        expected_alpha = item.get("llm_expected_alpha_id")
        if expected_alpha != "NONE" and expected_alpha not in known_alpha_ids:
            raise ReviewError("INVALID_ALPHA_ID", f"{sid}: {expected_alpha!r}")
        admissible = item.get("llm_should_be_admissible")
        if admissible not in VALID_ADMISSIBLE:
            raise ReviewError("INVALID_ADMISSIBLE", f"{sid}: {admissible!r}")
        confidence = item.get("llm_confidence")
        if confidence not in VALID_CONFIDENCE:
            raise ReviewError("INVALID_CONFIDENCE", f"{sid}: {confidence!r}")

        out_rows.append(
            {
                "sample_id": sid,
                "ticker": row["ticker"],
                "target_alpha_id": row["target_alpha_id"],
                "llm_expected_stance": stance,
                "llm_counter_alpha_id": counter_alpha_id or "",
                "llm_expected_alpha_id": expected_alpha,
                "llm_should_be_admissible": admissible,
                "llm_too_generic": bool(item.get("llm_too_generic")),
                "llm_ticker_specific": bool(item.get("llm_ticker_specific")),
                "llm_duplicate": sid in duplicate_ids,
                "llm_confidence": confidence,
                "llm_reason": item.get("llm_reason") or "",
                "review_source": REVIEW_SOURCE,
            }
        )

    if len(out_rows) != EXPECTED_ROW_COUNT:
        raise ReviewError("OUTPUT_ROW_COUNT_UNEXPECTED", str(len(out_rows)))

    with OUTPUT_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(out_rows)

    call_summary = {
        "provider": profile.llm_provider,
        "model_name": profile.quick_think_llm,
        "temperature": 0,
        "total_logical_calls": len({c["call_tag"] for c in call_log}),
        "total_provider_attempts": len(call_log),
        "calls": call_log,
    }
    existing_log = {}
    if CALL_LOG_PATH.exists():
        existing_log = json.loads(CALL_LOG_PATH.read_text(encoding="utf-8"))
    existing_log["independent_review"] = call_summary
    CALL_LOG_PATH.write_text(json.dumps(existing_log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {len(out_rows)} rows -> {OUTPUT_CSV_PATH}")
    print(f"{call_summary['total_logical_calls']} logical calls, {call_summary['total_provider_attempts']} attempts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
