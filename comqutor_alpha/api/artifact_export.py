"""Sprint 1 -- Run Identity Integrity and Complete Artifact Export,
Track A2: canonical artifact export builders and the run-completion
artifact finalizer.

Every builder here extracts an already-computed payload -- never
recomputes Activation, Conflict, or Evidence Fact grouping. See the
sprint boundary: "不得重新分组 claims", "不得分别重算 Conflict",
"不得重新调用 scorer".
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from comqutor_alpha.api.unclassified_findings import (
    ARTIFACT_FILENAME as UNCLASSIFIED_FINDINGS_FILENAME,
    build_unclassified_findings_export,
)
from comqutor_alpha.conflict_engine.conflict_admissibility import CANDIDATE as B2_CANDIDATE
from comqutor_alpha.storage.file_store import run_dir_for, save_json_record
from comqutor_alpha.structure_engine.evidence_stance import (
    CLASSIFIER_VERSION as EVIDENCE_STANCE_VERSION,
)
from comqutor_alpha.structure_engine.evidence_stance_llm import (
    STANCE_METHOD_LLM,
    VALID_FALLBACK_REASONS,
)

EVIDENCE_FACTS_EXPORT_SCHEMA_VERSION = "evidence_facts.export.v1"
ALPHA_ACTIVATIONS_EXPORT_SCHEMA_VERSION = "alpha_activations.export.v1"
CONFLICTS_EXPORT_SCHEMA_VERSION = "conflicts.export.v1"
RESEARCH_SUMMARY_EXPORT_SCHEMA_VERSION = "research_summary.export.v1"
ARTIFACT_MANIFEST_EXPORT_SCHEMA_VERSION = "artifact_manifest.export.v1"
# Sprint 2 (Alpha-Relative Evidence Stance Classification), Track B1.
EVIDENCE_STANCE_AUDIT_SCHEMA_VERSION = "evidence_stance_audit.v1"
EVIDENCE_STANCE_AUDIT_FILENAME = "evidence_stance_audit.json"

# John's 9 required artifacts for every new completed run (section 6).
REQUIRED_ARTIFACT_FILENAMES = (
    "metadata.json",
    "raw_agent_outputs.json",
    "structured_agent_outputs.json",
    "evidence_facts.json",
    "alpha_matches.json",
    "structure_graph.json",
    "alpha_activations.json",
    "conflicts.json",
    "run_audit.json",
)
# Architecture Replay's own required set (section 10) -- deliberately
# excludes "raw_agent_outputs.json": a replay bundle intentionally never
# copies the source run's raw artifact (see metadata.json's own
# source_raw_artifact_path/source_raw_sha256 lineage fields instead), so
# requiring a physical copy here would be a fabricated completeness
# requirement, not a real one.
REPLAY_REQUIRED_ARTIFACT_FILENAMES = tuple(
    name for name in REQUIRED_ARTIFACT_FILENAMES if name != "raw_agent_outputs.json"
)
# COMQUTOR's current product also exports these (section 6, "COMQUTOR
# 当前产品还应导出") -- tracked separately since they are not part of
# John's 9-artifact required set, but are still validated/manifested.
# evidence_stance_audit.json (Sprint 2, Track B1) joins this set rather
# than REQUIRED_ARTIFACT_FILENAMES: it must never change John's existing
# artifact_completeness / "completed" status gate for Sprint 1 (section 8,
# "不得修改... Live-run completed gating").
# Sprint 3 (Unclassified Findings Control), Track A3: additive claim-level
# audit artifact -- joins entity structured_agent_outputs.json/
# alpha_matches.json/evidence_facts.json, never re-groups or re-scores
# anything. Joins this set rather than REQUIRED_ARTIFACT_FILENAMES for the
# exact same reason evidence_stance_audit.json does: it must never change
# John's existing artifact_completeness / "completed" status gate.
PRODUCT_EXTENSION_ARTIFACT_FILENAMES = (
    "entity_alpha_exposures.json",
    "summary.json",
    EVIDENCE_STANCE_AUDIT_FILENAME,
    UNCLASSIFIED_FINDINGS_FILENAME,
)
# Written last, once every other artifact above already exists.
MANIFEST_ARTIFACT_FILENAME = "artifact_manifest.json"
# Replay-only legacy filename, preserved for backward compatibility --
# never deleted or renamed. conflicts.json is the new canonical export;
# both come from the exact same in-memory conflict payload.
CONFLICT_RESULTS_COMPATIBILITY_FILENAME = "conflict_results.json"

ARTIFACT_COMPLETENESS_PASS = "pass"
ARTIFACT_COMPLETENESS_FAIL = "fail"


class RunArtifactFinalizationError(Exception):
    """A required export step itself failed (write error, malformed
    already-computed input) -- distinct from an artifact-completeness or
    ticker-consistency *result* that is merely reported."""

    reason_code = "RUN_ARTIFACT_FINALIZATION_FAILED"


class RunArtifactIncompleteError(Exception):
    reason_code = "RUN_ARTIFACT_INCOMPLETE"


class RunTickerConsistencyError(Exception):
    reason_code = "RUN_TICKER_CONSISTENCY_FAILED"


def _v2_alphas(graph_payload: Any) -> list[dict]:
    versions = graph_payload.get("activation_versions") if isinstance(graph_payload, dict) else None
    block = versions.get("v2") if isinstance(versions, dict) else None
    alphas = block.get("alphas") if isinstance(block, dict) else None
    return [a for a in alphas if isinstance(a, dict)] if isinstance(alphas, list) else []


def _claim_alpha_stance_index(alpha_matches_payload: Any) -> dict[tuple[str, str], dict[str, Any]]:
    """(claim_id, alpha_id) -> Evidence Stance fields already attached to
    each candidate by alpha_mapper._attach_evidence_stance (Sprint 2, Track
    B1). Pure lookup-table construction -- never reclassifies anything."""
    index: dict[tuple[str, str], dict[str, Any]] = {}
    matches = alpha_matches_payload.get("matches") if isinstance(alpha_matches_payload, dict) else None
    if not isinstance(matches, list):
        return index
    for record in matches:
        if not isinstance(record, dict):
            continue
        claim_id = record.get("claim_id")
        if not claim_id:
            continue
        for candidate in record.get("candidate_scores") or []:
            if not isinstance(candidate, dict):
                continue
            alpha_id = candidate.get("alpha_id")
            if not alpha_id or "evidence_stance" not in candidate:
                continue
            index[(str(claim_id), str(alpha_id))] = {
                "evidence_stance": candidate.get("evidence_stance"),
                "requires_manual_review": bool(candidate.get("requires_manual_review")),
            }
    return index


def _alpha_stances_for_group(
    alpha_ids: list[str],
    representative_claim_id: str | None,
    member_claim_ids: list[str],
    stance_index: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Additive, Alpha-relative stance aggregation for one Evidence Fact
    group -- reads stances already classified per (claim, alpha) by the
    Mapper; never re-groups members and never re-classifies. Section 12."""
    alpha_stances: dict[str, dict[str, Any]] = {}
    for alpha_id in alpha_ids:
        member_stances: list[str] = []
        member_review_flags: list[bool] = []
        counts = dict.fromkeys(("supports_alpha", "opposes_alpha", "mentions_alpha", "neutral_background", "supports_counter_alpha"), 0)
        for claim_id in member_claim_ids:
            entry = stance_index.get((str(claim_id), str(alpha_id)))
            if entry is None or entry.get("evidence_stance") is None:
                continue
            stance = entry["evidence_stance"]
            member_stances.append(stance)
            member_review_flags.append(bool(entry.get("requires_manual_review")))
            if stance in counts:
                counts[stance] += 1
        representative_entry = stance_index.get((str(representative_claim_id), str(alpha_id))) if representative_claim_id else None
        representative_stance = representative_entry.get("evidence_stance") if representative_entry else None
        mixed_member_stances = len(set(member_stances)) > 1
        alpha_stances[alpha_id] = {
            "representative_stance": representative_stance,
            "member_stance_counts": counts,
            "mixed_member_stances": mixed_member_stances,
            "requires_manual_review": mixed_member_stances or any(member_review_flags),
        }
    return alpha_stances


def extract_evidence_facts_export(
    graph_payload: dict, *, run_id: str, ticker: str, alpha_matches_payload: Any = None
) -> dict:
    """Unions every v2 alpha's already-computed ``evidence_fact_groups``
    list (a permanent, additive extraction of the same ``_group_evidence``
    result Activation v2 already computes for scoring -- see
    ``activation_scorer_v2.score_alpha_v2``), deduped by
    ``evidence_fact_group_id`` -- never a second grouping pass over raw
    claims.

    ``alpha_matches_payload`` is optional and purely additive (Sprint 2,
    Track B1): when supplied, each group also gets an ``alpha_stances``
    dict aggregating the Evidence Stance already classified per
    (claim, alpha) by the Alpha Mapper. Omitting it reproduces the exact
    Sprint 1 output -- backward compatible for any existing caller."""
    groups_by_id: dict[str, dict[str, Any]] = {}
    for alpha in _v2_alphas(graph_payload):
        alpha_id = alpha.get("alpha_id")
        fact_groups = alpha.get("evidence_fact_groups")
        if not isinstance(fact_groups, list):
            continue
        for fact in fact_groups:
            if not isinstance(fact, dict):
                continue
            group_id = fact.get("evidence_fact_group_id")
            if not group_id:
                continue
            entry = groups_by_id.setdefault(
                group_id,
                {
                    "evidence_fact_group_id": group_id,
                    "ticker": ticker,
                    "representative_claim_id": fact.get("representative_claim_id"),
                    "member_claim_ids": sorted(fact.get("member_claim_ids") or []),
                    "supporting_agents": sorted(fact.get("supporting_agents") or []),
                    "supporting_alpha_ids": [],
                },
            )
            if alpha_id and alpha_id not in entry["supporting_alpha_ids"]:
                entry["supporting_alpha_ids"].append(alpha_id)

    groups = [groups_by_id[key] for key in sorted(groups_by_id)]
    for group in groups:
        group["supporting_alpha_ids"] = sorted(group["supporting_alpha_ids"])

    if alpha_matches_payload is not None:
        stance_index = _claim_alpha_stance_index(alpha_matches_payload)
        for group in groups:
            group["alpha_stances"] = _alpha_stances_for_group(
                group["supporting_alpha_ids"],
                group["representative_claim_id"],
                group["member_claim_ids"],
                stance_index,
            )

    return {
        "schema_version": EVIDENCE_FACTS_EXPORT_SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "grouping_method": "evidence_fact_index.v1",
        "unique_evidence_fact_count": len(groups),
        "groups": groups,
    }


def extract_alpha_activations_export(graph_payload: dict, *, run_id: str, ticker: str) -> dict:
    """Direct extraction of the already-computed primary Activation
    payload -- never a second call into the scorer."""
    return {
        "schema_version": ALPHA_ACTIVATIONS_EXPORT_SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "primary_activation_version": graph_payload.get("primary_activation_version"),
        "activation": graph_payload.get("activation"),
        "activation_versions": graph_payload.get("activation_versions"),
    }


def _candidate_conflicts(conflict_payload: dict) -> list[dict]:
    """John's B2 Conflict Evidence Admissibility gate: the taxonomy-declared
    pairs that reached B2 evaluation but were denied admission, read
    straight off the already-computed
    ``arbitration.candidate_evaluations[*].admissibility`` -- never a second
    admissibility evaluation. A pair suppressed/rejected before ever
    reaching B2 (e.g. missing evidence, unresolved bull/bear role) carries
    no ``admissibility`` block and is therefore not a B2 candidate."""
    arbitration = conflict_payload.get("arbitration")
    candidate_evaluations = arbitration.get("candidate_evaluations") if isinstance(arbitration, dict) else None
    if not isinstance(candidate_evaluations, list):
        return []
    return [
        item
        for item in candidate_evaluations
        if isinstance(item, dict)
        and isinstance(item.get("admissibility"), dict)
        and item["admissibility"].get("status") == B2_CANDIDATE
    ]


def extract_conflicts_export(conflict_payload: Any, *, run_id: str, ticker: str) -> dict | None:
    """Direct extraction of the already-computed Conflict result (the
    same in-memory payload ``conflict_results.json``/``run_audit.json``
    already read) -- never a second ``detect_alpha_conflicts`` call.
    Returns ``None`` when no conflict payload is available yet (e.g.
    Week 4 has not run) -- never a fabricated empty conflict result.

    John's B2 Conflict Evidence Admissibility gate (task
    B2_CONFLICT_EVIDENCE_ADMISSIBILITY), section 17: ``candidate_conflicts``
    and the two explicit counts are additive extractions of the exact same
    ``arbitration.candidate_evaluations`` this function already serializes
    below -- never a second computation. ``conflicts``/``main_conflict``
    only ever hold B2-admitted conflicts (unchanged Conflict Detector
    contract), so ``admitted_conflict_count`` is the same value as
    ``len(conflicts)``, exposed under John's requested name."""
    if not isinstance(conflict_payload, dict):
        return None
    conflicts = conflict_payload.get("conflicts")
    return {
        "schema_version": CONFLICTS_EXPORT_SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "source_schema_version": conflict_payload.get("schema_version"),
        "formula_version": conflict_payload.get("formula_version"),
        "activation_formula_version": conflict_payload.get("activation_formula_version"),
        "conflicts": conflicts,
        "main_conflict": conflict_payload.get("main_conflict"),
        "arbitration": conflict_payload.get("arbitration"),
        "candidate_conflicts": _candidate_conflicts(conflict_payload),
        "admitted_conflict_count": len(conflicts) if isinstance(conflicts, list) else 0,
        "candidate_conflict_count": len(_candidate_conflicts(conflict_payload)),
    }


_STANCE_SUMMARY_KEYS = (
    "supports_alpha",
    "opposes_alpha",
    "mentions_alpha",
    "neutral_background",
    "supports_counter_alpha",
)


def _claim_group_ids_index(graph_payload: Any) -> dict[str, set[str]]:
    """claim_id -> the set of evidence_fact_group_ids it is a member of,
    across every v2 Alpha's already-computed evidence_fact_groups. Used
    only to report used_in_activation -- a pure membership lookup, never a
    second grouping pass."""
    index: dict[str, set[str]] = {}
    for alpha in _v2_alphas(graph_payload):
        for fact in alpha.get("evidence_fact_groups") or []:
            if not isinstance(fact, dict):
                continue
            group_id = fact.get("evidence_fact_group_id")
            if not group_id:
                continue
            for claim_id in fact.get("member_claim_ids") or []:
                index.setdefault(str(claim_id), set()).add(str(group_id))
    return index


def _conflict_fact_group_ids(conflict_payload: Any) -> set[str]:
    """Every evidence_fact_group_id that participated in ANY declared
    Conflict pair (bull or bear side), read directly off the already-
    computed conflict payload's own bull_fact_group_ids/bear_fact_group_ids
    -- never a second Conflict evidence-gathering pass."""
    group_ids: set[str] = set()
    if not isinstance(conflict_payload, dict):
        return group_ids
    for conflict in conflict_payload.get("conflicts") or []:
        if not isinstance(conflict, dict):
            continue
        for key in ("bull_fact_group_ids", "bear_fact_group_ids"):
            for group_id in conflict.get(key) or []:
                group_ids.add(str(group_id))
    return group_ids


def build_evidence_stance_audit(
    *,
    run_id: str,
    ticker: str,
    alpha_matches_payload: Any,
    graph_payload: Any = None,
    conflict_payload: Any = None,
) -> dict[str, Any]:
    """Sprint 2 (Alpha-Relative Evidence Stance Classification), Track B1:
    a standalone, additive audit artifact -- one record per (claim,
    candidate Alpha) pair already classified by
    ``comqutor_alpha.structure_engine.evidence_stance`` and attached onto
    each candidate by the Alpha Mapper. Pure extraction: never
    reclassifies, never re-groups Evidence Facts, never re-runs Activation
    or Conflict. ``effect_mode`` is always ``"shadow"`` and
    ``stance_effect_applied`` is always ``False`` -- this Sprint changes no
    scoring or admission behavior (section 13/14)."""
    claim_group_ids = _claim_group_ids_index(graph_payload) if graph_payload else {}
    conflict_group_ids = _conflict_fact_group_ids(conflict_payload)

    records: list[dict[str, Any]] = []
    counts = dict.fromkeys(_STANCE_SUMMARY_KEYS, 0)
    manual_review_count = 0
    unknown_count = 0
    # B1 LLM upgrade: tallied the same way as every other count here --
    # read straight off each candidate's already-computed stance_method/
    # stance_fallback_reason (evidence_stance_llm.apply_llm_stance_upgrade),
    # never recomputed.
    llm_stance_count = 0
    deterministic_fallback_count = 0
    fallback_reason_counts: dict[str, int] = dict.fromkeys(sorted(VALID_FALLBACK_REASONS), 0)

    matches = alpha_matches_payload.get("matches") if isinstance(alpha_matches_payload, dict) else None
    for match in matches or []:
        if not isinstance(match, dict):
            continue
        claim_id = match.get("claim_id")
        group_ids = sorted(claim_group_ids.get(str(claim_id), set()))
        used_in_activation = bool(group_ids)
        used_in_conflict = bool(set(group_ids) & conflict_group_ids)
        for candidate in match.get("candidate_scores") or []:
            if not isinstance(candidate, dict) or "evidence_stance" not in candidate:
                continue
            stance = candidate.get("evidence_stance")
            if stance in counts:
                counts[stance] += 1
            else:
                unknown_count += 1
            if candidate.get("requires_manual_review"):
                manual_review_count += 1
            stance_method = candidate.get("stance_method")
            stance_fallback_reason = candidate.get("stance_fallback_reason")
            if stance_method == STANCE_METHOD_LLM:
                llm_stance_count += 1
            elif stance_method is not None:
                deterministic_fallback_count += 1
                if stance_fallback_reason in fallback_reason_counts:
                    fallback_reason_counts[stance_fallback_reason] += 1
            records.append(
                {
                    "run_id": run_id,
                    "ticker": ticker,
                    "claim_id": claim_id,
                    "source_agent_output_id": match.get("source_agent_output_id"),
                    "agent": match.get("agent"),
                    "target_alpha_id": candidate.get("alpha_id"),
                    "matched_alpha_id": match.get("matched_alpha"),
                    "match_status": match.get("match_status"),
                    "match_score": candidate.get("score"),
                    "relation": candidate.get("relation"),
                    "direction": match.get("direction"),
                    "assertion_status": match.get("assertion_status"),
                    "semantic_polarity": match.get("semantic_polarity"),
                    "claim_quality": match.get("claim_quality"),
                    "ticker_specific": bool(match.get("ticker")) and match.get("ticker") == ticker,
                    "evidence_stance": stance,
                    "counter_alpha_id": candidate.get("counter_alpha_id"),
                    "stance_reason_codes": list(candidate.get("stance_reason_codes") or []),
                    "stance_confidence_band": candidate.get("stance_confidence_band"),
                    "requires_manual_review": bool(candidate.get("requires_manual_review")),
                    "used_in_activation": used_in_activation,
                    "used_in_conflict": used_in_conflict,
                    "evidence_fact_group_ids": group_ids,
                    "claim": match.get("claim"),
                    "evidence": match.get("evidence"),
                    # B1 LLM upgrade: which semantic authority produced this
                    # specific record's stance, and the exact stored
                    # classifier version -- null/None when neither the LLM
                    # nor a fallback was ever attempted for this candidate
                    # (outside the PD-011 retained scope for its claim).
                    "stance_method": stance_method,
                    "stance_fallback_reason": stance_fallback_reason,
                    "evidence_stance_version": candidate.get("evidence_stance_version"),
                }
            )

    return {
        "schema_version": EVIDENCE_STANCE_AUDIT_SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "classifier_version": EVIDENCE_STANCE_VERSION,
        "effect_mode": "shadow",
        "stance_effect_applied": False,
        "summary": {
            "claim_alpha_pair_count": len(records),
            "supports_alpha_count": counts["supports_alpha"],
            "opposes_alpha_count": counts["opposes_alpha"],
            "mentions_alpha_count": counts["mentions_alpha"],
            "neutral_background_count": counts["neutral_background"],
            "supports_counter_alpha_count": counts["supports_counter_alpha"],
            "manual_review_required_count": manual_review_count,
            "unknown_count": unknown_count,
            "llm_stance_count": llm_stance_count,
            "deterministic_fallback_count": deterministic_fallback_count,
            "fallback_reason_counts": fallback_reason_counts,
        },
        "records": records,
    }


def build_summary_export(
    *,
    run_id: str,
    ticker: str,
    dominant_alpha_ids: list[str],
    main_conflict_id: str | None,
    graph_nodes: int,
    graph_edges: int,
    artifact_refs: dict[str, str],
) -> dict:
    """Deterministic, structure-only summary -- assembled purely from
    already-computed fields, never a new LLM call or invented investment
    language."""
    return {
        "schema_version": RESEARCH_SUMMARY_EXPORT_SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "dominant_alpha_ids": sorted(dominant_alpha_ids),
        "main_conflict_id": main_conflict_id,
        "graph_nodes": graph_nodes,
        "graph_edges": graph_edges,
        "artifact_refs": artifact_refs,
    }


def finalize_completed_run_artifacts(
    *,
    run_id: str,
    ticker: str,
    output_root: str | Path,
    graph_payload: dict,
    conflict_payload: Any,
    alpha_matches_payload: Any = None,
) -> dict[str, Any]:
    """Writes ``evidence_facts.json``, ``alpha_activations.json``,
    ``conflicts.json``, and ``summary.json`` from already-computed
    inputs. Never re-executes TradingAgents, an LLM, Activation scoring,
    Conflict detection, or Evidence Fact grouping -- every value here is
    read straight off ``graph_payload``/``conflict_payload``, both of
    which the caller must have already computed.

    Raises ``RunArtifactFinalizationError`` only for a genuine write/
    extraction failure -- never for an artifact-completeness or ticker-
    consistency *result*, which the caller inspects separately (via the
    subsequently-written ``run_audit.json``/``artifact_manifest.json``).
    """
    try:
        evidence_facts = extract_evidence_facts_export(
            graph_payload, run_id=run_id, ticker=ticker, alpha_matches_payload=alpha_matches_payload
        )
        save_json_record(run_id, "evidence_facts.json", evidence_facts, output_root=output_root)

        alpha_activations = extract_alpha_activations_export(graph_payload, run_id=run_id, ticker=ticker)
        save_json_record(run_id, "alpha_activations.json", alpha_activations, output_root=output_root)

        conflicts_export = extract_conflicts_export(conflict_payload, run_id=run_id, ticker=ticker)
        if conflicts_export is not None:
            save_json_record(run_id, "conflicts.json", conflicts_export, output_root=output_root)

        # Sprint 2, Track B1: standalone Evidence Stance audit artifact --
        # additive, only written when a caller has an alpha_matches_payload
        # to extract from (backward compatible: omitting it silently skips
        # this artifact rather than fabricating an empty one).
        evidence_stance_audit = None
        if alpha_matches_payload is not None:
            evidence_stance_audit = build_evidence_stance_audit(
                run_id=run_id,
                ticker=ticker,
                alpha_matches_payload=alpha_matches_payload,
                graph_payload=graph_payload,
                conflict_payload=conflict_payload,
            )
            save_json_record(
                run_id, EVIDENCE_STANCE_AUDIT_FILENAME, evidence_stance_audit, output_root=output_root
            )

        # Sprint 3, Track A3: additive Unclassified Findings Control
        # artifact -- same conditional-write precedent as
        # evidence_stance_audit.json above (only written when a caller
        # has an alpha_matches_payload to join against; omitting it
        # silently skips this artifact rather than fabricating a fake
        # "0 unclassified findings" result for a run this finalizer never
        # actually processed). Reuses the evidence_facts export just
        # computed above -- never a second Evidence Fact grouping pass.
        unclassified_findings = None
        if alpha_matches_payload is not None:
            unclassified_findings = build_unclassified_findings_export(
                run_id=run_id,
                ticker=ticker,
                output_root=output_root,
                alpha_matches_payload=alpha_matches_payload,
                evidence_facts_payload=evidence_facts,
            )
            save_json_record(
                run_id, UNCLASSIFIED_FINDINGS_FILENAME, unclassified_findings, output_root=output_root
            )

        dominant_alphas = graph_payload.get("dominant_alphas")
        dominant_alpha_ids = [
            a.get("alpha_id") for a in dominant_alphas if isinstance(a, dict) and a.get("alpha_id")
        ] if isinstance(dominant_alphas, list) else []
        main_conflict = conflict_payload.get("main_conflict") if isinstance(conflict_payload, dict) else None
        main_conflict_id = main_conflict.get("conflict_id") if isinstance(main_conflict, dict) else None
        graph_metrics = graph_payload.get("graph_metrics")
        graph_metrics = graph_metrics if isinstance(graph_metrics, dict) else {}

        artifact_refs = {
            name: name
            for name in (*REQUIRED_ARTIFACT_FILENAMES, *PRODUCT_EXTENSION_ARTIFACT_FILENAMES, MANIFEST_ARTIFACT_FILENAME)
        }
        summary = build_summary_export(
            run_id=run_id,
            ticker=ticker,
            dominant_alpha_ids=dominant_alpha_ids,
            main_conflict_id=main_conflict_id,
            graph_nodes=int(graph_metrics.get("node_count") or 0),
            graph_edges=int(graph_metrics.get("edge_count") or 0),
            artifact_refs=artifact_refs,
        )
        save_json_record(run_id, "summary.json", summary, output_root=output_root)
    except Exception as exc:
        raise RunArtifactFinalizationError(f"{RunArtifactFinalizationError.reason_code}: {exc}") from exc

    return {
        "evidence_facts": evidence_facts,
        "alpha_activations": alpha_activations,
        "conflicts": conflicts_export,
        "summary": summary,
        "evidence_stance_audit": evidence_stance_audit,
        "unclassified_findings": unclassified_findings,
    }


# ---------------------------------------------------------------------------
# Artifact manifest (persisted artifact_manifest.json)
# ---------------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_entry(run_dir: Path, filename: str, *, run_id: str, ticker: str, required: bool) -> dict[str, Any]:
    path = run_dir / filename
    entry: dict[str, Any] = {
        "artifact_name": filename,
        "path": filename,
        "required": required,
        "run_id": run_id,
        "ticker": ticker,
    }
    if not path.exists():
        entry.update({"exists": False, "size_bytes": None, "sha256": None, "schema_version": None, "status": "missing"})
        return entry
    try:
        raw_bytes = path.read_bytes()
    except OSError:
        entry.update({"exists": True, "size_bytes": None, "sha256": None, "schema_version": None, "status": "unreadable"})
        return entry
    schema_version = None
    try:
        parsed = json.loads(raw_bytes.decode("utf-8"))
        if isinstance(parsed, dict):
            schema_version = parsed.get("schema_version")
        status = "valid"
    except (UnicodeDecodeError, json.JSONDecodeError):
        status = "unreadable" if filename.endswith(".json") else "valid"
    entry.update(
        {
            "exists": True,
            "size_bytes": len(raw_bytes),
            "sha256": _sha256_file(path),
            "schema_version": schema_version,
            "status": status,
        }
    )
    return entry


def build_and_write_artifact_manifest(
    *,
    run_id: str,
    ticker: str,
    output_root: str | Path,
    required_filenames: tuple[str, ...] = REQUIRED_ARTIFACT_FILENAMES,
) -> dict[str, Any]:
    """Builds and persists ``artifact_manifest.json``. Always the last
    artifact written by the finalizer, so it can honestly report on
    every other artifact including ``run_audit.json`` itself.

    ``required_filenames`` defaults to a live run's 9-artifact required
    set (John's contract); pass ``REPLAY_REQUIRED_ARTIFACT_FILENAMES`` for
    an Architecture Replay bundle, which never copies
    ``raw_agent_outputs.json`` by design.
    """
    run_dir = run_dir_for(run_id, output_root)

    entries: list[dict[str, Any]] = []
    missing_required: list[str] = []
    for filename in required_filenames:
        entry = _manifest_entry(run_dir, filename, run_id=run_id, ticker=ticker, required=True)
        entries.append(entry)
        if not entry["exists"] or entry["status"] != "valid":
            missing_required.append(filename)
    for filename in PRODUCT_EXTENSION_ARTIFACT_FILENAMES:
        entries.append(_manifest_entry(run_dir, filename, run_id=run_id, ticker=ticker, required=False))

    compat_entry = _manifest_entry(
        run_dir, CONFLICT_RESULTS_COMPATIBILITY_FILENAME, run_id=run_id, ticker=ticker, required=False
    )
    compat_entry["compatibility_alias_of"] = "conflicts.json"
    entries.append(compat_entry)

    required_count = len(required_filenames)
    present_required_count = required_count - len(missing_required)
    completeness = ARTIFACT_COMPLETENESS_PASS if not missing_required else ARTIFACT_COMPLETENESS_FAIL

    manifest = {
        "schema_version": ARTIFACT_MANIFEST_EXPORT_SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "required_artifact_count": required_count,
        "present_required_artifact_count": present_required_count,
        "missing_required_artifacts": missing_required,
        "artifact_completeness": completeness,
        "artifacts": entries,
    }
    save_json_record(run_id, MANIFEST_ARTIFACT_FILENAME, manifest, output_root=output_root)
    return manifest


__all__ = [
    "EVIDENCE_FACTS_EXPORT_SCHEMA_VERSION",
    "ALPHA_ACTIVATIONS_EXPORT_SCHEMA_VERSION",
    "CONFLICTS_EXPORT_SCHEMA_VERSION",
    "RESEARCH_SUMMARY_EXPORT_SCHEMA_VERSION",
    "ARTIFACT_MANIFEST_EXPORT_SCHEMA_VERSION",
    "EVIDENCE_STANCE_AUDIT_SCHEMA_VERSION",
    "EVIDENCE_STANCE_AUDIT_FILENAME",
    "REQUIRED_ARTIFACT_FILENAMES",
    "REPLAY_REQUIRED_ARTIFACT_FILENAMES",
    "PRODUCT_EXTENSION_ARTIFACT_FILENAMES",
    "MANIFEST_ARTIFACT_FILENAME",
    "CONFLICT_RESULTS_COMPATIBILITY_FILENAME",
    "ARTIFACT_COMPLETENESS_PASS",
    "ARTIFACT_COMPLETENESS_FAIL",
    "RunArtifactFinalizationError",
    "RunArtifactIncompleteError",
    "RunTickerConsistencyError",
    "extract_evidence_facts_export",
    "extract_alpha_activations_export",
    "extract_conflicts_export",
    "build_evidence_stance_audit",
    "build_summary_export",
    "finalize_completed_run_artifacts",
    "build_and_write_artifact_manifest",
]
