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

from collections.abc import Mapping
from pathlib import Path

# Public HTTP analyst name -> TradingAgents internal analyst key, in the
# frozen canonical public order (market, sentiment, news, fundamentals).
PUBLIC_TO_INTERNAL_ANALYSTS: dict[str, str] = {
    "market": "market",
    "sentiment": "social",
    "news": "news",
    "fundamentals": "fundamentals",
}

_CANONICAL_PUBLIC_ORDER: tuple[str, ...] = ("market", "sentiment", "news", "fundamentals")

# TradingAgents internal analyst key -> the final_state report field whose
# first non-empty appearance marks that analyst as genuinely complete.
INTERNAL_ANALYST_REPORT_KEYS: dict[str, str] = {
    "market": "market_report",
    "social": "sentiment_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
}


def map_public_analysts_to_internal(selected_analysts) -> tuple[list[str], list[str]]:
    """(public_canonical, internal) analyst lists for one run.

    Deduplicates, enforces the canonical public order, rejects unknown
    names, and requires at least one analyst. ``sentiment`` becomes
    ``social`` on the internal side only -- the two can never both reach the
    same TradingAgentsGraph because ``social`` is not a valid *public* name
    in the first place.
    """
    requested = []
    seen = set()
    for item in selected_analysts or []:
        name = str(item or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        requested.append(name)

    unknown = [name for name in requested if name not in PUBLIC_TO_INTERNAL_ANALYSTS]
    if unknown:
        raise RuntimeError(
            "INVALID_ANALYST_SELECTION: selected_analysts contains an unsupported analyst"
        )
    public_canonical = [name for name in _CANONICAL_PUBLIC_ORDER if name in seen]
    if not public_canonical:
        raise RuntimeError("INVALID_ANALYST_SELECTION: at least one analyst must be selected")
    internal = [PUBLIC_TO_INTERNAL_ANALYSTS[name] for name in public_canonical]
    return public_canonical, internal


def _require_payload_value(payload, key):
    value = payload.get(key)
    if value in (None, "", []):
        raise RuntimeError(f"Missing required payload field for real TradingAgents run: {key}")
    return value


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
    selected_analysts = payload.get("selected_analysts") or ["market", "news", "fundamentals", "sentiment"]
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
        from tradingagents.graph.trading_graph import TradingAgentsGraph
    except Exception as exc:
        raise RuntimeError(f"Unable to import TradingAgents graph entrypoint: {exc}") from exc

    graph = TradingAgentsGraph(selected_analysts, config=config, debug=False)
    final_state, _processed_signal = graph.propagate(str(ticker), str(analysis_date))
    run_dir = save_comqutor_run_outputs(
        final_state=final_state,
        ticker=ticker,
        config=config,
        selected_analysts=selected_analysts,
        analysis_date=analysis_date,
        output_root=Path(output_root),
    )
    return run_dir


def _default_streaming_graph_factory(internal_analysts, config):
    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
    except Exception as exc:
        raise RuntimeError(f"Unable to import TradingAgents graph entrypoint: {exc}") from exc
    return TradingAgentsGraph(internal_analysts, config=config, debug=False)


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


def _relocate_run_outputs(temp_run_dir, target_run_id, output_root):
    """Move the writer's freshly-created run directory to the lifecycle's
    already-claimed run_id and rewrite the embedded run_id references, so
    artifacts, the research_runs row, progress telemetry, and every GET
    route all agree on one run_id. The artifact *content* is untouched --
    only identity fields are rewritten."""
    from comqutor_alpha.storage.file_store import (
        load_json_record,
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
    return target_dir


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
        payload.get("selected_analysts") or list(_CANONICAL_PUBLIC_ORDER)
    )

    try:
        from comqutor_alpha.adapters.tradingagents_output_writer import (
            save_comqutor_run_outputs,
        )
    except Exception as exc:
        raise RuntimeError(f"Unable to import COMQUTOR output writer: {exc}") from exc

    graph = (graph_factory or _default_streaming_graph_factory)(internal_analysts, config)

    instrument_context = ""
    resolve_context = getattr(graph, "resolve_instrument_context", None)
    if callable(resolve_context):
        try:
            instrument_context = str(resolve_context(str(ticker)) or "")
        except Exception:
            # Deterministic identity resolution is fail-open in TradingAgents
            # itself; a lookup failure degrades to ticker-only context.
            instrument_context = ""

    init_state = graph.propagator.create_initial_state(
        str(ticker), str(analysis_date), instrument_context=instrument_context
    )
    stream_args = graph.propagator.get_graph_args()

    # stream_mode="values" chunks are cumulative state snapshots; merging
    # with dict.update matches TradingAgentsGraph's own debug-path merge
    # rule, so the final merged state equals what graph.invoke would return.
    final_state: dict = {}
    reached: set[str] = set()
    for chunk in graph.graph.stream(init_state, **stream_args):
        if isinstance(chunk, Mapping):
            final_state.update(chunk)
            _report_stream_milestones(final_state, public_analysts, progress_reporter, reached)

    if not final_state:
        raise RuntimeError("TradingAgents stream produced no state.")

    run_dir = save_comqutor_run_outputs(
        final_state=final_state,
        ticker=ticker,
        config=config,
        selected_analysts=public_analysts,
        analysis_date=analysis_date,
        output_root=Path(output_root),
    )

    claimed_run_id = payload.get("run_id")
    if claimed_run_id:
        run_dir = _relocate_run_outputs(run_dir, claimed_run_id, output_root)
    return run_dir
