# v0.2 Day 4 Validation Manifest — PLAN ONLY, NOT EXECUTED

Nothing in this document has been run. No Provider call, no TradingAgents call, and no Fresh Run was made to produce it. This enumerates what Day 4 should execute and in what order; Day 3 does not start any of it.

## A. Development Regression — 38 Historical Error Samples

**Validation type: `FROZEN_INPUT_RECOMPUTED_WITH_NEW_CODE`.**

| Field | Value |
|---|---|
| Input source | The 38 distinct erroneous samples (34 Alpha Match + 9 Polarity, 5 overlapping) from `docs/audit_artifacts/v0_2_evidence_failure_analysis.json`, all drawn from run `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1` |
| Evidence cutoff | Frozen at this run's own `created_at`: 2026-07-24T23:05:51Z — no new evidence retrieval |
| Code HEAD | To be re-recorded at the start of Day 4 (do not assume — inspect); at minimum must postdate commit `c454245` (2026-08-21, the identified `alpha_classifier`/`evidence_stance_classifier` prompt rewrite) and include Day 3's `structured_output_adapter.py` lexicon fix |
| Gold baseline hash | SHA256 of `docs/audit_artifacts/v0_2_john_frozen_gold_baseline.yaml` at Day 4 start time (not applicable to this regression's pass/fail scoring directly, since these are row-level Alpha/Polarity samples, not ticker-level Gold acceptance — recorded for provenance only) |
| Prompt/model metadata | `week2.alpha_classifier` v3 and current `evidence_stance_classifier` version identifiers, plus whichever model/provider is configured at Day 4 run time — to be captured from the live run's own persisted metadata, not assumed in advance |
| Expected result artifact | `v0_2_semantic_reproducibility_audit_day4_confirmation.json` (new; supersedes nothing — Day 3's audit is preserved) |

This is the run that would upgrade each of the 21 Day 3 `FIX_PROVENANCE_IDENTIFIED` cases to either `CURRENTLY_CORRECT` (if the new prompt now produces the reviewer-expected output) or `CURRENTLY_WRONG` (if it does not) — a real Provider call against these 38 frozen claim texts, compared against the existing reviewer labels already on file. No new human review needed; the labels already exist.

## B. Independent Frozen Holdout — Validation Set

No second, independent frozen holdout set (distinct from the 200-row `item2_blind_holdout5` sample already used for the Day 2 statistics) currently exists in the repository — confirmed by search: no other `*_holdout*` labeled/reviewed CSV or JSON set was found under `docs/audit_artifacts/` besides the `item2_blind_holdout5_*` family. **If Day 4 requires a truly independent validation set** (one never used to derive the Day 2/3 failure analysis itself, to avoid evaluating the fix against the same data that motivated it), one would need to be freshly labeled — itself a `FRESH_RUN`-adjacent activity requiring new human review, out of scope for a quick Day 4 pass. Recommendation: Day 4 should explicitly decide whether the existing holdout5 set is acceptable for confirmation purposes (it was never used to *train* anything, only to *review* existing deterministic/LLM output — re-running it against new code is a legitimate regression, not data leakage) or whether an independent set is required first.

## C. Six-Ticker Frozen-Input Recomputation — Affected Modules Only

**Validation type: `FROZEN_INPUT_RECOMPUTED_WITH_NEW_CODE`.**

Only for the one module Day 3 actually changed (`comqutor_alpha/structure_engine/structured_output_adapter.py::infer_direction`, via the `POSITIVE_WORDS` addition), re-run Architecture Replay (`comqutor_alpha.replay.pipeline.run_structure_replay`, zero-Provider, zero-TradingAgents) against the six frozen runs already on file:

| Ticker | Run ID | Evidence cutoff | Code HEAD | Gold baseline hash | Expected artifact |
|---|---|---|---|---|---|
| NVDA | `57d7b4c4-dbb9-4134-b962-ee2a873941cc` | 2026-09-04T00:31:19Z | Day 4 start HEAD | SHA256 of frozen baseline at Day 4 start | `v0_2_day4_replay_NVDA.json` |
| QQQ | `f239a53f-4ebe-455c-bb76-5f5485903901` | 2026-09-11T17:10:46Z | same | same | `v0_2_day4_replay_QQQ.json` |
| SNDK | `e8e0f398-7b26-4462-8135-a1410ea5b335` | 2026-09-04T21:53:49Z | same | same | `v0_2_day4_replay_SNDK.json` |
| MSFT | `43472ace-454f-4c69-892c-adca91c25be7` | 2026-09-04T20:20:34Z | same | same | `v0_2_day4_replay_MSFT.json` — **primary target**: confirm whether MSFT-A102-DIRECT-INFERENCE-TRIGGER now reaches `active` |
| TSM | `dfc7ceb3-3584-4514-bd84-6c371aab3e95` | 2026-09-06T20:07:22Z | same | same | `v0_2_day4_replay_TSM.json` |
| AMD | `949f685a-3945-4fd0-b7b9-362b37c90721` | 2026-09-06T23:12:29Z | same | same | `v0_2_day4_replay_AMD.json` |

Prompt/model metadata: not applicable to this step (Architecture Replay never calls an LLM gateway — deterministic-only, per its own documented contract), so this recomputation cannot itself confirm any of the 21 Category A/B/C provenance findings (those need item A above, a live LLM call) — it can only confirm whether the Day 3 `structured_output_adapter.py` fix changes MSFT's deterministic direction/quality/stance chain as traced, at full pipeline scale.

## D. Fresh E2E — NVDA, QQQ (Day 4 or later, only after A/B/C above)

**Validation type: `FRESH_RUN`.** Explicitly NOT part of Day 4's first pass — only after the frozen-input steps above are complete and reviewed.

| Field | NVDA | QQQ |
|---|---|---|
| Input source | New TradingAgents + Provider research run | New TradingAgents + Provider research run |
| Evidence cutoff | As of the fresh run's own execution date | same |
| Code HEAD | Whatever HEAD is current when Day 4/5 actually executes this | same |
| Gold baseline hash | SHA256 of `v0_2_john_frozen_gold_baseline.yaml` at execution time | same |
| Prompt/model metadata | Captured live from the run's own persisted `llm_semantic_manifest.json` | same |
| Expected result artifact | `v0_2_fresh_e2e_NVDA_<new_run_id>.json` | `v0_2_fresh_e2e_QQQ_<new_run_id>.json` |

QQQ's fresh run additionally serves as the live re-check for the `QQQ-FROZEN-ALLOWED-MAIN-CONFLICTS` `REVIEW_REQUIRED` status and the pending `RULE_CHANGE_RECOMMENDATION` — still requires human/product-owner sign-off before any Gold-rule change, per Day 3's explicit instruction.

## Ordering

A and C (frozen-input, no Provider) should run before B is decided and well before D (fresh, Provider-backed) is attempted — consistent with the freeze plan's (`v0_2_validation_freeze_plan.md`) own validation-type ordering and Day 3's explicit instruction not to perform Fresh Runs today.

## Nothing Above Was Executed

No run was triggered, no Provider was called, no TradingAgents research was performed, and no formal validation of any kind occurred while producing this manifest.
