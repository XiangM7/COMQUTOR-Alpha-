# QA Closure v0.1.2 — Item 2 Blind Holdout #3 — Formal Acceptance of LLM-Primary Alpha Mapper

Pure blind acceptance evaluation. No prompt tuning, no taxonomy edits, no threshold edits, no AI-gate edits, no root-cause-driven code modification performed in this task. `PROVIDER_CALLS` were used only for (1) current production Alpha inference and (2) the independent blind Alpha reviewer, as explicitly authorized.

## 1. Frozen architecture (recorded before holdout construction, read fresh from source — not trusted from prior task reports)

- Branch `comqutor-structure-layer`, HEAD `8ecf6bfdf7fd8203e223b220be8ca244da92d1f1`, unchanged throughout.
- `alpha_mapper.py` SHA-256 `33ab39f0c76c4ceda84d96fdf57295a9abd69aa1c631d146b9fcb2707c253c1c`
- `week2_llm.py` SHA-256 `cb89e57f943e223dc45dd987c1067f78aafdf72a0ff3a61eb005fc4a8053fdc6`
- `alpha_taxonomy_v1.yaml` SHA-256 `c031168c726cd424252cd9ee0491e55f335b5966694a326e0bcdfeeab1e7939c`
- `ai_alpha_discriminator.py` SHA-256 `9d6b2c1abb968750a5dc19cae6b74afd154bde30c2fa4e78e359bed4b00efb69`
- `MAPPER_VERSION=week2.alpha_mapper.v2`, `SCHEMA_VERSION=week2.alpha_matches.v2`, `DEFAULT_MIN_MATCH_SCORE=0.35`, `DEFAULT_AMBIGUITY_DELTA=0.14`, `DEFAULT_SECONDARY_DELTA=0.25`, `AI_ALPHA_IDS={A101,A102,A103}`
- `alpha_classifier`: `prompt_version=week2.alpha_classifier.v2`, `input_schema_version=week2.alpha_classifier.input.v2`, `output_schema_version=week2.alpha_classifier.output.v1`, `taxonomy_version=alpha_taxonomy_v1`, prompt identity SHA-256 `5afa31274bf0e32cdbca60ab149dfe57f9b51110366a8d9e73e6092771c685c6`.
- Confirmed via direct source read: LLM is semantic authority over the full canonical taxonomy; deterministic scoring/AI-gate/threshold survive only as fallback + diagnostics. Matches the expected architecture — not assumed, verified.
- Production and reviewer both used `anthropic` / `claude-sonnet-4-6` (`comqutor_anthropic_medium_sonnet46_v1`).
- Full artifact: `item2_blind_holdout3_freeze_manifest.json` (includes verbatim prompt text).

## 2–3. Historical exclusion

Excluded, by exact `claim_id` AND `normalize_claim_for_dedupe`-normalized evidence text: old-50 (50 rows), Blind Holdout #1 (100 rows), Blind Holdout #2 (141 rows, using the frozen `item2_blind_holdout_141_v2.csv` as authority) — 291 total historical rows, 286 unique claim_ids, 284 unique normalized texts excluded. Holdout #3 self-deduplicated by the same normalized-text key (0 within-holdout duplicates, verified programmatically).

## 4. Source pool

Read-only inventory across **all** `outputs/runs/*/alpha_matches.json` (19 run directories, 8 tickers) — not limited to previously-used runs. Two tickers, **GOOGL and MU, had never been used in any prior holdout** and contributed a genuinely fresh pool. Post-exclusion eligible pool: AMD 35, GOOGL 96, MSFT 32, MU 32, NVDA 242, QQQ 12 = 449 available. **SNDK and TSM are now fully exhausted (0 eligible rows)** — Holdout #2 already consumed their complete available pools; both are excluded entirely, not padded or substituted. 449 available rows was comfortably sufficient for a 150-row target — `INSUFFICIENT_UNSEEN_POOL` does not apply.

## 5–6. Sample quality and representation

Quality filters (matched claims only, non-empty evidence, dedup) applied uniformly and specified before any system inference. Stratified by `relation` × match-score tier with a 35% per-Alpha soft cap, using each row's **historical, already-persisted** `matched_alpha_id` purely as an internal diversity signal — explicitly distinguished from, and never confused with, the official expected Alpha (which comes only from the independent reviewer). Current-system prediction was never inspected during sample construction (`current_system_prediction_used_for_selection: false` in the manifest) — Phase 5 (system inference) ran strictly after the freeze.

**Final N = 152.** Ticker distribution: AMD 28, GOOGL 28, MSFT 28, MU 28, NVDA 28, QQQ 12. All 10 canonical Alpha families present in the historical stratification distribution (A001:15, A003:5, A101:15, A102:4, A103:16, A201:7, A301:36, A304:22, A501:18, A601:14).

## 7. Freeze

`item2_blind_holdout3_frozen.csv` written **before** any production inference or reviewer call, containing only `sample_id, run_id, ticker, claim_id, agent, claim, evidence` — no system fields, no historical `target_alpha_id`/`matched_alpha`, no reviewer label. SHA-256 `e6c778d3bbfb65e7bf9e6a72580d499424f1371c69f2027f477faae15ab82bc6`, verified unchanged at report time (re-hashed independently, matches). No row added/removed/reordered/edited after freeze.

## 8–10. Independent reviewer — blindness and independence

Separate script, separate `create_llm_client`/model instance, no shared session/context with Phase 5. Input: `sample_id`, `ticker`, `claim`, `evidence`, full 10-Alpha taxonomy (id/name/core thesis) only — no `target_alpha_id` (the frozen CSV doesn't contain one), no system output of any kind. Reviewer prompt frozen before execution, never altered after seeing results (verbatim text in `item2_blind_holdout3_provider_audit.json`). Output: `sample_id`, `reviewer_expected_alpha_id`, `confidence`, `reason` — the official field is explicitly named `reviewer_expected_alpha_id`, never `target_alpha_id`.

## 11–12. Production inference and Provider accounting

Real production Alpha Mapper (`map_claim_to_alpha`, `classifier_enabled=True`, a real `Week2LLMGateway`/Anthropic client) run on every row — the actual LLM-primary path, never simulated. **One implementation issue caught and fixed before any result was observed**: `Week2LLMGateway` hard-clamps `max_calls` to the existing, unmodified production constant `MAX_SERVER_CALLS=100` per instance; my first script run requested `max_calls=152` on a single gateway, silently capping ~52 rows to a budget-exhausted fallback with no real LLM attempt. This was a bug in my own evaluation harness, not production code, and was caught from an internal call-count diagnostic (`logical_provider_calls: 100` ≠ `rows_total: 152`) — before any accuracy/agreement number was ever computed. Fixed by chunking into two gateway instances (100 + 52 rows), each within the unmodified ceiling, and re-run once, cleanly. This is not the "root-cause tuning after results" the task prohibits — no accuracy result existed yet when the fix was made.

- **Production**: 152 logical calls, 152 real attempts, 0 retries, 0 missing structured records, 0 timeouts/errors (all 54 non-`llm`-method rows are genuine `llm_deferred`, not technical failures).
- **Reviewer**: 16 logical calls (152 rows ÷ 10/batch), 16 attempts, 0 retries, 0 malformed batches.

Full detail: `item2_blind_holdout3_provider_audit.json`.

## 13–14. Primary metric

```
alpha_match_accuracy = 105 / 152 = 69.08%
```

**FAIL** against the ≥75.00% threshold (69.08% < 75.00%; not rounded up).

## 15–16. Secondary diagnostics and confusion matrix

- By ticker: AMD 71.4% (20/28), GOOGL 82.1% (23/28), MSFT 82.1% (23/28), **MU 32.1% (9/28) — a clear outlier**, NVDA 67.9% (19/28), QQQ 91.7% (11/12).
- System `NONE`: 10 rows, accuracy **10%** (1/10) — when the system defers to no-match, the reviewer usually still finds a fitting Alpha.
- Reviewer `NONE`: 6 rows.
- Reviewer-confidence agreement: high 74.7% (59/79), medium 62.1% (41/66), low 71.4% (5/7).
- Full 11×11 confusion matrix (10 Alphas + NONE): `item2_blind_holdout3_metrics.json`. Notable off-diagonal concentrations (descriptive only, no causal claim): `system=NONE → reviewer=A103` (6 of the 10 system-NONE rows), `system=A301 → reviewer=A103` (5), `system=A201` spread across A101/A102/A103/A601.

## 17. LLM-primary vs. deterministic-counterfactual (Section 17's key diagnostic)

| | vs. reviewer |
|---|---|
| **LLM-primary (actual system)** | **69.08%** (105/152) |
| Deterministic-only counterfactual | 61.18% (93/152) |

The LLM-primary architecture **outperforms** the deterministic counterfactual by **+7.9 points** on this genuinely unseen sample. Among the 23 rows where the LLM's final answer differed from the deterministic-only answer: **14 corrected** (deterministic wrong → LLM right), **2 worsened** (deterministic right → LLM wrong), **7 both wrong differently**, 0 "equivalent" (mathematically unreachable under exact-Top-1 comparison for a row defined by disagreement — reported as 0, not omitted). Net effect: **+12 rows**, a real, positive, unambiguous improvement from the authority migration — even though the overall result still falls short of the 75% bar.

Splitting by method: rows where the LLM committed to a selection score **84.7%** (83/98) against the reviewer; rows where the LLM deferred (falling back to deterministic) score only **40.7%** (22/54). The defer rate itself (54/152 = 35.5%) combined with deterministic's own weak standalone performance (61.2%) is the dominant arithmetic driver of the overall shortfall — not a flaw introduced by the LLM tier, which is comparatively strong when it commits.

AI-family (A101/A102/A103) accuracy: **38.5%** (15/39) — much weaker than non-AI (**83.2%**, 89/107). This is the other major, clearly visible driver of the shortfall, concentrated in a taxonomy area (AI Expansion / Inference / Infrastructure) that has been diagnostically difficult throughout this whole QA arc.

## 18. Comparison with Holdout #2 (informational only)

Holdout #2: 84/141 = 59.57%. Holdout #3: 105/152 = 69.08%. **Holdout #3 scores ~9.5 points higher, but this is explicitly not claimed as a controlled causal improvement** — the two evaluations use different, non-overlapping samples, drawn partly from different tickers (GOOGL/MU are new to Holdout #3), and Holdout #2 predates this session's Exact Semantic Replay B1 binding work and used a combined single-track reviewer for some of its fields. The only claim made here is that the CURRENT frozen architecture, tested fresh, does not clear the CURRENT ≥75% bar.

## 19. B1 diagnostic (optional, not a gate)

Not run in this task — Holdout #3's purpose is Alpha Top-1 acceptance only, per explicit instruction, and no new B1 reviewer track was created. B1 was not naturally exercised as part of this evaluation's own scripts (Phase 5 calls `map_claim_to_alpha` directly, not the full pipeline that would also invoke B1's stance upgrade), so there is nothing to report here.

## 20–21. No tuning; error categories (offline, diagnostic only)

No production code, prompt, taxonomy, threshold, or gate was modified after the primary metric was observed. Holdout #3 is now consumed development data. Read-only categorization of the 47 mismatches (152 − 105), by inspection of the confusion matrix and method/AI-family splits above, suggests two dominant diagnostic buckets: `LLM_DEFER_FALLBACK_ERROR` (defer rate is high and the deterministic fallback it lands on is weak) and `LLM_SEMANTIC_SELECTION_ERROR` concentrated in the AI-family Alphas specifically. This is descriptive, not a root-cause finding, and no adjudicator or second LLM was used to rewrite reviewer labels.

## 22. Artifacts

`item2_blind_holdout3_freeze_manifest.json`, `item2_blind_holdout3_freeze_manifest_sampling.json`, `item2_blind_holdout3_frozen.csv`, `item2_blind_holdout3_sampling_metadata.json`, `item2_blind_holdout3_system_alpha.json`, `item2_blind_holdout3_alpha_review.json`, `item2_blind_holdout3_comparison.csv`, `item2_blind_holdout3_metrics.json`, `item2_blind_holdout3_provider_audit.json`, `item2_blind_holdout3_report.md` (this file). Holdout #1/#2 artifacts untouched.

## 23. Integrity

All four production source SHA-256 values, HEAD, and the frozen holdout SHA-256 confirmed byte-identical at report time to their values at freeze time (re-hashed independently, not merely re-read from the manifest). `git status`/`git diff --stat` show zero new production-file changes from this task — every modified file predates this task (Alpha Mapper Authority Migration, Post-Migration Registry Cleanup, Exact Semantic Replay B1 Binding Support, earlier B1 work), preserved exactly as found.

## Final verdict

**ALPHA MAPPER ACCEPTANCE: FAIL**
- 105/152
- 69.08%
- threshold ≥75%

Holdout #3 is now consumed development data. No production change was made in this task. The LLM-primary architecture measurably outperformed the deterministic-only counterfactual on this same data (69.08% vs. 61.18%, net +12 corrected rows) — the migration direction is validated — but overall accuracy does not clear the formal ≥75% acceptance bar. Any future fix (e.g., addressing the high defer rate, the weak deterministic fallback it lands on, or AI-family-specific semantic selection) requires a genuinely new Blind Holdout #4 before re-acceptance can be claimed. This report does not claim final QA closure of any other, unrelated item.
