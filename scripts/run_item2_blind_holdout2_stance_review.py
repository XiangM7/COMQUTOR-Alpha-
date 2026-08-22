#!/usr/bin/env python3
"""QA Closure v0.1.2 -- Item 2 Blind Holdout #2, Phase 4: independent stance
reviewer. Deliberately a SEPARATE review task from the Alpha Top-1 reviewer
(task spec section 7) -- this call is shown target_alpha_id (needed to judge
stance relative to it); the Alpha reviewer (phase 6, a different script) is
never shown target_alpha_id or any system output, so it cannot be anchored
by either.

The reviewer sees ONLY: sample_id, ticker, claim, evidence, target_alpha_id
+ name + definition, and the target's legal canonical counter Alphas (name +
definition). It NEVER sees current_b1_stance, stance_method, system reason
code, system confidence, B2/conflict results, or any previous reviewer
label. Real Provider calls, temperature=0, batches of 10. Every batch
validated fail-closed before acceptance; a malformed batch is retried (same
rows, never resampled) up to 3 attempts.
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

HOLDOUT_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout_141_v2.csv"
TAXONOMY_PATH = REPO_ROOT / "comqutor_alpha" / "alpha_library" / "alpha_taxonomy_v1.yaml"
OUTPUT_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout2_independent_stance_review.csv"
CALL_LOG_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout2_provider_call_log.json"

BATCH_SIZE = 10
MAX_ATTEMPTS_PER_BATCH = 3
TIMEOUT_SECONDS = 120.0
REVIEW_SOURCE = "independent_llm_provisional"

VALID_STANCES = frozenset(
    {"supports_alpha", "opposes_alpha", "mentions_alpha", "neutral_background", "supports_counter_alpha"}
)
VALID_CONFIDENCE = frozenset({"high", "medium", "low"})

CSV_FIELDS = [
    "sample_id", "ticker", "target_alpha_id", "llm_expected_stance", "llm_counter_alpha_id",
    "llm_confidence", "llm_reason", "review_source",
]

INSTRUCTIONS = """You are an independent, blind semantic reviewer for a financial research system called COMQUTOR. \
You are shown a batch of items, each one (ticker, claim, evidence, target Alpha) extracted from analyst debate \
transcripts. You are NOT told what any system, model, or prior reviewer previously judged about any item -- no \
such information exists in your input, and none should be assumed. Judge each item completely independently; do \
not let one item's judgment influence another's.

For EACH item, judge the Evidence's stance relative to its OWN target_alpha_id (shown with its name and \
definition below) -- never toward any other Alpha. First ask whether the Evidence contains a substantive, \
independently interpretable assertion relevant to the target Alpha's thesis (a heading, a bare label or score, an \
isolated topic name, a fragment, an instruction, or a watch-item note, judged from actual content never from \
length, has no stance beyond neutral_background). When it does contain such an assertion: use mentions_alpha when \
it directly concerns the target thesis but does not materially support or weaken it; use supports_alpha for a \
material net endorsement of the target thesis, and opposes_alpha for a material net rebuttal or weakening of it. \
When Evidence contains more than one clause bearing on the target thesis, consider all of them together and \
resolve from their combined net implication -- an unresolved/non-directional net implication among clauses that \
do bear on the target thesis is mentions_alpha, not neutral_background. Conditional language ('if', 'could', \
'may', 'would') affects certainty, not whether a stance exists. Only use supports_counter_alpha when the Evidence \
itself materially supports one of this item's own legal_counter_alphas (shown below) -- never merely because it \
opposes the target, never merely because it is mixed, and never merely because another Alpha is mentioned.

Respond with ONLY a single JSON object, no prose, no markdown fence, of exactly this shape:
{{"results": [{{"sample_id": "...", "llm_expected_stance": "...", "llm_counter_alpha_id": null, \
"llm_confidence": "...", "llm_reason": "..."}}, ...]}}

ITEMS TO REVIEW ({count} items):
{items_block}
"""


class ReviewError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _load_holdout_rows() -> list[dict[str, Any]]:
    with HOLDOUT_CSV_PATH.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _taxonomy_by_id() -> dict[str, dict[str, Any]]:
    alphas = yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))["alphas"]
    return {a["alpha_id"]: a for a in alphas}


def _legal_counter_alphas(target_alpha_id: str, by_id: dict[str, dict[str, Any]]) -> list[str]:
    alpha = by_id.get(target_alpha_id)
    if not alpha:
        return []
    return [c["alpha_id"] for c in (alpha.get("conflict_alphas") or [])]


def _items_block(rows: list[dict[str, Any]], by_id: dict[str, dict[str, Any]]) -> str:
    parts = []
    for row in rows:
        target = by_id.get(row["target_alpha_id"], {})
        counters = _legal_counter_alphas(row["target_alpha_id"], by_id)
        counter_defs = "; ".join(f"{cid} ({by_id[cid]['name_en']}): {by_id[cid]['core_thesis']}" for cid in counters if cid in by_id)
        parts.append(
            f'sample_id: {row["sample_id"]}\nticker: {row["ticker"]}\nclaim: {row["claim"]}\n'
            f'evidence: {row["evidence"]}\ntarget_alpha_id: {row["target_alpha_id"]} ({target.get("name_en","?")}): '
            f'{target.get("core_thesis","?")}\nlegal_counter_alphas: {counter_defs or "(none)"}\n---'
        )
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

    rows = _load_holdout_rows()
    by_id = _taxonomy_by_id()
    known_alpha_ids = set(by_id.keys())

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
        prompt = INSTRUCTIONS.format(count=len(batch), items_block=_items_block(batch, by_id))
        parsed = _invoke(model, prompt, call_log, f"stance_review_batch_{batch_index}")
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
        confidence = item.get("llm_confidence")
        if confidence not in VALID_CONFIDENCE:
            raise ReviewError("INVALID_CONFIDENCE", f"{sid}: {confidence!r}")

        out_rows.append(
            {
                "sample_id": sid, "ticker": row["ticker"], "target_alpha_id": row["target_alpha_id"],
                "llm_expected_stance": stance, "llm_counter_alpha_id": counter_alpha_id or "",
                "llm_confidence": confidence, "llm_reason": item.get("llm_reason") or "",
                "review_source": REVIEW_SOURCE,
            }
        )

    if len(out_rows) != len(rows):
        raise ReviewError("OUTPUT_ROW_COUNT_UNEXPECTED", str(len(out_rows)))

    with OUTPUT_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(out_rows)

    call_summary = {
        "provider": profile.llm_provider, "model_name": profile.quick_think_llm, "temperature": 0,
        "total_logical_calls": len({c["call_tag"] for c in call_log}),
        "total_provider_attempts": len(call_log), "calls": call_log,
    }
    existing_log = json.loads(CALL_LOG_PATH.read_text(encoding="utf-8")) if CALL_LOG_PATH.exists() else {}
    existing_log["phase4_stance_review"] = call_summary
    CALL_LOG_PATH.write_text(json.dumps(existing_log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {len(out_rows)} rows -> {OUTPUT_CSV_PATH}")
    print(f"{call_summary['total_logical_calls']} logical calls, {call_summary['total_provider_attempts']} attempts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
