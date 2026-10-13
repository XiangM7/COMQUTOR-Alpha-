"""Operator entry for ``alpha_evidence_consumption.v2`` on SAVED runs (T1 integration, 2026-10-11).

A recomputation of a saved run's inputs -- never a Fresh Run: no model, search or data-fetch call is made here. The operator picks the
contract explicitly (``"v2"`` or ``"legacy"``; there is no default); nothing asks anyone to edit a run's internal metadata by hand.

* :func:`copy_saved_run` -- copies one saved run directory, byte for byte, into a separate verification output root (the original is only
  read; every copied file is re-hashed against the original).
* :func:`derive_consumption_execution` -- creates a derived execution ``consumption-<UTC>-<hex8>`` of that saved run through the existing
  production entry ``classification_recovery.finalize_classification_recovery_execution`` (rebased copies, lineage record, research-run
  row, the production Week 3 pipeline). For ``"v2"`` the execution's metadata names the contract; when the source run has its own
  model-stance ledger, the metadata also declares the ledger binding (source run + sha256 of that ledger) so the stances are corroborated
  against the run that produced them -- the ledger itself is NOT copied (it describes the source run's own calls).
* :func:`rollback_consumption_execution` -- removes the contract from such an execution, re-runs the production Week 3 pipeline (which
  strips every consumption block) and writes ``consumption_rollback.json``.

Identities are kept apart everywhere: ``based_on_run_id`` (the saved run = source identity), the execution id (execution identity) and
the stance-ledger binding (whose ledger corroborated the stances).
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from secrets import token_hex
from typing import Any

from comqutor_alpha.graph_engine.evidence_consumption import (
    CONSUMPTION_BLOCK_KEY,
    CONSUMPTION_CONTRACT_V2,
    CONSUMPTION_METADATA_KEY,
    CONSUMPTION_RECOMPUTE_EXECUTION_TYPE,
    LEDGER_BINDING_METADATA_KEY,
    LEDGER_FILENAME,
    LEDGER_MANIFEST_FILENAME,
    PAYLOAD_CONTRACT_KEY,
    strip_alpha_evidence_consumption,
)
from comqutor_alpha.storage.file_store import (
    load_json_record,
    load_json_record_if_exists,
    run_dir_for,
    save_json_record,
    validate_run_id_for_path,
)

CONSUMPTION_EXECUTION_TYPE = CONSUMPTION_RECOMPUTE_EXECUTION_TYPE
CONSUMPTION_EXECUTION_MODE = "consumption"  # research_runs.execution_mode (<= 16 chars)
CONSUMPTION_LINEAGE_FILENAME = "consumption_lineage.json"
CONSUMPTION_ROLLBACK_FILENAME = "consumption_rollback.json"
CONSUMPTION_ROLLBACK_SCHEMA_VERSION = "comqutor.consumption_rollback.v1"
VERIFICATION_COPIES_FILENAME = "verification_copies.json"
CONTRACT_CHOICES: dict[str, str | None] = {"v2": CONSUMPTION_CONTRACT_V2, "legacy": None}
RECOMPUTE_LABEL = "recomputation of saved inputs -- not a Fresh Run (no model, search or data-fetch call)"


def _utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fail(error_code: str, **extra: Any) -> dict[str, Any]:
    return {"status": "failed", "error_code": error_code, **extra}


def new_consumption_execution_id() -> str:
    return f"consumption-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{token_hex(4)}"


def _real_outputs_dir() -> Path:
    return (Path(__file__).resolve().parents[1] / "outputs").resolve()


def refuse_real_outputs(output_root: Any) -> None:
    """The verification copy and every execution made here live OUTSIDE the repository's ``outputs/`` tree, so historical runs stay untouched."""
    root = Path(output_root).expanduser().resolve()
    real = _real_outputs_dir()
    if root == real or real in root.parents:
        raise ValueError(f"REFUSED_REAL_OUTPUTS: {root} is inside the repository outputs tree {real}; use a separate verification root")


# ------------------------------------------------------------------------------------------------- verification copy
def copy_saved_run(source_run_dir: Any, output_root: Any) -> dict[str, Any]:
    """Byte copy of one saved run directory into ``output_root`` (same run id = same source identity). Refuses an existing target; never
    follows symlinks; records the copy in ``<output_root>/verification_copies.json``."""
    refuse_real_outputs(output_root)
    source = Path(source_run_dir).expanduser().resolve()
    if not source.is_dir():
        return _fail("SOURCE_RUN_DIR_NOT_FOUND", source_run_dir=str(source))
    run_id = validate_run_id_for_path(source.name)
    root = Path(output_root).expanduser().resolve()
    target = root / run_id
    if target.exists():
        return _fail("VERIFICATION_COPY_EXISTS", target=str(target))
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, symlinks=True)
    files = sorted(p for p in source.rglob("*") if p.is_file() and not p.is_symlink())
    mismatched = [str(p.relative_to(source)) for p in files if _sha256(p) != _sha256(target / p.relative_to(source))]
    entry = {"run_id": run_id, "copied_from": str(source), "copied_at": _utc(), "files": len(files), "mismatched": mismatched,
             "original_sha256": {str(p.relative_to(source)): _sha256(p) for p in files}}
    index_path = root / VERIFICATION_COPIES_FILENAME
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else {"copies": []}
    index["copies"].append(entry)
    index_path.write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    if mismatched:
        return _fail("VERIFICATION_COPY_MISMATCH", mismatched=mismatched)
    return {"status": "ok", "run_id": run_id, "verification_copy": str(target), "files": len(files)}


# ------------------------------------------------------------------------------------------------- derive
def source_ledger_binding(source_dir: Path, source_run_id: str) -> dict[str, Any] | None:
    """The binding a derived execution declares: the source run's OWN ledger, pinned by its sha256 (``None`` if it has no ledger)."""
    ledger = source_dir / LEDGER_FILENAME
    if not ledger.is_file():
        return None
    sha = _sha256(ledger)
    manifest = source_dir / LEDGER_MANIFEST_FILENAME
    expected = None
    if manifest.is_file():
        try:
            expected = json.loads(manifest.read_text(encoding="utf-8")).get("calls_file_sha256")
        except ValueError:
            expected = None
    return {"source_run_id": source_run_id, "calls_file_sha256": sha, "manifest_calls_file_sha256": expected,
            "manifest_matches": (expected == sha) if expected else None}


def derive_consumption_execution(
    source_run_id: str,
    *,
    contract: str | None,
    output_root: Any,
    graph_repository: Any = None,
    execution_id: str | None = None,
    run_pipeline: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    if contract not in CONTRACT_CHOICES:
        return _fail("CONSUMPTION_CONTRACT_NOT_CHOSEN", allowed=sorted(CONTRACT_CHOICES), given=contract)
    refuse_real_outputs(output_root)
    from comqutor_alpha.classification_recovery import (
        finalize_classification_recovery_execution,  # noqa: PLC0415
    )

    try:
        safe_source = validate_run_id_for_path(source_run_id)
    except ValueError:
        return _fail("INVALID_RUN_ID", source_run_id=str(source_run_id))
    source_dir = run_dir_for(safe_source, output_root)
    if not (source_dir / "alpha_matches.json").is_file():
        return _fail("SOURCE_RUN_NOT_FOUND", source_run_id=safe_source)
    source_metadata = load_json_record(safe_source, "metadata.json", output_root=output_root)
    if source_metadata.get(CONSUMPTION_METADATA_KEY) is not None:
        return _fail("SOURCE_ALREADY_DECLARES_A_CONTRACT", source_run_id=safe_source)
    assembled = copy.deepcopy(load_json_record(safe_source, "alpha_matches.json", output_root=output_root))
    strip_alpha_evidence_consumption(assembled)  # a saved legacy run carries none; the derived input is always the legacy payload
    binding = source_ledger_binding(source_dir, safe_source)
    execution_id = execution_id or new_consumption_execution_id()
    chosen = CONTRACT_CHOICES[contract]
    metadata_extras: dict[str, Any] = {"saved_input_recompute": {"label": RECOMPUTE_LABEL, "model_calls": 0, "searches": 0, "data_fetches": 0}}
    if chosen is not None:
        metadata_extras[CONSUMPTION_METADATA_KEY] = chosen
        if binding is not None:
            metadata_extras[LEDGER_BINDING_METADATA_KEY] = {"source_run_id": binding["source_run_id"], "calls_file_sha256": binding["calls_file_sha256"]}
    result = finalize_classification_recovery_execution(
        safe_source,
        execution_id,
        assembled_alpha_matches=assembled,
        recovery_provenance={"checkpoint_origin": "saved_run_recompute",
                             "note": "alpha_matches / structured records / source registry reused verbatim from the saved run; only the run-level contract choice is added"},
        output_root=output_root,
        graph_repository=graph_repository,
        run_pipeline=run_pipeline,
        execution_type=CONSUMPTION_EXECUTION_TYPE,
        execution_mode=CONSUMPTION_EXECUTION_MODE,
        lineage_filename=CONSUMPTION_LINEAGE_FILENAME,
        assembled_transformation="reused_verbatim_from_source",
        root_run_id=source_metadata.get("root_research_run_id") or None,
        metadata_extras=metadata_extras,
        lineage_extras={
            "purpose": "recompute a saved run's inputs under an explicitly chosen evidence contract (operator choice)",
            "contract_choice": contract,
            "alpha_evidence_consumption": chosen,
            "stance_ledger_binding": binding if chosen is not None else None,
            "stance_ledger_note": ("the source run's own ledger is NOT copied (it describes that run's own model calls); the execution "
                                   "declares a binding to it, verified on every read" if binding else
                                   "the source run has no model-stance ledger: no stance can be corroborated, so the stance policy excludes nothing"),
            "fresh_run": False, "model_calls": 0, "searches": 0, "data_fetches": 0,
        },
    )
    return {**result, "contract_choice": contract, "alpha_evidence_consumption": chosen, "source_run_id": safe_source,
            "execution_id": execution_id, "stance_ledger_binding": binding if chosen is not None else None}


# ------------------------------------------------------------------------------------------------- rollback
def _remaining_blocks(alpha_matches: Mapping[str, Any]) -> int:
    count = 0
    for match in alpha_matches.get("matches") or []:
        if isinstance(match, Mapping):
            count += CONSUMPTION_BLOCK_KEY in match
            for pool in ("candidate_scores", "eligible_candidates", "top_candidates"):
                count += sum(1 for c in match.get(pool) or () if isinstance(c, Mapping) and CONSUMPTION_BLOCK_KEY in c)
    return count


def rollback_consumption_execution(
    execution_id: str,
    *,
    output_root: Any,
    graph_repository: Any = None,
    run_pipeline: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    refuse_real_outputs(output_root)
    try:
        safe = validate_run_id_for_path(execution_id)
    except ValueError:
        return _fail("INVALID_RUN_ID", execution_id=str(execution_id))
    run_dir = run_dir_for(safe, output_root)
    metadata = load_json_record_if_exists(safe, "metadata.json", output_root=output_root)
    if not isinstance(metadata, dict) or metadata.get("execution_type") != CONSUMPTION_EXECUTION_TYPE:
        return _fail("NOT_A_CONSUMPTION_EXECUTION", execution_id=safe)
    previous = metadata.get(CONSUMPTION_METADATA_KEY)
    if previous is None:
        return _fail("NOTHING_TO_ROLL_BACK", execution_id=safe)
    watched = ("alpha_matches.json", "structure_graph.json", "metadata.json")
    before = {name: _sha256(run_dir / name) for name in watched if (run_dir / name).is_file()}
    save_json_record(safe, "metadata.json", {k: v for k, v in metadata.items() if k != CONSUMPTION_METADATA_KEY}, output_root=output_root)
    repository = graph_repository
    if repository is None:
        from comqutor_alpha.storage.db.repository import (
            build_write_repository_from_env,  # noqa: PLC0415
        )

        repository = build_write_repository_from_env(str(output_root))
    if run_pipeline is None:
        from comqutor_alpha.api import routes_research as rr  # noqa: PLC0415

        run_pipeline = rr._run_week3_graph_pipeline
    run_pipeline(run_dir, graph_repository=repository, require_verified_evidence_gate=True)
    status = load_json_record_if_exists(safe, "week3_pipeline_status.json", output_root=output_root) or {}
    alpha_matches = load_json_record(safe, "alpha_matches.json", output_root=output_root)
    graph = load_json_record_if_exists(safe, "structure_graph.json", output_root=output_root) or {}
    checks = {"consumption_blocks_remaining": _remaining_blocks(alpha_matches), "payload_contract_marker_present": PAYLOAD_CONTRACT_KEY in alpha_matches,
              "structure_graph_has_evidence_consumption": "evidence_consumption" in graph, "pipeline_outcome": status.get("outcome")}
    ok = (checks["consumption_blocks_remaining"] == 0 and not checks["payload_contract_marker_present"]
          and not checks["structure_graph_has_evidence_consumption"] and checks["pipeline_outcome"] == "success")
    record = {
        "schema_version": CONSUMPTION_ROLLBACK_SCHEMA_VERSION, "execution_id": safe, "rolled_back_at": _utc(),
        "removed_metadata_key": CONSUMPTION_METADATA_KEY, "previous_contract": previous,
        "kept_metadata": {k: metadata.get(k) for k in (LEDGER_BINDING_METADATA_KEY, "based_on_run_id", "root_research_run_id") if metadata.get(k)},
        "sha256_before": before, "sha256_after": {name: _sha256(run_dir / name) for name in watched if (run_dir / name).is_file()},
        "checks": checks, "rolled_back": ok,
    }
    save_json_record(safe, CONSUMPTION_ROLLBACK_FILENAME, record, output_root=output_root)
    # the pipeline above rebuilt the artifact manifest before this record existed; rebuild it once more (as the pipeline's own last step
    # does) so the Export carries the rollback record next to the lineage file that still names the contract originally chosen
    from comqutor_alpha.api.artifact_export import (
        build_and_write_artifact_manifest,  # noqa: PLC0415
    )

    build_and_write_artifact_manifest(run_id=safe, ticker=str(metadata.get("ticker") or ""), output_root=output_root)
    return {"status": "ok" if ok else "failed", **({} if ok else {"error_code": "ROLLBACK_INCOMPLETE"}), "execution_id": safe, "checks": checks}


def require_isolated_test_database() -> str:
    """The database the operator entry writes to must be an isolated ``*_test`` database, named explicitly (never a shared one by default)."""
    from sqlalchemy.engine import make_url  # noqa: PLC0415

    url = os.environ.get("COMQUTOR_DATABASE_URL")
    if not url:
        raise ValueError("REFUSED_NO_DATABASE: set COMQUTOR_DATABASE_URL to an isolated *_test database")
    name = make_url(url).database or ""
    if not name.endswith("_test") or os.environ.get("COMQUTOR_REQUIRE_DATABASE_NAME") != name:
        raise ValueError("REFUSED_DATABASE: the database name must end in _test and equal COMQUTOR_REQUIRE_DATABASE_NAME")
    return name


__all__ = [
    "CONSUMPTION_EXECUTION_MODE",
    "CONSUMPTION_EXECUTION_TYPE",
    "CONSUMPTION_LINEAGE_FILENAME",
    "CONSUMPTION_ROLLBACK_FILENAME",
    "CONTRACT_CHOICES",
    "copy_saved_run",
    "derive_consumption_execution",
    "new_consumption_execution_id",
    "refuse_real_outputs",
    "require_isolated_test_database",
    "rollback_consumption_execution",
    "source_ledger_binding",
]
