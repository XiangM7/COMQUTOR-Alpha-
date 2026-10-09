# v0.2 Candidate 3 — Freeze Manifest

**Status: `CANDIDATE_3_ACCEPTED_FOR_FINAL_VALIDATION`**

This freezes Candidate 3 (`week2.alpha_classifier.v6` / `week2.alpha_classifier_batch.v4`) for a future, separate task's one-time final independent validation against the sealed 150-sample holdout. **This task did not perform that validation** — the decision below is based solely on the 100-sample Development Gold, which is explicitly a development metric, not independent evidence of production readiness.

## Acceptance Criteria

| Criterion | Result |
|---|---|
| Materially improves over baseline | YES — 64.00% → 81.00% (+17.00pp) |
| No major new regression class | YES — 1 isolated new regression (`gold-dev-045`), not systematic |
| Changes are general semantic rules | YES — no new Alpha IDs, no hardcoded sample IDs/claims/labels, no ticker-specific exceptions |
| Deterministic tests pass | YES — 225 passed, 0 failed, 1 skipped (env-gated smoke test) |
| Final 150 remains untouched | YES — sealed, hash unchanged, 0 samples exposed |

## Identifiers

| Field | Value |
|---|---|
| Classifier prompt version | `week2.alpha_classifier.v6` |
| Classifier prompt hash | `d53b2d7511f4c4a8089db746d09e4c79cb38f22597dac6459920ca3deac1171d` |
| Batch prompt version | `week2.alpha_classifier_batch.v4` |
| Batch prompt hash | `a03c8f673ffd387a866bc8dd585c4c96cf5464b80a50cb6e4c3fc5f894f68379` |
| Output schema (single) | `week2.alpha_classifier.output.v3` |
| Output schema (batch) | `week2.alpha_classifier_batch.output.v2` |
| HEAD | `7a9aefa5c7b5c820515447c6289aeef80eac9bdc` |
| Branch | `comqutor-structure-layer` |
| Development Gold SHA256 | `e8a78cbbb9359eb1361ca43891b52e71fa38528e0b6914c91aa5c9d874902ada` |

## Changed Files

- `comqutor_alpha/structure_engine/week2_llm.py` — the semantic guardrail addition (prompt text) and version metadata bump.
- `tests/test_week2_llm_semantic_runtime_integration.py` — two existing tests updated to reference the live prompt/version constants instead of hardcoding baseline text (established precedent from Candidates 1/2).
- `tests/test_candidate3_alpha_classifier_guardrail.py` (new) — narrowly targeted deterministic tests for the new guardrail content.

`comqutor_alpha/structure_engine/alpha_mapper.py` was **not** modified — the fix is a prompt-wording change only, no deterministic-scoring or candidate-architecture change.

## Design Basis

One cohesive semantic-sufficiency guardrail, explicitly designed not to repeat Candidate 1's documented mistake (an unconditional "bare figure never sufficient" rule that caused 21/25 regressions by blocking legitimate growth-language figures — see `v0_2_day4c_candidate1_regression_analysis.json`):

1. The Evidence's own words must state an Alpha's specific mechanism — not industry/ticker context, not a bare uncharacterized data listing.
2. **Explicit protective exemption**: a figure the Evidence already characterizes as a trend ("grew", "record", "accelerating", etc.) remains sufficient on its own — this is the exact carve-out Candidate 1 lacked.
3. Hypothetical/conditional-downside/rebuttal/skepticism framing must be judged by what it actually asserts now, never as affirmative evidence.
4. Price-technical indicators alone are never sufficient for A601.
5. A103 is preferred over A101 when concrete infrastructure capacity is named (the same confusion direction already documented in Candidate 1's own regression analysis).

Full per-sample basis: `v0_2_candidate3_dev_error_analysis.md` (36 baseline errors, 12 generalized categories).

## Do Not

- Do not modify Candidate 3 after this freeze — any further change is Candidate 4, in a future task.
- Do not unseal or execute the final 150-sample holdout except as the single, one-time final validation this freeze exists to enable.
- Do not cite the 81.00% development figure as independent validation.
