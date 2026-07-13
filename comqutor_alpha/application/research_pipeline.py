"""Single application entry point for a complete COMQUTOR research run."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Protocol
from uuid import UUID, uuid4

from comqutor_alpha.alpha_library.alpha_loader import AlphaTaxonomy
from comqutor_alpha.config import ComqutorConfig, normalize_analysis_date, normalize_ticker
from comqutor_alpha.integration.state_capture import capture_report_bundle
from comqutor_alpha.integration.tradingagents_runner import TradingAgentsRunner
from comqutor_alpha.storage.artifact_store import ArtifactStore
from comqutor_alpha.structure_engine.activation_scorer import ActivationScorer
from comqutor_alpha.structure_engine.alpha_mapper import AlphaMapper
from comqutor_alpha.structure_engine.conflict_detector import ConflictDetector
from comqutor_alpha.structure_engine.graph_builder import GraphBuilder
from comqutor_alpha.structure_engine.structure_extractor import StructureExtractor
from comqutor_alpha.structure_engine.structure_schema import (
    ActivationStatus,
    AdapterRunResult,
    Claim,
    ResearchError,
    ResearchResult,
    RunStatus,
)
from comqutor_alpha.structure_engine.structured_output_adapter import StructuredOutputAdapter


class ResearchPersistencePort(Protocol):
    def save_result(self, result: ResearchResult) -> None: ...


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, check=False, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


class ResearchPipeline:
    def __init__(
        self,
        *,
        runner: TradingAgentsRunner,
        adapter: StructuredOutputAdapter,
        mapper: AlphaMapper,
        extractor: StructureExtractor,
        graph_builder: GraphBuilder,
        activation_scorer: ActivationScorer,
        conflict_detector: ConflictDetector,
        taxonomy: AlphaTaxonomy,
        artifact_store: ArtifactStore,
        config: ComqutorConfig,
        persistence: ResearchPersistencePort | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self.runner = runner
        self.adapter = adapter
        self.mapper = mapper
        self.extractor = extractor
        self.graph_builder = graph_builder
        self.activation_scorer = activation_scorer
        self.conflict_detector = conflict_detector
        self.taxonomy = taxonomy
        self.artifact_store = artifact_store
        self.config = config
        self.persistence = persistence
        self.clock = clock or (lambda: datetime.now(UTC))

    def _metadata(
        self,
        *,
        run_id: UUID,
        ticker: str,
        analysis_date: date,
        asset_type: str,
        created_at: datetime,
        status: str,
    ) -> dict[str, object]:
        return {
            "run_id": str(run_id),
            "ticker": ticker,
            "analysis_date": analysis_date.isoformat(),
            "asset_type": asset_type,
            "created_at": created_at.isoformat(),
            "upstream_commit": _git_commit(),
            "config_fingerprint": self.config.fingerprint(),
            "provider": self.config.llm_provider,
            "models": {
                "quick": self.config.quick_model,
                "deep": self.config.deep_model,
                "adapter": self.config.adapter_model,
            },
            "status": status,
        }

    def _persist_result(self, result: ResearchResult) -> None:
        self.artifact_store.write_derived_artifact(
            run_id=result.run_id,
            filename="research_result.json",
            payload=result.model_dump(mode="json"),
        )
        if self.persistence is not None:
            self.persistence.save_result(result)

    @staticmethod
    def _summary(dominant, main_conflict) -> str:
        if not dominant:
            return "Insufficient admitted evidence to identify a dominant Alpha Structure."
        names = ", ".join(f"{item.alpha_id}" for item in dominant)
        if main_conflict is None:
            return f"Research evidence identifies {names} as the leading Alpha Structures."
        return (
            f"Research evidence identifies {names}; the main structural conflict is "
            f"{main_conflict.bull_structure} versus {main_conflict.bear_structure}."
        )

    def _terminal_failure(
        self,
        *,
        run_id: UUID,
        ticker: str,
        analysis_date: date,
        stage: str,
        exc: Exception,
    ) -> ResearchResult:
        result = ResearchResult(
            run_id=run_id,
            ticker=ticker,
            analysis_date=analysis_date,
            status=RunStatus.FAILED,
            summary="Insufficient admitted evidence to complete structural research.",
            evidence_coverage=0.0,
            degraded_reasons=[f"{stage}_failed"],
            errors=[
                ResearchError(
                    error_code=f"{stage}_failed",
                    message=f"{type(exc).__name__}: {exc}",
                    stage=stage,
                )
            ],
        )
        self._persist_result(result)
        return result

    def run(
        self,
        *,
        ticker: str,
        analysis_date: str | date,
        asset_type: str = "stock",
        run_id: UUID | None = None,
    ) -> ResearchResult:
        normalized_ticker = normalize_ticker(ticker)
        normalized_date = normalize_analysis_date(analysis_date)
        current_run_id = run_id or uuid4()
        created_at = self.clock()
        if created_at.tzinfo is None:
            raise ValueError("pipeline clock must return a timezone-aware datetime")

        try:
            upstream = self.runner.run(normalized_ticker, normalized_date, asset_type)
        except Exception as exc:
            self.artifact_store.write_initial_run(
                run_id=current_run_id,
                metadata=self._metadata(
                    run_id=current_run_id,
                    ticker=normalized_ticker,
                    analysis_date=normalized_date,
                    asset_type=asset_type,
                    created_at=created_at,
                    status="upstream_failed",
                ),
                raw_reports=[],
                upstream_decision={"comparison_only": True, "available": False},
            )
            return self._terminal_failure(
                run_id=current_run_id,
                ticker=normalized_ticker,
                analysis_date=normalized_date,
                stage="upstream",
                exc=exc,
            )

        bundle, capture_errors = capture_report_bundle(
            upstream.final_state,
            run_id=current_run_id,
            ticker=normalized_ticker,
            analysis_date=normalized_date,
            captured_at=created_at,
        )
        self.artifact_store.write_initial_run(
            run_id=current_run_id,
            metadata=self._metadata(
                run_id=current_run_id,
                ticker=normalized_ticker,
                analysis_date=normalized_date,
                asset_type=asset_type,
                created_at=created_at,
                status="captured",
            ),
            raw_reports=[report.model_dump(mode="json") for report in bundle.reports.values()],
            upstream_decision={
                "comparison_only": True,
                "processed_decision": upstream.processed_decision,
                "final_trade_decision": upstream.final_state.get("final_trade_decision"),
            },
        )

        try:
            adapter_result: AdapterRunResult = self.adapter.adapt_bundle(bundle)
            self.artifact_store.write_derived_artifact(
                run_id=current_run_id,
                filename="structured_agent_outputs.json",
                payload=adapter_result.model_dump(mode="json"),
            )
            claims: list[Claim] = [
                claim for batch in adapter_result.batches for claim in batch.claims
            ]
            matches = self.mapper.map_claims(claims)
            self.artifact_store.write_derived_artifact(
                run_id=current_run_id,
                filename="alpha_matches.json",
                payload=[match.model_dump(mode="json") for match in matches],
            )
            fragments = self.extractor.extract_claims(claims, matches)
            self.artifact_store.write_derived_artifact(
                run_id=current_run_id,
                filename="structure_edges.json",
                payload=[fragment.model_dump(mode="json") for fragment in fragments],
            )
            built = self.graph_builder.build(
                run_id=current_run_id,
                ticker=normalized_ticker,
                fragments=fragments,
            )
            self.artifact_store.write_derived_artifact(
                run_id=current_run_id,
                filename="structure_graph.json",
                payload=built.document.model_dump(mode="json"),
            )
            claims_by_id = {claim.claim_id: claim for claim in claims}
            activations = self.activation_scorer.score(
                taxonomy=self.taxonomy,
                matches=matches,
                claims=claims_by_id,
                graph=built.document,
                analysis_date=normalized_date,
                as_of=created_at.date(),
            )
            self.artifact_store.write_derived_artifact(
                run_id=current_run_id,
                filename="alpha_activations.json",
                payload=[activation.model_dump(mode="json") for activation in activations],
            )
            conflicts = self.conflict_detector.detect(
                taxonomy=self.taxonomy,
                activations=activations,
                matches=matches,
                claims=claims_by_id,
            )
            self.artifact_store.write_derived_artifact(
                run_id=current_run_id,
                filename="alpha_conflicts.json",
                payload=[conflict.model_dump(mode="json") for conflict in conflicts],
            )
        except Exception as exc:
            return self._terminal_failure(
                run_id=current_run_id,
                ticker=normalized_ticker,
                analysis_date=normalized_date,
                stage="structure_pipeline",
                exc=exc,
            )

        extraction_failures = [fragment.failure for fragment in fragments if fragment.failure]
        reasons = [f"capture:{error.error_code}:{error.field}" for error in capture_errors]
        reasons.extend(
            f"adapter:{batch.agent.value}:{batch.failure.error_code}"
            for batch in adapter_result.batches
            if batch.failure is not None
        )
        reasons.extend(
            f"extractor:{failure.claim_id}:{failure.error_code}"
            for failure in extraction_failures
        )
        if claims and not matches:
            reasons.append("no_alpha_matches")
        successful_claims = len(claims)
        evidence_coverage = (
            sum(bool(claim.evidence) for claim in claims) / successful_claims
            if successful_claims
            else 0.0
        )
        dominant = [
            activation
            for activation in activations
            if activation.status in {ActivationStatus.DOMINANT, ActivationStatus.REGIME_LEVEL}
            and activation.evidence_references
        ]
        dominant.sort(key=lambda item: (-item.final_score, item.alpha_id))
        status = (
            RunStatus.FAILED
            if not claims
            else RunStatus.DEGRADED
            if reasons
            else RunStatus.COMPLETE
        )
        result = ResearchResult(
            run_id=current_run_id,
            ticker=normalized_ticker,
            analysis_date=normalized_date,
            status=status,
            dominant_alphas=dominant,
            main_conflict=conflicts[0] if conflicts else None,
            conflicts=list(conflicts),
            graph_reference="structure_graph.json",
            summary=self._summary(dominant, conflicts[0] if conflicts else None),
            evidence_coverage=evidence_coverage,
            degraded_reasons=reasons,
            errors=[],
        )
        self._persist_result(result)
        return result
