# Shared Week2LLMGateway JSON Parser Fix and Failed-30 Rerun

Status: **Fix confirmed, 30/30 previously-failed rows now parse cleanly, 0
real Provider calls spent beyond the authorized budget.** HEAD unchanged at
`b5837e80a4550fc35165d0013a8ef0f27ccb4c8f`. No commit, no push.

## 1–3. What exactly failed, and was Markdown fencing confirmed?

The original B1 50-row validation ran 5 batches of 10 sequentially. Batches
1, 3, and 5 (rows `evrs-001..010`, `evrs-021..030`, `evrs-041..050`) each
failed with a single `WEEK2_LLM_INVALID_JSON` entry in
`outputs/runs/b1-llm-stance-50-validation/error_logs/week2_llm_errors.jsonl`
— the raw response text failed strict `json.loads` before this module's own
identity/vocabulary validator ever ran. This codebase never logs raw
Provider payload content in error paths (by design, matching its existing
error-log convention elsewhere), so the exact three raw response strings
could not be inspected directly. Root cause was therefore established from
the strongest available evidence rather than assumed:

- The error code (`WEEK2_LLM_INVALID_JSON`, raised only when `json.loads`
  itself throws) is exactly the signature `_strip_markdown_json_fence`
  exists to fix — a whole-response markdown fence around otherwise-valid
  JSON.
- **Same-model, disclosed precedent already exists in this repository**:
  `docs/audit_artifacts/phase1_master/prompt_audit/v2_json_format_diagnostic_findings.json`
  documents that `claude-sonnet-4-6` — the exact model used for the B1
  validation — "reliably wraps its JSON response in a &#96;&#96;&#96;json
  ... &#96;&#96;&#96; markdown code fence" for a structurally similar task,
  **even when explicitly told not to** ("Do not return Markdown"), which is
  materially the same instruction the shared JSON-only prompt prefix gives
  ("Return strict JSON only, with no markdown"). This is not a new or
  speculative failure mode for this model/prompt-instruction combination.
- The rerun (section 14–16 below) is the empirical confirmation: after the
  fix, all 3 rerun batches against the exact same 30 rows, same prompt,
  same model, parsed with **zero** `WEEK2_LLM_INVALID_JSON` occurrences.

No evidence surfaced a materially different root cause for any of the three
failures (no distinct error codes, no timeout, no budget exhaustion — all
three were bit-for-bit the same `WEEK2_LLM_INVALID_JSON` signature), so the
fix was not broadened beyond markdown-fence stripping.

## 4–5. Where the existing fix lives, and whether it was reused or duplicated

`comqutor_alpha/structure_engine/structured_output_shadow_provider.py`
already contained `_MARKDOWN_JSON_FENCE_RE` / `_strip_markdown_json_fence`
(a conservative, whole-response-only regex,
`^```(?:json)?\s*\n(.*)\n```\s*$`, DOTALL) and `_MarkdownFenceStrippingModel`
(a model-response wrapper for that module's own real-Provider gateway
construction). Both pre-date this task, built and tested for the separate
`structured_claim_shadow` path only.

**The pure regex/function was moved, not copied.** `_strip_markdown_json_fence`
and its regex now live in `comqutor_alpha/structure_engine/week2_llm.py` as
a public `strip_markdown_json_fence`, and
`structured_output_shadow_provider.py` imports that exact function
(aliased back to its old local name so its own untouched 10-test file,
`test_shadow_markdown_fence_stripping.py`, needed zero changes and still
passes verbatim). There is now **one** implementation, not two.
`_MarkdownFenceStrippingModel` itself (the response-wrapper class, tightly
coupled to that module's own gateway-construction call site) was left in
place — only its internal call was repointed to the shared function.

## 6. What exact shared Week2LLMGateway parsing path changed

`week2_llm.py`'s `_strict_json_object(response)` — the single function
`invoke_json_with_trace`, `invoke_prebuilt_json_prompt`, and the legacy
`_invoke_json_legacy` path all call to turn a raw response into a dict —
now calls `json.loads(strip_markdown_json_fence(content))` instead of
`json.loads(content)`. This is the one shared chokepoint every named Week2
task's response passes through, so `claim_batch_enrichment`,
`alpha_classifier`, `structure_extractor`, and `evidence_stance_classifier`
all benefit uniformly from the same fix with no per-task code.

## 7–10. Confirmations

- **B1 prompt changed?** `NO`. `week2_llm._TASK_INSTRUCTIONS["evidence_stance_classifier"]`
  is byte-identical to before this task.
- **B1 semantic logic changed?** `NO`. `evidence_stance_llm.py` was not
  touched at all in this task.
- **`deterministic.v1` changed?** `NO`. `evidence_stance.py` was not
  touched at all in this task.
- **Any other Week2 semantic task's semantic behavior changed?** `NO`. Only
  the JSON *parsing* boundary changed; no task's instruction text, request
  shape, or validator changed. `structured_claim_shadow`'s own 10 existing
  tests (`test_shadow_markdown_fence_stripping.py`) pass unmodified,
  proving byte-identical behavior for that path too.

## 11. Focused test results

New: `tests/test_week2_llm_markdown_fence_parsing.py` — **17/17 passed**,
covering all 10 required scenarios from task spec section 8 (raw JSON,
json-tagged fence, untagged fence, whitespace tolerance, malformed-inside-
fence still fails, prose+fence not repaired, values unchanged by stripping,
existing-task compatibility via a fake model through the real
`invoke_json_with_trace`, B1's own batch validator receiving parsed items,
Replay's call site unaffected) plus full-stack proof
(`test_9b_end_to_end_apply_llm_stance_upgrade_accepts_a_fenced_real_shaped_response`)
that a fenced response now reaches `apply_llm_stance_upgrade` and becomes
genuinely `stance_method=llm`, not a parser-forced fallback.

Existing, untouched: `test_shadow_markdown_fence_stripping.py` (10/10),
`test_evidence_stance_llm.py` (27/27), `test_evidence_stance_classifier.py`,
`test_evidence_stance_integration.py`, `test_alpha_mapper*.py`, full
`tests/structured_output_shadow/` directory (589 tests) — **all pass**.

Two false-positive test failures were found and fixed with documented
reasoning during this task (both are pre-existing, over-literal
substring-scanning tests, not real defects):

1. `test_shadow_modules_contain_no_provider_route_cache_or_database_imports`
   flagged the literal text "from week2_llm" — which appeared only inside a
   comment I wrote (`"...imported above from week2_llm.strip_markdown_..."`),
   not in any actual import statement. `structured_output_shadow_provider.py`'s
   real import boundary is unchanged (it already imported from
   `comqutor_alpha.structure_engine.week2_llm` via the full qualified path
   before this task). Fixed by rewording the comment; the test's real
   invariant (no forbidden bare imports) was never actually violated.
2. My own new test asserting no "repair/fuzzy/guess/reconstruct" substrings
   appear anywhere in `week2_llm.py` failed on my own comment explicitly
   stating the code "*Never* fuzzy-matches or repairs" — a negation the
   crude substring check couldn't distinguish from an affirmative claim.
   Removed as redundant: `test_5`/`test_6` already behaviorally prove no
   repair happens.

## 12. Broader regression result

`python -m pytest -m "not integration"`: **3235 passed**, 1 pre-existing,
unrelated failure
(`test_current_semantic_components_match_approved_phase1_master_baseline`
— already confirmed, in the prior B1 report, to predate all work in this
arc via `git show HEAD:...` proving the committed baseline itself diverges
from the test's hardcoded hashes; this task's edits to `week2_llm.py` and
`structured_output_shadow_provider.py` simply shift two already-wrong
hashes to two different already-wrong hashes), 1 pre-existing skip
(missing optional dependency), 47 deselected. Ruff: clean on every touched
file.

## 13. Real Provider calls used (regression phase)

`0`. All fix verification was offline.

## 14. Exact 30 rows rerun

Identified directly from the **original, untouched**
`docs/audit_artifacts/b1_llm_stance_50_validation.csv` — every row with
`stance_method=deterministic_fallback` AND `fallback_reason=malformed_response`
— printed before any Provider call
(`IDENTIFIED_FAILED_30 = ['evrs-001', ..., 'evrs-050']`, 30 entries, exactly
`evrs-001..010`, `evrs-021..030`, `evrs-041..050`). Not resampled, not
reselected by current semantics — the identity set came from the historical
CSV, then the corresponding full row content (claim/evidence/reason codes
etc.) was looked up from the untouched original 50-row sample
(`docs/evidence_review_sample_records.json`) by `sample_id`.

## 15–17. Rerun results

3 batches of 10 (exactly `MAX_LOGICAL_CALLS`), 3 real Provider attempts, 0
retries, sequential. **30/30 rows parsed successfully and reached the B1
identity/vocabulary/counter-Alpha validator; 0 fell back.**
`rerun_fallback_reason_counts` is all-zero across all 8 reason codes,
including `malformed_response=0` — confirmed independently by the rerun's
own error log
(`outputs/runs/b1-llm-stance-failed30-rerun/error_logs/week2_llm_errors.jsonl`),
which does not exist because `Week2LLMGateway._log()` is only ever called
on a failure and none occurred.

## 18. Final combined 50-row result

`docs/audit_artifacts/b1_llm_stance_50_validation_after_parser_fix.csv` —
the prior 20 valid LLM rows (`provenance=original_50_row_validation`,
copied verbatim, never recomputed) plus the 30 rerun rows
(`provenance=parser_fix_rerun`). **50/50 rows now have a valid LLM result;
0 deterministic fallbacks remain.** The original
`b1_llm_stance_50_validation.csv` was verified byte-for-byte unchanged
(re-read after the rerun: still exactly 20 `llm` / 30 `deterministic_fallback`).

Recomputed from the final combined 50:

| Stance | Count |
|---|---|
| supports_alpha | 22 |
| opposes_alpha | 18 |
| mentions_alpha | 9 |
| supports_counter_alpha | 1 |
| neutral_background | 0 |

**LLM-vs-deterministic disagreements: 31/50 (62%)**, of which **7** are
direct support↔oppose reversals: `evrs-002` (A101), `evrs-003` (A001),
`evrs-019` (A304), `evrs-027` (A304), `evrs-039` (A301), `evrs-043` (A301),
`evrs-047` (A301). One observation worth surfacing plainly, not
overstating: **no row's final LLM stance is `neutral_background`** — every
row the LLM classified landed on a positive committal stance
(supports/opposes/mentions/supports_counter_alpha). Without independent
human labels (still `REVIEW_GOLD_AVAILABLE = NO`, re-confirmed — all 50
`review_status` remain `pending`), this is reported as an observed pattern,
not evidence that either side is more accurate.

**John's A304 rebuttal** (`evrs-014`, in the original successful batch,
`provenance=original_50_row_validation`): unchanged, `opposes_alpha`,
`stance_method=llm` — this task did not touch that result.

`INVALID_LLM_OUTPUT_ADMITTED = 0` and
`VALID_LLM_RESULT_OVERRIDDEN_BY_DETERMINISTIC = 0` — both hold by the same
unmodified code-level guarantee established in the original B1 task
(`evidence_stance_llm.py` was not touched here).

## 19. Files changed

- `comqutor_alpha/structure_engine/week2_llm.py` — added
  `strip_markdown_json_fence` (public) and its regex; `_strict_json_object`
  now calls it before `json.loads`.
- `comqutor_alpha/structure_engine/structured_output_shadow_provider.py` —
  removed the local duplicate regex/function; now imports the shared one
  (aliased to the same old private name, zero call-site changes); removed
  the now-unused `import re`; reworded one comment to fix a false-positive
  import-scanner match.
- **New**: `tests/test_week2_llm_markdown_fence_parsing.py`,
  `scripts/run_b1_llm_stance_failed30_rerun.py`,
  `docs/audit_artifacts/b1_llm_stance_failed30_rerun.csv`,
  `docs/audit_artifacts/b1_llm_stance_failed30_rerun_result.json`,
  `docs/audit_artifacts/b1_llm_stance_50_validation_after_parser_fix.csv`,
  this report and its JSON companion.
- **Untouched**: `docs/audit_artifacts/b1_llm_stance_50_validation.csv`
  (original evidence, verified byte-identical), `evidence_stance.py`,
  `evidence_stance_llm.py`, `alpha_mapper.py`, B1 prompt/ontology, PD-013,
  Activation, Conflict, Exposure, §5.1/§5.3, B2/B3/B4/B5.

## 20. HEAD / branch / commit / push

`HEAD = b5837e80a4550fc35165d0013a8ef0f27ccb4c8f` (unchanged before and
after). `BRANCH = comqutor-structure-layer`. `COMMIT = NO`. `PUSH = NO`.
