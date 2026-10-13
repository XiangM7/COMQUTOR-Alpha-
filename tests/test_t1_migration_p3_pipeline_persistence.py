"""alpha_evidence_consumption.v2 through the PRODUCTION Week 3 pipeline, persistence, trace and export (round 36).

Every test works on a COPY of a real saved run (NVDA Fresh Run #2, 951 claims) made in ``tmp_path``: the pipeline, the file store and
the repository write only there. The original run is never opened for writing -- the fixture refuses any copy that is not
outside the repository's ``outputs`` tree, and the saved files are re-hashed after the copy. The tests skip when the saved run is
not present (a fresh clone): nothing here needs a model, a network call, or a Provider.

Proven here
  * legacy (no metadata key): the pipeline's result equals the saved result and ``alpha_matches.json`` is not rewritten;
  * v2: blocks and summary are persisted, the payload without the blocks equals the original, official A301 is unchanged;
  * rollback by removing the metadata key restores the original bytes of ``alpha_matches.json``;
  * an unknown contract version produces NO result and its own failure stage;
  * a re-evaluation (changed verification, changed model judgment) is recomputed, never reused;
  * the trace shows the block with the shared reason code; the export reports the applied effect only for v2;
  * the new JSON fields survive the production persistence path (file store and repository) unchanged.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from comqutor_alpha.api.artifact_export import build_evidence_stance_audit
from comqutor_alpha.api.evidence_trace import get_evidence_trace_response
from comqutor_alpha.api.routes_research import _run_week3_graph_pipeline
from comqutor_alpha.graph_engine.evidence_consumption import (
    CONSUMPTION_BLOCK_KEY,
    CONSUMPTION_CONTRACT_V2,
    CONSUMPTION_METADATA_KEY,
    PAYLOAD_CONTRACT_KEY,
    block_for_match,
    strip_alpha_evidence_consumption,
)
from comqutor_alpha.graph_engine.evidence_fact_index import select_supporting_alpha_claims
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository

RUN_ID = "12591384-0b26-470d-a99d-a49c00be440b"
REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_RUN = REPO_ROOT / "outputs" / "t4_runs" / RUN_ID
INPUT_FILES = (
    "metadata.json", "alpha_matches.json", "extracted_structures.json", "structured_agent_outputs.json", "source_registry.json",
    "raw_agent_outputs.json", "llm_semantic_calls.jsonl", "llm_semantic_manifest.json", "structure_graph.json", "derived_inputs.json",
)
CLAIM_5 = f"{RUN_ID}:aggressive_risk_analyst:risk_debate_state.aggressive_history:claim:5"  # in A301's official pool, model stance supports_alpha

pytestmark = pytest.mark.skipif(not (SOURCE_RUN / "alpha_matches.json").is_file(), reason="the saved NVDA Fresh Run #2 is not present (local run data)")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repo() -> GraphPersistenceRepository:
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


@pytest.fixture
def source_hashes():
    return {name: _sha(SOURCE_RUN / name) for name in INPUT_FILES}


@pytest.fixture
def run_copy(tmp_path, source_hashes):
    assert REPO_ROOT / "outputs" not in tmp_path.resolve().parents, "the working copy must live outside the repository's outputs tree"
    run_dir = tmp_path / RUN_ID
    run_dir.mkdir()
    for name in INPUT_FILES:
        shutil.copy2(SOURCE_RUN / name, run_dir / name)
    yield run_dir
    # the original files are exactly what they were before the test
    assert {name: _sha(SOURCE_RUN / name) for name in INPUT_FILES} == source_hashes


def _load(run_dir: Path, name: str):
    return json.loads((run_dir / name).read_text(encoding="utf-8"))


def _set_metadata(run_dir: Path, **changes):
    metadata = _load(run_dir, "metadata.json")
    for key, value in changes.items():
        if value is None:
            metadata.pop(key, None)
        else:
            metadata[key] = value
    (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _run(run_dir: Path, repo=None):
    repo = repo or _repo()
    _run_week3_graph_pipeline(run_dir, graph_repository=repo, require_verified_evidence_gate=True)
    return repo


def _stance_exclusions_by_alpha(run_dir: Path) -> dict[str, int]:
    """The run audit's evidence-eligibility section is built through the same shared selector Activation uses."""
    reasons = _load(run_dir, "run_audit.json")["evidence_eligibility"]["exclusion_reasons_by_alpha"]
    return {alpha: r["STANCE_MODEL_NOT_SUPPORTING"] for alpha, r in reasons.items() if r.get("STANCE_MODEL_NOT_SUPPORTING")}


def _alpha(graph: dict, alpha_id: str, view: str = "official") -> dict:
    block = graph["activation"] if view == "official" else graph["activation_versions"][view]
    return next(a for a in block["alphas"] if a["alpha_id"] == alpha_id)


# ---------------------------------------------------------------------------
# Legacy: nothing changes
# ---------------------------------------------------------------------------


def test_a_legacy_run_through_the_pipeline_reproduces_the_saved_result_and_does_not_rewrite_alpha_matches(run_copy):
    saved_graph = _load(run_copy, "structure_graph.json")
    original_bytes = (run_copy / "alpha_matches.json").read_bytes()
    assert CONSUMPTION_METADATA_KEY not in _load(run_copy, "metadata.json")
    _run(run_copy)
    assert (run_copy / "alpha_matches.json").read_bytes() == original_bytes
    graph = _load(run_copy, "structure_graph.json")
    assert "evidence_consumption" not in graph
    assert graph == saved_graph  # the production pipeline, run again on the saved inputs, gives the saved structure graph
    assert _stance_exclusions_by_alpha(run_copy) == {}  # the new reason code never appears for a legacy run
    assert _load(run_copy, "week3_pipeline_status.json")["outcome"] == "success"


# ---------------------------------------------------------------------------
# v2: blocks persisted, additive, official result unchanged
# ---------------------------------------------------------------------------


def _without_lineage_unresolved(alphas: list) -> list:
    alphas = json.loads(json.dumps(alphas))
    for alpha in alphas:
        lss = alpha["components"]["local_structure_support"]
        lss["local_edge_exclusion_reasons"] = [r for r in lss["local_edge_exclusion_reasons"] if r != "LINEAGE_UNRESOLVED"]
    return alphas


def test_v2_persists_blocks_and_a_summary_leaves_the_official_scores_unchanged_and_is_additive(run_copy):
    original = _load(run_copy, "alpha_matches.json")
    saved_graph = _load(run_copy, "structure_graph.json")
    _set_metadata(run_copy, **{CONSUMPTION_METADATA_KEY: CONSUMPTION_CONTRACT_V2})
    _run(run_copy)

    payload = _load(run_copy, "alpha_matches.json")
    graph = _load(run_copy, "structure_graph.json")
    assert payload[PAYLOAD_CONTRACT_KEY] == CONSUMPTION_CONTRACT_V2
    assert sum(1 for m in payload["matches"] if block_for_match(m)) == 164  # one block per committed match
    assert sum(1 for m in payload["matches"] if m["match_status"] != "matched" and CONSUMPTION_BLOCK_KEY in m) == 787  # attribution-only blocks
    assert strip_alpha_evidence_consumption(payload) is True and payload == original  # additive: nothing else was rewritten

    summary = graph["evidence_consumption"]
    assert summary["contract"] == CONSUMPTION_CONTRACT_V2 and summary["matched_pairs"] == 164
    assert summary["stance"]["model_judged"] == 163 and summary["stance"]["unjudged_by_reason"] == {"missing_result": 1}
    assert summary["positive_admission"]["excluded"] == 87 and summary["positive_admission"]["admitted"] == 77
    assert summary["positive_admission"]["excluded_by_label"] == {"mentions_alpha": 20, "opposes_alpha": 63, "supports_counter_alpha": 4}
    assert summary["relevance"]["by_authority"] == {"LEXICAL_RULE_FALLBACK": 164} and summary["relevance"]["model_weights"] == 0
    assert summary["attribution"]["subject_determined"] is False and summary["attribution"]["target_by_source_object"] == "DISABLED"

    # the OFFICIAL result is unchanged (its three claims are model-judged supports); the unverified diagnostic view changes
    assert _alpha(graph, "A301")["activation_score"] == _alpha(saved_graph, "A301")["activation_score"] == 22.0056
    # 2026-10-13 (owner brief, T3 defect 4): canonical_edge_scope.v1 withholds the three "no-cut" relations of
    # rate_cut_cycle -> valuation_risk. One of them (canrel_9a5d30d57e97aed8) was the only relation in the graph whose lineage never
    # resolved, so LINEAGE_UNRESOLVED leaves every Alpha's local-edge exclusion reasons; nothing else in the official result moves.
    withheld = {w["relation_id"] for w in summary["canonical_edge_scope"]["withheld"]}
    assert "canrel_9a5d30d57e97aed8" in withheld and summary["canonical_edge_scope"]["withheld_relation_count"] == 3
    assert all("LINEAGE_UNRESOLVED" in a["components"]["local_structure_support"]["local_edge_exclusion_reasons"]
               for a in saved_graph["activation"]["alphas"])
    assert graph["activation"]["alphas"] == _without_lineage_unresolved(saved_graph["activation"]["alphas"])
    assert graph["entity_alpha_exposures"] == saved_graph["entity_alpha_exposures"]  # Exposure follows the official facts: unchanged
    assert graph["dominant_alphas"] == saved_graph["dominant_alphas"] and graph["active_alphas"] == saved_graph["active_alphas"]
    assert _alpha(graph, "A601", "v2")["activation_score"] < _alpha(saved_graph, "A601", "v2")["activation_score"]
    assert _alpha(graph, "A601", "v2")["raw_supporting_claim_count"] < _alpha(saved_graph, "A601", "v2")["raw_supporting_claim_count"]
    assert _load(run_copy, "week3_pipeline_status.json")["outcome"] == "success"
    # the run audit (another reader of the shared selector) reports the same exclusions: 50 claims left the unverified pools
    assert _stance_exclusions_by_alpha(run_copy) == {"A201": 7, "A301": 5, "A304": 6, "A501": 8, "A601": 24}


def test_removing_the_metadata_key_rolls_the_run_back_to_the_original_bytes(run_copy):
    original_bytes = (run_copy / "alpha_matches.json").read_bytes()
    saved_graph = _load(run_copy, "structure_graph.json")
    _set_metadata(run_copy, **{CONSUMPTION_METADATA_KEY: CONSUMPTION_CONTRACT_V2})
    _run(run_copy)
    assert (run_copy / "alpha_matches.json").read_bytes() != original_bytes
    _set_metadata(run_copy, **{CONSUMPTION_METADATA_KEY: None})
    _run(run_copy)
    assert (run_copy / "alpha_matches.json").read_bytes() == original_bytes  # blocks and marker are gone, byte for byte
    assert _load(run_copy, "structure_graph.json") == saved_graph and "evidence_consumption" not in _load(run_copy, "structure_graph.json")


# ---------------------------------------------------------------------------
# Failure states
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["v3", "alpha_evidence_consumption.v1", "", 2, True])
def test_an_unknown_contract_version_produces_no_result_and_its_own_failure_stage(run_copy, bad):
    (run_copy / "structure_graph.json").unlink()  # inside the temp copy: so that "no result" can be asserted
    original_bytes = (run_copy / "alpha_matches.json").read_bytes()
    _set_metadata(run_copy, **{CONSUMPTION_METADATA_KEY: bad})
    repo = _run(run_copy)
    status = _load(run_copy, "week3_pipeline_status.json")
    assert status["outcome"] == "failed" and status["stage"] == "evidence_consumption:EVIDENCE_CONSUMPTION_ILLEGAL_CONTRACT_VERSION"
    assert not (run_copy / "structure_graph.json").exists() and repo.get_graph(RUN_ID) is None  # nothing was scored, nothing persisted
    assert (run_copy / "alpha_matches.json").read_bytes() == original_bytes  # the input was not touched either
    assert any("EVIDENCE_CONSUMPTION_ILLEGAL_CONTRACT_VERSION" in line for line in (run_copy / "error_logs" / "week3_pipeline_errors.jsonl").read_text().splitlines())


def test_a_ticker_mismatch_between_metadata_and_the_matches_fails_explicitly(run_copy):
    _set_metadata(run_copy, **{CONSUMPTION_METADATA_KEY: CONSUMPTION_CONTRACT_V2, "ticker": "AMD"})
    (run_copy / "structure_graph.json").unlink()
    _run(run_copy)
    status = _load(run_copy, "week3_pipeline_status.json")
    assert status["outcome"] == "failed" and status["stage"] == "evidence_consumption:EVIDENCE_CONSUMPTION_TICKER_MISMATCH"
    assert not (run_copy / "structure_graph.json").exists()


def test_an_unexpected_failure_inside_the_overlay_is_its_own_stage_and_produces_no_result(run_copy, monkeypatch):
    from comqutor_alpha.api import routes_research

    (run_copy / "structure_graph.json").unlink()
    _set_metadata(run_copy, **{CONSUMPTION_METADATA_KEY: CONSUMPTION_CONTRACT_V2})

    def explode(*_args, **_kwargs):
        raise RuntimeError("synthetic failure inside the consumption overlay")

    monkeypatch.setattr(routes_research, "apply_alpha_evidence_consumption", explode)
    repo = _run(run_copy)
    status = _load(run_copy, "week3_pipeline_status.json")
    assert status["outcome"] == "failed" and status["stage"] == "evidence_consumption_apply"  # not "activation_scoring", not a success
    assert not (run_copy / "structure_graph.json").exists() and repo.get_graph(RUN_ID) is None


@pytest.mark.parametrize("damage, reason", [("delete", "ledger_unavailable"), ("tamper", "ledger_integrity_failed")])
def test_a_missing_or_tampered_ledger_never_excludes_anything_and_is_disclosed_per_pair(run_copy, damage, reason):
    ledger = run_copy / "llm_semantic_calls.jsonl"
    if damage == "delete":
        ledger.unlink()
    else:
        ledger.write_text(ledger.read_text(encoding="utf-8") + "\n", encoding="utf-8")  # one byte more: the manifest hash no longer matches
    _set_metadata(run_copy, **{CONSUMPTION_METADATA_KEY: CONSUMPTION_CONTRACT_V2})
    _run(run_copy)
    assert _load(run_copy, "week3_pipeline_status.json")["outcome"] == "success"  # an unverifiable ledger is a disclosed state, not a crash
    summary = _load(run_copy, "structure_graph.json")["evidence_consumption"]
    assert summary["stance"]["model_judged"] == 0 and summary["positive_admission"]["excluded"] == 0
    assert summary["stance"]["unjudged_by_reason"] == {reason: 163, "missing_result": 1}
    assert summary["stance"]["unjudged_by_category"] == {"UNVERIFIED": 163, "MISSING": 1}
    assert summary["ledger"]["available"] is (damage == "tamper")
    assert _alpha(_load(run_copy, "structure_graph.json"), "A301")["activation_score"] == 22.0056  # official result unchanged either way


# ---------------------------------------------------------------------------
# Re-evaluation: recomputed from today's inputs, never reused
# ---------------------------------------------------------------------------


def test_a_changed_source_verification_is_picked_up_on_the_next_pass_and_a_changed_judgment_is_corroborated_not_trusted(run_copy):
    _set_metadata(run_copy, **{CONSUMPTION_METADATA_KEY: CONSUMPTION_CONTRACT_V2})
    _run(run_copy)
    first_graph = _load(run_copy, "structure_graph.json")
    first = block_for_match(next(m for m in _load(run_copy, "alpha_matches.json")["matches"] if m["claim_id"] == CLAIM_5))
    assert first["source_support"]["verified_eligible"] is True
    assert CLAIM_5 in _alpha(first_graph, "A301")["claim_ids"]

    # (1) the content verification of claim 5 is withdrawn (e.g. a re-evaluation) -> the next pass recomputes the mirror and the pool
    structured = _load(run_copy, "structured_agent_outputs.json")
    record = next(r for r in structured["records"] if r["claim_id"] == CLAIM_5)
    record["content_support_status"] = "PENDING_REVIEW"
    record["content_support_review"] = {**record["content_support_review"], "status": "PENDING_REVIEW"}
    (run_copy / "structured_agent_outputs.json").write_text(json.dumps(structured, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _run(run_copy)
    second = block_for_match(next(m for m in _load(run_copy, "alpha_matches.json")["matches"] if m["claim_id"] == CLAIM_5))
    assert second["source_support"]["verified_eligible"] is False
    assert second["binding"]["source_state_sha256"] != first["binding"]["source_state_sha256"]
    assert CLAIM_5 not in _alpha(_load(run_copy, "structure_graph.json"), "A301")["claim_ids"]

    # (2) the saved model label is edited WITHOUT the run's ledger -> the ledger does not corroborate it, so it is not MODEL_JUDGED
    payload = _load(run_copy, "alpha_matches.json")
    match = next(m for m in payload["matches"] if m["claim_id"] == CLAIM_5)
    for pool in ("candidate_scores", "top_candidates", "eligible_candidates"):
        for candidate in match[pool]:
            if candidate["alpha_id"] == match["matched_alpha"]:
                candidate["evidence_stance"] = "opposes_alpha"
    (run_copy / "alpha_matches.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _run(run_copy)
    third = block_for_match(next(m for m in _load(run_copy, "alpha_matches.json")["matches"] if m["claim_id"] == CLAIM_5))
    assert third["stance"]["state"] == "UNJUDGED" and third["stance"]["unjudged_reason"] == "ledger_label_mismatch"
    assert third["positive_admission"]["admitted"] is True


def test_a_change_that_leaves_eligibility_unchanged_still_moves_the_source_state_binding_and_the_mirror(run_copy):
    _set_metadata(run_copy, **{CONSUMPTION_METADATA_KEY: CONSUMPTION_CONTRACT_V2})
    _run(run_copy)
    first = {m["claim_id"]: block_for_match(m) for m in _load(run_copy, "alpha_matches.json")["matches"] if m["match_status"] == "matched"}
    victim = next(cid for cid, b in sorted(first.items()) if b["source_support"]["verified_eligible"] is False
                  and b["source_support"]["content_support_status"] != "BACKGROUND")
    structured = _load(run_copy, "structured_agent_outputs.json")
    record = next(r for r in structured["records"] if r["claim_id"] == victim)
    record["content_support_status"] = "BACKGROUND"  # not a resolved support status: eligibility stays False
    (run_copy / "structured_agent_outputs.json").write_text(json.dumps(structured, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _run(run_copy)
    second = {m["claim_id"]: block_for_match(m) for m in _load(run_copy, "alpha_matches.json")["matches"] if m["match_status"] == "matched"}
    assert second[victim]["source_support"]["verified_eligible"] is False
    assert second[victim]["source_support"]["content_support_status"] == "BACKGROUND"
    assert second[victim]["binding"]["source_state_sha256"] != first[victim]["binding"]["source_state_sha256"]
    # every other pair is exactly as before
    assert {cid: b for cid, b in second.items() if cid != victim} == {cid: b for cid, b in first.items() if cid != victim}


def _retarget_stance(run_dir: Path, claim_id: str, new_label: str) -> None:
    """Make a model judgment change consistently in the saved matches AND the run's ledger (with its manifest hash)."""
    payload = _load(run_dir, "alpha_matches.json")
    match = next(m for m in payload["matches"] if m["claim_id"] == claim_id)
    alpha_id = match["matched_alpha"]
    for pool in ("candidate_scores", "top_candidates", "eligible_candidates"):
        for candidate in match[pool]:
            if candidate["alpha_id"] == alpha_id:
                candidate["evidence_stance"] = new_label
    (run_dir / "alpha_matches.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = []
    for line in (run_dir / "llm_semantic_calls.jsonl").read_text(encoding="utf-8").splitlines():
        if claim_id in line and '"evidence_stance_classifier"' in line:
            record = json.loads(line)
            for item in record["validated_output"]["items"]:
                if item["claim_id"] == claim_id and item["target_alpha_id"] == alpha_id:
                    item["stance"] = new_label
            line = json.dumps(record, ensure_ascii=False)
        lines.append(line)
    (run_dir / "llm_semantic_calls.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = _load(run_dir, "llm_semantic_manifest.json")
    manifest["calls_file_sha256"] = _sha(run_dir / "llm_semantic_calls.jsonl")
    (run_dir / "llm_semantic_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def test_a_corroborated_opposition_removes_the_claim_from_the_official_pool_and_the_trace_shows_the_shared_reason(run_copy):
    _retarget_stance(run_copy, CLAIM_5, "opposes_alpha")
    _set_metadata(run_copy, **{CONSUMPTION_METADATA_KEY: CONSUMPTION_CONTRACT_V2})
    _run(run_copy)
    graph = _load(run_copy, "structure_graph.json")
    assert CLAIM_5 not in _alpha(graph, "A301")["claim_ids"]  # a verified, otherwise eligible claim -- kept out only by the stance policy

    trace = get_evidence_trace_response(RUN_ID, run_copy.parent, claim_id=CLAIM_5)["item"]
    consumption = trace["consumption"]
    assert consumption["state"] == "CURRENT" and consumption["verification_error"] is None
    assert consumption["stance"]["state"] == "MODEL_JUDGED" and consumption["stance"]["label"] == "opposes_alpha" and consumption["stance"]["ledger"] == "VERIFIED"
    assert consumption["positive_admission"]["admitted"] is False and consumption["positive_admission"]["reason_code"] == "STANCE_MODEL_NOT_SUPPORTING"
    assert consumption["text_rule"]["relation"] == "activation"  # the raw baseline is still the text rule's, not a rewritten one
    assert trace["scoring"]["status_code"] == "NOT_SCORED" and trace["scoring"]["not_scored_code"] == "STANCE_MODEL_NOT_SUPPORTING"
    assert trace["summary"]["scoring"] == "NOT_SCORED"
    assert consumption["relevance"]["weight_authority"] == "LEXICAL_RULE_FALLBACK" and consumption["relevance"]["model_weight"] is None


def test_the_trace_of_a_legacy_run_has_no_consumption_key_and_a_v2_run_reports_current_blocks(run_copy):
    legacy = get_evidence_trace_response(RUN_ID, run_copy.parent, claim_id=CLAIM_5)["item"]
    assert "consumption" not in legacy
    _set_metadata(run_copy, **{CONSUMPTION_METADATA_KEY: CONSUMPTION_CONTRACT_V2})
    _run(run_copy)
    item = get_evidence_trace_response(RUN_ID, run_copy.parent, claim_id=CLAIM_5)["item"]
    assert item["consumption"]["state"] == "CURRENT" and item["scoring"]["status_code"] == "IN_OFFICIAL_POOL"
    artifact = get_evidence_trace_response(RUN_ID, run_copy.parent)
    assert artifact["contracts"][CONSUMPTION_METADATA_KEY] == CONSUMPTION_CONTRACT_V2


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def test_the_stance_audit_export_reports_the_applied_effect_only_for_v2(run_copy):
    legacy_payload, graph = _load(run_copy, "alpha_matches.json"), _load(run_copy, "structure_graph.json")
    legacy = build_evidence_stance_audit(run_id=RUN_ID, ticker="NVDA", alpha_matches_payload=legacy_payload, graph_payload=graph)
    assert legacy["effect_mode"] == "shadow" and legacy["stance_effect_applied"] is False and "stance_effect" not in legacy
    assert all("consumption_contract" not in r for r in legacy["records"])
    assert all(r["ticker_specific"] is True for r in legacy["records"])  # the legacy field is true for every record (non-discriminative)

    _set_metadata(run_copy, **{CONSUMPTION_METADATA_KEY: CONSUMPTION_CONTRACT_V2})
    _run(run_copy)
    v2 = build_evidence_stance_audit(run_id=RUN_ID, ticker="NVDA", alpha_matches_payload=_load(run_copy, "alpha_matches.json"), graph_payload=_load(run_copy, "structure_graph.json"))
    assert v2["effect_mode"] == "positive_pool_exclusion" and v2["stance_effect_applied"] is True
    assert v2["stance_effect"] == {"policy": "alpha_stance_policy.v1", "scope": "matched Alpha's positive pool only", "excluded_pairs": 87}
    flags = {r["ticker_specific"] for r in v2["records"]}
    assert flags == {True, False}  # the v2 field discriminates
    assert {r["target_name_present"] for r in v2["records"]} == {True, False}
    assert all(r["target_name_present"] == r["ticker_specific"] for r in v2["records"])  # one decision, reported under both names
    assert sum(1 for r in v2["records"] if r["ticker_specific"]) == 496  # the saved run's name-present records (see the legacy-export measurement)
    assert all(r["consumption_contract"] == CONSUMPTION_CONTRACT_V2 for r in v2["records"])
    excluded = [r for r in v2["records"] if r["positive_admission"] and not r["positive_admission"]["admitted"]]
    assert len(excluded) == 87 and {r["positive_admission"]["reason_code"] for r in excluded} == {"STANCE_MODEL_NOT_SUPPORTING"}


# ---------------------------------------------------------------------------
# Persistence: the new fields survive the production path unchanged
# ---------------------------------------------------------------------------


def assert_persistence_round_trip(run_dir: Path, repo) -> int:
    """Shared by the SQLite test here and the PostgreSQL test: what the repository returns equals what the file store holds."""
    payload, graph_file = _load(run_dir, "alpha_matches.json"), _load(run_dir, "structure_graph.json")
    rows = {row["claim_id"]: row for row in repo.get_alpha_matches(RUN_ID)}
    compared = 0
    for match in payload["matches"]:
        if match["match_status"] != "matched":
            continue
        row = rows[match["claim_id"]]
        file_block = block_for_match(match)
        db_candidate = next(c for c in row["candidate_scores"] if c["alpha_id"] == match["matched_alpha"])
        db_block = db_candidate[CONSUMPTION_BLOCK_KEY]
        assert db_block == file_block  # version, raw baseline (text rule, stance, lexical), policy decisions and reasons: identical
        assert db_block["contract"] == CONSUMPTION_CONTRACT_V2
        assert db_block["relevance"]["lexical_baseline"] == db_block["relevance"]["effective_weight"] == pytest.approx(row["match_score"])
        assert db_block["text_rule"]["relation"] == db_candidate["relation"] and db_block["text_rule"]["assertion_status"] == row["assertion_status"]
        compared += 1
    graph_db = repo.get_graph(RUN_ID)["graph_json"]
    assert graph_db["evidence_consumption"] == graph_file["evidence_consumption"]
    assert graph_db["activation"] == graph_file["activation"]
    return compared


def test_the_new_fields_survive_the_production_persistence_path_unchanged(run_copy):
    _set_metadata(run_copy, **{CONSUMPTION_METADATA_KEY: CONSUMPTION_CONTRACT_V2})
    repo = _run(run_copy)
    assert assert_persistence_round_trip(run_copy, repo) == 164
    # a model-excluded pair keeps its reason code through the repository
    row = next(r for r in repo.get_alpha_matches(RUN_ID) if r["alpha_id"] and any(
        c.get(CONSUMPTION_BLOCK_KEY, {}).get("positive_admission", {}).get("admitted") is False for c in r["candidate_scores"]))
    block = next(c[CONSUMPTION_BLOCK_KEY] for c in row["candidate_scores"] if CONSUMPTION_BLOCK_KEY in c)
    assert block["positive_admission"]["reason_code"] == "STANCE_MODEL_NOT_SUPPORTING" and block["stance"]["state"] == "MODEL_JUDGED"


def test_a_reread_payload_selects_the_same_pools_as_the_in_memory_one(run_copy):
    _set_metadata(run_copy, **{CONSUMPTION_METADATA_KEY: CONSUMPTION_CONTRACT_V2})
    _run(run_copy)
    payload = _load(run_copy, "alpha_matches.json")
    eligible, excluded, _ = select_supporting_alpha_claims(payload["matches"], "A601")
    assert {e["reason"] for e in excluded if e["reason"] == "STANCE_MODEL_NOT_SUPPORTING"} == {"STANCE_MODEL_NOT_SUPPORTING"}
    pool_in_graph = set(_alpha(_load(run_copy, "structure_graph.json"), "A601", "v2")["claim_ids"])
    assert {r["claim_id"] for r in eligible} >= pool_in_graph
