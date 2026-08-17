"""A3 Unclassified Findings Control -- dedicated tests (task
A3_UNCLASSIFIED_FINDINGS_CONTROL).

Presentation/audit control layer only, layered on top of already-computed
upstream authorities:

    B1 = Alpha-relative Evidence Stance (final stance, semantic authority)
    B2 = deterministic Conflict Evidence Admissibility
    Activation v2 = Evidence Fact Index grouping, ticker-specificity
    A3 = this task -- never re-judges Alpha mapping, never re-classifies
         Evidence Stance, never re-groups Evidence Facts, never calls a
         Provider/LLM. It only joins existing artifacts, assigns one of
         John's 5 canonical reasons (or the honest UNRESOLVED escape
         hatch), and computes a deterministic Top-20 display order.

Every test drives the real, unmodified public entry point
(``build_unclassified_findings_export``) directly against hand-built
alpha_matches.json/evidence_facts.json payloads and a real
structured_agent_outputs.json written to a temp run directory -- never a
second/simplified reimplementation of the reason logic.

Section map:
    A - Universe definition (direction-neutral vs unclassified, B1 stance
        vs A3 reason, no-match retention, no duplication of classified
        claims)
    B - Canonical reasons (all 5, frozen priority order, UNRESOLVED escape
        hatch, vocabulary closure)
    C - Deduplication reuse (Evidence Fact Index only, never a new dedup
        pass, never conflating structured-level duplicate_group_id with
        Evidence Fact representative status)
    D - Top-20 deterministic ordering and count behavior
    E - Full audit (download) vs UI Top-20 subset
    F - Artifact/manifest/run_audit/API consistency
    G - Upstream invariants (no mutation of inputs) + Provider calls = 0
"""

from __future__ import annotations

import copy
import json

import pytest

from comqutor_alpha.api.artifact_export import (
    PRODUCT_EXTENSION_ARTIFACT_FILENAMES,
    REQUIRED_ARTIFACT_FILENAMES,
    build_and_write_artifact_manifest,
)
from comqutor_alpha.api.routes_research import (
    build_research_response,
    build_run_audit_payload,
    get_run_artifact_file,
)
from comqutor_alpha.api.unclassified_findings import (
    ARTIFACT_FILENAME,
    CANONICAL_REASONS,
    DEFAULT_DISPLAY_LIMIT,
    LOW_CONFIDENCE_THRESHOLD_NOT_FORMALLY_DEFINED,
    REASON_DUPLICATE_SUPPORTING_TEXT,
    REASON_GENERIC_BACKGROUND,
    REASON_LOW_CONFIDENCE,
    REASON_NO_ALPHA_MATCH,
    REASON_NO_TICKER_SPECIFIC_EVIDENCE,
    REASON_PRIORITY,
    REASON_UNRESOLVED,
    SCHEMA_VERSION,
    build_unclassified_findings_export,
)
from comqutor_alpha.storage.file_store import save_json_record

RUN_ID = "run_a3"
TICKER = "NVDA"


# ---------------------------------------------------------------------------
# Fixture builders -- minimal, real-schema-shaped records (field names/shapes
# confirmed against the actual alpha_matches.json/evidence_facts.json/
# structured_agent_outputs.json produced by the real pipeline, not guessed).
# ---------------------------------------------------------------------------


def _structured_record(claim_id: str, **overrides) -> dict:
    record = {
        "claim_id": claim_id,
        "source_agent_output_id": f"{claim_id}:src",
        "run_id": RUN_ID,
        "ticker": TICKER,
        "agent": "market_agent",
        "claim": "Placeholder claim text.",
        "evidence": "Placeholder claim text.",
        "entities": [TICKER],
        "factors": [],
        "direction": "unknown",
        "confidence": 0.5,
        "claim_index": 0,
        "source_refs": [f"{claim_id}:src"],
        "duplicate_group_id": None,
    }
    record.update(overrides)
    return record


def _match_record(claim_id: str, **overrides) -> dict:
    record = {
        "run_id": RUN_ID,
        "ticker": TICKER,
        "agent": "market_agent",
        "claim_id": claim_id,
        "source_agent_output_id": f"{claim_id}:src",
        "claim": "Placeholder claim text.",
        "evidence": "Placeholder claim text.",
        "direction": "unknown",
        "matched_alpha": None,
        "matched_alpha_name": None,
        "secondary_alphas": [],
        "match_status": "no_match",
        "reason": None,
        "candidate_scores": [],
        "matched_evidence_stance": None,
        "matched_stance_confidence_band": None,
        "matched_stance_reason_codes": [],
        "matched_counter_alpha_id": None,
    }
    record.update(overrides)
    return record


def _fact_group(group_id: str, representative_claim_id: str, member_claim_ids: list[str], supporting_alpha_ids: list[str]) -> dict:
    return {
        "evidence_fact_group_id": group_id,
        "representative_claim_id": representative_claim_id,
        "member_claim_ids": member_claim_ids,
        "supporting_alpha_ids": supporting_alpha_ids,
    }


def _build(tmp_path, matches, structured=None, groups=None, ticker=TICKER, run_id=RUN_ID, persist=True):
    structured = structured if structured is not None else [_structured_record(m["claim_id"]) for m in matches]
    save_json_record(run_id, "structured_agent_outputs.json", {"records": structured}, output_root=tmp_path)
    result = build_unclassified_findings_export(
        run_id=run_id,
        ticker=ticker,
        output_root=tmp_path,
        alpha_matches_payload={"matches": matches},
        evidence_facts_payload={"groups": groups or []},
    )
    if persist:
        # Mirrors artifact_export.finalize_completed_run_artifacts's own
        # write-back -- build_unclassified_findings_export itself is a pure
        # in-memory builder (matching precedent), the caller persists it.
        save_json_record(run_id, ARTIFACT_FILENAME, result, output_root=tmp_path)
    return result


def _finding_for(result: dict, claim_id: str) -> dict | None:
    for finding in result["findings"]:
        if finding["claim_id"] == claim_id:
            return finding
    return None


# ---------------------------------------------------------------------------
# Section A -- universe definition
# ---------------------------------------------------------------------------


class TestSectionAUniverseDefinition:
    def test_a1_direction_neutral_valid_match_ticker_specific_claim_is_fully_classified(self, tmp_path):
        matches = [
            _match_record(
                "c1",
                claim="NVDA reported a durable revenue base this quarter.",
                evidence="NVDA reported a durable revenue base this quarter.",
                direction="neutral",
                matched_alpha="A304",
                matched_evidence_stance="supports_alpha",
            )
        ]
        result = _build(tmp_path, matches)
        assert _finding_for(result, "c1") is None
        assert result["total_count"] == 0

    def test_a2_direction_never_drives_universe_membership(self, tmp_path):
        base = {
            "claim": "NVDA reported a durable revenue base this quarter.",
            "evidence": "NVDA reported a durable revenue base this quarter.",
            "matched_alpha": "A304",
            "matched_evidence_stance": "supports_alpha",
        }
        for direction in ("positive", "negative", "neutral", "unknown"):
            matches = [_match_record("c1", direction=direction, **base)]
            result = _build(tmp_path, matches)
            assert _finding_for(result, "c1") is None, f"direction={direction} wrongly treated as unclassified"

    def test_a3_b1_neutral_background_stance_is_not_the_same_as_claim_direction(self, tmp_path):
        # direction is "positive" (claim-level), but the Alpha-relative B1
        # stance is neutral_background -- the stance, not the direction,
        # drives generic_background.
        matches = [
            _match_record(
                "c1",
                claim="NVDA is mentioned in passing.",
                evidence="NVDA is mentioned in passing.",
                direction="positive",
                matched_alpha="A304",
                matched_evidence_stance="neutral_background",
            )
        ]
        result = _build(tmp_path, matches)
        finding = _finding_for(result, "c1")
        assert finding is not None
        assert finding["reason"] == REASON_GENERIC_BACKGROUND

    def test_a4_mentions_alpha_preserves_target_alpha_identity_and_is_not_supporting(self, tmp_path):
        matches = [
            _match_record(
                "c1",
                claim="NVDA was referenced by an analyst without further detail.",
                evidence="NVDA was referenced by an analyst without further detail.",
                matched_alpha="A304",
                matched_evidence_stance="mentions_alpha",
            )
        ]
        result = _build(tmp_path, matches)
        finding = _finding_for(result, "c1")
        assert finding is not None
        assert finding["reason"] == REASON_GENERIC_BACKGROUND
        assert finding["matched_alpha"] == "A304"  # target identity never lost
        assert "mentions_alpha" in finding["diagnostic_reason_codes"]

    def test_a5_no_match_claims_are_retained_never_dropped(self, tmp_path):
        matches = [_match_record("c1", matched_alpha=None, match_status="no_match")]
        result = _build(tmp_path, matches)
        finding = _finding_for(result, "c1")
        assert finding is not None
        assert finding["matched_alpha"] is None
        assert finding["reason"] == REASON_NO_ALPHA_MATCH

    def test_a6_classified_findings_never_appear_in_the_unclassified_list(self, tmp_path):
        matches = [
            _match_record(
                "c1",
                claim="NVDA guidance improved materially this quarter.",
                evidence="NVDA guidance improved materially this quarter.",
                matched_alpha="A304",
                matched_evidence_stance="supports_alpha",
            ),
            _match_record("c2", matched_alpha=None),
        ]
        result = _build(tmp_path, matches)
        claim_ids = [f["claim_id"] for f in result["findings"]]
        assert "c1" not in claim_ids
        assert claim_ids.count("c2") == 1
        assert result["total_count"] == 1

    def test_a7_mentions_alpha_never_counted_toward_a_supporting_reason_code(self, tmp_path):
        matches = [
            _match_record(
                "c1",
                claim="NVDA mentioned as background context only.",
                evidence="NVDA mentioned as background context only.",
                matched_alpha="A304",
                matched_evidence_stance="mentions_alpha",
            )
        ]
        result = _build(tmp_path, matches)
        finding = _finding_for(result, "c1")
        assert set(finding["reason_codes"]) <= CANONICAL_REASONS


# ---------------------------------------------------------------------------
# Section B -- canonical reasons
# ---------------------------------------------------------------------------


class TestSectionBCanonicalReasons:
    def test_b1_no_alpha_match_fires_on_null_matched_alpha(self, tmp_path):
        result = _build(tmp_path, [_match_record("c1", matched_alpha=None)])
        assert _finding_for(result, "c1")["reason"] == REASON_NO_ALPHA_MATCH

    def test_b2_generic_background_fires_on_neutral_background_stance(self, tmp_path):
        matches = [
            _match_record(
                "c1",
                claim="NVDA context only.",
                evidence="NVDA context only.",
                matched_alpha="A304",
                matched_evidence_stance="neutral_background",
            )
        ]
        result = _build(tmp_path, matches)
        assert _finding_for(result, "c1")["reason"] == REASON_GENERIC_BACKGROUND

    def test_b3_generic_background_fires_on_mentions_alpha_stance(self, tmp_path):
        matches = [
            _match_record(
                "c1",
                claim="NVDA mention only.",
                evidence="NVDA mention only.",
                matched_alpha="A304",
                matched_evidence_stance="mentions_alpha",
            )
        ]
        result = _build(tmp_path, matches)
        assert _finding_for(result, "c1")["reason"] == REASON_GENERIC_BACKGROUND

    def test_b4_no_ticker_specific_evidence_fires_when_ticker_never_named(self, tmp_path):
        matches = [
            _match_record(
                "c1",
                claim="The broader semiconductor sector saw strong momentum.",
                evidence="The broader semiconductor sector saw strong momentum.",
                matched_alpha="A601",
                matched_evidence_stance="supports_alpha",
            )
        ]
        result = _build(tmp_path, matches)
        finding = _finding_for(result, "c1")
        assert finding["reason"] == REASON_NO_TICKER_SPECIFIC_EVIDENCE
        assert finding["ticker_specific"] is False

    def test_b5_duplicate_supporting_text_fires_for_non_representative_member(self, tmp_path):
        matches = [
            _match_record(
                "c1",
                claim="NVDA data center revenue accelerated.",
                evidence="NVDA data center revenue accelerated.",
                matched_alpha="A304",
                matched_evidence_stance="supports_alpha",
            ),
            _match_record(
                "c2",
                claim="NVDA data center revenue accelerated.",
                evidence="NVDA data center revenue accelerated.",
                matched_alpha="A304",
                matched_evidence_stance="supports_alpha",
            ),
        ]
        groups = [_fact_group("g1", "c1", ["c1", "c2"], ["A304"])]
        result = _build(tmp_path, matches, groups=groups)
        assert _finding_for(result, "c1") is None  # representative: classified
        dup = _finding_for(result, "c2")
        assert dup["reason"] == REASON_DUPLICATE_SUPPORTING_TEXT
        assert dup["representative_claim_id"] == "c1"

    def test_b6_low_confidence_never_fires_regardless_of_confidence_value(self, tmp_path):
        structured = [_structured_record("c1", confidence=0.01)]
        matches = [_match_record("c1", matched_alpha=None)]
        result = _build(tmp_path, matches, structured=structured)
        finding = _finding_for(result, "c1")
        assert REASON_LOW_CONFIDENCE not in finding["reason_codes"]
        assert result["reason_counts"][REASON_LOW_CONFIDENCE] == 0
        assert result["low_confidence_signal_status"] == LOW_CONFIDENCE_THRESHOLD_NOT_FORMALLY_DEFINED

    def test_b7_vocabulary_is_restricted_to_exactly_johns_five_reasons(self, tmp_path):
        matches = [
            _match_record("c1", matched_alpha=None),
            _match_record(
                "c2",
                claim="NVDA background only.",
                evidence="NVDA background only.",
                matched_alpha="A304",
                matched_evidence_stance="neutral_background",
            ),
            _match_record(
                "c3",
                claim="Sector-wide momentum, no ticker named.",
                evidence="Sector-wide momentum, no ticker named.",
                matched_alpha="A601",
                matched_evidence_stance="supports_alpha",
            ),
        ]
        result = _build(tmp_path, matches)
        for finding in result["findings"]:
            assert finding["reason"] in CANONICAL_REASONS or finding["reason"] == REASON_UNRESOLVED
            for code in finding["reason_codes"]:
                assert code in CANONICAL_REASONS or code == REASON_UNRESOLVED
        assert set(result["reason_counts"].keys()) == set(REASON_PRIORITY)

    def test_b8_exactly_one_primary_reason_per_finding(self, tmp_path):
        matches = [
            _match_record(
                "c1",
                claim="NVDA background only, off-ticker phrasing elsewhere.",
                evidence="NVDA background only, off-ticker phrasing elsewhere.",
                matched_alpha="A304",
                matched_evidence_stance="neutral_background",
            )
        ]
        result = _build(tmp_path, matches)
        finding = _finding_for(result, "c1")
        assert isinstance(finding["reason"], str)

    def test_b9_multi_reason_primary_follows_frozen_priority_all_codes_preserved(self, tmp_path):
        # duplicate + generic_background + no_ticker_specific_evidence all
        # apply at once; duplicate_supporting_text must win as primary.
        matches = [
            _match_record(
                "c1",
                claim="Sector background chatter, no ticker named.",
                evidence="Sector background chatter, no ticker named.",
                matched_alpha="A601",
                matched_evidence_stance="neutral_background",
            ),
            _match_record(
                "c2",
                claim="Sector background chatter, no ticker named.",
                evidence="Sector background chatter, no ticker named.",
                matched_alpha="A601",
                matched_evidence_stance="neutral_background",
            ),
        ]
        groups = [_fact_group("g1", "c1", ["c1", "c2"], ["A601"])]
        result = _build(tmp_path, matches, groups=groups)
        finding = _finding_for(result, "c2")
        assert finding["reason"] == REASON_DUPLICATE_SUPPORTING_TEXT
        assert set(finding["reason_codes"]) == {
            REASON_DUPLICATE_SUPPORTING_TEXT,
            REASON_GENERIC_BACKGROUND,
            REASON_NO_TICKER_SPECIFIC_EVIDENCE,
        }

    def test_b10_priority_order_is_frozen(self):
        assert REASON_PRIORITY == (
            REASON_DUPLICATE_SUPPORTING_TEXT,
            REASON_GENERIC_BACKGROUND,
            REASON_LOW_CONFIDENCE,
            REASON_NO_ALPHA_MATCH,
            REASON_NO_TICKER_SPECIFIC_EVIDENCE,
        )

    def test_b11_unresolved_escape_hatch_fires_honestly_for_a_genuine_anomaly(self, tmp_path):
        # matched_alpha present, but no legitimate Evidence Stance was ever
        # attached (data anomaly) -- never guessed into one of the five.
        matches = [
            _match_record(
                "c1",
                claim="NVDA anomalous record with no attached stance.",
                evidence="NVDA anomalous record with no attached stance.",
                matched_alpha="A304",
                matched_evidence_stance=None,
            )
        ]
        result = _build(tmp_path, matches)
        finding = _finding_for(result, "c1")
        assert finding["reason"] == REASON_UNRESOLVED
        assert finding["reason_codes"] == [REASON_UNRESOLVED]
        assert result["unresolved_reason_count"] == 1

    def test_b12_unresolved_never_shadows_a_genuinely_classified_finding(self, tmp_path):
        matches = [
            _match_record(
                "c1",
                claim="NVDA delivered a clean supporting data point.",
                evidence="NVDA delivered a clean supporting data point.",
                matched_alpha="A304",
                matched_evidence_stance="supports_alpha",
            )
        ]
        result = _build(tmp_path, matches)
        assert _finding_for(result, "c1") is None
        assert result["unresolved_reason_count"] == 0


# ---------------------------------------------------------------------------
# Section C -- deduplication reuse
# ---------------------------------------------------------------------------


class TestSectionCDeduplicationReuse:
    def test_c1_representative_claim_never_flagged_as_its_own_duplicate(self, tmp_path):
        matches = [
            _match_record("c1", matched_alpha=None),
            _match_record("c2", matched_alpha=None),
        ]
        groups = [_fact_group("g1", "c1", ["c1", "c2"], ["A304"])]
        # Both have no matched_alpha here, so neither is alpha-scoped into
        # the group; use a case where c1 *is* matched to A304 to exercise
        # representative exclusion specifically.
        matches = [
            _match_record(
                "c1",
                claim="NVDA capex plans accelerated.",
                evidence="NVDA capex plans accelerated.",
                matched_alpha="A304",
                matched_evidence_stance="supports_alpha",
            ),
            _match_record(
                "c2",
                claim="NVDA capex plans accelerated.",
                evidence="NVDA capex plans accelerated.",
                matched_alpha="A304",
                matched_evidence_stance="supports_alpha",
            ),
        ]
        result = _build(tmp_path, matches, groups=groups)
        assert _finding_for(result, "c1") is None

    def test_c2_non_representative_member_carries_full_group_provenance(self, tmp_path):
        matches = [
            _match_record(
                "c1",
                claim="NVDA capex plans accelerated.",
                evidence="NVDA capex plans accelerated.",
                matched_alpha="A304",
                matched_evidence_stance="supports_alpha",
            ),
            _match_record(
                "c2",
                claim="NVDA capex plans accelerated.",
                evidence="NVDA capex plans accelerated.",
                matched_alpha="A304",
                matched_evidence_stance="supports_alpha",
            ),
        ]
        groups = [_fact_group("g1", "c1", ["c1", "c2"], ["A304"])]
        result = _build(tmp_path, matches, groups=groups)
        dup = _finding_for(result, "c2")
        assert dup["evidence_fact_group_id"] == "g1"
        assert dup["representative_claim_id"] == "c1"

    def test_c3_structured_level_duplicate_group_id_alone_never_drives_the_reason(self, tmp_path):
        # Two claims share a structured-level duplicate_group_id but are
        # NOT part of any Evidence Fact group -- must not be flagged.
        structured = [
            _structured_record("c1", duplicate_group_id="dupgroup_x"),
            _structured_record("c2", duplicate_group_id="dupgroup_x"),
        ]
        matches = [
            _match_record(
                "c1",
                claim="NVDA capex plans accelerated.",
                evidence="NVDA capex plans accelerated.",
                matched_alpha="A304",
                matched_evidence_stance="supports_alpha",
            ),
            _match_record(
                "c2",
                claim="NVDA capex plans accelerated.",
                evidence="NVDA capex plans accelerated.",
                matched_alpha="A304",
                matched_evidence_stance="supports_alpha",
            ),
        ]
        result = _build(tmp_path, matches, structured=structured)
        assert _finding_for(result, "c1") is None
        assert _finding_for(result, "c2") is None
        # Provenance is still surfaced when the finding IS unclassified for
        # some other reason.
        matches2 = [
            _match_record("c1", matched_alpha=None),
        ]
        structured2 = [_structured_record("c1", duplicate_group_id="dupgroup_y")]
        result2 = _build(tmp_path, matches2, structured=structured2)
        assert _finding_for(result2, "c1")["duplicate_group_id"] == "dupgroup_y"

    def test_c4_duplicate_status_is_scoped_to_the_claims_own_matched_alpha(self, tmp_path):
        # c2 is a member of a group supporting A601, but c2's own
        # matched_alpha is A304 -- must not be flagged as a duplicate of a
        # group it does not actually support.
        matches = [
            _match_record(
                "c1",
                claim="NVDA momentum broadly positive.",
                evidence="NVDA momentum broadly positive.",
                matched_alpha="A601",
                matched_evidence_stance="supports_alpha",
            ),
            _match_record(
                "c2",
                claim="NVDA capex plans distinct from c1.",
                evidence="NVDA capex plans distinct from c1.",
                matched_alpha="A304",
                matched_evidence_stance="supports_alpha",
            ),
        ]
        groups = [_fact_group("g1", "c1", ["c1", "c2"], ["A601"])]
        result = _build(tmp_path, matches, groups=groups)
        assert _finding_for(result, "c2") is None

    def test_c5_full_audit_keeps_every_independently_unclassified_duplicate(self, tmp_path):
        matches = [
            _match_record("c1", matched_alpha=None),
            _match_record("c2", matched_alpha=None),
            _match_record("c3", matched_alpha=None),
        ]
        result = _build(tmp_path, matches)
        assert result["total_count"] == 3
        assert len(result["findings"]) == 3

    def test_c6_top_ranked_slice_never_amplifies_duplicate_entries(self, tmp_path):
        matches = [
            _match_record(
                "c1",
                claim="NVDA capex plans accelerated.",
                evidence="NVDA capex plans accelerated.",
                matched_alpha="A304",
                matched_evidence_stance="supports_alpha",
            ),
            _match_record(
                "c2",
                claim="NVDA capex plans accelerated.",
                evidence="NVDA capex plans accelerated.",
                matched_alpha="A304",
                matched_evidence_stance="supports_alpha",
            ),
        ]
        groups = [_fact_group("g1", "c1", ["c1", "c2"], ["A304"])]
        result = _build(tmp_path, matches, groups=groups)
        assert len(result["findings"]) == 1  # only c2 is unclassified


# ---------------------------------------------------------------------------
# Section D -- Top-20 deterministic ordering
# ---------------------------------------------------------------------------


class TestSectionDTopTwentyOrdering:
    def test_d1_zero_unclassified_findings(self, tmp_path):
        matches = [
            _match_record(
                "c1",
                claim="NVDA clean support.",
                evidence="NVDA clean support.",
                matched_alpha="A304",
                matched_evidence_stance="supports_alpha",
            )
        ]
        result = _build(tmp_path, matches)
        assert result["total_count"] == 0
        assert result["findings"] == []
        assert all(count == 0 for count in result["reason_counts"].values())

    def test_d2_between_one_and_twenty_all_present_with_ranks(self, tmp_path):
        matches = [_match_record(f"c{i}", matched_alpha=None) for i in range(5)]
        result = _build(tmp_path, matches)
        assert result["total_count"] == 5
        ranks = sorted(f["display_rank"] for f in result["findings"])
        assert ranks == [1, 2, 3, 4, 5]

    def test_d3_more_than_twenty_never_truncated_at_the_artifact_level(self, tmp_path):
        matches = [_match_record(f"c{i}", matched_alpha=None) for i in range(25)]
        result = _build(tmp_path, matches)
        assert result["total_count"] == 25
        assert len(result["findings"]) == 25
        ranks = sorted(f["display_rank"] for f in result["findings"])
        assert ranks == list(range(1, 26))

    def test_d4_ticker_specific_findings_sort_first(self, tmp_path):
        matches = [
            _match_record("specific", claim="NVDA named directly.", evidence="NVDA named directly.", matched_alpha=None),
            _match_record("generic", claim="Sector-wide, no ticker.", evidence="Sector-wide, no ticker.", matched_alpha=None),
        ]
        result = _build(tmp_path, matches)
        ordered = sorted(result["findings"], key=lambda f: f["display_rank"])
        assert [f["claim_id"] for f in ordered] == ["specific", "generic"]

    def test_d5_higher_confidence_sorts_first_among_equal_ticker_specificity(self, tmp_path):
        structured = [
            _structured_record("low", confidence=0.2),
            _structured_record("high", confidence=0.9),
        ]
        matches = [
            _match_record("low", matched_alpha=None),
            _match_record("high", matched_alpha=None),
        ]
        result = _build(tmp_path, matches, structured=structured)
        ordered = sorted(result["findings"], key=lambda f: f["display_rank"])
        assert [f["claim_id"] for f in ordered] == ["high", "low"]

    def test_d6_missing_confidence_sorts_after_present_confidence_never_guessed(self, tmp_path):
        structured = [
            _structured_record("missing"),
            _structured_record("present", confidence=0.05),
        ]
        del structured[0]["confidence"]
        matches = [
            _match_record("missing", matched_alpha=None),
            _match_record("present", matched_alpha=None),
        ]
        result = _build(tmp_path, matches, structured=structured)
        missing_finding = _finding_for(result, "missing")
        assert missing_finding["confidence"] is None
        ordered = sorted(result["findings"], key=lambda f: f["display_rank"])
        assert [f["claim_id"] for f in ordered] == ["present", "missing"]

    def test_d7_original_pipeline_order_breaks_ties_after_confidence(self, tmp_path):
        structured = [
            _structured_record("second", confidence=0.5, claim_index=5),
            _structured_record("first", confidence=0.5, claim_index=1),
        ]
        matches = [
            _match_record("second", matched_alpha=None),
            _match_record("first", matched_alpha=None),
        ]
        result = _build(tmp_path, matches, structured=structured)
        ordered = sorted(result["findings"], key=lambda f: f["display_rank"])
        assert [f["claim_id"] for f in ordered] == ["first", "second"]

    def test_d8_claim_id_is_the_final_stable_tiebreaker(self, tmp_path):
        structured = [
            _structured_record("z-claim", confidence=0.5, claim_index=1),
            _structured_record("a-claim", confidence=0.5, claim_index=1),
        ]
        matches = [
            _match_record("z-claim", matched_alpha=None),
            _match_record("a-claim", matched_alpha=None),
        ]
        result = _build(tmp_path, matches, structured=structured)
        ordered = sorted(result["findings"], key=lambda f: f["display_rank"])
        assert [f["claim_id"] for f in ordered] == ["a-claim", "z-claim"]

    def test_d9_display_rank_is_always_a_clean_permutation(self, tmp_path):
        matches = [_match_record(f"c{i}", matched_alpha=None) for i in range(37)]
        result = _build(tmp_path, matches)
        ranks = sorted(f["display_rank"] for f in result["findings"])
        assert ranks == list(range(1, 38))

    def test_d10_ordering_is_reproducible_across_repeated_builds(self, tmp_path):
        matches = [_match_record(f"c{i}", matched_alpha=None) for i in range(10)]
        result_a = _build(tmp_path, matches)
        result_b = _build(tmp_path, matches)
        order_a = [f["claim_id"] for f in sorted(result_a["findings"], key=lambda f: f["display_rank"])]
        order_b = [f["claim_id"] for f in sorted(result_b["findings"], key=lambda f: f["display_rank"])]
        assert order_a == order_b


# ---------------------------------------------------------------------------
# Section E -- full audit (download) vs UI Top-20 subset
# ---------------------------------------------------------------------------


class TestSectionEFullAuditVsTopTwenty:
    def test_e1_artifact_findings_list_always_contains_the_complete_total(self, tmp_path):
        matches = [_match_record(f"c{i}", matched_alpha=None) for i in range(30)]
        result = _build(tmp_path, matches)
        assert len(result["findings"]) == result["total_count"] == 30

    def test_e2_download_route_serves_the_complete_list_not_just_twenty(self, tmp_path):
        matches = [_match_record(f"c{i}", matched_alpha=None) for i in range(30)]
        _build(tmp_path, matches)
        status, content_type, raw_bytes, error = get_run_artifact_file(RUN_ID, ARTIFACT_FILENAME, output_root=str(tmp_path))
        assert status == 200
        assert content_type == "application/json"
        payload = json.loads(raw_bytes)
        assert len(payload["findings"]) == 30
        assert error is None

    def test_e3_research_response_top20_is_capped_but_total_count_is_true(self, tmp_path):
        matches = [_match_record(f"c{i}", matched_alpha=None) for i in range(30)]
        _build(tmp_path, matches)
        response = build_research_response(RUN_ID, str(tmp_path))
        assert len(response["unclassified_findings_top20"]) == DEFAULT_DISPLAY_LIMIT
        assert response["unclassified_findings_total_count"] == 30

    def test_e4_historical_run_without_the_artifact_reports_unavailable_never_zero(self, tmp_path):
        save_json_record(RUN_ID, "structured_agent_outputs.json", {"records": []}, output_root=tmp_path)
        response = build_research_response(RUN_ID, str(tmp_path))
        assert response["unclassified_findings_status"] == "unavailable"
        assert response["unclassified_findings_top20"] == []
        assert response["unclassified_findings_total_count"] is None
        assert response["unclassified_findings_download_available"] is False

    def test_e5_download_route_404s_cleanly_for_a_historical_run_without_the_artifact(self, tmp_path):
        save_json_record(RUN_ID, "structured_agent_outputs.json", {"records": []}, output_root=tmp_path)
        status, _content_type, raw_bytes, error = get_run_artifact_file(RUN_ID, ARTIFACT_FILENAME, output_root=str(tmp_path))
        assert status == 404
        assert raw_bytes is None
        assert error is not None

    def test_e6_module_never_imports_an_llm_or_provider_client(self):
        import comqutor_alpha.api.unclassified_findings as module

        source = module.__file__
        with open(source, encoding="utf-8") as handle:
            text = handle.read()
        for forbidden in ("llm_runtime", "provider", "openai", "anthropic"):
            assert forbidden not in text.lower()


# ---------------------------------------------------------------------------
# Section F -- artifact/manifest/run_audit/API consistency
# ---------------------------------------------------------------------------


class TestSectionFArtifactManifestConsistency:
    def test_f1_artifact_filename_registered_as_a_product_extension_not_required(self):
        assert ARTIFACT_FILENAME in PRODUCT_EXTENSION_ARTIFACT_FILENAMES
        assert ARTIFACT_FILENAME not in REQUIRED_ARTIFACT_FILENAMES

    def test_f2_a2_required_artifact_count_and_contents_are_unchanged(self):
        assert len(REQUIRED_ARTIFACT_FILENAMES) == 9
        assert REQUIRED_ARTIFACT_FILENAMES == (
            "metadata.json",
            "raw_agent_outputs.json",
            "structured_agent_outputs.json",
            "evidence_facts.json",
            "alpha_matches.json",
            "structure_graph.json",
            "alpha_activations.json",
            "conflicts.json",
            "run_audit.json",
        )

    def test_f3_manifest_registers_the_artifact_without_affecting_completeness(self, tmp_path):
        matches = [_match_record("c1", matched_alpha=None)]
        _build(tmp_path, matches)
        manifest = build_and_write_artifact_manifest(run_id=RUN_ID, ticker=TICKER, output_root=str(tmp_path))
        entry = next(e for e in manifest["artifacts"] if e["artifact_name"] == ARTIFACT_FILENAME)
        assert entry["required"] is False
        assert entry["exists"] is True
        assert entry["status"] == "valid"
        # Absence must never fail completeness either (it is not required).
        assert ARTIFACT_FILENAME not in manifest["missing_required_artifacts"]

    def test_f3b_manifest_reports_missing_honestly_when_absent(self, tmp_path):
        save_json_record(RUN_ID, "structured_agent_outputs.json", {"records": []}, output_root=tmp_path)
        manifest = build_and_write_artifact_manifest(run_id=RUN_ID, ticker=TICKER, output_root=str(tmp_path))
        entry = next(e for e in manifest["artifacts"] if e["artifact_name"] == ARTIFACT_FILENAME)
        assert entry["exists"] is False
        assert entry["status"] == "missing"
        assert ARTIFACT_FILENAME not in manifest["missing_required_artifacts"]
        assert manifest["required_artifact_count"] == 9

    def test_f4_run_audit_block_ready_when_artifact_exists(self, tmp_path):
        matches = [_match_record(f"c{i}", matched_alpha=None) for i in range(5)]
        _build(tmp_path, matches)
        audit = build_run_audit_payload(RUN_ID, str(tmp_path))
        block = audit["unclassified_findings"]
        assert block["status"] == "ready"
        assert block["total_count"] == 5
        assert block["display_count"] == 5
        assert block["display_limit"] == DEFAULT_DISPLAY_LIMIT

    def test_f4b_run_audit_block_unavailable_when_artifact_absent(self, tmp_path):
        save_json_record(RUN_ID, "structured_agent_outputs.json", {"records": []}, output_root=tmp_path)
        audit = build_run_audit_payload(RUN_ID, str(tmp_path))
        block = audit["unclassified_findings"]
        assert block["status"] == "unavailable"
        assert block["total_count"] is None
        assert block["reason_counts"] == {}

    def test_f5_run_audit_reason_counts_match_the_artifact_exactly(self, tmp_path):
        matches = [
            _match_record("c1", matched_alpha=None),
            _match_record(
                "c2",
                claim="NVDA background only.",
                evidence="NVDA background only.",
                matched_alpha="A304",
                matched_evidence_stance="neutral_background",
            ),
        ]
        artifact = _build(tmp_path, matches)
        audit = build_run_audit_payload(RUN_ID, str(tmp_path))
        assert audit["unclassified_findings"]["reason_counts"] == artifact["reason_counts"]

    def test_f6_unknown_extra_fields_never_pollute_run_audit(self, tmp_path):
        matches = [_match_record("c1", matched_alpha=None)]
        artifact = _build(tmp_path, matches)
        artifact["from_the_future_field"] = "unexpected"
        save_json_record(RUN_ID, ARTIFACT_FILENAME, artifact, output_root=tmp_path)
        audit = build_run_audit_payload(RUN_ID, str(tmp_path))
        assert "from_the_future_field" not in audit["unclassified_findings"]

    def test_f7_incompatible_schema_version_treated_as_unavailable(self, tmp_path):
        matches = [_match_record("c1", matched_alpha=None)]
        artifact = _build(tmp_path, matches)
        artifact["schema_version"] = "unclassified_findings.v99"
        save_json_record(RUN_ID, ARTIFACT_FILENAME, artifact, output_root=tmp_path)
        audit = build_run_audit_payload(RUN_ID, str(tmp_path))
        assert audit["unclassified_findings"]["status"] == "unavailable"
        response = build_research_response(RUN_ID, str(tmp_path))
        assert response["unclassified_findings_status"] == "unavailable"


# ---------------------------------------------------------------------------
# Section G -- upstream invariants + Provider calls = 0
# ---------------------------------------------------------------------------


class TestSectionGUpstreamInvariants:
    def test_g1_input_matches_payload_is_never_mutated(self, tmp_path):
        matches = [
            _match_record(
                "c1",
                claim="NVDA background only.",
                evidence="NVDA background only.",
                matched_alpha="A304",
                matched_evidence_stance="neutral_background",
            )
        ]
        before = copy.deepcopy(matches)
        _build(tmp_path, matches)
        assert matches == before

    def test_g2_structured_agent_outputs_file_is_never_rewritten(self, tmp_path):
        structured = [_structured_record("c1")]
        matches = [_match_record("c1", matched_alpha=None)]
        save_json_record(RUN_ID, "structured_agent_outputs.json", {"records": structured}, output_root=tmp_path)
        path = tmp_path / RUN_ID / "structured_agent_outputs.json"
        before = path.read_bytes()
        build_unclassified_findings_export(
            run_id=RUN_ID,
            ticker=TICKER,
            output_root=str(tmp_path),
            alpha_matches_payload={"matches": matches},
            evidence_facts_payload={"groups": []},
        )
        after = path.read_bytes()
        assert before == after

    def test_g3_alpha_matches_records_are_byte_identical_after_export(self, tmp_path):
        matches = [
            _match_record(
                "c1",
                claim="NVDA capex plans accelerated.",
                evidence="NVDA capex plans accelerated.",
                matched_alpha="A304",
                matched_evidence_stance="supports_alpha",
                candidate_scores=[{"alpha_id": "A304", "score": 0.9}],
            )
        ]
        payload = {"matches": matches}
        before = copy.deepcopy(payload)
        save_json_record(RUN_ID, "structured_agent_outputs.json", {"records": [_structured_record("c1")]}, output_root=tmp_path)
        build_unclassified_findings_export(
            run_id=RUN_ID,
            ticker=TICKER,
            output_root=str(tmp_path),
            alpha_matches_payload=payload,
            evidence_facts_payload={"groups": []},
        )
        assert payload == before

    def test_g4_evidence_facts_groups_are_byte_identical_after_export(self, tmp_path):
        groups = [_fact_group("g1", "c1", ["c1", "c2"], ["A304"])]
        evidence_facts_payload = {"groups": groups}
        before = copy.deepcopy(evidence_facts_payload)
        matches = [
            _match_record(
                "c1",
                claim="NVDA capex plans accelerated.",
                evidence="NVDA capex plans accelerated.",
                matched_alpha="A304",
                matched_evidence_stance="supports_alpha",
            ),
            _match_record(
                "c2",
                claim="NVDA capex plans accelerated.",
                evidence="NVDA capex plans accelerated.",
                matched_alpha="A304",
                matched_evidence_stance="supports_alpha",
            ),
        ]
        save_json_record(RUN_ID, "structured_agent_outputs.json", {"records": [_structured_record("c1"), _structured_record("c2")]}, output_root=tmp_path)
        build_unclassified_findings_export(
            run_id=RUN_ID,
            ticker=TICKER,
            output_root=str(tmp_path),
            alpha_matches_payload={"matches": matches},
            evidence_facts_payload=evidence_facts_payload,
        )
        assert evidence_facts_payload == before

    def test_g5_module_reuses_only_the_narrow_ticker_specificity_helper(self):
        import comqutor_alpha.api.unclassified_findings as module

        with open(module.__file__, encoding="utf-8") as handle:
            text = handle.read()
        assert "_is_ticker_specific" in text
        # Never imports the scoring/grouping entry points themselves.
        assert "score_alpha_v2" not in text
        assert "group_evidence_candidates" not in text
        assert "detect_alpha_conflicts" not in text

    def test_g6_output_is_byte_for_byte_reproducible(self, tmp_path):
        matches = [
            _match_record(
                "c1",
                claim="NVDA capex plans accelerated.",
                evidence="NVDA capex plans accelerated.",
                matched_alpha="A304",
                matched_evidence_stance="supports_alpha",
            ),
            _match_record("c2", matched_alpha=None),
        ]
        groups = [_fact_group("g1", "c1", ["c1"], ["A304"])]
        result_a = _build(tmp_path, matches, groups=groups)
        result_b = _build(tmp_path, matches, groups=groups)
        assert json.dumps(result_a, sort_keys=True) == json.dumps(result_b, sort_keys=True)

    def test_g7_schema_version_is_stable(self):
        assert SCHEMA_VERSION == "unclassified_findings.v1"

    @pytest.mark.parametrize("env_flag", ["PROVIDER_CALLS"])
    def test_g8_no_provider_env_dependency_declared_by_this_module(self, env_flag):
        import comqutor_alpha.api.unclassified_findings as module

        with open(module.__file__, encoding="utf-8") as handle:
            text = handle.read()
        assert env_flag not in text
