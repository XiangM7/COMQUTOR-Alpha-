"""Additive v4.1 deterministic candidate-binding protocol.

The semantic extraction rules are inherited byte-for-byte from v4. Only
Provider-visible evidence location fields and instructions change. v4 remains
frozen and is never modified.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v4 import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4,
)

STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_1 = (
    "structured_adapter.claim_extraction_shadow.v4.1"
)
PARENT_PROMPT_VERSION = "structured_adapter.claim_extraction_shadow.v4"
SEMANTIC_RULE_DELTA = "NONE"
LOCATION_PROTOCOL_DELTA = "DETERMINISTIC_CANDIDATE_BINDING"

_V4_IDENTITY_RULE = (
    "- You never restate identity, hashes, or IDs in your response -- the caller already owns "
    "them and computes them independently. Return only the claims/abstentions shape below."
)
_V4_1_IDENTITY_RULE = (
    "- You never restate identity, hashes, or IDs except the optional caller-owned candidate_id "
    "inside a supporting_evidence item. Return only the claims/abstentions shape below."
)

_V4_OUTPUT_SHAPE = r'''OUTPUT SHAPE
{
  "claims":[{
    "claim":"...",
    "supporting_quotes":["verbatim source sentence or clause"],
    "entities":[],"factors":[],"direction":"unknown","confidence":0.0
  }],
  "abstentions":[{"candidate_ids":[],"reason_code":"NO_RELIABLE_CLAIM","notes":""}]
}'''

_V4_1_OUTPUT_SHAPE = r'''OUTPUT SHAPE
{
  "claims":[{
    "claim":"...",
    "supporting_evidence":[{
      "quote":"verbatim source sentence or clause",
      "candidate_id":null
    }],
    "entities":[],"factors":[],"direction":"unknown","confidence":0.0
  }],
  "abstentions":[{"candidate_ids":[],"reason_code":"NO_RELIABLE_CLAIM","notes":""}]
}'''

_V4_CANDIDATE_RULE = (
    "- CANDIDATE_HINTS (if present below) are OPTIONAL location hints only, with no semantic "
    "authority: you may ignore them, agree with them, or propose claims they do not cover. "
    "They never cover the whole report -- you must still read AGENT_REPORT yourself. A "
    "candidate_id is never required on a claim."
)
_V4_1_CANDIDATE_RULE = (
    "- CANDIDATE_HINTS are deterministic, caller-owned location bindings with no semantic "
    "authority. Each candidate_id is pre-registered for this request and maps to one source "
    "span owned by the caller. For each supporting_evidence item, return at most one exact "
    "candidate_id from CANDIDATE_HINTS. If the quote occurs more than once in AGENT_REPORT, "
    "candidate_id is required and must select a candidate containing exactly one full exact "
    "occurrence. For a globally unique quote, candidate_id may be null; if supplied, it must "
    "still contain that occurrence. Never create a candidate_id or return offsets."
)

_V4_LOCATION_RULE = (
    "- Do not compute or output character offsets, start/end positions, or any numeric location. "
    "You never see or guess offsets -- the caller locates each quote in AGENT_REPORT by exact "
    "deterministic string match. A quote that does not appear verbatim, or that the caller cannot "
    "uniquely locate, is rejected, not fixed. If a sentence in the report is repeated more than "
    "once and you need to point at one specific occurrence, quote enough surrounding text (or "
    "reference the relevant candidate_id, if one exists) to make the location unambiguous -- do "
    "not rely on the caller guessing which occurrence you meant."
)
_V4_1_LOCATION_RULE = (
    "- Do not compute or output character offsets, start/end positions, or any numeric location. "
    "The caller first finds every character-for-character occurrence in the complete report. A "
    "candidate_id can disambiguate only when the quoted text occurs exactly once, fully inside "
    "that candidate's caller-owned span. Missing, unknown, wrong-source, zero-local-match, or "
    "multiple-local-match candidate binding is rejected. There is no first-match, nearest-match, "
    "fuzzy, normalized, or semantic fallback."
)

_V4_1_WIRE_TEXT_DELTAS = (
    (
        "- claim may be a concise faithful paraphrase of its supporting_quotes.",
        "- claim may be a concise faithful paraphrase of its supporting_evidence quote values.",
    ),
    (
        "- Every claim needs supporting_quotes: a list of one or more strings, each copied "
        "VERBATIM, character-for-character, from AGENT_REPORT. Do not paraphrase, summarize, "
        "truncate with an ellipsis, or alter punctuation/whitespace/case inside a quote.",
        "- Every claim needs supporting_evidence: a list of one or more objects. Each object's "
        "quote must be copied VERBATIM, character-for-character, from AGENT_REPORT. Do not "
        "paraphrase, summarize, truncate with an ellipsis, or alter punctuation/whitespace/case "
        "inside a quote.",
    ),
    (
        "- A claim may cite more than one supporting_quotes entry when separate, non-adjacent "
        "sentences jointly support it. Each quote is independently located by the caller; never "
        "combine two different report locations into a single quote string.",
        "- A claim may cite more than one supporting_evidence item when separate, non-adjacent "
        "sentences jointly support it. Each quote is independently located by the caller; never "
        "combine two different report locations into a single quote string.",
    ),
    (
        "- When the phrase you want to quote is wrapped in, or contains, formatting characters "
        "in AGENT_REPORT, your supporting_quotes entry must include those exact characters, in "
        "the exact same position.",
        "- When the phrase you want to quote is wrapped in, or contains, formatting characters "
        "in AGENT_REPORT, your supporting_evidence quote value must include those exact "
        "characters, in the exact same position.",
    ),
    (
        "each with its own supporting_quotes drawn from its own sentence.",
        "each with its own supporting_evidence item drawn from its own sentence.",
    ),
    (
        "as two separate supporting_quotes entries when both jointly support it.",
        "as two separate supporting_evidence items when both jointly support it.",
    ),
)

STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1 = STRUCTURED_OUTPUT_SHADOW_PROMPT_V4
for _old, _new in (
    (_V4_IDENTITY_RULE, _V4_1_IDENTITY_RULE),
    (_V4_OUTPUT_SHAPE, _V4_1_OUTPUT_SHAPE),
    (_V4_CANDIDATE_RULE, _V4_1_CANDIDATE_RULE),
    (_V4_LOCATION_RULE, _V4_1_LOCATION_RULE),
    *_V4_1_WIRE_TEXT_DELTAS,
):
    if STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1.count(_old) != 1:
        raise RuntimeError("V4_1_PARENT_PROMPT_DELTA_ANCHOR_INVALID")
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1 = STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1.replace(
        _old, _new
    )

if "supporting_quotes" in STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1:
    raise RuntimeError("V4_1_PARENT_WIRE_FIELD_REFERENCE_REMAINS")

STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256 = hashlib.sha256(
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1.encode("utf-8")
).hexdigest()
FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256 = (
    "c5ac3a9b44df24970d27ebd5670cb7f09eb934b01a0d99d7cd4ff93e5f225c6b"
)
if (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256
    != FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256
):
    raise RuntimeError("Phase 1 Master v4.1 Shadow prompt drifted without a version change")


def build_shadow_prompt_input_v4_1(request: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(request), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1}\n\nSHADOW_REQUEST_JSON:\n{payload}"


__all__ = [
    "LOCATION_PROTOCOL_DELTA",
    "PARENT_PROMPT_VERSION",
    "SEMANTIC_RULE_DELTA",
    "FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256",
    "STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1",
    "STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256",
    "STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_1",
    "build_shadow_prompt_input_v4_1",
]
