"""J3 Independent LLM Review Packet Export -- dedicated tests (task
J3_INDEPENDENT_LLM_REVIEW_PACKET_EXPORT).

Export-only verification against the real, already-existing, frozen
50-row sample (docs/evidence_review_sample_records.json) and the real,
already-existing stance comparison
(docs/audit_artifacts/b1_llm_stance_50_validation_after_parser_fix.csv)
-- never a synthetic fixture, since the entire point of this task is to
verify the integrity of this specific, real, frozen dataset. Exports in
these tests are written to tmp_path, never overwriting the real
deliverables at docs/audit_artifacts/j3_llm_*.json.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from comqutor_alpha.evaluation.j3_review_packet_export import (
    BLIND_PACKET_ROW_FIELDS,
    DEFAULT_REPLAY_OUTPUT_ROOT,
    DEFAULT_SOURCE_SAMPLE_PATH,
    DEFAULT_STANCE_COMPARISON_PATH,
    EXPECTED_LLM_DETERMINISTIC_DISAGREEMENT_COUNT,
    EXPECTED_LLM_NEUTRAL_BACKGROUND_COUNT,
    EXPECTED_ROW_COUNT,
    EXPECTED_SUPPORT_OPPOSE_REVERSAL_COUNT,
    FORBIDDEN_BLIND_PACKET_ROW_FIELDS,
    J3SourceSampleMismatchError,
    build_blind_review_packet,
    build_comparison_reference,
    export_j3_review_packets,
    load_alpha_taxonomy,
    load_source_refs_by_claim_id,
    load_source_sample,
    load_stance_comparison,
    verify_historical_numbers,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _fixed_timestamp() -> str:
    return datetime(2026, 1, 1, tzinfo=UTC).isoformat().replace("+00:00", "Z")


@pytest.fixture(scope="module")
def real_sample_payload():
    return load_source_sample(DEFAULT_SOURCE_SAMPLE_PATH)


@pytest.fixture(scope="module")
def real_stance_rows():
    return load_stance_comparison(DEFAULT_STANCE_COMPARISON_PATH)


@pytest.fixture(scope="module")
def real_taxonomy():
    return load_alpha_taxonomy()


@pytest.fixture(scope="module")
def exported(tmp_path_factory, real_sample_payload, real_stance_rows, real_taxonomy):
    out_dir = tmp_path_factory.mktemp("j3_export")
    source_refs = load_source_refs_by_claim_id(real_sample_payload["records"], DEFAULT_REPLAY_OUTPUT_ROOT)
    historical_summary = verify_historical_numbers(real_stance_rows)
    blind = build_blind_review_packet(
        sample_payload=real_sample_payload,
        taxonomy=real_taxonomy,
        source_refs_by_claim=source_refs,
        source_sample_path=DEFAULT_SOURCE_SAMPLE_PATH,
        created_at=_fixed_timestamp(),
    )
    reference = build_comparison_reference(
        sample_payload=real_sample_payload,
        stance_rows=real_stance_rows,
        historical_summary=historical_summary,
        source_sample_path=DEFAULT_SOURCE_SAMPLE_PATH,
        stance_comparison_path=DEFAULT_STANCE_COMPARISON_PATH,
        created_at=_fixed_timestamp(),
    )
    return {"blind": blind, "reference": reference, "out_dir": out_dir}


class TestRowCounts:
    def test_1_blind_packet_has_exactly_50_rows(self, exported):
        assert len(exported["blind"]["rows"]) == EXPECTED_ROW_COUNT

    def test_2_comparison_reference_has_exactly_50_rows(self, exported):
        assert len(exported["reference"]["rows"]) == EXPECTED_ROW_COUNT


class TestIdentityConsistency:
    def test_3_identity_sets_equal_between_both_files(self, exported):
        blind_ids = {(r["run_id"], r["claim_id"], r["target_alpha_id"]) for r in exported["blind"]["rows"]}
        reference_ids = {(r["run_id"], r["claim_id"], r["target_alpha_id"]) for r in exported["reference"]["rows"]}
        assert blind_ids == reference_ids

    def test_4_identity_unique_within_blind_packet(self, exported):
        ids = [(r["run_id"], r["claim_id"], r["target_alpha_id"]) for r in exported["blind"]["rows"]]
        assert len(ids) == len(set(ids))

    def test_4b_identity_unique_within_comparison_reference(self, exported):
        ids = [(r["run_id"], r["claim_id"], r["target_alpha_id"]) for r in exported["reference"]["rows"]]
        assert len(ids) == len(set(ids))

    def test_4c_sample_id_unique_in_both_files(self, exported):
        blind_sample_ids = [r["sample_id"] for r in exported["blind"]["rows"]]
        reference_sample_ids = [r["sample_id"] for r in exported["reference"]["rows"]]
        assert len(blind_sample_ids) == len(set(blind_sample_ids))
        assert len(reference_sample_ids) == len(set(reference_sample_ids))


class TestNoResamplingOrReordering:
    def test_5_blind_packet_row_order_matches_original_sample_order(self, exported, real_sample_payload):
        original_order = [r["sample_id"] for r in real_sample_payload["records"]]
        blind_order = [r["sample_id"] for r in exported["blind"]["rows"]]
        assert blind_order == original_order

    def test_5b_comparison_reference_preserves_the_same_canonical_order(self, exported, real_sample_payload):
        original_order = [r["sample_id"] for r in real_sample_payload["records"]]
        reference_order = [r["sample_id"] for r in exported["reference"]["rows"]]
        assert reference_order == original_order

    def test_5c_sample_id_set_matches_the_original_sample_exactly(self, exported, real_sample_payload):
        original_ids = {r["sample_id"] for r in real_sample_payload["records"]}
        blind_ids = {r["sample_id"] for r in exported["blind"]["rows"]}
        reference_ids = {r["sample_id"] for r in exported["reference"]["rows"]}
        assert original_ids == blind_ids == reference_ids
        assert len(original_ids) == EXPECTED_ROW_COUNT


class TestClaimEvidenceByteForByte:
    def test_6_claim_and_evidence_are_byte_for_byte_identical_to_the_original_sample(
        self, exported, real_sample_payload
    ):
        original_by_id = {r["sample_id"]: r for r in real_sample_payload["records"]}
        for row in exported["blind"]["rows"]:
            original = original_by_id[row["sample_id"]]
            assert row["claim"] == original["claim"]
            assert row["evidence"] == original["evidence"]

    def test_6b_known_john_rebuttal_example_is_present_and_unaltered(self, exported):
        row = next(r for r in exported["blind"]["rows"] if r["sample_id"] == "evrs-014")
        assert row["claim"] == 'The "valuation risk" argument is a lazy heuristic that ignores the actual numbers.'
        assert row["target_alpha_id"] == "A304"


class TestCanonicalTaxonomy:
    def test_7_every_target_alpha_is_canonical(self, exported, real_taxonomy):
        known_alpha_ids = frozenset(real_taxonomy.keys())
        for row in exported["blind"]["rows"]:
            assert row["target_alpha_id"] in known_alpha_ids
        for row in exported["reference"]["rows"]:
            assert row["target_alpha_id"] in known_alpha_ids

    def test_8_every_legal_counter_alpha_is_a_real_canonical_conflict_partner(self, exported, real_taxonomy):
        for row in exported["blind"]["rows"]:
            alpha = real_taxonomy[row["target_alpha_id"]]
            real_partners = {c.alpha_id for c in (alpha.conflict_alphas or ())}
            assert set(row["legal_counter_alphas"]) == real_partners

    def test_8b_returned_counter_alpha_ids_are_always_legal_for_their_row(self, exported):
        for row in exported["reference"]["rows"]:
            blind_row = next(b for b in exported["blind"]["rows"] if b["sample_id"] == row["sample_id"])
            for field in ("original_llm_counter_alpha_id", "deterministic_counter_alpha_id", "system_final_counter_alpha_id"):
                value = row[field]
                if value is not None:
                    assert value in blind_row["legal_counter_alphas"], f"{row['sample_id']}.{field}={value}"


class TestBlindPacketLeakage:
    def test_9_blind_packet_rows_contain_only_the_allowed_field_set(self, exported):
        for row in exported["blind"]["rows"]:
            assert set(row.keys()) == set(BLIND_PACKET_ROW_FIELDS)

    def test_9b_blind_packet_rows_contain_no_forbidden_keys(self, exported):
        for row in exported["blind"]["rows"]:
            assert not (set(row.keys()) & FORBIDDEN_BLIND_PACKET_ROW_FIELDS)

    def test_9c_no_stance_value_string_appears_as_a_dict_value_in_any_blind_row(self, exported):
        stance_values = {
            "supports_alpha",
            "opposes_alpha",
            "mentions_alpha",
            "neutral_background",
            "supports_counter_alpha",
        }
        for row in exported["blind"]["rows"]:
            # legal_counter_alphas/source_refs hold lists (alpha IDs /
            # ref strings), never a bare stance literal; every other
            # (hashable, scalar) value must never equal a stance literal.
            for key, value in row.items():
                if isinstance(value, list):
                    assert not (set(value) & stance_values), f"{row['sample_id']}.{key} leaked stance value"
                    continue
                assert value not in stance_values, f"{row['sample_id']}.{key} leaked stance value {value!r}"

    def test_9d_written_file_has_no_forbidden_key_substrings_outside_the_instructions_section(self, exported, tmp_path):
        # Serialize just the rows (not review_instructions, which
        # legitimately describes the reviewer's own output schema) and
        # confirm no forbidden key name appears anywhere in that slice.
        rows_only = json.dumps(exported["blind"]["rows"])
        for forbidden in FORBIDDEN_BLIND_PACKET_ROW_FIELDS:
            assert forbidden not in rows_only, f"forbidden field {forbidden!r} found in blind packet rows"


class TestHistoricalNumbersReproduced:
    def test_10_reproduces_31_llm_deterministic_disagreements(self, exported):
        assert exported["reference"]["historical_summary"]["llm_deterministic_disagreement_count"] == (
            EXPECTED_LLM_DETERMINISTIC_DISAGREEMENT_COUNT
        )
        actual = sum(1 for r in exported["reference"]["rows"] if r["llm_deterministic_disagreement"] is True)
        assert actual == EXPECTED_LLM_DETERMINISTIC_DISAGREEMENT_COUNT == 31

    def test_11_reproduces_7_support_oppose_reversals(self, exported):
        assert exported["reference"]["historical_summary"]["support_oppose_reversal_count"] == (
            EXPECTED_SUPPORT_OPPOSE_REVERSAL_COUNT
        )
        actual = sum(1 for r in exported["reference"]["rows"] if r["support_oppose_reversal"] is True)
        assert actual == EXPECTED_SUPPORT_OPPOSE_REVERSAL_COUNT == 7

    def test_11b_reproduces_zero_neutral_background_in_llm_distribution(self, exported):
        assert exported["reference"]["historical_summary"]["llm_neutral_background_count"] == (
            EXPECTED_LLM_NEUTRAL_BACKGROUND_COUNT
        )
        actual = sum(1 for r in exported["reference"]["rows"] if r["original_llm_stance"] == "neutral_background")
        assert actual == 0


class TestFailClosed:
    def test_12_missing_mandatory_records_field_fails_closed(self, tmp_path):
        bad_path = tmp_path / "bad_sample.json"
        bad_path.write_text(json.dumps({"schema_version": "x"}), encoding="utf-8")
        with pytest.raises(J3SourceSampleMismatchError):
            load_source_sample(bad_path)

    def test_12b_identity_set_mismatch_between_sample_and_stance_comparison_fails_closed(
        self, tmp_path, real_sample_payload, real_stance_rows
    ):
        tampered_sample = copy.deepcopy(real_sample_payload)
        tampered_sample["records"] = tampered_sample["records"][:-1]  # drop one row
        sample_path = tmp_path / "sample.json"
        sample_path.write_text(json.dumps(tampered_sample), encoding="utf-8")

        stance_path = DEFAULT_STANCE_COMPARISON_PATH
        out_blind = tmp_path / "blind.json"
        out_ref = tmp_path / "ref.json"
        with pytest.raises(J3SourceSampleMismatchError):
            export_j3_review_packets(
                source_sample_path=sample_path,
                stance_comparison_path=stance_path,
                blind_packet_output_path=out_blind,
                comparison_reference_output_path=out_ref,
                created_at=_fixed_timestamp(),
            )
        assert not out_blind.exists()
        assert not out_ref.exists()

    def test_12c_wrong_historical_numbers_are_detected_as_source_sample_mismatch(self, real_stance_rows):
        tampered = copy.deepcopy(real_stance_rows)
        # Find a row that currently disagrees and force agreement --
        # guaranteed to change the disagreement count away from 31,
        # regardless of dict iteration order.
        disagreeing_key = next(
            key for key, row in tampered.items() if row["deterministic_v1_stance"] != row["llm_v1_stance"]
        )
        tampered[disagreeing_key] = dict(tampered[disagreeing_key])
        tampered[disagreeing_key]["llm_v1_stance"] = tampered[disagreeing_key]["deterministic_v1_stance"]
        with pytest.raises(J3SourceSampleMismatchError):
            verify_historical_numbers(tampered)


class TestValidUtf8Json:
    def test_13_both_output_files_are_valid_utf8_json(self, exported, tmp_path):
        blind_path = tmp_path / "blind.json"
        ref_path = tmp_path / "ref.json"
        blind_path.write_text(json.dumps(exported["blind"], ensure_ascii=False), encoding="utf-8")
        ref_path.write_text(json.dumps(exported["reference"], ensure_ascii=False), encoding="utf-8")
        with blind_path.open(encoding="utf-8") as handle:
            json.load(handle)
        with ref_path.open(encoding="utf-8") as handle:
            json.load(handle)


class TestDeterminism:
    def test_14_repeated_export_is_deterministic_except_created_at(self, tmp_path):
        out1_blind = tmp_path / "run1_blind.json"
        out1_ref = tmp_path / "run1_ref.json"
        out2_blind = tmp_path / "run2_blind.json"
        out2_ref = tmp_path / "run2_ref.json"
        export_j3_review_packets(
            blind_packet_output_path=out1_blind, comparison_reference_output_path=out1_ref, created_at="2026-01-01T00:00:00Z"
        )
        export_j3_review_packets(
            blind_packet_output_path=out2_blind, comparison_reference_output_path=out2_ref, created_at="2026-06-06T00:00:00Z"
        )
        blind1 = json.loads(out1_blind.read_text())
        blind2 = json.loads(out2_blind.read_text())
        ref1 = json.loads(out1_ref.read_text())
        ref2 = json.loads(out2_ref.read_text())
        del blind1["created_at"], blind2["created_at"], ref1["created_at"], ref2["created_at"]
        assert blind1 == blind2
        assert ref1 == ref2


class TestSourceArtifactsUnchanged:
    def test_15_source_sample_and_stance_csv_are_hash_identical_before_and_after_export(self, tmp_path):
        before_sample = DEFAULT_SOURCE_SAMPLE_PATH.read_bytes()
        before_csv = DEFAULT_STANCE_COMPARISON_PATH.read_bytes()
        export_j3_review_packets(
            blind_packet_output_path=tmp_path / "b.json",
            comparison_reference_output_path=tmp_path / "r.json",
            created_at=_fixed_timestamp(),
        )
        after_sample = DEFAULT_SOURCE_SAMPLE_PATH.read_bytes()
        after_csv = DEFAULT_STANCE_COMPARISON_PATH.read_bytes()
        assert before_sample == after_sample
        assert before_csv == after_csv


class TestZeroProviderAndTradingAgentsCalls:
    def test_16_module_never_imports_a_provider_or_llm_client(self):
        import comqutor_alpha.evaluation.j3_review_packet_export as module

        with open(module.__file__, encoding="utf-8") as handle:
            text = handle.read().lower()
        for forbidden in ("llm_runtime", "week2llmgateway", "invoke_json_with_trace", "anthropic", "openai"):
            assert forbidden not in text

    def test_17_module_never_imports_tradingagents(self):
        import comqutor_alpha.evaluation.j3_review_packet_export as module

        with open(module.__file__, encoding="utf-8") as handle:
            text = handle.read().lower()
        assert "tradingagents" not in text
        assert "run_structure_replay" not in text  # reads existing replay bundles only, never triggers a new one
