"""Round 3 (2026-10-04), section 4: a LIMITED, re-computable derived-
calculation verifier -- "两值比较;差值;相对差值百分比" only (two-value
comparison, delta, relative percent change), per the explicit 下一轮开发
任务单 scope. This is NOT a natural-language formula executor: it only
recognizes a small, fixed claim shape (one stated percent-above/below
comparison against a known, aliased indicator name) and only ever
verifies against a value ALREADY present in a real, already-saved
``source_registry.json`` entry's own ``data_snapshot`` -- it never invents
an "original input" from a number the claim itself states, and it never
sets ``content_support_status``/``HUMAN_REVIEWED`` or otherwise touches
the existing eligibility gate (``source_provenance.
compute_verified_support_eligibility``, unmodified).

Reuses, rather than re-implements:
- ``comqutor_alpha.source_provenance.iter_source_numeric_leaves`` for
  walking a source's own saved ``data_snapshot`` (reused, not copied);
- the SAME round/tolerance-aware comparison style Round 1/2 already
  established for the financial ``comparison`` dict shape (current/prior/
  delta/method), extended here to a ratio-based percent comparison.

A verified/refuted/non-computable RESULT here is additive evidence about
ONE specific stated numeric comparison -- never, by itself, a judgment on
any further interpretive clause in the same sentence (e.g. "confirming a
well-established primary uptrend" is a SEPARATE claim this module never
evaluates, by design -- see ``verify_percent_comparison_claim``'s own
return shape, which carries only the arithmetic verdict)."""

from __future__ import annotations

import re
from typing import Any

from comqutor_alpha.source_provenance import iter_source_numeric_leaves

# A small, EXPLICIT, bounded alias table for the known stockstats indicator
# field names a real market snapshot's own data_snapshot["indicators"]
# actually carries (see tradingagents.dataflows.y_finance / the real
# source_registry.json shape already established by Round 1/2) -- never a
# general metric-name NLP resolver. A reference phrase not in this table
# is honestly reported as unresolvable, never guessed.
_INDICATOR_ALIASES: dict[str, str] = {
    "200 sma": "close_200_sma", "200-day sma": "close_200_sma", "200 day sma": "close_200_sma",
    "200-sma": "close_200_sma",
    "50 sma": "close_50_sma", "50-day sma": "close_50_sma", "50 day sma": "close_50_sma",
    "50-sma": "close_50_sma",
    "10 ema": "close_10_ema", "10-day ema": "close_10_ema", "10-ema": "close_10_ema",
    "rsi": "rsi",
    "atr": "atr",
    "macd": "macd",
    "bollinger midline": "boll", "boll": "boll",
    "upper bollinger band": "boll_ub", "bollinger upper band": "boll_ub",
    "lower bollinger band": "boll_lb", "bollinger lower band": "boll_lb",
}

_PERCENT_COMPARISON_PATTERN = re.compile(
    r"(?P<value>[\d,]+\.?\d*)\s+is\s+(?:approximately\s+|about\s+|roughly\s+)?"
    r"(?P<percent>[\d.]+)%\s+(?P<direction>above|below)\s+(?:the\s+)?(?P<reference>[A-Za-z0-9 \-]+?)"
    r"(?=[,.;]|\s+(?:confirming|suggesting|indicating|which|and)\b|$)",
    re.IGNORECASE,
)

# "Approximately" display rounding (claim text) vs a recomputed value from
# raw saved inputs is never expected to match bit-exactly -- 0.5 percentage
# points covers one decimal place of real-world rounding without
# masking a genuinely wrong figure.
_PERCENT_TOLERANCE = 0.5


def verify_percent_comparison_claim(
    claim_text: str | None, sources: list[dict[str, Any]] | None
) -> dict[str, Any] | None:
    """Recognizes the fixed shape "``<value>`` is ``<percent>``% above/below
    the ``<reference>``" and, when it matches, independently recomputes the
    percent from two values ALREADY saved in one real source's own
    ``data_snapshot`` -- never from the claim's own stated numbers alone.

    Returns ``None`` when the claim text does not match this one fixed
    shape at all (this is not the claim this verifier applies to -- the
    caller should not report anything derived for it). Otherwise returns a
    structured verdict dict, always including ``inputs`` (source_id,
    field paths, and the exact raw values read back from disk) so the
    arithmetic can be independently re-checked by anyone, per John
    section 3.2.A's own requirement.
    """
    if not claim_text:
        return None
    match = _PERCENT_COMPARISON_PATTERN.search(claim_text)
    if not match:
        return None

    stated_value = float(match.group("value").replace(",", ""))
    stated_percent = float(match.group("percent"))
    direction = match.group("direction").lower()
    reference_text = match.group("reference").strip()
    alias_key = _INDICATOR_ALIASES.get(reference_text.lower())

    base_record: dict[str, Any] = {
        "operation": "percent_comparison",
        "stated_value": stated_value,
        "stated_percent": stated_percent,
        "stated_direction": direction,
        "reference_text": reference_text,
    }

    if alias_key is None:
        return {
            **base_record,
            "status": "REFERENCE_NOT_RESOLVABLE",
            "reason": (
                f"'{reference_text}' is not in this verifier's known indicator-alias table -- "
                "it cannot be mapped to any saved data_snapshot field without guessing. This is "
                "an honest unresolved reference, not proof the figure is wrong."
            ),
            "inputs": None,
        }

    for source in sources or ():
        if not isinstance(source, dict):
            continue
        snapshot = source.get("data_snapshot")
        if not isinstance(snapshot, dict):
            continue
        leaves = {".".join(path): value for path, value in iter_source_numeric_leaves(snapshot)}
        value_field = next((p for p in leaves if p.split(".")[-1] == "Close"), None)
        base_field = next((p for p in leaves if p.split(".")[-1] == alias_key), None)
        if value_field is None or base_field is None:
            continue
        current_value = leaves[value_field]
        base_value = leaves[base_field]
        if round(current_value, 2) != round(stated_value, 2):
            # This source has the reference field, but its own current
            # price does not match the claim's stated value -- not the
            # right source for this claim, keep looking.
            continue

        inputs = {
            "source_id": source.get("source_id"),
            "fragment_id": source.get("fragment_id"),
            "content_hash": source.get("content_hash"),
            "value_field": value_field,
            "value_from_saved_snapshot": current_value,
            "base_field": base_field,
            "base_from_saved_snapshot": base_value,
            "formula": "(value / base - 1) * 100",
            "formula_version": "derived_fact_verification.percent_comparison.v1",
        }

        if base_value == 0:
            return {
                **base_record,
                "status": "NON_COMPUTABLE_ZERO_DENOMINATOR",
                "reason": "the base value is exactly 0 -- a percent change against a zero base is undefined.",
                "inputs": inputs,
            }
        if base_value < 0:
            return {
                **base_record,
                "status": "NON_COMPUTABLE_NEGATIVE_BASE",
                "reason": (
                    "the base value is negative -- a signed percent-change formula over a negative "
                    "base period produces a misleading growth/decline direction, so this is reported "
                    "as non-computable rather than returning a number that LOOKS like a normal percent."
                ),
                "inputs": inputs,
            }

        recomputed_percent = (current_value / base_value - 1.0) * 100.0
        recomputed_direction = "above" if recomputed_percent >= 0 else "below"
        inputs["recomputed_percent"] = recomputed_percent
        direction_matches = recomputed_direction == direction
        percent_matches = abs(abs(recomputed_percent) - stated_percent) <= _PERCENT_TOLERANCE
        return {
            **base_record,
            "status": "VERIFIED" if (direction_matches and percent_matches) else "REFUTED",
            "recomputed_percent": round(recomputed_percent, 4),
            "inputs": inputs,
        }

    return {
        **base_record,
        "status": "INPUT_NOT_LOCATABLE",
        "reason": (
            f"no saved source has both a 'Close'-shaped current value matching {stated_value} AND a "
            f"'{alias_key}' field -- the comparison cannot be independently recomputed from anything "
            "actually persisted for this run."
        ),
        "inputs": None,
    }


__all__ = ["verify_percent_comparison_claim"]
