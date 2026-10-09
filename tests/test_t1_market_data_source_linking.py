"""T1 source-linking / evidence-support chain -- MARKET DATA (second real
chain after news, 2026-09-29 task-sheet Part 3, sequenced first per direct
user instruction: market -> derived indicators -> financial -> macro, all
reusing the EXISTING source/review/gate/persistence framework -- no
parallel system per data type).

Exercises the REAL production functions across every stage of the market-
data chain:

    fetch (tradingagents.dataflows.market_data_validator.
    build_verified_market_snapshot, the SAME deterministic "ground truth"
    tool the real market_analyst is instructed to treat as authoritative)
    -> source_capture -> source_registry.json (comqutor_alpha.
    source_provenance.build_source_registry, the SAME SourceRecord shape
    extended with instrument/observation_date/timezone/unit/data_snapshot)
    -> structured extraction (structured_output_adapter.
    save_structured_agent_outputs, llm_gateway=None -- fully deterministic,
    zero Provider calls) -> gate (verified_evidence_gate, unmodified) ->
    review (submit_content_support_review, unmodified) -> API
    (agent_output_reader.get_agent_outputs_response).

Every fixture is a real, hand-built OHLCV DataFrame fed through the REAL
build_verified_market_snapshot via monkeypatch.setattr(validator,
"load_ohlcv", ...) -- the SAME external-boundary-only mocking technique
tests/test_market_data_validator.py already established -- never a claim
that a model's semantic accuracy has been validated. Zero Provider calls,
zero network, zero TradingAgents graph invocation anywhere in this file.
"""

from __future__ import annotations

import json
import re

import pandas as pd

import tradingagents.dataflows.market_data_validator as validator
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

RUN_ID = "t1-market-data-e2e-run"
TICKER = "NVDA"
ANALYSIS_DATE = "2026-08-10"


def _sample_ohlcv() -> pd.DataFrame:
    dates = pd.bdate_range("2026-06-01", ANALYSIS_DATE)
    closes = [400.0 + i * 0.75 for i in range(len(dates))]
    return pd.DataFrame({
        "Date": dates,
        "Open": [c - 1.0 for c in closes],
        "High": [c + 2.0 for c in closes],
        "Low": [c - 2.0 for c in closes],
        "Close": closes,
        "Volume": [30_000_000 + i * 1000 for i in range(len(dates))],
    })


def _capture_real_market_snapshot(monkeypatch, *, symbol=TICKER, curr_date=ANALYSIS_DATE, ohlcv=None):
    """Runs the REAL build_verified_market_snapshot against a monkeypatched
    load_ohlcv (never a real network request) inside a real source_capture_
    scope. Returns (snapshot_text, captured_records)."""
    monkeypatch.setattr(validator, "load_ohlcv", lambda s, d: ohlcv if ohlcv is not None else _sample_ohlcv())
    with source_capture_scope() as sink:
        snapshot_text = validator.build_verified_market_snapshot(symbol, curr_date)
    return snapshot_text, list(sink)


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


class TestMarketDataScenarioA_ValidLinkPropagatesEndToEnd:
    def test_real_verified_snapshot_produces_a_valid_link_through_the_real_pipeline(self, tmp_path, monkeypatch):
        snapshot_text, captured = _capture_real_market_snapshot(monkeypatch)
        assert len(captured) == 1
        assert captured[0]["source_type"] == "market"
        assert captured[0]["instrument"] == TICKER

        # Simulates the market_analyst LLM having preserved the marker
        # verbatim while writing its own prose report -- exactly the fixed,
        # offline boundary tests/test_t1_source_linking_pipeline.py's own
        # Scenario A already established for news (real, deterministic tool
        # output as the "agent report", never a real LLM call).
        agent_outputs = [
            {
                "agent": "market_agent",
                "agent_output_id": f"{RUN_ID}:market_agent:market_report",
                "raw_output": (
                    f"{snapshot_text}\n\nNVDA's close moved higher through the verified window, "
                    "consistent with sustained buying interest."
                ),
            }
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, captured_sources=captured)

        save_structured_agent_outputs(_run_dir(tmp_path), llm_gateway=None)

        persisted = json.loads((_run_dir(tmp_path) / "structured_agent_outputs.json").read_text())
        linked_records = [r for r in persisted["records"] if r.get("source_link_status") == "VALID"]
        assert linked_records, "expected the real verified snapshot to produce a VALID-linked claim"
        record = linked_records[0]
        assert record["linked_source_id"] is not None
        assert record["content_support_status"] == "PENDING_REVIEW"

        registry = json.loads((_run_dir(tmp_path) / "source_registry.json").read_text())
        source = registry["sources"][0]
        assert source["source_type"] == "market"
        assert source["provider"] == "yfinance"
        assert source["instrument"] == TICKER
        assert source["timezone"] == "America/New_York"
        assert source["unit"] == "USD"
        assert source["data_snapshot"]["ohlcv"]["Close"]
        assert source["data_snapshot"]["indicators"]

        # API response must show the SAME status/reference, plus the new
        # market-specific fields, for the SAME persisted claim.
        response = get_agent_outputs_response(RUN_ID, output_root=str(tmp_path))
        assert response["status"] == "ok"
        api_record = next(r for r in response["structured_agent_outputs"] if r["claim_id"] == record["claim_id"])
        assert api_record["source_link_status"] == "VALID"
        assert api_record["linked_source"]["instrument"] == TICKER
        assert api_record["linked_source"]["unit"] == "USD"
        assert api_record["content_support_status"] == "PENDING_REVIEW"
        assert api_record["verified_support_diagnostic"]["category"] == "CONTENT_SUPPORT_PENDING_REVIEW"


class TestMarketDataScenarioB_GateAndReviewIntegration:
    def test_unreviewed_market_claim_never_counts_as_official_but_review_makes_it_count(self, tmp_path, monkeypatch):
        """Full production-entrypoint integration: unreviewed real market
        evidence is excluded from the OFFICIAL (verified) Activation pool
        exactly like an unreviewed news claim -- proving the gate is
        genuinely source-type-agnostic, not something re-implemented per
        chain -- and a real HUMAN_REVIEWED SUPPORTS review makes it count,
        through the SAME real run_research_request/submit_content_support_
        review entrypoints used throughout this whole round."""
        engine = build_engine("sqlite:///:memory:")
        apply_migrations(engine)
        repo = GraphPersistenceRepository(engine)

        snapshot_text, captured = _capture_real_market_snapshot(monkeypatch)
        # The verified snapshot's own marker-bearing sentence is pure price
        # data (Open/High/Low/Close/Volume) -- it has no alpha-relevant
        # keyword content on its own, so it never gets a matched_alpha. A
        # real market_analyst LLM would COMBINE the verified numbers with
        # its own analytical narrative in the SAME sentence (exactly what
        # its system prompt instructs); this reconstructs that combined
        # sentence directly so the ONE claim that resolves the marker ALSO
        # matches a real alpha -- otherwise reviewing the linked (but
        # alpha-less) claim would never move any alpha's evidence_count at
        # all, which would prove nothing about the gate.
        marker_match = re.search(r"\[source_id: [^\]]+\] \[fragment_id: [^\]]+\]", snapshot_text)
        assert marker_match, "expected the real snapshot text to carry a source/fragment marker"
        marker_text = marker_match.group(0)

        def runner(payload, *, output_root):
            from comqutor_alpha.adapters.tradingagents_output_writer import (
                save_comqutor_run_outputs,
            )

            final_state = {
                "market_report": (
                    "NVDA's revenue growth outlook remains constructive, supported by the verified "
                    f"snapshot showing sustained trading momentum {marker_text}."
                ),
            }
            return save_comqutor_run_outputs(
                final_state, payload["ticker"], selected_analysts=["market"],
                analysis_date=payload.get("analysis_date"), output_root=output_root,
                captured_sources=captured,
            )

        gateway = build_deterministic_echo_gateway("market-data-gate-integration-test", tmp_path)
        payload = {"ticker": TICKER, "analysis_date": ANALYSIS_DATE, "selected_analysts": ["market"]}
        response = run_research_request(
            payload, runner=runner, output_root=tmp_path, graph_repository=repo, week2_llm_gateway=gateway
        )
        assert response["status"] == "completed"
        run_id = response["run_id"]

        agent_outputs = get_agent_outputs_response(run_id, output_root=tmp_path, graph_repository=repo)
        linked = [r for r in agent_outputs["structured_agent_outputs"] if r.get("source_link_status") == "VALID"]
        assert linked, "expected the real verified market snapshot to produce a VALID-linked claim"
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
        assert official_before["evidence_count"] == 0  # unreviewed market evidence never counts officially

        review_result = submit_content_support_review(
            run_id, record["claim_id"], status="SUPPORTS", reviewer="analyst_a",
            rationale="the verified market snapshot directly reports this same trading data",
            output_root=tmp_path, graph_repository=repo,
        )
        assert review_result["status"] == "ok"
        assert review_result["reevaluation"]["status"] == "ok"
        execution_id = review_result["reevaluation"]["execution_id"]

        execution_graph = json.loads((tmp_path / execution_id / "structure_graph.json").read_text(encoding="utf-8"))
        official_after = next(a for a in execution_graph["activation"]["alphas"] if a["alpha_id"] == alpha_id)
        assert official_after["evidence_count"] == 1  # now counts, once genuinely reviewed


class TestMarketDataScenarioC_InvalidReferencesAreRejectedOrDowngraded:
    def test_a_forged_marker_that_does_not_resolve_in_this_runs_registry_is_never_trusted(self, tmp_path, monkeypatch):
        """'Validate the reference belongs to this run's own allowed input'
        -- a fragment_id that looks real (correct shape) but was never
        actually captured by THIS run must never be trusted. Two levels:

        (1) End-to-end (exactly mirroring tests/test_t1_source_linking_
        pipeline.py's own equivalent test): a forged FREE-TEXT marker with
        no other resolvable reference in the same claim text falls through
        every candidate method (explicit marker -> content-match) and ends
        at NOT_PROVIDED, the same "never silently accepted" outcome the
        news chain's own forged-marker test already established -- a
        forged marker is never itself suficient to produce a link, whether
        the final status names it NOT_PROVIDED (nothing else resolves
        either) or VALID via a genuine fallback (the news test's own case).

        (2) The actual UNKNOWN_ID status names an id that WAS recognized as
        an explicit reference attempt but does not resolve in this run's
        own registry -- exercised directly against the real, frozen
        validate_source_reference (the SAME function every candidate
        method, including this run's own marker path, is required to pass
        through), proving the market-data registry is validated by the
        exact same real mechanism as news, never a parallel check.
        """
        from comqutor_alpha.source_provenance import validate_source_reference

        _, captured = _capture_real_market_snapshot(monkeypatch)
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
                "agent": "market_agent",
                "agent_output_id": f"{RUN_ID}:market_agent:market_report",
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

    def test_a_snapshot_observed_after_the_evidence_cutoff_is_rejected_never_used_as_look_ahead(
        self, tmp_path, monkeypatch
    ):
        """Time-out-of-bounds: this run's own analysis_date (evidence
        cutoff) is set BEFORE the captured snapshot's own observation_date
        -- validate_source_reference must independently reject it as
        TIME_INVALID, the SAME check already proven for news, now proven
        source-type-agnostic for market data too."""
        snapshot_text, captured = _capture_real_market_snapshot(
            monkeypatch, curr_date=ANALYSIS_DATE
        )
        agent_outputs = [
            {
                "agent": "market_agent",
                "agent_output_id": f"{RUN_ID}:market_agent:market_report",
                "raw_output": f"{snapshot_text}\n\nNVDA momentum remains constructive.",
            }
        ]
        # The original run's own evidence cutoff (analysis_date) predates
        # the captured snapshot's own observation_date (2026-08-10) --
        # simulating a stale/reused registry entry, exactly mirroring
        # test_t1_source_linking_pipeline.py's own news time-boundary test.
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, captured_sources=captured, analysis_date="2026-08-01")
        save_structured_agent_outputs(_run_dir(tmp_path), llm_gateway=None)

        persisted = json.loads((_run_dir(tmp_path) / "structured_agent_outputs.json").read_text())
        linked_or_time_invalid = [
            r for r in persisted["records"] if r.get("source_link_status") in ("VALID", "TIME_INVALID")
        ]
        assert linked_or_time_invalid, "expected the marker to at least resolve an identity"
        assert all(r["source_link_status"] == "TIME_INVALID" for r in linked_or_time_invalid)
        assert all(r["content_support_status"] == "NOT_APPLICABLE" for r in linked_or_time_invalid)

    def test_underlying_market_data_changing_after_a_review_is_detected_never_silently_carried_forward(
        self, tmp_path, monkeypatch
    ):
        """'Value/unit consistency' as this framework can actually enforce
        it: a review is bound to the source's content_hash AT REVIEW TIME
        (see source_provenance.apply_content_support_review's own
        docstring) -- if the underlying market data is later revised
        (e.g. a corrected/adjusted close), the SAME claim_id's review no
        longer matches the CURRENT source content_hash and must be
        reported as stale, never silently treated as still-current
        support. This is the same real mechanism the news chain's own
        content-version-changed test already proves, exercised here for
        market data specifically."""
        from comqutor_alpha.source_provenance import (
            SOURCE_LINK_VALID,
            apply_content_support_review,
            resolve_fragment_by_id,
        )

        snapshot_text, captured = _capture_real_market_snapshot(monkeypatch)
        registry = build_source_registry(
            run_id=RUN_ID, ticker=TICKER, retrieved_at="2026-08-10T00:00:00Z", captured_records=captured
        )
        source = registry["sources"][0]
        record = {
            "claim_id": f"{RUN_ID}:market_agent:claim:1",
            "run_id": RUN_ID, "ticker": TICKER, "agent": "market_agent",
            "claim": "NVDA closed higher on strong verified trading data.",
            "evidence": "NVDA closed higher on strong verified trading data.",
            "entities": [], "factors": [], "direction": "positive", "confidence": 0.8,
            "source_link_status": SOURCE_LINK_VALID,
            "linked_source_id": source["fragment_id"],
        }
        reviewed = apply_content_support_review(
            record, status="SUPPORTS", reviewer="analyst_a",
            rationale="matches the verified snapshot's own reported close",
            reviewed_at="2026-08-10T12:00:00Z", sources=registry["sources"],
        )
        assert reviewed["content_support_review"]["content_hash"] == source["content_hash"]

        # The underlying data is revised (a different Close value) -- the
        # SAME symbol/date identity, but genuinely different content, so
        # build_source_record computes a DIFFERENT content_hash for it.
        revised_ohlcv = _sample_ohlcv()
        revised_ohlcv.loc[revised_ohlcv.index[-1], "Close"] = 999.99
        _, revised_captured = _capture_real_market_snapshot(monkeypatch, ohlcv=revised_ohlcv)
        revised_registry = build_source_registry(
            run_id=RUN_ID, ticker=TICKER, retrieved_at="2026-08-10T13:00:00Z", captured_records=revised_captured
        )
        revised_source = resolve_fragment_by_id(source["fragment_id"], revised_registry["sources"])
        assert revised_source is not None
        assert revised_source["content_hash"] != source["content_hash"]

        from comqutor_alpha.source_provenance import compute_verified_support_eligibility

        eligibility = compute_verified_support_eligibility(reviewed, revised_registry["sources"])
        assert eligibility["eligible"] is False
        assert eligibility["reason_code"] == "CONTENT_VERSION_CHANGED_SINCE_REVIEW"


class TestDerivedIndicatorScenario_CalculationIsReproducibleFromFrozenInput:
    """T1 task-sheet Part 3, second data chain (derived indicators), per
    direct user instruction: 'market -> derived indicators..., all reusing
    the existing framework.' Reuses the SAME market-data source record
    build_verified_market_snapshot already captures (no parallel derived-
    indicator system) -- this proves its calculation_method/calculation_
    version/calculation_params are actually SUFFICIENT to independently
    reproduce the exact indicator values from frozen input, never merely a
    reference to a model-generated number."""

    def test_calculation_metadata_is_saved_and_the_recorded_indicators_are_independently_reproducible(
        self, tmp_path, monkeypatch
    ):
        frozen_ohlcv = _sample_ohlcv()
        _, captured = _capture_real_market_snapshot(monkeypatch, ohlcv=frozen_ohlcv)
        source = captured[0]

        assert source["calculation_method"] == "stockstats"
        assert source["calculation_version"].startswith("stockstats==")
        params = source["calculation_params"]
        assert params["symbol"] == TICKER
        assert params["as_of_date"] == ANALYSIS_DATE
        assert params["window_end"] == ANALYSIS_DATE
        assert params["row_count"] == len(frozen_ohlcv)
        assert "rsi" in params["indicator_names"]

        # Independently reproduce: re-run the SAME real library (stockstats)
        # over a FROZEN OHLCV window matching calculation_params (never the
        # module's own internal state, never a live re-fetch) and confirm
        # the recorded indicator values are exactly what that recomputation
        # produces -- proving "input record reference + calculation method/
        # version/params" is actually enough to regenerate the number, not
        # merely a label on an already-trusted value.
        from stockstats import wrap

        reproduction_df = frozen_ohlcv[
            (frozen_ohlcv["Date"] >= pd.Timestamp(params["window_start"]))
            & (frozen_ohlcv["Date"] <= pd.Timestamp(params["window_end"]))
        ].copy()
        assert len(reproduction_df) == params["row_count"]
        stock_df = wrap(reproduction_df.copy())
        recorded_indicators = source["data_snapshot"]["indicators"]
        for name in params["indicator_names"]:
            stock_df[name]  # triggers stockstats calculation, same as the real tool does
            reproduced_value = f"{stock_df.iloc[-1][name]:.2f}"
            assert reproduced_value == recorded_indicators[name], (
                f"indicator {name}: recorded {recorded_indicators[name]!r} != "
                f"reproduced {reproduced_value!r} from the SAME frozen input"
            )
