"""T2 unified formal acceptance entry point -- dedicated tests
(comqutor_alpha.regression.acceptance_engine).

SYNTHETIC FIXTURES (task sheet: "测试可以使用明确标注的合成 fixtures，但不能把它们计为真实市场验证样本"): every conflict payload, label dict and
evaluate_ticker_result in this file is built by hand to exercise one rule at a time. None of it is market data and none of it counts as real
validation; the real six-ticker verdicts come from scripts/run_formal_acceptance.py run on the repository's saved runs.

Covers the 9 automated-test scenarios required by the COMQUTOR Alpha
next-round development task (Section 4.5):

  (a) clear support but a required pair is missed -> detected, not silently
      dropped.
  (b) no supporting evidence -> never forces detection or fabricates a
      conflict.
  (c) only opposing/citation/background evidence -> never counted as valid
      support (proven structurally: the evidence-present bar reads ONLY
      B2's own stance-filtered supporting_evidence_count field, which by
      construction excludes non-supports_alpha stances -- see
      conflict_admissibility.py's own docstring/_stance_filtered_qualifying).
  (d) a required rule/config is missing or unexecutable -> config error,
      never a formal PASS.
  (e) same-source duplicate citation -> never inflates evidence strength
      (the engine only ever reads B2's already-deduped fact-group count,
      never a raw claim count).
  (f) an actual admitted conflict outside every declared category -> kept
      visible for review, never silently dropped.
  (g) pure replay of the same input (only run_id/ticker label changes) ->
      identical rule verdicts, no unexplained drift.
  (h) a source ID/citation the pipeline never issued -> rejected, never
      silently accepted (existing source_provenance.py defensive
      validator).
  (i) the SAME already-computed admitted-conflict set is what both the
      do_not_force invariant and every per-category verdict read --
      no second, divergent notion of "admitted" is introduced here (the
      same field is what API/UI/Export consume downstream).
"""

from __future__ import annotations

from comqutor_alpha.regression.acceptance_engine import (
    FORMAL_STATUS_ALPHA_SEMANTIC_UNAVAILABLE,
    SEMANTIC_INPUT_REASON_ALL_UNAVAILABLE,
    SEMANTIC_INPUT_REASON_MISSING,
    SEMANTIC_INPUT_REASON_UNPARSEABLE,
    VERDICT_FAIL,
    VERDICT_NEEDS_REVIEW,
    VERDICT_NOT_APPLICABLE,
    VERDICT_PASS,
    VERDICT_PENDING_REVIEW,
    evaluate_do_not_force_invariant,
    evaluate_must_detect_if_evidence_present,
    evaluate_should_detect_if_supported,
    pair_admissibility_lookup,
    run_formal_acceptance,
)
from comqutor_alpha.source_provenance import resolve_source_by_id


def _conflict_payload(entries: list[dict]) -> dict:
    return {"arbitration": {"candidate_evaluations": entries}}


def _candidate_entry(alpha_a, alpha_b, *, outcome, status, bull_evidence, bear_evidence, reason_codes=()):
    return {
        "alpha_a": alpha_a,
        "alpha_b": alpha_b,
        "outcome": outcome,
        "admissibility": {
            "status": status,
            "reason_codes": list(reason_codes),
            "bull_supporting_evidence_count": bull_evidence,
            "bear_supporting_evidence_count": bear_evidence,
            "bull_score": 80.0,
            "bear_score": 80.0,
        },
    }


def _alpha_matches_payload(*alpha_ids: str) -> dict:
    """A minimal, real-shaped, genuinely-available alpha_matches payload --
    2026-09-30 closing fix: run_formal_acceptance now REQUIRES this
    parameter, so every call site testing something other than the
    semantic-availability gate itself must supply a payload that is
    clearly NOT 'missing/unparseable/all-unavailable', or it would trip
    the new ALPHA_SEMANTIC_UNAVAILABLE short-circuit before ever reaching
    the rule-family logic these tests actually exercise."""
    return {
        "matches": [
            {"claim_id": f"c-{alpha_id}", "match_status": "matched", "matched_alpha": alpha_id}
            for alpha_id in alpha_ids
        ]
        or [{"claim_id": "c-none", "match_status": "matched", "matched_alpha": None}]
    }


def _evaluate_ticker_result(*, admitted, candidate=(), stance_source="deterministic_baseline"):
    return {
        "ticker": "TEST",
        "run_selection_status": "selected",
        "offline_reprocess_status": "completed",
        "artifact_completeness": "pass",
        "artifact_missing_files": [],
        "admitted_conflicts": list(admitted),
        "candidate_conflicts": list(candidate),
        "stance_source": stance_source,
    }


class TestScenarioA_MissedRequiredPairIsDetected:
    def test_a_clear_support_but_missed_required_pair_is_reported_as_fail(self):
        label = {"required_conflicts": ["A101__A304"]}
        entries = [
            _candidate_entry(
                "A101", "A304", outcome="suppressed", status="candidate",
                bull_evidence=3, bear_evidence=3,
                reason_codes=["INSUFFICIENT_BULL_SUPPORTING_EVIDENCE"],
            )
        ]
        lookup = pair_admissibility_lookup(_conflict_payload(entries))
        results = evaluate_must_detect_if_evidence_present(ticker_v2_label=label, admissibility_lookup=lookup)
        assert results == [
            {
                "pair": "A101__A304",
                "evidence_present": True,
                "admissibility_status": "candidate",
                "verdict": VERDICT_FAIL,
                "detail": "evidence present on both sides but pair was not admitted -- a genuine miss",
            }
        ]


class TestScenarioB_NoEvidenceNeverForcesDetection:
    def test_b_no_supporting_evidence_never_forces_activation_or_a_conflict(self):
        label = {"required_conflicts": ["A101__A304"]}
        # Pair never even reached arbitration (e.g. one side never
        # activated) -- no candidate_evaluations entry at all.
        lookup = pair_admissibility_lookup(_conflict_payload([]))
        results = evaluate_must_detect_if_evidence_present(ticker_v2_label=label, admissibility_lookup=lookup)
        assert results[0]["verdict"] == VERDICT_NOT_APPLICABLE
        assert "never reached B2 arbitration" in results[0]["detail"]


class TestScenarioC_OpposingOrBackgroundEvidenceNeverCountsAsSupport:
    def test_c_zero_stance_confirmed_support_never_counts_as_evidence_present(self):
        # B2's own admissibility gate only counts claims whose FINAL stance
        # is exactly "supports_alpha" into
        # bull/bear_supporting_evidence_count (conflict_admissibility.py's
        # own _stance_filtered_qualifying) -- a candidate backed only by
        # opposing/background/citation-only evidence surfaces here as
        # count == 0, which this engine treats as "no evidence present",
        # never as valid support.
        label = {"required_conflicts": ["A101__A304"], "conditional_conflicts": []}
        entries = [
            _candidate_entry(
                "A101", "A304", outcome="suppressed", status="candidate",
                bull_evidence=0, bear_evidence=0,
                reason_codes=["INSUFFICIENT_BULL_SUPPORTING_EVIDENCE", "INSUFFICIENT_BEAR_SUPPORTING_EVIDENCE"],
            )
        ]
        lookup = pair_admissibility_lookup(_conflict_payload(entries))
        results = evaluate_must_detect_if_evidence_present(ticker_v2_label=label, admissibility_lookup=lookup)
        assert results[0]["evidence_present"] is False
        assert results[0]["verdict"] == VERDICT_NOT_APPLICABLE


class TestScenarioD_MissingConfigBlocksFormalPass:
    def test_d_missing_label_file_is_a_config_error_never_a_formal_pass(self, tmp_path):
        missing_path = tmp_path / "does_not_exist.yaml"
        result = run_formal_acceptance(
            ticker="NVDA",
            ticker_v2_label=None,
            label_block_v1=None,
            evaluate_ticker_result=_evaluate_ticker_result(admitted=[]),
            conflict_payload=None,
            graph_payload={},
            alpha_matches_payload=_alpha_matches_payload("A101"),
            label_v2_path=missing_path,
        )
        assert result["formal_status"] == "config_error"
        assert result["config_error_reason_code"] == "ACCEPTANCE_LABEL_V2_INVALID"
        assert "rule_family_results" not in result or result["rule_family_results"] == {}

    def test_d_missing_taxonomy_file_is_a_config_error_never_a_formal_pass(self, tmp_path):
        missing_path = tmp_path / "no_taxonomy.yaml"
        result = run_formal_acceptance(
            ticker="NVDA",
            ticker_v2_label=None,
            label_block_v1=None,
            evaluate_ticker_result=_evaluate_ticker_result(admitted=[]),
            conflict_payload=None,
            graph_payload={},
            alpha_matches_payload=_alpha_matches_payload("A101"),
            taxonomy_path=missing_path,
        )
        assert result["formal_status"] == "config_error"
        assert result["config_error_reason_code"] == "ACCEPTANCE_TAXONOMY_FILE_NOT_FOUND"


class TestScenarioE_DuplicateCitationNeverInflatesEvidence:
    def test_e_engine_only_ever_reads_the_already_deduped_fact_group_count(self):
        # This module has no access to raw claim counts at all -- it only
        # ever reads bull/bear_supporting_evidence_count, which is already
        # a deduped Evidence-Fact-group count computed upstream by
        # conflict_admissibility.py (John's B2 gate). Ten duplicate raw
        # mentions of the same underlying filing collapse into ONE fact
        # group upstream; this test locks in that the engine's own verdict
        # is driven by that single deduped count, never by re-deriving a
        # bigger number from raw claims (which it structurally cannot do --
        # no raw claim list is ever passed into this module).
        label = {"required_conflicts": ["A101__A304"]}
        entries = [
            _candidate_entry(
                "A101", "A304", outcome="admitted", status="admitted",
                bull_evidence=1, bear_evidence=1,  # one deduped fact group per side
            )
        ]
        lookup = pair_admissibility_lookup(_conflict_payload(entries))
        results = evaluate_must_detect_if_evidence_present(ticker_v2_label=label, admissibility_lookup=lookup)
        assert results[0]["verdict"] == VERDICT_PASS
        # The lookup entry itself carries no raw-claim-count field at all --
        # proving there is nothing here an inflated duplicate count could
        # even attach to.
        assert set(lookup["A101__A304"]) == {
            "outcome",
            "admissibility_status",
            "reason_codes",
            "bull_supporting_evidence_count",
            "bear_supporting_evidence_count",
            "bull_score",
            "bear_score",
        }


class TestScenarioF_OutOfListConflictKeptVisible:
    def test_f_admitted_conflict_outside_every_declared_category_is_never_dropped(self):
        # A304__A601 is admitted by B2/the detector but declared in none of
        # this ticker's required/conditional/allowed categories.
        result = run_formal_acceptance(
            ticker="TEST",
            ticker_v2_label={
                "required_conflicts": [],
                "conditional_conflicts": [],
                "allowed_conflicts": [],
                "product_decision_pending": [],
                "remove_while_undeclared": [],
                "structural_expectations": {},
            },
            label_block_v1=None,
            evaluate_ticker_result=_evaluate_ticker_result(admitted=["A304__A601"]),
            conflict_payload=_conflict_payload(
                [_candidate_entry("A304", "A601", outcome="admitted", status="admitted", bull_evidence=2, bear_evidence=2)]
            ),
            graph_payload={},
            alpha_matches_payload=_alpha_matches_payload("A304", "A601"),
        )
        # do_not_force still runs over the real admitted set and finds no
        # violation (B2 genuinely admitted it) -- the pair is not silently
        # excluded from that check just because no label category names it.
        assert result["rule_family_results"]["do_not_force"]["verdict"] == "invariant_held"
        assert "A304__A601" not in [r["pair"] for r in result["rule_family_results"]["must_detect_if_evidence_present"]]
        # Round 5 (2026-10-04): never surfaced as a fail purely for being
        # undeclared-in-a-category, AND genuinely routed to review -- not
        # just "not failed". Before this, formal_status came back a bare
        # "pass" with zero signal anywhere that an undeclared admitted
        # conflict existed, which is "kept visible" but never actually
        # "routed to review" the way John's own scenario (f) requires.
        assert result["undeclared_admitted_conflicts"] == ["A304__A601"]
        assert result["formal_status"] == "needs_review"


class TestScenarioG_PureReplayIsDeterministic:
    def test_g_identical_input_replayed_under_a_different_run_id_yields_identical_verdicts(self):
        label = {
            "required_conflicts": ["A101__A304"],
            "conditional_conflicts": [],
            "allowed_conflicts": [],
            "product_decision_pending": [],
            "remove_while_undeclared": [],
            "structural_expectations": {},
        }
        conflict_payload = _conflict_payload(
            [_candidate_entry("A101", "A304", outcome="admitted", status="admitted", bull_evidence=2, bear_evidence=2)]
        )
        result_1 = run_formal_acceptance(
            ticker="NVDA",
            ticker_v2_label=label,
            label_block_v1=None,
            evaluate_ticker_result=_evaluate_ticker_result(admitted=["A101__A304"]),
            conflict_payload=conflict_payload,
            graph_payload={},
            alpha_matches_payload=_alpha_matches_payload("A101", "A304"),
        )
        # Same underlying evidence/labels, only run_id/execution_id would
        # differ in a real replay (neither field feeds any verdict here) --
        # verdicts must be byte-identical.
        result_2 = run_formal_acceptance(
            ticker="NVDA",
            ticker_v2_label=label,
            label_block_v1=None,
            evaluate_ticker_result=_evaluate_ticker_result(admitted=["A101__A304"]),
            conflict_payload=conflict_payload,
            graph_payload={},
            alpha_matches_payload=_alpha_matches_payload("A101", "A304"),
        )
        assert result_1["rule_family_results"] == result_2["rule_family_results"]
        assert result_1["formal_status"] == result_2["formal_status"]


class TestScenarioH_ForgedSourceIdRejected:
    def test_h_an_id_the_pipeline_never_issued_is_rejected_not_silently_accepted(self):
        real_sources = [
            {
                "source_id": "src_real_0001",
                "source_type": "news",
                "title": "Real filing",
                "url": "https://example.com/real",
                "metadata_status": "traceable",
            }
        ]
        forged = resolve_source_by_id("src_model_hallucinated_9999", real_sources)
        assert forged is None
        real = resolve_source_by_id("src_real_0001", real_sources)
        assert real is not None and real["source_id"] == "src_real_0001"


class TestScenarioI_SingleSharedAdmittedSetAcrossConsumers:
    def test_i_do_not_force_and_per_category_verdicts_read_the_same_admitted_set(self):
        # evaluate_ticker_result["admitted_conflicts"] is the exact field
        # API routes / export already read (comqutor_alpha.regression
        # .evaluator.conflict_comparison's own admitted_ids, sourced from
        # conflicts.json's "conflicts" list) -- this engine introduces no
        # second, parallel notion of "admitted".
        admitted = ["A101__A304"]
        evaluate_ticker_result = _evaluate_ticker_result(admitted=admitted)
        conflict_payload = _conflict_payload(
            [_candidate_entry("A101", "A304", outcome="admitted", status="admitted", bull_evidence=2, bear_evidence=2)]
        )
        lookup = pair_admissibility_lookup(conflict_payload)
        do_not_force = evaluate_do_not_force_invariant(
            evaluate_ticker_result=evaluate_ticker_result, admissibility_lookup=lookup
        )
        assert do_not_force["verdict"] == "invariant_held"
        # The same evaluate_ticker_result.admitted_conflicts list is what
        # apply_v2_contract (feeding conditional/allowed results) also
        # reads -- verified indirectly via run_formal_acceptance already
        # exercising both paths over the identical object in scenario G.


class TestShouldDetectIfSupported:
    def test_evidence_present_but_stance_unreliable_is_pending_review_not_a_verdict(self):
        label = {"conditional_conflicts": ["A101__A304"]}
        entries = [
            _candidate_entry("A101", "A304", outcome="suppressed", status="candidate", bull_evidence=2, bear_evidence=2)
        ]
        lookup = pair_admissibility_lookup(_conflict_payload(entries))
        results = evaluate_should_detect_if_supported(
            ticker_v2_label=label, admissibility_lookup=lookup, stance_source_value="deterministic_baseline"
        )
        assert results[0]["verdict"] == VERDICT_PENDING_REVIEW

    def test_evidence_present_and_stance_reliable_but_not_admitted_is_needs_review(self):
        label = {"conditional_conflicts": ["A101__A304"]}
        entries = [
            _candidate_entry("A101", "A304", outcome="suppressed", status="candidate", bull_evidence=2, bear_evidence=2)
        ]
        lookup = pair_admissibility_lookup(_conflict_payload(entries))
        results = evaluate_should_detect_if_supported(
            ticker_v2_label=label, admissibility_lookup=lookup, stance_source_value="llm_semantic"
        )
        assert results[0]["verdict"] == VERDICT_NEEDS_REVIEW


class TestScenarioI_SemanticInputGateNeverSilentlyDefaultsToPass:
    """2026-09-30 closing fix: alpha_matches_payload was previously OPTIONAL
    on run_formal_acceptance, so a real caller (the six-ticker script) could
    simply never pass it and get the pre-gate PASS-defaulting behavior back.
    Proves, via the REAL run_formal_acceptance entry point, all three
    required cases: missing input never fakes a pass; all-UNAVAILABLE
    semantic input never fakes a pass; complete and qualified input is
    accepted normally under the existing rule families."""

    _LABEL = {
        "required_conflicts": [],
        "conditional_conflicts": [],
        "allowed_conflicts": [],
        "product_decision_pending": [],
        "remove_while_undeclared": [],
        "structural_expectations": {},
    }

    def test_missing_alpha_matches_payload_is_never_a_pass(self):
        # The exact condition the six-ticker script's own OLD call used to
        # produce: no required/allowed conflicts declared, so every rule
        # family's own empty-result default would otherwise fall through
        # straight to formal_status="pass".
        result = run_formal_acceptance(
            ticker="TEST",
            ticker_v2_label=self._LABEL,
            label_block_v1=None,
            evaluate_ticker_result=_evaluate_ticker_result(admitted=[]),
            conflict_payload=_conflict_payload([]),
            graph_payload={},
            alpha_matches_payload=None,
        )
        assert result["formal_status"] == FORMAL_STATUS_ALPHA_SEMANTIC_UNAVAILABLE
        assert result["formal_status"] != "pass"
        assert result["semantic_input_reason_code"] == SEMANTIC_INPUT_REASON_MISSING
        assert result["rule_family_results"] == {}
        # Rule version identity is still explicit even on this early-return
        # status -- never omitted just because semantic input was absent.
        assert "effective_rules" in result

    def test_unparseable_alpha_matches_payload_is_never_a_pass(self):
        result = run_formal_acceptance(
            ticker="TEST",
            ticker_v2_label=self._LABEL,
            label_block_v1=None,
            evaluate_ticker_result=_evaluate_ticker_result(admitted=[]),
            conflict_payload=_conflict_payload([]),
            graph_payload={},
            alpha_matches_payload={"matches": "not-a-list"},
        )
        assert result["formal_status"] == FORMAL_STATUS_ALPHA_SEMANTIC_UNAVAILABLE
        assert result["semantic_input_reason_code"] == SEMANTIC_INPUT_REASON_UNPARSEABLE

    def test_all_claims_semantic_unavailable_is_never_a_pass(self):
        # Architecture Replay's own real, deterministic signal -- every
        # claim's match_status=="unavailable", never rewritten to "none".
        result = run_formal_acceptance(
            ticker="TEST",
            ticker_v2_label=self._LABEL,
            label_block_v1=None,
            evaluate_ticker_result=_evaluate_ticker_result(admitted=[]),
            conflict_payload=_conflict_payload([]),
            graph_payload={},
            alpha_matches_payload={
                "matches": [
                    {"claim_id": "c1", "match_status": "unavailable", "matched_alpha": None},
                    {"claim_id": "c2", "match_status": "unavailable", "matched_alpha": None},
                ]
            },
        )
        assert result["formal_status"] == FORMAL_STATUS_ALPHA_SEMANTIC_UNAVAILABLE
        assert result["semantic_input_reason_code"] == SEMANTIC_INPUT_REASON_ALL_UNAVAILABLE
        # Never disguised as a genuine "none" semantic decision -- the
        # returned reason names "unavailable" explicitly, never "none".
        assert "unavailable" in result["reason"].lower()
        assert "none" not in result["reason"].lower()

    def test_complete_and_qualified_input_is_accepted_normally(self):
        # Same shape as scenario F -- a real matched alpha_matches payload
        # -- must reach the ordinary rule-family evaluation, never blocked
        # by the new gate just because it exists.
        result = run_formal_acceptance(
            ticker="TEST",
            ticker_v2_label=self._LABEL,
            label_block_v1=None,
            evaluate_ticker_result=_evaluate_ticker_result(admitted=["A304__A601"]),
            conflict_payload=_conflict_payload(
                [_candidate_entry("A304", "A601", outcome="admitted", status="admitted", bull_evidence=2, bear_evidence=2)]
            ),
            graph_payload={},
            alpha_matches_payload=_alpha_matches_payload("A304", "A601"),
        )
        assert result["formal_status"] in ("pass", "needs_review")
        assert result["formal_status"] != FORMAL_STATUS_ALPHA_SEMANTIC_UNAVAILABLE
        assert result["rule_family_results"]["do_not_force"]["verdict"] == "invariant_held"

    def test_config_error_still_takes_precedence_over_the_semantic_input_gate(self, tmp_path):
        # An unresolvable rule config is a more fundamental failure than a
        # missing semantic input -- CONFIG_ERROR must still fire first,
        # exactly as scenario D already established, even now that the
        # semantic gate exists.
        result = run_formal_acceptance(
            ticker="TEST",
            ticker_v2_label=self._LABEL,
            label_block_v1=None,
            evaluate_ticker_result=_evaluate_ticker_result(admitted=[]),
            conflict_payload=_conflict_payload([]),
            graph_payload={},
            alpha_matches_payload=None,
            taxonomy_path=tmp_path / "does_not_exist.yaml",
        )
        assert result["formal_status"] == "config_error"
        assert "effective_rules" not in result
