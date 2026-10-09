#!/usr/bin/env python3
"""T4 round 34 (D1 fix): write the minimal diff, the changed-file list and the old / new prompt versions with their identity
hashes. Reads the pre-fix copies saved in 02_code/before/ and the current working tree; writes only into 02_code/.

    python tools/make_code_evidence34.py
"""
from __future__ import annotations

import difflib
import hashlib
import json
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
REPO = next(p for p in R.parents if (p / "comqutor_alpha").is_dir())
BEFORE = R / "02_code" / "before"
NEW_FILES = ["tests/test_t4_round34_d1_adapter_citation_contract.py"]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    sys.path.insert(0, str(REPO))
    from comqutor_alpha.replay.source_bundle import _SUPPORTED_CALL_IDENTITIES
    from comqutor_alpha.run_environment import process_code_identity
    from comqutor_alpha.structure_engine import week2_llm as w

    changed, chunks = [], []
    for before in sorted(p for p in BEFORE.rglob("*") if p.is_file()):
        rel = before.relative_to(BEFORE).as_posix()
        old, new = before.read_bytes(), (REPO / rel).read_bytes()
        entry = {"path": rel, "sha256_before": sha(old), "sha256_after": sha(new), "changed": old != new}
        changed.append(entry)
        if old != new:
            chunks.append("".join(difflib.unified_diff(old.decode("utf-8").splitlines(True), new.decode("utf-8").splitlines(True),
                                                       fromfile=f"a/{rel}", tofile=f"b/{rel}")))
    for rel in NEW_FILES:
        new = (REPO / rel).read_bytes()
        changed.append({"path": rel, "sha256_before": None, "sha256_after": sha(new), "changed": True, "new_file": True})
        chunks.append("".join(difflib.unified_diff([], new.decode("utf-8").splitlines(True), fromfile="/dev/null", tofile=f"b/{rel}")))
    out = R / "02_code"
    (out / "round34_d1_changes.diff").write_text("".join(chunks), encoding="utf-8")
    ci = process_code_identity()
    (out / "changed_files.json").write_text(json.dumps({
        "code_identity_before": {"tracked_diff_sha256": "6cdd51e345929a1936845a416dd8a38c6f00ea3d0293afa03282d002dc96857c",
                                 "untracked_runtime_source_sha256": "10ee75185ae8032bc9bdf304152a87c1d22db08120cdd546d31925277e21f0f6"},
        "code_identity_after": {k: ci.get(k) for k in ("git_head", "tracked_diff_sha256", "untracked_runtime_source_files", "untracked_runtime_source_sha256")},
        "files": changed,
        "diff_sha256": sha((out / "round34_d1_changes.diff").read_bytes()),
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    meta = w._TASK_RUNTIME_METADATA["claim_batch_enrichment"]
    retired = w._RETIRED_TASK_PROMPTS["week2.claim_batch_enrichment.v1"]
    identity_text = lambda instruction: f"{w._SHARED_JSON_ONLY_PROMPT_PREFIX}{instruction}{w._PROMPT_IDENTITY_SEPARATOR}"
    doc = {
        "how_the_identity_is_computed": "sha256 of shared JSON-only prefix + task instruction + the literal identity separator \\nINPUT_JSON:\\n "
                                        "(Week2LLMGateway.prompt_identity_text); the dynamic payload is excluded",
        "identity_prefix": w._SHARED_JSON_ONLY_PROMPT_PREFIX,
        "identity_separator": w._PROMPT_IDENTITY_SEPARATOR,
        "v1_retired": {"prompt_version": "week2.claim_batch_enrichment.v1", "input_schema_version": retired["input_schema_version"],
                       "output_schema_version": retired["output_schema_version"], "instruction": retired["instruction"],
                       "prompt_sha256": sha(identity_text(retired["instruction"]).encode("utf-8")),
                       "prompt_sha256_via_gateway": w.Week2LLMGateway.retired_prompt_identity_sha256("week2.claim_batch_enrichment.v1"),
                       "recorded_by_both_fresh_runs": "c6822099e2171c6fbad72c36bf2881bcd59bd4d4ad2fc20e10ab62af50b5bfd9"},
        "v2_live": {"prompt_version": meta["prompt_version"], "input_schema_version": meta["input_schema_version"],
                    "output_schema_version": meta["output_schema_version"], "instruction": w._TASK_INSTRUCTIONS["claim_batch_enrichment"],
                    "prompt_sha256": sha(identity_text(w._TASK_INSTRUCTIONS["claim_batch_enrichment"]).encode("utf-8")),
                    "prompt_sha256_via_gateway": w.Week2LLMGateway.prompt_identity_sha256("claim_batch_enrichment")},
        "replay_registry_structured_adapter": list(_SUPPORTED_CALL_IDENTITIES["structured_adapter"]),
    }
    v1_text, v2_text = doc["v1_retired"]["instruction"], doc["v2_live"]["instruction"]
    v1_sentences = [x.strip().rstrip(".") + "." for x in v1_text.split(". ") if x.strip()]
    doc["v1_sentences_verbatim_in_v2"] = [x for x in v1_sentences if x in v2_text]
    doc["v1_sentences_changed_in_v2"] = [
        {"v1": x, "v2": x.replace("entities, factors, direction, and confidence", "entities, factors, direction, confidence, and cited_source_id"),
         "v2_contains_it": x.replace("entities, factors, direction, and confidence", "entities, factors, direction, confidence, and cited_source_id") in v2_text}
        for x in v1_sentences if x not in v2_text]
    (out / "prompt_versions.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"changed": [c["path"] for c in changed if c["changed"]], "unchanged_backups": [c["path"] for c in changed if not c["changed"]],
                      "v1": doc["v1_retired"]["prompt_sha256"], "v2": doc["v2_live"]["prompt_sha256"],
                      "code_after": ci.get("tracked_diff_sha256")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
