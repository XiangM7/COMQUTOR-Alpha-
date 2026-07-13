"""Fail-soft conversion from analyst reports to evidence-bearing Claims."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Protocol
from uuid import UUID, uuid5

from pydantic import Field, ValidationError

from comqutor_alpha.structure_engine.evidence_policy import (
    EvidencePolicy,
    EvidencePolicyError,
)
from comqutor_alpha.structure_engine.structure_schema import (
    AdapterFailure,
    AdapterRunResult,
    AgentType,
    Claim,
    ClaimBatch,
    Direction,
    DomainModel,
    NonEmptyStr,
    RawAnalystReport,
    RawAnalystReportBundle,
    RunStatus,
    SourceType,
    UnitFloat,
)

CLAIM_ID_NAMESPACE = UUID("7f84ace7-c7f0-4b87-af91-250ee20a31a7")


class ExtractedClaim(DomainModel):
    claim: NonEmptyStr
    evidence: NonEmptyStr
    entities: list[NonEmptyStr] = Field(default_factory=list)
    factors: list[NonEmptyStr] = Field(default_factory=list)
    direction: Direction
    confidence: UnitFloat
    source_type: SourceType
    source_refs: list[NonEmptyStr] = Field(default_factory=list)


class ExtractedClaimBatch(DomainModel):
    claims: list[ExtractedClaim]


class StructuredClaimExtractor(Protocol):
    method: str

    def extract(self, report: RawAnalystReport) -> Any: ...


class ExtractorError(RuntimeError):
    def __init__(self, error_code: str, message: str, *, retryable: bool):
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable


class StructuredOutputAdapter:
    def __init__(
        self,
        extractor: StructuredClaimExtractor,
        *,
        retry_budget: int = 1,
        evidence_policy: EvidencePolicy | None = None,
    ):
        if retry_budget < 0:
            raise ValueError("retry_budget must be non-negative")
        self.extractor = extractor
        self.retry_budget = retry_budget
        self.evidence_policy = evidence_policy or EvidencePolicy()

    @staticmethod
    def _raw_reference(agent: AgentType) -> str:
        return f"raw_agent_outputs.json#{agent.value}"

    @staticmethod
    def _parse_payload(payload: Any) -> ExtractedClaimBatch:
        if isinstance(payload, ExtractedClaimBatch):
            return payload
        if isinstance(payload, str):
            return ExtractedClaimBatch.model_validate_json(payload)
        if isinstance(payload, Mapping):
            return ExtractedClaimBatch.model_validate(payload)
        if hasattr(payload, "model_dump"):
            return ExtractedClaimBatch.model_validate(payload.model_dump())
        raise TypeError(f"unsupported extractor payload: {type(payload).__name__}")

    @staticmethod
    def _classified_error(exc: Exception) -> ExtractorError:
        if isinstance(exc, ExtractorError):
            return exc
        if isinstance(exc, TimeoutError):
            return ExtractorError("timeout", str(exc) or "extractor timed out", retryable=True)
        if isinstance(exc, (ValidationError, json.JSONDecodeError, TypeError)):
            return ExtractorError(
                "invalid_structured_output", str(exc), retryable=True
            )
        return ExtractorError(
            "extractor_failure", f"{type(exc).__name__}: {exc}", retryable=False
        )

    def _failure(
        self,
        report: RawAnalystReport,
        *,
        error: ExtractorError,
        attempts: int,
    ) -> ClaimBatch:
        return ClaimBatch(
            run_id=report.run_id,
            ticker=report.ticker,
            agent=report.agent,
            claims=[],
            failure=AdapterFailure(
                agent=report.agent,
                error_code=error.error_code,
                message=str(error),
                attempt_count=attempts,
                retryable=error.retryable,
                raw_artifact_reference=self._raw_reference(report.agent),
            ),
        )

    def adapt_report(self, report: RawAnalystReport) -> ClaimBatch:
        attempts = 0
        extracted: ExtractedClaimBatch | None = None
        last_error: ExtractorError | None = None
        while attempts <= self.retry_budget:
            attempts += 1
            try:
                extracted = self._parse_payload(self.extractor.extract(report))
                break
            except Exception as exc:  # extractor boundary is intentionally fail-soft
                last_error = self._classified_error(exc)
                if not last_error.retryable or attempts > self.retry_budget:
                    return self._failure(report, error=last_error, attempts=attempts)

        if extracted is None:
            assert last_error is not None
            return self._failure(report, error=last_error, attempts=attempts)
        if not extracted.claims:
            return self._failure(
                report,
                error=ExtractorError(
                    "empty_claim_batch", "extractor returned no claims", retryable=False
                ),
                attempts=attempts,
            )

        accepted: list[Claim] = []
        rejections: list[str] = []
        for index, item in enumerate(extracted.claims):
            try:
                self.evidence_policy.validate(
                    claim=item.claim,
                    evidence=item.evidence,
                    report_text=report.report_text,
                )
            except EvidencePolicyError as exc:
                rejections.append(f"claim[{index}] {exc.error_code}: {exc}")
                continue
            identity = "|".join(
                (
                    str(report.run_id),
                    report.agent.value,
                    str(index),
                    item.claim.strip(),
                    item.evidence.strip(),
                )
            )
            accepted.append(
                Claim(
                    claim_id=uuid5(CLAIM_ID_NAMESPACE, identity),
                    run_id=report.run_id,
                    ticker=report.ticker,
                    agent=report.agent,
                    claim=item.claim,
                    evidence=item.evidence,
                    entities=item.entities,
                    factors=item.factors,
                    direction=item.direction,
                    confidence=item.confidence,
                    source_type=item.source_type,
                    source_refs=item.source_refs or [self._raw_reference(report.agent)],
                    extraction_method=self.extractor.method,
                )
            )

        failure = None
        if rejections:
            failure = AdapterFailure(
                agent=report.agent,
                error_code="evidence_rejected",
                message="; ".join(rejections),
                attempt_count=attempts,
                retryable=False,
                raw_artifact_reference=self._raw_reference(report.agent),
            )
        if not accepted:
            error = ExtractorError(
                "evidence_rejected",
                "; ".join(rejections) or "no evidence-admissible claims",
                retryable=False,
            )
            return self._failure(report, error=error, attempts=attempts)
        return ClaimBatch(
            run_id=report.run_id,
            ticker=report.ticker,
            agent=report.agent,
            claims=accepted,
            failure=failure,
        )

    def adapt_bundle(self, bundle: RawAnalystReportBundle) -> AdapterRunResult:
        batches: list[ClaimBatch] = []
        for agent in AgentType:
            report = bundle.reports.get(agent)
            if report is None:
                batches.append(
                    ClaimBatch(
                        run_id=bundle.run_id,
                        ticker=bundle.ticker,
                        agent=agent,
                        claims=[],
                        failure=AdapterFailure(
                            agent=agent,
                            error_code="missing_report",
                            message=f"{agent.value} report was explicitly missing",
                            attempt_count=1,
                            retryable=False,
                            raw_artifact_reference=self._raw_reference(agent),
                        ),
                    )
                )
                continue
            batches.append(self.adapt_report(report))
        successes = sum(bool(batch.claims) for batch in batches)
        failures = sum(batch.failure is not None for batch in batches)
        status = (
            RunStatus.FAILED
            if successes == 0
            else RunStatus.DEGRADED
            if failures
            else RunStatus.COMPLETE
        )
        return AdapterRunResult(
            run_id=bundle.run_id,
            ticker=bundle.ticker,
            status=status,
            batches=batches,
        )
