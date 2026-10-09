"""T2 (2026-10-07): frozen-input conflict recompute (comqutor_alpha.regression.frozen_input_conflict_recompute).

T2 made A102__A304 and A201__A304 evaluable. These tests pin what the UNCHANGED evidence-driven gate does with them on REAL saved inputs - the
repository's own saved historical runs under outputs/runs, read-only, exactly like tests/test_v0_1_3_offline_replay_proof.py - plus the module's error
reporting on hand-made (synthetic) directories. Zero Provider / model calls: the detector is a pure function of the saved files and the taxonomy.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from comqutor_alpha.regression import frozen_input_conflict_recompute as recompute

REPO = Path(__file__).resolve().parents[1]
RUNS_ROOT = REPO / "outputs" / "runs"
MSFT_RUN = "64568bfb-fe0c-453c-9872-831a8dc339a0"
TSM_RUN = "fc09821e-c7cf-40a7-bd76-c98172e16992"


def _tree_hash(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture(scope="module")
def msft():
    before = _tree_hash(RUNS_ROOT / MSFT_RUN)
    result = recompute.recompute_saved_run(ticker="MSFT", run_id=MSFT_RUN, runs_root=RUNS_ROOT)
    return result, before


@pytest.fixture(scope="module")
def tsm():
    return recompute.recompute_saved_run(ticker="TSM", run_id=TSM_RUN, runs_root=RUNS_ROOT)


def test_the_recompute_does_not_touch_the_saved_run_and_makes_no_provider_or_model_call(msft):
    result, before = msft
    assert result["status"] == "RECOMPUTED"
    assert result["provider_calls"] == 0 and result["model_calls"] == 0
    assert result["execution_type"] == "FROZEN_INPUT_RECOMPUTE"
    assert result["inputs"] == ["alpha_activations.json", "alpha_matches.json"]
    assert _tree_hash(RUNS_ROOT / MSFT_RUN) == before


def test_pairs_that_existed_before_the_taxonomy_change_are_reproduced_exactly(msft, tsm):
    for result in (msft[0], tsm):
        assert set(result["recomputed"]["admitted"]) - set(recompute.NEWLY_EVALUABLE_PAIRS) == set(result["saved"]["admitted"])
        assert result["recomputed"]["main_conflict"] == result["saved"]["main_conflict"]


def test_an_evaluable_pair_that_the_evidence_does_not_carry_stays_a_candidate_with_its_reasons(msft):
    """A102__A304 on MSFT: evaluable, evaluated, NOT admitted - below the score threshold, one supporting fact on the bull side, none ticker-specific."""
    result, _ = msft
    info = result["newly_evaluable_pairs"]["A102__A304"]
    assert info["saved_status"] == "not_reached"  # the saved run predates the pair
    assert info["recomputed_status"] == "candidate"
    assert info["recomputed"]["outcome"] == "suppressed"
    assert set(info["recomputed"]["reason_codes"]) == {
        "BULL_SCORE_BELOW_THRESHOLD",
        "INSUFFICIENT_BULL_SUPPORTING_EVIDENCE",
        "NO_BULL_TICKER_SPECIFIC_SUPPORT",
    }
    assert "A102__A304" not in result["recomputed"]["admitted"]


def test_an_evaluable_pair_that_the_evidence_carries_is_admitted_but_does_not_become_the_main_conflict(tsm):
    """A201__A304 on TSM: admitted by the unchanged gate (12 bull / 7 bear supporting facts, both scores above 50) - and the main conflict is still
    A101__A304. John: "允许评估不等于自动成立，更不等于必须成为主冲突" - evaluable is not admitted by itself; admitted is not main by itself."""
    info = tsm["newly_evaluable_pairs"]["A201__A304"]
    assert info["recomputed_status"] == "admitted"
    assert info["recomputed"]["reason_codes"] == []
    assert info["recomputed"]["bull_score"] >= 50 and info["recomputed"]["bear_score"] >= 50
    assert tsm["changed"]["admitted_added"] == ["A201__A304"]
    assert tsm["changed"]["main_conflict_changed"] is False
    assert tsm["recomputed"]["main_conflict"] == "A101__A304"


# ---------------------------------------------------------------------------------------------------------------------------------------
# hand-made (synthetic) directories: error reporting and rendering
# ---------------------------------------------------------------------------------------------------------------------------------------


def test_a_run_without_its_saved_inputs_is_reported_with_the_missing_file_names(tmp_path):
    (tmp_path / "runs" / "r1").mkdir(parents=True)
    result = recompute.recompute_saved_run(ticker="AMD", run_id="r1", runs_root=tmp_path / "runs")
    assert result["status"] == "SAVED_INPUTS_NOT_FOUND"
    assert result["missing"] == ["alpha_activations.json", "alpha_matches.json", "conflicts.json"]


def test_a_taxonomy_that_cannot_be_loaded_is_a_reported_error_not_a_result(tmp_path):
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / "alpha_activations.json").write_text(json.dumps({"activation": {"alphas": []}}), encoding="utf-8")
    (run_dir / "alpha_matches.json").write_text(json.dumps({"matches": []}), encoding="utf-8")
    (run_dir / "conflicts.json").write_text(json.dumps({"conflicts": []}), encoding="utf-8")
    bad_taxonomy = tmp_path / "taxonomy.yaml"
    bad_taxonomy.write_text("alphas: not-a-list\n", encoding="utf-8")
    result = recompute.recompute_saved_run(ticker="AMD", run_id="r1", runs_root=tmp_path / "runs", taxonomy_path=bad_taxonomy)
    assert result["status"] == "RECOMPUTE_ERROR"
    assert "ValueError" in result["error"]


def test_the_table_is_rendered_from_the_document_alone_and_outputs_are_never_overwritten(tmp_path, msft):
    document = {
        "schema_version": recompute.SCHEMA_VERSION,
        "execution_id": "unit-test",
        "execution_type": recompute.EXECUTION_TYPE,
        "generated_at": "2026-10-07T00:00:00Z",
        "provider_calls": 0,
        "model_calls": 0,
        "note": "n",
        "tickers": {"MSFT": msft[0], "AMD": {"ticker": "AMD", "run_id": "deadbeef0000", "status": "SAVED_INPUTS_NOT_FOUND", "missing": ["conflicts.json"]}},
    }
    markdown = recompute.render_markdown(document)
    assert "Frozen-input conflict recompute — unit-test" in markdown
    assert "SAVED_INPUTS_NOT_FOUND" in markdown and "A102__A304" in markdown
    out = tmp_path / "out"
    paths = recompute.write_outputs(document, out)
    assert paths["table"].read_text(encoding="utf-8") == markdown
    with pytest.raises(FileExistsError):
        recompute.write_outputs(document, out)
