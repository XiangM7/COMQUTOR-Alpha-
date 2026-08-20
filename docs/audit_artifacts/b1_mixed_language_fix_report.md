# QA Closure v0.1.2 — B1 Mixed/Contrastive Language Improvement

## Preservation

Branch `comqutor-structure-layer`, HEAD at task start `9f9b681fd2e4ffaf94ad463495bf6f9144b4282c` (unchanged — no commit made by this task). Worktree at task start: 5 untracked files only (Item 2 root-cause analysis artifacts), nothing else — reported as the actual current state, not an assumed prior HEAD.

## What changed

**One production file, one string constant:** `comqutor_alpha/structure_engine/week2_llm.py`, the `evidence_stance_classifier` entry in `_TASK_INSTRUCTIONS`. Added explicit target-relative resolution guidance for mixed/contrastive/conditional Evidence: identify which part of the Evidence actually bears on `target_alpha_id`'s own thesis, resolve from that part alone (net endorsement → `supports_alpha`, net rebuttal → `opposes_alpha`), and fall back to `mentions_alpha`/`neutral_background` only when the target thesis genuinely cannot be resolved — not merely because the sentence also contains other, target-irrelevant content. Conditional language (`if`/`could`/`may`/`would`) is explicitly named as affecting *confidence*, not *whether a stance exists*. No sixth stance value was added. The existing counter-Alpha sentence (only report `supports_counter_alpha` when the Evidence materially supports the counter Alpha's own thesis) is unchanged except for one added clause — "and never merely because the Evidence is mixed" — the same general principle applied to the one place counter-Alpha routing intersects it, not a counter-routing redesign.

`prompt_version` for this task bumped `evidence_stance.llm_classifier.v1` → `v2` (ADR-005: a versioned prompt identifier must change with the instructions it identifies, so no old cached v1 semantic-call result is ever silently reused as if it reflected this behavior).

**Nothing else in production code changed.** `evidence_stance_llm.py` (contract/validation layer), `evidence_stance.py` (deterministic.v1 fallback), Alpha Mapper, B2–B5, the AI hard gate, and the taxonomy are all byte-identical to before this task.

## Before / after (same 50 rows, same frozen J3 reviewer)

| | correct | accuracy | critical reversals |
|---|---|---|---|
| BEFORE (`b1_llm_stance_50_validation_after_parser_fix.csv`, frozen, untouched) | 39/50 | 78% | 0 |
| AFTER (real rerun through the current production path, this task) | **45/50** | **90%** | **0** |

Critical support↔opposition reversals independently re-verified at both points — **not assumed**: 0 before, 0 after.

## The six MIXED_OR_CONDITIONAL_LANGUAGE root-cause rows

| sample_id | before | after | reviewer | changed | now agrees | B2 impact before | B2 impact after |
|---|---|---|---|---|---|---|---|
| evrs-007 | mentions_alpha | **opposes_alpha** | opposes_alpha | YES | YES | no B2 count impact | no B2 count impact |
| evrs-020 | mentions_alpha | mentions_alpha | supports_alpha | no | no | no B2 count impact | no B2 count impact |
| evrs-026 | mentions_alpha | mentions_alpha | supports_alpha | no | no | no B2 count impact | no B2 count impact |
| evrs-034 | mentions_alpha | **supports_alpha** | supports_alpha | YES | YES | no B2 count impact | **counts toward B2 supporting_evidence_count** |
| evrs-036 | opposes_alpha | **mentions_alpha** | mentions_alpha | YES | YES | no B2 count impact | no B2 count impact |
| evrs-040 | mentions_alpha | **supports_alpha** | supports_alpha | YES | YES | no B2 count impact | **counts toward B2 supporting_evidence_count** |

**4 of 6 fixed, 2 unchanged, 0 worsened.** The two unchanged rows (evrs-020, evrs-026) were independently judged `GENUINELY_AMBIGUOUS` in the prior root-cause analysis — evrs-020 contains an explicit hedging clause ("though sources call it reasonable") and evrs-026 explicitly frames a "dominant tension" between competing narratives. The prompt change correctly did **not** force these to flip; that would have been overfitting to the current 50-row set, not a genuine semantic improvement. This is evidence the fix is behaving as a real semantic principle, not a lookup table.

As a side effect, one row outside this bucket also fixed itself: **evrs-006** (`TARGET_ALPHA_AMBIGUITY`, `mentions_alpha` → `neutral_background`, now agrees) and **evrs-008** (`COUNTER_ALPHA_BOUNDARY`, `opposes_alpha` → `supports_counter_alpha`, now agrees) — both plausible, since the same target-relative resolution reasoning generalizes past the exact six rows it was designed around.

**B2-impacting rows improved: 2 of 4** (evrs-034, evrs-040 now genuinely count as `supports_alpha` evidence for their target Alpha; evrs-020/evrs-026 correctly remain unresolved, so B2's `supporting_evidence_count` is unaffected for those two).

## All-50 collateral check

| category | count |
|---|---|
| UNCHANGED_CORRECT | 39 |
| UNCHANGED_DISAGREEMENT | 5 (evrs-013, 020, 026, 042, 045) |
| FIXED_DISAGREEMENT | 6 (evrs-006, 007, 008, 034, 036, 040) |
| **NEW_DISAGREEMENT** | **0** |

Zero rows regressed. Confusion transitions (before → after), all six are fixes, none are regressions: `mentions_alpha → supports_alpha` ×2, `mentions_alpha → neutral_background` ×1, `mentions_alpha → opposes_alpha` ×1, `opposes_alpha → supports_counter_alpha` ×1, `opposes_alpha → mentions_alpha` ×1. Notably **zero** `supports_alpha → mentions_alpha` transitions occurred — the fix never downgraded a previously-correct committal stance.

## Provider / reproducibility

Provider: `anthropic` · model: `claude-sonnet-4-6` (the same production profile/model as the original validation and its parser-fix rerun) · temperature: production default (unchanged, not overridden) · prompt_version: `evidence_stance.llm_classifier.v2` · 5 logical batches, 5 real Provider attempts, 0 retries, 0 fallback rows, 0 invalid outputs admitted. Full log: `docs/audit_artifacts/b1_mixed_language_provider_call_log.json`.

## Tests

Added 10 fake-gateway tests to `tests/test_evidence_stance_llm.py` (the general patterns from task spec section 9) plus one prompt-identity/versioning test — 11 new, all passing, alongside the 27 pre-existing (38/38 total in that file). Consistent with this file's own established, explicit convention ("no network, no Provider, no LLM call anywhere in this file"), these verify the **contract layer** correctly threads each pattern's correct answer through unchanged; they are not themselves proof that the real prompt produces that answer for real text — that empirical proof is the 50-row regression above, which is where the real Provider budget for this task was actually spent. Broader sweep for collateral damage: `test_evidence_stance_classifier.py`, `test_evidence_stance_integration.py`, `test_week2_llm_markdown_fence_parsing.py`, `test_alpha_mapper.py`, `test_week2_llm_semantic_runtime_integration.py`, `test_ai_alpha_mapper_discrimination.py`, `test_alpha_mapper_nvda_real_report.py` — 264 tests, all passing.

`tests/test_msft_a102_a304_taxonomy_adjudication.py` shows 2 failures, both expected and not caused by this task's logic:
- `test_head_unchanged_from_session_frozen_starting_commit` — pre-existing, hardcodes an old HEAD from a prior session checkpoint; already failing before this task started, unrelated to any code.
- `test_a6_b1_b2_b3_b4_invariant_modules_are_byte_identical` — this test pins an exact SHA-256 for `week2_llm.py` in its own scoped `FROZEN_HASHES` dict, guarding *that task's own* (MSFT A102/A304 taxonomy adjudication) claim that B1–B4 were untouched *by it*. This task's `week2_llm.py` edit is a legitimate, in-scope, explicitly-authorized B1 change, so this hash correctly, expectedly drifts — same precedent as QA Closure Item 4's `conflict_detector.py` edit tripping the identical guard for the identical reason. Not reverted, not silently updated.

## Holdout

**OLD 50 = DEVELOPMENT SET.** This result must not be read as final QA polarity acceptance — it is the same 50 rows used to diagnose the problem in the first place. **NEW BLIND HOLDOUT REQUIRED = YES**, to be generated in a separate, later task only.

## Final verdict

**B1 MIXED-LANGUAGE FIX = PASS** — all six acceptance criteria (A–F) hold: the systematic issue demonstrably improved (4/6 root-cause rows fixed, 2 correctly left alone), zero critical reversals introduced, zero collateral regression anywhere in the 50, no benchmark-specific hardcoding (the change is a general target-relative resolution principle), B1 remains LLM-semantic-primary, and B2/Alpha Mapper/taxonomy/threshold/AI-gate semantics are all untouched.
