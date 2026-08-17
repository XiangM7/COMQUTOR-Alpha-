from __future__ import annotations

from copy import deepcopy

import pytest

from comqutor_alpha.llm_runtime.contracts import (
    LLM_CACHE_ENTRY_SCHEMA_VERSION,
    cache_entry_from_record,
    redact_sensitive_text,
    validate_cache_entry,
    validate_semantic_call_record,
    validate_semantic_call_records,
)
from comqutor_alpha.llm_runtime.errors import ContractValidationError
from tests.llm_runtime.fakes import make_record


def assert_valid(record: dict[str, object]) -> None:
    result = validate_semantic_call_record(record)
    assert result.valid, result.to_dict()
    assert result.reason_codes == ()


def failure_record(provider_status: str, error_code: str) -> dict[str, object]:
    return make_record(
        provider_status=provider_status,
        validation_status="not_run",
        validated_output=None,
        raw_output_text=None,
        token_usage={"input_tokens": None, "output_tokens": None, "total_tokens": None},
        error_code=error_code,
        error_message="Provider operation failed safely",
    )


def test_valid_success_record() -> None:
    assert_valid(make_record())


def test_valid_cache_hit_record() -> None:
    record = make_record(
        provider_status="not_called",
        raw_output_text=None,
        token_usage={"input_tokens": None, "output_tokens": None, "total_tokens": None},
    )
    record["cache"] = {"cache_key": record["cache"]["cache_key"], "hit": True}
    assert_valid(record)


@pytest.mark.parametrize(
    ("provider_status", "error_code"),
    [("timeout", "PROVIDER_TIMEOUT"), ("provider_error", "PROVIDER_ERROR")],
)
def test_valid_provider_failure_record(provider_status: str, error_code: str) -> None:
    assert_valid(failure_record(provider_status, error_code))


def test_valid_accepted_fallback_record() -> None:
    assert_valid(
        make_record(
            provider_status="timeout",
            raw_output_text=None,
            token_usage={"input_tokens": None, "output_tokens": None, "total_tokens": None},
            fallback_used=True,
            fallback_reason="safe deterministic fallback",
            error_code="PROVIDER_TIMEOUT",
            error_message="Provider timed out",
        )
    )


def test_timestamp_order_is_rejected() -> None:
    result = validate_semantic_call_record(
        make_record(
            started_at="2026-01-01T00:00:01+00:00",
            completed_at="2026-01-01T00:00:00+00:00",
        )
    )
    assert "SEMANTIC_TIMESTAMP_ORDER_INVALID" in result.reason_codes


@pytest.mark.parametrize(
    ("field", "value", "reason_code"),
    [
        ("latency_ms", -1, "SEMANTIC_LATENCY_INVALID"),
        ("retry_count", -1, "SEMANTIC_RETRY_COUNT_INVALID"),
    ],
)
def test_negative_scalar_is_rejected(field: str, value: int, reason_code: str) -> None:
    record = make_record()
    record[field] = value
    assert reason_code in validate_semantic_call_record(record).reason_codes


def test_negative_token_is_rejected() -> None:
    record = make_record()
    record["token_usage"] = {"input_tokens": -1, "output_tokens": 2, "total_tokens": 1}
    assert "SEMANTIC_TOKEN_COUNT_INVALID" in validate_semantic_call_record(record).reason_codes


def test_accepted_record_requires_validated_output() -> None:
    result = validate_semantic_call_record(make_record(validated_output=None))
    assert "SEMANTIC_ACCEPTED_OUTPUT_MISSING" in result.reason_codes


@pytest.mark.parametrize(
    ("field", "reason_code"),
    [
        ("input_sha256", "SEMANTIC_INPUT_HASH_MISMATCH"),
        ("raw_output_sha256", "SEMANTIC_RAW_OUTPUT_HASH_MISMATCH"),
        ("validated_output_sha256", "SEMANTIC_VALIDATED_OUTPUT_HASH_MISMATCH"),
    ],
)
def test_hash_mismatch_is_rejected(field: str, reason_code: str) -> None:
    record = make_record()
    record[field] = "0" * 64
    assert reason_code in validate_semantic_call_record(record).reason_codes


def test_secret_and_home_path_redaction() -> None:
    raw = "Authorization: Bearer sk-supersecret at /Users/alice/private/file.txt"
    redacted = redact_sensitive_text(raw)
    assert "supersecret" not in redacted
    assert "/Users/alice" not in redacted
    assert "[REDACTED" in redacted

    record = failure_record("provider_error", "PROVIDER_ERROR")
    record["error_message"] = raw
    result = validate_semantic_call_record(record)
    assert "SEMANTIC_ERROR_MESSAGE_NOT_REDACTED" in result.reason_codes


def test_secret_field_in_payload_is_rejected() -> None:
    record = make_record(input_payload={"api_key": "hidden", "ticker": "AAPL"})
    assert "SEMANTIC_SECRET_FIELD_FORBIDDEN" in validate_semantic_call_record(record).reason_codes


def test_collection_rejects_duplicate_ids_and_non_monotonic_sequence() -> None:
    records = [make_record(), make_record(call_sequence=0)]
    result = validate_semantic_call_records(records)
    assert "SEMANTIC_DUPLICATE_CALL_ID" in result.reason_codes
    assert "SEMANTIC_CALL_SEQUENCE_NOT_MONOTONIC" in result.reason_codes


def test_cache_entry_only_from_eligible_record() -> None:
    entry = cache_entry_from_record(
        make_record(),
        created_at="2026-01-01T00:00:01+00:00",
        source_run_id="run-test",
    )
    assert entry.schema_version == LLM_CACHE_ENTRY_SCHEMA_VERSION
    assert validate_cache_entry(entry).valid
    assert "run_id" not in entry.to_dict()

    rejected = failure_record("provider_error", "PROVIDER_ERROR")
    with pytest.raises(ContractValidationError) as caught:
        cache_entry_from_record(rejected, created_at="2026-01-01T00:00:01+00:00")
    assert caught.value.reason_code == "CACHE_ENTRY_SOURCE_NOT_ELIGIBLE"


def test_cache_entry_rejects_tampered_output() -> None:
    entry = cache_entry_from_record(
        make_record(),
        created_at="2026-01-01T00:00:01+00:00",
    ).to_dict()
    tampered = deepcopy(entry)
    tampered["validated_output"] = {"claims": ["tampered"]}
    assert "CACHE_ENTRY_OUTPUT_HASH_MISMATCH" in validate_cache_entry(tampered).reason_codes
