#!/usr/bin/env python3
"""Amend recovery_lineage.json of the real recovery execution so its per-claim labels are TRUE.

As first written, the lineage labelled all 973 recovered claims `recovered_real_classification`. The execution's
own records contradict that for two groups:
  * 1 claim whose request timed out (45.01 s, no response saved): its record is `llm_unavailable /
    provider_timeout` -- an attempt, not a recovered classification;
  * 18 claims served by the run-local exact response cache (provider_status `not_called`): they carry an
    identical-input sibling's real answer, not their own request.

Only `classification_source` / `cache_source_call_id` / the counts change. The first-written file is kept next to
this script with its sha256, and every change is recorded inside the amended artifact (`amendments`). No
classification result, alpha_matches, score or anything else in the run is touched. The artifact manifest is
rebuilt with the production function so its hashes match the amended file.
"""
import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
EXECUTION_ID = sys.argv[1]

spec = importlib.util.spec_from_file_location("recover_amend", REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round12_alpha_classifier_audit_fix_20261006/recover_alpha_classification.py")
recover = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recover)
from comqutor_alpha.api.artifact_export import build_and_write_artifact_manifest
from comqutor_alpha.storage.file_store import save_json_record

output_root = recover.OUTPUT_ROOT
run_dir = output_root / EXECUTION_ID
lineage_path = run_dir / "recovery_lineage.json"
raw = lineage_path.read_bytes()
lineage = json.loads(raw)
if lineage.get("amendments"):
    sys.exit("already amended; refusing to amend twice")
(HERE / "recovery_lineage_as_first_written.json").write_bytes(raw)
previous_sha = hashlib.sha256(raw).hexdigest()

matches = {m["claim_id"]: m for m in json.loads((run_dir / "alpha_matches.json").read_text())["matches"]}
cache_sources = recover.cache_served_claims(output_root, EXECUTION_ID)
changes = []
for entry in lineage["claim_identity_map"]:
    claim_id = entry["claim_id"]
    entry["cache_source_call_id"] = cache_sources.get(claim_id)
    if entry["classification_source"] != "recovered_real_classification":
        continue
    match = matches[claim_id]
    if match.get("alpha_match_method") != "llm" or match.get("alpha_match_fallback_reason"):
        new_label = "attempted_failed_no_valid_result"
    elif claim_id in cache_sources:
        new_label = "recovered_via_identical_input_cache"
    else:
        continue
    changes.append({"claim_id": claim_id, "from": entry["classification_source"], "to": new_label,
                    "evidence": {"derived_alpha_match_method": match.get("alpha_match_method"),
                                 "derived_fallback_reason": match.get("alpha_match_fallback_reason"),
                                 "cache_source_call_id": cache_sources.get(claim_id)}})
    entry["classification_source"] = new_label

counts = {}
for entry in lineage["claim_identity_map"]:
    counts[entry["classification_source"]] = counts.get(entry["classification_source"], 0) + 1
lineage["classification_source_counts"] = counts
lineage["amendments"] = [{
    "amended_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "reason": ("first-written labels over-claimed: a timed-out attempt and 18 cache-served claims were labelled "
               "recovered_real_classification; corrected from the execution's own alpha_matches and semantic-call ledger"),
    "first_written_sha256": previous_sha,
    "first_written_copy": "docs/audit_artifacts/round_source_linking_t0_t2/round16_real_recovery_20261006/recovery_lineage_as_first_written.json",
    "first_written_counts": {"reused_original_valid_result": 2, "recovered_real_classification": 973},
    "fields_changed": ["claim_identity_map[*].classification_source (for the listed claims)", "claim_identity_map[*].cache_source_call_id (added)", "classification_source_counts"],
    "changed_claims": changes,
    "unchanged": "alpha_matches.json and every result, score and other artifact",
}]
save_json_record(EXECUTION_ID, "recovery_lineage.json", lineage, output_root=output_root)
build_and_write_artifact_manifest(run_id=EXECUTION_ID, ticker=lineage["ticker"], output_root=output_root)
print(json.dumps({"changed_claims": len(changes), "counts_now": counts, "first_written_sha256": previous_sha,
                  "amended_sha256": hashlib.sha256(lineage_path.read_bytes()).hexdigest()}, indent=1))
