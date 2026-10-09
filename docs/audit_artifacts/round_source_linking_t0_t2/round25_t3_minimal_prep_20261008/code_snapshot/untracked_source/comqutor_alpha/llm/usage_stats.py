"""Read-only request-level usage/cost rollup over persisted semantic-call logs.

Deliberately lives in ``comqutor_alpha/llm/``, not ``comqutor_alpha/llm_runtime/``:
that package is a closed set guarded by
``tests/llm_runtime/test_no_production_importers.py`` (an exact allow-list of
both its own source files and everything outside it that may import from it)
to keep the semantic-call runtime's dependency surface curated and reviewed.
This module never touches ``manifest.py``'s frozen
``SEMANTIC_MANIFEST_SCHEMA_VERSION`` / ``_MANIFEST_FIELDS`` contract (which
``source_bundle.py``'s tamper-detection recomputation depends on reproducing
exactly) and never mutates any persisted file -- it only aggregates over
``SemanticCallRecord.to_dict()``-shaped records the caller already has (e.g.
lines already read from a real run's ``llm_semantic_calls.jsonl``), the same
read-only convention already used by
``docs/audit_artifacts/v0_2_semantic_classifier_cost_latency_audit.json``.

Three distinct counts, never conflated:
  - ``logical_call_count``: one per ``SemanticCallRecord`` (one per task
    invocation, i.e. one per ``call_sequence``), regardless of how many
    Provider attempts it took.
  - ``actual_request_count``: real network attempts -- a logical call whose
    ``provider_status`` is one of the "Provider was actually called" values
    made 1 real request plus one more per retry; a cache hit or a call that
    never reached the Provider makes zero requests.
  - ``retry_count_total``: the sum of each record's own ``retry_count``,
    reported separately so retries are visible on their own.

Token usage and cost are never estimated from elapsed time or any other
proxy. A record whose ``token_usage`` has no usable counts is counted in
``calls_missing_usage`` and excluded from the summed totals -- never
treated as zero.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from comqutor_alpha.llm.cost_basis import estimate_cost_usd

# Deliberately mirrored, not imported, from
# comqutor_alpha.llm_runtime.contracts.PROVIDER_CALLED_STATUSES -- importing
# that closed package from here would require widening its own guarded
# importer allow-list for a read-only analysis module that has no need to
# live inside it. If the canonical value ever changes, update this mirror
# to match.
_PROVIDER_CALLED_STATUSES = frozenset({"success", "timeout", "provider_error"})

USAGE_STATS_SCHEMA_VERSION = "comqutor.llm_usage_stats.v1"


@dataclass
class UsageStats:
    schema_version: str = USAGE_STATS_SCHEMA_VERSION
    logical_call_count: int = 0
    actual_request_count: int = 0
    retry_count_total: int = 0
    calls_with_usage: int = 0
    calls_missing_usage: int = 0
    missing_usage_ratio: float | None = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens_known: int = 0
    cache_hit_count: int = 0
    provider_status_counts: dict[str, int] = field(default_factory=dict)
    total_cost_usd: float | None = None
    cost_basis_notes: dict[str, int] = field(default_factory=dict)
    per_provider_model: dict[str, dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "logical_call_count": self.logical_call_count,
            "actual_request_count": self.actual_request_count,
            "retry_count_total": self.retry_count_total,
            "calls_with_usage": self.calls_with_usage,
            "calls_missing_usage": self.calls_missing_usage,
            "missing_usage_ratio": self.missing_usage_ratio,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens_known": self.total_tokens_known,
            "cache_hit_count": self.cache_hit_count,
            "provider_status_counts": dict(self.provider_status_counts),
            "total_cost_usd": self.total_cost_usd,
            "cost_basis_notes": dict(self.cost_basis_notes),
            "per_provider_model": {key: dict(value) for key, value in self.per_provider_model.items()},
        }


def compute_usage_stats(records: Iterable[Mapping[str, Any]]) -> UsageStats:
    """Aggregate request-level statistics from ``SemanticCallRecord``-shaped dicts.

    Pure function: takes an iterable of already-loaded record dicts, reads
    no file, makes no network call. The caller decides where the records
    came from (a real ``llm_semantic_calls.jsonl``, or a fixed synthetic
    fixture in a test).
    """
    stats = UsageStats()
    cost_total: float | None = None
    cost_seen = False

    for record in records:
        stats.logical_call_count += 1

        provider_status = str(record.get("provider_status") or "")
        stats.provider_status_counts[provider_status] = stats.provider_status_counts.get(provider_status, 0) + 1

        retry_count = record.get("retry_count") or 0
        stats.retry_count_total += retry_count

        cache = record.get("cache") or {}
        if bool(cache.get("hit")):
            stats.cache_hit_count += 1

        if provider_status in _PROVIDER_CALLED_STATUSES:
            stats.actual_request_count += 1 + retry_count

        token_usage = record.get("token_usage") or {}
        input_tokens = token_usage.get("input_tokens")
        output_tokens = token_usage.get("output_tokens")
        total_tokens = token_usage.get("total_tokens")
        has_usage = total_tokens is not None or (
            isinstance(input_tokens, int) and isinstance(output_tokens, int)
        )
        if has_usage:
            stats.calls_with_usage += 1
            if isinstance(input_tokens, int):
                stats.total_input_tokens += input_tokens
            if isinstance(output_tokens, int):
                stats.total_output_tokens += output_tokens
            if isinstance(total_tokens, int):
                stats.total_tokens_known += total_tokens
            elif isinstance(input_tokens, int) and isinstance(output_tokens, int):
                stats.total_tokens_known += input_tokens + output_tokens
        else:
            stats.calls_missing_usage += 1

        provider = record.get("provider")
        model = record.get("model")
        cost = estimate_cost_usd(provider, model, input_tokens, output_tokens)
        stats.cost_basis_notes[cost.basis] = stats.cost_basis_notes.get(cost.basis, 0) + 1
        if cost.usd is not None:
            cost_total = (cost_total or 0.0) + cost.usd
            cost_seen = True

        bucket_key = f"{provider}:{model}"
        bucket = stats.per_provider_model.setdefault(
            bucket_key, {"logical_call_count": 0, "calls_with_usage": 0, "calls_missing_usage": 0}
        )
        bucket["logical_call_count"] += 1
        if has_usage:
            bucket["calls_with_usage"] += 1
        else:
            bucket["calls_missing_usage"] += 1

    if stats.logical_call_count:
        stats.missing_usage_ratio = round(stats.calls_missing_usage / stats.logical_call_count, 6)
    stats.total_cost_usd = round(cost_total, 6) if cost_seen else None
    return stats
