"""Proves the T1 verified-support eligibility gate DECIDES THE OFFICIAL
result of the REAL production orchestration path (escalated 2026-09-28
from "additive diagnostic field" to "official result") -- not merely
callable via ``comqutor_alpha.graph_engine.verified_evidence_gate``'s own
functions, and not merely an extra field sitting alongside an unchanged
official conclusion.

The user's explicit requirement: "直接调用 wrapper 的单元测试不能替代生产接入"
(a unit test that calls the wrapper directly cannot substitute for
production wiring) -- and, this round, "正式结果必须采用经过资格门的计算结果"
(the OFFICIAL result itself must be the gate-filtered computation, not a
side channel a consumer can still bypass). This file therefore never
imports/calls ``score_alpha_v2_verified``/``evaluate_conflict_
admissibility_verified`` itself -- it calls ``comqutor_alpha.api.
routes_research._run_week3_graph_pipeline``, the exact same private
orchestration function the live API server invokes after Week 1-2
completes (already directly tested this way elsewhere in this suite --
see ``tests/test_graph_persistence.py::test_week3_pipeline_degrades_
safely_in_production_without_database_url`` for the identical, precedented
pattern), against a hand-built run directory on disk. Nothing here
manually threads ``structured_records``/``sources`` into any wrapper -- the
pipeline reads ``structured_agent_outputs.json``/``source_registry.json``
off disk itself, exactly as it would for a real run.
"""

from __future__ import annotations

import json

import comqutor_alpha.api.routes_research as routes_research
from comqutor_alpha.source_provenance import (
    SOURCE_LINK_VALID,
    apply_content_support_review,
)
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository

RUN_ID = "prodwire_verified_gate_run"
TICKER = "NVDA"


def _repo():
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


def _match(claim_id, agent, claim, *, alpha_id, direction, factor, keyword):
    """Same real match-record shape as tests/test_activation_scorer_v2.py's
    own ``_record()`` oracle fixture -- real, recognized agent names
    (``market_agent``/``fundamental_agent``/``sentiment_agent``) are
    required for Step 6's Primary/Secondary role qualification to accept
    the claim at all; a synthetic agent name silently zeros the score."""
    candidate = {
        "alpha_id": alpha_id, "relation": "activation", "matched_keywords": [keyword], "matched_factors": [factor],
        # John's B2 gate reads its own final B1 stance from this SAME
        # candidate pool (conflict_admissibility.stance_for_alpha) -- never
        # defaults to support, so it must be set explicitly for
        # _stance_filtered_qualifying to count this claim on its side.
        "evidence_stance": "supports_alpha",
    }
    return {
        "run_id": RUN_ID, "ticker": TICKER, "agent": agent, "claim_id": claim_id,
        "source_agent_output_id": f"{agent}:source", "claim": claim, "evidence": claim,
        "match_status": "matched", "matched_alpha": alpha_id, "score": 1.0,
        "assertion_status": "asserted", "semantic_polarity": "activation",
        "factor_score": 1.0, "keyword_score": 1.0, "eligible_candidates": [candidate],
        "claim_quality": "analytical", "direction": direction,
    }


def _reviewed_record(claim_id, linked_fragment_id):
    review = apply_content_support_review(
        {"claim_id": claim_id, "source_link_status": SOURCE_LINK_VALID, "linked_source_id": linked_fragment_id},
        status="SUPPORTS", reviewer="analyst_a", rationale="matches the captured excerpt",
        reviewed_at="2026-09-28T00:00:00Z", sources=_SOURCES,
    )
    return {
        "claim_id": claim_id,
        "source_link_status": SOURCE_LINK_VALID,
        "linked_source_id": linked_fragment_id,
        "content_support_status": "SUPPORTS",
        "content_support_review": review["content_support_review"],
    }


def _unreviewed_record(claim_id):
    return {"claim_id": claim_id, "source_link_status": "NOT_PROVIDED"}


# published_at is REQUIRED here, not optional fixture detail -- see the
# identical fix and justification in tests/test_verified_evidence_gate.py's
# own _source() helper (the same 2026-09-29 DISCLOSURE_TIME_UNKNOWN gate,
# the same systemic staleness, found and fixed together this round).
_SOURCES = [
    {
        "source_id": "s_a102", "fragment_id": "s_a102:frag-0", "content_hash": "sha256:a102hash",
        "published_at": "2026-06-25T00:00:00Z",
    },
    {
        "source_id": "s_a304", "fragment_id": "s_a304:frag-0", "content_hash": "sha256:a304hash",
        "published_at": "2026-06-25T00:00:00Z",
    },
]


def _build_run_dir(tmp_path):
    run_dir = tmp_path / RUN_ID
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(
        json.dumps({"run_id": RUN_ID, "ticker": TICKER, "analysis_date": "2026-06-30"}), encoding="utf-8"
    )

    a102_claims = [
        _match("a102_1", "market_agent", f"{TICKER} datacenter revenue growth is accelerating.", alpha_id="A102", direction="positive", factor="Revenue Growth", keyword="demand"),
        _match("a102_2", "fundamental_agent", f"{TICKER} order backlog continues to expand this quarter.", alpha_id="A102", direction="positive", factor="Order Backlog", keyword="backlog"),
        _match("a102_3", "sentiment_agent", f"{TICKER} announced new supply agreements boosting output capacity.", alpha_id="A102", direction="positive", factor="Supply", keyword="supply"),
    ]
    a304_claims = [
        _match("a304_1", "market_agent", f"{TICKER} gross margin compression is accelerating.", alpha_id="A304", direction="negative", factor="Margin", keyword="margin"),
        _match("a304_2", "fundamental_agent", f"{TICKER} pricing power continues to weaken this quarter.", alpha_id="A304", direction="negative", factor="Pricing", keyword="pricing"),
        _match("a304_3", "sentiment_agent", f"{TICKER} announced new price cuts hurting profitability.", alpha_id="A304", direction="negative", factor="Price Cuts", keyword="cuts"),
    ]
    (run_dir / "alpha_matches.json").write_text(
        json.dumps({"run_id": RUN_ID, "ticker": TICKER, "matches": a102_claims + a304_claims}), encoding="utf-8"
    )
    (run_dir / "extracted_structures.json").write_text(
        json.dumps({"run_id": RUN_ID, "ticker": TICKER, "nodes": [], "edges": []}), encoding="utf-8"
    )

    # Only ONE of each side's three real, score-qualifying claims has ever
    # been through a genuine human review -- exactly the realistic "review
    # is still in progress" state. This is the ONLY variable between the
    # raw and verified views below; every match/activation input is
    # identical.
    records = [
        _reviewed_record("a102_1", "s_a102:frag-0"),
        _unreviewed_record("a102_2"),
        _unreviewed_record("a102_3"),
        _reviewed_record("a304_1", "s_a304:frag-0"),
        _unreviewed_record("a304_2"),
        _unreviewed_record("a304_3"),
    ]
    (run_dir / "structured_agent_outputs.json").write_text(
        json.dumps({"run_id": RUN_ID, "ticker": TICKER, "records": records}), encoding="utf-8"
    )
    (run_dir / "source_registry.json").write_text(
        json.dumps(
            {"schema_version": "source_registry.v1", "run_id": RUN_ID, "ticker": TICKER, "source_count": 2, "sources": _SOURCES}
        ),
        encoding="utf-8",
    )
    return run_dir


def test_real_week3_pipeline_makes_the_verified_view_the_official_activation_result(tmp_path):
    run_dir = _build_run_dir(tmp_path)
    repo = _repo()

    routes_research._run_week3_graph_pipeline(run_dir, graph_repository=repo)

    graph_payload = json.loads((run_dir / "structure_graph.json").read_text(encoding="utf-8"))
    activation_versions = graph_payload["activation_versions"]
    assert "v2_verified" in activation_versions, (
        "structure_graph.json must carry a v2_verified activation view once "
        "structured_agent_outputs.json/source_registry.json are present on disk "
        "-- this is computed by the real pipeline itself, never by a test-side wrapper call"
    )

    by_alpha_v2 = {a["alpha_id"]: a for a in activation_versions["v2"]["alphas"]}
    by_alpha_verified = {a["alpha_id"]: a for a in activation_versions["v2_verified"]["alphas"]}
    # Raw v2 (now diagnostic-only): all 3 claims per side count -> 3 unique
    # Evidence Facts each.
    assert by_alpha_v2["A102"]["evidence_count"] == 3
    assert by_alpha_v2["A304"]["evidence_count"] == 3
    # Verified: only the 1 genuinely reviewed claim per side counts.
    assert by_alpha_verified["A102"]["evidence_count"] == 1
    assert by_alpha_verified["A304"]["evidence_count"] == 1
    assert by_alpha_verified["A102"]["activation_score"] < by_alpha_v2["A102"]["activation_score"]
    assert by_alpha_verified["A304"]["activation_score"] < by_alpha_v2["A304"]["activation_score"]

    # THE ESCALATION: "activation" (the field every existing consumer reads
    # as the official result) and primary_activation_version now point at
    # the VERIFIED view, not the raw v2 diagnostic one -- the raw pool can
    # no longer produce an official result that bypasses the gate.
    assert graph_payload["activation"] == activation_versions["v2_verified"]
    assert graph_payload["primary_activation_version"] == activation_versions["v2_verified"]["formula_version"]
    assert graph_payload["primary_activation_version"] != activation_versions["v2"]["formula_version"]
    assert graph_payload["evidence_gate_version"]
    assert graph_payload["evidence_gate_applied"] is True

    # active/dominant/etc. (what pages actually render) are computed from
    # the OFFICIAL (verified) pool: with only 1/3 claims reviewed per side,
    # neither A102 nor A304 clears the activation score threshold under the
    # verified-only evidence pool, so neither appears as active/dominant.
    official_ids = {a["alpha_id"] for a in graph_payload["active_alphas"]} | {
        a["alpha_id"] for a in graph_payload["dominant_alphas"]
    }
    assert "A102" not in official_ids
    assert "A304" not in official_ids


def test_real_week4_pipeline_makes_admitted_and_main_conflict_gate_filtered(tmp_path):
    run_dir = _build_run_dir(tmp_path)
    repo = _repo()

    routes_research._run_week3_graph_pipeline(run_dir, graph_repository=repo)

    conflict_result = repo.get_week4_conflict_result(RUN_ID)
    assert conflict_result is not None
    pair = next(
        c for c in conflict_result["arbitration"]["candidate_evaluations"]
        if {c["alpha_a"], c["alpha_b"]} == {"A102", "A304"}
    )
    admissibility = pair.get("admissibility")
    admissibility_diagnostic_unverified = pair.get("admissibility_diagnostic_unverified")
    assert admissibility is not None
    assert admissibility_diagnostic_unverified is not None, (
        "the raw, unfiltered computation must survive as a DIAGNOSTIC field on the real, "
        "DB-round-tripped candidate_evaluations entry -- proves it survives Week 4's own DB "
        "write/read whitelist, not just an in-process return value"
    )
    assert pair["evidence_gate_version"]
    assert pair["evidence_gate_applied"] is True

    # Diagnostic (raw, bypassed): 3 unreviewed-but-real claims per side
    # would have cleared both MIN_SUPPORTING_EVIDENCE_PER_SIDE(2) and the
    # ticker-specific/score gates under the OLD, ungated rules.
    assert admissibility_diagnostic_unverified["status"] == "admitted"
    # OFFICIAL: only 1 genuinely-reviewed claim per side -- below
    # MIN_SUPPORTING_EVIDENCE_PER_SIDE(2) -- so the SAME real, unmodified,
    # frozen B2 gate correctly refuses to admit it as the OFFICIAL result,
    # using the SAME threshold, never a relaxed one. This candidate must
    # therefore never appear in "conflicts"/"main_conflict".
    assert admissibility["status"] != "admitted"
    assert admissibility["bull_supporting_evidence_count"] < admissibility_diagnostic_unverified["bull_supporting_evidence_count"]
    assert admissibility["bear_supporting_evidence_count"] < admissibility_diagnostic_unverified["bear_supporting_evidence_count"]
    assert conflict_result["conflicts"] == []
    assert conflict_result["main_conflict"] is None

    # The exact same fields the live GET /api/research/{run_id}/conflicts
    # endpoint serves (get_persisted_conflicts is a straight passthrough of
    # this same repository read) -- so this is also what reaches the API.
    api_result = routes_research.get_persisted_conflicts(RUN_ID, output_root=tmp_path, graph_repository=repo)
    api_pair = next(
        c for c in api_result["arbitration"]["candidate_evaluations"]
        if {c["alpha_a"], c["alpha_b"]} == {"A102", "A304"}
    )
    assert api_pair["admissibility"] == admissibility
    assert api_result["conflicts"] == []
    assert api_result["main_conflict"] is None
