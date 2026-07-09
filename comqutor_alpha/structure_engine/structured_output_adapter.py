"""Adapt TradingAgents raw output JSON into official structured claim records."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from comqutor_alpha.storage.file_store import (
    append_jsonl_record,
    load_json_record,
    save_json_record,
    validate_run_id_for_path,
)
from comqutor_alpha.structure_engine.structure_schema import (
    VALID_DIRECTIONS,
    clamp_score,
    normalize_direction,
)

# Constants for structured output schema and entity/factor extraction
SCHEMA_VERSION = "week1a.structured_agent_outputs.v1"
ERROR_LOG_ARTIFACT_PATH = "error_logs/structured_output_adapter_errors.jsonl"
MAX_ERROR_PREVIEW_CHARS = 500
ENTITY_TERMS = (
    "NVDA",
    "NVIDIA",
    "GPU",
    "AI",
    "datacenter",
    "data center",
    "revenue",
    "valuation",
    "rates",
    "liquidity",
    "recession",
    "semiconductor",
    "chip",
)
FACTOR_PATTERNS = {
    "AI Demand": ("ai demand", "ai training", "artificial intelligence", "ai workload"),
    "AI CapEx": ("ai capex", "ai capital spending", "cloud capex", "infrastructure spending"),
    "GPU Demand": ("gpu demand", "accelerator demand", "compute demand", "gpu", "accelerator"),
    "Datacenter CapEx": ("datacenter", "data center", "power", "cooling", "networking"),
    "Revenue Growth": ("revenue growth", "revenue guidance", "guidance raised", "eps revisions"),
    "Valuation Risk": ("valuation", "multiple compression", "rich valuation", "high valuation"),
    "Recession Risk": ("recession", "economic slowdown", "credit spreads", "slowdown"),
    "Liquidity Expansion": ("liquidity", "risk appetite", "cash moves", "monetary liquidity"),
    "Narrative Momentum": ("narrative", "investor attention", "momentum", "reflexive flows"),
    "Semiconductor Cycle": ("semiconductor", "chip demand", "inventory", "asp", "chip cycle"),
}
POSITIVE_WORDS = (
    "bullish",
    "growth",
    "strong",
    "increase",
    "increasing",
    "beat",
    "upside",
    "buy",
    "positive",
    "raised",
    "supporting",
    "improving",
    "recovering",
)
NEGATIVE_WORDS = (
    "bearish",
    "risk",
    "decline",
    "pressure",
    "recession",
    "downside",
    "valuation compression",
    "sell",
    "negative",
    "widening",
    "slowdown",
)
NEUTRAL_WORDS = ("hold", "mixed", "wait", "balanced", "neutral")
EVIDENCE_WORDS = ("because", "due to", "driven by", "supports", "data", "guidance", "%", "$")
CERTAINTY_WORDS = ("clearly", "strong", "confirmed", "raised", "improving", "increasing")
ANALYST_AGENTS = {
    "market_agent",
    "sentiment_agent",
    "news_agent",
    "fundamental_agent",
    "fundamentals_agent",
    "technical_agent",
}
RESEARCH_AGENTS = {"bull_researcher", "bear_researcher", "research_manager"}
TRADER_AGENTS = {"trader"}
RISK_PORTFOLIO_AGENTS = {
    "aggressive_risk_analyst",
    "conservative_risk_analyst",
    "neutral_risk_analyst",
    "portfolio_manager",
}


def _now():
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, default=str)
    return re.sub(r"\s+", " ", text).strip()


def _safe_preview(value, max_chars=MAX_ERROR_PREVIEW_CHARS):
    preview = _normalize_text(value)
    if len(preview) <= max_chars:
        return preview
    return preview[:max_chars] + "...[truncated]"


def _run_context_from_dir(run_dir):
    run_dir = Path(run_dir).expanduser().resolve()
    run_id = validate_run_id_for_path(run_dir.name)
    output_root = run_dir.parent
    return run_dir, run_id, output_root


def load_raw_agent_outputs(run_dir):
    _, run_id, output_root = _run_context_from_dir(run_dir)
    return load_json_record(run_id, "raw_agent_outputs.json", output_root=output_root)


def normalize_agent_name(agent):
    return str(agent or "unknown_agent").strip().lower().replace(" ", "_")

# Infer the source type of the agent based on its name and raw text
def infer_source_type(agent, raw_text):
    agent = normalize_agent_name(agent)
    if "technical" in agent:
        return "technical"
    if "news" in agent:
        return "news"
    if "sentiment" in agent or "social" in agent:
        return "social"
    if "fundamental" in agent:
        return "filing"
    if "analyst" in agent or "researcher" in agent:
        return "analyst"
    if "price" in _normalize_text(raw_text).lower():
        return "price"
    return "unknown"


def infer_output_type(agent):
    agent = normalize_agent_name(agent)
    if agent in ANALYST_AGENTS:
        return "analyst"
    if agent in RESEARCH_AGENTS:
        return "research_debate"
    if agent in TRADER_AGENTS:
        return "trader"
    if agent in RISK_PORTFOLIO_AGENTS:
        return "risk_portfolio"
    if "research" in agent or "bull" in agent or "bear" in agent:
        return "research_debate"
    if "trader" in agent:
        return "trader"
    if "risk" in agent or "portfolio" in agent:
        return "risk_portfolio"
    if "agent" in agent or "analyst" in agent:
        return "analyst"
    return "unknown"

def extract_claim(raw_text):
    text = _normalize_text(raw_text)
    if not text:
        return "unknown"
    sentences = re.split(r"(?<=[.!?。！？])\s+", text)
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) >= 20:
            return sentence[:300]
    return text[:300]


def extract_evidence(raw_text):
    text = _normalize_text(raw_text)
    return text[:1000] if text else "unknown"


def extract_entities(raw_text, ticker):
    text = _normalize_text(raw_text).lower()
    entities = []
    if ticker:
        entities.append(str(ticker).upper())
    for term in ENTITY_TERMS:
        if re.search(rf"\b{re.escape(term.lower())}\b", text) and term not in entities:
            entities.append(term)
    return entities


def extract_factors(raw_text):
    text = _normalize_text(raw_text).lower()
    factors = []
    for factor, patterns in FACTOR_PATTERNS.items():
        if any(pattern in text for pattern in patterns):
            factors.append(factor)
    return factors

# Infer the direction of the claim based on the presence of positive, negative, and neutral words
def infer_direction(raw_text):
    text = _normalize_text(raw_text).lower()
    if not text:
        return "unknown"
    positive = sum(1 for word in POSITIVE_WORDS if word in text)
    negative = sum(1 for word in NEGATIVE_WORDS if word in text)
    neutral = sum(1 for word in NEUTRAL_WORDS if word in text)
    if positive > negative and positive > 0:
        return "positive"
    if negative > positive and negative > 0:
        return "negative"
    if positive > 0 and negative > 0:
        return "neutral"
    if neutral > 0:
        return "neutral"
    return "unknown"

# Estimate the confidence score of the claim based on text length, presence of evidence words, numbers, and certainty words
def estimate_confidence(raw_text):
    text = _normalize_text(raw_text).lower()
    if not text:
        return 0.0
    score = 0.25
    if len(text) >= 80:
        score += 0.15
    if len(text) >= 250:
        score += 0.10
    if any(word in text for word in EVIDENCE_WORDS):
        score += 0.20
    if re.search(r"\d|%|\$", text):
        score += 0.15
    if any(word in text for word in CERTAINTY_WORDS):
        score += 0.10
    return clamp_score(score)


def _normalize_source_refs(source_refs, source_agent_output_id=None):
    refs = []
    if isinstance(source_refs, str):
        refs = [source_refs]
    elif isinstance(source_refs, (list, tuple, set)):
        refs = [str(item) for item in source_refs if str(item).strip()]
    if source_agent_output_id and source_agent_output_id not in refs:
        refs.insert(0, str(source_agent_output_id))
    return refs


# Validate that the structured output record contains required fields with stable types.
def validate_structured_output(record):
    if not isinstance(record, dict):
        return False
    required_text = ("run_id", "ticker", "agent", "claim", "evidence")
    if any(not _normalize_text(record.get(field)) for field in required_text):
        return False
    if not isinstance(record.get("entities"), list):
        return False
    if not isinstance(record.get("factors"), list):
        return False
    if normalize_direction(record.get("direction")) not in VALID_DIRECTIONS:
        return False
    try:
        float(record.get("confidence"))
    except (TypeError, ValueError):
        return False
    if record.get("source_refs") is not None and not isinstance(record.get("source_refs"), list):
        return False
    return True

# Return a safe default structured record with a warning reason if the raw output is invalid or missing
def safe_default_record(
    run_id,
    ticker,
    agent,
    raw_text,
    reason,
    source_agent_output_id=None,
    error_code="INVALID_STRUCTURED_OUTPUT",
):
    del raw_text
    agent = normalize_agent_name(agent)
    return {
        "agent_output_id": source_agent_output_id or f"{normalize_agent_name(agent)}_default",
        "run_id": run_id,
        "ticker": ticker,
        "agent": agent,
        "timestamp": _now(),
        "claim": "unknown",
        "evidence": "unknown",
        "entities": [str(ticker).upper()] if ticker else [],
        "factors": [],
        "direction": "unknown",
        "confidence": 0.0,
        "source_type": "unknown",
        "output_type": infer_output_type(agent),
        "source_agent_output_id": source_agent_output_id,
        "source_refs": [source_agent_output_id] if source_agent_output_id else [],
        "adapter_warning": reason,
        "adapter_error_code": error_code,
    }


# Log an error payload through the storage boundary.
def _log_error(run_id, output_root, payload):
    append_jsonl_record(run_id, ERROR_LOG_ARTIFACT_PATH, payload, output_root=output_root)


def _error_payload(run_id, ticker, raw_record, structured_record):
    return {
        "run_id": run_id,
        "ticker": ticker,
        "agent": structured_record.get("agent"),
        "source_agent_output_id": structured_record.get("source_agent_output_id"),
        "error_code": structured_record.get("adapter_error_code", "INVALID_STRUCTURED_OUTPUT"),
        "message": structured_record.get("adapter_warning", "Structured output adapter warning."),
        "raw_preview": _safe_preview(raw_record),
        "record_preview": _safe_preview(structured_record),
        "created_at": _now(),
    }

# Adapt a single raw agent output record into a structured claim record, handling validation and warnings
def adapt_raw_agent_output(raw_record, run_id, ticker):
    if not isinstance(raw_record, dict):
        return safe_default_record(
            run_id,
            ticker,
            "unknown_agent",
            "",
            "raw row is not an object",
            error_code="INVALID_RAW_RECORD",
        )
    agent = normalize_agent_name(raw_record.get("agent") or raw_record.get("tradingagents_agent"))
    raw_text = raw_record.get("raw_output")
    # Preserve traceability: the raw writer stamps every record with a stable
    # agent_output_id, so structured output should inherit it rather than mint
    # an unrelated identifier.
    source_agent_output_id = raw_record.get("agent_output_id")
    if not _normalize_text(raw_text):
        return safe_default_record(
            run_id,
            ticker,
            agent,
            raw_text,
            "raw output is empty",
            source_agent_output_id=source_agent_output_id,
            error_code="EMPTY_RAW_OUTPUT",
        )
    record = {
        "agent_output_id": source_agent_output_id
        or f"{agent}_{hashlib.sha1(_normalize_text(raw_text).encode('utf-8')).hexdigest()[:10]}",
        "run_id": run_id,
        "ticker": ticker,
        "agent": agent,
        "timestamp": _now(),
        "claim": extract_claim(raw_text),
        "evidence": extract_evidence(raw_text),
        "entities": extract_entities(raw_text, ticker),
        "factors": extract_factors(raw_text),
        "direction": normalize_direction(infer_direction(raw_text)),
        "confidence": estimate_confidence(raw_text),
        "source_type": infer_source_type(agent, raw_text),
        "output_type": infer_output_type(agent),
        "source_agent_output_id": source_agent_output_id,
        "source_refs": _normalize_source_refs(raw_record.get("source_refs"), source_agent_output_id),
    }
    if validate_structured_output(record):
        return record
    return safe_default_record(
        run_id,
        ticker,
        agent,
        raw_text,
        "structured record failed validation",
        source_agent_output_id=source_agent_output_id,
        error_code="STRUCTURED_VALIDATION_FAILED",
    )

# Adapt all raw agent output records in a run directory into structured claim records, logging any warnings
def adapt_run_outputs(run_dir):
    run_dir, run_id, output_root = _run_context_from_dir(run_dir)
    raw_payload = load_raw_agent_outputs(run_dir)
    ticker = str(raw_payload.get("ticker") or "unknown").upper()
    records = []
    for raw_record in raw_payload.get("agent_outputs", []):
        record = adapt_raw_agent_output(raw_record, run_id, ticker)
        if record.get("adapter_warning"):
            _log_error(run_id, output_root, _error_payload(run_id, ticker, raw_record, record))
        records.append(record)
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "records": records,
    }

# Save the adapted structured agent outputs to a JSON file in the run directory, returning the path
def save_structured_agent_outputs(run_dir):
    run_dir, run_id, output_root = _run_context_from_dir(run_dir)
    output = adapt_run_outputs(run_dir)
    return save_json_record(
        run_id,
        "structured_agent_outputs.json",
        output,
        output_root=output_root,
    )


def _main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    path = save_structured_agent_outputs(args.run_dir)
    print(path)


if __name__ == "__main__":
    _main()
