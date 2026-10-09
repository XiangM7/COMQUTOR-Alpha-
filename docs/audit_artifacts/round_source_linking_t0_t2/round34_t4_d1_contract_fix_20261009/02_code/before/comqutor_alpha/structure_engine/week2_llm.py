"""Controlled JSON-only LLM access for COMQUTOR Week 1-2 extraction tasks."""

from __future__ import annotations

import contextlib
import contextvars
import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any, TypeVar

# 2026-10-06 (AMD c904d4cc round 13: true concurrent audit support). Replaces
# the earlier single, Gateway-wide "pending attempt" dict (which assumed
# strictly sequential use and raised WEEK2_LLM_AUDIT_CONCURRENT_ATTEMPT the
# moment two real calls overlapped -- confirmed, from a real run, to be the
# root cause of 973/975 alpha_classifier failures). A contextvars.ContextVar
# is per-logical-call-chain, not per-Gateway-instance or per-thread: two
# concurrent calls through the SAME Gateway, each in its own worker thread,
# each get their OWN independent value here -- as long as that value is
# explicitly propagated across any nested thread boundary a call crosses
# (Python does NOT do this automatically for concurrent.futures.
# ThreadPoolExecutor.submit() -- see call_with_timeout's own explicit
# contextvars.copy_context() + ctx.run() below, which is what makes this
# correct rather than merely "seems to work"). A late-completing, previously
# timed-out call's own background thread still carries the EXACT context
# value that was live when it was originally submitted -- never whatever a
# newer, unrelated call set afterward -- because each thread's own copied
# context is independent once copied, even if the gateway-wide state (e.g.
# audit_write_failed) is intentionally still shared.
_current_audit_attempt: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "comqutor_week2_llm_current_audit_attempt", default=None
)

from comqutor_alpha.llm_runtime.canonical_json import sha256_text
from comqutor_alpha.llm_runtime.contracts import (
    EXECUTION_POLICY_SCHEMA_VERSION,
    PROVIDER_RESPONSE_SCHEMA_VERSION,
    REQUEST_CONTROL_SCHEMA_VERSION,
)
from comqutor_alpha.llm_runtime.session import SemanticCallTrace, SemanticRuntimeSession
from comqutor_alpha.run_provider_stop import (
    LAYER_WEEK2,
    STOP_ERROR_CODE,
    STOP_STATUS_CODES,
    RunProviderStop,
)
from comqutor_alpha.storage.file_store import append_jsonl_record, validate_artifact_path
from comqutor_alpha.structure_engine.week2_execution_profile import (
    UnknownWeek2ExecutionProfile,
    resolve_week2_execution_profile,
)
from comqutor_alpha.structure_engine.week2_llm_request_audit import (
    AuditingTransport,
    AuditingTransportError,
    sanitize_headers,
)

ERROR_LOG_ARTIFACT_PATH = "error_logs/week2_llm_errors.jsonl"


class RunStoppedBeforeSendError(AuditingTransportError):
    """2026-10-08 (T4 round 28): raised by the request-audit hook -- the last point before AuditingTransport forwards a
    request -- when the run was stopped by a provider refusal after this request passed the gateway's own check. The
    request is never forwarded (same contract as AuditingTransportError); the gateway records it as not sent."""
# 2026-10-06 (Phase C controlled single-request verification round): opt-in
# only (Week2LLMGateway(enable_request_response_audit=True)) -- every
# existing caller that never passes this keeps writing nothing here, exact
# same behavior as before this round.
PROVIDER_REQUEST_AUDIT_ARTIFACT_PATH = "error_logs/week2_llm_provider_request_audit.jsonl"
PROVIDER_RESPONSE_AUDIT_ARTIFACT_PATH = "error_logs/week2_llm_provider_response_audit.jsonl"
REQUEST_AUDIT_SCHEMA_VERSION = "comqutor.week2_llm_provider_request_audit.v1"
RESPONSE_AUDIT_SCHEMA_VERSION = "comqutor.week2_llm_provider_response_audit.v1"
# Step 5A runtime-capacity repair, single-claim semantics (docs/audit_artifacts/
# week2_runtime_capacity_root_cause_v0.1.2.1.json + week2_single_claim_
# concurrency_benchmark_v0.1.2.1.json). Multi-claim batching was evaluated
# and DEFERRED for v0.1.2.1: real controlled-Provider testing against
# DeepSeek deepseek-v4-flash showed multi-item structured completions are
# unreliable regardless of batch size (40 -> 22.9% coverage; 15 -> repeated
# >60s timeouts even with a fresh client per call, ruling out a connection-
# reuse bug) or timeout (45s, then 60s). A raw single-claim call, by
# contrast, was consistently fast and reliable (~1.8-2s measured directly,
# matching Step-4's own per-claim p50 ~1.87s/p90 ~3.47s for the old
# unbatched alpha_classifier task). 20.0s is roughly 6x that observed p50 and
# comfortably above the observed p90 -- enough headroom for real variance
# without retaining a timeout sized for the multi-claim case that no longer
# applies. Still overridable per-run via the existing
# COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS env var (bounded 1-120s in
# build_server_week2_llm_gateway) -- no provider-specific hardcoding.
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_RETRIES = 1
MAX_SERVER_RETRIES = 2
MAX_PROMPT_PAYLOAD_CHARS = 60_000

# v0.1.3 Provider Final-Orphan Reliability Fix, Phase 1 (Option C from
# docs/audit_artifacts/v0_1_3_provider_final_orphan_reliability_audit.md):
# evidence_stance_classifier alone contributed 74.4% of all final semantic
# orphans across the six authoritative runs with a 97.3% orphan-rate-given-
# failure and only a 2.7% retry recovery rate -- by far the dominant
# component-specific reliability gap identified by that audit. This is a
# component-SPECIFIC retry-count increase, not a global one: alpha_classifier
# (72.2% recovery, already well-served by 1 retry) and structure_extractor
# (orphans are schema/validation-driven, not attempt-count-driven) keep the
# shared DEFAULT_MAX_RETRIES unchanged. Bounded to MAX_SERVER_RETRIES -- this
# is not a new ceiling, it reaches the existing one exactly.
EVIDENCE_STANCE_CLASSIFIER_MAX_RETRIES = min(2, MAX_SERVER_RETRIES)


def _resolve_task_max_retries(task: str, default_max_retries: int) -> int:
    """Component-specific retry-policy resolution. Every task except
    ``evidence_stance_classifier`` keeps the shared Gateway-level
    ``default_max_retries`` (``self.max_retries``) exactly as before this
    change -- this function changes behavior for exactly one task.

    An explicit ``default_max_retries == 0`` is respected as-is, never
    raised, even for ``evidence_stance_classifier``: zero is an intentional
    "no retries at all" signal (used, for example, by narrow unit tests that
    construct a Gateway with ``max_retries=0`` to isolate single-attempt
    behavior unrelated to retry-count itself) -- the component-specific
    reliability increase only ever *adds* attempt opportunities on top of a
    non-zero configured policy, never overrides an explicit opt-out."""
    if task == "evidence_stance_classifier" and default_max_retries > 0:
        return max(default_max_retries, EVIDENCE_STANCE_CLASSIFIER_MAX_RETRIES)
    return default_max_retries

# --- Workload-aware call budget (Step 5A Section 8, single-claim semantics) -
# DEFAULT_MAX_CALLS was a fixed 32 with no documented rationale (see the
# root-cause artifact, questions 5-7: classified HISTORICAL_TEST_DEFAULT,
# not evidenced as safety/cost/rate-limit protection). Six real Step-4
# production runs proved this more than 25x too small for a single real
# ticker under single-claim semantics (up to 949 claims observed, one
# Provider call per claim). This replaces it with an explicit, auditable
# formula rather than an arbitrary large number (never "set MAX_CALLS =
# 5000"): one call per expected claim, plus the OTHER existing tasks
# (claim_batch_enrichment/structure_extractor/evidence_stance_classifier,
# unaffected by this repair and still sharing this one global budget), plus
# one full bounded retry pass over that entire total (retries reserve a
# separate budget unit each, per Week2LLMGateway._reserve_call/
# invoke_json_with_trace) and a small fixed safety margin.
MAX_EXPECTED_CLAIMS_PER_TICKER = 1200  # observed max = 949 (TSM, Step 4); ~25% headroom, rounded
ENRICHMENT_BATCH_SIZE = 64  # structured_output_adapter.LLM_CLAIM_BATCH_SIZE, duplicated here only as a documented budget-formula input, not re-exported
OTHER_TASK_CALL_ALLOWANCE = 15  # structure_extractor + evidence_stance_classifier + misc (observed <= 11/ticker across all six Step-4 runs)
CALL_BUDGET_SAFETY_MARGIN = 10


def compute_workload_aware_max_calls(
    *,
    eligible_claim_count: int = MAX_EXPECTED_CLAIMS_PER_TICKER,
    enrichment_batch_size: int = ENRICHMENT_BATCH_SIZE,
    other_task_allowance: int = OTHER_TASK_CALL_ALLOWANCE,
    max_retries: int = DEFAULT_MAX_RETRIES,
    safety_margin: int = CALL_BUDGET_SAFETY_MARGIN,
) -> dict[str, int]:
    """Deterministic, auditable per-run call-budget formula (Step 5A
    Section 3/8, single-claim semantics): one Provider call per eligible
    claim (no batching), plus the other existing tasks, plus one full
    bounded retry pass over that total, plus a small fixed margin.

    base_call_budget = eligible_claim_count + ceil(eligible_claim_count / enrichment_batch_size) + other_task_allowance
    retry_budget = base_call_budget * max_retries
    total_call_budget = base_call_budget + retry_budget + safety_margin

    Returns the full breakdown (not just the total) so callers can persist
    eligible_claim_count/base_call_budget/retry_budget/total_call_budget
    exactly, per Section 3. Every input is a named, documented constant or
    the real observed claim count -- never a blind round number. Still
    finite and bounded (the caller additionally clamps against
    MAX_SERVER_CALLS).
    """
    eligible_claim_count = int(eligible_claim_count)
    base_call_budget = (
        eligible_claim_count
        + -(-eligible_claim_count // int(enrichment_batch_size))  # ceil division, no float rounding
        + int(other_task_allowance)
    )
    retry_budget = base_call_budget * max(0, int(max_retries))
    total_call_budget = base_call_budget + retry_budget + int(safety_margin)
    return {
        "eligible_claim_count": eligible_claim_count,
        "base_call_budget": base_call_budget,
        "retry_budget": retry_budget,
        "total_call_budget": total_call_budget,
    }


DEFAULT_MAX_CALLS = compute_workload_aware_max_calls()["total_call_budget"]  # = (1200+19+15) + 1234*1 + 10 = 2478
# Hard ceiling an operator's COMQUTOR_WEEK2_LLM_MAX_CALLS override can reach.
# Raised from 100 (itself unexplained, same origin as the old
# DEFAULT_MAX_CALLS=32) to comfortably exceed the new workload-aware default
# with real headroom for a ticker above MAX_EXPECTED_CLAIMS_PER_TICKER,
# while remaining a firm, documented, bounded ceiling -- never unbounded.
MAX_SERVER_CALLS = 3000

# --- Controlled single-claim concurrency (Step 5A Section 4/10) ------------
# Batching is DEFERRED for v0.1.2.1 (see DEFAULT_TIMEOUT_SECONDS's own
# comment above); execution capacity instead comes from running independent
# single-claim calls concurrently. Week2LLMGateway's call-budget counter
# (_reserve_call) and error logger (_log) are both lock-protected
# (Section 5), so concurrent workers cannot overshoot the shared budget or
# corrupt the shared error log. Selected from a real 3-way benchmark
# (concurrency 1 vs 4 vs 8) against persisted QQQ claims -- see
# docs/audit_artifacts/week2_single_claim_concurrency_benchmark_v0.1.2.1.json
# for the measured evidence this default is based on.
DEFAULT_ALPHA_CLASSIFIER_CONCURRENCY = 4
MAX_ALPHA_CLASSIFIER_CONCURRENCY = 8


def _selected_profile_or_none():
    """The selected Week 2 execution profile (week2_execution_profile.py),
    ``None`` when none is selected. An unknown name also yields ``None``
    here: build_server_week2_llm_gateway refuses to build a gateway for it,
    so no request is ever sent under a misnamed profile."""
    try:
        return resolve_week2_execution_profile()
    except UnknownWeek2ExecutionProfile:
        return None


def resolve_alpha_classifier_concurrency() -> int:
    profile = _selected_profile_or_none()
    if profile is not None:
        return profile.alpha_classifier_concurrency
    return _bounded_int(
        os.environ.get("COMQUTOR_WEEK2_LLM_CONCURRENCY"),
        DEFAULT_ALPHA_CLASSIFIER_CONCURRENCY,
        1,
        MAX_ALPHA_CLASSIFIER_CONCURRENCY,
    )


# --- Bounded concurrency for evidence_stance_classifier (John Requirement B,
# Phase B2 Slice 2A) ---------------------------------------------------------
# evidence_stance_classifier's batches are independent (proven in
# docs/audit_artifacts/v0_2_evidence_stance_concurrency_optimization.json --
# each batch reads only the immutable taxonomy and writes onto its own
# already-unique candidate dicts, mutating no state any other batch reads or
# writes) and were, before this change, the single largest fully-serial
# latency contributor identified by the B1 cost/latency audit (median ~2671s
# span across the seven analyzed runs). A dedicated offline scheduling
# simulation using persisted per-call durations from all seven runs (see the
# same artifact) showed diminishing returns past concurrency=4 relative to
# the Provider-pressure increase of running more of this task's much
# heavier, longer-running batch calls (mean ~48.6s, up to 135s observed)
# simultaneously -- so this reuses the SAME proven default already selected
# for alpha_classifier via a real controlled benchmark, rather than picking
# a new, unvalidated-under-real-Provider-load ceiling. A separate env var
# (not COMQUTOR_WEEK2_LLM_CONCURRENCY) keeps the two tasks independently
# tunable, since they have very different per-call cost/duration profiles.
DEFAULT_EVIDENCE_STANCE_CONCURRENCY = 4
MAX_EVIDENCE_STANCE_CONCURRENCY = 8


def resolve_evidence_stance_concurrency() -> int:
    profile = _selected_profile_or_none()
    if profile is not None:
        return profile.evidence_stance_concurrency
    return _bounded_int(
        os.environ.get("COMQUTOR_WEEK2_STANCE_CONCURRENCY"),
        DEFAULT_EVIDENCE_STANCE_CONCURRENCY,
        1,
        MAX_EVIDENCE_STANCE_CONCURRENCY,
    )


# --- Bounded concurrency for structured_adapter (John Requirement B, Phase
# B2 Slice 2B) ---------------------------------------------------------------
# Every persisted run analyzed (all seven) shows exactly 4 LLM-eligible raw
# agent outputs per ticker (market_agent, sentiment_agent, news_agent,
# fundamental_agent) -- confirmed from source, not assumed -- so 4 concurrent
# workers already give every independent agent-report its own lane; a higher
# cap (6/8) was simulated and produces IDENTICAL stage makespan to 4 in every
# one of the seven runs (there is nothing left to parallelize past the 4th
# lane). This mirrors both alpha_classifier's and evidence_stance_classifier's
# own already-proven default, rather than introducing a new, unvalidated
# ceiling for a task with an even smaller, more tightly-bounded fan-out.
DEFAULT_STRUCTURED_ADAPTER_CONCURRENCY = 4
MAX_STRUCTURED_ADAPTER_CONCURRENCY = 8


def resolve_structured_adapter_concurrency() -> int:
    return _bounded_int(
        os.environ.get("COMQUTOR_WEEK2_ADAPTER_CONCURRENCY"),
        DEFAULT_STRUCTURED_ADAPTER_CONCURRENCY,
        1,
        MAX_STRUCTURED_ADAPTER_CONCURRENCY,
    )
# Phase 1B.1 only: invoke_prebuilt_json_prompt's own bound, sized for the
# Shadow prompt's shape (frozen instructions + full verbatim untrusted
# report + candidate-segment hints, which the Shadow contract's own
# StructuredOutputShadowParser already allows up to 500,000 report bytes)
# -- deliberately not MAX_PROMPT_PAYLOAD_CHARS, which is sized for the three
# existing tasks' compact JSON-only payloads and is unrelated to this one.
MAX_PREBUILT_PROMPT_CHARS = 2_000_000
# Phase 1 Master task-level execution policy override bound (invoke_prebuilt_
# json_prompt only): an outer safety clamp, never itself a target value --
# the product-owner-approved structured_claim_shadow policy (90s/0 retries)
# is well inside it. Never applied to the shared Gateway constructor
# defaults or to the three existing tasks' invoke_json(_with_trace) calls.
MAX_TASK_TIMEOUT_SECONDS = 300.0

T = TypeVar("T")

_TASK_INSTRUCTIONS = {
    "claim_batch_enrichment": (
        "Enrich each already-segmented claim in the supplied segments array. Return one JSON "
        "object with a claims array containing exactly one item per input segment, matched by "
        "segment_id. Each item must contain segment_id, claim, evidence, source_section, "
        "entities, factors, direction, and confidence. claim, evidence, and source_section must "
        "be returned byte-for-byte identical to the input segment with that segment_id -- never "
        "rewritten, merged with another segment, or split. Never omit a segment_id and never "
        "invent one that was not supplied."
    ),
    "alpha_classifier": (
        "First identify what the Evidence's own words actually assert as a present-tense "
        "proposition: is it the author's own stated conclusion, a view the author merely reports "
        "or quotes from someone else without endorsing it, a question (including a rhetorical one "
        "defending why a question matters), the setup for a rebuttal whose actual substantiating "
        "content is not given in this Evidence (for example 'let me challenge that with the actual "
        "trajectory' when no trajectory follows), or a conditional/hypothetical consequence that "
        "has not been asserted as having happened. Only the author's own asserted, present-tense "
        "conclusion can be classified -- a bare question, an unendorsed quotation, or an "
        "unsubstantiated rebuttal setup is not yet a conclusion to classify, even if it uses an "
        "Alpha-relevant word. "
        "Classify that proposition against the FULL supplied Alpha taxonomy (alpha_taxonomy) -- "
        "every canonical Alpha is a legitimate candidate, none has been pre-filtered or "
        "pre-admitted by any other program logic. Select the single Alpha whose core thesis and "
        "causal/economic mechanism the proposition most directly and substantively supports or "
        "opposes -- never an Alpha that merely shares surface words or a topic with the Evidence. "
        "Opposing an Alpha's thesis still means the Evidence substantively engages that Alpha -- "
        "select it; do not convert a genuine, substantive opposition into decision=none merely "
        "because the Evidence argues against the thesis rather than for it. Several Alphas can "
        "share overlapping keywords (for example AI capex, GPU demand, or data center activity can "
        "each relate to more than one Alpha); when more than one Alpha looks plausible, compare "
        "them directly against each other and select whichever one's own stated mechanism the "
        "Evidence engages with more closely and substantively -- never by keyword overlap alone, "
        "and never by declining to choose merely because the comparison is close. A difficult or "
        "close classification is still a classification task: decision=none is not a way to avoid "
        "choosing between two or more plausible Alphas. For example, if both A101 and A103 seem "
        "plausible, deciding decision=none because 'both are plausible' is WRONG; if A103 is the "
        "closer, more substantive fit, the required answer is decision=select with "
        "selected_alpha_id=A103. Use decision=none with selected_alpha_id=null only when no single "
        "canonical Alpha materially fits the Evidence at all -- when the Evidence does not "
        "substantively engage any Alpha's thesis, or is generic or background market commentary "
        "with no specific Alpha-relevant mechanism. The Evidence's own words must state the "
        "specific mechanism an Alpha's own thesis describes -- not merely that the claim shares an "
        "industry, sector, or ticker context with that Alpha, and not a conclusion a reader would "
        "have to compute from a bare listing of figures across periods or categories that the "
        "Evidence itself never characterizes as a trend. A single financial figure or ratio that "
        "the Evidence already characterizes in its own words as a growth, decline, or "
        "valuation-relevant trend (for example 'grew', 'increased', 'record', 'accelerating', "
        "'compressed', 'declined') remains sufficient on its own -- this targets only "
        "uncharacterized data listings and industry/ticker context, never a figure the Evidence "
        "itself already interprets. A hypothetical, conditional-downside, rebuttal, or skepticism "
        "framing (for example 'if X happens, Y would...', a statement arguing against another "
        "framing, or a low stated probability of reaching a threshold) must be judged by what it "
        "actually asserts is true now, never treated as affirmative evidence for the thesis whose "
        "surface vocabulary it happens to use. "
        "A304 (Multiple Compression) requires the Evidence to assert that valuation is rich "
        "RELATIVE TO FUNDAMENTALS -- a stated multiple (P/E, P/S, PEG, book value, or similar) "
        "characterized in the Evidence's own words as high, stretched, rich, or unsupported by "
        "fundamentals, or an explicit statement that strong fundamentals are not preventing "
        "downside. A claim that price has moved relative to its OWN trading history (for example a "
        "percentage above or below a moving average) is a price-technical observation, not a "
        "valuation-vs-fundamentals claim, and does not by itself satisfy A304 even when the "
        "Evidence calls it a 'reversion' or 'repricing' risk. The mere appearance of a "
        "valuation-sounding word (for example 'PEG', 'valuation', 'multiple', 'compression') is not "
        "sufficient on its own -- per the proposition-identification step above, a question about "
        "whether a price is justified, or a rebuttal of someone else's valuation argument that "
        "does not itself assert a valuation conclusion, does not satisfy A304 either. "
        "Price-technical indicators alone (moving averages, RSI, MACD, momentum streaks) are never "
        "sufficient for A601 -- A601 requires the Evidence to describe investor attention, media or "
        "analyst narrative, or crowd positioning, not price mechanics. "
        "A101 (AI Expansion) and A103 (AI Infrastructure) both require genuine AI-related content: "
        "A101's mechanism is AI training/adoption increasing demand for accelerators and AI-related "
        "equities broadly; A103's mechanism is AI buildout specifically driving datacenter, power, "
        "cooling, networking, or server demand. When the Evidence names concrete datacenter, power, "
        "cooling, networking, server, or advanced-packaging/foundry capacity, prefer A103 over A101 "
        "even when AI demand is the stated cause -- but this is a tie-breaking preference for when "
        "such capacity IS named, not a requirement: the absence of these specific words never by "
        "itself disqualifies A103, and never by itself means A101 is the better fit. When neither "
        "Alpha's specific mechanism is named concretely (for example a bare statement that 'AI "
        "capex' or 'AI spending' is continuing, without saying what it funds), compare based on "
        "whatever the Evidence's own words DO specify, and recognize that a non-AI capital-spending "
        "claim (for example generic 'infrastructure buildout' or capital-expenditure growth with no "
        "mention of AI, data, compute, or a specific AI-driven ticker narrative stated IN the "
        "Evidence itself) does not satisfy either Alpha merely because of the company's general "
        "reputation or ticker context -- judge only from what the Evidence's own words state, per "
        "the rule below. "
        "A003 (Liquidity Expansion) requires the Evidence to describe broad macro liquidity "
        "conditions improving -- for example central-bank balance-sheet expansion, money-supply "
        "growth, or credit conditions easing -- supporting risk appetite and discretionary equity "
        "inflows generally. A mechanical, structural flow tied to a specific event -- for example "
        "index-inclusion-driven passive rebalancing, or a forced/passive fund bid resulting from an "
        "index-composition change -- is not itself evidence of improving macro liquidity or risk "
        "appetite, even when the Evidence uses words like 'inflows' or 'bid'; it is a different "
        "mechanism A003 does not cover. "
        "Judge only from the claim, the evidence, and "
        "each Alpha's own definition. Return one JSON object with decision set to select or none "
        "and selected_alpha_id set to exactly one alpha_id from the supplied alpha_taxonomy when "
        "decision is select, or null when decision is none. Never invent an Alpha ID that is not "
        "in the supplied taxonomy, never select more than one Alpha, and never provide a trading "
        "decision or recommendation."
    ),
    "structure_extractor": (
        "Extract only evidence-backed relations between supplied allowed_factors. Return one JSON "
        "object with an edges array. Each edge must contain source_factor, target_factor, edge_type "
        "(causal, supportive, or conflicting), assertion_status (asserted, conditional, negated, "
        "mixed, or unknown), and confidence. Return an empty array when no relation is stated."
    ),
    # Step 5A execution-capacity repair: batched sibling of "alpha_classifier"
    # with the IDENTICAL semantic decision criteria -- only the input/output
    # envelope changes (one claim per call -> many claims per call, matched
    # by claim_id). This is not a semantic prompt change; every classification
    # rule below is copied verbatim from "alpha_classifier" v3.
    "alpha_classifier_batch": (
        "Classify EACH claim in the supplied claims array independently against the FULL supplied "
        "Alpha taxonomy (alpha_taxonomy) -- every canonical Alpha is a legitimate candidate for "
        "every claim, none has been pre-filtered or pre-admitted by any other program logic. For "
        "each claim, select the single Alpha whose core thesis and causal/economic mechanism that "
        "claim's Evidence most directly and substantively supports or opposes -- never an Alpha "
        "that merely shares surface words or a topic with the Evidence. Several Alphas can share "
        "overlapping keywords (for example AI capex, GPU demand, or data center activity can each "
        "relate to more than one Alpha); when more than one Alpha looks plausible for a given claim, "
        "compare them directly against each other and select whichever one's own stated mechanism "
        "that claim's Evidence engages with more closely and substantively -- never by keyword "
        "overlap alone, and never by declining to choose merely because the comparison is close. A "
        "difficult or close classification is still a classification task: decision=none is not a "
        "way to avoid choosing between two or more plausible Alphas for that claim. For example, if "
        "both A101 and A103 seem plausible for a claim, deciding decision=none because 'both are "
        "plausible' is WRONG; if A103 is the closer, more substantive fit, the required answer for "
        "that claim is decision=select with selected_alpha_id=A103. Use decision=none with "
        "selected_alpha_id=null for a claim only when no single canonical Alpha materially fits that "
        "claim's Evidence at all -- when the Evidence does not substantively engage any Alpha's "
        "thesis, or is generic or background market commentary with no specific Alpha-relevant "
        "mechanism. Each claim's Evidence's own words must state the specific mechanism an Alpha's "
        "own thesis describes -- not merely that the claim shares an industry, sector, or ticker "
        "context with that Alpha, and not a conclusion a reader would have to compute from a bare "
        "listing of figures across periods or categories that the Evidence itself never "
        "characterizes as a trend. A single financial figure or ratio that the Evidence already "
        "characterizes in its own words as a growth, decline, or valuation-relevant trend (for "
        "example 'grew', 'increased', 'record', 'accelerating', 'compressed', 'declined') remains "
        "sufficient on its own -- this targets only uncharacterized data listings and "
        "industry/ticker context, never a figure the Evidence itself already interprets. A "
        "hypothetical, conditional-downside, rebuttal, or skepticism framing (for example 'if X "
        "happens, Y would...', a statement arguing against another framing, or a low stated "
        "probability of reaching a threshold) must be judged by what it actually asserts is true "
        "now, never treated as affirmative evidence for the thesis whose surface vocabulary it "
        "happens to use. Price-technical indicators alone (moving averages, RSI, MACD, momentum "
        "streaks) are never sufficient for A601 -- A601 requires the Evidence to describe investor "
        "attention, media or analyst narrative, or crowd positioning, not price mechanics. When the "
        "Evidence names concrete datacenter, power, cooling, networking, server, or "
        "advanced-packaging/foundry capacity, prefer A103 over A101 even when AI demand is the "
        "stated cause. Judge each claim only from its own claim, its own evidence, and each Alpha's own "
        "definition -- never let one claim's content influence another claim's classification. "
        "Return one JSON object with a decisions array containing EXACTLY one item per input claim, "
        "matched by claim_id. Each item must contain claim_id (copied verbatim from the input claim "
        "with that id), decision set to select or none, and selected_alpha_id set to exactly one "
        "alpha_id from the supplied alpha_taxonomy when decision is select, or null when decision is "
        "none. Never omit a claim_id and never invent one that was not supplied. Never invent an "
        "Alpha ID that is not in the supplied taxonomy, never select more than one Alpha for a "
        "claim, and never provide a trading decision or recommendation."
    ),
    "evidence_stance_classifier": (
        "For each item, classify only the Evidence's stance toward its own target_alpha_id -- never "
        "toward any other Alpha. First ask whether the Evidence contains a substantive, "
        "independently interpretable assertion relevant to evaluating the target Alpha's thesis -- "
        "judge this from the actual content, never from length: not every short sentence is "
        "non-substantive, and not every long one is substantive. Evidence that is a heading, a bare "
        "label or score, an isolated topic name, a fragment, an instruction, a watch-item note, or "
        "otherwise formatting-like, with no assertion that can be evaluated on its own, has no stance "
        "to assign beyond neutral_background. When the Evidence does contain a substantive assertion, "
        "distinguish two further cases relative to target_alpha_id: use mentions_alpha when the "
        "assertion directly concerns the target thesis, mechanism, or subject matter but does not "
        "materially support or materially weaken it; use supports_alpha when it is a material, net "
        "endorsement of the target thesis, and opposes_alpha when it is a material, net rebuttal or "
        "weakening of it. Reserve neutral_background for Evidence that is contextual, generic, or "
        "otherwise makes no sufficiently direct substantive assertion about the target thesis at all "
        "-- not for Evidence that does directly concern the target thesis without taking a side, "
        "which is mentions_alpha. Read negation, rebuttal, qualification, conditional language, risk "
        "relief, and already-priced-in arguments on their actual meaning. When the Evidence contains "
        "more than one clause that materially bears on target_alpha_id's own thesis (for example 'X "
        "remains strong, but Y creates risk', 'although X, Y', 'if X, then Y'), identify every such "
        "clause -- not only the first one found -- and resolve the stance from their combined, net "
        "implication for the target thesis: supports_alpha if the material clauses net to "
        "endorsement, opposes_alpha if they net to rebuttal or material weakening, and mentions_alpha "
        "when the material clauses directly concern the target thesis but their combined implication "
        "is genuinely non-directional or cannot be resolved as net support or opposition -- never by "
        "selecting one clause and discarding a second, equally target-relevant one. Use "
        "neutral_background here only under the earlier rule, where no sufficiently direct "
        "substantive target-relative assertion exists in the first place: an unresolved or "
        "non-directional net implication among clauses that do directly bear on the target thesis is "
        "mentions_alpha, not neutral_background. Conditional language ('if', 'could', 'may', 'would') "
        "affects how certain the claim is, not whether it has a stance: a clearly conditional endorsement of the target thesis is still "
        "supports_alpha, and a clearly conditional rebuttal is still opposes_alpha. Only report "
        "supports_counter_alpha when the Evidence itself materially supports one of the supplied "
        "counter_alphas' own thesis -- never merely because it opposes target_alpha_id, never merely "
        "because the Evidence is mixed, and never merely because another Alpha is mentioned. Return "
        "one JSON object with an items array containing exactly one result per input item, matched by "
        "claim_id and target_alpha_id, each with stance set to exactly one of supports_alpha, "
        "opposes_alpha, mentions_alpha, neutral_background, or supports_counter_alpha, and "
        "counter_alpha_id set to the supported counter Alpha's id only when stance is "
        "supports_counter_alpha, omitted otherwise. Use only the supplied claim_id, target_alpha_id, "
        "and counter Alpha ids -- never invent one."
    ),
    # v2 (2026-10-06, T1 judgment-standard correction): a TradingAgents report
    # is a RESTATEMENT, SUMMARY, and ANALYSIS of material -- not a transcript.
    # v1's own framing ("a single verified number... never an adjacent
    # interpretive... claim layered onto it") was closer to requiring the
    # source to say the conclusion nearly verbatim than to judging whether
    # the conclusion is actually WARRANTED by the material. v2 keeps every
    # real v1 safeguard (grammar-sensitivity, allowed_candidates-only
    # citation, identity/vocabulary discipline) but replaces "does the source
    # already say this" with the real question: is there a reliable basis
    # (direct fact, faithful paraphrase, a real recomputation, or a
    # reasonable inference from stated facts plus explicit assumptions) for
    # the claim, and does any gap change its core meaning or direction.
    "content_support_verification": (
        "This claim is one Agent's own restatement/summary/analysis of material it read -- not a "
        "transcript -- so your job is to judge whether the claim has a RELIABLE BASIS in the SAVED "
        "MATERIAL in allowed_candidates, never whether the material states the exact same sentence. "
        "Faithful paraphrase, a real recomputation from stated figures, and a reasonable inference "
        "from stated facts plus an explicit, named assumption are all real support -- do not reject "
        "a claim merely because allowed_candidates never spells out its exact wording or conclusion. "
        "Equally, do not accept a claim merely because it shares a topic, a number, or a general "
        "sentiment with allowed_candidates -- the material must actually warrant THIS claim's own "
        "stated proposition, its object, its direction, and its degree of certainty. Never judge "
        "whether the proposition is true in the world and never draw on general knowledge: if "
        "allowed_candidates contains nothing that bears on the proposition, the correct answer is "
        "INSUFFICIENT. allowed_candidates is the ONLY material you may cite -- never invent a "
        "source_id, excerpt text, or data_snapshot field not literally present in it. report_context "
        "(when present) is this claim's OWN agent's other claims from the same report section, given "
        "ONLY to help you resolve pronouns/referents and recover the surrounding argument -- it is "
        "the Agent's own paraphrase, never independent evidence, and must never be cited as support "
        "itself. Read the proposition's own actual grammar before judging: a reported view "
        "('analysts say X'), a quoted or paraphrased opinion the author does not themselves endorse, "
        "a question, a rebuttal's own setup before its substantiation, a negation ('X did NOT "
        "happen'), and a conditional or future prediction ('if X then Y', 'X is expected to "
        "continue') are each judged on their own actual claim, never collapsed into the surface "
        "topic they mention, and never treated as if already a settled past/present fact when the "
        "claim itself is a prediction or scenario. A subjective evaluative word ('cheap', "
        "'expensive', 'the biggest risk', 'will inevitably grow') is not automatically mere color: "
        "judge whether it is itself the claim's core conclusion (then it needs real support or a "
        "reasonable, disclosed inference from the material) or a genuinely minor rhetorical flourish "
        "alongside a separately-supported core fact (then it may belong in unsupported_remainder as "
        "non-material) -- state which, and why, in rationale; never decide this by keyword alone. "
        "Set status to SUPPORTS only when the material gives the claim's own stated proposition a "
        "reliable basis; OPPOSES when it materially rebuts or contradicts it; BACKGROUND when it is "
        "genuinely relevant context that neither supports nor opposes the specific proposition -- "
        "never a fact that has not yet actually happened reported as if it had; CITATION_ONLY when "
        "the claim merely names or references the material without the material itself bearing on "
        "the proposition's truth; CONDITIONAL when support depends on an assumption the material "
        "does not itself establish; INSUFFICIENT when allowed_candidates lacks material that bears "
        "on the proposition at all. First state core_proposition: the claim's own single core "
        "testable assertion, in your own words, for audit only -- this never replaces or scores in "
        "place of the claim's original text. For SUPPORTS/OPPOSES/CONDITIONAL, also set support_basis "
        "to exactly one of: DIRECT_FACT (the material states the same fact essentially verbatim), "
        "SEMANTIC_PARAPHRASE (a faithful restatement preserving the material's own meaning, no new "
        "number or relationship added), DERIVED_CALCULATION (a real, checkable arithmetic/formula "
        "computation from the material's own stated figures), or GROUNDED_INFERENCE (any other real "
        "conclusion that genuinely follows from the material's own stated facts -- whether or not it "
        "needs an extra assumption the material does not itself state; a real inference that follows "
        "by plain logical entailment from stated facts alone, with no gap-filling assumption at all, "
        "is still GROUNDED_INFERENCE, not DIRECT_FACT/SEMANTIC_PARAPHRASE); set it to NONE for "
        "BACKGROUND/CITATION_ONLY/INSUFFICIENT. For DERIVED_CALCULATION/GROUNDED_INFERENCE, list every "
        "fact you relied on in inference_facts (each one must itself be real material from allowed_"
        "candidates; never empty for these two bases). When the conclusion also relies on an "
        "assumption the material does not itself state, name it in inference_assumptions (plain "
        "language, naming it as an assumption, not disguised as a fact) -- but leave inference_"
        "assumptions empty, never invented, when the conclusion genuinely needs none (do not pad "
        "inference_assumptions with something you did not actually rely on just to fill the field). An "
        "inference that skips a necessary step or overstates what the facts (plus any real "
        "assumptions) actually entail is not GROUNDED_INFERENCE, it is unsupported. For SUPPORTS/"
        "OPPOSES/BACKGROUND/CITATION_ONLY/CONDITIONAL, used_source_id must "
        "be exactly one of allowed_candidates' own source_id values, used_location must name where "
        "in that candidate the material lives (an excerpt quote or a data_snapshot field path), and "
        "supporting_quote_or_data must be the material's own real quoted text or data value -- never "
        "paraphrased, never a value you computed yourself (state any computed value only in "
        "rationale/inference_facts, never in supporting_quote_or_data). When the claim combines a "
        "part the material supports with a part it does not, set supported_proposition to the "
        "narrow part that is actually supported (a faithful narrowing of the ORIGINAL claim's own "
        "wording, never a corrected or substituted proposition -- e.g. if the claim says 'the stock "
        "price is 37% above its 200-day average' but the material only supports that the 50-day "
        "average is 37% above the 200-day average, that is a DIFFERENT object and must go in "
        "unsupported_remainder, not supported_proposition) and unsupported_remainder to the specific "
        "remaining part that is not. Then set unsupported_remainder_materiality: NONE when "
        "unsupported_remainder is empty; MATERIAL when the unsupported part changes the claim's own "
        "object, its causal/comparative relationship, its direction, or its degree of certainty (a "
        "correction like the 50-day/200-day example above is always MATERIAL); NON_MATERIAL only "
        "when the unsupported part is a genuinely minor rhetorical add-on that does not change what "
        "the core, supported proposition actually asserts -- a subjective word like 'cheap'/'the "
        "biggest risk'/'should be trimmed' is NOT automatically non-material just because it is "
        "evaluative: if it IS the claim's own core conclusion, treat it as the thing needing real "
        "support (or as the material gap, if unsupported), never as free-standing color. Whenever you "
        "set NON_MATERIAL, state in rationale SPECIFICALLY why that remaining part does not change the "
        "core proposition's own object/direction/certainty -- a bare NON_MATERIAL label with no real "
        "explanation is not acceptable. Use mechanical_checks (when present) as "
        "already-confirmed real arithmetic/data facts you may rely on without re-deriving them, "
        "never as something to contradict without citing contrary material. Return one JSON object "
        "with an items array containing exactly one result per input item, matched by claim_id, each "
        "with claim_id, core_proposition, status, support_basis, used_source_id, used_location, "
        "supporting_quote_or_data, inference_facts, inference_assumptions, rationale, "
        "supported_proposition, unsupported_remainder, and unsupported_remainder_materiality "
        "(used_source_id/used_location/supporting_quote_or_data/supported_proposition/"
        "unsupported_remainder may be empty, and inference_facts/inference_assumptions may be empty "
        "lists, only for status INSUFFICIENT; inference_facts must otherwise be non-empty exactly "
        "when support_basis is DERIVED_CALCULATION or GROUNDED_INFERENCE, empty for every other "
        "support_basis; inference_assumptions must stay empty for every support_basis except "
        "GROUNDED_INFERENCE, where it may be non-empty OR empty depending on whether this specific "
        "conclusion genuinely needs an assumption -- never force-fill it). Use only the supplied "
        "claim_id and candidate source_id values -- never invent one."
    ),
}

_SHARED_JSON_ONLY_PROMPT_PREFIX = (
    "You are a constrained COMQUTOR extraction component. Return strict JSON only, with "
    "no markdown and no hidden reasoning. "
)
_INPUT_JSON_SEPARATOR = "\nINPUT_JSON:\n"
_PROMPT_IDENTITY_SEPARATOR = r"\nINPUT_JSON:\n"
_TASK_RUNTIME_METADATA = {
    "claim_batch_enrichment": {
        "semantic_task": "structured_adapter",
        "prompt_version": "week2.claim_batch_enrichment.v1",
        "input_schema_version": "week2.claim_batch_enrichment.input.v1",
        "output_schema_version": "week2.claim_batch_enrichment.output.v1",
        "taxonomy_version": None,
    },
    "alpha_classifier": {
        "semantic_task": "alpha_classifier",
        # v3: Pure-LLM Alpha semantic authority -- the LLM is now the SOLE
        # source of the semantic Alpha result (deterministic logic is a
        # diagnostic/counterfactual only, never a semantic fallback), and
        # the decision vocabulary itself changed: v2's decision=defer (a
        # successful "cannot decide" outcome that deterministic scoring was
        # allowed to resolve) is retired entirely and replaced by
        # decision=none (a successful, first-class "no canonical Alpha
        # materially fits" semantic answer -- semantic ambiguity between two
        # plausible Alphas is explicitly NOT grounds for none; the prompt
        # now requires selecting the closer of two plausible Alphas rather
        # than deferring). This is a genuine output-contract/vocabulary
        # change, not a wording patch, so both prompt_version and
        # output_schema_version bump (ADR-005: a versioned identifier must
        # change with the instructions/contract it identifies, so no old
        # cached v2 defer-vocabulary semantic-call result is ever silently
        # reused as if it reflected v3 select/none behavior). input_schema_
        # version is unchanged: the request payload shape itself (claim,
        # evidence, ticker, factors, direction, alpha_taxonomy) did not
        # change -- only the response contract and how callers interpret it.
        #
        # v4 (Day 4B, Candidate 1) and v5 (Day 4C, Candidate 2) were both
        # tried and RETIRED without becoming the production baseline: v4 was
        # formally REJECTED as a net regression on Provider-backed validation
        # (148/200 74.00% -> 139/200 69.50%, 25 new regressions -- see
        # docs/audit_artifacts/v0_2_day4b_provider_validation_result.json);
        # v5 improved on v4 but was never independently validated and
        # remained below the v3 baseline on development data (145/200 72.50%
        # -- see docs/audit_artifacts/v0_2_alpha_prompt_candidate2.md) and was
        # NOT_ACCEPTED. Both were already used in real Provider-backed runs
        # (v4 in Fresh NVDA/QQQ E2E; v5 in a Holdout #4 development pass), so
        # per ADR-005's anti-collision principle neither version string is
        # ever reassigned to different content. v3 (the restored baseline)
        # was then Provider-evaluated against the NEW, independent 100-sample
        # Development Gold (Day 4G) and scored 64/100 (64.00%), dominated by
        # 31 false positives where Gold=NONE (see
        # docs/audit_artifacts/v0_2_candidate3_baseline_dev_result.md) --
        # the OPPOSITE failure mode from v4's over-conservatism: v3 is
        # over-eager to select an Alpha from industry/ticker context, bare
        # data listings, and hypothetical/negated framing that don't state
        # the Alpha's own mechanism in the Evidence's own words.
        #
        # v6 (Day 4G, Candidate 3): adds ONE conditional semantic-sufficiency
        # guardrail targeting that specific error mass, explicitly designed
        # to avoid repeating v4's mistake (see
        # docs/audit_artifacts/v0_2_day4c_candidate1_regression_analysis.json)
        # -- the new clause requires the Evidence's own words to state an
        # Alpha's specific mechanism (not industry/ticker context, not a
        # bare uncharacterized data listing, not a hypothetical/rebuttal/
        # skepticism framing), while explicitly EXEMPTING any figure the
        # Evidence itself already characterizes as a trend (e.g. "grew",
        # "record", "accelerating") -- precisely the case whose absence broke
        # v4. Also adds two narrow, independently-evidenced boundary rules:
        # price-technical indicators are never sufficient for A601 (that
        # requires investor-attention/narrative evidence, not price
        # mechanics), and A103 is preferred over A101 when concrete
        # datacenter/power/networking/server/foundry capacity is named (the
        # same A101/A103 confusion direction already documented in v4's own
        # regression analysis, holdout4-022/024/066). See
        # docs/audit_artifacts/v0_2_candidate3_dev_error_analysis.md for the
        # full per-sample analysis this design is based on. Both
        # prompt_version and output_schema_version bump per ADR-005 (a
        # versioned identifier must change with the instructions it
        # identifies); input_schema_version is unchanged (request shape
        # unchanged). v6 was development-metric-only at freeze time; see
        # docs/audit_artifacts/v0_2_candidate3_freeze_manifest.md for
        # acceptance status. v6's own real-execution sha256 is
        # bb2dbdf0f3fc9a43291233494c2f355275b4fe6fddc71cd63fd1377f9ba109d9
        # (matches t3live_20261001T014648Z_1fb9c9d5's own frozen
        # freeze_identity.json -- the exact prompt that execution used,
        # preserved here, never overwritten, per ADR-005's anti-collision
        # principle).
        #
        # v7 (2026-10-01, AI-review comparison round): development-only,
        # NOT Provider-validated -- built from a real-execution error
        # analysis (t3live_20261001T014648Z_1fb9c9d5's own 40-sample run,
        # cross-checked against an independent ChatGPT AI_REVIEW second
        # opinion; see outputs/t3_ai_review_comparisons/ and
        # docs/audit_artifacts/round_source_linking_t0_t2/
        # t3live_...prompt_v7_adjudication.md for the full per-sample
        # adjudication this is based on), NOT a new Provider-backed dev/
        # holdout score the way v4/v5/v6 each had at their own introduction.
        # Real verification against a dev/holdout set is still required
        # before this could be treated as validated (see that same doc's
        # "limited real-verification plan").
        #
        # Five additive clarifications, each traced to a specific confirmed
        # misclassification pattern in the real execution (10 of that run's
        # 13 disagreements with the independent AI review were attributable
        # to one of these, after correcting an initial miscount and a
        # reasoning error that had treated the A103-preference tie-break
        # rule as if it were an exclusive requirement):
        #   1. A new FIRST step requiring the model to identify what the
        #      Evidence's own words actually assert (author's own
        #      conclusion vs. a quoted/reported view, a question, an
        #      unsubstantiated rebuttal setup, or an unmet conditional)
        #      before classifying -- targets gold-final-019/041/052/048's
        #      pattern (A304/A301 selected for a question, an unendorsed
        #      quotation, or a rebuttal's own setup with no substantiating
        #      content given).
        #   2. An explicit statement that opposing an Alpha's thesis still
        #      counts as substantive engagement (select it, don't default
        #      to none) -- clarifies, does not change, the existing
        #      "supports or opposes" rule; added because this round's own
        #      adjudication needed to repeatedly re-derive it from context.
        #   3. A304-specific clause distinguishing price-vs-own-history
        #      (technical) claims from valuation-vs-fundamentals claims, and
        #      stating explicitly that a valuation-sounding word alone
        #      (PEG/valuation/compression) is not sufficient -- targets
        #      gold-final-001/019/079's pattern.
        #   4. A101/A103-specific clause making explicit that the existing
        #      facility-word list (datacenter/power/cooling/networking/
        #      server/foundry) is a TIE-BREAKING preference for when such
        #      words ARE present, never a requirement whose absence
        #      disqualifies A103 or defaults to A101 -- targets
        #      gold-final-077's pattern, and corrects an exclusion-from-
        #      absence reasoning error this round's own first-pass human
        #      adjudication initially made before being corrected.
        #   5. A003-specific clause distinguishing broad macro liquidity
        #      conditions from mechanical, index-event-driven passive/forced
        #      flows -- targets prod-run-014/015's pattern.
        # Every illustrative example added is generic/invented, never a
        # verbatim real sample sentence from this or any frozen evaluation
        # pool -- no sample_id, no real claim text, and no answer key is
        # embedded in the prompt. The decision/selected_alpha_id response
        # contract, the taxonomy, every quality threshold, and every
        # downstream eligibility rule are unchanged; no new classification-
        # time regex veto gate was added anywhere in this round's work --
        # this is a prompt-text-only change.
        "prompt_version": "week2.alpha_classifier.v7",
        "input_schema_version": "week2.alpha_classifier.input.v2",
        "output_schema_version": "week2.alpha_classifier.output.v3",
        "taxonomy_version": "alpha_taxonomy_v1",
    },
    "alpha_classifier_batch": {
        "semantic_task": "alpha_classifier_batch",
        # v1: Step 5A execution-capacity repair. Same semantic decision
        # contract as alpha_classifier v3 (see the instruction text above),
        # restructured for batched claims -> decisions I/O. A distinct task
        # name/prompt identity (never silently merged with the unbatched
        # "alpha_classifier" task's own cache/replay identity) because the
        # request/response shape genuinely differs, per ADR-005.
        #
        # v2 (Day 4B, Candidate 1) and v3 (Day 4C, Candidate 2) mirrored
        # alpha_classifier's own v4/v5 history exactly; both were retired
        # without becoming production (see alpha_classifier's own metadata
        # comment above and docs/audit_artifacts/v0_2_alpha_candidate_
        # history.md). v4 (Day 4G, Candidate 3) mirrors alpha_classifier's
        # own v6 semantic content exactly (see the instruction text above and
        # its metadata comment for full rationale).
        "prompt_version": "week2.alpha_classifier_batch.v4",
        "input_schema_version": "week2.alpha_classifier_batch.input.v1",
        "output_schema_version": "week2.alpha_classifier_batch.output.v2",
        "taxonomy_version": "alpha_taxonomy_v1",
    },
    "structure_extractor": {
        "semantic_task": "structure_extractor",
        "prompt_version": "week2.structure_extractor.v1",
        "input_schema_version": "week2.structure_extractor.input.v1",
        "output_schema_version": "week2.structure_extractor.output.v1",
        "taxonomy_version": None,
    },
    "evidence_stance_classifier": {
        "semantic_task": "evidence_stance_classifier",
        # v3: B1 substantive-assertion gate + mentions_alpha/neutral_background
        # boundary clarification (QA Closure v0.1.2, following Blind Holdout
        # #1 root-cause analysis) -- adds an explicit pre-check for whether
        # the Evidence contains a substantive, independently interpretable
        # assertion at all (headings/labels/bare scores/fragments/watch-items
        # now explicitly route to neutral_background, never merely because
        # they are short), explicit definitions distinguishing mentions_alpha
        # (on-thesis, non-directional) from neutral_background (not
        # sufficiently on-thesis), and refines mixed-clause handling to
        # consider ALL target-relevant clauses' combined net implication
        # rather than only the first one found.
        #
        # v3 ontology consistency fix (same v3, applied before this prompt
        # was ever frozen/evaluated on a blind holdout -- not a new
        # version): the mixed-clause paragraph originally still allowed an
        # unresolved/non-directional net implication to fall back to
        # neutral_background, contradicting the mentions_alpha/
        # neutral_background definitions immediately above it -- clauses
        # already established as directly, substantively target-relevant
        # cannot un-clear the earlier substantive-assertion gate merely by
        # being hard to net out. That case now resolves to mentions_alpha;
        # neutral_background remains reserved solely for the earlier gate
        # (no sufficiently direct substantive target-relative assertion at
        # all).
        #
        # supports_alpha/opposes_alpha/
        # supports_counter_alpha semantics and the conditional-affects-
        # certainty-not-existence rule are unchanged in substance. No stance
        # value added or removed. Bumped from v2 because the prompt's
        # semantic instructions changed (ADR-005: a versioned prompt
        # identifier must change with the instructions it identifies, so any
        # old cached semantic-call result under v1/v2 is never silently
        # reused as if it reflected this behavior).
        "prompt_version": "evidence_stance.llm_classifier.v3",
        "input_schema_version": "evidence_stance.llm_classifier.input.v1",
        "output_schema_version": "evidence_stance.llm_classifier.output.v1",
        "taxonomy_version": "alpha_taxonomy_v1",
    },
    "content_support_verification": {
        "semantic_task": "content_support_verification",
        # Round 9 (2026-10-06): the first real LLM content-support judgment
        # task -- replaces reliance on human review (or Round 8's narrow
        # strip-and-check data-fact/derived-calc verifier, kept unmodified
        # for the pure-numeric case it already proves) for an ANALYTICAL
        # claim's own content-support eligibility. v1's own identity
        # ("content_support.llm.v1"/".input.v1"/".output.v1") is preserved
        # here in history/comments and stays permanently stamped on every
        # record a v1 call ever produced -- never silently relabeled.
        #
        # v2 (2026-10-06, T1 judgment-standard correction): a REAL finding
        # from round10's own 21-claim AMD execution -- 8 of 9 raw SUPPORTS
        # verdicts carried a non-empty unsupported_remainder, and v1's own
        # mechanical rule (ANY non-empty remainder -> CONDITIONAL, no
        # exceptions) downgraded every one of them, with no way to tell a
        # genuinely material correction (changes the claim's own object/
        # direction/certainty) apart from a non-material rhetorical add-on
        # riding alongside an otherwise fully-supported core fact. v2 adds
        # an explicit, LLM-reported support_basis (DIRECT_FACT/SEMANTIC_
        # PARAPHRASE/DERIVED_CALCULATION/GROUNDED_INFERENCE) and an
        # explicit unsupported_remainder_materiality (NONE/NON_MATERIAL/
        # MATERIAL) that the downgrade decision now actually consumes (see
        # content_support_llm.py's _effective_content_support_status) --
        # replacing the blanket mechanical rule with a disclosed, auditable
        # judgment, while keeping a MATERIAL remainder's own downgrade to
        # CONDITIONAL exactly as strict as v1 always was. This is a genuine
        # output-contract/vocabulary change (new required fields, new
        # decision input), so both prompt_version and output_schema_
        # version bump per ADR-005 -- no old v1-shaped cached semantic-call
        # result is ever silently reused as if it reflected v2's own
        # richer judgment.
        #
        # v2.1 (2026-10-06, limited real-verification round): v2 was NEVER
        # sent to a real Provider under its own identity (every real
        # execution to date stayed v1-shaped) -- found and fixed, before
        # any real spend, during this round's own required zero-cost
        # pre-send contract review: (1) v2's prompt wrongly required a
        # non-empty inference_assumptions whenever support_basis was
        # GROUNDED_INFERENCE, forcing the model to either invent a fake
        # assumption or get rejected for a genuinely assumption-free real
        # inference (e.g. "beta 2.45 implies high volatility" follows from
        # beta's own definition, no assumption needed) -- an unnecessary
        # FORMAT condition this round was explicitly asked to check for;
        # (2) NON_MATERIAL had no requirement to actually explain itself,
        # risking a bare label standing in for real judgment on claims
        # where the evaluative word ("cheap"/"the biggest risk") IS the
        # core conclusion. Both fixed in the prompt text above and in
        # content_support_llm.py's _v2_structural_contradiction. v2's own
        # identity is kept, distinct and never reused for this different
        # text, per "同一身份不能对应不同文本".
        "prompt_version": "content_support.llm.v2.1",
        "input_schema_version": "content_support.llm.input.v2",
        "output_schema_version": "content_support.llm.output.v2.1",
        "taxonomy_version": None,
    },
}


@dataclass(frozen=True)
class Week2LLMInvocation:
    parsed_output: dict[str, Any] | None
    validated_output: Any | None
    trace_handle: SemanticCallTrace | None
    cache_hit: bool
    provider_called: bool
    provider_status: str
    retry_count: int
    provider_attempt_count: int
    validation_attempted: bool
    validation_accepted: bool
    error_code: str | None = None
    cache_error_code: str | None = None
    # Populated only by invoke_prebuilt_json_prompt when a caller supplies an
    # explicit per-call execution policy override; always None (unchanged)
    # for invoke_json/invoke_json_with_trace and for invoke_prebuilt_json_
    # prompt calls that don't pass an override.
    effective_timeout_seconds: float | None = None
    effective_max_retries: int | None = None
    execution_policy_source: str | None = None
    # Evaluation-only observability for the prebuilt Shadow seam. Existing
    # Week2 tasks leave these additive fields at their defaults.
    response_received: bool = False
    token_usage: Mapping[str, int | None] | None = None
    attempt_history: tuple[Mapping[str, Any], ...] = ()
    # DeepSeek max_tokens/max_completion_tokens compatibility round
    # (2026-10-01): sanitized request-control/response-metadata, populated
    # only by invoke_json_with_trace on a real provider-called attempt (see
    # _request_control_snapshot/_response_provider_metadata). None for every
    # other call shape, including cache hits and invoke_prebuilt_json_prompt.
    request_control: Mapping[str, Any] | None = None
    provider_response_metadata: Mapping[str, Any] | None = None
    # v7 limited real-verification round (2026-10-01): one entry per REAL
    # attempt (base + every retry), success or failure -- distinct from
    # ``attempt_history`` above (the Shadow seam's own timeout/retry-policy
    # record): this is populated by invoke_json_with_trace itself (the path
    # the three standard tasks use), never overwritten by a later retry the
    # way token_usage/provider_response_metadata are, so an earlier failed
    # attempt's own real finish_reason/usage survives even once a
    # subsequent retry supersedes it as the invocation's own final outcome.
    request_attempts: tuple[Mapping[str, Any], ...] = ()
    # 2026-10-09 (T4 round 32): set only when the request was refused LOCALLY because its input exceeded the size limit
    # (error_code WEEK2_LLM_INPUT_TOO_LARGE): the measured input length and the limit it was checked against. Such a
    # request is never sent: no budget reservation, no HTTP request, no response, no usage.
    input_chars: int | None = None
    input_limit_chars: int | None = None


def input_too_large_error_message(input_chars: int | None, limit_chars: int | None) -> str:
    """The semantic ledger's error_message for a locally refused, never-sent request (T4 round 32)."""
    return (
        f"not sent: input of {input_chars} characters exceeds the {limit_chars}-character limit; refused locally "
        "before any budget reservation or HTTP request (no provider response, no usage)"
    )


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def call_with_timeout(function: Callable[[], T], timeout_seconds: float) -> T:
    """Run a blocking provider call with a caller-side wall-clock deadline.

    2026-10-06 (round 13): explicitly copies the CALLING thread's own
    contextvars.Context and runs ``function`` inside that copy on the nested
    worker thread (``executor.submit(ctx.run, function)``), rather than the
    bare ``executor.submit(function)`` this had before. This is required,
    not optional: ThreadPoolExecutor.submit() does NOT propagate context by
    itself (a new thread starts with a fresh, empty context) -- without this
    explicit copy, _current_audit_attempt (and any other contextvar a caller
    relies on) would silently read as unset inside the real Provider call,
    exactly the gap that made per-attempt audit identity impossible before
    this round's fix."""
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="comqutor-week2-llm")
    ctx = contextvars.copy_context()
    future = executor.submit(ctx.run, function)
    try:
        return future.result(timeout=max(float(timeout_seconds), 0.01))
    except FutureTimeoutError as exc:
        future.cancel()
        raise TimeoutError("Week 2 LLM call timed out") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


# Real-Provider diagnostic finding (disclosed in full in
# docs/audit_artifacts/phase1_master/prompt_audit/
# v2_json_format_diagnostic_findings.json, and reconfirmed by the B1 Evidence
# Stance live 50-row validation): claude-sonnet-4-6 reliably wraps its JSON
# response in a ```json ... ``` markdown code fence for some task shapes,
# even though the shared JSON-only prompt prefix explicitly says "Return
# strict JSON only, with no markdown". The content INSIDE the fence is
# well-formed JSON -- the only defect is the envelope, not the model's
# semantic judgment. This regex strips exactly one whole-response leading/
# trailing fence and nothing else; if the content is not fence-wrapped, or
# what remains after stripping is still not valid JSON, this returns the
# input unchanged -- json.loads immediately below remains the sole,
# unweakened, fail-closed JSON authority. Never fuzzy-matches or repairs
# content INSIDE the JSON itself.
#
# This was originally implemented, model-specific-diagnosed, and tested only
# for the separate structured_claim_shadow gateway path
# (structured_output_shadow_provider._MarkdownFenceStrippingModel). It lives
# here, at the shared Week2LLMGateway parsing boundary every task's response
# passes through (invoke_json_with_trace, invoke_prebuilt_json_prompt, and
# the legacy path all call _strict_json_object), so every current and future
# named Week2 task benefits uniformly -- structured_output_shadow_provider.py
# now imports this same function instead of defining a second copy.
_MARKDOWN_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*\n(.*)\n```\s*$", re.DOTALL)


def strip_markdown_json_fence(text: str) -> str:
    match = _MARKDOWN_JSON_FENCE_RE.match(text.strip())
    return match.group(1) if match else text


def _strict_json_object(response: Any) -> dict[str, Any]:
    if isinstance(response, Mapping):
        return dict(response)
    content = response if isinstance(response, str) else getattr(response, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise ValueError("missing JSON response content")
    parsed = json.loads(strip_markdown_json_fence(content))
    if not isinstance(parsed, dict):
        raise ValueError("JSON response must be an object")
    return parsed


def _response_token_usage(response: Any) -> dict[str, int | None] | None:
    """Extract non-secret token counters from common Provider message shapes."""

    usage = getattr(response, "usage_metadata", None)
    if not isinstance(usage, Mapping):
        metadata = getattr(response, "response_metadata", None)
        if isinstance(metadata, Mapping):
            usage = metadata.get("usage") or metadata.get("token_usage")
    if not isinstance(usage, Mapping):
        return None

    def _count(*names: str) -> int | None:
        for name in names:
            value = usage.get(name)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                return value
        return None

    input_tokens = _count("input_tokens", "prompt_tokens", "input_token_count")
    output_tokens = _count("output_tokens", "completion_tokens", "output_token_count")
    total_tokens = _count("total_tokens", "total_token_count")
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


# DeepSeek max_tokens/max_completion_tokens compatibility round (2026-10-01):
# the t3live_20261001T014648Z_1fb9c9d5 diagnostic found that a chat model's
# own object attribute (e.g. ``model.max_tokens``) does not reliably reflect
# what field name actually gets serialized into the real HTTP request --
# langchain_openai's own base class silently renames it per-model. The only
# faithful source of truth is the real, same-input call to the model's own
# ``_get_request_payload`` (the exact method LangChain's own ``invoke()``
# calls internally to build that request). This computes that payload
# separately, immediately before/alongside the real call, with the identical
# message conversion ``invoke(prompt)`` would apply to the same string
# prompt -- it does not intercept the literal bytes sent over the wire, but
# it is the same method, same model instance, same input, so for the
# OpenAI-compatible family (every provider this project's own
# DeepSeekChatOpenAI/NormalizedChatOpenAI/MinimaxChatOpenAI classes cover)
# it reproduces the real serialized field deterministically. Models that
# don't expose this method (e.g. ChatAnthropic, ChatGoogleGenerativeAI) are
# left unrecorded (None) rather than guessed at.
def _request_control_snapshot(model: Any, prompt: str) -> dict[str, Any] | None:
    """Sanitized, best-effort snapshot of the real serialized request this
    call sends -- endpoint, request model name, and the actual token-cap
    field name/value. Never includes auth headers or credentials (nothing
    here is sourced from them)."""

    get_payload = getattr(model, "_get_request_payload", None)
    if not callable(get_payload):
        return None
    try:
        from langchain_core.messages import HumanMessage

        payload = get_payload([HumanMessage(content=prompt)], stop=None)
    except Exception:
        return None
    if not isinstance(payload, Mapping):
        return None

    endpoint = getattr(model, "openai_api_base", None)
    request_model = payload.get("model") or getattr(model, "model_name", None)
    if not isinstance(endpoint, str) or not endpoint.strip():
        return None
    if not isinstance(request_model, str) or not request_model.strip():
        return None

    max_tokens_field: str | None = None
    max_tokens_value: int | None = None
    for field_name in ("max_tokens", "max_completion_tokens", "max_output_tokens"):
        if field_name not in payload:
            continue
        candidate = payload[field_name]
        if isinstance(candidate, int) and not isinstance(candidate, bool):
            max_tokens_field = field_name
            max_tokens_value = candidate
        break

    return {
        "schema_version": REQUEST_CONTROL_SCHEMA_VERSION,
        "endpoint": endpoint,
        "request_model": request_model,
        "max_tokens_field": max_tokens_field,
        "max_tokens_value": max_tokens_value,
    }


def _response_provider_metadata(response: Any) -> dict[str, Any] | None:
    """Sanitized Provider-reported response metadata: its own request/
    completion id, the returned model name, its raw (not yet trimmed to the
    three-field token_usage summary above) usage object, and its own
    finish_reason (e.g. "stop" vs "length" -- the latter is how a real
    truncation against the configured output cap is actually distinguished
    from a genuine, complete response; 2026-10-01, needed to let a limited
    real-verification run detect truncation from saved artifacts rather
    than only from live output). Sourced only from the already-parsed
    response object's own response_metadata -- never from auth headers or
    credentials."""

    metadata = getattr(response, "response_metadata", None)
    if not isinstance(metadata, Mapping):
        return None

    provider_request_id = metadata.get("id")
    response_model = metadata.get("model_name")
    finish_reason = metadata.get("finish_reason")
    raw_usage = metadata.get("token_usage")
    if not isinstance(raw_usage, Mapping):
        raw_usage = metadata.get("usage")

    result: dict[str, Any] = {"schema_version": PROVIDER_RESPONSE_SCHEMA_VERSION}
    if isinstance(provider_request_id, str) and provider_request_id.strip():
        result["provider_request_id"] = provider_request_id
    if isinstance(response_model, str) and response_model.strip():
        result["response_model"] = response_model
    if isinstance(finish_reason, str) and finish_reason.strip():
        result["finish_reason"] = finish_reason
    if isinstance(raw_usage, Mapping):
        result["raw_usage"] = dict(raw_usage)
    return result if len(result) > 1 else None


def _attempt_record(
    attempt_number: int,
    provider_status: str,
    error_code: str | None,
    provider_response: Mapping[str, Any] | None,
    attempt_id: str | None = None,
) -> dict[str, Any]:
    """One real attempt's own outcome, finish_reason, and raw usage --
    sanitized (sourced only from _response_provider_metadata, never from
    auth headers/credentials). Appended, never overwritten, so a retry that
    replaces an earlier failed attempt does not erase that earlier attempt's
    own real record (2026-10-01, v7 limited real-verification round).

    ``attempt_id`` (2026-10-06, additive): None for every existing caller
    (enable_request_response_audit=False) -- when set, joins this record to
    the literal wire-level request/response audit entries sharing the same
    attempt_id in PROVIDER_REQUEST_AUDIT_ARTIFACT_PATH/
    PROVIDER_RESPONSE_AUDIT_ARTIFACT_PATH."""

    record = {
        "attempt_number": attempt_number,
        "provider_status": provider_status,
        "error_code": error_code,
        "finish_reason": (provider_response or {}).get("finish_reason"),
        "raw_usage": (provider_response or {}).get("raw_usage"),
    }
    if attempt_id is not None:
        record["attempt_id"] = attempt_id
    return record


def _find_auditing_transport_error(exc: BaseException, *, max_depth: int = 5) -> AuditingTransportError | None:
    """Walks exc's __cause__/__context__ chain looking for an
    AuditingTransportError the underlying SDK may have wrapped in its own
    exception type (e.g. openai.APIConnectionError) before it reached the
    caller -- a bare ``isinstance(exc, AuditingTransportError)`` would miss
    that case."""
    current: BaseException | None = exc
    depth = 0
    while current is not None and depth < max_depth:
        if isinstance(current, AuditingTransportError):
            return current
        current = current.__cause__ or current.__context__
        depth += 1
    return None


def _provider_status_code(exc: BaseException) -> int | None:
    for candidate in (exc, getattr(exc, "response", None)):
        value = getattr(candidate, "status_code", None)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def _transient_provider_error_reason(exc: BaseException) -> str | None:
    """Return a stable retry reason only for explicitly transient failures."""

    status_code = _provider_status_code(exc)
    if status_code == 429:
        return "HTTP_429"
    if status_code is not None and 500 <= status_code <= 599:
        return "HTTP_5XX"
    if isinstance(exc, (ConnectionError, OSError)):
        return "TRANSIENT_PROVIDER_TRANSPORT"
    class_name = type(exc).__name__.lower()
    if any(
        token in class_name
        for token in (
            "connecterror",
            "connectionerror",
            "networkerror",
            "remoteprotocolerror",
            "transporterror",
        )
    ):
        return "TRANSIENT_PROVIDER_TRANSPORT"
    return None


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(number, minimum), maximum)


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(number, minimum), maximum)


def _enabled(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def week2_llm_enabled() -> bool:
    """Return the existing explicit opt-in flag without changing its default."""

    return _enabled(os.environ.get("COMQUTOR_WEEK2_LLM_ENABLED"))


class Week2LLMGateway:
    """Strict JSON gateway with bounded retries, timeout, and per-run call budget."""

    def __init__(
        self,
        model: Any,
        *,
        run_id: str,
        output_root: Any,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        max_calls: int = DEFAULT_MAX_CALLS,
        provider: str | None = None,
        model_name: str | None = None,
        semantic_runtime: SemanticRuntimeSession | None = None,
        error_log_artifact_path: str = ERROR_LOG_ARTIFACT_PATH,
        task_model_overrides: Mapping[str, Any] | None = None,
        execution_id: str | None = None,
        enable_request_response_audit: bool = False,
        task_timeout_seconds: Mapping[str, float] | None = None,
    ) -> None:
        self._model = model
        self.run_id = str(run_id)
        self.output_root = output_root
        self.timeout_seconds = max(float(timeout_seconds), 0.01)
        # 2026-10-08 (T3 closeout): optional per-task application timeout, set
        # by a selected execution profile (week2_execution_profile.py); a task
        # not listed keeps the shared ``timeout_seconds``. Empty by default.
        self._task_timeout_seconds: dict[str, float] = {
            str(task): min(max(float(value), 0.01), MAX_TASK_TIMEOUT_SECONDS)
            for task, value in (task_timeout_seconds or {}).items()
        }
        self.execution_profile: str | None = None  # set by build_server_week2_llm_gateway when a profile is selected
        self.max_retries = min(max(int(max_retries), 0), MAX_SERVER_RETRIES)
        self.max_calls = min(max(int(max_calls), 1), MAX_SERVER_CALLS)
        self._call_count = 0
        self._budget_exhaustion_logged = False
        self._lock = Lock()
        self.provider = str(provider or "UNKNOWN_NOT_INSTRUMENTED")
        self.model_name = str(model_name or "UNKNOWN_NOT_INSTRUMENTED")
        self.semantic_runtime = semantic_runtime
        self.error_log_artifact_path = validate_artifact_path(error_log_artifact_path)
        # 2026-10-06 (Phase C controlled single-request verification round):
        # additive, off by default -- every existing caller that never
        # passes enable_request_response_audit keeps zero new behavior,
        # zero new files written, zero new attempt_id allocation.
        # execution_id falls back to run_id so passing neither is a no-op.
        self.execution_id = str(execution_id) if execution_id else self.run_id
        self._audit_enabled = bool(enable_request_response_audit)
        self._audit_write_failed = False
        self._attempt_counter = 0
        # 2026-10-06 (round 13): per-attempt audit identity now lives in the
        # module-level _current_audit_attempt contextvar, not a Gateway
        # instance attribute -- see that variable's own docstring.
        # 2026-10-01 (NVDA Fresh Run request-shape budget task): per-task
        # model override, additive and empty by default -- every existing
        # caller that never passes this keeps every task on the one shared
        # ``model`` exactly as before. A dedicated model instance (not a
        # mutated shared one, and not a bare ``.bind()`` wrapper, which would
        # lose ``_get_request_payload`` for _request_control_snapshot's own
        # introspection) lets one task (e.g. alpha_classifier) carry its own
        # max_tokens without changing any other task's request shape, and
        # without any cross-task mutation race under concurrent dispatch.
        self._task_model_overrides: dict[str, Any] = (
            dict(task_model_overrides) if task_model_overrides else {}
        )
        # 2026-10-08 (T4 round 28): the run's provider-refusal stop (comqutor_alpha.run_provider_stop), attached by
        # the research pipeline (routes_research.run_research_request) and shared with the run's research-agent
        # layer. None (every other caller: recovery / evaluation drivers, tests) keeps the earlier behavior exactly.
        self.provider_stop: RunProviderStop | None = None
        self._provider_stop_logged = False

    def _provider_stop_refusal(self, task: str) -> dict[str, Any] | None:
        """Checked immediately before a request would be sent: the stop trigger when the run is stopped (logged
        once), else None."""
        if self.provider_stop is None:
            return None
        trigger = self.provider_stop.refusal(layer=LAYER_WEEK2, task=task)
        if trigger is not None and not self._provider_stop_logged:
            with self._lock:
                first, self._provider_stop_logged = not self._provider_stop_logged, True
            if first:
                self._log(task, STOP_ERROR_CODE, 0)
        return trigger

    def _note_provider_refusal(
        self, status_code: int | None, task: str, *, call_id: Any = None, attempt_id: Any = None, reason: Any = None
    ) -> bool:
        """A 401/403/429 answer: stops the run (first one wins). Returns True when THIS answer triggered the stop."""
        if self.provider_stop is None or status_code not in STOP_STATUS_CODES:
            return False
        return self.provider_stop.trigger(
            status_code=status_code, layer=LAYER_WEEK2, task=task, call_id=call_id, attempt_id=attempt_id, reason=reason
        )

    def _note_answer_after_stop(self, task: str, *, call_id: Any = None, attempt_id: Any = None, status: Any = None) -> None:
        if self.provider_stop is not None and self.provider_stop.triggered is not None:
            self.provider_stop.note_answer_after_stop(
                layer=LAYER_WEEK2, task=task, call_id=call_id, attempt_id=attempt_id, status_code=status
            )

    def _resolve_task_model(self, task: str) -> Any:
        return self._task_model_overrides.get(task, self._model)

    def task_timeout_seconds_for(self, task: str) -> float:
        return self._task_timeout_seconds.get(task, self.timeout_seconds)

    @property
    def call_count(self) -> int:
        with self._lock:
            return self._call_count

    def _reserve_call(self) -> bool:
        with self._lock:
            if self._call_count >= self.max_calls:
                return False
            self._call_count += 1
            return True

    def _log(self, task: str, error_code: str, attempt: int) -> None:
        # Step 5A Section 5 (controlled single-claim concurrency): append_
        # jsonl_record is a read-whole-file-then-rewrite operation, not a
        # true atomic append -- concurrent unlocked writers could silently
        # lose each other's lines. Serialized under the same lock
        # _reserve_call already uses, so concurrent workers' error-log
        # entries are never dropped.
        with self._lock:
            append_jsonl_record(
                self.run_id,
                self.error_log_artifact_path,
                {
                    "run_id": self.run_id,
                    "task": task,
                    "error_code": error_code,
                    "attempt": attempt,
                    "created_at": _now(),
                },
                output_root=self.output_root,
            )

    def _log_budget_exhausted_once(self, task: str, attempt: int) -> None:
        with self._lock:
            if self._budget_exhaustion_logged:
                return
            self._budget_exhaustion_logged = True
        self._log(task, "WEEK2_LLM_CALL_BUDGET_EXHAUSTED", attempt)

    def _log_runtime_error(self, task: str, error_code: str) -> None:
        """Keep cache/recording diagnostics outside the business-result path."""

        try:
            self._log(task, error_code, 0)
        except Exception:
            if self.semantic_runtime is not None:
                self.semantic_runtime.report_degraded(
                    "SEMANTIC_RUNTIME_ERROR_LOG_FAILED"
                )

    @property
    def audit_write_failed(self) -> bool:
        with self._lock:
            return self._audit_write_failed

    def _mark_audit_write_failed(self) -> None:
        with self._lock:
            self._audit_write_failed = True

    def _allocate_attempt_id(self) -> str:
        with self._lock:
            self._attempt_counter += 1
            return f"{self.execution_id}:{self._attempt_counter}"

    def _set_pending_audit_attempt(
        self,
        attempt_id: str,
        task: str,
        payload: Mapping[str, Any],
        *,
        claim_ids: Sequence[str] | None = None,
        semantic_call_id: str | None = None,
    ) -> contextvars.Token:
        """2026-10-06 (round 13): per-call-chain identity via contextvars,
        replacing the old single Gateway-wide dict (which could only ever
        track ONE in-flight attempt at a time, by construction). Never
        raises on concurrent use -- a second, concurrent call sets its OWN
        independent value; it does not observe or conflict with the first
        one's. The caller MUST pass the returned token to
        ``_reset_pending_audit_attempt`` (in a ``finally``) once this
        specific attempt is done, so a pooled worker thread that goes on to
        handle a LATER, unrelated attempt never sees a stale value left
        over from this one.

        ``claim_ids``/``semantic_call_id`` (2026-10-06, round 14): optional,
        explicit, out-of-band identity -- never derived from ``payload``
        (which for alpha_classifier never carries a claim_id at all, by
        design -- see invoke_json_with_trace's own caller). When supplied,
        ``_persist_request_audit``/``_persist_response_audit`` use these
        directly instead of falling back to ``_extract_claim_ids(payload)``,
        completing the claim_id -> semantic_call_id -> attempt_id ->
        request/response chain without ever touching what the model itself
        receives."""
        return _current_audit_attempt.set(
            {
                "attempt_id": attempt_id,
                "task": task,
                "payload": payload,
                "claim_ids": list(claim_ids) if claim_ids else None,
                "semantic_call_id": semantic_call_id,
            }
        )

    @staticmethod
    def _reset_pending_audit_attempt(token: contextvars.Token) -> None:
        _current_audit_attempt.reset(token)

    def _current_pending_audit_attempt(self) -> dict[str, Any] | None:
        return _current_audit_attempt.get()

    @staticmethod
    def _extract_claim_ids(payload: Mapping[str, Any]) -> list[str]:
        items = payload.get("items")
        if isinstance(items, list):
            return [str(item.get("claim_id")) for item in items if isinstance(item, Mapping) and item.get("claim_id")]
        claim_id = payload.get("claim_id")
        return [str(claim_id)] if claim_id else []

    @classmethod
    def _resolve_audit_claim_ids(cls, pending: Mapping[str, Any]) -> list[str]:
        """Prefers the explicit, out-of-band claim_ids registered via
        _set_pending_audit_attempt; falls back to the old payload-scanning
        heuristic only when a caller never supplied one (e.g. tasks that
        already carry real claim identity inside their own payload, like
        content_support_verification's "items" list -- unchanged)."""
        explicit = pending.get("claim_ids")
        if explicit:
            return list(explicit)
        return cls._extract_claim_ids(pending["payload"])

    def _persist_request_audit(self, request: Any) -> None:
        """Called by AuditingTransport with the LITERAL httpx.Request about
        to be sent. Raising here (e.g. disk full, invalid artifact path)
        means the caller (AuditingTransport.handle_request) never forwards
        the request to the wrapped transport -- nothing is actually sent."""
        pending = self._current_pending_audit_attempt()
        if self._provider_stop_refusal(pending["task"] if pending is not None else "UNKNOWN_NO_PENDING_ATTEMPT") is not None:
            # 2026-10-08 (T4 round 28): the literal last check before AuditingTransport forwards the request
            raise RunStoppedBeforeSendError(
                "WEEK2_LLM_RUN_STOPPED: an earlier request of this run got HTTP 401/403/429 -- not sent"
            )
        if pending is None:
            raise AuditingTransportError(
                "WEEK2_LLM_AUDIT_NO_PENDING_ATTEMPT: a request reached the auditing transport "
                "with no attempt registered via _set_pending_audit_attempt -- refusing to send "
                "an un-attributable request"
            )
        body_text = request.content.decode("utf-8", errors="replace")
        record = {
            "schema_version": REQUEST_AUDIT_SCHEMA_VERSION,
            "execution_id": self.execution_id,
            "attempt_id": pending["attempt_id"],
            "semantic_call_id": pending.get("semantic_call_id"),
            "task": pending["task"],
            "claim_ids": self._resolve_audit_claim_ids(pending),
            "method": request.method,
            "url": str(request.url),
            "headers": sanitize_headers(request.headers),
            "body": body_text,
            "body_sha256": sha256_text(body_text),
            "created_at": _now(),
        }
        # 2026-10-06 (round 13): append_jsonl_record is a real read-whole-
        # file-then-rewrite operation, not a true atomic append (same fact
        # already documented for _log's own error-log writes elsewhere in
        # this class) -- genuinely concurrent callers (now possible, since
        # this round removes the forced-serial compatibility shim) would
        # otherwise race on this read-modify-write and silently lose each
        # other's lines. Reproduced directly: an 8-claim, concurrency=4 test
        # wrote only 3 of 8 real request-audit records before this lock was
        # added. The lock protects ONLY this fast, local file write -- never
        # the network wait itself (which happens entirely outside this
        # method, in the caller's own call_with_timeout), so concurrent
        # Provider requests still genuinely overlap.
        with self._lock:
            append_jsonl_record(
                self.run_id, PROVIDER_REQUEST_AUDIT_ARTIFACT_PATH, record, output_root=self.output_root
            )

    def _persist_response_audit(self, request: Any, response: Any) -> None:
        """Called by AuditingTransport with the LITERAL httpx.Response
        received. If this raises, AuditingTransport still returns the
        response to its caller (the Provider already answered), but marks
        this Gateway's audit as failed so every subsequent attempt refuses
        to send (checked at the top of invoke_json_with_trace's loop)."""
        pending = self._current_pending_audit_attempt()
        attempt_id = pending["attempt_id"] if pending is not None else "UNKNOWN_NO_PENDING_ATTEMPT"
        task = pending["task"] if pending is not None else "UNKNOWN_NO_PENDING_ATTEMPT"
        # 2026-10-06 (round 14): the response record previously carried no
        # claim_ids/semantic_call_id at all -- a reader had to join it back
        # to its own request record (by attempt_id) to learn either. Now
        # self-contained, using the SAME pending-state this attempt's
        # request record already used (never re-derived, never guessed).
        claim_ids = self._resolve_audit_claim_ids(pending) if pending is not None else []
        semantic_call_id = pending.get("semantic_call_id") if pending is not None else None
        body_text = response.content.decode("utf-8", errors="replace")
        record = {
            "schema_version": RESPONSE_AUDIT_SCHEMA_VERSION,
            "execution_id": self.execution_id,
            "attempt_id": attempt_id,
            "semantic_call_id": semantic_call_id,
            "task": task,
            "claim_ids": claim_ids,
            "status_code": response.status_code,
            "headers": sanitize_headers(response.headers),
            "body": body_text,
            "body_sha256": sha256_text(body_text),
            "created_at": _now(),
        }
        # See _persist_request_audit's own comment -- same race, same fix.
        with self._lock:
            append_jsonl_record(
                self.run_id, PROVIDER_RESPONSE_AUDIT_ARTIFACT_PATH, record, output_root=self.output_root
            )
        # 2026-10-08 (T4 round 28): the earliest point a 401/403/429 is visible -- stop the run before the client
        # library even raises, so concurrent threads are refused as soon as possible
        self._note_provider_refusal(
            response.status_code, task, call_id=semantic_call_id, attempt_id=attempt_id, reason=body_text
        )

    def attach_semantic_runtime(self, semantic_runtime: SemanticRuntimeSession) -> None:
        if not isinstance(semantic_runtime, SemanticRuntimeSession):
            raise TypeError("semantic_runtime must be a SemanticRuntimeSession")
        if semantic_runtime.run_id != self.run_id:
            raise ValueError("SEMANTIC_RUNTIME_RUN_ID_MISMATCH")
        self.semantic_runtime = semantic_runtime

    @staticmethod
    def prompt_identity_text(task: str) -> str:
        instruction = _TASK_INSTRUCTIONS.get(task)
        if instruction is None:
            raise ValueError(f"Unsupported Week 2 LLM task: {task}")
        return f"{_SHARED_JSON_ONLY_PROMPT_PREFIX}{instruction}{_PROMPT_IDENTITY_SEPARATOR}"

    @staticmethod
    def _provider_prompt_prefix(task: str) -> str:
        instruction = _TASK_INSTRUCTIONS.get(task)
        if instruction is None:
            raise ValueError(f"Unsupported Week 2 LLM task: {task}")
        return f"{_SHARED_JSON_ONLY_PROMPT_PREFIX}{instruction}{_INPUT_JSON_SEPARATOR}"

    @classmethod
    def prompt_identity_sha256(cls, task: str) -> str:
        return sha256_text(cls.prompt_identity_text(task))

    def _start_semantic_call(
        self,
        task: str,
        payload: Mapping[str, Any],
        *,
        claim_ids: Sequence[str] | None = None,
    ) -> tuple[SemanticCallTrace | None, Any | None, str | None]:
        if self.semantic_runtime is None:
            return None, None, None
        metadata = _TASK_RUNTIME_METADATA[task]
        started = self.semantic_runtime.start_call(
            task=metadata["semantic_task"],
            prompt_version=metadata["prompt_version"],
            prompt_sha256=self.prompt_identity_sha256(task),
            input_schema_version=metadata["input_schema_version"],
            output_schema_version=metadata["output_schema_version"],
            taxonomy_version=metadata["taxonomy_version"],
            input_payload=payload,
            claim_ids=claim_ids,
        )
        return started.trace_handle, started.cached_candidate, started.cache_error_code

    def invoke_json_with_trace(
        self,
        task: str,
        payload: Mapping[str, Any],
        validator: Callable[[Mapping[str, Any]], T],
        *,
        claim_ids: Sequence[str] | None = None,
    ) -> Week2LLMInvocation:
        """Run one logical request while leaving persistence finalization to its caller.

        ``claim_ids`` (2026-10-06, round 14, claim-identity traceability):
        optional, additive, out-of-band business identity for this call --
        e.g. alpha_classifier's own claim_id, which is never part of the
        LLM-facing ``payload`` (so adding it here changes neither the
        prompt the model receives nor the semantic cache key, which is
        derived purely from ``payload``). Every existing caller that never
        passes it keeps exactly its current behavior (claim_ids resolved
        the old way, from ``payload`` itself, where that already worked --
        e.g. content_support_verification's own "items" list)."""

        instruction = _TASK_INSTRUCTIONS.get(task)
        if instruction is None:
            raise ValueError(f"Unsupported Week 2 LLM task: {task}")
        serialized = json.dumps(dict(payload), ensure_ascii=False, default=str)
        prompt = f"{self._provider_prompt_prefix(task)}{serialized}"
        trace, cached_candidate, cache_error_code = self._start_semantic_call(
            task, payload, claim_ids=claim_ids
        )
        semantic_call_id = trace.call_id if trace is not None else None

        if cached_candidate is not None:
            try:
                if not isinstance(cached_candidate, Mapping):
                    raise TypeError("cached task candidate must be an object")
                validated = validator(cached_candidate)
            except Exception:
                cache_error_code = "WEEK2_LLM_CACHE_VALIDATION_FAILED"
                if trace is not None:
                    trace.cache_hit = False
                    trace.cache_error_code = cache_error_code
                if self.semantic_runtime is not None:
                    self.semantic_runtime.report_degraded(cache_error_code)
                self._log_runtime_error(task, cache_error_code)
            else:
                return Week2LLMInvocation(
                    parsed_output=dict(cached_candidate),
                    validated_output=validated,
                    trace_handle=trace,
                    cache_hit=True,
                    provider_called=False,
                    provider_status="not_called",
                    retry_count=0,
                    provider_attempt_count=0,
                    validation_attempted=True,
                    validation_accepted=True,
                    cache_error_code=cache_error_code,
                )
        elif cache_error_code is not None:
            self._log_runtime_error(task, "WEEK2_LLM_CACHE_READ_FAILED")

        if len(serialized) > MAX_PROMPT_PAYLOAD_CHARS:
            self._log(task, "WEEK2_LLM_INPUT_TOO_LARGE", 0)
            return Week2LLMInvocation(
                parsed_output=None,
                validated_output=None,
                trace_handle=trace,
                cache_hit=False,
                provider_called=False,
                provider_status="not_called",
                retry_count=0,
                provider_attempt_count=0,
                validation_attempted=False,
                validation_accepted=False,
                error_code="WEEK2_LLM_INPUT_TOO_LARGE",
                cache_error_code=cache_error_code,
                input_chars=len(serialized),
                input_limit_chars=MAX_PROMPT_PAYLOAD_CHARS,
            )

        provider_attempts = 0
        validation_attempted = False
        last_parsed: dict[str, Any] | None = None
        last_provider_status = "provider_error"
        last_error_code: str | None = "WEEK2_LLM_PROVIDER_ERROR"
        last_token_usage: dict[str, int | None] | None = None
        last_request_control: dict[str, Any] | None = None
        last_provider_response: dict[str, Any] | None = None
        # 2026-10-01 (v7 limited real-verification round): one entry per
        # REAL attempt, success or failure -- never overwritten by a later
        # retry the way last_provider_response/last_token_usage are.
        # Confirmed necessary by a real execution (t3live_20261001T230846Z_
        # 16d44096): the first attempt's own raw usage/finish_reason was
        # otherwise unrecoverable once a retry replaced it in the "last_*"
        # variables, even though it was a real, billed Provider call.
        request_attempts: list[dict[str, Any]] = []
        effective_max_retries = _resolve_task_max_retries(task, self.max_retries)
        task_model = self._resolve_task_model(task)
        for attempt in range(1, effective_max_retries + 2):
            if self._provider_stop_refusal(task) is not None:
                # 2026-10-08 (T4 round 28): an earlier request of this run got HTTP 401/403/429 -- nothing further
                # is sent (this claim's retry or a queued claim); a never-sent call is "not_called" with the stop
                # code, which every task maps to "not sent", never to a valid NONE.
                if provider_attempts == 0:
                    last_provider_status = "not_called"
                    last_error_code = STOP_ERROR_CODE
                break
            if self._audit_enabled and self.audit_write_failed:
                # 2026-10-06: a prior attempt's request or response audit
                # record failed to persist -- refuse to send anything
                # further through this Gateway instance (this claim's
                # remaining retries AND every subsequent claim), rather
                # than keep producing real, billed calls with no reliable
                # wire-level audit trail.
                last_provider_status = "audit_unavailable"
                last_error_code = "WEEK2_LLM_AUDIT_WRITE_FAILED"
                break
            if not self._reserve_call():
                self._log_budget_exhausted_once(task, attempt)
                if provider_attempts == 0:
                    last_provider_status = "budget_exhausted"
                    last_error_code = "WEEK2_LLM_CALL_BUDGET_EXHAUSTED"
                break
            provider_attempts += 1
            # Captured for every real attempt, success or failure, since it
            # reflects what was actually about to be/was sent -- not just the
            # eventually-accepted attempt. Cheap (no network call) and the
            # same value on every retry (same model instance, same prompt).
            last_request_control = _request_control_snapshot(task_model, prompt)
            attempt_id = self._allocate_attempt_id() if self._audit_enabled else None
            audit_token: contextvars.Token | None = None
            if self._audit_enabled:
                audit_token = self._set_pending_audit_attempt(
                    attempt_id, task, payload,
                    claim_ids=claim_ids, semantic_call_id=semantic_call_id,
                )
            attempt_provider_status = "provider_error"
            attempt_error_code: str | None = "WEEK2_LLM_PROVIDER_ERROR"
            attempt_provider_response: dict[str, Any] | None = None
            try:
                try:
                    response = call_with_timeout(
                        lambda: task_model.invoke(prompt),
                        self.task_timeout_seconds_for(task),
                    )
                finally:
                    # 2026-10-06 (round 13): resets THIS attempt's own
                    # context value, in THIS (outer, Thread-A) context --
                    # never the nested call_with_timeout worker thread's own
                    # copy, which is independent once contextvars.
                    # copy_context() captured it. A late-completing,
                    # previously-timed-out background call keeps its own
                    # frozen copy regardless of this reset, so its eventual
                    # audit write still attributes correctly to ITS OWN
                    # attempt_id, never a newer one allocated after this
                    # reset runs.
                    if self._audit_enabled and audit_token is not None:
                        self._reset_pending_audit_attempt(audit_token)
                self._note_answer_after_stop(task, call_id=semantic_call_id, attempt_id=attempt_id, status="answered")
                # Reuses the same real-response extraction already proven in
                # invoke_prebuilt_json_prompt below -- this method (the one
                # the three standard tasks actually call) never threaded
                # token usage through to Week2LLMInvocation/SemanticCallRecord
                # until this round; never estimates, stays None when the
                # Provider genuinely returns nothing usable.
                last_token_usage = _response_token_usage(response)
                last_provider_response = _response_provider_metadata(response)
                attempt_provider_response = last_provider_response
                last_parsed = _strict_json_object(response)
                validation_attempted = True
                validated = validator(last_parsed)
                request_attempts.append(
                    _attempt_record(attempt, "success", None, attempt_provider_response, attempt_id)
                )
                return Week2LLMInvocation(
                    parsed_output=last_parsed,
                    validated_output=validated,
                    trace_handle=trace,
                    cache_hit=False,
                    provider_called=True,
                    provider_status="success",
                    retry_count=max(0, provider_attempts - 1),
                    provider_attempt_count=provider_attempts,
                    validation_attempted=True,
                    validation_accepted=True,
                    cache_error_code=cache_error_code,
                    token_usage=last_token_usage,
                    request_control=last_request_control,
                    provider_response_metadata=last_provider_response,
                    request_attempts=tuple(request_attempts),
                )
            except TimeoutError:
                attempt_provider_status = last_provider_status = "timeout"
                attempt_error_code = last_error_code = "WEEK2_LLM_TIMEOUT"
                self._note_answer_after_stop(task, call_id=semantic_call_id, attempt_id=attempt_id, status="timeout")
            except json.JSONDecodeError:
                attempt_provider_status = last_provider_status = "provider_error"
                attempt_error_code = last_error_code = "WEEK2_LLM_INVALID_JSON"
                attempt_provider_response = last_provider_response
            except (TypeError, ValueError, KeyError):
                attempt_provider_status = last_provider_status = "success"
                attempt_error_code = last_error_code = "WEEK2_LLM_VALIDATION_FAILED"
                attempt_provider_response = last_provider_response
            except Exception as exc:
                # 2026-10-06: a request-audit-save failure raises
                # AuditingTransportError from deep inside AuditingTransport.
                # handle_request, which the underlying OpenAI SDK's own
                # exception handling may re-wrap (e.g. into its own
                # APIConnectionError) before it reaches here -- checked via
                # the exception's __cause__/__context__ chain, not a bare
                # isinstance, so this is detected either way. When found,
                # the request was genuinely never forwarded to the wrapped
                # transport (AuditingTransport raises BEFORE calling it),
                # so nothing was sent -- every subsequent attempt/claim
                # through this Gateway instance is then refused too.
                auditing_failure = _find_auditing_transport_error(exc)
                if isinstance(auditing_failure, RunStoppedBeforeSendError):
                    # 2026-10-08 (T4 round 28): refused at the transport, after the gateway check -- never sent
                    provider_attempts -= 1
                    if provider_attempts == 0:
                        last_provider_status = "not_called"
                        last_error_code = STOP_ERROR_CODE
                    break
                if auditing_failure is not None:
                    self._mark_audit_write_failed()
                    attempt_provider_status = last_provider_status = "audit_unavailable"
                    attempt_error_code = last_error_code = "WEEK2_LLM_AUDIT_WRITE_FAILED"
                    request_attempts.append(
                        _attempt_record(attempt, attempt_provider_status, attempt_error_code, None, attempt_id)
                    )
                    self._log(task, last_error_code, attempt)
                    break
                # Step 5A Section 9: sub-classify transient provider failures
                # (rate limit / transport) so BUDGET_EXHAUSTED-adjacent
                # symptoms are auditable per-cause instead of one generic
                # bucket. Retry COUNT/bound behavior is unchanged -- this
                # only refines the recorded error_code.
                attempt_provider_status = last_provider_status = "provider_error"
                transient_reason = _transient_provider_error_reason(exc)
                if transient_reason == "HTTP_429":
                    attempt_error_code = last_error_code = "WEEK2_LLM_RATE_LIMIT"
                elif transient_reason is not None:
                    attempt_error_code = last_error_code = "WEEK2_LLM_TRANSPORT_ERROR"
                else:
                    attempt_error_code = last_error_code = "WEEK2_LLM_PROVIDER_ERROR"
                refusal_status = _provider_status_code(exc)
                if refusal_status in STOP_STATUS_CODES and self.provider_stop is not None:
                    # 2026-10-08 (T4 round 28): stop the run; this attempt stays a failure and is not retried
                    refused_here = self._note_provider_refusal(
                        refusal_status, task, call_id=semantic_call_id, attempt_id=attempt_id, reason=exc
                    )
                    if not refused_here:
                        self._note_answer_after_stop(
                            task, call_id=semantic_call_id, attempt_id=attempt_id, status=refusal_status
                        )
                    request_attempts.append(
                        _attempt_record(attempt, attempt_provider_status, attempt_error_code, attempt_provider_response, attempt_id)
                    )
                    self._log(task, last_error_code, attempt)
                    break
                self._note_answer_after_stop(task, call_id=semantic_call_id, attempt_id=attempt_id, status="provider_error")
            # 2026-10-01: a response whose own finish_reason is confirmed
            # "length" (genuine truncation against the configured output
            # cap, not a formatting/parsing defect) is never retried under
            # the SAME configuration -- a retry would face the identical
            # token budget and, empirically (t3live_20261001T230846Z_
            # 16d44096), reliably truncates again, wasting a real billed
            # request. The specific error_code is preserved (never folded
            # back into the generic WEEK2_LLM_VALIDATION_FAILED/
            # WEEK2_LLM_INVALID_JSON it would otherwise have been), so a
            # downstream reader can tell "truncated" apart from "malformed
            # for some other reason" and from the model's own explicit
            # decision=none.
            truncated_this_attempt = (
                attempt_provider_response is not None
                and attempt_provider_response.get("finish_reason") == "length"
            )
            if truncated_this_attempt:
                attempt_error_code = last_error_code = "WEEK2_LLM_OUTPUT_TRUNCATED"
                # The "success" provider_status used by the generic
                # WEEK2_LLM_VALIDATION_FAILED/WEEK2_LLM_INVALID_JSON paths
                # deliberately causes finalize_semantic_invocation's own
                # persisted_error_code filter to drop error_code entirely
                # (required by validate_semantic_call_record's own
                # "success cannot carry an error" invariant). Truncation is
                # a genuine provider-side failure to deliver usable output
                # (not "valid response, bad content") and must keep its
                # error_code visible in the persisted record -- "provider_
                # error" is both the correct classification and the one
                # persisted_error_code's filter actually preserves.
                attempt_provider_status = last_provider_status = "provider_error"
            request_attempts.append(
                _attempt_record(
                    attempt, attempt_provider_status, attempt_error_code, attempt_provider_response, attempt_id
                )
            )
            self._log(task, last_error_code, attempt)
            if truncated_this_attempt:
                break

        return Week2LLMInvocation(
            parsed_output=last_parsed,
            validated_output=None,
            trace_handle=trace,
            cache_hit=False,
            provider_called=provider_attempts > 0,
            provider_status=last_provider_status,
            retry_count=max(0, provider_attempts - 1),
            provider_attempt_count=provider_attempts,
            validation_attempted=validation_attempted,
            validation_accepted=False,
            error_code=last_error_code,
            cache_error_code=cache_error_code,
            token_usage=last_token_usage,
            request_control=last_request_control,
            provider_response_metadata=last_provider_response,
            request_attempts=tuple(request_attempts),
        )

    def invoke_prebuilt_json_prompt(
        self,
        *,
        task: str,
        prompt: str,
        prompt_version: str,
        prompt_sha256: str,
        input_schema_version: str,
        output_schema_version: str,
        payload_for_identity: Mapping[str, Any],
        validator: Callable[[Mapping[str, Any]], T],
        taxonomy_version: str | None = None,
        max_prompt_chars: int = MAX_PREBUILT_PROMPT_CHARS,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        execution_policy_source: str | None = None,
    ) -> Week2LLMInvocation:
        """Send an already-fully-built prompt through the existing retry/
        timeout/budget/semantic-runtime machinery, without touching the fixed
        ``_TASK_INSTRUCTIONS``/``_TASK_RUNTIME_METADATA`` tables the three
        existing Week2 tasks (``claim_batch_enrichment``, ``alpha_classifier``,
        ``structure_extractor``) use for their own prompt/version identity.

        Phase 1B.1 evaluation-CLI-only seam: the caller supplies the frozen
        Phase 1A Shadow prompt text verbatim (never built or altered here) and
        its own prompt/schema identity. This method never reads
        ``_TASK_INSTRUCTIONS`` and therefore cannot silently reuse or drift
        one of the three existing task prompts. By default, retry, timeout,
        and the per-run call budget are the same ``self.max_retries``/
        ``self.timeout_seconds``/``self._reserve_call()`` the three existing
        tasks already use -- no new retry behavior is introduced.

        ``timeout_seconds``/``max_retries`` (Phase 1 Master task-level
        execution policy, section 3): when explicitly supplied by the
        caller, they override the Gateway's shared instance defaults for
        THIS call only -- ``self.timeout_seconds``/``self.max_retries``
        (the constructor defaults shared by every other call, including the
        three existing tasks) are never mutated. Never derived from Provider
        output or report text; always a literal caller-supplied value.
        """
        effective_timeout = self.timeout_seconds
        if timeout_seconds is not None:
            effective_timeout = min(max(float(timeout_seconds), 0.01), MAX_TASK_TIMEOUT_SECONDS)
        effective_retries = self.max_retries
        if max_retries is not None:
            effective_retries = min(max(int(max_retries), 0), MAX_SERVER_RETRIES)

        trace: SemanticCallTrace | None = None
        cached_candidate: Any | None = None
        cache_error_code: str | None = None
        if self.semantic_runtime is not None:
            started = self.semantic_runtime.start_call(
                task=task,
                prompt_version=prompt_version,
                prompt_sha256=prompt_sha256,
                input_schema_version=input_schema_version,
                output_schema_version=output_schema_version,
                taxonomy_version=taxonomy_version,
                input_payload=payload_for_identity,
            )
            trace, cached_candidate, cache_error_code = (
                started.trace_handle,
                started.cached_candidate,
                started.cache_error_code,
            )

        if cached_candidate is not None:
            try:
                if not isinstance(cached_candidate, Mapping):
                    raise TypeError("cached task candidate must be an object")
                validated = validator(cached_candidate)
            except Exception:
                cache_error_code = "WEEK2_LLM_CACHE_VALIDATION_FAILED"
                if trace is not None:
                    trace.cache_hit = False
                    trace.cache_error_code = cache_error_code
                if self.semantic_runtime is not None:
                    self.semantic_runtime.report_degraded(cache_error_code)
                self._log_runtime_error(task, cache_error_code)
            else:
                return Week2LLMInvocation(
                    parsed_output=dict(cached_candidate),
                    validated_output=validated,
                    trace_handle=trace,
                    cache_hit=True,
                    provider_called=False,
                    provider_status="not_called",
                    retry_count=0,
                    provider_attempt_count=0,
                    validation_attempted=True,
                    validation_accepted=True,
                    cache_error_code=cache_error_code,
                    effective_timeout_seconds=effective_timeout,
                    effective_max_retries=effective_retries,
                    execution_policy_source=execution_policy_source,
                )
        elif cache_error_code is not None:
            self._log_runtime_error(task, "WEEK2_LLM_CACHE_READ_FAILED")

        if len(prompt) > max_prompt_chars:
            self._log(task, "WEEK2_LLM_INPUT_TOO_LARGE", 0)
            return Week2LLMInvocation(
                parsed_output=None,
                validated_output=None,
                trace_handle=trace,
                cache_hit=False,
                provider_called=False,
                provider_status="not_called",
                retry_count=0,
                provider_attempt_count=0,
                validation_attempted=False,
                validation_accepted=False,
                error_code="WEEK2_LLM_INPUT_TOO_LARGE",
                cache_error_code=cache_error_code,
                effective_timeout_seconds=effective_timeout,
                effective_max_retries=effective_retries,
                execution_policy_source=execution_policy_source,
                input_chars=len(prompt),
                input_limit_chars=max_prompt_chars,
            )

        provider_attempts = 0
        validation_attempted = False
        last_parsed: dict[str, Any] | None = None
        last_provider_status = "provider_error"
        last_error_code: str | None = "WEEK2_LLM_PROVIDER_ERROR"
        response_received = False
        token_usage: dict[str, int | None] | None = None
        attempt_history: list[dict[str, Any]] = []
        for attempt in range(1, effective_retries + 2):
            if self._provider_stop_refusal(task) is not None:
                # 2026-10-08 (T4 round 28): see invoke_json_with_trace -- nothing further is sent
                if provider_attempts == 0:
                    last_provider_status = "not_called"
                    last_error_code = STOP_ERROR_CODE
                break
            if not self._reserve_call():
                self._log_budget_exhausted_once(task, attempt)
                if provider_attempts == 0:
                    last_provider_status = "budget_exhausted"
                    last_error_code = "WEEK2_LLM_CALL_BUDGET_EXHAUSTED"
                    attempt_history.append(
                        {
                            "attempt": attempt,
                            "status": "budget_exhausted",
                            "retry_eligible": False,
                            "retry_reason": None,
                            "retry_delay_seconds": None,
                            "error_code": last_error_code,
                        }
                    )
                break
            provider_attempts += 1
            try:
                response = call_with_timeout(
                    lambda: self._model.invoke(prompt),
                    effective_timeout,
                )
                response_received = True
                token_usage = _response_token_usage(response)
            except TimeoutError:
                last_provider_status = "timeout"
                last_error_code = "WEEK2_LLM_TIMEOUT"
                retry_reason = "TIMEOUT"
                should_retry = attempt <= effective_retries
                attempt_history.append(
                    {
                        "attempt": attempt,
                        "status": "timeout",
                        "retry_eligible": True,
                        "retry_reason": retry_reason,
                        "retry_delay_seconds": 0.0 if should_retry else None,
                        "error_code": last_error_code,
                    }
                )
                self._log(task, last_error_code, attempt)
                if should_retry:
                    continue
                break
            except Exception as exc:
                if isinstance(_find_auditing_transport_error(exc), RunStoppedBeforeSendError):
                    provider_attempts -= 1
                    if provider_attempts == 0:
                        last_provider_status = "not_called"
                        last_error_code = STOP_ERROR_CODE
                    break
                last_provider_status = "provider_error"
                last_error_code = "WEEK2_LLM_PROVIDER_ERROR"
                retry_reason = _transient_provider_error_reason(exc)
                refusal_status = _provider_status_code(exc)
                if refusal_status in STOP_STATUS_CODES and self.provider_stop is not None:
                    self._note_provider_refusal(refusal_status, task, reason=exc)
                    retry_reason = None  # T4 round 28: a refusal stops the run and is never retried
                should_retry = retry_reason is not None and attempt <= effective_retries
                attempt_history.append(
                    {
                        "attempt": attempt,
                        "status": "provider_error",
                        "retry_eligible": retry_reason is not None,
                        "retry_reason": retry_reason,
                        "retry_delay_seconds": 0.0 if should_retry else None,
                        "error_code": last_error_code,
                    }
                )
                self._log(task, last_error_code, attempt)
                if should_retry:
                    continue
                break

            try:
                last_parsed = _strict_json_object(response)
            except (json.JSONDecodeError, TypeError, ValueError):
                last_provider_status = "provider_error"
                last_error_code = "WEEK2_LLM_INVALID_JSON"
                attempt_history.append(
                    {
                        "attempt": attempt,
                        "status": "invalid_json",
                        "retry_eligible": False,
                        "retry_reason": None,
                        "retry_delay_seconds": None,
                        "error_code": last_error_code,
                    }
                )
                self._log(task, last_error_code, attempt)
                break

            validation_attempted = True
            try:
                validated = validator(last_parsed)
            except (TypeError, ValueError, KeyError):
                last_provider_status = "success"
                last_error_code = "WEEK2_LLM_VALIDATION_FAILED"
                attempt_history.append(
                    {
                        "attempt": attempt,
                        "status": "validation_rejected",
                        "retry_eligible": False,
                        "retry_reason": None,
                        "retry_delay_seconds": None,
                        "error_code": last_error_code,
                    }
                )
                self._log(task, last_error_code, attempt)
                break
            else:
                attempt_history.append(
                    {
                        "attempt": attempt,
                        "status": "success",
                        "retry_eligible": False,
                        "retry_reason": None,
                        "retry_delay_seconds": None,
                        "error_code": None,
                    }
                )
                return Week2LLMInvocation(
                    parsed_output=last_parsed,
                    validated_output=validated,
                    trace_handle=trace,
                    cache_hit=False,
                    provider_called=True,
                    provider_status="success",
                    retry_count=max(0, provider_attempts - 1),
                    provider_attempt_count=provider_attempts,
                    validation_attempted=True,
                    validation_accepted=True,
                    cache_error_code=cache_error_code,
                    effective_timeout_seconds=effective_timeout,
                    effective_max_retries=effective_retries,
                    execution_policy_source=execution_policy_source,
                    response_received=True,
                    token_usage=token_usage,
                    attempt_history=tuple(attempt_history),
                )

        return Week2LLMInvocation(
            parsed_output=last_parsed,
            validated_output=None,
            trace_handle=trace,
            cache_hit=False,
            provider_called=provider_attempts > 0,
            provider_status=last_provider_status,
            retry_count=max(0, provider_attempts - 1),
            provider_attempt_count=provider_attempts,
            validation_attempted=validation_attempted,
            validation_accepted=False,
            error_code=last_error_code,
            cache_error_code=cache_error_code,
            effective_timeout_seconds=effective_timeout,
            effective_max_retries=effective_retries,
            execution_policy_source=execution_policy_source,
            response_received=response_received,
            token_usage=token_usage,
            attempt_history=tuple(attempt_history),
        )

    def finalize_semantic_invocation(
        self,
        invocation: Week2LLMInvocation,
        *,
        accepted: bool,
        fallback_reason: str | None = None,
    ) -> None:
        """Persist/cache after the task-specific caller accepts or rejects."""

        if self.semantic_runtime is None or invocation.trace_handle is None:
            return
        execution_policy = None
        if invocation.execution_policy_source is not None:
            execution_policy = {
                "schema_version": EXECUTION_POLICY_SCHEMA_VERSION,
                "effective_timeout_seconds": invocation.effective_timeout_seconds,
                "effective_max_retries": invocation.effective_max_retries,
                "execution_policy_source": invocation.execution_policy_source,
                "first_attempt_status": (
                    invocation.attempt_history[0].get("status")
                    if invocation.attempt_history
                    else None
                ),
                "retry_reason": next(
                    (
                        item.get("retry_reason")
                        for item in invocation.attempt_history
                        if item.get("retry_delay_seconds") is not None
                    ),
                    None,
                ),
                "retry_delay_seconds": next(
                    (
                        item.get("retry_delay_seconds")
                        for item in invocation.attempt_history
                        if item.get("retry_delay_seconds") is not None
                    ),
                    None,
                ),
                "final_status": (
                    invocation.attempt_history[-1].get("status")
                    if invocation.attempt_history
                    else invocation.provider_status
                ),
                "attempt_history": [dict(item) for item in invocation.attempt_history],
            }
        try:
            if accepted:
                self.semantic_runtime.finalize_call(
                    invocation.trace_handle,
                    provider_status=invocation.provider_status,
                    retry_count=invocation.retry_count,
                    validation_status="accepted",
                    accepted_candidate=invocation.parsed_output,
                    fallback_used=False,
                    fallback_reason=None,
                    error_code=None,
                    execution_policy=execution_policy,
                    token_usage=invocation.token_usage,
                    request_control=invocation.request_control,
                    provider_response=invocation.provider_response_metadata,
                    request_attempts=invocation.request_attempts,
                )
                return

            validation_status = "rejected" if invocation.validation_attempted else "not_run"
            reason = fallback_reason or invocation.error_code or "WEEK2_LLM_DETERMINISTIC_FALLBACK"
            persisted_error_code = (
                invocation.error_code
                if invocation.provider_status in {"timeout", "provider_error", "budget_exhausted"}
                else (
                    invocation.error_code if invocation.provider_status == "not_called" else None
                )
            )
            error_message = None
            if invocation.error_code == "WEEK2_LLM_INPUT_TOO_LARGE" and invocation.input_chars is not None:
                error_message = input_too_large_error_message(invocation.input_chars, invocation.input_limit_chars)
            self.semantic_runtime.finalize_call(
                invocation.trace_handle,
                provider_status=invocation.provider_status,
                retry_count=invocation.retry_count,
                validation_status=validation_status,
                accepted_candidate=None,
                fallback_used=True,
                fallback_reason=reason,
                error_code=persisted_error_code,
                # passed only when set, so a semantic runtime without the parameter keeps working unchanged
                **({"error_message": error_message} if error_message is not None else {}),
                execution_policy=execution_policy,
                token_usage=invocation.token_usage,
                request_control=invocation.request_control,
                provider_response=invocation.provider_response_metadata,
                request_attempts=invocation.request_attempts,
            )
        except Exception:
            self.semantic_runtime.report_degraded(
                "SEMANTIC_CALL_FINALIZATION_FAILED"
            )

    def _invoke_json_legacy(
        self,
        task: str,
        payload: Mapping[str, Any],
        validator: Callable[[Mapping[str, Any]], T],
    ) -> T | None:
        """The pre-Phase-0.6B execution path, retained byte-for-byte in behavior."""

        instruction = _TASK_INSTRUCTIONS.get(task)
        if instruction is None:
            raise ValueError(f"Unsupported Week 2 LLM task: {task}")

        serialized = json.dumps(dict(payload), ensure_ascii=False, default=str)
        if len(serialized) > MAX_PROMPT_PAYLOAD_CHARS:
            self._log(task, "WEEK2_LLM_INPUT_TOO_LARGE", 0)
            return None
        prompt = f"{self._provider_prompt_prefix(task)}{serialized}"

        for attempt in range(1, self.max_retries + 2):
            if self._provider_stop_refusal(task) is not None:
                return None
            if not self._reserve_call():
                self._log_budget_exhausted_once(task, attempt)
                return None
            try:
                response = call_with_timeout(
                    lambda: self._model.invoke(prompt),
                    self.timeout_seconds,
                )
                parsed = _strict_json_object(response)
                return validator(parsed)
            except TimeoutError:
                error_code = "WEEK2_LLM_TIMEOUT"
            except json.JSONDecodeError:
                error_code = "WEEK2_LLM_INVALID_JSON"
            except (TypeError, ValueError, KeyError):
                error_code = "WEEK2_LLM_VALIDATION_FAILED"
            except Exception as exc:
                error_code = "WEEK2_LLM_PROVIDER_ERROR"
                if self.provider_stop is not None and _provider_status_code(exc) in STOP_STATUS_CODES:
                    self._note_provider_refusal(_provider_status_code(exc), task, reason=exc)
                    self._log(task, error_code, attempt)
                    return None
            self._log(task, error_code, attempt)
        return None

    def invoke_json(
        self,
        task: str,
        payload: Mapping[str, Any],
        validator: Callable[[Mapping[str, Any]], T],
    ) -> T | None:
        if self.semantic_runtime is None:
            return self._invoke_json_legacy(task, payload, validator)
        invocation = self.invoke_json_with_trace(task, payload, validator)
        accepted = invocation.validation_accepted
        self.finalize_semantic_invocation(invocation, accepted=accepted)
        return invocation.validated_output if accepted else None


def _log_configuration_error(run_id: str, output_root: Any, error_code: str) -> None:
    append_jsonl_record(
        run_id,
        ERROR_LOG_ARTIFACT_PATH,
        {
            "run_id": run_id,
            "task": "gateway_initialization",
            "error_code": error_code,
            "attempt": 0,
            "created_at": _now(),
        },
        output_root=output_root,
    )


class _AuditTransportGatewayRef:
    """Bridges AuditingTransport's callbacks (built before the Gateway
    exists -- the model/client must be constructed first) to the Gateway
    instance that owns the actual persistence methods. Set exactly once,
    immediately after the real Week2LLMGateway below is constructed."""

    def __init__(self) -> None:
        self.gateway: Week2LLMGateway | None = None

    def save_request(self, request: Any) -> None:
        if self.gateway is None:
            raise AuditingTransportError(
                "WEEK2_LLM_AUDIT_GATEWAY_NOT_ATTACHED: a request reached the auditing "
                "transport before its owning Gateway was constructed -- refusing to send"
            )
        self.gateway._persist_request_audit(request)

    def save_response(self, request: Any, response: Any) -> None:
        if self.gateway is None:
            return
        self.gateway._persist_response_audit(request, response)

    def on_response_save_failed(self) -> None:
        if self.gateway is not None:
            self.gateway._mark_audit_write_failed()


def resolve_server_week2_settings(*, explicit_request_response_audit: bool = False) -> dict[str, Any]:
    """The Week 2 gateway settings ``build_server_week2_llm_gateway`` uses,
    resolved from the server process environment and the selected execution
    profile -- one function, so run metadata and ``/ready`` report exactly
    what the builder builds. Never a credential (only whether a base URL is
    configured, not the URL itself)."""
    profile_error = None
    try:
        profile = resolve_week2_execution_profile()
    except UnknownWeek2ExecutionProfile:
        profile, profile_error = None, "WEEK2_LLM_PROFILE_UNKNOWN"
    audit = bool(explicit_request_response_audit) or (profile is not None and profile.request_response_audit) or _enabled(
        os.environ.get("COMQUTOR_WEEK2_LLM_ENABLE_REQUEST_AUDIT")
    )
    max_retries = _bounded_int(os.environ.get("COMQUTOR_WEEK2_LLM_MAX_RETRIES"), DEFAULT_MAX_RETRIES, 0, MAX_SERVER_RETRIES)
    if profile is not None:
        max_retries = profile.max_retries
    return {
        "enabled": week2_llm_enabled(),
        "profile": profile,
        "profile_error": profile_error,
        "request_response_audit": audit,
        "provider": (os.environ.get("COMQUTOR_WEEK2_LLM_PROVIDER") or os.environ.get("TRADINGAGENTS_LLM_PROVIDER") or "").strip(),
        "model_name": (os.environ.get("COMQUTOR_WEEK2_LLM_MODEL") or os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM") or "").strip(),
        "timeout_seconds": _bounded_float(os.environ.get("COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS"), DEFAULT_TIMEOUT_SECONDS, 1.0, 120.0),
        "max_retries": max_retries,
        "max_calls": _bounded_int(os.environ.get("COMQUTOR_WEEK2_LLM_MAX_CALLS"), DEFAULT_MAX_CALLS, 1, MAX_SERVER_CALLS),
        "base_url": os.environ.get("COMQUTOR_WEEK2_LLM_BASE_URL") or os.environ.get("TRADINGAGENTS_LLM_BACKEND_URL") or None,
    }


def describe_server_week2_effective_config() -> dict[str, Any]:
    """Non-secret, per-task view of ``resolve_server_week2_settings`` for run
    metadata and ``/ready``: the values a gateway built now would use."""
    from comqutor_alpha.structure_engine import content_support_llm

    settings = resolve_server_week2_settings()
    profile = settings["profile"]
    tasks = {}
    for task in ("content_support_verification", "alpha_classifier", "evidence_stance_classifier"):
        timeout = (
            float(profile.task_timeout_seconds[task])
            if profile is not None and task in profile.task_timeout_seconds
            else settings["timeout_seconds"]
        )
        tasks[task] = {
            "client_read_timeout_seconds": timeout,
            "application_timeout_seconds": min(timeout, MAX_TASK_TIMEOUT_SECONDS),
            "application_retries": _resolve_task_max_retries(task, settings["max_retries"]),
            "sdk_retries": 0,
        }
    batch_env = os.environ.get("COMQUTOR_WEEK2_CONTENT_SUPPORT_BATCH_SIZE")
    tasks["content_support_verification"]["batch_size"] = (
        profile.content_support_batch_size if profile is not None else (int(batch_env) if batch_env else content_support_llm.BATCH_SIZE)
    )
    tasks["content_support_verification"]["max_tokens"] = os.environ.get("COMQUTOR_WEEK2_CONTENT_SUPPORT_MAX_TOKENS") or None
    tasks["alpha_classifier"]["path"] = "single"
    tasks["alpha_classifier"]["concurrency"] = resolve_alpha_classifier_concurrency()
    tasks["alpha_classifier"]["max_tokens"] = os.environ.get("COMQUTOR_WEEK2_ALPHA_CLASSIFIER_MAX_TOKENS") or None
    tasks["evidence_stance_classifier"]["batch_size"] = 10
    tasks["evidence_stance_classifier"]["concurrency"] = resolve_evidence_stance_concurrency()
    return {
        "enabled": settings["enabled"],
        "execution_profile": profile.name if profile is not None else None,
        "profile_error": settings["profile_error"],
        "provider": settings["provider"] or None,
        "model": settings["model_name"] or None,
        "base_url_configured": settings["base_url"] is not None,
        "request_response_audit": settings["request_response_audit"],
        "max_calls": settings["max_calls"],
        "shared_timeout_seconds_other_tasks": settings["timeout_seconds"],
        "gateway_max_retries": settings["max_retries"],
        "tasks": tasks,
    }


def build_server_week2_llm_gateway(
    run_id: str,
    output_root: Any,
    *,
    max_tokens: int | None = None,
    execution_id: str | None = None,
    enable_request_response_audit: bool = False,
    _base_transport_for_testing: Any = None,
) -> Week2LLMGateway | None:
    """Build the existing TradingAgents provider only after explicit server opt-in.

    ``max_tokens`` (2026-09-30, fifth follow-up round): optional, additive,
    ``None`` by default -- every existing real production call site that
    never passes it keeps its exact current behavior (no output-length cap
    at the client level, as before). When a caller does supply it (e.g. an
    evaluation driver whose task has a known-small, fixed output shape), it
    is forwarded straight to the real client constructor and reaches the
    real ``ChatOpenAI``/``ChatAnthropic`` instance's own ``max_tokens``
    field -- never merely documented as "the output happens to be small".

    ``enable_request_response_audit`` (2026-10-06, Phase C controlled
    single-request verification round): optional, additive, ``False`` by
    default -- every existing real production call site that never passes
    this keeps zero new behavior, zero new httpx.Client construction, zero
    new files written. When ``True``, wraps the real client's httpx
    transport in ``AuditingTransport`` so every real request/response is
    saved at the literal wire boundary (see week2_llm_request_audit.py).
    ``_base_transport_for_testing`` is a narrow, explicit, underscore-
    prefixed test-only seam: tests pass an ``httpx.MockTransport`` here to
    fake ONLY the lowest HTTP layer while every other real function on this
    path (this builder, create_llm_client, Week2LLMGateway's real retry/
    budget loop) runs completely unmodified; production code never passes
    it, so ``None`` here always means the real default httpx transport.

    2026-10-06 (AMD Fresh Run production-wiring task): ``enable_request_
    response_audit``'s caller-supplied value (default ``False``) can now
    also be turned on via ``COMQUTOR_WEEK2_LLM_ENABLE_REQUEST_AUDIT`` --
    needed because ``run_research_request``'s own internal call to this
    function (the real path every live research run goes through) passes
    neither keyword explicitly; it only ever learns the real, per-run
    ``run_id`` after the TradingAgents graph itself has already run, so an
    external caller cannot pre-build a gateway with this flag and hand it
    in ahead of time. An explicit ``True``/``False`` argument still always
    wins over the env var. Unset env var and unset argument (every
    existing deployment): unchanged, audit off.
    """
    if not week2_llm_enabled():
        return None

    # 2026-10-08 (T3 closeout): an explicitly selected execution profile
    # (COMQUTOR_WEEK2_LLM_PROFILE) supplies the three measured tasks' own
    # client+application timeouts, the retry count and the audit switch; an
    # unknown profile name builds no gateway at all (nothing is sent).
    # 2026-10-08 (T4): the settings come from resolve_server_week2_settings,
    # the same function run metadata and /ready report from.
    settings = resolve_server_week2_settings(explicit_request_response_audit=enable_request_response_audit)
    if settings["profile_error"] is not None:
        _log_configuration_error(run_id, output_root, settings["profile_error"])
        return None
    profile = settings["profile"]
    enable_request_response_audit = settings["request_response_audit"]
    provider = settings["provider"]
    model_name = settings["model_name"]
    if not provider or not model_name:
        _log_configuration_error(run_id, output_root, "WEEK2_LLM_CONFIG_INCOMPLETE")
        return None
    timeout_seconds = settings["timeout_seconds"]
    max_retries = settings["max_retries"]
    max_calls = settings["max_calls"]
    base_url = settings["base_url"]

    audit_gateway_ref = _AuditTransportGatewayRef() if enable_request_response_audit else None

    def _audited_http_client_kwarg() -> dict[str, Any]:
        """2026-10-06 (AMD c904d4cc post-run audit, round 11): shared by
        EVERY real client construction below -- the default model AND every
        per-task override -- so a future per-task override can never again
        silently build an unaudited client the way alpha_classifier's and
        content_support_verification's own overrides did (confirmed via a
        real run: both bypassed AuditingTransport entirely, because each
        called create_llm_client(...) directly without this kwarg). Returns
        ``{}`` (no override at all) when auditing is disabled, so every
        existing unaudited deployment is completely unaffected. A FRESH
        httpx.Client/AuditingTransport pair is built on every call -- never
        shared across the default model and an override, since each backs a
        logically distinct LangChain client object."""
        if audit_gateway_ref is None:
            return {}
        import httpx

        base_transport = _base_transport_for_testing or httpx.HTTPTransport()
        return {
            "http_client": httpx.Client(
                transport=AuditingTransport(
                    base_transport,
                    save_request=audit_gateway_ref.save_request,
                    save_response=audit_gateway_ref.save_response,
                    on_response_save_failed=audit_gateway_ref.on_response_save_failed,
                )
            )
        }

    try:
        from tradingagents.llm_clients import create_llm_client

        client_kwargs: dict[str, Any] = {
            "provider": provider,
            "model": model_name,
            "base_url": base_url,
            "timeout": timeout_seconds,
            "max_retries": 0,
        }
        if max_tokens is not None:
            client_kwargs["max_tokens"] = int(max_tokens)
        client_kwargs.update(_audited_http_client_kwarg())
        client = create_llm_client(**client_kwargs)
        model = client.get_llm()
    except Exception:
        _log_configuration_error(run_id, output_root, "WEEK2_LLM_INITIALIZATION_FAILED")
        return None

    # 2026-10-01 (NVDA Fresh Run request-shape budget task): optional,
    # additive, per-task output-cap override for exactly one task
    # (alpha_classifier), opt-in via its own env var -- unset means no
    # override dict is even built, so every other task and every existing
    # deployment that never sets this var keeps the shared ``model`` (and
    # its shared ``max_tokens`` above, if any) exactly as before. A separate
    # client/model instance, not a mutation of ``model`` and not a
    # ``.bind()`` wrapper (which would drop ``_get_request_payload`` and
    # silently blind _request_control_snapshot's own auditing for this
    # task), so other tasks sharing ``model`` concurrently are never
    # affected and the real serialized request is still fully introspectable.
    task_model_overrides: dict[str, Any] = {}
    raw_alpha_classifier_max_tokens = os.environ.get(
        "COMQUTOR_WEEK2_ALPHA_CLASSIFIER_MAX_TOKENS"
    )
    if raw_alpha_classifier_max_tokens:
        try:
            alpha_classifier_max_tokens = int(raw_alpha_classifier_max_tokens)
        except ValueError:
            _log_configuration_error(
                run_id, output_root, "WEEK2_LLM_ALPHA_CLASSIFIER_MAX_TOKENS_INVALID"
            )
        else:
            try:
                alpha_classifier_client = create_llm_client(
                    provider=provider,
                    model=model_name,
                    base_url=base_url,
                    timeout=timeout_seconds,
                    max_retries=0,
                    max_tokens=alpha_classifier_max_tokens,
                    **_audited_http_client_kwarg(),
                )
                task_model_overrides["alpha_classifier"] = (
                    alpha_classifier_client.get_llm()
                )
            except Exception:
                _log_configuration_error(
                    run_id, output_root, "WEEK2_LLM_ALPHA_CLASSIFIER_MAX_TOKENS_INIT_FAILED"
                )

    # 2026-10-06 (AMD Fresh Run production-wiring task): same additive,
    # opt-in per-task output-cap override pattern as alpha_classifier
    # above, for content_support_verification -- unset means no override,
    # every existing deployment keeps the shared model's own max_tokens
    # exactly as before.
    raw_content_support_max_tokens = os.environ.get(
        "COMQUTOR_WEEK2_CONTENT_SUPPORT_MAX_TOKENS"
    )
    if raw_content_support_max_tokens:
        try:
            content_support_max_tokens = int(raw_content_support_max_tokens)
        except ValueError:
            _log_configuration_error(
                run_id, output_root, "WEEK2_LLM_CONTENT_SUPPORT_MAX_TOKENS_INVALID"
            )
        else:
            try:
                content_support_client = create_llm_client(
                    provider=provider,
                    model=model_name,
                    base_url=base_url,
                    timeout=timeout_seconds,
                    max_retries=0,
                    max_tokens=content_support_max_tokens,
                    **_audited_http_client_kwarg(),
                )
                task_model_overrides["content_support_verification"] = (
                    content_support_client.get_llm()
                )
            except Exception:
                _log_configuration_error(
                    run_id, output_root, "WEEK2_LLM_CONTENT_SUPPORT_MAX_TOKENS_INIT_FAILED"
                )

    # Profile: each of its tasks gets its own client whose read timeout is the
    # profile's value (the same audited construction, the same output cap
    # rule as above -- that task's own *_MAX_TOKENS env var, else the shared
    # ``max_tokens``), replacing any override built above for that task. A
    # client that cannot be built means the profile cannot be honored, so no
    # gateway is returned.
    task_max_tokens_env = {
        "alpha_classifier": "COMQUTOR_WEEK2_ALPHA_CLASSIFIER_MAX_TOKENS",
        "content_support_verification": "COMQUTOR_WEEK2_CONTENT_SUPPORT_MAX_TOKENS",
    }
    if profile is not None:
        for task, task_timeout in profile.task_timeout_seconds.items():
            task_cap: int | None = max_tokens
            raw_task_cap = os.environ.get(task_max_tokens_env.get(task, ""), "")
            # an invalid value was already logged as *_MAX_TOKENS_INVALID above; the shared cap applies, as it does without a profile
            with contextlib.suppress(ValueError):
                task_cap = int(raw_task_cap) if raw_task_cap else task_cap
            profile_client_kwargs: dict[str, Any] = {
                "provider": provider,
                "model": model_name,
                "base_url": base_url,
                "timeout": float(task_timeout),
                "max_retries": 0,
            }
            if task_cap is not None:
                profile_client_kwargs["max_tokens"] = int(task_cap)
            try:
                task_model_overrides[task] = create_llm_client(
                    **profile_client_kwargs, **_audited_http_client_kwarg()
                ).get_llm()
            except Exception:
                _log_configuration_error(run_id, output_root, "WEEK2_LLM_PROFILE_TASK_CLIENT_INIT_FAILED")
                return None

    gateway = Week2LLMGateway(
        model,
        run_id=run_id,
        output_root=output_root,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        max_calls=max_calls,
        provider=provider,
        model_name=model_name,
        task_model_overrides=task_model_overrides or None,
        execution_id=execution_id,
        enable_request_response_audit=enable_request_response_audit,
        task_timeout_seconds=profile.task_timeout_seconds if profile is not None else None,
    )
    gateway.execution_profile = profile.name if profile is not None else None
    if audit_gateway_ref is not None:
        audit_gateway_ref.gateway = gateway
    return gateway
