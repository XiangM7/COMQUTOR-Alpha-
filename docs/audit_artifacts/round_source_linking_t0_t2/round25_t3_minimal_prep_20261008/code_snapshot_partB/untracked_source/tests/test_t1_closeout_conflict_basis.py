"""T1 closeout (Round 22): the evidence basis of a CONFLICT's evidence -- what the run historically did with a claim, and what
can be shown about its basis today -- as two SEPARATE things.

Two data sets, never mixed up:

* ``LEGACY`` -- a trimmed copy of the SAVED historical AMD run ``d5b60b8a-...`` (the run of John's original 34 evidence items):
  REAL data. Its admitted conflict A301__A304 is kept exactly as saved (``IN_OFFICIAL_POOL`` / admitted / low / 14.2594), and its
  records carry no source-link fields, so today's basis is "not linked / not verified" -- stated as a description of what was
  saved, never as "the 34 judgments were wrong" or "there was no basis at the time".
* ``POSITIVE FIXTURE`` -- the real claim 31 of the newer AMD run, placed under a HAND-WRITTEN conflict. Explicitly a FIXTURE (no
  verified real admitted conflict exists in any run); it only proves that a verified basis is shown next to the historical use.

Read-only by construction: building a trace never writes, and the saved conflict / scoring are never re-evaluated.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

import pytest

from comqutor_alpha.api.evidence_trace import (
    HISTORICAL_USE_NOTE,
    LEGACY_REASON_CODE,
    LEGACY_RUN_NOTE,
    _conflict_adoption_index,
    build_claim_trace,
    get_evidence_trace_response,
    load_trace_context,
)

FIXTURES = Path(__file__).parent / "fixtures"
LEGACY = json.loads((FIXTURES / "t1_closeout_legacy_conflict_excerpt.json").read_text(encoding="utf-8"))
AMD = json.loads((FIXTURES / "t1_closure_amd_excerpt.json").read_text(encoding="utf-8"))
LEGACY_RUN_ID = LEGACY["_provenance"]["source_run_id"]
CLAIMS = LEGACY["_provenance"]["claims"]  # {"bull": ..., "bear": ..., "counter": ...}


def _write_legacy_run(root: Path) -> Path:
    run_dir = root / LEGACY_RUN_ID
    run_dir.mkdir(parents=True)
    write = lambda name, data: (run_dir / name).write_text(json.dumps(data), encoding="utf-8")  # noqa: E731
    write("metadata.json", LEGACY["metadata"])
    write("structured_agent_outputs.json", {"run_id": LEGACY_RUN_ID, "ticker": "AMD", "records": LEGACY["records"]})
    write("alpha_matches.json", {"run_id": LEGACY_RUN_ID, "ticker": "AMD", "matches": LEGACY["matches"]})
    write("structure_graph.json", {"activation": {**LEGACY["activation_header"], "alphas": LEGACY["activation_alphas"]}})
    write("conflicts.json", LEGACY["conflicts"])
    return run_dir


def _tree_hash(run_dir: Path) -> dict[str, str]:
    return {str(p.relative_to(run_dir)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(run_dir.rglob("*")) if p.is_file()}


@pytest.fixture()
def legacy_run(tmp_path):
    run_dir = _write_legacy_run(tmp_path)
    return run_dir, tmp_path


def _trace(root, run_id, claim_id):
    ctx = load_trace_context(run_id, root)
    assert ctx is not None
    return build_claim_trace(ctx, claim_id)


# ---------------------------------------------------------------------------
# LEGACY (real historical data): the historical use is kept, today's basis is "not linked"
# ---------------------------------------------------------------------------


def test_a_claim_of_the_historical_admitted_conflict_keeps_its_historical_use_exactly_as_saved(legacy_run):
    _run_dir, root = legacy_run
    saved_main = LEGACY["conflicts"]["main_conflict"]
    for side, claim_id in CLAIMS.items():
        entries = _trace(root, LEGACY_RUN_ID, claim_id)["conflict_adoption"]["entries"]
        # a claim can sit on more than one side / in more than one conflict of the saved run (claim 90 is both bear and
        # counter evidence of A301__A304): every saved placement is reported, none is chosen for the reader
        main = next(e for e in entries if e["conflict_id"] == "A301__A304" and e["side"] == side)
        assert main["is_main_conflict"] is True and main["is_representative"] is True
        # the conflict's OWN saved admission, level and score -- not re-evaluated, not re-worded
        assert (main["conflict_status"], main["conflict_level"], main["conflict_score"]) == (
            saved_main["admissibility"]["status"], saved_main["conflict_level"], saved_main["conflict_score"]) == ("admitted", "low", 14.2594)


def test_the_current_basis_of_a_legacy_claim_is_not_linked_with_a_neutral_reason_and_the_official_scoring_is_as_saved(legacy_run):
    _run_dir, root = legacy_run
    trace = _trace(root, LEGACY_RUN_ID, CLAIMS["bull"])
    support = trace["source_support"]
    assert (support["status_code"], support["reason_code"], support["reason"]) == ("NOT_LINKED", LEGACY_REASON_CODE, LEGACY_RUN_NOTE)
    assert trace["run_basis"] == {"link_fields_saved": False, "note": LEGACY_RUN_NOTE}
    assert trace["sources"] == []  # nothing is invented to fill the gap
    # the historical scoring is read from the run's own saved activation: the claim WAS in the official pool of that run
    assert trace["scoring"]["status_code"] in ("IN_OFFICIAL_POOL", "IN_POOL_ZERO_WEIGHT")
    assert trace["scoring"]["alpha_id"] == "A301"
    assert trace["conflict_adoption"]["note"] == HISTORICAL_USE_NOTE


def test_nothing_the_trace_says_about_a_legacy_claim_calls_the_historical_judgment_wrong_or_baseless(legacy_run):
    _run_dir, root = legacy_run
    for claim_id in CLAIMS.values():
        trace = _trace(root, LEGACY_RUN_ID, claim_id)
        visible = [trace["source_support"]["label"], trace["source_support"]["reason"], trace["run_basis"]["note"], trace["conflict_adoption"]["note"],
                   trace["note"], *(f"{e['conflict_status']} {e['conflict_level']}" for e in trace["conflict_adoption"]["entries"])]
        text = " ".join(str(v) for v in visible if v).replace(LEGACY_RUN_NOTE, "")  # the one sentence that NEGATES those words
        assert not re.search(r"(?i)\b(wrong|incorrect|erroneous|invalid|fabricat\w*|no basis|without basis|baseless|unsupported)\b", text), text


def test_building_a_trace_is_strictly_read_only_and_never_re_evaluates_the_saved_conflict(legacy_run):
    run_dir, root = legacy_run
    before = _tree_hash(run_dir)
    conflicts_before = copy.deepcopy(json.loads((run_dir / "conflicts.json").read_text(encoding="utf-8")))
    for claim_id in CLAIMS.values():
        _trace(root, LEGACY_RUN_ID, claim_id)
    get_evidence_trace_response(LEGACY_RUN_ID, root, claim_id=CLAIMS["bear"])
    assert _tree_hash(run_dir) == before  # no file created, changed or removed
    assert json.loads((run_dir / "conflicts.json").read_text(encoding="utf-8")) == conflicts_before


def test_the_api_envelope_carries_the_historical_use_and_the_legacy_basis(legacy_run):
    _run_dir, root = legacy_run
    response = get_evidence_trace_response(LEGACY_RUN_ID, root, claim_id=CLAIMS["counter"])
    assert response["status"] == "ok"
    item = response["item"]
    sides = {(e["conflict_id"], e["side"]) for e in item["conflict_adoption"]["entries"]}
    assert ("A301__A304", "counter") in sides and ("A301__A304", "bear") in sides  # both saved placements are shown
    assert item["run_basis"]["link_fields_saved"] is False
    json.dumps(response)  # serializable as served


def test_every_conflict_of_the_run_that_lists_a_claim_is_reported_once_with_its_own_saved_status():
    conflicts = {
        "main_conflict": {"conflict_id": "A__B", "admissibility": {"status": "admitted"}, "conflict_level": "high", "conflict_score": 61.5,
                          "evidence_ui": {"bull_evidence": [{"representative_claim_id": "c1", "member_claim_ids": ["c1", "c2"], "target_alpha_id": "A"}],
                                          "bear_evidence": [], "counter_evidence": []}},
        "conflicts": [{"conflict_id": "A__B", "admissibility": {"status": "admitted"}, "conflict_level": "high", "conflict_score": 61.5,
                       "evidence_ui": {"bull_evidence": [{"representative_claim_id": "c1", "member_claim_ids": ["c1", "c2"], "target_alpha_id": "A"}],
                                       "bear_evidence": [], "counter_evidence": []}},
                      {"conflict_id": "C__D", "admissibility": {"status": "admitted"}, "conflict_level": "low", "conflict_score": 9.0,
                       "evidence_ui": {"bull_evidence": [], "bear_evidence": [{"representative_claim_id": "c2", "member_claim_ids": ["c2"], "target_alpha_id": "D"}],
                                       "counter_evidence": []}}],
        "candidate_conflicts": [{"alpha_a": "E", "alpha_b": "F", "admissibility": {"status": "rejected"}, "conflict_level": None, "conflict_score": 0.0,
                                 "evidence_ui": {"bull_evidence": [{"representative_claim_id": "c1", "member_claim_ids": ["c1"], "target_alpha_id": "E"}],
                                                 "bear_evidence": [], "counter_evidence": []}}],
    }
    index = _conflict_adoption_index(conflicts)
    assert [(e["conflict_id"], e["side"], e["conflict_status"]) for e in index["c1"]] == [("A__B", "bull", "admitted"), ("E__F", "bull", "rejected")]
    assert [(e["conflict_id"], e["side"], e["is_representative"]) for e in index["c2"]] == [("A__B", "bull", False), ("C__D", "bear", True)]
    assert _conflict_adoption_index({}) == {} and _conflict_adoption_index(None) == {}


# ---------------------------------------------------------------------------
# POSITIVE FIXTURE (explicitly a fixture): a verified basis shown next to the historical use
# ---------------------------------------------------------------------------

FIXTURE_RUN_ID = "positive-fixture-run"
FIXTURE_CLAIM = "c904d4cc-dc09-495c-aec5-b056979948e1:fundamental_agent:fundamentals_report:claim:31"


def _write_positive_fixture_run(root: Path) -> Path:
    run_dir = root / FIXTURE_RUN_ID
    run_dir.mkdir(parents=True)

    def rebase(value):
        if isinstance(value, dict):
            return {k: (FIXTURE_RUN_ID if k == "run_id" else rebase(v)) for k, v in value.items()}
        if isinstance(value, list):
            return [rebase(v) for v in value]
        return value

    write = lambda name, data: (run_dir / name).write_text(json.dumps(data), encoding="utf-8")  # noqa: E731
    write("metadata.json", {"run_id": FIXTURE_RUN_ID, "ticker": "AMD", "analysis_date": AMD["metadata"]["analysis_date"]})
    write("structured_agent_outputs.json", {"run_id": FIXTURE_RUN_ID, "ticker": "AMD", "records": [rebase(r) for r in AMD["records"]]})
    write("alpha_matches.json", {"run_id": FIXTURE_RUN_ID, "ticker": "AMD", "matches": [rebase(m) for m in AMD["matches"]]})
    write("source_registry.json", {"schema_version": "source_registry.v2", "run_id": FIXTURE_RUN_ID, "ticker": "AMD", "source_count": len(AMD["sources"]),
                                   "sources": AMD["sources"]})
    # FIXTURE: a hand-written conflict that lists the real claim 31 as bull evidence (no such real admitted conflict exists)
    write("conflicts.json", {"main_conflict": None, "candidate_conflicts": [], "conflicts": [
        {"conflict_id": "FIXTURE_A301__FIXTURE_BEAR", "admissibility": {"status": "admitted"}, "conflict_level": "medium", "conflict_score": 33.3,
         "evidence_ui": {"bull_evidence": [{"representative_claim_id": FIXTURE_CLAIM, "member_claim_ids": [FIXTURE_CLAIM], "target_alpha_id": "A301"}],
                         "bear_evidence": [], "counter_evidence": []}}]})
    return run_dir


def test_positive_fixture_a_verified_basis_is_shown_next_to_the_historical_use_and_neither_changes_the_other(tmp_path):
    _write_positive_fixture_run(tmp_path)
    trace = _trace(tmp_path, FIXTURE_RUN_ID, FIXTURE_CLAIM)
    assert trace["run_basis"]["link_fields_saved"] is True and trace["run_basis"]["note"] is None
    assert trace["source_support"]["status_code"] == "VERIFIED_SUPPORT" and "reason_code" not in trace["source_support"]
    assert trace["sources"][0]["has_saved_content"] and trace["sources"][0]["role"] == "verified_basis"
    entry = trace["conflict_adoption"]["entries"][0]
    assert (entry["conflict_id"], entry["side"], entry["conflict_status"], entry["conflict_score"]) == ("FIXTURE_A301__FIXTURE_BEAR", "bull", "admitted", 33.3)
    assert trace["conflict_adoption"]["note"] == HISTORICAL_USE_NOTE


def test_a_claim_in_no_conflict_has_an_empty_adoption_block_and_no_note(tmp_path):
    _write_positive_fixture_run(tmp_path)
    other = next(r["claim_id"] for r in AMD["records"] if r["claim_id"] != FIXTURE_CLAIM)
    adoption = _trace(tmp_path, FIXTURE_RUN_ID, other)["conflict_adoption"]
    assert adoption == {"entries": [], "note": None}
