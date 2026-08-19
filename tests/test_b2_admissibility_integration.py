"""John's B2 Conflict Evidence Admissibility gate -- focused end-to-end
integration test (task B2_CONFLICT_EVIDENCE_ADMISSIBILITY, section 22).

Exercises the full downstream chain B2 sits in, entirely offline (0
Provider calls -- no LLM, no network, nothing in this module's import graph
can reach either): final B1 stance (represented here as already-attached
``candidate_scores[].evidence_stance`` fields -- the exact final-field
contract ``conflict_detector.py``'s own module docstring declares as its
input boundary; Conflict Detector, and B2 built strictly on top of it, never
touches raw text or B1 internals) -> the shared Evidence Fact Index ->
the existing, unmodified Conflict Detector -> John's B2 admissibility gate
-> Week 4 DB persistence -> the conflicts artifact export -> the run_audit
conflict summary. The same hand-built, minimal, fully-controlled two-pair
scenario as ``tests/test_conflict_admissibility.py`` (one genuinely
admitted pair, one genuinely candidate pair) is threaded through every
stage so the SAME computed admissibility result can be asserted
byte-identical at each stage -- proving section 22's requirement that it is
computed once (inside ``conflict_detector._evaluate_candidate``) and
serialized everywhere else, never independently recomputed by the DB
reconstruction, the artifact export, or the run_audit summary.
"""

from __future__ import annotations

from comqutor_alpha.alpha_library.alpha_schema import ConflictAlpha
from comqutor_alpha.api.artifact_export import extract_conflicts_export
from comqutor_alpha.api.routes_research import _build_research_summary, _conflict_summary_section
from comqutor_alpha.conflict_engine.conflict_admissibility import ADMITTED, CANDIDATE
from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from tests.fixtures.week4_conflict_cases import activation_entry, activation_payload, fake_alpha

RUN_ID = "b2_integration_run"
TICKER = "NVDA"

# A -- B: genuinely clears John's B2 gate (both sides score>=50, >=2 unique
# ticker-specific supports_alpha facts). C -- D: genuinely reaches B2
# evaluation but is denied (bear side has only one unique supporting fact).
_TAXONOMY = {
    "A": fake_alpha("A", [ConflictAlpha(alpha_id="B", contradiction_weight=0.9)]),
    "B": fake_alpha("B", [ConflictAlpha(alpha_id="A", contradiction_weight=0.9)]),
    "C": fake_alpha("C", [ConflictAlpha(alpha_id="D", contradiction_weight=0.9)]),
    "D": fake_alpha("D", [ConflictAlpha(alpha_id="C", contradiction_weight=0.9)]),
}


def _raw_match(claim_id, alpha_id, evidence, *, score=0.8, stance="supports_alpha", stance_method="llm"):
    """The real alpha_matches.json record shape -- ``evidence_stance``
    attached under ``candidate_scores[]`` exactly as
    ``evidence_stance_llm.apply_llm_stance_upgrade`` leaves it after a real
    (offline, deterministic) B1 run."""
    candidate = {"alpha_id": alpha_id, "score": score, "relation": "activation"}
    if stance is not None:
        candidate["evidence_stance"] = stance
        candidate["stance_method"] = stance_method
    return {
        "claim_id": claim_id,
        "source_agent_output_id": f"o_{claim_id}",
        "agent": f"agent_{claim_id}",
        "match_status": "matched",
        "matched_alpha": alpha_id,
        "matched_alpha_name": alpha_id,
        "score": score,
        "direction": "positive",
        "assertion_status": "asserted",
        "semantic_polarity": "activation",
        "claim": evidence,
        "evidence": evidence,
        "reason": "test fixture",
        "plausible_alphas": [],
        "candidate_scores": [candidate],
        "claim_quality": "analytical",
        "factors": [],
    }


def _build_alpha_matches():
    return [
        # A (bull): 2 unique, ticker-specific, supports_alpha facts.
        _raw_match("a1", "A", f"{TICKER} datacenter demand is accelerating."),
        _raw_match("a2", "A", f"{TICKER} new supply agreements were announced."),
        # B (bear): 2 unique, ticker-specific, supports_alpha facts.
        _raw_match("b1", "B", f"{TICKER} valuation multiples remain stretched."),
        _raw_match("b2", "B", f"{TICKER} insider selling has picked up."),
        # C (bull): 2 unique, ticker-specific, supports_alpha facts.
        _raw_match("c1", "C", f"{TICKER} cloud capex guidance was raised."),
        _raw_match("c2", "C", f"{TICKER} backlog grew again this quarter."),
        # D (bear): only ONE unique supporting fact -- denied by B2.
        _raw_match("d1", "D", f"{TICKER} margin compression was flagged by analysts."),
    ]


def _build_activation_payload():
    return activation_payload(
        activation_entry("A", score=70.0, direction="positive"),
        activation_entry("B", score=70.0, direction="negative"),
        activation_entry("C", score=70.0, direction="positive"),
        activation_entry("D", score=70.0, direction="negative"),
    )


def _repo():
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


def test_b2_result_is_computed_once_and_identical_across_detector_db_and_export():
    activation = _build_activation_payload()
    alpha_matches = _build_alpha_matches()

    # 1. Final B1 stance (embedded above) -> shared Evidence Fact Index ->
    # existing Conflict Detector -> B2 admissibility gate. Pure function,
    # zero I/O, zero Provider calls.
    detector_result = detect_alpha_conflicts(
        run_id=RUN_ID,
        ticker=TICKER,
        activation_payload=activation,
        alpha_matches=alpha_matches,
        taxonomy=_TAXONOMY,
    )

    # Sanity: this fixture genuinely exercises both an admitted and a
    # candidate outcome under B2 -- not a degenerate all-pass/all-fail case.
    assert [c["conflict_id"] for c in detector_result["conflicts"]] == ["A__B"]
    assert detector_result["main_conflict"]["conflict_id"] == "A__B"
    detector_evaluations = {
        (c["alpha_a"], c["alpha_b"]): c for c in detector_result["arbitration"]["candidate_evaluations"]
    }
    assert detector_evaluations[("A", "B")]["admissibility"]["status"] == ADMITTED
    cd_admissibility = detector_evaluations[("C", "D")]["admissibility"]
    assert cd_admissibility["status"] == CANDIDATE
    assert cd_admissibility["bear_supporting_evidence_count"] == 1

    # 2. Week 4 DB persistence: 0 Provider calls, pure DB round-trip.
    repo = _repo()
    repo.persist_week4_results(
        run_id=RUN_ID, ticker=TICKER, activation_payload=activation, conflict_payload=detector_result
    )
    db_result = repo.get_week4_conflict_result(RUN_ID)
    assert db_result is not None
    assert db_result["main_conflict"]["conflict_id"] == "A__B"
    db_evaluations = {
        (c["alpha_a"], c["alpha_b"]): c for c in db_result["arbitration"]["candidate_evaluations"]
    }
    # The exact same admissibility diagnostic (both the admitted A/B pair's
    # and the denied C/D pair's) survives the DB round-trip byte-for-byte --
    # never recomputed by the persistence/reconstruction layer.
    assert db_evaluations[("A", "B")]["admissibility"] == detector_evaluations[("A", "B")]["admissibility"]
    assert db_evaluations[("C", "D")]["admissibility"] == detector_evaluations[("C", "D")]["admissibility"]
    assert db_result["main_conflict"] == detector_result["conflicts"][0]

    # 3. Conflicts artifact export (artifact_export.extract_conflicts_export):
    # a direct extraction of the same in-memory payload, never a second
    # detect_alpha_conflicts call.
    export = extract_conflicts_export(detector_result, run_id=RUN_ID, ticker=TICKER)
    assert export is not None
    assert export["main_conflict"] == detector_result["main_conflict"]
    assert export["admitted_conflict_count"] == 1
    assert export["candidate_conflict_count"] == 1
    exported_candidate_ids = {(c["alpha_a"], c["alpha_b"]) for c in export["candidate_conflicts"]}
    assert exported_candidate_ids == {("C", "D")}
    exported_cd = next(
        c for c in export["candidate_conflicts"] if (c["alpha_a"], c["alpha_b"]) == ("C", "D")
    )
    assert exported_cd["admissibility"] == cd_admissibility

    # Also exported from the DB-persisted payload (the real production
    # path: artifact_export reads whatever conflict_payload the caller
    # already has in memory, which after a completed run is this same DB
    # reconstruction) -- still byte-identical, still never recomputed.
    export_from_db = extract_conflicts_export(db_result, run_id=RUN_ID, ticker=TICKER)
    assert export_from_db == export

    # 4. run_audit's conflict_summary section (routes_research.py): the
    # same per-pair admissibility diagnostic, reshaped but never
    # recomputed, plus the new admitted_conflict_count/
    # candidate_conflict_count fields agreeing with the export above.
    conflict_summary = _conflict_summary_section(detector_result)
    assert conflict_summary["admitted_conflict_count"] == export["admitted_conflict_count"]
    assert conflict_summary["candidate_conflict_count"] == export["candidate_conflict_count"]
    summary_by_pair = {(p["alpha_a"], p["alpha_b"]): p for p in conflict_summary["per_pair"]}
    assert summary_by_pair[("A", "B")]["admissibility"] == detector_evaluations[("A", "B")]["admissibility"]
    assert summary_by_pair[("C", "D")]["admissibility"] == cd_admissibility
    assert summary_by_pair[("A", "B")]["is_main"] is True
    assert summary_by_pair[("C", "D")]["is_main"] is False

    # 5. Research Summary text (routes_research._build_research_summary,
    # the same function ResearchRunPage's "Research summary" panel
    # displays verbatim): must describe the admitted A__B main conflict,
    # never the denied candidate C__D pair, however evidence-rich C__D's
    # own diagnostic looks (QA Closure v0.1.2 Item 3, Invariant 1).
    summary_text = _build_research_summary("ready", db_result["main_conflict"], dominant_alphas=[])
    assert summary_text == db_result["main_conflict"]["explanation"]
    assert "C" not in summary_text.split() and "D" not in summary_text.split()
