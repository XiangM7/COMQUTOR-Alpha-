"""Adapt TradingAgents raw output JSON into official structured claim records."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import unicodedata
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from comqutor_alpha.structure_engine.content_support_llm import apply_llm_content_support_verification
from comqutor_alpha.source_provenance import (
    REVIEW_METHOD_AGENT_CITED_UNVERIFIED_SUPPORT,
    REVIEW_METHOD_ORIGINAL_AGENT_CITED_UNVERIFIED_SUPPORT,
    REVIEW_METHOD_UNREVIEWED,
    REVIEW_METHOD_UNVERIFIED_OFFLINE_CONTENT_MATCH,
    SOURCE_LINK_NOT_PROVIDED,
    SOURCE_LINK_VALID,
    SUPPORT_NOT_APPLICABLE,
    SUPPORT_PENDING_REVIEW,
    apply_automated_content_support_verification,
    build_content_support_review,
    extract_all_source_markers_from_text,
    extract_source_marker_from_text,
    match_evidence_to_source_candidates,
    match_evidence_to_source_candidates_normalized,
    public_source_fields,
    resolve_evidence_cutoff_at,
    validate_source_reference,
)
from comqutor_alpha.storage.file_store import (
    append_jsonl_record,
    load_json_record,
    load_json_record_if_exists,
    save_json_record,
    validate_run_id_for_path,
)
from comqutor_alpha.structure_engine.canonical_relation_block import (
    resolve_relation_source_claims,
    split_human_text_and_canonical_block,
    validate_canonical_relations,
)
from comqutor_alpha.structure_engine.canonical_relation_prompt import RELATION_BLOCK_MARKER
from comqutor_alpha.structure_engine.canonical_vocabulary import build_canonical_relation_vocabulary
from comqutor_alpha.structure_engine.claim_quality import (
    QUALITY_NON_SUBSTANTIVE,
    classify_claim_quality,
)
from comqutor_alpha.structure_engine.claim_semantics import analyze_claim_semantics
from comqutor_alpha.structure_engine.derived_fact_verification import verify_percent_comparison_claim
from comqutor_alpha.structure_engine.factor_normalizer import (
    extract_known_factors_from_text,
    normalize_factor_label,
)
from comqutor_alpha.structure_engine.week2_llm import resolve_structured_adapter_concurrency
from comqutor_alpha.structure_engine.week2_llm import _selected_profile_or_none as _selected_week2_execution_profile
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
    # Day 3 (MSFT-A102-DIRECT-INFERENCE-TRIGGER root-cause fix): a
    # pricing-power/competitive-moat metaphor ("toll booth on the highway
    # of X") is common cross-ticker bullish framing that the prior list had
    # no coverage for at all, leaving affected claims at direction=unknown
    # regardless of ticker -- not an MSFT-specific term.
    "toll booth",
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


# Round 3 (2026-10-04), section 3: "只提供本步骤实际可见的相关依据,不把整个
# run注册表无差别塞进每个请求" -- derived from a direct read of each real
# TradingAgents node's own prompt-building code (not a guess):
#   - market_analyst.py / news_analyst.py / fundamentals_analyst.py each
#     build their prompt EXCLUSIVELY from their own tool-call loop
#     (state["messages"]) -- confirmed by direct read, none of the three
#     reads another analyst's report field at all. Each is therefore only
#     legitimately offered the ONE source_type its own tools produce.
#   - sentiment_analyst.py / social_media_analyst.py: same self-contained
#     shape, but this round captures no source_type for either (out of
#     scope, unchanged) -- empty visible set, never the whole registry.
#   - bull_researcher.py / bear_researcher.py: read market_report +
#     sentiment_report + news_report + fundamentals_report directly.
#   - research_manager.py: reads ONLY investment_debate_state.history (the
#     bull/bear debate text) -- transitively the SAME union the debate
#     itself was given, never a NEW direct source.
#   - trader.py: reads ONLY investment_plan (research_manager's own
#     output) -- same transitive union again, never a new direct source.
#   - aggressive/conservative/neutral risk debators: read all 4 raw
#     reports directly PLUS trader_investment_plan.
#   - portfolio_manager.py: reads risk_debate_state history +
#     investment_plan + trader_investment_plan -- same transitive union.
# Every downstream (non-analyst) agent therefore shares the exact same
# union -- there is no finer-grained split available without rebuilding
# the graph's own text-chaining architecture (out of scope this round).
# "macro" is offered to the SAME agents as "news" (get_macro_indicators is
# one of news_analyst's own tools, confirmed by direct read of
# news_analyst.py's tool list).
_DOWNSTREAM_VISIBLE_SOURCE_TYPES = frozenset({"market", "news", "macro", "financial"})
_AGENT_VISIBLE_SOURCE_TYPES: dict[str, frozenset[str]] = {
    "market_agent": frozenset({"market"}),
    "news_agent": frozenset({"news", "macro"}),
    "sentiment_agent": frozenset(),
    "social_media_agent": frozenset(),
    "fundamental_agent": frozenset({"financial"}),
    "bull_researcher": _DOWNSTREAM_VISIBLE_SOURCE_TYPES,
    "bear_researcher": _DOWNSTREAM_VISIBLE_SOURCE_TYPES,
    "research_manager": _DOWNSTREAM_VISIBLE_SOURCE_TYPES,
    "trader": _DOWNSTREAM_VISIBLE_SOURCE_TYPES,
    "aggressive_risk_analyst": _DOWNSTREAM_VISIBLE_SOURCE_TYPES,
    "conservative_risk_analyst": _DOWNSTREAM_VISIBLE_SOURCE_TYPES,
    "neutral_risk_analyst": _DOWNSTREAM_VISIBLE_SOURCE_TYPES,
    "portfolio_manager": _DOWNSTREAM_VISIBLE_SOURCE_TYPES,
}


def visible_source_types_for_agent(agent: str) -> frozenset[str] | None:
    """Returns the set of ``source_type``s legitimately visible to
    ``agent`` at the step that produced its raw_output, or ``None`` for an
    agent not in the known map (a future/unrecognized agent name --
    ``None`` means "do not scope, pass the full registry unchanged",
    strictly more permissive than an empty set, so an unrecognized agent
    is never silently starved of every source it might legitimately need;
    see ``scope_sources_for_agent``)."""
    return _AGENT_VISIBLE_SOURCE_TYPES.get(normalize_agent_name(agent))


def scope_sources_for_agent(
    agent: str, sources: list[dict[str, Any]] | None
) -> list[dict[str, Any]] | None:
    """Filters ``sources`` down to only the entries whose ``source_type``
    was actually visible to ``agent`` at generation time (see
    ``visible_source_types_for_agent``'s own derivation). A source that
    exists in this run's registry but was never shown to THIS agent can
    therefore never be accepted as this agent's own explicit citation or
    content-match candidate -- closing the exact gap John 下一轮开发任务单
    section 3 point 5 names: "整个registry里存在但该步骤未提供的来源,不能
    因此被当成合法的Agent显式引用". Returns ``sources`` unchanged when the
    agent is unrecognized (see ``visible_source_types_for_agent``) or when
    ``sources`` is falsy."""
    if not sources:
        return sources
    visible = visible_source_types_for_agent(agent)
    if visible is None:
        return sources
    return [s for s in sources if isinstance(s, dict) and s.get("source_type") in visible]


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
        # T1 source-linking chain: a placeholder is never a real claim, so
        # it never has content to evaluate a source link against -- honest
        # NOT_PROVIDED/NOT_APPLICABLE, never a fabricated link.
        "source_link_status": SOURCE_LINK_NOT_PROVIDED,
        "linked_source_id": None,
        "source_link_method": "NONE",
        "content_support_status": SUPPORT_NOT_APPLICABLE,
        "content_support_method": "PLACEHOLDER_RECORD",
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
#
# cited_source_id (T1 source-linking chain, COMQUTOR Alpha next-round task,
# 2026-09-28): a REQUIRED field (nullable), not an optional extra key -- the
# strict "response field set must equal exactly this set" check below would
# otherwise let a caller omit it silently. The LLM may only ever cite an id
# that THIS SAME request's own "candidate_sources" offered for THAT segment
# (see _llm_batch_enrichment) -- never an arbitrary run-registry id it was
# never shown, never a candidate offered only for another segment, and never
# a string it invents.
# T4 round 34 (D1 fix, 2026-10-09): the prompt (week2.claim_batch_enrichment.
# v2) now asks for this field, and a citation outside the segment's own
# offered candidates REJECTS the reply (the whole batch falls back, like any
# other contract violation) instead of being silently nulled -- a nulled
# forgery was indistinguishable from a legitimate "no citation" answer.
_LLM_BATCH_ENRICHMENT_REQUIRED_FIELDS = {
    "segment_id",
    "claim",
    "evidence",
    "entities",
    "factors",
    "direction",
    "confidence",
    "source_section",
    "cited_source_id",
}


def _validate_llm_batch_enrichment(
    payload: Mapping[str, Any],
    batch_segments: list[dict[str, Any]],
    *,
    candidate_source_ids: frozenset[str] = frozenset(),
    candidate_source_ids_by_segment: Mapping[str, frozenset[str]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Validate one LLM batch-enrichment response against its own input
    batch. Raises ``ValueError`` (causing the whole batch to fall back to
    deterministic enrichment -- see ``_llm_batch_enrichment``) on any
    violation. Returns ``{segment_id: {"entities", "factors", "direction",
    "confidence", "cited_source_id"}}`` covering every input segment_id
    exactly once.

    ``candidate_source_ids_by_segment`` (what production passes): for each
    segment_id, the source/fragment ids THIS call's own request offered for
    that segment in ``candidate_sources`` -- the scope its
    ``cited_source_id`` must belong to. Narrower than "exists anywhere in the
    run's source_registry.json" and narrower than "offered somewhere in this
    batch": an id offered only for another segment, or real elsewhere in the
    run but never offered, is rejected. ``candidate_source_ids`` (a single
    set applied to every segment) is used only when the per-segment mapping
    is not given.
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

        cited_source_id = item.get("cited_source_id")
        if cited_source_id is not None:
            if not isinstance(cited_source_id, str) or not cited_source_id.strip():
                raise ValueError("cited_source_id must be a non-empty string or null")
            allowed = (
                candidate_source_ids_by_segment.get(segment_id, frozenset())
                if candidate_source_ids_by_segment is not None
                else candidate_source_ids
            )
            if cited_source_id not in allowed:
                # A forged id, a real id never offered, or a candidate offered
                # only for another segment: never trusted, and never silently
                # turned into a "no citation" answer.
                raise ValueError("cited_source_id is not one of the candidate sources offered for this segment")

        enrichment_by_id[segment_id] = {
            "entities": [str(value)[:200] for value in entities if str(value).strip()],
            "factors": [str(value)[:200] for value in factors if str(value).strip()],
            "direction": direction,
            "confidence": confidence,
            "cited_source_id": cited_source_id,
        }

    if seen_ids != set(by_id):
        raise ValueError("enrichment is missing one or more input segment_ids")

    return enrichment_by_id


def _candidate_sources_for_batch(
    batch_segments: list[dict[str, Any]], sources: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """T1 source-linking chain (COMQUTOR Alpha next-round task, 2026-09-28):
    the exact, narrow set of this run's own source_registry.json entries
    offered to THIS batch's enrichment call -- every segment's own
    claim+evidence text is checked via the same deterministic content
    matcher (comqutor_alpha.source_provenance.match_evidence_to_source_
    candidates) already used for the content-match fallback, and any
    source it flags for ANY segment in this batch is offered to the WHOLE
    batch (the LLM sees the same request either way; a segment-level
    citation is still checked against this same set at validation time).
    This is deliberately a narrow, batch-scoped subset of the full
    registry -- never the whole run's registry -- so a citation's backend
    validation can check "was this actually offered to this step", not
    merely "does this id exist somewhere in the run".

    Round 3 (2026-10-04): also offers a source the NORMALIZED numeric
    matcher (``match_evidence_to_source_candidates_normalized``) flags for
    any segment -- a reformatted number (thousands separators/M-billion-K
    scale/display-precision rounding) deserves the SAME chance to be
    offered to the extraction LLM as an exact-substring match does. An
    ambiguous number (2+ distinct sources) contributes no candidate here
    either, exactly like its single-candidate caller in
    ``_annotate_source_link``.

    T4 round 34 (D1 fix): the matching itself is per segment
    (``_candidate_fragment_ids_by_segment``); this is the union. The request
    states which segments each candidate was matched for, and a citation is
    checked against its own segment's candidates only.
    """
    offered_fragment_ids = set().union(*_candidate_fragment_ids_by_segment(batch_segments, sources).values())
    if not offered_fragment_ids:
        return []
    return [s for s in sources if isinstance(s, dict) and s.get("fragment_id") in offered_fragment_ids]


def _candidate_fragment_ids_by_segment(
    batch_segments: list[dict[str, Any]], sources: list[dict[str, Any]] | None
) -> dict[str, set[str]]:
    """For each segment_id of the batch, the fragment ids the deterministic
    matchers flag for THAT segment's own claim+evidence text (exact and
    normalized-numeric, as described in ``_candidate_sources_for_batch``).
    A segment with no match maps to an empty set."""
    by_segment: dict[str, set[str]] = {}
    for segment in batch_segments:
        offered: set[str] = set()
        if sources:
            offered.update(match_evidence_to_source_candidates(segment.get("evidence"), segment.get("claim"), sources))
            offered.update(
                match_evidence_to_source_candidates_normalized(
                    segment.get("evidence"), segment.get("claim"), sources
                )["candidates"]
            )
        by_segment.setdefault(segment["segment_id"], set()).update(offered)
    return by_segment


# AGENT-STAGE COVERAGE (T1 source-linking chain, COMQUTOR Alpha next-round
# task, 2026-09-28): the real pipeline is
#   fetch (tradingagents.dataflows.*, e.g. yfinance_news.py's
#          _capture_news_source -- a side-channel registry write only, never
#          changes what the caller prints into the report text)
#   -> ORIGINAL research agent (news_analyst/bull_researcher/bear_researcher/
#      etc. -- generates its own free-text report via its own LLM call;
#      confirmed by direct read of e.g. tradingagents/agents/analysts/
#      news_analyst.py's own prompt construction: it receives NO source_id/
#      fragment_id/excerpt of its own -- its prompt is built exclusively
#      from tool_names/current_date/instrument_context)
#   -> EXTRACTION-stage enrichment Agent (`_llm_batch_enrichment`, below --
#      a SEPARATE, LATER LLM call that segments the original agent's
#      ALREADY-GENERATED raw_output text and is the ONLY call in this chain
#      that receives `candidate_sources`/returns `cited_source_id`)
#   -> persistence (`_build_records_from_segments`/`_annotate_source_link`).
#
# `candidate_sources`/`cited_source_id` therefore cover ONLY the extraction
# stage -- this is an "抽取阶段引用闭环" (extraction-stage citation closure),
# NOT an original-agent citation closure. The extraction Agent's after-the-
# fact discovery of a content-matching candidate, or even its own
# AGENT_CITED selection of an offered candidate, must never be described as
# "the original research agent has already cited the source" -- the
# original agent's own generation-time input still carries no source_id/
# fragment_id at all. Threading source_id/fragment_id into the ORIGINAL
# research agent's own prompt/tool-output (so IT can cite at generation
# time, not just have its output matched afterward) remains unimplemented
# and out of scope for this round.
def _llm_batch_enrichment(
    llm_gateway: Any,
    *,
    ticker: str,
    agent: str,
    batch_segments: list[dict[str, Any]],
    sources: list[dict[str, Any]] | None = None,
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
    # T1 source-linking chain: the real Agent input for this extraction
    # step now carries this run's own already-captured source_id/
    # fragment_id/excerpt for every candidate source relevant to this
    # batch -- never the model's own invention, always a real, already-
    # persisted registry entry (comqutor_alpha.source_provenance.
    # public_source_fields, the same whitelist projection API/export use).
    # T4 round 34 (D1 fix, input.v2): each candidate also lists segment_ids --
    # the segments its excerpt was matched for, i.e. the only segments it may
    # be cited for -- and the validator checks each citation against its own
    # segment's candidates.
    fragment_ids_by_segment = _candidate_fragment_ids_by_segment(batch_segments, sources)
    candidate_sources = _candidate_sources_for_batch(batch_segments, sources)
    request = {
        "ticker": ticker,
        "agent": agent,
        "segments": payload_segments,
        "candidate_sources": [
            {
                "source_id": s.get("source_id"),
                "fragment_id": s.get("fragment_id"),
                "excerpt": s.get("excerpt"),
                "segment_ids": [
                    segment["segment_id"]
                    for segment in batch_segments
                    if s.get("fragment_id") in fragment_ids_by_segment.get(segment["segment_id"], ())
                ],
            }
            for s in candidate_sources
        ],
    }
    candidate_source_ids_by_segment = {
        segment_id: frozenset(
            {s.get("source_id") for s in candidate_sources if s.get("fragment_id") in fragment_ids}
            | {s.get("fragment_id") for s in candidate_sources if s.get("fragment_id") in fragment_ids}
        )
        - {None}
        for segment_id, fragment_ids in fragment_ids_by_segment.items()
    }

    def validator(payload):
        return _validate_llm_batch_enrichment(
            payload, batch_segments, candidate_source_ids_by_segment=candidate_source_ids_by_segment
        )

    if getattr(llm_gateway, "semantic_runtime", None) is not None and callable(
        getattr(llm_gateway, "invoke_json_with_trace", None)
    ):
        invocation = llm_gateway.invoke_json_with_trace(
            "claim_batch_enrichment",
            request,
            validator,
        )
        if invocation.validation_accepted:
            llm_gateway.finalize_semantic_invocation(invocation, accepted=True)
            return invocation.validated_output
        llm_gateway.finalize_semantic_invocation(
            invocation,
            accepted=False,
            fallback_reason=invocation.error_code or "WEEK2_LLM_BATCH_ENRICHMENT_FALLBACK",
        )
        return None

    return llm_gateway.invoke_json(
        "claim_batch_enrichment",
        request,
        validator,
    )


def _normalized_values(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(str(value) for value in values if str(value).strip()))

SOURCE_LINK_METHOD_AGENT_CITED = "AGENT_CITED"
# T1 follow-up, 2026-09-28: a literal [fragment_id: ...] marker (see
# tradingagents.dataflows.yfinance_news._source_reference_marker) found
# INSIDE the claim's own evidence/claim text -- proof the ORIGINAL research
# agent's own free-text output preserved the real reference its own tool
# message offered it, distinct from SOURCE_LINK_METHOD_AGENT_CITED (the
# SEPARATE, LATER extraction-stage Agent's own structured citation).
SOURCE_LINK_METHOD_ORIGINAL_AGENT_MARKER = "ORIGINAL_AGENT_MARKER_CITED"
SOURCE_LINK_METHOD_CONTENT_MATCH_CANDIDATE = "CONTENT_MATCH_CANDIDATE"
# Round 3 (2026-10-04): a SPECIFIC already-saved numeric field (not a
# whole-excerpt substring) located via comqutor_alpha.source_provenance.
# match_evidence_to_source_candidates_normalized -- handles thousands
# separators/M-billion-K scale suffixes/display-precision rounding that
# the whole-excerpt matcher above cannot. Always its own distinct method
# name, never folded into SOURCE_LINK_METHOD_CONTENT_MATCH_CANDIDATE, so a
# reader never confuses "the whole excerpt text overlapped" with "one
# specific number, reformatted, was located."
SOURCE_LINK_METHOD_NORMALIZED_FIELD_MATCH = "NORMALIZED_FIELD_MATCH_CANDIDATE"
SOURCE_LINK_METHOD_NONE = "NONE"


def _annotate_source_link(
    record: dict[str, Any],
    sources: list[dict[str, Any]] | None,
    evidence_cutoff: str | None,
    agent_cited_source_id: str | None = None,
) -> None:
    """T1 source-linking chain (COMQUTOR Alpha next-round task, 2026-09-26,
    extended 2026-09-28): attaches ``source_link_status``/
    ``linked_source_id``/``source_link_method``/``content_support_status``/
    ``content_support_method`` to ``record`` in place, real production
    behavior (not a demo/tool script).

    Three ways a candidate id can arise, checked in this PRIORITY order:

      1. ``agent_cited_source_id`` -- an explicit citation the extraction-
         stage Agent itself returned (see ``_llm_batch_enrichment``'s
         ``cited_source_id``), ALREADY validated by
         ``_validate_llm_batch_enrichment`` against exactly the
         ``candidate_sources`` this batch's own request offered (never the
         whole run's registry) -- an explicit reference, never a guess.
      2. :func:`comqutor_alpha.source_provenance.extract_source_marker_from_text`
         -- a literal ``[fragment_id: ...]`` marker found inside the
         claim's OWN evidence/claim text, proving the ORIGINAL research
         agent's own free-text output preserved the real reference its own
         tool message offered it (see ``tradingagents.dataflows.
         yfinance_news._source_reference_marker``) -- distinct from (1),
         which is the SEPARATE, LATER extraction-stage Agent's own
         structured citation. Checked only when (1) did not already
         produce a valid link.
      3. :func:`match_evidence_to_source_candidates` -- deterministic,
         content-based matching with no explicit reference at all, only
         text overlap. This is ONLY an auxiliary candidate method, used
         solely when neither (1) nor (2) produced a valid link;
         ``source_link_method`` always names which path produced the
         result, so a caller never confuses an explicit reference with a
         same-text coincidence.

    Every path's candidate must still pass :func:`validate_source_reference`
    (exists in THIS run's own registry, has locatable content, satisfies
    the evidence cutoff) before ever being treated as ``SOURCE_LINK_VALID``
    -- an explicit citation/marker is validated exactly like a content-
    match candidate, never trusted merely for being explicit.

    ``SOURCE_LINK_VALID`` is never, by itself, treated as content support:
    a genuinely linked claim gets ``content_support_status =
    SUPPORT_PENDING_REVIEW`` (this module can prove a claim's evidence text
    traces to a real, in-scope source -- it cannot judge whether that
    source's content actually backs the claim's assertion, an explicitly
    separate semantic question this module never answers -- see
    ``comqutor_alpha.source_provenance``'s own module docstring).
    ``SUPPORT_NOT_APPLICABLE`` marks a claim with no valid link to evaluate
    support against at all.
    """
    if not sources:
        record["source_link_status"] = SOURCE_LINK_NOT_PROVIDED
        record["linked_source_id"] = None
        record["source_link_method"] = SOURCE_LINK_METHOD_NONE
        record["content_support_status"] = SUPPORT_NOT_APPLICABLE
        record["content_support_method"] = "NO_SOURCE_REGISTRY"
        record["content_support_review"] = build_content_support_review(
            SUPPORT_NOT_APPLICABLE, method=REVIEW_METHOD_UNREVIEWED, claim_id=record.get("claim_id")
        )
        return

    result = None
    method = SOURCE_LINK_METHOD_NONE
    if agent_cited_source_id:
        validated = validate_source_reference(agent_cited_source_id, sources=sources, evidence_cutoff=evidence_cutoff)
        result = validated
        method = SOURCE_LINK_METHOD_AGENT_CITED

    if result is None or result["source_link_status"] != SOURCE_LINK_VALID:
        marker_fragment_id = extract_source_marker_from_text(record.get("evidence"), sources) or (
            extract_source_marker_from_text(record.get("claim"), sources)
        )
        if marker_fragment_id:
            validated = validate_source_reference(marker_fragment_id, sources=sources, evidence_cutoff=evidence_cutoff)
            if result is None or validated["source_link_status"] == SOURCE_LINK_VALID:
                result = validated
                method = SOURCE_LINK_METHOD_ORIGINAL_AGENT_MARKER

    if result is None or result["source_link_status"] != SOURCE_LINK_VALID:
        candidates = match_evidence_to_source_candidates(record.get("evidence"), record.get("claim"), sources)
        for candidate in candidates:
            validated = validate_source_reference(candidate, sources=sources, evidence_cutoff=evidence_cutoff)
            if validated["source_link_status"] == SOURCE_LINK_VALID:
                result = validated
                method = SOURCE_LINK_METHOD_CONTENT_MATCH_CANDIDATE
                break
            if result is None:
                result = validated
                method = SOURCE_LINK_METHOD_CONTENT_MATCH_CANDIDATE

    # Round 3 (2026-10-04), section 5: a SEPARATE, additive pass -- tried
    # only when nothing above has already produced SOURCE_LINK_VALID --
    # for a claim that reformats one specific already-saved NUMBER
    # (thousands separators / M-billion-K scale / display-precision
    # rounding) that the whole-excerpt matcher above cannot handle.
    # Ambiguity (the same number genuinely present in 2+ distinct sources)
    # is recorded, never guessed -- no candidate is accepted for it.
    normalized_match = None
    if result is None or result["source_link_status"] != SOURCE_LINK_VALID:
        normalized_match = match_evidence_to_source_candidates_normalized(
            record.get("evidence"), record.get("claim"), sources, instrument=record.get("ticker")
        )
        if normalized_match["ambiguous_numbers"]:
            record["source_link_ambiguous_candidates"] = normalized_match["ambiguous_numbers"]
        for candidate in normalized_match["candidates"]:
            validated = validate_source_reference(candidate, sources=sources, evidence_cutoff=evidence_cutoff)
            if validated["source_link_status"] == SOURCE_LINK_VALID:
                result = validated
                method = SOURCE_LINK_METHOD_NORMALIZED_FIELD_MATCH
                break
            if result is None:
                result = validated
                method = SOURCE_LINK_METHOD_NORMALIZED_FIELD_MATCH

    if result is None:
        result = validate_source_reference(None, sources=sources, evidence_cutoff=evidence_cutoff)
        method = SOURCE_LINK_METHOD_NONE

    record["source_link_status"] = result["source_link_status"]
    record["linked_source_id"] = result["linked_source_id"]
    record["source_link_method"] = method if result["source_link_status"] != SOURCE_LINK_NOT_PROVIDED else SOURCE_LINK_METHOD_NONE

    # Round 3 (2026-10-04), section 3.7: "一个声明确需多个引用时...不得丢掉
    # 除第一项外的来源". `linked_source_id` above stays exactly the single
    # PRIMARY reference (unchanged, backward compatible with every existing
    # reader). `linked_source_ids` is a NEW, additive, plural field -- every
    # DISTINCT additional source_id this same claim/evidence text also
    # carries a real, independently-validated reference to (another
    # marker, or another normalized field match), primary one listed
    # first. Legacy records/readers that only know `linked_source_id`
    # continue to work unchanged; nothing here replaces or narrows that
    # field.
    if result["source_link_status"] == SOURCE_LINK_VALID:
        extra_ids: list[str] = [result["linked_source_id"]]
        for text_field in (record.get("evidence"), record.get("claim")):
            for fragment_id in extract_all_source_markers_from_text(text_field, sources):
                extra_validated = validate_source_reference(fragment_id, sources=sources, evidence_cutoff=evidence_cutoff)
                extra_source_id = extra_validated.get("linked_source_id")
                if extra_validated["source_link_status"] == SOURCE_LINK_VALID and extra_source_id not in extra_ids:
                    extra_ids.append(extra_source_id)
        if normalized_match is None:
            normalized_match = match_evidence_to_source_candidates_normalized(
                record.get("evidence"), record.get("claim"), sources, instrument=record.get("ticker")
            )
        for fragment_id in normalized_match["candidates"]:
            extra_validated = validate_source_reference(fragment_id, sources=sources, evidence_cutoff=evidence_cutoff)
            extra_source_id = extra_validated.get("linked_source_id")
            if extra_validated["source_link_status"] == SOURCE_LINK_VALID and extra_source_id not in extra_ids:
                extra_ids.append(extra_source_id)
        if len(extra_ids) > 1:
            record["linked_source_ids"] = extra_ids
    if result["source_link_status"] == SOURCE_LINK_VALID:
        record["content_support_status"] = SUPPORT_PENDING_REVIEW
        if method == SOURCE_LINK_METHOD_AGENT_CITED:
            review_method = REVIEW_METHOD_AGENT_CITED_UNVERIFIED_SUPPORT
        elif method == SOURCE_LINK_METHOD_ORIGINAL_AGENT_MARKER:
            review_method = REVIEW_METHOD_ORIGINAL_AGENT_CITED_UNVERIFIED_SUPPORT
        else:
            review_method = REVIEW_METHOD_UNVERIFIED_OFFLINE_CONTENT_MATCH
        record["content_support_method"] = review_method
        record["content_support_review"] = build_content_support_review(
            SUPPORT_PENDING_REVIEW,
            method=review_method,
            claim_id=record.get("claim_id"),
            linked_source_id=result.get("linked_source_id"),
        )
        # Automated eligibility round (2026-10-06): production cannot gate
        # scoring on a human reviewer who may never click anything -- a
        # real, deterministic, re-checkable automated verification (data
        # fact / derived calculation, see ``verify_data_fact_or_
        # derived_calculation``) upgrades the PENDING_REVIEW default set
        # above to SUPPORTS when, and only when, it actually succeeds.
        # Narrow and conservative by construction: a compound claim mixing
        # a real number with unverifiable interpretation is left exactly as
        # PENDING_REVIEW above, never upgraded.
        automated = apply_automated_content_support_verification(record, sources=sources)
        if automated is not None:
            record["content_support_status"] = automated["content_support_status"]
            record["content_support_method"] = automated["content_support_method"]
            record["content_support_review"] = automated["content_support_review"]
    else:
        record["content_support_status"] = SUPPORT_NOT_APPLICABLE
        record["content_support_method"] = "NOT_LINKED"
        record["content_support_review"] = build_content_support_review(
            SUPPORT_NOT_APPLICABLE, method=REVIEW_METHOD_UNREVIEWED, claim_id=record.get("claim_id")
        )


def _build_records_from_segments(
    segments, raw_record, run_id, ticker, agent, raw_text, base_id, source_agent_output_id,
    sources=None, evidence_cutoff=None,
):
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
        _annotate_source_link(record, sources, evidence_cutoff, agent_cited_source_id=segment.get("cited_source_id"))
        # Round 3 (2026-10-04), section 4: real production wiring -- every
        # claim passes through the SAME limited derived-calculation
        # verifier the offline diagnostic/tests use (never a test-only
        # helper). Purely additive: a non-None verdict is stamped as
        # `derived_fact_check`; it NEVER touches source_link_status,
        # content_support_status, claim_quality, or any eligibility gate
        # computed above/below it. A claim whose text does not match the
        # one recognized percent-comparison shape gets no field at all
        # (verify_percent_comparison_claim returns None) -- never a
        # fabricated "not applicable" verdict for every other claim shape.
        derived_check = verify_percent_comparison_claim(claim, sources)
        if derived_check is not None:
            record["derived_fact_check"] = derived_check
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
    raw_record, run_id, ticker, *, llm_gateway=None, filter_audit=None, quality_audit=None,
    canonical_relations_audit=None, sources=None, evidence_cutoff=None,
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

    # TradingAgents' own, single existing LLM call for this agent may have
    # appended a COMQUTOR_CANONICAL_RELATIONS machine-readable block after
    # its normal report text (see canonical_relation_prompt.py /
    # canonical_prompt_injection.py -- never a second LLM call). Split it
    # out here, deterministically, *before* claim segmentation, so the
    # block's JSON syntax/field names can never become a claim segment, and
    # validate any relations it proposed against the real production
    # vocabulary. A raw output with no such marker is completely unaffected
    # (parsed_block.human_text == raw_text unchanged) -- this is exactly
    # what every historical run without this feature already looks like.
    parsed_block = split_human_text_and_canonical_block(raw_text)
    human_text = parsed_block.human_text
    local_canonical_relations: list[dict[str, Any]] = []
    if parsed_block.found:
        local_canonical_relations = validate_canonical_relations(
            parsed_block,
            vocabulary=build_canonical_relation_vocabulary(),
            agent_report_text=human_text,
            agent=agent,
            run_id=run_id,
            ticker=ticker,
            source_agent_output_id=source_agent_output_id,
        )

    segments, filtered = extract_claim_segments_with_audit(human_text)
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
                llm_gateway, ticker=ticker, agent=agent, batch_segments=batch, sources=sources
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
                    # T1 source-linking chain: the Agent's own validated
                    # citation (already checked against this batch's own
                    # offered candidate set by _validate_llm_batch_
                    # enrichment) -- None when the Agent cited nothing, or
                    # cited something outside the offered set.
                    merged["cited_source_id"] = item["cited_source_id"]
                    enriched_batch.append(merged)
                batch_records = _build_records_from_segments(
                    enriched_batch, raw_record, run_id, ticker, agent, raw_text, base_id, source_agent_output_id,
                    sources=sources, evidence_cutoff=evidence_cutoff,
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
                det_batch, raw_record, run_id, ticker, agent, raw_text, base_id, source_agent_output_id,
                sources=sources, evidence_cutoff=evidence_cutoff,
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

    if canonical_relations_audit is not None and local_canonical_relations:
        # Lineage Repair (Structure Integrity Repair Sprint, Track 1):
        # resolve each canonical relation's evidence_quote against THIS same
        # raw agent output's own real, quality-gate-eligible structured
        # claims -- never the relation's own synthetic relation_id, and
        # never a claim from a different agent/run. This must happen after
        # eligible_records exists (the real claim_id/claim/claim_index pool
        # to match against), not at validation time.
        canonical_relations_audit.extend(
            resolve_relation_source_claims(local_canonical_relations, eligible_records)
        )

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


class _DeferredFinalizeGatewayProxy:
    """John Requirement B, Phase B2 Slice 2B: wraps a real llm_gateway so
    ``invoke_json_with_trace`` (the Provider call, and the call_sequence
    allocation that comes with it) runs immediately -- safe to call
    concurrently, since it is the same already-thread-safe
    Week2LLMGateway/SemanticRuntimeSession infrastructure alpha_classifier's
    and evidence_stance_classifier's own existing concurrency already rely
    on -- while ``finalize_semantic_invocation`` (the call that actually
    appends to the shared recorder) is BUFFERED rather than applied
    immediately. A caller drains ``buffered_finalizations`` afterward,
    sorted by each invocation's own ``trace_handle.call_sequence``, into the
    real gateway -- exactly the invoke-concurrently/finalize-in-sequence-
    order technique Phase B2 Slice 2A validated for evidence_stance_
    classifier, generalized here behind a transparent proxy so
    ``adapt_raw_agent_outputs`` (and anything else) needs zero changes to
    run safely under concurrency. Everything else (attribute access,
    ``invoke_json`` for a gateway with no attached semantic_runtime) is
    delegated straight through, unproxied."""

    def __init__(self, real_gateway: Any) -> None:
        self._real = real_gateway
        self.buffered_finalizations: list[tuple[Any, bool, str | None]] = []

    def invoke_json_with_trace(self, task: str, payload: Mapping[str, Any], validator: Any, **kwargs: Any) -> Any:
        # Transparent: any optional keyword the real gateway accepts (e.g.
        # the out-of-band claim_ids= identity added in round 14) passes
        # through untouched rather than being silently dropped or rejected.
        return self._real.invoke_json_with_trace(task, payload, validator, **kwargs)

    def finalize_semantic_invocation(self, invocation: Any, *, accepted: bool, fallback_reason: str | None = None) -> None:
        self.buffered_finalizations.append((invocation, accepted, fallback_reason))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


def _sequence_key_for_buffered_finalization(item: tuple[Any, bool, str | None]) -> float:
    invocation, _accepted, _reason = item
    trace = getattr(invocation, "trace_handle", None)
    sequence = getattr(trace, "call_sequence", None)
    # A call with no trace (no attached semantic_runtime, or trace
    # allocation itself failed) never reaches the recorder, so its relative
    # position among buffered finalizations cannot violate the sequence
    # invariant -- ordered last is an arbitrary-but-safe placement.
    return sequence if isinstance(sequence, int) else float("inf")


def _run_one_raw_agent_output(
    index: int,
    raw_record: Any,
    run_id: str,
    ticker: str,
    proxy: "_DeferredFinalizeGatewayProxy",
    sources: list[dict[str, Any]] | None = None,
    evidence_cutoff: str | None = None,
) -> tuple[int, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """One concurrency-safe unit of work: adapt_raw_agent_outputs is called
    completely unmodified, with its own fresh, thread-local filter_audit/
    quality_audit/canonical_relations_audit accumulators (never shared with
    any other raw_record's own call) -- so no shared-list/dict mutation is
    even possible during the concurrent phase. ``sources`` is this run's own
    already-loaded, read-only source_registry.json sources list (or
    ``None``) -- the same value for every raw_record, safe to share
    unguarded across threads since it is never mutated here."""
    local_filter_audit: list[dict[str, Any]] = []
    local_quality_audit = _new_quality_audit()
    local_canonical_relations: list[dict[str, Any]] = []
    agent_key = normalize_agent_name(
        (raw_record.get("agent") or raw_record.get("tradingagents_agent"))
        if isinstance(raw_record, dict)
        else "unknown_agent"
    )
    scoped_sources = scope_sources_for_agent(agent_key, sources)
    adapted_records = adapt_raw_agent_outputs(
        raw_record,
        run_id,
        ticker,
        llm_gateway=proxy,
        filter_audit=local_filter_audit,
        quality_audit=local_quality_audit,
        canonical_relations_audit=local_canonical_relations,
        sources=scoped_sources,
        evidence_cutoff=evidence_cutoff,
    )
    return index, adapted_records, local_filter_audit, local_canonical_relations, local_quality_audit


def _adapt_run_outputs_concurrently(
    raw_agent_outputs: list[Any],
    run_id: str,
    ticker: str,
    llm_gateway: Any,
    concurrency: int,
    sources: list[dict[str, Any]] | None = None,
    evidence_cutoff: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], dict[str, dict[str, Any]]]:
    """John Requirement B, Phase B2 Slice 2B: bounded concurrency across
    independent raw agent outputs. Each raw_record's own call is fully
    independent of every other (see the Slice 2B audit's independence
    proof: own segments, own batches, own filter/quality/canonical-relation
    accumulators, and adapt_raw_agent_outputs itself is completely
    unmodified and unaware it is running concurrently).

    Phase 1 (concurrent): dispatch one _run_one_raw_agent_output call per
    raw_record, each wrapped in its own _DeferredFinalizeGatewayProxy (built
    up front so phase 2a can drain each one's buffered finalizations after
    its future resolves).
    Phase 2a (serial, sequence-sorted): drain every buffered
    finalize_semantic_invocation call, sorted by call_sequence -- restoring
    the exact recorder-append ordering SemanticCallRecorder already
    requires for every task (the same fix Slice 2A validated).
    Phase 2b (serial, ORIGINAL raw_agent_outputs order -- never completion
    order): merge each worker's own results into the run-level
    records/filter_audit/canonical_relations/global_audit/per_agent
    structures, byte-identical to what the serial loop in adapt_run_outputs
    already does.
    """
    proxies = [_DeferredFinalizeGatewayProxy(llm_gateway) for _ in raw_agent_outputs]
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="comqutor-structured-adapter") as executor:
        futures = [
            executor.submit(
                _run_one_raw_agent_output, index, raw_record, run_id, ticker, proxies[index],
                sources, evidence_cutoff,
            )
            for index, raw_record in enumerate(raw_agent_outputs)
        ]
        completed = [future.result() for future in futures]

    # Phase 2a: finalize every buffered gateway call, in ascending
    # call_sequence order across ALL raw_agent_outputs combined (never
    # per-agent or completion order).
    all_buffered: list[tuple[Any, bool, str | None]] = []
    for proxy in proxies:
        all_buffered.extend(proxy.buffered_finalizations)
    for invocation, accepted, fallback_reason in sorted(all_buffered, key=_sequence_key_for_buffered_finalization):
        llm_gateway.finalize_semantic_invocation(invocation, accepted=accepted, fallback_reason=fallback_reason)

    # Phase 2b: merge each worker's own results, in ORIGINAL
    # raw_agent_outputs order -- byte-identical to the serial loop's own
    # per-iteration bookkeeping.
    records: list[dict[str, Any]] = []
    filter_audit: list[dict[str, Any]] = []
    canonical_relations: list[dict[str, Any]] = []
    global_audit = _new_quality_audit()
    per_agent: dict[str, dict[str, Any]] = {}

    for index, adapted_records, local_filter_audit, local_canonical_relations, local_quality_audit in sorted(
        completed, key=lambda item: item[0]
    ):
        raw_record = raw_agent_outputs[index]
        agent_key = normalize_agent_name(
            (raw_record.get("agent") or raw_record.get("tradingagents_agent"))
            if isinstance(raw_record, dict)
            else "unknown_agent"
        )
        filter_audit.extend(local_filter_audit)
        canonical_relations.extend(local_canonical_relations)

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
        for item in local_filter_audit:
            code = str(item.get("reason_code") or "UNKNOWN")
            if code == FILTER_REASON_DISCLAIMER:
                bucket["disclaimer_removed"] += 1
            else:
                bucket["boilerplate_removed"] += 1
        _add_quality_audit(bucket.setdefault("_audit", _new_quality_audit()), local_quality_audit)
        _add_quality_audit(global_audit, local_quality_audit)

        records.extend(adapted_records)

    return records, filter_audit, canonical_relations, global_audit, per_agent


# Adapt all raw agent output records in a run directory into structured claim
# records, logging any warnings. ``concurrency`` (John Requirement B, Phase
# B2 Slice 2B): number of independent raw agent outputs to process at once.
# ``None`` (the default) resolves to
# week2_llm.resolve_structured_adapter_concurrency() -- the same env-var-
# overridable, centrally-defined resolution pattern already used for
# alpha_classifier and evidence_stance_classifier. ``concurrency<=1`` (or a
# single/empty raw_agent_outputs list) reproduces the exact prior serial
# behavior with zero functional change.
def adapt_run_outputs(run_dir, *, llm_gateway=None, concurrency=None):
    run_dir, run_id, output_root = _run_context_from_dir(run_dir)
    raw_payload = load_raw_agent_outputs(run_dir)
    ticker = str(raw_payload.get("ticker") or "unknown").upper()
    raw_agent_outputs = raw_payload.get("agent_outputs", []) or []

    # T1 source-linking chain (COMQUTOR Alpha next-round task, 2026-09-26;
    # time-contract fix, round7 follow-up, 2026-10-06): best-effort load of
    # this SAME run's own already-persisted source_registry.json (absent for
    # a historical run, or a run with no real news tool calls -- honest
    # empty list, never an error). The evidence-cutoff a linked source's own
    # published_at must not be later than (look-ahead safety, re-asserted
    # here independently of tradingagents.dataflows.yfinance_news's own
    # fetch-time window filter) now prefers the real, tz-aware moment this
    # run's own sources were actually fetched (``resolve_evidence_cutoff_at``
    # -- see its own docstring) over the bare ``analysis_date`` calendar
    # string, which round7 traced as the root cause of every one of a real
    # run's SOURCE_LINK_TIME_INVALID false positives: a bare date parses to
    # that date's own MIDNIGHT, incorrectly rejecting a same-day source
    # fetched at any real time after 00:00:00. ``analysis_date`` remains the
    # fallback, unchanged, when no source has a usable ``retrieved_at``.
    source_registry = load_json_record_if_exists(run_id, "source_registry.json", output_root=output_root)
    sources = source_registry.get("sources") if isinstance(source_registry, dict) else None
    run_metadata = load_json_record_if_exists(run_id, "metadata.json", output_root=output_root)
    analysis_date = run_metadata.get("analysis_date") if isinstance(run_metadata, dict) else None
    evidence_cutoff, evidence_cutoff_basis = resolve_evidence_cutoff_at(analysis_date, sources)

    if concurrency is None:
        concurrency = resolve_structured_adapter_concurrency()

    # 2026-10-06 (round 11 -> round 13): round 11 found a real defect here --
    # Week2LLMGateway's request/response audit mode tracked at most one
    # pending attempt via a single, Gateway-wide slot, and this function's
    # own concurrent dispatch (multiple raw agent outputs onto a
    # ThreadPoolExecutor, all sharing one llm_gateway) crashed the real run's
    # whole structured_agent_outputs stage the moment two agents'
    # claim_batch_enrichment calls overlapped. Round 11's own fix forced
    # concurrency=1 whenever audit was on -- a deliberately labeled temporary
    # compatibility shim. Round 13 replaced the Gateway's own single-slot
    # design with real, independent per-attempt identity (contextvars.
    # ContextVar, explicitly propagated across call_with_timeout's nested
    # executor boundary -- see week2_llm.py's own _current_audit_attempt
    # docstring), so concurrent audited dispatch is now genuinely safe. The
    # forced-serial override is therefore REMOVED: ``concurrency`` keeps its
    # real, original meaning in every case, audit-enabled or not.

    if llm_gateway is None or concurrency <= 1 or len(raw_agent_outputs) <= 1:
        records = []
        filter_audit: list[dict[str, Any]] = []
        canonical_relations: list[dict[str, Any]] = []
        global_audit = _new_quality_audit()
        # Section E: per-agent coverage breakdown. Keyed by normalized agent
        # name; multiple raw outputs for the same agent are aggregated
        # (their original source_agent_output_id provenance stays on each
        # record regardless -- this bucket is a count-only rollup).
        per_agent: dict[str, dict[str, Any]] = {}

        for raw_record in raw_agent_outputs:
            agent_key = normalize_agent_name(
                (raw_record.get("agent") or raw_record.get("tradingagents_agent"))
                if isinstance(raw_record, dict)
                else "unknown_agent"
            )
            call_audit = _new_quality_audit()
            filter_start = len(filter_audit)
            scoped_sources = scope_sources_for_agent(agent_key, sources)
            adapted_records = adapt_raw_agent_outputs(
                raw_record,
                run_id,
                ticker,
                llm_gateway=llm_gateway,
                filter_audit=filter_audit,
                quality_audit=call_audit,
                canonical_relations_audit=canonical_relations,
                sources=scoped_sources,
                evidence_cutoff=evidence_cutoff,
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
    else:
        records, filter_audit, canonical_relations, global_audit, per_agent = _adapt_run_outputs_concurrently(
            raw_agent_outputs, run_id, ticker, llm_gateway, concurrency, sources, evidence_cutoff
        )
        for record in records:
            if record.get("adapter_warning"):
                # Re-derive which raw_record this came from for the error
                # log payload -- adapter_warning records always carry their
                # own source_agent_output_id, matching the serial path's
                # own per-record logging exactly.
                matching_raw_record = next(
                    (
                        r
                        for r in raw_agent_outputs
                        if isinstance(r, dict)
                        and str(r.get("agent_output_id") or "") == str(record.get("source_agent_output_id") or "")
                    ),
                    None,
                ) or {}
                _log_error(
                    run_id,
                    output_root,
                    _error_payload(run_id, ticker, matching_raw_record, record),
                )

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

    # Round 9 (2026-10-06): additive post-pass over the FULL, already-built
    # records list -- mirrors alpha_mapper's own "map_structured_records
    # then apply_llm_stance_upgrade" shape exactly (see evidence_stance_llm
    # .apply_llm_stance_upgrade). A zero-cost no-op whenever llm_gateway is
    # None (every existing caller's default, and Architecture Replay, which
    # never passes one) -- ``records`` is returned unchanged. Never touches
    # source_link_status or any field this function already set above;
    # only ever upgrades content_support_status/method/review (and the
    # additive content_support_llm_detail/content_support_llm_fallback_
    # reason diagnostic fields) for a claim that is SOURCE_LINK_VALID and
    # was not already resolved by the cheaper deterministic verifier inside
    # _annotate_source_link above.
    # 2026-10-06 (AMD Fresh Run production-wiring task): additive, opt-in
    # per-run batch-size override -- unset (every existing caller) means
    # the module's own BATCH_SIZE default, unchanged. A real function
    # parameter read from its own env var at the point of use, never a
    # module-global mutated after import (see content_support_llm.py's own
    # apply_llm_content_support_verification docstring for why that
    # approach silently fails).
    _content_support_batch_size_raw = os.environ.get("COMQUTOR_WEEK2_CONTENT_SUPPORT_BATCH_SIZE")
    _content_support_batch_size = (
        int(_content_support_batch_size_raw) if _content_support_batch_size_raw else None
    )
    # 2026-10-08 (T3 closeout): a selected execution profile's batch size
    # replaces the env override (week2_execution_profile.py).
    _execution_profile = _selected_week2_execution_profile()
    if _execution_profile is not None:
        _content_support_batch_size = _execution_profile.content_support_batch_size
    records, content_support_llm_stats = apply_llm_content_support_verification(
        records, sources, llm_gateway=llm_gateway, batch_size=_content_support_batch_size
    )

    canonical_relation_block_count = sum(
        1
        for raw_record in raw_agent_outputs
        if isinstance(raw_record, dict) and RELATION_BLOCK_MARKER in str(raw_record.get("raw_output") or "")
    )
    canonical_relations_validated_count = sum(
        1 for relation in canonical_relations if relation.get("validation_status") == "accepted"
    )
    canonical_relations_rejected_count = sum(
        1 for relation in canonical_relations if relation.get("validation_status") == "rejected"
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "records": records,
        # TradingAgents' own existing LLM call may append a
        # COMQUTOR_CANONICAL_RELATIONS block to its normal report text (see
        # canonical_relation_prompt.py). Kept as a top-level sibling to
        # ``records`` -- these are report-level relations, not tied to any
        # one segmented claim -- and never mixed into claim segmentation.
        "canonical_relations": canonical_relations,
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
            # Inject COMQUTOR Canonical Vocabulary into Existing TradingAgents
            # Prompts: additive counters only, never breaking an existing
            # consumer's expectations about the metadata shape.
            "canonical_relation_block_count": canonical_relation_block_count,
            "canonical_relations_validated_count": canonical_relations_validated_count,
            "canonical_relations_rejected_count": canonical_relations_rejected_count,
            # Time-contract fix (round7 follow-up, 2026-10-06): the REAL
            # evidence-cutoff moment actually used for every source-link
            # time-validity check this adapter run performed, explicitly
            # recorded (never left implicit) -- see
            # ``source_provenance.resolve_evidence_cutoff_at``.
            "evidence_cutoff_at": evidence_cutoff,
            "evidence_cutoff_basis": evidence_cutoff_basis,
            "analysis_date": analysis_date,
            # Round 9 (2026-10-06): real LLM content-support verification
            # run stats -- all zero/False when llm_gateway is None.
            "content_support_llm": content_support_llm_stats.to_dict(),
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
