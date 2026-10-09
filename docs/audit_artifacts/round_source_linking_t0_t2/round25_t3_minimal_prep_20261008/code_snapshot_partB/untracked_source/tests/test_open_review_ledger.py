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


def test_a_later_pass_closes_nothing(ledger):
    """QQQ has PASS runs dated after its first open item (no Gold contract rule belongs to it); none of them closes anything."""
    qqq = ledger["tickers"]["QQQ"]
    assert qqq["open_item_count"] > 0
    assert qqq["passes_after_the_first_open_item"], "there are PASS runs dated after the first open item"
    assert all(p["closes"] == 0 for p in qqq["passes_after_the_first_open_item"])
    assert ledger["closure_records"] == []  # no recorded review decision exists; the ledger does not pretend one does


def test_a_vacuous_pass_is_marked_and_nvdas_latest_run_is_no_longer_one(ledger):
    """Round 24: the latest saved NVDA run used to read as a vacuous PASS. It is not a PASS any more: its three Gold contract rules (two blocking
    Alpha rules and the blocking composite) cannot be evaluated for it -- the frozen trigger matrix is bound to another run -- and an unevaluated
    rule can never certify a PASS. Nothing is closed by that: the open items are the same."""
    nvda = ledger["tickers"]["NVDA"]
    latest = nvda["latest_run"]
    assert latest["run_id"] == NVDA_FRESH
    assert latest["formal_status"] == "needs_review" and latest["pass_is_vacuous"] is False
    assert latest["open_item_count"] == 0 and latest["unevaluated_rule_count"] == 3
    assert nvda["passes_after_the_first_open_item"] == []
    assert nvda["open_item_count"] == 7  # John's named A304__A601 on seven runs; unchanged by the contract rules
    vacuous_qqq = [r for r in ledger["tickers"]["QQQ"]["runs"] if r["pass_is_vacuous"]]
    assert vacuous_qqq and all(r["formal_status"] == "pass" for r in vacuous_qqq)


def test_qqq_keeps_its_open_items_next_to_runs_that_came_back_pass(ledger):
    qqq = ledger["tickers"]["QQQ"]
    assert qqq["open_item_count"] > 0
    assert qqq["status_counts"].get("pass", 0) >= 1 and qqq["status_counts"].get("needs_review", 0) >= 1
    pinned = _items(ledger, "QQQ", QQQ_PINNED[:8])
    assert {i["subject"] for i in pinned if i["family"] == "undeclared_admitted_conflict"} == {"A501__A601"}


def test_diagnostics_and_unevaluated_rules_are_listed_apart_from_the_open_items(ledger):
    """A diagnostic (engine-defined, no approval basis) and a rule that could not be evaluated are not disputes: they are never open items."""
    assert all(i["family"] != "should_detect_if_supported" for i in ledger["items"])
    assert all(i["kind"] in ("fail", "review") and i["family"] for i in ledger["items"])
    nvda_diagnostics = [d for d in ledger["diagnostic_findings"] if d["ticker"] == "NVDA"]
    assert nvda_diagnostics and all(d["decides_formal_status"] is False and d["authority"] == "implementation_only_unapproved" for d in nvda_diagnostics)
    unevaluated = [u for u in ledger["unevaluated_rules"] if u["ticker"] == "NVDA" and u["run_id"] == NVDA_FRESH]
    assert {u["subject"] for u in unevaluated} == {"NVDA-A101-AI-GROWTH", "NVDA-A304-VALUATION-RISK", "NVDA-GROWTH-VS-VALUATION-CONFLICT"}
    assert {u["reason_code"] for u in unevaluated} == {"RUN_NOT_BOUND_TO_FROZEN_TRIGGER_MATRIX"}
    assert all(u["blocking"] is True for u in unevaluated)
    assert not [i for i in ledger["items"] if i["run_id"] == NVDA_FRESH], "an unevaluated rule is not a review item"


def test_the_matrix_bound_nvda_run_evaluates_its_contract_rules_so_none_is_left_unevaluated(ledger):
    bound = next(r for r in ledger["tickers"]["NVDA"]["runs"] if r["run_id"].startswith("57d7b4c4"))
    assert bound["unevaluated_rule_count"] == 0  # the frozen trigger matrix IS bound to this run: the three rules reach a verdict


def test_every_run_of_the_ticker_is_listed_including_the_ones_that_could_not_be_evaluated(ledger):
    nvda_runs = ledger["tickers"]["NVDA"]["runs"]
    statuses = {r["formal_status"] for r in nvda_runs}
    assert {"needs_review", "not_evaluable", "alpha_semantic_unavailable"} <= statuses
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
