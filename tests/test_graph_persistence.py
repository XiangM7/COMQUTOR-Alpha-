import json

import pytest
import sqlalchemy as sa

from comqutor_alpha.storage.db.engine import (
    DatabaseConfigurationError,
    build_engine,
    resolve_database_url,
)
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import (
    GraphPersistenceError,
    GraphPersistenceRepository,
    build_repository_from_env,
    build_write_repository_from_env,
)
from comqutor_alpha.storage.db.schema import alpha_matches, structure_graphs


def _fresh_repository():
    # GraphPersistenceRepository's constructor no longer applies migrations
    # itself (that is now write-path-only, via ensure_schema()/
    # build_write_repository_from_env) -- tests that build a repo directly
    # and expect a ready schema must apply it explicitly.
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


def _alpha_matches_payload(claim_id="c1", alpha_id="A101", agent="news_agent"):
    return {
        "schema_version": "week2.alpha_matches.v2",
        "run_id": "r1",
        "ticker": "NVDA",
        "matches": [
            {
                "claim_id": claim_id,
                "source_agent_output_id": f"o_{claim_id}",
                "agent": agent,
                "match_status": "matched",
                "matched_alpha": alpha_id,
                "matched_alpha_name": "AI Expansion",
                "score": 0.8,
                "direction": "positive",
                "assertion_status": "asserted",
                "semantic_polarity": "activation",
                "claim": "AI demand is strong.",
                "evidence": "AI demand is strong.",
                "reason": "top eligible alpha",
                "candidate_scores": [{"alpha_id": alpha_id, "score": 0.8}],
            }
        ],
    }


def _graph_payload(run_id="r1", ticker="NVDA", score=42.0):
    return {
        "schema_version": "week3.structure_graph.v1",
        "graph_builder_version": "week3.graph_builder.v1",
        "activation_scorer_version": "week3.activation_scorer.v1",
        "run_id": run_id,
        "ticker": ticker,
        "nodes": [],
        "edges": [],
        "graph_metrics": {},
        "graph_coherence": {"score": score, "valid_edges": 1, "alpha_covered_count": 1},
        "activation": {"alphas": []},
        "dominant_alphas": [],
        "provenance": {},
    }


class TestSchema:
    def test_alpha_matches_table_has_required_logical_fields(self):
        columns = set(alpha_matches.columns.keys())
        required = {
            "id",
            "run_id",
            "ticker",
            "claim_id",
            "source_agent_output_id",
            "agent",
            "alpha_id",
            "match_score",
            "match_status",
            "direction",
            "evidence",
            "created_at",
        }
        assert required.issubset(columns)
        assert alpha_matches.c.id.primary_key

    def test_structure_graphs_table_has_required_logical_fields(self):
        columns = set(structure_graphs.columns.keys())
        required = {
            "id",
            "run_id",
            "ticker",
            "graph_json",
            "graph_coherence_score",
            "schema_version",
            "created_at",
            "updated_at",
        }
        assert required.issubset(columns)
        assert structure_graphs.c.id.primary_key


class TestPersistence:
    def test_match_persistence_round_trips_claim_and_source_output_identity(self):
        repo = _fresh_repository()
        payload = _alpha_matches_payload()

        repo.persist_run(run_id="r1", ticker="NVDA", alpha_matches_payload=payload, graph_payload=_graph_payload())

        rows = repo.get_alpha_matches("r1")
        assert len(rows) == 1
        assert rows[0]["claim_id"] == "c1"
        assert rows[0]["source_agent_output_id"] == "o_c1"
        assert rows[0]["alpha_id"] == "A101"
        assert rows[0]["match_status"] == "matched"

    def test_only_matched_rows_carry_a_committed_alpha_id(self):
        repo = _fresh_repository()
        payload = _alpha_matches_payload()
        payload["matches"].append(
            {
                "claim_id": "c2",
                "source_agent_output_id": "o_c2",
                "agent": "news_agent",
                "match_status": "no_match",
                "matched_alpha": None,
                "score": 0.1,
                "claim": "irrelevant claim",
                "evidence": "irrelevant claim",
            }
        )

        repo.persist_run(run_id="r1", ticker="NVDA", alpha_matches_payload=payload, graph_payload=_graph_payload())

        rows = {row["claim_id"]: row for row in repo.get_alpha_matches("r1")}
        assert rows["c1"]["alpha_id"] == "A101"
        assert rows["c2"]["match_status"] == "no_match"
        assert rows["c2"]["alpha_id"] is None  # no_match must never masquerade as committed

    def test_graph_json_persists_and_round_trips_exactly(self):
        repo = _fresh_repository()
        graph_payload = _graph_payload(score=77.5)

        repo.persist_run(
            run_id="r1", ticker="NVDA", alpha_matches_payload=_alpha_matches_payload(), graph_payload=graph_payload
        )

        row = repo.get_graph("r1")
        assert row["graph_json"] == graph_payload
        assert row["graph_coherence_score"] == 77.5
        assert row["schema_version"] == "week3.structure_graph.v1"

    def test_repeated_persist_of_same_run_is_idempotent(self):
        repo = _fresh_repository()
        payload = _alpha_matches_payload()
        graph_payload = _graph_payload()

        repo.persist_run(run_id="r1", ticker="NVDA", alpha_matches_payload=payload, graph_payload=graph_payload)
        repo.persist_run(run_id="r1", ticker="NVDA", alpha_matches_payload=payload, graph_payload=graph_payload)

        assert len(repo.get_alpha_matches("r1")) == 1  # no duplicate rows
        assert repo.get_graph("r1")["graph_json"] == graph_payload

    def test_retry_with_changed_claim_set_replaces_rather_than_accumulates(self):
        repo = _fresh_repository()
        repo.persist_run(
            run_id="r1", ticker="NVDA", alpha_matches_payload=_alpha_matches_payload("c1"), graph_payload=_graph_payload()
        )
        repo.persist_run(
            run_id="r1", ticker="NVDA", alpha_matches_payload=_alpha_matches_payload("c2"), graph_payload=_graph_payload()
        )

        rows = repo.get_alpha_matches("r1")
        assert [row["claim_id"] for row in rows] == ["c2"]

    def test_run_isolation_across_separate_run_ids(self):
        repo = _fresh_repository()
        repo.persist_run(
            run_id="r1",
            ticker="NVDA",
            alpha_matches_payload=_alpha_matches_payload("c1", alpha_id="A101"),
            graph_payload=_graph_payload(run_id="r1", ticker="NVDA", score=10.0),
        )
        repo.persist_run(
            run_id="r2",
            ticker="QQQ",
            alpha_matches_payload=_alpha_matches_payload("c9", alpha_id="A001"),
            graph_payload=_graph_payload(run_id="r2", ticker="QQQ", score=90.0),
        )

        assert repo.get_graph("r1")["ticker"] == "NVDA"
        assert repo.get_graph("r1")["graph_coherence_score"] == 10.0
        assert repo.get_graph("r2")["ticker"] == "QQQ"
        assert repo.get_graph("r2")["graph_coherence_score"] == 90.0
        assert [row["claim_id"] for row in repo.get_alpha_matches("r1")] == ["c1"]
        assert [row["claim_id"] for row in repo.get_alpha_matches("r2")] == ["c9"]

    def test_run_isolation_holds_even_when_two_runs_share_the_same_ticker(self):
        """test_run_isolation_across_separate_run_ids uses two different
        tickers, which leaves open whether isolation actually keys off
        run_id or could be accidentally bypassed via ticker. This pins down
        that ticker is never a substitute lookup key: two runs for the
        *same* ticker must stay just as isolated as two runs for different
        tickers."""
        repo = _fresh_repository()
        repo.persist_run(
            run_id="r1",
            ticker="NVDA",
            alpha_matches_payload=_alpha_matches_payload("c1", alpha_id="A101"),
            graph_payload=_graph_payload(run_id="r1", ticker="NVDA", score=10.0),
        )
        repo.persist_run(
            run_id="r2",
            ticker="NVDA",
            alpha_matches_payload=_alpha_matches_payload("c9", alpha_id="A001"),
            graph_payload=_graph_payload(run_id="r2", ticker="NVDA", score=90.0),
        )

        assert repo.get_graph("r1")["graph_coherence_score"] == 10.0
        assert repo.get_graph("r2")["graph_coherence_score"] == 90.0
        assert [row["claim_id"] for row in repo.get_alpha_matches("r1")] == ["c1"]
        assert [row["claim_id"] for row in repo.get_alpha_matches("r2")] == ["c9"]

        # retrying r1 must never touch r2's rows/graph just because they
        # share a ticker
        repo.persist_run(
            run_id="r1",
            ticker="NVDA",
            alpha_matches_payload=_alpha_matches_payload("c1", alpha_id="A301"),
            graph_payload=_graph_payload(run_id="r1", ticker="NVDA", score=15.0),
        )
        assert repo.get_graph("r2")["graph_coherence_score"] == 90.0
        assert [row["claim_id"] for row in repo.get_alpha_matches("r2")] == ["c9"]

    def test_query_by_run_id_returns_none_for_unknown_run(self):
        repo = _fresh_repository()
        assert repo.get_graph("never_persisted") is None
        assert repo.get_alpha_matches("never_persisted") == []

    def test_graph_schema_and_version_metadata_round_trip(self):
        repo = _fresh_repository()
        graph_payload = _graph_payload()
        repo.persist_run(run_id="r1", ticker="NVDA", alpha_matches_payload=_alpha_matches_payload(), graph_payload=graph_payload)

        row = repo.get_graph("r1")
        assert row["schema_version"] == graph_payload["schema_version"]
        assert row["graph_json"]["graph_builder_version"] == graph_payload["graph_builder_version"]
        assert row["graph_json"]["activation_scorer_version"] == graph_payload["activation_scorer_version"]

    def test_failed_write_rolls_back_and_leaves_prior_state_intact(self):
        repo = _fresh_repository()
        good_payload = _alpha_matches_payload("c1", alpha_id="A101")
        good_graph = _graph_payload(score=10.0)
        repo.persist_run(run_id="r1", ticker="NVDA", alpha_matches_payload=good_payload, graph_payload=good_graph)

        rows_before = repo.get_alpha_matches("r1")
        graph_before = repo.get_graph("r1")

        # ticker is NOT NULL on structure_graphs; forcing None triggers a real
        # constraint violation partway through the same transaction that also
        # replaces alpha_matches rows.
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_run(
                run_id="r1",
                ticker=None,
                alpha_matches_payload=_alpha_matches_payload("c2", alpha_id="A301"),
                graph_payload=_graph_payload(score=99.0),
            )
        assert exc_info.value.reason_code == "DB_WRITE_FAILED"

        assert repo.get_alpha_matches("r1") == rows_before
        assert repo.get_graph("r1") == graph_before

    @pytest.mark.parametrize(
        "bad_score", [float("nan"), float("inf"), -0.1, 1.1, "0.8", True]
    )
    def test_invalid_alpha_match_score_is_rejected(self, bad_score):
        repo = _fresh_repository()
        payload = _alpha_matches_payload()
        payload["matches"][0]["score"] = bad_score

        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_run(
                run_id="r1",
                ticker="NVDA",
                alpha_matches_payload=payload,
                graph_payload=_graph_payload(),
            )

        assert exc_info.value.reason_code == "ALPHA_MATCHES_PAYLOAD_INVALID"
        assert repo.get_alpha_matches("r1") == []

    @pytest.mark.parametrize(
        "bad_score", [float("nan"), float("inf"), -0.1, 100.1, "42", True]
    )
    def test_invalid_graph_coherence_score_is_rejected(self, bad_score):
        repo = _fresh_repository()

        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_run(
                run_id="r1",
                ticker="NVDA",
                alpha_matches_payload=_alpha_matches_payload(),
                graph_payload=_graph_payload(score=bad_score),
            )

        assert exc_info.value.reason_code == "STRUCTURE_GRAPH_PAYLOAD_INVALID"
        assert repo.get_graph("r1") is None

    def test_migrations_are_idempotent_to_reapply(self):
        from comqutor_alpha.storage.db.migrations import apply_migrations

        engine = build_engine("sqlite:///:memory:")
        first = apply_migrations(engine)
        second = apply_migrations(engine)
        assert first  # applied something the first time
        assert second == []  # nothing new the second time

    def test_unsupported_dialect_is_rejected_explicitly(self):
        repo = _fresh_repository()
        object.__setattr__(repo._engine.dialect, "name", "oracle")
        with pytest.raises(GraphPersistenceError) as exc_info:
            repo.persist_run(
                run_id="r1", ticker="NVDA", alpha_matches_payload=_alpha_matches_payload(), graph_payload=_graph_payload()
            )
        assert exc_info.value.reason_code == "UNSUPPORTED_DATABASE_DIALECT"

    def test_persistence_error_never_carries_dsn_or_raw_exception_text(self):
        repo = _fresh_repository()
        try:
            repo.persist_run(
                run_id="r1",
                ticker=None,
                alpha_matches_payload=_alpha_matches_payload(),
                graph_payload=_graph_payload(),
            )
        except GraphPersistenceError as exc:
            assert str(exc) == exc.reason_code
            assert "sqlite" not in str(exc).lower()
            assert ":memory:" not in str(exc)


class TestReadWriteRepositoryConstruction:
    """build_repository_from_env (read-only) vs build_write_repository_from_env
    (write, provisions schema) is the split that keeps GET /api/research/
    {run_id}/graph from ever running a migration or creating a local SQLite
    file -- see routes_research.get_persisted_structure_graph, which only
    ever calls the read-only factory."""
    @pytest.fixture(autouse=True)
    def _force_sqlite_fallback(self, monkeypatch):
        monkeypatch.delenv("COMQUTOR_DATABASE_URL", raising=False)
        monkeypatch.delenv("COMQUTOR_ENV", raising=False)

    def test_write_repository_provisions_schema_and_can_persist_immediately(self, tmp_path):
        repo = build_write_repository_from_env(output_root=tmp_path)

        repo.persist_run(
            run_id="r1", ticker="NVDA", alpha_matches_payload=_alpha_matches_payload(), graph_payload=_graph_payload()
        )

        assert repo.get_graph("r1") is not None
        assert (tmp_path / "_comqutor_alpha_graph.db").exists()

    def test_read_only_repository_creates_no_file_and_no_schema_for_unwritten_root(self, tmp_path):
        repo = build_repository_from_env(output_root=tmp_path)

        assert repo.get_graph("never_persisted") is None
        assert repo.get_alpha_matches("never_persisted") == []
        assert not (tmp_path / "_comqutor_alpha_graph.db").exists()

    def test_read_only_repository_sees_what_the_write_repository_persisted(self, tmp_path):
        writer = build_write_repository_from_env(output_root=tmp_path)
        writer.persist_run(
            run_id="r1", ticker="NVDA", alpha_matches_payload=_alpha_matches_payload(), graph_payload=_graph_payload(score=55.0)
        )

        reader = build_repository_from_env(output_root=tmp_path)
        row = reader.get_graph("r1")

        assert row is not None
        assert row["graph_coherence_score"] == 55.0

    def test_read_only_repository_constructor_never_calls_apply_migrations(self, tmp_path, monkeypatch):
        import comqutor_alpha.storage.db.repository as repository_module

        calls = []
        monkeypatch.setattr(repository_module, "apply_migrations", lambda engine: calls.append(engine))

        build_repository_from_env(output_root=tmp_path).get_graph("anything")

        assert calls == []


class TestProductionDatabaseFallback:
    """COMQUTOR_ENV=production must never silently persist to a local
    SQLite file: a missing COMQUTOR_DATABASE_URL is a configuration error in
    production, not a "just use SQLite" default. Development/tests are
    unaffected."""

    def test_production_without_database_url_raises_safely(self, monkeypatch, tmp_path):
        monkeypatch.setenv("COMQUTOR_ENV", "production")
        monkeypatch.delenv("COMQUTOR_DATABASE_URL", raising=False)

        with pytest.raises(DatabaseConfigurationError) as exc_info:
            resolve_database_url(output_root=tmp_path)

        assert exc_info.value.reason_code == "PRODUCTION_DATABASE_URL_REQUIRED"
        assert str(exc_info.value) == "PRODUCTION_DATABASE_URL_REQUIRED"
        assert str(tmp_path) not in str(exc_info.value)
        assert "sqlite" not in str(exc_info.value).lower()

    def test_production_without_database_url_creates_no_local_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("COMQUTOR_ENV", "production")
        monkeypatch.delenv("COMQUTOR_DATABASE_URL", raising=False)

        with pytest.raises(DatabaseConfigurationError):
            resolve_database_url(output_root=tmp_path)

        assert list(tmp_path.iterdir()) == []  # no silent sqlite fallback file, no directory created

    def test_production_with_database_url_uses_it_directly_not_sqlite(self, monkeypatch, tmp_path):
        monkeypatch.setenv("COMQUTOR_ENV", "production")
        monkeypatch.setenv("COMQUTOR_DATABASE_URL", "postgresql+psycopg://user:pass@db.internal/comqutor")

        url = resolve_database_url(output_root=tmp_path)

        assert url == "postgresql+psycopg://user:pass@db.internal/comqutor"

    def test_non_production_without_database_url_still_falls_back_to_sqlite(self, monkeypatch, tmp_path):
        monkeypatch.delenv("COMQUTOR_ENV", raising=False)
        monkeypatch.delenv("COMQUTOR_DATABASE_URL", raising=False)

        url = resolve_database_url(output_root=tmp_path)

        assert url.startswith("sqlite:///")
        assert str(tmp_path) in url

    def test_build_repository_from_env_wraps_production_config_error(self, monkeypatch, tmp_path):
        monkeypatch.setenv("COMQUTOR_ENV", "production")
        monkeypatch.delenv("COMQUTOR_DATABASE_URL", raising=False)

        with pytest.raises(GraphPersistenceError) as exc_info:
            build_repository_from_env(output_root=tmp_path)

        assert exc_info.value.reason_code == "PRODUCTION_DATABASE_URL_REQUIRED"
        assert str(tmp_path) not in str(exc_info.value)

    def test_week3_pipeline_degrades_safely_in_production_without_database_url(self, monkeypatch, tmp_path):
        """End-to-end: Week 1-2 artifacts already exist on disk; processed
        with COMQUTOR_ENV=production, no COMQUTOR_DATABASE_URL, and no
        injected repository (the real default-resolution path). Must
        degrade safely (graph construction/scoring still run since they
        need no DB; persistence fails safely) rather than crash or fall
        back to SQLite."""
        import comqutor_alpha.api.routes_research as routes_research

        run_id = "prod_no_dsn_run"
        run_dir = tmp_path / run_id
        run_dir.mkdir()
        (run_dir / "metadata.json").write_text(
            json.dumps({"run_id": run_id, "ticker": "NVDA", "analysis_date": "2026-06-30"}), encoding="utf-8"
        )
        (run_dir / "alpha_matches.json").write_text(
            json.dumps({"run_id": run_id, "ticker": "NVDA", "matches": []}), encoding="utf-8"
        )
        (run_dir / "extracted_structures.json").write_text(
            json.dumps({"run_id": run_id, "ticker": "NVDA", "nodes": [], "edges": []}), encoding="utf-8"
        )

        monkeypatch.setenv("COMQUTOR_ENV", "production")
        monkeypatch.delenv("COMQUTOR_DATABASE_URL", raising=False)

        routes_research._run_week3_graph_pipeline(run_dir)

        assert (run_dir / "structure_graph.json").exists()  # construction/scoring need no DB
        assert (run_dir / "error_logs" / "week3_pipeline_errors.jsonl").exists()
        assert not list(tmp_path.glob("**/_comqutor_alpha_graph.db"))  # no silent sqlite fallback

        graph = routes_research.get_persisted_structure_graph(run_id, output_root=tmp_path)
        assert graph["status"] == "failed"
        assert graph["error_code"] == "GRAPH_UNAVAILABLE"
        serialized = json.dumps(graph)
        assert str(tmp_path) not in serialized
        assert "postgresql" not in serialized
        assert "sqlite" not in serialized.lower()


class TestAlphaMatchesCardinality:
    """Confirms and locks in the actual persistence semantics: alpha_matches
    stores exactly one row per structured claim (the primary/committed
    decision for that claim -- matched, ambiguous, or no_match), never one
    row per candidate Alpha. Secondary/plausible candidates for an ambiguous
    or matched claim remain visible in that single row's own
    ``candidate_scores`` JSON column (and in the graph's
    ``ambiguous_alpha_ids`` provenance) rather than being promoted to
    additional committed database rows. The UNIQUE(run_id, claim_id)
    constraint is aligned with this: it is *not*
    UNIQUE(run_id, claim_id, alpha_id), because there is never more than one
    committed alpha_id for a given claim in this schema."""

    def test_unique_constraint_is_run_id_claim_id_only(self):
        unique_constraints = [c for c in alpha_matches.constraints if isinstance(c, sa.UniqueConstraint)]
        assert len(unique_constraints) == 1
        assert {col.name for col in unique_constraints[0].columns} == {"run_id", "claim_id"}

    def test_one_row_per_claim_regardless_of_candidate_count(self):
        repo = _fresh_repository()
        payload = {
            "run_id": "r1",
            "ticker": "NVDA",
            "matches": [
                {
                    "claim_id": "c1",
                    "source_agent_output_id": "o_c1",
                    "agent": "news_agent",
                    "match_status": "ambiguous",
                    "matched_alpha": None,
                    "score": 0.5,
                    "claim": "AI demand is strong but rich valuation creates downside risk.",
                    "evidence": "AI demand is strong but rich valuation creates downside risk.",
                    "plausible_alphas": ["A101", "A304"],
                    "candidate_scores": [
                        {"alpha_id": "A101", "score": 0.5, "relation": "activation"},
                        {"alpha_id": "A304", "score": 0.48, "relation": "activation"},
                    ],
                },
            ],
        }

        repo.persist_run(run_id="r1", ticker="NVDA", alpha_matches_payload=payload, graph_payload=_graph_payload())

        rows = repo.get_alpha_matches("r1")

        assert len(rows) == 1  # one row for this claim, not one per plausible candidate
        assert rows[0]["match_status"] == "ambiguous"
        assert rows[0]["alpha_id"] is None  # ambiguous never masquerades as a committed alpha_id

        # Secondary/plausible candidates are preserved in the JSON column of
        # that same row, not promoted to extra committed rows.
        candidate_ids = {c["alpha_id"] for c in rows[0]["candidate_scores"]}
        assert candidate_ids == {"A101", "A304"}

    def test_matched_claim_with_secondary_alphas_still_persists_one_row(self):
        repo = _fresh_repository()
        payload = {
            "run_id": "r1",
            "ticker": "NVDA",
            "matches": [
                {
                    "claim_id": "c1",
                    "source_agent_output_id": "o_c1",
                    "agent": "news_agent",
                    "match_status": "matched",
                    "matched_alpha": "A101",
                    "matched_alpha_name": "AI Expansion",
                    "score": 0.8,
                    "claim": "AI training demand is accelerating.",
                    "evidence": "AI training demand is accelerating.",
                    "secondary_alphas": ["A301"],
                    "candidate_scores": [
                        {"alpha_id": "A101", "score": 0.8, "relation": "activation"},
                        {"alpha_id": "A301", "score": 0.6, "relation": "activation"},
                    ],
                },
            ],
        }

        repo.persist_run(run_id="r1", ticker="NVDA", alpha_matches_payload=payload, graph_payload=_graph_payload())

        rows = repo.get_alpha_matches("r1")

        assert len(rows) == 1
        assert rows[0]["alpha_id"] == "A101"  # only the committed match becomes the row's alpha_id
        candidate_ids = {c["alpha_id"] for c in rows[0]["candidate_scores"]}
        assert "A301" in candidate_ids  # secondary candidate preserved in JSON, not a second row
