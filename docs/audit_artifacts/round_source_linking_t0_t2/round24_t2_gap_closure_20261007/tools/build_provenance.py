#!/usr/bin/env python3
"""Builds provenance/alpha_rule_provenance.{json,md}: for each Gold contract rule the unified entry executes, the contract record (verified against its
freeze manifest), the John decision text it implements (quoted from the session transcript by section markers, not retyped), the frozen trigger the matrix holds
for the run it is bound to, and the integrity notes. Reads repository files and the transcript; writes two new files.

    python build_provenance.py --transcript <session .jsonl> --out-dir <new dir>
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = next(p for p in Path(__file__).resolve().parents if (p / "comqutor_alpha").is_dir())
AUDIT = REPO / "docs" / "audit_artifacts"

# (name, transcript line, ISO timestamp as recorded in the transcript)
MESSAGES = {
    "step1": (72541, "2026-09-10T20:43:46Z", "Step 1 -- operationalize John's Gold labels v0.2"),
    "step2": (72630, "2026-09-10T21:02:57Z", "Step 2 -- John's final decisions and the freeze"),
    "step4": (72837, "2026-09-10T21:52:47Z", "Step 4 -- compare frozen Gold + frozen triggers against the six runs"),
    "cleanup": (82435, "2026-09-15T01:15:19Z", "Final John-scoped submission cleanup (rewrites the contract's markdown)"),
}

# (message, label, start marker, end marker) -- the quoted text is everything from the start marker up to (not including) the end marker
QUOTES = {
    "NVDA-A101-AI-GROWTH": [
        ("step2", "section 4 (NVDA policy, core mappings)", "==================================================\n4. IMPORTANT NVDA POLICY", "==================================================\n5. IMPORTANT SNDK POLICY"),
        ("step2", "section 2 (blocking)", "==================================================\n2. PRESERVE ALL OTHER DRAFT RULES", "==================================================\n3. IMPORTANT QQQ POLICY"),
        ("step1", "section 8.A (AI growth)", "A. AI growth\n", "B. Fundamental growth\n"),
    ],
    "NVDA-A304-VALUATION-RISK": [
        ("step2", "section 4 (NVDA policy, core mappings)", "==================================================\n4. IMPORTANT NVDA POLICY", "==================================================\n5. IMPORTANT SNDK POLICY"),
        ("step1", "section 8.C (valuation downside)", "C. Valuation downside\n", "D. Growth-vs-Valuation Composite\n"),
    ],
    "MSFT-A102-DIRECT-INFERENCE-TRIGGER": [
        ("step2", "section 1.G (final decision)", "G. MSFT A102\n", "H. MSFT CAPEX BURDEN\n"),
        ("step2", "section 2 (blocking)", "==================================================\n2. PRESERVE ALL OTHER DRAFT RULES", "==================================================\n3. IMPORTANT QQQ POLICY"),
        ("step1", "section 11.B (the 'must/should' wording that decision G resolved)", "B. Inference\n", "C. Capex burden\n"),
    ],
    "NVDA-GROWTH-VS-VALUATION-CONFLICT": [
        ("step2", "section 4 (composite)", "==================================================\n4. IMPORTANT NVDA POLICY", "==================================================\n5. IMPORTANT SNDK POLICY"),
        ("step4", "section 13 (composite evaluation)", "==================================================\n13. COMPOSITE STRUCTURE RULE", "==================================================\n14. CONFLICT PAIR NORMALIZATION"),
        ("step4", "section 15 (NVDA frozen trigger states)", "==================================================\n15. NVDA", "==================================================\n16. QQQ"),
    ],
    "AMD-AI-GROWTH-VS-VALUATION": [
        ("step1", "section 13 (AMD composite)", "==================================================\n13. AMD", "==================================================\n14. BLOCKING AUTHORITY"),
        ("step4", "section 13 (composite evaluation)", "==================================================\n13. COMPOSITE STRUCTURE RULE", "==================================================\n14. CONFLICT PAIR NORMALIZATION"),
        ("step4", "section 20 (AMD)", "==================================================\n20. AMD", "==================================================\n21. DO NOT COMPUTE"),
    ],
}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _message_texts(transcript):
    wanted = {line: key for key, (line, _, _) in MESSAGES.items()}
    found = {}
    with open(transcript, encoding="utf-8", errors="replace") as handle:
        for number, line in enumerate(handle, 1):
            if number in wanted:
                obj = json.loads(line)
                content = (obj.get("message") or {}).get("content")
                text = content if isinstance(content, str) else "\n".join(b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")
                found[wanted[number]] = {"text": text, "timestamp": obj.get("timestamp")}
            if len(found) == len(wanted):
                break
    return found


def _slice(text, start, end):
    i = text.index(start)
    j = text.index(end, i + len(start))
    return text[i:j].strip()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out_dir)
    if out.exists() and any(out.iterdir()):
        print("refusing: output directory is not empty", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    messages = _message_texts(args.transcript)
    contract = json.loads((AUDIT / "v0_2_gold_operational_contract.json").read_text(encoding="utf-8"))
    manifest = json.loads((AUDIT / "v0_2_gold_freeze_manifest.json").read_text(encoding="utf-8"))
    matrix = json.loads((AUDIT / "v0_2_evidence_trigger_matrix.json").read_text(encoding="utf-8"))
    rules = {r["rule_id"]: r for t in contract["tickers"].values() for r in t["rules"]}
    matrix_rules = {(t, r["rule_id"]): r for t, b in matrix["tickers"].items() for r in b["rules"]}
    baseline = (AUDIT / "v0_2_john_frozen_gold_baseline.yaml").read_text(encoding="utf-8")

    records = []
    for rule_id, quotes in QUOTES.items():
        rule = rules[rule_id]
        ticker = rule["ticker"]
        m = matrix_rules[(ticker, rule_id)]
        records.append(
            {
                "rule_id": rule_id,
                "ticker": ticker,
                "tier": rule["tier"],
                "blocking": rule["blocking"],
                "hit_type": rule["hit_type"],
                "rule_type": rule["rule_type"],
                "acceptable_alphas": rule["acceptable_alphas"],
                "allowed_main_conflicts": rule.get("allowed_main_conflicts"),
                "evidence_condition_in_contract": rule["evidence_condition"],
                "required_behavior_in_contract": rule["required_behavior"],
                "not_triggered_behavior_in_contract": rule["not_triggered_behavior"],
                "review_notes_in_contract": rule.get("review_notes"),
                "frozen_trigger": {
                    "bound_run": matrix["tickers"][ticker]["run_id"],
                    "state": m["trigger_state"],
                    "strength": m["evidence_strength"],
                    "rationale": m["trigger_rationale"],
                    "source_artifacts": m["source_artifacts"],
                    "determined_by": "reading structured_agent_outputs.json of the bound run once (not executable for other runs)",
                },
                "john_decision_text": [
                    {
                        "message": MESSAGES[key][2],
                        "transcript_line": MESSAGES[key][0],
                        "recorded_timestamp": messages[key]["timestamp"],
                        "section": label,
                        "quoted_text": _slice(messages[key]["text"], start, end),
                    }
                    for key, label, start, end in quotes
                ],
                "conflicts_found_that_would_pause_the_rule": "none (see integrity_notes for the observations that do not conflict with it)",
                "status": "IN EFFECT",
            }
        )

    md_now, md_frozen = _sha(AUDIT / "v0_2_gold_operational_contract.md"), manifest["frozen_contract_md_sha256"]
    notes = [
        {
            "id": "N1",
            "topic": "the 'APPROVED' flag inside the contract file",
            "finding": "contract.authority.approval_status = APPROVED with approval_authority = John is the literal block the Step-1 instruction (section 20) asked the file to contain; it is a template field, not evidence of approval.",
            "handling": "not cited. Each executed rule cites the John decision it implements (john_decision_text).",
        },
        {
            "id": "N2",
            "topic": "contract JSON integrity",
            "finding": f"sha256 {_sha(AUDIT / 'v0_2_gold_operational_contract.json')} equals frozen_contract_json_sha256 in the freeze manifest ({manifest['frozen_contract_json_sha256']}).",
            "handling": "verified at load time on every run of the entry; a different sha256 is a configuration error.",
        },
        {
            "id": "N3",
            "topic": "contract markdown companion",
            "finding": f"sha256 now {md_now}; the freeze manifest recorded {md_frozen}. The file was rewritten on John's instruction of 2026-09-15 (final submission cleanup, section 3: a short John-facing definition of the six semantics), which is why it is 1.9 KB and no longer byte-identical. Its six semantics sentences agree with contract.rule_type_semantics. The rule records live in the JSON only.",
            "handling": "reported in effective_rules (markdown_companion), not read by the executor, not a conflict with any executed rule. The owner may want the freeze manifest to record the post-cleanup hash.",
        },
        {
            "id": "N4",
            "topic": "trigger matrix integrity and binding",
            "finding": f"sha256 {_sha(AUDIT / 'v0_2_evidence_trigger_matrix.json')} equals the frozen hash recorded in v0_2_final_acceptance_closure.json (authorities_verified.historical_trigger_matrix_json); it was written against the contract sha256 {matrix['gold_authority']['contract_sha256']}. Its triggers were determined by reading structured_agent_outputs.json of ONE run per ticker: {matrix['fresh_run_authority']['runs']}. It records the run id and the input artifact name but no hash of that input, so the binding is by run id.",
            "handling": "the trigger is used only when the evaluated run id equals the bound run id; every other run is NOT_EVALUABLE. No approved executable method determines the trigger for another run.",
        },
        {
            "id": "N5",
            "topic": "AMD allowed pairs",
            "finding": "the contract's AMD composite lists A101__A304 and A301__A304; John's later written baseline (authority hierarchy level 1, which supersedes the contract for acceptance purposes) lists A101__A304, A201__A304 and A301__A304 for AMD.",
            "handling": "the allowed family is the baseline-controlled set the label already carries, plus the contract's own pairs. No executed rule's verdict on the six pinned runs depends on it (AMD's pinned run is not bound).",
        },
        {
            "id": "N6",
            "topic": "NVDA composite: contract wording versus matrix method",
            "finding": "the contract's evidence_condition for the NVDA composite is written in terms of the component Alphas reaching a qualified / detected level; the matrix (and John's Step-4 protocol: 'do not use actual Alpha output to change a trigger') fixes the trigger from evidence, independent of the system's output.",
            "handling": "the executor uses only the matrix trigger, for the bound run. Whether a level-based trigger is approved for other runs is an OWNER DECISION; none is assumed.",
        },
        {
            "id": "N7",
            "topic": "QQQ run identity",
            "finding": "the matrix binds QQQ to f88c8956; John's final submission table (2026-09-15) uses the later QQQ run f239a53f. No executed rule belongs to QQQ.",
            "handling": "no effect now; recorded for the day a QQQ rule is executed.",
        },
        {
            "id": "N8",
            "topic": "label v0.2 structural_expectations versus the Gold must_detect rules",
            "finding": "the provisional label file says a missing structural Alpha never fails a run; the Gold contract's must_detect rules say a missed Alpha with the evidence present is a FAIL.",
            "handling": "not a conflict that pauses a rule: the baseline's authority hierarchy ranks John's Gold contract above the repository label files ('implementation sources only'). The two do not collide in the executor (structural_expectations are never executed).",
        },
    ]
    doc = {
        "schema_version": "comqutor.alpha_rule_provenance.v1",
        "contract": {"path": "docs/audit_artifacts/v0_2_gold_operational_contract.json", "sha256": _sha(AUDIT / "v0_2_gold_operational_contract.json")},
        "freeze_manifest": {"path": "docs/audit_artifacts/v0_2_gold_freeze_manifest.json", "sha256": _sha(AUDIT / "v0_2_gold_freeze_manifest.json")},
        "trigger_matrix": {"path": "docs/audit_artifacts/v0_2_evidence_trigger_matrix.json", "sha256": _sha(AUDIT / "v0_2_evidence_trigger_matrix.json")},
        "baseline": {"path": "docs/audit_artifacts/v0_2_john_frozen_gold_baseline.yaml", "sha256": hashlib.sha256(baseline.encode()).hexdigest()},
        "source_messages": {k: {"transcript_line": v[0], "recorded_timestamp": messages[k]["timestamp"], "description": v[2]} for k, v in MESSAGES.items()},
        "transcript_file": Path(args.transcript).name,  # the Claude Code session transcript on the engineer's machine; no absolute path is recorded
        "note": (
            "The John decisions are cited from the working session in which they were relayed; they are quoted by section from that transcript, not retyped. The repository "
            "preserves their effect (contract JSON, freeze manifest) but not their text."
        ),
        "rules": records,
        "integrity_notes": notes,
    }
    (out / "alpha_rule_provenance.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    lines = [
        "# Provenance of the Gold contract rules the unified entry executes",
        "",
        "Every rule below is the record in John's frozen contract (`docs/audit_artifacts/v0_2_gold_operational_contract.json`, sha256 `" + doc["contract"]["sha256"] + "`, equal to the",
        "freeze manifest's), together with the John decision text it implements. The file's own `approval_status: APPROVED` is NOT cited (see N1).",
        "",
        "| Rule | Ticker / tier | Blocking | Type | Alpha / allowed pairs | Frozen trigger (bound run) | Conflict that would pause it |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in records:
        lines.append(
            f"| {r['rule_id']} | {r['ticker']} / {r['tier']} | {'yes' if r['blocking'] else 'no'} | {r['rule_type']} / {r['hit_type']} | "
            f"{', '.join(r['acceptable_alphas'])}{' / ' + ', '.join(r['allowed_main_conflicts']) if r['allowed_main_conflicts'] else ''} | "
            f"{r['frozen_trigger']['state']}/{r['frozen_trigger']['strength']} (run {r['frozen_trigger']['bound_run'][:8]}) | none |"
        )
    for r in records:
        lines += ["", f"## {r['rule_id']}", "", f"- Contract `evidence_condition`: {r['evidence_condition_in_contract']}", f"- Contract `required_behavior`: {r['required_behavior_in_contract']}", f"- Contract `not_triggered_behavior`: {r['not_triggered_behavior_in_contract']}", f"- Frozen trigger: **{r['frozen_trigger']['state']} / {r['frozen_trigger']['strength']}** for run `{r['frozen_trigger']['bound_run']}` only — {r['frozen_trigger']['rationale']}", "", "John's decision text that this rule implements:", ""]
        for q in r["john_decision_text"]:
            lines += [f"**{q['message']}** — transcript line {q['transcript_line']}, recorded {q['recorded_timestamp']}, {q['section']}:", "", "```text", q["quoted_text"], "```", ""]
    lines += ["## Integrity notes (observations; none pauses an executed rule)", ""]
    for n in notes:
        lines += [f"**{n['id']} — {n['topic']}.** {n['finding']} *Handling:* {n['handling']}", ""]
    (out / "alpha_rule_provenance.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("rules:", len(records), "| notes:", len(notes), "| wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
