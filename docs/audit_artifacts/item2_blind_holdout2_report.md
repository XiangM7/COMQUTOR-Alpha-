# QA Closure v0.1.2 — Item 2 Blind Holdout #2 — Acceptance Evaluation of Frozen B1 Evidence Stance v3

Pure evaluation. No prompt tuning, no taxonomy edits, no threshold edits, no ranking edits, no hard-gate edits performed in this task. `PROVIDER_CALLS` were used only for (1) current B1 v3 inference and (2) the two independent blind reviewer tracks, as explicitly authorized. No root-cause-driven production fix was attempted in this task, per its own explicit instruction.

## 1–2. Scope and frozen current-system state (recorded BEFORE holdout construction)

Full detail in `item2_b1_v3_freeze_manifest.json`.

- Branch `comqutor-structure-layer`, HEAD `8ecf6bfd`, evaluated with production code changes disallowed for the duration of this task (verified clean at time of writing this report — see §19).
- B1 `prompt_version`: **`evidence_stance.llm_classifier.v3`** (the ontology-corrected version, already manually approved for freeze prior to this task) · classifier: `evidence_stance.llm.v1` (LLM) / `evidence_stance.deterministic.v1` (fail-soft fallback) · parser: shared `strip_markdown_json_fence`/`_strict_json_object` (`week2_llm.py`) · provider/model: anthropic / claude-sonnet-4-6.
- `week2_llm.py` SHA-256 at freeze: `bf2f641c952c0128a06e13f969e7bdc805a5be3ae661636727ddb06af8facbd7`. Re-hashed at report-writing time (§19): **identical** — zero drift across the whole evaluation.
- Alpha Mapper: `DEFAULT_MIN_MATCH_SCORE=0.35`, `DEFAULT_AMBIGUITY_DELTA=0.14`, `DEFAULT_SECONDARY_DELTA=0.25`, `AI_ALPHA_IDS={A101,A102,A103}` hard gate active. Untouched throughout this entire B1 v2/v3 arc, not only this task.
- Taxonomy: `alpha_taxonomy_v1.yaml`, untouched.

## 3–5. Holdout #2 construction, exclusion, and freeze

141 rows (target 150; six tickers' genuinely-eligible post-exclusion pools did not stretch further without lowering quality — see manifest `pool_sizes_after_exclusion_and_dedup`), drawn exclusively from already-persisted saved-run `alpha_matches.json`/`structured_agent_outputs.json` (no new research run, no TradingAgents invocation). Excluded by **both** exact `claim_id` and `normalize_claim_for_dedupe`-normalized evidence-text identity against **both** the old 50-row development set and Blind Holdout #1 (100 rows) — **145** claim_ids and **143** normalized texts excluded in total, plus within-Holdout-#2 self-deduplication. Frozen **before** any B1/Alpha-Mapper/reviewer evaluation ran: `item2_blind_holdout_141_v2.csv`, SHA-256 **`5c11f7f6637153dd9178e025dd7e791148a37cb8c9164f69534a397bd65b5870`**, verified present and matching in the manifest before Phase 3 began. Neither the CSV nor the manifest has been touched since.

**Ticker distribution:** AMD 25, MSFT 25, NVDA 25, QQQ 25, SNDK 19, TSM 22 = 141 (SNDK/TSM capped by genuine post-exclusion pool size — 19 and 22 respectively — not padded from elsewhere).

**Alpha distribution:** A001 12, A003 5, A101 8, A102 2, A103 17, A201 13, A301 17, A304 38, A501 12, A601 17 — all 10 canonical families represented.

**Stratification signals used** (machine-side only; no reviewer label existed yet, `reviewer_labels_used_for_selection: false`): `relation`, match-score tier, `direction`, `used_in_activation`, `used_in_conflict`, duplicate-group size, AI-gate applicability, per-ticker Alpha soft-cap (35%).

## 6. Frozen-file contents

The frozen CSV contains only ticker/claim/evidence/target_alpha_id and machine-derived `system_*` diagnostic columns captured at holdout-build time — no reviewer answers, no post-hoc system re-evaluation. All evaluation outputs (Phases 3–7) were written to **separate** files, never back into the frozen CSV.

## 7. Two separate, independent review tracks (architectural requirement of this task)

Unlike Holdout #1 (one combined stance+alpha+quality call per row), this evaluation used **two structurally separate Provider call sequences**:

- **Phase 4 — stance reviewer** (`run_item2_blind_holdout2_stance_review.py`): shown `sample_id`/`ticker`/`claim`/`evidence`/`target_alpha_id` + its name and definition + its legal canonical counter-Alphas. **Never** shown `current_b1_stance`, stance method, fallback reason, confidence, B2/conflict results, or any prior label.
- **Phase 6 — Alpha reviewer** (`run_item2_blind_holdout2_alpha_review.py`): shown `sample_id`/`ticker`/`claim`/`evidence` and the **full 10-Alpha taxonomy** only. **Never** shown `target_alpha_id`, `matched_alpha_id`, candidate ranking/scores, threshold/gate result, or any stance-track output — eliminating any risk of the independent Alpha Top-1 pick being anchored by the target the stance question used.

## 8. Reviewer blindness / protocol

`review_source: "independent_llm_provisional"` throughout · `human_review_performed: false` — this is an LLM-provisional review, not human gold, consistent with this arc's standing, explicitly user-authorized substitution policy. Reviewer prompts were frozen (written once, not iterated after seeing outputs) before either Phase 4 or Phase 6 ran.

## 9. Phase execution log

| Phase | Script | Result |
|---|---|---|
| 1 | freeze manifest | `item2_b1_v3_freeze_manifest.json` written, hash recorded |
| 2 | `build_item2_blind_holdout2.py` | 141 rows frozen, hash verified before Phase 3 |
| 3 | `run_item2_blind_holdout2_b1.py` | 15 logical calls, 15 attempts, 0 retries, 141/141 real LLM, 0 fallback |
| 4 | `run_item2_blind_holdout2_stance_review.py` | 15 logical calls, 15 attempts, 0 retries |
| 5 | `run_item2_blind_holdout2_alpha_mapper.py` | 141/141 rows, deterministic, offline |
| 6 | `run_item2_blind_holdout2_alpha_review.py` | 16 logical calls (15 batches + 1 duplicate-clustering), 16 attempts, 0 retries |
| 7 | `build_item2_blind_holdout2_summary.py` | join + metrics, deterministic, offline |

Total Provider activity across the whole evaluation: **46 logical calls, 46 real attempts, 0 retries, 0 malformed-batch rejections** anywhere in the sequence.

## 10. PRIMARY METRICS

### Polarity accuracy (exact 5-class agreement)

correct: **123** · wrong: **18** · accuracy: **87.23%** (123/141) · target ≥80%: **PASS**

### Alpha match accuracy (exact Top-1, vs independent reviewer's `llm_expected_alpha_id`, NOT `target_alpha_id`)

correct: **84** · wrong: **57** · accuracy: **59.57%** (84/141) · target ≥75%: **FAIL**

## 11. SECONDARY METRICS

**Critical support/opposition reversals: 0** (none) — rate 0.0%.

Also reported (diagnostics, not the primary metric): directional-vs-neutral mismatches = 12 · counter-Alpha mismatches = 1 · mention-vs-neutral mismatches = 5.

### Stance confusion matrix (rows = current B1 v3, columns = independent stance reviewer)

| B1 v3 \\ reviewer | supports | opposes | mentions | neutral | counter |
|---|---|---|---|---|---|
| **supports_alpha** | 67 | 0 | 3 | 1 | 0 |
| **opposes_alpha** | 0 | 32 | 1 | 0 | 1 |
| **mentions_alpha** | 2 | 4 | 18 | 0 | 0 |
| **neutral_background** | 0 | 1 | 5 | 5 | 0 |
| **supports_counter_alpha** | 0 | 0 | 0 | 0 | 1 |

### Polarity accuracy by ticker

AMD 96% · NVDA 96% · SNDK 89.5% · QQQ 84% · MSFT 80% · **TSM 77.3% (weakest)**

### Polarity accuracy by target Alpha

A501 100% · A102 100% · A103 94.1% · A304 92.1% · A601 88.2% · A101 87.5% · A001 83.3% · A201 76.9% · A301 76.5% · **A003 60% (weakest, n=5)**

### Alpha-match accuracy by ticker

QQQ 76% · MSFT 64% · NVDA 64% · TSM 59.1% · AMD 52% · **SNDK 36.8% (weakest)**

### Alpha-match accuracy by system-matched Alpha

A304 94.7% · A501 83.3% · A001 75% · A103 62.5% · A201 53.8% · A301 52.6% · A601 35.3% · A003 20% · **A101 0% (n=5) · NONE 0% (n=12, i.e. every row the system left unmatched disagreed with the reviewer's own pick)**

### Alpha-match accuracy by AI-gate applicability (diagnostic; not a metric adjustment)

AI-gate-applicable (system-matched candidate is A101/A102/A103): **18.5%** (5/27)
Not AI-gate-applicable: **69.3%** (79/114)

This is a **descriptive observation only** — this task's own governance (§13–14) forbids root-cause conclusions or production changes here, and the Alpha Mapper / AI hard gate were not touched anywhere in this arc (verified clean, §19). It is reported because it mirrors the same pattern already documented in the Item 2 development-set and Holdout #1 root-cause analyses, now visible again on entirely new, unseen data.

## 12. Quality diagnostics (do not alter the frozen primary result)

too_generic: **44** · not_ticker_specific: **56** · duplicates (LLM-judged, second separate clustering call): **39** · system evidence-fact-group duplicate-candidate count (reported separately, not substituted): **3**

## 13. No post-hoc tuning

This is the first and only complete run of Phases 3–7 against this frozen holdout. No row was relabeled, resampled, or rerun after seeing results. No production file changed between Phase 1's freeze-hash and this report (verified, §19).

## 14. Result interpretation

**Polarity: PASS. Alpha match: FAIL.** This is the outcome where B1 v3's own metric clears its bar on genuinely unseen data while the (unchanged) Alpha Mapper's metric does not — and must **not** be read as "B1 v3 caused an Alpha-match regression." The Alpha Mapper and AI hard gate are byte-identical to Holdout #1's evaluation (confirmed via git diff, §19); nothing about how `matched_alpha_id` is produced changed between the two holdouts. What changed is the **sample**: Holdout #2's target distribution concentrates more heavily on the AI-gated families (A101 8 + A102 2 + A103 17 = 27/141 = 19.1% of targets, vs. Holdout #1's 11/100 = 11%), and, independently, the accuracy *within* both the gate-applicable and non-gate-applicable subsets is lower here than in Holdout #1 (18.5% vs. 27.3%, and 69.3% vs. 78.7%, respectively). Both of those facts are stated descriptively; this task's scope does not extend to diagnosing which one dominates, or why the non-gate subset also declined — that would require a dedicated root-cause task against this specific holdout, exactly as was done after Holdout #1.

## 15. Required artifacts (11)

1. `item2_b1_v3_freeze_manifest.json`
2. `item2_blind_holdout_141_v2.csv`
3. `item2_blind_holdout_141_v2_manifest.json`
4. `item2_blind_holdout2_system_stance.csv`
5. `item2_blind_holdout2_independent_stance_review.csv`
6. `item2_blind_holdout2_system_alpha.csv`
7. `item2_blind_holdout2_independent_alpha_review.csv`
8. `item2_blind_holdout2_comparison.csv`
9. `item2_blind_holdout2_summary.json`
10. `item2_blind_holdout2_provider_call_log.json`
11. `item2_blind_holdout2_report.md` (this file)

## 16. Summary JSON schema

`item2_blind_holdout2_summary.json` follows the same schema as Holdout #1's `item2_blind_holdout_summary.json` (sample/correct/wrong counts, accuracies, target/target_met booleans, confusion matrices, per-ticker/per-Alpha/per-relation/per-AI-gate rate tables, stale-data disclosure, architecture note), computed by a pure, deterministic, offline join script with no Provider dependency.

## 17. Pre-evaluation tests

Full test suite run before any Phase 3–6 Provider call, per this task's own requirement (see prior turn in this session) — passing at that time; no production code was modified in response to test results in this task, since none failed.

## 18. Stale historical Alpha-Mapper data (fully disclosed, not hidden)

Re-running the CURRENT production Alpha Mapper fresh (rather than trusting persisted `alpha_matches.json`, exactly as this task requires) surfaced **14 rows** (of 141) where the frozen CSV's `system_matched_alpha_id` — captured from a historical persisted run at holdout-build time — disagrees with today's fresh result:

- **10 rows** from run `8d21c047-fc0a-4d94-957d-3787f353a544` (SNDK, 2026-07-17) — the **same** pre-AI-gate-era run already flagged in the Holdout #1 root-cause analysis. Its persisted `alpha_matches.json` predates the `AI_ALPHA_IDS` hard gate.
- **4 rows** from run `4ca7dafa-6ac1-4d94-add0-f6f93b1af150` (NVDA, 2026-07-17) — a **newly identified** instance of the same staleness class, not previously flagged: its `metadata.json` shows `llm_provider: offline_recovery`, `quick_model: deterministic_fallback`, `recovered_from_run_id: 8be070d5-5d66-44d9-aa8d-8be5e70294ad` — this run's structured records were reconstructed from a raw TradingAgents state log, not produced by a live model call, and its persisted Alpha Mapper output likewise predates current production logic.

The frozen holdout CSV's `target_alpha_id` and `system_*` columns were **not** modified post-freeze. The alpha-match metric in §10 uses the **fresh**, current-production Alpha Mapper result (`item2_blind_holdout2_system_alpha.csv`) for all 141 rows, never the stale frozen value. The B1 stance question for these 14 rows was still asked relative to each row's own (possibly historically-stale) `target_alpha_id` — this remains a valid, uncorrupted stance comparison, since both current B1 and the independent stance reviewer answered the identical, fixed question.

## OLD-50 → HOLDOUT #1 → HOLDOUT #2 (never averaged or combined; different B1 versions, different samples)

| | OLD dev set (50, deterministic.v1 vs. reviewer) | OLD dev set (50, current-B1 vs. reviewer) | Holdout #1 (100, B1 v2) | **Holdout #2 (141, B1 v3)** |
|---|---|---|---|---|
| Polarity | 22/50 = 44% | 39/50 = 78% (pre-mixed-fix) / 45/50 = 90% (v2, same rows) | 79/100 = **79% FAIL** | **123/141 = 87.23% PASS** |
| Alpha match | — | 36/50 = 72% | 73/100 = **73% FAIL** | **84/141 = 59.57% FAIL** |

## 19. Confirmation checklist

- Production B1 prompt changed during this task: **NO** (SHA-256 identical to Phase-1 freeze value at report time)
- Alpha Mapper changed: **NO** (`git diff --stat HEAD` empty for `alpha_mapper.py`/`ai_alpha_discriminator.py`)
- Taxonomy changed: **NO** (`git diff --stat HEAD` empty for `alpha_taxonomy_v1.yaml`)
- B2 changed: **NO** (`git diff --stat HEAD` empty for `comqutor_alpha/conflict_engine/`)
- Thresholds/scoring changed: **NO**
- Holdout replaced or edited after results were seen: **NO**
- Reviewer labels changed after comparison: **NO**
- Root-cause-driven production fix attempted in this task: **NO** (out of scope by explicit instruction)
- Commit / push performed: **NO**

## 20. Integrity

141 source rows = 141 system-stance rows = 141 independent-stance-review rows = 141 system-alpha rows = 141 independent-alpha-review rows (verified programmatically via set-equality assertion in the join script, not sampled). No duplicate sample IDs, no missing IDs, no extra IDs.

## 21. Final verdict

**POLARITY = PASS** (87.23% ≥ 80%)
**ALPHA MATCH = FAIL** (59.57% < 75%)

This is the first and complete Blind Holdout #2 result, reported exactly as observed. Per this task's own explicit governance, no prompt/threshold/gate change follows from seeing these results in this task. B1 Evidence Stance v3 clears its own acceptance bar on genuinely unseen, doubly-excluded data — a real generalization result, not merely a development-set fit (87.23% here vs. 90% on the set v3's own predecessor v2 was tuned against, and a meaningful improvement over Holdout #1's 79%). The Alpha Mapper's shortfall is real, unchanged-code, and now measured twice on two independent unseen samples (73% then 59.57%) — it was never in scope for the B1 v2/v3 work and remains open. Any future fix made in response to either finding converts the relevant holdout into a new development set and requires yet another fresh, untouched holdout for the next final-acceptance attempt.
