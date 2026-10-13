"""P4 phase 1 (2026-10-12): the independent Alpha relevance judgment task -- experimental, default off.

For one (claim, already-selected Alpha) pair the model reports how substantively the claim engages THAT Alpha's own definition: one of
four tiers -- ``core``, ``strong``, ``weak``, ``none`` -- or ``UNRESOLVED`` when it cannot tell. The judgment unit is the claim plus the
Alpha its match already committed to; an unmatched claim is never sent and no Alpha is enumerated or chosen here.

Responsibility split (as in ``content_support_llm`` and ``evidence_stance_llm``):
  * LLM = semantic authority: which definition ELEMENTS the claim engages, and therefore the tier.
  * This module = contract authority only: identity (the request's claim_id + alpha_id), vocabulary (two outcomes, four tiers),
    anchors (element ids of THIS Alpha), the tier/anchor consistency the criterion implies (core needs a core-owned anchor; strong has
    only strong-eligible anchors; weak and none have none), duplicates and missing results. It never re-judges a valid answer.

Criterion ``alpha_relevance_criterion.exp1`` (P4 phase 1, prompt v1, output v1 -- retired 2026-10-12, kept so its recorded judgments
verify as v1): Q1 first; true synonyms are the same element, broader/narrower concepts, indicators, proxies and consequences are not;
numbers, YoY/QoQ, time span, direction, truth, confidence and company attribution never decide a tier; an undeterminable ownership is
UNRESOLVED, never guessed.

Criterion ``alpha_relevance_criterion.exp2`` (current, prompt v2, output v2; the owner's experimental rules after the first real run --
not an A9 approval; taxonomy and element ownership unchanged):
  A. an explicit subcategory whose SAME property is stated is the element (AI memory demand states semiconductor demand); one element
     never implies another; a backlog / share / probability / estimate / indicator is judged for the object, property or expectation it
     actually states; a forecast is not the event and an indicator does not prove the quantity moved; an explicit statement of a
     definition variable counts on its own even next to an indicator;
  B. core needs locatable evidence: every anchor carries a quote of the claim's own words (checked here); nothing is supplied from
     general knowledge; a stated strong element without core evidence is strong; UNRESOLVED only when missing context would change the
     tier, naming what is missing;
  C. a background or contrast passage counts when it states the element's state, change or relation; a bare name, modifier, setting or
     scene does not;
  D. weak = a direct topical or semantic link to THIS definition without a stated element; the same industry alone is not a link;
     none = no link; a missing keyword is never the reason for none.

Criterion ``alpha_relevance_criterion.exp3`` (current, prompt v3, input v2, output v3; owner decisions of 2026-10-12, session 6 --
experimental, not an A9 approval; taxonomy and element ownership unchanged): the model no longer returns core / strong. It lists the
claim's explicit statements that bear on the definition -- each with its quote, object, property, mode (assertion, forecast,
probability, condition, negation, question, recommendation), the element it may state and whether it states it (object, property and
scope must all match; forecasts, probabilities, conditions and negations about an element can state it, the mode is recorded and never
rewritten as an event) -- and, only when nothing is stated, the semantic weak / none, or UNRESOLVED with what is missing. This module
then derives core / strong from the confirmed element ownership (Q1). Element hints (``alpha_relevance_hints_v1.json``) are sent as
semantic hints, never automatic hits; mechanical text notes (an unclosed parenthesis ...) are sent as hints of possible
incompleteness, never as a rejection. The contract checks structure, identity, quotes and ownership only -- never semantic correctness.

Not wired into the research pipeline: no live caller and no execution profile lists the task; the only entry
(``comqutor_alpha.alpha_relevance_experiment``) refuses to run unless an experiment configuration explicitly enables it. The shared
``Week2LLMGateway`` is used through its prebuilt-prompt seam (``invoke_prebuilt_json_prompt``, the Phase 1B.1 precedent), so no
existing task's prompt or table entry changes. Nothing here produces or consumes a weight.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from comqutor_alpha.alpha_library.alpha_relevance_elements import (
    ELEMENTS_VERSION,
    HINTS_PATH,
    OWNERSHIP_CORE,
    OWNERSHIP_STRONG,
    AlphaRelevanceDefinition,
    RelevanceHints,
    canonical_json_text,
    load_relevance_hints,
    sha256_text,
)
from comqutor_alpha.graph_engine.company_attribution import attribution_text

LLM_TASK_NAME = "alpha_relevance_judge"
# 2026-10-12 (P4 phase 2, after the first real run): criterion exp2 + prompt v2 + output contract v2 (anchor evidence quotes) are
# current. The v1 identity stays registered so judgments recorded under it keep verifying AS v1 -- they are never relabelled v2.
PROMPT_VERSION_V1 = "alpha_relevance.judge.prompt.v1"
PROMPT_VERSION_V2 = "alpha_relevance.judge.prompt.v2"
PROMPT_VERSION_V3 = "alpha_relevance.judge.prompt.v3"
OUTPUT_SCHEMA_V1 = "alpha_relevance.judge.output.v1"
OUTPUT_SCHEMA_V2 = "alpha_relevance.judge.output.v2"
OUTPUT_SCHEMA_V3 = "alpha_relevance.judge.output.v3"
CRITERION_EXP1 = "alpha_relevance_criterion.exp1"
CRITERION_EXP2 = "alpha_relevance_criterion.exp2"
CRITERION_EXP3 = "alpha_relevance_criterion.exp3"
INPUT_SCHEMA_V1 = "alpha_relevance.judge.input.v1"
INPUT_SCHEMA_V2 = "alpha_relevance.judge.input.v2"  # input v1 + the element hints (and their version) + mechanical text notes per item
# 2026-10-12, session 6: criterion exp3 / prompt v3 / input v2 / output v3 are current; v1 and v2 stay registered and verifiable.
PROMPT_VERSION = PROMPT_VERSION_V3
INPUT_SCHEMA_VERSION = INPUT_SCHEMA_V2
OUTPUT_SCHEMA_VERSION = OUTPUT_SCHEMA_V3
CRITERION_VERSION = CRITERION_EXP3
TAXONOMY_VERSION = "alpha_taxonomy_v1"

TIER_CORE = "core"
TIER_STRONG = "strong"
TIER_WEAK = "weak"
TIER_NONE = "none"
TIERS = (TIER_CORE, TIER_STRONG, TIER_WEAK, TIER_NONE)
OUTCOME_DETERMINED = "DETERMINED"
OUTCOME_UNRESOLVED = "UNRESOLVED"
OUTCOMES = (OUTCOME_DETERMINED, OUTCOME_UNRESOLVED)

# judgment states -- only JUDGED carries a tier; every other state has tier = None (never "none")
STATE_UNJUDGED = "UNJUDGED"
STATE_JUDGED = "JUDGED"
STATE_UNRESOLVED = "UNRESOLVED"
STATE_FAILED = "FAILED"
STATES = (STATE_UNJUDGED, STATE_JUDGED, STATE_UNRESOLVED, STATE_FAILED)

# failure reasons -- the stance / content-support vocabulary where it already exists, plus the tier/anchor rules of this task
FAILURE_PROVIDER_ERROR = "provider_error"
FAILURE_TIMEOUT = "timeout"
FAILURE_BUDGET_EXHAUSTED = "budget_exhausted"
FAILURE_PROVIDER_STOPPED = "provider_stopped"
FAILURE_INPUT_TOO_LARGE = "input_too_large"
FAILURE_MALFORMED_RESPONSE = "malformed_response"
FAILURE_MISSING_RESULT = "missing_result"
FAILURE_DUPLICATE_RESULT = "duplicate_result"
FAILURE_IDENTITY_MISMATCH = "identity_mismatch"
FAILURE_INVALID_LABEL = "invalid_label"
FAILURE_ANCHOR_INVALID = "anchor_invalid"
FAILURE_TIER_ANCHOR_INCONSISTENT = "tier_anchor_inconsistent"
FAILURE_DEFINITION_UNAVAILABLE = "definition_unavailable"
FAILURE_EVIDENCE_INVALID = "evidence_invalid"  # output v2: an anchor without a quote, a quote of no anchor, or words not in the claim

BATCH_SIZE = 8
MAX_PROMPT_CHARS = 200_000
MAX_BASIS_CHARS = 600
MAX_UNRESOLVED_REASON_CHARS = 300
RESPONSE_FIELDS_V1 = ("claim_id", "alpha_id", "outcome", "tier", "anchor_element_ids", "basis", "unresolved_reason")
RESPONSE_FIELDS_V2 = (*RESPONSE_FIELDS_V1, "anchor_evidence")
RESPONSE_FIELDS_V3 = ("claim_id", "alpha_id", "outcome", "statements", "no_hit_tier", "basis", "unresolved_reason")
RESPONSE_FIELDS = RESPONSE_FIELDS_V3
STATEMENT_FIELDS = ("quote", "object", "property", "mode", "element_id", "hit", "why")
STATEMENT_MODES = ("assertion", "forecast", "probability", "condition", "negation", "question", "recommendation")
NO_HIT_TIERS = (TIER_WEAK, TIER_NONE)
MAX_STATEMENTS = 12
MAX_STATEMENT_FIELD_CHARS = 200  # object, property
MAX_WHY_CHARS = 400
TIER_SOURCE_OWNERSHIP = "element_ownership_q1"  # core / strong derived by this module from the hit elements' ownership
TIER_SOURCE_MODEL_NO_HIT = "model_no_hit"  # weak / none: the model's semantic judgment when no element is stated
MAX_QUOTE_CHARS = 200
MIN_QUOTE_CHARS = 3

PROMPT_TEXT_V1 = """You judge how substantively ONE claim engages ONE investment thesis ("Alpha") that was ALREADY matched to it.
You do not choose an Alpha, you do not judge whether the claim is true, and you never invent elements.

Input: "alpha_definitions" gives each Alpha's own definition (core thesis, trigger signals, confirmation signals, invalidation
conditions) and its ELEMENTS -- the named variables or relations those lists state. Each element is either
  - CORE-OWNED (ownership "core"): it has a head occurrence in the core thesis, a trigger signal or an invalidation condition, or
  - STRONG-ELIGIBLE (ownership "strong"): its head occurrences are only in confirmation signals.
"shadowed_confirmation_entries" are confirmation entries that name a core-owned element: they can never make a claim "strong".
"related_not_merged" lists near-identical elements that are deliberately DIFFERENT elements. "items" are the claims to judge;
"claim_text_sha256" and "alpha_definition_sha256" are bookkeeping identifiers -- ignore them.

For each item decide which elements of ITS alpha_id the claim ENGAGES. A claim engages an element when its content is ABOUT that
element: it asserts, reports, measures, forecasts, conditions on, negates or asks about the element's state or change. An element
whose name only appears as a label, a denominator, a qualifier or a shared word is NOT engaged. A relation element is engaged only
when the claim states the relation itself, not when it states one side of it.

Tier (Q1 first -- when a claim engages both a core-owned and a strong-eligible element, the tier is core):
  - "core": the claim engages at least one core-owned element.
  - "strong": the claim engages at least one strong-eligible element and no core-owned element.
  - "weak": the claim engages no element but is topically related to the Alpha (it mentions an element without engaging it, or
    discusses the Alpha's subject matter).
  - "none": the claim has no substantive relation to the Alpha's definition. Never answer "none" merely because a keyword is absent.
Identity: two expressions are the same element only if they are true synonyms of the same quantity. A broader or narrower concept,
an indicator, a proxy or a consequence of a quantity is a DIFFERENT element (orders are not demand, backlog is not orders, estimates
are not earnings).
These never decide the tier: the size of a number, year-over-year or quarter-over-quarter comparisons, the time span, the
direction (up or down, good or bad), whether the claim is true, how confident it sounds, and which company it is about.
If you cannot determine which element (if any) the claim engages -- for example its quantity is unspecified, or it is unclear
whether a proxy or the quantity itself is meant -- answer outcome "UNRESOLVED" with tier null and a short reason. Do not guess.

Return exactly one JSON object and nothing else: {"items": [ ... ]} with one entry per input item:
{"claim_id": <copied from the item>, "alpha_id": <copied from the item>, "outcome": "DETERMINED" or "UNRESOLVED",
 "tier": "core" | "strong" | "weak" | "none" | null, "anchor_element_ids": [element ids the claim engages, from that Alpha only],
 "basis": "<one or two sentences: which element the claim engages, and why>", "unresolved_reason": "<short reason>" or null}
Rules: tier is null exactly when outcome is "UNRESOLVED"; "core" needs at least one core-owned anchor; "strong" has only
strong-eligible anchors; "weak" and "none" have no anchors; unresolved_reason is null when outcome is "DETERMINED"."""

PROMPT_TEXT_V2 = """You judge how substantively ONE claim engages ONE investment thesis ("Alpha") that was ALREADY matched to it.
You do not choose an Alpha, you do not judge whether the claim is true, and you never invent elements. Judge from the claim text
and the definitions given here only; never add facts from general knowledge.

Input: "alpha_definitions" gives each Alpha's own definition (core thesis, trigger signals, confirmation signals, invalidation
conditions, topic terms) and its ELEMENTS -- the named variables or relations those lists state. Each element is either
  - CORE-OWNED (ownership "core"): it has a head occurrence in the core thesis, a trigger signal or an invalidation condition, or
  - STRONG-ELIGIBLE (ownership "strong"): its head occurrences are only in confirmation signals.
"shadowed_confirmation_entries" are confirmation entries that name a core-owned element: they can never make a claim "strong".
"related_not_merged" lists near-identical elements that are deliberately DIFFERENT elements. "items" are the claims to judge;
"claim_text_sha256" and "alpha_definition_sha256" are bookkeeping identifiers -- ignore them.

STATING AN ELEMENT. A claim states an element when its words assert, report, measure, forecast, condition on, negate or ask about
that element's state, change or relation. Decide by what the words say, never by where a keyword appears.
  1. The same element: a true synonym, or an explicitly named subcategory of the element's object whose SAME property is stated
     ("demand for AI memory chips rose" states semiconductor demand).
  2. A different element: another property of the same object, or another object. Stating one element never implies another:
     demand does not imply inventory, prices or orders.
  3. A backlog, a market share, a probability, an expectation, an estimate, a price move or any other indicator is not
     automatically the quantity it relates to. Ask what object, property or expectation the words actually state, and whether that
     object, property or expectation is itself part of THIS Alpha's definition. A forecast or a probability is not the event having
     happened, and an indicator does not by itself show that the underlying quantity changed.
  4. If the claim ALSO states a variable of the definition explicitly -- even in the same sentence as an indicator -- judge that
     statement on its own; the indicator next to it neither adds to it nor cancels it.
  5. Background and contrast still count when they actually state an element's state, change or relation ("unlike last year's
     glut, inventories are now lean" states inventory). A name used only as a label, a modifier, a setting or a scene does not
     ("as cloud budgets were debated, the firm launched a chip" does not state cloud spending).
  6. A relation element is stated only when the claim states the relation itself, not one side of it.

EVIDENCE. Every anchor needs at least one quote: words copied EXACTLY from that item's claim_text that state the element. Never
anchor an element by inference from general knowledge -- "a product roadmap implies demand" or "retail traders' price calls imply
positioning" are not evidence.

TIER (Q1 first -- when a core-owned and a strong-eligible element are both stated, the tier is core):
  - "core": at least one core-owned element is stated, with a quote.
  - "strong": at least one strong-eligible element is stated, with a quote, and no core-owned element is. A clearly stated
    strong-eligible element with no core evidence is "strong", not UNRESOLVED.
  - "weak": no element is stated, but the claim has a direct topical or semantic link to THIS Alpha's definition (its thesis,
    signals, elements or topic terms). Belonging to the same industry, sector or asset class is not enough by itself.
  - "none": no such link. Never answer "none" merely because a keyword is absent.

UNRESOLVED: answer outcome "UNRESOLVED" (tier null) only when two reasonable readings exist AND information missing from the claim --
an unclear referent, a sentence cut off mid-way, a quantity that is never named -- would change the tier. Say exactly what is
missing in unresolved_reason. Lacking core evidence is not, by itself, an ambiguity.

These never decide the tier: the size of a number, year-over-year or quarter-over-quarter comparisons, the time span, the
direction (up or down, good or bad), whether the claim is true, how confident it sounds, and which company it is about.

Return exactly one JSON object and nothing else: {"items": [ ... ]} with one entry per input item:
{"claim_id": <copied from the item>, "alpha_id": <copied from the item>, "outcome": "DETERMINED" or "UNRESOLVED",
 "tier": "core" | "strong" | "weak" | "none" | null, "anchor_element_ids": [element ids the claim states, from that Alpha only],
 "anchor_evidence": [{"element_id": <one of the anchor ids>, "quote": "<words copied exactly from claim_text>"}],
 "basis": "<one or two sentences: which element the quoted words state, or what the topical link is or why there is none>",
 "unresolved_reason": "<what is missing>" or null}
Rules: tier is null exactly when outcome is "UNRESOLVED"; "core" needs at least one core-owned anchor; "strong" has only
strong-eligible anchors; "weak" and "none" have no anchors and no evidence; every anchor has at least one quote and every quote names
one of the anchors; quotes are copied exactly from that item's claim_text, at most 200 characters each; unresolved_reason is null
when outcome is "DETERMINED"."""

PROMPT_TEXT_V3 = """You judge how ONE claim relates to ONE investment thesis ("Alpha") that was ALREADY matched to it. You do not choose an Alpha, you
do not judge whether the claim is true, and you never invent elements. Judge from the claim text and the definitions given here
only; never add facts from general knowledge.

Input: "alpha_definitions" gives each Alpha's own definition (core thesis, trigger signals, confirmation signals, invalidation
conditions, topic terms) and its ELEMENTS -- the named variables or relations those lists state. "element_hints" lists expressions
the owner has confirmed MAY state an element: a true synonym, or a subcategory of the element's object with the same property. A
hint is only a hint: the claim states the element only when the object, the property and the scope also match, and a hint word
appearing is never enough by itself. Elements are core-owned or strong-eligible; you do not need that -- the tier is derived from
the elements you find. "related_not_merged" lists near-identical elements that are deliberately DIFFERENT elements. "items" are the
claims to judge. "text_notes" are mechanical observations about a claim's text (for example an unclosed parenthesis); they only
SUGGEST the text may be incomplete -- headlines, short phrases and list items often look like this and are complete.
"claim_text_sha256" and "alpha_definition_sha256" are bookkeeping identifiers -- ignore them.

STEP 1 -- STATEMENTS. Read the whole claim and list its explicit statements that bear on THIS Alpha's definition: every statement
about a definition variable, every indicator or proxy (a backlog, a share, an estimate, a price move ...), and every other explicit
statement in the same sentence. Never stop at the first indicator: a later statement in the same sentence is listed and judged on
its own. For each statement give:
  - "quote": the words, copied exactly from claim_text, that make the statement. A label such as "Factor: X", "Theme: X",
    "Category: X" or "Signal: X" only names a topic -- quote the words that say something about it;
  - "object": what the words are about (for example "AI servers", "the company's balance sheet", "the economy");
  - "property": which property, quantity or relation of that object the words state (for example "demand", "current ratio",
    "growth");
  - "mode": how it is stated -- "assertion" (as a fact), "forecast", "probability" (odds, likelihood or risk), "condition"
    (if / when), "negation" (it is not, or will not be), "question", or "recommendation" (advice to act);
  - "element_id": the element of THIS Alpha the statement may state, or null when none comes close;
  - "hit": true only when the object, the property and the scope (the range the element covers, for example the whole economy
    rather than one sector) all match that element -- a true synonym, an explicitly named subcategory of the element's object with
    the same property, or a hint whose object, property and scope match;
  - "why": one sentence on why the object, property and scope do or do not match.
A forecast, a probability, a condition, a negation or a question about an element still states that element (hit true when it
matches); the mode records how it is stated -- never treat a forecast or a probability as the event having happened.
The same word can name a different property: "liquidity" read from a company's current ratio is balance-sheet liquidity, a
different property from market liquidity. An indicator (a backlog, a share, an estimate, a price move) states its own property,
not the quantity it relates to, unless the definition names that indicator.

STEP 2 -- OUTCOME.
  - When at least one statement has "hit" true: "outcome" "DETERMINED" and "no_hit_tier" null.
  - When no statement hits an element: "outcome" "DETERMINED" and "no_hit_tier" "weak" if the claim has a direct topical or
    semantic link to THIS Alpha's thesis -- list the linking words as a statement with "hit" false -- or "none" if it has no such
    link. A missing keyword is never by itself a reason for "none"; belonging to the same industry, sector or asset class is never
    by itself a reason for "weak".
  - "outcome" "UNRESOLVED" only when information missing from the claim -- words cut off, an unclear referent, a quantity that is
    never named -- would change whether an element is hit or the weak / none decision; say exactly what is missing in
    "unresolved_reason". Lacking evidence is not, by itself, an ambiguity.
These never decide the outcome: the size of a number, comparisons over time, the time span, the direction (up or down, good or
bad), whether the claim is true, how confident it sounds, and which company it is about.

Return exactly one JSON object and nothing else: {"items": [ ... ]} with one entry per input item:
{"claim_id": <copied from the item>, "alpha_id": <copied from the item>, "outcome": "DETERMINED" or "UNRESOLVED",
 "statements": [{"quote": "<words copied exactly from claim_text>", "object": "...", "property": "...", "mode": "...",
                 "element_id": "<element id of that Alpha>" or null, "hit": true or false, "why": "..."}],
 "no_hit_tier": "weak" | "none" | null, "basis": "<one or two sentences summarising the decision>",
 "unresolved_reason": "<what is missing>" or null}
Rules: every quote is copied exactly from that item's claim_text, at most 200 characters; a statement with "hit" true names an
element of that Alpha; "no_hit_tier" is null when a statement hits or when the outcome is UNRESOLVED, and is "weak" or "none"
otherwise; "weak" needs at least one statement with the linking words; "unresolved_reason" is null when the outcome is DETERMINED."""

PROMPT_TEXT = PROMPT_TEXT_V3
PROMPT_IDENTITY_SEPARATOR = "\n\n[INPUT JSON]\n"
# every prompt version the task knows: the current one sends requests; a retired one only verifies what was recorded under it
PROMPT_VERSIONS: dict[str, dict[str, str]] = {
    PROMPT_VERSION_V1: {"text": PROMPT_TEXT_V1, "criterion_version": CRITERION_EXP1, "output_schema_version": OUTPUT_SCHEMA_V1,
                        "input_schema_version": INPUT_SCHEMA_V1, "status": "retired 2026-10-12: verifies judgments recorded under it, never sends"},
    PROMPT_VERSION_V2: {"text": PROMPT_TEXT_V2, "criterion_version": CRITERION_EXP2, "output_schema_version": OUTPUT_SCHEMA_V2,
                        "input_schema_version": INPUT_SCHEMA_V1, "status": "retired 2026-10-12 (session 6): verifies judgments recorded under it, never sends"},
    PROMPT_VERSION_V3: {"text": PROMPT_TEXT_V3, "criterion_version": CRITERION_EXP3, "output_schema_version": OUTPUT_SCHEMA_V3,
                        "input_schema_version": INPUT_SCHEMA_V2, "status": "current"},
}
# the module-level names that together make the CURRENT version (a test that covers an older contract pins them to that version)
CURRENT_VERSION_NAMES = ("PROMPT_VERSION", "PROMPT_TEXT", "OUTPUT_SCHEMA_VERSION", "CRITERION_VERSION", "INPUT_SCHEMA_VERSION")


def version_constants(prompt_version: str) -> dict[str, str]:
    """The values of ``CURRENT_VERSION_NAMES`` that make ``prompt_version`` the current version (used to pin a test to an older contract)."""
    spec = PROMPT_VERSIONS[prompt_version]
    return {"PROMPT_VERSION": prompt_version, "PROMPT_TEXT": spec["text"], "OUTPUT_SCHEMA_VERSION": spec["output_schema_version"],
            "CRITERION_VERSION": spec["criterion_version"], "INPUT_SCHEMA_VERSION": spec["input_schema_version"]}


def prompt_identity_text(prompt_version: str | None = None) -> str:
    """``None`` = the current instruction (read when called); a registered version = the instruction recorded under it."""
    text = PROMPT_TEXT if prompt_version is None else PROMPT_VERSIONS[prompt_version]["text"]
    return f"{text}{PROMPT_IDENTITY_SEPARATOR}"


def prompt_identity_sha256(prompt_version: str | None = None) -> str:
    """The identity of the instruction itself (the input JSON excluded), recorded as the semantic call's ``prompt_sha256``."""
    return sha256_text(prompt_identity_text(prompt_version))


def build_prompt(payload: Mapping[str, Any], prompt_version: str | None = None) -> str:
    return f"{prompt_identity_text(prompt_version)}{canonical_json_text(dict(payload))}"


def claim_text_sha256(record: Mapping[str, Any]) -> str:
    """The claim text this task judges is the text the evidence contract reads (claim, else its evidence)."""
    return sha256_text(attribution_text(record))


def task_identity(prompt_version: str | None = None) -> dict[str, str]:
    """Every version a judgment is bound to (a change to any of them makes an older judgment stale). Default: the current identity
    (read from the module's versions when called); a registered version -- current or retired -- gives the identity its records were
    made under (to verify them as what they are). Input v2 sends the element hints, so their version and content hash are part of it."""
    spec = None if prompt_version is None else PROMPT_VERSIONS[prompt_version]
    identity = {
        "task": LLM_TASK_NAME,
        "prompt_version": PROMPT_VERSION if prompt_version is None else prompt_version,
        "prompt_sha256": prompt_identity_sha256(prompt_version),
        "input_schema_version": INPUT_SCHEMA_VERSION if spec is None else spec["input_schema_version"],
        "output_schema_version": OUTPUT_SCHEMA_VERSION if spec is None else spec["output_schema_version"],
        "criterion_version": CRITERION_VERSION if spec is None else spec["criterion_version"],
        "elements_version": ELEMENTS_VERSION,
    }
    if identity["input_schema_version"] == INPUT_SCHEMA_V2:
        hints = current_hints()
        identity.update({"hints_version": hints.version, "hints_sha256": hints.sha256})
    return identity


_HINTS_CACHE: dict[str, RelevanceHints] = {}


def current_hints() -> RelevanceHints:
    """The element hint register that input v2 sends, validated once per file content (a changed file is a new register)."""
    key = sha256_text(HINTS_PATH.read_text(encoding="utf-8"))
    if key not in _HINTS_CACHE:
        _HINTS_CACHE[key] = load_relevance_hints(HINTS_PATH)
    return _HINTS_CACHE[key]


_ABBREVIATION_TAIL = re.compile(r"(?:^|[\s(\[])(?:No|Nos|vs|approx|est|Fig|Vol|pp|p|St|Mr|Ms|Dr)\.$", re.IGNORECASE)


def text_completeness_notes(text: str) -> list[str]:
    """Mechanical observations that only SUGGEST a claim text may be incomplete -- sent to the model as hints, never a rejection
    (headlines, short phrases and list items are often unpunctuated and complete). A missing final full stop is deliberately not a
    note: it is far too common in complete headlines and list items."""
    value = str(text or "").rstrip()
    notes = []
    if value.count("(") > value.count(")"):
        notes.append("unclosed_parenthesis")
    if value.count("[") > value.count("]"):
        notes.append("unclosed_bracket")
    if value.count('"') % 2 == 1 or value.count("\u201c") > value.count("\u201d"):
        notes.append("unclosed_quote")
    if _ABBREVIATION_TAIL.search(value):
        notes.append("ends_with_abbreviation")
    return notes


def known_task_identities() -> list[dict[str, str]]:
    return [task_identity(version) for version in PROMPT_VERSIONS]


def is_known_task_identity(identity: Mapping[str, Any]) -> bool:
    return dict(identity) in known_task_identities()


@dataclass(frozen=True)
class RelevanceRequestItem:
    claim_id: str
    alpha_id: str
    ticker: str
    claim_text: str
    claim_text_sha256: str
    definition: AlphaRelevanceDefinition

    @property
    def key(self) -> tuple[str, str]:
        return (self.claim_id, self.alpha_id)

    @property
    def payload(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id, "alpha_id": self.alpha_id, "ticker": self.ticker, "claim_text": self.claim_text,
            "claim_text_sha256": self.claim_text_sha256, "alpha_definition_sha256": self.definition.sha256,
        }


def matched_pairs(matches: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The judgment units: matches committed to an Alpha. An unmatched claim is never given an Alpha here."""
    return [m for m in matches if isinstance(m, Mapping) and m.get("match_status") == "matched" and m.get("claim_id") and m.get("matched_alpha")]


def build_request_items(
    matches: Sequence[Mapping[str, Any]], *, ticker: str, definitions: Mapping[str, AlphaRelevanceDefinition]
) -> tuple[list[RelevanceRequestItem], list[dict[str, str]]]:
    """Request items for every matched pair, in a deterministic order; pairs whose Alpha has no definition are returned separately."""
    items: list[RelevanceRequestItem] = []
    without_definition: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for match in sorted(matched_pairs(matches), key=lambda m: (str(m["matched_alpha"]), str(m["claim_id"]))):
        key = (str(match["claim_id"]), str(match["matched_alpha"]))
        if key in seen:
            continue
        seen.add(key)
        definition = definitions.get(key[1])
        if definition is None:
            without_definition.append({"claim_id": key[0], "alpha_id": key[1], "reason": FAILURE_DEFINITION_UNAVAILABLE})
            continue
        items.append(RelevanceRequestItem(
            claim_id=key[0], alpha_id=key[1], ticker=str(ticker), claim_text=attribution_text(match),
            claim_text_sha256=claim_text_sha256(match), definition=definition,
        ))
    return items, without_definition


def chunk_items(items: Sequence[RelevanceRequestItem], size: int = BATCH_SIZE) -> list[list[RelevanceRequestItem]]:
    """Batches never mix Alphas, so each batch carries each definition once."""
    size = max(int(size), 1)
    batches: list[list[RelevanceRequestItem]] = []
    current: list[RelevanceRequestItem] = []
    for item in items:
        if current and (len(current) >= size or current[-1].alpha_id != item.alpha_id):
            batches.append(current)
            current = []
        current.append(item)
    if current:
        batches.append(current)
    return batches


def batch_payload(
    batch: Sequence[RelevanceRequestItem], *, criterion_version: str | None = None, input_schema_version: str | None = None
) -> dict[str, Any]:
    """The request payload. ``criterion_version`` / ``input_schema_version`` None = the current ones; a recorded request of an older
    version is rebuilt with what it carried. Input v2 = input v1 + each Alpha's element hints (and the register's version) + each
    item's mechanical text notes."""
    definitions: dict[str, AlphaRelevanceDefinition] = {}
    for item in batch:
        definitions.setdefault(item.alpha_id, item.definition)
    payload = {
        "task": LLM_TASK_NAME,
        "criterion_version": CRITERION_VERSION if criterion_version is None else criterion_version,
        "alpha_definitions": [{**dict(d.payload), "alpha_definition_sha256": d.sha256} for d in definitions.values()],
        "items": [item.payload for item in batch],
    }
    if (INPUT_SCHEMA_VERSION if input_schema_version is None else input_schema_version) == INPUT_SCHEMA_V2:
        hints = current_hints()
        payload["hints_version"] = hints.version
        for entry in payload["alpha_definitions"]:
            entry["element_hints"] = hints.for_alpha(entry["alpha_id"])
        for entry, item in zip(payload["items"], batch, strict=True):
            entry["text_notes"] = text_completeness_notes(item.claim_text)
    return payload


def validate_batch_shape(parsed: Any) -> list[Any]:
    """Batch-level structural validator (passed to the gateway); per-item legality is checked by ``validate_response_item``."""
    if not isinstance(parsed, Mapping):
        raise TypeError("alpha_relevance_judge response must be a JSON object")
    items = parsed.get("items")
    if not isinstance(items, list):
        raise TypeError("alpha_relevance_judge response missing an items array")
    return items


def _validate_common(
    item: RelevanceRequestItem, returned: Any, fields: Sequence[str]
) -> tuple[dict[str, Any] | None, str | None]:
    """The checks every output contract shares -- the whole of output.v1. Never re-judges a valid answer."""
    if not isinstance(returned, Mapping) or any(name not in returned for name in fields):
        return None, FAILURE_MALFORMED_RESPONSE
    if returned.get("claim_id") != item.claim_id or returned.get("alpha_id") != item.alpha_id:
        return None, FAILURE_IDENTITY_MISMATCH
    outcome, tier = returned.get("outcome"), returned.get("tier")
    if outcome not in OUTCOMES:
        return None, FAILURE_INVALID_LABEL
    if outcome == OUTCOME_DETERMINED and tier not in TIERS:
        return None, FAILURE_INVALID_LABEL
    if outcome == OUTCOME_UNRESOLVED and tier is not None:
        return None, FAILURE_INVALID_LABEL
    anchors = returned.get("anchor_element_ids")
    if not isinstance(anchors, list) or any(not isinstance(a, str) for a in anchors) or len(set(anchors)) != len(anchors):
        return None, FAILURE_MALFORMED_RESPONSE
    basis, unresolved = returned.get("basis"), returned.get("unresolved_reason")
    if not isinstance(basis, str) or not basis.strip() or len(basis) > MAX_BASIS_CHARS:
        return None, FAILURE_MALFORMED_RESPONSE
    if outcome == OUTCOME_UNRESOLVED:
        if not isinstance(unresolved, str) or not unresolved.strip() or len(unresolved) > MAX_UNRESOLVED_REASON_CHARS:
            return None, FAILURE_MALFORMED_RESPONSE
    elif unresolved not in (None, ""):
        return None, FAILURE_MALFORMED_RESPONSE
    ownership = item.definition.ownership
    if any(anchor not in ownership for anchor in anchors):
        return None, FAILURE_ANCHOR_INVALID
    if outcome == OUTCOME_DETERMINED:
        kinds = {ownership[a] for a in anchors}
        consistent = {
            TIER_CORE: OWNERSHIP_CORE in kinds,
            TIER_STRONG: bool(anchors) and kinds == {OWNERSHIP_STRONG},
            TIER_WEAK: not anchors,
            TIER_NONE: not anchors,
        }[tier]
        if not consistent:
            return None, FAILURE_TIER_ANCHOR_INCONSISTENT
    return {
        "state": STATE_JUDGED if outcome == OUTCOME_DETERMINED else STATE_UNRESOLVED,
        "tier": tier if outcome == OUTCOME_DETERMINED else None,
        "anchor_element_ids": list(anchors),
        "basis": basis.strip(),
        "unresolved_reason": unresolved.strip() if outcome == OUTCOME_UNRESOLVED else None,
    }, None


def _validate_item_v1(item: RelevanceRequestItem, returned: Any) -> tuple[dict[str, Any] | None, str | None]:
    return _validate_common(item, returned, RESPONSE_FIELDS_V1)


_QUOTE_FOLDS = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-", "\u00a0": " "})
_QUOTE_EDGES = " .,;:!?\"'()[]"


def _folded(text: str) -> str:
    return " ".join(str(text).translate(_QUOTE_FOLDS).replace("\u2026", "...").casefold().split())


def quote_in_text(quote: str, text: str) -> bool:
    """A quote is the claim's own words: found in the claim text once case, whitespace, curly quotes and dashes are folded and the
    quote's own surrounding punctuation is dropped. Nothing else is forgiven (no paraphrase, no reordering)."""
    folded = _folded(quote).strip(_QUOTE_EDGES)
    return len(folded) >= MIN_QUOTE_CHARS and folded in _folded(text)


def _validate_item_v2(item: RelevanceRequestItem, returned: Any) -> tuple[dict[str, Any] | None, str | None]:
    """output.v2 = output.v1 plus locatable evidence: every anchor is supported by at least one quote of the claim's own words,
    and every quote supports one of the anchors (criterion exp2, rule B)."""
    validated, reason = _validate_common(item, returned, RESPONSE_FIELDS_V2)
    if validated is None:
        return None, reason
    evidence = returned.get("anchor_evidence")
    if not isinstance(evidence, list) or any(
            not isinstance(e, Mapping) or not isinstance(e.get("element_id"), str) or not isinstance(e.get("quote"), str)
            or len(e["quote"]) > MAX_QUOTE_CHARS for e in evidence):
        return None, FAILURE_MALFORMED_RESPONSE
    anchors = validated["anchor_element_ids"]
    if {e["element_id"] for e in evidence} != set(anchors):
        return None, FAILURE_EVIDENCE_INVALID  # an anchor without a quote, or a quote for something that is not an anchor
    if any(not quote_in_text(e["quote"], item.claim_text) for e in evidence):
        return None, FAILURE_EVIDENCE_INVALID  # words that are not in the claim cannot locate anything in it
    validated["anchor_evidence"] = [{"element_id": e["element_id"], "quote": e["quote"].strip()} for e in evidence]
    return validated, None


def _text_field(value: Any, limit: int) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


def _validate_item_v3(item: RelevanceRequestItem, returned: Any) -> tuple[dict[str, Any] | None, str | None]:
    """output.v3 (criterion exp3): the model reports statements -- quote, object, property, mode, element, hit, why -- and, only when
    nothing is hit, the semantic weak / none. This contract checks structure, identity, vocabulary, that every quote is the claim's own
    words and every element belongs to THIS Alpha, and the hit / no-hit consistency; it then derives core / strong from the confirmed
    ownership of the hit elements (Q1). It never re-judges whether a statement really states its element."""
    if not isinstance(returned, Mapping) or any(name not in returned for name in RESPONSE_FIELDS_V3):
        return None, FAILURE_MALFORMED_RESPONSE
    if returned.get("claim_id") != item.claim_id or returned.get("alpha_id") != item.alpha_id:
        return None, FAILURE_IDENTITY_MISMATCH
    outcome, no_hit = returned.get("outcome"), returned.get("no_hit_tier")
    if outcome not in OUTCOMES or no_hit not in (None, *NO_HIT_TIERS):
        return None, FAILURE_INVALID_LABEL
    basis, unresolved = returned.get("basis"), returned.get("unresolved_reason")
    if not _text_field(basis, MAX_BASIS_CHARS):
        return None, FAILURE_MALFORMED_RESPONSE
    if outcome == OUTCOME_UNRESOLVED:
        if not _text_field(unresolved, MAX_UNRESOLVED_REASON_CHARS):
            return None, FAILURE_MALFORMED_RESPONSE
    elif unresolved not in (None, ""):
        return None, FAILURE_MALFORMED_RESPONSE
    statements = returned.get("statements")
    if not isinstance(statements, list) or len(statements) > MAX_STATEMENTS:
        return None, FAILURE_MALFORMED_RESPONSE
    ownership = item.definition.ownership
    clean: list[dict[str, Any]] = []
    for statement in statements:
        if not isinstance(statement, Mapping) or any(name not in statement for name in STATEMENT_FIELDS):
            return None, FAILURE_MALFORMED_RESPONSE
        element, hit = statement.get("element_id"), statement.get("hit")
        if (not isinstance(statement.get("quote"), str) or len(statement["quote"]) > MAX_QUOTE_CHARS or not isinstance(hit, bool)
                or not _text_field(statement.get("object"), MAX_STATEMENT_FIELD_CHARS)
                or not _text_field(statement.get("property"), MAX_STATEMENT_FIELD_CHARS)
                or not _text_field(statement.get("why"), MAX_WHY_CHARS) or (element is not None and not isinstance(element, str))):
            return None, FAILURE_MALFORMED_RESPONSE
        if statement.get("mode") not in STATEMENT_MODES:
            return None, FAILURE_INVALID_LABEL
        if (hit and element is None) or (element is not None and element not in ownership):
            return None, FAILURE_ANCHOR_INVALID
        if not quote_in_text(statement["quote"], item.claim_text):
            return None, FAILURE_EVIDENCE_INVALID
        clean.append({"quote": statement["quote"].strip(), "object": statement["object"].strip(), "property": statement["property"].strip(),
                      "mode": statement["mode"], "element_id": element, "hit": hit, "why": statement["why"].strip()})
    hits = [s for s in clean if s["hit"]]
    anchors = list(dict.fromkeys(s["element_id"] for s in hits))
    if outcome == OUTCOME_UNRESOLVED:
        if no_hit is not None:
            return None, FAILURE_TIER_ANCHOR_INCONSISTENT
        tier, source = None, None
    elif hits:
        if no_hit is not None:
            return None, FAILURE_TIER_ANCHOR_INCONSISTENT
        tier = TIER_CORE if any(ownership[a] == OWNERSHIP_CORE for a in anchors) else TIER_STRONG  # Q1: core wins
        source = TIER_SOURCE_OWNERSHIP
    else:
        if no_hit is None:
            return None, FAILURE_TIER_ANCHOR_INCONSISTENT
        if no_hit == TIER_WEAK and not clean:
            return None, FAILURE_EVIDENCE_INVALID  # weak names the words that link the claim to the thesis
        tier, source = no_hit, TIER_SOURCE_MODEL_NO_HIT
    return {
        "state": STATE_JUDGED if outcome == OUTCOME_DETERMINED else STATE_UNRESOLVED,
        "tier": tier,
        "anchor_element_ids": anchors,
        "basis": basis.strip(),
        "unresolved_reason": unresolved.strip() if outcome == OUTCOME_UNRESOLVED else None,
        "anchor_evidence": [{"element_id": s["element_id"], "quote": s["quote"], "mode": s["mode"]} for s in hits],
        "statements": clean,
        "tier_source": source,
    }, None


_VALIDATORS = {OUTPUT_SCHEMA_V1: _validate_item_v1, OUTPUT_SCHEMA_V2: _validate_item_v2, OUTPUT_SCHEMA_V3: _validate_item_v3}


def validate_response_item(
    item: RelevanceRequestItem, returned: Any, *, output_schema_version: str | None = None
) -> tuple[dict[str, Any] | None, str | None]:
    """One returned entry against its request under ONE output contract (None = the current one; a recorded call is re-checked
    under the contract it was made under): ``(validated, None)`` or ``(None, failure reason)``. An unknown contract accepts nothing."""
    validator = _VALIDATORS.get(OUTPUT_SCHEMA_VERSION if output_schema_version is None else output_schema_version)
    if validator is None:
        return None, FAILURE_MALFORMED_RESPONSE
    return validator(item, returned)


def judge_returned_items(
    batch: Sequence[RelevanceRequestItem], returned_items: Sequence[Any], *, output_schema_version: str | None = None
) -> dict[tuple[str, str], dict[str, Any]]:
    """Pair every requested item with its returned entry: missing, duplicate and unrequested entries are handled, never guessed."""
    requested = {item.key: item for item in batch}
    by_key: dict[tuple[str, str], Any] = {}
    duplicates: set[tuple[str, str]] = set()
    for returned in returned_items:
        if not isinstance(returned, Mapping):
            continue
        key = (str(returned.get("claim_id") or ""), str(returned.get("alpha_id") or ""))
        if key not in requested:
            continue  # an unrequested pair is never admitted (another claim or Alpha cannot borrow this answer)
        if key in by_key:
            duplicates.add(key)
        else:
            by_key[key] = returned
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for key, item in requested.items():
        if key in duplicates:
            out[key] = failed(FAILURE_DUPLICATE_RESULT)
        elif key not in by_key:
            out[key] = failed(FAILURE_MISSING_RESULT)
        else:
            validated, reason = validate_response_item(item, by_key[key], output_schema_version=output_schema_version)
            out[key] = validated if validated is not None else failed(reason or FAILURE_MALFORMED_RESPONSE)
    return out


def failed(reason: str) -> dict[str, Any]:
    return {"state": STATE_FAILED, "tier": None, "anchor_element_ids": [], "basis": None, "unresolved_reason": None, "failure_reason": reason}


def reason_from_invocation(invocation: Any) -> str:
    status = getattr(invocation, "provider_status", None)
    error_code = getattr(invocation, "error_code", None)
    if status == "timeout":
        return FAILURE_TIMEOUT
    if error_code == "WEEK2_LLM_RUN_STOPPED_AFTER_PROVIDER_REFUSAL":
        return FAILURE_PROVIDER_STOPPED
    if status == "budget_exhausted" or error_code == "WEEK2_LLM_CALL_BUDGET_EXHAUSTED":
        return FAILURE_BUDGET_EXHAUSTED
    if error_code == "WEEK2_LLM_INPUT_TOO_LARGE":
        return FAILURE_INPUT_TOO_LARGE
    if error_code in {"WEEK2_LLM_INVALID_JSON", "WEEK2_LLM_VALIDATION_FAILED"}:
        return FAILURE_MALFORMED_RESPONSE
    return FAILURE_PROVIDER_ERROR


@dataclass
class RelevanceRunStats:
    requested_pairs: int = 0
    batches: int = 0
    provider_attempts: int = 0
    states: dict[str, int] = field(default_factory=dict)
    failure_reasons: dict[str, int] = field(default_factory=dict)

    def record(self, result: Mapping[str, Any]) -> None:
        self.states[result["state"]] = self.states.get(result["state"], 0) + 1
        if result.get("failure_reason"):
            self.failure_reasons[result["failure_reason"]] = self.failure_reasons.get(result["failure_reason"], 0) + 1

    def as_dict(self) -> dict[str, Any]:
        return {"requested_pairs": self.requested_pairs, "batches": self.batches, "provider_attempts": self.provider_attempts,
                "states": dict(sorted(self.states.items())), "failure_reasons": dict(sorted(self.failure_reasons.items()))}


def judge_relevance(
    items: Sequence[RelevanceRequestItem],
    llm_gateway: Any,
    *,
    batch_size: int = BATCH_SIZE,
    timeout_seconds: float | None = None,
    max_retries: int | None = None,
    execution_policy_source: str | None = None,
) -> tuple[dict[tuple[str, str], dict[str, Any]], RelevanceRunStats]:
    """Send the items through the shared gateway, batch by batch, and return one result per requested pair (with the semantic
    ``call_id`` that recorded it). ``llm_gateway=None`` sends nothing and returns no results."""
    stats = RelevanceRunStats(requested_pairs=len(items))
    results: dict[tuple[str, str], dict[str, Any]] = {}
    if llm_gateway is None or not items:
        return results, stats
    identity = task_identity()
    for batch in chunk_items(items, batch_size):
        stats.batches += 1
        payload = batch_payload(batch)
        invocation = None
        finalized = False
        try:
            invocation = llm_gateway.invoke_prebuilt_json_prompt(
                task=LLM_TASK_NAME, prompt=build_prompt(payload), prompt_version=identity["prompt_version"],
                prompt_sha256=identity["prompt_sha256"], input_schema_version=identity["input_schema_version"],
                output_schema_version=identity["output_schema_version"], payload_for_identity=payload,
                validator=validate_batch_shape, taxonomy_version=TAXONOMY_VERSION, max_prompt_chars=MAX_PROMPT_CHARS,
                timeout_seconds=timeout_seconds, max_retries=max_retries, execution_policy_source=execution_policy_source,
            )
            stats.provider_attempts += int(getattr(invocation, "provider_attempt_count", 0) or 0)
            call_id = getattr(getattr(invocation, "trace_handle", None), "call_id", None)
            if not invocation.validation_accepted:
                reason = reason_from_invocation(invocation)
                finalized = True
                llm_gateway.finalize_semantic_invocation(invocation, accepted=False, fallback_reason=reason)
                batch_results = {item.key: failed(reason) for item in batch}
            else:
                batch_results = judge_returned_items(batch, invocation.validated_output or [])
                rejections = sorted({r["failure_reason"] for r in batch_results.values() if r["state"] == STATE_FAILED})
                finalized = True
                if all(r["state"] == STATE_FAILED for r in batch_results.values()):
                    llm_gateway.finalize_semantic_invocation(invocation, accepted=False, fallback_reason=",".join(rejections))
                else:
                    llm_gateway.finalize_semantic_invocation(invocation, accepted=True)
            for key, result in batch_results.items():
                results[key] = {**result, "call_id": call_id}
        except Exception:
            if invocation is not None and not finalized:
                llm_gateway.finalize_semantic_invocation(invocation, accepted=False, fallback_reason=FAILURE_PROVIDER_ERROR)
            call_id = getattr(getattr(invocation, "trace_handle", None), "call_id", None)
            for item in batch:
                results[item.key] = {**failed(FAILURE_PROVIDER_ERROR), "call_id": call_id}
        for item in batch:
            stats.record(results[item.key])
    return results, stats


__all__ = [
    "BATCH_SIZE",
    "CRITERION_VERSION",
    "CURRENT_VERSION_NAMES",
    "FAILURE_EVIDENCE_INVALID",
    "INPUT_SCHEMA_VERSION",
    "LLM_TASK_NAME",
    "OUTCOMES",
    "OUTCOME_DETERMINED",
    "OUTCOME_UNRESOLVED",
    "OUTPUT_SCHEMA_VERSION",
    "PROMPT_TEXT",
    "PROMPT_VERSION",
    "PROMPT_VERSIONS",
    "STATEMENT_MODES",
    "STATES",
    "STATE_FAILED",
    "STATE_JUDGED",
    "STATE_UNJUDGED",
    "STATE_UNRESOLVED",
    "TIERS",
    "RelevanceRequestItem",
    "RelevanceRunStats",
    "batch_payload",
    "build_prompt",
    "build_request_items",
    "chunk_items",
    "claim_text_sha256",
    "current_hints",
    "is_known_task_identity",
    "judge_relevance",
    "judge_returned_items",
    "known_task_identities",
    "matched_pairs",
    "prompt_identity_sha256",
    "quote_in_text",
    "task_identity",
    "text_completeness_notes",
    "validate_batch_shape",
    "validate_response_item",
    "version_constants",
]
