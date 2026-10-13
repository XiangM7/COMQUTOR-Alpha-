"""P4 phase 2 (2026-10-12): preparation of the small-sample evaluation of the Alpha relevance judgment.

Builds, without calling any model and without reading any model answer:

  * a CANDIDATE SAMPLE of real saved claims paired with the Alpha their saved match already selected (the judgment unit of
    ``alpha_relevance_judge``), stratified over ordinary cases and the documented boundary types, each with its source identity, claim
    text, claim-text hash and Alpha-definition hash;
  * a BLIND REVIEW PACKET (fillable CSV sheets for one or two independent reviewers, the definitions appendix and the instructions) that
    shows the claim and the target Alpha's definition only -- never a model answer, a simulated answer or an engineering label;
  * an ENGINEERING DRAFT label file, kept apart and marked as draft (never a reference answer);
  * an OFFLINE EXECUTION PLAN: the exact requests (batch payload hashes), the rounds including a repeat subset, the request cap, the
    token / latency / cost estimates with their method and unknowns, the stop conditions, the code identity the run must still match,
    and quality thresholds marked as PENDING owner confirmation.

The stratum of a sample is selection metadata produced by simple lexical heuristics; it is NOT a label and never reaches the blind sheet.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from comqutor_alpha.alpha_library.alpha_loader import TAXONOMY_PATH
from comqutor_alpha.alpha_library.alpha_relevance_elements import (
    ELEMENTS_PATH,
    AlphaRelevanceDefinition,
    canonical_json_text,
    sha256_canonical_json,
    taxonomy_content_version,
)
from comqutor_alpha.structure_engine import alpha_relevance_llm as rl

SAMPLE_SCHEMA = "alpha_relevance_eval_sample.v1"
PLAN_SCHEMA = "alpha_relevance_eval_plan.v1"
AUTHORIZATION_SCHEMA = "alpha_relevance_eval_authorization.v1"
REVIEW_SCHEMA = "alpha_relevance_blind_review.v1"
SAMPLE_SEED = "p4-phase2-sample-v1"
MIN_TEXT_CHARS = 20
REPO_ROOT = Path(__file__).resolve().parents[1]
SAVED_RUN_ROOTS = (REPO_ROOT / "outputs" / "runs", REPO_ROOT / "outputs" / "t4_runs")

# The LIVE call settings of the small-sample evaluation (shared by the plan builder and the experiment configuration).
# provider / model: the pair every saved real Week 2 call of the latest Fresh Runs used (verified again before any request).
# batch 4 (my judgment): the reference task bills ~11 s and ~840 output tokens per item (median, mostly hidden reasoning), so a batch of
# 4 stays far inside the timeout, and a failed batch loses 4 pairs, not 8. timeout 300 s = the gateway's own per-task maximum.
# max_output_tokens 16384: >= 3x the largest per-item output ever billed for the reference task, times 4 items; it bounds the cost of a
# runaway answer. LIVE_REPEAT_EVERY = 2 re-sends the round-1 batches with an even 0-based index (B01, B03, ...); in this sample every Alpha
# has exactly two batches, so these are the first batch of each Alpha (the plan states the actual batches). 60 = the ceiling any plan may request.
LIVE_PROVIDER = "deepseek"
LIVE_MODEL = "deepseek-v4-flash"
LIVE_BATCH_SIZE = 4
LIVE_TIMEOUT_SECONDS = 300.0
LIVE_MAX_OUTPUT_TOKENS = 16384
LIVE_REPEAT_EVERY = 2
LIVE_MAX_CALLS_CEILING = 60
# session 4 (2026-10-12): a development-set retest of prompt v2 is an exact subset of the sample, never a new sample
RETEST_MAX_CALLS_CEILING = 24
RETEST_PURPOSE_KIND = "development_retest"

STRATUM_AMBIGUOUS = "DOCUMENTED_AMBIGUITY"
STRATUM_COLLISION = "WORD_COLLISION"
STRATUM_A9_FIXTURE = "A9_REAL_FIXTURE"
STRATUM_SHADOWED = "SHADOWED_CONFIRMATION"
STRATUM_IDENTITY_PROXY = "IDENTITY_PROXY"
STRATUM_RELATION = "RELATION_ELEMENT"
STRATUM_TOPIC_ONLY = "TOPIC_TERM_ONLY"
STRATUM_NO_OVERLAP = "NO_DEFINITION_OVERLAP"
STRATUM_ORDINARY = "ORDINARY"
STRATUM_PRIORITY = (STRATUM_AMBIGUOUS, STRATUM_COLLISION, STRATUM_A9_FIXTURE, STRATUM_SHADOWED, STRATUM_IDENTITY_PROXY,
                    STRATUM_RELATION, STRATUM_TOPIC_ONLY, STRATUM_NO_OVERLAP, STRATUM_ORDINARY)
STRATUM_MEANING = {
    STRATUM_AMBIGUOUS: "a round-36 A9 disputed item on its own saved matched Alpha: two documented readings give different tiers (UNRESOLVED may be right)",
    STRATUM_COLLISION: "a round-36 A9 fixture that records a real word collision (same string, different meaning)",
    STRATUM_A9_FIXTURE: "a round-36 A9 real-claim fixture judged against its own saved matched Alpha (it has an engineering DRAFT tier)",
    STRATUM_SHADOWED: "the claim names a core-owned element that also has a confirmation entry (a shadowed confirmation: never strong)",
    STRATUM_IDENTITY_PROXY: "the claim names a strong-eligible element whose tier depends on 'proxy / indicator != the quantity itself', and no core-owned element",
    STRATUM_RELATION: "the claim names both sides of a relation element (the relation itself may or may not be stated)",
    STRATUM_TOPIC_ONLY: "the claim uses one of the Alpha's topic terms but no element phrase matches lexically (mention vs. engagement; it may still engage an element in other words)",
    STRATUM_NO_OVERLAP: "the claim shares no content word with its matched Alpha's elements, taxonomy phrases or topic terms (a candidate for 'clearly unrelated'; not verified)",
    STRATUM_ORDINARY: "an ordinary matched pair",
}
DEFAULT_QUOTAS = {
    STRATUM_AMBIGUOUS: 4, STRATUM_COLLISION: 4, STRATUM_A9_FIXTURE: 8, STRATUM_SHADOWED: 6, STRATUM_IDENTITY_PROXY: 9,
    STRATUM_RELATION: 4, STRATUM_TOPIC_ONLY: 6, STRATUM_NO_OVERLAP: 6, STRATUM_ORDINARY: 13,
}
MAX_PER_RUN = 6
PER_ALPHA_MIN = 2

REVIEW_COLUMNS = (
    "sample_id", "target_alpha_id", "alpha_name", "claim_text", "definition_section", "core_owned_elements", "strong_eligible_elements",
    "outcome", "tier", "anchor_element_ids", "basis", "ambiguity_note", "review_status", "reviewer", "reviewed_at",
)
REVIEW_FILL_COLUMNS = ("outcome", "tier", "anchor_element_ids", "basis", "ambiguity_note", "review_status", "reviewer", "reviewed_at")
REVIEW_STATUS_PENDING = "PENDING"
REVIEW_STATUS_CONFIRMED = "CONFIRMED"
REVIEW_STATUS_NEEDS_DISCUSSION = "NEEDS_DISCUSSION"
REVIEW_STATUSES = (REVIEW_STATUS_PENDING, REVIEW_STATUS_CONFIRMED, REVIEW_STATUS_NEEDS_DISCUSSION)

DIRECTION_WORDS = frozenset({
    "rise", "rises", "rising", "fall", "falls", "falling", "hold", "holds", "strengthen", "strengthens", "weaken", "weakens", "beat", "beats",
    "expectations", "accelerate", "accelerates", "miss", "misses", "improve", "improves", "expand", "expands", "tighten", "tightens",
    "stabilize", "stabilizes", "recover", "recovers", "raised", "raise", "cut", "cuts", "down", "up", "higher", "lower", "despite", "fail",
    "fails", "to", "support", "exceeds", "exceed", "block", "blocks", "the", "of", "a", "an", "and", "within",
})
# words too generic to show any relation to an Alpha on their own (used only by the loose-word check of NO_DEFINITION_OVERLAP)
GENERIC_WORDS = frozenset({
    "for", "from", "with", "into", "over", "under", "near", "term", "strong", "signal", "signals", "growth", "stock",
    "stocks", "assets", "asset", "market", "markets", "risk", "level", "levels", "broad", "real", "high", "low", "new", "data",
})


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _term_regex(term: str) -> re.Pattern[str]:
    words = [re.escape(w) for w in re.findall(r"[A-Za-z0-9]+", term)]
    if not words:
        return re.compile(r"(?!x)x")
    body = r"[\s\-]+".join(words)
    return re.compile(rf"(?<![A-Za-z0-9]){body}s?(?![A-Za-z0-9])", re.IGNORECASE)


@dataclass(frozen=True)
class AlphaLexicon:
    """Selection heuristics only: the words that make a claim a candidate for a stratum (never a label)."""

    element_terms: Mapping[str, tuple[re.Pattern[str], ...]]
    relation_relata: Mapping[str, tuple[tuple[re.Pattern[str], ...], ...]]
    topic_terms: tuple[re.Pattern[str], ...]
    shadow_elements: frozenset[str]
    identity_dependent_strong: frozenset[str]
    loose_words: re.Pattern[str]


def build_lexicon(definition: AlphaRelevanceDefinition) -> AlphaLexicon:
    payload = definition.payload
    terms: dict[str, tuple[re.Pattern[str], ...]] = {}
    relata: dict[str, tuple[tuple[re.Pattern[str], ...], ...]] = {}
    for element in payload["elements"]:
        if element["kind"] == "relation":
            relata[element["id"]] = tuple(tuple(_term_regex(w) for w in [r]) for r in element.get("relata") or [])
            continue
        candidates = {element["label"]}
        for occurrence in element["occurrences"]:
            words = re.findall(r"[A-Za-z0-9\-]+", occurrence["phrase"])
            while words and words[0].lower() in DIRECTION_WORDS:
                words.pop(0)
            while words and words[-1].lower() in DIRECTION_WORDS:
                words.pop()
            if words:
                candidates.add(" ".join(words))
        terms[element["id"]] = tuple(_term_regex(c) for c in sorted(candidates) if len(c) >= 2)
    topics = [*payload["topic_terms"]["keywords"], *payload["topic_terms"]["beneficiary_assets"], *payload["topic_terms"]["risk_assets"]]
    shadow = frozenset(s["element_id"] for s in payload["shadowed_confirmation_entries"])
    ownership = definition.ownership
    dependent = set()
    for pair in payload["related_not_merged"]:
        for strong, core in ((pair["a"], pair["b"]), (pair["b"], pair["a"])):
            if ownership.get(strong) == "strong" and ownership.get(core) == "core":
                dependent.add(strong)
    # the merge-would-be-core rule: a related_not_merged pair records the tier merging would produce in the source table; the derived
    # definition keeps only (a, b, reason), so a strong element paired with a core element is identity-dependent here
    # every content word of the element labels, their taxonomy phrases and the topic terms: a claim containing none of them shows no
    # lexical relation at all to the Alpha (the NO_DEFINITION_OVERLAP candidates for 'clearly unrelated')
    phrases = [e["label"] for e in payload["elements"]] + [o["phrase"] for e in payload["elements"] for o in e["occurrences"]]
    phrases += [r for e in payload["elements"] for r in e.get("relata") or []] + topics
    vocabulary = {w.lower() for phrase in phrases for w in re.findall(r"[A-Za-z0-9]+", phrase)}
    words = sorted(w for w in vocabulary if (len(w) >= 3 or w == "ai") and w not in DIRECTION_WORDS and w not in GENERIC_WORDS)
    loose = re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(re.escape(w) for w in words) + r")s?(?![A-Za-z0-9])", re.IGNORECASE) if words else re.compile(r"(?!x)x")
    return AlphaLexicon(element_terms=terms, relation_relata=relata, topic_terms=tuple(_term_regex(t) for t in topics if t),
                        shadow_elements=shadow, identity_dependent_strong=frozenset(dependent), loose_words=loose)


def lexical_features(text: str, definition: AlphaRelevanceDefinition, lexicon: AlphaLexicon) -> dict[str, Any]:
    hits = sorted(e for e, patterns in lexicon.element_terms.items() if any(p.search(text) for p in patterns))
    relations = sorted(e for e, sides in lexicon.relation_relata.items() if sides and all(any(p.search(text) for p in side) for side in sides))
    topics = sorted({p.pattern for p in lexicon.topic_terms if p.search(text)})
    core_hits = [e for e in hits if definition.ownership.get(e) == "core"]
    strong_hits = [e for e in hits if definition.ownership.get(e) == "strong"]
    return {
        "element_hits": hits, "core_hits": core_hits, "strong_hits": strong_hits, "relation_hits": relations, "topic_term_hits": len(topics),
        "loose_word_hits": sorted({m.group(0).lower() for m in lexicon.loose_words.finditer(text)}),
        "shadowed_hits": sorted(e for e in core_hits if e in lexicon.shadow_elements),
        "identity_proxy_hits": sorted(e for e in strong_hits if e in lexicon.identity_dependent_strong) if not core_hits else [],
    }


@dataclass
class Candidate:
    run_id: str
    run_path: str
    alpha_matches_sha256: str
    claim_id: str
    alpha_id: str
    ticker: str
    agent: str
    text: str
    text_sha256: str
    features: dict[str, Any]
    strata: set[str] = field(default_factory=set)
    a9_fixture: dict[str, Any] | None = None
    disputed: dict[str, Any] | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.text_sha256, self.alpha_id)

    def order_key(self, salt: str) -> str:
        return hashlib.sha256(f"{SAMPLE_SEED}|{salt}|{self.run_id}|{self.claim_id}|{self.alpha_id}".encode()).hexdigest()


def is_original_run_dir(path: Path) -> bool:
    name = path.name
    return len(name) == 36 and name[8] == "-" and name[13] == "-" and (path / "alpha_matches.json").is_file()


def _a9_index(a9_fixtures_path: Path | None) -> tuple[dict[tuple[str, str], dict], dict[tuple[str, str], dict]]:
    if a9_fixtures_path is None or not Path(a9_fixtures_path).is_file():
        return {}, {}
    table = json.loads(Path(a9_fixtures_path).read_text(encoding="utf-8"))
    fixtures: dict[tuple[str, str], dict] = {}
    for fixture in table.get("fixtures") or []:
        source = fixture.get("source") if isinstance(fixture.get("source"), Mapping) else {}
        if source.get("claim_id") and source.get("saved_matched_alpha") == fixture.get("alpha_id"):
            fixtures[(source["claim_id"], fixture["alpha_id"])] = fixture
    disputed: dict[tuple[str, str], dict] = {}
    for item in table.get("disputed") or []:
        source = item.get("source") if isinstance(item.get("source"), Mapping) else {}
        if source.get("claim_id") and source.get("saved_matched_alpha") == item.get("alpha_id"):
            disputed[(source["claim_id"], item["alpha_id"])] = item
    return fixtures, disputed


def scan_candidates(
    run_dirs: Sequence[Path], definitions: Mapping[str, AlphaRelevanceDefinition], *, a9_fixtures_path: Path | None = None
) -> list[Candidate]:
    """Every matched (claim, saved matched Alpha) pair of the given ORIGINAL saved runs, with its selection features. Only read."""
    from comqutor_alpha.graph_engine.company_attribution import attribution_text  # noqa: PLC0415

    fixtures, disputed = _a9_index(a9_fixtures_path)
    lexicons = {aid: build_lexicon(d) for aid, d in definitions.items()}
    out: list[Candidate] = []
    for run_dir in sorted(Path(p) for p in run_dirs):
        raw = (run_dir / "alpha_matches.json").read_bytes()
        raw_sha256 = _sha256_bytes(raw)
        payload = json.loads(raw.decode("utf-8"))
        ticker = str(payload.get("ticker") or "")
        for match in rl.matched_pairs(payload.get("matches") or []):
            alpha_id = str(match["matched_alpha"])
            definition = definitions.get(alpha_id)
            text = attribution_text(match)
            if definition is None or len(text.strip()) < MIN_TEXT_CHARS:
                continue
            claim_id = str(match["claim_id"])
            candidate = Candidate(
                run_id=run_dir.name, run_path=str(run_dir), alpha_matches_sha256=raw_sha256, claim_id=claim_id, alpha_id=alpha_id,
                ticker=str(match.get("ticker") or ticker), agent=str(match.get("agent") or ""), text=text, text_sha256=rl.claim_text_sha256(match),
                features=lexical_features(text, definition, lexicons[alpha_id]),
                a9_fixture=fixtures.get((claim_id, alpha_id)), disputed=disputed.get((claim_id, alpha_id)),
            )
            f = candidate.features
            if candidate.disputed:
                candidate.strata.add(STRATUM_AMBIGUOUS)
            if candidate.a9_fixture:
                candidate.strata.add(STRATUM_COLLISION if (candidate.a9_fixture.get("term_collisions") or candidate.a9_fixture.get("collisions")) else STRATUM_A9_FIXTURE)
            if f["shadowed_hits"]:
                candidate.strata.add(STRATUM_SHADOWED)
            if f["identity_proxy_hits"]:
                candidate.strata.add(STRATUM_IDENTITY_PROXY)
            if f["relation_hits"]:
                candidate.strata.add(STRATUM_RELATION)
            if not f["element_hits"] and f["topic_term_hits"]:
                candidate.strata.add(STRATUM_TOPIC_ONLY)
            if not f["element_hits"] and not f["topic_term_hits"] and not f["relation_hits"] and not f["loose_word_hits"]:
                candidate.strata.add(STRATUM_NO_OVERLAP)
            candidate.strata.add(STRATUM_ORDINARY)
            out.append(candidate)
    return out


@dataclass
class Selection:
    selected: list[tuple[Candidate, str]]
    availability: dict[str, int]
    shortfalls: list[dict[str, Any]]
    pool: list[Candidate] = field(default_factory=list)


ELEMENT_KEYED_STRATA = {STRATUM_IDENTITY_PROXY: "identity_proxy_hits", STRATUM_SHADOWED: "shadowed_hits", STRATUM_RELATION: "relation_hits"}


def _diversity_key(c: Candidate, stratum: str) -> str:
    """Boundary strata spread over the element that put the pair in the stratum; every other stratum spreads over Alphas."""
    hits = c.features.get(ELEMENT_KEYED_STRATA.get(stratum, ""), [])
    return str(hits[0]) if hits else c.alpha_id


def select_sample(candidates: Sequence[Candidate], quotas: Mapping[str, int] | None = None) -> Selection:
    """Deterministic stratified selection: strata in priority order; inside a stratum, round-robin over the triggering element (boundary
    strata) or the Alpha (the rest), the least represented first; at most MAX_PER_RUN pairs per run, one pair per (claim text, Alpha);
    then every Alpha present in the pool is topped up to PER_ALPHA_MIN with ordinary pairs."""
    quotas = dict(quotas or DEFAULT_QUOTAS)
    groups: dict[tuple[str, str], list[Candidate]] = {}
    for c in sorted(candidates, key=lambda c: c.order_key("dedupe")):
        groups.setdefault(c.key, []).append(c)
    pool = []
    for group in groups.values():
        # the same claim text on the same Alpha in several runs is ONE pair; the documented A9 occurrence (if any) represents it so its
        # source identity is the one the A9 material cites, and the strata of every occurrence are kept
        representative = next((c for c in group if c.disputed or c.a9_fixture), group[0])
        for other in group:
            representative.strata |= other.strata
        pool.append(representative)
    availability = {s: sum(1 for c in pool if s in c.strata) for s in STRATUM_PRIORITY}
    chosen: list[tuple[Candidate, str]] = []
    used: set[tuple[str, str]] = set()
    per_run: dict[str, int] = {}

    def take(stratum: str, limit: int, alphas: Sequence[str] | None = None) -> int:
        by_key: dict[str, list[Candidate]] = {}
        for c in sorted((c for c in pool if stratum in c.strata and c.key not in used), key=lambda c: c.order_key(stratum)):
            if alphas is None or c.alpha_id in alphas:
                by_key.setdefault(_diversity_key(c, stratum), []).append(c)

        def rank(key: str) -> tuple[int, int, str]:
            alpha = by_key[key][0].alpha_id if by_key[key] else ""
            in_stratum = sum(1 for c, s in chosen if s == stratum and _diversity_key(c, stratum) == key)
            overall = sum(1 for c, _ in chosen if c.alpha_id == alpha)
            return (in_stratum, overall, key) if stratum in ELEMENT_KEYED_STRATA else (overall, in_stratum, key)

        taken = 0
        while taken < limit and any(by_key.values()):
            for key in sorted(by_key, key=rank):  # the least represented element / Alpha first
                queue = by_key[key]
                while queue and (queue[0].key in used or per_run.get(queue[0].run_id, 0) >= MAX_PER_RUN):
                    queue.pop(0)
                if not queue or taken >= limit:
                    continue
                c = queue.pop(0)
                chosen.append((c, stratum))
                used.add(c.key)
                per_run[c.run_id] = per_run.get(c.run_id, 0) + 1
                taken += 1
        return taken

    shortfalls = []
    for stratum in STRATUM_PRIORITY:
        target = int(quotas.get(stratum, 0))
        got = take(stratum, target)
        if got < target:
            shortfalls.append({"stratum": stratum, "target": target, "selected": got, "available_unique_pairs": availability[stratum]})
    present = sorted({c.alpha_id for c in pool})
    for alpha in present:
        have = sum(1 for c, _ in chosen if c.alpha_id == alpha)
        if have < PER_ALPHA_MIN:
            take(STRATUM_ORDINARY, PER_ALPHA_MIN - have, alphas=[alpha])
    return Selection(selected=chosen, availability=availability, shortfalls=shortfalls, pool=pool)


def element_coverage(selection: Selection, definitions: Mapping[str, AlphaRelevanceDefinition]) -> dict[str, dict[str, dict[str, int]]]:
    """For every boundary element of the definitions (zero rows included): unique pool pairs that lexically trigger it, and how many of
    them the sample holds -- an element with no available pair is a coverage gap, never filled with a constructed sample."""
    lexicons = {aid: build_lexicon(d) for aid, d in definitions.items()}
    kinds = {
        "identity_dependent_strong": ("identity_proxy_hits", sorted(e for lx in lexicons.values() for e in lx.identity_dependent_strong)),
        "shadowed_confirmation": ("shadowed_hits", sorted(e for lx in lexicons.values() for e in lx.shadow_elements)),
        "relation": ("relation_hits", sorted(e["id"] for d in definitions.values() for e in d.payload["elements"] if e["kind"] == "relation")),
    }
    chosen = [c for c, _ in selection.selected]
    return {kind: {e: {"available": sum(1 for c in selection.pool if e in c.features[field_name]),
                       "selected": sum(1 for c in chosen if e in c.features[field_name])} for e in elements}
            for kind, (field_name, elements) in kinds.items()}


def build_manifest(selection: Selection, definitions: Mapping[str, AlphaRelevanceDefinition], *, pool_runs: Sequence[str]) -> dict[str, Any]:
    """The fixed sample: sample ids are assigned in a hash order unrelated to the strata (the id never hints the stratum)."""
    rows = sorted(selection.selected, key=lambda pair: hashlib.sha256(f"{SAMPLE_SEED}|id|{pair[0].claim_id}|{pair[0].alpha_id}".encode()).hexdigest())
    samples = []
    for index, (c, stratum) in enumerate(rows, start=1):
        definition = definitions[c.alpha_id]
        samples.append({
            "sample_id": f"S{index:03d}",
            "source_run_id": c.run_id, "source_alpha_matches_sha256": c.alpha_matches_sha256, "claim_id": c.claim_id, "ticker": c.ticker,
            "agent": c.agent, "target_alpha_id": c.alpha_id, "claim_text": c.text, "claim_text_sha256": c.text_sha256,
            "alpha_definition_sha256": definition.sha256,
            "selection": {"primary_stratum": stratum, "all_strata": sorted(c.strata), "features": c.features,
                          "a9_fixture_id": (c.a9_fixture or {}).get("id"), "a9_disputed_id": (c.disputed or {}).get("id")},
        })
    keys = [(s["claim_id"], s["target_alpha_id"]) for s in samples]
    if len(set(keys)) != len(keys):
        raise ValueError("DUPLICATE_SAMPLE_PAIR")
    body = {
        "schema": SAMPLE_SCHEMA, "seed": SAMPLE_SEED, "task": rl.task_identity(),
        "elements_file_sha256": _sha256_bytes(Path(ELEMENTS_PATH).read_bytes()), "taxonomy_file_sha256": _sha256_bytes(Path(TAXONOMY_PATH).read_bytes()),
        "taxonomy_content_version": taxonomy_content_version(), "pool": {"original_runs": len(pool_runs)},
        "selection_rules": {"quotas": DEFAULT_QUOTAS, "max_per_run": MAX_PER_RUN, "per_alpha_min": PER_ALPHA_MIN, "min_text_chars": MIN_TEXT_CHARS,
                            "strata": STRATUM_MEANING,
                            "note": "strata come from lexical heuristics for SELECTION only; they are not labels and never reach the blind sheet"},
        "availability_unique_pairs": selection.availability, "shortfalls": selection.shortfalls,
        "boundary_element_coverage": element_coverage(selection, definitions),
        "sample_count": len(samples), "samples": samples,
        "use": "preliminary verification only; not representative of every Alpha or every input",
    }
    return {**body, "content_sha256": sha256_canonical_json(body)}


def verify_manifest_sources(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every sample re-read from its saved run: the claim text hash and the matched Alpha must still be what the manifest records."""
    from comqutor_alpha.graph_engine.company_attribution import attribution_text  # noqa: PLC0415

    problems = []
    cache: dict[str, dict[str, Any]] = {}
    for s in manifest["samples"]:
        run_path = _run_path(s["source_run_id"])
        if run_path is None:
            problems.append({"sample_id": s["sample_id"], "problem": "SOURCE_RUN_MISSING"})
            continue
        if s.get("repair") is not None:  # session 6: a repaired sample is re-read from the saved source text it was repaired from
            if repaired_text_from_source(run_path, s["repair"]) != s["claim_text"]:
                problems.append({"sample_id": s["sample_id"], "problem": "SOURCE_REPAIR_CHANGED"})
            continue
        if s["source_run_id"] not in cache:
            cache[s["source_run_id"]] = {str(m.get("claim_id")): m for m in json.loads((run_path / "alpha_matches.json").read_text(encoding="utf-8")).get("matches") or []}
        match = cache[s["source_run_id"]].get(s["claim_id"])
        if match is None or match.get("matched_alpha") != s["target_alpha_id"]:
            problems.append({"sample_id": s["sample_id"], "problem": "SOURCE_MATCH_CHANGED"})
        elif rl.claim_text_sha256(match) != s["claim_text_sha256"] or attribution_text(match) != s["claim_text"]:
            problems.append({"sample_id": s["sample_id"], "problem": "SOURCE_TEXT_CHANGED"})
    return problems


def _json_at(value: Any, path: Sequence[Any]) -> Any:
    for step in path:
        value = value[step]
    return value


def repaired_text_from_source(run_path: Path, repair: Mapping[str, Any]) -> str | None:
    """The text a repaired sample was read from: the saved source file must still have the recorded hash, and the recorded span of the
    recorded JSON field is returned. ``None`` when the source changed or cannot be read -- never a guess."""
    source = run_path / str(repair.get("source_file") or "")
    try:
        raw = source.read_bytes()
        if _sha256_bytes(raw) != repair.get("source_file_sha256"):
            return None
        text = _json_at(json.loads(raw.decode("utf-8")), repair.get("json_path") or [])
        return text[int(repair["char_start"]):int(repair["char_end"])] if isinstance(text, str) else None
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None


def build_repaired_sample(original: Mapping[str, Any], *, run_path: Path, source_file: str, json_path: Sequence[Any], char_start: int,
                          char_end: int, defect: str, method: str) -> dict[str, Any]:
    """Session 6: a repaired copy of a sample whose claim text was cut by the extraction, read from the saved source text. The repaired
    sample gets its own id (``<id>R``) and claim id (``<claim id>:repaired:1``); the original sample is never changed. The repaired
    text must extend the original text (same sentence, more words) -- a different sentence is refused."""
    repair = {"original_sample_id": original["sample_id"], "original_claim_id": original["claim_id"],
              "original_claim_text": original["claim_text"], "original_claim_text_sha256": original["claim_text_sha256"],
              "source_file": source_file, "source_file_sha256": _sha256_bytes((run_path / source_file).read_bytes()),
              "json_path": list(json_path), "char_start": int(char_start), "char_end": int(char_end), "defect": defect, "method": method}
    text = repaired_text_from_source(run_path, repair)
    if text is None:
        raise ValueError(f"REPAIR_SOURCE_UNREADABLE: {original['sample_id']}")
    if not " ".join(text.split()).startswith(" ".join(str(original["claim_text"]).split())) or len(text) <= len(original["claim_text"]):
        raise ValueError(f"REPAIR_NOT_AN_EXTENSION_OF_THE_ORIGINAL: {original['sample_id']}")
    return {
        **{k: v for k, v in original.items() if k not in ("sample_id", "claim_id", "claim_text", "claim_text_sha256", "selection", "retest")},
        "sample_id": f"{original['sample_id']}R", "claim_id": f"{original['claim_id']}:repaired:1", "claim_text": text,
        "claim_text_sha256": rl.claim_text_sha256({"claim": text}),
        "selection": {**dict(original.get("selection") or {}), "repaired_from": original["sample_id"]},
        "repair": repair,
    }


def input_quality_rows(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Session 6: per sample, the mechanical observations about its text. ``text_notes`` are sent to the model as hints of possible
    incompleteness (never a rejection); ``report_only_notes`` (no final punctuation) are too common in complete headlines and list items
    to be sent. Nothing here excludes a sample."""
    rows = []
    for s in manifest["samples"]:
        text = str(s["claim_text"]).rstrip()
        report_only = [] if text[-1:] in ".!?。！？)\"'\u201d" else ["no_terminal_punctuation"]
        rows.append({"sample_id": s["sample_id"], "target_alpha_id": s["target_alpha_id"], "text_notes": rl.text_completeness_notes(text),
                     "report_only_notes": report_only, "repaired": bool(s.get("repair")), "handling": "sent as is; notes are hints only"})
    return rows


def _run_path(run_id: str) -> Path | None:
    for root in SAVED_RUN_ROOTS:
        if (root / run_id / "alpha_matches.json").is_file():
            return root / run_id
    return None


def manifest_content_sha256(manifest: Mapping[str, Any]) -> str:
    return sha256_canonical_json({k: v for k, v in manifest.items() if k != "content_sha256"})


def source_match(sample: Mapping[str, Any]) -> dict[str, Any] | None:
    run_path = _run_path(sample["source_run_id"])
    if run_path is None:
        return None
    for m in json.loads((run_path / "alpha_matches.json").read_text(encoding="utf-8")).get("matches") or []:
        if m.get("claim_id") == sample["claim_id"]:
            return m
    return None


# ----------------------------------------------------------------------------------------------------------- blind review packet
def _element_summary(definition: AlphaRelevanceDefinition, ownership: str) -> str:
    return "; ".join(f"{e} ({definition.labels[e]})" for e, o in definition.ownership.items() if o == ownership)


def blind_review_rows(manifest: Mapping[str, Any], definitions: Mapping[str, AlphaRelevanceDefinition]) -> list[dict[str, str]]:
    """One row per sample, in sample-id order. Shows the claim and the target Alpha's definition only; every answer column is empty."""
    rows = []
    for s in manifest["samples"]:
        d = definitions[s["target_alpha_id"]]
        row = dict.fromkeys(REVIEW_COLUMNS, "")
        row.update({
            "sample_id": s["sample_id"], "target_alpha_id": s["target_alpha_id"], "alpha_name": str(d.payload["name"]), "claim_text": s["claim_text"],
            "definition_section": f"review_definitions.md#{s['target_alpha_id'].lower()}", "core_owned_elements": _element_summary(d, "core"),
            "strong_eligible_elements": _element_summary(d, "strong"), "review_status": REVIEW_STATUS_PENDING,
        })
        rows.append(row)
    return rows


def render_csv(rows: Sequence[Mapping[str, str]], columns: Sequence[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), extrasaction="raise", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in columns})
    return "﻿" + buffer.getvalue()  # BOM: spreadsheet applications open the UTF-8 text correctly


def render_definitions_markdown(manifest: Mapping[str, Any], definitions: Mapping[str, AlphaRelevanceDefinition]) -> str:
    alphas = sorted({s["target_alpha_id"] for s in manifest["samples"]})
    out = ["# Definitions for the blind review (criterion alpha_relevance_criterion.exp1)", "",
           "Verbatim taxonomy text and the experimental element ownership the relevance task is given. Nothing here is an answer.", ""]
    for alpha_id in alphas:
        d = definitions[alpha_id]
        p = d.payload
        out += [f"## {alpha_id}", "", f"**{p['name']}** — definition sha256 `{d.sha256}`", "",
                f"- core thesis: {p['definition']['core_thesis']}",
                f"- trigger signals: {'; '.join(p['definition']['trigger_signals'])}",
                f"- confirmation signals: {'; '.join(p['definition']['confirmation_signals'])}",
                f"- invalidation conditions: {'; '.join(p['definition']['invalidation_conditions'])}",
                f"- topic terms (keywords / beneficiaries / risk assets): {'; '.join([*p['topic_terms']['keywords'], *p['topic_terms']['beneficiary_assets'], *p['topic_terms']['risk_assets']])}",
                "", "| element id | label | ownership | where the taxonomy states it |", "|---|---|---|---|"]
        for e in p["elements"]:
            where = "; ".join(f"{o['list']}: “{o['phrase']}”" for o in e["occurrences"])
            relata = f" (relation between: {', '.join(e['relata'])})" if e.get("relata") else ""
            out.append(f"| `{e['id']}` | {e['label']}{relata} | {'core-owned' if e['ownership'] == 'core' else 'strong-eligible'} | {where} |")
        if p["shadowed_confirmation_entries"]:
            out += ["", "Shadowed confirmation entries (they name a core-owned element, so they never produce “strong”): "
                    + "; ".join(f"“{s['phrase']}” → `{s['element_id']}`" for s in p["shadowed_confirmation_entries"])]
        if p["related_not_merged"]:
            out += ["", "Near-identical but DIFFERENT elements (not merged):"]
            out += [f"- `{r['a']}` vs `{r['b']}`: {r['reason']}" for r in p["related_not_merged"]]
        if p["context_phrases"]:
            out += ["", "Context phrases (no ownership): " + "; ".join(f"“{c['phrase']}” — {c['reason']}" for c in p["context_phrases"])]
        out.append("")
    return "\n".join(out) + "\n"


REVIEW_INSTRUCTIONS = """# 盲审说明（P4 第二阶段，判据 alpha_relevance_criterion.exp1）

**写给**：负责人（审阅人 A），以及可选的第二位独立审阅人（审阅人 B）。两人各填自己的表，填写前不要互相看。

## 判断什么
每一行是一条真实 claim 和它在保存 run 里**已经匹配的** Alpha。只判断这条 claim 与这个 Alpha 定义的相关程度，不判断 claim 是否正确、是否看多看空、说的是哪家公司。

## 判据（第一阶段的实验判据，本轮不改）
- 判断单位：claim 实质陈述或度量了哪些**要素**（变量或关系）。仅出现名字（标签、分母、修饰语、撞词）不算。关系要素必须陈述关系本身。
- **core**：至少陈述或度量了一个 core 归属要素（核心论点、触发条件、失效条件里的变量或关系）。同时命中 core 和 strong，取 core（Q1 优先）。
- **strong**：只陈述或度量了 strong 可达要素（只出现在确认信号里），没有命中 core。被遮蔽的确认条目指向 core 归属要素，不能产生 strong。
- **weak**：没有实质触及任何要素，只有主题联系或语义上的提及。
- **none**：与该 Alpha 的定义没有实质关系。不能只因为没有关键词就判 none。
- 真正同义的概念可以合并；上下位概念、代理指标与原量分别判断（订单≠需求，backlog≠订单，预期≠盈利）。
- 数字大小、同比／环比、时间跨度、方向、真伪、置信度、公司归属，都**不**决定档位。
- 证据不足以确定归属时，填 **UNRESOLVED**，不要硬选档位。

## 怎么填（只改下面这些列，其余列不要改）
| 列 | 允许的值 |
|---|---|
| `outcome` | `DETERMINED` 或 `UNRESOLVED` |
| `tier` | outcome 为 DETERMINED 时填 `core`／`strong`／`weak`／`none`；UNRESOLVED 时留空 |
| `anchor_element_ids` | 你认为被实质陈述或度量的要素 id，用 `;` 分隔（core／strong 必填；weak／none 留空） |
| `basis` | 一两句判断依据 |
| `ambiguity_note` | 有歧义时写明两种读法；没有就留空 |
| `review_status` | `PENDING`（未完成）／`CONFIRMED`（我确认这一行）／`NEEDS_DISCUSSION`（需要讨论） |
| `reviewer`、`reviewed_at` | 你的名字缩写、日期 |

只有审阅人 A（负责人）标为 `CONFIRMED` 的行，才会作为参考标签用于质量评价。程序不会替你补任何答案，未完成的行一直保持待复核。
要素、归属和原文短语见 `review_definitions.md`（每个 Alpha 一节）。

## 注意
- 负责人填 `blind_review_sheet_A.csv`；第二位审阅人（可选）填 `blind_review_sheet_B.csv`。两份表在填完之前都不要给对方看。
- 不要改 `sample_id`、`claim_text`、`target_alpha_id`。程序按 `sample_id` 对齐，并核对这一行显示的 claim 和 Alpha 是否仍是样本清单里的那一对，不一致的行作废。可以排序，但不要拆分、合并或复制行。
- 保存时选 **CSV UTF-8** 格式。
- 填完盲审表之前，只看 `review/` 文件夹。不要打开 `sample/`（选样分层）、`engineering_draft/`（工程侧草稿，不是参考答案）、`rehearsal/`（模拟答案）和任何评测报告，它们都会影响盲审。
- 填写不合规的行会在评测报告里标成 INVALID 并写明原因（例如 core 没填 core 归属的要素），改正后重新评测即可。
"""


def draft_label_rows(manifest: Mapping[str, Any], a9_fixtures_path: Path | None) -> list[dict[str, str]]:
    """ENGINEERING DRAFT labels where the round-36 A9 material has one -- for comparison only, never a reference answer."""
    fixtures, disputed = _a9_index(a9_fixtures_path)
    rows = []
    for s in manifest["samples"]:
        key = (s["claim_id"], s["target_alpha_id"])
        fixture, dispute = fixtures.get(key), disputed.get(key)
        draft, basis = "", ""
        if fixture:
            draft = str(fixture.get("expected_tier") or "")
            basis = "; ".join(f"engages {e.get('element')} ({e.get('evidence')})" for e in fixture.get("engages") or []) or "no engaged element recorded"
        if dispute:
            draft = "UNRESOLVED-candidate"
            basis = " | ".join(f"{r.get('id')}: {r.get('label')} -> {r.get('tier')}" for r in dispute.get("readings") or [])
        rows.append({"sample_id": s["sample_id"], "engineering_draft_tier": draft, "draft_basis": basis,
                     "draft_source": "round-36 A9 fixture" if fixture else ("round-36 A9 disputed item" if dispute else "none"),
                     "status": "ENGINEERING DRAFT - NOT A REFERENCE ANSWER"})
    return rows


# ----------------------------------------------------------------------------------------------------------- execution plan
CODE_IDENTITY_FILES = (
    "comqutor_alpha/structure_engine/alpha_relevance_llm.py",
    "comqutor_alpha/alpha_library/alpha_relevance_elements.py",
    "comqutor_alpha/alpha_library/alpha_relevance_elements_v1.json",
    "comqutor_alpha/alpha_library/alpha_relevance_hints_v1.json",
    "comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml",
    "comqutor_alpha/graph_engine/alpha_relevance_judgment.py",
    "comqutor_alpha/graph_engine/company_attribution.py",
    "comqutor_alpha/alpha_relevance_experiment.py",
    "comqutor_alpha/alpha_relevance_eval_prep.py",
    "comqutor_alpha/alpha_relevance_evaluation.py",
    "comqutor_alpha/structure_engine/week2_llm.py",
    "comqutor_alpha/run_provider_stop.py",
    "comqutor_alpha/llm/cost_basis.py",
    "comqutor_alpha/llm_runtime/contracts.py",
    "comqutor_alpha/llm_runtime/session.py",
    "comqutor_alpha/llm_runtime/recorder.py",
    "tradingagents/llm_clients/factory.py",
    "tradingagents/llm_clients/openai_client.py",
    "scripts/alpha_relevance_judgment.py",
    "scripts/alpha_relevance_eval.py",
)
REFERENCE_TASK = "evidence_stance_classifier"
# My judgment, stated in the plan: the relevance prompt asks for an element analysis per item, so the upper estimate doubles the largest
# per-item output the reference task ever billed. The hard bound does not depend on it (it is the max_tokens cap).
OUTPUT_HIGH_MULTIPLIER = 2.0


def code_identity(repo_root: Path | str = ".") -> dict[str, Any]:
    root = Path(repo_root)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False).stdout.strip() or None
    return {"git_head": head, "files": {p: _sha256_bytes((root / p).read_bytes()) for p in CODE_IDENTITY_FILES}}


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _quantiles(values: Sequence[float]) -> dict[str, float | int | None]:
    ordered = sorted(values)
    if not ordered:
        return {"n": 0, "median": None, "p90": None, "min": None, "max": None}
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    p90 = ordered[min(len(ordered) - 1, int(round(0.9 * (len(ordered) - 1))))]
    return {"n": len(ordered), "median": round(median, 3), "p90": round(p90, 3), "min": round(ordered[0], 3), "max": round(ordered[-1], 3)}


def measure_reference_ledgers(stance_ledgers: Sequence[Path | str], cap_ledgers: Sequence[Path | str]) -> dict[str, Any]:
    """Facts measured from saved REAL semantic ledgers (execution mode ``live``), the basis of every estimate in the plan.

    * ``stance``: the reference task's prompt is rebuilt exactly (its recorded prompt identity must equal today's) to measure prompt
      characters per billed input token; billed output (visible JSON + hidden reasoning) per item; latency per call and per item.
    * ``max_tokens_enforcement``: every live call that carried an output cap, deduplicated by (run, call id): whether the billed output
      ever exceeded the cap, and how calls that reached it ended.
    """
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway  # noqa: PLC0415

    prefix = Week2LLMGateway._provider_prompt_prefix(REFERENCE_TASK)  # noqa: SLF001
    identity = Week2LLMGateway.prompt_identity_sha256(REFERENCE_TASK)
    sources, seen = [], set()
    chars_per_token, per_item, reasoning_share, latency_call, latency_item, items_per_call = [], [], [], [], [], []
    excluded: dict[str, int] = {}
    caps: dict[int, dict[str, Any]] = {}
    pairs: set[tuple[str, str]] = set()

    def records(path: Path | str, role: str):
        raw = Path(path).read_bytes()
        sources.append({"path": str(path), "role": role, "sha256": _sha256_bytes(raw)})
        for line in raw.decode("utf-8", "replace").splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, Mapping) and record.get("execution_mode") == "live":
                yield record

    names: dict[tuple[str, str], int] = {}
    call_dates: set[str] = set()
    seen_named: set[tuple[Any, Any]] = set()
    for path in stance_ledgers:
        for r in records(path, "reference_task"):
            if (r.get("run_id"), r.get("call_id")) not in seen_named:  # every live call of the run: the name requested vs. the name returned
                seen_named.add((r.get("run_id"), r.get("call_id")))
                requested = _as_mapping(r.get("request_control")).get("request_model") or r.get("model")
                returned = _as_mapping(r.get("provider_response")).get("response_model")
                names[(str(requested), str(returned))] = names.get((str(requested), str(returned)), 0) + 1
                if r.get("started_at"):
                    call_dates.add(str(r["started_at"])[:10])
            if r.get("task") != REFERENCE_TASK or (r.get("run_id"), r.get("call_id")) in seen:
                continue
            seen.add((r.get("run_id"), r.get("call_id")))
            usage = _as_mapping(r.get("token_usage"))
            items = len(_as_mapping(r.get("input_payload")).get("items") or [])
            if r.get("prompt_sha256") != identity:
                excluded["prompt_identity_differs"] = excluded.get("prompt_identity_differs", 0) + 1
                continue
            if not usage.get("input_tokens") or not items:
                excluded["no_usage_or_items"] = excluded.get("no_usage_or_items", 0) + 1
                continue
            pairs.add((str(r.get("provider")), str(r.get("model"))))
            prompt = prefix + json.dumps(dict(r["input_payload"]), ensure_ascii=False, default=str)
            chars_per_token.append(len(prompt) / usage["input_tokens"])
            items_per_call.append(items)
            if r.get("validation_status") == "accepted" and usage.get("output_tokens"):
                per_item.append(usage["output_tokens"] / items)
                details = _as_mapping(_as_mapping(_as_mapping(r.get("provider_response")).get("raw_usage")).get("completion_tokens_details"))
                if details.get("reasoning_tokens") is not None:
                    reasoning_share.append(details["reasoning_tokens"] / usage["output_tokens"])
            if r.get("latency_ms"):
                latency_call.append(r["latency_ms"] / 1000)
                latency_item.append(r["latency_ms"] / 1000 / items)
    seen_capped = set()
    for path in cap_ledgers:
        for r in records(path, "max_tokens_evidence"):
            cap = _as_mapping(r.get("request_control")).get("max_tokens_value")
            out = _as_mapping(r.get("token_usage")).get("output_tokens")
            if not cap or out is None or (r.get("run_id"), r.get("call_id")) in seen_capped:
                continue
            seen_capped.add((r.get("run_id"), r.get("call_id")))
            entry = caps.setdefault(int(cap), {"calls": 0, "max_output_tokens": 0, "over_cap": 0, "finish_reasons": {}, "models": set()})
            entry["calls"] += 1
            entry["max_output_tokens"] = max(entry["max_output_tokens"], int(out))
            entry["over_cap"] += int(out > cap)
            reason = str(_as_mapping(r.get("provider_response")).get("finish_reason"))
            entry["finish_reasons"][reason] = entry["finish_reasons"].get(reason, 0) + 1
            entry["models"].add(f"{r.get('provider')}/{r.get('model')}")
    for entry in caps.values():
        entry["models"] = sorted(entry["models"])
    return {
        "sources": sources,
        "reference_task": REFERENCE_TASK,
        "reference_provider_models": sorted(f"{p}/{m}" for p, m in pairs),
        "stance": {"calls": len(chars_per_token), "excluded": excluded, "items_per_call": _quantiles(items_per_call),
                   "chars_per_input_token": _quantiles(chars_per_token), "output_tokens_per_item": _quantiles(per_item),
                   "reasoning_share_of_output": _quantiles(reasoning_share), "latency_seconds_per_call": _quantiles(latency_call),
                   "latency_seconds_per_item": _quantiles(latency_item)},
        "max_tokens_enforcement": {"calls": sum(e["calls"] for e in caps.values()), "calls_over_cap": sum(e["over_cap"] for e in caps.values()),
                                   "by_cap": {str(k): caps[k] for k in sorted(caps)}},
        "model_names_observed": {
            "pairs": [{"requested": req, "returned_by_provider": ret if ret != "None" else None, "calls": n} for (req, ret), n in sorted(names.items())],
            "call_dates": sorted(call_dates),
            "note": "requested = request_control.request_model; returned = the model field of the provider's response (absent when no response arrived)",
        },
    }


def measure_relevance_ledgers(ledgers: Sequence[Path | str]) -> dict[str, Any]:
    """Session 4 (2026-10-12): facts measured from the relevance task's OWN saved real calls (execution mode ``live``), the basis of a
    later plan of the same task. Every prompt is rebuilt exactly under the version it was recorded with (that version's identity must
    reproduce the recorded ``prompt_sha256``), so characters per billed input token are exact; billed output per item and latency per
    item are those calls' own. ``basis_prompt_versions`` names what was measured: a plan for another prompt version states the gap."""
    sources: list[dict[str, Any]] = []
    chars_per_token, per_item, reasoning_share, latency_call, latency_item, items_per_call = [], [], [], [], [], []
    excluded: dict[str, int] = {}
    versions: dict[str, int] = {}
    names: dict[tuple[str, str], int] = {}
    call_dates: set[str] = set()
    caps: dict[int, dict[str, Any]] = {}
    pairs: set[tuple[str, str]] = set()
    seen: set[tuple[Any, Any]] = set()
    for path in ledgers:
        raw = Path(path).read_bytes()
        sources.append({"path": str(path), "role": "relevance_task_real_calls", "sha256": _sha256_bytes(raw)})
        for line in raw.decode("utf-8", "replace").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if not isinstance(r, Mapping) or r.get("execution_mode") != "live" or r.get("task") != rl.LLM_TASK_NAME:
                continue
            if (r.get("run_id"), r.get("call_id")) in seen:
                continue
            seen.add((r.get("run_id"), r.get("call_id")))
            requested = _as_mapping(r.get("request_control")).get("request_model") or r.get("model")
            returned = _as_mapping(r.get("provider_response")).get("response_model")
            names[(str(requested), str(returned))] = names.get((str(requested), str(returned)), 0) + 1
            if r.get("started_at"):
                call_dates.add(str(r["started_at"])[:10])
            usage = _as_mapping(r.get("token_usage"))
            cap = _as_mapping(r.get("request_control")).get("max_tokens_value")
            if cap and usage.get("output_tokens") is not None:
                entry = caps.setdefault(int(cap), {"calls": 0, "max_output_tokens": 0, "over_cap": 0, "finish_reasons": {}, "models": set()})
                entry["calls"] += 1
                entry["max_output_tokens"] = max(entry["max_output_tokens"], int(usage["output_tokens"]))
                entry["over_cap"] += int(int(usage["output_tokens"]) > int(cap))
                reason = str(_as_mapping(r.get("provider_response")).get("finish_reason"))
                entry["finish_reasons"][reason] = entry["finish_reasons"].get(reason, 0) + 1
                entry["models"].add(f"{r.get('provider')}/{r.get('model')}")
            version = str(r.get("prompt_version"))
            if version not in rl.PROMPT_VERSIONS or rl.prompt_identity_sha256(version) != r.get("prompt_sha256"):
                excluded["prompt_identity_not_reproduced"] = excluded.get("prompt_identity_not_reproduced", 0) + 1
                continue
            items = len(_as_mapping(r.get("input_payload")).get("items") or [])
            if not usage.get("input_tokens") or not items:
                excluded["no_usage_or_items"] = excluded.get("no_usage_or_items", 0) + 1
                continue
            versions[version] = versions.get(version, 0) + 1
            pairs.add((str(r.get("provider")), str(r.get("model"))))
            chars_per_token.append(len(rl.build_prompt(r["input_payload"], prompt_version=version)) / usage["input_tokens"])
            items_per_call.append(items)
            if r.get("validation_status") == "accepted" and usage.get("output_tokens"):
                per_item.append(usage["output_tokens"] / items)
                details = _as_mapping(_as_mapping(_as_mapping(r.get("provider_response")).get("raw_usage")).get("completion_tokens_details"))
                if details.get("reasoning_tokens") is not None:
                    reasoning_share.append(details["reasoning_tokens"] / usage["output_tokens"])
            if r.get("latency_ms"):
                latency_call.append(r["latency_ms"] / 1000)
                latency_item.append(r["latency_ms"] / 1000 / items)
    for entry in caps.values():
        entry["models"] = sorted(entry["models"])
    return {
        "sources": sources,
        "basis_task": rl.LLM_TASK_NAME,
        "basis_kind": "relevance_task_own_real_calls",
        "basis_prompt_versions": dict(sorted(versions.items())),
        "reference_provider_models": sorted(f"{p}/{m}" for p, m in pairs),
        "basis": {"calls": len(chars_per_token), "excluded": excluded, "items_per_call": _quantiles(items_per_call),
                  "chars_per_input_token": _quantiles(chars_per_token), "output_tokens_per_item": _quantiles(per_item),
                  "reasoning_share_of_output": _quantiles(reasoning_share), "latency_seconds_per_call": _quantiles(latency_call),
                  "latency_seconds_per_item": _quantiles(latency_item)},
        "max_tokens_enforcement": {"calls": sum(e["calls"] for e in caps.values()), "calls_over_cap": sum(e["over_cap"] for e in caps.values()),
                                   "by_cap": {str(k): caps[k] for k in sorted(caps)}},
        "model_names_observed": {
            "pairs": [{"requested": req, "returned_by_provider": ret if ret != "None" else None, "calls": n} for (req, ret), n in sorted(names.items())],
            "call_dates": sorted(call_dates),
            "note": "requested = request_control.request_model; returned = the model field of the provider's response (absent when no response arrived)",
        },
    }


def plan_batches(manifest: Mapping[str, Any], definitions: Mapping[str, AlphaRelevanceDefinition], *, batch_size: int,
                 isolate: Sequence[str] = (), exclude: Sequence[str] = ()) -> list[dict[str, Any]]:
    """The exact round-1 requests: the manifest's pairs rebuilt into request items (definitions read today and checked against the
    manifest's hashes), grouped by Alpha and chunked exactly like the task does. Session 6: ``exclude`` = samples the plan keeps in
    its table but does not send; ``isolate`` = samples sent alone in their own request (after the others), e.g. a repaired sample
    that must not share a request with the original it repairs."""
    known = {s["sample_id"] for s in manifest["samples"]}
    if (set(isolate) | set(exclude)) - known or set(isolate) & set(exclude):
        raise ValueError(f"PLAN_SAMPLE_SELECTION_INVALID: {sorted((set(isolate) | set(exclude)) - known) or sorted(set(isolate) & set(exclude))}")
    items = []
    lone = []
    by_key = {}
    for s in sorted(manifest["samples"], key=lambda s: (s["target_alpha_id"], s["sample_id"])):
        if s["sample_id"] in exclude:
            continue
        definition = definitions.get(s["target_alpha_id"])
        if definition is None or definition.sha256 != s["alpha_definition_sha256"]:
            raise ValueError(f"DEFINITION_CHANGED_SINCE_SAMPLE: {s['sample_id']}")
        if rl.claim_text_sha256({"claim": s["claim_text"]}) != s["claim_text_sha256"]:
            raise ValueError(f"CLAIM_TEXT_HASH_MISMATCH: {s['sample_id']}")
        item = rl.RelevanceRequestItem(claim_id=s["claim_id"], alpha_id=s["target_alpha_id"], ticker=s["ticker"], claim_text=s["claim_text"],
                                       claim_text_sha256=s["claim_text_sha256"], definition=definition)
        (lone if s["sample_id"] in isolate else items).append(item)
        by_key[item.key] = s["sample_id"]
    batches = []
    for index, batch in enumerate([*rl.chunk_items(items, batch_size), *([item] for item in lone)], start=1):
        payload = rl.batch_payload(batch)
        batches.append({"batch_id": f"B{index:02d}", "alpha_id": batch[0].alpha_id, "sample_ids": [by_key[i.key] for i in batch],
                        "items": len(batch), "payload_sha256": sha256_canonical_json(payload), "prompt_chars": len(rl.build_prompt(payload))})
    return batches


def estimate_basis(reference: Mapping[str, Any]) -> Mapping[str, Any]:
    """The measured rates a plan's estimates and cost guard use: this task's own real calls (``basis``, session 4) when the plan was
    built on them, else the reference-task analogy (``stance``, the first plan)."""
    return reference.get("basis") or reference["stance"]


def _estimates(batches: Sequence[Mapping[str, Any]], basis: Mapping[str, Any], *, max_output_tokens: int, timeout_seconds: float) -> dict[str, Any]:
    rates = estimate_basis(basis)
    cpt = rates["chars_per_input_token"]
    out = rates["output_tokens_per_item"]
    lat = rates["latency_seconds_per_item"]
    chars = sum(b["prompt_chars"] for b in batches)
    items = sum(b["items"] for b in batches)
    requests = len(batches)
    return {
        "requests": requests, "items": items, "prompt_chars": chars,
        "input_tokens": {"central": round(chars / cpt["median"]), "low": round(chars / cpt["max"]), "high": round(chars / cpt["min"])},
        # the high estimate never exceeds the hard bound: every request's billed output is capped at max_output_tokens (session 4)
        "output_tokens": {"central": round(items * out["median"]), "high": min(round(items * out["max"] * OUTPUT_HIGH_MULTIPLIER), requests * max_output_tokens),
                          "hard_bound": requests * max_output_tokens},
        "latency_seconds": {"central": round(items * lat["median"]), "worst_case": round(requests * timeout_seconds)},
    }


def _prices(provider: str, model: str) -> dict[str, Any] | None:
    from comqutor_alpha.llm import cost_basis  # noqa: PLC0415

    key = (provider, model)
    off = cost_basis._PRICING_USD_PER_MILLION_TOKENS.get(key)  # noqa: SLF001
    if off is None:
        return None
    peak = cost_basis._PEAK_PRICING_USD_PER_MILLION_TOKENS.get(key) or off  # noqa: SLF001
    hit = cost_basis._CACHE_HIT_INPUT_USD_PER_MILLION_TOKENS.get(key)  # noqa: SLF001
    source = getattr(cost_basis, "PRICING_SOURCE", {})
    return {"off_peak": list(off), "peak": list(peak), "cache_hit_input": {"off_peak": hit[0], "peak": hit[1]} if hit else None,
            "unit": "USD per million tokens (input, output)", "source": source.get(key) if isinstance(source, Mapping) and key in source else source}


def usd(prices: Sequence[float], input_tokens: float, output_tokens: float) -> float:
    return round(input_tokens / 1e6 * prices[0] + output_tokens / 1e6 * prices[1], 4)


def _cost(total: Mapping[str, Any], provider: str, model: str) -> dict[str, Any]:
    prices = _prices(provider, model)
    if prices is None:
        return {"status": "NO_PRICE_ON_RECORD", "provider": provider, "model": model}
    inp, outp = total["input_tokens"], total["output_tokens"]
    return {
        "status": "ESTIMATE", "prices": prices,
        "central_usd": {"off_peak": usd(prices["off_peak"], inp["central"], outp["central"]), "peak": usd(prices["peak"], inp["central"], outp["central"])},
        "high_usd_peak": usd(prices["peak"], inp["high"], outp["high"]),
        "hard_bound_usd_peak": usd(prices["peak"], inp["high"], outp["hard_bound"]),
        "assumptions": [
            "no provider cache hit is assumed (a hit only lowers the input price)",
            "billed output includes the hidden reasoning tokens",
            "the hard bound holds only if the provider enforces max_tokens; see reference.max_tokens_enforcement",
        ],
    }


PENDING_THRESHOLDS = {
    "status": "PENDING_OWNER_CONFIRMATION",
    "rule": ("proposed before any model result exists and frozen into the plan hash. They take effect only if the owner confirms them in "
             "the authorization, i.e. before the execution; changing them later requires a new plan. Not copied from the old Alpha "
             "classifier gates."),
    "thresholds": [
        {"id": "Q1", "metric": "valid return rate (JUDGED + UNRESOLVED) over ALL round-1 planned pairs; not sent counts as invalid",
         "metric_key": "round_1.valid_return_rate", "comparator": ">=", "value": 0.95, "min_n": 1,
         "why": "the output contract is mechanical; below 95% the label is unusable before quality is even asked"},
        {"id": "Q2", "metric": "round-1 pairs FAILED by the task's own contract checks (illegal label, identity, anchors, duplicate, missing)",
         "metric_key": "round_1.contract_failures", "comparator": "<=", "value": 2, "min_n": 1,
         "why": "a contract violation means the prompt is misread; provider errors and timeouts are reported separately"},
        {"id": "Q3", "metric": "UNRESOLVED share of owner-confirmed DETERMINED pairs",
         "metric_key": "reference.unresolved_share_on_determined", "comparator": "<=", "value": 0.15, "min_n": 20,
         "why": "UNRESOLVED is for real ambiguity, not a way to avoid answering"},
        {"id": "Q4", "metric": "exact tier agreement on owner-confirmed DETERMINED pairs; FAILED, UNRESOLVED and not sent count as not agreeing",
         "metric_key": "reference.unconditional_agreement", "comparator": ">=", "value": 0.70, "min_n": 20,
         "why": "four ordered tiers with a thin strong layer; a go / no-go for a larger evaluation (reported with its 95% Wilson interval), never a production gate"},
        {"id": "Q5", "metric": "pairs the owner confirmed as core that the model judged 'none'",
         "metric_key": "reference.none_on_core", "comparator": "<=", "value": 0, "min_n": 1,
         "why": "a core pair read as unrelated is the error that would most distort a later weight"},
        {"id": "Q6", "metric": "identical state and tier in both calls, over repeat-subset pairs valid (JUDGED / UNRESOLVED) in both calls",
         "metric_key": "repeat.identical_share_valid_in_both", "comparator": ">=", "value": 0.90, "min_n": 10,
         "why": "a label that flips on identical input cannot carry a weight"},
        {"id": "Q7", "metric": "what the model answered on owner-confirmed UNRESOLVED pairs", "metric_key": None, "comparator": None,
         "value": None, "min_n": None, "why": "too few ambiguous pairs for a rate: reported case by case, no gate"},
    ],
    "sample_size_note": ("with about 40 determined reference pairs a 0.70 agreement has a 95% interval of roughly +/-0.14: these gates "
                         "answer 'is a larger evaluation worth running', never 'may this label become a weight'"),
}


# session 4 (2026-10-12): a development-set retest carries no quality gate -- its cases were chosen from earlier errors, so a rate over
# them says nothing about the task in general; the result is read case by case against the pre-registered checks.
RETEST_THRESHOLDS = {
    "status": "NOT_APPLICABLE_DEVELOPMENT_RETEST",
    "rule": ("a development-set retest applies no quality threshold: its cases were chosen from the first real run's disagreements, "
             "flips and a few agreeing controls, so no rate over them is a property of the task; each case is read against its "
             "pre-registered check. Not an independent validation and not an acceptance."),
    "thresholds": [],
}


def stop_conditions(request_cap: int, timeout_seconds: float) -> dict[str, Any]:
    return {
        "request_cap": request_cap,
        "max_retries": 0,
        "consecutive_failed_batches": 3,
        "failed_batch_means": "no pair of the batch came back JUDGED or UNRESOLVED",
        "provider_refusal": "the first provider refusal (HTTP 401 / 403 / 429) stops the whole execution",
        "cost_limit": "before each request: cost already billed (peak price) + this request's hard bound must stay within the authorized max_cost_usd",
        "wall_clock_limit_minutes": int(-(-request_cap * timeout_seconds // 60)) + 10,
        "scope": "a failed or unsent batch is never re-sent; no pair, batch or round is ever added; nothing is re-planned during the run",
        "pre_run": "refused on any mismatch of plan hash, manifest hash, authorization, code identity, definitions, sources, provider/model or request payloads",
    }


def build_plan(
    manifest: Mapping[str, Any],
    definitions: Mapping[str, AlphaRelevanceDefinition],
    *,
    manifest_file_sha256: str,
    reference: Mapping[str, Any],
    provider: str,
    model: str,
    batch_size: int,
    repeat_every: int,
    timeout_seconds: float,
    max_output_tokens: int,
    repo_root: Path | str = ".",
    model_identity_note: Mapping[str, Any] | None = None,
    repeat_sample_ids: Sequence[str] | None = None,
    purpose: str | None = None,
    purpose_kind: str | None = None,
    experiment_config: str | None = None,
    quality_thresholds: Mapping[str, Any] | None = None,
    pre_registered: Mapping[str, Any] | None = None,
    isolate: Sequence[str] | None = None,
    not_sent: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """The offline execution plan. Round 2 re-sends, with the IDENTICAL payload, the round-1 batches whose 0-based index is a multiple of
    ``repeat_every``; the plan states which batches that actually is (``rounds[1].purpose``, ``requests.repeat_batches``).

    Session 4 (2026-10-12), all optional (a plan built without them is the same as before): ``repeat_sample_ids`` repeats instead the
    round-1 batches that hold those samples; ``purpose`` / ``purpose_kind`` state what the execution is for; ``experiment_config``
    binds the plan to one evaluation configuration; ``quality_thresholds`` replaces the pending thresholds (``RETEST_THRESHOLDS`` for
    a development retest); ``pre_registered`` freezes what the result will be read against (e.g. the engineering expectations'
    file hash) into the plan hash before anything is sent. Session 6: ``isolate`` sends those samples alone; ``not_sent`` (each with a
    reason and its evidence) keeps samples in the plan's sample table without sending them -- they are reported as NOT_SENT, never as
    an answer."""
    not_sent = [{"sample_id": str(e["sample_id"]), "reason": str(e["reason"]), "evidence": str(e.get("evidence") or "")} for e in not_sent or ()]
    if any(not e["reason"].strip() for e in not_sent):
        raise ValueError("NOT_SENT_REASON_MISSING")
    round1 = plan_batches(manifest, definitions, batch_size=batch_size, isolate=isolate or (), exclude=[e["sample_id"] for e in not_sent])
    if repeat_sample_ids is None:
        repeat = [dict(b, batch_id=f"R{b['batch_id']}") for i, b in enumerate(round1) if i % max(int(repeat_every), 1) == 0]
        repeat_purpose = repeat_description(round1, repeat)
    else:
        wanted = {str(s) for s in repeat_sample_ids}
        unknown = sorted(wanted - {s for b in round1 for s in b["sample_ids"]})
        if unknown:
            raise ValueError(f"REPEAT_SAMPLE_NOT_IN_PLAN: {','.join(unknown)}")
        repeat = [dict(b, batch_id=f"R{b['batch_id']}") for b in round1 if wanted & set(b["sample_ids"])]
        repeat_purpose = f"{repeat_description(round1, repeat)}; chosen as the batches holding {', '.join(sorted(wanted))}"
    rounds = [{"round": 1, "purpose": "every sample once", "batches": round1},
              {"round": 2, "purpose": repeat_purpose, "batches": repeat}]
    cap = len(round1) + len(repeat)
    per_round = {f"round_{r['round']}": _estimates(r["batches"], reference, max_output_tokens=max_output_tokens, timeout_seconds=timeout_seconds) for r in rounds}
    total = _estimates([b for r in rounds for b in r["batches"]], reference, max_output_tokens=max_output_tokens, timeout_seconds=timeout_seconds)
    thresholds = dict(quality_thresholds if quality_thresholds is not None else PENDING_THRESHOLDS)
    own_basis = reference.get("basis_kind") == "relevance_task_own_real_calls"
    measured_on = ", ".join(f"{v} x {n}" for v, n in (reference.get("basis_prompt_versions") or {}).items())
    body = {
        "schema": PLAN_SCHEMA, "mode": "LIVE", "status": "PLANNED_NOT_EXECUTED",
        "sample_manifest": {"content_sha256": manifest["content_sha256"], "file_sha256": manifest_file_sha256, "sample_count": manifest["sample_count"]},
        "task": rl.task_identity(), "taxonomy_content_version": taxonomy_content_version(), "provider": provider, "model": model,
        "call_settings": {"batch_size": batch_size, "timeout_seconds": timeout_seconds, "max_retries": 0, "concurrency": 1,
                          "max_output_tokens": max_output_tokens, "semantic_cache": "none (every planned request reaches the provider)",
                          "sampling": "provider default: the client sets no temperature, like every Week 2 task"},
        "rounds": rounds, "request_cap": cap,
        "requests": {"round_1": len(round1), "round_2": len(repeat), "total": cap,
                     "repeat_batches": [{"batch_id": b["batch_id"], "repeats": b["batch_id"][1:], "alpha_id": b["alpha_id"], "pairs": b["items"]} for b in repeat],
                     "repeat_subset_samples": sorted({s for b in repeat for s in b["sample_ids"]}),
                     **({"repeat_selected_by_samples": sorted({str(s) for s in repeat_sample_ids})} if repeat_sample_ids is not None else {})},
        "model_identity": {
            "request_model": model,
            "pinning": "the request name selects the provider's model name; it does not pin the underlying model version",
            "observed_in_saved_real_ledgers": reference.get("model_names_observed"),
            "recorded_at_execution": ("every call keeps the requested name (request_control.request_model), the model field the provider "
                                      "returned (provider_response.response_model) and its timestamps; the execution record and the "
                                      "evaluation report summarize them with the call dates"),
            **dict(model_identity_note or {}),
        },
        "reference": reference,
        "estimate_method": {
            "input_tokens": "each planned prompt's exact character count / measured characters per billed input token of the reference task (median; range = measured min..max)",
            "output_tokens": (f"items x measured billed output per item of the reference task (median); high = items x measured max x {OUTPUT_HIGH_MULTIPLIER} "
                              "(my judgment: this prompt asks for an element analysis per item), never above the hard bound; hard bound = requests x max_output_tokens"),
            "latency": "items x measured latency per item (median); worst case = requests x timeout (sequential, no retry)",
            "cost": "token estimates x the recorded price table of comqutor_alpha/llm/cost_basis.py (off-peak and peak)",
        } if not own_basis else {
            "input_tokens": (f"each planned prompt's exact character count / measured characters per billed input token of this task's own real calls "
                             f"({measured_on}; prompts rebuilt exactly; median; range = measured min..max)"),
            "output_tokens": (f"items x measured billed output per item of this task's own real calls ({measured_on}; median); high = items x measured "
                              f"max x {OUTPUT_HIGH_MULTIPLIER} (my judgment: the planned prompt version may ask for more, e.g. quotes), never above the "
                              "hard bound; hard bound = requests x max_output_tokens"),
            "latency": "items x measured latency per item of this task's own real calls (median); worst case = requests x timeout (sequential, no retry)",
            "cost": "token estimates x the recorded price table of comqutor_alpha/llm/cost_basis.py (off-peak and peak)",
        },
        "estimates": {"per_round": per_round, "total": total},
        "cost_estimate": _cost(total, provider, model),
        "unknowns": [
            f"the basis was measured on this task's own real calls under {measured_on}; the planned prompt is "
            f"{rl.task_identity()['prompt_version']}: a longer instruction and a different output contract may change billed output and "
            "latency per item (the hard bound does not depend on them)",
            "max_tokens enforcement is measured on those calls (see reference.max_tokens_enforcement), not guaranteed by the provider",
            "prices were recorded on the date in prices.source; the provider may have changed them; peak and off-peak hours differ",
            "a response cut at max_output_tokens (finish_reason length) or a timeout is a FAILED batch, never retried",
            "repeat consistency is measured under the provider's default sampling (no temperature is set); it is not a property of a fixed seed",
            "the request name does not pin the served model: what serves it may differ from the first real run",
        ] if own_basis else [
            "no relevance-task request has ever reached a model: the 26 calls of phase 1 were SIMULATED (no tokens, no latency, no cost) and are not a basis",
            "the reference task differs from this one; its per-item output and latency are an analogy, not a measurement of this prompt",
            "max_tokens enforcement is measured on earlier calls of the same model (see reference.max_tokens_enforcement), not guaranteed by the provider",
            "prices were recorded on the date in prices.source; the provider may have changed them; peak and off-peak hours differ",
            "a response cut at max_output_tokens (finish_reason length) or a timeout is a FAILED batch, never retried",
            "repeat consistency is measured under the provider's default sampling (no temperature is set); it is not a property of a fixed seed",
        ],
        "stop_conditions": stop_conditions(cap, timeout_seconds),
        "quality_thresholds": thresholds, "quality_thresholds_sha256": sha256_canonical_json(thresholds),
        "code_identity": code_identity(repo_root),
        **({"purpose": {"kind": purpose_kind, "text": purpose}} if purpose is not None or purpose_kind is not None else {}),
        **({"experiment_config": experiment_config} if experiment_config is not None else {}),
        **({"pre_registered": dict(pre_registered)} if pre_registered is not None else {}),
        **({"isolated_samples": sorted(isolate)} if isolate else {}),
        **({"not_sent": not_sent, "not_sent_count": len(not_sent)} if not_sent else {}),
        **({"sample_table": _sample_table(manifest, round1, not_sent)} if isolate or not_sent else {}),
    }
    return {**body, "plan_sha256": sha256_canonical_json(body)}


def _sample_table(manifest: Mapping[str, Any], round1: Sequence[Mapping[str, Any]], not_sent: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Every sample of the manifest with what the plan does with it: the round-1 request that carries it, or NOT_SENT with the reason."""
    batch_of = {sid: b["batch_id"] for b in round1 for sid in b["sample_ids"]}
    reasons = {e["sample_id"]: e["reason"] for e in not_sent}
    return [{"sample_id": s["sample_id"], "status": "NOT_SENT" if s["sample_id"] in reasons else "PLANNED", "round_1_batch": batch_of.get(s["sample_id"]),
             "reason": reasons.get(s["sample_id"])} for s in sorted(manifest["samples"], key=lambda s: s["sample_id"])]


def model_names_in_calls(calls: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Per recorded call: the model name that was requested and the model field the provider returned ("(no model field)" when no
    response arrived or the response carried none), with the first and last call time -- the evidence that names what actually served
    the requests on those dates."""
    requested: dict[str, int] = {}
    returned: dict[str, int] = {}
    starts, ends = [], []
    for call in calls:
        name = str(_as_mapping(call.get("request_control")).get("request_model") or call.get("model"))
        requested[name] = requested.get(name, 0) + 1
        got = _as_mapping(call.get("provider_response")).get("response_model")
        key = str(got) if got is not None else "(no model field)"
        returned[key] = returned.get(key, 0) + 1
        if call.get("started_at"):
            starts.append(str(call["started_at"]))
        if call.get("completed_at"):
            ends.append(str(call["completed_at"]))
    return {"requested": dict(sorted(requested.items())), "returned_by_provider": dict(sorted(returned.items())),
            "first_call_at": min(starts) if starts else None, "last_call_at": max(ends) if ends else None}


def repeat_description(round1: Sequence[Mapping[str, Any]], repeat: Sequence[Mapping[str, Any]]) -> str:
    """What round 2 actually re-sends, stated from the batches themselves (never from the selection rule)."""
    first_of_alpha = {}
    for batch in round1:
        first_of_alpha.setdefault(batch["alpha_id"], batch["batch_id"])
    repeated = [b["batch_id"][1:] for b in repeat]
    pairs = sum(b["items"] for b in repeat)
    if sorted(repeated) == sorted(first_of_alpha.values()):
        return f"identical repeat of the first round-1 batch of each Alpha ({len(repeat)} batches, {pairs} pairs; consistency)"
    return f"identical repeat of round-1 batches {', '.join(repeated)} ({len(repeat)} batches, {pairs} pairs; consistency)"


def plan_content_sha256(plan: Mapping[str, Any]) -> str:
    return sha256_canonical_json({k: v for k, v in plan.items() if k != "plan_sha256"})


def suggested_max_cost_usd(plan: Mapping[str, Any]) -> float | None:
    bound = (plan.get("cost_estimate") or {}).get("hard_bound_usd_peak")
    return None if bound is None else float(-(-bound * 2 // 1) / 2)  # rounded up to the next half dollar


def authorization_template(plan: Mapping[str, Any]) -> dict[str, Any]:
    """What the owner fills in to authorize the LIVE execution of THIS plan, once, and nothing else."""
    return {
        "schema": AUTHORIZATION_SCHEMA, "mode": "LIVE", "live_authorized": False,
        "plan_sha256": plan["plan_sha256"], "sample_manifest_content_sha256": plan["sample_manifest"]["content_sha256"],
        "provider": plan["provider"], "model": plan["model"], "max_requests": plan["request_cap"],
        "max_cost_usd": None, "suggested_max_cost_usd": suggested_max_cost_usd(plan),
        "quality_thresholds_sha256": plan["quality_thresholds_sha256"], "quality_thresholds_confirmed": False,
        "valid_until": None, "authorized_by": None, "authorized_at": None,
        "statement": ("I authorize real requests of the alpha_relevance_judge task for this plan only, once, up to max_requests and "
                      "max_cost_usd, with no retry."),
        "how_to_authorize": ("set live_authorized to true; fill max_cost_usd (a number), valid_until and authorized_at (ISO 8601 with a "
                             "time zone) and authorized_by; set quality_thresholds_confirmed to true only if you accept the plan's "
                             "proposed thresholds as they are; change nothing else"),
    }


def rehearsal_authorization(plan: Mapping[str, Any], *, authorized_by: str, authorized_at: str, valid_until: str) -> dict[str, Any]:
    """A SIMULATED rehearsal of the plan (simulated provider, TEST DATA). It can never authorize a LIVE execution."""
    return {
        "schema": AUTHORIZATION_SCHEMA, "mode": "SIMULATED_REHEARSAL", "rehearsal_authorized": True, "live_authorized": False,
        "plan_sha256": plan["plan_sha256"], "sample_manifest_content_sha256": plan["sample_manifest"]["content_sha256"],
        "max_requests": plan["request_cap"], "quality_thresholds_sha256": plan["quality_thresholds_sha256"], "quality_thresholds_confirmed": False,
        "valid_until": valid_until, "authorized_by": authorized_by, "authorized_at": authorized_at,
        "statement": "SIMULATED rehearsal of the execution plan: no model, every answer is TEST DATA.",
    }


# ----------------------------------------------------------------------------------------------------------- development retest (session 4)
def build_retest_manifest(original: Mapping[str, Any], entries: Sequence[Mapping[str, Any]], *, purpose: str,
                          repaired: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """A development-set retest sample: an EXACT subset of an existing manifest. Every sample object (id, source run, claim text, hashes,
    selection metadata) is copied unchanged; the only addition is its ``retest`` tag -- the category and what the case checks. No sample
    is created, re-identified or relabelled, and no answer (reference or expected) is put into the manifest."""
    if manifest_content_sha256(original) != original.get("content_sha256"):
        raise ValueError("ORIGINAL_MANIFEST_HASH_MISMATCH")
    by_id = {s["sample_id"]: s for s in original["samples"]}
    for r in repaired:  # session 6: a repaired sample (own id, own claim id, source provenance) of a sample of this manifest
        if not r.get("repair") or r["repair"].get("original_sample_id") not in by_id or r["sample_id"] in by_id:
            raise ValueError(f"REPAIRED_SAMPLE_INVALID: {r.get('sample_id')}")
        by_id = {**by_id, r["sample_id"]: dict(r)}
    chosen: dict[str, dict[str, Any]] = {}
    for entry in entries:
        sid = str(entry["sample_id"])
        if sid not in by_id:
            raise ValueError(f"UNKNOWN_SAMPLE: {sid}")
        if sid in chosen:
            raise ValueError(f"DUPLICATE_SAMPLE: {sid}")
        if not str(entry.get("category") or "").strip() or not str(entry.get("checks") or "").strip():
            raise ValueError(f"RETEST_TAG_MISSING: {sid}")
        chosen[sid] = {**by_id[sid], "retest": {"category": str(entry["category"]), "checks": str(entry["checks"])}}
    samples = [chosen[sid] for sid in sorted(chosen)]
    categories: dict[str, int] = {}
    for s in samples:
        categories[s["retest"]["category"]] = categories.get(s["retest"]["category"], 0) + 1
    body = {
        "schema": SAMPLE_SCHEMA, "seed": original.get("seed"), "task": rl.task_identity(),
        "elements_file_sha256": _sha256_bytes(Path(ELEMENTS_PATH).read_bytes()), "taxonomy_file_sha256": _sha256_bytes(Path(TAXONOMY_PATH).read_bytes()),
        "taxonomy_content_version": taxonomy_content_version(),
        "derived_from": {"sample_manifest_content_sha256": original["content_sha256"], "sample_count": original.get("sample_count"),
                         "rule": "exact subset: each sample object is copied unchanged; only the retest tag is added",
                         **({"repaired": ("a repaired sample is a separate object with its own sample id and claim id, read from the saved source "
                                          "named in its 'repair' provenance; the sample it repairs is unchanged")} if repaired else {})},
        "retest": {"purpose_kind": RETEST_PURPOSE_KIND, "purpose": purpose, "categories": dict(sorted(categories.items())),
                   **({"repaired_samples": sorted(s["sample_id"] for s in samples if s.get("repair"))} if any(s.get("repair") for s in samples) else {})},
        "sample_count": len(samples), "samples": samples,
        "use": ("development-set retest only: the cases were chosen from earlier disagreements, flips and agreeing controls; the result is "
                "not representative, not an independent validation and not an acceptance"),
    }
    return {**body, "content_sha256": sha256_canonical_json(body)}


def review_sheet_subset(sheet_text: str, sample_ids: Sequence[str]) -> tuple[str, dict[str, Any]]:
    """The rows of a filled review sheet for the given samples, every field copied unchanged (same columns, same order). Returns the
    CSV text and a check that each kept row equals its original row field by field. Nothing is filled in or changed."""
    reader = csv.DictReader(io.StringIO(sheet_text.lstrip("\ufeff")))
    columns = list(reader.fieldnames or [])
    wanted = {str(s) for s in sample_ids}
    rows = [dict(row) for row in reader if str(row.get("sample_id") or "").strip() in wanted]
    found = [str(r["sample_id"]).strip() for r in rows]
    missing = sorted(wanted - set(found))
    duplicates = sorted({s for s in found if found.count(s) > 1})
    if missing or duplicates:
        raise ValueError(f"REVIEW_SUBSET_ROWS: missing {missing}, duplicated {duplicates}")
    text = render_csv(rows, columns)
    again = {str(r["sample_id"]).strip(): r for r in csv.DictReader(io.StringIO(text.lstrip("﻿")))}
    identical = all(again[str(r["sample_id"]).strip()] == r for r in rows)
    return text, {"columns": columns, "rows": len(rows), "every_field_identical_to_source": identical}


def write_json(path: Path | str, value: Any) -> str:
    text = json.dumps(value, indent=1, ensure_ascii=False) + "\n"
    Path(path).write_text(text, encoding="utf-8")
    return _sha256_bytes(text.encode("utf-8"))


__all__ = [
    "AUTHORIZATION_SCHEMA",
    "CODE_IDENTITY_FILES",
    "DEFAULT_QUOTAS",
    "PENDING_THRESHOLDS",
    "PLAN_SCHEMA",
    "RETEST_PURPOSE_KIND",
    "RETEST_THRESHOLDS",
    "REVIEW_COLUMNS",
    "REVIEW_FILL_COLUMNS",
    "REVIEW_INSTRUCTIONS",
    "REVIEW_STATUSES",
    "SAMPLE_SCHEMA",
    "STRATUM_PRIORITY",
    "Candidate",
    "authorization_template",
    "blind_review_rows",
    "build_manifest",
    "build_plan",
    "build_repaired_sample",
    "build_retest_manifest",
    "canonical_json_text",
    "code_identity",
    "draft_label_rows",
    "estimate_basis",
    "input_quality_rows",
    "is_original_run_dir",
    "measure_reference_ledgers",
    "measure_relevance_ledgers",
    "plan_batches",
    "plan_content_sha256",
    "rehearsal_authorization",
    "model_names_in_calls",
    "render_csv",
    "repeat_description",
    "render_definitions_markdown",
    "repaired_text_from_source",
    "review_sheet_subset",
    "scan_candidates",
    "select_sample",
    "source_match",
    "stop_conditions",
    "suggested_max_cost_usd",
    "usd",
    "verify_manifest_sources",
    "write_json",
]
