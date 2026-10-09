"""T2: applies the new unified acceptance engine to the six historical
tickers' EXISTING, ALREADY-PERSISTED research artifacts -- Type A
(旧结果复评): research/conflict-detection output is read completely
unchanged; only the acceptance/verdict layer is (re-)executed on top of it.
Zero Provider calls, zero recompute of any kind (no Architecture Replay,
unlike evaluate_ticker's own Type-B replay path, which recomputes B1 stance
via a deterministic-only fallback and would otherwise misleadingly show
near-zero evidence everywhere it lacks a live LLM gateway)."""
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


def build_type_a_evaluate_ticker_result(ticker: str, run_id: str, label_block_v1) -> tuple[dict, dict, dict]:
    """Type A: reads run_id's OWN already-persisted artifacts, unchanged.
    Returns (evaluate_ticker_result_shaped_dict, graph_payload, conflict_payload)."""
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
    return result, graph_payload, conflict_payload


def main() -> None:
    labels_v1 = load_j2_labels()
    labels_v2 = load_j2_labels_v2()

    out = {
        "schema_version": "t2_six_ticker_acceptance_verdicts.v1",
        "execution_classification": "A_REEVALUATION",
        "note": "Every ticker below is evaluated by reading its own already-persisted run artifacts unchanged and re-running only the acceptance/verdict layer -- zero Provider calls, zero recompute.",
        "label_v1_version": labels_v1.get("label_version"),
        "label_v2_version": labels_v2.get("label_version"),
        "tickers": {},
    }

    for ticker, run_id in TICKER_RUNS.items():
        label_block_v1 = ticker_label(labels_v1, ticker)
        label_block_v2 = ticker_label_v2(labels_v2, ticker)

        eval_result, graph_payload, conflict_payload = build_type_a_evaluate_ticker_result(ticker, run_id, label_block_v1)

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

        acceptance = run_formal_acceptance(
            ticker=ticker,
            ticker_v2_label=label_block_v2,
            label_block_v1=label_block_v1,
            evaluate_ticker_result=eval_result,
            conflict_payload=conflict_payload,
            graph_payload=graph_payload,
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

    out_path = REPO_ROOT / "docs/audit_artifacts/round_source_linking_t0_t2/t2_six_ticker_acceptance_verdicts.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=False), encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
