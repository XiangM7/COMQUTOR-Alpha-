"""Automated-eligibility round (2026-10-06): real, deterministic, zero-
Provider-call tests for the automated data-fact/derived-calculation
verifier and the evidence_cutoff_at time-contract fix -- the mechanism
that lets production scoring use a claim's content support WITHOUT a
human reviewer having ever clicked anything (see
comqutor_alpha.source_provenance.verify_data_fact_or_derived_calculation /
apply_automated_content_support_verification / resolve_evidence_cutoff_at).

Both positive (a real, clean data fact / derived calculation verifies) and
negative (wrong object/period, a false arithmetic relationship, a marker
pointing at a source that does not actually carry the stated field, a
compound claim mixing a real number with unverifiable interpretation)
cases are covered -- a verifier that only ever proves the positive case is
not trustworthy.
"""

from __future__ import annotations

from comqutor_alpha.source_provenance import (
    AUTOMATICALLY_ELIGIBLE_REVIEW_METHODS,
    EVIDENCE_CUTOFF_BASIS_ANALYSIS_DATE_FALLBACK,
    EVIDENCE_CUTOFF_BASIS_MAX_SOURCE_FETCHED_AT,
    EVIDENCE_CUTOFF_BASIS_UNKNOWN,
    REVIEW_METHOD_AUTOMATED_DATA_FACT_VERIFIED,
    REVIEW_METHOD_AUTOMATED_DERIVED_CALC_VERIFIED,
    SOURCE_LINK_VALID,
    SUPPORT_SUPPORTS,
    apply_automated_content_support_verification,
    build_source_record,
    compute_verified_support_eligibility,
    resolve_evidence_cutoff_at,
    validate_source_reference,
    verify_data_fact_or_derived_calculation,
)

_RETRIEVED_AT = "2026-10-05T17:36:24Z"


def _income_statement_source(**overrides):
    base = dict(
        source_type="financial",
        name="Yahoo Finance",
        title="AMD income statement Total Revenue snapshot 2026-06-30 (quarterly)",
        url="",
        published_at=None,
        retrieved_at=_RETRIEVED_AT,
        provider="yfinance",
        excerpt="AMD income statement (quarterly) Total Revenue: 2026-06-30=11536000000.0",
        instrument="AMD",
        observation_date="2026-06-30",
        unit="UNKNOWN_CURRENCY",
        data_snapshot={
            "statement_type": "income statement",
            "line_item": "Total Revenue",
            "value": 11536000000.0,
            "periods": {
                "2026-06-30": 11536000000.0,
                "2026-03-31": 10253000000.0,
            },
            "all_line_items": {
                "Total Revenue": {"2026-06-30": 11536000000.0, "2026-03-31": 10253000000.0},
                "Operating Income": {"2026-06-30": 1990000000.0, "2026-03-31": 1476000000.0},
            },
        },
    )
    base.update(overrides)
    return build_source_record(**base)


def _record_linked_to(source, *, claim: str) -> dict:
    return {
        "claim_id": "claim-1",
        "claim": claim,
        "evidence": claim,
        "source_link_status": SOURCE_LINK_VALID,
        "linked_source_id": source["fragment_id"],
    }


# ---------------------------------------------------------------------------
# Positive: clean data-fact claim
# ---------------------------------------------------------------------------


def test_clean_line_item_claim_verifies_as_automated_data_fact():
    source = _income_statement_source()
    claim = "Line Item: Total Revenue; 2026-06-30: $11,536M; 2026-03-31: $10,253M"
    record = _record_linked_to(source, claim=claim)
    result = verify_data_fact_or_derived_calculation(record, [source])
    assert result is not None
    assert result["method"] == REVIEW_METHOD_AUTOMATED_DATA_FACT_VERIFIED


def test_apply_automated_content_support_verification_sets_real_fields_never_disguised_as_human():
    source = _income_statement_source()
    claim = "Line Item: Total Revenue; 2026-06-30: $11,536M; 2026-03-31: $10,253M"
    record = _record_linked_to(source, claim=claim)
    updated = apply_automated_content_support_verification(record, sources=[source])
    assert updated is not None
    assert record.get("content_support_status") is None  # original untouched
    assert updated["content_support_status"] == SUPPORT_SUPPORTS
    assert updated["content_support_method"] == REVIEW_METHOD_AUTOMATED_DATA_FACT_VERIFIED
    review = updated["content_support_review"]
    assert review["reviewer"] is None  # never fabricated as if a human reviewed it
    assert review["claim_id"] == "claim-1"
    assert review["linked_source_id"] == source["source_id"]
    assert review["content_hash"] == source["content_hash"]


def test_automated_verification_makes_the_claim_eligible_without_any_human_review():
    # A live-snapshot source (published_at IS genuinely known -- the
    # retrieval moment itself, see y_finance._fundamentals_summary_sentence)
    # so this exercises full end-to-end eligibility, not just content
    # support -- condition 6 of compute_verified_support_eligibility
    # independently requires a known disclosure time.
    source = build_source_record(
        source_type="financial", name="Yahoo Finance", title="AMD fundamentals snapshot",
        url="", published_at="2026-10-05T10:34:46", retrieved_at="2026-10-05T10:34:46",
        excerpt="AMD fundamentals as retrieved", instrument="AMD", observation_date="2026-10-05",
        data_snapshot={"market_cap": 1030810042368.0},
    )
    claim = "Metric: Market Cap; Value: $1,030,810,042,368"
    record = _record_linked_to(source, claim=claim)
    updated = apply_automated_content_support_verification(record, sources=[source])
    assert updated is not None
    eligibility = compute_verified_support_eligibility(updated, [source])
    assert eligibility["eligible"] is True
    assert updated["content_support_review"]["method"] in AUTOMATICALLY_ELIGIBLE_REVIEW_METHODS


def test_automated_data_fact_verification_alone_does_not_bypass_the_disclosure_time_check():
    # Honest, documented interaction (not a bug): a historical financial-
    # statement source deliberately carries published_at=None (yfinance
    # exposes only a fiscal PERIOD END, never a real disclosure date -- see
    # source_provenance.py's own module comment) -- automated DATA_FACT
    # verification succeeds (the content really is supported), but full
    # eligibility still correctly reports DISCLOSURE_TIME_UNKNOWN, exactly
    # as it would for an equivalent HUMAN_REVIEWED verdict on the same
    # source. Automated verification is additive to the existing gate, it
    # never weakens it.
    source = _income_statement_source()
    claim = "Line Item: Total Revenue; 2026-06-30: $11,536M; 2026-03-31: $10,253M"
    record = _record_linked_to(source, claim=claim)
    updated = apply_automated_content_support_verification(record, sources=[source])
    assert updated is not None
    assert updated["content_support_status"] == SUPPORT_SUPPORTS
    eligibility = compute_verified_support_eligibility(updated, [source])
    assert eligibility["eligible"] is False
    assert eligibility["reason_code"] == "DISCLOSURE_TIME_UNKNOWN"


# ---------------------------------------------------------------------------
# Positive: derived calculation (explicit "A - B = C" / "A + B = C")
# ---------------------------------------------------------------------------


def test_explicit_derived_calculation_recomputes_and_verifies():
    source = _income_statement_source()
    # Operating income delta: 1990000000 - 1476000000 = 514000000
    claim = "Operating Income: $1,990M - $1,476M = $514M"
    record = _record_linked_to(source, claim=claim)
    result = verify_data_fact_or_derived_calculation(record, [source])
    assert result is not None
    assert result["method"] == REVIEW_METHOD_AUTOMATED_DERIVED_CALC_VERIFIED


def test_derived_calculation_with_a_false_result_is_never_verified():
    source = _income_statement_source()
    # Real inputs, but a WRONG stated result -- this must fail, not pass
    # merely because each operand independently appears in the source.
    claim = "Operating Income: $1,990M - $1,476M = $999M"
    record = _record_linked_to(source, claim=claim)
    result = verify_data_fact_or_derived_calculation(record, [source])
    assert result is None


# ---------------------------------------------------------------------------
# Negative: wrong object / period / value
# ---------------------------------------------------------------------------


def test_a_value_not_present_in_the_source_is_never_verified():
    source = _income_statement_source()
    claim = "Line Item: Total Revenue; 2026-06-30: $99,999M"
    record = _record_linked_to(source, claim=claim)
    assert verify_data_fact_or_derived_calculation(record, [source]) is None


def test_marker_valid_but_source_lacks_the_stated_field_is_never_verified():
    # A source that resolves and has real content, but none of ITS OWN
    # fields match the claim's stated metric/value at all.
    source = _income_statement_source(
        data_snapshot={
            "statement_type": "income statement",
            "line_item": "Net Income",
            "periods": {"2026-06-30": 2297000000.0},
        }
    )
    claim = "Line Item: Total Revenue; 2026-06-30: $11,536M"
    record = _record_linked_to(source, claim=claim)
    assert verify_data_fact_or_derived_calculation(record, [source]) is None


def test_unresolvable_linked_source_is_never_verified():
    record = {
        "claim_id": "claim-1",
        "claim": "Line Item: Total Revenue; 2026-06-30: $11,536M",
        "source_link_status": SOURCE_LINK_VALID,
        "linked_source_id": "does-not-exist",
    }
    assert verify_data_fact_or_derived_calculation(record, []) is None


def test_not_yet_source_linked_claim_is_never_verified():
    source = _income_statement_source()
    record = {
        "claim_id": "claim-1",
        "claim": "Line Item: Total Revenue; 2026-06-30: $11,536M",
        "source_link_status": "NOT_PROVIDED",
        "linked_source_id": None,
    }
    assert verify_data_fact_or_derived_calculation(record, [source]) is None
    assert apply_automated_content_support_verification(record, sources=[source]) is None


# ---------------------------------------------------------------------------
# Negative: compound claims mixing a real number with unverifiable
# interpretation must stay exactly unverified -- the task's own explicit
# requirement that a verified fragment must never promote a whole sentence.
# ---------------------------------------------------------------------------


def test_compound_claim_with_evaluative_language_is_never_upgraded():
    source = _income_statement_source()
    claim = "Revenue of $11,536M is a record and confirms a strong demand environment."
    record = _record_linked_to(source, claim=claim)
    assert verify_data_fact_or_derived_calculation(record, [source]) is None


def test_compound_claim_with_an_unexplained_derived_adjustment_is_never_upgraded():
    source = _income_statement_source()
    claim = "Ex-that gain, clean EPS is closer to $1.12 rather than the reported $1.38."
    record = _record_linked_to(source, claim=claim)
    assert verify_data_fact_or_derived_calculation(record, [source]) is None


def test_informal_paraphrase_of_a_real_field_name_is_conservatively_left_unverified():
    # "cash" / "total debt" are not the source's own exact field names
    # (e.g. "Cash And Cash Equivalents") -- this module never guesses a
    # loose semantic mapping, so this stays unverified even though the
    # numbers themselves are real.
    source = _income_statement_source(
        data_snapshot={
            "line_item": "Cash And Cash Equivalents",
            "periods": {"2026-06-30": 13111000000.0},
            "all_line_items": {
                "Cash And Cash Equivalents": {"2026-06-30": 13111000000.0},
                "Total Debt": {"2026-06-30": 4276000000.0},
            },
        }
    )
    claim = "$13,111M cash vs $4,276M total debt = $8,835M net cash."
    record = _record_linked_to(source, claim=claim)
    assert verify_data_fact_or_derived_calculation(record, [source]) is None


# ---------------------------------------------------------------------------
# Time-contract fix: resolve_evidence_cutoff_at
# ---------------------------------------------------------------------------


def test_evidence_cutoff_prefers_max_source_fetched_at_over_bare_analysis_date():
    sources = [
        {"retrieved_at": "2026-10-05T17:36:24Z"},
        {"retrieved_at": "2026-10-05T10:00:00Z"},
    ]
    cutoff, basis = resolve_evidence_cutoff_at("2026-10-05", sources)
    assert basis == EVIDENCE_CUTOFF_BASIS_MAX_SOURCE_FETCHED_AT
    assert cutoff.startswith("2026-10-05T17:36:24")


def test_evidence_cutoff_falls_back_to_analysis_date_when_no_source_has_retrieved_at():
    cutoff, basis = resolve_evidence_cutoff_at("2026-10-05", [{"source_id": "x"}])
    assert basis == EVIDENCE_CUTOFF_BASIS_ANALYSIS_DATE_FALLBACK
    assert cutoff == "2026-10-05"


def test_evidence_cutoff_falls_back_to_analysis_date_when_sources_is_none():
    cutoff, basis = resolve_evidence_cutoff_at("2026-10-05", None)
    assert basis == EVIDENCE_CUTOFF_BASIS_ANALYSIS_DATE_FALLBACK
    assert cutoff == "2026-10-05"


def test_evidence_cutoff_is_unknown_when_nothing_is_available():
    cutoff, basis = resolve_evidence_cutoff_at(None, None)
    assert cutoff is None
    assert basis == EVIDENCE_CUTOFF_BASIS_UNKNOWN


def test_fixed_cutoff_accepts_a_same_day_retrieval_that_the_old_midnight_cutoff_rejected():
    # The exact round7 false positive: a financial snapshot retrieved
    # mid-morning on its own analysis_date, with the run's OTHER sources
    # fetched later the same day.
    source = build_source_record(
        source_type="financial", name="Yahoo Finance", title="AMD fundamentals snapshot",
        url="", published_at="2026-10-05T10:34:46.683873", retrieved_at="2026-10-05T10:34:46.683873",
        excerpt="AMD fundamentals as retrieved", instrument="AMD", observation_date="2026-10-05",
    )
    later_source = {"retrieved_at": "2026-10-05T17:36:24Z"}
    cutoff, basis = resolve_evidence_cutoff_at("2026-10-05", [source, later_source])
    assert basis == EVIDENCE_CUTOFF_BASIS_MAX_SOURCE_FETCHED_AT
    result = validate_source_reference(source["fragment_id"], sources=[source], evidence_cutoff=cutoff)
    assert result["source_link_status"] == SOURCE_LINK_VALID


def test_fixed_cutoff_still_rejects_a_genuinely_future_dated_source():
    # The fix must never become a blanket relaxation -- a source published
    # strictly after every real fetch in the run is still TIME_INVALID.
    future_source = build_source_record(
        source_type="news", name="Reuters", title="A headline from the future",
        url="https://example.com/x", published_at="2026-10-06T00:00:01", retrieved_at="2026-10-05T17:36:24Z",
        excerpt="some real excerpt text",
    )
    cutoff, _basis = resolve_evidence_cutoff_at("2026-10-05", [future_source])
    result = validate_source_reference(future_source["fragment_id"], sources=[future_source], evidence_cutoff=cutoff)
    assert result["source_link_status"] == "TIME_INVALID"
