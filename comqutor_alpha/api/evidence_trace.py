"""T1 closure: the claim-level evidence trace.

For one saved run this answers, per claim and from the run's OWN saved artifacts only (no model, no network, no
write): what source material the claim rests on and where in it, how that material was verified, which Alpha the
claim was matched to, what its stance/relation toward that Alpha is and who decided it, and what it actually
contributed to the official score -- as four SEPARATE statuses (source support / Alpha match / stance / scoring),
never one blended "verified" flag.

Design rules (John T1-D/E):

* the four statuses are independent. Verified source support is not a relevance judgment, a matched Alpha is not a
  stance, and a stance is not a score contribution;
* a missing step is reported as missing, with the reason: ``not linked``, ``verification not completed
  (technical)``, ``partially supported``, ``model judged insufficient``, ``relation unresolved`` ... -- never as a
  model judgment the model did not make. A rule-based zero match score is reported as a rule score, not as "the
  model judged this irrelevant";
* an Agent writing "verified" in its own report text is displayed as that wording (``agent_wording``) next to the
  system's own result and never substitutes for it;
* a calculation reproduced from the saved rows proves the arithmetic only (``claim_data_grounding``).

Everything here reads artifacts the run already persisted; the same builder serves the API route, the exported
``evidence_trace.json`` and (for runs that predate the artifact) a read-time computation, so the three can never
disagree about a claim.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from comqutor_alpha.capture_artifacts import DERIVED_INPUTS_FILENAME, recompute_ohlcv_indicators, series_sha256
from comqutor_alpha.graph_engine.activation_scorer_v2 import ASSERTION_WEIGHTS, RELATION_WEIGHTS
from comqutor_alpha.graph_engine.claim_data_grounding import (
    FACT_DEPENDENCY_CONTRACT,
    ClaimGrounding,
    dependency_anchors,
    ground_claim,
    iter_source_cells,
    shared_input_claims,
)
from comqutor_alpha.graph_engine.evidence_consumption import (
    CONSUMPTION_BLOCK_KEY,
    CONSUMPTION_CONTRACT_V2,
    CONSUMPTION_METADATA_KEY,
    CONSUMPTION_RECOMPUTE_EXECUTION_TYPE,
    LEDGER_BINDING_SOURCE_DECLARED,
    PAYLOAD_CONTRACT_KEY,
    EvidenceConsumptionError,
    block_for_match,
    build_block,
    ledger_description,
    matched_candidate,
    resolve_stance_ledger,
    verify_payload,
)
from comqutor_alpha.graph_engine import alpha_relevance_judgment as relevance_record
from comqutor_alpha.graph_engine.alpha_relevance_judgment import RelevanceVerification, verify_relevance_judgments
from comqutor_alpha.graph_engine.evidence_fact_index import select_supporting_alpha_claims
from comqutor_alpha.graph_engine.statement_scope import (
    BASIS_CONTRAST_ALTERNATIVE,
    BASIS_OTHER_CLAUSE,
    REMAINING_ALPHA_TERMS_ONLY_IN_REMOVED_PART,
    STATEMENT_SCOPE_POLICY_VERSION,
)
from comqutor_alpha.structure_engine import alpha_relevance_llm as relevance_task
from comqutor_alpha.source_provenance import compute_verified_support_eligibility, evaluate_source_availability
from comqutor_alpha.storage.file_store import load_json_record_if_exists, run_dir_for, validate_run_id_for_path

EVIDENCE_TRACE_SCHEMA_VERSION = "evidence_trace.v1"
EVIDENCE_TRACE_FILENAME = "evidence_trace.json"

# --- who writes the final decision: the claims whose verification status the report must show -----------------
KEY_CONCLUSION_AGENTS = ("portfolio_manager", "research_manager", "trader")
_RESEARCH_MANAGER_KEY_SECTION = re.compile(r"verdict|decision|recommend", re.IGNORECASE)
KEY_CONCLUSION_RULE = (
    "Claims written by the final-decision agents: every portfolio_manager claim (final decision memo), the "
    "research_manager sections whose heading names the verdict / decision / recommendation, and every trader claim "
    "-- limited to claims that are analytical, carry a source link, or contain the Agent's own 'verified' wording."
)

_VERIFYING_METHODS = frozenset({
    "LLM_CONTENT_SUPPORT_VERIFIED", "AUTOMATED_DATA_FACT_VERIFIED", "AUTOMATED_DERIVED_CALC_VERIFIED", "HUMAN_REVIEWED",
})

# --- the Agent's own wording ---------------------------------------------------------------------------------
_SELF_VERIFIED_RE = re.compile(r"(?<![A-Za-z])verified(?![A-Za-z])|已验证|已核实|经核实", re.IGNORECASE)
AGENT_WORDING_NOTE = (
    "This statement contains the word 'verified' as written by the Agent. That is the Agent's own wording, not a "
    "system verification; the system's result is the source-support status shown beside it."
)

# --- status vocabularies (codes are stable API; labels are display text) ---------------------------------------
SOURCE_SUPPORT_LABELS = {
    "VERIFIED_SUPPORT": "Verified: the saved source content supports this claim",
    "SUPPORT_NOT_ELIGIBLE": "Source supports the claim, but it does not yet count as verified evidence",
    "PARTIAL_SUPPORT": "Partly supported: part of the claim is not backed by the source",
    "BACKGROUND_ONLY": "Source content is background only, not support",
    "SOURCE_OPPOSES": "The source content opposes this claim",
    "TECHNICAL_INCOMPLETE": "Verification not completed (technical failure)",
    "MODEL_JUDGED_INSUFFICIENT": "Model judged the saved material insufficient to decide",
    "NOT_VERIFIED": "Linked to a source but not content-verified",
    "NOT_LINKED": "No source linked; not verified",
    "LINK_INVALID": "Source reference could not be validated",
}
_FALLBACK_REASON_TEXT = {
    "timeout": "the verification request timed out and was not retried",
    "quote_or_data_not_found": "the model's cited quote or data could not be located in the saved source, so its answer was not accepted",
    "malformed_response": "the model's response did not match the required format and was not accepted",
    "provider_error": "the verification request failed at the provider",
    "budget_exhausted": "the request budget was exhausted before this claim was verified",
    "provider_stopped": "not sent: an earlier model request of this run was refused by the provider (HTTP 401/403/429) and the run was stopped",
    "input_too_large": "not sent: the verification request exceeded the local input-size limit and was never sent to the model (no response, no usage)",
}
ALPHA_MATCH_LABELS = {
    "MATCHED": "Matched to an Alpha by the model's selection",
    "MODEL_NONE": "The model judged that no Alpha materially fits",
    "MAPPER_OVERRIDE": "Model selected an Alpha, then a rule gate overrode it to no match",
    "CLASSIFICATION_UNAVAILABLE": "Alpha classification did not complete",
    "NOT_CLASSIFIED": "Not classified",
}
STANCE_LABELS = {
    "RULE_ONLY": "Stance is the deterministic rule result; no model judgment obtained",
    "MODEL_JUDGED": "Stance judged by the model",
    "RELATION_UNRESOLVED": "Relation to the Alpha is not established",
    "NOT_APPLICABLE": "No Alpha matched, so there is no stance",
}
SCORING_LABELS = {
    "IN_OFFICIAL_POOL": "Counted in the Alpha's official score",
    "IN_POOL_ZERO_WEIGHT": "In the official pool with zero weight",
    "NOT_SCORED": "Not counted in any official score",
}
NOT_SCORED_REASONS = {
    "CLASSIFICATION_UNAVAILABLE": "Alpha classification for this claim did not complete (request timed out; not retried).",
    "MODEL_NONE": "The classifier judged that no canonical Alpha materially fits this claim.",
    "MAPPER_GATE_OVERRIDE": "The classifier selected an Alpha, but an Alpha-specific rule gate overrode the selection to no match.",
    "NON_ANALYTICAL_QUALITY": "Classified as context only (not an analytical claim), so it is not used as scoring evidence.",
    "VERIFIED_GATE_SOURCE_LINK_NOT_VALID": "No valid source link, so the verified-evidence gate keeps it out of the official score.",
    "VERIFIED_GATE_NOT_REVIEWED": "Linked to a source but not content-verified by a qualifying method (verification not completed).",
    "VERIFIED_GATE_SUPPORT_STATUS_NOT_RESOLVED": "Content verification did not resolve to supports/opposes (partial support, background only, or pending).",
    "VERIFIED_GATE_SOURCE_OPPOSES_CLAIM": "The source content opposes the claim, so it is not supporting evidence.",
    "VERIFIED_GATE_OTHER": "Did not pass the verified-evidence gate (see the source-support status).",
    "STANCE_MODEL_NOT_SUPPORTING": "A model-judged stance toward this Alpha (opposes, background, mention only, or supports the counter-Alpha) keeps the claim out of the Alpha's positive pool (alpha_stance_policy.v1, R-1). The text-rule relation and the reverse-evidence channel are unchanged.",
    "RELATION_NOT_SUPPORTING": "Verified, but the text rule classified its relation to the Alpha as non-supporting (mention or negation) and no model stance judgment was obtained to resolve it.",
    "ASSERTION_NEGATED": "Verified, but the text rule marked the assertion as negated, which carries zero weight; no model judgment was obtained to resolve it.",
    "ROLE_OR_GROUPING_GATE": "Verified and relation-qualified, but excluded by the Primary/Secondary role or evidence-grouping rule.",
    "MATCH_NOT_COMMITTED": "The Alpha match was not committed (ambiguous or unavailable).",
}
WEIGHT_NOTE = (
    "The weight uses the rule-based lexical match score. A score of 0.0 means the rule found no keyword/factor "
    "overlap; it is NOT a model judgment that the claim is irrelevant (the model was never asked for a relevance strength)."
)
SCOPE_OF_VERIFICATION_NOTE = (
    "Source support, Alpha match, stance and scoring are separate checks; passing one does not imply the others."
)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


@dataclass
class TraceContext:
    run_id: str
    ticker: str | None
    metadata: dict[str, Any]
    records: list[dict[str, Any]]
    records_by_id: dict[str, dict[str, Any]]
    matches: list[dict[str, Any]]
    matches_by_id: dict[str, dict[str, Any]]
    sources: list[dict[str, Any]]
    sources_by_id: dict[str, dict[str, Any]]
    graph: dict[str, Any]
    raw_text_by_output_id: dict[str, str]
    conflict_index: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    derived_inputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    alpha_blocks: dict[str, dict[str, Any]] = field(default_factory=dict)
    pool_index: dict[str, tuple[str, dict[str, Any]]] = field(default_factory=dict)
    group_index: dict[str, dict[str, Any]] = field(default_factory=dict)
    # alpha_evidence_consumption.v2: only set for a run that applied the contract (legacy runs: inactive, nothing shown)
    consumption_active: bool = False
    consumption_states: dict[str, str] = field(default_factory=dict)
    consumption_error: str | None = None
    consumption_ledger: Any = None
    # P4 phase 1: the run's relevance judgments, verified once per read (no results file = every matched pair UNJUDGED)
    relevance: RelevanceVerification | None = None
    _selector_cache: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    _cells_cache: dict[str, list[Any]] = field(default_factory=dict)
    _grounding_cache: dict[str, ClaimGrounding] = field(default_factory=dict)
    _derived_cache: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def dependency_contract_active(self) -> bool:
        return self.metadata.get("fact_dependency_contract") == FACT_DEPENDENCY_CONTRACT


def _safe_load(run_id: str, name: str, output_root: Any) -> Any:
    try:
        return load_json_record_if_exists(run_id, name, output_root=output_root)
    except Exception:  # corrupted/unreadable artifact: treat as absent, never raise from a read-only trace
        return {}


def load_trace_context(run_id: Any, output_root: Any) -> TraceContext | None:
    """``None`` when the run, or the structured claims it is built on, does not exist."""
    try:
        safe_run_id = validate_run_id_for_path(run_id)
        run_dir = run_dir_for(safe_run_id, output_root)
    except ValueError:
        return None
    if not run_dir.exists():
        return None
    structured = _safe_load(safe_run_id, "structured_agent_outputs.json", output_root)
    records = [r for r in (structured.get("records") if isinstance(structured, dict) else None) or [] if isinstance(r, dict)]
    if not records:
        return None
    metadata = _safe_load(safe_run_id, "metadata.json", output_root)
    matches_payload = _safe_load(safe_run_id, "alpha_matches.json", output_root)
    matches = [m for m in (matches_payload.get("matches") if isinstance(matches_payload, dict) else None) or [] if isinstance(m, dict)]
    registry = _safe_load(safe_run_id, "source_registry.json", output_root)
    sources = [s for s in (registry.get("sources") if isinstance(registry, dict) else None) or [] if isinstance(s, dict)]
    graph = _safe_load(safe_run_id, "structure_graph.json", output_root)
    raw = _safe_load(safe_run_id, "raw_agent_outputs.json", output_root)
    raw_text = {
        str(o.get("agent_output_id")): str(o.get("raw_output") or "")
        for o in (raw.get("agent_outputs") if isinstance(raw, dict) else None) or []
        if isinstance(o, dict) and o.get("agent_output_id")
    }
    conflicts = _safe_load(safe_run_id, "conflicts.json", output_root)
    derived = _safe_load(safe_run_id, DERIVED_INPUTS_FILENAME, output_root)
    ctx = TraceContext(
        run_id=safe_run_id,
        ticker=(metadata.get("ticker") if isinstance(metadata, dict) else None) or structured.get("ticker"),
        metadata=metadata if isinstance(metadata, dict) else {},
        records=records,
        records_by_id={str(r.get("claim_id")): r for r in records if r.get("claim_id")},
        matches=matches,
        matches_by_id={str(m.get("claim_id")): m for m in matches if m.get("claim_id")},
        sources=sources,
        sources_by_id={str(s.get("source_id")): s for s in sources if s.get("source_id")},
        graph=graph if isinstance(graph, dict) else {},
        raw_text_by_output_id=raw_text,
    )
    ctx.consumption_active = bool(ctx.metadata.get(CONSUMPTION_METADATA_KEY)) or (
        isinstance(matches_payload, dict) and PAYLOAD_CONTRACT_KEY in matches_payload
    )
    if ctx.consumption_active:
        # read-only: compare every saved block with a fresh recomputation from today's records, sources and ledger
        try:
            ctx.consumption_ledger = resolve_stance_ledger(run_dir, ctx.metadata)
            states = verify_payload(matches_payload, records, sources, ticker=ctx.ticker or "", ledger=ctx.consumption_ledger)
            ctx.consumption_states = {str(s["claim_id"]): str(s["state"]) for s in states}
        except EvidenceConsumptionError as exc:
            ctx.consumption_error = exc.reason_code
        except Exception:
            ctx.consumption_error = "EVIDENCE_CONSUMPTION_VERIFY_FAILED"
    try:
        ctx.relevance = verify_relevance_judgments(run_dir, run_id=safe_run_id, ticker=ctx.ticker or "", matches=matches)
    except Exception:  # read-only trace: an unexpected error is disclosed on every matched claim, never raised
        ctx.relevance = None
    ctx.conflict_index = _conflict_adoption_index(conflicts)
    ctx.derived_inputs = {
        str(e.get("source_id")): e
        for e in (derived.get("inputs") if isinstance(derived, dict) else None) or []
        if isinstance(e, dict) and e.get("source_id")
    }
    activation = ctx.graph.get("activation") if isinstance(ctx.graph, dict) else None
    for alpha in (activation.get("alphas") if isinstance(activation, dict) else None) or []:
        if not isinstance(alpha, dict) or not alpha.get("alpha_id"):
            continue
        alpha_id = str(alpha["alpha_id"])
        ctx.alpha_blocks[alpha_id] = alpha
        for detail in alpha.get("evidence_detail") or []:
            if isinstance(detail, dict) and detail.get("claim_id"):
                ctx.pool_index[str(detail["claim_id"])] = (alpha_id, detail)
        for group in alpha.get("evidence_fact_groups") or []:
            if not isinstance(group, dict):
                continue
            for claim_id in group.get("member_claim_ids") or []:
                ctx.group_index[str(claim_id)] = {**group, "alpha_id": alpha_id}
    return ctx


# ---------------------------------------------------------------------------
# Historical use in a conflict (a READ of what the run saved -- never a re-evaluation)
# ---------------------------------------------------------------------------

HISTORICAL_USE_NOTE = (
    "This is the saved record of what the run did with this claim. It is read from the run's own conflicts.json and is "
    "unchanged by anything shown in the current basis: the admission, level and score of the conflict are not re-evaluated here."
)
LEGACY_RUN_NOTE = (
    "This run was saved before source linking existed, so its records carry no source-link fields and no source basis can "
    "be shown for this claim today. That describes what was saved; it is not a finding that the claim was wrong or "
    "that it had no basis when it was made."
)
LEGACY_REASON_CODE = "RUN_PREDATES_SOURCE_LINKING"


def _conflict_adoption_index(conflicts: Any) -> dict[str, list[dict[str, Any]]]:
    """``{claim_id: [adoption, ...]}`` -- every conflict of the run (admitted, the main one, and evaluated candidates) whose
    saved evidence lists the claim, with that conflict's OWN saved status, level and score and the side it sits on."""
    out: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(conflicts, dict):
        return out
    main = conflicts.get("main_conflict") if isinstance(conflicts.get("main_conflict"), dict) else None
    main_id = main.get("conflict_id") if main else None
    entries: list[Mapping[str, Any]] = [c for c in conflicts.get("conflicts") or [] if isinstance(c, dict)]
    if main and not any(c.get("conflict_id") == main_id for c in entries):
        entries.append(main)
    entries += [c for c in conflicts.get("candidate_conflicts") or [] if isinstance(c, dict)]
    seen: set[tuple[str, str, str]] = set()
    for conflict in entries:
        conflict_id = str(conflict.get("conflict_id") or f"{conflict.get('alpha_a')}__{conflict.get('alpha_b')}")
        admissibility = conflict.get("admissibility") if isinstance(conflict.get("admissibility"), dict) else {}
        status = admissibility.get("status") or conflict.get("status")
        evidence_ui = conflict.get("evidence_ui") if isinstance(conflict.get("evidence_ui"), dict) else {}
        for key, side in (("bull_evidence", "bull"), ("bear_evidence", "bear"), ("counter_evidence", "counter")):
            for item in evidence_ui.get(key) or []:
                if not isinstance(item, dict):
                    continue
                representative = item.get("representative_claim_id")
                for claim_id in {*(item.get("member_claim_ids") or []), representative} - {None, ""}:
                    marker = (str(claim_id), conflict_id, side)
                    if marker in seen:
                        continue
                    seen.add(marker)
                    out.setdefault(str(claim_id), []).append({
                        "conflict_id": conflict_id, "side": side, "target_alpha_id": item.get("target_alpha_id"),
                        "counter_target_alpha_id": item.get("counter_target_alpha_id"),
                        "is_representative": claim_id == representative,
                        "conflict_status": status, "conflict_level": conflict.get("conflict_level"),
                        "conflict_score": conflict.get("conflict_score"), "is_main_conflict": conflict_id == main_id,
                    })
    return out


# ---------------------------------------------------------------------------
# Derived inputs (technical indicators): saved? recomputable from the saved inputs?
# ---------------------------------------------------------------------------


def _derived_inputs_view(ctx: TraceContext, source: Mapping[str, Any]) -> dict[str, Any] | None:
    """For a source that carries a derived value (``calculation_method``): did the run save the COMPLETE input window, and do
    those saved inputs alone reproduce the saved outputs? ``None`` for a source with no derived value."""
    if not source.get("calculation_method"):
        return None
    source_id = str(source.get("source_id"))
    if source_id in ctx._derived_cache:
        return ctx._derived_cache[source_id]
    params = source.get("calculation_params") if isinstance(source.get("calculation_params"), dict) else {}
    entry = ctx.derived_inputs.get(source_id)
    if not entry:
        view = {
            "status": "NOT_SAVED",
            "method": source.get("calculation_method"), "version": source.get("calculation_version"),
            "window_parameters": {k: params.get(k) for k in ("symbol", "as_of_date", "window_start", "window_end", "row_count") if k in params},
            "note": ("This run did not save the input series behind its derived values (it was written before that was "
                     "captured, or the capture did not run); only the method, version and window parameters survive. "
                     "Nothing is backfilled from a later fetch."),
        }
    else:
        series = entry.get("series") if isinstance(entry.get("series"), dict) else {}
        pointer = params.get("input_series_sha256")
        verdict = recompute_ohlcv_indicators(entry)
        view = {
            "status": "SAVED", "method": (entry.get("method") or {}).get("library"), "version": (entry.get("method") or {}).get("version"),
            "row_count": series.get("row_count"), "first_date": series.get("first_date"), "last_date": series.get("last_date"),
            "columns": series.get("columns"), "series_sha256": series.get("sha256"),
            "series_hash_ok": series_sha256(series) == series.get("sha256") if series else False,
            "registry_pointer_matches": (pointer == series.get("sha256")) if pointer else None,
            "recomputation": {"status": verdict.get("status"), "indicators_checked": len(verdict.get("indicators") or {}),
                              "mismatched": verdict.get("mismatched") or [], "version_match": verdict.get("version_match")},
            "note": "Recomputed from the saved inputs alone (no provider call, no cache). Reproducing a value proves the arithmetic of the saved inputs only.",
        }
    ctx._derived_cache[source_id] = view
    return view


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _llm_detail(record: Mapping[str, Any]) -> dict[str, Any]:
    detail = record.get("content_support_llm_detail")
    if isinstance(detail, str):
        try:
            import json

            detail = json.loads(detail)
        except ValueError:
            detail = {}
    return detail if isinstance(detail, dict) else {}


def _linked_ids(record: Mapping[str, Any]) -> list[str]:
    ids: list[str] = []
    if record.get("source_link_status") == "VALID":
        for candidate in [record.get("linked_source_id"), *(record.get("linked_source_ids") or [])]:
            if isinstance(candidate, str) and candidate and candidate not in ids:
                ids.append(candidate)
    return ids


def agent_wording(text: str) -> dict[str, Any]:
    terms = sorted({m.group(0).lower() if m.group(0).isascii() else m.group(0) for m in _SELF_VERIFIED_RE.finditer(text or "")})
    return {"self_labeled_verified": bool(terms), "matched_terms": terms, "note": AGENT_WORDING_NOTE if terms else None}


def _report_location(ctx: TraceContext, record: Mapping[str, Any]) -> dict[str, Any]:
    output_id = str(record.get("source_agent_output_id") or "")
    text = ctx.raw_text_by_output_id.get(output_id)
    claim = str(record.get("claim") or "")
    needle = claim.split("[")[0].strip()[:40] or claim[:25]
    offset = text.find(needle) if text and needle else -1
    paragraph = None
    if text is not None and offset >= 0:
        start = text.rfind("\n", 0, offset) + 1
        end = text.find("\n", offset)
        paragraph = text[start: end if end >= 0 else len(text)].strip()[:700]
    return {
        "agent_output_id": output_id or None,
        "section": record.get("source_section"),
        "claim_index": record.get("claim_index"),
        "char_offset": offset if offset >= 0 else None,
        "paragraph": paragraph,
    }


def _grounding(ctx: TraceContext, record: Mapping[str, Any]) -> ClaimGrounding:
    claim_id = str(record.get("claim_id") or "")
    cached = ctx._grounding_cache.get(claim_id)
    if cached is None:
        cached = ground_claim(record, ctx.sources_by_id, cells_cache=ctx._cells_cache)
        ctx._grounding_cache[claim_id] = cached
    return cached


def _time_basis(source: Mapping[str, Any] | None) -> dict[str, Any]:
    if not source:
        return {"basis": "NOT_APPLICABLE", "value": None}
    if source.get("published_at"):
        return {"basis": "PUBLISHED_AT", "value": source["published_at"]}
    availability = evaluate_source_availability(source)
    if availability.get("available_before_cutoff"):
        return {"basis": availability.get("basis") or "REGISTRY_WRITE_TIME_UPPER_BOUND", "value": availability.get("available_by"),
                "note": "capture time is an upper bound (the registry write time), not the per-call fetch time"}
    return {"basis": "UNKNOWN", "value": None}


# ---------------------------------------------------------------------------
# Sources: the actual material, and where in it the claim's numbers sit
# ---------------------------------------------------------------------------


def _source_view(ctx: TraceContext, source_id: str, role: str, grounding: ClaimGrounding) -> dict[str, Any]:
    source = ctx.sources_by_id.get(source_id)
    if source is None:
        return {"source_id": source_id, "role": role, "resolved": False}
    excerpt = str(source.get("excerpt") or "")
    used: dict[tuple[str, str], dict[str, str]] = {}
    for point in grounding.data_points:
        if point.source_id == source_id:
            used.setdefault((point.label, point.kind), {})[str(point.period or "")] = point.token
    rows: list[dict[str, Any]] = []
    cells = ctx._cells_cache.get(source_id)
    if cells is None:
        cells = ctx._cells_cache[source_id] = iter_source_cells(source)
    cells_by_label: dict[tuple[str, str], list[Any]] = {}
    for cell in cells:
        cells_by_label.setdefault((cell.label, cell.kind), []).append(cell)
    for (label, kind), marks in used.items():
        row_cells = cells_by_label.get((label, kind)) or []
        if kind == "statement_row":
            row_cells = sorted(row_cells, key=lambda c: c.period or "", reverse=True)
        rows.append({
            "label": label, "kind": kind, "unit": row_cells[0].unit if row_cells else None,
            "cells": [
                {"period": c.period, "value": c.value, "used": str(c.period or "") in marks,
                 "token": marks.get(str(c.period or ""))}
                for c in row_cells
            ],
        })
    return {
        "source_id": source_id, "role": role, "resolved": True,
        "source_type": source.get("source_type"), "title": source.get("title"), "name": source.get("name"),
        "provider": source.get("provider"), "instrument": source.get("instrument"), "url": source.get("url"),
        "observation_date": source.get("observation_date"), "published_at": source.get("published_at"),
        "retrieved_at": source.get("retrieved_at"), "unit": source.get("unit"),
        "fragment_id": source.get("fragment_id"), "content_hash": source.get("content_hash"),
        "time_basis": _time_basis(source),
        "excerpt": {"text": excerpt[:700], "length": len(excerpt), "truncated": len(excerpt) > 700},
        "has_saved_content": bool(excerpt),
        "material_rows": rows[:8],
        "derived_inputs": _derived_inputs_view(ctx, source),
    }


# ---------------------------------------------------------------------------
# The four statuses
# ---------------------------------------------------------------------------


def _source_support_status(record: Mapping[str, Any], eligibility: Mapping[str, Any], detail: Mapping[str, Any]) -> dict[str, Any]:
    link = record.get("source_link_status")
    support = record.get("content_support_status")
    method = record.get("content_support_method")
    fallback = record.get("content_support_llm_fallback_reason")
    remainder = (detail.get("unsupported_remainder") or "").strip()
    if link is None:  # the record carries no source-link field at all: the run predates source linking
        code, reason = "NOT_LINKED", LEGACY_RUN_NOTE
    elif link == "NOT_PROVIDED":
        code, reason = "NOT_LINKED", ("No source reference was linked to this claim. Commentary and recommendations "
                                       "need no external source, but this statement is not verified.")
    elif link != "VALID":
        code, reason = "LINK_INVALID", f"The source reference did not validate ({link})."
    elif support == "SUPPORTS" and eligibility.get("eligible"):
        code, reason = "VERIFIED_SUPPORT", detail.get("rationale") or "The saved source content supports the claim."
    elif support == "SUPPORTS":
        code, reason = "SUPPORT_NOT_ELIGIBLE", f"The verdict is SUPPORTS but the eligibility check returned {eligibility.get('reason_code')}."
    elif support == "OPPOSES":
        code, reason = "SOURCE_OPPOSES", detail.get("rationale") or "The saved source content opposes the claim."
    elif support == "CONDITIONAL":
        code, reason = "PARTIAL_SUPPORT", (f"Not backed by the source: {remainder}" if remainder else (detail.get("rationale") or "Only part of the claim is backed by the source."))
    elif support in ("BACKGROUND", "CITATION_ONLY"):
        code, reason = "BACKGROUND_ONLY", detail.get("rationale") or "The source is background or a citation, not support for the claim."
    elif support == "PENDING_REVIEW" and fallback:
        code, reason = "TECHNICAL_INCOMPLETE", f"Verification did not complete: {_FALLBACK_REASON_TEXT.get(str(fallback), str(fallback))}."
    elif support == "PENDING_REVIEW" and method == "LLM_CONTENT_SUPPORT_VERIFIED":
        code, reason = "MODEL_JUDGED_INSUFFICIENT", detail.get("rationale") or "The model judged the saved material insufficient to decide."
    else:
        code, reason = "NOT_VERIFIED", "Linked to a source (by Agent citation or text overlap) but no qualifying content verification was completed."
    out = {"status_code": code, "label": SOURCE_SUPPORT_LABELS[code], "reason": reason}
    if link is None:
        out["reason_code"] = LEGACY_REASON_CODE
    return out


def _alpha_match_status(match: Mapping[str, Any] | None) -> dict[str, Any]:
    if not match:
        return {"status_code": "NOT_CLASSIFIED", "label": ALPHA_MATCH_LABELS["NOT_CLASSIFIED"], "reason": "No Alpha-match record exists for this claim.",
                "match_status": None, "matched_alpha": None}
    status = match.get("match_status")
    overrides = [k for k in ("alpha_positive_requirement_override", "alpha_specific_invalidation_override") if match.get(k)]
    if status == "matched":
        code, reason = "MATCHED", f"The classifier selected {match.get('matched_alpha')} ({match.get('matched_alpha_name') or ''}) from the full taxonomy.".replace(" ()", "")
    elif status == "unavailable":
        code, reason = "CLASSIFICATION_UNAVAILABLE", "The classification request timed out or failed and was not retried; there is no usable result."
    elif overrides:
        code, reason = "MAPPER_OVERRIDE", f"The model selected {match.get('llm_selected_alpha_id')}; the {overrides[0]} rule gate then set it to no match."
    else:
        code, reason = "MODEL_NONE", "The classifier returned a valid answer that no canonical Alpha materially fits."
    return {
        "status_code": code, "label": ALPHA_MATCH_LABELS[code], "reason": reason,
        "match_status": status, "matched_alpha": match.get("matched_alpha"),
        "llm_selected_alpha_id": match.get("llm_selected_alpha_id"),
        "alpha_match_method": match.get("alpha_match_method"),
        "mapper_override": overrides[0] if overrides else None,
    }


def _matched_candidate(match: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if not match or not match.get("matched_alpha"):
        return None
    for pool in ("candidate_scores", "eligible_candidates", "top_candidates"):
        for candidate in match.get(pool) or []:
            if isinstance(candidate, Mapping) and candidate.get("alpha_id") == match.get("matched_alpha"):
                return candidate
    return None


def _stance_status(match: Mapping[str, Any] | None) -> dict[str, Any]:
    candidate = _matched_candidate(match)
    if candidate is None:
        return {"status_code": "NOT_APPLICABLE", "label": STANCE_LABELS["NOT_APPLICABLE"],
                "reason": "The claim has no matched Alpha, so no stance toward an Alpha applies.",
                "evidence_stance": None, "method": None, "relation": None, "assertion_status": None}
    method = candidate.get("stance_method")
    relation = candidate.get("relation")
    assertion = match.get("assertion_status") if match else None
    polarity = match.get("semantic_polarity") if match else None
    relation_basis = "text rule (claim_semantics)"
    # alpha_evidence_consumption.v2 (alpha_statement_scope): the gates and the weights read the block's per-pair negation scope,
    # so this explanation reads the same fields (the block's own validity is shown by the consumption section).
    block = block_for_match(match) if match else None
    scope = block.get("statement_scope") if isinstance(block, Mapping) else None
    if isinstance(scope, Mapping) and isinstance(scope.get("effective"), Mapping):
        effective = scope["effective"]
        relation, assertion, polarity = effective.get("relation"), effective.get("assertion_status"), effective.get("semantic_polarity")
        if scope.get("changed"):
            relation_basis = f"text rule re-read for this Alpha ({STATEMENT_SCOPE_POLICY_VERSION}: the negation does not govern its statement)"
    stance = candidate.get("evidence_stance")
    if method == "llm":
        code, reason = "MODEL_JUDGED", f"The model judged the stance toward {candidate.get('alpha_id')} as {stance}."
    else:
        code = "RULE_ONLY"
        reason = (f"The stance ({stance}) is the deterministic shadow classifier's result. A model direction judgment was "
                  "never obtained for this claim-Alpha pair (it is not a model finding of 'no stance').")
    if relation in ("mention", "unknown") or str(assertion).lower() == "negated":
        code = "RELATION_UNRESOLVED"
        why = "the text rule classified the relation as 'mention'" if relation == "mention" else (
            "the text rule marked the assertion as negated" if str(assertion).lower() == "negated" else "the relation is unknown")
        if method == "llm":
            reason = (f"The model judged the stance as {stance}, but the relation used for scoring is still the text rule's result "
                      f"({why}), which the model's stance does not update; the claim therefore does not count as supporting evidence.")
        else:
            reason = (f"Relation to {candidate.get('alpha_id')} is not established: {why} (a word-pattern rule, e.g. the word 'not'). "
                      "No model stance judgment was obtained to resolve it, so this is unresolved rather than 'does not support'.")
    return {
        "status_code": code, "label": STANCE_LABELS[code], "reason": reason, "evidence_stance": stance,
        "method": "llm" if method == "llm" else ("deterministic_fallback" if method else "deterministic"),
        "version": candidate.get("evidence_stance_version"), "stance_fallback_reason": candidate.get("stance_fallback_reason"),
        "relation": relation, "assertion_status": assertion, "semantic_polarity": polarity,
        "relation_basis": relation_basis, "target_alpha_id": candidate.get("alpha_id"),
    }


def _selector_excluded(ctx: TraceContext, alpha_id: str) -> dict[str, dict[str, Any]]:
    if alpha_id not in ctx._selector_cache:
        try:
            _eligible, excluded, _warnings = select_supporting_alpha_claims(ctx.matches, alpha_id)
        except EvidenceConsumptionError as exc:  # an invalid block: shown as such, never silently treated as "no exclusion"
            ctx.consumption_error = ctx.consumption_error or exc.reason_code
            excluded = []
        ctx._selector_cache[alpha_id] = {str(e.get("claim_id")): e for e in excluded if e.get("claim_id")}
    return ctx._selector_cache[alpha_id]


def _execution_basis(ctx: TraceContext) -> dict[str, Any]:
    """Which run executed this evaluation and on what basis -- the executing run, the saved run it was derived from, and WHOSE model
    ledger corroborated the stances -- kept apart, so a recomputation of saved inputs is never presented as a Fresh Run."""
    metadata = ctx.metadata if isinstance(ctx.metadata, Mapping) else {}
    execution_type = metadata.get("execution_type")
    based_on = metadata.get("based_on_run_id")
    if execution_type == CONSUMPTION_RECOMPUTE_EXECUTION_TYPE:
        rules = "under the evidence contract" if ctx.consumption_active else "under the legacy rules (no evidence contract declared)"
        label = (f"Recomputation of a saved run's inputs {rules} -- not a Fresh Run. This execution made no model, "
                 "search or data-fetch call; every stance is the source run's saved result (nothing was re-judged).")
    elif based_on:
        label = f"Derived execution ({execution_type or 'unknown type'}) based on the saved run {based_on} -- not a Fresh Run."
    else:
        label = "Original research run."
    return {
        "execution_run_id": ctx.run_id,
        "execution_type": execution_type,
        "based_on_run_id": based_on,
        "root_research_run_id": metadata.get("root_research_run_id"),
        "recomputation_of_saved_inputs": bool(based_on),
        "label": label,
        "stance_ledger": ledger_description(ctx.consumption_ledger),
    }


def _attribution_view(attribution: Any) -> Any:
    """The name decision in words -- the same sentence for a matched claim and for a claim matched to no Alpha."""
    if not isinstance(attribution, Mapping):
        return attribution
    return {
        **attribution,
        "explanation": (
            "The target company's name is present in the claim text; this does not establish that the claim is ABOUT the target."
            if attribution.get("ticker_specific") else "The target company's name is not present in the claim text."
        ),
    }


def _consumption_view(ctx: TraceContext, claim_id: str, match: Mapping[str, Any] | None) -> dict[str, Any]:
    """The alpha_evidence_consumption.v2 block of one claim as the trace shows it: what the contract decided, from which
    raw inputs, under which policy versions -- and whether the saved block still equals a fresh recomputation (``CURRENT``),
    has gone ``STALE`` (the source state or ledger moved since it was written), or is ``MISSING`` / ``INVALID``."""
    state = ctx.consumption_states.get(claim_id)
    out: dict[str, Any] = {
        "contract": CONSUMPTION_CONTRACT_V2,
        "state": state or ("NOT_APPLICABLE" if match is None else "UNKNOWN"),
        "verification_error": ctx.consumption_error,
        "execution_basis": _execution_basis(ctx),
    }
    if match is None:
        return out
    if match.get("match_status") != "matched":
        top = match.get(CONSUMPTION_BLOCK_KEY)
        if isinstance(top, Mapping):
            out["scope"] = "attribution_only (the claim is matched to no Alpha)"
            out["attribution"] = _attribution_view(top.get("attribution"))
        return out
    block = block_for_match(match)
    if block is None:
        return out
    stance, admission, attribution = block.get("stance") or {}, block.get("positive_admission") or {}, block.get("attribution") or {}
    alpha_id = block.get("alpha_id")
    if stance.get("state") == "MODEL_JUDGED":
        ledger_ref = (block.get("binding") or {}).get("ledger") or {}
        if ledger_ref.get("binding") == LEDGER_BINDING_SOURCE_DECLARED:
            whose = f"the validated ledger output of the saved source run {ledger_ref.get('owner_run_id')}, bound by its declared hash"
        else:
            whose = "the run's own validated ledger output"
        stance_text = f"The model judged the stance toward {alpha_id} as {stance.get('label')} (confirmed by {whose})."
    else:
        stance_text = (f"The stance toward {alpha_id} is unjudged ({stance.get('unjudged_category')}: {stance.get('unjudged_reason')}); "
                       "this adds no exclusion, and the other gates still apply.")
    out.update({
        "alpha_id": alpha_id,
        "policies": block.get("policies"),
        "text_rule": block.get("text_rule"),
        "stance": {**stance, "explanation": stance_text},
        "positive_admission": {
            **admission,
            "explanation": (
                f"Excluded from {alpha_id}'s positive pool by alpha_stance_policy.v1 (R-1). Only this Alpha's pool is affected; the "
                "original selection, the text-rule relation, the assertion and the reverse-evidence channel are unchanged."
                if not admission.get("admitted") else
                f"No exclusion from {alpha_id}'s positive pool by the stance policy (every other gate still applies)."
            ),
        },
        "attribution": _attribution_view(attribution),
        "relevance": block.get("relevance"),
        "source_support": block.get("source_support"),
        "binding": block.get("binding"),
        "statement_scope": _statement_scope_view(block.get("statement_scope"), alpha_id),
    })
    if state == "STALE":
        out["recomputed_now"] = build_block(
            match, matched_candidate(match) or {}, str(alpha_id), str(block.get("ticker")),
            record=ctx.records_by_id.get(claim_id), sources=ctx.sources, taxonomy=None, ledger=ctx.consumption_ledger,
        )
    return out


_SCOPE_BASIS_LABELS = {
    "CITATION_MARKER": "a citation marker",
    "CONTRAST_ALTERNATIVE": "the rejected alternative of a contrast",
    "NEGATED_PROTECTION_AFFIRMS_RISK": "a negated protection, which affirms the risk",
    "NEGATION_IN_ANOTHER_CLAUSE": "another clause than the one carrying this Alpha's matched terms",
}


def _statement_scope_view(scope: Any, alpha_id: Any) -> dict[str, Any] | None:
    """The statement scope as the trace shows it: why the text rule's whole-claim negation does or does not negate this Alpha's
    statement, and which text-rule fields the positive gates and the weights read (the stored ones stay unchanged)."""
    if not isinstance(scope, Mapping):
        return None
    effective = scope.get("effective") or {}
    def _bases(items: Any) -> str:
        return " and ".join(sorted({_SCOPE_BASIS_LABELS.get(str(i.get("basis")), str(i.get("basis"))) for i in items or [] if isinstance(i, Mapping)}))
    if not scope.get("applies"):
        explanation = "The text rule did not mark this claim negated; its stored fields are used as they are."
    elif scope.get("governing_negation") and scope.get("not_applied") and scope.get("remaining_negators") != [REMAINING_ALPHA_TERMS_ONLY_IN_REMOVED_PART]:
        explanation = (f"The text rule marked the claim negated. The negation may sit only in {_bases(scope.get('not_applied'))}, but "
                       f"the words alone cannot tell whether {alpha_id}'s statement is the kept or the rejected part, and this pair has "
                       f"no ledger-corroborated model judgment that the claim supports {alpha_id} (the anchor this rule needs); the "
                       "claim is read as negated.")
    elif scope.get("governing_negation"):
        remaining = scope.get("remaining_negators") or []
        why = (f"its own matched terms are only in {_bases(scope.get('removed'))}" if remaining == [REMAINING_ALPHA_TERMS_ONLY_IN_REMOVED_PART]
               else ", ".join(str(n) for n in remaining) or "a negator")
        explanation = (f"The text rule marked the claim negated, and the negation still governs {alpha_id}'s statement ({why}); "
                       "the claim is read as negated.")
    else:
        anchored = any(str(i.get("basis")) in (BASIS_CONTRAST_ALTERNATIVE, BASIS_OTHER_CLAUSE) for i in scope.get("removed") or [] if isinstance(i, Mapping))
        explanation = (f"The text rule marked the whole claim negated, but the negation sits only in {_bases(scope.get('removed'))}; it "
                       f"does not negate {alpha_id}'s statement"
                       + (f" (which side carries the statement is anchored by the ledger-corroborated model judgment that the claim "
                          f"supports {alpha_id})" if anchored else "")
                       + f". Read without that part: relation {effective.get('relation')}, assertion {effective.get('assertion_status')}. "
                       "The positive gates and the weights use these; the stored text-rule fields are unchanged, and the stance, source "
                       "and every other gate still apply.")
    return {**dict(scope), "explanation": explanation}


_RELEVANCE_LABELS = {
    relevance_task.STATE_UNJUDGED: "No relevance judgment exists for this claim and its matched Alpha.",
    relevance_task.STATE_JUDGED: "Relevance to {alpha} judged: {tier}.",
    relevance_task.STATE_UNRESOLVED: "The relevance judgment explicitly could not determine a tier for {alpha}.",
    relevance_task.STATE_FAILED: "The relevance judgment for {alpha} failed; no tier is shown.",
}
RELEVANCE_TEST_DATA_NOTE = "SIMULATED TEST DATA -- produced by the P4 phase-1 simulated gateway, not a model judgment."
RELEVANCE_CONSUMPTION_NOTE = ("Experimental label only (P4 phase 1): not read by Alpha selection, stance, admission or scoring, and "
                              "no weight is derived from it (model_weight stays null).")


def _relevance_view(ctx: TraceContext, claim_id: str, match: Mapping[str, Any]) -> dict[str, Any]:
    """The experimental relevance judgment of one claim and its MATCHED Alpha, as verified on this read: state, tier (JUDGED only),
    the definition elements it is anchored to, the short basis, the source (which run executed the trace, which saved run it derives
    from, which run owns the judgment and its ledger) and the failure / unjudged reason. Nothing is judged here."""
    alpha_id = str(match.get("matched_alpha") or "")
    verification = ctx.relevance
    if verification is None:
        view: Mapping[str, Any] = {"state": relevance_task.STATE_FAILED, "tier": None, "reason": "relevance_verification_error",
                                   "reason_detail": None, "anchor_element_ids": [], "basis": None, "unresolved_reason": None, "call_id": None,
                                   "anchor_evidence": [], "versions": None}
    else:
        view = verification.pairs.get((claim_id, alpha_id)) or {
            "state": relevance_task.STATE_UNJUDGED, "tier": None, "reason": relevance_record.UNJUDGED_PAIR_NOT_REQUESTED, "reason_detail": None,
            "anchor_element_ids": [], "basis": None, "unresolved_reason": None, "call_id": None, "anchor_evidence": [], "versions": None}
    definitions = (verification.definitions if verification is not None else None) or {}
    definition = definitions.get(alpha_id)
    anchors = [
        {"element_id": element_id,
         "label": definition.labels.get(element_id) if definition else None,
         "ownership": definition.ownership.get(element_id) if definition else None,
         "occurrences": [{"list": name, "phrase": phrase} for name, phrase in (definition.occurrences.get(element_id) or ())] if definition else [],
         # output v2: the claim's own words the judgment quoted for this element (empty for a judgment recorded under output v1)
         "evidence_quotes": [str(e.get("quote")) for e in view.get("anchor_evidence") or []
                             if isinstance(e, Mapping) and e.get("element_id") == element_id and e.get("quote")],
         # output v3: how each quoted statement is made (assertion, forecast, probability ...), aligned with evidence_quotes
         "evidence_modes": [str(e.get("mode") or "") for e in view.get("anchor_evidence") or []
                            if isinstance(e, Mapping) and e.get("element_id") == element_id and e.get("quote")]}
        for element_id in view.get("anchor_element_ids") or []
    ]
    versions = view.get("versions") or {}  # the versions the record itself was made under -- never the current ones by assumption
    source = view.get("source") or {}
    experiment = (verification.experiment if verification is not None else None) or {}
    test_data = bool(source.get("test_data") or experiment.get("test_data"))
    state = view["state"]
    label = _RELEVANCE_LABELS[state].format(alpha=alpha_id, tier=view.get("tier"))
    return {
        "contract": relevance_record.RESULTS_SCHEMA_VERSION,
        "alpha_id": alpha_id,
        "state": state,
        "tier": view.get("tier") if state == relevance_task.STATE_JUDGED else None,
        "reason": view.get("reason"),
        "reason_detail": view.get("reason_detail"),
        "label": f"{RELEVANCE_TEST_DATA_NOTE} {label}" if test_data and state != relevance_task.STATE_UNJUDGED else label,
        "anchors": anchors,
        "basis": view.get("basis"),
        "unresolved_reason": view.get("unresolved_reason"),
        # output v3: every statement the judgment reported (hit or not) and where the tier came from -- recorded, not re-judged here
        "statements": [dict(s) for s in view.get("statements") or [] if isinstance(s, Mapping)],
        "tier_source": view.get("tier_source"),
        "test_data": test_data and state != relevance_task.STATE_UNJUDGED,
        "source": {
            "execution_run_id": ctx.run_id,
            "based_on_run_id": ctx.metadata.get("based_on_run_id"),
            "owner_run_id": verification.owner_run_id if verification is not None else None,
            "call_id": view.get("call_id"),
            "task": relevance_task.LLM_TASK_NAME,
            "prompt_version": versions.get("prompt_version"),
            "criterion_version": versions.get("criterion_version"),
            "output_schema_version": versions.get("output_schema_version"),
            "provider": source.get("provider"),
            "model": source.get("model"),
            "execution_mode": source.get("execution_mode"),
            "ledger": verification.ledger.description() if verification is not None and verification.ledger is not None else None,
        },
        "model_weight": None,
        "consumption_note": RELEVANCE_CONSUMPTION_NOTE,
    }


def _alpha_result(ctx: TraceContext, alpha_id: str, block: Mapping[str, Any]) -> dict[str, Any]:
    """The Alpha's official result with the counts kept apart: claims, independent facts (evidence fact groups),
    distinct agents and distinct linked sources are four different numbers."""
    claim_ids = [str(c) for c in block.get("claim_ids") or []]
    source_ids = {sid for cid in claim_ids if cid in ctx.records_by_id for sid in _linked_ids(ctx.records_by_id[cid])}
    claims = block.get("raw_supporting_claim_count")
    facts = block.get("unique_evidence_fact_count")
    return {
        "score": block.get("activation_score"), "level": block.get("qualified_level") or block.get("status"),
        "claims_in_pool": claims if claims is not None else len(claim_ids),
        "independent_facts": facts if facts is not None else block.get("unique_evidence_count"),
        "distinct_agents": block.get("distinct_supporting_agents"), "distinct_sources": len(source_ids),
    }


def _scoring_status(
    ctx: TraceContext, record: Mapping[str, Any], match: Mapping[str, Any] | None, eligibility: Mapping[str, Any]
) -> dict[str, Any]:
    claim_id = str(record.get("claim_id") or "")
    pooled = ctx.pool_index.get(claim_id)
    if pooled is not None:
        alpha_id, detail = pooled
        block = ctx.alpha_blocks.get(alpha_id, {})
        score = float(detail.get("match_score") or 0.0)
        weight = round(score * RELATION_WEIGHTS.get(str(detail.get("relation")), 0.0)
                       * ASSERTION_WEIGHTS.get(str(detail.get("assertion_status")).lower(), 0.0), 6)
        group = ctx.group_index.get(claim_id) or {}
        members = [str(m) for m in group.get("member_claim_ids") or []]
        code = "IN_OFFICIAL_POOL" if weight > 0 else "IN_POOL_ZERO_WEIGHT"
        reason = (f"Counted as evidence for {alpha_id} (official score {block.get('activation_score')}, level "
                  f"{block.get('qualified_level') or block.get('status')}). " + WEIGHT_NOTE)
        return {
            "status_code": code, "label": SCORING_LABELS[code], "reason": reason, "in_official_pool": True,
            "alpha_id": alpha_id, "weight_contribution": weight, "match_score_lexical": score,
            "relation": detail.get("relation"), "assertion_status": detail.get("assertion_status"),
            "fact_group": {
                "id": group.get("evidence_fact_group_id"), "member_claim_ids": members,
                "supporting_agents": group.get("supporting_agents") or [],
                "role": next((r for r in group.get("members_source_role_detail") or [] if r.get("claim_id") == claim_id), None),
            },
            "alpha_result": _alpha_result(ctx, alpha_id, block),
            "not_scored_code": None,
        }
    # not in any official pool: the first gate that stops it, using the same production functions as scoring
    status = match.get("match_status") if match else None
    alpha_id = match.get("matched_alpha") if match else None
    if match is None or status == "unavailable":
        gate = "CLASSIFICATION_UNAVAILABLE"
    elif status == "no_match":
        gate = "MAPPER_GATE_OVERRIDE" if (match.get("alpha_positive_requirement_override") or match.get("alpha_specific_invalidation_override")) else "MODEL_NONE"
    elif status != "matched":
        gate = "MATCH_NOT_COMMITTED"
    elif not eligibility.get("eligible"):
        gate = f"VERIFIED_GATE_{eligibility.get('reason_code')}"
        gate = gate if gate in NOT_SCORED_REASONS else "VERIFIED_GATE_OTHER"
    else:
        excluded = _selector_excluded(ctx, str(alpha_id)).get(claim_id)
        gate = excluded["reason"] if excluded and excluded.get("reason") in NOT_SCORED_REASONS else "ROLE_OR_GROUPING_GATE"
    return {
        "status_code": "NOT_SCORED", "label": SCORING_LABELS["NOT_SCORED"], "reason": NOT_SCORED_REASONS.get(gate, gate),
        "in_official_pool": False, "alpha_id": alpha_id, "weight_contribution": None,
        "match_score_lexical": match.get("score") if match and alpha_id else None, "not_scored_code": gate,
    }


# ---------------------------------------------------------------------------
# One claim
# ---------------------------------------------------------------------------


def key_conclusion_group(record: Mapping[str, Any]) -> str | None:
    """``"<agent> / <section>"`` when the claim belongs to the final-decision chain and is worth a status row."""
    agent = str(record.get("agent") or "")
    if agent not in KEY_CONCLUSION_AGENTS:
        return None
    section = str(record.get("source_section") or "")
    if agent == "research_manager" and not _RESEARCH_MANAGER_KEY_SECTION.search(section):
        return None
    wording = agent_wording(str(record.get("claim") or ""))["self_labeled_verified"]
    if record.get("claim_quality") != "analytical" and record.get("source_link_status") != "VALID" and not wording:
        return None
    return f"{agent} / {section}" if section else agent


def build_claim_trace(ctx: TraceContext, claim_id: str) -> dict[str, Any] | None:
    record = ctx.records_by_id.get(claim_id)
    if record is None:
        return None
    match = ctx.matches_by_id.get(claim_id)
    eligibility = compute_verified_support_eligibility(record, ctx.sources)
    detail = _llm_detail(record)
    review = record.get("content_support_review") if isinstance(record.get("content_support_review"), dict) else {}
    grounding = _grounding(ctx, record)

    linked = _linked_ids(record)
    # only a verification that actually ran (a model/automated/human result) has a "source the verification used";
    # a claim whose verification fell back (timeout, quote not found, malformed) or was never run has none
    verified_basis = (
        review.get("linked_source_id")
        if record.get("content_support_method") in _VERIFYING_METHODS and review.get("linked_source_id") in linked
        else None
    )
    sources = [
        _source_view(ctx, sid, "verified_basis" if sid == verified_basis else ("primary_link" if sid == linked[0] and not verified_basis else "cited"), grounding)
        for sid in linked
    ]
    bound = ctx.sources_by_id.get(str(review.get("linked_source_id") or record.get("linked_source_id") or ""))
    source_support = _source_support_status(record, eligibility, detail)
    source_support.update({
        "link": {"status": record.get("source_link_status"), "method": record.get("source_link_method")},
        "content_support": {
            "status": record.get("content_support_status"), "method": record.get("content_support_method"),
            "task_version": detail.get("schema_version"), "llm_status": detail.get("llm_status"),
            "support_basis": detail.get("support_basis"), "core_proposition": detail.get("core_proposition"),
            "used_source_id": detail.get("used_source_id"), "used_location": detail.get("used_location"),
            "supporting_quote_or_data": detail.get("supporting_quote_or_data"), "rationale": detail.get("rationale"),
            "unsupported_remainder": detail.get("unsupported_remainder") or None,
            "unsupported_materiality": detail.get("unsupported_remainder_materiality"),
            "fallback_reason": record.get("content_support_llm_fallback_reason"),
        },
        "eligibility": {
            "eligible": bool(eligibility.get("eligible")), "reason_code": eligibility.get("reason_code"),
            "time_basis": _time_basis(bound) if record.get("source_link_status") == "VALID" else {"basis": "NOT_APPLICABLE", "value": None},
        },
    })

    alpha_match = _alpha_match_status(match)
    stance = _stance_status(match)
    scoring = _scoring_status(ctx, record, match, eligibility)

    group = ctx.group_index.get(claim_id) or {}
    members = [str(m) for m in group.get("member_claim_ids") or []]
    depends_on = None
    depended_by: list[str] = []
    shared: list[str] = []
    if members and len(members) > 1:
        member_groundings = {m: _grounding(ctx, ctx.records_by_id[m]) for m in members if m in ctx.records_by_id}
        anchors = dependency_anchors(
            {m: g.input_keys for m, g in member_groundings.items()}, {m: g.stated_keys for m, g in member_groundings.items()}
        )
        depends_on = anchors.get(claim_id)
        depended_by = sorted(m for m, anchor in anchors.items() if anchor == claim_id)
        shared = shared_input_claims({m: g.input_keys for m, g in member_groundings.items()}, claim_id)
    dependency = {
        "contract": FACT_DEPENDENCY_CONTRACT if ctx.dependency_contract_active else None,
        "same_evidence_fact_members": members,
        "depends_on": depends_on, "depended_by": depended_by, "shares_inputs_with": shared,
        "note": ("Claims in the same evidence fact keep their own citations and wording; they count as ONE independent "
                 "fact because every observation a dependent claim uses is stated by its anchor claim. Sharing a source "
                 "or only some data does not merge claims.") if len(members) > 1 else None,
    }
    text = str(record.get("claim") or "")
    key_group = key_conclusion_group(record)
    return {
        "claim_id": claim_id,
        "claim": {
            "text": text, "evidence_text": record.get("evidence") if record.get("evidence") != text else None,
            "agent": record.get("agent"), "claim_quality": record.get("claim_quality"),
            "direction": record.get("direction"), "confidence": record.get("confidence"),
            "report_location": _report_location(ctx, record), "agent_wording": agent_wording(text),
            "key_conclusion_group": key_group,
        },
        "sources": sources,
        "source_support": source_support,
        "alpha_match": alpha_match,
        "stance": stance,
        "scoring": scoring,
        "calculation": {
            "data_points": [p.to_dict() for p in grounding.data_points],
            "derived_calculations": [c.to_dict() for c in grounding.derived_calculations],
            "ambiguous_tokens": grounding.ambiguous_tokens,
            "unreproduced_percent_tokens": grounding.unreproduced_percent_tokens,
            "numbers_not_found_in_saved_data": grounding.unmatched_tokens,
            "scope_note": ("A reproduced calculation proves the arithmetic from the saved rows only; it does not verify "
                           "the rest of the statement and does not change verified-support eligibility.")
            if grounding.derived_calculations else None,
        },
        "dependency": dependency,
        # present only for a run that applied alpha_evidence_consumption.v2 -- a legacy run's trace has no such key
        **({"consumption": _consumption_view(ctx, claim_id, match)} if ctx.consumption_active else {}),
        # P4 phase 1: the experimental relevance judgment of the claim and its matched Alpha (a claim matched to no Alpha has none)
        **({"relevance_judgment": _relevance_view(ctx, claim_id, match)} if match is not None and match.get("match_status") == "matched" else {}),
        "conflict_adoption": {
            "entries": ctx.conflict_index.get(claim_id, []),
            "note": HISTORICAL_USE_NOTE if ctx.conflict_index.get(claim_id) else None,
        },
        "run_basis": {
            "link_fields_saved": record.get("source_link_status") is not None,
            "note": LEGACY_RUN_NOTE if record.get("source_link_status") is None else None,
        },
        "summary": {
            "source_support": source_support["status_code"], "alpha_match": alpha_match["status_code"],
            "stance": stance["status_code"], "scoring": scoring["status_code"],
        },
        "note": SCOPE_OF_VERIFICATION_NOTE,
    }


def compact_row(trace: Mapping[str, Any]) -> dict[str, Any]:
    """The one-line status row used by the key-conclusions view (details are fetched per claim on click)."""
    claim = trace["claim"]
    return {
        "claim_id": trace["claim_id"], "text": claim["text"], "agent": claim["agent"],
        "section": claim["report_location"].get("section"), "claim_index": claim["report_location"].get("claim_index"),
        "claim_quality": claim["claim_quality"], "agent_wording": claim["agent_wording"],
        "source_support": {k: trace["source_support"][k] for k in ("status_code", "label", "reason")},
        "alpha_match": {k: trace["alpha_match"].get(k) for k in ("status_code", "label", "reason", "matched_alpha")},
        "stance": {k: trace["stance"].get(k) for k in ("status_code", "label", "reason", "evidence_stance", "method", "relation")},
        "scoring": {k: trace["scoring"].get(k) for k in ("status_code", "label", "reason", "alpha_id", "weight_contribution", "not_scored_code")},
        "linked_source_ids": [s["source_id"] for s in trace["sources"]],
    }


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


def key_conclusion_claim_ids(ctx: TraceContext) -> list[tuple[str, str]]:
    return [(str(r.get("claim_id")), g) for r in ctx.records if (g := key_conclusion_group(r))]


def build_key_conclusions(ctx: TraceContext) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    status_counts: dict[str, dict[str, int]] = {"source_support": {}, "alpha_match": {}, "stance": {}, "scoring": {}}
    total = 0
    for claim_id, group in key_conclusion_claim_ids(ctx):
        trace = build_claim_trace(ctx, claim_id)
        if trace is None:
            continue
        groups.setdefault(group, []).append(compact_row(trace))
        total += 1
        for dimension, code in trace["summary"].items():
            status_counts[dimension][code] = status_counts[dimension].get(code, 0) + 1
    # the run-level execution basis, for a run under the evidence contract or produced by the consumption recompute entry (every other
    # run's view is unchanged): the research page states, before any claim is opened, that a recomputation is not a Fresh Run
    basis_shown = ctx.consumption_active or (ctx.metadata or {}).get("execution_type") == CONSUMPTION_RECOMPUTE_EXECUTION_TYPE
    return {
        "rule": KEY_CONCLUSION_RULE, "claim_count": total, "status_counts": status_counts,
        "groups": [{"group": name, "rows": rows} for name, rows in groups.items()],
        "agent_wording_verified_count": sum(1 for rows in groups.values() for r in rows if r["agent_wording"]["self_labeled_verified"]),
        **({"execution_basis": _execution_basis(ctx)} if basis_shown else {}),
    }


def _alpha_summaries(ctx: TraceContext) -> list[dict[str, Any]]:
    out = []
    for alpha_id, block in sorted(ctx.alpha_blocks.items()):
        result = _alpha_result(ctx, alpha_id, block)
        out.append({
            "alpha_id": alpha_id, "alpha_name": block.get("alpha_name"), "activation_score": block.get("activation_score"),
            "level": result["level"], "claims_in_pool": result["claims_in_pool"],
            "independent_facts": result["independent_facts"], "distinct_agents": result["distinct_agents"],
            "distinct_sources": result["distinct_sources"], "claim_ids": list(block.get("claim_ids") or []),
            "fact_groups": [
                {"id": g.get("evidence_fact_group_id"), "member_claim_ids": g.get("member_claim_ids"), "supporting_agents": g.get("supporting_agents")}
                for g in block.get("evidence_fact_groups") or [] if isinstance(g, dict)
            ],
            "components": block.get("components"), "cap_reason_codes": block.get("cap_reason_codes"),
        })
    return out


def _calculation_summary(ctx: TraceContext) -> dict[str, Any]:
    """Every calculation reproducible from the saved rows, over ALL linked claims of the run (not only the traced
    ones): which claim states it, the formula, the saved inputs (source, row, period, value, content hash) and the
    result. A reproduced calculation proves the arithmetic only."""
    calculations = []
    claims_with_calculations = 0
    for record in ctx.records:
        if record.get("source_link_status") != "VALID":
            continue
        grounding = _grounding(ctx, record)
        if not grounding.derived_calculations:
            continue
        claims_with_calculations += 1
        for calc in grounding.derived_calculations:
            calculations.append({"claim_id": record.get("claim_id"), "agent": record.get("agent"), **calc.to_dict()})
    return {
        "claims_with_reproduced_calculations": claims_with_calculations,
        "reproduced_calculation_count": len(calculations),
        "scope_note": ("Each calculation was recomputed from the rows saved in this run's own source registry (no later data). "
                       "It proves the arithmetic only; it does not verify the rest of the statement and does not change "
                       "verified-support eligibility."),
        "calculations": calculations,
    }


def build_evidence_trace_artifact(run_id: Any, output_root: Any, *, ctx: TraceContext | None = None) -> dict[str, Any] | None:
    """The exported ``evidence_trace.json``: full traces for every official-pool claim and every key-conclusion claim."""
    ctx = ctx or load_trace_context(run_id, output_root)
    if ctx is None:
        return None
    wanted: dict[str, str | None] = {cid: None for cid in ctx.pool_index}
    for cid, group in key_conclusion_claim_ids(ctx):
        wanted[cid] = group
    items = {}
    for cid in sorted(wanted):
        trace = build_claim_trace(ctx, cid)
        if trace is not None:
            items[cid] = trace
    return {
        "schema_version": EVIDENCE_TRACE_SCHEMA_VERSION,
        "run_id": ctx.run_id, "ticker": ctx.ticker,
        "lineage": {k: ctx.metadata.get(k) for k in ("based_on_run_id", "root_research_run_id", "execution_type") if ctx.metadata.get(k)},
        "contracts": {
            "fact_dependency_contract": ctx.metadata.get("fact_dependency_contract"),
            **({CONSUMPTION_METADATA_KEY: CONSUMPTION_CONTRACT_V2} if ctx.consumption_active else {}),
        },
        "scope": "official-pool claims of every Alpha plus the final-decision chain (key conclusions); any other claim is available from the API by claim_id",
        "four_checks_note": SCOPE_OF_VERIFICATION_NOTE,
        "key_conclusions": build_key_conclusions(ctx),
        # P4 phase 1: the run's experimental relevance judgments in counts (present: false = none exist; nothing is consumed)
        "relevance_judgments": ctx.relevance.summary() if ctx.relevance is not None else {
            "contract": relevance_record.RESULTS_SCHEMA_VERSION, "error": "relevance_verification_error"},
        "calculations": _calculation_summary(ctx),
        "alphas": _alpha_summaries(ctx),
        "item_count": len(items),
        "items": items,
    }


def get_evidence_trace_response(
    run_id: Any, output_root: Any = "outputs/runs", *, claim_id: str | None = None, scope: str | None = None
) -> dict[str, Any]:
    """``GET /api/research/{run_id}/evidence-trace``: ``claim_id=`` -> one full trace, ``scope=key`` -> the
    key-conclusion status rows, neither -> the whole exported artifact. Soft-200 envelope like the other read routes."""

    def failed(code: str) -> dict[str, Any]:
        return {"run_id": str(run_id), "status": "failed", "error_code": code}

    try:
        safe_run_id = validate_run_id_for_path(run_id)
    except ValueError:
        return failed("INVALID_RUN_ID")
    ctx = load_trace_context(safe_run_id, output_root)
    if ctx is None:
        return failed("RUN_NOT_FOUND" if not run_dir_for(safe_run_id, output_root).exists() else "EVIDENCE_TRACE_UNAVAILABLE")
    base = {"run_id": ctx.run_id, "ticker": ctx.ticker, "status": "ok", "schema_version": EVIDENCE_TRACE_SCHEMA_VERSION}
    if claim_id:
        trace = build_claim_trace(ctx, claim_id)
        if trace is None:
            return failed("CLAIM_NOT_FOUND")
        return {**base, "item": trace}
    if scope == "key":
        return {**base, "key_conclusions": build_key_conclusions(ctx)}
    artifact = build_evidence_trace_artifact(safe_run_id, output_root, ctx=ctx)
    return {**base, **{k: v for k, v in (artifact or {}).items() if k not in base}}


__all__ = [
    "EVIDENCE_TRACE_FILENAME",
    "EVIDENCE_TRACE_SCHEMA_VERSION",
    "KEY_CONCLUSION_RULE",
    "TraceContext",
    "agent_wording",
    "build_claim_trace",
    "build_evidence_trace_artifact",
    "build_key_conclusions",
    "get_evidence_trace_response",
    "key_conclusion_group",
    "load_trace_context",
]
