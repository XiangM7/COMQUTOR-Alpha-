#!/usr/bin/env python3
"""Blind Holdout #5 (task spec sections 3-7): build the genuinely-new,
human-reviewed 200-row frozen dataset.

Excludes every claim_id and normalized-Evidence text already used in the
original 50-row development review and Blind Holdouts #1-#4 (H4's own
development re-review reuses H4's existing 200 rows verbatim -- no new rows
-- so excluding H4's frozen set already covers it).

Pool built purely from claim_quality.is_claim_eligible(record,
CONSUMER_MAPPING) against real, already-persisted structured_agent_outputs.
json across every saved run for the eight target tickers -- never
conditioned on any Alpha prediction, deterministic Alpha, Alpha score,
match_status, AI gate, B1 stance, reviewer label, or system confidence. No
new TradingAgents research is run.

Uses the repository's existing normalize_claim_for_dedupe implementation
(structured_output_adapter.py) for canonical Evidence-text normalization --
no invented fuzzy-similarity matching.

Pure, deterministic, offline: no Provider/LLM call.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.structure_engine.claim_quality import CONSUMER_MAPPING, is_claim_eligible  # noqa: E402
from comqutor_alpha.structure_engine.structured_output_adapter import normalize_claim_for_dedupe  # noqa: E402

TICKERS = ["AMD", "GOOGL", "MSFT", "MU", "NVDA", "QQQ", "SNDK", "TSM"]
PER_TICKER_TARGET = 25
TOTAL_TARGET = 200
SAMPLING_SEED = 5
RUNS_ROOT = REPO_ROOT / "outputs" / "runs"

DEV_50_PATH = REPO_ROOT / "docs" / "evidence_review_sample_records.json"
H1_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout_100.csv"
H2_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout_141_v2.csv"
H3_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout3_frozen.csv"
H4_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout4_frozen.csv"

FROZEN_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout5_frozen.csv"
SAMPLING_MANIFEST_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout5_sampling_manifest.json"
HUMAN_REVIEW_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "evidence_review_sample_h5.csv"

FROZEN_CSV_COLUMNS = ["sample_id", "run_id", "ticker", "claim_id", "agent", "claim", "evidence"]
HUMAN_REVIEW_COLUMNS = [
    "sample_id",
    "ticker",
    "agent",
    "claim",
    "evidence",
    "human_material_alpha_fit",
    "human_expected_alpha_id",
    "human_alpha_confidence",
    "human_polarity",
    "human_review_note",
]


class Holdout5Error(Exception):
    pass


def _load_historical_exclusions() -> tuple[set[str], set[str], dict[str, int]]:
    claim_ids: set[str] = set()
    evidence_norms: set[str] = set()
    counts: dict[str, int] = {}

    dev = json.loads(DEV_50_PATH.read_text(encoding="utf-8"))
    recs = dev["records"]
    counts["dev_50_sample"] = len(recs)
    for r in recs:
        claim_ids.add(r["claim_id"])
        evidence_norms.add(normalize_claim_for_dedupe(r.get("evidence", "")))

    for name, path in [
        ("holdout1_100", H1_PATH),
        ("holdout2_141", H2_PATH),
        ("holdout3", H3_PATH),
        ("holdout4_200", H4_PATH),
    ]:
        with path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        counts[name] = len(rows)
        for row in rows:
            claim_ids.add(row["claim_id"])
            evidence_norms.add(normalize_claim_for_dedupe(row.get("evidence", "")))

    return claim_ids, evidence_norms, counts


def _build_eligible_pool(
    excluded_claim_ids: set[str], excluded_evidence_norms: set[str]
) -> tuple[list[dict[str, Any]], int, int]:
    raw_source_count = 0
    eligible_count = 0
    pool: list[dict[str, Any]] = []
    for run_dir in sorted(RUNS_ROOT.iterdir()):
        sfile = run_dir / "structured_agent_outputs.json"
        if not sfile.exists():
            continue
        data = json.loads(sfile.read_text(encoding="utf-8"))
        ticker = data.get("ticker")
        if ticker not in TICKERS:
            continue
        for rec in data.get("records", []):
            raw_source_count += 1
            if not is_claim_eligible(rec, CONSUMER_MAPPING):
                continue
            eligible_count += 1
            claim_id = rec.get("claim_id")
            evidence = rec.get("evidence") or ""
            norm_ev = normalize_claim_for_dedupe(evidence)
            if claim_id in excluded_claim_ids or norm_ev in excluded_evidence_norms:
                continue
            pool.append(
                {
                    "run_id": rec.get("run_id"),
                    "ticker": ticker,
                    "claim_id": claim_id,
                    "agent": rec.get("agent"),
                    "claim": rec.get("claim"),
                    "evidence": evidence,
                    "_norm_evidence": norm_ev,
                }
            )
    return pool, raw_source_count, eligible_count


def _self_dedupe(pool: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    pool_sorted = sorted(pool, key=lambda r: (r["ticker"], r["run_id"], r["claim_id"]))
    seen: set[str] = set()
    deduped = []
    for r in pool_sorted:
        if r["_norm_evidence"] in seen:
            continue
        seen.add(r["_norm_evidence"])
        deduped.append(r)
    return deduped, len(pool_sorted) - len(deduped)


def main() -> int:
    claim_ids, evidence_norms, hist_counts = _load_historical_exclusions()
    pool, raw_source_count, eligible_count = _build_eligible_pool(claim_ids, evidence_norms)
    deduped, dup_removed = _self_dedupe(pool)

    by_ticker: dict[str, list[dict[str, Any]]] = {t: [] for t in TICKERS}
    for r in deduped:
        by_ticker[r["ticker"]].append(r)

    total_unseen = sum(len(v) for v in by_ticker.values())
    if total_unseen < TOTAL_TARGET:
        print("HOLDOUT5_INSUFFICIENT_UNSEEN_POOL", file=sys.stderr)
        print(json.dumps({t: len(v) for t, v in by_ticker.items()}, indent=2), file=sys.stderr)
        return 1

    shortfall_tickers = {t: len(v) for t, v in by_ticker.items() if len(v) < PER_TICKER_TARGET}
    if not shortfall_tickers:
        allocation = {t: PER_TICKER_TARGET for t in TICKERS}
        redistribution_note = "none needed -- every ticker had >= 25 genuinely unseen eligible rows"
    else:
        allocation = {t: min(PER_TICKER_TARGET, len(by_ticker[t])) for t in TICKERS}
        remaining = TOTAL_TARGET - sum(allocation.values())
        surplus_tickers = [t for t in TICKERS if t not in shortfall_tickers]
        i = 0
        while remaining > 0:
            t = surplus_tickers[i % len(surplus_tickers)]
            if allocation[t] < len(by_ticker[t]):
                allocation[t] += 1
                remaining -= 1
            i += 1
        redistribution_note = (
            f"shortfall in {sorted(shortfall_tickers)} -- redistributed deterministically to "
            f"surplus tickers in fixed ticker order {TICKERS}"
        )

    rng = random.Random(SAMPLING_SEED)
    sampled: list[dict[str, Any]] = []
    for t in TICKERS:
        candidates = sorted(by_ticker[t], key=lambda r: (r["run_id"], r["claim_id"]))
        k = allocation[t]
        sampled.extend(rng.sample(candidates, k))

    if len(sampled) != TOTAL_TARGET:
        raise Holdout5Error(f"sampled {len(sampled)} != {TOTAL_TARGET}")

    ticker_rank = {t: i for i, t in enumerate(TICKERS)}
    sampled.sort(key=lambda r: (ticker_rank[r["ticker"]], r["run_id"], r["claim_id"]))

    frozen_rows = []
    for i, r in enumerate(sampled, start=1):
        sample_id = f"holdout5-{i:03d}"
        frozen_rows.append(
            {
                "sample_id": sample_id,
                "run_id": r["run_id"],
                "ticker": r["ticker"],
                "claim_id": r["claim_id"],
                "agent": r["agent"],
                "claim": r["claim"],
                "evidence": r["evidence"],
            }
        )

    if len({r["claim_id"] for r in frozen_rows}) != TOTAL_TARGET:
        raise Holdout5Error("duplicate claim_id in final H5 sample")
    if len({normalize_claim_for_dedupe(r["evidence"]) for r in frozen_rows}) != TOTAL_TARGET:
        raise Holdout5Error("duplicate normalized evidence in final H5 sample")

    with FROZEN_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FROZEN_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(frozen_rows)

    frozen_sha256 = hashlib.sha256(FROZEN_CSV_PATH.read_bytes()).hexdigest()

    with HUMAN_REVIEW_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HUMAN_REVIEW_COLUMNS)
        writer.writeheader()
        for r in frozen_rows:
            writer.writerow(
                {
                    "sample_id": r["sample_id"],
                    "ticker": r["ticker"],
                    "agent": r["agent"],
                    "claim": r["claim"],
                    "evidence": r["evidence"],
                    "human_material_alpha_fit": "",
                    "human_expected_alpha_id": "",
                    "human_alpha_confidence": "",
                    "human_polarity": "",
                    "human_review_note": "",
                }
            )

    ticker_counts = Counter(r["ticker"] for r in frozen_rows)
    run_counts = Counter(r["run_id"] for r in frozen_rows)
    agent_counts = Counter(r["agent"] for r in frozen_rows)

    manifest = {
        "task": "Blind Holdout #5 sampling manifest",
        "starting_source_record_count_all_tickers_all_runs": raw_source_count,
        "eligible_record_count_is_claim_eligible_mapping": eligible_count,
        "historical_exclusion_source_counts": hist_counts,
        "historical_excluded_claim_id_count": len(claim_ids),
        "historical_excluded_normalized_evidence_count": len(evidence_norms),
        "unseen_eligible_pool_pre_self_dedupe": len(pool),
        "self_dedupe_removed_count": dup_removed,
        "unseen_eligible_pool_post_self_dedupe": len(deduped),
        "unseen_eligible_pool_by_ticker": {t: len(v) for t, v in by_ticker.items()},
        "preferred_per_ticker_allocation": PER_TICKER_TARGET,
        "actual_allocation": allocation,
        "redistribution_note": redistribution_note,
        "final_n": len(frozen_rows),
        "ticker_counts": dict(sorted(ticker_counts.items())),
        "run_counts": dict(sorted(run_counts.items())),
        "agent_counts": dict(sorted(agent_counts.items())),
        "sampling_seed": SAMPLING_SEED,
        "sampling_method": (
            "For each ticker: candidates sorted deterministically by (run_id, claim_id), then "
            "random.Random(seed=5).sample(candidates, k) where k is that ticker's allocation. "
            "Final row order: fixed ticker order (AMD,GOOGL,MSFT,MU,NVDA,QQQ,SNDK,TSM), then (run_id, claim_id)."
        ),
        "normalization_implementation_reused": (
            "comqutor_alpha.structure_engine.structured_output_adapter.normalize_claim_for_dedupe "
            "(existing, unmodified) applied to the evidence field"
        ),
        "eligibility_implementation_reused": (
            "comqutor_alpha.structure_engine.claim_quality.is_claim_eligible(record, CONSUMER_MAPPING) "
            "(existing, unmodified)"
        ),
        "pool_membership_independent_of": [
            "current Alpha prediction",
            "deterministic Alpha prediction",
            "Alpha score",
            "match_status",
            "AI gate",
            "B1 stance",
            "reviewer label",
            "system confidence",
        ],
        "new_tradingagents_research_run": False,
        "frozen_csv_path": str(FROZEN_CSV_PATH.relative_to(REPO_ROOT)),
        "frozen_csv_sha256": frozen_sha256,
        "frozen_csv_row_count": len(frozen_rows),
    }
    SAMPLING_MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"Wrote {len(frozen_rows)} rows -> {FROZEN_CSV_PATH}")
    print(f"frozen_csv_sha256 = {frozen_sha256}")
    print(f"Wrote sampling manifest -> {SAMPLING_MANIFEST_PATH}")
    print(f"Wrote blind human review file -> {HUMAN_REVIEW_CSV_PATH}")
    print(
        json.dumps(
            {"ticker_counts": dict(ticker_counts), "allocation": allocation, "redistribution_note": redistribution_note},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
