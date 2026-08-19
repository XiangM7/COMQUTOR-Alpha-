"""QA Closure v0.1.2 Item 6: nine-artifact bundle completeness audit and
safe, provenance-tracked reconstruction.

Two independent concerns, kept separate:

  * ``check_artifact_bundle`` -- pure, read-only. Verifies a run directory
    has all nine required core artifacts (see
    ``comqutor_alpha.api.artifact_export.REQUIRED_ARTIFACT_FILENAMES``,
    reused verbatim, never redefined here), each present, non-empty,
    valid JSON, and identity-consistent (``run_id``/``ticker`` fields, when
    present on that artifact, must match the selected run).

  * ``reconstruct_missing_artifacts`` -- writes ``evidence_facts.json``/
    ``alpha_activations.json``/``conflicts.json``/``run_audit.json`` ONLY
    when genuinely absent, using ONLY this run's own already-present,
    undisputed ``structure_graph.json``/``alpha_matches.json`` as source
    (never Architecture Replay's from-raw-text rebuild, which re-derives
    Alpha matches from scratch and can disagree with the already-persisted
    ``alpha_matches.json`` -- see the QA Item 6 report for a real observed
    case). Reuses the official, already-existing A2 export functions
    (``comqutor_alpha.api.artifact_export.extract_*_export``,
    ``comqutor_alpha.conflict_engine.conflict_detector.
    detect_alpha_conflicts``, ``comqutor_alpha.api.routes_research.
    build_run_audit_payload``) verbatim -- never a parallel/invented
    exporter, never a second B1/B2/B4 computation with different
    semantics. Never overwrites a file that already exists.

Zero Provider calls, zero TradingAgents calls, zero LLM calls anywhere in
this module's own code or import graph.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from comqutor_alpha.api.artifact_export import (
    REQUIRED_ARTIFACT_FILENAMES,
    extract_alpha_activations_export,
    extract_conflicts_export,
    extract_evidence_facts_export,
)
from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts
from comqutor_alpha.storage.file_store import run_dir_for, save_json_record

SCHEMA_VERSION = "artifact_bundle_audit.v1"

BUNDLE_STATUS_COMPLETE_ORIGINAL = "complete_original"
BUNDLE_STATUS_COMPLETE_RECONSTRUCTED = "complete_reconstructed"
BUNDLE_STATUS_INCOMPLETE_HISTORICAL = "incomplete_historical"
BUNDLE_STATUS_BLOCKED_MISSING_SOURCE_DATA = "blocked_missing_source_data"

# Artifacts this module knows how to safely reconstruct, and the source
# artifact(s) each one's reconstruction reads (never raw_agent_outputs.json
# re-derivation, never a fresh Alpha-Mapper/B1 pass).
RECONSTRUCTABLE_ARTIFACTS = ("evidence_facts.json", "alpha_activations.json", "conflicts.json", "run_audit.json")
# metadata.json/raw_agent_outputs.json/structured_agent_outputs.json/
# alpha_matches.json/structure_graph.json are never reconstructed by this
# module -- see task section 4.1-4.3/4.5/4.6 and the module docstring.
NEVER_RECONSTRUCTED_ARTIFACTS = tuple(n for n in REQUIRED_ARTIFACT_FILENAMES if n not in RECONSTRUCTABLE_ARTIFACTS)


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Returns (payload, error) -- exactly one is None. Never raises."""
    if not path.exists():
        return None, "MISSING"
    if path.stat().st_size == 0:
        return None, "ZERO_BYTE"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, "INVALID_JSON"
    if not isinstance(payload, Mapping):
        return None, "INVALID_JSON"
    return dict(payload), None


def check_artifact_bundle(run_id: str, ticker: str, output_root: str = "outputs/runs") -> dict[str, Any]:
    """Read-only completeness + validity + identity check. Never writes
    anything. ``per_artifact`` reports one of MISSING/ZERO_BYTE/
    INVALID_JSON/RUN_ID_MISMATCH/TICKER_MISMATCH/OK per required filename."""
    run_dir = run_dir_for(run_id, output_root)
    ticker_upper = str(ticker).upper()

    per_artifact: dict[str, str] = {}
    present: list[str] = []
    missing: list[str] = []

    for name in REQUIRED_ARTIFACT_FILENAMES:
        payload, error = _load_json(run_dir / name)
        if error is not None:
            per_artifact[name] = error
            missing.append(name)
            continue
        artifact_run_id = payload.get("run_id")
        artifact_ticker = payload.get("ticker")
        if artifact_run_id is not None and str(artifact_run_id) != str(run_id):
            per_artifact[name] = "RUN_ID_MISMATCH"
            missing.append(name)
            continue
        if artifact_ticker is not None and str(artifact_ticker).upper() != ticker_upper:
            per_artifact[name] = "TICKER_MISMATCH"
            missing.append(name)
            continue
        per_artifact[name] = "OK"
        present.append(name)

    return {
        "run_id": run_id,
        "ticker": ticker_upper,
        "artifact_folder": str(run_dir),
        "required_artifact_count": len(REQUIRED_ARTIFACT_FILENAMES),
        "present_artifact_count": len(present),
        "present_artifacts": present,
        "missing_artifacts": missing,
        "per_artifact_status": per_artifact,
    }


def reconstruct_missing_artifacts(
    run_id: str, ticker: str, output_root: str = "outputs/runs", *, dry_run: bool = False
) -> dict[str, Any]:
    """Writes only the required artifacts that are genuinely absent,
    reusing the official extraction functions against this run's own
    already-present ``structure_graph.json``/``alpha_matches.json`` --
    never overwrites a file that already exists, never touches
    ``metadata.json``/``raw_agent_outputs.json``/
    ``structured_agent_outputs.json``/``alpha_matches.json``/
    ``structure_graph.json``. ``dry_run=True`` computes and reports
    exactly what would be written without writing anything (used by
    tests and by the pre-flight safety check)."""
    run_dir = run_dir_for(run_id, output_root)
    before = check_artifact_bundle(run_id, ticker, output_root)

    graph_payload, graph_error = _load_json(run_dir / "structure_graph.json")
    matches_payload, matches_error = _load_json(run_dir / "alpha_matches.json")

    reconstructed: list[str] = []
    blocked: dict[str, str] = {}

    if graph_error is not None or matches_error is not None:
        # Neither evidence_facts.json/alpha_activations.json/conflicts.json
        # can be honestly reconstructed without both authoritative source
        # artifacts already present for this same run -- report the exact
        # blocker rather than guessing or fabricating.
        for name in ("evidence_facts.json", "alpha_activations.json", "conflicts.json"):
            if name in before["missing_artifacts"]:
                blocked[name] = f"structure_graph.json={graph_error or 'OK'}, alpha_matches.json={matches_error or 'OK'}"
        conflict_payload = None
    else:
        conflict_payload = None
        if "evidence_facts.json" in before["missing_artifacts"]:
            export = extract_evidence_facts_export(
                graph_payload, run_id=run_id, ticker=ticker, alpha_matches_payload=matches_payload
            )
            if not dry_run:
                save_json_record(run_id, "evidence_facts.json", export, output_root=output_root)
            reconstructed.append("evidence_facts.json")

        if "alpha_activations.json" in before["missing_artifacts"]:
            export = extract_alpha_activations_export(graph_payload, run_id=run_id, ticker=ticker)
            if not dry_run:
                save_json_record(run_id, "alpha_activations.json", export, output_root=output_root)
            reconstructed.append("alpha_activations.json")

        if "conflicts.json" in before["missing_artifacts"]:
            activation_payload = graph_payload.get("activation")
            matches = matches_payload.get("matches")
            if not isinstance(activation_payload, Mapping) or not isinstance(matches, list):
                blocked["conflicts.json"] = "structure_graph.json['activation'] or alpha_matches.json['matches'] missing/malformed"
            else:
                conflict_payload = detect_alpha_conflicts(
                    run_id=run_id, ticker=ticker, activation_payload=activation_payload, alpha_matches=matches
                )
                export = extract_conflicts_export(conflict_payload, run_id=run_id, ticker=ticker)
                if export is not None:
                    if not dry_run:
                        save_json_record(run_id, "conflicts.json", export, output_root=output_root)
                    reconstructed.append("conflicts.json")

    if "run_audit.json" in before["missing_artifacts"] and not dry_run:
        # Imported lazily: routes_research has a much larger import graph
        # than this focused module needs for every other function above.
        from comqutor_alpha.api.routes_research import build_run_audit_payload

        audit = build_run_audit_payload(run_id, output_root)
        save_json_record(run_id, "run_audit.json", audit, output_root=output_root)
        reconstructed.append("run_audit.json")
    elif "run_audit.json" in before["missing_artifacts"] and dry_run:
        reconstructed.append("run_audit.json")

    after = before if dry_run else check_artifact_bundle(run_id, ticker, output_root)

    return {
        "run_id": run_id,
        "ticker": str(ticker).upper(),
        "dry_run": dry_run,
        "pre_existing_artifacts": before["present_artifacts"],
        "reconstructed_artifacts": reconstructed,
        "blocked_artifacts": blocked,
        "post_missing_artifacts": [
            name
            for name in before["missing_artifacts"]
            if name not in reconstructed and name not in NEVER_RECONSTRUCTED_ARTIFACTS
        ]
        if dry_run
        else after["missing_artifacts"],
        "provider_calls": 0,
        "tradingagents_calls": 0,
    }


def classify_bundle_status(before: Mapping[str, Any], reconstruction: Mapping[str, Any] | None) -> str:
    """Task section 2's exact four-value vocabulary. Never
    ``complete_original`` when any file was actually reconstructed."""
    if not before["missing_artifacts"]:
        return BUNDLE_STATUS_COMPLETE_ORIGINAL
    if reconstruction is None or not reconstruction["reconstructed_artifacts"]:
        remaining = (
            before["missing_artifacts"]
            if reconstruction is None
            else reconstruction.get("post_missing_artifacts", before["missing_artifacts"])
        )
        if remaining and reconstruction is not None and reconstruction.get("blocked_artifacts"):
            return BUNDLE_STATUS_BLOCKED_MISSING_SOURCE_DATA
        return BUNDLE_STATUS_INCOMPLETE_HISTORICAL
    post_missing = reconstruction.get("post_missing_artifacts", [])
    if post_missing:
        return (
            BUNDLE_STATUS_BLOCKED_MISSING_SOURCE_DATA
            if reconstruction.get("blocked_artifacts")
            else BUNDLE_STATUS_INCOMPLETE_HISTORICAL
        )
    return BUNDLE_STATUS_COMPLETE_RECONSTRUCTED


def build_bundle_manifest(
    run_id: str, ticker: str, output_root: str, *, pre_existing: list[str], reconstruction: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Assembles the section-10 manifest shape from already-computed
    before/after state -- never recomputes the check itself."""
    after = check_artifact_bundle(run_id, ticker, output_root)
    before_snapshot = {"missing_artifacts": [n for n in REQUIRED_ARTIFACT_FILENAMES if n not in pre_existing]}
    status = classify_bundle_status(before_snapshot, reconstruction)
    return {
        "schema_version": SCHEMA_VERSION,
        "ticker": str(ticker).upper(),
        "run_id": run_id,
        "bundle_status": status,
        "required_count": len(REQUIRED_ARTIFACT_FILENAMES),
        "present_count": after["present_artifact_count"],
        "original_artifacts": sorted(pre_existing),
        "reconstructed_artifacts": sorted((reconstruction or {}).get("reconstructed_artifacts") or []),
        "missing_artifacts": after["missing_artifacts"],
        "blocked_artifacts": (reconstruction or {}).get("blocked_artifacts") or {},
        "provider_calls": 0,
        "tradingagents_calls": 0,
    }


__all__ = [
    "SCHEMA_VERSION",
    "BUNDLE_STATUS_COMPLETE_ORIGINAL",
    "BUNDLE_STATUS_COMPLETE_RECONSTRUCTED",
    "BUNDLE_STATUS_INCOMPLETE_HISTORICAL",
    "BUNDLE_STATUS_BLOCKED_MISSING_SOURCE_DATA",
    "RECONSTRUCTABLE_ARTIFACTS",
    "NEVER_RECONSTRUCTED_ARTIFACTS",
    "check_artifact_bundle",
    "reconstruct_missing_artifacts",
    "classify_bundle_status",
    "build_bundle_manifest",
]
