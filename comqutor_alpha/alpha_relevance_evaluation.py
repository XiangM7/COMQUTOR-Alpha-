"""P4 phase 2 (2026-10-12): evaluation of one execution of a small-sample relevance plan.

Inputs: the sample manifest, the plan, the evaluation directory written by ``run_relevance_evaluation_plan`` and one or two filled blind
review sheets. Nothing here calls a model, and nothing reads an engineering draft, a saved ``matched_alpha`` or another model's answer:
reference labels come ONLY from reviewer A's rows marked ``CONFIRMED`` (and internally consistent). Every other row stays pending -- the
program never fills an answer in.

Every planned pair stays in the totals, and the rates are reported side by side, never by dropping failures:

  * per round: valid-return rate ((JUDGED + UNRESOLVED) / planned), result coverage (JUDGED / planned), failure and not-sent rates,
    FAILED reasons split into call-level, contract-level and read-time verification, UNRESOLVED cases with the model's reason;
  * on owner-confirmed DETERMINED pairs (round 1): unconditional agreement (FAILED / UNRESOLVED / not sent count as not agreeing),
    coverage, and conditional agreement (only where the model gave a tier), each with a 95% Wilson interval; the confusion matrix
    (reference tier x model outcome incl. UNRESOLVED / FAILED / NOT_SENT); per-tier precision and recall; core<->strong confusions and
    every wrong "none", by sample;
  * repeat consistency of state and tier between the identical requests of round 1 and round 2;
  * agreement between two human reviewers only when two independent sheets exist; model-vs-reference agreement separately;
  * requests, provider attempts, tokens (with reasoning and provider-cache split), latency, finish reasons and cost from the recorded
    usage and the recorded price table;
  * the plan's quality thresholds, applied only when the owner confirmed them in the authorization (i.e. before the execution) and
    never on a simulated rehearsal.

Every result is verified against its round's OWN relevance ledger (``verify_relevance_records``) before it is counted.
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from comqutor_alpha import alpha_relevance_eval_prep as ep
from comqutor_alpha.alpha_library.alpha_relevance_elements import (
    AlphaRelevanceDefinition,
    load_relevance_definitions,
    sha256_canonical_json,
)
from comqutor_alpha.graph_engine.alpha_relevance_judgment import (
    verify_relevance_records,
)
from comqutor_alpha.structure_engine import alpha_relevance_llm as rl

REPORT_SCHEMA = "alpha_relevance_eval_report.v1"
EVAL_RECORD_FILENAME = "execution_record.json"
NOT_SENT = "NOT_SENT"
MODEL_OUTCOMES = (*rl.TIERS, rl.STATE_UNRESOLVED, rl.STATE_FAILED, NOT_SENT)
VALID_STATES = (rl.STATE_JUDGED, rl.STATE_UNRESOLVED)
CALL_FAILURES = frozenset({rl.FAILURE_PROVIDER_ERROR, rl.FAILURE_TIMEOUT, rl.FAILURE_BUDGET_EXHAUSTED, rl.FAILURE_PROVIDER_STOPPED,
                           rl.FAILURE_INPUT_TOO_LARGE, rl.FAILURE_MALFORMED_RESPONSE})
CONTRACT_FAILURES = frozenset({rl.FAILURE_MISSING_RESULT, rl.FAILURE_DUPLICATE_RESULT, rl.FAILURE_IDENTITY_MISMATCH, rl.FAILURE_INVALID_LABEL,
                               rl.FAILURE_ANCHOR_INVALID, rl.FAILURE_TIER_ANCHOR_INCONSISTENT, rl.FAILURE_EVIDENCE_INVALID})

ROW_MISSING = "MISSING"
ROW_INVALID = "INVALID"
REFERENCE_STATUSES = (*ep.REVIEW_STATUSES, ROW_INVALID, ROW_MISSING)
SAMPLE_TABLE_COLUMNS = (
    "sample_id", "target_alpha_id", "ticker", "primary_stratum", "reference_status", "reference_label", "reviewer_b_label",
    "round_1_outcome", "round_1_reason", "round_1_anchor_element_ids", "agrees_with_reference", "round_2_outcome", "repeat_identical",
    "claim_text",
)


class EvaluationInputError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


# ----------------------------------------------------------------------------------------------------------- statistics
def wilson_interval(successes: int, n: int, z: float = 1.959964) -> list[float] | None:
    if n <= 0:
        return None
    p = successes / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def cohen_kappa(pairs: Sequence[tuple[str, str]]) -> float | None:
    """Unweighted Cohen's kappa; None when undefined (no pairs, or both raters used one and the same single category)."""
    n = len(pairs)
    if n == 0:
        return None
    first, second = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    observed = sum(1 for a, b in pairs if a == b) / n
    expected = sum(first[c] / n * second[c] / n for c in set(first) | set(second))
    if expected >= 1:
        return None
    return round((observed - expected) / (1 - expected), 4)


def _rate(k: int, n: int) -> float | None:
    return round(k / n, 4) if n else None


def _ratio_block(k: int, n: int) -> dict[str, Any]:
    return {"count": k, "n": n, "rate": _rate(k, n), "wilson_95": wilson_interval(k, n)}


# ----------------------------------------------------------------------------------------------------------- review sheets
@dataclass
class ReviewRow:
    sample_id: str
    status: str
    outcome: str | None = None
    tier: str | None = None
    anchors: tuple[str, ...] = ()
    basis: str = ""
    ambiguity_note: str = ""
    reviewer: str = ""
    reviewed_at: str = ""
    problems: list[str] = field(default_factory=list)

    @property
    def label(self) -> str | None:
        """The confirmed label (a tier, or UNRESOLVED) -- None for every row that is not a usable confirmation."""
        if self.status != ep.REVIEW_STATUS_CONFIRMED:
            return None
        return rl.STATE_UNRESOLVED if self.outcome == rl.OUTCOME_UNRESOLVED else self.tier


@dataclass
class ReviewSheet:
    path: str
    sha256: str
    rows: dict[str, ReviewRow]
    problems: list[dict[str, Any]]

    @property
    def reviewers(self) -> list[str]:
        return sorted({r.reviewer.strip().lower() for r in self.rows.values() if r.reviewer.strip()})

    def status_counts(self) -> dict[str, int]:
        counts = Counter(r.status for r in self.rows.values())
        return {s: counts.get(s, 0) for s in REFERENCE_STATUSES}


def _normalized(text: Any) -> str:
    return " ".join(str(text or "").split())


def _parse_row(row: Mapping[str, Any], sample: Mapping[str, Any], definition: AlphaRelevanceDefinition) -> ReviewRow:
    problems = []
    if _normalized(row.get("claim_text")) != _normalized(sample["claim_text"]) or _normalized(row.get("target_alpha_id")) != sample["target_alpha_id"]:
        problems.append("ROW_CONTENT_CHANGED")  # the row no longer shows the claim / Alpha of its sample id (e.g. a mis-sorted sheet)
    status = _normalized(row.get("review_status")).upper() or ep.REVIEW_STATUS_PENDING
    outcome = _normalized(row.get("outcome")).upper() or None
    tier = _normalized(row.get("tier")).lower() or None
    anchors = tuple(a for a in re.split(r"[;,\s]+", str(row.get("anchor_element_ids") or "")) if a)
    if status not in ep.REVIEW_STATUSES:
        problems.append(f"REVIEW_STATUS_INVALID:{status}")
    elif status == ep.REVIEW_STATUS_CONFIRMED:
        if outcome not in rl.OUTCOMES:
            problems.append("OUTCOME_INVALID")
        elif outcome == rl.OUTCOME_UNRESOLVED:
            if tier:
                problems.append("TIER_ON_UNRESOLVED")
        elif tier not in rl.TIERS:
            problems.append("TIER_INVALID")
        else:
            unknown = [a for a in anchors if a not in definition.ownership]
            owners = {definition.ownership.get(a) for a in anchors}
            if unknown:
                problems.append("ANCHOR_UNKNOWN:" + ",".join(unknown))
            elif tier == rl.TIER_CORE and "core" not in owners:
                problems.append("CORE_WITHOUT_CORE_OWNED_ANCHOR")
            elif tier == rl.TIER_STRONG and ("strong" not in owners or "core" in owners):
                problems.append("STRONG_ANCHORS_INCONSISTENT")
            elif tier in (rl.TIER_WEAK, rl.TIER_NONE) and anchors:
                problems.append("ANCHORS_ON_WEAK_OR_NONE")
    return ReviewRow(sample_id=str(sample["sample_id"]), status=ROW_INVALID if problems else status, outcome=outcome, tier=tier, anchors=anchors,
                     basis=str(row.get("basis") or ""), ambiguity_note=str(row.get("ambiguity_note") or ""), reviewer=str(row.get("reviewer") or ""),
                     reviewed_at=str(row.get("reviewed_at") or ""), problems=problems)


def load_review_sheet(path: Path | str, manifest: Mapping[str, Any], definitions: Mapping[str, AlphaRelevanceDefinition]) -> ReviewSheet:
    """A filled blind review sheet, aligned to the manifest by sample id. Never fills or guesses an answer: a missing row is MISSING, a
    row with an unusable value is INVALID (with the reason), and only a consistent CONFIRMED row carries a label."""
    raw = Path(path).read_bytes()
    samples = {s["sample_id"]: s for s in manifest["samples"]}
    problems: list[dict[str, Any]] = []
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        problems.append({"problem": "SHEET_NOT_UTF8", "fix": "save the sheet as CSV UTF-8"})
        return ReviewSheet(str(path), ep._sha256_bytes(raw), {sid: ReviewRow(sid, ROW_MISSING) for sid in samples}, problems)  # noqa: SLF001
    reader = csv.DictReader(io.StringIO(text))
    missing_columns = [c for c in ep.REVIEW_COLUMNS if c not in (reader.fieldnames or [])]
    if missing_columns:
        problems.append({"problem": "SHEET_COLUMNS_MISSING", "columns": missing_columns})
        return ReviewSheet(str(path), ep._sha256_bytes(raw), {sid: ReviewRow(sid, ROW_MISSING) for sid in samples}, problems)  # noqa: SLF001
    entries: dict[str, list[tuple[int, Mapping[str, Any]]]] = {}
    for line, row in enumerate(reader, start=2):
        sample_id = _normalized(row.get("sample_id"))
        if sample_id not in samples:
            problems.append({"problem": "UNKNOWN_SAMPLE", "line": line, "sample_id": sample_id})
            continue
        entries.setdefault(sample_id, []).append((line, row))
    rows: dict[str, ReviewRow] = {}
    for sample_id, sample in samples.items():
        found = entries.get(sample_id) or []
        if not found:
            rows[sample_id] = ReviewRow(sample_id, ROW_MISSING)
        elif len(found) > 1:
            lines = [line for line, _ in found]
            rows[sample_id] = ReviewRow(sample_id, ROW_INVALID, problems=[f"DUPLICATE_ROW:lines {lines}"])
            problems.append({"problem": "DUPLICATE_ROW", "sample_id": sample_id, "lines": lines})
        else:
            rows[sample_id] = _parse_row(found[0][1], sample, definitions[sample["target_alpha_id"]])
    return ReviewSheet(str(path), ep._sha256_bytes(raw), rows, problems)  # noqa: SLF001


# ----------------------------------------------------------------------------------------------------------- execution
def _model_outcome(view: Mapping[str, Any]) -> str:
    if view["state"] == rl.STATE_JUDGED:
        return str(view["tier"])
    if view["state"] == rl.STATE_UNJUDGED:
        return NOT_SENT
    return str(view["state"])


def load_execution(eval_dir: Path | str, manifest: Mapping[str, Any], plan: Mapping[str, Any],
                   definitions: Mapping[str, AlphaRelevanceDefinition]) -> dict[str, Any]:
    """Every planned pair of every round, verified against that round's own relevance ledger (pairs never sent stay NOT_SENT)."""
    eval_dir = Path(eval_dir)
    try:
        record = json.loads((eval_dir / EVAL_RECORD_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EvaluationInputError("EXECUTION_RECORD_UNREADABLE", str(eval_dir)) from exc
    if record.get("plan_sha256") != plan["plan_sha256"]:
        raise EvaluationInputError("EXECUTION_PLAN_MISMATCH")
    if record.get("sample_manifest_content_sha256") != manifest["content_sha256"]:
        raise EvaluationInputError("EXECUTION_MANIFEST_MISMATCH")
    samples = {s["sample_id"]: s for s in manifest["samples"]}
    rounds: dict[int, dict[str, Any]] = {}
    not_sent_by_plan = {str(e["sample_id"]): str(e["reason"]) for e in plan.get("not_sent") or []}  # session 6: kept in the table, never sent
    for round_plan in plan["rounds"]:
        number = int(round_plan["round"])
        round_id = f"{record['evaluation_id']}-r{number}"
        planned = [sid for batch in round_plan["batches"] for sid in batch["sample_ids"]]
        pairs = {(samples[sid]["claim_id"], samples[sid]["target_alpha_id"]):
                 (samples[sid]["ticker"], {"claim_id": samples[sid]["claim_id"], "matched_alpha": samples[sid]["target_alpha_id"], "claim": samples[sid]["claim_text"]})
                 for sid in planned}
        # verified against the task identity the plan was made for: an execution under prompt v1 is read as v1, never as a later version
        verification = verify_relevance_records(eval_dir / round_id, owner_run_id=round_id, pairs=pairs, definitions=definitions, identity=plan["task"])
        views = {}
        for sid in planned:
            view = dict(verification.pairs[(samples[sid]["claim_id"], samples[sid]["target_alpha_id"])])
            view["model_outcome"] = _model_outcome(view)
            views[sid] = view
        if number == 1:
            for sid, reason in sorted(not_sent_by_plan.items()):
                views[sid] = {"state": rl.STATE_UNJUDGED, "tier": None, "reason": "not_sent_by_plan", "reason_detail": reason,
                              "anchor_element_ids": [], "basis": None, "unresolved_reason": None, "model_outcome": NOT_SENT}
        ledger = verification.ledger
        rounds[number] = {
            "round": number, "round_run_id": round_id, "results_present": verification.present, "views": views,
            "orphan_records": len(verification.orphan_records), "error": verification.error,
            "ledger": ledger.description() if ledger is not None else None,
            "calls": sorted(ledger.records.values(), key=lambda c: int(c.get("call_sequence") or 0)) if ledger is not None else [],
        }
    return {"record": record, "rounds": rounds}


# ----------------------------------------------------------------------------------------------------------- metrics
def round_totals(views: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    n = len(views)
    outcomes = Counter(v["model_outcome"] for v in views.values())
    judged = sum(outcomes.get(t, 0) for t in rl.TIERS)
    unresolved, failed, not_sent = outcomes.get(rl.STATE_UNRESOLVED, 0), outcomes.get(rl.STATE_FAILED, 0), outcomes.get(NOT_SENT, 0)
    reasons = Counter(str(v.get("reason")) for v in views.values() if v["state"] == rl.STATE_FAILED)
    categories = {"call_level": sum(c for r, c in reasons.items() if r in CALL_FAILURES),
                  "contract_level": sum(c for r, c in reasons.items() if r in CONTRACT_FAILURES),
                  "read_time_verification": sum(c for r, c in reasons.items() if r not in CALL_FAILURES and r not in CONTRACT_FAILURES)}
    return {
        "planned_pairs": n,
        "outcomes": {o: outcomes.get(o, 0) for o in MODEL_OUTCOMES},
        "valid_return_rate": _rate(judged + unresolved, n), "result_coverage": _rate(judged, n), "failure_rate": _rate(failed, n),
        "not_sent_rate": _rate(not_sent, n), "unresolved_rate": _rate(unresolved, n),
        "failure_reasons": dict(sorted(reasons.items())), "failure_categories": categories, "contract_failures": categories["contract_level"],
        "failed_cases": [{"sample_id": sid, "reason": v.get("reason"), "detail": v.get("reason_detail")} for sid, v in sorted(views.items()) if v["state"] == rl.STATE_FAILED],
        "unresolved_cases": [{"sample_id": sid, "unresolved_reason": v.get("unresolved_reason")} for sid, v in sorted(views.items()) if v["state"] == rl.STATE_UNRESOLVED],
    }


def reference_metrics(views: Mapping[str, Mapping[str, Any]], sheet: ReviewSheet) -> dict[str, Any]:
    """Model (round 1) against reviewer A's confirmed labels only."""
    confirmed = {sid: row for sid, row in sheet.rows.items() if row.label is not None and sid in views}
    determined = {sid: row for sid, row in confirmed.items() if row.outcome == rl.OUTCOME_DETERMINED}
    ambiguous = {sid: row for sid, row in confirmed.items() if row.outcome == rl.OUTCOME_UNRESOLVED}
    n = len(determined)
    agree = [sid for sid, row in determined.items() if views[sid]["model_outcome"] == row.tier]
    covered = [sid for sid in determined if views[sid]["model_outcome"] in rl.TIERS]
    confusion = {tier: dict.fromkeys(MODEL_OUTCOMES, 0) for tier in rl.TIERS}
    for sid, row in determined.items():
        confusion[str(row.tier)][views[sid]["model_outcome"]] += 1
    per_tier = {}
    for tier in rl.TIERS:
        support = sum(1 for row in determined.values() if row.tier == tier)
        predicted = sum(1 for sid in determined if views[sid]["model_outcome"] == tier)
        hits = confusion[tier][tier]
        per_tier[tier] = {"reference_support": support, "model_judged_as": predicted, "agree": hits,
                          "recall": _rate(hits, support), "precision": _rate(hits, predicted)}

    def case(sid: str) -> dict[str, Any]:
        view = views[sid]
        return {"sample_id": sid, "reference": determined[sid].tier if sid in determined else rl.STATE_UNRESOLVED, "model": view["model_outcome"],
                "model_anchor_element_ids": list(view.get("anchor_element_ids") or []), "reference_anchor_element_ids": list(confirmed[sid].anchors)}

    labelled = [(row.label, views[sid]["model_outcome"]) for sid, row in confirmed.items() if views[sid]["state"] in VALID_STATES]
    return {
        "reference_rows": sheet.status_counts(), "confirmed": len(confirmed), "confirmed_determined": n, "confirmed_unresolved": len(ambiguous),
        "unconditional_agreement": _ratio_block(len(agree), n),
        "coverage": _ratio_block(len(covered), n),
        "conditional_agreement": _ratio_block(len(agree), len(covered)),
        "unresolved_share_on_determined": _ratio_block(sum(1 for sid in determined if views[sid]["model_outcome"] == rl.STATE_UNRESOLVED), n),
        "failed_on_determined": sum(1 for sid in determined if views[sid]["model_outcome"] == rl.STATE_FAILED),
        "not_sent_on_determined": sum(1 for sid in determined if views[sid]["model_outcome"] == NOT_SENT),
        "confusion_matrix": {"rows": "reference tier", "columns": list(MODEL_OUTCOMES), "cells": confusion},
        "per_tier": per_tier,
        "core_strong_confusions": [case(sid) for sid in sorted(determined) if {determined[sid].tier, views[sid]["model_outcome"]} == {rl.TIER_CORE, rl.TIER_STRONG}],
        "wrong_none": [case(sid) for sid in sorted(determined) if views[sid]["model_outcome"] == rl.TIER_NONE and determined[sid].tier != rl.TIER_NONE],
        "none_on_core": {"count": sum(1 for sid in determined if determined[sid].tier == rl.TIER_CORE and views[sid]["model_outcome"] == rl.TIER_NONE),
                         "n": sum(1 for row in determined.values() if row.tier == rl.TIER_CORE)},
        "on_confirmed_unresolved": [{**case(sid), "ambiguity_note": ambiguous[sid].ambiguity_note} for sid in sorted(ambiguous)],
        "model_vs_reference_agreement": {
            "scope": "confirmed rows (a tier or UNRESOLVED) where the model returned a valid result; FAILED / not sent are excluded here and counted above",
            "n": len(labelled), "excluded_model_invalid": len(confirmed) - len(labelled),
            "agreement": _rate(sum(1 for a, b in labelled if a == b), len(labelled)), "cohen_kappa": cohen_kappa(labelled)},
    }


def repeat_consistency(first: Mapping[str, Mapping[str, Any]], second: Mapping[str, Mapping[str, Any]], subset: Sequence[str]) -> dict[str, Any]:
    comparable, identical, valid_both, identical_valid, anchors_same, judged_same_tier = [], [], [], [], 0, 0
    flips = []
    for sid in subset:
        a, b = first.get(sid), second.get(sid)
        if a is None or b is None or NOT_SENT in (a["model_outcome"], b["model_outcome"]):
            continue
        comparable.append(sid)
        same = a["model_outcome"] == b["model_outcome"]
        if same:
            identical.append(sid)
        else:
            flips.append({"sample_id": sid, "round_1": a["model_outcome"], "round_2": b["model_outcome"],
                          "round_1_reason": a.get("reason"), "round_2_reason": b.get("reason")})
        if a["state"] in VALID_STATES and b["state"] in VALID_STATES:
            valid_both.append(sid)
            if same:
                identical_valid.append(sid)
        if same and a["state"] == rl.STATE_JUDGED:
            judged_same_tier += 1
            anchors_same += int(sorted(a.get("anchor_element_ids") or []) == sorted(b.get("anchor_element_ids") or []))
    return {
        "repeat_subset": len(subset), "comparable": len(comparable), "not_comparable": len(subset) - len(comparable),
        "identical_share_comparable": _ratio_block(len(identical), len(comparable)),
        "identical_share_valid_in_both": _ratio_block(len(identical_valid), len(valid_both)),
        "same_anchors_when_same_tier": {"count": anchors_same, "n": judged_same_tier, "rate": _rate(anchors_same, judged_same_tier)},
        "flips": flips,
    }


def inter_annotator_agreement(sheet_a: ReviewSheet, sheet_b: ReviewSheet | None) -> dict[str, Any]:
    if sheet_b is None:
        return {"status": "NOT_COMPUTED", "why": "only one independent annotation exists"}
    if sheet_a.sha256 == sheet_b.sha256 or (set(sheet_a.reviewers) & set(sheet_b.reviewers)):
        return {"status": "NOT_INDEPENDENT", "why": "the two sheets are the same file or share a reviewer name", "reviewers_a": sheet_a.reviewers,
                "reviewers_b": sheet_b.reviewers}
    labelled = [(row.label, sheet_b.rows[sid].label, sid) for sid, row in sheet_a.rows.items()
                if row.label is not None and sid in sheet_b.rows and sheet_b.rows[sid].label is not None]
    pairs = [(a, b) for a, b, _ in labelled]
    return {"status": "COMPUTED", "n_both_confirmed": len(pairs), "agreement": _rate(sum(1 for a, b in pairs if a == b), len(pairs)),
            "cohen_kappa": cohen_kappa(pairs), "disagreements": [{"sample_id": sid, "reviewer_a": a, "reviewer_b": b} for a, b, sid in labelled if a != b]}


def usage_summary(rounds: Mapping[int, Mapping[str, Any]], prices: Mapping[str, Any] | None, record: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Requests and attempts as the execution entry counted them (its batch log); tokens, latency, finish reasons, caps and cost from the
    calls recorded in the rounds' own ledgers."""
    calls = [c for r in rounds.values() for c in r["calls"]]
    sent = [b for b in (record or {}).get("batches") or [] if b.get("status") == "SENT"]
    tokens = {"input": 0, "output": 0, "reasoning": 0, "cache_hit_input": 0, "cache_miss_input": 0}
    cache_split_known = True
    latencies, finish, caps, over_cap, semantic_cache_hits, retries, attempt_entries, metadata_calls = [], Counter(), set(), 0, 0, 0, 0, 0
    for call in calls:
        usage = call.get("token_usage") if isinstance(call.get("token_usage"), Mapping) else {}
        raw = ((call.get("provider_response") or {}).get("raw_usage") or {}) if isinstance(call.get("provider_response"), Mapping) else {}
        tokens["input"] += int(usage.get("input_tokens") or 0)
        tokens["output"] += int(usage.get("output_tokens") or 0)
        tokens["reasoning"] += int(((raw.get("completion_tokens_details") or {}).get("reasoning_tokens")) or 0)
        if raw.get("prompt_cache_hit_tokens") is None or raw.get("prompt_cache_miss_tokens") is None:
            cache_split_known = cache_split_known and not usage.get("input_tokens")
        else:
            tokens["cache_hit_input"] += int(raw["prompt_cache_hit_tokens"])
            tokens["cache_miss_input"] += int(raw["prompt_cache_miss_tokens"])
        if call.get("latency_ms") is not None:
            latencies.append(float(call["latency_ms"]) / 1000)
        finish[str((call.get("provider_response") or {}).get("finish_reason") if isinstance(call.get("provider_response"), Mapping) else None)] += 1
        cap = (call.get("request_control") or {}).get("max_tokens_value") if isinstance(call.get("request_control"), Mapping) else None
        if cap:
            caps.add(int(cap))
            over_cap += int(int(usage.get("output_tokens") or 0) > int(cap))
        semantic_cache_hits += int(bool((call.get("cache") or {}).get("hit")) if isinstance(call.get("cache"), Mapping) else 0)
        retries += int(call.get("retry_count") or 0)
        attempt_entries += len(call.get("request_attempts") or []) if isinstance(call.get("request_attempts"), list) else 0
        metadata_calls += int(isinstance(call.get("provider_response"), Mapping) and len(call["provider_response"]) > 1)
    cost = None
    if prices is not None:
        cost = {"off_peak": ep.usd(prices["off_peak"], tokens["input"], tokens["output"]), "peak": ep.usd(prices["peak"], tokens["input"], tokens["output"]),
                "with_provider_cache_split": None, "price_source": prices.get("source")}
        hit = prices.get("cache_hit_input")
        if hit and cache_split_known:
            cost["with_provider_cache_split"] = {
                period: round(tokens["cache_miss_input"] / 1e6 * prices[period][0] + tokens["cache_hit_input"] / 1e6 * hit[period] + tokens["output"] / 1e6 * prices[period][1], 4)
                for period in ("off_peak", "peak")}
    return {
        "requests_sent": len(sent), "provider_attempts": sum(int(b.get("provider_attempts") or 0) for b in sent),
        "recorded_calls": len(calls), "calls_with_provider_metadata": metadata_calls, "ledger_attempt_entries": attempt_entries,
        "retries": retries, "semantic_cache_hits": semantic_cache_hits,
        "tokens": tokens, "reasoning_share_of_output": _rate(tokens["reasoning"], tokens["output"]),
        "latency_seconds_per_call": ep._quantiles(latencies),  # noqa: SLF001
        "finish_reasons": dict(sorted(finish.items())), "max_tokens_values": sorted(caps), "calls_over_max_tokens": over_cap, "cost_usd": cost,
        "model_names": ep.model_names_in_calls(calls),
    }


def apply_thresholds(plan: Mapping[str, Any], record: Mapping[str, Any], flat: Mapping[str, tuple[Any, int]]) -> dict[str, Any]:
    thresholds = plan["quality_thresholds"]
    auth = record.get("authorization") or {}
    if record.get("test_data"):
        return {"status": "NOT_APPLIED", "why": "simulated rehearsal: every answer is TEST DATA"}
    if not thresholds.get("thresholds"):
        return {"status": "NOT_APPLICABLE", "why": thresholds.get("rule") or "the plan defines no quality threshold"}
    if auth.get("quality_thresholds_confirmed") is not True or auth.get("quality_thresholds_sha256") != plan.get("quality_thresholds_sha256") \
            or sha256_canonical_json(thresholds) != plan.get("quality_thresholds_sha256"):
        return {"status": "NOT_APPLIED", "why": "the owner did not confirm these thresholds in the authorization, i.e. before the execution"}
    results = []
    for t in thresholds["thresholds"]:
        if not t.get("metric_key"):
            results.append({"id": t["id"], "verdict": "REPORTED", "metric": t["metric"]})
            continue
        value, n = flat.get(t["metric_key"], (None, 0))
        if value is None or n < int(t.get("min_n") or 0):
            verdict = "NOT_EVALUABLE"
        elif t["comparator"] == ">=":
            verdict = "PASS" if value >= t["value"] else "FAIL"
        else:
            verdict = "PASS" if value <= t["value"] else "FAIL"
        results.append({"id": t["id"], "metric": t["metric"], "value": value, "n": n, "min_n": t.get("min_n"),
                        "threshold": f"{t['comparator']} {t['value']}", "verdict": verdict})
    return {"status": "APPLIED", "results": results}


# ----------------------------------------------------------------------------------------------------------- report
def evaluate(
    *,
    manifest: Mapping[str, Any],
    plan: Mapping[str, Any],
    eval_dir: Path | str,
    review_a: Path | str,
    review_b: Path | str | None = None,
    definitions: Mapping[str, AlphaRelevanceDefinition] | None = None,
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    if ep.manifest_content_sha256(manifest) != manifest.get("content_sha256"):
        raise EvaluationInputError("MANIFEST_HASH_MISMATCH")
    if ep.plan_content_sha256(plan) != plan.get("plan_sha256") or plan["sample_manifest"]["content_sha256"] != manifest["content_sha256"]:
        raise EvaluationInputError("PLAN_HASH_MISMATCH")
    definitions = definitions if definitions is not None else load_relevance_definitions()
    execution = load_execution(eval_dir, manifest, plan, definitions)
    record, rounds = execution["record"], execution["rounds"]
    sheet_a = load_review_sheet(review_a, manifest, definitions)
    sheet_b = load_review_sheet(review_b, manifest, definitions) if review_b is not None else None
    first = rounds[1]["views"]
    second = rounds[2]["views"] if 2 in rounds else {}
    totals = {f"round_{n}": round_totals(r["views"]) for n, r in sorted(rounds.items())}
    reference = reference_metrics(first, sheet_a)
    repeat = repeat_consistency(first, second, plan["requests"]["repeat_subset_samples"])
    flat = {
        "round_1.valid_return_rate": (totals["round_1"]["valid_return_rate"], totals["round_1"]["planned_pairs"]),
        "round_1.contract_failures": (totals["round_1"]["contract_failures"], totals["round_1"]["planned_pairs"]),
        "reference.unresolved_share_on_determined": (reference["unresolved_share_on_determined"]["rate"], reference["confirmed_determined"]),
        "reference.unconditional_agreement": (reference["unconditional_agreement"]["rate"], reference["confirmed_determined"]),
        "reference.none_on_core": (reference["none_on_core"]["count"], reference["none_on_core"]["n"]),
        "repeat.identical_share_valid_in_both": (repeat["identical_share_valid_in_both"]["rate"], repeat["identical_share_valid_in_both"]["n"]),
    }
    samples = {s["sample_id"]: s for s in manifest["samples"]}
    by_stratum: dict[str, dict[str, int]] = {}
    for sid, sample in samples.items():
        stratum = sample["selection"]["primary_stratum"]
        entry = by_stratum.setdefault(stratum, {"samples": 0, "valid_round_1": 0, "confirmed_determined": 0, "agree": 0})
        entry["samples"] += 1
        entry["valid_round_1"] += int(first[sid]["state"] in VALID_STATES) if sid in first else 0
        row = sheet_a.rows.get(sid)
        if row is not None and row.label is not None and row.outcome == rl.OUTCOME_DETERMINED:
            entry["confirmed_determined"] += 1
            entry["agree"] += int(first.get(sid, {}).get("model_outcome") == row.tier)
    current_tools = ep.code_identity(repo_root or ep.REPO_ROOT)["files"]
    planned_tools = plan["code_identity"]["files"]
    banner = ("SIMULATED REHEARSAL -- every model answer here is TEST DATA, not a model judgment" if record.get("test_data")
              else "LIVE execution -- contains model answers: do not show to a reviewer whose sheet is not final")
    if (plan.get("purpose") or {}).get("kind") == ep.RETEST_PURPOSE_KIND:
        banner = ("DEVELOPMENT-SET RETEST (cases chosen from earlier disagreements, flips and controls; not an independent validation, "
                  "not an acceptance) -- " + banner)
    return {
        "schema": REPORT_SCHEMA,
        "test_data": bool(record.get("test_data")),
        "banner": banner,
        "inputs": {"plan_sha256": plan["plan_sha256"], "sample_manifest_content_sha256": manifest["content_sha256"], "evaluation_id": record.get("evaluation_id"),
                   "task": plan["task"], "purpose": plan.get("purpose"),
                   "execution_status": record.get("status"), "execution_stop": record.get("stop"), "mode": record.get("mode"),
                   "provider": record.get("provider"), "model": record.get("model"), "requests_sent": record.get("requests_sent"),
                   "request_cap": record.get("request_cap"), "review_a": {"path": sheet_a.path, "sha256": sheet_a.sha256, "problems": sheet_a.problems},
                   "review_b": None if sheet_b is None else {"path": sheet_b.path, "sha256": sheet_b.sha256, "problems": sheet_b.problems},
                   "evaluation_code_unchanged_since_plan": {p: current_tools.get(p) == planned_tools.get(p) for p in
                                                            ("comqutor_alpha/alpha_relevance_evaluation.py", "comqutor_alpha/graph_engine/alpha_relevance_judgment.py")}},
        "verification": {f"round_{n}": {"results_present": r["results_present"], "orphan_records": r["orphan_records"], "error": r["error"], "ledger": r["ledger"]}
                         for n, r in sorted(rounds.items())},
        "totals": totals,
        "reference": reference,
        "repeat_consistency": repeat,
        "inter_annotator_agreement": inter_annotator_agreement(sheet_a, sheet_b),
        "by_primary_stratum": dict(sorted(by_stratum.items())),
        "usage": usage_summary(rounds, ep._prices(record.get("provider") or "", record.get("model") or ""), record),  # noqa: SLF001
        "thresholds": apply_thresholds(plan, record, flat),
        "samples": per_sample_rows(manifest, rounds, sheet_a, sheet_b),
    }


def per_sample_rows(manifest: Mapping[str, Any], rounds: Mapping[int, Mapping[str, Any]], sheet_a: ReviewSheet, sheet_b: ReviewSheet | None) -> list[dict[str, Any]]:
    """Every sample of the manifest, whether or not it was sent or reviewed."""
    out = []
    first, second = rounds[1]["views"], (rounds[2]["views"] if 2 in rounds else {})
    for sample in manifest["samples"]:
        sid = sample["sample_id"]
        row = sheet_a.rows.get(sid) or ReviewRow(sid, ROW_MISSING)
        view = first.get(sid) or {}
        repeat_view = second.get(sid)
        agrees = None
        if row.label is not None and view:
            agrees = view["model_outcome"] == row.label
        row_b = sheet_b.rows.get(sid) if sheet_b is not None else None
        out.append({
            "sample_id": sid, "target_alpha_id": sample["target_alpha_id"], "ticker": sample["ticker"],
            "primary_stratum": sample["selection"]["primary_stratum"], "reference_status": row.status, "reference_label": row.label or "",
            "reviewer_b_label": (row_b.label or "") if row_b is not None else "",
            "round_1_outcome": view.get("model_outcome", NOT_SENT), "round_1_reason": view.get("reason") or view.get("unresolved_reason") or "",
            "round_1_anchor_element_ids": ";".join(view.get("anchor_element_ids") or []),
            "agrees_with_reference": "" if agrees is None else ("yes" if agrees else "no"),
            "round_2_outcome": "" if repeat_view is None else repeat_view["model_outcome"],
            "repeat_identical": "" if repeat_view is None or NOT_SENT in (repeat_view["model_outcome"], view.get("model_outcome", NOT_SENT))
            else ("yes" if repeat_view["model_outcome"] == view.get("model_outcome") else "no"),
            "claim_text": sample["claim_text"],
        })
    return out


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _block(b: Mapping[str, Any]) -> str:
    interval = b.get("wilson_95")
    return f"{b['count']}/{b['n']} = {_fmt(b['rate'])}" + (f" (95% Wilson {interval[0]:.3f}–{interval[1]:.3f})" if interval else "")


def render_markdown(report: Mapping[str, Any]) -> str:
    r, inputs = report["reference"], report["inputs"]
    out = [f"# Relevance evaluation report — {inputs['evaluation_id']}", "", f"> **{report['banner']}**", "",
           f"- plan `{inputs['plan_sha256'][:16]}…`, sample manifest `{inputs['sample_manifest_content_sha256'][:16]}…`, mode {inputs['mode']}, "
           f"provider/model {inputs['provider']}/{inputs['model']}",
           f"- task versions (as planned and verified): prompt `{(inputs.get('task') or {}).get('prompt_version')}`, criterion "
           f"`{(inputs.get('task') or {}).get('criterion_version')}`, output `{(inputs.get('task') or {}).get('output_schema_version')}`"
           + (f"; purpose: {inputs['purpose'].get('kind')} — {inputs['purpose'].get('text')}" if inputs.get("purpose") else ""),
           f"- execution {inputs['execution_status']} (stop: {inputs['execution_stop'] or 'none'}), requests sent {inputs['requests_sent']} of cap {inputs['request_cap']}",
           f"- review sheet A `{Path(inputs['review_a']['path']).name}` ({len(inputs['review_a']['problems'])} sheet problems); "
           f"sheet B: {'none' if inputs['review_b'] is None else Path(inputs['review_b']['path']).name}", "",
           "## 1. Every planned pair (no pair is dropped)", "",
           "| round | planned | core | strong | weak | none | UNRESOLVED | FAILED | NOT_SENT | valid-return rate | result coverage | failure rate |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, t in report["totals"].items():
        o = t["outcomes"]
        out.append(f"| {name} | {t['planned_pairs']} | {o['core']} | {o['strong']} | {o['weak']} | {o['none']} | {o['UNRESOLVED']} | {o['FAILED']} | "
                   f"{o['NOT_SENT']} | {_fmt(t['valid_return_rate'])} | {_fmt(t['result_coverage'])} | {_fmt(t['failure_rate'])} |")
    for name, t in report["totals"].items():
        out += ["", f"**{name} FAILED reasons**: {t['failure_reasons'] or 'none'} — categories {t['failure_categories']}",
                f"**{name} UNRESOLVED cases**: " + ("; ".join(f"{c['sample_id']} ({c['unresolved_reason']})" for c in t["unresolved_cases"]) or "none")]
    out += ["", "## 2. Against owner-confirmed reference labels (round 1)", "",
            f"Reference rows (reviewer A): {r['reference_rows']} — only CONFIRMED and consistent rows count; nothing is filled in by the program.", "",
            f"- unconditional agreement on confirmed DETERMINED pairs: {_block(r['unconditional_agreement'])}",
            f"- coverage (model gave a tier): {_block(r['coverage'])}",
            f"- conditional agreement (only where the model gave a tier): {_block(r['conditional_agreement'])}",
            f"- UNRESOLVED on confirmed DETERMINED: {_block(r['unresolved_share_on_determined'])}; FAILED {r['failed_on_determined']}; not sent {r['not_sent_on_determined']}",
            f"- model 'none' on confirmed core: {r['none_on_core']['count']} of {r['none_on_core']['n']}", "",
            "Confusion matrix (rows = reference tier, columns = model outcome):", "",
            "| reference \\ model | " + " | ".join(MODEL_OUTCOMES) + " |", "|---|" + "---|" * len(MODEL_OUTCOMES)]
    for tier, cells in r["confusion_matrix"]["cells"].items():
        out.append(f"| {tier} | " + " | ".join(str(cells[o]) for o in MODEL_OUTCOMES) + " |")
    out += ["", "| tier | reference support | model judged as | agree | recall | precision |", "|---|---|---|---|---|---|"]
    for tier, p in r["per_tier"].items():
        out.append(f"| {tier} | {p['reference_support']} | {p['model_judged_as']} | {p['agree']} | {_fmt(p['recall'])} | {_fmt(p['precision'])} |")
    out += ["", f"core ↔ strong confusions: {[c['sample_id'] + ' ' + c['reference'] + '→' + c['model'] for c in r['core_strong_confusions']] or 'none'}",
            f"wrong 'none': {[c['sample_id'] + ' ' + c['reference'] + '→none' for c in r['wrong_none']] or 'none'}",
            f"confirmed UNRESOLVED pairs: {[c['sample_id'] + ' →' + c['model'] for c in r['on_confirmed_unresolved']] or 'none'}",
            f"model-vs-reference agreement (separate from reviewer agreement): {r['model_vs_reference_agreement']}"]
    rc = report["repeat_consistency"]
    out += ["", "## 3. Repeat consistency (identical requests)", "",
            f"- subset {rc['repeat_subset']}, comparable {rc['comparable']} (not comparable {rc['not_comparable']})",
            f"- identical state+tier, comparable pairs: {_block(rc['identical_share_comparable'])}",
            f"- identical state+tier, pairs valid in both calls: {_block(rc['identical_share_valid_in_both'])}",
            f"- same anchors when the same tier: {rc['same_anchors_when_same_tier']}", f"- flips: {rc['flips'] or 'none'}"]
    out += ["", "## 4. Reviewer agreement (only with two independent sheets)", "", f"{report['inter_annotator_agreement']}"]
    u = report["usage"]
    out += ["", "## 5. Requests, tokens, latency, cost (recorded)", "",
            f"- requests sent {u['requests_sent']}, provider attempts {u['provider_attempts']} (execution log); recorded calls {u['recorded_calls']}, "
            f"provider metadata (request_control + provider_response) on {u['calls_with_provider_metadata']} of them; per-attempt ledger entries "
            f"{u['ledger_attempt_entries']} (that list is written only by the production Week 2 path, not by this task's prebuilt-prompt path; with no "
            f"retry each call is one attempt); retries {u['retries']}, semantic-cache hits {u['semantic_cache_hits']}",
            f"- tokens {u['tokens']} (reasoning share of output {_fmt(u['reasoning_share_of_output'])})",
            f"- latency per call (s) {u['latency_seconds_per_call']}", f"- finish reasons {u['finish_reasons']}; max_tokens {u['max_tokens_values']}; over cap {u['calls_over_max_tokens']}",
            f"- cost (USD) {u['cost_usd']}",
            f"- model names (the request name does not pin the served model): requested {u['model_names']['requested']}; "
            f"returned by the provider {u['model_names']['returned_by_provider']}; calls {u['model_names']['first_call_at']} -> {u['model_names']['last_call_at']}"]
    out += ["", "## 6. By selection stratum (selection metadata, not a label)", "", "| stratum | samples | valid round 1 | confirmed determined | agree |", "|---|---|---|---|---|"]
    for stratum, s in report["by_primary_stratum"].items():
        out.append(f"| {stratum} | {s['samples']} | {s['valid_round_1']} | {s['confirmed_determined']} | {s['agree']} |")
    th = report["thresholds"]
    out += ["", "## 7. Quality thresholds", "", f"Status: **{th['status']}** — {th.get('why', '')}"]
    for t in th.get("results") or []:
        out.append(f"- {t['id']} {t.get('metric')}: value {_fmt(t.get('value'))} (n {t.get('n')}, threshold {t.get('threshold')}) → **{t['verdict']}**")
    out += ["", "The per-sample table (every sample, sent or not, reviewed or not) is in `per_sample.csv`.", ""]
    return "\n".join(out)


__all__ = [
    "NOT_SENT",
    "REPORT_SCHEMA",
    "SAMPLE_TABLE_COLUMNS",
    "EvaluationInputError",
    "ReviewRow",
    "ReviewSheet",
    "apply_thresholds",
    "cohen_kappa",
    "evaluate",
    "inter_annotator_agreement",
    "load_execution",
    "load_review_sheet",
    "per_sample_rows",
    "reference_metrics",
    "render_markdown",
    "repeat_consistency",
    "round_totals",
    "usage_summary",
    "wilson_interval",
]
