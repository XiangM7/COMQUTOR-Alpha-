"""Adapt TradingAgents raw output JSON into official structured claim records."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from comqutor_alpha.storage.file_store import (
    append_jsonl_record,
    load_json_record,
    save_json_record,
    validate_run_id_for_path,
)
from comqutor_alpha.structure_engine.claim_quality import (
    QUALITY_NON_SUBSTANTIVE,
    classify_claim_quality,
)
from comqutor_alpha.structure_engine.claim_semantics import analyze_claim_semantics
from comqutor_alpha.structure_engine.factor_normalizer import (
    extract_known_factors_from_text,
    normalize_factor_label,
)
from comqutor_alpha.structure_engine.structure_schema import (
    VALID_DIRECTIONS,
    clamp_score,
    normalize_direction,
)

# Constants for structured output schema and entity/factor extraction
SCHEMA_VERSION = "week1a.structured_agent_outputs.v2"
ADAPTER_VERSION = "week1.claim_extraction.v2"
ERROR_LOG_ARTIFACT_PATH = "error_logs/structured_output_adapter_errors.jsonl"
MAX_ERROR_PREVIEW_CHARS = 500
# Complete Claim Coverage Sprint: this is the maximum number of deterministic
# segments sent to the LLM in a single enrichment call -- it is a batch size,
# never a total-per-report cap. Deterministic segmentation (below) walks the
# entire raw report regardless of how many segments that produces; a report
# with more than this many substantive segments is simply split into
# multiple sequential batches (see `_chunk_segments`), every one of which is
# still fully processed (LLM-enriched or, on any batch validation failure,
# deterministically enriched as a per-batch fallback -- never dropped).
LLM_CLAIM_BATCH_SIZE = 64
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
    "not financial advice",
    "for informational purposes only",
    "past performance is not indicative",
)
# Stable reason codes for claims filtered at the extraction boundary. The
# filtered text never enters structured claims; only these codes (plus
# counts) are recorded for audit.
FILTER_REASON_BOILERPLATE = "BOILERPLATE_META_COMMENTARY"
FILTER_REASON_DISCLAIMER = "DISCLAIMER_ONLY"
FILTER_REASON_TRANSITION = "NON_ASSERTIVE_TRANSITION"

# First-person report-generation narration ("I now have all the data needed
# to compile a comprehensive report.", "Let me synthesize everything."). A
# sentence is only ever dropped by these when it ALSO lacks every
# substantive-signal marker below -- "Based on the data, revenue grew 20%"
# must survive.
_META_COMMENTARY_PATTERNS = (
    re.compile(
        r"(?i)\b(?:i|we)\s+(?:now\s+)?(?:have|will(?:\s+now)?|can(?:\s+now)?|am going to|"
        r"'m going to)\s+"
        r"(?:all\s+the\s+data|enough\s+(?:data|information)|the\s+(?:data|information)|"
        r"now\s+)?[^.!?]*"
        r"\b(?:compile|synthesize|synthesise|summarize|summarise|write|draft|produce|"
        r"present|prepare|proceed|begin|gather)\b"
    ),
    re.compile(
        r"(?i)^\s*(?:excellent|great|perfect|okay|ok|alright)?\s*[-—,.!]*\s*(?:now\s+)?"
        r"(?:let\s+me|let's|i\s+will|i'll|i\s+can\s+now|i\s+now\s+have)\b"
    ),
    re.compile(r"(?i)^\s*here\s+is\s+(?:the|a|my)\s+(?:comprehensive|full|final|complete)\b"),
    re.compile(r"(?i)\bi\s+now\s+have\s+(?:all\s+the|a\s+comprehensive|enough)\b"),
)
# Pure section-transition narration with no assertion of its own.
_TRANSITION_PATTERNS = (
    re.compile(r"(?i)^\s*(?:moving|turning)\s+(?:on\s+)?to\b"),
    re.compile(r"(?i)^\s*(?:now\s+)?(?:for|onto)\s+the\s+next\s+(?:section|part|topic)\b"),
    re.compile(r"(?i)^\s*(?:as|with)\s+(?:mentioned|noted|discussed)\s+(?:above|earlier|previously)\b[^a-z0-9]*$"),
)
# Substantive-signal markers: a sentence containing any of these is treated
# as a potential real claim and is never dropped as meta commentary or
# transition, no matter how it starts.
_SUBSTANTIVE_SIGNAL_PATTERN = re.compile(
    r"(?i)(?:\d|%|\$"
    r"|\b(?:revenue|earnings|margin|guidance|demand|supply|price|prices|pricing|valuation"
    r"|growth|decline|risk|rally|selloff|sell-off|upside|downside|bullish|bearish"
    r"|buy|sell|hold|underweight|overweight|capex|debt|cash|inventory|volume"
    r"|because|due to|driven by|leads to|supports|pressures|constrains|increases"
    r"|reduces|despite|headwind|tailwind|if|unless|could|may|might|would)\b)"
)


def classify_filtered_claim(text):
    """Return a stable filter reason code for a claim sentence, or None to keep it.

    Conservative by design: only pure meta commentary, pure transitions, and
    disclaimer sentences are filtered. Any sentence carrying a substantive
    signal (entity/metric/number/direction/causal/risk/conditional language)
    is kept even when it starts with narration like "Based on the data".
    """
    normalized = _normalize_text(text)
    lowered = normalized.lower()
    if not normalized:
        return None
    if any(marker in lowered for marker in DISCLAIMER_MARKERS):
        return FILTER_REASON_DISCLAIMER
    has_substance = bool(_SUBSTANTIVE_SIGNAL_PATTERN.search(normalized)) or bool(
        extract_known_factors_from_text(normalized)
    )
    if has_substance:
        return None
    if any(pattern.search(normalized) for pattern in _META_COMMENTARY_PATTERNS):
        return FILTER_REASON_BOILERPLATE
    if any(pattern.search(normalized) for pattern in _TRANSITION_PATTERNS):
        return FILTER_REASON_TRANSITION
    return None
LLM_STRUCTURED_AGENTS = {
    "market_agent",
    "technical_agent",
    "sentiment_agent",
    "news_agent",
    "fundamental_agent",
    "fundamentals_agent",
}


def _now():
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_text(value):
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
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
_LOCAL_ABSOLUTE_PATH_PATTERN = re.compile(
    r"(?i)(?:^|\s)(?:/users/|/home/|/private/|file://|[a-z]:\\users\\)"
)


def _redact_secrets(text):
    if not text:
        return text
    redacted = _SECRET_JSON_KV_PATTERN.sub(lambda m: f'"{m.group(1)}": "[REDACTED]"', text)
    redacted = _SECRET_KEY_VALUE_PATTERN.sub(lambda m: f"{m.group(1)}=[REDACTED]", redacted)
    redacted = _SECRET_BEARER_PATTERN.sub("Bearer [REDACTED]", redacted)
    redacted = _SECRET_SK_TOKEN_PATTERN.sub("[REDACTED]", redacted)
    return redacted


def contains_sensitive_text(value):
    """Detect obvious credentials or local absolute paths before persistence."""
    text = _normalize_text(value)
    return _redact_secrets(text) != text or bool(_LOCAL_ABSOLUTE_PATH_PATTERN.search(text))


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


def _is_table_separator_row(line):
    """A GFM table's own ``| --- | --- |`` / ``|:---:|---:|`` divider row --
    never a header, never a data row, never a claim."""
    stripped = line.strip()
    return bool(re.fullmatch(r"[:|\-\s]+", stripped)) and "-" in stripped


def _is_pipe_row(line):
    """A candidate table row: at least two pipe characters. A lone stray
    ``|`` in ordinary prose is deliberately not treated as tabular."""
    return line.strip().count("|") >= 2


def _split_table_cells(line):
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _table_row_text(cells, header_cells):
    """Render one table row as traceable claim text (Section D).

    When the row's cell count matches a confirmed header's cell count, emit
    a deterministic ``"Header: value"`` pairing per cell (never inventing
    data -- only real header/cell text is ever joined). When no confirmed
    header is available or the cell counts do not line up, fall back to the
    cleaned, pipe-joined raw row text. Empty/format-only rows render to the
    empty string so they are dropped by the same downstream
    meaningful-claim/word-count checks every other candidate segment goes
    through -- no special-cased "is this an empty table row" branch needed.
    """
    cleaned_cells = [_clean_markdown_inline(cell) for cell in cells]
    if not any(cell.strip() for cell in cleaned_cells):
        return ""
    if header_cells and len(header_cells) == len(cleaned_cells):
        cleaned_headers = [_clean_markdown_inline(header) for header in header_cells]
        if all(header.strip() for header in cleaned_headers):
            pairs = [
                f"{header.strip()}: {value.strip()}"
                for header, value in zip(cleaned_headers, cleaned_cells, strict=True)
                if value.strip()
            ]
            if pairs:
                return "; ".join(pairs)
    return " | ".join(cell for cell in cleaned_cells if cell.strip())


def _is_meaningful_claim(text):
    normalized = _normalize_text(text)
    lowered = normalized.lower()
    if len(normalized) < MIN_CLAIM_CHARS or len(normalized.split()) < 4:
        return False
    if any(marker in lowered for marker in DISCLAIMER_MARKERS):
        return False
    return bool(re.search(r"[A-Za-z0-9]", normalized))


def extract_claim_segments_with_audit(raw_text):
    """Split one raw Markdown report into complete, traceable claim segments.

    Returns ``(segments, filtered)`` where ``filtered`` records one entry
    (``{"reason_code": ...}``) per sentence removed at this boundary --
    boilerplate meta commentary, disclaimers, and pure transitions. The
    filtered text itself is never returned and never enters a structured
    claim. Disclaimers are filtered per-sentence, so a paragraph mixing real
    claims with a trailing disclaimer keeps the real claims.

    Complete Claim Coverage Sprint: this walks *every* block and sentence in
    the raw report -- there is no total-segment cap here (see
    ``LLM_CLAIM_BATCH_SIZE`` for the *separate*, LLM-batch-only limit applied
    later, in ``adapt_raw_agent_outputs``). Each returned segment also
    carries a stable, zero-based ``segment_index`` reflecting its true
    position in the full report, so claim numbering/ordering never depends
    on how segments are later chunked into LLM batches.

    Markdown pipe-tables are handled as three distinct row kinds (Section
    D): a separator row (``| --- | --- |``) is always ignored; a header row
    (the row immediately followed by a separator) is context only, never a
    claim on its own; every other table row is converted into a traceable
    claim segment (``"Header: value"`` pairs when the cell counts line up,
    else the cleaned raw row text).
    """
    if raw_text is None:
        return [], []
    if not isinstance(raw_text, str):
        raw_text = json.dumps(raw_text, ensure_ascii=False, default=str)
    raw_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    if not raw_text.strip():
        return [], []

    blocks = []
    paragraph = []
    section = None
    in_fence = False
    table_header_cells = None
    pending_header_row = None  # {"cells": [...], "section": ...}

    def flush_paragraph():
        if paragraph:
            blocks.append((section, " ".join(paragraph)))
            paragraph.clear()

    def end_table():
        """Ends the current table (if any): a pending, never-confirmed
        candidate header row is really just its own data row (no separator
        ever arrived to confirm it as a header), so it is emitted now."""
        nonlocal pending_header_row, table_header_cells
        if pending_header_row is not None:
            text = _table_row_text(pending_header_row["cells"], None)
            if text:
                blocks.append((pending_header_row["section"], text))
            pending_header_row = None
        table_header_cells = None

    for raw_line in raw_text.split("\n"):
        line = raw_line.strip()
        if line.startswith("```"):
            flush_paragraph()
            end_table()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line:
            flush_paragraph()
            end_table()
            continue

        if _is_table_separator_row(line):
            if pending_header_row is not None:
                table_header_cells = pending_header_row["cells"]
                pending_header_row = None
            # A separator with no pending header is inert formatting noise
            # either way -- never a claim.
            continue

        if _is_pipe_row(line):
            flush_paragraph()
            cells = _split_table_cells(line)
            if pending_header_row is not None:
                # The previous candidate header was never confirmed by a
                # separator -- it was not a real header after all.
                text = _table_row_text(pending_header_row["cells"], None)
                if text:
                    blocks.append((pending_header_row["section"], text))
                pending_header_row = None
            if table_header_cells is None:
                pending_header_row = {"cells": cells, "section": section}
            else:
                text = _table_row_text(cells, table_header_cells)
                if text:
                    blocks.append((section, text))
            continue

        # A non-pipe, non-separator line ends any active/pending table.
        end_table()

        heading = re.match(r"^#{1,6}\s+(.+)$", line)
        if heading:
            flush_paragraph()
            section = _clean_markdown_inline(heading.group(1))[:200] or None
            continue

        bullet = re.match(r"^(?:[-*+]\s+|\d+[.)]\s+)(.+)$", line)
        if bullet:
            flush_paragraph()
            blocks.append((section, bullet.group(1)))
            continue
        paragraph.append(line)

    flush_paragraph()
    end_table()

    segments = []
    filtered = []
    for block_section, block in blocks:
        cleaned_block = _clean_markdown_inline(block)
        sentences = re.split(r"(?<=[.!?。！？])\s+", cleaned_block)
        for sentence in sentences:
            claim = _clean_markdown_inline(sentence)
            reason_code = classify_filtered_claim(claim)
            if reason_code is not None:
                filtered.append({"reason_code": reason_code})
                continue
            if not _is_meaningful_claim(claim):
                continue
            segments.append(
                {
                    "claim": claim[:MAX_CLAIM_CHARS],
                    "evidence": claim[:MAX_CLAIM_CHARS],
                    "source_section": block_section,
                }
            )

    if not segments:
        fallback = _clean_markdown_inline(raw_text)
        if fallback and classify_filtered_claim(fallback) is None:
            segments.append(
                {
                    "claim": fallback[:MAX_CLAIM_CHARS],
                    "evidence": fallback[:MAX_CLAIM_CHARS],
                    "source_section": section,
                }
            )

    for index, segment in enumerate(segments):
        segment["segment_index"] = index

    return segments, filtered


def extract_claim_segments(raw_text):
    """Split one raw Markdown report into bounded, traceable claim segments."""
    segments, _filtered = extract_claim_segments_with_audit(raw_text)
    return segments


def extract_claim(raw_text):
    segments = extract_claim_segments(raw_text)
    return segments[0]["claim"] if segments else "unknown"


# ---------------------------------------------------------------------------
# Claim dedupe (Week 1a data-quality boundary)
# ---------------------------------------------------------------------------

_QUOTE_TRANSLATION = str.maketrans(
    {"‘": "'", "’": "'", "“": '"', "”": '"', "«": '"', "»": '"'}
)
_NUMBER_TOKEN_PATTERN = re.compile(r"\d+(?:[.,]\d+)*%?")


def normalize_claim_for_dedupe(text):
    """Deterministic claim normalization used only for duplicate grouping.

    Unicode NFKC, lowercase, whitespace collapse, unified quotes, and outer
    punctuation stripped. Numbers, percentages, tickers, and direction words
    are all preserved -- "Revenue increased 10%." and "Revenue increased
    20%." normalize to *different* keys.
    """
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    normalized = normalized.translate(_QUOTE_TRANSLATION).lower()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.strip(" \t\"'.,;:!?()[]")


def _claim_numeric_signature(normalized_claim):
    return tuple(sorted(_NUMBER_TOKEN_PATTERN.findall(normalized_claim)))


def _near_duplicate(record_a, record_b):
    """Conservative near-duplicate check for two records of the same agent.

    Never merges claims that differ in any numeric token, direction, or
    assertion status; otherwise requires near-identical token content
    (Jaccard >= 0.9 over word tokens). Never uses a lone global string
    similarity on raw text.
    """
    norm_a = record_a["_dedupe_key"]
    norm_b = record_b["_dedupe_key"]
    if record_a.get("direction") != record_b.get("direction"):
        return False
    if record_a.get("assertion_status") != record_b.get("assertion_status"):
        return False
    if _claim_numeric_signature(norm_a) != _claim_numeric_signature(norm_b):
        return False
    tokens_a = set(norm_a.split())
    tokens_b = set(norm_b.split())
    if not tokens_a or not tokens_b:
        return False
    union = tokens_a | tokens_b
    return len(tokens_a & tokens_b) / len(union) >= 0.9


def _record_quality_key(record):
    """Higher is better; deterministic tie-break by claim identity."""
    return (
        float(record.get("confidence") or 0.0),
        len(str(record.get("claim") or "")),
        # Negative index: earlier claims win ties, keeping output stable.
        -int(record.get("claim_index") or 0),
        str(record.get("claim_id") or ""),
    )


def dedupe_structured_records(records):
    """Merge duplicate claims without erasing cross-agent agreement.

    Boundaries (in order):
    1. Same ``source_agent_output_id``: exact/near duplicates merge; only the
       highest-quality record survives.
    2. Same ``agent`` across the run: duplicates merge; the survivor's
       ``merged_source_agent_output_ids`` records every merged source.
    3. Different agents expressing the same claim: both records survive
       (agent agreement is preserved) but share one ``duplicate_group_id``
       with ``merged_agents`` listing every supporting agent.

    Identity semantics are untouched: surviving records keep their original
    ``claim_id`` and ``source_agent_output_id``. Returns
    ``(deduped_records, removed_count)``.
    """
    annotated = []
    for record in records:
        entry = dict(record)
        entry["_dedupe_key"] = normalize_claim_for_dedupe(entry.get("claim"))
        annotated.append(entry)

    # Boundary 1 + 2: within one agent, group exact-normalized duplicates,
    # then fold conservative near-duplicates into those groups.
    survivors_by_agent: dict[str, list[dict]] = {}
    removed_count = 0
    for entry in annotated:
        agent = str(entry.get("agent") or "unknown_agent")
        groups = survivors_by_agent.setdefault(agent, [])
        merged_into = None
        for survivor in groups:
            if survivor["_dedupe_key"] == entry["_dedupe_key"] or _near_duplicate(survivor, entry):
                merged_into = survivor
                break
        if merged_into is None:
            entry["_merged_sources"] = {str(entry.get("source_agent_output_id") or "")}
            entry["_duplicate_count"] = 1
            groups.append(entry)
            continue
        removed_count += 1
        merged_into["_duplicate_count"] += 1
        source_id = str(entry.get("source_agent_output_id") or "")
        if source_id:
            merged_into["_merged_sources"].add(source_id)
        if _record_quality_key(entry) > _record_quality_key(merged_into):
            # Keep the higher-quality record's content/identity; carry the
            # accumulated provenance over.
            entry["_merged_sources"] = merged_into["_merged_sources"]
            entry["_duplicate_count"] = merged_into["_duplicate_count"]
            groups[groups.index(merged_into)] = entry

    survivors = [entry for groups in survivors_by_agent.values() for entry in groups]
    # Preserve original record order deterministically.
    order = {id(entry): index for index, entry in enumerate(annotated)}
    survivors.sort(key=lambda entry: order.get(id(entry), 0))

    # Boundary 3: cross-agent duplicate groups share an auditable group id
    # but every agent's own record is kept.
    by_key: dict[str, list[dict]] = {}
    for entry in survivors:
        by_key.setdefault(entry["_dedupe_key"], []).append(entry)

    deduped = []
    for entry in survivors:
        group = by_key[entry["_dedupe_key"]]
        group_agents = sorted({str(item.get("agent") or "") for item in group if item.get("agent")})
        record = {k: v for k, v in entry.items() if not k.startswith("_")}
        record["duplicate_group_id"] = (
            "dupgroup_" + hashlib.sha1(entry["_dedupe_key"].encode("utf-8")).hexdigest()[:12]
        )
        record["duplicate_count"] = entry["_duplicate_count"] + max(0, len(group) - 1)
        record["merged_source_agent_output_ids"] = sorted(entry["_merged_sources"] - {""})
        record["merged_agents"] = group_agents
        deduped.append(record)
    return deduped, removed_count


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
    required_text = (
        "claim_id",
        "source_agent_output_id",
        "run_id",
        "ticker",
        "agent",
        "claim",
        "evidence",
    )
    if any(not _normalize_text(record.get(field)) for field in required_text):
        return False
    if not isinstance(record.get("entities"), list):
        return False
    if not isinstance(record.get("factors"), list):
        return False
    if normalize_direction(record.get("direction")) not in VALID_DIRECTIONS:
        return False
    confidence = record.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return False
    confidence = float(confidence)
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        return False
    return record.get("source_refs") is None or isinstance(record.get("source_refs"), list)

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
    agent = normalize_agent_name(agent)
    normalized_raw = _normalize_text(raw_text)
    raw_id = source_agent_output_id
    if raw_id is None and normalized_raw:
        raw_id = f"{agent}_{hashlib.sha1(normalized_raw.encode('utf-8')).hexdigest()[:10]}"
    claim_base = raw_id or f"{agent}_default"
    claim_id = f"{claim_base}:claim:1"
    return {
        "claim_id": claim_id,
        "agent_output_id": claim_id,
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
        "source_agent_output_id": raw_id,
        "source_refs": [raw_id] if raw_id else [],
        "claim_index": 0,
        "source_section": None,
        "assertion_status": "unknown",
        "semantic_polarity": "unknown",
        "extraction_method": "deterministic_fallback",
        "adapter_warning": reason,
        "adapter_error_code": error_code,
        # Unified Claim Admissibility Sprint: an adapter-error placeholder is
        # never a real claim -- every downstream consumer must skip it via
        # the shared claim_quality.is_claim_eligible() gate, never a
        # per-module ad hoc "claim == 'unknown'" check.
        "claim_quality": QUALITY_NON_SUBSTANTIVE,
        "claim_quality_reason_codes": ["PLACEHOLDER_UNKNOWN"],
        "analysis_eligible": False,
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


def _chunk_segments(segments: list[dict[str, Any]], batch_size: int) -> list[list[dict[str, Any]]]:
    return [segments[start : start + batch_size] for start in range(0, len(segments), batch_size)]


# Section C's strict one-to-one enrichment contract: the LLM receives exactly
# these fields per segment (claim/evidence/source_section verbatim, plus its
# own stable segment_id) and must return exactly one enrichment item per
# segment_id it was given -- it may add entities/factors/direction/
# confidence, but it can never omit a segment, invent a new one, merge/split
# segments, or rewrite claim/evidence/source_section.
_LLM_BATCH_ENRICHMENT_REQUIRED_FIELDS = {
    "segment_id",
    "claim",
    "evidence",
    "entities",
    "factors",
    "direction",
    "confidence",
    "source_section",
}


def _validate_llm_batch_enrichment(
    payload: Mapping[str, Any], batch_segments: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Validate one LLM batch-enrichment response against its own input
    batch. Raises ``ValueError`` (causing the whole batch to fall back to
    deterministic enrichment -- see ``_llm_batch_enrichment``) on any
    violation. Returns ``{segment_id: {"entities", "factors", "direction",
    "confidence"}}`` covering every input segment_id exactly once.
    """
    if set(payload) != {"claims"}:
        raise ValueError("batch enrichment response has unexpected fields")
    claims = payload.get("claims")
    if not isinstance(claims, list) or len(claims) != len(batch_segments):
        raise ValueError("enrichment count must match input segment count exactly")

    by_id = {segment["segment_id"]: segment for segment in batch_segments}
    seen_ids: set[str] = set()
    enrichment_by_id: dict[str, dict[str, Any]] = {}

    for item in claims:
        if not isinstance(item, Mapping):
            raise ValueError("enrichment item must be an object")
        if set(item) != _LLM_BATCH_ENRICHMENT_REQUIRED_FIELDS:
            raise ValueError("enrichment item fields do not match the strict schema")

        segment_id = item.get("segment_id")
        if segment_id not in by_id:
            raise ValueError("enrichment item references an unknown segment_id")
        if segment_id in seen_ids:
            raise ValueError("enrichment item duplicates a segment_id")
        seen_ids.add(segment_id)
        source_segment = by_id[segment_id]

        # The LLM is only ever an enricher: claim/evidence/source_section
        # must come back byte-for-byte identical to what was sent, never
        # rewritten, merged, or split.
        if _normalize_text(item.get("claim")) != source_segment["claim"]:
            raise ValueError("enrichment item must preserve the input claim verbatim")
        if str(item.get("evidence") or "").strip() != source_segment["evidence"]:
            raise ValueError("enrichment item must preserve the input evidence verbatim")
        if item.get("source_section") != source_segment["source_section"]:
            raise ValueError("enrichment item must preserve the input source_section verbatim")

        entities = item.get("entities")
        factors = item.get("factors")
        if not isinstance(entities, list) or not isinstance(factors, list):
            raise ValueError("entities and factors must be lists")
        if len(entities) > 32 or len(factors) > 32:
            raise ValueError("entities or factors exceed bounds")

        raw_direction = str(item.get("direction") or "unknown").strip().lower()
        direction = normalize_direction(raw_direction)
        if direction == "unknown" and raw_direction not in {"", "unknown"}:
            raise ValueError("invalid direction")
        confidence = item.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ValueError("invalid confidence")
        confidence = float(confidence)
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between zero and one")

        enrichment_by_id[segment_id] = {
            "entities": [str(value)[:200] for value in entities if str(value).strip()],
            "factors": [str(value)[:200] for value in factors if str(value).strip()],
            "direction": direction,
            "confidence": confidence,
        }

    if seen_ids != set(by_id):
        raise ValueError("enrichment is missing one or more input segment_ids")

    return enrichment_by_id


def _llm_batch_enrichment(
    llm_gateway: Any,
    *,
    ticker: str,
    agent: str,
    batch_segments: list[dict[str, Any]],
) -> dict[str, dict[str, Any]] | None:
    if llm_gateway is None or not batch_segments:
        return None
    payload_segments = [
        {
            "segment_id": segment["segment_id"],
            "claim": segment["claim"],
            "evidence": segment["evidence"],
            "source_section": segment["source_section"],
        }
        for segment in batch_segments
    ]
    return llm_gateway.invoke_json(
        "claim_batch_enrichment",
        {"ticker": ticker, "agent": agent, "segments": payload_segments},
        lambda payload: _validate_llm_batch_enrichment(payload, batch_segments),
    )


def _normalized_values(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(str(value) for value in values if str(value).strip()))

def _build_records_from_segments(segments, raw_record, run_id, ticker, agent, raw_text, base_id, source_agent_output_id):
    """Build full structured records from one extraction path's segments.

    Every record is tagged with ``claim_quality``/``claim_quality_reason_codes``
    (Unified Claim Admissibility Sprint) via the single shared
    ``claim_quality.classify_claim_quality()`` gate -- the same gate applies
    regardless of whether ``segments`` came from the LLM or deterministic
    path, so the two extraction methods can never silently diverge in what
    they consider a real claim. Callers decide admission (this helper never
    drops a record itself, so its full output remains available for the
    LLM-all-rejected fallback decision).
    """
    records = []
    for segment in segments:
        index = segment["segment_index"]
        claim = segment["claim"]
        evidence = segment["evidence"]
        semantics = analyze_claim_semantics(f"{claim} {evidence}")
        claim_id = f"{base_id}:claim:{index + 1}"
        verified_entities = extract_entities(evidence, ticker)
        normalized_source = _normalize_text(evidence).lower()
        proposed_entities = [
            value
            for value in _normalized_values(segment.get("entities"))
            if value.lower() in normalized_source
        ]
        entities = [*proposed_entities, *verified_entities]
        verified_factors = extract_factors(evidence)
        factors = [
            normalize_factor_label(value)
            for value in _normalized_values(segment.get("factors"))
            if normalize_factor_label(value) in verified_factors
        ]
        factors.extend(verified_factors)
        direction = normalize_direction(segment.get("direction") or infer_direction(claim))
        entities = list(dict.fromkeys(entities))
        factors = list(dict.fromkeys(value for value in factors if value != "Unknown"))
        record = {
            "claim_id": claim_id,
            "agent_output_id": claim_id,
            "run_id": run_id,
            "ticker": ticker,
            "agent": agent,
            "timestamp": _now(),
            "claim": claim,
            "evidence": evidence,
            "entities": entities,
            "factors": factors,
            "direction": direction,
            "confidence": clamp_score(
                segment.get("confidence")
                if segment.get("confidence") is not None
                else estimate_confidence(claim)
            ),
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
            "extraction_method": segment.get("extraction_method", "deterministic_splitter"),
        }
        if validate_structured_output(record):
            quality = classify_claim_quality(
                claim,
                evidence,
                entities=entities,
                factors=factors,
                direction=direction,
                assertion_status=semantics.assertion_status,
            )
            record["claim_quality"] = quality.quality_class
            record["claim_quality_reason_codes"] = list(quality.reason_codes)
            record["analysis_eligible"] = quality.quality_class != QUALITY_NON_SUBSTANTIVE
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
        fallback["claim_id"] = claim_id
        fallback["agent_output_id"] = claim_id
        fallback["claim_index"] = index
        records.append(fallback)
    return records


def _tally_rejections(rejected_records, quality_audit):
    if quality_audit is None:
        return
    for record in rejected_records:
        for code in record.get("claim_quality_reason_codes") or ():
            quality_audit["reason_counts"][code] = quality_audit["reason_counts"].get(code, 0) + 1


# Adapt one raw agent output into structured claim records covering *every*
# deterministic segment in the report (Complete Claim Coverage Sprint).
#
# ``filter_audit`` (optional list) collects one ``{"reason_code": ...}``
# entry per sentence removed by the extraction-boundary quality filter.
# ``quality_audit`` (optional dict) accumulates this call's own coverage/
# quality counters -- see ``_new_quality_audit()``.
#
# Flow (Section C): complete deterministic segmentation is always computed
# first and is the sole source of truth for *which* segments exist and in
# what order. When the agent is LLM-eligible, segments are split into
# sequential batches of at most ``LLM_CLAIM_BATCH_SIZE``; each batch is
# independently sent for enrichment and independently validated
# one-to-one. A batch that fails validation (or returns no result) falls
# back to deterministic enrichment for *that batch only* -- every other
# batch's outcome, and every segment's own record, is unaffected. Non-LLM-
# eligible agents (or a disabled gateway) use the deterministic path for
# every segment directly.
def adapt_raw_agent_outputs(
    raw_record, run_id, ticker, *, llm_gateway=None, filter_audit=None, quality_audit=None
):
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

    base_id = source_agent_output_id or (
        f"{agent}_{hashlib.sha1(_normalize_text(raw_text).encode('utf-8')).hexdigest()[:10]}"
    )
    source_agent_output_id = str(base_id)

    segments, filtered = extract_claim_segments_with_audit(raw_text)
    if filter_audit is not None:
        filter_audit.extend(filtered)
    for segment in segments:
        segment["segment_id"] = f"{source_agent_output_id}:segment:{segment['segment_index']}"
    if quality_audit is not None:
        quality_audit["candidate_segment_count"] += len(segments)

    llm_eligible_agent = llm_gateway is not None and agent in LLM_STRUCTURED_AGENTS

    all_records: list[dict[str, Any]] = []
    for batch in _chunk_segments(segments, LLM_CLAIM_BATCH_SIZE):
        batch_records = None
        if llm_eligible_agent:
            if quality_audit is not None:
                quality_audit["llm_batch_count"] += 1
            enrichment = _llm_batch_enrichment(
                llm_gateway, ticker=ticker, agent=agent, batch_segments=batch
            )
            if enrichment is not None:
                enriched_batch = []
                for segment in batch:
                    merged = dict(segment)
                    item = enrichment[segment["segment_id"]]
                    merged["entities"] = item["entities"]
                    merged["factors"] = item["factors"]
                    merged["direction"] = item["direction"]
                    merged["confidence"] = item["confidence"]
                    merged["extraction_method"] = "llm_strict_json"
                    enriched_batch.append(merged)
                batch_records = _build_records_from_segments(
                    enriched_batch, raw_record, run_id, ticker, agent, raw_text, base_id, source_agent_output_id
                )
            elif quality_audit is not None:
                quality_audit["llm_batch_fallback_count"] += 1

        if batch_records is None:
            det_batch = []
            for segment in batch:
                merged = dict(segment)
                merged["extraction_method"] = "deterministic_splitter"
                det_batch.append(merged)
            batch_records = _build_records_from_segments(
                det_batch, raw_record, run_id, ticker, agent, raw_text, base_id, source_agent_output_id
            )
        all_records.extend(batch_records)

    eligible_records = [r for r in all_records if r["claim_quality"] != QUALITY_NON_SUBSTANTIVE]
    rejected_records = [r for r in all_records if r["claim_quality"] == QUALITY_NON_SUBSTANTIVE]
    if quality_audit is not None:
        llm_records = [r for r in all_records if r["extraction_method"] == "llm_strict_json"]
        llm_rejected = [r for r in rejected_records if r["extraction_method"] == "llm_strict_json"]
        det_rejected = [r for r in rejected_records if r["extraction_method"] != "llm_strict_json"]
        quality_audit["llm_claims_proposed_count"] += len(llm_records)
        quality_audit["llm_claims_removed_count"] += len(llm_rejected)
        quality_audit["deterministic_claims_removed_count"] += len(det_rejected)
    _tally_rejections(rejected_records, quality_audit)

    if not eligible_records:
        return [safe_default_record(
            run_id,
            ticker,
            agent,
            raw_text,
            "raw output contains no meaningful claims",
            source_agent_output_id=source_agent_output_id,
            error_code="NO_MEANINGFUL_CLAIMS",
        )]
    return eligible_records


# Preserve the original single-record helper for existing callers.
def adapt_raw_agent_output(raw_record, run_id, ticker, *, llm_gateway=None):
    return adapt_raw_agent_outputs(
        raw_record,
        run_id,
        ticker,
        llm_gateway=llm_gateway,
    )[0]

def _new_quality_audit():
    """Fresh, per-call accumulator -- one instance per raw agent output, so
    ``adapt_run_outputs`` can both sum these into run-level metadata and
    keep a per-agent breakdown (Section E's coverage-audit requirement)."""
    return {
        "llm_claims_proposed_count": 0,
        "llm_claims_removed_count": 0,
        "deterministic_claims_removed_count": 0,
        "llm_batch_count": 0,
        "llm_batch_fallback_count": 0,
        "candidate_segment_count": 0,
        "reason_counts": {},
    }


_AUDIT_SUM_KEYS = (
    "llm_claims_proposed_count",
    "llm_claims_removed_count",
    "deterministic_claims_removed_count",
    "llm_batch_count",
    "llm_batch_fallback_count",
    "candidate_segment_count",
)


def _add_quality_audit(target, source):
    for key in _AUDIT_SUM_KEYS:
        target[key] += source[key]
    for code, count in source["reason_counts"].items():
        target["reason_counts"][code] = target["reason_counts"].get(code, 0) + count


# Adapt all raw agent output records in a run directory into structured claim records, logging any warnings
def adapt_run_outputs(run_dir, *, llm_gateway=None):
    run_dir, run_id, output_root = _run_context_from_dir(run_dir)
    raw_payload = load_raw_agent_outputs(run_dir)
    ticker = str(raw_payload.get("ticker") or "unknown").upper()
    records = []
    filter_audit: list[dict[str, Any]] = []
    global_audit = _new_quality_audit()
    # Section E: per-agent coverage breakdown. Keyed by normalized agent
    # name; multiple raw outputs for the same agent are aggregated (their
    # original source_agent_output_id provenance stays on each record
    # regardless -- this bucket is a count-only rollup).
    per_agent: dict[str, dict[str, Any]] = {}

    raw_agent_outputs = raw_payload.get("agent_outputs", []) or []
    for raw_record in raw_agent_outputs:
        agent_key = normalize_agent_name(
            (raw_record.get("agent") or raw_record.get("tradingagents_agent"))
            if isinstance(raw_record, dict)
            else "unknown_agent"
        )
        call_audit = _new_quality_audit()
        filter_start = len(filter_audit)
        adapted_records = adapt_raw_agent_outputs(
            raw_record,
            run_id,
            ticker,
            llm_gateway=llm_gateway,
            filter_audit=filter_audit,
            quality_audit=call_audit,
        )
        call_filtered = filter_audit[filter_start:]

        bucket = per_agent.setdefault(
            agent_key,
            {
                "agent": agent_key,
                "raw_output_count": 0,
                "boilerplate_removed": 0,
                "disclaimer_removed": 0,
            },
        )
        bucket["raw_output_count"] += 1
        for item in call_filtered:
            code = str(item.get("reason_code") or "UNKNOWN")
            if code == FILTER_REASON_DISCLAIMER:
                bucket["disclaimer_removed"] += 1
            else:
                bucket["boilerplate_removed"] += 1
        _add_quality_audit(bucket.setdefault("_audit", _new_quality_audit()), call_audit)
        _add_quality_audit(global_audit, call_audit)

        for record in adapted_records:
            if record.get("adapter_warning"):
                _log_error(
                    run_id,
                    output_root,
                    _error_payload(run_id, ticker, raw_record, record),
                )
            records.append(record)

    raw_claim_count = len(records)  # legacy pre-dedup count, kept for backward compatibility
    pre_dedup_by_agent: dict[str, int] = {}
    for record in records:
        agent_key = str(record.get("agent") or "unknown_agent")
        pre_dedup_by_agent[agent_key] = pre_dedup_by_agent.get(agent_key, 0) + 1

    records, duplicate_removed_count = dedupe_structured_records(records)

    post_dedup_by_agent: dict[str, int] = {}
    for record in records:
        agent_key = str(record.get("agent") or "unknown_agent")
        post_dedup_by_agent[agent_key] = post_dedup_by_agent.get(agent_key, 0) + 1

    filter_reason_counts: dict[str, int] = {}
    for item in filter_audit:
        code = str(item.get("reason_code") or "UNKNOWN")
        filter_reason_counts[code] = filter_reason_counts.get(code, 0) + 1

    analytical_claim_count = sum(1 for record in records if record.get("claim_quality") == "analytical")
    context_only_claim_count = sum(1 for record in records if record.get("claim_quality") == "context_only")
    non_substantive_removed_count = (
        global_audit["llm_claims_removed_count"] + global_audit["deterministic_claims_removed_count"]
    )
    boilerplate_removed_count = (
        filter_reason_counts.get(FILTER_REASON_BOILERPLATE, 0)
        + filter_reason_counts.get(FILTER_REASON_TRANSITION, 0)
    )
    disclaimer_removed_count = filter_reason_counts.get(FILTER_REASON_DISCLAIMER, 0)
    candidate_segment_count = global_audit["candidate_segment_count"]
    # Derived directly from segmentation/quality-gate tallies (never from
    # len(records)): candidate segments minus the ones the quality gate
    # rejected as non-substantive -- this stays exact even in the edge case
    # where a whole raw output's segments are all non-substantive (that
    # raw output then contributes a single NO_MEANINGFUL_CLAIMS placeholder
    # record instead of its rejected segments' own records).
    retained_claim_count = candidate_segment_count - non_substantive_removed_count
    filtered_claim_count = boilerplate_removed_count + disclaimer_removed_count + non_substantive_removed_count
    # The total-per-report segmentation cap that used to silently drop
    # everything past the 65th sentence no longer exists (see
    # LLM_CLAIM_BATCH_SIZE's docstring) -- there is no remaining code path
    # in this module that can silently truncate a report's coverage.
    truncated_claim_count = 0
    coverage_complete = truncated_claim_count == 0

    agent_coverage = []
    for agent_key, bucket in sorted(per_agent.items()):
        audit = bucket["_audit"]
        agent_candidate = audit["candidate_segment_count"]
        agent_non_substantive = audit["llm_claims_removed_count"] + audit["deterministic_claims_removed_count"]
        agent_filtered = bucket["boilerplate_removed"] + bucket["disclaimer_removed"] + agent_non_substantive
        agent_retained = agent_candidate - agent_non_substantive
        agent_coverage.append(
            {
                "agent": agent_key,
                "raw_output_count": bucket["raw_output_count"],
                "candidate_segment_count": agent_candidate,
                "retained_claim_count": agent_retained,
                "filtered_claim_count": agent_filtered,
                "duplicate_removed_count": (
                    pre_dedup_by_agent.get(agent_key, 0) - post_dedup_by_agent.get(agent_key, 0)
                ),
                "truncated_claim_count": 0,
                "llm_batch_count": audit["llm_batch_count"],
                "llm_batch_fallback_count": audit["llm_batch_fallback_count"],
                "coverage_complete": True,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "records": records,
        "metadata": {
            "llm_enabled": llm_gateway is not None,
            "llm_record_count": sum(
                record.get("extraction_method") == "llm_strict_json" for record in records
            ),
            "raw_output_count": len(raw_agent_outputs),
            "raw_claim_count": raw_claim_count,
            "candidate_segment_count": candidate_segment_count,
            "retained_claim_count": retained_claim_count,
            "filtered_claim_count": filtered_claim_count,
            "boilerplate_removed_count": boilerplate_removed_count,
            "disclaimer_removed_count": disclaimer_removed_count,
            "duplicate_removed_count": duplicate_removed_count,
            "truncated_claim_count": truncated_claim_count,
            "coverage_complete": coverage_complete,
            "filter_reason_counts": filter_reason_counts,
            # Unified Claim Admissibility and Context-Only Routing Sprint:
            # additive quality-gate counters, computed from the SAME gate
            # both extraction paths go through (see claim_quality.py).
            "analytical_claim_count": analytical_claim_count,
            "context_only_claim_count": context_only_claim_count,
            "non_substantive_removed_count": non_substantive_removed_count,
            "llm_claims_proposed_count": global_audit["llm_claims_proposed_count"],
            "llm_claims_removed_count": global_audit["llm_claims_removed_count"],
            "deterministic_claims_removed_count": global_audit["deterministic_claims_removed_count"],
            "llm_batch_count": global_audit["llm_batch_count"],
            "llm_batch_fallback_count": global_audit["llm_batch_fallback_count"],
            "quality_reason_counts": global_audit["reason_counts"],
            "agent_coverage": agent_coverage,
        },
    }

# Save the adapted structured agent outputs to a JSON file in the run directory, returning the path
def save_structured_agent_outputs(run_dir, *, llm_gateway=None):
    run_dir, run_id, output_root = _run_context_from_dir(run_dir)
    output = adapt_run_outputs(run_dir, llm_gateway=llm_gateway)
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
