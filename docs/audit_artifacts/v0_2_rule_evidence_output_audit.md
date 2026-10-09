# v0.2 Rule → Evidence → Output Audit — Day 2

Authority: `docs/audit_artifacts/v0_2_john_frozen_gold_baseline.yaml` (`JOHN_WRITTEN_V0_2_BASELINE`). Read-only audit — no production code, test, or Gold rule was changed to produce this document; no Provider/TradingAgents calls; no fresh runs. Full per-row data (including all evidence IDs) is in the companion `v0_2_rule_evidence_output_audit.json`.

Sources used (all persisted, none fabricated):
- `docs/audit_artifacts/v0_2_gold_operational_contract.json` — the 19 base rule definitions (rule_id, rule_type, evidence_condition, acceptable_alphas).
- `docs/audit_artifacts/v0_2_john_frozen_gold_baseline.yaml` — the 16-pair `allowed_main_conflicts` frozen baseline (6 additional rows, one per ticker).
- `docs/audit_artifacts/v0_2_evidence_trigger_matrix.json` — independent, pre-existing trigger-condition adjudication (`trigger_state`, `evidence_strength`) for NVDA/SNDK/MSFT/TSM/AMD, each verified against the frozen baseline's own `run_id`.
- `docs/audit_artifacts/v0_2_qqq_postfix_acceptance.json` — QQQ's own trigger adjudication (`frozen_trigger`), verified bound to the frozen post-remediation run `f239a53f-...` (the trigger matrix's QQQ entries are bound to the superseded historical run `f88c8956-...` and were **not** used for QQQ's `trigger_condition_status` for that reason — see Notable Findings).
- Each frozen run's own `outputs/runs/<run_id>/evidence_facts.json` (per-alpha stance-labeled evidence groups → `supporting_evidence_ids`/`opposing_evidence_ids`), `structure_graph.json` (`active_alphas`/`dominant_alphas`/`regime_level_alphas`/`candidate_alphas`/`blocked_alphas` → `actual_system_output`), and `conflicts.json` (`admitted`/`candidate`/`main_conflict`).

## Adjudication Tally (25 rule rows)

| State | Count |
|---|---|
| PASS | 21 |
| FAIL | 1 |
| REVIEW_REQUIRED | 3 |
| NOT_TRIGGERED | 0 (used as a `trigger_condition_status` value for 2 conflict rows; never used as the final `adjudication_status`) |
| INSUFFICIENT_EVIDENCE | 0 |
| NOT_EVALUATED | 0 |
| NOT_APPLICABLE | 0 |

**NOT_EVALUATED is never counted as PASS** — the adjudication logic checks for a persisted trigger source first and only proceeds to PASS/FAIL reasoning once one exists; every one of the 25 rows here had a persisted, non-fabricated trigger source available, so 0 rows landed in NOT_EVALUATED this round (this state remains available in the schema for any future rule lacking a persisted adjudication).

## Rule Rows

### NVDA (FORMAL_GOLD, run `57d7b4c4-dbb9-4134-b962-ee2a873941cc`)

| Rule ID | Rule Type | Trigger | Actual Output | Adjudication | Evidence Trace |
|---|---|---|---|---|---|
| NVDA-A101-AI-GROWTH | must_detect_if_evidence_present | PRESENT | A101=active | **PASS** | COMPLETE (13 supporting) |
| NVDA-A301-FUNDAMENTAL-GROWTH | should_detect_if_supported / conditional_only | PRESENT | A301=active | **PASS** | COMPLETE (15 supporting) |
| NVDA-A304-VALUATION-RISK | must_detect_if_evidence_present | PRESENT | A304=active | **PASS** | COMPLETE (20 supporting) |
| NVDA-GROWTH-VS-VALUATION-CONFLICT | conditional_only | PRESENT | A101/A301/A304=active | **PASS** | COMPLETE (48 supporting) |
| NVDA-SUPPORTING-STRUCTURES | should_detect_if_supported | PRESENT | A103/A201/A601=active | **PASS** | COMPLETE (28 supporting) |
| NVDA-FROZEN-ALLOWED-MAIN-CONFLICTS | allowed_main_conflicts | REVIEW_REQUIRED (no dedicated trigger adjudication for the pair itself) | admitted=[A101__A304, A301__A304, A304__A601], main=A101__A304 | **PASS** | COMPLETE — both frozen pairs actually admitted |

### QQQ (FORMAL_GOLD, run `f239a53f-4ebe-455c-bb76-5f5485903901`)

| Rule ID | Rule Type | Trigger | Actual Output | Adjudication | Evidence Trace |
|---|---|---|---|---|---|
| QQQ-A001-RATE-CUT-CYCLE | should_detect_if_supported / conditional_only | ABSENT | A001=candidate | **PASS** (correctly not forced) | COMPLETE (0 supporting, 2 opposing) |
| QQQ-A003-LIQUIDITY-EXPANSION | should_detect_if_supported / conditional_only | ABSENT | A003=candidate | **PASS** (correctly not forced) | **INCOMPLETE** — no evidence_fact_group carries any stance for A003 in this run at all |
| QQQ-A304-VALUATION-RISK | conditional_only | PRESENT/STRONG | A304=active | **PASS** | COMPLETE (43 supporting, 2 opposing) |
| QQQ-A501-RECESSION-RISK | should_detect_if_supported / conditional_only | ABSENT | A501=candidate | **PASS** (correctly not forced) | COMPLETE (0 supporting, 3 opposing) |
| QQQ-A601-NARRATIVE-MOMENTUM | should_detect_if_supported | PRESENT/STRONG | A601=active | **PASS** | COMPLETE (20 supporting, 13 opposing) |
| QQQ-ETF-CONTEXT-CONTROL | forbidden_dominant_without_strong_evidence | UNCERTAIN (strong ETF-level A301 evidence) | A301=active, not dominant | **PASS** (asymmetric rule: passes unless dominant, regardless of uncertainty) | COMPLETE (11 supporting, 2 opposing) |
| QQQ-FROZEN-ALLOWED-MAIN-CONFLICTS | allowed_main_conflicts | REVIEW_REQUIRED | admitted main=A301__A304 (not in frozen baseline [A001__A501, A003__A501, A304__A601]) | **REVIEW_REQUIRED** (frozen QQQ status, unchanged) | COMPLETE (63 supporting, 20 opposing across baseline-pair alphas) |

### SNDK (FORMAL_GOLD, run `e8e0f398-7b26-4462-8135-a1410ea5b335`)

| Rule ID | Rule Type | Trigger | Actual Output | Adjudication | Evidence Trace |
|---|---|---|---|---|---|
| SNDK-A201-SEMICONDUCTOR-CYCLE | should_detect_if_supported / conditional_only | PRESENT | A201=active | **PASS** | COMPLETE (21 supporting, 1 opposing) |
| SNDK-ANTI-OVER-AI-CONTROL | forbidden_dominant_without_strong_evidence | ABSENT | A101/A102 not dominant | **PASS** | COMPLETE (2 supporting) |
| SNDK-FROZEN-ALLOWED-MAIN-CONFLICTS | allowed_main_conflicts | NOT_TRIGGERED (no conflict admitted) | admitted=[] | **PASS** (absence of a listed conflict is not a failure) | COMPLETE (42 supporting, 2 opposing) — `IMPLEMENTATION_ALIGNMENT_REQUIRED` for pair A201__A304 (non-canonical taxonomy, see below) |

### MSFT (SILVER_DIAGNOSTIC, run `43472ace-454f-4c69-892c-adca91c25be7`)

| Rule ID | Rule Type | Trigger | Actual Output | Adjudication | Evidence Trace |
|---|---|---|---|---|---|
| MSFT-A101-ENTERPRISE-AI-CONDITIONAL | conditional_only | PRESENT (MODERATE) | A101=active | **PASS** | COMPLETE (10 supporting) |
| MSFT-A102-DIRECT-INFERENCE-TRIGGER | must_detect_if_evidence_present | PRESENT (STRONG) | A102=candidate (not detected) | **FAIL** | COMPLETE (only 1 supporting evidence group — thin) |
| MSFT-A102-INDIRECT-INFERENCE-SUPPORT | should_detect_if_supported | UNCERTAIN (WEAK) | A102=candidate | **REVIEW_REQUIRED** | COMPLETE (1 supporting) |
| MSFT-CAPEX-BURDEN-CONDITIONAL | conditional_only | PRESENT (STRONG) | A304=candidate (not detected) | **REVIEW_REQUIRED** (matches the pre-existing human `step4_result: REVIEW` in `v0_2_acceptance_adjudication.json` Case C) | COMPLETE (13 supporting) |
| MSFT-FROZEN-ALLOWED-MAIN-CONFLICTS | allowed_main_conflicts | NOT_TRIGGERED (no conflict admitted) | admitted=[] | **PASS** (absence not a failure) | COMPLETE (40 supporting) — `IMPLEMENTATION_ALIGNMENT_REQUIRED` for all 3 pairs (see below) |

### TSM (SILVER_DIAGNOSTIC, run `dfc7ceb3-3584-4514-bd84-6c371aab3e95`)

| Rule ID | Rule Type | Trigger | Actual Output | Adjudication | Evidence Trace |
|---|---|---|---|---|---|
| TSM-AI-TO-FOUNDRY-TRANSMISSION | conditional_only | PRESENT | A101/A201/A301=active | **PASS** | COMPLETE (36 supporting) |
| TSM-FROZEN-ALLOWED-MAIN-CONFLICTS | allowed_main_conflicts | REVIEW_REQUIRED (main=A101__A304, not itself covered by the trigger matrix's single base rule) | admitted main=A101__A304 (in frozen baseline) | **PASS** — frozen pair actually admitted | COMPLETE (57 supporting, 2 opposing) — `IMPLEMENTATION_ALIGNMENT_REQUIRED` for pairs A201__A304, A101__A304 (see below) |

### AMD (SILVER_DIAGNOSTIC, run `949f685a-3945-4fd0-b7b9-362b37c90721`)

| Rule ID | Rule Type | Trigger | Actual Output | Adjudication | Evidence Trace |
|---|---|---|---|---|---|
| AMD-AI-GROWTH-VS-VALUATION | conditional_only | PRESENT | A101/A201/A301/A304=active | **PASS** | COMPLETE (81 supporting) |
| AMD-FROZEN-ALLOWED-MAIN-CONFLICTS | allowed_main_conflicts | REVIEW_REQUIRED | admitted main=A101__A304 (in frozen baseline) | **PASS** — frozen pair actually admitted | COMPLETE (81 supporting) — `IMPLEMENTATION_ALIGNMENT_REQUIRED` for pairs A201__A304, A301__A304 (see below) |

## Notable Findings

1. **MSFT-A102-DIRECT-INFERENCE-TRIGGER is a genuine FAIL**, not a NOT_EVALUATED or a REVIEW_REQUIRED masquerading as PASS: the trigger matrix independently adjudicates PRESENT/STRONG evidence for direct inference-workload language, but MSFT's own run only produced 1 supporting evidence-fact group for A102 and the alpha stayed at `candidate`, never reaching `active`. This is consistent with, and does not re-litigate, the pre-existing `must_detect_if_evidence_present` miss already tracked in `v0_2_evidence_failure_analysis.md`.
2. **QQQ-A003-LIQUIDITY-EXPANSION has `evidence_traceability: INCOMPLETE`** — the frozen QQQ run's `evidence_facts.json` contains no evidence-fact group with any A003 stance at all (not even `mentions_alpha`). The rule's `PASS` adjudication (ABSENT trigger, correctly not forced) still holds on `v0_2_qqq_postfix_acceptance.json`'s own authority, but there is no lower-level evidence-fact corroboration for it in this run's own persisted data. No evidence ID was invented to fill this gap.
3. **QQQ's trigger matrix entries are stale relative to the frozen baseline run.** `v0_2_evidence_trigger_matrix.json`'s QQQ block is bound to run `f88c8956-...` (historical, pre-remediation), not the frozen `f239a53f-...` run. QQQ's `trigger_condition_status` values in this audit were therefore taken from `v0_2_qqq_postfix_acceptance.json` instead, which is explicitly bound to the correct run. The trigger matrix was not used for QQQ's adjudication and no attempt was made to reconcile the two — they simply describe different runs.
4. **QQQ-FROZEN-ALLOWED-MAIN-CONFLICTS remains `REVIEW_REQUIRED`, unchanged.** The actual admitted main conflict (A301__A304) is not one of John's three frozen allowed pairs. This is not re-adjudicated here — it is carried forward exactly as Day 1 and John's instruction require.
5. **Two of MSFT's three rules resolve to `REVIEW_REQUIRED`** (A102-INDIRECT and CAPEX-BURDEN) rather than PASS or FAIL. Both cases correctly refuse to guess: `should_detect_if_supported`/`conditional_only` misses are informational under v0.2 semantics, and the CAPEX-BURDEN row explicitly reproduces the pre-existing, already-published human `REVIEW` verdict from `v0_2_acceptance_adjudication.json` Case C rather than overriding it.

## Implementation Alignment Audit (Section 5 — mapping Day 1's 15 items)

| # | Frozen Gold Requirement | Current Implementation Behavior | Source File / Code Path | Exact Mismatch | Minimal Implementation Action Needed | Production Code Change Required? |
|---|---|---|---|---|---|---|
| 1 | QQQ allowed_main_conflicts includes A003__A501 | Absent from every rule-source file (v0.1 YAML, v0.2 YAML, gold_operational_contract.json) for QQQ | `comqutor_alpha/config/j2_provisional_regression_labels_v0.1.yaml` (QQQ block) | Pair never encoded | Add `A003__A501` to QQQ's `allowed_main_conflicts` (v0.1) and/or `conditional_conflicts`/`allowed_conflicts` (v0.2) | **No** — config-only edit |
| 2 | QQQ allowed_main_conflicts includes A304__A601 | Absent from every rule-source file for QQQ | same file | Pair never encoded | Add `A304__A601` to QQQ's config block | **No** — config-only edit |
| 3 | SNDK allowed_main_conflicts includes A201__A304 | Present in v0.1 (flagged non-canonical by the loader); stripped entirely in v0.2 | `comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml` (A201's `conflict_alphas` is `[]`) | Taxonomy does not declare this pair as a canonical conflict | Add a `conflict_alphas` entry linking A201↔A304 in the taxonomy, or accept the pair as taxonomy-exempt in the regression-label schema | **Yes** — taxonomy is production config read by `comqutor_alpha/alpha_library/alpha_loader.py`; not modified in this Day 2 task pending John's decision |
| 4 | MSFT allowed_main_conflicts includes A102__A304 | Present in v0.1 (flagged non-canonical, PD-017 `REJECTED_BY_INDEPENDENT_LLM_ADJUDICATION`); stripped in v0.2 | same taxonomy file (A102's `conflict_alphas` is `[]`) | Taxonomy gap + a standing product-decision rejection (PD-017) that predates John's frozen baseline | Requires John's explicit ruling on whether PD-017 still stands against the new baseline before any taxonomy change | **Yes, if approved** — not modified in this Day 2 task |
| 5 | MSFT allowed_main_conflicts includes A101__A304 | Absent from every rule-source file for MSFT | `j2_provisional_regression_labels_v0.1.yaml` / `_v0.2.yaml` (MSFT block) | Pair never encoded (it is a canonical taxonomy pair — no taxonomy gap) | Add `A101__A304` to MSFT's config block | **No** — config-only edit |
| 6 | MSFT allowed_main_conflicts includes A301__A304 | Absent from every rule-source file for MSFT | same | Pair never encoded (canonical) | Add `A301__A304` to MSFT's config block | **No** — config-only edit |
| 7 | TSM allowed_main_conflicts includes A201__A304 | Present in v0.1 (flagged non-canonical); stripped in v0.2 | `alpha_taxonomy_v1.yaml` (A201's `conflict_alphas` is `[]`) | Taxonomy gap, same root cause as item 3 | Same taxonomy decision as item 3 (shared root cause across SNDK/TSM/AMD) | **Yes, if approved** |
| 8 | TSM allowed_main_conflicts includes A101__A304 | Absent from every rule-source file for TSM (though it matches TSM's own actual detected main conflict) | `j2_provisional_regression_labels_v0.1.yaml` / `_v0.2.yaml` (TSM block) | Pair never encoded (canonical) | Add `A101__A304` to TSM's config block | **No** — config-only edit |
| 9 | AMD allowed_main_conflicts includes A201__A304 | Present in v0.1 (flagged non-canonical); stripped in v0.2 | `alpha_taxonomy_v1.yaml` (A201's `conflict_alphas` is `[]`) | Taxonomy gap, same root cause as items 3/7 | Same taxonomy decision as item 3 | **Yes, if approved** |
| 10 | AMD allowed_main_conflicts includes A301__A304 | Present in v0.2 (`allowed_conflicts`) and the documentation-only contract JSON, but **absent from v0.1's `allowed_main_conflicts`** — the only field `evaluator.py::conflict_comparison` actually reads | `comqutor_alpha/config/j2_provisional_regression_labels_v0.1.yaml` (AMD block) | Version/field-name gap, not a taxonomy or content gap (pair is canonical and already present in v0.2) | Add `A301__A304` to AMD's v0.1 `allowed_main_conflicts` list, or repoint the evaluator at a merged/updated source | **No** — config-only edit (or a 1-line evaluator source-selection change, not a semantics change) |
| 11 | `forbidden_dominant_without_strong_evidence` is an official Gold v0.2 semantic family | Implemented under a different name, `should_not_be_dominant_without_strong_evidence`, in both v0.1 and v0.2 label YAMLs, and genuinely read by `comqutor_alpha/regression/evaluator.py` line 333 | `comqutor_alpha/regression/evaluator.py` (`six_ticker_qa_alpha_fields`) | Naming mismatch only — mechanism is real, loaded, and functioning | None required functionally; optional cosmetic rename for documentation consistency | **No** |
| 12 | `must_detect_if_evidence_present` is an official Gold v0.2 semantic family | Documentation-only in `v0_2_gold_operational_contract.json`; no runtime evaluator enforces an evidence-conditional "must detect" gate under this exact name | No runtime code path exists | The 19-rule roster in this audit is the only place this family is currently operationalized (via this Day 2 audit's own trigger-matrix cross-reference) | Wire a runtime check that reads `must_detect_if_evidence_present` rules from a single authoritative rule file and fails a run when a STRONG trigger is not surfaced (this is effectively what this Day 2 audit does manually, offline) | **Yes** — genuinely new runtime logic; not implemented in this Day 2 task (would exceed "minimal, evidence-justified" fix scope) |
| 13 | `should_detect_if_supported` is an official Gold v0.2 semantic family | Closest real analogue: v0.1 `conditional_alphas` / v0.2 `conditional_conflicts` (informational-miss only) | `comqutor_alpha/regression/evaluator.py::alpha_comparison` | Different code path, different name, and does not distinguish "should_detect" from "conditional_only" the way the frozen semantics do | Same as item 12 — a real runtime distinction, not implemented here | **Yes** — not implemented in this Day 2 task |
| 14 | `conditional_only` is an official Gold v0.2 semantic family | Closest real analogue: v0.1 `conditional_alphas` / v0.2 `conditional_conflicts` | same | Same as item 13 | Same as item 13 | **Yes** — not implemented in this Day 2 task |
| 15 | `do_not_force` is an official Gold v0.2 semantic family | Documented as "a cross-cutting constraint... not a standalone rule_type of its own"; no dedicated rule entries or code enforcement | No runtime code path exists | By design, this family has no separate rule content to wire — it is a constraint on how *other* rules are applied (never force an Alpha from identity/stereotype alone) | None — already correctly represented as a cross-cutting principle, not a missing feature | **No** |

None of the 15 items above was resolved by changing production code, config, or the taxonomy in this Day 2 task. Items 3/4/7/9 explicitly require a John decision before any taxonomy change; items 1/2/5/6/8/10 are minimal config-only edits not yet made; items 12/13/14 would require new runtime logic beyond this task's "minimal, failure-justified" fix scope; items 11/15 require no code change at all (the mechanism/design is already correct, only naming/documentation differs).
