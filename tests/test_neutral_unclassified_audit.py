"""QA Closure v0.1.2 Item 5 (Neutral / Unclassified Findings Audit) --
dedicated tests.

``build_neutral_unclassified_audit`` is a pure, deterministic
post-processing layer over an already-built ``unclassified_findings.json``
payload (see ``comqutor_alpha.api.unclassified_findings`` and its own
dedicated test file, ``tests/test_a3_unclassified_findings_control.py``,
for the upstream reason-assignment authority this module never re-derives).
Every test here drives hand-built ``unclassified_findings.json``-shaped
payloads directly -- the exact input contract this module actually
consumes -- plus one real-saved-run integration test.

Section map:
    A - Population accounting (audited_count, agent/reason sums, unknown
        agent/reason never dropped)
    B - Pattern detection (deterministic normalization, repeated-count
        correctness, distinct examples never merged)
    C - Suggested prompt fixes (evidence-backed only, threshold-gated)
    D - Determinism (repeated calls, real saved run)
"""

from __future__ import annotations

import copy

from comqutor_alpha.evaluation.neutral_unclassified_audit import (
    CLASSIFICATION_DUPLICATE_OUTPUT,
    CLASSIFICATION_GENERIC_BACKGROUND,
    CLASSIFICATION_PROMPT_REDUNDANCY,
    CLASSIFICATION_TICKER_SPECIFICITY_FAILURE,
    CLASSIFICATION_UNCLEAR,
    MISSING_REASON,
    UNKNOWN_AGENT,
    build_neutral_unclassified_audit,
)

REAL_RUN_ID = "07ddc074-9ab2-4b16-8957-acbf94012144"
REAL_RUN_OUTPUT_ROOT = "outputs/runs"


def _finding(claim_id, *, agent="news_agent", reason="no_alpha_match", reason_codes=None, claim=None, **overrides):
    base = {
        "claim_id": claim_id,
        "claim": claim if claim is not None else f"claim text for {claim_id}",
        "evidence": None,
        "agent": agent,
        "reason": reason,
        "reason_codes": reason_codes if reason_codes is not None else ([reason] if reason else []),
        "ticker_specific": True,
        "evidence_fact_group_id": None,
        "duplicate_group_id": None,
        "matched_alpha": None,
    }
    base.update(overrides)
    return base


def _payload(findings, *, run_id="test_run", ticker="NVDA", total_count=None):
    return {
        "schema_version": "unclassified_findings.v1",
        "run_id": run_id,
        "ticker": ticker,
        "total_count": total_count if total_count is not None else len(findings),
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# Section A -- Population accounting
# ---------------------------------------------------------------------------


class TestSectionAPopulationAccounting:
    def test_a1_audited_count_equals_actual_source_population(self):
        findings = [_finding(f"c{i}") for i in range(5)]
        audit = build_neutral_unclassified_audit(_payload(findings))
        assert audit["audited_count"] == 5
        assert audit["audited_count_matches_source_artifact"] is True

    def test_a2_audited_count_flags_mismatch_against_source_total_count_honestly(self):
        # total_count lies about the real findings list length -- the audit
        # must report this mismatch, never silently trust the stale field.
        findings = [_finding("c1")]
        audit = build_neutral_unclassified_audit(_payload(findings, total_count=999))
        assert audit["audited_count"] == 1
        assert audit["audited_count_matches_source_artifact"] is False

    def test_a3_agent_grouping_sum_equals_audited_count(self):
        findings = [
            _finding("c1", agent="news_agent"),
            _finding("c2", agent="market_agent"),
            _finding("c3", agent="news_agent"),
        ]
        audit = build_neutral_unclassified_audit(_payload(findings))
        by_agent = audit["unclassified_by_agent"]
        assert by_agent["counts"] == {"news_agent": 2, "market_agent": 1}
        assert by_agent["sum_equals_audited_count"] is True
        assert by_agent["percentage_of_total"]["news_agent"] == round(200 / 3, 2)

    def test_a4_missing_agent_is_reported_as_unknown_agent_never_dropped(self):
        findings = [_finding("c1", agent=None), _finding("c2", agent="")]
        audit = build_neutral_unclassified_audit(_payload(findings))
        by_agent = audit["unclassified_by_agent"]
        assert by_agent["counts"] == {UNKNOWN_AGENT: 2}
        assert by_agent["sum_equals_audited_count"] is True

    def test_a5_reason_finding_count_is_mutually_exclusive_and_sums_to_audited_count(self):
        findings = [
            _finding("c1", reason="no_alpha_match", reason_codes=["no_alpha_match"]),
            _finding("c2", reason="generic_background", reason_codes=["generic_background"]),
            _finding(
                "c3",
                reason="duplicate_supporting_text",
                reason_codes=["duplicate_supporting_text", "generic_background"],
            ),
        ]
        audit = build_neutral_unclassified_audit(_payload(findings))
        by_reason = audit["unclassified_by_reason"]
        assert by_reason["finding_count"] == {
            "no_alpha_match": 1,
            "generic_background": 1,
            "duplicate_supporting_text": 1,
        }
        assert by_reason["finding_count_sum_equals_audited_count"] is True
        # c3 carries 2 reason_codes -- occurrence_count must reflect both,
        # never silently collapsed to just the primary.
        assert by_reason["reason_occurrence_count"]["generic_background"] == 2
        assert by_reason["reason_occurrence_count"]["duplicate_supporting_text"] == 1
        assert by_reason["multi_reason_finding_count"] == 1

    def test_a6_missing_reason_is_reported_as_missing_reason_never_dropped(self):
        findings = [_finding("c1", reason=None, reason_codes=[])]
        audit = build_neutral_unclassified_audit(_payload(findings))
        by_reason = audit["unclassified_by_reason"]
        assert by_reason["finding_count"] == {MISSING_REASON: 1}
        assert by_reason["reason_occurrence_count"] == {MISSING_REASON: 1}

    def test_a7_agent_and_reason_cross_tab_reconciles_with_both_marginals(self):
        findings = [
            _finding("c1", agent="news_agent", reason="no_alpha_match", reason_codes=["no_alpha_match"]),
            _finding("c2", agent="news_agent", reason="generic_background", reason_codes=["generic_background"]),
            _finding("c3", agent="market_agent", reason="no_alpha_match", reason_codes=["no_alpha_match"]),
        ]
        audit = build_neutral_unclassified_audit(_payload(findings))
        cross_tab = audit["unclassified_by_agent_and_reason"]
        assert cross_tab["news_agent"] == {"no_alpha_match": 1, "generic_background": 1}
        assert cross_tab["market_agent"] == {"no_alpha_match": 1}
        # Every cross-tab cell sums back to the same by_agent/by_reason marginals.
        assert sum(sum(reasons.values()) for reasons in cross_tab.values()) == audit["audited_count"]


# ---------------------------------------------------------------------------
# Section B -- Pattern detection
# ---------------------------------------------------------------------------


class TestSectionBPatternDetection:
    def test_b8_top_patterns_only_include_genuinely_repeated_text_never_singletons(self):
        findings = [
            _finding("c1", claim="Revenue grew due to macro tailwinds."),
            _finding("c2", claim="Revenue grew due to macro tailwinds."),
            _finding("c3", claim="A completely different, unique observation."),
        ]
        audit = build_neutral_unclassified_audit(_payload(findings))
        assert audit["pattern_summary"]["total_findings"] == 3
        assert audit["pattern_summary"]["total_repeated_pattern_count"] == 1
        assert audit["pattern_summary"]["findings_fully_unique"] == 1
        patterns = audit["top_20_repeated_patterns"]
        assert len(patterns) == 1
        assert patterns[0]["count"] == 2

    def test_b9_repeated_pattern_count_is_correct_and_ranking_is_deterministic(self):
        findings = (
            [_finding(f"a{i}", claim="Pattern A repeats three times.") for i in range(3)]
            + [_finding(f"b{i}", claim="Pattern B repeats twice.") for i in range(2)]
        )
        audit = build_neutral_unclassified_audit(_payload(findings))
        patterns = audit["top_20_repeated_patterns"]
        assert [p["count"] for p in patterns] == [3, 2]
        assert [p["rank"] for p in patterns] == [1, 2]
        # Re-running produces byte-identical ranking (order is a pure
        # function of count + normalized text, never dict/set iteration
        # order).
        audit_again = build_neutral_unclassified_audit(_payload(findings))
        assert audit_again["top_20_repeated_patterns"] == patterns

    def test_b10_deterministic_normalization_ignores_only_case_whitespace_and_outer_punctuation(self):
        findings = [
            _finding("c1", claim="Revenue grew  by 10%."),
            _finding("c2", claim="  revenue grew by 10%"),
        ]
        audit = build_neutral_unclassified_audit(_payload(findings))
        assert len(audit["top_20_repeated_patterns"]) == 1
        assert audit["top_20_repeated_patterns"][0]["count"] == 2

    def test_b11_distinct_examples_are_never_merged_by_an_overly_aggressive_matcher(self):
        # Same topic, different number -- normalize_claim_for_dedupe's own
        # documented contract says these must stay two different patterns.
        findings = [
            _finding("c1", claim="Revenue increased 10%."),
            _finding("c2", claim="Revenue increased 20%."),
        ]
        audit = build_neutral_unclassified_audit(_payload(findings))
        assert audit["pattern_summary"]["total_repeated_pattern_count"] == 0
        assert audit["top_20_repeated_patterns"] == []

    def test_b12_pattern_classification_uses_dominant_reason_and_repetition_threshold(self):
        duplicate = [
            _finding(f"d{i}", claim="Duplicate evidence text.", reason="duplicate_supporting_text")
            for i in range(2)
        ]
        generic = [
            _finding(f"g{i}", claim="Generic macro commentary.", reason="generic_background") for i in range(2)
        ]
        ticker_fail = [
            _finding(f"t{i}", claim="No ticker named here.", reason="no_ticker_specific_evidence")
            for i in range(2)
        ]
        redundant_no_match = [
            _finding(f"n{i}", claim="Repeated unmatched boilerplate statement.", reason="no_alpha_match")
            for i in range(3)
        ]
        rare_no_match = [
            _finding(f"r{i}", claim="Rare unmatched statement pair.", reason="no_alpha_match") for i in range(2)
        ]
        audit = build_neutral_unclassified_audit(
            _payload(duplicate + generic + ticker_fail + redundant_no_match + rare_no_match)
        )
        by_pattern = {p["normalized_pattern"]: p["classification"] for p in audit["top_20_repeated_patterns"]}
        assert by_pattern["duplicate evidence text"] == CLASSIFICATION_DUPLICATE_OUTPUT
        assert by_pattern["generic macro commentary"] == CLASSIFICATION_GENERIC_BACKGROUND
        assert by_pattern["no ticker named here"] == CLASSIFICATION_TICKER_SPECIFICITY_FAILURE
        assert by_pattern["repeated unmatched boilerplate statement"] == CLASSIFICATION_PROMPT_REDUNDANCY
        # Below the repetition threshold (2 < 3) -- honestly unclear, never
        # guessed as a taxonomy gap or redundancy.
        assert by_pattern["rare unmatched statement pair"] == CLASSIFICATION_UNCLEAR


# ---------------------------------------------------------------------------
# Section C -- Suggested prompt fixes
# ---------------------------------------------------------------------------


class TestSectionCSuggestedPromptFixes:
    def test_c13_no_fix_proposed_below_the_minimum_support_threshold(self):
        findings = [_finding(f"c{i}", agent="news_agent", reason="generic_background") for i in range(2)]
        audit = build_neutral_unclassified_audit(_payload(findings))
        assert audit["suggested_prompt_fixes"] == []

    def test_c14_fix_proposed_once_support_reaches_the_threshold_and_cites_the_real_count(self):
        findings = [_finding(f"c{i}", agent="news_agent", reason="generic_background") for i in range(6)]
        audit = build_neutral_unclassified_audit(_payload(findings))
        fixes = audit["suggested_prompt_fixes"]
        assert len(fixes) == 1
        assert fixes[0]["target_agent"] == "news_agent"
        assert fixes[0]["supporting_pattern_count"] == 6
        assert fixes[0]["status"] == "recommendation_only"
        # Every required field (task section 11) is present.
        for key in (
            "target_agent",
            "observed_problem",
            "supporting_pattern_count",
            "suggested_change",
            "expected_effect",
            "risk",
            "status",
        ):
            assert key in fixes[0]


# ---------------------------------------------------------------------------
# Section D -- Determinism (including the real saved run)
# ---------------------------------------------------------------------------


class TestSectionDDeterminism:
    def test_d15_zero_provider_calls_reported(self):
        audit = build_neutral_unclassified_audit(_payload([_finding("c1")]))
        assert audit["provider_calls"] == 0
        assert audit["tradingagents_calls"] == 0

    def test_d16_input_payload_is_never_mutated(self):
        findings = [_finding("c1"), _finding("c2")]
        payload = _payload(findings)
        before = copy.deepcopy(payload)
        build_neutral_unclassified_audit(payload)
        assert payload == before

    def test_d17_real_saved_run_is_fully_accounted_for_and_deterministic(self):
        import json

        from comqutor_alpha.storage.file_store import load_json_record_if_exists

        source = load_json_record_if_exists(REAL_RUN_ID, "unclassified_findings.json", output_root=REAL_RUN_OUTPUT_ROOT)
        if source is None:
            import pytest

            pytest.skip("LIVE_SAVED_RUN_NOT_AVAILABLE: real MSFT run artifact not found locally")

        audit_a = build_neutral_unclassified_audit(source)
        audit_b = build_neutral_unclassified_audit(json.loads(json.dumps(source)))
        assert audit_a == audit_b
        assert audit_a["audited_count"] == audit_a["source_artifact_total_count"]
        assert audit_a["unclassified_by_agent"]["sum_equals_audited_count"] is True
        assert audit_a["unclassified_by_reason"]["finding_count_sum_equals_audited_count"] is True
