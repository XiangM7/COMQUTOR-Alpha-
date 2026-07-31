import json

import pytest

from comqutor_alpha.adapters.tradingagents_output_writer import build_raw_agent_output_record
from comqutor_alpha.structure_engine.claim_quality import (
    CONSUMER_ACTIVATION,
    CONSUMER_ANALYTICAL_PERSISTENCE,
    CONSUMER_CONFLICT,
    CONSUMER_MAPPING,
    CONSUMER_PRODUCT_FINDINGS,
    CONSUMER_STRUCTURE,
    is_claim_eligible,
)
from comqutor_alpha.structure_engine.structure_extractor import build_extracted_structures_payload
from comqutor_alpha.structure_engine.structured_output_adapter import (
    FILTER_REASON_BOILERPLATE,
    LLM_CLAIM_BATCH_SIZE,
    SCHEMA_VERSION,
    _error_payload,
    _new_quality_audit,
    _validate_llm_batch_enrichment,
    adapt_raw_agent_output,
    adapt_raw_agent_outputs,
    dedupe_structured_records,
    extract_claim_segments_with_audit,
    safe_default_record,
    save_structured_agent_outputs,
    validate_structured_output,
)


def test_empty_raw_output_returns_safe_default():
    record = adapt_raw_agent_output({"agent": "news_agent", "raw_output": ""}, "run1", "NVDA")
    assert record["claim"] == "unknown"
    assert record["direction"] == "unknown"
    assert record["confidence"] == 0.0


def test_nvda_ai_text_extracts_factors_and_source_type():
    text = "NVDA AI demand and GPU demand are rising as datacenter capex increases."
    record = adapt_raw_agent_output({"agent": "technical_agent", "raw_output": text}, "run1", "NVDA")
    assert "AI Demand" in record["factors"]
    assert "GPU Demand" in record["factors"]
    assert "Datacenter CapEx" in record["factors"]
    assert record["source_type"] == "technical"


@pytest.mark.parametrize(
    "confidence",
    [True, "0.8", float("nan"), float("inf"), -0.01, 1.01],
)
def test_structured_output_rejects_non_numeric_or_invalid_confidence(confidence):
    record = adapt_raw_agent_output(
        {"agent": "news_agent", "raw_output": "AI demand supports GPU demand."},
        "run1",
        "NVDA",
    )
    record["confidence"] = confidence

    assert validate_structured_output(record) is False


@pytest.mark.parametrize("confidence", [0, 0.5, 1])
def test_structured_output_accepts_finite_numeric_confidence(confidence):
    record = adapt_raw_agent_output(
        {"agent": "news_agent", "raw_output": "AI demand supports GPU demand."},
        "run1",
        "NVDA",
    )
    record["confidence"] = confidence

    assert validate_structured_output(record) is True


@pytest.mark.parametrize("confidence", [True, "0.8", float("nan"), float("inf"), 1.01])
def test_llm_batch_enrichment_rejects_invalid_confidence(confidence):
    raw_text = "AI demand supports GPU demand."
    batch_segments = [{"segment_id": "seg-1", "claim": raw_text, "evidence": raw_text, "source_section": None}]
    payload = {
        "claims": [
            {
                "segment_id": "seg-1",
                "claim": raw_text,
                "evidence": raw_text,
                "entities": ["NVDA"],
                "factors": ["AI Demand", "GPU Demand"],
                "direction": "bullish",
                "confidence": confidence,
                "source_section": None,
            }
        ]
    }

    with pytest.raises(ValueError, match="confidence"):
        _validate_llm_batch_enrichment(payload, batch_segments)


def _raw_record(raw_output, agent="news_agent"):
    return build_raw_agent_output_record(
        run_id="run1",
        ticker="NVDA",
        agent=agent,
        tradingagents_agent="News Analyst",
        source_field="news_report",
        source_path="news_report",
        source_candidates=["news_report"],
        raw_value=raw_output,
        created_at="2026-07-01T00:00:00Z",
    )


def test_structured_record_traces_back_to_raw_agent_output_id():
    raw_record = _raw_record("AI demand supports GPU demand and datacenter capex.")

    structured = adapt_raw_agent_output(raw_record, "run1", "NVDA")

    assert structured["claim_id"] == f"{raw_record['agent_output_id']}:claim:1"
    assert structured["agent_output_id"] == structured["claim_id"]
    assert structured["claim_id"] != raw_record["agent_output_id"]
    assert structured["source_agent_output_id"] == raw_record["agent_output_id"]
    assert structured["source_refs"] == [raw_record["agent_output_id"]]


def test_safe_default_record_preserves_traceability_for_empty_raw_output():
    raw_record = _raw_record("")

    structured = adapt_raw_agent_output(raw_record, "run1", "NVDA")

    assert structured["claim"] == "unknown"
    assert structured["adapter_warning"] == "raw output is empty"
    assert structured["claim_id"] == f"{raw_record['agent_output_id']}:claim:1"
    assert structured["source_agent_output_id"] == raw_record["agent_output_id"]
    assert structured["source_refs"] == [raw_record["agent_output_id"]]


def test_safe_default_record_has_no_traceability_when_raw_row_is_invalid():
    structured = adapt_raw_agent_output("not-a-mapping", "run1", "NVDA")

    assert structured["adapter_warning"] == "raw row is not an object"
    assert structured["source_refs"] == []
    assert structured["source_agent_output_id"] is None
    assert structured["claim_id"] == "unknown_agent_default:claim:1"


def test_adapter_writes_file_and_logs_invalid_rows(tmp_path):
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    (run_dir / "raw_agent_outputs.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "ticker": "NVDA",
                "agent_outputs": [
                    {"agent": "news_agent", "raw_output": "AI demand supports GPU demand."},
                    {"agent": "fundamental_agent", "raw_output": ""},
                ],
            }
        )
    )
    path = save_structured_agent_outputs(run_dir)
    assert path.exists()
    payload = json.loads(path.read_text())
    assert payload["schema_version"] == SCHEMA_VERSION
    assert SCHEMA_VERSION == "week1a.structured_agent_outputs.v2"
    assert len(payload["records"]) == 2
    log_path = run_dir / "error_logs" / "structured_output_adapter_errors.jsonl"
    assert log_path.exists()

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert entries[0]["run_id"] == "run1"
    assert entries[0]["ticker"] == "NVDA"
    assert entries[0]["agent"] == "fundamental_agent"
    assert entries[0]["error_code"] == "EMPTY_RAW_OUTPUT"
    assert "raw_preview" in entries[0]
    assert "record_preview" in entries[0]
    assert str(tmp_path) not in json.dumps(entries[0])


def test_error_log_redacts_secret_like_tokens_from_previews():
    raw_record = {
        "agent": "news_agent",
        "raw_output": "Leaked credential api_key=sk-testsecret123 in the report.",
    }
    structured_record = safe_default_record(
        "run1",
        "NVDA",
        "news_agent",
        raw_record["raw_output"],
        "structured record failed validation",
        error_code="STRUCTURED_VALIDATION_FAILED",
    )

    payload = _error_payload("run1", "NVDA", raw_record, structured_record)

    assert "sk-testsecret123" not in json.dumps(payload)
    assert "api_key=[REDACTED]" in payload["raw_preview"]


def test_error_log_redacts_quoted_json_style_secrets_from_previews():
    """raw_record is a dict, so _safe_preview() serializes it with json.dumps(),
    which double-quotes both keys and values (e.g. `"token": "abcdef123456"`).
    The plain key=value redaction pattern cannot match through that extra
    quoting, so the JSON-aware pattern must catch it instead.
    """
    raw_record = {
        "agent": "news_agent",
        "raw_output": "Some innocuous claim text.",
        "api_key": "sk-jsonstyle123",
        "token": "abcdef123456",
        "password": "hunter2",
        "secret": "topsecret",
    }
    structured_record = safe_default_record(
        "run1",
        "NVDA",
        "news_agent",
        raw_record["raw_output"],
        "structured record failed validation",
        error_code="STRUCTURED_VALIDATION_FAILED",
    )

    payload = _error_payload("run1", "NVDA", raw_record, structured_record)
    serialized = json.dumps(payload)

    assert "sk-jsonstyle123" not in serialized
    assert "abcdef123456" not in serialized
    assert "hunter2" not in serialized
    assert "topsecret" not in serialized
    assert '"api_key": "[REDACTED]"' in payload["raw_preview"]
    assert '"token": "[REDACTED]"' in payload["raw_preview"]
    assert '"password": "[REDACTED]"' in payload["raw_preview"]
    assert '"secret": "[REDACTED]"' in payload["raw_preview"]


def test_malformed_raw_record_does_not_crash_full_run(tmp_path):
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    (run_dir / "raw_agent_outputs.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "ticker": "NVDA",
                "agent_outputs": [
                    "not-a-mapping",
                    {"agent": "news_agent", "raw_output": "AI demand drives GPU demand."},
                ],
            }
        ),
        encoding="utf-8",
    )

    path = save_structured_agent_outputs(run_dir)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert len(payload["records"]) == 2
    assert payload["records"][0]["adapter_error_code"] == "INVALID_RAW_RECORD"
    assert payload["records"][1]["claim"] != "unknown"


def test_long_markdown_report_splits_into_traceable_claims():
    report = """# NVDA Outlook

## Demand
- AI training demand is accelerating and GPU demand is rising.
- Datacenter power and cooling spending supports infrastructure growth.

| Metric | Change |
| --- | --- |
| Revenue | +20% |

Disclaimer: This report is not investment advice.

## Risk
Custom silicon could reduce NVIDIA dependency over time.
"""
    raw_record = _raw_record(report)

    records = adapt_raw_agent_outputs(raw_record, "run1", "NVDA")

    # 2 bullet claims + 1 table data-row claim + 1 Risk-section claim. The
    # separator row and the header row (Section D) never become claims of
    # their own -- only the genuine data row does.
    assert len(records) == 4
    assert len({record["claim_id"] for record in records}) == 4
    assert {record["source_section"] for record in records} == {"Demand", "Risk"}
    assert all(record["source_agent_output_id"] == raw_record["agent_output_id"] for record in records)
    assert all(record["source_refs"] == [raw_record["agent_output_id"]] for record in records)
    serialized = json.dumps(records).lower()
    assert "disclaimer" not in serialized
    table_claim = next(r for r in records if "revenue" in r["claim"].lower())
    assert "Metric: Revenue" in table_claim["claim"]
    assert "Change: +20%" in table_claim["claim"]
    assert "---" not in serialized


def test_legacy_raw_record_without_agent_output_id_still_adapts():
    records = adapt_raw_agent_outputs(
        {
            "agent": "news_agent",
            "raw_output": "AI demand is increasing and GPU demand is rising.",
        },
        "run1",
        "NVDA",
    )

    assert len(records) == 1
    assert records[0]["agent_output_id"].startswith("news_agent_")
    assert records[0]["source_agent_output_id"].startswith("news_agent_")
    assert records[0]["claim_id"].endswith(":claim:1")
    assert records[0]["claim_id"] != records[0]["source_agent_output_id"]


# ---------------------------------------------------------------------------
# Unified Claim Admissibility and Context-Only Routing Sprint
# ---------------------------------------------------------------------------


class _FakeBatchLLMGateway:
    """Stand-in for the real LLM gateway under the Complete Claim Coverage
    Sprint's claim-batch-enrichment contract: one pre-baked response is
    consumed per ``invoke_json`` call, in order (one call per batch) --
    mirroring the real gateway's contract that a validator raising
    ValueError, or a ``None`` response, yields ``None`` (never an exception
    escaping to the caller). Once ``responses`` is exhausted, further calls
    return ``None`` (simulating retries/budget exhaustion)."""

    def __init__(self, responses):
        self._responses = list(responses)
        self._call_index = 0

    def invoke_json(self, _kind, _request, validator):
        if self._call_index >= len(self._responses):
            return None
        payload = self._responses[self._call_index]
        self._call_index += 1
        if payload is None:
            return None
        try:
            return validator(payload)
        except ValueError:
            return None


def _segments_with_ids(raw_record, raw_text):
    """Deterministically segment ``raw_text`` and attach the exact
    ``segment_id`` values ``adapt_raw_agent_outputs`` itself would assign,
    given ``raw_record["agent_output_id"]`` -- lets a test build a fake LLM
    response that is valid (or deliberately invalid) against the real
    segment IDs without needing to run the adapter first."""
    segments, _filtered = extract_claim_segments_with_audit(raw_text)
    source_agent_output_id = str(raw_record["agent_output_id"])
    for segment in segments:
        segment["segment_id"] = f"{source_agent_output_id}:segment:{segment['segment_index']}"
    return segments


def _valid_enrichment_payload(segments, *, direction="unknown", confidence=0.8):
    """A batch-enrichment response that echoes every input segment's own
    claim/evidence/source_section back verbatim (as the contract requires)
    while adding the given direction/confidence."""
    return {
        "claims": [
            {
                "segment_id": segment["segment_id"],
                "claim": segment["claim"],
                "evidence": segment["evidence"],
                "source_section": segment["source_section"],
                "entities": [],
                "factors": [],
                "direction": direction,
                "confidence": confidence,
            }
            for segment in segments
        ]
    }


def test_deterministic_and_llm_paths_agree_on_quality_class_for_the_same_sentence():
    text = "Revenue declined 12% year over year."
    raw_record = {"agent": "news_agent", "raw_output": text, "agent_output_id": "news_agent_agree_test"}

    deterministic_records = adapt_raw_agent_outputs(raw_record, "run1", "NVDA")
    segments = _segments_with_ids(raw_record, text)
    llm_gateway = _FakeBatchLLMGateway([_valid_enrichment_payload(segments, direction="negative")])
    llm_records = adapt_raw_agent_outputs(raw_record, "run1", "NVDA", llm_gateway=llm_gateway)

    assert len(deterministic_records) == 1
    assert len(llm_records) == 1
    assert deterministic_records[0]["claim_quality"] == "analytical"
    assert llm_records[0]["claim_quality"] == "analytical"
    assert llm_records[0]["extraction_method"] == "llm_strict_json"
    assert llm_records[0]["direction"] == "negative"


def test_llm_path_never_receives_boilerplate_meta_commentary_segments():
    """Boundary filtering (Section B/C) happens once, in deterministic
    segmentation, before any batch is ever built -- the LLM enrichment step
    only ever sees real candidate segments, never boilerplate/disclaimer/
    transition sentences (those are still recorded in ``filter_audit`` with
    a stable reason code, exactly as the pure-deterministic path records
    them)."""
    real = "Revenue declined 12% year over year."
    meta = "Let me synthesize everything."
    raw_record = {"agent": "news_agent", "raw_output": f"{real} {meta}", "agent_output_id": "news_agent_meta_test"}
    quality_audit = _new_quality_audit()
    filter_audit: list[dict] = []

    segments = _segments_with_ids(raw_record, f"{real} {meta}")
    assert len(segments) == 1
    assert segments[0]["claim"] == real

    llm_gateway = _FakeBatchLLMGateway([_valid_enrichment_payload(segments, direction="negative")])
    records = adapt_raw_agent_outputs(
        raw_record,
        "run1",
        "NVDA",
        llm_gateway=llm_gateway,
        filter_audit=filter_audit,
        quality_audit=quality_audit,
    )

    assert len(records) == 1
    assert records[0]["claim"] == real
    assert records[0]["claim_quality"] == "analytical"
    assert records[0]["extraction_method"] == "llm_strict_json"
    assert quality_audit["llm_claims_proposed_count"] == 1
    assert quality_audit["llm_claims_removed_count"] == 0
    assert len(filter_audit) == 1
    assert filter_audit[0]["reason_code"] == FILTER_REASON_BOILERPLATE


def test_llm_batch_validation_failure_recovers_the_real_claim_via_deterministic_fallback():
    real = "Revenue declined 12% year over year."
    raw_record = {"agent": "news_agent", "raw_output": real, "agent_output_id": "news_agent_fallback_test"}
    quality_audit = _new_quality_audit()
    # Structurally invalid: wrong claims count (0 vs. the 1 input segment).
    llm_gateway = _FakeBatchLLMGateway([{"claims": []}])

    records = adapt_raw_agent_outputs(
        raw_record, "run1", "NVDA", llm_gateway=llm_gateway, quality_audit=quality_audit
    )

    assert len(records) == 1
    assert records[0]["claim"] == real
    assert records[0]["claim_quality"] == "analytical"
    assert records[0]["extraction_method"] == "deterministic_splitter"
    assert quality_audit["llm_batch_count"] == 1
    assert quality_audit["llm_batch_fallback_count"] == 1


def test_audit_counts_match_real_removals_across_a_full_run(tmp_path):
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    (run_dir / "raw_agent_outputs.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "ticker": "NVDA",
                "agent_outputs": [
                    {
                        "agent": "news_agent",
                        "raw_output": (
                            "Revenue declined 12% year over year. "
                            "The company introduced a new HBM product. "
                            "Let me synthesize everything."
                        ),
                    }
                ],
            }
        )
    )
    path = save_structured_agent_outputs(run_dir)
    payload = json.loads(path.read_text())
    metadata = payload["metadata"]
    records = payload["records"]

    assert len(records) == 2
    analytical = [r for r in records if r["claim_quality"] == "analytical"]
    context_only = [r for r in records if r["claim_quality"] == "context_only"]
    assert len(analytical) == 1
    assert len(context_only) == 1
    assert metadata["analytical_claim_count"] == len(analytical)
    assert metadata["context_only_claim_count"] == len(context_only)
    # The boilerplate sentence never became a segment at all (filtered at
    # the earlier sentence-boundary), so it is counted there, not as a
    # quality-gate removal -- the two counters must never double-count the
    # same removed sentence.
    assert metadata["boilerplate_removed_count"] == 1
    assert metadata["non_substantive_removed_count"] == 0


def test_safe_default_unknown_record_is_ineligible_for_every_consumer():
    record = safe_default_record(
        "run1", "NVDA", "news_agent", "", "raw output is empty", error_code="EMPTY_RAW_OUTPUT"
    )

    assert record["claim_quality"] == "non_substantive"
    assert record["analysis_eligible"] is False
    for consumer in (
        CONSUMER_MAPPING,
        CONSUMER_STRUCTURE,
        CONSUMER_ACTIVATION,
        CONSUMER_CONFLICT,
        CONSUMER_PRODUCT_FINDINGS,
        CONSUMER_ANALYTICAL_PERSISTENCE,
    ):
        assert is_claim_eligible(record, consumer) is False


# ---------------------------------------------------------------------------
# Complete Claim Coverage + Directional Findings UI Sprint
# ---------------------------------------------------------------------------


def _two_hundred_substantive_sentences():
    return [
        f"Revenue metric number {i} increased by {i} percent this quarter." for i in range(1, 201)
    ]


def test_two_hundred_substantive_sentences_are_all_retained():
    sentences = _two_hundred_substantive_sentences()
    records = adapt_raw_agent_outputs(
        {"agent": "news_agent", "raw_output": " ".join(sentences)}, "run1", "NVDA"
    )

    assert len(records) == 200
    assert all(record["claim_quality"] == "analytical" for record in records)


def test_the_sixty_fifth_sentence_forms_its_own_claim():
    sentences = _two_hundred_substantive_sentences()
    records = adapt_raw_agent_outputs(
        {"agent": "news_agent", "raw_output": " ".join(sentences)}, "run1", "NVDA"
    )

    assert records[64]["claim"] == sentences[64]
    assert records[64]["claim_index"] == 64
    assert records[64]["claim_id"].endswith(":claim:65")


def test_the_one_hundredth_sentence_forms_its_own_claim():
    sentences = _two_hundred_substantive_sentences()
    records = adapt_raw_agent_outputs(
        {"agent": "news_agent", "raw_output": " ".join(sentences)}, "run1", "NVDA"
    )

    assert records[99]["claim"] == sentences[99]
    assert records[99]["claim_index"] == 99
    assert records[99]["claim_id"].endswith(":claim:100")


def test_the_two_hundredth_sentence_forms_its_own_claim():
    sentences = _two_hundred_substantive_sentences()
    records = adapt_raw_agent_outputs(
        {"agent": "news_agent", "raw_output": " ".join(sentences)}, "run1", "NVDA"
    )

    assert records[199]["claim"] == sentences[199]
    assert records[199]["claim_index"] == 199
    assert records[199]["claim_id"].endswith(":claim:200")


def test_direction_unknown_causal_sentence_at_position_150_enters_structure_extractor_and_forms_an_edge():
    causal = "AI CapEx drives Semiconductor Cycle."
    sentences = _two_hundred_substantive_sentences()
    sentences[149] = causal
    records = adapt_raw_agent_outputs(
        {"agent": "news_agent", "raw_output": " ".join(sentences)}, "run1", "NVDA"
    )

    target = records[149]
    assert target["claim"] == causal
    assert target["direction"] == "unknown"
    assert target["claim_quality"] == "analytical"

    structured_payload = {"run_id": "run1", "ticker": "NVDA", "records": records}
    extracted = build_extracted_structures_payload(structured_payload)

    assert any(
        edge["source"] == "ai_capex"
        and edge["target"] == "semiconductor_cycle"
        and edge["source_record_id"] == target["claim_id"]
        for edge in extracted["edges"]
    )


def test_direction_unknown_analytical_claim_is_not_excluded_from_graph_consumers():
    record = adapt_raw_agent_output(
        {"agent": "news_agent", "raw_output": "AI CapEx drives Semiconductor Cycle."}, "run1", "NVDA"
    )

    assert record["direction"] == "unknown"
    assert record["claim_quality"] == "analytical"
    assert is_claim_eligible(record, CONSUMER_STRUCTURE, has_relation_candidate=True) is True
    assert is_claim_eligible(record, CONSUMER_ACTIVATION) is True


def test_multiple_llm_batches_merge_completely_and_in_order():
    sentences = [
        f"Revenue metric number {i} increased by {i} percent this quarter." for i in range(1, 141)
    ]
    raw_text = " ".join(sentences)
    raw_record = {"agent": "news_agent", "raw_output": raw_text, "agent_output_id": "news_agent_batch_test"}
    segments = _segments_with_ids(raw_record, raw_text)
    assert len(segments) == 140
    batches = [segments[i : i + LLM_CLAIM_BATCH_SIZE] for i in range(0, len(segments), LLM_CLAIM_BATCH_SIZE)]
    assert len(batches) == 3

    llm_gateway = _FakeBatchLLMGateway(
        [_valid_enrichment_payload(batch, direction="positive") for batch in batches]
    )
    records = adapt_raw_agent_outputs(raw_record, "run1", "NVDA", llm_gateway=llm_gateway)

    assert len(records) == 140
    assert [record["claim_index"] for record in records] == list(range(140))
    assert all(record["extraction_method"] == "llm_strict_json" for record in records)
    assert all(record["direction"] == "positive" for record in records)


def test_second_batch_failure_only_falls_back_that_batch_others_keep_llm_enrichment():
    sentences = [
        f"Revenue metric number {i} increased by {i} percent this quarter." for i in range(1, 141)
    ]
    raw_text = " ".join(sentences)
    raw_record = {"agent": "news_agent", "raw_output": raw_text, "agent_output_id": "news_agent_batch_test"}
    segments = _segments_with_ids(raw_record, raw_text)
    batches = [segments[i : i + LLM_CLAIM_BATCH_SIZE] for i in range(0, len(segments), LLM_CLAIM_BATCH_SIZE)]
    assert len(batches) == 3

    llm_gateway = _FakeBatchLLMGateway(
        [
            _valid_enrichment_payload(batches[0], direction="positive"),
            {"claims": []},  # batch 2: structurally invalid -> falls back alone
            _valid_enrichment_payload(batches[2], direction="positive"),
        ]
    )
    records = adapt_raw_agent_outputs(raw_record, "run1", "NVDA", llm_gateway=llm_gateway)

    # Total claim count is unaffected by the middle batch's fallback.
    assert len(records) == 140
    by_index = {record["claim_index"]: record for record in records}
    assert all(by_index[i]["extraction_method"] == "llm_strict_json" for i in range(0, 64))
    assert all(by_index[i]["extraction_method"] == "deterministic_splitter" for i in range(64, 128))
    assert all(by_index[i]["extraction_method"] == "llm_strict_json" for i in range(128, 140))


def test_llm_omitting_a_segment_falls_back_the_whole_batch():
    sentences = ["Revenue increased 10 percent this quarter.", "GPU demand is rising sharply this year."]
    raw_text = " ".join(sentences)
    raw_record = {"agent": "news_agent", "raw_output": raw_text, "agent_output_id": "news_agent_omit_test"}
    segments = _segments_with_ids(raw_record, raw_text)
    assert len(segments) == 2

    # Only enriches the first segment -- omits the second entirely.
    llm_gateway = _FakeBatchLLMGateway([_valid_enrichment_payload(segments[:1])])
    records = adapt_raw_agent_outputs(raw_record, "run1", "NVDA", llm_gateway=llm_gateway)

    assert len(records) == 2
    assert all(record["extraction_method"] == "deterministic_splitter" for record in records)
    assert [record["claim"] for record in records] == sentences


def test_llm_merging_two_segments_into_one_falls_back_the_whole_batch():
    sentences = ["Revenue increased 10 percent this quarter.", "GPU demand is rising sharply this year."]
    raw_text = " ".join(sentences)
    raw_record = {"agent": "news_agent", "raw_output": raw_text, "agent_output_id": "news_agent_merge_test"}
    segments = _segments_with_ids(raw_record, raw_text)
    merged_claim_text = f"{segments[0]['claim']} {segments[1]['claim']}"

    payload = {
        "claims": [
            {
                "segment_id": segments[0]["segment_id"],
                "claim": merged_claim_text,
                "evidence": merged_claim_text,
                "source_section": segments[0]["source_section"],
                "entities": [],
                "factors": [],
                "direction": "unknown",
                "confidence": 0.5,
            },
            {
                "segment_id": segments[1]["segment_id"],
                "claim": segments[1]["claim"],
                "evidence": segments[1]["evidence"],
                "source_section": segments[1]["source_section"],
                "entities": [],
                "factors": [],
                "direction": "unknown",
                "confidence": 0.5,
            },
        ]
    }
    llm_gateway = _FakeBatchLLMGateway([payload])
    records = adapt_raw_agent_outputs(raw_record, "run1", "NVDA", llm_gateway=llm_gateway)

    assert len(records) == 2
    assert all(record["extraction_method"] == "deterministic_splitter" for record in records)
    assert [record["claim"] for record in records] == sentences


def test_llm_rewriting_evidence_falls_back_the_whole_batch():
    text = "Revenue increased 10 percent this quarter."
    raw_record = {"agent": "news_agent", "raw_output": text, "agent_output_id": "news_agent_rewrite_test"}
    segments = _segments_with_ids(raw_record, text)
    assert len(segments) == 1

    payload = _valid_enrichment_payload(segments)
    payload["claims"][0]["evidence"] = "Revenue increased by a lot this quarter."
    llm_gateway = _FakeBatchLLMGateway([payload])
    records = adapt_raw_agent_outputs(raw_record, "run1", "NVDA", llm_gateway=llm_gateway)

    assert len(records) == 1
    assert records[0]["extraction_method"] == "deterministic_splitter"
    assert records[0]["evidence"] == text


def test_table_data_row_is_retained_as_a_traceable_claim():
    report = "| Metric | Change |\n| --- | --- |\n| Revenue | +20% |\n"
    records = adapt_raw_agent_outputs({"agent": "news_agent", "raw_output": report}, "run1", "NVDA")

    assert len(records) == 1
    assert "Metric: Revenue" in records[0]["claim"]
    assert "Change: +20%" in records[0]["claim"]


def test_table_separator_row_is_ignored():
    report = "| Metric | Change |\n| --- | --- |\n| Revenue | +20% |\n"
    records = adapt_raw_agent_outputs({"agent": "news_agent", "raw_output": report}, "run1", "NVDA")

    serialized = json.dumps([record["claim"] for record in records])
    assert "---" not in serialized


def test_table_header_row_is_not_its_own_substantive_claim():
    report = "| Metric | Change |\n| --- | --- |\n| Revenue | +20% |\n"
    records = adapt_raw_agent_outputs({"agent": "news_agent", "raw_output": report}, "run1", "NVDA")

    claims = [record["claim"].strip() for record in records]
    assert "Metric | Change" not in claims
    assert "Metric" not in claims
    assert "Change" not in claims


def test_metadata_reports_zero_truncation_and_full_coverage_for_a_long_report(tmp_path):
    sentences = [
        f"Revenue metric number {i} increased by {i} percent this quarter." for i in range(1, 141)
    ]
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    (run_dir / "raw_agent_outputs.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "ticker": "NVDA",
                "agent_outputs": [{"agent": "news_agent", "raw_output": " ".join(sentences)}],
            }
        )
    )
    path = save_structured_agent_outputs(run_dir)
    metadata = json.loads(path.read_text())["metadata"]

    assert metadata["truncated_claim_count"] == 0
    assert metadata["coverage_complete"] is True
    assert metadata["candidate_segment_count"] == 140
    assert metadata["retained_claim_count"] == 140
    assert len(metadata["agent_coverage"]) == 1
    agent_row = metadata["agent_coverage"][0]
    assert agent_row["agent"] == "news_agent"
    assert agent_row["raw_output_count"] == 1
    assert agent_row["candidate_segment_count"] == 140
    assert agent_row["retained_claim_count"] == 140
    assert agent_row["truncated_claim_count"] == 0
    assert agent_row["coverage_complete"] is True


def test_dedupe_behavior_is_unchanged_by_the_new_segmentation_path():
    text = "Revenue declined 12 percent year over year. Revenue declined 12 percent year over year."
    records = adapt_raw_agent_outputs({"agent": "news_agent", "raw_output": text}, "run1", "NVDA")

    assert len(records) == 2
    deduped, removed = dedupe_structured_records(records)
    assert removed == 1
    assert len(deduped) == 1


def test_original_claim_order_is_preserved_end_to_end():
    sentences = [
        "Revenue increased 5 percent this quarter.",
        "GPU demand is rising sharply this year.",
        "AI CapEx spending grew substantially in the period.",
    ]
    records = adapt_raw_agent_outputs(
        {"agent": "news_agent", "raw_output": " ".join(sentences)}, "run1", "NVDA"
    )

    assert [record["claim"] for record in records] == sentences
    assert [record["claim_index"] for record in records] == [0, 1, 2]
