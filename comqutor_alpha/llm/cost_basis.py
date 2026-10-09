"""Cost-basis lookup for LLM request-level statistics.

A repo-wide search (2026-09-30) confirmed there was no existing, confirmed
USD-per-token pricing table anywhere in this codebase --
``docs/audit_artifacts/v0_2_semantic_classifier_cost_latency_audit.json``'s
own "cost" field means wall-clock latency, not currency. Fabricating a
per-token price here would violate the exact same "never estimate, mark
unknown" rule this module exists to uphold for token counts themselves
(see ``comqutor_alpha.structure_engine.week2_llm._response_token_usage``).

``_PRICING_USD_PER_MILLION_TOKENS`` (2026-09-30, third follow-up round) now
holds real, dated, sourced entries for the three billed models actually
named in this codebase's own frozen production config
(``t3_model_config_comparison_2026-09-30.md``: the Research Agent's
``openai``/``gpt-5.5``+``gpt-5.4-mini``, and every Week2 semantic task's
``deepseek``/``deepseek-v4-flash``) -- each entry's own source URL and query
date is cited in the comment directly above it; see
``docs/audit_artifacts/round_source_linking_t0_t2/t3_t4_pricing_reference_2026-09-30.md``
for the full research trail (including the two providers/models this
search could NOT confirm a price for, kept as explicit gaps rather than
guessed). Add any further ``(provider, model)`` entry only once a real,
dated, sourced published price is confirmed and cited the same way -- never
a remembered or guessed figure. Every lookup for anything not in the table
still honestly reports "no pricing table entry" rather than a cost.

DeepSeek bills a lower OFF-PEAK rate and a higher PEAK rate depending on the
time of day the call is made (01:00-04:00 and 06:00-10:00 UTC on weekdays,
excluding Chinese public holidays, is peak). This table stores the OFF-PEAK
(lower-bound) rate as the point estimate for ``estimate_cost_usd`` -- a
deliberate floor, not the only possible real figure -- and
``estimate_cost_usd`` additionally returns the peak-rate figure in
``CostEstimate.usd_ceiling`` so a caller can see both bounds rather than a
single number quietly hiding which regime it assumes.
"""

from __future__ import annotations

from typing import NamedTuple


class CostEstimate(NamedTuple):
    usd: float | None
    basis: str
    usd_ceiling: float | None = None


# Keys are lowercased (provider, model) tuples. Values are
# (input_usd_per_million, output_usd_per_million) at the OFF-PEAK/standard
# rate for time-varying providers, plus an optional third element
# (peak_input_usd_per_million, peak_output_usd_per_million) when the
# provider's own official pricing varies by time of day.
#
# gpt-5.5 (Research Agent deep_think_llm): $5.00 input / $30.00 output per 1M
# tokens (cached input $0.50/1M, not modeled separately here -- this table
# tracks input/output only). Source: https://developers.openai.com/api/docs/pricing
# (reached via the official https://platform.openai.com/docs/pricing redirect),
# queried 2026-09-30.
_PRICING_USD_PER_MILLION_TOKENS: dict[tuple[str, str], tuple[float, float]] = {
    ("openai", "gpt-5.5"): (5.00, 30.00),
    # gpt-5.4-mini (Research Agent quick_think_llm): $0.75 input / $4.50
    # output per 1M tokens (cached input $0.075/1M, not modeled separately).
    # Source: https://developers.openai.com/api/docs/pricing, queried 2026-09-30.
    ("openai", "gpt-5.4-mini"): (0.75, 4.50),
    # deepseek-v4-flash (every Week2 semantic task: structured_adapter,
    # alpha_classifier, structure_extractor, evidence_stance_classifier):
    # the official DeepSeek API docs (https://api-docs.deepseek.com/quick_start/pricing,
    # queried 2026-09-30) confirm "deepseek-v4-flash" is a still-accepted
    # LEGACY ALIAS for the current "deepseek-flash" model -- this is the
    # vendor's own documented rename, not a substitution of a similar-but-
    # different model's price. OFF-PEAK (all hours outside 01:00-04:00 and
    # 06:00-10:00 UTC weekdays): $0.15 input (cache miss) / $0.60 output per
    # 1M tokens. PEAK: $0.30 input / $1.20 output. Cache-HIT input is
    # separately far cheaper ($0.003 off-peak / $0.006 peak per 1M) but is
    # not modeled here since this table only tracks the two fields
    # estimate_cost_usd accepts (input_tokens, output_tokens), not a
    # cache-hit/miss split.
    ("deepseek", "deepseek-v4-flash"): (0.15, 0.60),
}

_PEAK_PRICING_USD_PER_MILLION_TOKENS: dict[tuple[str, str], tuple[float, float]] = {
    ("deepseek", "deepseek-v4-flash"): (0.30, 1.20),
}

# 2026-10-08 (T4): the cache-HIT input rate the deepseek-v4-flash comment
# above already records from the same source and query date (off-peak,
# peak), now used by estimate_cost_with_cache_split; nothing else changes.
_CACHE_HIT_INPUT_USD_PER_MILLION_TOKENS: dict[tuple[str, str], tuple[float, float]] = {
    ("deepseek", "deepseek-v4-flash"): (0.003, 0.006),
}
PRICING_SOURCE = {
    ("deepseek", "deepseek-v4-flash"): {
        "url": "https://api-docs.deepseek.com/quick_start/pricing",
        "queried_at": "2026-09-30",
        "note": "deepseek-v4-flash is the vendor's documented legacy alias of deepseek-flash; off-peak / peak by time of day",
    },
}

# Round 5 (2026-10-04), T4 cost-metering gap: comqutor_alpha.runners.
# diagnostics._extract_provider_model reads LangChain's own ``ls_provider``
# call metadata "never a guess" (its own docstring) -- but LangChain
# genuinely reports ``ls_provider="openai"`` for a DeepSeek call made
# through an OpenAI-compatible client class (the real client used here),
# because that metadata tag describes the CLIENT CLASS, not the actual
# billed vendor. A real NVDA Fresh Run (034a0a60-430e-41f8-8321-
# 03a11389707a) confirmed this exact symptom: ``tradingagents_llm_usage_
# summary.json`` recorded all 20 calls under ``"openai:deepseek-v4-flash"``
# and ``total_cost_usd: null`` with reason ``no_pricing_table_entry_for_
# provider_model`` -- every one of those calls has real token_usage and a
# confirmed off-peak price on file, the ONLY blocker is the provider label.
#
# The MODEL NAME itself is never ambiguous about which vendor actually
# bills it (no two providers in this table's own entries share a model
# name) -- so a model name present here authoritatively overrides a
# mismatched/generic client-reported provider label, never the other way
# around (a real OpenAI gpt-5.5/gpt-5.4-mini call is never remapped, since
# those model names are not in this table). This is purely a LOOKUP-KEY
# normalization; the raw, originally-reported provider label is preserved
# unchanged everywhere else (run_audit/usage summaries/logs) -- only the
# pricing lookup itself stops trusting a known-misleading client-class tag
# over the model name's own, unambiguous vendor identity.
_MODEL_NAME_IMPLIES_PROVIDER: dict[str, str] = {
    "deepseek-v4-flash": "deepseek",
}


def estimate_cost_usd(
    provider: str | None,
    model: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
) -> CostEstimate:
    """Return a cost estimate and its basis, never a guess.

    Returns ``(None, "no_pricing_table_entry_for_provider_model")`` when no
    confirmed price is on file for this (provider, model), and
    ``(None, "token_usage_unavailable")`` when a price exists but the
    Provider itself never returned usable token counts for this call.
    Never derives a cost from elapsed time or any other proxy.

    ``usd_ceiling`` is populated only for providers with confirmed
    time-varying (peak/off-peak) pricing -- ``usd`` itself is always the
    lower, off-peak figure for those; every other provider/model has
    ``usd_ceiling is None`` because its price does not vary.
    """
    reported_provider = str(provider or "").strip().lower()
    model_normalized = str(model or "").strip().lower()
    canonical_provider = _MODEL_NAME_IMPLIES_PROVIDER.get(model_normalized, reported_provider)
    key = (canonical_provider, model_normalized)
    prices = _PRICING_USD_PER_MILLION_TOKENS.get(key)
    if prices is None:
        return CostEstimate(None, "no_pricing_table_entry_for_provider_model")
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        return CostEstimate(None, "token_usage_unavailable")
    input_price, output_price = prices
    usd = (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price

    ceiling = None
    peak_prices = _PEAK_PRICING_USD_PER_MILLION_TOKENS.get(key)
    if peak_prices is not None:
        peak_input_price, peak_output_price = peak_prices
        ceiling = round(
            (input_tokens / 1_000_000) * peak_input_price + (output_tokens / 1_000_000) * peak_output_price,
            6,
        )

    basis = f"pricing_table:{key[0]}:{key[1]}"
    if canonical_provider != reported_provider:
        basis += f":model_name_overrode_reported_provider_{reported_provider or 'empty'}"
    if ceiling is not None:
        basis += ":off_peak_floor_estimate_see_usd_ceiling_for_peak_rate"
    return CostEstimate(round(usd, 6), basis, ceiling)


def estimate_cost_with_cache_split(
    provider: str | None,
    model: str | None,
    *,
    cache_miss_input_tokens: int | None,
    cache_hit_input_tokens: int | None,
    output_tokens: int | None,
) -> CostEstimate:
    """Like ``estimate_cost_usd`` but prices cache-hit input at the provider's
    own cache-hit rate when the response reported the split. ``cache_hit_input_
    tokens=None`` means the split is unknown: every input token is then priced
    at the cache-miss rate (an upper bound of the off-peak figure) and the
    basis says so. Never a cost without real token counts."""
    model_normalized = str(model or "").strip().lower()
    canonical_provider = _MODEL_NAME_IMPLIES_PROVIDER.get(model_normalized, str(provider or "").strip().lower())
    key = (canonical_provider, model_normalized)
    prices = _PRICING_USD_PER_MILLION_TOKENS.get(key)
    if prices is None:
        return CostEstimate(None, "no_pricing_table_entry_for_provider_model")
    if not isinstance(cache_miss_input_tokens, int) or not isinstance(output_tokens, int):
        return CostEstimate(None, "token_usage_unavailable")
    hit_prices = _CACHE_HIT_INPUT_USD_PER_MILLION_TOKENS.get(key)
    split_known = isinstance(cache_hit_input_tokens, int) and hit_prices is not None
    hit = cache_hit_input_tokens if split_known else 0
    peak = _PEAK_PRICING_USD_PER_MILLION_TOKENS.get(key)

    def _usd(miss_rate: float, hit_rate: float, out_rate: float) -> float:
        return round((cache_miss_input_tokens * miss_rate + hit * hit_rate + output_tokens * out_rate) / 1_000_000, 6)

    floor = _usd(prices[0], hit_prices[0] if split_known else 0.0, prices[1])
    ceiling = _usd(peak[0], hit_prices[1] if split_known else 0.0, peak[1]) if peak is not None else None
    basis = f"pricing_table:{key[0]}:{key[1]}:" + ("cache_split_priced" if split_known else "cache_split_unknown_all_input_at_cache_miss_rate")
    return CostEstimate(floor, basis, ceiling)
