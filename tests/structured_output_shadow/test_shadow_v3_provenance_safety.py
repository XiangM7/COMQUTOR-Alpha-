"""Phase 1 Master evidence-alignment fix: provenance safety tests for v3.

Proves the deterministic layer's actual guarantee: exact_quote ==
report[start:end], always, and any quote that cannot be found or uniquely
located is rejected outright -- never fuzzy-matched, never repaired, never
defaulted to the first occurrence, and never silently dropped from a claim
while keeping the rest (rejection is bundle-level, matching v1/v2). No
Provider calls.
"""

from __future__ import annotations

import json

from conftest import FakeSemanticInvoker, v3_claim, v3_proposal

from comqutor_alpha.structure_engine.structured_output_shadow_v3 import (
    normalize_v3_proposal_to_canonical_bundle,
    parse_report_shadow_v3,
)


def _bundle(*, report: str, proposal: dict, factor_vocabulary=()):
    return parse_report_shadow_v3(
        semantic_invoker=FakeSemanticInvoker(json.dumps(proposal)),
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="fundamental_agent",
        agent_output_id="run-1:fundamental_agent:fundamentals_report",
        factor_vocabulary=list(factor_vocabulary),
    )


def test_fabricated_quote_is_rejected_never_admitted():
    report = "Net margin reached 71.5% for the quarter."
    bundle = _bundle(
        report=report,
        proposal=v3_proposal(
            claims=[
                v3_claim(
                    claim="Net margin reached 71.5%",
                    supporting_quotes=["Net margin reached 92.0% for the quarter."],
                )
            ]
        ),
    )
    assert bundle["validation_summary"]["valid"] is False
    assert "SHADOW_SOURCE_SPAN_INVALID" in bundle["validation_summary"]["reason_codes"]
    assert bundle["claims"] == []


def test_cross_report_evidence_is_rejected():
    """A quote that is a real, exact sentence from a DIFFERENT report's text
    must not be admitted just because it is well-formed prose -- it must be
    an exact substring of THIS report's text specifically."""

    other_report_sentence = "Total revenue rose 18% year over year at the parent company."
    this_report = "Net margin reached 71.5% for the quarter, driven by cost discipline."
    assert other_report_sentence not in this_report
    bundle = _bundle(
        report=this_report,
        proposal=v3_proposal(
            claims=[v3_claim(claim="Total revenue rose 18%", supporting_quotes=[other_report_sentence])]
        ),
    )
    assert bundle["validation_summary"]["valid"] is False
    assert "SHADOW_SOURCE_SPAN_INVALID" in bundle["validation_summary"]["reason_codes"]


def test_ambiguous_quote_without_disambiguating_hint_is_rejected():
    report = "Disclaimer text. Unrelated filler content. Disclaimer text."
    bundle = _bundle(
        report=report,
        proposal=v3_proposal(claims=[v3_claim(claim="Disclaimer applies", supporting_quotes=["Disclaimer text."])]),
    )
    assert bundle["validation_summary"]["valid"] is False
    assert "SHADOW_SOURCE_SPAN_INVALID" in bundle["validation_summary"]["reason_codes"]


def test_one_bad_quote_among_several_rejects_the_whole_bundle_not_just_that_claim():
    """v1/v2/v3 all use bundle-level, all-or-nothing admission -- a claim
    with one good quote and one fabricated quote must not be partially
    admitted with only the good span kept."""

    report = "Net margin reached 71.5% for the quarter. Gross margin was 46.2% in the period."
    good_quote = "Net margin reached 71.5% for the quarter."
    fabricated_quote = "Operating margin reached 99.9% for the quarter."
    bundle = _bundle(
        report=report,
        proposal=v3_proposal(
            claims=[v3_claim(claim="Margins improved", supporting_quotes=[good_quote, fabricated_quote])]
        ),
    )
    assert bundle["validation_summary"]["valid"] is False
    assert bundle["claims"] == []


def test_exact_quote_always_equals_report_slice_on_acceptance():
    report = "RSI reached 74.03 on the daily chart, its highest reading this quarter."
    quote = "RSI reached 74.03 on the daily chart, its highest reading this quarter."
    bundle = _bundle(report=report, proposal=v3_proposal(claims=[v3_claim(claim=quote, supporting_quotes=[quote])]))
    assert bundle["validation_summary"]["valid"] is True
    span = bundle["claims"][0]["source_spans"][0]
    assert report[span["start"] : span["end"]] == span["exact_quote"] == quote


def test_unicode_provenance_survives_full_pipeline():
    report = "净利润率达到71.5%🎯，超过去年同期。总收入增长强劲。"
    quote = "净利润率达到71.5%🎯，超过去年同期。"
    bundle = _bundle(report=report, proposal=v3_proposal(claims=[v3_claim(claim=quote, supporting_quotes=[quote])]))
    assert bundle["validation_summary"]["valid"] is True
    span = bundle["claims"][0]["source_spans"][0]
    assert report[span["start"] : span["end"]] == quote


def test_newline_spanning_quote_survives_full_pipeline():
    report = "Factory utilization rose in June.\nThe second shift supplied the extra units."
    bundle = _bundle(report=report, proposal=v3_proposal(claims=[v3_claim(claim=report, supporting_quotes=[report])]))
    assert bundle["validation_summary"]["valid"] is True
    span = bundle["claims"][0]["source_spans"][0]
    assert report[span["start"] : span["end"]] == report


def test_punctuation_and_case_must_match_exactly_no_normalization():
    report = "Net margin reached 71.5% for the quarter."
    # Case-folded, punctuation-stripped near-miss -- must NOT be treated as
    # equivalent to the real sentence.
    near_miss = "net margin reached 71.5% for the quarter"
    bundle = _bundle(
        report=report,
        proposal=v3_proposal(claims=[v3_claim(claim="Net margin 71.5%", supporting_quotes=[near_miss])]),
    )
    assert bundle["validation_summary"]["valid"] is False


def test_non_string_quote_entries_rejected_not_crashed():
    report = "Revenue growth remained strong this quarter."
    proposal = v3_proposal(
        claims=[
            {
                "claim": "Revenue grew",
                "supporting_quotes": [12345, None, ["nested"]],
                "entities": [],
                "factors": [],
                "direction": "unknown",
                "confidence": 0.5,
            }
        ]
    )
    bundle = _bundle(report=report, proposal=proposal)
    assert bundle["validation_summary"]["valid"] is False
    assert bundle["claims"] == []


def test_supporting_quotes_not_a_list_degrades_to_empty_spans_not_a_crash():
    report = "Revenue growth remained strong this quarter."
    proposal = v3_proposal(
        claims=[
            {
                "claim": "Revenue grew",
                "supporting_quotes": "not a list",
                "entities": [],
                "factors": [],
                "direction": "unknown",
                "confidence": 0.5,
            }
        ]
    )
    bundle = _bundle(report=report, proposal=proposal)
    assert bundle["validation_summary"]["valid"] is False


def test_missing_supporting_quotes_key_degrades_to_empty_spans_not_a_crash():
    report = "Revenue growth remained strong this quarter."
    proposal = v3_proposal(
        claims=[
            {
                "claim": "Revenue grew",
                "entities": [],
                "factors": [],
                "direction": "unknown",
                "confidence": 0.5,
            }
        ]
    )
    bundle = _bundle(report=report, proposal=proposal)
    assert bundle["validation_summary"]["valid"] is False


def test_normalizer_never_raises_on_deeply_malformed_proposal():
    report = "Revenue growth remained strong this quarter."
    malformed = {"claims": "not a list", "abstentions": 42}
    canonical, resolution_log = normalize_v3_proposal_to_canonical_bundle(
        malformed,
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-1:news_agent:news_report",
        candidate_index_to_id={},
    )
    assert canonical["claims"] == []
    assert canonical["abstentions"] == []
    assert resolution_log == []


def test_no_fuzzy_repair_module_never_imports_a_fuzzy_matching_library():
    """Static guard: structured_output_shadow_v3.py must never import a
    fuzzy-matching, embedding, or edit-distance library -- the resolver's
    only allowed primitive is exact str.find()."""

    import ast
    from pathlib import Path

    source_path = (
        Path(__file__).resolve().parents[2]
        / "comqutor_alpha/structure_engine/structured_output_shadow_v3.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module.split(".")[0])
    forbidden = {
        "rapidfuzz",
        "fuzzywuzzy",
        "Levenshtein",
        "difflib",
        "sentence_transformers",
        "faiss",
        "annoy",
        "sklearn",
        "numpy",
        "scipy",
    }
    assert imported_modules.isdisjoint(forbidden), imported_modules & forbidden
