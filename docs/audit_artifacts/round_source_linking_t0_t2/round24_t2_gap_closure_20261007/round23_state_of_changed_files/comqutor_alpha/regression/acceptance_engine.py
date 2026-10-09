"""T2 unified formal acceptance entry point (COMQUTOR Alpha next-round task,
Section 4): a single, machine-readable executor for the six Gold v0.2
acceptance rule families frozen in
``docs/audit_artifacts/v0_2_john_frozen_gold_baseline.yaml``
(``evidence_conditional_semantics``):

  * ``must_detect_if_evidence_present``
  * ``should_detect_if_supported``
  * ``conditional_only``
  * ``do_not_force``
  * ``allowed_main_conflicts``
  * ``forbidden_dominant_without_strong_evidence``

This module never re-derives Alpha/Conflict/admissibility data -- every
verdict is computed by reading already-persisted, already-computed fields
from :func:`comqutor_alpha.regression.evaluator.evaluate_ticker`'s result,
the run's own ``conflicts.json`` ``arbitration.candidate_evaluations``
(B2's own admissibility detail), and the v0.2 label file
(:mod:`comqutor_alpha.regression.labels_v2`). Per the frozen baseline's own
``implementation_alignment_required`` notes:

  * ``forbidden_dominant_without_strong_evidence`` is the SAME concept as
    the already-implemented ``dominance_guard_flags``
    (:mod:`comqutor_alpha.regression.evaluator`) under a different name --
    reused directly, not reimplemented.
  * ``conditional_only`` and ``allowed_main_conflicts`` are the same
    concepts as v0.2's ``conditional_conflicts``/``allowed_conflicts``
    categories, already executed by
    :func:`comqutor_alpha.regression.evaluation_contract.apply_v2_contract`
    -- reused directly.
  * ``must_detect_if_evidence_present``, ``should_detect_if_supported``,
    and ``do_not_force`` have no prior runtime implementation under any
    name (baseline: "Documentation-only" / "not a standalone rule_type
    with ... code enforcement anywhere in the repository today") -- these
    are genuinely new, implemented here directly on top of the same
    already-persisted B2 admissibility fields, never a new admissibility
    heuristic.

Explicit config, no silent fallback: :func:`effective_rules` always states
the exact taxonomy and label file it resolved and raises
:class:`AcceptanceConfigError` (never falls back to a different file) if
either is missing/malformed. :func:`run_formal_acceptance` refuses a formal
PASS whenever ``effective_rules`` itself failed, or the ticker's own
source artifacts are incomplete -- it never uses ``not_applicable`` to
paper over a config or execution problem.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from comqutor_alpha.alpha_library.alpha_loader import TAXONOMY_PATH, load_alpha_taxonomy
from comqutor_alpha.conflict_engine.conflict_admissibility import (
    ADMITTED as B2_ADMITTED,
)
from comqutor_alpha.conflict_engine.conflict_schema import canonical_pair_key, conflict_id
from comqutor_alpha.regression.evaluation_contract import apply_v2_contract
from comqutor_alpha.regression.evaluator import (
    STANCE_SOURCE_LLM_SEMANTIC,
    STANCE_SOURCE_MIXED,
    dominance_guard_flags,
)
from comqutor_alpha.regression.labels import (
    DEFAULT_LABEL_PATH as DEFAULT_LABEL_V1_PATH,
    load_j2_labels,
    ticker_label,
)
from comqutor_alpha.regression.labels_v2 import (
    DEFAULT_LABEL_V2_PATH,
    LabelV2ValidationError,
    load_j2_labels_v2,
)

SCHEMA_VERSION = "acceptance_engine.v2"

RULE_FAMILY_MUST_DETECT_IF_EVIDENCE_PRESENT = "must_detect_if_evidence_present"
RULE_FAMILY_SHOULD_DETECT_IF_SUPPORTED = "should_detect_if_supported"
RULE_FAMILY_CONDITIONAL_ONLY = "conditional_only"
RULE_FAMILY_DO_NOT_FORCE = "do_not_force"
RULE_FAMILY_ALLOWED_MAIN_CONFLICTS = "allowed_main_conflicts"
RULE_FAMILY_FORBIDDEN_DOMINANT_WITHOUT_STRONG_EVIDENCE = "forbidden_dominant_without_strong_evidence"

ALL_RULE_FAMILIES = (
    RULE_FAMILY_MUST_DETECT_IF_EVIDENCE_PRESENT,
    RULE_FAMILY_SHOULD_DETECT_IF_SUPPORTED,
    RULE_FAMILY_CONDITIONAL_ONLY,
    RULE_FAMILY_DO_NOT_FORCE,
    RULE_FAMILY_ALLOWED_MAIN_CONFLICTS,
    RULE_FAMILY_FORBIDDEN_DOMINANT_WITHOUT_STRONG_EVIDENCE,
)

VERDICT_PASS = "pass"
VERDICT_FAIL = "fail"
VERDICT_NOT_APPLICABLE = "not_applicable"
VERDICT_NEEDS_REVIEW = "needs_review"
VERDICT_PENDING_REVIEW = "pending_review"
VERDICT_NOT_EVALUABLE = "not_evaluable"

FORMAL_STATUS_CONFIG_ERROR = "config_error"
FORMAL_STATUS_NOT_EVALUABLE = "not_evaluable"
FORMAL_STATUS_FAIL = "fail"
FORMAL_STATUS_NEEDS_REVIEW = "needs_review"
FORMAL_STATUS_PASS = "pass"
# 2026-09-29 (T2 verification follow-up, item 3c): a ticker whose own
# alpha_matches are ALL match_status=="unavailable" (Architecture Replay's
# own deterministic, by-design Alpha-semantic-authority-unavailable state --
# see comqutor_alpha.replay.pipeline's own module docstring) has nothing a
# real rule family can genuinely evaluate: an empty must_detect_results/
# do_not_force_result/dominance_results set would otherwise fall through
# run_formal_acceptance's own PASS default below, formally labeling a run
# with zero real Alpha semantic evidence as having "passed" -- never a
# claim this round makes. This status is distinct from NOT_EVALUABLE
# (artifacts missing/incomplete) and from CONFIG_ERROR (rules unresolvable):
# the artifacts and rules are both fine here, only the underlying semantic
# evidence itself is genuinely, deliberately absent.
FORMAL_STATUS_ALPHA_SEMANTIC_UNAVAILABLE = "alpha_semantic_unavailable"
# T2 (2026-10-07), John's task sheet: "规则缺失、类型未实现或 taxonomy 不兼容，应输出配置／执行错误". The verdict could not be computed
# because of a failure of the execution itself (not of the rule files); written by the production wiring, never a pass.
FORMAL_STATUS_EXECUTION_ERROR = "execution_error"

REASON_TICKER_RULES_NOT_DECLARED = "ACCEPTANCE_TICKER_RULES_NOT_DECLARED"
REASON_RULE_SOURCES_DISAGREE = "ACCEPTANCE_RULE_SOURCES_DISAGREE"
REASON_RULE_TYPE_NOT_IMPLEMENTED = "ACCEPTANCE_RULE_TYPE_NOT_IMPLEMENTED"
REASON_TAXONOMY_INCOMPATIBLE_WITH_LABELS = "ACCEPTANCE_TAXONOMY_INCOMPATIBLE_WITH_LABELS"
REASON_TAXONOMY_VERSION_MISMATCH = "ACCEPTANCE_TAXONOMY_VERSION_MISMATCH"
REASON_TAXONOMY_CONTENT_VERSION_MISSING = "ACCEPTANCE_TAXONOMY_CONTENT_VERSION_MISSING"
REASON_LABEL_TAXONOMY_CONTENT_VERSION_MISSING = "ACCEPTANCE_LABEL_TAXONOMY_CONTENT_VERSION_MISSING"
REASON_TAXONOMY_CONTENT_VERSION_MISMATCH = "ACCEPTANCE_TAXONOMY_CONTENT_VERSION_MISMATCH"
REASON_LABEL_V1_INVALID = "ACCEPTANCE_LABEL_V1_INVALID"

DOMINANCE_GUARD_KEY = "should_not_be_dominant_without_strong_evidence"
_REPO_ROOT = Path(__file__).resolve().parents[2]

# Label-loader failures that mean "this label file does not fit THIS taxonomy" (as opposed to a malformed label file).
_TAXONOMY_INCOMPATIBLE_LABEL_REASONS = frozenset(
    {
        "LABEL_V2_UNDECLARED_EXECUTABLE_CONFLICT_PAIR",
        "LABEL_V2_UNKNOWN_ALPHA_ID",
        "LABEL_V2_REMOVE_WHILE_UNDECLARED_IS_ACTUALLY_CANONICAL",
    }
)

# Every key a ticker block of the v0.2 label file may carry, and what executes it. A key outside this set is a rule TYPE this engine does
# not implement: effective_rules() refuses it (ACCEPTANCE_RULE_TYPE_NOT_IMPLEMENTED) instead of silently ignoring it.
TICKER_RULE_KEY_ROLES = {
    "required_conflicts": RULE_FAMILY_MUST_DETECT_IF_EVIDENCE_PRESENT,
    "conditional_conflicts": f"{RULE_FAMILY_CONDITIONAL_ONLY} + {RULE_FAMILY_SHOULD_DETECT_IF_SUPPORTED}",
    "allowed_conflicts": RULE_FAMILY_ALLOWED_MAIN_CONFLICTS,
    DOMINANCE_GUARD_KEY: RULE_FAMILY_FORBIDDEN_DOMINANT_WITHOUT_STRONG_EVIDENCE,
    "product_decision_pending": "context: pair kept out of every verdict (never pass/fail)",
    "remove_while_undeclared": "context: pair no longer an executable expectation",
    "structural_expectations": "context: informational (a missing structural Alpha never fails a run)",
    "run_bound_expectations": "recorded only: no rule family evaluates it",
    "source_basis": "provenance text",
}
IMPLEMENTED_TICKER_RULE_KEYS = frozenset(TICKER_RULE_KEY_ROLES)

# "Evidence present" bar for must_detect_if_evidence_present: at least one
# stance-confirmed supporting claim on EACH side (bull and bear), read
# straight off B2's own already-computed
# bull_supporting_evidence_count/bear_supporting_evidence_count -- a
# strictly weaker bar than B2's own admission threshold
# (conflict_admissibility.MIN_SUPPORTING_EVIDENCE_PER_SIDE == 2), never a
# new evidence-detection heuristic.
EVIDENCE_PRESENT_MIN_SUPPORTING_EVIDENCE_PER_SIDE = 1


class AcceptanceConfigError(Exception):
    """A required rule-configuration source (taxonomy or v0.2 label file)
    is missing or malformed -- this always blocks formal PASS and is never
    silently substituted with a different file."""

    def __init__(self, reason_code: str, detail: str = "") -> None:
        self.reason_code = reason_code
        self.detail = detail
        super().__init__(f"{reason_code}: {detail}" if detail else reason_code)


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _display_path(path: Path) -> str:
    """Repository-relative path when the file lives in the repository (so an artifact never carries an engineer's home directory), else the path
    as given."""
    try:
        return path.resolve().relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _read_taxonomy_meta(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {"schema_version": raw.get("schema_version"), "content_version": raw.get("content_version")}


def _check_versions(label_v2: dict[str, Any], taxonomy_meta: dict[str, Any]) -> None:
    declared = label_v2.get("taxonomy_version")
    actual = taxonomy_meta.get("schema_version")
    if declared != actual:
        raise AcceptanceConfigError(
            REASON_TAXONOMY_VERSION_MISMATCH,
            f"label file declares taxonomy_version={declared!r}, the taxonomy file's schema_version is {actual!r}",
        )
    actual_content = taxonomy_meta.get("content_version")
    if not actual_content:
        raise AcceptanceConfigError(REASON_TAXONOMY_CONTENT_VERSION_MISSING, "the taxonomy file declares no content_version")
    declared_content = label_v2.get("taxonomy_content_version")
    if not declared_content:
        raise AcceptanceConfigError(
            REASON_LABEL_TAXONOMY_CONTENT_VERSION_MISSING, "the label file declares no taxonomy_content_version"
        )
    if str(declared_content) != str(actual_content):
        raise AcceptanceConfigError(
            REASON_TAXONOMY_CONTENT_VERSION_MISMATCH,
            f"the label file was written against taxonomy content_version={declared_content!r}, the taxonomy file is {actual_content!r}",
        )


def _check_rule_vocabulary(label_v2: dict[str, Any]) -> None:
    unknown: dict[str, list[str]] = {}
    for ticker, block in (label_v2.get("tickers") or {}).items():
        extra = sorted(set(block) - IMPLEMENTED_TICKER_RULE_KEYS)
        if extra:
            unknown[str(ticker)] = extra
    if unknown:
        raise AcceptanceConfigError(
            REASON_RULE_TYPE_NOT_IMPLEMENTED, f"rule keys with no implementation in this engine: {unknown}"
        )


def _load_label_v1(path: Path) -> dict[str, Any]:
    try:
        return load_j2_labels(path)
    except Exception as exc:  # any unusable v0.1 file is a configuration problem, never a reason to skip the dominance family
        raise AcceptanceConfigError(REASON_LABEL_V1_INVALID, f"{type(exc).__name__}: {exc}") from exc


def _check_dominance_sources_agree(label_v2: dict[str, Any], label_v1: dict[str, Any]) -> None:
    """The sixth rule family reads the v0.1 file (its runtime field); the v0.2 file carries a copy. Two copies of one rule must not diverge
    silently: if they differ for any ticker, the execution is refused."""
    disagreeing = []
    for ticker, block in (label_v2.get("tickers") or {}).items():
        guard_v2 = block.get(DOMINANCE_GUARD_KEY)
        block_v1 = ticker_label(label_v1, str(ticker))
        if guard_v2 is None or block_v1 is None:
            continue
        if (block_v1.get(DOMINANCE_GUARD_KEY) or {}) != guard_v2:
            disagreeing.append(str(ticker))
    if disagreeing:
        raise AcceptanceConfigError(
            REASON_RULE_SOURCES_DISAGREE,
            f"{DOMINANCE_GUARD_KEY} differs between the v0.1 and v0.2 label files for: {sorted(disagreeing)}",
        )


def effective_rules(
    *,
    taxonomy_path: str | Path | None = None,
    label_v2_path: str | Path | None = None,
    label_v1_path: str | Path | None = None,
) -> dict[str, Any]:
    """Explicitly resolves this run's rule configuration. Never a silent
    fallback: an explicit path is honored as given; the default is always
    the SAME named repository constant every other B2/A4 caller uses
    (``alpha_loader.TAXONOMY_PATH`` / ``labels_v2.DEFAULT_LABEL_V2_PATH`` /
    ``labels.DEFAULT_LABEL_PATH``), never re-derived or guessed.

    Raises :class:`AcceptanceConfigError` -- callers must not catch this to
    fall back to some other config -- when:

      * a file is missing or malformed (taxonomy, v0.2 label file, v0.1 label file);
      * the v0.2 label file does not fit the taxonomy that was NAMED here
        (an undeclared conflict pair, an unknown Alpha id: since 2026-10-07 the
        label file is validated against the resolved taxonomy, not the default);
      * the label file's ``taxonomy_version`` / ``taxonomy_content_version`` differ
        from the taxonomy's ``schema_version`` / ``content_version``;
      * a ticker block carries a rule key this engine does not implement;
      * the two copies of the dominance guard (v0.1 and v0.2) disagree."""
    resolved_taxonomy_path = Path(taxonomy_path) if taxonomy_path is not None else TAXONOMY_PATH
    resolved_label_path = Path(label_v2_path) if label_v2_path is not None else DEFAULT_LABEL_V2_PATH
    resolved_label_v1_path = Path(label_v1_path) if label_v1_path is not None else DEFAULT_LABEL_V1_PATH

    if not resolved_taxonomy_path.exists():
        raise AcceptanceConfigError("ACCEPTANCE_TAXONOMY_FILE_NOT_FOUND", str(resolved_taxonomy_path))
    try:
        taxonomy = load_alpha_taxonomy(resolved_taxonomy_path)
    except ValueError as exc:
        raise AcceptanceConfigError("ACCEPTANCE_TAXONOMY_MALFORMED", str(exc)) from exc
    taxonomy_meta = _read_taxonomy_meta(resolved_taxonomy_path)

    try:
        label_v2 = load_j2_labels_v2(resolved_label_path, taxonomy_path=resolved_taxonomy_path)
    except LabelV2ValidationError as exc:
        code = (
            REASON_TAXONOMY_INCOMPATIBLE_WITH_LABELS
            if exc.reason_code in _TAXONOMY_INCOMPATIBLE_LABEL_REASONS
            else "ACCEPTANCE_LABEL_V2_INVALID"
        )
        raise AcceptanceConfigError(code, str(exc)) from exc

    _check_versions(label_v2, taxonomy_meta)
    _check_rule_vocabulary(label_v2)
    label_v1 = _load_label_v1(resolved_label_v1_path)
    _check_dominance_sources_agree(label_v2, label_v1)

    rule_family_definitions = {
        RULE_FAMILY_MUST_DETECT_IF_EVIDENCE_PRESENT: {
            "config_source": f"{resolved_label_path.name}: required_conflicts",
            "applicable_target": "declared conflict pair, per ticker",
            "execution_function": "acceptance_engine.evaluate_must_detect_if_evidence_present",
            "trigger_condition": (
                "pair is in the ticker's required_conflicts AND B2 arbitration "
                f"recorded >= {EVIDENCE_PRESENT_MIN_SUPPORTING_EVIDENCE_PER_SIDE} "
                "stance-confirmed supporting claim on EACH side (bull_supporting_evidence_count "
                "and bear_supporting_evidence_count from conflicts.json's own "
                "arbitration.candidate_evaluations[].admissibility)"
            ),
            "evidence_requirement": (
                f">= {EVIDENCE_PRESENT_MIN_SUPPORTING_EVIDENCE_PER_SIDE} supporting claim per side "
                "(weaker than B2's own admission threshold of 2 -- this rule asks 'was evidence "
                "present at all', not 'did it clear B2's admission bar')"
            ),
            "verdict_result": [VERDICT_PASS, VERDICT_FAIL, VERDICT_NOT_APPLICABLE, VERDICT_NOT_EVALUABLE],
        },
        RULE_FAMILY_SHOULD_DETECT_IF_SUPPORTED: {
            "config_source": f"{resolved_label_path.name}: conditional_conflicts",
            "applicable_target": "declared conflict pair, per ticker",
            "execution_function": "acceptance_engine.evaluate_should_detect_if_supported",
            "trigger_condition": (
                "pair is in the ticker's conditional_conflicts AND evidence is present per the "
                "same bar as must_detect_if_evidence_present AND stance_source is llm_semantic or "
                "mixed (evaluator.stance_source) -- offline runs with deterministic-baseline-only "
                "stance cannot reliably judge 'supported' and are marked pending_review instead"
            ),
            "evidence_requirement": (
                "evidence present (>= 1 supporting claim per side) AND LLM-semantic stance "
                "resolution actually ran for this replay"
            ),
            "verdict_result": [
                VERDICT_PASS,
                VERDICT_NEEDS_REVIEW,
                VERDICT_PENDING_REVIEW,
                VERDICT_NOT_APPLICABLE,
                VERDICT_NOT_EVALUABLE,
            ],
        },
        RULE_FAMILY_CONDITIONAL_ONLY: {
            "config_source": f"{resolved_label_path.name}: conditional_conflicts",
            "applicable_target": "declared conflict pair, per ticker",
            "execution_function": "evaluation_contract.apply_v2_contract (conditional_conflict_results)",
            "trigger_condition": "pair is in the ticker's conditional_conflicts",
            "evidence_requirement": "none required to trigger; a miss is always informational, never a fail",
            "verdict_result": [VERDICT_PASS, "informational_mismatch", VERDICT_NOT_EVALUABLE],
        },
        RULE_FAMILY_DO_NOT_FORCE: {
            "config_source": "conflicts.json: conflicts[] cross-checked against arbitration.candidate_evaluations[].admissibility",
            "applicable_target": "every admitted conflict, per ticker (a run-wide invariant, not a per-pair rule)",
            "execution_function": "acceptance_engine.evaluate_do_not_force_invariant",
            "trigger_condition": "always evaluated when the ticker is evaluable",
            "evidence_requirement": (
                "every pair in evaluate_ticker's admitted_conflicts must have a matching "
                "arbitration.candidate_evaluations entry whose own admissibility.status is "
                "'admitted' -- proves B2's evidence gate was not bypassed, never a second judgment call"
            ),
            "verdict_result": ["invariant_held", "invariant_violated", VERDICT_NOT_EVALUABLE],
        },
        RULE_FAMILY_ALLOWED_MAIN_CONFLICTS: {
            "config_source": f"{resolved_label_path.name}: allowed_conflicts",
            "applicable_target": "declared conflict pair, per ticker",
            "execution_function": "evaluation_contract.apply_v2_contract (allowed_conflict_results)",
            "trigger_condition": "pair is in the ticker's allowed_conflicts",
            "evidence_requirement": "none -- legal structures, never mandatory outputs; absence is never a failure",
            "verdict_result": ["observed_admitted", "observed_candidate", "not_observed", VERDICT_NOT_EVALUABLE],
        },
        RULE_FAMILY_FORBIDDEN_DOMINANT_WITHOUT_STRONG_EVIDENCE: {
            "config_source": (
                f"{resolved_label_v1_path.name}: {DOMINANCE_GUARD_KEY} (the v0.1 runtime field; the v0.2 file carries an "
                "identical copy and effective_rules() refuses the execution if the two differ)"
            ),
            "applicable_target": "Alpha, per ticker",
            "execution_function": "evaluator.dominance_guard_flags",
            "trigger_condition": "Alpha is listed in the ticker's should_not_be_dominant_without_strong_evidence AND reached dominant/regime_level status",
            "evidence_requirement": "none to trigger the flag itself -- flags for human review (the evidence counts are reported next to the flag), never auto-fails",
            "verdict_result": ["review_required", "not_triggered", VERDICT_NOT_EVALUABLE],
        },
    }

    tickers_block = label_v2.get("tickers") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "taxonomy": {
            "path": _display_path(resolved_taxonomy_path),
            "sha256": _sha256_file(resolved_taxonomy_path),
            "declared_alpha_count": len(taxonomy),
            "schema_version": taxonomy_meta.get("schema_version"),
            "content_version": taxonomy_meta.get("content_version"),
            "canonical_conflict_pairs": list(label_v2.get("canonical_conflict_pairs") or ()),
        },
        "label_v2": {
            "path": _display_path(resolved_label_path),
            "sha256": _sha256_file(resolved_label_path),
            "label_version": label_v2.get("label_version"),
            "evaluation_mode": label_v2.get("evaluation_mode"),
            "status": label_v2.get("status"),
            "evaluation_authority": label_v2.get("evaluation_authority"),
            "formal_product_owner_approval": label_v2.get("formal_product_owner_approval"),
            "approved_by": label_v2.get("approved_by"),
            "taxonomy_version": label_v2.get("taxonomy_version"),
            "taxonomy_content_version": label_v2.get("taxonomy_content_version"),
        },
        "label_v1": {
            "path": _display_path(resolved_label_v1_path),
            "sha256": _sha256_file(resolved_label_v1_path),
            "label_version": label_v1.get("label_version"),
            "used_for": f"{RULE_FAMILY_FORBIDDEN_DOMINANT_WITHOUT_STRONG_EVIDENCE} ({DOMINANCE_GUARD_KEY})",
        },
        "ticker_rule_keys": dict(sorted(TICKER_RULE_KEY_ROLES.items())),
        "declared_but_not_evaluated": {
            "run_bound_expectations": sorted(
                str(t) for t, block in tickers_block.items() if block.get("run_bound_expectations") is not None
            ),
        },
        "rule_families": rule_family_definitions,
    }


# ---------------------------------------------------------------------------
# B2 admissibility lookup (read-only extraction, never a re-judgment)
# ---------------------------------------------------------------------------


def pair_admissibility_lookup(conflict_payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Keys every ``arbitration.candidate_evaluations`` entry by its
    canonical pair id. Never recomputes admissibility -- only re-indexes
    the SAME already-persisted per-pair ``admissibility``/``outcome``
    fields ``conflict_detector.detect_alpha_conflicts`` already wrote."""
    lookup: dict[str, dict[str, Any]] = {}
    if not isinstance(conflict_payload, dict):
        return lookup
    arbitration = conflict_payload.get("arbitration") or {}
    for entry in arbitration.get("candidate_evaluations") or ():
        if not isinstance(entry, dict):
            continue
        alpha_a, alpha_b = entry.get("alpha_a"), entry.get("alpha_b")
        if not alpha_a or not alpha_b:
            continue
        a, b = canonical_pair_key(str(alpha_a), str(alpha_b))
        pair_id = conflict_id(a, b)
        admissibility = entry.get("admissibility") or {}
        lookup[pair_id] = {
            "outcome": entry.get("outcome"),
            "admissibility_status": admissibility.get("status"),
            "reason_codes": list(admissibility.get("reason_codes") or ()),
            "bull_supporting_evidence_count": admissibility.get("bull_supporting_evidence_count"),
            "bear_supporting_evidence_count": admissibility.get("bear_supporting_evidence_count"),
            "bull_score": admissibility.get("bull_score"),
            "bear_score": admissibility.get("bear_score"),
        }
    return lookup


def _evidence_present(entry: dict[str, Any] | None) -> bool:
    if entry is None:
        return False
    bull = entry.get("bull_supporting_evidence_count")
    bear = entry.get("bear_supporting_evidence_count")
    return (
        isinstance(bull, int)
        and isinstance(bear, int)
        and bull >= EVIDENCE_PRESENT_MIN_SUPPORTING_EVIDENCE_PER_SIDE
        and bear >= EVIDENCE_PRESENT_MIN_SUPPORTING_EVIDENCE_PER_SIDE
    )


# ---------------------------------------------------------------------------
# Rule family 1: must_detect_if_evidence_present (new)
# ---------------------------------------------------------------------------


def evaluate_must_detect_if_evidence_present(
    *, ticker_v2_label: dict[str, Any] | None, admissibility_lookup: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    results = []
    for pair in sorted((ticker_v2_label or {}).get("required_conflicts") or ()):
        entry = admissibility_lookup.get(pair)
        evidence_present = _evidence_present(entry)
        if entry is None:
            verdict = VERDICT_NOT_APPLICABLE
            detail = "pair never reached B2 arbitration (no candidate_evaluations entry) -- no evidence to require detection of"
        elif not evidence_present:
            verdict = VERDICT_NOT_APPLICABLE
            detail = "evidence below the evidence-present bar on at least one side -- rule does not trigger"
        elif entry.get("admissibility_status") == B2_ADMITTED:
            verdict = VERDICT_PASS
            detail = "evidence present and pair was admitted"
        else:
            verdict = VERDICT_FAIL
            detail = "evidence present on both sides but pair was not admitted -- a genuine miss"
        results.append(
            {
                "pair": pair,
                "evidence_present": evidence_present,
                "admissibility_status": entry.get("admissibility_status") if entry else None,
                "verdict": verdict,
                "detail": detail,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Rule family 2: should_detect_if_supported (new)
# ---------------------------------------------------------------------------


def evaluate_should_detect_if_supported(
    *,
    ticker_v2_label: dict[str, Any] | None,
    admissibility_lookup: dict[str, dict[str, Any]],
    stance_source_value: str,
) -> list[dict[str, Any]]:
    results = []
    stance_reliable = stance_source_value in (STANCE_SOURCE_LLM_SEMANTIC, STANCE_SOURCE_MIXED)
    for pair in sorted((ticker_v2_label or {}).get("conditional_conflicts") or ()):
        entry = admissibility_lookup.get(pair)
        evidence_present = _evidence_present(entry)
        if not evidence_present:
            verdict = VERDICT_NOT_APPLICABLE
            detail = "evidence below the evidence-present bar -- rule does not trigger"
        elif not stance_reliable:
            verdict = VERDICT_PENDING_REVIEW
            detail = (
                f"evidence present but stance_source={stance_source_value!r} -- offline replay never ran "
                "LLM-semantic stance resolution, so 'supported' cannot be reliably judged here"
            )
        elif entry.get("admissibility_status") == B2_ADMITTED:
            verdict = VERDICT_PASS
            detail = "evidence present, stance reliable, pair was admitted"
        else:
            verdict = VERDICT_NEEDS_REVIEW
            detail = "evidence present with reliable stance but pair was not admitted -- soft miss, flagged for review, never a hard fail"
        results.append(
            {
                "pair": pair,
                "evidence_present": evidence_present,
                "stance_source": stance_source_value,
                "admissibility_status": entry.get("admissibility_status") if entry else None,
                "verdict": verdict,
                "detail": detail,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Rule family 4: do_not_force (new) -- a run-wide invariant, not a per-pair
# verdict: proves the acceptance engine and B2 itself never promoted a pair
# to admitted without B2's own evidence gate agreeing.
# ---------------------------------------------------------------------------


def evaluate_do_not_force_invariant(
    *, evaluate_ticker_result: dict[str, Any], admissibility_lookup: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    violations = []
    for pair in evaluate_ticker_result.get("admitted_conflicts") or ():
        entry = admissibility_lookup.get(pair)
        if entry is None or entry.get("admissibility_status") != B2_ADMITTED:
            violations.append(
                {
                    "pair": pair,
                    "found_admissibility_status": entry.get("admissibility_status") if entry else "NO_ARBITRATION_ENTRY",
                }
            )
    return {
        "verdict": "invariant_violated" if violations else "invariant_held",
        "violations": violations,
        "detail": (
            "every conflicts.json-admitted pair has a matching B2-admitted arbitration entry"
            if not violations
            else "at least one admitted pair lacks a matching B2-admitted arbitration entry -- admission was forced outside B2's own gate"
        ),
    }


# Round 5 (2026-10-04), closing John's own explicit scenario (f): "实际冲突
# 不在标的验收列表 -> 保留研究输出，转入复核，不改答案" (an actual admitted
# conflict outside the ticker's own acceptance list -> keep the research
# output, ROUTE TO REVIEW, never change the answer). Before this, an
# admitted pair matching none of required/conditional/allowed/
# product_decision_pending/remove_while_undeclared produced formal_status
# "pass" with ZERO signal anywhere in the result that it existed -- never
# actually routed to review, only silently not-failed. This detects that
# exact gap and surfaces it; run_formal_acceptance below also now folds a
# non-empty result into needs_review, never into fail (never changes the
# research answer or the conflict's own admission).
def _undeclared_admitted_conflicts(
    *, ticker_v2_label: dict[str, Any] | None, evaluate_ticker_result: dict[str, Any]
) -> list[str]:
    label = ticker_v2_label or {}
    declared = (
        set(label.get("required_conflicts") or ())
        | set(label.get("conditional_conflicts") or ())
        | set(label.get("allowed_conflicts") or ())
        | set(label.get("product_decision_pending") or ())
        | set(label.get("remove_while_undeclared") or ())
    )
    admitted = set(evaluate_ticker_result.get("admitted_conflicts") or ())
    return sorted(admitted - declared)


# ---------------------------------------------------------------------------
# Rule families 3, 5, 6: reused directly from existing, unmodified modules
# ---------------------------------------------------------------------------


def evaluate_conditional_only(v2_contract_result: dict[str, Any]) -> list[dict[str, Any]]:
    return list(v2_contract_result.get("conditional_conflict_results") or ())


def evaluate_allowed_main_conflicts(v2_contract_result: dict[str, Any]) -> list[dict[str, Any]]:
    return list(v2_contract_result.get("allowed_conflict_results") or ())


def evaluate_forbidden_dominant_without_strong_evidence(
    *,
    label_block_v1: dict[str, Any] | None,
    graph_payload: dict[str, Any],
    exposure_seed_for_ticker: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return dominance_guard_flags(label_block_v1, graph_payload, exposure_seed_for_ticker)


# ---------------------------------------------------------------------------
# Unified per-ticker orchestration
# ---------------------------------------------------------------------------


def _ticker_is_evaluable(evaluate_ticker_result: dict[str, Any]) -> bool:
    return (
        evaluate_ticker_result.get("run_selection_status") == "selected"
        and evaluate_ticker_result.get("offline_reprocess_status") == "completed"
        and evaluate_ticker_result.get("artifact_completeness") == "pass"
    )


SEMANTIC_INPUT_REASON_MISSING = "ALPHA_MATCHES_PAYLOAD_MISSING"
SEMANTIC_INPUT_REASON_UNPARSEABLE = "ALPHA_MATCHES_PAYLOAD_UNPARSEABLE"
SEMANTIC_INPUT_REASON_ALL_UNAVAILABLE = "ALL_CLAIMS_MATCH_STATUS_UNAVAILABLE"


def _semantic_input_reason_code(alpha_matches_payload: Any) -> str | None:
    """Returns a reason code when ``alpha_matches_payload`` cannot support a
    genuine formal-acceptance verdict, or ``None`` when it is usable
    (including a genuinely empty ``matches`` list -- a ticker legitimately
    having zero relevant claims is a real, rule-family-handled state, never
    conflated with "the caller never supplied real semantic input at all").

    2026-09-30 closing fix: ``alpha_matches_payload`` is now a REQUIRED
    keyword argument on :func:`run_formal_acceptance` (no default) --
    every caller must pass SOMETHING, so a caller can no longer silently
    omit it and fall through to the pre-gate PASS-defaulting behavior this
    function exists to close. ``None`` (a caller passing it explicitly, or
    Python's own "I have nothing real to pass" idiom) is itself one of the
    three explicit failure reasons below, never a silent bypass.

    - MISSING: ``None`` was passed -- no semantic input available at all.
    - UNPARSEABLE: present but not the expected ``{"matches": [...]}``
      shape (a real structural/plumbing defect, never guessed past).
    - ALL_CLAIMS_MATCH_STATUS_UNAVAILABLE: a genuine, non-empty match list
      where EVERY claim carries ``match_status == "unavailable"`` --
      Architecture Replay's own deterministic, by-design signal (see
      replay/pipeline.py's own module docstring: llm_gateway=None makes
      every claim's Alpha semantic state UNAVAILABLE, never a fabricated
      NONE, never silently rewritten to "none" here either).
    """
    if alpha_matches_payload is None:
        return SEMANTIC_INPUT_REASON_MISSING
    if not isinstance(alpha_matches_payload, Mapping):
        return SEMANTIC_INPUT_REASON_UNPARSEABLE
    matches = alpha_matches_payload.get("matches")
    if not isinstance(matches, list):
        return SEMANTIC_INPUT_REASON_UNPARSEABLE
    if not matches:
        return None
    if all(isinstance(m, Mapping) and m.get("match_status") == "unavailable" for m in matches):
        return SEMANTIC_INPUT_REASON_ALL_UNAVAILABLE
    return None


def resolve_ticker_rules(
    *, ticker: str, ticker_v2_label: dict[str, Any] | None, label_block_v1: dict[str, Any] | None
) -> dict[str, Any]:
    """What this ticker's rules RESOLVED to: the declared inputs of every rule family, so a verdict can be read without opening the YAML files.
    Mirrors exactly what the families below consume (the dominance guard comes from the v0.1 block, as the family itself does)."""
    label = ticker_v2_label or {}
    guard = (label_block_v1 or {}).get(DOMINANCE_GUARD_KEY) or {}

    def pairs(key: str) -> list[str]:
        return sorted(str(pair) for pair in (label.get(key) or ()))

    pending = sorted(
        str(entry.get("pair_id")) if isinstance(entry, Mapping) else str(entry)
        for entry in (label.get("product_decision_pending") or ())
    )
    return {
        "ticker": ticker,
        RULE_FAMILY_MUST_DETECT_IF_EVIDENCE_PRESENT: {"source_field": "required_conflicts", "pairs": pairs("required_conflicts")},
        RULE_FAMILY_SHOULD_DETECT_IF_SUPPORTED: {"source_field": "conditional_conflicts", "pairs": pairs("conditional_conflicts")},
        RULE_FAMILY_CONDITIONAL_ONLY: {"source_field": "conditional_conflicts", "pairs": pairs("conditional_conflicts")},
        RULE_FAMILY_ALLOWED_MAIN_CONFLICTS: {"source_field": "allowed_conflicts", "pairs": pairs("allowed_conflicts")},
        RULE_FAMILY_DO_NOT_FORCE: {"scope": "every admitted conflict of the run (an invariant; nothing is declared per ticker)"},
        RULE_FAMILY_FORBIDDEN_DOMINANT_WITHOUT_STRONG_EVIDENCE: {
            "source_field": DOMINANCE_GUARD_KEY,
            "guarded_alphas": {str(k): v for k, v in sorted(guard.items())},
        },
        "context_only": {"product_decision_pending": pending, "remove_while_undeclared": pairs("remove_while_undeclared")},
    }


def _coverage(
    *,
    ticker_v2_label: dict[str, Any] | None,
    admissibility_lookup: dict[str, dict[str, Any]],
    admitted: set[str],
    guard_map: Mapping[str, Any],
    dominance_results: list[dict[str, Any]],
    formal_status: str,
) -> dict[str, Any]:
    """How much of what was declared actually had something to evaluate. A PASS is only as strong as this: it says no declared rule was violated,
    and when no declared conflict pair had supporting evidence on both sides (or was admitted), no conflict rule had evidence to look at. A pair
    that merely appeared in arbitration with no supporting evidence does not count: the evidence-conditional rules treat it as not applicable."""
    label = ticker_v2_label or {}
    declared = (
        set(label.get("required_conflicts") or ())
        | set(label.get("conditional_conflicts") or ())
        | set(label.get("allowed_conflicts") or ())
    )
    with_evidence = {pair for pair in declared if pair in admitted or _evidence_present(admissibility_lookup.get(pair))}
    vacuous = formal_status == FORMAL_STATUS_PASS and not with_evidence and not admitted
    return {
        "declared_conflict_pairs": len(declared),
        "declared_pairs_with_evidence": len(with_evidence),
        "admitted_conflicts_checked_by_do_not_force": len(admitted),
        "dominance_guards_declared": len(guard_map),
        "dominance_guards_triggered": len(dominance_results),
        "pass_is_vacuous": vacuous,
        "reading": (
            "PASS means no declared rule was violated. None of the declared conflict pairs had supporting evidence on both sides and no conflict "
            "was admitted, so no conflict rule had evidence to evaluate."
            if vacuous
            else None
        ),
    }


def run_formal_acceptance(
    *,
    ticker: str,
    ticker_v2_label: dict[str, Any] | None,
    label_block_v1: dict[str, Any] | None,
    evaluate_ticker_result: dict[str, Any],
    conflict_payload: dict[str, Any] | None,
    graph_payload: dict[str, Any],
    alpha_matches_payload: dict[str, Any] | None,
    exposure_seed_for_ticker: dict[str, Any] | None = None,
    taxonomy_path: str | Path | None = None,
    label_v2_path: str | Path | None = None,
    label_v1_path: str | Path | None = None,
) -> dict[str, Any]:
    """The single formal acceptance entry point: resolves ``effective_rules``
    (raising, never silently falling back, on a config problem), executes
    all six rule families, and returns one machine-readable per-ticker
    verdict. A required rule family that cannot execute, or a ticker whose
    own source artifacts are incomplete, always blocks ``formal_status ==
    "pass"`` -- never masked as ``not_applicable``.

    ``alpha_matches_payload`` is REQUIRED, no default (2026-09-30 closing
    fix): ``None`` is an explicit, valid value meaning "I have none", itself
    one of the checked failure modes below, never a silent get-out.

    Checked, in order, BEFORE any rule family runs:
      1. ``effective_rules()`` itself -- ``CONFIG_ERROR`` on failure (a missing
         or malformed file, a label file that does not fit the taxonomy that
         was named, a version mismatch, an unimplemented rule key, two copies
         of one rule that disagree). This is the only status that omits
         ``effective_rules`` (resolving it is what failed).
      2. ``alpha_matches_payload`` missing / unparseable / every claim
         ``match_status == "unavailable"`` -- ``ALPHA_SEMANTIC_UNAVAILABLE``,
         never a PASS and never rewritten to ``"none"``.
      3. ``_ticker_is_evaluable`` -- ``NOT_EVALUABLE`` on incomplete artifacts.
      4. (T2, 2026-10-07) ``ticker_v2_label is None`` -- the rule file declares
         nothing for this ticker: ``CONFIG_ERROR`` with
         ``ACCEPTANCE_TICKER_RULES_NOT_DECLARED``. Before this, a ticker with no
         rules went straight to PASS (every family was empty).
      5. The six rule families, exactly as before.

    The overall verdict follows the families, not the legacy v0.2 contract
    view: a required pair with no supporting evidence is ``not_applicable``
    (John: "no supporting evidence -> never forced"); only the evidence-present
    miss, a violated ``do_not_force`` invariant, or a failed ticker consistency
    check is a ``fail``. ``v2_contract_result`` stays in the verdict as the
    unconditional, report-only view."""
    try:
        rules = effective_rules(taxonomy_path=taxonomy_path, label_v2_path=label_v2_path, label_v1_path=label_v1_path)
    except AcceptanceConfigError as exc:
        return {
            "ticker": ticker,
            "formal_status": FORMAL_STATUS_CONFIG_ERROR,
            "config_error_reason_code": exc.reason_code,
            "config_error_detail": exc.detail,
            "rule_family_results": {},
        }

    semantic_input_reason_code = _semantic_input_reason_code(alpha_matches_payload)
    if semantic_input_reason_code is not None:
        return {
            "ticker": ticker,
            "formal_status": FORMAL_STATUS_ALPHA_SEMANTIC_UNAVAILABLE,
            "effective_rules": rules,
            "semantic_input_reason_code": semantic_input_reason_code,
            "reason": (
                "alpha_matches_payload was not provided"
                if semantic_input_reason_code == SEMANTIC_INPUT_REASON_MISSING
                else "alpha_matches_payload is not in the expected {'matches': [...]} shape"
                if semantic_input_reason_code == SEMANTIC_INPUT_REASON_UNPARSEABLE
                else (
                    "every claim in this run's own alpha_matches carries "
                    "match_status=='unavailable' -- Alpha semantic authority was never "
                    "exercised for this run (e.g. Architecture Replay)"
                )
            ),
            "rule_family_results": {},
        }

    if not _ticker_is_evaluable(evaluate_ticker_result):
        return {
            "ticker": ticker,
            "formal_status": FORMAL_STATUS_NOT_EVALUABLE,
            "effective_rules": rules,
            "reason": "source run artifacts incomplete or offline reprocess did not complete -- see evaluate_ticker_result.artifact_missing_files",
            "artifact_missing_files": evaluate_ticker_result.get("artifact_missing_files") or [],
            "rule_family_results": {},
        }

    if ticker_v2_label is None:
        return {
            "ticker": ticker,
            "formal_status": FORMAL_STATUS_CONFIG_ERROR,
            "config_error_reason_code": REASON_TICKER_RULES_NOT_DECLARED,
            "config_error_detail": (
                f"{rules['label_v2']['path']} declares no rules for ticker {ticker!r}; a formal verdict cannot be certified without them"
            ),
            "effective_rules": rules,
            "rule_family_results": {},
        }

    guard_v2 = ticker_v2_label.get(DOMINANCE_GUARD_KEY)
    guard_v1 = (label_block_v1 or {}).get(DOMINANCE_GUARD_KEY)
    if guard_v2 and guard_v1 and guard_v2 != guard_v1:
        return {
            "ticker": ticker,
            "formal_status": FORMAL_STATUS_CONFIG_ERROR,
            "config_error_reason_code": REASON_RULE_SOURCES_DISAGREE,
            "config_error_detail": f"{DOMINANCE_GUARD_KEY} differs between the v0.1 block and the v0.2 block handed in for {ticker!r}",
            "effective_rules": rules,
            "rule_family_results": {},
        }

    admissibility_lookup = pair_admissibility_lookup(conflict_payload)
    v2_contract_result = apply_v2_contract(
        ticker=ticker, ticker_v2_label=ticker_v2_label, evaluate_ticker_result=evaluate_ticker_result
    )

    must_detect_results = evaluate_must_detect_if_evidence_present(
        ticker_v2_label=ticker_v2_label, admissibility_lookup=admissibility_lookup
    )
    should_detect_results = evaluate_should_detect_if_supported(
        ticker_v2_label=ticker_v2_label,
        admissibility_lookup=admissibility_lookup,
        stance_source_value=evaluate_ticker_result.get("stance_source", "unavailable"),
    )
    do_not_force_result = evaluate_do_not_force_invariant(
        evaluate_ticker_result=evaluate_ticker_result, admissibility_lookup=admissibility_lookup
    )
    conditional_only_results = evaluate_conditional_only(v2_contract_result)
    allowed_main_conflicts_results = evaluate_allowed_main_conflicts(v2_contract_result)
    dominance_results = evaluate_forbidden_dominant_without_strong_evidence(
        label_block_v1=label_block_v1,
        graph_payload=graph_payload,
        exposure_seed_for_ticker=exposure_seed_for_ticker,
    )
    undeclared_admitted_conflicts = _undeclared_admitted_conflicts(
        ticker_v2_label=ticker_v2_label, evaluate_ticker_result=evaluate_ticker_result
    )

    rule_family_results = {
        RULE_FAMILY_MUST_DETECT_IF_EVIDENCE_PRESENT: must_detect_results,
        RULE_FAMILY_SHOULD_DETECT_IF_SUPPORTED: should_detect_results,
        RULE_FAMILY_CONDITIONAL_ONLY: conditional_only_results,
        RULE_FAMILY_DO_NOT_FORCE: do_not_force_result,
        RULE_FAMILY_ALLOWED_MAIN_CONFLICTS: allowed_main_conflicts_results,
        RULE_FAMILY_FORBIDDEN_DOMINANT_WITHOUT_STRONG_EVIDENCE: dominance_results,
    }

    # Every reason a verdict is not a PASS, listed once, so the status and every table / summary rendered from this result cannot disagree.
    failure_reasons: list[dict[str, Any]] = [
        {"family": RULE_FAMILY_MUST_DETECT_IF_EVIDENCE_PRESENT, "pair": r["pair"], "detail": r["detail"]}
        for r in must_detect_results
        if r["verdict"] == VERDICT_FAIL
    ]
    if do_not_force_result["verdict"] == "invariant_violated":
        failure_reasons.append(
            {
                "family": RULE_FAMILY_DO_NOT_FORCE,
                "pairs": [v["pair"] for v in do_not_force_result["violations"]],
                "detail": do_not_force_result["detail"],
            }
        )
    if evaluate_ticker_result.get("ticker_consistency") == "fail":
        failure_reasons.append({"family": "ticker_consistency", "detail": "the run's own ticker consistency check failed"})

    review_reasons: list[dict[str, Any]] = [
        {"family": RULE_FAMILY_SHOULD_DETECT_IF_SUPPORTED, "pair": r["pair"], "verdict": r["verdict"], "detail": r["detail"]}
        for r in should_detect_results
        if r["verdict"] in (VERDICT_NEEDS_REVIEW, VERDICT_PENDING_REVIEW)
    ]
    review_reasons += [
        {"family": RULE_FAMILY_FORBIDDEN_DOMINANT_WITHOUT_STRONG_EVIDENCE, "alpha_id": flag["alpha_id"], "verdict": "review_required"}
        for flag in dominance_results
    ]
    review_reasons += [
        {"family": "undeclared_admitted_conflict", "pair": pair, "verdict": "review_required"}
        for pair in undeclared_admitted_conflicts
    ]

    if failure_reasons:
        formal_status = FORMAL_STATUS_FAIL
    elif review_reasons:
        formal_status = FORMAL_STATUS_NEEDS_REVIEW
    else:
        formal_status = FORMAL_STATUS_PASS

    resolved_rules = {**rules, "ticker_rules": resolve_ticker_rules(ticker=ticker, ticker_v2_label=ticker_v2_label, label_block_v1=label_block_v1)}
    return {
        "ticker": ticker,
        "formal_status": formal_status,
        "effective_rules": resolved_rules,
        "rule_family_results": rule_family_results,
        "undeclared_admitted_conflicts": undeclared_admitted_conflicts,
        "failure_reasons": failure_reasons,
        "review_reasons": review_reasons,
        "coverage": _coverage(
            ticker_v2_label=ticker_v2_label,
            admissibility_lookup=admissibility_lookup,
            admitted=set(evaluate_ticker_result.get("admitted_conflicts") or ()),
            guard_map=(label_block_v1 or {}).get(DOMINANCE_GUARD_KEY) or {},
            dominance_results=dominance_results,
            formal_status=formal_status,
        ),
        "v2_contract_result": v2_contract_result,
        "v2_contract_note": (
            "v2_contract_result is the unconditional v0.2 contract view (report only). The verdict follows the rule families above: "
            "a required pair with no supporting evidence is not_applicable there, never a fail."
        ),
    }


__all__ = [
    "SCHEMA_VERSION",
    "ALL_RULE_FAMILIES",
    "RULE_FAMILY_MUST_DETECT_IF_EVIDENCE_PRESENT",
    "RULE_FAMILY_SHOULD_DETECT_IF_SUPPORTED",
    "RULE_FAMILY_CONDITIONAL_ONLY",
    "RULE_FAMILY_DO_NOT_FORCE",
    "RULE_FAMILY_ALLOWED_MAIN_CONFLICTS",
    "RULE_FAMILY_FORBIDDEN_DOMINANT_WITHOUT_STRONG_EVIDENCE",
    "VERDICT_PASS",
    "VERDICT_FAIL",
    "VERDICT_NOT_APPLICABLE",
    "VERDICT_NEEDS_REVIEW",
    "VERDICT_PENDING_REVIEW",
    "VERDICT_NOT_EVALUABLE",
    "FORMAL_STATUS_CONFIG_ERROR",
    "FORMAL_STATUS_NOT_EVALUABLE",
    "FORMAL_STATUS_FAIL",
    "FORMAL_STATUS_NEEDS_REVIEW",
    "FORMAL_STATUS_PASS",
    "FORMAL_STATUS_ALPHA_SEMANTIC_UNAVAILABLE",
    "FORMAL_STATUS_EXECUTION_ERROR",
    "IMPLEMENTED_TICKER_RULE_KEYS",
    "TICKER_RULE_KEY_ROLES",
    "resolve_ticker_rules",
    "SEMANTIC_INPUT_REASON_MISSING",
    "SEMANTIC_INPUT_REASON_UNPARSEABLE",
    "SEMANTIC_INPUT_REASON_ALL_UNAVAILABLE",
    "AcceptanceConfigError",
    "effective_rules",
    "pair_admissibility_lookup",
    "evaluate_must_detect_if_evidence_present",
    "evaluate_should_detect_if_supported",
    "evaluate_do_not_force_invariant",
    "evaluate_conditional_only",
    "evaluate_allowed_main_conflicts",
    "evaluate_forbidden_dominant_without_strong_evidence",
    "run_formal_acceptance",
]
