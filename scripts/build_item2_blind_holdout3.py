#!/usr/bin/env python3
"""QA Closure v0.1.2 -- Item 2 Blind Holdout #3: build and FREEZE the holdout
population BEFORE any production Alpha Mapper / independent-reviewer
evaluation runs against it.

Draws exclusively from already-persisted, saved-run alpha_matches.json files
(never a new research run). Excludes every row from the historical 50-row
development set, Blind Holdout #1 (100 rows), AND Blind Holdout #2 (141
rows), by exact claim_id AND by normalize_claim_for_dedupe-normalized
evidence text (the same established repo dedupe normalization reused for
Holdout #1 and #2). Also deduplicates within Holdout #3 itself.

Section 6/7 compliance (Blind Holdout #3 task spec -- stricter than Holdout
#1/#2's own frozen schema): the historical, persisted matched_alpha_id from
each source run is used ONLY internally, to stratify/diversify the sample
(soft-cap per Alpha family) -- it is a "historical/frozen source label", not
the official expected Alpha, and is NEVER written into the frozen holdout
CSV itself (which could anchor the independent reviewer or be mistaken for
ground truth). It is recorded separately, in the manifest only, under a key
explicitly labeled as non-authoritative.

SNDK and TSM are fully exhausted after excluding old-50 + Holdout #1 +
Holdout #2 (0 eligible rows remain in either -- Holdout #2 already consumed
their complete available pools) and are excluded entirely, not padded.
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
HOLDOUT2_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout_141_v2.csv"

SAMPLING_VERSION = "item2_blind_holdout3.v1"
RANDOM_SEED = "item2_blind_holdout3_deterministic_seed"

# Full read-only inventory of outputs/runs/*/alpha_matches.json (Section 4)
# -- every ticker with a persisted alpha_matches.json, not merely the subset
# Holdout #2 happened to use. GOOGL and MU are genuinely new tickers, never
# touched by old-50/Holdout #1/Holdout #2.
RUNS: dict[str, list[str]] = {
    "AMD": ["66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1", "b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6"],
    "GOOGL": ["299bb6af-5217-422e-bd47-1b3b07c57192", "fadaa93c-8cd5-40df-a1bb-53ac4ccd1fb3"],
    "MSFT": ["61f3e019-63a8-4c56-b763-057208d5efae", "0cb43bae-1a4d-4003-bb29-55d420498842", "07ddc074-9ab2-4b16-8957-acbf94012144"],
    "MU": ["0ba23540-0623-4d05-a670-098fbbfec1d1"],
    "NVDA": ["4ca7dafa-6ac1-4d94-add0-f6f93b1af150", "0e044e37-862c-43be-871c-31012cd660e7", "e434f80b-e4d0-4b09-9471-d84532659de5", "e3eb3909-3744-4a02-9b32-b225cf6ef665", "5ffe121a-68fd-473b-82b5-c9465332d8a2"],
    "QQQ": ["a364e0ee-3bb4-4032-88b7-5cd82e379805"],
    # SNDK/TSM deliberately absent: 0 eligible rows remain after exclusion
    # (Holdout #2 already consumed their complete available pools). Not
    # padded, not substituted, reported explicitly.
}
# QQQ capped by genuine post-exclusion pool size (12); the other five use a
# shared per-ticker target chosen to reach close to the 150-row preferred
# target while leaving meaningful headroom on the two largest pools
# (GOOGL 96, NVDA 242) and using most-but-not-all of the two smallest
# (MSFT 32, MU 32) -- not proportional-to-pool-size, to avoid NVDA/GOOGL
# dominating the sample.
TARGET_COUNTS: dict[str, int] = {"AMD": 28, "GOOGL": 28, "MSFT": 28, "MU": 28, "NVDA": 28, "QQQ": 12}
EXHAUSTED_TICKERS = {"SNDK": "0 eligible rows after exclusion (Holdout #2 already used the complete available pool)", "TSM": "0 eligible rows after exclusion (Holdout #2 already used the complete available pool)"}

ALPHA_SOFT_CAP_FRACTION = 0.35


def _load_exclusion_set() -> tuple[set[str], set[str], int, int, int]:
    old50 = json.loads(OLD_SAMPLE_PATH.read_text(encoding="utf-8"))["records"]
    ids = {r["claim_id"] for r in old50}
    texts = {normalize_claim_for_dedupe(r["evidence"]) for r in old50}
    with HOLDOUT1_PATH.open(encoding="utf-8", newline="") as f:
        h1 = list(csv.DictReader(f))
    ids |= {r["claim_id"] for r in h1}
    texts |= {normalize_claim_for_dedupe(r["evidence"]) for r in h1}
    with HOLDOUT2_PATH.open(encoding="utf-8", newline="") as f:
        h2 = list(csv.DictReader(f))
    ids |= {r["claim_id"] for r in h2}
    texts |= {normalize_claim_for_dedupe(r["evidence"]) for r in h2}
    return ids, texts, len(old50), len(h1), len(h2)


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
                    # Historical/frozen source label -- internal stratification
                    # signal ONLY (Section 6). Never the official expected
                    # Alpha, never written to the frozen CSV.
                    "historical_matched_alpha_id_not_official_label": m["matched_alpha"],
                    "historical_matched_alpha_name_not_official_label": m.get("matched_alpha_name"),
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
                alpha_key = candidate["historical_matched_alpha_id_not_official_label"]
                if alpha_counts[alpha_key] >= soft_cap:
                    deferred.append(candidate)
                    continue
                selected.append(candidate)
                alpha_counts[alpha_key] += 1
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
    exclude_claim_ids, exclude_texts, old50_count, h1_count, h2_count = _load_exclusion_set()
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
        row["sample_id"] = f"holdout3-{i:03d}"

    manifest_extra = {
        "pool_sizes_after_exclusion_and_dedup": pool_sizes,
        "target_vs_actual_shortfall": shortfall,
        "exhausted_tickers_excluded": EXHAUSTED_TICKERS,
        "old50_excluded_row_count": old50_count,
        "holdout1_excluded_row_count": h1_count,
        "holdout2_excluded_row_count": h2_count,
        "total_exclusion_claim_id_count": len(exclude_claim_ids),
        "total_exclusion_normalized_text_count": len(exclude_texts),
    }
    return all_selected, manifest_extra


# Section 7: strict minimal frozen schema -- no system/historical Alpha
# fields of any kind, so nothing can anchor the independent reviewer.
FROZEN_CSV_FIELDS = ["sample_id", "run_id", "ticker", "claim_id", "agent", "claim", "evidence"]


def main() -> int:
    rows, manifest_extra = build_holdout()
    n = len(rows)
    assert len({r["sample_id"] for r in rows}) == n
    assert len({r["claim_id"] for r in rows}) == n
    assert len({normalize_claim_for_dedupe(r["evidence"]) for r in rows}) == n, "within-holdout duplicate evidence text found"

    frozen_csv_path = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout3_frozen.csv"
    # Sampling-metadata sidecar: retains the historical stratification label
    # and diagnostic fields for later offline diagnostics (Sections 15-17)
    # WITHOUT it ever being part of the frozen evaluation file itself.
    sampling_metadata_path = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout3_sampling_metadata.json"
    manifest_path = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout3_freeze_manifest_sampling.json"

    frozen_rows = []
    for r in rows:
        frozen_rows.append(
            {
                "sample_id": r["sample_id"], "run_id": r["source_run_id"], "ticker": r["ticker"],
                "claim_id": r["claim_id"], "agent": r["agent"], "claim": r["claim"], "evidence": r["evidence"],
            }
        )

    with frozen_csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FROZEN_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(frozen_rows)

    csv_sha256 = hashlib.sha256(frozen_csv_path.read_bytes()).hexdigest()
    ticker_dist = Counter(r["ticker"] for r in rows)
    historical_alpha_dist = Counter(r["historical_matched_alpha_id_not_official_label"] for r in rows)
    relation_dist = Counter(r["relation"] for r in rows)
    agent_dist = Counter(r["agent"] for r in rows)

    # Sampling metadata sidecar (NOT the frozen evaluation file): keeps the
    # per-row historical label + diagnostics for later offline use, keyed
    # by sample_id so it can be joined back in after evaluation without
    # ever having been part of the frozen/reviewer-facing artifact.
    sampling_metadata = {
        row["sample_id"]: {
            "historical_matched_alpha_id_not_official_label": row["historical_matched_alpha_id_not_official_label"],
            "historical_matched_alpha_name_not_official_label": row["historical_matched_alpha_name_not_official_label"],
            "historical_match_score": row["match_score"],
            "historical_relation": row["relation"],
            "historical_direction": row["direction"],
            "historical_used_in_activation": row["used_in_activation"],
            "historical_used_in_conflict": row["used_in_conflict"],
            "historical_duplicate_group_size": row["duplicate_group_size"],
            "historical_ai_gate_alpha": row["ai_gate_alpha"],
        }
        for row in rows
    }
    sampling_metadata_path.write_text(json.dumps(sampling_metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest = {
        "schema_version": "item2_blind_holdout3_manifest.v1",
        "sample_count": n,
        "sampling_version": SAMPLING_VERSION,
        "random_seed": RANDOM_SEED,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_runs": RUNS,
        "ticker_distribution": dict(ticker_dist),
        "ticker_targets": TARGET_COUNTS,
        "historical_alpha_distribution_not_official_label": dict(historical_alpha_dist),
        "relation_distribution": dict(relation_dist),
        "agent_distribution": dict(agent_dist),
        "alpha_soft_cap_fraction": ALPHA_SOFT_CAP_FRACTION,
        "exclusion": manifest_extra,
        "duplicate_exclusion_method": "claim_id exact match + normalize_claim_for_dedupe(evidence) text-identity match against ALL rows from the historical 50-row development set, Blind Holdout #1 (100 rows), AND Blind Holdout #2 (141 rows); also deduplicated within Holdout #3 itself by the same normalized-text key",
        "reviewer_labels_used_for_selection": False,
        "current_system_prediction_used_for_selection": False,
        "frozen_csv_fields": FROZEN_CSV_FIELDS,
        "frozen_csv_sha256": csv_sha256,
        "frozen_csv_path": str(frozen_csv_path.relative_to(REPO_ROOT)),
        "sampling_metadata_path": str(sampling_metadata_path.relative_to(REPO_ROOT)),
        "sampling_metadata_note": "Historical matched_alpha_id used ONLY for internal stratification diversity during sampling (Section 6) -- NOT the official expected Alpha, NOT exposed to the reviewer, NOT part of the frozen evaluation file.",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Wrote {n} rows -> {frozen_csv_path}")
    print(f"frozen_csv_sha256 = {csv_sha256}")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
