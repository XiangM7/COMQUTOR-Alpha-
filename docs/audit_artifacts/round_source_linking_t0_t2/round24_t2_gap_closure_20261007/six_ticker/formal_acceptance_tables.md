# Formal acceptance verdicts — round24-six-ticker

- Execution type: **A_REEVALUATION** (saved results re-evaluated; research output untouched) | Provider calls: **0** | Generated: 2026-10-08T06:02:51Z
- Runs root: `outputs/runs`

## 1. Rules resolved (effective_rules)

| Rule file | Path | Version | sha256 |
|---|---|---|---|
| taxonomy | comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml | alpha_taxonomy_v1 / content 1.1.0 | c6d523beaee4942c71756a3fddbb8213d4ba2f8653fded088d73031ca80f3bfa |
| labels v0.2 | comqutor_alpha/config/j2_provisional_regression_labels_v0.2.yaml | j2.provisional.v0.2 | 667262aaa15a94a5c660488493f7386a4e6ec6b8c02f1293927d887bf7920ba6 |
| labels v0.1 (dominance guard) | comqutor_alpha/config/j2_provisional_regression_labels_v0.1.yaml | j2.provisional.v0.1 | 3eec746e1f0fed0f568d77cb5a4368b5fa6d19421b305c54c6d24132cacbe9f1 |
| Gold v0.2 operational contract | docs/audit_artifacts/v0_2_gold_operational_contract.json | gold_operational_contract.v0.2 / v0.2 / FROZEN_GOLD_V0_2 | e2df7139e19ec998afc6335caf4d53528dd3f4356a46d4e9a88d9d04b520000f |
| frozen evidence trigger matrix | docs/audit_artifacts/v0_2_evidence_trigger_matrix.json | v0.2.evidence_trigger_matrix.v1 | 3e8e7402803632198b01c2a08a98929031929cc4b909927dc7e475d37b5d22a1 |

Authority of the v0.2 label file: status `provisional_ai_predicted`, evaluation_mode `shadow`, evaluation_authority `provisional`, formal_product_owner_approval `pending`, approved_by `None`. A verdict computed under a provisional file is a provisional verdict.

Gold contract integrity: sha256 equals the one the freeze manifest recorded (`docs/audit_artifacts/v0_2_gold_freeze_manifest.json`): **True**. Trigger matrix equals its frozen hash: **True**; written against the same contract: **True**. Matrix-bound runs: AMD 949f685a, MSFT 43472ace, NVDA 57d7b4c4, QQQ f88c8956, SNDK e8e0f398, TSM dfc7ceb3. Markdown companion equals its frozen hash: **False** (rewritten on John's instruction of 2026-09-15 (final submission cleanup: a short John-facing definition of the six semantics); the rule records live in the JSON, which is byte-identical to the frozen file). Detection authority: run_audit.json -> activation_summary.per_alpha[alpha_id].level, read as regression_report_v3._detected_alphas does; detected levels ['active', 'dominant', 'regime_level'].

### Gold contract rules in effect, and the John decision each one implements

| Rule | Ticker | Family | Blocking | Alpha / allowed pairs | Trigger source | Approval basis |
|---|---|---|---|---|---|---|
| NVDA-A101-AI-GROWTH | NVDA | must_detect_if_evidence_present | yes | A101 | frozen evidence trigger matrix, for run 57d7b4c4-dbb9-4134-b962-ee2a873941cc only; any other run -> NOT_EVALUABLE | John's final decisions for the Gold v0.2 freeze (Step 2), 2026-09-10T21:02:57Z, section 4: 'A101: must_detect_if_evidence_present'; section 2: NVDA is Formal Gold, blocking = true \|\| John's Gold v0.2 operationalization instruction (Step 1), 2026-09-10T20:43:46Z, section 8.A (mapping, condition, 'do NOT force A101 when such evidence is absent') \|\| v0_2_gold_freeze_manifest.json (contract JSON sha256 e2df7139e19e...; 9 review items resolved, none remaining) |
| NVDA-A304-VALUATION-RISK | NVDA | must_detect_if_evidence_present | yes | A304 | frozen evidence trigger matrix, for run 57d7b4c4-dbb9-4134-b962-ee2a873941cc only; any other run -> NOT_EVALUABLE | John's final decisions for the Gold v0.2 freeze (Step 2), 2026-09-10T21:02:57Z, section 4: 'A304: must_detect_if_evidence_present'; section 2: NVDA is Formal Gold, blocking = true \|\| John's Gold v0.2 operationalization instruction (Step 1), 2026-09-10T20:43:46Z, section 8.C \|\| v0_2_gold_freeze_manifest.json (contract JSON sha256 e2df7139e19e...; 9 review items resolved, none remaining) |
| NVDA-GROWTH-VS-VALUATION-CONFLICT | NVDA | conditional_only | yes | A101, A301, A304 / A101__A304, A301__A304 | frozen evidence trigger matrix, for run 57d7b4c4-dbb9-4134-b962-ee2a873941cc only; any other run -> NOT_EVALUABLE | John's final decisions for the Gold v0.2 freeze (Step 2), 2026-09-10T21:02:57Z, section 4: composite allowed pairs A101__A304 and A301__A304 'only when both relevant evidence sides are present; do not force a conflict if only one side is supported' \|\| Frozen-gold vs frozen-trigger comparison protocol (Step 4), 2026-09-10T21:52:47Z, section 13: any allowed evidence-supported conflict admitted -> PASS; none admitted -> REVIEW with adjudication; outside the allowed family -> FAIL or REVIEW \|\| v0_2_john_frozen_gold_baseline.yaml (authority JOHN_WRITTEN_V0_2_BASELINE): allowed_main_conflicts NVDA = A101__A304, A301__A304 |
| MSFT-A102-DIRECT-INFERENCE-TRIGGER | MSFT | must_detect_if_evidence_present | no | A102 | frozen evidence trigger matrix, for run 43472ace-454f-4c69-892c-adca91c25be7 only; any other run -> NOT_EVALUABLE | John's final decisions for the Gold v0.2 freeze (Step 2), 2026-09-10T21:02:57Z, section 1.G (final decision): DIRECT_INFERENCE_TRIGGER -> must_detect_if_evidence_present -> A102; section 2: MSFT is Silver, blocking = false \|\| John's Gold v0.2 operationalization instruction (Step 1), 2026-09-10T20:43:46Z, section 11.B (the 'must/should' wording that decision G resolved) \|\| v0_2_gold_freeze_manifest.json (contract JSON sha256 e2df7139e19e...; 9 review items resolved, none remaining) |
| AMD-AI-GROWTH-VS-VALUATION | AMD | conditional_only | no | A101, A201, A301, A304 / A101__A304, A301__A304 | frozen evidence trigger matrix, for run 949f685a-3945-4fd0-b7b9-362b37c90721 only; any other run -> NOT_EVALUABLE | John's Gold v0.2 operationalization instruction (Step 1), 2026-09-10T20:43:46Z, section 13 (composite; 'do not force either pair'; Silver, non-blocking) \|\| Frozen-gold vs frozen-trigger comparison protocol (Step 4), 2026-09-10T21:52:47Z, sections 13 and 20 \|\| v0_2_john_frozen_gold_baseline.yaml (authority JOHN_WRITTEN_V0_2_BASELINE): allowed_main_conflicts AMD = A101__A304, A201__A304, A301__A304 (the baseline controls; the contract lists only A101__A304 and A301__A304) |

Contract rules NOT executed by this entry (14; nothing is evaluated or implied for them): `NVDA-A301-FUNDAMENTAL-GROWTH`, `NVDA-SUPPORTING-STRUCTURES`, `QQQ-A001-RATE-CUT-CYCLE`, `QQQ-A003-LIQUIDITY-EXPANSION`, `QQQ-A304-VALUATION-RISK`, `QQQ-A501-RECESSION-RISK`, `QQQ-A601-NARRATIVE-MOMENTUM`, `QQQ-ETF-CONTEXT-CONTROL`, `SNDK-A201-SEMICONDUCTOR-CYCLE`, `SNDK-ANTI-OVER-AI-CONTROL`, `MSFT-A101-ENTERPRISE-AI-CONDITIONAL`, `MSFT-A102-INDIRECT-INFERENCE-SUPPORT`, `MSFT-CAPEX-BURDEN-CONDITIONAL`, `TSM-AI-TO-FOUNDRY-TRANSMISSION`.

### Six rule families — what each one reads and executes

| Rule family | Config source | Applies to | Execution function | Trigger | Possible results |
|---|---|---|---|---|---|
| must_detect_if_evidence_present | v0_2_gold_operational_contract.json: ALPHA_HIT rules MSFT-A102-DIRECT-INFERENCE-TRIGGER, NVDA-A101-AI-GROWTH, NVDA-A304-VALUATION-RISK (Alpha layer, John's frozen Gold v0.2 contract); j2_provisional_regression_labels_v0.2.yaml: required_conflicts (conflict-pair layer) | Alpha, per contract rule and ticker (Alpha layer); declared conflict pair, per ticker (pair layer) | gold_contract_rules.evaluate_alpha_rule (Alpha layer); acceptance_engine.evaluate_must_detect_if_evidence_present (pair layer) | Alpha layer: the frozen evidence-trigger matrix says PRESENT for the rule AND the evaluated run is the run the matrix is bound to (for any other run the trigger is NOT_EVALUABLE: no approved executable method determines it and a historical state is never carried over). Pair layer: the pair is in the ticker's required_conflicts | pass, fail, not_applicable, not_triggered, needs_review, not_evaluable |
| should_detect_if_supported | j2_provisional_regression_labels_v0.2.yaml: conditional_conflicts (conflict-pair reading, DIAGNOSTIC ONLY). The contract defines this family for Alphas (its should_detect rules are not executed by this entry) | declared conflict pair, per ticker | acceptance_engine.evaluate_should_detect_if_supported (diagnostic) | pair is in the ticker's conditional_conflicts AND at least one stance-confirmed supporting claim is recorded on each side AND stance_source is llm_semantic or mixed (evaluator.stance_source) -- offline runs with deterministic-baseline-only stance cannot reliably judge 'supported' and are marked pending_review instead | pass, needs_review, pending_review, not_applicable, not_evaluable |
| conditional_only | v0_2_gold_operational_contract.json: COMPOSITE_STRUCTURE_HIT rules AMD-AI-GROWTH-VS-VALUATION, NVDA-GROWTH-VS-VALUATION-CONFLICT (John's frozen contract); j2_provisional_regression_labels_v0.2.yaml: conditional_conflicts (informational reading) | composite growth-vs-valuation structure, per contract rule and ticker; declared conflict pair, per ticker | gold_contract_rules.evaluate_composite_rule (composites: ANY ONE allowed pair admitted satisfies the rule); evaluation_contract.apply_v2_contract (conditional_conflict_results) | composites: the frozen trigger is PRESENT for the bound run (otherwise NOT_EVALUABLE). Pairs: the pair is in the ticker's conditional_conflicts | pass, needs_review, not_triggered, informational_mismatch, not_evaluable |
| do_not_force | conflicts.json: conflicts[] cross-checked against arbitration.candidate_evaluations[].admissibility | every admitted conflict, per ticker (a run-wide invariant, not a per-pair rule) | acceptance_engine.evaluate_do_not_force_invariant | always evaluated when the ticker is evaluable | invariant_held, invariant_violated, not_evaluable |
| allowed_main_conflicts | j2_provisional_regression_labels_v0.2.yaml: allowed_conflicts | declared conflict pair, per ticker | evaluation_contract.apply_v2_contract (allowed_conflict_results) | pair is in the ticker's allowed_conflicts | observed_admitted, observed_candidate, not_observed, not_evaluable |
| forbidden_dominant_without_strong_evidence | j2_provisional_regression_labels_v0.1.yaml: should_not_be_dominant_without_strong_evidence (the v0.1 runtime field; the v0.2 file carries an identical copy and effective_rules() refuses the execution if the two differ) | Alpha, per ticker | evaluator.dominance_guard_flags | Alpha is listed in the ticker's should_not_be_dominant_without_strong_evidence AND reached dominant/regime_level status | review_required, not_triggered, not_evaluable |

### Execution status of each rule family, by scope

| Rule family | Scope | Status | Contract rules | Limits / reading |
|---|---|---|---|---|
| must_detect_if_evidence_present | alpha_layer_contract | aligned_execution | MSFT-A102-DIRECT-INFERENCE-TRIGGER, NVDA-A101-AI-GROWTH, NVDA-A304-VALUATION-RISK | the trigger is established only for the run the frozen matrix is bound to; for every other run the rule is not_evaluable |
| must_detect_if_evidence_present | conflict_pair_label | aligned_execution | — | only a record that satisfies every B2 condition and is still not admitted is a miss; no ticker declares a required pair today |
| should_detect_if_supported | alpha_layer_contract | not_in_effect | MSFT-A102-INDIRECT-INFERENCE-SUPPORT, NVDA-A301-FUNDAMENTAL-GROWTH, NVDA-SUPPORTING-STRUCTURES, QQQ-A001-RATE-CUT-CYCLE, QQQ-A003-LIQUIDITY-EXPANSION, QQQ-A501-RECESSION-RISK, QQQ-A601-NARRATIVE-MOMENTUM, SNDK-A201-SEMICONDUCTOR-CYCLE |  |
| should_detect_if_supported | conflict_pair_label | diagnostic_only | — | no approval basis: the contract defines should_detect for Alphas; the baseline lists these pairs as allowed, never mandatory |
| conditional_only | conflict_structure_contract | aligned_execution | AMD-AI-GROWTH-VS-VALUATION, NVDA-GROWTH-VS-VALUATION-CONFLICT | the trigger is established only for the run the frozen matrix is bound to; for every other run the rule is not_evaluable |
| conditional_only | conflict_pair_label | aligned_execution | — | informational mismatch only |
| conditional_only | alpha_layer_contract | not_in_effect | MSFT-A101-ENTERPRISE-AI-CONDITIONAL, MSFT-CAPEX-BURDEN-CONDITIONAL, NVDA-A301-FUNDAMENTAL-GROWTH, QQQ-A001-RATE-CUT-CYCLE, QQQ-A003-LIQUIDITY-EXPANSION, QQQ-A304-VALUATION-RISK, QQQ-A501-RECESSION-RISK, SNDK-A201-SEMICONDUCTOR-CYCLE, TSM-AI-TO-FOUNDRY-TRANSMISSION |  |
| do_not_force | conflict_invariant | aligned_execution | — | every admitted conflict has a B2-admitted arbitration record |
| do_not_force | alpha_layer_contract | not_in_effect | — | the contract defines it as a cross-cutting constraint, not a standalone rule |
| allowed_main_conflicts | conflict_pair_label | aligned_execution | — | legal structures, never mandatory outputs: a pair's absence raises no review and no failure; an admitted pair declared nowhere is routed to review |
| forbidden_dominant_without_strong_evidence | label_dominance_guard | aligned_execution | — | its guarded Alphas are the label's own, not the scope of the contract's two negative-control rules |
| forbidden_dominant_without_strong_evidence | alpha_layer_contract | not_in_effect | QQQ-ETF-CONTEXT-CONTROL, SNDK-ANTI-OVER-AI-CONTROL |  |

Declared in the label file but **not a rule** (an unapproved, run-bound historical observation; reported unchanged, decides no verdict): NVDA: reference run `e3eb3909-3744-4a02-9b32-b225cf6ef665`, observed main conflict `A301__A304`, approval: none: the label file is provisional / shadow / approval pending and states that no formal approval exists for this run.

## 2. Verdict per ticker

| Ticker | Run | Artifacts | Stance source | formal_status | Admitted conflicts | Undeclared admitted | Contract release impact | Vacuous PASS |
|---|---|---|---|---|---|---|---|---|
| NVDA | ded99ecd | pass | mixed | needs_review | A304__A601 | A304__A601 | unresolved (3 contract rules executed, 2 not executed) | — |
| QQQ | 0d890564 | pass | mixed | needs_review | A003__A501, A304__A601, A501__A601 | A501__A601 | no_blocker_among_executed_rules (0 contract rules executed, 6 not executed) | — |
| SNDK | e8e0f398 | pass | mixed | pass | — | — | no_blocker_among_executed_rules (0 contract rules executed, 2 not executed) | — |
| MSFT | 64568bfb | pass | mixed | needs_review | A301__A304, A304__A601 | A304__A601 | no_blocker_among_executed_rules (1 contract rules executed, 3 not executed) | — |
| TSM | fc09821e | pass | mixed | needs_review | A101__A304, A301__A304, A304__A601 | A304__A601 | no_blocker_among_executed_rules (0 contract rules executed, 1 not executed) | — |
| AMD | d5b60b8a | pass | mixed | needs_review | A101__A304, A301__A304, A304__A601 | A304__A601 | no_blocker_among_executed_rules (1 contract rules executed, 0 not executed) | — |

## 3. Why each verdict is not a PASS

| Ticker | Kind | Rule family | Rule / pair / Alpha | Blocking rule | Detail |
|---|---|---|---|---|---|
| NVDA | REVIEW | must_detect_if_evidence_present | NVDA-A101-AI-GROWTH | yes | evidence trigger not established: the frozen trigger matrix is bound to NVDA run 57d7b4c4-dbb9-4134-b962-ee2a873941cc; this is run ded99ecd-a186-4a90-859e-0f1a0efa43db. No approved, executable evidence-determination method exists for another run, and the historical trigger state is not carried over to it |
| NVDA | REVIEW | must_detect_if_evidence_present | NVDA-A304-VALUATION-RISK | yes | evidence trigger not established: the frozen trigger matrix is bound to NVDA run 57d7b4c4-dbb9-4134-b962-ee2a873941cc; this is run ded99ecd-a186-4a90-859e-0f1a0efa43db. No approved, executable evidence-determination method exists for another run, and the historical trigger state is not carried over to it |
| NVDA | REVIEW | conditional_only | NVDA-GROWTH-VS-VALUATION-CONFLICT | yes | evidence trigger not established: the frozen trigger matrix is bound to NVDA run 57d7b4c4-dbb9-4134-b962-ee2a873941cc; this is run ded99ecd-a186-4a90-859e-0f1a0efa43db. No approved, executable evidence-determination method exists for another run, and the historical trigger state is not carried over to it |
| NVDA | REVIEW | undeclared_admitted_conflict | A304__A601 | — | review_required |
| QQQ | REVIEW | undeclared_admitted_conflict | A501__A601 | — | review_required |
| MSFT | REVIEW | must_detect_if_evidence_present | MSFT-A102-DIRECT-INFERENCE-TRIGGER | no | evidence trigger not established: the frozen trigger matrix is bound to MSFT run 43472ace-454f-4c69-892c-adca91c25be7; this is run 64568bfb-fe0c-453c-9872-831a8dc339a0. No approved, executable evidence-determination method exists for another run, and the historical trigger state is not carried over to it |
| MSFT | REVIEW | undeclared_admitted_conflict | A304__A601 | — | review_required |
| TSM | REVIEW | undeclared_admitted_conflict | A304__A601 | — | review_required |
| AMD | REVIEW | conditional_only | AMD-AI-GROWTH-VS-VALUATION | no | evidence trigger not established: the frozen trigger matrix is bound to AMD run 949f685a-3945-4fd0-b7b9-362b37c90721; this is run d5b60b8a-66b8-44c1-9f55-ee345e58c48d. No approved, executable evidence-determination method exists for another run, and the historical trigger state is not carried over to it |
| AMD | REVIEW | undeclared_admitted_conflict | A304__A601 | — | review_required |

## 4. Rule-by-rule judgments

| Ticker | Rule family | Pair / Alpha | Observed | Verdict |
|---|---|---|---|---|
| NVDA | should_detect_if_supported (conflict pair, DIAGNOSTIC ONLY) | A101__A304 | evidence_present=True; stance=mixed; B2: candidate ['BULL_SCORE_BELOW_THRESHOLD'] | needs_review (decides nothing) |
| NVDA | should_detect_if_supported (conflict pair, DIAGNOSTIC ONLY) | A301__A304 | evidence_present=True; stance=mixed; B2: candidate ['NO_BULL_TICKER_SPECIFIC_SUPPORT'] | needs_review (decides nothing) |
| NVDA | conditional_only | A101__A304 | candidate | informational_mismatch |
| NVDA | conditional_only | A301__A304 | candidate | informational_mismatch |
| NVDA | do_not_force | (every admitted conflict) | violations=0 | invariant_held |
| NVDA | forbidden_dominant_without_strong_evidence | 4 guarded Alphas | none dominant | not_triggered |
| QQQ | should_detect_if_supported (conflict pair, DIAGNOSTIC ONLY) | A001__A501 | evidence_present=True; stance=mixed; B2: candidate ['BULL_SCORE_BELOW_THRESHOLD', 'INSUFFICIENT_BULL_SUPPORTING_EVIDENCE', 'NO_BULL_TICKER_SPECIFIC_SUPPORT'] | needs_review (decides nothing) |
| QQQ | conditional_only | A001__A501 | candidate | informational_mismatch |
| QQQ | allowed_main_conflicts | A003__A501 | admitted | observed |
| QQQ | allowed_main_conflicts | A304__A601 | admitted | observed |
| QQQ | do_not_force | (every admitted conflict) | violations=0 | invariant_held |
| QQQ | forbidden_dominant_without_strong_evidence | 4 guarded Alphas | none dominant | not_triggered |
| SNDK | should_detect_if_supported (conflict pair, DIAGNOSTIC ONLY) | A201__A304 | evidence_present=False; stance=mixed; B2: None | not_applicable (decides nothing) |
| SNDK | should_detect_if_supported (conflict pair, DIAGNOSTIC ONLY) | A301__A304 | evidence_present=True; stance=mixed; B2: candidate ['BULL_SCORE_BELOW_THRESHOLD', 'NO_BULL_TICKER_SPECIFIC_SUPPORT', 'NO_BEAR_TICKER_SPECIFIC_SUPPORT'] | needs_review (decides nothing) |
| SNDK | conditional_only | A301__A304 | candidate | informational_mismatch |
| SNDK | conditional_only | A201__A304 | not_reached | informational_mismatch |
| SNDK | do_not_force | (every admitted conflict) | violations=0 | invariant_held |
| SNDK | forbidden_dominant_without_strong_evidence | 6 guarded Alphas | none dominant | not_triggered |
| MSFT | should_detect_if_supported (conflict pair, DIAGNOSTIC ONLY) | A102__A304 | evidence_present=False; stance=mixed; B2: None | not_applicable (decides nothing) |
| MSFT | conditional_only | A102__A304 | not_reached | informational_mismatch |
| MSFT | allowed_main_conflicts | A101__A304 | candidate | observed |
| MSFT | allowed_main_conflicts | A301__A304 | admitted | observed |
| MSFT | do_not_force | (every admitted conflict) | violations=0 | invariant_held |
| MSFT | forbidden_dominant_without_strong_evidence | 4 guarded Alphas | none dominant | not_triggered |
| TSM | should_detect_if_supported (conflict pair, DIAGNOSTIC ONLY) | A201__A304 | evidence_present=False; stance=mixed; B2: None | not_applicable (decides nothing) |
| TSM | should_detect_if_supported (conflict pair, DIAGNOSTIC ONLY) | A301__A304 | evidence_present=True; stance=mixed; B2: admitted | pass (decides nothing) |
| TSM | conditional_only | A301__A304 | admitted | match |
| TSM | conditional_only | A201__A304 | not_reached | informational_mismatch |
| TSM | allowed_main_conflicts | A101__A304 | admitted | observed |
| TSM | do_not_force | (every admitted conflict) | violations=0 | invariant_held |
| TSM | forbidden_dominant_without_strong_evidence | 5 guarded Alphas | none dominant | not_triggered |
| AMD | should_detect_if_supported (conflict pair, DIAGNOSTIC ONLY) | A101__A304 | evidence_present=True; stance=mixed; B2: admitted | pass (decides nothing) |
| AMD | should_detect_if_supported (conflict pair, DIAGNOSTIC ONLY) | A201__A304 | evidence_present=False; stance=mixed; B2: None | not_applicable (decides nothing) |
| AMD | conditional_only | A101__A304 | admitted | match |
| AMD | conditional_only | A201__A304 | not_reached | informational_mismatch |
| AMD | allowed_main_conflicts | A301__A304 | admitted | observed |
| AMD | do_not_force | (every admitted conflict) | violations=0 | invariant_held |
| AMD | forbidden_dominant_without_strong_evidence | 5 guarded Alphas | none dominant | not_triggered |

### 4a. Gold contract rules (Alpha layer and composites): four facts kept apart

| Ticker | Run | Rule | Blocking | Evidence trigger | Alpha identified / activation level (score) | Contract requirement met | Result | Blocks release | Reason |
|---|---|---|---|---|---|---|---|---|---|
| NVDA | ded99ecd | NVDA-A101-AI-GROWTH | yes | NOT_EVALUABLE (RUN_NOT_BOUND_TO_FROZEN_TRIGGER_MATRIX; matrix bound to run 57d7b4c4) | A101: identified (21 claims); level candidate (48.5501) | no | NOT_EVALUABLE (not_evaluable) | no | RUN_NOT_BOUND_TO_FROZEN_TRIGGER_MATRIX |
| NVDA | ded99ecd | NVDA-A304-VALUATION-RISK | yes | NOT_EVALUABLE (RUN_NOT_BOUND_TO_FROZEN_TRIGGER_MATRIX; matrix bound to run 57d7b4c4) | A304: identified (76 claims); level dominant (71.7302) | yes | NOT_EVALUABLE (not_evaluable) | no | RUN_NOT_BOUND_TO_FROZEN_TRIGGER_MATRIX |
| NVDA | ded99ecd | NVDA-GROWTH-VS-VALUATION-CONFLICT | yes | NOT_EVALUABLE (RUN_NOT_BOUND_TO_FROZEN_TRIGGER_MATRIX; matrix bound to run 57d7b4c4) | allowed family ['A101__A304', 'A301__A304']; admitted in family []; outside ['A304__A601']; components: A101: identified (21 claims); level candidate (48.5501) \| A301: identified (52 claims); level dominant (74.214) \| A304: identified (76 claims); level dominant (71.7302) | — | NOT_EVALUABLE (not_evaluable) | no | RUN_NOT_BOUND_TO_FROZEN_TRIGGER_MATRIX |
| MSFT | 64568bfb | MSFT-A102-DIRECT-INFERENCE-TRIGGER | no | NOT_EVALUABLE (RUN_NOT_BOUND_TO_FROZEN_TRIGGER_MATRIX; matrix bound to run 43472ace) | A102: identified (6 claims); level candidate (41.9468) | no | NOT_EVALUABLE (not_evaluable) | no | RUN_NOT_BOUND_TO_FROZEN_TRIGGER_MATRIX |
| AMD | d5b60b8a | AMD-AI-GROWTH-VS-VALUATION | no | NOT_EVALUABLE (RUN_NOT_BOUND_TO_FROZEN_TRIGGER_MATRIX; matrix bound to run 949f685a) | allowed family ['A101__A304', 'A201__A304', 'A301__A304']; admitted in family ['A101__A304', 'A301__A304']; outside ['A304__A601']; components: A101: identified (15 claims); level active (58.5954) \| A201: identified (56 claims); level active (62.5918) \| A301: identified (40 claims); level active (65.2271) \| A304: identified (97 claims); level dominant (81.5323) | — | NOT_EVALUABLE (not_evaluable) | no | RUN_NOT_BOUND_TO_FROZEN_TRIGGER_MATRIX |

### 4b. Diagnostic findings — reported with their source, deciding nothing

| Ticker | Rule family | Pair | Diagnostic result | B2 reason codes | Authority | Source |
|---|---|---|---|---|---|---|
| NVDA | should_detect_if_supported | A101__A304 | needs_review | BULL_SCORE_BELOW_THRESHOLD | implementation_only_unapproved; decides_formal_status=False | comqutor_alpha/config/j2_provisional_regression_labels_v0.2.yaml: conditional_conflicts |
| NVDA | should_detect_if_supported | A301__A304 | needs_review | NO_BULL_TICKER_SPECIFIC_SUPPORT | implementation_only_unapproved; decides_formal_status=False | comqutor_alpha/config/j2_provisional_regression_labels_v0.2.yaml: conditional_conflicts |
| QQQ | should_detect_if_supported | A001__A501 | needs_review | BULL_SCORE_BELOW_THRESHOLD, INSUFFICIENT_BULL_SUPPORTING_EVIDENCE, NO_BULL_TICKER_SPECIFIC_SUPPORT | implementation_only_unapproved; decides_formal_status=False | comqutor_alpha/config/j2_provisional_regression_labels_v0.2.yaml: conditional_conflicts |
| SNDK | should_detect_if_supported | A301__A304 | needs_review | BULL_SCORE_BELOW_THRESHOLD, NO_BULL_TICKER_SPECIFIC_SUPPORT, NO_BEAR_TICKER_SPECIFIC_SUPPORT | implementation_only_unapproved; decides_formal_status=False | comqutor_alpha/config/j2_provisional_regression_labels_v0.2.yaml: conditional_conflicts |

## 5. John's frozen allowed_main_conflicts × what the saved runs showed

| Ticker | Pair | Carried by the rule file as | Observed in the saved run |
|---|---|---|---|
| NVDA | A101__A304 | conditional_conflicts | candidate |
| NVDA | A301__A304 | conditional_conflicts | candidate |
| QQQ | A001__A501 | conditional_conflicts | candidate |
| QQQ | A003__A501 | allowed_conflicts | admitted |
| QQQ | A304__A601 | allowed_conflicts | admitted |
| SNDK | A201__A304 | conditional_conflicts | not_reached |
| SNDK | A301__A304 | conditional_conflicts | candidate |
| MSFT | A102__A304 | conditional_conflicts | not_reached |
| MSFT | A101__A304 | allowed_conflicts | candidate |
| MSFT | A301__A304 | allowed_conflicts | admitted |
| TSM | A201__A304 | conditional_conflicts | not_reached |
| TSM | A301__A304 | conditional_conflicts | admitted |
| TSM | A101__A304 | allowed_conflicts | admitted |
| AMD | A101__A304 | conditional_conflicts | admitted |
| AMD | A201__A304 | conditional_conflicts | not_reached |
| AMD | A301__A304 | allowed_conflicts | admitted |

## 6. Coverage — what each PASS actually exercised

| Ticker | Declared pairs | With supporting evidence on both sides (descriptive) | Admitted (do_not_force) | Dominance guards triggered/declared | Contract rules with a verdict / executed | Contract rules not executed for this ticker | Reading |
|---|---|---|---|---|---|---|---|
| NVDA | 2 | 2 | 1 | 0/4 | 0/3 (not evaluable: 3) | NVDA-A301-FUNDAMENTAL-GROWTH, NVDA-SUPPORTING-STRUCTURES |  |
| QQQ | 3 | 3 | 3 | 0/4 | 0/0 (not evaluable: 0) | QQQ-A001-RATE-CUT-CYCLE, QQQ-A003-LIQUIDITY-EXPANSION, QQQ-A304-VALUATION-RISK, QQQ-A501-RECESSION-RISK, QQQ-A601-NARRATIVE-MOMENTUM, QQQ-ETF-CONTEXT-CONTROL |  |
| SNDK | 2 | 1 | 0 | 0/6 | 0/0 (not evaluable: 0) | SNDK-A201-SEMICONDUCTOR-CYCLE, SNDK-ANTI-OVER-AI-CONTROL | this PASS covers the label-based rule families and the contract rules in contract_rule_results; it says nothing about the contract rules this entry does not execute for the ticker (SNDK-A201-SEMICONDUCTOR-CYCLE, SNDK-ANTI-OVER-AI-CONTROL) |
| MSFT | 3 | 2 | 2 | 0/4 | 0/1 (not evaluable: 1) | MSFT-A101-ENTERPRISE-AI-CONDITIONAL, MSFT-A102-INDIRECT-INFERENCE-SUPPORT, MSFT-CAPEX-BURDEN-CONDITIONAL |  |
| TSM | 3 | 2 | 3 | 0/5 | 0/0 (not evaluable: 0) | TSM-AI-TO-FOUNDRY-TRANSMISSION |  |
| AMD | 3 | 2 | 3 | 0/5 | 0/1 (not evaluable: 1) | — |  |

