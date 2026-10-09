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
from comqutor_alpha.regression.labels_v2 import (
    DEFAULT_LABEL_V2_PATH,
    LabelV2ValidationError,
    load_j2_labels_v2,
    ticker_label_v2,
)

SCHEMA_VERSION = "acceptance_engine.v1"

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


def effective_rules(
    *, taxonomy_path: str | Path | None = None, label_v2_path: str | Path | None = None
) -> dict[str, Any]:
    """Explicitly resolves this run's rule configuration. Never a silent
    fallback: an explicit path is honored as given; the default is always
    the SAME named repository constant every other B2/A4 caller uses
    (``alpha_loader.TAXONOMY_PATH`` /
    ``labels_v2.DEFAULT_LABEL_V2_PATH``), never re-derived or guessed.
    Raises :class:`AcceptanceConfigError` if either file is missing or the
    label file fails its own structural validation -- callers must not
    catch this to fall back to some other config."""
    resolved_taxonomy_path = Path(taxonomy_path) if taxonomy_path is not None else TAXONOMY_PATH
    resolved_label_path = Path(label_v2_path) if label_v2_path is not None else DEFAULT_LABEL_V2_PATH

    if not resolved_taxonomy_path.exists():
        raise AcceptanceConfigError("ACCEPTANCE_TAXONOMY_FILE_NOT_FOUND", str(resolved_taxonomy_path))
    try:
        taxonomy = load_alpha_taxonomy(resolved_taxonomy_path)
    except ValueError as exc:
        raise AcceptanceConfigError("ACCEPTANCE_TAXONOMY_MALFORMED", str(exc)) from exc

    try:
        label_v2 = load_j2_labels_v2(resolved_label_path)
    except LabelV2ValidationError as exc:
        raise AcceptanceConfigError("ACCEPTANCE_LABEL_V2_INVALID", str(exc)) from exc

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
            "config_source": f"{resolved_label_path.name.replace('v0.2', 'v0.1')} (v0.1): should_not_be_dominant_without_strong_evidence",
            "applicable_target": "Alpha, per ticker",
            "execution_function": "evaluator.dominance_guard_flags",
            "trigger_condition": "Alpha is listed in the ticker's should_not_be_dominant_without_strong_evidence AND reached dominant/regime_level status",
            "evidence_requirement": "none to trigger the flag itself -- flags for human review, never auto-fails",
            "verdict_result": ["review_required", "not_triggered", VERDICT_NOT_EVALUABLE],
        },
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "taxonomy": {
            "path": str(resolved_taxonomy_path),
            "sha256": _sha256_file(resolved_taxonomy_path),
            "declared_alpha_count": len(taxonomy),
        },
        "label_v2": {
            "path": str(resolved_label_path),
            "sha256": _sha256_file(resolved_label_path),
            "label_version": label_v2.get("label_version"),
            "evaluation_mode": label_v2.get("evaluation_mode"),
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
) -> dict[str, Any]:
    """The single formal acceptance entry point: resolves ``effective_rules``
    (raising, never silently falling back, on a config problem), executes
    all six rule families, and returns one machine-readable per-ticker
    verdict. A required rule family that cannot execute, or a ticker whose
    own source artifacts are incomplete, always blocks ``formal_status ==
    "pass"`` -- never masked as ``not_applicable``.

    ``alpha_matches_payload`` (2026-09-30 closing fix): REQUIRED, no
    default -- every real caller must now explicitly pass this run's own
    ``alpha_matches.json``-shaped payload (``None`` is an explicit, valid
    value meaning "I have none", itself one of the checked failure modes
    below, never a silent get-out). The PRIOR version of this parameter
    was optional with a ``None`` default that a caller could simply never
    pass, computing "today's original [pre-gate] behavior" -- exactly the
    bypass this closing fix removes: a caller can no longer omit real
    semantic input and fall through to a rule family's own empty-result
    PASS default.

    Checked, in order, BEFORE any rule family runs (so ``effective_rules``
    -- this execution's own rule version identity -- is resolved and
    attached to every returned status except ``CONFIG_ERROR`` itself,
    where resolving it is the very thing that failed):
      1. ``effective_rules()`` itself -- ``CONFIG_ERROR`` on failure, as
         before.
      2. ``alpha_matches_payload`` missing / unparseable / every claim
         ``match_status == "unavailable"`` -- ``formal_status =
         ALPHA_SEMANTIC_UNAVAILABLE`` with a specific
         ``semantic_input_reason_code`` (see ``_semantic_input_reason_
         code``), never a PASS. This never re-derives, guesses, or
         deterministically falls back to a semantic decision the real
         classifier never made, and never rewrites ``"unavailable"`` to
         ``"none"`` -- it only reports that a formal verdict cannot be
         certified from what was supplied.
      3. ``_ticker_is_evaluable`` -- ``NOT_EVALUABLE`` on incomplete
         artifacts, as before.
      4. The six rule families, exactly as before.

    A genuinely empty ``alpha_matches_payload["matches"]`` list (a ticker
    with zero relevant claims) is NOT treated as missing/unavailable --
    the existing rule families already handle zero evidence correctly
    (``evidence_present=False`` etc.); this is a real, legitimate state,
    never conflated with "semantic authority was never exercised"."""
    try:
        rules = effective_rules(taxonomy_path=taxonomy_path, label_v2_path=label_v2_path)
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

    hard_fail = bool(
        [r for r in must_detect_results if r["verdict"] == VERDICT_FAIL]
    ) or do_not_force_result["verdict"] == "invariant_violated" or (
        v2_contract_result.get("ticker_status") == "fail"
    )
    needs_review = bool(
        [r for r in should_detect_results if r["verdict"] in (VERDICT_NEEDS_REVIEW, VERDICT_PENDING_REVIEW)]
    ) or bool(dominance_results) or bool(undeclared_admitted_conflicts)

    if hard_fail:
        formal_status = FORMAL_STATUS_FAIL
    elif needs_review:
        formal_status = FORMAL_STATUS_NEEDS_REVIEW
    else:
        formal_status = FORMAL_STATUS_PASS

    return {
        "ticker": ticker,
        "formal_status": formal_status,
        "effective_rules": rules,
        "rule_family_results": rule_family_results,
        "undeclared_admitted_conflicts": undeclared_admitted_conflicts,
        "v2_contract_result": v2_contract_result,
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
