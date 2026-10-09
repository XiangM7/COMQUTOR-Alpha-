"""Narrowly targeted deterministic tests for the Day 4G Candidate 3 semantic
guardrail addition to the Alpha classifier prompt (week2.alpha_classifier.v6
/ week2.alpha_classifier_batch.v4), plus the v7 (2026-10-01, AI-review
comparison round) follow-up to the single prompt only.

These are prompt-content and metadata assertions, not LLM-behavior tests --
the semantic change lives entirely in instruction wording sent to a real
Provider, so it cannot be exercised deterministically. What CAN be verified
deterministically:
  - the new guardrail clauses are present, verbatim-consistent, in both the
    single and batch prompts (the file's own convention requires the batch
    prompt to carry identical semantic content to the single prompt) for v6;
  - v7's five additive clarifications are present in the single prompt only
    (alpha_classifier_batch is a separate task/call-path, not touched this
    round -- out of scope for John's T3 Alpha-classification work);
  - the specific protective exemption that Candidate 1 lacked (a
    growth/decline-characterized figure remains sufficient) is present, so
    Candidate 1's exact regression mechanism is not silently reintroduced;
  - the version identifiers changed and do not collide with any retired
    Candidate 1/2 identifier, or with v6 (ADR-005 anti-collision).
"""

from __future__ import annotations

import hashlib

from comqutor_alpha.structure_engine.week2_llm import (
    _TASK_INSTRUCTIONS,
    _TASK_RUNTIME_METADATA,
)

RETIRED_SINGLE_VERSIONS = {"week2.alpha_classifier.v4", "week2.alpha_classifier.v5"}
RETIRED_BATCH_VERSIONS = {
    "week2.alpha_classifier_batch.v2",
    "week2.alpha_classifier_batch.v3",
}
# v6, unlike v4/v5, was never rejected for a regression -- it was the real
# production baseline (used by execution t3live_20261001T014648Z_1fb9c9d5,
# among others) until v7 superseded it. Tracked in its own set so the
# anti-collision check below still covers it without mislabeling it a
# rejected candidate.
PRIOR_PRODUCTION_SINGLE_VERSIONS = {"week2.alpha_classifier.v6"}


def test_guardrail_clauses_present_in_single_prompt() -> None:
    text = _TASK_INSTRUCTIONS["alpha_classifier"]
    assert "The Evidence's own words must state the" in text
    assert "not merely that the claim shares an" in text
    assert "bare listing of figures across periods or categories" in text
    assert "hypothetical, conditional-downside, rebuttal, or skepticism" in text
    assert "Price-technical indicators alone" in text
    assert "prefer A103 over A101" in text


def test_guardrail_protective_exemption_present_in_single_prompt() -> None:
    """The exact carve-out that Candidate 1 lacked: a figure the Evidence
    already characterizes as a trend remains sufficient on its own. Without
    this sentence, Candidate 1's documented regression mechanism (21/25
    regressions -- see docs/audit_artifacts/
    v0_2_day4c_candidate1_regression_analysis.json) would reappear."""
    text = _TASK_INSTRUCTIONS["alpha_classifier"]
    assert "remains sufficient on its own" in text
    assert "'grew', 'increased', 'record', 'accelerating'" in text
    assert "never a figure the Evidence itself already interprets" in text


def test_v7_clauses_present_in_single_prompt() -> None:
    """2026-10-01 (AI-review comparison round): the five additive
    clarifications this round added, each traced to a confirmed
    misclassification pattern in t3live_20261001T014648Z_1fb9c9d5's own
    real execution (see week2_llm.py's own prompt_version metadata comment
    for the full per-clause rationale)."""
    text = _TASK_INSTRUCTIONS["alpha_classifier"]
    # 1. proposition-identification step
    assert "First identify what the Evidence's own words actually assert" in text
    assert "the setup for a rebuttal whose actual substantiating content is not given" in text
    # 2. opposition still counts as engagement
    assert "Opposing an Alpha's thesis still means the Evidence substantively engages" in text
    # 3. A304 price-vs-valuation clause
    assert "RELATIVE TO FUNDAMENTALS" in text
    assert "is a price-technical observation, not a valuation-vs-fundamentals claim" in text
    # 4. A101/A103 tie-break-not-requirement clause
    assert "this is a tie-breaking preference for when such capacity IS named, not a requirement" in text
    assert "the absence of these specific words never by itself disqualifies A103" in text
    # 5. A003 mechanical-flow clause
    assert "A003 (Liquidity Expansion) requires the Evidence to describe broad macro liquidity" in text
    assert "is not itself evidence of improving macro liquidity or risk appetite" in text


def test_v7_clauses_absent_from_batch_prompt_because_batch_is_untouched() -> None:
    """alpha_classifier_batch is a separate task/call-path (Step 5A
    execution-capacity repair), out of this round's T3 Alpha-classification
    scope -- v7's new clauses were deliberately NOT propagated there. This
    test makes that an explicit, checked fact rather than an unstated
    assumption, so a future round that DOES intend to sync them will see
    this test start failing and know to update it, rather than silently
    drifting unnoticed."""
    batch = _TASK_INSTRUCTIONS["alpha_classifier_batch"]
    assert "First identify what the Evidence's own words actually assert" not in batch
    assert "RELATIVE TO FUNDAMENTALS" not in batch


def test_batch_prompt_carries_identical_new_guardrail_content() -> None:
    """The file's own long-standing convention: alpha_classifier_batch's
    semantic rules must be an exact copy of alpha_classifier's own -- only
    the request/response envelope differs."""
    single = _TASK_INSTRUCTIONS["alpha_classifier"]
    batch = _TASK_INSTRUCTIONS["alpha_classifier_batch"]

    guardrail_fragments = [
        "not merely that the claim shares an industry, sector, or ticker",
        "bare listing of figures across periods or categories",
        "remains sufficient on its own -- this targets only",
        "'grew', 'increased', 'record', 'accelerating', "
        "'compressed', 'declined'",
        "hypothetical, conditional-downside, rebuttal, or skepticism",
        "Price-technical indicators alone (moving averages, "
        "RSI, MACD, momentum streaks) are never sufficient for A601",
        "prefer A103 over A101 even when AI demand is the "
        "stated cause",
    ]
    for fragment in guardrail_fragments:
        assert fragment in single, f"missing from single prompt: {fragment!r}"
        assert fragment in batch, f"missing from batch prompt: {fragment!r}"


def test_candidate3_versions_bumped_and_do_not_collide_with_retired_ids() -> None:
    single_meta = _TASK_RUNTIME_METADATA["alpha_classifier"]
    batch_meta = _TASK_RUNTIME_METADATA["alpha_classifier_batch"]

    # 2026-10-01 (AI-review comparison round): v7 supersedes v6 as the
    # single-claim prompt's current content -- v6's own text/hash is
    # preserved in the metadata comment above and in
    # docs/audit_artifacts/round_source_linking_t0_t2/
    # alpha_classifier_prompt_v7_diff.patch, never silently discarded.
    # alpha_classifier_batch is NOT touched this round (separate task/
    # call-path, out of this round's T3 scope) and remains v4.
    assert single_meta["prompt_version"] == "week2.alpha_classifier.v7"
    assert single_meta["output_schema_version"] == "week2.alpha_classifier.output.v3"
    assert single_meta["input_schema_version"] == "week2.alpha_classifier.input.v2"

    assert batch_meta["prompt_version"] == "week2.alpha_classifier_batch.v4"
    assert batch_meta["output_schema_version"] == "week2.alpha_classifier_batch.output.v2"
    assert batch_meta["input_schema_version"] == "week2.alpha_classifier_batch.input.v1"

    assert single_meta["prompt_version"] not in RETIRED_SINGLE_VERSIONS
    assert single_meta["prompt_version"] not in PRIOR_PRODUCTION_SINGLE_VERSIONS
    assert batch_meta["prompt_version"] not in RETIRED_BATCH_VERSIONS


def test_candidate3_prompt_hash_differs_from_every_retired_candidate_hash() -> None:
    """ADR-005 anti-collision: a versioned identifier's content must be
    unique -- the current v7 prompt text must hash differently from the v3
    baseline, the retired v4/v5 candidate texts (recorded in the Day 4B/4C
    audit artifacts), and v6 (the prior real production baseline, preserved
    verbatim below and in alpha_classifier_prompt_v7_diff.patch) -- so no
    cached result under a different version could ever be mistaken for
    reflecting this content, and vice versa."""
    current_hash = hashlib.sha256(
        _TASK_INSTRUCTIONS["alpha_classifier"].encode("utf-8")
    ).hexdigest()

    baseline_v3_hash = (
        "a2ca2a32be2d5c22301a0905112727d2c43aece60b1d9e680c8092c3d67c25d8"
    )
    candidate1_v4_hash = "36bf5a63"  # documented prefix, Day 4B
    candidate2_v5_hash = "70303c5f"  # documented prefix, Day 4C
    # v6's own raw-instruction-text hash (NOT Week2LLMGateway.
    # prompt_identity_sha256, which also hashes the shared JSON-only prefix
    # and separator -- that composite value, bb2dbdf0f3fc9a43291233494c2f
    # 355275b4fe6fddc71cd63fd1377f9ba109d9, is the one recorded in
    # t3live_20261001T014648Z_1fb9c9d5's own freeze_identity.json).
    baseline_v6_hash = (
        "d53b2d7511f4c4a8089db746d09e4c79cb38f22597dac6459920ca3deac1171d"
    )

    assert current_hash != baseline_v3_hash
    assert not current_hash.startswith(candidate1_v4_hash)
    assert not current_hash.startswith(candidate2_v5_hash)
    assert current_hash != baseline_v6_hash
    assert len(current_hash) == 64
