# NVDA run (034a0a60-430e-41f8-8321-03a11389707a): one-time documentation precision corrections

All items below verified directly against this run's own frozen artifacts (`llm_semantic_calls.jsonl`, `alpha_matches.json`, `alpha_activations.json`, `conflicts.json`) -- none restated from the AI review without independent confirmation.

## 1. "800 real Provider calls" -- unverified claim, corrected

800 is the count of **logical records** in `llm_semantic_calls.jsonl` for `task=alpha_classifier, prompt_version=week2.alpha_classifier.v7`. Verified breakdown by `provider_status`:

| provider_status | count | meaning |
|---|---:|---|
| `success` | **430** | a real Provider request was sent and returned a usable response |
| `budget_exhausted` | **370** | **zero** Provider requests -- `_reserve_call()` refused before any request was sent |
| **total logical records** | **800** | |

**"800 real Provider calls" is false. The real count of alpha_classifier v7 calls that actually reached the Provider is 430**, not 800. (This is separate from, and smaller than, the ~688 reconciled total real Week2 requests across all 4 tasks reported in `nvda_run_request_reconciliation_and_audit_fix.md` -- that figure already correctly excluded budget_exhausted rows; this section corrects a different, narrower v7-specific overstatement in `05_frozen_taxonomy_and_rules/README.md`.)

## 2. 370 vs. 400 budget-rejected -- same underlying log, different scope, not two different sources

Both numbers come from the **same** artifact, `llm_semantic_calls.jsonl` -- there is no separate "400-count log" in this package.

- **370** = `provider_status=budget_exhausted` rows where `task=alpha_classifier` only. This is the number independently reproducible from `alpha_matches.json`'s own per-claim `reason="llm semantic classifier unavailable: call_budget_exhausted"` field (claim-level view).
- **400** = the same `provider_status=budget_exhausted` count, summed across **all 4 Week2 tasks** (370 alpha_classifier + 16 structure_extractor + 14 evidence_stance_classifier calls' own smaller share + 8 structured_adapter -- 30 total from the other three tasks). `alpha_matches.json` only ever reflects `alpha_classifier`'s own results, so it cannot independently reproduce the 400 figure; that requires reading `llm_semantic_calls.jsonl` directly (included in this delivery's evidence folder).

## 3. Official result: v2_verified only

Already corrected in the v2 joint-review package (`01_conclusions_and_alpha_candidates.md`, `08_source_coverage_root_cause_analysis.md`). `04_derived_metrics/README.md` is corrected in this delivery to state the three score sets' formulas and weights separately: `v1` = `week3.activation.mvp_v1` (weights 0.35/0.20/0.25/0.10/0.10); `v2`/`v2_verified` = `activation.v2.evidence_local_structure(.verified_gate).v1` (weights 0.35/0.20/0.20/0.10/0.10/0.05, six components including `direction_consistency`) -- these are two different formulas with different component sets, not the same formula under two names.

## 4. A001: 1 claim-level match, 0 claims in any Activation evidence pool -- two separate facts

Verified: `alpha_matches.json` has exactly 1 claim with `matched_alpha=A001` (`news_agent:news_report:claim:50`, `relation=activation`, `eligible=True`, `assertion_status=asserted`). Verified separately: `alpha_activations.json`'s `evidence_count`/`claim_ids` for A001 are `0`/`[]` in **all three** score sets (`v1`, `v2`, `v2_verified`) -- this one match never became qualifying Activation evidence (the specific further filter responsible, e.g. duplicate-group/claim-quality grouping, was not traced further this round; not needed to state the two facts separately, which is what was asked). **"A001 has no match" is wrong (1 exists); "A001 has supporting Activation evidence" is also wrong (0 in every score set) -- both must be stated, not collapsed into one.**

## 5. The 8 conflict candidate pairs' real, top-level rejection codes

Verified directly against `conflicts.json`'s own `arbitration.candidate_evaluations[].reason_codes` (not the per-claim `evidence_audit` exclusion reasons used in an earlier draft of this delivery's own Part 1 table, which is real detail but not the pair's own verdict code):

| pair | outcome | reason_codes |
|---|---|---|
| A001 vs A501 | rejected | `MISSING_LEFT_EVIDENCE`, `DIRECTION_ROLE_UNRESOLVED` |
| A003 vs A501 | rejected | `MISSING_LEFT_EVIDENCE`, `DIRECTION_ROLE_UNRESOLVED` |
| A101 vs A304 | rejected | `DIRECTION_ROLE_UNRESOLVED` |
| A102 vs A304 | rejected | `DIRECTION_ROLE_UNRESOLVED` |
| A201 vs A304 | rejected | `DIRECTION_ROLE_UNRESOLVED` |
| A301 vs A304 | rejected | `DIRECTION_ROLE_UNRESOLVED` |
| A304 vs A601 | rejected | `DIRECTION_ROLE_UNRESOLVED` |
| A501 vs A601 | rejected | `DIRECTION_ROLE_UNRESOLVED` |

**Correction to an earlier framing**: this arbitration is **not independent of the human-review gate**. `DIRECTION_ROLE_UNRESOLVED` on all 8 pairs is a direct downstream consequence of the same fact documented in `08_source_coverage_root_cause_analysis.md` -- with zero claims `HUMAN_REVIEWED`, the verified-Activation evidence each side of a pair would need to establish a bull/bear role never exists, so no pair's direction role can be resolved either. The per-claim `evidence_audit` breakdown (reported in the v2 package's Part 1) remains real and accurate detail about why each side's raw candidate evidence was excluded, but it is a different, lower-level fact than the pair's own top-level verdict code, and the two must not be conflated as "two independent gates agreeing."

## 6. Request totals: known subset vs. derived estimate, kept explicitly distinct

- **448**: real attempts with complete, directly-counted per-attempt detail in `llm_semantic_calls.jsonl` -- a precise, audited figure for exactly that subset.
- **~240**: attempts whose real completion is known only from an ephemeral process-log line count (`SEMANTIC_RECORDER_APPEND_FAILED` occurrences) -- explicitly *not* a persisted, independently-reproducible count; stated as approximate throughout.
- **~688** (448+240): a **derived reconciliation**, not an independently-measured total -- never described as "exact" or "precise accounting" anywhere in this delivery.
- One append failure corresponds to one real attempt's own audit record being lost -- not to "one logical call" in general (a single logical call that retried once could have one of its two real attempts degrade while the other persists; `tests/test_a304_a501_reverse_evidence_fix.py`'s sibling file `tests/test_week2_llm.py::test_concurrent_success_timeout_and_retry_all_preserve_their_own_attempts` demonstrates this distinction directly against the real code).

## 7. "No source found in available materials" vs. "confirmed no external basis" -- kept distinct throughout this delivery

Every place this delivery describes the ~1001 claims with no plausible source match states it as: *"no external source was found in this run's own frozen materials and matching logic"* -- never as proof the claim lacks any real-world external basis. Re-running the same production matcher against the same frozen data confirms the matcher's own internal consistency (it would find the same candidates again); it is not independent proof that the matcher's recall is complete, and this delivery does not claim that.

## 8. Original Agent HOLD/price-related text -- labeled as unreviewed research suggestions, not official Alpha conclusions

Confirmed present in this run's own raw output: `trader:trader_investment_plan:claim:8` ("FINAL TRANSACTION PROPOSAL: HOLD"), `portfolio_manager:final_trade_decision:claim:48` ("Rating: Hold (with a constructive bias and a defined trigger to upgrade)"), `research_manager:investment_plan:claim:82` ("Hold the position, do not add into resistance, trim into 232-234..."). These are the TradingAgents research agents' own narrative output -- real, and preserved, but they are **research suggestions that have not passed joint (human or otherwise-verified) review**, and are labeled as such in `02_NVDA_FINAL_RESULTS.md`/`.json` in the final delivery package, never presented as, or alongside, the official `v2_verified` Alpha result.
