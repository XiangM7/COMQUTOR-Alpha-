#!/usr/bin/env python3
"""QA Closure v0.1.2, Item 2: independent LLM PROVISIONAL review of the
existing 50-row ``docs/evidence_review_sample.csv``.

Genuine human review of that file remains unavailable (every
``reviewer_*`` column is still blank -- see
``docs/audit_artifacts/evidence_review_sample_validation.json``). The user
has explicitly authorized using an independent LLM as a *provisional*
substitute so John's ``polarity_accuracy``/``alpha_match_accuracy`` metrics
can be estimated now. This is NOT human gold and must never be described as
human-reviewed -- every row this script writes carries
``review_source = "independent_llm_provisional"``.

Two review pieces, deliberately handled differently:

1. Stance (``llm_expected_stance``/``llm_counter_alpha_id``): REUSED from
   the existing J3 benchmark
   (``comqutor_alpha/config/j3_provisional_semantic_benchmark_v0.1.json``),
   never re-called. Verified blind: its own source packet
   (``docs/audit_artifacts/j3_llm_blind_review_packet.json``) shows a row
   only ``sample_id/run_id/ticker/claim_id/agent/claim/evidence/
   target_alpha_id/target_alpha_name/target_alpha_definition/
   legal_counter_alphas/source_refs`` -- never any system
   evidence_stance/matched_alpha_id/match_score/stance_reason_codes.

2. Everything the J3 schema does not contain -- ``llm_expected_alpha_id``
   (an independent Alpha-Mapper-analogue judgment from the FULL canonical
   taxonomy, deliberately blind to target_alpha_id/matched_alpha_id so it
   cannot just parrot either back), ``llm_should_be_admissible``,
   ``llm_too_generic``, ``llm_ticker_specific``, ``llm_confidence``,
   ``llm_reason`` -- is a NEW real Provider call, batched 10 rows/call (5
   batches). ``llm_duplicate`` is a further, separate single call across
   all 50 claim/evidence texts together (genuine duplication is a
   cross-row judgment, not a per-row one).

Never invokes TradingAgents or starts a research run: uses the same bare
``tradingagents.llm_clients.create_llm_client`` factory
``scripts/run_b1_llm_stance_50_validation.py`` already uses to construct an
LLM client, then calls it directly with this script's own prompts --
never Week2LLMGateway's production task registry (that stays scoped to
production Week 2 tasks; this is a one-off QA review, not a pipeline
stage). Zero production semantic files are imported or modified.

Never modifies ``docs/evidence_review_sample.csv`` or any ``reviewer_*``
field -- those stay reserved for genuine future human review.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
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

SAMPLE_PATH = REPO_ROOT / "docs" / "evidence_review_sample_records.json"
TAXONOMY_PATH = REPO_ROOT / "comqutor_alpha" / "alpha_library" / "alpha_taxonomy_v1.yaml"
J3_BENCHMARK_PATH = REPO_ROOT / "comqutor_alpha" / "config" / "j3_provisional_semantic_benchmark_v0.1.json"
OUTPUT_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "evidence_review_llm_provisional.csv"
CALL_LOG_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "evidence_review_llm_provisional_call_log.json"

REVIEW_SOURCE = "independent_llm_provisional"
EXPECTED_ROW_COUNT = 50
ALPHA_BATCH_SIZE = 10
TIMEOUT_SECONDS = 120.0
MAX_ATTEMPTS_PER_CALL = 3

VALID_STANCES = frozenset(
    {"supports_alpha", "opposes_alpha", "mentions_alpha", "neutral_background", "supports_counter_alpha"}
)
VALID_ADMISSIBLE = frozenset({"yes", "no", "conditional", "unclear"})
VALID_CONFIDENCE = frozenset({"high", "medium", "low"})

CSV_FIELDS = [
    "sample_id",
    "ticker",
    "llm_expected_stance",
    "llm_expected_alpha_id",
    "llm_counter_alpha_id",
    "llm_should_be_admissible",
    "llm_too_generic",
    "llm_ticker_specific",
    "llm_duplicate",
    "llm_confidence",
    "llm_reason",
    "review_source",
    # Extra transparency columns beyond John's minimum required set --
    # never substituted for the required fields above.
    "llm_stance_confidence",
    "llm_stance_reason",
    "llm_stance_source",
]


class ProvisionalReviewError(Exception):
    def __init__(self, reason_code: str, detail: str = "") -> None:
        self.reason_code = reason_code
        self.detail = detail
        super().__init__(f"{reason_code}: {detail}" if detail else reason_code)


def _load_sample() -> list[dict[str, Any]]:
    data = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    records = data["records"]
    if len(records) != EXPECTED_ROW_COUNT:
        raise ProvisionalReviewError("SAMPLE_ROW_COUNT_UNEXPECTED", str(len(records)))
    return records


def _load_taxonomy() -> list[dict[str, Any]]:
    payload = yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))
    return payload["alphas"]


def _taxonomy_prompt_block(alphas: list[dict[str, Any]]) -> str:
    lines = []
    for alpha in alphas:
        conflict_ids = [c["alpha_id"] for c in (alpha.get("conflict_alphas") or [])]
        lines.append(
            f"- {alpha['alpha_id']} ({alpha['name_en']}): {alpha['core_thesis']}"
            + (f" [canonical conflict Alphas: {', '.join(conflict_ids)}]" if conflict_ids else "")
        )
    return "\n".join(lines)


def _load_j3_stance() -> dict[str, dict[str, Any]]:
    """Reuse the existing, already-blind-verified J3 verdicts for stance.
    Never re-called, never re-inferred -- read verbatim from the frozen
    benchmark file."""
    payload = json.loads(J3_BENCHMARK_PATH.read_text(encoding="utf-8"))
    rows = payload["rows"]
    if len(rows) != EXPECTED_ROW_COUNT:
        raise ProvisionalReviewError("J3_BENCHMARK_ROW_COUNT_UNEXPECTED", str(len(rows)))
    by_id = {row["sample_id"]: row for row in rows}
    if len(by_id) != EXPECTED_ROW_COUNT:
        raise ProvisionalReviewError("J3_BENCHMARK_DUPLICATE_SAMPLE_ID")
    return by_id


def _build_llm_client(profile_id: str):
    from dotenv import load_dotenv

    load_dotenv()
    try:
        profile = get_research_profile(profile_id)
    except ResearchProfileError as exc:
        raise ProvisionalReviewError("PROVIDER_CREDENTIALS_MISSING", exc.reason_code) from exc

    from tradingagents.llm_clients import create_llm_client

    client = create_llm_client(
        provider=profile.llm_provider,
        model=profile.quick_think_llm,
        base_url=profile.backend_url,
        timeout=TIMEOUT_SECONDS,
        max_retries=0,
        temperature=0,
        max_tokens=8000,
    )
    return client.get_llm(), profile


def _parse_json_response(content: str) -> dict[str, Any]:
    parsed = json.loads(strip_markdown_json_fence(content).strip())
    if not isinstance(parsed, dict):
        raise ValueError("response is not a JSON object")
    return parsed


def _invoke(model, prompt: str, call_log: list[dict[str, Any]], call_tag: str) -> dict[str, Any]:
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS_PER_CALL + 1):
        started = time.monotonic()
        try:
            response = model.invoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            parsed = _parse_json_response(content)
            call_log.append(
                {
                    "call_tag": call_tag,
                    "attempt": attempt,
                    "status": "OK",
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                }
            )
            return parsed
        except Exception as exc:  # noqa: BLE001 -- must never crash the whole run on one bad call
            last_error = exc
            call_log.append(
                {
                    "call_tag": call_tag,
                    "attempt": attempt,
                    "status": "RETRY" if attempt < MAX_ATTEMPTS_PER_CALL else "FAILED",
                    "error_type": type(exc).__name__,
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                }
            )
    raise ProvisionalReviewError("LLM_CALL_FAILED_AFTER_RETRIES", f"{call_tag}: {type(last_error).__name__}: {last_error}")


ALPHA_QUALITY_INSTRUCTIONS = """You are an independent, blind semantic reviewer for a financial research \
system called COMQUTOR. You are shown a batch of items, each one (ticker, claim, evidence) extracted from \
analyst debate transcripts. You are NOT told what any system, model, or prior reviewer previously judged \
about any item -- no such information exists in your input, and none should be assumed. Judge each item \
completely independently; do not let one item's judgment influence another's.

For EACH item, judge:

1. llm_expected_alpha_id: which ONE canonical Alpha (from the taxonomy below) this evidence most directly \
and substantively supports or opposes, based SOLELY on the evidence text and the taxonomy definitions below \
-- pick the single best-fit primary Alpha. Return "NONE" only when the evidence genuinely does not \
meaningfully engage with any canonical Alpha's core thesis. Do not pick an Alpha merely because a keyword \
appears -- the evidence must substantively engage with that Alpha's thesis.

2. llm_should_be_admissible: relative to the llm_expected_alpha_id you just picked (if you picked "NONE", \
this is always "no"), would this evidence be a legitimate, specific, decision-relevant piece of Bull/Bear \
evidence for that Alpha -- as opposed to vague opinion, speculation, or noise? One of: "yes", "no", \
"conditional", "unclear".

3. llm_too_generic: true if the evidence is generic/context-poor boilerplate that could not reliably \
support any specific Alpha-relative claim (pure industry background, generic market commentary with no \
substantive claim), false otherwise.

4. llm_ticker_specific: true only if the evidence has a genuine, direct, substantive link to the GIVEN \
ticker specifically -- not merely generic commentary that could equally apply to any peer company in the \
same industry. false otherwise.

5. llm_confidence: your own confidence in this judgment -- "high", "medium", or "low".

6. llm_reason: one or two sentences giving the specific semantic basis for your judgment.

Rules:
- Do not classify based on keyword presence alone -- read the full meaning. A claim can mention a topic \
while actually rebutting it (e.g. "the valuation risk argument is a lazy heuristic that ignores the actual \
numbers" is a REBUTTAL of valuation risk, not an assertion of it).
- Do not infer llm_expected_alpha_id from any field other than the evidence text and the taxonomy \
definitions below.

CANONICAL ALPHA TAXONOMY (pick llm_expected_alpha_id from these IDs, or "NONE"):
{taxonomy_block}

Respond with ONLY a single JSON object, no prose, no markdown fence, of exactly this shape:
{{"results": [{{"sample_id": "...", "llm_expected_alpha_id": "...", "llm_should_be_admissible": "...", \
"llm_too_generic": true, "llm_ticker_specific": true, "llm_confidence": "...", "llm_reason": "..."}}, ...]}}

ITEMS TO REVIEW ({count} items):
{items_block}
"""

DUPLICATE_INSTRUCTIONS = """You are an independent reviewer identifying near-duplicate or paraphrase claims \
within a set of 50 (sample_id, ticker, claim, evidence) items pulled from analyst debate transcripts across \
six different tickers.

Two items are "duplicates/paraphrases of each other" only if they restate substantially the same underlying \
factual claim/evidence in different words -- not merely because they discuss the same broad topic, ticker, \
or Alpha. Items about genuinely different facts, even on the same topic, are NOT duplicates.

Group sample_ids into duplicate/paraphrase clusters. Only include clusters of size 2 or more. Any sample_id \
not listed in any cluster is implicitly not a duplicate of anything else in this set.

Respond with ONLY a single JSON object, no prose, no markdown fence, of exactly this shape:
{{"duplicate_clusters": [["evrs-008", "evrs-036"], ...]}}

ITEMS (50):
{items_block}
"""


def _items_block(rows: list[dict[str, Any]]) -> str:
    parts = []
    for row in rows:
        parts.append(
            f'sample_id: {row["sample_id"]}\nticker: {row["ticker"]}\nclaim: {row["claim"]}\n'
            f'evidence: {row["evidence"]}\n---'
        )
    return "\n".join(parts)


def _run_alpha_quality_calls(
    model, records: list[dict[str, Any]], taxonomy_block: str, call_log: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    batches = [records[i : i + ALPHA_BATCH_SIZE] for i in range(0, len(records), ALPHA_BATCH_SIZE)]
    for batch_index, batch in enumerate(batches):
        prompt = ALPHA_QUALITY_INSTRUCTIONS.format(
            taxonomy_block=taxonomy_block, count=len(batch), items_block=_items_block(batch)
        )
        parsed = _invoke(model, prompt, call_log, f"alpha_quality_batch_{batch_index}")
        batch_results = parsed.get("results")
        if not isinstance(batch_results, list):
            raise ProvisionalReviewError("ALPHA_BATCH_MALFORMED", f"batch {batch_index}: no 'results' list")
        expected_ids = {r["sample_id"] for r in batch}
        seen_ids = set()
        for item in batch_results:
            sid = item.get("sample_id")
            if sid not in expected_ids:
                raise ProvisionalReviewError("ALPHA_BATCH_UNKNOWN_SAMPLE_ID", f"batch {batch_index}: {sid!r}")
            if sid in seen_ids:
                raise ProvisionalReviewError("ALPHA_BATCH_DUPLICATE_SAMPLE_ID", f"batch {batch_index}: {sid!r}")
            seen_ids.add(sid)
            results[sid] = item
        if seen_ids != expected_ids:
            raise ProvisionalReviewError(
                "ALPHA_BATCH_INCOMPLETE", f"batch {batch_index}: missing={sorted(expected_ids - seen_ids)}"
            )
    return results


def _run_duplicate_call(model, records: list[dict[str, Any]], call_log: list[dict[str, Any]]) -> set[str]:
    prompt = DUPLICATE_INSTRUCTIONS.format(items_block=_items_block(records))
    parsed = _invoke(model, prompt, call_log, "duplicate_clustering")
    clusters = parsed.get("duplicate_clusters")
    if not isinstance(clusters, list):
        raise ProvisionalReviewError("DUPLICATE_RESPONSE_MALFORMED", "no 'duplicate_clusters' list")
    all_ids = {r["sample_id"] for r in records}
    duplicate_ids: set[str] = set()
    for cluster in clusters:
        if not isinstance(cluster, list) or len(cluster) < 2:
            continue
        for sid in cluster:
            if sid not in all_ids:
                raise ProvisionalReviewError("DUPLICATE_CLUSTER_UNKNOWN_SAMPLE_ID", str(sid))
            duplicate_ids.add(sid)
    return duplicate_ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Actually make Provider calls.")
    parser.add_argument("--profile-id", default=ANTHROPIC_PROFILE_ID)
    args = parser.parse_args(argv)

    if not args.execute:
        print("BLOCKED: pass --execute to actually make Provider calls.", file=sys.stderr)
        return 1

    records = _load_sample()
    taxonomy_alphas = _load_taxonomy()
    taxonomy_block = _taxonomy_prompt_block(taxonomy_alphas)
    known_alpha_ids = {a["alpha_id"] for a in taxonomy_alphas}
    j3_stance = _load_j3_stance()

    sample_ids = [r["sample_id"] for r in records]
    if len(set(sample_ids)) != EXPECTED_ROW_COUNT:
        raise ProvisionalReviewError("SAMPLE_DUPLICATE_SAMPLE_ID")
    if set(sample_ids) != set(j3_stance.keys()):
        raise ProvisionalReviewError(
            "SAMPLE_J3_IDENTITY_MISMATCH",
            f"only-in-sample={sorted(set(sample_ids) - set(j3_stance.keys()))}, "
            f"only-in-j3={sorted(set(j3_stance.keys()) - set(sample_ids))}",
        )

    model, profile = _build_llm_client(args.profile_id)
    call_log: list[dict[str, Any]] = []

    alpha_quality_results = _run_alpha_quality_calls(model, records, taxonomy_block, call_log)
    duplicate_ids = _run_duplicate_call(model, records, call_log)

    rows_out = []
    for record in records:
        sid = record["sample_id"]
        j3_row = j3_stance[sid]
        aq = alpha_quality_results[sid]

        stance = j3_row["reviewed_stance"]
        if stance not in VALID_STANCES:
            raise ProvisionalReviewError("INVALID_STANCE_FROM_J3", f"{sid}: {stance!r}")
        stance_counter_alpha_id = j3_row.get("reviewed_counter_alpha_id")

        alpha_id = aq.get("llm_expected_alpha_id")
        if alpha_id != "NONE" and alpha_id not in known_alpha_ids:
            raise ProvisionalReviewError("INVALID_ALPHA_ID", f"{sid}: {alpha_id!r}")

        admissible = aq.get("llm_should_be_admissible")
        if admissible not in VALID_ADMISSIBLE:
            raise ProvisionalReviewError("INVALID_ADMISSIBLE_VALUE", f"{sid}: {admissible!r}")

        confidence = aq.get("llm_confidence")
        if confidence not in VALID_CONFIDENCE:
            raise ProvisionalReviewError("INVALID_CONFIDENCE_VALUE", f"{sid}: {confidence!r}")

        stance_confidence = j3_row.get("review_confidence")
        if stance_confidence not in VALID_CONFIDENCE:
            raise ProvisionalReviewError("INVALID_STANCE_CONFIDENCE_FROM_J3", f"{sid}: {stance_confidence!r}")

        rows_out.append(
            {
                "sample_id": sid,
                "ticker": record["ticker"],
                "llm_expected_stance": stance,
                "llm_expected_alpha_id": alpha_id,
                "llm_counter_alpha_id": stance_counter_alpha_id or "",
                "llm_should_be_admissible": admissible,
                "llm_too_generic": bool(aq.get("llm_too_generic")),
                "llm_ticker_specific": bool(aq.get("llm_ticker_specific")),
                "llm_duplicate": sid in duplicate_ids,
                "llm_confidence": confidence,
                "llm_reason": aq.get("llm_reason") or "",
                "review_source": REVIEW_SOURCE,
                "llm_stance_confidence": stance_confidence,
                "llm_stance_reason": j3_row.get("review_reason") or "",
                "llm_stance_source": "j3_provisional_semantic_benchmark_v0.1_reused",
            }
        )

    if len(rows_out) != EXPECTED_ROW_COUNT:
        raise ProvisionalReviewError("OUTPUT_ROW_COUNT_UNEXPECTED", str(len(rows_out)))
    if len({r["sample_id"] for r in rows_out}) != EXPECTED_ROW_COUNT:
        raise ProvisionalReviewError("OUTPUT_DUPLICATE_SAMPLE_ID")

    OUTPUT_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows_out)

    call_summary = {
        "provider": profile.llm_provider,
        "model_name": profile.quick_think_llm,
        "total_logical_calls": len({c["call_tag"] for c in call_log}),
        "total_provider_attempts": len(call_log),
        "calls": call_log,
    }
    CALL_LOG_PATH.write_text(json.dumps(call_summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {len(rows_out)} rows to {OUTPUT_CSV_PATH}")
    print(
        f"Provider: {profile.llm_provider}/{profile.quick_think_llm} -- "
        f"{call_summary['total_logical_calls']} logical calls, "
        f"{call_summary['total_provider_attempts']} total attempts (incl. retries)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
