"""COMQUTOR Structure Output Contract -- the text appended to existing
TradingAgents prompts (never a new LLM call).

Renders the real production factor/relation vocabulary
(``canonical_vocabulary.build_canonical_relation_vocabulary``) into a
human-readable block plus a strict machine-readable output-format contract,
so the *same* TradingAgents LLM call that produces a normal analyst/debate/
risk report also appends one ``COMQUTOR_CANONICAL_RELATIONS`` JSON block at
the end of that same response.
"""

from __future__ import annotations

import hashlib
from typing import Any

RELATION_BLOCK_MARKER = "COMQUTOR_CANONICAL_RELATIONS"
RELATION_BLOCK_SCHEMA_VERSION = "comqutor_relation_output_v1"
PROMPT_CONTRACT_VERSION = "comqutor_structure_output_contract.v1"

_VALID_ASSERTION_STATUSES = ("asserted", "hedged", "conditional", "hypothetical")

# The two example factors used in the prompt's worked examples -- picked by
# looking them up in the real vocabulary at render time (never hardcoded as
# IDs), falling back gracefully if either is renamed/removed from the
# production taxonomy in the future.
_EXAMPLE_SOURCE_FACTOR = "AI CapEx"
_EXAMPLE_TARGET_FACTOR = "GPU Demand"
_EXAMPLE_SECOND_SOURCE_FACTOR = "Inference Demand"
_EXAMPLE_SECOND_TARGET_FACTOR = "Revenue Growth"


def _factor_block(factor: dict[str, Any]) -> str:
    aliases = ", ".join(factor["aliases"]) if factor.get("aliases") else "(none)"
    return (
        f"- {factor['factor_id']}\n"
        f"  Display name: {factor['display_name']}\n"
        f"  Known expressions: {aliases}\n"
        f"  Description: {factor['description']}"
    )


def _relation_block(relation: dict[str, Any]) -> str:
    return (
        f"- {relation['relation_type']}\n"
        f"  Canonical phrase: {relation['display_phrase']}\n"
        f"  Meaning: {relation['definition']}\n"
        f"  Directional: {relation['directional']}"
    )


def _find_factor_id(vocabulary: dict[str, Any], display_name: str) -> str | None:
    for factor in vocabulary.get("factors") or []:
        if factor.get("display_name") == display_name:
            return str(factor.get("factor_id"))
    return None


def _worked_example(vocabulary: dict[str, Any]) -> str:
    ai_capex_id = _find_factor_id(vocabulary, _EXAMPLE_SOURCE_FACTOR)
    gpu_demand_id = _find_factor_id(vocabulary, _EXAMPLE_TARGET_FACTOR)
    inference_id = _find_factor_id(vocabulary, _EXAMPLE_SECOND_SOURCE_FACTOR)
    revenue_id = _find_factor_id(vocabulary, _EXAMPLE_SECOND_TARGET_FACTOR)
    causal_type = next(
        (r["relation_type"] for r in vocabulary.get("relations") or [] if r["relation_type"] == "causal"),
        "causal",
    )
    supportive_type = next(
        (r["relation_type"] for r in vocabulary.get("relations") or [] if r["relation_type"] == "supportive"),
        "supportive",
    )

    lines = ["VALID EXAMPLES (illustrative only -- use the real IDs/aliases above, never these literal English words as IDs):", ""]
    if ai_capex_id and gpu_demand_id:
        lines += [
            'Original statement: "Hyperscaler AI capital spending is driving demand for GPUs."',
            f"Valid canonical relation: {ai_capex_id} --{causal_type}--> {gpu_demand_id}",
            "",
        ]
    if inference_id and revenue_id:
        lines += [
            'Original statement: "Growing inference workloads support Nvidia\'s data-center revenue growth."',
            f"Valid canonical relation: {inference_id} --{supportive_type}--> {revenue_id}",
            "",
        ]
    lines += [
        "INVALID EXAMPLE 1 (parallel facts, no stated direction):",
        f'"{_EXAMPLE_SOURCE_FACTOR} is strong. {_EXAMPLE_TARGET_FACTOR} is also strong." -> relations = []',
        "Reason: both facts are merely stated side by side; no directional relation is expressed.",
        "",
        "INVALID EXAMPLE 2 (question, not an assertion):",
        f'"Could {_EXAMPLE_SOURCE_FACTOR} increase {_EXAMPLE_TARGET_FACTOR}?" -> must NOT be asserted.',
        'Return relations = [] or, if your schema allows it, assertion_status = "hypothetical" -- '
        "a hypothetical relation must never be treated as admitted.",
        "",
        "INVALID EXAMPLE 3 (conditional, must stay conditional):",
        f'"If hyperscaler spending continues, {_EXAMPLE_TARGET_FACTOR.lower()} may increase." -> '
        'assertion_status must stay "conditional" or "hedged", never promoted to unconditional "asserted".',
    ]
    return "\n".join(lines)


def build_structure_output_contract_prompt_suffix(vocabulary: dict[str, Any]) -> str:
    """Render the full COMQUTOR Structure Output Contract text appended to
    every existing TradingAgents agent prompt. Deterministic: the same
    vocabulary always renders the same text (byte for byte), so its sha256
    is a stable "what did the LLM actually see" audit fingerprint.
    """
    factors_text = "\n".join(_factor_block(f) for f in vocabulary.get("factors") or [])
    relations_text = "\n".join(_relation_block(r) for r in vocabulary.get("relations") or [])

    return f"""

---
COMQUTOR STRUCTURE OUTPUT CONTRACT ({PROMPT_CONTRACT_VERSION})

You must still write your complete, normal, professional analysis report exactly as instructed above --
nothing about your normal report changes. In addition, after your normal report, append one machine-readable
relation block extracting ONLY the factor-to-factor relations your OWN report text explicitly states.

ALLOWED COMQUTOR FACTORS (taxonomy_version={vocabulary.get('taxonomy_version')}, sha256={vocabulary.get('taxonomy_sha256')})

{factors_text}

ALLOWED COMQUTOR RELATIONS (relation_registry_version={vocabulary.get('relation_registry_version')})

{relations_text}

{_worked_example(vocabulary)}

OUTPUT FORMAT: after your normal report text, on its own line, write the literal marker
{RELATION_BLOCK_MARKER}
followed by a fenced json code block with exactly this shape:

```json
{{
  "schema_version": "{RELATION_BLOCK_SCHEMA_VERSION}",
  "relations": [
    {{
      "source_factor_id": "<one of the factor IDs listed above>",
      "relation_type": "<one of the relation types listed above>",
      "target_factor_id": "<one of the factor IDs listed above>",
      "evidence_quote": "<verbatim substring copied from your own report text above>",
      "assertion_status": "<one of: {', '.join(_VALID_ASSERTION_STATUSES)}>",
      "confidence": 0.0
    }}
  ]
}}
```

When your report states no clear factor-to-factor relation, return an empty array:
{RELATION_BLOCK_MARKER}
```json
{{"schema_version": "{RELATION_BLOCK_SCHEMA_VERSION}", "relations": []}}
```

Rules (all mandatory):
1. Only map relations your OWN report text has already explicitly stated -- never add a new fact.
2. Never use outside/common-sense knowledge to fill in a relation your text does not state.
3. Never turn two facts merely mentioned together into a causal or supportive relation.
4. Never turn a correlation into a causal claim.
5. Never turn a question into an asserted relation.
6. Never turn a pure hypothetical into a confident relation.
7. Never promote a conditional statement into an unconditional fact.
8. source_factor_id must be exactly one of the factor IDs listed above -- never invent a new one.
9. target_factor_id must be exactly one of the factor IDs listed above -- never invent a new one.
10. relation_type must be exactly one of the relation types listed above -- never invent a new one.
11. evidence_quote must be an exact, verbatim substring of your own report text above.
12. Never fabricate a ticker-specific temporary factor that is not in the allowed list.
13. Never invent a relation solely to avoid returning an empty array -- an empty array is a fully valid answer.
14. Your normal report text must remain complete, natural, and unabridged -- it must never be reduced to only
    the standardized relation sentences.
---
"""


def compute_prompt_contract_sha256(prompt_suffix: str) -> str:
    return hashlib.sha256(prompt_suffix.encode("utf-8")).hexdigest()


__all__ = [
    "RELATION_BLOCK_MARKER",
    "RELATION_BLOCK_SCHEMA_VERSION",
    "PROMPT_CONTRACT_VERSION",
    "build_structure_output_contract_prompt_suffix",
    "compute_prompt_contract_sha256",
]
