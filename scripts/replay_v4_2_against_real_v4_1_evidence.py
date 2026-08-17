#!/usr/bin/env python3
"""Zero-Provider, zero-subagent offline regression: re-run the new v4.2
``resolve_supporting_quote_v4_2`` against every one of the 99 real,
already-persisted Evidence quotes from the failed final v4.1 Re-Canary,
using the real source report text for each slot. No synthetic fixtures, no
hard-coded pass count -- the result is computed fresh from the actual
persisted artifacts every time this script runs.

Reads only:
  outputs/canaries/phase1-v4-1-final-recanary-20260810T230224Z/slot_results/*.json
  outputs/runs/0e044e37-862c-43be-871c-31012cd660e7/raw_agent_outputs.json

Writes:
  docs/audit_artifacts/phase1_master/phase1_v4_2_real_evidence_replay.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.structure_engine.structured_output_shadow_v4_2 import (  # noqa: E402
    RESOLUTION_STATUSES_LOCATED,
    resolve_supporting_quote_v4_2,
)

RECANARY_DIR = REPO_ROOT / "outputs/canaries/phase1-v4-1-final-recanary-20260810T230224Z"
SOURCE_RUN_PATH = REPO_ROOT / "outputs/runs/0e044e37-862c-43be-871c-31012cd660e7/raw_agent_outputs.json"
OUT_JSON = REPO_ROOT / "docs/audit_artifacts/phase1_master/phase1_v4_2_real_evidence_replay.json"

SLOT_FILES = {
    "fundamental": "01-fundamental.json",
    "news": "02-news.json",
    "sentiment": "03-sentiment.json",
    "technical": "04-technical.json",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    raw = load_json(SOURCE_RUN_PATH)
    raw_by_agent = {item["agent"]: item for item in raw.get("agent_outputs") or [] if isinstance(item, dict)}

    per_slot = {}
    total = 0
    total_accepted = 0
    total_zero_match = 0
    recovered_wrong_candidate_unique = 0
    genuine_duplicates_resolved = 0
    determinism_mismatches = 0

    for family, fname in SLOT_FILES.items():
        slot = load_json(RECANARY_DIR / "slot_results" / fname)
        agent = slot["agent"]
        raw_output = str(raw_by_agent[agent].get("raw_output") or "")
        v1_1_diagnostics = slot.get("resolution_diagnostics") or []

        items = []
        for old in v1_1_diagnostics:
            quote = old.get("quote", "")
            old_status = old.get("resolution_status")
            old_global_count = old.get("global_exact_match_count")

            # Run twice to prove determinism (required by TEST 8/11 spirit).
            new1 = resolve_supporting_quote_v4_2(report=raw_output, quote=quote)
            new2 = resolve_supporting_quote_v4_2(report=raw_output, quote=quote)
            deterministic = new1.to_diagnostic(claim_index=0, quote_index=0) == new2.to_diagnostic(
                claim_index=0, quote_index=0
            )
            if not deterministic:
                determinism_mismatches += 1

            located = new1.status in RESOLUTION_STATUSES_LOCATED
            total += 1
            if located:
                total_accepted += 1
            if new1.status == "NO_EXACT_MATCH":
                total_zero_match += 1

            was_previously_located = old_status in ("UNIQUE_EXACT_MATCH", "DISAMBIGUATED_VIA_CANDIDATE_BINDING")
            if not was_previously_located and located:
                if old_global_count == 1:
                    recovered_wrong_candidate_unique += 1
                elif old_global_count and old_global_count > 1:
                    genuine_duplicates_resolved += 1

            items.append(
                {
                    "quote_sha256": old.get("quote_sha256"),
                    "quote_len": len(quote),
                    "v4_1_status": old_status,
                    "v4_1_global_exact_match_count": old_global_count,
                    "v4_2_status": new1.status,
                    "v4_2_exact_match_count": new1.exact_match_count,
                    "v4_2_exact_match_offsets": list(new1.exact_match_offsets),
                    "v4_2_selected_start": new1.start,
                    "v4_2_selected_end": new1.end,
                    "v4_2_selection_policy": new1.selection_policy,
                    "v4_2_duplicate_exact_quote": new1.duplicate_exact_quote,
                    "deterministic_on_rerun": deterministic,
                    "match_counts_agree_with_v4_1_diagnosis": new1.exact_match_count == old_global_count,
                }
            )

        located_count = sum(1 for it in items if it["v4_2_status"] in ("UNIQUE_EXACT_MATCH", "DUPLICATE_ACCEPTED_EARLIEST_OCCURRENCE"))
        per_slot[family] = {
            "agent": agent,
            "total_evidence_items": len(items),
            "located_under_v4_2": located_count,
            "zero_match_under_v4_2": sum(1 for it in items if it["v4_2_status"] == "NO_EXACT_MATCH"),
            "items": items,
        }

    result = {
        "schema_version": "comqutor.phase1_v4_2_real_evidence_replay.v1",
        "source": "real, persisted final v4.1 Re-Canary resolution_diagnostics + real historical source reports",
        "provider_calls": 0,
        "subagents": 0,
        "offline_real_evidence_total": total,
        "offline_real_evidence_accepted": total_accepted,
        "offline_real_evidence_zero_match": total_zero_match,
        "previous_wrong_candidate_unique_cases_recovered": recovered_wrong_candidate_unique,
        "genuine_duplicate_cases_canonically_resolved": genuine_duplicates_resolved,
        "determinism_mismatches": determinism_mismatches,
        "provenance_replay": "PASS" if total_zero_match == 0 and determinism_mismatches == 0 else "FAIL",
        "per_slot": per_slot,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {OUT_JSON.relative_to(REPO_ROOT)}")
    print(f"OFFLINE_REAL_EVIDENCE_TOTAL={total}")
    print(f"OFFLINE_REAL_EVIDENCE_ACCEPTED={total_accepted}")
    print(f"OFFLINE_REAL_EVIDENCE_ZERO_MATCH={total_zero_match}")
    print(f"PREVIOUS_WRONG_CANDIDATE_UNIQUE_CASES_RECOVERED={recovered_wrong_candidate_unique}")
    print(f"GENUINE_DUPLICATE_CASES_CANONICALLY_RESOLVED={genuine_duplicates_resolved}")
    print(f"DETERMINISM_MISMATCHES={determinism_mismatches}")
    print(f"PROVENANCE_REPLAY={result['provenance_replay']}")
    for family, s in per_slot.items():
        print(f"  {family}: {s['located_under_v4_2']}/{s['total_evidence_items']} located, zero_match={s['zero_match_under_v4_2']}")
    return 0 if result["provenance_replay"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
