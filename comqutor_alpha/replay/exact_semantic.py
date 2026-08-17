"""Provider-zero Exact Semantic Replay over saved validated artifacts."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from comqutor_alpha.api.artifact_export import (
    build_summary_export,
    extract_alpha_activations_export,
    extract_conflicts_export,
    extract_evidence_facts_export,
)
from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts
from comqutor_alpha.graph_engine.pipeline import (
    build_structure_graph_stage,
    score_and_assemble_structure_graph,
)
from comqutor_alpha.replay.modes import ReplayMode
from comqutor_alpha.replay.semantic_binding import (
    BINDING_STATUS_PASS,
    verify_semantic_bindings,
)
from comqutor_alpha.replay.source_bundle import (
    EXACT_REPLAY_OUTPUT_VALIDATION_FAILED,
    EXACT_REPLAY_SOURCE_ARTIFACT_INVALID,
    EXACT_REPLAY_STAGING_WRITE_FAILED,
    SEMANTIC_ARTIFACT_COPY_FILENAMES,
    ExactReplayError,
    ExactSemanticSourceBundle,
    load_exact_semantic_source_bundle,
    sha256_canonical_json,
    verify_source_bundle_unchanged,
)

EXACT_REPLAY_RUN_TYPE = "exact_semantic_replay"
EXACT_REPLAY_METADATA_SCHEMA_VERSION = "comqutor.exact_semantic_replay.metadata.v1"
EXACT_SOURCE_SNAPSHOT_SCHEMA_VERSION = "comqutor.exact_semantic_source_snapshot.v1"
EXACT_REPLAY_COMPARISON_SCHEMA_VERSION = "comqutor.exact_replay_comparison.v1"
EXACT_REPLAY_AUDIT_SCHEMA_VERSION = "comqutor.exact_replay_audit.v1"
EXACT_REPLAY_ARTIFACT_MANIFEST_SCHEMA_VERSION = (
    "comqutor.exact_replay_artifact_manifest.v1"
)

_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_STAGING_PREFIX = ".exact-semantic-replay-staging-"
_SEMANTIC_SOURCE = "saved_validated_artifacts"
_DYNAMIC_COMPARISON_KEYS = frozenset(
    {"created_at", "updated_at", "generated_at", "replay_created_at"}
)
_REQUIRED_OUTPUT_FILENAMES = (
    "metadata.json",
    *SEMANTIC_ARTIFACT_COPY_FILENAMES,
    "structure_graph.json",
    "entity_alpha_exposures.json",
    "alpha_activations.json",
    "evidence_facts.json",
    "conflicts.json",
    "summary.json",
    "exact_semantic_source_snapshot.json",
    "semantic_binding_audit.json",
    "exact_replay_comparison.json",
    "run_audit.json",
    "artifact_manifest.json",
)


@dataclass(frozen=True)
class ExactReplayResult:
    source_run_id: str
    replay_id: str
    replay_mode: str
    run_type: str
    status: str
    output_dir: str | None
    semantic_source: str
    provider_zero: bool
    provider_calls: int
    tradingagents_calls: int
    market_data_calls: int
    database_writes: int
    semantic_artifacts_byte_identical: bool
    source_run_unchanged: bool
    binding_audit: dict[str, Any]
    comparison: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_run_id": self.source_run_id,
            "replay_id": self.replay_id,
            "replay_mode": self.replay_mode,
            "run_type": self.run_type,
            "status": self.status,
            "output_dir": self.output_dir,
            "semantic_source": self.semantic_source,
            "provider_zero": self.provider_zero,
            "provider_calls": self.provider_calls,
            "tradingagents_calls": self.tradingagents_calls,
            "market_data_calls": self.market_data_calls,
            "database_writes": self.database_writes,
            "semantic_artifacts_byte_identical": self.semantic_artifacts_byte_identical,
            "source_run_unchanged": self.source_run_unchanged,
            "binding_audit": self.binding_audit,
            "comparison": self.comparison,
        }


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_exact_replay_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"exact-replay-{stamp}-{uuid4().hex[:8]}"


def _validate_replay_id(value: str) -> str:
    if not isinstance(value, str) or not _RUN_ID_PATTERN.fullmatch(value):
        raise ExactReplayError(EXACT_REPLAY_SOURCE_ARTIFACT_INVALID)
    return value


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _copy_semantic_artifacts(
    bundle: ExactSemanticSourceBundle,
    staging_directory: Path,
) -> dict[str, dict[str, Any]]:
    copies: dict[str, dict[str, Any]] = {}
    for filename in SEMANTIC_ARTIFACT_COPY_FILENAMES:
        source = bundle.artifact_path(filename)
        destination = staging_directory / filename
        shutil.copyfile(source, destination)
        source_hash = _sha256_file(source)
        copy_hash = _sha256_file(destination)
        copies[filename] = {
            "source_path": filename,
            "source_sha256": source_hash,
            "replay_copy_sha256": copy_hash,
            "byte_identical": source.read_bytes() == destination.read_bytes(),
            "semantic_owner_run_id": bundle.source_run_id,
        }
    return copies


def _replay_computation_views(
    bundle: ExactSemanticSourceBundle,
    replay_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return identity-context views without changing persisted copies."""

    structured = copy.deepcopy(bundle.structured_agent_outputs)
    structured["run_id"] = replay_id
    for record in structured.get("records") or []:
        if isinstance(record, dict) and "run_id" in record:
            record["run_id"] = replay_id
    for relation in structured.get("canonical_relations") or []:
        if isinstance(relation, dict) and "run_id" in relation:
            relation["run_id"] = replay_id

    alpha_matches = copy.deepcopy(bundle.alpha_matches)
    alpha_matches["run_id"] = replay_id
    for record in alpha_matches.get("matches") or []:
        if isinstance(record, dict) and "run_id" in record:
            record["run_id"] = replay_id

    extracted = copy.deepcopy(bundle.extracted_structures)
    extracted["run_id"] = replay_id
    return structured, alpha_matches, extracted


def _run_deterministic_downstream(
    bundle: ExactSemanticSourceBundle,
    replay_id: str,
) -> dict[str, dict[str, Any]]:
    structured, alpha_matches, extracted = _replay_computation_views(bundle, replay_id)
    graph_stage = build_structure_graph_stage(alpha_matches, extracted)
    run_timestamp = bundle.metadata.get("analysis_date") or bundle.metadata.get("created_at")
    graph = score_and_assemble_structure_graph(
        graph_stage,
        alpha_matches,
        extracted,
        run_timestamp=run_timestamp,
        structured_records=structured.get("records") or [],
        exposure_run_id=replay_id,
    )
    conflicts = detect_alpha_conflicts(
        run_id=replay_id,
        ticker=bundle.ticker,
        activation_payload=graph.get("activation") or {},
        alpha_matches=alpha_matches.get("matches") or [],
    )
    conflicts_export = extract_conflicts_export(
        conflicts,
        run_id=replay_id,
        ticker=bundle.ticker,
    )
    if conflicts_export is None:
        raise ExactReplayError(EXACT_REPLAY_OUTPUT_VALIDATION_FAILED)
    exposure = graph.get("entity_alpha_exposures")
    if not isinstance(exposure, dict):
        raise ExactReplayError(EXACT_REPLAY_OUTPUT_VALIDATION_FAILED)
    activations = extract_alpha_activations_export(
        graph,
        run_id=replay_id,
        ticker=bundle.ticker,
    )
    evidence_facts = extract_evidence_facts_export(
        graph,
        run_id=replay_id,
        ticker=bundle.ticker,
        alpha_matches_payload=alpha_matches,
    )
    graph_metrics = graph.get("graph_metrics")
    graph_metrics = graph_metrics if isinstance(graph_metrics, dict) else {}
    dominant = graph.get("dominant_alphas")
    dominant_ids = [
        str(item.get("alpha_id"))
        for item in dominant or []
        if isinstance(item, dict) and item.get("alpha_id")
    ]
    main_conflict = conflicts.get("main_conflict")
    summary = build_summary_export(
        run_id=replay_id,
        ticker=bundle.ticker,
        dominant_alpha_ids=dominant_ids,
        main_conflict_id=(
            str(main_conflict.get("conflict_id"))
            if isinstance(main_conflict, dict) and main_conflict.get("conflict_id")
            else None
        ),
        graph_nodes=int(graph_metrics.get("node_count") or 0),
        graph_edges=int(graph_metrics.get("edge_count") or 0),
        artifact_refs={name: name for name in _REQUIRED_OUTPUT_FILENAMES},
    )
    return {
        "structure_graph.json": graph,
        "entity_alpha_exposures.json": exposure,
        "alpha_activations.json": activations,
        "evidence_facts.json": evidence_facts,
        "conflicts.json": conflicts_export,
        "summary.json": summary,
    }


def _fact_group_identity_map(value: Any) -> dict[str, str]:
    result: dict[str, str] = {}

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            group_id = item.get("evidence_fact_group_id")
            members = item.get("member_claim_ids")
            if group_id and isinstance(members, list):
                stable = sha256_canonical_json(
                    {
                        "member_claim_ids": sorted(str(member) for member in members),
                        "representative_claim_id": item.get("representative_claim_id"),
                    }
                )
                result[str(group_id)] = f"fact-group:{stable}"
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return result


def _normalize_for_comparison(
    value: Any,
    *,
    source_run_id: str,
    replay_id: str,
) -> Any:
    fact_groups = _fact_group_identity_map(value)

    def normalize(item: Any) -> Any:
        if isinstance(item, dict):
            return {
                key: normalize(child)
                for key, child in item.items()
                if key not in _DYNAMIC_COMPARISON_KEYS
            }
        if isinstance(item, list):
            return [normalize(child) for child in item]
        if isinstance(item, str):
            if item in {source_run_id, replay_id}:
                return "__EXECUTION_RUN_ID__"
            return fact_groups.get(item, item)
        return item

    return normalize(value)


def _comparison_entry(
    source: Any,
    replay: Any,
    *,
    source_run_id: str,
    replay_id: str,
) -> dict[str, Any]:
    normalized_source = _normalize_for_comparison(
        source,
        source_run_id=source_run_id,
        replay_id=replay_id,
    )
    normalized_replay = _normalize_for_comparison(
        replay,
        source_run_id=source_run_id,
        replay_id=replay_id,
    )
    source_hash = sha256_canonical_json(normalized_source)
    replay_hash = sha256_canonical_json(normalized_replay)
    return {
        "source_normalized_sha256": source_hash,
        "replay_normalized_sha256": replay_hash,
        "semantically_equivalent": source_hash == replay_hash,
    }


def _build_comparison(
    bundle: ExactSemanticSourceBundle,
    replay_id: str,
    downstream: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    graph = downstream["structure_graph.json"]
    comparisons = {
        "graph": _comparison_entry(
            bundle.structure_graph,
            graph,
            source_run_id=bundle.source_run_id,
            replay_id=replay_id,
        ),
        "activation": _comparison_entry(
            bundle.structure_graph.get("activation"),
            graph.get("activation"),
            source_run_id=bundle.source_run_id,
            replay_id=replay_id,
        ),
        "exposure": _comparison_entry(
            bundle.entity_alpha_exposures,
            downstream["entity_alpha_exposures.json"],
            source_run_id=bundle.source_run_id,
            replay_id=replay_id,
        ),
        "conflict": _comparison_entry(
            bundle.conflicts,
            downstream["conflicts.json"],
            source_run_id=bundle.source_run_id,
            replay_id=replay_id,
        ),
    }
    equivalent = all(item["semantically_equivalent"] for item in comparisons.values())
    return {
        "schema_version": EXACT_REPLAY_COMPARISON_SCHEMA_VERSION,
        "source_run_id": bundle.source_run_id,
        "replay_id": replay_id,
        "replay_mode": ReplayMode.EXACT_SEMANTIC_REPLAY.value,
        "semantic_inputs_reused_exactly": True,
        "identity_normalization": {
            "source_semantic_owner": bundle.source_run_id,
            "downstream_execution_owner": replay_id,
            "run_identity_mapped_to_explicit_placeholder": True,
            "derived_evidence_fact_group_ids_mapped_by_exact_member_claim_ids": True,
        },
        "comparisons": comparisons,
        "deterministic_downstream_equivalent": equivalent,
        "deterministic_engine_delta": not equivalent,
        "final_status": "PASS" if equivalent else "DETERMINISTIC_ENGINE_DELTA",
    }


def _build_source_snapshot(
    bundle: ExactSemanticSourceBundle,
    replay_id: str,
    copies: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": EXACT_SOURCE_SNAPSHOT_SCHEMA_VERSION,
        "source_run_id": bundle.source_run_id,
        "replay_id": replay_id,
        "replay_mode": ReplayMode.EXACT_SEMANTIC_REPLAY.value,
        "semantic_manifest_sha256": _sha256_file(
            bundle.artifact_path("llm_semantic_manifest.json")
        ),
        "semantic_calls_sha256": _sha256_file(
            bundle.artifact_path("llm_semantic_calls.jsonl")
        ),
        "structured_agent_outputs_sha256": _sha256_file(
            bundle.artifact_path("structured_agent_outputs.json")
        ),
        "alpha_matches_sha256": _sha256_file(bundle.artifact_path("alpha_matches.json")),
        "extracted_structures_sha256": _sha256_file(
            bundle.artifact_path("extracted_structures.json")
        ),
        "semantic_artifact_copies": copies,
        "semantic_artifact_copies_byte_identical": all(
            item["byte_identical"] for item in copies.values()
        ),
        "source_file_count": len(bundle.source_files),
        "source_files": [item.to_dict() for item in bundle.source_files],
        "provider_calls": 0,
        "tradingagents_calls": 0,
        "market_data_calls": 0,
        "database_writes": 0,
    }


def _build_metadata(
    bundle: ExactSemanticSourceBundle,
    replay_id: str,
) -> dict[str, Any]:
    return {
        "schema_version": EXACT_REPLAY_METADATA_SCHEMA_VERSION,
        "run_id": replay_id,
        "replay_id": replay_id,
        "source_run_id": bundle.source_run_id,
        "ticker": bundle.ticker,
        "run_type": EXACT_REPLAY_RUN_TYPE,
        "replay_mode": ReplayMode.EXACT_SEMANTIC_REPLAY.value,
        "semantic_source": _SEMANTIC_SOURCE,
        "semantic_artifact_owner_run_id": bundle.source_run_id,
        "downstream_output_owner_run_id": replay_id,
        "provider_zero": True,
        "provider_calls": 0,
        "tradingagents_calls": 0,
        "market_data_calls": 0,
        "database_writes": 0,
        "replay_created_at": _utc_now_iso(),
    }


def _build_run_audit(
    bundle: ExactSemanticSourceBundle,
    replay_id: str,
    binding_audit: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": EXACT_REPLAY_AUDIT_SCHEMA_VERSION,
        "run_id": replay_id,
        "replay_id": replay_id,
        "source_run_id": bundle.source_run_id,
        "ticker": bundle.ticker,
        "replay_mode": ReplayMode.EXACT_SEMANTIC_REPLAY.value,
        "semantic_source": _SEMANTIC_SOURCE,
        "binding_status": binding_audit["final_status"],
        "deterministic_comparison_status": comparison["final_status"],
        "source_run_unchanged": True,
        "artifact_completeness": "pass",
        "provider_zero": True,
        "provider_calls": 0,
        "tradingagents_calls": 0,
        "market_data_calls": 0,
        "database_writes": 0,
    }


def _build_artifact_manifest(
    staging_directory: Path,
    *,
    bundle: ExactSemanticSourceBundle,
    replay_id: str,
) -> dict[str, Any]:
    artifacts = []
    missing = []
    for filename in _REQUIRED_OUTPUT_FILENAMES:
        if filename == "artifact_manifest.json":
            continue
        path = staging_directory / filename
        exists = path.is_file()
        if not exists:
            missing.append(filename)
        artifacts.append(
            {
                "artifact_name": filename,
                "exists": exists,
                "size_bytes": path.stat().st_size if exists else None,
                "sha256": _sha256_file(path) if exists else None,
                "semantic_owner_run_id": (
                    bundle.source_run_id
                    if filename in SEMANTIC_ARTIFACT_COPY_FILENAMES
                    else replay_id
                ),
            }
        )
    return {
        "schema_version": EXACT_REPLAY_ARTIFACT_MANIFEST_SCHEMA_VERSION,
        "run_id": replay_id,
        "replay_id": replay_id,
        "source_run_id": bundle.source_run_id,
        "ticker": bundle.ticker,
        "replay_mode": ReplayMode.EXACT_SEMANTIC_REPLAY.value,
        "required_artifact_count": len(_REQUIRED_OUTPUT_FILENAMES),
        "present_required_artifact_count": len(_REQUIRED_OUTPUT_FILENAMES) - len(missing),
        "missing_required_artifacts": missing,
        "artifact_completeness": "pass" if not missing else "fail",
        "artifacts": artifacts,
    }


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExactReplayError(EXACT_REPLAY_OUTPUT_VALIDATION_FAILED) from exc
    if not isinstance(value, dict):
        raise ExactReplayError(EXACT_REPLAY_OUTPUT_VALIDATION_FAILED)
    return value


def _validate_staged_output(
    staging_directory: Path,
    *,
    bundle: ExactSemanticSourceBundle,
    replay_id: str,
) -> None:
    missing = [
        filename
        for filename in _REQUIRED_OUTPUT_FILENAMES
        if not (staging_directory / filename).is_file()
    ]
    if missing:
        raise ExactReplayError(
            EXACT_REPLAY_OUTPUT_VALIDATION_FAILED,
            details={"missing_artifacts": missing},
        )
    metadata = _load_json_object(staging_directory / "metadata.json")
    binding = _load_json_object(staging_directory / "semantic_binding_audit.json")
    manifest = _load_json_object(staging_directory / "artifact_manifest.json")
    graph = _load_json_object(staging_directory / "structure_graph.json")
    exposure = _load_json_object(staging_directory / "entity_alpha_exposures.json")
    conflicts = _load_json_object(staging_directory / "conflicts.json")
    if (
        metadata.get("replay_mode") != ReplayMode.EXACT_SEMANTIC_REPLAY.value
        or metadata.get("semantic_source") != _SEMANTIC_SOURCE
        or metadata.get("provider_zero") is not True
        or any(
            metadata.get(field) != 0
            for field in (
                "provider_calls",
                "tradingagents_calls",
                "market_data_calls",
                "database_writes",
            )
        )
        or binding.get("final_status") != BINDING_STATUS_PASS
        or manifest.get("artifact_completeness") != "pass"
        or graph.get("run_id") != replay_id
        or exposure.get("run_id") != replay_id
        or conflicts.get("run_id") != replay_id
    ):
        raise ExactReplayError(EXACT_REPLAY_OUTPUT_VALIDATION_FAILED)
    manifest_entries = manifest.get("artifacts")
    if not isinstance(manifest_entries, list):
        raise ExactReplayError(EXACT_REPLAY_OUTPUT_VALIDATION_FAILED)
    manifest_by_name = {
        str(item.get("artifact_name")): item
        for item in manifest_entries
        if isinstance(item, dict) and item.get("artifact_name")
    }
    expected_manifest_names = set(_REQUIRED_OUTPUT_FILENAMES) - {
        "artifact_manifest.json"
    }
    if (
        set(manifest_by_name) != expected_manifest_names
        or manifest.get("required_artifact_count") != len(_REQUIRED_OUTPUT_FILENAMES)
        or manifest.get("present_required_artifact_count")
        != len(_REQUIRED_OUTPUT_FILENAMES)
        or manifest.get("missing_required_artifacts") != []
    ):
        raise ExactReplayError(EXACT_REPLAY_OUTPUT_VALIDATION_FAILED)
    for filename, entry in manifest_by_name.items():
        path = staging_directory / filename
        if (
            entry.get("exists") is not True
            or entry.get("size_bytes") != path.stat().st_size
            or entry.get("sha256") != _sha256_file(path)
        ):
            raise ExactReplayError(EXACT_REPLAY_OUTPUT_VALIDATION_FAILED)
    for filename in SEMANTIC_ARTIFACT_COPY_FILENAMES:
        source = bundle.artifact_path(filename)
        copy_path = staging_directory / filename
        if source.read_bytes() != copy_path.read_bytes():
            raise ExactReplayError(
                EXACT_REPLAY_OUTPUT_VALIDATION_FAILED,
                artifact=filename,
            )


def _atomic_promote(staging_directory: Path, final_directory: Path) -> None:
    staging_directory.replace(final_directory)


def _safe_cleanup_staging(staging_directory: Path, output_root: Path) -> None:
    try:
        safe = (
            staging_directory.parent == output_root
            and staging_directory.name.startswith(_STAGING_PREFIX)
        )
        if safe and staging_directory.exists():
            shutil.rmtree(staging_directory)
    except OSError:
        # A hidden, uniquely named staging directory is isolated and never a
        # successful replay bundle.  Cleanup failure cannot promote it.
        return


def run_exact_semantic_replay(
    source_run_dir: str | Path,
    replay_output_root: str | Path,
    *,
    replay_id: str | None = None,
    persist: bool = True,
) -> ExactReplayResult:
    """Reuse saved semantic authority and recompute deterministic stages only."""

    bundle = load_exact_semantic_source_bundle(source_run_dir)
    binding_audit = verify_semantic_bindings(bundle)
    resolved_replay_id = _validate_replay_id(replay_id or new_exact_replay_id())
    try:
        downstream = _run_deterministic_downstream(bundle, resolved_replay_id)
        comparison = _build_comparison(bundle, resolved_replay_id, downstream)
    except ExactReplayError:
        raise
    except Exception as exc:
        raise ExactReplayError(EXACT_REPLAY_OUTPUT_VALIDATION_FAILED) from exc
    verify_source_bundle_unchanged(bundle)

    output_root = Path(replay_output_root).expanduser()
    if ".." in output_root.parts or output_root.is_symlink():
        raise ExactReplayError(EXACT_REPLAY_SOURCE_ARTIFACT_INVALID)
    output_root.mkdir(parents=True, exist_ok=True)
    output_root = output_root.resolve()
    try:
        output_root.relative_to(bundle.source_directory)
    except ValueError:
        pass
    else:
        raise ExactReplayError(EXACT_REPLAY_SOURCE_ARTIFACT_INVALID)
    final_directory = output_root / resolved_replay_id
    if final_directory.exists():
        raise FileExistsError(f"Exact replay output already exists: {resolved_replay_id}")
    staging_directory = output_root / f"{_STAGING_PREFIX}{resolved_replay_id}-{uuid4().hex}"
    staging_directory.mkdir()

    try:
        try:
            copies = _copy_semantic_artifacts(bundle, staging_directory)
            metadata = _build_metadata(bundle, resolved_replay_id)
            source_snapshot = _build_source_snapshot(bundle, resolved_replay_id, copies)
            run_audit = _build_run_audit(
                bundle,
                resolved_replay_id,
                binding_audit,
                comparison,
            )
            _write_json(staging_directory / "metadata.json", metadata)
            for filename, payload in downstream.items():
                _write_json(staging_directory / filename, payload)
            _write_json(
                staging_directory / "exact_semantic_source_snapshot.json",
                source_snapshot,
            )
            _write_json(staging_directory / "semantic_binding_audit.json", binding_audit)
            _write_json(staging_directory / "exact_replay_comparison.json", comparison)
            _write_json(staging_directory / "run_audit.json", run_audit)
            artifact_manifest = _build_artifact_manifest(
                staging_directory,
                bundle=bundle,
                replay_id=resolved_replay_id,
            )
            _write_json(staging_directory / "artifact_manifest.json", artifact_manifest)
        except ExactReplayError:
            raise
        except Exception as exc:
            raise ExactReplayError(EXACT_REPLAY_STAGING_WRITE_FAILED) from exc

        try:
            _validate_staged_output(
                staging_directory,
                bundle=bundle,
                replay_id=resolved_replay_id,
            )
            verify_source_bundle_unchanged(bundle)
            if persist:
                _atomic_promote(staging_directory, final_directory)
                output_dir = str(final_directory)
            else:
                output_dir = None
        except ExactReplayError:
            raise
        except Exception as exc:
            raise ExactReplayError(EXACT_REPLAY_STAGING_WRITE_FAILED) from exc
    except ExactReplayError:
        raise
    finally:
        _safe_cleanup_staging(staging_directory, output_root)

    return ExactReplayResult(
        source_run_id=bundle.source_run_id,
        replay_id=resolved_replay_id,
        replay_mode=ReplayMode.EXACT_SEMANTIC_REPLAY.value,
        run_type=EXACT_REPLAY_RUN_TYPE,
        status="completed",
        output_dir=output_dir,
        semantic_source=_SEMANTIC_SOURCE,
        provider_zero=True,
        provider_calls=0,
        tradingagents_calls=0,
        market_data_calls=0,
        database_writes=0,
        semantic_artifacts_byte_identical=True,
        source_run_unchanged=True,
        binding_audit=binding_audit,
        comparison=comparison,
    )


__all__ = [
    "EXACT_REPLAY_RUN_TYPE",
    "ExactReplayResult",
    "new_exact_replay_id",
    "run_exact_semantic_replay",
]
