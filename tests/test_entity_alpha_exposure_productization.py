from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from types import MappingProxyType

import pytest
import yaml

from comqutor_alpha.api.routes_research import get_entity_alpha_exposures
from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts
from comqutor_alpha.exposure.seed_loader import (
    ENFORCEMENT_NOT_ALLOWED,
    SEED_HASH_MISMATCH,
    SEED_NOT_APPROVED,
    SEED_VALUE_OUT_OF_RANGE,
    UNKNOWN_ALPHA_ID,
    ExposureModeDecision,
    ExposureSeedBundle,
    ExposureSeedError,
    load_exposure_seed,
    resolve_exposure_mode,
)
from comqutor_alpha.exposure_engine import (
    EXPOSURE_BELOW_DOMINANT_THRESHOLD,
    EXPOSURE_BELOW_REGIME_THRESHOLD,
    EXPOSURE_QUALIFICATION_APPLIED,
    EXPOSURE_SEED_MISSING,
    calculate_runtime_exposure_inputs,
    compute_run_entity_alpha_exposures,
)
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from comqutor_alpha.storage.file_store import load_json_record, save_json_record
from tests.fixtures.week4_conflict_cases import (
    activation_entry,
    activation_payload,
    match_record,
    two_alpha_taxonomy,
)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_seed_fixture(tmp_path, seed):
    seed_path = tmp_path / "seed.yaml"
    review_path = tmp_path / "review.csv"
    methodology_path = tmp_path / "methodology.md"
    manifest_path = tmp_path / "manifest.yaml"
    seed_path.write_text(yaml.safe_dump(seed), encoding="utf-8")
    review_path.write_text("review\n", encoding="utf-8")
    methodology_path.write_text("methodology\n", encoding="utf-8")
    manifest = {
        "schema_version": "entity_alpha_exposure_seed_manifest.v1",
        "seed_version": "test",
        "methodology_version": "test",
        "effective_date": "2026-07-31",
        "approval_status": "approved",
        "approved_by": "synthetic-test",
        "enforcement_allowed": True,
        "seed_sha256": _sha(seed_path),
        "review_csv_sha256": _sha(review_path),
        "methodology_sha256": _sha(methodology_path),
        "formal_plan_tickers": ["NVDA"],
        "extension_tickers": ["SNDK"],
    }
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return seed_path, manifest_path, review_path, methodology_path


def _load_fixture(paths):
    seed, manifest, review, methodology = paths
    return load_exposure_seed(
        seed, manifest, review_path=review, methodology_path=methodology
    )


def _fact(
    group_id,
    score,
    *,
    ticker_specific=True,
    agents=(("market_agent", 0.8),),
):
    return {
        "evidence_fact_group_id": group_id,
        "representative_claim_id": f"{group_id}:rep",
        "representative_match_score": score,
        "ticker_specific": ticker_specific,
        "member_claim_ids": [f"{group_id}:rep"],
        "agent_representatives": [
            {"agent": agent, "claim_id": f"{group_id}:{agent}", "confidence": confidence}
            for agent, confidence in agents
        ],
    }


def _summary(*facts, local_edges=0):
    agents = {
        rep["agent"]
        for fact in facts
        for rep in fact.get("agent_representatives", [])
    }
    return {
        "evidence_fact_index_version": "evidence_fact_index.v1",
        "facts": list(facts),
        "unique_evidence_fact_count": len(facts),
        "ticker_specific_fact_count": sum(
            1 for fact in facts if fact.get("ticker_specific") is True
        ),
        "distinct_supporting_agent_count": len(agents),
        "qualifying_local_edge_count": local_edges,
    }


def _activation(alpha_id="A101", status="regime_level", score=91.0, summary=None):
    entry = {
        "alpha_id": alpha_id,
        "alpha_name": alpha_id,
        "activation_score": score,
        "status": status,
        "_exposure_evidence": summary or _summary(),
    }
    return {
        "formula_version": "activation.v2.evidence_local_structure.v1",
        "weights": {},
        "run_timestamp": None,
        "as_of": None,
        "alphas": [entry],
        "dominant_alphas": [
            {
                "alpha_id": alpha_id,
                "alpha_name": alpha_id,
                "activation_score": score,
                "status": status,
                "direction": "positive",
                "evidence_summary": {
                    "evidence_count": 0,
                    "distinct_supporting_agents": 0,
                },
            }
        ],
    }


def _bundle_with_value(value, *, approved=False):
    bundle = load_exposure_seed()
    manifest = replace(
        bundle.manifest,
        approval_status="approved" if approved else "draft",
        approved_by="synthetic-test" if approved else None,
        enforcement_allowed=approved,
    )
    return ExposureSeedBundle(
        manifest=manifest,
        values=MappingProxyType({"SYNTH": MappingProxyType({"A101": value})}),
    )


def _decision(bundle, mode):
    return resolve_exposure_mode(bundle.manifest, mode)


def test_exact_seed_and_manifest_hashes_load():
    bundle = load_exposure_seed()
    assert bundle.manifest.seed_sha256 == (
        "97cd4510f3cc3d54965d351880346cb46c032eabd84a52e9651d1ba0029e513f"
    )
    assert bundle.historical_mapping("SNDK", "A102") == 0.25


def test_all_seed_values_are_unit_interval_and_immutable():
    bundle = load_exposure_seed()
    assert all(0.0 <= value <= 1.0 for row in bundle.values.values() for value in row.values())
    with pytest.raises(TypeError):
        bundle.values["NVDA"]["A101"] = 0.0


def test_missing_ticker_remains_none_not_zero():
    assert load_exposure_seed().historical_mapping("MISSING", "A101") is None


def test_unknown_alpha_and_out_of_range_are_rejected(tmp_path):
    paths = _write_seed_fixture(tmp_path, {"NVDA": {"A999": 0.5}})
    with pytest.raises(ExposureSeedError) as error:
        _load_fixture(paths)
    assert error.value.reason_code == UNKNOWN_ALPHA_ID

    paths = _write_seed_fixture(tmp_path, {"NVDA": {"A101": 1.01}})
    with pytest.raises(ExposureSeedError) as error:
        _load_fixture(paths)
    assert error.value.reason_code == SEED_VALUE_OUT_OF_RANGE


def test_manifest_hash_mismatch_is_rejected(tmp_path):
    paths = _write_seed_fixture(tmp_path, {"NVDA": {"A101": 0.5}})
    paths[0].write_text("NVDA:\n  A101: 0.6\n", encoding="utf-8")
    with pytest.raises(ExposureSeedError) as error:
        _load_fixture(paths)
    assert error.value.reason_code == SEED_HASH_MISMATCH


def test_draft_enforcement_downgrades_with_both_reasons():
    decision = resolve_exposure_mode(load_exposure_seed().manifest, "enforced")
    assert decision.effective_mode == "shadow"
    assert decision.reason_codes == (SEED_NOT_APPROVED, ENFORCEMENT_NOT_ALLOWED)


def test_synthetic_approved_manifest_allows_enforced_mode():
    bundle = _bundle_with_value(0.5, approved=True)
    assert _decision(bundle, "enforced").effective_mode == "enforced"


def test_current_evidence_uses_unique_ticker_fact_representatives():
    result = calculate_runtime_exposure_inputs(
        _summary(_fact("g1", 0.8), _fact("g2", 0.6), _fact("macro", 1.0, ticker_specific=False))
    )
    assert result["ticker_specific_fact_count"] == 2
    assert result["current_evidence"] == pytest.approx((2 / 4) * 0.7)


def test_agent_confidence_counts_each_agent_once_at_max_confidence():
    result = calculate_runtime_exposure_inputs(
        _summary(
            _fact("g1", 0.8, agents=(("market", 0.4), ("news", 0.7))),
            _fact("g2", 0.8, agents=(("market", 0.9),)),
        )
    )
    assert result["distinct_supporting_agent_count"] == 2
    assert result["agent_confidence"] == pytest.approx((0.9 + 0.7) / 2)


def test_no_evidence_produces_deterministic_zero_runtime_inputs():
    assert calculate_runtime_exposure_inputs(_summary()) == {
        "current_evidence": 0.0,
        "agent_confidence": 0.0,
        "unique_evidence_fact_count": 0,
        "ticker_specific_fact_count": 0,
        "distinct_supporting_agent_count": 0,
        "qualifying_local_edge_count": 0,
        "mean_representative_match_score": 0.0,
        "ticker_specific_fact_ratio": 0.0,
        "representative_fact_group_ids": [],
    }


def test_shadow_computes_flags_without_changing_score_level_or_dominant_list():
    bundle = _bundle_with_value(0.4)
    activation = _activation()
    result, artifact = compute_run_entity_alpha_exposures(
        run_id="run-1",
        ticker="SYNTH",
        activation_payload=activation,
        seed_bundle=bundle,
        mode_decision=_decision(bundle, "shadow"),
    )
    record = artifact["records"][0]
    assert record["final_exposure"] == pytest.approx(0.2)
    assert record["would_block_dominant"] is True
    assert record["would_block_regime_level"] is True
    assert record["qualification_effect_applied"] is False
    assert result["alphas"][0]["activation_score"] == 91.0
    assert result["alphas"][0]["status"] == "regime_level"
    assert result["dominant_alphas"] == activation["dominant_alphas"]
    assert artifact["activation_invariants"] == {
        "scores_unchanged": True,
        "levels_unchanged": True,
        "shadow_mode_did_not_alter_activation": True,
    }


def test_shadow_entity_exposure_does_not_change_conflict_outcomes():
    before = activation_payload(
        activation_entry("A101", score=90, status="dominant", direction="positive"),
        activation_entry("A304", score=88, status="dominant", direction="negative"),
    )
    for entry in before["alphas"]:
        entry["_exposure_evidence"] = _summary()
    matches = [
        match_record("c1", "A101", direction="positive"),
        match_record("c2", "A304", direction="negative"),
    ]
    taxonomy = two_alpha_taxonomy("A101", "A304")
    baseline = detect_alpha_conflicts(
        run_id="run-1",
        ticker="SYNTH",
        activation_payload=before,
        alpha_matches=matches,
        taxonomy=taxonomy,
    )
    after, _ = compute_run_entity_alpha_exposures(
        run_id="run-1",
        ticker="SYNTH",
        activation_payload=before,
        seed_bundle=_bundle_with_value(0.4),
        mode_decision=_decision(_bundle_with_value(0.4), "shadow"),
    )
    observed = detect_alpha_conflicts(
        run_id="run-1",
        ticker="SYNTH",
        activation_payload=after,
        alpha_matches=matches,
        taxonomy=taxonomy,
    )
    assert observed == baseline


def test_missing_seed_returns_null_final_exposure():
    bundle = _bundle_with_value(0.4)
    activation = _activation(alpha_id="A102")
    _, artifact = compute_run_entity_alpha_exposures(
        run_id="run-1",
        ticker="SYNTH",
        activation_payload=activation,
        seed_bundle=bundle,
        mode_decision=_decision(bundle, "shadow"),
    )
    record = artifact["records"][0]
    assert record["historical_mapping"] is None
    assert record["final_exposure"] is None
    assert record["exposure_status"] == "missing_seed"
    assert record["reason_codes"] == ["SEED_ENTRY_MISSING"]


def test_override_candidate_is_never_applied_in_shadow():
    facts = tuple(
        _fact(f"g{index}", 0.9, agents=(("market", 0.9), ("news", 0.9), ("fund", 0.9)))
        for index in range(4)
    )
    bundle = _bundle_with_value(0.4)
    _, artifact = compute_run_entity_alpha_exposures(
        run_id="run-1",
        ticker="SYNTH",
        activation_payload=_activation(summary=_summary(*facts, local_edges=1)),
        seed_bundle=bundle,
        mode_decision=_decision(bundle, "shadow"),
    )
    assert artifact["records"][0]["override_candidate"] is True
    assert artifact["records"][0]["qualification_effect_applied"] is False


@pytest.mark.parametrize(
    ("historical", "summary", "expected_status", "expected_reasons"),
    [
        (
            0.4,
            _summary(),
            "active",
            {
                EXPOSURE_BELOW_DOMINANT_THRESHOLD,
                EXPOSURE_BELOW_REGIME_THRESHOLD,
                EXPOSURE_QUALIFICATION_APPLIED,
            },
        ),
        (
            0.8,
            _summary(),
            "dominant",
            {EXPOSURE_BELOW_REGIME_THRESHOLD, EXPOSURE_QUALIFICATION_APPLIED},
        ),
        (
            0.4,
            _summary(
                *tuple(_fact(f"g{i}", 1.0, agents=(("market", 1.0),)) for i in range(4))
            ),
            "regime_level",
            set(),
        ),
    ],
)
def test_synthetic_enforced_qualification_ceiling(
    historical, summary, expected_status, expected_reasons
):
    bundle = _bundle_with_value(historical, approved=True)
    result, artifact = compute_run_entity_alpha_exposures(
        run_id="run-1",
        ticker="SYNTH",
        activation_payload=_activation(summary=summary),
        seed_bundle=bundle,
        mode_decision=_decision(bundle, "enforced"),
    )
    assert result["alphas"][0]["status"] == expected_status
    assert result["alphas"][0]["activation_score"] == 91.0
    assert set(artifact["records"][0]["reason_codes"]) == expected_reasons


def test_synthetic_enforced_missing_seed_is_explicit_and_safe():
    bundle = _bundle_with_value(0.5, approved=True)
    result, artifact = compute_run_entity_alpha_exposures(
        run_id="run-1",
        ticker="SYNTH",
        activation_payload=_activation(alpha_id="A102"),
        seed_bundle=bundle,
        mode_decision=_decision(bundle, "enforced"),
    )
    assert result["alphas"][0]["status"] == "active"
    assert {EXPOSURE_SEED_MISSING, EXPOSURE_QUALIFICATION_APPLIED} <= set(
        artifact["records"][0]["reason_codes"]
    )


def test_db_and_artifact_round_trip_preserve_exposure(tmp_path):
    bundle = _bundle_with_value(0.4)
    _, artifact = compute_run_entity_alpha_exposures(
        run_id="run-1",
        ticker="SYNTH",
        activation_payload=_activation(),
        seed_bundle=bundle,
        mode_decision=_decision(bundle, "shadow"),
    )
    engine = build_engine("sqlite:///:memory:")
    repository = GraphPersistenceRepository(engine)
    repository.ensure_schema()
    repository.upsert_entity_alpha_exposures(
        run_id="run-1", ticker="SYNTH", artifact=artifact
    )
    assert repository.get_entity_alpha_exposures("run-1")[0] == artifact["records"][0]
    assert repository.get_entity_alpha_exposure("run-1", "A101") == artifact["records"][0]

    save_json_record("run-1", "entity_alpha_exposures.json", artifact, output_root=tmp_path)
    assert load_json_record(
        "run-1", "entity_alpha_exposures.json", output_root=tmp_path
    ) == json.loads(json.dumps(artifact))


def test_api_old_run_returns_explicit_unavailable_without_500(tmp_path):
    run_dir = tmp_path / "old-run"
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(
        json.dumps({"run_id": "old-run", "ticker": "NVDA"}), encoding="utf-8"
    )
    result = get_entity_alpha_exposures("old-run", output_root=tmp_path)
    assert result["status"] == "unavailable"
    assert result["records"] == []


def test_off_mode_writes_no_records_and_removes_transient_fact_summary():
    bundle = _bundle_with_value(0.4)
    result, artifact = compute_run_entity_alpha_exposures(
        run_id="run-1",
        ticker="SYNTH",
        activation_payload=_activation(),
        seed_bundle=bundle,
        mode_decision=ExposureModeDecision("off", "off", (), False),
    )
    assert artifact["records"] == []
    assert "_exposure_evidence" not in result["alphas"][0]
    assert "entity_exposure" not in result["alphas"][0]
