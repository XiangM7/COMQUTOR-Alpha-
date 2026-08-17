from __future__ import annotations

import math

import pytest

from comqutor_alpha.llm_runtime.canonical_json import (
    canonical_json_bytes,
    canonical_json_text,
    sha256_canonical_json,
)
from comqutor_alpha.llm_runtime.errors import CanonicalJSONError


def test_dictionary_key_order_and_unicode_are_stable() -> None:
    left = {"z": "雪", "a": {"β": "值", "a": 1}}
    right = {"a": {"a": 1, "β": "值"}, "z": "雪"}

    assert canonical_json_text(left) == '{"a":{"a":1,"β":"值"},"z":"雪"}'
    assert canonical_json_bytes(left) == canonical_json_bytes(right)
    assert sha256_canonical_json(left) == sha256_canonical_json(right)


def test_list_order_and_string_case_change_hash() -> None:
    assert sha256_canonical_json([1, 2]) != sha256_canonical_json([2, 1])
    assert sha256_canonical_json("Alpha") != sha256_canonical_json("alpha")


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_numbers_are_rejected(value: float) -> None:
    with pytest.raises(CanonicalJSONError, match="Non-finite") as caught:
        canonical_json_text({"value": value})
    assert caught.value.reason_code == "CANONICAL_JSON_NON_FINITE_NUMBER"


@pytest.mark.parametrize("value", [{"bad": {1, 2}}, {1: "non-string"}, (1, 2), b"bytes"])
def test_unsupported_values_are_rejected_without_repr(value: object) -> None:
    with pytest.raises(CanonicalJSONError):
        canonical_json_text(value)


def test_number_types_have_explicit_distinct_serialization() -> None:
    assert canonical_json_text(1) == "1"
    assert canonical_json_text(1.0) == "1.0"
    assert sha256_canonical_json(1) != sha256_canonical_json(1.0)


def test_platform_newlines_are_not_added() -> None:
    assert canonical_json_bytes({"a": 1}) == b'{"a":1}'
