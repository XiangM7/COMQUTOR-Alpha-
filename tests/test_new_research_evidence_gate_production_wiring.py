"""T1 verified-support eligibility gate -- closing fix (2026-09-29): the
normal new-research PRODUCTION entrypoint (``routes_research.
run_research_request``) now sets ``require_verified_evidence_gate=True``
too, not just re-evaluation. Every test here drives the REAL
``run_research_request`` top-level function (never ``_run_week3_graph_
pipeline`` called directly with a manually-passed flag, except in the one
test explicitly documented as an exception below) -- proving the actual
upstream production entrypoint genuinely threads the flag through and it
takes effect, not merely that the underlying gate mechanism works when
asked to (already proven in tests/test_content_support_review_endpoint.py).

Zero Provider calls anywhere in this file: every fixture uses either
``offline_raw_agent_outputs`` (no LLM, no network) or a ``runner=`` that
calls the real ``save_comqutor_run_outputs`` with a ``final_state`` built
from a REAL captured news source -- fetched via the real ``tradingagents.
dataflows.yfinance_news.get_news_yfinance`` against a monkeypatched
``yfinance.Ticker`` (never a real HTTP request), exactly the same technique
``tests/test_t1_source_linking_pipeline.py`` already uses. Alpha
classification uses ``scripts.deterministic_echo_llm``'s real, deterministic
``Week2LLMGateway`` double -- a genuine gateway object, zero real Provider
calls.
"""

from __future__ import annotations

import json

import tradingagents.dataflows.yfinance_news as ynews
from comqutor_alpha.adapters.tradingagents_output_writer import save_comqutor_run_outputs
from comqutor_alpha.api.agent_output_reader import get_agent_outputs_response
from comqutor_alpha.api.routes_research import (
    _run_week3_graph_pipeline,
    run_research_request,
)
from comqutor_alpha.graph_engine.verified_evidence_gate import (
    ACTIVATION_V2_VERIFIED_FORMULA_VERSION,
    EVIDENCE_GATE_POLICY_VERSION,
    EVIDENCE_GATE_VERSION,
)
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from comqutor_alpha.storage.file_store import load_json_record_if_exists
from scripts.deterministic_echo_llm import build_deterministic_echo_gateway
from tradingagents.dataflows.source_capture import source_capture_scope

TICKER = "NVDA"
NVDA_EXCERPT = "NVDA reported strong data center revenue growth this quarter, beating analyst estimates."


def _repo():
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


class _FakeTicker:
    def __init__(self, articles):
        self._articles = articles

    def get_news(self, count=None):
        return self._articles


def _flat_article(title, publisher, link, epoch_ts, summary):
    return {
        "title": title,
        "publisher": publisher,
        "link": link,
        "providerPublishTime": epoch_ts,
        "summary": summary,
    }


def _epoch(date_str):
    import time
    from datetime import datetime

    return int(time.mktime(datetime.strptime(date_str, "%Y-%m-%d").timetuple()))


def _capture_real_nvda_source(monkeypatch):
    """Runs the REAL tradingagents.dataflows.yfinance_news.get_news_yfinance
    against a monkeypatched yfinance.Ticker (never a real HTTP request) and
    returns the genuinely-captured record list -- exactly as
    tradingagents_output_writer.save_comqutor_run_outputs would receive it
    from a real source_capture_scope() during a real run. Mirrors tests/
    test_t1_source_linking_pipeline.py's own fixture builder."""
    articles = [
        _flat_article(
            "NVDA Data Center Revenue Beats Estimates", "Reuters",
            "https://reuters.com/nvda-dc", _epoch("2026-08-05"), NVDA_EXCERPT,
        )
    ]
    monkeypatch.setattr(ynews.yf, "Ticker", lambda symbol: _FakeTicker(articles))
    monkeypatch.setattr(ynews, "normalize_symbol", lambda ticker: ticker)
    with source_capture_scope() as sink:
        ynews.get_news_yfinance(TICKER, "2026-08-01", "2026-08-09")
    return list(sink)


def _runner_with_source_linked_news_claim(captured_sources):
    """A real ``runner=`` callable for run_research_request: calls the REAL
    save_comqutor_run_outputs (never a hand-rolled artifact writer) with a
    ``final_state`` whose news_report contains the EXACT captured excerpt
    text (so the real structured_output_adapter's content-match source-
    linking resolves it against the ALSO-real, captured_sources-built
    source_registry.json -- the same mechanism tests/test_t1_source_linking
    _pipeline.py's own Scenario A test already proves end to end)."""

    def runner(payload, *, output_root):
        final_state = {
            "news_report": f"{NVDA_EXCERPT} Shares rallied on the news.",
        }
        return save_comqutor_run_outputs(
            final_state,
            payload["ticker"],
            selected_analysts=["news"],
            analysis_date=payload.get("analysis_date"),
            output_root=output_root,
            captured_sources=captured_sources,
        )

    return runner


def test_run_research_request_never_lets_missing_source_type_coverage_restore_the_old_official_pool(tmp_path):
    """2026-09-29 gate-bypass correction: 'whether sources need reading' and
    'whether evidence is qualified' are different questions -- a claim with
    NO source-linked claims at all (e.g. a pure market_agent claim; every
    non-news chain has no real source-linking wired up yet) must NOT let
    the OFFICIAL pool silently fall back to the raw, unfiltered v2 formula.
    The gate still applies (evidence_gate_applied=True, v2_verified
    present, policy version persisted) and still honestly reports ZERO
    verified evidence for this run (source_link_status=NOT_PROVIDED never
    counts as verified support) -- proven the same way as the news scenario
    below: the raw v2 pool DOES see the real, unfiltered evidence, but the
    official pool does not."""
    repo = _repo()
    payload = {
        "ticker": TICKER,
        "analysis_date": "2026-06-30",
        "selected_analysts": ["market"],
        "offline_raw_agent_outputs": [
            {"agent": "market_agent", "raw_output": "NVDA datacenter revenue growth is accelerating."}
        ],
    }
    gateway = build_deterministic_echo_gateway("new-research-gate-policy-test", tmp_path)
    response = run_research_request(
        payload, output_root=tmp_path, graph_repository=repo, week2_llm_gateway=gateway
    )
    assert response["status"] == "completed"

    graph = json.loads((tmp_path / response["run_id"] / "structure_graph.json").read_text(encoding="utf-8"))
    assert graph["evidence_gate_required"] is True
    assert graph["evidence_gate_policy_version"] == EVIDENCE_GATE_POLICY_VERSION
    assert graph["evidence_gate_applied"] is True
    assert graph["evidence_gate_version"] == EVIDENCE_GATE_VERSION
    assert "v2_verified" in graph["activation_versions"]
    assert graph["primary_activation_version"] == ACTIVATION_V2_VERIFIED_FORMULA_VERSION

    matches_payload = json.loads(
        (tmp_path / response["run_id"] / "alpha_matches.json").read_text(encoding="utf-8")
    )
    matched = next(m for m in matches_payload["matches"] if m.get("matched_alpha"))
    alpha_id = matched["matched_alpha"]
    official_entry = next(a for a in graph["activation"]["alphas"] if a["alpha_id"] == alpha_id)
    raw_v2_entry = next(a for a in graph["activation_versions"]["v2"]["alphas"] if a["alpha_id"] == alpha_id)
    assert raw_v2_entry["evidence_count"] > 0  # the real, unfiltered evidence genuinely exists
    assert official_entry["evidence_count"] == 0  # never counted officially -- not source-linked/reviewed
    assert alpha_id not in {a["alpha_id"] for a in graph["dominant_alphas"]}


def test_run_research_request_never_counts_unreviewed_source_linked_evidence_as_official(tmp_path, monkeypatch):
    """The central scenario: a brand-new run with a REAL, content-matched,
    source-linked news claim that has never been reviewed. The claim/
    candidate still displays normally through the real page-facing API, but
    the OFFICIAL Activation result must not count it as verified support --
    proven by comparing the OFFICIAL (verified) pool's evidence_count
    against the RAW v2 pool's own (which does see the real, unfiltered
    evidence), so this is a genuine filtering effect, not merely "no
    evidence was extracted at all"."""
    repo = _repo()
    captured = _capture_real_nvda_source(monkeypatch)
    payload = {"ticker": TICKER, "analysis_date": "2026-08-10", "selected_analysts": ["news"]}
    gateway = build_deterministic_echo_gateway("new-research-unreviewed-evidence-test", tmp_path)

    response = run_research_request(
        payload,
        runner=_runner_with_source_linked_news_claim(captured),
        output_root=tmp_path,
        graph_repository=repo,
        week2_llm_gateway=gateway,
    )
    assert response["status"] == "completed"
    run_id = response["run_id"]

    # Content and pending-review candidates still display normally through
    # the real page-facing agent-outputs API.
    agent_outputs = get_agent_outputs_response(run_id, output_root=tmp_path, graph_repository=repo)
    assert agent_outputs["status"] == "ok"
    linked_records = [r for r in agent_outputs["structured_agent_outputs"] if r.get("source_link_status") == "VALID"]
    assert linked_records, "expected the real captured NVDA source to produce a VALID-linked claim"
    record = linked_records[0]
    assert record["content_support_status"] == "PENDING_REVIEW"
    # Never reviewed: the record's own content_support_review sub-dict
    # (present for every source-linked claim, reviewed or not) shows no
    # HUMAN_REVIEWED method yet.
    assert (record.get("content_support_review") or {}).get("method") != "HUMAN_REVIEWED"

    # This run's own persisted execution config names the new REQUIRED
    # policy explicitly.
    graph = json.loads((tmp_path / run_id / "structure_graph.json").read_text(encoding="utf-8"))
    assert graph["evidence_gate_required"] is True
    assert graph["evidence_gate_policy_version"] == EVIDENCE_GATE_POLICY_VERSION
    assert graph["evidence_gate_applied"] is True
    assert graph["evidence_gate_version"] == EVIDENCE_GATE_VERSION
    assert graph["primary_activation_version"] == ACTIVATION_V2_VERIFIED_FORMULA_VERSION

    alpha_id = record["eligible_candidates"][0]["alpha_id"] if record.get("eligible_candidates") else None
    matches_payload = json.loads((tmp_path / run_id / "alpha_matches.json").read_text(encoding="utf-8"))
    if alpha_id is None:
        matched = next((m for m in matches_payload["matches"] if m.get("matched_alpha")), None)
        assert matched, "expected at least one claim to have a real matched_alpha"
        alpha_id = matched["matched_alpha"]

    official_entry = next(a for a in graph["activation"]["alphas"] if a["alpha_id"] == alpha_id)
    raw_v2_entry = next(a for a in graph["activation_versions"]["v2"]["alphas"] if a["alpha_id"] == alpha_id)
    # The genuine, unfiltered evidence really exists in the raw pool...
    assert raw_v2_entry["evidence_count"] > 0
    # ...but never counts as OFFICIAL support while unreviewed -- this is
    # the gate genuinely filtering, not merely "no evidence extracted".
    assert official_entry["evidence_count"] == 0
    assert alpha_id not in {a["alpha_id"] for a in graph["dominant_alphas"]}


def test_missing_source_registry_after_a_new_runs_valid_link_fails_explicitly_never_a_silent_old_formula_pass(
    tmp_path, monkeypatch
):
    """The 'missing source input must not silently fall back to the old
    formula' requirement, for the NEW-RESEARCH entrypoint's own data: takes
    a run that run_research_request itself already produced (with a real
    VALID-linked claim -- the SAME fixture the previous test proves the
    wiring on), then simulates the registry becoming unavailable by the
    time Week 3 needs it (e.g. a corrupted/lost artifact -- this exact
    input-loss scenario cannot be produced through one atomic run_research_
    request call, since source-linking and Week 3 both happen inside it, so
    this re-invokes _run_week3_graph_pipeline directly with the SAME
    require_verified_evidence_gate=True run_research_request itself now
    hardcodes -- the wiring claim itself is proven by the test above, not
    here)."""
    repo = _repo()
    captured = _capture_real_nvda_source(monkeypatch)
    payload = {"ticker": TICKER, "analysis_date": "2026-08-10", "selected_analysts": ["news"]}
    gateway = build_deterministic_echo_gateway("new-research-missing-source-test", tmp_path)

    response = run_research_request(
        payload,
        runner=_runner_with_source_linked_news_claim(captured),
        output_root=tmp_path,
        graph_repository=repo,
        week2_llm_gateway=gateway,
    )
    assert response["status"] == "completed"
    run_id = response["run_id"]
    run_dir = tmp_path / run_id

    original_graph = json.loads((run_dir / "structure_graph.json").read_text(encoding="utf-8"))
    assert original_graph["evidence_gate_applied"] is True  # sanity: the fixture really did link+gate

    (run_dir / "source_registry.json").unlink()

    _run_week3_graph_pipeline(run_dir, graph_repository=repo, require_verified_evidence_gate=True)

    status = load_json_record_if_exists(run_id, "week3_pipeline_status.json", output_root=tmp_path)
    assert status.get("outcome") == "failed"
    assert status.get("stage") == "evidence_gate_required_input_unavailable"

    # The original, genuinely-gated structure_graph.json was never
    # overwritten by a silent, old-formula "official PASS" fallback.
    unchanged_graph = json.loads((run_dir / "structure_graph.json").read_text(encoding="utf-8"))
    assert unchanged_graph == original_graph
