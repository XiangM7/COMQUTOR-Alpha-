"""P4 phase 1 (2026-10-12): the definition anchors of the experimental Alpha relevance judgment.

``alpha_relevance_elements_v1.json`` registers, per Alpha, the substantive ELEMENTS (named variables and relations) of the Alpha's own
taxonomy definition and where each one has its head occurrence. An element with a head occurrence in ``core_thesis``,
``trigger_signals`` or ``invalidation_conditions`` is CORE-OWNED; an element whose head occurrences are all in
``confirmation_signals`` is STRONG-ELIGIBLE. A confirmation entry whose element is core-owned is SHADOWED: it can never produce
"strong" (Q1 first). The table is copied verbatim from the round-36 A9 v2 draft; the taxonomy (``alpha_taxonomy_v1.yaml``) is never
edited to fit it -- instead every phrase is checked against the taxonomy text on load, so a taxonomy change surfaces as a load
error or as a changed definition hash, never as a silently reused definition.

The definition handed to the judgment task, and its sha256, are built here. Nothing in this module carries a weight.

Session 6 (2026-10-12): ``alpha_relevance_hints_v1.json`` is a separate, versioned register of ELEMENT HINTS -- expressions the
owner accepted as possible statements of an element (a true synonym, or a subcategory of the element's object with the same
property). A hint is a semantic hint for the model, never an automatic hit. The register is kept apart from the element table so the
definitions and their hashes (and every judgment bound to them) stay unchanged.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from comqutor_alpha.alpha_library.alpha_loader import TAXONOMY_PATH, load_alpha_taxonomy

ELEMENTS_PATH = Path(__file__).with_name("alpha_relevance_elements_v1.json")
ELEMENTS_VERSION = "alpha_relevance_elements.v1"
CORE_LISTS = ("core_thesis", "trigger_signals", "invalidation_conditions")
STRONG_LISTS = ("confirmation_signals",)
DEFINITION_LISTS = (*CORE_LISTS, *STRONG_LISTS)
OWNERSHIP_CORE = "core"
OWNERSHIP_STRONG = "strong"
ELEMENT_KINDS = frozenset({"variable", "relation"})
HINTS_PATH = Path(__file__).with_name("alpha_relevance_hints_v1.json")
HINTS_VERSION = "alpha_relevance_element_hints.v1"
HINT_RELATIONS = frozenset({"synonym", "same_property_subcategory"})
HINT_SENT_FIELDS = ("element_id", "relation", "expressions", "object", "property", "scope")  # what the model sees of each hint


def canonical_json_text(value: Any) -> str:
    """Canonical JSON (sorted keys, compact separators, UTF-8 text, no NaN) -- byte-identical to the semantic runtime's canonical form,
    kept here so the relevance modules are not themselves importers of ``comqutor_alpha.llm_runtime`` (only approved integration
    points import the runtime; a test proves the two forms agree)."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_canonical_json(value: Any) -> str:
    return sha256_text(canonical_json_text(value))


class RelevanceElementsError(ValueError):
    """The element table cannot be used as definition anchors (stable reason code; the message names the offending entry)."""

    def __init__(self, reason_code: str, detail: str = "") -> None:
        super().__init__(f"{reason_code}: {detail}" if detail else reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class AlphaRelevanceDefinition:
    """One Alpha's definition as the judgment task sees it: the taxonomy text verbatim plus the element ownership."""

    alpha_id: str
    payload: Mapping[str, Any]
    sha256: str
    ownership: Mapping[str, str] = field(default_factory=dict)  # element id -> "core" | "strong"
    labels: Mapping[str, str] = field(default_factory=dict)  # element id -> label
    occurrences: Mapping[str, tuple[tuple[str, str], ...]] = field(default_factory=dict)  # element id -> ((list, phrase), ...)


def taxonomy_content_version(path: Path | str | None = None) -> str:
    """The taxonomy file's own ``content_version`` (the loader does not expose it)."""
    with Path(path or TAXONOMY_PATH).open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    value = payload.get("content_version") if isinstance(payload, Mapping) else None
    if not isinstance(value, str) or not value:
        raise RelevanceElementsError("TAXONOMY_CONTENT_VERSION_MISSING")
    return value


def _norm(text: Any) -> str:
    return " ".join(str(text or "").split()).casefold()


def _phrase_in_taxonomy(alpha: Any, list_name: str, phrase: str) -> bool:
    if list_name == "core_thesis":
        return _norm(phrase) in _norm(alpha.core_thesis)
    return any(_norm(phrase) == _norm(entry) for entry in getattr(alpha, list_name) or [])


def _definition(alpha: Any, entry: Mapping[str, Any], content_version: str) -> AlphaRelevanceDefinition:
    alpha_id = alpha.alpha_id
    elements = entry.get("elements")
    if not isinstance(elements, list) or not elements:
        raise RelevanceElementsError("ELEMENTS_MISSING", alpha_id)
    ownership: dict[str, str] = {}
    labels: dict[str, str] = {}
    occurrences: dict[str, tuple[tuple[str, str], ...]] = {}
    rendered: list[dict[str, Any]] = []
    for element in elements:
        element_id = str(element.get("id") or "")
        if not element_id.startswith(f"{alpha_id}.") or element_id in ownership:
            raise RelevanceElementsError("ELEMENT_ID_INVALID", element_id or "<empty>")
        if element.get("kind") not in ELEMENT_KINDS:
            raise RelevanceElementsError("ELEMENT_KIND_INVALID", element_id)
        heads: list[tuple[str, str]] = []
        for occurrence in element.get("occurrences") or []:
            list_name, phrase = occurrence.get("list"), str(occurrence.get("phrase") or "")
            if list_name not in DEFINITION_LISTS or not phrase:
                raise RelevanceElementsError("ELEMENT_OCCURRENCE_INVALID", element_id)
            if not _phrase_in_taxonomy(alpha, list_name, phrase):
                raise RelevanceElementsError("ELEMENT_PHRASE_NOT_IN_TAXONOMY", f"{element_id}: {list_name} {phrase!r}")
            if occurrence.get("role") == "head":
                heads.append((list_name, phrase))
        if not heads:
            raise RelevanceElementsError("ELEMENT_WITHOUT_HEAD", element_id)
        ownership[element_id] = OWNERSHIP_CORE if any(name in CORE_LISTS for name, _ in heads) else OWNERSHIP_STRONG
        labels[element_id] = str(element.get("label") or element_id)
        occurrences[element_id] = tuple(heads)
        rendered.append({
            "id": element_id, "label": labels[element_id], "kind": element["kind"], "ownership": ownership[element_id],
            **({"relata": list(element.get("relata") or [])} if element["kind"] == "relation" else {}),
            "occurrences": [{"list": name, "phrase": phrase} for name, phrase in heads],
        })
    shadowed = [
        {"phrase": phrase, "element_id": element_id}
        for element_id, heads in occurrences.items() if ownership[element_id] == OWNERSHIP_CORE
        for name, phrase in heads if name in STRONG_LISTS
    ]
    not_merged = []
    for pair in entry.get("related_not_merged") or []:
        if pair.get("a") not in ownership or pair.get("b") not in ownership:
            raise RelevanceElementsError("NOT_MERGED_PAIR_UNKNOWN_ELEMENT", f"{pair.get('a')} / {pair.get('b')}")
        not_merged.append({"a": pair["a"], "b": pair["b"], "reason": str(pair.get("reason") or "")})
    context = []
    for phrase_entry in entry.get("context_phrases") or []:
        list_name, phrase = phrase_entry.get("list"), str(phrase_entry.get("phrase") or "")
        if list_name not in DEFINITION_LISTS or not _phrase_in_taxonomy(alpha, list_name, phrase):
            raise RelevanceElementsError("CONTEXT_PHRASE_NOT_IN_TAXONOMY", f"{alpha_id}: {phrase!r}")
        context.append({"list": list_name, "phrase": phrase, "reason": str(phrase_entry.get("reason") or "")})
    payload = {
        "alpha_id": alpha_id,
        "name": alpha.name_en,
        "definition": {
            "core_thesis": alpha.core_thesis,
            "trigger_signals": list(alpha.trigger_signals),
            "confirmation_signals": list(alpha.confirmation_signals),
            "invalidation_conditions": list(alpha.invalidation_conditions),
        },
        "topic_terms": {
            "keywords": list(alpha.keywords),
            "beneficiary_assets": list(alpha.beneficiary_assets),
            "risk_assets": list(alpha.risk_assets),
        },
        "elements": rendered,
        "shadowed_confirmation_entries": shadowed,
        "related_not_merged": not_merged,
        "context_phrases": context,
    }
    digest = sha256_canonical_json({"elements_version": ELEMENTS_VERSION, "taxonomy_content_version": content_version, "definition": payload})
    return AlphaRelevanceDefinition(alpha_id=alpha_id, payload=payload, sha256=digest, ownership=ownership, labels=labels, occurrences=occurrences)


def load_relevance_definitions(
    elements_path: Path | str | None = None, *, taxonomy_path: Path | str | None = None
) -> dict[str, AlphaRelevanceDefinition]:
    """Every Alpha's relevance definition, validated against the taxonomy text. Raises ``RelevanceElementsError`` on any mismatch."""
    import json  # noqa: PLC0415 -- only this loader reads JSON

    try:
        table = json.loads(Path(elements_path or ELEMENTS_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RelevanceElementsError("ELEMENTS_UNREADABLE", type(exc).__name__) from exc
    if not isinstance(table, Mapping) or table.get("schema") != ELEMENTS_VERSION:
        raise RelevanceElementsError("ELEMENTS_SCHEMA_INVALID", str(table.get("schema") if isinstance(table, Mapping) else type(table).__name__))
    content_version = taxonomy_content_version(taxonomy_path)
    if table.get("taxonomy_content_version") != content_version:
        raise RelevanceElementsError("ELEMENTS_TAXONOMY_VERSION_MISMATCH", f"{table.get('taxonomy_content_version')} != {content_version}")
    taxonomy = load_alpha_taxonomy(taxonomy_path)
    alphas = table.get("alphas")
    if not isinstance(alphas, Mapping) or not alphas:
        raise RelevanceElementsError("ELEMENTS_ALPHAS_MISSING")
    definitions: dict[str, AlphaRelevanceDefinition] = {}
    for alpha_id, entry in alphas.items():
        alpha = taxonomy.get(alpha_id)
        if alpha is None or not isinstance(entry, Mapping):
            raise RelevanceElementsError("ELEMENTS_UNKNOWN_ALPHA", str(alpha_id))
        definitions[alpha_id] = _definition(alpha, entry, content_version)
    return definitions


@dataclass(frozen=True)
class RelevanceHints:
    """The element hint register as the judgment task sends it: per Alpha, the hints' sent fields; ``sha256`` covers exactly that."""

    version: str
    sha256: str
    by_alpha: Mapping[str, tuple[Mapping[str, Any], ...]]

    def for_alpha(self, alpha_id: str) -> list[dict[str, Any]]:
        return [dict(hint) for hint in self.by_alpha.get(alpha_id, ())]


def load_relevance_hints(
    path: Path | str | None = None, *, definitions: Mapping[str, AlphaRelevanceDefinition] | None = None
) -> RelevanceHints:
    """The element hint register, validated against the element table: every hint names an existing element of its Alpha, a known
    relation, at least one expression, and its object, property, scope and basis. Raises ``RelevanceElementsError`` otherwise."""
    try:
        table = json.loads(Path(path or HINTS_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RelevanceElementsError("HINTS_UNREADABLE", type(exc).__name__) from exc
    if not isinstance(table, Mapping) or table.get("schema") != HINTS_VERSION:
        raise RelevanceElementsError("HINTS_SCHEMA_INVALID", str(table.get("schema") if isinstance(table, Mapping) else type(table).__name__))
    if table.get("elements_version") != ELEMENTS_VERSION:
        raise RelevanceElementsError("HINTS_ELEMENTS_VERSION_MISMATCH", str(table.get("elements_version")))
    definitions = definitions if definitions is not None else load_relevance_definitions()
    hints = table.get("hints")
    if not isinstance(hints, list):
        raise RelevanceElementsError("HINTS_MISSING")
    seen: set[str] = set()
    by_alpha: dict[str, list[dict[str, Any]]] = {}
    for hint in hints:
        hint_id = str(hint.get("id") or "") if isinstance(hint, Mapping) else ""
        if not hint_id or hint_id in seen:
            raise RelevanceElementsError("HINT_ID_INVALID", hint_id or "<empty>")
        seen.add(hint_id)
        definition = definitions.get(str(hint.get("alpha_id")))
        if definition is None or hint.get("element_id") not in definition.ownership:
            raise RelevanceElementsError("HINT_UNKNOWN_ELEMENT", f"{hint_id}: {hint.get('alpha_id')} / {hint.get('element_id')}")
        if hint.get("relation") not in HINT_RELATIONS:
            raise RelevanceElementsError("HINT_RELATION_INVALID", hint_id)
        expressions = hint.get("expressions")
        if (not isinstance(expressions, list) or not expressions or any(not isinstance(e, str) or not e.strip() for e in expressions)
                or len({_norm(e) for e in expressions}) != len(expressions)):
            raise RelevanceElementsError("HINT_EXPRESSIONS_INVALID", hint_id)
        if any(not isinstance(hint.get(name), str) or not hint[name].strip() for name in ("object", "property", "scope", "basis")):
            raise RelevanceElementsError("HINT_FIELDS_MISSING", hint_id)
        by_alpha.setdefault(definition.alpha_id, []).append({name: hint[name] for name in HINT_SENT_FIELDS})
    sent = {alpha_id: sorted(entries, key=lambda h: (h["element_id"], h["expressions"][0])) for alpha_id, entries in sorted(by_alpha.items())}
    return RelevanceHints(version=HINTS_VERSION, sha256=sha256_canonical_json({"version": HINTS_VERSION, "hints": sent}),
                          by_alpha={alpha_id: tuple(entries) for alpha_id, entries in sent.items()})


__all__ = [
    "CORE_LISTS",
    "DEFINITION_LISTS",
    "ELEMENTS_PATH",
    "ELEMENTS_VERSION",
    "HINTS_PATH",
    "HINTS_VERSION",
    "OWNERSHIP_CORE",
    "OWNERSHIP_STRONG",
    "STRONG_LISTS",
    "AlphaRelevanceDefinition",
    "RelevanceElementsError",
    "RelevanceHints",
    "load_relevance_definitions",
    "load_relevance_hints",
    "taxonomy_content_version",
]
