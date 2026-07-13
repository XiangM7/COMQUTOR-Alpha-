from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import pytest

from comqutor_alpha.storage.artifact_store import ArtifactStore, ArtifactStoreError
from comqutor_alpha.structure_engine.structure_schema import (
    AgentType,
    RawAnalystReport,
    RawAnalystReportBundle,
    RunStatus,
)
from comqutor_alpha.structure_engine.structured_output_adapter import (
    ExtractorError,
    StructuredOutputAdapter,
)

RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
FIXTURES = Path(__file__).parents[1] / "fixtures/analyst_reports"


def _bundle() -> RawAnalystReportBundle:
    reports = {}
    for agent in AgentType:
        reports[agent] = RawAnalystReport(
            run_id=RUN_ID,
            ticker="NVDA",
            analysis_date=date(2026, 1, 15),
            agent=agent,
            report_text=(FIXTURES / f"{agent.value}.txt").read_text(),
            captured_at=NOW,
            source_field=f"{agent.value}_report",
        )
    return RawAnalystReportBundle(
        run_id=RUN_ID,
        ticker="NVDA",
        analysis_date=date(2026, 1, 15),
        reports=reports,
    )


def _valid_payload(report: RawAnalystReport):
    evidence = report.report_text.split(". ")[0].rstrip(".") + "."
    return {
        "claims": [
            {
                "claim": f"{report.agent.value} evidence supports an Alpha factor.",
                "evidence": evidence,
                "entities": ["NVDA"],
                "factors": [report.agent.value],
                "direction": "positive",
                "confidence": 0.8,
                "source_type": "analyst",
                "source_refs": [],
            }
        ]
    }


class FakeExtractor:
    method = "fake_structured_extractor_v1"

    def __init__(self, behavior=None):
        self.behavior = behavior
        self.calls = []

    def extract(self, report):
        self.calls.append(report.agent)
        if self.behavior:
            return self.behavior(report, len(self.calls))
        return _valid_payload(report)


@pytest.mark.unit
def test_four_fixtures_create_schema_valid_claims() -> None:
    extractor = FakeExtractor()
    result = StructuredOutputAdapter(extractor).adapt_bundle(_bundle())
    assert result.status == RunStatus.COMPLETE
    assert len(result.batches) == 4
    assert all(len(batch.claims) == 1 and batch.failure is None for batch in result.batches)
    assert [batch.agent for batch in result.batches] == list(AgentType)
    assert result.model_validate_json(result.model_dump_json()) == result


@pytest.mark.unit
@pytest.mark.parametrize(
    "first_response",
    [
        "{not-json",
        {"claims": [{"claim": "bad", "evidence": "bad", "confidence": 9}]},
        TimeoutError("slow provider"),
    ],
)
def test_retryable_failures_retry_then_succeed(first_response) -> None:
    per_agent_attempts = {}

    def behavior(report, _call):
        attempt = per_agent_attempts.get(report.agent, 0) + 1
        per_agent_attempts[report.agent] = attempt
        if attempt == 1:
            if isinstance(first_response, Exception):
                raise first_response
            return first_response
        return json.dumps(_valid_payload(report))

    result = StructuredOutputAdapter(FakeExtractor(behavior), retry_budget=1).adapt_bundle(_bundle())
    assert result.status == RunStatus.COMPLETE
    assert all(value == 2 for value in per_agent_attempts.values())


@pytest.mark.unit
def test_partial_failure_continues_other_agents_and_is_degraded() -> None:
    def behavior(report, _call):
        if report.agent == AgentType.NEWS:
            raise ExtractorError("provider_unavailable", "offline", retryable=False)
        return _valid_payload(report)

    extractor = FakeExtractor(behavior)
    result = StructuredOutputAdapter(extractor, retry_budget=3).adapt_bundle(_bundle())
    assert result.status == RunStatus.DEGRADED
    assert len(extractor.calls) == 4
    news = next(batch for batch in result.batches if batch.agent == AgentType.NEWS)
    assert news.claims == []
    assert news.failure is not None
    assert news.failure.error_code == "provider_unavailable"
    assert news.failure.attempt_count == 1


@pytest.mark.unit
def test_all_failures_return_failed_without_fake_unknown_claims() -> None:
    def behavior(_report, _call):
        raise TimeoutError("timed out")

    result = StructuredOutputAdapter(FakeExtractor(behavior), retry_budget=1).adapt_bundle(
        _bundle()
    )
    assert result.status == RunStatus.FAILED
    assert all(batch.claims == [] for batch in result.batches)
    assert all(batch.failure and batch.failure.attempt_count == 2 for batch in result.batches)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        ({"claims": []}, "empty_claim_batch"),
        (
            {
                "claims": [
                    {
                        "claim": "identical text",
                        "evidence": "identical text",
                        "direction": "unknown",
                        "confidence": 0,
                        "source_type": "unknown",
                    }
                ]
            },
            "evidence_rejected",
        ),
        (
            {
                "claims": [
                    {
                        "claim": "a claim",
                        "evidence": "text invented outside the raw report",
                        "direction": "unknown",
                        "confidence": 0,
                        "source_type": "unknown",
                    }
                ]
            },
            "evidence_rejected",
        ),
    ],
)
def test_empty_or_unadmitted_evidence_is_explicit_failure(payload, expected_code) -> None:
    result = StructuredOutputAdapter(FakeExtractor(lambda _r, _n: payload)).adapt_report(
        _bundle().reports[AgentType.MARKET]
    )
    assert result.claims == []
    assert result.failure is not None
    assert result.failure.error_code == expected_code


@pytest.mark.unit
def test_structured_artifact_is_published_once(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "runs")
    store.write_initial_run(
        run_id=RUN_ID,
        metadata={"run_id": str(RUN_ID)},
        raw_reports=[],
        upstream_decision={"comparison_only": True},
    )
    result = StructuredOutputAdapter(FakeExtractor()).adapt_bundle(_bundle())
    artifact = store.write_derived_artifact(
        run_id=RUN_ID,
        filename="structured_agent_outputs.json",
        payload=result.model_dump(mode="json"),
    )
    assert json.loads(artifact.read_text())["status"] == "complete"
    with pytest.raises(ArtifactStoreError) as duplicate:
        store.write_derived_artifact(
            run_id=RUN_ID,
            filename="structured_agent_outputs.json",
            payload={},
        )
    assert duplicate.value.error_code == "duplicate_artifact"
