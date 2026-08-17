from __future__ import annotations

from conftest import bundle_for, claim_for

from comqutor_alpha.structure_engine.structured_output_shadow_review import (
    compare_legacy_and_shadow,
)


def test_comparison_emits_signals_not_gold_labels(report):
    legacy = [
        {
            "claim_id": "legacy-1",
            "claim": "GPU demand increased in June.",
            "evidence": "GPU demand increased in June.",
            "entities": ["GPU"],
            "factors": ["GPU Demand"],
            "direction": "positive",
        }
    ]
    shadow = bundle_for(
        report,
        claims=[
            claim_for(
                report,
                "GPU demand increased in June.",
                candidate_ids=["candidate-1"],
                entities=["GPU"],
                factors=["GPU Demand"],
                direction="positive",
            )
        ],
    )
    comparison = compare_legacy_and_shadow(legacy, shadow)
    assert comparison["classification"] == "comparison_signals_and_diagnostic_candidates_only"
    assert comparison["semantic_quality_judgment"] is False
    assert comparison["gold_labels"] is False
    assert comparison["exact_text_overlaps"][0]["legacy_record_id"] == "legacy-1"


def test_lineage_flags_merge_and_split_candidates():
    report = "GPU demand rose. Revenue grew."
    claims = [
        claim_for(
            report,
            "GPU demand rose.",
            claim="GPU demand rose.",
            candidate_ids=["c1", "c2"],
        ),
        claim_for(report, "Revenue grew.", candidate_ids=["c2"]),
    ]
    comparison = compare_legacy_and_shadow([], bundle_for(report, claims=claims))
    assert comparison["potential_legacy_over_merge"][0]["classification"] == "diagnostic_candidate"
    assert comparison["potential_legacy_over_split"][0]["candidate_segment_id"] == "c2"
    assert len(comparison["unmatched_shadow_claims"]) == 2


def test_no_fuzzy_similarity_judgment(report):
    legacy = [{"claim_id": "legacy", "claim": "Demand moved higher", "evidence": "Demand moved higher"}]
    shadow = bundle_for(report, claims=[claim_for(report, "GPU demand increased in June.")])
    comparison = compare_legacy_and_shadow(legacy, shadow)
    assert comparison["exact_text_overlaps"] == []
    assert comparison["unmatched_legacy_claims"] == ["legacy"]

