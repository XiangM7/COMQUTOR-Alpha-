"""AI Alpha Mapper Discrimination Sprint: closes over-triggering and shared
generic-keyword collisions between A101 (AI Expansion), A102 (Inference
Explosion), and A103 (AI Infrastructure).

This is an implementation/verification Sprint, not a frozen contract --
``tests/fixtures/ai_alpha_mapper_golden_v1.json`` is the current
implementation's acceptance Golden Set, expected to evolve as the mapper
improves. Nothing here creates a new Alpha, changes taxonomy content,
touches Activation/Graph/Conflict/Exposure/Data Sanity, or persists any
artifact.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.structure_engine.ai_alpha_discriminator import (
    AI_ALPHA_IDS,
    evaluate_ai_alpha_gates,
    normalize_claim_for_gate,
)
from comqutor_alpha.structure_engine.alpha_mapper import map_claim_to_alpha

GOLDEN_SET_PATH = Path(__file__).parent / "fixtures" / "ai_alpha_mapper_golden_v1.json"


def _load_golden_set() -> list[dict]:
    with GOLDEN_SET_PATH.open(encoding="utf-8") as f:
        payload = json.load(f)
    return payload["cases"]


GOLDEN_CASES = _load_golden_set()


def _record(text: str, *, direction: str = "neutral", claim_id: str = "c1") -> dict:
    return {
        "run_id": "run1",
        "ticker": "TEST",
        "agent": "news_agent",
        "claim_id": claim_id,
        "claim": text,
        "evidence": text,
        "factors": [],
        "direction": direction,
    }


def _ai_matches(text: str, **kwargs) -> set[str]:
    return set(map_claim_to_alpha(_record(text, **kwargs))["ai_alpha_matches"])


# ---------------------------------------------------------------------------
# Golden Set (test requirement #1)
# ---------------------------------------------------------------------------


class TestGoldenSet:
    def test_golden_set_has_at_least_45_cases_with_required_distribution(self):
        assert len(GOLDEN_CASES) >= 45
        from collections import Counter

        distribution = Counter(tuple(sorted(c["expected_alpha_ids"])) for c in GOLDEN_CASES)
        assert distribution[("A101",)] >= 8
        assert distribution[("A102",)] >= 8
        assert distribution[("A103",)] >= 8
        assert distribution[("A101", "A102")] >= 3
        assert distribution[("A101", "A103")] >= 3
        assert distribution[("A102", "A103")] >= 3
        assert distribution[("A101", "A102", "A103")] >= 2
        assert distribution[()] >= 10

    def test_golden_set_case_ids_are_unique(self):
        case_ids = [c["case_id"] for c in GOLDEN_CASES]
        assert len(case_ids) == len(set(case_ids))

    @pytest.mark.parametrize("case", GOLDEN_CASES, ids=[c["case_id"] for c in GOLDEN_CASES])
    def test_golden_case(self, case):
        result = map_claim_to_alpha(_record(case["claim_text"], direction=case.get("direction", "neutral")))
        actual = sorted(result["ai_alpha_matches"])
        expected = sorted(case["expected_alpha_ids"])
        assert actual == expected, case["description"]
        for rejected_id in case.get("expected_rejected_alpha_ids", []):
            assert rejected_id not in actual, (
                f"{case['case_id']}: {rejected_id} must not match -- {case['description']}"
            )


# ---------------------------------------------------------------------------
# Per-Alpha hard gates (#2-4)
# ---------------------------------------------------------------------------


class TestA101HardGate:
    @pytest.mark.parametrize(
        "text",
        [
            "AI training demand increased.",
            "GPU orders increased.",
            "AI capex funded new equipment.",
            "AI adoption accelerated across the enterprise customer base.",
        ],
    )
    def test_admits_with_anchor_and_predicate(self, text):
        assert "A101" in _ai_matches(text, direction="positive")

    @pytest.mark.parametrize(
        "text",
        [
            "GPU is a widely used term in the industry.",
            "AI adoption remains a talking point.",
        ],
    )
    def test_rejects_anchor_without_predicate_or_static_mention(self, text):
        assert "A101" not in _ai_matches(text)

    def test_adoption_alone_suppressed_when_a102_also_passes(self):
        text = "AI adoption increased as inference requests also increased."
        matches = _ai_matches(text, direction="positive")
        assert "A102" in matches
        assert "A101" not in matches, (
            "A101's only qualifying group here is bare AI adoption, and A102 "
            "already passed independently -- A101 must be suppressed."
        )

    def test_adoption_alone_still_admits_when_a102_does_not_pass(self):
        text = "AI adoption increased across the enterprise customer base."
        matches = _ai_matches(text, direction="positive")
        assert "A101" in matches
        assert "A102" not in matches


class TestA102HardGate:
    @pytest.mark.parametrize(
        "text",
        [
            "Inference requests increased.",
            "Token generation doubled.",
            "AI agent workloads expanded.",
            "Enterprise AI application usage rose.",
        ],
    )
    def test_admits_with_inference_specific_anchor_and_predicate(self, text):
        assert "A102" in _ai_matches(text, direction="positive")

    @pytest.mark.parametrize(
        "text",
        [
            "GPU demand increased.",
            "Cloud providers raised AI capex.",
            "AI demand remains strong.",
            "Data-center construction accelerated.",
            "Enterprise AI remains a strategic priority.",
        ],
    )
    def test_rejects_generic_terms(self, text):
        assert "A102" not in _ai_matches(text, direction="positive")

    def test_ai_agents_as_static_noun_alone_does_not_admit(self):
        assert "A102" not in _ai_matches("The roadmap mentions AI agents as a future initiative.")


class TestA103HardGate:
    @pytest.mark.parametrize(
        "text",
        [
            "Data-center construction increased.",
            "Server orders rose.",
            "Networking demand weakened.",
            "Power infrastructure expansion was delayed.",
            "Liquid-cooling capacity increased.",
        ],
    )
    def test_admits_with_physical_infrastructure_anchor_and_predicate(self, text):
        assert "A103" in _ai_matches(text)

    def test_rejects_datacenter_as_bare_location(self):
        assert "A103" not in _ai_matches("Inference workloads in data centers increased.", direction="positive")

    def test_rejects_datacenter_stock_price_context(self):
        assert "A103" not in _ai_matches("Data-center stocks rallied.")

    def test_rejects_server_as_static_product_name(self):
        assert "A103" not in _ai_matches("The server is a core product in the company's lineup.")


# ---------------------------------------------------------------------------
# Generic-term rejection (#5-8)
# ---------------------------------------------------------------------------


class TestGenericTermsNeverAdmitAlone:
    @pytest.mark.parametrize(
        "text",
        [
            "AI is important.",
            "The company talked about artificial intelligence.",
            "Technology stocks were mixed today.",
        ],
    )
    def test_generic_ai_never_triggers(self, text):
        assert _ai_matches(text) == set()

    def test_generic_cloud_never_triggers(self):
        assert _ai_matches("The company discussed its cloud strategy.") == set()

    def test_generic_capex_never_triggers(self):
        assert _ai_matches("Capex guidance was reaffirmed for the fiscal year.") == set()

    def test_datacenter_as_location_never_triggers_a103(self):
        matches = _ai_matches("Inference workloads in data centers increased.", direction="positive")
        assert "A103" not in matches


# ---------------------------------------------------------------------------
# Alpha-specific admission (#9-10)
# ---------------------------------------------------------------------------


def test_a102_requires_inference_specific_evidence():
    assert _ai_matches("Inference traffic increased.", direction="positive") == {"A102"}
    assert _ai_matches("GPU demand increased.", direction="positive") == {"A101"}


def test_a103_requires_physical_infrastructure_evidence():
    assert _ai_matches("Server orders increased.", direction="positive") == {"A103"}
    assert _ai_matches("AI demand increased.", direction="positive") == set()


# ---------------------------------------------------------------------------
# Pairwise disambiguation (#11-13)
# ---------------------------------------------------------------------------


class TestPairwiseDisambiguation:
    def test_a101_a102(self):
        assert _ai_matches("AI training demand increased.", direction="positive") == {"A101"}
        assert _ai_matches("Inference demand increased.", direction="positive") == {"A102"}

    def test_a102_a103(self):
        assert _ai_matches("Inference workloads in data centers increased.", direction="positive") == {"A102"}
        assert _ai_matches("Data-center power and cooling demand increased.", direction="positive") == {"A103"}

    def test_a101_a103(self):
        assert _ai_matches("Cloud providers raised AI investment.", direction="positive") == {"A101"}
        assert _ai_matches("Cloud providers built new data-center capacity.", direction="positive") == {"A103"}


# ---------------------------------------------------------------------------
# Multi-match (#14-15) and No Propagation (#16)
# ---------------------------------------------------------------------------


class TestMultiMatch:
    def test_reasonable_double_match(self):
        assert _ai_matches(
            "AI capex funded new servers and cooling capacity.", direction="positive"
        ) == {"A101", "A103"}

    def test_reasonable_triple_match(self):
        assert _ai_matches(
            "AI training demand grew, inference requests increased, and the company added new server capacity.",
            direction="positive",
        ) == {"A101", "A102", "A103"}

    def test_single_fact_claim_never_forces_a_second_alpha(self):
        assert _ai_matches("Inference workloads in data centers increased.", direction="positive") == {"A102"}


class TestNoPropagation:
    def test_a101_only_claim_never_gains_a103(self):
        assert _ai_matches("AI training demand increased.", direction="positive") == {"A101"}

    def test_a102_only_claim_never_gains_a103(self):
        assert _ai_matches("Inference workloads increased.", direction="positive") == {"A102"}

    def test_a103_only_claim_never_gains_a101_or_a102(self):
        assert _ai_matches("Server orders increased.", direction="positive") == {"A103"}

    def test_mapper_never_reads_taxonomy_relations(self):
        """Stripping every alpha's .relations must not change any mapping
        result -- proves the Mapper itself never consults relations to
        create an additional match (that remains exclusively a Structure
        Graph concern)."""
        taxonomy = load_alpha_taxonomy()
        relation_free_taxonomy = {
            alpha_id: dataclasses.replace(alpha, relations=[]) for alpha_id, alpha in taxonomy.items()
        }
        texts = [
            "AI training demand increased.",
            "Inference workloads increased.",
            "Server orders increased.",
            "AI capex funded new servers and cooling capacity.",
            "Revenue guidance was raised due to strong customer demand.",
        ]
        for text in texts:
            with_relations = map_claim_to_alpha(_record(text, direction="positive"), taxonomy)
            without_relations = map_claim_to_alpha(_record(text, direction="positive"), relation_free_taxonomy)
            assert with_relations["ai_alpha_matches"] == without_relations["ai_alpha_matches"]
            assert with_relations["matched_alpha"] == without_relations["matched_alpha"]

    def test_alpha_mapper_source_never_reads_dot_relations(self):
        import inspect

        from comqutor_alpha.structure_engine import alpha_mapper

        source = inspect.getsource(alpha_mapper)
        assert ".relations" not in source


# ---------------------------------------------------------------------------
# Normalization: word/phrase boundary, case, punctuation, order (#17-21)
# ---------------------------------------------------------------------------


class TestNormalization:
    def test_word_boundary_ai_does_not_match_unrelated_words(self):
        text = "The chairman said the outlook was positive amid strong retail chair demand."
        assert _ai_matches(text, direction="positive") == set()

    def test_word_boundary_rack_does_not_match_track(self):
        gates = evaluate_ai_alpha_gates("The track record improved this quarter.")
        assert not gates["A103"].passed

    def test_word_boundary_agent_does_not_match_agency(self):
        gates = evaluate_ai_alpha_gates("The agency reported higher spending this year.")
        assert not gates["A102"].passed

    def test_phrase_boundary_ai_capex_requires_full_phrase(self):
        # "AI" followed by an unrelated word, then "capex" elsewhere, must
        # not be treated as the "AI capex" anchor phrase.
        gates = evaluate_ai_alpha_gates("AI is popular; capex overall increased.")
        assert not gates["A101"].passed

    def test_case_insensitivity(self):
        lower = _ai_matches("gpu orders increased.", direction="positive")
        upper = _ai_matches("GPU ORDERS INCREASED.", direction="positive")
        mixed = _ai_matches("Gpu Orders Increased.", direction="positive")
        assert lower == upper == mixed == {"A101"}

    def test_punctuation_variation_does_not_affect_result(self):
        base = _ai_matches("GPU orders increased.", direction="positive")
        no_period = _ai_matches("GPU orders increased", direction="positive")
        extra_space = _ai_matches("GPU   orders    increased.", direction="positive")
        assert base == no_period == extra_space == {"A101"}

    def test_hyphen_variation_does_not_affect_result(self):
        hyphenated = _ai_matches("Pre-training demand increased.", direction="positive")
        spaced = _ai_matches("Pre training demand increased.", direction="positive")
        assert hyphenated == spaced == {"A101"}

    def test_normalize_claim_for_gate_is_deterministic_and_idempotent(self):
        text = "  GPU-Demand   Increased!! "
        first = normalize_claim_for_gate(text)
        second = normalize_claim_for_gate(text)
        assert first == second
        assert normalize_claim_for_gate(first) == first

    def test_input_order_independence_across_repeated_calls(self):
        """Calling the gate multiple times, or in a different order relative
        to other claims, never changes any individual result (no shared
        mutable state)."""
        text_a = "GPU orders increased."
        text_b = "Server orders increased."
        first_pass = (_ai_matches(text_a, direction="positive"), _ai_matches(text_b, direction="positive"))
        second_pass = (_ai_matches(text_b, direction="positive"), _ai_matches(text_a, direction="positive"))
        assert first_pass == (second_pass[1], second_pass[0])


# ---------------------------------------------------------------------------
# Mutation tests (#22) -- prove the hard gates are load-bearing
# ---------------------------------------------------------------------------


class TestMutationsProveGatesAreLoadBearing:
    def test_removing_inference_anchor_breaks_a102(self):
        assert "A102" in _ai_matches("Inference requests increased.", direction="positive")
        assert "A102" not in _ai_matches("Requests increased.", direction="positive")

    def test_removing_usage_predicate_breaks_a102(self):
        assert "A102" in _ai_matches("Inference requests increased.", direction="positive")
        assert "A102" not in _ai_matches("Inference requests exist.", direction="positive")

    def test_replacing_inference_with_generic_ai_breaks_a102(self):
        assert "A102" in _ai_matches("Inference demand increased.", direction="positive")
        assert "A102" not in _ai_matches("AI demand increased.", direction="positive") or True
        # "AI demand increased" legitimately admits A101 (training-adjacent
        # generic demand is still not an A102 anchor); the mutation proves
        # specifically that A102 no longer admits once "inference" is gone.
        assert "A102" not in _ai_matches("AI demand increased.", direction="positive")

    def test_removing_physical_anchor_breaks_a103(self):
        assert "A103" in _ai_matches("Server orders increased.", direction="positive")
        assert "A103" not in _ai_matches("Orders increased.", direction="positive")

    def test_removing_buildout_predicate_breaks_a103(self):
        assert "A103" in _ai_matches("Server orders increased.", direction="positive")
        assert "A103" not in _ai_matches("Servers exist.", direction="positive")

    def test_datacenter_construction_to_stocks_breaks_a103(self):
        # Mutating both the predicate (increased -> rallied) and the object
        # (construction -> stocks) turns a genuine buildout claim into pure
        # stock-price commentary: "rallied" is not a buildout/demand/order/
        # capacity change predicate, so A103 must no longer admit even
        # though the "data center" anchor text is still present.
        assert "A103" in _ai_matches("Data-center construction increased.", direction="positive")
        assert "A103" not in _ai_matches("Data-center stocks rallied.", direction="positive")

    def test_removing_a101_anchor_breaks_a101(self):
        assert "A101" in _ai_matches("AI training demand increased.", direction="positive")
        assert "A101" not in _ai_matches("Demand increased.", direction="positive")

    def test_ai_capex_to_generic_capex_breaks_a101(self):
        assert "A101" in _ai_matches("AI capex increased.", direction="positive")
        assert "A101" not in _ai_matches("Capex increased.", direction="positive")

    def test_adding_datacenter_location_to_a102_claim_does_not_add_a103(self):
        without_location = _ai_matches("Inference requests increased.", direction="positive")
        with_location = _ai_matches("Inference requests in data centers increased.", direction="positive")
        assert without_location == {"A102"}
        assert with_location == {"A102"}
        assert "A103" not in with_location

    def test_adding_generic_infrastructure_to_a101_claim_does_not_add_a103(self):
        without_infra = _ai_matches("AI training demand increased.", direction="positive")
        with_infra = _ai_matches(
            "AI training demand increased as part of the company's broader AI infrastructure strategy.",
            direction="positive",
        )
        assert without_infra == {"A101"}
        assert with_infra == {"A101"}
        assert "A103" not in with_infra


# ---------------------------------------------------------------------------
# Match-score protection: score formula unchanged, generic stacking never
# admits on its own
# ---------------------------------------------------------------------------


class TestMatchScoreProtection:
    def test_generic_word_stacking_does_not_admit_a102(self):
        text = "AI cloud server usage was discussed at the conference."
        assert "A102" not in _ai_matches(text)

    def test_ai_and_datacenter_without_predicate_does_not_admit_a103(self):
        assert "A103" not in _ai_matches("AI data center strategy was outlined.")

    def test_score_formula_weights_are_unchanged(self):
        from comqutor_alpha.structure_engine import alpha_mapper

        assert alpha_mapper.FACTOR_ALPHA_WEIGHTS["AI CapEx"] == {"A101": 0.85, "A103": 0.75, "A301": 0.35}
        assert alpha_mapper.GENERIC_KEYWORD_WEIGHTS["ai"] == 0.35
        assert alpha_mapper.GENERIC_KEYWORD_WEIGHTS["inference"] == 0.55


# ---------------------------------------------------------------------------
# Non-AI Alpha regression (#23)
# ---------------------------------------------------------------------------

# Baseline recorded from the exact pre-Sprint alpha_mapper.py (git show
# HEAD:comqutor_alpha/structure_engine/alpha_mapper.py, run standalone via
# importlib before any change in this Sprint was applied). Two
# representative claims per non-AI Alpha, capturing matched_alpha, score,
# and matched_keywords -- the post-Sprint mapper must reproduce every field
# exactly, since none of these Alphas are in AI_ALPHA_IDS and the new gate
# branch in _candidate_score never executes for them.
NON_AI_REGRESSION_BASELINE = [
    {
        "text": "Falling rates are expected to support long-duration growth assets.",
        "alpha_id": "A001", "score": 0.8846,
        "matched_keywords": ["duration", "falling rates"],
    },
    {
        "text": "Rate cuts are supporting duration-sensitive growth assets.",
        "alpha_id": "A001", "score": 0.3923,
        "matched_keywords": ["duration"],
    },
    {
        "text": "Improving liquidity conditions are supporting broad equity inflows.",
        "alpha_id": "A003", "score": 0.5846,
        "matched_keywords": ["liquidity", "liquidity conditions"],
    },
    {
        "text": "Reserves are rising as liquidity conditions ease.",
        "alpha_id": "A003", "score": 0.7,
        "matched_keywords": ["liquidity", "liquidity conditions", "reserves"],
    },
    {
        "text": "Semiconductor inventory is improving and chip demand is recovering.",
        "alpha_id": "A201", "score": 0.9519,
        "matched_keywords": ["chip", "chip demand", "semiconductor"],
    },
    {
        "text": "Wafer orders are rising as the semiconductor cycle improves.",
        "alpha_id": "A201", "score": 1.0,
        "matched_keywords": ["orders", "semiconductor", "wafer"],
    },
    {
        "text": "Revenue guidance was raised due to strong customer demand.",
        "alpha_id": "A301", "score": 0.4596,
        "matched_keywords": ["customer demand", "revenue"],
    },
    {
        "text": "Strong demand is driving accelerating revenue growth.",
        "alpha_id": "A301", "score": 0.9519,
        "matched_keywords": ["revenue", "revenue growth", "strong demand"],
    },
    {
        "text": "High valuation is creating downside risk for the stock.",
        "alpha_id": "A304", "score": 0.9008,
        "matched_keywords": ["downside risk", "high valuation", "valuation"],
    },
    {
        "text": "Rich valuation leaves the stock vulnerable to multiple compression.",
        "alpha_id": "A304", "score": 0.92,
        "matched_keywords": ["multiple compression", "rich valuation", "valuation"],
    },
    {
        "text": "Credit spreads are widening and recession risk is rising.",
        "alpha_id": "A501", "score": 0.92,
        "matched_keywords": ["credit spreads", "recession", "recession risk"],
    },
    {
        "text": "Widening credit spreads signal rising recession risk.",
        "alpha_id": "A501", "score": 0.92,
        "matched_keywords": ["credit spreads", "recession", "recession risk"],
    },
    {
        "text": "AI stocks are rising due to strong investor attention.",
        "alpha_id": "A601", "score": 1.0,
        "matched_keywords": ["ai stocks", "attention", "investor attention"],
    },
    {
        "text": "Investor attention and crowded positioning are driving momentum.",
        "alpha_id": "A601", "score": 0.9711,
        "matched_keywords": ["attention", "investor attention", "momentum"],
    },
]


class TestNonAiAlphaRegression:
    @pytest.mark.parametrize(
        "baseline",
        NON_AI_REGRESSION_BASELINE,
        ids=[f"{b['alpha_id']}_{i}" for i, b in enumerate(NON_AI_REGRESSION_BASELINE)],
    )
    def test_non_ai_alpha_matching_is_byte_for_byte_unchanged(self, baseline):
        result = map_claim_to_alpha(_record(baseline["text"], direction="positive"))
        assert result["matched_alpha"] == baseline["alpha_id"]
        candidate = next(c for c in result["candidate_scores"] if c["alpha_id"] == baseline["alpha_id"])
        assert candidate["score"] == baseline["score"]
        assert candidate["matched_keywords"] == baseline["matched_keywords"]
        # Never touched by the new AI-gate branch in _candidate_score.
        assert candidate["ai_gate_passed"] is None

    def test_non_ai_alpha_ids_are_never_in_ai_alpha_ids(self):
        for baseline in NON_AI_REGRESSION_BASELINE:
            assert baseline["alpha_id"] not in AI_ALPHA_IDS


# ---------------------------------------------------------------------------
# Artifact schema compatibility (#25) and downstream input fields (#26-28)
# ---------------------------------------------------------------------------


class TestArtifactSchemaCompatibility:
    def test_new_fields_are_purely_additive(self):
        result = map_claim_to_alpha(_record("GPU orders increased.", direction="positive"))
        # Every field the pre-Sprint schema guaranteed is still present.
        for key in (
            "run_id", "ticker", "agent", "claim_id", "source_agent_output_id",
            "claim", "evidence", "factors", "direction",
            "matched_alpha", "matched_alpha_name", "score",
            "keyword_score", "factor_score", "direction_score",
            "candidate_scores", "top_candidates", "eligible_candidates",
            "plausible_alphas", "secondary_alphas", "match_status", "reason",
            "assertion_status", "semantic_polarity", "taxonomy_gap_context",
        ):
            assert key in result
        # New fields are additive, not replacements.
        assert "ai_alpha_matches" in result
        assert isinstance(result["ai_alpha_matches"], list)
        for candidate in result["candidate_scores"]:
            assert "ai_gate_passed" in candidate

    def test_non_ai_candidate_score_keys_are_unchanged(self):
        # Sprint 2 (Alpha-Relative Evidence Stance Classification) added six
        # additive keys (evidence_stance, counter_alpha_id,
        # stance_reason_codes, stance_confidence_band, requires_manual_review,
        # evidence_stance_version) to every candidate dict -- this asserts
        # every pre-existing key is still present and unchanged, not that the
        # key set is closed.
        result = map_claim_to_alpha(_record("High valuation is creating downside risk.", direction="negative"))
        candidate = next(c for c in result["candidate_scores"] if c["alpha_id"] == "A304")
        assert {
            "alpha_id", "alpha_name", "score", "keyword_score", "factor_score",
            "direction_score", "semantic_score", "relation", "eligible",
            "rejection_reason", "matched_keywords", "matched_factors", "ai_gate_passed",
        }.issubset(set(candidate))


class TestDownstreamInputFieldsUnchanged:
    """Activation/Graph/Conflict all consume alpha_matches.json's existing
    fields (matched_alpha, score, direction, factors, claim_ids, etc) --
    this Sprint adds ai_alpha_matches/ai_gate_passed as new fields only, so
    none of those consumers' input contracts change."""

    def test_matched_alpha_and_score_fields_still_drive_downstream_shape(self):
        result = map_claim_to_alpha(_record("Revenue guidance was raised due to strong customer demand.", direction="positive"))
        assert result["matched_alpha"] == "A301"
        assert isinstance(result["score"], float)
        assert isinstance(result["direction"], str)
        assert isinstance(result["factors"], list)

    def test_build_alpha_matches_payload_schema_version_unchanged(self):
        from comqutor_alpha.structure_engine.alpha_mapper import (
            MAPPER_VERSION,
            SCHEMA_VERSION,
            build_alpha_matches_payload,
        )

        payload = build_alpha_matches_payload({"run_id": "r1", "ticker": "TEST", "records": []})
        assert payload["schema_version"] == SCHEMA_VERSION == "week2.alpha_matches.v2"
        assert payload["mapper_version"] == MAPPER_VERSION == "week2.alpha_mapper.v2"
