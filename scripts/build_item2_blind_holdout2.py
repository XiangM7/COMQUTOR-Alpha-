#!/usr/bin/env python3
"""QA Closure v0.1.2 -- Item 2 Blind Holdout #2: build and FREEZE the holdout
population BEFORE any B1 v3/Alpha Mapper/reviewer evaluation runs against it.

Draws exclusively from already-persisted, saved-run alpha_matches.json files
(never a new research run). Excludes every row from BOTH the historical
50-row development set AND Blind Holdout #1, by exact claim_id AND by
normalize_claim_for_dedupe-normalized evidence text (the same established
repo dedupe normalization reused for Holdout #1). Also deduplicates within
Holdout #2 itself by the same normalized-text key.

Target: 25 rows/ticker (150 total) where source availability allows;
SNDK and TSM are source-constrained (see the printed pool-size survey) and
use their full remaining eligible pool instead of being padded or having
other tickers inflated to compensate.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.api.artifact_export import _claim_group_ids_index, _conflict_fact_group_ids  # noqa: E402
from comqutor_alpha.structure_engine.ai_alpha_discriminator import AI_ALPHA_IDS  # noqa: E402
from comqutor_alpha.structure_engine.structured_output_adapter import normalize_claim_for_dedupe  # noqa: E402

OLD_SAMPLE_PATH = REPO_ROOT / "docs" / "evidence_review_sample_records.json"
HOLDOUT1_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout_100.csv"

SAMPLING_VERSION = "item2_blind_holdout2.v1"
RANDOM_SEED = "item2_blind_holdout2_deterministic_seed"

RUNS: dict[str, list[str]] = {
    "AMD": ["66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1", "b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6"],
    "MSFT": ["07ddc074-9ab2-4b16-8957-acbf94012144", "0cb43bae-1a4d-4003-bb29-55d420498842", "61f3e019-63a8-4c56-b763-057208d5efae"],
    "NVDA": ["0e044e37-862c-43be-871c-31012cd660e7", "4ca7dafa-6ac1-4d94-add0-f6f93b1af150", "5ffe121a-68fd-473b-82b5-c9465332d8a2", "e3eb3909-3744-4a02-9b32-b225cf6ef665", "e434f80b-e4d0-4b09-9471-d84532659de5"],
    "QQQ": ["a364e0ee-3bb4-4032-88b7-5cd82e379805"],
    "SNDK": ["183b04dd-aae3-4b33-bbb0-3c9bc3bc942f", "8d21c047-fc0a-4d94-957d-3787f353a544"],
    "TSM": ["1a338ced-118e-44d2-b3f6-2444bfb9d7e6"],
}
# 25/ticker where source availability allows; SNDK/TSM capped by genuine
# pool size (19/22 respectively after exclusion+dedup -- see survey run
# before this script). Not padded, not compensated elsewhere.
TARGET_COUNTS: dict[str, int] = {"AMD": 25, "MSFT": 25, "NVDA": 25, "QQQ": 25, "SNDK": 19, "TSM": 22}

ALPHA_SOFT_CAP_FRACTION = 0.35


def _output_paths(n: int) -> tuple[Path, Path]:
    csv_path = REPO_ROOT / "docs" / "audit_artifacts" / f"item2_blind_holdout_{n}_v2.csv"
    manifest_path = REPO_ROOT / "docs" / "audit_artifacts" / f"item2_blind_holdout_{n}_v2_manifest.json"
    return csv_path, manifest_path


def _load_exclusion_set() -> tuple[set[str], set[str]]:
    old50 = json.loads(OLD_SAMPLE_PATH.read_text(encoding="utf-8"))["records"]
    ids = {r["claim_id"] for r in old50}
    texts = {normalize_claim_for_dedupe(r["evidence"]) for r in old50}
    with HOLDOUT1_PATH.open(encoding="utf-8", newline="") as f:
        h1 = list(csv.DictReader(f))
    ids |= {r["claim_id"] for r in h1}
    texts |= {normalize_claim_for_dedupe(r["evidence"]) for r in h1}
    return ids, texts, len(old50), len(h1)


def _load_run_artifacts(run_id: str) -> dict[str, Any]:
    run_dir = REPO_ROOT / "outputs" / "runs" / run_id
    matches = json.loads((run_dir / "alpha_matches.json").read_text(encoding="utf-8"))["matches"]
    graph_payload = None
    conflict_payload = None
    graph_path = run_dir / "structure_graph.json"
    if graph_path.exists():
        graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
    conflicts_path = run_dir / "conflicts.json"
    if conflicts_path.exists():
        conflict_payload = json.loads(conflicts_path.read_text(encoding="utf-8"))
    return {"matches": matches, "graph_payload": graph_payload, "conflict_payload": conflict_payload}


def _duplicate_group_sizes(graph_payload: Any) -> dict[str, int]:
    sizes: dict[str, int] = {}
    if not isinstance(graph_payload, dict):
        return sizes
    versions = graph_payload.get("activation_versions")
    v2 = versions.get("v2") if isinstance(versions, dict) else None
    alphas = v2.get("alphas") if isinstance(v2, dict) else None
    if not isinstance(alphas, list):
        return sizes
    for alpha in alphas:
        if not isinstance(alpha, dict):
            continue
        for group in alpha.get("evidence_fact_groups") or []:
            if not isinstance(group, dict):
                continue
            member_ids = group.get("member_claim_ids") or []
            size = len(member_ids)
            for cid in member_ids:
                sizes[str(cid)] = max(sizes.get(str(cid), 0), size)
    return sizes


def _eligible_claims_for_ticker(
    ticker: str, run_ids: list[str], exclude_claim_ids: set[str], exclude_texts: set[str]
) -> list[dict[str, Any]]:
    eligible = []
    seen_texts: set[str] = set()
    for run_id in run_ids:
        artifacts = _load_run_artifacts(run_id)
        matches = artifacts["matches"]
        claim_group_ids = _claim_group_ids_index(artifacts["graph_payload"]) if artifacts["graph_payload"] else {}
        conflict_group_ids = _conflict_fact_group_ids(artifacts["conflict_payload"]) if artifacts["conflict_payload"] else set()
        dup_sizes = _duplicate_group_sizes(artifacts["graph_payload"])

        for m in matches:
            if m.get("match_status") != "matched" or not m.get("matched_alpha"):
                continue
            claim_id = str(m.get("claim_id") or "")
            if not claim_id or claim_id in exclude_claim_ids:
                continue
            evidence_text = str(m.get("evidence") or m.get("claim") or "")
            norm = normalize_claim_for_dedupe(evidence_text)
            if norm in exclude_texts or norm in seen_texts:
                continue
            candidate = next((c for c in (m.get("candidate_scores") or []) if c.get("alpha_id") == m["matched_alpha"]), None)
            if candidate is None:
                continue
            seen_texts.add(norm)
            group_ids = sorted(claim_group_ids.get(claim_id, set()))
            eligible.append(
                {
                    "ticker": ticker, "source_run_id": run_id, "claim_id": claim_id,
                    "agent": m.get("agent"), "claim": m.get("claim"), "evidence": evidence_text,
                    "matched_alpha_id": m["matched_alpha"], "matched_alpha_name": m.get("matched_alpha_name"),
                    "match_score": candidate.get("score"), "match_status": m.get("match_status"),
                    "relation": candidate.get("relation"), "direction": m.get("direction"),
                    "used_in_activation": bool(group_ids),
                    "used_in_conflict": bool(set(group_ids) & conflict_group_ids),
                    "duplicate_group_size": dup_sizes.get(claim_id, 1),
                    "ai_gate_alpha": m["matched_alpha"] in AI_ALPHA_IDS,
                }
            )
    return eligible


def _stratify_bucket(row: dict[str, Any]) -> tuple[str, str]:
    score = row["match_score"] or 0.0
    tier = "high" if score >= 0.6 else "medium"
    return (row["relation"] or "unknown", tier)


def _sample_ticker(rng: random.Random, pool: list[dict[str, Any]], target: int) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in pool:
        buckets.setdefault(_stratify_bucket(row), []).append(row)
    for bucket_rows in buckets.values():
        rng.shuffle(bucket_rows)

    bucket_keys = sorted(buckets.keys())
    rng.shuffle(bucket_keys)
    cursors = dict.fromkeys(bucket_keys, 0)
    alpha_counts: Counter[str] = Counter()
    soft_cap = max(2, round(target * ALPHA_SOFT_CAP_FRACTION))

    selected: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    progressed = True
    while len(selected) < target and progressed:
        progressed = False
        for key in bucket_keys:
            if len(selected) >= target:
                break
            rows = buckets[key]
            idx = cursors[key]
            while idx < len(rows):
                candidate = rows[idx]
                idx += 1
                if alpha_counts[candidate["matched_alpha_id"]] >= soft_cap:
                    deferred.append(candidate)
                    continue
                selected.append(candidate)
                alpha_counts[candidate["matched_alpha_id"]] += 1
                progressed = True
                break
            cursors[key] = idx

    if len(selected) < target:
        rng.shuffle(deferred)
        for candidate in deferred:
            if len(selected) >= target:
                break
            if candidate in selected:
                continue
            selected.append(candidate)

    return selected[:target]


def build_holdout() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    exclude_claim_ids, exclude_texts, old50_count, h1_count = _load_exclusion_set()
    rng = random.Random(RANDOM_SEED)

    all_selected: list[dict[str, Any]] = []
    pool_sizes: dict[str, int] = {}
    shortfall: dict[str, dict[str, int]] = {}

    for ticker, target in TARGET_COUNTS.items():
        pool = _eligible_claims_for_ticker(ticker, RUNS[ticker], exclude_claim_ids, exclude_texts)
        pool_sizes[ticker] = len(pool)
        if len(pool) < target:
            shortfall[ticker] = {"target": target, "available": len(pool)}
            target = len(pool)
        selected = _sample_ticker(rng, pool, target)
        all_selected.extend(selected)

    all_selected.sort(key=lambda r: (r["ticker"], r["claim_id"]))
    for i, row in enumerate(all_selected, start=1):
        row["sample_id"] = f"holdout2-{i:03d}"

    manifest_extra = {
        "pool_sizes_after_exclusion_and_dedup": pool_sizes,
        "target_vs_actual_shortfall": shortfall,
        "old50_excluded_row_count": old50_count,
        "holdout1_excluded_row_count": h1_count,
        "total_exclusion_claim_id_count": len(exclude_claim_ids),
        "total_exclusion_normalized_text_count": len(exclude_texts),
    }
    return all_selected, manifest_extra


CSV_FIELDS = [
    "sample_id", "ticker", "source_run_id", "claim_id", "agent", "claim", "evidence",
    "target_alpha_id", "system_matched_alpha_id", "system_matched_alpha_name",
    "system_match_score", "system_match_status", "system_relation", "system_direction",
    "system_used_in_activation", "system_used_in_conflict", "system_duplicate_group_size",
    "system_ai_gate_alpha",
]


def main() -> int:
    rows, manifest_extra = build_holdout()
    n = len(rows)
    assert len({r["sample_id"] for r in rows}) == n
    assert len({r["claim_id"] for r in rows}) == n
    assert len({normalize_claim_for_dedupe(r["evidence"]) for r in rows}) == n, "within-holdout duplicate evidence text found"

    csv_path, manifest_path = _output_paths(n)

    csv_rows = []
    for r in rows:
        csv_rows.append(
            {
                "sample_id": r["sample_id"], "ticker": r["ticker"], "source_run_id": r["source_run_id"],
                "claim_id": r["claim_id"], "agent": r["agent"], "claim": r["claim"], "evidence": r["evidence"],
                "target_alpha_id": r["matched_alpha_id"], "system_matched_alpha_id": r["matched_alpha_id"],
                "system_matched_alpha_name": r["matched_alpha_name"], "system_match_score": r["match_score"],
                "system_match_status": r["match_status"], "system_relation": r["relation"],
                "system_direction": r["direction"], "system_used_in_activation": r["used_in_activation"],
                "system_used_in_conflict": r["used_in_conflict"], "system_duplicate_group_size": r["duplicate_group_size"],
                "system_ai_gate_alpha": r["ai_gate_alpha"],
            }
        )

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(csv_rows)

    csv_sha256 = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    ticker_dist = Counter(r["ticker"] for r in rows)
    alpha_dist = Counter(r["matched_alpha_id"] for r in rows)
    relation_dist = Counter(r["relation"] for r in rows)

    manifest = {
        "schema_version": "item2_blind_holdout2_manifest.v1",
        "sample_count": n,
        "sampling_version": SAMPLING_VERSION,
        "random_seed": RANDOM_SEED,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_runs": RUNS,
        "ticker_distribution": dict(ticker_dist),
        "ticker_targets": TARGET_COUNTS,
        "alpha_distribution": dict(alpha_dist),
        "relation_distribution": dict(relation_dist),
        "alpha_soft_cap_fraction": ALPHA_SOFT_CAP_FRACTION,
        "exclusion": manifest_extra,
        "duplicate_exclusion_method": "claim_id exact match + normalize_claim_for_dedupe(evidence) text-identity match against ALL rows from the historical 50-row development set AND Blind Holdout #1; also deduplicated within Holdout #2 itself by the same normalized-text key",
        "reviewer_labels_used_for_selection": False,
        "csv_sha256": csv_sha256,
        "csv_path": str(csv_path.relative_to(REPO_ROOT)),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Wrote {n} rows -> {csv_path}")
    print(f"csv_sha256 = {csv_sha256}")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
