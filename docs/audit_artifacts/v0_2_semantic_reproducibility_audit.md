# v0.2 Semantic Reproducibility Audit — Day 3

Read-only investigation. No Provider calls, no TradingAgents calls, no Fresh Runs. Full per-row detail (verbatim old/new prompt quotes) is in the companion `v0_2_semantic_reproducibility_audit.json`.

## Key Finding

All 43 row-level failure samples analyzed on Day 2 (and the 21 sampled into categories A/B/C) come from a **single run**, `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1` (AMD), created **2026-07-24T23:05:51Z**.

Git history shows commit **`c454245` ("test 0.1.6"), dated 2026-08-21T17:14:41-07:00 — 28 days after that run** — substantially rewrote both LLM prompts responsible for the decisions under review, in `comqutor_alpha/structure_engine/week2_llm.py`:

1. **`alpha_classifier`** (Categories A and C): went from prompt_version `v1` to `v3`. The old text allowed `decision=defer` "when the supplied admissible candidates cannot be distinguished." The new text explicitly retires deferral and adds, verbatim: *"if both A101 and A103 seem plausible, deciding decision=none because 'both are plausible' is WRONG; if A103 is the closer, more substantive fit, the required answer is decision=select with selected_alpha_id=A103."* This is the exact Category C failure pattern, named explicitly in the prompt's own worked example — not a coincidence of category naming, the literal Alpha IDs A101/A103 appear in the shipped instruction text itself.
2. **`evidence_stance_classifier`** (Category B): rewritten with substantial new guidance on multi-clause claims: *"When the Evidence contains more than one clause that materially bears on target_alpha_id's own thesis... identify every such clause -- not only the first one found -- and resolve the stance from their combined, net implication... never by selecting one clause and discarding a second, equally target-relevant one."* This directly targets both Category B sub-patterns: under-calling clear support as a mere mention, and over-calling hedged/cautious language as outright opposition.

Both prompt rewrites are dated, diffable (`git diff <parent>..c454245 -- comqutor_alpha/structure_engine/week2_llm.py`), and on-topic for the exact failure patterns Day 2 found — not a guess.

## Why "Reproducible Now" Is `False` for All 21 Cases, Despite This Evidence

The mechanism that actually produced the historical decisions under review (`_classify_alpha_with_llm` / `_classify_alpha_stance_with_llm`, both Provider-backed) cannot be invoked today — Day 3 forbids Provider calls. So while the prompt-change provenance is strong and dated, **it was not independently re-verified against these exact 21 claims this session**. Per this task's own Section 5 ("a historical failing sample may only be labeled FIXED if the current correct behavior is reproducible AND the change responsible can be identified"), that bar is not met — only the second half is. Every case is therefore classified `ALREADY_FIXED_BY_IDENTIFIED_PROMPT_CHANGE` **as a provenance finding**, not relabeled `CURRENTLY_CORRECT` or `FIXED`.

For Category B specifically, Day 2 additionally re-ran the separate, always-shadow, never-authoritative deterministic classifier (`evidence_stance.py`, which never calls a Provider and was never the mechanism that produced the reviewed output in the first place) against all 9 claims: it returns `neutral_background` for every one, not the historical `opposes_alpha`/`mentions_alpha` values. This is corroborating context, not proof of the actual fix.

## Summary

| Category | Total | Currently Correct | Currently Wrong | Fix Provenance Identified | Provenance Unresolved |
|---|---:|---:|---:|---:|---:|
| A (growth/cycle vs risk-structure) | 8 | 0 | 0 | **8** | 0 |
| B (cautious/questioning wording) | 9 | 0 | 0 | **9** | 0 |
| C (A101/A102/A103 boundary) | 4 | 0 | 0 | **4** | 0 |
| **Total** | **21** | **0** | **0** | **21** | **0** |

## Per-Case Detail (abbreviated — full quotes in the JSON)

All 21 cases share the identical classification and evidence base described above (same commit, same before/after prompt text, same run). Individual rows in `v0_2_semantic_reproducibility_audit.json` additionally carry each sample's own `historical_input`, `historical_output`, `historical_expected_output`, and (Category B only) its own Day-2 deterministic-classifier re-run result.

| Category | Sample IDs |
|---|---|
| A | holdout5-004, -056, -071, -146, -151, -154, -158, -174 |
| B | holdout5-003, -016, -017, -040, -057, -070, -154, -196, -198 |
| C | holdout5-001, -003, -057, -164 |

## What Would Close the Provenance Gap

A `FROZEN_INPUT_RECOMPUTED_WITH_NEW_CODE` validation round (see `v0_2_day4_validation_manifest.md`, Section A) that re-runs these 38 distinct historical samples' claim/evidence text through the *current* `alpha_classifier`/`evidence_stance_classifier` prompts via a live Provider call, and compares the output to the reviewer's expected label. This is explicitly a Day 4 activity, not performed today.
