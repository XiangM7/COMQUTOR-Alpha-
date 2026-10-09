"""T1 verified-support eligibility gate -- Part 2 closing acceptance
(2026-09-29): one full, offline round trip through the REAL content-support
review -> re-evaluation -> page-facing read APIs -> REAL export entrypoint,
driven entirely by fixed, hand-built offline data (no Provider, no Fresh
Research, no network).

Confirms, against the REAL production functions (never a mock, never a
reimplementation):
- the new execution's result, its review record, its source references, its
  rule version, and its execution_id are all mutually consistent;
- the export bundle reflects ONLY the review snapshot THIS execution
  actually used at trigger time -- never contaminated by a review appended
  to the original run afterward;
- the original run_id / input version / evidence-cutoff-time association is
  preserved on the new execution;
- the original run's own input artifacts, structure_graph.json, and
  page-facing API response are byte-for-byte unchanged throughout;
- the new execution's own page-facing API (the same functions the frontend
  calls: build_research_response, get_agent_outputs_response) correctly
  reads the new, gate-filtered result.

DB dialect actually exercised here: SQLite. This module carries no
``integration`` marker, and ``tests/conftest.py``'s autouse
``_isolate_database_env`` fixture strips ``COMQUTOR_DATABASE_URL`` (and,
for a non-integration test, ``COMQUTOR_TEST_DATABASE_URL`` too) from the
process environment before every test -- so
``build_write_repository_from_env``/``build_repository_from_env`` always
fall back to the local, on-disk SQLite backend here, never PostgreSQL. A
real-PostgreSQL run of this exact review/re-evaluation path (against the
isolated COMQUTOR_TEST_DATABASE_URL test database, never production) is a
separate, explicit verification -- see the round's closing report for
whether that was performed this round.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

from comqutor_alpha.api.agent_output_reader import get_agent_outputs_response
from comqutor_alpha.api.routes_research import (
    _run_week3_graph_pipeline,
    build_research_response,
    get_run_export_bundle,
    list_content_support_reviews,
    submit_content_support_review,
)
from comqutor_alpha.graph_engine.verified_evidence_gate import (
    ACTIVATION_V2_VERIFIED_FORMULA_VERSION,
    EVIDENCE_GATE_VERSION,
)
from comqutor_alpha.source_provenance import SOURCE_LINK_VALID
from comqutor_alpha.storage.file_store import load_json_record

RUN_ID = "reevaluation_export_roundtrip_run"
TICKER = "NVDA"
# published_at is REQUIRED here, not optional fixture detail: John follow-up
# round task (2026-09-30, "handle the review->reevaluation->export failure")
# traced test_full_offline_reevaluation_and_export_round_trip's own
# a102["evidence_count"] == 1 assertion failing (actual 0) directly to
# compute_verified_support_eligibility returning reason_code=
# "DISCLOSURE_TIME_UNKNOWN" for this exact source -- a real, deliberately
# added 2026-09-29 gate (see that function's own docstring, item 6) that
# this fixture's source predates/never satisfied: a source with no known
# published_at can be real, resolvable, content-locatable, and even
# HUMAN_REVIEWED SUPPORTS, yet still never counts as VERIFIED support,
# precisely because its disclosure timing is unknown. This is the real,
# already-confirmed production contract working as designed, not an
# implementation defect -- the fixture is what was stale. Fixed by supplying
# a real-shaped disclosure timestamp strictly before the run's own
# evidence-cutoff/analysis_date ("2026-06-30" below), never by lowering the
# evidence_count expectation to 0 to make the symptom disappear.
_SOURCE = {
    "source_id": "s1",
    "fragment_id": "s1:frag-0",
    "content_hash": "sha256:realhash",
    "published_at": "2026-06-25T00:00:00Z",
}


def _match(claim_id, *, alpha_id="A102"):
    candidate = {
        "alpha_id": alpha_id, "relation": "activation", "matched_keywords": ["demand"],
        "matched_factors": ["Revenue Growth"], "evidence_stance": "supports_alpha",
    }
    claim = f"{TICKER} datacenter revenue growth is accelerating."
    return {
        "run_id": RUN_ID, "ticker": TICKER, "agent": "market_agent", "claim_id": claim_id,
        "source_agent_output_id": "market_agent:source", "claim": claim, "evidence": claim,
        "match_status": "matched", "matched_alpha": alpha_id, "score": 1.0,
        "assertion_status": "asserted", "semantic_polarity": "activation",
        "factor_score": 1.0, "keyword_score": 1.0, "eligible_candidates": [candidate],
        "claim_quality": "analytical", "direction": "positive",
    }


def _build_run_dir(tmp_path):
    run_dir = tmp_path / RUN_ID
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(
        json.dumps({"run_id": RUN_ID, "ticker": TICKER, "analysis_date": "2026-06-30"}), encoding="utf-8"
    )
    (run_dir / "alpha_matches.json").write_text(
        json.dumps({"run_id": RUN_ID, "ticker": TICKER, "matches": [_match("c1")]}), encoding="utf-8"
    )
    (run_dir / "extracted_structures.json").write_text(
        json.dumps({"run_id": RUN_ID, "ticker": TICKER, "nodes": [], "edges": []}), encoding="utf-8"
    )
    record = {
        "claim_id": "c1", "run_id": RUN_ID, "ticker": TICKER, "agent": "market_agent",
        "source_agent_output_id": "market_agent:source",
        "claim": f"{TICKER} datacenter revenue growth is accelerating.",
        "evidence": f"{TICKER} datacenter revenue growth is accelerating.",
        "entities": [], "factors": ["Revenue Growth"], "direction": "positive", "confidence": 0.8,
        "content_support_status": "PENDING_REVIEW",
        "source_link_status": SOURCE_LINK_VALID,
        "linked_source_id": _SOURCE["fragment_id"],
    }
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


def _read_zip_json(raw_bytes, name):
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
        return json.loads(zf.read(name))


def _zip_contents_by_name(raw_bytes):
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def test_full_offline_reevaluation_and_export_round_trip(tmp_path):
    run_dir = _build_run_dir(tmp_path)
    _run_week3_graph_pipeline(run_dir)

    # --- Baseline: the ORIGINAL run's own artifacts/API response before any
    # review is ever submitted. ---
    original_metadata = load_json_record(RUN_ID, "metadata.json", output_root=tmp_path)
    original_structured_before = load_json_record(RUN_ID, "structured_agent_outputs.json", output_root=tmp_path)
    original_graph_before = json.loads((run_dir / "structure_graph.json").read_text(encoding="utf-8"))
    original_research_before = build_research_response(RUN_ID, output_root=tmp_path)

    # --- Step 1: submit a review through the real review endpoint -- this
    # creates a NEW execution via the real trigger_content_support_
    # reevaluation, itself wrapping the same real _run_week3_graph_pipeline
    # every ordinary run uses, with require_verified_evidence_gate=True. ---
    review_result = submit_content_support_review(
        RUN_ID, "c1", status="SUPPORTS", reviewer="analyst_a",
        rationale="the captured excerpt directly states the same revenue figure the claim asserts",
        output_root=tmp_path,
    )
    assert review_result["status"] == "ok"
    review_id = review_result["content_support_review"]["review_id"]
    execution_id = review_result["reevaluation"]["execution_id"]
    assert review_result["reevaluation"]["status"] == "ok"
    assert execution_id != RUN_ID

    # The review record itself is independently discoverable via the real
    # review-log read route, keyed by the same review_id this submission
    # returned.
    reviews_after_first = list_content_support_reviews(RUN_ID, output_root=tmp_path)
    assert reviews_after_first["status"] == "ok"
    assert [r["review_id"] for r in reviews_after_first["reviews"]] == [review_id]

    # --- Step 2: re-read via the SAME real, page-facing APIs the frontend
    # (useResearchRun) calls: GET /api/research/{run_id} and GET
    # /api/research/{run_id}/agent-outputs. ---
    execution_research = build_research_response(execution_id, output_root=tmp_path)
    assert execution_research["run_id"] == execution_id
    # This fixture (like its sibling in test_content_support_review_endpoint
    # .py) never writes raw_agent_outputs.json, so "status" tops out at
    # "partial" for both the original run and every execution derived from
    # it -- consistent, not a regression. structure_graph_status/
    # conflict_status are the fields that actually depend on the gate.
    assert execution_research["status"] == original_research_before["status"]
    assert execution_research["structure_graph_status"] == "ready"
    assert execution_research["conflict_status"] == "ready"
    execution_agent_outputs = get_agent_outputs_response(execution_id, output_root=tmp_path)
    assert execution_agent_outputs["status"] == "ok"
    execution_record = next(r for r in execution_agent_outputs["structured_agent_outputs"] if r["claim_id"] == "c1")
    assert execution_record["content_support_status"] == "SUPPORTS"
    # review_id itself lives only on the independent content_support_reviews
    # .jsonl log entry (assigned in submit_content_support_review, after
    # apply_content_support_review already returned) -- the record's own
    # embedded content_support_review carries the review's substance
    # (reviewer/rationale/content_hash), which IS what gets replayed here.
    assert execution_record["content_support_review"]["reviewer"] == "analyst_a"
    assert execution_record["content_support_review"]["status"] == "SUPPORTS"
    assert execution_record["content_support_review"]["content_hash"] == _SOURCE["content_hash"]
    assert execution_record["linked_source"]["source_id"] == _SOURCE["source_id"]

    # The execution's own persisted structure_graph.json shows the gate
    # genuinely applied, with the distinct verified-gate rule version --
    # never the plain (unfiltered) v2 formula version as primary.
    execution_graph = json.loads((tmp_path / execution_id / "structure_graph.json").read_text(encoding="utf-8"))
    assert execution_graph["run_id"] == execution_id
    assert execution_graph["evidence_gate_applied"] is True
    assert execution_graph["evidence_gate_version"] == EVIDENCE_GATE_VERSION
    assert execution_graph["primary_activation_version"] == ACTIVATION_V2_VERIFIED_FORMULA_VERSION
    a102 = next(a for a in execution_graph["activation_versions"]["v2_verified"]["alphas"] if a["alpha_id"] == "A102")
    assert a102["evidence_count"] == 1

    # --- Step 3: call the REAL export entrypoint for the new execution. ---
    status_code, content_type, raw_bytes, filename, error_body = get_run_export_bundle(
        execution_id, output_root=tmp_path
    )
    assert status_code == 200, error_body
    assert content_type == "application/zip"
    exported_metadata = _read_zip_json(raw_bytes, "metadata.json")
    exported_structured = _read_zip_json(raw_bytes, "structured_agent_outputs.json")

    # Lineage/version association preserved: the new execution's own
    # exported metadata still names the ORIGINAL run_id, the exact input
    # version it was built from, and the review-log depth it replayed --
    # and the evidence-cutoff time (analysis_date) carries over from the
    # ORIGINAL run's own metadata, never a fresh "now".
    assert exported_metadata["run_id"] == execution_id
    assert exported_metadata["based_on_run_id"] == RUN_ID
    assert exported_metadata["execution_type"] == "content_support_review_reevaluation"
    assert exported_metadata["review_log_entry_count_at_trigger"] == 1
    assert exported_metadata["analysis_date"] == original_metadata["analysis_date"]
    # input_structured_agent_outputs_sha256 pins the EXACT pre-review input
    # version this execution was built from -- recomputed independently here
    # (the same way trigger_content_support_reevaluation derives it) against
    # the ORIGINAL run's own structured_agent_outputs.json baseline.
    expected_input_sha256 = hashlib.sha256(
        json.dumps(original_structured_before, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    assert exported_metadata["input_structured_agent_outputs_sha256"] == expected_input_sha256
    exported_record = next(r for r in exported_structured["records"] if r["claim_id"] == "c1")
    assert exported_record["content_support_status"] == "SUPPORTS"
    assert exported_record["content_support_review"]["reviewer"] == "analyst_a"
    assert exported_record["content_support_review"]["content_hash"] == _SOURCE["content_hash"]
    assert exported_record["run_id"] == execution_id

    # --- Step 4: append a SECOND, later review to the ORIGINAL run -- the
    # FIRST execution's own already-generated export must never reflect it. ---
    second_review = submit_content_support_review(
        RUN_ID, "c1", status="OPPOSES", reviewer="analyst_b",
        rationale="on reflection this rebuts the claim", output_root=tmp_path,
    )
    assert second_review["status"] == "ok"
    second_execution_id = second_review["reevaluation"]["execution_id"]
    assert second_execution_id != execution_id

    status_code_again, _, raw_bytes_again, _, _ = get_run_export_bundle(execution_id, output_root=tmp_path)
    assert status_code_again == 200
    assert _zip_contents_by_name(raw_bytes_again) == _zip_contents_by_name(raw_bytes)
    # The FIRST execution's own live structured_agent_outputs.json (not just
    # the export) is likewise untouched by the second review/execution.
    first_execution_structured_after = load_json_record(
        execution_id, "structured_agent_outputs.json", output_root=tmp_path
    )
    assert first_execution_structured_after == json.loads(json.dumps(exported_structured))

    # --- Step 5: the original run's own inputs, structure_graph.json, and
    # page-facing API response remain byte-for-byte unchanged throughout --
    # two independent reviews/executions later. ---
    original_structured_after = load_json_record(RUN_ID, "structured_agent_outputs.json", output_root=tmp_path)
    assert original_structured_after == original_structured_before
    original_graph_after = json.loads((run_dir / "structure_graph.json").read_text(encoding="utf-8"))
    assert original_graph_after == original_graph_before
    original_research_after = build_research_response(RUN_ID, output_root=tmp_path)
    assert original_research_after == original_research_before
