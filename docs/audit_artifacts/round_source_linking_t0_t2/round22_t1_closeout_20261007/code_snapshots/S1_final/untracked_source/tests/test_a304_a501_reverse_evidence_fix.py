"""2026-10-02 (NVDA joint-review round): A304/A501 reverse-evidence fix.

A ChatGPT AI_REVIEW of the NVDA Fresh Run (034a0a60-430e-41f8-8321-03a11389707a)
joint-review package found that several real claims arguing recession risk
is DECREASING, or that NVDA's valuation is NOT expensive, were being counted
as `relation="activation"` (i.e. as if they were evidence FOR A501/A304's
own risk thesis materializing) instead of `relation="risk_relief"` (evidence
AGAINST it). Root cause, confirmed by direct code trace: `claim_semantics.
_RECESSION_RELIEF_PATTERNS`/`_VALUATION_RELIEF_PATTERNS` required the
easing/cheapness wording to sit in a narrow, specific grammatical shape that
several common, equally explicit real phrasings don't match (an article
between a copula and the adjective; a quantitative aside between the risk
noun and its easing verb; a PEG-ratio or "objectively cheap" valuation
argument; an explicit rebuttal of a quoted "valuation risk" framing).

The downstream mechanism that CONSUMES `relation` was already correct and
is NOT touched by this fix: `evidence_fact_index.select_supporting_alpha_
claims`'s frozen `QUALIFYING_RELATIONS = {"activation", "conditional",
"mixed"}` already excludes `risk_relief` from counting as supporting
evidence, and `activation_scorer_v2.DIRECTION_SIGNED_RELATIONS["risk_
relief"] = -1.0` already pulls direction_consistency the correct way. Only
the upstream text->relation classification had gaps for these specific
real-world phrasings -- this file locks in the fix at that layer, and one
end-to-end test proves the already-correct downstream mechanism actually
receives and uses the corrected classification.

A real, frozen-input, independent recomputation of this exact run's A304/A501
scores (before vs. after this fix, using the real score_alpha_v2 function)
is saved separately at docs/audit_artifacts/round_source_linking_t0_t2/
nvda_034a0a60_a304_a501_relation_fix_recompute_20261002.json -- NOT a Fresh
Run, no Provider call, and it never overwrites the original run's own files.
"""

from __future__ import annotations

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.graph_engine.activation_scorer_v2 import score_alpha_v2
from comqutor_alpha.structure_engine.claim_semantics import (
    alpha_relation,
    recession_risk_is_relief,
    valuation_risk_is_relief,
)

TAXONOMY = load_alpha_taxonomy()


class TestRecessionRiskEasingRealPhrasings:
    """A501 (a RISK_ALPHA_IDS member): claims asserting recession risk is
    decreasing must classify as risk_relief, not activation."""

    def test_risk_is_a_diminishing_concern(self):
        text = "At 8% and falling 2pp on the week, recession risk is a diminishing concern."
        assert recession_risk_is_relief(text) is True
        assert alpha_relation(text, "A501") == "risk_relief"

    def test_risk_at_n_percent_and_falling(self):
        text = "Recession risk at 8% and falling is a structural tailwind for AI capex durability."
        assert recession_risk_is_relief(text) is True
        assert alpha_relation(text, "A501") == "risk_relief"

    def test_categorical_signal_framing_remains_an_unfixed_known_gap(self):
        """Confirmed, real, and deliberately NOT fixed this round: terse
        categorical/numeric framing with no easing-verb vocabulary at all
        (e.g. a bare negative point-change plus an idiomatic "tail removed")
        is too bespoke to generalize into a regex without overfitting to one
        example -- documented as an accepted limitation, not silently
        papered over."""
        text = (
            "Category: Recession risk; Signal: Bullish; Evidence: 8% by "
            "end-2026, -2.0pp on week; Implication for NVDA: "
            "Demand-destruction tail removed"
        )
        assert recession_risk_is_relief(text) is False
        assert alpha_relation(text, "A501") == "activation"


class TestValuationRiskEasingRealPhrasings:
    """A304 (a RISK_ALPHA_IDS member): claims asserting NVDA's valuation is
    not expensive must classify as risk_relief, not activation."""

    def test_low_peg_ratio_argument(self):
        text = (
            "A PEG of 0.48 is unusually low for a mega-cap, indicating "
            "growth is currently outpacing the multiple."
        )
        assert valuation_risk_is_relief(text) is True
        assert alpha_relation(text, "A304") == "risk_relief"

    def test_objectively_cheap_relative_to_growth(self):
        text = (
            'Bear Claim: "Valuation risk / priced for perfection"; '
            "Bull Rebuttal: Forward P/E 14.7, PEG 0.48 -- objectively cheap "
            "relative to growth"
        )
        assert valuation_risk_is_relief(text) is True
        assert alpha_relation(text, "A304") == "risk_relief"

    def test_objectively_undemanding_relative_to_growth(self):
        text = "The valuation is objectively undemanding relative to growth."
        assert valuation_risk_is_relief(text) is True
        assert alpha_relation(text, "A304") == "risk_relief"

    def test_explicit_rebuttal_of_quoted_valuation_risk_framing(self):
        text = (
            "When a company grows revenue 106% Y/Y and trades at 14.7x "
            'forward earnings, the bear\'s "valuation risk" argument isn\'t '
            "a valuation argument at all."
        )
        assert valuation_risk_is_relief(text) is True
        assert alpha_relation(text, "A304") == "risk_relief"


class TestRealRiskEscalationCounterExamplesAreUnaffected:
    """The fix must not sweep real, opposite-direction evidence (recession
    risk escalating, valuation genuinely expensive) into risk_relief --
    "must not pass by excluding everything." These are real bear_researcher
    claims from the same NVDA run, explicitly pushing back on the "cheap
    valuation" framing; none of them assert risk/valuation easing
    themselves, and all must remain relation="activation" (or another
    non-risk_relief relation already produced by unrelated, untouched
    classification logic), exactly as before this fix."""

    def test_bull_is_making_a_bet_dressed_as_a_thesis(self):
        text = (
            "Let me translate: the bull is making a mean-reversion bet on "
            "the single most important variable for NVDA's valuation, and "
            "he's calling it a thesis."
        )
        assert valuation_risk_is_relief(text) is False
        assert alpha_relation(text, "A304") == "activation"

    def test_good_for_revenue_but_bad_for_the_multiple(self):
        text = (
            'The bull says "overheating means strong nominal demand, which '
            'is good for revenue." True -- but it\'s bad for the multiple, '
            "and the multiple is what you're paying for."
        )
        assert valuation_risk_is_relief(text) is False
        assert alpha_relation(text, "A304") == "activation"

    def test_cheap_valuation_is_a_function_of_an_untested_estimate(self):
        text = (
            'The bull\'s "cheap" valuation is entirely a function of an '
            "estimate that hasn't been tested by a full demand cycle."
        )
        assert valuation_risk_is_relief(text) is False
        assert alpha_relation(text, "A304") == "activation"

    def test_premium_multiple_on_book(self):
        text = "That's a premium multiple on book."
        assert valuation_risk_is_relief(text) is False
        assert alpha_relation(text, "A304") == "activation"

    def test_peg_mentioned_without_an_easing_claim_stays_unaffected(self):
        """PEG appears in the text, but with no "low"/"cheap"/"undemanding"
        assertion attached -- the new peg-based pattern must not fire on
        bare mentions of the metric."""
        text = (
            'The bull says "PEG of 0.48 means growth is running at 2x the '
            'multiple." Sure -- if the growth materializes.'
        )
        assert valuation_risk_is_relief(text) is False
        assert alpha_relation(text, "A304") == "conditional"

    def test_no_recession_conflated_with_no_risk_pushback_stays_unaffected(self):
        text = (
            'The aggressive analyst keeps conflating "no recession" with '
            '"no risk." Those are different.'
        )
        assert recession_risk_is_relief(text) is False
        assert alpha_relation(text, "A501") == "activation"


def _record(claim_id, agent, claim, *, alpha_id, relation):
    candidate = {"alpha_id": alpha_id, "relation": relation, "matched_keywords": [], "matched_factors": []}
    return {
        "run_id": "oracle_run", "ticker": "ACME", "agent": agent, "claim_id": claim_id,
        "source_agent_output_id": f"{agent}:source", "claim": claim, "evidence": claim,
        "match_status": "matched", "matched_alpha": alpha_id, "score": 1.0,
        "assertion_status": "asserted", "semantic_polarity": "activation",
        "factor_score": 1.0, "keyword_score": 1.0, "eligible_candidates": [candidate],
        "claim_quality": "analytical", "direction": "negative",
    }


def test_end_to_end_risk_relief_text_is_excluded_from_qualifying_support_but_still_visible():
    """Proves the already-correct, untouched downstream mechanism actually
    receives and acts on the corrected text->relation classification: a
    claim whose TEXT is real recession-risk-easing language (not a
    hand-set relation=) is excluded from A501's qualifying/supporting
    evidence count (the frozen ALPHA_ACTIVATION_EVIDENCE_V1 contract), while
    a genuine activation claim for the same Alpha is still admitted --
    "must not pass by excluding everything" (a real counter-example claim
    is still present and still counted)."""
    relief_text = "Recession risk is low and falling, removing a key demand-destruction tail for NVDA."
    activation_text = "Recession probability is climbing sharply, raising concrete demand-destruction risk for NVDA."

    relief_relation = alpha_relation(relief_text, "A501")
    activation_relation = alpha_relation(activation_text, "A501")
    assert relief_relation == "risk_relief"
    assert activation_relation == "activation"

    payload = {
        "run_id": "oracle_run",
        "ticker": "ACME",
        "matches": [
            _record("r:claim:1", "news_agent", relief_text, alpha_id="A501", relation=relief_relation),
            _record("r:claim:2", "fundamental_agent", activation_text, alpha_id="A501", relation=activation_relation),
        ],
    }
    result = score_alpha_v2(
        "A501", payload, TAXONOMY, ticker="ACME",
        structured_records=[{"claim_id": "r:claim:1", "entities": []}, {"claim_id": "r:claim:2", "entities": []}],
        run_timestamp="2026-06-30", as_of="2026-06-30",
    )

    # The risk_relief claim is excluded from qualifying supporting evidence
    # (frozen contract); the genuine activation claim remains admitted.
    assert "oracle_run:claim:1" not in "".join(result["claim_ids"])  # sanity: never silently merged
    assert any(cid.endswith("r:claim:2") for cid in result["claim_ids"])
    assert not any(cid.endswith("r:claim:1") for cid in result["claim_ids"])
    assert result["evidence_count"] == 1
