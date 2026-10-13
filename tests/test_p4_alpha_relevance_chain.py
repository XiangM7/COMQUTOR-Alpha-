"""P4 phase 1 (2026-10-12): the simulated relevance chain on a COPY of the saved NVDA Fresh Run #2 -- save, read back, API, Export.

A v2 consumption execution is derived from the copy (in-memory SQLite), judged by the experiment entry with the SIMULATED gateway (TEST
DATA), and then read back through the production trace route and the Export bundle. The saved run itself is only read. No model,
search or network call exists in these paths.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections import Counter
from pathlib import Path

import pytest

from comqutor_alpha import alpha_relevance_experiment as ex, consumption_recompute as cr
from comqutor_alpha.api.evidence_trace import get_evidence_trace_response
from comqutor_alpha.api.routes_research import _run_week3_graph_pipeline, get_run_export_bundle
from comqutor_alpha.graph_engine.alpha_relevance_judgment import LEDGER_DIRNAME, RESULTS_FILENAME
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from comqutor_alpha.structure_engine import alpha_relevance_llm as rl
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

RUN_ID = "12591384-0b26-470d-a99d-a49c00be440b"
REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_RUN = REPO_ROOT / "outputs" / "t4_runs" / RUN_ID
CLAIM_5 = f"{RUN_ID}:aggressive_risk_analyst:risk_debate_state.aggressive_history:claim:5"
SCORING_ARTIFACTS = ("alpha_matches.json", "structure_graph.json", "alpha_activations.json", "conflicts.json", "evidence_facts.json",
                     "evidence_stance_audit.json")
needs_saved_run = pytest.mark.skipif(not (SOURCE_RUN / "alpha_matches.json").is_file(), reason="the saved NVDA Fresh Run #2 is not present (local run data)")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _repo() -> GraphPersistenceRepository:
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


@pytest.fixture
def v2_execution(tmp_path):
    before = {p.name: _sha(p) for p in SOURCE_RUN.iterdir() if p.is_file()}
    root = tmp_path / "verification"
    assert cr.copy_saved_run(SOURCE_RUN, root)["status"] == "ok"
    repo = _repo()
    derived = cr.derive_consumption_execution(RUN_ID, contract="v2", output_root=root, graph_repository=repo)
    assert derived["status"] == "ok", derived
    yield root, derived["execution_id"], repo
    assert {p.name: _sha(p) for p in SOURCE_RUN.iterdir() if p.is_file()} == before, "the saved run itself must never change"


@needs_saved_run
def test_the_simulated_chain_reads_back_the_same_judgment_in_the_api_and_the_export(v2_execution):
    root, execution, repo = v2_execution
    exec_dir = root / execution
    scoring_before = {name: _sha(exec_dir / name) for name in SCORING_ARTIFACTS}
    result = ex.judge_run_relevance(execution, output_root=root, config=ex.P4_RELEVANCE_SIMULATED_20261012)
    assert result["status"] == "ok" and result["test_data"] is True and result["provider_calls"] >= 1
    # consumption and scoring are untouched: the label is not consumed by anything
    assert {name: _sha(exec_dir / name) for name in SCORING_ARTIFACTS} == scoring_before
    # the v2 stance policy still corroborates through the bound SOURCE ledger -- the relevance ledger is never mistaken for it
    consumption = get_evidence_trace_response(execution, root, claim_id=CLAIM_5)["item"]["consumption"]
    assert consumption["state"] == "CURRENT" and consumption["execution_basis"]["stance_ledger"]["binding"] == "SOURCE_RUN_DECLARED"
    assert not (exec_dir / "llm_semantic_calls.jsonl").exists() and (exec_dir / LEDGER_DIRNAME / "llm_semantic_calls.jsonl").is_file()
    # save -> read back: the saved records are exactly what the read side reproduces from the relevance ledger
    payload = _load(exec_dir / RESULTS_FILENAME)
    assert dict(Counter(r["state"] for r in payload["records"])) == result["verification"]["states"]
    assert set(result["verification"]["states"]) <= set(rl.STATES) and result["verification"]["ledger"]["integrity"] == "MATCHES_MANIFEST"
    # the exported trace and the API agree on every exported claim that has a judgment (one of each state at least)
    exported = _load(exec_dir / "evidence_trace.json")
    assert exported["relevance_judgments"]["states"] == result["verification"]["states"]
    per_state: dict[str, list[str]] = {}
    for claim_id, item in exported["items"].items():
        if "relevance_judgment" in item:
            per_state.setdefault(item["relevance_judgment"]["state"], []).append(claim_id)
    checked = [ids[0] for ids in per_state.values()] + [ids[-1] for ids in per_state.values()]
    for claim_id in checked:
        api = get_evidence_trace_response(execution, root, claim_id=claim_id)["item"]["relevance_judgment"]
        assert api == exported["items"][claim_id]["relevance_judgment"], claim_id
        assert (api["tier"] is not None) == (api["state"] == rl.STATE_JUDGED) and api["model_weight"] is None
        assert api["test_data"] is True and "SIMULATED TEST DATA" in api["label"]
        assert api["source"]["execution_run_id"] == execution and api["source"]["owner_run_id"] == execution and api["source"]["based_on_run_id"] == RUN_ID
    # the Export carries the versioned record (its relevance ledger stays local, like the run's main ledger)
    status, _ctype, raw, _name, error = get_run_export_bundle(execution, output_root=str(root))
    assert status == 200, error
    names = set(zipfile.ZipFile(io.BytesIO(raw)).namelist())
    assert RESULTS_FILENAME in names and not any(n.startswith(LEDGER_DIRNAME) for n in names)
    assert json.loads(zipfile.ZipFile(io.BytesIO(raw)).read(RESULTS_FILENAME)) == payload
    # a later Week 3 pass keeps the judgment valid (same claims, same definitions) and still exports it
    _run_week3_graph_pipeline(exec_dir, graph_repository=repo, require_verified_evidence_gate=True)
    again = get_evidence_trace_response(execution, root, claim_id=checked[0])["item"]["relevance_judgment"]
    assert again == exported["items"][checked[0]]["relevance_judgment"]


@needs_saved_run
def test_runs_without_results_show_unjudged_and_the_default_path_sends_nothing(v2_execution, monkeypatch):
    root, execution, repo = v2_execution
    # the saved source copy and the v2 execution carry no relevance results: every matched claim is UNJUDGED (never "none")
    for run in (RUN_ID, execution):
        view = get_evidence_trace_response(run, root, claim_id=CLAIM_5)["item"]["relevance_judgment"]
        assert (view["state"], view["tier"], view["reason"], view["test_data"]) == (rl.STATE_UNJUDGED, None, "no_relevance_results_for_run", False)
    calls: list[str] = []

    def boom(*_args, **_kwargs):
        calls.append("gateway")
        raise AssertionError("the default path must not call the gateway")

    for method in ("invoke_json", "invoke_json_with_trace", "invoke_prebuilt_json_prompt"):
        monkeypatch.setattr(Week2LLMGateway, method, boom)
    _run_week3_graph_pipeline(root / execution, graph_repository=repo, require_verified_evidence_gate=True)
    assert calls == [] and _load(root / execution / "week3_pipeline_status.json")["outcome"] == "success"
    assert ex.judge_run_relevance(execution, output_root=root)["status"] == "disabled" and calls == []
    assert not (root / execution / RESULTS_FILENAME).exists() and not (root / execution / LEDGER_DIRNAME).exists()
