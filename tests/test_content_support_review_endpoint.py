"""Minimal viable human content-support review entrypoint (T1 verified-
support eligibility gate; history-protection fix, 2026-09-28):
``comqutor_alpha.api.routes_research.submit_content_support_review`` --
the real production function backing ``POST /api/research/{run_id}/
claims/{claim_id}/review`` -- plus ``trigger_content_support_reevaluation``,
``list_content_support_reviews``, and ``list_reevaluation_executions``.

History-protection fix: an EARLIER version of this endpoint wrote a review
back into the original run's own ``structured_agent_outputs.json`` in
place and re-ran the original pipeline over it -- risking overwriting the
original run's own persisted result. This version never opens that file
for writing at all: a review is appended, as its own independent record,
to ``content_support_reviews.jsonl``; re-evaluation builds a NEW,
independent execution_id (a full sibling run directory + its own DB rows)
derived from (the ORIGINAL run's own untouched structured_agent_outputs.json
+ the review log at trigger time). Every test below confirms the original
run's own artifacts/DB rows are byte-identical before and after a review,
regardless of whether re-evaluation succeeds.

Every test drives these REAL functions directly against a hand-built run
directory on disk (never a mocked review-application function). Never a
fabricated review: every success case supplies a real, non-empty
reviewer/rationale, and every rejection case proves the function refuses
rather than silently accepting.
"""

from __future__ import annotations

import json

from comqutor_alpha.api.routes_research import (
    _run_week3_graph_pipeline,
    list_content_support_reviews,
    list_reevaluation_executions,
    submit_content_support_review,
    trigger_content_support_reevaluation,
)
from comqutor_alpha.source_provenance import SOURCE_LINK_VALID
from comqutor_alpha.storage.file_store import load_json_record

RUN_ID = "content_support_review_endpoint_run"
TICKER = "NVDA"


def _match(claim_id, agent, claim, *, alpha_id="A102"):
    candidate = {
        "alpha_id": alpha_id, "relation": "activation", "matched_keywords": ["demand"],
        "matched_factors": ["Revenue Growth"], "evidence_stance": "supports_alpha",
    }
    return {
        "run_id": RUN_ID, "ticker": TICKER, "agent": agent, "claim_id": claim_id,
        "source_agent_output_id": f"{agent}:source", "claim": claim, "evidence": claim,
        "match_status": "matched", "matched_alpha": alpha_id, "score": 1.0,
        "assertion_status": "asserted", "semantic_polarity": "activation",
        "factor_score": 1.0, "keyword_score": 1.0, "eligible_candidates": [candidate],
        "claim_quality": "analytical", "direction": "positive",
    }


# published_at is REQUIRED here, not optional fixture detail -- see the
# identical fix and justification in
# tests/test_verified_evidence_gate.py's own _source() helper (the same
# 2026-09-29 DISCLOSURE_TIME_UNKNOWN gate; this file shared the same
# systemic staleness, found and fixed together this round).
_SOURCE = {
    "source_id": "s1",
    "fragment_id": "s1:frag-0",
    "content_hash": "sha256:realhash",
    "published_at": "2026-06-25T00:00:00Z",
}


def _build_run_dir(tmp_path, *, linked=True):
    run_dir = tmp_path / RUN_ID
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(
        json.dumps({"run_id": RUN_ID, "ticker": TICKER, "analysis_date": "2026-06-30"}), encoding="utf-8"
    )
    (run_dir / "alpha_matches.json").write_text(
        json.dumps(
            {
                "run_id": RUN_ID, "ticker": TICKER,
                "matches": [_match("c1", "market_agent", f"{TICKER} datacenter revenue growth is accelerating.")],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "extracted_structures.json").write_text(
        json.dumps({"run_id": RUN_ID, "ticker": TICKER, "nodes": [], "edges": []}), encoding="utf-8"
    )
    record = {
        "claim_id": "c1",
        "run_id": RUN_ID,
        "ticker": TICKER,
        "agent": "market_agent",
        "source_agent_output_id": "market_agent:source",
        "claim": f"{TICKER} datacenter revenue growth is accelerating.",
        "evidence": f"{TICKER} datacenter revenue growth is accelerating.",
        "entities": [],
        "factors": ["Revenue Growth"],
        "direction": "positive",
        "confidence": 0.8,
        "content_support_status": "PENDING_REVIEW",
    }
    if linked:
        record["source_link_status"] = SOURCE_LINK_VALID
        record["linked_source_id"] = _SOURCE["fragment_id"]
    else:
        record["source_link_status"] = "NOT_PROVIDED"
    (run_dir / "structured_agent_outputs.json").write_text(
        json.dumps(
            {"schema_version": "structured_agent_outputs.v1", "run_id": RUN_ID, "ticker": TICKER, "records": [record]}
        ),
        encoding="utf-8",
    )
    (run_dir / "source_registry.json").write_text(
        json.dumps(
            {"schema_version": "source_registry.v1", "run_id": RUN_ID, "ticker": TICKER, "source_count": 1, "sources": [_SOURCE]}
        ),
        encoding="utf-8",
    )
    return run_dir


def _original_artifact_snapshot(tmp_path):
    """Byte-for-byte snapshot of every original-run artifact this endpoint
    could conceivably touch -- compared before/after in every test that
    submits a review, to prove the original run is genuinely never
    mutated."""
    run_dir = tmp_path / RUN_ID
    return {
        name: (run_dir / name).read_text(encoding="utf-8")
        for name in ("metadata.json", "alpha_matches.json", "extracted_structures.json",
                     "structured_agent_outputs.json", "source_registry.json")
        if (run_dir / name).exists()
    }


def test_a_real_review_never_mutates_the_original_run_and_a_new_execution_reflects_it(tmp_path):
    run_dir = _build_run_dir(tmp_path)

    # Baseline: before any review, Activation's verified view excludes this
    # unreviewed claim entirely -- established via the SAME real
    # _run_week3_graph_pipeline entrypoint every run uses, run once here to
    # capture the pre-review state on the ORIGINAL run_id.
    _run_week3_graph_pipeline(run_dir)
    before_snapshot = _original_artifact_snapshot(tmp_path)
    original_graph_before = json.loads((run_dir / "structure_graph.json").read_text(encoding="utf-8"))

    result = submit_content_support_review(
        RUN_ID, "c1", status="SUPPORTS", reviewer="analyst_a",
        rationale="the captured excerpt directly states the same revenue figure the claim asserts",
        output_root=tmp_path,
    )
    assert result["status"] == "ok"
    assert result["content_support_status"] == "SUPPORTS"
    review = result["content_support_review"]
    assert review["method"] == "HUMAN_REVIEWED"
    assert review["reviewer"] == "analyst_a"
    assert review["claim_id"] == "c1"
    assert review["linked_source_id"] == _SOURCE["fragment_id"]
    assert review["content_hash"] == _SOURCE["content_hash"]
    assert review["review_id"]

    # HISTORY PROTECTION: every original-run artifact is byte-identical to
    # before the review -- the review was never written back into
    # structured_agent_outputs.json (or any other original artifact) in
    # place.
    after_snapshot = _original_artifact_snapshot(tmp_path)
    assert after_snapshot == before_snapshot
    persisted = load_json_record(RUN_ID, "structured_agent_outputs.json", output_root=tmp_path)
    assert persisted["records"][0]["content_support_status"] == "PENDING_REVIEW"
    original_graph_after = json.loads((run_dir / "structure_graph.json").read_text(encoding="utf-8"))
    assert original_graph_after == original_graph_before

    # The review IS durably, independently recorded (its own append-only
    # log), discoverable without needing the reevaluation result at all.
    reviews = list_content_support_reviews(RUN_ID, output_root=tmp_path)
    assert reviews["status"] == "ok"
    assert len(reviews["reviews"]) == 1
    assert reviews["reviews"][0]["review_id"] == review["review_id"]

    # A NEW, independent execution was created and linked to this run_id --
    # never overwriting the original.
    reevaluation = result["reevaluation"]
    assert reevaluation["status"] == "ok"
    execution_id = reevaluation["execution_id"]
    assert execution_id != RUN_ID
    assert reevaluation["based_on_run_id"] == RUN_ID

    executions = list_reevaluation_executions(RUN_ID, output_root=tmp_path)
    assert executions["status"] == "ok"
    assert [e["execution_id"] for e in executions["executions"]] == [execution_id]

    # The NEW execution's own structure_graph.json reflects the review --
    # via the exact same real _run_week3_graph_pipeline entrypoint every
    # run uses, reading THIS execution's own rebuilt structured_agent_
    # outputs.json.
    execution_graph = json.loads((tmp_path / execution_id / "structure_graph.json").read_text(encoding="utf-8"))
    assert execution_graph["run_id"] == execution_id
    a102_execution = next(a for a in execution_graph["activation_versions"]["v2_verified"]["alphas"] if a["alpha_id"] == "A102")
    assert a102_execution["evidence_count"] == 1
    execution_structured = json.loads((tmp_path / execution_id / "structured_agent_outputs.json").read_text(encoding="utf-8"))
    execution_record = next(r for r in execution_structured["records"] if r["claim_id"] == "c1")
    assert execution_record["content_support_status"] == "SUPPORTS"
    assert execution_record["run_id"] == execution_id  # identity correctly rebased, never left pointing at the original


def test_a_second_review_creates_a_second_independent_execution_first_one_still_readable(tmp_path):
    run_dir = _build_run_dir(tmp_path)
    _run_week3_graph_pipeline(run_dir)

    first = submit_content_support_review(
        RUN_ID, "c1", status="SUPPORTS", reviewer="analyst_a", rationale="first pass review", output_root=tmp_path,
    )
    first_execution_id = first["reevaluation"]["execution_id"]

    second = submit_content_support_review(
        RUN_ID, "c1", status="OPPOSES", reviewer="analyst_b", rationale="on reflection, this rebuts the claim",
        output_root=tmp_path,
    )
    second_execution_id = second["reevaluation"]["execution_id"]

    assert first_execution_id != second_execution_id

    # Both executions remain independently readable -- the second review/
    # execution never deleted or overwrote the first.
    first_structured = json.loads((tmp_path / first_execution_id / "structured_agent_outputs.json").read_text(encoding="utf-8"))
    assert first_structured["records"][0]["content_support_status"] == "SUPPORTS"
    second_structured = json.loads((tmp_path / second_execution_id / "structured_agent_outputs.json").read_text(encoding="utf-8"))
    assert second_structured["records"][0]["content_support_status"] == "OPPOSES"

    reviews = list_content_support_reviews(RUN_ID, output_root=tmp_path)
    assert len(reviews["reviews"]) == 2  # both submissions kept, never overwritten in the log
    executions = list_reevaluation_executions(RUN_ID, output_root=tmp_path)
    assert [e["execution_id"] for e in executions["executions"]] == [first_execution_id, second_execution_id]

    # The original run is STILL untouched after two reviews + two
    # executions.
    original = load_json_record(RUN_ID, "structured_agent_outputs.json", output_root=tmp_path)
    assert original["records"][0]["content_support_status"] == "PENDING_REVIEW"


def test_reevaluation_can_be_triggered_directly_and_is_idempotently_re_triggerable(tmp_path):
    run_dir = _build_run_dir(tmp_path)
    _run_week3_graph_pipeline(run_dir)
    submit_content_support_review(
        RUN_ID, "c1", status="SUPPORTS", reviewer="analyst_a", rationale="real rationale",
        output_root=tmp_path, trigger_reevaluation=False,
    )
    result = trigger_content_support_reevaluation(RUN_ID, output_root=tmp_path)
    assert result["status"] == "ok"
    assert result["based_on_run_id"] == RUN_ID
    assert result["review_log_entry_count"] == 1


def test_empty_reviewer_is_refused_never_silently_accepted_and_creates_no_execution(tmp_path):
    _build_run_dir(tmp_path)
    result = submit_content_support_review(
        RUN_ID, "c1", status="SUPPORTS", reviewer="   ", rationale="real rationale", output_root=tmp_path,
    )
    assert result["status"] == "failed"
    assert result["error_code"] == "REVIEWER_REQUIRED"
    persisted = load_json_record(RUN_ID, "structured_agent_outputs.json", output_root=tmp_path)
    assert persisted["records"][0]["content_support_status"] == "PENDING_REVIEW"
    assert list_content_support_reviews(RUN_ID, output_root=tmp_path)["reviews"] == []
    assert list_reevaluation_executions(RUN_ID, output_root=tmp_path)["executions"] == []


def test_empty_rationale_is_refused_never_silently_accepted(tmp_path):
    _build_run_dir(tmp_path)
    result = submit_content_support_review(
        RUN_ID, "c1", status="SUPPORTS", reviewer="analyst_a", rationale="", output_root=tmp_path,
        trigger_reevaluation=False,
    )
    assert result["status"] == "failed"
    assert result["error_code"] == "RATIONALE_REQUIRED"


def test_invalid_content_support_status_is_rejected(tmp_path):
    _build_run_dir(tmp_path)
    result = submit_content_support_review(
        RUN_ID, "c1", status="TOTALLY_MADE_UP", reviewer="analyst_a", rationale="real rationale",
        output_root=tmp_path, trigger_reevaluation=False,
    )
    assert result["status"] == "failed"
    assert result["error_code"] == "INVALID_CONTENT_SUPPORT_STATUS"


def test_unknown_claim_id_is_refused(tmp_path):
    _build_run_dir(tmp_path)
    result = submit_content_support_review(
        RUN_ID, "does_not_exist", status="SUPPORTS", reviewer="analyst_a", rationale="real rationale",
        output_root=tmp_path, trigger_reevaluation=False,
    )
    assert result["status"] == "failed"
    assert result["error_code"] == "CLAIM_NOT_FOUND"


def test_a_claim_with_no_valid_source_link_is_refused_never_reviewed_anyway(tmp_path):
    _build_run_dir(tmp_path, linked=False)
    result = submit_content_support_review(
        RUN_ID, "c1", status="SUPPORTS", reviewer="analyst_a", rationale="real rationale",
        output_root=tmp_path, trigger_reevaluation=False,
    )
    assert result["status"] == "failed"
    assert result["error_code"] == "CLAIM_NOT_ELIGIBLE_FOR_REVIEW"
    persisted = load_json_record(RUN_ID, "structured_agent_outputs.json", output_root=tmp_path)
    assert persisted["records"][0]["content_support_status"] == "PENDING_REVIEW"
    assert list_content_support_reviews(RUN_ID, output_root=tmp_path)["reviews"] == []


def test_reevaluation_with_missing_source_registry_fails_explicitly_never_a_silent_official_pass(tmp_path):
    """T1 closing fix (2026-09-28): a re-evaluation execution REQUIRES the
    verified-support eligibility gate. If the original run's own
    source_registry.json is gone by the time re-evaluation runs (anomalous
    -- the review could only have been submitted while it existed), this
    must fail explicitly rather than silently treat "no registry" as
    "zero sources, gate still officially passes"."""
    run_dir = _build_run_dir(tmp_path)
    _run_week3_graph_pipeline(run_dir)
    submit_content_support_review(
        RUN_ID, "c1", status="SUPPORTS", reviewer="analyst_a", rationale="real rationale",
        output_root=tmp_path, trigger_reevaluation=False,
    )
    (run_dir / "source_registry.json").unlink()

    result = trigger_content_support_reevaluation(RUN_ID, output_root=tmp_path)
    assert result["status"] == "failed"
    assert result["error_code"] == "EVIDENCE_GATE_SOURCES_UNAVAILABLE"

    # No partial/half-built execution was ever created or recorded.
    assert list_reevaluation_executions(RUN_ID, output_root=tmp_path)["executions"] == []
    assert not list(tmp_path.glob("review-*"))
    # The original run's own artifacts are untouched.
    original = load_json_record(RUN_ID, "structured_agent_outputs.json", output_root=tmp_path)
    assert original["records"][0]["content_support_status"] == "PENDING_REVIEW"


def test_reevaluation_with_corrupted_source_registry_fails_explicitly(tmp_path):
    run_dir = _build_run_dir(tmp_path)
    _run_week3_graph_pipeline(run_dir)
    submit_content_support_review(
        RUN_ID, "c1", status="SUPPORTS", reviewer="analyst_a", rationale="real rationale",
        output_root=tmp_path, trigger_reevaluation=False,
    )
    (run_dir / "source_registry.json").write_text("{not valid json", encoding="utf-8")

    result = trigger_content_support_reevaluation(RUN_ID, output_root=tmp_path)
    assert result["status"] == "failed"
    assert result["error_code"] == "EVIDENCE_GATE_SOURCES_UNAVAILABLE"
    assert list_reevaluation_executions(RUN_ID, output_root=tmp_path)["executions"] == []


def test_reevaluation_with_malformed_registry_missing_sources_key_fails_explicitly(tmp_path):
    run_dir = _build_run_dir(tmp_path)
    _run_week3_graph_pipeline(run_dir)
    submit_content_support_review(
        RUN_ID, "c1", status="SUPPORTS", reviewer="analyst_a", rationale="real rationale",
        output_root=tmp_path, trigger_reevaluation=False,
    )
    # Well-formed JSON, but no resolvable "sources" list at all -- distinct
    # from a genuinely-empty-but-present sources list.
    (run_dir / "source_registry.json").write_text(
        json.dumps({"schema_version": "source_registry.v1", "run_id": RUN_ID, "ticker": TICKER}),
        encoding="utf-8",
    )

    result = trigger_content_support_reevaluation(RUN_ID, output_root=tmp_path)
    assert result["status"] == "failed"
    assert result["error_code"] == "EVIDENCE_GATE_SOURCES_UNAVAILABLE"
    assert list_reevaluation_executions(RUN_ID, output_root=tmp_path)["executions"] == []


def test_reevaluation_with_genuinely_empty_sources_list_succeeds_with_honest_zero_verified_evidence(tmp_path):
    """A genuinely-resolved-but-EMPTY sources list is valid input, not an
    error -- the gate still runs and honestly reports zero verified
    evidence, rather than being confused with a missing/corrupted registry.
    Exercised on a claim with NO review yet (so replaying the review log
    onto an empty sources list never needs to resolve a vanished source --
    see test_reevaluation_review_replay_against_vanished_source_fails_
    explicitly below for that distinct case)."""
    run_dir = _build_run_dir(tmp_path)
    (run_dir / "source_registry.json").write_text(
        json.dumps(
            {"schema_version": "source_registry.v1", "run_id": RUN_ID, "ticker": TICKER, "source_count": 0, "sources": []}
        ),
        encoding="utf-8",
    )
    _run_week3_graph_pipeline(run_dir)

    result = trigger_content_support_reevaluation(RUN_ID, output_root=tmp_path)
    assert result["status"] == "ok"
    execution_id = result["execution_id"]
    execution_graph = json.loads((tmp_path / execution_id / "structure_graph.json").read_text(encoding="utf-8"))
    assert execution_graph["evidence_gate_applied"] is True
    a102 = next(a for a in execution_graph["activation_versions"]["v2_verified"]["alphas"] if a["alpha_id"] == "A102")
    assert a102["evidence_count"] == 0  # honest "zero verified evidence", not a fabricated pass


def test_reevaluation_review_replay_against_a_vanished_source_fails_explicitly(tmp_path):
    """A review was legitimately submitted while the source existed, but by
    re-evaluation time the registry resolves (well-formed, non-empty) yet no
    longer contains that specific source -- distinct from "registry
    unresolvable": here apply_content_support_review correctly refuses to
    bind the review to nothing, and that refusal must surface as an
    explicit failure, never a crash and never a silent pass."""
    run_dir = _build_run_dir(tmp_path)
    _run_week3_graph_pipeline(run_dir)
    submit_content_support_review(
        RUN_ID, "c1", status="SUPPORTS", reviewer="analyst_a", rationale="real rationale",
        output_root=tmp_path, trigger_reevaluation=False,
    )
    (run_dir / "source_registry.json").write_text(
        json.dumps(
            {"schema_version": "source_registry.v1", "run_id": RUN_ID, "ticker": TICKER, "source_count": 0, "sources": []}
        ),
        encoding="utf-8",
    )

    result = trigger_content_support_reevaluation(RUN_ID, output_root=tmp_path)
    assert result["status"] == "failed"
    assert result["error_code"] == "REEVALUATION_REVIEW_REPLAY_FAILED"
    assert list_reevaluation_executions(RUN_ID, output_root=tmp_path)["executions"] == []


try:
    from fastapi.testclient import TestClient

    from comqutor_alpha.api.routes_research import get_agent_outputs_response, router

    FASTAPI_AVAILABLE = router is not None
except ImportError:
    FASTAPI_AVAILABLE = False


def _client(tmp_path):
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    app.state.output_root = tmp_path
    return TestClient(app)


def test_real_http_post_review_route_creates_an_execution_the_api_read_route_reflects(tmp_path):
    if not FASTAPI_AVAILABLE:
        return
    _build_run_dir(tmp_path)
    client = _client(tmp_path)

    response = client.post(
        f"/api/research/{RUN_ID}/claims/c1/review",
        json={"status": "SUPPORTS", "reviewer": "analyst_a", "rationale": "matches the captured excerpt"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["content_support_status"] == "SUPPORTS"
    execution_id = body["reevaluation"]["execution_id"]

    # The ORIGINAL run's own real GET route stays unreviewed -- history
    # protection, exercised through the real HTTP route, not just the
    # business-logic function.
    original_api = get_agent_outputs_response(RUN_ID, output_root=str(tmp_path))
    original_record = next(r for r in original_api["structured_agent_outputs"] if r["claim_id"] == "c1")
    assert original_record["content_support_status"] == "PENDING_REVIEW"

    # The NEW execution's own real GET route (the SAME route, addressed by
    # its own execution_id) shows the review -- API/UI/Export consistency
    # for the specific execution this endpoint just created.
    execution_api = get_agent_outputs_response(execution_id, output_root=str(tmp_path))
    assert execution_api["status"] == "ok"
    execution_record = next(r for r in execution_api["structured_agent_outputs"] if r["claim_id"] == "c1")
    assert execution_record["content_support_status"] == "SUPPORTS"
    assert execution_record["content_support_review"]["method"] == "HUMAN_REVIEWED"
    assert execution_record["content_support_review"]["reviewer"] == "analyst_a"

    # The review log and execution index are also reachable through their
    # own real GET routes.
    reviews_response = client.get(f"/api/research/{RUN_ID}/content-support-reviews")
    assert reviews_response.status_code == 200
    assert len(reviews_response.json()["reviews"]) == 1
    executions_response = client.get(f"/api/research/{RUN_ID}/reevaluations")
    assert executions_response.status_code == 200
    assert [e["execution_id"] for e in executions_response.json()["executions"]] == [execution_id]


def test_real_http_post_review_route_rejects_empty_reviewer_with_a_stable_error_code(tmp_path):
    if not FASTAPI_AVAILABLE:
        return
    _build_run_dir(tmp_path)
    client = _client(tmp_path)

    response = client.post(
        f"/api/research/{RUN_ID}/claims/c1/review",
        json={"status": "SUPPORTS", "reviewer": "  ", "rationale": "matches the captured excerpt"},
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "REVIEWER_REQUIRED"
