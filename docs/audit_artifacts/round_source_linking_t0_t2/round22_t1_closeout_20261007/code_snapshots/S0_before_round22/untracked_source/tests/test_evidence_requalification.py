"""2026-10-07 (round 18): evidence-eligibility re-qualification -- unit / flow tests on SYNTHETIC records.

These prove the rules and are reported separately from the real AMD results. Synthetic material only; nothing here reads a
real run except the single clearly-marked reproduction test at the end (skipped if the saved run is absent).

Covers:
  * time basis: a live financial snapshot captured before the evidence cutoff is eligible; counter-examples -- captured after
    the cutoff, time missing/unparseable, only a period end, a forged or inconsistent availability record, wrong source type,
    broken content hash -- all stay unverified; published_at is never filled in;
  * review binding: the same content bound to a multi-source claim's USED source is accepted; genuinely changed content,
    a review naming a source the claim does not cite, and hash-shopping are refused;
  * relation: a qualifying relation is consumed, 'mention' is excluded (no rule change was made).
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from comqutor_alpha.source_provenance import (
    AVAILABILITY_ANNOTATION_DERIVED_FROM_SAVED_REGISTRY,
    AVAILABILITY_ANNOTATION_REGISTRY_WRITE,
    ELIGIBILITY_REASON_AVAILABILITY_AFTER_CUTOFF,
    ELIGIBILITY_REASON_DISCLOSURE_TIME_UNKNOWN,
    ELIGIBILITY_REASON_REVIEW_SOURCE_NOT_LINKED,
    annotate_sources_availability,
    classify_verified_support_diagnostic,
    compute_verified_support_eligibility,
    evaluate_source_availability,
)

RUN = "run-1"
ANALYSIS_DATE = "2026-10-06"
SAVE_TIME = "2026-10-06T17:39:31Z"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _statement_source(source_id="src_stmt", *, retrieved_at=SAVE_TIME, published_at=None, source_type="financial", with_snapshot=True, excerpt=None):
    excerpt = excerpt or "AMD income statement (quarterly) Total Revenue: 2026-06-30=11536000000.0"
    return {
        "source_id": source_id, "source_type": source_type, "name": "Yahoo Finance", "title": f"AMD income statement {source_id}", "url": None,
        "published_at": published_at, "retrieved_at": retrieved_at, "provider": "yfinance", "excerpt": excerpt, "content_hash": _sha(excerpt),
        "fragment_id": f"{source_id}:frag:0", "instrument": "AMD", "observation_date": "2026-06-30", "unit": "UNKNOWN_CURRENCY",
        "data_snapshot": {"line_item": "Total Revenue", "periods": {"2026-06-30": 11536000000.0}} if with_snapshot else None,
    }


def _record(source, *, claim_id="c1", status="SUPPORTS", method="LLM_CONTENT_SUPPORT_VERIFIED", review_source=None, review_hash=None, linked_ids=None):
    return {
        "claim_id": claim_id, "source_link_status": "VALID", "linked_source_id": source["source_id"], "linked_source_ids": linked_ids or [source["source_id"]],
        "content_support_review": {"schema_version": "content_support_review.v1", "status": status, "method": method, "claim_id": claim_id,
                                    "linked_source_id": review_source if review_source is not None else source["source_id"],
                                    "content_hash": review_hash if review_hash is not None else source["content_hash"]},
    }


def _annotated(sources, analysis_date=ANALYSIS_DATE):
    out, _ = annotate_sources_availability(sources, analysis_date, mode=AVAILABILITY_ANNOTATION_REGISTRY_WRITE)
    return out


# ---------------------------------------------------------------------------
# Time basis
# ---------------------------------------------------------------------------


def test_live_snapshot_captured_before_the_cutoff_is_eligible_and_published_at_stays_unknown():
    source = _statement_source()
    (annotated,) = _annotated([source])
    assert annotated["published_at"] is None, "a capture time must never be written into published_at"
    assert annotated["availability"]["published_at_status"] == "UNKNOWN_NOT_BACKFILLED"
    assert annotated["observation_date"] == "2026-06-30", "the period end is kept as the period end"
    assert evaluate_source_availability(annotated)["available_before_cutoff"] is True
    assert compute_verified_support_eligibility(_record(source), [annotated]) == {"eligible": True, "reason_code": "ELIGIBLE", "support_status": "SUPPORTS"}


def test_without_an_availability_record_an_undated_snapshot_stays_unverified():
    source = _statement_source()
    assert compute_verified_support_eligibility(_record(source), [source])["reason_code"] == ELIGIBILITY_REASON_DISCLOSURE_TIME_UNKNOWN


def test_a_snapshot_obtained_after_the_cutoff_cannot_support_an_earlier_judgment():
    # analysis declared for 2026-10-01 but the snapshot was fetched on 10-06: the cutoff falls back to the bare analysis date.
    source = _statement_source(retrieved_at="2026-10-06T17:39:31Z")
    (annotated,) = _annotated([source], analysis_date="2026-10-01")
    assert annotated["availability"]["cutoff_basis"] == "ANALYSIS_DATE_FALLBACK_MIDNIGHT"
    assert evaluate_source_availability(annotated)["reason_code"] == ELIGIBILITY_REASON_AVAILABILITY_AFTER_CUTOFF
    result = compute_verified_support_eligibility(_record(source), [annotated])
    assert result == {"eligible": False, "reason_code": ELIGIBILITY_REASON_AVAILABILITY_AFTER_CUTOFF}
    assert classify_verified_support_diagnostic(_record(source), [annotated])["category"] == "DISCLOSURE_TIME_UNKNOWN"


def test_a_period_end_earlier_than_the_cutoff_proves_nothing():
    """The figure is for 2026-06-30, well before the cutoff -- but it was obtained after it. Period end is never the basis."""
    source = _statement_source(retrieved_at="2026-10-06T17:39:31Z")
    (annotated,) = _annotated([source], analysis_date="2026-09-01")
    assert annotated["observation_date"] == "2026-06-30" < "2026-09-01"
    assert compute_verified_support_eligibility(_record(source), [annotated])["eligible"] is False


@pytest.mark.parametrize("retrieved_at", [None, "", "not a time"])
def test_missing_or_unparseable_capture_time_stays_unknown(retrieved_at):
    source = _statement_source(retrieved_at=retrieved_at)
    (annotated,) = _annotated([source])
    assert evaluate_source_availability(annotated)["reason_code"] == ELIGIBILITY_REASON_DISCLOSURE_TIME_UNKNOWN
    assert compute_verified_support_eligibility(_record(source), [annotated])["reason_code"] == ELIGIBILITY_REASON_DISCLOSURE_TIME_UNKNOWN


def test_a_forged_or_inconsistent_availability_record_is_refused():
    source = _statement_source()
    (good,) = _annotated([source])

    forged_flag = copy.deepcopy(good)
    forged_flag["retrieved_at"] = "2026-10-07T09:00:00Z"  # fetched later than the cutoff, but the block still says "before"
    forged_flag["availability"]["available_before_cutoff"] = True  # a stored boolean is never trusted
    assert evaluate_source_availability(forged_flag)["available_before_cutoff"] is False

    decoupled = copy.deepcopy(good)
    decoupled["availability"]["available_by"] = "2026-10-06T00:00:01Z"  # not this source's own retrieved_at
    assert evaluate_source_availability(decoupled)["reason_code"] == ELIGIBILITY_REASON_DISCLOSURE_TIME_UNKNOWN

    unknown_basis = copy.deepcopy(good)
    unknown_basis["availability"]["basis"] = "TRUST_ME"
    assert evaluate_source_availability(unknown_basis)["reason_code"] == ELIGIBILITY_REASON_DISCLOSURE_TIME_UNKNOWN

    broken_hash = copy.deepcopy(good)
    broken_hash["excerpt"] = broken_hash["excerpt"] + " (edited)"  # content no longer matches its recorded hash
    assert evaluate_source_availability(broken_hash)["reason_code"] == ELIGIBILITY_REASON_DISCLOSURE_TIME_UNKNOWN


def test_only_live_financial_data_snapshots_are_annotated_and_dated_sources_are_left_alone():
    news = _statement_source("src_news", source_type="news", published_at=None)
    no_snapshot = _statement_source("src_nosnap", with_snapshot=False)
    dated = _statement_source("src_dated", published_at="2026-10-06T10:37:04")
    stmt = _statement_source("src_stmt")
    out = _annotated([news, no_snapshot, dated, stmt])
    assert [("availability" in s) for s in out] == [False, False, False, True]
    assert out[2]["published_at"] == "2026-10-06T10:37:04"
    assert compute_verified_support_eligibility(_record(dated), [out[2]])["eligible"] is True, "the dated path is unchanged"
    assert compute_verified_support_eligibility(_record(news), [out[0]])["reason_code"] == ELIGIBILITY_REASON_DISCLOSURE_TIME_UNKNOWN


def test_annotation_is_deterministic_and_never_reads_the_current_time(monkeypatch):
    import comqutor_alpha.source_provenance as sp

    sources = [_statement_source("a"), _statement_source("b", retrieved_at="2026-10-06T17:00:00Z")]
    first = annotate_sources_availability(sources, ANALYSIS_DATE, mode=AVAILABILITY_ANNOTATION_DERIVED_FROM_SAVED_REGISTRY)
    monkeypatch.setattr(sp.dt, "datetime", type("NoClock", (), {"now": staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("clock read"))),
                                                               "fromisoformat": sp.dt.datetime.fromisoformat, "strptime": sp.dt.datetime.strptime}))
    second = annotate_sources_availability(sources, ANALYSIS_DATE, mode=AVAILABILITY_ANNOTATION_DERIVED_FROM_SAVED_REGISTRY)
    assert first == second
    # evidence cutoff = the latest fetched moment of THIS registry (same-day), reproduced identically later
    assert first[0][0]["availability"]["evidence_cutoff_at"] == "2026-10-06T17:39:31"


# ---------------------------------------------------------------------------
# Review binding (the "content hash mismatch")
# ---------------------------------------------------------------------------


def _two_dated_sources():
    primary = _statement_source("src_primary", published_at="2026-10-06T10:00:00", excerpt="AMD fundamentals as retrieved: Forward EPS=15.72")
    used = _statement_source("src_used", published_at="2026-10-06T10:01:00", excerpt="AMD income statement Diluted EPS: 2026-06-30=1.38")
    return primary, used


def test_same_content_bound_to_the_used_source_of_a_multi_source_claim_is_accepted():
    primary, used = _two_dated_sources()
    record = _record(primary, review_source="src_used", review_hash=used["content_hash"], linked_ids=["src_primary", "src_used"])
    assert record["content_support_review"]["content_hash"] != primary["content_hash"], "the old comparison would have called this a changed version"
    assert compute_verified_support_eligibility(record, [primary, used]) == {"eligible": True, "reason_code": "ELIGIBLE", "support_status": "SUPPORTS"}


def test_genuinely_changed_content_of_the_used_source_is_still_refused_and_not_migrated():
    primary, used = _two_dated_sources()
    record = _record(primary, review_source="src_used", review_hash=used["content_hash"], linked_ids=["src_primary", "src_used"])
    changed = copy.deepcopy(used)
    changed["excerpt"] = "AMD income statement Diluted EPS: 2026-06-30=1.99"
    changed["content_hash"] = _sha(changed["excerpt"])
    result = compute_verified_support_eligibility(record, [primary, changed])
    assert result == {"eligible": False, "reason_code": "CONTENT_VERSION_CHANGED_SINCE_REVIEW"}


def test_a_review_naming_a_source_the_claim_does_not_cite_is_refused():
    primary, used = _two_dated_sources()
    stranger = _statement_source("src_stranger", published_at="2026-10-06T09:00:00", excerpt="unrelated source text")
    record = _record(primary, review_source="src_stranger", review_hash=stranger["content_hash"], linked_ids=["src_primary", "src_used"])
    assert compute_verified_support_eligibility(record, [primary, used, stranger]) == {"eligible": False, "reason_code": ELIGIBILITY_REASON_REVIEW_SOURCE_NOT_LINKED}


def test_a_review_without_its_own_source_id_is_compared_with_the_primary_link_as_before_no_hash_shopping():
    primary, used = _two_dated_sources()
    legacy = _record(primary, review_hash=used["content_hash"], linked_ids=["src_primary", "src_used"])
    legacy["content_support_review"].pop("linked_source_id")
    # The hash happens to equal ANOTHER cited source's hash, but nothing says the verifier used it: not searched for.
    assert compute_verified_support_eligibility(legacy, [primary, used]) == {"eligible": False, "reason_code": "CONTENT_VERSION_CHANGED_SINCE_REVIEW"}
    ok = _record(primary)
    ok["content_support_review"].pop("linked_source_id")
    assert compute_verified_support_eligibility(ok, [primary, used])["eligible"] is True


def test_the_two_defects_stack_for_the_amd_pattern_and_each_fix_is_needed():
    """Multi-source claim whose used source is an undated statement snapshot: binding fix alone -> time unknown; both -> eligible."""
    primary = _statement_source("src_primary", published_at="2026-10-06T10:00:00", excerpt="AMD fundamentals as retrieved: Forward EPS=15.72")
    used = _statement_source("src_used")
    record = _record(primary, review_source="src_used", review_hash=used["content_hash"], linked_ids=["src_primary", "src_used"])
    assert compute_verified_support_eligibility(record, [primary, used])["reason_code"] == ELIGIBILITY_REASON_DISCLOSURE_TIME_UNKNOWN
    assert compute_verified_support_eligibility(record, [primary, *_annotated([used])])["eligible"] is True


# ---------------------------------------------------------------------------
# Generation path: the registry writer stamps the availability record on new runs
# ---------------------------------------------------------------------------


def test_the_registry_writer_stamps_availability_on_an_undated_snapshot_and_nothing_else(tmp_path):
    from comqutor_alpha.adapters.tradingagents_output_writer import save_comqutor_run_outputs

    captured = [
        {"source_type": "financial", "name": "Yahoo Finance", "title": "AMD income statement Total Revenue snapshot 2026-06-30 (quarterly)", "url": "", "published_at": None,
         "provider": "yfinance", "excerpt": "AMD income statement (quarterly) Total Revenue: 2026-06-30=11536000000.0", "instrument": "AMD", "observation_date": "2026-06-30",
         "unit": "UNKNOWN_CURRENCY", "data_snapshot": {"line_item": "Total Revenue", "periods": {"2026-06-30": 11536000000.0}}},
        {"source_type": "news", "name": "Reuters", "title": "AMD ships new part", "url": "https://example.invalid/a", "published_at": "2026-10-06T12:00:00Z",
         "provider": "yfinance", "excerpt": "AMD ships a new data-center part this week."},
    ]
    today = __import__("datetime").datetime.now(__import__("datetime").UTC).strftime("%Y-%m-%d")
    run_dir = save_comqutor_run_outputs({"fundamentals_report": "x"}, "AMD", analysis_date=today, output_root=str(tmp_path), captured_sources=captured)
    registry = json.loads((Path(run_dir) / "source_registry.json").read_text())
    by_type = {source["source_type"]: source for source in registry["sources"]}  # the registry orders its entries itself
    statement, news = by_type["financial"], by_type["news"]
    assert statement["published_at"] is None and statement["availability"]["basis"] == "REGISTRY_WRITE_TIME_UPPER_BOUND"
    assert statement["availability"]["annotation_mode"] == AVAILABILITY_ANNOTATION_REGISTRY_WRITE
    assert evaluate_source_availability(statement)["available_before_cutoff"] is True
    assert "availability" not in news and news["published_at"] == "2026-10-06T12:00:00Z"


# ---------------------------------------------------------------------------
# Relation: qualifying relations are consumed, 'mention' is excluded (no rule change)
# ---------------------------------------------------------------------------


def _match(claim_id, relation):
    return {"claim_id": claim_id, "match_status": "matched", "matched_alpha": "A304", "claim": "c", "evidence": "valuation evidence", "score": 0.7,
            "claim_quality": "analytical", "analysis_eligible": True, "direction": "negative", "agent": "bear_researcher", "assertion_status": "asserted",
            "semantic_polarity": "activation", "source_agent_output_id": "o1", "factors": [],
            "candidate_scores": [{"alpha_id": "A304", "relation": relation, "score": 0.7, "evidence_stance": "supports_alpha"}]}


def test_a_qualifying_relation_is_consumed_and_a_mention_is_excluded_as_unsupported_relation():
    from comqutor_alpha.conflict_engine.conflict_detector import _gather_qualifying_evidence

    result = _gather_qualifying_evidence("A304", [_match("good", "activation"), _match("bg", "mention")], {})
    assert [c["claim_id"] for c in result.qualifying] == ["good"]
    assert result.excluded == [{"claim_id": "bg", "reason_code": "UNSUPPORTED_RELATION"}]


# ---------------------------------------------------------------------------
# One clearly-marked reproduction on the saved real record (skipped when absent)
# ---------------------------------------------------------------------------

SAVED = Path(__file__).resolve().parents[1] / "outputs" / "runs" / "recovery-20261007T053635Z-26d6cd1a"


@pytest.mark.skipif(not (SAVED / "structured_agent_outputs.json").exists(), reason="saved recovery run not present")
def test_reproduction_on_the_saved_real_a304_claim_binding_and_relation_origin():
    records = {r["claim_id"]: r for r in json.loads((SAVED / "structured_agent_outputs.json").read_text())["records"]}
    sources = json.loads((SAVED / "source_registry.json").read_text())["sources"]
    record = records["c904d4cc-dc09-495c-aec5-b056979948e1:portfolio_manager:final_trade_decision:claim:10"]
    by_id = {s["source_id"]: s for s in sources}
    review = record["content_support_review"]
    assert review["linked_source_id"] != record["linked_source_id"], "this is the one claim whose review is bound to a non-primary source"
    assert review["content_hash"] == by_id[review["linked_source_id"]]["content_hash"], "content unchanged: the review hash IS its own source's hash"
    assert hashlib.sha256(by_id[review["linked_source_id"]]["excerpt"].encode()).hexdigest() == review["content_hash"]
    # binding fixed, time still unknown on the saved registry (no availability record yet) ...
    assert compute_verified_support_eligibility(record, sources)["reason_code"] == ELIGIBILITY_REASON_DISCLOSURE_TIME_UNKNOWN
    # ... and eligible once the derived availability record is added (analysis date = the original one)
    annotated, _ = annotate_sources_availability(sources, "2026-10-06", mode=AVAILABILITY_ANNOTATION_DERIVED_FROM_SAVED_REGISTRY)
    assert compute_verified_support_eligibility(record, annotated)["eligible"] is True
    # the relation is a code-derived rule, reproduced: negated assertion -> 'mention'
    from comqutor_alpha.structure_engine.claim_semantics import alpha_relation

    assert alpha_relation(record["claim"], "A304") == "mention"
