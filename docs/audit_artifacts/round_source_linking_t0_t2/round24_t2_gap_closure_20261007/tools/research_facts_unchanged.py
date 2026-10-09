#!/usr/bin/env python3
"""Round 24: the acceptance work changed verdicts, not research. For every ticker of the six fixed runs this compares what the Round 23 entry read from the saved
run with what the Round 24 entry reads from it now -- run id, artifact completeness, stance source, admitted / candidate conflicts, main conflict -- and the Alpha
facts the Round 24 verdict records next to each contract rule (identification, level, score) with the saved run's own activation_summary. It also hashes every file
of each of the six run directories, so a changed research artifact would show here as well.

    python research_facts_unchanged.py --round23 <round23 formal_acceptance_verdicts.json> --round24 <round24 formal_acceptance_verdicts.json> --out <json>

Read-only on the repository (outputs/runs is only read); exit 0 only when nothing differs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = next(p for p in Path(__file__).resolve().parents if (p / "comqutor_alpha").is_dir())
RESEARCH_FIELDS = ("run_id", "status", "artifact_completeness", "artifact_missing_files", "stance_source", "admitted_conflicts", "candidate_conflicts", "main_conflict")


def tree_digest(root: Path) -> dict[str, object]:
    """One sha256 over (relative path, file sha256) of every file under ``root``, plus the file count."""
    outer = hashlib.sha256()
    count = 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        outer.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        outer.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii") + b"\n")
        count += 1
    return {"files": count, "digest": outer.hexdigest()}


def alpha_levels(run_dir: Path) -> dict[str, dict[str, object]]:
    audit = json.loads((run_dir / "run_audit.json").read_text(encoding="utf-8"))
    summary = (audit.get("activation_summary") or {}).get("per_alpha") or {}
    return {alpha: {"level": entry.get("level"), "score": entry.get("score")} for alpha, entry in sorted(summary.items())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round23", required=True)
    parser.add_argument("--round24", required=True)
    parser.add_argument("--runs-root", default=str(REPO / "outputs" / "runs"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    if out.exists():
        print("refusing: output exists", out, file=sys.stderr)
        return 2
    old = json.loads(Path(args.round23).read_text(encoding="utf-8"))["tickers"]
    new = json.loads(Path(args.round24).read_text(encoding="utf-8"))["tickers"]
    runs_root = Path(args.runs_root)
    rows, differences = {}, []
    for ticker in sorted(old):
        before, after = old[ticker], new[ticker]
        run_dir = runs_root / after["run_id"]
        levels = alpha_levels(run_dir)
        recorded = {}
        for rule in after["verdict"].get("contract_rule_results") or ():
            for rec in rule.get("alpha_recognition") or ():
                recorded[rec["alpha_id"]] = {"level": rec["activation_level"], "score": rec["activation_score"]}
            for rec in rule.get("component_alphas") or ():
                recorded[rec["alpha_id"]] = {"level": rec["activation_level"], "score": rec["activation_score"]}
        field_diff = {f: {"round23": before.get(f), "round24": after.get(f)} for f in RESEARCH_FIELDS if before.get(f) != after.get(f)}
        level_diff = {a: {"saved_run": levels.get(a), "recorded_by_round24": r} for a, r in recorded.items() if levels.get(a) != r}
        rows[ticker] = {
            "run_id": after["run_id"],
            "research_fields_equal": not field_diff,
            "alpha_facts_recorded_by_round24": recorded,
            "alpha_facts_equal_the_saved_runs_own": not level_diff,
            "run_directory": tree_digest(run_dir),
            "formal_status": {"round23": before["verdict"]["formal_status"], "round24": after["verdict"]["formal_status"]},
        }
        if field_diff:
            differences.append({"ticker": ticker, "research_field_differences": field_diff})
        if level_diff:
            differences.append({"ticker": ticker, "alpha_fact_differences": level_diff})
    document = {
        "what": "research facts read from the six saved runs: Round 23 entry vs Round 24 entry, and the Alpha facts of Round 24 vs the run's own run_audit.json",
        "tickers": rows,
        "differences": differences,
        "research_unchanged": not differences,
    }
    out.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"research_unchanged": document["research_unchanged"], "differences": len(differences)}))
    return 0 if document["research_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
