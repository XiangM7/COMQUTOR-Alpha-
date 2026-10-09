# alpha_classifier v7 limited real-verification plan (FROZEN, not executed)

**Status: frozen plan only. Zero real Provider calls were made to produce
this document.** 27 is the proposed ceiling for the NEXT paid run, pending
separate, explicit authorization -- this does not reuse any prior round's
authorization and does not execute automatically.

## 1. What this verifies (and does not)

This checks whether the real classifier's own raw decision changes, under
the v7 prompt, on 19 specific samples already analyzed against v6's real
historical behavior. It is **not** an independent blind test, **not** a
claim of reaching John's overall accuracy target, and **does not**
rewrite `t3live_20261001T014648Z_1fb9c9d5`'s own historical 27/40 (Stage 1)
or 23/35 (Stage 2) numbers -- those remain exactly what that execution
produced under v6.

## 2. Configuration difference from the v6 historical run (stated explicitly, not glossed over)

| | v6 historical run (`t3live_20261001T014648Z_1fb9c9d5`) | this verification run |
|---|---|---|
| prompt | v6 (`week2.alpha_classifier.v6`) | v7 (`week2.alpha_classifier.v7`) |
| actual serialized token-cap field | `max_completion_tokens` (confirmed bug -- DeepSeek does not recognize this field) | `max_tokens` (fixed, confirmed via `tests/test_week2_llm.py::test_server_gateway_deepseek_max_tokens_reaches_real_serialized_request`) |
| configured cap value | 200 | 200 (unchanged, not raised) |
| model/provider | deepseek / deepseek-v4-flash | deepseek / deepseek-v4-flash (unchanged) |
| thinking mode | not disabled | not disabled |

**Because the field-mapping fix landed between the v6 run and now, this is
NOT a clean "prompt-only" A/B experiment.** Any observed change in a
sample's raw decision could be caused by the prompt change, by the
token-cap field now actually reaching the Provider correctly (previously it
silently didn't), or both. This report will state this caveat again next to
every result -- no difference will be attributed to "v7" alone without this
qualifier.

## 3. The frozen 19-sample list (unique, verified against the real historical records)

All `claim_id`/`claim_text`/`ticker`/`evidence_text`/`run_id`/`quota_category`
values below are copied verbatim from `t3_eval_records.jsonl` and
`t3_targeted_diagnostic_sample_2026-09-30.json` -- never retyped by hand.
These are **development/regression comparison labels, not human Gold**.

### Phase 1 (1 sample -- doubles as the wiring/smoke check, no separate call added)

| sample_id | ticker | v6 Stage 1 (raw) | v6 Stage 2 (final) | ChatGPT | role |
|---|---|---|---|---|---|
| gold-final-051 | AMD | A304 | A304 (MATCHED) | A304 | agreement control -- confirmed against the real record before freezing this list |

### Phase 2 (18 samples -- run only if Phase 1 shows no truncation/parse failure)

**5 further agreement controls** (model and ChatGPT already agreed under v6):

| sample_id | ticker | v6 Stage 1/2 | ChatGPT |
|---|---|---|---|
| gold-final-061 | GOOGL | A304 | A304 |
| gold-final-074 | TSM | A101 | A101 |
| gold-final-059 | TSM | A103 | A103 |
| prod-run-002 | MSFT | A102 | A102 |
| prod-run-013 | MSFT | NONE | NONE |

**13 Stage-1 disagreement samples** (verdict from the prompt v7 adjudication doc, carried forward unchanged -- not re-litigated here):

| sample_id | ticker | v6 Stage 1 (raw) | v6 Stage 2 (final) | ChatGPT | verdict |
|---|---|---|---|---|---|
| gold-final-001 | AMD | A304 | A304 (MATCHED) | NONE | MODEL_VIOLATES_FROZEN_RULE |
| gold-final-019 | GOOGL | A304 | A304 (MATCHED) | NONE | MODEL_VIOLATES_FROZEN_RULE |
| gold-final-041 | MSFT | A304 | A304 (MATCHED) | NONE | MODEL_VIOLATES_FROZEN_RULE |
| gold-final-052 | TSM | A304 | A304 (MATCHED) | NONE | MODEL_VIOLATES_FROZEN_RULE |
| gold-final-079 | NVDA | A304 | A304 (MATCHED) | NONE | MODEL_VIOLATES_FROZEN_RULE |
| gold-final-085 | QQQ | A304 | A304 (MATCHED) | A001 | TAXONOMY_BOUNDARY_AMBIGUOUS (listed, not forced to agree) |
| gold-final-077 | AMD | A103 | A103 (MATCHED) | A101 | TAXONOMY_BOUNDARY_AMBIGUOUS (listed, not forced to agree) |
| gold-final-127 | SNDK | A103 | A103 (MATCHED) | A501 | MODEL_VIOLATES_FROZEN_RULE |
| gold-final-144 | GOOGL | A103 | A103 (MATCHED) | NONE | MODEL_VIOLATES_FROZEN_RULE |
| gold-final-030 | QQQ | A001 | NONE (PRODUCT_GATE_REJECTED) | NONE | MISSING_CONTEXT |
| gold-final-048 | NVDA | A301 | A301 (MATCHED) | NONE | MODEL_VIOLATES_FROZEN_RULE |
| prod-run-014 | SNDK | A003 | A003 (MATCHED) | NONE | MODEL_VIOLATES_FROZEN_RULE |
| prod-run-015 | SNDK | A003 | A003 (MATCHED) | NONE | MODEL_VIOLATES_FROZEN_RULE |

Frozen sample files (already written, hash-stable, read-only until used):
`t3_prompt_v7_verification_phase1_smoke.json` (1 sample),
`t3_prompt_v7_verification_phase2_remaining18.json` (18 samples).

## 4. Global request budget: 27, shared, not per-sample-guaranteed

Max 1 retry per sample; the 27 ceiling is a **shared pool** across all 19
samples combined (base attempts + retries) -- it is not "19 bases + 19
guaranteed retries" (which could reach up to 38). The existing, already
real-execution-tested `_BudgetTrackingGateway` mechanism (in
`t3_diagnostic_evaluation_driver.py`, unmodified) enforces this exactly as
it did for the original authorized Plan A run: it checks remaining budget
before starting each new sample, counting every real attempt including
retries. The same already-disclosed limitation applies: a single sample's
own retry can push the final count up to 1 over the configured ceiling on
the very last sample processed, never more.

**Phase 1 budget**: `--max-actual-requests 2` (1 base + up to 1 retry for
the single sample).

**Phase 2 budget**: `27 - <Phase 1's actual actual_requests_made>`, read
directly from Phase 1's own `t3_eval_summary.json` after it completes --
never assumed in advance. If Phase 1 needed zero retries (used 1 of 27),
Phase 2 gets 26. If Phase 1 needed its one retry (used 2 of 27), Phase 2
gets 25.

## 5. Stop conditions (checked after Phase 1, before Phase 2 is ever started)

Phase 1's own single real result must be inspected before proceeding.
**Abort the whole plan (do not run Phase 2) if any of these hold**, and in
every abort case: save the real Phase 1 result exactly as the Provider
returned it, do not convert it to NONE, do not raise the token cap, do not
disable thinking mode, do not switch models, do not retry outside the
already-exhausted budget:

- `outcome_code` is `PARSE_FAILED` or `CALL_FAILED` (request or parse
  failure).
- The record's `provider_response.finish_reason` (newly captured this
  round -- see Section 7) is `"length"` (real truncation against the
  configured 200-token cap, now that the field-mapping fix means the cap
  actually reaches the Provider).

## 6. Pre-fixed result-reporting schema (decided now, before any real call)

Every one of the 19 samples is reported in exactly one of these mutually
exclusive buckets -- never silently folded into another:

- **Stage 1 (raw)**: the real call's own `decision`/`selected_alpha_id`
  (`validated_output` on the call record) -- independent of any later gate.
- **Stage 2 (post-gate)**: the final `predicted_alpha`/`outcome_code` after
  `map_claim_to_alpha`'s full pipeline (Step 7A/7A.2 included for any A001
  selection).
- **PRODUCT_GATE_REJECTED**: Stage 1 was `select` with a valid in-taxonomy
  ID, but Stage 2 ended with no usable `predicted_alpha` -- reported with
  the original `llm_selected_alpha_id` and the specific override flag
  (`alpha_specific_invalidation_override` / `alpha_positive_requirement_override`)
  that fired, exactly as the v6/v7 driver fix (prior round) already
  structures this.
- **REQUEST_FAILED**: `outcome_code == "CALL_FAILED"`.
- **PARSE_FAILED**: `outcome_code == "PARSE_FAILED"`.
- **TRUNCATED**: `provider_response.finish_reason == "length"` (checked
  regardless of whether JSON parsing happened to still succeed on a
  truncated-but-coincidentally-valid-looking response).

Two top-level views are reported, never merged into one number:

1. **How each of the 13 original disagreement samples' Stage 1 raw
   decision changes** (same label as v6 / changed to a different Alpha /
   changed to NONE / now PRODUCT_GATE_REJECTED / request or parse failure),
   cross-referenced against ChatGPT's existing label for context only
   (ChatGPT is never re-run, never treated as Gold).
2. **Whether any of the 6 agreement-control samples regress** (Stage 1 raw
   decision no longer matches v6's own real historical raw decision for
   that sample) -- reported as its own explicit count, since a control
   regressing is itself a finding regardless of what happens to the
   disagreement samples.

The 2 `TAXONOMY_BOUNDARY_AMBIGUOUS` samples (gold-final-085, gold-final-077)
remain listed separately in both views; their outcome is reported
descriptively, never scored as "correct" or "incorrect" against ChatGPT's
label.

No "new accuracy" or "new agreement rate" across the 19 (or any subset) is
computed or reported as a headline number -- only the per-sample, per-bucket
facts above.

## 7. What gets recorded per real call (already wired, verified offline this round)

- Real request: `request_control.endpoint`, `.request_model`,
  `.max_tokens_field` (must read `"max_tokens"`, confirming the fix is live
  for this run), `.max_tokens_value` (must read `200`).
- Real response: `provider_response.provider_request_id`, `.response_model`,
  `.finish_reason` (new field, this round), `.raw_usage` (real input/output
  token counts, including any `reasoning_tokens` sub-field DeepSeek
  reports).
- Retry count, `provider_status`, `validation_status` -- all already
  persisted by the existing, unmodified `SemanticCallRecord`/driver
  mechanism.

## 8. Directly executable commands (NOT run this round)

```bash
cd /Users/xiangmao/COMQUTOR-Alpha-

# Phase 1: single real call (gold-final-051), doubles as the wiring smoke test.
COMQUTOR_WEEK2_LLM_ENABLED=1 \
COMQUTOR_WEEK2_LLM_PROVIDER=deepseek \
COMQUTOR_WEEK2_LLM_MODEL=deepseek-v4-flash \
.venv/bin/python3 docs/audit_artifacts/round_source_linking_t0_t2/t3_diagnostic_evaluation_driver.py live \
  --i-acknowledge-this-makes-real-provider-calls \
  --samples-file docs/audit_artifacts/round_source_linking_t0_t2/t3_prompt_v7_verification_phase1_smoke.json \
  --review-form-file docs/audit_artifacts/round_source_linking_t0_t2/t3_human_review_form_2026-09-30.json \
  --output-dir outputs/t3_prompt_v7_verification \
  --max-actual-requests 2 --max-retries-per-call 1 --max-output-tokens 200

# STOP HERE. Inspect the printed summary + <output-dir>/<execution_id>/t3_eval_records.jsonl
# for outcome_code and provider_response.finish_reason before proceeding.
# Only if clean (no PARSE_FAILED/CALL_FAILED, finish_reason != "length"):

# Phase 2: remaining 18 real calls. Replace <N> with 27 minus Phase 1's own
# actual_requests_made (read from Phase 1's t3_eval_summary.json), not assumed.
COMQUTOR_WEEK2_LLM_ENABLED=1 \
COMQUTOR_WEEK2_LLM_PROVIDER=deepseek \
COMQUTOR_WEEK2_LLM_MODEL=deepseek-v4-flash \
.venv/bin/python3 docs/audit_artifacts/round_source_linking_t0_t2/t3_diagnostic_evaluation_driver.py live \
  --i-acknowledge-this-makes-real-provider-calls \
  --samples-file docs/audit_artifacts/round_source_linking_t0_t2/t3_prompt_v7_verification_phase2_remaining18.json \
  --review-form-file docs/audit_artifacts/round_source_linking_t0_t2/t3_human_review_form_2026-09-30.json \
  --output-dir outputs/t3_prompt_v7_verification \
  --max-actual-requests <N> --max-retries-per-call 1 --max-output-tokens 200
```

`t3_diagnostic_evaluation_driver.py` itself is **not modified** by this
plan -- both commands use its existing, already real-execution-tested
`live` mode exactly as the original authorized Plan A run did, with a
different (non-40-count) samples file. `--review-form-file` is required by
the CLI for provenance-hashing (`freeze_identity.json`) only -- live mode
never reads its content for predictions. Each phase writes its own
independent `execution_id` under `outputs/t3_prompt_v7_verification/`,
never touching `t3live_20261001T014648Z_1fb9c9d5`'s own directory, John's
human review form, or historical Gold.

Dry-run of both commands' underlying `run_live_evaluation` call, with a
fake gateway (zero real Provider calls), confirms both samples files parse
correctly, the budget-tracking mechanism behaves as expected, and every
field this plan's result schema depends on (`llm_selected_alpha_id`,
`alpha_specific_invalidation_override`, `alpha_positive_requirement_override`,
`outcome_code`, `predicted_alpha`) is present on the resulting records.
