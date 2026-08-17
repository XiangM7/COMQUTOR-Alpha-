"""v4.2 deterministic global-exact-provenance protocol identity.

Product Owner final decision, made after a real, persisted v4.1 Re-Canary
root-cause diagnosis
(``docs/audit_artifacts/phase1_master/phase1_v4_1_location_root_cause.md``):
the Provider must never be asked to identify WHERE its Evidence quote is
located inside COMQUTOR's internal representation of the source report --
not a candidate_id, not an offset, not a segment/window number, nothing.
The Provider's only job is WHAT the Claim and Evidence are; COMQUTOR's own
deterministic resolver (``structured_output_shadow_v4_2.py``) is the sole
authority for WHERE that Evidence text exists.

This is a genuine, small text delta from v4's frozen prompt -- NOT byte-
identical -- because v4's prompt still described ``CANDIDATE_HINTS``/
``candidate_id`` as an available, optional mechanism (see
``structured_output_shadow_prompt_v4.py``), and the root-cause diagnosis
found that merely offering that option was actively harmful: 58 of 61
Evidence rejections in the real, failed v4.1 Re-Canary were already-unique,
correctly-copied quotes that failed ONLY because the model voluntarily
attached a candidate_id whose span did not happen to contain them. v4.2
therefore removes every candidate/segment/offset-related instruction and
wire field from both the request and the response shape. The semantic
extraction rules themselves (what counts as a faithful claim, what
evidence completeness means, uncertainty/attribution preservation, Markdown
exactness) are otherwise unchanged from v4 -- copied verbatim except for
the four candidate-related edits documented below. v4 and v4.1 both remain
frozen and are never modified.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v4 import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4,
)

STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_2 = (
    "structured_adapter.claim_extraction_shadow.v4.2"
)
PARENT_PROMPT_VERSION = "structured_adapter.claim_extraction_shadow.v4"
PARENT_SEMANTIC_BASELINE = "structured_adapter.claim_extraction_shadow.v4"
QUALITY_BASELINE = "PASS_V4"
SEMANTIC_EXTRACTION_DELTA = "NONE"
EVIDENCE_TEXT_REQUIREMENT_DELTA = "NONE"
PROVENANCE_RESOLUTION_DELTA = "GLOBAL_EXACT_SEARCH_WITH_CANONICAL_FIRST_OCCURRENCE"
CANDIDATE_BINDING_REMOVED = True
CANDIDATE_BINDING_ACTIVE = False

# ---------------------------------------------------------------------------
# Exactly four anchored text edits relative to v4's frozen prompt -- every
# other character is identical. Each anchor must occur exactly once in v4's
# text or this module fails closed at import time (RuntimeError below),
# exactly like v4.1's own anchor-replace derivation.
# ---------------------------------------------------------------------------

_V4_CLAIM_RULES_CANDIDATE_TEXT = (
    "- Propose atomic, faithful claims. You may retain one candidate, merge "
    "adjacent candidates, split one candidate, omit headings/disclaimers/"
    "transitions/procedural text, abstain, or return an empty claims list."
)
_V4_2_CLAIM_RULES_TEXT = (
    "- Propose atomic, faithful claims directly from AGENT_REPORT. You may "
    "treat one sentence or statement as one claim, merge adjacent related "
    "sentences into one claim, split one sentence into multiple claims, omit "
    "headings/disclaimers/transitions/procedural text, abstain, or return an "
    "empty claims list."
)

_V4_CANDIDATE_HINTS_BULLET = (
    "\n- CANDIDATE_HINTS (if present below) are OPTIONAL location hints "
    "only, with no semantic authority: you may ignore them, agree with "
    "them, or propose claims they do not cover. They never cover the whole "
    "report -- you must still read AGENT_REPORT yourself. A candidate_id is "
    "never required on a claim."
)
_V4_2_NO_CANDIDATE_HINTS_BULLET = ""

_V4_LOCATION_RULE = (
    "- Do not compute or output character offsets, start/end positions, or "
    "any numeric location. You never see or guess offsets -- the caller "
    "locates each quote in AGENT_REPORT by exact deterministic string "
    "match. A quote that does not appear verbatim, or that the caller "
    "cannot uniquely locate, is rejected, not fixed. If a sentence in the "
    "report is repeated more than once and you need to point at one "
    "specific occurrence, quote enough surrounding text (or reference the "
    "relevant candidate_id, if one exists) to make the location unambiguous "
    "-- do not rely on the caller guessing which occurrence you meant."
)
_V4_2_LOCATION_RULE = (
    "- Do not compute or output character offsets, start/end positions, "
    "candidate identifiers, segment numbers, or any numeric or symbolic "
    "location. You never see or guess a location -- the caller locates each "
    "quote in AGENT_REPORT by exact deterministic string match. A quote "
    "that does not appear verbatim is rejected, not fixed. If the exact "
    "sentence or phrase you quote happens to repeat more than once in "
    "AGENT_REPORT, that is fine and expected -- the caller resolves it "
    "deterministically on its own; you do not need to, and cannot, "
    "disambiguate which occurrence you meant."
)

_V4_ABSTENTION_SHAPE = (
    '"abstentions":[{"candidate_ids":[],"reason_code":"NO_RELIABLE_CLAIM","notes":""}]'
)
_V4_2_ABSTENTION_SHAPE = (
    '"abstentions":[{"reason_code":"NO_RELIABLE_CLAIM","notes":""}]'
)

_ANCHORS = (
    (_V4_CLAIM_RULES_CANDIDATE_TEXT, _V4_2_CLAIM_RULES_TEXT),
    (_V4_CANDIDATE_HINTS_BULLET, _V4_2_NO_CANDIDATE_HINTS_BULLET),
    (_V4_LOCATION_RULE, _V4_2_LOCATION_RULE),
    (_V4_ABSTENTION_SHAPE, _V4_2_ABSTENTION_SHAPE),
)

STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2 = STRUCTURED_OUTPUT_SHADOW_PROMPT_V4
for _old, _new in _ANCHORS:
    if STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2.count(_old) != 1:
        raise RuntimeError("V4_2_PARENT_PROMPT_DELTA_ANCHOR_INVALID")
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2 = STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2.replace(_old, _new)

for _forbidden in ("candidate_id", "CANDIDATE_HINTS", "candidate_ids", "candidate_index"):
    if _forbidden in STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2:
        raise RuntimeError(f"V4_2_PROMPT_STILL_REFERENCES_CANDIDATE_CONCEPT:{_forbidden}")

STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256 = hashlib.sha256(
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2.encode("utf-8")
).hexdigest()
FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256 = (
    "19196137044e04ff8e5258b6e3a93463fedb6cf0e64725b1626d5b9c69049945"
)
if (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256
    != FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256
):
    raise RuntimeError("Phase 1 Master v4.2 Shadow prompt drifted without a version change")


def build_shadow_prompt_input_v4_2(request: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(request), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2}\n\nSHADOW_REQUEST_JSON:\n{payload}"


__all__ = [
    "CANDIDATE_BINDING_ACTIVE",
    "CANDIDATE_BINDING_REMOVED",
    "EVIDENCE_TEXT_REQUIREMENT_DELTA",
    "FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256",
    "PARENT_PROMPT_VERSION",
    "PARENT_SEMANTIC_BASELINE",
    "PROVENANCE_RESOLUTION_DELTA",
    "QUALITY_BASELINE",
    "SEMANTIC_EXTRACTION_DELTA",
    "STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2",
    "STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256",
    "STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_2",
    "build_shadow_prompt_input_v4_2",
]
