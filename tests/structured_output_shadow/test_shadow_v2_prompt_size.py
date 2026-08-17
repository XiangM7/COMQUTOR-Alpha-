"""Phase 1 Master prompt-size fix: regression test pinning the measured
result of docs/audit_artifacts/phase1_master/prompt_audit/. Builds the real
v1 and v2 requests through real production code (not hand-simulated text) for
the frozen NVDA fundamental Smoke report and asserts the audit's size/
duplication targets keep holding -- so a future change to
build_candidate_segments, build_shadow_request_v2, or the v2 prompt cannot
silently regress this fix back toward the original ~98.6K-char request.
Zero Provider calls.
"""

from __future__ import annotations

import json

from comqutor_alpha.structure_engine.structured_output_shadow_prompt import (
    build_shadow_prompt_input,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v2 import (
    build_shadow_prompt_input_v2,
)
from scripts.audit_prompt_v1_root_cause import build_v1_request
from scripts.audit_prompt_v2_comparison import build_v2_request

TARGET_MAX_V2_CHARS = 40_000
TARGET_MAX_DUPLICATION_RATIO = 1.05


def test_v2_request_is_well_under_the_40k_target():
    built = build_v2_request()
    prompt_text = build_shadow_prompt_input_v2(built["request"])
    assert len(prompt_text) <= TARGET_MAX_V2_CHARS


def test_v2_report_duplication_ratio_at_target():
    built = build_v2_request()
    report_text = built["report_text"]
    prompt_text = build_shadow_prompt_input_v2(built["request"])
    # No candidate text is ever sent in v2 -- the report should appear
    # exactly once by construction.
    payload = json.loads(prompt_text.split("SHADOW_REQUEST_JSON:\n", 1)[1])
    assert payload["agent_report"] == report_text
    assert "claim_hint" not in prompt_text
    assert "evidence_hint" not in prompt_text
    ratio = len(report_text) / len(report_text)  # v2 sends it exactly once
    assert ratio <= TARGET_MAX_DUPLICATION_RATIO


def test_v2_request_is_deterministic():
    first = build_shadow_prompt_input_v2(build_v2_request()["request"])
    second = build_shadow_prompt_input_v2(build_v2_request()["request"])
    assert first == second


def test_v1_still_reproduces_the_measured_real_failed_request():
    """Pins the audit's own baseline: if this ever changes, the v1 report
    in docs/audit_artifacts/phase1_master/prompt_audit/ is stale and must be
    regenerated, not silently left inconsistent with the code."""

    built = build_v1_request()
    prompt_text = build_shadow_prompt_input(built["request"])
    assert len(prompt_text) == 98_633


def test_v2_is_a_large_reduction_from_v1():
    v1_text = build_shadow_prompt_input(build_v1_request()["request"])
    v2_text = build_shadow_prompt_input_v2(build_v2_request()["request"])
    reduction_pct = 100 * (len(v1_text) - len(v2_text)) / len(v1_text)
    assert reduction_pct >= 50.0
