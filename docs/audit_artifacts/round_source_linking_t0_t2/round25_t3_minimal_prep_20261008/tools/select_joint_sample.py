#!/usr/bin/env python3
"""Round 25 (T3 prep), deliverable 4: select and freeze the NEW 40-item joint sample (John's quota 16 A304 boundary / 8 A101-A103 /
4 each A001 A003 A102 A501) and write the reviewer package.

Selection is mechanical and blind to the model under evaluation:
  * candidates come from the three root research runs that carry a source registry (scan_joint_pool.RUNS); alpha_matches.json and
    evidence_stance_audit.json are never opened while selecting;
  * a claim is a candidate for a cell when the cell's scenario rule matches the CLAIM text (scan_joint_pool.SCENARIOS);
  * within a cell, order = sha256("t3v3|" + claim_id); claims whose linked source carries real content (excerpt or data row) come first
    (full five-link chain); key-conclusion claims (production rule evidence_trace.key_conclusion_group, which reads only the agent, the report
    section and the claim's own wording) are taken first among those; A304 candidates are then spread round-robin over the text cues of John's
    situations; text-only claims (no saved source content) fill a cell only when content-linked ones run out, and are marked PARTIAL_CHAIN;
  * duplicates (same normalized text or same duplicate_group_id) are skipped.
The "real use" of each claim in its saved run (conflict raw pool / official Alpha pool) is attached AFTER selection, kept in the manifest only,
and never shown to the reviewer (it reveals the system's Alpha answer).

    python select_joint_sample.py --out-dir <new dir>
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from scan_joint_pool import A304_CUES, RUNS, SCENARIOS, content_of  # noqa: E402

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy  # noqa: E402
from comqutor_alpha.api.evidence_trace import key_conclusion_group  # noqa: E402

QUOTA = {"A304_boundary": 16, "A101_A103": 8, "A001": 4, "A003": 4, "A102": 4, "A501": 4}
SALT = "t3v3|"
# the final execution of the c904d4cc lineage (zero-model-call re-evaluations of the same claims); used only for the post-selection "real use" note
FINAL_EXECUTION = {"c904d4cc-dc09-495c-aec5-b056979948e1": "dependency-20261007T220450Z-33128621"}
CUE_ORDER = ("refute", "conditional", "citation", "data", "none")
# the reviewer's answer sets; R1_source_relation and R3_direction use the production vocabularies so they can be compared one-to-one
JUDGMENT_VOCABULARY = {
    "R1_claim_fidelity": ["FAITHFUL", "MINOR_DEVIATION", "MATERIAL_DEVIATION", "NOT_IN_SOURCE", "UNABLE_TO_JUDGE"],
    "R1_source_relation": ["SUPPORTS", "CONDITIONAL", "BACKGROUND", "CITATION_ONLY", "OPPOSES", "INSUFFICIENT", "UNABLE_TO_JUDGE"],
    "R2_alpha": [*sorted(load_alpha_taxonomy()), "NONE", "UNABLE_TO_JUDGE"],
    "R3_direction": ["supports_alpha", "opposes_alpha", "mentions_alpha", "neutral_background", "supports_counter_alpha", "NOT_APPLICABLE", "UNABLE_TO_JUDGE"],
    "R4_evidence_eligibility": ["QUALIFIES", "DOES_NOT_QUALIFY", "UNABLE_TO_JUDGE"],
}


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9.$%]+", norm(text)))


def figures(text: str) -> frozenset[str]:
    return frozenset(re.sub(r"[,$%]", "", f) for f in re.findall(r"\d[\d,]*\.?\d*", text or "") if len(re.sub(r"\D", "", f)) >= 2)


def order_key(claim_id: str) -> str:
    return hashlib.sha256((SALT + claim_id).encode("utf-8")).hexdigest()


def load_run(run_id: str) -> dict:
    run_dir = REPO / "outputs" / "runs" / run_id
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    records = json.loads((run_dir / "structured_agent_outputs.json").read_text(encoding="utf-8"))["records"]
    sources = {s["source_id"]: s for s in json.loads((run_dir / "source_registry.json").read_text(encoding="utf-8"))["sources"]}
    by_output: dict[str, list] = {}
    for r in records:
        by_output.setdefault(r.get("source_agent_output_id") or "", []).append(r)
    for rows in by_output.values():
        rows.sort(key=lambda r: r.get("claim_index") or 0)
    return {"metadata": metadata, "records": records, "sources": sources, "by_output": by_output}


def context(run: dict, record: dict, width: int = 2) -> dict:
    rows = run["by_output"].get(record.get("source_agent_output_id") or "", [])
    idx = next((i for i, r in enumerate(rows) if r["claim_id"] == record["claim_id"]), None)
    if idx is None:
        return {"before": [], "after": []}
    return {
        "before": [r.get("claim") for r in rows[max(0, idx - width):idx]],
        "after": [r.get("claim") for r in rows[idx + 1: idx + 1 + width]],
    }


def relevant_rows(excerpt: str, claim: str) -> list[str]:
    """Excerpt segments that contain a figure the claim states (mechanical match; the full excerpt stays in the form JSON)."""
    if not excerpt:
        return []
    segments = [s.strip() for s in excerpt.split(" | ") if s.strip()]
    figures = {re.sub(r"[,$%]", "", f) for f in re.findall(r"\d[\d,]*\.?\d*", claim or "") if len(re.sub(r"\D", "", f)) >= 2}
    hits = [segments[0]] if segments else []
    for seg in segments[1:]:
        flat = seg.replace(",", "")
        if any(fig and fig.split(".")[0] in flat for fig in figures):
            hits.append(seg)
    return hits[:8]


def candidates() -> list[dict]:
    out = []
    for run_id in RUNS:
        run = load_run(run_id)
        for r in run["records"]:
            claim_text = r.get("claim") or ""
            cells = [name for name, rx in SCENARIOS.items() if rx.search(claim_text)]
            if not cells:
                continue
            src = run["sources"].get(r.get("linked_source_id") or "")
            kind = content_of(src) if src else None
            out.append({"run_id": run_id, "record": r, "source": src if kind else None, "content_kind": kind, "cells": cells, "run": run})
    return out


def pick(cands: list[dict], cell: str, quota: int, used_ids: set, used_texts: list, used_groups: set) -> list[dict]:
    """``used_texts`` holds (token set, linked source id, figure set) of everything already chosen, across cells: a candidate is a duplicate
    when its tokens overlap an earlier choice by >= 0.8 (Jaccard) or >= 0.6 of the shorter claim (overlap coefficient, both >= 6 tokens),
    or it cites the same source with the same figures (the same fact restated by another agent)."""
    pool = [c for c in cands if cell in c["cells"]]
    pool.sort(key=lambda c: order_key(c["record"]["claim_id"]))
    chosen: list[dict] = []

    def is_duplicate(r: dict) -> bool:
        toks, src, figs = tokens(r.get("claim")), r.get("linked_source_id"), figures(r.get("claim"))
        for other_toks, other_src, other_figs in used_texts:
            union = toks | other_toks
            if union and len(toks & other_toks) / len(union) >= 0.8:
                return True
            # one claim restating another (e.g. a risk analyst repeating a researcher's sentence): overlap coefficient >= 0.6
            smaller = min(len(toks), len(other_toks))
            if smaller >= 6 and len(toks & other_toks) / smaller >= 0.6:
                return True
            if src and src == other_src and figs and figs == other_figs:
                return True
        return False

    def take(c: dict, reason: str) -> bool:
        r = c["record"]
        g = r.get("duplicate_group_id")
        if r["claim_id"] in used_ids or (g and g in used_groups) or len(chosen) >= quota or is_duplicate(r):
            return False
        chosen.append({**c, "selection_reason": reason})
        used_ids.add(r["claim_id"])
        used_texts.append((tokens(r.get("claim")), r.get("linked_source_id"), figures(r.get("claim"))))
        if g:
            used_groups.add(g)
        return True

    full = [c for c in pool if c["content_kind"]]
    partial = [c for c in pool if not c["content_kind"]]
    for c in full:
        if key_conclusion_group(c["record"]):
            take(c, "full chain; key conclusion; hash order")
    if cell == "A304_boundary":
        buckets: dict[str, list[dict]] = {cue: [] for cue in CUE_ORDER}
        for c in full:
            text = c["record"].get("claim") or ""
            cue = next((name for name in CUE_ORDER[:-1] if A304_CUES[name].search(text)), "none")
            buckets[cue].append(c)
        while len(chosen) < quota and any(buckets.values()):
            for cue in CUE_ORDER:
                while buckets[cue]:
                    if take(buckets[cue].pop(0), f"full chain; A304 text cue '{cue}'; hash order"):
                        break
                if len(chosen) >= quota:
                    break
    for c in full:
        take(c, "full chain; hash order")
    for c in partial:
        take(c, "PARTIAL chain (no saved source content); hash order; filled only after content-linked candidates ran out")
    return chosen


def real_use(run_id: str, claim_id: str) -> dict:
    """Post-selection only: where the saved run actually used this claim. Reveals the system's Alpha answer -> manifest only."""
    execution = FINAL_EXECUTION.get(run_id, run_id)
    run_dir = REPO / "outputs" / "runs" / execution
    use = {"execution": execution, "conflict_raw_pool_alphas": [], "official_alpha_pool_alphas": []}
    conflicts = json.loads((run_dir / "conflicts.json").read_text(encoding="utf-8"))
    for ev in conflicts.get("arbitration", {}).get("candidate_evaluations") or []:
        for side in ("alpha_a", "alpha_b"):
            audit = (ev.get("evidence_audit") or {}).get(side) or {}
            if claim_id in (audit.get("qualifying_claim_ids") or []) and audit.get("alpha_id") not in use["conflict_raw_pool_alphas"]:
                use["conflict_raw_pool_alphas"].append(audit.get("alpha_id"))
    trace_path = run_dir / "evidence_trace.json"
    if trace_path.exists():
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        use["official_alpha_pool_alphas"] = [a["alpha_id"] for a in trace.get("alphas", []) if claim_id in (a.get("claim_ids") or [])]
    else:
        use["official_alpha_pool_alphas"] = "not recorded for this run (no evidence_trace.json)"
    return use


_DOC_INDEX: list[tuple[str, str, str]] = []


def exposure(claim_id: str) -> dict:
    """Where this claim id already appears under docs/audit_artifacts (other than this round): human-readable reports (.md/.csv) are listed by
    name; data copies (.json/.jsonl, e.g. run copies and ledgers) are only counted. Appearing in a report means a person may have seen what the
    system said about it -- recorded so the reviewer can attest, never used to drop or keep a sample."""
    if not _DOC_INDEX:
        for path in (REPO / "docs" / "audit_artifacts").rglob("*"):
            if not path.is_file() or "round25_t3_minimal_prep" in path.as_posix() or path.suffix not in {".md", ".json", ".csv", ".jsonl"}:
                continue
            try:
                _DOC_INDEX.append((path.relative_to(REPO).as_posix(), path.suffix, path.read_text(encoding="utf-8")))
            except (UnicodeDecodeError, OSError):
                continue
    reports = sorted(rel for rel, suffix, text in _DOC_INDEX if suffix in {".md", ".csv"} and claim_id in text)
    data = sum(1 for rel, suffix, text in _DOC_INDEX if suffix in {".json", ".jsonl"} and claim_id in text)
    return {"reports": reports, "data_files_count": data}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    out_dir = Path(args.out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        print("refusing: output directory is not empty", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    cands = candidates()
    used_ids: set = set()
    used_texts: list = []
    used_groups: set = set()
    selected, gaps = [], {}
    for cell, quota in QUOTA.items():
        chosen = pick(cands, cell, quota, used_ids, used_texts, used_groups)
        full = sum(1 for c in chosen if c["content_kind"])
        gaps[cell] = {
            "quota": quota,
            "selected": len(chosen),
            "full_chain": full,
            "partial_chain_no_source_content": len(chosen) - full,
            "content_linked_candidates_available": sum(1 for c in cands if cell in c["cells"] and c["content_kind"]),
            "text_only_candidates_available": sum(1 for c in cands if cell in c["cells"] and not c["content_kind"]),
        }
        for c in chosen:
            selected.append({**c, "cell": cell})
    manifest, form_items, csv_rows = [], [], []
    for n, c in enumerate(selected, start=1):
        r, run, src = c["record"], c["run"], c["source"]
        sid = f"t3v3-{n:03d}"
        meta = run["metadata"]
        source_block = None
        if src:
            source_block = {
                "source_id": src["source_id"], "source_type": src.get("source_type"), "title": src.get("title"), "provider": src.get("provider") or src.get("name"),
                "url": src.get("url"), "published_at": src.get("published_at"), "retrieved_at": src.get("retrieved_at"), "observation_date": src.get("observation_date"),
                "fragment_id": src.get("fragment_id"), "locator": src.get("locator"), "content_hash": src.get("content_hash"),
                "excerpt": src.get("excerpt"), "data_snapshot": src.get("data_snapshot"),
                "calculation_method": src.get("calculation_method"), "calculation_params": src.get("calculation_params"),
                "rows_with_figures_the_claim_states": relevant_rows(src.get("excerpt") or "", r.get("claim") or ""),
            }
        common = {
            "sample_id": sid, "cell": c["cell"], "ticker": r.get("ticker") or meta.get("ticker"), "analysis_date": meta.get("analysis_date"),
            "agent": r.get("agent"), "report_section": r.get("source_section"), "claim_text": r.get("claim"), "evidence_text": r.get("evidence") if r.get("evidence") != r.get("claim") else None,
            "context": context(run, r), "chain": "FULL" if src else "PARTIAL_NO_SAVED_SOURCE_CONTENT",
            "source": source_block,
            "time_facts": {
                "source_published_at": src.get("published_at") if src else None,
                "disclosure_time_known": bool(src and src.get("published_at")),
            },
        }
        manifest.append({
            **common,
            # the run's own link validation is a system output: kept here, never on the form
            "time_facts": {**common["time_facts"], "source_link_status_in_run": r.get("source_link_status")},
            "run_id": c["run_id"], "claim_id": r["claim_id"], "claim_quality_in_run": r.get("claim_quality"),
            "selection_reason": c["selection_reason"], "key_conclusion_group": key_conclusion_group(r),
            "source_link_method_in_run": r.get("source_link_method"),
            "saved_content_support_in_run": {"status": r.get("content_support_status"), "method": r.get("content_support_method"), "review": r.get("content_support_review")},
            "real_use_in_saved_run": real_use(c["run_id"], r["claim_id"]),
            "prior_mentions_in_docs": exposure(r["claim_id"]),
        })
        form_items.append({**common, "judgments": {
            "R1_claim_fidelity": None, "R1_source_relation": None, "R2_alpha": None, "R3_direction": None, "R4_evidence_eligibility": None,
            "rationale": None, "reviewer_id": None, "reviewer_role": None, "reviewed_at": None, "attests_no_prior_view_of_system_outputs": None,
        }})
        csv_rows.append({
            "sample_id": sid, "ticker": common["ticker"], "analysis_date": common["analysis_date"], "agent": common["agent"], "report_section": common["report_section"],
            "claim_text": common["claim_text"], "context_before": " || ".join(x or "" for x in common["context"]["before"]),
            "context_after": " || ".join(x or "" for x in common["context"]["after"]), "chain": common["chain"],
            "source_title": (source_block or {}).get("title"), "source_provider": (source_block or {}).get("provider"),
            "source_published_at": (source_block or {}).get("published_at"), "source_observation_date": (source_block or {}).get("observation_date"),
            "source_content": " | ".join((source_block or {}).get("rows_with_figures_the_claim_states") or []) if source_block else "NO SAVED SOURCE CONTENT -- R1 cannot be judged",
            "R1_claim_fidelity": "", "R1_source_relation": "", "R2_alpha": "", "R3_direction": "", "R4_evidence_eligibility": "",
            "rationale": "", "reviewer_id": "", "reviewer_role": "", "reviewed_at": "", "attests_no_prior_view_of_system_outputs": "",
        })
    (out_dir / "joint_sample_v3_manifest.json").write_text(json.dumps({
        "schema_version": "t3_joint_sample_v3_manifest.v1", "quota": QUOTA, "gaps": gaps, "selection_rule": __doc__, "samples": manifest,
        "note": "MANIFEST: contains run usage and saved system statuses -- never give this file to the reviewer",
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out_dir / "review_form_v3.json").write_text(json.dumps({
        "schema_version": "t3_joint_review_form_v3.v1", "system_answers": "NOT INCLUDED -- predictions are produced later and kept in a separate file",
        "instructions": "see 04_reviewer_instructions.md in the same package (Alpha definitions from the taxonomy only; no prompt rules)",
        "judgment_vocabulary": JUDGMENT_VOCABULARY,
        "items": form_items,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with (out_dir / "review_worksheet_v3.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows)
    print(json.dumps({"selected": len(selected), "gaps": gaps}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
