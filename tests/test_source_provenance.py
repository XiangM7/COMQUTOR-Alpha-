"""John MVP Final Gap Closure -- Structured External Source Traceability.

Deterministic, offline unit tests for comqutor_alpha.source_provenance:
building SourceRecords from genuine upstream fields, deduping/persisting a
run's registry, and the read-time claim<->source matcher. No Provider call,
no network, no TradingAgents graph invocation anywhere in this file.
"""

from __future__ import annotations

import pytest

from comqutor_alpha.source_provenance import (
    REVIEW_METHOD_HUMAN_REVIEWED,
    REVIEW_METHOD_UNREVIEWED,
    SOURCE_LINK_CONTENT_UNAVAILABLE,
    SOURCE_LINK_NOT_PROVIDED,
    SOURCE_LINK_TIME_INVALID,
    SOURCE_LINK_UNKNOWN_ID,
    SOURCE_LINK_VALID,
    STATUS_PARTIAL,
    STATUS_TRACEABLE,
    STATUS_UNAVAILABLE,
    SUPPORT_PENDING_REVIEW,
    apply_content_support_review,
    build_content_support_review,
    build_source_record,
    build_source_registry,
    classify_metadata_status,
    find_matching_source,
    fragment_id_for,
    make_source_id,
    match_evidence_to_source_candidates,
    public_source_fields,
    resolve_external_source_for_claim,
    resolve_fragment_by_id,
    resolve_source_by_id,
    validate_source_reference,
)

_RETRIEVED_AT = "2026-09-21T00:00:00Z"


# ---------------------------------------------------------------------------
# A. Upstream item with full provenance: title + publisher + URL + date
# ---------------------------------------------------------------------------


def test_full_provenance_item_is_classified_traceable():
    record = build_source_record(
        source_type="news",
        name="Barron's",
        title="Why Stocks Are Loving the Fed's Rate Hike",
        url="https://barrons.com/articles/x",
        published_at="2026-09-17T10:00:00",
        retrieved_at=_RETRIEVED_AT,
        provider="yfinance",
    )
    assert record["metadata_status"] == STATUS_TRACEABLE
    assert record["name"] == "Barron's"
    assert record["title"] == "Why Stocks Are Loving the Fed's Rate Hike"
    assert record["url"] == "https://barrons.com/articles/x"
    assert record["published_at"] == "2026-09-17T10:00:00"
    assert record["retrieved_at"] == _RETRIEVED_AT


def test_deterministic_source_id_is_stable_for_identical_content():
    id_a = make_source_id(source_type="news", name="Barron's", title="Same Headline Text Here", url="https://x/y")
    id_b = make_source_id(source_type="news", name="Barron's", title="Same Headline Text Here", url="https://x/y")
    assert id_a == id_b
    id_different = make_source_id(source_type="news", name="Barron's", title="A Different Headline", url="https://x/y")
    assert id_different != id_a


# ---------------------------------------------------------------------------
# B. Filing/data item with a structured record identifier but no ordinary
#    web URL (e.g. a FRED dataset series id) -- PARTIAL, not UNAVAILABLE,
#    and never fabricated a URL to reach TRACEABLE.
# ---------------------------------------------------------------------------


def test_structured_record_id_without_url_is_partial_never_traceable():
    record = build_source_record(
        source_type="macro_dataset",
        name="FRED",
        title="Consumer Price Index for All Urban Consumers",
        url=None,
        published_at=None,
        retrieved_at=_RETRIEVED_AT,
        external_record_id="CPIAUCSL",
        provider="fred",
    )
    assert record["metadata_status"] == STATUS_PARTIAL
    assert record["url"] is None
    assert record["external_record_id"] == "CPIAUCSL"


# ---------------------------------------------------------------------------
# C. Upstream item with partial provenance (name only, nothing else)
# ---------------------------------------------------------------------------


def test_name_only_item_is_partial():
    record = build_source_record(
        source_type="news", name="Reuters", title=None, url=None, retrieved_at=_RETRIEVED_AT
    )
    assert record["metadata_status"] == STATUS_PARTIAL


# ---------------------------------------------------------------------------
# D. Item with no provenance at all
# ---------------------------------------------------------------------------


def test_item_with_nothing_is_unavailable():
    record = build_source_record(source_type="news", name=None, title=None, url=None, retrieved_at=_RETRIEVED_AT)
    assert record["metadata_status"] == STATUS_UNAVAILABLE
    assert classify_metadata_status(name=None, title="", url="   ") == STATUS_UNAVAILABLE


# ---------------------------------------------------------------------------
# E. Attempted invalid/model-invented source_id
# ---------------------------------------------------------------------------


def test_invented_source_id_is_rejected_not_resolved():
    registry = build_source_registry(
        run_id="run-1",
        ticker="NVDA",
        retrieved_at=_RETRIEVED_AT,
        captured_records=[
            {"source_type": "news", "name": "Barron's", "title": "Real Genuine Article Headline", "url": "https://x"}
        ],
    )
    real_id = registry["sources"][0]["source_id"]
    assert resolve_source_by_id(real_id, registry["sources"]) is not None
    assert resolve_source_by_id("src_totally_invented_by_a_model", registry["sources"]) is None
    assert resolve_source_by_id("", registry["sources"]) is None
    assert resolve_source_by_id(None, registry["sources"]) is None
    assert resolve_source_by_id(123, registry["sources"]) is None


# ---------------------------------------------------------------------------
# Registry building: dedup, no-fabrication, malformed-input safety
# ---------------------------------------------------------------------------


def test_registry_dedupes_identical_captures_by_content():
    same_article = {
        "source_type": "news",
        "name": "Yahoo Finance",
        "title": "Federal Reserve interest rate hike may trigger a move",
        "url": "https://finance.yahoo.com/x",
    }
    registry = build_source_registry(
        run_id="run-1", ticker="NVDA", retrieved_at=_RETRIEVED_AT, captured_records=[same_article, dict(same_article)]
    )
    assert registry["source_count"] == 1


def test_registry_ignores_malformed_captured_entries_without_crashing():
    registry = build_source_registry(
        run_id="run-1",
        ticker="NVDA",
        retrieved_at=_RETRIEVED_AT,
        captured_records=[None, "not a dict", {}, {"name": "no source_type key"}],
    )
    assert registry["source_count"] == 0
    assert registry["sources"] == []


def test_empty_or_none_captured_records_produces_empty_registry():
    for value in (None, []):
        registry = build_source_registry(run_id="run-1", ticker="NVDA", retrieved_at=_RETRIEVED_AT, captured_records=value)
        assert registry["source_count"] == 0


# ---------------------------------------------------------------------------
# Claim<->source matching: deterministic substring match, never inference
# ---------------------------------------------------------------------------


def test_claim_text_containing_real_title_matches_traceable():
    sources = [
        build_source_record(
            source_type="news",
            name="Barron's",
            title="Why Stocks Are Loving the Fed's Rate Hike",
            url="https://barrons.com/x",
            retrieved_at=_RETRIEVED_AT,
        )
    ]
    claim = (
        "Barron's: \"Why Stocks Are Loving the Fed's Rate Hike\" -- equities "
        "initially took the hike constructively."
    )
    match, status = resolve_external_source_for_claim(claim=claim, evidence=claim, sources=sources)
    assert status == STATUS_TRACEABLE
    assert match is not None
    assert match["name"] == "Barron's"


def test_claim_text_matching_is_case_insensitive():
    sources = [build_source_record(source_type="news", name="X", title="A Fairly Long Distinctive Headline", url="https://x", retrieved_at=_RETRIEVED_AT)]
    match, status = resolve_external_source_for_claim(
        claim=None, evidence="quoting: a fairly long distinctive headline here", sources=sources
    )
    assert status == STATUS_TRACEABLE
    assert match is not None


def test_unrelated_claim_text_is_unavailable_never_forced_match():
    sources = [
        build_source_record(
            source_type="news", name="Barron's", title="Why Stocks Are Loving the Fed's Rate Hike",
            url="https://barrons.com/x", retrieved_at=_RETRIEVED_AT,
        )
    ]
    match, status = resolve_external_source_for_claim(
        claim="NVDA gross margin expanded 200bps this quarter.",
        evidence="NVDA gross margin expanded 200bps this quarter.",
        sources=sources,
    )
    assert match is None
    assert status == STATUS_UNAVAILABLE


def test_empty_registry_is_always_unavailable():
    match, status = resolve_external_source_for_claim(claim="anything", evidence="anything", sources=[])
    assert match is None
    assert status == STATUS_UNAVAILABLE
    match2, status2 = resolve_external_source_for_claim(claim="anything", evidence="anything", sources=None)
    assert match2 is None
    assert status2 == STATUS_UNAVAILABLE


def test_short_title_is_registered_but_never_offered_as_a_match():
    # Titles shorter than the matchable-length floor are real, valid
    # sources (still returned in the registry with their own honest
    # metadata_status) -- they are just never used as a substring anchor,
    # since a short phrase risks matching unrelated prose spuriously.
    sources = [build_source_record(source_type="news", name="X", title="Fed cuts", url="https://x", retrieved_at=_RETRIEVED_AT)]
    assert find_matching_source("The Fed cuts rates today in a surprising move.", sources) is None


def test_publisher_name_alone_never_produces_a_match():
    # A bare publisher mention is too weak a signal on its own (see module
    # docstring) -- only a genuine title substring match counts.
    sources = [
        build_source_record(
            source_type="news", name="Reuters", title="A Sufficiently Long Specific Headline Text",
            url="https://reuters.com/x", retrieved_at=_RETRIEVED_AT,
        )
    ]
    match = find_matching_source("Reuters reported today that markets rallied.", sources)
    assert match is None


def test_public_source_fields_only_exposes_whitelisted_keys():
    record = build_source_record(
        source_type="news", name="Barron's", title="A Genuine Headline For Testing",
        url="https://x", retrieved_at=_RETRIEVED_AT,
    )
    record["_internal_debug"] = "should never leak"
    projected = public_source_fields(record)
    assert "_internal_debug" not in projected
    assert projected["name"] == "Barron's"
    assert projected["metadata_status"] == STATUS_TRACEABLE


# ---------------------------------------------------------------------------
# T1 source-linking chain (COMQUTOR Alpha next-round task, 2026-09-26):
# excerpt/content_hash/fragment_id, content-based candidate matching, and
# validate_source_reference's real backend validation gate.
# ---------------------------------------------------------------------------


def _news_source_with_excerpt(
    *, title="NVDA Data Center Revenue Beats Estimates", excerpt="NVDA reported record data center revenue this quarter.",
    published_at="2026-08-05T00:00:00",
):
    return build_source_record(
        source_type="news", name="Reuters", title=title, url="https://reuters.com/nvda-dc",
        published_at=published_at, retrieved_at=_RETRIEVED_AT, excerpt=excerpt,
    )


def test_source_with_excerpt_gets_a_content_hash_and_fragment_id():
    record = _news_source_with_excerpt()
    assert record["content_hash"] is not None
    assert record["fragment_id"] == fragment_id_for(record["source_id"], 0)


def test_source_without_excerpt_has_no_content_hash_or_fragment_id():
    record = build_source_record(
        source_type="news", name="Reuters", title="A Genuine Headline With No Captured Body",
        url="https://reuters.com/x", retrieved_at=_RETRIEVED_AT,
    )
    assert record["excerpt"] is None
    assert record["content_hash"] is None
    assert record["fragment_id"] is None


def test_resolve_fragment_by_id_rejects_a_forged_id():
    record = _news_source_with_excerpt()
    assert resolve_fragment_by_id("frag_model_hallucinated_9999", [record]) is None
    assert resolve_fragment_by_id(record["fragment_id"], [record]) == record


def test_match_evidence_to_source_candidates_finds_exact_excerpt_quote():
    record = _news_source_with_excerpt()
    evidence = "As reported: NVDA reported record data center revenue this quarter. Shares rose."
    candidates = match_evidence_to_source_candidates(evidence, None, [record])
    assert candidates == [record["fragment_id"]]


def test_match_evidence_to_source_candidates_finds_nothing_for_unrelated_text():
    record = _news_source_with_excerpt()
    candidates = match_evidence_to_source_candidates("Completely unrelated commentary about AMD.", None, [record])
    assert candidates == []


def test_match_evidence_to_source_candidates_ignores_sources_without_excerpt():
    record = build_source_record(
        source_type="news", name="Reuters", title="A Genuine Headline With No Captured Body",
        url="https://reuters.com/x", retrieved_at=_RETRIEVED_AT,
    )
    candidates = match_evidence_to_source_candidates("Any text at all, even matching the title.", None, [record])
    assert candidates == []


def test_validate_source_reference_accepts_a_real_valid_fragment_id():
    record = _news_source_with_excerpt()
    result = validate_source_reference(record["fragment_id"], sources=[record])
    assert result["source_link_status"] == SOURCE_LINK_VALID
    assert result["linked_source_id"] == record["source_id"]


def test_validate_source_reference_accepts_a_real_valid_source_id_too():
    record = _news_source_with_excerpt()
    result = validate_source_reference(record["source_id"], sources=[record])
    assert result["source_link_status"] == SOURCE_LINK_VALID


def test_validate_source_reference_rejects_a_forged_id_never_accepted():
    record = _news_source_with_excerpt()
    result = validate_source_reference("src_model_invented_0000", sources=[record])
    assert result["source_link_status"] == SOURCE_LINK_UNKNOWN_ID
    assert result["linked_source_id"] is None


def test_validate_source_reference_rejects_an_id_from_a_different_runs_registry():
    # Same shape as a forged id from this run's own perspective: an id that
    # is real somewhere else is still not a member of THIS registry.
    other_run_record = _news_source_with_excerpt(title="A Totally Different Article Headline")
    this_run_sources = [_news_source_with_excerpt()]
    result = validate_source_reference(other_run_record["fragment_id"], sources=this_run_sources)
    assert result["source_link_status"] == SOURCE_LINK_UNKNOWN_ID


def test_validate_source_reference_flags_content_unavailable_for_identity_only_source():
    record = build_source_record(
        source_type="news", name="Reuters", title="A Genuine Headline With No Captured Body",
        url="https://reuters.com/x", retrieved_at=_RETRIEVED_AT,
    )
    result = validate_source_reference(record["source_id"], sources=[record])
    assert result["source_link_status"] == SOURCE_LINK_CONTENT_UNAVAILABLE
    assert result["linked_source_id"] == record["source_id"]


def test_validate_source_reference_flags_a_source_published_after_the_evidence_cutoff():
    record = _news_source_with_excerpt(published_at="2026-08-20T00:00:00")
    result = validate_source_reference(record["fragment_id"], sources=[record], evidence_cutoff="2026-08-10")
    assert result["source_link_status"] == SOURCE_LINK_TIME_INVALID


def test_validate_source_reference_accepts_a_source_published_on_the_cutoff_date():
    record = _news_source_with_excerpt(published_at="2026-08-10T00:00:00")
    result = validate_source_reference(record["fragment_id"], sources=[record], evidence_cutoff="2026-08-10")
    assert result["source_link_status"] == SOURCE_LINK_VALID


def test_validate_source_reference_with_no_candidate_id_is_not_provided_never_invalid():
    result = validate_source_reference(None, sources=[_news_source_with_excerpt()])
    assert result["source_link_status"] == SOURCE_LINK_NOT_PROVIDED
    assert result["linked_source_id"] is None


# ---------------------------------------------------------------------------
# Content-support review record (COMQUTOR Alpha T1 follow-up, 2026-09-28)
# ---------------------------------------------------------------------------


def test_build_content_support_review_defaults_to_unreviewed():
    review = build_content_support_review(SUPPORT_PENDING_REVIEW)
    assert review["status"] == SUPPORT_PENDING_REVIEW
    assert review["method"] == REVIEW_METHOD_UNREVIEWED
    assert review["reviewer"] is None
    assert review["rationale"] is None
    assert review["reviewed_at"] is None


def test_build_content_support_review_rejects_invalid_status():
    with pytest.raises(ValueError):
        build_content_support_review("NOT_A_REAL_STATUS")


def test_apply_content_support_review_requires_a_real_reviewer_and_rationale():
    record = {"claim_id": "c1", "content_support_status": "PENDING_REVIEW"}
    with pytest.raises(ValueError):
        apply_content_support_review(record, status="SUPPORTS", reviewer="", rationale="looks fine", reviewed_at="2026-09-28")
    with pytest.raises(ValueError):
        apply_content_support_review(record, status="SUPPORTS", reviewer="analyst_a", rationale="", reviewed_at="2026-09-28")


def test_apply_content_support_review_returns_a_new_record_never_mutates_the_original():
    sources = [
        {
            "source_id": "src-1",
            "fragment_id": "src-1:frag-0",
            "content_hash": "sha256:deadbeef",
        }
    ]
    record = {
        "claim_id": "c1",
        "content_support_status": "PENDING_REVIEW",
        "source_link_status": "VALID",
        "linked_source_id": "src-1:frag-0",
    }
    updated = apply_content_support_review(
        record, status="SUPPORTS", reviewer="analyst_a",
        rationale="excerpt directly states the same revenue figure the claim asserts",
        reviewed_at="2026-09-28T00:00:00Z",
        sources=sources,
    )
    assert record["content_support_status"] == "PENDING_REVIEW"  # original untouched
    assert updated["content_support_status"] == "SUPPORTS"
    assert updated["content_support_method"] == REVIEW_METHOD_HUMAN_REVIEWED
    review = updated["content_support_review"]
    assert review["reviewer"] == "analyst_a"
    assert review["method"] == REVIEW_METHOD_HUMAN_REVIEWED
    assert review["reviewed_at"] == "2026-09-28T00:00:00Z"
