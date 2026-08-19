"""QA Closure v0.1.2 Item 5: Neutral / Unclassified Findings Audit.

Pure, deterministic post-hoc analysis over an already-built
``unclassified_findings.json`` payload (see
``comqutor_alpha.api.unclassified_findings``). Never re-runs the Alpha
Mapper, Evidence Stance classifier, Evidence Fact grouping, B1-B5, or an
LLM/Provider -- every field this module reads (``agent``, ``reason``,
``reason_codes``, ``claim``, ``evidence``, ``ticker_specific``,
``evidence_fact_group_id``, ``duplicate_group_id``, ``matched_alpha``) is
already computed and persisted by the existing A3 pipeline. This module
only groups, counts, and (for repeated-pattern detection) reuses the
existing, already-established ``normalize_claim_for_dedupe`` text
normalizer verbatim -- never a new fuzzy/semantic matcher, never LLM
clustering.

Findings can legitimately carry more than one canonical reason
(``reason_codes``); this module reports both the primary-reason breakdown
(``finding_count`` -- mutually exclusive, one bucket per finding, using
the same frozen priority order A3 already assigned) and the
reason-occurrence breakdown (``reason_occurrence_count`` -- every
applicable reason counted, matching the source payload's own
``reason_counts``) rather than silently picking one and implying the
other.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from comqutor_alpha.api.unclassified_findings import REASON_PRIORITY, REASON_UNRESOLVED
from comqutor_alpha.structure_engine.structured_output_adapter import normalize_claim_for_dedupe

SCHEMA_VERSION = "neutral_unclassified_audit.v1"
DEFAULT_TOP_N = 20

UNKNOWN_AGENT = "unknown_agent"
MISSING_REASON = "missing_reason"

# Section 10's fixed diagnostic vocabulary. Only ever assigned by an
# explicit, documented rule below -- "unclear" is the honest default
# whenever the observed data does not support a confident label, never a
# guess dressed up as one of the other seven.
CLASSIFICATION_EXPECTED_UNCERTAINTY = "expected_uncertainty"
CLASSIFICATION_PROMPT_REDUNDANCY = "prompt_redundancy"
CLASSIFICATION_GENERIC_BACKGROUND = "generic_background"
CLASSIFICATION_DUPLICATE_OUTPUT = "duplicate_output"
CLASSIFICATION_TICKER_SPECIFICITY_FAILURE = "ticker_specificity_failure"
CLASSIFICATION_ALPHA_TAXONOMY_GAP = "alpha_taxonomy_gap"
CLASSIFICATION_LOW_CONFIDENCE_MAPPING = "low_confidence_mapping"
CLASSIFICATION_OTHER = "other"
CLASSIFICATION_UNCLEAR = "unclear"

# A pattern's dominant reason is prompt_redundancy-eligible (a repeated,
# unmatched, identically-worded observation -- worth a prompt review) only
# once the SAME exact-normalized text has recurred at least this many
# times. Below this, a single/rare no_alpha_match occurrence is reported
# "unclear" rather than guessed -- there is no deterministic way to tell
# "genuine taxonomy gap" from "just one unique unmatched claim" from
# repetition count alone.
PROMPT_REDUNDANCY_MIN_COUNT = 3

# Minimum total occurrences (across the whole 699, not just the Top 20)
# an (agent, problem) combination must have before this module proposes a
# prompt-fix recommendation for it -- keeps recommendations traceable to a
# real, non-trivial volume of observed data rather than a single outlier.
PROMPT_FIX_MIN_SUPPORT = 5


def _agent_of(finding: Mapping[str, Any]) -> str:
    agent = finding.get("agent")
    return str(agent) if isinstance(agent, str) and agent else UNKNOWN_AGENT


def _primary_reason_of(finding: Mapping[str, Any]) -> str:
    reason = finding.get("reason")
    return str(reason) if isinstance(reason, str) and reason else MISSING_REASON


def _reason_codes_of(finding: Mapping[str, Any]) -> list[str]:
    codes = finding.get("reason_codes")
    if isinstance(codes, list) and codes:
        return [str(c) for c in codes]
    primary = finding.get("reason")
    return [str(primary)] if isinstance(primary, str) and primary else [MISSING_REASON]


def _pattern_key(finding: Mapping[str, Any]) -> str:
    """Exact-normalized-text pattern key -- reuses the existing, already-
    established dedupe normalizer verbatim (NFKC + lowercase + whitespace
    collapse + outer punctuation stripped; numbers/tickers/direction words
    preserved, so two claims differing only in magnitude are two different
    patterns, never merged). Falls back to the ``evidence`` field only when
    ``claim`` is absent (never both empty for a real finding, but handled
    honestly either way)."""
    text = finding.get("claim") or finding.get("evidence") or ""
    key = normalize_claim_for_dedupe(text)
    return key or "__EMPTY_TEXT__"


def _percentage(count: int, total: int) -> float:
    return round(100.0 * count / total, 2) if total else 0.0


def _grouped_counts(findings: Sequence[Mapping[str, Any]], key_fn) -> dict[str, int]:
    counts: Counter[str] = Counter(key_fn(f) for f in findings)
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _by_agent(findings: Sequence[Mapping[str, Any]], audited_count: int) -> dict[str, Any]:
    counts = _grouped_counts(findings, _agent_of)
    return {
        "counts": counts,
        "percentage_of_total": {agent: _percentage(n, audited_count) for agent, n in counts.items()},
        "sum_equals_audited_count": sum(counts.values()) == audited_count,
    }


def _by_reason(findings: Sequence[Mapping[str, Any]], audited_count: int) -> dict[str, Any]:
    finding_counts = _grouped_counts(findings, _primary_reason_of)
    occurrence_counter: Counter[str] = Counter()
    for finding in findings:
        occurrence_counter.update(_reason_codes_of(finding))
    occurrence_counts = dict(sorted(occurrence_counter.items(), key=lambda kv: (-kv[1], kv[0])))
    return {
        # Mutually exclusive: one primary reason per finding, sums to
        # audited_count exactly.
        "finding_count": finding_counts,
        # NOT mutually exclusive: a finding with 2 applicable reasons is
        # counted once under each -- sum can exceed audited_count. Matches
        # the source payload's own reason_counts exactly.
        "reason_occurrence_count": occurrence_counts,
        "finding_count_sum_equals_audited_count": sum(finding_counts.values()) == audited_count,
        "multi_reason_finding_count": sum(1 for f in findings if len(_reason_codes_of(f)) > 1),
    }


def _by_agent_and_reason(findings: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    table: dict[str, Counter[str]] = {}
    for finding in findings:
        agent = _agent_of(finding)
        table.setdefault(agent, Counter())[_primary_reason_of(finding)] += 1
    return {
        agent: dict(sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0])))
        for agent, reasons in sorted(table.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))
    }


def _classify_pattern(dominant_reason: str, count: int) -> str:
    """Deterministic, rule-based only (task section 10) -- never a
    semantic/LLM judgment. Documented per branch; "unclear" whenever the
    observed data (dominant reason + repetition count alone) does not
    support a confident label."""
    if dominant_reason == "duplicate_supporting_text":
        return CLASSIFICATION_DUPLICATE_OUTPUT
    if dominant_reason == "generic_background":
        return CLASSIFICATION_GENERIC_BACKGROUND
    if dominant_reason == "no_ticker_specific_evidence":
        return CLASSIFICATION_TICKER_SPECIFICITY_FAILURE
    if dominant_reason == "low_confidence":
        return CLASSIFICATION_LOW_CONFIDENCE_MAPPING
    if dominant_reason == "no_alpha_match":
        # A high-repetition, verbatim-identical, still-unmatched pattern
        # is worth a prompt-level look (the model is repeating itself);
        # a rare/unique one cannot be deterministically distinguished from
        # a genuine one-off taxonomy gap vs. ordinary diverse content.
        return CLASSIFICATION_PROMPT_REDUNDANCY if count >= PROMPT_REDUNDANCY_MIN_COUNT else CLASSIFICATION_UNCLEAR
    if dominant_reason == REASON_UNRESOLVED:
        return CLASSIFICATION_OTHER
    return CLASSIFICATION_UNCLEAR


def _pattern_summary(findings: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    groups: Counter[str] = Counter(_pattern_key(f) for f in findings)
    repeated = {key: n for key, n in groups.items() if n >= 2}
    return {
        "total_findings": len(findings),
        "total_distinct_normalized_patterns": len(groups),
        "total_repeated_pattern_count": len(repeated),
        "findings_within_a_repeated_pattern": sum(repeated.values()),
        "findings_fully_unique": len(findings) - sum(repeated.values()),
    }


def _top_n_patterns(findings: Sequence[Mapping[str, Any]], *, top_n: int) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for finding in findings:
        groups.setdefault(_pattern_key(finding), []).append(finding)

    # Deterministic ranking: count desc, then the normalized key itself
    # asc as a stable tie-breaker (never insertion order, never a set's
    # incidental iteration order). A "pattern" that occurs exactly once is
    # not a repeated pattern at all -- excluded here rather than padding
    # the Top-N list with singletons, which would misrepresent how much
    # genuine repetition actually exists (see total_repeated_pattern_count
    # on the caller's own output for the honest total).
    ranked = sorted(
        ((key, members) for key, members in groups.items() if len(members) >= 2),
        key=lambda kv: (-len(kv[1]), kv[0]),
    )

    patterns: list[dict[str, Any]] = []
    for rank, (key, members) in enumerate(ranked[:top_n], start=1):
        agents = _grouped_counts(members, _agent_of)
        reasons = _grouped_counts(members, _primary_reason_of)
        dominant_reason = next(iter(reasons)) if reasons else MISSING_REASON
        # Up to 3 distinct raw (pre-normalization) texts, deterministically
        # ordered -- never dozens of raw duplicates dumped into the report.
        raw_texts = sorted({str(m.get("claim") or m.get("evidence") or "") for m in members})[:3]
        example_claim_ids = sorted(str(m.get("claim_id") or "") for m in members)[:3]
        patterns.append(
            {
                "rank": rank,
                "normalized_pattern": key,
                "count": len(members),
                "agents": agents,
                "reason_codes": reasons,
                "example_findings": raw_texts,
                "example_claim_ids": example_claim_ids,
                "classification": _classify_pattern(dominant_reason, len(members)),
            }
        )
    return patterns


def _ticker_specificity_audit(findings: Sequence[Mapping[str, Any]], audited_count: int) -> dict[str, Any]:
    subset = [f for f in findings if _primary_reason_of(f) == "no_ticker_specific_evidence"]
    top_patterns = _top_n_patterns(subset, top_n=5)
    return {
        "count": len(subset),
        "percentage_of_total": _percentage(len(subset), audited_count),
        "top_source_agents": _grouped_counts(subset, _agent_of),
        "top_repeated_patterns": top_patterns,
    }


def _duplicate_audit(findings: Sequence[Mapping[str, Any]], audited_count: int) -> dict[str, Any]:
    subset = [f for f in findings if _primary_reason_of(f) == "duplicate_supporting_text"]
    fact_groups: dict[str, list[str]] = {}
    for finding in subset:
        group_id = finding.get("evidence_fact_group_id")
        if group_id:
            fact_groups.setdefault(str(group_id), []).append(str(finding.get("claim_id") or ""))
    largest = max(fact_groups.values(), key=len) if fact_groups else []
    return {
        "duplicate_finding_count": len(subset),
        "percentage_of_total": _percentage(len(subset), audited_count),
        "unique_duplicate_patterns": len(fact_groups),
        "largest_duplicate_cluster": {
            "evidence_fact_group_id": max(fact_groups, key=lambda k: len(fact_groups[k])) if fact_groups else None,
            "member_count": len(largest),
            "example_claim_ids": sorted(largest)[:5],
        },
        "top_duplicate_generating_agents": _grouped_counts(subset, _agent_of),
    }


def _possible_taxonomy_gaps(findings: Sequence[Mapping[str, Any]], *, top_n: int = 10) -> list[dict[str, Any]]:
    """Section 15: never a confident classification, never new Alpha IDs,
    never a remap -- the most-repeated still-unmatched patterns, surfaced
    for a human Product Owner to judge, explicitly labeled as a
    recommendation-only candidate list."""
    subset = [f for f in findings if _primary_reason_of(f) == "no_alpha_match"]
    candidates = [
        p for p in _top_n_patterns(subset, top_n=top_n) if p["count"] >= PROMPT_REDUNDANCY_MIN_COUNT
    ]
    for candidate in candidates:
        candidate["note"] = (
            "possible_taxonomy_gap candidate -- repeated, still-unmatched text; requires human Product "
            "Owner review, never auto-mapped to an existing or new Alpha ID by this audit."
        )
    return candidates


def _healthy_vs_avoidable_split(
    findings: Sequence[Mapping[str, Any]], top_patterns: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Best-effort, deterministic, and explicitly conservative (task
    section 12): only findings belonging to a Top-N pattern whose
    classification is confidently avoidable/healthy are counted; every
    finding outside the Top-N pattern set (the long tail of genuinely
    singular observations) is left in ``unclear`` rather than assigned a
    split it cannot be defensibly assigned to from pattern data alone."""
    avoidable_labels = {
        CLASSIFICATION_PROMPT_REDUNDANCY,
        CLASSIFICATION_DUPLICATE_OUTPUT,
    }
    healthy_labels = {
        CLASSIFICATION_GENERIC_BACKGROUND,
        CLASSIFICATION_TICKER_SPECIFICITY_FAILURE,
    }
    claim_id_to_label: dict[str, str] = {}
    for pattern in top_patterns:
        label = pattern["classification"]
        bucket = "avoidable" if label in avoidable_labels else "healthy" if label in healthy_labels else None
        if bucket is None:
            continue
        for claim_id in pattern.get("example_claim_ids") or ():
            claim_id_to_label.setdefault(claim_id, bucket)

    # example_claim_ids is capped at 3 per pattern (never the full member
    # list, to keep the report small) -- so this split is a *lower bound*
    # sample over the Top-N patterns only, never a claim it covers the
    # full 699. Reported honestly as such.
    healthy_sample = sum(1 for v in claim_id_to_label.values() if v == "healthy")
    avoidable_sample = sum(1 for v in claim_id_to_label.values() if v == "avoidable")
    return {
        "method": (
            "Sampled from up to 3 example claim_ids per Top-N repeated pattern only (never the full "
            "population) -- a deterministic lower bound, not a claimed split of all findings. The "
            "remaining majority of findings (the long tail outside the Top-N patterns, and any Top-N "
            "member beyond the first 3 examples) is honestly left unclear rather than force-classified."
        ),
        "healthy_uncertainty_sample_count": healthy_sample,
        "potentially_avoidable_sample_count": avoidable_sample,
        "unclear": (
            "A safe, deterministic full-population split could not be established from Top-N pattern "
            "membership alone; see reason/pattern breakdowns above for the complete, exact accounting."
        ),
    }


def _suggested_prompt_fixes(
    by_agent_and_reason: Mapping[str, Mapping[str, int]], top_patterns: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Recommendations only (task section 11) -- never applied to any
    prompt. Derived strictly from observed (agent, reason) volume plus
    corroborating Top-N pattern evidence; an (agent, problem) combination
    below PROMPT_FIX_MIN_SUPPORT total occurrences is not proposed."""
    fixes: list[dict[str, Any]] = []

    generic_background_by_agent: Counter[str] = Counter()
    no_ticker_by_agent: Counter[str] = Counter()
    redundant_by_agent: Counter[str] = Counter()
    for pattern in top_patterns:
        label = pattern["classification"]
        for agent, count in pattern["agents"].items():
            if label == CLASSIFICATION_PROMPT_REDUNDANCY:
                redundant_by_agent[agent] += count

    for agent, reasons in by_agent_and_reason.items():
        if reasons.get("generic_background", 0) > 0:
            generic_background_by_agent[agent] = reasons["generic_background"]
        if reasons.get("no_ticker_specific_evidence", 0) > 0:
            no_ticker_by_agent[agent] = reasons["no_ticker_specific_evidence"]

    for agent, count in generic_background_by_agent.most_common():
        if count < PROMPT_FIX_MIN_SUPPORT:
            continue
        fixes.append(
            {
                "target_agent": agent,
                "observed_problem": (
                    "Repeated background/mentions-only commentary with no supports/opposes stance toward "
                    "any matched Alpha (generic_background)."
                ),
                "supporting_pattern_count": count,
                "suggested_change": (
                    "Prompt the agent to explicitly state whether each extracted finding takes a directional "
                    "position on a named Alpha concept, or to explicitly tag it as background context."
                ),
                "expected_effect": "Reduce avoidable generic_background findings from this agent.",
                "risk": "May suppress genuinely useful macro/background context if over-applied.",
                "status": "recommendation_only",
            }
        )

    for agent, count in no_ticker_by_agent.most_common():
        if count < PROMPT_FIX_MIN_SUPPORT:
            continue
        fixes.append(
            {
                "target_agent": agent,
                "observed_problem": "Repeated findings lacking ticker-specific language (no_ticker_specific_evidence).",
                "supporting_pattern_count": count,
                "suggested_change": (
                    "Prompt the agent to name the specific ticker/company explicitly in each extracted "
                    "finding rather than relying on implicit context from the surrounding report."
                ),
                "expected_effect": "Reduce avoidable no_ticker_specific_evidence findings from this agent.",
                "risk": "May produce repetitive ticker-naming boilerplate if over-applied.",
                "status": "recommendation_only",
            }
        )

    for agent, count in redundant_by_agent.most_common():
        if count < PROMPT_FIX_MIN_SUPPORT:
            continue
        fixes.append(
            {
                "target_agent": agent,
                "observed_problem": (
                    "The exact same unmatched statement recurs verbatim across multiple claims "
                    "(prompt_redundancy pattern in no_alpha_match)."
                ),
                "supporting_pattern_count": count,
                "suggested_change": (
                    "Review this agent's prompt template for boilerplate phrasing that repeats regardless "
                    "of the underlying analysis, and deduplicate or condition it on genuinely new content."
                ),
                "expected_effect": "Reduce repeated, avoidable no_alpha_match output from this agent.",
                "risk": "None expected beyond normal prompt-iteration risk; recommendation only, not applied.",
                "status": "recommendation_only",
            }
        )

    return sorted(fixes, key=lambda f: (-f["supporting_pattern_count"], f["target_agent"]))


def build_neutral_unclassified_audit(
    unclassified_findings_payload: Mapping[str, Any], *, top_n: int = DEFAULT_TOP_N
) -> dict[str, Any]:
    """Builds the neutral/unclassified audit for one already-computed
    ``unclassified_findings.json`` payload. Deterministic and offline:
    zero Provider/LLM calls, zero re-derivation of any B1-B5 signal."""
    findings = unclassified_findings_payload.get("findings")
    findings = [f for f in findings if isinstance(f, Mapping)] if isinstance(findings, list) else []
    audited_count = len(findings)

    by_reason = _by_reason(findings, audited_count)
    by_agent_and_reason = _by_agent_and_reason(findings)
    top_patterns = _top_n_patterns(findings, top_n=top_n)

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": unclassified_findings_payload.get("run_id"),
        "ticker": unclassified_findings_payload.get("ticker"),
        "source_artifact_total_count": unclassified_findings_payload.get("total_count"),
        "audited_count": audited_count,
        "audited_count_matches_source_artifact": audited_count == unclassified_findings_payload.get("total_count"),
        "unclassified_by_agent": _by_agent(findings, audited_count),
        "unclassified_by_reason": by_reason,
        "unclassified_by_agent_and_reason": by_agent_and_reason,
        "pattern_summary": _pattern_summary(findings),
        "top_20_repeated_patterns": top_patterns,
        "ticker_specificity_audit": _ticker_specificity_audit(findings, audited_count),
        "duplicate_audit": _duplicate_audit(findings, audited_count),
        "possible_taxonomy_gaps": _possible_taxonomy_gaps(findings),
        "healthy_vs_avoidable": _healthy_vs_avoidable_split(findings, top_patterns),
        "suggested_prompt_fixes": _suggested_prompt_fixes(by_agent_and_reason, top_patterns),
        "canonical_reason_priority": list(REASON_PRIORITY),
        "provider_calls": 0,
        "tradingagents_calls": 0,
    }


__all__ = [
    "SCHEMA_VERSION",
    "DEFAULT_TOP_N",
    "UNKNOWN_AGENT",
    "MISSING_REASON",
    "CLASSIFICATION_EXPECTED_UNCERTAINTY",
    "CLASSIFICATION_PROMPT_REDUNDANCY",
    "CLASSIFICATION_GENERIC_BACKGROUND",
    "CLASSIFICATION_DUPLICATE_OUTPUT",
    "CLASSIFICATION_TICKER_SPECIFICITY_FAILURE",
    "CLASSIFICATION_ALPHA_TAXONOMY_GAP",
    "CLASSIFICATION_LOW_CONFIDENCE_MAPPING",
    "CLASSIFICATION_OTHER",
    "CLASSIFICATION_UNCLEAR",
    "build_neutral_unclassified_audit",
]
