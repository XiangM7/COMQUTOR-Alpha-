# T2 — John's seven required scenarios → the tests that prove them

Source: COMQUTOR Alpha 下一轮开发任务单, 四、T2, 3. 必须提供的自动测试 (7 scenarios)

> Every test below runs offline with zero Provider calls. Its `fixture` field says what its inputs are, and none of them is counted as real market validation except `historical_saved_runs`, which reads the repository's saved runs read-only and says what those runs show -- not that a market was validated.

Fixture kinds: **synthetic** = hand-made inputs to one rule function or to the engine; **real_detector_and_b2_on_synthetic_inputs** = the production conflict detector and B2 gate run on hand-made activation entries and claims; **controlled_modification** = a record or rule file edited on purpose to a state the production code cannot produce; it proves the check can detect an anomaly, never that production produced it; **real_pipeline_synthetic_text** = run_research_request end to end with hand-written report text and a faked data boundary; **historical_saved_runs** = the repository's saved runs under outputs/runs, read-only

Coverage statuses: **covered** = proven at every layer the scenario's sentence involves, with no stated gap; **covered_with_limits** = proven, with a limit the `limits` field states and the report repeats; **not_covered** = no test proves it

The map is checked by `tests/test_t2_scenario_map_points_at_real_tests.py` (every cited test exists; a scenario is only `covered` when something beyond hand-made records proves it). The *Outcome* column below is read from the JUnit files of this round's runs.

## 1. 有明确支持证据，却漏掉必须识别的 Alpha → 验收能够发现漏检

**Coverage: covered_with_limits**

| Kind | Fixture | Test | Outcome | What it proves |
|---|---|---|---|---|
| rule function | synthetic | `tests/test_t2_gold_contract_alpha_rules.py::test_trigger_present_and_the_alpha_identified_but_below_the_required_level_is_a_fail_that_is_not_written_as_not_identified` | passed | Alpha layer (John's frozen contract): trigger PRESENT for the bound run + the Alpha identified but below the required level -> FAIL; identification, level, requirement and trigger recorded apart |
| rule function | synthetic | `tests/test_t2_gold_contract_alpha_rules.py::test_trigger_present_and_the_alpha_never_classified_with_a_complete_classification_is_a_fail_recorded_as_not_identified` | passed | Alpha layer: no claim classified to the Alpha and the classification complete -> FAIL, recorded as not identified |
| rule function | synthetic | `tests/test_t2_gold_contract_alpha_rules.py::test_a_technically_unfinished_classification_is_never_written_as_a_valid_none_and_the_miss_is_not_asserted` | passed | Alpha layer: unavailable classification is not a valid NONE -> not_evaluable, the miss is not asserted |
| final status | synthetic | `tests/test_t2_gold_contract_alpha_rules.py::test_the_ticker_verdict_consumes_the_severity_the_contract_fixed` | passed | the ticker verdict: NVDA-A101 missed -> fail and blocks release; MSFT-A102 missed -> fail, blocks nothing (non-blocking) |
| rule function | controlled_modification | `tests/test_t2_conflict_semantics_real_b2.py::test_controlled_modification_a_record_that_meets_every_condition_but_is_not_admitted_is_a_missed_required_conflict` | passed | conflict-pair layer: the real control record, hand-edited to 'meets every B2 condition but not admitted' -> FAIL (B2 cannot produce this record) |
| final status | controlled_modification | `tests/test_t2_rule_config_errors.py::test_scenario_a_a_b2_record_with_no_rejection_reason_that_is_not_admitted_is_a_formal_fail` | passed | the same pair-layer omission changes the FINAL formal_status to fail and names the pair |
| upstream real code | historical_saved_runs | `tests/test_t2_gold_contract_alpha_rules.py::test_on_the_runs_the_matrix_is_bound_to_the_executor_reproduces_Johns_step_4_rows` | passed | on NVDA 57d7b4c4, MSFT 43472ace and AMD 949f685a the executor reproduces John's own Step-4 rule rows, including the MSFT-A102 miss (FAIL, non-blocking) |
| rule function | controlled_modification | `tests/test_t2_gold_contract_alpha_rules.py::test_controlled_modification_an_allowed_pair_that_meets_every_b2_condition_yet_is_not_admitted_is_a_deterministic_violation` | passed | composite layer (John's Step-4 section 13 exception): the trigger is PRESENT and an allowed pair's own B2 record lists no rejection reason yet the pair is not admitted -> FAIL at the contract's severity (NVDA blocking, AMD non-blocking); an admitted allowed pair still satisfies the composite |
| final status | controlled_modification | `tests/test_t2_gold_contract_alpha_rules.py::test_through_the_unified_entry_a_composite_violation_is_a_blocking_failure_of_the_ticker` | passed | the same composite violation changes the ticker's FINAL formal_status to fail and the release block to blocked |

*Limit:* Alpha layer: executed for the three must_detect rules John froze (NVDA-A101, NVDA-A304 blocking; MSFT-A102 non-blocking), but the evidence trigger exists only for the run the frozen trigger matrix is bound to (one run per ticker). For any other run no approved, executable evidence-determination method exists, so the trigger is not evaluable and a missed Alpha there is recorded as facts and reported not_evaluable, never asserted as a FAIL -- on a new run the unified entry cannot yet 'discover' the miss (owner decision). The contract's other Alpha-level rules are not executed. Conflict-pair layer and composite layer: a miss is a B2 record that meets every condition and is not admitted; B2 cannot produce one, so those layers are proven by a controlled modification (a composite whose allowed pairs B2 rejected for a recorded reason is a REVIEW that needs adjudication, not a miss).

## 2. 没有支持证据 → 不强制激活 Alpha 或生成冲突

**Coverage: covered**

| Kind | Fixture | Test | Outcome | What it proves |
|---|---|---|---|---|
| rule function | synthetic | `tests/test_acceptance_engine.py::TestScenarioB_NoEvidenceNeverForcesDetection::test_b_a_detector_recorded_absence_of_qualifying_evidence_never_forces_a_conflict` | passed | the detector's own recorded absence of qualifying evidence -> the rule does not trigger |
| rule function | synthetic | `tests/test_acceptance_engine.py::TestScenarioB_NoEvidenceNeverForcesDetection::test_b_a_missing_arbitration_record_is_not_evaluated_and_never_read_as_no_evidence` | passed | no arbitration record -> not_evaluable; never 'no evidence' and never 'conditions met' |
| rule function | synthetic | `tests/test_acceptance_engine.py::TestScenarioB_NoEvidenceNeverForcesDetection::test_b_a_pair_rejected_before_b2_for_a_non_evidence_reason_is_not_evaluated_even_when_the_record_shows_claims` | passed | rejected before B2 for a non-evidence reason -> not_evaluable although the record lists supporting claims |
| rule function | real_detector_and_b2_on_synthetic_inputs | `tests/test_t2_conflict_semantics_real_b2.py::test_no_supporting_evidence_forces_nothing_and_is_recorded_as_the_detectors_own_absence_of_evidence` | passed | the real detector with no claims generates no conflict and no main conflict; the acceptance engine reads the absence as the detector's, not its own inference |
| final status | synthetic | `tests/test_t2_rule_config_errors.py::test_scenario_b_a_required_pair_without_an_arbitration_record_is_not_evaluated_never_forced_into_a_fail_and_never_a_pass` | passed | a required pair with no record -> status needs_review: not a fail, not a pass |
| final status | synthetic | `tests/test_t2_rule_config_errors.py::test_scenario_b_one_sided_evidence_is_not_enough_to_force_a_fail` | passed | evidence on one side only (B2 rejected it with its own reason) is not a miss |
| rule function | synthetic | `tests/test_t2_gold_contract_alpha_rules.py::test_trigger_absent_means_not_triggered_and_nothing_is_forced_and_uncertain_means_review` | passed | Alpha layer: trigger ABSENT -> not triggered, nothing forced (an Alpha at candidate level is not a FAIL); UNCERTAIN -> review |
| final status | synthetic | `tests/test_t2_gold_contract_alpha_rules.py::test_the_sixteen_allowed_relations_create_no_expectation_the_conditional_ones_only_leave_a_diagnostic` | passed | the 16 allowed relations demand no output: none admitted, every one B2-rejected -> no failure, no review on their account, status unchanged |
| upstream real code | synthetic | `tests/test_activation_scorer_v2.py::test_context_only_claim_contributes_no_activation_evidence` | passed | real activation scorer: no qualifying evidence -> activation 0.0 with NO_QUALIFYING_EVIDENCE: an Alpha is never forced active |
| upstream real code | real_detector_and_b2_on_synthetic_inputs | `tests/test_conflict_admissibility.py::test_c_single_unique_supporting_fact_is_insufficient` | passed | real B2 does not admit a pair on a single supporting fact |

*Limit:* Three states are kept apart and each has its own result: a recorded absence of qualifying evidence (does not trigger), unknown evidence (no record, rejected before B2, trigger not evaluable: not_evaluable) and an unfinished task (classification unavailable: not_evaluable).

## 3. 只有反驳、引用或背景文字 → 不当成该 Alpha 的有效支持

**Coverage: covered**

| Kind | Fixture | Test | Outcome | What it proves |
|---|---|---|---|---|
| rule function | synthetic | `tests/test_acceptance_engine.py::TestScenarioC_OpposingOrBackgroundEvidenceNeverCountsAsSupport::test_c_zero_stance_confirmed_support_never_counts_as_support_and_is_not_a_miss` | passed | a zero supporting count with B2's own reasons: B2 evaluated and rejected, neither admitted nor a miss (injected count) |
| upstream real code | real_detector_and_b2_on_synthetic_inputs | `tests/test_conflict_admissibility.py::test_e_opposes_alpha_stance_does_not_count_as_support` | passed | real B2: an opposing stance is not support |
| upstream real code | real_detector_and_b2_on_synthetic_inputs | `tests/test_conflict_admissibility.py::test_f_mentions_alpha_stance_does_not_count_as_support` | passed | real B2: a mere mention / citation is not support |
| upstream real code | real_detector_and_b2_on_synthetic_inputs | `tests/test_conflict_admissibility.py::test_g_neutral_background_stance_does_not_count_as_support` | passed | real B2: neutral background is not support |
| upstream real code | real_detector_and_b2_on_synthetic_inputs | `tests/test_conflict_admissibility.py::test_h_supports_counter_alpha_stance_does_not_count_as_support` | passed | real B2: support for the OTHER side is not support |
| upstream real code | real_pipeline_synthetic_text | `tests/test_t2_acceptance_engine_qualified_evidence_scenarios.py::TestScenarioA_InvalidSourceNeverCountsAsQualifyingEvidence::test_forged_bear_marker_leaves_bear_supporting_evidence_count_at_zero` | passed | through the real pipeline a forged source never counts; the pair is not evaluated by B2 and the acceptance result is neither a pass nor a fail |
| upstream real code | real_pipeline_synthetic_text | `tests/test_t2_acceptance_engine_qualified_evidence_scenarios.py::TestScenarioB_PendingReviewNeverCountsAsQualifyingEvidence::test_a_real_valid_but_unreviewed_bear_source_leaves_bear_supporting_evidence_count_at_zero` | passed | through the real pipeline an unreviewed source never counts; same outcome |
| upstream real code | real_pipeline_synthetic_text | `tests/test_t2_acceptance_engine_qualified_evidence_scenarios.py::TestScenarioC_ValidSupportGenuinelyCounts::test_a_real_reviewed_bear_source_reaches_b2_and_a_correct_rejection_is_not_a_miss` | passed | control: once the source is reviewed it counts, B2 evaluates the pair, and its correct rejection (one supporting fact per side) is not a miss |

*Limit:* The engine reads B2's supporting-evidence count and reasons; that opposing / citation / background text is excluded from that count is proven by the upstream tests listed.

## 4. 必需规则缺失或无法执行 → 报错，不产生正式 PASS

**Coverage: covered**

| Kind | Fixture | Test | Outcome | What it proves |
|---|---|---|---|---|
| rule function | synthetic | `tests/test_acceptance_engine.py::TestScenarioD_MissingConfigBlocksFormalPass::test_d_missing_label_file_is_a_config_error_never_a_formal_pass` | passed | missing label file -> config_error |
| rule function | synthetic | `tests/test_acceptance_engine.py::TestScenarioD_MissingConfigBlocksFormalPass::test_d_missing_taxonomy_file_is_a_config_error_never_a_formal_pass` | passed | missing taxonomy file -> config_error |
| final status | synthetic | `tests/test_t2_rule_config_errors.py::test_a_taxonomy_that_lacks_the_pairs_the_label_declares_is_a_config_error_not_a_silent_acceptance` | passed | taxonomy incompatible with the label file -> config_error |
| final status | synthetic | `tests/test_t2_rule_config_errors.py::test_a_label_file_written_against_another_taxonomy_content_version_is_a_config_error` | passed | version mismatch -> config_error |
| final status | synthetic | `tests/test_t2_rule_config_errors.py::test_a_rule_key_the_engine_does_not_implement_is_a_config_error_that_names_it` | passed | rule type not implemented -> config_error |
| final status | synthetic | `tests/test_t2_rule_config_errors.py::test_a_ticker_with_no_declared_rules_is_a_config_error_never_a_pass` | passed | a ticker the rule file says nothing about -> config_error, never PASS |
| final status | controlled_modification | `tests/test_t2_gold_contract_alpha_rules.py::test_a_missing_contract_freeze_manifest_or_matrix_is_a_configuration_error` | passed | Gold contract / freeze manifest / trigger matrix missing or malformed -> configuration error |
| final status | controlled_modification | `tests/test_t2_gold_contract_alpha_rules.py::test_an_edited_contract_is_not_the_contract_John_froze_even_if_it_still_parses` | passed | an edited contract (sha256 differs from the freeze manifest) is refused |
| final status | controlled_modification | `tests/test_t2_gold_contract_alpha_rules.py::test_a_contract_of_another_gold_version_is_refused` | passed | another Gold version / not frozen -> refused |
| final status | controlled_modification | `tests/test_t2_gold_contract_alpha_rules.py::test_a_matrix_that_is_not_the_frozen_file_or_was_written_against_another_contract_is_refused` | passed | a trigger matrix that is not the frozen file, or was written against another contract -> refused |
| final status | controlled_modification | `tests/test_t2_gold_contract_alpha_rules.py::test_a_rule_the_executor_runs_but_the_contract_lacks_or_retypes_is_refused` | passed | a rule the entry executes that the contract lacks or retypes -> refused (type not implemented) |
| final status | controlled_modification | `tests/test_t2_gold_contract_alpha_rules.py::test_through_the_unified_entry_a_bad_contract_file_is_a_config_error_for_every_ticker_never_a_pass` | passed | through run_formal_acceptance: a bad contract file -> formal_status config_error for every ticker |
| final status | synthetic | `tests/test_t2_gold_contract_alpha_rules.py::test_when_the_detection_authority_cannot_be_read_a_present_trigger_is_not_evaluable_never_guessed` | passed | an executable rule whose input cannot be read -> not_evaluable, never guessed |
| final status | synthetic | `tests/test_t2_gold_contract_alpha_rules.py::test_an_unevaluated_blocking_rule_blocks_certification_but_is_not_a_failure` | passed | an unevaluated blocking rule makes the release non-certifiable |
| final status | historical_saved_runs | `tests/test_t2_gold_contract_alpha_rules.py::test_the_pinned_verdicts_do_not_change_because_of_a_historical_trigger_that_was_never_theirs` | passed | on the six saved runs no status is a pass while a rule that should execute could not |
| final status | synthetic | `tests/test_t2_rule_config_errors.py::test_an_unusable_rule_file_leaves_a_visible_config_error_artifact` | passed | in production a broken rule file leaves a visible config_error artifact |
| final status | synthetic | `tests/test_t2_rule_config_errors.py::test_an_unexpected_failure_leaves_a_visible_execution_error_artifact` | passed | in production an unexpected failure leaves a visible execution_error artifact |
| rule function | synthetic | `tests/test_acceptance_engine.py::TestScenarioI_SemanticInputGateNeverSilentlyDefaultsToPass::test_missing_alpha_matches_payload_is_never_a_pass` | passed | missing semantic input -> alpha_semantic_unavailable, never PASS |
| upstream real code | real_pipeline_synthetic_text | `tests/test_formal_acceptance_artifact_production_wiring.py::TestScenarioA_RealPipelineProducesTheArtifact::test_formal_acceptance_artifact_is_written_by_the_real_completion_path` | passed | the real completion path: the production artifact carries the contract rules, they are not_evaluable for a new run, the status is not a pass, and the unified entry reaches the same contract verdicts |

## 5. 同源证据增加多份重复表达 → 不重复抬高证据强度

**Coverage: covered**

| Kind | Fixture | Test | Outcome | What it proves |
|---|---|---|---|---|
| rule function | synthetic | `tests/test_acceptance_engine.py::TestScenarioE_DuplicateCitationNeverInflatesEvidence::test_e_engine_only_ever_reads_the_already_deduped_fact_group_count` | passed | the engine only reads B2's already-deduplicated count and carries no raw-count field (injected count) |
| upstream real code | real_detector_and_b2_on_synthetic_inputs | `tests/test_conflict_admissibility.py::test_d_three_near_duplicate_claims_count_as_one_not_three` | passed | real B2: three near-duplicate claims count as one fact |
| upstream real code | real_pipeline_synthetic_text | `tests/test_content_support_llm_production_wiring.py::test_duplicate_source_citation_across_two_claims_does_not_inflate_independent_evidence_count` | passed | real pipeline: one source cited by two claims does not inflate the independent evidence count |
| upstream real code | synthetic | `tests/test_structure_correctness_sprint.py::test_same_source_duplicate_claims_are_merged` | passed | real structure code: same-source duplicate claims merge |
| upstream real code | synthetic | `tests/test_structure_correctness_sprint.py::test_duplicate_claims_do_not_inflate_matched_evidence` | passed | real structure code: duplicates do not inflate matched evidence |

*Limit:* The deduplication itself lives upstream (evidence facts / B2) and is proven there; the engine test only pins that the engine adds no second count.

## 6. 实际冲突不在标的验收列表 → 保留研究输出，转入复核，不改答案

**Coverage: covered**

| Kind | Fixture | Test | Outcome | What it proves |
|---|---|---|---|---|
| final status | synthetic | `tests/test_acceptance_engine.py::TestScenarioF_OutOfListConflictKeptVisible::test_f_admitted_conflict_outside_every_declared_category_is_never_dropped` | passed | an admitted undeclared pair -> needs_review (not fail), research output untouched |
| final status | synthetic | `tests/test_t2_rule_config_errors.py::test_an_undeclared_admitted_conflict_is_a_review_reason` | passed | the undeclared pair is listed in review_reasons that explain the status |
| rule function | synthetic | `tests/test_t2_gold_contract_alpha_rules.py::test_an_admitted_conflict_outside_the_allowed_family_keeps_the_research_output_and_routes_to_review` | passed | the Gold composite rule: an admitted conflict outside its allowed family -> review, the research output kept |
| upstream real code | historical_saved_runs | `tests/test_open_review_ledger.py::test_johns_named_nvda_item_is_open_on_the_pinned_run` | passed | on the saved NVDA run the undeclared admitted A304__A601 is an open review item |

*Limit:* On the six saved runs the same mechanism routes NVDA A304__A601 and QQQ A501__A601 etc. to review (see the six-ticker verdicts and the open-review ledger).

## 7. 同一输入做纯 replay，只更换执行编号 → 不因 run_id 变化产生无依据的研究结论变化

**Coverage: covered_with_limits**

| Kind | Fixture | Test | Outcome | What it proves |
|---|---|---|---|---|
| rule function | synthetic | `tests/test_acceptance_engine.py::TestScenarioG_PureReplayIsDeterministic::test_g_identical_input_replayed_under_a_different_run_id_yields_identical_verdicts` | passed | the label-based verdict does not depend on run_id |
| final status | historical_saved_runs | `tests/test_t2_gold_contract_alpha_rules.py::test_a_replay_under_another_run_id_changes_no_research_fact_and_only_the_run_bound_trigger_becomes_not_evaluable` | passed | a saved run copied under another id: Alpha facts and admitted conflicts identical; the Gold contract rules (bound to a run id by John's design) become not_evaluable, never pass or fail |
| upstream real code | synthetic | `tests/test_replay_pipeline.py::TestReplayCore::test_two_identical_replays_are_deterministic` | passed | two identical replays give identical results |
| upstream real code | synthetic | `tests/test_replay_identity_correction.py::test_conflict_detector_receives_replay_run_id_and_zero_mismatches` | passed | the replay run_id reaches the conflict detector with zero mismatches |
| upstream real code | synthetic | `tests/test_artifact_export_and_api.py::test_replay_conflict_does_not_get_run_id_mismatch` | passed | a replayed conflict payload does not get a run_id mismatch |
| upstream real code | synthetic | `tests/replay/test_exact_semantic_replay.py::test_eligible_exact_replay_is_atomic_byte_identical_and_source_read_only` | passed | exact semantic replay is byte-identical and read-only on the source |

*Limit:* The label-based verdicts never read the run id. The Gold contract rules DO: the frozen trigger matrix is bound to one run id per ticker by design, so the same saved run under another id is not evaluable for them (shown above, with every research fact unchanged). The research-conclusion property is carried by the upstream replay tests.

Cited tests: **61**; passed in this round's runs: **61**.

