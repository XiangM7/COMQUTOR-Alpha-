"""Phase 1 Master evidence-alignment fix: unit tests for the
EvidenceQuoteResolver (resolve_supporting_quote) -- the sole, exact-match-
only authority that turns a Provider-proposed verbatim quote into a source
span. No Provider calls; pure function tests only.
"""

from __future__ import annotations

from comqutor_alpha.structure_engine.structured_output_shadow_v3 import (
    RESOLUTION_AMBIGUOUS_MULTIPLE_MATCH,
    RESOLUTION_DISAMBIGUATED_VIA_CANDIDATE,
    RESOLUTION_INVALID_QUOTE,
    RESOLUTION_NO_EXACT_MATCH,
    RESOLUTION_UNIQUE_EXACT_MATCH,
    resolve_supporting_quote,
    summarize_resolution_log,
)

REPORT = (
    "Net margin reached 71.5% for the quarter, well above the prior year period. "
    "Gross margin was 46.2% in the same period."
)


def test_unique_exact_match_locates_correct_span():
    quote = "Net margin reached 71.5% for the quarter, well above the prior year period."
    resolved = resolve_supporting_quote(report=REPORT, quote=quote)
    assert resolved.status == RESOLUTION_UNIQUE_EXACT_MATCH
    assert resolved.start == REPORT.index(quote)
    assert resolved.end == resolved.start + len(quote)
    assert REPORT[resolved.start : resolved.end] == quote
    assert resolved.match_count == 1


def test_no_exact_match_is_rejected_not_repaired():
    resolved = resolve_supporting_quote(report=REPORT, quote="Net margin reached 71.6%")
    assert resolved.status == RESOLUTION_NO_EXACT_MATCH
    assert resolved.start is None
    assert resolved.end is None


def test_fabricated_quote_never_falls_back_to_nearest_neighbor():
    """A quote that is NOT in the report must never be silently mapped to
    the textually closest real sentence -- that would be exactly the
    fuzzy/embedding-style repair this resolver must never perform."""

    resolved = resolve_supporting_quote(report=REPORT, quote="Net income rose 71.5%")
    assert resolved.status == RESOLUTION_NO_EXACT_MATCH


def test_duplicate_exact_match_without_hints_is_ambiguous_and_rejected():
    report = "Disclaimer text. Some content in between. Disclaimer text."
    resolved = resolve_supporting_quote(report=report, quote="Disclaimer text.")
    assert resolved.status == RESOLUTION_AMBIGUOUS_MULTIPLE_MATCH
    assert resolved.match_count == 2
    assert resolved.start is None
    assert resolved.end is None


def test_ambiguous_match_never_defaults_to_first_occurrence():
    report = "X. X. X."
    resolved = resolve_supporting_quote(report=report, quote="X.")
    assert resolved.status == RESOLUTION_AMBIGUOUS_MULTIPLE_MATCH
    assert resolved.match_count == 3
    # The critical safety property: never silently pick positions[0].
    assert resolved.start is None


def test_disambiguation_via_candidate_hint_picks_the_overlapping_occurrence():
    report = "Disclaimer text. Some content in between. Disclaimer text."
    second_occurrence_start = report.rindex("Disclaimer text.")
    hint_span = (second_occurrence_start, second_occurrence_start + len("Disclaimer text."))
    resolved = resolve_supporting_quote(
        report=report, quote="Disclaimer text.", candidate_hint_spans=[hint_span]
    )
    assert resolved.status == RESOLUTION_DISAMBIGUATED_VIA_CANDIDATE
    assert resolved.start == second_occurrence_start
    assert resolved.match_count == 2


def test_disambiguation_hint_overlapping_more_than_one_occurrence_stays_ambiguous():
    report = "AB AB AB"
    # A hint spanning the whole report overlaps all three occurrences of "AB" --
    # disambiguation requires the hint to isolate exactly one, not "at least one".
    resolved = resolve_supporting_quote(
        report=report, quote="AB", candidate_hint_spans=[(0, len(report))]
    )
    assert resolved.status == RESOLUTION_AMBIGUOUS_MULTIPLE_MATCH


def test_disambiguation_hint_that_overlaps_nothing_stays_ambiguous():
    report = "Disclaimer text. Disclaimer text."
    resolved = resolve_supporting_quote(
        report=report, quote="Disclaimer text.", candidate_hint_spans=[(1000, 1010)]
    )
    assert resolved.status == RESOLUTION_AMBIGUOUS_MULTIPLE_MATCH


def test_invalid_quote_type_rejected():
    resolved = resolve_supporting_quote(report=REPORT, quote=12345)
    assert resolved.status == RESOLUTION_INVALID_QUOTE


def test_empty_string_quote_rejected():
    resolved = resolve_supporting_quote(report=REPORT, quote="")
    assert resolved.status == RESOLUTION_INVALID_QUOTE


def test_none_quote_rejected():
    resolved = resolve_supporting_quote(report=REPORT, quote=None)
    assert resolved.status == RESOLUTION_INVALID_QUOTE


def test_unicode_quote_resolves_by_character_offset_not_byte_offset():
    report = "净利润率达到71.5%🎯，超过去年同期。总收入增长强劲。"
    quote = "净利润率达到71.5%🎯，超过去年同期。"
    resolved = resolve_supporting_quote(report=report, quote=quote)
    assert resolved.status == RESOLUTION_UNIQUE_EXACT_MATCH
    assert report[resolved.start : resolved.end] == quote
    # Character-offset sanity: end must equal start + len(quote) in Python
    # character units, not UTF-8 byte units (the emoji is >1 byte in UTF-8).
    assert resolved.end - resolved.start == len(quote)


def test_quote_spanning_a_newline_resolves_correctly():
    report = "Factory utilization rose in June.\nThe second shift supplied the extra units."
    quote = "Factory utilization rose in June.\nThe second shift supplied the extra units."
    resolved = resolve_supporting_quote(report=report, quote=quote)
    assert resolved.status == RESOLUTION_UNIQUE_EXACT_MATCH
    assert report[resolved.start : resolved.end] == quote


def test_quote_inside_a_markdown_table_cell_resolves_correctly():
    report = (
        "## Technicals\n"
        "| Metric | Value |\n"
        "|---|---|\n"
        "| RSI | 74.03 |\n"
        "| MACD | 1.2 |\n"
    )
    quote = "| RSI | 74.03 |"
    resolved = resolve_supporting_quote(report=report, quote=quote)
    assert resolved.status == RESOLUTION_UNIQUE_EXACT_MATCH
    assert report[resolved.start : resolved.end] == quote


def test_repeated_number_across_two_table_rows_is_ambiguous_without_full_row_context():
    report = "| RSI | 71.5 |\n| Volume Index | 71.5 |\n"
    resolved = resolve_supporting_quote(report=report, quote="71.5")
    assert resolved.status == RESOLUTION_AMBIGUOUS_MULTIPLE_MATCH
    # Quoting the full row (not just the bare number) disambiguates it --
    # this is exactly the behavior the v3 prompt instructs the model to
    # follow ("quote enough surrounding text ... to make the location
    # unambiguous").
    resolved_full_row = resolve_supporting_quote(report=report, quote="| RSI | 71.5 |")
    assert resolved_full_row.status == RESOLUTION_UNIQUE_EXACT_MATCH


def test_repeated_sentence_boilerplate_is_ambiguous():
    report = (
        "For information only, not investment advice.\n"
        "Revenue rose 12% year over year.\n"
        "For information only, not investment advice.\n"
    )
    resolved = resolve_supporting_quote(
        report=report, quote="For information only, not investment advice."
    )
    assert resolved.status == RESOLUTION_AMBIGUOUS_MULTIPLE_MATCH
    assert resolved.match_count == 2


def test_overlapping_occurrences_are_all_counted():
    # "aa" occurs at offsets 0 and 1 in "aaa" (overlapping) -- both must be
    # detected so ambiguity is never hidden by a stride that skips a match.
    resolved = resolve_supporting_quote(report="aaa", quote="aa")
    assert resolved.status == RESOLUTION_AMBIGUOUS_MULTIPLE_MATCH
    assert resolved.match_count == 2


def test_summarize_resolution_log_counts_every_status():
    log = [
        {"status": RESOLUTION_UNIQUE_EXACT_MATCH},
        {"status": RESOLUTION_UNIQUE_EXACT_MATCH},
        {"status": RESOLUTION_DISAMBIGUATED_VIA_CANDIDATE},
        {"status": RESOLUTION_NO_EXACT_MATCH},
        {"status": RESOLUTION_AMBIGUOUS_MULTIPLE_MATCH},
        {"status": RESOLUTION_INVALID_QUOTE},
    ]
    summary = summarize_resolution_log(log)
    assert summary == {
        "total": 6,
        "unique_exact_match": 2,
        "disambiguated_via_candidate": 1,
        "no_exact_match": 1,
        "ambiguous_multiple_match": 1,
        "invalid_quote": 1,
    }


def test_summarize_resolution_log_empty():
    assert summarize_resolution_log([]) == {
        "total": 0,
        "unique_exact_match": 0,
        "disambiguated_via_candidate": 0,
        "no_exact_match": 0,
        "ambiguous_multiple_match": 0,
        "invalid_quote": 0,
    }
