"""Fail-soft live sidecar wiring and Stage G authority routing for the
Phase 1 Structured Adapter.

This module reads the same raw reports and the already-persisted legacy
output, executes the active v4.2 Shadow protocol only when explicitly
enabled (``shadow`` or ``primary`` mode), and writes three separate
sidecars (:data:`SHADOW_OUTPUT_FILENAME` and friends). It never calls
Mapper, Extractor, Graph, Activation, or Conflict code, and never itself
writes the authoritative ``structured_agent_outputs.json``.

For ``legacy``/``shadow`` mode, the legacy adapter's ``structured_agent_
outputs.json`` remains the sole authoritative input, exactly as before
Stage G. For ``primary`` mode, :func:`select_primary_authority` decides
-- from this same, unmodified Shadow execution's already-computed
per-report accepted/rejected result, never a new pipeline -- whether the
v4.2 result becomes authoritative; the actual authoritative overwrite of
``structured_agent_outputs.json`` happens in the caller
(``routes_research.py``'s ``_run_week1_week2_artifact_pipeline``), which
already owns that file's legacy write and read-back.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from comqutor_alpha.llm_runtime.canonical_json import sha256_canonical_json
from comqutor_alpha.storage.file_store import load_json_record, save_json_record
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v4 import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v4_1 import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_1,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v4_2 import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_2,
)
from comqutor_alpha.structure_engine.structured_output_shadow_review import (
    compare_legacy_and_shadow,
)
from comqutor_alpha.structure_engine.structured_output_shadow_schema import (
    SHADOW_IDENTITY_MISMATCH,
    SHADOW_INVOKER_ERROR,
    SHADOW_JSON_INVALID,
    SHADOW_SOURCE_HASH_MISMATCH,
    build_failure_bundle,
    sha256_text,
    validate_shadow_bundle,
)

MODE_ENV_VAR = "COMQUTOR_STRUCTURED_ADAPTER_MODE"
MODE_LEGACY = "legacy"
MODE_SHADOW = "shadow"
MODE_PRIMARY = "primary"
VALID_MODES = frozenset({MODE_LEGACY, MODE_SHADOW, MODE_PRIMARY})

SHADOW_OUTPUT_FILENAME = "structured_agent_outputs_shadow.json"
SHADOW_VALIDATION_FILENAME = "structured_adapter_shadow_validation.json"
SHADOW_COMPARISON_FILENAME = "structured_adapter_shadow_comparison.json"
LIVE_SHADOW_SCHEMA_VERSION = "comqutor.structured_adapter_live_shadow.v1"


@dataclass(frozen=True)
class StructuredAdapterModeDecision:
    requested_mode: str
    effective_mode: str
    shadow_enabled: bool
    reason_code: str | None = None


@dataclass(frozen=True)
class ShadowReportContext:
    source_report: str
    run_id: str
    ticker: str
    agent: str
    agent_output_id: str
    factor_vocabulary: tuple[str, ...]


@dataclass(frozen=True)
class ShadowAttemptResult:
    bundle: Mapping[str, Any]
    provider: str = "unknown"
    model: str = "unknown"
    profile_id: str | None = None
    semantic_call_id: str | None = None
    provider_called: bool | None = None
    provider_status: str | None = None
    retry_count: int | None = None
    resolution_log: tuple[Mapping[str, Any], ...] = ()
    candidate_manifest: tuple[Mapping[str, Any], ...] = ()
    rejected_forensic_record: Mapping[str, Any] | None = None


class ShadowExecutor(Protocol):
    def execute(self, context: ShadowReportContext) -> ShadowAttemptResult | Mapping[str, Any]: ...

    def close(self, *, complete: bool) -> None: ...


def resolve_structured_adapter_mode(
    requested_mode: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> StructuredAdapterModeDecision:
    """Resolve once per run.

    Stage G (real primary-authority routing, implemented in this module's
    :func:`select_primary_authority` plus the caller-side authoritative
    write in ``routes_research.py``) supersedes the earlier Stage-E-only
    restriction: an explicitly requested ``"primary"`` mode is now real --
    it enables the same Shadow execution ``"shadow"`` mode uses
    (``shadow_enabled=True``), and the caller uses
    :func:`select_primary_authority` to decide, from that same execution's
    already-computed per-report accepted/rejected result, whether v4.2
    becomes authoritative or Legacy remains authoritative as fail-soft
    fallback. No new Provider path is added here -- only the caller-side
    authority decision is new.

    The hard-coded fallback used when neither an explicit ``requested_mode``
    nor the ``COMQUTOR_STRUCTURED_ADAPTER_MODE`` environment variable is
    set remains ``"legacy"``, deliberately unchanged: many existing tests
    call this function (directly or via ``run_research_request``) with no
    override and assert legacy-only behavior with no Provider construction.
    Activating primary mode as an environment's actual default is a
    deployment-level decision (set the environment variable in that
    environment) -- never a change to this shared function's own fallback,
    which every caller including the test suite implicitly depends on.
    """

    source = os.environ if environ is None else environ
    raw = requested_mode if requested_mode is not None else source.get(MODE_ENV_VAR, MODE_LEGACY)
    mode = str(raw or MODE_LEGACY).strip().lower()
    if mode == MODE_SHADOW:
        return StructuredAdapterModeDecision(mode, MODE_SHADOW, True)
    if mode == MODE_LEGACY:
        return StructuredAdapterModeDecision(mode, MODE_LEGACY, False)
    if mode == MODE_PRIMARY:
        return StructuredAdapterModeDecision(mode, MODE_PRIMARY, True)
    return StructuredAdapterModeDecision(
        mode, MODE_LEGACY, False, "STRUCTURED_ADAPTER_MODE_INVALID"
    )


AUTHORITY_LEGACY = "LEGACY_ADAPTER"

# Stage-G-only fallback reason codes: every one of these describes v4.2
# simply not becoming authoritative for this run -- never a semantic
# repair, never a relaxed provenance rule, never a second attempt.
FALLBACK_SIDECAR_UNAVAILABLE = "STRUCTURED_ADAPTER_PRIMARY_SIDECAR_UNAVAILABLE"
FALLBACK_SIDECAR_OUTPUT_UNREADABLE = "STRUCTURED_ADAPTER_PRIMARY_SIDECAR_OUTPUT_UNREADABLE"
FALLBACK_NO_REPORTS_ATTEMPTED = "STRUCTURED_ADAPTER_PRIMARY_NO_REPORTS_ATTEMPTED"
FALLBACK_REPORT_REJECTED = "STRUCTURED_ADAPTER_PRIMARY_REPORT_REJECTED"
FALLBACK_EMPTY_OR_NON_SUBSTANTIVE = "STRUCTURED_ADAPTER_PRIMARY_EMPTY_OR_NON_SUBSTANTIVE"


@dataclass(frozen=True)
class PrimaryAuthorityDecision:
    """The single, explicit authority decision for one run. Never leaves it
    to a downstream reader to infer which adapter is authoritative."""

    primary_attempted: bool
    primary_succeeded: bool
    authoritative_adapter: str
    fallback_used: bool
    fallback_reason: str | None
    active_protocol: str | None
    authoritative_payload: Mapping[str, Any] | None


def select_primary_authority(
    run_dir: str | Path,
    *,
    mode_decision: StructuredAdapterModeDecision,
    validation_payload: Mapping[str, Any] | None,
) -> PrimaryAuthorityDecision:
    """Decide, for ``primary`` mode only, whether the v4.2 Shadow attempt
    this run already made becomes authoritative -- reusing ONLY the
    per-report accepted/rejected classification ``run_live_shadow_sidecar``
    already computed and already persisted to
    :data:`SHADOW_OUTPUT_FILENAME`. Never re-executes, re-invokes a
    Provider, or duplicates any part of the v4.2 extraction/provenance
    path; never inspects or judges a single Claim.

    Unanimous per-report acceptance (every report this run actually
    attempted was accepted -- the same all-or-nothing admission philosophy
    already used at the Evidence-quote and bundle levels) is required for
    v4.2 to become this run's sole authority; any rejection anywhere means
    Legacy remains authoritative for the whole run. This is not an
    invented threshold -- it is the existing per-report accept/reject
    result, applied uniformly, so a run is never left with a mix of
    v4.2-authoritative and Legacy-authoritative reports.

    For ``legacy``/``shadow`` mode (or any non-primary effective mode),
    always returns the trivial "Legacy is authoritative, primary was never
    attempted" decision -- this function has no effect at all outside
    primary mode.
    """

    if mode_decision.effective_mode != MODE_PRIMARY:
        return PrimaryAuthorityDecision(
            primary_attempted=False,
            primary_succeeded=False,
            authoritative_adapter=AUTHORITY_LEGACY,
            fallback_used=False,
            fallback_reason=None,
            active_protocol=None,
            authoritative_payload=None,
        )

    def _fallback(reason: str) -> PrimaryAuthorityDecision:
        return PrimaryAuthorityDecision(
            primary_attempted=True,
            primary_succeeded=False,
            authoritative_adapter=AUTHORITY_LEGACY,
            fallback_used=True,
            fallback_reason=reason,
            active_protocol=None,
            authoritative_payload=None,
        )

    if not isinstance(validation_payload, Mapping):
        return _fallback(FALLBACK_SIDECAR_UNAVAILABLE)

    reports = validation_payload.get("reports")
    accepted_count = int(validation_payload.get("accepted_report_count") or 0)
    rejected_count = int(validation_payload.get("rejected_report_count") or 0)
    total = accepted_count + rejected_count
    if not isinstance(reports, list) or total == 0:
        return _fallback(FALLBACK_NO_REPORTS_ATTEMPTED)
    if rejected_count > 0:
        return _fallback(FALLBACK_REPORT_REJECTED)

    directory = Path(run_dir).expanduser().resolve()
    run_id = directory.name
    output_root = str(directory.parent)
    try:
        shadow_output = load_json_record(run_id, SHADOW_OUTPUT_FILENAME, output_root=output_root)
    except Exception:
        return _fallback(FALLBACK_SIDECAR_OUTPUT_UNREADABLE)

    records = shadow_output.get("records") if isinstance(shadow_output, Mapping) else None
    if not isinstance(shadow_output, Mapping) or not isinstance(records, list) or not records:
        return _fallback(FALLBACK_EMPTY_OR_NON_SUBSTANTIVE)

    adapter_version = str(shadow_output.get("adapter_version") or "")
    authoritative_payload = {
        **{
            key: value
            for key, value in shadow_output.items()
            if key not in ("shadow_only", "production_authority", "selected_authority")
        },
        "shadow_only": False,
        "production_authority": True,
        "selected_authority": adapter_version,
    }
    return PrimaryAuthorityDecision(
        primary_attempted=True,
        primary_succeeded=True,
        authoritative_adapter=adapter_version,
        fallback_used=False,
        fallback_reason=None,
        active_protocol=adapter_version,
        authoritative_payload=authoritative_payload,
    )


class _DefaultV4ShadowExecutor:
    """Lazy real-provider executor used only after explicit shadow enablement."""

    def __init__(self, run_dir: Path, report_count: int, *, cache: Any = None) -> None:
        from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
        from comqutor_alpha.research_profiles import get_research_profile
        from comqutor_alpha.structure_engine.structured_output_shadow_provider import (
            STRUCTURED_CLAIM_SHADOW_TASK,
            build_phase1_master_provider_gateway,
            profile_id_for_semantic_task,
            run_real_provider_shadow_smoke_for_report_v4,
        )

        self._runner = run_real_provider_shadow_smoke_for_report_v4
        profile = get_research_profile(profile_id_for_semantic_task(STRUCTURED_CLAIM_SHADOW_TASK))
        self.provider = profile.llm_provider
        self.model = profile.quick_think_llm
        self.profile_id = profile.profile_id
        # A run may already own the canonical Week2 semantic-call files.
        # Keep Shadow's recorder/manifest in a distinct run-local directory
        # so two sessions can never reuse call_sequence=0 in one JSONL file.
        self.runtime_directory = run_dir / "structured_adapter_shadow_runtime"
        self.runtime_directory.mkdir(exist_ok=True)
        self.session = SemanticRuntimeSession(
            run_id=run_dir.name,
            output_directory=self.runtime_directory,
            execution_mode="shadow",
            provider=self.provider,
            model=self.model,
            profile_id=self.profile_id,
            cache=cache,
        )
        self.gateway, _info = build_phase1_master_provider_gateway(
            profile=profile,
            run_id=run_dir.name,
            output_root=run_dir.parent,
            logical_call_limit=max(1, report_count),
            semantic_runtime=self.session,
        )

    def execute(self, context: ShadowReportContext) -> ShadowAttemptResult:
        bundle, invoker, _candidates, resolution_log = self._runner(
            gateway=self.gateway,
            source_report=context.source_report,
            run_id=context.run_id,
            ticker=context.ticker,
            agent=context.agent,
            agent_output_id=context.agent_output_id,
            factor_vocabulary=list(context.factor_vocabulary),
        )
        invocation = invoker.last_invocation
        trace = invocation.trace_handle if invocation is not None else None
        return ShadowAttemptResult(
            bundle=bundle,
            provider=self.provider,
            model=self.model,
            profile_id=self.profile_id,
            semantic_call_id=getattr(trace, "call_id", None),
            provider_called=invocation.provider_called if invocation is not None else None,
            provider_status=invocation.provider_status if invocation is not None else None,
            retry_count=invocation.retry_count if invocation is not None else None,
            resolution_log=tuple(resolution_log),
        )

    def close(self, *, complete: bool) -> None:
        self.session.finalize_manifest(complete=complete)


def _invoke_executor(
    executor: ShadowExecutor | Callable[..., Any], context: ShadowReportContext
) -> ShadowAttemptResult:
    method = getattr(executor, "execute", None)
    if callable(method):
        result = method(context)
    elif callable(executor):
        result = executor(
            source_report=context.source_report,
            run_id=context.run_id,
            ticker=context.ticker,
            agent=context.agent,
            agent_output_id=context.agent_output_id,
            factor_vocabulary=list(context.factor_vocabulary),
        )
    else:
        raise TypeError("shadow executor must be callable or implement execute")
    if isinstance(result, ShadowAttemptResult):
        return result
    if isinstance(result, Mapping):
        return ShadowAttemptResult(bundle=result)
    raise TypeError("shadow executor returned an unsupported value")


def _failure_bundle(
    context: ShadowReportContext,
    reason_code: str,
    message: str,
    *,
    prompt_version: str = STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4,
    prompt_sha256: str = STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256,
) -> dict[str, Any]:
    return build_failure_bundle(
        run_id=context.run_id,
        ticker=context.ticker,
        agent=context.agent,
        agent_output_id=context.agent_output_id,
        source_report_sha256=sha256_text(context.source_report),
        prompt_version=prompt_version,
        prompt_sha256=prompt_sha256,
        status="parser_error" if reason_code in {SHADOW_INVOKER_ERROR, SHADOW_JSON_INVALID} else "validation_rejected",
        reason_code=reason_code,
        message=message,
    )


def _admit_attempt(
    context: ShadowReportContext, attempt: ShadowAttemptResult
) -> tuple[dict[str, Any], bool]:
    bundle = dict(attempt.bundle)
    prompt_version = str(
        bundle.get("prompt_version") or STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4
    )
    prompt_sha256 = str(
        bundle.get("prompt_sha256") or STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256
    )
    allowed_prompt_identities = {
        (
            STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4,
            STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256,
        ),
        (
            STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_1,
            STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256,
        ),
        (
            STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_2,
            STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256,
        ),
    }
    if (prompt_version, prompt_sha256) not in allowed_prompt_identities:
        return _failure_bundle(
            context,
            SHADOW_JSON_INVALID,
            "shadow bundle prompt identity is not an approved live-sidecar version",
        ), False
    expected_identity = {
        "run_id": context.run_id,
        "ticker": context.ticker,
        "agent": context.agent,
        "agent_output_id": context.agent_output_id,
    }
    if any(str(bundle.get(key) or "") != value for key, value in expected_identity.items()):
        return _failure_bundle(
            context,
            SHADOW_IDENTITY_MISMATCH,
            "shadow bundle identity does not match source report",
            prompt_version=prompt_version,
            prompt_sha256=prompt_sha256,
        ), False
    if bundle.get("source_report_sha256") != sha256_text(context.source_report):
        return _failure_bundle(
            context,
            SHADOW_SOURCE_HASH_MISMATCH,
            "shadow bundle source hash does not match source report",
            prompt_version=prompt_version,
            prompt_sha256=prompt_sha256,
        ), False

    reported_summary = bundle.get("validation_summary")
    if not isinstance(reported_summary, Mapping) or reported_summary.get("valid") is not True:
        # Preserve the parser's versioned rejected bundle identity and
        # diagnostics. Proposed claims remain only in the separately bounded
        # forensic record and can never enter the admitted Shadow output.
        bundle["claims"] = []
        bundle["shadow_only"] = True
        bundle["production_authority"] = False
        return bundle, False

    allowed_candidate_ids = None
    if prompt_version == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_1:
        allowed_candidate_ids = [
            str(item.get("candidate_id"))
            for item in attempt.candidate_manifest
            if isinstance(item, Mapping) and item.get("candidate_id")
        ]
    validation = validate_shadow_bundle(
        bundle,
        source_report=context.source_report,
        run_id=context.run_id,
        ticker=context.ticker,
        agent=context.agent,
        agent_output_id=context.agent_output_id,
        prompt_version=prompt_version,
        prompt_sha256=prompt_sha256,
        factor_vocabulary=context.factor_vocabulary,
        allowed_source_refs=(),
        allowed_candidate_segment_ids=allowed_candidate_ids,
    )
    if not validation.valid:
        reason = validation.reason_codes[0] if validation.reason_codes else SHADOW_JSON_INVALID
        return _failure_bundle(
            context,
            reason,
            "shadow proposal failed live admission",
            prompt_version=prompt_version,
            prompt_sha256=prompt_sha256,
        ), False
    bundle["validation_summary"] = validation.to_summary()
    bundle["shadow_only"] = True
    bundle["production_authority"] = False
    return bundle, True


def _shadow_records(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    prompt_version = bundle.get("prompt_version")
    if prompt_version == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_2:
        extraction_method = "structured_llm_adapter_v4_2_shadow"
    elif prompt_version == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_1:
        extraction_method = "structured_llm_adapter_v4_1_shadow"
    else:
        extraction_method = "structured_llm_adapter_v4_shadow"
    records: list[dict[str, Any]] = []
    for claim in bundle.get("claims") or []:
        if not isinstance(claim, Mapping):
            continue
        records.append(
            {
                "run_id": bundle["run_id"],
                "ticker": bundle["ticker"],
                "agent": bundle["agent"],
                "claim": claim.get("claim"),
                "evidence": claim.get("evidence"),
                "factors": list(claim.get("factors") or []),
                "entities": list(claim.get("entities") or []),
                "direction": claim.get("direction"),
                "confidence": claim.get("confidence"),
                "source_type": claim.get("source_type"),
                "claim_id": claim.get("shadow_claim_id"),
                "source_agent_output_id": bundle["agent_output_id"],
                "source_spans": list(claim.get("source_spans") or []),
                "source_refs": list(claim.get("source_refs") or []),
                "candidate_segment_ids": list(claim.get("candidate_segment_ids") or []),
                "extraction_method": extraction_method,
                "shadow_only": True,
                "production_authority": False,
            }
        )
    return records


def _legacy_records_for_report(
    legacy_payload: Mapping[str, Any], agent_output_id: str
) -> list[dict[str, Any]]:
    return [
        dict(record)
        for record in legacy_payload.get("records") or []
        if isinstance(record, Mapping)
        and str(record.get("source_agent_output_id") or "") == agent_output_id
    ]


def run_live_shadow_sidecar(
    run_dir: str | Path,
    *,
    mode_decision: StructuredAdapterModeDecision,
    executor: ShadowExecutor | Callable[..., Any] | None = None,
    cache: Any = None,
) -> dict[str, Any]:
    """Execute and persist v4 sidecars without changing legacy authority."""

    directory = Path(run_dir).expanduser().resolve()
    if not mode_decision.shadow_enabled:
        return {
            "status": "disabled",
            "mode": mode_decision.effective_mode,
            "reason_code": mode_decision.reason_code,
            "production_authority": "LEGACY_ADAPTER",
        }

    run_id = directory.name
    output_root = directory.parent
    raw_payload = load_json_record(run_id, "raw_agent_outputs.json", output_root=output_root)
    legacy_payload = load_json_record(
        run_id, "structured_agent_outputs.json", output_root=output_root
    )
    ticker = str(raw_payload.get("ticker") or "")
    raw_reports = [item for item in raw_payload.get("agent_outputs") or [] if isinstance(item, Mapping)]

    owned_executor = executor is None
    executor_error: Exception | None = None
    if executor is None:
        try:
            executor = _DefaultV4ShadowExecutor(directory, len(raw_reports), cache=cache)
        except Exception as exc:  # explicit shadow stays fail-soft
            executor_error = exc

    from comqutor_alpha.structure_engine.factor_normalizer import FACTOR_ALIASES

    factor_vocabulary = tuple(FACTOR_ALIASES.keys())
    report_entries: list[dict[str, Any]] = []
    accepted_records: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    complete = True
    try:
        for raw in raw_reports:
            context = ShadowReportContext(
                source_report=str(raw.get("raw_output") or ""),
                run_id=run_id,
                ticker=ticker,
                agent=str(raw.get("agent") or raw.get("tradingagents_agent") or "unknown_agent"),
                agent_output_id=str(raw.get("agent_output_id") or ""),
                factor_vocabulary=factor_vocabulary,
            )
            if executor_error is not None or executor is None:
                attempt = ShadowAttemptResult(
                    bundle=_failure_bundle(
                        context,
                        SHADOW_INVOKER_ERROR,
                        f"shadow executor initialization failed: {type(executor_error).__name__}",
                    )
                )
                admitted_bundle, admitted = dict(attempt.bundle), False
            else:
                try:
                    attempt = _invoke_executor(executor, context)
                    admitted_bundle, admitted = _admit_attempt(context, attempt)
                except Exception as exc:
                    complete = False
                    attempt = ShadowAttemptResult(
                        bundle=_failure_bundle(
                            context,
                            SHADOW_INVOKER_ERROR,
                            f"shadow executor failed: {type(exc).__name__}",
                        )
                    )
                    admitted_bundle, admitted = dict(attempt.bundle), False

            if admitted:
                accepted_records.extend(_shadow_records(admitted_bundle))
            legacy_records = _legacy_records_for_report(legacy_payload, context.agent_output_id)
            comparison = compare_legacy_and_shadow(legacy_records, admitted_bundle)
            comparisons.append(comparison)
            summary = admitted_bundle.get("validation_summary") or {}
            report_entry = {
                    "run_id": run_id,
                    "ticker": ticker,
                    "agent": context.agent,
                    "agent_output_id": context.agent_output_id,
                    "source_report_sha256": sha256_text(context.source_report),
                    "prompt_version": admitted_bundle.get(
                        "prompt_version", STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4
                    ),
                    "prompt_sha256": admitted_bundle.get(
                        "prompt_sha256", STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256
                    ),
                    "schema_version": admitted_bundle.get("schema_version"),
                    "status": summary.get("status", "parser_error"),
                    "accepted": admitted,
                    "reason_codes": list(summary.get("reason_codes") or []),
                    "shadow_claim_count": len(admitted_bundle.get("claims") or []) if admitted else 0,
                    "provider": attempt.provider,
                    "model": attempt.model,
                    "profile_id": attempt.profile_id,
                    "semantic_call_id": attempt.semantic_call_id,
                    "provider_called": attempt.provider_called,
                    "provider_status": attempt.provider_status,
                    "retry_count": attempt.retry_count,
                    "resolution_log": [dict(item) for item in attempt.resolution_log],
                    "candidate_manifest": [
                        dict(item) for item in attempt.candidate_manifest
                    ],
                    "shadow_bundle": admitted_bundle,
                    "shadow_only": True,
                    "production_authority": False,
                }
            if not admitted and attempt.rejected_forensic_record is not None:
                report_entry["rejected_forensics"] = dict(
                    attempt.rejected_forensic_record
                )
            report_entries.append(report_entry)
    finally:
        if owned_executor and executor is not None:
            close = getattr(executor, "close", None)
            if callable(close):
                try:
                    close(complete=complete)
                except Exception:
                    complete = False

    report_prompt_versions = {
        str(item.get("prompt_version") or "") for item in report_entries
    }
    output_adapter_version = (
        next(iter(report_prompt_versions))
        if len(report_prompt_versions) == 1
        else "mixed"
    )
    output_payload = {
        "schema_version": legacy_payload.get("schema_version"),
        "adapter_version": output_adapter_version,
        "run_id": run_id,
        "ticker": ticker,
        "records": accepted_records,
        "shadow_only": True,
        "production_authority": False,
        "selected_authority": "LEGACY_ADAPTER",
    }
    validation_payload = {
        "schema_version": LIVE_SHADOW_SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "mode": MODE_SHADOW,
        "reports": report_entries,
        "accepted_report_count": sum(bool(item["accepted"]) for item in report_entries),
        "rejected_report_count": sum(not bool(item["accepted"]) for item in report_entries),
        "shadow_only": True,
        "production_authority": False,
        "selected_authority": "LEGACY_ADAPTER",
    }
    comparison_payload = {
        "schema_version": LIVE_SHADOW_SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "reports": comparisons,
        "legacy_output_sha256": sha256_canonical_json(legacy_payload),
        "shadow_output_sha256": sha256_canonical_json(output_payload),
        "diagnostic_only": True,
        "shadow_only": True,
        "production_authority": False,
        "authoritative_downstream_changed": False,
    }
    save_json_record(run_id, SHADOW_OUTPUT_FILENAME, output_payload, output_root=output_root)
    save_json_record(run_id, SHADOW_VALIDATION_FILENAME, validation_payload, output_root=output_root)
    save_json_record(run_id, SHADOW_COMPARISON_FILENAME, comparison_payload, output_root=output_root)
    return validation_payload


def verify_live_shadow_exact_replay(run_dir: str | Path) -> dict[str, Any]:
    """Provider-zero revalidation of persisted accepted live-shadow bundles."""

    directory = Path(run_dir).expanduser().resolve()
    run_id = directory.name
    output_root = directory.parent
    reasons: list[str] = []
    try:
        raw = load_json_record(run_id, "raw_agent_outputs.json", output_root=output_root)
        legacy = load_json_record(run_id, "structured_agent_outputs.json", output_root=output_root)
        shadow = load_json_record(run_id, SHADOW_OUTPUT_FILENAME, output_root=output_root)
        validation = load_json_record(run_id, SHADOW_VALIDATION_FILENAME, output_root=output_root)
        comparison = load_json_record(run_id, SHADOW_COMPARISON_FILENAME, output_root=output_root)
    except Exception:
        return {
            "status": "FAIL",
            "reason_codes": ["LIVE_SHADOW_REPLAY_ARTIFACT_MISSING_OR_INVALID"],
            "provider_calls": 0,
        }

    raw_by_id = {
        str(item.get("agent_output_id") or ""): item
        for item in raw.get("agent_outputs") or []
        if isinstance(item, Mapping)
    }
    from comqutor_alpha.structure_engine.factor_normalizer import FACTOR_ALIASES

    factor_vocabulary = tuple(FACTOR_ALIASES.keys())
    replay_records: list[dict[str, Any]] = []
    replay_comparisons: list[dict[str, Any]] = []
    accepted_count = 0
    for entry in validation.get("reports") or []:
        if not isinstance(entry, Mapping):
            reasons.append("LIVE_SHADOW_REPLAY_REPORT_ENTRY_INVALID")
            continue
        agent_output_id = str(entry.get("agent_output_id") or "")
        source = raw_by_id.get(agent_output_id)
        bundle = entry.get("shadow_bundle")
        if not isinstance(source, Mapping) or not isinstance(bundle, Mapping):
            reasons.append("LIVE_SHADOW_REPLAY_BINDING_MISSING")
            continue
        source_report = str(source.get("raw_output") or "")
        if entry.get("source_report_sha256") != sha256_text(source_report):
            reasons.append("LIVE_SHADOW_REPLAY_SOURCE_HASH_MISMATCH")
            continue
        if entry.get("accepted") is True:
            prompt_version = str(entry.get("prompt_version") or "")
            prompt_sha256 = str(entry.get("prompt_sha256") or "")
            candidate_manifest = entry.get("candidate_manifest") or []
            allowed_candidate_ids = None
            if prompt_version == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_1:
                allowed_candidate_ids = [
                    str(item.get("candidate_id"))
                    for item in candidate_manifest
                    if isinstance(item, Mapping) and item.get("candidate_id")
                ]
            result = validate_shadow_bundle(
                bundle,
                source_report=source_report,
                run_id=run_id,
                ticker=str(raw.get("ticker") or ""),
                agent=str(source.get("agent") or source.get("tradingagents_agent") or "unknown_agent"),
                agent_output_id=agent_output_id,
                prompt_version=prompt_version,
                prompt_sha256=prompt_sha256,
                factor_vocabulary=factor_vocabulary,
                allowed_source_refs=(),
                allowed_candidate_segment_ids=allowed_candidate_ids,
            )
            if not result.valid:
                reasons.append("LIVE_SHADOW_REPLAY_VALIDATION_NOT_REPRODUCIBLE")
                continue
            accepted_count += 1
            replay_records.extend(_shadow_records(bundle))
        legacy_records = _legacy_records_for_report(legacy, agent_output_id)
        replay_comparisons.append(compare_legacy_and_shadow(legacy_records, bundle))

    expected_shadow = dict(shadow)
    expected_shadow["records"] = replay_records
    if expected_shadow != shadow:
        reasons.append("LIVE_SHADOW_REPLAY_OUTPUT_NOT_REPRODUCIBLE")
    expected_comparison = dict(comparison)
    expected_comparison["reports"] = replay_comparisons
    if expected_comparison != comparison:
        reasons.append("LIVE_SHADOW_REPLAY_COMPARISON_NOT_REPRODUCIBLE")
    if comparison.get("legacy_output_sha256") != sha256_canonical_json(legacy):
        reasons.append("LIVE_SHADOW_REPLAY_LEGACY_IDENTITY_MISMATCH")
    if comparison.get("shadow_output_sha256") != sha256_canonical_json(shadow):
        reasons.append("LIVE_SHADOW_REPLAY_SHADOW_IDENTITY_MISMATCH")
    return {
        "status": "PASS" if not reasons else "FAIL",
        "reason_codes": list(dict.fromkeys(reasons)),
        "accepted_report_count": accepted_count,
        "provider_calls": 0,
        "provider_zero": True,
    }


__all__ = [
    "AUTHORITY_LEGACY",
    "FALLBACK_EMPTY_OR_NON_SUBSTANTIVE",
    "FALLBACK_NO_REPORTS_ATTEMPTED",
    "FALLBACK_REPORT_REJECTED",
    "FALLBACK_SIDECAR_OUTPUT_UNREADABLE",
    "FALLBACK_SIDECAR_UNAVAILABLE",
    "LIVE_SHADOW_SCHEMA_VERSION",
    "MODE_ENV_VAR",
    "MODE_LEGACY",
    "MODE_PRIMARY",
    "MODE_SHADOW",
    "SHADOW_COMPARISON_FILENAME",
    "SHADOW_OUTPUT_FILENAME",
    "SHADOW_VALIDATION_FILENAME",
    "PrimaryAuthorityDecision",
    "ShadowAttemptResult",
    "ShadowReportContext",
    "StructuredAdapterModeDecision",
    "resolve_structured_adapter_mode",
    "run_live_shadow_sidecar",
    "select_primary_authority",
    "verify_live_shadow_exact_replay",
]
