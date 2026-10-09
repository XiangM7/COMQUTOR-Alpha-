"""Round 3 (2026-10-04): cross-agent reference passing, derived-calculation
verification, and no-marker normalized candidate matching -- the three
mechanisms John 下一轮开发任务单 section 3/4/5 asks for, built additively on
top of the EXISTING source/review/gate/persistence framework (never a
parallel system).

Exercises the REAL production functions:
    comqutor_alpha.structure_engine.structured_output_adapter.
        scope_sources_for_agent / visible_source_types_for_agent
        (per-step candidate-set scoping, section 3)
    comqutor_alpha.source_provenance.
        match_evidence_to_source_candidates_normalized
        (no-marker numeric candidate matching, section 5)
    comqutor_alpha.source_provenance.extract_all_source_markers_from_text
        (multi-reference preservation, section 3.7)
    comqutor_alpha.structure_engine.derived_fact_verification.
        verify_percent_comparison_claim (limited derived-calculation
        verification, section 4)
    comqutor_alpha.graph_engine.evidence_fact_index.group_evidence_candidates
        (same-source dedup without inflation / opposite-polarity
        preservation, section 6 -- confirms PRE-EXISTING, unmodified
        correctness; this round found no defect here worth fixing)
    save_structured_agent_outputs / run_research_request /
        get_agent_outputs_response / get_run_export_bundle (the real
        end-to-end entrypoints, one scenario below spans all of them)

Zero Provider calls, zero network, zero real LLM anywhere in this file
(the one full-pipeline scenario uses the deterministic echo gateway).
"""

from __future__ import annotations

import json

from comqutor_alpha.adapters.tradingagents_output_writer import save_comqutor_run_outputs
from comqutor_alpha.api.agent_output_reader import get_agent_outputs_response
from comqutor_alpha.api.routes_research import get_run_export_bundle, run_research_request
from comqutor_alpha.graph_engine.evidence_fact_index import (
    EvidenceFactCandidate,
    group_evidence_candidates,
)
from comqutor_alpha.source_provenance import (
    build_source_registry,
    extract_all_source_markers_from_text,
    match_evidence_to_source_candidates_normalized,
)
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from comqutor_alpha.storage.file_store import save_json_record
from comqutor_alpha.structure_engine.derived_fact_verification import verify_percent_comparison_claim
from comqutor_alpha.structure_engine.structured_output_adapter import (
    save_structured_agent_outputs,
    scope_sources_for_agent,
    visible_source_types_for_agent,
)
from scripts.deterministic_echo_llm import build_deterministic_echo_gateway

RUN_ID = "t1-cross-agent-reference-run"
TICKER = "NVDA"
ANALYSIS_DATE = "2026-08-10"

_MARKET_SOURCE = {
    "source_type": "market",
    "name": "Yahoo Finance",
    "title": "NVDA verified market snapshot 2026-08-09",
    "url": "",
    # Deliberately BEFORE ANALYSIS_DATE (2026-08-10) -- a market source
    # published AFTER the run's own evidence cutoff is correctly rejected
    # as SOURCE_LINK_TIME_INVALID by the existing, unmodified
    # validate_source_reference (real look-ahead-safety behavior, not a
    # bug this round's new matching passes should ever paper over by
    # falling through to a coincidental different-source match instead).
    "published_at": "2026-08-09T00:00:00",
    "provider": "yfinance",
    "excerpt": "NVDA 2026-08-09 OHLCV Close=228.38 Volume=121732200; close_200_sma=199.81",
    "instrument": "NVDA",
    "observation_date": "2026-08-09",
    "unit": "USD",
    "data_snapshot": {"ohlcv": {"Close": "228.38", "Volume": "121732200"}, "indicators": {"close_200_sma": "199.81"}},
}
_FINANCIAL_SOURCE = {
    "source_type": "financial",
    "name": "Yahoo Finance",
    "title": "NVDA fundamentals snapshot 2026-08-09",
    "url": "",
    "published_at": "2026-08-09T00:00:00",
    "provider": "yfinance",
    "excerpt": "NVDA fundamentals Market Cap=3000000000000.0",
    "instrument": "NVDA",
    "observation_date": "2026-08-09",
    "unit": None,
    "data_snapshot": {"market_cap": 3000000000000.0},
}


def _registry(*raw_records):
    return build_source_registry(
        run_id=RUN_ID, ticker=TICKER, retrieved_at="2026-08-10T00:00:00Z", captured_records=list(raw_records)
    )


def _write_run_fixture(tmp_path, *, agent_outputs, sources_registry, run_id=RUN_ID):
    save_json_record(
        run_id, "metadata.json", {"run_id": run_id, "ticker": TICKER, "analysis_date": ANALYSIS_DATE},
        output_root=str(tmp_path),
    )
    save_json_record(
        run_id, "raw_agent_outputs.json",
        {"schema_version": "raw.v1", "run_id": run_id, "ticker": TICKER, "agent_outputs": agent_outputs},
        output_root=str(tmp_path),
    )
    save_json_record(run_id, "source_registry.json", sources_registry, output_root=str(tmp_path))


class TestScenarioA_PerStepCandidateScoping:
    def test_market_agent_cannot_borrow_a_financial_source_it_was_never_shown(self, tmp_path):
        """market_agent's own tool loop never sees fundamentals data (direct
        read of market_analyst.py confirms it). A market_agent claim that
        happens to carry a forged/foreign fragment_id marker pointing at
        the REAL, existing financial source must still be rejected -- that
        source genuinely exists in this run's registry, but was never
        offered to market_agent's own step."""
        registry = _registry(_MARKET_SOURCE, _FINANCIAL_SOURCE)
        financial_fragment_id = next(
            s["fragment_id"] for s in registry["sources"] if s["source_type"] == "financial"
        )
        agent_outputs = [
            {
                "agent": "market_agent",
                "agent_output_id": f"{RUN_ID}:market_agent:market_report",
                "raw_output": f"NVDA market cap is strong [fragment_id: {financial_fragment_id}].",
            }
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, sources_registry=registry)
        save_structured_agent_outputs(tmp_path / RUN_ID, llm_gateway=None)

        persisted = json.loads((tmp_path / RUN_ID / "structured_agent_outputs.json").read_text())
        record = persisted["records"][0]
        assert record["source_link_status"] == "NOT_PROVIDED", (
            "market_agent must not be able to resolve a source it was never scoped to see, "
            "even though that source is real and exists elsewhere in the same run's registry"
        )
        assert record["linked_source_id"] is None

    def test_bull_researcher_can_use_the_same_financial_source_it_is_legitimately_shown(self, tmp_path):
        """bull_researcher DOES legitimately receive fundamentals_report in
        its own prompt (direct read of bull_researcher.py confirms this) --
        the SAME financial source that market_agent could not use above
        must resolve VALID for bull_researcher."""
        registry = _registry(_MARKET_SOURCE, _FINANCIAL_SOURCE)
        financial_fragment_id = next(
            s["fragment_id"] for s in registry["sources"] if s["source_type"] == "financial"
        )
        agent_outputs = [
            {
                "agent": "bull_researcher",
                "agent_output_id": f"{RUN_ID}:bull_researcher:investment_debate_state.bull_history",
                "raw_output": f"NVDA's market cap remains strong [fragment_id: {financial_fragment_id}].",
            }
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, sources_registry=registry)
        save_structured_agent_outputs(tmp_path / RUN_ID, llm_gateway=None)

        persisted = json.loads((tmp_path / RUN_ID / "structured_agent_outputs.json").read_text())
        record = persisted["records"][0]
        assert record["source_link_status"] == "VALID"
        assert record["source_link_method"] == "ORIGINAL_AGENT_MARKER_CITED"

    def test_visibility_map_matches_the_real_code_derived_scoping(self):
        assert visible_source_types_for_agent("market_agent") == frozenset({"market"})
        assert visible_source_types_for_agent("fundamental_agent") == frozenset({"financial"})
        assert visible_source_types_for_agent("sentiment_agent") == frozenset()
        for downstream in ("bull_researcher", "bear_researcher", "research_manager", "trader",
                           "aggressive_risk_analyst", "conservative_risk_analyst",
                           "neutral_risk_analyst", "portfolio_manager"):
            assert visible_source_types_for_agent(downstream) == frozenset({"market", "news", "macro", "financial"})
        # An unrecognized agent is never silently starved -- scoping is a
        # closed, explicit allowlist, never a default-deny for an agent
        # this round never analyzed.
        assert visible_source_types_for_agent("some_future_agent") is None
        sources = [_MARKET_SOURCE, _FINANCIAL_SOURCE]
        assert scope_sources_for_agent("some_future_agent", sources) == sources


class TestScenarioB_NormalizedNumericCandidateMatching:
    def _sources(self):
        return _registry(_MARKET_SOURCE)["sources"]

    def test_scale_suffix_and_display_precision_rounding_is_located(self):
        sources = self._sources()
        result = match_evidence_to_source_candidates_normalized(
            "the stock traded 121.7M shares", "the stock traded 121.7M shares", sources, instrument="NVDA"
        )
        assert result["candidates"] == [sources[0]["fragment_id"]]
        assert result["matched_fields"][sources[0]["fragment_id"]] == ["ohlcv.Volume"]

    def test_a_number_absent_from_every_saved_source_is_never_invented(self):
        sources = self._sources()
        result = match_evidence_to_source_candidates_normalized(
            "versus 298.9M on a prior day", "versus 298.9M on a prior day", sources, instrument="NVDA"
        )
        assert result["candidates"] == []
        assert result["ambiguous_numbers"] == []

    def test_a_bare_low_specificity_number_is_never_used_as_a_signal(self):
        sources = self._sources()
        result = match_evidence_to_source_candidates_normalized(
            "roughly 200 shares were mentioned", "roughly 200 shares were mentioned", sources, instrument="NVDA"
        )
        assert result["candidates"] == []

    def test_ambiguity_across_two_distinct_sources_is_preserved_never_guessed(self):
        other_source = dict(_MARKET_SOURCE)
        other_source["title"] = "NVDA verified market snapshot 2026-09-29"
        other_source["observation_date"] = "2026-09-29"
        other_source["data_snapshot"] = {"ohlcv": {"Close": "228.38"}}
        registry = _registry(_MARKET_SOURCE, other_source)
        result = match_evidence_to_source_candidates_normalized(
            "the stock closed at 228.38", "the stock closed at 228.38", registry["sources"], instrument="NVDA"
        )
        assert result["candidates"] == []
        assert len(result["ambiguous_numbers"]) == 1
        assert len(result["ambiguous_numbers"][0]["source_ids"]) == 2

    def test_an_instrument_mismatch_rejects_a_source_that_would_otherwise_match(self):
        sources = self._sources()
        result = match_evidence_to_source_candidates_normalized(
            "AMD traded 121.7M shares", "AMD traded 121.7M shares", sources, instrument="AMD"
        )
        assert result["candidates"] == []

    def test_a_different_calendar_day_mention_does_not_block_the_matching_day(self):
        sources = self._sources()
        claim = "the 08-09 session traded 121.7M shares, versus an unrecorded 07-15 figure"
        result = match_evidence_to_source_candidates_normalized(claim, claim, sources, instrument="NVDA")
        assert result["candidates"] == [sources[0]["fragment_id"]]


class TestScenarioC_MultiReferencePreservation:
    def test_a_claim_combining_two_distinct_markers_keeps_both_not_only_the_first(self, tmp_path):
        registry = _registry(_MARKET_SOURCE, _FINANCIAL_SOURCE)
        market_fragment_id = next(s["fragment_id"] for s in registry["sources"] if s["source_type"] == "market")
        financial_fragment_id = next(s["fragment_id"] for s in registry["sources"] if s["source_type"] == "financial")
        agent_outputs = [
            {
                "agent": "bull_researcher",
                "agent_output_id": f"{RUN_ID}:bull_researcher:investment_debate_state.bull_history",
                "raw_output": (
                    f"NVDA closed at 228.38 [fragment_id: {market_fragment_id}] with a market cap of "
                    f"$3T [fragment_id: {financial_fragment_id}], a genuinely strong combination."
                ),
            }
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, sources_registry=registry)
        save_structured_agent_outputs(tmp_path / RUN_ID, llm_gateway=None)

        persisted = json.loads((tmp_path / RUN_ID / "structured_agent_outputs.json").read_text())
        record = persisted["records"][0]
        assert record["source_link_status"] == "VALID"
        market_source_id = next(s["source_id"] for s in registry["sources"] if s["source_type"] == "market")
        financial_source_id = next(s["source_id"] for s in registry["sources"] if s["source_type"] == "financial")
        assert record["linked_source_id"] == market_source_id  # primary stays unchanged, backward compatible
        assert set(record["linked_source_ids"]) == {market_source_id, financial_source_id}

    def test_extract_all_source_markers_returns_every_distinct_marker_in_order(self):
        registry = _registry(_MARKET_SOURCE, _FINANCIAL_SOURCE)
        market_fragment_id = next(s["fragment_id"] for s in registry["sources"] if s["source_type"] == "market")
        financial_fragment_id = next(s["fragment_id"] for s in registry["sources"] if s["source_type"] == "financial")
        text = f"A [fragment_id: {market_fragment_id}] and B [fragment_id: {financial_fragment_id}] and A again [fragment_id: {market_fragment_id}]"
        found = extract_all_source_markers_from_text(text, registry["sources"])
        assert found == [market_fragment_id, financial_fragment_id]

    def test_a_single_marker_claim_never_gains_a_fabricated_second_reference(self, tmp_path):
        registry = _registry(_MARKET_SOURCE)
        market_fragment_id = registry["sources"][0]["fragment_id"]
        agent_outputs = [
            {
                "agent": "market_agent",
                "agent_output_id": f"{RUN_ID}:market_agent:market_report",
                "raw_output": f"NVDA closed at 228.38 [fragment_id: {market_fragment_id}].",
            }
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, sources_registry=registry)
        save_structured_agent_outputs(tmp_path / RUN_ID, llm_gateway=None)
        persisted = json.loads((tmp_path / RUN_ID / "structured_agent_outputs.json").read_text())
        record = persisted["records"][0]
        assert "linked_source_ids" not in record


class TestScenarioD_DerivedPercentComparisonVerification:
    def _sources(self):
        return _registry(_MARKET_SOURCE)["sources"]

    def test_verified_matches_the_real_case_b_claim(self):
        sources = self._sources()
        claim = "The close of 228.38 is approximately 14% above the 200 SMA, confirming a well-established primary uptrend."
        result = verify_percent_comparison_claim(claim, sources)
        assert result["status"] == "VERIFIED"
        assert round(result["recomputed_percent"], 2) == 14.30
        assert result["inputs"]["value_field"] == "ohlcv.Close"
        assert result["inputs"]["base_field"] == "indicators.close_200_sma"

    def test_refuted_when_the_stated_percent_does_not_match_the_saved_inputs(self):
        sources = self._sources()
        claim = "The close of 228.38 is approximately 40% above the 200 SMA."
        result = verify_percent_comparison_claim(claim, sources)
        assert result["status"] == "REFUTED"

    def test_unresolvable_reference_is_honest_not_a_silent_pass(self):
        sources = self._sources()
        claim = "The close of 228.38 is approximately 2% above the VWMA."
        result = verify_percent_comparison_claim(claim, sources)
        assert result["status"] == "REFERENCE_NOT_RESOLVABLE"
        assert result["inputs"] is None

    def test_zero_denominator_is_never_silently_computed(self):
        source = dict(_MARKET_SOURCE)
        source["data_snapshot"] = {"ohlcv": {"Close": "228.38"}, "indicators": {"close_200_sma": "0"}}
        sources = _registry(source)["sources"]
        claim = "The close of 228.38 is approximately 14% above the 200 SMA."
        result = verify_percent_comparison_claim(claim, sources)
        assert result["status"] == "NON_COMPUTABLE_ZERO_DENOMINATOR"

    def test_negative_base_never_produces_a_misleading_growth_number(self):
        source = dict(_MARKET_SOURCE)
        source["data_snapshot"] = {"ohlcv": {"Close": "228.38"}, "indicators": {"close_200_sma": "-10.0"}}
        sources = _registry(source)["sources"]
        claim = "The close of 228.38 is approximately 14% above the 200 SMA."
        result = verify_percent_comparison_claim(claim, sources)
        assert result["status"] == "NON_COMPUTABLE_NEGATIVE_BASE"

    def test_non_matching_claim_shape_returns_none_not_a_false_verdict(self):
        sources = self._sources()
        assert verify_percent_comparison_claim("NVDA is a strong buy.", sources) is None


class TestScenarioE_EvidenceFactDedupNeverInflatesOrLosesOppositePolarity:
    """Verifies PRE-EXISTING, unmodified comqutor_alpha.graph_engine.
    evidence_fact_index.group_evidence_candidates behavior still holds --
    this round found no defect here, only confirmed it directly against
    the exact kind of claims this round's own new mechanisms produce."""

    def test_two_different_agents_citing_the_same_validated_source_for_the_same_fact_do_not_inflate_count(self):
        candidates = [
            EvidenceFactCandidate(
                claim_id="market_agent:claim:1", claim_text="NVDA closed at 228.38, up sharply today.",
                factors=("Price Momentum",), semantic_polarity="positive", linked_source_id="src_shared",
            ),
            EvidenceFactCandidate(
                claim_id="bull_researcher:claim:1", claim_text="NVDA closed at 228.38, up sharply today.",
                factors=("Price Momentum",), semantic_polarity="positive", linked_source_id="src_shared",
            ),
        ]
        groups = group_evidence_candidates(candidates, ticker="NVDA")
        assert len(groups) == 1
        assert {c.claim_id for c in groups[0]} == {"market_agent:claim:1", "bull_researcher:claim:1"}

    def test_opposite_polarity_claims_sharing_the_same_source_are_never_merged(self):
        candidates = [
            EvidenceFactCandidate(
                claim_id="bull_researcher:claim:1", claim_text="NVDA closed at 228.38, up sharply today.",
                factors=("Price Momentum",), semantic_polarity="positive", linked_source_id="src_shared",
            ),
            EvidenceFactCandidate(
                claim_id="bear_researcher:claim:1", claim_text="NVDA closed at 228.38, up sharply today.",
                factors=("Price Momentum",), semantic_polarity="negative", linked_source_id="src_shared",
            ),
        ]
        groups = group_evidence_candidates(candidates, ticker="NVDA")
        assert len(groups) == 2

    def test_same_source_different_unrelated_facts_are_never_merged(self):
        candidates = [
            EvidenceFactCandidate(
                claim_id="market_agent:claim:1", claim_text="NVDA closed at 228.38 today.",
                factors=("Price Momentum",), semantic_polarity="positive", linked_source_id="src_shared",
            ),
            EvidenceFactCandidate(
                claim_id="market_agent:claim:2", claim_text="NVDA's RSI suggests overbought conditions.",
                factors=("Momentum Indicator",), semantic_polarity="negative", linked_source_id="src_shared",
            ),
        ]
        groups = group_evidence_candidates(candidates, ticker="NVDA")
        assert len(groups) == 2


class TestScenarioF_RealPipelineCrossAgentMarkerForwarding:
    def test_bull_researcher_claim_forwarding_a_market_marker_is_valid_through_real_api_and_export(self, tmp_path):
        """One full real-pipeline scenario (section 8's "at least one test
        spans real product entrypoint to API/Export"): a market_agent
        snapshot carries a real marker; a bull_researcher claim restates
        the SAME figure, forwarding that marker (exactly what
        get_citation_forwarding_instruction now asks real bull_researcher
        prompts to do) -- resolved through the REAL run_research_request
        pipeline, REAL get_agent_outputs_response, and REAL
        get_run_export_bundle. Fixed data only; zero Provider calls; the
        LLM gateway is the deterministic echo gateway."""
        engine = build_engine("sqlite:///:memory:")
        apply_migrations(engine)
        repo = GraphPersistenceRepository(engine)

        captured_market_source = dict(_MARKET_SOURCE)
        registry_preview = _registry(captured_market_source)
        market_fragment_id = registry_preview["sources"][0]["fragment_id"]
        market_marker_text = f"[source_id: {registry_preview['sources'][0]['source_id']}] [fragment_id: {market_fragment_id}]"

        def runner(payload, *, output_root):
            final_state = {
                "market_report": f"NVDA closed at 228.38 on 2026-08-09 {market_marker_text}.",
                "investment_debate_state": {
                    "bull_history": (
                        f"Bull Analyst: NVDA's momentum is strengthening -- the stock has risen to close "
                        f"at 228.38 {market_marker_text}, confirming the uptrend accelerated."
                    )
                },
            }
            return save_comqutor_run_outputs(
                final_state, payload["ticker"], selected_analysts=["market"],
                analysis_date=payload.get("analysis_date"), output_root=output_root,
                captured_sources=[captured_market_source],
            )

        gateway = build_deterministic_echo_gateway("cross-agent-marker-forwarding-test", tmp_path)
        payload = {"ticker": TICKER, "analysis_date": ANALYSIS_DATE, "selected_analysts": ["market"]}
        response = run_research_request(
            payload, runner=runner, output_root=tmp_path, graph_repository=repo, week2_llm_gateway=gateway
        )
        assert response["status"] == "completed"
        run_id = response["run_id"]

        api_response = get_agent_outputs_response(run_id, output_root=tmp_path, graph_repository=repo)
        bull_record = next(
            r for r in api_response["structured_agent_outputs"]
            if r["agent"] == "bull_researcher" and r.get("source_link_status") == "VALID"
        )
        assert bull_record["source_link_method"] == "ORIGINAL_AGENT_MARKER_CITED"

        status_code, _, raw_bytes, _, error_body = get_run_export_bundle(run_id, output_root=tmp_path)
        assert status_code == 200, error_body
        import io
        import zipfile
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            exported = json.loads(zf.read("structured_agent_outputs.json"))
        exported_record = next(r for r in exported["records"] if r["claim_id"] == bull_record["claim_id"])
        assert exported_record["source_link_status"] == "VALID"
        assert exported_record["linked_source_id"] == bull_record["linked_source_id"]


class TestScenarioG_DerivedCalcVerifierIsWiredIntoRealExtractionNotOnlyTested:
    """John 下一轮开发任务单's own explicit warning: "必须把功能接入实际抽取/
    来源注释/持久化路径,不能只提供一个测试会调用、生产不调用的函数." This
    proves verify_percent_comparison_claim is actually invoked by the REAL
    save_structured_agent_outputs path (via _build_records_from_segments),
    not only unit-tested in isolation -- the `derived_fact_check` field
    must appear on the record this round-trips through real persistence."""

    def test_derived_fact_check_is_stamped_on_the_real_persisted_record(self, tmp_path):
        sources_registry = _registry(_MARKET_SOURCE)
        agent_outputs = [
            {
                "agent": "market_agent",
                "agent_output_id": f"{RUN_ID}:market_agent:market_report",
                "raw_output": (
                    "The close of 228.38 is approximately 14% above the 200 SMA, "
                    "confirming a well-established primary uptrend."
                ),
            }
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, sources_registry=sources_registry)
        save_structured_agent_outputs(tmp_path / RUN_ID, llm_gateway=None)

        persisted = json.loads((tmp_path / RUN_ID / "structured_agent_outputs.json").read_text())
        record = persisted["records"][0]
        assert "derived_fact_check" in record, (
            "verify_percent_comparison_claim must be reachable from the real "
            "save_structured_agent_outputs path -- this must not be a function only tests call"
        )
        check = record["derived_fact_check"]
        assert check["status"] == "VERIFIED"
        assert round(check["recomputed_percent"], 2) == 14.30
        # Purely additive: never touches the independently-computed
        # source-link/eligibility fields this same record already carries.
        assert record["source_link_status"] == "VALID"
        assert "content_support_status" in record

    def test_a_claim_with_no_percent_comparison_shape_gets_no_fabricated_field(self, tmp_path):
        sources_registry = _registry(_MARKET_SOURCE)
        agent_outputs = [
            {
                "agent": "market_agent",
                "agent_output_id": f"{RUN_ID}:market_agent:market_report",
                "raw_output": "NVDA closed at 228.38 today, a strong session overall.",
            }
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, sources_registry=sources_registry)
        save_structured_agent_outputs(tmp_path / RUN_ID, llm_gateway=None)

        persisted = json.loads((tmp_path / RUN_ID / "structured_agent_outputs.json").read_text())
        record = persisted["records"][0]
        assert "derived_fact_check" not in record
