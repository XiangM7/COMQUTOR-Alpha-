# Formal acceptance verdicts — t2-six-ticker-20261007

- Execution type: **A_REEVALUATION** (saved results re-evaluated; research output untouched) | Provider calls: **0** | Generated: 2026-10-08T02:16:58Z
- Runs root: `outputs/runs`

## 1. Rules resolved (effective_rules)

| Rule file | Path | Version | sha256 |
|---|---|---|---|
| taxonomy | comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml | alpha_taxonomy_v1 / content 1.1.0 | c6d523beaee4942c71756a3fddbb8213d4ba2f8653fded088d73031ca80f3bfa |
| labels v0.2 | comqutor_alpha/config/j2_provisional_regression_labels_v0.2.yaml | j2.provisional.v0.2 | 667262aaa15a94a5c660488493f7386a4e6ec6b8c02f1293927d887bf7920ba6 |
| labels v0.1 (dominance guard) | comqutor_alpha/config/j2_provisional_regression_labels_v0.1.yaml | j2.provisional.v0.1 | 3eec746e1f0fed0f568d77cb5a4368b5fa6d19421b305c54c6d24132cacbe9f1 |

Authority of the v0.2 label file: status `provisional_ai_predicted`, evaluation_mode `shadow`, evaluation_authority `provisional`, formal_product_owner_approval `pending`, approved_by `None`. A verdict computed under a provisional file is a provisional verdict.

### Six rule families — what each one reads and executes

| Rule family | Config source | Applies to | Execution function | Trigger | Possible results |
|---|---|---|---|---|---|
| must_detect_if_evidence_present | j2_provisional_regression_labels_v0.2.yaml: required_conflicts | declared conflict pair, per ticker | acceptance_engine.evaluate_must_detect_if_evidence_present | pair is in the ticker's required_conflicts AND B2 arbitration recorded >= 1 stance-confirmed supporting claim on EACH side (bull_supporting_evidence_count and bear_supporting_evidence_count from conflicts.json's own arbitration.candidate_evaluations[].admissibility) | pass, fail, not_applicable, not_evaluable |
| should_detect_if_supported | j2_provisional_regression_labels_v0.2.yaml: conditional_conflicts | declared conflict pair, per ticker | acceptance_engine.evaluate_should_detect_if_supported | pair is in the ticker's conditional_conflicts AND evidence is present per the same bar as must_detect_if_evidence_present AND stance_source is llm_semantic or mixed (evaluator.stance_source) -- offline runs with deterministic-baseline-only stance cannot reliably judge 'supported' and are marked pending_review instead | pass, needs_review, pending_review, not_applicable, not_evaluable |
| conditional_only | j2_provisional_regression_labels_v0.2.yaml: conditional_conflicts | declared conflict pair, per ticker | evaluation_contract.apply_v2_contract (conditional_conflict_results) | pair is in the ticker's conditional_conflicts | pass, informational_mismatch, not_evaluable |
| do_not_force | conflicts.json: conflicts[] cross-checked against arbitration.candidate_evaluations[].admissibility | every admitted conflict, per ticker (a run-wide invariant, not a per-pair rule) | acceptance_engine.evaluate_do_not_force_invariant | always evaluated when the ticker is evaluable | invariant_held, invariant_violated, not_evaluable |
| allowed_main_conflicts | j2_provisional_regression_labels_v0.2.yaml: allowed_conflicts | declared conflict pair, per ticker | evaluation_contract.apply_v2_contract (allowed_conflict_results) | pair is in the ticker's allowed_conflicts | observed_admitted, observed_candidate, not_observed, not_evaluable |
| forbidden_dominant_without_strong_evidence | j2_provisional_regression_labels_v0.1.yaml: should_not_be_dominant_without_strong_evidence (the v0.1 runtime field; the v0.2 file carries an identical copy and effective_rules() refuses the execution if the two differ) | Alpha, per ticker | evaluator.dominance_guard_flags | Alpha is listed in the ticker's should_not_be_dominant_without_strong_evidence AND reached dominant/regime_level status | review_required, not_triggered, not_evaluable |

Declared in the rule file but evaluated by **no** rule family: `{"run_bound_expectations": ["NVDA"]}`.

## 2. Verdict per ticker

| Ticker | Run | Artifacts | Stance source | formal_status | Admitted conflicts | Undeclared admitted | Vacuous PASS |
|---|---|---|---|---|---|---|---|
| NVDA | ded99ecd | pass | mixed | needs_review | A304__A601 | A304__A601 | — |
| QQQ | 0d890564 | pass | mixed | needs_review | A003__A501, A304__A601, A501__A601 | A501__A601 | — |
| SNDK | e8e0f398 | pass | mixed | needs_review | — | — | — |
| MSFT | 64568bfb | pass | mixed | needs_review | A301__A304, A304__A601 | A304__A601 | — |
| TSM | fc09821e | pass | mixed | needs_review | A101__A304, A301__A304, A304__A601 | A304__A601 | — |
| AMD | d5b60b8a | pass | mixed | needs_review | A101__A304, A301__A304, A304__A601 | A304__A601 | — |

## 3. Why each verdict is not a PASS

| Ticker | Kind | Rule family | Pair / Alpha | Detail |
|---|---|---|---|---|
| NVDA | REVIEW | should_detect_if_supported | A101__A304 | evidence present with reliable stance but pair was not admitted -- soft miss, flagged for review, never a hard fail |
| NVDA | REVIEW | should_detect_if_supported | A301__A304 | evidence present with reliable stance but pair was not admitted -- soft miss, flagged for review, never a hard fail |
| NVDA | REVIEW | undeclared_admitted_conflict | A304__A601 | review_required |
| QQQ | REVIEW | should_detect_if_supported | A001__A501 | evidence present with reliable stance but pair was not admitted -- soft miss, flagged for review, never a hard fail |
| QQQ | REVIEW | undeclared_admitted_conflict | A501__A601 | review_required |
| SNDK | REVIEW | should_detect_if_supported | A301__A304 | evidence present with reliable stance but pair was not admitted -- soft miss, flagged for review, never a hard fail |
| MSFT | REVIEW | undeclared_admitted_conflict | A304__A601 | review_required |
| TSM | REVIEW | undeclared_admitted_conflict | A304__A601 | review_required |
| AMD | REVIEW | undeclared_admitted_conflict | A304__A601 | review_required |

## 4. Rule-by-rule judgments

| Ticker | Rule family | Pair / Alpha | Observed | Verdict |
|---|---|---|---|---|
| NVDA | should_detect_if_supported | A101__A304 | evidence_present=True; stance=mixed; candidate | needs_review |
| NVDA | should_detect_if_supported | A301__A304 | evidence_present=True; stance=mixed; candidate | needs_review |
| NVDA | conditional_only | A101__A304 | candidate | informational_mismatch |
| NVDA | conditional_only | A301__A304 | candidate | informational_mismatch |
| NVDA | do_not_force | (every admitted conflict) | violations=0 | invariant_held |
| NVDA | forbidden_dominant_without_strong_evidence | 4 guarded Alphas | none dominant | not_triggered |
| QQQ | should_detect_if_supported | A001__A501 | evidence_present=True; stance=mixed; candidate | needs_review |
| QQQ | conditional_only | A001__A501 | candidate | informational_mismatch |
| QQQ | allowed_main_conflicts | A003__A501 | admitted | observed |
| QQQ | allowed_main_conflicts | A304__A601 | admitted | observed |
| QQQ | do_not_force | (every admitted conflict) | violations=0 | invariant_held |
| QQQ | forbidden_dominant_without_strong_evidence | 4 guarded Alphas | none dominant | not_triggered |
| SNDK | should_detect_if_supported | A201__A304 | evidence_present=False; stance=mixed; None | not_applicable |
| SNDK | should_detect_if_supported | A301__A304 | evidence_present=True; stance=mixed; candidate | needs_review |
| SNDK | conditional_only | A301__A304 | candidate | informational_mismatch |
| SNDK | conditional_only | A201__A304 | not_reached | informational_mismatch |
| SNDK | do_not_force | (every admitted conflict) | violations=0 | invariant_held |
| SNDK | forbidden_dominant_without_strong_evidence | 6 guarded Alphas | none dominant | not_triggered |
| MSFT | should_detect_if_supported | A102__A304 | evidence_present=False; stance=mixed; None | not_applicable |
| MSFT | conditional_only | A102__A304 | not_reached | informational_mismatch |
| MSFT | allowed_main_conflicts | A101__A304 | candidate | observed |
| MSFT | allowed_main_conflicts | A301__A304 | admitted | observed |
| MSFT | do_not_force | (every admitted conflict) | violations=0 | invariant_held |
| MSFT | forbidden_dominant_without_strong_evidence | 4 guarded Alphas | none dominant | not_triggered |
| TSM | should_detect_if_supported | A201__A304 | evidence_present=False; stance=mixed; None | not_applicable |
| TSM | should_detect_if_supported | A301__A304 | evidence_present=True; stance=mixed; admitted | pass |
| TSM | conditional_only | A301__A304 | admitted | match |
| TSM | conditional_only | A201__A304 | not_reached | informational_mismatch |
| TSM | allowed_main_conflicts | A101__A304 | admitted | observed |
| TSM | do_not_force | (every admitted conflict) | violations=0 | invariant_held |
| TSM | forbidden_dominant_without_strong_evidence | 5 guarded Alphas | none dominant | not_triggered |
| AMD | should_detect_if_supported | A101__A304 | evidence_present=True; stance=mixed; admitted | pass |
| AMD | should_detect_if_supported | A201__A304 | evidence_present=False; stance=mixed; None | not_applicable |
| AMD | conditional_only | A101__A304 | admitted | match |
| AMD | conditional_only | A201__A304 | not_reached | informational_mismatch |
| AMD | allowed_main_conflicts | A301__A304 | admitted | observed |
| AMD | do_not_force | (every admitted conflict) | violations=0 | invariant_held |
| AMD | forbidden_dominant_without_strong_evidence | 5 guarded Alphas | none dominant | not_triggered |

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

| Ticker | Declared pairs | With evidence on both sides | Admitted (do_not_force) | Dominance guards triggered/declared | Reading |
|---|---|---|---|---|---|
| NVDA | 2 | 2 | 1 | 0/4 |  |
| QQQ | 3 | 3 | 3 | 0/4 |  |
| SNDK | 2 | 1 | 0 | 0/6 |  |
| MSFT | 3 | 2 | 2 | 0/4 |  |
| TSM | 3 | 2 | 3 | 0/5 |  |
| AMD | 3 | 2 | 3 | 0/5 |  |

