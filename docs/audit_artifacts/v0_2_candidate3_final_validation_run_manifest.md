# v0.2 Candidate 3 — Final Validation Run Manifest (FROZEN BEFORE EXECUTION)

**Validation type: `ONE_SHOT_INDEPENDENT_FINAL_VALIDATION`.** This manifest is written and frozen before any Provider call in this task.

| Field | Value |
|---|---|
| Final Gold path | `docs/audit_artifacts/v0_2_alpha_final_gold_v1.json` |
| Final Gold SHA256 | `a3c402ce391cfba1bd49d3d84a352e222e2775118f24b9ebf2a003183e2392de` |
| Final Gold sample count | 150 |
| Candidate 3 classifier hash | `d53b2d7511f4c4a8089db746d09e4c79cb38f22597dac6459920ca3deac1171d` (`week2.alpha_classifier.v6`) |
| Candidate 3 batch hash | `a03c8f673ffd387a866bc8dd585c4c96cf5464b80a50cb6e4c3fc5f894f68379` (`week2.alpha_classifier_batch.v4`) |
| HEAD | `7a9aefa5c7b5c820515447c6289aeef80eac9bdc` |
| Branch | `comqutor-structure-layer` |

## Model / Provider Identity

- Research profile: `comqutor_anthropic_medium_sonnet46_v1` (`ANTHROPIC_PROFILE_ID`)
- Provider: `anthropic`
- Model: `claude-sonnet-4-6`

## Parameters (unchanged from prior Day 4G runs)

- Temperature: production default, no explicit override — identical to the Day 4G baseline and Candidate 3 development runs.
- Retry policy: `max_retries=0` at the harness level, identical to `scripts/run_day4g_candidate3_baseline_dev.py`. Any Provider-client-level automatic retry for transient failures is unmodified.
- Timeout: 60.0 seconds per call, identical to the Day 4G harness.

## Evaluation Code

`scripts/run_day4i_candidate3_final_validation.py` — new, modeled byte-for-byte on the Day 4G harness logic (`scripts/run_day4g_candidate3_baseline_dev.py`). Only the input join table (Final Gold's 150 samples instead of Development Gold's 100) and output file names differ.

## Environment

`COMQUTOR_WEEK2_LLM_ENABLED=true`, scoped **inline** to the validation command only. Never persisted to `.env`.

## Run Plan

- Sample count: 150
- Planned evaluation passes: **1**
- Tuning after result permitted: **NO**

## Explicitly Prohibited This Task

Running baseline, Candidate 1, or Candidate 2 against Final Gold; running Candidate 3 a second time; pre-testing a subset; manually probing samples; selectively rerunning misclassifications; tuning prompts after observing outputs; changing model/provider settings after seeing results.
