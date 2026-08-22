#!/usr/bin/env python3
"""Blind Holdout #5: independent model semantic review (Alpha material-fit +
single-best Alpha + polarity + note), run BLIND to all H5 production Alpha/
B1 outputs, before any system inference on H5 begins.

review_source = "independent_model_review"; human_review_performed = False.
This is NOT a human review -- see item2_blind_holdout5_review_manifest.json
for the full, truthful provenance record.

Two-stage protocol per row, in one combined pass (task spec sections 7-13):
  Stage 1 -- material-fit EXISTENCE gate (does the Evidence materially
  express/support/weaken/discuss at least one canonical Alpha's own causal/
  economic mechanism?). Keyword overlap, price moves, technical momentum
  (MACD/SMA/RSI/breakout/support-resistance), generic bullish/bearish tone,
  a bare BUY/SELL recommendation, or "generally AI-related" text are all
  explicitly insufficient on their own.
  Stage 2 -- only if Stage 1 = true: select the SINGLE best canonical Alpha.
  A601 (Narrative Momentum) specifically requires an attention/narrative/
  crowding/reflexive-flow mechanism; technical momentum alone never
  qualifies (task spec section 10).
  Polarity -- only if Stage 1 = true: classify the Evidence's stance toward
  the just-selected target Alpha using the existing five-class B1 contract
  (supports_alpha/opposes_alpha/mentions_alpha/neutral_background/
  supports_counter_alpha). Blank when material_fit = false.

Session-isolated: independent client construction, no shared conversation/
session state with production inference or any other review phase.

Input fields shown to the reviewer per item: sample_id, ticker, claim,
evidence, and the full canonical taxonomy. Never shown: any H5 production
Alpha output, B1 output, deterministic ranking, candidate score,
match_status, historical reviewer label, or correctness field.
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
from comqutor_alpha.structure_engine.week2_llm import strip_markdown_json_fence  # noqa: E402

FROZEN_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout5_frozen.csv"
REVIEW_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "evidence_review_sample_h5.csv"
TAXONOMY_PATH = REPO_ROOT / "comqutor_alpha" / "alpha_library" / "alpha_taxonomy_v1.yaml"
PROVIDER_AUDIT_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout5_provider_audit.json"

BATCH_SIZE = 10
MAX_ATTEMPTS_PER_BATCH = 3
TIMEOUT_SECONDS = 120.0
REVIEW_SOURCE = "independent_model_review"
REVIEWER_PROMPT_VERSION = "item2_blind_holdout5.material_fit_alpha_and_polarity_reviewer.v1"

VALID_CONFIDENCE = frozenset({"high", "medium", "low"})
VALID_STANCES = frozenset({"supports_alpha", "opposes_alpha", "mentions_alpha", "neutral_background", "supports_counter_alpha"})

INSTRUCTIONS = """You are an independent semantic reviewer for a financial-analysis Evidence \
classification benchmark. For EACH item below, decide whether the Evidence text materially \
fits one canonical Alpha from the taxonomy provided, and if so, which one and what stance it \
takes toward that Alpha.

You are NOT told what any production system predicted for these items. Judge purely from the \
Claim/Evidence text and the taxonomy definitions below.

===========================================================
STAGE 1 -- MATERIAL-FIT EXISTENCE TEST (ask this FIRST)
===========================================================
Does the Evidence materially express, support, weaken, or directly discuss the underlying \
CAUSAL/ECONOMIC MECHANISM of at least one canonical Alpha below?

This is an EXISTENCE test, not a "which is closest" test. Do NOT start by asking "which Alpha \
is closest" -- ask whether ANY Alpha's actual mechanism is materially present at all.

Do NOT force a mapping merely because:
- a keyword overlaps with an Alpha's keyword list
- the stock price moved
- technical momentum exists (rising/falling trend)
- MACD is positive or negative
- a moving average (SMA) is rising or falling
- a support/resistance level or breakout is mentioned
- generic bullish/bearish language is present
- an analyst recommends BUY/SELL/HOLD
- the company is generically "AI-related" with no specific mechanism stated

If NO canonical Alpha materially fits: human_material_alpha_fit = false, \
human_expected_alpha_id = "NONE". This is a normal, valid, non-penalized result -- do not avoid it.

===========================================================
STAGE 2 -- SINGLE BEST ALPHA (only if Stage 1 = true)
===========================================================
Select exactly ONE canonical Alpha -- the one whose core causal/economic thesis is the DOMINANT \
mechanism actually expressed by the Evidence. Never output more than one Alpha, never give \
Top-3/partial credit, never choose a weak approximate Alpha merely to avoid NONE.

Read each Alpha's taxonomy entry in this priority order:
  1. core thesis (the causal/economic mechanism itself) -- this has semantic priority
  2. trigger / confirmation signals -- these help RECOGNIZE the thesis, they never SUBSTITUTE \
for it
  3. keywords -- weakest signal; a shared word alone never creates an Alpha

--- Special rule: A601 Narrative Momentum ---
A601 specifically requires a material mechanism involving investor attention, narrative/theme \
attention, sentiment-driven participation, crowded positioning, reflexive flows, media/social \
attention, flows chasing a theme, or an attention -> flows -> price -> more-attention loop.
Technical momentum ALONE is NOT A601. None of the following, by themselves, establish A601: \
rising SMA, positive MACD, a bullish technical trend, a breakout, RSI readings, price momentum, \
a support level, or higher highs. These may CONFIRM A601 only once an actual narrative/\
attention/flow mechanism is already present in the Evidence -- they never substitute for it.

===========================================================
CONFIDENCE
===========================================================
human_alpha_confidence in {{high, medium, low}} measures your certainty in the Stage \
1/2 judgment itself. It does NOT control whether NONE is legal. All combinations are legal: \
NONE+high, NONE+medium, NONE+low, A301+high, A601+low, etc.

===========================================================
POLARITY (only fill in if human_expected_alpha_id != "NONE")
===========================================================
If material_alpha_fit = false: human_polarity MUST be null/blank. Never assign a polarity to NONE.

If material_alpha_fit = true: classify the Evidence's stance RELATIVE TO THE ALPHA YOU JUST \
SELECTED, using exactly one of these five classes:
- supports_alpha: substantive Evidence materially strengthens/endorses the target Alpha thesis.
- opposes_alpha: substantive Evidence materially weakens, rebuts, or contradicts the target \
Alpha thesis.
- mentions_alpha: Evidence directly discusses the target Alpha's mechanism but has no clear net \
supporting or opposing direction.
- neutral_background: Evidence is contextual/background information with no substantive stance \
toward the target thesis.
- supports_counter_alpha: Evidence materially supports a valid COUNTER-thesis (one of the \
target Alpha's own listed conflict Alphas, shown per item below) rather than merely opposing \
the target in generic terms. If you choose this, name the specific counter Alpha id inside \
human_review_note (there is no separate counter-Alpha column).

Bullish/bearish stock TONE alone is NOT polarity. Polarity must be about the target Alpha's own \
thesis specifically, not generic sentiment about the stock.

===========================================================
REVIEW NOTE
===========================================================
human_review_note: a concise semantic reason, approximately 5-20 words, e.g. "technical \
momentum only; no canonical Alpha mechanism" or "AI capex directly supports infrastructure \
buildout demand". Never mention any system prediction (you were not shown any).

===========================================================
CANONICAL ALPHA TAXONOMY (the complete, only legal set of non-NONE answers)
===========================================================
{taxonomy_block}

===========================================================
OUTPUT FORMAT
===========================================================
Return ONLY a JSON object: {{"results": [{{"sample_id": "...", "human_material_alpha_fit": \
true/false, "human_expected_alpha_id": "Axxx or NONE", "human_alpha_confidence": \
"high/medium/low", "human_polarity": "one of the five classes, or null if NONE", \
"human_review_note": "..."}}, ...]}}
One entry per item below, sample_id echoed back exactly. No prose outside the JSON.

===========================================================
ITEMS
===========================================================
{items_block}
"""


def _taxonomy_block(taxonomy: dict[str, Any]) -> str:
    parts = []
    for alpha_id in sorted(taxonomy.keys()):
        a = taxonomy[alpha_id]
        conflicts = ", ".join(c.alpha_id for c in a.conflict_alphas) if a.conflict_alphas else "(none)"
        parts.append(
            f"[{alpha_id}] {a.name_en}\n"
            f"  core_thesis: {a.core_thesis}\n"
            f"  trigger_signals: {'; '.join(a.trigger_signals) if a.trigger_signals else '(none)'}\n"
            f"  confirmation_signals: {'; '.join(a.confirmation_signals) if a.confirmation_signals else '(none)'}\n"
            f"  invalidation_conditions: {'; '.join(a.invalidation_conditions) if a.invalidation_conditions else '(none)'}\n"
            f"  keywords: {', '.join(a.keywords) if a.keywords else '(none)'}\n"
            f"  legal_counter_alphas (for supports_counter_alpha): {conflicts}"
        )
    return "\n\n".join(parts)


def _items_block(rows: list[dict[str, Any]]) -> str:
    parts = []
    for row in rows:
        parts.append(
            f"sample_id: {row['sample_id']}\n"
            f"ticker: {row['ticker']}\n"
            f"claim: {row['claim']}\n"
            f"evidence: {row['evidence']}"
        )
    return "\n\n---\n\n".join(parts)


def _load_frozen_rows() -> list[dict[str, Any]]:
    with FROZEN_CSV_PATH.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--profile-id", default=ANTHROPIC_PROFILE_ID)
    args = parser.parse_args(argv)

    if not args.execute:
        print("BLOCKED: pass --execute to actually make Provider calls.", file=sys.stderr)
        return 1

    rows = _load_frozen_rows()
    if len(rows) != 200:
        print(f"BLOCKED: expected 200 rows, found {len(rows)}", file=sys.stderr)
        return 1

    taxonomy = load_alpha_taxonomy()
    known_alpha_ids = set(taxonomy.keys())
    taxonomy_block = _taxonomy_block(taxonomy)

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

    results: dict[str, dict[str, Any]] = {}
    call_log = []
    malformed_batches = []

    batches = [rows[i : i + BATCH_SIZE] for i in range(0, len(rows), BATCH_SIZE)]
    for batch_index, batch in enumerate(batches):
        prompt = INSTRUCTIONS.format(taxonomy_block=taxonomy_block, items_block=_items_block(batch))
        expected_ids = {r["sample_id"] for r in batch}
        ok = False
        for attempt in range(1, MAX_ATTEMPTS_PER_BATCH + 1):
            started = time.monotonic()
            try:
                response = model.invoke(prompt)
                text = response.content if hasattr(response, "content") else str(response)
                payload = json.loads(strip_markdown_json_fence(text).strip())
                batch_results = payload["results"]
                got_ids = {r["sample_id"] for r in batch_results}
                if got_ids != expected_ids:
                    raise ValueError(f"sample_id mismatch: missing={expected_ids - got_ids} extra={got_ids - expected_ids}")
                for r in batch_results:
                    sid = r["sample_id"]
                    material_fit = r["human_material_alpha_fit"]
                    if not isinstance(material_fit, bool):
                        raise ValueError(f"{sid}: human_material_alpha_fit not bool: {material_fit!r}")
                    expected_alpha = r["human_expected_alpha_id"]
                    confidence = r["human_alpha_confidence"]
                    polarity = r.get("human_polarity")
                    note = r.get("human_review_note") or ""
                    if material_fit:
                        if expected_alpha not in known_alpha_ids:
                            raise ValueError(f"INVARIANT_VIOLATION_MATERIAL_FIT_TRUE_NEEDS_REAL_ALPHA: {sid}: {expected_alpha!r}")
                        if polarity not in VALID_STANCES:
                            raise ValueError(f"INVARIANT_VIOLATION_ALPHA_ROW_NEEDS_POLARITY: {sid}: {polarity!r}")
                    else:
                        if expected_alpha != "NONE":
                            raise ValueError(f"INVARIANT_VIOLATION_MATERIAL_FIT_FALSE_NEEDS_NONE: {sid}: {expected_alpha!r}")
                        if polarity not in (None, "", "null"):
                            raise ValueError(f"INVARIANT_VIOLATION_NONE_ROW_MUST_HAVE_BLANK_POLARITY: {sid}: {polarity!r}")
                        polarity = ""
                    if confidence not in VALID_CONFIDENCE:
                        raise ValueError(f"{sid}: invalid confidence {confidence!r}")
                    if not note.strip():
                        raise ValueError(f"{sid}: empty human_review_note")
                    results[sid] = {
                        "sample_id": sid,
                        "human_material_alpha_fit": "true" if material_fit else "false",
                        "human_expected_alpha_id": expected_alpha,
                        "human_alpha_confidence": confidence,
                        "human_polarity": polarity or "",
                        "human_review_note": note.strip(),
                    }
                elapsed = time.monotonic() - started
                call_log.append({"batch": batch_index, "attempt": attempt, "status": "OK", "elapsed_seconds": round(elapsed, 2)})
                ok = True
                break
            except Exception as exc:  # noqa: BLE001
                elapsed = time.monotonic() - started
                call_log.append(
                    {"batch": batch_index, "attempt": attempt, "status": "ERROR", "error": str(exc)[:300], "elapsed_seconds": round(elapsed, 2)}
                )
        if not ok:
            malformed_batches.append(batch_index)

    if malformed_batches:
        print(f"BLOCKED: malformed_batches={malformed_batches}; no rows left unreviewed silently.", file=sys.stderr)
        return 1

    if len(results) != 200:
        print(f"BLOCKED: reviewed {len(results)} != 200", file=sys.stderr)
        return 1

    # Write results into the existing evidence_review_sample_h5.csv's five blank columns.
    with REVIEW_CSV_PATH.open(encoding="utf-8", newline="") as f:
        existing_rows = list(csv.DictReader(f))
        fieldnames = list(existing_rows[0].keys())
    for row in existing_rows:
        r = results[row["sample_id"]]
        row["human_material_alpha_fit"] = r["human_material_alpha_fit"]
        row["human_expected_alpha_id"] = r["human_expected_alpha_id"]
        row["human_alpha_confidence"] = r["human_alpha_confidence"]
        row["human_polarity"] = r["human_polarity"]
        row["human_review_note"] = r["human_review_note"]
    with REVIEW_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing_rows)

    audit = {
        "phase": "item2_blind_holdout5_review",
        "review_source": REVIEW_SOURCE,
        "human_review_performed": False,
        "reviewer_prompt_version": REVIEWER_PROMPT_VERSION,
        "provider": profile.llm_provider,
        "model_name": profile.quick_think_llm,
        "temperature": 0,
        "batch_size": BATCH_SIZE,
        "total_logical_calls": len(batches),
        "total_provider_attempts": sum(1 for c in call_log),
        "malformed_batches": malformed_batches,
        "reviewed_count": len(results),
        "calls": call_log,
    }
    existing_audit = json.loads(PROVIDER_AUDIT_PATH.read_text(encoding="utf-8")) if PROVIDER_AUDIT_PATH.exists() else {}
    existing_audit["item2_blind_holdout5_review"] = audit
    PROVIDER_AUDIT_PATH.write_text(json.dumps(existing_audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Reviewed {len(results)} rows -> {REVIEW_CSV_PATH}")
    print(f"{len(batches)} logical calls, malformed_batches={malformed_batches}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
