"""2026-10-06 (T1 judgment-standard correction): targeted, zero-Provider-call
tests for the NEW v2 content-support contract -- fixed responses injected
ONLY at the Provider boundary; every other function (validation,
materiality-based downgrade, eligibility, scoring/activation/conflict
wiring) is the REAL, unmodified production code.

These tests prove the WIRING and the mechanical consistency checks are
real -- they do NOT prove a real DeepSeek model actually produces good
semantic judgments under the new prompt (that requires the separately
proposed, not-yet-executed limited real verification -- see this round's
proposal document).

Scenarios NOT re-tested here because an existing, already-updated test
already covers them under the v2 contract:
  - core supported + NON_MATERIAL remainder stays SUPPORTS, and a MATERIAL
    remainder downgrades to CONDITIONAL:
    test_content_support_llm_multi_field_citation.py
  - forged source / wrong field-value binding / segment-count mismatch:
    test_content_support_llm_multi_field_citation.py
  - a TIME_INVALID source is never even queued (pre-send gate, unaffected
    by the v2 contract): test_content_support_llm_production_wiring.py::
    test_time_invalid_source_is_never_queued_for_content_support_verification
  - qualified analytical evidence contributes a real official score, a
    full qualifying fixture genuinely activates/admits a conflict through
    the real production chain, and same-fact cross-agent duplicate_group_id
    citation does not inflate independent evidence count: test_content_
    support_llm_production_wiring.py's test_1/test_2/test_3/test_duplicate_
    source_citation... (already updated to emit v2-shaped fixed responses)
  - a bearish, source-opposes-claim-direction scenario preserved, never
    dropped wholesale: test_content_support_llm_production_wiring.py::
    test_source_opposes_claim_direction_preserved_never_dropped_wholesale
"""

from __future__ import annotations

import json

from comqutor_alpha.source_provenance import (
    SOURCE_LINK_VALID,
    SUPPORT_CONDITIONAL,
    SUPPORT_SUPPORTS,
    build_source_record,
    compute_verified_support_eligibility,
)
from comqutor_alpha.structure_engine import content_support_llm as csl
from tests._content_support_v2_fixture_helpers import v2_response
from tests.test_content_support_llm import FakeContentSupportGateway, _analytical_record, _analytical_source

_RETRIEVED_AT = "2026-10-05T17:36:24Z"


def test_faithful_paraphrase_passes_even_though_source_never_uses_the_claims_own_wording():
    """Requirement 1 (正确核验目标): a claim that restates the source's own
    meaning in different words -- never the source's literal phrasing --
    must be accepted as SEMANTIC_PARAPHRASE, not rejected merely because
    the source "never says this exact sentence"."""
    source = _analytical_source(
        excerpt="AMD income statement (quarterly) Gross Profit: 2026-06-30=6203000000.0; 2026-03-31=5416000000.0",
        data_snapshot={"line_item": "Gross Profit", "periods": {"2026-06-30": 6203000000.0, "2026-03-31": 5416000000.0}},
    )
    # The claim is a FAITHFUL RESTATEMENT in different words -- the source
    # never says "jumped" or "quarter-over-quarter", it just lists two
    # period figures; this is exactly what SEMANTIC_PARAPHRASE is for.
    claim = "AMD's gross profit jumped quarter-over-quarter, rising from $5,416M to $6,203M."
    record = _analytical_record(source, claim=claim)
    response = {
        "items": [
            v2_response(
                claim_id="claim-1",
                status=csl.STATUS_SUPPORTS,
                used_source_id=source["source_id"],
                used_location="data_snapshot.periods",
                supporting_quote_or_data="6203000000.0",
                rationale=(
                    "The source's own two period figures (5416000000.0 for 2026-03-31, 6203000000.0 for "
                    "2026-06-30) directly establish the rise from $5,416M to $6,203M; 'jumped quarter-over-"
                    "quarter' is a faithful restatement of this increase, not a new fact."
                ),
                supported_proposition=claim,
                support_basis="SEMANTIC_PARAPHRASE",
            )
        ]
    }
    gateway = FakeContentSupportGateway([response])
    records, stats = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
    updated = records[0]
    assert updated["content_support_llm_fallback_reason"] is None
    assert updated["content_support_status"] == SUPPORT_SUPPORTS
    assert updated["content_support_llm_detail"]["support_basis"] == "SEMANTIC_PARAPHRASE"
    assert compute_verified_support_eligibility(updated, [source])["eligible"] is True


def test_grounded_inference_from_stated_facts_passes_with_disclosed_assumption():
    """Requirement 1: a reasonable conclusion the source does not itself
    spell out, but that genuinely follows from the source's own stated
    facts plus an explicit, disclosed assumption, must be accepted as
    GROUNDED_INFERENCE -- never rejected merely because "the source never
    concludes this itself"."""
    source = _analytical_source(
        excerpt="AMD income statement (quarterly) Gross Profit: 2026-06-30=6203000000.0; 2026-03-31=5416000000.0",
        data_snapshot={"line_item": "Gross Profit", "periods": {"2026-06-30": 6203000000.0, "2026-03-31": 5416000000.0}},
    )
    claim = "AMD's gross profit growth rate this quarter was roughly 14-15%, assuming no change in revenue recognition timing."
    record = _analytical_record(source, claim=claim)
    response = {
        "items": [
            v2_response(
                claim_id="claim-1",
                status=csl.STATUS_SUPPORTS,
                used_source_id=source["source_id"],
                used_location="data_snapshot.periods",
                supporting_quote_or_data="6203000000.0",
                rationale="(6203000000-5416000000)/5416000000 = 14.5%, computed from the source's own two stated figures.",
                supported_proposition=claim,
                support_basis="GROUNDED_INFERENCE",
                inference_facts=["Gross Profit 2026-06-30=6203000000.0", "Gross Profit 2026-03-31=5416000000.0"],
                inference_assumptions=["no change in revenue recognition timing between the two periods"],
            )
        ]
    }
    gateway = FakeContentSupportGateway([response])
    records, stats = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
    updated = records[0]
    assert updated["content_support_llm_fallback_reason"] is None
    assert updated["content_support_status"] == SUPPORT_SUPPORTS
    detail = updated["content_support_llm_detail"]
    assert detail["support_basis"] == "GROUNDED_INFERENCE"
    assert detail["inference_assumptions"] == ["no change in revenue recognition timing between the two periods"]
    assert compute_verified_support_eligibility(updated, [source])["eligible"] is True


def test_grounded_inference_needing_no_assumption_is_not_rejected_for_empty_assumptions():
    """v2.1 correction (Part 二 point 3): a real inference that follows
    directly from stated facts via plain logical entailment -- needing NO
    extra assumption at all -- must not be rejected just because
    inference_assumptions is empty. Beta's own mathematical definition
    means "beta=2.45 implies high volatility relative to the market" is a
    real GROUNDED_INFERENCE with no assumption gap to fill."""
    source = _analytical_source(excerpt="AMD valuation snapshot Beta=2.454", data_snapshot={"beta": 2.454})
    claim = "AMD's beta of 2.45 means it will amplify broader market moves -- a high-volatility instrument."
    record = _analytical_record(source, claim=claim)
    response = {
        "items": [
            v2_response(
                claim_id="claim-1",
                status=csl.STATUS_SUPPORTS,
                used_source_id=source["source_id"],
                used_location="data_snapshot.beta",
                supporting_quote_or_data="2.454",
                rationale="Beta=2.454 mathematically means price moves amplify market moves by that factor -- this follows directly from beta's own definition, no additional assumption is needed.",
                supported_proposition=claim,
                support_basis="GROUNDED_INFERENCE",
                inference_facts=["beta=2.454"],
                inference_assumptions=[],  # genuinely none needed -- must not be force-filled or rejected
            )
        ]
    }
    gateway = FakeContentSupportGateway([response])
    records, stats = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
    updated = records[0]
    assert updated["content_support_llm_fallback_reason"] is None
    assert updated["content_support_status"] == SUPPORT_SUPPORTS
    assert updated["content_support_llm_detail"]["inference_assumptions"] == []


def test_non_material_with_no_rationale_is_an_internal_contradiction():
    """v2.1 correction (Part 二 point 4): NON_MATERIAL must never be a
    bare label -- asserting it with an empty rationale is rejected as an
    internal contradiction, never silently accepted."""
    source = _analytical_source()
    claim = "Gross profit was $6,203M -- a modestly encouraging print."
    record = _analytical_record(source, claim=claim)
    response = {
        "items": [
            v2_response(
                claim_id="claim-1",
                status=csl.STATUS_SUPPORTS,
                used_source_id=source["source_id"],
                used_location="data_snapshot.periods.2026-06-30",
                supporting_quote_or_data="6203000000.0",
                rationale="",  # no explanation at all for why "modestly encouraging" is non-material
                supported_proposition="Gross profit was $6,203M.",
                unsupported_remainder="a modestly encouraging print",
                materiality="NON_MATERIAL",
            )
        ]
    }
    gateway = FakeContentSupportGateway([response])
    records, stats = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
    updated = records[0]
    assert updated["content_support_llm_fallback_reason"] == csl.FALLBACK_INTERNAL_CONTRADICTION


def test_prediction_written_as_already_happened_fact_is_rejected_not_accepted():
    """Requirement 1/4: a FUTURE prediction the claim states as if it were
    already a settled fact must not be matched to source material that
    only supports the PRESENT/past state -- status must not be SUPPORTS
    for the claim's own (future) proposition."""
    source = _analytical_source(
        excerpt="AMD income statement (quarterly) Gross Profit: 2026-06-30=6203000000.0; 2026-03-31=5416000000.0",
        data_snapshot={"line_item": "Gross Profit", "periods": {"2026-06-30": 6203000000.0, "2026-03-31": 5416000000.0}},
    )
    claim = "AMD's gross profit has already reached $7,000M this quarter, confirming the growth trend continues."
    record = _analytical_record(source, claim=claim)
    # The real production-correct answer: the source only shows $6,203M,
    # not $7,000M -- a different, unsupported object/value. The model
    # correctly declines to support the stated (false) proposition.
    response = {
        "items": [
            v2_response(
                claim_id="claim-1",
                status=csl.STATUS_INSUFFICIENT,
                rationale="The source's latest figure is $6,203M, not $7,000M -- the claim's own stated value is not established by this material.",
                unsupported_remainder=claim,
            )
        ]
    }
    gateway = FakeContentSupportGateway([response])
    records, stats = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
    updated = records[0]
    assert updated["content_support_status"] != SUPPORT_SUPPORTS
    assert compute_verified_support_eligibility(updated, [source])["eligible"] is False


def test_subjective_evaluative_core_conclusion_requires_real_support_not_rejected_by_keyword():
    """Requirement 1 (program must not simulate semantic judgment with
    keywords): a subjective word like "cheap" that IS the claim's own core
    conclusion must still be checked for real support when the LLM
    discloses a real basis -- this module's own validation
    (_validate_response_item/_v2_structural_contradiction/
    _effective_content_support_status) reads only status/support_basis/
    unsupported_remainder_materiality/citation fields, never the claim's
    own text -- proven here behaviorally: this claim's core conclusion IS
    the evaluative word "cheap", and it validates/reaches eligible SUPPORTS
    purely because the LLM disclosed a real basis and the citation checks
    out, with no special-casing possible on the word itself (the program
    never even looks at record["claim"] during validation)."""
    source = _analytical_source(
        excerpt="AMD valuation snapshot PEG Ratio=0.64",
        data_snapshot={"peg_ratio": 0.64},
    )
    claim = "AMD looks cheap here -- the PEG ratio of 0.64 signals the market is mispricing its growth."
    record = _analytical_record(source, claim=claim)
    response = {
        "items": [
            v2_response(
                claim_id="claim-1",
                status=csl.STATUS_SUPPORTS,
                used_source_id=source["source_id"],
                used_location="data_snapshot.peg_ratio",
                supporting_quote_or_data="0.64",
                rationale="PEG=0.64 is a real, stated valuation figure; 'cheap'/'mispricing' is the claim's own core conclusion from this real number.",
                supported_proposition=claim,
                support_basis="DIRECT_FACT",
            )
        ]
    }
    gateway = FakeContentSupportGateway([response])
    records, stats = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
    updated = records[0]
    assert updated["content_support_llm_fallback_reason"] is None
    assert updated["content_support_status"] == SUPPORT_SUPPORTS
    assert compute_verified_support_eligibility(updated, [source])["eligible"] is True


def test_supports_with_no_disclosed_basis_is_an_internal_contradiction_not_silently_accepted():
    """Requirement 3: Provider SUPPORTS alone is never trusted -- if the
    structured result simultaneously discloses NO basis for that verdict
    (support_basis=NONE), this is a real internal contradiction, recorded
    distinctly, never silently resolved in SUPPORTS' favor."""
    source = _analytical_source()
    record = _analytical_record(source, claim="Gross margin is improving meaningfully.")
    response = {
        "items": [
            v2_response(
                claim_id="claim-1",
                status=csl.STATUS_SUPPORTS,
                used_source_id=source["source_id"],
                used_location="data_snapshot.periods",
                supporting_quote_or_data="6203000000.0",
                support_basis="NONE",  # the contradiction: claims support, discloses no basis
            )
        ]
    }
    gateway = FakeContentSupportGateway([response])
    records, stats = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
    updated = records[0]
    assert updated["content_support_llm_fallback_reason"] == csl.FALLBACK_INTERNAL_CONTRADICTION
    assert updated.get("content_support_status") != SUPPORT_SUPPORTS


def test_scorable_proposition_never_consumed_by_eligibility_function():
    """Requirement 4 (计分范围必须明确): compute_verified_support_
    eligibility must never read supported_proposition/core_proposition at
    all -- proven by direct source inspection, not merely by behavioral
    coincidence -- so a materially-rewritten supported_proposition can
    never, by itself, cause a claim to become eligible."""
    import inspect

    from comqutor_alpha import source_provenance

    source_code = inspect.getsource(source_provenance.compute_verified_support_eligibility)
    assert "supported_proposition" not in source_code
    assert "core_proposition" not in source_code


def test_reclassification_detection_flags_material_remainder_claims_matched_to_an_alpha():
    """Requirement 5 (重新分类路径): when verification finds a MATERIAL
    unsupported remainder on a claim that WAS matched to an Alpha, that
    original match/direction (computed from the claim's full ORIGINAL
    text) is flagged as needing review -- this is pure detection, zero
    Provider calls, never an automatic re-trigger."""
    from comqutor_alpha.structure_engine.content_support_llm import identify_claims_needing_alpha_reclassification

    records = [
        {
            "claim_id": "c1",
            "content_support_llm_detail": {
                "unsupported_remainder_materiality": "MATERIAL",
                "unsupported_remainder": "a material correction",
                "supported_proposition": "the narrow supported part",
            },
        },
        {  # NON_MATERIAL -- must not be flagged
            "claim_id": "c2",
            "content_support_llm_detail": {
                "unsupported_remainder_materiality": "NON_MATERIAL",
                "unsupported_remainder": "a minor aside",
            },
        },
        {  # MATERIAL but never matched to any Alpha -- nothing to reclassify
            "claim_id": "c3",
            "content_support_llm_detail": {"unsupported_remainder_materiality": "MATERIAL"},
        },
    ]
    alpha_matches = {
        "c1": {"matched_alpha": "A304", "direction": "bearish"},
        "c2": {"matched_alpha": "A304", "direction": "bearish"},
        "c3": {"matched_alpha": None, "direction": "unknown"},
    }
    flagged = identify_claims_needing_alpha_reclassification(records, alpha_matches)
    assert [f["claim_id"] for f in flagged] == ["c1"]
    assert flagged[0]["matched_alpha"] == "A304"


def test_reclassification_detection_returns_empty_on_real_v1_shaped_data_never_guesses():
    """Honesty check (已有真实响应...旧响应缺少必要语义字段时明确标为
    尚需新版本核验): the REAL 20-claim execution's own saved records were
    produced under the v1 contract (schema_version=content_support.llm.v1)
    -- they have no unsupported_remainder_materiality field at all. This
    function must return an empty list for them, not guess a materiality
    value to make a flag appear -- proven directly against the real saved
    execution file, not a synthetic stand-in."""
    from comqutor_alpha.structure_engine.content_support_llm import identify_claims_needing_alpha_reclassification

    exec20 = json.loads(
        open(
            "docs/audit_artifacts/round_source_linking_t0_t2/round10_amd_official_scoring_trace_20261006/"
            "executions/phase-c-20261006T000643Z-bb63dfd7.json"
        ).read()
    )
    some_detail = next(
        r["content_support_llm_detail"] for r in exec20["records"] if r.get("content_support_llm_detail")
    )
    assert some_detail["schema_version"] == "content_support.llm.v1"
    assert "unsupported_remainder_materiality" not in some_detail

    alpha_matches = json.loads(open("outputs/runs/1bad76a7-72ac-4c8b-8189-2e5c0f1a6105/alpha_matches.json").read())
    matches_by_id = {m["claim_id"]: m for m in alpha_matches["matches"]}
    flagged = identify_claims_needing_alpha_reclassification(exec20["records"], matches_by_id)
    assert flagged == []


def test_api_export_round_trip_preserves_v2_fields_and_scope():
    """Requirement 11 (API/Export一致性), zero-Provider-call version: a
    real run through apply_llm_content_support_verification, then a real
    disk round-trip (json.dumps/json.loads, the same serialization Export
    performs) must preserve core_proposition/support_basis/inference_facts/
    unsupported_remainder_materiality exactly, and the ORIGINAL claim text
    must never be replaced by supported_proposition anywhere in that
    round-trip."""
    source = _analytical_source()
    claim = "Gross profit hit $6,203M, confirming the AI-driven margin thesis is now fully playing out."
    record = _analytical_record(source, claim=claim)
    response = {
        "items": [
            v2_response(
                claim_id="claim-1",
                status=csl.STATUS_SUPPORTS,
                used_source_id=source["source_id"],
                used_location="data_snapshot.periods.2026-06-30",
                supporting_quote_or_data="6203000000.0",
                rationale="The figure is real; the broader thesis claim is not addressed by this material.",
                supported_proposition="Gross profit was $6,203M this period.",
                unsupported_remainder="confirming the AI-driven margin thesis is now fully playing out",
                materiality="MATERIAL",
                support_basis="DIRECT_FACT",
            )
        ]
    }
    gateway = FakeContentSupportGateway([response])
    records, _ = csl.apply_llm_content_support_verification([record], [source], llm_gateway=gateway)
    updated = records[0]

    round_tripped = json.loads(json.dumps(updated, default=str))
    detail = round_tripped["content_support_llm_detail"]
    assert detail["support_basis"] == "DIRECT_FACT"
    assert detail["unsupported_remainder_materiality"] == "MATERIAL"
    assert detail["supported_proposition"] == "Gross profit was $6,203M this period."
    # The original claim is untouched by the round-trip and is NOT equal to
    # the scorable sub-proposition -- an API/UI reading this must use
    # round_tripped["claim"], never detail["supported_proposition"], as
    # the claim text.
    assert round_tripped["claim"] == claim
    assert round_tripped["claim"] != detail["supported_proposition"]
    assert round_tripped["content_support_status"] == SUPPORT_CONDITIONAL
