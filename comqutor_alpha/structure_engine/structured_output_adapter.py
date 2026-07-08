"""Adapt TradingAgents raw output JSON into official structured claim records."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from comqutor_alpha.storage.file_store import atomic_write_text
from comqutor_alpha.structure_engine.structure_schema import clamp_score, normalize_direction


SCHEMA_VERSION = "week1a.structured_agent_outputs.v1"
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


def load_raw_agent_outputs(run_dir):
    with (Path(run_dir) / "raw_agent_outputs.json").open(encoding="utf-8") as f:
        return json.load(f)


def normalize_agent_name(agent):
    return str(agent or "unknown_agent").strip().lower().replace(" ", "_")


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


def validate_structured_output(record):
    required = {"run_id", "ticker", "agent", "claim", "evidence"}
    return all(record.get(field) for field in required)


def safe_default_record(run_id, ticker, agent, raw_text, reason, source_agent_output_id=None):
    del raw_text
    return {
        "agent_output_id": source_agent_output_id or f"{normalize_agent_name(agent)}_default",
        "run_id": run_id,
        "ticker": ticker,
        "agent": normalize_agent_name(agent),
        "timestamp": _now(),
        "claim": "unknown",
        "evidence": "unknown",
        "entities": [str(ticker).upper()] if ticker else [],
        "factors": [],
        "direction": "unknown",
        "confidence": 0.0,
        "source_type": "unknown",
        "source_refs": [source_agent_output_id] if source_agent_output_id else [],
        "adapter_warning": reason,
    }


def _log_error(run_dir, payload):
    log_dir = Path(run_dir) / "error_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "structured_output_adapter_errors.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def adapt_raw_agent_output(raw_record, run_id, ticker):
    if not isinstance(raw_record, dict):
        return safe_default_record(run_id, ticker, "unknown_agent", "", "raw row is not an object")
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
        "source_refs": [source_agent_output_id] if source_agent_output_id else [],
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
    )


def adapt_run_outputs(run_dir):
    run_dir = Path(run_dir)
    raw_payload = load_raw_agent_outputs(run_dir)
    run_id = str(raw_payload.get("run_id") or run_dir.name)
    ticker = str(raw_payload.get("ticker") or "unknown").upper()
    records = []
    for raw_record in raw_payload.get("agent_outputs", []):
        record = adapt_raw_agent_output(raw_record, run_id, ticker)
        if record.get("adapter_warning"):
            _log_error(run_dir, {"agent": record.get("agent"), "warning": record["adapter_warning"]})
        records.append(record)
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "records": records,
    }


def save_structured_agent_outputs(run_dir):
    run_dir = Path(run_dir)
    output = adapt_run_outputs(run_dir)
    output_path = run_dir / "structured_agent_outputs.json"
    atomic_write_text(output_path, json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def _main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    path = save_structured_agent_outputs(args.run_dir)
    print(path)


if __name__ == "__main__":
    _main()
