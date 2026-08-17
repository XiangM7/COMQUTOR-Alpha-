from __future__ import annotations

import hashlib
import json
from types import MappingProxyType

import pytest
import yaml

from comqutor_alpha.api.routes_research import get_entity_alpha_exposures
from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts
from comqutor_alpha.exposure.seed_loader import (
    APPROVED_GATING,
    DISABLED,
    DRAFT_SHADOW,
    SEED_HASH_MISMATCH,
    SEED_VALUE_OUT_OF_RANGE,
    UNKNOWN_ALPHA_ID,
    ExposureModeDecision,
    ExposureSeedBundle,
    ExposureSeedError,
    TickerSeedLifecycle,
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
from comqutor_alpha.graph_engine.alpha_level_classifier import classify_and_rebuild_collections
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
    """``seed`` is the NEW per-ticker shape: {TICKER: {alpha_id: value}}.
    Wraps each ticker in a minimal, complete approved_gating lifecycle
    block so existing value/range/alpha-id validation tests need not care
    about lifecycle fields at all."""
    wrapped = {
        ticker: {
            "seed_version": "test",
            "owner": "synthetic-test",
            "approved_by": "synthetic-test",
            "approved_at": "2026-07-31",
            "status": APPROVED_GATING,
            "exposures": exposures,
        }
        for ticker, exposures in seed.items()
    }
    seed_path = tmp_path / "seed.yaml"
    review_path = tmp_path / "review.csv"
    methodology_path = tmp_path / "methodology.md"
    manifest_path = tmp_path / "manifest.yaml"
    seed_path.write_text(yaml.safe_dump(wrapped), encoding="utf-8")
    review_path.write_text("review\n", encoding="utf-8")
    methodology_path.write_text("methodology\n", encoding="utf-8")
    manifest = {
        "schema_version": "entity_alpha_exposure_seed_manifest.v2",
        "methodology_version": "test",
        "seed_sha256": _sha(seed_path),
        "review_csv_sha256": _sha(review_path),
        "methodology_sha256": _sha(methodology_path),
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


def _bundle_with_value(value, *, approved=False, ticker="SYNTH", alpha_id="A101"):
    """A synthetic single-ticker bundle -- lifecycle is per-ticker (task
    B3_ENTITY_EXPOSURE_GATED_STATES), never a global manifest flag."""
    bundle = load_exposure_seed()
    lifecycle = TickerSeedLifecycle(
        ticker=ticker,
        seed_version="test",
        owner="synthetic-test" if approved else None,
        approved_by="synthetic-test" if approved else None,
        approved_at="2026-07-31" if approved else None,
        configured_status=APPROVED_GATING if approved else DRAFT_SHADOW,
    )
    return ExposureSeedBundle(
        manifest=bundle.manifest,
        values=MappingProxyType({ticker: MappingProxyType({alpha_id: value})}),
        lifecycle=MappingProxyType({ticker: lifecycle}),
    )


def _decision(bundle, status, *, ticker="SYNTH"):
    return resolve_exposure_mode(bundle, ticker, status)


def test_exact_seed_and_manifest_hashes_load():
    bundle = load_exposure_seed()
    assert bundle.manifest.seed_sha256 == (
        "6330f9175593b52cbc4a3b33c0a30ec909d3b91d854af964ca01b2af338134bf"
    )
    # SNDK is one of John's six first-batch approved_gating tickers (task
    # section 4) -- 0.20, not the old, now-superseded draft value (0.25).
    assert bundle.historical_mapping("SNDK", "A102") == 0.20
    assert bundle.ticker_lifecycle("SNDK").configured_status == APPROVED_GATING
    assert bundle.ticker_lifecycle("SNDK").owner == "John"
    # GOOGL was never in John's first batch -- stays draft_shadow, with its
    # original (unchanged, never-approved) draft value.
    assert bundle.historical_mapping("GOOGL", "A001") == 0.55
    assert bundle.ticker_lifecycle("GOOGL").configured_status == DRAFT_SHADOW
    assert bundle.ticker_lifecycle("GOOGL").owner is None


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


def test_draft_ticker_ignores_requested_upgrade_to_approved_gating():
    # GOOGL is one of the original 11 draft tickers John did not re-approve
    # in this batch -- a requested override can never upgrade it (task
    # section 7), regardless of what is asked for.
    bundle = load_exposure_seed()
    decision = resolve_exposure_mode(bundle, "GOOGL", APPROVED_GATING)
    assert decision.effective_mode == "shadow"
    assert decision.effective_status == DRAFT_SHADOW
    assert decision.configured_status == DRAFT_SHADOW


def test_synthetic_approved_manifest_allows_enforced_mode():
    bundle = _bundle_with_value(0.5, approved=True)
    assert _decision(bundle, APPROVED_GATING).effective_mode == "enforced"
    assert _decision(bundle, APPROVED_GATING).effective_status == APPROVED_GATING


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
        mode_decision=_decision(bundle, DRAFT_SHADOW),
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
        mode_decision=_decision(_bundle_with_value(0.4), DRAFT_SHADOW),
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
        mode_decision=_decision(bundle, DRAFT_SHADOW),
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
        mode_decision=_decision(bundle, DRAFT_SHADOW),
    )
    assert artifact["records"][0]["override_candidate"] is True
    assert artifact["records"][0]["qualification_effect_applied"] is False


@pytest.mark.parametrize(
    ("historical", "summary", "expected_qualified_level", "expected_reasons"),
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
    historical, summary, expected_qualified_level, expected_reasons
):
    """``compute_run_entity_alpha_exposures`` itself no longer caps
    ``status`` (task B4_ACTIVATION_LEVEL_ALIGNMENT: the alpha-level
    classifier is now the sole writer) -- it only computes and reports the
    diagnostic fields (would_block_dominant/would_block_regime_level/
    reason_codes) that feed that classifier. This test checks both halves:
    the diagnostics this function itself owns, and -- by feeding its output
    through classify_and_rebuild_collections exactly as
    graph_engine.pipeline does -- that the qualification ceiling this test
    is named for still holds end-to-end."""
    bundle = _bundle_with_value(historical, approved=True)
    result, artifact = compute_run_entity_alpha_exposures(
        run_id="run-1",
        ticker="SYNTH",
        activation_payload=_activation(summary=summary),
        seed_bundle=bundle,
        mode_decision=_decision(bundle, APPROVED_GATING),
    )
    # This function's own contract now: activation_score/status pass
    # through completely untouched -- qualification is reported, never
    # applied, here.
    assert result["alphas"][0]["status"] == "regime_level"
    assert result["alphas"][0]["activation_score"] == 91.0
    assert set(artifact["records"][0]["reason_codes"]) == expected_reasons

    # End-to-end: B4's classifier is the sole place the ceiling is actually
    # applied. regime_gate_passed=True isolates Exposure as the only acting
    # constraint under test here, matching how a real regime-candidate
    # alpha that already cleared _evaluate_regime_gate arrives at this
    # point in the real pipeline.
    result["alphas"][0]["regime_gate_passed"] = True
    classified = classify_and_rebuild_collections(result)
    assert classified["alphas"][0]["qualified_level"] == expected_qualified_level


def test_synthetic_enforced_missing_seed_is_explicit_and_safe():
    bundle = _bundle_with_value(0.5, approved=True)
    result, artifact = compute_run_entity_alpha_exposures(
        run_id="run-1",
        ticker="SYNTH",
        activation_payload=_activation(alpha_id="A102"),
        seed_bundle=bundle,
        mode_decision=_decision(bundle, APPROVED_GATING),
    )
    assert result["alphas"][0]["status"] == "regime_level"
    assert {EXPOSURE_SEED_MISSING, EXPOSURE_QUALIFICATION_APPLIED} <= set(
        artifact["records"][0]["reason_codes"]
    )

    # A missing approved seed entry fails closed end-to-end too (task
    # B4_ACTIVATION_LEVEL_ALIGNMENT section 8) -- even though
    # would_block_dominant/would_block_regime_level are individually False
    # for a null final_exposure, "missing" must never read as "computed and
    # merely low".
    result["alphas"][0]["regime_gate_passed"] = True
    classified = classify_and_rebuild_collections(result)
    assert classified["alphas"][0]["qualified_level"] == "active"


def test_db_and_artifact_round_trip_preserve_exposure(tmp_path):
    bundle = _bundle_with_value(0.4)
    _, artifact = compute_run_entity_alpha_exposures(
        run_id="run-1",
        ticker="SYNTH",
        activation_payload=_activation(),
        seed_bundle=bundle,
        mode_decision=_decision(bundle, DRAFT_SHADOW),
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
        mode_decision=ExposureModeDecision(
            ticker="SYNTH",
            requested_mode="off",
            effective_mode="off",
            configured_status=DISABLED,
            effective_status=DISABLED,
            reason_codes=(),
        ),
    )
    assert artifact["records"] == []
    assert artifact["effective_status"] == DISABLED
    assert "_exposure_evidence" not in result["alphas"][0]
    assert "entity_exposure" not in result["alphas"][0]
