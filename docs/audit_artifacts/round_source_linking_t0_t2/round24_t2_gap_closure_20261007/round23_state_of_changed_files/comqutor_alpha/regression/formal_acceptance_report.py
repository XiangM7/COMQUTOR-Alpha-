"""T2 (2026-10-07): the unified formal-acceptance ENTRY for runs that are already saved on disk (COMQUTOR Alpha next-round task sheet, section 4,
"第三，统一正式验收入口").

John: "正式验收显式读取指定规则文件和 taxonomy，不允许静默回退到旧版本。程序输出解析后的 effective_rules，所有验收表和摘要从同一结果生成。"

What this module does, and only this:

  * ``evaluate_saved_runs`` -- Type A re-evaluation (旧结果复评): reads each named run's OWN already-persisted artifacts, read-only, and runs
    :func:`comqutor_alpha.regression.acceptance_engine.run_formal_acceptance` on them with the rule files that were NAMED (taxonomy, v0.2 labels,
    v0.1 labels). The research output is never touched; there is no Provider call, no replay, no recompute of any kind.
  * ``render_markdown`` -- every table is rendered from the result DOCUMENT alone (it never calls the engine and never re-reads a run), so a table
    and the JSON it came from cannot disagree.
  * ``write_outputs`` -- writes into a directory that must not already hold files, so a dated verdict file is never overwritten (an earlier round
    once overwrote ``t2_six_ticker_acceptance_verdicts_2026-09-29.json`` with a script that hardcoded its output path).

The command line is ``scripts/run_formal_acceptance.py``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from comqutor_alpha.regression.acceptance_engine import (
    RULE_FAMILY_ALLOWED_MAIN_CONFLICTS,
    RULE_FAMILY_CONDITIONAL_ONLY,
    RULE_FAMILY_DO_NOT_FORCE,
    RULE_FAMILY_FORBIDDEN_DOMINANT_WITHOUT_STRONG_EVIDENCE,
    RULE_FAMILY_MUST_DETECT_IF_EVIDENCE_PRESENT,
    RULE_FAMILY_SHOULD_DETECT_IF_SUPPORTED,
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
from comqutor_alpha.regression.labels_v2 import load_j2_labels_v2, ticker_label_v2
from comqutor_alpha.regression.run_selection import _file_artifact_completeness

SCHEMA_VERSION = "comqutor.formal_acceptance_verdicts.v1"
EXECUTION_TYPE = "A_REEVALUATION"
VERDICTS_FILENAME = "formal_acceptance_verdicts.json"
TABLES_FILENAME = "formal_acceptance_tables.md"
RULES_FILENAME = "effective_rules.json"

# The six historical runs John's six-ticker verdicts are pinned to (NOT "the newest run of each ticker": new runs of the same ticker exist, and a
# newer PASS on one of them must never stand in for the review still open on the pinned run).
DEFAULT_SIX_TICKER_RUNS: dict[str, str] = {
    "NVDA": "ded99ecd-a186-4a90-859e-0f1a0efa43db",
    "QQQ": "0d890564-2479-4361-94e8-25c48af3b9a8",
    "SNDK": "e8e0f398-7b26-4462-8135-a1410ea5b335",
    "MSFT": "64568bfb-fe0c-453c-9872-831a8dc339a0",
    "TSM": "fc09821e-c7cf-40a7-bd76-c98172e16992",
    "AMD": "d5b60b8a-66b8-44c1-9f55-ee345e58c48d",
}

_RUN_ARTIFACTS = {
    "graph": "structure_graph.json",
    "conflicts": "conflicts.json",
    "alpha_matches": "alpha_matches.json",
}


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _display(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path(__file__).resolve().parents[2]).as_posix()
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------------------------------------------------------------------


def _labels_or_empty(label_v1_path, label_v2_path, taxonomy_path) -> tuple[dict[str, Any], dict[str, Any]]:
    """The label files as the engine will see them. A file that cannot be loaded yields an empty mapping here ON PURPOSE: the engine then resolves
    effective_rules() itself and reports the precise configuration error in every verdict, instead of this module inventing a fallback."""
    try:
        labels_v1 = load_j2_labels(label_v1_path)
    except Exception:
        labels_v1 = {}
    try:
        labels_v2 = load_j2_labels_v2(label_v2_path, taxonomy_path=taxonomy_path)
    except Exception:
        labels_v2 = {}
    return labels_v1, labels_v2


def evaluate_saved_run(
    *,
    ticker: str,
    run_id: str,
    runs_root: str | Path,
    taxonomy_path: str | Path | None = None,
    label_v2_path: str | Path | None = None,
    label_v1_path: str | Path | None = None,
) -> dict[str, Any]:
    """One ticker, one saved run. Read-only on ``runs_root``. The artifact completeness is computed for THIS run directory (not for whichever run of
    the ticker happens to be newest)."""
    run_dir = Path(runs_root) / run_id
    if not run_dir.is_dir():
        return {"ticker": ticker, "run_id": run_id, "status": "RUN_NOT_FOUND", "verdict": None}

    completeness, missing = _file_artifact_completeness(run_dir)
    graph_payload = _read_json(run_dir / _RUN_ARTIFACTS["graph"]) or {}
    conflict_payload = _read_json(run_dir / _RUN_ARTIFACTS["conflicts"]) or {}
    alpha_matches_payload = _read_json(run_dir / _RUN_ARTIFACTS["alpha_matches"])

    labels_v1, labels_v2 = _labels_or_empty(label_v1_path, label_v2_path, taxonomy_path)
    label_block_v1 = ticker_label(labels_v1, ticker) if labels_v1 else None
    label_block_v2 = ticker_label_v2(labels_v2, ticker) if labels_v2 else None

    detected = detected_alpha_sets(graph_payload)
    conflict_cmp = conflict_comparison(label_block_v1, conflict_payload)
    evaluate_ticker_result = {
        "ticker": ticker,
        "run_id": run_id,
        "run_selection_status": "selected",
        "offline_reprocess_status": "completed",
        "artifact_completeness": completeness,
        "artifact_missing_files": missing,
        "detected_alphas": detected["detected_alphas"],
        "dominant_alphas": detected["dominant_alphas"],
        **conflict_cmp,
        **six_ticker_qa_conflict_fields(conflict_cmp),
        **six_ticker_qa_alpha_fields(label_block_v1, detected),
        "stance_source": stance_source(alpha_matches_payload or {}),
        "evaluation_authority": "provisional",
        "execution_type": EXECUTION_TYPE,
    }
    verdict = run_formal_acceptance(
        ticker=ticker,
        ticker_v2_label=label_block_v2,
        label_block_v1=label_block_v1,
        evaluate_ticker_result=evaluate_ticker_result,
        conflict_payload=conflict_payload,
        graph_payload=graph_payload,
        alpha_matches_payload=alpha_matches_payload,
        taxonomy_path=taxonomy_path,
        label_v2_path=label_v2_path,
        label_v1_path=label_v1_path,
    )
    return {
        "ticker": ticker,
        "run_id": run_id,
        "status": "EVALUATED",
        "execution_type": EXECUTION_TYPE,
        "provider_calls": 0,
        "artifact_completeness": completeness,
        "artifact_missing_files": missing,
        "stance_source": evaluate_ticker_result["stance_source"],
        "admitted_conflicts": list(evaluate_ticker_result.get("admitted_conflicts") or ()),
        "candidate_conflicts": list(evaluate_ticker_result.get("candidate_conflicts") or ()),
        "main_conflict": evaluate_ticker_result.get("main_conflict"),
        "verdict": verdict,
    }


def _baseline_view(tickers: Mapping[str, Mapping[str, Any]], baseline_pairs: Mapping[str, list[str]]) -> dict[str, list[dict[str, Any]]]:
    """John's frozen pairs next to the rule file that carries them and what each saved run actually showed. Built from the evaluated entries only."""
    view: dict[str, list[dict[str, Any]]] = {}
    for ticker, pairs in baseline_pairs.items():
        entry = tickers.get(ticker) or {}
        verdict = entry.get("verdict") or {}
        ticker_rules = (verdict.get("effective_rules") or {}).get("ticker_rules") or {}
        admitted = set(entry.get("admitted_conflicts") or ())
        candidate = set(entry.get("candidate_conflicts") or ())
        rows = []
        for pair in pairs:
            declared_in = None
            for family, field in (
                (RULE_FAMILY_MUST_DETECT_IF_EVIDENCE_PRESENT, "required_conflicts"),
                (RULE_FAMILY_CONDITIONAL_ONLY, "conditional_conflicts"),
                (RULE_FAMILY_ALLOWED_MAIN_CONFLICTS, "allowed_conflicts"),
            ):
                if pair in (ticker_rules.get(family) or {}).get("pairs", ()):
                    declared_in = field
                    break
            rows.append(
                {
                    "pair": pair,
                    "declared_in": declared_in,
                    "observed": "admitted" if pair in admitted else "candidate" if pair in candidate else "not_reached",
                }
            )
        view[ticker] = rows
    return view


def evaluate_saved_runs(
    runs: Mapping[str, str],
    *,
    runs_root: str | Path,
    execution_id: str,
    taxonomy_path: str | Path | None = None,
    label_v2_path: str | Path | None = None,
    label_v1_path: str | Path | None = None,
    baseline_pairs: Mapping[str, list[str]] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """The result DOCUMENT: everything a table or summary may show, computed once."""
    try:
        rules: dict[str, Any] = effective_rules(taxonomy_path=taxonomy_path, label_v2_path=label_v2_path, label_v1_path=label_v1_path)
    except AcceptanceConfigError as exc:
        rules = {"config_error_reason_code": exc.reason_code, "config_error_detail": exc.detail}

    tickers = {
        ticker: evaluate_saved_run(
            ticker=ticker,
            run_id=run_id,
            runs_root=runs_root,
            taxonomy_path=taxonomy_path,
            label_v2_path=label_v2_path,
            label_v1_path=label_v1_path,
        )
        for ticker, run_id in runs.items()
    }
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "execution_id": execution_id,
        "execution_type": EXECUTION_TYPE,
        "generated_at": generated_at or _utc_now_iso(),
        "provider_calls": 0,
        "note": (
            "Type A re-evaluation: each run's own already-persisted artifacts are read unchanged and only the acceptance / verdict layer is "
            "executed. No Provider call, no replay, no recompute, no write into the run directories."
        ),
        "inputs": {
            "runs_root": _display(Path(runs_root)),
            "runs": dict(runs),
            "taxonomy_path": _display(Path(taxonomy_path)) if taxonomy_path else None,
            "label_v2_path": _display(Path(label_v2_path)) if label_v2_path else None,
            "label_v1_path": _display(Path(label_v1_path)) if label_v1_path else None,
        },
        "effective_rules": rules,
        "tickers": tickers,
        "status_by_ticker": {t: ((e.get("verdict") or {}).get("formal_status") or e.get("status")) for t, e in tickers.items()},
    }
    if baseline_pairs is not None:
        document["john_baseline_view"] = _baseline_view(tickers, baseline_pairs)
    return document


# ---------------------------------------------------------------------------------------------------------------------------------------
# rendering: from the document ALONE
# ---------------------------------------------------------------------------------------------------------------------------------------


def _cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _table(header: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return lines


def _family_rows(ticker: str, verdict: Mapping[str, Any]) -> list[list[Any]]:
    results = verdict.get("rule_family_results") or {}
    rows: list[list[Any]] = []
    for item in results.get(RULE_FAMILY_MUST_DETECT_IF_EVIDENCE_PRESENT) or ():
        rows.append([ticker, RULE_FAMILY_MUST_DETECT_IF_EVIDENCE_PRESENT, item.get("pair"), f"evidence_present={item.get('evidence_present')}; {item.get('admissibility_status')}", item.get("verdict")])
    for item in results.get(RULE_FAMILY_SHOULD_DETECT_IF_SUPPORTED) or ():
        rows.append([ticker, RULE_FAMILY_SHOULD_DETECT_IF_SUPPORTED, item.get("pair"), f"evidence_present={item.get('evidence_present')}; stance={item.get('stance_source')}; {item.get('admissibility_status')}", item.get("verdict")])
    for item in results.get(RULE_FAMILY_CONDITIONAL_ONLY) or ():
        rows.append([ticker, RULE_FAMILY_CONDITIONAL_ONLY, item.get("pair"), item.get("observed_status"), item.get("result")])
    for item in results.get(RULE_FAMILY_ALLOWED_MAIN_CONFLICTS) or ():
        rows.append([ticker, RULE_FAMILY_ALLOWED_MAIN_CONFLICTS, item.get("pair"), item.get("observed_status"), "observed"])
    dnf = results.get(RULE_FAMILY_DO_NOT_FORCE)
    if isinstance(dnf, Mapping):
        rows.append([ticker, RULE_FAMILY_DO_NOT_FORCE, "(every admitted conflict)", f"violations={len(dnf.get('violations') or ())}", dnf.get("verdict")])
    flags = results.get(RULE_FAMILY_FORBIDDEN_DOMINANT_WITHOUT_STRONG_EVIDENCE) or []
    guarded = ((verdict.get("effective_rules") or {}).get("ticker_rules") or {}).get(RULE_FAMILY_FORBIDDEN_DOMINANT_WITHOUT_STRONG_EVIDENCE, {}).get("guarded_alphas") or {}
    if flags:
        for flag in flags:
            rows.append([ticker, RULE_FAMILY_FORBIDDEN_DOMINANT_WITHOUT_STRONG_EVIDENCE, flag.get("alpha_id"), f"level={flag.get('qualified_level')}", flag.get("review_status")])
    elif RULE_FAMILY_FORBIDDEN_DOMINANT_WITHOUT_STRONG_EVIDENCE in results:
        rows.append([ticker, RULE_FAMILY_FORBIDDEN_DOMINANT_WITHOUT_STRONG_EVIDENCE, f"{len(guarded)} guarded Alphas", "none dominant", "not_triggered"])
    return rows


def render_markdown(document: Mapping[str, Any]) -> str:
    """The tables, built ONLY from ``document``. Nothing here calls the engine or reads a run directory."""
    rules = document.get("effective_rules") or {}
    out: list[str] = [
        f"# Formal acceptance verdicts — {document.get('execution_id')}",
        "",
        f"- Execution type: **{document.get('execution_type')}** (saved results re-evaluated; research output untouched) | Provider calls: **{document.get('provider_calls')}** | Generated: {document.get('generated_at')}",
        f"- Runs root: `{(document.get('inputs') or {}).get('runs_root')}`",
        "",
        "## 1. Rules resolved (effective_rules)",
        "",
    ]
    if "config_error_reason_code" in rules:
        out += [f"**CONFIG ERROR** `{rules['config_error_reason_code']}` — {rules.get('config_error_detail')}", ""]
    else:
        taxonomy, label_v2, label_v1 = rules.get("taxonomy") or {}, rules.get("label_v2") or {}, rules.get("label_v1") or {}
        out += _table(
            ["Rule file", "Path", "Version", "sha256"],
            [
                ["taxonomy", taxonomy.get("path"), f"{taxonomy.get('schema_version')} / content {taxonomy.get('content_version')}", taxonomy.get("sha256")],
                ["labels v0.2", label_v2.get("path"), label_v2.get("label_version"), label_v2.get("sha256")],
                ["labels v0.1 (dominance guard)", label_v1.get("path"), label_v1.get("label_version"), label_v1.get("sha256")],
            ],
        )
        out += [
            "",
            f"Authority of the v0.2 label file: status `{label_v2.get('status')}`, evaluation_mode `{label_v2.get('evaluation_mode')}`, "
            f"evaluation_authority `{label_v2.get('evaluation_authority')}`, formal_product_owner_approval `{label_v2.get('formal_product_owner_approval')}`, "
            f"approved_by `{label_v2.get('approved_by')}`. A verdict computed under a provisional file is a provisional verdict.",
            "",
            "### Six rule families — what each one reads and executes",
            "",
        ]
        out += _table(
            ["Rule family", "Config source", "Applies to", "Execution function", "Trigger", "Possible results"],
            [
                [
                    family,
                    definition.get("config_source"),
                    definition.get("applicable_target"),
                    definition.get("execution_function"),
                    definition.get("trigger_condition"),
                    ", ".join(definition.get("verdict_result") or ()),
                ]
                for family, definition in (rules.get("rule_families") or {}).items()
            ],
        )
        not_evaluated = rules.get("declared_but_not_evaluated") or {}
        declared = {key: value for key, value in not_evaluated.items() if value}
        if declared:
            out += ["", f"Declared in the rule file but evaluated by **no** rule family: `{json.dumps(declared)}`."]
        out.append("")

    tickers = document.get("tickers") or {}
    out += ["## 2. Verdict per ticker", ""]
    overview = []
    for ticker, entry in tickers.items():
        verdict = entry.get("verdict") or {}
        coverage = verdict.get("coverage") or {}
        status = verdict.get("formal_status") or entry.get("status")
        reason = verdict.get("config_error_reason_code") or verdict.get("semantic_input_reason_code") or ""
        overview.append(
            [
                ticker,
                (entry.get("run_id") or "")[:8],
                entry.get("artifact_completeness"),
                entry.get("stance_source"),
                f"{status} {reason}".strip(),
                ", ".join(entry.get("admitted_conflicts") or ()) or "—",
                ", ".join(verdict.get("undeclared_admitted_conflicts") or ()) or "—",
                "yes" if coverage.get("pass_is_vacuous") else "—",
            ]
        )
    out += _table(["Ticker", "Run", "Artifacts", "Stance source", "formal_status", "Admitted conflicts", "Undeclared admitted", "Vacuous PASS"], overview)

    out += ["", "## 3. Why each verdict is not a PASS", ""]
    reason_rows = []
    for ticker, entry in tickers.items():
        verdict = entry.get("verdict") or {}
        for item in verdict.get("failure_reasons") or ():
            reason_rows.append([ticker, "FAIL", item.get("family"), item.get("pair") or item.get("pairs") or "", item.get("detail")])
        for item in verdict.get("review_reasons") or ():
            reason_rows.append([ticker, "REVIEW", item.get("family"), item.get("pair") or item.get("alpha_id") or "", item.get("detail") or item.get("verdict")])
    out += _table(["Ticker", "Kind", "Rule family", "Pair / Alpha", "Detail"], reason_rows) if reason_rows else ["(no verdict carries a failure or review reason)"]

    out += ["", "## 4. Rule-by-rule judgments", ""]
    rows: list[list[Any]] = []
    for ticker, entry in tickers.items():
        rows += _family_rows(ticker, entry.get("verdict") or {})
    out += _table(["Ticker", "Rule family", "Pair / Alpha", "Observed", "Verdict"], rows) if rows else ["(none)"]

    baseline = document.get("john_baseline_view")
    if baseline:
        out += ["", "## 5. John's frozen allowed_main_conflicts × what the saved runs showed", ""]
        out += _table(
            ["Ticker", "Pair", "Carried by the rule file as", "Observed in the saved run"],
            [[ticker, row["pair"], row["declared_in"] or "NOT CARRIED", row["observed"]] for ticker, rows_ in baseline.items() for row in rows_],
        )

    out += ["", "## 6. Coverage — what each PASS actually exercised", ""]
    coverage_rows = []
    for ticker, entry in tickers.items():
        coverage = (entry.get("verdict") or {}).get("coverage")
        if coverage:
            coverage_rows.append(
                [
                    ticker,
                    coverage.get("declared_conflict_pairs"),
                    coverage.get("declared_pairs_with_evidence"),
                    coverage.get("admitted_conflicts_checked_by_do_not_force"),
                    f"{coverage.get('dominance_guards_triggered')}/{coverage.get('dominance_guards_declared')}",
                    coverage.get("reading") or "",
                ]
            )
    out += (
        _table(["Ticker", "Declared pairs", "With evidence on both sides", "Admitted (do_not_force)", "Dominance guards triggered/declared", "Reading"], coverage_rows)
        if coverage_rows
        else ["(no evaluated ticker)"]
    )
    out.append("")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------------------------------------------------------------------


def write_outputs(document: Mapping[str, Any], out_dir: str | Path) -> dict[str, Path]:
    """Writes the three files into ``out_dir``. Refuses a directory that already holds anything: a delivered verdict file is never overwritten."""
    out = Path(out_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"{out} already holds files; choose a new --out-dir (verdict files are never overwritten)")
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "verdicts": out / VERDICTS_FILENAME,
        "tables": out / TABLES_FILENAME,
        "effective_rules": out / RULES_FILENAME,
    }
    paths["verdicts"].write_text(json.dumps(document, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    paths["tables"].write_text(render_markdown(document), encoding="utf-8")
    paths["effective_rules"].write_text(json.dumps(document.get("effective_rules"), ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return paths


__all__ = [
    "DEFAULT_SIX_TICKER_RUNS",
    "EXECUTION_TYPE",
    "SCHEMA_VERSION",
    "evaluate_saved_run",
    "evaluate_saved_runs",
    "render_markdown",
    "write_outputs",
]
