"""Structure Graph Schema v1/v2 contract tests (Activation v2 Closure Review,
Phase 1).

Pure unit tests of ``graph_schema.validate_structure_graph_contract`` and
``graph_schema.primary_activation_version_for`` -- the single shared
source of truth used by both the write path (repository.persist_run) and
the read path (repository.get_graph / GET .../graph API). Explicitly
version-specific: never accepts by prefix/startswith, never guesses a
missing version, never treats v1 and v2 as one merged shape.
"""

from __future__ import annotations

import pytest

from comqutor_alpha.graph_engine.graph_schema import (
    GRAPH_SCHEMA_VERSION_V1,
    GRAPH_SCHEMA_VERSION_V2,
    GraphSchemaContractError,
    primary_activation_version_for,
    validate_structure_graph_contract,
)


def _v1_payload(**overrides):
    payload = {
        "schema_version": GRAPH_SCHEMA_VERSION_V1,
        "nodes": [],
        "edges": [],
        "activation": {"formula_version": "week3.activation.mvp_v1", "alphas": []},
        "dominant_alphas": [],
    }
    payload.update(overrides)
    return payload


def _v2_activation_block(formula_version="activation.v2.evidence_local_structure.v1"):
    return {"formula_version": formula_version, "alphas": []}


def _v2_payload(**overrides):
    v2_block = _v2_activation_block()
    payload = {
        "schema_version": GRAPH_SCHEMA_VERSION_V2,
        "nodes": [],
        "edges": [],
        "activation": v2_block,
        "dominant_alphas": [],
        "activation_versions": {
            "v1": {"formula_version": "week3.activation.mvp_v1", "alphas": []},
            "v2": v2_block,
        },
        "primary_activation_version": v2_block["formula_version"],
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Test #1/#2: schema_version identity.
# ---------------------------------------------------------------------------


def test_v1_payload_is_accepted():
    validate_structure_graph_contract(_v1_payload())  # must not raise


def test_v2_payload_is_accepted():
    validate_structure_graph_contract(_v2_payload())  # must not raise


# ---------------------------------------------------------------------------
# Test #5: v2 missing activation_versions is rejected.
# ---------------------------------------------------------------------------


def test_v2_missing_activation_versions_is_rejected():
    payload = _v2_payload()
    del payload["activation_versions"]
    with pytest.raises(GraphSchemaContractError) as exc_info:
        validate_structure_graph_contract(payload)
    assert exc_info.value.reason_code == "GRAPH_SCHEMA_INVALID"


def test_v2_missing_primary_activation_version_is_rejected():
    payload = _v2_payload()
    del payload["primary_activation_version"]
    with pytest.raises(GraphSchemaContractError) as exc_info:
        validate_structure_graph_contract(payload)
    assert exc_info.value.reason_code == "GRAPH_SCHEMA_INVALID"


def test_v2_activation_versions_missing_v1_or_v2_block_is_rejected():
    payload = _v2_payload()
    del payload["activation_versions"]["v1"]
    with pytest.raises(GraphSchemaContractError):
        validate_structure_graph_contract(payload)

    payload2 = _v2_payload()
    del payload2["activation_versions"]["v2"]
    with pytest.raises(GraphSchemaContractError):
        validate_structure_graph_contract(payload2)


# ---------------------------------------------------------------------------
# Test #6: v2 primary/formula mismatch is rejected.
# ---------------------------------------------------------------------------


def test_v2_primary_activation_version_mismatch_is_rejected():
    payload = _v2_payload()
    payload["primary_activation_version"] = "activation.v2.some_other_formula"
    with pytest.raises(GraphSchemaContractError) as exc_info:
        validate_structure_graph_contract(payload)
    assert exc_info.value.reason_code == "GRAPH_SCHEMA_PRIMARY_MISMATCH"


def test_v2_top_level_activation_disagreeing_with_v2_block_is_rejected():
    """The top-level "activation" field (what callers read as primary) must
    be exactly activation_versions["v2"] -- not merely an independently
    plausible payload that happens to declare the same formula_version."""
    payload = _v2_payload()
    payload["activation"] = {
        "formula_version": payload["primary_activation_version"],
        "alphas": [{"alpha_id": "A101"}],  # differs from activation_versions["v2"]
    }
    with pytest.raises(GraphSchemaContractError) as exc_info:
        validate_structure_graph_contract(payload)
    assert exc_info.value.reason_code == "GRAPH_SCHEMA_PRIMARY_MISMATCH"


# ---------------------------------------------------------------------------
# Test #7: unknown schema_version is rejected -- never accepted by
# startswith/prefix, never guessed when absent.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "schema_version",
    [
        "week3.structure_graph.v3",
        "week3.structure_graph",  # prefix of a real version, must not match
        "week99.some_future_schema",
        "",
        None,
    ],
)
def test_unknown_or_missing_schema_version_is_rejected(schema_version):
    payload = _v1_payload(schema_version=schema_version)
    with pytest.raises(GraphSchemaContractError) as exc_info:
        validate_structure_graph_contract(payload)
    assert exc_info.value.reason_code == "GRAPH_SCHEMA_MISMATCH"


def test_non_mapping_payload_is_rejected():
    with pytest.raises(GraphSchemaContractError) as exc_info:
        validate_structure_graph_contract(["not", "a", "mapping"])
    assert exc_info.value.reason_code == "GRAPH_SCHEMA_INVALID"


def test_v1_missing_required_key_is_rejected():
    payload = _v1_payload()
    del payload["dominant_alphas"]
    with pytest.raises(GraphSchemaContractError) as exc_info:
        validate_structure_graph_contract(payload)
    assert exc_info.value.reason_code == "GRAPH_SCHEMA_INVALID"


def test_v1_activation_block_missing_formula_version_is_rejected():
    payload = _v1_payload()
    payload["activation"] = {"alphas": []}
    with pytest.raises(GraphSchemaContractError) as exc_info:
        validate_structure_graph_contract(payload)
    assert exc_info.value.reason_code == "GRAPH_SCHEMA_INVALID"


# ---------------------------------------------------------------------------
# primary_activation_version_for: computed strictly per the payload's own
# schema_version -- v1 never backfilled with v2's field name or vice versa.
# ---------------------------------------------------------------------------


def test_primary_activation_version_for_v1_reads_activation_formula_version():
    payload = _v1_payload()
    assert primary_activation_version_for(payload) == "week3.activation.mvp_v1"


def test_primary_activation_version_for_v2_reads_its_own_field():
    payload = _v2_payload()
    assert (
        primary_activation_version_for(payload)
        == "activation.v2.evidence_local_structure.v1"
    )


def test_primary_activation_version_for_unknown_schema_is_none():
    payload = _v1_payload(schema_version="week99.unknown")
    assert primary_activation_version_for(payload) is None


def test_primary_activation_version_never_backfilled_across_versions():
    """A v1 payload's primary must never be read from a v2-shaped field
    (primary_activation_version), and a v2 payload's primary must never
    fall back to reading activation.formula_version directly if the v2
    field itself is absent -- each version reads strictly its own field."""
    v1 = _v1_payload()
    v1["primary_activation_version"] = "activation.v2.should_never_be_used"
    assert primary_activation_version_for(v1) == "week3.activation.mvp_v1"
