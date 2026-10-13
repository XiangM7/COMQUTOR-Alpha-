"""Negation scope of one (claim, matched Alpha) pair under ``alpha_evidence_consumption.v2`` (2026-10-13).

The text rule (``claim_semantics.analyze_claim_semantics``) marks a whole claim ``negated`` when any negator appears anywhere in
it, and ``alpha_relation`` then reads the claim as a mere ``mention`` of the Alpha, so the shared selector excludes it
(``RELATION_NOT_SUPPORTING`` / ``ASSERTION_NEGATED``). John's T3 cases and the saved NVDA run show negators that do not negate
the statement the Alpha relies on:

* a citation marker -- ``[fragmentid: not provided]`` (T3 027R, NVDA claims 8, 17, 63, ...);
* the rejected alternative of a contrast -- ``X, not Y`` (T3 006), ``It's not -- it's X``, ``not Y but X``;
* a negated protection, which affirms the risk -- ``net cash does not immunize a 167x trailing multiple from ... compression``
  (T3 005), only for the risk Alphas A304 / A501;
* a negation in another clause than the one carrying this Alpha's own matched terms -- ``Recession risk is not the threat;
  valuation and crowding are.`` (negated for A501, not for A304).

This module decides, per pair, which parts of the claim are such non-governing negations, removes exactly those parts and
re-reads the remaining text with the unchanged text rule. When a negator still governs the Alpha's statement, the stored
text-rule fields stand unchanged. Legacy records (no contract) never reach it.

Which removals need an anchor (``alpha_statement_scope.v2``, 2026-10-13). A citation marker is never statement content and a
negated protection affirms the risk by its construction, so those two are always removed. A contrast or another clause is
different: the rule cannot tell from the words alone whether this Alpha's statement is the kept part or the rejected one --
"... repricing, not a growth scare" negates the recession Alpha's own statement, "... a trailing inflection, not a forward EPS
of $15.72" does not negate the valuation Alpha's. Those removals are therefore applied only when a ledger-corroborated model
judgment says the claim supports this Alpha (``model_supports``); without it they are reported as ``not_applied`` and the
text rule's negated reading stands. The anchor only ever withholds a re-read -- a model "supports" never removes anything by
itself, so it cannot let a claim bypass this or any other gate (R-1, the source gate and the rest still apply after it).
v1 (the same day, never delivered) applied the contrast and clause removals without the anchor; on a run without a ledger
it read two such negated statements as support (AMD news claim 18 for A501, research-manager claim 10 for A301).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from comqutor_alpha.structure_engine.alpha_mapper import _record_text
from comqutor_alpha.structure_engine.claim_semantics import (
    _NEGATION_PATTERN,
    RISK_ALPHA_IDS,
    alpha_relation,
    analyze_claim_semantics,
)
from comqutor_alpha.structure_engine.factor_normalizer import normalize_text

STATEMENT_SCOPE_POLICY_VERSION = "alpha_statement_scope.v2"
ANCHOR_MODEL_SUPPORTS = "MODEL_JUDGED_SUPPORTS_ALPHA"
REMAINING_ALPHA_TERMS_ONLY_IN_REMOVED_PART = "ALPHA_TERMS_ONLY_IN_REMOVED_PART"

BASIS_CITATION_MARKER = "CITATION_MARKER"
BASIS_NEGATED_PROTECTION = "NEGATED_PROTECTION_AFFIRMS_RISK"
BASIS_CONTRAST_ALTERNATIVE = "CONTRAST_ALTERNATIVE"
BASIS_OTHER_CLAUSE = "NEGATION_IN_ANOTHER_CLAUSE"

# "[fragmentid: ...]", "[source_id: ...]", "Source Marker: [fragmentid: not provided]" -- provenance, never statement content
_CITATION_MARKER = re.compile(
    r"(?:\bsource\s+marker\s*:\s*)?\[\s*(?:fragment\s*_?\s*ids?|source(?:\s*_?\s*ids?)?|src)\s*:[^\]]*\]", re.IGNORECASE
)
# "does not immunize ... from", "cannot shield ... against": the protection is denied, the risk is affirmed (risk Alphas only)
_NEGATED_PROTECTION = re.compile(
    r"\b(?:(?:does|do|did|will|would|can|could|should)\s+not|(?:does|do|did|wo|ca|could|should)n['’]t|cannot)\s+"
    r"(?:fully\s+)?(?:immuni[sz]e|insulate|shield|protect|offset|cushion|prevent)s?\b(?=[^.;!?]*\b(?:from|against)\b)",
    re.IGNORECASE,
)
# the end of a clause: a sentence end (not a decimal point), a semicolon, or a dash
_CLAUSE_END = r"(?:[;!?]|[.](?=[\"”’']?(?:\s|$))|\s[—–]\s|\s--?\s|$)"
# "X, not Y" / "X -- not Y": the alternative from the comma or dash to the next comma or the end of its clause
_TRAILING_ALTERNATIVE = re.compile(
    r"(?:,|\s[—–]|\s--?)\s*(?:and\s+)?not\s+(?!only\b)(?:(?!,|" + _CLAUSE_END + r").)+", re.IGNORECASE
)
# "not Y but X": the rejected alternative and the "but" that introduces the statement
_NOT_BUT = re.compile(r"\bnot\s+(?!only\b)[^,;.!?—–]*?\s+but\s+(?:rather\s+)?", re.IGNORECASE)
# "It's not -- it's X", "That is not 'Y'. That is X": a negated clause followed by a restatement of the same subject
_CORRECTIVE = re.compile(
    r"(?:^|(?<=[.;!?]\s)|(?<=[.;!?][\"”’']\s))(?P<neg>[^.;!?—–]*\b(?:not|n['’]t)\b[^.;!?—–]*?)"
    r"(?P<sep>[.;!?][\"”’']?\s+|\s*[—–]\s*|\s+--?\s+)"
    r"(?=(?:it|that|this|they|these|those)(?:['’]s|['’]re|\s+is|\s+are|\s+was|\s+were)\b)",
    re.IGNORECASE,
)
_CLAUSE_SPLIT = re.compile(r"[;!?]+|[.](?=[\"”’']?(?:\s|$))")
# a clause that refers back ("that risk is not ...") may be negating the statement it refers to
_BACK_REFERENCE = re.compile(r"\b(?:it|its|this|that|these|those|they|them|such)\b", re.IGNORECASE)


def _negators(text: str) -> list[str]:
    return [m.group(0) for m in _NEGATION_PATTERN.finditer(normalize_text(text))]


def _remove(text: str, pattern: re.Pattern[str], basis: str, removed: list[dict[str, str]], *, group: str | None = None) -> str:
    def _cut(match: re.Match[str]) -> str:
        span = match.group(group) if group else match.group(0)
        if group is None or span is None:
            removed.append({"basis": basis, "text": match.group(0).strip()})
            return " "
        removed.append({"basis": basis, "text": (span + match.group("sep")).strip()})
        return " "

    return pattern.sub(_cut, text)


def _term_in(term: str, normalized_clause: str) -> bool:
    norm = normalize_text(term)
    return bool(norm) and re.search(rf"(?<![a-z0-9]){re.escape(norm)}(?![a-z0-9])", normalized_clause) is not None


def _without_other_clause_negations(text: str, terms: Sequence[str], removed: list[dict[str, str]]) -> str:
    """Drop the clauses that carry a negator but none of this Alpha's own matched terms -- only when at least one clause
    carries a matched term and none of those clauses is negated (otherwise the negation may govern the statement)."""
    clauses = [c for c in _CLAUSE_SPLIT.split(text) if c and c.strip()]
    with_terms = [c for c in clauses if any(_term_in(t, normalize_text(c)) for t in terms)]
    if not with_terms or any(_negators(c) for c in with_terms):
        return text
    if any(_negators(c) and _BACK_REFERENCE.search(c) for c in clauses if c not in with_terms):
        return text
    kept = []
    for clause in clauses:
        if clause in with_terms or not _negators(clause):
            kept.append(clause.strip())
        else:
            removed.append({"basis": BASIS_OTHER_CLAUSE, "text": clause.strip()})
    return ". ".join(kept)


def matched_terms(candidate: Mapping[str, Any]) -> list[str]:
    """This Alpha's own lexical evidence in the claim, as the mapper recorded it on the matched candidate."""
    terms = [*(candidate.get("matched_keywords") or ()), *(candidate.get("matched_factors") or ())]
    return sorted({str(t) for t in terms if str(t or "").strip()})


def statement_scope(
    text: str, alpha_id: str, *, text_rule: Mapping[str, Any], terms: Sequence[str], model_supports: bool = False
) -> dict[str, Any]:
    """The negation-scope decision of one pair. ``text_rule`` is the stored (relation, assertion_status, semantic_polarity);
    ``model_supports`` is the anchor the contrast and clause removals need (a ledger-corroborated model judgment that the
    claim supports this Alpha) -- without it they are only reported, under ``not_applied``."""
    stored = {key: text_rule.get(key) for key in ("relation", "assertion_status", "semantic_polarity")}
    decision: dict[str, Any] = {
        "policy": STATEMENT_SCOPE_POLICY_VERSION,
        "applies": stored["assertion_status"] == "negated",
        "governing_negation": stored["assertion_status"] == "negated",
        "text_rule_negators": _negators(text),
        "remaining_negators": [],
        "removed": [],
        "not_applied": [],
        "anchor": ANCHOR_MODEL_SUPPORTS if model_supports else None,
        "matched_terms": list(terms),
        "effective": dict(stored),
        "changed": False,
    }
    if not decision["applies"]:
        return decision
    removed: list[dict[str, str]] = []
    scoped = _remove(text, _CITATION_MARKER, BASIS_CITATION_MARKER, removed)
    if _negators(scoped) and alpha_id in RISK_ALPHA_IDS:
        scoped = _remove(scoped, _NEGATED_PROTECTION, BASIS_NEGATED_PROTECTION, removed)
    # the content-dependent removals: which side of a contrast (or which clause) carries this Alpha's statement is decided by the
    # anchor, never by the words alone
    contrast: list[dict[str, str]] = []
    candidate = scoped
    if _negators(candidate):
        candidate = _remove(candidate, _CORRECTIVE, BASIS_CONTRAST_ALTERNATIVE, contrast, group="neg")
        candidate = _remove(candidate, _NOT_BUT, BASIS_CONTRAST_ALTERNATIVE, contrast)
        candidate = _remove(candidate, _TRAILING_ALTERNATIVE, BASIS_CONTRAST_ALTERNATIVE, contrast)
    if _negators(candidate) and terms:
        candidate = _without_other_clause_negations(candidate, terms, contrast)
    if model_supports:
        scoped = candidate
        removed.extend(contrast)
    else:
        decision["not_applied"] = contrast
    scoped = re.sub(r"\s+", " ", scoped).strip()
    remaining = _negators(scoped)
    decision["removed"] = removed
    decision["remaining_negators"] = remaining
    if remaining or len(normalize_text(scoped).split()) < 3:
        return decision  # a negator still governs the statement (or nothing is left to read): the text rule stands
    if terms and not any(_term_in(term, normalize_text(scoped)) for term in terms):
        # this Alpha's own matched terms were only in the removed part: its statement is the negated alternative
        decision["remaining_negators"] = [REMAINING_ALPHA_TERMS_ONLY_IN_REMOVED_PART]
        return decision
    semantics = analyze_claim_semantics(scoped)
    effective = {
        "relation": alpha_relation(scoped, alpha_id),
        "assertion_status": semantics.assertion_status,
        "semantic_polarity": semantics.semantic_polarity,
    }
    decision.update(governing_negation=False, effective=effective, changed=effective != stored)
    return decision


def statement_scope_for_match(
    match: Mapping[str, Any], candidate: Mapping[str, Any], alpha_id: str, *, model_supports: bool = False
) -> dict[str, Any]:
    """The decision for a committed match: the mapper's own text-rule input, the stored text-rule fields, the matched terms and
    the anchor (the pair's ledger-corroborated model stance is ``supports_alpha``)."""
    text_rule = {
        "relation": candidate.get("relation"),
        "assertion_status": match.get("assertion_status"),
        "semantic_polarity": match.get("semantic_polarity"),
    }
    return statement_scope(
        _record_text(match), alpha_id, text_rule=text_rule, terms=matched_terms(candidate), model_supports=model_supports
    )
