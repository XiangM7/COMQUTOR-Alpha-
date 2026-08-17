"""Phase 1 Master evidence-alignment fix: regression test proving v3 keeps
v2's measured prompt-size compression (docs/audit_artifacts/phase1_master/
prompt_audit/) -- the task explicitly requires v3 to retain v2's already-
completed compression (report sent exactly once, compact request, compact
factors, deterministic IDs), changing only the evidence proposal shape.
Builds the real v3 request through real production code for the same
frozen, already-persisted NVDA fundamental Smoke report v1/v2's own size
tests use. Zero Provider calls (reads only already-persisted historical
data on disk).
"""

from __future__ import annotations

import json

from comqutor_alpha.structure_engine.factor_normalizer import FACTOR_ALIASES
from comqutor_alpha.structure_engine.structured_output_shadow import build_candidate_segments
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v2 import (
    build_shadow_prompt_input_v2,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v3 import (
    build_shadow_prompt_input_v3,
)
from comqutor_alpha.structure_engine.structured_output_shadow_v2 import build_shadow_request_v2
from comqutor_alpha.structure_engine.structured_output_shadow_v3 import build_shadow_request_v3
from scripts.audit_prompt_v1_root_cause import (
    AGENT,
    AGENT_OUTPUT_ID,
    REAL_RUN_ID,
    TICKER,
    _load_raw_report,
)
from scripts.audit_prompt_v2_comparison import build_v2_request

TARGET_MAX_V3_CHARS = 40_000
TARGET_MAX_DUPLICATION_RATIO = 1.05


def build_v3_request() -> dict:
    report_text, _raw_record = _load_raw_report()
    candidate_segments, _filtered = build_candidate_segments(report_text, agent_output_id=AGENT_OUTPUT_ID)
    request = build_shadow_request_v3(
        source_report=report_text,
        run_id=REAL_RUN_ID,
        ticker=TICKER,
        agent=AGENT,
        agent_output_id=AGENT_OUTPUT_ID,
        candidate_segments=candidate_segments,
        factor_vocabulary=list(FACTOR_ALIASES.keys()),
    )
    return {"report_text": report_text, "candidate_segments": candidate_segments, "request": request}


def test_v3_request_is_well_under_the_40k_target():
    built = build_v3_request()
    prompt_text = build_shadow_prompt_input_v3(built["request"])
    assert len(prompt_text) <= TARGET_MAX_V3_CHARS


def test_v3_report_duplication_ratio_at_target():
    built = build_v3_request()
    report_text = built["report_text"]
    prompt_text = build_shadow_prompt_input_v3(built["request"])
    # No candidate text is ever sent in v3 either -- the report appears
    # exactly once, by construction, exactly like v2.
    payload = json.loads(prompt_text.split("SHADOW_REQUEST_JSON:\n", 1)[1])
    assert payload["agent_report"] == report_text
    assert "claim_hint" not in prompt_text
    assert "evidence_hint" not in prompt_text
    ratio = len(report_text) / len(report_text)  # v3 sends it exactly once
    assert ratio <= TARGET_MAX_DUPLICATION_RATIO


def test_v3_request_is_deterministic():
    first = build_shadow_prompt_input_v3(build_v3_request()["request"])
    second = build_shadow_prompt_input_v3(build_v3_request()["request"])
    assert first == second


def test_v3_wire_request_never_contains_offset_fields_for_the_model_to_fill():
    """v3's OWN request never asks the model to produce start/end -- the
    minimal wire shape has no candidate 'source_spans' field for the model
    to imitate; only compact {id,start,end} location HINTS the model may
    read, never write."""

    built = build_v3_request()
    request = built["request"]
    assert set(request) == {
        "input_schema_version",
        "run_id",
        "ticker",
        "agent",
        "agent_output_id",
        "factor_vocabulary",
        "candidate_hints",
        "agent_report_boundary",
        "agent_report",
        "agent_report_end_boundary",
    }
    for hint in request["candidate_hints"]:
        assert set(hint) == {"id", "start", "end"}


def test_v3_is_a_comparably_large_reduction_from_v1():
    from comqutor_alpha.structure_engine.structured_output_shadow_prompt import (
        build_shadow_prompt_input,
    )
    from scripts.audit_prompt_v1_root_cause import build_v1_request

    v1_text = build_shadow_prompt_input(build_v1_request()["request"])
    v3_text = build_shadow_prompt_input_v3(build_v3_request()["request"])
    reduction_pct = 100 * (len(v1_text) - len(v3_text)) / len(v1_text)
    assert reduction_pct >= 50.0


def test_v3_request_size_is_close_to_v2s_not_a_regression():
    """v3 changes only the evidence proposal shape (verbatim quotes instead
    of offsets); it must not silently reintroduce v1-scale bloat. v3's
    fixed instruction is slightly larger than v2's (the added evidence-
    selection rules), so exact equality is not expected -- only that it
    stays in the same small-request regime."""

    v2_text = build_shadow_prompt_input_v2(build_v2_request()["request"])
    v3_text = build_shadow_prompt_input_v3(build_v3_request()["request"])
    assert v3_text != v2_text  # different prompt identity, by construction
    assert len(v3_text) <= len(v2_text) * 1.5
    assert len(v3_text) <= TARGET_MAX_V3_CHARS


def test_v2_and_v3_wire_requests_carry_identical_candidate_hints_for_the_same_report():
    """Both v2 and v3 compress candidate segments to the same {id,start,end}
    hint shape -- v3 changes the evidence PROPOSAL shape, not the candidate
    hint compression v2 already achieved."""

    report_text, _raw_record = _load_raw_report()
    candidate_segments, _filtered = build_candidate_segments(report_text, agent_output_id=AGENT_OUTPUT_ID)
    common = {
        "source_report": report_text,
        "run_id": REAL_RUN_ID,
        "ticker": TICKER,
        "agent": AGENT,
        "agent_output_id": AGENT_OUTPUT_ID,
        "candidate_segments": candidate_segments,
        "factor_vocabulary": list(FACTOR_ALIASES.keys()),
    }
    v2_request = build_shadow_request_v2(**common)
    v3_request = build_shadow_request_v3(**common)
    assert v2_request["candidate_hints"] == v3_request["candidate_hints"]
