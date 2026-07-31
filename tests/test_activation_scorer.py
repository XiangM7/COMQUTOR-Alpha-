from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.graph_engine.activation_scorer import (
    ACTIVATION_WEIGHTS,
    compute_dominant_alphas,
    score_alpha,
    score_alpha_activations,
)
from comqutor_alpha.graph_engine.graph_schema import MVP_ALPHA_IDS, activation_status_band

TAXONOMY = load_alpha_taxonomy()


def _match(
    claim_id,
    agent,
    alpha_id,
    relation,
    *,
    status="matched",
    score=0.8,
    plausible=None,
    evidence=None,
    claim_quality="analytical",
    direction="positive",
):
    # These fixtures test the Activation *formula* (relation weighting,
    # agent agreement, recency, direction strength) in isolation, so every
    # synthetic claim is tagged as an already-quality-gated "analytical"
    # claim by default (Unified Claim Admissibility Sprint) -- tests that
    # specifically exercise context_only/non_substantive routing pass their
    # own claim_quality/direction override instead.
    record = {
        "claim_id": claim_id,
        "agent": agent,
        "match_status": status,
        "matched_alpha": alpha_id if status == "matched" else None,
        "matched_alpha_name": TAXONOMY[alpha_id].name_en if status == "matched" and alpha_id else None,
        "score": score,
        "evidence": evidence or f"evidence for {claim_id}",
        "claim": evidence or f"evidence for {claim_id}",
        "plausible_alphas": plausible if plausible is not None else ([alpha_id] if alpha_id else []),
        "eligible_candidates": [{"alpha_id": alpha_id, "relation": relation}] if alpha_id else [],
        "claim_quality": claim_quality,
        "direction": direction,
    }
    return record


def _payload(matches):
    return {"schema_version": "week2.alpha_matches.v2", "run_id": "r1", "ticker": "NVDA", "matches": matches}


def test_scores_exactly_the_mvp_ten_alphas():
    result = score_alpha_activations(_payload([]), graph_coherence_score=0.0)

    alpha_ids = {a["alpha_id"] for a in result["alphas"]}
    assert alpha_ids == MVP_ALPHA_IDS
    assert len(result["alphas"]) == 10


def test_every_score_is_in_0_to_100_range():
    matches = [_match("c1", "news_agent", "A101", "activation", score=1.0) for _ in range(1)]
    result = score_alpha_activations(_payload(matches), graph_coherence_score=100.0)

    for alpha in result["alphas"]:
        assert 0.0 <= alpha["activation_score"] <= 100.0


def test_component_breakdown_is_complete_and_auditable():
    matches = [_match("c1", "news_agent", "A101", "activation")]
    result = score_alpha_activations(_payload(matches), graph_coherence_score=50.0, run_timestamp="2026-06-30")

    a101 = next(a for a in result["alphas"] if a["alpha_id"] == "A101")
    assert set(a101["components"]) == {
        "matched_evidence",
        "agent_agreement",
        "graph_coherence",
        "direction_strength",
        "recency",
    }
    for name, component in a101["components"].items():
        assert component["weight"] == ACTIVATION_WEIGHTS[name]
        assert "raw" in component
        assert "contribution" in component
        assert component["contribution"] == round(component["raw"] * component["weight"], 4)
    total = sum(c["contribution"] for c in a101["components"].values())
    assert abs(total - a101["activation_score"]) < 1e-6
    assert "conflict_penalty" not in a101["components"]  # Week 4 scope, must not be simulated


def test_no_evidence_gives_inactive_score():
    result = score_alpha_activations(_payload([]), graph_coherence_score=0.0)

    for alpha in result["alphas"]:
        assert alpha["status"] == "inactive"
        assert "NO_EVIDENCE" in alpha["reason_codes"]


def test_duplicate_claim_rows_do_not_inflate_matched_evidence():
    single = [_match("c1", "news_agent", "A101", "activation", score=0.9)]
    duplicated = single + [dict(single[0])]  # same claim_id repeated

    single_result = score_alpha(
        "A101", _payload(single), TAXONOMY, graph_coherence_score=0.0, run_timestamp="2026-01-01", as_of="2026-01-01"
    )
    duplicated_result = score_alpha(
        "A101", _payload(duplicated), TAXONOMY, graph_coherence_score=0.0, run_timestamp="2026-01-01", as_of="2026-01-01"
    )

    assert single_result["activation_score"] == duplicated_result["activation_score"]
    assert duplicated_result["components"]["matched_evidence"]["unique_committed_claims"] == 1


def test_agent_agreement_counts_distinct_agents_not_raw_claims():
    same_agent_twice = [
        _match("c1", "news_agent", "A101", "activation"),
        _match("c2", "news_agent", "A101", "activation"),
    ]
    two_agents = [
        _match("c1", "news_agent", "A101", "activation"),
        _match("c2", "fundamental_agent", "A101", "activation"),
    ]

    same_agent_result = score_alpha("A101", _payload(same_agent_twice), TAXONOMY, graph_coherence_score=0.0)
    two_agent_result = score_alpha("A101", _payload(two_agents), TAXONOMY, graph_coherence_score=0.0)

    assert same_agent_result["components"]["agent_agreement"]["distinct_agents"] == 1
    assert two_agent_result["components"]["agent_agreement"]["distinct_agents"] == 2
    assert (
        two_agent_result["components"]["agent_agreement"]["raw"]
        > same_agent_result["components"]["agent_agreement"]["raw"]
    )


def test_agent_agreement_denominator_is_explicit_and_taxonomy_sourced():
    matches = [_match("c1", "news_agent", "A101", "activation")]
    result = score_alpha("A101", _payload(matches), TAXONOMY, graph_coherence_score=0.0)

    assert result["components"]["agent_agreement"]["denominator"] == len(TAXONOMY["A101"].agent_sources)
    assert result["components"]["agent_agreement"]["denominator_source"] == "taxonomy.agent_sources"


def test_missing_agent_field_does_not_crash_or_fabricate_agreement():
    matches = [_match("c1", None, "A101", "activation")]
    result = score_alpha("A101", _payload(matches), TAXONOMY, graph_coherence_score=0.0)

    assert result["components"]["agent_agreement"]["distinct_agents"] == 0
    assert result["components"]["agent_agreement"]["raw"] == 0.0


def test_recency_is_deterministic_given_explicit_timestamps():
    matches = [_match("c1", "news_agent", "A101", "activation")]
    first = score_alpha(
        "A101", _payload(matches), TAXONOMY, graph_coherence_score=0.0, run_timestamp="2026-01-01", as_of="2026-02-01"
    )
    second = score_alpha(
        "A101", _payload(matches), TAXONOMY, graph_coherence_score=0.0, run_timestamp="2026-01-01", as_of="2026-02-01"
    )

    assert first["components"]["recency"] == second["components"]["recency"]
    assert first["components"]["recency"]["age_days"] == 31


def test_recency_decays_with_age_and_never_exceeds_100_for_future_run_timestamp():
    matches = [_match("c1", "news_agent", "A101", "activation")]
    fresh = score_alpha(
        "A101", _payload(matches), TAXONOMY, graph_coherence_score=0.0, run_timestamp="2026-06-30", as_of="2026-06-30"
    )
    stale = score_alpha(
        "A101", _payload(matches), TAXONOMY, graph_coherence_score=0.0, run_timestamp="2026-01-01", as_of="2026-06-30"
    )
    future_run = score_alpha(
        "A101", _payload(matches), TAXONOMY, graph_coherence_score=0.0, run_timestamp="2026-12-31", as_of="2026-06-30"
    )

    assert fresh["components"]["recency"]["raw"] == 100.0
    assert stale["components"]["recency"]["raw"] < fresh["components"]["recency"]["raw"]
    assert future_run["components"]["recency"]["raw"] <= 100.0
    assert future_run["components"]["recency"]["age_days"] == 0


def test_recency_missing_timestamp_uses_documented_neutral_fallback():
    matches = [_match("c1", "news_agent", "A101", "activation")]
    result = score_alpha("A101", _payload(matches), TAXONOMY, graph_coherence_score=0.0, run_timestamp=None)

    assert result["components"]["recency"]["fallback"] is True
    assert result["components"]["recency"]["raw"] == 50.0


def test_scoring_is_order_invariant():
    matches = [
        _match("c1", "news_agent", "A101", "activation"),
        _match("c2", "fundamental_agent", "A101", "activation"),
    ]
    forward = score_alpha_activations(_payload(matches), graph_coherence_score=40.0, run_timestamp="2026-06-30")
    backward = score_alpha_activations(
        _payload(list(reversed(matches))), graph_coherence_score=40.0, run_timestamp="2026-06-30"
    )

    assert forward == backward


def test_risk_relief_does_not_activate_the_risk_alpha():
    baseline = score_alpha("A501", _payload([]), TAXONOMY, graph_coherence_score=20.0, run_timestamp="2026-06-30", as_of="2026-06-30")
    with_relief = score_alpha(
        "A501",
        _payload([_match("c1", "news_agent", "A501", "risk_relief")]),
        TAXONOMY,
        graph_coherence_score=20.0,
        run_timestamp="2026-06-30",
        as_of="2026-06-30",
    )

    assert with_relief["components"]["matched_evidence"]["raw"] == 0.0
    assert with_relief["activation_score"] <= baseline["activation_score"]
    assert with_relief["status"] == "inactive"
    assert "ONLY_COUNTER_EVIDENCE_PRESENT" in with_relief["reason_codes"]


def test_invalidation_does_not_strengthen_the_opportunity_alpha():
    activated = score_alpha(
        "A001", _payload([_match("c1", "news_agent", "A001", "activation")]), TAXONOMY, graph_coherence_score=0.0
    )
    invalidated = score_alpha(
        "A001", _payload([_match("c1", "news_agent", "A001", "invalidation")]), TAXONOMY, graph_coherence_score=0.0
    )

    assert invalidated["components"]["matched_evidence"]["raw"] == 0.0
    assert invalidated["activation_score"] < activated["activation_score"]
    assert invalidated["direction"] == "negative"


def test_ambiguous_evidence_contributes_conservatively_less_than_committed():
    committed = score_alpha(
        "A101", _payload([_match("c1", "news_agent", "A101", "activation", status="matched")]), TAXONOMY, graph_coherence_score=0.0
    )
    ambiguous = score_alpha(
        "A101",
        _payload([_match("c1", "news_agent", "A101", "activation", status="ambiguous", plausible=["A101", "A301"])]),
        TAXONOMY,
        graph_coherence_score=0.0,
    )

    assert ambiguous["components"]["matched_evidence"]["raw"] < committed["components"]["matched_evidence"]["raw"]
    assert ambiguous["components"]["matched_evidence"]["unique_committed_claims"] == 0
    assert ambiguous["components"]["matched_evidence"]["unique_ambiguous_claims"] == 1
    assert "AMBIGUOUS_EVIDENCE_ONLY" in ambiguous["reason_codes"]


def test_positive_opportunity_direction_is_reported_positive():
    result = score_alpha(
        "A101", _payload([_match("c1", "news_agent", "A101", "activation")]), TAXONOMY, graph_coherence_score=0.0
    )
    assert result["direction"] == "positive"


def test_activated_risk_alpha_direction_is_negative_even_though_it_is_the_alphas_own_activation():
    """A304/A501 'activating' is legitimately a bearish-for-the-stock signal;
    DirectionStrength measures alpha-thesis consistency, not raw market
    bullishness, so an activation-relation claim for a risk alpha must not be
    reported as 'positive' direction."""
    result = score_alpha(
        "A304", _payload([_match("c1", "fundamental_agent", "A304", "activation")]), TAXONOMY, graph_coherence_score=0.0
    )
    assert result["status"] != "inactive"
    assert result["direction"] == "negative"


def test_mixed_direction_evidence_pulls_toward_neutral_and_is_flagged():
    matches = [
        _match("c1", "news_agent", "A001", "activation"),
        _match("c2", "fundamental_agent", "A001", "invalidation"),
    ]
    result = score_alpha("A001", _payload(matches), TAXONOMY, graph_coherence_score=0.0)

    assert result["direction"] == "neutral"
    assert result["components"]["direction_strength"]["mixed_direction_evidence"] is True
    assert "MIXED_DIRECTION_EVIDENCE" in result["reason_codes"]


def test_stable_dominant_alphas_ordering_by_score_desc_then_alpha_id():
    alphas = [
        {"alpha_id": "A601", "activation_score": 90.0, "status": "regime_level", "direction": "positive", "evidence_count": 1, "distinct_supporting_agents": 1, "alpha_name": "x"},
        {"alpha_id": "A101", "activation_score": 90.0, "status": "regime_level", "direction": "positive", "evidence_count": 1, "distinct_supporting_agents": 1, "alpha_name": "x"},
        {"alpha_id": "A304", "activation_score": 75.0, "status": "dominant", "direction": "negative", "evidence_count": 1, "distinct_supporting_agents": 1, "alpha_name": "x"},
        {"alpha_id": "A501", "activation_score": 10.0, "status": "inactive", "direction": "unknown", "evidence_count": 0, "distinct_supporting_agents": 0, "alpha_name": "x"},
    ]

    dominant = compute_dominant_alphas(alphas)

    assert [d["alpha_id"] for d in dominant] == ["A101", "A601", "A304"]  # tie broken by alpha_id


def test_dominant_alphas_empty_when_no_alpha_reaches_the_band():
    result = score_alpha_activations(_payload([]), graph_coherence_score=0.0)
    assert result["dominant_alphas"] == []


def test_unsupported_alpha_stays_exactly_inactive_on_a_highly_coherent_recent_graph():
    """Evidence-gating policy: GraphCoherence(25%) is deliberately reused
    globally (documented policy) and Recency(10%) is run-level, not
    per-alpha -- so without gating, a completely unsupported (zero
    admissible evidence) alpha could still pick up a nonzero floor purely
    from ambient run quality (0.25*100 + 0.10*100 = 35, 'watch' band) even
    though nothing about it was actually evidenced. The gate forces such an
    alpha to activation_score == 0 / status == inactive / direction ==
    "unknown" (the documented no-evidence value), on a graph that is
    maximally coherent (100) and maximally recent (as_of == run_timestamp)
    -- the worst case for this gate. Every other alpha in the same run has
    real evidence for comparison, so this is not just an all-zero payload."""
    matches = [_match("c1", "news_agent", "A101", "activation", score=0.9)]
    result = score_alpha_activations(
        _payload(matches), graph_coherence_score=100.0, run_timestamp="2026-06-30", as_of="2026-06-30"
    )

    evidenced = next(a for a in result["alphas"] if a["alpha_id"] == "A101")
    assert evidenced["activation_score"] > 0  # sanity: the gate does not zero out real evidence

    for alpha in result["alphas"]:
        if alpha["alpha_id"] == "A101":
            continue
        assert alpha["activation_score"] == 0.0, alpha
        assert alpha["status"] == "inactive", alpha
        assert alpha["direction"] == "unknown", alpha
        assert alpha["components"]["graph_coherence"]["evidence_gated"] is True
        assert alpha["components"]["graph_coherence"]["contribution"] == 0.0
        assert alpha["components"]["graph_coherence"]["raw"] == 100.0  # ambient value stays visible
        assert alpha["components"]["recency"]["evidence_gated"] is True
        assert alpha["components"]["recency"]["contribution"] == 0.0

    assert result["dominant_alphas"] == [] or all(
        d["alpha_id"] == "A101" for d in result["dominant_alphas"]
    )  # unsupported alphas are never dominant


def test_only_counter_evidence_is_gated_identically_to_true_zero_evidence():
    """risk_relief/invalidation-only evidence contributes zero to
    MatchedEvidence by design (it is not support for the alpha), so it must
    not out-score true absence of evidence either -- both are "completely
    unsupported" for gating purposes."""
    baseline = score_alpha(
        "A501", _payload([]), TAXONOMY, graph_coherence_score=60.0, run_timestamp="2026-06-30", as_of="2026-06-30"
    )
    only_relief = score_alpha(
        "A501",
        _payload([_match("c1", "news_agent", "A501", "risk_relief")]),
        TAXONOMY,
        graph_coherence_score=60.0,
        run_timestamp="2026-06-30",
        as_of="2026-06-30",
    )

    assert baseline["activation_score"] == 0.0
    assert only_relief["activation_score"] == 0.0
    assert only_relief["status"] == "inactive"


class TestStatusBandBoundaries:
    def test_boundaries(self):
        expected = [
            (0, "inactive"),
            (30, "inactive"),
            (30.1, "watch"),
            (31, "watch"),
            (50, "watch"),
            (50.1, "active"),
            (51, "active"),
            (70, "active"),
            (70.1, "dominant"),
            (71, "dominant"),
            (85, "dominant"),
            (85.1, "regime_level"),
            (86, "regime_level"),
            (100, "regime_level"),
        ]
        for score, status in expected:
            assert activation_status_band(score) == status, score

    def test_out_of_range_scores_are_clamped_not_rejected(self):
        assert activation_status_band(-10) == "inactive"
        assert activation_status_band(150) == "regime_level"
