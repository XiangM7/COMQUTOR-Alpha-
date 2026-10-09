"""T2 (round 24): executes the Alpha-layer rules of John's frozen Gold v0.2 operational contract
(``docs/audit_artifacts/v0_2_gold_operational_contract.json``) inside the unified formal-acceptance entry.

Before this module the unified entry mapped ``must_detect_if_evidence_present`` onto the v0.2 label's pair-level ``required_conflicts``. John's
contract defines that family at the Alpha level ("if the defining current-evidence condition is present, the system must detect an acceptable
existing Alpha/structure at an official detected level"). This module executes the rules the contract defines, and no others:

  * ``NVDA-A101-AI-GROWTH``, ``NVDA-A304-VALUATION-RISK`` (blocking), ``MSFT-A102-DIRECT-INFERENCE-TRIGGER`` (non-blocking):
    ``must_detect_if_evidence_present``, ALPHA_HIT;
  * ``NVDA-GROWTH-VS-VALUATION-CONFLICT`` (blocking), ``AMD-AI-GROWTH-VS-VALUATION`` (non-blocking): ``conditional_only``,
    COMPOSITE_STRUCTURE_HIT -- "any allowed pair admitted" (never "every allowed pair must appear").

Every other contract rule is listed in ``rules_not_in_effect`` with the reason; nothing is silently skipped and nothing is claimed.

What this module will not do:

  * It does not invent a threshold, a score or an evidence-qualification step. The detected levels are the contract's own
    (``regression_report_v3._DETECTED_LEVELS`` read from ``run_audit.json -> activation_summary.per_alpha[alpha].level``, the path the contract
    cites); the admitted conflicts are the run's own.
  * It does not borrow a trigger. The frozen Evidence Trigger Matrix was read by hand from ONE run per ticker (``structured_agent_outputs.json`` of
    the six ledger-selected runs). It is used for exactly that (ticker, run_id) and nothing else. For any other run the evidence trigger is
    ``NOT_EVALUABLE``: no approved, executable evidence-determination method exists for it, and a historical TRUE/FALSE is never carried over.
  * It does not touch the research output. It reads persisted artifacts after the research is complete.

Four facts are recorded separately for every Alpha rule, because they answer four different questions: was the Alpha identified (claims classified
to it), what activation level did it reach, does that level satisfy the contract, and was the evidence trigger established.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from comqutor_alpha.regression.regression_report_v3 import _DETECTED_LEVELS

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AUDIT_DIR = _REPO_ROOT / "docs" / "audit_artifacts"
DEFAULT_CONTRACT_PATH = _AUDIT_DIR / "v0_2_gold_operational_contract.json"
DEFAULT_FREEZE_MANIFEST_PATH = _AUDIT_DIR / "v0_2_gold_freeze_manifest.json"
DEFAULT_TRIGGER_MATRIX_PATH = _AUDIT_DIR / "v0_2_evidence_trigger_matrix.json"


def _default_artifact_path(path: Path) -> Path:
    """The frozen files live under ``docs/audit_artifacts/``, which is not package data: next to the package in a source checkout, under the working
    directory in the container image (the image installs the package into a virtualenv and keeps the repository copy in WORKDIR). The first location that
    holds the file is used; when neither does, the repository-relative path is returned so the configuration error names a real, expected place. The
    same file at another root is not a fallback to a different rule file -- its sha256 is verified against the freeze manifest either way."""
    candidates = [path, Path.cwd() / "docs" / "audit_artifacts" / path.name]
    return next((c for c in candidates if c.exists()), path)

# The matrix's own frozen hash. It is recorded in v0_2_final_acceptance_closure.json (authorities_verified.historical_trigger_matrix_json) and in the
# Step-4 table; the contract's hash is read from the freeze manifest instead.
FROZEN_TRIGGER_MATRIX_SHA256 = "3e8e7402803632198b01c2a08a98929031929cc4b909927dc7e475d37b5d22a1"
_UNSET = object()

SCHEMA_VERSION = "comqutor.gold_contract_rules.v1"
CONTRACT_SCHEMA_VERSION = "gold_operational_contract.v0.2"
CONTRACT_GOLD_VERSION = "v0.2"
CONTRACT_FREEZE_STATUS = "FROZEN_GOLD_V0_2"

FAMILY_MUST_DETECT = "must_detect_if_evidence_present"
FAMILY_CONDITIONAL_ONLY = "conditional_only"

VERDICT_PASS = "pass"
VERDICT_FAIL = "fail"
VERDICT_NOT_TRIGGERED = "not_triggered"
VERDICT_NEEDS_REVIEW = "needs_review"
VERDICT_NOT_EVALUABLE = "not_evaluable"
JOHN_RESULT = {
    VERDICT_PASS: "PASS",
    VERDICT_FAIL: "FAIL",
    VERDICT_NOT_TRIGGERED: "NOT_TRIGGERED",
    VERDICT_NEEDS_REVIEW: "REVIEW",
    VERDICT_NOT_EVALUABLE: "NOT_EVALUABLE",
}

TRIGGER_PRESENT = "PRESENT"
TRIGGER_ABSENT = "ABSENT"
TRIGGER_UNCERTAIN = "UNCERTAIN"
TRIGGER_NOT_EVALUABLE = "NOT_EVALUABLE"

REASON_RUN_NOT_BOUND = "RUN_NOT_BOUND_TO_FROZEN_TRIGGER_MATRIX"
REASON_TICKER_NOT_IN_MATRIX = "TICKER_NOT_IN_FROZEN_TRIGGER_MATRIX"
REASON_RULE_NOT_IN_MATRIX = "RULE_NOT_IN_FROZEN_TRIGGER_MATRIX"
REASON_DETECTION_AUTHORITY_UNAVAILABLE = "DETECTION_AUTHORITY_UNAVAILABLE"
REASON_CLASSIFICATION_INCOMPLETE = "CLASSIFICATION_INCOMPLETE_NONE_NOT_VALID"
REASON_NO_ALLOWED_PAIR_ADMITTED = "NO_ALLOWED_PAIR_ADMITTED_ADJUDICATION_REQUIRED"
REASON_ADMITTED_OUTSIDE_FAMILY = "ADMITTED_CONFLICT_OUTSIDE_ALLOWED_FAMILY"
REASON_ALLOWED_PAIR_COMPLETE_NOT_ADMITTED = "ALLOWED_PAIR_MEETS_EVERY_B2_CONDITION_BUT_NOT_ADMITTED"
# The arbitration record states acceptance_engine.pair_record_state distinguishes; the composite needs only these two (a test pins them to the engine's).
PAIR_STATE_B2_NO_REASON = "b2_not_admitted_without_reason"
PAIR_STATE_NO_RECORD = "no_arbitration_record"

# Identification states of an Alpha (distinct from its activation level).
IDENTIFIED = "IDENTIFIED"
NOT_IDENTIFIED = "NOT_IDENTIFIED"
UNKNOWN_CLASSIFICATION_INCOMPLETE = "UNKNOWN_CLASSIFICATION_INCOMPLETE"
UNKNOWN_NO_MATCH_PAYLOAD = "UNKNOWN_NO_ALPHA_MATCHES_PAYLOAD"

# The rule ids this module executes, and the contract shape each one must have for the executor to run it.
_EXECUTED_RULES: dict[str, dict[str, Any]] = {
    "NVDA-A101-AI-GROWTH": {"hit_type": "ALPHA_HIT", "rule_type": FAMILY_MUST_DETECT},
    "NVDA-A304-VALUATION-RISK": {"hit_type": "ALPHA_HIT", "rule_type": FAMILY_MUST_DETECT},
    "MSFT-A102-DIRECT-INFERENCE-TRIGGER": {"hit_type": "ALPHA_HIT", "rule_type": FAMILY_MUST_DETECT},
    "NVDA-GROWTH-VS-VALUATION-CONFLICT": {"hit_type": "COMPOSITE_STRUCTURE_HIT", "rule_type": FAMILY_CONDITIONAL_ONLY},
    "AMD-AI-GROWTH-VS-VALUATION": {"hit_type": "COMPOSITE_STRUCTURE_HIT", "rule_type": FAMILY_CONDITIONAL_ONLY},
}

EXECUTED_RULE_IDS = frozenset(_EXECUTED_RULES)

_STEP1 = "John's Gold v0.2 operationalization instruction (Step 1), 2026-09-10T20:43:46Z"
_STEP2 = "John's final decisions for the Gold v0.2 freeze (Step 2), 2026-09-10T21:02:57Z"
_STEP4 = "Frozen-gold vs frozen-trigger comparison protocol (Step 4), 2026-09-10T21:52:47Z"
_FREEZE = "v0_2_gold_freeze_manifest.json (contract JSON sha256 e2df7139e19e...; 9 review items resolved, none remaining)"
_BASELINE = "v0_2_john_frozen_gold_baseline.yaml (authority JOHN_WRITTEN_V0_2_BASELINE)"

# Where each executed rule's approval comes from. The contract's own ``authority.approval_status: APPROVED`` is a field the Step-1 instruction
# supplied as a template, so it is not cited as evidence; John's decisions are.
RULE_AUTHORITY_BASIS: dict[str, list[str]] = {
    "NVDA-A101-AI-GROWTH": [
        f"{_STEP2}, section 4: 'A101: must_detect_if_evidence_present'; section 2: NVDA is Formal Gold, blocking = true",
        f"{_STEP1}, section 8.A (mapping, condition, 'do NOT force A101 when such evidence is absent')",
        _FREEZE,
    ],
    "NVDA-A304-VALUATION-RISK": [
        f"{_STEP2}, section 4: 'A304: must_detect_if_evidence_present'; section 2: NVDA is Formal Gold, blocking = true",
        f"{_STEP1}, section 8.C",
        _FREEZE,
    ],
    "MSFT-A102-DIRECT-INFERENCE-TRIGGER": [
        f"{_STEP2}, section 1.G (final decision): DIRECT_INFERENCE_TRIGGER -> must_detect_if_evidence_present -> A102; section 2: MSFT is Silver, blocking = false",
        f"{_STEP1}, section 11.B (the 'must/should' wording that decision G resolved)",
        _FREEZE,
    ],
    "NVDA-GROWTH-VS-VALUATION-CONFLICT": [
        f"{_STEP2}, section 4: composite allowed pairs A101__A304 and A301__A304 'only when both relevant evidence sides are present; do not force a conflict if only one side is supported'",
        f"{_STEP4}, section 13: any allowed evidence-supported conflict admitted -> PASS; none admitted -> REVIEW with adjudication; outside the allowed family -> FAIL or REVIEW",
        f"{_BASELINE}: allowed_main_conflicts NVDA = A101__A304, A301__A304",
    ],
    "AMD-AI-GROWTH-VS-VALUATION": [
        f"{_STEP1}, section 13 (composite; 'do not force either pair'; Silver, non-blocking)",
        f"{_STEP4}, sections 13 and 20",
        f"{_BASELINE}: allowed_main_conflicts AMD = A101__A304, A201__A304, A301__A304 (the baseline controls; the contract lists only A101__A304 and A301__A304)",
    ],
}


class GoldContractError(Exception):
    """The contract, its freeze manifest or the trigger matrix is missing, malformed, of the wrong version, or not the frozen file. Carries a
    stable reason code; the unified entry reports it as a configuration error and never falls back to another file."""

    def __init__(self, reason_code: str, detail: str = "") -> None:
        self.reason_code = reason_code
        self.detail = detail
        super().__init__(f"{reason_code}: {detail}" if detail else reason_code)


def _display_path(path: Path) -> str:
    for root in (_REPO_ROOT, Path.cwd()):
        try:
            return path.resolve().relative_to(root).as_posix()
        except ValueError:
            continue
    return str(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path, *, missing_code: str, malformed_code: str) -> dict[str, Any]:
    if not path.exists():
        raise GoldContractError(missing_code, _display_path(path))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GoldContractError(malformed_code, f"{_display_path(path)}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(payload, dict):
        raise GoldContractError(malformed_code, f"{_display_path(path)}: top level is not an object")
    return payload


def _normalize_pair(pair: str) -> str:
    left, sep, right = str(pair).partition("__")
    return "__".join(sorted((left, right))) if sep else str(pair)


@dataclass(frozen=True)
class GoldContractBundle:
    """The contract, its freeze manifest and the trigger matrix, loaded once and verified."""

    contract_path: Path
    contract_sha256: str
    contract: dict[str, Any]
    manifest_path: Path
    manifest_sha256: str
    manifest: dict[str, Any]
    matrix_path: Path
    matrix_sha256: str
    matrix_sha256_expected: str | None
    matrix: dict[str, Any]
    rules_by_id: dict[str, dict[str, Any]]
    matrix_rules: dict[tuple[str, str], dict[str, Any]]
    matrix_runs: dict[str, str]
    markdown_path: Path

    def executed_rules_for(self, ticker: str) -> list[dict[str, Any]]:
        return [rule for rule_id, rule in self.rules_by_id.items() if rule_id in _EXECUTED_RULES and rule.get("ticker") == ticker]


def load_gold_contract_bundle(
    *,
    contract_path: str | Path | None = None,
    freeze_manifest_path: str | Path | None = None,
    trigger_matrix_path: str | Path | None = None,
    expected_matrix_sha256: Any = _UNSET,
) -> GoldContractBundle:
    """Loads and verifies the three frozen inputs. Raises :class:`GoldContractError` (never falls back to another file) when:

      * a file is missing or malformed;
      * the contract is not Gold v0.2 / not frozen;
      * the contract's sha256 differs from the one its freeze manifest recorded (an edited contract is not the contract John froze);
      * the trigger matrix was written against a different contract, or is not the matrix whose hash was recorded when it was frozen;
      * a rule this module executes is absent from the contract, or has a rule type / hit type it cannot execute.

    ``expected_matrix_sha256=None`` skips the matrix hash comparison (a test using its own matrix); the default is the frozen hash."""
    resolved_contract = Path(contract_path) if contract_path is not None else _default_artifact_path(DEFAULT_CONTRACT_PATH)
    resolved_manifest = Path(freeze_manifest_path) if freeze_manifest_path is not None else _default_artifact_path(DEFAULT_FREEZE_MANIFEST_PATH)
    resolved_matrix = Path(trigger_matrix_path) if trigger_matrix_path is not None else _default_artifact_path(DEFAULT_TRIGGER_MATRIX_PATH)

    contract = _read_json(
        resolved_contract, missing_code="ACCEPTANCE_GOLD_CONTRACT_FILE_NOT_FOUND", malformed_code="ACCEPTANCE_GOLD_CONTRACT_MALFORMED"
    )
    if (
        contract.get("schema_version") != CONTRACT_SCHEMA_VERSION
        or contract.get("gold_version") != CONTRACT_GOLD_VERSION
        or contract.get("freeze_status") != CONTRACT_FREEZE_STATUS
    ):
        raise GoldContractError(
            "ACCEPTANCE_GOLD_CONTRACT_VERSION_MISMATCH",
            f"this engine executes {CONTRACT_SCHEMA_VERSION} / {CONTRACT_GOLD_VERSION} / {CONTRACT_FREEZE_STATUS}; the file declares "
            f"schema_version={contract.get('schema_version')!r}, gold_version={contract.get('gold_version')!r}, freeze_status={contract.get('freeze_status')!r}",
        )

    manifest = _read_json(
        resolved_manifest, missing_code="ACCEPTANCE_GOLD_FREEZE_MANIFEST_NOT_FOUND", malformed_code="ACCEPTANCE_GOLD_FREEZE_MANIFEST_MALFORMED"
    )
    recorded = manifest.get("frozen_contract_json_sha256")
    contract_sha = _sha256(resolved_contract)
    if not recorded or recorded != contract_sha:
        raise GoldContractError(
            "ACCEPTANCE_GOLD_CONTRACT_INTEGRITY_MISMATCH",
            f"{_display_path(resolved_contract)} has sha256 {contract_sha}; the freeze manifest recorded {recorded}",
        )

    # The detected levels are the contract's own (``detected_level_authority``); the code constant is the production authority it cites. They must agree.
    declared_levels = set((contract.get("detected_level_authority") or {}).get("detected_levels") or ())
    if declared_levels != set(_DETECTED_LEVELS):
        raise GoldContractError(
            "ACCEPTANCE_GOLD_CONTRACT_DETECTION_AUTHORITY_MISMATCH",
            f"the contract lists the detected levels {sorted(declared_levels)}; the authority it cites (regression_report_v3._DETECTED_LEVELS) is {sorted(_DETECTED_LEVELS)}",
        )

    matrix = _read_json(
        resolved_matrix, missing_code="ACCEPTANCE_TRIGGER_MATRIX_NOT_FOUND", malformed_code="ACCEPTANCE_TRIGGER_MATRIX_MALFORMED"
    )
    matrix_sha = _sha256(resolved_matrix)
    expected_matrix = FROZEN_TRIGGER_MATRIX_SHA256 if expected_matrix_sha256 is _UNSET else expected_matrix_sha256
    if expected_matrix is not None and expected_matrix != matrix_sha:
        raise GoldContractError(
            "ACCEPTANCE_TRIGGER_MATRIX_INTEGRITY_MISMATCH",
            f"{_display_path(resolved_matrix)} has sha256 {matrix_sha}; the frozen matrix is {expected_matrix}",
        )
    if (matrix.get("gold_authority") or {}).get("contract_sha256") != contract_sha:
        raise GoldContractError(
            "ACCEPTANCE_TRIGGER_MATRIX_CONTRACT_MISMATCH",
            f"the matrix was written against contract sha256 {(matrix.get('gold_authority') or {}).get('contract_sha256')}, not {contract_sha}",
        )

    rules_by_id: dict[str, dict[str, Any]] = {}
    for ticker_block in (contract.get("tickers") or {}).values():
        for rule in (ticker_block or {}).get("rules") or ():
            if isinstance(rule, dict) and rule.get("rule_id"):
                rules_by_id[str(rule["rule_id"])] = rule

    for rule_id, shape in _EXECUTED_RULES.items():
        rule = rules_by_id.get(rule_id)
        if rule is None:
            raise GoldContractError("ACCEPTANCE_GOLD_CONTRACT_RULE_MISSING", f"{rule_id} is not in {_display_path(resolved_contract)}")
        if rule.get("rule_type") != shape["rule_type"] or rule.get("hit_type") != shape["hit_type"]:
            raise GoldContractError(
                "ACCEPTANCE_RULE_TYPE_NOT_IMPLEMENTED",
                f"{rule_id}: the executor runs rule_type={shape['rule_type']!r} / hit_type={shape['hit_type']!r}; the contract has "
                f"rule_type={rule.get('rule_type')!r} / hit_type={rule.get('hit_type')!r}",
            )
        if not isinstance(rule.get("blocking"), bool) or not rule.get("acceptable_alphas"):
            raise GoldContractError("ACCEPTANCE_GOLD_CONTRACT_MALFORMED", f"{rule_id}: needs a boolean 'blocking' and 'acceptable_alphas'")

    matrix_rules: dict[tuple[str, str], dict[str, Any]] = {}
    matrix_runs: dict[str, str] = {}
    for ticker, block in (matrix.get("tickers") or {}).items():
        if isinstance(block, dict) and block.get("run_id"):
            matrix_runs[str(ticker)] = str(block["run_id"])
            for rule in block.get("rules") or ():
                if isinstance(rule, dict) and rule.get("rule_id"):
                    matrix_rules[(str(ticker), str(rule["rule_id"]))] = rule

    return GoldContractBundle(
        contract_path=resolved_contract,
        contract_sha256=contract_sha,
        contract=contract,
        manifest_path=resolved_manifest,
        manifest_sha256=_sha256(resolved_manifest),
        manifest=manifest,
        matrix_path=resolved_matrix,
        matrix_sha256=matrix_sha,
        matrix_sha256_expected=expected_matrix,
        matrix=matrix,
        rules_by_id=rules_by_id,
        matrix_rules=matrix_rules,
        matrix_runs=matrix_runs,
        markdown_path=resolved_contract.with_suffix(".md"),
    )


def describe_bundle(bundle: GoldContractBundle) -> dict[str, Any]:
    """The contract section of ``effective_rules``: which files were loaded, what verified them, what is executed and what is not."""
    contract = bundle.contract
    frozen_md = bundle.manifest.get("frozen_contract_md_sha256")
    md_now = _sha256(bundle.markdown_path) if bundle.markdown_path.exists() else None
    in_effect, not_in_effect = [], []
    for rule_id, rule in bundle.rules_by_id.items():
        if rule_id in _EXECUTED_RULES:
            in_effect.append(
                {
                    "rule_id": rule_id,
                    "ticker": rule.get("ticker"),
                    "family": rule.get("rule_type"),
                    "hit_type": rule.get("hit_type"),
                    "acceptable_alphas": list(rule.get("acceptable_alphas") or ()),
                    "allowed_main_conflicts": list(rule.get("allowed_main_conflicts") or ()),
                    "blocking": rule.get("blocking"),
                    "executor": f"gold_contract_rules.{'evaluate_composite_rule' if rule.get('hit_type') == 'COMPOSITE_STRUCTURE_HIT' else 'evaluate_alpha_rule'}",
                    "trigger_source": (
                        f"frozen evidence trigger matrix, for run {bundle.matrix_runs.get(str(rule.get('ticker')))} only; "
                        "any other run -> NOT_EVALUABLE"
                    ),
                    "authority_basis": list(RULE_AUTHORITY_BASIS.get(rule_id, ())),
                }
            )
        else:
            not_in_effect.append(
                {
                    "rule_id": rule_id,
                    "ticker": rule.get("ticker"),
                    "rule_type": rule.get("rule_type"),
                    "hit_type": rule.get("hit_type"),
                    "blocking": rule.get("blocking"),
                    "reason_code": "NOT_EXECUTED_THIS_ROUND",
                    "reason": "outside the five contract rules this round executes; not evaluated, not counted in any verdict",
                }
            )
    return {
        "path": _display_path(bundle.contract_path),
        "sha256": bundle.contract_sha256,
        "schema_version": contract.get("schema_version"),
        "gold_version": contract.get("gold_version"),
        "freeze_status": contract.get("freeze_status"),
        "freeze_timestamp": contract.get("freeze_timestamp"),
        "total_rule_count": len(bundle.rules_by_id),
        "authority_field_in_file": contract.get("authority"),
        "authority_note": (
            "the file's authority.approval_status is a field the Step-1 instruction supplied as a template; it is not cited as evidence. "
            "Each executed rule cites the John decision it implements (rules_in_effect[].authority_basis)."
        ),
        "integrity": {
            "expected_sha256": bundle.manifest.get("frozen_contract_json_sha256"),
            "expected_from": _display_path(bundle.manifest_path),
            "freeze_manifest_sha256": bundle.manifest_sha256,
            "matches": True,
        },
        "markdown_companion": {
            "path": _display_path(bundle.markdown_path),
            "sha256_now": md_now,
            "sha256_frozen": frozen_md,
            "matches_frozen": md_now == frozen_md,
            "read_by_executor": False,
            "note": (
                "rewritten on John's instruction of 2026-09-15 (final submission cleanup: a short John-facing definition of the six semantics); "
                "the rule records live in the JSON, which is byte-identical to the frozen file"
            ),
        },
        "trigger_matrix": {
            "path": _display_path(bundle.matrix_path),
            "sha256": bundle.matrix_sha256,
            "expected_sha256": bundle.matrix_sha256_expected,
            "matches_expected": bundle.matrix_sha256_expected is None or bundle.matrix_sha256_expected == bundle.matrix_sha256,
            "written_against_contract_sha256": (bundle.matrix.get("gold_authority") or {}).get("contract_sha256"),
            "bound_runs": dict(sorted(bundle.matrix_runs.items())),
            "determination_method": (
                "the evidence of each bound run was read once, by hand, from that run's structured_agent_outputs.json; there is no approved "
                "executable method that determines the trigger for any other run"
            ),
            "executable_method_for_other_runs": None,
        },
        "detection_authority": {
            "source": "run_audit.json -> activation_summary.per_alpha[alpha_id].level, read as regression_report_v3._detected_alphas does",
            "detected_levels": sorted(_DETECTED_LEVELS),
            "not_detected_levels": ["candidate", "capped_active", "blocked", "unavailable"],
        },
        "rules_in_effect": in_effect,
        "rules_not_in_effect": not_in_effect,
    }


def trigger_for(bundle: GoldContractBundle, *, ticker: str, rule_id: str, run_id: str | None) -> dict[str, Any]:
    """The evidence trigger for one rule on one run. The frozen state is returned only for the run the matrix is bound to."""
    bound_run = bundle.matrix_runs.get(ticker)
    base = {"evaluated_run_id": run_id, "matrix_run_id": bound_run, "source": None, "strength": None, "reason_code": None, "reading": None}
    if bound_run is None:
        return {**base, "state": TRIGGER_NOT_EVALUABLE, "reason_code": REASON_TICKER_NOT_IN_MATRIX,
                "reading": f"the frozen trigger matrix has no entry for {ticker}"}
    if not run_id or run_id != bound_run:
        return {
            **base,
            "state": TRIGGER_NOT_EVALUABLE,
            "reason_code": REASON_RUN_NOT_BOUND,
            "reading": (
                f"the frozen trigger matrix is bound to {ticker} run {bound_run}; this is run {run_id}. No approved, executable evidence-determination "
                "method exists for another run, and the historical trigger state is not carried over to it"
            ),
        }
    record = bundle.matrix_rules.get((ticker, rule_id))
    if record is None or record.get("trigger_state") not in (TRIGGER_PRESENT, TRIGGER_ABSENT, TRIGGER_UNCERTAIN):
        return {**base, "state": TRIGGER_NOT_EVALUABLE, "reason_code": REASON_RULE_NOT_IN_MATRIX,
                "reading": f"the frozen trigger matrix carries no usable trigger for {rule_id} on {ticker}"}
    return {
        **base,
        "state": record["trigger_state"],
        "strength": record.get("evidence_strength"),
        "source": "frozen_evidence_trigger_matrix",
        "source_input": "; ".join(str(a) for a in record.get("source_artifacts") or ()) or None,
        "reading": f"frozen trigger {record['trigger_state']}/{record.get('evidence_strength')} for exactly this run ({run_id})",
    }


def alpha_recognition(alpha_id: str, *, activation_summary: Any, alpha_matches_payload: Any) -> dict[str, Any]:
    """What the run persisted about one Alpha, kept as separate facts: identification (claims classified to it), activation level and score.

    ``identification_state`` is ``NOT_IDENTIFIED`` (a valid NONE) only when the classification finished for every claim; a claim whose classification
    was technically unavailable never counts as 'no match', so zero matched claims plus any unavailable claim is ``UNKNOWN_CLASSIFICATION_INCOMPLETE``."""
    per_alpha = activation_summary.get("per_alpha") if isinstance(activation_summary, Mapping) else None
    entry = per_alpha.get(alpha_id) if isinstance(per_alpha, Mapping) else None
    entry = entry if isinstance(entry, Mapping) else None
    matches = alpha_matches_payload.get("matches") if isinstance(alpha_matches_payload, Mapping) else None
    if isinstance(matches, list):
        records = [m for m in matches if isinstance(m, Mapping)]
        matched = sum(1 for m in records if m.get("match_status") == "matched" and m.get("matched_alpha") == alpha_id)
        unavailable = sum(1 for m in records if m.get("match_status") == "unavailable")
        no_match = sum(1 for m in records if m.get("match_status") == "no_match")
        if matched > 0:
            state = IDENTIFIED
        elif unavailable > 0:
            state = UNKNOWN_CLASSIFICATION_INCOMPLETE
        else:
            state = NOT_IDENTIFIED
        counts: dict[str, Any] = {
            "claims_total": len(records),
            "claims_matched_to_this_alpha": matched,
            "claims_no_match": no_match,
            "claims_classification_unavailable": unavailable,
        }
    else:
        state = UNKNOWN_NO_MATCH_PAYLOAD
        counts = {"claims_total": None, "claims_matched_to_this_alpha": None, "claims_no_match": None, "claims_classification_unavailable": None}
    level = entry.get("level") if entry else None
    return {
        "alpha_id": alpha_id,
        "identification_state": state,
        **counts,
        "activation_level": level,
        "activation_score": entry.get("score") if entry else None,
        "level_is_official_detected_level": (level in _DETECTED_LEVELS) if level else None,
        "level_source": "run_audit.json:activation_summary.per_alpha" if entry else None,
        "qualification_codes": list(entry.get("qualification_codes") or ()) if entry else None,
        "unique_evidence_fact_count": entry.get("unique_evidence_fact_count") if entry else None,
        "distinct_supporting_agents": entry.get("distinct_supporting_agents") if entry else None,
        "ticker_specific_evidence_count": entry.get("ticker_specific_evidence_count") if entry else None,
    }


def _rule_header(rule: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "rule_id": rule["rule_id"],
        "ticker": rule.get("ticker"),
        "tier": rule.get("tier"),
        "hit_type": rule.get("hit_type"),
        "family": rule.get("rule_type"),
        "blocking": bool(rule.get("blocking")),
        "evidence_condition": rule.get("evidence_condition"),
        "required_behavior": rule.get("required_behavior"),
        "authority_basis": list(RULE_AUTHORITY_BASIS.get(str(rule["rule_id"]), ())),
    }


def _finish(record: dict[str, Any], verdict: str, reason_code: str | None, detail: str) -> dict[str, Any]:
    blocking = record["blocking"]
    record.update(
        {
            "verdict": verdict,
            "john_result": JOHN_RESULT[verdict],
            "reason_code": reason_code,
            "detail": detail,
            "blocks_release": verdict == VERDICT_FAIL and blocking,
            "unresolved_blocking": verdict in (VERDICT_NEEDS_REVIEW, VERDICT_NOT_EVALUABLE) and blocking,
        }
    )
    return record


def evaluate_alpha_rule(
    bundle: GoldContractBundle,
    rule: Mapping[str, Any],
    *,
    ticker: str,
    run_id: str | None,
    activation_summary: Any,
    alpha_matches_payload: Any,
) -> dict[str, Any]:
    """One ``must_detect_if_evidence_present`` ALPHA_HIT rule. John's rule: trigger PRESENT -> the Alpha detected at an official level is a PASS, not
    detected a FAIL; ABSENT -> NOT_TRIGGERED; UNCERTAIN -> REVIEW. A trigger that cannot be established for this run is NOT_EVALUABLE."""
    record = _rule_header(rule)
    alphas = [str(a) for a in rule.get("acceptable_alphas") or ()]
    recognition = [alpha_recognition(a, activation_summary=activation_summary, alpha_matches_payload=alpha_matches_payload) for a in alphas]
    detected_by = [r["alpha_id"] for r in recognition if r["level_is_official_detected_level"]]
    levels_known = all(r["activation_level"] is not None for r in recognition)
    trigger = trigger_for(bundle, ticker=ticker, rule_id=record["rule_id"], run_id=run_id)
    record.update(
        {
            "alpha_recognition": recognition,
            "requirement": {
                "acceptable_alphas": alphas,
                "required_levels": sorted(_DETECTED_LEVELS),
                "satisfied": (True if detected_by else (False if levels_known else None)),
                "satisfied_by": detected_by[0] if detected_by else None,
                "reading": _requirement_reading(recognition, levels_known=levels_known, satisfied=bool(detected_by)),
            },
            "evidence_trigger": trigger,
        }
    )
    state = trigger["state"]
    if state == TRIGGER_NOT_EVALUABLE:
        return _finish(record, VERDICT_NOT_EVALUABLE, trigger["reason_code"], f"evidence trigger not established: {trigger['reading']}")
    if state == TRIGGER_ABSENT:
        return _finish(record, VERDICT_NOT_TRIGGERED, None, "frozen evidence trigger ABSENT for this run: no detection is required and none is forced")
    if state == TRIGGER_UNCERTAIN:
        return _finish(record, VERDICT_NEEDS_REVIEW, None, "frozen evidence trigger UNCERTAIN for this run: review, never a pass or a fail")
    # trigger PRESENT: the contract requires detection at an official level
    if detected_by:
        return _finish(record, VERDICT_PASS, None, f"trigger PRESENT and {detected_by[0]} is detected at an official level")
    if not levels_known:
        return _finish(
            record,
            VERDICT_NOT_EVALUABLE,
            REASON_DETECTION_AUTHORITY_UNAVAILABLE,
            "trigger PRESENT but the run's activation level could not be read from run_audit.json (activation_summary.per_alpha)",
        )
    if all(r["identification_state"] in (UNKNOWN_CLASSIFICATION_INCOMPLETE, UNKNOWN_NO_MATCH_PAYLOAD) for r in recognition):
        return _finish(
            record,
            VERDICT_NOT_EVALUABLE,
            REASON_CLASSIFICATION_INCOMPLETE,
            "trigger PRESENT and the level is below the requirement, but no claim was classified to the Alpha while some claims were technically "
            "unclassified: 'not identified' cannot be written as a valid NONE, so the miss is not asserted",
        )
    return _finish(record, VERDICT_FAIL, None, f"trigger PRESENT but the Alpha is not detected at an official level ({_requirement_reading(recognition, levels_known=True, satisfied=False)})")


def _requirement_reading(recognition: Sequence[Mapping[str, Any]], *, levels_known: bool, satisfied: bool) -> str:
    if satisfied:
        return "an acceptable Alpha is at an official detected level"
    if not levels_known:
        return "the activation level is not available"
    parts = []
    for r in recognition:
        state = r["identification_state"]
        if state == IDENTIFIED:
            who = f"identified ({r['claims_matched_to_this_alpha']} claims classified to it) but its level is {r['activation_level']}, below the required level"
        elif state == NOT_IDENTIFIED:
            who = f"not identified (no claim classified to it; classification complete) and its level is {r['activation_level']}"
        else:
            who = (
                f"no claim classified to it, but {r['claims_classification_unavailable']} claims were technically unclassified (not a valid NONE); "
                f"its level is {r['activation_level']}"
            )
        parts.append(f"{r['alpha_id']}: {who}")
    return "; ".join(parts)


def evaluate_composite_rule(
    bundle: GoldContractBundle,
    rule: Mapping[str, Any],
    *,
    ticker: str,
    run_id: str | None,
    admitted_conflicts: Sequence[str],
    main_conflict: Any,
    allowed_family: Sequence[str],
    activation_summary: Any = None,
    alpha_matches_payload: Any = None,
    pair_records: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """One COMPOSITE_STRUCTURE_HIT / ``conditional_only`` rule. John's Step-4 logic: trigger PRESENT -> an allowed evidence-supported conflict that is
    actually admitted (ANY ONE of the allowed pairs) is a PASS; none admitted is a REVIEW that needs adjudication (never an immediate error) UNLESS the
    persisted artifact already proves a deterministic violation -- an allowed pair whose own B2 record lists no rejection reason (every condition B2 checks
    is met) and is still not admitted -- which is a FAIL; an admitted conflict outside the family is a REVIEW (the T2 sheet: keep the research output, route
    it to review). ABSENT -> NOT_TRIGGERED, UNCERTAIN -> REVIEW. Nothing here requires every allowed pair to appear, and nothing generates or removes a
    conflict.

    ``pair_records`` is what the run's own arbitration recorded per pair (``{"state", "b2_status", "b2_reason_codes", "entry_reason_codes"}``, built by the
    acceptance engine from the saved conflicts.json); a family pair absent from it has no record.

    ``allowed_family`` is the ticker's allowed pairs as the acceptance label carries them: John's later written baseline controls the family (for
    AMD it adds A201__A304 to the contract's two pairs); the contract's own pairs are always included."""
    record = _rule_header(rule)
    contract_pairs = sorted({_normalize_pair(p) for p in rule.get("allowed_main_conflicts") or ()})
    family = sorted({*contract_pairs, *(_normalize_pair(p) for p in allowed_family)})
    admitted = sorted({_normalize_pair(p) for p in admitted_conflicts})
    in_family = sorted(set(admitted) & set(family))
    outside = sorted(set(admitted) - set(family))
    trigger = trigger_for(bundle, ticker=ticker, rule_id=record["rule_id"], run_id=run_id)
    main_id = main_conflict.get("conflict_id") if isinstance(main_conflict, Mapping) else main_conflict
    family_records = {
        pair: {
            "state": (pair_records or {}).get(pair, {}).get("state", PAIR_STATE_NO_RECORD),
            "b2_status": (pair_records or {}).get(pair, {}).get("b2_status"),
            "b2_reason_codes": list((pair_records or {}).get(pair, {}).get("b2_reason_codes") or ()),
            "entry_reason_codes": list((pair_records or {}).get(pair, {}).get("entry_reason_codes") or ()),
        }
        for pair in family
    }
    record.update(
        {
            # context for the reader (John's Step 4: "inspect the relevant actual Alpha states"); it decides nothing
            "component_alphas": [
                alpha_recognition(str(a), activation_summary=activation_summary, alpha_matches_payload=alpha_matches_payload)
                for a in rule.get("acceptable_alphas") or ()
            ],
            "allowed_pairs_in_contract": contract_pairs,
            "allowed_family": family,
            "admitted_conflicts": admitted,
            "admitted_in_allowed_family": in_family,
            "admitted_outside_allowed_family": outside,
            "family_pair_records": family_records,
            "main_conflict": _normalize_pair(main_id) if main_id else None,
            "requirement": {
                "logic": "any ONE allowed pair admitted satisfies the composite; no allowed pair is individually required",
                "satisfied": bool(in_family) if trigger["state"] == TRIGGER_PRESENT else None,
            },
            "evidence_trigger": trigger,
        }
    )
    state = trigger["state"]
    if state == TRIGGER_NOT_EVALUABLE:
        return _finish(record, VERDICT_NOT_EVALUABLE, trigger["reason_code"], f"evidence trigger not established: {trigger['reading']}")
    if state == TRIGGER_ABSENT:
        return _finish(record, VERDICT_NOT_TRIGGERED, None, "frozen composite trigger ABSENT for this run: no conflict is required and none is forced")
    if state == TRIGGER_UNCERTAIN:
        return _finish(record, VERDICT_NEEDS_REVIEW, None, "frozen composite trigger UNCERTAIN for this run: review")
    if in_family:
        return _finish(record, VERDICT_PASS, None, f"trigger PRESENT and an allowed conflict is admitted: {', '.join(in_family)}")
    complete_yet_not_admitted = sorted(pair for pair, r in family_records.items() if r["state"] == PAIR_STATE_B2_NO_REASON)
    if complete_yet_not_admitted:
        return _finish(
            record,
            VERDICT_FAIL,
            REASON_ALLOWED_PAIR_COMPLETE_NOT_ADMITTED,
            f"trigger PRESENT and B2's own record for {', '.join(complete_yet_not_admitted)} lists no rejection reason (every condition it checks is met) yet the "
            "pair is not admitted: the persisted artifact proves a deterministic violation of the contract, not a gap that needs adjudication",
        )
    why = "; ".join(
        f"{pair}: {r['state']}" + (f" [{', '.join(r['b2_reason_codes'] or r['entry_reason_codes'])}]" if (r["b2_reason_codes"] or r["entry_reason_codes"]) else "")
        for pair, r in family_records.items()
    )
    record["requires_adjudication"] = True
    if outside:
        return _finish(
            record,
            VERDICT_NEEDS_REVIEW,
            REASON_ADMITTED_OUTSIDE_FAMILY,
            f"trigger PRESENT; the admitted conflict(s) {', '.join(outside)} are outside the allowed family and no allowed pair is admitted "
            f"(the research output is kept and routed to review). What the run recorded for each allowed pair: {why}",
        )
    return _finish(
        record,
        VERDICT_NEEDS_REVIEW,
        REASON_NO_ALLOWED_PAIR_ADMITTED,
        "trigger PRESENT but no conflict is admitted: not an immediate system error (B2 may have correctly rejected every pair); root-cause adjudication "
        f"required. What the run recorded for each allowed pair: {why}",
    )


RELEASE_BLOCKED = "blocked"
RELEASE_UNRESOLVED = "unresolved"
RELEASE_NO_BLOCKER_AMONG_EXECUTED = "no_blocker_among_executed_rules"


def release_impact(results: Sequence[Mapping[str, Any]], not_executed: Sequence[str] = ()) -> dict[str, Any]:
    """Severity as the contract fixes it: only a FAIL of a blocking rule blocks release; a non-blocking rule never does.

    ``release_status`` is scoped to the rules this entry executes and is NOT a release certification: ``blocked`` (a blocking rule failed),
    ``unresolved`` (a blocking rule could not be evaluated or needs adjudication) or ``no_blocker_among_executed_rules`` -- the ticker's contract
    rules that are not executed (``contract_rules_not_executed``) say nothing either way."""
    blocking_failures = [r["rule_id"] for r in results if r["blocks_release"]]
    blocking_unresolved = [r["rule_id"] for r in results if r["unresolved_blocking"]]
    non_blocking = [
        {"rule_id": r["rule_id"], "verdict": r["verdict"], "reason_code": r["reason_code"]}
        for r in results
        if not r["blocking"] and r["verdict"] in (VERDICT_FAIL, VERDICT_NEEDS_REVIEW, VERDICT_NOT_EVALUABLE)
    ]
    return {
        "scope": "the contract rules this entry executes for the ticker; not a release certification; label-based findings carry no contract severity",
        "contract_rules_executed": len(results),
        "contract_rules_not_executed": list(not_executed),
        "blocks_release": bool(blocking_failures),
        "blocking_failures": blocking_failures,
        "blocking_unresolved": blocking_unresolved,
        "non_blocking_findings": non_blocking,
        "release_status": (
            RELEASE_BLOCKED if blocking_failures else RELEASE_UNRESOLVED if blocking_unresolved else RELEASE_NO_BLOCKER_AMONG_EXECUTED
        ),
    }


def evaluate_contract_rules(
    bundle: GoldContractBundle,
    *,
    ticker: str,
    run_id: str | None,
    activation_summary: Any,
    alpha_matches_payload: Any,
    admitted_conflicts: Sequence[str],
    main_conflict: Any,
    allowed_family: Sequence[str],
    pair_records: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Executes the contract rules that belong to ``ticker``. A ticker none of them belongs to gets an empty result: nothing is evaluated and
    nothing is implied for it."""
    results: list[dict[str, Any]] = []
    for rule in bundle.executed_rules_for(ticker):
        if rule.get("hit_type") == "COMPOSITE_STRUCTURE_HIT":
            results.append(
                evaluate_composite_rule(
                    bundle,
                    rule,
                    ticker=ticker,
                    run_id=run_id,
                    admitted_conflicts=admitted_conflicts,
                    main_conflict=main_conflict,
                    allowed_family=allowed_family,
                    activation_summary=activation_summary,
                    alpha_matches_payload=alpha_matches_payload,
                    pair_records=pair_records,
                )
            )
        else:
            results.append(
                evaluate_alpha_rule(
                    bundle, rule, ticker=ticker, run_id=run_id, activation_summary=activation_summary, alpha_matches_payload=alpha_matches_payload
                )
            )
    not_executed = sorted(r["rule_id"] for r in bundle.rules_by_id.values() if r.get("ticker") == ticker and r["rule_id"] not in _EXECUTED_RULES)
    return {"results": results, "release": release_impact(results, not_executed), "contract_rules_not_executed_for_ticker": not_executed}


__all__ = [
    "DEFAULT_CONTRACT_PATH",
    "DEFAULT_FREEZE_MANIFEST_PATH",
    "DEFAULT_TRIGGER_MATRIX_PATH",
    "EXECUTED_RULE_IDS",
    "FROZEN_TRIGGER_MATRIX_SHA256",
    "GoldContractBundle",
    "GoldContractError",
    "JOHN_RESULT",
    "RULE_AUTHORITY_BASIS",
    "alpha_recognition",
    "describe_bundle",
    "evaluate_alpha_rule",
    "evaluate_composite_rule",
    "evaluate_contract_rules",
    "load_gold_contract_bundle",
    "RELEASE_BLOCKED",
    "RELEASE_NO_BLOCKER_AMONG_EXECUTED",
    "RELEASE_UNRESOLVED",
    "release_impact",
    "trigger_for",
]
