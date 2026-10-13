"""alpha_evidence_consumption.v2 on SAVED runs (T1 integration, 2026-10-11): ledger binding and the operator entry.

A derived execution recomputes a saved run's inputs; it does not copy the source run's model-call ledger, so its stances can only be
corroborated against the ledger of the run that produced them -- through an explicit, hash-pinned binding. These tests prove:
  * the binding rules (own ledger first; declared binding must be in the execution's lineage, hash-pinned; anything else is unusable);
  * the operator entry recomputes a COPY of the saved NVDA Fresh Run #2 under v2 with the source ledger bound (not copied), gets the same
    87 positive-pool exclusions as the run with its own ledger, keeps source / execution / ledger identities apart in the run response and
    the trace, and never touches the source files;
  * rollback restores exactly the legacy payload; a tampered source ledger is refused (no exclusion); the contract must be chosen.
Everything runs on copies in ``tmp_path`` with an in-memory SQLite database; no model, search or network call exists in these paths.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from comqutor_alpha import consumption_recompute as cr
from comqutor_alpha.api.evidence_trace import get_evidence_trace_response
from comqutor_alpha.api.routes_research import (
    _run_week3_graph_pipeline,
    build_research_response,
    get_run_export_bundle,
)
from comqutor_alpha.classification_recovery import rebase_run_id
from comqutor_alpha.graph_engine.evidence_consumption import (
    CONSUMPTION_CONTRACT_V2,
    CONSUMPTION_METADATA_KEY,
    LEDGER_BINDING_METADATA_KEY,
    LEDGER_BINDING_OWN_RUN,
    LEDGER_BINDING_SOURCE_DECLARED,
    LEDGER_FILENAME,
    resolve_stance_ledger,
)
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository

RUN_ID = "12591384-0b26-470d-a99d-a49c00be440b"
REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_RUN = REPO_ROOT / "outputs" / "t4_runs" / RUN_ID
CLAIM_5 = f"{RUN_ID}:aggressive_risk_analyst:risk_debate_state.aggressive_history:claim:5"
needs_saved_run = pytest.mark.skipif(not (SOURCE_RUN / "alpha_matches.json").is_file(), reason="the saved NVDA Fresh Run #2 is not present (local run data)")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repo() -> GraphPersistenceRepository:
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------------- binding rules (synthetic, fast)
def _write_ledger(run_dir: Path, claim_id: str = "c1", alpha_id: str = "A301", stance: str = "opposes_alpha", manifest: bool = True) -> str:
    run_dir.mkdir(parents=True, exist_ok=True)
    line = {"task": "evidence_stance_classifier", "provider_status": "success", "validation_status": "accepted",
            "validated_output": {"items": [{"claim_id": claim_id, "target_alpha_id": alpha_id, "stance": stance}]}}
    (run_dir / LEDGER_FILENAME).write_text(json.dumps(line) + "\n", encoding="utf-8")
    sha = _sha(run_dir / LEDGER_FILENAME)
    if manifest:
        (run_dir / "llm_semantic_manifest.json").write_text(json.dumps({"calls_file_sha256": sha}), encoding="utf-8")
    return sha


def test_own_ledger_wins_and_names_its_owner(tmp_path):
    _write_ledger(tmp_path / "run-a")
    ledger = resolve_stance_ledger(tmp_path / "run-a", {LEDGER_BINDING_METADATA_KEY: {"source_run_id": "x", "calls_file_sha256": "0" * 64}})
    assert ledger is not None and ledger.binding == LEDGER_BINDING_OWN_RUN and ledger.owner_run_id == "run-a" and ledger.usable


def test_no_own_ledger_and_no_binding_means_no_ledger(tmp_path):
    (tmp_path / "exec-1").mkdir()
    assert resolve_stance_ledger(tmp_path / "exec-1", {"based_on_run_id": "run-a"}) is None


def test_declared_binding_to_the_source_run_is_used_when_the_hash_matches(tmp_path):
    sha = _write_ledger(tmp_path / "run-a")
    (tmp_path / "exec-1").mkdir()
    ledger = resolve_stance_ledger(tmp_path / "exec-1", {"based_on_run_id": "run-a", LEDGER_BINDING_METADATA_KEY: {"source_run_id": "run-a", "calls_file_sha256": sha}})
    assert ledger is not None
    assert ledger.binding == LEDGER_BINDING_SOURCE_DECLARED and ledger.owner_run_id == "run-a" and ledger.integrity == "MATCHES_MANIFEST" and ledger.usable
    assert ("c1", "A301") in ledger.pairs


@pytest.mark.parametrize(("metadata_of", "integrity"), [
    (lambda sha: {"based_on_run_id": "run-a", LEDGER_BINDING_METADATA_KEY: {"source_run_id": "run-a", "calls_file_sha256": "f" * 64}}, "BINDING_SHA_MISMATCH"),
    (lambda sha: {"based_on_run_id": "run-a", LEDGER_BINDING_METADATA_KEY: {"source_run_id": "run-b", "calls_file_sha256": sha}}, "BINDING_NOT_IN_LINEAGE"),
    (lambda sha: {"based_on_run_id": "run-z", "root_research_run_id": "run-z", LEDGER_BINDING_METADATA_KEY: {"source_run_id": "run-z", "calls_file_sha256": sha}}, "BOUND_LEDGER_MISSING"),
    (lambda sha: {"based_on_run_id": "run-a", LEDGER_BINDING_METADATA_KEY: {"source_run_id": "run-a"}}, "BINDING_INVALID"),
    (lambda sha: {"based_on_run_id": "../run-a", LEDGER_BINDING_METADATA_KEY: {"source_run_id": "../run-a", "calls_file_sha256": sha}}, "BINDING_INVALID"),
])
def test_a_binding_that_cannot_be_honoured_is_unusable_never_a_silent_fallback(tmp_path, metadata_of, integrity):
    sha = _write_ledger(tmp_path / "run-a")
    (tmp_path / "exec-1").mkdir()
    ledger = resolve_stance_ledger(tmp_path / "exec-1", metadata_of(sha))
    assert ledger is not None and ledger.integrity == integrity and not ledger.usable and ledger.binding == LEDGER_BINDING_SOURCE_DECLARED


def test_the_operator_entry_refuses_the_real_outputs_tree_and_a_missing_contract_choice(tmp_path):
    with pytest.raises(ValueError, match="REFUSED_REAL_OUTPUTS"):
        cr.refuse_real_outputs(REPO_ROOT / "outputs" / "t4_runs")
    result = cr.derive_consumption_execution(RUN_ID, contract=None, output_root=tmp_path)
    assert result["status"] == "failed" and result["error_code"] == "CONSUMPTION_CONTRACT_NOT_CHOSEN"
    assert cr.derive_consumption_execution(RUN_ID, contract="v3", output_root=tmp_path)["error_code"] == "CONSUMPTION_CONTRACT_NOT_CHOSEN"
    assert list(tmp_path.iterdir()) == []


def test_only_an_explicitly_named_isolated_test_database_is_accepted(monkeypatch):
    monkeypatch.delenv("COMQUTOR_DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="REFUSED_NO_DATABASE"):
        cr.require_isolated_test_database()
    monkeypatch.setenv("COMQUTOR_DATABASE_URL", "postgresql+psycopg://u@127.0.0.1:5433/comqutor_alpha")
    monkeypatch.setenv("COMQUTOR_REQUIRE_DATABASE_NAME", "comqutor_alpha")
    with pytest.raises(ValueError, match="REFUSED_DATABASE"):
        cr.require_isolated_test_database()
    monkeypatch.setenv("COMQUTOR_DATABASE_URL", "postgresql+psycopg://u@127.0.0.1:5433/scratch_test")
    monkeypatch.setenv("COMQUTOR_REQUIRE_DATABASE_NAME", "scratch_test")
    assert cr.require_isolated_test_database() == "scratch_test"


# --------------------------------------------------------------------------------------------- operator entry on a copy of a real saved run
@pytest.fixture
def saved_copy(tmp_path):
    before = {p.name: _sha(p) for p in SOURCE_RUN.iterdir() if p.is_file()}
    result = cr.copy_saved_run(SOURCE_RUN, tmp_path / "verification")
    assert result["status"] == "ok", result
    yield tmp_path / "verification"
    assert {p.name: _sha(p) for p in SOURCE_RUN.iterdir() if p.is_file()} == before, "the saved run itself must never change"


@needs_saved_run
def test_v2_recompute_binds_the_source_ledger_and_keeps_the_identities_apart(saved_copy):
    repo = _repo()
    source_ledger_sha = _sha(saved_copy / RUN_ID / LEDGER_FILENAME)
    source_hashes = {p.name: _sha(p) for p in (saved_copy / RUN_ID).iterdir() if p.is_file()}
    result = cr.derive_consumption_execution(RUN_ID, contract="v2", output_root=saved_copy, graph_repository=repo)
    assert result["status"] == "ok", result
    execution = result["execution_id"]
    exec_dir = saved_copy / execution
    metadata = _load(exec_dir / "metadata.json")
    assert metadata["execution_type"] == cr.CONSUMPTION_EXECUTION_TYPE and metadata["based_on_run_id"] == RUN_ID and metadata["run_id"] == execution
    assert metadata[CONSUMPTION_METADATA_KEY] == CONSUMPTION_CONTRACT_V2
    assert metadata[LEDGER_BINDING_METADATA_KEY] == {"source_run_id": RUN_ID, "calls_file_sha256": source_ledger_sha}
    assert not (exec_dir / LEDGER_FILENAME).exists(), "the source run's own call ledger must not be copied into the execution"
    summary = _load(exec_dir / "structure_graph.json")["evidence_consumption"]
    assert summary["ledger"]["binding"] == LEDGER_BINDING_SOURCE_DECLARED and summary["ledger"]["owner_run_id"] == RUN_ID
    assert summary["ledger"]["integrity"] == "MATCHES_MANIFEST" and summary["ledger"]["sha256"] == source_ledger_sha
    assert summary["positive_admission"]["excluded"] == 87, "the same exclusions as the run evaluated with its own ledger"
    lineage = _load(exec_dir / cr.CONSUMPTION_LINEAGE_FILENAME)
    assert lineage["fresh_run"] is False and lineage["model_calls"] == 0 and lineage["stance_ledger_binding"]["calls_file_sha256"] == source_ledger_sha
    # the run response reports the three identities separately
    response = build_research_response(execution, output_root=str(saved_copy), graph_repository=repo)
    assert response["lineage"]["based_on_run_id"] == RUN_ID and response["lineage"]["execution_run_id"] == execution
    assert response["lineage"]["recomputation_of_saved_inputs"] is True and response["lineage"]["fresh_run"] is False
    assert response["lineage"]["stance_ledger_binding"]["source_run_id"] == RUN_ID
    # the trace states the execution basis and whose ledger corroborated the stance
    trace = get_evidence_trace_response(execution, saved_copy, claim_id=CLAIM_5)
    basis = trace["item"]["consumption"]["execution_basis"]
    assert basis["execution_run_id"] == execution and basis["based_on_run_id"] == RUN_ID and basis["recomputation_of_saved_inputs"] is True
    assert "not a Fresh Run" in basis["label"]
    assert basis["stance_ledger"]["binding"] == LEDGER_BINDING_SOURCE_DECLARED and basis["stance_ledger"]["owner_run_id"] == RUN_ID
    assert trace["item"]["consumption"]["stance"]["state"] == "MODEL_JUDGED"
    explanation = trace["item"]["consumption"]["stance"]["explanation"]
    assert f"saved source run {RUN_ID}" in explanation and "run's own" not in explanation, "the stance must name whose ledger confirmed it"
    # a claim matched to no Alpha carries only the name decision -- stated in the same words as for a matched claim
    unmatched = get_evidence_trace_response(execution, saved_copy, claim_id=f"{RUN_ID}:portfolio_manager:final_trade_decision:claim:8")["item"]["consumption"]
    assert unmatched["scope"].startswith("attribution_only") and unmatched["attribution"]["ticker_specific"] is True
    assert unmatched["attribution"]["explanation"].startswith("The target company's name is present in the claim text")
    # the research page's key-conclusions view states the same execution basis at run level, before any claim is opened
    key = get_evidence_trace_response(execution, saved_copy, scope="key")["key_conclusions"]
    assert key["execution_basis"] == basis
    # an original run outside the contract keeps its key-conclusions view unchanged (no execution basis)
    assert "execution_basis" not in get_evidence_trace_response(RUN_ID, saved_copy, scope="key")["key_conclusions"]
    # the verification copy of the source run was only read
    assert {p.name: _sha(p) for p in (saved_copy / RUN_ID).iterdir() if p.is_file()} == source_hashes


@needs_saved_run
def test_rollback_restores_exactly_the_legacy_payload(saved_copy):
    repo = _repo()
    v2 = cr.derive_consumption_execution(RUN_ID, contract="v2", output_root=saved_copy, graph_repository=repo)
    assert v2["status"] == "ok", v2
    rolled = cr.rollback_consumption_execution(v2["execution_id"], output_root=saved_copy, graph_repository=repo)
    assert rolled["status"] == "ok", rolled
    exec_dir = saved_copy / v2["execution_id"]
    record = _load(exec_dir / cr.CONSUMPTION_ROLLBACK_FILENAME)
    assert record["rolled_back"] is True and record["previous_contract"] == CONSUMPTION_CONTRACT_V2
    assert CONSUMPTION_METADATA_KEY not in _load(exec_dir / "metadata.json")
    assert "evidence_consumption" not in _load(exec_dir / "structure_graph.json")
    expected = rebase_run_id(_load(saved_copy / RUN_ID / "alpha_matches.json"), base_run_id=RUN_ID, execution_id=v2["execution_id"])
    assert _load(exec_dir / "alpha_matches.json") == expected, "after rollback the payload is the saved legacy payload (only run_id rebased)"
    # the Export of the rolled-back execution carries the rollback record next to the lineage file, and its stance audit is legacy again
    status, _ctype, raw, _name, error = get_run_export_bundle(v2["execution_id"], output_root=str(saved_copy))
    assert status == 200, error
    exported = zipfile.ZipFile(io.BytesIO(raw))
    assert {cr.CONSUMPTION_ROLLBACK_FILENAME, cr.CONSUMPTION_LINEAGE_FILENAME} <= set(exported.namelist())
    assert json.loads(exported.read(cr.CONSUMPTION_ROLLBACK_FILENAME))["rolled_back"] is True
    assert json.loads(exported.read("evidence_stance_audit.json"))["effect_mode"] == "shadow"
    assert cr.rollback_consumption_execution(v2["execution_id"], output_root=saved_copy, graph_repository=repo)["error_code"] == "NOTHING_TO_ROLL_BACK"


@needs_saved_run
def test_a_tampered_source_ledger_is_refused_and_nothing_is_excluded(saved_copy):
    repo = _repo()
    v2 = cr.derive_consumption_execution(RUN_ID, contract="v2", output_root=saved_copy, graph_repository=repo)
    assert v2["status"] == "ok", v2
    with (saved_copy / RUN_ID / LEDGER_FILENAME).open("a", encoding="utf-8") as handle:
        handle.write("\n")
    exec_dir = saved_copy / v2["execution_id"]
    _run_week3_graph_pipeline(exec_dir, graph_repository=repo, require_verified_evidence_gate=True)
    summary = _load(exec_dir / "structure_graph.json")["evidence_consumption"]
    assert summary["ledger"]["integrity"] == "BINDING_SHA_MISMATCH" and summary["ledger"]["usable"] is False
    assert summary["positive_admission"]["excluded"] == 0


@needs_saved_run
def test_legacy_choice_declares_no_contract(saved_copy):
    repo = _repo()
    legacy = cr.derive_consumption_execution(RUN_ID, contract="legacy", output_root=saved_copy, graph_repository=repo)
    assert legacy["status"] == "ok", legacy
    metadata = _load(saved_copy / legacy["execution_id"] / "metadata.json")
    assert CONSUMPTION_METADATA_KEY not in metadata and LEDGER_BINDING_METADATA_KEY not in metadata
    assert "evidence_consumption" not in _load(saved_copy / legacy["execution_id"] / "structure_graph.json")
    # still a recomputation of saved inputs, labelled with the rules it actually ran under -- never as the evidence contract
    basis = get_evidence_trace_response(legacy["execution_id"], saved_copy, scope="key")["key_conclusions"]["execution_basis"]
    assert basis["recomputation_of_saved_inputs"] is True and basis["based_on_run_id"] == RUN_ID
    assert "not a Fresh Run" in basis["label"] and "legacy rules" in basis["label"] and "under the evidence contract" not in basis["label"]
