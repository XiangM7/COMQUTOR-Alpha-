"""T2 (2026-10-07): the open-review ledger (COMQUTOR Alpha next-round task sheet, section 4 "第四" and section 7 签收标准).

John, T2: "NVDA 当前的 A304__A601 继续保留为待审核结果；QQQ 新 run 的 PASS 不能替代旧 run 尚未关闭的复核。"
John, sign-off: "NVDA、QQQ 尚未关闭的具体争议继续单独记录，不能通过换一个成功 run 消除。"

A ticker has many saved runs. A later run that comes back PASS says nothing about an earlier run's review item - and a PASS that exercised no rule at all
(``coverage.pass_is_vacuous``) says even less. This module lists, per ticker, EVERY saved run with its formal verdict under the CURRENT rules and every
review / failure reason those verdicts carry, so the disputes are recorded on their own and cannot be made to disappear by running again.

An item is closed only by a recorded review decision (``closure_records``: who decided what, when, referring to which run and rule). No later run closes
an item. There are no such records today; the ledger says so instead of implying otherwise.

Read-only on the saved runs; Type A re-evaluation (the same engine call the six-ticker verdicts use); zero Provider calls.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from comqutor_alpha.regression.formal_acceptance_report import evaluate_saved_run
from comqutor_alpha.regression.run_selection import discover_candidate_runs

SCHEMA_VERSION = "comqutor.open_review_ledger.v1"
LEDGER_FILENAME = "open_review_ledger.json"
TABLE_FILENAME = "open_review_ledger.md"

# What John's own text names, quoted, so a reader sees which items are his and which the engine found.
NAMED_BY_JOHN: tuple[dict[str, Any], ...] = (
    {
        "ticker": "NVDA",
        "pair": "A304__A601",
        "quote": "NVDA 当前的 A304__A601 继续保留为待审核结果",
        "source": "COMQUTOR Alpha 下一轮开发任务单, T2 第四",
    },
    {
        "ticker": "QQQ",
        "pair": None,
        "quote": "QQQ 新 run 的 PASS 不能替代旧 run 尚未关闭的复核",
        "source": "COMQUTOR Alpha 下一轮开发任务单, T2 第四",
    },
)

POLICY = (
    "An item is closed only by a recorded review decision (closure_records). A later run's PASS never closes an earlier run's item, and a PASS whose "
    "coverage shows no rule was exercised (pass_is_vacuous) says nothing about the declared rules at all."
)


def _sort_key(candidate: Mapping[str, Any]) -> tuple[str, str, str]:
    return (str(candidate.get("analysis_date") or ""), str(candidate.get("created_at") or ""), str(candidate.get("run_id") or ""))


def _item_key(ticker: str, run_id: str, family: str, subject: str) -> tuple[str, str, str, str]:
    return (ticker, run_id, family, subject)


def _items_of(ticker: str, run_id: str, verdict: Mapping[str, Any]) -> list[dict[str, Any]]:
    items = []
    for kind, reasons in (("fail", verdict.get("failure_reasons") or ()), ("review", verdict.get("review_reasons") or ())):
        for reason in reasons:
            subject = reason.get("pair") or reason.get("alpha_id") or ",".join(reason.get("pairs") or ()) or ""
            items.append(
                {
                    "ticker": ticker,
                    "run_id": run_id,
                    "kind": kind,
                    "family": reason.get("family"),
                    "subject": subject,
                    "detail": reason.get("detail") or reason.get("verdict"),
                }
            )
    return items


def build_open_review_ledger(
    tickers: Sequence[str],
    *,
    runs_root: str | Path,
    generated_at: str,
    closure_records: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    closed = {
        _item_key(str(r.get("ticker")), str(r.get("run_id")), str(r.get("family")), str(r.get("subject"))): dict(r) for r in closure_records
    }
    per_ticker: dict[str, Any] = {}
    all_items: list[dict[str, Any]] = []
    for ticker in tickers:
        candidates = sorted(discover_candidate_runs(ticker, runs_root), key=_sort_key)
        runs = []
        for candidate in candidates:
            entry = evaluate_saved_run(ticker=ticker, run_id=candidate["run_id"], runs_root=runs_root)
            verdict = entry.get("verdict") or {}
            items = _items_of(ticker, candidate["run_id"], verdict)
            for item in items:
                record = closed.get(_item_key(ticker, item["run_id"], str(item["family"]), str(item["subject"])))
                item["status"] = "closed" if record else "open"
                item["closure_record"] = record
            all_items += items
            runs.append(
                {
                    "run_id": candidate["run_id"],
                    "analysis_date": candidate.get("analysis_date"),
                    "created_at": candidate.get("created_at"),
                    "formal_status": verdict.get("formal_status") or entry.get("status"),
                    "reason_code": verdict.get("config_error_reason_code") or verdict.get("semantic_input_reason_code"),
                    "pass_is_vacuous": (verdict.get("coverage") or {}).get("pass_is_vacuous"),
                    "admitted_conflicts": entry.get("admitted_conflicts"),
                    "open_item_count": sum(1 for i in items if i["status"] == "open"),
                }
            )
        evaluated = [r for r in runs if r["formal_status"] in ("pass", "needs_review", "fail")]
        first_open = next((r for r in evaluated if r["open_item_count"]), None)
        passes_after_open = [
            r
            for r in evaluated
            if r["formal_status"] == "pass" and first_open is not None and (str(r["analysis_date"]), str(r["created_at"])) > (str(first_open["analysis_date"]), str(first_open["created_at"]))
        ]
        latest = runs[-1] if runs else None
        per_ticker[ticker] = {
            "runs_total": len(runs),
            "runs": runs,
            "status_counts": {s: sum(1 for r in runs if r["formal_status"] == s) for s in sorted({r["formal_status"] for r in runs}, key=str)},
            "latest_run": latest,
            "open_item_count": sum(1 for i in all_items if i["ticker"] == ticker and i["status"] == "open"),
            "passes_after_the_first_open_item": [
                {"run_id": r["run_id"], "analysis_date": r["analysis_date"], "pass_is_vacuous": r["pass_is_vacuous"], "closes": 0} for r in passes_after_open
            ],
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "execution_type": "A_REEVALUATION",
        "provider_calls": 0,
        "policy": POLICY,
        "named_by_john": list(NAMED_BY_JOHN),
        "closure_records": [dict(r) for r in closure_records],
        "tickers": per_ticker,
        "items": all_items,
    }


def _cell(value: Any) -> str:
    return ("" if value is None else str(value)).replace("|", "\\|").replace("\n", " ")


def render_markdown(ledger: Mapping[str, Any]) -> str:
    """From the ledger alone."""
    out = [
        "# Open-review ledger — NVDA / QQQ disputes recorded on their own",
        "",
        f"- Generated: {ledger.get('generated_at')} | Execution type: **{ledger.get('execution_type')}** | Provider calls: **{ledger.get('provider_calls')}**",
        f"- Policy: {ledger.get('policy')}",
        f"- Closure records: **{len(ledger.get('closure_records') or ())}** (no recorded review decision closes any item below).",
        "",
        "## What John's text names",
        "",
    ]
    out += [f"- *{n['quote']}* — {n['source']}" + (f" (pair `{n['pair']}`)" if n.get("pair") else "") for n in ledger.get("named_by_john") or ()]
    for ticker, block in (ledger.get("tickers") or {}).items():
        latest = block.get("latest_run") or {}
        out += [
            "",
            f"## {ticker}",
            "",
            f"- Saved runs: **{block['runs_total']}** — status counts `{json.dumps(block['status_counts'])}`; open items: **{block['open_item_count']}**.",
            f"- Most recent saved run: `{(latest.get('run_id') or '')[:8]}` ({latest.get('analysis_date')}) → **{latest.get('formal_status')}**"
            + (" — a vacuous PASS (no declared rule was exercised)" if latest.get("pass_is_vacuous") else "")
            + ".",
            f"- PASS runs dated after the first open item: **{len(block['passes_after_the_first_open_item'])}**; items they close: **0**.",
            "",
            "| Run | Analysis date | formal_status | Vacuous PASS | Admitted conflicts | Open items |",
            "|---|---|---|---|---|---|",
        ]
        out += [
            "| " + " | ".join(_cell(c) for c in (r["run_id"][:8], r["analysis_date"], f"{r['formal_status']} {r['reason_code'] or ''}".strip(), "yes" if r["pass_is_vacuous"] else "", ", ".join(r["admitted_conflicts"] or ()) or "—", r["open_item_count"])) + " |"
            for r in block["runs"]
        ]
        items = [i for i in ledger.get("items") or () if i["ticker"] == ticker]
        out += ["", f"### {ticker} — items", ""]
        if items:
            out += ["| Run | Kind | Rule family | Pair / Alpha | Status | Detail |", "|---|---|---|---|---|---|"]
            out += ["| " + " | ".join(_cell(c) for c in (i["run_id"][:8], i["kind"], i["family"], i["subject"], i["status"], i["detail"])) + " |" for i in items]
        else:
            out.append("(none)")
    out.append("")
    return "\n".join(out) + "\n"


def write_outputs(ledger: Mapping[str, Any], out_dir: str | Path) -> dict[str, Path]:
    out = Path(out_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"{out} already holds files; choose a new --out-dir")
    out.mkdir(parents=True, exist_ok=True)
    paths = {"ledger": out / LEDGER_FILENAME, "table": out / TABLE_FILENAME}
    paths["ledger"].write_text(json.dumps(ledger, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    paths["table"].write_text(render_markdown(ledger), encoding="utf-8")
    return paths


__all__ = ["NAMED_BY_JOHN", "POLICY", "build_open_review_ledger", "render_markdown", "write_outputs"]
