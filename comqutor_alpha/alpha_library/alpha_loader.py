"""Load and validate the official COMQUTOR MVP alpha taxonomy."""

from __future__ import annotations

from pathlib import Path

import yaml

from comqutor_alpha.alpha_library.alpha_schema import AlphaDefinition


TAXONOMY_PATH = Path(__file__).with_name("alpha_taxonomy_v1.yaml")
EXPECTED_ALPHA_IDS = {
    "A001",
    "A003",
    "A101",
    "A102",
    "A103",
    "A201",
    "A301",
    "A304",
    "A501",
    "A601",
}
REQUIRED_FIELDS = {
    "alpha_id",
    "name_en",
    "name_cn",
    "layer",
    "status",
    "core_thesis",
    "keywords",
    "trigger_signals",
    "confirmation_signals",
    "beneficiary_assets",
    "risk_assets",
    "conflict_alphas",
    "invalidation_conditions",
    "agent_sources",
}
MANDATORY_CONFLICT_WEIGHTS = {
    frozenset({"A101", "A304"}): 0.90,
    frozenset({"A301", "A304"}): 0.85,
    frozenset({"A001", "A501"}): 0.85,
    frozenset({"A003", "A501"}): 0.85,
    frozenset({"A601", "A304"}): 0.80,
    frozenset({"A601", "A501"}): 0.80,
}


def _taxonomy_path(path=None) -> Path:
    return Path(path) if path is not None else TAXONOMY_PATH


def load_alpha_taxonomy(path=None) -> dict[str, AlphaDefinition]:
    taxonomy_path = _taxonomy_path(path)
    try:
        with taxonomy_path.open(encoding="utf-8") as f:
            payload = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ValueError(f"Malformed alpha taxonomy YAML: {exc}") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("alphas"), list):
        raise ValueError("Alpha taxonomy must contain an 'alphas' list.")

    alphas = {}
    for raw_alpha in payload["alphas"]:
        if not isinstance(raw_alpha, dict):
            raise ValueError("Each alpha entry must be a mapping.")
        missing = REQUIRED_FIELDS - set(raw_alpha)
        if missing:
            alpha_id = raw_alpha.get("alpha_id", "<unknown>")
            raise ValueError(f"Alpha {alpha_id} is missing required fields: {sorted(missing)}")
        alpha = AlphaDefinition.from_dict(raw_alpha)
        if alpha.alpha_id in alphas:
            raise ValueError(f"Duplicate alpha_id found: {alpha.alpha_id}")
        alphas[alpha.alpha_id] = alpha

    validate_taxonomy(alphas)
    return alphas


def get_alpha_by_id(alpha_id, taxonomy=None):
    taxonomy = taxonomy or load_alpha_taxonomy()
    return taxonomy.get(alpha_id)


def build_keyword_index(taxonomy):
    index = {}
    for alpha in taxonomy.values():
        searchable_terms = [
            alpha.alpha_id,
            alpha.name_en,
            alpha.name_cn,
            alpha.core_thesis,
            *alpha.keywords,
            *alpha.trigger_signals,
            *alpha.confirmation_signals,
        ]
        for term in searchable_terms:
            normalized = str(term).strip().lower()
            if not normalized:
                continue
            index.setdefault(normalized, set()).add(alpha.alpha_id)
    return index


def _conflict_lookup(taxonomy):
    lookup = {}
    for alpha in taxonomy.values():
        for conflict in alpha.conflict_alphas:
            lookup[(alpha.alpha_id, conflict.alpha_id)] = conflict.contradiction_weight
    return lookup


def validate_taxonomy(taxonomy):
    if not isinstance(taxonomy, dict):
        raise ValueError("taxonomy must be a dict keyed by alpha_id.")
    alpha_ids = set(taxonomy)
    if alpha_ids != EXPECTED_ALPHA_IDS:
        raise ValueError(
            f"Expected exactly MVP-10 alpha IDs {sorted(EXPECTED_ALPHA_IDS)}, "
            f"got {sorted(alpha_ids)}."
        )

    conflicts = _conflict_lookup(taxonomy)
    for pair, expected_weight in MANDATORY_CONFLICT_WEIGHTS.items():
        left, right = sorted(pair)
        left_to_right = conflicts.get((left, right))
        right_to_left = conflicts.get((right, left))
        if left_to_right is None or right_to_left is None:
            raise ValueError(f"Mandatory conflict pair must exist in both directions: {left}-{right}")
        if abs(left_to_right - expected_weight) > 0.05:
            raise ValueError(f"Unexpected conflict weight for {left}->{right}: {left_to_right}")
        if abs(right_to_left - expected_weight) > 0.05:
            raise ValueError(f"Unexpected conflict weight for {right}->{left}: {right_to_left}")

    for alpha in taxonomy.values():
        if not alpha.keywords:
            raise ValueError(f"{alpha.alpha_id} must define at least one keyword.")
    return True
