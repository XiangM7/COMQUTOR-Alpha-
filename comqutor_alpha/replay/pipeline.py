"""Core Historical Architecture Replay service (Track D).

``run_structure_replay`` is the single, real (non-scratch-script) service
both the CLI (``cli.py``) and the historical-learning audit (Track C) call.
It reprocesses one completed run's ``raw_agent_outputs.json`` -- the only
allowed canonical replay input (never a prior ``structured_agent_outputs.
json``, since that would silently freeze in whatever the *old* architecture
already decided) -- through the current, unmodified pipeline functions:

    raw_agent_outputs.json
      -> adapt_run_outputs            (complete claim segmentation)
      -> build_alpha_matches_payload   (factor resolution + Alpha mapping)
      -> build_extracted_structures_payload (relation extraction)
      -> build_structure_graph_stage / score_and_assemble_structure_graph
         (structure graph + activation v1/v2)
      -> detect_alpha_conflicts        (pure function; result is written to
         a replay-local file, never persisted to the database)

No stage here calls TradingAgents, an LLM provider, or a market-data
provider -- ``llm_gateway=None`` throughout, and every function above is a
pure function of its already-materialized JSON inputs. Every replay writes
to a brand-new ``replay-<timestamp>-<uuid>`` directory under
``outputs/replays/`` (never the source run's own directory), and the
source raw artifact's sha256/size/mtime are checked before and after --
any change flips ``status`` to ``"blocked"`` rather than claiming success.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from comqutor_alpha.alpha_library.alpha_loader import TAXONOMY_PATH
from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts
from comqutor_alpha.graph_engine.graph_schema import (
    ACTIVATION_FORMULA_VERSION,
    GRAPH_SCHEMA_VERSION,
)
from comqutor_alpha.graph_engine.pipeline import (
    build_structure_graph_stage,
    score_and_assemble_structure_graph,
)
from comqutor_alpha.storage.file_store import (
    load_json_record,
    run_dir_for,
    validate_run_id_for_path,
)
from comqutor_alpha.structure_engine.alpha_mapper import (
    MAPPER_VERSION,
    build_alpha_matches_payload,
)
from comqutor_alpha.structure_engine.factor_normalizer import ALIAS_VERSION
from comqutor_alpha.structure_engine.relation_grammar import RELATION_GRAMMAR_VERSION
from comqutor_alpha.structure_engine.structure_extractor import (
    EXTRACTOR_VERSION,
    build_extracted_structures_payload,
)
from comqutor_alpha.structure_engine.structured_output_adapter import (
    ADAPTER_VERSION,
    adapt_run_outputs,
)

DEFAULT_SOURCE_OUTPUT_ROOT = "outputs/runs"
DEFAULT_REPLAY_OUTPUT_ROOT = "outputs/replays"
RUN_TYPE = "architecture_replay"
REPLAY_MODE_STRUCTURE_ONLY = "structure_only"

_REPO_ROOT = Path(__file__).resolve().parents[2]


class ReplaySourceIncompleteError(Exception):
    """Raised when the source run has no ``raw_agent_outputs.json``.

    Per Track D's contract, a replay must never silently fall back to an
    old ``structured_agent_outputs.json`` to fake a complete architecture
    replay -- this is the explicit, loud failure instead.
    """


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], capture_output=True, text=True, cwd=_REPO_ROOT, check=True, timeout=10
        )
        return result.stdout.strip()
    except Exception:
        return None


def new_replay_run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"replay-{stamp}-{uuid4().hex[:8]}"


@dataclass(frozen=True)
class ReplayResult:
    source_run_id: str
    replay_run_id: str
    run_type: str
    status: str  # "completed" | "blocked"
    output_dir: str | None
    source_raw_sha256_before: str
    source_raw_sha256_after: str
    source_raw_size_before: int
    source_raw_size_after: int
    source_raw_mtime_before: float
    source_raw_mtime_after: float
    tradingagents_calls: int
    llm_provider_calls: int
    market_data_provider_calls: int
    database_writes: int
    comparison: dict[str, Any] | None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_run_id": self.source_run_id,
            "replay_run_id": self.replay_run_id,
            "run_type": self.run_type,
            "status": self.status,
            "output_dir": self.output_dir,
            "source_raw_sha256_before": self.source_raw_sha256_before,
            "source_raw_sha256_after": self.source_raw_sha256_after,
            "source_raw_size_before": self.source_raw_size_before,
            "source_raw_size_after": self.source_raw_size_after,
            "source_raw_mtime_before": self.source_raw_mtime_before,
            "source_raw_mtime_after": self.source_raw_mtime_after,
            "tradingagents_calls": self.tradingagents_calls,
            "llm_provider_calls": self.llm_provider_calls,
            "market_data_provider_calls": self.market_data_provider_calls,
            "database_writes": self.database_writes,
            "comparison": self.comparison,
            "error": self.error,
        }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def _edge_identity(edge: dict[str, Any]) -> tuple:
    """Claim-level identity for before/after diffing of *candidate* (extracted-
    structures) edges -- matches structure_extractor's own dedup key, so an
    edge here always traces to exactly one claim."""
    return (
        str(edge.get("source_record_id") or ""),
        str(edge.get("source_label") or ""),
        str(edge.get("target_label") or ""),
        str(edge.get("rule_name") or ""),
    )


def _claim_admitted(edge: dict[str, Any], admitted_claim_ids_by_pair: dict[tuple, set[str]]) -> bool:
    """Graph-stage edges merge multiple claims into one (source, target,
    edge_type) row and lose the per-claim rule_name/label fields (they
    become `claim_ids`/`rule_names` lists) -- so admission for one
    candidate edge is "does this claim's id appear in the graph edge that
    shares its (source, target, edge_type) slug triple", not an identity
    match against the candidate edge's own dict shape."""
    pair_key = (str(edge.get("source") or ""), str(edge.get("target") or ""), str(edge.get("edge_type") or ""))
    claim_id = str(edge.get("source_record_id") or "")
    return claim_id in admitted_claim_ids_by_pair.get(pair_key, set())


def _admitted_claim_ids_by_pair(admitted_edges: list[dict[str, Any]]) -> dict[tuple, set[str]]:
    result: dict[tuple, set[str]] = {}
    for edge in admitted_edges:
        if not isinstance(edge, dict):
            continue
        pair_key = (str(edge.get("source") or ""), str(edge.get("target") or ""), str(edge.get("edge_type") or ""))
        result.setdefault(pair_key, set()).update(str(c) for c in (edge.get("claim_ids") or []))
    return result


def _edge_provenance(edge: dict[str, Any], admitted_claim_ids_by_pair: dict[tuple, set[str]]) -> dict[str, Any]:
    return {
        "claim_id": edge.get("source_record_id"),
        "claim": edge.get("source_claim"),
        "source_factor": edge.get("source_label"),
        "relation": edge.get("rule_name"),
        "edge_type": edge.get("edge_type"),
        "target_factor": edge.get("target_label"),
        "assertion_status": edge.get("assertion_status"),
        "admission_result": "admitted" if _claim_admitted(edge, admitted_claim_ids_by_pair) else "candidate_only",
        "rule_id": edge.get("rule_name"),
        "source_agent_output_id": edge.get("source_agent_output_id"),
        "evidence": edge.get("evidence"),
    }


def _load_existing_artifact(source_run_id: str, filename: str, output_root: str) -> dict[str, Any] | None:
    try:
        return load_json_record(source_run_id, filename, output_root=output_root)
    except (FileNotFoundError, ValueError):
        return None


def _build_comparison(
    source_run_id: str,
    source_output_root: str,
    replay_run_id: str,
    structured: dict[str, Any],
    extracted: dict[str, Any],
    graph: dict[str, Any],
) -> dict[str, Any]:
    before_structured = _load_existing_artifact(source_run_id, "structured_agent_outputs.json", source_output_root)
    before_extracted = _load_existing_artifact(source_run_id, "extracted_structures.json", source_output_root)
    before_graph = _load_existing_artifact(source_run_id, "structure_graph.json", source_output_root)

    before_claims = (before_structured or {}).get("records") or []
    after_claims = structured.get("records") or []
    before_factors = (before_extracted or {}).get("nodes") or []
    after_factors = extracted.get("nodes") or []
    before_candidate_edges = (before_extracted or {}).get("edges") or []
    after_candidate_edges = extracted.get("edges") or []
    before_admitted_edges = (before_graph or {}).get("edges") or []
    after_admitted_edges = graph.get("edges") or []

    before_factor_ids = {n.get("id") for n in before_factors if isinstance(n, dict)}
    after_factor_ids = {n.get("id") for n in after_factors if isinstance(n, dict)}

    before_admitted_ids = _admitted_claim_ids_by_pair(before_admitted_edges)
    after_admitted_ids = _admitted_claim_ids_by_pair(after_admitted_edges)

    before_by_id = {_edge_identity(e): e for e in before_candidate_edges if isinstance(e, dict)}
    after_by_id = {_edge_identity(e): e for e in after_candidate_edges if isinstance(e, dict)}

    new_edge_ids = set(after_by_id) - set(before_by_id)
    removed_edge_ids = set(before_by_id) - set(after_by_id)
    unchanged_edge_ids = set(after_by_id) & set(before_by_id)

    before_activation = (before_graph or {}).get("activation") or {}
    after_activation = graph.get("activation") or {}
    before_active = [a for a in (before_activation.get("alphas") or []) if a.get("status") == "active"]
    after_active = [a for a in (after_activation.get("alphas") or []) if a.get("status") == "active"]

    return {
        "source_run_id": source_run_id,
        "replay_run_id": replay_run_id,
        "before_claim_count": len(before_claims),
        "after_claim_count": len(after_claims),
        "claim_count_delta": len(after_claims) - len(before_claims),
        "before_factor_count": len(before_factor_ids),
        "after_factor_count": len(after_factor_ids),
        "new_factors": sorted(str(f) for f in (after_factor_ids - before_factor_ids)),
        "removed_factors": sorted(str(f) for f in (before_factor_ids - after_factor_ids)),
        "before_candidate_edge_count": len(before_candidate_edges),
        "after_candidate_edge_count": len(after_candidate_edges),
        "before_admitted_edge_count": len(before_admitted_edges),
        "after_admitted_edge_count": len(after_admitted_edges),
        "new_edges": [_edge_provenance(after_by_id[i], after_admitted_ids) for i in sorted(new_edge_ids, key=str)],
        "removed_edges": [
            _edge_provenance(before_by_id[i], before_admitted_ids) for i in sorted(removed_edge_ids, key=str)
        ],
        "unchanged_edges": [
            _edge_provenance(after_by_i, after_admitted_ids)
            for i in sorted(unchanged_edge_ids, key=str)
            for after_by_i in [after_by_id[i]]
        ],
        "before_activation_count": len(before_activation.get("alphas") or []),
        "after_activation_count": len(after_activation.get("alphas") or []),
        "activation_changes": {
            "before_active_alpha_ids": sorted(a.get("alpha_id") for a in before_active),
            "after_active_alpha_ids": sorted(a.get("alpha_id") for a in after_active),
        },
        "before_conflict_count": None,  # W4 conflicts are DB-only, never a source artifact (see conflict_engine.pipeline)
        "after_conflict_count": None,  # populated separately in conflict_results.json for this replay
        "conflict_changes": None,
    }


def run_structure_replay(
    source_run_id: str,
    *,
    source_output_root: str = DEFAULT_SOURCE_OUTPUT_ROOT,
    replay_output_root: str = DEFAULT_REPLAY_OUTPUT_ROOT,
    replay_run_id: str | None = None,
    persist: bool = True,
    comparison: bool = True,
) -> ReplayResult:
    """Reprocess ``source_run_id`` through the current structure pipeline.

    Raises ``ReplaySourceIncompleteError`` if the source run has no
    ``raw_agent_outputs.json``. Never mutates anything under
    ``source_output_root`` -- only reads. Returns a ``ReplayResult`` with
    ``status="blocked"`` (never claiming success) if the source raw
    artifact's hash/size/mtime differ after the run than before.
    """
    source_run_id = validate_run_id_for_path(source_run_id)
    source_run_dir = run_dir_for(source_run_id, source_output_root)
    raw_path = source_run_dir / "raw_agent_outputs.json"
    if not raw_path.exists():
        raise ReplaySourceIncompleteError(
            f"REPLAY_SOURCE_INCOMPLETE: no raw_agent_outputs.json for source run {source_run_id!r} "
            f"under {source_output_root!r}"
        )
    metadata_path = source_run_dir / "metadata.json"
    metadata: dict[str, Any] = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}

    sha_before = _sha256_file(raw_path)
    stat_before = raw_path.stat()

    resolved_replay_run_id = validate_run_id_for_path(replay_run_id or new_replay_run_id())

    structured = adapt_run_outputs(source_run_dir, llm_gateway=None)
    alpha_matches = build_alpha_matches_payload(structured)
    extracted = build_extracted_structures_payload(structured)
    graph_stage = build_structure_graph_stage(alpha_matches, extracted)
    graph = score_and_assemble_structure_graph(
        graph_stage, alpha_matches, extracted, structured_records=structured.get("records")
    )
    conflicts = detect_alpha_conflicts(
        run_id=resolved_replay_run_id,
        ticker=str(graph.get("ticker") or ""),
        activation_payload=graph.get("activation") or {},
        alpha_matches=alpha_matches.get("matches") or [],
    )

    sha_after = _sha256_file(raw_path)
    stat_after = raw_path.stat()
    integrity_ok = (
        sha_before == sha_after
        and stat_before.st_size == stat_after.st_size
        and stat_before.st_mtime_ns == stat_after.st_mtime_ns
    )

    if not integrity_ok:
        return ReplayResult(
            source_run_id=source_run_id,
            replay_run_id=resolved_replay_run_id,
            run_type=RUN_TYPE,
            status="blocked",
            output_dir=None,
            source_raw_sha256_before=sha_before,
            source_raw_sha256_after=sha_after,
            source_raw_size_before=stat_before.st_size,
            source_raw_size_after=stat_after.st_size,
            source_raw_mtime_before=stat_before.st_mtime,
            source_raw_mtime_after=stat_after.st_mtime,
            tradingagents_calls=0,
            llm_provider_calls=0,
            market_data_provider_calls=0,
            database_writes=0,
            comparison=None,
            error="REPLAY_SOURCE_INTEGRITY_VIOLATION",
        )

    raw_config = metadata.get("config")
    config: dict[str, Any] = raw_config if isinstance(raw_config, dict) else {}
    lineage = {
        "run_id": resolved_replay_run_id,
        "run_type": RUN_TYPE,
        "replay_run_id": resolved_replay_run_id,
        "source_run_id": source_run_id,
        "source_ticker": metadata.get("ticker"),
        "source_trade_date": metadata.get("trade_date") or metadata.get("analysis_date"),
        "source_raw_artifact_path": str(raw_path),
        "source_raw_sha256": sha_before,
        "source_raw_output_count": len(
            json.loads(raw_path.read_text(encoding="utf-8")).get("agent_outputs") or []
        ),
        "source_profile_id": metadata.get("profile_id"),
        "source_provider": metadata.get("llm_provider") or config.get("llm_provider"),
        "source_models": {
            "quick_think_llm": metadata.get("quick_think_llm") or config.get("quick_think_llm"),
            "deep_think_llm": metadata.get("deep_think_llm") or config.get("deep_think_llm"),
        },
        "source_created_at": metadata.get("created_at"),
        "replay_created_at": _utc_now_iso(),
        "replay_mode": REPLAY_MODE_STRUCTURE_ONLY,
        "pipeline_git_head": _git("rev-parse", "HEAD") or "unknown",
        "pipeline_worktree_dirty": bool(_git("status", "--porcelain") or ""),
        "pipeline_version": ADAPTER_VERSION,
        "claim_adapter_version": ADAPTER_VERSION,
        "taxonomy_version": TAXONOMY_PATH.stem,
        "alias_version": ALIAS_VERSION,
        "relation_grammar_version": RELATION_GRAMMAR_VERSION,
        "graph_schema_version": graph.get("schema_version") or GRAPH_SCHEMA_VERSION,
        "activation_version": graph.get("primary_activation_version") or ACTIVATION_FORMULA_VERSION,
        "mapper_version": MAPPER_VERSION,
        "extractor_version": EXTRACTOR_VERSION,
        "tradingagents_calls": 0,
        "llm_provider_calls": 0,
        "market_data_provider_calls": 0,
        "database_writes": 0,
    }

    comparison_payload = None
    if comparison:
        comparison_payload = _build_comparison(
            source_run_id, source_output_root, resolved_replay_run_id, structured, extracted, graph
        )
        comparison_payload["after_conflict_count"] = len(conflicts.get("conflicts") or [])

    output_dir_str = None
    if persist:
        target_dir = run_dir_for(resolved_replay_run_id, replay_output_root)
        if target_dir.exists() and any(target_dir.iterdir()):
            raise FileExistsError(f"Replay output directory already exists and is non-empty: {target_dir}")
        _write_json(target_dir / "metadata.json", lineage)
        _write_json(target_dir / "structured_agent_outputs.json", structured)
        _write_json(target_dir / "extracted_structures.json", extracted)
        _write_json(target_dir / "structure_graph.json", graph)
        _write_json(target_dir / "conflict_results.json", conflicts)
        if comparison_payload is not None:
            _write_json(target_dir / "replay_comparison.json", comparison_payload)
        output_dir_str = str(target_dir)

    return ReplayResult(
        source_run_id=source_run_id,
        replay_run_id=resolved_replay_run_id,
        run_type=RUN_TYPE,
        status="completed",
        output_dir=output_dir_str,
        source_raw_sha256_before=sha_before,
        source_raw_sha256_after=sha_after,
        source_raw_size_before=stat_before.st_size,
        source_raw_size_after=stat_after.st_size,
        source_raw_mtime_before=stat_before.st_mtime,
        source_raw_mtime_after=stat_after.st_mtime,
        tradingagents_calls=0,
        llm_provider_calls=0,
        market_data_provider_calls=0,
        database_writes=0,
        comparison=comparison_payload,
        error=None,
    )


__all__ = [
    "DEFAULT_SOURCE_OUTPUT_ROOT",
    "DEFAULT_REPLAY_OUTPUT_ROOT",
    "RUN_TYPE",
    "REPLAY_MODE_STRUCTURE_ONLY",
    "ReplayResult",
    "ReplaySourceIncompleteError",
    "new_replay_run_id",
    "run_structure_replay",
]
