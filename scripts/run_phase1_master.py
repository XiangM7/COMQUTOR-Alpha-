#!/usr/bin/env python3
"""Phase 1 Master — one resumable state machine for Development Plan §5.1
Structured Output Adapter Provider Recovery, Controlled Evaluation, Human
Quality Gate, Live Shadow Integration, and Conditional Production Cutover.

See ``docs/adr/ADR-010-phase1-structured-adapter-authority.md`` and
``docs/specs/phase1_master_execution_contract_v1.md`` for the governing
decisions and full contract this script implements.

Usage::

    python scripts/run_phase1_master.py --resume
    python scripts/run_phase1_master.py --resume --human-review-csv <path>

Never invoked automatically; never invokes a Provider beyond the
``PROVIDER_DIAGNOSTIC`` stage unless ``COMQUTOR_PHASE1_MASTER_APPROVED`` is
exactly the string ``"true"``. State is persisted atomically after every
transition to ``docs/audit_artifacts/phase1_master/phase1_master_state.json``
so a later ``--resume`` (in this or a later process) continues from exactly
where execution stopped, using the same cumulative call/attempt ledger.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import socket
import ssl
import statistics
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.evaluation.phase1_human_review_packet import (  # noqa: E402
    ALLOWED_REVIEW_VALUES as HUMAN_REVIEW_V2_ALLOWED_VALUES,
    REVIEW_FIELDS as HUMAN_REVIEW_V2_FIELDS,
)
from comqutor_alpha.llm_runtime.cache import NullLLMResponseCache  # noqa: E402
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession  # noqa: E402
from comqutor_alpha.research_profiles import (  # noqa: E402
    ANTHROPIC_PROFILE_ID,
    DEEPSEEK_DEFAULT_PROFILE_ID,
    ResearchProfileError,
    get_research_profile,
)
from comqutor_alpha.structure_engine.factor_normalizer import FACTOR_ALIASES  # noqa: E402
from comqutor_alpha.structure_engine.structured_output_adapter import (  # noqa: E402
    adapt_raw_agent_outputs,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt import (  # noqa: E402
    STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v2 import (  # noqa: E402
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v3 import (  # noqa: E402
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V3_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v4 import (  # noqa: E402
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4,
)
from comqutor_alpha.structure_engine.structured_output_shadow_provider import (  # noqa: E402
    STRUCTURED_CLAIM_SHADOW_MAX_RETRIES,
    STRUCTURED_CLAIM_SHADOW_TIMEOUT_SECONDS,
    ProviderSmokeAuthorizationError,
    build_phase1_master_provider_gateway,
    profile_id_for_semantic_task,
    run_real_provider_shadow_smoke_for_report,
    run_real_provider_shadow_smoke_for_report_v2,
    run_real_provider_shadow_smoke_for_report_v3,
    run_real_provider_shadow_smoke_for_report_v4,
)
from comqutor_alpha.structure_engine.structured_output_shadow_replay import (  # noqa: E402
    verify_phase1_master_shadow_exact_replay,
)
from comqutor_alpha.structure_engine.structured_output_shadow_review import (  # noqa: E402
    build_blank_review_rows,
    compare_legacy_and_shadow,
    render_blank_review_csv,
)
from comqutor_alpha.structure_engine.structured_output_shadow_v3 import (  # noqa: E402
    summarize_resolution_log as summarize_resolution_log_v3,
)
from comqutor_alpha.structure_engine.structured_output_shadow_v4 import (  # noqa: E402
    summarize_resolution_log as summarize_resolution_log_v4,
)

STATE_DIR = REPO_ROOT / "docs/audit_artifacts/phase1_master"
STATE_PATH = STATE_DIR / "phase1_master_state.json"
LEDGER_PATH = STATE_DIR / "provider_call_ledger.json"
GLOBAL_PROVIDER_LEDGER_PATH = STATE_DIR / "phase1_global_provider_call_ledger.jsonl"
CONNECTIVITY_REPORT_PATH = STATE_DIR / "provider_connectivity_report.json"
EVALUATION_CORPUS_PATH = REPO_ROOT / "docs/audit_artifacts/phase1a/evaluation_corpus_inventory.json"

APPROVAL_ENV_VAR = "COMQUTOR_PHASE1_MASTER_APPROVED"
DATA_EGRESS_APPROVAL_ENV_VAR = "COMQUTOR_PHASE1_MASTER_DATA_EGRESS_APPROVED"
RESEARCH_PROFILE_ID = DEEPSEEK_DEFAULT_PROFILE_ID
STRUCTURED_CLAIM_SHADOW_PROFILE_ID = ANTHROPIC_PROFILE_ID
TARGET_FAMILY_ORDER = ("fundamental", "news", "sentiment", "technical")

# Raised from 53 to 70, then 70 to 95, for the Phase 1 Master evidence-
# alignment fix (product-owner-approved each time): 43 logical calls were
# already spent on v1+v2; the v3 24-report evaluation used 24 more (43+24=
# 67, matching the first raise to 70); the v4 24-report evaluation
# (markdown-formatting-fidelity fix) needs 24 more genuinely new logical
# calls (a prompt-version switch always resets anthropic_called_report_ids,
# so no v3 call can be reused under v4), 67 + 24 = 91, plus a small margin.
# HARD_CAP_PROVIDER_ATTEMPTS raised from 105 to 130: 74 already used, and
# even the worst case of one transient retry on every one of the 24 v4
# calls (+48) stays within the new cap with headroom (v3's real run
# actually needed zero retries across all 24 calls).
# Phase 1 Master original cap (95) plus the product-owner-authorized final
# v4.1 four-slot Re-Canary (99). Raised again by exactly 4 (99->103) for the
# product-owner-authorized final v4.2 four-slot live Canary, confirmed via
# AskUserQuestion before this raise: 99 used + 4 = 103. Provider-attempt cap
# needs no change (106 used + 4 = 110 <= 130, already has headroom). No
# other task may consume this additive budget.
HARD_CAP_LOGICAL_CALLS = 103
HARD_CAP_PROVIDER_ATTEMPTS = 130

STATES = (
    "PROVIDER_DIAGNOSTIC",
    "PROVIDER_PROBE",
    "ANTHROPIC_QUALIFICATION",
    "SMOKE",
    "PILOT",
    "CORE_EVALUATION",
    "WAITING_FOR_HUMAN_REVIEW",
    "QUALITY_GATE",
    "PROMPT_V2_REVISION",
    "LIVE_SHADOW_INTEGRATION",
    "LIVE_SHADOW_CANARY",
    "PRODUCTION_CUTOVER",
    "COMPLETE",
    "BLOCKED",
    "FAIL",
)

# BLOCKED reasons whose root cause is the task-level execution-policy
# question (never a genuine unresolved DNS/TCP/TLS/credential/profile
# problem) -- section 6: a resume after the policy fix skips re-running
# PROVIDER_DIAGNOSTIC/PROVIDER_PROBE and retries SMOKE directly, but only
# when this state's own history proves those two stages already passed.
RETRYABLE_AFTER_POLICY_FIX_REASON_CODES = frozenset(
    {
        "BLOCKED_PROVIDER_CONNECTIVITY",
        "BLOCKED_STRUCTURED_SHADOW_TASK_TIMEOUT_POLICY",
        "BLOCKED_PROVIDER_LATENCY_UNSTABLE",
        "BLOCKED_PROVIDER_MODEL_UNSUITABLE_FOR_LONG_STRUCTURED_TASK",
        "BLOCKED_SMOKE_EXACT_REPLAY_NOT_REPRODUCIBLE",
        "BLOCKED_ANTHROPIC_PROVIDER_RELIABILITY",
    }
)

STAGE_TICKERS: dict[str, tuple[str, ...]] = {
    "SMOKE": ("NVDA",),
    "PILOT": ("NVDA", "QQQ", "MSFT"),
    "CORE_EVALUATION": ("NVDA", "QQQ", "MSFT", "SNDK", "TSM", "AMD"),
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _initial_state() -> dict[str, Any]:
    return {
        "schema_version": "comqutor.phase1_master.state.v1",
        "current_state": "ANTHROPIC_QUALIFICATION",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "research_profile_id": RESEARCH_PROFILE_ID,
        "structured_claim_shadow_profile_id": STRUCTURED_CLAIM_SHADOW_PROFILE_ID,
        "structured_claim_shadow_provider": "anthropic",
        "structured_claim_shadow_model": "claude-sonnet-4-6",
        "structured_claim_shadow_timeout": STRUCTURED_CLAIM_SHADOW_TIMEOUT_SECONDS,
        "structured_claim_shadow_max_retries": STRUCTURED_CLAIM_SHADOW_MAX_RETRIES,
        "cumulative_logical_calls": 0,
        "cumulative_provider_attempts": 0,
        "prompt_version_in_use": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
        "prompt_sha256_in_use": STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
        "already_called_report_ids": [],
        "anthropic_called_report_ids": [],
        "previous_provider_evaluations": [],
        "current_provider_evaluation": {
            "profile_id": STRUCTURED_CLAIM_SHADOW_PROFILE_ID,
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "evaluation_dir": None,
            "qualification_completed": False,
        },
        "evaluation_dir": None,
        "blocked_reason_code": None,
        "fail_reason_code": None,
        "human_review_csv_path": None,
        "quality_gate_result": None,
        "next_action": "run PROVIDER_DIAGNOSTIC",
        "history": [],
    }


def load_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if _migrate_existing_state_to_anthropic(state):
            save_state(state)
        return state
    state = _initial_state()
    _write_json(STATE_PATH, state)
    return state


def _migrate_existing_state_to_anthropic(state: dict[str, Any]) -> bool:
    """Add the product-owner-approved task route without erasing history."""

    if state.get("structured_claim_shadow_profile_id") == STRUCTURED_CLAIM_SHADOW_PROFILE_ID:
        return False

    prior_evaluation_dir = state.get("evaluation_dir")
    prior_blocker = state.get("blocked_reason_code")
    prior_called = list(state.get("already_called_report_ids") or [])
    state["structured_claim_shadow_profile_id"] = STRUCTURED_CLAIM_SHADOW_PROFILE_ID
    state["structured_claim_shadow_provider"] = "anthropic"
    state["structured_claim_shadow_model"] = "claude-sonnet-4-6"
    state["structured_claim_shadow_timeout"] = STRUCTURED_CLAIM_SHADOW_TIMEOUT_SECONDS
    state["structured_claim_shadow_max_retries"] = STRUCTURED_CLAIM_SHADOW_MAX_RETRIES
    state["deepseek_called_report_ids"] = prior_called
    state["anthropic_called_report_ids"] = []
    state["previous_provider_evaluations"] = [
        {
            "profile_id": DEEPSEEK_DEFAULT_PROFILE_ID,
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "evaluation_dir": prior_evaluation_dir,
            "terminal_blocker": "BLOCKED_PROVIDER_MODEL_UNSUITABLE_FOR_LONG_STRUCTURED_TASK",
            "preserved": True,
        }
    ]
    state["current_provider_evaluation"] = {
        "profile_id": STRUCTURED_CLAIM_SHADOW_PROFILE_ID,
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "evaluation_dir": None,
        "qualification_completed": False,
    }
    state["evaluation_dir"] = None
    state["blocked_reason_reclassified_from"] = prior_blocker
    state["blocked_reason_code"] = "BLOCKED_PROVIDER_MODEL_UNSUITABLE_FOR_LONG_STRUCTURED_TASK"
    state["root_cause_status"] = (
        "DeepSeek model/provider instability is the root blocker; Exact Replay is downstream, "
        "not the root cause."
    )
    state["next_action"] = "run one Anthropic qualification, then Anthropic Smoke/Pilot/Core"
    return True


def _switch_structured_claim_shadow_to_prompt_v2(state: dict[str, Any]) -> None:
    """One-time switch from the frozen v1 prompt to the measured, tested v2
    minimal-request prompt -- the Phase 1 Master prompt-size root-cause fix
    (docs/audit_artifacts/phase1_master/prompt_audit/). This is itself the
    one Prompt v2 revision the Master task's own budget rule allows ("at
    most one Prompt v2 revision"); the caller must only invoke this once,
    guarded by ``prompt_version_in_use`` not already being v2.

    Voids (but preserves as audit evidence, never deletes) the prior
    v1-prompted Anthropic Smoke attempt: those 4 report results are not
    valid under a different prompt identity (a mixed-prompt-version
    evaluation_dir would violate the Exact Replay verifier's prompt-hash
    consistency check), so they must be genuinely re-attempted under v2,
    never silently reused or merged.
    """

    prior_evaluation_dir = state.get("evaluation_dir")
    prior_anthropic_called = list(state.get("anthropic_called_report_ids") or [])
    current_eval = dict(state.get("current_provider_evaluation") or {})
    state.setdefault("previous_provider_evaluations", []).append(
        {
            "profile_id": current_eval.get("profile_id"),
            "provider": current_eval.get("provider"),
            "model": current_eval.get("model"),
            "prompt_version": state.get("prompt_version_in_use"),
            "evaluation_dir": prior_evaluation_dir,
            "terminal_blocker": "BLOCKED_ANTHROPIC_PROVIDER_RELIABILITY",
            "preserved": True,
        }
    )
    state["prompt_version_in_use"] = STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2
    state["prompt_sha256_in_use"] = STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256
    state["prompt_v2_migration"] = {
        "migrated_at": _now_iso(),
        "from_prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
        "to_prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2,
        "reason_code": "PHASE1_MASTER_PROMPT_SIZE_ROOT_CAUSE_FIX",
        "audit_artifacts_dir": "docs/audit_artifacts/phase1_master/prompt_audit/",
        "measured_v1_request_chars": 98633,
        "measured_v2_request_chars": 18874,
        "reduction_pct": 80.86,
        "prior_anthropic_smoke_report_ids_voided": prior_anthropic_called,
        "prior_evaluation_dir_preserved_untouched": prior_evaluation_dir,
        "revision_count": 1,
    }
    state["anthropic_called_report_ids"] = []
    state["evaluation_dir"] = None
    if isinstance(state.get("current_provider_evaluation"), dict):
        state["current_provider_evaluation"]["evaluation_dir"] = None
    state["blocked_reason_code"] = None


def _switch_structured_claim_shadow_to_prompt_v3(state: dict[str, Any]) -> None:
    """Phase 1 Master evidence-alignment fix: one-time switch from the v2
    minimal-request prompt to the measured, tested v3 prompt.

    v2 proved Claim extraction runs at a compact request size
    (docs/audit_artifacts/phase1_master/prompt_audit/). Human/AI review of
    the completed v2 24-report evaluation then found a systemic problem
    downstream of size: a Claim's bound ``source_spans`` were often not
    actually the evidence that supports it, because v2 asked the model to
    compute its own character offsets with no independent verification
    that they were even the right sentence. v3 asks the model for verbatim
    ``supporting_quotes`` instead and locates every quote deterministically
    by exact string match only (see
    ``structured_output_shadow_v3.resolve_supporting_quote``); it never
    asks for or trusts a model-supplied offset.

    This is a deliberate, human-triggered transition
    (``--apply-v3-evidence-alignment-fix``), never something this state
    machine infers on its own from a blank, not-yet-reviewed CSV: the
    finding that motivates it came from review conducted outside this
    resumable state machine, exactly like every other real, external input
    this script has ever required explicit approval for.

    Preserves (never deletes) the completed v2 24-report evaluation as
    audit evidence -- it remains a real, valid data point
    (``V2_ENGINEERING_RELIABILITY=PASS``: 100% response rate, 100%
    accepted, 100% Exact Replay) even though its evidence alignment was
    judged insufficient (``V2_SEMANTIC_EVIDENCE_ALIGNMENT=FAIL``). Voids
    (but preserves) v2's ``anthropic_called_report_ids`` and
    ``evaluation_dir`` so every report is genuinely re-attempted under v3 --
    the same shape as :func:`_switch_structured_claim_shadow_to_prompt_v2`.
    """

    prior_evaluation_dir = state.get("evaluation_dir")
    prior_anthropic_called = list(state.get("anthropic_called_report_ids") or [])
    current_eval = dict(state.get("current_provider_evaluation") or {})
    state.setdefault("previous_provider_evaluations", []).append(
        {
            "profile_id": current_eval.get("profile_id"),
            "provider": current_eval.get("provider"),
            "model": current_eval.get("model"),
            "prompt_version": state.get("prompt_version_in_use"),
            "evaluation_dir": prior_evaluation_dir,
            "terminal_blocker": "V2_SEMANTIC_EVIDENCE_ALIGNMENT_FAIL",
            "v2_engineering_reliability": "PASS",
            "v2_semantic_evidence_alignment": "FAIL",
            "preserved": True,
        }
    )
    state["prompt_version_in_use"] = STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3
    state["prompt_sha256_in_use"] = STRUCTURED_OUTPUT_SHADOW_PROMPT_V3_SHA256
    state["prompt_v3_migration"] = {
        "migrated_at": _now_iso(),
        "from_prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2,
        "to_prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3,
        "reason_code": "PHASE1_MASTER_EVIDENCE_ALIGNMENT_FIX",
        "finding": (
            "v2 human/AI review found systemic Claim-to-Evidence "
            "misalignment: the Claim was often correct but its bound "
            "source_spans were not always the sentence that actually "
            "supports it, because v2 trusted model-computed offsets."
        ),
        "fix": (
            "v3 asks the model for verbatim supporting_quotes only; a "
            "deterministic EvidenceQuoteResolver (exact string match only, "
            "never fuzzy) locates and verifies every quote; unresolved or "
            "ambiguous quotes are rejected, never repaired or defaulted."
        ),
        "prior_v2_evaluation_dir_preserved_untouched": prior_evaluation_dir,
        "prior_v2_anthropic_smoke_report_ids_voided": prior_anthropic_called,
        "v2_engineering_reliability": "PASS",
        "v2_semantic_evidence_alignment": "FAIL",
        "revision_count": 1,
    }
    state["semantic_quality"] = "FAILED_CURRENT_V2_GATE"
    state["human_review"] = None
    state["production_authority"] = "LEGACY_ADAPTER"
    state["anthropic_called_report_ids"] = []
    state["evaluation_dir"] = None
    if isinstance(state.get("current_provider_evaluation"), dict):
        state["current_provider_evaluation"]["evaluation_dir"] = None
    state["blocked_reason_code"] = None
    state["fail_reason_code"] = None


def _switch_structured_claim_shadow_to_prompt_v4(state: dict[str, Any]) -> None:
    """Phase 1 Master evidence-alignment fix, round 2: one-time switch from
    the v3 prompt to the measured, tested v4 markdown-formatting-fidelity
    prompt.

    v3's real 24-report evaluation proved the EvidenceQuoteResolver design
    works (zero fabricated or unresolved quotes were ever admitted), but
    measured a real cost: 8 of 24 reports (33.3%) were rejected outright.
    Offline root-cause analysis of that real, persisted data found 31 of 33
    individual quote-resolution failures (94%) traced to one precise,
    mechanical cause: the model reliably dropped or repositioned Markdown
    emphasis characters (``**bold**``) when copying a phrase, because v3's
    prompt never told it those characters are literal report content. v4
    adds exactly one new instruction section addressing that, changing
    nothing else about the request shape, resolver algorithm, canonical
    schema, or validator.

    This is a deliberate, human-triggered transition
    (``--apply-v4-markdown-formatting-fix``), never something this state
    machine infers on its own -- mirrors
    :func:`_switch_structured_claim_shadow_to_prompt_v3` exactly, one
    version up.

    Preserves (never deletes) the completed v3 24-report evaluation as
    audit evidence -- it remains a real, valid data point
    (``V3_ENGINEERING_RELIABILITY=PASS``: 100% response rate, zero
    fabricated/unresolved quotes ever admitted, 100% Exact Replay) even
    though its acceptance rate was lower than desired
    (``V3_MARKDOWN_FORMATTING_FIDELITY=PARTIAL``, 16/24 = 66.7% accepted).
    Voids (but preserves) v3's ``anthropic_called_report_ids`` and
    ``evaluation_dir`` so every report is genuinely re-attempted under v4.
    """

    prior_evaluation_dir = state.get("evaluation_dir")
    prior_anthropic_called = list(state.get("anthropic_called_report_ids") or [])
    current_eval = dict(state.get("current_provider_evaluation") or {})
    state.setdefault("previous_provider_evaluations", []).append(
        {
            "profile_id": current_eval.get("profile_id"),
            "provider": current_eval.get("provider"),
            "model": current_eval.get("model"),
            "prompt_version": state.get("prompt_version_in_use"),
            "evaluation_dir": prior_evaluation_dir,
            "terminal_blocker": "V3_MARKDOWN_FORMATTING_FIDELITY_PARTIAL",
            "v3_engineering_reliability": "PASS",
            "v3_evidence_alignment_safety": "PASS",
            "v3_markdown_formatting_fidelity": "PARTIAL",
            "v3_accepted_report_count": 16,
            "v3_rejected_report_count": 8,
            "preserved": True,
        }
    )
    state["prompt_version_in_use"] = STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4
    state["prompt_sha256_in_use"] = STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256
    state["prompt_v4_migration"] = {
        "migrated_at": _now_iso(),
        "from_prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3,
        "to_prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4,
        "reason_code": "PHASE1_MASTER_MARKDOWN_FORMATTING_FIDELITY_FIX",
        "finding": (
            "v3's real 24-report evaluation rejected 8/24 (33.3%) reports; "
            "94% of the underlying quote-resolution failures (31/33) traced "
            "to the model silently dropping or repositioning the report's "
            "own Markdown emphasis characters (**bold**) when quoting."
        ),
        "fix": (
            "v4 adds one explicit FORMATTING RULES instruction (with its "
            "own synthetic example) telling the model that Markdown "
            "formatting characters inside AGENT_REPORT are literal text "
            "and must be reproduced exactly when quoted. The resolver "
            "algorithm, wire request shape, canonical schema, and "
            "validator are all unchanged from v3."
        ),
        "prior_v3_evaluation_dir_preserved_untouched": prior_evaluation_dir,
        "prior_v3_anthropic_smoke_report_ids_voided": prior_anthropic_called,
        "v3_engineering_reliability": "PASS",
        "v3_evidence_alignment_safety": "PASS",
        "v3_markdown_formatting_fidelity": "PARTIAL",
        "v3_accepted_report_count": 16,
        "v3_rejected_report_count": 8,
        "revision_count": 1,
    }
    state["semantic_quality"] = "PENDING_V4_REEVALUATION"
    state["human_review"] = None
    state["production_authority"] = "LEGACY_ADAPTER"
    state["anthropic_called_report_ids"] = []
    state["evaluation_dir"] = None
    if isinstance(state.get("current_provider_evaluation"), dict):
        state["current_provider_evaluation"]["evaluation_dir"] = None
    state["blocked_reason_code"] = None
    state["fail_reason_code"] = None


def _void_evaluation_dir_and_reset_for_retry(state: dict[str, Any], *, terminal_note: str) -> str | None:
    """Preserve (never delete) the current evaluation_dir as audit evidence
    and reset identity so the next SMOKE/PILOT/CORE_EVALUATION call mints a
    fresh one and genuinely re-attempts every report. Shared by any recovery
    path that determines a prior real attempt's artifacts are not valid to
    build on (a different prompt version, or -- as with
    FAIL_ACCEPTED_OUTPUT_EXACT_REPLAY -- a bug in this repo's own verifier
    that has since been fixed, confirmed by re-running the corrected
    verifier against the SAME unmodified real artifacts)."""

    prior_evaluation_dir = state.get("evaluation_dir")
    current_eval = dict(state.get("current_provider_evaluation") or {})
    state.setdefault("previous_provider_evaluations", []).append(
        {
            "profile_id": current_eval.get("profile_id"),
            "provider": current_eval.get("provider"),
            "model": current_eval.get("model"),
            "prompt_version": state.get("prompt_version_in_use"),
            "evaluation_dir": prior_evaluation_dir,
            "terminal_blocker": terminal_note,
            "preserved": True,
        }
    )
    state["anthropic_called_report_ids"] = []
    state["evaluation_dir"] = None
    if isinstance(state.get("current_provider_evaluation"), dict):
        state["current_provider_evaluation"]["evaluation_dir"] = None
    return prior_evaluation_dir


def save_state(state: dict[str, Any]) -> None:
    state["updated_at"] = _now_iso()
    _write_json(STATE_PATH, state)


def transition(state: dict[str, Any], to_state: str, detail: dict[str, Any]) -> None:
    state["history"].append(
        {"at": _now_iso(), "from_state": state["current_state"], "to_state": to_state, "detail": detail}
    )
    state["current_state"] = to_state
    save_state(state)


def _append_ledger(entry: dict[str, Any]) -> None:
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8")) if LEDGER_PATH.exists() else {"entries": []}
    ledger["entries"].append(entry)
    ledger["cumulative_logical_calls"] = sum(e.get("logical_calls", 0) for e in ledger["entries"])
    ledger["cumulative_provider_attempts"] = sum(e.get("provider_attempts", 0) for e in ledger["entries"])
    _write_json(LEDGER_PATH, ledger)


def _append_global_provider_ledger(entry: dict[str, Any]) -> None:
    """Append one idempotent, non-secret actual-usage event to the JSONL ledger."""

    event_id = str(entry.get("event_id") or "")
    if not event_id:
        raise ValueError("PHASE1_GLOBAL_PROVIDER_LEDGER_EVENT_ID_REQUIRED")
    GLOBAL_PROVIDER_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    if GLOBAL_PROVIDER_LEDGER_PATH.exists():
        for line in GLOBAL_PROVIDER_LEDGER_PATH.read_text(encoding="utf-8").splitlines():
            if line and json.loads(line).get("event_id") == event_id:
                return
    payload = json.dumps(entry, ensure_ascii=False, separators=(",", ":"), default=str) + "\n"
    descriptor = os.open(
        GLOBAL_PROVIDER_LEDGER_PATH,
        os.O_APPEND | os.O_CREAT | os.O_WRONLY,
        0o600,
    )
    try:
        os.write(descriptor, payload.encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _reserve_budget(state: dict[str, Any], logical_calls: int, provider_attempts: int) -> bool:
    """Reserve budget against the hard caps. Returns False (does not mutate
    state) if the reservation would exceed either cap."""
    return (
        state["cumulative_logical_calls"] + logical_calls <= HARD_CAP_LOGICAL_CALLS
        and state["cumulative_provider_attempts"] + provider_attempts <= HARD_CAP_PROVIDER_ATTEMPTS
    )


def _commit_budget(
    state: dict[str, Any],
    logical_calls: int,
    provider_attempts: int,
    note: str,
    *,
    global_event: dict[str, Any] | None = None,
) -> None:
    state["cumulative_logical_calls"] += logical_calls
    state["cumulative_provider_attempts"] += provider_attempts
    _append_ledger(
        {
            "at": _now_iso(),
            "logical_calls": logical_calls,
            "provider_attempts": provider_attempts,
            "note": note,
            "running_total_logical_calls": state["cumulative_logical_calls"],
            "running_total_provider_attempts": state["cumulative_provider_attempts"],
        }
    )
    if global_event is not None:
        _append_global_provider_ledger(global_event)


# ---------------------------------------------------------------------------
# Stage A: Provider connectivity recovery
# ---------------------------------------------------------------------------


def run_provider_configuration_precheck(profile: Any) -> dict[str, Any]:
    """Section 1: read-only precheck. Never prints the key value, an
    Authorization header, a full environment dump, or a Provider client
    repr -- only presence/length and non-secret identity facts."""

    from tradingagents.llm_clients.api_key_env import get_api_key_env

    result: dict[str, Any] = {"passed": True, "failures": []}

    env_path = REPO_ROOT / ".env"
    result["dotenv_present"] = env_path.exists()
    if not result["dotenv_present"]:
        result["passed"] = False
        result["failures"].append("DOTENV_MISSING")

    key_env_name = get_api_key_env(profile.llm_provider)
    result["credential_env_name"] = key_env_name
    key_value = os.environ.get(key_env_name) if key_env_name else None
    result["key_present"] = bool(key_value)
    result["key_length"] = len(key_value) if key_value else 0
    if not result["key_present"]:
        result["passed"] = False
        result["failures"].append("API_KEY_NOT_LOADED_OR_EMPTY")

    result["profile_id"] = profile.profile_id
    result["provider"] = profile.llm_provider
    result["model"] = profile.quick_think_llm
    if (
        profile.profile_id != STRUCTURED_CLAIM_SHADOW_PROFILE_ID
        or profile.llm_provider != "anthropic"
        or profile.quick_think_llm != "claude-sonnet-4-6"
    ):
        result["passed"] = False
        result["failures"].append("PROVIDER_OR_MODEL_CHANGED")

    hostname, port = _resolve_diagnostic_target(profile)
    result["sanitized_base_url_hostname"] = hostname
    result["port"] = port
    if hostname != "api.anthropic.com":
        result["passed"] = False
        result["failures"].append("UNEXPECTED_BASE_URL_HOSTNAME")

    return result


def _resolve_diagnostic_target(profile: Any) -> tuple[str, int]:
    if profile.backend_url:
        parsed = urlparse(profile.backend_url)
        return parsed.hostname or profile.backend_url, parsed.port or 443
    if profile.llm_provider == "anthropic":
        return "api.anthropic.com", 443
    from tradingagents.llm_clients.openai_client import OPENAI_COMPATIBLE_PROVIDERS

    spec = OPENAI_COMPATIBLE_PROVIDERS.get(profile.llm_provider)
    base_url = spec.base_url if spec else None
    if not base_url:
        return "api.openai.com", 443
    parsed = urlparse(base_url)
    return parsed.hostname or base_url, parsed.port or 443


def run_provider_diagnostic(state: dict[str, Any], profile: Any) -> dict[str, Any]:
    hostname, port = _resolve_diagnostic_target(profile)
    report: dict[str, Any] = {
        "schema_version": "comqutor.phase1_master.provider_connectivity_report.v1",
        "generated_at": _now_iso(),
        "profile_id": profile.profile_id,
        "provider": profile.llm_provider,
        "sanitized_hostname": hostname,
        "port": port,
        "checks": {},
    }

    dns_ok = False
    try:
        addrs = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
        report["checks"]["dns_lookup"] = {"status": "PASS", "resolved_address_count": len(addrs)}
        dns_ok = True
    except OSError as exc:
        report["checks"]["dns_lookup"] = {"status": "FAIL", "error_class": type(exc).__name__}

    tcp_ok = False
    if dns_ok:
        try:
            sock = socket.create_connection((hostname, port), timeout=10)
            sock.close()
            report["checks"]["tcp_connect_443"] = {"status": "PASS"}
            tcp_ok = True
        except OSError as exc:
            report["checks"]["tcp_connect_443"] = {"status": "FAIL", "error_class": type(exc).__name__}
    else:
        report["checks"]["tcp_connect_443"] = {"status": "SKIP", "reason": "dns_lookup did not pass"}

    tls_ok = False
    if tcp_ok:
        try:
            context = ssl.create_default_context()
            with (
                socket.create_connection((hostname, port), timeout=10) as sock,
                context.wrap_socket(sock, server_hostname=hostname) as tls_sock,
            ):
                tls_sock.getpeercert()
            report["checks"]["tls_handshake"] = {"status": "PASS"}
            tls_ok = True
        except (OSError, ssl.SSLError) as exc:
            report["checks"]["tls_handshake"] = {"status": "FAIL", "error_class": type(exc).__name__}
    else:
        report["checks"]["tls_handshake"] = {"status": "SKIP", "reason": "tcp_connect_443 did not pass"}

    proxy_env_present = any(
        os.environ.get(name) for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY")
    )
    report["checks"]["proxy_env_vars_present"] = proxy_env_present
    report["prior_smoke_timeout_evidence"] = {
        "source": "docs/audit_artifacts/phase1b1/real_provider_smoke_result.json",
        "summary": (
            "All 8 real attempts (4 logical calls x 2) timed out at the Gateway's own "
            "15s read-timeout layer -- consistent with either a network-level failure "
            "(no TCP/TLS reachability) or a reachable-but-non-responding endpoint. This "
            "diagnostic determines which."
        ),
    }
    all_pass = dns_ok and tcp_ok and tls_ok
    report["overall"] = "PASS" if all_pass else "FAIL"
    _write_json(CONNECTIVITY_REPORT_PATH, report)
    return {"all_pass": all_pass, "report": report}


def run_provider_probe(state: dict[str, Any], profile: Any) -> dict[str, Any]:
    from comqutor_alpha.structure_engine.week2_llm import DEFAULT_TIMEOUT_SECONDS, call_with_timeout
    from tradingagents.llm_clients import create_llm_client

    if not _reserve_budget(state, 1, 1):
        return {"outcome": "budget_exceeded"}

    try:
        client = create_llm_client(
            provider=profile.llm_provider,
            model=profile.quick_think_llm,
            base_url=profile.backend_url,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            max_retries=0,
        )
        model = client.get_llm()
    except Exception as exc:
        _commit_budget(state, 1, 0, "provider_probe_client_init_failed")
        return {"outcome": "client_init_failed", "error_class": type(exc).__name__}

    probe_prompt = 'Respond with exactly this JSON object and nothing else: {"ok": true}'
    started = _now_iso()
    try:
        response = call_with_timeout(lambda: model.invoke(probe_prompt), DEFAULT_TIMEOUT_SECONDS)
        _commit_budget(state, 1, 1, "provider_probe_response_received")
        response_repr_type = type(response).__name__
        return {
            "outcome": "response_received",
            "started_at": started,
            "completed_at": _now_iso(),
            "response_type": response_repr_type,
        }
    except TimeoutError:
        _commit_budget(state, 1, 1, "provider_probe_timeout")
        return {"outcome": "timeout", "started_at": started, "completed_at": _now_iso()}
    except Exception as exc:
        _commit_budget(state, 1, 1, "provider_probe_error")
        return {"outcome": "error", "error_class": type(exc).__name__, "started_at": started, "completed_at": _now_iso()}


def _exception_http_status(exc: BaseException) -> int | None:
    for candidate in (exc, getattr(exc, "response", None)):
        value = getattr(candidate, "status_code", None)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def _anthropic_qualification_blocker(exc: BaseException) -> str:
    status = _exception_http_status(exc)
    if status in {401, 403}:
        return "BLOCKED_ANTHROPIC_CREDENTIAL_INVALID"
    if status == 404:
        return "BLOCKED_ANTHROPIC_PROFILE_MODEL_INVALID"
    if status is not None and 500 <= status <= 599:
        return "BLOCKED_ANTHROPIC_PROVIDER_UNAVAILABLE"
    if isinstance(exc, TimeoutError):
        return "BLOCKED_ANTHROPIC_PROVIDER_UNAVAILABLE"
    if isinstance(exc, (socket.gaierror, ssl.SSLError, ConnectionError, OSError)):
        return "BLOCKED_ANTHROPIC_NETWORK"
    class_name = type(exc).__name__.lower()
    if any(token in class_name for token in ("connect", "network", "transport", "tls", "dns")):
        return "BLOCKED_ANTHROPIC_NETWORK"
    return "BLOCKED_ANTHROPIC_PROVIDER_UNAVAILABLE"


def run_anthropic_profile_qualification(
    state: dict[str, Any], profile: Any
) -> dict[str, Any]:
    """Perform the one permitted minimal Anthropic credential/model probe."""

    result_path = STATE_DIR / "anthropic_profile_qualification_result.json"
    if result_path.exists():
        saved = json.loads(result_path.read_text(encoding="utf-8"))
        if saved.get("outcome") == "response_received_and_parsed":
            return {**saved, "resumed_from_saved_result": True}

    existing_qualification_events = 0
    if GLOBAL_PROVIDER_LEDGER_PATH.exists():
        existing_qualification_events = sum(
            1
            for line in GLOBAL_PROVIDER_LEDGER_PATH.read_text(encoding="utf-8").splitlines()
            if line
            and json.loads(line).get("stage") == "ANTHROPIC_QUALIFICATION"
        )
    attempt_number = existing_qualification_events + 1
    if attempt_number > 2:
        return {
            "outcome": "blocked",
            "reason_code": "BLOCKED_ANTHROPIC_PROVIDER_UNAVAILABLE",
            "qualification_attempt_limit_reached": True,
        }
    if result_path.exists():
        prior = json.loads(result_path.read_text(encoding="utf-8"))
        prior_path = STATE_DIR / f"anthropic_profile_qualification_attempt_{attempt_number - 1}.json"
        if not prior_path.exists():
            _write_json(prior_path, prior)

    if not _reserve_budget(state, 1, 1):
        return {"outcome": "budget_exceeded"}

    from comqutor_alpha.structure_engine.week2_llm import call_with_timeout
    from tradingagents.llm_clients import create_llm_client

    started_at = _now_iso()
    try:
        client = create_llm_client(
            provider=profile.llm_provider,
            model=profile.quick_think_llm,
            base_url=profile.backend_url,
            timeout=30.0,
            max_retries=0,
        )
        model = client.get_llm()
        response = call_with_timeout(
            lambda: model.invoke(
                'Return exactly one JSON object and no markdown: {"qualification":true}'
            ),
            30.0,
        )
        content = response if isinstance(response, str) else getattr(response, "content", None)
        if not isinstance(content, str):
            raise ValueError("ANTHROPIC_QUALIFICATION_RESPONSE_NOT_TEXT")
        parsed = json.loads(content)
        if not isinstance(parsed, dict) or parsed.get("qualification") is not True:
            raise ValueError("ANTHROPIC_QUALIFICATION_RESPONSE_INVALID")
        result = {
            "schema_version": "comqutor.phase1_master.anthropic_qualification.v1",
            "outcome": "response_received_and_parsed",
            "profile_id": profile.profile_id,
            "provider": profile.llm_provider,
            "model": profile.quick_think_llm,
            "logical_calls": 1,
            "provider_attempts": 1,
            "retry_count": 0,
            "started_at": started_at,
            "completed_at": _now_iso(),
            "raw_output_persisted": False,
            "qualification_attempt_number": attempt_number,
        }
    except Exception as exc:
        result = {
            "schema_version": "comqutor.phase1_master.anthropic_qualification.v1",
            "outcome": "blocked",
            "reason_code": _anthropic_qualification_blocker(exc),
            "error_class": type(exc).__name__,
            "profile_id": profile.profile_id,
            "provider": profile.llm_provider,
            "model": profile.quick_think_llm,
            "logical_calls": 1,
            "provider_attempts": 1,
            "retry_count": 0,
            "started_at": started_at,
            "completed_at": _now_iso(),
            "raw_output_persisted": False,
            "qualification_attempt_number": attempt_number,
        }

    _write_json(
        STATE_DIR / f"anthropic_profile_qualification_attempt_{attempt_number}.json",
        result,
    )
    _write_json(result_path, result)
    state["anthropic_qualification_attempts"] = attempt_number
    _commit_budget(
        state,
        1,
        1,
        "anthropic_profile_qualification",
        global_event={
            "schema_version": "comqutor.phase1_global_provider_call_ledger.v1",
            "event_id": f"phase1_master:anthropic_qualification:attempt:{attempt_number}",
            "recorded_at": _now_iso(),
            "source_phase": "PHASE_1_MASTER",
            "stage": "ANTHROPIC_QUALIFICATION",
            "task": "profile_qualification",
            "profile_id": profile.profile_id,
            "provider": profile.llm_provider,
            "model": profile.quick_think_llm,
            "logical_calls": 1,
            "provider_attempts": 1,
            "outcome": result["outcome"],
            "accounting_confidence": "EXACT",
            "master_contract_budget_counted": True,
        },
    )
    return result


# ---------------------------------------------------------------------------
# Stage B/C/D: historical corpus evaluation (Smoke / Pilot / Core Evaluation)
# ---------------------------------------------------------------------------


def _load_evaluation_corpus() -> dict[str, Any]:
    return json.loads(EVALUATION_CORPUS_PATH.read_text(encoding="utf-8"))


def _target_reports_for_tickers(corpus: dict[str, Any], tickers: tuple[str, ...]) -> list[dict[str, Any]]:
    reports_by_id = {str(r.get("agent_output_id")): r for r in corpus.get("reports") or []}
    coverage_by_ticker: dict[str, dict[str, dict[str, Any]]] = {}
    for entry in corpus.get("coverage") or []:
        coverage_by_ticker.setdefault(str(entry.get("ticker")), {})[str(entry.get("agent_family"))] = entry

    selected: list[dict[str, Any]] = []
    for ticker in tickers:
        families = coverage_by_ticker.get(ticker, {})
        for family in TARGET_FAMILY_ORDER:
            slot = families.get(family, {})
            if not (slot.get("slot_covered") and slot.get("target_slot")):
                continue
            agent_output_id = str(slot.get("selected_agent_output_id") or "")
            report = reports_by_id.get(agent_output_id)
            if report is None or not report.get("eligible_for_phase1_shadow"):
                continue
            selected.append({**report, "ticker": ticker, "agent_family": family})
    return selected


def _load_raw_report(run_id: str, agent_output_id: str) -> dict[str, Any]:
    raw_path = REPO_ROOT / "outputs/runs" / run_id / "raw_agent_outputs.json"
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    for entry in payload.get("agent_outputs") or []:
        if str(entry.get("agent_output_id")) == agent_output_id:
            return entry
    raise ValueError(f"PHASE1_MASTER_REPORT_NOT_FOUND_IN_RAW_OUTPUTS:{agent_output_id}")


def _evaluation_dir(state: dict[str, Any]) -> Path:
    if state["evaluation_dir"]:
        return REPO_ROOT / state["evaluation_dir"]
    prompt_version = state.get("prompt_version_in_use")
    if prompt_version == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4:
        prompt_slug = "anthropic-v4"
    elif prompt_version == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3:
        prompt_slug = "anthropic-v3"
    elif prompt_version == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2:
        prompt_slug = "anthropic-v2"
    else:
        prompt_slug = "anthropic"
    eval_id = (
        f"phase1-master-{prompt_slug}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-"
        f"{uuid.uuid4().hex[:8]}"
    )
    rel = f"outputs/evaluations/{eval_id}"
    state["evaluation_dir"] = rel
    current = state.get("current_provider_evaluation")
    if isinstance(current, dict):
        current["evaluation_dir"] = rel
    return REPO_ROOT / rel


def run_evaluation_batch(state: dict[str, Any], profile: Any, stage_name: str) -> dict[str, Any]:
    corpus = _load_evaluation_corpus()
    tickers = STAGE_TICKERS[stage_name]
    target_reports = _target_reports_for_tickers(corpus, tickers)
    already_called = set(state.get("anthropic_called_report_ids") or [])
    reports_to_call = [r for r in target_reports if str(r["agent_output_id"]) not in already_called]

    if not reports_to_call:
        return {
            "outcome": "nothing_new_to_call",
            "per_report_results": _load_saved_report_results(state, target_reports),
        }

    logical_call_limit = len(reports_to_call)
    provider_attempt_estimate = logical_call_limit * (
        1 + STRUCTURED_CLAIM_SHADOW_MAX_RETRIES
    )
    if not _reserve_budget(state, logical_call_limit, provider_attempt_estimate):
        return {"outcome": "budget_exceeded", "logical_call_limit": logical_call_limit}

    evaluation_dir = _evaluation_dir(state)
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    state["current_provider_evaluation"]["evaluation_dir"] = state["evaluation_dir"]
    batch_id = (
        f"anthropic-{stage_name.lower()}-"
        f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    )
    try:
        gateway, gateway_info = build_phase1_master_provider_gateway(
            profile=profile,
            run_id=batch_id,
            output_root=evaluation_dir,
            logical_call_limit=logical_call_limit,
            semantic_runtime=None,
        )
    except ProviderSmokeAuthorizationError as exc:
        return {"outcome": "gateway_init_failed", "reason_code": exc.reason_code}

    per_report_results: list[dict[str, Any]] = []
    all_comparisons: list[dict[str, Any]] = []
    all_review_rows: list[dict[str, str]] = []

    for report_meta in reports_to_call:
        ticker = str(report_meta["ticker"])
        family = str(report_meta["agent_family"])
        run_id = str(report_meta["source_run_id"])
        agent_output_id = str(report_meta["agent_output_id"])
        agent = str(report_meta.get("agent") or "")
        raw_record = _load_raw_report(run_id, agent_output_id)
        report_text = str(raw_record.get("raw_output") or "")
        report_key = hashlib.sha256(agent_output_id.encode("utf-8")).hexdigest()[:16]
        report_execution_id = f"{batch_id}-{report_key}"
        family_dir = evaluation_dir / "reports" / ticker / family
        result_path = family_dir / "report_result.json"
        runtime_dir = (
            evaluation_dir
            / "semantic_runtime"
            / stage_name.lower()
            / report_key
        )
        if runtime_dir.exists() or result_path.exists():
            return {
                "outcome": "interrupted_report_requires_audit",
                "reason_code": "BLOCKED_ANTHROPIC_INTERRUPTED_REPORT_STATE_AMBIGUOUS",
                "agent_output_id": agent_output_id,
                "per_report_results": per_report_results,
            }
        runtime_dir.mkdir(parents=True, exist_ok=False)
        session = SemanticRuntimeSession(
            run_id=report_execution_id,
            output_directory=runtime_dir,
            execution_mode="shadow",
            provider=profile.llm_provider,
            model=profile.quick_think_llm,
            profile_id=profile.profile_id,
            cache=NullLLMResponseCache(),
        )
        gateway.semantic_runtime = session

        legacy_records = adapt_raw_agent_outputs(
            raw_record, report_execution_id, ticker, llm_gateway=None
        )

        # Which prompt/wire-format actually goes out is driven by the
        # resumable state's own recorded identity, never guessed at call
        # time -- once _switch_structured_claim_shadow_to_prompt_v2/_v3/_v4
        # flips prompt_version_in_use, every subsequent report (Smoke,
        # Pilot, Core alike) uses that prompt, matching the Master task's
        # own "Master uses Prompt vN, continues" requirement.
        using_prompt_v4 = state.get("prompt_version_in_use") == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4
        using_prompt_v3 = state.get("prompt_version_in_use") == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3
        using_prompt_v2 = state.get("prompt_version_in_use") == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2
        call_started = time.monotonic()
        resolution_log: list[dict[str, Any]] = []
        if using_prompt_v4:
            bundle, invoker, candidate_segments, resolution_log = run_real_provider_shadow_smoke_for_report_v4(
                gateway=gateway,
                source_report=report_text,
                run_id=report_execution_id,
                ticker=ticker,
                agent=agent,
                agent_output_id=agent_output_id,
                factor_vocabulary=list(FACTOR_ALIASES.keys()),
            )
        elif using_prompt_v3:
            bundle, invoker, candidate_segments, resolution_log = run_real_provider_shadow_smoke_for_report_v3(
                gateway=gateway,
                source_report=report_text,
                run_id=report_execution_id,
                ticker=ticker,
                agent=agent,
                agent_output_id=agent_output_id,
                factor_vocabulary=list(FACTOR_ALIASES.keys()),
            )
        elif using_prompt_v2:
            bundle, invoker, candidate_segments = run_real_provider_shadow_smoke_for_report_v2(
                gateway=gateway,
                source_report=report_text,
                run_id=report_execution_id,
                ticker=ticker,
                agent=agent,
                agent_output_id=agent_output_id,
                factor_vocabulary=list(FACTOR_ALIASES.keys()),
            )
        else:
            bundle, invoker, candidate_segments = run_real_provider_shadow_smoke_for_report(
                gateway=gateway,
                source_report=report_text,
                run_id=report_execution_id,
                ticker=ticker,
                agent=agent,
                agent_output_id=agent_output_id,
                factor_vocabulary=list(FACTOR_ALIASES.keys()),
                source_metadata={
                    "source_path": raw_record.get("source_path") or "",
                    "source_field": raw_record.get("source_field") or "",
                    "source_refs": [],
                },
            )
        elapsed_ms = max(0.0, (time.monotonic() - call_started) * 1000.0)
        manifest_path = session.finalize_manifest(complete=True)
        manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest_path is not None
            else {}
        )
        comparison = compare_legacy_and_shadow(legacy_records, bundle)
        all_comparisons.append(comparison)

        family_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            family_dir / "source_report_snapshot.json",
            {
                "run_id": report_execution_id,
                "source_run_id": run_id,
                "agent_output_id": agent_output_id,
                "agent": agent,
                "ticker": ticker,
                "report_text": report_text,
                "report_sha256": report_meta.get("report_sha256"),
                "factor_vocabulary": list(FACTOR_ALIASES.keys()),
                "allowed_source_refs": [],
            },
        )
        _write_json(family_dir / "candidate_segments.json", candidate_segments)
        invocation = invoker.last_invocation
        _write_json(
            family_dir / "provider_candidate.json",
            invocation.parsed_output if invocation else None,
        )
        _write_json(family_dir / "shadow_bundle.json", bundle)
        _write_json(family_dir / "validation_report.json", bundle.get("validation_summary") or {})
        _write_json(family_dir / "legacy_claims_snapshot.json", legacy_records)
        _write_json(family_dir / "legacy_vs_shadow_comparison.json", comparison)

        row_batch = build_blank_review_rows(comparison=comparison, legacy_outputs=legacy_records, shadow_bundle=bundle)
        all_review_rows.extend(row_batch)

        report_result = {
            "ticker": ticker,
            "agent_family": family,
            "agent_output_id": agent_output_id,
            "provider_status": invocation.provider_status if invocation else "not_called",
            "provider_completed_response": invocation.response_received if invocation else False,
            "provider_attempt_count": invocation.provider_attempt_count if invocation else 0,
            "retry_count": invocation.retry_count if invocation else 0,
            "attempt_history": (
                [dict(item) for item in invocation.attempt_history] if invocation else []
            ),
            "error_code": invocation.error_code if invocation else None,
            "validation_accepted": invocation.validation_accepted if invocation else False,
            "validation_status": (
                "accepted"
                if invocation and invocation.validation_accepted
                else ("rejected" if invocation and invocation.validation_attempted else "not_run")
            ),
            "shadow_status": (bundle.get("validation_summary") or {}).get("status"),
            "claim_count": len(bundle.get("claims") or []),
            "abstention_count": len(bundle.get("abstentions") or []),
            "valid_empty": (bundle.get("validation_summary") or {}).get("status")
            == "empty_valid_output",
            "latency_ms": elapsed_ms,
            "token_usage": dict(invocation.token_usage) if invocation and invocation.token_usage else None,
            "profile_id": profile.profile_id,
            "provider": profile.llm_provider,
            "model": profile.quick_think_llm,
            "prompt_version": (
                STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4
                if using_prompt_v4
                else STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3
                if using_prompt_v3
                else STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2
                if using_prompt_v2
                else STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION
            ),
            "prompt_sha256": (
                STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256
                if using_prompt_v4
                else STRUCTURED_OUTPUT_SHADOW_PROMPT_V3_SHA256
                if using_prompt_v3
                else STRUCTURED_OUTPUT_SHADOW_PROMPT_V2_SHA256
                if using_prompt_v2
                else STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256
            ),
            "quote_resolution_summary": (
                summarize_resolution_log_v4(resolution_log)
                if using_prompt_v4
                else summarize_resolution_log_v3(resolution_log)
                if using_prompt_v3
                else None
            ),
            "semantic_manifest": manifest,
        }
        per_report_results.append(report_result)
        _write_json(result_path, report_result)

        already_called.add(agent_output_id)
        state.setdefault("anthropic_called_report_ids", []).append(agent_output_id)

        # Commit budget and persist state after EVERY report, not just at
        # batch end -- an interrupted process (shell timeout, crash) must
        # never lose track of reports already called, or a later --resume
        # would re-call them and burn budget twice (the exact failure mode
        # observed in the Phase 1B.1 interrupted-attempt incident).
        _commit_budget(
            state,
            1,
            report_result["provider_attempt_count"],
            f"anthropic_{stage_name.lower()}_report:{agent_output_id}",
            global_event={
                "schema_version": "comqutor.phase1_global_provider_call_ledger.v1",
                # Includes prompt_version_in_use, not just agent_output_id:
                # the same 4 historical reports are legitimately re-attempted
                # under a new prompt after a v1->v2 switch, and
                # _append_global_provider_ledger dedupes by event_id alone --
                # without the prompt version, the v2 attempt's real usage
                # would silently collide with (and be dropped in favor of)
                # the already-recorded v1 attempt's event_id, undercounting
                # real Provider spend in the append-only global ledger.
                "event_id": (
                    f"phase1_master:anthropic:{agent_output_id}:{state['prompt_version_in_use']}"
                ),
                "recorded_at": _now_iso(),
                "source_phase": "PHASE_1_MASTER",
                "stage": stage_name,
                "task": "structured_claim_shadow",
                "report_id": agent_output_id,
                "prompt_version": state["prompt_version_in_use"],
                "ticker": ticker,
                "agent_family": family,
                "profile_id": profile.profile_id,
                "provider": profile.llm_provider,
                "model": profile.quick_think_llm,
                "logical_calls": 1,
                "provider_attempts": report_result["provider_attempt_count"],
                "outcome": report_result["provider_status"],
                "accounting_confidence": "EXACT",
                "master_contract_budget_counted": True,
            },
        )
        save_state(state)

    return {
        "outcome": "completed",
        "batch_id": batch_id,
        "per_report_results": _load_saved_report_results(state, target_reports),
        "review_rows": all_review_rows,
        "comparisons": all_comparisons,
        "gateway_info": gateway_info.__dict__,
    }


def _load_saved_report_results(
    state: dict[str, Any], target_reports: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    evaluation_dir = _evaluation_dir(state)
    results: list[dict[str, Any]] = []
    for report_meta in target_reports:
        result_path = (
            evaluation_dir
            / "reports"
            / str(report_meta["ticker"])
            / str(report_meta["agent_family"])
            / "report_result.json"
        )
        if result_path.exists():
            results.append(json.loads(result_path.read_text(encoding="utf-8")))
    return results


def _response_received(result: dict[str, Any]) -> bool:
    return bool(result.get("provider_completed_response"))


BLOCKED_PROVIDER_MODEL_UNSUITABLE_FOR_LONG_STRUCTURED_TASK = (
    "BLOCKED_PROVIDER_MODEL_UNSUITABLE_FOR_LONG_STRUCTURED_TASK"
)
BLOCKED_PROVIDER_LATENCY_UNSTABLE = "BLOCKED_PROVIDER_LATENCY_UNSTABLE"


def smoke_engineering_gate(per_report_results: list[dict[str, Any]]) -> dict[str, Any]:
    responded = sum(1 for r in per_report_results if _response_received(r))
    total = len(per_report_results)
    every_result_has_status = all(bool(r.get("provider_status")) for r in per_report_results)
    all_zero_admission = responded > 0 and all(not r.get("validation_accepted") for r in per_report_results)
    all_timeout = all(r.get("provider_status") == "timeout" for r in per_report_results)
    meets_3_of_4 = responded >= 3 or (total < 4 and responded == total)
    reproducible_terminal_outcomes = sum(
        1
        for result in per_report_results
        if result.get("validation_accepted")
        or result.get("shadow_status") in {"empty_valid_output", "abstained"}
    )
    meets_2_of_4_reproducible_outcomes = reproducible_terminal_outcomes >= 2

    outcome_reason_code: str | None = None
    if not meets_3_of_4:
        outcome_reason_code = "BLOCKED_ANTHROPIC_PROVIDER_RELIABILITY"

    return {
        "responded_count": responded,
        "total_count": total,
        "meets_3_of_4_threshold": meets_3_of_4,
        "reproducible_terminal_outcome_count": reproducible_terminal_outcomes,
        "meets_2_of_4_reproducible_outcome_target": meets_2_of_4_reproducible_outcomes,
        "every_result_has_explicit_status": every_result_has_status,
        "all_calls_timed_out": all_timeout,
        "output_admission_rate_zero": all_zero_admission,
        "outcome_reason_code": outcome_reason_code,
        "semantic_quality_warning": (
            None
            if meets_2_of_4_reproducible_outcomes
            else "FEWER_THAN_TWO_VALID_OR_ABSTAINED_OUTPUTS; continue only as evaluation data"
        ),
    }


def v3_evidence_alignment_gate(per_report_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Phase 1 Master evidence-alignment fix Smoke gate (v3 only): re-derives,
    from each report's own persisted ``quote_resolution_summary``, that no
    ACCEPTED report ever admitted a fabricated (``NO_EXACT_MATCH``) or
    unresolved (``AMBIGUOUS_MULTIPLE_MATCH``/``INVALID_QUOTE``) quote.

    This should already be structurally impossible: an accepted bundle's
    spans have all already passed ``validate_shadow_bundle``'s own exact-
    match/type check by construction (an unresolved quote produces
    ``start=None, end=None``, which the unchanged validator rejects,
    failing the WHOLE bundle -- see
    ``structured_output_shadow_v3.normalize_v3_proposal_to_canonical_bundle``).
    This gate is therefore an independent, defense-in-depth confirmation of
    that invariant, not the primary enforcement mechanism -- if it ever
    fails, that means the invariant itself broke somewhere, which is exactly
    why this stops the Master (``BLOCKED_V3_EVIDENCE_ALIGNMENT_UNSAFE``)
    rather than being auto-retryable.
    """

    fabricated = 0
    unresolved = 0
    for result in per_report_results:
        if result.get("shadow_status") != "accepted":
            continue
        summary = result.get("quote_resolution_summary") or {}
        fabricated += int(summary.get("no_exact_match") or 0)
        unresolved += int(summary.get("ambiguous_multiple_match") or 0) + int(
            summary.get("invalid_quote") or 0
        )

    zero_fabricated_quote_admitted = fabricated == 0
    zero_unresolved_quote_admitted = unresolved == 0
    return {
        "fabricated_quote_count_in_accepted_reports": fabricated,
        "unresolved_quote_count_in_accepted_reports": unresolved,
        "zero_fabricated_quote_admitted": zero_fabricated_quote_admitted,
        "zero_unresolved_quote_admitted": zero_unresolved_quote_admitted,
        "pass": zero_fabricated_quote_admitted and zero_unresolved_quote_admitted,
    }


def build_provider_stability_summary(
    state: dict[str, Any], replay_audit: dict[str, Any]
) -> dict[str, Any]:
    corpus = _load_evaluation_corpus()
    targets = _target_reports_for_tickers(corpus, STAGE_TICKERS["CORE_EVALUATION"])
    results = _load_saved_report_results(state, targets)
    total = len(results)
    completed = sum(1 for item in results if _response_received(item))
    timeouts = sum(1 for item in results if item.get("provider_status") == "timeout")
    transport_errors = sum(
        1
        for item in results
        if item.get("provider_status") == "provider_error"
        and not item.get("provider_completed_response")
    )
    retry_reports = sum(1 for item in results if int(item.get("retry_count") or 0) > 0)
    latencies = sorted(float(item.get("latency_ms") or 0.0) for item in results)
    p95_latency = latencies[min(len(latencies) - 1, int((len(latencies) - 1) * 0.95))] if latencies else None

    http_429_attempts = 0
    http_5xx_attempts = 0
    for item in results:
        for attempt in item.get("attempt_history") or []:
            http_429_attempts += int(attempt.get("retry_reason") == "HTTP_429")
            http_5xx_attempts += int(attempt.get("retry_reason") == "HTTP_5XX")

    family_rates: dict[str, float] = {}
    for family in TARGET_FAMILY_ORDER:
        family_results = [item for item in results if item.get("agent_family") == family]
        family_rates[family] = (
            sum(1 for item in family_results if _response_received(item)) / len(family_results)
            if family_results
            else 0.0
        )

    token_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    token_usage_available = False
    for item in results:
        usage = item.get("token_usage")
        if not isinstance(usage, dict):
            continue
        for key in token_totals:
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                token_totals[key] += value
                token_usage_available = True

    replay_entries = replay_audit.get("checks", {}).get("per_report", [])
    accepted_replay_entries = [
        item for item in replay_entries if item.get("validation_status") == "accepted"
    ]
    accepted_replay_pass = all(
        item.get("replay_status") == "PASS" for item in accepted_replay_entries
    )
    completed_rate = completed / total if total else 0.0
    failure_rate = (timeouts + transport_errors) / total if total else 1.0
    no_duplicate_calls = len(state.get("anthropic_called_report_ids") or []) == len(
        set(state.get("anthropic_called_report_ids") or [])
    )
    operational_gate = {
        "provider_completed_response_rate_pass": completed_rate >= 0.90,
        "timeout_plus_transport_error_rate_pass": failure_rate <= 0.10,
        "all_agent_family_response_rates_pass": all(rate >= 0.75 for rate in family_rates.values()),
        "no_silent_retry_pass": all(
            len(item.get("attempt_history") or []) == int(item.get("provider_attempt_count") or 0)
            for item in results
        ),
        "no_duplicate_logical_calls_pass": no_duplicate_calls,
        "accepted_output_replay_pass": accepted_replay_pass,
    }
    return {
        "schema_version": "comqutor.phase1_master.provider_stability_summary.v1",
        "profile_id": STRUCTURED_CLAIM_SHADOW_PROFILE_ID,
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "report_count": total,
        "provider_completed_response_count": completed,
        "provider_completed_response_rate": completed_rate,
        "timeout_count": timeouts,
        "timeout_rate": timeouts / total if total else 0.0,
        "transport_error_count": transport_errors,
        "timeout_plus_transport_error_rate": failure_rate,
        "http_429_attempt_count": http_429_attempts,
        "http_5xx_attempt_count": http_5xx_attempts,
        "transient_retry_report_count": retry_reports,
        "transient_retry_rate": retry_reports / total if total else 0.0,
        "median_latency_ms": statistics.median(latencies) if latencies else None,
        "p95_latency_ms": p95_latency,
        "token_usage": token_totals if token_usage_available else None,
        "cost": None,
        "accepted_count": sum(1 for item in results if item.get("shadow_status") == "accepted"),
        "rejected_count": sum(1 for item in results if item.get("shadow_status") == "validation_rejected"),
        "abstained_count": sum(1 for item in results if item.get("shadow_status") == "abstained"),
        "valid_empty_count": sum(1 for item in results if item.get("shadow_status") == "empty_valid_output"),
        "agent_family_completed_response_rates": family_rates,
        "operational_gate": operational_gate,
        "operational_gate_pass": all(operational_gate.values()),
    }


def render_final_evaluation_bundle(state: dict[str, Any], batch: dict[str, Any]) -> None:
    evaluation_dir = _evaluation_dir(state)
    corpus = _load_evaluation_corpus()
    all_target = _target_reports_for_tickers(corpus, STAGE_TICKERS["CORE_EVALUATION"])

    all_comparisons: list[dict[str, Any]] = []
    all_review_rows: list[dict[str, str]] = []
    for report_meta in all_target:
        ticker = str(report_meta["ticker"])
        family = str(report_meta["agent_family"])
        family_dir = evaluation_dir / "reports" / ticker / family
        comparison_path = family_dir / "legacy_vs_shadow_comparison.json"
        bundle_path = family_dir / "shadow_bundle.json"
        legacy_path = family_dir / "legacy_claims_snapshot.json"
        if not (comparison_path.exists() and bundle_path.exists() and legacy_path.exists()):
            continue
        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        legacy_records = json.loads(legacy_path.read_text(encoding="utf-8"))
        all_comparisons.append(comparison)
        all_review_rows.extend(
            build_blank_review_rows(comparison=comparison, legacy_outputs=legacy_records, shadow_bundle=bundle)
        )

    replay_audit = verify_phase1_master_shadow_exact_replay(evaluation_dir)
    _write_json(evaluation_dir / "shadow_exact_replay_audit.json", replay_audit)
    for entry in replay_audit["checks"].get("per_report", []):
        ticker = entry.get("ticker")
        family = entry.get("agent_family")
        if not ticker or not family:
            continue
        _write_json(evaluation_dir / "reports" / ticker / family / "exact_replay_audit.json", entry)

    review_csv = render_blank_review_csv(all_review_rows)
    (evaluation_dir / "phase1_human_review.csv").write_text(review_csv, encoding="utf-8")
    (evaluation_dir / "phase1_human_review_instructions.md").write_text(_review_instructions_text(), encoding="utf-8")

    _write_json(
        evaluation_dir / "phase1_automatic_diagnostics.json",
        {
            "schema_version": "comqutor.phase1_master.automatic_diagnostics.v1",
            "generated_at": _now_iso(),
            "report_count": len(all_target),
            "review_row_count": len(all_review_rows),
            "note": "Diagnostic signals only -- not a substitute for human semantic judgment.",
        },
    )
    _write_json(
        evaluation_dir / "evaluation_metadata.json",
        {
            "schema_version": "comqutor.phase1_master.evaluation_metadata.v1",
            "generated_at": _now_iso(),
            "research_profile_id": state["structured_claim_shadow_profile_id"],
            "provider": state["structured_claim_shadow_provider"],
            "model": state["structured_claim_shadow_model"],
            "prompt_version": state["prompt_version_in_use"],
            "prompt_sha256": state["prompt_sha256_in_use"],
            "report_count": len(all_target),
            "null_cache": True,
            "human_labels_created": False,
            "semantic_quality": (
                "UNPROVEN_V4"
                if state["prompt_version_in_use"] == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4
                else "UNPROVEN_V3"
                if state["prompt_version_in_use"] == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3
                else "UNPROVEN"
            ),
            "production_authority": "LEGACY_ADAPTER",
        },
    )
    _write_json(
        evaluation_dir / "artifact_manifest.json",
        {
            "schema_version": "comqutor.phase1_master.artifact_manifest.v1",
            "generated_at": _now_iso(),
            "files": sorted(str(p.relative_to(evaluation_dir)) for p in evaluation_dir.rglob("*") if p.is_file()),
        },
    )


def _review_instructions_text() -> str:
    return """# Phase 1 Human Review Instructions

For each row: open source_report_snapshot.json for the cited report, compare
the Legacy claim (if any) against the Shadow claim (if any), and judge:

- Claim boundary: correct / too_broad / too_narrow / wrong
- Evidence pairing: correct / partially_supported / unsupported / wrong_span
- Semantic fidelity: correct / negation_reversed / attribution_reversed /
  modality_error / temporal_error / other_error
- Overall disposition: accept / accept_with_minor_edit / reject
- Severity: none / minor / major / critical

Leave review_label/severity/reviewer/notes blank until you have made your own
judgment. "uncertain" is an acceptable label -- do not force a conclusion you
do not hold. Do not use any Provider or automated output to fill these
fields; human_labels_created stays false until this file is genuinely
completed by a human reviewer.
"""


# ---------------------------------------------------------------------------
# Human review CSV validation + Quality Gate scoring (pure functions)
# ---------------------------------------------------------------------------

APPROVED_DISPOSITIONS = {"accept", "accept_with_minor_edit", "reject", "uncertain"}
APPROVED_SEVERITIES = {"none", "minor", "major", "critical"}
APPROVED_FIDELITY = {
    "correct",
    "negation_reversed",
    "attribution_reversed",
    "modality_error",
    "temporal_error",
    "other_error",
    "uncertain",
}
APPROVED_PAIRING = {"correct", "partially_supported", "unsupported", "wrong_span", "uncertain"}
APPROVED_BOUNDARY = {"correct", "too_broad", "too_narrow", "wrong", "uncertain"}


def validate_human_review_csv(original_rows: list[dict[str, str]], csv_path: Path) -> dict[str, Any]:
    text = csv_path.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text))
    completed_rows = list(reader)
    if reader.fieldnames and "overall_disposition" in reader.fieldnames:
        return _validate_human_review_v2_csv(original_rows, completed_rows)

    original_ids = {row["review_row_id"] for row in original_rows}
    completed_ids = {row["review_row_id"] for row in completed_rows}

    errors: list[str] = []
    if len(completed_ids) != len(completed_rows):
        errors.append("duplicate_review_row_id")
    if original_ids - completed_ids:
        errors.append(f"missing_rows:{len(original_ids - completed_ids)}")
    if completed_ids - original_ids:
        errors.append(f"unexpected_new_rows:{len(completed_ids - original_ids)}")

    for row in completed_rows:
        if not row.get("reviewer", "").strip():
            errors.append(f"empty_reviewer:{row.get('review_row_id')}")
        disposition = row.get("review_label", "").strip()
        if disposition and disposition not in APPROVED_DISPOSITIONS:
            errors.append(f"disposition_not_in_vocabulary:{row.get('review_row_id')}:{disposition}")
        severity = row.get("severity", "").strip()
        if severity and severity not in APPROVED_SEVERITIES:
            errors.append(f"severity_not_in_vocabulary:{row.get('review_row_id')}:{severity}")

    return {"valid": not errors, "errors": errors, "row_count": len(completed_rows), "rows": completed_rows}


def _validate_human_review_v2_csv(
    original_rows: list[dict[str, str]],
    completed_rows: list[dict[str, str]],
) -> dict[str, Any]:
    """Validate the self-contained one-row-per-Claim v2 review packet.

    Every persisted semantic/source column is immutable.  Only the explicit
    human-review fields may be completed, and their vocabularies are closed.
    The returned compatibility aliases let the existing downstream quality
    gate consume the v2 dispositions without changing semantic authority.
    """

    errors: list[str] = []
    original_by_id = {row.get("review_row_id", ""): row for row in original_rows}
    completed_by_id = {row.get("review_row_id", ""): row for row in completed_rows}
    if len(original_by_id) != len(original_rows):
        errors.append("original_template_duplicate_review_row_id")
    if len(completed_by_id) != len(completed_rows):
        errors.append("duplicate_review_row_id")

    original_ids = set(original_by_id)
    completed_ids = set(completed_by_id)
    if original_ids - completed_ids:
        errors.append(f"missing_rows:{len(original_ids - completed_ids)}")
    if completed_ids - original_ids:
        errors.append(f"unexpected_new_rows:{len(completed_ids - original_ids)}")

    normalized_rows: list[dict[str, str]] = []
    required_judgments = tuple(HUMAN_REVIEW_V2_ALLOWED_VALUES)
    for row in completed_rows:
        row_id = row.get("review_row_id", "")
        original = original_by_id.get(row_id)
        if original is None:
            continue
        for field, original_value in original.items():
            if field not in HUMAN_REVIEW_V2_FIELDS and row.get(field, "") != original_value:
                errors.append(f"immutable_field_changed:{row_id}:{field}")

        for field in required_judgments:
            value = row.get(field, "").strip()
            if not value:
                errors.append(f"empty_review_field:{row_id}:{field}")
            elif value not in HUMAN_REVIEW_V2_ALLOWED_VALUES[field]:
                errors.append(f"review_value_not_in_vocabulary:{row_id}:{field}:{value}")
        if not row.get("reviewer", "").strip():
            errors.append(f"empty_reviewer:{row_id}")
        if not row.get("review_timestamp", "").strip():
            errors.append(f"empty_review_timestamp:{row_id}")

        normalized = dict(row)
        normalized["review_label"] = {
            "ACCEPT": "accept",
            "ACCEPT_WITH_MINOR_ISSUE": "accept_with_minor_edit",
            "REJECT": "reject",
        }.get(row.get("overall_disposition", "").strip(), "")
        normalized["severity"] = row.get("severity", "").strip().lower()
        normalized_rows.append(normalized)

    return {
        "valid": not errors,
        "errors": errors,
        "row_count": len(completed_rows),
        "rows": normalized_rows,
        "template_version": "v2",
    }


def compute_quality_gate(completed_rows: list[dict[str, str]], safety_gate_results: dict[str, Any]) -> dict[str, Any]:
    total = len(completed_rows) or 1
    accept_like = sum(1 for r in completed_rows if r.get("review_label") in {"accept", "accept_with_minor_edit"})
    critical = sum(1 for r in completed_rows if r.get("severity") == "critical")
    major = sum(1 for r in completed_rows if r.get("severity") in {"major", "critical"})

    human_gates = {
        "disposition_accept_rate": accept_like / total,
        "disposition_accept_rate_pass": (accept_like / total) >= 0.85,
        "critical_severity_errors": critical,
        "critical_severity_errors_pass": critical == 0,
        "major_plus_critical_rate": major / total,
        "major_plus_critical_rate_pass": (major / total) <= 0.05,
    }
    safety_pass = all(bool(v) for v in safety_gate_results.values())
    human_pass = all(v for k, v in human_gates.items() if k.endswith("_pass"))
    overall_pass = safety_pass and human_pass
    return {
        "safety_gates": safety_gate_results,
        "safety_gates_pass": safety_pass,
        "human_gates": human_gates,
        "human_gates_pass": human_pass,
        "overall_pass": overall_pass,
    }


# ---------------------------------------------------------------------------
# Main driver
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true", default=False)
    parser.add_argument("--human-review-csv", default=None)
    parser.add_argument(
        "--apply-v3-evidence-alignment-fix",
        action="store_true",
        default=False,
        help=(
            "One-time, human-triggered switch from prompt v2 to the v3 "
            "evidence-alignment fix while WAITING_FOR_HUMAN_REVIEW under "
            "v2 (human/AI review found systemic Claim-to-Evidence "
            "misalignment in the v2 evaluation). Never inferred "
            "automatically -- the finding that motivates it comes from "
            "review conducted outside this resumable state machine."
        ),
    )
    parser.add_argument(
        "--apply-v4-markdown-formatting-fix",
        action="store_true",
        default=False,
        help=(
            "One-time, human-triggered switch from prompt v3 to the v4 "
            "markdown-formatting-fidelity fix while WAITING_FOR_HUMAN_REVIEW "
            "under v3 (v3's real evaluation rejected 33.3% of reports; "
            "root-cause analysis found 94% of the underlying failures "
            "traced to the model dropping the report's own Markdown "
            "emphasis characters when quoting). Never inferred "
            "automatically."
        ),
    )
    parser.add_argument(
        "--max-stage-transitions",
        type=int,
        default=None,
        help=(
            "Optional cap on state transitions processed by this single invocation "
            "(does not affect the resumable ledger/state file -- a later --resume "
            "with no cap continues exactly where this one stopped)."
        ),
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if not args.resume:
        print("PHASE1_MASTER: pass --resume to continue the Master Task")
        return 1

    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env", override=False)
    state = load_state()
    try:
        routed_profile_id = profile_id_for_semantic_task("structured_claim_shadow")
        if routed_profile_id != state["structured_claim_shadow_profile_id"]:
            raise ResearchProfileError("RESEARCH_PROFILE_INVALID")
        profile = get_research_profile(routed_profile_id)
    except ResearchProfileError:
        transition(state, "BLOCKED", {"blocked_reason_code": "BLOCKED_RESEARCH_PROFILE_INVALID"})
        state["blocked_reason_code"] = "BLOCKED_RESEARCH_PROFILE_INVALID"
        save_state(state)
        print("BLOCKED_RESEARCH_PROFILE_INVALID")
        return 0

    precheck = run_provider_configuration_precheck(profile)
    print(f"PROFILE_ID={precheck['profile_id']}")
    print(f"PROVIDER={precheck['provider']}")
    print(f"MODEL={precheck['model']}")
    print(f"CREDENTIAL_ENV_NAME={precheck['credential_env_name']}")
    print(f"KEY_PRESENT={str(precheck['key_present']).lower()}")
    print(f"KEY_LENGTH={precheck['key_length']}")
    print(f"SANITIZED_HOSTNAME={precheck['sanitized_base_url_hostname']}")
    _write_json(STATE_DIR / "provider_configuration_precheck.json", precheck)
    if not precheck["passed"]:
        blocker = (
            "BLOCKED_ANTHROPIC_CREDENTIAL_MISSING"
            if "API_KEY_NOT_LOADED_OR_EMPTY" in precheck["failures"]
            else "BLOCKED_RESEARCH_PROFILE_INVALID"
        )
        state["blocked_reason_code"] = blocker
        transition(state, "BLOCKED", {"precheck_failures": precheck["failures"]})
        print(blocker)
        print(f"failures: {precheck['failures']}")
        return 0

    approved = os.environ.get(APPROVAL_ENV_VAR, "") == "true"
    data_egress_approved = os.environ.get(DATA_EGRESS_APPROVAL_ENV_VAR, "") == "true"
    print(f"current_state: {state['current_state']}")
    print(f"cumulative_logical_calls: {state['cumulative_logical_calls']}/{HARD_CAP_LOGICAL_CALLS}")
    print(f"cumulative_provider_attempts: {state['cumulative_provider_attempts']}/{HARD_CAP_PROVIDER_ATTEMPTS}")
    print(f"{APPROVAL_ENV_VAR} set to 'true': {approved}")
    print(
        f"{DATA_EGRESS_APPROVAL_ENV_VAR} set to 'true': "
        f"{data_egress_approved}"
    )

    transitions_this_invocation = 0
    while True:
        if args.max_stage_transitions is not None and transitions_this_invocation >= args.max_stage_transitions:
            print(f"PHASE1_MASTER: stopping after {transitions_this_invocation} transition(s) (--max-stage-transitions)")
            print(f"current_state: {state['current_state']}")
            return 0
        transitions_this_invocation += 1
        current = state["current_state"]

        if current == "BLOCKED" and state.get("blocked_reason_code") == (
            "BLOCKED_PROVIDER_MODEL_UNSUITABLE_FOR_LONG_STRUCTURED_TASK"
        ):
            state["blocked_reason_code"] = None
            transition(
                state,
                "ANTHROPIC_QUALIFICATION",
                {
                    "root_blocker_corrected": True,
                    "previous_provider": "deepseek",
                    "current_provider": "anthropic",
                    "deepseek_diagnostics_repeated": False,
                },
            )
            continue

        if (
            current == "BLOCKED"
            and state.get("blocked_reason_code") == "BLOCKED_ANTHROPIC_NETWORK"
            and approved
            and data_egress_approved
        ):
            qualification_event_count = 0
            if GLOBAL_PROVIDER_LEDGER_PATH.exists():
                qualification_event_count = sum(
                    1
                    for line in GLOBAL_PROVIDER_LEDGER_PATH.read_text(
                        encoding="utf-8"
                    ).splitlines()
                    if line
                    and json.loads(line).get("stage") == "ANTHROPIC_QUALIFICATION"
                )
            if qualification_event_count < 2:
                state["blocked_reason_code"] = None
                transition(
                    state,
                    "ANTHROPIC_QUALIFICATION",
                    {
                        "explicit_user_data_egress_authorization": True,
                        "authorized_payload_scope": (
                            "24 frozen historical reports plus frozen structured-claim "
                            "Shadow prompt and candidate segments"
                        ),
                        "authorized_destination": (
                            "api.anthropic.com / claude-sonnet-4-6"
                        ),
                        "prior_sandbox_qualification_preserved": True,
                    },
                )
                continue

        if (
            current == "BLOCKED"
            and state.get("blocked_reason_code") == "BLOCKED_ANTHROPIC_PROVIDER_RELIABILITY"
            and state.get("prompt_version_in_use") != STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2
        ):
            _switch_structured_claim_shadow_to_prompt_v2(state)
            transition(
                state,
                "SMOKE",
                {
                    "prompt_size_root_cause_fix_applied": True,
                    "previous_prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
                    "new_prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2,
                    "audit_artifacts_dir": "docs/audit_artifacts/phase1_master/prompt_audit/",
                    "measured_v1_request_chars": 98633,
                    "measured_v2_request_chars": 18874,
                    "reduction_pct": 80.86,
                    "prior_anthropic_smoke_reports_voided_and_will_be_reattempted": True,
                },
            )
            continue

        if current == "FAIL" and state.get("fail_reason_code") == "FAIL_ACCEPTED_OUTPUT_EXACT_REPLAY":
            # docs/audit_artifacts/phase1_master/prompt_audit/
            # v2_json_format_diagnostic_findings.json: this FAIL was caused
            # by structured_output_shadow_replay.py's exact-replay verifier
            # hardcoding a v1-only prompt-identity allowlist -- a bug in
            # THIS repo's own verifier, not a real data-integrity failure of
            # the persisted artifacts. Re-run the now-fixed verifier
            # read-only against the SAME unmodified real artifacts before
            # doing anything else: only if it now genuinely passes do we
            # treat this as the verifier bug (never silently clear a FAIL
            # that is still failing under the corrected verifier).
            prior_dir = _evaluation_dir(state)
            recheck = verify_phase1_master_shadow_exact_replay(prior_dir)
            if recheck["final_status"] != "PASS":
                print("FAIL_ACCEPTED_OUTPUT_EXACT_REPLAY")
                print(
                    "PHASE1_MASTER: exact replay still fails after the verifier fix -- "
                    "this is a genuine unresolved FAIL, not auto-cleared."
                )
                print(json.dumps(recheck["reason_codes"], indent=2))
                return 0
            # The old batch's own per-report results are 0/4 accepted --
            # all 4 predate the separately-diagnosed and now-fixed
            # markdown-fence JSON-parsing defect
            # (_MarkdownFenceStrippingModel). Re-deriving the Smoke gate
            # from that stale, known-bad data and pushing forward to Pilot
            # would waste real Provider budget on reports we already know
            # would fail the same way. The honest action is a genuine
            # Smoke retry -- new real Provider calls -- now that the actual
            # fix is in place, not resurrecting old failed output.
            void_dir = _void_evaluation_dir_and_reset_for_retry(
                state,
                terminal_note=(
                    "FAIL_ACCEPTED_OUTPUT_EXACT_REPLAY (verifier false positive, fixed; "
                    "underlying reports were also pre-markdown-fence-fix and would not "
                    "have been usable regardless)"
                ),
            )
            state["fail_reason_code"] = None
            transition(
                state,
                "SMOKE",
                {
                    "recovered_from_exact_replay_verifier_false_positive": True,
                    "verifier_fix": "structured_output_shadow_replay.py KNOWN_PROMPT_VERSIONS/KNOWN_PROMPT_HASHES now recognize both frozen v1 and v2 prompt identities instead of hardcoding only v1",
                    "reverify_status_against_old_artifacts": recheck["final_status"],
                    "separately_fixed_json_format_defect": "_MarkdownFenceStrippingModel (comqutor_alpha/structure_engine/structured_output_shadow_provider.py) -- see v2_json_format_diagnostic_findings.json",
                    "void_evaluation_dir": void_dir,
                },
            )
            continue

        if (
            current == "WAITING_FOR_HUMAN_REVIEW"
            and args.apply_v3_evidence_alignment_fix
            and state.get("prompt_version_in_use") == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2
        ):
            _switch_structured_claim_shadow_to_prompt_v3(state)
            transition(
                state,
                "SMOKE",
                {
                    "evidence_alignment_fix_applied": True,
                    "previous_prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V2,
                    "new_prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3,
                    "v2_engineering_reliability": "PASS",
                    "v2_semantic_evidence_alignment": "FAIL",
                    "prior_v2_evaluation_preserved": True,
                },
            )
            continue

        if (
            current == "WAITING_FOR_HUMAN_REVIEW"
            and args.apply_v4_markdown_formatting_fix
            and state.get("prompt_version_in_use") == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3
        ):
            _switch_structured_claim_shadow_to_prompt_v4(state)
            transition(
                state,
                "SMOKE",
                {
                    "markdown_formatting_fix_applied": True,
                    "previous_prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3,
                    "new_prompt_version": STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4,
                    "v3_engineering_reliability": "PASS",
                    "v3_evidence_alignment_safety": "PASS",
                    "v3_markdown_formatting_fidelity": "PARTIAL",
                    "prior_v3_evaluation_preserved": True,
                },
            )
            continue

        if current in ("COMPLETE", "BLOCKED", "FAIL"):
            print(f"PHASE1_MASTER: {current}")
            return 0

        if current == "WAITING_FOR_HUMAN_REVIEW":
            if not args.human_review_csv:
                print("PHASE1_MASTER: WAITING_FOR_HUMAN_REVIEW -- supply --human-review-csv to continue")
                return 0
            evaluation_dir = _evaluation_dir(state)
            v4_template = evaluation_dir / "phase1_human_review_v4.csv"
            v3_template = evaluation_dir / "phase1_human_review_v3.csv"
            v2_template = evaluation_dir / "phase1_human_review_v2.csv"
            if v4_template.is_file():
                review_template = v4_template
            elif v3_template.is_file():
                review_template = v3_template
            elif v2_template.is_file():
                review_template = v2_template
            else:
                review_template = evaluation_dir / "phase1_human_review.csv"
            original_rows = list(
                csv.DictReader(
                    io.StringIO(review_template.read_text(encoding="utf-8"))
                )
            )
            validation = validate_human_review_csv(original_rows, Path(args.human_review_csv))
            if not validation["valid"]:
                print("PHASE1_MASTER: human review CSV failed validation")
                for err in validation["errors"]:
                    print(f"  {err}")
                return 1
            state["human_review_csv_path"] = str(Path(args.human_review_csv).resolve())
            transition(state, "QUALITY_GATE", {"row_count": validation["row_count"]})
            continue

        if current == "PROVIDER_DIAGNOSTIC":
            result = run_provider_diagnostic(state, profile)
            if result["all_pass"]:
                transition(state, "PROVIDER_PROBE", {"connectivity": "PASS"})
                continue
            state["blocked_reason_code"] = "BLOCKED_PROVIDER_NETWORK_ENVIRONMENT"
            transition(state, "BLOCKED", {"connectivity": "FAIL", "report": result["report"]["checks"]})
            print("BLOCKED_PROVIDER_NETWORK_ENVIRONMENT")
            print(json.dumps(result["report"]["checks"], indent=2))
            return 0

        if current == "PROVIDER_PROBE":
            if not approved:
                print(f"PHASE1_MASTER: PROVIDER_PROBE requires {APPROVAL_ENV_VAR}=true -- stopping without a Provider call")
                return 0
            result = run_provider_probe(state, profile)
            save_state(state)
            if result["outcome"] == "response_received":
                transition(state, "SMOKE", {"probe": result})
                continue
            state["blocked_reason_code"] = "BLOCKED_PROVIDER_CONNECTIVITY"
            transition(state, "BLOCKED", {"probe": result})
            print("BLOCKED_PROVIDER_CONNECTIVITY")
            print(json.dumps(result, indent=2))
            return 0

        if current == "ANTHROPIC_QUALIFICATION":
            if not approved or not data_egress_approved:
                print(
                    f"PHASE1_MASTER: ANTHROPIC_QUALIFICATION requires "
                    f"{APPROVAL_ENV_VAR}=true and "
                    f"{DATA_EGRESS_APPROVAL_ENV_VAR}=true -- stopping without a Provider call"
                )
                return 0
            result = run_anthropic_profile_qualification(state, profile)
            save_state(state)
            if result.get("outcome") == "budget_exceeded":
                state["fail_reason_code"] = "FAIL_PHASE1_PROVIDER_CALL_LIMIT_EXCEEDED"
                transition(state, "FAIL", {"stage": current, "reason": "budget_exceeded"})
                print("FAIL_PHASE1_PROVIDER_CALL_LIMIT_EXCEEDED")
                return 0
            if result.get("outcome") != "response_received_and_parsed":
                blocker = str(result.get("reason_code") or "BLOCKED_ANTHROPIC_PROVIDER_UNAVAILABLE")
                state["blocked_reason_code"] = blocker
                transition(state, "BLOCKED", {"qualification": result})
                print(blocker)
                return 0
            state["current_provider_evaluation"]["qualification_completed"] = True
            transition(state, "SMOKE", {"anthropic_qualification": result})
            continue

        if current in ("SMOKE", "PILOT", "CORE_EVALUATION"):
            if not approved or not data_egress_approved:
                print(
                    f"PHASE1_MASTER: {current} requires {APPROVAL_ENV_VAR}=true "
                    f"and {DATA_EGRESS_APPROVAL_ENV_VAR}=true -- stopping without a Provider call"
                )
                return 0
            batch = run_evaluation_batch(state, profile, current)
            save_state(state)
            if batch["outcome"] == "budget_exceeded":
                state["fail_reason_code"] = "FAIL_PHASE1_PROVIDER_CALL_LIMIT_EXCEEDED"
                transition(state, "FAIL", {"stage": current, "reason": "budget_exceeded"})
                print("FAIL_PHASE1_PROVIDER_CALL_LIMIT_EXCEEDED")
                return 0
            if batch["outcome"] == "gateway_init_failed":
                state["blocked_reason_code"] = "BLOCKED_ANTHROPIC_PROVIDER_UNAVAILABLE"
                transition(state, "BLOCKED", {"stage": current, "detail": batch})
                print("BLOCKED_ANTHROPIC_PROVIDER_UNAVAILABLE")
                return 0
            if batch["outcome"] == "interrupted_report_requires_audit":
                state["blocked_reason_code"] = batch["reason_code"]
                transition(state, "BLOCKED", {"stage": current, "detail": batch})
                print(batch["reason_code"])
                return 0

            per_report_results = batch.get("per_report_results", [])
            _write_json(_evaluation_dir(state) / f"{current.lower()}_results.json", batch)

            if current == "SMOKE":
                gate = smoke_engineering_gate(per_report_results)
                # Replay is a per-report audit, not a whole-stage readiness
                # proxy.  Run it even when the Provider reliability gate is
                # already blocked: timeout/provider-error records must be
                # auditable as AUDITABLE_NO_ACCEPTED_OUTPUT and must never be
                # misreported as an Exact Replay implementation defect.
                replay_audit = verify_phase1_master_shadow_exact_replay(
                    _evaluation_dir(state)
                )
                _write_json(
                    _evaluation_dir(state) / "shadow_exact_replay_audit.json",
                    replay_audit,
                )
                gate["exact_replay_status"] = replay_audit["final_status"]
                gate["exact_replay_reason_codes"] = replay_audit["reason_codes"]
                gate["per_report_exact_replay_status"] = replay_audit.get(
                    "checks", {}
                ).get("per_report", [])
                if replay_audit["final_status"] != "PASS":
                    state["fail_reason_code"] = "FAIL_ACCEPTED_OUTPUT_EXACT_REPLAY"
                    transition(state, "FAIL", {"gate": gate})
                    print("FAIL_ACCEPTED_OUTPUT_EXACT_REPLAY")
                    return 0

                # v3_evidence_alignment_gate is pure, version-agnostic logic
                # over per_report_results/quote_resolution_summary -- reused
                # unchanged for v4 (same EvidenceQuoteResolver algorithm,
                # same safety property: zero fabricated/unresolved quote
                # ever admitted among accepted reports).
                if state.get("prompt_version_in_use") in (
                    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3,
                    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4,
                ):
                    evidence_gate = v3_evidence_alignment_gate(per_report_results)
                    gate["evidence_alignment"] = evidence_gate
                    if not evidence_gate["pass"]:
                        blocked_code = (
                            "BLOCKED_V4_EVIDENCE_ALIGNMENT_UNSAFE"
                            if state.get("prompt_version_in_use") == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4
                            else "BLOCKED_V3_EVIDENCE_ALIGNMENT_UNSAFE"
                        )
                        state["blocked_reason_code"] = blocked_code
                        transition(state, "BLOCKED", {"gate": gate})
                        print(blocked_code)
                        print(json.dumps(evidence_gate, indent=2))
                        return 0

                _write_json(STATE_DIR / "smoke_results.json", {"batch": batch, "gate": gate})
                if gate["outcome_reason_code"] is not None:
                    state["blocked_reason_code"] = gate["outcome_reason_code"]
                    transition(state, "BLOCKED", {"gate": gate})
                    print(gate["outcome_reason_code"])
                    return 0
                transition(state, "PILOT", {"gate": gate})
                continue

            if current == "PILOT":
                _write_json(STATE_DIR / "pilot_results.json", batch)
                safety_failure = any(
                    r.get("provider_status") not in ("success", "timeout", "provider_error", "budget_exhausted")
                    for r in per_report_results
                )
                if safety_failure:
                    state["fail_reason_code"] = "FAIL_PHASE1_NEW_REGRESSION"
                    transition(state, "FAIL", {"reason": "pilot_safety_failure"})
                    print("FAIL_PHASE1_NEW_REGRESSION")
                    return 0
                transition(state, "CORE_EVALUATION", {})
                continue

            if current == "CORE_EVALUATION":
                render_final_evaluation_bundle(state, batch)
                _write_json(STATE_DIR / "core_evaluation_results.json", batch)
                replay_audit = json.loads(
                    (_evaluation_dir(state) / "shadow_exact_replay_audit.json").read_text(
                        encoding="utf-8"
                    )
                )
                stability = build_provider_stability_summary(state, replay_audit)
                _write_json(STATE_DIR / "provider_stability_summary.json", stability)
                _write_json(_evaluation_dir(state) / "provider_stability_summary.json", stability)
                if not stability["operational_gate_pass"]:
                    state["blocked_reason_code"] = "BLOCKED_ANTHROPIC_PROVIDER_RELIABILITY"
                    transition(state, "BLOCKED", {"provider_stability": stability})
                    print("BLOCKED_ANTHROPIC_PROVIDER_RELIABILITY")
                    return 0
                if state.get("prompt_version_in_use") == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4:
                    state["semantic_quality"] = "UNPROVEN_V4"
                    state["human_review"] = "PENDING_V4"
                    state["production_authority"] = "LEGACY_ADAPTER"
                elif state.get("prompt_version_in_use") == STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V3:
                    state["semantic_quality"] = "UNPROVEN_V3"
                    state["human_review"] = "PENDING_V3"
                    state["production_authority"] = "LEGACY_ADAPTER"
                transition(state, "WAITING_FOR_HUMAN_REVIEW", {})
                print("PHASE1_MASTER: WAITING_FOR_HUMAN_REVIEW")
                print(f"review CSV: {_evaluation_dir(state) / 'phase1_human_review.csv'}")
                return 0

        if current in (
            "QUALITY_GATE",
            "PROMPT_V2_REVISION",
            "LIVE_SHADOW_INTEGRATION",
            "LIVE_SHADOW_CANARY",
            "PRODUCTION_CUTOVER",
        ):
            print(f"PHASE1_MASTER: {current} reached -- not yet implemented in this resumption; stopping cleanly")
            print("next_action: implement this stage's code once the prerequisite real data exists, then --resume")
            return 0

        print(f"PHASE1_MASTER: unknown state {current}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
