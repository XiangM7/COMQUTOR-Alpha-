"""Strict loader and bidirectional conflict index for MVP-10 taxonomy."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from .alpha_schema import AlphaDefinition, AlphaTaxonomyDocument, ConflictAlpha

DEFAULT_TAXONOMY_PATH = Path(__file__).with_name("alpha_taxonomy_v1.yaml")
EXPECTED_ALPHA_IDS = frozenset(
    {"A001", "A003", "A101", "A102", "A103", "A201", "A301", "A304", "A501", "A601"}
)
MANDATORY_CONFLICT_PAIRS = frozenset(
    {
        ("A101", "A304"),
        ("A301", "A304"),
        ("A001", "A501"),
        ("A003", "A501"),
        ("A304", "A601"),
        ("A501", "A601"),
    }
)
MANDATORY_RELATIONS = frozenset(
    {
        ("A001", "A304"),
        ("A001", "A601"),
        ("A003", "A601"),
        ("A003", "A304"),
        ("A101", "A103"),
        ("A101", "A201"),
        ("A101", "A301"),
        ("A101", "A601"),
        ("A102", "A103"),
        ("A102", "A301"),
        ("A201", "A301"),
    }
)


class TaxonomyError(ValueError):
    """Taxonomy data is incomplete, inconsistent, or unsafe to use."""


class AlphaTaxonomy:
    def __init__(self, document: AlphaTaxonomyDocument):
        self.document = document
        self._by_id = {alpha.alpha_id: alpha for alpha in document.alphas}
        self._conflicts: dict[str, list[ConflictAlpha]] = {alpha_id: [] for alpha_id in self._by_id}
        seen: set[tuple[str, str]] = set()
        for alpha in document.alphas:
            for conflict in alpha.conflict_alphas:
                pair = tuple(sorted((alpha.alpha_id, conflict.alpha_id)))
                if pair in seen:
                    continue
                seen.add(pair)
                self._conflicts[alpha.alpha_id].append(conflict)
                reverse = ConflictAlpha(
                    alpha_id=alpha.alpha_id,
                    contradiction_weight=conflict.contradiction_weight,
                    source_note=conflict.source_note,
                    review_status=conflict.review_status,
                )
                self._conflicts[conflict.alpha_id].append(reverse)
        for values in self._conflicts.values():
            values.sort(key=lambda value: value.alpha_id)

    @property
    def alphas(self) -> tuple[AlphaDefinition, ...]:
        return tuple(self.document.alphas)

    def get(self, alpha_id: str) -> AlphaDefinition:
        try:
            return self._by_id[alpha_id]
        except KeyError as exc:
            raise TaxonomyError(f"unknown Alpha ID: {alpha_id}") from exc

    def conflicts_for(self, alpha_id: str) -> tuple[ConflictAlpha, ...]:
        self.get(alpha_id)
        return tuple(self._conflicts[alpha_id])

    def conflict_pairs(self) -> tuple[tuple[str, str, ConflictAlpha], ...]:
        pairs: list[tuple[str, str, ConflictAlpha]] = []
        for alpha_id in sorted(self._conflicts):
            for conflict in self._conflicts[alpha_id]:
                if alpha_id < conflict.alpha_id:
                    pairs.append((alpha_id, conflict.alpha_id, conflict))
        return tuple(pairs)


def _validate_document(document: AlphaTaxonomyDocument) -> None:
    ids = [alpha.alpha_id for alpha in document.alphas]
    if len(ids) != len(set(ids)):
        raise TaxonomyError("duplicate Alpha ID")
    if len(ids) != 10 or set(ids) != EXPECTED_ALPHA_IDS:
        missing = sorted(EXPECTED_ALPHA_IDS - set(ids))
        extra = sorted(set(ids) - EXPECTED_ALPHA_IDS)
        raise TaxonomyError(f"taxonomy must contain exactly MVP-10; missing={missing}, extra={extra}")

    conflict_weights: dict[tuple[str, str], float] = {}
    for alpha in document.alphas:
        for conflict in alpha.conflict_alphas:
            if conflict.alpha_id not in EXPECTED_ALPHA_IDS:
                raise TaxonomyError(
                    f"{alpha.alpha_id} references unknown conflict target {conflict.alpha_id}"
                )
            pair = tuple(sorted((alpha.alpha_id, conflict.alpha_id)))
            previous = conflict_weights.get(pair)
            if previous is not None and previous != conflict.contradiction_weight:
                raise TaxonomyError(f"conflict pair {pair} has asymmetric weights")
            conflict_weights[pair] = conflict.contradiction_weight
    if set(conflict_weights) != MANDATORY_CONFLICT_PAIRS:
        raise TaxonomyError("taxonomy conflicts must equal the six mandatory MVP pairs")

    relations = {
        (edge.source, edge.target)
        for alpha in document.alphas
        for edge in alpha.causal_graph
    }
    if not relations >= MANDATORY_RELATIONS:
        missing_relations = sorted(MANDATORY_RELATIONS - relations)
        raise TaxonomyError(f"missing mandatory structural relations: {missing_relations}")
    for source, target in relations:
        if source not in EXPECTED_ALPHA_IDS or target not in EXPECTED_ALPHA_IDS:
            raise TaxonomyError(f"unknown structural relation target: {(source, target)}")


def load_taxonomy(path: Path | str = DEFAULT_TAXONOMY_PATH) -> AlphaTaxonomy:
    source = Path(path)
    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise TaxonomyError(f"unable to read taxonomy {source}: {exc}") from exc
    if not isinstance(raw, dict):
        raise TaxonomyError("taxonomy root must be an object")

    raw_alphas = raw.get("alphas")
    if isinstance(raw_alphas, list):
        raw_ids = [item.get("alpha_id") for item in raw_alphas if isinstance(item, dict)]
        if len(raw_ids) != len(set(raw_ids)):
            raise TaxonomyError("duplicate Alpha ID")
    try:
        document = AlphaTaxonomyDocument.model_validate(raw)
    except ValidationError as exc:
        raise TaxonomyError(f"taxonomy schema validation failed: {exc}") from exc
    _validate_document(document)
    return AlphaTaxonomy(document)
