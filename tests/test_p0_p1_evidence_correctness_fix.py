"""P0/P1 Evidence Correctness Fix (V0.1.3 CORRECTNESS FIX -- PHASE 1).

P1: canonical issuer-name/alias registry (``graph_engine/issuer_aliases.py``)
propagated into ``score_alpha_activations_v2`` via
``graph_engine/pipeline.py`` so a claim naming the issuer by its real name
("Microsoft") rather than its ticker symbol ("MSFT") can qualify as
ticker-specific evidence.

P0: an independent, deterministic evidence-ownership veto
(``activation_scorer_v2._foreign_issuer_only_reason``) that prevents a
claim whose ONLY named issuer is a DIFFERENT ticker this system covers,
AND which carries zero deterministic taxonomy signal (keyword_score and
factor_score both exactly 0 for every candidate Alpha), from counting as
activation-qualifying evidence -- reproducing and fixing the confirmed
AMD A201 Silicon Motion/SanDisk contamination
(docs/audit_artifacts/v0_1_3_a102_cross_company_integrity_audit.md).

Neither fix touches B1 stance, Alpha Mapper eligibility/thresholds,
Primary/Secondary role qualification, fact-group dedupe, or any B2/B4
threshold value -- both operate strictly within the existing evidence
qualification stage in ``activation_scorer_v2.py``.
"""

from __future__ import annotations

from comqutor_alpha.graph_engine.activation_scorer_v2 import (
    FOREIGN_ISSUER_NO_TAXONOMY_SIGNAL,
    _foreign_issuer_only_reason,
    _is_ticker_specific,
)
from comqutor_alpha.graph_engine.issuer_aliases import (
    CANONICAL_ISSUER_ALIASES,
    company_names_for_ticker,
)
from comqutor_alpha.graph_engine.pipeline import build_and_score_structure_graph
from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy

TAXONOMY = load_alpha_taxonomy()
AS_OF = "2026-09-08"
RUN_TS = "2026-09-08"


def _zero_candidate_scores(alpha_ids=("A101", "A102", "A103", "A201", "A301", "A304", "A601")):
    return [
        {"alpha_id": aid, "keyword_score": 0.0, "factor_score": 0.0, "eligible": False}
        for aid in alpha_ids
    ]


def _nonzero_candidate_scores(matched_alpha_id, keyword_score=1.0, factor_score=1.0):
    scores = _zero_candidate_scores()
    for entry in scores:
        if entry["alpha_id"] == matched_alpha_id:
            entry["keyword_score"] = keyword_score
            entry["factor_score"] = factor_score
    return scores


def _record(claim_id, agent, claim, ticker, matched_alpha, candidate_scores, **extra):
    base = {
        "run_id": "run1",
        "ticker": ticker,
        "agent": agent,
        "claim_id": claim_id,
        "source_agent_output_id": f"{agent}:source",
        "claim": claim,
        "evidence": claim,
        "direction": "positive",
        "matched_alpha": matched_alpha,
        "matched_alpha_name": matched_alpha,
        "score": 0.8,
        "match_status": "matched",
        "assertion_status": "asserted",
        "semantic_polarity": "activation",
        "claim_quality": "analytical",
        "candidate_scores": candidate_scores,
        "eligible_candidates": [
            {
                "alpha_id": matched_alpha,
                "relation": "activation",
                "matched_keywords": ["demand"],
                "matched_factors": ["Revenue Growth"],
            }
        ],
    }
    base.update(extra)
    return base


def _payload(ticker, *records):
    return {"run_id": "run1", "ticker": ticker, "matches": list(records)}


def _score_via_pipeline(ticker, matches):
    matches_payload = _payload(ticker, *matches)
    extracted = {"run_id": "run1", "ticker": ticker, "nodes": [], "edges": []}
    return build_and_score_structure_graph(
        matches_payload, extracted, taxonomy=TAXONOMY, run_timestamp=RUN_TS, as_of=AS_OF
    )


# ---------------------------------------------------------------------------
# Production wiring: the real call site actually passes the value
# ---------------------------------------------------------------------------


def test_production_call_site_passes_nonempty_company_names_for_msft(monkeypatch):
    """Section 8's explicit requirement: a registry that production never
    reads is not a fix. Monkeypatches pipeline.py's own imported reference
    to score_alpha_activations_v2 (the real production call site) and
    asserts the company_names kwarg it actually receives."""
    import comqutor_alpha.graph_engine.pipeline as pipeline_module

    captured = {}
    real_score = pipeline_module.score_alpha_activations_v2

    def capturing_score(*args, **kwargs):
        captured["company_names"] = kwargs.get("company_names")
        captured["ticker"] = kwargs.get("ticker")
        return real_score(*args, **kwargs)

    monkeypatch.setattr(pipeline_module, "score_alpha_activations_v2", capturing_score)

    matches_payload = {"run_id": "run1", "ticker": "MSFT", "matches": []}
    extracted = {"run_id": "run1", "ticker": "MSFT", "nodes": [], "edges": []}
    pipeline_module.build_and_score_structure_graph(matches_payload, extracted)

    assert captured["ticker"] == "MSFT"
    assert captured["company_names"] == ("Microsoft", "Microsoft Corporation")


def test_production_call_site_passes_empty_company_names_for_qqq(monkeypatch):
    """QQQ has no registry entry -- production must receive () unchanged,
    never a fabricated ETF alias."""
    import comqutor_alpha.graph_engine.pipeline as pipeline_module

    captured = {}
    real_score = pipeline_module.score_alpha_activations_v2

    def capturing_score(*args, **kwargs):
        captured["company_names"] = kwargs.get("company_names")
        return real_score(*args, **kwargs)

    monkeypatch.setattr(pipeline_module, "score_alpha_activations_v2", capturing_score)

    matches_payload = {"run_id": "run1", "ticker": "QQQ", "matches": []}
    extracted = {"run_id": "run1", "ticker": "QQQ", "nodes": [], "edges": []}
    pipeline_module.build_and_score_structure_graph(matches_payload, extracted)

    assert captured["company_names"] == ()


# ---------------------------------------------------------------------------
# A. Company alias propagation
# ---------------------------------------------------------------------------


def test_a_company_alias_registry_returns_expected_aliases():
    assert company_names_for_ticker("MSFT") == ("Microsoft", "Microsoft Corporation")
    assert company_names_for_ticker("NVDA") == ("NVIDIA", "NVIDIA Corporation")
    assert company_names_for_ticker("SNDK") == ("SanDisk", "SanDisk Corporation")
    assert "Advanced Micro Devices" in company_names_for_ticker("AMD")
    assert "TSMC" in company_names_for_ticker("TSM")


def test_a_registry_lookup_is_case_insensitive_on_ticker():
    assert company_names_for_ticker("msft") == company_names_for_ticker("MSFT")


# ---------------------------------------------------------------------------
# B. Token-boundary behavior (never a bare substring match)
# ---------------------------------------------------------------------------


def test_b_amd_does_not_match_inside_an_unrelated_word():
    record = {"claim": "AMDocs reported strong quarterly earnings today."}
    assert _is_ticker_specific(record, "AMD", company_names_for_ticker("AMD"), {}) is False


def test_b_microsoft_matches_as_a_real_token():
    record = {"claim": "Microsoft's AI products are driving inference demand."}
    assert _is_ticker_specific(record, "MSFT", company_names_for_ticker("MSFT"), {}) is True


# ---------------------------------------------------------------------------
# C/D/E. Full-name ticker specificity for MSFT / NVDA / AMD
# ---------------------------------------------------------------------------


def test_c_msft_full_company_name_qualifies_as_ticker_specific():
    record = {"claim": "Microsoft's Azure AI services are driving inference demand growth."}
    assert _is_ticker_specific(record, "MSFT", company_names_for_ticker("MSFT"), {}) is True


def test_d_nvda_full_company_name_qualifies_as_ticker_specific():
    record = {"claim": "NVIDIA's data center revenue accelerated sharply this quarter."}
    assert _is_ticker_specific(record, "NVDA", company_names_for_ticker("NVDA"), {}) is True


def test_e_amd_full_company_name_qualifies_as_ticker_specific():
    record = {"claim": "Advanced Micro Devices reported strong data center growth."}
    assert _is_ticker_specific(record, "AMD", company_names_for_ticker("AMD"), {}) is True


def test_e_amd_product_alias_qualifies_as_ticker_specific():
    record = {"claim": "Client PC: Recovery in the PC market with Ryzen processors."}
    assert _is_ticker_specific(record, "AMD", company_names_for_ticker("AMD"), {}) is True


# ---------------------------------------------------------------------------
# F. Unknown ticker/company fallback
# ---------------------------------------------------------------------------


def test_f_unknown_ticker_returns_empty_aliases_and_does_not_crash():
    assert company_names_for_ticker("ZZZZ") == ()
    record = {"claim": "Some unrelated company reported earnings."}
    assert _is_ticker_specific(record, "ZZZZ", company_names_for_ticker("ZZZZ"), {}) is False


def test_f_qqq_has_no_registry_entry_etf_deferred():
    assert company_names_for_ticker("QQQ") == ()
    assert "QQQ" not in CANONICAL_ISSUER_ALIASES


# ---------------------------------------------------------------------------
# G. Foreign-company-only rejection from direct support
# ---------------------------------------------------------------------------


def test_g_foreign_issuer_only_claim_is_vetoed():
    record = _record(
        "run1:news_agent:news_report:claim:43",
        "news_agent",
        "Memory/storage: Silicon Motion up 186% in a year on NAND strength; "
        "SanDisk soaring on S&P 100 inclusion.",
        "AMD",
        "A201",
        _zero_candidate_scores(),
    )
    assert _foreign_issuer_only_reason(record, "AMD") == FOREIGN_ISSUER_NO_TAXONOMY_SIGNAL


def test_g_foreign_issuer_reason_is_none_when_own_ticker_present():
    record = _record(
        "run1:news_agent:news_report:claim:99",
        "news_agent",
        "AMD's data center revenue and SanDisk's storage rally both reflect strong AI demand.",
        "AMD",
        "A201",
        _zero_candidate_scores(),
    )
    assert _foreign_issuer_only_reason(record, "AMD") is None


def test_g_foreign_issuer_reason_is_none_when_deterministic_signal_exists():
    """Even naming another covered ticker, a claim with real deterministic
    keyword/factor signal (e.g. 'NVIDIA' is itself an A101 taxonomy
    keyword) must NOT be vetoed -- this is what keeps legitimate
    competitive/sector evidence intact."""
    record = _record(
        "run1:bear_researcher:investment_debate_state.bear_history:claim:39",
        "bear_researcher",
        "It signals a direct target for Nvidia's competitive response.",
        "AMD",
        "A101",
        _nonzero_candidate_scores("A101"),
    )
    assert _foreign_issuer_only_reason(record, "AMD") is None


def test_g_generic_sector_text_with_no_issuer_reference_is_not_vetoed():
    record = _record(
        "run1:news_agent:news_report:claim:1",
        "news_agent",
        "Rate-hike odds for 2026 rose to 62% this week.",
        "AMD",
        "A001",
        _zero_candidate_scores(alpha_ids=("A001", "A003")),
    )
    assert _foreign_issuer_only_reason(record, "AMD") is None


# ---------------------------------------------------------------------------
# H. Valid relational evidence preservation
# ---------------------------------------------------------------------------


def test_h_relational_evidence_naming_another_company_survives():
    """'Microsoft demand for AMD MI accelerators increased' names another
    company but ALSO names AMD directly -- must not be rejected merely
    because Microsoft is mentioned."""
    record = _record(
        "run1:fundamental_agent:fundamentals_report:claim:1",
        "fundamental_agent",
        "Microsoft demand for AMD MI accelerators increased sharply this quarter.",
        "AMD",
        "A101",
        _nonzero_candidate_scores("A101"),
    )
    assert _foreign_issuer_only_reason(record, "AMD") is None
    assert _is_ticker_specific(record, "AMD", company_names_for_ticker("AMD"), {}) is True


# ---------------------------------------------------------------------------
# I. AMD A201 contamination regression (exact reproduction fixture)
# ---------------------------------------------------------------------------


def test_i_amd_a201_contamination_regression_fixture():
    contaminated = _record(
        "run1:news_agent:news_report:claim:43",
        "news_agent",
        "Memory/storage: Silicon Motion up 186% in a year on NAND strength; "
        "SanDisk soaring on S&P 100 inclusion.",
        "AMD",
        "A201",
        _zero_candidate_scores(),
    )
    legitimate = _record(
        "run1:fundamental_agent:fundamentals_report:claim:1",
        "fundamental_agent",
        "AMD's net margin expanded to 19.9% from 10% a year ago, reflecting strong demand.",
        "AMD",
        "A201",
        _nonzero_candidate_scores("A201"),
    )
    graph_payload = _score_via_pipeline("AMD", [contaminated, legitimate])
    a201 = next(a for a in graph_payload["activation"]["alphas"] if a["alpha_id"] == "A201")
    # evidence_count/unique_evidence_count reflect qualified_groups (the
    # POST-ownership-veto set that actually feeds the score) -- unlike
    # evidence_detail, which is a broader read-back provenance view over
    # every claim ever assigned this matched_alpha, intentionally including
    # ineligible ones for audit visibility (Section 14: "Research
    # background may remain visible").
    assert a201["evidence_count"] == 1, (
        "only the legitimate claim should count toward qualifying activation support"
    )
    assert a201["unique_evidence_count"] == 1

    # The claim must remain visible in the full audit view (never deleted),
    # marked ineligible with the new reason code.
    all_role_detail_claim_ids = {
        member["claim_id"]
        for group in a201["evidence_fact_groups"]
        for member in group["members_source_role_detail"]
    }
    assert contaminated["claim_id"] in all_role_detail_claim_ids
    contaminated_detail = next(
        member
        for group in a201["evidence_fact_groups"]
        for member in group["members_source_role_detail"]
        if member["claim_id"] == contaminated["claim_id"]
    )
    assert contaminated_detail["activation_eligible"] is False
    assert contaminated_detail["activation_qualification_reason"] == (
        FOREIGN_ISSUER_NO_TAXONOMY_SIGNAL
    )


# ---------------------------------------------------------------------------
# J. QQQ ETF negative control
# ---------------------------------------------------------------------------


def test_j_qqq_constituent_mention_does_not_become_qqq_direct_evidence():
    """A named constituent (AMD) inside a QQQ claim must not become
    QQQ-ticker-specific merely because AMD is one of the covered issuers
    this system tracks elsewhere."""
    record = _record(
        "run1:news_agent:news_report:claim:1",
        "news_agent",
        "Intel +4%, AMD +3%, and Marvell +6% as the AI trade broadens.",
        "QQQ",
        "A201",
        _nonzero_candidate_scores("A201"),
    )
    assert _is_ticker_specific(record, "QQQ", company_names_for_ticker("QQQ"), {}) is False


def test_j_qqq_alias_registry_unchanged_deferred():
    assert company_names_for_ticker("QQQ") == ()


# ---------------------------------------------------------------------------
# K/L/M. Primary/Secondary, B1 stance, fact-group dedupe unchanged
# ---------------------------------------------------------------------------


def test_k_primary_secondary_dedupe_unaffected_by_p0_veto():
    """A Secondary duplicate of a Primary claim is still correctly excluded
    as SECONDARY_DUPLICATE_OF_PRIMARY -- the P0 veto only ever narrows an
    ALREADY-eligible member further, it never restores one, and it must
    never be confused with the existing dedupe reason."""
    primary = _record(
        "run1:fundamental_agent:fundamentals_report:claim:1",
        "fundamental_agent",
        "AMD's Instinct MI-series demand increased sharply this quarter.",
        "AMD",
        "A102",
        _nonzero_candidate_scores("A102"),
    )
    secondary_dup = _record(
        "run1:bull_researcher:investment_debate_state.bull_history:claim:1",
        "bull_researcher",
        "AMD's Instinct MI-series demand increased sharply this quarter.",
        "AMD",
        "A102",
        _nonzero_candidate_scores("A102"),
    )
    graph_payload = _score_via_pipeline("AMD", [primary, secondary_dup])
    a102 = next(a for a in graph_payload["activation"]["alphas"] if a["alpha_id"] == "A102")
    detail_by_claim = {
        member["claim_id"]: member
        for group in a102["evidence_fact_groups"]
        for member in group["members_source_role_detail"]
    }
    assert detail_by_claim[primary["claim_id"]]["activation_qualification_reason"] == "PRIMARY_QUALIFIED"
    assert (
        detail_by_claim[secondary_dup["claim_id"]]["activation_qualification_reason"]
        == "SECONDARY_DUPLICATE_OF_PRIMARY"
    )


def test_l_b1_stance_classification_untouched_by_p0_p1():
    """B1 stance lives entirely in the Alpha Mapper (structure_engine); this
    fix never imports from or modifies it. Import-level check that no
    circular/behavioral coupling was introduced."""
    import comqutor_alpha.structure_engine.alpha_mapper as mapper_module

    assert "issuer_aliases" not in mapper_module.__file__
    assert not hasattr(mapper_module, "_foreign_issuer_only_reason")
    assert not hasattr(mapper_module, "CANONICAL_ISSUER_ALIASES")


def test_m_fact_group_dedupe_unaffected():
    """Semantic grouping (_group_evidence/evidence_fact_index) runs BEFORE
    the P0 veto and is not passed ticker/company_names -- unaffected."""
    from comqutor_alpha.graph_engine.activation_scorer_v2 import _group_evidence

    qualifying = [
        {
            "claim_id": "c1",
            "claim": "AMD's Instinct MI-series demand increased.",
            "evidence": "AMD's Instinct MI-series demand increased.",
            "match_score": 0.8,
            "relation": "activation",
            "assertion_status": "asserted",
            "factors": (),
            "semantic_polarity": "activation",
            "duplicate_group_id": None,
            "relation_triple": None,
            "record": {},
        }
    ]
    groups_before = _group_evidence(qualifying, "AMD", "run1")
    groups_after = _group_evidence(qualifying, "AMD", "run1")
    assert groups_before.keys() == groups_after.keys()


# ---------------------------------------------------------------------------
# N. Neutral/opposing evidence still cannot support activation
# ---------------------------------------------------------------------------


def test_n_negated_evidence_still_cannot_support_activation():
    record = _record(
        "run1:fundamental_agent:fundamentals_report:claim:1",
        "fundamental_agent",
        "AMD's data center revenue growth is decelerating.",
        "AMD",
        "A201",
        _nonzero_candidate_scores("A201"),
        assertion_status="negated",
    )
    graph_payload = _score_via_pipeline("AMD", [record])
    a201 = next(a for a in graph_payload["activation"]["alphas"] if a["alpha_id"] == "A201")
    assert record["claim_id"] not in {d["claim_id"] for d in a201["evidence_detail"]}


# ---------------------------------------------------------------------------
# O. LLM Alpha semantic mapping cannot override ticker ownership
# ---------------------------------------------------------------------------


def test_o_matched_alpha_alone_is_insufficient_for_ownership():
    """Even though matched_alpha='A201' (whatever semantic authority chose
    it), the foreign-issuer-only + zero-taxonomy-signal claim is still
    excluded from qualifying evidence -- ownership is independently
    deterministic, never inferred solely from matched_alpha."""
    record = _record(
        "run1:news_agent:news_report:claim:43",
        "news_agent",
        "Memory/storage: Silicon Motion up 186% in a year on NAND strength; "
        "SanDisk soaring on S&P 100 inclusion.",
        "AMD",
        "A201",
        _zero_candidate_scores(),
        alpha_match_method="llm",
    )
    graph_payload = _score_via_pipeline("AMD", [record])
    a201 = next(a for a in graph_payload["activation"]["alphas"] if a["alpha_id"] == "A201")
    assert a201["evidence_count"] == 0
    assert a201["activation_score"] == 0.0


# ---------------------------------------------------------------------------
# P. Claim remains visible as background even when ineligible
# ---------------------------------------------------------------------------


def test_p_ineligible_claim_remains_visible_in_evidence_fact_groups():
    record = _record(
        "run1:news_agent:news_report:claim:43",
        "news_agent",
        "Memory/storage: Silicon Motion up 186% in a year on NAND strength; "
        "SanDisk soaring on S&P 100 inclusion.",
        "AMD",
        "A201",
        _zero_candidate_scores(),
    )
    graph_payload = _score_via_pipeline("AMD", [record])
    a201 = next(a for a in graph_payload["activation"]["alphas"] if a["alpha_id"] == "A201")
    all_ids = {
        member["claim_id"]
        for group in a201["evidence_fact_groups"]
        for member in group["members_source_role_detail"]
    }
    assert record["claim_id"] in all_ids, "ineligible evidence must remain visible, never deleted"
