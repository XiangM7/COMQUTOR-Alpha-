"""T2 (2026-10-07): the open-review ledger (comqutor_alpha.regression.open_review_ledger).

John: "NVDA 当前的 A304__A601 继续保留为待审核结果；QQQ 新 run 的 PASS 不能替代旧 run 尚未关闭的复核" and, in the sign-off, "NVDA、QQQ 尚未关闭的具体争议继续单独记录，
不能通过换一个成功 run 消除".

The real-data tests read the repository's saved NVDA / QQQ runs under outputs/runs (read-only, Type A; the same practice as
tests/test_v0_1_3_offline_replay_proof.py). The closure-record and rendering tests use a hand-made (synthetic) ledger.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from comqutor_alpha.regression import open_review_ledger as ledger_module

REPO = Path(__file__).resolve().parents[1]
RUNS_ROOT = REPO / "outputs" / "runs"
NVDA_PINNED = "ded99ecd-a186-4a90-859e-0f1a0efa43db"
NVDA_FRESH = "034a0a60-430e-41f8-8321-03a11389707a"
QQQ_PINNED = "0d890564-2479-4361-94e8-25c48af3b9a8"


@pytest.fixture(scope="module")
def ledger():
    return ledger_module.build_open_review_ledger(["NVDA", "QQQ"], runs_root=RUNS_ROOT, generated_at="2026-10-07T00:00:00Z")


def _items(ledger, ticker, run_prefix):
    return [i for i in ledger["items"] if i["ticker"] == ticker and i["run_id"].startswith(run_prefix)]


def test_johns_named_nvda_item_is_open_on_the_pinned_run(ledger):
    items = _items(ledger, "NVDA", NVDA_PINNED[:8])
    named = [i for i in items if i["subject"] == "A304__A601" and i["family"] == "undeclared_admitted_conflict"]
    assert len(named) == 1 and named[0]["status"] == "open" and named[0]["kind"] == "review"


def test_a_later_pass_closes_nothing_and_a_pass_that_exercised_no_rule_says_so(ledger):
    nvda = ledger["tickers"]["NVDA"]
    latest = nvda["latest_run"]
    assert latest["run_id"] == NVDA_FRESH and latest["formal_status"] == "pass"
    assert latest["pass_is_vacuous"] is True  # the Fresh run admitted nothing and no declared pair had evidence on both sides
    assert nvda["open_item_count"] > 0
    assert nvda["passes_after_the_first_open_item"], "there are PASS runs dated after the first open item"
    assert all(p["closes"] == 0 for p in nvda["passes_after_the_first_open_item"])
    assert ledger["closure_records"] == []  # no recorded review decision exists; the ledger does not pretend one does


def test_qqq_keeps_its_open_items_next_to_runs_that_came_back_pass(ledger):
    qqq = ledger["tickers"]["QQQ"]
    assert qqq["open_item_count"] > 0
    assert qqq["status_counts"].get("pass", 0) >= 1 and qqq["status_counts"].get("needs_review", 0) >= 1
    pinned = _items(ledger, "QQQ", QQQ_PINNED[:8])
    assert {i["subject"] for i in pinned if i["family"] == "undeclared_admitted_conflict"} == {"A501__A601"}


def test_every_run_of_the_ticker_is_listed_including_the_ones_that_could_not_be_evaluated(ledger):
    nvda_runs = ledger["tickers"]["NVDA"]["runs"]
    statuses = {r["formal_status"] for r in nvda_runs}
    assert {"pass", "needs_review", "not_evaluable", "alpha_semantic_unavailable"} <= statuses
    assert ledger["tickers"]["NVDA"]["runs_total"] == len(nvda_runs)


def test_only_a_recorded_review_decision_closes_an_item(ledger):
    target = next(i for i in ledger["items"] if i["ticker"] == "NVDA" and i["run_id"] == NVDA_PINNED and i["subject"] == "A304__A601")
    record = {
        "ticker": "NVDA",
        "run_id": NVDA_PINNED,
        "family": target["family"],
        "subject": "A304__A601",
        "decided_by": "a named reviewer",
        "decided_at": "2026-10-07",
        "decision": "accepted as a legal structure",
        "reference": "synthetic record used only by this test",
    }
    with_record = ledger_module.build_open_review_ledger(["NVDA"], runs_root=RUNS_ROOT, generated_at="t", closure_records=[record])
    closed = next(i for i in with_record["items"] if i["run_id"] == NVDA_PINNED and i["subject"] == "A304__A601")
    assert closed["status"] == "closed" and closed["closure_record"]["decided_by"] == "a named reviewer"
    still_open = [i for i in with_record["items"] if i["status"] == "open"]
    assert still_open and all(i["run_id"] != NVDA_PINNED or i["subject"] != "A304__A601" for i in still_open)


def test_the_table_is_rendered_from_the_ledger_alone_and_outputs_are_never_overwritten(tmp_path, ledger):
    markdown = ledger_module.render_markdown(ledger)
    assert "Open-review ledger" in markdown
    assert "NVDA 当前的 A304__A601 继续保留为待审核结果" in markdown
    assert "QQQ 新 run 的 PASS 不能替代旧 run 尚未关闭的复核" in markdown
    assert "Closure records: **0**" in markdown
    paths = ledger_module.write_outputs(ledger, tmp_path / "out")
    assert paths["table"].read_text(encoding="utf-8") == markdown
    with pytest.raises(FileExistsError):
        ledger_module.write_outputs(ledger, tmp_path / "out")
