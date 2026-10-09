# v0.2 New Independent Alpha Holdout — Creation Plan

**Status: `NEW_INDEPENDENT_HOLDOUT_REQUIRES_ADJUDICATION`.** This is a plan only — no new holdout was created, no sample was labeled, no Provider was called in this task. Full labeled-data inventory in `v0_2_labeled_alpha_data_inventory.json`.

## Why No Untouched Labeled Pool Exists Today

| Source | Samples | Eligible as untouched? |
|---|---:|---|
| Holdout #1 | 100 | No — pre-Pure-LLM architecture, fully closed QA milestone |
| Holdout #2 | 141 | No — pre-Pure-LLM architecture, already cited this engagement |
| Holdout #3 | 152 | No — directly used to validate the decision=defer→select/none migration |
| Holdout #4 | 200 | No — `DEVELOPMENT_AFTER_FIRST_INSPECTION`, designed Candidates 1 & 2 |
| Holdout #5 | 200 | No — `DEVELOPMENT`, the original failure-analysis set |
| "old-50" (`docs/evidence_review_sample_records.json`) | 50 | No — its only Alpha field (`target_alpha_id`) is identical to the system's own historical `matched_alpha_id` for every record; this is the system grading itself, not an independent label. Its *raw, unlabeled* claim/evidence text is untouched, though, and is exactly the kind of source pool Section 6 asks for. |
| `evaluation/golden_cases/*/manual_claim_labels.csv` | 0 | No — empty templates, no actual data |

**`UNTOUCHED_SAMPLE_POOL_AVAILABLE = NO` — 0 untouched, independently-labeled samples exist.** Total labeled samples discovered across the repository: **793** (100+141+152+200+200), all from H1–H5, all already touched.

## Source Pool for a New Holdout (raw, unlabeled — not itself Gold)

- **64 real research run directories** exist under `outputs/runs/` (excluding replay/synthetic IDs) — confirmed by direct listing, not assumed.
- Holdout #4's own construction report (`item2_blind_holdout4_report.md`) already computed, at 2026-08-21, a **13,663-row genuinely unseen pool** across 8 tickers after excluding old-50/H1/H2/H3 — before H4 (200) and H5 (200) were themselves drawn from it. After also excluding H4 and H5, roughly **~13,263 rows** would remain from that same computation, **plus** claims from every run added since 2026-08-21 (at least the Day 4B Fresh NVDA (`421bca7a-...`) and Fresh QQQ (`a4dae9c5-...`) runs, and any others among the 64 total run directories not yet enumerated in that count).
- This is a real, substantial, defensible source pool for a NEW holdout — but it carries **no independent Alpha labels yet**. Per explicit instruction, the system's own output must never be used as the Gold label for grading itself.

## Plan

### A. Source Pool
All claims/evidence in `outputs/runs/<run_id>/structured_agent_outputs.json` for every run directory **not** already consumed by old-50, H1, H2, H3, H4, or H5 (exclusion by exact `claim_id` and normalized-evidence-text, mirroring every prior holdout's own construction discipline).

### B. Sampling Method
Stratified random sampling, deterministic seed frozen and recorded before any draw:
- Stratify by ticker (flat per-ticker target, as H4 did: N/ticker-count rows per ticker) and, where feasible, by canonical Alpha family (using only *structural* signals available pre-review — e.g. deterministic keyword/factor hits — never the current LLM's own decision, to avoid seeding selection bias toward what the model already gets right).
- Sample IDs frozen into a versioned CSV **before** any reviewer or Provider call, exactly as H1–H5 each did.

### C. Sample Size
Target **≥200 for a new development set** and **≥200 for the reserved final independent set** (400+ total) if the ~13,263-row pool supports it after exclusion and per-ticker quota checks (it should, based on H4's own pool-size finding). If ticker-level exhaustion forces a smaller number (as happened to SNDK/TSM in H1/H2), report the actual achievable size honestly rather than padding from an already-touched source.

### D. Frozen IDs Before Labeling
Both the development-set and final-set sample IDs (and their raw claim/evidence text) must be frozen — written to disk with a SHA256 recorded — **before** any adjudication begins, exactly as every prior holdout's own "frozen before evaluation" discipline required.

### E. Adjudication Rubric
Per-sample, an independent reviewer (human or a separate, blinded LLM reviewer session) sees **only**: `sample_id`, `ticker`, `claim`, `evidence`, and the full canonical Alpha taxonomy (id/name/thesis) — **never** the system's own `matched_alpha_id`, candidate scores, or any prior label. The reviewer answers: "Does this Evidence materially, substantively engage exactly one canonical Alpha's own thesis/mechanism? If yes, which one and at what confidence (low/medium/high)? If no single Alpha is materially engaged, answer NONE." This mirrors H1–H5's own established reviewer-blindness discipline exactly.

### F. Ambiguous Samples
A sample where the reviewer cannot confidently resolve to exactly one Alpha (genuine two-Alpha ambiguity, or a negated/rebuttal framing whose target is unclear) is recorded with an explicit `adjudication_outcome` (e.g. `BOTH_REASONABLE_AMBIGUOUS`), excluded from the accepted scoring population via the *same* general, non-hardcoded `directional_eligibility_contract`-style mechanism Holdout #5 already established for polarity — never silently forced to a single answer, never dropped without a recorded reason.

### G. Disagreement Resolution
If two independent reviewer passes are used (recommended for the reserved final set, to avoid single-annotator bias), disagreements are adjudicated by a third, independent pass that also never sees the system's own output; the majority (2-of-3) label stands, and any 1-1-1 split is recorded as `NO_MAJORITY_EXCLUDED`.

### H. Freezing Labels Before Provider Evaluation
Once adjudication is complete, the label set is written to a frozen, hashed JSON (mirroring `item2_blind_holdout{4,5}_alpha_review.json`'s own shape) **before** the current production Alpha semantic path is ever run against it. The label file's SHA256 is recorded in the same freeze manifest as the sample CSV's SHA256.

### Preferred Authority Order (per explicit instruction)
1. Pre-existing human Gold labels — **none exist** for any untouched sample today (checked and confirmed above).
2. Independent human adjudication — preferred if reviewer time is available.
3. Independent, blinded LLM adjudication process that never sees COMQUTOR's own Alpha output — the fallback this repository's own H1–H5 precedent already uses when human review isn't available, and the only Provider call this plan would ever require (a separate, review-only Provider session, distinct from and never informed by the production Alpha-classifier session).

## What This Task Did Not Do

No sample was drawn, no claim was labeled, no Provider was called, and no code/prompt was changed to produce this plan.
