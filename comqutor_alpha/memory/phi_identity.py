"""Alpha Memory Implementation Step 2 (SHADOW ONLY) -- atomic edge phi
identity + whole-Alpha aggregate fingerprint.

Product decisions authoritative for this module, established by real
cross-run empirical audit (docs/audit_artifacts/
alpha_memory_phi_stability_audit.json,
alpha_memory_edge_identity_ablation.json) and now adopted (Implementation
Step 2):

  1. PRIMARY DURABLE UNIT IS THE ATOMIC EDGE, NOT THE WHOLE-ALPHA EDGE SET.
     Step 1's whole-set identity measured 0% cross-run recognition on real
     data (0 of 14 alpha-pairs matched across two real ticker pairs) --
     confirmed structural, not a fluke. One Alpha MAY produce, and
     typically does produce, MANY atomic phi tokens (one per qualifying
     edge) -- never assume one Alpha = one phi.
  2. EXACT IDENTITY MODEL, FULL FIELD SET RETAINED. The ablation audit
     showed dropping alpha_id or edge_type to raise the raw match rate
     would silently merge structures with real, non-noise semantic
     content: the same edge is already, intentionally, linked to more
     than one Alpha within a single run (real multi-relevance, not
     duplication), and at least one real cross-run case showed edge_type
     disagreement (causal vs conflicting) that reads as a genuinely
     different claim, not mere classification wording variance. alpha_id
     and edge_type therefore REMAIN part of durable identity -- never
     removed merely to increase the match rate.
  3. v2 identity is strictly TICKER-SCOPED (unchanged from Step 1).
  4. EXACT CANONICAL MATCHING ONLY (unchanged from Step 1) -- no
     embeddings, no LLM similarity, no fuzzy/heuristic matching, no
     equivalence tables.
  5. Explicit version authority (PHI_EDGE_IDENTITY_VERSION) and the
     producing run's own persisted taxonomy authority
     (taxonomy_version/taxonomy_sha256, read from that run's own
     tradingagents_comqutor_vocabulary_snapshot.json -- never recomputed
     against the current worktree's taxonomy) remain part of every hash,
     exactly as in Step 1.
  6. The Step 1 whole-Alpha edge-set computation is RETAINED, UNCHANGED IN
     ITS ARITHMETIC, but explicitly renamed and reclassified as an
     AGGREGATE_FINGERPRINT -- never presented as "the" phi identity. It
     remains useful for whole-structure drift diagnostics and QA, but zero
     aggregate-fingerprint overlap must never be read as zero atomic-phi
     overlap (the two are now separate, independently reported concepts).
  7. Motif/path-level identity remains explicitly DEFERRED (unchanged from
     Step 1.5's finding, reaffirmed by Step 1.6 -- 2-/3-edge motifs
     measured even less stable than the whole-alpha set on real data).
  8. SHADOW ONLY: this module is read-only and pure. It is never imported
     by activation_scorer_v2.py, alpha_level_classifier.py,
     conflict_detector.py, or conflict_admissibility.py, and computes
     nothing that could feed back into official B4/Conflict outcomes.

No Python runtime hash() is used anywhere in this module (that function's
output is not stable across process runs by design in modern CPython for
str/bytes). No timestamp, UUID, or other non-deterministic value ever
enters an identity computation.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

# The PRIMARY durable identity as of Implementation Step 2. One entry per
# (ticker, alpha_id, source, edge_type, target) -- an atomic causal edge,
# not a whole Alpha's structure. A change to what this hashes MUST bump
# this string, exactly like this codebase's existing SCHEMA_VERSION/
# MAPPER_VERSION/CONFLICT_FORMULA_VERSION convention.
PHI_EDGE_IDENTITY_VERSION = "alpha_memory.phi_edge.v1"

# Step 1's original whole-Alpha edge-SET computation, retained with
# IDENTICAL arithmetic but renamed/reclassified: this is now explicitly an
# aggregate fingerprint (a coarse, secondary, drift-diagnostic signal),
# never the primary phi identity. Kept as its own version string, distinct
# from PHI_EDGE_IDENTITY_VERSION, since it is now a conceptually different
# artifact even though its hash formula is unchanged from Step 1's
# PHI_IDENTITY_VERSION = "alpha_memory.phi.v1".
AGGREGATE_FINGERPRINT_VERSION = "alpha_memory.aggregate_fingerprint.v1"

# The identity_model label exposed on the run_audit.json alpha_memory
# section (Implementation Step 2, section H) -- names which concept is now
# primary, so no artifact/consumer can mistake the aggregate fingerprint
# for the durable phi identity.
IDENTITY_MODEL = "atomic_edge_phi"


def _canonical_chain_edges(
    edges: Sequence[Mapping[str, Any]], alpha_id: str
) -> list[tuple[str, str, str]]:
    """The deterministic set of (source, edge_type, target) triples this
    run's Structure Graph already links to ``alpha_id`` via the existing
    edge['alpha_ids'] field. Used by both the atomic edge computation
    (one entry per triple) and the aggregate fingerprint (the whole sorted
    set, unchanged from Step 1)."""
    triples: set[tuple[str, str, str]] = set()
    for edge in edges:
        if not isinstance(edge, Mapping):
            continue
        edge_alpha_ids = edge.get("alpha_ids")
        if not isinstance(edge_alpha_ids, Sequence) or alpha_id not in edge_alpha_ids:
            continue
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        edge_type = str(edge.get("edge_type") or "").strip()
        if source and target:
            triples.add((source, edge_type, target))
    return sorted(triples)


def _stable_digest(payload: Mapping[str, Any]) -> str:
    """SHA-256 of the JSON-canonicalized (sorted keys, fixed separators,
    ASCII-only) payload. Deterministic across processes and Python
    versions -- unlike Python's own hash(), which this module never uses
    for a persisted identifier."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _alpha_ids_in_graph(edges: Sequence[Mapping[str, Any]]) -> list[str]:
    alpha_ids: set[str] = set()
    for edge in edges:
        if isinstance(edge, Mapping):
            edge_alpha_ids = edge.get("alpha_ids")
            if isinstance(edge_alpha_ids, Sequence):
                alpha_ids.update(str(a) for a in edge_alpha_ids if a)
    return sorted(alpha_ids)


def compute_phi_edges(
    *,
    structure_graph: Mapping[str, Any],
    vocabulary_snapshot: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """PRIMARY identity computation (Implementation Step 2). One atomic
    phi record per (ticker, alpha_id, source, edge_type, target) that this
    run's already-persisted Structure Graph links via edge['alpha_ids'].
    One Alpha with N qualifying edges produces N phi records -- never one.

    Pure function -- no filesystem/DB/network access, no Provider or
    TradingAgents call, no randomness, no wall-clock read. Reuses the
    Structure Graph's own existing edge['alpha_ids'] linkage verbatim --
    never re-derives or re-scores an alpha/edge association, and never
    duplicates Structure Extractor logic (source/target/edge_type are
    read directly from the already-persisted edge, not recomputed).

    ``vocabulary_snapshot`` should be the SAME run's own persisted
    tradingagents_comqutor_vocabulary_snapshot.json (or ``None``/``{}`` if
    unavailable) -- never the current worktree's live taxonomy, so a
    historical run's phi_id remains stable even if the taxonomy file has
    since changed.
    """
    ticker = str(structure_graph.get("ticker") or "")
    run_id = str(structure_graph.get("run_id") or "")
    edges = structure_graph.get("edges")
    edges = edges if isinstance(edges, Sequence) else []
    vocabulary_snapshot = vocabulary_snapshot if isinstance(vocabulary_snapshot, Mapping) else {}
    taxonomy_version = vocabulary_snapshot.get("taxonomy_version")
    taxonomy_sha256 = vocabulary_snapshot.get("taxonomy_sha256")

    phi_edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for alpha_id in _alpha_ids_in_graph(edges):
        for source, edge_type, target in _canonical_chain_edges(edges, alpha_id):
            dedup_key = (alpha_id, source, edge_type, target)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            # Product Decisions 2-4 (Implementation Step 2): ticker,
            # alpha_id, edge_type, taxonomy authority, and identity_version
            # are ALL part of the hashed content -- a difference in ANY of
            # them produces a different phi_id, never a silent merge.
            canonical_representation = {
                "identity_version": PHI_EDGE_IDENTITY_VERSION,
                "ticker": ticker,
                "alpha_id": alpha_id,
                "taxonomy_version": taxonomy_version,
                "taxonomy_sha256": taxonomy_sha256,
                "source": source,
                "edge_type": edge_type,
                "target": target,
            }
            phi_id = _stable_digest(canonical_representation)
            phi_edges.append(
                {
                    "phi_id": phi_id,
                    "identity_version": PHI_EDGE_IDENTITY_VERSION,
                    "ticker": ticker,
                    "alpha_id": alpha_id,
                    "source": source,
                    "edge_type": edge_type,
                    "target": target,
                    "taxonomy_version": taxonomy_version,
                    "taxonomy_sha256": taxonomy_sha256,
                    "run_id": run_id,
                }
            )
    return phi_edges


def compute_aggregate_fingerprints(
    *,
    structure_graph: Mapping[str, Any],
    vocabulary_snapshot: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """SECONDARY, coarse whole-Alpha edge-SET fingerprint -- Step 1's
    original computation, arithmetic UNCHANGED, renamed and reclassified
    as an aggregate diagnostic (never the primary phi identity; see the
    module docstring's Product Decision 6). One entry per (ticker,
    alpha_id) that has at least one linked edge -- exactly Step 1's
    original ``compute_phi_structures`` behavior, field-for-field
    identical except ``phi_id`` is renamed ``aggregate_fingerprint_id`` and
    ``identity_version`` reports ``AGGREGATE_FINGERPRINT_VERSION`` instead
    of the atomic edge version, so no consumer can mistake one for the
    other."""
    ticker = str(structure_graph.get("ticker") or "")
    run_id = str(structure_graph.get("run_id") or "")
    edges = structure_graph.get("edges")
    edges = edges if isinstance(edges, Sequence) else []
    vocabulary_snapshot = vocabulary_snapshot if isinstance(vocabulary_snapshot, Mapping) else {}
    taxonomy_version = vocabulary_snapshot.get("taxonomy_version")
    taxonomy_sha256 = vocabulary_snapshot.get("taxonomy_sha256")

    fingerprints: list[dict[str, Any]] = []
    for alpha_id in _alpha_ids_in_graph(edges):
        chain_edges = _canonical_chain_edges(edges, alpha_id)
        if not chain_edges:
            continue
        canonical_representation = {
            "identity_version": AGGREGATE_FINGERPRINT_VERSION,
            "ticker": ticker,
            "alpha_id": alpha_id,
            "taxonomy_version": taxonomy_version,
            "taxonomy_sha256": taxonomy_sha256,
            "chain_edges": [list(triple) for triple in chain_edges],
        }
        aggregate_fingerprint_id = _stable_digest(canonical_representation)
        fingerprints.append(
            {
                "aggregate_fingerprint_id": aggregate_fingerprint_id,
                "identity_version": AGGREGATE_FINGERPRINT_VERSION,
                "ticker": ticker,
                "alpha_id": alpha_id,
                "taxonomy_version": taxonomy_version,
                "taxonomy_sha256": taxonomy_sha256,
                "chain_edges": [list(triple) for triple in chain_edges],
                "run_id": run_id,
            }
        )
    return fingerprints


__all__ = [
    "PHI_EDGE_IDENTITY_VERSION",
    "AGGREGATE_FINGERPRINT_VERSION",
    "IDENTITY_MODEL",
    "compute_phi_edges",
    "compute_aggregate_fingerprints",
]
