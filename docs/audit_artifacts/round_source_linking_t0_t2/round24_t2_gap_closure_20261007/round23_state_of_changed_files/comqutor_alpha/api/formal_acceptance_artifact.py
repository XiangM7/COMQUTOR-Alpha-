"""Round 5 (2026-10-04), T2 closing gap: wires ``comqutor_alpha.regression.
acceptance_engine.run_formal_acceptance`` into the REAL production pipeline
as an additive, best-effort artifact write -- before this, the formal
acceptance entry point (taxonomy/rule-version-pinned, six rule families,
``effective_rules`` attached to every verdict) was only ever invoked by
test files and one-off offline scripts under ``docs/audit_artifacts/``, so
a real completed run never actually produced a formal acceptance verdict
of its own.

This is the ONLY place outside ``comqutor_alpha/regression/*.py`` itself
that imports Gold label data (``comqutor_alpha.regression.labels``/
``labels_v2``) -- deliberately isolated into its own module so the import
boundary stays small and auditable (see
``tests/test_no_gold_label_import_in_research_path.py``, the guard test
added alongside this). This is the POST-HOC acceptance/grading layer
John's own T2 section explicitly requires reading Gold's allowed-conflict/
expected-alpha declarations AFTER research is complete, to check the
already-produced output -- never fed into the research Agent's own prompt
or used to rewrite a claim (that remains forbidden, unchanged, and is
exactly what the import-boundary guard test polices for every OTHER
module on the research/scoring path).

Zero Provider calls; reads only label YAML files and this SAME run's own
already-computed in-memory payloads (graph_payload/conflict_payload/
alpha_matches_payload) -- never re-fetches, never re-scores, never alters
any of them.

T2 (2026-10-07): a rule or execution problem is now VISIBLE. Before, every
exception was swallowed and nothing was written, so a broken rule file left
a completed run with no formal-acceptance artifact and no error anywhere
but one log line -- exactly the "silent" outcome John's task sheet forbids
("规则缺失…应输出配置／执行错误"). Now a rule-file problem is persisted as
``formal_status = config_error`` (with the engine's own reason code) and an
unexpected failure as ``formal_status = execution_error``; neither is ever
a pass, and neither can fail the run itself."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from comqutor_alpha.regression.acceptance_engine import (
    FORMAL_STATUS_CONFIG_ERROR,
    FORMAL_STATUS_EXECUTION_ERROR,
    AcceptanceConfigError,
    effective_rules,
    run_formal_acceptance,
)
from comqutor_alpha.regression.evaluator import (
    conflict_comparison,
    detected_alpha_sets,
    six_ticker_qa_alpha_fields,
    six_ticker_qa_conflict_fields,
    stance_source,
)
from comqutor_alpha.regression.labels import load_j2_labels, ticker_label
from comqutor_alpha.regression.labels_v2 import (
    LabelV2ValidationError,
    load_j2_labels_v2,
    ticker_label_v2,
)
from comqutor_alpha.storage.file_store import save_json_record

logger = logging.getLogger(__name__)

FORMAL_ACCEPTANCE_ARTIFACT_FILENAME = "formal_acceptance.json"
FORMAL_ACCEPTANCE_SCHEMA_VERSION = "comqutor.formal_acceptance_artifact.v2"

REASON_RULE_FILE_UNUSABLE = "ACCEPTANCE_RULE_FILE_UNUSABLE"
REASON_EXECUTION_ERROR = "ACCEPTANCE_EXECUTION_ERROR"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DETAIL_LIMIT = 500


def _clean_detail(text: str) -> str:
    """An error detail must not carry the engineer's home directory (John: no absolute paths) and must stay short."""
    cleaned = str(text).replace(str(_REPO_ROOT) + "/", "").replace(str(_REPO_ROOT), "<repo>")
    return cleaned[:_DETAIL_LIMIT]


def _error_artifact(*, run_id: str, ticker: str, status: str, reason_code: str, detail: str) -> dict[str, Any]:
    prefix = "config_error" if status == FORMAL_STATUS_CONFIG_ERROR else "execution_error"
    return {
        "schema_version": FORMAL_ACCEPTANCE_SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "label_v1_version": None,
        "label_v2_version": None,
        "formal_status": status,
        f"{prefix}_reason_code": reason_code,
        f"{prefix}_detail": _clean_detail(detail),
        "rule_family_results": {},
    }


def write_formal_acceptance_artifact(
    *,
    run_id: str,
    ticker: str,
    output_root: Any,
    graph_payload: dict[str, Any] | None,
    conflict_payload: dict[str, Any] | None,
    alpha_matches_payload: dict[str, Any] | None,
    artifact_completeness: str | None,
) -> dict[str, Any] | None:
    """Builds this run's own ``evaluate_ticker_result`` from its already-
    computed in-memory payloads (the SAME ones ``finalize_completed_run_
    artifacts`` just used -- never re-read from disk, never re-derived a
    second way) and real Gold label lookups (``None`` for a ticker with no
    declared label at all, which the engine reports as a configuration error
    -- no requirement is fabricated and no PASS is manufactured), then calls
    the real ``run_formal_acceptance`` and persists its verdict additively as
    ``formal_acceptance.json``.

    Best-effort by design, matching this call site's siblings in
    ``routes_research.py`` (``finalize_completed_run_artifacts``/
    ``write_run_audit_artifact``): nothing here ever raises, so a formal-
    acceptance problem can never take down an otherwise-successful run
    completion. But it is never silent either: a rule-file problem is
    written as ``config_error`` and any other failure as ``execution_error``.
    Returns the written artifact, or ``None`` only when even writing the
    artifact failed (never a fabricated verdict)."""
    try:
        graph_payload = graph_payload or {}
        conflict_payload = conflict_payload or {}
        alpha_matches_payload = alpha_matches_payload or {}

        try:
            effective_rules()  # validates every rule file once, up front, with the engine's own reason codes
            labels_v1 = load_j2_labels()
            labels_v2 = load_j2_labels_v2()
        except AcceptanceConfigError as exc:
            logger.warning("formal acceptance: rule configuration error (run_id=%s): %s", run_id, exc)
            artifact = _error_artifact(
                run_id=run_id, ticker=ticker, status=FORMAL_STATUS_CONFIG_ERROR, reason_code=exc.reason_code, detail=exc.detail
            )
        except Exception as exc:  # a rule file that cannot even be loaded is a configuration problem, not a reason to stay silent
            logger.warning("formal acceptance: rule file unusable (run_id=%s): %s", run_id, exc)
            reason = exc.reason_code if isinstance(exc, LabelV2ValidationError) else REASON_RULE_FILE_UNUSABLE
            artifact = _error_artifact(
                run_id=run_id,
                ticker=ticker,
                status=FORMAL_STATUS_CONFIG_ERROR,
                reason_code=reason,
                detail=f"{type(exc).__name__}: {exc}",
            )
        else:
            label_block_v1 = ticker_label(labels_v1, ticker)
            label_block_v2 = ticker_label_v2(labels_v2, ticker)

            detected = detected_alpha_sets(graph_payload)
            conflict_cmp = conflict_comparison(label_block_v1, conflict_payload)

            evaluate_ticker_result = {
                "ticker": ticker,
                "run_id": run_id,
                "run_selection_status": "selected",
                "offline_reprocess_status": "completed",
                "artifact_completeness": artifact_completeness,
                "artifact_missing_files": [],
                "detected_alphas": detected["detected_alphas"],
                "dominant_alphas": detected["dominant_alphas"],
                **conflict_cmp,
                **six_ticker_qa_conflict_fields(conflict_cmp),
                **six_ticker_qa_alpha_fields(label_block_v1, detected),
                "stance_source": stance_source(alpha_matches_payload),
                "evaluation_authority": "live_production_run",
                "execution_type": "LIVE_RUN_FORMAL_ACCEPTANCE",
                "note": (
                    "Computed inline at the end of this SAME run's own completion flow, from the "
                    "SAME in-memory graph/conflict/alpha_matches payloads this run already persisted -- "
                    "never a second recompute, never a different run's data."
                ),
            }

            verdict = run_formal_acceptance(
                ticker=ticker,
                ticker_v2_label=label_block_v2,
                label_block_v1=label_block_v1,
                evaluate_ticker_result=evaluate_ticker_result,
                conflict_payload=conflict_payload,
                graph_payload=graph_payload,
                alpha_matches_payload=alpha_matches_payload,
            )
            artifact = {
                "schema_version": FORMAL_ACCEPTANCE_SCHEMA_VERSION,
                "run_id": run_id,
                "ticker": ticker,
                "label_v1_version": labels_v1.get("label_version"),
                "label_v2_version": labels_v2.get("label_version"),
                **verdict,
            }
    except Exception as exc:
        logger.warning("formal acceptance verdict could not be computed (run_id=%s)", run_id, exc_info=True)
        artifact = _error_artifact(
            run_id=run_id,
            ticker=ticker,
            status=FORMAL_STATUS_EXECUTION_ERROR,
            reason_code=REASON_EXECUTION_ERROR,
            detail=f"{type(exc).__name__}: {exc}",
        )

    try:
        save_json_record(run_id, FORMAL_ACCEPTANCE_ARTIFACT_FILENAME, artifact, output_root=output_root)
    except Exception:
        logger.warning("formal acceptance artifact write failed (run_id=%s)", run_id, exc_info=True)
        return None
    return artifact


__all__ = [
    "FORMAL_ACCEPTANCE_ARTIFACT_FILENAME",
    "FORMAL_ACCEPTANCE_SCHEMA_VERSION",
    "write_formal_acceptance_artifact",
]
