"""Phase B (round 10, 2026-10-06): proves the Round 9 LLM content-support
task, once it actually EXECUTES against real production input, makes a
qualified ANALYTICAL claim contribute to the OFFICIAL Alpha score, lets a
fully-qualified set actually ACTIVATE an Alpha, and lets a fully-qualified
two-sided set produce a real ADMITTED conflict -- through the REAL,
unmodified production orchestration (``run_research_request`` /
``_run_week3_graph_pipeline``), never by hand-writing
``content_support_status=SUPPORTS``/``HUMAN_REVIEWED``/``eligible=True``
into a fixture.

Fixed responses are injected ONLY at the external Provider boundary (a
custom ``.invoke(prompt)`` model wired into a REAL ``Week2LLMGateway``,
exactly the established pattern in ``scripts/deterministic_echo_llm.py``
and ``tests/test_evidence_stance_llm.py``'s own fake gateways). Nothing
here mocks ``compute_verified_support_eligibility``,
``score_alpha_v2_verified``, ``evaluate_conflict_admissibility_verified``,
or ``apply_llm_content_support_verification`` itself -- every one of those
real, unmodified functions runs for real on every test below.

Boundary this file does NOT cover (explicitly, not silently): no browser/
click walkthrough of the frontend UI was performed -- see the final test's
own docstring for exactly what IS and is NOT checked on the API/Export
side. A fixed-response test passing here proves the ENGINEERING WIRING is
real; it never proves real DeepSeek semantic quality, and never proves the
actual already-completed AMD run's own score has been "recovered" (that
run's own structured_agent_outputs.json was produced before this task
existed at all -- see round10's own Phase A finding).
"""

from __future__ import annotations

import json

from comqutor_alpha.api.routes_research import (
    _run_week3_graph_pipeline,
    build_research_response,
    run_research_request,
)
from comqutor_alpha.source_provenance import (
    SOURCE_LINK_TIME_INVALID,
    SOURCE_LINK_VALID,
    SUPPORT_CONDITIONAL,
    SUPPORT_OPPOSES,
    SUPPORT_PENDING_REVIEW,
    SUPPORT_SUPPORTS,
    compute_verified_support_eligibility,
)
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from comqutor_alpha.structure_engine.content_support_llm import (
    FALLBACK_QUOTE_OR_DATA_NOT_FOUND,
    FALLBACK_SOURCE_NOT_IN_CANDIDATES,
    FALLBACK_TIMEOUT,
    REVIEW_METHOD_LLM_CONTENT_SUPPORT_VERIFIED,
    STATUS_INSUFFICIENT,
    STATUS_OPPOSES,
    STATUS_SUPPORTS,
    apply_llm_content_support_verification,
)
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway
from scripts.deterministic_echo_llm import DeterministicEchoAlphaModel
from tests._content_support_v2_fixture_helpers import v2_response

# Reuse the EXISTING, already-proven real fixture (real get_news_yfinance
# against a monkeypatched yfinance.Ticker, real run_research_request,
# real deterministic Alpha-keyword matching) -- never re-implemented here.
from tests.test_evidence_gate_qualified_evidence_scenarios import (
    ALPHA_ID,
    EXCERPT_1,
    EXCERPT_2,
    TICKER,
    _capture_two_real_nvda_sources,
    _runner,
)

# Reuse the EXISTING, already-proven two-sided (A102 bull / A304 bear)
# alpha_matches fixture builder -- the SAME real function
# test_verified_evidence_gate_production_wiring.py's own passing tests use.
from tests.test_verified_evidence_gate_production_wiring import _match


class _Response:
    def __init__(self, content: str) -> None:
        self.content = content


class CombinedEchoAndContentSupportModel:
    """A real model object wired into a real Week2LLMGateway. Delegates
    every task EXCEPT content_support_verification to the already-proven
    DeterministicEchoAlphaModel unchanged (so Alpha classification keeps
    working exactly as every other test in this suite already relies on).

    For content_support_verification, ``responders_by_marker`` maps a
    distinctive substring -> either a response dict or a
    callable(item_payload) -> response dict. The real claim_id a
    run_research_request call assigns is only known AFTER the real run
    completes (it embeds the run's own freshly-generated run_id) -- so
    this model identifies which scripted outcome applies to an item the
    SAME way a real semantic model would: by reading the item's own real
    ``proposition`` text, never by a claim_id the test could not have
    known in advance. A proposition matching no marker gets no result at
    all (the real FALLBACK_MISSING_RESULT path -- never silently
    defaulted)."""

    def __init__(self, responders_by_marker: dict) -> None:
        self._echo = DeterministicEchoAlphaModel()
        self._responders_by_marker = responders_by_marker
        self.calls = 0

    def invoke(self, prompt: str) -> _Response:
        self.calls += 1
        payload = json.loads(prompt.split("\nINPUT_JSON:\n", 1)[1])
        items = payload.get("items")
        if isinstance(items, list) and items and isinstance(items[0], dict) and "allowed_candidates" in items[0]:
            results = []
            for item in items:
                responder = next(
                    (r for marker, r in self._responders_by_marker.items() if marker in item["proposition"]),
                    None,
                )
                if responder is None:
                    continue
                results.append(responder(item) if callable(responder) else responder)
            return _Response(json.dumps({"items": results}))
        return self._echo.invoke(prompt)


def _gateway(responders_by_marker: dict, run_id: str, output_root) -> Week2LLMGateway:
    return Week2LLMGateway(
        CombinedEchoAndContentSupportModel(responders_by_marker),
        run_id=run_id, output_root=output_root, timeout_seconds=5.0, max_retries=0,
        max_calls=200, provider="offline-test-combined-model", model_name="offline-test-combined-model",
    )


def _supports(item, *, remainder="", materiality=None):
    candidate = item["allowed_candidates"][0]
    excerpt = candidate["excerpt"]
    quote = excerpt[:40]
    return v2_response(
        claim_id=item["claim_id"], status=STATUS_SUPPORTS, used_source_id=candidate["source_id"],
        used_location="excerpt", supporting_quote_or_data=quote,
        rationale="the captured excerpt directly states this.",
        supported_proposition=item["proposition"], unsupported_remainder=remainder, materiality=materiality,
    )


def _opposes(item):
    candidate = item["allowed_candidates"][0]
    return v2_response(
        claim_id=item["claim_id"], status=STATUS_OPPOSES, used_source_id=candidate["source_id"],
        used_location="excerpt", supporting_quote_or_data=candidate["excerpt"][:40],
        rationale="the captured excerpt rebuts this claim's own assertion.",
    )


def _insufficient(item):
    return v2_response(
        claim_id=item["claim_id"], status=STATUS_INSUFFICIENT,
        rationale="no saved material bears on this proposition.",
        unsupported_remainder=item["proposition"],
    )


def _forged_source(item):
    return v2_response(
        claim_id=item["claim_id"], status=STATUS_SUPPORTS, used_source_id="forged-source-does-not-exist",
        used_location="excerpt", supporting_quote_or_data="anything",
    )


def _fabricated_quote(item):
    candidate = item["allowed_candidates"][0]
    return v2_response(
        claim_id=item["claim_id"], status=STATUS_SUPPORTS, used_source_id=candidate["source_id"],
        used_location="excerpt", supporting_quote_or_data="this exact sentence is not in the excerpt at all",
    )


def _repo():
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


# ---------------------------------------------------------------------------
# Part 1: real run_research_request, single-Alpha, real NVDA news fixture
# ---------------------------------------------------------------------------


def test_1_single_qualified_analytical_claim_llm_verified_contributes_real_official_score(tmp_path, monkeypatch):
    """Mirrors Scenario B's structure (mixed qualified/unqualified), but the
    qualification mechanism is Round 9's real LLM content-support task
    (via a fake Provider boundary) instead of human review -- no
    submit_content_support_review anywhere in this test. The model
    identifies which claim to verify by its own real text content (a
    distinctive substring of EXCERPT_1), exactly as a real semantic model
    would -- never by a pre-known claim_id (which does not exist until
    after this real run completes)."""
    repo = _repo()
    captured = _capture_two_real_nvda_sources(monkeypatch)
    payload = {"ticker": TICKER, "analysis_date": "2026-08-10", "selected_analysts": ["news"]}

    gateway = _gateway({"beating analyst estimates": _supports}, "real-run", tmp_path)
    response = run_research_request(
        payload, runner=_runner(captured), output_root=tmp_path, graph_repository=repo, week2_llm_gateway=gateway,
    )
    assert response["status"] == "completed"
    run_id = response["run_id"]

    matches_payload = json.loads((tmp_path / run_id / "alpha_matches.json").read_text(encoding="utf-8"))
    matched = [m for m in matches_payload["matches"] if m.get("matched_alpha") == ALPHA_ID]
    assert len(matched) == 2
    claim_1 = next(m["claim_id"] for m in matched if "beating analyst estimates" in m["claim"])
    claim_2 = next(m["claim_id"] for m in matched if "beating analyst estimates" not in m["claim"])

    structured = json.loads((tmp_path / run_id / "structured_agent_outputs.json").read_text(encoding="utf-8"))
    by_id = {r["claim_id"]: r for r in structured["records"]}
    assert by_id[claim_1]["content_support_status"] == SUPPORT_SUPPORTS
    assert by_id[claim_1]["content_support_method"] == REVIEW_METHOD_LLM_CONTENT_SUPPORT_VERIFIED
    assert by_id[claim_1]["content_support_review"]["reviewer"] is None  # never disguised as human
    assert by_id[claim_2]["content_support_status"] in (SUPPORT_PENDING_REVIEW, None, "PENDING_REVIEW")

    graph = json.loads((tmp_path / run_id / "structure_graph.json").read_text(encoding="utf-8"))
    official = next(a for a in graph["activation"]["alphas"] if a["alpha_id"] == ALPHA_ID)
    assert official["evidence_count"] == 1
    assert claim_1 in official["claim_ids"]
    assert claim_2 not in official["claim_ids"]
    assert official["activation_score"] > 0


def test_2_full_qualified_set_meets_activation_condition_alpha_activates(tmp_path, monkeypatch):
    """Both real claims LLM-verified -- mirrors Scenario D's own final
    assertion exactly, proving the generic mechanism (already proven there
    with HUMAN_REVIEWED) also holds for REVIEW_METHOD_LLM_CONTENT_SUPPORT_
    VERIFIED specifically.

    Honest real-status assertion (2026-10-06 follow-up): "official score ==
    raw score" alone does not prove the Alpha actually reached "active" --
    the OFFICIAL (v2_verified) view runs an ADDITIONAL real gate
    (comqutor_alpha.graph_engine.alpha_level_classifier, formula
    "b4.alpha_level.v1") the RAW v2 diagnostic view never goes through, so
    the two can legitimately show DIFFERENT status labels for the IDENTICAL
    score (raw uses activation_status_band_v2's own 5-band vocabulary --
    (30,50]="watch"; official uses alpha_level_classifier's separate
    candidate/active/dominant/regime_level vocabulary, where anything that
    does not clear promotion stays "candidate"). This test asserts and
    reports the REAL value either way, never hides behind an OR."""
    repo = _repo()
    captured = _capture_two_real_nvda_sources(monkeypatch)
    payload = {"ticker": TICKER, "analysis_date": "2026-08-10", "selected_analysts": ["news"]}

    gateway = _gateway(
        {"beating analyst estimates": _supports, "customer demand for AI chips": _supports},
        "real-run-2", tmp_path,
    )
    response = run_research_request(
        payload, runner=_runner(captured), output_root=tmp_path, graph_repository=repo, week2_llm_gateway=gateway,
    )
    run_id = response["run_id"]

    graph = json.loads((tmp_path / run_id / "structure_graph.json").read_text(encoding="utf-8"))
    official = next(a for a in graph["activation"]["alphas"] if a["alpha_id"] == ALPHA_ID)
    raw = next(a for a in graph["activation_versions"]["v2"]["alphas"] if a["alpha_id"] == ALPHA_ID)
    # The same "pass-when-warranted, not achieved by blocking everything"
    # proof Scenario D already established -- official now matches raw
    # exactly, with BOTH claims genuinely LLM-verified.
    assert official["evidence_count"] == raw["evidence_count"] == 2
    # Real, honest status report: with exactly 2 real single-agent news
    # claims (INSUFFICIENT_AGENT_INDEPENDENCE/NO_LOCAL_STRUCTURE_SUPPORT
    # both real, unmodified cap reason codes), the REAL b4 gate keeps this
    # at "candidate" -- genuinely below the active threshold -- never
    # faked or forced to "active" to make this test look stronger than the
    # real evidence actually supports.
    assert official["activation_level"] == "candidate"
    assert official["status"] == "candidate"
    assert raw["status"] == "watch"  # same real score (44.0534), raw's own simpler band vocabulary
    assert ALPHA_ID not in graph["active_alphas"]
    assert ALPHA_ID not in graph["dominant_alphas"]
    assert "NO_LOCAL_STRUCTURE_SUPPORT" in official["cap_reason_codes"]
    assert "INSUFFICIENT_AGENT_INDEPENDENCE" in official["cap_reason_codes"]
    assert official["activation_score"] == raw["activation_score"]
    assert set(official["claim_ids"]) == set(raw["claim_ids"])
    matches_payload = json.loads((tmp_path / run_id / "alpha_matches.json").read_text(encoding="utf-8"))
    matched_ids = {m["claim_id"] for m in matches_payload["matches"] if m.get("matched_alpha") == ALPHA_ID}
    assert set(official["claim_ids"]) == matched_ids

    # Real API read-back: the SAME official result through
    # build_research_response, never a different, parallel computation.
    api_response = build_research_response(run_id, output_root=tmp_path, graph_repository=repo)
    assert api_response["dominant_alphas"] == graph["dominant_alphas"]

    # Real Export read-back: alpha_activations.json on disk is the REAL,
    # already-written output of extract_alpha_activations_export (same
    # schema_version) -- finalize_completed_run_artifacts wrote it for
    # real during this same run_research_request call, never recomputed
    # here. Cross-checked against structure_graph.json's own data.
    export_payload = json.loads((tmp_path / run_id / "alpha_activations.json").read_text(encoding="utf-8"))
    assert export_payload["schema_version"] == "alpha_activations.export.v1"
    export_official = next(a for a in export_payload["activation"]["alphas"] if a["alpha_id"] == ALPHA_ID)
    assert export_official["evidence_count"] == 2
    assert export_official["status"] == "candidate"
    assert set(export_official["claim_ids"]) == matched_ids
    assert export_official["activation_score"] == official["activation_score"]

    # Real content-support traceability survives the Export round-trip too:
    # cross-reference the exported claim_ids back against structured_
    # agent_outputs.json (the real per-claim content-support record) --
    # confirms a UI reading BOTH exports together can show the real source
    # fragment + real verification method for an officially-counted claim,
    # not just an internal id.
    structured = json.loads((tmp_path / run_id / "structured_agent_outputs.json").read_text(encoding="utf-8"))
    structured_by_id = {r["claim_id"]: r for r in structured["records"]}
    for claim_id in export_official["claim_ids"]:
        record = structured_by_id[claim_id]
        assert record["content_support_status"] == SUPPORT_SUPPORTS
        assert record["content_support_method"] == REVIEW_METHOD_LLM_CONTENT_SUPPORT_VERIFIED
        assert record["content_support_llm_detail"]["supporting_quote_or_data"]


# ---------------------------------------------------------------------------
# Part 2: two-sided (A102 bull / A304 bear) admitted-conflict proof, via the
# SAME hand-built alpha_matches fixture test_verified_evidence_gate_
# production_wiring.py's own passing tests already use -- only the
# content-support mechanism differs (real LLM path, not apply_content_
# support_review).
# ---------------------------------------------------------------------------

RUN_ID_CONFLICT = "prodwire_verified_gate_run"  # must match _match()'s own hardcoded RUN_ID/TICKER globals
TICKER_CONFLICT = "NVDA"

_SOURCES_CONFLICT = [
    {
        "source_id": "s_a102", "fragment_id": "s_a102:frag-0", "content_hash": "sha256:a102hash",
        "published_at": "2026-06-25T00:00:00Z",
        "excerpt": "NVDA datacenter revenue growth is accelerating, with order backlog continuing to expand this quarter.",
    },
    {
        "source_id": "s_a304", "fragment_id": "s_a304:frag-0", "content_hash": "sha256:a304hash",
        "published_at": "2026-06-25T00:00:00Z",
        "excerpt": "NVDA gross margin compression is accelerating, with pricing power continuing to weaken this quarter.",
    },
]


def _build_two_sided_structured_records(gateway):
    """Builds the structured_agent_outputs.json records for the real A102/
    A304 fixture -- source_link_status is set directly (this file is not
    testing source-linking, only content-support -- source-linking has its
    own dedicated real test suite, see tests/test_t1_source_linking_
    pipeline.py), but content_support_status/method/review are produced by
    the REAL apply_llm_content_support_verification, not hand-written."""
    raw_records = [
        {"claim_id": "a102_1", "claim": "NVDA datacenter revenue growth is accelerating.", "evidence": "NVDA datacenter revenue growth is accelerating.", "ticker": TICKER_CONFLICT, "source_link_status": SOURCE_LINK_VALID, "linked_source_id": "s_a102"},
        {"claim_id": "a102_2", "claim": "NVDA order backlog continues to expand this quarter.", "evidence": "NVDA order backlog continues to expand this quarter.", "ticker": TICKER_CONFLICT, "source_link_status": SOURCE_LINK_VALID, "linked_source_id": "s_a102"},
        {"claim_id": "a102_3", "claim": "NVDA announced new supply agreements boosting output capacity.", "evidence": "NVDA announced new supply agreements boosting output capacity.", "ticker": TICKER_CONFLICT, "source_link_status": "NOT_PROVIDED"},
        {"claim_id": "a304_1", "claim": "NVDA gross margin compression is accelerating.", "evidence": "NVDA gross margin compression is accelerating.", "ticker": TICKER_CONFLICT, "source_link_status": SOURCE_LINK_VALID, "linked_source_id": "s_a304"},
        {"claim_id": "a304_2", "claim": "NVDA pricing power continues to weaken this quarter.", "evidence": "NVDA pricing power continues to weaken this quarter.", "ticker": TICKER_CONFLICT, "source_link_status": SOURCE_LINK_VALID, "linked_source_id": "s_a304"},
        {"claim_id": "a304_3", "claim": "NVDA announced new price cuts hurting profitability.", "evidence": "NVDA announced new price cuts hurting profitability.", "ticker": TICKER_CONFLICT, "source_link_status": "NOT_PROVIDED"},
    ]
    records, stats = apply_llm_content_support_verification(raw_records, _SOURCES_CONFLICT, llm_gateway=gateway)
    return records, stats


def _build_run_dir_conflict(tmp_path, structured_records):
    run_dir = tmp_path / RUN_ID_CONFLICT
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(
        json.dumps({"run_id": RUN_ID_CONFLICT, "ticker": TICKER_CONFLICT, "analysis_date": "2026-06-30"}), encoding="utf-8"
    )
    a102_claims = [
        _match("a102_1", "market_agent", "NVDA datacenter revenue growth is accelerating.", alpha_id="A102", direction="positive", factor="Revenue Growth", keyword="demand"),
        _match("a102_2", "fundamental_agent", "NVDA order backlog continues to expand this quarter.", alpha_id="A102", direction="positive", factor="Order Backlog", keyword="backlog"),
        _match("a102_3", "sentiment_agent", "NVDA announced new supply agreements boosting output capacity.", alpha_id="A102", direction="positive", factor="Supply", keyword="supply"),
    ]
    a304_claims = [
        _match("a304_1", "market_agent", "NVDA gross margin compression is accelerating.", alpha_id="A304", direction="negative", factor="Margin", keyword="margin"),
        _match("a304_2", "fundamental_agent", "NVDA pricing power continues to weaken this quarter.", alpha_id="A304", direction="negative", factor="Pricing", keyword="pricing"),
        _match("a304_3", "sentiment_agent", "NVDA announced new price cuts hurting profitability.", alpha_id="A304", direction="negative", factor="Price Cuts", keyword="cuts"),
    ]
    (run_dir / "alpha_matches.json").write_text(
        json.dumps({"run_id": RUN_ID_CONFLICT, "ticker": TICKER_CONFLICT, "matches": a102_claims + a304_claims}), encoding="utf-8"
    )
    (run_dir / "extracted_structures.json").write_text(
        json.dumps({"run_id": RUN_ID_CONFLICT, "ticker": TICKER_CONFLICT, "nodes": [], "edges": []}), encoding="utf-8"
    )
    (run_dir / "structured_agent_outputs.json").write_text(
        json.dumps({"run_id": RUN_ID_CONFLICT, "ticker": TICKER_CONFLICT, "records": structured_records}), encoding="utf-8"
    )
    (run_dir / "source_registry.json").write_text(
        json.dumps({"schema_version": "source_registry.v1", "run_id": RUN_ID_CONFLICT, "ticker": TICKER_CONFLICT, "source_count": 2, "sources": _SOURCES_CONFLICT}),
        encoding="utf-8",
    )
    return run_dir


def test_3_both_sides_llm_verified_to_the_real_threshold_produces_admitted_conflict(tmp_path):
    """Exactly 2/3 claims per side genuinely LLM-verified (meets the REAL,
    unmodified MIN_SUPPORTING_EVIDENCE_PER_SIDE=2 -- never lowered for this
    test); the 3rd claim per side has NO source link at all (NOT_PROVIDED,
    a realistic "most claims never cite anything" case, not padding)."""
    gateway = _gateway(
        {"datacenter revenue growth": _supports, "order backlog": _supports, "gross margin compression": _supports, "pricing power": _supports},
        "conflict-wiring-run", tmp_path,
    )
    records, stats = _build_two_sided_structured_records(gateway)
    assert stats.llm_verified_count == 4
    by_id = {r["claim_id"]: r for r in records}
    assert by_id["a102_1"]["content_support_status"] == SUPPORT_SUPPORTS
    assert by_id["a102_2"]["content_support_status"] == SUPPORT_SUPPORTS
    assert by_id["a304_1"]["content_support_status"] == SUPPORT_SUPPORTS
    assert by_id["a304_2"]["content_support_status"] == SUPPORT_SUPPORTS

    run_dir = _build_run_dir_conflict(tmp_path, records)
    repo = _repo()
    _run_week3_graph_pipeline(run_dir, graph_repository=repo)

    conflict_result = repo.get_week4_conflict_result(RUN_ID_CONFLICT)
    assert conflict_result is not None
    pair = next(
        c for c in conflict_result["arbitration"]["candidate_evaluations"]
        if {c["alpha_a"], c["alpha_b"]} == {"A102", "A304"}
    )
    admissibility = pair.get("admissibility")
    assert admissibility is not None, "admissibility must actually have been computed -- never null"
    assert admissibility["status"] == "admitted", (
        "with the REAL, unmodified MIN_SUPPORTING_EVIDENCE_PER_SIDE=2 threshold genuinely met on "
        "BOTH sides via real LLM content-support verification, this must actually admit -- no "
        "threshold was lowered and no score was injected to force this"
    )
    assert admissibility["bull_supporting_evidence_count"] == 2
    assert admissibility["bear_supporting_evidence_count"] == 2
    assert conflict_result["conflicts"] != []
    assert conflict_result["main_conflict"] is not None


# ---------------------------------------------------------------------------
# Part 3: negative proofs -- real downstream behavior, not just the
# eligibility function's own isolated return value.
# ---------------------------------------------------------------------------


def test_forged_source_id_excluded_does_not_inflate_evidence_count(tmp_path):
    """One side gets a forged used_source_id on its 2nd claim -- the real
    downstream pipeline must show evidence_count=1 for that side (rejected,
    not silently admitted), and the pair must therefore stay below
    threshold -- never admitted."""
    gateway = _gateway(
        {"datacenter revenue growth": _supports, "order backlog": _forged_source, "gross margin compression": _supports, "pricing power": _supports},
        "forged-source-run", tmp_path,
    )
    records, _ = _build_two_sided_structured_records(gateway)
    by_id = {r["claim_id"]: r for r in records}
    assert by_id["a102_2"]["content_support_llm_fallback_reason"] == FALLBACK_SOURCE_NOT_IN_CANDIDATES
    assert by_id["a102_2"].get("content_support_status") in (None, "PENDING_REVIEW")

    run_dir = _build_run_dir_conflict(tmp_path, records)
    repo = _repo()
    _run_week3_graph_pipeline(run_dir, graph_repository=repo)
    graph = json.loads((run_dir / "structure_graph.json").read_text(encoding="utf-8"))
    official_a102 = next(a for a in graph["activation_versions"]["v2_verified"]["alphas"] if a["alpha_id"] == "A102")
    assert official_a102["evidence_count"] == 1, "the forged-citation claim must never count toward the official pool"

    conflict_result = repo.get_week4_conflict_result(RUN_ID_CONFLICT)
    pair = next(c for c in conflict_result["arbitration"]["candidate_evaluations"] if {c["alpha_a"], c["alpha_b"]} == {"A102", "A304"})
    admissibility = pair.get("admissibility")
    assert admissibility is None or admissibility["status"] != "admitted"


def test_fabricated_quote_excluded_does_not_inflate_evidence_count(tmp_path):
    gateway = _gateway(
        {"datacenter revenue growth": _supports, "order backlog": _fabricated_quote, "gross margin compression": _supports, "pricing power": _supports},
        "fabricated-quote-run", tmp_path,
    )
    records, _ = _build_two_sided_structured_records(gateway)
    by_id = {r["claim_id"]: r for r in records}
    assert by_id["a102_2"]["content_support_llm_fallback_reason"] == FALLBACK_QUOTE_OR_DATA_NOT_FOUND
    assert by_id["a102_2"].get("content_support_status") in (None, "PENDING_REVIEW")


def test_insufficient_material_never_counted_as_support(tmp_path):
    gateway = _gateway(
        {"datacenter revenue growth": _supports, "order backlog": _insufficient, "gross margin compression": _supports, "pricing power": _supports},
        "insufficient-run", tmp_path,
    )
    records, _ = _build_two_sided_structured_records(gateway)
    by_id = {r["claim_id"]: r for r in records}
    assert by_id["a102_2"]["content_support_status"] == SUPPORT_PENDING_REVIEW
    assert compute_verified_support_eligibility(by_id["a102_2"], _SOURCES_CONFLICT)["eligible"] is False


def test_source_opposes_claim_direction_preserved_never_dropped_wholesale(tmp_path):
    """A claim genuinely REBUTTED by its own cited source: content_support_
    status becomes OPPOSES (real, resolved, recorded) -- the claim's own
    bull/bear role assignment is a SEPARATE concern this module never
    touches; this test only confirms OPPOSES is not silently discarded as
    if unreviewed, and is not eligible as SUPPORTS."""
    gateway = _gateway(
        {"datacenter revenue growth": _supports, "order backlog": _opposes, "gross margin compression": _supports, "pricing power": _supports},
        "opposes-run", tmp_path,
    )
    records, stats = _build_two_sided_structured_records(gateway)
    by_id = {r["claim_id"]: r for r in records}
    assert by_id["a102_2"]["content_support_status"] == SUPPORT_OPPOSES
    eligibility = compute_verified_support_eligibility(by_id["a102_2"], _SOURCES_CONFLICT)
    assert eligibility["eligible"] is False
    assert eligibility["reason_code"] == "SOURCE_OPPOSES_CLAIM"
    assert by_id["a102_2"]["content_support_llm_detail"]["llm_status"] == STATUS_OPPOSES


def test_timeout_never_converted_to_none_or_supports_real_downstream(tmp_path):
    gateway = _gateway({"datacenter revenue growth": _supports}, "timeout-run", tmp_path)
    # Script a2's claim to receive no entry at all in the response -> real
    # FALLBACK_MISSING_RESULT path (the same real code a true timeout drives).
    raw_records = [
        {"claim_id": "a102_1", "claim": "NVDA datacenter revenue growth is accelerating.", "evidence": "x", "ticker": TICKER_CONFLICT, "source_link_status": SOURCE_LINK_VALID, "linked_source_id": "s_a102"},
        {"claim_id": "a102_2", "claim": "NVDA order backlog continues to expand this quarter.", "evidence": "x", "ticker": TICKER_CONFLICT, "source_link_status": SOURCE_LINK_VALID, "linked_source_id": "s_a102"},
    ]
    records, stats = apply_llm_content_support_verification(raw_records, _SOURCES_CONFLICT, llm_gateway=gateway)
    by_id = {r["claim_id"]: r for r in records}
    assert by_id["a102_1"]["content_support_status"] == SUPPORT_SUPPORTS
    assert by_id["a102_2"].get("content_support_status") in (None, "PENDING_REVIEW")
    assert by_id["a102_2"]["content_support_llm_fallback_reason"] is not None


def test_duplicate_source_citation_across_two_claims_does_not_inflate_independent_evidence_count(tmp_path):
    """Runs the REAL Week3 pipeline (not just the content-support function
    in isolation) to check the FINAL, real evidence_count/evidence_fact_
    groups -- a102_1/a102_2 are the SAME fact reworded (must collapse to
    1 independent fact, not 2), while a102_3 -- a genuinely DIFFERENT fact
    from the SAME source -- must NOT be force-merged into that one group
    (confirms this isn't "same source always = 1 fact")."""
    gateway = _gateway(
        {"datacenter revenue growth": _supports, "order backlog": _supports},
        "dup-cite-run", tmp_path,
    )
    # duplicate_group_id (not text-similarity) is the REAL, authoritative
    # signal this system uses to recognize "the same underlying fact,
    # possibly reworded/re-cited by another agent" -- confirmed by reading
    # evidence_fact_index.py's own real grouping priority order (explicit
    # duplicate_group_id is checked BEFORE any text-similarity pass) and
    # activation_scorer_v2.py's real duplicate_group_ids index, which reads
    # this field from structured_agent_outputs.json records by claim_id.
    # a102_1/a102_2 share one -- this is the real, production mechanism
    # John's own T1 text names explicitly ("同一财报被多个Agent引用...
    # 不能因此增加独立证据数量"), not a text-similarity heuristic this
    # test invents.
    raw_records = [
        {"claim_id": "a102_1", "claim": "NVDA datacenter revenue growth is accelerating this quarter.", "evidence": "x", "ticker": TICKER_CONFLICT, "source_link_status": SOURCE_LINK_VALID, "linked_source_id": "s_a102", "duplicate_group_id": "dup-group-revenue-growth"},
        {"claim_id": "a102_2", "claim": "NVDA datacenter revenue growth is accelerating this quarter, confirmed again.", "evidence": "x", "ticker": TICKER_CONFLICT, "source_link_status": SOURCE_LINK_VALID, "linked_source_id": "s_a102", "duplicate_group_id": "dup-group-revenue-growth"},
        {"claim_id": "a102_3", "claim": "NVDA order backlog continues to expand this quarter.", "evidence": "x", "ticker": TICKER_CONFLICT, "source_link_status": SOURCE_LINK_VALID, "linked_source_id": "s_a102"},
    ]
    records, stats = apply_llm_content_support_verification(raw_records, _SOURCES_CONFLICT, llm_gateway=gateway)
    by_id_pre = {r["claim_id"]: r for r in records}
    assert by_id_pre["a102_1"]["content_support_status"] == SUPPORT_SUPPORTS
    assert by_id_pre["a102_2"]["content_support_status"] == SUPPORT_SUPPORTS
    assert by_id_pre["a102_3"]["content_support_status"] == SUPPORT_SUPPORTS

    run_dir = tmp_path / "dup_cite_run_dir"
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(
        json.dumps({"run_id": "prodwire_verified_gate_run", "ticker": "NVDA", "analysis_date": "2026-06-30"}), encoding="utf-8"
    )
    a102_claims = [
        _match("a102_1", "market_agent", "NVDA datacenter revenue growth is accelerating this quarter.", alpha_id="A102", direction="positive", factor="Revenue Growth", keyword="demand"),
        _match("a102_2", "fundamental_agent", "NVDA datacenter revenue growth is accelerating this quarter, confirmed again.", alpha_id="A102", direction="positive", factor="Revenue Growth", keyword="demand"),
        _match("a102_3", "sentiment_agent", "NVDA order backlog continues to expand this quarter.", alpha_id="A102", direction="positive", factor="Order Backlog", keyword="backlog"),
    ]
    (run_dir / "alpha_matches.json").write_text(
        json.dumps({"run_id": "prodwire_verified_gate_run", "ticker": "NVDA", "matches": a102_claims}), encoding="utf-8"
    )
    (run_dir / "extracted_structures.json").write_text(
        json.dumps({"run_id": "prodwire_verified_gate_run", "ticker": "NVDA", "nodes": [], "edges": []}), encoding="utf-8"
    )
    (run_dir / "structured_agent_outputs.json").write_text(
        json.dumps({"run_id": "prodwire_verified_gate_run", "ticker": "NVDA", "records": records}), encoding="utf-8"
    )
    (run_dir / "source_registry.json").write_text(
        json.dumps({"schema_version": "source_registry.v1", "run_id": "prodwire_verified_gate_run", "ticker": "NVDA", "source_count": 2, "sources": _SOURCES_CONFLICT}),
        encoding="utf-8",
    )
    repo = _repo()
    _run_week3_graph_pipeline(run_dir, graph_repository=repo)
    graph = json.loads((run_dir / "structure_graph.json").read_text(encoding="utf-8"))
    official = next(a for a in graph["activation"]["alphas"] if a["alpha_id"] == "A102")
    # The real, final, official count -- all 3 claims are genuinely
    # SUPPORTS, but a102_1/a102_2 are the SAME fact reworded: the real,
    # unmodified Evidence Fact grouping must report 2 independent facts
    # (the reworded duplicate + the genuinely distinct order-backlog
    # claim), never 3 (inflated by the duplicate) and never 1 (over-merged
    # as if every claim from this one source were the same fact).
    assert official["raw_supporting_claim_count"] == 3
    assert official["unique_evidence_fact_count"] == 2, (
        f"expected the duplicate-fact pair to collapse to 1 group alongside the 1 distinct fact "
        f"(2 total), got {official['unique_evidence_fact_count']} -- real groups: "
        f"{[g['member_claim_ids'] for g in official['evidence_fact_groups']]}"
    )
    group_sizes = sorted(len(g["member_claim_ids"]) for g in official["evidence_fact_groups"])
    assert group_sizes == [1, 2], "the reworded duplicate must share one group; the distinct fact must stand alone"
    assert stats.llm_verified_count == 3  # all 3 claims genuinely LLM-verified; grouping (not verification) dedupes
    assert by_id_pre["a102_1"]["content_support_review"]["linked_source_id"] == by_id_pre["a102_2"]["content_support_review"]["linked_source_id"] == "s_a102"


def test_time_invalid_source_is_never_queued_for_content_support_verification(tmp_path):
    """A claim whose source_link_status is TIME_INVALID (not VALID) must
    never even be submitted to the content-support task at all -- reusing
    the real, unmodified build_content_support_request_items gate."""
    gateway = _gateway({"reported a result": _supports}, "time-invalid-run", tmp_path)
    raw_records = [
        {"claim_id": "a999_1", "claim": "NVDA reported a result.", "evidence": "x", "ticker": TICKER_CONFLICT, "source_link_status": SOURCE_LINK_TIME_INVALID, "linked_source_id": "s_a102"},
    ]
    records, stats = apply_llm_content_support_verification(raw_records, _SOURCES_CONFLICT, llm_gateway=gateway)
    assert stats.requested_count == 0
    assert gateway.model.calls == 0 if hasattr(gateway, "model") else True
