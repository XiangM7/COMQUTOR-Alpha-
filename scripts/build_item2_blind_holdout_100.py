#!/usr/bin/env python3
"""QA Closure v0.1.2 -- Item 2 NEW 100-row blind holdout: build and FREEZE
the holdout population BEFORE any B1/Alpha Mapper/independent-reviewer
evaluation runs against it.

Draws exclusively from already-persisted, saved-run alpha_matches.json
files (never a new research run). Excludes every one of the old 50
development-set rows by BOTH claim_id and normalized evidence text
(comqutor_alpha.structure_engine.structured_output_adapter.normalize_claim_for_dedupe,
the same dedupe normalization already established in this repo -- reused,
not reinvented).

Stratification uses ONLY machine-side signals already computed and
persisted by the production pipeline (relation, match_score, direction,
used_in_activation, used_in_conflict, AI-gate applicability, duplicate/
paraphrase group membership) -- no reviewer label of any kind exists yet
for these rows, so none can leak into selection.

Sampling is deterministic (fixed seed) so the exact same 100 rows would be
selected on a re-run against unchanged source artifacts -- not that this
script is ever re-run after the CSV is frozen (section 6 forbids it).
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
OUTPUT_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout_100.csv"
OUTPUT_MANIFEST_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout_100_manifest.json"

SAMPLING_VERSION = "item2_blind_holdout_100.v1"
RANDOM_SEED = "item2_blind_holdout_100_v1_deterministic_seed"

# Primary source: the same six regression-selected/"canonical" runs used
# throughout QA Closure v0.1.2 (Items 1/6/2) -- chosen for consistency and
# because all six have both structure_graph.json and conflicts.json.
CANONICAL_RUNS: dict[str, str] = {
    "NVDA": "5ffe121a-68fd-473b-82b5-c9465332d8a2",
    "QQQ": "a364e0ee-3bb4-4032-88b7-5cd82e379805",
    "MSFT": "07ddc074-9ab2-4b16-8957-acbf94012144",
    "SNDK": "183b04dd-aae3-4b33-bbb0-3c9bc3bc942f",
    "TSM": "1a338ced-118e-44d2-b3f6-2444bfb9d7e6",
    "AMD": "b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6",
}
# SNDK's canonical run has only 5 matched claims after exclusions -- far
# short of quota. Supplemented from a second, genuinely distinct saved SNDK
# run never touched by the old 50-row sample.
SECONDARY_RUNS: dict[str, list[str]] = {
    "SNDK": ["8d21c047-fc0a-4d94-957d-3787f353a544"],
}

TARGET_COUNTS: dict[str, int] = {
    "NVDA": 17, "QQQ": 17, "MSFT": 17, "SNDK": 17, "TSM": 16, "AMD": 16,
}
assert sum(TARGET_COUNTS.values()) == 100

ALPHA_SOFT_CAP_FRACTION = 0.35  # no single Alpha may exceed ~35% of a ticker's quota


def _load_old50_exclusion_set() -> tuple[set[str], set[str]]:
    records = json.loads(OLD_SAMPLE_PATH.read_text(encoding="utf-8"))["records"]
    claim_ids = {r["claim_id"] for r in records}
    normalized_texts = {normalize_claim_for_dedupe(r["evidence"]) for r in records}
    return claim_ids, normalized_texts


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
    """claim_id -> size of its own evidence_fact_group (>1 means it shares
    a group with at least one other claim -- the same structural signal the
    old sample's own duplicate_or_paraphrase_member field was built from)."""
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


def _eligible_claims_for_ticker(ticker: str, run_id: str, exclude_claim_ids: set[str], exclude_texts: set[str]) -> list[dict[str, Any]]:
    artifacts = _load_run_artifacts(run_id)
    matches = artifacts["matches"]
    claim_group_ids = _claim_group_ids_index(artifacts["graph_payload"]) if artifacts["graph_payload"] else {}
    conflict_group_ids = _conflict_fact_group_ids(artifacts["conflict_payload"]) if artifacts["conflict_payload"] else set()
    dup_sizes = _duplicate_group_sizes(artifacts["graph_payload"])

    eligible = []
    for m in matches:
        if m.get("match_status") != "matched" or not m.get("matched_alpha"):
            continue
        claim_id = str(m.get("claim_id") or "")
        if not claim_id or claim_id in exclude_claim_ids:
            continue
        evidence_text = str(m.get("evidence") or m.get("claim") or "")
        if normalize_claim_for_dedupe(evidence_text) in exclude_texts:
            continue
        candidate = next((c for c in (m.get("candidate_scores") or []) if c.get("alpha_id") == m["matched_alpha"]), None)
        if candidate is None:
            continue
        group_ids = sorted(claim_group_ids.get(claim_id, set()))
        eligible.append(
            {
                "ticker": ticker,
                "source_run_id": run_id,
                "claim_id": claim_id,
                "agent": m.get("agent"),
                "claim": m.get("claim"),
                "evidence": evidence_text,
                "matched_alpha_id": m["matched_alpha"],
                "matched_alpha_name": m.get("matched_alpha_name"),
                "match_score": candidate.get("score"),
                "match_status": m.get("match_status"),
                "relation": candidate.get("relation"),
                "direction": m.get("direction"),
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
    """Deterministic stratified sample: round-robin across (relation,
    score_tier) buckets, skipping a candidate that would push any single
    Alpha above ALPHA_SOFT_CAP_FRACTION of the ticker's own target -- pure
    machine-metadata logic, no reviewer label involved."""
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

    # If the soft cap made the target unreachable from fresh rows, relax it
    # using the deferred pool (still fully deterministic) rather than
    # leaving the ticker short.
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
    exclude_claim_ids, exclude_texts = _load_old50_exclusion_set()
    rng = random.Random(RANDOM_SEED)

    all_selected: list[dict[str, Any]] = []
    pool_sizes: dict[str, int] = {}
    sources_used: dict[str, list[str]] = {}

    for ticker, target in TARGET_COUNTS.items():
        run_ids = [CANONICAL_RUNS[ticker]] + SECONDARY_RUNS.get(ticker, [])
        pool: list[dict[str, Any]] = []
        seen_claim_ids: set[str] = set()
        for run_id in run_ids:
            for row in _eligible_claims_for_ticker(ticker, run_id, exclude_claim_ids, exclude_texts):
                if row["claim_id"] in seen_claim_ids:
                    continue
                seen_claim_ids.add(row["claim_id"])
                pool.append(row)
        pool_sizes[ticker] = len(pool)
        sources_used[ticker] = run_ids
        if len(pool) < target:
            raise SystemExit(f"INSUFFICIENT_POOL: {ticker} has only {len(pool)} eligible claims, needs {target}")
        selected = _sample_ticker(rng, pool, target)
        all_selected.extend(selected)

    # Deterministic final ordering (ticker, then claim_id) before ID
    # assignment -- never an arbitrary/accidental dict-iteration order.
    all_selected.sort(key=lambda r: (r["ticker"], r["claim_id"]))
    for i, row in enumerate(all_selected, start=1):
        row["sample_id"] = f"holdout-{i:03d}"

    manifest_extra = {
        "pool_sizes_after_exclusion": pool_sizes,
        "sources_used": sources_used,
        "old50_excluded_claim_id_count": len(exclude_claim_ids),
        "old50_excluded_normalized_text_count": len(exclude_texts),
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
    assert len(rows) == 100
    assert len({r["sample_id"] for r in rows}) == 100
    assert len({r["claim_id"] for r in rows}) == 100

    csv_rows = []
    for r in rows:
        csv_rows.append(
            {
                "sample_id": r["sample_id"],
                "ticker": r["ticker"],
                "source_run_id": r["source_run_id"],
                "claim_id": r["claim_id"],
                "agent": r["agent"],
                "claim": r["claim"],
                "evidence": r["evidence"],
                "target_alpha_id": r["matched_alpha_id"],
                "system_matched_alpha_id": r["matched_alpha_id"],
                "system_matched_alpha_name": r["matched_alpha_name"],
                "system_match_score": r["match_score"],
                "system_match_status": r["match_status"],
                "system_relation": r["relation"],
                "system_direction": r["direction"],
                "system_used_in_activation": r["used_in_activation"],
                "system_used_in_conflict": r["used_in_conflict"],
                "system_duplicate_group_size": r["duplicate_group_size"],
                "system_ai_gate_alpha": r["ai_gate_alpha"],
            }
        )

    with OUTPUT_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(csv_rows)

    csv_sha256 = hashlib.sha256(OUTPUT_CSV_PATH.read_bytes()).hexdigest()

    ticker_dist = Counter(r["ticker"] for r in rows)
    alpha_dist = Counter(r["matched_alpha_id"] for r in rows)
    relation_dist = Counter(r["relation"] for r in rows)
    ai_gate_count = sum(1 for r in rows if r["ai_gate_alpha"])
    used_in_activation_count = sum(1 for r in rows if r["used_in_activation"])
    used_in_conflict_count = sum(1 for r in rows if r["used_in_conflict"])
    duplicate_candidate_count = sum(1 for r in rows if r["duplicate_group_size"] > 1)

    manifest = {
        "schema_version": "item2_blind_holdout_100_manifest.v1",
        "sample_count": len(rows),
        "sampling_version": SAMPLING_VERSION,
        "random_seed": RANDOM_SEED,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_runs": {t: [CANONICAL_RUNS[t]] + SECONDARY_RUNS.get(t, []) for t in TARGET_COUNTS},
        "ticker_distribution": dict(ticker_dist),
        "ticker_targets": TARGET_COUNTS,
        "alpha_distribution": dict(alpha_dist),
        "relation_distribution": dict(relation_dist),
        "ai_gate_alpha_count": ai_gate_count,
        "used_in_activation_count": used_in_activation_count,
        "used_in_conflict_count": used_in_conflict_count,
        "system_duplicate_candidate_count": duplicate_candidate_count,
        "duplicate_exclusion_method": "claim_id exact match + normalize_claim_for_dedupe(evidence) text-identity match against all 50 old development rows",
        "old50_exclusion_proof": manifest_extra,
        "alpha_soft_cap_fraction": ALPHA_SOFT_CAP_FRACTION,
        "stratification_signals_used": [
            "relation (activation/invalidation/risk_relief/conditional/mixed/mention)",
            "match_score tier (high >=0.6 / medium 0.35-0.6)",
            "direction",
            "used_in_activation",
            "used_in_conflict",
            "duplicate_group_size (evidence_fact_group membership)",
            "ai_gate_alpha (matched_alpha_id in AI_ALPHA_IDS)",
            "matched_alpha_id (soft-capped per ticker to avoid A101/A301/A304 domination)",
        ],
        "reviewer_labels_used_for_selection": False,
        "csv_sha256": csv_sha256,
        "csv_path": str(OUTPUT_CSV_PATH.relative_to(REPO_ROOT)),
    }
    OUTPUT_MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Wrote {len(rows)} rows -> {OUTPUT_CSV_PATH}")
    print(f"csv_sha256 = {csv_sha256}")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
