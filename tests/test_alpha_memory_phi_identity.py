"""Alpha Memory Implementation Step 2 -- atomic edge phi identity tests.

Pure, offline, deterministic. Zero Provider calls, zero TradingAgents
calls. Every fixture here is synthetic -- no real run data is required for
these unit tests (see test_alpha_memory_history_reader.py and
tests/test_v0_1_3_offline_replay_proof.py for real-data checks).
"""

from __future__ import annotations

import ast
from pathlib import Path

from comqutor_alpha.memory.phi_identity import (
    AGGREGATE_FINGERPRINT_VERSION,
    PHI_EDGE_IDENTITY_VERSION,
    compute_aggregate_fingerprints,
    compute_phi_edges,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _edge(source, target, edge_type, alpha_ids):
    return {"source": source, "target": target, "edge_type": edge_type, "alpha_ids": list(alpha_ids)}


def _graph(*, ticker, run_id, edges):
    return {"ticker": ticker, "run_id": run_id, "edges": edges}


def _vocab(taxonomy_version="structure_engine.factor_aliases.v1", taxonomy_sha256="deadbeef"):
    return {"taxonomy_version": taxonomy_version, "taxonomy_sha256": taxonomy_sha256}


# ---------------------------------------------------------------------------
# 1. Same ticker + same Alpha + same source/type/target across runs -> same
# atomic phi_id.
# ---------------------------------------------------------------------------


def test_same_ticker_alpha_edge_across_two_runs_produces_the_same_atomic_phi_id():
    edges = [_edge("ai_demand", "gpu_shortage", "causal", ["A101"])]
    vocab = _vocab()
    phi_run1 = compute_phi_edges(structure_graph=_graph(ticker="NVDA", run_id="run-1", edges=edges), vocabulary_snapshot=vocab)
    phi_run2 = compute_phi_edges(structure_graph=_graph(ticker="NVDA", run_id="run-2", edges=edges), vocabulary_snapshot=vocab)
    assert phi_run1[0]["phi_id"] == phi_run2[0]["phi_id"]


# ---------------------------------------------------------------------------
# 2. Different ticker -> different phi_id.
# ---------------------------------------------------------------------------


def test_different_ticker_produces_different_phi_id():
    edges = [_edge("ai_demand", "gpu_shortage", "causal", ["A101"])]
    vocab = _vocab()
    nvda = compute_phi_edges(structure_graph=_graph(ticker="NVDA", run_id="r1", edges=edges), vocabulary_snapshot=vocab)
    amd = compute_phi_edges(structure_graph=_graph(ticker="AMD", run_id="r2", edges=edges), vocabulary_snapshot=vocab)
    assert nvda[0]["phi_id"] != amd[0]["phi_id"]


# ---------------------------------------------------------------------------
# 3. Different alpha_id -> different phi_id.
# ---------------------------------------------------------------------------


def test_different_alpha_id_produces_different_phi_id():
    edges = [_edge("ai_demand", "gpu_shortage", "causal", ["A101", "A103"])]
    phi = compute_phi_edges(structure_graph=_graph(ticker="NVDA", run_id="r1", edges=edges), vocabulary_snapshot=_vocab())
    a101 = next(p for p in phi if p["alpha_id"] == "A101")
    a103 = next(p for p in phi if p["alpha_id"] == "A103")
    assert a101["phi_id"] != a103["phi_id"]


# ---------------------------------------------------------------------------
# 4. Different edge_type -> different phi_id. Product Decision: edge_type
# is NEVER dropped merely to raise the match rate.
# ---------------------------------------------------------------------------


def test_different_edge_type_produces_different_phi_id():
    vocab = _vocab()
    causal = compute_phi_edges(
        structure_graph=_graph(ticker="NVDA", run_id="r1", edges=[_edge("ai_capex", "gpu_demand", "causal", ["A101"])]),
        vocabulary_snapshot=vocab,
    )
    supportive = compute_phi_edges(
        structure_graph=_graph(ticker="NVDA", run_id="r2", edges=[_edge("ai_capex", "gpu_demand", "supportive", ["A101"])]),
        vocabulary_snapshot=vocab,
    )
    assert causal[0]["phi_id"] != supportive[0]["phi_id"]


# ---------------------------------------------------------------------------
# 5. Different source or target -> different phi_id.
# ---------------------------------------------------------------------------


def test_different_source_or_target_produces_different_phi_id():
    vocab = _vocab()
    original = compute_phi_edges(
        structure_graph=_graph(ticker="NVDA", run_id="r1", edges=[_edge("ai_demand", "gpu_shortage", "causal", ["A101"])]),
        vocabulary_snapshot=vocab,
    )
    changed_target = compute_phi_edges(
        structure_graph=_graph(ticker="NVDA", run_id="r2", edges=[_edge("ai_demand", "datacenter_buildout", "causal", ["A101"])]),
        vocabulary_snapshot=vocab,
    )
    changed_source = compute_phi_edges(
        structure_graph=_graph(ticker="NVDA", run_id="r3", edges=[_edge("cloud_capex", "gpu_shortage", "causal", ["A101"])]),
        vocabulary_snapshot=vocab,
    )
    assert original[0]["phi_id"] != changed_target[0]["phi_id"]
    assert original[0]["phi_id"] != changed_source[0]["phi_id"]


# ---------------------------------------------------------------------------
# 6. Taxonomy/identity version mismatch -> different phi_id (no silent match).
# ---------------------------------------------------------------------------


def test_taxonomy_version_mismatch_produces_different_phi_id():
    edges = [_edge("ai_demand", "gpu_shortage", "causal", ["A101"])]
    old_taxonomy = compute_phi_edges(
        structure_graph=_graph(ticker="NVDA", run_id="r1", edges=edges), vocabulary_snapshot=_vocab(taxonomy_sha256="old-hash")
    )
    new_taxonomy = compute_phi_edges(
        structure_graph=_graph(ticker="NVDA", run_id="r2", edges=edges), vocabulary_snapshot=_vocab(taxonomy_sha256="new-hash")
    )
    assert old_taxonomy[0]["phi_id"] != new_taxonomy[0]["phi_id"]


def test_missing_vocabulary_snapshot_degrades_gracefully_never_crashes():
    phi = compute_phi_edges(
        structure_graph=_graph(ticker="NVDA", run_id="r1", edges=[_edge("ai_demand", "gpu_shortage", "causal", ["A101"])]),
        vocabulary_snapshot=None,
    )
    assert phi[0]["taxonomy_version"] is None
    assert phi[0]["taxonomy_sha256"] is None


# ---------------------------------------------------------------------------
# 7. One Alpha with N qualifying edges -> N atomic phi tokens. One Alpha
# MUST NOT be hashed as a single primary identity.
# ---------------------------------------------------------------------------


def test_one_alpha_with_n_qualifying_edges_produces_n_atomic_phi_tokens():
    edges = [
        _edge("ai_capex", "gpu_demand", "causal", ["A101"]),
        _edge("gpu_demand", "nvda_revenue_growth", "supportive", ["A101"]),
        _edge("rate_cut_cycle", "valuation_risk", "conflicting", ["A101"]),
    ]
    phi = compute_phi_edges(structure_graph=_graph(ticker="NVDA", run_id="r1", edges=edges), vocabulary_snapshot=_vocab())
    a101_phi = [p for p in phi if p["alpha_id"] == "A101"]
    assert len(a101_phi) == 3
    assert len({p["phi_id"] for p in a101_phi}) == 3  # all distinct


def test_alpha_with_no_linked_edges_produces_no_phi():
    phi = compute_phi_edges(structure_graph=_graph(ticker="NVDA", run_id="r1", edges=[]), vocabulary_snapshot=_vocab())
    assert phi == []


def test_shared_edge_across_two_alphas_produces_two_distinct_phi_records():
    """Real audit finding (Step 1.6): the same literal edge is already,
    intentionally, linked to more than one Alpha within a single run --
    this must produce two separate phi records, never be collapsed into
    one, and never silently deduplicated to a single alpha."""
    edges = [_edge("ai_capex", "gpu_demand", "causal", ["A101", "A103"])]
    phi = compute_phi_edges(structure_graph=_graph(ticker="NVDA", run_id="r1", edges=edges), vocabulary_snapshot=_vocab())
    assert len(phi) == 2
    assert {p["alpha_id"] for p in phi} == {"A101", "A103"}
    assert phi[0]["phi_id"] != phi[1]["phi_id"]
    assert phi[0]["source"] == phi[1]["source"] == "ai_capex"
    assert phi[0]["target"] == phi[1]["target"] == "gpu_demand"


# ---------------------------------------------------------------------------
# 17. Repeated offline execution is deterministic.
# ---------------------------------------------------------------------------


def test_repeated_execution_is_deterministic():
    graph = _graph(
        ticker="NVDA", run_id="r1",
        edges=[
            _edge("ai_demand", "gpu_shortage", "causal", ["A101"]),
            _edge("gpu_shortage", "nvda_revenue_growth", "causal", ["A101"]),
        ],
    )
    vocab = _vocab()
    first = compute_phi_edges(structure_graph=graph, vocabulary_snapshot=vocab)
    second = compute_phi_edges(structure_graph=graph, vocabulary_snapshot=vocab)
    assert first == second


def test_identity_version_is_stamped_on_every_atomic_phi():
    phi = compute_phi_edges(
        structure_graph=_graph(ticker="NVDA", run_id="r1", edges=[_edge("ai_demand", "gpu_shortage", "causal", ["A101"])]),
        vocabulary_snapshot=_vocab(),
    )
    assert phi[0]["identity_version"] == PHI_EDGE_IDENTITY_VERSION == "alpha_memory.phi_edge.v1"


def test_phi_identity_module_never_uses_python_runtime_hash_or_random_or_time():
    tree = ast.parse((REPO_ROOT / "comqutor_alpha/memory/phi_identity.py").read_text())
    banned_calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            banned_calls.add(node.func.id)
    assert "hash" not in banned_calls
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", None) or ""
            names = [alias.name for alias in node.names]
            assert "random" not in module and "random" not in names
            assert "uuid" not in module and "uuid" not in names
            assert "datetime" not in module and "datetime" not in names
            assert "time" not in names


def test_memory_package_never_imported_by_activation_or_conflict_modules():
    guarded_files = [
        "comqutor_alpha/graph_engine/activation_scorer_v2.py",
        "comqutor_alpha/graph_engine/activation_scorer.py",
        "comqutor_alpha/graph_engine/alpha_level_classifier.py",
        "comqutor_alpha/conflict_engine/conflict_detector.py",
        "comqutor_alpha/conflict_engine/conflict_admissibility.py",
    ]
    for relative_path in guarded_files:
        path = REPO_ROOT / relative_path
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "comqutor_alpha.memory" not in node.module, (
                    f"{relative_path} must never import comqutor_alpha.memory"
                )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "comqutor_alpha.memory" not in alias.name, (
                        f"{relative_path} must never import comqutor_alpha.memory"
                    )


# ---------------------------------------------------------------------------
# Aggregate fingerprint: retained, unchanged arithmetic, but a distinct,
# clearly-separate concept from the atomic phi identity above.
# ---------------------------------------------------------------------------


def test_aggregate_fingerprint_is_a_distinct_concept_from_atomic_phi():
    edges = [
        _edge("ai_capex", "gpu_demand", "causal", ["A101"]),
        _edge("gpu_demand", "nvda_revenue_growth", "supportive", ["A101"]),
    ]
    graph = _graph(ticker="NVDA", run_id="r1", edges=edges)
    vocab = _vocab()
    phi_edges = compute_phi_edges(structure_graph=graph, vocabulary_snapshot=vocab)
    fingerprints = compute_aggregate_fingerprints(structure_graph=graph, vocabulary_snapshot=vocab)
    assert len(phi_edges) == 2  # one atomic phi per edge
    assert len(fingerprints) == 1  # one aggregate fingerprint for the whole A101 set
    assert fingerprints[0]["identity_version"] == AGGREGATE_FINGERPRINT_VERSION
    assert "aggregate_fingerprint_id" in fingerprints[0]
    assert "phi_id" not in fingerprints[0]  # never mislabeled as the primary phi identity


def test_aggregate_fingerprint_arithmetic_is_unchanged_from_step1():
    """The aggregate fingerprint's hash formula must be byte-identical to
    Step 1's original whole-set computation -- only the name/classification
    changed, never the arithmetic."""
    import hashlib
    import json

    edges = [_edge("ai_capex", "gpu_demand", "causal", ["A101"])]
    graph = _graph(ticker="NVDA", run_id="r1", edges=edges)
    vocab = _vocab()
    fingerprints = compute_aggregate_fingerprints(structure_graph=graph, vocabulary_snapshot=vocab)
    expected_payload = {
        "identity_version": AGGREGATE_FINGERPRINT_VERSION,
        "ticker": "NVDA",
        "alpha_id": "A101",
        "taxonomy_version": vocab["taxonomy_version"],
        "taxonomy_sha256": vocab["taxonomy_sha256"],
        "chain_edges": [["ai_capex", "causal", "gpu_demand"]],
    }
    expected_id = hashlib.sha256(
        json.dumps(expected_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    assert fingerprints[0]["aggregate_fingerprint_id"] == expected_id
