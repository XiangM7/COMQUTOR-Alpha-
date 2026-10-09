"""T2 verification, 2026-09-29 follow-up, item 3: a REAL, saved Exact
Semantic Replay frozen-input/result consistency comparison.

Honest finding recorded here first: none of the six official historical
ticker runs (NVDA/QQQ/SNDK/MSFT/TSM/AMD) are actually exact_replay_ready --
each one's own llm_semantic_manifest.json shows a real, nonzero
fallback_count (10/14/47/23/53/15 respectively) from its ORIGINAL live run,
so `complete`/`exact_replay_ready` are both False for every one of them.
This is not fabricated or worked around: this script does NOT touch any of
those six runs, does NOT retry/replay them live (forbidden this round --
zero paid Provider calls, no Fresh Run), and does NOT launder their
fallback records to force eligibility. Instead, it builds ONE separate,
genuinely complete, exact_replay_ready live-shaped run (same offline
double-based construction tests/replay/conftest.py::eligible_live_source
already uses, entirely provider-zero) under a clearly-labeled scratch
output root, runs the REAL run_exact_semantic_replay against it, and saves
its own real exact_replay_comparison.json here as a concrete, inspectable
artifact -- not merely "a test passed".
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tests" / "replay"))

import comqutor_alpha.api.routes_research as routes_research  # noqa: E402
from comqutor_alpha.replay.exact_semantic import run_exact_semantic_replay  # noqa: E402
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway  # noqa: E402
import conftest as replay_conftest  # noqa: E402

SOURCE_ROOT = REPO_ROOT / "docs/audit_artifacts/round_source_linking_t0_t2/_exact_replay_demo_source"
REPLAY_ROOT = REPO_ROOT / "docs/audit_artifacts/round_source_linking_t0_t2/_exact_replay_demo_output"
SOURCE_RUN_ID = "exact-replay-demonstration-source"


def _build_eligible_source(output_root: Path) -> None:
    import os

    os.environ["COMQUTOR_WEEK2_LLM_ENABLED"] = "true"
    routes_research.run_data_sanity_stage = lambda *a, **k: None
    model = replay_conftest.OfflineSemanticModel()
    gateway = Week2LLMGateway(
        model, run_id=SOURCE_RUN_ID, output_root=output_root, timeout_seconds=0.1,
        max_retries=0, max_calls=32, provider="offline-fixture-provider", model_name="offline-fixture-model",
    )
    response = routes_research.run_research_request(
        {
            "run_id": SOURCE_RUN_ID, "ticker": "NVDA", "analysis_date": "2026-06-30",
            "selected_analysts": ["news"],
            "offline_raw_agent_outputs": [
                {
                    "agent": "news_agent",
                    "raw_output": (
                        "AI demand drives GPU demand and revenue growth while "
                        "valuation risk creates downside."
                    ),
                }
            ],
        },
        output_root=output_root, week2_llm_gateway=gateway,
        graph_repository=replay_conftest.OfflineMemoryRepository(),
    )
    assert response["status"] == "completed", response
    manifest = json.loads((output_root / SOURCE_RUN_ID / "llm_semantic_manifest.json").read_text(encoding="utf-8"))
    assert manifest["complete"] is True, "expected the demonstration source run to be genuinely complete"
    assert manifest["exact_replay_ready"] is True, "expected the demonstration source run to be genuinely exact_replay_ready"


def main() -> None:
    for path in (SOURCE_ROOT, REPLAY_ROOT):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)

    _build_eligible_source(SOURCE_ROOT)
    source_dir = SOURCE_ROOT / SOURCE_RUN_ID

    result = run_exact_semantic_replay(source_dir, REPLAY_ROOT, replay_id="exact-replay-demonstration")
    print("status:", result.status)
    print("semantic_artifacts_byte_identical:", result.semantic_artifacts_byte_identical)
    print("source_run_unchanged:", result.source_run_unchanged)
    print("comparison.final_status:", result.comparison["final_status"])
    print("comparison.deterministic_downstream_equivalent:", result.comparison["deterministic_downstream_equivalent"])

    out_path = REPO_ROOT / "docs/audit_artifacts/round_source_linking_t0_t2/t2_exact_semantic_replay_comparison_demonstration.json"
    out_path.write_text(
        json.dumps(
            {
                "schema_version": "t2_exact_semantic_replay_comparison_demonstration.v1",
                "note": (
                    "None of the six official historical tickers are exact_replay_ready "
                    "(each has a real, nonzero fallback_count from its own original live run -- "
                    "see this script's own module docstring); this demonstration therefore uses a "
                    "separate, genuinely complete, provider-zero offline-double-based run, built with "
                    "the SAME construction tests/replay/conftest.py::eligible_live_source already uses. "
                    "The mechanism (run_exact_semantic_replay) is identical to what would run against "
                    "a real historical ticker once one becomes exact_replay_ready."
                ),
                "source_run_id": result.source_run_id,
                "replay_id": result.replay_id,
                "status": result.status,
                "semantic_source": result.semantic_source,
                "provider_zero": result.provider_zero,
                "provider_calls": result.provider_calls,
                "tradingagents_calls": result.tradingagents_calls,
                "market_data_calls": result.market_data_calls,
                "database_writes": result.database_writes,
                "semantic_artifacts_byte_identical": result.semantic_artifacts_byte_identical,
                "source_run_unchanged": result.source_run_unchanged,
                "binding_audit": result.binding_audit,
                "comparison": result.comparison,
            },
            indent=2, ensure_ascii=False, default=str,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out_path}")

    shutil.rmtree(SOURCE_ROOT)
    shutil.rmtree(REPLAY_ROOT)


if __name__ == "__main__":
    main()
