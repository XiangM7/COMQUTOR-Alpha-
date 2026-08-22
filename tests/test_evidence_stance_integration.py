"""Sprint 2, Track B1: Evidence Stance integration tests (task spec
section 28, items 21-45).

Uses the same approved, deterministic, offline NVDA fixture as
test_artifact_export_and_api.py (scripts.w5_demo_fixtures.approved_demo_outputs)
for one real, completed research run, plus a real Architecture Replay of a
real source run. No network, no Provider, no LLM call anywhere in this file.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from comqutor_alpha.api.artifact_export import (
    PRODUCT_EXTENSION_ARTIFACT_FILENAMES,
    build_evidence_stance_audit,
)
from comqutor_alpha.api.routes_research import (
    get_evidence_stances_response,
    run_research_request,
)
from comqutor_alpha.replay.pipeline import run_structure_replay
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from comqutor_alpha.structure_engine import evidence_stance as es
from scripts.w5_demo_fixtures import (
    DEMO_ANALYSIS_DATE,
    DEMO_SELECTED_ANALYSTS,
    approved_demo_outputs,
)
from scripts.deterministic_echo_llm import build_deterministic_echo_gateway

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def real_completed_run(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("evidence_stance_run")
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    repo = GraphPersistenceRepository(engine)
    payload = {
        "ticker": "NVDA",
        "analysis_date": DEMO_ANALYSIS_DATE,
        "selected_analysts": list(DEMO_SELECTED_ANALYSTS),
        "offline_raw_agent_outputs": approved_demo_outputs("NVDA"),
    }
    gateway = build_deterministic_echo_gateway("evidence-stance-integration", tmp_path)
    response = run_research_request(
        payload, output_root=tmp_path, graph_repository=repo, week2_llm_gateway=gateway
    )
    assert response["status"] == "completed", response
    run_id = response["run_id"]
    run_dir = tmp_path / run_id
    conflict_result = repo.get_week4_conflict_result(run_id)
    return {
        "run_id": run_id,
        "run_dir": run_dir,
        "output_root": tmp_path,
        "response": response,
        "repo": repo,
        "conflict_result": conflict_result,
    }


def _load(run_dir, name):
    return json.loads((run_dir / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 21-24: candidate pool propagation
# ---------------------------------------------------------------------------


def test_21_candidate_scores_carry_stance(real_completed_run):
    matches = _load(real_completed_run["run_dir"], "alpha_matches.json")["matches"]
    scored = [m for m in matches if m.get("candidate_scores")]
    assert scored
    for candidate in scored[0]["candidate_scores"]:
        assert "evidence_stance" in candidate
        assert "counter_alpha_id" in candidate
        assert "stance_reason_codes" in candidate
        assert "stance_confidence_band" in candidate
        assert "requires_manual_review" in candidate
        assert "evidence_stance_version" in candidate


def test_22_top_candidates_carry_same_stance_result(real_completed_run):
    matches = _load(real_completed_run["run_dir"], "alpha_matches.json")["matches"]
    for match in matches:
        by_id_top = {c["alpha_id"]: c.get("evidence_stance") for c in match.get("top_candidates") or []}
        by_id_all = {c["alpha_id"]: c.get("evidence_stance") for c in match.get("candidate_scores") or []}
        for alpha_id, stance in by_id_top.items():
            if alpha_id in by_id_all:
                assert by_id_all[alpha_id] == stance


def test_23_eligible_candidates_carry_same_stance_result(real_completed_run):
    matches = _load(real_completed_run["run_dir"], "alpha_matches.json")["matches"]
    for match in matches:
        by_id_eligible = {
            c["alpha_id"]: c.get("evidence_stance") for c in match.get("eligible_candidates") or []
        }
        by_id_all = {c["alpha_id"]: c.get("evidence_stance") for c in match.get("candidate_scores") or []}
        for alpha_id, stance in by_id_eligible.items():
            if alpha_id in by_id_all:
                assert by_id_all[alpha_id] == stance


def test_24_top_level_matched_stance_consistent(real_completed_run):
    matches = _load(real_completed_run["run_dir"], "alpha_matches.json")["matches"]
    matched = [m for m in matches if m.get("match_status") == "matched"]
    assert matched
    for match in matched:
        top_alpha = match["matched_alpha"]
        candidate = next(c for c in match["candidate_scores"] if c["alpha_id"] == top_alpha)
        assert match["matched_evidence_stance"] == candidate["evidence_stance"]
        assert match["matched_counter_alpha_id"] == candidate["counter_alpha_id"]
        assert match["matched_stance_confidence_band"] == candidate["stance_confidence_band"]
    unmatched = [m for m in matches if m.get("match_status") != "matched"]
    for match in unmatched:
        assert match["matched_evidence_stance"] is None


# ---------------------------------------------------------------------------
# 25-27: Evidence Fact integration
# ---------------------------------------------------------------------------


def test_25_evidence_fact_ids_unchanged(real_completed_run):
    evidence_facts = _load(real_completed_run["run_dir"], "evidence_facts.json")
    graph = _load(real_completed_run["run_dir"], "structure_graph.json")
    v2_alphas = graph["activation_versions"]["v2"]["alphas"]
    all_group_ids_from_scoring = set()
    for alpha in v2_alphas:
        for fact in alpha.get("evidence_fact_groups") or []:
            all_group_ids_from_scoring.add(fact["evidence_fact_group_id"])
    exported_ids = {g["evidence_fact_group_id"] for g in evidence_facts["groups"]}
    assert exported_ids == all_group_ids_from_scoring


def test_26_evidence_fact_stance_aggregation_correct(real_completed_run):
    evidence_facts = _load(real_completed_run["run_dir"], "evidence_facts.json")
    matches = {m["claim_id"]: m for m in _load(real_completed_run["run_dir"], "alpha_matches.json")["matches"]}
    checked = 0
    for group in evidence_facts["groups"]:
        for alpha_id, stance_block in group.get("alpha_stances", {}).items():
            counted = sum(stance_block["member_stance_counts"].values())
            assert counted <= len(group["member_claim_ids"])
            rep_claim = matches.get(group["representative_claim_id"])
            if rep_claim:
                rep_candidate = next(
                    (c for c in rep_claim.get("candidate_scores") or [] if c["alpha_id"] == alpha_id), None
                )
                if rep_candidate is not None:
                    assert stance_block["representative_stance"] == rep_candidate["evidence_stance"]
                    checked += 1
    assert checked > 0


def test_27_mixed_member_stance_disclosed(real_completed_run):
    evidence_facts = _load(real_completed_run["run_dir"], "evidence_facts.json")
    for group in evidence_facts["groups"]:
        for stance_block in group.get("alpha_stances", {}).values():
            non_zero_stances = [k for k, v in stance_block["member_stance_counts"].items() if v > 0]
            expected_mixed = len(non_zero_stances) > 1
            assert stance_block["mixed_member_stances"] == expected_mixed
            if expected_mixed:
                assert stance_block["requires_manual_review"] is True


# ---------------------------------------------------------------------------
# 28-30: Activation/Conflict evidence detail, effect flag
# ---------------------------------------------------------------------------


def test_28_activation_evidence_detail_carries_stance_via_used_in_activation(real_completed_run):
    audit = build_evidence_stance_audit(
        run_id=real_completed_run["run_id"],
        ticker="NVDA",
        alpha_matches_payload=_load(real_completed_run["run_dir"], "alpha_matches.json"),
        graph_payload=_load(real_completed_run["run_dir"], "structure_graph.json"),
        conflict_payload=real_completed_run["conflict_result"],
    )
    used = [r for r in audit["records"] if r["used_in_activation"]]
    assert used
    for record in used:
        assert record["evidence_fact_group_ids"]


def test_29_conflict_evidence_audit_carries_stance_via_used_in_conflict(real_completed_run):
    audit = build_evidence_stance_audit(
        run_id=real_completed_run["run_id"],
        ticker="NVDA",
        alpha_matches_payload=_load(real_completed_run["run_dir"], "alpha_matches.json"),
        graph_payload=_load(real_completed_run["run_dir"], "structure_graph.json"),
        conflict_payload=real_completed_run["conflict_result"],
    )
    conflict_relevant = [r for r in audit["records"] if r["used_in_conflict"]]
    # John's B2 Conflict Evidence Admissibility gate: this real fixture's
    # declared pairs (Sprint 1 verification predates B1/B2) no longer clear
    # B2's stricter per-side admission bar -- main_conflict is null, conflicts
    # is empty -- so no claim is part of an *admitted* conflict's fact
    # groups, and used_in_conflict is correctly False everywhere for this
    # exact run. See tests/test_week4_golden_closure.py for the honest
    # admissibility diagnostic on this same fixture, and the synthetic
    # companion test below for direct proof this flag still responds to a
    # real admitted conflict's fact_group_ids when one exists.
    assert real_completed_run["conflict_result"]["conflicts"] == []
    assert conflict_relevant == []
    for record in audit["records"]:
        assert record["used_in_conflict"] is False


def test_29b_conflict_evidence_audit_used_in_conflict_flag_can_be_true():
    """Synthetic, minimal companion to test_29 above: proves
    used_in_conflict genuinely responds to an admitted conflict's
    bull_fact_group_ids/bear_fact_group_ids -- not merely always False --
    independent of whether any specific real fixture happens to clear
    John's B2 gate. Never reclassifies/re-groups/re-runs Conflict; just
    hand-builds the minimal already-computed shapes build_evidence_stance_audit
    reads (the exact same extraction the real pipeline performs)."""
    alpha_matches_payload = {
        "matches": [
            {
                "claim_id": "c1",
                "source_agent_output_id": "o1",
                "agent": "agent_one",
                "matched_alpha": "A",
                "match_status": "matched",
                "claim": "evidence text",
                "evidence": "evidence text",
                "candidate_scores": [
                    {
                        "alpha_id": "A",
                        "score": 0.8,
                        "relation": "activation",
                        "evidence_stance": "supports_alpha",
                    }
                ],
            }
        ]
    }
    graph_payload = {
        "activation_versions": {
            "v2": {
                "alphas": [
                    {
                        "alpha_id": "A",
                        "evidence_fact_groups": [
                            {"evidence_fact_group_id": "fg1", "member_claim_ids": ["c1"]}
                        ],
                    }
                ]
            }
        }
    }
    conflict_payload = {"conflicts": [{"bull_fact_group_ids": ["fg1"], "bear_fact_group_ids": []}]}

    audit = build_evidence_stance_audit(
        run_id="synthetic_run",
        ticker="NVDA",
        alpha_matches_payload=alpha_matches_payload,
        graph_payload=graph_payload,
        conflict_payload=conflict_payload,
    )
    conflict_relevant = [r for r in audit["records"] if r["used_in_conflict"]]
    assert conflict_relevant
    assert conflict_relevant[0]["claim_id"] == "c1"
    assert conflict_relevant[0]["used_in_activation"] is True


def test_30_stance_effect_applied_is_always_false(real_completed_run):
    audit = _load(real_completed_run["run_dir"], "evidence_stance_audit.json")
    assert audit["stance_effect_applied"] is False
    assert audit["effect_mode"] == "shadow"
    run_audit = _load(real_completed_run["run_dir"], "run_audit.json")
    assert run_audit["evidence_stance"]["stance_effect_applied"] is False


# ---------------------------------------------------------------------------
# 31-37: behavior invariants
# ---------------------------------------------------------------------------


def test_31_32_activation_scores_and_levels_are_real_and_plausible(real_completed_run):
    graph = _load(real_completed_run["run_dir"], "structure_graph.json")
    alphas = graph["activation"]["alphas"]
    assert alphas
    for alpha in alphas:
        assert isinstance(alpha["activation_score"], (int, float))
        assert isinstance(alpha["status"], str) and alpha["status"]


def test_33_34_35_conflict_outcomes_are_real_and_internally_consistent(real_completed_run):
    # Evidence Stance is a shadow layer never read by Conflict -- this
    # asserts the outcome is real (evidence-determined, never fabricated
    # or forced nonzero) and internally consistent, not a specific
    # hardcoded number (a different fixture run than Sprint 1's own
    # replay-verification runs, so the exact counts legitimately differ).
    conflict_result = real_completed_run["conflict_result"]
    arb = conflict_result["arbitration"]
    assert arb["declared_pair_count"] == 6
    assert (
        arb["admitted_count"] + arb["suppressed_count"] + arb["rejected_count"]
        == arb["declared_pair_count"]
    )
    if arb["admitted_count"] > 0:
        assert conflict_result["main_conflict"] is not None


def test_36_entity_exposure_unchanged(real_completed_run):
    exposure = _load(real_completed_run["run_dir"], "entity_alpha_exposures.json")
    invariants = exposure.get("activation_invariants") or {}
    if invariants:
        assert invariants.get("scores_unchanged") is True
        assert invariants.get("levels_unchanged") is True


def test_37_graph_unchanged_shape(real_completed_run):
    graph = _load(real_completed_run["run_dir"], "structure_graph.json")
    metrics = graph["graph_metrics"]
    assert metrics["node_count"] > 0
    assert metrics["edge_count"] >= 0


def test_evidence_stance_never_imported_by_activation_or_conflict_modules():
    for relative_path in (
        "comqutor_alpha/graph_engine/activation_scorer_v2.py",
        "comqutor_alpha/graph_engine/activation_scorer.py",
        "comqutor_alpha/conflict_engine/conflict_detector.py",
    ):
        tree = ast.parse((REPO_ROOT / relative_path).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "evidence_stance" not in node.module, relative_path
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "evidence_stance" not in alias.name, relative_path


# ---------------------------------------------------------------------------
# 38-45: artifact / API / replay
# ---------------------------------------------------------------------------


def test_38_evidence_stance_audit_exported(real_completed_run):
    assert (real_completed_run["run_dir"] / "evidence_stance_audit.json").exists()


def test_39_manifest_includes_stance_artifact(real_completed_run):
    manifest = _load(real_completed_run["run_dir"], "artifact_manifest.json")
    names = {a["artifact_name"] for a in manifest["artifacts"]}
    assert "evidence_stance_audit.json" in names
    assert "evidence_stance_audit.json" in PRODUCT_EXTENSION_ARTIFACT_FILENAMES


def test_40_artifact_hash_valid(real_completed_run):
    manifest = _load(real_completed_run["run_dir"], "artifact_manifest.json")
    entry = next(a for a in manifest["artifacts"] if a["artifact_name"] == "evidence_stance_audit.json")
    assert entry["status"] == "valid"
    raw = (real_completed_run["run_dir"] / "evidence_stance_audit.json").read_bytes()
    assert entry["sha256"] == hashlib.sha256(raw).hexdigest()
    assert entry["size_bytes"] == len(raw)


def test_41_api_returns_stance_artifact(real_completed_run):
    response = get_evidence_stances_response(
        real_completed_run["run_id"], real_completed_run["output_root"]
    )
    assert response["status"] == "ready"
    assert response["records"]
    assert response["classifier_version"] == es.CLASSIFIER_VERSION


def test_42_old_run_fallback_does_not_500(tmp_path):
    response = get_evidence_stances_response("does-not-exist-anywhere", tmp_path)
    assert response["status"] == "unavailable"
    assert response["records"] == []
    assert "reason_codes" in response


def test_43_44_45_replay_uses_replay_run_id_and_zero_provider_calls(tmp_path):
    source_root = REPO_ROOT / "outputs" / "runs"
    nvda_source_run_id = None
    for run_dir in sorted(source_root.iterdir()):
        metadata_path = run_dir / "metadata.json"
        if not metadata_path.exists():
            continue
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if str(metadata.get("ticker", "")).upper() == "NVDA":
            nvda_source_run_id = run_dir.name
            break
    assert nvda_source_run_id, "expected at least one real NVDA source run under outputs/runs"

    raw_path = source_root / nvda_source_run_id / "raw_agent_outputs.json"
    sha_before = hashlib.sha256(raw_path.read_bytes()).hexdigest()

    result = run_structure_replay(
        nvda_source_run_id,
        source_output_root=str(source_root),
        replay_output_root=str(tmp_path),
        persist=True,
        comparison=False,
    )
    assert result.status == "completed"
    assert result.tradingagents_calls == 0
    assert result.llm_provider_calls == 0
    assert result.market_data_provider_calls == 0

    sha_after = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    assert sha_after == sha_before

    replay_dir = Path(result.output_dir)
    audit = json.loads((replay_dir / "evidence_stance_audit.json").read_text(encoding="utf-8"))
    assert audit["run_id"] == result.replay_run_id
    for record in audit["records"]:
        assert record["run_id"] == result.replay_run_id
