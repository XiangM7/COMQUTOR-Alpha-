"""Runs one evaluation case (frozen_golden_case / historical_replay_case /
live_smoke_result) purely offline.

``frozen_golden_case`` and ``historical_replay_case`` both reuse
``comqutor_alpha.replay.pipeline.run_structure_replay`` -- the exact same
production Architecture Replay service (0 Provider calls, source-artifact
integrity checked, never mutates the source) -- to regenerate structure/
activation/conflict output from already-materialized ``raw_agent_outputs.
json``. ``live_smoke_result`` never replays anything: it only checks that
an existing run completed and its artifacts are schema-valid, since its own
text output is non-deterministic and must never be used as an exact
golden oracle.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from comqutor_alpha.evaluation.expectations import ExpectationResult, evaluate_expected
from comqutor_alpha.evaluation.golden_case import GoldenCase, verify_artifact_hashes
from comqutor_alpha.replay.pipeline import (
    ReplaySourceIncompleteError,
    run_structure_replay,
)
from comqutor_alpha.storage.file_store import run_dir_for

STATUS_COMPLETED = "completed"
STATUS_PENDING_FIXTURE = "pending_fixture"
STATUS_BLOCKED = "blocked"
STATUS_ERROR = "error"


@dataclass
class CaseResult:
    case_id: str
    case_type: str
    ticker: str
    status: str
    skipped_reason: str | None = None
    error: str | None = None
    replay_run_id: str | None = None
    source_run_id: str | None = None
    provider_calls: int = 0
    hash_mismatches: list[str] = field(default_factory=list)
    actual: dict[str, Any] = field(default_factory=dict)
    expectation_results: list[ExpectationResult] = field(default_factory=list)

    @property
    def required_expectations_passed(self) -> bool:
        return all(r.passed for r in self.expectation_results if not r.manual)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "case_type": self.case_type,
            "ticker": self.ticker,
            "status": self.status,
            "skipped_reason": self.skipped_reason,
            "error": self.error,
            "replay_run_id": self.replay_run_id,
            "source_run_id": self.source_run_id,
            "provider_calls": self.provider_calls,
            "hash_mismatches": self.hash_mismatches,
            "required_expectations_passed": self.required_expectations_passed if self.status == STATUS_COMPLETED else None,
            "expectation_results": [r.to_dict() for r in self.expectation_results],
            "metrics": _summarize_actual_for_report(self.actual),
        }


def _summarize_actual_for_report(actual: dict[str, Any]) -> dict[str, Any]:
    if not actual:
        return {}
    graph = actual.get("graph") or {}
    activation = actual.get("activation") or {}
    conflicts = actual.get("conflicts") or {}
    claims = actual.get("claims") or {}
    return {
        "graph_node_count": graph.get("node_count"),
        "graph_edge_count": graph.get("edge_count"),
        "active_alpha_count": len(activation.get("active_alpha_ids") or []),
        "regime_level_alpha_count": len(activation.get("regime_level_alpha_ids") or []),
        "admitted_conflict_count": len(conflicts.get("admitted") or []),
        "main_conflict_id": conflicts.get("main_conflict_id"),
        "retained_claim_count": claims.get("retained_claim_count"),
    }


def _read_replay_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _actual_from_replayed_artifacts(structured: dict, graph: dict, conflicts: dict) -> dict[str, Any]:
    graph_metrics = graph.get("graph_metrics") if isinstance(graph.get("graph_metrics"), dict) else {}
    activation = graph.get("activation") if isinstance(graph.get("activation"), dict) else {}
    alphas = activation.get("alphas") if isinstance(activation.get("alphas"), list) else []

    def _ids_with_status(status: str) -> list[str]:
        return [a.get("alpha_id") for a in alphas if isinstance(a, dict) and a.get("status") == status]

    conflict_entries = conflicts.get("conflicts") if isinstance(conflicts.get("conflicts"), list) else []
    admitted = [
        {
            "pair_id": f"{c.get('alpha_a')}__{c.get('alpha_b')}",
            "bull_raw_claim_count": c.get("bull_raw_claim_count"),
            "bear_raw_claim_count": c.get("bear_raw_claim_count"),
        }
        for c in conflict_entries
        if isinstance(c, dict)
    ]
    main_conflict = conflicts.get("main_conflict") if isinstance(conflicts.get("main_conflict"), dict) else None

    records = structured.get("records") if isinstance(structured.get("records"), list) else []
    structured_metadata = structured.get("metadata") if isinstance(structured.get("metadata"), dict) else {}

    return {
        "graph": {
            "node_count": int(graph_metrics.get("node_count") or 0),
            "edge_count": int(graph_metrics.get("edge_count") or 0),
            "edges": graph.get("edges") if isinstance(graph.get("edges"), list) else [],
        },
        "activation": {
            "alphas": alphas,
            "active_alpha_ids": _ids_with_status("active"),
            "dominant_alpha_ids": _ids_with_status("dominant"),
            "regime_level_alpha_ids": _ids_with_status("regime_level"),
        },
        "conflicts": {
            "main_conflict_id": (main_conflict or {}).get("conflict_id"),
            "admitted": admitted,
            "declared_pair_count": ((conflicts.get("arbitration") or {}).get("declared_pair_count")),
            "evaluated_pair_count": len((conflicts.get("arbitration") or {}).get("candidate_evaluations") or []),
        },
        "claims": {
            "texts": [r.get("claim_text") or r.get("evidence") or "" for r in records if isinstance(r, dict)],
            "retained_claim_count": len(records),
            "analytical_claim_count": int(structured_metadata.get("analytical_claim_count") or 0),
            "context_only_claim_count": int(structured_metadata.get("context_only_claim_count") or 0),
        },
    }


def _run_replay_backed_case(
    *,
    case_id: str,
    ticker: str,
    case_type: str,
    source_run_id: str,
    source_output_root: str,
    replay_output_root: str,
) -> CaseResult:
    try:
        result = run_structure_replay(
            source_run_id,
            source_output_root=source_output_root,
            replay_output_root=replay_output_root,
            persist=True,
            comparison=False,
        )
    except ReplaySourceIncompleteError as exc:
        return CaseResult(
            case_id=case_id,
            case_type=case_type,
            ticker=ticker,
            status=STATUS_PENDING_FIXTURE,
            skipped_reason=str(exc),
            source_run_id=source_run_id,
        )
    except Exception as exc:  # noqa: BLE001 -- a case failure must never crash the whole harness run
        return CaseResult(
            case_id=case_id,
            case_type=case_type,
            ticker=ticker,
            status=STATUS_ERROR,
            error=f"{type(exc).__name__}: {exc}",
            source_run_id=source_run_id,
        )

    if result.status != "completed" or not result.output_dir:
        return CaseResult(
            case_id=case_id,
            case_type=case_type,
            ticker=ticker,
            status=STATUS_BLOCKED,
            skipped_reason=result.error or "REPLAY_BLOCKED",
            source_run_id=source_run_id,
            replay_run_id=result.replay_run_id,
        )

    output_dir = Path(result.output_dir)
    replay_run_id = result.replay_run_id
    # comqutor_alpha.replay.pipeline writes its own output directly (not
    # through file_store's artifact-filename allowlist, since
    # "conflict_results.json" is a replay-only filename never served by any
    # API route) -- read the same way here, read-only, never through
    # file_store.
    structured = _read_replay_json(output_dir / "structured_agent_outputs.json")
    graph = _read_replay_json(output_dir / "structure_graph.json")
    conflicts = _read_replay_json(output_dir / "conflict_results.json")

    actual = _actual_from_replayed_artifacts(structured, graph, conflicts)
    return CaseResult(
        case_id=case_id,
        case_type=case_type,
        ticker=ticker,
        status=STATUS_COMPLETED,
        source_run_id=source_run_id,
        replay_run_id=replay_run_id,
        provider_calls=result.llm_provider_calls + result.tradingagents_calls + result.market_data_provider_calls,
        actual=actual,
    )


def _run_live_smoke_case(case_id: str, ticker: str, source_run_id: str, source_output_root: str) -> CaseResult:
    """Checks that an existing (already-completed) live run is schema-valid
    and finished -- never replays it, never treats its text output as an
    exact oracle."""
    run_dir = run_dir_for(source_run_id, source_output_root)
    if not run_dir.exists():
        return CaseResult(
            case_id=case_id,
            case_type="live_smoke_result",
            ticker=ticker,
            status=STATUS_PENDING_FIXTURE,
            skipped_reason=f"LIVE_SMOKE_SOURCE_NOT_FOUND: {run_dir}",
            source_run_id=source_run_id,
        )
    required = ("metadata.json", "raw_agent_outputs.json", "structured_agent_outputs.json", "alpha_matches.json")
    missing = [name for name in required if not (run_dir / name).exists()]
    if missing:
        return CaseResult(
            case_id=case_id,
            case_type="live_smoke_result",
            ticker=ticker,
            status=STATUS_BLOCKED,
            skipped_reason=f"LIVE_SMOKE_INCOMPLETE_ARTIFACTS: missing {missing}",
            source_run_id=source_run_id,
        )
    return CaseResult(
        case_id=case_id,
        case_type="live_smoke_result",
        ticker=ticker,
        status=STATUS_COMPLETED,
        source_run_id=source_run_id,
        actual={},
    )


def run_case(case: GoldenCase, *, evaluation_output_root: str) -> CaseResult:
    hash_mismatches = verify_artifact_hashes(case)

    if case.case_type == "frozen_golden_case":
        if not case.has_frozen_raw_outputs():
            return CaseResult(
                case_id=case.case_id,
                case_type=case.case_type,
                ticker=case.ticker,
                status=STATUS_PENDING_FIXTURE,
                skipped_reason="GOLDEN_CASE_RAW_OUTPUTS_NOT_PRESENT",
                hash_mismatches=hash_mismatches,
            )
        result = _run_replay_backed_case(
            case_id=case.case_id,
            ticker=case.ticker,
            case_type=case.case_type,
            source_run_id=case.case_dir.name,
            source_output_root=str(case.case_dir.parent),
            replay_output_root=str(Path(evaluation_output_root) / "replays"),
        )
    elif case.case_type == "historical_replay_case":
        source_run_id = case.source_run_id
        if not source_run_id:
            return CaseResult(
                case_id=case.case_id,
                case_type=case.case_type,
                ticker=case.ticker,
                status=STATUS_PENDING_FIXTURE,
                skipped_reason="HISTORICAL_REPLAY_CASE_MISSING_SOURCE_RUN_ID",
                hash_mismatches=hash_mismatches,
            )
        source_output_root = str(case.case_yaml.get("source_output_root") or "outputs/runs")
        result = _run_replay_backed_case(
            case_id=case.case_id,
            ticker=case.ticker,
            case_type=case.case_type,
            source_run_id=source_run_id,
            source_output_root=source_output_root,
            replay_output_root=str(Path(evaluation_output_root) / "replays"),
        )
    elif case.case_type == "live_smoke_result":
        source_run_id = case.source_run_id
        if not source_run_id:
            return CaseResult(
                case_id=case.case_id,
                case_type=case.case_type,
                ticker=case.ticker,
                status=STATUS_PENDING_FIXTURE,
                skipped_reason="LIVE_SMOKE_MISSING_SOURCE_RUN_ID",
                hash_mismatches=hash_mismatches,
            )
        source_output_root = str(case.case_yaml.get("source_output_root") or "outputs/runs")
        result = _run_live_smoke_case(case.case_id, case.ticker, source_run_id, source_output_root)
    else:
        return CaseResult(
            case_id=case.case_id,
            case_type=case.case_type,
            ticker=case.ticker,
            status=STATUS_ERROR,
            error=f"UNKNOWN_CASE_TYPE: {case.case_type!r}",
            hash_mismatches=hash_mismatches,
        )

    result.hash_mismatches = hash_mismatches
    if result.status == STATUS_COMPLETED and case.case_type != "live_smoke_result":
        # live_smoke_result carries no golden oracle -- expected.yaml for
        # that type must stay empty/manual_review only (enforced by
        # convention/tests, not fabricated here).
        result.expectation_results = evaluate_expected(case.expected, result.actual)
    return result


__all__ = ["CaseResult", "run_case", "STATUS_COMPLETED", "STATUS_PENDING_FIXTURE", "STATUS_BLOCKED", "STATUS_ERROR"]
