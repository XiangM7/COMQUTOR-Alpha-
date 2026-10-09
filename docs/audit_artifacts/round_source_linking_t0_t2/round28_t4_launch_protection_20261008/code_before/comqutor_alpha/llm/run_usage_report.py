"""Unified per-run LLM usage and cost report (2026-10-08, T4).

One report per run over both LLM layers -- the research agents (TradingAgents'
own calls, ``tradingagents_llm_calls.jsonl``) and the Week 2 semantic gateway
(``llm_semantic_calls.jsonl``, plus its wire-level request/response audit when
the run had one). Each HTTP request becomes exactly one normalized record:

* the Week 2 ledger holds one record per LOGICAL call; its top-level
  ``token_usage``/``provider_response`` repeat the LAST attempt, while
  ``request_attempts`` lists every attempt -- so requests are counted from the
  attempts only (never top-level + attempts), and joined with the audit by
  ``attempt_id`` when both exist (an audit row the ledger lacks still counts,
  once);
* a cache hit or a send refused before reaching the provider (call budget
  exhausted, audit unavailable, input too large) is a logical call with no
  request;
* the OpenAI-compatible client class LangChain reports (``openai``) and the
  provider actually billing the request (resolved from the model name / base
  URL) are kept side by side -- the original value is never overwritten.

Tokens are only what the provider returned (never estimated from latency); a
request without usage -- a timeout, an unknown outcome -- is counted as
"usage missing" and its cost "not estimable", never zero. Costs are ESTIMATES
from ``cost_basis`` (source and query date in the report), an off-peak floor
and a peak ceiling, not billed amounts.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from comqutor_alpha.llm.cost_basis import PRICING_SOURCE, estimate_cost_with_cache_split

SCHEMA_VERSION = "comqutor.llm_usage_report.v1"
REPORT_FILENAME = "llm_usage_report.json"
_NEVER_SENT_STATUSES = {"budget_exhausted", "not_called", "audit_unavailable"}
_MODEL_PROVIDER = {"deepseek-v4-flash": "deepseek", "deepseek-flash": "deepseek"}


@dataclass
class UsageSources:
    run_id: str
    agent_calls: Path | None = None
    semantic_ledgers: list[Path] = field(default_factory=list)
    audit_dirs: list[Path] = field(default_factory=list)
    raw_agent_outputs: Path | None = None
    checkpoint: Path | None = None
    known_gaps: list[str] = field(default_factory=list)


def sources_for_run_dir(run_dir: Path) -> UsageSources:
    run_dir = Path(run_dir)

    def _if(path: Path) -> Path | None:
        return path if path.is_file() else None

    return UsageSources(
        run_id=run_dir.name,
        agent_calls=_if(run_dir / "tradingagents_llm_calls.jsonl"),
        semantic_ledgers=[p for p in (run_dir / "llm_semantic_calls.jsonl",) if p.is_file()],
        audit_dirs=[d for d in (run_dir / "error_logs",) if (d / "week2_llm_provider_request_audit.jsonl").is_file()],
        raw_agent_outputs=_if(run_dir / "raw_agent_outputs.json"),
    )


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _tokens_from_raw_usage(raw: Mapping[str, Any] | None) -> dict[str, int | None]:
    if not isinstance(raw, Mapping) or not isinstance(raw.get("prompt_tokens"), int):
        return {"input": None, "output": None, "reasoning": None, "cache_hit": None, "cache_miss": None}
    details = raw.get("completion_tokens_details") or {}
    hit = raw.get("prompt_cache_hit_tokens")
    miss = raw.get("prompt_cache_miss_tokens")
    return {"input": raw.get("prompt_tokens"), "output": raw.get("completion_tokens"),
            "reasoning": details.get("reasoning_tokens") if isinstance(details, Mapping) else None,
            "cache_hit": hit if isinstance(hit, int) else None, "cache_miss": miss if isinstance(miss, int) else None}


def _cost(model: str | None, tokens: Mapping[str, int | None]) -> dict[str, Any]:
    if tokens.get("input") is None or tokens.get("output") is None:
        return {"status": "not_estimable", "reason": "usage_missing", "usd_off_peak_floor": None, "usd_peak_ceiling": None}
    split = tokens.get("cache_hit") is not None and tokens.get("cache_miss") is not None
    estimate = estimate_cost_with_cache_split(
        _MODEL_PROVIDER.get(str(model or "").lower()), model,
        cache_miss_input_tokens=tokens["cache_miss"] if split else tokens["input"],
        cache_hit_input_tokens=tokens["cache_hit"] if split else None, output_tokens=tokens["output"])
    if estimate.usd is None:
        return {"status": "not_estimable", "reason": estimate.basis, "usd_off_peak_floor": None, "usd_peak_ceiling": None}
    return {"status": "estimated", "basis": estimate.basis, "usd_off_peak_floor": estimate.usd, "usd_peak_ceiling": estimate.usd_ceiling}


def _semantic_task(gateway_task: Any) -> Any:
    """The wire audit names a call by its gateway task (e.g. ``claim_batch_enrichment``), the ledger by its semantic task
    (``structured_adapter``); both are joined under the semantic name."""
    from comqutor_alpha.structure_engine.week2_llm import _TASK_RUNTIME_METADATA

    return (_TASK_RUNTIME_METADATA.get(gateway_task) or {}).get("semantic_task", gateway_task)


def _attempt_outcome(provider_status: Any, error_code: Any) -> str:
    """HTTP-level outcome of one attempt: a transport error after the request left (connection dropped, no response) is
    ``unknown`` -- it may or may not have been processed and billed -- never a plain failure."""
    if provider_status == "success":
        return "success"
    if provider_status == "timeout":
        return "timeout"
    if provider_status in _NEVER_SENT_STATUSES:
        return "not_sent"
    if provider_status == "provider_error":
        return "unknown" if error_code == "WEEK2_LLM_TRANSPORT_ERROR" else "failure"
    return "unknown"


def _semantic_requests(sources: UsageSources) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    audit_requests: dict[str, dict[str, Any]] = {}
    audit_responses: dict[str, dict[str, Any]] = {}
    for directory in sources.audit_dirs:
        req_path, resp_path = directory / "week2_llm_provider_request_audit.jsonl", directory / "week2_llm_provider_response_audit.jsonl"
        # attempt ids are numbered per gateway, so a run with one gateway per task repeats them: identity is (task, attempt_id)
        for row in _jsonl(req_path) if req_path.is_file() else []:
            audit_requests.setdefault((_semantic_task(row.get("task")), row["attempt_id"]), row)
        for row in _jsonl(resp_path) if resp_path.is_file() else []:
            audit_responses.setdefault((_semantic_task(row.get("task")), row["attempt_id"]), row)
    logical: list[dict[str, Any]] = []
    requests: list[dict[str, Any]] = []
    seen_attempts: set[tuple[Any, str]] = set()
    counters = Counter()
    for ledger in sources.semantic_ledgers:
        for record in _jsonl(ledger):
            attempts = record.get("request_attempts") or []
            cache_hit = bool((record.get("cache") or {}).get("hit"))
            status = record.get("provider_status")
            logical.append({"layer": "week2_semantic", "step": record.get("task"), "call_id": record.get("call_id"),
                            "outcome": "served_from_cache" if cache_hit else ("not_sent" if status in _NEVER_SENT_STATUSES and not attempts else status),
                            "not_sent_reason": record.get("error_code") if status in _NEVER_SENT_STATUSES and not attempts else None,
                            "attempts": len(attempts)})
            if record.get("token_usage") and attempts and len(attempts) > 1:
                counters["ledger_records_where_top_level_usage_is_last_attempt_only"] += 1
            response_meta = record.get("provider_response") or {}
            for index, attempt in enumerate(attempts):
                attempt_id = attempt.get("attempt_id")
                identity = (record.get("task"), attempt_id)
                if attempt_id and identity in seen_attempts:
                    counters["duplicate_attempts_dropped"] += 1
                    continue
                if attempt_id:
                    seen_attempts.add(identity)
                response = audit_responses.get(identity) if attempt_id else None
                returned_model, request_id = None, None
                if response is not None:
                    try:
                        body = json.loads(response.get("body") or "{}")
                        returned_model, request_id = body.get("model"), body.get("id")
                    except ValueError:
                        pass
                if index == len(attempts) - 1:
                    returned_model = returned_model or response_meta.get("response_model")
                    request_id = request_id or response_meta.get("provider_request_id")
                outcome = _attempt_outcome(attempt.get("provider_status"), attempt.get("error_code"))
                if outcome == "unknown" and response is not None and response.get("status_code") not in (None, 200):
                    outcome = "failure"  # the wire audit shows an error response did come back
                tokens = _tokens_from_raw_usage(attempt.get("raw_usage"))
                requests.append({
                    "layer": "week2_semantic", "run_id": record.get("run_id"), "step": record.get("task"),
                    "client_api_style": "openai_compatible", "provider_reported": record.get("provider"),
                    "provider_resolved": _MODEL_PROVIDER.get(str(record.get("model") or "").lower(), record.get("provider")),
                    "model_requested": record.get("model"), "model_returned": returned_model,
                    "call_id": record.get("call_id"), "attempt_id": attempt_id, "attempt_number": attempt.get("attempt_number"),
                    "provider_request_id": request_id,
                    "started_at": (audit_requests.get(identity) or {}).get("created_at") or (record.get("started_at") if index == 0 else None),
                    "completed_at": (response or {}).get("created_at") or (record.get("completed_at") if index == len(attempts) - 1 else None),
                    "outcome": outcome, "error_code": attempt.get("error_code"), "finish_reason": attempt.get("finish_reason"),
                    "is_retry": index > 0, "raw_usage": attempt.get("raw_usage"), "tokens": tokens,
                    "usage_status": "known" if tokens["input"] is not None else "missing",
                    "cost": _cost(record.get("model"), tokens) if outcome != "not_sent" else {"status": "not_sent"},
                })
    # audit rows with no ledger attempt (e.g. a task whose calls never reached the semantic ledger): each counted once
    for identity, row in sorted(audit_requests.items(), key=lambda item: (str(item[0][0]), str(item[0][1]))):
        if identity in seen_attempts:
            continue
        seen_attempts.add(identity)
        attempt_id = identity[1]
        counters["audit_only_requests"] += 1
        response = audit_responses.get(identity)
        raw, returned_model, request_id, outcome = None, None, None, "unknown"
        try:
            sent_model = json.loads(row.get("body") or "{}").get("model")
        except ValueError:
            sent_model = None
        if response is not None:
            outcome = "success" if response.get("status_code") == 200 else "failure"
            try:
                body = json.loads(response.get("body") or "{}")
                raw, returned_model, request_id = body.get("usage"), body.get("model"), body.get("id")
            except ValueError:
                pass
        tokens = _tokens_from_raw_usage(raw)
        requests.append({
            "layer": "week2_semantic", "run_id": row.get("execution_id"), "step": _semantic_task(row.get("task")), "client_api_style": "openai_compatible",
            "provider_reported": None, "provider_resolved": _MODEL_PROVIDER.get(str(sent_model or "").lower()),
            "model_requested": sent_model, "model_returned": returned_model, "call_id": row.get("semantic_call_id"), "attempt_id": attempt_id,
            "attempt_number": None, "provider_request_id": request_id, "started_at": row.get("created_at"),
            "completed_at": (response or {}).get("created_at"), "outcome": outcome, "error_code": None, "finish_reason": None,
            "is_retry": False, "raw_usage": raw, "tokens": tokens, "usage_status": "known" if tokens["input"] is not None else "missing",
            "cost": _cost(sent_model, tokens),
        })
    return logical, requests, dict(counters)


def _agent_requests(sources: UsageSources) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if sources.agent_calls is None:
        return [], []
    logical, requests = [], []
    for record in _jsonl(sources.agent_calls):
        usage = record.get("token_usage") or {}
        tokens = {"input": usage.get("input_tokens"), "output": usage.get("output_tokens"), "reasoning": None, "cache_hit": None, "cache_miss": None}
        error = str(record.get("error_type") or "")
        outcome = "success" if record.get("success") else ("timeout" if "timeout" in error.lower() else "failure")
        retries = int(record.get("retry_count") or 0)
        logical.append({"layer": "research_agent", "step": record.get("agent_label"), "call_id": record.get("provider_call_id"),
                        "outcome": outcome, "attempts": 1 + retries})
        requests.append({
            "layer": "research_agent", "run_id": record.get("run_id"), "step": record.get("agent_label"), "client_api_style": "openai_compatible",
            "provider_reported": record.get("provider"),
            "provider_resolved": _MODEL_PROVIDER.get(str(record.get("model") or "").lower(), record.get("provider")),
            "model_requested": record.get("model"), "model_returned": None, "call_id": record.get("provider_call_id"), "attempt_id": None,
            "attempt_number": None, "provider_request_id": record.get("provider_call_id"), "started_at": record.get("started_at"),
            "completed_at": record.get("completed_at"), "outcome": outcome, "error_code": record.get("error_type"), "finish_reason": None,
            "is_retry": False, "client_retries_within_call": retries, "raw_usage": usage or None, "tokens": tokens,
            "usage_status": "known" if tokens["input"] is not None else "missing", "cost": _cost(record.get("model"), tokens),
        })
    return logical, requests


def _sum(values: Iterable[int | None]) -> int:
    return sum(v for v in values if isinstance(v, int))


def _summarize(logical: list[dict[str, Any]], requests: list[dict[str, Any]]) -> dict[str, Any]:
    by_outcome = Counter(r["outcome"] for r in requests)
    sent = [r for r in requests if r["outcome"] != "not_sent"]
    known = [r for r in sent if r["usage_status"] == "known"]
    estimated = [r for r in sent if r["cost"].get("status") == "estimated"]
    return {
        "logical_calls": len(logical),
        "served_from_cache": sum(1 for c in logical if c["outcome"] == "served_from_cache"),
        "not_sent": sum(1 for c in logical if c["outcome"] == "not_sent") + by_outcome.get("not_sent", 0),
        "not_sent_reasons": dict(Counter(c.get("not_sent_reason") for c in logical if c["outcome"] == "not_sent")),
        "budget_reservations": len(sent),
        "actual_http_requests": len(sent) + _sum(r.get("client_retries_within_call") for r in sent),
        "retries": sum(1 for r in sent if r["is_retry"]) + _sum(r.get("client_retries_within_call") for r in sent),
        "outcomes": {k: by_outcome.get(k, 0) for k in ("success", "failure", "timeout", "unknown")},
        # a token kind no request reported (e.g. research-agent calls report no cache split) is null, never 0
        "tokens_known": {k: (_sum(r["tokens"][k] for r in known) if any(r["tokens"][k] is not None for r in known) else None)
                         for k in ("input", "output", "reasoning", "cache_hit", "cache_miss")},
        "requests_with_usage": len(known),
        "requests_missing_usage": len(sent) - len(known),
        "usage_missing_ratio": round((len(sent) - len(known)) / len(sent), 6) if sent else None,
        "cache_split_reported_requests": sum(1 for r in known if r["tokens"]["cache_hit"] is not None),
        "cost_estimate_usd": {"off_peak_floor": round(sum(r["cost"]["usd_off_peak_floor"] for r in estimated), 6),
                              "peak_ceiling": round(sum(r["cost"]["usd_peak_ceiling"] or 0 for r in estimated), 6),
                              "requests_estimated": len(estimated), "requests_not_estimable": len(sent) - len(estimated),
                              "not_estimable_reasons": dict(Counter(r["cost"].get("reason") for r in sent if r["cost"].get("status") != "estimated"))},
    }


def build_usage_report(sources: UsageSources) -> dict[str, Any]:
    semantic_logical, semantic_requests, dedup = _semantic_requests(sources)
    agent_logical, agent_requests = _agent_requests(sources)
    agents: list[str] = []
    if sources.raw_agent_outputs is not None:
        payload = json.loads(Path(sources.raw_agent_outputs).read_text(encoding="utf-8"))
        agents = sorted({str(a.get("agent")) for a in payload.get("agent_outputs") or [] if isinstance(a, Mapping)})
    per_step: dict[str, dict[str, Any]] = {}
    grouped: dict[tuple[str, str], tuple[list, list]] = defaultdict(lambda: ([], []))
    for item in semantic_logical + agent_logical:
        grouped[(item["layer"], str(item["step"]))][0].append(item)
    for item in semantic_requests + agent_requests:
        grouped[(item["layer"], str(item["step"]))][1].append(item)
    for (layer, step), (logical, requests) in sorted(grouped.items()):
        per_step[f"{layer}:{step}"] = _summarize(logical, requests)
    corrections = []
    reported = Counter((r["provider_reported"], r["provider_resolved"]) for r in agent_requests + semantic_requests
                       if r["provider_reported"] and r["provider_resolved"] and r["provider_reported"] != r["provider_resolved"])
    for (rep, res), n in reported.items():
        corrections.append({"field": "provider", "reported": rep, "resolved": res, "requests": n,
                            "basis": "the reported value is the OpenAI-compatible client class LangChain tags; the model name (pricing table) and the "
                                     "configured DeepSeek endpoint identify the billing provider; the original value is kept in provider_reported"})
    data_sources = {str(p): _sha(p) for p in ([sources.agent_calls] if sources.agent_calls else []) + list(sources.semantic_ledgers)
                    + [d / n for d in sources.audit_dirs for n in ("week2_llm_provider_request_audit.jsonl", "week2_llm_provider_response_audit.jsonl")
                       if (d / n).is_file()] + ([sources.raw_agent_outputs] if sources.raw_agent_outputs else [])}
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": sources.run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "upstream_agents": {"count": len(agents), "agents": agents},
        "totals": {"research_agent": _summarize(agent_logical, agent_requests), "week2_semantic": _summarize(semantic_logical, semantic_requests),
                   "all": _summarize(agent_logical + semantic_logical, agent_requests + semantic_requests)},
        "per_step": per_step,
        "deduplication": {"rule": "one record per HTTP request: Week 2 ledger attempts (never its top-level last-attempt usage) joined with the "
                                  "wire audit by attempt_id; research-agent calls one record each", **dedup},
        "corrections": corrections,
        "pricing": {"source": {f"{k[0]}:{k[1]}": v for k, v in PRICING_SOURCE.items()},
                    "method": "cost = cache-miss input x input rate + cache-hit input x cache-hit rate + output x output rate (reasoning tokens are "
                              "part of output); when a response reports no cache split all input is priced at the cache-miss rate; off-peak "
                              "floor and peak ceiling; ESTIMATES, not billed amounts"},
        "known_gaps": list(sources.known_gaps),
        "data_sources": data_sources,
        "requests": semantic_requests + agent_requests,
    }


def write_run_usage_report(run_dir: Path) -> dict[str, Any]:
    report = build_usage_report(sources_for_run_dir(run_dir))
    (Path(run_dir) / REPORT_FILENAME).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return report


__all__ = ["REPORT_FILENAME", "SCHEMA_VERSION", "UsageSources", "build_usage_report", "sources_for_run_dir", "write_run_usage_report"]
