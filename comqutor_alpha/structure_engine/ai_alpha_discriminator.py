"""AI Alpha Discrimination hard gates for A101 (AI Expansion), A102
(Inference Explosion), and A103 (AI Infrastructure).

The taxonomy's own broad keyword lists are good for *candidate recall*
(alpha_mapper.py's existing keyword/factor scoring), but generic terms like
"AI", "cloud", "capex", or "data center" alone are not specific enough to
justify a *formal* match -- and the taxonomy's factor-weight table
deliberately gives partial credit across A101/A102/A103 for shared factors
(e.g. "AI CapEx" contributes to both A101 and A103), which is appropriate
for candidate scoring but not for a hard admission decision.

This module is a deterministic, independent boolean gate layered *after*
the existing keyword/factor/direction/semantic scoring: each of A101/A102/
A103 must have (a) at least one alpha-specific anchor phrase and (b) at
least one expansion/contraction predicate, co-located in the same clause of
the claim text. It never reads taxonomy relations, never propagates a match
from one Alpha to another, and never changes the existing match-score
formula -- it only decides whether a candidate is *eligible* to be admitted
as a formal match at all.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

AI_ALPHA_IDS = frozenset({"A101", "A102", "A103"})

# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

_DASH_PATTERN = re.compile(r"[‐-―−]")
_NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9%$]+")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def _light_normalize(text) -> str:
    """Unicode NFKC, lowercase, hyphen normalization, whitespace collapse --
    punctuation (commas/periods/semicolons/colons) is deliberately kept at
    this stage so clause boundaries survive for segmentation."""
    value = unicodedata.normalize("NFKC", str(text or ""))
    value = value.lower()
    value = _DASH_PATTERN.sub("-", value)
    value = _WHITESPACE_PATTERN.sub(" ", value)
    return value.strip()


def _strip_to_alnum(text: str) -> str:
    value = _NON_ALNUM_PATTERN.sub(" ", text)
    return _WHITESPACE_PATTERN.sub(" ", value).strip()


def normalize_claim_for_gate(text) -> str:
    """Full deterministic normalization used for anchor/predicate matching:
    NFKC, lowercase, whitespace/hyphen normalized, and punctuation-stripped
    to token boundaries. Order-independent and input-order independent --
    calling this twice on the same text always returns the same string."""
    return _strip_to_alnum(_light_normalize(text))


def _normalize_phrase(phrase: str) -> str:
    return normalize_claim_for_gate(phrase)


# ---------------------------------------------------------------------------
# Clause segmentation
# ---------------------------------------------------------------------------

# Strong clause boundaries only. Deliberately excludes "and"/"or": those
# frequently join a compound subject or object that shares a single trailing
# predicate ("AI training and inference workloads increased", "AI capex
# funded new servers and cooling capacity") -- splitting on them would
# incorrectly strand an anchor away from the predicate it depends on.
_SEGMENT_BOUNDARY_PATTERN = re.compile(
    r"[,.;:]+|\bwhile\b|\bwhereas\b|\balthough\b|\bhowever\b|\bbut\b"
)


def _segments(light_text: str) -> list[str]:
    parts = _SEGMENT_BOUNDARY_PATTERN.split(light_text)
    return [_strip_to_alnum(part) for part in parts if part.strip()]


# ---------------------------------------------------------------------------
# Anchor / predicate matching
# ---------------------------------------------------------------------------


def _phrase_pattern(phrase: str) -> re.Pattern:
    """Token/phrase-boundary regex for one normalized anchor or predicate.
    A trailing optional "s"/"es" tolerates simple regular plurals (server ->
    servers, campus -> campuses) without ever matching an unrelated word
    that merely starts with the same letters (boundaries are enforced on
    both sides, so "rack" never matches "track" and "agent" never matches
    "agency")."""
    normalized = _normalize_phrase(phrase)
    escaped = re.escape(normalized)
    return re.compile(rf"(?<![a-z0-9]){escaped}(?:es|s)?(?![a-z0-9])")


_LOCATIVE_PREPOSITIONS = frozenset({"in", "at", "within", "inside", "across"})


def _find_anchor_hits(segment: str, phrases: tuple[str, ...], *, exclude_locative: bool) -> list[str]:
    """Returns the subset of `phrases` that appear in `segment`. When
    `exclude_locative` is set, an occurrence immediately preceded by a bare
    locative preposition ("in data centers", "at the facility") is treated
    as a location reference, not a buildout/demand subject, and does not
    count -- this is what keeps "Inference workloads in data centers
    increased" from admitting A103: the datacenter is merely where the
    workload runs, not what is described as changing."""
    hits: list[str] = []
    for phrase in phrases:
        pattern = _phrase_pattern(phrase)
        for match in pattern.finditer(segment):
            if exclude_locative:
                preceding = segment[: match.start()].rstrip()
                preceding_token = preceding.rsplit(" ", 1)[-1] if preceding else ""
                if preceding_token in _LOCATIVE_PREPOSITIONS:
                    continue
            hits.append(phrase)
            break
    return hits


def _find_predicate_hits(segment: str, predicates: frozenset[str]) -> list[str]:
    hits = []
    for word in predicates:
        if _phrase_pattern(word).search(segment):
            hits.append(word)
    return hits


# ---------------------------------------------------------------------------
# Shared change predicate vocabulary
# ---------------------------------------------------------------------------

POSITIVE_PREDICATES = frozenset(
    {
        "increase", "increased", "increasing",
        "rise", "rose", "rising",
        "grow", "grew", "growing",
        "expand", "expanded", "expanding",
        "accelerate", "accelerated", "accelerating",
        "surge", "surged", "surging",
        "double", "doubled",
        "raise", "raised",
        "add", "added",
        "build", "built",
        "construct", "constructed",
        "deploy", "deployed",
        "adopt", "adopted",
        "invest", "invested",
        "order", "ordered",
        "purchase", "purchased",
        "upgrade", "upgraded",
        # Practical extensions beyond the minimum list: nominal/participle
        # forms that appear in natural claim phrasing for capital deployment
        # ("AI capex funded new servers", "requiring deployment of more
        # servers") but are not covered by the verb conjugations above.
        "fund", "funded", "funding",
        "deployment", "deployments",
        "drive", "drives", "driving", "driven",
    }
)

NEGATIVE_PREDICATES = frozenset(
    {
        "decrease", "decreased",
        "decline", "declined",
        "fall", "fell", "falling",
        "slow", "slowed",
        "cut", "reduced",
        "delay", "delayed",
        "cancel", "cancelled",
        "weaken", "weakened",
        "contract", "contracted",
        "shortage",
        "bottleneck",
    }
)

ALL_PREDICATES = POSITIVE_PREDICATES | NEGATIVE_PREDICATES

# ---------------------------------------------------------------------------
# A101 anchor groups
# ---------------------------------------------------------------------------

_A101_ANCHOR_GROUPS: dict[str, tuple[str, ...]] = {
    "training": (
        "AI training", "model training", "training workload", "training workloads",
        "pretraining", "pre-training", "pre training",
        "fine-tuning", "fine tuning",
        "foundation model training", "large model training",
    ),
    "accelerator": (
        "GPU", "GPUs", "AI accelerator", "AI accelerators",
        "accelerator demand", "accelerator orders",
        "AI chip", "AI chips",
        "training accelerator", "training compute",
    ),
    "investment": (
        "AI capex", "AI capital expenditure", "AI capital spending",
        "AI investment", "AI investments",
        "cloud AI investment", "cloud AI capex",
        "AI compute capacity", "AI training capacity",
    ),
    "adoption": (
        "AI adoption",
    ),
}

# ---------------------------------------------------------------------------
# A102 anchors (one flat inference-specific group)
# ---------------------------------------------------------------------------

_A102_ANCHOR_GROUPS: dict[str, tuple[str, ...]] = {
    "inference": (
        "inference", "AI inference",
        "inference workload", "inference workloads",
        "inference demand", "inference request", "inference requests",
        "inference traffic", "inference capacity",
        "model serving", "model-serving",
        "serving workload", "serving workloads", "serving demand", "serving capacity",
        "token generation", "token volume", "tokens generated", "tokens processed",
        "AI agent", "AI agents", "agent workload", "agent workloads",
        "enterprise AI usage", "enterprise AI application", "enterprise AI applications",
        "production AI deployment", "production deployment of AI", "production model deployment",
    ),
}

# ---------------------------------------------------------------------------
# A103 anchor groups (physical infrastructure)
# ---------------------------------------------------------------------------

_A103_ANCHOR_GROUPS: dict[str, tuple[str, ...]] = {
    "datacenter_facilities": (
        "data center", "data centers", "datacenter", "datacenters",
        "data-center campus", "data center campus",
        "colocation", "colo capacity",
    ),
    "compute_hardware": (
        "server", "servers", "server rack", "server racks", "rack capacity",
        "compute cluster", "compute clusters",
    ),
    "networking": (
        "networking", "network switch", "network switches", "switch capacity",
        "optical interconnect", "optical networking", "interconnect", "network fabric",
    ),
    "power": (
        "power infrastructure", "power equipment", "power demand",
        "transformer", "transformers",
        "UPS", "uninterruptible power supply",
        "grid connection", "electrical infrastructure",
    ),
    "cooling": (
        "cooling", "liquid cooling", "HVAC", "thermal management",
        "cooling capacity", "cooling equipment",
    ),
}

_ANCHOR_GROUPS_BY_ALPHA: dict[str, dict[str, tuple[str, ...]]] = {
    "A101": _A101_ANCHOR_GROUPS,
    "A102": _A102_ANCHOR_GROUPS,
    "A103": _A103_ANCHOR_GROUPS,
}
# Only A103's physical-infrastructure anchors are excluded when they appear
# as a bare locative ("in data centers") rather than the subject of a
# buildout/demand/capacity statement.
_LOCATIVE_EXCLUDED_ALPHAS = frozenset({"A103"})


@dataclass(frozen=True)
class AiAlphaGateResult:
    alpha_id: str
    passed: bool
    matched_groups: frozenset[str] = field(default_factory=frozenset)
    matched_anchors: tuple[str, ...] = ()
    matched_predicates: tuple[str, ...] = ()


def _evaluate_single_gate(segments: list[str], alpha_id: str) -> AiAlphaGateResult:
    groups = _ANCHOR_GROUPS_BY_ALPHA[alpha_id]
    exclude_locative = alpha_id in _LOCATIVE_EXCLUDED_ALPHAS

    matched_groups: set[str] = set()
    matched_anchors: list[str] = []
    matched_predicates: list[str] = []

    for segment in segments:
        predicate_hits = _find_predicate_hits(segment, ALL_PREDICATES)
        if not predicate_hits:
            continue
        for group_name, phrases in groups.items():
            anchor_hits = _find_anchor_hits(segment, phrases, exclude_locative=exclude_locative)
            if anchor_hits:
                matched_groups.add(group_name)
                matched_anchors.extend(anchor_hits)
                matched_predicates.extend(predicate_hits)

    return AiAlphaGateResult(
        alpha_id=alpha_id,
        passed=bool(matched_groups),
        matched_groups=frozenset(matched_groups),
        matched_anchors=tuple(dict.fromkeys(matched_anchors)),
        matched_predicates=tuple(dict.fromkeys(matched_predicates)),
    )


def evaluate_ai_alpha_gates(text) -> dict[str, AiAlphaGateResult]:
    """Independently evaluates the A101/A102/A103 hard gates over one claim
    (claim + evidence, already concatenated by the caller).

    Each gate requires an alpha-specific anchor and a change predicate to
    co-occur in the same clause/segment of the text (segments are split on
    strong delimiters only -- commas, periods, semicolons, colons, and the
    subordinating/contrastive conjunctions while/whereas/although/however/
    but; "and"/"or" are never split on, so a shared trailing predicate over
    a compound subject or object still counts for every Alpha whose anchor
    appears before it).

    A single special cross-alpha rule applies: if A101's *only* qualifying
    anchor group is the broad "adoption" group (bare "AI adoption") and
    A102 already independently passed its own gate on this same claim, A101
    is suppressed -- a generic AI-adoption mention riding alongside genuine
    inference-specific evidence is not independent corroboration for A101.
    Every other combination of independently-passing gates is left alone;
    this function never otherwise prevents more than one Alpha from
    admitting on the same claim.
    """
    light = _light_normalize(text)
    segments = _segments(light)

    results = {alpha_id: _evaluate_single_gate(segments, alpha_id) for alpha_id in AI_ALPHA_IDS}

    a101 = results["A101"]
    a102 = results["A102"]
    if a101.passed and a101.matched_groups == {"adoption"} and a102.passed:
        results["A101"] = AiAlphaGateResult(
            alpha_id="A101",
            passed=False,
            matched_groups=a101.matched_groups,
            matched_anchors=a101.matched_anchors,
            matched_predicates=a101.matched_predicates,
        )

    return results
