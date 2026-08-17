"""B3 Entity Alpha Exposure gated seed lifecycle -- dedicated tests (task
B3_ENTITY_EXPOSURE_GATED_STATES).

Reuses the existing, unmodified Exposure Engine formula/qualification-
ceiling logic, the shared Evidence Fact Index, and the real approved demo
fixture -- never reimplements the engine, never a second dedup pass. Each
test below is numbered against the task's own section 11 checklist so
coverage can be audited item-by-item; items already covered by
``tests/test_entity_alpha_exposure_productization.py`` (draft_shadow/
approved_gating score-and-status invariants, hash mismatch, DB round-trip)
are not duplicated here.
"""

from __future__ import annotations

import math
from types import MappingProxyType

import pytest
import yaml

from comqutor_alpha.api.routes_research import (
    get_entity_alpha_exposures,
    get_persisted_structure_graph,
    run_research_request,
)
from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts
from comqutor_alpha.exposure.seed_loader import (
    APPROVAL_METADATA_INCOMPLETE,
    APPROVED_GATING,
    CANONICAL_STATUSES,
    DEFAULT_MANIFEST_PATH,
    DEFAULT_SEED_PATH,
    DISABLED,
    DRAFT_SHADOW,
    GATING_NOT_ALLOWED,
    REQUESTED_UPGRADE_IGNORED,
    ExposureSeedBundle,
    ExposureSeedError,
    TickerSeedLifecycle,
    load_exposure_seed,
    resolve_exposure_mode,
)
from comqutor_alpha.exposure_engine import compute_run_entity_alpha_exposures
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from scripts.w5_demo_fixtures import (
    DEMO_ANALYSIS_DATE,
    DEMO_SELECTED_ANALYSTS,
    approved_demo_outputs,
)
from tests.fixtures.week4_conflict_cases import activation_entry, activation_payload, match_record

# John's exact first-batch v0.1 seed (task section 4) -- kept here, verbatim,
# as the sole authoritative expected values for the exact-match contract
# test. Never derived from the YAML file itself (that would make the test
# tautological); retyped independently from the task spec.
JOHNS_SEED = {
    "NVDA": {"A101": 0.95, "A102": 0.75, "A103": 0.85, "A201": 0.90, "A301": 0.85, "A304": 0.75, "A601": 0.85},
    "SNDK": {"A101": 0.30, "A102": 0.20, "A103": 0.45, "A201": 0.80, "A301": 0.70, "A304": 0.75, "A601": 0.60},
    "TSM": {"A101": 0.55, "A102": 0.30, "A103": 0.60, "A201": 0.95, "A301": 0.75, "A304": 0.65, "A601": 0.55},
    "MSFT": {"A101": 0.70, "A102": 0.85, "A103": 0.65, "A301": 0.80, "A304": 0.70, "A601": 0.60},
    "QQQ": {"A001": 0.80, "A003": 0.75, "A101": 0.60, "A304": 0.70, "A501": 0.65, "A601": 0.75},
    "AMD": {"A101": 0.80, "A102": 0.55, "A103": 0.65, "A201": 0.85, "A301": 0.70, "A304": 0.75, "A601": 0.75},
}
NON_REISSUED_DRAFT_TICKERS = ("GOOGL", "AMZN", "AVGO", "SMCI", "SPY")


def _activation(alpha_id="A101", status="regime_level", score=91.0):
    entry = {
        "alpha_id": alpha_id,
        "alpha_name": alpha_id,
        "activation_score": score,
        "status": status,
        "_exposure_evidence": {
            "facts": [],
            "unique_evidence_fact_count": 0,
            "ticker_specific_fact_count": 0,
            "distinct_supporting_agent_count": 0,
            "qualifying_local_edge_count": 0,
        },
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
                "evidence_summary": {"evidence_count": 0, "distinct_supporting_agents": 0},
            }
        ],
    }


# ---------------------------------------------------------------------------
# Seed contract (task section 11, items 1-7)
# ---------------------------------------------------------------------------


def test_1_only_six_tickers_are_approved_gating_eligible():
    bundle = load_exposure_seed()
    approved = {
        ticker
        for ticker, lifecycle in bundle.lifecycle.items()
        if lifecycle.configured_status == APPROVED_GATING
    }
    assert approved == set(JOHNS_SEED)
    for ticker in NON_REISSUED_DRAFT_TICKERS:
        assert bundle.ticker_lifecycle(ticker).configured_status == DRAFT_SHADOW


def test_2_johns_six_seed_values_match_exactly_ticker_by_ticker_alpha_by_alpha():
    bundle = load_exposure_seed()
    for ticker, alphas in JOHNS_SEED.items():
        lifecycle = bundle.ticker_lifecycle(ticker)
        assert lifecycle.configured_status == APPROVED_GATING
        assert lifecycle.owner == "John"
        assert lifecycle.approved_by == "John"
        assert lifecycle.approved_at == "2026-08-11"
        assert lifecycle.seed_version == "v0.1"
        # Exact alpha coverage -- no extra alpha, no missing alpha.
        assert set(bundle.values[ticker]) == set(alphas)
        for alpha_id, expected_value in alphas.items():
            assert bundle.historical_mapping(ticker, alpha_id) == expected_value


def test_2b_old_eleven_ticker_draft_values_do_not_leak_into_approved_seed():
    """The task's own explicit warning: the prior draft seed's values for
    the six reissued tickers must NEVER be mistaken for John's numbers --
    proves the new values are genuinely different from the old ones this
    file used to hold for the same (ticker, alpha_id) pairs."""
    old_draft_values = {
        ("NVDA", "A103"): 0.70, ("NVDA", "A304"): 0.80, ("NVDA", "A601"): 0.90,
        ("TSM", "A101"): 0.85, ("TSM", "A102"): 0.80, ("TSM", "A301"): 0.85,
        ("MSFT", "A103"): 0.85, ("MSFT", "A601"): 0.75,
        ("SNDK", "A101"): 0.35, ("SNDK", "A102"): 0.25,
        ("AMD", "A101"): 0.85, ("AMD", "A102"): 0.80, ("AMD", "A601"): 0.85,
    }
    bundle = load_exposure_seed()
    for (ticker, alpha_id), old_value in old_draft_values.items():
        assert bundle.historical_mapping(ticker, alpha_id) != old_value


def test_3_missing_alpha_on_an_approved_ticker_stays_missing_never_zero():
    bundle = load_exposure_seed()
    # NVDA's John seed does not include A001/A003/A501 (task section 4) --
    # the old draft did. Must be genuinely absent, not silently zeroed.
    assert bundle.historical_mapping("NVDA", "A001") is None
    assert bundle.historical_mapping("NVDA", "A501") is None

    decision = resolve_exposure_mode(bundle, "NVDA")
    _, artifact = compute_run_entity_alpha_exposures(
        run_id="r1", ticker="NVDA", activation_payload=_activation(alpha_id="A001"),
        seed_bundle=bundle, mode_decision=decision,
    )
    record = artifact["records"][0]
    assert record["historical_mapping"] is None
    assert record["final_exposure"] is None
    assert record["exposure_status"] == "missing_seed"


def test_5_seed_loader_rejects_nan_bool_and_string_values(tmp_path):
    def _seed(value):
        return {
            "TESTX": {
                "seed_version": "v0.1", "owner": "John", "approved_by": "John",
                "approved_at": "2026-08-11", "status": APPROVED_GATING,
                "exposures": {"A101": value},
            }
        }

    for bad_value in (math.nan, math.inf, True, "0.5"):
        seed_path = tmp_path / f"seed_{bad_value!r}.yaml"
        review_path = tmp_path / "review.csv"
        methodology_path = tmp_path / "methodology.md"
        manifest_path = tmp_path / f"manifest_{bad_value!r}.yaml"
        seed_path.write_text(yaml.safe_dump(_seed(bad_value)), encoding="utf-8")
        review_path.write_text("review\n", encoding="utf-8")
        methodology_path.write_text("methodology\n", encoding="utf-8")
        import hashlib

        manifest_path.write_text(
            yaml.safe_dump(
                {
                    "schema_version": "entity_alpha_exposure_seed_manifest.v2",
                    "methodology_version": "test",
                    "seed_sha256": hashlib.sha256(seed_path.read_bytes()).hexdigest(),
                    "review_csv_sha256": hashlib.sha256(review_path.read_bytes()).hexdigest(),
                    "methodology_sha256": hashlib.sha256(methodology_path.read_bytes()).hexdigest(),
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ExposureSeedError):
            load_exposure_seed(
                seed_path, manifest_path, review_path=review_path, methodology_path=methodology_path
            )


def test_6_seed_loader_rejects_non_canonical_lifecycle_status(tmp_path):
    import hashlib

    seed = {
        "TESTX": {
            "seed_version": "v0.1", "owner": "John", "approved_by": "John",
            "approved_at": "2026-08-11", "status": "pending_review",
            "exposures": {"A101": 0.5},
        }
    }
    seed_path = tmp_path / "seed.yaml"
    review_path = tmp_path / "review.csv"
    methodology_path = tmp_path / "methodology.md"
    manifest_path = tmp_path / "manifest.yaml"
    seed_path.write_text(yaml.safe_dump(seed), encoding="utf-8")
    review_path.write_text("review\n", encoding="utf-8")
    methodology_path.write_text("methodology\n", encoding="utf-8")
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "entity_alpha_exposure_seed_manifest.v2",
                "methodology_version": "test",
                "seed_sha256": hashlib.sha256(seed_path.read_bytes()).hexdigest(),
                "review_csv_sha256": hashlib.sha256(review_path.read_bytes()).hexdigest(),
                "methodology_sha256": hashlib.sha256(methodology_path.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ExposureSeedError):
        load_exposure_seed(
            seed_path, manifest_path, review_path=review_path, methodology_path=methodology_path
        )
    assert "pending_review" not in CANONICAL_STATUSES


def test_7_real_manifest_files_are_the_ones_on_disk():
    # Sanity: the default paths this whole module resolves against are the
    # real, currently-committed-to-worktree config files, not a fixture.
    assert DEFAULT_SEED_PATH.exists()
    assert DEFAULT_MANIFEST_PATH.exists()
    load_exposure_seed()  # must not raise


# ---------------------------------------------------------------------------
# Lifecycle behavior (task section 11, items 8-17; 8-13/15 already covered
# by test_entity_alpha_exposure_productization.py)
# ---------------------------------------------------------------------------


def test_14_approved_gating_missing_approval_field_fails_closed():
    manifest = load_exposure_seed().manifest
    incomplete = TickerSeedLifecycle(
        ticker="FAKE", seed_version="v0.1", owner=None, approved_by="John",
        approved_at="2026-08-11", configured_status=APPROVED_GATING,
    )
    bundle = ExposureSeedBundle(
        manifest=manifest,
        values=MappingProxyType({"FAKE": MappingProxyType({"A101": 0.9})}),
        lifecycle=MappingProxyType({"FAKE": incomplete}),
    )
    decision = resolve_exposure_mode(bundle, "FAKE")
    assert decision.effective_status == DRAFT_SHADOW
    assert decision.configured_status == APPROVED_GATING
    assert APPROVAL_METADATA_INCOMPLETE in decision.reason_codes
    assert GATING_NOT_ALLOWED in decision.reason_codes
    # Gating must not silently proceed: the qualification ceiling must not
    # fire even though the seed *claims* approved_gating.
    _, artifact = compute_run_entity_alpha_exposures(
        run_id="r1", ticker="FAKE", activation_payload=_activation(score=91.0, status="regime_level"),
        seed_bundle=bundle, mode_decision=decision,
    )
    assert artifact["records"][0]["mode"] == "shadow"
    assert artifact["records"][0]["qualification_effect_applied"] is False


def test_16_disabled_leaves_activation_score_and_status_completely_unchanged():
    manifest = load_exposure_seed().manifest
    lifecycle = TickerSeedLifecycle(
        ticker="FAKE", seed_version="v0.1", owner="John", approved_by="John",
        approved_at="2026-08-11", configured_status=DISABLED,
    )
    bundle = ExposureSeedBundle(
        manifest=manifest,
        values=MappingProxyType({"FAKE": MappingProxyType({"A101": 0.05})}),  # would fail every threshold
        lifecycle=MappingProxyType({"FAKE": lifecycle}),
    )
    decision = resolve_exposure_mode(bundle, "FAKE")
    assert decision.effective_status == DISABLED
    activation_in = _activation(score=91.0, status="regime_level")
    result, artifact = compute_run_entity_alpha_exposures(
        run_id="r1", ticker="FAKE", activation_payload=activation_in,
        seed_bundle=bundle, mode_decision=decision,
    )
    assert result["alphas"][0]["activation_score"] == 91.0
    assert result["alphas"][0]["status"] == "regime_level"
    assert result["dominant_alphas"] == activation_in["dominant_alphas"]
    assert artifact["records"] == []
    assert artifact["effective_status"] == DISABLED


def test_17_env_var_cannot_upgrade_draft_or_disabled_to_gating(monkeypatch):
    bundle = load_exposure_seed()
    # GOOGL: real, current draft_shadow ticker in the live seed file.
    monkeypatch.setenv("COMQUTOR_ENTITY_EXPOSURE_MODE", "enforced")
    decision = resolve_exposure_mode(bundle, "GOOGL")
    assert decision.effective_status == DRAFT_SHADOW
    assert REQUESTED_UPGRADE_IGNORED in decision.reason_codes

    monkeypatch.setenv("COMQUTOR_ENTITY_EXPOSURE_STATUS", "approved_gating")
    decision2 = resolve_exposure_mode(bundle, "GOOGL")
    assert decision2.effective_status == DRAFT_SHADOW

    # A disabled ticker (synthetic) can never be re-enabled by env var either.
    manifest = bundle.manifest
    disabled_lifecycle = TickerSeedLifecycle(
        ticker="FAKE", seed_version="v0.1", owner="John", approved_by="John",
        approved_at="2026-08-11", configured_status=DISABLED,
    )
    disabled_bundle = ExposureSeedBundle(
        manifest=manifest,
        values=MappingProxyType({"FAKE": MappingProxyType({"A101": 0.9})}),
        lifecycle=MappingProxyType({"FAKE": disabled_lifecycle}),
    )
    monkeypatch.setenv("COMQUTOR_ENTITY_EXPOSURE_MODE", "enforced")
    decision3 = resolve_exposure_mode(disabled_bundle, "FAKE")
    assert decision3.effective_status == DISABLED

    # Downgrade direction still works normally (approved_gating -> shadow).
    monkeypatch.delenv("COMQUTOR_ENTITY_EXPOSURE_STATUS", raising=False)
    monkeypatch.setenv("COMQUTOR_ENTITY_EXPOSURE_MODE", "shadow")
    approved_lifecycle = TickerSeedLifecycle(
        ticker="FAKE2", seed_version="v0.1", owner="John", approved_by="John",
        approved_at="2026-08-11", configured_status=APPROVED_GATING,
    )
    approved_bundle = ExposureSeedBundle(
        manifest=manifest,
        values=MappingProxyType({"FAKE2": MappingProxyType({"A101": 0.9})}),
        lifecycle=MappingProxyType({"FAKE2": approved_lifecycle}),
    )
    decision4 = resolve_exposure_mode(approved_bundle, "FAKE2")
    assert decision4.effective_status == DRAFT_SHADOW


# ---------------------------------------------------------------------------
# Integration (task section 11, items 18-24; uses the real, approved demo
# NVDA fixture -- which is, since this task, a genuinely approved_gating
# ticker, so this also exercises the real end-to-end gated path, 0 Provider
# calls, offline).
# ---------------------------------------------------------------------------


def _repo():
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


@pytest.fixture(scope="module")
def real_gated_run(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("b3_gated_run")
    repo = _repo()
    payload = {
        "ticker": "NVDA",
        "analysis_date": DEMO_ANALYSIS_DATE,
        "selected_analysts": list(DEMO_SELECTED_ANALYSTS),
        "offline_raw_agent_outputs": approved_demo_outputs("NVDA"),
    }
    response = run_research_request(payload, output_root=tmp_path, graph_repository=repo)
    assert response["status"] == "completed", response
    return {"run_id": response["run_id"], "output_root": tmp_path, "repo": repo}


def test_18_artifact_contains_full_lifecycle_provenance(real_gated_run):
    from comqutor_alpha.storage.file_store import load_json_record

    artifact = load_json_record(
        real_gated_run["run_id"], "entity_alpha_exposures.json", output_root=real_gated_run["output_root"]
    )
    assert artifact["configured_status"] == APPROVED_GATING
    assert artifact["effective_status"] == APPROVED_GATING
    assert artifact["records"], "NVDA is one of John's approved tickers -- must produce records"
    for record in artifact["records"]:
        assert record["owner"] == "John"
        assert record["approved_by"] == "John"
        assert record["approved_at"] == "2026-08-11"
        assert record["configured_status"] == APPROVED_GATING
        assert record["effective_status"] == APPROVED_GATING
        assert record["run_id"] == real_gated_run["run_id"]
        assert record["ticker"] == "NVDA"


def test_19_structure_graph_embedded_exposure_matches_artifact_record(real_gated_run):
    from comqutor_alpha.storage.file_store import load_json_record

    graph = get_persisted_structure_graph(
        real_gated_run["run_id"], output_root=real_gated_run["output_root"], graph_repository=real_gated_run["repo"]
    )
    artifact = load_json_record(
        real_gated_run["run_id"], "entity_alpha_exposures.json", output_root=real_gated_run["output_root"]
    )
    records_by_alpha = {r["alpha_id"]: r for r in artifact["records"]}
    checked = 0
    for entry in graph["activation"]["alphas"]:
        embedded = entry.get("entity_exposure")
        if embedded is None:
            continue
        record = records_by_alpha[entry["alpha_id"]]
        for field in ("owner", "approved_by", "approved_at", "configured_status", "effective_status", "final_exposure"):
            assert embedded[field] == record[field]
        checked += 1
    assert checked > 0


def test_20_run_audit_entity_exposure_section_matches_artifact_lifecycle(real_gated_run):
    from comqutor_alpha.api.routes_research import build_run_audit_payload

    audit = build_run_audit_payload(
        real_gated_run["run_id"], real_gated_run["output_root"], repository=real_gated_run["repo"]
    )
    section = audit["entity_exposure"]
    assert section["configured_status"] == APPROVED_GATING
    assert section["effective_status"] == APPROVED_GATING
    assert section["owner"] == "John"
    assert section["approved_by"] == "John"
    assert section["approved_at"] == "2026-08-11"
    # Backward-compatible fields still present and correctly mapped.
    assert section["seed_approval_status"] == APPROVED_GATING
    assert section["enforcement_allowed"] is True
    for per_alpha in section["per_alpha"].values():
        assert per_alpha["configured_status"] == APPROVED_GATING


def test_21_api_endpoint_exposes_lifecycle_fields(real_gated_run):
    response = get_entity_alpha_exposures(
        real_gated_run["run_id"], output_root=real_gated_run["output_root"], graph_repository=real_gated_run["repo"]
    )
    assert response["status"] == "ready"
    assert response["records"]
    for record in response["records"]:
        assert record["configured_status"] == APPROVED_GATING
        assert record["effective_status"] == APPROVED_GATING
        assert record["owner"] == "John"


# ---------------------------------------------------------------------------
# B1/B2 compatibility (task section 11, items 25-29)
# ---------------------------------------------------------------------------


def test_25_exposure_module_never_imports_b1_stance_or_b2_admissibility():
    import ast
    from pathlib import Path

    for module_path in (
        Path("comqutor_alpha/exposure_engine.py"),
        Path("comqutor_alpha/exposure/seed_loader.py"),
    ):
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
        assert not any("evidence_stance" in name for name in imported), module_path
        assert not any("conflict_admissibility" in name for name in imported), module_path
        assert not any("conflict_detector" in name for name in imported), module_path


def test_27_28_exposure_lifecycle_never_changes_b2_evidence_count_or_conflict_score():
    """Constructs one real conflict candidate (A101 bull / A304 bear, real
    Evidence Fact Index grouping, real B2 admissibility) and runs the exact
    same activation payload through detect_alpha_conflicts three times --
    with no exposure attached, with draft_shadow exposure attached, and
    with approved_gating exposure attached. Evidence counts, conflict_score,
    and the full admissibility diagnostic must be byte-identical every time:
    Exposure is never part of the Conflict formula or B2's evidence-count
    input, by construction (exposure_engine.py never touches
    qualifying-claim pools; it only ever reads/caps activation_score/status
    after Conflict's own inputs are already fixed)."""
    ticker = "NVDA"  # a real ticker_specific match for match_record's default text
    matches = [
        match_record("c1", "A101", agent="a1", evidence=f"{ticker} datacenter demand is accelerating.", score=0.9),
        match_record("c2", "A101", agent="a2", evidence=f"{ticker} new supply agreements were announced.", score=0.9),
        match_record("c3", "A304", agent="a3", evidence=f"{ticker} valuation multiples remain stretched.", score=0.8),
        match_record("c4", "A304", agent="a4", evidence=f"{ticker} margin compression was flagged by analysts.", score=0.8),
    ]
    baseline_activation = activation_payload(
        activation_entry("A101", score=70.0, status="active", direction="positive"),
        activation_entry("A304", score=70.0, status="active", direction="negative"),
    )
    baseline = detect_alpha_conflicts(
        run_id="b3_run", ticker=ticker, activation_payload=baseline_activation, alpha_matches=matches
    )

    bundle = load_exposure_seed()  # real seed: NVDA is approved_gating

    def _with_exposure(status_override):
        activation = activation_payload(
            activation_entry("A101", score=70.0, status="active", direction="positive"),
            activation_entry("A304", score=70.0, status="active", direction="negative"),
        )
        for entry in activation["alphas"]:
            entry["_exposure_evidence"] = {
                "facts": [], "unique_evidence_fact_count": 0, "ticker_specific_fact_count": 0,
                "distinct_supporting_agent_count": 0, "qualifying_local_edge_count": 0,
            }
        decision = resolve_exposure_mode(bundle, ticker, status_override)
        result, _ = compute_run_entity_alpha_exposures(
            run_id="b3_run", ticker=ticker, activation_payload=activation,
            seed_bundle=bundle, mode_decision=decision,
        )
        return detect_alpha_conflicts(
            run_id="b3_run", ticker=ticker, activation_payload=result, alpha_matches=matches
        )

    shadow_result = _with_exposure(DRAFT_SHADOW)
    gated_result = _with_exposure(APPROVED_GATING)

    for observed, label in ((shadow_result, "draft_shadow"), (gated_result, "approved_gating")):
        assert observed["conflicts"] == baseline["conflicts"], label
        assert observed["main_conflict"] == baseline["main_conflict"], label
        assert observed["arbitration"]["candidate_evaluations"] == (
            baseline["arbitration"]["candidate_evaluations"]
        ), label
