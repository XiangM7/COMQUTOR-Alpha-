"""Round 5 (2026-10-04), T2 closing gap: proves comqutor_alpha.regression.
acceptance_engine.run_formal_acceptance is actually invoked by the REAL
production completion path (routes_research.py's pipeline completion
flow), not only by test files and offline scripts under
docs/audit_artifacts/ -- see comqutor_alpha.api.formal_acceptance_artifact.

TestScenarioA exercises the REAL entrypoint end to end: run_research_request
(zero real Provider calls -- yf.Ticker is monkeypatched at the external
boundary exactly like tests/test_t1_financial_source_chain.py's own
established TestFinancialDataScenarioB_GateAndReviewIntegration pattern,
which this fixture deliberately mirrors since it is already proven to
reach a real "completed" run through the full _run_week3_graph_pipeline;
the LLM gateway is the deterministic echo gateway). Confirms
formal_acceptance.json is genuinely written to disk with
effective_rules/formal_status attached.

TestScenarioB separately proves write_formal_acceptance_artifact degrades
safely -- no crash, no fabricated requirement -- for a ticker with NO J2
Gold label at all (the overwhelming majority of real production usage is
an arbitrary ticker outside John's six Gold-labeled regression tickers:
NVDA/QQQ/SNDK/MSFT/TSM/AMD). This is checked directly against the
function (not through the full, fixture-fragile live pipeline) since the
behavior under test here is specifically the label lookup/None-handling
contract, already independently confirmed correct by direct code reading
of ticker_label/ticker_label_v2/conflict_comparison/dominance_guard_flags.

SYNTHETIC INPUTS (task sheet: "测试可以使用明确标注的合成 fixtures，但不能把它们计为真实市场验证样本"): the pipeline code under test is the real
production code, but the market / news / report text it is fed here is hand-written and the external data boundary is faked. These tests prove
mechanisms; they are NOT real market validation and are never counted as such.
"""

from __future__ import annotations

import json
from datetime import datetime

import tradingagents.dataflows.y_finance as y_finance
from comqutor_alpha.api.formal_acceptance_artifact import (
    FORMAL_ACCEPTANCE_ARTIFACT_FILENAME,
    write_formal_acceptance_artifact,
)
from comqutor_alpha.api.routes_research import run_research_request
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from scripts.deterministic_echo_llm import build_deterministic_echo_gateway
from tradingagents.dataflows.source_capture import source_capture_scope

TICKER = "NVDA"
ANALYSIS_DATE = "2026-08-10"
RETRIEVED_AT = datetime(2026, 8, 9, 12, 0, 0)


class _FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return RETRIEVED_AT


class _FakeTicker:
    def __init__(self, info):
        self.info = info


class TestScenarioA_RealPipelineProducesTheArtifact:
    def test_formal_acceptance_artifact_is_written_by_the_real_completion_path(self, tmp_path, monkeypatch):
        engine = build_engine("sqlite:///:memory:")
        apply_migrations(engine)
        repo = GraphPersistenceRepository(engine)

        monkeypatch.setattr(y_finance, "datetime", _FixedDatetime)
        monkeypatch.setattr(
            y_finance.yf, "Ticker", lambda symbol: _FakeTicker({"marketCap": 3_000_000_000_000, "trailingPE": 35.2})
        )
        with source_capture_scope() as sink:
            y_finance.get_fundamentals(TICKER)
        captured = list(sink)
        assert captured, "expected the real get_fundamentals call to capture a source"

        def runner(payload, *, output_root):
            from comqutor_alpha.adapters.tradingagents_output_writer import save_comqutor_run_outputs

            final_state = {
                "fundamentals_report": (
                    f"{TICKER}'s valuation outlook is strengthening, with the verified fundamentals "
                    "snapshot showing the trailing P/E multiple has risen alongside market cap."
                ),
            }
            return save_comqutor_run_outputs(
                final_state, payload["ticker"], selected_analysts=["fundamentals"],
                analysis_date=payload.get("analysis_date"), output_root=output_root,
                captured_sources=captured,
            )

        gateway = build_deterministic_echo_gateway("formal-acceptance-wiring-test", tmp_path)
        payload = {"ticker": TICKER, "analysis_date": ANALYSIS_DATE, "selected_analysts": ["fundamentals"]}
        response = run_research_request(
            payload, runner=runner, output_root=tmp_path, graph_repository=repo, week2_llm_gateway=gateway
        )
        assert response["status"] == "completed"
        run_id = response["run_id"]

        artifact_path = tmp_path / run_id / FORMAL_ACCEPTANCE_ARTIFACT_FILENAME
        assert artifact_path.exists(), "formal_acceptance.json must be written by the real completion path"
        artifact = json.loads(artifact_path.read_text())

        assert artifact["run_id"] == run_id
        assert artifact["ticker"] == TICKER
        assert artifact["label_v1_version"] is not None
        assert "effective_rules" in artifact
        assert "formal_status" in artifact
        assert artifact["formal_status"] is not None


class TestScenarioB_UnlabeledTickerDegradesSafely:
    def test_a_ticker_with_no_gold_label_is_a_visible_config_error_not_a_crash_and_not_a_pass(self, tmp_path):
        graph_payload = {
            "ticker": "ZZZZ_NO_GOLD_LABEL",
            "activation_versions": {"v2": {"alphas": []}},
            "activation": {"alphas": []},
            "dominant_alphas": [],
        }
        conflict_payload = {"conflicts": [], "arbitration": {"candidate_evaluations": []}, "main_conflict": None}
        alpha_matches_payload = {"matches": [{"claim_id": "c1", "match_status": "matched", "matched_alpha": None}]}

        artifact = write_formal_acceptance_artifact(
            run_id="unlabeled-ticker-run",
            ticker="ZZZZ_NO_GOLD_LABEL",
            output_root=tmp_path,
            graph_payload=graph_payload,
            conflict_payload=conflict_payload,
            alpha_matches_payload=alpha_matches_payload,
            artifact_completeness="pass",
        )

        assert artifact is not None, "a ticker with no Gold label must still produce a visible artifact, never None"
        assert artifact["ticker"] == "ZZZZ_NO_GOLD_LABEL"
        assert "effective_rules" in artifact
        # T2 (2026-10-07), John's task sheet: "规则缺失…应输出配置／执行错误，不能改成 NOT_APPLICABLE 后继续 PASS".
        # No requirement is fabricated for an undeclared ticker (so never a fail manufactured from nothing), but an empty
        # rule set must not be turned into a PASS either: the ticker has no rules, which is a configuration error.
        # (This test used to assert `!= "FAIL"`; the real statuses are lower-case, so that assertion could never fail.)
        assert artifact["formal_status"] == "config_error"
        assert artifact["config_error_reason_code"] == "ACCEPTANCE_TICKER_RULES_NOT_DECLARED"

        persisted = json.loads((tmp_path / "unlabeled-ticker-run" / FORMAL_ACCEPTANCE_ARTIFACT_FILENAME).read_text())
        assert persisted == artifact
