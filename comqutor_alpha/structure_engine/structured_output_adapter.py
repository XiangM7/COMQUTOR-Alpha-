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
from comqutor_alpha.structure_engine.claim_semantics import analyze_claim_semantics
from comqutor_alpha.structure_engine.factor_normalizer import extract_known_factors_from_text
from comqutor_alpha.structure_engine.structure_schema import (
    VALID_DIRECTIONS,
    clamp_score,
    normalize_direction,
)

# Constants for structured output schema and entity/factor extraction
SCHEMA_VERSION = "week1a.structured_agent_outputs.v1"
ERROR_LOG_ARTIFACT_PATH = "error_logs/structured_output_adapter_errors.jsonl"
MAX_ERROR_PREVIEW_CHARS = 500
MAX_CLAIMS_PER_RAW_OUTPUT = 64
MAX_CLAIM_CHARS = 1200
MIN_CLAIM_CHARS = 20
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
DISCLAIMER_MARKERS = (
    "disclaimer",
    "not investment advice",
    "for informational purposes only",
    "past performance is not indicative",
)


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


# Redact obvious secret-like tokens (api keys, bearer tokens, passwords) from
# error log previews. This is a simple, deterministic best-effort filter for
# debugging safety, not a full secret scanner.
_SECRET_KEY_VALUE_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*(\S+)"
)
# Quoted JSON-style secrets, e.g. `"api_key": "sk-abc123"` (raw records are
# often previewed as json.dumps() output, so the key/value are both
# double-quoted and the plain key=value pattern above cannot match).
_SECRET_JSON_KV_PATTERN = re.compile(
    r'(?i)"(api[_-]?key|secret|token|password)"\s*:\s*"[^"]*"'
)
_SECRET_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+(\S+)")
_SECRET_SK_TOKEN_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{3,}")


def _redact_secrets(text):
    if not text:
        return text
    redacted = _SECRET_JSON_KV_PATTERN.sub(lambda m: f'"{m.group(1)}": "[REDACTED]"', text)
    redacted = _SECRET_KEY_VALUE_PATTERN.sub(lambda m: f"{m.group(1)}=[REDACTED]", redacted)
    redacted = _SECRET_BEARER_PATTERN.sub("Bearer [REDACTED]", redacted)
    redacted = _SECRET_SK_TOKEN_PATTERN.sub("[REDACTED]", redacted)
    return redacted


def _safe_preview(value, max_chars=MAX_ERROR_PREVIEW_CHARS):
    preview = _redact_secrets(_normalize_text(value))
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

def _clean_markdown_inline(text):
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", str(text or ""))
    text = re.sub(r"[`*_~]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_table_line(line):
    stripped = line.strip()
    if stripped.count("|") >= 2:
        return True
    return bool(re.fullmatch(r"[:|\-\s]+", stripped)) and "-" in stripped


def _is_meaningful_claim(text):
    normalized = _normalize_text(text)
    lowered = normalized.lower()
    if len(normalized) < MIN_CLAIM_CHARS or len(normalized.split()) < 4:
        return False
    if any(marker in lowered for marker in DISCLAIMER_MARKERS):
        return False
    if not re.search(r"[A-Za-z0-9]", normalized):
        return False
    return True


def extract_claim_segments(raw_text):
    """Split one raw Markdown report into bounded, traceable claim segments."""
    if raw_text is None:
        return []
    if not isinstance(raw_text, str):
        raw_text = json.dumps(raw_text, ensure_ascii=False, default=str)
    raw_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    if not raw_text.strip():
        return []

    blocks = []
    paragraph = []
    section = None
    in_fence = False

    def flush_paragraph():
        if paragraph:
            blocks.append((section, " ".join(paragraph)))
            paragraph.clear()

    for raw_line in raw_text.split("\n"):
        line = raw_line.strip()
        if line.startswith("```"):
            flush_paragraph()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line:
            flush_paragraph()
            continue

        heading = re.match(r"^#{1,6}\s+(.+)$", line)
        if heading:
            flush_paragraph()
            section = _clean_markdown_inline(heading.group(1))[:200] or None
            continue
        if _is_table_line(line):
            flush_paragraph()
            continue
        if any(marker in line.lower() for marker in DISCLAIMER_MARKERS):
            flush_paragraph()
            continue

        bullet = re.match(r"^(?:[-*+]\s+|\d+[.)]\s+)(.+)$", line)
        if bullet:
            flush_paragraph()
            blocks.append((section, bullet.group(1)))
            continue
        paragraph.append(line)

    flush_paragraph()

    segments = []
    for block_section, block in blocks:
        cleaned_block = _clean_markdown_inline(block)
        sentences = re.split(r"(?<=[.!?。！？])\s+", cleaned_block)
        for sentence in sentences:
            claim = _clean_markdown_inline(sentence)
            if not _is_meaningful_claim(claim):
                continue
            segments.append(
                {
                    "claim": claim[:MAX_CLAIM_CHARS],
                    "evidence": claim[:MAX_CLAIM_CHARS],
                    "source_section": block_section,
                }
            )
            if len(segments) >= MAX_CLAIMS_PER_RAW_OUTPUT:
                return segments

    if not segments:
        fallback = _clean_markdown_inline(raw_text)
        if fallback and not any(marker in fallback.lower() for marker in DISCLAIMER_MARKERS):
            segments.append(
                {
                    "claim": fallback[:MAX_CLAIM_CHARS],
                    "evidence": fallback[:MAX_CLAIM_CHARS],
                    "source_section": section,
                }
            )
    return segments


def extract_claim(raw_text):
    segments = extract_claim_segments(raw_text)
    return segments[0]["claim"] if segments else "unknown"


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
    return extract_known_factors_from_text(_normalize_text(raw_text))

# Infer the direction of the claim based on the presence of positive, negative, and neutral words
def infer_direction(raw_text):
    text = _normalize_text(raw_text).lower()
    if not text:
        return "unknown"
    semantics = analyze_claim_semantics(text)
    if semantics.semantic_polarity == "risk_relief":
        return "positive"
    if semantics.semantic_polarity == "invalidation":
        return "negative"
    if semantics.mixed or semantics.negated:
        return "neutral"
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
        "assertion_status": "unknown",
        "semantic_polarity": "unknown",
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

# Adapt one raw agent output into one or more structured claim records.
def adapt_raw_agent_outputs(raw_record, run_id, ticker):
    if not isinstance(raw_record, dict):
        return [safe_default_record(
            run_id,
            ticker,
            "unknown_agent",
            "",
            "raw row is not an object",
            error_code="INVALID_RAW_RECORD",
        )]
    agent = normalize_agent_name(raw_record.get("agent") or raw_record.get("tradingagents_agent"))
    raw_text = raw_record.get("raw_output")
    # Preserve traceability: the raw writer stamps every record with a stable
    # agent_output_id, so structured output should inherit it rather than mint
    # an unrelated identifier.
    source_agent_output_id = raw_record.get("agent_output_id")
    if not _normalize_text(raw_text):
        return [safe_default_record(
            run_id,
            ticker,
            agent,
            raw_text,
            "raw output is empty",
            source_agent_output_id=source_agent_output_id,
            error_code="EMPTY_RAW_OUTPUT",
        )]

    segments = extract_claim_segments(raw_text)
    if not segments:
        return [safe_default_record(
            run_id,
            ticker,
            agent,
            raw_text,
            "raw output contains no meaningful claims",
            source_agent_output_id=source_agent_output_id,
            error_code="NO_MEANINGFUL_CLAIMS",
        )]

    base_id = source_agent_output_id or (
        f"{agent}_{hashlib.sha1(_normalize_text(raw_text).encode('utf-8')).hexdigest()[:10]}"
    )
    records = []
    for index, segment in enumerate(segments):
        claim = segment["claim"]
        semantics = analyze_claim_semantics(claim)
        record_id = base_id if len(segments) == 1 else f"{base_id}:claim:{index + 1}"
        record = {
            "agent_output_id": record_id,
            "run_id": run_id,
            "ticker": ticker,
            "agent": agent,
            "timestamp": _now(),
            "claim": claim,
            "evidence": segment["evidence"],
            "entities": extract_entities(claim, ticker),
            "factors": extract_factors(claim),
            "direction": normalize_direction(infer_direction(claim)),
            "confidence": estimate_confidence(claim),
            "source_type": infer_source_type(agent, claim),
            "output_type": infer_output_type(agent),
            "source_agent_output_id": source_agent_output_id,
            "source_refs": _normalize_source_refs(
                raw_record.get("source_refs"), source_agent_output_id
            ),
            "claim_index": index,
            "source_section": segment.get("source_section"),
            "assertion_status": semantics.assertion_status,
            "semantic_polarity": semantics.semantic_polarity,
        }
        if validate_structured_output(record):
            records.append(record)
            continue
        fallback = safe_default_record(
            run_id,
            ticker,
            agent,
            raw_text,
            "structured record failed validation",
            source_agent_output_id=source_agent_output_id,
            error_code="STRUCTURED_VALIDATION_FAILED",
        )
        fallback["agent_output_id"] = record_id
        fallback["claim_index"] = index
        records.append(fallback)
    return records


# Preserve the original single-record helper for existing callers.
def adapt_raw_agent_output(raw_record, run_id, ticker):
    return adapt_raw_agent_outputs(raw_record, run_id, ticker)[0]

# Adapt all raw agent output records in a run directory into structured claim records, logging any warnings
def adapt_run_outputs(run_dir):
    run_dir, run_id, output_root = _run_context_from_dir(run_dir)
    raw_payload = load_raw_agent_outputs(run_dir)
    ticker = str(raw_payload.get("ticker") or "unknown").upper()
    records = []
    for raw_record in raw_payload.get("agent_outputs", []):
        adapted_records = adapt_raw_agent_outputs(raw_record, run_id, ticker)
        for record in adapted_records:
            if record.get("adapter_warning"):
                _log_error(
                    run_id,
                    output_root,
                    _error_payload(run_id, ticker, raw_record, record),
                )
            records.append(record)
    return {
        "schema_version": SCHEMA_VERSION,
        "adapter_version": "week1.claim_splitter.v2",
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
