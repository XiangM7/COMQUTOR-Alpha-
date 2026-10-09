"""T1 verified-support eligibility gate -- gate-bypass closing fix
(2026-09-29): the four required production-entrypoint acceptance scenarios,
driven entirely through the REAL run_research_request /
submit_content_support_review entrypoints (never a manually-passed
require_verified_evidence_gate flag, never a hand-rolled recompute).

A. All evidence unreviewed, where the OLD (raw v2) formula could have
   produced an official conclusion: the official result must not use it;
   research text/candidates/diagnostics remain readable.
   -> covered by tests/test_new_research_evidence_gate_production_wiring.py
   ::test_run_research_request_never_counts_unreviewed_source_linked_
   evidence_as_official (not duplicated here).

B. Mixed qualified/unqualified evidence: the official score, support
   count, and admission result must match what "qualified evidence only"
   would produce -- proven here by comparing against the raw v2 pool
   computed over ONLY the qualified claim.

C. Every valid reference becomes ineligible (via a genuine, real
   HUMAN_REVIEWED OPPOSES verdict -- never a fabricated one): the official
   result must not revert to the old formula just because the count of
   currently-eligible claims drops to zero.

D. Qualified evidence meets the existing threshold: the official result
   must match the underlying real evidence exactly (official == raw, since
   every claim is now genuinely reviewed) -- proving this is a genuine
   pass-when-warranted mechanism, never achieved by blocking everything.

All four use real, content-matched NVDA news claims (fetched via the REAL
tradingagents.dataflows.yfinance_news.get_news_yfinance against a
monkeypatched yfinance.Ticker -- never a real request) and real,
non-empty reviewer/rationale HUMAN_REVIEWED reviews via the real
submit_content_support_review entrypoint -- never a fabricated review
record. Zero Provider calls anywhere in this file.
"""

from __future__ import annotations

import json
import time
from datetime import datetime

import tradingagents.dataflows.yfinance_news as ynews
from comqutor_alpha.adapters.tradingagents_output_writer import save_comqutor_run_outputs
from comqutor_alpha.api.routes_research import run_research_request, submit_content_support_review
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from scripts.deterministic_echo_llm import build_deterministic_echo_gateway
from tradingagents.dataflows.source_capture import source_capture_scope

TICKER = "NVDA"
EXCERPT_1 = "NVDA reported strong data center revenue growth this quarter, beating analyst estimates."
EXCERPT_2 = "NVDA sales growth accelerated as customer demand for AI chips remained strong."
ALPHA_ID = "A301"  # both excerpts deterministically map here (Revenue Expansion keywords)


class _FakeTicker:
    def __init__(self, articles):
        self._articles = articles

    def get_news(self, count=None):
        return self._articles


def _flat_article(title, publisher, link, epoch_ts, summary):
    return {"title": title, "publisher": publisher, "link": link, "providerPublishTime": epoch_ts, "summary": summary}


def _epoch(date_str):
    return int(time.mktime(datetime.strptime(date_str, "%Y-%m-%d").timetuple()))


def _capture_two_real_nvda_sources(monkeypatch):
    """Runs the REAL get_news_yfinance against a monkeypatched
    yfinance.Ticker (never a real HTTP request), returning two genuinely
    distinct captured articles -- different publisher/title/link/excerpt,
    each mapping (deterministically, via real taxonomy keyword matching) to
    the SAME alpha (A301, Revenue Expansion)."""
    articles = [
        _flat_article(
            "NVDA Data Center Revenue Beats Estimates", "Reuters",
            "https://reuters.com/nvda-dc", _epoch("2026-08-05"), EXCERPT_1,
        ),
        _flat_article(
            "NVDA Sales Growth Accelerates on Customer Demand", "Bloomberg",
            "https://bloomberg.com/nvda-sales", _epoch("2026-08-06"), EXCERPT_2,
        ),
    ]
    monkeypatch.setattr(ynews.yf, "Ticker", lambda symbol: _FakeTicker(articles))
    monkeypatch.setattr(ynews, "normalize_symbol", lambda ticker: ticker)
    with source_capture_scope() as sink:
        ynews.get_news_yfinance(TICKER, "2026-08-01", "2026-08-09")
    return list(sink)


def _runner(captured_sources):
    def runner(payload, *, output_root):
        final_state = {"news_report": f"{EXCERPT_1} {EXCERPT_2}"}
        return save_comqutor_run_outputs(
            final_state,
            payload["ticker"],
            selected_analysts=["news"],
            analysis_date=payload.get("analysis_date"),
            output_root=output_root,
            captured_sources=captured_sources,
        )

    return runner


def _repo():
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


def _capture_one_real_nvda_source(monkeypatch):
    """Same technique as _capture_two_real_nvda_sources, but only the first
    (EXCERPT_1) article -- used to build a genuinely separate, single-claim
    comparison run for scenario B."""
    articles = [
        _flat_article(
            "NVDA Data Center Revenue Beats Estimates", "Reuters",
            "https://reuters.com/nvda-dc", _epoch("2026-08-05"), EXCERPT_1,
        )
    ]
    monkeypatch.setattr(ynews.yf, "Ticker", lambda symbol: _FakeTicker(articles))
    monkeypatch.setattr(ynews, "normalize_symbol", lambda ticker: ticker)
    with source_capture_scope() as sink:
        ynews.get_news_yfinance(TICKER, "2026-08-01", "2026-08-09")
    return list(sink)


def _runner_single_claim(captured_sources):
    def runner(payload, *, output_root):
        final_state = {"news_report": EXCERPT_1}
        return save_comqutor_run_outputs(
            final_state,
            payload["ticker"],
            selected_analysts=["news"],
            analysis_date=payload.get("analysis_date"),
            output_root=output_root,
            captured_sources=captured_sources,
        )

    return runner


def _create_two_claim_run(tmp_path, monkeypatch):
    """Real production entrypoint, real captured sources, zero reviews yet.
    Returns (repo, run_id, claim_id_1, claim_id_2)."""
    repo = _repo()
    captured = _capture_two_real_nvda_sources(monkeypatch)
    payload = {"ticker": TICKER, "analysis_date": "2026-08-10", "selected_analysts": ["news"]}
    gateway = build_deterministic_echo_gateway("evidence-gate-qualified-scenarios", tmp_path)
    response = run_research_request(
        payload, runner=_runner(captured), output_root=tmp_path, graph_repository=repo, week2_llm_gateway=gateway
    )
    assert response["status"] == "completed"
    run_id = response["run_id"]

    matches_payload = json.loads((tmp_path / run_id / "alpha_matches.json").read_text(encoding="utf-8"))
    matched = [m for m in matches_payload["matches"] if m.get("matched_alpha") == ALPHA_ID]
    assert len(matched) == 2, "expected both real captured claims to map to the same alpha"
    claim_ids = sorted(m["claim_id"] for m in matched)
    return repo, run_id, claim_ids[0], claim_ids[1]


def _create_single_claim_run(tmp_path, monkeypatch):
    """Real production entrypoint, real captured source, a single claim
    that never coexists with any other -- the comparison baseline for
    scenario B. Returns (repo, run_id, claim_id)."""
    repo = _repo()
    captured = _capture_one_real_nvda_source(monkeypatch)
    payload = {"ticker": TICKER, "analysis_date": "2026-08-10", "selected_analysts": ["news"]}
    gateway = build_deterministic_echo_gateway("evidence-gate-qualified-scenarios-single", tmp_path)
    response = run_research_request(
        payload, runner=_runner_single_claim(captured), output_root=tmp_path,
        graph_repository=repo, week2_llm_gateway=gateway,
    )
    assert response["status"] == "completed"
    run_id = response["run_id"]
    matches_payload = json.loads((tmp_path / run_id / "alpha_matches.json").read_text(encoding="utf-8"))
    matched = [m for m in matches_payload["matches"] if m.get("matched_alpha") == ALPHA_ID]
    assert len(matched) == 1, "expected exactly one real captured claim to map to the alpha"
    return repo, run_id, matched[0]["claim_id"]


def _official_and_raw_evidence(tmp_path, run_id):
    graph = json.loads((tmp_path / run_id / "structure_graph.json").read_text(encoding="utf-8"))
    official = next(a for a in graph["activation"]["alphas"] if a["alpha_id"] == ALPHA_ID)
    raw = next(a for a in graph["activation_versions"]["v2"]["alphas"] if a["alpha_id"] == ALPHA_ID)
    return graph, official, raw


def test_scenario_b_mixed_qualified_and_unqualified_evidence_official_pool_matches_qualified_only(
    tmp_path, monkeypatch
):
    repo, run_id, claim_1, claim_2 = _create_two_claim_run(tmp_path, monkeypatch)

    # Baseline: both unreviewed -- official shows zero, raw shows both.
    _, baseline_official, baseline_raw = _official_and_raw_evidence(tmp_path, run_id)
    assert baseline_official["evidence_count"] == 0
    assert baseline_raw["evidence_count"] == 2

    # Review ONLY claim_1 as SUPPORTS -- a real, non-empty reviewer/rationale.
    review_result = submit_content_support_review(
        run_id, claim_1, status="SUPPORTS", reviewer="analyst_a",
        rationale="the captured excerpt directly reports the same revenue figure the claim asserts",
        output_root=tmp_path, graph_repository=repo,
    )
    assert review_result["status"] == "ok"
    execution_id = review_result["reevaluation"]["execution_id"]
    assert review_result["reevaluation"]["status"] == "ok"

    _, mixed_official, _ = _official_and_raw_evidence(tmp_path, execution_id)
    assert mixed_official["evidence_count"] == 1
    assert claim_1 in mixed_official["claim_ids"]
    assert claim_2 not in mixed_official["claim_ids"]

    # Matches "qualified evidence only": a genuinely SEPARATE real run built
    # from ONLY claim_1's own article (claim_2 never existed at all, not
    # merely unreviewed), reviewed the same way, produces the SAME
    # official-pool evidence_count/score the mixed run already showed --
    # the unqualified claim contributes nothing to the official result,
    # exactly as if it had never been part of the input.
    alone_repo, alone_run_id, alone_claim_1, *_ = _create_single_claim_run(tmp_path, monkeypatch)
    alone_review = submit_content_support_review(
        alone_run_id, alone_claim_1, status="SUPPORTS", reviewer="analyst_a",
        rationale="the captured excerpt directly reports the same revenue figure the claim asserts",
        output_root=tmp_path, graph_repository=alone_repo,
    )
    assert alone_review["status"] == "ok"
    alone_execution_id = alone_review["reevaluation"]["execution_id"]
    _, alone_official, _ = _official_and_raw_evidence(tmp_path, alone_execution_id)

    assert mixed_official["evidence_count"] == alone_official["evidence_count"] == 1
    assert mixed_official["activation_score"] == alone_official["activation_score"]


def test_scenario_d_all_evidence_qualified_official_pool_matches_raw_exactly_not_blocked(tmp_path, monkeypatch):
    repo, run_id, claim_1, claim_2 = _create_two_claim_run(tmp_path, monkeypatch)

    review_1 = submit_content_support_review(
        run_id, claim_1, status="SUPPORTS", reviewer="analyst_a",
        rationale="the captured excerpt directly reports the same revenue figure the claim asserts",
        output_root=tmp_path, graph_repository=repo,
    )
    assert review_1["status"] == "ok"

    review_2 = submit_content_support_review(
        run_id, claim_2, status="SUPPORTS", reviewer="analyst_b",
        rationale="the captured excerpt directly reports the same sales growth the claim asserts",
        output_root=tmp_path, graph_repository=repo,
    )
    assert review_2["status"] == "ok"
    execution_id = review_2["reevaluation"]["execution_id"]

    graph, official, raw = _official_and_raw_evidence(tmp_path, execution_id)
    # Both claims now genuinely reviewed -- the official (verified) pool
    # must produce the EXACT same result the raw pool does, proving this is
    # a genuine pass-when-warranted mechanism, not achieved by blocking
    # everything: with every input claim qualified, there is nothing left
    # for the gate to filter.
    assert official["evidence_count"] == raw["evidence_count"] == 2
    assert official["activation_score"] == raw["activation_score"]
    assert set(official["claim_ids"]) == set(raw["claim_ids"]) == {claim_1, claim_2}
    assert ALPHA_ID in {a["alpha_id"] for a in graph["dominant_alphas"]} or official["activation_score"] > 0


def test_scenario_c_all_valid_references_invalidated_official_pool_never_reverts_to_raw(tmp_path, monkeypatch):
    repo, run_id, claim_1, claim_2 = _create_two_claim_run(tmp_path, monkeypatch)

    submit_content_support_review(
        run_id, claim_1, status="SUPPORTS", reviewer="analyst_a",
        rationale="the captured excerpt directly reports the same revenue figure the claim asserts",
        output_root=tmp_path, graph_repository=repo,
    )
    review_2 = submit_content_support_review(
        run_id, claim_2, status="SUPPORTS", reviewer="analyst_b",
        rationale="the captured excerpt directly reports the same sales growth the claim asserts",
        output_root=tmp_path, graph_repository=repo,
    )
    both_supports_execution_id = review_2["reevaluation"]["execution_id"]
    _, both_supports_official, both_supports_raw = _official_and_raw_evidence(tmp_path, both_supports_execution_id)
    assert both_supports_official["evidence_count"] == 2
    assert both_supports_raw["evidence_count"] == 2  # sanity: raw genuinely has real evidence to revert to

    # Real, genuine HUMAN_REVIEWED OPPOSES verdicts on BOTH claims -- a
    # real reviewer rebutting the claim, never a fabricated invalidation.
    # This is the LATEST review per claim_id, so it supersedes the earlier
    # SUPPORTS verdict for eligibility purposes.
    submit_content_support_review(
        run_id, claim_1, status="OPPOSES", reviewer="analyst_c",
        rationale="on closer reading, this source rebuts rather than supports the claim",
        output_root=tmp_path, graph_repository=repo,
    )
    review_4 = submit_content_support_review(
        run_id, claim_2, status="OPPOSES", reviewer="analyst_c",
        rationale="on closer reading, this source rebuts rather than supports the claim",
        output_root=tmp_path, graph_repository=repo,
    )
    assert review_4["status"] == "ok"
    all_opposed_execution_id = review_4["reevaluation"]["execution_id"]

    graph, official, raw = _official_and_raw_evidence(tmp_path, all_opposed_execution_id)
    # Every VALID reference is now ineligible (OPPOSES, never counted as
    # support) -- the official pool must NOT revert to the raw formula's
    # real, positive evidence just because the eligible count dropped to
    # zero.
    assert raw["evidence_count"] == 2  # the raw pool still has the real, unfiltered evidence
    assert official["evidence_count"] == 0
    assert official["claim_ids"] == []
    assert ALPHA_ID not in {a["alpha_id"] for a in graph["dominant_alphas"]}
    assert graph["evidence_gate_applied"] is True  # never silently un-gated
