"""Alpha evidence consumption contract v2 (``alpha_evidence_consumption.v2``; T1 follow-up migration, round 36).

One module owns the rules by which a (claim, matched Alpha) pair is consumed downstream; every entry point that needs one of
those rules calls the functions here instead of re-deriving it.

What it adds, and what it never touches
---------------------------------------
For each committed match it writes ONE ``consumption`` block INSIDE the matched Alpha's ``candidate_scores`` entry (so it is
per claim-Alpha pair and cannot leak to another Alpha, and it travels with the ``candidate_scores`` JSON column that the
production persistence path already stores). The block is purely ADDITIVE:

* the original Alpha selection, the model stance, the text-rule relation / assertion / polarity and the lexical score are NOT
  rewritten -- ``relation`` is never changed to ``mention``, so reverse evidence and DirectionConsistency are untouched;
* the block records them (``text_rule``, ``stance``, ``relevance.lexical_baseline``) as the raw baseline next to what the
  contract decided.

Approved policies carried by v2 (the owner's decisions of 2026-10-10; none is John's sign-off)
* ``alpha_stance_policy.v1`` -- R-1: a MODEL-JUDGED stance of ``opposes_alpha`` / ``neutral_background`` / ``mentions_alpha`` /
  ``supports_counter_alpha`` toward the matched Alpha excludes the claim from THAT Alpha's positive pool, through the explicit
  ``positive_admission`` field. It only subtracts: it never admits a claim, never touches another Alpha, never rewrites the
  reverse-evidence channel. An unjudged stance (missing, timeout, parse failure, fallback, unverifiable) adds NO exclusion.
* ``company_attribution.name.v1`` -- name presence (see ``company_attribution``); ``TARGET_BY_SOURCE_OBJECT`` stays disabled.
* ``alpha_relevance_fallback.v1`` -- DISCLOSURE only: no relevance judgment exists in this version; the lexical score is consumed
  unchanged and is labelled ``LEXICAL_RULE_FALLBACK``; the model weight is ``null``.

Added 2026-10-13 (the owner's instruction to fix John's named T3 consumption defects; still not John's sign-off)
* ``alpha_statement_scope.v2`` -- the text rule's whole-claim negation is re-read per pair (``statement_scope``): a negator that
  only sits in a citation marker or in a negated protection of a risk never negates this Alpha's statement; one in the rejected
  alternative of a contrast, or in another clause than this Alpha's own matched terms, is removed only when the pair's
  ledger-corroborated model stance is ``supports_alpha`` (the anchor that says which side carries the Alpha's statement).
  The stored text-rule fields stay as they were (``text_rule``); the positive gates and the scorer read
  ``statement_scope.effective``. The anchor only withholds a re-read, never grants one, and the source support is never read,
  so the scope cannot let a claim bypass R-1, the source gate or any other gate.
* ``alpha_direction_stance_policy.v1`` -- DirectionConsistency reads the same ``positive_admission``: a claim R-1 keeps out of the
  positive pool is not counted as POSITIVE direction evidence either (subtract only; negative and neutral signs are unchanged).

A MODEL-JUDGED stance must be bound to the right claim and Alpha and must come from a valid model result. ``method == "llm"``
and a legal label are NOT enough: the candidate's own provenance fields must be self-consistent (version, no fallback reason,
no manual-review flag, no deterministic residue, a legal counter-Alpha, all candidate copies agreeing) and, because the
exclusion removes evidence, the run's semantic ledger must independently hold an accepted validated output for the same
(claim_id, target_alpha_id) with the same label. Without that corroboration the stance is reported as unjudged
(``ledger_unavailable`` / ``pair_not_in_ledger`` / ...), never as an exclusion.

Failure is explicit: an unknown contract version, a ticker or pair mismatch, or a stale input binding raises
``EvidenceConsumptionError``; the Week 3 pipeline logs it under its own stage code and produces no result. Nothing here falls back
silently and then reports success.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from comqutor_alpha.graph_engine.company_attribution import (
    COMPANY_ATTRIBUTION_POLICY_VERSION,
    attribution_text,
    resolve_name_attribution,
)
from comqutor_alpha.graph_engine.statement_scope import (
    STATEMENT_SCOPE_POLICY_VERSION,
    matched_terms,
    statement_scope_for_match,
)

CONSUMPTION_CONTRACT_V2 = "alpha_evidence_consumption.v2"
SUPPORTED_CONTRACTS = frozenset({CONSUMPTION_CONTRACT_V2})
CONSUMPTION_METADATA_KEY = "alpha_evidence_consumption"  # run metadata.json: absent => legacy
CONSUMPTION_BLOCK_KEY = "consumption"  # inside candidate_scores[<matched alpha>]
PAYLOAD_CONTRACT_KEY = "evidence_consumption_contract"  # alpha_matches.json top level, written once the contract was applied

STANCE_POLICY_VERSION = "alpha_stance_policy.v1"
RELEVANCE_POLICY_VERSION = "alpha_relevance_fallback.v1"
DIRECTION_POLICY_VERSION = "alpha_direction_stance_policy.v1"
POLICY_VERSIONS = {
    "stance": STANCE_POLICY_VERSION,
    "attribution": COMPANY_ATTRIBUTION_POLICY_VERSION,
    "relevance": RELEVANCE_POLICY_VERSION,
    "statement_scope": STATEMENT_SCOPE_POLICY_VERSION,
    "direction": DIRECTION_POLICY_VERSION,
}

# R-1 (owner decision A1, 2026-10-10): the labels that exclude a claim from the matched Alpha's positive pool when the stance
# is a validated model result.
R1_EXCLUDING_STANCES = frozenset({"opposes_alpha", "neutral_background", "mentions_alpha", "supports_counter_alpha"})
REASON_STANCE_MODEL_NOT_SUPPORTING = "STANCE_MODEL_NOT_SUPPORTING"

STANCE_MODEL_JUDGED = "MODEL_JUDGED"
STANCE_UNJUDGED = "UNJUDGED"
# how an unjudged stance is disclosed (missing, timeout, parse failure and fallback are reported separately)
UNJUDGED_MISSING = "MISSING"
UNJUDGED_TIMEOUT = "TIMEOUT"
UNJUDGED_PARSE_FAILED = "PARSE_FAILED"
UNJUDGED_FALLBACK = "FALLBACK"
UNJUDGED_UNVERIFIED = "UNVERIFIED"
_FALLBACK_REASON_CATEGORY = {
    "missing_result": UNJUDGED_MISSING,
    "timeout": UNJUDGED_TIMEOUT,
    "malformed_response": UNJUDGED_PARSE_FAILED,
    "invalid_stance": UNJUDGED_PARSE_FAILED,
    "invalid_counter_alpha": UNJUDGED_PARSE_FAILED,
    "identity_mismatch": UNJUDGED_PARSE_FAILED,
    "duplicate_result": UNJUDGED_PARSE_FAILED,
    "provider_error": UNJUDGED_FALLBACK,
    "provider_stopped": UNJUDGED_FALLBACK,
    "input_too_large": UNJUDGED_FALLBACK,
}

WEIGHT_AUTHORITY_LEXICAL_FALLBACK = "LEXICAL_RULE_FALLBACK"
RELEVANCE_STATE_UNJUDGED = "UNJUDGED"

# Reason codes of EvidenceConsumptionError
REASON_ILLEGAL_CONTRACT_VERSION = "EVIDENCE_CONSUMPTION_ILLEGAL_CONTRACT_VERSION"
REASON_INPUT_INVALID = "EVIDENCE_CONSUMPTION_INPUT_INVALID"
REASON_TICKER_MISMATCH = "EVIDENCE_CONSUMPTION_TICKER_MISMATCH"
REASON_PAIR_MISMATCH = "EVIDENCE_CONSUMPTION_PAIR_MISMATCH"
REASON_BINDING_STALE = "EVIDENCE_CONSUMPTION_BINDING_STALE"
REASON_DECISION_INCONSISTENT = "EVIDENCE_CONSUMPTION_DECISION_INCONSISTENT"
REASON_BLOCK_MISSING = "EVIDENCE_CONSUMPTION_BLOCK_MISSING"
REASON_CANDIDATE_MISSING = "EVIDENCE_CONSUMPTION_CANDIDATE_MISSING"

_CANDIDATE_POOLS = ("candidate_scores", "top_candidates", "eligible_candidates")
_STANCE_FIELDS = (
    "evidence_stance",
    "stance_method",
    "evidence_stance_version",
    "stance_fallback_reason",
    "counter_alpha_id",
    "requires_manual_review",
    "stance_confidence_band",
    "stance_reason_codes",
)


class EvidenceConsumptionError(Exception):
    """A consumption contract violation. ``reason_code`` is a stable safe code (never exception text)."""

    def __init__(self, reason_code: str, detail: str | None = None) -> None:
        self.reason_code = reason_code
        self.detail = detail
        super().__init__(reason_code if detail is None else f"{reason_code}: {detail}")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _finite_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) else None


# ---------------------------------------------------------------------------
# Locating the block and the matched candidate
# ---------------------------------------------------------------------------


def matched_candidate(match: Mapping[str, Any]) -> dict[str, Any] | None:
    """The ``candidate_scores`` entry of the matched Alpha -- the one canonical place the block lives."""
    alpha_id = str(match.get("matched_alpha") or "")
    if not alpha_id:
        return None
    for candidate in match.get("candidate_scores") or ():
        if isinstance(candidate, dict) and str(candidate.get("alpha_id")) == alpha_id:
            return candidate
    return None


def block_for_match(match: Mapping[str, Any]) -> dict[str, Any] | None:
    candidate = matched_candidate(match)
    block = candidate.get(CONSUMPTION_BLOCK_KEY) if candidate else None
    return block if isinstance(block, dict) else None


def _stray_block_alpha(match: Mapping[str, Any]) -> str | None:
    """The Alpha of a candidate that carries a block although it is NOT the record's matched Alpha -- the footprint of a record
    that was re-matched (or un-matched) after the contract was applied. Such a block must never be silently ignored."""
    matched = str(match.get("matched_alpha") or "") if match.get("match_status") == "matched" else ""
    for candidate in match.get("candidate_scores") or ():
        if isinstance(candidate, Mapping) and isinstance(candidate.get(CONSUMPTION_BLOCK_KEY), Mapping) and str(candidate.get("alpha_id")) != matched:
            return str(candidate.get("alpha_id"))
    return None


def _taxonomy(taxonomy: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if taxonomy is not None:
        return taxonomy
    from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy  # noqa: PLC0415

    return load_alpha_taxonomy()


# ---------------------------------------------------------------------------
# The run's semantic ledger (independent corroboration of a model stance)
# ---------------------------------------------------------------------------

STANCE_TASK = "evidence_stance_classifier"
LEDGER_FILENAME = "llm_semantic_calls.jsonl"
LEDGER_MANIFEST_FILENAME = "llm_semantic_manifest.json"

# Ledger binding (2026-10-11). A derived execution recomputes a SAVED run's inputs; it does not copy the original model-call ledger (that
# ledger describes the original run's own calls), so its stances can only be corroborated against the ledger of the run that produced
# them. The execution declares that binding explicitly in its metadata -- the source run (which must be in its own lineage) and the
# sha256 of that run's ledger -- and the binding is verified on every read. Undeclared, mismatched or missing => no usable ledger (no
# exclusion follows). ``owner_run_id`` / ``binding`` say WHOSE ledger corroborated a stance, kept apart from the executing run's id.
LEDGER_BINDING_METADATA_KEY = "stance_ledger_binding"
LEDGER_BINDING_OWN_RUN = "OWN_RUN"
LEDGER_BINDING_SOURCE_DECLARED = "SOURCE_RUN_DECLARED"
# execution_type of a derived execution that recomputes a saved run's inputs under an explicitly chosen contract (created only by
# comqutor_alpha.consumption_recompute; never a Fresh Run, never a model/search/data-fetch call)
CONSUMPTION_RECOMPUTE_EXECUTION_TYPE = "alpha_evidence_consumption_recompute"


class StanceLedgerIndex:
    """Accepted, validated stance outputs of one run, keyed by (claim_id, target_alpha_id).

    ``integrity``: ``MATCHES_MANIFEST`` (the file hash equals the manifest's ``calls_file_sha256``), ``NO_MANIFEST``, or
    ``MISMATCH_MANIFEST`` / ``MANIFEST_WITHOUT_HASH`` -- the last two make the ledger unusable as corroboration. A declared binding adds
    ``BINDING_SHA_MISMATCH`` / ``BOUND_LEDGER_MISSING`` / ``BINDING_INVALID`` / ``BINDING_NOT_IN_LINEAGE`` (all unusable)."""

    def __init__(
        self,
        pairs: dict[tuple[str, str], set[tuple[str, str | None]]],
        *,
        path: str,
        sha256: str,
        integrity: str,
        accepted_batches: int,
        owner_run_id: str | None = None,
        binding: str = LEDGER_BINDING_OWN_RUN,
        declared_sha256: str | None = None,
    ) -> None:
        self.pairs = pairs
        self.path = path
        self.sha256 = sha256
        self.integrity = integrity
        self.accepted_batches = accepted_batches
        self.owner_run_id = owner_run_id
        self.binding = binding
        self.declared_sha256 = declared_sha256

    @property
    def usable(self) -> bool:
        return self.integrity in ("MATCHES_MANIFEST", "NO_MANIFEST")

    @classmethod
    def load(
        cls,
        ledger_path: str | Path,
        manifest_path: str | Path | None = None,
        *,
        owner_run_id: str | None = None,
        binding: str = LEDGER_BINDING_OWN_RUN,
        declared_sha256: str | None = None,
    ) -> StanceLedgerIndex:
        raw = Path(ledger_path).read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        integrity = "NO_MANIFEST"
        if manifest_path is not None and Path(manifest_path).is_file():
            try:
                expected = json.loads(Path(manifest_path).read_text(encoding="utf-8")).get("calls_file_sha256")
            except ValueError:
                expected = None
            integrity = "MANIFEST_WITHOUT_HASH" if not expected else ("MATCHES_MANIFEST" if expected == sha else "MISMATCH_MANIFEST")
        if declared_sha256 is not None and declared_sha256 != sha:
            integrity = "BINDING_SHA_MISMATCH"
        pairs: dict[tuple[str, str], set[tuple[str, str | None]]] = {}
        batches = 0
        for line in raw.decode("utf-8", "replace").splitlines():
            if f'"{STANCE_TASK}"' not in line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("task") != STANCE_TASK or record.get("provider_status") != "success" or record.get("validation_status") != "accepted":
                continue
            output = record.get("validated_output")
            items = output.get("items") if isinstance(output, Mapping) else output
            if not isinstance(items, list):
                continue
            batches += 1
            for item in items:
                if isinstance(item, Mapping) and item.get("claim_id") and item.get("target_alpha_id") and item.get("stance"):
                    key = (str(item["claim_id"]), str(item["target_alpha_id"]))
                    pairs.setdefault(key, set()).add((str(item["stance"]), str(item["counter_alpha_id"]) if item.get("counter_alpha_id") else None))
        return cls(pairs, path=str(ledger_path), sha256=sha, integrity=integrity, accepted_batches=batches,
                   owner_run_id=owner_run_id, binding=binding, declared_sha256=declared_sha256)


def load_stance_ledger(run_dir: str | Path) -> StanceLedgerIndex | None:
    """The run's OWN ledger (``None`` when the run directory has none)."""
    ledger = Path(run_dir) / LEDGER_FILENAME
    if not ledger.is_file():
        return None
    return StanceLedgerIndex.load(ledger, Path(run_dir) / LEDGER_MANIFEST_FILENAME, owner_run_id=Path(run_dir).name)


def resolve_stance_ledger(run_dir: str | Path, metadata: Mapping[str, Any] | None = None) -> StanceLedgerIndex | None:
    """The ledger that corroborates this run's stances: its own ledger if it has one; otherwise the ledger of the source run named by an
    explicit ``stance_ledger_binding`` in its metadata -- that run must be the execution's ``based_on_run_id`` or ``root_research_run_id``,
    must live next to it under the same output root, and its ledger must still hash to the declared ``calls_file_sha256``. No binding ->
    ``None``. A declared binding that cannot be honoured returns an UNUSABLE index (so the stances are unjudged and nothing is excluded),
    never a silent fallback to "no ledger"."""
    run_dir = Path(run_dir)
    own = load_stance_ledger(run_dir)
    if own is not None:
        return own
    declared = metadata.get(LEDGER_BINDING_METADATA_KEY) if isinstance(metadata, Mapping) else None
    if declared is None:
        return None

    def unusable(integrity: str, owner: str | None = None, path: str = "", declared_sha: str | None = None) -> StanceLedgerIndex:
        return StanceLedgerIndex({}, path=path, sha256="", integrity=integrity, accepted_batches=0, owner_run_id=owner,
                                 binding=LEDGER_BINDING_SOURCE_DECLARED, declared_sha256=declared_sha)

    source_run_id, declared_sha = (declared.get("source_run_id"), declared.get("calls_file_sha256")) if isinstance(declared, Mapping) else (None, None)
    if not isinstance(source_run_id, str) or not isinstance(declared_sha, str) or len(declared_sha) != 64:
        return unusable("BINDING_INVALID")
    from comqutor_alpha.storage.file_store import (
        validate_run_id_for_path,  # noqa: PLC0415 -- stdlib-only module, no cycle
    )

    try:
        safe_source = validate_run_id_for_path(source_run_id)
    except ValueError:
        return unusable("BINDING_INVALID", declared_sha=declared_sha)
    lineage = {str(metadata.get(key)) for key in ("based_on_run_id", "root_research_run_id") if metadata.get(key)}  # type: ignore[union-attr]
    if safe_source not in lineage:
        return unusable("BINDING_NOT_IN_LINEAGE", owner=safe_source, declared_sha=declared_sha)
    source_dir = run_dir.parent / safe_source
    ledger = source_dir / LEDGER_FILENAME
    if not ledger.is_file():
        return unusable("BOUND_LEDGER_MISSING", owner=safe_source, path=str(ledger), declared_sha=declared_sha)
    return StanceLedgerIndex.load(ledger, source_dir / LEDGER_MANIFEST_FILENAME, owner_run_id=safe_source,
                                  binding=LEDGER_BINDING_SOURCE_DECLARED, declared_sha256=declared_sha)


def ledger_description(ledger: StanceLedgerIndex | None) -> dict[str, Any]:
    """Whose ledger corroborated the stances, how it was bound and whether it is usable -- the same shape in the blocks, the run
    summary and the trace."""
    if ledger is None:
        return {"available": False, "integrity": None, "sha256": None, "owner_run_id": None, "binding": None}
    return {"available": True, "integrity": ledger.integrity, "sha256": ledger.sha256 or None, "owner_run_id": ledger.owner_run_id,
            "binding": ledger.binding, "usable": ledger.usable}


# ---------------------------------------------------------------------------
# Stance judgement: valid model result or unjudged, never inferred from method + label alone
# ---------------------------------------------------------------------------


def _llm_constants() -> tuple[str, str, str]:
    from comqutor_alpha.structure_engine.evidence_stance_llm import (  # noqa: PLC0415
        LLM_CLASSIFIER_VERSION,
        STANCE_METHOD_DETERMINISTIC_FALLBACK,
        STANCE_METHOD_LLM,
    )

    return LLM_CLASSIFIER_VERSION, STANCE_METHOD_LLM, STANCE_METHOD_DETERMINISTIC_FALLBACK


def _unjudged(candidate: Mapping[str, Any] | None, category: str, reason: str, **checks: Any) -> dict[str, Any]:
    candidate = candidate or {}
    return {
        "state": STANCE_UNJUDGED,
        "label": candidate.get("evidence_stance"),
        "method": candidate.get("stance_method"),
        "version": candidate.get("evidence_stance_version"),
        "counter_alpha_id": candidate.get("counter_alpha_id"),
        "unjudged_category": category,
        "unjudged_reason": reason,
        "ledger": checks.get("ledger", "NOT_CHECKED"),
    }


def stance_judgement(
    match: Mapping[str, Any],
    candidate: Mapping[str, Any] | None,
    alpha_id: str,
    *,
    taxonomy: Mapping[str, Any] | None,
    ledger: StanceLedgerIndex | None,
) -> dict[str, Any]:
    llm_version, method_llm, method_fallback = _llm_constants()
    if candidate is None:
        return _unjudged(None, UNJUDGED_MISSING, "candidate_missing")
    method = candidate.get("stance_method")
    if method is None:
        return _unjudged(candidate, UNJUDGED_MISSING, "no_stance_result")
    if method == method_fallback:
        reason = str(candidate.get("stance_fallback_reason") or "unspecified_fallback")
        return _unjudged(candidate, _FALLBACK_REASON_CATEGORY.get(reason, UNJUDGED_FALLBACK), reason)
    if method != method_llm:
        return _unjudged(candidate, UNJUDGED_UNVERIFIED, "unknown_method")

    # method == "llm": the record must be self-consistent before it counts as a model result at all
    from comqutor_alpha.structure_engine.evidence_stance import (  # noqa: PLC0415
        VALID_EVIDENCE_STANCES,
        canonical_conflict_partners,
    )

    label = candidate.get("evidence_stance")
    if candidate.get("evidence_stance_version") != llm_version:
        return _unjudged(candidate, UNJUDGED_UNVERIFIED, "version_mismatch")
    if candidate.get("stance_fallback_reason") not in (None, ""):
        return _unjudged(candidate, UNJUDGED_UNVERIFIED, "fallback_reason_on_model_result")
    if label not in VALID_EVIDENCE_STANCES:
        return _unjudged(candidate, UNJUDGED_UNVERIFIED, "illegal_label")
    if candidate.get("requires_manual_review"):
        return _unjudged(candidate, UNJUDGED_UNVERIFIED, "manual_review_flag")
    if candidate.get("stance_confidence_band") is not None or candidate.get("stance_reason_codes"):
        return _unjudged(candidate, UNJUDGED_UNVERIFIED, "deterministic_residue_on_model_result")
    counter = candidate.get("counter_alpha_id")
    if label == "supports_counter_alpha":
        if not counter or str(counter) == alpha_id or str(counter) not in canonical_conflict_partners(alpha_id, _taxonomy(taxonomy)):
            return _unjudged(candidate, UNJUDGED_UNVERIFIED, "counter_alpha_invalid")
    elif counter not in (None, ""):
        return _unjudged(candidate, UNJUDGED_UNVERIFIED, "counter_alpha_unexpected")
    for pool in ("eligible_candidates", "top_candidates"):
        for other in match.get(pool) or ():
            if (
                isinstance(other, Mapping)
                and other.get("alpha_id") == alpha_id
                and any(other.get(k) != candidate.get(k) for k in _STANCE_FIELDS)
            ):
                return _unjudged(candidate, UNJUDGED_UNVERIFIED, "candidate_copies_disagree")

    # independent corroboration (the exclusion removes evidence, so it must rest on the run's own validated output)
    if ledger is None:
        return _unjudged(candidate, UNJUDGED_UNVERIFIED, "ledger_unavailable", ledger="NO_LEDGER")
    if not ledger.usable:
        return _unjudged(candidate, UNJUDGED_UNVERIFIED, "ledger_integrity_failed", ledger=ledger.integrity)
    entries = ledger.pairs.get((str(match.get("claim_id") or ""), alpha_id))
    if not entries:
        return _unjudged(candidate, UNJUDGED_UNVERIFIED, "pair_not_in_ledger", ledger="PAIR_NOT_IN_LEDGER")
    if len(entries) > 1:
        return _unjudged(candidate, UNJUDGED_UNVERIFIED, "ledger_conflict", ledger="LEDGER_CONFLICT")
    ledger_label, ledger_counter = next(iter(entries))
    if ledger_label != label or (ledger_counter or None) != (str(counter) if counter else None):
        return _unjudged(candidate, UNJUDGED_UNVERIFIED, "ledger_label_mismatch", ledger="LABEL_MISMATCH")
    return {
        "state": STANCE_MODEL_JUDGED,
        "label": label,
        "method": method,
        "version": candidate.get("evidence_stance_version"),
        "counter_alpha_id": str(counter) if counter else None,
        "unjudged_category": None,
        "unjudged_reason": None,
        "ledger": "VERIFIED",
    }


def model_supports_anchor(stance: Mapping[str, Any]) -> bool:
    """The statement scope's anchor: the pair's stance is a validated (ledger-corroborated) model judgment ``supports_alpha``."""
    return stance.get("state") == STANCE_MODEL_JUDGED and stance.get("label") == "supports_alpha"


def positive_admission_for(stance: Mapping[str, Any]) -> dict[str, Any]:
    """The explicit field the positive-support gates read (R-1). Subtractive only."""
    excluded = stance.get("state") == STANCE_MODEL_JUDGED and stance.get("label") in R1_EXCLUDING_STANCES
    return {
        "admitted": not excluded,
        "reason_code": REASON_STANCE_MODEL_NOT_SUPPORTING if excluded else None,
        "label": stance.get("label") if excluded else None,
        "policy": STANCE_POLICY_VERSION,
    }


# ---------------------------------------------------------------------------
# Building one block
# ---------------------------------------------------------------------------


def binding_inputs(match: Mapping[str, Any], candidate: Mapping[str, Any], alpha_id: str, ticker: str) -> dict[str, Any]:
    """Everything in the match record the block's decisions are computed from (and nothing else)."""
    return {
        "claim_id": str(match.get("claim_id") or ""),
        "alpha_id": alpha_id,
        "ticker": ticker,
        "text": attribution_text(match),
        "text_rule": {
            "relation": candidate.get("relation"),
            "assertion_status": match.get("assertion_status"),
            "semantic_polarity": match.get("semantic_polarity"),
        },
        "lexical_score": _finite_or_none(match.get("score")),
        "stance_fields": {key: candidate.get(key) for key in _STANCE_FIELDS},
        "matched_terms": matched_terms(candidate),
        "policies": dict(POLICY_VERSIONS),
    }


def _source_support_mirror(record: Mapping[str, Any] | None, sources: Sequence[Mapping[str, Any]] | None) -> dict[str, Any]:
    if record is None:
        return {"link_status": None, "verified_eligible": False, "eligibility_reason": "NO_STRUCTURED_RECORD"}
    from comqutor_alpha.source_provenance import (  # noqa: PLC0415
        compute_verified_support_eligibility,
    )

    eligibility = compute_verified_support_eligibility(record, cast("list[dict[str, Any]] | None", list(sources) if sources is not None else None))
    return {
        "link_status": record.get("source_link_status"),
        "linked_source_id": record.get("linked_source_id"),
        "content_support_status": record.get("content_support_status"),
        "content_support_method": record.get("content_support_method"),
        "verified_eligible": bool(eligibility.get("eligible")),
        "eligibility_reason": eligibility.get("reason_code"),
    }


def build_block(
    match: Mapping[str, Any],
    candidate: Mapping[str, Any],
    alpha_id: str,
    ticker: str,
    *,
    record: Mapping[str, Any] | None,
    sources: Sequence[Mapping[str, Any]] | None,
    taxonomy: Mapping[str, Any] | None,
    ledger: StanceLedgerIndex | None,
) -> dict[str, Any]:
    stance = stance_judgement(match, candidate, alpha_id, taxonomy=taxonomy, ledger=ledger)
    lexical = _finite_or_none(match.get("score"))
    source_support = _source_support_mirror(record, sources)
    return {
        "contract": CONSUMPTION_CONTRACT_V2,
        "ticker": ticker,
        "claim_id": str(match.get("claim_id") or ""),
        "alpha_id": alpha_id,
        "policies": dict(POLICY_VERSIONS),
        "binding": {
            "input_sha256": canonical_sha256(binding_inputs(match, candidate, alpha_id, ticker)),
            "source_state_sha256": canonical_sha256(source_support),
            "ledger": ledger_description(ledger),
        },
        "text_rule": {
            "relation": candidate.get("relation"),
            "assertion_status": match.get("assertion_status"),
            "semantic_polarity": match.get("semantic_polarity"),
        },
        "statement_scope": statement_scope_for_match(match, candidate, alpha_id, model_supports=model_supports_anchor(stance)),
        "stance": stance,
        "positive_admission": positive_admission_for(stance),
        "attribution": resolve_name_attribution(match, ticker),
        "relevance": {
            "policy": RELEVANCE_POLICY_VERSION,
            "state": RELEVANCE_STATE_UNJUDGED,
            "model_level": None,
            "model_weight": None,
            "lexical_baseline": lexical,
            "effective_weight": lexical,
            "weight_authority": WEIGHT_AUTHORITY_LEXICAL_FALLBACK,
            "note": "No relevance judgment exists in this contract version. The lexical score is consumed unchanged; it is not a model strength.",
        },
        "source_support": source_support,
    }


# ---------------------------------------------------------------------------
# Applying the contract to a payload (idempotent, additive)
# ---------------------------------------------------------------------------


def _strip_blocks(match: dict[str, Any]) -> None:
    match.pop(CONSUMPTION_BLOCK_KEY, None)
    for pool in _CANDIDATE_POOLS:
        for candidate in match.get(pool) or ():
            if isinstance(candidate, dict):
                candidate.pop(CONSUMPTION_BLOCK_KEY, None)


def build_attribution_only_block(match: Mapping[str, Any], ticker: str) -> dict[str, Any]:
    """The block of a claim that is matched to NO Alpha. There is no pair to bind a stance or an admission to, but the name
    decision is a property of the claim text and the target ticker, and entries that look at unmatched claims (unclassified
    findings) must read the same name rule. It sits on the record itself (``consumption``), not in any candidate."""
    return {
        "contract": CONSUMPTION_CONTRACT_V2,
        "ticker": ticker,
        "claim_id": str(match.get("claim_id") or ""),
        "alpha_id": None,
        "policies": {"attribution": COMPANY_ATTRIBUTION_POLICY_VERSION},
        "attribution": resolve_name_attribution(match, ticker),
    }


def apply_alpha_evidence_consumption(
    alpha_matches_payload: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]] | None,
    sources: Sequence[Mapping[str, Any]] | None,
    *,
    ticker: str,
    contract: Any,
    ledger: StanceLedgerIndex | None = None,
    taxonomy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Recompute and attach the block of every committed match, in place; returns the run-level summary.

    Always recomputes from the current inputs (records, sources, ledger) and replaces any earlier block, so a re-evaluation
    after the source verification changed can never reuse a stale block; applying twice gives the same payload."""
    if not _is_supported_contract(contract):
        raise EvidenceConsumptionError(REASON_ILLEGAL_CONTRACT_VERSION, str(contract)[:60])
    ticker_key = str(ticker or "").strip().upper()
    if not ticker_key:
        raise EvidenceConsumptionError(REASON_INPUT_INVALID, "ticker")
    if not isinstance(alpha_matches_payload, dict) or not isinstance(alpha_matches_payload.get("matches"), list):
        raise EvidenceConsumptionError(REASON_INPUT_INVALID, "alpha_matches")
    payload_ticker = str(alpha_matches_payload.get("ticker") or "").strip().upper()
    if payload_ticker and payload_ticker != ticker_key:
        raise EvidenceConsumptionError(REASON_TICKER_MISMATCH, "alpha_matches payload")
    taxonomy = _taxonomy(taxonomy)
    records_by_id = {str(r.get("claim_id")): r for r in records or () if isinstance(r, Mapping) and r.get("claim_id")}

    counters: dict[str, Counter] = {k: Counter() for k in ("stance_state", "stance_category", "stance_reason", "admission", "excluded_label", "attribution", "relevance", "scope_basis")}
    scope_applies = scope_changed = scope_still_negated = 0
    ticker_specific = 0
    pairs = 0
    unmatched_with_attribution = 0
    lexical_zero = 0
    for match in alpha_matches_payload["matches"]:
        if not isinstance(match, dict):
            continue
        _strip_blocks(match)
        record_ticker = str(match.get("ticker") or "").strip().upper()
        if record_ticker and record_ticker != ticker_key:
            raise EvidenceConsumptionError(REASON_TICKER_MISMATCH, str(match.get("claim_id"))[:80])
        if match.get("match_status") != "matched":
            if match.get("claim_id"):
                match[CONSUMPTION_BLOCK_KEY] = build_attribution_only_block(match, ticker_key)
                unmatched_with_attribution += 1
            continue
        alpha_id = str(match.get("matched_alpha") or "")
        candidate = matched_candidate(match)
        if not alpha_id or candidate is None or not match.get("claim_id"):
            raise EvidenceConsumptionError(REASON_CANDIDATE_MISSING, str(match.get("claim_id"))[:80])
        block = build_block(
            match, candidate, alpha_id, ticker_key,
            record=records_by_id.get(str(match.get("claim_id"))), sources=sources, taxonomy=taxonomy, ledger=ledger,
        )
        candidate[CONSUMPTION_BLOCK_KEY] = block
        pairs += 1
        stance = block["stance"]
        counters["stance_state"][stance["state"]] += 1
        if stance["state"] == STANCE_UNJUDGED:
            counters["stance_category"][stance["unjudged_category"]] += 1
            counters["stance_reason"][stance["unjudged_reason"]] += 1
        counters["admission"]["admitted" if block["positive_admission"]["admitted"] else "excluded"] += 1
        if not block["positive_admission"]["admitted"]:
            counters["excluded_label"][block["positive_admission"]["label"]] += 1
        counters["attribution"][block["attribution"]["category"]] += 1
        ticker_specific += 1 if block["attribution"]["ticker_specific"] else 0
        counters["relevance"][block["relevance"]["weight_authority"]] += 1
        lexical_zero += 1 if block["relevance"]["lexical_baseline"] == 0.0 else 0
        scope = block["statement_scope"]
        if scope["applies"]:
            scope_applies += 1
            scope_changed += 1 if scope["changed"] else 0
            scope_still_negated += 1 if scope["governing_negation"] else 0
            for basis in sorted({item["basis"] for item in scope["removed"]}):
                counters["scope_basis"][basis] += 1
    alpha_matches_payload[PAYLOAD_CONTRACT_KEY] = CONSUMPTION_CONTRACT_V2
    return {
        "contract": CONSUMPTION_CONTRACT_V2,
        "policies": dict(POLICY_VERSIONS),
        "ticker": ticker_key,
        "matched_pairs": pairs,
        "stance": {
            "model_judged": counters["stance_state"][STANCE_MODEL_JUDGED],
            "unjudged": counters["stance_state"][STANCE_UNJUDGED],
            "unjudged_by_category": dict(sorted(counters["stance_category"].items())),
            "unjudged_by_reason": dict(sorted(counters["stance_reason"].items())),
        },
        "positive_admission": {
            "admitted": counters["admission"]["admitted"],
            "excluded": counters["admission"]["excluded"],
            "excluded_by_label": dict(sorted(counters["excluded_label"].items())),
            "reason_code": REASON_STANCE_MODEL_NOT_SUPPORTING,
        },
        "attribution": {"target_name_present": ticker_specific, "by_category": dict(sorted(counters["attribution"].items())),
                        "unmatched_claims_with_attribution": unmatched_with_attribution,
                        "subject_determined": False, "target_by_source_object": "DISABLED"},
        "relevance": {"model_weights": 0, "lexical_zero_pairs": lexical_zero, "by_authority": dict(sorted(counters["relevance"].items()))},
        "statement_scope": {"policy": STATEMENT_SCOPE_POLICY_VERSION, "text_rule_negated_pairs": scope_applies,
                            "negation_not_governing": scope_applies - scope_still_negated, "negation_still_governing": scope_still_negated,
                            "effective_fields_changed": scope_changed, "pairs_by_removed_basis": dict(sorted(counters["scope_basis"].items()))},
        "ledger": {
            **ledger_description(ledger),
            "declared_sha256": ledger.declared_sha256 if ledger is not None else None,
            "accepted_stance_batches": ledger.accepted_batches if ledger is not None else 0,
            "stance_pairs": len(ledger.pairs) if ledger is not None else 0,
        },
    }


def strip_alpha_evidence_consumption(alpha_matches_payload: Any) -> bool:
    """Rollback: remove every consumption block and the payload marker, in place; ``True`` if anything was removed.

    The contract only ADDS keys (it rewrites none), so stripping restores the payload that existed before it was applied --
    byte-identical once serialised again. The Week 3 pipeline calls this for a run whose metadata no longer names the
    contract, so removing the metadata key is a complete rollback."""
    if not isinstance(alpha_matches_payload, dict):
        return False
    removed = alpha_matches_payload.pop(PAYLOAD_CONTRACT_KEY, None) is not None
    for match in alpha_matches_payload.get("matches") or ():
        if not isinstance(match, dict):
            continue
        if CONSUMPTION_BLOCK_KEY in match or any(
            isinstance(c, dict) and CONSUMPTION_BLOCK_KEY in c for pool in _CANDIDATE_POOLS for c in match.get(pool) or ()
        ):
            removed = True
        _strip_blocks(match)
    return removed


# ---------------------------------------------------------------------------
# Reading and validating a block (the functions every gate calls)
# ---------------------------------------------------------------------------


def _is_supported_contract(value: Any) -> bool:
    """Exact string match only: a JSON value of any other type (a list, a number, ``true``) is an illegal version, never a
    ``TypeError`` from a set lookup that a caller could mistake for an unrelated failure."""
    return isinstance(value, str) and value in SUPPORTED_CONTRACTS


def validate_block_identity(block: Mapping[str, Any], *, claim_id: str, alpha_id: str | None, ticker: str | None) -> None:
    """Contract version, target ticker and (claim, Alpha) pair of a block -- all a compact pass-through copy can be checked
    for. ``alpha_id=None`` skips the Alpha comparison (a pass-through member does not know which Alpha it was gathered for;
    an attribution-only block has none)."""
    if not _is_supported_contract(block.get("contract")):
        raise EvidenceConsumptionError(REASON_ILLEGAL_CONTRACT_VERSION, str(block.get("contract"))[:60])
    if ticker is not None and str(block.get("ticker") or "").upper() != str(ticker).strip().upper():
        raise EvidenceConsumptionError(REASON_TICKER_MISMATCH, claim_id[:80])
    if str(block.get("claim_id") or "") != str(claim_id):
        raise EvidenceConsumptionError(REASON_PAIR_MISMATCH, claim_id[:80])
    if alpha_id is not None and str(block.get("alpha_id") or "") != str(alpha_id):
        raise EvidenceConsumptionError(REASON_PAIR_MISMATCH, claim_id[:80])


def validate_block_for_match(match: Mapping[str, Any], *, ticker: str | None = None) -> dict[str, Any] | None:
    """Full record-level validation of the matched candidate's block; ``None`` when the record has no block (legacy).

    Checks the contract version, the target ticker, that the block belongs to this claim and this matched Alpha, that the
    inputs it was computed from still equal the record's current fields (a stale block fails), and that the stored exclusion
    decision is the one the stored stance state implies."""
    block = block_for_match(match)
    if block is None:
        return None
    alpha_id = str(match.get("matched_alpha") or "")
    expected_ticker = str(ticker or match.get("ticker") or "").strip().upper()
    validate_block_identity(block, claim_id=str(match.get("claim_id") or ""), alpha_id=alpha_id, ticker=expected_ticker or None)
    if match.get("match_status") != "matched":
        raise EvidenceConsumptionError(REASON_PAIR_MISMATCH, "block on an uncommitted match")
    candidate = matched_candidate(match) or {}
    block_ticker = expected_ticker or str(block.get("ticker") or "")
    binding, stance, admission, attribution = (block.get(key) for key in ("binding", "stance", "positive_admission", "attribution"))
    claim_label = str(match.get("claim_id"))[:80]
    if not isinstance(binding, Mapping):
        raise EvidenceConsumptionError(REASON_BINDING_STALE, claim_label)
    if canonical_sha256(binding_inputs(match, candidate, alpha_id, block_ticker)) != binding.get("input_sha256"):
        raise EvidenceConsumptionError(REASON_BINDING_STALE, claim_label)
    # the stored decisions must be the ones their stored inputs imply: a block whose parts were edited separately is invalid
    if not isinstance(stance, Mapping) or not isinstance(admission, Mapping) or positive_admission_for(stance) != admission:
        raise EvidenceConsumptionError(REASON_DECISION_INCONSISTENT, claim_label)
    if not isinstance(attribution, Mapping) or attribution != resolve_name_attribution(match, block_ticker):
        raise EvidenceConsumptionError(REASON_DECISION_INCONSISTENT, claim_label)
    if block.get("statement_scope") != statement_scope_for_match(match, candidate, alpha_id, model_supports=model_supports_anchor(stance)):
        raise EvidenceConsumptionError(REASON_DECISION_INCONSISTENT, claim_label)
    return block


def effective_text_rule(match: Mapping[str, Any], alpha_id: str) -> dict[str, Any] | None:
    """The text-rule fields the positive gates and the scorer read for ``alpha_id``: the validated block's
    ``statement_scope.effective`` under the contract, ``None`` for a legacy record (the caller then reads the stored fields).
    Raises ``EvidenceConsumptionError`` for an invalid block, never falls back."""
    stray = _stray_block_alpha(match)
    if stray is not None:
        raise EvidenceConsumptionError(REASON_PAIR_MISMATCH, f"block of {stray} on a record matched to {match.get('matched_alpha')}")
    if block_for_match(match) is None or str(match.get("matched_alpha") or "") != alpha_id:
        return None
    block = validate_block_for_match(match)
    effective = (block or {}).get("statement_scope", {}).get("effective")
    return dict(effective) if isinstance(effective, Mapping) else None


def positive_admission_exclusion(match: Mapping[str, Any], alpha_id: str) -> dict[str, Any] | None:
    """THE shared judgement of R-1: ``None`` when the claim is not excluded from ``alpha_id``'s positive pool (also for every
    legacy record), else ``{"reason_code", "label"}``. Raises ``EvidenceConsumptionError`` for an invalid block."""
    stray = _stray_block_alpha(match)
    if stray is not None:
        raise EvidenceConsumptionError(REASON_PAIR_MISMATCH, f"block of {stray} on a record matched to {match.get('matched_alpha')}")
    block = block_for_match(match)
    if block is None:
        return None
    if str(match.get("matched_alpha") or "") != alpha_id:
        return None  # a block belongs to the matched Alpha only; it can never exclude the claim from another Alpha
    validate_block_for_match(match)
    admission = block["positive_admission"]
    if admission.get("admitted"):
        return None
    return {"reason_code": admission["reason_code"], "label": admission.get("label")}


def attribution_decision_for_record(record: Mapping[str, Any], ticker: str | None) -> bool | None:
    """``ticker_specific`` from the consumption block, or ``None`` when the record carries none (legacy path).

    ``record`` is either a match record (block inside its matched candidate) or a compact pass-through member (``consumption``
    key). The block's contract, target ticker and pair are validated; a mismatch raises instead of falling back."""
    claim_id = str(record.get("claim_id") or "")
    top_level = record.get(CONSUMPTION_BLOCK_KEY)
    if isinstance(top_level, Mapping):
        # a pass-through member (conflict side) or the attribution-only block of an unmatched match record
        validate_block_identity(top_level, claim_id=claim_id, alpha_id=None, ticker=ticker)
        attribution = top_level.get("attribution")
        if not isinstance(attribution, Mapping) or not isinstance(attribution.get("ticker_specific"), bool):
            raise EvidenceConsumptionError(REASON_DECISION_INCONSISTENT, claim_id[:80])
        if "candidate_scores" in record:  # a match record: the name decision must still describe THIS text
            expected = hashlib.sha256(attribution_text(record).encode("utf-8")).hexdigest()
            if attribution.get("text_sha256") != expected:
                raise EvidenceConsumptionError(REASON_BINDING_STALE, claim_id[:80])
        return attribution["ticker_specific"]
    stray = _stray_block_alpha(record) if "candidate_scores" in record else None
    if stray is not None:
        raise EvidenceConsumptionError(REASON_PAIR_MISMATCH, f"block of {stray} on a record matched to {record.get('matched_alpha')}")
    if record.get("match_status") != "matched":
        return None
    block = validate_block_for_match(record, ticker=ticker)
    if block is None:
        return None
    specific = block["attribution"].get("ticker_specific")  # a Mapping (validated), built by resolve_name_attribution
    if not isinstance(specific, bool):
        raise EvidenceConsumptionError(REASON_DECISION_INCONSISTENT, claim_id[:80])
    return specific


def compact_block(block: Mapping[str, Any]) -> dict[str, Any]:
    """The part of a block the conflict side's member dictionaries carry: identity plus the attribution decision."""
    return {
        "contract": block.get("contract"),
        "ticker": block.get("ticker"),
        "claim_id": block.get("claim_id"),
        "alpha_id": block.get("alpha_id"),
        "attribution": dict(block.get("attribution") or {}),
    }


def verify_payload(
    alpha_matches_payload: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]] | None,
    sources: Sequence[Mapping[str, Any]] | None,
    *,
    ticker: str,
    ledger: StanceLedgerIndex | None = None,
    taxonomy: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Per committed match: ``CURRENT`` (block equals a fresh recomputation from today's records, sources and ledger),
    ``STALE`` (it validates against the record but the source state or ledger moved), or ``INVALID:<reason>`` / ``MISSING``.
    Used by the read-only trace; it never writes."""
    ticker_key = str(ticker or "").strip().upper()
    taxonomy = _taxonomy(taxonomy)
    records_by_id = {str(r.get("claim_id")): r for r in records or () if isinstance(r, Mapping) and r.get("claim_id")}
    out = []
    for match in alpha_matches_payload.get("matches") or ():
        if not isinstance(match, Mapping):
            continue
        claim_id = str(match.get("claim_id") or "")
        if match.get("match_status") != "matched":
            if claim_id:
                try:
                    attribution_decision_for_record(match, ticker_key)
                    present = isinstance(match.get(CONSUMPTION_BLOCK_KEY), Mapping)
                    fresh_only = build_attribution_only_block(match, ticker_key) if present else None
                    state = "MISSING" if not present else ("CURRENT" if fresh_only == match.get(CONSUMPTION_BLOCK_KEY) else "STALE")
                except EvidenceConsumptionError as exc:
                    state = f"INVALID:{exc.reason_code}"
                out.append({"claim_id": claim_id, "alpha_id": None, "state": state})
            continue
        alpha_id = str(match.get("matched_alpha") or "")
        block = block_for_match(match)
        if block is None:
            out.append({"claim_id": claim_id, "alpha_id": alpha_id, "state": "MISSING"})
            continue
        try:
            validate_block_for_match(match, ticker=ticker_key)
        except EvidenceConsumptionError as exc:
            out.append({"claim_id": claim_id, "alpha_id": alpha_id, "state": f"INVALID:{exc.reason_code}"})
            continue
        candidate = matched_candidate(match) or {}
        fresh = build_block(match, candidate, alpha_id, ticker_key, record=records_by_id.get(claim_id), sources=sources, taxonomy=taxonomy, ledger=ledger)
        stale = fresh != block
        out.append({"claim_id": claim_id, "alpha_id": alpha_id, "state": "STALE" if stale else "CURRENT"})
    return out


__all__ = [
    "CONSUMPTION_BLOCK_KEY",
    "CONSUMPTION_CONTRACT_V2",
    "CONSUMPTION_METADATA_KEY",
    "CONSUMPTION_RECOMPUTE_EXECUTION_TYPE",
    "EvidenceConsumptionError",
    "LEDGER_BINDING_METADATA_KEY",
    "LEDGER_BINDING_OWN_RUN",
    "LEDGER_BINDING_SOURCE_DECLARED",
    "PAYLOAD_CONTRACT_KEY",
    "POLICY_VERSIONS",
    "R1_EXCLUDING_STANCES",
    "REASON_STANCE_MODEL_NOT_SUPPORTING",
    "StanceLedgerIndex",
    "apply_alpha_evidence_consumption",
    "attribution_decision_for_record",
    "block_for_match",
    "build_attribution_only_block",
    "build_block",
    "canonical_sha256",
    "compact_block",
    "ledger_description",
    "load_stance_ledger",
    "matched_candidate",
    "positive_admission_exclusion",
    "positive_admission_for",
    "resolve_stance_ledger",
    "stance_judgement",
    "strip_alpha_evidence_consumption",
    "validate_block_for_match",
    "validate_block_identity",
    "verify_payload",
]
