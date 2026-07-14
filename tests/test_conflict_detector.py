"""Week 4 deterministic Conflict Core unit tests (W4.1).

Covers the full checklist in the W4.1 task: taxonomy pair enumeration,
evidence-strength, admissibility, bull/bear resolution, formula/levels,
main-conflict arbitration, determinism, and the MSFT boundary. NVDA/QQQ
golden sanity checks live in their own files
(test_week4_nvda_conflict_sanity.py / test_week4_qqq_conflict_sanity.py).
"""

from __future__ import annotations

import inspect
import json

import pytest

from comqutor_alpha.alpha_library.alpha_loader import (
    MANDATORY_CONFLICT_WEIGHTS,
    load_alpha_taxonomy,
)
from comqutor_alpha.alpha_library.alpha_schema import ConflictAlpha
from comqutor_alpha.conflict_engine import conflict_detector, conflict_schema
from comqutor_alpha.conflict_engine.conflict_detector import (
    detect_alpha_conflicts,
    evaluate_conflict_pair,
)
from comqutor_alpha.conflict_engine.conflict_schema import (
    QUALIFYING_RELATIONS,
    ConflictInputError,
    canonical_pair_key,
    conflict_level,
)
from comqutor_alpha.graph_engine.activation_scorer import _EVIDENCE_RELATION_WEIGHT
from comqutor_alpha.graph_engine.graph_schema import ACTIVATION_FORMULA_VERSION
from tests.fixtures.week4_conflict_cases import (
    activation_entry,
    activation_payload,
    fake_alpha,
    match_record,
    two_alpha_taxonomy,
)

RUN_ID = "run_1"
TICKER = "NVDA"


def _detect(activation, matches, taxonomy=None, run_id=RUN_ID, ticker=TICKER):
    return detect_alpha_conflicts(
        run_id=run_id, ticker=ticker, activation_payload=activation, alpha_matches=matches, taxonomy=taxonomy
    )


def _outcome_for(result, alpha_a, alpha_b):
    key = canonical_pair_key(alpha_a, alpha_b)
    for item in result["arbitration"]["candidate_evaluations"]:
        if (item["alpha_a"], item["alpha_b"]) == key:
            return item
    raise AssertionError(f"no candidate evaluation for {key}")


def _audit_for_alpha(item, alpha_id):
    for side in ("alpha_a", "alpha_b"):
        audit = item["evidence_audit"][side]
        if audit["alpha_id"] == alpha_id:
            return audit
    raise AssertionError(f"no evidence audit for {alpha_id}")


class TestTaxonomyPairEnumeration:
    def test_six_mandatory_pairs_enumerated_exactly_once(self):
        result = _detect(activation_payload(), [])
        assert result["arbitration"]["declared_pair_count"] == 6
        assert len(result["arbitration"]["candidate_evaluations"]) == 6
        pairs = {(c["alpha_a"], c["alpha_b"]) for c in result["arbitration"]["candidate_evaluations"]}
        expected = {tuple(sorted(pair)) for pair in MANDATORY_CONFLICT_WEIGHTS}
        assert pairs == expected

    def test_bidirectional_declaration_collapses_to_one_candidate(self):
        taxonomy = two_alpha_taxonomy("A101", "A304", weight_a_to_b=0.9)
        result = _detect(activation_payload(), [], taxonomy=taxonomy)
        assert result["arbitration"]["declared_pair_count"] == 1
        assert len(result["arbitration"]["candidate_evaluations"]) == 1

    def test_undeclared_pair_never_computed(self):
        result = _detect(activation_payload(), [])
        pairs = {(c["alpha_a"], c["alpha_b"]) for c in result["arbitration"]["candidate_evaluations"]}
        assert canonical_pair_key("A102", "A304") not in pairs

    def test_a102_a304_never_appears_as_a_candidate(self):
        # Same intent as the previous test, phrased as its own explicit gate
        # per the W4.1 task's checklist item #33.
        result = _detect(
            activation_payload(
                activation_entry("A102", score=90, status="dominant", direction="positive"),
                activation_entry("A304", score=90, status="dominant", direction="negative"),
            ),
            [
                match_record("c1", "A102", relation="activation"),
                match_record("c2", "A304", relation="activation"),
            ],
        )
        serialized = json.dumps(result)
        assert "A102__A304" not in serialized
        assert "A304__A102" not in serialized

    def test_weights_are_read_from_the_real_taxonomy_not_hardcoded(self):
        result = _detect(activation_payload(), [])
        by_pair = {
            (c["alpha_a"], c["alpha_b"]): c
            for c in result["arbitration"]["candidate_evaluations"]
        }
        # No weight assertions possible directly from the audit item (weight
        # only surfaces inside an admitted conflict's components), but we can
        # confirm every declared pair matches the loader's own mandatory set
        # -- i.e. detect_alpha_conflicts truly delegates to load_alpha_taxonomy()
        # rather than a private copy.
        for pair in MANDATORY_CONFLICT_WEIGHTS:
            assert tuple(sorted(pair)) in by_pair

    def test_canonical_pair_key_is_order_independent(self):
        assert canonical_pair_key("A304", "A101") == canonical_pair_key("A101", "A304") == ("A101", "A304")

    def test_duplicate_declaration_within_taxonomy_is_rejected_not_silently_deduped(self):
        # A304 lists A101 twice, plus A101's own single reciprocal
        # declaration -- three directed entries collapsing to one canonical
        # pair is an anomaly the frozen real taxonomy never has.
        taxonomy = {
            "A304": fake_alpha(
                "A304",
                [
                    ConflictAlpha(alpha_id="A101", contradiction_weight=0.9),
                    ConflictAlpha(alpha_id="A101", contradiction_weight=0.9),
                ],
            ),
            "A101": fake_alpha("A101", [ConflictAlpha(alpha_id="A304", contradiction_weight=0.9)]),
        }
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, direction="positive"),
                activation_entry("A304", score=90, direction="negative"),
            ),
            [match_record("c1", "A101"), match_record("c2", "A304")],
            taxonomy=taxonomy,
        )
        item = _outcome_for(result, "A101", "A304")
        assert item["outcome"] == "rejected"
        assert "DUPLICATE_PAIR" in item["reason_codes"]

    def test_explicit_empty_taxonomy_does_not_fall_back_to_default(self):
        result = _detect(activation_payload(), [], taxonomy={})
        assert result["arbitration"]["declared_pair_count"] == 0
        assert result["arbitration"]["candidate_evaluations"] == []
        assert result["conflicts"] == []
        assert result["main_conflict"] is None

    def test_missing_reciprocal_declaration_is_rejected(self):
        taxonomy = {
            "A101": fake_alpha(
                "A101", [ConflictAlpha(alpha_id="A304", contradiction_weight=0.9)]
            ),
            "A304": fake_alpha("A304"),
        }
        result = _detect(activation_payload(), [], taxonomy=taxonomy)
        item = _outcome_for(result, "A101", "A304")
        assert item["outcome"] == "rejected"
        assert "MISSING_RECIPROCAL_DECLARATION" in item["reason_codes"]

    def test_asymmetric_weights_are_rejected_without_selecting_one(self):
        taxonomy = two_alpha_taxonomy(
            "A101", "A304", weight_a_to_b=0.9, weight_b_to_a=0.7
        )
        result = _detect(activation_payload(), [], taxonomy=taxonomy)
        item = _outcome_for(result, "A101", "A304")
        assert item["outcome"] == "rejected"
        assert "ASYMMETRIC_CONTRADICTION_WEIGHT" in item["reason_codes"]

    def test_dangling_alpha_reference_is_schema_invalid(self):
        taxonomy = {
            "A101": fake_alpha(
                "A101", [ConflictAlpha(alpha_id="A999", contradiction_weight=0.9)]
            )
        }
        with pytest.raises(ConflictInputError) as exc_info:
            _detect(activation_payload(), [], taxonomy=taxonomy)
        assert exc_info.value.reason_code == "SCHEMA_INVALID"

    def test_self_conflict_is_schema_invalid(self):
        taxonomy = {
            "A101": fake_alpha(
                "A101", [ConflictAlpha(alpha_id="A101", contradiction_weight=0.9)]
            )
        }
        with pytest.raises(ConflictInputError) as exc_info:
            _detect(activation_payload(), [], taxonomy=taxonomy)
        assert exc_info.value.reason_code == "SCHEMA_INVALID"

    def test_mapping_key_must_match_alpha_definition_id(self):
        taxonomy = {"A101": fake_alpha("A304")}
        with pytest.raises(ConflictInputError) as exc_info:
            _detect(activation_payload(), [], taxonomy=taxonomy)
        assert exc_info.value.reason_code == "SCHEMA_INVALID"

    def test_nonnumeric_weight_is_safely_rejected(self):
        taxonomy = {
            "A101": fake_alpha(
                "A101",
                [ConflictAlpha(alpha_id="A304", contradiction_weight="not-a-number")],
            ),
            "A304": fake_alpha(
                "A304",
                [ConflictAlpha(alpha_id="A101", contradiction_weight="not-a-number")],
            ),
        }

        result = _detect(activation_payload(), [], taxonomy=taxonomy)
        item = _outcome_for(result, "A101", "A304")
        assert item["outcome"] == "rejected"
        assert "INVALID_CONTRADICTION_WEIGHT" in item["reason_codes"]
        assert "not-a-number" not in json.dumps(item)

    @pytest.mark.parametrize("bad_weight", [float("nan"), float("inf"), float("-inf")])
    def test_nonfinite_weight_is_safely_rejected(self, bad_weight):
        taxonomy = two_alpha_taxonomy("A101", "A304", weight_a_to_b=bad_weight)
        result = _detect(activation_payload(), [], taxonomy=taxonomy)
        item = _outcome_for(result, "A101", "A304")
        assert item["outcome"] == "rejected"
        assert "INVALID_CONTRADICTION_WEIGHT" in item["reason_codes"]


class TestQualifyingEvidence:
    def _pair(self, score_a=1.0, score_b=1.0, relation_a="activation", relation_b="activation", **kw):
        return _detect(
            activation_payload(
                activation_entry("A101", score=90, direction="positive"),
                activation_entry("A304", score=90, direction="negative"),
            ),
            [
                match_record("cA", "A101", score=score_a, relation=relation_a),
                match_record("cB", "A304", score=score_b, relation=relation_b),
            ],
            **kw,
        )

    def test_qualifying_committed_evidence_reaches_bull_bear_structures(self):
        result = self._pair()
        conflict = result["main_conflict"]
        assert conflict["bull_structure"]["claim_ids"] == ["cA"]
        assert conflict["bear_structure"]["claim_ids"] == ["cB"]

    def test_ambiguous_is_excluded_from_evidence(self):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, direction="positive"),
                activation_entry("A304", score=90, direction="negative"),
            ),
            [
                match_record(
                    "cA", None, match_status="ambiguous", plausible_alphas=["A101"],
                    candidate_alpha_ids=["A101"],
                ),
                match_record("cB", "A304", relation="activation"),
            ],
        )
        item = _outcome_for(result, "A101", "A304")
        assert item["outcome"] != "admitted"
        assert "MISSING_LEFT_EVIDENCE" in item["reason_codes"] or "AMBIGUOUS_ONLY" in item["reason_codes"]

    def test_no_match_is_excluded_from_evidence(self):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, direction="positive"),
                activation_entry("A304", score=90, direction="negative"),
            ),
            [
                match_record("cA", None, match_status="no_match", candidate_alpha_ids=["A101"]),
                match_record("cB", "A304", relation="activation"),
            ],
        )
        item = _outcome_for(result, "A101", "A304")
        assert item["outcome"] != "admitted"
        assert "MISSING_LEFT_EVIDENCE" in item["reason_codes"]

    @pytest.mark.parametrize("relation", ["mention", "risk_relief", "invalidation", "unknown"])
    def test_unsupported_relations_are_excluded(self, relation):
        result = self._pair(relation_a=relation)
        item = _outcome_for(result, "A101", "A304")
        assert item["outcome"] != "admitted"
        assert "MISSING_LEFT_EVIDENCE" in item["reason_codes"]

    @pytest.mark.parametrize("relation", ["activation", "conditional", "mixed"])
    def test_qualifying_relations_are_retained(self, relation):
        result = self._pair(relation_a=relation, relation_b=relation)
        assert result["main_conflict"] is not None
        assert result["main_conflict"]["alpha_a"] == "A101"

    def test_duplicate_claim_id_counted_once(self):
        duplicate = match_record("cA", "A101", score=0.9)
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, direction="positive"),
                activation_entry("A304", score=90, direction="negative"),
            ),
            [
                duplicate,
                dict(duplicate),
                match_record("cB", "A304", score=0.9),
            ],
        )
        conflict = result["main_conflict"]
        assert conflict["bull_structure"]["claim_ids"] == ["cA"]
        assert conflict["components"]["alpha_a_evidence_strength"] == 0.9
        audit = _audit_for_alpha(_outcome_for(result, "A101", "A304"), "A101")
        assert audit["qualifying_claim_ids"] == ["cA"]
        assert audit["excluded"] == [{"claim_id": "cA", "reason_code": "DUPLICATE_CLAIM"}]

    def test_missing_claim_id_is_excluded(self):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, direction="positive"),
                activation_entry("A304", score=90, direction="negative"),
            ),
            [
                match_record("", "A101"),
                match_record("cB", "A304"),
            ],
        )
        item = _outcome_for(result, "A101", "A304")
        assert "MISSING_LEFT_EVIDENCE" in item["reason_codes"]

    def test_empty_evidence_text_is_excluded(self):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, direction="positive"),
                activation_entry("A304", score=90, direction="negative"),
            ),
            [
                match_record("cA", "A101", evidence="   "),
                match_record("cB", "A304"),
            ],
        )
        item = _outcome_for(result, "A101", "A304")
        assert "MISSING_LEFT_EVIDENCE" in item["reason_codes"]

    def test_ambiguous_only_reason_code_is_distinct_from_true_zero_evidence(self):
        # Side A: has *some* relevant evidence, but only ambiguous (never
        # committed) -> AMBIGUOUS_ONLY. Side B has literally nothing relevant
        # at all -> plain MISSING_RIGHT_EVIDENCE.
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, direction="positive"),
                activation_entry("A304", score=90, direction="negative"),
            ),
            [
                match_record(
                    "cA", None, match_status="ambiguous", plausible_alphas=["A101"],
                    candidate_alpha_ids=["A101"],
                ),
            ],
        )
        item = _outcome_for(result, "A101", "A304")
        assert "AMBIGUOUS_ONLY" in item["reason_codes"]
        assert "MISSING_RIGHT_EVIDENCE" in item["reason_codes"]

    def test_ambiguous_plus_no_match_uses_missing_evidence(self):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, direction="positive"),
                activation_entry("A304", score=90, direction="negative"),
            ),
            [
                match_record(
                    "c1",
                    None,
                    match_status="ambiguous",
                    plausible_alphas=["A101"],
                    candidate_alpha_ids=["A101"],
                ),
                match_record(
                    "c2", None, match_status="no_match", candidate_alpha_ids=["A101"]
                ),
                match_record("cB", "A304"),
            ],
        )
        item = _outcome_for(result, "A101", "A304")
        assert "MISSING_LEFT_EVIDENCE" in item["reason_codes"]
        assert "AMBIGUOUS_ONLY" not in item["reason_codes"]

    def test_ambiguous_plus_unsupported_committed_uses_missing_evidence(self):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, direction="positive"),
                activation_entry("A304", score=90, direction="negative"),
            ),
            [
                match_record(
                    "c1",
                    None,
                    match_status="ambiguous",
                    plausible_alphas=["A101"],
                    candidate_alpha_ids=["A101"],
                ),
                match_record("c2", "A101", relation="mention"),
                match_record("cB", "A304"),
            ],
        )
        item = _outcome_for(result, "A101", "A304")
        assert "MISSING_LEFT_EVIDENCE" in item["reason_codes"]
        assert "AMBIGUOUS_ONLY" not in item["reason_codes"]

    def test_wrong_alpha_claim_is_excluded_but_still_audited(self):
        # cA is a candidate for A101 but actually committed to a different
        # alpha (still relevant because it appears in A101's candidate_scores).
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, direction="positive"),
                activation_entry("A304", score=90, direction="negative"),
            ),
            [
                {
                    **match_record("cA", "A201", relation="activation"),
                    "candidate_scores": [
                        {"alpha_id": "A201", "score": 0.8, "relation": "activation"},
                        {"alpha_id": "A101", "score": 0.5, "relation": "activation"},
                    ],
                },
                match_record("cB", "A304"),
            ],
        )
        item = _outcome_for(result, "A101", "A304")
        assert "MISSING_LEFT_EVIDENCE" in item["reason_codes"]


class TestDuplicateClaimCorrectness:
    def _activation(self):
        return activation_payload(
            activation_entry("A101", score=90, direction="positive"),
            activation_entry("A304", score=90, direction="negative"),
        )

    def test_exact_duplicates_are_order_independent_and_audited_once(self):
        original = match_record("cA", "A101", score=0.9)
        duplicate_with_reordered_keys = dict(reversed(list(original.items())))
        duplicate_with_reordered_keys["claim_id"] = "  cA  "
        matches = [original, duplicate_with_reordered_keys, match_record("cB", "A304")]

        forward = _detect(self._activation(), matches)
        reverse = _detect(self._activation(), list(reversed(matches)))

        assert json.dumps(forward, sort_keys=True) == json.dumps(reverse, sort_keys=True)
        assert forward["main_conflict"]["bull_structure"]["claim_ids"] == ["cA"]
        audit = _audit_for_alpha(_outcome_for(forward, "A101", "A304"), "A101")
        assert audit == {
            "alpha_id": "A101",
            "qualifying_claim_ids": ["cA"],
            "qualifying_count": 1,
            "excluded": [{"claim_id": "cA", "reason_code": "DUPLICATE_CLAIM"}],
            "excluded_count": 1,
        }

    @pytest.mark.parametrize(
        "field,mutate",
        [
            ("score", lambda record: record.update(score=0.1)),
            ("matched_alpha", lambda record: record.update(matched_alpha="A304")),
            (
                "relation",
                lambda record: record.update(
                    candidate_scores=[
                        {"alpha_id": "A101", "score": 0.9, "relation": "conditional"}
                    ]
                ),
            ),
            (
                "evidence",
                lambda record: record.update(
                    evidence="materially different evidence",
                    claim="materially different evidence",
                ),
            ),
        ],
        ids=("score", "matched-alpha", "relation", "evidence"),
    )
    def test_conflicting_duplicate_is_a_safe_global_error(self, field, mutate):
        del field  # pytest id documents which semantic field is changed.
        first = match_record("cA", "A101", score=0.9)
        second = dict(first)
        mutate(second)

        with pytest.raises(ConflictInputError) as exc_info:
            _detect(self._activation(), [first, second, match_record("cB", "A304")])

        assert exc_info.value.reason_code == "DUPLICATE_CLAIM_CONFLICT"
        assert str(exc_info.value) == "DUPLICATE_CLAIM_CONFLICT"


class TestEvidenceAuditContract:
    def _item(self, left_record, *, right_record=None):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, direction="positive"),
                activation_entry("A304", score=90, direction="negative"),
            ),
            [left_record, right_record or match_record("cB", "A304")],
        )
        return _outcome_for(result, "A101", "A304")

    @pytest.mark.parametrize(
        "record,expected_reason",
        [
            (
                match_record("c1", None, match_status="ambiguous", plausible_alphas=["A101"]),
                "NON_COMMITTED_MATCH",
            ),
            (match_record("", "A101"), "MISSING_CLAIM_ID"),
            (match_record("c2", "A101", relation="mention"), "UNSUPPORTED_RELATION"),
            (match_record("c3", "A101", evidence="   "), "EMPTY_EVIDENCE"),
            (match_record("c4", "A101", score=float("nan")), "INVALID_MATCH_SCORE"),
        ],
        ids=("non-committed", "missing-id", "unsupported", "empty", "invalid-score"),
    )
    def test_exclusion_reason_is_visible(self, record, expected_reason):
        audit = _audit_for_alpha(self._item(record), "A101")
        assert expected_reason in {entry["reason_code"] for entry in audit["excluded"]}

    def test_wrong_alpha_is_visible(self):
        record = match_record("cA", "A201")
        record["candidate_scores"].append(
            {"alpha_id": "A101", "score": 0.5, "relation": "activation"}
        )
        audit = _audit_for_alpha(self._item(record), "A101")
        assert audit["excluded"] == [{"claim_id": "cA", "reason_code": "WRONG_ALPHA"}]

    def test_admitted_suppressed_and_rejected_candidates_all_include_audit(self):
        admitted = self._item(match_record("cA", "A101"))
        suppressed = self._item(match_record("cA", "A101", relation="mention"))
        rejected_result = _detect(
            activation_payload(activation_entry("A101", score=90, direction="positive")),
            [match_record("cA", "A101")],
        )
        rejected = _outcome_for(rejected_result, "A101", "A304")

        assert admitted["outcome"] == "admitted"
        assert suppressed["outcome"] == "suppressed"
        assert rejected["outcome"] == "rejected"
        for item in (admitted, suppressed, rejected):
            assert set(item["evidence_audit"]) == {"alpha_a", "alpha_b"}

    def test_audit_is_sorted_and_input_order_independent(self):
        records = [
            match_record("z", "A101", relation="mention"),
            match_record("a", "A101", evidence="   "),
            match_record("cB", "A304"),
        ]
        activation = activation_payload(
            activation_entry("A101", score=90, direction="positive"),
            activation_entry("A304", score=90, direction="negative"),
        )
        forward = _outcome_for(_detect(activation, records), "A101", "A304")
        reverse = _outcome_for(_detect(activation, list(reversed(records))), "A101", "A304")
        assert forward["evidence_audit"] == reverse["evidence_audit"]
        audit = _audit_for_alpha(forward, "A101")
        assert audit["excluded"] == sorted(
            audit["excluded"], key=lambda entry: (entry["claim_id"] or "", entry["reason_code"])
        )

    def test_audit_does_not_copy_evidence_or_sensitive_text(self):
        sensitive = "/Users/private/project password=do-not-copy provider_response=secret"
        item = self._item(match_record("cA", "A101", evidence=sensitive))
        serialized_audit = json.dumps(item["evidence_audit"], sort_keys=True)
        assert sensitive not in serialized_audit
        for forbidden in ("/Users/", "password", "provider_response", "Traceback"):
            assert forbidden not in serialized_audit


class TestEvidenceStrengthCalculation:
    def test_evidence_strength_is_mean_of_side_means(self):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, direction="positive"),
                activation_entry("A304", score=90, direction="negative"),
            ),
            [
                match_record("cA1", "A101", score=1.0),
                match_record("cA2", "A101", score=0.5),
                match_record("cB1", "A304", score=0.4),
                match_record("cB2", "A304", score=0.6),
            ],
        )
        components = result["main_conflict"]["components"]
        assert components["alpha_a_evidence_strength"] == pytest.approx(0.75)  # mean(1.0, 0.5)
        assert components["alpha_b_evidence_strength"] == pytest.approx(0.5)  # mean(0.4, 0.6)
        assert components["evidence_strength"] == pytest.approx(0.625)  # mean(0.75, 0.5)

    def test_match_score_is_clamped_to_unit_interval(self):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, direction="positive"),
                activation_entry("A304", score=90, direction="negative"),
            ),
            [
                match_record("cA", "A101", score=5.0),  # out of range, must clamp to 1.0
                match_record("cB", "A304", score=-3.0),  # out of range, must clamp to 0.0
            ],
        )
        conflict = result["main_conflict"]
        # side B clamps to 0.0 -> evidence_strength becomes 0.5, still > 0,
        # so the pair can still be admitted; the clamp itself is the point.
        assert conflict["bull_structure"]["match_scores"] == [1.0]
        assert conflict["bear_structure"]["match_scores"] == [0.0]

    def test_non_finite_match_score_is_excluded_not_treated_as_strong(self):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, direction="positive"),
                activation_entry("A304", score=90, direction="negative"),
            ),
            [
                match_record("cA", "A101", score=float("nan")),
                match_record("cB", "A304", score=0.9),
            ],
        )
        item = _outcome_for(result, "A101", "A304")
        assert "MISSING_LEFT_EVIDENCE" in item["reason_codes"]

    def test_zero_evidence_strength_is_suppressed_even_with_admissible_status(self):
        # Contrived: both sides watch+ but with clamped-to-zero match scores
        # on both -> evidence_strength == 0 exactly.
        result = _detect(
            activation_payload(
                activation_entry("A101", score=60, status="watch", direction="positive"),
                activation_entry("A304", score=60, status="watch", direction="negative"),
            ),
            [
                match_record("cA", "A101", score=-1.0),
                match_record("cB", "A304", score=-1.0),
            ],
        )
        item = _outcome_for(result, "A101", "A304")
        assert item["outcome"] == "suppressed"
        assert "ZERO_EVIDENCE_STRENGTH" in item["reason_codes"]

    def test_missing_left_evidence_is_suppressed(self):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, direction="positive"),
                activation_entry("A304", score=90, direction="negative"),
            ),
            [match_record("cB", "A304")],
        )
        item = _outcome_for(result, "A101", "A304")
        assert item["outcome"] == "suppressed"
        assert "MISSING_LEFT_EVIDENCE" in item["reason_codes"]

    def test_missing_right_evidence_is_suppressed(self):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, direction="positive"),
                activation_entry("A304", score=90, direction="negative"),
            ),
            [match_record("cA", "A101")],
        )
        item = _outcome_for(result, "A101", "A304")
        assert item["outcome"] == "suppressed"
        assert "MISSING_RIGHT_EVIDENCE" in item["reason_codes"]

    def test_evidence_strength_scale_is_0_to_1(self):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, direction="positive"),
                activation_entry("A304", score=90, direction="negative"),
            ),
            [match_record("cA", "A101", score=1.0), match_record("cB", "A304", score=1.0)],
        )
        assert result["main_conflict"]["components"]["evidence_strength"] == 1.0

    def test_qualifying_relations_constant_matches_current_week3_positive_weights(self):
        # Consistency canary (not a hard coupling -- see conflict_schema.py's
        # docstring): Week 4's frozen QUALIFYING_RELATIONS must currently
        # equal the set of Week 3 relations with a positive
        # _EVIDENCE_RELATION_WEIGHT. If Week 3 ever changes that dict, this
        # test is the tripwire that surfaces the drift for a human decision
        # -- it does not silently follow Week 3.
        positive_weight_relations = frozenset(
            relation for relation, weight in _EVIDENCE_RELATION_WEIGHT.items() if weight > 0
        )
        assert positive_weight_relations == QUALIFYING_RELATIONS


class TestAdmissibility:
    def test_inactive_side_is_suppressed(self):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=10, status="inactive", direction="positive"),
                activation_entry("A304", score=90, status="dominant", direction="negative"),
            ),
            [match_record("cA", "A101"), match_record("cB", "A304")],
        )
        item = _outcome_for(result, "A101", "A304")
        assert item["outcome"] == "suppressed"
        assert "BELOW_ACTIVATION_THRESHOLD" in item["reason_codes"]

    def test_watch_status_on_both_sides_can_be_admitted(self):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=35, status="watch", direction="positive"),
                activation_entry("A304", score=35, status="watch", direction="negative"),
            ),
            [match_record("cA", "A101"), match_record("cB", "A304")],
        )
        assert result["main_conflict"] is not None

    @pytest.mark.parametrize("status", ["active", "dominant", "regime_level"])
    def test_admissible_statuses_above_watch_can_be_admitted(self, status):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, status=status, direction="positive"),
                activation_entry("A304", score=90, status=status, direction="negative"),
            ),
            [match_record("cA", "A101"), match_record("cB", "A304")],
        )
        assert result["main_conflict"] is not None

    def test_unrecognized_status_is_rejected(self):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, status="not_a_real_status", direction="positive"),
                activation_entry("A304", score=90, status="active", direction="negative"),
            ),
            [match_record("cA", "A101"), match_record("cB", "A304")],
        )
        item = _outcome_for(result, "A101", "A304")
        assert "BELOW_ACTIVATION_THRESHOLD" in item["reason_codes"]

    def test_missing_left_activation_entry_is_rejected(self):
        result = _detect(
            activation_payload(activation_entry("A304", score=90, direction="negative")),
            [match_record("cB", "A304")],
        )
        item = _outcome_for(result, "A101", "A304")
        assert item["outcome"] == "rejected"
        assert "MISSING_LEFT_ACTIVATION" in item["reason_codes"]

    def test_missing_right_activation_entry_is_rejected(self):
        result = _detect(
            activation_payload(activation_entry("A101", score=90, direction="positive")),
            [match_record("cA", "A101")],
        )
        item = _outcome_for(result, "A101", "A304")
        assert item["outcome"] == "rejected"
        assert "MISSING_RIGHT_ACTIVATION" in item["reason_codes"]

    @pytest.mark.parametrize("bad_score", [float("nan"), float("inf"), float("-inf"), "abc", None])
    def test_non_finite_or_invalid_activation_score_is_rejected(self, bad_score):
        entry = activation_entry("A101", direction="positive")
        entry["activation_score"] = bad_score
        result = _detect(
            activation_payload(entry, activation_entry("A304", score=90, direction="negative")),
            [match_record("cA", "A101"), match_record("cB", "A304")],
        )
        item = _outcome_for(result, "A101", "A304")
        assert item["outcome"] == "rejected"
        assert "NON_FINITE_SCORE_COMPONENT" in item["reason_codes"]

    @pytest.mark.parametrize("bad_score", [150.0, -10.0])
    def test_out_of_range_activation_score_is_rejected(self, bad_score):
        entry = activation_entry("A101", direction="positive")
        entry["activation_score"] = bad_score
        result = _detect(
            activation_payload(entry, activation_entry("A304", score=90, direction="negative")),
            [match_record("cA", "A101"), match_record("cB", "A304")],
        )
        item = _outcome_for(result, "A101", "A304")
        assert item["outcome"] == "rejected"
        assert "INVALID_ACTIVATION_SCORE" in item["reason_codes"]

    @pytest.mark.parametrize("bad_weight", [float("nan"), float("inf"), -0.1, 1.5])
    def test_invalid_contradiction_weight_is_rejected(self, bad_weight):
        taxonomy = two_alpha_taxonomy("A101", "A304", weight_a_to_b=bad_weight)
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, direction="positive"),
                activation_entry("A304", score=90, direction="negative"),
            ),
            [match_record("cA", "A101"), match_record("cB", "A304")],
            taxonomy=taxonomy,
        )
        item = _outcome_for(result, "A101", "A304")
        assert item["outcome"] == "rejected"
        assert "INVALID_CONTRADICTION_WEIGHT" in item["reason_codes"]

    def test_contradiction_weight_boundaries_0_and_1_are_valid(self):
        for boundary in (0.0, 1.0):
            taxonomy = two_alpha_taxonomy("A101", "A304", weight_a_to_b=boundary)
            result = _detect(
                activation_payload(
                    activation_entry("A101", score=90, direction="positive"),
                    activation_entry("A304", score=90, direction="negative"),
                ),
                [match_record("cA", "A101"), match_record("cB", "A304")],
                taxonomy=taxonomy,
            )
            item = _outcome_for(result, "A101", "A304")
            assert "INVALID_CONTRADICTION_WEIGHT" not in item["reason_codes"]


class TestDirectionRoleResolution:
    @pytest.mark.parametrize(
        "direction_a,direction_b",
        [
            ("positive", "positive"),
            ("negative", "negative"),
            ("unknown", "negative"),
            ("positive", "unknown"),
            ("neutral", "negative"),
            (None, "negative"),
        ],
    )
    def test_direction_role_unresolved_variants(self, direction_a, direction_b):
        entry_a = activation_entry("A101", score=90, direction=direction_a) if direction_a else activation_entry(
            "A101", score=90
        )
        if direction_a is None:
            entry_a.pop("direction")
        result = _detect(
            activation_payload(entry_a, activation_entry("A304", score=90, direction=direction_b)),
            [match_record("cA", "A101"), match_record("cB", "A304")],
        )
        item = _outcome_for(result, "A101", "A304")
        assert item["outcome"] == "rejected"
        assert "DIRECTION_ROLE_UNRESOLVED" in item["reason_codes"]

    def test_positive_negative_resolves_bull_bear_correctly(self):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, direction="positive"),
                activation_entry("A304", score=90, direction="negative"),
            ),
            [match_record("cA", "A101"), match_record("cB", "A304")],
        )
        conflict = result["main_conflict"]
        assert conflict["bull_alpha_id"] == "A101"
        assert conflict["bear_alpha_id"] == "A304"
        assert conflict["bull_structure"]["direction"] == "positive"
        assert conflict["bear_structure"]["direction"] == "negative"

    def test_negative_positive_resolves_bull_bear_correctly_not_by_dict_order(self):
        # A304 (alphabetically first as alpha_a) is positive here, A101 is
        # negative -- bull/bear must follow direction, not canonical order.
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, direction="negative"),
                activation_entry("A304", score=90, direction="positive"),
            ),
            [match_record("cA", "A101"), match_record("cB", "A304")],
        )
        conflict = result["main_conflict"]
        assert conflict["alpha_a"] == "A101"  # canonical order unchanged
        assert conflict["bull_alpha_id"] == "A304"  # role is not canonical order
        assert conflict["bear_alpha_id"] == "A101"


class TestFormulaAndLevels:
    def test_conflict_score_formula_matches_official_definition(self):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=80.0, direction="positive"),
                activation_entry("A304", score=60.0, direction="negative"),
            ),
            [match_record("cA", "A101", score=1.0), match_record("cB", "A304", score=1.0)],
        )
        conflict = result["main_conflict"]
        expected = min(80.0, 60.0) * 0.90 * 1.0  # A101-A304 taxonomy weight is 0.90
        assert conflict["conflict_score"] == pytest.approx(expected, abs=1e-6)

    def test_component_breakdown_is_complete_and_matches_score(self):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=80.0, direction="positive"),
                activation_entry("A304", score=60.0, direction="negative"),
            ),
            [match_record("cA", "A101", score=0.8), match_record("cB", "A304", score=0.6)],
        )
        components = result["main_conflict"]["components"]
        for key in (
            "activation_a",
            "activation_b",
            "minimum_activation",
            "contradiction_weight",
            "alpha_a_evidence_strength",
            "alpha_b_evidence_strength",
            "evidence_strength",
        ):
            assert key in components
        recomputed = (
            components["minimum_activation"]
            * components["contradiction_weight"]
            * components["evidence_strength"]
        )
        assert recomputed == pytest.approx(result["main_conflict"]["conflict_score"], abs=1e-3)

    def test_conflict_score_is_clamped_to_0_100(self):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=100.0, direction="positive"),
                activation_entry("A304", score=100.0, direction="negative"),
            ),
            [match_record("cA", "A101", score=1.0), match_record("cB", "A304", score=1.0)],
        )
        score = result["main_conflict"]["conflict_score"]
        assert 0.0 <= score <= 100.0

    @pytest.mark.parametrize(
        "score,expected_level",
        [
            (0, "low"),
            (25, "low"),
            (25.0001, "medium"),
            (50, "medium"),
            (50.0001, "medium_high"),
            (75, "medium_high"),
            (75.0001, "high"),
            (100, "high"),
        ],
    )
    def test_conflict_level_boundaries(self, score, expected_level):
        assert conflict_level(score) == expected_level

    @pytest.mark.parametrize("bad_score", [float("nan"), float("inf"), float("-inf"), -50, 500])
    def test_conflict_level_never_raises_on_bad_input(self, bad_score):
        level = conflict_level(bad_score)
        assert level in ("low", "medium", "medium_high", "high")

    def test_conflict_level_does_not_reuse_week3_activation_status_names(self):
        # Week 3 activation status bands are inactive/watch/active/dominant/
        # regime_level -- none of those strings must ever come out of
        # conflict_level().
        for score in (10, 40, 60, 90):
            assert conflict_level(score) not in ("inactive", "watch", "active", "dominant", "regime_level")


class TestMainConflictArbitration:
    def test_main_conflict_is_highest_ranked_admitted_conflict(self):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=95, direction="positive"),
                activation_entry("A304", score=95, direction="negative"),
                activation_entry("A301", score=40, direction="positive"),
                activation_entry("A601", score=40, direction="negative"),
            ),
            [
                match_record("cA1", "A101", score=1.0),
                match_record("cB1", "A304", score=1.0),
                match_record("cA2", "A301", score=0.3),
                match_record("cB2", "A601", score=0.3),
            ],
        )
        assert result["main_conflict"]["conflict_id"] == "A101__A304"
        scores = [c["conflict_score"] for c in result["conflicts"]]
        assert scores == sorted(scores, reverse=True)

    def test_tie_break_uses_canonical_pair_id_ascending(self):
        # Two independent two-alpha taxonomies produce identical scores by
        # construction, so canonical pair ID must break the tie.
        taxonomy = {
            **two_alpha_taxonomy("A101", "A304", weight_a_to_b=0.5),
            **two_alpha_taxonomy("A301", "A601", weight_a_to_b=0.5),
        }
        activation = activation_payload(
            activation_entry("A101", score=80, direction="positive"),
            activation_entry("A304", score=80, direction="negative"),
            activation_entry("A301", score=80, direction="positive"),
            activation_entry("A601", score=80, direction="negative"),
        )
        matches = [
            match_record("c1", "A101", score=1.0),
            match_record("c2", "A304", score=1.0),
            match_record("c3", "A301", score=1.0),
            match_record("c4", "A601", score=1.0),
        ]
        result = _detect(activation, matches, taxonomy=taxonomy)
        assert len(result["conflicts"]) == 2
        assert result["conflicts"][0]["conflict_score"] == result["conflicts"][1]["conflict_score"]
        assert result["main_conflict"]["conflict_id"] == "A101__A304"  # "A101__A304" < "A301__A601"

    def test_rounding_does_not_change_main_conflict_ranking(self):
        # Two candidates whose *rounded* scores tie but whose true
        # (unrounded) scores differ must still rank by the true value.
        taxonomy = {
            **two_alpha_taxonomy("A101", "A304", weight_a_to_b=0.7000005),
            **two_alpha_taxonomy("A301", "A601", weight_a_to_b=0.7),
        }
        activation = activation_payload(
            activation_entry("A101", score=50, direction="positive"),
            activation_entry("A304", score=50, direction="negative"),
            activation_entry("A301", score=50, direction="positive"),
            activation_entry("A601", score=50, direction="negative"),
        )
        matches = [
            match_record("c1", "A101", score=1.0),
            match_record("c2", "A304", score=1.0),
            match_record("c3", "A301", score=1.0),
            match_record("c4", "A601", score=1.0),
        ]
        result = _detect(activation, matches, taxonomy=taxonomy)
        # A101-A304's true score is fractionally higher even though both
        # round to the same displayed 4-decimal value at this magnitude.
        assert result["conflicts"][0]["conflict_score"] == result["conflicts"][1]["conflict_score"]
        assert result["main_conflict"]["conflict_id"] == "A101__A304"

        reversed_result = _detect(
            activation_payload(*reversed(activation["alphas"])),
            list(reversed(matches)),
            taxonomy=dict(reversed(list(taxonomy.items()))),
        )
        assert reversed_result["main_conflict"]["conflict_id"] == "A101__A304"
        assert json.dumps(result, sort_keys=True) == json.dumps(reversed_result, sort_keys=True)

    def test_no_admitted_conflicts_yields_empty_list_and_null_main_conflict(self):
        result = _detect(activation_payload(), [])
        assert result["conflicts"] == []
        assert result["main_conflict"] is None

    def test_conflicts_list_itself_is_stably_sorted(self):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=95, direction="positive"),
                activation_entry("A304", score=95, direction="negative"),
                activation_entry("A001", score=50, direction="positive"),
                activation_entry("A501", score=50, direction="negative"),
            ),
            [
                match_record("c1", "A101", score=1.0),
                match_record("c2", "A304", score=1.0),
                match_record("c3", "A001", score=0.5),
                match_record("c4", "A501", score=0.5),
            ],
        )
        assert [c["conflict_id"] for c in result["conflicts"]] == [
            c["conflict_id"] for c in sorted(result["conflicts"], key=lambda c: -c["conflict_score"])
        ]

    def test_arbitration_does_not_backfill_from_suppressed_or_rejected(self):
        result = _detect(
            activation_payload(activation_entry("A101", score=10, status="inactive", direction="positive")),
            [],
        )
        assert result["conflicts"] == []
        assert result["main_conflict"] is None
        assert result["arbitration"]["admitted_count"] == 0


class TestDeterminism:
    def _fixture(self):
        activation = activation_payload(
            activation_entry("A101", score=80, direction="positive"),
            activation_entry("A304", score=60, direction="negative"),
            activation_entry("A301", score=55, direction="positive"),
            activation_entry("A601", score=45, direction="negative"),
        )
        matches = [
            match_record("c1", "A101", score=0.9, agent="news_agent"),
            match_record("c2", "A304", score=0.8, agent="technical_agent"),
            match_record("c3", "A301", score=0.6, agent="fundamental_agent"),
            match_record("c4", "A601", score=0.5, agent="sentiment_agent"),
        ]
        return activation, matches

    def test_repeated_execution_produces_identical_serialization(self):
        activation, matches = self._fixture()
        first = json.dumps(_detect(activation, matches), sort_keys=True)
        second = json.dumps(_detect(activation, matches), sort_keys=True)
        assert first == second

    def test_alpha_matches_input_order_does_not_affect_result(self):
        activation, matches = self._fixture()
        forward = _detect(activation, matches)
        backward = _detect(activation, list(reversed(matches)))
        assert json.dumps(forward, sort_keys=True) == json.dumps(backward, sort_keys=True)

    def test_activation_entries_input_order_does_not_affect_result(self):
        activation, matches = self._fixture()
        reordered = activation_payload(*list(reversed(activation["alphas"])))
        forward = _detect(activation, matches)
        backward = _detect(reordered, matches)
        assert json.dumps(forward, sort_keys=True) == json.dumps(backward, sort_keys=True)

    def test_taxonomy_input_order_does_not_affect_result(self):
        taxonomy = load_alpha_taxonomy()
        reordered_taxonomy = dict(reversed(list(taxonomy.items())))
        activation, matches = self._fixture()
        forward = _detect(activation, matches, taxonomy=taxonomy)
        backward = _detect(activation, matches, taxonomy=reordered_taxonomy)
        assert json.dumps(forward, sort_keys=True) == json.dumps(backward, sort_keys=True)

    def test_no_wall_clock_or_random_dependence_in_source(self):
        source = inspect.getsource(conflict_detector) + inspect.getsource(conflict_schema)
        for forbidden in ("datetime.now", "time.time(", "uuid.uuid4", "random.", "os.urandom"):
            assert forbidden not in source


class TestReasonCodeHygiene:
    def test_reason_codes_are_deduplicated_and_stably_ordered(self):
        result = _detect(
            activation_payload(activation_entry("A101", score=10, status="inactive", direction="positive")),
            [],
        )
        item = _outcome_for(result, "A101", "A304")
        assert item["reason_codes"] == list(dict.fromkeys(item["reason_codes"]))  # no duplicates

    def test_reason_codes_never_contain_raw_exception_or_path_text(self):
        result = _detect(
            activation_payload(activation_entry("A101", score=float("nan"), direction="positive")),
            [],
        )
        serialized = json.dumps(result)
        for forbidden in ("Traceback", "/Users/", "/private/", "site-packages", "line "):
            assert forbidden not in serialized


class TestInputValidation:
    def test_empty_run_id_raises_schema_invalid(self):
        with pytest.raises(ConflictInputError) as exc_info:
            _detect(activation_payload(), [], run_id="")
        assert exc_info.value.reason_code == "SCHEMA_INVALID"

    def test_empty_ticker_raises_schema_invalid(self):
        with pytest.raises(ConflictInputError) as exc_info:
            _detect(activation_payload(), [], ticker="")
        assert exc_info.value.reason_code == "SCHEMA_INVALID"

    def test_non_mapping_activation_payload_raises_schema_invalid(self):
        with pytest.raises(ConflictInputError):
            _detect("not-a-mapping", [])

    def test_activation_without_alphas_list_raises_schema_invalid(self):
        with pytest.raises(ConflictInputError):
            _detect(
                {
                    "formula_version": ACTIVATION_FORMULA_VERSION,
                    "alphas": "not-a-list",
                },
                [],
            )

    def test_official_activation_formula_version_is_accepted(self):
        result = _detect(activation_payload(), [])
        assert result["arbitration"]["declared_pair_count"] == 6

    @pytest.mark.parametrize("payload", [{"alphas": []}, {"formula_version": "", "alphas": []}])
    def test_missing_or_empty_activation_formula_version_is_rejected(self, payload):
        with pytest.raises(ConflictInputError) as exc_info:
            _detect(payload, [])
        assert exc_info.value.reason_code == "ACTIVATION_VERSION_MISMATCH"

    def test_wrong_activation_formula_version_is_rejected(self):
        payload = {**activation_payload(), "formula_version": "week3.activation.wrong"}
        with pytest.raises(ConflictInputError) as exc_info:
            _detect(payload, [])
        assert exc_info.value.reason_code == "ACTIVATION_VERSION_MISMATCH"

    def test_unknown_activation_alpha_is_rejected(self):
        payload = activation_payload(activation_entry("A999"))
        with pytest.raises(ConflictInputError) as exc_info:
            _detect(payload, [])
        assert exc_info.value.reason_code == "UNKNOWN_ACTIVATION_ALPHA"

    def test_partial_activation_payload_reaches_candidate_missing_side_logic(self):
        result = _detect(
            activation_payload(activation_entry("A101", score=90, direction="positive")),
            [match_record("cA", "A101")],
        )
        item = _outcome_for(result, "A101", "A304")
        assert item["outcome"] == "rejected"
        assert "MISSING_RIGHT_ACTIVATION" in item["reason_codes"]

    def test_non_sequence_alpha_matches_raises_schema_invalid(self):
        with pytest.raises(ConflictInputError):
            _detect(activation_payload(), object())

    def test_duplicate_alpha_id_in_activation_payload_raises_schema_invalid(self):
        with pytest.raises(ConflictInputError):
            _detect(
                activation_payload(
                    activation_entry("A101", score=10),
                    activation_entry("A101", score=90),
                ),
                [],
            )

    def test_exception_never_carries_reason_text_beyond_the_code(self):
        try:
            _detect(activation_payload(), [], run_id="")
        except ConflictInputError as exc:
            assert str(exc) == exc.reason_code

    def test_embedded_run_id_mismatch_rejects_all_candidates(self):
        activation = {**activation_payload(), "run_id": "some_other_run"}
        result = _detect(activation, [])
        assert result["conflicts"] == []
        assert result["main_conflict"] is None
        assert result["arbitration"]["rejected_count"] == 6
        for item in result["arbitration"]["candidate_evaluations"]:
            assert item["reason_codes"] == ["RUN_ID_MISMATCH"]

    def test_embedded_ticker_mismatch_rejects_all_candidates(self):
        activation = {**activation_payload(), "ticker": "SOME_OTHER_TICKER"}
        result = _detect(activation, [])
        assert result["arbitration"]["rejected_count"] == 6
        for item in result["arbitration"]["candidate_evaluations"]:
            assert item["reason_codes"] == ["TICKER_MISMATCH"]

    def test_match_record_with_matching_embedded_run_id_is_unaffected(self):
        matches = [{**match_record("cA", "A101"), "run_id": RUN_ID}]
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, direction="positive"),
                activation_entry("A304", score=90, direction="negative"),
            ),
            [*matches, match_record("cB", "A304")],
        )
        assert result["main_conflict"] is not None

    def test_match_record_with_mismatching_embedded_run_id_rejects_all(self):
        matches = [{**match_record("cA", "A101"), "run_id": "other_run"}]
        result = _detect(activation_payload(), matches)
        assert result["arbitration"]["rejected_count"] == 6


class TestExplanationLanguageGuard:
    _FORBIDDEN_PHRASES = (
        "Buy",
        "Sell",
        "Hold",
        "Strong Buy",
        "Strong Sell",
        "You should buy",
        "You should sell",
        "Guaranteed return",
        "Guaranteed upside",
        "Will rise",
        "Will fall",
    )

    def _explanation(self):
        result = _detect(
            activation_payload(
                activation_entry("A101", score=90, direction="positive", name="AI Expansion"),
                activation_entry("A304", score=90, direction="negative", name="Multiple Compression"),
            ),
            [match_record("cA", "A101"), match_record("cB", "A304")],
        )
        return result["main_conflict"]["explanation"]

    def test_explanation_mentions_both_alpha_names(self):
        explanation = self._explanation()
        assert "AI Expansion" in explanation
        assert "Multiple Compression" in explanation

    def test_explanation_mentions_conflict_level(self):
        assert conflict_level  # sanity import check
        explanation = self._explanation()
        assert any(level in explanation for level in ("low", "medium", "medium_high", "high"))

    def test_explanation_is_deterministic(self):
        assert self._explanation() == self._explanation()

    def test_explanation_never_contains_trading_advice_language(self):
        explanation = self._explanation()
        for phrase in self._FORBIDDEN_PHRASES:
            assert phrase not in explanation
            assert phrase.lower() not in explanation.lower()

    def test_no_ticker_specific_copy_in_explanation(self):
        explanation = self._explanation()
        for ticker in ("NVDA", "QQQ", "MSFT", "AMD", "SPY"):
            assert ticker not in explanation


class TestNoTickerSpecificProductionCode:
    def test_detector_source_has_no_ticker_literal_branching(self):
        source = inspect.getsource(conflict_detector)
        for literal in ('"NVDA"', "'NVDA'", '"QQQ"', "'QQQ'", '"MSFT"', "'MSFT'"):
            assert literal not in source

    def test_schema_source_has_no_ticker_literal_branching(self):
        source = inspect.getsource(conflict_schema)
        for literal in ('"NVDA"', "'NVDA'", '"QQQ"', "'QQQ'", '"MSFT"', "'MSFT'"):
            assert literal not in source


class TestSinglePairHelper:
    def test_pair_not_declared_is_rejected(self):
        result = evaluate_conflict_pair(
            "A102", "A304", activation_payload=activation_payload(), alpha_matches=[]
        )
        assert result["outcome"] == "rejected"
        assert result["reason_codes"] == ["PAIR_NOT_DECLARED"]

    def test_declared_pair_can_be_evaluated_directly(self):
        result = evaluate_conflict_pair(
            "A304",
            "A101",  # reversed order on purpose
            activation_payload=activation_payload(
                activation_entry("A101", score=90, direction="positive"),
                activation_entry("A304", score=90, direction="negative"),
            ),
            alpha_matches=[match_record("cA", "A101"), match_record("cB", "A304")],
        )
        assert result["outcome"] == "admitted"
        assert result["conflict"]["conflict_id"] == "A101__A304"


class TestMSFTBoundary:
    """MSFT's Golden Case (A102 vs A304) is a product-specification conflict
    documented as BLOCKED_BY_SPEC_CONFLICT in
    docs/week4_spec_freeze_audit.md -- not a per-run suppressed/deferred
    candidate. This class only pins down that the boundary holds; it does
    not implement, fixture, or otherwise attempt the MSFT Golden Case
    itself."""

    def test_a102_a304_is_not_declared_in_the_real_taxonomy(self):
        taxonomy = load_alpha_taxonomy()
        a102_conflicts = {c.alpha_id for c in taxonomy["A102"].conflict_alphas}
        a304_conflicts = {c.alpha_id for c in taxonomy["A304"].conflict_alphas}
        assert "A304" not in a102_conflicts
        assert "A102" not in a304_conflicts

    def test_real_taxonomy_loader_never_returns_a102_a304_as_a_declared_pair(self):
        result = _detect(activation_payload(), [])  # uses the real default taxonomy
        pairs = {(c["alpha_a"], c["alpha_b"]) for c in result["arbitration"]["candidate_evaluations"]}
        assert canonical_pair_key("A102", "A304") not in pairs
        assert result["arbitration"]["declared_pair_count"] == 6

    def test_detector_never_generates_a102_a304_even_with_strong_evidence_for_both(self):
        # Even with strong, well-formed evidence for A102 and A304
        # individually, the pair must never be synthesized -- admissibility
        # requires taxonomy declaration first, and A102-A304 has none.
        result = _detect(
            activation_payload(
                activation_entry("A102", score=95, status="dominant", direction="positive"),
                activation_entry("A304", score=95, status="dominant", direction="negative"),
            ),
            [
                match_record("c1", "A102", score=1.0, relation="activation"),
                match_record("c2", "A304", score=1.0, relation="activation"),
            ],
        )
        pairs = {(c["alpha_a"], c["alpha_b"]) for c in result["arbitration"]["candidate_evaluations"]}
        assert canonical_pair_key("A102", "A304") not in pairs
        conflict_ids = {c["conflict_id"] for c in result["conflicts"]}
        assert "A102__A304" not in conflict_ids
        assert "A304__A102" not in conflict_ids

    def test_single_pair_helper_rejects_a102_a304_as_not_declared(self):
        result = evaluate_conflict_pair(
            "A102",
            "A304",
            activation_payload=activation_payload(
                activation_entry("A102", score=95, direction="positive"),
                activation_entry("A304", score=95, direction="negative"),
            ),
            alpha_matches=[match_record("c1", "A102"), match_record("c2", "A304")],
        )
        assert result["outcome"] == "rejected"
        assert result["reason_codes"] == ["PAIR_NOT_DECLARED"]

    def test_spec_freeze_audit_still_documents_msft_as_blocked(self):
        from pathlib import Path

        doc_path = Path(__file__).resolve().parents[1] / "docs" / "week4_spec_freeze_audit.md"
        text = doc_path.read_text(encoding="utf-8")
        assert "BLOCKED_BY_SPEC_CONFLICT" in text
        assert "MSFT" in text
