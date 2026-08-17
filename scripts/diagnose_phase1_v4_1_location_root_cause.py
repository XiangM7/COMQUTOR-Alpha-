#!/usr/bin/env python3
"""Read-only, Provider-zero forensic diagnosis of why the final v4.1
Re-Canary's Evidence-location resolution failed (0/4 slots passed).

Reads ONLY already-persisted artifacts from the real, completed Re-Canary
(``outputs/canaries/phase1-v4-1-final-recanary-20260810T230224Z/``) and the
frozen historical source run (``outputs/runs/0e044e37-.../
raw_agent_outputs.json``). Makes zero Provider/network calls, spawns zero
subagents, and modifies zero production code or state. Writes one JSON
companion (``phase1_v4_1_location_root_cause.json``) that the accompanying
Markdown report is built from.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
RECANARY_DIR = REPO_ROOT / "outputs/canaries/phase1-v4-1-final-recanary-20260810T230224Z"
SOURCE_RUN_PATH = REPO_ROOT / "outputs/runs/0e044e37-862c-43be-871c-31012cd660e7/raw_agent_outputs.json"
OUT_JSON = REPO_ROOT / "docs/audit_artifacts/phase1_master/phase1_v4_1_location_root_cause.json"

SLOT_FILES = {
    "fundamental": "01-fundamental.json",
    "news": "02-news.json",
    "sentiment": "03-sentiment.json",
    "technical": "04-technical.json",
}
CANONICAL_MARKER = "COMQUTOR_CANONICAL_RELATIONS"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def context(text: str, offset: int, length: int, radius: int) -> str:
    start = max(0, offset - radius)
    end = min(len(text), offset + length + radius)
    return text[start:end]


def classify_occurrence_location(raw_output: str, offset: int) -> str:
    marker_idx = raw_output.find(CANONICAL_MARKER)
    if marker_idx != -1 and offset >= marker_idx:
        return "CANONICAL_BLOCK"
    return "HUMAN_REPORT"


def windows_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def analyze_slot(family: str, raw_by_agent: dict[str, dict[str, Any]]) -> dict[str, Any]:
    slot = load_json(RECANARY_DIR / "slot_results" / SLOT_FILES[family])
    agent = slot["agent"]
    raw_record = raw_by_agent[agent]
    raw_output = str(raw_record.get("raw_output") or "")

    s1_sha256 = sha256_text(raw_output)
    slot_source_sha256 = slot.get("source_report_sha256")
    forensic = slot.get("rejected_forensics") or {}
    forensic_source_sha256 = forensic.get("source_report_sha256")

    diagnostics = slot.get("resolution_diagnostics") or []
    manifest = slot.get("candidate_manifest") or []
    manifest_by_id = {item["candidate_id"]: item for item in manifest if isinstance(item, dict)}

    marker_count_in_source = raw_output.count(CANONICAL_MARKER)

    per_item: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for item in diagnostics:
        status = item.get("resolution_status")
        quote = item.get("quote", "")
        global_offsets = item.get("global_exact_match_offsets") or []
        global_count = item.get("global_exact_match_count", len(global_offsets))
        selected_id = item.get("selected_candidate_id")
        cand_start = item.get("candidate_source_start")
        cand_end = item.get("candidate_source_end")
        local_offsets = item.get("candidate_local_match_offsets") or []

        located = status in ("UNIQUE_EXACT_MATCH", "DISAMBIGUATED_VIA_CANDIDATE_BINDING")
        entry: dict[str, Any] = {
            "claim_index": item.get("claim_index"),
            "evidence_index": item.get("evidence_index"),
            "quote_sha256": item.get("quote_sha256"),
            "quote_len": len(quote),
            "quote_preview": quote[:160],
            "resolution_status": status,
            "global_exact_match_count": global_count,
            "global_exact_match_offsets": global_offsets,
            "selected_candidate_id": selected_id,
            "candidate_source_start": cand_start,
            "candidate_source_end": cand_end,
            "candidate_local_match_offsets": local_offsets,
        }
        if located:
            entry["root_cause"] = "NONE_LOCATED_OK"
            per_item.append(entry)
            counts["NONE_LOCATED_OK"] = counts.get("NONE_LOCATED_OK", 0) + 1
            continue

        # --- classification ---
        root_cause = "UNKNOWN_INSUFFICIENT_FORENSICS"
        occurrence_types = [classify_occurrence_location(raw_output, off) for off in global_offsets]
        entry["occurrence_location_types"] = occurrence_types

        if global_count == 0:
            root_cause = "ZERO_GLOBAL_EXACT_MATCH"

        elif global_count == 1:
            # A single, unambiguous global occurrence. If it still failed,
            # a candidate_id MUST have been supplied and MUST have missed.
            only_offset = global_offsets[0]
            if selected_id is None:
                root_cause = "UNKNOWN_INSUFFICIENT_FORENSICS"  # should not happen; flag for review
            else:
                candidate = manifest_by_id.get(selected_id)
                selected_covers = (
                    isinstance(cand_start, int)
                    and isinstance(cand_end, int)
                    and cand_start <= only_offset < cand_end
                )
                any_other_candidate_covers = any(
                    isinstance(c.get("source_start"), int)
                    and isinstance(c.get("source_end"), int)
                    and c["source_start"] <= only_offset < c["source_end"]
                    for c in manifest
                )
                entry["selected_candidate_covers_unique_offset"] = selected_covers
                entry["some_other_candidate_covers_unique_offset"] = any_other_candidate_covers
                entry["candidate_exists_in_manifest"] = candidate is not None
                root_cause = "PROVIDER_WRONG_CANDIDATE_ID_FOR_UNIQUE_QUOTE"

        else:
            # Genuine multiple global occurrences.
            distinct_locations = set(occurrence_types)
            if "CANONICAL_BLOCK" in distinct_locations and "HUMAN_REPORT" in distinct_locations or distinct_locations == {"CANONICAL_BLOCK"}:
                root_cause = "CANONICAL_BLOCK_DUPLICATION"
            else:
                # All occurrences are in the human report body. Check whether
                # this is genuine text duplication vs. candidate-window
                # overlap creating fake ambiguity around a single occurrence
                # (not applicable here since count>1 means >1 real distinct
                # offsets exist by construction of _find_all_occurrences).
                root_cause = "TRUE_HUMAN_REPORT_DUPLICATE"
                if selected_id is not None:
                    candidate = manifest_by_id.get(selected_id)
                    selected_covers_any = (
                        isinstance(cand_start, int)
                        and isinstance(cand_end, int)
                        and any(cand_start <= off < cand_end for off in global_offsets)
                    )
                    entry["selected_candidate_covers_any_global_offset"] = selected_covers_any
                    if not selected_covers_any:
                        root_cause = "PROVIDER_WRONG_CANDIDATE_ID"
                else:
                    entry["no_candidate_id_supplied_for_genuine_duplicate"] = True

            # Candidate-window-overlap check: do >=2 candidates in the full
            # manifest overlap AND both contain the SAME single global
            # offset (a different phenomenon from true multi-offset
            # duplication, checked per-offset).
            overlap_hits = []
            for off in global_offsets:
                covering = [
                    c["candidate_id"]
                    for c in manifest
                    if isinstance(c.get("source_start"), int)
                    and isinstance(c.get("source_end"), int)
                    and c["source_start"] <= off < c["source_end"]
                ]
                if len(covering) > 1:
                    overlap_hits.append({"offset": off, "covering_candidate_ids": covering})
            entry["candidate_window_overlap_per_offset"] = overlap_hits

            entry["occurrence_contexts"] = [
                context(raw_output, off, len(quote), 250) for off in global_offsets
            ]

        entry["root_cause"] = root_cause
        counts[root_cause] = counts.get(root_cause, 0) + 1
        per_item.append(entry)

    return {
        "family": family,
        "agent": agent,
        "source_agent_output_id": slot.get("source_agent_output_id"),
        "raw_output_len": len(raw_output),
        "canonical_marker_count_in_raw_output": marker_count_in_source,
        "s1_raw_output_sha256": s1_sha256,
        "slot_recorded_source_report_sha256": slot_source_sha256,
        "forensic_recorded_source_report_sha256": forensic_source_sha256,
        "s1_equals_slot_source": s1_sha256 == slot_source_sha256,
        "s1_equals_forensic_source": s1_sha256 == forensic_source_sha256,
        "evidence_resolution_summary": slot.get("evidence_resolution"),
        "reason_codes": slot.get("reason_codes"),
        "candidate_manifest_count": len(manifest),
        "total_evidence_items": len(diagnostics),
        "root_cause_counts": counts,
        "items": per_item,
    }


def main() -> None:
    raw = load_json(SOURCE_RUN_PATH)
    raw_by_agent = {
        item["agent"]: item for item in raw.get("agent_outputs") or [] if isinstance(item, dict)
    }

    results = {family: analyze_slot(family, raw_by_agent) for family in SLOT_FILES}

    overall_counts: dict[str, int] = {}
    for slot_result in results.values():
        for cause, n in slot_result["root_cause_counts"].items():
            overall_counts[cause] = overall_counts.get(cause, 0) + n

    output = {
        "schema_version": "comqutor.phase1_v4_1_location_root_cause_diagnosis.v1",
        "recanary_dir": str(RECANARY_DIR.relative_to(REPO_ROOT)),
        "source_run_path": str(SOURCE_RUN_PATH.relative_to(REPO_ROOT)),
        "per_slot": results,
        "overall_root_cause_counts": overall_counts,
        "provider_calls": 0,
        "subagents": 0,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {OUT_JSON.relative_to(REPO_ROOT)}")
    for family, slot_result in results.items():
        print(f"\n=== {family} ===")
        print(f"  s1_equals_slot_source={slot_result['s1_equals_slot_source']} "
              f"s1_equals_forensic_source={slot_result['s1_equals_forensic_source']} "
              f"canonical_marker_count={slot_result['canonical_marker_count_in_raw_output']}")
        print(f"  total_evidence_items={slot_result['total_evidence_items']}")
        for cause, n in sorted(slot_result["root_cause_counts"].items()):
            print(f"    {cause}: {n}")
    print("\n=== OVERALL ===")
    for cause, n in sorted(overall_counts.items()):
        print(f"  {cause}: {n}")


if __name__ == "__main__":
    main()
