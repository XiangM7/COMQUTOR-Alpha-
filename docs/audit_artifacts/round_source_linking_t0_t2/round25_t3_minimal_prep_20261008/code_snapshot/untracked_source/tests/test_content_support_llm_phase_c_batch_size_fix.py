"""Round 10 (2026-10-06): fixed-response verification of the REAL Phase C
execution script's own path, after finding (via a real, paid execution)
that the script's attempt to force batch_size=1 by reassigning the
module's BATCH_SIZE attribute after import silently had no effect --
Python binds a function's own default-argument value once, at definition
time, so chunk_items(items, size: int = BATCH_SIZE) kept using the
original size=5 default regardless.

Every test here uses a REAL comqutor_alpha.structure_engine.week2_llm.
Week2LLMGateway (never a hand-rolled stand-in) wired to a fake underlying
model object -- the SAME real retry loop, real _reserve_call() budget
counter, and real invoke_json_with_trace/finalize_semantic_invocation
code paths the actual paid execution went through are genuinely exercised
here, with zero Provider calls (the fake model's own .invoke() never
makes a real HTTP request). This is exactly the fixed-response-at-the-
Provider-boundary-only pattern already established in
test_content_support_llm_production_wiring.py.
"""

from __future__ import annotations

import json

from comqutor_alpha.source_provenance import SOURCE_LINK_VALID
from comqutor_alpha.structure_engine.content_support_llm import (
    FALLBACK_BUDGET_EXHAUSTED,
    apply_llm_content_support_verification,
)
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway
from tests._content_support_v2_fixture_helpers import v2_response


class _Response:
    def __init__(self, content: str) -> None:
        self.content = content


class _AlwaysTruncatedModel:
    """Mirrors the REAL failure mode just observed: every real call hits
    the output cap before producing any JSON -- the gateway's own JSON
    parser fails, exactly reproducing WEEK2_LLM_INVALID_JSON/VALIDATION_
    FAILED-shaped rejections offline, at zero cost."""

    def __init__(self) -> None:
        self.calls = 0
        self.prompts_seen: list[str] = []

    def invoke(self, prompt: str) -> _Response:
        self.calls += 1
        self.prompts_seen.append(prompt)
        return _Response("{not valid json, truncated mid-stream")


class _AlwaysSupportsModel:
    def __init__(self) -> None:
        self.calls = 0
        self.prompts_seen: list[str] = []

    def invoke(self, prompt: str) -> _Response:
        self.calls += 1
        self.prompts_seen.append(prompt)
        payload = json.loads(prompt.split("\nINPUT_JSON:\n", 1)[1])
        items = []
        for item in payload["items"]:
            candidate = item["allowed_candidates"][0]
            items.append(
                v2_response(
                    claim_id=item["claim_id"],
                    status="SUPPORTS",
                    used_source_id=candidate["source_id"],
                    used_location="excerpt",
                    supporting_quote_or_data=candidate["excerpt"][:30],
                    supported_proposition=item["proposition"],
                )
            )
        return _Response(json.dumps({"items": items}))


def _real_gateway(model, *, max_calls: int, max_retries: int = 0) -> Week2LLMGateway:
    return Week2LLMGateway(
        model, run_id="phase-c-batch-fix-test", output_root="/tmp", timeout_seconds=5.0,
        max_retries=max_retries, max_calls=max_calls, provider="deepseek", model_name="deepseek-v4-flash",
    )


def _load_21_real_amd_claims() -> tuple[list[dict], list[dict]]:
    """The SAME 21 real, frozen AMD claims Phase C targets -- loaded from
    the already-saved, already-verified re-annotation artifact, never
    re-derived or swapped for synthetic ones."""
    reeval_dir = "outputs/runs/automated-eligibility-reeval-20261005T190101Z-d9b7fdba"
    claims_path = (
        "docs/audit_artifacts/round_source_linking_t0_t2/round9_llm_content_support_20261006"
        "/01_amd_21_analytical_claims_raw.json"
    )
    frozen_claims = json.loads(open(claims_path).read())
    structured = json.loads(open(f"{reeval_dir}/structured_agent_outputs.json").read())
    sources = json.loads(open(f"{reeval_dir}/source_registry.json").read())["sources"]
    structured_by_id = {r["claim_id"]: r for r in structured["records"]}
    records = [structured_by_id[c["claim_id"]] for c in frozen_claims]
    assert len(records) == 21
    assert all(r["source_link_status"] == SOURCE_LINK_VALID for r in records)
    return records, sources


def test_batch_size_one_produces_21_single_claim_requests_not_5():
    """Reproduces, at zero cost, the exact scenario the real paid execution
    hit -- but with the fix (explicit batch_size=1 parameter) applied, and
    confirms it actually changes real behavior this time."""
    records, sources = _load_21_real_amd_claims()
    model = _AlwaysTruncatedModel()
    gateway = _real_gateway(model, max_calls=21)

    updated_records, stats = apply_llm_content_support_verification(
        records, sources, llm_gateway=gateway, batch_size=1
    )

    assert stats.requested_count == 21
    assert stats.batch_count == 21, "batch_size=1 must produce 21 separate batches, not 5"
    assert model.calls == 21, "the real underlying model must be invoked 21 times, once per claim"
    for prompt in model.prompts_seen:
        payload = json.loads(prompt.split("\nINPUT_JSON:\n", 1)[1])
        assert len(payload["items"]) == 1, "each real request must serialize exactly one claim"


def test_chunk_items_own_default_is_bound_at_definition_time_not_read_live():
    """Isolates the real, language-level root cause directly on chunk_items
    itself (not through apply_llm_content_support_verification, whose body
    was just changed by this fix to always pass size=effective_batch_size
    explicitly -- which means a BATCH_SIZE mutation would now incidentally
    work even without the batch_size= parameter, and would therefore no
    longer reproduce the real historical bug if tested through that
    function). The real 03_phase_c_execution_script.py bug was calling
    chunk_items(items) with NO explicit size= argument at all, after
    reassigning csl_module.BATCH_SIZE = 1 -- chunk_items(items, size: int =
    BATCH_SIZE)'s default is evaluated ONCE, when the module is first
    imported, so that reassignment has no effect on it. This reproduces
    the real paid execution's exact observed batch shape: [5, 5, 5, 5, 1]
    for 21 items, even with BATCH_SIZE mutated to 1 beforehand."""
    import comqutor_alpha.structure_engine.content_support_llm as csl_module

    original = csl_module.BATCH_SIZE
    csl_module.BATCH_SIZE = 1
    try:
        items = list(range(21))
        batches = csl_module.chunk_items(items)  # no explicit size= -- the real historical bug shape
        assert [len(b) for b in batches] == [5, 5, 5, 5, 1], (
            "chunk_items' own default must remain bound to the ORIGINAL BATCH_SIZE=5 even after "
            "the module attribute is reassigned -- this is the real, language-level root cause, "
            "and it reproduces the real paid execution's exact 5/5/5/5/1 batch shape"
        )
    finally:
        csl_module.BATCH_SIZE = original


def test_candidate_scope_stays_within_the_single_claim_when_batch_size_one():
    """Each single-claim request's allowed_candidates must contain ONLY
    that claim's own linked source(s) -- never another claim's candidate
    bleeding in, confirmed directly from the real serialized request body."""
    records, sources = _load_21_real_amd_claims()
    model = _AlwaysTruncatedModel()
    gateway = _real_gateway(model, max_calls=21)
    apply_llm_content_support_verification(records, sources, llm_gateway=gateway, batch_size=1)

    records_by_id = {r["claim_id"]: r for r in records}
    for prompt in model.prompts_seen:
        payload = json.loads(prompt.split("\nINPUT_JSON:\n", 1)[1])
        item = payload["items"][0]
        own_record = records_by_id[item["claim_id"]]
        candidate_ids = {c["source_id"] for c in item["allowed_candidates"]}
        expected_ids = {own_record["linked_source_id"].split(":frag:")[0]}
        assert candidate_ids == expected_ids, (
            f"claim {item['claim_id']} got candidates {candidate_ids}, expected only its own {expected_ids}"
        )


def test_global_budget_cap_stops_sending_once_exhausted_real_gateway():
    """A real Week2LLMGateway with max_calls=5 and 21 batch_size=1 items
    must make EXACTLY 5 real .invoke() calls -- the remaining 16 get
    FALLBACK_BUDGET_EXHAUSTED without ever reaching the fake Provider
    boundary at all (proven by the model's own real call counter, not
    just the stats object)."""
    records, sources = _load_21_real_amd_claims()
    model = _AlwaysSupportsModel()
    gateway = _real_gateway(model, max_calls=5)

    updated_records, stats = apply_llm_content_support_verification(
        records, sources, llm_gateway=gateway, batch_size=1
    )

    assert model.calls == 5, "the real model must never be invoked more than the real max_calls budget"
    assert stats.fallback_reason_counts[FALLBACK_BUDGET_EXHAUSTED] == 16
    assert stats.llm_verified_count == 5


def test_max_retries_zero_means_exactly_one_real_attempt_per_claim():
    """A real Week2LLMGateway with max_retries=0, given a model that ALWAYS
    fails validation, must call .invoke() exactly ONCE per claim -- never
    retried -- confirmed by the real model's own call counter."""
    records, sources = _load_21_real_amd_claims()
    single_claim = records[:1]
    model = _AlwaysTruncatedModel()
    gateway = _real_gateway(model, max_calls=21, max_retries=0)

    apply_llm_content_support_verification(single_claim, sources, llm_gateway=gateway, batch_size=1)

    assert model.calls == 1, "max_retries=0 must mean exactly one real attempt, confirmed via the real Gateway's own retry loop"


def test_every_real_attempt_is_saved_independently_in_the_attempt_log():
    records, sources = _load_21_real_amd_claims()
    model = _AlwaysTruncatedModel()
    gateway = _real_gateway(model, max_calls=21)

    _, stats = apply_llm_content_support_verification(records, sources, llm_gateway=gateway, batch_size=1)

    assert len(stats.attempt_log) == 21
    for entry in stats.attempt_log:
        assert len(entry["claim_ids"]) == 1
        assert "request_control" in entry
        assert "provider_response_metadata" in entry
