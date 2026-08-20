#!/usr/bin/env python3
"""QA Closure v0.1.2 -- Item 2 NEW blind holdout: run the CURRENT, exact
production Alpha Mapper (comqutor_alpha.structure_engine.alpha_mapper.
map_claim_to_alpha) fresh against each of the 100 frozen holdout rows'
FULL original structured record (pulled from that row's own source run's
structured_agent_outputs.json by claim_id -- never a lossy reconstruction
from the holdout CSV's own trimmed columns).

Deterministic, offline: classifier_enabled=False, llm_gateway=None (no
Tier-2 LLM classifier, no Provider call) -- pure Alpha Mapper, unmodified
threshold/weights/AI_ALPHA_IDS/candidate-pool rules.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy  # noqa: E402
from comqutor_alpha.structure_engine.alpha_mapper import map_claim_to_alpha  # noqa: E402

HOLDOUT_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout_100.csv"
OUTPUT_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout_alpha_predictions.csv"

CSV_FIELDS = [
    "sample_id", "claim_id", "matched_alpha_id", "matched_alpha_name", "match_score", "match_status",
    "candidate_ranking", "rejection_reason_for_matched", "ai_gate_applicable",
    "matches_frozen_csv_matched_alpha", "matches_frozen_csv_match_score",
]


def _load_holdout_rows() -> list[dict[str, Any]]:
    with HOLDOUT_CSV_PATH.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _structured_record_for(run_id: str, claim_id: str, cache: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if run_id not in cache:
        payload = json.loads((REPO_ROOT / "outputs" / "runs" / run_id / "structured_agent_outputs.json").read_text(encoding="utf-8"))
        cache[run_id] = {r["claim_id"]: r for r in payload["records"]}
    return cache[run_id].get(claim_id)


def main() -> int:
    rows = _load_holdout_rows()
    assert len(rows) == 100
    taxonomy = load_alpha_taxonomy()
    structured_cache: dict[str, dict[str, Any]] = {}

    out_rows = []
    for row in rows:
        record = _structured_record_for(row["source_run_id"], row["claim_id"], structured_cache)
        if record is None:
            raise SystemExit(f"MISSING_STRUCTURED_RECORD: {row['sample_id']} claim_id={row['claim_id']}")

        result = map_claim_to_alpha(record, taxonomy, classifier_enabled=False, llm_gateway=None)
        matched_alpha = result.get("matched_alpha")
        matched_candidate = next(
            (c for c in (result.get("candidate_scores") or []) if c.get("alpha_id") == matched_alpha), None
        )
        ranking = sorted(result.get("candidate_scores") or [], key=lambda c: -(c.get("score") or 0))
        ranking_str = "; ".join(f"{c['alpha_id']}={c.get('score')}({'eligible' if c.get('eligible') else 'ineligible'})" for c in ranking)

        frozen_alpha = row["system_matched_alpha_id"]
        frozen_score = row["system_match_score"]

        out_rows.append(
            {
                "sample_id": row["sample_id"],
                "claim_id": row["claim_id"],
                "matched_alpha_id": matched_alpha or "",
                "matched_alpha_name": result.get("matched_alpha_name") or "",
                "match_score": matched_candidate.get("score") if matched_candidate else None,
                "match_status": result.get("match_status"),
                "candidate_ranking": ranking_str,
                "rejection_reason_for_matched": (matched_candidate or {}).get("rejection_reason") or "",
                "ai_gate_applicable": bool(matched_candidate and matched_candidate.get("alpha_id") in {"A101", "A102", "A103"}),
                "matches_frozen_csv_matched_alpha": (matched_alpha or "") == frozen_alpha,
                "matches_frozen_csv_match_score": str(matched_candidate.get("score") if matched_candidate else "") == frozen_score,
            }
        )

    with OUTPUT_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(out_rows)

    mismatches = [r for r in out_rows if not r["matches_frozen_csv_matched_alpha"]]
    print(f"Wrote {len(out_rows)} rows -> {OUTPUT_CSV_PATH}")
    print(f"Fresh-vs-frozen-CSV matched_alpha_id mismatches: {len(mismatches)}")
    for m in mismatches:
        print(" ", m["sample_id"], m["claim_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
