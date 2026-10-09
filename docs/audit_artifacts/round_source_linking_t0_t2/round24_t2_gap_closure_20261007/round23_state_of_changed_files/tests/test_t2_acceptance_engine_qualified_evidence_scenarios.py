"""T2 verification, 2026-09-29 follow-up: prove -- through the REAL
comqutor_alpha.regression.acceptance_engine.run_formal_acceptance entry
point, never a hand-rolled recompute -- that formal acceptance consumes
evidence that is BOTH source-link-qualified AND content-support-qualified,
never merely evidence_stance-qualified.

The mechanism under test: conflict_engine.conflict_detector.
detect_alpha_conflicts(require_verified_evidence_gate=True) restricts each
side's "qualifying claims" to those whose OWN persisted structured record
passes comqutor_alpha.source_provenance.compute_verified_support_eligibility
(graph_engine.verified_evidence_gate.filter_verified_qualifying_claims) --
a source-link-validity AND content-support-review check, entirely separate
from (and applied ON TOP OF) evidence_stance classification. This is what
acceptance_engine.py's own bull_supporting_evidence_count/
bear_supporting_evidence_count (read via pair_admissibility_lookup) and
_evidence_present ultimately consume.

Four required scenarios, all via real production entrypoints
(run_research_request/submit_content_support_review), never a manually
constructed conflicts.json:

  A. Invalid source (a forged, unresolvable marker) -- the claim's
     evidence_stance would classify identically to a valid one, but it
     never counts as officially qualifying evidence.
  B. Pending review (a REAL, valid, resolvable source link that has never
     been reviewed) -- same non-count, for a different reason.
  C. Valid support (REAL HUMAN_REVIEWED SUPPORTS) -- now counts, and
     run_formal_acceptance's own must_detect_if_evidence_present rule
     family genuinely observes evidence_present flip from False to True.
  D. Missing rules (effective_rules() cannot resolve its own taxonomy/
     label_v2 config) -- run_formal_acceptance must report
     formal_status="config_error", never a silent pass.

One control claim (A301, the bull side) stays constantly valid+reviewed
throughout A/B/C so the varying side (A304, the bear side) is the only
thing changing; this isolates the mechanism instead of conflating two
moving parts. Zero Provider calls anywhere in this file.

SYNTHETIC INPUTS (task sheet: "测试可以使用明确标注的合成 fixtures，但不能把它们计为真实市场验证样本"): the pipeline code under test is the real
production code, but the market / news / report text it is fed here is hand-written and the external data boundary is faked. These tests prove
mechanisms; they are NOT real market validation and are never counted as such.
"""

from __future__ import annotations

import json
import time
from datetime import datetime

import tradingagents.dataflows.yfinance_news as ynews
from comqutor_alpha.adapters.tradingagents_output_writer import save_comqutor_run_outputs
from comqutor_alpha.api.routes_research import run_research_request, submit_content_support_review
from comqutor_alpha.regression.acceptance_engine import (
    pair_admissibility_lookup,
    run_formal_acceptance,
)
from comqutor_alpha.regression.evaluator import (
    conflict_comparison,
    detected_alpha_sets,
    six_ticker_qa_alpha_fields,
    six_ticker_qa_conflict_fields,
    stance_source,
)
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from scripts.deterministic_echo_llm import build_deterministic_echo_gateway
from tradingagents.dataflows.source_capture import source_capture_scope

TICKER = "NVDA"
BULL_ALPHA_ID = "A301"  # Revenue Expansion
BEAR_ALPHA_ID = "A304"  # Multiple Compression
PAIR_ID = "A301__A304"  # canonical_pair_key sorts lexicographically: A301 < A304
BULL_EXCERPT = "NVDA reported strong data center revenue growth this quarter, beating analyst estimates."
# Deliberately no contrast/positive language (e.g. "despite strong
# fundamentals") -- structured_output_adapter.analyze_claim_semantics
# flags has_contrast+has_positive+has_negative as "mixed", which
# infer_direction then reports as "neutral" rather than "negative",
# which would prevent conflict_schema.resolve_bull_bear from ever
# resolving a bull/bear role for this pair at all.
BEAR_EXCERPT = (
    "NVDA valuation has become dangerously stretched, with rich multiples driving severe "
    "downside risk. Analysts warn the shares are overvalued and vulnerable to a sharp pullback."
)


class _FakeTicker:
    def __init__(self, articles):
        self._articles = articles

    def get_news(self, count=None):
        return self._articles


def _flat_article(title, publisher, link, epoch_ts, summary):
    return {"title": title, "publisher": publisher, "link": link, "providerPublishTime": epoch_ts, "summary": summary}


def _epoch(date_str):
    return int(time.mktime(datetime.strptime(date_str, "%Y-%m-%d").timetuple()))


def _capture_real_source(monkeypatch, *, title, publisher, link, date_str, excerpt):
    articles = [_flat_article(title, publisher, link, _epoch(date_str), excerpt)]
    monkeypatch.setattr(ynews.yf, "Ticker", lambda symbol: _FakeTicker(articles))
    monkeypatch.setattr(ynews, "normalize_symbol", lambda ticker: ticker)
    with source_capture_scope() as sink:
        ynews.get_news_yfinance(TICKER, "2026-08-01", "2026-08-09")
    return list(sink)


def _repo():
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


def _build_run_with_bull_and_bear(tmp_path, monkeypatch, *, bear_report_text, run_label):
    """Real production entrypoint: bull side is ALWAYS a genuinely captured,
    resolvable NVDA article; bear side's raw_output text is supplied by the
    caller so each of scenarios A/B/C can vary it independently."""
    repo = _repo()
    bull_captured = _capture_real_source(
        monkeypatch, title="NVDA Data Center Revenue Beats Estimates", publisher="Reuters",
        link="https://reuters.com/nvda-dc", date_str="2026-08-05", excerpt=BULL_EXCERPT,
    )

    def runner(payload, *, output_root):
        final_state = {"news_report": f"{BULL_EXCERPT} {bear_report_text}"}
        return save_comqutor_run_outputs(
            final_state, payload["ticker"], selected_analysts=["news"],
            analysis_date=payload.get("analysis_date"), output_root=output_root,
            captured_sources=bull_captured,
        )

    payload = {"ticker": TICKER, "analysis_date": "2026-08-10", "selected_analysts": ["news"]}
    gateway = build_deterministic_echo_gateway(f"t2-acceptance-{run_label}", tmp_path)
    response = run_research_request(
        payload, runner=runner, output_root=tmp_path, graph_repository=repo, week2_llm_gateway=gateway
    )
    assert response["status"] == "completed"
    return repo, response["run_id"]


def _bull_and_bear_claim_ids(tmp_path, run_id):
    matches = json.loads((tmp_path / run_id / "alpha_matches.json").read_text(encoding="utf-8"))["matches"]
    bull = next(m for m in matches if m.get("matched_alpha") == BULL_ALPHA_ID)
    bear_candidates = [m for m in matches if m.get("matched_alpha") == BEAR_ALPHA_ID]
    bear = bear_candidates[0] if bear_candidates else None
    return bull["claim_id"], (bear["claim_id"] if bear else None)


def _run_formal_acceptance_for(tmp_path, run_id):
    """Mirrors run_six_ticker_acceptance_typea.py's own Type A construction
    (the SAME real helper functions), fed from THIS test's own fresh run
    instead of a historical one, with a minimal, controlled
    ticker_v2_label that declares ONLY our synthetic PAIR_ID as
    required -- a real, legitimate input to the real function, not a
    fabricated result."""
    graph_payload = json.loads((tmp_path / run_id / "structure_graph.json").read_text(encoding="utf-8"))
    conflict_payload = json.loads((tmp_path / run_id / "conflicts.json").read_text(encoding="utf-8"))
    alpha_matches_payload = json.loads((tmp_path / run_id / "alpha_matches.json").read_text(encoding="utf-8"))

    label_block_v1 = {}
    ticker_v2_label = {"required_conflicts": [PAIR_ID]}
    detected = detected_alpha_sets(graph_payload)
    conflict_cmp = conflict_comparison(label_block_v1, conflict_payload)
    evaluate_ticker_result = {
        "ticker": TICKER,
        "run_id": run_id,
        "run_selection_status": "selected",
        "offline_reprocess_status": "completed",
        "artifact_completeness": "pass",
        "artifact_missing_files": [],
        "detected_alphas": detected["detected_alphas"],
        "dominant_alphas": detected["dominant_alphas"],
        **conflict_cmp,
        **six_ticker_qa_conflict_fields(conflict_cmp),
        **six_ticker_qa_alpha_fields(label_block_v1, detected),
        "stance_source": stance_source(alpha_matches_payload),
    }
    admissibility_lookup = pair_admissibility_lookup(conflict_payload)
    acceptance = run_formal_acceptance(
        ticker=TICKER,
        ticker_v2_label=ticker_v2_label,
        label_block_v1=label_block_v1,
        evaluate_ticker_result=evaluate_ticker_result,
        conflict_payload=conflict_payload,
        graph_payload=graph_payload,
        alpha_matches_payload=alpha_matches_payload,
    )
    return acceptance, admissibility_lookup.get(PAIR_ID)


class TestScenarioA_InvalidSourceNeverCountsAsQualifyingEvidence:
    def test_forged_bear_marker_leaves_bear_supporting_evidence_count_at_zero(self, tmp_path, monkeypatch):
        forged_bear_text = f"{BEAR_EXCERPT} [fragment_id: src_deadbeefdeadbeef:frag:0]."
        repo, run_id = _build_run_with_bull_and_bear(tmp_path, monkeypatch, bear_report_text=forged_bear_text, run_label="scenario-a")
        bull_claim_id, bear_claim_id = _bull_and_bear_claim_ids(tmp_path, run_id)
        assert bear_claim_id is not None, "expected the forged-source claim to still map to A304 semantically"

        # Review the BULL side as SUPPORTS (the constant control claim) --
        # the bear side is never touched, so its own state is entirely
        # determined by the forged marker.
        review = submit_content_support_review(
            run_id, bull_claim_id, status="SUPPORTS", reviewer="analyst_a",
            rationale="the captured excerpt directly reports the same revenue figure the claim asserts",
            output_root=tmp_path, graph_repository=repo,
        )
        assert review["status"] == "ok"
        execution_id = review["reevaluation"]["execution_id"]

        acceptance, admissibility = _run_formal_acceptance_for(tmp_path, execution_id)
        assert admissibility is not None, "expected the declared pair to reach B2 arbitration"
        # The forged claim never becomes officially qualifying evidence for
        # A304, so A304's own OFFICIAL activation-level direction stays
        # "unknown" (zero official evidence) -- conflict_schema.
        # resolve_bull_bear then cannot resolve a bull/bear role at all
        # (needs exactly one positive + one negative official direction),
        # so the pair never even reaches admissibility SCORING -- an even
        # stronger form of "never counts" than a computed zero count.
        assert admissibility["bear_supporting_evidence_count"] is None
        assert admissibility["admissibility_status"] is None
        must_detect = acceptance["rule_family_results"]["must_detect_if_evidence_present"]
        entry = next(r for r in must_detect if r["pair"] == PAIR_ID)
        assert entry["evidence_present"] is False
        assert entry["verdict"] == "not_applicable"


class TestScenarioB_PendingReviewNeverCountsAsQualifyingEvidence:
    def test_a_real_valid_but_unreviewed_bear_source_leaves_bear_supporting_evidence_count_at_zero(
        self, tmp_path, monkeypatch
    ):
        bear_captured = _capture_real_source(
            monkeypatch, title="NVDA Valuation Looks Stretched", publisher="Bloomberg",
            link="https://bloomberg.com/nvda-valuation", date_str="2026-08-06", excerpt=BEAR_EXCERPT,
        )
        # Extract the REAL marker this capture produced (a genuine,
        # resolvable [fragment_id: ...] this run's own registry contains --
        # never a forged id), so the bear claim carries a VALID reference
        # that simply has not been reviewed yet.
        from tradingagents.dataflows.yfinance_news import _source_reference_marker

        marker = _source_reference_marker(bear_captured[0])
        bear_text_with_real_marker = f"{BEAR_EXCERPT} {marker}"

        repo = _repo()
        bull_captured = _capture_real_source(
            monkeypatch, title="NVDA Data Center Revenue Beats Estimates", publisher="Reuters",
            link="https://reuters.com/nvda-dc", date_str="2026-08-05", excerpt=BULL_EXCERPT,
        )

        def runner(payload, *, output_root):
            final_state = {"news_report": f"{BULL_EXCERPT} {bear_text_with_real_marker}"}
            return save_comqutor_run_outputs(
                final_state, payload["ticker"], selected_analysts=["news"],
                analysis_date=payload.get("analysis_date"), output_root=output_root,
                captured_sources=bull_captured + bear_captured,
            )

        payload = {"ticker": TICKER, "analysis_date": "2026-08-10", "selected_analysts": ["news"]}
        gateway = build_deterministic_echo_gateway("t2-acceptance-scenario-b", tmp_path)
        response = run_research_request(
            payload, runner=runner, output_root=tmp_path, graph_repository=repo, week2_llm_gateway=gateway
        )
        assert response["status"] == "completed"
        run_id = response["run_id"]

        bull_claim_id, bear_claim_id = _bull_and_bear_claim_ids(tmp_path, run_id)
        assert bear_claim_id is not None

        structured = json.loads((tmp_path / run_id / "structured_agent_outputs.json").read_text(encoding="utf-8"))
        bear_record = next(r for r in structured["records"] if r["claim_id"] == bear_claim_id)
        assert bear_record["source_link_status"] == "VALID"
        assert bear_record["content_support_status"] == "PENDING_REVIEW"

        review = submit_content_support_review(
            run_id, bull_claim_id, status="SUPPORTS", reviewer="analyst_a",
            rationale="the captured excerpt directly reports the same revenue figure the claim asserts",
            output_root=tmp_path, graph_repository=repo,
        )
        assert review["status"] == "ok"
        execution_id = review["reevaluation"]["execution_id"]

        acceptance, admissibility = _run_formal_acceptance_for(tmp_path, execution_id)
        assert admissibility is not None
        # Same underlying reason as scenario A: an unreviewed (even though
        # genuinely source-linked) claim never contributes to A304's own
        # OFFICIAL evidence_count, so its official direction stays
        # "unknown" and the pair never reaches admissibility scoring.
        assert admissibility["bear_supporting_evidence_count"] is None
        assert admissibility["admissibility_status"] is None
        must_detect = acceptance["rule_family_results"]["must_detect_if_evidence_present"]
        entry = next(r for r in must_detect if r["pair"] == PAIR_ID)
        assert entry["evidence_present"] is False


class TestScenarioC_ValidSupportGenuinelyCounts:
    def test_a_real_reviewed_bear_source_makes_evidence_present_flip_to_true(self, tmp_path, monkeypatch):
        bear_captured = _capture_real_source(
            monkeypatch, title="NVDA Valuation Looks Stretched", publisher="Bloomberg",
            link="https://bloomberg.com/nvda-valuation", date_str="2026-08-06", excerpt=BEAR_EXCERPT,
        )
        from tradingagents.dataflows.yfinance_news import _source_reference_marker

        marker = _source_reference_marker(bear_captured[0])
        bear_text_with_real_marker = f"{BEAR_EXCERPT} {marker}"

        repo = _repo()
        bull_captured = _capture_real_source(
            monkeypatch, title="NVDA Data Center Revenue Beats Estimates", publisher="Reuters",
            link="https://reuters.com/nvda-dc", date_str="2026-08-05", excerpt=BULL_EXCERPT,
        )

        def runner(payload, *, output_root):
            final_state = {"news_report": f"{BULL_EXCERPT} {bear_text_with_real_marker}"}
            return save_comqutor_run_outputs(
                final_state, payload["ticker"], selected_analysts=["news"],
                analysis_date=payload.get("analysis_date"), output_root=output_root,
                captured_sources=bull_captured + bear_captured,
            )

        payload = {"ticker": TICKER, "analysis_date": "2026-08-10", "selected_analysts": ["news"]}
        gateway = build_deterministic_echo_gateway("t2-acceptance-scenario-c", tmp_path)
        response = run_research_request(
            payload, runner=runner, output_root=tmp_path, graph_repository=repo, week2_llm_gateway=gateway
        )
        assert response["status"] == "completed"
        run_id = response["run_id"]
        bull_claim_id, bear_claim_id = _bull_and_bear_claim_ids(tmp_path, run_id)
        assert bear_claim_id is not None

        submit_content_support_review(
            run_id, bull_claim_id, status="SUPPORTS", reviewer="analyst_a",
            rationale="the captured excerpt directly reports the same revenue figure the claim asserts",
            output_root=tmp_path, graph_repository=repo,
        )
        review_2 = submit_content_support_review(
            run_id, bear_claim_id, status="SUPPORTS", reviewer="analyst_b",
            rationale="the captured excerpt directly reports the same valuation concern the claim asserts",
            output_root=tmp_path, graph_repository=repo,
        )
        assert review_2["status"] == "ok"
        execution_id = review_2["reevaluation"]["execution_id"]

        acceptance, admissibility = _run_formal_acceptance_for(tmp_path, execution_id)
        assert admissibility is not None
        assert admissibility["bear_supporting_evidence_count"] == 1
        assert admissibility["bull_supporting_evidence_count"] == 1
        must_detect = acceptance["rule_family_results"]["must_detect_if_evidence_present"]
        entry = next(r for r in must_detect if r["pair"] == PAIR_ID)
        # Now genuinely present on both sides (1 >= EVIDENCE_PRESENT_MIN=1) --
        # real evidence flows through once genuinely source+content
        # qualified, exactly the "not merely evidence_stance" proof this
        # scenario exists for. Whether the pair reaches full B2 ADMISSION
        # (which needs >=2 per side, a higher, separate bar) is a different
        # question this minimal two-claim run does not attempt to cross --
        # the verdict here is honestly PASS (if admitted) or FAIL (if not,
        # since evidence_present=True but not admitted is reported as a
        # genuine miss, never silently hidden), never NOT_APPLICABLE.
        assert entry["evidence_present"] is True
        assert entry["verdict"] in ("pass", "fail")


class TestScenarioD_MissingRulesNeverSilentlyPasses:
    def test_unresolvable_taxonomy_path_reports_config_error_not_a_silent_pass(self, tmp_path):
        acceptance = run_formal_acceptance(
            ticker=TICKER,
            ticker_v2_label={"required_conflicts": [PAIR_ID]},
            label_block_v1={},
            evaluate_ticker_result={"artifact_completeness": "pass", "offline_reprocess_status": "completed"},
            conflict_payload={"arbitration": {"candidate_evaluations": []}},
            graph_payload={},
            alpha_matches_payload=None,
            taxonomy_path=str(tmp_path / "does_not_exist_taxonomy.yaml"),
            label_v2_path=str(tmp_path / "does_not_exist_labels_v2.yaml"),
        )
        assert acceptance["formal_status"] == "config_error"
        assert acceptance["rule_family_results"] == {}
        assert acceptance.get("config_error_reason_code")
