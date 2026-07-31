"""Deterministic factor-to-factor relation grammar for the Structure Extractor.

Pure-function helper: no I/O, no LLM/network/database calls, no dependency on
Graph Builder, Alpha Mapper, or Activation. `structure_extractor.py` is the only
caller.

Design summary
--------------
A legal edge requires, within one claim's evidence text:

1. a controlled relation-verb/phrase match (never a bare preposition, never an
   arbitrary "A verb B" -> causal assumption);
2. a resolvable source factor and a resolvable target factor, found by
   searching outward from the relation span within *the same clause* (or, for
   the explicitly cross-clause rule families below, the adjacent clause);
3. source != target;
4. no ambiguous same-span multi-factor collision at either endpoint (see
   `_LOCATIVE`-style handling in the AI Alpha Discriminator for the analogous
   idea applied there -- this module implements the Structure Graph's own
   version of it).

Rule families, in the priority order actually applied (higher first):

1. REVERSE_PASSIVE       -- "A is driven by B"            => B -> A
2. FORWARD_MULTIWORD     -- "A leads to B"                 => A -> B
3. REVERSE_MULTIWORD     -- "A results from B"              => B -> A
4. PREFIX_CAUSE          -- "Because of B, A ..."            => B -> A
5. WITH_EMBEDDED_RELATION-- "With B driving A ..."           => B -> A (i.e. source B, target A)
6. FORWARD_TRANSITIVE    -- "A drives B"                     => A -> B
7. CONDITIONAL           -- "If A, B could accelerate"        => A -> B, assertion_status=conditional
8. CONFLICTING           -- existing contrast-word x risk/growth pairing (unchanged)

Text with a literal "?" anywhere is treated as interrogative and abstains
entirely (the schema has no assertion_status for questions).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from comqutor_alpha.structure_engine.claim_semantics import analyze_claim_semantics
from comqutor_alpha.structure_engine.factor_normalizer import FACTOR_ALIASES, normalize_text

# Bump whenever a rule family, guard, or pattern in this module changes in a
# way that could alter which claims produce a relation candidate -- consumed
# by the architecture-replay lineage metadata (comqutor_alpha/replay/pipeline.py).
RELATION_GRAMMAR_VERSION = "structure_graph.relation_grammar.v1"

# ---------------------------------------------------------------------------
# Direction-plausibility guard (moved here from structure_extractor.py; same
# values, same behavior -- re-exported there for backward compatibility).
# ---------------------------------------------------------------------------

# Broad causal ordering avoids a brittle list of exact pairs while still
# refusing economically reversed edges such as GPU Demand -> AI Demand.
CAUSAL_RANK = {
    "AI Demand": 1,
    "AI CapEx": 1,
    "Inference Demand": 1,
    "Rate Cut Cycle": 1,
    "Liquidity Expansion": 1,
    "Semiconductor Cycle": 1,
    "Datacenter CapEx": 2,
    "AI Infrastructure": 2,
    "GPU Demand": 2,
    "Narrative Momentum": 2,
    "Revenue Growth": 3,
    "Valuation Risk": 3,
    "Recession Risk": 3,
}
GROWTH_FACTORS = {
    "AI Demand",
    "AI CapEx",
    "GPU Demand",
    "Revenue Growth",
    "Liquidity Expansion",
    "Narrative Momentum",
    "Semiconductor Cycle",
    "Inference Demand",
}
RISK_FACTORS = {"Valuation Risk", "Recession Risk"}


# Narrow, evidence-backed exceptions to the general rank rule below: pairs
# where a buildout/infrastructure-stage factor (rank 2) legitimately drives
# *derived component demand* for an upstream input factor (rank 1) -- e.g.
# AI infrastructure construction creating memory/storage chip demand. This
# is a pairwise allowlist, not a general numeric-tolerance widening, so it
# can never also admit an unrelated same-tier-gap reversal such as GPU
# Demand -> AI Demand (still rejected by the general rule below, and still
# covered by test_reversed_causal_phrasing_does_not_emit_wrong_direction_edge).
# Forcing evidence: tests/test_structure_correctness_sprint.py's
# pre-existing (not authored by this Sprint) SNDK-shaped fixture "AI
# infrastructure demand driving memory and storage demand from the AI data
# center buildout..." requires AI Infrastructure -> Semiconductor Cycle to
# be admitted; this Sprint's corrected nearest-clause-neighbor endpoint
# resolution (replacing the prior unbounded all-pairs bridge scan) resolves
# that claim's genuine grammatical target as Semiconductor Cycle ("...memory
# and storage demand...", not the more distant "AI data center buildout"),
# which the un-widened rank rule would otherwise incorrectly reject.
_RANK_EXCEPTION_PAIRS = frozenset(
    {
        ("AI Infrastructure", "Semiconductor Cycle"),
        ("Datacenter CapEx", "Semiconductor Cycle"),
    }
)


def plausible_causal_direction(source: str, target: str) -> bool:
    """Refuse economically reversed causal edges (e.g. GPU Demand -> AI
    Demand). Equal-rank pairs (e.g. Inference Demand -> AI CapEx feedback,
    AI Infrastructure -> Datacenter CapEx) are admissible when the claim
    itself asserts the relation explicitly -- only a strictly descending
    rank is treated as reversed, except for the narrow, explicitly listed
    `_RANK_EXCEPTION_PAIRS` above.

    Audited (Structure Graph Deterministic Relation Grammar Sprint) against
    every mandatory acceptance/negative sentence and every new pattern
    family in this module. One *additional*, non-hypothetical case (a
    risk factor such as Recession Risk causally pressuring a rank-1 demand
    factor, e.g. "AI CapEx faces pressure from Recession Risk") was also
    found to be incorrectly rejected, but is deliberately NOT added to the
    exception set here: unlike the pair above, it is not required by any
    existing or mandated test in this Sprint, and a risk-factor-as-source
    exception is a materially bigger, less-constrained change (RISK_FACTORS
    could plausibly pressure many rank-1/2 factors, not just one named
    pair) that deserves its own dedicated review rather than being folded in
    under time pressure here -- see the Sprint report's CAUSAL_RANK section.
    """
    if (source, target) in _RANK_EXCEPTION_PAIRS:
        return True
    source_rank = CAUSAL_RANK.get(source)
    target_rank = CAUSAL_RANK.get(target)
    return source_rank is not None and target_rank is not None and source_rank <= target_rank


# ---------------------------------------------------------------------------
# Light normalization: unlike factor_normalizer.normalize_text (which strips
# ALL punctuation), this preserves clause-boundary punctuation and "?" so the
# grammar can reason about clause structure and interrogatives.
# ---------------------------------------------------------------------------

_DASH_CHARS = "‐‑‒–—―-"
_DASH_PATTERN = re.compile(f"[{re.escape(_DASH_CHARS)}]")
_STRIP_OTHER_PUNCT_PATTERN = re.compile(r"[^a-z0-9%$,.;:?!\s]")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def _light_normalize(text: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    normalized = normalized.lower()
    normalized = _DASH_PATTERN.sub(" ", normalized)
    normalized = _STRIP_OTHER_PUNCT_PATTERN.sub(" ", normalized)
    normalized = _WHITESPACE_PATTERN.sub(" ", normalized)
    return normalized.strip()


_CLAUSE_BOUNDARY_PATTERN = re.compile(
    r"[,.;:]+|\bbut\b|\bhowever\b|\balthough\b|\bwhile\b|\bwhereas\b|\byet\b"
)


@dataclass(frozen=True)
class _Clause:
    text: str
    start: int
    end: int


def _split_clauses(light_text: str) -> list[_Clause]:
    clauses: list[_Clause] = []
    last = 0
    for match in _CLAUSE_BOUNDARY_PATTERN.finditer(light_text):
        if match.start() > last:
            segment = light_text[last : match.start()]
            if segment.strip():
                clauses.append(_Clause(segment, last, match.start()))
        last = match.end()
    if last < len(light_text):
        segment = light_text[last:]
        if segment.strip():
            clauses.append(_Clause(segment, last, len(light_text)))
    return clauses


# ---------------------------------------------------------------------------
# Factor mention finding (clause-local, all occurrences -- not just the
# earliest, unlike factor_normalizer.factor_mention_span) plus same-span
# overlapping-alias ambiguity detection.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Mention:
    factor: str
    start: int
    end: int


def _factor_spans(factor: str, text: str) -> list[tuple[int, int]]:
    aliases = (factor, *FACTOR_ALIASES.get(factor, ()))
    spans = []
    for alias in aliases:
        alias_norm = normalize_text(alias)
        if not alias_norm:
            continue
        pattern = re.compile(rf"(?<![a-z0-9]){re.escape(alias_norm)}(?![a-z0-9])")
        for match in pattern.finditer(text):
            spans.append((match.start(), match.end()))
    return spans


def _find_mentions(clause_text: str, factors: list[str]) -> list[_Mention]:
    mentions = [
        _Mention(factor, start, end)
        for factor in factors
        for start, end in _factor_spans(factor, clause_text)
    ]
    mentions.sort(key=lambda mention: mention.start)
    return mentions


def _ambiguous_factors(mentions: list[_Mention]) -> set[str]:
    """Factors whose mention span overlaps a *different* factor's mention
    span in this clause -- e.g. "AI CapEx" / "Datacenter CapEx" / "AI
    Infrastructure" all matching the one "ai infrastructure spending" phrase.
    Such factors must never be silently picked as a clean endpoint; the
    candidate must abstain (AMBIGUOUS_OVERLAPPING_FACTOR_ENDPOINT) instead.
    """
    ambiguous: set[str] = set()
    for i, left in enumerate(mentions):
        for right in mentions[i + 1 :]:
            if right.start >= left.end:
                break
            if left.factor != right.factor:
                ambiguous.add(left.factor)
                ambiguous.add(right.factor)
    return ambiguous


def _nearest_left(mentions: list[_Mention], position: int, ambiguous: set[str]) -> _Mention | None:
    candidates = [m for m in mentions if m.end <= position and m.factor not in ambiguous]
    if not candidates:
        return None
    return max(candidates, key=lambda m: m.end)


def _nearest_right(mentions: list[_Mention], position: int, ambiguous: set[str]) -> _Mention | None:
    candidates = [m for m in mentions if m.start >= position and m.factor not in ambiguous]
    if not candidates:
        return None
    return min(candidates, key=lambda m: m.start)


# ---------------------------------------------------------------------------
# Relation candidate (grammar's output type -- structure_extractor.py adapts
# this into its own `_edge()` dict, which owns provenance/ticker/claim_id).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RelationCandidate:
    source: str
    target: str
    edge_type: str  # "causal" | "supportive"
    rule_name: str
    bridge: str  # local span used for negation detection ("bridge" text)
    passive: bool = False


def _resolve_forward(
    mentions: list[_Mention], ambiguous: set[str], match_start: int, match_end: int
) -> tuple[str, str] | None:
    left = _nearest_left(mentions, match_start, ambiguous)
    right = _nearest_right(mentions, match_end, ambiguous)
    if left is None or right is None or left.factor == right.factor:
        return None
    return left.factor, right.factor  # source, target


def _resolve_reverse(
    mentions: list[_Mention], ambiguous: set[str], match_start: int, match_end: int
) -> tuple[str, str] | None:
    left = _nearest_left(mentions, match_start, ambiguous)
    right = _nearest_right(mentions, match_end, ambiguous)
    if left is None or right is None or left.factor == right.factor:
        return None
    return right.factor, left.factor  # source, target (direction flipped)


# ---------------------------------------------------------------------------
# 1. REVERSE_PASSIVE -- "A is driven by B" => B -> A
# ---------------------------------------------------------------------------

_ADVERBS = ("primarily", "mainly", "largely", "partly", "directly", "significantly")
_ADVERB_GROUP = rf"(?:(?:{'|'.join(_ADVERBS)})\s+)?"

# Verbs safe to allow WITHOUT a preceding auxiliary ("..., driven by AI
# demand") -- restricted to verbs that are not naturally used with a raw
# numeric magnitude ("increased by 20%" must never match; "caused by 20%" is
# not a realistic false-positive risk).
_PASSIVE_NO_AUX_VERBS = ("driven", "supported", "reinforced", "fueled", "caused", "enabled", "constrained", "pressured")
# Verbs requiring an explicit auxiliary, because their bare "X VERB by Y"
# participial form collides with numeric-magnitude phrasing ("Revenue Growth
# increased by 20%").
_PASSIVE_AUX_ONLY_VERBS = ("raised", "boosted", "increased", "weighed down")
_PASSIVE_AUX = r"(?:is|are|was|were|be|been|being)"

REVERSE_PASSIVE_PATTERN = re.compile(
    rf"\b{_PASSIVE_AUX}\s+{_ADVERB_GROUP}(?:{'|'.join(_PASSIVE_NO_AUX_VERBS + _PASSIVE_AUX_ONLY_VERBS)})\s+by\b"
    rf"|\b(?:{'|'.join(_PASSIVE_NO_AUX_VERBS)})\s+{_ADVERB_GROUP}by\b"
)


def _match_reverse_passive(clause_text: str, factors: list[str]) -> list[RelationCandidate]:
    mentions = _find_mentions(clause_text, factors)
    if len(mentions) < 2:
        return []
    ambiguous = _ambiguous_factors(mentions)
    candidates = []
    for match in REVERSE_PASSIVE_PATTERN.finditer(clause_text):
        resolved = _resolve_reverse(mentions, ambiguous, match.start(), match.end())
        if resolved is None:
            continue
        source, target = resolved
        edge_type = "supportive" if "supported" in match.group(0) or "reinforced" in match.group(0) else "causal"
        candidates.append(
            RelationCandidate(source, target, edge_type, "reverse_passive_relation", clause_text, passive=True)
        )
    return candidates


# No-auxiliary-only variant, anchored to the start of a clause: this is the
# form used by a comma-offset reduced relative clause ("Storage demand
# strength, driven by hyperscaler AI capex, is broad.") where the target
# ("storage demand strength") is the *preceding* clause's own subject, not
# anything within this participial clause itself. The full-auxiliary form
# ("X is driven by Y") is ordinarily a clause's own main verb, not a
# comma-offset modifier, so it is deliberately not given this same
# cross-clause reach -- only the no-aux participial list qualifies.
_PASSIVE_NO_AUX_ONLY_PATTERN = re.compile(rf"^(?:{'|'.join(_PASSIVE_NO_AUX_VERBS)})\s+{_ADVERB_GROUP}by\b")


def _match_comma_offset_participial(
    clauses: list[_Clause], factors: list[str]
) -> tuple[list[RelationCandidate], set[int]]:
    candidates: list[RelationCandidate] = []
    consumed: set[int] = set()
    for index, clause in enumerate(clauses):
        if index == 0:
            continue
        match = _PASSIVE_NO_AUX_ONLY_PATTERN.match(clause.text.strip())
        if match is None:
            continue
        this_mentions = _find_mentions(clause.text, factors)
        this_ambiguous = _ambiguous_factors(this_mentions)
        if _nearest_left(this_mentions, match.start(), this_ambiguous) is not None:
            continue  # a local target already exists; the regular per-clause pass handles it
        source_mention = _nearest_right(this_mentions, match.end(), this_ambiguous)
        if source_mention is None:
            continue
        prev_mentions = _find_mentions(clauses[index - 1].text, factors)
        prev_ambiguous = _ambiguous_factors(prev_mentions)
        non_ambiguous_prev = [m for m in prev_mentions if m.factor not in prev_ambiguous]
        if not non_ambiguous_prev:
            continue
        target = non_ambiguous_prev[-1].factor
        if target == source_mention.factor:
            continue
        edge_type = "supportive" if "supported" in match.group(0) or "reinforced" in match.group(0) else "causal"
        candidates.append(
            RelationCandidate(
                source_mention.factor,
                target,
                edge_type,
                "reverse_passive_relation",
                clauses[index - 1].text + " " + clause.text,
                passive=True,
            )
        )
        consumed.add(index - 1)
        consumed.add(index)
    return candidates, consumed


# ---------------------------------------------------------------------------
# 2. FORWARD_MULTIWORD -- "A leads to B" / "A translates into B" => A -> B
# ---------------------------------------------------------------------------

FORWARD_MULTIWORD_PATTERN = re.compile(
    r"\blead(?:s|ing)?\s+to\b"
    r"|\bresult(?:s|ing)?\s+in\b"
    r"|\btranslat(?:e|es|ing)\s+into\b"
    r"|\bcontribut(?:e|es|ing)\s+to\b"
    r"|\bgiv(?:e|es|ing)\s+rise\s+to\b"
    r"|\bfeed(?:s|ing)?(?:\s+back)?\s+into\b"
    r"|\badd(?:s|ing)?\s+to\b"
    r"|\bcreat(?:e|es|ing)\s+demand\s+for\b"
    r"|\bappl(?:y|ies|ying)\s+pressure\s+(?:to|on)\b"
    r"|\bput(?:s|ting)?\s+pressure\s+on\b"
    r"|\bplac(?:e|es|ing)\s+pressure\s+on\b"
    r"|\bweigh(?:s|ing)?\s+on\b"
)


def _match_forward_multiword(clause_text: str, factors: list[str]) -> list[RelationCandidate]:
    mentions = _find_mentions(clause_text, factors)
    if len(mentions) < 2:
        return []
    ambiguous = _ambiguous_factors(mentions)
    candidates = []
    for match in FORWARD_MULTIWORD_PATTERN.finditer(clause_text):
        resolved = _resolve_forward(mentions, ambiguous, match.start(), match.end())
        if resolved is None:
            continue
        source, target = resolved
        candidates.append(RelationCandidate(source, target, "causal", "forward_multiword_relation", clause_text))
    return candidates


# ---------------------------------------------------------------------------
# 3. REVERSE_MULTIWORD -- "A results from B" / "A benefits from B" => B -> A
# ---------------------------------------------------------------------------

REVERSE_MULTIWORD_PATTERN = re.compile(
    r"\bresult(?:s|ing)?\s+from\b"
    r"|\bstem(?:s|ming)?\s+from\b"
    r"|\baris(?:e|es|ing)\s+from\b"
    r"|\b(?:is|are|was|were)\s+due\s+to\b"
    r"|\b(?:is|are|was|were)\s+because\s+of\b"
    r"|\b(?:is|are|was|were)\s+owing\s+to\b"
    r"|\bdepend(?:s|ing)?\s+on\b"
    r"|\brel(?:y|ies|ying)\s+on\b"
    r"|\bbenefit(?:s|ing)?\s+from\b"
    r"|\bfac(?:e|es|ing)\s+pressure\s+from\b"
    r"|\b(?:is|are|was|were)\s+vulnerable\s+to\b"
    r"|\b(?:is|are|was|were)\s+exposed\s+to\b"
)


def _match_reverse_multiword(clause_text: str, factors: list[str]) -> list[RelationCandidate]:
    mentions = _find_mentions(clause_text, factors)
    if len(mentions) < 2:
        return []
    ambiguous = _ambiguous_factors(mentions)
    candidates = []
    for match in REVERSE_MULTIWORD_PATTERN.finditer(clause_text):
        resolved = _resolve_reverse(mentions, ambiguous, match.start(), match.end())
        if resolved is None:
            continue
        source, target = resolved
        candidates.append(RelationCandidate(source, target, "causal", "reverse_multiword_relation", clause_text))
    return candidates


# ---------------------------------------------------------------------------
# 6. FORWARD_TRANSITIVE -- "A drives B" / "A supports B" => A -> B
# ---------------------------------------------------------------------------

FORWARD_CAUSAL_VERBS = (
    "cause", "causes", "causing",
    "drive", "drives", "driving",
    "boost", "boosts", "boosting",
    "fuel", "fuels", "fueling",
    "raise", "raises", "raising",
    "increase", "increases", "increasing",
    "reduce", "reduces", "reducing",
    "lower", "lowers", "lowering",
    "pressure", "pressures", "pressuring",
    "constrain", "constrains", "constraining",
    "limit", "limits", "limiting",
    "trigger", "triggers", "triggering",
    "create", "creates", "creating",
    "generate", "generates", "generating",
    "produce", "produces", "producing",
    "accelerate", "accelerates", "accelerating",
    "slow", "slows", "slowing",
    "compress", "compresses", "compressing",
    "undermine", "undermines", "undermining",
    "push", "pushes", "pushing",
    "expand", "expands", "expanding",
)
FORWARD_SUPPORTIVE_VERBS = (
    "support", "supports", "supporting",
    "reinforce", "reinforces", "reinforcing",
    "confirm", "confirms", "confirming",
    "enable", "enables", "enabling",
    "help", "helps", "helping",
    "strengthen", "strengthens", "strengthening",
    # "A benefits B" (transitive) is FORWARD; "A benefits from B" is caught
    # first by REVERSE_MULTIWORD (higher priority), so this bare form only
    # ever fires when there is no trailing "from".
    "benefit", "benefits", "benefiting",
)
FORWARD_TRANSITIVE_CAUSAL_PATTERN = re.compile(rf"\b(?:{'|'.join(FORWARD_CAUSAL_VERBS)})\b")
FORWARD_TRANSITIVE_SUPPORTIVE_PATTERN = re.compile(rf"\b(?:{'|'.join(FORWARD_SUPPORTIVE_VERBS)})\b(?!\s+from\b)")

# Shared "clear change" vocabulary for CONDITIONAL/PREFIX_CAUSE result-clause
# validation -- deliberately the same verb list as FORWARD_TRANSITIVE's
# causal family (a single source of truth) rather than a second regex.
CHANGE_VERB_PATTERN = FORWARD_TRANSITIVE_CAUSAL_PATTERN


def _match_forward_transitive(clause_text: str, factors: list[str]) -> list[RelationCandidate]:
    mentions = _find_mentions(clause_text, factors)
    if len(mentions) < 2:
        return []
    ambiguous = _ambiguous_factors(mentions)
    candidates = []
    for pattern, edge_type in (
        (FORWARD_TRANSITIVE_CAUSAL_PATTERN, "causal"),
        (FORWARD_TRANSITIVE_SUPPORTIVE_PATTERN, "supportive"),
    ):
        for match in pattern.finditer(clause_text):
            resolved = _resolve_forward(mentions, ambiguous, match.start(), match.end())
            if resolved is None:
                continue
            source, target = resolved
            # Risk-factor/supportive exclusion is applied centrally in
            # structure_extractor.py's caller, uniformly across every rule
            # family (not just this one) -- see `_reject_risk_factor_support`.
            candidates.append(
                RelationCandidate(source, target, edge_type, f"forward_transitive_{edge_type}", clause_text)
            )
    return candidates


# ---------------------------------------------------------------------------
# 4. PREFIX_CAUSE -- "Because of B, A ..." => B -> A
# ---------------------------------------------------------------------------

_PREFIX_CAUSE_MARKER = re.compile(
    r"^(?:because\s+of|due\s+to|owing\s+to|as\s+a\s+result\s+of|on\s+the\s+back\s+of)\b"
)


def _match_prefix_cause(clauses: list[_Clause], factors: list[str]) -> tuple[list[RelationCandidate], set[int]]:
    if not clauses:
        return [], set()
    marker_match = _PREFIX_CAUSE_MARKER.match(clauses[0].text.strip())
    if marker_match is None or len(clauses) < 2:
        return [], set()

    marker_clause = clauses[0].text
    result_clause = clauses[1].text
    marker_mentions = _find_mentions(marker_clause, factors)
    marker_ambiguous = _ambiguous_factors(marker_mentions)
    non_ambiguous_marker = [m for m in marker_mentions if m.factor not in marker_ambiguous]
    if not non_ambiguous_marker:
        return [], set()
    source = non_ambiguous_marker[0].factor

    result_mentions = _find_mentions(result_clause, factors)
    result_ambiguous = _ambiguous_factors(result_mentions)
    non_ambiguous_result = [m for m in result_mentions if m.factor not in result_ambiguous]
    if not non_ambiguous_result:
        return [], set()
    if not CHANGE_VERB_PATTERN.search(result_clause):
        return [], set()
    target = non_ambiguous_result[0].factor

    if source == target:
        return [], set()
    return [
        RelationCandidate(source, target, "causal", "prefix_cause_relation", marker_clause + " " + result_clause)
    ], {0, 1}


# ---------------------------------------------------------------------------
# 5. WITH_EMBEDDED_RELATION
#    (a) "With B driving A ..."      => B -> A (source B, target A)
#    (b) "A, with support from B ..."=> B -> A (source B, target A)
# ---------------------------------------------------------------------------

_WITH_PREFIX = re.compile(r"^with\s+")
_WITH_SUPPORT_FROM = re.compile(r"\bwith\s+(?:support|help)\s+from\b")


def _match_with_embedded(clauses: list[_Clause], factors: list[str]) -> tuple[list[RelationCandidate], set[int]]:
    candidates: list[RelationCandidate] = []
    consumed: set[int] = set()

    for index, clause in enumerate(clauses):
        stripped_match = _WITH_PREFIX.match(clause.text)
        if stripped_match is not None:
            remainder = clause.text[stripped_match.end() :]
            found = _match_forward_transitive(remainder, factors)
            if found:
                candidates.extend(found)
                consumed.add(index)
                continue

        support_match = _WITH_SUPPORT_FROM.search(clause.text)
        if support_match is not None and index > 0:
            this_mentions = _find_mentions(clause.text, factors)
            this_ambiguous = _ambiguous_factors(this_mentions)
            source_mention = _nearest_right(this_mentions, support_match.end(), this_ambiguous)
            prev_mentions = _find_mentions(clauses[index - 1].text, factors)
            prev_ambiguous = _ambiguous_factors(prev_mentions)
            non_ambiguous_prev = [m for m in prev_mentions if m.factor not in prev_ambiguous]
            if source_mention is not None and non_ambiguous_prev:
                target = non_ambiguous_prev[-1].factor
                if target != source_mention.factor:
                    candidates.append(
                        RelationCandidate(
                            source_mention.factor,
                            target,
                            "supportive",
                            "with_support_from_relation",
                            clauses[index - 1].text + " " + clause.text,
                        )
                    )
                    consumed.add(index - 1)
                    consumed.add(index)

    return candidates, consumed


# ---------------------------------------------------------------------------
# 7. CONDITIONAL -- "If A, B could accelerate" => A -> B, conditional
# ---------------------------------------------------------------------------

_CONDITIONAL_MARKER = re.compile(r"^(?:if|unless|provided\s+that|assuming(?:\s+that)?)\b")
CONDITIONAL_MODAL_PATTERN = re.compile(r"\b(could|may|might|would)\b")


def _match_conditional(clauses: list[_Clause], factors: list[str]) -> tuple[list[RelationCandidate], set[int]]:
    if not clauses:
        return [], set()
    marker_match = _CONDITIONAL_MARKER.match(clauses[0].text.strip())
    if marker_match is None or len(clauses) < 2:
        return [], set()

    if_clause = clauses[0].text
    result_clause = clauses[1].text

    if_mentions = _find_mentions(if_clause, factors)
    if_ambiguous = _ambiguous_factors(if_mentions)
    non_ambiguous_if = [m for m in if_mentions if m.factor not in if_ambiguous]
    if not non_ambiguous_if:
        return [], set()
    source = non_ambiguous_if[0].factor

    result_mentions = _find_mentions(result_clause, factors)
    result_ambiguous = _ambiguous_factors(result_mentions)
    non_ambiguous_result = [m for m in result_mentions if m.factor not in result_ambiguous]
    if not non_ambiguous_result:
        return [], set()
    if not CONDITIONAL_MODAL_PATTERN.search(result_clause):
        return [], set()
    if not CHANGE_VERB_PATTERN.search(result_clause):
        return [], set()
    target = non_ambiguous_result[0].factor

    if source == target:
        return [], set()
    return [
        RelationCandidate(source, target, "causal", "conditional_relation", if_clause + " " + result_clause)
    ], {0, 1}


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

_INTERROGATIVE_MARK = "?"


def extract_relation_candidates(evidence_text: str, factors: list[str]) -> list[RelationCandidate]:
    """Return every admissible (non-conflicting) relation candidate in
    `evidence_text` given the claim's already-extracted `factors`.

    Conflicting (contrast-word x risk/growth) candidates are handled
    separately by `match_conflicting`, matching the existing sentence-wide
    (not clause-scoped) design this Sprint explicitly preserves.
    """
    if len(factors) < 2 or not evidence_text:
        return []
    if _INTERROGATIVE_MARK in evidence_text:
        return []

    light = _light_normalize(evidence_text)
    if not light:
        return []
    clauses = _split_clauses(light)
    if not clauses:
        return []

    consumed: set[int] = set()
    candidates: list[RelationCandidate] = []

    participial_candidates, participial_consumed = _match_comma_offset_participial(clauses, factors)
    candidates.extend(participial_candidates)
    consumed |= participial_consumed

    prefix_candidates, prefix_consumed = _match_prefix_cause(clauses, factors)
    candidates.extend(prefix_candidates)
    consumed |= prefix_consumed

    with_candidates, with_consumed = _match_with_embedded(clauses, factors)
    candidates.extend(with_candidates)
    consumed |= with_consumed

    cond_candidates, cond_consumed = _match_conditional(clauses, factors)
    candidates.extend(cond_candidates)
    consumed |= cond_consumed

    for index, clause in enumerate(clauses):
        if index in consumed:
            continue
        for family in (
            _match_reverse_passive,
            _match_forward_multiword,
            _match_reverse_multiword,
            _match_forward_transitive,
        ):
            found = family(clause.text, factors)
            if found:
                candidates.extend(found)
                break

    return [c for c in candidates if _passes_direction_guards(c)]


def _passes_direction_guards(candidate: RelationCandidate) -> bool:
    """Two guards applied uniformly to every rule family's output, so
    `extract_relation_candidates` is always a fully-filtered, correct answer
    for any caller (not just structure_extractor.py's own wrapper):

    1. self-loop (source == target) is already excluded by every endpoint
       resolver, but re-checked here as a final invariant;
    2. a causal edge must satisfy `plausible_causal_direction`;
    3. a supportive edge must not touch a RISK_FACTORS member (a risk
       factor's presence in a "supportive" relation almost always means the
       claim is really asserting "low/falling risk supports X", not "the
       risk itself supports X" -- a polarity inversion this deterministic
       grammar does not parse).
    """
    if candidate.source == candidate.target:
        return False
    if candidate.edge_type == "causal" and not plausible_causal_direction(
        candidate.source, candidate.target
    ):
        return False
    return not (
        candidate.edge_type == "supportive"
        and (candidate.source in RISK_FACTORS or candidate.target in RISK_FACTORS)
    )


# ---------------------------------------------------------------------------
# 8. CONFLICTING -- unchanged sentence-wide contrast x risk/growth pairing.
# ---------------------------------------------------------------------------

CONFLICT_WORDS = (
    "but",
    "however",
    "despite",
    "although",
    "while",
    "yet",
    "offset",
    "conflict",
    "downside risk",
)


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    from comqutor_alpha.structure_engine.factor_normalizer import term_in_text

    return any(term_in_text(term, text) for term in terms)


def match_conflicting(text: str, factors: list[str]) -> list[tuple[str, str]]:
    """Return (risk_factor, growth_factor) pairs when a contrast word
    appears alongside at least one risk factor and one growth/demand factor
    in the same claim. Unchanged from the pre-Sprint behavior: this is a
    whole-claim signal, not a clause-scoped one -- the conflicting edge's
    direction is a serialization convention only, never a causal claim.
    """
    if not _has_any(text, CONFLICT_WORDS):
        return []
    pairs = []
    for risk_factor in [f for f in factors if f in RISK_FACTORS]:
        for growth_factor in [f for f in factors if f in GROWTH_FACTORS]:
            pairs.append((risk_factor, growth_factor))
    return pairs


# ---------------------------------------------------------------------------
# Assertion-status / confidence derivation (moved here, same logic as the
# pre-Sprint structure_extractor.py implementation).
# ---------------------------------------------------------------------------

NEGATED_RELATION_PATTERN = re.compile(
    r"\b(no|not|never|does not|do not|did not|fails? to|failed to|without)\b"
)


def assertion_status_for(evidence_text: str, bridge: str) -> str:
    semantics = analyze_claim_semantics(evidence_text)
    if NEGATED_RELATION_PATTERN.search(bridge) or semantics.negated:
        return "negated"
    if semantics.conditional:
        return "conditional"
    return "asserted"


def relation_confidence(edge_type: str, assertion_status: str) -> float:
    if assertion_status == "negated":
        return 0.35
    if assertion_status == "conditional":
        return 0.58
    return 0.84 if edge_type == "causal" else 0.68


def relation_reason(edge_type: str, assertion_status: str, passive: bool = False) -> str:
    voice = "passive" if passive else "active"
    article = "an" if voice == "active" else "a"
    if assertion_status == "negated":
        return f"The claim explicitly negates {article} {voice} {edge_type} relation."
    if assertion_status == "conditional":
        return f"The claim states a conditional {voice} {edge_type} relation."
    return f"The claim states an asserted {voice} {edge_type} relation."
