"""v0.2 QQQ A001 Mapping Remediation (Step 7A and Step 7A.2).

Focused, offline (no Provider/TradingAgents) regression tests for:

- Step 7A: the deterministic Alpha-Specific Invalidation Veto added to
  `comqutor_alpha.structure_engine.alpha_mapper.map_claim_to_alpha` and the
  expanded `_RATE_CUT_INVALIDATION_PATTERN` in
  `comqutor_alpha.structure_engine.claim_semantics`.
- Step 7A.2: the complementary Alpha-Specific Positive Requirement gate
  (`classify_a001_directional_semantics` / `alpha_positive_requirement_satisfied`
  in the same module), added after an independent Step-7A.1 residual audit
  found 0/29 claims surviving the Step-7A veto were genuine positive A001
  evidence.

Root cause (docs/audit_artifacts/v0_2_acceptance_adjudication.json, Case A):
QQQ's authoritative fresh run (f88c8956-...) pooled 66 claims into A001's
matched_alpha bucket via the LLM semantic classifier, even though the
dominant real content describes a rate HIKE / hawkish repricing environment
-- the direct economic opposite of A001's Rate Cut Cycle thesis. Because
Activation Scorer v2's evidence_quality/agent_independence components count
claim volume/agent breadth without regard to direction, this pool alone
pushed A001 to an official "active" level in a run where Gold v0.2's
Step-3 evidence trigger for A001 is frozen ABSENT with STRONG contrary
evidence. Step 7A closed the most explicit false-positive surface (66->29);
Step 7A.2 closes the remaining generic/non-directional surface the negative
veto structurally cannot reach (docs/audit_artifacts/
v0_2_qqq_a001_residual_mapping_audit.json).

This file uses the same `_FakeLLMGateway` pattern already established in
tests/test_alpha_mapper_llm_authority.py -- no real Provider call anywhere.
"""

from __future__ import annotations

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.structure_engine.alpha_mapper import map_claim_to_alpha
from comqutor_alpha.structure_engine.claim_semantics import (
    alpha_positive_requirement_satisfied,
    alpha_specific_invalidation_matched,
    classify_a001_directional_semantics,
)

TAXONOMY = load_alpha_taxonomy()


class _FakeLLMGateway:
    """Mirrors tests/test_alpha_mapper_llm_authority.py's fake gateway: no
    real Provider call, speaks the same invoke_json(task, payload, validator)
    seam Week2LLMGateway exposes."""

    invoke_json_with_trace = None

    def __init__(self, response):
        self._response = response
        self.calls: list[dict] = []
        self.semantic_runtime = None

    def invoke_json(self, task, payload, validator):
        self.calls.append({"task": task, "payload": payload})
        try:
            return validator(self._response)
        except (TypeError, ValueError, KeyError):
            return None


def _record(text, *, direction="neutral", ticker="QQQ", agent="news_agent"):
    return {
        "run_id": "run1",
        "ticker": ticker,
        "agent": agent,
        "claim": text,
        "evidence": text,
        "factors": [],
        "direction": direction,
        "confidence": 0.8,
        "source_agent_output_id": "run1:%s:report" % agent,
    }


def _select_a001(record):
    gateway = _FakeLLMGateway({"decision": "select", "selected_alpha_id": "A001"})
    return map_claim_to_alpha(record, TAXONOMY, classifier_enabled=True, llm_gateway=gateway)


def _select(record, alpha_id):
    gateway = _FakeLLMGateway({"decision": "select", "selected_alpha_id": alpha_id})
    return map_claim_to_alpha(record, TAXONOMY, classifier_enabled=True, llm_gateway=gateway)


# ---------------------------------------------------------------------------
# Unit-level: the new predicate itself
# ---------------------------------------------------------------------------


def test_alpha_specific_invalidation_matched_true_for_a001_no_cut_language():
    assert alpha_specific_invalidation_matched(
        "93% probability of NO Fed rate cuts in 2026", "A001"
    )


def test_alpha_specific_invalidation_matched_true_for_a001_hike_language():
    assert alpha_specific_invalidation_matched(
        "72% probability of a Fed rate hike in 2026", "A001"
    )


def test_alpha_specific_invalidation_matched_false_for_genuine_cut_language():
    assert not alpha_specific_invalidation_matched(
        "The Fed cut rates by 25bp, initiating an easing cycle.", "A001"
    )


def test_alpha_specific_invalidation_matched_false_for_unregistered_alpha():
    # No registered pattern for A101 -- must never fabricate a veto.
    assert not alpha_specific_invalidation_matched(
        "72% probability of a Fed rate hike in 2026", "A101"
    )


# ---------------------------------------------------------------------------
# POSITIVE A001 CONTROLS -- genuine Rate Cut Cycle evidence must still map
# ---------------------------------------------------------------------------


def test_positive_explicit_rate_cut():
    record = _record(
        "The Fed cut rates by 25 basis points, beginning an easing cycle.",
        direction="positive",
    )
    result = _select_a001(record)
    assert result["matched_alpha"] == "A001"
    assert result["match_status"] == "matched"
    assert result["alpha_specific_invalidation_override"] is False


def test_positive_falling_discount_rate_supports_growth():
    record = _record(
        "Falling discount rates are supporting long-duration growth equity valuations "
        "as the Fed's easing cycle continues.",
        direction="positive",
    )
    result = _select_a001(record)
    assert result["matched_alpha"] == "A001"
    assert result["alpha_specific_invalidation_override"] is False


def test_positive_expected_ongoing_easing():
    record = _record(
        "Markets are pricing an ongoing rate-cut cycle as inflation cools and the Fed "
        "pivots dovish.",
        direction="positive",
    )
    result = _select_a001(record)
    assert result["matched_alpha"] == "A001"
    assert result["alpha_specific_invalidation_override"] is False


def test_positive_lower_rates_beneficiary_framing():
    record = _record(
        "Lower rates are expected to support QQQ's long-duration growth holdings.",
        direction="positive",
    )
    result = _select_a001(record)
    assert result["matched_alpha"] == "A001"
    assert result["alpha_specific_invalidation_override"] is False


# ---------------------------------------------------------------------------
# NEGATIVE CONTROLS -- real false-positive classes from the persisted QQQ
# evidence (run f88c8956-cb62-48aa-9951-89f8e8a95f83)
# ---------------------------------------------------------------------------


def test_negative_no_rate_cuts_probability():
    # Verbatim pattern from the persisted QQQ run's news_agent claim.
    record = _record(
        "93% probability of NO Fed rate cuts in 2026 (up +4.3pp over the week; $8.1M volume)",
        direction="negative",
    )
    result = _select_a001(record)
    assert result["matched_alpha"] is None
    assert result["match_status"] == "no_match"
    assert result["alpha_specific_invalidation_override"] is True


def test_negative_rate_hike_probability():
    record = _record(
        "72% probability of a Fed rate hike in 2026 (up 4pp in a week)",
        direction="negative",
    )
    result = _select_a001(record)
    assert result["matched_alpha"] is None
    assert result["alpha_specific_invalidation_override"] is True


def test_negative_rate_hike_odds_pushed_past_threshold():
    record = _record(
        "The strong jobs report pushed September rate-hike odds past 60%, pressuring "
        "long-duration growth.",
        direction="negative",
    )
    result = _select_a001(record)
    assert result["matched_alpha"] is None
    assert result["alpha_specific_invalidation_override"] is True


def test_negative_hawkish_repricing():
    record = _record(
        "This is a distinctly hawkish repricing that pressures long-duration, "
        "high-multiple growth names -- the core of QQQ's holdings.",
        direction="negative",
    )
    result = _select_a001(record)
    assert result["matched_alpha"] is None
    assert result["alpha_specific_invalidation_override"] is True


def test_negative_rising_yields():
    record = _record(
        "With 72% odds of a 2026 hike and September odds past 60%, rising yields "
        "directly pressure QQQ's long-duration, high-multiple holdings.",
        direction="negative",
    )
    result = _select_a001(record)
    assert result["matched_alpha"] is None
    assert result["alpha_specific_invalidation_override"] is True


def test_negative_higher_for_longer():
    record = _record(
        "The Fed is signaling rates will stay higher for longer.",
        direction="negative",
    )
    result = _select_a001(record)
    assert result["matched_alpha"] is None
    assert result["alpha_specific_invalidation_override"] is True


# ---------------------------------------------------------------------------
# BOUNDARY CONTROLS -- A001 must not collapse into A003 or A501 (and the
# veto must not spuriously fire for unrelated alphas the LLM selects)
# ---------------------------------------------------------------------------


def test_boundary_liquidity_evidence_selected_as_a003_is_not_vetoed():
    # A003 (Liquidity Expansion) evidence with no rate-cut/hike semantics at
    # all must map to A003 normally -- the veto is a no-op for A003 (no
    # registered pattern), and this is not an A001 claim in the first place.
    record = _record(
        "Liquidity conditions are improving as the Fed's balance sheet expands, "
        "supporting broad risk appetite.",
        direction="positive",
    )
    result = _select(record, "A003")
    assert result["matched_alpha"] == "A003"
    assert result["alpha_specific_invalidation_override"] is False


def test_boundary_recession_evidence_selected_as_a501_is_not_vetoed():
    record = _record(
        "Recession risk is elevated given weakening consumer spending and rising "
        "credit spreads.",
        direction="negative",
    )
    result = _select(record, "A501")
    assert result["matched_alpha"] == "A501"
    assert result["alpha_specific_invalidation_override"] is False


def test_boundary_recession_evidence_negative_veto_does_not_overreach():
    # If the classifier were to (incorrectly) select A001 for recession-risk
    # commentary that itself contains no rate-cut/hike language, the Step-7A
    # NEGATIVE veto specifically must NOT fire -- it is not a general
    # "reject A001 for macro-risk" rule, only a high-precision veto on
    # explicit thesis-contradiction language. This claim is correctly
    # rejected end-to-end by the separate Step-7A.2 POSITIVE-requirement
    # gate instead (it contains no affirmative easing evidence either), so
    # matched_alpha still ends up None -- but for a different, legitimate
    # reason than the negative veto.
    record = _record(
        "Recession risk is elevated given weakening consumer spending.",
        direction="negative",
    )
    result = _select_a001(record)
    assert result["alpha_specific_invalidation_override"] is False
    assert result["alpha_positive_requirement_override"] is True
    assert result["matched_alpha"] is None


def test_boundary_higher_for_longer_never_positive_for_a001():
    record = _record(
        "Rates remain restrictive and the Fed remains restrictive on policy.",
        direction="negative",
    )
    result = _select_a001(record)
    assert result["matched_alpha"] is None
    assert result["alpha_specific_invalidation_override"] is True


# ---------------------------------------------------------------------------
# Collateral-damage check -- unrelated Alphas' candidate/eligible behavior
# is unaffected by the claim_semantics.py pattern expansion
# ---------------------------------------------------------------------------


def test_collateral_a304_valuation_claim_unaffected():
    record = _record(
        "NVDA is priced for perfection at current multiples, a valuation risk.",
        direction="negative",
        ticker="NVDA",
    )
    result = _select(record, "A304")
    assert result["matched_alpha"] == "A304"
    assert result["alpha_specific_invalidation_override"] is False


def test_collateral_a601_narrative_claim_unaffected():
    record = _record(
        "AI narrative remains the dominant force driving crowded flows into QQQ's "
        "largest holdings.",
        direction="positive",
    )
    result = _select(record, "A601")
    assert result["matched_alpha"] == "A601"
    assert result["alpha_specific_invalidation_override"] is False


# ===========================================================================
# Step 7A.2 -- Alpha-Specific Positive Requirement gate
# ===========================================================================

# ---------------------------------------------------------------------------
# Unit-level: classify_a001_directional_semantics itself
# ---------------------------------------------------------------------------


def test_classify_positive_easing_explicit_cut():
    assert classify_a001_directional_semantics(
        "The Fed cut rates by 25bp, beginning an easing cycle."
    ) == "POSITIVE_EASING"


def test_classify_positive_easing_affirmative_expectation():
    assert classify_a001_directional_semantics(
        "Markets expect the Fed to cut rates at the next meeting."
    ) == "POSITIVE_EASING"


def test_classify_negative_or_hawkish_no_cuts():
    assert classify_a001_directional_semantics(
        "93% probability of NO Fed rate cuts in 2026"
    ) == "NEGATIVE_OR_HAWKISH"


def test_classify_conditional_or_uncertain_hedged_cut():
    assert classify_a001_directional_semantics(
        "Rate cuts could occur if growth deteriorates."
    ) == "CONDITIONAL_OR_UNCERTAIN"


def test_classify_conditional_or_uncertain_modal_ease():
    assert classify_a001_directional_semantics(
        "The Fed might eventually ease."
    ) == "CONDITIONAL_OR_UNCERTAIN"


def test_classify_generic_rate_context_no_direction():
    assert classify_a001_directional_semantics(
        "QQQ is sensitive to the interest-rate environment."
    ) == "GENERIC_RATE_CONTEXT"


def test_classify_generic_rate_context_liquidity_without_cuts():
    assert classify_a001_directional_semantics(
        "Liquidity conditions are improving as the Fed's balance sheet expands."
    ) == "GENERIC_RATE_CONTEXT"


def test_classify_no_rate_semantics_unrelated():
    assert classify_a001_directional_semantics(
        "Recession risk is elevated given weakening consumer spending."
    ) == "NO_RATE_SEMANTICS"


def test_alpha_positive_requirement_satisfied_true_for_positive_easing():
    assert alpha_positive_requirement_satisfied(
        "The Fed cut rates by 25bp, beginning an easing cycle.", "A001"
    )


def test_alpha_positive_requirement_satisfied_false_for_generic_context():
    assert not alpha_positive_requirement_satisfied(
        "QQQ is sensitive to the interest-rate environment.", "A001"
    )


def test_alpha_positive_requirement_satisfied_true_for_unregistered_alpha():
    # No registered classifier for A101 -- gate must be a no-op (never a
    # false rejection for an Alpha this mechanism doesn't cover).
    assert alpha_positive_requirement_satisfied(
        "QQQ is sensitive to the interest-rate environment.", "A101"
    )


# ---------------------------------------------------------------------------
# POSITIVE CONTROLS -- affirmative easing must still survive end-to-end,
# including semantic equivalents that do NOT rely on the exact phrase
# "rate cut" (Section 17)
# ---------------------------------------------------------------------------


def test_positive_gate_explicit_rate_cut_cycle():
    result = _select_a001(_record(
        "The Fed cut rates by 25 basis points, beginning an easing cycle.",
        direction="positive",
    ))
    assert result["matched_alpha"] == "A001"
    assert result["alpha_positive_requirement_override"] is False


def test_positive_gate_falling_policy_rates():
    result = _select_a001(_record(
        "Falling discount rates are supporting long-duration growth equity valuations "
        "as the Fed's easing cycle continues.",
        direction="positive",
    ))
    assert result["matched_alpha"] == "A001"
    assert result["alpha_positive_requirement_override"] is False


def test_positive_gate_monetary_easing_supports_growth():
    result = _select_a001(_record(
        "Monetary easing is increasing risk appetite and supporting long-duration growth assets.",
        direction="positive",
    ))
    assert result["matched_alpha"] == "A001"
    assert result["alpha_positive_requirement_override"] is False


def test_positive_gate_credible_expected_decline():
    result = _select_a001(_record(
        "Policy rates are expected to decline materially as inflation cools.",
        direction="positive",
    ))
    assert result["matched_alpha"] == "A001"
    assert result["alpha_positive_requirement_override"] is False


def test_positive_gate_semantic_equivalent_not_exact_phrase():
    # Deliberately avoids the literal phrase "rate cut" -- "borrowing costs
    # falling" + "central bank shifting to easier policy" must still pass.
    result = _select_a001(_record(
        "Borrowing costs are falling as the central bank shifts to easier policy.",
        direction="positive",
    ))
    assert result["matched_alpha"] == "A001"
    assert result["alpha_positive_requirement_override"] is False


# ---------------------------------------------------------------------------
# NEGATIVE CONTROLS -- Step-7A.1 residual mechanisms (Section 18 A-O)
# ---------------------------------------------------------------------------


def test_negative_gate_opposition_hawkish():
    result = _select_a001(_record(
        "This is a distinctly hawkish repricing that pressures long-duration growth names.",
        direction="negative",
    ))
    assert result["matched_alpha"] is None


def test_negative_gate_generic_rates():
    result = _select_a001(_record(
        "QQQ is a high-beta play on the direction of interest rates and liquidity conditions.",
        direction="positive",
    ))
    assert result["matched_alpha"] is None
    assert result["alpha_positive_requirement_override"] is True


def test_negative_gate_rising_yields():
    result = _select_a001(_record(
        "Rising yields directly pressure QQQ's long-duration, high-multiple holdings.",
        direction="negative",
    ))
    assert result["matched_alpha"] is None


def test_negative_gate_higher_for_longer():
    result = _select_a001(_record(
        "The Fed is signaling rates will stay higher for longer.",
        direction="negative",
    ))
    assert result["matched_alpha"] is None


def test_negative_gate_cuts_delayed():
    result = _select_a001(_record(
        "Rate cuts have been delayed as inflation remains sticky.",
        direction="negative",
    ))
    assert result["matched_alpha"] is None
    assert result["alpha_positive_requirement_override"] is True


def test_negative_gate_fewer_cuts_expected():
    result = _select_a001(_record(
        "Fewer cuts are expected this year given persistent inflation.",
        direction="negative",
    ))
    assert result["matched_alpha"] is None
    assert result["alpha_positive_requirement_override"] is True


def test_negative_gate_pricing_a_hike():
    # The exact Step-7A.1-identified phrasing gap: "pricing a hike" without
    # the word "rate" immediately adjacent.
    result = _select_a001(_record(
        "The market is pricing a hike because the economy is strong.",
        direction="positive",
    ))
    assert result["matched_alpha"] is None


def test_negative_gate_generic_discount_rate_alone():
    result = _select_a001(_record(
        "Metric: Rate Sensitivity; Value: High; Interpretation: sensitive to discount rates",
        direction="positive",
    ))
    assert result["matched_alpha"] is None
    assert result["alpha_positive_requirement_override"] is True


def test_negative_gate_generic_duration_alone():
    result = _select_a001(_record(
        "As a growth-heavy fund with long duration, QQQ tracks the broader market's positioning.",
        direction="neutral",
    ))
    assert result["matched_alpha"] is None
    assert result["alpha_positive_requirement_override"] is True


def test_negative_gate_generic_treasury_yield_alone():
    result = _select_a001(_record(
        "The 10-year Treasury yield remains a key input to QQQ's valuation model.",
        direction="neutral",
    ))
    assert result["matched_alpha"] is None
    assert result["alpha_positive_requirement_override"] is True


def test_negative_gate_rate_sensitive_valuation():
    result = _select_a001(_record(
        "High yields pressure technology valuations across the index.",
        direction="negative",
    ))
    assert result["matched_alpha"] is None
    assert result["alpha_positive_requirement_override"] is True


def test_negative_gate_recession_implying_possible_future_cuts():
    result = _select_a001(_record(
        "Recession risk is elevated given weakening consumer spending, which could eventually "
        "prompt the Fed to act.",
        direction="negative",
    ))
    assert result["matched_alpha"] is None


def test_negative_gate_liquidity_without_cuts():
    result = _select_a001(_record(
        "Liquidity conditions are improving as the Fed's balance sheet expands, supporting "
        "broad risk appetite.",
        direction="positive",
    ))
    assert result["matched_alpha"] is None
    assert result["alpha_positive_requirement_override"] is True


def test_negative_gate_mention_only_fed_policy():
    # "focused on whether...will cut" is a mention of the topic, not an
    # affirmative easing thesis -- must not satisfy the positive gate.
    assert classify_a001_directional_semantics(
        "The market is focused on whether the Fed will cut rates at its next meeting."
    ) == "CONDITIONAL_OR_UNCERTAIN"
    result = _select_a001(_record(
        "The market is focused on whether the Fed will cut rates at its next meeting.",
        direction="neutral",
    ))
    assert result["matched_alpha"] is None
    assert result["alpha_positive_requirement_override"] is True


def test_negative_gate_conditional_cuts_without_affirmative_thesis():
    result = _select_a001(_record(
        "If inflation falls further, the Fed may eventually cut rates.",
        direction="neutral",
    ))
    assert result["matched_alpha"] is None
    assert result["alpha_positive_requirement_override"] is True


# ---------------------------------------------------------------------------
# BOUNDARY CONTROLS -- A001/A003, A001/A501, A001/A304 (Sections 12-14)
# ---------------------------------------------------------------------------


def test_boundary_a003_liquidity_alone_does_not_require_a001():
    record = _record(
        "Liquidity is improving and financial conditions are easier, supporting broad "
        "risk appetite.",
        direction="positive",
    )
    result = _select(record, "A003")
    assert result["matched_alpha"] == "A003"


def test_boundary_a501_recession_does_not_imply_a001():
    record = _record(
        "Recession risk is elevated given weakening consumer spending and rising credit "
        "spreads.",
        direction="negative",
    )
    result = _select(record, "A501")
    assert result["matched_alpha"] == "A501"


def test_boundary_a304_valuation_pressure_does_not_require_a001():
    record = _record(
        "High yields pressure technology valuations across the index.",
        direction="negative",
    )
    result = _select(record, "A304")
    assert result["matched_alpha"] == "A304"


def test_boundary_a001_positive_gate_does_not_affect_other_alphas():
    # The positive-requirement gate is registered only for A001 -- an
    # unrelated Alpha's own selection must never be touched by it.
    record = _record(
        "AI narrative remains the dominant force driving crowded flows into QQQ's "
        "largest holdings.",
        direction="positive",
    )
    result = _select(record, "A601")
    assert result["matched_alpha"] == "A601"
    assert result["alpha_positive_requirement_override"] is False


# ---------------------------------------------------------------------------
# Step-7A.1 residual set -- all 29 rows must not positively survive as A001
# ---------------------------------------------------------------------------


def test_all_29_step7a1_residual_rows_rejected_by_positive_gate():
    import json
    from pathlib import Path

    audit_path = Path(__file__).parent.parent / "docs" / "audit_artifacts" / "v0_2_qqq_a001_residual_mapping_audit.json"
    audit = json.loads(audit_path.read_text())
    rows = audit["rows"]
    assert len(rows) == 29

    survivors = []
    for row in rows:
        classification = classify_a001_directional_semantics(row["claim"])
        if classification == "POSITIVE_EASING":
            survivors.append((row["claim_id"], row["claim"]))

    assert survivors == [], (
        "The following Step-7A.1 residual rows unexpectedly classify as "
        f"POSITIVE_EASING under the new gate: {survivors}"
    )
