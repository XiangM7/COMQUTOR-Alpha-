"""T2 six-ticker re-verdict, THIS ROUND (2026-09-29), under a SEPARATE
execution id/output file -- never overwrites the original
t2_six_ticker_acceptance_verdicts.json (2026-09-26). Same Type A method as
that original script (research/conflict-detection output read completely
unchanged from each ticker's own already-persisted artifacts; only the
acceptance/verdict layer -- comqutor_alpha.regression.acceptance_engine
.run_formal_acceptance -- is (re-)executed, using the FINAL, current code
after this round's gate-bypass fix, T1 source chains, and Replay-consistency
fixes). Zero Provider calls, zero recompute, zero Fresh Run, zero write to
any of the six original run directories under outputs/runs/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

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
from comqutor_alpha.regression.run_selection import select_run_for_ticker
from comqutor_alpha.storage.file_store import load_json_record_if_exists

TICKER_RUNS = {
    "NVDA": "ded99ecd-a186-4a90-859e-0f1a0efa43db",
    "QQQ": "0d890564-2479-4361-94e8-25c48af3b9a8",
    "SNDK": "e8e0f398-7b26-4462-8135-a1410ea5b335",
    "MSFT": "64568bfb-fe0c-453c-9872-831a8dc339a0",
    "TSM": "fc09821e-c7cf-40a7-bd76-c98172e16992",
    "AMD": "d5b60b8a-66b8-44c1-9f55-ee345e58c48d",
}
SOURCE_OUTPUT_ROOT = "outputs/runs"
EXECUTION_ID = "t2_six_ticker_acceptance_reeval_2026-09-29"


def build_type_a_evaluate_ticker_result(ticker: str, run_id: str, label_block_v1) -> tuple[dict, dict, dict, dict]:
    selection = select_run_for_ticker(ticker, output_root=SOURCE_OUTPUT_ROOT)
    file_completeness = selection.get("file_artifact_completeness")
    missing_files = selection.get("file_artifact_missing") or []

    graph_payload = load_json_record_if_exists(run_id, "structure_graph.json", output_root=SOURCE_OUTPUT_ROOT) or {}
    conflict_payload = load_json_record_if_exists(run_id, "conflicts.json", output_root=SOURCE_OUTPUT_ROOT) or {}
    alpha_matches_payload = load_json_record_if_exists(run_id, "alpha_matches.json", output_root=SOURCE_OUTPUT_ROOT) or {}

    detected = detected_alpha_sets(graph_payload)
    conflict_cmp = conflict_comparison(label_block_v1, conflict_payload)

    result = {
        "ticker": ticker,
        "run_id": run_id,
        "run_selection_status": "selected",
        "offline_reprocess_status": "completed",
        "artifact_completeness": file_completeness,
        "artifact_missing_files": missing_files,
        "detected_alphas": detected["detected_alphas"],
        "dominant_alphas": detected["dominant_alphas"],
        **conflict_cmp,
        **six_ticker_qa_conflict_fields(conflict_cmp),
        **six_ticker_qa_alpha_fields(label_block_v1, detected),
        "stance_source": stance_source(alpha_matches_payload),
        "evaluation_authority": "provisional",
        "execution_type": "A_REEVALUATION",
        "note": "Type A (旧结果复评): admitted_conflicts/detected_alphas/stance_source read directly from this run_id's own already-persisted conflicts.json/structure_graph.json/alpha_matches.json -- no Architecture Replay, no recompute.",
    }
    return result, graph_payload, conflict_payload, alpha_matches_payload


def main() -> None:
    labels_v1 = load_j2_labels()
    labels_v2 = load_j2_labels_v2()

    out = {
        "schema_version": "t2_six_ticker_acceptance_verdicts.v1",
        "execution_id": EXECUTION_ID,
        "execution_classification": "A_REEVALUATION",
        "based_on_original_execution_id": "acceptance_engine_six_ticker_v1_2026-09-26",
        "note": (
            "Every ticker below is evaluated by reading its own already-persisted run artifacts "
            "unchanged and re-running only the acceptance/verdict layer, under FINAL code as of "
            "2026-09-29 (after this round's gate-bypass closing fix, T1 market/derived-indicator/"
            "financial/macro source chains, and Replay-consistency fixes) -- zero Provider calls, "
            "zero recompute, zero Fresh Run. This is a SEPARATE execution id; it never overwrites "
            "acceptance_engine_six_ticker_v1_2026-09-26's own output file or verdicts."
        ),
        "label_v1_version": labels_v1.get("label_version"),
        "label_v2_version": labels_v2.get("label_version"),
        "tickers": {},
    }

    for ticker, run_id in TICKER_RUNS.items():
        label_block_v1 = ticker_label(labels_v1, ticker)
        label_block_v2 = ticker_label_v2(labels_v2, ticker)

        eval_result, graph_payload, conflict_payload, alpha_matches_payload = build_type_a_evaluate_ticker_result(
            ticker, run_id, label_block_v1
        )

        if eval_result["artifact_completeness"] != "pass":
            out["tickers"][ticker] = {
                "status": "INCOMPLETE_ARTIFACTS",
                "run_id": run_id,
                "artifact_completeness": eval_result["artifact_completeness"],
                "artifact_missing_files": eval_result["artifact_missing_files"],
                "note": "listed as missing/incomplete -- never defaulted to pass",
            }
            print(f"{ticker}: INCOMPLETE_ARTIFACTS missing={eval_result['artifact_missing_files']}")
            continue

        # 2026-09-30 closing fix: alpha_matches_payload is now REQUIRED --
        # this run's own real, already-persisted alpha_matches.json is
        # passed through so run_formal_acceptance can genuinely verify
        # Alpha semantic availability, never silently defaulting to a PASS
        # because this parameter was left unset.
        acceptance = run_formal_acceptance(
            ticker=ticker,
            ticker_v2_label=label_block_v2,
            label_block_v1=label_block_v1,
            evaluate_ticker_result=eval_result,
            conflict_payload=conflict_payload,
            graph_payload=graph_payload,
            alpha_matches_payload=alpha_matches_payload,
        )

        out["tickers"][ticker] = {
            "status": "EVALUATED",
            "run_id": run_id,
            "execution_type": "A_REEVALUATION",
            "provider_calls": 0,
            "artifact_completeness": eval_result["artifact_completeness"],
            "stance_source": eval_result["stance_source"],
            "admitted_conflicts": eval_result.get("admitted_conflicts"),
            "candidate_conflicts": eval_result.get("candidate_conflicts"),
            "main_conflict": eval_result.get("main_conflict"),
            "formal_status": acceptance["formal_status"],
            "rule_family_results": acceptance.get("rule_family_results", {}),
            "v2_contract_result": acceptance.get("v2_contract_result"),
            "effective_rules_taxonomy_sha256": acceptance.get("effective_rules", {}).get("taxonomy", {}).get("sha256"),
            "effective_rules_label_v2_sha256": acceptance.get("effective_rules", {}).get("label_v2", {}).get("sha256"),
        }
        print(
            f"{ticker}: formal_status={acceptance['formal_status']} "
            f"admitted={eval_result.get('admitted_conflicts')} stance_source={eval_result['stance_source']}"
        )

    out_path = REPO_ROOT / "docs/audit_artifacts/round_source_linking_t0_t2/t2_six_ticker_acceptance_verdicts_2026-09-29.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=False), encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
