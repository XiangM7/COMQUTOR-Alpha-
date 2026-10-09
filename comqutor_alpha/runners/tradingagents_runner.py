"""Guarded wrappers for running the original TradingAgents research pipeline.

Two real-execution entrypoints live here:

- ``run_original_tradingagents_research``: the legacy one-shot
  ``graph.propagate()`` path, preserved unchanged for direct Python callers
  and the injected-``final_state`` test seam.
- ``run_streaming_tradingagents_research``: the W7 API path. It builds the
  same ``TradingAgentsGraph``, but drives it through LangGraph's native
  ``graph.graph.stream(...)`` so genuinely-completed agent milestones
  (analyst reports, the research debate, the trading plan, the risk review)
  can advance real progress telemetry as they happen. The final state is
  still written through the exact same official
  ``save_comqutor_run_outputs`` writer.

The public HTTP analyst vocabulary uses ``sentiment``; TradingAgents' graph
wiring uses ``social`` for the same analyst. That mapping happens *only*
here, immediately before ``TradingAgentsGraph`` construction -- metadata,
HTTP responses, run history, and the web UI keep saying ``sentiment``, and
``social`` never leaks outward.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
from collections.abc import Mapping
from pathlib import Path

from comqutor_alpha.research_progress import (
    PUBLIC_ANALYST_ORDER,
    normalize_public_analysts,
)
from comqutor_alpha.run_provider_stop import RunProviderStopped, run_provider_stop
from comqutor_alpha.runners.diagnostics import (
    TradingAgentsDiagnosticCallback,
    TradingAgentsUsageStatsCallback,
    summarize_usage_records,
)
from comqutor_alpha.runners.request_budget import (
    RequestBudgetGuard,
    ResearchAgentBudgetExceeded,
    wrap_chat_model_with_budget_guard,
)
from comqutor_alpha.storage.file_store import resolve_output_root

logger = logging.getLogger(__name__)


def _deepseek_thinking_scope_for_config(config):
    """Scope DeepSeek's thinking-mode request injection (see
    ``comqutor_alpha.llm.deepseek_smoke``) around ``TradingAgentsGraph``
    construction -- a no-op context manager for every other provider.

    Only the *construction* moment matters: ``OpenAIClient.get_llm()``
    reads the provider registry's current ``chat_class`` once, at
    construction time, to decide which client class to instantiate: the
    constructed LLM client instance's class (and therefore its
    ``_get_request_payload`` override) is then fixed for that instance's
    whole lifetime regardless of the registry's state afterward. So the
    scope only needs to wrap the ``TradingAgentsGraph(...)`` call itself,
    not the run's entire propagate/stream duration.

    Raises ``ValueError`` immediately (never silently swallowed) if
    ``TRADINGAGENTS_DEEPSEEK_THINKING`` is set to anything other than
    "enabled"/"disabled" -- a bad thinking-mode value must fail the run
    loudly, exactly like every other real-run configuration error here.
    """
    provider = str((config or {}).get("llm_provider") or "").strip().lower()
    if provider != "deepseek":
        return contextlib.nullcontext()

    from comqutor_alpha.llm.deepseek_smoke import (
        deepseek_thinking_scope,
        resolve_deepseek_thinking_value,
    )

    mode = resolve_deepseek_thinking_value(config.get("deepseek_thinking"))
    return deepseek_thinking_scope(mode)

# Public HTTP analyst name -> TradingAgents internal analyst key, in the
# frozen canonical public order (market, sentiment, news, fundamentals).
PUBLIC_TO_INTERNAL_ANALYSTS: dict[str, str] = {
    "market": "market",
    "sentiment": "social",
    "news": "news",
    "fundamentals": "fundamentals",
}

# TradingAgents internal analyst key -> the final_state report field whose
# first non-empty appearance marks that analyst as genuinely complete.
INTERNAL_ANALYST_REPORT_KEYS: dict[str, str] = {
    "market": "market_report",
    "social": "sentiment_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
}

## Public -> Internal Analyst Mapping
def map_public_analysts_to_internal(selected_analysts) -> tuple[list[str], list[str]]:
    """(public_canonical, internal) analyst lists for one run.

    Deduplicates, enforces the canonical public order, rejects unknown
    names, and requires at least one analyst. ``sentiment`` becomes
    ``social`` on the internal side only -- the two can never both reach the
    same TradingAgentsGraph because ``social`` is not a valid *public* name
    in the first place.
    """
    try:
        public_canonical = normalize_public_analysts(
            selected_analysts,
            default_if_missing=False,
        )
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    internal = [PUBLIC_TO_INTERNAL_ANALYSTS[name] for name in public_canonical]
    return public_canonical, internal


def _require_payload_value(payload, key):
    value = payload.get(key)
    if value in (None, "", []):
        raise RuntimeError(f"Missing required payload field for real TradingAgents run: {key}")
    return value

## Legacy One-Shot Research
def run_original_tradingagents_research(payload, output_root="outputs/runs"):
    """Run original TradingAgents only when explicitly requested.

    Tests should inject a fake runner or use ``offline_raw_agent_outputs``.
    A real run may call LLM/data providers and therefore requires the caller to
    opt in with ``allow_real_tradingagents_run=True`` and provide config.
    """
    payload = payload or {}

    if payload.get("final_state") is not None:
        from comqutor_alpha.adapters.tradingagents_output_writer import (
            save_comqutor_run_outputs,
        )

        return save_comqutor_run_outputs(
            final_state=payload.get("final_state"),
            ticker=_require_payload_value(payload, "ticker"),
            config=payload.get("config") or {},
            selected_analysts=payload.get("selected_analysts") or [],
            analysis_date=payload.get("analysis_date"),
            output_root=output_root,
        )

    if payload.get("allow_real_tradingagents_run") is not True:
        raise RuntimeError(
            "Real TradingAgents execution is disabled by default. Use "
            "offline_raw_agent_outputs for local tests, inject a fake runner, or set "
            "allow_real_tradingagents_run=True with a configured environment."
        )

    ticker = _require_payload_value(payload, "ticker")
    analysis_date = _require_payload_value(payload, "analysis_date")
    public_analysts, selected_analysts = map_public_analysts_to_internal(
        payload.get("selected_analysts") or list(PUBLIC_ANALYST_ORDER)
    )
    asset_type = str(payload.get("asset_type") or "stock")
    config = payload.get("config")
    if not isinstance(config, dict):
        raise RuntimeError(
            "Real TradingAgents execution requires payload['config'] with provider/model/API "
            "configuration. The API wrapper does not read or modify .env."
        )

    try:
        from comqutor_alpha.adapters.tradingagents_output_writer import (
            save_comqutor_run_outputs,
        )
        from tradingagents.dataflows.source_capture import source_capture_scope
        from tradingagents.graph.trading_graph import TradingAgentsGraph
    except Exception as exc:
        raise RuntimeError(f"Unable to import TradingAgents graph entrypoint: {exc}") from exc

    with _deepseek_thinking_scope_for_config(config):
        graph = TradingAgentsGraph(selected_analysts, config=config, debug=False)

    from comqutor_alpha.llm.canonical_prompt_injection import (
        comqutor_structure_output_contract_scope,
    )

    # John MVP Final Gap Closure -- Structured External Source Traceability:
    # scoped around the exact same propagate() call, nothing else -- see
    # tradingagents.dataflows.source_capture's own docstring for why this
    # can never change graph.propagate()'s return value.
    with comqutor_structure_output_contract_scope(), source_capture_scope() as captured_sources:
        final_state, _processed_signal = graph.propagate(
            str(ticker),
            str(analysis_date),
            asset_type=asset_type,
        )
    run_dir = save_comqutor_run_outputs(
        final_state=final_state,
        ticker=ticker,
        config=config,
        selected_analysts=public_analysts,
        analysis_date=analysis_date,
        output_root=Path(output_root),
        captured_sources=captured_sources,
    )
    return run_dir

## Streaming Graph Factory
def _default_streaming_graph_factory(internal_analysts, config):
    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
    except Exception as exc:
        raise RuntimeError(f"Unable to import TradingAgents graph entrypoint: {exc}") from exc
    with _deepseek_thinking_scope_for_config(config):
        return TradingAgentsGraph(internal_analysts, config=config, debug=False)

## Report Streaming Milestones
def _report_stream_milestones(final_state, public_analysts, progress_reporter, reached):
    """Advance progress for every milestone whose content genuinely appeared
    for the first time in the merged state. ``reached`` deduplicates across
    chunks so a repeated chunk never advances anything twice."""
    if progress_reporter is None:
        return

    for public_name in public_analysts:
        report_key = INTERNAL_ANALYST_REPORT_KEYS[PUBLIC_TO_INTERNAL_ANALYSTS[public_name]]
        marker = f"analyst:{public_name}"
        if marker in reached:
            continue
        value = final_state.get(report_key)
        if isinstance(value, str) and value.strip():
            reached.add(marker)
            progress_reporter.record_analyst_completed(public_name)

    debate_state = final_state.get("investment_debate_state")
    if (
        "research_debate" not in reached
        and isinstance(debate_state, Mapping)
        and str(debate_state.get("judge_decision") or "").strip()
    ):
        reached.add("research_debate")
        progress_reporter.record_stage("research_debate")

    trader_plan = final_state.get("trader_investment_plan")
    if "trading_plan" not in reached and isinstance(trader_plan, str) and trader_plan.strip():
        reached.add("trading_plan")
        progress_reporter.record_stage("trading_plan")

    risk_state = final_state.get("risk_debate_state")
    if (
        "risk_review" not in reached
        and isinstance(risk_state, Mapping)
        and str(risk_state.get("judge_decision") or "").strip()
    ):
        reached.add("risk_review")
        progress_reporter.record_stage("risk_review")

## Relocate run outputs to claimed run_id
def _relocate_run_outputs(temp_run_dir, target_run_id, output_root):
    """Move the writer's freshly-created run directory to the lifecycle's
    already-claimed run_id and rewrite the embedded run_id references, so
    artifacts, the research_runs row, progress telemetry, and every GET
    route all agree on one run_id. The artifact *content* is untouched --
    only identity fields are rewritten."""
    from comqutor_alpha.storage.file_store import (
        load_json_record,
        load_json_record_if_exists,
        run_dir_for,
        save_json_record,
        validate_run_id_for_path,
    )

    temp_run_id = validate_run_id_for_path(Path(temp_run_dir).name)
    safe_target = validate_run_id_for_path(str(target_run_id))
    if temp_run_id == safe_target:
        return Path(temp_run_dir)

    target_dir = run_dir_for(safe_target, output_root)
    if target_dir.exists():
        raise RuntimeError("Target run directory already exists for this run_id.")
    Path(temp_run_dir).rename(target_dir)

    metadata = load_json_record(safe_target, "metadata.json", output_root=output_root)
    metadata["run_id"] = safe_target
    save_json_record(safe_target, "metadata.json", metadata, output_root=output_root)

    raw_payload = load_json_record(safe_target, "raw_agent_outputs.json", output_root=output_root)
    raw_payload["run_id"] = safe_target
    old_prefix = f"{temp_run_id}:"
    new_prefix = f"{safe_target}:"
    for record in raw_payload.get("agent_outputs") or []:
        if not isinstance(record, dict):
            continue
        record["run_id"] = safe_target
        agent_output_id = record.get("agent_output_id")
        if isinstance(agent_output_id, str) and agent_output_id.startswith(old_prefix):
            record["agent_output_id"] = new_prefix + agent_output_id[len(old_prefix):]
    save_json_record(safe_target, "raw_agent_outputs.json", raw_payload, output_root=output_root)

    # John MVP Final Gap Closure -- Structured External Source
    # Traceability: source_registry.json (when a run actually captured any
    # genuine sources) is written by the same pre-relocation
    # save_comqutor_run_outputs call as metadata.json/raw_agent_outputs.json
    # above, so it carries the same stale temp run_id unless rewritten here
    # too. Optional artifact -- a run with no captured sources never wrote
    # one, so this is a no-op for it, never an error. load_json_record_if_exists
    # returns {} (falsy) rather than None when the file is absent -- `if
    # registry:` (not `isinstance(registry, dict)`, which {} also satisfies)
    # is required to avoid writing a bogus {"run_id": ...}-only file here.
    registry = load_json_record_if_exists(safe_target, "source_registry.json", output_root=output_root)
    if registry:
        registry["run_id"] = safe_target
        save_json_record(safe_target, "source_registry.json", registry, output_root=output_root)

    return target_dir

## Streaming Research
def run_streaming_tradingagents_research(
    payload,
    output_root="outputs/runs",
    *,
    progress_reporter=None,
    graph_factory=None,
):
    """W7 real-execution path: stream the TradingAgents graph chunk by
    chunk, advancing real progress as each agent milestone genuinely
    completes, then persist the merged final state through the official
    ``save_comqutor_run_outputs`` writer under the lifecycle's claimed
    run_id.

    Requires the same server-only opt-in as the legacy path
    (``allow_real_tradingagents_run=True`` plus a server-built ``config``)
    -- an HTTP request can never set either. ``graph_factory`` is a test
    seam so the streaming/merge/progress logic is fully testable with a
    fake graph, without any provider call.
    """
    payload = payload or {}
    if payload.get("allow_real_tradingagents_run") is not True:
        raise RuntimeError(
            "Real TradingAgents execution is disabled by default. Use "
            "offline_raw_agent_outputs for local tests, inject a fake runner, or set "
            "allow_real_tradingagents_run=True with a configured environment."
        )

    ticker = _require_payload_value(payload, "ticker")
    analysis_date = _require_payload_value(payload, "analysis_date")
    config = payload.get("config")
    if not isinstance(config, dict):
        raise RuntimeError(
            "Real TradingAgents execution requires payload['config'] with provider/model "
            "configuration built by the server. The API wrapper does not read or modify .env."
        )

    public_analysts, internal_analysts = map_public_analysts_to_internal(
        payload.get("selected_analysts") or list(PUBLIC_ANALYST_ORDER)
    )
    asset_type = str(_require_payload_value(payload, "asset_type"))
    # Read early for the usage-stats callback's own correlation field --
    # pure dict read, no effect on the relocation logic near the end of
    # this function which still independently re-reads payload["run_id"].
    run_id_for_stats = payload.get("run_id") or f"{ticker}:{analysis_date}"

    try:
        from comqutor_alpha.adapters.tradingagents_output_writer import (
            save_comqutor_run_outputs,
        )
    except Exception as exc:
        raise RuntimeError(f"Unable to import COMQUTOR output writer: {exc}") from exc

    # Observability-only (John Requirement B follow-up, docs/audit_artifacts/
    # v0_2_instrument_identity_timeout_fix.json): the prior root-cause task
    # proved the ~903s failure occurs somewhere between here and
    # STREAM_LOOP_START, without pinning the exact step. These markers close
    # that remaining gap -- if a future run fails again in this setup phase,
    # the log shows exactly which step was in flight.
    _setup_start = time.monotonic()
    logger.info(
        "tradingagents_diagnostic stage=GRAPH_CONSTRUCTION_START run=%s:%s elapsed=0.0s",
        ticker, analysis_date,
    )

    # Real, enforced Research Agent request-count cap (2026-09-30, fifth
    # follow-up round) -- opt-in via payload["research_agent_max_actual_requests"]
    # so every existing caller/test that never sets this key is completely
    # unaffected. CRITICAL, empirically-confirmed prerequisite: the
    # underlying chat client's OWN max_retries must be forced to 0 BEFORE
    # construction, never patched afterward -- a real transport-level test
    # (see tests/test_request_budget.py's transport-boundary suite) proved
    # that mutating an already-constructed ChatOpenAI's .max_retries field
    # does NOT change its real retry behavior (the underlying openai SDK
    # client is already built with the original value baked in), and that
    # the SDK's own default max_retries causes 3 real transport calls for
    # what LangChain's own .invoke() sees as one -- invisible to any
    # wrapper sitting above it. Forcing max_retries=0 here, before
    # TradingAgentsGraph ever constructs the real client, is what makes
    # this wrapper's own retry loop (max_retries=research_agent_max_retries
    # below) the ONE AND ONLY place a retry happens, with full visibility.
    # TRADINGAGENTS_MAX_RETRIES (an operator's own config value) is
    # deliberately overridden here, never silently combined with the
    # guard's own retry count -- avoiding exactly the "hidden or duplicate
    # retry" failure mode this round's own task explicitly warned about.
    research_agent_max_actual_requests = payload.get("research_agent_max_actual_requests")
    graph_construction_config = config
    if research_agent_max_actual_requests is not None:
        graph_construction_config = {**config, "max_retries": 0}

    graph = (graph_factory or _default_streaming_graph_factory)(internal_analysts, graph_construction_config)
    graph.ticker = str(ticker)
    logger.info(
        "tradingagents_diagnostic stage=GRAPH_CONSTRUCTION_END run=%s:%s elapsed=%.3fs",
        ticker, analysis_date, time.monotonic() - _setup_start,
    )

    # Both LLM instances TradingAgentsGraph already constructed (with their
    # own underlying client's max_retries forced to 0 above) are wrapped IN
    # PLACE (see comqutor_alpha.runners.request_budget's own docstring for
    # why a callback cannot do this -- confirmed empirically that a
    # callback exception here would be swallowed and the real call would
    # proceed anyway). deep_thinking_llm/quick_thinking_llm share ONE
    # guard, since the budget is a total across the whole run, not per-model.
    research_agent_budget_guard: RequestBudgetGuard | None = None
    # 2026-10-08 (T4 round 28): the run's provider-refusal stop, shared with this run's Week 2 gateway (keyed by the
    # claimed run_id); checked by the guard before every request.
    provider_stop = run_provider_stop(payload["run_id"]) if payload.get("run_id") else None
    if research_agent_max_actual_requests is not None:
        research_agent_budget_guard = RequestBudgetGuard(
            int(research_agent_max_actual_requests), provider_stop=provider_stop
        )
        research_agent_max_retries = int(payload.get("research_agent_max_retries") or 0)
        for llm_attr in ("deep_thinking_llm", "quick_thinking_llm"):
            llm = getattr(graph, llm_attr, None)
            if llm is not None:
                wrap_chat_model_with_budget_guard(
                    llm, research_agent_budget_guard, max_retries=research_agent_max_retries
                )

    resolve_pending = getattr(graph, "_resolve_pending_entries", None)
    if callable(resolve_pending):
        logger.info(
            "tradingagents_diagnostic stage=PENDING_ENTRIES_START run=%s:%s elapsed=%.3fs",
            ticker, analysis_date, time.monotonic() - _setup_start,
        )
        resolve_pending(str(ticker))
        logger.info(
            "tradingagents_diagnostic stage=PENDING_ENTRIES_END run=%s:%s elapsed=%.3fs",
            ticker, analysis_date, time.monotonic() - _setup_start,
        )

    checkpointer_ctx = None
    checkpointer_entered = False
    checkpoint_enabled = bool(config.get("checkpoint_enabled"))
    try:
        if checkpoint_enabled:
            from tradingagents.graph.checkpointer import get_checkpointer, thread_id

            checkpointer_ctx = get_checkpointer(config["data_cache_dir"], str(ticker))
            graph._checkpointer_ctx = checkpointer_ctx
            saver = checkpointer_ctx.__enter__()
            checkpointer_entered = True
            graph.graph = graph.workflow.compile(checkpointer=saver)

        logger.info(
            "tradingagents_diagnostic stage=PAST_CONTEXT_START run=%s:%s elapsed=%.3fs",
            ticker, analysis_date, time.monotonic() - _setup_start,
        )
        memory_log = getattr(graph, "memory_log", None)
        get_past_context = getattr(memory_log, "get_past_context", None)
        past_context = str(get_past_context(str(ticker)) or "") if callable(get_past_context) else ""
        logger.info(
            "tradingagents_diagnostic stage=PAST_CONTEXT_END run=%s:%s elapsed=%.3fs",
            ticker, analysis_date, time.monotonic() - _setup_start,
        )

        logger.info(
            "tradingagents_diagnostic stage=INSTRUMENT_CONTEXT_START run=%s:%s elapsed=%.3fs",
            ticker, analysis_date, time.monotonic() - _setup_start,
        )
        resolve_context = getattr(graph, "resolve_instrument_context", None)
        instrument_context = (
            str(resolve_context(str(ticker), asset_type) or "")
            if callable(resolve_context)
            else ""
        )
        logger.info(
            "tradingagents_diagnostic stage=INSTRUMENT_CONTEXT_END run=%s:%s elapsed=%.3fs",
            ticker, analysis_date, time.monotonic() - _setup_start,
        )

        init_state = graph.propagator.create_initial_state(
            str(ticker),
            str(analysis_date),
            asset_type=asset_type,
            past_context=past_context,
            instrument_context=instrument_context,
        )
        # Observability-only (John Requirement B root-cause instrumentation,
        # docs/audit_artifacts/v0_2_tradingagents_timeout_root_cause.json): a
        # passive diagnostic callback so a stall inside the stream loop below
        # shows exactly which chain/tool/LLM call was in flight and for how
        # long. It only logs (never raises, never inspects prompt/tool
        # content beyond name/count) -- see comqutor_alpha.runners.diagnostics.
        diagnostic_callback = TradingAgentsDiagnosticCallback(
            run_label=f"{ticker}:{analysis_date}"
        )
        # T4 request-level statistics offline prep (this round): a second,
        # additive callback alongside the diagnostic one above -- same real
        # call boundary, never replacing it. Records are flushed to
        # tradingagents_llm_calls.jsonl in the final run directory after
        # save_comqutor_run_outputs below, once that directory is known.
        usage_stats_callback = TradingAgentsUsageStatsCallback(
            run_id=run_id_for_stats, agent_label=f"{ticker}:{analysis_date}"
        )
        stream_args = graph.propagator.get_graph_args()
        stream_args.setdefault("config", {}).setdefault("callbacks", []).extend(
            [diagnostic_callback, usage_stats_callback]
        )
        if checkpoint_enabled:
            stream_args.setdefault("config", {}).setdefault("configurable", {})[
                "thread_id"
            ] = thread_id(str(ticker), str(analysis_date))

        if progress_reporter is not None:
            progress_reporter.record_analyst_started(public_analysts[0])

        # stream_mode="values" chunks are cumulative state snapshots;
        # merging with dict.update preserves the same final state as invoke.
        from comqutor_alpha.llm.canonical_prompt_injection import (
            comqutor_structure_output_contract_scope,
        )

        from tradingagents.dataflows.source_capture import source_capture_scope

        final_state: dict = {}
        reached: set[str] = set()
        stream_start = time.monotonic()
        chunk_count = 0
        captured_sources: list = []
        logger.info(
            "tradingagents_diagnostic stage=STREAM_LOOP_START run=%s:%s elapsed=0.0s",
            ticker, analysis_date,
        )

        def _partial_save_on_stop(exc: BaseException) -> None:
            """Best-effort partial save when the run is stopped -- by the research-agent request budget or (T4
            round 28) by a provider refusal (HTTP 401/403/429): whatever real chunks arrived before the stop are
            still real, already-computed research output -- never discarded just because the run didn't reach its
            own natural end -- and so are the already-collected usage records of the requests that were sent. A
            failure while saving must never mask the original stop."""
            stop_trigger = provider_stop.triggered if provider_stop is not None else None
            stopped_reason = (
                "RESEARCH_AGENT_REQUEST_BUDGET_EXCEEDED"
                if isinstance(exc, ResearchAgentBudgetExceeded)
                else "PROVIDER_REFUSAL_RUN_STOPPED"
            )
            logger.error(
                "tradingagents_diagnostic stage=STREAM_LOOP_%s "
                "run=%s:%s elapsed=%.3fs chunks_received=%d actual_requests_made=%s "
                "max_actual_requests=%s reason=%s",
                stopped_reason, ticker, analysis_date, time.monotonic() - stream_start, chunk_count,
                research_agent_budget_guard.actual_requests_made if research_agent_budget_guard else None,
                research_agent_budget_guard.max_actual_requests if research_agent_budget_guard else None,
                str(exc),
            )
            partial_run_dir = None
            if final_state:
                try:
                    resolved_output_root = resolve_output_root(output_root)
                    partial_run_dir = save_comqutor_run_outputs(
                        final_state=final_state,
                        ticker=ticker,
                        config=config,
                        selected_analysts=public_analysts,
                        analysis_date=analysis_date,
                        output_root=resolved_output_root,
                        captured_sources=captured_sources,
                    )
                    # Same claimed-run_id relocation the normal completion
                    # path applies below -- a partial save is discoverable by
                    # its own real run_id, not a throwaway temp directory.
                    claimed_run_id = payload.get("run_id")
                    if claimed_run_id:
                        partial_run_dir = _relocate_run_outputs(
                            partial_run_dir, claimed_run_id, resolved_output_root
                        )
                    metadata_path = Path(partial_run_dir) / "metadata.json"
                    if metadata_path.exists():
                        metadata = json.loads(metadata_path.read_text())
                        metadata["stopped_reason"] = stopped_reason
                        metadata["stopped_detail"] = str(exc)
                        if stop_trigger is not None:
                            metadata["provider_stop"] = stop_trigger
                        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True))
                    logger.error(
                        "tradingagents_diagnostic stage=PARTIAL_SAVE_ON_%s "
                        "run=%s:%s partial_run_dir=%s",
                        stopped_reason, ticker, analysis_date, partial_run_dir,
                    )
                except Exception:
                    partial_run_dir = None
                    logger.exception(
                        "tradingagents_diagnostic stage=PARTIAL_SAVE_ON_STOP_FAILED "
                        "run=%s:%s -- the original stop is unaffected",
                        ticker, analysis_date,
                    )
            # Provider stop only (a budget stop keeps its earlier behavior exactly): the stop record and the usage
            # records of the requests that were sent are kept even when no agent output could be saved -- then in the
            # claimed run's own directory.
            if stop_trigger is None:
                return
            try:
                target_dir = Path(partial_run_dir) if partial_run_dir else None
                if target_dir is None and payload.get("run_id"):
                    target_dir = Path(resolve_output_root(output_root)) / str(payload["run_id"])
                if target_dir is not None:
                    target_dir.mkdir(parents=True, exist_ok=True)
                    provider_stop.attach_artifact_dir(target_dir)
                    with (target_dir / "tradingagents_llm_calls.jsonl").open("w", encoding="utf-8") as handle:
                        for record in usage_stats_callback.records:
                            handle.write(json.dumps(record, sort_keys=True) + "\n")
            except Exception:
                logger.exception(
                    "tradingagents_diagnostic stage=STOP_RECORD_SAVE_FAILED run=%s:%s", ticker, analysis_date
                )

        try:
            # John MVP Final Gap Closure -- Structured External Source
            # Traceability: scoped around the exact same stream() call,
            # nothing else -- never changes a single chunk's content.
            with comqutor_structure_output_contract_scope(), source_capture_scope() as sink:
                captured_sources = sink
                for chunk in graph.graph.stream(init_state, **stream_args):
                    if isinstance(chunk, Mapping):
                        chunk_count += 1
                        final_state.update(chunk)
                        logger.info(
                            "tradingagents_diagnostic stage=STREAM_CHUNK run=%s:%s "
                            "chunk_index=%d elapsed=%.3fs chunk_keys=%s",
                            ticker, analysis_date, chunk_count,
                            time.monotonic() - stream_start, sorted(chunk.keys()),
                        )
                        _report_stream_milestones(
                            final_state,
                            public_analysts,
                            progress_reporter,
                            reached,
                        )
        except (ResearchAgentBudgetExceeded, RunProviderStopped) as exc:
            _partial_save_on_stop(exc)
            raise
        except Exception as exc:
            if provider_stop is not None and provider_stop.triggered is not None:
                # 2026-10-08 (T4 round 28): the provider refused (401/403/429) and the refusal itself ended the
                # stream -- saved exactly like a budget stop
                _partial_save_on_stop(exc)
            logger.error(
                "tradingagents_diagnostic stage=STREAM_LOOP_ERROR run=%s:%s "
                "elapsed=%.3fs chunks_received=%d exc_type=%s exc_message=%s "
                "chained_cause=%s",
                ticker, analysis_date, time.monotonic() - stream_start,
                chunk_count, type(exc).__name__, str(exc),
                repr(exc.__cause__) if exc.__cause__ is not None else None,
                exc_info=True,
            )
            raise

        if not final_state:
            raise RuntimeError("TradingAgents stream produced no state.")

        graph.curr_state = final_state
        log_state = getattr(graph, "_log_state", None)
        if callable(log_state):
            log_state(str(analysis_date), final_state)

        store_decision = getattr(memory_log, "store_decision", None)
        if callable(store_decision):
            store_decision(
                ticker=str(ticker),
                trade_date=str(analysis_date),
                final_trade_decision=final_state["final_trade_decision"],
            )

        if checkpoint_enabled:
            from tradingagents.graph.checkpointer import clear_checkpoint

            clear_checkpoint(
                config["data_cache_dir"],
                str(ticker),
                str(analysis_date),
            )

        process_signal = getattr(graph, "process_signal", None)
        if callable(process_signal):
            process_signal(final_state["final_trade_decision"])
    finally:
        if checkpointer_ctx is not None:
            if checkpointer_entered:
                checkpointer_ctx.__exit__(None, None, None)
            graph._checkpointer_ctx = None
            graph.graph = graph.workflow.compile()

    resolved_output_root = resolve_output_root(output_root)
    run_dir = save_comqutor_run_outputs(
        final_state=final_state,
        ticker=ticker,
        config=config,
        selected_analysts=public_analysts,
        analysis_date=analysis_date,
        output_root=resolved_output_root,
        captured_sources=captured_sources,
    )

    claimed_run_id = payload.get("run_id")
    if claimed_run_id:
        run_dir = _relocate_run_outputs(run_dir, claimed_run_id, resolved_output_root)

    # T4 request-level statistics offline prep (this round): write the
    # usage-stats callback's own real, already-collected records only after
    # run_dir reaches its final, post-relocation location -- avoids needing
    # a second rewrite pass the way _relocate_run_outputs performs for
    # metadata.json/raw_agent_outputs.json above. Best-effort: a failure
    # here must never fail a real research run that otherwise succeeded.
    try:
        usage_records = usage_stats_callback.records
        run_dir_path = Path(run_dir)
        with (run_dir_path / "tradingagents_llm_calls.jsonl").open("w", encoding="utf-8") as handle:
            for record in usage_records:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
        summary = summarize_usage_records(usage_records)
        (run_dir_path / "tradingagents_llm_usage_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
        )
    except Exception:
        logger.exception(
            "tradingagents_usage_stats_flush_failed run=%s:%s -- research run output is unaffected",
            ticker, analysis_date,
        )

    return run_dir
