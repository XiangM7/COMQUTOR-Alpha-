# v0.2 Day 4 Frozen Regression — Phases A, B, C

Metric family: **DAY4_FROZEN_VALIDATION** — distinct from `HISTORICAL_ANALYSIS` (`v0_2_evidence_failure_analysis.json`/`v0_2_evidence_error_statistics.json`, unchanged, not overwritten). No Provider calls, no TradingAgents calls, no Fresh Runs. Full detail in the companion `v0_2_day4_frozen_regression.json`.

## Phase A — Development Regression (38 distinct historical samples)

**Validation type: `FROZEN_INPUT_RECOMPUTED_WITH_NEW_CODE`.** Method: deterministic-only replay — `map_claim_to_alpha()` with no `llm_gateway` (Architecture Replay's own zero-Provider contract) for the 34 Alpha Match samples, and `classify_evidence_stance()` (the always-local `evidence_stance.py` shadow layer) for the 9 Polarity samples. This deliberately avoids Provider calls per this task's instruction to prefer deterministic/local replay — it does **not** test the LLM-backed `alpha_classifier`/`evidence_stance_classifier` path that Day 3 identified as the actual historically-responsible mechanism (prompt rewrite in commit `c454245`).

| Metric | Value |
|---|---:|
| Total sample-rows | 43 (34 Alpha + 9 Polarity) |
| Distinct samples | 38 |
| Currently correct | **1** (`holdout5-057`, Polarity — attributable to the pre-existing "growth" keyword already in the lexicon, unrelated to the Day 3 "toll booth" addition) |
| Unchanged, still wrong | 0 |
| Changed, still wrong | 42 |
| Critical reversals | Not applicable to this replay — the critical-reversal gate is defined over the original human-reviewed labels (frozen: 0 accepted / 1 raw pre-exclusion), which this deterministic replay does not re-run |

**Honest finding:** the deterministic-only Alpha Mapper resolved `matched_alpha=None` for essentially all 34 Alpha Match samples (vs. a wrong-but-plausible Alpha historically) — a different failure mode (false negative vs. false positive), not an improvement. This confirms Day 3's conclusion: these samples' resolution genuinely depends on the LLM path, which a Provider-free regression cannot exercise. No case here is claimed fixed by this phase.

**Result classification: `INCOMPLETE_REPLAY_PATH_NOT_VALID_AS_FULL_PIPELINE_ACCURACY`.** The "1/43 correct" figure is **not** a system-accuracy measurement — this replay omitted the LLM-assisted semantic matching the real pipeline actually uses for these claims, so it measures only the deterministic fallback path in isolation. It is preserved here as a diagnostic (it shows the fallback path alone cannot resolve this corpus), never cited elsewhere in Day 4 reporting as an accuracy number, and not deleted.

## Phase B — MSFT-A102-DIRECT-INFERENCE-TRIGGER Frozen Recomputation

**Validation type: `FROZEN_INPUT_RECOMPUTED_WITH_NEW_CODE`.** Method: `comqutor_alpha.replay.pipeline.run_structure_replay()` against the frozen MSFT source run (`43472ace-...`) — a full pipeline rebuild from raw agent text using current code. Verified zero Provider/TradingAgents calls (`llm_provider_calls=0`, `market_data_provider_calls=0`, `tradingagents_calls=0`, `provider_zero=True`); source raw artifact hash unchanged before/after. Replay output: `outputs/replays/replay-20260916T205410Z-6b80a5c8/` (new location — original frozen run untouched).

| Stage | Result |
|---|---|
| Direction inference | **CONFIRMED FIXED** — both previously-`unknown` claims now resolve `direction=positive` in this real pipeline run |
| Claim quality | **CONFIRMED FIXED** — both claims now resolve `claim_quality=analytical` (previously `context_only`) |
| Evidence stance / activation | **NOT CONCLUSIVELY CONFIRMABLE** via this tool — activation collapses to `score=0.0`/`candidate` for **every** alpha on **every** ticker in this same zero-Provider replay (verified across all six frozen tickers). Even A304 — MSFT's best-evidenced alpha historically (39 real evidence groups) — shows 0 evidence-fact groups here. This is a universal limitation of Architecture Replay against this LLM-dependent pipeline, not something the Day 3 fix caused or left behind. |

**Result: `FAIL`.**

**First remaining incorrect stage:** Activation Scoring / Alpha Mapping's dependence on LLM-assisted semantic matching and stance classification — a validation-tooling limitation confirmed to affect all six tickers equally, not a residual defect in the Day 3 fix (independently confirmed correct at the direction and claim-quality stages, using this exact real pipeline run, not merely isolated function calls). Confirming whether A102 now reaches `active` requires a Provider-backed recomputation (Fresh E2E or targeted re-classification) — not performed today.

## Phase C — Rule/Evidence Re-Adjudication

Re-ran the exact Day 2 rule-evidence-output audit script, unchanged, against the same frozen persisted evidence/output for all six tickers (25 rule rows) — this underlying data is unaffected by the Day 3 code change (which touches only a fallback path not exercised by these already-persisted, LLM-computed records).

| PASS | FAIL | NOT_TRIGGERED | INSUFFICIENT_EVIDENCE | NOT_EVALUATED | NOT_APPLICABLE | REVIEW_REQUIRED | IMPLEMENTATION_ALIGNMENT_REQUIRED |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 21 | 1 | 0 | 0 | 0 | 0 | 3 | 0 |

**Unchanged from Day 2.** The one FAIL (MSFT-A102-DIRECT-INFERENCE-TRIGGER) is **not** counted PASS — its downstream effect remains unconfirmed per Phase B. No rule with missing/unconfirmed implementation is counted PASS, per explicit instruction.
