#!/usr/bin/env python3
"""QA Closure v0.1.2 -- Item 2 Blind Holdout #4, Phase 2: sample and FREEZE
the holdout population from the already-computed, already-verified
genuinely-unseen pool (item2_blind_holdout4_unseen_pool_working.json,
produced read-only by build_item2_blind_holdout4_inventory.py). No Provider
call, no Alpha inference, no dependency on current/deterministic/historical
Alpha output of any kind.

Sampling is a flat per-ticker uniform random draw (deterministic seed) --
every ticker in the genuinely-unseen pool gets the same target count,
capped by its own true pool size, with no engineered Alpha-family balance
(task spec section 9: "do NOT inspect production system Alpha predictions
to enforce Alpha family balance") and no removal of generic/background/
ambiguous-looking/non-ticker-specific rows (section 8).
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

from comqutor_alpha.structure_engine.structured_output_adapter import (  # noqa: E402
    normalize_claim_for_dedupe,
)

POOL_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout4_unseen_pool_working.json"
INVENTORY_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout4_source_pool_inventory.json"

FROZEN_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout4_frozen.csv"
FREEZE_SAMPLING_METADATA_PATH = (
    REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout4_freeze_manifest_sampling.json"
)

RANDOM_SEED = "item2_blind_holdout4_deterministic_seed"
PER_TICKER_TARGET = 25  # 8 tickers x 25 = 200, within the 150-200 preferred range
FROZEN_FIELDS = ["sample_id", "run_id", "ticker", "claim_id", "agent", "claim", "evidence"]


def main() -> int:
    pool: list[dict[str, Any]] = json.loads(POOL_PATH.read_text(encoding="utf-8"))
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))

    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for row in pool:
        by_ticker.setdefault(row["ticker"], []).append(row)

    rng = random.Random(RANDOM_SEED)
    selected: list[dict[str, Any]] = []
    pool_sizes: dict[str, int] = {}
    shortfall: dict[str, dict[str, int]] = {}

    for ticker in sorted(by_ticker):
        ticker_pool = list(by_ticker[ticker])
        pool_sizes[ticker] = len(ticker_pool)
        rng.shuffle(ticker_pool)
        target = PER_TICKER_TARGET
        if len(ticker_pool) < target:
            shortfall[ticker] = {"target": target, "available": len(ticker_pool)}
            target = len(ticker_pool)
        selected.extend(ticker_pool[:target])

    # Self-dedup safety net (the pool is already globally self-deduped by
    # build_item2_blind_holdout4_inventory.py, but re-verify here since this
    # is the actual frozen output).
    seen_texts: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in selected:
        norm = normalize_claim_for_dedupe(row["evidence"])
        if norm in seen_texts:
            continue
        seen_texts.add(norm)
        deduped.append(row)
    selected = deduped

    selected.sort(key=lambda r: (r["ticker"], r["claim_id"]))
    for i, row in enumerate(selected, start=1):
        row["sample_id"] = f"holdout4-{i:03d}"

    n = len(selected)
    assert len({r["claim_id"] for r in selected}) == n, "duplicate claim_id in frozen H4"
    assert len({normalize_claim_for_dedupe(r["evidence"]) for r in selected}) == n, "duplicate evidence text in frozen H4"

    with FROZEN_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FROZEN_FIELDS)
        writer.writeheader()
        for row in selected:
            writer.writerow({k: row[k] for k in FROZEN_FIELDS})

    frozen_sha256 = hashlib.sha256(FROZEN_CSV_PATH.read_bytes()).hexdigest()

    ticker_distribution = dict(Counter(r["ticker"] for r in selected))
    run_distribution = dict(Counter(r["run_id"] for r in selected))
    agent_distribution = dict(Counter(r["agent"] for r in selected))

    sampling_metadata = {
        "sampling_version": "item2_blind_holdout4.v1",
        "random_seed": RANDOM_SEED,
        "per_ticker_target": PER_TICKER_TARGET,
        "sample_count": n,
        "frozen_csv_path": str(FROZEN_CSV_PATH.relative_to(REPO_ROOT)),
        "frozen_csv_sha256": frozen_sha256,
        "frozen_csv_fields": FROZEN_FIELDS,
        "pool_sizes_by_ticker": pool_sizes,
        "target_vs_actual_shortfall": shortfall,
        "ticker_distribution": ticker_distribution,
        "run_distribution": run_distribution,
        "agent_distribution": agent_distribution,
        "sampling_depended_on_system_alpha_output": False,
        "sampling_note": (
            "Flat per-ticker uniform random draw from the already-frozen "
            "genuinely-unseen pool (build_item2_blind_holdout4_inventory.py), "
            "deterministic seed, no stratification by current/deterministic "
            "Alpha output, candidate scores, AI gate, threshold, B1 stance, "
            "or reviewer labels (none of these were computed or consulted "
            "before this freeze)."
        ),
        "historical_exclusion_summary": inventory["historical_exclusion"],
        "source_run_inventory": inventory["per_run_detail"],
    }
    FREEZE_SAMPLING_METADATA_PATH.write_text(
        json.dumps(sampling_metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(json.dumps(sampling_metadata, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"\nWrote {n} rows -> {FROZEN_CSV_PATH}")
    print(f"SHA-256: {frozen_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
