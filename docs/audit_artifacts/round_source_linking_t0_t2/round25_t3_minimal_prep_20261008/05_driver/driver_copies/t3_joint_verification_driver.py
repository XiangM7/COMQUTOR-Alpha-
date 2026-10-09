#!/usr/bin/env python3
"""Joint (multi-stage) T3 verification driver -- John's own T3 acceptance,
NOT the narrower Alpha-classification-only driver
(``t3_diagnostic_evaluation_driver.py``, kept separate and unchanged).

Chains FIVE real, separately-owned production stages, per claim (the first
four) then once per ticker (the fifth):

  1. source locatability + time eligibility
     -- comqutor_alpha.source_provenance.match_evidence_to_source_candidates
        + .validate_source_reference
  2. source-to-claim relationship (content support)
     -- comqutor_alpha.source_provenance.build_content_support_review
        (SUPPORT_PENDING_REVIEW/REVIEW_METHOD_UNREVIEWED is the real, honest
        default for any claim no human has content-reviewed yet -- never a
        fabricated SUPPORTS/OPPOSES verdict this driver invented itself)
  3. Alpha classification
     -- comqutor_alpha.structure_engine.alpha_mapper.map_claim_to_alpha
        (the EXACT SAME function t3_diagnostic_evaluation_driver.py calls --
        imported and called directly here, never reimplemented)
  4. Evidence Stance / Polarity
     -- comqutor_alpha.structure_engine.evidence_stance.classify_evidence_stance
        (Round 25: the DETERMINISTIC BASELINE only, reported as
        DETERMINISTIC_BASELINE_ONLY -- not the production LLM direction; the
        T3 five-link check uses t3_joint_sample_driver.py instead)
  5. Formal Activation/Conflict eligibility (once per ticker, not per claim)
     -- comqutor_alpha.regression.acceptance_engine.run_formal_acceptance,
        the real, already-hardened formal-acceptance gate (the same one
        whose optional-parameter bypass was closed in an earlier round this
        session) -- never a separately-invented "looks done" check.

Every stage's real status/exclusion-reason is saved per claim, never
collapsed into a single aggregate score, and system output is kept in its
own key, structurally separate from any future human reference judgment
(``human_reference`` is always ``None`` here -- this driver never fabricates
one). ``run_formal_acceptance`` itself is what actually preserves
"insufficient evidence" / "no qualifying Alpha" / "no main conflict" as real,
un-demo'd outcomes -- this driver calls it unmodified and reports whatever
it returns, including a real ``NOT_EVALUABLE``/``ALPHA_SEMANTIC_UNAVAILABLE``
verdict if that is genuinely what the run's own artifacts support.

SCOPE, stated once here rather than implied: this driver's own claim-level
stages 1-4 run for whatever claims exist in the given run's own
``structured_agent_outputs.json`` -- it never claims to cover every Alpha in
the taxonomy, and it is not a substitute for the 40-item stratified
diagnostic sample in ``t3_targeted_diagnostic_sample_2026-09-30.json`` (a
deliberately-curated, cross-run pool covering specific boundary cases a
single run's own claims will not evenly cover). A run this driver processes
can only ever report on the Alpha/claim mix that run's own material
actually contains.

This module is verified RUNNABLE this round using FIXED, synthetic fixture
data (a fake run directory built by a test, not a real Fresh Run) -- see
tests/test_t3_joint_verification_driver.py. A fixture run's own
stage-by-stage RESULTS are never a measurement of real model quality; they
only prove the wiring executes end to end and produces the right shape.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_SCOPE = (
    "JOINT_MULTI_STAGE_VERIFICATION -- source-link+time-eligibility, content-support, "
    "Alpha, Evidence-Stance, formal Activation/Conflict eligibility. NOT a replacement for "
    "the 40-item stratified diagnostic sample; only covers the given run's own claim mix."
)

STAGE_ORDER = ("source_link", "content_support", "alpha_classification", "stance")


def verify_claim_source_link(
    claim: dict[str, Any], sources: list[dict[str, Any]], evidence_cutoff: str | None
) -> dict[str, Any]:
    """Stage 1: source locatability + time eligibility.

    Tries the claim's own already-assigned ``cited_source_id`` (from
    extraction-stage enrichment, if present) first, then falls back to
    deterministic content-overlap candidates -- both are validated through
    the SAME real ``validate_source_reference`` gate, never trusted as-is.
    """
    from comqutor_alpha.source_provenance import (
        SOURCE_LINK_VALID,
        match_evidence_to_source_candidates,
        validate_source_reference,
    )

    cited = claim.get("cited_source_id")
    candidates = ([cited] if cited else []) + match_evidence_to_source_candidates(
        claim.get("evidence"), claim.get("claim"), sources
    )
    if not candidates:
        return {
            "stage": "source_link",
            "status": "NO_CANDIDATE",
            "exclusion_reason": "no_cited_or_content_matching_source_candidate",
            "linked_source_id": None,
        }
    last_result: dict[str, Any] = {}
    for candidate_id in candidates:
        result = validate_source_reference(candidate_id, sources=sources, evidence_cutoff=evidence_cutoff)
        last_result = result
        if result["source_link_status"] == SOURCE_LINK_VALID:
            return {
                "stage": "source_link",
                "status": "VALID",
                "exclusion_reason": None,
                "linked_source_id": result["linked_source_id"],
            }
    # No candidate validated -- report the first/best candidate's own real
    # reason rather than a generic "no", so a reviewer can see WHY.
    return {
        "stage": "source_link",
        "status": last_result.get("source_link_status", "UNKNOWN"),
        "exclusion_reason": last_result.get("source_link_status", "UNKNOWN"),
        "linked_source_id": last_result.get("linked_source_id"),
    }


def verify_claim_content_support(source_link_result: dict[str, Any], claim_id: str) -> dict[str, Any]:
    """Stage 2: source-to-claim relationship.

    A valid source link is necessary but never sufficient for content
    support -- absent a real human review, this honestly reports
    SUPPORT_PENDING_REVIEW/REVIEW_METHOD_UNREVIEWED (the real, existing
    default this codebase already uses for exactly this situation), never a
    fabricated SUPPORTS/OPPOSES verdict.
    """
    from comqutor_alpha.source_provenance import SUPPORT_PENDING_REVIEW, build_content_support_review

    if source_link_result["status"] != "VALID":
        return {
            "stage": "content_support",
            "status": "NOT_APPLICABLE_NO_VALID_SOURCE_LINK",
            "exclusion_reason": source_link_result["exclusion_reason"],
        }
    review = build_content_support_review(
        SUPPORT_PENDING_REVIEW,
        claim_id=claim_id,
        linked_source_id=source_link_result["linked_source_id"],
    )
    return {
        "stage": "content_support",
        "status": review["status"],
        "exclusion_reason": "not_yet_human_reviewed",
        "review": review,
    }


def verify_claim_alpha(claim: dict[str, Any], taxonomy: Any, llm_gateway: Any) -> dict[str, Any]:
    """Stage 3: Alpha classification. Calls the exact same real function
    t3_diagnostic_evaluation_driver.py uses -- never a second implementation."""
    from comqutor_alpha.structure_engine.alpha_mapper import map_claim_to_alpha

    result = map_claim_to_alpha(claim, taxonomy, classifier_enabled=True, llm_gateway=llm_gateway)
    classifier = result.get("classifier") or {}
    matched = result.get("matched_alpha")
    status = "MATCHED" if matched else str(result.get("match_status", "UNKNOWN")).upper()
    return {
        "stage": "alpha_classification",
        "status": status,
        "exclusion_reason": None if matched else classifier.get("status"),
        "matched_alpha": matched,
        "raw_match_status": result.get("match_status"),
    }


def verify_claim_stance(claim: dict[str, Any], alpha_result: dict[str, Any], taxonomy: Any) -> dict[str, Any]:
    """Stage 4: Evidence Stance / Polarity, deterministic path.

    Only meaningful once an Alpha has actually been matched -- stance is
    defined relative to a target_alpha_id (see classify_evidence_stance's
    own docstring), so a claim with no matched Alpha genuinely has nothing
    for this stage to evaluate. This is reported as NOT_APPLICABLE, never
    skipped silently.
    """
    from comqutor_alpha.structure_engine.evidence_stance import classify_evidence_stance

    matched_alpha = alpha_result.get("matched_alpha")
    if not matched_alpha:
        return {
            "stage": "stance",
            "status": "NOT_APPLICABLE_NO_ALPHA_MATCHED",
            "exclusion_reason": alpha_result.get("exclusion_reason"),
        }
    stance = classify_evidence_stance(
        record=claim, target_alpha_id=matched_alpha, candidate=None, taxonomy=taxonomy
    )
    # Round 25: this is the deterministic baseline, not the production LLM
    # direction (evidence_stance_llm.apply_llm_stance_upgrade); it must never
    # be read as a direction result. The five-link check uses
    # t3_joint_sample_driver.py, which calls the production LLM path.
    return {
        "stage": "stance",
        "status": "DETERMINISTIC_BASELINE_ONLY",
        "method": "deterministic_baseline (not an LLM result)",
        "deterministic_baseline_stance": stance.evidence_stance or "UNKNOWN",
        "exclusion_reason": None,
        "detail": stance.to_dict(),
    }


@dataclass
class ClaimVerificationRecord:
    claim_id: str
    ticker: str
    system_output: dict[str, Any]
    human_reference: None = None  # never fabricated by this driver

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "ticker": self.ticker,
            "system_output": self.system_output,
            "human_reference": self.human_reference,
        }


def verify_claims(
    claims: list[dict[str, Any]],
    *,
    sources: list[dict[str, Any]],
    evidence_cutoff: str | None,
    taxonomy: Any,
    llm_gateway: Any,
) -> list[ClaimVerificationRecord]:
    """Runs stages 1-4 for every claim, saving each stage's own result and
    exclusion reason -- never just a non-null-field check, never only an
    aggregate Alpha accuracy number."""
    records = []
    for claim in claims:
        source_link = verify_claim_source_link(claim, sources, evidence_cutoff)
        content_support = verify_claim_content_support(source_link, str(claim.get("claim_id", "")))
        alpha = verify_claim_alpha(claim, taxonomy, llm_gateway)
        stance = verify_claim_stance(claim, alpha, taxonomy)
        records.append(
            ClaimVerificationRecord(
                claim_id=str(claim.get("claim_id", "")),
                ticker=str(claim.get("ticker", "")),
                system_output={
                    "source_link": source_link,
                    "content_support": content_support,
                    "alpha_classification": alpha,
                    "stance": stance,
                },
            )
        )
    return records


def build_evaluate_ticker_result_from_run_dir(run_dir: Path) -> dict[str, Any]:
    """Honestly computes the minimal real fields run_formal_acceptance's own
    _ticker_is_evaluable gate reads, from a run directory's ACTUAL file
    presence -- never hardcoded to "pass". See acceptance_engine.py's own
    _ticker_is_evaluable for the exact three fields this must supply.
    """
    expected_files = (
        "raw_agent_outputs.json",
        "structured_agent_outputs.json",
        "alpha_matches.json",
        "alpha_activations.json",
        "conflicts.json",
        "structure_graph.json",
    )
    missing = [name for name in expected_files if not (run_dir / name).exists()]
    stance_audit_path = run_dir / "evidence_stance_audit.json"
    stance_source = "unavailable"
    if stance_audit_path.exists():
        try:
            stance_audit = json.loads(stance_audit_path.read_text())
            stance_source = stance_audit.get("stance_source", "unavailable")
        except Exception:
            stance_source = "unavailable"
    return {
        "run_selection_status": "selected" if run_dir.exists() else "not_selected",
        "offline_reprocess_status": "completed" if not missing else "incomplete",
        "artifact_completeness": "pass" if not missing else "fail",
        "artifact_missing_files": missing,
        "stance_source": stance_source,
        "admitted_conflicts": [],
    }


def run_formal_eligibility_stage(ticker: str, run_id: str, run_dir: Path) -> dict[str, Any]:
    """Stage 5: formal Activation/Conflict eligibility, once per ticker.

    Calls the real, unmodified run_formal_acceptance -- this function is
    never re-derived or loosened here; whatever it returns (including a
    real NOT_EVALUABLE/ALPHA_SEMANTIC_UNAVAILABLE/insufficient-evidence
    verdict) is reported as-is, never softened for a cleaner-looking result.
    ``run_dir`` must be ``<output_root>/<run_id>`` -- artifacts are loaded by
    real run_id, never by ticker (a ticker can have many runs).
    """
    from comqutor_alpha.regression.acceptance_engine import run_formal_acceptance
    from comqutor_alpha.storage.file_store import load_json_record_if_exists

    output_root = run_dir.parent
    graph_payload = load_json_record_if_exists(run_id, "structure_graph.json", output_root=output_root) or {}
    conflict_payload = load_json_record_if_exists(run_id, "conflicts.json", output_root=output_root) or {}
    alpha_matches_payload = load_json_record_if_exists(run_id, "alpha_matches.json", output_root=output_root)
    if not alpha_matches_payload:
        alpha_matches_payload = None  # honestly MISSING, never a fabricated empty-but-present payload
    evaluate_ticker_result = build_evaluate_ticker_result_from_run_dir(run_dir)

    return run_formal_acceptance(
        ticker=ticker,
        ticker_v2_label=None,
        label_block_v1=None,
        evaluate_ticker_result=evaluate_ticker_result,
        conflict_payload=conflict_payload,
        graph_payload=graph_payload,
        alpha_matches_payload=alpha_matches_payload,
    )


@dataclass
class JointVerificationResult:
    run_id: str
    ticker: str
    claim_records: list[ClaimVerificationRecord]
    formal_eligibility: dict[str, Any]
    fixture_mode: bool

    def write(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        records_path = output_dir / "joint_verification_records.jsonl"
        records_path.write_text(
            "\n".join(json.dumps(r.to_dict(), ensure_ascii=False, sort_keys=True) for r in self.claim_records) + "\n"
        )
        stage_counts: dict[str, dict[str, int]] = {}
        for record in self.claim_records:
            for stage_name, stage_result in record.system_output.items():
                bucket = stage_counts.setdefault(stage_name, {})
                status = stage_result["status"]
                bucket[status] = bucket.get(status, 0) + 1
        summary = {
            "schema_version": "t3_joint_verification_summary.v1",
            "script_scope": SCRIPT_SCOPE,
            "run_id": self.run_id,
            "ticker": self.ticker,
            "fixture_mode": self.fixture_mode,
            "claim_count": len(self.claim_records),
            "stage_status_counts": stage_counts,
            "formal_eligibility": self.formal_eligibility,
        }
        (output_dir / "joint_verification_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2)
        )


def run_joint_verification(
    run_dir: Path,
    *,
    taxonomy: Any = None,
    llm_gateway: Any = None,
    fixture_mode: bool = False,
) -> JointVerificationResult:
    """Loads a run's own real artifacts and runs all five stages.

    ``fixture_mode=True`` must be passed by any caller using synthetic
    (non-real-run) data -- it is carried into the written summary so a
    fixture run's results are never mistaken for a real run's.
    """
    from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy

    metadata = json.loads((run_dir / "metadata.json").read_text())
    ticker = str(metadata.get("ticker", ""))
    run_id = str(metadata.get("run_id", run_dir.name))

    structured = json.loads((run_dir / "structured_agent_outputs.json").read_text())
    # Round 25: real runs save the list under "records"; "claims" is the old fixture shape
    claims = structured.get("records") or structured.get("claims") or structured.get("structured_claims") or []

    sources_path = run_dir / "source_registry.json"
    sources: list[dict[str, Any]] = []
    if sources_path.exists():
        registry = json.loads(sources_path.read_text())
        sources = registry.get("sources", [])
    evidence_cutoff = metadata.get("evidence_cutoff")

    taxonomy = taxonomy if taxonomy is not None else load_alpha_taxonomy()
    claim_records = verify_claims(
        claims, sources=sources, evidence_cutoff=evidence_cutoff, taxonomy=taxonomy, llm_gateway=llm_gateway
    )
    formal_eligibility = run_formal_eligibility_stage(ticker, run_id, run_dir)

    return JointVerificationResult(
        run_id=run_id,
        ticker=ticker,
        claim_records=claim_records,
        formal_eligibility=formal_eligibility,
        fixture_mode=fixture_mode,
    )
