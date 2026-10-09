# Test results

Files: NEWTESTS_ON_ROUND23_CODE.junit.xml

Total **71**: 3 error, 19 failed, 49 passed

## Not passing

| Test | Outcome | First line of the message |
|---|---|---|
| `::tests.test_acceptance_engine` | error | collection failure |
| `::tests.test_t2_conflict_semantics_real_b2` | error | collection failure |
| `::tests.test_t2_gold_contract_alpha_rules` | error | collection failure |
| `tests.test_formal_acceptance_artifact_production_wiring.TestScenarioA_RealPipelineProducesTheArtifact::test_formal_acceptance_artifact_is_written_by_the_real_completion_path` | failed | KeyError: 'contract_rule_results' |
| `tests.test_formal_acceptance_report::test_the_command_line_takes_the_contract_paths_and_a_missing_contract_is_a_config_error_exit` | failed | SystemExit: 2 |
| `tests.test_formal_acceptance_report::test_the_contract_tables_show_the_facts_apart_and_are_rendered_from_the_document_alone` | failed | KeyError: 'contract_rule_results' |
| `tests.test_formal_acceptance_report::test_the_diagnostics_and_the_execution_status_are_in_the_document_and_in_the_tables` | failed | KeyError: 'rule_status' |
| `tests.test_no_gold_label_import_in_research_path::test_the_contract_scan_is_not_vacuous_the_acceptance_layer_does_name_the_files` | failed | FileNotFoundError: [Errno 2] No such file or directory: '/private/tmp/claude-501/-Users-xiangmao-COMQUTOR-Alpha-/8d38fcbd-98ee-4ff6-b804-8855e3f6b189/scratchpad/r24/r23_code_tree/comqutor_alpha/regression/gold_contract_rules.py' |
| `tests.test_open_review_ledger::test_a_vacuous_pass_is_marked_and_nvdas_latest_run_is_no_longer_one` | failed | AssertionError: assert ('pass' == 'needs_review' |
| `tests.test_open_review_ledger::test_diagnostics_and_unevaluated_rules_are_listed_apart_from_the_open_items` | failed | assert False |
| `tests.test_open_review_ledger::test_the_matrix_bound_nvda_run_evaluates_its_contract_rules_so_none_is_left_unevaluated` | failed | KeyError: 'unevaluated_rule_count' |
| `tests.test_t2_acceptance_engine_qualified_evidence_scenarios.TestScenarioA_InvalidSourceNeverCountsAsQualifyingEvidence::test_forged_bear_marker_leaves_bear_supporting_evidence_count_at_zero` | failed | KeyError: 'state' |
| `tests.test_t2_acceptance_engine_qualified_evidence_scenarios.TestScenarioB_PendingReviewNeverCountsAsQualifyingEvidence::test_a_real_valid_but_unreviewed_bear_source_leaves_bear_supporting_evidence_count_at_zero` | failed | KeyError: 'state' |
| `tests.test_t2_acceptance_engine_qualified_evidence_scenarios.TestScenarioC_ValidSupportGenuinelyCounts::test_a_real_reviewed_bear_source_reaches_b2_and_a_correct_rejection_is_not_a_miss` | failed | KeyError: 'state' |
| `tests.test_t2_rule_config_errors::test_a_conflict_pair_should_detect_finding_is_a_diagnostic_that_decides_nothing` | failed | AssertionError: assert 'needs_review' == 'pass' |
| `tests.test_t2_rule_config_errors::test_effective_rules_names_every_rule_file_by_repository_relative_path_and_hash` | failed | KeyError: 'gold_contract' |
| `tests.test_t2_rule_config_errors::test_review_reasons_explain_a_needs_review_and_name_their_family` | failed | AssertionError: assert 'pass' == 'needs_review' |
| `tests.test_t2_rule_config_errors::test_run_bound_expectations_is_an_unapproved_historical_observation_that_decides_nothing` | failed | KeyError: 'run_bound_observation' |
| `tests.test_t2_rule_config_errors::test_scenario_a_a_b2_record_with_no_rejection_reason_that_is_not_admitted_is_a_formal_fail` | failed | KeyError: 'state' |
| `tests.test_t2_rule_config_errors::test_scenario_a_a_required_pair_b2_rejected_for_a_recorded_reason_is_not_a_formal_fail` | failed | AssertionError: assert [{'family': '...enuine miss'}] == [] |
| `tests.test_t2_rule_config_errors::test_scenario_b_a_required_pair_without_an_arbitration_record_is_not_evaluated_never_forced_into_a_fail_and_never_a_pass` | failed | AssertionError: assert ('not_applicable' == 'not_evaluable' |
| `tests.test_t2_rule_config_errors::test_scenario_b_one_sided_evidence_is_not_enough_to_force_a_fail` | failed | KeyError: 'state' |
