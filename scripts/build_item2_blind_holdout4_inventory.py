#!/usr/bin/env python3
"""QA Closure v0.1.2 -- Item 2 Blind Holdout #4, Phase 1: read-only source-pool
inventory + historical-exclusion computation. NO sampling, NO Provider call,
NO Alpha inference. Reports whether the genuinely-unseen pool is sufficient
for a formal Holdout #4 (task spec sections 6/7) BEFORE any further action.

Candidate pool membership is built EXCLUSIVELY from structured_agent_outputs.
json's own records (claim_id/agent/claim/evidence/ticker), gated only by the
existing, pre-declared, purely-structural claim_quality.is_claim_eligible(
record, CONSUMER_MAPPING) admissibility check (the same gate
map_structured_records itself applies before ever calling the Alpha Mapper --
a property of the claim record from the B0 adapter, never of anything the
Alpha Mapper computes). alpha_matches.json is deliberately NEVER read for
pool-membership purposes (task spec section 8: "Sampling must NOT depend on
current matched_alpha... Do not select rows based on current Alpha Mapper
output") -- this is a deliberate departure from Holdout #3's own build
script, which filtered to match_status=="matched" and is therefore not a
valid precedent to reuse here.

Historical exclusion draws from the same four already-consumed sources
Holdout #3 excluded (old-50, Holdout #1, Holdout #2), plus Holdout #3 itself
(newly consumed since H3's own formal development/blind evaluation), by
exact claim_id AND normalize_claim_for_dedupe-normalized evidence text.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.structure_engine.claim_quality import (  # noqa: E402
    CONSUMER_MAPPING,
    is_claim_eligible,
)
from comqutor_alpha.structure_engine.structured_output_adapter import (  # noqa: E402
    normalize_claim_for_dedupe,
)

OLD_SAMPLE_PATH = REPO_ROOT / "docs" / "evidence_review_sample_records.json"
HOLDOUT1_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout_100.csv"
HOLDOUT2_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout_141_v2.csv"
HOLDOUT3_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout3_frozen.csv"
HOLDOUT3_EXPECTED_SHA256 = "e6c778d3bbfb65e7bf9e6a72580d499424f1371c69f2027f477faae15ab82bc6"

RUNS_DIR = REPO_ROOT / "outputs" / "runs"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_exclusion_set() -> dict[str, Any]:
    old50 = json.loads(OLD_SAMPLE_PATH.read_text(encoding="utf-8"))["records"]
    ids: set[str] = {r["claim_id"] for r in old50}
    texts: set[str] = {normalize_claim_for_dedupe(r["evidence"]) for r in old50}

    with HOLDOUT1_PATH.open(encoding="utf-8", newline="") as f:
        h1 = list(csv.DictReader(f))
    ids |= {r["claim_id"] for r in h1}
    texts |= {normalize_claim_for_dedupe(r["evidence"]) for r in h1}

    with HOLDOUT2_PATH.open(encoding="utf-8", newline="") as f:
        h2 = list(csv.DictReader(f))
    ids |= {r["claim_id"] for r in h2}
    texts |= {normalize_claim_for_dedupe(r["evidence"]) for r in h2}

    # H3 integrity gate (task spec section 5): verify the frozen SHA before
    # ever using it as an exclusion source. STOP (raise), never proceed on
    # an unverified/mismatched file.
    h3_actual_sha256 = _sha256_file(HOLDOUT3_PATH)
    if h3_actual_sha256 != HOLDOUT3_EXPECTED_SHA256:
        raise SystemExit(
            f"HOLDOUT4_INTEGRITY_FAILURE: item2_blind_holdout3_frozen.csv sha256 "
            f"mismatch -- expected {HOLDOUT3_EXPECTED_SHA256}, got {h3_actual_sha256}"
        )
    with HOLDOUT3_PATH.open(encoding="utf-8", newline="") as f:
        h3 = list(csv.DictReader(f))
    ids |= {r["claim_id"] for r in h3}
    texts |= {normalize_claim_for_dedupe(r["evidence"]) for r in h3}

    return {
        "ids": ids,
        "texts": texts,
        "old50_count": len(old50),
        "h1_count": len(h1),
        "h2_count": len(h2),
        "h3_count": len(h3),
        "h3_verified_sha256": h3_actual_sha256,
    }


def _discover_real_runs() -> list[dict[str, Any]]:
    """Every outputs/runs/<uuid>/ directory with a real metadata.json AND
    structured_agent_outputs.json -- excludes error-log-only leftover
    directories (e.g. bare gateway run_ids from prior scripts that never
    produced a real pipeline run) and incomplete/failed runs."""
    runs = []
    for d in sorted(RUNS_DIR.iterdir()):
        if not d.is_dir():
            continue
        meta_path = d / "metadata.json"
        structured_path = d / "structured_agent_outputs.json"
        if not meta_path.exists() or not structured_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        runs.append(
            {
                "run_id": d.name,
                "ticker": meta.get("ticker"),
                "analysis_date": meta.get("analysis_date") or meta.get("trade_date"),
                "created_at": meta.get("created_at"),
            }
        )
    return runs


def main() -> int:
    exclusion = _load_exclusion_set()
    exclude_ids = exclusion["ids"]
    exclude_texts = exclusion["texts"]

    real_runs = _discover_real_runs()

    per_ticker_raw: dict[str, int] = defaultdict(int)
    per_ticker_eligible_structural: dict[str, int] = defaultdict(int)
    per_ticker_after_historical_exclusion: dict[str, int] = defaultdict(int)
    per_run_detail: list[dict[str, Any]] = []
    unseen_pool: list[dict[str, Any]] = []
    seen_texts_global: set[str] = set()
    within_pool_duplicate_count = 0

    for run in real_runs:
        run_id = run["run_id"]
        ticker = run["ticker"] or ""
        structured = json.loads(
            (RUNS_DIR / run_id / "structured_agent_outputs.json").read_text(encoding="utf-8")
        )
        records = structured.get("records") or []
        raw_count = len(records)
        structural_eligible = 0
        after_historical_exclusion = 0
        for record in records:
            if not isinstance(record, dict):
                continue
            if not is_claim_eligible(record, CONSUMER_MAPPING):
                continue
            structural_eligible += 1
            claim_id = str(record.get("claim_id") or record.get("agent_output_id") or "")
            evidence_text = str(record.get("evidence") or record.get("claim") or "")
            if not claim_id or not evidence_text.strip():
                continue
            norm = normalize_claim_for_dedupe(evidence_text)
            if claim_id in exclude_ids or norm in exclude_texts:
                continue
            after_historical_exclusion += 1
            if norm in seen_texts_global:
                within_pool_duplicate_count += 1
                continue
            seen_texts_global.add(norm)
            unseen_pool.append(
                {
                    "ticker": ticker,
                    "run_id": run_id,
                    "claim_id": claim_id,
                    "agent": record.get("agent"),
                    "claim": record.get("claim"),
                    "evidence": evidence_text,
                }
            )

        per_ticker_raw[ticker] += raw_count
        per_ticker_eligible_structural[ticker] += structural_eligible
        per_ticker_after_historical_exclusion[ticker] += after_historical_exclusion
        per_run_detail.append(
            {
                "run_id": run_id,
                "ticker": ticker,
                "analysis_date": run["analysis_date"],
                "created_at": run["created_at"],
                "raw_claim_count": raw_count,
                "structurally_eligible_count": structural_eligible,
                "after_historical_exclusion_count": after_historical_exclusion,
            }
        )

    report = {
        "phase": "holdout4_source_pool_inventory",
        "real_run_count": len(real_runs),
        "per_run_detail": per_run_detail,
        "per_ticker_raw_claim_count": dict(sorted(per_ticker_raw.items())),
        "per_ticker_structurally_eligible_count": dict(sorted(per_ticker_eligible_structural.items())),
        "per_ticker_after_historical_exclusion_count": dict(sorted(per_ticker_after_historical_exclusion.items())),
        "historical_exclusion": {
            "old50_row_count": exclusion["old50_count"],
            "holdout1_row_count": exclusion["h1_count"],
            "holdout2_row_count": exclusion["h2_count"],
            "holdout3_row_count": exclusion["h3_count"],
            "holdout3_verified_sha256": exclusion["h3_verified_sha256"],
            "total_exclusion_claim_id_count": len(exclude_ids),
            "total_exclusion_normalized_text_count": len(exclude_texts),
        },
        "within_pool_duplicate_count_removed_by_self_dedup": within_pool_duplicate_count,
        "final_genuinely_unseen_pool_size": len(unseen_pool),
        "final_unique_claim_id_count": len({r["claim_id"] for r in unseen_pool}),
        "final_unique_normalized_evidence_count": len(
            {normalize_claim_for_dedupe(r["evidence"]) for r in unseen_pool}
        ),
    }

    out_path = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout4_source_pool_inventory.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"\nWrote inventory -> {out_path}")

    # Persist the pool itself (not yet the frozen H4 -- pre-sampling working
    # data only) so Phase 2 sampling never has to re-derive it differently.
    pool_path = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout4_unseen_pool_working.json"
    pool_path.write_text(json.dumps(unseen_pool, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote working unseen pool ({len(unseen_pool)} rows) -> {pool_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
