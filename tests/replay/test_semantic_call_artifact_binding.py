from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from comqutor_alpha.llm_runtime.canonical_json import sha256_canonical_json
from comqutor_alpha.replay.semantic_binding import (
    build_semantic_binding_audit,
    verify_semantic_bindings,
)
from comqutor_alpha.replay.source_bundle import (
    EXACT_REPLAY_SEMANTIC_BINDING_MISSING,
    EXACT_REPLAY_SEMANTIC_CALL_AMBIGUOUS,
    EXACT_REPLAY_SEMANTIC_INPUT_MISMATCH,
    EXACT_REPLAY_SEMANTIC_OUTPUT_MISMATCH,
    EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH,
    ExactReplayError,
    load_exact_semantic_source_bundle,
)


def _bundle(source: Path):
    return load_exact_semantic_source_bundle(source)


def _calls(bundle) -> list[dict]:
    return [deepcopy(item) for item in bundle.semantic_calls]


def _replace_calls(bundle, calls: list[dict]):
    return replace(bundle, semantic_calls=tuple(calls))


def _call(calls: list[dict], task: str) -> dict:
    return next(item for item in calls if item["task"] == task)


def _rehash(record: dict, field: str) -> None:
    record[f"{field}_sha256"] = sha256_canonical_json(record[f"{field}_payload"])


def test_orphan_call_is_reported_without_weak_matching(
    eligible_live_source: Path,
) -> None:
    bundle = _bundle(eligible_live_source)
    calls = _calls(bundle)
    adapter = _call(calls, "structured_adapter")
    adapter["validated_output"]["claims"][0]["confidence"] = 0.11
    adapter["validated_output_sha256"] = sha256_canonical_json(
        adapter["validated_output"]
    )

    audit = build_semantic_binding_audit(_replace_calls(bundle, calls))

    assert adapter["call_id"] in audit["orphan_records"]
    assert audit["artifact_decision_mismatches"]
    assert audit["final_status"] == "FAIL"


def test_missing_artifact_decision_call_fails_closed(
    eligible_live_source: Path,
) -> None:
    bundle = _bundle(eligible_live_source)
    calls = [item for item in _calls(bundle) if item["task"] != "structured_adapter"]

    with pytest.raises(ExactReplayError) as caught:
        verify_semantic_bindings(_replace_calls(bundle, calls))

    assert caught.value.reason_code == EXACT_REPLAY_SEMANTIC_BINDING_MISSING


def test_one_call_to_multiple_artifact_positions_is_ambiguous(
    eligible_live_source: Path,
) -> None:
    bundle = _bundle(eligible_live_source)
    structured = deepcopy(bundle.structured_agent_outputs)
    structured["records"].append(deepcopy(structured["records"][0]))

    with pytest.raises(ExactReplayError) as caught:
        verify_semantic_bindings(replace(bundle, structured_agent_outputs=structured))

    assert caught.value.reason_code == EXACT_REPLAY_SEMANTIC_CALL_AMBIGUOUS


def test_multiple_calls_competing_for_one_decision_are_ambiguous(
    eligible_live_source: Path,
) -> None:
    bundle = _bundle(eligible_live_source)
    calls = _calls(bundle)
    duplicate = deepcopy(_call(calls, "alpha_classifier"))
    duplicate["call_id"] = f"{bundle.source_run_id}:semantic:duplicate"
    duplicate["call_sequence"] = 99
    calls.append(duplicate)

    with pytest.raises(ExactReplayError) as caught:
        verify_semantic_bindings(_replace_calls(bundle, calls))

    assert caught.value.reason_code == EXACT_REPLAY_SEMANTIC_CALL_AMBIGUOUS
    audit = caught.value.details["binding_audit"]
    assert any(isinstance(item, dict) for item in audit["ambiguous_bindings"])


@pytest.mark.parametrize("identity_kind", ["claim_id", "segment_id"])
def test_claim_or_segment_identity_mismatch_fails_closed(
    eligible_live_source: Path,
    identity_kind: str,
) -> None:
    bundle = _bundle(eligible_live_source)
    calls = _calls(bundle)
    if identity_kind == "claim_id":
        record = _call(calls, "structure_extractor")
        record["input_payload"]["claim_id"] = "missing-claim"
        _rehash(record, "input")
    else:
        record = _call(calls, "structured_adapter")
        record["input_payload"]["segments"][0]["segment_id"] = "missing-segment"
        record["validated_output"]["claims"][0]["segment_id"] = "missing-segment"
        _rehash(record, "input")
        record["validated_output_sha256"] = sha256_canonical_json(
            record["validated_output"]
        )

    with pytest.raises(ExactReplayError) as caught:
        verify_semantic_bindings(_replace_calls(bundle, calls))

    assert caught.value.reason_code == EXACT_REPLAY_SEMANTIC_BINDING_MISSING


def test_alpha_selected_result_mismatch_fails_closed(
    eligible_live_source: Path,
) -> None:
    bundle = _bundle(eligible_live_source)
    calls = _calls(bundle)
    record = _call(calls, "alpha_classifier")
    selected = record["input_payload"]["allowed_alpha_ids"][0]
    record["validated_output"] = {
        "decision": "select",
        "selected_alpha_id": selected,
    }
    record["validated_output_sha256"] = sha256_canonical_json(
        record["validated_output"]
    )

    with pytest.raises(ExactReplayError) as caught:
        verify_semantic_bindings(_replace_calls(bundle, calls))

    assert caught.value.reason_code == EXACT_REPLAY_SEMANTIC_OUTPUT_MISMATCH


def test_edge_result_mismatch_fails_closed(eligible_live_source: Path) -> None:
    bundle = _bundle(eligible_live_source)
    calls = _calls(bundle)
    record = _call(calls, "structure_extractor")
    record["validated_output"]["edges"][0]["confidence"] = 0.12
    record["validated_output_sha256"] = sha256_canonical_json(
        record["validated_output"]
    )

    with pytest.raises(ExactReplayError) as caught:
        verify_semantic_bindings(_replace_calls(bundle, calls))

    assert caught.value.reason_code == EXACT_REPLAY_SEMANTIC_OUTPUT_MISMATCH


@pytest.mark.parametrize(
    ("hash_field", "expected"),
    [
        ("input_sha256", EXACT_REPLAY_SEMANTIC_INPUT_MISMATCH),
        ("validated_output_sha256", EXACT_REPLAY_SEMANTIC_OUTPUT_MISMATCH),
    ],
)
def test_call_hash_mismatch_fails_closed(
    eligible_live_source: Path,
    hash_field: str,
    expected: str,
) -> None:
    bundle = _bundle(eligible_live_source)
    calls = _calls(bundle)
    calls[0][hash_field] = "0" * 64

    with pytest.raises(ExactReplayError) as caught:
        verify_semantic_bindings(_replace_calls(bundle, calls))

    assert caught.value.reason_code == expected


def test_taxonomy_or_version_mismatch_fails_closed(
    eligible_live_source: Path,
) -> None:
    bundle = _bundle(eligible_live_source)
    calls = _calls(bundle)
    _call(calls, "alpha_classifier")["taxonomy_version"] = "unsupported"

    with pytest.raises(ExactReplayError) as caught:
        verify_semantic_bindings(_replace_calls(bundle, calls))

    assert caught.value.reason_code == EXACT_REPLAY_SEMANTIC_VERSION_MISMATCH
