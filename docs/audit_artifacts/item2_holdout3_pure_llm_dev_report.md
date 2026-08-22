# Alpha Mapper Pure-LLM Semantic Authority + Holdout #3 Development Re-Evaluation

**THIS IS NOT A BLIND ACCEPTANCE RESULT. HOLDOUT #3 WAS ALREADY CONSUMED (see
`item2_blind_holdout3_report.md`). FORMAL ALPHA ACCEPTANCE REQUIRES A
GENUINELY NEW BLIND HOLDOUT #4.**

## 1. Architecture change

The Alpha Mapper's semantic authority was migrated from
"LLM-primary-with-deterministic-fallback" (Segment 2/Holdout #3 architecture)
to **Pure-LLM semantic authority**: the LLM is now the *sole* source of
`matched_alpha`/`match_status`. It sees the full canonical taxonomy and
resolves to exactly one of two successful outcomes -- `select` (exactly one
Alpha) or `none` (no Alpha materially fits). There is no successful
"defer"/"cannot decide" outcome. On any operational failure (disabled, no
gateway, provider timeout/error, malformed output, unknown Alpha ID) the
result is `match_status="unavailable"` -- the deterministic scorer's own
conclusion is *never* substituted as the semantic answer, on any path.
Deterministic scoring, the AI hard gate, and the 0.35 threshold are
unmodified and continue to run as diagnostics/counterfactual only, exposed
via two new fields: `deterministic_top_alpha`/`deterministic_match_status`.

Full detail: `item2_holdout3_pure_llm_dev_freeze_manifest.json`.

## 2. Regression validation

- `tests/test_alpha_mapper_llm_authority.py`: 19/19 PASS (tests A-M; test N
  lives in `tests/replay/test_semantic_call_artifact_binding.py`).
- Full offline suite (`python -m pytest tests/ -q`): **3697 passed, 8
  failed, 47 skipped**. All 8 failures are pre-existing or a disclosed
  structural consequence of this task's own approved architecture change --
  none is an unexplained regression. See the freeze manifest's
  `pre_evaluation_regression_results` for the full, itemized breakdown.

## 3. Development re-evaluation on the (already-consumed) Holdout #3 set

Reused the exact same frozen 152-row set (`item2_blind_holdout3_frozen.csv`,
SHA-256 `e6c778d3bbfb65e7bf9e6a72580d499424f1371c69f2027f477faae15ab82bc6`,
verified unchanged) and the exact same 152 original independent-reviewer
labels (`item2_blind_holdout3_alpha_review.json`, verified unchanged, not
re-derived). Real Provider calls were made only for the new Pure-LLM Alpha
inference itself (152/152 attempts, 0 missing, 0 unavailable, chunked
2x100/52 from the start).

| Metric | Value |
|---|---|
| Development accuracy | **119/152 = 78.29%** |
| Development target (>=75%) | **MET** |
| Original Holdout #3 accuracy (consumed, historical) | 105/152 = 69.08% |
| Deterministic-only counterfactual (historical) | 61.18% |
| Change vs original | **+9.21 points** |
| Change vs deterministic counterfactual | **+17.11 points** |

### Row transitions (old system vs new Pure-LLM system, vs the same reviewer label)

| Transition | Count |
|---|---|
| wrong -> correct | 22 |
| correct -> wrong | 8 |
| wrong -> different wrong | 7 |
| unchanged correct | 97 |
| unchanged wrong | 18 |

### Original 54 "LLM deferred" rows (the dominant historical failure mode)

| | Old (deterministic fallback) | New (Pure-LLM) |
|---|---|---|
| Accuracy | 22/54 = 40.74% | **37/54 = 68.52%** |
| Outcome mix | 54 deterministic-fallback | 49 select, 5 none, 0 unavailable |

fallback-wrong-now-correct: 19 · fallback-correct-now-wrong: 4 · both-wrong: 13 · both-correct: 18

This confirms the hypothesis from Section 1: forcing the LLM to always
resolve to a real select/none decision substantially improved accuracy on
exactly the rows that were previously the dominant failure mode -- though
this was measured, not assumed in advance (Section 1's own caveat).

### Original 98 "LLM committed" rows (checking for regression on previously-strong cases)

| | Old | New |
|---|---|---|
| Accuracy | 83/98 = 84.69% | 82/98 = 83.67% |

wrong-now-correct: 3 · correct-now-wrong: 4 · both-wrong: 12 · both-correct: 79

Essentially preserved (-1 row net) -- the "select the closer Alpha, don't
defer" prompt rewording did not materially degrade the cases the LLM was
already confident about.

### AI family (A101/A102/A103)

Combined: **23/39 = 58.97%** vs original 38.46% (+20.5 points).
By Alpha: A101 3/6=50.0%, A102 3/7=42.9%, A103 17/26=65.4%.
19 of the 39 AI-family rows were previously deferred; now 38 selected, 1 none.
Confusion within family (wrong): A101->A103 (1), A102->A103 (1), A103->A101 (2).
Confusion into A201/A301/A601/A304: A101->A201 (1), A101->A304 (1), A102->A201 (1), A102->A301 (2), A103->A201 (4), A103->A301 (2).

### MU ticker

New accuracy 14/28 = 50.0% vs original 32.14% (+17.9 points). 15 of 28 MU
rows were previously deferred; 1 now NONE. Dominant reviewer Alpha: A103
(12/28); dominant system Alpha: A201 (14/28) -- the confusion matrix in
`item2_holdout3_pure_llm_dev_comparison.csv` has the row-level detail.

### NONE analysis

System NONE: 5 · Reviewer NONE: 6 · NONE/NONE correct: 4 ·
system-NONE-but-reviewer-Alpha: 1 · system-Alpha-but-reviewer-NONE: 2.
NONE remains a low-frequency, not dominant, outcome -- consistent with a
genuine semantic decision rather than a disguised uncertainty escape hatch.

## 4. Disclosed consequences of this architecture change (not part of the dev metric)

1. **Live default configuration impact.** `COMQUTOR_WEEK2_LLM_ENABLED` is
   unset in this repo's `.env`/shell and PD-006 is `NOT_APPROVED` for
   default/live use. Under the prior architecture a disabled classifier
   silently used the deterministic result; under Pure-LLM authority it now
   reports `unavailable`/`matched_alpha=null` for every claim. Confirmed
   and explicitly re-confirmed with the product owner mid-task (twice, via
   AskUserQuestion) before proceeding -- flagged here for deployment
   awareness, not a defect in this task's own scope.
2. **Architecture Replay.** `run_structure_replay` is hardcoded
   `llm_gateway=None` by design ("architecture diagnosis only"). Under
   Pure-LLM authority this now always yields `matched_alpha=null`, so
   Architecture-Replay-derived Activation/Conflict evidence is structurally
   empty. Affects `tests/test_artifact_export_and_api.py::test_replay_conflict_does_not_get_run_id_mismatch`
   and `tests/test_evidence_review_sample.py::test_60_sample_includes_conflict_and_activation_evidence`
   (left failing, not force-fixed -- fixing would require either an offline
   LLM double inside Architecture Replay or reusing historical Alpha
   decisions, both out of this task's scope).

## 5. Verdicts

**PURE-LLM AUTHORITY MIGRATION: PASS**

**HOLDOUT #3 DEVELOPMENT RE-EVALUATION: 119/152 = 78.29%**

**DEVELOPMENT TARGET MET (>=75%)**

**THIS IS NOT A BLIND ACCEPTANCE RESULT. HOLDOUT #3 WAS ALREADY CONSUMED.
FORMAL ALPHA ACCEPTANCE REQUIRES A GENUINELY NEW BLIND HOLDOUT #4.**
