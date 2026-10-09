#!/usr/bin/env python3
"""Round 22: a trimmed, REAL-data fixture of the historical AMD run ``d5b60b8a-...`` (the run of John's original 34 conflict
evidence items) for the Conflict-page "View basis" tests.

READ-ONLY on the historical run: it only reads the run's saved files (hashes are checked before and after) and writes the
fixture under ``tests/fixtures/``. Nothing from the newer AMD runs is used: the fixture shows what the historical run
itself saved -- which is exactly why its claims carry no source-link fields.

Kept: metadata, the structured records / Alpha matches of three of the 34 evidence claims (one bull, one bear, one counter),
the FULL A301 and A304 activation blocks (the run's own saved scoring), and every admitted conflict of the run with its
evidence list trimmed to those three claims (conflict id, status, level, score and every other field untouched).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
RUN_ID = "d5b60b8a-66b8-44c1-9f55-ee345e58c48d"
RUN = REPO / "outputs" / "runs" / RUN_ID
OUT = REPO / "tests" / "fixtures" / "t1_closeout_legacy_conflict_excerpt.json"
PICK = {  # side -> claim id suffix (taken from the run's own admitted conflict A301__A304)
    "bull": "bull_researcher:investment_debate_state.bull_history:claim:107",
    "bear": "news_agent:news_report:claim:99",
    "counter": "news_agent:news_report:claim:90",
}


def run_hashes() -> dict[str, str]:
    return {str(p.relative_to(RUN)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(RUN.rglob("*")) if p.is_file()}


def load(name: str):
    return json.loads((RUN / name).read_text(encoding="utf-8"))


def main() -> None:
    before = run_hashes()
    claim_ids = {side: f"{RUN_ID}:{suffix}" for side, suffix in PICK.items()}
    wanted = set(claim_ids.values())
    structured = load("structured_agent_outputs.json")
    matches = load("alpha_matches.json")
    graph = load("structure_graph.json")
    conflicts = load("conflicts.json")

    def trim_evidence_ui(evidence_ui: dict) -> dict:
        out = dict(evidence_ui)
        for key in ("bull_evidence", "bear_evidence", "counter_evidence"):
            out[key] = [i for i in evidence_ui.get(key) or [] if wanted & ({i.get("representative_claim_id")} | set(i.get("member_claim_ids") or []))]
        return out

    def trim_conflict(conflict: dict) -> dict:
        trimmed = dict(conflict)
        if isinstance(conflict.get("evidence_ui"), dict):
            trimmed["evidence_ui"] = trim_evidence_ui(conflict["evidence_ui"])
        return trimmed

    trimmed_conflicts = dict(conflicts)
    trimmed_conflicts["conflicts"] = [trim_conflict(c) for c in conflicts.get("conflicts") or []]
    trimmed_conflicts["main_conflict"] = trim_conflict(conflicts["main_conflict"]) if conflicts.get("main_conflict") else None
    trimmed_conflicts["arbitration"] = {k: v for k, v in (conflicts.get("arbitration") or {}).items() if k != "candidate_evaluations"}

    alphas = [a for a in graph["activation"]["alphas"] if a["alpha_id"] in ("A301", "A304")]
    fixture = {
        "_provenance": {
            "what": "trimmed copy of the SAVED historical AMD run (read-only extraction); not a newer run, not synthetic",
            "source_run_id": RUN_ID,
            "evidence_cutoff": load("metadata.json").get("analysis_date"),
            "claims": claim_ids,
            "kept": "metadata; structured records + Alpha matches of the three claims; full A301/A304 activation blocks; every conflict of the run with its evidence list trimmed to the three claims",
            "source_run_files_sha256_unchanged_by_extraction": None,
        },
        "metadata": load("metadata.json"),
        "records": [r for r in structured["records"] if r["claim_id"] in wanted],
        "matches": [m for m in matches["matches"] if m["claim_id"] in wanted],
        "activation_alphas": alphas,
        "activation_header": {k: v for k, v in graph["activation"].items() if k != "alphas"},
        "conflicts": trimmed_conflicts,
    }
    after = run_hashes()
    assert before == after, "the historical run changed while extracting -- impossible for a read-only extraction"
    fixture["_provenance"]["source_run_files_sha256_unchanged_by_extraction"] = True
    assert len(fixture["records"]) == 3 and len(fixture["matches"]) == 3 and {a["alpha_id"] for a in alphas} == {"A301", "A304"}
    OUT.write_text(json.dumps(fixture, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"fixture": str(OUT.relative_to(REPO)), "bytes": OUT.stat().st_size, "records": len(fixture["records"]),
                      "conflicts": [c["conflict_id"] for c in trimmed_conflicts["conflicts"]], "historical_run_files_hashed": len(after)}, indent=1))


if __name__ == "__main__":
    main()
