"""T2 (2026-10-07): the unified formal-acceptance ENTRY (comqutor_alpha.regression.formal_acceptance_report + scripts/run_formal_acceptance.py).

John's task sheet: "正式验收显式读取指定规则文件和 taxonomy ... 程序输出解析后的 effective_rules，所有验收表和摘要从同一结果生成" and
"验收标准：交付 ... 六个历史标的的逐条规则判定".

SYNTHETIC FIXTURES: the run directories below are tiny hand-made stand-ins (a few JSON files) built to test the entry's behavior: read-only access, a
table that comes only from the result document, refusal to overwrite, error reporting. They are NOT market data and are never counted as real
validation. The real six-ticker verdicts are produced by running the script on the repository's saved runs.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from comqutor_alpha.api.artifact_export import REQUIRED_ARTIFACT_FILENAMES
from comqutor_alpha.regression import formal_acceptance_report as report

REPO = Path(__file__).resolve().parents[1]
RUN_ID = "synthetic-amd-run"


def _admitted_entry(alpha_a, alpha_b):
    return {
        "alpha_a": alpha_a,
        "alpha_b": alpha_b,
        "outcome": "admitted",
        "admissibility": {
            "status": "admitted",
            "reason_codes": [],
            "bull_supporting_evidence_count": 2,
            "bear_supporting_evidence_count": 2,
            "bull_score": 80.0,
            "bear_score": 80.0,
        },
    }


def _make_run(runs_root: Path, run_id: str = RUN_ID, *, complete: bool = True) -> Path:
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True)
    names = REQUIRED_ARTIFACT_FILENAMES if complete else REQUIRED_ARTIFACT_FILENAMES[:3]
    for name in names:
        (run_dir / name).write_text("{}", encoding="utf-8")
    (run_dir / "alpha_matches.json").write_text(
        json.dumps({"matches": [{"claim_id": "c1", "match_status": "matched", "matched_alpha": "A301"}]}), encoding="utf-8"
    )
    (run_dir / "structure_graph.json").write_text(
        json.dumps({"activation_versions": {"v2": {"alphas": []}}, "activation": {"alphas": []}, "dominant_alphas": []}), encoding="utf-8"
    )
    (run_dir / "conflicts.json").write_text(
        json.dumps(
            {
                "conflicts": [{"conflict_id": "A301__A304"}],
                "arbitration": {"candidate_evaluations": [_admitted_entry("A301", "A304")]},
                "main_conflict": {"conflict_id": "A301__A304"},
            }
        ),
        encoding="utf-8",
    )
    return run_dir


def _tree_hash(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


def _evaluate(tmp_path: Path, **kwargs):
    runs_root = tmp_path / "runs"
    _make_run(runs_root)
    return runs_root, report.evaluate_saved_runs({"AMD": RUN_ID}, runs_root=runs_root, execution_id="test-exec", **kwargs)


def _load_cli():
    spec = importlib.util.spec_from_file_location("run_formal_acceptance_cli", REPO / "scripts" / "run_formal_acceptance.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_a_saved_run_is_evaluated_read_only_and_every_table_comes_from_the_document_alone(tmp_path, monkeypatch):
    runs_root = tmp_path / "runs"
    _make_run(runs_root)
    before = _tree_hash(runs_root)
    document = report.evaluate_saved_runs(
        {"AMD": RUN_ID}, runs_root=runs_root, execution_id="test-exec", baseline_pairs={"AMD": ["A301__A304", "A999__A998"]}
    )
    assert _tree_hash(runs_root) == before, "the saved run directory must be byte-identical afterwards"
    assert document["provider_calls"] == 0 and document["execution_type"] == "A_REEVALUATION"
    entry = document["tickers"]["AMD"]
    assert entry["status"] == "EVALUATED" and entry["artifact_completeness"] == "pass"
    assert entry["verdict"]["formal_status"] in ("pass", "needs_review")

    def must_not_be_called(*_a, **_k):
        raise AssertionError("rendering must not call the engine or read a run")

    for name in ("run_formal_acceptance", "effective_rules", "_read_json", "evaluate_saved_run"):
        monkeypatch.setattr(report, name, must_not_be_called)
    markdown = report.render_markdown(document)
    assert "Formal acceptance verdicts — test-exec" in markdown
    assert "## 1. Rules resolved (effective_rules)" in markdown
    assert "## 4. Rule-by-rule judgments" in markdown
    assert "A301__A304" in markdown
    assert "Provider calls: **0**" in markdown
    # the six rule families are all described in the rules section
    for family in ("must_detect_if_evidence_present", "should_detect_if_supported", "conditional_only", "do_not_force", "allowed_main_conflicts", "forbidden_dominant_without_strong_evidence"):
        assert family in markdown


def test_john_baseline_view_says_which_rule_category_carries_each_pair_and_what_the_run_showed(tmp_path):
    _runs_root, document = _evaluate(tmp_path, baseline_pairs={"AMD": ["A301__A304", "A101__A304", "A999__A998"]})
    rows = {row["pair"]: row for row in document["john_baseline_view"]["AMD"]}
    assert rows["A301__A304"] == {"pair": "A301__A304", "declared_in": "allowed_conflicts", "observed": "admitted"}
    assert rows["A101__A304"]["declared_in"] == "conditional_conflicts"
    assert rows["A101__A304"]["observed"] == "not_reached"
    assert rows["A999__A998"]["declared_in"] is None  # a baseline pair no rule category carries is visible, not skipped
    assert "NOT CARRIED" in report.render_markdown(document)


def test_a_run_that_does_not_exist_is_reported_not_silently_skipped(tmp_path):
    document = report.evaluate_saved_runs({"AMD": "no-such-run"}, runs_root=tmp_path / "runs", execution_id="test-exec")
    assert document["tickers"]["AMD"]["status"] == "RUN_NOT_FOUND"
    assert document["status_by_ticker"] == {"AMD": "RUN_NOT_FOUND"}
    assert "RUN_NOT_FOUND" in report.render_markdown(document)


def test_an_unusable_rule_file_is_reported_in_the_rules_section_and_in_every_verdict(tmp_path):
    _runs_root, document = _evaluate(tmp_path, label_v2_path=tmp_path / "missing_labels.yaml")
    assert document["effective_rules"]["config_error_reason_code"] == "ACCEPTANCE_LABEL_V2_INVALID"
    assert document["tickers"]["AMD"]["verdict"]["formal_status"] == "config_error"
    assert "CONFIG ERROR" in report.render_markdown(document)


def test_completeness_is_judged_for_the_pinned_run_and_not_for_a_newer_run_of_the_same_ticker(tmp_path):
    runs_root = tmp_path / "runs"
    _make_run(runs_root, "pinned-complete-run", complete=True)
    _make_run(runs_root, "zzz-newer-incomplete-run", complete=False)
    document = report.evaluate_saved_runs({"AMD": "pinned-complete-run"}, runs_root=runs_root, execution_id="t")
    entry = document["tickers"]["AMD"]
    assert entry["artifact_completeness"] == "pass" and entry["artifact_missing_files"] == []
    assert entry["verdict"]["formal_status"] != "not_evaluable"
    other = report.evaluate_saved_runs({"AMD": "zzz-newer-incomplete-run"}, runs_root=runs_root, execution_id="t")
    assert other["tickers"]["AMD"]["verdict"]["formal_status"] == "not_evaluable"  # an incomplete run is reported as such, never as a pass


def test_every_formal_status_is_explained_by_the_reasons_listed_in_the_tables(tmp_path):
    _runs_root, document = _evaluate(tmp_path)
    verdict = document["tickers"]["AMD"]["verdict"]
    expected = "fail" if verdict["failure_reasons"] else "needs_review" if verdict["review_reasons"] else "pass"
    assert verdict["formal_status"] == expected


def test_output_files_are_written_from_one_document_and_a_second_write_into_the_same_directory_is_refused(tmp_path):
    _runs_root, document = _evaluate(tmp_path)
    out = tmp_path / "out"
    paths = report.write_outputs(document, out)
    assert json.loads(paths["verdicts"].read_text(encoding="utf-8")) == json.loads(json.dumps(document, default=str))
    assert paths["tables"].read_text(encoding="utf-8") == report.render_markdown(document)
    assert json.loads(paths["effective_rules"].read_text(encoding="utf-8")) == document["effective_rules"]
    before = _tree_hash(out)
    with pytest.raises(FileExistsError):
        report.write_outputs(document, out)
    assert _tree_hash(out) == before


def test_the_command_line_writes_three_files_and_never_overwrites(tmp_path, capsys):
    runs_root = tmp_path / "runs"
    _make_run(runs_root)
    cli = _load_cli()
    out = tmp_path / "cli_out"
    args = ["--out-dir", str(out), "--runs-root", str(runs_root), "--run", f"amd={RUN_ID}", "--baseline", "none", "--execution-id", "cli-test"]
    assert cli.main(args) == 0
    assert {p.name for p in out.iterdir()} == {report.VERDICTS_FILENAME, report.TABLES_FILENAME, report.RULES_FILENAME}
    before = _tree_hash(out)
    assert cli.main(args) == 2
    assert _tree_hash(out) == before
    assert "refusing" in capsys.readouterr().err


def test_the_command_line_exits_3_when_a_run_cannot_be_evaluated(tmp_path):
    cli = _load_cli()
    args = ["--out-dir", str(tmp_path / "o"), "--runs-root", str(tmp_path / "runs"), "--run", "AMD=nope", "--baseline", "none"]
    assert cli.main(args) == 3
