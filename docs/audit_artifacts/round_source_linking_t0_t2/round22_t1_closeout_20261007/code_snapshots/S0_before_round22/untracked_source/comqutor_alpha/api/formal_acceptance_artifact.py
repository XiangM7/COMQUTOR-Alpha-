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
any of them."""

from __future__ import annotations

import logging
from typing import Any

from comqutor_alpha.regression.acceptance_engine import run_formal_acceptance
from comqutor_alpha.regression.evaluator import (
    conflict_comparison,
    detected_alpha_sets,
    six_ticker_qa_alpha_fields,
    six_ticker_qa_conflict_fields,
    stance_source,
)
from comqutor_alpha.regression.labels import load_j2_labels, ticker_label
from comqutor_alpha.regression.labels_v2 import load_j2_labels_v2, ticker_label_v2
from comqutor_alpha.storage.file_store import save_json_record

logger = logging.getLogger(__name__)

FORMAL_ACCEPTANCE_ARTIFACT_FILENAME = "formal_acceptance.json"
FORMAL_ACCEPTANCE_SCHEMA_VERSION = "comqutor.formal_acceptance_artifact.v1"


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
    declared label at all -- a real, honest, safely-handled state every
    rule family already degrades gracefully for, never a crash and never a
    fabricated requirement), then calls the real ``run_formal_acceptance``
    and persists its verdict additively as ``formal_acceptance.json``.

    Best-effort by design, matching this call site's siblings in
    ``routes_research.py`` (``finalize_completed_run_artifacts``/
    ``write_run_audit_artifact``): any exception here is logged and
    swallowed, never raised -- a formal-acceptance computation problem
    must never take down an otherwise-successful run completion. Returns
    the written verdict dict, or ``None`` if anything above prevented it
    (never returns a fabricated verdict)."""
    try:
        graph_payload = graph_payload or {}
        conflict_payload = conflict_payload or {}
        alpha_matches_payload = alpha_matches_payload or {}

        labels_v1 = load_j2_labels()
        labels_v2 = load_j2_labels_v2()
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
        save_json_record(run_id, FORMAL_ACCEPTANCE_ARTIFACT_FILENAME, artifact, output_root=output_root)
        return artifact
    except Exception:
        logger.warning("formal acceptance artifact write failed (run_id=%s)", run_id, exc_info=True)
        return None


__all__ = ["FORMAL_ACCEPTANCE_ARTIFACT_FILENAME", "write_formal_acceptance_artifact"]
