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

Round 24 (2026-10-07) corrected two things about those families:

  * ``must_detect_if_evidence_present`` is defined by John's frozen Gold v0.2 contract at the ALPHA level ("must detect an acceptable existing
    Alpha/structure at an official detected level"). The Alpha-layer rules of that contract are now executed by
    :mod:`comqutor_alpha.regression.gold_contract_rules` (trigger from the frozen matrix for its bound run only, otherwise not evaluable). The
    label's pair-level ``required_conflicts`` check stays, but it reuses B2's own recorded result: a pair B2 evaluated and correctly rejected is
    never a "miss"; a pair without a usable record is "not evaluated", never "no evidence"; only a record that satisfies every B2 condition and is
    still not admitted is a missed required conflict.
  * ``should_detect_if_supported`` on ``conditional_conflicts`` has no approval basis (John's contract defines it for Alphas; his baseline lists
    the 16 pairs as allowed, never mandatory). It keeps its result and its source as a DIAGNOSTIC and decides no formal status.

Explicit config, no silent fallback: :func:`effective_rules` always states
the exact taxonomy, label files and Gold contract it resolved and raises
:class:`AcceptanceConfigError` (never falls back to a different file) if
any is missing/malformed/not the frozen one. :func:`run_formal_acceptance`
refuses a formal PASS whenever ``effective_rules`` itself failed, or the
ticker's own source artifacts are incomplete -- it never uses
``not_applicable`` to paper over a config or execution problem.
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
from comqutor_alpha.conflict_engine.conflict_schema import (
    REASON_AMBIGUOUS_ONLY,
    REASON_MISSING_LEFT_EVIDENCE,
    REASON_MISSING_RIGHT_EVIDENCE,
    REASON_ZERO_EVIDENCE_STRENGTH,
    canonical_pair_key,
    conflict_id,
)
from comqutor_alpha.regression import gold_contract_rules as gold
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
    "run_bound_expectations": "unapproved run-bound historical observation: not an executable rule; reported unchanged, decides no verdict",
    "source_basis": "provenance text",
}
IMPLEMENTED_TICKER_RULE_KEYS = frozenset(TICKER_RULE_KEY_ROLES)

# A DESCRIPTIVE "something to look at" bar: at least one stance-confirmed supporting claim on EACH side, read off B2's own
# bull_supporting_evidence_count/bear_supporting_evidence_count. It is an implementation constant with no approval behind it, and since round 24 it
# decides NO verdict: it only feeds the diagnostic should_detect result and the coverage count. A required pair is judged from B2's own recorded
# result (status and reason codes), never from this number -- B2's approved bar is conflict_admissibility.MIN_SUPPORTING_EVIDENCE_PER_SIDE == 2 plus
# score and ticker-specificity conditions, and a pair B2 correctly rejects is not a missed detection.
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


def _contract_families(rule: Mapping[str, Any]) -> list[str]:
    declared = rule.get("rule_type")
    return [declared] if isinstance(declared, str) else [str(item) for item in declared or ()]


def _executed_ids(bundle: gold.GoldContractBundle, family: str) -> list[str]:
    return sorted(
        rule_id for rule_id, rule in bundle.rules_by_id.items() if rule_id in gold.EXECUTED_RULE_IDS and family in _contract_families(rule)
    )


def _not_executed_ids(bundle: gold.GoldContractBundle, family: str) -> list[str]:
    return sorted(
        rule_id for rule_id, rule in bundle.rules_by_id.items() if rule_id not in gold.EXECUTED_RULE_IDS and family in _contract_families(rule)
    )


def _non_executable_declarations(tickers_block: Mapping[str, Any]) -> dict[str, Any]:
    """Declarations in the label file that no rule executes, said for what they are. ``run_bound_expectations`` is a run-bound historical
    observation: the label file itself says no formal approval exists for the run, and J2 v0.2 allows a run-bound expectation to be strict only once
    fully bound AND approved. It is reported unchanged and decides no verdict."""
    run_bound = {}
    for ticker, block in tickers_block.items():
        declared = block.get("run_bound_expectations")
        if declared is not None:
            run_bound[str(ticker)] = {
                "classification": "unapproved_historical_observation",
                "executable": False,
                "reference_run_id": declared.get("reference_run_id"),
                "analysis_date": declared.get("analysis_date"),
                "observed_historical_main_conflict": declared.get("observed_historical_main_conflict"),
                "approval": "none: the label file is provisional / shadow / approval pending and states that no formal approval exists for this run",
                "consumed_by": ["evaluation_contract.apply_v2_contract: passed through unchanged into v2_contract_result (report only)"],
                "effect_on_formal_status": "none",
            }
    return {"run_bound_expectations": run_bound} if run_bound else {}


def _rule_status(bundle: gold.GoldContractBundle, tickers_block: Mapping[str, Any]) -> dict[str, Any]:
    """Per family and scope: is it executed as defined, kept as a diagnostic, not evaluable on some runs, or not executed at all."""
    declared_pairs = sum(
        len(set(block.get("required_conflicts") or ()) | set(block.get("conditional_conflicts") or ()) | set(block.get("allowed_conflicts") or ()))
        for block in tickers_block.values()
    )
    required_pairs = sum(len(block.get("required_conflicts") or ()) for block in tickers_block.values())
    trigger_limit = "the trigger is established only for the run the frozen matrix is bound to; for every other run the rule is not_evaluable"
    return {
        "legend": {
            "aligned_execution": "executed as John's text or an approved record defines it (a contract scope is evaluable only on the run the frozen matrix is bound to; elsewhere it is reported not_evaluable)",
            "diagnostic_only": "executed and reported with its source, but decides no formal status (no approval basis)",
            "not_in_effect": "defined by the frozen contract but not executed by this entry; nothing is implied about it",
        },
        "families": {
            RULE_FAMILY_MUST_DETECT_IF_EVIDENCE_PRESENT: [
                {
                    "scope": "alpha_layer_contract",
                    "status": "aligned_execution",
                    "rules": _executed_ids(bundle, RULE_FAMILY_MUST_DETECT_IF_EVIDENCE_PRESENT),
                    "limits": trigger_limit,
                },
                {
                    "scope": "conflict_pair_label",
                    "status": "aligned_execution",
                    "config_source": "required_conflicts",
                    "declared_required_pairs": required_pairs,
                    "limits": "only a record that satisfies every B2 condition and is still not admitted is a miss; no ticker declares a required pair today",
                },
            ],
            RULE_FAMILY_SHOULD_DETECT_IF_SUPPORTED: [
                {"scope": "alpha_layer_contract", "status": "not_in_effect", "rules": _not_executed_ids(bundle, RULE_FAMILY_SHOULD_DETECT_IF_SUPPORTED)},
                {
                    "scope": "conflict_pair_label",
                    "status": "diagnostic_only",
                    "config_source": "conditional_conflicts",
                    "reason": "no approval basis: the contract defines should_detect for Alphas; the baseline lists these pairs as allowed, never mandatory",
                },
            ],
            RULE_FAMILY_CONDITIONAL_ONLY: [
                {
                    "scope": "conflict_structure_contract",
                    "status": "aligned_execution",
                    "rules": _executed_ids(bundle, RULE_FAMILY_CONDITIONAL_ONLY),
                    "logic": "any ONE allowed pair admitted satisfies the composite",
                    "limits": trigger_limit,
                },
                {"scope": "conflict_pair_label", "status": "aligned_execution", "config_source": "conditional_conflicts", "reading": "informational mismatch only"},
                {"scope": "alpha_layer_contract", "status": "not_in_effect", "rules": _not_executed_ids(bundle, RULE_FAMILY_CONDITIONAL_ONLY)},
            ],
            RULE_FAMILY_DO_NOT_FORCE: [
                {"scope": "conflict_invariant", "status": "aligned_execution", "reading": "every admitted conflict has a B2-admitted arbitration record"},
                {"scope": "alpha_layer_contract", "status": "not_in_effect", "rules": [], "reading": "the contract defines it as a cross-cutting constraint, not a standalone rule"},
            ],
            RULE_FAMILY_ALLOWED_MAIN_CONFLICTS: [
                {
                    "scope": "conflict_pair_label",
                    "status": "aligned_execution",
                    "declared_pairs": declared_pairs,
                    "reading": "legal structures, never mandatory outputs: a pair's absence raises no review and no failure; an admitted pair declared nowhere is routed to review",
                }
            ],
            RULE_FAMILY_FORBIDDEN_DOMINANT_WITHOUT_STRONG_EVIDENCE: [
                {
                    "scope": "label_dominance_guard",
                    "status": "aligned_execution",
                    "config_source": f"label v0.1 {DOMINANCE_GUARD_KEY}",
                    "limits": "its guarded Alphas are the label's own, not the scope of the contract's two negative-control rules",
                },
                {
                    "scope": "alpha_layer_contract",
                    "status": "not_in_effect",
                    "rules": _not_executed_ids(bundle, RULE_FAMILY_FORBIDDEN_DOMINANT_WITHOUT_STRONG_EVIDENCE),
                },
            ],
        },
    }


def effective_rules(
    *,
    taxonomy_path: str | Path | None = None,
    label_v2_path: str | Path | None = None,
    label_v1_path: str | Path | None = None,
    gold_contract_path: str | Path | None = None,
    gold_freeze_manifest_path: str | Path | None = None,
    trigger_matrix_path: str | Path | None = None,
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
      * the two copies of the dominance guard (v0.1 and v0.2) disagree;
      * (round 24) John's Gold v0.2 contract, its freeze manifest or the trigger matrix is missing, malformed, of another version, not the frozen
        file (sha256 recorded by the freeze), or lacks / changes a contract rule this engine executes."""
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
    try:
        bundle = gold.load_gold_contract_bundle(
            contract_path=gold_contract_path, freeze_manifest_path=gold_freeze_manifest_path, trigger_matrix_path=trigger_matrix_path
        )
    except gold.GoldContractError as exc:
        raise AcceptanceConfigError(exc.reason_code, exc.detail) from exc

    resolved_contract_name = bundle.contract_path.name
    rule_family_definitions = {
        RULE_FAMILY_MUST_DETECT_IF_EVIDENCE_PRESENT: {
            "config_source": (
                f"{resolved_contract_name}: ALPHA_HIT rules {', '.join(_executed_ids(bundle, RULE_FAMILY_MUST_DETECT_IF_EVIDENCE_PRESENT))} "
                f"(Alpha layer, John's frozen Gold v0.2 contract); {resolved_label_path.name}: required_conflicts (conflict-pair layer)"
            ),
            "applicable_target": "Alpha, per contract rule and ticker (Alpha layer); declared conflict pair, per ticker (pair layer)",
            "execution_function": (
                "gold_contract_rules.evaluate_alpha_rule (Alpha layer); acceptance_engine.evaluate_must_detect_if_evidence_present (pair layer)"
            ),
            "trigger_condition": (
                "Alpha layer: the frozen evidence-trigger matrix says PRESENT for the rule AND the evaluated run is the run the matrix is bound to "
                "(for any other run the trigger is NOT_EVALUABLE: no approved executable method determines it and a historical state is never carried "
                "over). Pair layer: the pair is in the ticker's required_conflicts"
            ),
            "evidence_requirement": (
                "Alpha layer: the Alpha's level in run_audit.json (activation_summary.per_alpha) is active, dominant or regime_level. Pair layer: B2's own "
                "recorded result -- admitted is a pass; evaluated and rejected for a recorded reason is NOT a miss; a record with no rejection reason that "
                "is still not admitted is a miss; no usable record is 'not evaluated', never 'no evidence'"
            ),
            "verdict_result": [VERDICT_PASS, VERDICT_FAIL, VERDICT_NOT_APPLICABLE, gold.VERDICT_NOT_TRIGGERED, VERDICT_NEEDS_REVIEW, VERDICT_NOT_EVALUABLE],
        },
        RULE_FAMILY_SHOULD_DETECT_IF_SUPPORTED: {
            "config_source": (
                f"{resolved_label_path.name}: conditional_conflicts (conflict-pair reading, DIAGNOSTIC ONLY). The contract defines this family for Alphas "
                "(its should_detect rules are not executed by this entry)"
            ),
            "applicable_target": "declared conflict pair, per ticker",
            "execution_function": "acceptance_engine.evaluate_should_detect_if_supported (diagnostic)",
            "trigger_condition": (
                "pair is in the ticker's conditional_conflicts AND at least one stance-confirmed supporting claim is recorded on each side AND "
                "stance_source is llm_semantic or mixed (evaluator.stance_source) -- offline runs with deterministic-baseline-only stance cannot "
                "reliably judge 'supported' and are marked pending_review instead"
            ),
            "evidence_requirement": (
                "descriptive only: >= 1 supporting claim per side (an implementation constant with no approval) AND LLM-semantic stance resolution "
                "actually ran for this replay"
            ),
            "decides_formal_status": False,
            "authority": "implementation_only_unapproved: John's contract defines should_detect for Alphas; his baseline lists these pairs as allowed, never mandatory",
            "verdict_result": [
                VERDICT_PASS,
                VERDICT_NEEDS_REVIEW,
                VERDICT_PENDING_REVIEW,
                VERDICT_NOT_APPLICABLE,
                VERDICT_NOT_EVALUABLE,
            ],
        },
        RULE_FAMILY_CONDITIONAL_ONLY: {
            "config_source": (
                f"{resolved_contract_name}: COMPOSITE_STRUCTURE_HIT rules {', '.join(_executed_ids(bundle, RULE_FAMILY_CONDITIONAL_ONLY))} "
                f"(John's frozen contract); {resolved_label_path.name}: conditional_conflicts (informational reading)"
            ),
            "applicable_target": "composite growth-vs-valuation structure, per contract rule and ticker; declared conflict pair, per ticker",
            "execution_function": (
                "gold_contract_rules.evaluate_composite_rule (composites: ANY ONE allowed pair admitted satisfies the rule); "
                "evaluation_contract.apply_v2_contract (conditional_conflict_results)"
            ),
            "trigger_condition": (
                "composites: the frozen trigger is PRESENT for the bound run (otherwise NOT_EVALUABLE). Pairs: the pair is in the ticker's "
                "conditional_conflicts"
            ),
            "evidence_requirement": (
                "composites: PRESENT and no allowed pair admitted -> REVIEW with adjudication (never an immediate error) unless an allowed pair's own B2 "
                "record lists no rejection reason yet is not admitted (a deterministic violation -> FAIL); ABSENT -> not triggered. "
                "Pairs: none required to trigger; a miss is always informational, never a fail"
            ),
            "verdict_result": [VERDICT_PASS, VERDICT_NEEDS_REVIEW, gold.VERDICT_NOT_TRIGGERED, "informational_mismatch", VERDICT_NOT_EVALUABLE],
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
        "gold_contract": gold.describe_bundle(bundle),
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
        "non_executable_declarations": _non_executable_declarations(tickers_block),
        "rule_status": _rule_status(bundle, tickers_block),
        "rule_families": rule_family_definitions,
    }


# ---------------------------------------------------------------------------
# B2 admissibility lookup (read-only extraction, never a re-judgment)
# ---------------------------------------------------------------------------


PAIR_STATE_ADMITTED = "admitted"
PAIR_STATE_B2_REJECTED = "b2_rejected"
PAIR_STATE_B2_NO_REASON = "b2_not_admitted_without_reason"
PAIR_STATE_NO_QUALIFYING_EVIDENCE = "rejected_before_b2_no_qualifying_evidence"
PAIR_STATE_NOT_EVALUATED = "not_evaluated_before_b2"
PAIR_STATE_NO_RECORD = "no_arbitration_record"

# The detector's own reasons that mean "no qualifying evidence on a side" (conflict_detector._evaluate_candidate): the pair was evaluated and the
# evidence condition is absent. Every other reason a pair is rejected BEFORE the B2 gate (an Alpha not in an admissible activation state, an
# unresolved direction, an invalid weight ...) means B2 never judged the evidence.
_NO_QUALIFYING_EVIDENCE_REASONS = frozenset(
    {REASON_MISSING_LEFT_EVIDENCE, REASON_MISSING_RIGHT_EVIDENCE, REASON_AMBIGUOUS_ONLY, REASON_ZERO_EVIDENCE_STRENGTH}
)


def _evidence_audit_counts(audit: Any) -> dict[str, int | None]:
    counts: dict[str, int | None] = {}
    for side in ("alpha_a", "alpha_b"):
        block = audit.get(side) if isinstance(audit, dict) else None
        counts[side] = block.get("qualifying_count") if isinstance(block, dict) else None
    return counts


def pair_admissibility_lookup(conflict_payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Keys every ``arbitration.candidate_evaluations`` entry by its
    canonical pair id. Never recomputes admissibility -- only re-indexes
    the SAME already-persisted fields ``conflict_detector.detect_alpha_conflicts``
    already wrote: B2's own result when the pair reached the gate
    (``admissibility``), and the detector's own reasons and evidence audit
    when the pair was rejected before it."""
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
            "has_admissibility_block": bool(admissibility),
            "admissibility_status": admissibility.get("status"),
            "reason_codes": list(admissibility.get("reason_codes") or ()),
            "entry_reason_codes": list(entry.get("reason_codes") or ()),
            "bull_supporting_evidence_count": admissibility.get("bull_supporting_evidence_count"),
            "bear_supporting_evidence_count": admissibility.get("bear_supporting_evidence_count"),
            "bull_ticker_specific_support_count": admissibility.get("bull_ticker_specific_support_count"),
            "bear_ticker_specific_support_count": admissibility.get("bear_ticker_specific_support_count"),
            "bull_score": admissibility.get("bull_score"),
            "bear_score": admissibility.get("bear_score"),
            "evidence_audit_counts": _evidence_audit_counts(entry.get("evidence_audit")),
        }
    return lookup


def _evidence_present(entry: dict[str, Any] | None) -> bool:
    """DESCRIPTIVE only (see EVIDENCE_PRESENT_MIN_SUPPORTING_EVIDENCE_PER_SIDE): decides no verdict."""
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


def pair_record_state(entry: dict[str, Any] | None) -> str:
    """What the run's own arbitration record says about one pair -- six distinct situations that must never be mistaken for one another."""
    if entry is None:
        return PAIR_STATE_NO_RECORD
    reached_b2 = entry.get("has_admissibility_block", entry.get("admissibility_status") is not None)
    if reached_b2:
        if entry.get("admissibility_status") == B2_ADMITTED:
            return PAIR_STATE_ADMITTED
        return PAIR_STATE_B2_REJECTED if entry.get("reason_codes") else PAIR_STATE_B2_NO_REASON
    if set(entry.get("entry_reason_codes") or ()) & _NO_QUALIFYING_EVIDENCE_REASONS:
        return PAIR_STATE_NO_QUALIFYING_EVIDENCE
    return PAIR_STATE_NOT_EVALUATED


def _evidence_facts(entry: dict[str, Any] | None) -> dict[str, Any] | None:
    if entry is None:
        return None
    return {
        "bull_supporting_evidence_count": entry.get("bull_supporting_evidence_count"),
        "bear_supporting_evidence_count": entry.get("bear_supporting_evidence_count"),
        "bull_ticker_specific_support_count": entry.get("bull_ticker_specific_support_count"),
        "bear_ticker_specific_support_count": entry.get("bear_ticker_specific_support_count"),
        "bull_score": entry.get("bull_score"),
        "bear_score": entry.get("bear_score"),
        "qualifying_claims_in_evidence_audit": entry.get("evidence_audit_counts"),
    }


def _pair_verdict(state: str, entry: dict[str, Any] | None, declared_pair_count: int | None) -> tuple[str, str]:
    codes = ", ".join((entry or {}).get("reason_codes") or (entry or {}).get("entry_reason_codes") or ()) or "none recorded"
    audit = (entry or {}).get("evidence_audit_counts")
    if state == PAIR_STATE_ADMITTED:
        return VERDICT_PASS, "B2 admitted the pair"
    if state == PAIR_STATE_B2_REJECTED:
        return (
            VERDICT_NOT_APPLICABLE,
            f"B2 evaluated the pair and rejected it ({codes}): the approved admission gate working as designed, not a missed detection -- no conflict "
            "is forced when a side lacks sufficient evidence",
        )
    if state == PAIR_STATE_B2_NO_REASON:
        return (
            VERDICT_FAIL,
            "B2's own record lists no rejection reason (the score, supporting-fact and ticker-specificity conditions it checks are all met) yet the pair "
            "is not admitted: every necessary condition is satisfied and the required conflict is missing",
        )
    if state == PAIR_STATE_NO_QUALIFYING_EVIDENCE:
        return (
            VERDICT_NOT_APPLICABLE,
            f"the detector found no qualifying evidence on at least one side ({codes}; qualifying claims per side in its evidence audit: {audit}): the "
            "defining evidence condition is absent, so the rule does not trigger",
        )
    if state == PAIR_STATE_NOT_EVALUATED:
        return (
            VERDICT_NOT_EVALUABLE,
            f"the pair was rejected before B2 judged it ({codes}; qualifying claims per side in its evidence audit: {audit}): whether the evidence suffices "
            "is unknown -- not evidence of absence, and not evidence that the admission conditions are met",
        )
    counted = f"{declared_pair_count} declared candidate pairs were recorded" if declared_pair_count is not None else "the candidate pairs it recorded"
    return (
        VERDICT_NOT_EVALUABLE,
        f"this run's arbitration holds no record for the pair ({counted}): the pair was not evaluated in this run (for example the run predates the "
        "pair's declaration in the taxonomy) -- not evidence of absence, and not evidence that the admission conditions are met. The frozen-input "
        "recompute evaluates it",
    )


# ---------------------------------------------------------------------------
# Rule family 1: must_detect_if_evidence_present -- conflict-pair layer
# (the Alpha layer of the same family is gold_contract_rules.evaluate_alpha_rule)
# ---------------------------------------------------------------------------


def evaluate_must_detect_if_evidence_present(
    *,
    ticker_v2_label: dict[str, Any] | None,
    admissibility_lookup: dict[str, dict[str, Any]],
    declared_pair_count: int | None = None,
) -> list[dict[str, Any]]:
    """The pair layer: for every pair the label lists in ``required_conflicts``, read what the run's OWN arbitration recorded -- B2's result (status
    and reason codes) when the pair reached the gate, the detector's reasons and evidence audit when it was rejected before it. Nothing is
    recomputed and no number is invented:

      * admitted -> pass;
      * B2 evaluated it and recorded why it rejected it -> not_applicable: a correct rejection is not a miss (score, supporting facts and ticker
        specificity are all B2's conditions, and the reason codes carry them);
      * the detector found no qualifying evidence on a side -> not_applicable: the defining evidence condition is absent;
      * rejected before B2, or no record at all -> not_evaluable: unknown, never read as "no evidence" and never as "conditions met";
      * B2's record lists no rejection reason and the pair is still not admitted -> fail: the conflict is required, every condition is met, it is
        missing."""
    results = []
    for pair in sorted((ticker_v2_label or {}).get("required_conflicts") or ()):
        entry = admissibility_lookup.get(pair)
        state = pair_record_state(entry)
        verdict, detail = _pair_verdict(state, entry, declared_pair_count)
        results.append(
            {
                "pair": pair,
                "state": state,
                "verdict": verdict,
                "admissibility_status": entry.get("admissibility_status") if entry else None,
                "b2_reason_codes": list((entry or {}).get("reason_codes") or ()),
                "entry_reason_codes": list((entry or {}).get("entry_reason_codes") or ()),
                "evidence_facts": _evidence_facts(entry),
                "detail": detail,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Rule family 2: should_detect_if_supported -- conflict-pair reading, DIAGNOSTIC ONLY
# ---------------------------------------------------------------------------


def evaluate_should_detect_if_supported(
    *,
    ticker_v2_label: dict[str, Any] | None,
    admissibility_lookup: dict[str, dict[str, Any]],
    stance_source_value: str,
) -> list[dict[str, Any]]:
    """The old pair-level reading of ``should_detect_if_supported`` over the label's ``conditional_conflicts``. John's contract defines the family for
    Alphas, and his baseline lists these pairs as allowed, never mandatory -- so this reading has no approval basis. It is kept with its result and its
    source, labelled as such, and ``run_formal_acceptance`` lets it decide NOTHING (``decides_formal_status`` is False)."""
    results = []
    stance_reliable = stance_source_value in (STANCE_SOURCE_LLM_SEMANTIC, STANCE_SOURCE_MIXED)
    for pair in sorted((ticker_v2_label or {}).get("conditional_conflicts") or ()):
        entry = admissibility_lookup.get(pair)
        evidence_present = _evidence_present(entry)
        reasons = list((entry or {}).get("reason_codes") or (entry or {}).get("entry_reason_codes") or ())
        if not evidence_present:
            verdict = VERDICT_NOT_APPLICABLE
            detail = "evidence below the diagnostic bar (>= 1 supporting claim per side) -- the diagnostic does not trigger"
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
            detail = (
                "evidence present with reliable stance but pair was not admitted"
                + (f" -- B2 rejected it for {', '.join(reasons)}, a correct rejection under the approved gate" if reasons else "")
                + "; a soft miss in the engine's own diagnostic reading, never a hard fail"
            )
        results.append(
            {
                "pair": pair,
                "scope": "conflict_pair",
                "authority": "implementation_only_unapproved",
                "decides_formal_status": False,
                "evidence_present": evidence_present,
                "stance_source": stance_source_value,
                "admissibility_status": entry.get("admissibility_status") if entry else None,
                "b2_reason_codes": reasons,
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
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    """How much of what was declared actually had something to evaluate. A PASS is only as strong as this: it says no declared rule was violated,
    and when no declared conflict pair had supporting evidence on both sides (or was admitted) and no contract rule was exercised, no rule had
    evidence to look at. A pair that merely appeared in arbitration with no supporting evidence does not count. The evidence count is DESCRIPTIVE
    (see EVIDENCE_PRESENT_MIN_SUPPORTING_EVIDENCE_PER_SIDE); it decides no verdict."""
    label = ticker_v2_label or {}
    declared = (
        set(label.get("required_conflicts") or ())
        | set(label.get("conditional_conflicts") or ())
        | set(label.get("allowed_conflicts") or ())
    )
    with_evidence = {pair for pair in declared if pair in admitted or _evidence_present(admissibility_lookup.get(pair))}
    results = contract.get("results") or []
    exercised = [r for r in results if r["verdict"] in (gold.VERDICT_PASS, gold.VERDICT_NOT_TRIGGERED)]
    not_executed = list(contract.get("contract_rules_not_executed_for_ticker") or ())
    vacuous = formal_status == FORMAL_STATUS_PASS and not with_evidence and not admitted and not exercised
    return {
        "declared_conflict_pairs": len(declared),
        "declared_pairs_with_evidence": len(with_evidence),
        "admitted_conflicts_checked_by_do_not_force": len(admitted),
        "dominance_guards_declared": len(guard_map),
        "dominance_guards_triggered": len(dominance_results),
        "contract_rules_executed": len(results),
        "contract_rules_with_a_verdict": sum(1 for r in results if r["verdict"] != gold.VERDICT_NOT_EVALUABLE),
        "contract_rules_not_evaluable": sum(1 for r in results if r["verdict"] == gold.VERDICT_NOT_EVALUABLE),
        "contract_rules_not_executed_for_ticker": not_executed,
        "pass_is_vacuous": vacuous,
        "pass_scope_note": (
            "this PASS covers the label-based rule families and the contract rules in contract_rule_results; it says nothing about the contract rules "
            f"this entry does not execute for the ticker ({', '.join(not_executed)})"
            if formal_status == FORMAL_STATUS_PASS and not_executed
            else None
        ),
        "reading": (
            "PASS means no declared rule was violated. None of the declared conflict pairs had supporting evidence on both sides, no conflict "
            "was admitted and no contract rule reached a verdict, so no rule had evidence to evaluate."
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
    activation_summary: dict[str, Any] | None = None,
    gold_contract_path: str | Path | None = None,
    gold_freeze_manifest_path: str | Path | None = None,
    trigger_matrix_path: str | Path | None = None,
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

    ``activation_summary`` (round 24) is the run's own ``run_audit.json ->
    activation_summary`` -- the detection authority John's contract cites. Without it
    an Alpha-layer contract rule whose trigger holds cannot read the Alpha's level and is
    reported ``not_evaluable``, never guessed.

    Checked, in order, BEFORE any rule family runs:
      1. ``effective_rules()`` itself -- ``CONFIG_ERROR`` on failure (a missing
         or malformed file, a label file that does not fit the taxonomy that
         was named, a version mismatch, an unimplemented rule key, two copies
         of one rule that disagree, a Gold contract / freeze manifest / trigger
         matrix that is missing or not the frozen file). This is the only status
         that omits ``effective_rules`` (resolving it is what failed).
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
    view. A failure is: a required conflict whose B2 record satisfies every
    condition yet is not admitted, a violated ``do_not_force`` invariant, a
    failed ticker consistency check, or a contract rule that FAILs (blocking
    or not -- ``release`` says which blocks release). A review is: an
    undeclared admitted conflict, a dominance flag, a required pair or a
    contract rule that cannot be evaluated or is UNCERTAIN / needs
    adjudication. The conflict-pair ``should_detect`` reading is a diagnostic
    and appears in ``diagnostic_findings`` only. ``v2_contract_result`` stays
    in the verdict as the unconditional, report-only view."""
    try:
        rules = effective_rules(
            taxonomy_path=taxonomy_path,
            label_v2_path=label_v2_path,
            label_v1_path=label_v1_path,
            gold_contract_path=gold_contract_path,
            gold_freeze_manifest_path=gold_freeze_manifest_path,
            trigger_matrix_path=trigger_matrix_path,
        )
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
    declared_pair_count = ((conflict_payload or {}).get("arbitration") or {}).get("declared_pair_count")
    v2_contract_result = apply_v2_contract(
        ticker=ticker, ticker_v2_label=ticker_v2_label, evaluate_ticker_result=evaluate_ticker_result
    )

    must_detect_results = evaluate_must_detect_if_evidence_present(
        ticker_v2_label=ticker_v2_label, admissibility_lookup=admissibility_lookup, declared_pair_count=declared_pair_count
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

    try:
        bundle = gold.load_gold_contract_bundle(
            contract_path=gold_contract_path, freeze_manifest_path=gold_freeze_manifest_path, trigger_matrix_path=trigger_matrix_path
        )
    except gold.GoldContractError as exc:  # effective_rules just loaded the same files; a change in between is still never a silent pass
        return {
            "ticker": ticker,
            "formal_status": FORMAL_STATUS_CONFIG_ERROR,
            "config_error_reason_code": exc.reason_code,
            "config_error_detail": exc.detail,
            "rule_family_results": {},
        }
    declared_family = sorted(
        set(ticker_v2_label.get("required_conflicts") or ())
        | set(ticker_v2_label.get("conditional_conflicts") or ())
        | set(ticker_v2_label.get("allowed_conflicts") or ())
    )
    pair_records = {
        pair: {
            "state": pair_record_state(entry),
            "b2_status": entry.get("admissibility_status"),
            "b2_reason_codes": entry.get("reason_codes"),
            "entry_reason_codes": entry.get("entry_reason_codes"),
        }
        for pair, entry in admissibility_lookup.items()
    }
    contract = gold.evaluate_contract_rules(
        bundle,
        ticker=ticker,
        run_id=evaluate_ticker_result.get("run_id"),
        activation_summary=activation_summary,
        alpha_matches_payload=alpha_matches_payload,
        admitted_conflicts=evaluate_ticker_result.get("admitted_conflicts") or (),
        main_conflict=evaluate_ticker_result.get("main_conflict"),
        allowed_family=declared_family,
        pair_records=pair_records,
    )

    rule_family_results = {
        RULE_FAMILY_MUST_DETECT_IF_EVIDENCE_PRESENT: must_detect_results,
        RULE_FAMILY_SHOULD_DETECT_IF_SUPPORTED: should_detect_results,
        RULE_FAMILY_CONDITIONAL_ONLY: conditional_only_results,
        RULE_FAMILY_DO_NOT_FORCE: do_not_force_result,
        RULE_FAMILY_ALLOWED_MAIN_CONFLICTS: allowed_main_conflicts_results,
        RULE_FAMILY_FORBIDDEN_DOMINANT_WITHOUT_STRONG_EVIDENCE: dominance_results,
    }

    def _contract_reason(result: Mapping[str, Any]) -> dict[str, Any]:
        recognition = result.get("alpha_recognition") or []
        return {
            "family": result["family"],
            "rule_id": result["rule_id"],
            "alpha_id": recognition[0]["alpha_id"] if recognition else None,
            "verdict": result["verdict"],
            "blocking": result["blocking"],
            "blocks_release": result["blocks_release"],
            "reason_code": result["reason_code"],
            "detail": result["detail"],
        }

    # Every reason a verdict is not a PASS, listed once, so the status and every table / summary rendered from this result cannot disagree.
    failure_reasons: list[dict[str, Any]] = [
        {"family": RULE_FAMILY_MUST_DETECT_IF_EVIDENCE_PRESENT, "pair": r["pair"], "state": r["state"], "detail": r["detail"]}
        for r in must_detect_results
        if r["verdict"] == VERDICT_FAIL
    ]
    failure_reasons += [_contract_reason(r) for r in contract["results"] if r["verdict"] == gold.VERDICT_FAIL]
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
        {
            "family": RULE_FAMILY_MUST_DETECT_IF_EVIDENCE_PRESENT,
            "pair": r["pair"],
            "verdict": r["verdict"],
            "state": r["state"],
            "detail": r["detail"],
        }
        for r in must_detect_results
        if r["verdict"] == VERDICT_NOT_EVALUABLE
    ]
    review_reasons += [
        _contract_reason(r) for r in contract["results"] if r["verdict"] in (gold.VERDICT_NEEDS_REVIEW, gold.VERDICT_NOT_EVALUABLE)
    ]
    review_reasons += [
        {"family": RULE_FAMILY_FORBIDDEN_DOMINANT_WITHOUT_STRONG_EVIDENCE, "alpha_id": flag["alpha_id"], "verdict": "review_required"}
        for flag in dominance_results
    ]
    review_reasons += [
        {"family": "undeclared_admitted_conflict", "pair": pair, "verdict": "review_required"}
        for pair in undeclared_admitted_conflicts
    ]

    # The conflict-pair should_detect reading has no approval basis: it is reported with its source and decides nothing.
    diagnostic_findings: list[dict[str, Any]] = [
        {
            "family": RULE_FAMILY_SHOULD_DETECT_IF_SUPPORTED,
            "scope": r["scope"],
            "pair": r["pair"],
            "verdict": r["verdict"],
            "b2_reason_codes": r["b2_reason_codes"],
            "source": f"{rules['label_v2']['path']}: conditional_conflicts",
            "authority": r["authority"],
            "decides_formal_status": r["decides_formal_status"],
            "detail": r["detail"],
        }
        for r in should_detect_results
        if r["verdict"] in (VERDICT_NEEDS_REVIEW, VERDICT_PENDING_REVIEW)
    ]

    if failure_reasons:
        formal_status = FORMAL_STATUS_FAIL
    elif review_reasons:
        formal_status = FORMAL_STATUS_NEEDS_REVIEW
    else:
        formal_status = FORMAL_STATUS_PASS

    run_bound = ticker_v2_label.get("run_bound_expectations")
    run_id = evaluate_ticker_result.get("run_id")
    resolved_rules = {**rules, "ticker_rules": resolve_ticker_rules(ticker=ticker, ticker_v2_label=ticker_v2_label, label_block_v1=label_block_v1)}
    verdict = {
        "ticker": ticker,
        "run_id": run_id,
        "formal_status": formal_status,
        "effective_rules": resolved_rules,
        "rule_family_results": rule_family_results,
        "contract_rule_results": contract["results"],
        "release": contract["release"],
        "diagnostic_findings": diagnostic_findings,
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
            contract=contract,
        ),
        "v2_contract_result": v2_contract_result,
        "v2_contract_note": (
            "v2_contract_result is the unconditional v0.2 contract view (report only). The verdict follows the rule families and the contract rules "
            "above: a required pair B2 rejected for a recorded reason, or with no usable record, is never a fail there."
        ),
    }
    if run_bound is not None:
        verdict["run_bound_observation"] = {
            "classification": "unapproved_historical_observation",
            "executable": False,
            "reference_run_id": run_bound.get("reference_run_id"),
            "evaluated_run_id": run_id,
            "evaluated_run_is_the_reference_run": run_id == run_bound.get("reference_run_id"),
            "observed_historical_main_conflict": run_bound.get("observed_historical_main_conflict"),
            "effect_on_formal_status": "none",
        }
    return verdict


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
    "pair_record_state",
    "PAIR_STATE_ADMITTED",
    "PAIR_STATE_B2_REJECTED",
    "PAIR_STATE_B2_NO_REASON",
    "PAIR_STATE_NO_QUALIFYING_EVIDENCE",
    "PAIR_STATE_NOT_EVALUATED",
    "PAIR_STATE_NO_RECORD",
    "evaluate_must_detect_if_evidence_present",
    "evaluate_should_detect_if_supported",
    "evaluate_do_not_force_invariant",
    "evaluate_conditional_only",
    "evaluate_allowed_main_conflicts",
    "evaluate_forbidden_dominant_without_strong_evidence",
    "run_formal_acceptance",
]
