"""T1 source-linking / evidence-support chain -- end-to-end pipeline tests
(COMQUTOR Alpha next-round task, 2026-09-26).

Exercises the REAL production functions across every stage of the news-
source-fragment chain named in the task as the first complete chain:

    取数 (tradingagents.dataflows.yfinance_news + source_capture)
    -> source_registry.json (comqutor_alpha.source_provenance)
    -> structured extraction (comqutor_alpha.structure_engine.
       structured_output_adapter.save_structured_agent_outputs, the real
       top-level production entrypoint -- llm_gateway=None so extraction is
       fully deterministic, zero Provider calls)
    -> Evidence Fact grouping (comqutor_alpha.graph_engine.
       evidence_fact_index.group_evidence_candidates)
    -> API (comqutor_alpha.api.agent_output_reader.get_agent_outputs_response)

Every fixture here is either a real captured record (built via
tradingagents.dataflows.source_capture, a monkeypatched yfinance.Ticker --
never a real request) or an explicitly-labeled synthetic fixture -- never a
claim that a model's semantic accuracy has been validated (see each test's
own docstring). Zero Provider calls, zero network, zero TradingAgents graph
invocation anywhere in this file.
"""

from __future__ import annotations

import json

import pytest

import tradingagents.dataflows.yfinance_news as ynews
from comqutor_alpha.api.agent_output_reader import get_agent_outputs_response
from comqutor_alpha.graph_engine.evidence_fact_index import (
    EvidenceFactCandidate,
    group_evidence_candidates,
)
from comqutor_alpha.source_provenance import build_source_registry
from comqutor_alpha.storage.file_store import save_json_record
from comqutor_alpha.structure_engine.structured_output_adapter import (
    SOURCE_LINK_METHOD_CONTENT_MATCH_CANDIDATE,
    SOURCE_LINK_METHOD_ORIGINAL_AGENT_MARKER,
    save_structured_agent_outputs,
)
from tradingagents.dataflows.source_capture import source_capture_scope
from tests._network_guard import network_guard

# Network-leak fix follow-up (2026-09-26): the executable network block must
# cover every test package actually exercised this round, not only
# tests/structured_output_shadow -- this file calls the real
# save_structured_agent_outputs/get_agent_outputs_response production
# entrypoints, so the same fail-fast-on-any-real-connection guarantee
# applies here too.
_block_real_network_autouse = pytest.fixture(autouse=True)(lambda network_guard: None)

RUN_ID = "t1-source-linking-e2e-run"
TICKER = "NVDA"
ANALYSIS_DATE = "2026-08-10"


class _FakeCitingGateway:
    """Fixed Agent response double for the REAL extraction-stage enrichment
    contract (comqutor_alpha.structure_engine.structured_output_adapter.
    _llm_batch_enrichment / _validate_llm_batch_enrichment -- neither is
    mocked; this only supplies the fixed response text a real LLM gateway
    would supply). Records the exact request it was given (proves the real
    input construction genuinely offers candidate_sources) and cites
    ``cited_source_id`` on every segment in the batch, going through the
    REAL validator via ``validator(payload)`` -- an out-of-scope/forged
    citation is rejected by that real validator, not by this double.

    ``only_where_offered`` (T4 round 34, D1 fix): cite only on the segments the
    request's own candidate_sources list for that id (``segment_ids``) and
    answer null elsewhere -- what the v2 prompt asks for. Without it every
    segment cites the same id, which the per-segment scope check rejects for
    any segment the candidate was not offered for."""

    def __init__(self, cited_source_id, *, only_where_offered=False):
        self._cited_source_id = cited_source_id
        self._only_where_offered = only_where_offered
        self.requests: list[dict] = []

    def invoke_json(self, _kind, request, validator):
        self.requests.append(request)
        offered_for = {
            sid
            for cand in request.get("candidate_sources") or []
            if self._cited_source_id in (cand.get("source_id"), cand.get("fragment_id"))
            for sid in cand.get("segment_ids") or []
        }
        payload = {
            "claims": [
                {
                    "segment_id": seg["segment_id"],
                    "claim": seg["claim"],
                    "evidence": seg["evidence"],
                    "source_section": seg["source_section"],
                    "entities": [],
                    "factors": [],
                    "direction": "unknown",
                    "confidence": 0.8,
                    "cited_source_id": (
                        self._cited_source_id
                        if not self._only_where_offered or seg["segment_id"] in offered_for
                        else None
                    ),
                }
                for seg in request["segments"]
            ]
        }
        try:
            return validator(payload)
        except ValueError:
            return None


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


NVDA_EXCERPT = "NVDA reported strong data center revenue growth this quarter, beating analyst estimates."


def _capture_real_nvda_source(monkeypatch, *, published_date="2026-08-05"):
    """Runs the REAL fetch-stage function (tradingagents.dataflows.
    yfinance_news.get_news_yfinance) against a monkeypatched yfinance.Ticker
    -- never a real request -- and returns the genuinely-captured record
    list, exactly as tradingagents_output_writer.save_comqutor_run_outputs
    would receive it from source_capture_scope."""
    articles = [
        _flat_article(
            "NVDA Data Center Revenue Beats Estimates", "Reuters",
            "https://reuters.com/nvda-dc", _epoch(published_date), NVDA_EXCERPT,
        )
    ]
    monkeypatch.setattr(ynews.yf, "Ticker", lambda symbol: _FakeTicker(articles))
    monkeypatch.setattr(ynews, "normalize_symbol", lambda ticker: ticker)
    with source_capture_scope() as sink:
        ynews.get_news_yfinance(TICKER, "2026-08-01", "2026-08-09")
    return list(sink)


def _capture_two_real_nvda_sources(monkeypatch, *, published_date="2026-08-05"):
    """Same real fetch-stage function as ``_capture_real_nvda_source``, but
    captures TWO distinct articles (different publisher/title/link -- so
    each gets its own genuine ``source_id``/``fragment_id``) reporting the
    SAME underlying fact via the identical excerpt text -- the fixture
    Scenario (i) below needs to prove that merging claims which cite
    DIFFERENT real sources into one Evidence Fact never drops either
    member's own distinct source reference."""
    articles = [
        _flat_article(
            "NVDA Data Center Revenue Beats Estimates", "Reuters",
            "https://reuters.com/nvda-dc", _epoch(published_date), NVDA_EXCERPT,
        ),
        _flat_article(
            "NVDA Posts Record Data Center Sales", "Bloomberg",
            "https://bloomberg.com/nvda-dc-2", _epoch(published_date), NVDA_EXCERPT,
        ),
    ]
    monkeypatch.setattr(ynews.yf, "Ticker", lambda symbol: _FakeTicker(articles))
    monkeypatch.setattr(ynews, "normalize_symbol", lambda ticker: ticker)
    with source_capture_scope() as sink:
        ynews.get_news_yfinance(TICKER, "2026-08-01", "2026-08-09")
    return list(sink)


def _write_run_fixture(tmp_path, *, agent_outputs, captured_sources, analysis_date=ANALYSIS_DATE):
    output_root = tmp_path
    save_json_record(
        RUN_ID, "metadata.json",
        {"run_id": RUN_ID, "ticker": TICKER, "analysis_date": analysis_date},
        output_root=str(output_root),
    )
    save_json_record(
        RUN_ID, "raw_agent_outputs.json",
        {"schema_version": "raw.v1", "run_id": RUN_ID, "ticker": TICKER, "agent_outputs": agent_outputs},
        output_root=str(output_root),
    )
    if captured_sources:
        registry = build_source_registry(
            run_id=RUN_ID, ticker=TICKER, retrieved_at="2026-08-10T00:00:00Z", captured_records=captured_sources
        )
        save_json_record(RUN_ID, "source_registry.json", registry, output_root=str(output_root))
        return registry
    return None


def _run_dir(tmp_path):
    return tmp_path / RUN_ID


# ---------------------------------------------------------------------------
# Scenario (a): correct fragment reference propagates end-to-end, API/export
# agree (export is a verbatim file copy of structured_agent_outputs.json --
# see comqutor_alpha/api/artifact_export.py's REQUIRED_ARTIFACT_FILENAMES --
# so API-level consistency here is the same content Export would ship).
# ---------------------------------------------------------------------------


class TestScenarioA_ValidLinkPropagatesEndToEnd:
    def test_real_captured_excerpt_produces_a_valid_link_through_the_real_pipeline(self, tmp_path, monkeypatch):
        captured = _capture_real_nvda_source(monkeypatch)
        agent_outputs = [
            {
                "agent": "news_agent",
                "agent_output_id": f"{RUN_ID}:news_agent:news_report",
                "raw_output": f"{NVDA_EXCERPT} Shares rallied on the news.",
            }
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, captured_sources=captured)

        # Real production entrypoint, zero Provider calls (llm_gateway=None
        # -> fully deterministic extraction path).
        save_structured_agent_outputs(_run_dir(tmp_path), llm_gateway=None)

        persisted = json.loads((_run_dir(tmp_path) / "structured_agent_outputs.json").read_text())
        linked_records = [r for r in persisted["records"] if r.get("source_link_status") == "VALID"]
        assert linked_records, "expected at least one claim to link to the captured NVDA source"
        record = linked_records[0]
        assert record["linked_source_id"] is not None
        assert record["content_support_status"] == "PENDING_REVIEW"

        # API response must show the SAME status/reference for the SAME
        # persisted claim -- and the real excerpt, not a fabricated one.
        response = get_agent_outputs_response(RUN_ID, output_root=str(tmp_path))
        assert response["status"] == "ok"
        api_record = next(r for r in response["structured_agent_outputs"] if r["claim_id"] == record["claim_id"])
        assert api_record["source_link_status"] == "VALID"
        assert api_record["linked_source"]["excerpt"] == NVDA_EXCERPT
        assert api_record["content_support_status"] == "PENDING_REVIEW"


# ---------------------------------------------------------------------------
# Scenario (b)/(c): source real but not supportive; opposing/background/
# citation/conditional/unreviewed -- explicitly-labeled synthetic fixtures
# (this module cannot judge semantic support offline -- see source_
# provenance's own docstring). Proves the SCHEMA correctly carries each
# state, not that any new pipeline stage computes them automatically.
# ---------------------------------------------------------------------------


class TestScenarioBC_SupportAxisIsNeverInventedByLinkageAlone:
    @pytest.mark.parametrize(
        "content_support_status",
        ["OPPOSES", "BACKGROUND", "CITATION_ONLY", "CONDITIONAL", "PENDING_REVIEW"],
    )
    def test_a_valid_link_with_each_labeled_support_state_round_trips_through_the_api(
        self, tmp_path, content_support_status
    ):
        # Explicitly-labeled synthetic fixture: simulates the outcome of a
        # (not-yet-built) human/semantic review pass having set
        # content_support_status independently of linkage -- SOURCE_LINK_
        # VALID never implies SUPPORT_SUPPORTS, and this proves the field
        # survives real API projection unmodified whatever it is set to.
        registry = build_source_registry(
            run_id=RUN_ID, ticker=TICKER, retrieved_at="2026-08-10T00:00:00Z",
            captured_records=[
                {"source_type": "news", "name": "Reuters", "title": "NVDA Data Center Revenue Beats Estimates",
                 "url": "https://reuters.com/nvda-dc", "published_at": "2026-08-05T00:00:00", "excerpt": NVDA_EXCERPT}
            ],
        )
        save_json_record(RUN_ID, "source_registry.json", registry, output_root=str(tmp_path))
        source_id = registry["sources"][0]["source_id"]
        record = {
            "claim_id": f"{RUN_ID}:news_agent:claim:1",
            "agent_output_id": f"{RUN_ID}:news_agent:claim:1",
            "source_agent_output_id": f"{RUN_ID}:news_agent:report",
            "run_id": RUN_ID, "ticker": TICKER, "agent": "news_agent",
            "claim": "NVDA guidance was actually cut for next quarter.",
            "evidence": "NVDA guidance was actually cut for next quarter.",
            "entities": [], "factors": [], "direction": "negative", "confidence": 0.6,
            "source_link_status": "VALID",
            "linked_source_id": source_id,
            "content_support_status": content_support_status,
            "content_support_method": "TEST_FIXTURE_HUMAN_REVIEWED",
        }
        save_json_record(
            RUN_ID, "structured_agent_outputs.json",
            {"schema_version": "week1a.structured_agent_outputs.v2", "run_id": RUN_ID, "ticker": TICKER, "records": [record]},
            output_root=str(tmp_path),
        )
        response = get_agent_outputs_response(RUN_ID, output_root=str(tmp_path))
        api_record = response["structured_agent_outputs"][0]
        assert api_record["source_link_status"] == "VALID"
        assert api_record["content_support_status"] == content_support_status
        assert api_record["linked_source"]["source_id"] == source_id


# ---------------------------------------------------------------------------
# Scenario (d): forged id, out-of-scope reference, time-invalid, missing
# fragment -- all rejected/downgraded, never silently accepted.
# ---------------------------------------------------------------------------


class TestScenarioD_InvalidReferencesAreRejectedOrDowngraded:
    def test_a_claim_whose_evidence_never_matches_any_captured_excerpt_gets_no_forced_link(
        self, tmp_path, monkeypatch
    ):
        captured = _capture_real_nvda_source(monkeypatch)
        agent_outputs = [
            {
                "agent": "news_agent",
                "agent_output_id": f"{RUN_ID}:news_agent:news_report",
                "raw_output": "Completely unrelated commentary about AMD's roadmap and nothing else.",
            }
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, captured_sources=captured)
        save_structured_agent_outputs(_run_dir(tmp_path), llm_gateway=None)

        persisted = json.loads((_run_dir(tmp_path) / "structured_agent_outputs.json").read_text())
        for record in persisted["records"]:
            assert record["source_link_status"] in ("NOT_PROVIDED",)
            assert record["content_support_status"] == "NOT_APPLICABLE"
            assert record["linked_source_id"] is None

    def test_a_source_published_after_the_evidence_cutoff_is_rejected_never_used_as_look_ahead(
        self, tmp_path, monkeypatch
    ):
        # Captured normally (published 2026-08-05, inside the fetch
        # window's own look-ahead-safe filter -- that filter is a SEPARATE,
        # already-existing fetch-time mechanism this test does not
        # exercise). This run's own analysis_date (evidence cutoff) is set
        # EARLIER, at 2026-08-01 -- simulating a source whose registry entry
        # legitimately predates this specific run's own evidence cutoff
        # (e.g. a shared/reused registry) -- validate_source_reference must
        # independently reject it, never relying solely on the fetch-time
        # filter having already run.
        captured = _capture_real_nvda_source(monkeypatch, published_date="2026-08-05")
        agent_outputs = [
            {
                "agent": "news_agent",
                "agent_output_id": f"{RUN_ID}:news_agent:news_report",
                "raw_output": f"{NVDA_EXCERPT} Shares rallied on the news.",
            }
        ]
        _write_run_fixture(
            tmp_path, agent_outputs=agent_outputs, captured_sources=captured, analysis_date="2026-08-01"
        )
        save_structured_agent_outputs(_run_dir(tmp_path), llm_gateway=None)

        persisted = json.loads((_run_dir(tmp_path) / "structured_agent_outputs.json").read_text())
        matched = [r for r in persisted["records"] if r.get("linked_source_id")]
        assert matched, "expected the matcher to still propose the candidate"
        for record in matched:
            assert record["source_link_status"] == "TIME_INVALID"
            assert record["content_support_status"] == "NOT_APPLICABLE"

    def test_a_forged_source_id_injected_directly_into_a_record_is_never_exposed_as_linked(self, tmp_path):
        # Simulates the exact failure mode T1 forbids: a value that looks
        # like a source reference but was never validated (e.g. a future
        # live wiring where an extraction-stage LLM invents one). The API
        # layer must re-resolve linked_source_id against the REAL registry
        # at read time -- an id absent from it is never exposed as a
        # linked_source object, no matter what source_link_status a
        # (buggy/malicious) upstream record claims.
        registry = build_source_registry(
            run_id=RUN_ID, ticker=TICKER, retrieved_at="2026-08-10T00:00:00Z",
            captured_records=[
                {"source_type": "news", "name": "Reuters", "title": "A Real Captured Headline",
                 "url": "https://reuters.com/x", "published_at": "2026-08-05T00:00:00", "excerpt": NVDA_EXCERPT}
            ],
        )
        save_json_record(RUN_ID, "source_registry.json", registry, output_root=str(tmp_path))
        record = {
            "claim_id": f"{RUN_ID}:news_agent:claim:1",
            "agent_output_id": f"{RUN_ID}:news_agent:claim:1",
            "source_agent_output_id": f"{RUN_ID}:news_agent:report",
            "run_id": RUN_ID, "ticker": TICKER, "agent": "news_agent",
            "claim": "NVDA revenue growth accelerated sharply this quarter.",
            "evidence": "NVDA revenue growth accelerated sharply this quarter.",
            "entities": [], "factors": [], "direction": "positive", "confidence": 0.6,
            # Claims VALID, but this id was never validated against the
            # real registry above -- a forged/hallucinated reference.
            "source_link_status": "VALID",
            "linked_source_id": "src_model_hallucinated_0000",
            "content_support_status": "PENDING_REVIEW",
        }
        save_json_record(
            RUN_ID, "structured_agent_outputs.json",
            {"schema_version": "week1a.structured_agent_outputs.v2", "run_id": RUN_ID, "ticker": TICKER, "records": [record]},
            output_root=str(tmp_path),
        )
        response = get_agent_outputs_response(RUN_ID, output_root=str(tmp_path))
        api_record = response["structured_agent_outputs"][0]
        # The raw (forged) status/id fields are still copied through
        # verbatim (they are whatever the persisted record says) -- but the
        # RESOLVED object is the real backend validation boundary, and it
        # correctly refuses to resolve an id absent from the real registry.
        assert api_record["linked_source"] is None


# ---------------------------------------------------------------------------
# Scenario (e)/(f): same-source duplicate citation never inflates strength;
# merged group preserves every original claim reference.
# ---------------------------------------------------------------------------


class TestScenarioEF_DedupPreservesReferencesNeverInflates:
    def test_two_agents_citing_the_same_captured_source_merge_into_one_evidence_fact(self, tmp_path, monkeypatch):
        captured = _capture_real_nvda_source(monkeypatch)
        agent_outputs = [
            {
                "agent": "news_agent",
                "agent_output_id": f"{RUN_ID}:news_agent:news_report",
                "raw_output": f"{NVDA_EXCERPT} Shares rallied on the news.",
            },
            {
                "agent": "fundamentals_agent",
                "agent_output_id": f"{RUN_ID}:fundamentals_agent:report",
                "raw_output": f"Per the wire: {NVDA_EXCERPT} This confirms strong AI demand.",
            },
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, captured_sources=captured)
        save_structured_agent_outputs(_run_dir(tmp_path), llm_gateway=None)

        persisted = json.loads((_run_dir(tmp_path) / "structured_agent_outputs.json").read_text())
        linked = [r for r in persisted["records"] if r.get("source_link_status") == "VALID"]
        assert len({r["agent"] for r in linked}) == 2, "expected both agents to independently link the same source"
        linked_source_ids = {r["linked_source_id"] for r in linked}
        assert len(linked_source_ids) == 1, "both claims must resolve to the identical source_id"

        candidates = [
            EvidenceFactCandidate(
                claim_id=r["claim_id"], claim_text=r["evidence"],
                linked_source_id=r["linked_source_id"] if r["source_link_status"] == "VALID" else None,
            )
            for r in linked
        ]
        groups = group_evidence_candidates(candidates, TICKER)
        assert len(groups) == 1, "same underlying source cited by two agents must not count as independent evidence"
        # (f): merging preserves every original claim reference -- neither
        # claim_id is dropped by the merge.
        merged_claim_ids = {member.claim_id for member in groups[0]}
        assert merged_claim_ids == {r["claim_id"] for r in linked}

    def test_two_different_sources_merged_into_one_fact_each_keep_their_own_reference_readable_via_api(
        self, tmp_path, monkeypatch
    ):
        """Part 3 (2026-09-28): merging claims that cite DIFFERENT real
        sources into one Evidence Fact must never collapse/drop either
        member's own claim_id/linked_source_id/content_support_review --
        each must remain individually, correctly readable through the same
        REAL API entrypoint (get_agent_outputs_response) the export path
        also serves (artifact_export.py ships structured_agent_outputs.json
        verbatim).

        Both captured sources here carry the identical excerpt text (a
        realistic case: two wires reporting the same fact verbatim) --
        deterministic content-matching alone cannot disambiguate which
        specific one each claim came from, so this uses the REAL
        AGENT_CITED contract (each agent's own extraction-stage citation,
        validated by the real ``_validate_llm_batch_enrichment`` against
        its own batch's real ``candidate_sources``) to pin each claim to a
        DIFFERENT one of the two, exactly as a genuine Agent citation
        would."""
        captured = _capture_two_real_nvda_sources(monkeypatch)
        registry_preview = build_source_registry(
            run_id=RUN_ID, ticker=TICKER, retrieved_at="2026-08-10T00:00:00Z", captured_records=captured
        )
        fragment_id_by_publisher = {s["name"]: s["fragment_id"] for s in registry_preview["sources"]}
        assert len(fragment_id_by_publisher) == 2, "expected two distinct real sources to be captured"

        class _PerAgentCitingGateway:
            def __init__(self, cited_source_id_by_agent):
                self._by_agent = cited_source_id_by_agent
                self.requests: list[dict] = []

            def invoke_json(self, _kind, request, validator):
                self.requests.append(request)
                cited = self._by_agent[request["agent"]]
                payload = {
                    "claims": [
                        {
                            "segment_id": seg["segment_id"], "claim": seg["claim"], "evidence": seg["evidence"],
                            "source_section": seg["source_section"], "entities": [], "factors": [],
                            "direction": "unknown", "confidence": 0.8, "cited_source_id": cited,
                        }
                        for seg in request["segments"]
                    ]
                }
                try:
                    return validator(payload)
                except ValueError:
                    return None

        gateway = _PerAgentCitingGateway(
            {"news_agent": fragment_id_by_publisher["Reuters"], "fundamentals_agent": fragment_id_by_publisher["Bloomberg"]}
        )
        agent_outputs = [
            {
                "agent": "news_agent",
                "agent_output_id": f"{RUN_ID}:news_agent:news_report",
                "raw_output": NVDA_EXCERPT,
            },
            {
                "agent": "fundamentals_agent",
                "agent_output_id": f"{RUN_ID}:fundamentals_agent:report",
                "raw_output": NVDA_EXCERPT,
            },
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, captured_sources=captured)
        save_structured_agent_outputs(_run_dir(tmp_path), llm_gateway=gateway)
        assert gateway.requests, "both agents' extraction batches must actually call the Agent"

        persisted = json.loads((_run_dir(tmp_path) / "structured_agent_outputs.json").read_text())
        linked = [r for r in persisted["records"] if r.get("source_link_status") == "VALID"]
        assert len(linked) == 2, "expected both agents' claims to independently link a real source"
        linked_source_ids = {r["linked_source_id"] for r in linked}
        assert len(linked_source_ids) == 2, "the two claims must resolve to two DISTINCT real sources"

        candidates = [
            EvidenceFactCandidate(
                claim_id=r["claim_id"], claim_text=r["evidence"], linked_source_id=r["linked_source_id"],
            )
            for r in linked
        ]
        groups = group_evidence_candidates(candidates, TICKER)
        assert len(groups) == 1, "two different sources reporting the identical fact must merge into one Evidence Fact"
        merged_claim_ids = {member.claim_id for member in groups[0]}
        assert merged_claim_ids == {r["claim_id"] for r in linked}
        merged_source_ids = {member.linked_source_id for member in groups[0]}
        assert merged_source_ids == linked_source_ids, "each member's own distinct source_id must survive the merge"

        # The merge above is a downstream, in-memory grouping computation --
        # it must never have mutated or collapsed the SEPARATELY persisted
        # per-claim records each member's own reference actually lives in.
        response = get_agent_outputs_response(RUN_ID, output_root=str(tmp_path))
        assert response["status"] == "ok"
        api_records_by_claim_id = {r["claim_id"]: r for r in response["structured_agent_outputs"]}
        for record in linked:
            api_record = api_records_by_claim_id[record["claim_id"]]
            assert api_record["source_link_status"] == "VALID"
            assert api_record["linked_source_id"] == record["linked_source_id"]
            assert api_record["linked_source"]["excerpt"] == NVDA_EXCERPT
        api_linked_source_ids = {api_records_by_claim_id[r["claim_id"]]["linked_source_id"] for r in linked}
        assert api_linked_source_ids == linked_source_ids, "API must expose both distinct source references, never one collapsed into the other"


# ---------------------------------------------------------------------------
# Scenario (g): unqualified evidence correctly downgraded (no forced link).
# ---------------------------------------------------------------------------


class TestScenarioG_UnqualifiedEvidenceDowngradedNotFabricated:
    def test_content_unavailable_source_never_becomes_a_valid_link(self, tmp_path):
        # A source registered by identity alone (no excerpt ever captured,
        # e.g. a filing mentioned only by title) can never be validated as
        # content-locatable, however a candidate might reference it.
        from comqutor_alpha.source_provenance import build_source_record, validate_source_reference

        identity_only = build_source_record(
            source_type="news", name="Reuters", title="A Genuine Headline With No Captured Body",
            url="https://reuters.com/x", retrieved_at="2026-08-10T00:00:00Z",
        )
        result = validate_source_reference(identity_only["source_id"], sources=[identity_only])
        assert result["source_link_status"] == "CONTENT_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Scenario (h): old artifacts missing the new fields are read compatibly,
# never defaulted to "verified"/VALID.
# ---------------------------------------------------------------------------


class TestScenarioH_BackwardCompatibilityWithOldArtifacts:
    def test_a_pre_t1_structured_record_with_no_source_linking_fields_at_all_is_read_safely(self, tmp_path):
        # Exactly what every structured_agent_outputs.json produced before
        # this round looks like -- none of the 4 new fields exist at all.
        old_record = {
            "claim_id": f"{RUN_ID}:news_agent:claim:1",
            "agent_output_id": f"{RUN_ID}:news_agent:claim:1",
            "source_agent_output_id": f"{RUN_ID}:news_agent:report",
            "run_id": RUN_ID, "ticker": TICKER, "agent": "news_agent",
            "claim": "NVDA revenue growth accelerated well before source linking existed.",
            "evidence": "NVDA revenue growth accelerated well before source linking existed.",
            "entities": [], "factors": [], "direction": "positive", "confidence": 0.5,
        }
        save_json_record(
            RUN_ID, "structured_agent_outputs.json",
            {"schema_version": "week1a.structured_agent_outputs.v2", "run_id": RUN_ID, "ticker": TICKER, "records": [old_record]},
            output_root=str(tmp_path),
        )
        response = get_agent_outputs_response(RUN_ID, output_root=str(tmp_path))
        assert response["status"] == "ok"
        api_record = response["structured_agent_outputs"][0]
        # Never fabricated as VALID/verified -- simply absent, exactly like
        # any other optional field an old artifact never had.
        assert "source_link_status" not in api_record or api_record.get("source_link_status") is None
        assert api_record.get("linked_source") is None


# ---------------------------------------------------------------------------
# Part Two/Three follow-up (COMQUTOR Alpha T1, 2026-09-28): a literal
# [fragment_id: ...] marker embedded by tradingagents.dataflows.
# yfinance_news._source_reference_marker directly into the tool message the
# ORIGINAL research agent (news_agent) itself reads, surviving verbatim
# into that agent's own free-text report -- and correctly recognized at
# the (LLM-free, deterministic) extraction stage as a DIFFERENT, ORIGINAL-
# AGENT-level citation, never conflated with the SEPARATE, LATER
# extraction-stage Agent's own structured cited_source_id, nor with a bare
# content-match coincidence.
# ---------------------------------------------------------------------------


class TestOriginalAgentMarkerSurvivesIntoDeterministicLinking:
    def test_a_real_fragment_id_marker_in_the_agents_own_report_text_is_recognized_as_original_agent_citation(
        self, tmp_path, monkeypatch
    ):
        captured = _capture_real_nvda_source(monkeypatch)
        registry_preview = build_source_registry(
            run_id=RUN_ID, ticker=TICKER, retrieved_at="2026-08-10T00:00:00Z", captured_records=captured
        )
        fragment_id = registry_preview["sources"][0]["fragment_id"]
        # The exact real tool-message shape yfinance_news.get_news_yfinance
        # now emits: the marker on its own line, immediately followed by
        # the genuine, unaltered excerpt -- simulating an agent report that
        # preserved the marker verbatim while paraphrasing everything else
        # around it.
        agent_outputs = [
            {
                "agent": "news_agent",
                "agent_output_id": f"{RUN_ID}:news_agent:news_report",
                "raw_output": f"[fragment_id: {fragment_id}] {NVDA_EXCERPT}",
            }
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, captured_sources=captured)

        # Deterministic path, llm_gateway=None -- zero Provider calls, zero
        # extraction-stage Agent citation possible at all. Any link found
        # here can only come from the marker or from plain content-overlap.
        save_structured_agent_outputs(_run_dir(tmp_path), llm_gateway=None)

        persisted = json.loads((_run_dir(tmp_path) / "structured_agent_outputs.json").read_text())
        linked = [r for r in persisted["records"] if r.get("source_link_status") == "VALID"]
        assert linked, "expected the marker to produce a valid link even with zero Agent/LLM involvement"
        record = linked[0]
        # linked_source_id is always the resolved SOURCE's own source_id
        # (validate_source_reference's established contract), regardless of
        # whether the candidate that resolved it was a fragment_id or a
        # bare source_id -- see that function's own docstring.
        assert record["linked_source_id"] == registry_preview["sources"][0]["source_id"]
        assert record["source_link_method"] == SOURCE_LINK_METHOD_ORIGINAL_AGENT_MARKER
        assert record["source_link_method"] != SOURCE_LINK_METHOD_CONTENT_MATCH_CANDIDATE, (
            "an explicit, resolvable marker must never be reported as a mere text-overlap coincidence"
        )

    def test_a_forged_marker_that_does_not_resolve_in_this_runs_registry_is_never_trusted(self, tmp_path, monkeypatch):
        captured = _capture_real_nvda_source(monkeypatch)
        agent_outputs = [
            {
                "agent": "news_agent",
                "agent_output_id": f"{RUN_ID}:news_agent:news_report",
                "raw_output": f"[fragment_id: src_0000000000000000:frag:0] {NVDA_EXCERPT}",
            }
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, captured_sources=captured)
        save_structured_agent_outputs(_run_dir(tmp_path), llm_gateway=None)

        persisted = json.loads((_run_dir(tmp_path) / "structured_agent_outputs.json").read_text())
        record = next(r for r in persisted["records"])
        # The forged marker must never be trusted -- but the SAME claim
        # text also contains the real, unmarked excerpt verbatim, so the
        # existing content-match fallback still finds the real source; it
        # must never be attributed to the (fake) marker path.
        assert record["source_link_status"] == "VALID"
        assert record["linked_source_id"] != "src_0000000000000000:frag:0"
        assert record["source_link_method"] == SOURCE_LINK_METHOD_CONTENT_MATCH_CANDIDATE


class TestAgentInputCarriesRealSourceIds:
    def _build_registry_and_batch(self, tmp_path):
        registry = build_source_registry(
            run_id=RUN_ID, ticker=TICKER, retrieved_at="2026-08-10T00:00:00Z",
            captured_records=[
                {
                    "source_type": "news", "name": "Reuters",
                    "title": "NVDA Data Center Revenue Beats Estimates",
                    "url": "https://reuters.com/nvda-dc", "published_at": "2026-08-05T00:00:00",
                    "excerpt": NVDA_EXCERPT,
                },
                {
                    "source_type": "news", "name": "Barron's",
                    "title": "AMD Discusses Roadmap At Investor Day",
                    "url": "https://barrons.com/amd-roadmap", "published_at": "2026-08-05T00:00:00",
                    "excerpt": "AMD outlined its next-generation roadmap at its annual investor day event.",
                },
            ],
        )
        save_json_record(RUN_ID, "source_registry.json", registry, output_root=str(tmp_path))
        return registry

    def test_agent_input_request_offers_real_source_id_fragment_id_and_excerpt(self, tmp_path):
        registry = self._build_registry_and_batch(tmp_path)
        nvda_source = next(s for s in registry["sources"] if s["excerpt"] == NVDA_EXCERPT)
        agent_outputs = [
            {
                "agent": "news_agent",
                "agent_output_id": f"{RUN_ID}:news_agent:news_report",
                "raw_output": f"{NVDA_EXCERPT} Shares rallied on the news.",
            }
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, captured_sources=None)
        # _write_run_fixture with captured_sources=None skips writing a
        # registry -- write the two-source one built above instead.
        gateway = _FakeCitingGateway(nvda_source["fragment_id"])
        save_structured_agent_outputs(_run_dir(tmp_path), llm_gateway=gateway)

        assert gateway.requests, "the Agent must actually be called"
        offered = gateway.requests[0]["candidate_sources"]
        assert {s["source_id"] for s in offered} == {nvda_source["source_id"]}
        assert offered[0]["fragment_id"] == nvda_source["fragment_id"]
        assert offered[0]["excerpt"] == NVDA_EXCERPT
        # The AMD source (irrelevant to this agent's own report text) is
        # never offered -- candidate_sources is a narrow, batch-scoped
        # subset (only source_id/fragment_id/excerpt, never other internal
        # fields), never the whole run registry. Already proven by the
        # exact-set assertion above (a single NVDA entry), reconfirmed here
        # by excerpt content.
        assert len(offered) == 1
        assert "AMD" not in offered[0]["excerpt"]

    def test_agent_cited_id_is_preserved_verbatim_through_extraction_never_reguessed(self, tmp_path):
        registry = self._build_registry_and_batch(tmp_path)
        nvda_source = next(s for s in registry["sources"] if s["excerpt"] == NVDA_EXCERPT)
        agent_outputs = [
            {
                "agent": "news_agent",
                "agent_output_id": f"{RUN_ID}:news_agent:news_report",
                "raw_output": f"{NVDA_EXCERPT} Shares rallied on the news.",
            }
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, captured_sources=None)
        # T4 round 34 (D1 fix): cite only where the request offered the id (the
        # "Shares rallied" segment has no candidate and answers null).
        gateway = _FakeCitingGateway(nvda_source["fragment_id"], only_where_offered=True)
        save_structured_agent_outputs(_run_dir(tmp_path), llm_gateway=gateway)

        persisted = json.loads((_run_dir(tmp_path) / "structured_agent_outputs.json").read_text())
        cited = [r for r in persisted["records"] if r.get("source_link_method") == "AGENT_CITED"]
        assert cited, "expected at least one record to carry the Agent's own explicit citation"
        record = cited[0]
        assert record["linked_source_id"] == nvda_source["source_id"]
        assert record["source_link_status"] == "VALID"
        assert record["extraction_method"] == "llm_strict_json"

        # API round-trip shows the SAME method/reference.
        response = get_agent_outputs_response(RUN_ID, output_root=str(tmp_path))
        api_record = next(r for r in response["structured_agent_outputs"] if r["claim_id"] == record["claim_id"])
        assert api_record["source_link_method"] == "AGENT_CITED"
        assert api_record["linked_source"]["source_id"] == nvda_source["source_id"]

    def test_citation_of_a_real_id_never_offered_to_this_step_is_rejected(self, tmp_path):
        # AMD's source is REAL and exists in this run's own registry, but
        # was never offered as a candidate to the news_agent's own batch
        # (its excerpt does not appear anywhere in that agent's report
        # text). The Agent citing it anyway must be rejected -- "belongs to
        # what was actually provided to this step", never merely "exists
        # somewhere in the run's registry".
        registry = self._build_registry_and_batch(tmp_path)
        amd_source = next(s for s in registry["sources"] if "AMD" in s["title"])
        agent_outputs = [
            {
                "agent": "news_agent",
                "agent_output_id": f"{RUN_ID}:news_agent:news_report",
                "raw_output": f"{NVDA_EXCERPT} Shares rallied on the news.",
            }
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, captured_sources=None)
        gateway = _FakeCitingGateway(amd_source["fragment_id"])
        save_structured_agent_outputs(_run_dir(tmp_path), llm_gateway=gateway)

        persisted = json.loads((_run_dir(tmp_path) / "structured_agent_outputs.json").read_text())
        assert not any(r.get("source_link_method") == "AGENT_CITED" for r in persisted["records"])
        # The claim still legitimately links via the auxiliary content-match
        # path instead (its own text really does match the NVDA excerpt).
        # T4 round 34 (D1 fix): the out-of-scope citation now rejects the
        # reply, so the batch falls back to deterministic enrichment; the
        # deterministic records are annotated by the same content matcher.
        matched = [r for r in persisted["records"] if r.get("source_link_status") == "VALID"]
        assert matched
        assert matched[0]["source_link_method"] == "CONTENT_MATCH_CANDIDATE"
        assert matched[0]["linked_source_id"] != amd_source["source_id"]

    def test_citation_of_a_completely_forged_id_is_rejected(self, tmp_path):
        self._build_registry_and_batch(tmp_path)
        agent_outputs = [
            {
                "agent": "news_agent",
                "agent_output_id": f"{RUN_ID}:news_agent:news_report",
                "raw_output": "Completely unrelated commentary with no matching excerpt at all.",
            }
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, captured_sources=None)
        gateway = _FakeCitingGateway("src_model_hallucinated_0000")
        save_structured_agent_outputs(_run_dir(tmp_path), llm_gateway=gateway)

        persisted = json.loads((_run_dir(tmp_path) / "structured_agent_outputs.json").read_text())
        for record in persisted["records"]:
            assert record["source_link_method"] != "AGENT_CITED"
            assert record["source_link_status"] in ("NOT_PROVIDED",)

    def test_deterministic_path_without_an_agent_never_sets_agent_cited(self, tmp_path):
        # No llm_gateway at all -- the extractor must never invent a
        # citation on its own; only a real Agent call can ever produce
        # source_link_method == AGENT_CITED.
        self._build_registry_and_batch(tmp_path)
        agent_outputs = [
            {
                "agent": "news_agent",
                "agent_output_id": f"{RUN_ID}:news_agent:news_report",
                "raw_output": f"{NVDA_EXCERPT} Shares rallied on the news.",
            }
        ]
        _write_run_fixture(tmp_path, agent_outputs=agent_outputs, captured_sources=None)
        save_structured_agent_outputs(_run_dir(tmp_path), llm_gateway=None)

        persisted = json.loads((_run_dir(tmp_path) / "structured_agent_outputs.json").read_text())
        assert not any(r.get("source_link_method") == "AGENT_CITED" for r in persisted["records"])
        assert any(r.get("source_link_method") == "CONTENT_MATCH_CANDIDATE" for r in persisted["records"])
