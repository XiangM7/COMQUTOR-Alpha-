"""W4.2 SQLite persistence, migration, safety, and round-trip tests."""

from __future__ import annotations

import copy
import json

import pytest
import sqlalchemy as sa

from comqutor_alpha.api.routes_research import (
    get_persisted_structure_graph,
    run_research_request,
)
from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts
from comqutor_alpha.graph_engine.graph_schema import ACTIVATION_FORMULA_VERSION
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import (
    GraphPersistenceError,
    GraphPersistenceRepository,
    build_repository_from_env,
)
from comqutor_alpha.storage.db.schema import (
    MIGRATIONS,
    agent_outputs,
    alpha_activations,
    alpha_conflicts,
    alpha_matches,
    research_runs,
    schema_migrations,
    structure_graphs,
)
from tests.fixtures.week4_conflict_cases import (
    activation_entry,
    activation_payload,
    match_record,
)
from tests.test_week3_nvda_sanity import _nvda_offline_outputs


def _engine_and_repo():
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return engine, GraphPersistenceRepository(engine)


def _week4_payloads(run_id="w42_run", ticker="NVDA", *, score=90.0):
    activation = activation_payload(
        activation_entry("A001", score=50, direction="positive"),
        activation_entry("A003", score=50, direction="neutral"),
        activation_entry("A101", score=score, direction="positive"),
        activation_entry("A301", score=50, direction="positive"),
        activation_entry("A304", score=score, direction="negative"),
        activation_entry("A501", score=50, direction="negative"),
        activation_entry("A601", score=50, direction="positive"),
    )
    matches = [
        match_record("c101", "A101", score=0.9),
        match_record("c304", "A304", score=0.8),
        match_record("c501", "A501", score=0.7),
    ]
    conflict = detect_alpha_conflicts(
        run_id=run_id,
        ticker=ticker,
        activation_payload=activation,
        alpha_matches=matches,
    )
    return activation, conflict


def _persist(repo, run_id="w42_run", ticker="NVDA", *, score=90.0):
    activation, conflict = _week4_payloads(run_id, ticker, score=score)
    repo.persist_week4_results(
        run_id=run_id,
        ticker=ticker,
        activation_payload=activation,
        conflict_payload=conflict,
    )
    return activation, conflict


def _mutate_admitted_conflict(conflict_payload, mutator):
    """Apply `mutator` (conflict dict -> conflict dict) identically to both
    conflicts[0] and main_conflict, so the two stay equal to each other
    (satisfying _whitelist_conflict's own pre-existing internal-consistency
    check) while a mutated field can still disagree with the *separate*
    activation_payload being persisted alongside it -- exercising the
    Correctness Patch's new cross-payload snapshot check specifically,
    rather than the older same-payload self-consistency checks."""
    mutated = mutator(copy.deepcopy(conflict_payload["conflicts"][0]))
    conflict_payload["conflicts"][0] = mutated
    conflict_payload["main_conflict"] = copy.deepcopy(mutated)
    return conflict_payload


def _constraint_names(table):
    return {constraint.name for constraint in table.constraints if constraint.name}


class TestWeek4Schema:
    def test_alpha_activations_columns_primary_key_and_unique_constraint(self):
        assert set(alpha_activations.c) == {
            alpha_activations.c.id,
            alpha_activations.c.run_id,
            alpha_activations.c.ticker,
            alpha_activations.c.alpha_id,
            alpha_activations.c.alpha_name,
            alpha_activations.c.activation_score,
            alpha_activations.c.status,
            alpha_activations.c.direction,
            alpha_activations.c.formula_version,
            alpha_activations.c.activation_rank,
            alpha_activations.c.activation_json,
            alpha_activations.c.created_at,
            alpha_activations.c.updated_at,
        }
        assert alpha_activations.c.id.primary_key
        assert "uq_alpha_activations_run_alpha" in _constraint_names(alpha_activations)

    def test_alpha_conflicts_columns_primary_key_and_unique_constraint(self):
        required = {
            "id",
            "run_id",
            "ticker",
            "alpha_a",
            "alpha_b",
            "outcome",
            "bull_alpha_id",
            "bear_alpha_id",
            "conflict_score",
            "conflict_level",
            "contradiction_weight",
            "evidence_strength",
            "minimum_activation",
            "is_main_conflict",
            "conflict_rank",
            "reason_codes",
            "evidence_audit",
            "candidate_json",
            "conflict_json",
            "schema_version",
            "formula_version",
            "created_at",
            "updated_at",
        }
        assert set(alpha_conflicts.c.keys()) == required
        assert alpha_conflicts.c.id.primary_key
        assert "uq_alpha_conflicts_run_pair" in _constraint_names(alpha_conflicts)

    def test_migration_names_and_order_are_exact(self):
        assert [version for version, _ in MIGRATIONS] == [
            "0001_create_week3_alpha_matches_and_structure_graphs",
            "0002_create_week4_alpha_activations_and_alpha_conflicts",
            "0003_create_research_runs",
            "0004_create_agent_outputs",
        ]
        assert MIGRATIONS[0][1] == (alpha_matches, structure_graphs)
        assert MIGRATIONS[1][1] == (alpha_activations, alpha_conflicts)
        assert MIGRATIONS[2][1] == (research_runs,)
        assert MIGRATIONS[3][1] == (agent_outputs,)

    def test_sqlite_json_columns_use_json_type(self):
        engine = build_engine("sqlite:///:memory:")
        for column in (
            alpha_activations.c.activation_json,
            alpha_conflicts.c.reason_codes,
            alpha_conflicts.c.evidence_audit,
            alpha_conflicts.c.candidate_json,
            alpha_conflicts.c.conflict_json,
        ):
            assert isinstance(column.type.dialect_impl(engine.dialect), sa.JSON)


class TestMigration0002:
    def test_fresh_database_applies_0001_then_0002_and_reapply_is_empty(self):
        engine = build_engine("sqlite:///:memory:")
        assert apply_migrations(engine) == [version for version, _ in MIGRATIONS]
        assert apply_migrations(engine) == []
        with engine.connect() as conn:
            versions = conn.execute(sa.select(schema_migrations.c.version)).scalars().all()
        assert sorted(versions) == sorted(set(versions))

    def test_upgrade_from_0001_preserves_week3_rows_and_applies_later_migrations(self):
        engine = build_engine("sqlite:///:memory:")
        schema_migrations.create(engine)
        alpha_matches.create(engine)
        structure_graphs.create(engine)
        with engine.begin() as conn:
            conn.execute(
                sa.insert(schema_migrations).values(
                    version="0001_create_week3_alpha_matches_and_structure_graphs"
                )
            )
            conn.execute(
                sa.insert(alpha_matches).values(
                    run_id="old_run",
                    ticker="NVDA",
                    claim_id="old_claim",
                    match_score=0.8,
                    match_status="matched",
                )
            )
            conn.execute(
                sa.insert(structure_graphs).values(
                    run_id="old_run",
                    ticker="NVDA",
                    graph_json={"preserved": True},
                    graph_coherence_score=50,
                    schema_version="week3.structure_graph.v1",
                    graph_builder_version="week3.graph_builder.v1",
                    activation_scorer_version="week3.activation_scorer.v1",
                )
            )

        assert apply_migrations(engine) == [
            "0002_create_week4_alpha_activations_and_alpha_conflicts",
            "0003_create_research_runs",
            "0004_create_agent_outputs",
        ]
        with engine.connect() as conn:
            assert conn.scalar(sa.select(sa.func.count()).select_from(alpha_matches)) == 1
            assert conn.scalar(sa.select(sa.func.count()).select_from(structure_graphs)) == 1
            versions = conn.execute(sa.select(schema_migrations.c.version)).scalars().all()
        assert sorted(versions) == [
            "0001_create_week3_alpha_matches_and_structure_graphs",
            "0002_create_week4_alpha_activations_and_alpha_conflicts",
            "0003_create_research_runs",
            "0004_create_agent_outputs",
        ]


class TestActivationPersistence:
    def test_rows_round_trip_one_per_alpha_with_original_rank(self):
        _, repo = _engine_and_repo()
        activation, _ = _persist(repo)
        rows = repo.get_alpha_activations("w42_run")
        assert len(rows) == len(activation["alphas"])
        assert [row["alpha_id"] for row in rows] == [
            entry["alpha_id"] for entry in activation["alphas"]
        ]
        assert [row["activation_rank"] for row in rows] == list(range(len(rows)))
        assert rows[0]["formula_version"] == ACTIVATION_FORMULA_VERSION

    def test_activation_json_is_whitelisted_recursively(self):
        _, repo = _engine_and_repo()
        activation, conflict = _week4_payloads()
        activation["alphas"][0]["provider_response"] = "must-not-persist"
        activation["alphas"][0]["components"] = {
            "recency": {"raw": 100, "contribution": 10, "secret": "must-not-persist"},
            "unknown_component": {"prompt": "must-not-persist"},
        }
        repo.persist_week4_results(
            run_id="w42_run",
            ticker="NVDA",
            activation_payload=activation,
            conflict_payload=conflict,
        )
        stored = repo.get_alpha_activations("w42_run")[0]["activation_json"]
        serialized = json.dumps(stored)
        assert "provider_response" not in stored
        assert "unknown_component" not in stored["components"]
        assert "secret" not in serialized

    @pytest.mark.parametrize(
        "bad_score", [float("nan"), float("inf"), float("-inf"), "90"]
    )
    def test_nonfinite_activation_score_is_safely_rejected(self, bad_score):
        _, repo = _engine_and_repo()
        activation, conflict = _week4_payloads()
        activation["alphas"][0]["activation_score"] = bad_score
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_week4_results(
                run_id="w42_run",
                ticker="NVDA",
                activation_payload=activation,
                conflict_payload=conflict,
            )
        assert exc_info.value.reason_code == "WEEK4_ACTIVATION_PAYLOAD_INVALID"
        assert repo.get_alpha_activations("w42_run") == []

    def test_duplicate_alpha_and_wrong_formula_are_rejected(self):
        _, repo = _engine_and_repo()
        activation, conflict = _week4_payloads()
        activation["alphas"].append(copy.deepcopy(activation["alphas"][0]))
        with pytest.raises(GraphPersistenceError) as duplicate_error:
            repo.persist_week4_results(
                run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
            )
        assert duplicate_error.value.reason_code == "WEEK4_ACTIVATION_PAYLOAD_INVALID"

        activation, conflict = _week4_payloads()
        activation["formula_version"] = "wrong"
        with pytest.raises(GraphPersistenceError) as version_error:
            repo.persist_week4_results(
                run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
            )
        assert version_error.value.reason_code == "WEEK4_ACTIVATION_PAYLOAD_INVALID"

    @pytest.mark.parametrize(
        "field,bad_value,reason",
        [
            ("run_id", "another_run", "WEEK4_RUN_ID_MISMATCH"),
            ("ticker", "QQQ", "WEEK4_TICKER_MISMATCH"),
        ],
    )
    def test_embedded_activation_identity_mismatch_is_rejected(self, field, bad_value, reason):
        _, repo = _engine_and_repo()
        activation, conflict = _week4_payloads()
        activation[field] = bad_value
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_week4_results(
                run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
            )
        assert exc_info.value.reason_code == reason


class TestConflictPersistence:
    def test_all_six_candidate_outcomes_and_admitted_details_are_persisted(self):
        _, repo = _engine_and_repo()
        _, conflict = _persist(repo)
        rows = repo.get_alpha_conflicts("w42_run")
        assert len(rows) == 6
        assert {row["outcome"] for row in rows} == {"admitted", "suppressed", "rejected"}
        admitted = repo.get_alpha_conflicts("w42_run", outcome="admitted")
        assert len(admitted) == conflict["arbitration"]["admitted_count"] == 1
        assert admitted[0]["conflict_json"] == conflict["conflicts"][0]
        assert admitted[0]["conflict_rank"] == 0
        assert admitted[0]["is_main_conflict"] is True
        assert admitted[0]["conflict_score"] is not None
        assert admitted[0]["conflict_level"] in {"low", "medium", "medium_high", "high"}

    def test_suppressed_and_rejected_rows_keep_audit_but_no_conflict_data(self):
        _, repo = _engine_and_repo()
        _persist(repo)
        rows = [row for row in repo.get_alpha_conflicts("w42_run") if row["outcome"] != "admitted"]
        assert rows
        for row in rows:
            assert row["evidence_audit"] == row["candidate_json"]["evidence_audit"]
            assert row["conflict_json"] is None
            assert row["conflict_rank"] is None
            assert row["is_main_conflict"] is False
            assert row["conflict_score"] is None

    def test_pairs_are_canonical_unique_and_a102_a304_is_absent(self):
        _, repo = _engine_and_repo()
        _persist(repo)
        pairs = [(row["alpha_a"], row["alpha_b"]) for row in repo.get_alpha_conflicts("w42_run")]
        assert pairs == sorted(set(pairs))
        assert ("A102", "A304") not in pairs

    def test_unknown_conflict_fields_are_not_persisted(self):
        _, repo = _engine_and_repo()
        activation, conflict = _week4_payloads()
        conflict["arbitration"]["candidate_evaluations"][0]["prompt"] = "must-not-persist"
        conflict["arbitration"]["candidate_evaluations"][0]["evidence_audit"]["alpha_a"][
            "evidence"
        ] = "must-not-persist"
        conflict["conflicts"][0]["provider_response"] = "must-not-persist"
        conflict["conflicts"][0]["bull_structure"]["local_path"] = "/private/must-not-persist"
        conflict["main_conflict"] = copy.deepcopy(conflict["conflicts"][0])
        repo.persist_week4_results(
            run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
        )
        rows = repo.get_alpha_conflicts("w42_run")
        serialized = json.dumps(
            [
                {
                    "candidate_json": row["candidate_json"],
                    "conflict_json": row["conflict_json"],
                    "evidence_audit": row["evidence_audit"],
                }
                for row in rows
            ]
        )
        for forbidden in ("prompt", "provider_response", "local_path", "must-not-persist"):
            assert forbidden not in serialized

    @pytest.mark.parametrize(
        "mutation,expected_reason",
        [
            (lambda payload: payload.update(schema_version="wrong"), "WEEK4_CONFLICT_PAYLOAD_INVALID"),
            (lambda payload: payload.update(formula_version="wrong"), "WEEK4_CONFLICT_PAYLOAD_INVALID"),
            (lambda payload: payload.update(run_id="other"), "WEEK4_RUN_ID_MISMATCH"),
            (lambda payload: payload.update(ticker="QQQ"), "WEEK4_TICKER_MISMATCH"),
            (
                lambda payload: payload["arbitration"].update(declared_pair_count=999),
                "WEEK4_CONFLICT_DATA_INCONSISTENT",
            ),
            (
                lambda payload: payload.update(main_conflict=None),
                "WEEK4_CONFLICT_DATA_INCONSISTENT",
            ),
            (
                lambda payload: payload["arbitration"]["candidate_evaluations"][0][
                    "evidence_audit"
                ]["alpha_a"].update(excluded_count=False),
                "WEEK4_CONFLICT_PAYLOAD_INVALID",
            ),
        ],
        ids=("schema", "formula", "run", "ticker", "count", "main", "boolean-count"),
    )
    def test_invalid_conflict_contract_is_rejected_before_write(self, mutation, expected_reason):
        _, repo = _engine_and_repo()
        activation, conflict = _week4_payloads()
        mutation(conflict)
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_week4_results(
                run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
            )
        assert exc_info.value.reason_code == expected_reason
        assert repo.get_alpha_conflicts("w42_run") == []

    def test_nonstandard_json_in_allowed_fields_is_rejected(self):
        _, repo = _engine_and_repo()
        activation, conflict = _week4_payloads()
        conflict["conflicts"][0]["explanation"] = object()
        conflict["main_conflict"] = conflict["conflicts"][0]
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_week4_results(
                run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
            )
        assert exc_info.value.reason_code == "WEEK4_CONFLICT_PAYLOAD_INVALID"

    def test_outcome_filter_and_unknown_run_contract(self):
        _, repo = _engine_and_repo()
        _persist(repo)
        assert all(row["outcome"] == "suppressed" for row in repo.get_alpha_conflicts("w42_run", outcome="suppressed"))
        assert repo.get_alpha_conflicts("unknown") == []
        assert repo.get_alpha_activations("unknown") == []
        assert repo.get_week4_conflict_result("unknown") is None
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.get_alpha_conflicts("w42_run", outcome="invalid")
        assert exc_info.value.reason_code == "WEEK4_CONFLICT_PAYLOAD_INVALID"


class TestReconstruction:
    def test_w41_payload_round_trips_semantically_exactly(self):
        _, repo = _engine_and_repo()
        _, conflict = _persist(repo)
        reconstructed = repo.get_week4_conflict_result("w42_run")
        assert reconstructed == conflict
        assert reconstructed["main_conflict"] == conflict["main_conflict"]
        assert reconstructed["arbitration"] == conflict["arbitration"]

    def test_no_admitted_conflicts_reconstructs_all_candidate_audit(self):
        _, repo = _engine_and_repo()
        activation = activation_payload()
        conflict = detect_alpha_conflicts(
            run_id="empty_run", ticker="NVDA", activation_payload=activation, alpha_matches=[]
        )
        repo.persist_week4_results(
            run_id="empty_run",
            ticker="NVDA",
            activation_payload=activation,
            conflict_payload=conflict,
        )
        reconstructed = repo.get_week4_conflict_result("empty_run")
        assert reconstructed == conflict
        assert reconstructed["conflicts"] == []
        assert reconstructed["main_conflict"] is None
        assert len(reconstructed["arbitration"]["candidate_evaluations"]) == 6

    @pytest.mark.parametrize(
        "update_values",
        [
            {"is_main_conflict": False},
            {"conflict_rank": 5},
            {"schema_version": "corrupted"},
            {"conflict_json": None},
        ],
        ids=("missing-main", "bad-rank", "schema", "missing-conflict-json"),
    )
    def test_corrupted_database_rows_fail_closed(self, update_values):
        engine, repo = _engine_and_repo()
        _persist(repo)
        with engine.begin() as conn:
            conn.execute(
                sa.update(alpha_conflicts)
                .where(alpha_conflicts.c.outcome == "admitted")
                .values(**update_values)
            )
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.get_week4_conflict_result("w42_run")
        assert exc_info.value.reason_code == "DB_DATA_CORRUPTED"
        assert str(exc_info.value) == "DB_DATA_CORRUPTED"


class TestAtomicReplaceAndIsolation:
    def test_identical_retry_is_idempotent_and_changed_retry_replaces(self):
        _, repo = _engine_and_repo()
        _persist(repo, score=90)
        first = repo.get_week4_conflict_result("w42_run")
        _persist(repo, score=90)
        assert repo.get_week4_conflict_result("w42_run") == first
        assert len(repo.get_alpha_activations("w42_run")) == 7
        assert len(repo.get_alpha_conflicts("w42_run")) == 6

        _persist(repo, score=70)
        assert repo.get_alpha_activations("w42_run")[2]["activation_score"] == 70
        assert len(repo.get_alpha_activations("w42_run")) == 7
        assert len(repo.get_alpha_conflicts("w42_run")) == 6

    @pytest.mark.parametrize("failing_table", ["alpha_activations", "alpha_conflicts"])
    def test_database_failure_rolls_back_both_tables_and_preserves_prior_state(self, failing_table):
        engine, repo = _engine_and_repo()
        _persist(repo, score=90)
        activations_before = repo.get_alpha_activations("w42_run")
        conflicts_before = repo.get_alpha_conflicts("w42_run")
        activation, conflict = _week4_payloads(score=70)

        def fail_insert(_conn, _cursor, statement, _parameters, _context, _executemany):
            if f"insert into {failing_table}" in statement.lower():
                raise sa.exc.OperationalError(statement, {}, RuntimeError("forced"))

        sa.event.listen(engine, "before_cursor_execute", fail_insert)
        try:
            with pytest.raises(GraphPersistenceError) as exc_info:
                repo.persist_week4_results(
                    run_id="w42_run",
                    ticker="NVDA",
                    activation_payload=activation,
                    conflict_payload=conflict,
                )
            assert exc_info.value.reason_code == "DB_WRITE_FAILED"
        finally:
            sa.event.remove(engine, "before_cursor_execute", fail_insert)

        assert repo.get_alpha_activations("w42_run") == activations_before
        assert repo.get_alpha_conflicts("w42_run") == conflicts_before

    def test_validation_failure_preserves_previously_committed_state(self):
        _, repo = _engine_and_repo()
        _persist(repo)
        before = repo.get_week4_conflict_result("w42_run")
        activation, conflict = _week4_payloads(score=70)
        conflict["arbitration"]["admitted_count"] = 999
        with pytest.raises(GraphPersistenceError):
            repo.persist_week4_results(
                run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
            )
        assert repo.get_week4_conflict_result("w42_run") == before

    @pytest.mark.parametrize("same_ticker", [False, True])
    def test_run_isolation_including_same_ticker(self, same_ticker):
        _, repo = _engine_and_repo()
        _persist(repo, run_id="run_a", ticker="NVDA", score=90)
        _persist(repo, run_id="run_b", ticker="NVDA" if same_ticker else "QQQ", score=60)
        run_b_before = repo.get_week4_conflict_result("run_b")
        _persist(repo, run_id="run_a", ticker="NVDA", score=70)
        assert repo.get_week4_conflict_result("run_b") == run_b_before


class TestReadOnlyAndSecurity:
    def test_all_week4_reads_on_missing_sqlite_return_empty_without_creating_file(self, tmp_path):
        repo = build_repository_from_env(output_root=tmp_path)
        assert repo.get_alpha_activations("unknown") == []
        assert repo.get_alpha_conflicts("unknown") == []
        assert repo.get_week4_conflict_result("unknown") is None
        assert not (tmp_path / "_comqutor_alpha_graph.db").exists()

    def test_read_only_week4_methods_never_apply_migrations(self, tmp_path, monkeypatch):
        import comqutor_alpha.storage.db.repository as repository_module

        calls = []
        monkeypatch.setattr(repository_module, "apply_migrations", lambda engine: calls.append(engine))
        repo = build_repository_from_env(output_root=tmp_path)
        repo.get_alpha_activations("unknown")
        repo.get_alpha_conflicts("unknown")
        repo.get_week4_conflict_result("unknown")
        assert calls == []

    def test_errors_expose_only_stable_reason_codes(self):
        _, repo = _engine_and_repo()
        activation, conflict = _week4_payloads()
        activation["alphas"][0]["activation_score"] = float("nan")
        activation["alphas"][0]["evidence"] = ["secret-evidence"]
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_week4_results(
                run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
            )
        assert str(exc_info.value) == "WEEK4_ACTIVATION_PAYLOAD_INVALID"
        for forbidden in ("secret-evidence", "sqlite", ":memory:", "Traceback", "/Users/"):
            assert forbidden not in str(exc_info.value)

    def test_unsupported_dialect_is_rejected(self):
        _, repo = _engine_and_repo()
        object.__setattr__(repo._engine.dialect, "name", "oracle")
        activation, conflict = _week4_payloads()
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_week4_results(
                run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
            )
        assert exc_info.value.reason_code == "UNSUPPORTED_DATABASE_DIALECT"


def test_real_nvda_w41_to_w42_persistence_sanity(tmp_path):
    engine, repo = _engine_and_repo()
    payload = {
        "ticker": "NVDA",
        "analysis_date": "2026-06-30",
        "selected_analysts": ["market", "news", "fundamentals", "sentiment"],
        "offline_raw_agent_outputs": _nvda_offline_outputs(),
    }
    response = run_research_request(payload, output_root=tmp_path, graph_repository=repo)
    run_id = response["run_id"]
    graph = get_persisted_structure_graph(run_id, output_root=tmp_path, graph_repository=repo)
    matches = json.loads((tmp_path / run_id / "alpha_matches.json").read_text(encoding="utf-8"))
    conflict = detect_alpha_conflicts(
        run_id=run_id,
        ticker="NVDA",
        activation_payload=graph["activation"],
        alpha_matches=matches["matches"],
    )
    repo.persist_week4_results(
        run_id=run_id,
        ticker="NVDA",
        activation_payload=graph["activation"],
        conflict_payload=conflict,
    )

    admitted = repo.get_alpha_conflicts(run_id, outcome="admitted")
    a101_a304 = next(row for row in admitted if (row["alpha_a"], row["alpha_b"]) == ("A101", "A304"))
    assert a101_a304["is_main_conflict"] is True
    assert a101_a304["conflict_rank"] == 0
    assert repo.get_week4_conflict_result(run_id) == conflict
    assert repo.get_week4_conflict_result(run_id)["main_conflict"]["conflict_id"] == "A101__A304"
    assert engine.dialect.name == "sqlite"


# ---------------------------------------------------------------------------
# 2026-07-14 W4.2 Correctness Patch: cross-payload snapshot integrity,
# typed recursive component whitelist, and candidate reason-code contract.
# _week4_payloads(score=90) always produces an admitted A101-A304 conflict
# with A101 at index 2 of activation["alphas"] and A304 at index 4 -- both
# used below to construct "stale conflict, fresh activation" mismatches.
# ---------------------------------------------------------------------------


class TestCrossPayloadSnapshotIntegrity:
    def test_mismatch_activation_score_is_rejected(self):
        _, repo = _engine_and_repo()
        activation, conflict = _week4_payloads(score=90)
        activation["alphas"][2]["activation_score"] = 12.0  # A101, was 90
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_week4_results(
                run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
            )
        assert exc_info.value.reason_code == "WEEK4_CONFLICT_DATA_INCONSISTENT"
        assert repo.get_alpha_activations("w42_run") == []
        assert repo.get_alpha_conflicts("w42_run") == []

    def test_mismatch_activation_name_is_rejected(self):
        _, repo = _engine_and_repo()
        activation, conflict = _week4_payloads(score=90)
        activation["alphas"][2]["alpha_name"] = "Mutated Name"  # A101
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_week4_results(
                run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
            )
        assert exc_info.value.reason_code == "WEEK4_CONFLICT_DATA_INCONSISTENT"

    def test_mismatch_activation_status_is_rejected(self):
        _, repo = _engine_and_repo()
        activation, conflict = _week4_payloads(score=90)
        activation["alphas"][2]["status"] = "watch"  # A101, was "active"
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_week4_results(
                run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
            )
        assert exc_info.value.reason_code == "WEEK4_CONFLICT_DATA_INCONSISTENT"

    def test_mismatch_activation_direction_is_rejected(self):
        _, repo = _engine_and_repo()
        activation, conflict = _week4_payloads(score=90)
        activation["alphas"][4]["direction"] = "neutral"  # A304, was "negative"
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_week4_results(
                run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
            )
        assert exc_info.value.reason_code == "WEEK4_CONFLICT_DATA_INCONSISTENT"

    def test_bull_structure_wrong_direction_is_rejected(self):
        _, repo = _engine_and_repo()
        activation, conflict = _week4_payloads(score=90)
        _mutate_admitted_conflict(
            conflict,
            lambda c: {**c, "bull_structure": {**c["bull_structure"], "direction": "negative"}},
        )
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_week4_results(
                run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
            )
        assert exc_info.value.reason_code == "WEEK4_CONFLICT_DATA_INCONSISTENT"

    def test_bear_structure_wrong_direction_is_rejected(self):
        _, repo = _engine_and_repo()
        activation, conflict = _week4_payloads(score=90)
        _mutate_admitted_conflict(
            conflict,
            lambda c: {**c, "bear_structure": {**c["bear_structure"], "direction": "positive"}},
        )
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_week4_results(
                run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
            )
        assert exc_info.value.reason_code == "WEEK4_CONFLICT_DATA_INCONSISTENT"

    def test_admitted_conflict_missing_activation_side_is_rejected(self):
        _, repo = _engine_and_repo()
        activation, conflict = _week4_payloads(score=90)
        activation["alphas"] = [a for a in activation["alphas"] if a["alpha_id"] != "A304"]
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_week4_results(
                run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
            )
        assert exc_info.value.reason_code == "WEEK4_CONFLICT_DATA_INCONSISTENT"
        assert repo.get_alpha_activations("w42_run") == []

    def test_mixed_snapshot_with_matching_identity_fields_is_still_rejected(self):
        _, repo = _engine_and_repo()
        activation, conflict = _week4_payloads(score=90)
        # run_id/ticker/version all agree between the two payloads -- only
        # the underlying numeric snapshot disagrees.
        assert conflict["run_id"] == "w42_run"
        assert conflict["ticker"] == "NVDA"
        assert activation["formula_version"] == ACTIVATION_FORMULA_VERSION
        activation["alphas"][2]["activation_score"] = 5.0  # A101
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_week4_results(
                run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
            )
        assert exc_info.value.reason_code == "WEEK4_CONFLICT_DATA_INCONSISTENT"

    def test_mixed_snapshot_validation_preserves_prior_committed_state(self):
        _, repo = _engine_and_repo()
        _persist(repo, score=90)
        before = repo.get_week4_conflict_result("w42_run")
        activation, conflict = _week4_payloads(score=90)
        activation["alphas"][2]["activation_score"] = 5.0  # A101
        with pytest.raises(GraphPersistenceError):
            repo.persist_week4_results(
                run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
            )
        assert repo.get_week4_conflict_result("w42_run") == before

    def test_mixed_snapshot_validation_happens_before_any_sql_execution(self):
        engine, repo = _engine_and_repo()
        activation, conflict = _week4_payloads(score=90)
        activation["alphas"][2]["activation_score"] = 5.0  # A101

        executed_statements: list[str] = []

        def spy(_conn, _cursor, statement, _parameters, _context, _executemany):
            executed_statements.append(statement)

        sa.event.listen(engine, "before_cursor_execute", spy)
        try:
            with pytest.raises(GraphPersistenceError) as exc_info:
                repo.persist_week4_results(
                    run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
                )
            assert exc_info.value.reason_code == "WEEK4_CONFLICT_DATA_INCONSISTENT"
        finally:
            sa.event.remove(engine, "before_cursor_execute", spy)
        assert executed_statements == []  # validation failed before any SQL was issued


class TestTypedRecursiveActivationWhitelist:
    def _persist_with_components(self, components):
        _, repo = _engine_and_repo()
        activation, conflict = _week4_payloads()
        activation["alphas"][2]["components"] = components  # A101
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_week4_results(
                run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
            )
        assert exc_info.value.reason_code == "WEEK4_ACTIVATION_PAYLOAD_INVALID"
        assert repo.get_alpha_activations("w42_run") == []
        return repo

    def test_recency_reason_nested_dict_is_rejected(self):
        self._persist_with_components({"recency": {"reason": {"nested": "dict"}}})

    def test_agent_agreement_agents_with_nested_dict_is_rejected(self):
        self._persist_with_components({"agent_agreement": {"agents": [{"nested": "dict"}]}})

    def test_graph_coherence_scope_nested_dict_is_rejected(self):
        self._persist_with_components({"graph_coherence": {"scope": {"nested": "dict"}}})

    def test_bool_field_as_string_is_rejected(self):
        self._persist_with_components({"graph_coherence": {"evidence_gated": "true"}})

    def test_numeric_field_as_nested_object_is_rejected(self):
        self._persist_with_components({"matched_evidence": {"raw": {"nested": "object"}}})

    def test_integer_field_as_bool_is_rejected(self):
        self._persist_with_components({"agent_agreement": {"distinct_agents": True}})

    def test_recency_age_days_as_nan_is_rejected(self):
        self._persist_with_components({"recency": {"age_days": float("nan")}})

    def test_direction_strength_average_signed_strength_as_list_is_rejected(self):
        self._persist_with_components({"direction_strength": {"average_signed_strength": [0.5]}})

    def test_matched_evidence_saturation_must_be_positive(self):
        self._persist_with_components({"matched_evidence": {"saturation": 0.0}})

    def test_real_week3_activation_components_round_trip(self, tmp_path):
        _, repo = _engine_and_repo()
        payload = {
            "ticker": "NVDA",
            "analysis_date": "2026-06-30",
            "selected_analysts": ["market", "news", "fundamentals", "sentiment"],
            "offline_raw_agent_outputs": _nvda_offline_outputs(),
        }
        response = run_research_request(payload, output_root=tmp_path, graph_repository=repo)
        run_id = response["run_id"]
        graph = get_persisted_structure_graph(run_id, output_root=tmp_path, graph_repository=repo)
        matches = json.loads((tmp_path / run_id / "alpha_matches.json").read_text(encoding="utf-8"))
        conflict = detect_alpha_conflicts(
            run_id=run_id,
            ticker="NVDA",
            activation_payload=graph["activation"],
            alpha_matches=matches["matches"],
        )
        repo.persist_week4_results(
            run_id=run_id, ticker="NVDA", activation_payload=graph["activation"], conflict_payload=conflict
        )
        row = next(r for r in repo.get_alpha_activations(run_id) if r["alpha_id"] == "A101")
        components = row["activation_json"]["components"]
        assert components  # A101 has real evidence in this fixture
        assert set(components) <= {
            "matched_evidence",
            "agent_agreement",
            "graph_coherence",
            "recency",
            "direction_strength",
        }
        for component in components.values():
            assert isinstance(component, dict)
            for key in ("raw", "weight", "contribution"):
                if key in component:
                    assert isinstance(component[key], (int, float))
                    assert not isinstance(component[key], bool)


class TestCandidateReasonCodeContract:
    def test_suppressed_candidate_with_empty_reason_codes_is_rejected(self):
        _, repo = _engine_and_repo()
        activation, conflict = _week4_payloads()
        suppressed = next(
            c for c in conflict["arbitration"]["candidate_evaluations"] if c["outcome"] == "suppressed"
        )
        suppressed["reason_codes"] = []
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_week4_results(
                run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
            )
        assert exc_info.value.reason_code == "WEEK4_CONFLICT_DATA_INCONSISTENT"

    def test_rejected_candidate_with_empty_reason_codes_is_rejected(self):
        _, repo = _engine_and_repo()
        activation, conflict = _week4_payloads()
        rejected = next(
            c for c in conflict["arbitration"]["candidate_evaluations"] if c["outcome"] == "rejected"
        )
        rejected["reason_codes"] = []
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_week4_results(
                run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
            )
        assert exc_info.value.reason_code == "WEEK4_CONFLICT_DATA_INCONSISTENT"

    def test_duplicate_reason_code_on_a_candidate_is_rejected(self):
        _, repo = _engine_and_repo()
        activation, conflict = _week4_payloads()
        suppressed = next(
            c for c in conflict["arbitration"]["candidate_evaluations"] if c["outcome"] == "suppressed"
        )
        suppressed["reason_codes"] = [suppressed["reason_codes"][0], suppressed["reason_codes"][0]]
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_week4_results(
                run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
            )
        assert exc_info.value.reason_code == "WEEK4_CONFLICT_DATA_INCONSISTENT"

    def test_duplicate_qualifying_claim_id_in_evidence_audit_is_rejected(self):
        _, repo = _engine_and_repo()
        activation, conflict = _week4_payloads()
        admitted = next(
            c for c in conflict["arbitration"]["candidate_evaluations"] if c["outcome"] == "admitted"
        )
        side = admitted["evidence_audit"]["alpha_a"]
        assert side["qualifying_claim_ids"]  # A101 has c101 as qualifying evidence
        side["qualifying_claim_ids"] = side["qualifying_claim_ids"] * 2
        side["qualifying_count"] = len(side["qualifying_claim_ids"])
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_week4_results(
                run_id="w42_run", ticker="NVDA", activation_payload=activation, conflict_payload=conflict
            )
        assert exc_info.value.reason_code == "WEEK4_CONFLICT_DATA_INCONSISTENT"
