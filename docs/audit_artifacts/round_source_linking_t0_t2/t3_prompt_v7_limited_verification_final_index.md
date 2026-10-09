# alpha_classifier v7 limited real-verification: consolidated index and final conclusion

Closes the v7 limited real-verification effort authorized this round. All
executions below are independent, predict-only, and never modify
`t3live_20261001T014648Z_1fb9c9d5` (the v6 historical execution), John's
human review form, or historical Gold -- confirmed by checksum before and
after every real call in this effort.

## Execution index

| execution_id | config | samples | real requests | retries | outcome |
|---|---|---|---|---|---|
| `t3live_20261001T230846Z_16d44096` | v7, max_tokens=200 | gold-final-051 (smoke) | 2 (1 base + 1 retry) | 1 | TRUNCATED both attempts -- stopped per plan, max_tokens not raised unilaterally |
| `t3live_20261001T232646Z_0a0de18f` | v7, max_tokens=2048 | gold-final-051 (re-smoke) | 1 | 0 | MATCHED A304 -- continue condition met |
| `t3live_20261001T232716Z_5d79176f` | v7, max_tokens=2048 | remaining 18 | 18 | 0 | 15 valid (MATCHED/NONE/SELECTED_BUT_NOT_MATCHED), 3 TRUNCATED |
| `t3live_20261001T235944Z_c8839ced` | v7, max_tokens=4096 (these 3 samples only) | gold-final-127, gold-final-030, gold-final-077 | 3 | 0 | all 3 valid (no truncation) |

**Total real requests across the whole effort: 24. Total retries: 1.**
(21 consumed before this final retest + 3 here = 24, matching the
authorized ceiling exactly.)

## Results, reported separately by configuration (never merged)

### 2048-token configuration (19 samples processed)

16 valid classifications (13 MATCHED/NONE + gold-final-085's own
SELECTED_BUT_NOT_MATCHED), 3 TRUNCATED (gold-final-127, gold-final-030,
gold-final-077) -- **not** "19/19 success". Full per-sample detail already
reported in this round's prior message; unchanged here, and the original
TRUNCATED records in `t3live_20261001T232716Z_5d79176f` are unmodified.

### 4096-token configuration (the 3 previously-truncated samples only, separate real execution)

| sample_id | Stage 1 (raw) | Stage 2 (final) | vs v6 historical | vs ChatGPT (AI_REVIEW, not Gold) |
|---|---|---|---|---|
| gold-final-127 | select A103 | A103 (MATCHED) | same as v6 (A103) | still differs from ChatGPT (A501) -- disagreement persists |
| gold-final-030 | select A001 | SELECTED_BUT_NOT_MATCHED (positive-requirement gate this time, not the negative veto) | same bucket as v6 (PRODUCT_GATE_REJECTED) | **Correction (2026-10-02): Stage 1 is still a genuine disagreement** -- the model's own raw decision is select/A001, ChatGPT's is none/NONE; these differ and that disagreement is real. **Stage 2 is PRODUCT_GATE_REJECTED (==SELECTED_BUT_NOT_MATCHED), which is NOT the same thing as an explicit NONE** -- it means a valid in-taxonomy selection was made and then rejected by a post-hoc gate, never that no Alpha was selected. The two stages must not be collapsed into one verdict. |
| gold-final-077 | select A103 | A103 (MATCHED) | same as v6 (A103) | still differs from ChatGPT (A101) -- **taxonomy ambiguity persists, not resolved toward ChatGPT's label; the model was not forced to agree** |

None of the 3 hit the new 4096 cap (1341-2316 reasoning tokens each, well
under it). No sample needed a retry.

## Offline aggregate across the whole verification effort (computed from saved `request_attempts`, never estimated)

- **24** total real requests (base + retries) across all three
  configurations.
- **1** retry total (the 200-token smoke test's own retry; zero retries
  anywhere else).
- **45,498** known input tokens + **20,244** known output tokens =
  **65,742** known total tokens, summed across the **23** attempts whose
  usage was actually saved.
- **1** attempt's usage remains explicitly **UNKNOWN** -- the 200-token
  smoke test's first (pre-fix) attempt, superseded by its own retry before
  this round's `request_attempts` fix existed to capture it. Not
  estimated, not backfilled, and the 65,742-token known subtotal is **not**
  claimed to represent total consumption across all 24 requests.

## Final development-verification conclusion

- Of the 13 original Stage-1 disagreement samples: **9** now produce NONE
  under v7 (matching ChatGPT's prior label on each, but agreement is not
  equated with correctness); **1** (gold-final-085) shifted its raw
  decision toward ChatGPT's own pick (A001) but was rejected by the
  pre-existing, unmodified Step 7A veto; **3** required a token-cap
  increase to 4096 to even produce a valid classification, of which 2
  (gold-final-127, gold-final-077) ended up **unchanged from v6** once
  valid output was obtained, and 1 (gold-final-030) reproduced v6's own
  PRODUCT_GATE_REJECTED outcome exactly.
- Of the 6 agreement-control samples: **all 6 remained stable** -- zero
  regressions introduced by the v7 prompt edit.
- **This is not a single-variable experiment.** Three things changed
  relative to v6's own historical configuration at once: the prompt
  (v6->v7), the token-cap field mapping (`max_completion_tokens`->
  `max_tokens`, an earlier-round bug fix), and the effective token budget
  (200->2048, then ->4096 for 3 samples). No part of this result is
  attributed to the prompt alone.
- ChatGPT's labels are AI_REVIEW throughout this entire effort -- a second
  opinion, never promoted to Gold, and agreement with it is never reported
  as "correct."
- **This does not constitute, and is not reported as, an improvement in
  overall classification accuracy, and does not constitute John's T3
  acceptance.** It is development/regression verification evidence for the
  v7 prompt edit and the token-cap/field-mapping fixes, scoped to exactly
  these 19 samples.

This round's v7 limited real-verification effort ends here. No further
prompt modification, no additional real calls, no 40-sample rerun, and no
Plan B / NVDA Fresh Run follow from this document.
