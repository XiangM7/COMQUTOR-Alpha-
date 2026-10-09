"""T1 source-linking / evidence-support chain -- FINANCIAL DATA (third real
chain, 2026-09-29 task-sheet Part 3, sequenced per direct user instruction:
market -> derived indicators -> financial -> macro, all reusing the
EXISTING source/review/gate/persistence framework -- no parallel system per
data type).

Scope boundary (deliberate, not an oversight): only get_fundamentals is
wired this round. get_balance_sheet/get_cashflow/get_income_statement
expose only a fiscal PERIOD END date as their column identity -- never a
real disclosure/filing date -- so treating a period end as the evidence-
cutoff-relevant "published_at" would create a real, unmitigated look-ahead
risk (the exact report-period-vs-disclosure-time conflation this round's
task explicitly warns against). get_fundamentals's own `.info` fields
(market cap, trailing PE) are CURRENT/live-computed, so using retrieval
time as published_at is honest, not assumed -- see
tradingagents.dataflows.y_finance._fundamentals_summary_sentence's own
docstring. This file does NOT attempt to cover the three statement
endpoints; that gap is recorded, not silently omitted.

Exercises the REAL production functions across every stage of the
financial-data chain:

    fetch (tradingagents.dataflows.y_finance.get_fundamentals, the real
    production tool fundamentals_analyst calls) -> source_capture ->
    source_registry.json (comqutor_alpha.source_provenance.
    build_source_registry, the SAME SourceRecord shape) -> structured
    extraction (structured_output_adapter.save_structured_agent_outputs,
    llm_gateway=None -- fully deterministic, zero Provider calls) -> gate
    (verified_evidence_gate, unmodified) -> review
    (submit_content_support_review, unmodified) -> API
    (agent_output_reader.get_agent_outputs_response).

yfinance's own `Ticker.info` is monkeypatched (the SAME external-boundary-
only mocking technique the market-data chain test already established) --
never a claim that a model's semantic accuracy has been validated.
`datetime.now()` inside tradingagents.dataflows.y_finance is also
monkeypatched to a FIXED value: get_fundamentals's own retrieval timestamp
is always real wall-clock "now" (its `curr_date` parameter is explicitly
unused for yfinance, per its own type annotation), so freezing it here is
the only way to get a deterministic evidence_cutoff comparison against a
fixed ANALYSIS_DATE fixture -- exactly analogous to how the market chain's
frozen curr_date already pins its observation_date. Zero Provider calls,
zero network, zero TradingAgents graph invocation anywhere in this file.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime

import tradingagents.dataflows.y_finance as y_finance
from comqutor_alpha.api.agent_output_reader import get_agent_outputs_response
from comqutor_alpha.api.routes_research import (
    get_run_export_bundle,
    run_research_request,
    submit_content_support_review,
)
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

RUN_ID = "t1-financial-data-e2e-run"
TICKER = "NVDA"
ANALYSIS_DATE = "2026-08-10"
# Deliberately a calendar day BEFORE ANALYSIS_DATE, not merely midnight of
# the same day: validate_source_reference's evidence_cutoff comparison
# parses a bare "YYYY-MM-DD" cutoff as that date's OWN midnight (see
# source_provenance._parse_iso_like), so a same-day retrieval with any
# real (non-midnight) time-of-day would always compare as "later than the
# cutoff" and be rejected as TIME_INVALID -- a real, pre-existing
# characteristic of the shared, frozen validate_source_reference (used
# identically by every source type, never modified by this round) that a
# live intraday fetch on the SAME day as the analysis date would also hit
# in production. Recorded here rather than dodged: this fixture picks an
# honestly-earlier retrieval day so this test exercises genuine "evidence
# retrieved before the cutoff", not a workaround for that behavior.
RETRIEVED_AT = datetime(2026, 8, 9, 12, 0, 0)


class _FixedDatetime(datetime):
    """Freezes tradingagents.dataflows.y_finance's own datetime.now() to a
    fixed instant -- see this module's own docstring for why that is
    necessary for a deterministic evidence_cutoff comparison here."""

    @classmethod
    def now(cls, tz=None):
        return RETRIEVED_AT


class _FakeTicker:
    def __init__(self, info):
        self.info = info


def _fake_info(*, market_cap=3_000_000_000_000, trailing_pe=35.2):
    return {"marketCap": market_cap, "trailingPE": trailing_pe}


def _capture_real_fundamentals(monkeypatch, *, ticker=TICKER, info=None):
    """Runs the REAL get_fundamentals against a monkeypatched yf.Ticker
    (never a real network request) with a frozen retrieval clock, inside a
    real source_capture_scope. Returns (report_text, captured_records)."""
    fake_info = info if info is not None else _fake_info()
    monkeypatch.setattr(y_finance, "datetime", _FixedDatetime)
    monkeypatch.setattr(y_finance.yf, "Ticker", lambda symbol: _FakeTicker(fake_info))
    with source_capture_scope() as sink:
        report_text = y_finance.get_fundamentals(ticker)
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
            run_id=run_id, ticker=TICKER, retrieved_at=RETRIEVED_AT.isoformat(), captured_records=captured_sources
        )
        save_json_record(run_id, "source_registry.json", registry, output_root=str(tmp_path))
    return registry


def _run_dir(tmp_path, run_id=RUN_ID):
    return tmp_path / run_id


class TestFinancialDataScenarioA_ValidLinkPropagatesEndToEnd:
    def test_real_fundamentals_snapshot_produces_a_valid_link_through_the_real_pipeline(self, tmp_path, monkeypatch):
        report_text, captured = _capture_real_fundamentals(monkeypatch)
        assert len(captured) == 1
        assert captured[0]["source_type"] == "financial"
        assert captured[0]["instrument"] == TICKER

        agent_outputs = [
            {
                "agent": "fundamental_agent",
                "agent_output_id": f"{RUN_ID}:fundamental_agent:fundamentals_report",
                "raw_output": report_text,
            }
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, captured_sources=captured)

        save_structured_agent_outputs(_run_dir(tmp_path), llm_gateway=None)

        persisted = json.loads((_run_dir(tmp_path) / "structured_agent_outputs.json").read_text())
        linked_records = [r for r in persisted["records"] if r.get("source_link_status") == "VALID"]
        assert linked_records, "expected the real fundamentals snapshot to produce a VALID-linked claim"
        record = linked_records[0]
        assert record["linked_source_id"] is not None
        assert record["content_support_status"] == "PENDING_REVIEW"

        registry = json.loads((_run_dir(tmp_path) / "source_registry.json").read_text())
        source = registry["sources"][0]
        assert source["source_type"] == "financial"
        assert source["provider"] == "yfinance"
        assert source["instrument"] == TICKER
        assert source["unit"] is None
        assert source["data_snapshot"]["market_cap"]
        assert source["data_snapshot"]["trailing_pe"]
        # 2026-10-04 (T1 financial-data fix round): every present field is
        # now captured, each with its own real unit classification -- not
        # just the original two.
        assert source["data_snapshot"]["field_units"]["market_cap"] == "UNKNOWN_CURRENCY"  # fixture sets no currency
        assert source["data_snapshot"]["field_units"]["trailing_pe"] == "ratio"

        # 2026-10-04: this round removed the previous "...suggesting
        # valuation remains elevated" auto-judgment (never justified by a
        # bare non-zero P/E with no comparison baseline -- see John
        # task-sheet section 3 point 8). The resulting neutral sentence
        # ("market capitalization stood at X; trailing P/E was Y") carries
        # no state-or-change/risk/relation/directional signal, so
        # claim_quality.py's own PRE-EXISTING, unmodified classifier (not
        # touched by this round) now correctly scores it CONTEXT_ONLY rather
        # than ANALYTICAL -- exactly like this run's OWN real
        # "NVDA's close sits above its moving averages"-style snapshot
        # claims already do (confirmed against the real NVDA production run,
        # e.g. market_report:claim:3). CONTEXT_ONLY claims are correctly,
        # pre-existingly excluded from the product_findings-scoped
        # /agent-outputs endpoint (claim_quality.is_claim_eligible's own
        # documented matrix) -- this is not a source-linking defect; the
        # link itself is still fully intact in the persisted record checked
        # above. Verified directly instead of via the product_findings view:
        assert record["claim_quality"] == "context_only"
        assert record["source_link_status"] == "VALID"
        assert record["linked_source_id"] is not None


class TestFinancialDataScenarioB_GateAndReviewIntegration:
    def test_unreviewed_financial_claim_never_counts_as_official_but_review_makes_it_count(self, tmp_path, monkeypatch):
        """Full production-entrypoint integration: unreviewed real financial
        evidence is excluded from the OFFICIAL (verified) Activation pool
        exactly like an unreviewed news/market claim -- proving the gate is
        genuinely source-type-agnostic -- and a real HUMAN_REVIEWED SUPPORTS
        review makes it count, through the SAME real run_research_request/
        submit_content_support_review entrypoints used throughout this
        whole round."""
        engine = build_engine("sqlite:///:memory:")
        apply_migrations(engine)
        repo = GraphPersistenceRepository(engine)

        report_text, captured = _capture_real_fundamentals(monkeypatch)
        marker_match = re.search(r"\[source_id: [^\]]+\] \[fragment_id: [^\]]+\]", report_text)
        assert marker_match, "expected the real fundamentals report to carry a source/fragment marker"
        marker_text = marker_match.group(0)

        # The verified snapshot's own marker-bearing sentence is pure
        # valuation data -- it has no alpha-relevant keyword content on its
        # own. A real fundamentals_analyst LLM would combine the verified
        # figures with its own analytical narrative in the SAME sentence
        # (exactly what its system prompt instructs); this reconstructs
        # that combined sentence directly, mirroring the market chain's own
        # equivalent gate-integration test.
        def runner(payload, *, output_root):
            from comqutor_alpha.adapters.tradingagents_output_writer import (
                save_comqutor_run_outputs,
            )

            final_state = {
                "fundamentals_report": (
                    "NVDA's revenue growth outlook remains constructive, supported by the verified "
                    f"fundamentals snapshot showing a sustained valuation premium {marker_text}."
                ),
            }
            return save_comqutor_run_outputs(
                final_state, payload["ticker"], selected_analysts=["fundamentals"],
                analysis_date=payload.get("analysis_date"), output_root=output_root,
                captured_sources=captured,
            )

        gateway = build_deterministic_echo_gateway("financial-data-gate-integration-test", tmp_path)
        payload = {"ticker": TICKER, "analysis_date": ANALYSIS_DATE, "selected_analysts": ["fundamentals"]}
        response = run_research_request(
            payload, runner=runner, output_root=tmp_path, graph_repository=repo, week2_llm_gateway=gateway
        )
        assert response["status"] == "completed"
        run_id = response["run_id"]

        agent_outputs = get_agent_outputs_response(run_id, output_root=tmp_path, graph_repository=repo)
        linked = [r for r in agent_outputs["structured_agent_outputs"] if r.get("source_link_status") == "VALID"]
        assert linked, "expected the real verified fundamentals snapshot to produce a VALID-linked claim"
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
        assert official_before["evidence_count"] == 0  # unreviewed financial evidence never counts officially

        review_result = submit_content_support_review(
            run_id, record["claim_id"], status="SUPPORTS", reviewer="analyst_a",
            rationale="the verified fundamentals snapshot directly reports this same valuation data",
            output_root=tmp_path, graph_repository=repo,
        )
        assert review_result["status"] == "ok"
        assert review_result["reevaluation"]["status"] == "ok"
        execution_id = review_result["reevaluation"]["execution_id"]

        execution_graph = json.loads((tmp_path / execution_id / "structure_graph.json").read_text(encoding="utf-8"))
        official_after = next(a for a in execution_graph["activation"]["alphas"] if a["alpha_id"] == alpha_id)
        assert official_after["evidence_count"] == 1  # now counts, once genuinely reviewed


class TestFinancialDataScenarioC_InvalidReferencesAreRejectedOrDowngraded:
    def test_a_forged_marker_that_does_not_resolve_in_this_runs_registry_is_never_trusted(self, tmp_path, monkeypatch):
        """Mirrors the market chain's own forged-marker test: a fragment_id
        with the correct shape that was never actually captured by THIS
        run must never be trusted, whether the final claim-level status
        names it NOT_PROVIDED (nothing else resolves either) or the
        underlying UNKNOWN_ID is what validate_source_reference itself
        reports when asked directly."""
        from comqutor_alpha.source_provenance import validate_source_reference

        _, captured = _capture_real_fundamentals(monkeypatch)
        registry = build_source_registry(
            run_id=RUN_ID, ticker=TICKER, retrieved_at=RETRIEVED_AT.isoformat(), captured_records=captured
        )
        forged_result = validate_source_reference(
            "src_deadbeefdeadbeef:frag:0", sources=registry["sources"], evidence_cutoff=ANALYSIS_DATE
        )
        assert forged_result["source_link_status"] == "UNKNOWN_ID"
        assert forged_result["linked_source_id"] is None

        agent_outputs = [
            {
                "agent": "fundamental_agent",
                "agent_output_id": f"{RUN_ID}:fundamental_agent:fundamentals_report",
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

    def test_a_fundamentals_snapshot_retrieved_after_the_evidence_cutoff_is_rejected_never_used_as_look_ahead(
        self, tmp_path, monkeypatch
    ):
        """Time-out-of-bounds: this run's own analysis_date (evidence
        cutoff) is set BEFORE the frozen retrieval instant baked into
        RETRIEVED_AT -- validate_source_reference must independently
        reject it as TIME_INVALID, the same check already proven for news
        and market data, now proven source-type-agnostic for financial
        data too."""
        report_text, captured = _capture_real_fundamentals(monkeypatch)
        agent_outputs = [
            {
                "agent": "fundamental_agent",
                "agent_output_id": f"{RUN_ID}:fundamental_agent:fundamentals_report",
                "raw_output": report_text,
            }
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, captured_sources=captured, analysis_date="2026-08-01")
        save_structured_agent_outputs(_run_dir(tmp_path), llm_gateway=None)

        persisted = json.loads((_run_dir(tmp_path) / "structured_agent_outputs.json").read_text())
        linked_or_time_invalid = [
            r for r in persisted["records"] if r.get("source_link_status") in ("VALID", "TIME_INVALID")
        ]
        assert linked_or_time_invalid, "expected the marker to at least resolve an identity"
        assert all(r["source_link_status"] == "TIME_INVALID" for r in linked_or_time_invalid)
        assert all(r["content_support_status"] == "NOT_APPLICABLE" for r in linked_or_time_invalid)

    def test_underlying_fundamentals_changing_after_a_review_is_detected_never_silently_carried_forward(
        self, tmp_path, monkeypatch
    ):
        """Value consistency as this framework can actually enforce it: a
        review is bound to the source's content_hash AT REVIEW TIME -- if
        the underlying fundamentals are later revised (e.g. a corrected
        trailing PE), the SAME claim_id's review no longer matches the
        CURRENT source content_hash and must be reported as stale, never
        silently treated as still-current support. Mirrors the market
        chain's own content-version-changed test."""
        from comqutor_alpha.source_provenance import (
            SOURCE_LINK_VALID,
            apply_content_support_review,
            compute_verified_support_eligibility,
            resolve_fragment_by_id,
        )

        _, captured = _capture_real_fundamentals(monkeypatch)
        registry = build_source_registry(
            run_id=RUN_ID, ticker=TICKER, retrieved_at=RETRIEVED_AT.isoformat(), captured_records=captured
        )
        source = registry["sources"][0]
        record = {
            "claim_id": f"{RUN_ID}:fundamental_agent:claim:1",
            "run_id": RUN_ID, "ticker": TICKER, "agent": "fundamental_agent",
            "claim": "NVDA's valuation remains elevated per verified fundamentals data.",
            "evidence": "NVDA's valuation remains elevated per verified fundamentals data.",
            "entities": [], "factors": [], "direction": "positive", "confidence": 0.8,
            "source_link_status": SOURCE_LINK_VALID,
            "linked_source_id": source["fragment_id"],
        }
        reviewed = apply_content_support_review(
            record, status="SUPPORTS", reviewer="analyst_a",
            rationale="matches the verified fundamentals snapshot's own reported valuation",
            reviewed_at=RETRIEVED_AT.isoformat(), sources=registry["sources"],
        )
        assert reviewed["content_support_review"]["content_hash"] == source["content_hash"]

        # The underlying fundamentals are revised (a different trailing PE)
        # -- the SAME instrument/retrieval identity, but genuinely
        # different content, so build_source_record computes a DIFFERENT
        # content_hash for it.
        _, revised_captured = _capture_real_fundamentals(monkeypatch, info=_fake_info(trailing_pe=999.9))
        revised_registry = build_source_registry(
            run_id=RUN_ID, ticker=TICKER, retrieved_at=RETRIEVED_AT.isoformat(), captured_records=revised_captured
        )
        revised_source = resolve_fragment_by_id(source["fragment_id"], revised_registry["sources"])
        assert revised_source is not None
        assert revised_source["content_hash"] != source["content_hash"]

        eligibility = compute_verified_support_eligibility(reviewed, revised_registry["sources"])
        assert eligibility["eligible"] is False
        assert eligibility["reason_code"] == "CONTENT_VERSION_CHANGED_SINCE_REVIEW"


def _read_zip_json(raw_bytes, name):
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
        return json.loads(zf.read(name))


class TestFinancialDataScenarioE_ProductReferenceChainThroughRealApiAndExport:
    """Round 2 (2026-10-04), verification 2: proves the ENGINEERING
    reference chain -- capture -> persist -> real API -> real Export --
    works for a genuine ANALYTICAL claim (not the context_only snapshot
    ScenarioA already covers), using the SAME real production entrypoints
    ScenarioB already established (run_research_request, the real
    _run_week3_graph_pipeline it drives internally, and the real
    get_run_export_bundle the frontend's download button actually calls --
    see routes_research.py's `GET /api/research/{run_id}/export` route).

    Only yf.Ticker is mocked (the external Provider boundary) and the LLM
    gateway is the deterministic echo gateway (zero real model calls,
    zero network) -- extraction, persistence, the gate, the API read path,
    and the export bundler are all the REAL, unmodified production code.

    This proves the CODE PATH resolves and carries a reference end to end
    with controlled input. It does NOT measure how reliably a real LLM
    produces a marker-preserving, analytically-worded claim -- that
    compliance rate is a separate, unmeasured question (see
    extract_source_marker_from_text's own docstring)."""

    def test_an_analytical_claim_citing_a_captured_fact_is_locatable_via_real_api_and_real_export(
        self, tmp_path, monkeypatch
    ):
        engine = build_engine("sqlite:///:memory:")
        apply_migrations(engine)
        repo = GraphPersistenceRepository(engine)

        report_text, captured = _capture_real_fundamentals(monkeypatch)
        marker_match = re.search(r"\[source_id: [^\]]+\] \[fragment_id: [^\]]+\]", report_text)
        assert marker_match, "expected the real fundamentals report to carry a source/fragment marker"
        marker_text = marker_match.group(0)

        def runner(payload, *, output_root):
            from comqutor_alpha.adapters.tradingagents_output_writer import (
                save_comqutor_run_outputs,
            )

            final_state = {
                "fundamentals_report": (
                    "NVDA's valuation outlook is strengthening, with the verified fundamentals "
                    f"snapshot showing the trailing P/E multiple has risen alongside market cap {marker_text}."
                ),
            }
            return save_comqutor_run_outputs(
                final_state, payload["ticker"], selected_analysts=["fundamentals"],
                analysis_date=payload.get("analysis_date"), output_root=output_root,
                captured_sources=captured,
            )

        gateway = build_deterministic_echo_gateway("financial-data-api-export-reference-test", tmp_path)
        payload = {"ticker": TICKER, "analysis_date": ANALYSIS_DATE, "selected_analysts": ["fundamentals"]}
        response = run_research_request(
            payload, runner=runner, output_root=tmp_path, graph_repository=repo, week2_llm_gateway=gateway
        )
        assert response["status"] == "completed"
        run_id = response["run_id"]

        # --- (a) the pure fact is persisted, with a resolvable reference,
        # in the real source registry. ---
        registry = json.loads((tmp_path / run_id / "source_registry.json").read_text())
        assert registry["sources"], "expected the real fundamentals snapshot to be in the persisted registry"
        source = registry["sources"][0]
        assert source["source_type"] == "financial"

        # --- (b) the REAL API path: get_agent_outputs_response (the same
        # function GET /api/research/{run_id}/agent-outputs calls). ---
        api_response = get_agent_outputs_response(run_id, output_root=tmp_path, graph_repository=repo)
        assert api_response["status"] == "ok"
        api_record = next(
            r for r in api_response["structured_agent_outputs"] if r.get("source_link_status") == "VALID"
        )
        assert api_record["source_link_method"] == "ORIGINAL_AGENT_MARKER_CITED"
        assert api_record["linked_source_id"] == source["source_id"]
        assert api_record["linked_source"]["instrument"] == TICKER
        # agent_output_reader.py's own module docstring: claim_quality is
        # NEVER a public/API field (not in PUBLIC_STRUCTURED_OUTPUT_FIELDS)
        # -- it is used internally, before whitelist projection, to decide
        # whether a record is kept in this response AT ALL (claim_quality.
        # is_claim_eligible(record, "product_findings"); CONTEXT_ONLY and
        # NON_SUBSTANTIVE are dropped). This record's mere PRESENCE in
        # api_response["structured_agent_outputs"] IS the proof it passed
        # that gate as ANALYTICAL -- unlike ScenarioA's bare, context_only
        # snapshot claim, which this same endpoint correctly omits
        # entirely. Independently confirmed against the persisted on-disk
        # record below (the one place claim_quality IS actually stamped).
        persisted_structured = json.loads((tmp_path / run_id / "structured_agent_outputs.json").read_text())
        persisted_record = next(
            r for r in persisted_structured["records"] if r["claim_id"] == api_record["claim_id"]
        )
        assert persisted_record["claim_quality"] == "analytical"

        # --- (c) the REAL Export path: get_run_export_bundle (the same
        # function GET /api/research/{run_id}/export calls -- it only zips
        # already-persisted files from disk, it never recomputes anything,
        # see that function's own docstring). ---
        status_code, content_type, raw_bytes, filename, error_body = get_run_export_bundle(
            run_id, output_root=tmp_path
        )
        assert status_code == 200, error_body
        assert content_type == "application/zip"
        exported_structured = _read_zip_json(raw_bytes, "structured_agent_outputs.json")
        exported_registry = _read_zip_json(raw_bytes, "source_registry.json")

        exported_record = next(
            r for r in exported_structured["records"] if r["claim_id"] == api_record["claim_id"]
        )
        assert exported_record["source_link_status"] == "VALID"
        assert exported_record["source_link_method"] == "ORIGINAL_AGENT_MARKER_CITED"
        assert exported_record["linked_source_id"] == source["source_id"]

        exported_source = next(
            s for s in exported_registry["sources"] if s["source_id"] == exported_record["linked_source_id"]
        )
        assert exported_source["source_type"] == "financial"
        assert exported_source["instrument"] == TICKER
        assert exported_source["data_snapshot"]["market_cap"] == source["data_snapshot"]["market_cap"]

        # The export bundle's own data is byte-identical to what is on
        # disk right now -- confirming the export truly never recomputes,
        # it only bundles the exact files the API itself just read.
        assert exported_structured == json.loads((tmp_path / run_id / "structured_agent_outputs.json").read_text())
        assert exported_registry == registry
