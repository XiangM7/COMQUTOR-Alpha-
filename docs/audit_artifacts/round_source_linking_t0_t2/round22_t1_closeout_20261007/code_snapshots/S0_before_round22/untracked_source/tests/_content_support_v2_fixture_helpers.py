"""2026-10-06 (T1 judgment-standard correction, v2 contract): shared helper
for building a COMPLETE, internally-consistent v2-shaped fake Provider
response for content_support_verification -- not a test file itself.

The v2 contract added required fields (support_basis, inference_facts,
inference_assumptions, unsupported_remainder_materiality) that
_v2_structural_contradiction in content_support_llm.py now checks for
internal consistency. Every existing fixed-response test across this
project's content-support test files builds a fake Provider response dict
by hand; this helper fills in sensible, VALID v2 defaults for the fields a
pre-v2 test never needed to think about, so each test's own diff stays
about what it's actually testing.
"""

from __future__ import annotations

from typing import Any

_BACKGROUND_LIKE_STATUSES = {"BACKGROUND", "CITATION_ONLY", "INSUFFICIENT"}
_INFERENCE_BASES = {"DERIVED_CALCULATION", "GROUNDED_INFERENCE"}


def v2_response(
    *,
    claim_id: str,
    status: str,
    used_source_id: str | None = None,
    used_location: str | None = None,
    supporting_quote_or_data: str | None = None,
    rationale: str = "x",
    core_proposition: str = "x",
    supported_proposition: str = "",
    unsupported_remainder: str = "",
    support_basis: str | None = None,
    materiality: str | None = None,
    inference_facts: list[str] | None = None,
    inference_assumptions: list[str] | None = None,
) -> dict[str, Any]:
    if support_basis is None:
        support_basis = "NONE" if status in _BACKGROUND_LIKE_STATUSES else "DIRECT_FACT"
    if materiality is None:
        materiality = "NONE" if status == "INSUFFICIENT" or not unsupported_remainder.strip() else "MATERIAL"
    if inference_facts is None:
        inference_facts = ["a real cited fact"] if support_basis in _INFERENCE_BASES else []
    if inference_assumptions is None:
        inference_assumptions = ["a disclosed assumption"] if support_basis == "GROUNDED_INFERENCE" else []
    return {
        "claim_id": claim_id,
        "core_proposition": core_proposition,
        "status": status,
        "support_basis": support_basis,
        "used_source_id": used_source_id,
        "used_location": used_location,
        "supporting_quote_or_data": supporting_quote_or_data,
        "inference_facts": inference_facts,
        "inference_assumptions": inference_assumptions,
        "rationale": rationale,
        "supported_proposition": supported_proposition,
        "unsupported_remainder": unsupported_remainder,
        "unsupported_remainder_materiality": materiality,
    }
