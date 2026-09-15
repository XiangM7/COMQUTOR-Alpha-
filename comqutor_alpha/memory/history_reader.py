"""Alpha Memory Implementation Step 2 (SHADOW ONLY) -- cross-run history
reader, now operating on atomic edge phi identity as the primary matching
unit (Step 1's whole-Alpha-set matching is retained only as a secondary
aggregate-fingerprint comparison -- see phi_identity.py).

Read-only over already-persisted run artifacts under ``output_root``.
Never writes, never mutates a historical run's files, and is never
imported by activation_scorer_v2.py, alpha_level_classifier.py,
conflict_detector.py, or conflict_admissibility.py -- nothing in this
module can make current-run scoring depend on history.

Filesystem-based rather than DB-based by design, unchanged from Step 1: no
DB migration is added -- every fact this module needs is already
persisted in existing run artifacts.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from comqutor_alpha.memory.phi_identity import compute_aggregate_fingerprints, compute_phi_edges
from comqutor_alpha.storage.file_store import resolve_output_root


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _is_run_eligible_for_history(run_dir: Path) -> bool:
    """Implementation Step 3, Section E (run eligibility). Reuses the ONE
    existing, already-persisted, authoritative per-run completeness signal
    this codebase has -- artifact_manifest.json's own ``artifact_completeness``
    field (Sprint 1, Track A2; the same field routes_research.py's
    get_run_artifacts_response already treats as authoritative). A run
    whose manifest explicitly says anything other than "pass" is excluded
    -- exactly the case the task means by "existing metadata already
    identifies them as such". A run with NO manifest at all (it predates
    that sprint) is NOT excluded on that basis alone -- this module never
    invents a stricter "healthy run" standard than what production code
    already tracks; that would be a new eligibility rule, not a reused one.

    KNOWN LIMITATION, reported honestly rather than silently assumed away:
    this check does NOT catch every possible bad run. A concrete example
    found in this repository's own history -- run 40bd7e3d-2759-45bc-
    97ec-8f1cf96c2266 (NVDA), executed while Week2 LLM was disabled,
    producing zero committed Alpha matches and zero Activation (see
    scripts/start_live_comqutor.sh's own docstring) -- has
    artifact_completeness == "pass" (its files are all present; they are
    just semantically empty). No existing authoritative field distinguishes
    "complete but semantically empty" from "complete and meaningful". That
    specific failure mode is instead caught incidentally by this module's
    own pre-existing requirement to have real, alpha_ids-linked edges to
    derive a phi from at all (compute_phi_edges returns [] for such a run,
    so it contributes zero phi structures and can never produce a false
    match) -- not by this eligibility filter. This is reported as a real
    gap, not silently patched over with an invented "healthy run" rule."""
    manifest = _load_json_if_exists(run_dir / "artifact_manifest.json")
    if not manifest:
        return True
    return manifest.get("artifact_completeness") == "pass"


def find_ticker_run_ids(
    *, ticker: str, output_root: str | Path, exclude_run_id: str | None = None
) -> list[str]:
    """Every run_id directly under ``output_root`` whose own metadata.json
    ticker matches (case-insensitive), excluding ``exclude_run_id`` and any
    run this ticker's own persisted artifact_manifest.json already marks
    incomplete (see ``_is_run_eligible_for_history``). Deterministic
    ordering (sorted by directory name) -- callers that need recency order
    combine this with each run's own metadata.json created_at (see
    ``summarize_phi_edge_history``); this function itself never guesses at
    ordering from anything but directory listing."""
    root = resolve_output_root(output_root)
    if not root.is_dir():
        return []
    ticker_upper = ticker.upper()
    matches: list[str] = []
    for run_dir in sorted(root.iterdir()):
        if not run_dir.is_dir():
            continue
        run_id = run_dir.name
        if exclude_run_id is not None and run_id == exclude_run_id:
            continue
        metadata = _load_json_if_exists(run_dir / "metadata.json")
        if str(metadata.get("ticker") or "").upper() != ticker_upper:
            continue
        if not _is_run_eligible_for_history(run_dir):
            continue
        matches.append(run_id)
    return matches


def _load_run_artifacts(run_id: str, output_root: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    run_dir = resolve_output_root(output_root) / run_id
    structure_graph = _load_json_if_exists(run_dir / "structure_graph.json")
    vocabulary_snapshot = _load_json_if_exists(
        run_dir / "tradingagents_comqutor_vocabulary_snapshot.json"
    )
    return structure_graph, vocabulary_snapshot


def load_phi_edges_for_run(*, run_id: str, output_root: str | Path) -> list[dict[str, Any]]:
    """Recomputes (never caches/persists) one run's atomic phi edges fresh
    from its own already-persisted structure_graph.json +
    tradingagents_comqutor_vocabulary_snapshot.json. Returns ``[]`` for a
    run with no persisted Structure Graph (e.g. a failed/incomplete run) --
    never fabricated."""
    structure_graph, vocabulary_snapshot = _load_run_artifacts(run_id, output_root)
    if not structure_graph:
        return []
    return compute_phi_edges(structure_graph=structure_graph, vocabulary_snapshot=vocabulary_snapshot)


def load_aggregate_fingerprints_for_run(*, run_id: str, output_root: str | Path) -> list[dict[str, Any]]:
    """Same as ``load_phi_edges_for_run`` but for the secondary,
    whole-Alpha aggregate fingerprint (Step 1's original computation,
    renamed -- see phi_identity.compute_aggregate_fingerprints)."""
    structure_graph, vocabulary_snapshot = _load_run_artifacts(run_id, output_root)
    if not structure_graph:
        return []
    return compute_aggregate_fingerprints(structure_graph=structure_graph, vocabulary_snapshot=vocabulary_snapshot)


def find_prior_phi_edge_observations(
    *, phi_id: str, ticker: str, current_run_id: str, output_root: str | Path
) -> list[dict[str, Any]]:
    """Every OTHER already-persisted, history-eligible run (same ticker,
    excluding ``current_run_id``) whose own Structure Graph independently
    produces this exact atomic ``phi_id``. Read-only: loads other runs'
    already-written artifacts, never modifies them. Primary historical-
    matching entry point as of Implementation Step 2 -- historical matching
    no longer requires an entire Alpha edge-set to agree; a match on one
    atomic phi_id is sufficient.

    Implementation Step 3, Section F (duplicate/multiple observation
    rule): deduplicated by ``(run_id, phi_id)`` before being returned --
    one run counts at most once, even if a future graph representation
    were ever to derive the same phi_id from more than one edge row within
    that single run (compute_phi_edges already de-duplicates within a run
    by construction, so this is an explicit second guarantee, not reliance
    on that internal detail alone)."""
    seen_run_ids: set[str] = set()
    observations: list[dict[str, Any]] = []
    for run_id in find_ticker_run_ids(ticker=ticker, output_root=output_root, exclude_run_id=current_run_id):
        if run_id in seen_run_ids:
            continue
        for edge in load_phi_edges_for_run(run_id=run_id, output_root=output_root):
            if edge["phi_id"] == phi_id:
                observations.append(edge)
                seen_run_ids.add(run_id)
                break  # (run_id, phi_id) counted once -- do not scan this run's remaining edges
    return observations


def _created_at_for_runs(run_ids: list[str], output_root: str | Path) -> list[str]:
    timestamps: list[str] = []
    for run_id in run_ids:
        metadata = _load_json_if_exists(resolve_output_root(output_root) / run_id / "metadata.json")
        created_at = metadata.get("created_at")
        if isinstance(created_at, str) and created_at:
            timestamps.append(created_at)
    return timestamps


def summarize_phi_edge_history(
    *, phi_edge: dict[str, Any], current_run_id: str, output_root: str | Path
) -> dict[str, Any]:
    """Implementation Step 3 -- the deterministic, read-only historical
    OBSERVATION summary for one already-computed atomic phi edge of the
    CURRENT run. Descriptive only: never a score, never a weight, never a
    reward/penalty. Never fabricates a missing timestamp -- every *_seen*
    field is ``None`` when no real metadata.json carries a ``created_at``.

    Recurrence definition (Section D, deliberately narrow): a phi is
    recurring if and only if the exact same phi_id exists in at least one
    prior history-eligible run -- ``is_recurring = prior_observation_count
    >= 1``. No fuzzy/semantic/edge-type/Alpha equivalence, no recurrence
    strength, confidence, weight, streak, or decay -- none of those
    concepts exist in this function's output.

    ABSENCE IS NOT AN EVENT (Section H): this function records POSITIVE
    OBSERVATIONS ONLY. A phi missing from some run between two
    observations is never interpreted as expired/invalidated/failed --
    the chronology fields below name only what was actually observed
    (first_seen, last_seen_prior, current_seen_at), never a claim of
    continuity between them."""
    phi_id = phi_edge["phi_id"]
    ticker = phi_edge["ticker"]
    prior = find_prior_phi_edge_observations(
        phi_id=phi_id, ticker=ticker, current_run_id=current_run_id, output_root=output_root
    )
    prior_run_ids = sorted({observation["run_id"] for observation in prior})
    prior_timestamps = _created_at_for_runs(prior_run_ids, output_root)
    current_metadata = _load_json_if_exists(resolve_output_root(output_root) / current_run_id / "metadata.json")
    current_created_at = current_metadata.get("created_at")
    current_seen_at = current_created_at if isinstance(current_created_at, str) and current_created_at else None

    # first_seen is the earliest REAL timestamp across every observation of
    # this exact phi_id, prior or current -- never fabricated when neither
    # is available. Section G: no inference of continuity is made between
    # first_seen and last_seen_prior/current_seen_at.
    all_known_timestamps = list(prior_timestamps)
    if current_seen_at:
        all_known_timestamps.append(current_seen_at)

    prior_observation_count = len(prior_run_ids)
    has_prior_observation = prior_observation_count >= 1
    return {
        "phi_id": phi_id,
        "ticker": ticker,
        "alpha_id": phi_edge["alpha_id"],
        "source": phi_edge["source"],
        "edge_type": phi_edge["edge_type"],
        "target": phi_edge["target"],
        "current_run_id": current_run_id,
        "prior_run_ids": prior_run_ids,
        "prior_observation_count": prior_observation_count,
        # total_observation_count includes the current run's own sighting
        # -- prior observations plus this one.
        "total_observation_count": prior_observation_count + 1,
        "has_prior_observation": has_prior_observation,
        "is_recurring": has_prior_observation,  # Section D: identical definition, exposed under its own name
        "first_seen": min(all_known_timestamps) if all_known_timestamps else None,
        "last_seen_prior": max(prior_timestamps) if prior_timestamps else None,
        "current_seen_at": current_seen_at,
        "identity_version": phi_edge["identity_version"],
        "taxonomy_version": phi_edge["taxonomy_version"],
        "taxonomy_sha256": phi_edge["taxonomy_sha256"],
    }


def build_phi_structures(
    *, current_run_id: str, structure_graph: dict[str, Any], vocabulary_snapshot: dict[str, Any] | None,
    output_root: str | Path,
) -> list[dict[str, Any]]:
    """Combines compute_phi_edges (identity) with summarize_phi_edge_history
    (cross-run history) into one record per atomic phi -- the
    ``phi_structures`` list exposed on run_audit.json's alpha_memory
    section. Pure orchestration: no new computation of its own."""
    phi_edges = compute_phi_edges(structure_graph=structure_graph, vocabulary_snapshot=vocabulary_snapshot)
    structures = []
    for phi_edge in phi_edges:
        history = summarize_phi_edge_history(
            phi_edge=phi_edge, current_run_id=current_run_id, output_root=output_root
        )
        structures.append({**phi_edge, **history})
    return structures


def summarize_alpha_memory(phi_structures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Descriptive-only, per-Alpha aggregate rollup of already-computed
    phi_structures. NEVER a score, weight, or confidence -- purely a count
    summary of how many of an Alpha's current atomic phi tokens have any
    historical precedent (Implementation Step 3, Section I).

    ``recurrence_ratio`` is a plain descriptive fraction
    (recurring_phi_count / current_phi_count) -- it is not activation
    confidence, not Alpha confidence, not an exposure score, and not a
    memory weight, and it is never consumed by activation_scorer_v2.py,
    alpha_level_classifier.py, conflict_detector.py, or
    conflict_admissibility.py (see the architectural import guard test)."""
    by_alpha: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for structure in phi_structures:
        by_alpha[structure["alpha_id"]].append(structure)

    summaries = []
    for alpha_id in sorted(by_alpha):
        structures = by_alpha[alpha_id]
        current_phi_count = len(structures)
        recurring = [s for s in structures if s.get("is_recurring")]
        recurring_phi_count = len(recurring)
        first_seen_phi_count = current_phi_count - recurring_phi_count
        summaries.append(
            {
                "alpha_id": alpha_id,
                "current_phi_count": current_phi_count,
                "first_seen_phi_count": first_seen_phi_count,
                "recurring_phi_count": recurring_phi_count,
                # Retained from Step 2 for backward compatibility -- an
                # exact alias of recurring_phi_count/current_phi_count-len
                # under their Step 2 names.
                "historically_matched_phi_count": recurring_phi_count,
                "unmatched_phi_count": first_seen_phi_count,
                "recurrence_ratio": (recurring_phi_count / current_phi_count) if current_phi_count > 0 else None,
                "prior_observation_total": sum(s.get("prior_observation_count", 0) for s in structures),
            }
        )
    return summaries


# ---------------------------------------------------------------------------
# Instability signals (audit-only diagnostics). No merging, no equivalence
# inference, no scoring, no penalty, no reinforcement -- these report raw
# observed variants and their source run_ids, nothing else. Never
# consulted by, and never returning anything consumable as, an activation/
# conflict/evidence input.
# ---------------------------------------------------------------------------


def detect_alpha_attribution_variance(
    *, ticker: str, output_root: str | Path, run_ids: list[str] | None = None
) -> list[dict[str, Any]]:
    """For the same (ticker, source, edge_type, target), reports every
    distinct alpha_ids set observed across the given runs (default: every
    persisted run for this ticker) and which run_id(s) produced each
    variant. Purely observational -- never labels one variant correct,
    never merges them, never produces a score."""
    candidate_run_ids = run_ids if run_ids is not None else find_ticker_run_ids(ticker=ticker, output_root=output_root)
    variants_by_edge: dict[tuple[str, str, str], dict[frozenset, list[str]]] = defaultdict(lambda: defaultdict(list))
    for run_id in candidate_run_ids:
        structure_graph, _ = _load_run_artifacts(run_id, output_root)
        for edge in structure_graph.get("edges") or []:
            if not isinstance(edge, dict):
                continue
            source, target, edge_type = edge.get("source"), edge.get("target"), edge.get("edge_type")
            if not source or not target:
                continue
            alpha_ids = frozenset(str(a) for a in (edge.get("alpha_ids") or ()) if a)
            variants_by_edge[(str(source), str(edge_type or ""), str(target))][alpha_ids].append(run_id)

    signals = []
    for (source, edge_type, target), variants in sorted(variants_by_edge.items()):
        if len(variants) <= 1:
            continue
        signals.append(
            {
                "ticker": ticker,
                "source": source,
                "edge_type": edge_type,
                "target": target,
                "alpha_attribution_variance_detected": True,
                "observed_variants": [
                    {"alpha_ids": sorted(alpha_ids), "run_ids": sorted(set(run_ids_for_variant))}
                    for alpha_ids, run_ids_for_variant in sorted(variants.items(), key=lambda kv: sorted(kv[0]))
                ],
            }
        )
    return signals


def detect_edge_type_variance(
    *, ticker: str, output_root: str | Path, run_ids: list[str] | None = None
) -> list[dict[str, Any]]:
    """For the same (ticker, source, target), reports every distinct
    edge_type observed across the given runs and which run_id(s) produced
    each variant. Purely observational -- never labels one variant
    correct, never merges them, never produces a score."""
    candidate_run_ids = run_ids if run_ids is not None else find_ticker_run_ids(ticker=ticker, output_root=output_root)
    variants_by_pair: dict[tuple[str, str], dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for run_id in candidate_run_ids:
        structure_graph, _ = _load_run_artifacts(run_id, output_root)
        for edge in structure_graph.get("edges") or []:
            if not isinstance(edge, dict):
                continue
            source, target, edge_type = edge.get("source"), edge.get("target"), edge.get("edge_type")
            if not source or not target:
                continue
            variants_by_pair[(str(source), str(target))][str(edge_type or "")].append(run_id)

    signals = []
    for (source, target), variants in sorted(variants_by_pair.items()):
        if len(variants) <= 1:
            continue
        signals.append(
            {
                "ticker": ticker,
                "source": source,
                "target": target,
                "edge_type_variance_detected": True,
                "observed_variants": [
                    {"edge_type": edge_type, "run_ids": sorted(set(run_ids_for_variant))}
                    for edge_type, run_ids_for_variant in sorted(variants.items())
                ],
            }
        )
    return signals


__all__ = [
    "find_ticker_run_ids",
    "load_phi_edges_for_run",
    "load_aggregate_fingerprints_for_run",
    "find_prior_phi_edge_observations",
    "summarize_phi_edge_history",
    "build_phi_structures",
    "summarize_alpha_memory",
    "detect_alpha_attribution_variance",
    "detect_edge_type_variance",
]
