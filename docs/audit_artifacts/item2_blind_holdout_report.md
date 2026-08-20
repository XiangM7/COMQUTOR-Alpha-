# QA Closure v0.1.2 — Item 2 NEW Blind Holdout Final QA

Evaluation only. No prompt tuning, no taxonomy edits, no threshold edits, no ranking edits, no hard-gate edits performed in this task. `PROVIDER_CALLS` were used only for current B1 v2 inference and the independent blind reviewer, as explicitly authorized.

## Frozen current-system state (recorded before holdout construction)

- B1 `prompt_version`: `evidence_stance.llm_classifier.v2` · classifier: `evidence_stance.llm.v1` (LLM) / `evidence_stance.deterministic.v1` (fail-soft fallback) · parser: shared `strip_markdown_json_fence`/`_strict_json_object` (`week2_llm.py`) · provider/model: anthropic / claude-sonnet-4-6
- Alpha Mapper: `DEFAULT_MIN_MATCH_SCORE=0.35`, `DEFAULT_AMBIGUITY_DELTA=0.14`, `DEFAULT_SECONDARY_DELTA=0.25`, `AI_ALPHA_IDS={A101,A102,A103}` hard gate active
- Taxonomy: `alpha_taxonomy_v1`, SHA-256 `c031168c726c...e1e7939c` (matches `FROZEN_HASHES`, confirmed unchanged)

None of these were modified during this task.

## Holdout construction

100 rows, drawn exclusively from already-persisted saved-run `alpha_matches.json` (no new research run, no TradingAgents invocation). Excluded all 50 old development rows by both exact `claim_id` and `normalize_claim_for_dedupe`-normalized evidence-text identity. Frozen **before** any B1/Alpha-Mapper/reviewer evaluation ran — `docs/audit_artifacts/item2_blind_holdout_100.csv` (SHA-256 `835d7608b1aa...d873f592`) and its manifest were both written first; neither has been touched since.

**Ticker distribution:** NVDA 17, QQQ 17, MSFT 17, SNDK 17, TSM 16, AMD 16 = 100 (exact target hit; SNDK required a second, genuinely old-50-untouched saved run to reach quota — its canonical run alone had only 5 eligible claims after exclusion).

**Alpha distribution:** A001 18, A003 3, A101 6, A102 1, A103 4, A201 6, A301 17, A304 23, A501 11, A601 11 — all 10 canonical families represented; A101+A301+A304 combined = 46/100, not a majority.

**Stratification signals used** (machine-side only, no reviewer label existed yet): `relation` (activation/invalidation/risk_relief/conditional/mixed/mention), match-score tier, `direction`, `used_in_activation`, `used_in_conflict`, evidence-fact-group duplicate-candidate size, AI-gate applicability, per-ticker Alpha soft-cap (35%).

## Current B1 v2

LLM rows: **100** · fallback rows: **0** · 10 logical batches, 10 real Provider attempts, 0 retries, 0 malformed responses.

## Current Alpha Mapper

Re-run fresh (not reused from historical persisted files) against each row's full original structured record, using today's exact `map_claim_to_alpha`. This surfaced a genuine, disclosed finding: **6 rows** (all from the SNDK secondary source run, dated 2026-07-17 — the oldest run in this holdout) had a frozen `target_alpha_id`/persisted `matched_alpha_id` of A101/A102/A103 that **predates the AI hard gate**; today's Mapper correctly marks those candidates ineligible (confirmed directly via each candidate's own `rejection_reason` field). The frozen holdout CSV's `target_alpha_id` column was **not** modified post-freeze (per this task's own rule); the alpha-match metric below uses the **fresh, current** Mapper result for all 100 rows, as required. Full detail: `alpha_mapper_stale_historical_data_sample_ids`/`_note` in the summary JSON.

## POLARITY

correct: **79** · wrong: **21** · accuracy: **79%** · target ≥80%: **FAIL**

critical support/opposition reversals: **0** *(none)*

Also reported (diagnostics, per task spec section 13): directional-vs-neutral mismatches = 15 · counter-Alpha mismatches = 1 · mention-vs-neutral mismatches = 5. John's primary metric remains exact five-class agreement (79%), not any of these sub-slices.

### Stance confusion matrix (rows = current B1, columns = independent reviewer)

| B1 \ reviewer | supports | opposes | mentions | neutral | counter |
|---|---|---|---|---|---|
| **supports_alpha** | 49 | 0 | 6 | 5 | 0 |
| **opposes_alpha** | 0 | 29 | 0 | 0 | 1 |
| **mentions_alpha** | 2 | 2 | 1 | 5 | 0 |
| **neutral_background** | 0 | 0 | 0 | 0 | 0 |
| **supports_counter_alpha** | 0 | 0 | 0 | 0 | 0 |

Zero row has `neutral_background`/`supports_counter_alpha` as B1's own prediction anywhere in this holdout — both are reviewer-only outcomes here, worth noting as a pattern, not a bug.

### Polarity accuracy by ticker

NVDA 88.2% · TSM 81.3% · MSFT 82.4% · QQQ 76.5% · SNDK 76.5% · **AMD 68.75% (weakest)**

## ALPHA MATCH

correct: **73** · wrong: **27** · accuracy: **73%** · target ≥75%: **FAIL**

wrong Alpha sample_ids: `holdout-001, 002, 005, 006, 009, 010, 011, 012, 027, 032, 033, 042, 043, 051, 052, 055, 056, 063, 064, 068, 069, 071, 077, 079, 081, 084, 086` (27 total)

### Key diagnostic (not a metric adjustment — reported as-is per task spec section 16)

Alpha-match accuracy splits sharply by AI-gate applicability: rows where the matched candidate is one of A101/A102/A103 (the AI hard gate applies) score **27.3%** (3/11); every other row scores **78.7%** (70/89) — which alone would clear the 75% target. This is the same pattern independently found in the old 50-row development set's root-cause analysis (Item 2), now confirmed on entirely unseen data: the AI hard gate is disproportionately responsible for alpha-match shortfall under this metric's literal definition, though — as established there — this reflects the gate's deliberately conservative precision/recall tradeoff (built to close a real prior false-positive problem), not an obvious new defect. **The official metric is reported unadjusted: 73/100, FAIL.**

### Alpha-match accuracy by ticker

TSM 93.75% · NVDA 88.2% · MSFT 82.4% · QQQ 64.7% · SNDK 58.8% · **AMD 50% (weakest)**

## QUALITY

too_generic: **29** · not_ticker_specific: **51** · duplicates (LLM-judged): **37** (system evidence-fact-group duplicate-candidate count, reported separately, not substituted: **6**)

## OLD DEVELOPMENT SET vs NEW BLIND HOLDOUT (never averaged/combined)

| | OLD development set (50 rows) | NEW blind holdout (100 rows) |
|---|---|---|
| B1 polarity | 45/50 = 90% | **79/100 = 79%** |
| Alpha match | 36/50 = 72% | **73/100 = 73%** |

## GENERALIZATION

Does B1 v2 maintain ≥80% on unseen data? **NO** (79%, 1 point/1 row short)
Does Alpha Mapper maintain ≥75% on unseen data? **NO** (73%, 2 points/2 rows short — though notably close to the *development* set's own 72%, unlike B1's larger 90%→79% gap)

The 90%→79% B1 gap is the more significant generalization signal here: the mixed-language prompt fix was validated only against the same 50 rows used to diagnose it, and this holdout shows real, meaningful, but incomplete generalization — genuinely better than doing nothing (79% vs. the 44% pre-fix deterministic baseline, and matching the pre-mixed-language-fix B1's own 78% development-set figure almost exactly), but not enough to clear John's bar on unseen data. Alpha Mapper's near-identical 72%→73% is a much smaller gap, consistent with it not having been tuned against the development set at all in this arc.

## Provider

anthropic / claude-sonnet-4-6 / temperature 0 (reviewer) or production default (B1, unmodified) · logical calls: 10 (B1) + 11 (reviewer, incl. 1 duplicate-clustering call) = 21 · attempts: 21 · retries: 0

## Integrity

100 source rows = 100 B1 predictions = 100 Alpha predictions = 100 independent reviews (verified programmatically, not sampled). No duplicate sample IDs, no missing IDs, no extra IDs. `item2_blind_holdout_summary.json` regenerated twice from the frozen inputs: byte-identical (SHA-256 `45f9eba0f1d7...b439658cb2dcb4994` both runs).

## Production code changes = NONE

B1 prompt changed = NO · Alpha Mapper changed = NO · taxonomy changed = NO · threshold changed = NO · AI hard gate changed = NO

## Final verdict

**POLARITY = FAIL** (79% < 80%)
**ALPHA MATCH = FAIL** (73% < 75%)

Per this task's own explicit governance (section 18): these results are reported as measured. No prompt/threshold/gate change follows from seeing them in this task. Any future fix made in response to this holdout's specific findings converts *this* 100-row set into a new development set and requires yet another fresh, untouched holdout for the next final-acceptance attempt.
