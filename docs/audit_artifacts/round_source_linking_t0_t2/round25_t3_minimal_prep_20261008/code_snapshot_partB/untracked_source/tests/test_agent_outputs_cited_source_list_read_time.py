"""2026-10-07 (round 19): the read-time verified-support diagnostic must see a multi-source claim's FULL citation list.

Reproduced on the restarted live service: the A304 claim cites two sources, its content-support review binds the second one, the stored result is
ELIGIBLE -- yet GET /agent-outputs reported REVIEW_SOURCE_NOT_LINKED_TO_CLAIM, because the agent_outputs table has no column for ``linked_source_ids`` and
the public whitelist omits it, so the diagnostic only ever saw the primary link.

These tests use the REAL repository (in-memory SQLite, exactly like tests/test_agent_outputs_source_linking_db_migration.py) and the REAL reader. Fixed
synthetic records; they prove the wiring and every refusal boundary, not any real market result. (The real-run confirmation is in the round-19 report.)
"""

from __future__ import annotations

import hashlib
import json

import pytest

from comqutor_alpha.api import agent_output_reader as reader
from comqutor_alpha.api.agent_output_reader import PUBLIC_STRUCTURED_OUTPUT_FIELDS, get_agent_outputs_response
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository

RUN = "run-r19"
CLAIM = f"{RUN}:portfolio_manager:final_trade_decision:claim:10"


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _source(source_id, excerpt):
    return {"source_id": source_id, "source_type": "financial", "name": "Yahoo Finance", "title": f"AMD snapshot {source_id}", "url": None, "published_at": "2026-10-06T10:00:00",
            "retrieved_at": "2026-10-06T17:39:31Z", "provider": "yfinance", "excerpt": excerpt, "content_hash": _sha(excerpt), "fragment_id": f"{source_id}:frag:0",
            "instrument": "AMD", "observation_date": "2026-10-06", "data_snapshot": {"k": 1}}


PRIMARY = _source("src_primary", "AMD fundamentals Forward EPS=15.72189")
USED = _source("src_used", "AMD income statement Diluted EPS: 2026-06-30=1.38")


def _record(*, review_source="src_used", review_hash=None, cited=("src_primary", "src_used")):
    review = {"schema_version": "content_support_review.v1", "status": "SUPPORTS", "method": "LLM_CONTENT_SUPPORT_VERIFIED", "reviewer": None, "rationale": None,
              "reviewed_at": None, "claim_id": CLAIM, "linked_source_id": review_source,
              "content_hash": review_hash if review_hash is not None else (USED if review_source == "src_used" else PRIMARY)["content_hash"]}
    return {"claim_id": CLAIM, "agent_output_id": CLAIM, "source_agent_output_id": f"{RUN}:portfolio_manager:final_trade_decision", "run_id": RUN, "ticker": "AMD",
            "agent": "portfolio_manager", "claim": "AMD revenue growth accelerated sharply against a forward EPS of $15.72.", "evidence": "AMD revenue growth accelerated sharply against a forward EPS of $15.72.",
            "entities": ["AMD"], "factors": ["Revenue Growth"], "direction": "positive", "confidence": 0.8, "source_type": "financial",
            "source_link_status": "VALID", "linked_source_id": "src_primary", "linked_source_ids": list(cited), "source_link_method": "ORIGINAL_AGENT_MARKER_CITED",
            "content_support_status": "SUPPORTS", "content_support_method": "LLM_CONTENT_SUPPORT_VERIFIED", "content_support_review": review}


def _setup(tmp_path, record, *, artifact=True, artifact_primary=None, corrupt=False):
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    repo = GraphPersistenceRepository(engine)
    repo.persist_agent_outputs(run_id=RUN, ticker="AMD", structured_payload={"run_id": RUN, "ticker": "AMD", "records": [record]})
    run_dir = tmp_path / RUN
    run_dir.mkdir(parents=True)
    (run_dir / "source_registry.json").write_text(json.dumps({"sources": [PRIMARY, USED]}))
    if corrupt:
        (run_dir / "structured_agent_outputs.json").write_text("{not json")
    elif artifact:
        saved = {**record, "linked_source_id": artifact_primary or record["linked_source_id"]}
        (run_dir / "structured_agent_outputs.json").write_text(json.dumps({"run_id": RUN, "ticker": "AMD", "records": [saved]}))
    return repo


def _diagnostic(tmp_path, record, **kw):
    repo = _setup(tmp_path, record, **kw)
    response = get_agent_outputs_response(RUN, output_root=str(tmp_path), graph_repository=repo)
    assert response["status"] == "ok" and response["count"] == 1, response
    return response["structured_agent_outputs"][0]


def test_the_database_really_does_not_keep_the_plural_field(tmp_path):
    """Why the fix reads the saved artifact: the persisted row has only the primary link."""
    repo = _setup(tmp_path, _record())
    row = repo.list_agent_outputs(RUN)[0]
    assert row["linked_source_id"] == "src_primary" and "linked_source_ids" not in row


def test_multi_source_claim_whose_review_binds_a_cited_non_primary_source_is_eligible_at_read_time(tmp_path):
    out = _diagnostic(tmp_path, _record())
    assert out["verified_support_diagnostic"] == {"category": "ELIGIBLE", "detail_code": "ELIGIBLE"}
    assert "linked_source_ids" not in out  # the public contract is unchanged: the list feeds the diagnostic only
    assert set(out) <= PUBLIC_STRUCTURED_OUTPUT_FIELDS


def test_without_the_saved_artifact_the_previous_behaviour_is_kept(tmp_path):
    out = _diagnostic(tmp_path, _record(), artifact=False)
    assert out["verified_support_diagnostic"]["detail_code"] == "REVIEW_SOURCE_NOT_LINKED_TO_CLAIM"


def test_a_corrupt_artifact_degrades_to_the_previous_behaviour_and_never_raises(tmp_path):
    out = _diagnostic(tmp_path, _record(), corrupt=True)
    assert out["verified_support_diagnostic"]["detail_code"] == "REVIEW_SOURCE_NOT_LINKED_TO_CLAIM"


def test_a_review_source_that_the_claim_does_not_cite_is_still_refused(tmp_path):
    out = _diagnostic(tmp_path, _record(cited=("src_primary",)))  # the saved list does not contain the source the review binds
    assert out["verified_support_diagnostic"]["detail_code"] == "REVIEW_SOURCE_NOT_LINKED_TO_CLAIM"


def test_changed_content_is_still_refused_even_with_the_full_citation_list(tmp_path):
    out = _diagnostic(tmp_path, _record(review_hash="0" * 64))
    assert out["verified_support_diagnostic"]["detail_code"] == "CONTENT_VERSION_CHANGED_SINCE_REVIEW"


def test_an_artifact_whose_primary_link_disagrees_with_the_database_row_is_ignored(tmp_path):
    out = _diagnostic(tmp_path, _record(), artifact_primary="src_used")  # two sources of truth that disagree are never mixed
    assert out["verified_support_diagnostic"]["detail_code"] == "REVIEW_SOURCE_NOT_LINKED_TO_CLAIM"


def test_single_source_claims_never_trigger_an_artifact_read(tmp_path, monkeypatch):
    record = _record(review_source="src_primary", cited=("src_primary",))
    repo = _setup(tmp_path, record)
    real = reader.load_json_record_if_exists

    def guarded(run_id, filename, output_root="outputs/runs"):
        assert filename != "structured_agent_outputs.json", "the artifact must not be read when no review binds a non-primary source"
        return real(run_id, filename, output_root=output_root)

    monkeypatch.setattr(reader, "load_json_record_if_exists", guarded)
    out = get_agent_outputs_response(RUN, output_root=str(tmp_path), graph_repository=repo)["structured_agent_outputs"][0]
    assert out["verified_support_diagnostic"]["detail_code"] == "ELIGIBLE"


def test_a_list_saved_for_another_claim_is_not_applied(tmp_path):
    record = _record()
    repo = _setup(tmp_path, record, artifact=False)
    other = {**record, "claim_id": f"{RUN}:someone_else:report:claim:1"}
    (tmp_path / RUN / "structured_agent_outputs.json").write_text(json.dumps({"records": [other]}))
    out = get_agent_outputs_response(RUN, output_root=str(tmp_path), graph_repository=repo)["structured_agent_outputs"][0]
    assert out["verified_support_diagnostic"]["detail_code"] == "REVIEW_SOURCE_NOT_LINKED_TO_CLAIM"


@pytest.mark.parametrize("bad", [None, "src_used", [], [""], [1, 2], {"a": 1}])
def test_a_malformed_citation_list_in_the_artifact_is_ignored(tmp_path, bad):
    record = _record()
    repo = _setup(tmp_path, record, artifact=False)
    (tmp_path / RUN / "structured_agent_outputs.json").write_text(json.dumps({"records": [{**record, "linked_source_ids": bad}]}))
    out = get_agent_outputs_response(RUN, output_root=str(tmp_path), graph_repository=repo)["structured_agent_outputs"][0]
    assert out["verified_support_diagnostic"]["detail_code"] == "REVIEW_SOURCE_NOT_LINKED_TO_CLAIM"
