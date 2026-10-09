#!/usr/bin/env python3
"""ALPHA CLASSIFICATION DIAGNOSTIC DRIVER -- NOT John's full T3 joint verification.

Renamed/re-labeled explicitly (2026-09-30, fourth follow-up round) after
the prior round's own framing risked being read as "the T3 script." This
script covers exactly ONE of T3's real stages: Alpha classification. It
does NOT cover, and its own accuracy/PASS output must never be read as
covering: source locatability/time eligibility, the source-to-claim
relationship, Evidence-Stance/Polarity, or downstream Activation/Conflict
eligibility -- each is a separate real production stage with its own call
path (see ``t3_model_config_comparison_2026-09-30.md``), and each is
explicitly listed as ``NOT_IMPLEMENTED_THIS_ROUND`` in ``STEPS_COVERED``
below, not silently folded into an Alpha score. The joint, multi-stage
verification John's own T3 acceptance actually needs is a SEPARATE driver
(``t3_joint_verification_driver.py``, added this round) that chains all
five real stages and is honest about covering only what a given run's own
material actually supports.

Reuses the REAL production Alpha-classification call path -- this script
never reimplements classification/scoring logic of its own. The Alpha step
is exercised through exactly the same functions the live pipeline calls:

  comqutor_alpha.structure_engine.alpha_mapper.map_claim_to_alpha(
      record, taxonomy, classifier_enabled=True, llm_gateway=<real gateway>,
  )

with the gateway built the same way production builds it
(``comqutor_alpha.structure_engine.week2_llm.build_server_week2_llm_gateway``,
reading the same ``COMQUTOR_WEEK2_LLM_*`` environment variables the live
server reads) and a real ``SemanticRuntimeSession`` attached so every call is
recorded through the same ``llm_semantic_calls.jsonl`` / ``SemanticCallRecord``
machinery every real run uses.

SCOPE DISCLOSURE (required by the task sheet, not an oversight): this driver
implements the **Alpha classification** step only. Source-support verification,
claim-fidelity, Evidence-Stance/Polarity, and downstream-eligibility scoring
are each separate real production steps with their own call paths
(see ``t3_model_config_comparison_2026-09-30.md``) and are NOT computed by
this driver. Every report this script writes says so explicitly in its own
``steps_covered`` field, rather than silently implying a broader evaluation
than what actually ran.

Outcome taxonomy (grounded directly in the real, current
``comqutor_alpha.structure_engine.alpha_mapper._classify_alpha_with_llm``
return shape -- see that function for the authoritative source of every
status string referenced below):

  classifier.status            -> outcome_code
  ------------------------------------------------
  "disabled" / "unavailable"   -> UNAVAILABLE          (classifier never actually invoked)
  "provider_timeout"           -> CALL_FAILED          (a real request was attempted and failed)
  "provider_error"             -> CALL_FAILED
  "call_budget_exhausted"      -> CALL_FAILED
  "provider_rate_limited"      -> CALL_FAILED
  "invalid_output"             -> PARSE_FAILED         (a response arrived but failed validation)
  "invalid_alpha_id"           -> PARSE_FAILED
  "input_too_large"            -> PARSE_FAILED
  "llm_none"                   -> NONE                 (the model's own explicit "no Alpha applies")
  "llm_selected" + match_status == "ambiguous"  -> ABSTAINED_AMBIGUOUS (tie-break could not commit)
  "llm_selected" + match_status == "matched"    -> MATCHED
  "llm_selected" + match_status == "no_match"   -> SELECTED_BUT_NOT_MATCHED (see correction below)

CORRECTION (2026-10-01, AI-review comparison round -- supersedes the "HONEST
LIMITATION" paragraph below, which this round found to be factually wrong):
the claim that ``match_status`` is "UNCONDITIONALLY set to matched" whenever
``llm_outcome["outcome"] == "selected"`` does not hold. ``alpha_mapper.py``'s
own Step 7A (alpha-specific invalidation veto) and Step 7A.2 (positive-
requirement gate) -- both pre-existing, deliberate, documented product-level
checks, added in an earlier round than this docstring's own "HONEST
LIMITATION" claim -- can override a valid, in-taxonomy LLM selection back to
``match_status == "no_match"`` post hoc. 5 of the 40 real records in
execution t3live_20261001T014648Z_1fb9c9d5 hit exactly this combination
(confirmed via the real saved call records: ``validated_output == {"decision":
"select", "selected_alpha_id": "A001"}`` for all 5, with
``alpha_specific_invalidation_matched``/``alpha_positive_requirement_
satisfied`` reproduced offline, zero Provider calls, against the real claim
text). Before this round's fix, ``classify_outcome`` had no branch for this
case and silently fell through to ``MATCHED`` despite ``predicted_alpha``
being ``None`` -- a confirmed implementation defect in THIS driver (not in
``alpha_mapper.py``, whose veto/gate behavior is correct and intentional).
It is now its own explicit status, ``SELECTED_BUT_NOT_MATCHED``, distinct
from both ``MATCHED`` and ``NONE``; the classifier's own original selection
and the specific override reason are preserved via the ``map_claim_to_alpha``
result's ``llm_selected_alpha_id``/``alpha_specific_invalidation_override``/
``alpha_positive_requirement_override`` fields, now also persisted onto each
``t3_eval_records.jsonl`` row. This correction changes what this function
returns for any NEW classification; it is not retroactively applied to
t3live_20261001T014648Z_1fb9c9d5's own already-saved, frozen records.

HONEST LIMITATION (ORIGINAL, PARTIALLY SUPERSEDED -- see correction above),
checked directly against the real code this round: under Pure-LLM Alpha
semantic authority (the current production behavior), when
``llm_outcome["outcome"] == "selected"`` the top-level ``match_status`` is
never ``"ambiguous"`` at that point (the deterministic ambiguity computation
is fully superseded by the LLM's own decision) -- this part remains true.
The real classifier response contract itself is also strictly binary
(``decision`` must be exactly ``"select"`` or ``"none"``;
``validate_response`` in ``alpha_mapper.py`` rejects anything else) -- there
is no representable "abstain" response distinct from ``"none"``.
``ABSTAINED_AMBIGUOUS`` is therefore DEAD CODE under the current real
pipeline: it is kept only as a defensive branch (e.g. for a future
``llm_outcome_override`` caller, or if this constraint is ever relaxed) and
is never expected to fire. This driver's honest position, stated once here
rather than implied: the model's explicit ``NONE`` decision IS the closest
real equivalent to "abstention" this pipeline can currently produce, and
CALL_FAILED/PARSE_FAILED (never folded into NONE) cover the cases where the
Provider was reached but no decision was obtained at all. SELECTED_BUT_NOT_
MATCHED (see correction above) covers the third, previously-mislabeled case:
a decision WAS obtained and WAS a valid in-taxonomy selection, but a
post-hoc semantic gate rejected it.

No outcome is ever silently dropped from any denominator -- every sample
this script processes appears exactly once in ``t3_eval_records.jsonl``
regardless of its outcome_code.

A second honest limitation specific to THIS driver (not the pipeline in
general): live mode always calls ``map_claim_to_alpha`` with
``classifier_enabled=True`` and a real, already-verified-non-None gateway
(``_default_gateway_factory`` raises before scoring even starts if the
gateway could not be built) -- so ``UNAVAILABLE`` (which only occurs when
``classifier_enabled`` is False or no gateway/classifier was supplied at
all) can never actually fire from this script's own live path either. It is
kept in the taxonomy for completeness/documentation, not because this
driver can produce it.

Modes
-----
``preflight`` (default): checks samples/material/config/human-review-status/
output-dir/budget WITHOUT constructing any LLM client and WITHOUT importing
any network library -- zero external requests, by construction, not just by
convention. Writes a preflight report; never writes a score.

``live``: actually calls the real Alpha-classification path for each frozen
sample. Requires BOTH ``COMQUTOR_WEEK2_LLM_ENABLED=1`` in the environment
(the same real production gate every live run already requires) AND the
``--i-acknowledge-this-makes-real-provider-calls`` flag on this invocation.
This round never actually runs live mode -- it is implemented and tested
(with a fixed, offline fake gateway) but not executed against a real
Provider.

Usage
-----
  python t3_diagnostic_evaluation_driver.py preflight \\
      --samples-file t3_targeted_diagnostic_sample_2026-09-30.json \\
      --review-form-file t3_human_review_form_2026-09-30.json \\
      --output-dir /tmp/t3_eval_preflight

  python t3_diagnostic_evaluation_driver.py live \\
      --i-acknowledge-this-makes-real-provider-calls \\
      --samples-file t3_targeted_diagnostic_sample_2026-09-30.json \\
      --review-form-file t3_human_review_form_2026-09-30.json \\
      --output-dir outputs/t3_evaluations \\
      --max-actual-requests 60 --max-retries-per-call 1 --score
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]

# -----------------------------------------------------------------------
# Outcome taxonomy (see module docstring for the authoritative mapping)
# -----------------------------------------------------------------------

_UNAVAILABLE_STATUSES = frozenset({"disabled", "unavailable"})
_CALL_FAILED_STATUSES = frozenset(
    {"provider_timeout", "provider_error", "call_budget_exhausted", "provider_rate_limited"}
)
_PARSE_FAILED_STATUSES = frozenset({"invalid_output", "invalid_alpha_id", "input_too_large"})
# 2026-10-01 (v7 limited real-verification round): a confirmed real
# truncation (finish_reason=="length") gets its OWN outcome_code, distinct
# from PARSE_FAILED -- the two share a symptom (no usable validated_output)
# but a different, auditable cause (a format/content defect vs. the output
# cap being reached). Must never be NONE: truncation is not the model
# declining to classify.
_TRUNCATED_STATUSES = frozenset({"output_truncated"})


def classify_outcome(classifier_status: str, match_status: str) -> str:
    """Map a real ``map_claim_to_alpha`` result onto this driver's outcome taxonomy.

    Pure function, no I/O -- kept separate from the call site so the mapping
    itself (the part a reviewer most needs to audit) is trivially unit-testable
    without touching any gateway/session machinery.

    Bug fix (2026-10-01, AI-review comparison round): this function
    previously treated every ``classifier_status == "llm_selected"`` case
    that was not ``match_status == "ambiguous"`` as ``"MATCHED"`` -- this
    silently mislabeled the real, legitimate case where the classifier
    validly selected an Alpha ID (``llm_selected``) but one of
    ``alpha_mapper.py``'s own post-hoc semantic gates (the Step 7A
    alpha-specific invalidation veto, or the Step 7A.2 positive-requirement
    gate -- both already-documented, deliberate product-level checks, not a
    bug in ``alpha_mapper.py`` itself) overrode the match back to
    ``match_status == "no_match"``. That combination produced
    ``outcome_code == "MATCHED"`` with ``predicted_alpha`` actually ``None``
    -- an internally inconsistent, misleading record. 5 of the 40 real
    records in execution t3live_20261001T014648Z_1fb9c9d5 hit exactly this
    case (confirmed via the real saved call records and an offline,
    zero-Provider-call reproduction against the real
    ``alpha_specific_invalidation_matched``/``alpha_positive_requirement_
    satisfied`` functions). This is NOT retroactively applied to that
    execution's own already-saved ``t3_eval_records.jsonl`` (frozen,
    unmodified); it only changes what THIS function returns for any new
    classification going forward.
    """
    if classifier_status in _UNAVAILABLE_STATUSES:
        return "UNAVAILABLE"
    if classifier_status in _CALL_FAILED_STATUSES:
        return "CALL_FAILED"
    if classifier_status in _PARSE_FAILED_STATUSES:
        return "PARSE_FAILED"
    if classifier_status in _TRUNCATED_STATUSES:
        return "TRUNCATED"
    if classifier_status == "llm_none":
        return "NONE"
    if classifier_status == "llm_selected":
        if match_status == "ambiguous":
            return "ABSTAINED_AMBIGUOUS"
        if match_status == "matched":
            return "MATCHED"
        if match_status == "no_match":
            # The classifier selected a real, in-taxonomy Alpha ID, but a
            # post-hoc semantic gate rejected it -- neither a clean MATCHED
            # nor the model's own explicit NONE. Reported as its own status
            # so the original selection (see ``llm_selected_alpha_id`` on
            # the ``map_claim_to_alpha`` result) and the specific override
            # reason are never silently folded into either bucket.
            return "SELECTED_BUT_NOT_MATCHED"
        return "UNEXPECTED_CLASSIFIER_STATUS:" + str(classifier_status) + "+match_status=" + str(match_status)
    return "UNEXPECTED_CLASSIFIER_STATUS:" + str(classifier_status)


SCRIPT_SCOPE = "ALPHA_CLASSIFICATION_DIAGNOSTIC_ONLY -- not John's full T3 joint verification; see t3_joint_verification_driver.py for the multi-stage driver."

STEPS_COVERED = {
    "alpha_classification": "IMPLEMENTED -- reuses comqutor_alpha.structure_engine.alpha_mapper.map_claim_to_alpha with classifier_enabled=True and a real Week2LLMGateway, the exact real production call convention.",
    "source_support_verification": "NOT_IMPLEMENTED_THIS_ROUND -- a separate real step (comqutor_alpha.source_provenance); finding a claim in alpha_matches.json only proves a model output existed, never that it has verified source support.",
    "claim_fidelity": "NOT_IMPLEMENTED_THIS_ROUND",
    "evidence_stance_polarity": "NOT_IMPLEMENTED_THIS_ROUND -- a separate real step (comqutor_alpha.structure_engine.evidence_stance_llm.apply_llm_stance_upgrade).",
    "downstream_eligibility": "NOT_IMPLEMENTED_THIS_ROUND -- a separate real step (comqutor_alpha.structure_engine.claim_quality).",
}


# -----------------------------------------------------------------------
# Freeze / identity helpers
# -----------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip()
    except Exception as exc:  # pragma: no cover -- defensive only
        return f"GIT_COMMAND_FAILED:{exc}"


def build_freeze_identity(samples_path: Path, review_form_path: Path) -> dict[str, Any]:
    """Everything needed to reproduce or audit exactly what a run scored against.

    Computed entirely locally (git + file hashes) -- no network call.
    """
    taxonomy_path = REPO_ROOT / "comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml"
    identity: dict[str, Any] = {
        "samples_file": str(samples_path),
        "samples_file_sha256": _sha256_file(samples_path),
        "review_form_file": str(review_form_path),
        "review_form_file_sha256": _sha256_file(review_form_path),
        "taxonomy_file": "comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml",
        "taxonomy_file_sha256": _sha256_file(taxonomy_path),
        "git_head": _git("rev-parse", "HEAD"),
        "git_dirty_diff_sha256": _sha256_bytes(_git("diff", "HEAD").encode("utf-8")),
        "git_status_porcelain": _git("status", "--porcelain"),
    }
    try:
        from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

        identity["alpha_classifier_prompt_identity_sha256"] = Week2LLMGateway.prompt_identity_sha256(
            "alpha_classifier"
        )
    except Exception as exc:  # pragma: no cover -- defensive only
        identity["alpha_classifier_prompt_identity_sha256"] = f"UNAVAILABLE:{exc}"
    return identity


# -----------------------------------------------------------------------
# Preflight
# -----------------------------------------------------------------------


@dataclass
class PreflightReport:
    execution_id: str
    generated_at: str
    checks: dict[str, Any] = field(default_factory=dict)
    ready_for_live: bool = False
    blocking_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "t3_eval_preflight.v1",
            "script_scope": SCRIPT_SCOPE,
            "execution_id": self.execution_id,
            "generated_at": self.generated_at,
            "checks": self.checks,
            "ready_for_live": self.ready_for_live,
            "blocking_reasons": self.blocking_reasons,
            "note": (
                "This report makes ZERO external requests: it never constructs an LLM "
                "client, never imports a network/provider library, and only reads local "
                "files and environment variables. 'ready_for_live' reflects config/material "
                "completeness only -- it is not a claim that a live call would succeed."
            ),
        }


def run_preflight(
    samples_path: Path,
    review_form_path: Path,
    output_dir: Path,
    max_actual_requests: int,
    max_retries_per_call: int,
) -> PreflightReport:
    execution_id = f"t3preflight_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    report = PreflightReport(execution_id=execution_id, generated_at=datetime.now(timezone.utc).isoformat())
    blocking: list[str] = []

    # 1. Samples file
    try:
        samples_doc = json.loads(samples_path.read_text())
        samples = samples_doc.get("samples", [])
        report.checks["samples_file"] = {
            "path": str(samples_path),
            "status": samples_doc.get("status"),
            "count": len(samples),
            "expected_count": 40,
        }
        if samples_doc.get("status") != "COMPLETE" or len(samples) != 40:
            blocking.append("SAMPLES_NOT_COMPLETE")
        required_fields = {"sample_id", "claim_id", "claim_text", "ticker", "quota_category"}
        missing_field_samples = [
            s.get("sample_id", "<unknown>") for s in samples if not required_fields.issubset(s)
        ]
        report.checks["samples_missing_required_fields"] = missing_field_samples
        if missing_field_samples:
            blocking.append("SAMPLES_MISSING_REQUIRED_FIELDS")
    except Exception as exc:
        report.checks["samples_file"] = {"path": str(samples_path), "error": str(exc)}
        blocking.append("SAMPLES_FILE_UNREADABLE")
        samples = []

    # 2. Source material presence (existence only -- never a claim of
    #    verified source support; see module docstring's scope disclosure).
    material_status = []
    for s in samples:
        # The 15 prod-run-* samples carry an explicit "run_id" field; the 25
        # older gold-* samples (drawn from the historical Gold-set evaluation
        # files, not real production runs directly) do not -- for those,
        # run_id is the first ":"-delimited segment of claim_id, the same
        # convention every claim_id in this codebase already follows
        # (run_id:agent:report_section:claim:N).
        run_id = s.get("run_id") or (str(s.get("claim_id", "")).split(":", 1)[0] or None)
        if not run_id:
            material_status.append({"sample_id": s.get("sample_id"), "material_status": "NO_RUN_ID_RECORDED"})
            continue
        run_dir = REPO_ROOT / "outputs" / "runs" / run_id
        present = {
            name: (run_dir / name).exists()
            for name in ("alpha_matches.json", "raw_agent_outputs.json", "structured_agent_outputs.json")
        }
        material_status.append(
            {
                "sample_id": s.get("sample_id"),
                "run_dir_exists": run_dir.exists(),
                "files_present": present,
                "material_status": "PRESENT" if run_dir.exists() and all(present.values()) else "INCOMPLETE",
            }
        )
    incomplete_material = [m for m in material_status if m["material_status"] != "PRESENT"]
    report.checks["source_material"] = {
        "total": len(material_status),
        "incomplete_count": len(incomplete_material),
        "incomplete_samples": incomplete_material,
    }
    if incomplete_material:
        blocking.append("SOURCE_MATERIAL_INCOMPLETE_FOR_SOME_SAMPLES")

    # 3. Config -- read-only, never constructs a client.
    week2_enabled = os.environ.get("COMQUTOR_WEEK2_LLM_ENABLED") == "1"
    provider = (os.environ.get("COMQUTOR_WEEK2_LLM_PROVIDER") or "").strip()
    model = (os.environ.get("COMQUTOR_WEEK2_LLM_MODEL") or "").strip()
    report.checks["config"] = {
        "COMQUTOR_WEEK2_LLM_ENABLED": week2_enabled,
        "COMQUTOR_WEEK2_LLM_PROVIDER": provider or "UNSET",
        "COMQUTOR_WEEK2_LLM_MODEL": model or "UNSET",
        "note": "Read from os.environ only -- no client constructed, no network touched.",
    }
    if not (week2_enabled and provider and model):
        blocking.append("WEEK2_LLM_CONFIG_INCOMPLETE_OR_DISABLED")

    # 4. Human review status
    try:
        review_doc = json.loads(review_form_path.read_text())
        review_items = review_doc.get("review_items", [])
        judged = [r for r in review_items if r.get("your_judgment") is not None]
        report.checks["human_review"] = {
            "path": str(review_form_path),
            "total_items": len(review_items),
            "judged_count": len(judged),
            "human_review_performed": review_doc.get("human_review_performed"),
            "review_status": review_doc.get("review_status"),
        }
        if not judged:
            report.checks["human_review"]["scoring_will_be"] = "BLOCKED_NO_HUMAN_LABELS"
    except Exception as exc:
        report.checks["human_review"] = {"path": str(review_form_path), "error": str(exc)}
        blocking.append("REVIEW_FORM_UNREADABLE")

    # 5. Output directory
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        probe = output_dir / f".preflight_write_probe_{uuid.uuid4().hex}"
        probe.write_text("ok")
        probe.unlink()
        report.checks["output_dir"] = {"path": str(output_dir), "writable": True}
    except Exception as exc:
        report.checks["output_dir"] = {"path": str(output_dir), "writable": False, "error": str(exc)}
        blocking.append("OUTPUT_DIR_NOT_WRITABLE")

    # 6. Budget parameters -- sanity only, never silently defaulted to "unlimited".
    report.checks["budget"] = {
        "max_actual_requests": max_actual_requests,
        "max_retries_per_call": max_retries_per_call,
    }
    if max_actual_requests <= 0:
        blocking.append("MAX_ACTUAL_REQUESTS_MUST_BE_POSITIVE")
    if max_retries_per_call < 0:
        blocking.append("MAX_RETRIES_MUST_BE_NON_NEGATIVE")

    report.blocking_reasons = blocking
    report.ready_for_live = not blocking
    return report


# -----------------------------------------------------------------------
# Live evaluation
# -----------------------------------------------------------------------


class _BudgetTrackingGateway:
    """Wraps a real Week2LLMGateway to COUNT actual Provider requests.

    Delegates every real method to the wrapped gateway unchanged; only
    counts calls where the Provider was genuinely reached, plus their own
    retries. Deliberately does NOT raise to interrupt a call in flight: the
    real ``map_claim_to_alpha`` -> ``_classify_alpha_with_llm`` call path
    wraps every gateway call in its own broad ``except Exception`` (so it
    can normalize a real Provider failure into an "unavailable" outcome) --
    an exception raised from inside this wrapper would be caught THERE and
    silently relabeled as a fake "provider_error", which is exactly the
    "budget stop mis-recorded as a real failure" conflation the task
    requires never happen. The budget is therefore enforced by the CALLER
    (``run_live_evaluation``) checking ``actual_requests_made`` BEFORE
    starting each new sample, never by interrupting one already in progress.
    """

    def __init__(self, gateway: Any, max_actual_requests: int) -> None:
        self._gateway = gateway
        self.max_actual_requests = max_actual_requests
        self.actual_requests_made = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._gateway, name)

    def budget_remaining(self) -> int:
        return self.max_actual_requests - self.actual_requests_made

    def invoke_json_with_trace(self, task: str, payload: Any, validator: Any) -> Any:
        invocation = self._gateway.invoke_json_with_trace(task, payload, validator)
        # provider_attempt_count already counts the initial attempt + every
        # retry as one Provider-reaching attempt each (see week2_llm.py) --
        # this is the same real number used for retry_count elsewhere, so it
        # is reused here rather than recomputed with different semantics.
        attempts = getattr(invocation, "provider_attempt_count", 0)
        if invocation.provider_status != "budget_exhausted":
            self.actual_requests_made += max(attempts, 1 if invocation.provider_called else 0)
        return invocation


@dataclass
class LiveEvalResult:
    execution_id: str
    records: list[dict[str, Any]]
    stopped_early: bool
    stop_reason: str | None
    actual_requests_made: int
    max_actual_requests: int


def run_live_evaluation(
    samples: list[dict[str, Any]],
    *,
    execution_id: str,
    output_dir: Path,
    max_actual_requests: int,
    max_retries_per_call: int,
    max_output_tokens: int = 200,
    gateway_factory: Any = None,
) -> LiveEvalResult:
    """Runs the real Alpha-classification path for each sample.

    ``max_output_tokens`` (2026-09-30, fifth follow-up round): forwarded to
    the real client constructor via ``build_server_week2_llm_gateway``'s own
    ``max_tokens`` parameter -- confirmed (tests/test_week2_llm.py) to reach
    a real ``ChatOpenAI``/``ChatAnthropic`` instance's own ``max_tokens``
    field, never omitted on the assumption that this task's output "happens
    to be small". Default 200 is generous headroom over the real, fixed
    output shape (``{"decision": ..., "selected_alpha_id": ...}``, well
    under 50 tokens) -- a real, explicit cap, not an unbounded default.

    ``gateway_factory(run_id, output_root) -> (gateway, session)`` defaults to
    the real production construction (``build_server_week2_llm_gateway`` +
    a real ``SemanticRuntimeSession``); tests inject a fixed-response fake
    here instead of a live Provider -- this is a test SEAM, not a parallel
    scoring implementation (the actual classification/outcome-mapping code
    below is identical in both cases).
    """
    from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
    from comqutor_alpha.structure_engine.alpha_mapper import map_claim_to_alpha

    taxonomy = load_alpha_taxonomy()
    run_root = output_dir / execution_id
    run_root.mkdir(parents=True, exist_ok=True)

    if gateway_factory is None:
        def gateway_factory(exec_id: str, out_root: Path) -> tuple[Any, Any]:
            return _default_gateway_factory(exec_id, out_root, max_tokens=max_output_tokens)

    gateway, session = gateway_factory(execution_id, output_dir)
    # Week2LLMGateway.max_retries is a plain instance attribute (never read
    # only at __init__ time) -- overriding it here applies this run's own
    # --max-retries-per-call to every call this gateway makes, without
    # touching the gateway construction/env-reading logic the factory
    # itself (production or fake) already owns.
    gateway.max_retries = max(int(max_retries_per_call), 0)
    tracked_gateway = _BudgetTrackingGateway(gateway, max_actual_requests)

    records: list[dict[str, Any]] = []
    stopped_early = False
    stop_reason: str | None = None

    # Budget is checked once BEFORE each sample, not per individual retry
    # attempt inside a sample's own call -- a single sample's real attempts
    # (bounded by --max-retries-per-call) can therefore push the final
    # actual_requests_made up to max_retries_per_call past the configured
    # ceiling on the very last sample processed. This is an intentional,
    # disclosed simplification (see run summary's own actual_requests_made
    # vs max_actual_requests), never a silent overrun beyond that bound.
    for sample in samples:
        if tracked_gateway.budget_remaining() <= 0:
            stopped_early = True
            stop_reason = (
                f"Reached max_actual_requests={max_actual_requests} before sample "
                f"{sample.get('sample_id')!r}."
            )
            break

        record_input = {
            "claim": sample.get("claim_text", ""),
            "evidence": sample.get("evidence_text", sample.get("claim_text", "")),
            "ticker": sample.get("ticker", ""),
            "factors": [],
            "direction": "unknown",
            "run_id": sample.get("run_id"),
            "claim_id": sample.get("claim_id"),
        }
        result = map_claim_to_alpha(
            record_input,
            taxonomy,
            classifier_enabled=True,
            llm_gateway=tracked_gateway,
        )

        classifier = result.get("classifier") or {}
        outcome_code = classify_outcome(str(classifier.get("status", "")), str(result.get("match_status", "")))
        records.append(
            {
                "sample_id": sample.get("sample_id"),
                "claim_id": sample.get("claim_id"),
                "ticker": sample.get("ticker"),
                "quota_category": sample.get("quota_category"),
                "input": record_input,
                "predicted_alpha": result.get("matched_alpha"),
                "outcome_code": outcome_code,
                "classifier_status_raw": classifier.get("status"),
                "match_status_raw": result.get("match_status"),
                "alpha_match_fallback_reason": result.get("alpha_match_fallback_reason"),
                # Additive (2026-10-01, AI-review comparison round): preserves
                # the classifier's own raw selection and the specific reason
                # it was overridden, for the SELECTED_BUT_NOT_MATCHED case
                # above -- never folded into predicted_alpha=None without a
                # trace of what was actually selected and why.
                "llm_selected_alpha_id": result.get("llm_selected_alpha_id"),
                "alpha_specific_invalidation_override": result.get("alpha_specific_invalidation_override"),
                "alpha_positive_requirement_override": result.get("alpha_positive_requirement_override"),
            }
        )

    # Any sample never attempted because of an early budget stop is recorded
    # explicitly, never just absent from the file.
    attempted_ids = {r["sample_id"] for r in records}
    for sample in samples:
        if sample.get("sample_id") not in attempted_ids:
            records.append(
                {
                    "sample_id": sample.get("sample_id"),
                    "claim_id": sample.get("claim_id"),
                    "ticker": sample.get("ticker"),
                    "quota_category": sample.get("quota_category"),
                    "input": None,
                    "predicted_alpha": None,
                    "outcome_code": "SKIPPED_BUDGET_STOP",
                    "classifier_status_raw": None,
                    "match_status_raw": None,
                    "alpha_match_fallback_reason": None,
                    "llm_selected_alpha_id": None,
                    "alpha_specific_invalidation_override": None,
                    "alpha_positive_requirement_override": None,
                }
            )

    # Real per-call statistics (token usage, retries, provider_status,
    # latency) live in the real SemanticCallRecord ledger this session
    # already wrote -- read back rather than re-derived, so the request
    # stats reported are the SAME real numbers a production run's own
    # llm_semantic_manifest.json would show, not a second, parallel count.
    call_records = []
    try:
        call_records = session.recorder.read_all()
    except Exception:
        pass
    (run_root / "t3_eval_records.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in records) + "\n"
    )
    (run_root / "t3_eval_semantic_call_records.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in call_records) + "\n"
    )

    return LiveEvalResult(
        execution_id=execution_id,
        records=records,
        stopped_early=stopped_early,
        stop_reason=stop_reason,
        actual_requests_made=tracked_gateway.actual_requests_made,
        max_actual_requests=max_actual_requests,
    )


def _default_gateway_factory(
    execution_id: str, output_root: Path, *, max_tokens: int | None = None
) -> tuple[Any, Any]:
    """Real production construction -- only reachable in live mode."""
    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
    from comqutor_alpha.structure_engine.week2_llm import build_server_week2_llm_gateway

    gateway = build_server_week2_llm_gateway(execution_id, output_root, max_tokens=max_tokens)
    if gateway is None:
        raise RuntimeError(
            "COMQUTOR_WEEK2_LLM_ENABLED / COMQUTOR_WEEK2_LLM_PROVIDER / COMQUTOR_WEEK2_LLM_MODEL "
            "are not fully configured -- live mode refuses to run with a partially-configured gateway."
        )
    run_dir = Path(output_root) / execution_id
    run_dir.mkdir(parents=True, exist_ok=True)
    session = SemanticRuntimeSession(
        run_id=execution_id,
        output_directory=run_dir,
        # Real, enforced allow-list (comqutor_alpha.llm_runtime.contracts.
        # EXECUTION_MODES = {"live", "shadow", "replay_fixture", "test"}) --
        # this factory is only reachable in live mode (its own docstring:
        # "Real production construction -- only reachable in live mode"),
        # so "live" is the one honest value here. A descriptive-but-invalid
        # string here previously crashed SemanticCallRecorder.__init__ with
        # RECORDER_MODE_INVALID before any real Provider call was ever made
        # (caught during this round's own first authorized live attempt,
        # zero cost incurred) -- fixed, not worked around.
        execution_mode="live",
        provider=gateway.provider,
        model=gateway.model_name,
    )
    gateway.attach_semantic_runtime(session)
    return gateway, session


# -----------------------------------------------------------------------
# Scoring (only ever runs against samples that HAVE a human judgment)
# -----------------------------------------------------------------------


UNABLE_TO_JUDGE = "UNABLE_TO_JUDGE"


def score_against_human_labels(
    records: list[dict[str, Any]], review_items: list[dict[str, Any]]
) -> dict[str, Any]:
    """``your_judgment`` may be a real Alpha ID, the literal string ``"NONE"``,
    or the literal string ``UNABLE_TO_JUDGE`` -- a reviewer's explicit
    refusal to guess, never coerced into a right/wrong comparison. Items
    marked ``UNABLE_TO_JUDGE`` are counted and reported (``unable_to_judge_count``)
    but excluded from accuracy/precision/recall/confusion_matrix -- never
    silently dropped, and never forced into a score either.
    """
    judgments = {r["sample_id"]: r.get("your_judgment") for r in review_items if r.get("your_judgment") is not None}
    if not judgments:
        return {
            "scoring_status": "BLOCKED_NO_HUMAN_LABELS",
            "reason": "No review_item has a non-null your_judgment. No accuracy/PASS verdict is computed or implied.",
        }

    all_judged = [r for r in records if r["sample_id"] in judgments]
    unable_to_judge_ids = {sid for sid, label in judgments.items() if label == UNABLE_TO_JUDGE}
    scored = [r for r in all_judged if r["sample_id"] not in unable_to_judge_ids]

    confusion: dict[str, dict[str, int]] = {}
    correct = 0
    non_none_tp = non_none_fp = non_none_fn = 0
    category_counts: dict[str, int] = {}

    for r in scored:
        human_label = judgments[r["sample_id"]]
        predicted = r["predicted_alpha"] if r["outcome_code"] == "MATCHED" else r["outcome_code"]
        confusion.setdefault(str(human_label), {}).setdefault(str(predicted), 0)
        confusion[str(human_label)][str(predicted)] += 1
        category_counts[r.get("quota_category", "UNKNOWN")] = category_counts.get(r.get("quota_category", "UNKNOWN"), 0) + 1

        if str(predicted) == str(human_label):
            correct += 1

        human_is_non_none = human_label not in (None, "NONE")
        predicted_is_non_none = r["outcome_code"] == "MATCHED"
        if predicted_is_non_none and str(predicted) == str(human_label):
            non_none_tp += 1
        elif predicted_is_non_none and not (human_is_non_none and str(predicted) == str(human_label)):
            non_none_fp += 1
        if human_is_non_none and not (predicted_is_non_none and str(predicted) == str(human_label)):
            non_none_fn += 1

    precision = non_none_tp / (non_none_tp + non_none_fp) if (non_none_tp + non_none_fp) else None
    recall = non_none_tp / (non_none_tp + non_none_fn) if (non_none_tp + non_none_fn) else None

    outcome_counts: dict[str, int] = {}
    for r in scored:
        outcome_counts[r["outcome_code"]] = outcome_counts.get(r["outcome_code"], 0) + 1

    return {
        "scoring_status": "SCORED",
        "steps_covered": STEPS_COVERED,
        "scored_sample_count": len(scored),
        "unable_to_judge_count": len(unable_to_judge_ids),
        "total_judged_count": len(all_judged),
        "total_sample_count": len(records),
        "overall_accuracy": round(correct / len(scored), 6) if scored else None,
        "non_none_precision": round(precision, 6) if precision is not None else None,
        "non_none_recall": round(recall, 6) if recall is not None else None,
        "outcome_code_counts": outcome_counts,
        "category_counts": category_counts,
        "confusion_matrix": confusion,
        "note": (
            "confusion_matrix rows are the human label, columns are the system's outcome (an Alpha ID for "
            "MATCHED, or the literal outcome_code for NONE/CALL_FAILED/PARSE_FAILED/UNAVAILABLE/"
            "ABSTAINED_AMBIGUOUS/SKIPPED_BUDGET_STOP) -- failures and abstentions are never dropped from "
            "this matrix or from scored_sample_count. Items where the reviewer explicitly answered "
            "UNABLE_TO_JUDGE are counted in unable_to_judge_count and total_judged_count but excluded from "
            "scored_sample_count/accuracy/precision/recall/confusion_matrix -- never coerced into a "
            "right-or-wrong comparison."
        ),
    }


class SampleVersionMismatch(Exception):
    """Raised when the review form's own claim_text for a judged sample does
    not match what was actually sent to the Provider for that sample_id --
    scoring against a drifted pool would silently misattribute a human
    judgment to a different claim than the one they actually read."""


def score_offline(*, prediction_execution_dir: Path, review_form_file: Path) -> dict[str, Any]:
    """Scores an ALREADY-SAVED prediction execution against a completed human
    review form -- reads two files, computes, writes a NEW result file.
    Never constructs a gateway, never imports map_claim_to_alpha, never
    makes a Provider call of any kind (see
    tests/test_t3_diagnostic_evaluation_driver.py's own AST-based proof of
    this). Never re-runs classification "to fill a gap" and never touches
    the original prediction's own t3_eval_records.jsonl/t3_eval_summary.json.

    Records, in the returned/written result: the SOURCE prediction's own
    execution_id (derived from ``prediction_execution_dir``'s name), a
    sha256 of the exact predictions file scored, and a sha256 of the exact
    review-form file scored -- so a scoring result is always traceable to
    precisely which prediction run and which review-form snapshot produced
    it, never just asserted by a caller.
    """
    records_path = prediction_execution_dir / "t3_eval_records.jsonl"
    if not records_path.exists():
        raise FileNotFoundError(f"No t3_eval_records.jsonl in {prediction_execution_dir}")
    records = [json.loads(line) for line in records_path.read_text().splitlines() if line]
    records_by_id = {r["sample_id"]: r for r in records}

    review_doc = json.loads(review_form_file.read_text())
    review_items = review_doc.get("review_items", [])

    # Sample-version consistency: a judged item's own claim_text must match
    # what THIS prediction execution actually classified for that
    # sample_id -- catches "the pool drifted between prediction and review"
    # rather than silently scoring a judgment against the wrong claim.
    version_mismatches: list[dict[str, Any]] = []
    for item in review_items:
        if item.get("your_judgment") is None:
            continue
        sample_id = item.get("sample_id")
        record = records_by_id.get(sample_id)
        if record is None:
            version_mismatches.append(
                {"sample_id": sample_id, "reason": "JUDGED_SAMPLE_ID_NOT_IN_PREDICTION_RECORDS"}
            )
            continue
        predicted_claim = (record.get("input") or {}).get("claim")
        reviewed_claim = item.get("claim_text")
        if predicted_claim is not None and reviewed_claim is not None and predicted_claim != reviewed_claim:
            version_mismatches.append(
                {
                    "sample_id": sample_id,
                    "reason": "CLAIM_TEXT_MISMATCH_BETWEEN_PREDICTION_AND_REVIEW",
                    "predicted_claim_text": predicted_claim,
                    "reviewed_claim_text": reviewed_claim,
                }
            )

    scoring = score_against_human_labels(records, review_items)

    return {
        "schema_version": "t3_offline_score_result.v1",
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "source_prediction_execution_id": prediction_execution_dir.name,
        "source_predictions_file": str(records_path),
        "source_predictions_file_sha256": _sha256_file(records_path),
        "review_form_file": str(review_form_file),
        "review_form_file_sha256": _sha256_file(review_form_file),
        "sample_version_mismatches": version_mismatches,
        "sample_version_consistent": not version_mismatches,
        "scoring": scoring,
    }


# -----------------------------------------------------------------------
# Human-review worksheet: readable export + import back into the review form
# -----------------------------------------------------------------------

WORKSHEET_FIELDS = [
    "sample_id",
    "quota_category",
    "ticker",
    "claim_text",
    "alpha_judgment_feasibility",
    "source_material_completeness_status",
    "your_judgment",
    "your_rationale",
    "reviewer_id",
]

# 2026-10-05 fix: this previously hardcoded exactly the 7 Alpha IDs named
# in requested_quota's own sampling-stratification keys
# (t3_targeted_diagnostic_sample_2026-09-30.json: A304_boundary/
# A101_A103_differentiation [[which name A304/A101/A103]] + A001/A003/A102/
# A501) -- but that field controls which CLAIMS were selected to stress
# specific boundary pairs, never which ANSWERS a reviewer or the real
# classifier is allowed to give. The real, frozen candidate set is the
# full taxonomy the live classifier itself validates against
# (comqutor_alpha.structure_engine.alpha_mapper: `allowed_ids = set(taxonomy)`,
# raising "classifier selected an Alpha ID outside the canonical taxonomy"
# for anything else) -- confirmed to be 10 Alpha IDs, not 7: A001, A003,
# A101, A102, A103, A201, A301, A304, A501, A601 (comqutor_alpha/
# alpha_library/alpha_taxonomy_v1.yaml's own 10 top-level `alpha_id`
# entries). A human reviewer judging a claim's real mechanism must never be
# constrained to a narrower set than the classifier itself is allowed to
# answer with -- that would make some correct human judgments
# structurally unrepresentable. Derived dynamically from the same loader
# the real classifier uses, never a second hardcoded list that can drift
# out of sync with the taxonomy file again.
def _real_classifier_alpha_ids() -> frozenset[str]:
    from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy

    return frozenset(load_alpha_taxonomy())


VALID_JUDGMENT_VALUES_NOTE = (
    "your_judgment: one of the real taxonomy's own Alpha IDs (A001, A003, A101, A102, A103, "
    "A201, A301, A304, A501, A601), NONE, or "
    f"{UNABLE_TO_JUDGE} (explicit refusal to guess -- never forced to pick a side). "
    "Leave blank if not yet reviewed."
)


def export_review_worksheet(review_form_path: Path, worksheet_path: Path) -> int:
    """Writes a plain, readable CSV a human can open in any spreadsheet tool.

    Hides hidden_system_answers entirely (never reads that key) and every
    historical prediction field -- only the fields a reviewer needs to make
    an independent judgment are present. Returns the row count written.
    """
    review_doc = json.loads(review_form_path.read_text())
    items = review_doc.get("review_items", [])
    with worksheet_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=WORKSHEET_FIELDS)
        writer.writeheader()
        for item in items:
            writer.writerow(
                {
                    "sample_id": item.get("sample_id", ""),
                    "quota_category": item.get("quota_category", ""),
                    "ticker": item.get("ticker", ""),
                    "claim_text": item.get("claim_text", ""),
                    "alpha_judgment_feasibility": item.get("alpha_judgment_feasibility", ""),
                    "source_material_completeness_status": item.get("source_material_completeness_status", ""),
                    "your_judgment": item.get("your_judgment") or "",
                    "your_rationale": item.get("your_rationale") or "",
                    "reviewer_id": item.get("reviewer_id") or "",
                }
            )
    return len(items)


def _allowed_judgment_values() -> frozenset[str]:
    return _real_classifier_alpha_ids() | {"NONE", UNABLE_TO_JUDGE}


def import_review_worksheet(worksheet_path: Path, review_form_path: Path) -> dict[str, Any]:
    """Merges a filled-in worksheet back into the real review form, by sample_id.

    Never invents a judgment for a row the reviewer left blank (that
    review_item's your_judgment stays exactly what it already was -- null if
    it was never answered). Rejects (raises) on any non-blank value outside
    ``_allowed_judgment_values()`` (the real taxonomy's own Alpha IDs, plus
    NONE/UNABLE_TO_JUDGE) rather than silently accepting a typo as a real
    Alpha ID. This function performs the merge in memory and returns the
    updated document plus a summary -- the caller decides whether/how to
    persist it (kept separate so a dry-run is trivial).
    """
    review_doc = json.loads(review_form_path.read_text())
    items_by_id = {item["sample_id"]: item for item in review_doc.get("review_items", [])}
    allowed_judgment_values = _allowed_judgment_values()

    updated_count = 0
    rejected: list[dict[str, str]] = []
    with worksheet_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            sample_id = row.get("sample_id", "").strip()
            judgment = (row.get("your_judgment") or "").strip()
            if not judgment:
                continue  # not yet answered -- leave the existing item untouched
            if sample_id not in items_by_id:
                rejected.append({"sample_id": sample_id, "reason": "UNKNOWN_SAMPLE_ID"})
                continue
            if judgment.upper() not in allowed_judgment_values:
                rejected.append({"sample_id": sample_id, "reason": f"INVALID_JUDGMENT_VALUE:{judgment!r}"})
                continue
            item = items_by_id[sample_id]
            item["your_judgment"] = judgment.upper()
            item["your_rationale"] = (row.get("your_rationale") or "").strip() or None
            item["reviewer_id"] = (row.get("reviewer_id") or "").strip() or None
            item["reviewed_at"] = datetime.now(timezone.utc).isoformat()
            updated_count += 1

    judged_total = sum(1 for item in items_by_id.values() if item.get("your_judgment") is not None)
    review_doc["human_review_performed"] = judged_total > 0
    review_doc["review_status"] = (
        "COMPLETE" if judged_total == len(items_by_id) else f"IN_PROGRESS -- {judged_total}/{len(items_by_id)} judged"
    )
    return {"document": review_doc, "updated_count": updated_count, "rejected": rejected}


# -----------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "mode",
        choices=["preflight", "live", "score", "export-worksheet", "import-worksheet"],
        nargs="?",
        default="preflight",
    )
    parser.add_argument("--samples-file", type=Path)
    parser.add_argument("--review-form-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--worksheet-file", type=Path, help="Required for export-worksheet/import-worksheet.")
    parser.add_argument(
        "--prediction-execution-dir",
        type=Path,
        help="Required for --mode score: the <output-dir>/<execution_id> directory a prior `live` run wrote.",
    )
    parser.add_argument("--max-actual-requests", type=int, default=60)
    parser.add_argument("--max-retries-per-call", type=int, default=1)
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=200,
        help="Real per-call output-token cap forwarded to the Provider client (live mode only).",
    )
    parser.add_argument(
        "--i-acknowledge-this-makes-real-provider-calls",
        action="store_true",
        dest="acknowledged",
        help="Required for --mode live. Refused without it.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    if args.mode == "export-worksheet":
        if args.worksheet_file is None:
            print("REFUSED: export-worksheet requires --worksheet-file.", file=sys.stderr)
            return 2
        row_count = export_review_worksheet(args.review_form_file, args.worksheet_file)
        print(f"Wrote {row_count} rows to {args.worksheet_file}. {VALID_JUDGMENT_VALUES_NOTE}")
        return 0

    if args.mode == "import-worksheet":
        if args.worksheet_file is None:
            print("REFUSED: import-worksheet requires --worksheet-file.", file=sys.stderr)
            return 2
        result = import_review_worksheet(args.worksheet_file, args.review_form_file)
        if result["rejected"]:
            print(f"REJECTED {len(result['rejected'])} row(s) -- fix and re-import:", file=sys.stderr)
            for r in result["rejected"]:
                print(f"  {r['sample_id']}: {r['reason']}", file=sys.stderr)
        args.review_form_file.write_text(json.dumps(result["document"], ensure_ascii=False, indent=2))
        print(f"Merged {result['updated_count']} judgment(s) into {args.review_form_file}.")
        return 1 if result["rejected"] else 0

    if args.mode == "score":
        # Zero Provider calls, zero gateway construction, never re-invokes
        # map_claim_to_alpha -- reads two already-existing files and writes
        # a NEW result file. See tests/test_t3_diagnostic_evaluation_driver.py
        # for the AST-based proof that this code path never imports a
        # network/provider/gateway-construction module.
        if args.prediction_execution_dir is None:
            print("REFUSED: score requires --prediction-execution-dir.", file=sys.stderr)
            return 2
        result = score_offline(
            prediction_execution_dir=args.prediction_execution_dir,
            review_form_file=args.review_form_file,
        )
        if not result["sample_version_consistent"]:
            print(
                f"WARNING: {len(result['sample_version_mismatches'])} sample-version mismatch(es) between "
                "the prediction and the review form -- see sample_version_mismatches in the result below.",
                file=sys.stderr,
            )
        score_execution_id = f"t3score_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
        out_path = args.prediction_execution_dir / f"{score_execution_id}_score_result.json"
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["sample_version_consistent"] else 1

    if args.samples_file is None or args.output_dir is None:
        print(f"REFUSED: --mode {args.mode} requires --samples-file and --output-dir.", file=sys.stderr)
        return 2

    if args.mode == "preflight":
        report = run_preflight(
            args.samples_file,
            args.review_form_file,
            args.output_dir,
            args.max_actual_requests,
            args.max_retries_per_call,
        )
        out_path = args.output_dir / f"{report.execution_id}_preflight.json"
        args.output_dir.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 0 if report.ready_for_live else 1

    # live mode -- ALWAYS predict-only. Scoring is a fully separate, offline
    # `score` mode above; this path never reads review_items at all.
    if not args.acknowledged:
        print(
            "REFUSED: live mode requires --i-acknowledge-this-makes-real-provider-calls.",
            file=sys.stderr,
        )
        return 2
    if os.environ.get("COMQUTOR_WEEK2_LLM_ENABLED") != "1":
        print("REFUSED: COMQUTOR_WEEK2_LLM_ENABLED=1 is not set in this environment.", file=sys.stderr)
        return 2

    samples_doc = json.loads(args.samples_file.read_text())
    samples = samples_doc.get("samples", [])

    execution_id = f"t3live_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    freeze_identity = build_freeze_identity(args.samples_file, args.review_form_file)

    run_root = args.output_dir / execution_id
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "freeze_identity.json").write_text(json.dumps(freeze_identity, ensure_ascii=False, indent=2))

    result = run_live_evaluation(
        samples,
        execution_id=execution_id,
        output_dir=args.output_dir,
        max_actual_requests=args.max_actual_requests,
        max_retries_per_call=args.max_retries_per_call,
        max_output_tokens=args.max_output_tokens,
    )

    summary: dict[str, Any] = {
        "execution_id": execution_id,
        "script_scope": SCRIPT_SCOPE,
        "stopped_early": result.stopped_early,
        "stop_reason": result.stop_reason,
        "record_count": len(result.records),
        "actual_requests_made": result.actual_requests_made,
        "max_actual_requests": result.max_actual_requests,
        "max_output_tokens": args.max_output_tokens,
        "steps_covered": STEPS_COVERED,
        "scoring": {
            "scoring_status": (
                "NOT_APPLICABLE -- this is a predict-only run; the review form was never read. "
                "Use `score --prediction-execution-dir "
                f"{run_root} --review-form-file <path>` after human review to score it, offline, "
                "with zero Provider calls."
            )
        },
    }

    (run_root / "t3_eval_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
