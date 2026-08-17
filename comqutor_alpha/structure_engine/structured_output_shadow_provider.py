"""Phase 1 real-Provider Shadow invokers and fixed task routing.

Phase 1B.1 and the historical Master evaluation use these seams directly.
Stage E's explicitly-enabled live sidecar orchestrator imports only the v4
gateway/runner lazily; Legacy/Mapper/Extractor/Replay/TradingAgents do not.

It routes the frozen Phase 1A Shadow prompt
(``structured_output_shadow_prompt.STRUCTURED_OUTPUT_SHADOW_PROMPT``,
version ``structured_adapter.claim_extraction_shadow.v1``) through a real,
explicitly constructed ``Week2LLMGateway`` and the existing
``StructuredOutputShadowParser``/``validate_shadow_bundle`` admission
authority -- neither the prompt text nor the Shadow validator is duplicated
or reimplemented here.

Gateway construction is independent of ``COMQUTOR_WEEK2_LLM_ENABLED`` and of
``build_server_week2_llm_gateway``: Phase 1B.1 must never infer Provider
authorization from that unrelated live-route flag. The only actual
authorization gate is the caller-supplied CLI flags
(``--execute-provider-smoke`` plus ``COMQUTOR_PHASE1B1_PROVIDER_SMOKE_APPROVED
=true``), enforced entirely in ``scripts/run_phase1b1_provider_smoke.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.research_profiles import (
    ANTHROPIC_PROFILE_ID,
    DEEPSEEK_DEFAULT_PROFILE_ID,
    ResearchProfile,
)
from comqutor_alpha.structure_engine.structured_output_shadow import (
    SemanticInvoker,
    StructuredOutputShadowParser,
    build_candidate_segments,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v2 import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v3 import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V3_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3,
)
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
from comqutor_alpha.structure_engine.structured_output_shadow_schema import (
    SHADOW_INPUT_SCHEMA_VERSION,
    STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION,
    assign_deterministic_claim_ids,
    validate_shadow_bundle,
)
from comqutor_alpha.structure_engine.structured_output_shadow_v2 import (
    SHADOW_INPUT_SCHEMA_VERSION_V2,
    SHADOW_PROVIDER_PROPOSAL_SCHEMA_VERSION_V2,
    StructuredOutputShadowParserV2,
    normalize_v2_proposal_to_canonical_bundle,
)
from comqutor_alpha.structure_engine.structured_output_shadow_v3 import (
    SHADOW_INPUT_SCHEMA_VERSION_V3,
    SHADOW_PROVIDER_PROPOSAL_SCHEMA_VERSION_V3,
    StructuredOutputShadowParserV3,
    normalize_v3_proposal_to_canonical_bundle,
)
from comqutor_alpha.structure_engine.structured_output_shadow_v4 import (
    SHADOW_INPUT_SCHEMA_VERSION_V4,
    SHADOW_PROVIDER_PROPOSAL_SCHEMA_VERSION_V4,
    StructuredOutputShadowParserV4,
    normalize_v4_proposal_to_canonical_bundle,
)
from comqutor_alpha.structure_engine.structured_output_shadow_v4_1 import (
    SHADOW_INPUT_SCHEMA_VERSION_V4_1,
    SHADOW_PROVIDER_PROPOSAL_SCHEMA_VERSION_V4_1,
    StructuredOutputShadowParserV4_1,
    bounded_provider_proposal_v4_1,
    build_rejected_forensic_record_v4_1,
    normalize_v4_1_proposal_to_canonical_bundle,
    provider_proposal_shape_valid_v4_1,
)
from comqutor_alpha.structure_engine.structured_output_shadow_v4_2 import (
    SHADOW_INPUT_SCHEMA_VERSION_V4_2,
    SHADOW_PROVIDER_PROPOSAL_SCHEMA_VERSION_V4_2,
    StructuredOutputShadowParserV4_2,
    build_rejected_forensic_record_v4_2,
    normalize_v4_2_proposal_to_canonical_bundle,
    provider_proposal_shape_valid_v4_2,
)
from comqutor_alpha.structure_engine.week2_llm import (
    Week2LLMGateway,
    Week2LLMInvocation,
    strip_markdown_json_fence as _strip_markdown_json_fence,
)

STRUCTURED_CLAIM_SHADOW_TASK = "structured_claim_shadow"

# _strip_markdown_json_fence originated here -- it is imported above
# (aliased from the shared gateway module's public strip_markdown_json_fence)
# so the whole Week2LLMGateway parsing boundary uses one single helper; see
# that module for the full diagnostic history. This module keeps only the
# wrapper class below, which pre-applies the same stripping one layer
# earlier (at the model response itself) for this gateway's own
# construction path.


class _MarkdownFenceStrippingModel:
    """Wraps a real chat model's ``.invoke(prompt)`` so a whole-response
    markdown code fence around otherwise-valid JSON is stripped before the
    shared ``Week2LLMGateway``'s strict JSON parser ever sees it.

    Scoped entirely to ``structured_claim_shadow`` gateway construction in
    this module -- never touches ``week2_llm.py``, the shared
    ``Week2LLMGateway`` defaults, or the 3 existing DeepSeek-routed tasks
    (which never go through ``build_real_provider_gateway``/
    ``build_phase1_master_provider_gateway`` at all).
    """

    def __init__(self, model: Any) -> None:
        self._model = model

    def invoke(self, prompt: Any, *args: Any, **kwargs: Any) -> Any:
        response = self._model.invoke(prompt, *args, **kwargs)
        content = getattr(response, "content", None)
        if isinstance(content, str):
            stripped = _strip_markdown_json_fence(content)
            if stripped != content:
                try:
                    response.content = stripped
                except Exception:
                    return response
        return response

    def __getattr__(self, name: str) -> Any:
        return getattr(self._model, name)

# Phase 1 Master: product-owner-approved task-level execution
# policy override for structured_claim_shadow ONLY. Never applied to the
# shared Week2LLMGateway constructor defaults (DEFAULT_TIMEOUT_SECONDS=15,
# DEFAULT_MAX_RETRIES=1), which the three existing live tasks
# (structured_adapter, alpha_classifier, structure_extractor) keep using
# completely unchanged. Literal caller-supplied constants -- never derived
# from Provider output, report text, or an environment variable.
STRUCTURED_CLAIM_SHADOW_TIMEOUT_SECONDS = 180.0
STRUCTURED_CLAIM_SHADOW_MAX_RETRIES = 1
STRUCTURED_CLAIM_SHADOW_EXECUTION_POLICY_SOURCE = (
    "phase1_structured_claim_shadow_anthropic_policy"
)
SHADOW_WEEK2_ERROR_LOG_ARTIFACT_PATH = (
    "structured_adapter_shadow_runtime/error_logs/week2_llm_errors.jsonl"
)

# Evaluation-only fixed routing. This mapping is deliberately not consulted
# by live routes or build_server_week2_llm_gateway: the three existing Week2
# tasks retain their current DeepSeek configuration, while only the Phase 1
# Shadow evaluation task is routed to the registered Anthropic profile.
SEMANTIC_TASK_PROFILE_IDS = {
    STRUCTURED_CLAIM_SHADOW_TASK: ANTHROPIC_PROFILE_ID,
    "structured_adapter": DEEPSEEK_DEFAULT_PROFILE_ID,
    "alpha_classifier": DEEPSEEK_DEFAULT_PROFILE_ID,
    "structure_extractor": DEEPSEEK_DEFAULT_PROFILE_ID,
}


def profile_id_for_semantic_task(task: str) -> str:
    try:
        return SEMANTIC_TASK_PROFILE_IDS[task]
    except KeyError as exc:
        raise ValueError("PHASE1_MASTER_SEMANTIC_TASK_UNKNOWN") from exc


class ProviderSmokeAuthorizationError(Exception):
    """Raised when a caller attempts to build a real gateway without every
    required, explicit Phase 1B.1 authorization input."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class ProviderSmokeGatewayInfo:
    """Non-secret record of exactly what was constructed, for printing/audit."""

    provider: str
    model: str
    research_profile_id: str
    logical_call_limit: int
    max_retries: int
    max_provider_attempts: int
    timeout_seconds: float


def build_real_provider_gateway(
    *,
    profile: ResearchProfile,
    run_id: str,
    output_root: Any,
    logical_call_limit: int,
    semantic_runtime: SemanticRuntimeSession | None = None,
) -> tuple[Week2LLMGateway, ProviderSmokeGatewayInfo]:
    """Construct a real, evaluation-only ``Week2LLMGateway`` from an explicit
    :class:`ResearchProfile` -- never from ``COMQUTOR_WEEK2_LLM_ENABLED`` or
    ``build_server_week2_llm_gateway``.

    ``max_calls`` is derived, never guessed: ``logical_call_limit *
    (1 + Week2LLMGateway.DEFAULT_MAX_RETRIES)`` -- the existing Gateway retry
    default is reused unchanged; this function never overrides it.
    """
    if logical_call_limit < 1 or logical_call_limit > 4:
        raise ProviderSmokeAuthorizationError("PHASE1B1_LOGICAL_CALL_LIMIT_INVALID")

    from comqutor_alpha.structure_engine.week2_llm import DEFAULT_MAX_RETRIES
    from tradingagents.llm_clients import create_llm_client

    try:
        client = create_llm_client(
            provider=profile.llm_provider,
            model=profile.quick_think_llm,
            base_url=profile.backend_url,
            timeout=STRUCTURED_CLAIM_SHADOW_TIMEOUT_SECONDS,
            max_retries=0,
        )
        model = _MarkdownFenceStrippingModel(client.get_llm())
    except Exception as exc:
        raise ProviderSmokeAuthorizationError("PHASE1B1_PROVIDER_CLIENT_INITIALIZATION_FAILED") from exc

    max_provider_attempts = logical_call_limit * (1 + DEFAULT_MAX_RETRIES)
    gateway = Week2LLMGateway(
        model,
        run_id=run_id,
        output_root=output_root,
        timeout_seconds=STRUCTURED_CLAIM_SHADOW_TIMEOUT_SECONDS,
        max_retries=DEFAULT_MAX_RETRIES,
        max_calls=max_provider_attempts,
        provider=profile.llm_provider,
        model_name=profile.quick_think_llm,
        semantic_runtime=semantic_runtime,
        error_log_artifact_path=SHADOW_WEEK2_ERROR_LOG_ARTIFACT_PATH,
    )
    info = ProviderSmokeGatewayInfo(
        provider=profile.llm_provider,
        model=profile.quick_think_llm,
        research_profile_id=profile.profile_id,
        logical_call_limit=logical_call_limit,
        max_retries=DEFAULT_MAX_RETRIES,
        max_provider_attempts=max_provider_attempts,
        timeout_seconds=STRUCTURED_CLAIM_SHADOW_TIMEOUT_SECONDS,
    )
    return gateway, info


def build_phase1_master_provider_gateway(
    *,
    profile: ResearchProfile,
    run_id: str,
    output_root: Any,
    logical_call_limit: int,
    semantic_runtime: SemanticRuntimeSession | None = None,
    max_retries: int | None = None,
) -> tuple[Week2LLMGateway, ProviderSmokeGatewayInfo]:
    """Build the Phase 1 Master evaluation gateway for up to 24 reports.

    The profile is fixed by :func:`profile_id_for_semantic_task`; this seam
    merely validates the resolved object and never accepts provider/model
    strings. Provider SDK retries remain disabled so the explicit Gateway
    policy is the sole, observable retry authority.
    """

    if profile.profile_id != profile_id_for_semantic_task(STRUCTURED_CLAIM_SHADOW_TASK):
        raise ProviderSmokeAuthorizationError("PHASE1_MASTER_SHADOW_PROFILE_INVALID")
    if logical_call_limit < 1 or logical_call_limit > 24:
        raise ProviderSmokeAuthorizationError("PHASE1_MASTER_LOGICAL_CALL_LIMIT_INVALID")
    effective_max_retries = (
        STRUCTURED_CLAIM_SHADOW_MAX_RETRIES
        if max_retries is None
        else max_retries
    )
    if (
        not isinstance(effective_max_retries, int)
        or effective_max_retries < 0
        or effective_max_retries > STRUCTURED_CLAIM_SHADOW_MAX_RETRIES
    ):
        raise ProviderSmokeAuthorizationError("PHASE1_MASTER_MAX_RETRIES_INVALID")

    from tradingagents.llm_clients import create_llm_client

    try:
        client = create_llm_client(
            provider=profile.llm_provider,
            model=profile.quick_think_llm,
            base_url=profile.backend_url,
            timeout=STRUCTURED_CLAIM_SHADOW_TIMEOUT_SECONDS,
            max_retries=0,
        )
        model = _MarkdownFenceStrippingModel(client.get_llm())
    except Exception as exc:
        raise ProviderSmokeAuthorizationError(
            "PHASE1_MASTER_PROVIDER_CLIENT_INITIALIZATION_FAILED"
        ) from exc

    max_provider_attempts = logical_call_limit * (1 + effective_max_retries)
    gateway = Week2LLMGateway(
        model,
        run_id=run_id,
        output_root=output_root,
        timeout_seconds=STRUCTURED_CLAIM_SHADOW_TIMEOUT_SECONDS,
        max_retries=effective_max_retries,
        max_calls=max_provider_attempts,
        provider=profile.llm_provider,
        model_name=profile.quick_think_llm,
        semantic_runtime=semantic_runtime,
        error_log_artifact_path=SHADOW_WEEK2_ERROR_LOG_ARTIFACT_PATH,
    )
    return gateway, ProviderSmokeGatewayInfo(
        provider=profile.llm_provider,
        model=profile.quick_think_llm,
        research_profile_id=profile.profile_id,
        logical_call_limit=logical_call_limit,
        max_retries=effective_max_retries,
        max_provider_attempts=max_provider_attempts,
        timeout_seconds=STRUCTURED_CLAIM_SHADOW_TIMEOUT_SECONDS,
    )


class Week2GatewaySemanticInvoker(SemanticInvoker):
    """``SemanticInvoker``-compatible wrapper routing the frozen Phase 1A
    Shadow prompt through ``Week2LLMGateway.invoke_prebuilt_json_prompt``.

    The Gateway-level ``validator`` closure below runs the exact same
    ``validate_shadow_bundle`` deterministic admission authority Phase 1A
    already uses, so the persisted ``SemanticCallRecord.validation_status``
    reflects true Shadow-contract acceptance -- never mere JSON-parseability.
    The raw parsed proposal (accepted or not) is then handed back to
    ``StructuredOutputShadowParser.parse_report_shadow`` unchanged, which
    independently re-derives the exact same, already-tested fail-soft bundle
    (``parser_error``/``validation_rejected``/``empty_valid_output``/
    ``abstained``) -- this module never reimplements that logic.
    """

    def __init__(self, gateway: Week2LLMGateway) -> None:
        self._gateway = gateway
        self.last_invocation: Week2LLMInvocation | None = None

    def invoke(self, *, prompt: str, request: Mapping[str, Any]) -> Any:
        def _gateway_validator(parsed: Mapping[str, Any]) -> Mapping[str, Any]:
            if not isinstance(parsed, Mapping):
                raise ValueError("shadow_gateway_proposal_not_object")
            proposal_with_ids = assign_deterministic_claim_ids(parsed)
            validation = validate_shadow_bundle(
                proposal_with_ids,
                source_report=str(request.get("agent_report") or ""),
                run_id=str(request.get("run_id") or ""),
                ticker=str(request.get("ticker") or ""),
                agent=str(request.get("agent") or ""),
                agent_output_id=str(request.get("agent_output_id") or ""),
                prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
                prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
                factor_vocabulary=list(request.get("factor_vocabulary") or []),
                allowed_source_refs=list(request.get("allowed_source_refs") or []),
                allowed_candidate_segment_ids=[
                    str(segment.get("candidate_segment_id") or "")
                    for segment in (request.get("candidate_segments") or [])
                    if isinstance(segment, Mapping)
                ],
            )
            if not validation.valid:
                raise ValueError("shadow_gateway_validation_rejected:" + ",".join(validation.reason_codes))
            return parsed

        invocation = self._gateway.invoke_prebuilt_json_prompt(
            task=STRUCTURED_CLAIM_SHADOW_TASK,
            prompt=prompt,
            prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
            prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
            input_schema_version=str(request.get("input_schema_version") or SHADOW_INPUT_SCHEMA_VERSION),
            output_schema_version=str(
                request.get("output_schema_version") or STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION
            ),
            payload_for_identity=request,
            validator=_gateway_validator,
            timeout_seconds=STRUCTURED_CLAIM_SHADOW_TIMEOUT_SECONDS,
            max_retries=STRUCTURED_CLAIM_SHADOW_MAX_RETRIES,
            execution_policy_source=STRUCTURED_CLAIM_SHADOW_EXECUTION_POLICY_SOURCE,
        )
        self.last_invocation = invocation
        self._gateway.finalize_semantic_invocation(
            invocation,
            accepted=invocation.validation_accepted,
            fallback_reason=(
                None
                if invocation.validation_accepted
                else (invocation.error_code or "SHADOW_GATEWAY_VALIDATION_REJECTED")
            ),
        )
        if invocation.parsed_output is not None:
            # Return the RAW parsed proposal (not the Gateway-level validated
            # copy) so StructuredOutputShadowParser independently re-derives
            # its own authoritative bundle/failure -- this preserves Phase
            # 1A's exact, already-tested fail-soft granularity.
            return invocation.parsed_output
        raise RuntimeError(invocation.error_code or "WEEK2_LLM_PROVIDER_ERROR")


def run_real_provider_shadow_smoke_for_report(
    *,
    gateway: Week2LLMGateway,
    source_report: str,
    run_id: str,
    ticker: str,
    agent: str,
    agent_output_id: str,
    factor_vocabulary: list[str],
    source_metadata: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], Week2GatewaySemanticInvoker, list[dict[str, Any]]]:
    """Run one real-Provider Shadow smoke call for one report.

    Returns ``(shadow_bundle, invoker, candidate_segments)``. Candidate
    segments are the same read-only hints
    ``StructuredOutputShadowParser.parse_report_shadow`` would compute
    internally; returned separately so the caller can persist them without
    recomputation drift.
    """
    invoker = Week2GatewaySemanticInvoker(gateway)
    candidate_segments, _filtered = build_candidate_segments(
        source_report, agent_output_id=agent_output_id
    )
    parser = StructuredOutputShadowParser(invoker, factor_vocabulary=factor_vocabulary)
    bundle = parser.parse_report_shadow(
        source_report=source_report,
        run_id=run_id,
        ticker=ticker,
        agent=agent,
        agent_output_id=agent_output_id,
        source_metadata=source_metadata,
        candidate_segments=candidate_segments,
    )
    return bundle, invoker, candidate_segments


class Week2GatewaySemanticInvokerV2(SemanticInvoker):
    """``SemanticInvoker``-compatible wrapper routing the v2 minimal-request
    Shadow prompt (Phase 1 Master prompt-size fix; see
    ``docs/audit_artifacts/phase1_master/prompt_audit/``) through
    ``Week2LLMGateway.invoke_prebuilt_json_prompt``.

    Mirrors :class:`Week2GatewaySemanticInvoker` exactly, with one
    difference: the Gateway-level ``validator`` closure must first upgrade
    the small v2 Provider proposal into the canonical bundle shape via
    :func:`normalize_v2_proposal_to_canonical_bundle` before the same,
    unchanged ``validate_shadow_bundle`` can run -- v1's proposal already
    *was* bundle-shaped, so it skipped straight to validation. The raw small
    proposal (accepted or not) is handed back to
    ``StructuredOutputShadowParserV2.parse_report_shadow_v2`` unchanged,
    which independently re-derives its own authoritative bundle/failure --
    this class never reimplements that logic, matching v1's own pattern.
    """

    def __init__(self, gateway: Week2LLMGateway) -> None:
        self._gateway = gateway
        self.last_invocation: Week2LLMInvocation | None = None

    def invoke(self, *, prompt: str, request: Mapping[str, Any]) -> Any:
        def _gateway_validator(parsed: Mapping[str, Any]) -> Mapping[str, Any]:
            if not isinstance(parsed, Mapping):
                raise ValueError("shadow_gateway_v2_proposal_not_object")
            canonical = normalize_v2_proposal_to_canonical_bundle(
                parsed,
                source_report=str(request.get("agent_report") or ""),
                run_id=str(request.get("run_id") or ""),
                ticker=str(request.get("ticker") or ""),
                agent=str(request.get("agent") or ""),
                agent_output_id=str(request.get("agent_output_id") or ""),
                candidate_index_to_id={},
            )
            proposal_with_ids = assign_deterministic_claim_ids(canonical)
            validation = validate_shadow_bundle(
                proposal_with_ids,
                source_report=str(request.get("agent_report") or ""),
                run_id=str(request.get("run_id") or ""),
                ticker=str(request.get("ticker") or ""),
                agent=str(request.get("agent") or ""),
                agent_output_id=str(request.get("agent_output_id") or ""),
                prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2,
                prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256,
                factor_vocabulary=list(request.get("factor_vocabulary") or []),
                allowed_source_refs=(),
                allowed_candidate_segment_ids=None,
            )
            if not validation.valid:
                raise ValueError("shadow_gateway_v2_validation_rejected:" + ",".join(validation.reason_codes))
            return parsed

        invocation = self._gateway.invoke_prebuilt_json_prompt(
            task=STRUCTURED_CLAIM_SHADOW_TASK,
            prompt=prompt,
            prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2,
            prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256,
            input_schema_version=str(request.get("input_schema_version") or SHADOW_INPUT_SCHEMA_VERSION_V2),
            output_schema_version=SHADOW_PROVIDER_PROPOSAL_SCHEMA_VERSION_V2,
            payload_for_identity=request,
            validator=_gateway_validator,
            timeout_seconds=STRUCTURED_CLAIM_SHADOW_TIMEOUT_SECONDS,
            max_retries=STRUCTURED_CLAIM_SHADOW_MAX_RETRIES,
            execution_policy_source=STRUCTURED_CLAIM_SHADOW_EXECUTION_POLICY_SOURCE + "_v2_minimal_request",
        )
        self.last_invocation = invocation
        self._gateway.finalize_semantic_invocation(
            invocation,
            accepted=invocation.validation_accepted,
            fallback_reason=(
                None
                if invocation.validation_accepted
                else (invocation.error_code or "SHADOW_GATEWAY_VALIDATION_REJECTED")
            ),
        )
        if invocation.parsed_output is not None:
            return invocation.parsed_output
        raise RuntimeError(invocation.error_code or "WEEK2_LLM_PROVIDER_ERROR")


def run_real_provider_shadow_smoke_for_report_v2(
    *,
    gateway: Week2LLMGateway,
    source_report: str,
    run_id: str,
    ticker: str,
    agent: str,
    agent_output_id: str,
    factor_vocabulary: list[str],
) -> tuple[dict[str, Any], Week2GatewaySemanticInvokerV2, list[dict[str, Any]]]:
    """v2 sibling of :func:`run_real_provider_shadow_smoke_for_report`: same
    real-Provider, one-report-at-a-time call shape, minimal wire request.

    Returns ``(shadow_bundle, invoker, candidate_segments)`` -- the returned
    ``candidate_segments`` are still the FULL v1-shaped hints (for audit/
    replay persistence, matching the existing directory contract exactly);
    only what actually crosses the wire to the Provider is smaller.
    """
    invoker = Week2GatewaySemanticInvokerV2(gateway)
    candidate_segments, _filtered = build_candidate_segments(source_report, agent_output_id=agent_output_id)
    parser = StructuredOutputShadowParserV2(invoker, factor_vocabulary=factor_vocabulary)
    bundle = parser.parse_report_shadow_v2(
        source_report=source_report,
        run_id=run_id,
        ticker=ticker,
        agent=agent,
        agent_output_id=agent_output_id,
        candidate_segments=candidate_segments,
    )
    return bundle, invoker, candidate_segments


def _candidate_hint_spans_from_request(request: Mapping[str, Any]) -> dict[int, list[tuple[int, int]]]:
    """Rebuild ``{candidate_index: [(start,end)]}`` from the wire request's
    own ``candidate_hints`` -- the only candidate location data available at
    the Gateway-level pre-validation closure (the full candidate segment
    list, including string IDs, is never sent to the Provider). Used only
    so this coarse closure can disambiguate a repeated quote exactly the
    same way the authoritative parser-level normalization does; it never
    gains access to real ``candidate_segment_id`` strings this way (see
    :func:`normalize_v3_proposal_to_canonical_bundle`'s docstring)."""

    spans: dict[int, list[tuple[int, int]]] = {}
    for hint in request.get("candidate_hints") or []:
        if not isinstance(hint, Mapping):
            continue
        index, start, end = hint.get("id"), hint.get("start"), hint.get("end")
        if (
            isinstance(index, int)
            and not isinstance(index, bool)
            and isinstance(start, int)
            and not isinstance(start, bool)
            and isinstance(end, int)
            and not isinstance(end, bool)
        ):
            spans.setdefault(index, []).append((start, end))
    return spans


class Week2GatewaySemanticInvokerV3(SemanticInvoker):
    """``SemanticInvoker``-compatible wrapper routing the v3 evidence-
    alignment-fix Shadow prompt (Phase 1 Master evidence-alignment fix; see
    ``comqutor_alpha/structure_engine/structured_output_shadow_v3.py``)
    through ``Week2LLMGateway.invoke_prebuilt_json_prompt``.

    Mirrors :class:`Week2GatewaySemanticInvokerV2` exactly: the Gateway-
    level ``validator`` closure upgrades the small v3 Provider proposal
    into the canonical bundle shape via
    :func:`normalize_v3_proposal_to_canonical_bundle` (using only the
    offset hints available in the wire request itself for disambiguation,
    never real candidate-segment-id strings -- see
    :func:`_candidate_hint_spans_from_request`) before the same, unchanged
    ``validate_shadow_bundle`` runs. The raw small proposal (accepted or
    not) is handed back to
    ``StructuredOutputShadowParserV3.parse_report_shadow_v3`` unchanged,
    which independently re-derives its own authoritative bundle/failure
    (with the real candidate-segment-id mapping) -- this class never
    reimplements that logic, matching v1/v2's own pattern.
    """

    def __init__(self, gateway: Week2LLMGateway) -> None:
        self._gateway = gateway
        self.last_invocation: Week2LLMInvocation | None = None

    def invoke(self, *, prompt: str, request: Mapping[str, Any]) -> Any:
        def _gateway_validator(parsed: Mapping[str, Any]) -> Mapping[str, Any]:
            if not isinstance(parsed, Mapping):
                raise ValueError("shadow_gateway_v3_proposal_not_object")
            canonical, _resolution_log = normalize_v3_proposal_to_canonical_bundle(
                parsed,
                source_report=str(request.get("agent_report") or ""),
                run_id=str(request.get("run_id") or ""),
                ticker=str(request.get("ticker") or ""),
                agent=str(request.get("agent") or ""),
                agent_output_id=str(request.get("agent_output_id") or ""),
                candidate_index_to_id={},
                candidate_index_to_spans=_candidate_hint_spans_from_request(request),
            )
            proposal_with_ids = assign_deterministic_claim_ids(canonical)
            validation = validate_shadow_bundle(
                proposal_with_ids,
                source_report=str(request.get("agent_report") or ""),
                run_id=str(request.get("run_id") or ""),
                ticker=str(request.get("ticker") or ""),
                agent=str(request.get("agent") or ""),
                agent_output_id=str(request.get("agent_output_id") or ""),
                prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3,
                prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_V3_SHA256,
                factor_vocabulary=list(request.get("factor_vocabulary") or []),
                allowed_source_refs=(),
                allowed_candidate_segment_ids=None,
            )
            if not validation.valid:
                raise ValueError("shadow_gateway_v3_validation_rejected:" + ",".join(validation.reason_codes))
            return parsed

        invocation = self._gateway.invoke_prebuilt_json_prompt(
            task=STRUCTURED_CLAIM_SHADOW_TASK,
            prompt=prompt,
            prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3,
            prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_V3_SHA256,
            input_schema_version=str(request.get("input_schema_version") or SHADOW_INPUT_SCHEMA_VERSION_V3),
            output_schema_version=SHADOW_PROVIDER_PROPOSAL_SCHEMA_VERSION_V3,
            payload_for_identity=request,
            validator=_gateway_validator,
            timeout_seconds=STRUCTURED_CLAIM_SHADOW_TIMEOUT_SECONDS,
            max_retries=STRUCTURED_CLAIM_SHADOW_MAX_RETRIES,
            execution_policy_source=STRUCTURED_CLAIM_SHADOW_EXECUTION_POLICY_SOURCE + "_v3_evidence_alignment_fix",
        )
        self.last_invocation = invocation
        self._gateway.finalize_semantic_invocation(
            invocation,
            accepted=invocation.validation_accepted,
            fallback_reason=(
                None
                if invocation.validation_accepted
                else (invocation.error_code or "SHADOW_GATEWAY_VALIDATION_REJECTED")
            ),
        )
        if invocation.parsed_output is not None:
            return invocation.parsed_output
        raise RuntimeError(invocation.error_code or "WEEK2_LLM_PROVIDER_ERROR")


def run_real_provider_shadow_smoke_for_report_v3(
    *,
    gateway: Week2LLMGateway,
    source_report: str,
    run_id: str,
    ticker: str,
    agent: str,
    agent_output_id: str,
    factor_vocabulary: list[str],
) -> tuple[dict[str, Any], Week2GatewaySemanticInvokerV3, list[dict[str, Any]], list[dict[str, Any]]]:
    """v3 sibling of :func:`run_real_provider_shadow_smoke_for_report_v2`:
    same real-Provider, one-report-at-a-time call shape, minimal wire
    request.

    Returns ``(shadow_bundle, invoker, candidate_segments, resolution_log)``
    -- the returned ``candidate_segments`` are still the FULL v1-shaped
    hints (for audit/replay persistence, matching the existing directory
    contract exactly); ``resolution_log`` is the parser's authoritative,
    bundle-external per-quote ``EvidenceQuoteResolver`` record (read from
    ``parser.last_resolution_log`` after the call), used only for Phase 1
    Master's own evidence-alignment gate diagnostics.
    """
    invoker = Week2GatewaySemanticInvokerV3(gateway)
    candidate_segments, _filtered = build_candidate_segments(source_report, agent_output_id=agent_output_id)
    parser = StructuredOutputShadowParserV3(invoker, factor_vocabulary=factor_vocabulary)
    bundle = parser.parse_report_shadow_v3(
        source_report=source_report,
        run_id=run_id,
        ticker=ticker,
        agent=agent,
        agent_output_id=agent_output_id,
        candidate_segments=candidate_segments,
    )
    return bundle, invoker, candidate_segments, list(parser.last_resolution_log)


class Week2GatewaySemanticInvokerV4(SemanticInvoker):
    """``SemanticInvoker``-compatible wrapper routing the v4 markdown-
    formatting-fidelity Shadow prompt (Phase 1 Master evidence-alignment
    fix, round 2; see
    ``comqutor_alpha/structure_engine/structured_output_shadow_v4.py``)
    through ``Week2LLMGateway.invoke_prebuilt_json_prompt``.

    Byte-identical structure to :class:`Week2GatewaySemanticInvokerV3` --
    only the prompt/schema identity constants differ. See that class's
    docstring for why the Gateway-level pre-validation closure uses only
    the wire request's own offset hints (never real candidate-segment-id
    strings) for disambiguation.
    """

    def __init__(self, gateway: Week2LLMGateway) -> None:
        self._gateway = gateway
        self.last_invocation: Week2LLMInvocation | None = None

    def invoke(self, *, prompt: str, request: Mapping[str, Any]) -> Any:
        def _gateway_validator(parsed: Mapping[str, Any]) -> Mapping[str, Any]:
            if not isinstance(parsed, Mapping):
                raise ValueError("shadow_gateway_v4_proposal_not_object")
            canonical, _resolution_log = normalize_v4_proposal_to_canonical_bundle(
                parsed,
                source_report=str(request.get("agent_report") or ""),
                run_id=str(request.get("run_id") or ""),
                ticker=str(request.get("ticker") or ""),
                agent=str(request.get("agent") or ""),
                agent_output_id=str(request.get("agent_output_id") or ""),
                candidate_index_to_id={},
                candidate_index_to_spans=_candidate_hint_spans_from_request(request),
            )
            proposal_with_ids = assign_deterministic_claim_ids(canonical)
            validation = validate_shadow_bundle(
                proposal_with_ids,
                source_report=str(request.get("agent_report") or ""),
                run_id=str(request.get("run_id") or ""),
                ticker=str(request.get("ticker") or ""),
                agent=str(request.get("agent") or ""),
                agent_output_id=str(request.get("agent_output_id") or ""),
                prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4,
                prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256,
                factor_vocabulary=list(request.get("factor_vocabulary") or []),
                allowed_source_refs=(),
                allowed_candidate_segment_ids=None,
            )
            if not validation.valid:
                raise ValueError("shadow_gateway_v4_validation_rejected:" + ",".join(validation.reason_codes))
            return parsed

        invocation = self._gateway.invoke_prebuilt_json_prompt(
            task=STRUCTURED_CLAIM_SHADOW_TASK,
            prompt=prompt,
            prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4,
            prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256,
            input_schema_version=str(request.get("input_schema_version") or SHADOW_INPUT_SCHEMA_VERSION_V4),
            output_schema_version=SHADOW_PROVIDER_PROPOSAL_SCHEMA_VERSION_V4,
            payload_for_identity=request,
            validator=_gateway_validator,
            timeout_seconds=STRUCTURED_CLAIM_SHADOW_TIMEOUT_SECONDS,
            max_retries=STRUCTURED_CLAIM_SHADOW_MAX_RETRIES,
            execution_policy_source=STRUCTURED_CLAIM_SHADOW_EXECUTION_POLICY_SOURCE + "_v4_markdown_formatting_fix",
        )
        self.last_invocation = invocation
        self._gateway.finalize_semantic_invocation(
            invocation,
            accepted=invocation.validation_accepted,
            fallback_reason=(
                None
                if invocation.validation_accepted
                else (invocation.error_code or "SHADOW_GATEWAY_VALIDATION_REJECTED")
            ),
        )
        if invocation.parsed_output is not None:
            return invocation.parsed_output
        raise RuntimeError(invocation.error_code or "WEEK2_LLM_PROVIDER_ERROR")


def run_real_provider_shadow_smoke_for_report_v4(
    *,
    gateway: Week2LLMGateway,
    source_report: str,
    run_id: str,
    ticker: str,
    agent: str,
    agent_output_id: str,
    factor_vocabulary: list[str],
) -> tuple[dict[str, Any], Week2GatewaySemanticInvokerV4, list[dict[str, Any]], list[dict[str, Any]]]:
    """v4 sibling of :func:`run_real_provider_shadow_smoke_for_report_v3`:
    same real-Provider, one-report-at-a-time call shape, minimal wire
    request.

    Returns ``(shadow_bundle, invoker, candidate_segments, resolution_log)``
    -- see the v3 function's docstring; identical contract, v4 prompt only.
    """
    invoker = Week2GatewaySemanticInvokerV4(gateway)
    candidate_segments, _filtered = build_candidate_segments(source_report, agent_output_id=agent_output_id)
    parser = StructuredOutputShadowParserV4(invoker, factor_vocabulary=factor_vocabulary)
    bundle = parser.parse_report_shadow_v4(
        source_report=source_report,
        run_id=run_id,
        ticker=ticker,
        agent=agent,
        agent_output_id=agent_output_id,
        candidate_segments=candidate_segments,
    )
    return bundle, invoker, candidate_segments, list(parser.last_resolution_log)


class Week2GatewaySemanticInvokerV4_1(SemanticInvoker):
    """Gateway seam for the additive v4.1 location-only protocol."""

    def __init__(self, gateway: Week2LLMGateway, *, max_retries: int | None = None) -> None:
        self._gateway = gateway
        self._max_retries = (
            STRUCTURED_CLAIM_SHADOW_MAX_RETRIES
            if max_retries is None
            else max_retries
        )
        if (
            not isinstance(self._max_retries, int)
            or self._max_retries < 0
            or self._max_retries > STRUCTURED_CLAIM_SHADOW_MAX_RETRIES
        ):
            raise ValueError("structured_shadow_v4_1_max_retries_invalid")
        self.last_invocation: Week2LLMInvocation | None = None

    def invoke(self, *, prompt: str, request: Mapping[str, Any]) -> Any:
        def _gateway_validator(parsed: Mapping[str, Any]) -> Mapping[str, Any]:
            if not isinstance(parsed, Mapping):
                raise ValueError("shadow_gateway_v4_1_proposal_not_object")
            if not provider_proposal_shape_valid_v4_1(parsed):
                raise ValueError("shadow_gateway_v4_1_unapproved_output_field")
            bounded = bounded_provider_proposal_v4_1(parsed)
            manifest = [
                dict(item)
                for item in request.get("candidate_hints") or []
                if isinstance(item, Mapping)
            ]
            canonical, _diagnostics = normalize_v4_1_proposal_to_canonical_bundle(
                bounded,
                source_report=str(request.get("agent_report") or ""),
                run_id=str(request.get("run_id") or ""),
                ticker=str(request.get("ticker") or ""),
                agent=str(request.get("agent") or ""),
                agent_output_id=str(request.get("agent_output_id") or ""),
                candidate_manifest=manifest,
            )
            validation = validate_shadow_bundle(
                assign_deterministic_claim_ids(canonical),
                source_report=str(request.get("agent_report") or ""),
                run_id=str(request.get("run_id") or ""),
                ticker=str(request.get("ticker") or ""),
                agent=str(request.get("agent") or ""),
                agent_output_id=str(request.get("agent_output_id") or ""),
                prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_1,
                prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256,
                factor_vocabulary=list(request.get("factor_vocabulary") or []),
                allowed_source_refs=(),
                allowed_candidate_segment_ids=[
                    item["candidate_id"]
                    for item in manifest
                    if isinstance(item.get("candidate_id"), str)
                ],
            )
            if not validation.valid:
                raise ValueError(
                    "shadow_gateway_v4_1_validation_rejected:"
                    + ",".join(validation.reason_codes)
                )
            return bounded

        invocation = self._gateway.invoke_prebuilt_json_prompt(
            task=STRUCTURED_CLAIM_SHADOW_TASK,
            prompt=prompt,
            prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_1,
            prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256,
            input_schema_version=str(
                request.get("input_schema_version") or SHADOW_INPUT_SCHEMA_VERSION_V4_1
            ),
            output_schema_version=SHADOW_PROVIDER_PROPOSAL_SCHEMA_VERSION_V4_1,
            payload_for_identity=request,
            validator=_gateway_validator,
            timeout_seconds=STRUCTURED_CLAIM_SHADOW_TIMEOUT_SECONDS,
            max_retries=self._max_retries,
            execution_policy_source=(
                STRUCTURED_CLAIM_SHADOW_EXECUTION_POLICY_SOURCE
                + "_v4_1_deterministic_candidate_binding"
            ),
        )
        self.last_invocation = invocation
        self._gateway.finalize_semantic_invocation(
            invocation,
            accepted=invocation.validation_accepted,
            fallback_reason=(
                None
                if invocation.validation_accepted
                else (invocation.error_code or "SHADOW_GATEWAY_VALIDATION_REJECTED")
            ),
        )
        if invocation.parsed_output is not None:
            return invocation.parsed_output
        raise RuntimeError(invocation.error_code or "WEEK2_LLM_PROVIDER_ERROR")


def run_real_provider_shadow_smoke_for_report_v4_1(
    *,
    gateway: Week2LLMGateway,
    source_report: str,
    run_id: str,
    ticker: str,
    agent: str,
    agent_output_id: str,
    factor_vocabulary: list[str],
    max_retries: int | None = None,
) -> tuple[
    dict[str, Any],
    Week2GatewaySemanticInvokerV4_1,
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any] | None,
]:
    """Offline-testable real Gateway shape for future v4.1 qualification."""

    invoker = Week2GatewaySemanticInvokerV4_1(
        gateway, max_retries=max_retries
    )
    candidate_segments, _filtered = build_candidate_segments(
        source_report, agent_output_id=agent_output_id
    )
    parser = StructuredOutputShadowParserV4_1(
        invoker, factor_vocabulary=factor_vocabulary
    )
    bundle = parser.parse_report_shadow_v4_1(
        source_report=source_report,
        run_id=run_id,
        ticker=ticker,
        agent=agent,
        agent_output_id=agent_output_id,
        candidate_segments=candidate_segments,
    )
    invocation = invoker.last_invocation
    forensic = build_rejected_forensic_record_v4_1(
        parser=parser,
        bundle=bundle,
        provider=gateway.provider,
        model=gateway.model_name,
        semantic_call_id=getattr(invocation.trace_handle, "call_id", None)
        if invocation is not None
        else None,
    )
    return (
        bundle,
        invoker,
        candidate_segments,
        list(parser.last_resolution_diagnostics),
        forensic,
    )


class Week2GatewaySemanticInvokerV4_2(SemanticInvoker):
    """Gateway seam for the additive v4.2 canonical-duplicate-occurrence
    protocol (Product Owner final simplification: removes v4.1's Provider-
    selected candidate-binding requirement from the active path entirely --
    see ``structured_output_shadow_v4_2.py``). Prompt/wire identity and
    Gateway plumbing are otherwise byte-identical to
    :class:`Week2GatewaySemanticInvokerV4`; the Gateway-level pre-validation
    closure below never builds or consults any candidate-hint span, matching
    the deterministic resolver it validates against.
    """

    def __init__(self, gateway: Week2LLMGateway, *, max_retries: int | None = None) -> None:
        self._gateway = gateway
        self._max_retries = (
            STRUCTURED_CLAIM_SHADOW_MAX_RETRIES if max_retries is None else max_retries
        )
        if (
            not isinstance(self._max_retries, int)
            or self._max_retries < 0
            or self._max_retries > STRUCTURED_CLAIM_SHADOW_MAX_RETRIES
        ):
            raise ValueError("structured_shadow_v4_2_max_retries_invalid")
        self.last_invocation: Week2LLMInvocation | None = None

    def invoke(self, *, prompt: str, request: Mapping[str, Any]) -> Any:
        def _gateway_validator(parsed: Mapping[str, Any]) -> Mapping[str, Any]:
            if not isinstance(parsed, Mapping):
                raise ValueError("shadow_gateway_v4_2_proposal_not_object")
            if not provider_proposal_shape_valid_v4_2(parsed):
                raise ValueError("shadow_gateway_v4_2_unapproved_output_field")
            canonical, _resolution_log = normalize_v4_2_proposal_to_canonical_bundle(
                parsed,
                source_report=str(request.get("agent_report") or ""),
                run_id=str(request.get("run_id") or ""),
                ticker=str(request.get("ticker") or ""),
                agent=str(request.get("agent") or ""),
                agent_output_id=str(request.get("agent_output_id") or ""),
            )
            proposal_with_ids = assign_deterministic_claim_ids(canonical)
            validation = validate_shadow_bundle(
                proposal_with_ids,
                source_report=str(request.get("agent_report") or ""),
                run_id=str(request.get("run_id") or ""),
                ticker=str(request.get("ticker") or ""),
                agent=str(request.get("agent") or ""),
                agent_output_id=str(request.get("agent_output_id") or ""),
                prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_2,
                prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256,
                factor_vocabulary=list(request.get("factor_vocabulary") or []),
                allowed_source_refs=(),
                allowed_candidate_segment_ids=None,
            )
            if not validation.valid:
                raise ValueError("shadow_gateway_v4_2_validation_rejected:" + ",".join(validation.reason_codes))
            return parsed

        invocation = self._gateway.invoke_prebuilt_json_prompt(
            task=STRUCTURED_CLAIM_SHADOW_TASK,
            prompt=prompt,
            prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_2,
            prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256,
            input_schema_version=str(
                request.get("input_schema_version") or SHADOW_INPUT_SCHEMA_VERSION_V4_2
            ),
            output_schema_version=SHADOW_PROVIDER_PROPOSAL_SCHEMA_VERSION_V4_2,
            payload_for_identity=request,
            validator=_gateway_validator,
            timeout_seconds=STRUCTURED_CLAIM_SHADOW_TIMEOUT_SECONDS,
            max_retries=self._max_retries,
            execution_policy_source=(
                STRUCTURED_CLAIM_SHADOW_EXECUTION_POLICY_SOURCE
                + "_v4_2_canonical_duplicate_occurrence"
            ),
        )
        self.last_invocation = invocation
        self._gateway.finalize_semantic_invocation(
            invocation,
            accepted=invocation.validation_accepted,
            fallback_reason=(
                None
                if invocation.validation_accepted
                else (invocation.error_code or "SHADOW_GATEWAY_VALIDATION_REJECTED")
            ),
        )
        if invocation.parsed_output is not None:
            return invocation.parsed_output
        raise RuntimeError(invocation.error_code or "WEEK2_LLM_PROVIDER_ERROR")


def run_real_provider_shadow_smoke_for_report_v4_2(
    *,
    gateway: Week2LLMGateway,
    source_report: str,
    run_id: str,
    ticker: str,
    agent: str,
    agent_output_id: str,
    factor_vocabulary: list[str],
    max_retries: int | None = None,
) -> tuple[
    dict[str, Any],
    Week2GatewaySemanticInvokerV4_2,
    list[dict[str, Any]],
    dict[str, Any] | None,
]:
    """v4.2 sibling of :func:`run_real_provider_shadow_smoke_for_report_v4_1`:
    same real-Provider, one-report-at-a-time call shape and rejected-
    forensic persistence. Never calls ``build_candidate_segments`` -- there
    is no candidate concept anywhere in the active v4.2 path, so the return
    shape is a 4-tuple, one element shorter than v4/v4.1's 4-/5-tuples
    (deliberately: there is no ``candidate_segments`` value to return).
    Returns ``(shadow_bundle, invoker, resolution_log, forensic)``.
    """

    invoker = Week2GatewaySemanticInvokerV4_2(gateway, max_retries=max_retries)
    parser = StructuredOutputShadowParserV4_2(invoker, factor_vocabulary=factor_vocabulary)
    bundle = parser.parse_report_shadow_v4_2(
        source_report=source_report,
        run_id=run_id,
        ticker=ticker,
        agent=agent,
        agent_output_id=agent_output_id,
    )
    invocation = invoker.last_invocation
    forensic = build_rejected_forensic_record_v4_2(
        parser=parser,
        bundle=bundle,
        provider=gateway.provider,
        model=gateway.model_name,
        semantic_call_id=getattr(invocation.trace_handle, "call_id", None)
        if invocation is not None
        else None,
    )
    return (
        bundle,
        invoker,
        list(parser.last_resolution_log),
        forensic,
    )


__all__ = [
    "STRUCTURED_CLAIM_SHADOW_TASK",
    "ProviderSmokeAuthorizationError",
    "ProviderSmokeGatewayInfo",
    "Week2GatewaySemanticInvoker",
    "Week2GatewaySemanticInvokerV2",
    "Week2GatewaySemanticInvokerV3",
    "Week2GatewaySemanticInvokerV4",
    "Week2GatewaySemanticInvokerV4_1",
    "Week2GatewaySemanticInvokerV4_2",
    "SEMANTIC_TASK_PROFILE_IDS",
    "STRUCTURED_CLAIM_SHADOW_EXECUTION_POLICY_SOURCE",
    "STRUCTURED_CLAIM_SHADOW_MAX_RETRIES",
    "STRUCTURED_CLAIM_SHADOW_TIMEOUT_SECONDS",
    "build_phase1_master_provider_gateway",
    "build_real_provider_gateway",
    "profile_id_for_semantic_task",
    "run_real_provider_shadow_smoke_for_report",
    "run_real_provider_shadow_smoke_for_report_v2",
    "run_real_provider_shadow_smoke_for_report_v3",
    "run_real_provider_shadow_smoke_for_report_v4",
    "run_real_provider_shadow_smoke_for_report_v4_1",
    "run_real_provider_shadow_smoke_for_report_v4_2",
]
