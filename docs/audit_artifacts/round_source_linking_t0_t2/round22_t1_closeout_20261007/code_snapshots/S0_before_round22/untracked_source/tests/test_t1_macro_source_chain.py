"""T1 source-linking / evidence-support chain -- MACRO DATA (fourth and
final real chain, 2026-09-29 task-sheet Part 3, sequenced per direct user
instruction: market -> derived indicators -> financial -> macro, all
reusing the EXISTING source/review/gate/persistence framework -- no
parallel system per data type).

The real production entry point is tradingagents.dataflows.fred.
get_macro_data (called by news_analyst's own get_macro_indicators tool, so
macro claims are attributed to "news_agent" -- already covered by
LINKED_AGENT_COVERAGE, no extension needed here).

Disclosure-timing scope (deliberate, matches this round's own task-sheet
warning against treating an observation PERIOD as its disclosure time):
FRED's per-observation ``realtime_start`` field is used as the honest
published_at anchor when present -- it names when the CURRENTLY-displayed
value's vintage took effect, which for a never-since-revised observation
equals its true original release date, and for a revised one instead names
the latest revision (a real, inherent ambiguity, not resolved by guessing).
When the underlying response omits it entirely (as this codebase's own
pre-existing tests/test_fred.py fixtures already do), it is left None --
NEVER backfilled from the observation date -- and this is exercised
directly below as its own scenario, not silently skipped.

Exercises the REAL production function across every stage of the
macro-data chain:

    fetch (tradingagents.dataflows.fred.get_macro_data, monkeypatching only
    the external _request boundary -- the SAME technique tests/test_fred.py
    itself already established) -> source_capture -> source_registry.json
    (comqutor_alpha.source_provenance.build_source_registry) -> structured
    extraction (structured_output_adapter.save_structured_agent_outputs,
    llm_gateway=None -- fully deterministic, zero Provider calls) -> gate
    (verified_evidence_gate, unmodified) -> review
    (submit_content_support_review, unmodified) -> API
    (agent_output_reader.get_agent_outputs_response).

Zero Provider calls, zero network, zero TradingAgents graph invocation
anywhere in this file.
"""

from __future__ import annotations

import json
import re

import tradingagents.dataflows.fred as fred
from comqutor_alpha.api.agent_output_reader import get_agent_outputs_response
from comqutor_alpha.api.routes_research import run_research_request, submit_content_support_review
from comqutor_alpha.graph_engine.verified_evidence_gate import (
    ACTIVATION_V2_VERIFIED_FORMULA_VERSION,
)
from comqutor_alpha.source_provenance import build_source_registry
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from comqutor_alpha.storage.file_store import save_json_record
from comqutor_alpha.structure_engine.structured_output_adapter import save_structured_agent_outputs
from scripts.deterministic_echo_llm import build_deterministic_echo_gateway
from tradingagents.dataflows.source_capture import source_capture_scope

RUN_ID = "t1-macro-data-e2e-run"
TICKER = "NVDA"
ANALYSIS_DATE = "2026-08-10"

_META = {
    "seriess": [
        {
            "title": "Consumer Price Index",
            "units_short": "Index",
            "frequency": "Monthly",
            "seasonal_adjustment_short": "SA",
        }
    ]
}


def _obs(*, with_realtime_start: bool):
    base = [
        {"date": "2026-06-01", "value": "310.1"},
        {"date": "2026-07-01", "value": "311.4"},
    ]
    if with_realtime_start:
        for row in base:
            row["realtime_start"] = row["date"]
    return {"observations": base}


def _request_stub(meta=_META, obs=None, with_realtime_start=True):
    obs = obs if obs is not None else _obs(with_realtime_start=with_realtime_start)

    def _impl(path, params):
        if path == "series":
            return meta
        if path == "series/observations":
            return obs
        raise AssertionError(f"unexpected FRED path: {path}")

    return _impl


def _capture_real_macro_snapshot(monkeypatch, *, indicator="cpi", curr_date=ANALYSIS_DATE, with_realtime_start=True, obs=None):
    """Runs the REAL get_macro_data against a monkeypatched _request (never
    a real network request) inside a real source_capture_scope. Returns
    (report_text, captured_records)."""
    monkeypatch.setattr(fred, "_request", _request_stub(obs=obs, with_realtime_start=with_realtime_start))
    with source_capture_scope() as sink:
        report_text = fred.get_macro_data(indicator, curr_date)
    return report_text, list(sink)


def _write_run_fixture(tmp_path, *, agent_outputs, captured_sources, analysis_date=ANALYSIS_DATE, run_id=RUN_ID):
    save_json_record(
        run_id, "metadata.json",
        {"run_id": run_id, "ticker": TICKER, "analysis_date": analysis_date},
        output_root=str(tmp_path),
    )
    save_json_record(
        run_id, "raw_agent_outputs.json",
        {"schema_version": "raw.v1", "run_id": run_id, "ticker": TICKER, "agent_outputs": agent_outputs},
        output_root=str(tmp_path),
    )
    registry = None
    if captured_sources:
        registry = build_source_registry(
            run_id=run_id, ticker=TICKER, retrieved_at="2026-08-10T00:00:00Z", captured_records=captured_sources
        )
        save_json_record(run_id, "source_registry.json", registry, output_root=str(tmp_path))
    return registry


def _run_dir(tmp_path, run_id=RUN_ID):
    return tmp_path / run_id


class TestMacroDataScenarioA_ValidLinkPropagatesEndToEnd:
    def test_real_macro_snapshot_produces_a_valid_link_through_the_real_pipeline(self, tmp_path, monkeypatch):
        report_text, captured = _capture_real_macro_snapshot(monkeypatch)
        assert len(captured) == 1
        assert captured[0]["source_type"] == "macro"
        assert captured[0]["instrument"] == "CPIAUCSL"
        assert captured[0]["published_at"] == "2026-07-01"  # real realtime_start, not the observation date's own cutoff-conflating substitute
        assert captured[0]["observation_date"] == "2026-07-01"

        agent_outputs = [
            {
                "agent": "news_agent",
                "agent_output_id": f"{RUN_ID}:news_agent:news_report",
                "raw_output": report_text,
            }
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, captured_sources=captured)

        save_structured_agent_outputs(_run_dir(tmp_path), llm_gateway=None)

        persisted = json.loads((_run_dir(tmp_path) / "structured_agent_outputs.json").read_text())
        linked_records = [r for r in persisted["records"] if r.get("source_link_status") == "VALID"]
        assert linked_records, "expected the real macro snapshot to produce a VALID-linked claim"
        record = linked_records[0]
        assert record["linked_source_id"] is not None
        assert record["content_support_status"] == "PENDING_REVIEW"

        registry = json.loads((_run_dir(tmp_path) / "source_registry.json").read_text())
        source = registry["sources"][0]
        assert source["source_type"] == "macro"
        assert source["provider"] == "fred"
        assert source["instrument"] == "CPIAUCSL"
        assert source["unit"] == "Index"
        assert source["data_snapshot"]["value"] == "311.4"
        assert source["data_snapshot"]["realtime_start"] == "2026-07-01"

        response = get_agent_outputs_response(RUN_ID, output_root=str(tmp_path))
        assert response["status"] == "ok"
        api_record = next(r for r in response["structured_agent_outputs"] if r["claim_id"] == record["claim_id"])
        assert api_record["source_link_status"] == "VALID"
        assert api_record["linked_source"]["instrument"] == "CPIAUCSL"
        assert api_record["content_support_status"] == "PENDING_REVIEW"
        assert api_record["verified_support_diagnostic"]["category"] == "CONTENT_SUPPORT_PENDING_REVIEW"


class TestMacroDataScenarioB_GateAndReviewIntegration:
    def test_unreviewed_macro_claim_never_counts_as_official_but_review_makes_it_count(self, tmp_path, monkeypatch):
        """Full production-entrypoint integration: unreviewed real macro
        evidence is excluded from the OFFICIAL (verified) Activation pool
        exactly like an unreviewed news/market/financial claim -- proving
        the gate is genuinely source-type-agnostic -- and a real
        HUMAN_REVIEWED SUPPORTS review makes it count, through the SAME
        real run_research_request/submit_content_support_review
        entrypoints used throughout this whole round."""
        engine = build_engine("sqlite:///:memory:")
        apply_migrations(engine)
        repo = GraphPersistenceRepository(engine)

        report_text, captured = _capture_real_macro_snapshot(monkeypatch)
        marker_match = re.search(r"\[source_id: [^\]]+\] \[fragment_id: [^\]]+\]", report_text)
        assert marker_match, "expected the real macro report to carry a source/fragment marker"
        marker_text = marker_match.group(0)

        # The verified snapshot's own marker-bearing sentence is pure macro
        # data -- it has no alpha-relevant keyword content on its own. A
        # real news_analyst LLM would combine the verified figure with its
        # own analytical narrative in the SAME sentence (exactly what its
        # system prompt instructs); this reconstructs that combined
        # sentence directly, mirroring the market/financial chains' own
        # equivalent gate-integration tests.
        def runner(payload, *, output_root):
            from comqutor_alpha.adapters.tradingagents_output_writer import (
                save_comqutor_run_outputs,
            )

            final_state = {
                "news_report": (
                    "NVDA's revenue growth outlook remains constructive, supported by verified "
                    f"macro data showing resilient consumer price trends {marker_text}."
                ),
            }
            return save_comqutor_run_outputs(
                final_state, payload["ticker"], selected_analysts=["news"],
                analysis_date=payload.get("analysis_date"), output_root=output_root,
                captured_sources=captured,
            )

        gateway = build_deterministic_echo_gateway("macro-data-gate-integration-test", tmp_path)
        payload = {"ticker": TICKER, "analysis_date": ANALYSIS_DATE, "selected_analysts": ["news"]}
        response = run_research_request(
            payload, runner=runner, output_root=tmp_path, graph_repository=repo, week2_llm_gateway=gateway
        )
        assert response["status"] == "completed"
        run_id = response["run_id"]

        agent_outputs = get_agent_outputs_response(run_id, output_root=tmp_path, graph_repository=repo)
        linked = [r for r in agent_outputs["structured_agent_outputs"] if r.get("source_link_status") == "VALID"]
        assert linked, "expected the real verified macro snapshot to produce a VALID-linked claim"
        record = linked[0]
        assert record["verified_support_diagnostic"]["category"] == "CONTENT_SUPPORT_PENDING_REVIEW"

        graph = json.loads((tmp_path / run_id / "structure_graph.json").read_text(encoding="utf-8"))
        assert graph["evidence_gate_applied"] is True
        assert graph["primary_activation_version"] == ACTIVATION_V2_VERIFIED_FORMULA_VERSION
        matches_payload = json.loads((tmp_path / run_id / "alpha_matches.json").read_text(encoding="utf-8"))
        matched = next((m for m in matches_payload["matches"] if m.get("matched_alpha")), None)
        assert matched, "expected at least one claim to have a real matched_alpha"
        alpha_id = matched["matched_alpha"]
        official_before = next(a for a in graph["activation"]["alphas"] if a["alpha_id"] == alpha_id)
        raw_before = next(a for a in graph["activation_versions"]["v2"]["alphas"] if a["alpha_id"] == alpha_id)
        assert raw_before["evidence_count"] > 0
        assert official_before["evidence_count"] == 0  # unreviewed macro evidence never counts officially

        review_result = submit_content_support_review(
            run_id, record["claim_id"], status="SUPPORTS", reviewer="analyst_a",
            rationale="the verified macro snapshot directly reports this same data point",
            output_root=tmp_path, graph_repository=repo,
        )
        assert review_result["status"] == "ok"
        assert review_result["reevaluation"]["status"] == "ok"
        execution_id = review_result["reevaluation"]["execution_id"]

        execution_graph = json.loads((tmp_path / execution_id / "structure_graph.json").read_text(encoding="utf-8"))
        official_after = next(a for a in execution_graph["activation"]["alphas"] if a["alpha_id"] == alpha_id)
        assert official_after["evidence_count"] == 1  # now counts, once genuinely reviewed


class TestMacroDataScenarioC_InvalidReferencesAreRejectedOrDowngraded:
    def test_a_forged_marker_that_does_not_resolve_in_this_runs_registry_is_never_trusted(self, tmp_path, monkeypatch):
        """Mirrors the market/financial chains' own forged-marker test: a
        fragment_id with the correct shape that was never actually
        captured by THIS run must never be trusted."""
        from comqutor_alpha.source_provenance import validate_source_reference

        _, captured = _capture_real_macro_snapshot(monkeypatch)
        registry = build_source_registry(
            run_id=RUN_ID, ticker=TICKER, retrieved_at="2026-08-10T00:00:00Z", captured_records=captured
        )
        forged_result = validate_source_reference(
            "src_deadbeefdeadbeef:frag:0", sources=registry["sources"], evidence_cutoff=ANALYSIS_DATE
        )
        assert forged_result["source_link_status"] == "UNKNOWN_ID"
        assert forged_result["linked_source_id"] is None

        agent_outputs = [
            {
                "agent": "news_agent",
                "agent_output_id": f"{RUN_ID}:news_agent:news_report",
                "raw_output": (
                    "NVDA is showing strong revenue growth momentum "
                    "[fragment_id: src_deadbeefdeadbeef:frag:0]."
                ),
            }
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, captured_sources=captured)
        save_structured_agent_outputs(_run_dir(tmp_path), llm_gateway=None)

        persisted = json.loads((_run_dir(tmp_path) / "structured_agent_outputs.json").read_text())
        forged = next(r for r in persisted["records"] if "deadbeef" in r["claim"])
        assert forged["source_link_status"] == "NOT_PROVIDED"
        assert forged["linked_source_id"] is None
        assert forged["content_support_status"] == "NOT_APPLICABLE"

    def test_a_macro_snapshot_observed_after_the_evidence_cutoff_is_rejected_never_used_as_look_ahead(
        self, tmp_path, monkeypatch
    ):
        """Time-out-of-bounds: this run's own analysis_date (evidence
        cutoff) is set BEFORE the captured observation's own realtime_start
        -- validate_source_reference must independently reject it as
        TIME_INVALID, the same check already proven for news/market/
        financial data, now proven source-type-agnostic for macro data
        too."""
        report_text, captured = _capture_real_macro_snapshot(monkeypatch)
        agent_outputs = [
            {
                "agent": "news_agent",
                "agent_output_id": f"{RUN_ID}:news_agent:news_report",
                "raw_output": report_text,
            }
        ]
        # The original run's own evidence cutoff (analysis_date) predates
        # the captured observation's own realtime_start (2026-07-01).
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, captured_sources=captured, analysis_date="2026-06-15")
        save_structured_agent_outputs(_run_dir(tmp_path), llm_gateway=None)

        persisted = json.loads((_run_dir(tmp_path) / "structured_agent_outputs.json").read_text())
        linked_or_time_invalid = [
            r for r in persisted["records"] if r.get("source_link_status") in ("VALID", "TIME_INVALID")
        ]
        assert linked_or_time_invalid, "expected the marker to at least resolve an identity"
        assert all(r["source_link_status"] == "TIME_INVALID" for r in linked_or_time_invalid)
        assert all(r["content_support_status"] == "NOT_APPLICABLE" for r in linked_or_time_invalid)

    def test_missing_disclosure_timing_is_recorded_as_unavailable_never_self_completed_from_observation_period(
        self, tmp_path, monkeypatch
    ):
        """The task sheet's own explicit macro requirement: 'frozen
        material lacking disclosure timing must not be self-completed to
        satisfy the evidence cutoff.' When FRED's own response omits
        realtime_start entirely (exactly this codebase's own pre-existing
        tests/test_fred.py fixtures), the captured record must show
        published_at/realtime_start as None -- NEVER silently defaulted to
        the observation's own date, which would fabricate a disclosure
        timestamp out of an observation period."""
        _, captured = _capture_real_macro_snapshot(monkeypatch, with_realtime_start=False)
        source = captured[0]
        assert source["published_at"] is None
        assert source["observation_date"] == "2026-07-01"
        assert source["data_snapshot"]["realtime_start"] is None
        assert source["data_snapshot"]["value"] == "311.4"

    def test_underlying_macro_value_changing_after_a_review_is_detected_never_silently_carried_forward(
        self, tmp_path, monkeypatch
    ):
        """Value consistency as this framework can actually enforce it: a
        review is bound to the source's content_hash AT REVIEW TIME -- if
        the underlying macro series is later revised (a common, expected
        real-world occurrence for FRED data), the SAME claim_id's review no
        longer matches the CURRENT source content_hash and must be
        reported as stale. Mirrors the market/financial chains' own
        content-version-changed test."""
        from comqutor_alpha.source_provenance import (
            SOURCE_LINK_VALID,
            apply_content_support_review,
            compute_verified_support_eligibility,
            resolve_fragment_by_id,
        )

        _, captured = _capture_real_macro_snapshot(monkeypatch)
        registry = build_source_registry(
            run_id=RUN_ID, ticker=TICKER, retrieved_at="2026-08-10T00:00:00Z", captured_records=captured
        )
        source = registry["sources"][0]
        record = {
            "claim_id": f"{RUN_ID}:news_agent:claim:1",
            "run_id": RUN_ID, "ticker": TICKER, "agent": "news_agent",
            "claim": "NVDA's macro backdrop remains constructive per verified CPI data.",
            "evidence": "NVDA's macro backdrop remains constructive per verified CPI data.",
            "entities": [], "factors": [], "direction": "positive", "confidence": 0.8,
            "source_link_status": SOURCE_LINK_VALID,
            "linked_source_id": source["fragment_id"],
        }
        reviewed = apply_content_support_review(
            record, status="SUPPORTS", reviewer="analyst_a",
            rationale="matches the verified macro snapshot's own reported value",
            reviewed_at="2026-08-10T12:00:00Z", sources=registry["sources"],
        )
        assert reviewed["content_support_review"]["content_hash"] == source["content_hash"]

        # A later revision to the same observation (the SAME series/date
        # identity, but a genuinely different reported value -- a routine,
        # expected FRED occurrence) yields a DIFFERENT content_hash.
        revised_obs = _obs(with_realtime_start=True)
        revised_obs["observations"][-1]["value"] = "312.9"
        _, revised_captured = _capture_real_macro_snapshot(monkeypatch, obs=revised_obs)
        revised_registry = build_source_registry(
            run_id=RUN_ID, ticker=TICKER, retrieved_at="2026-08-10T13:00:00Z", captured_records=revised_captured
        )
        revised_source = resolve_fragment_by_id(source["fragment_id"], revised_registry["sources"])
        assert revised_source is not None
        assert revised_source["content_hash"] != source["content_hash"]

        eligibility = compute_verified_support_eligibility(reviewed, revised_registry["sources"])
        assert eligibility["eligible"] is False
        assert eligibility["reason_code"] == "CONTENT_VERSION_CHANGED_SINCE_REVIEW"
