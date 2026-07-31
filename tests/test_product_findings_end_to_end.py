"""Product Findings Closure Sprint: raw-output -> Adapter -> unified claim
quality gate -> persistence boundary -> repository read -> live FastAPI
Agent Findings route -> API payload, exercised end to end through the real
research pipeline (spec section 5).

No Provider/LLM/network call anywhere: the pipeline runs entirely through
``offline_raw_agent_outputs`` (same offline harness ``test_graph_api.py``
and friends already use) with the deterministic splitter path
(``llm_gateway=None`` inside the adapter whenever a Week2 LLM gateway is not
configured in this test environment).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import sqlalchemy as sa

from comqutor_alpha.api.agent_output_reader import get_agent_outputs_response
from comqutor_alpha.api.routes_research import run_research_request
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from comqutor_alpha.storage.db.schema import agent_outputs

_PROCESS_LANGUAGE_SENTENCES = (
    "I now have all the data needed.",
    "Let me synthesize everything.",
    "I will now compile the final report.",
    "Here is the comprehensive analysis.",
)
_ANALYTICAL_SENTENCES = (
    "Revenue declined 12% year over year.",
    "AI demand supports revenue growth.",
)
_CONTEXT_ONLY_SENTENCE = "The company introduced a new storage product."


def _repo():
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return engine, GraphPersistenceRepository(engine)


def _raw_output_text() -> str:
    return " ".join(
        _PROCESS_LANGUAGE_SENTENCES + _ANALYTICAL_SENTENCES + (_CONTEXT_ONLY_SENTENCE,)
    )


def test_raw_output_to_live_api_full_chain(tmp_path):
    """The exact chain spec section 5 requires: raw_agent_outputs ->
    structured_output_adapter -> unified claim quality gate -> persistence
    boundary -> repository read -> live FastAPI Agent Findings route -> API
    payload -- checked at every stage in one real run."""
    engine, repo = _repo()
    payload = {
        "ticker": "NVDA",
        "analysis_date": "2026-06-30",
        "offline_raw_agent_outputs": [
            {"agent": "news_agent", "raw_output": _raw_output_text()},
        ],
    }
    response = run_research_request(payload, output_root=tmp_path, graph_repository=repo)
    assert response["status"] == "completed"
    run_id = response["run_id"]

    # Stage 1: raw artifact retains every process-language sentence --
    # auditable, never scrubbed from the raw transcript.
    raw_payload = json.loads((tmp_path / run_id / "raw_agent_outputs.json").read_text())
    raw_text = json.dumps(raw_payload)
    for sentence in _PROCESS_LANGUAGE_SENTENCES:
        assert sentence in raw_text

    # Stage 2: the unified claim quality gate, applied inside the adapter.
    # Formal structured artifact contains exactly the 3 substantive claims,
    # each tagged with its quality class; none of the process-language
    # sentences appear at all.
    structured = json.loads((tmp_path / run_id / "structured_agent_outputs.json").read_text())
    quality_by_claim = {r["claim"]: r["claim_quality"] for r in structured["records"]}
    for sentence in _PROCESS_LANGUAGE_SENTENCES:
        assert sentence not in quality_by_claim
    for sentence in _ANALYTICAL_SENTENCES:
        assert quality_by_claim[sentence] == "analytical"
    assert quality_by_claim[_CONTEXT_ONLY_SENTENCE] == "context_only"

    # Stage 3: persistence admission boundary. Process language never
    # reaches the database; analytical AND context_only both persist
    # (analytical_persistence eligibility allows both, tagged context_only).
    db_claims = {row["claim"] for row in repo.list_agent_outputs(run_id)}
    for sentence in _PROCESS_LANGUAGE_SENTENCES:
        assert sentence not in db_claims
    for sentence in _ANALYTICAL_SENTENCES:
        assert sentence in db_claims
    assert _CONTEXT_ONLY_SENTENCE in db_claims

    # Stage 4: the live FastAPI Agent Findings route (DB-first read path).
    # Only the 2 analytical claims are shown; context_only is persisted
    # (for Mapper/analytical_persistence) but hidden here by default; process
    # language never appears anywhere in the API payload.
    api_result = get_agent_outputs_response(run_id, output_root=tmp_path, graph_repository=repo)
    assert api_result["status"] == "ok"
    api_claims = {r["claim"] for r in api_result["structured_agent_outputs"]}
    assert api_claims == set(_ANALYTICAL_SENTENCES)
    assert api_result["count"] == 2
    for sentence in _PROCESS_LANGUAGE_SENTENCES:
        assert sentence not in api_claims
    assert _CONTEXT_ONLY_SENTENCE not in api_claims

    # No internal quality-gate vocabulary (reason codes, the claim_quality
    # field itself) ever reaches the public API payload.
    serialized = json.dumps(api_result)
    assert "claim_quality" not in serialized
    assert "BOILERPLATE_META_COMMENTARY" not in serialized
    assert "reason_code" not in serialized


def _insert_legacy_row(
    engine,
    *,
    run_id: str,
    claim_id: str,
    claim: str,
    evidence: str,
    direction: str,
    confidence: float = 0.8,
    entities: list[str] | None = None,
    factors: list[str] | None = None,
    record_index: int = 0,
) -> None:
    """Insert one row directly into ``agent_outputs`` via raw SQLAlchemy,
    bypassing ``repository.persist_agent_outputs()`` (and therefore its
    write-time ``is_claim_eligible`` gate) entirely. Simulates a row that
    landed in the database before the Product Findings Closure Sprint's
    read-time gate existed -- ``claim_quality`` is not, and never was, a
    persisted column, so every such row is representative of "historical
    pollution", not a contrived edge case."""
    with engine.begin() as conn:
        conn.execute(
            sa.insert(agent_outputs).values(
                id=f"legacy-{run_id}-{claim_id}",
                run_id=run_id,
                claim_id=claim_id,
                source_agent_output_id=f"{run_id}:legacy_agent:legacy_report",
                ticker="NVDA",
                agent="legacy_agent",
                claim=claim,
                evidence=evidence,
                entities=entities if entities is not None else ["NVDA"],
                factors=factors if factors is not None else [],
                direction=direction,
                confidence=confidence,
                source_type="legacy",
                source_refs=[f"{run_id}:legacy_agent:legacy_report"],
                claim_index=0,
                record_index=record_index,
                created_at=datetime.now(UTC),
            )
        )


def test_historical_pollution_is_filtered_at_read_time(tmp_path):
    """Spec section 3's four worked examples, planted directly into the
    database (never through today's write-time gate) to simulate rows that
    predate this Sprint. The live API must classify and filter every one of
    them ephemerally, at read time, using only their own persisted fields --
    never depending on a ``claim_quality`` column that was never written."""
    engine, repo = _repo()
    run_id = "legacy-pollution-run"

    _insert_legacy_row(
        engine,
        run_id=run_id,
        claim_id="c-meta",
        claim="Let me synthesize everything.",
        evidence="Let me synthesize everything.",
        direction="unknown",
        record_index=0,
    )
    _insert_legacy_row(
        engine,
        run_id=run_id,
        claim_id="c-analytical",
        claim="Revenue declined 12% year over year.",
        evidence="Revenue declined 12% year over year.",
        direction="negative",
        record_index=1,
    )
    _insert_legacy_row(
        engine,
        run_id=run_id,
        claim_id="c-context",
        claim="The company operates three fabrication facilities.",
        evidence="The company operates three fabrication facilities.",
        direction="unknown",
        record_index=2,
    )
    _insert_legacy_row(
        engine,
        run_id=run_id,
        claim_id="c-unknown",
        claim="unknown",
        evidence="unknown",
        direction="unknown",
        confidence=0.0,
        record_index=3,
    )

    result = get_agent_outputs_response(run_id, output_root=tmp_path, graph_repository=repo)

    assert result["status"] == "ok"
    claims = [r["claim"] for r in result["structured_agent_outputs"]]
    assert claims == ["Revenue declined 12% year over year."]
    assert result["count"] == 1
