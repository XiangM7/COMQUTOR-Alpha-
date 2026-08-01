"""Inject the COMQUTOR Structure Output Contract into TradingAgents' own,
already-existing LLM prompts -- never a second LLM call, never an edit to
``tradingagents/``.

Every one of TradingAgents' 12 prompt-builder functions (market/sentiment/
news/fundamentals analysts, bull/bear researchers, research manager, trader,
aggressive/conservative/neutral risk debators, portfolio manager) already
calls a shared helper, ``get_language_instruction()``, and appends its
return value as the very last thing in its prompt (see
``tradingagents/agents/utils/agent_utils.py``). Because every one of those
12 modules did ``from ...agent_utils import get_language_instruction`` (a
name copy at import time), patching the origin module alone would not
reliably reach already-imported consumers -- this module instead patches the
already-imported attribute on each of the 12 consumer modules directly,
scoped (try/finally) around one full ``propagate()``/``stream()`` run, the
same "swap a registry-like seam for the scope of a call" technique
``comqutor_alpha.llm.deepseek_smoke.deepseek_thinking_scope`` already uses
for DeepSeek's thinking-mode toggle (a different seam, same pattern).
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from comqutor_alpha.structure_engine.canonical_relation_prompt import (
    PROMPT_CONTRACT_VERSION,
    build_structure_output_contract_prompt_suffix,
    compute_prompt_contract_sha256,
)
from comqutor_alpha.structure_engine.canonical_vocabulary import build_canonical_relation_vocabulary

# agent id (matches tradingagents_output_writer.AGENT_OUTPUT_FIELDS' own
# `agent` field, the identifier that reaches raw_agent_outputs.json) -> the
# real tradingagents module whose prompt-builder(s) are patched for that
# agent. Every one of these 12 modules defines
# ``get_language_instruction`` in its own namespace (imported from
# ``tradingagents.agents.utils.agent_utils``); ``social_media_analyst.py``
# is a deprecated re-export shim of ``sentiment_analyst.py`` (no separate
# prompt logic of its own), so patching ``sentiment_analyst`` alone already
# covers it.
AGENT_ID_TO_MODULE: dict[str, str] = {
    "market_agent": "tradingagents.agents.analysts.market_analyst",
    "sentiment_agent": "tradingagents.agents.analysts.sentiment_analyst",
    "news_agent": "tradingagents.agents.analysts.news_analyst",
    "fundamental_agent": "tradingagents.agents.analysts.fundamentals_analyst",
    "bull_researcher": "tradingagents.agents.researchers.bull_researcher",
    "bear_researcher": "tradingagents.agents.researchers.bear_researcher",
    "research_manager": "tradingagents.agents.managers.research_manager",
    "trader": "tradingagents.agents.trader.trader",
    "aggressive_risk_analyst": "tradingagents.agents.risk_mgmt.aggressive_debator",
    "conservative_risk_analyst": "tradingagents.agents.risk_mgmt.conservative_debator",
    "neutral_risk_analyst": "tradingagents.agents.risk_mgmt.neutral_debator",
    "portfolio_manager": "tradingagents.agents.managers.portfolio_manager",
}


def _build_suffix_and_vocabulary() -> tuple[str, dict[str, Any]]:
    vocabulary = build_canonical_relation_vocabulary()
    suffix = build_structure_output_contract_prompt_suffix(vocabulary)
    return suffix, vocabulary


def _make_wrapper(original, suffix: str):
    def _wrapped() -> str:
        return original() + suffix

    return _wrapped


@contextmanager
def comqutor_structure_output_contract_scope() -> Iterator[None]:
    """Patch ``get_language_instruction`` on every one of the 12 already-
    imported agent modules for the duration of the ``with`` block, then
    restore the originals. Must wrap the *entire* propagate/stream duration
    (not just graph construction): unlike the DeepSeek chat-class swap
    (fixed once, at LLM-client-construction time), every one of these 12
    prompt-builder functions calls ``get_language_instruction()`` fresh at
    node-execution time, once per agent node, throughout the whole run.
    Adds zero LLM calls -- it only changes what text is appended to prompts
    already being built at these exact call sites.
    """
    suffix, _vocabulary = _build_suffix_and_vocabulary()

    patched: list[tuple[Any, Any]] = []
    for module_name in AGENT_ID_TO_MODULE.values():
        module = importlib.import_module(module_name)
        original = getattr(module, "get_language_instruction", None)
        if original is None:
            continue
        module.get_language_instruction = _make_wrapper(original, suffix)
        patched.append((module, original))

    try:
        yield
    finally:
        for module, original in patched:
            module.get_language_instruction = original


def build_vocabulary_snapshot() -> dict[str, Any]:
    """Deterministic per-run artifact content
    (``tradingagents_comqutor_vocabulary_snapshot.json``): exactly which
    factors/relations every agent's prompt received this run, plus the
    prompt contract's own content hash. Every agent receives the identical,
    full production factor/relation catalog (the catalog is small -- see
    ``canonical_vocabulary.py`` -- so there is no per-agent shortlist to
    accidentally omit a needed endpoint from). Never includes an API key,
    Authorization header, or any other secret/Provider-header value."""
    suffix, vocabulary = _build_suffix_and_vocabulary()
    prompt_contract_sha256 = compute_prompt_contract_sha256(suffix)

    factor_ids = [f["factor_id"] for f in vocabulary["factors"]]
    relation_types = [r["relation_type"] for r in vocabulary["relations"]]
    agents = {
        agent_id: {"factor_ids_sent": list(factor_ids), "relation_types_sent": list(relation_types)}
        for agent_id in AGENT_ID_TO_MODULE
    }

    return {
        "taxonomy_version": vocabulary["taxonomy_version"],
        "taxonomy_sha256": vocabulary["taxonomy_sha256"],
        "relation_registry_version": vocabulary["relation_registry_version"],
        "factor_count": len(factor_ids),
        "relation_count": len(relation_types),
        "agents": agents,
        "prompt_contract_version": PROMPT_CONTRACT_VERSION,
        "prompt_contract_sha256": prompt_contract_sha256,
    }


__all__ = [
    "AGENT_ID_TO_MODULE",
    "comqutor_structure_output_contract_scope",
    "build_vocabulary_snapshot",
]
