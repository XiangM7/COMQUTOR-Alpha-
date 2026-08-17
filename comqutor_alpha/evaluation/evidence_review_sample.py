"""Sprint 2, Track J3: deterministic, stratified 50-Evidence human review
sample exporter.

Reuses existing infrastructure only -- never builds a second run-discovery
mechanism, replay pipeline, or classifier:
  * ``comqutor_alpha.storage.file_store.list_runs`` / ``load_json_record_if_exists``
    for run discovery and artifact loading.
  * ``comqutor_alpha.replay.pipeline.run_structure_replay`` for producing an
    artifact-complete, ticker-consistent bundle per ticker (Architecture
    Replay is offline: zero Provider/LLM/DB calls).
  * ``comqutor_alpha.audit.ticker_consistency`` (via the replay's own
    ``run_audit.json``) for the ticker-consistency gate.
  * the already-computed ``evidence_stance_audit.json`` artifact for every
    candidate row -- never a second classification pass.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.replay.pipeline import run_structure_replay
from comqutor_alpha.storage.file_store import (
    list_runs,
    load_json_record_if_exists,
    run_dir_for,
    validate_run_id_for_path,
)

SAMPLING_VERSION = "evidence_review_sample.v1"
DEFAULT_TICKERS = ("NVDA", "QQQ", "MSFT", "SNDK", "TSM", "AMD")
DEFAULT_TOTAL_COUNT = 50
MIN_PER_TICKER = 6
MAX_PER_TICKER = 10

# Section 20: target stratified distribution across the five stances.
REQUESTED_STANCE_QUOTAS = {
    "supports_alpha": 18,
    "opposes_alpha": 10,
    "mentions_alpha": 8,
    "neutral_background": 8,
    "supports_counter_alpha": 6,
}

_STANCE_ORDER = tuple(REQUESTED_STANCE_QUOTAS)

_NEGATION_REBUTTAL_REASON_CODES = {
    "EXPLICIT_REBUTTAL_OF_TARGET_ALPHA",
    "EXPLICIT_NEGATION_OF_TARGET_ALPHA",
    "INVALIDATION_OF_OPPORTUNITY_ALPHA",
    "ALREADY_PRICED_IN_OPPOSES_UPSIDE_ALPHA",
    "WEAKENS_TARGET_CAUSAL_CHAIN",
    "RISK_RELIEF_OPPOSES_RISK_ALPHA",
}
_CONDITIONAL_MIXED_REASON_CODES = {
    "CONDITIONAL_SUPPORT",
    "CONDITIONAL_OPPOSITION",
    "MIXED_STANCE_UNRESOLVED",
}

# Section 21 item 8 -- John's own fixed A304 rebuttal example ("a lazy
# heuristic that ignores the actual numbers").
_JOHNS_EXAMPLE_REASON_CODE = "EXPLICIT_REBUTTAL_OF_TARGET_ALPHA"
_JOHNS_EXAMPLE_TARGET_ALPHA = "A304"

CSV_FIELDNAMES = [
    "sample_id",
    "sampling_version",
    "run_id",
    "source_run_id",
    "replay_run_id",
    "ticker",
    "analysis_date",
    "claim_id",
    "source_agent_output_id",
    "agent",
    "claim",
    "evidence",
    "target_alpha_id",
    "target_alpha_name",
    "matched_alpha_id",
    "matched_alpha_name",
    "match_status",
    "match_score",
    "relation",
    "direction",
    "assertion_status",
    "semantic_polarity",
    "claim_quality",
    "ticker_specific",
    "evidence_stance",
    "counter_alpha_id",
    "stance_reason_codes",
    "stance_confidence_band",
    "requires_manual_review",
    "evidence_fact_group_ids",
    "fact_group_member_count",
    "duplicate_or_paraphrase_member",
    "used_in_activation",
    "activation_score",
    "used_in_conflict",
    "conflict_ids",
    "conflict_side",
    "reviewer_expected_stance",
    "reviewer_counter_alpha_id",
    "reviewer_should_be_admissible",
    "reviewer_confidence",
    "reviewer_notes",
    "review_status",
]

REVIEWER_BLANK_FIELDNAMES = (
    "reviewer_expected_stance",
    "reviewer_counter_alpha_id",
    "reviewer_should_be_admissible",
    "reviewer_confidence",
    "reviewer_notes",
)


@dataclass
class TickerSelection:
    ticker: str
    status: str  # "selected" | "skipped"
    source_run_id: str | None = None
    replay_run_id: str | None = None
    analysis_date: str | None = None
    reason_codes: list[str] = field(default_factory=list)
    source_artifact_hashes: dict[str, str] = field(default_factory=dict)


@dataclass
class ReviewSampleResult:
    requested_count: int
    actual_count: int
    sampling_version: str
    classifier_version: str
    rows: list[dict[str, Any]]
    ticker_selections: list[TickerSelection]
    requested_quotas: dict[str, int]
    actual_quotas: dict[str, int]
    quota_shortfalls: dict[str, int]
    ticker_distribution: dict[str, int]
    stance_distribution: dict[str, int]
    manual_review_count: int
    activation_evidence_count: int
    conflict_evidence_count: int
    negation_rebuttal_count: int
    conditional_mixed_count: int
    non_ticker_specific_count: int
    duplicate_paraphrase_count: int
    johns_example_included: bool
    verdict: str  # "PASS" | "PARTIAL"


def _stable_hash(*, ticker: str, run_id: str, claim_id: str, target_alpha_id: str) -> str:
    payload = f"{SAMPLING_VERSION}|{ticker}|{run_id}|{claim_id}|{target_alpha_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _candidate_source_run_ids(ticker: str, source_output_root: str | Path) -> list[str]:
    """Every locally available source run for ``ticker``, most-recent
    first (by analysis_date, then created_at, then run_id -- all stable,
    deterministic tie-breaks). Reuses list_runs -- never a second
    run-discovery mechanism."""
    candidates: list[tuple[str, str, str]] = []
    for run_id in list_runs(source_output_root):
        metadata = load_json_record_if_exists(run_id, "metadata.json", output_root=source_output_root)
        if str(metadata.get("ticker") or "").strip().upper() != ticker.upper():
            continue
        if not (run_dir_for(run_id, source_output_root) / "raw_agent_outputs.json").exists():
            continue
        analysis_date = str(metadata.get("analysis_date") or "")
        created_at = str(metadata.get("created_at") or "")
        candidates.append((analysis_date, created_at, run_id))
    candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return [run_id for _, _, run_id in candidates]


def _select_ticker_bundle(
    ticker: str, *, source_output_root: str | Path, replay_output_root: str | Path
) -> TickerSelection:
    """Deterministically pick, and (idempotently) replay, the most recent
    artifact-complete, ticker-consistent source run for ``ticker``. Reruns
    of the exporter reuse an already-produced replay bundle rather than
    re-replaying (bounded, deterministic, zero repeated Provider/LLM
    calls)."""
    for source_run_id in _candidate_source_run_ids(ticker, source_output_root):
        replay_run_id = validate_run_id_for_path(f"review-sample-{source_run_id}")
        replay_dir = run_dir_for(replay_run_id, replay_output_root)
        metadata = None
        if replay_dir.exists() and any(replay_dir.iterdir()):
            metadata = load_json_record_if_exists(replay_run_id, "metadata.json", output_root=replay_output_root)
        else:
            try:
                result = run_structure_replay(
                    source_run_id,
                    source_output_root=str(source_output_root),
                    replay_output_root=str(replay_output_root),
                    replay_run_id=replay_run_id,
                    persist=True,
                    comparison=False,
                )
            except FileExistsError:
                metadata = load_json_record_if_exists(replay_run_id, "metadata.json", output_root=replay_output_root)
            else:
                if result.status != "completed":
                    continue
                metadata = load_json_record_if_exists(replay_run_id, "metadata.json", output_root=replay_output_root)

        if not metadata:
            continue
        manifest = load_json_record_if_exists(replay_run_id, "artifact_manifest.json", output_root=replay_output_root)
        run_audit = load_json_record_if_exists(replay_run_id, "run_audit.json", output_root=replay_output_root)
        artifact_complete = manifest.get("artifact_completeness") == "pass"
        ticker_consistent = run_audit.get("ticker_consistency") in ("pass", None)
        if not (artifact_complete and ticker_consistent):
            continue

        raw_path = run_dir_for(source_run_id, source_output_root) / "raw_agent_outputs.json"
        source_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest() if raw_path.exists() else None
        return TickerSelection(
            ticker=ticker,
            status="selected",
            source_run_id=source_run_id,
            replay_run_id=replay_run_id,
            analysis_date=(
                metadata.get("analysis_date")
                or metadata.get("source_trade_date")
                or metadata.get("source_analysis_date")
            ),
            source_artifact_hashes={"raw_agent_outputs.json": source_hash} if source_hash else {},
        )

    return TickerSelection(ticker=ticker, status="skipped", reason_codes=["NO_ELIGIBLE_SOURCE_RUN"])


def _candidate_pool_for_ticker(selection: TickerSelection, *, replay_output_root: str | Path, taxonomy) -> list[dict[str, Any]]:
    if selection.status != "selected":
        return []
    replay_run_id = selection.replay_run_id
    stance_audit = load_json_record_if_exists(replay_run_id, "evidence_stance_audit.json", output_root=replay_output_root)
    records = stance_audit.get("records")
    if not isinstance(records, list) or not records:
        return []

    evidence_facts = load_json_record_if_exists(replay_run_id, "evidence_facts.json", output_root=replay_output_root)
    group_member_counts: dict[str, int] = {}
    group_representative: dict[str, str] = {}
    for group in evidence_facts.get("groups") or []:
        group_id = group.get("evidence_fact_group_id")
        if not group_id:
            continue
        group_member_counts[group_id] = len(group.get("member_claim_ids") or [])
        group_representative[group_id] = group.get("representative_claim_id")

    graph = load_json_record_if_exists(replay_run_id, "structure_graph.json", output_root=replay_output_root)
    activation_alphas = ((graph.get("activation") or {}).get("alphas")) or []
    activation_score_by_alpha = {
        a.get("alpha_id"): a.get("activation_score") for a in activation_alphas if isinstance(a, dict)
    }

    conflicts_payload = load_json_record_if_exists(replay_run_id, "conflicts.json", output_root=replay_output_root)
    conflicts = conflicts_payload.get("conflicts") or []

    def _conflict_hits(target_alpha_id: str, group_ids: list[str]) -> tuple[list[str], str | None]:
        matched_ids: list[str] = []
        sides: set[str] = set()
        for conflict in conflicts:
            if not isinstance(conflict, dict):
                continue
            if conflict.get("bull_alpha_id") == target_alpha_id and set(group_ids) & set(
                conflict.get("bull_fact_group_ids") or []
            ):
                matched_ids.append(conflict.get("conflict_id"))
                sides.add("bull")
            if conflict.get("bear_alpha_id") == target_alpha_id and set(group_ids) & set(
                conflict.get("bear_fact_group_ids") or []
            ):
                matched_ids.append(conflict.get("conflict_id"))
                sides.add("bear")
        side = "bull" if sides == {"bull"} else "bear" if sides == {"bear"} else ("mixed" if sides else None)
        return matched_ids, side

    pool: list[dict[str, Any]] = []
    for record in records:
        target_alpha_id = record.get("target_alpha_id")
        if record.get("evidence_stance") not in REQUESTED_STANCE_QUOTAS:
            continue
        group_ids = record.get("evidence_fact_group_ids") or []
        primary_group_id = group_ids[0] if group_ids else None
        member_count = group_member_counts.get(primary_group_id, 0) if primary_group_id else 0
        representative_claim_id = group_representative.get(primary_group_id) if primary_group_id else None
        duplicate_or_paraphrase_member = bool(
            primary_group_id and member_count > 1 and representative_claim_id != record.get("claim_id")
        )
        conflict_ids, conflict_side = _conflict_hits(target_alpha_id, group_ids)
        target_alpha = taxonomy.get(target_alpha_id)
        matched_alpha = taxonomy.get(record.get("matched_alpha_id"))

        row = {
            **record,
            "source_run_id": selection.source_run_id,
            "replay_run_id": selection.replay_run_id,
            "analysis_date": selection.analysis_date,
            "target_alpha_name": target_alpha.name_en if target_alpha else None,
            "matched_alpha_name": matched_alpha.name_en if matched_alpha else None,
            "fact_group_member_count": member_count,
            "duplicate_or_paraphrase_member": duplicate_or_paraphrase_member,
            "activation_score": activation_score_by_alpha.get(target_alpha_id),
            "conflict_ids": conflict_ids,
            "conflict_side": conflict_side,
        }
        row["_key"] = (selection.ticker, replay_run_id, record.get("claim_id"), target_alpha_id)
        row["_hash"] = _stable_hash(
            ticker=selection.ticker,
            run_id=replay_run_id,
            claim_id=str(record.get("claim_id")),
            target_alpha_id=str(target_alpha_id),
        )
        row["_priority_tier"] = (
            0 if not record.get("requires_manual_review") else -1,
        )
        pool.append(row)
    return pool


def build_evidence_review_sample(
    *,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    count: int = DEFAULT_TOTAL_COUNT,
    source_output_root: str | Path = "outputs/runs",
    replay_output_root: str | Path = "outputs/review_sample_replays",
) -> ReviewSampleResult:
    taxonomy = load_alpha_taxonomy()
    selections = [
        _select_ticker_bundle(ticker, source_output_root=source_output_root, replay_output_root=replay_output_root)
        for ticker in tickers
    ]

    pool: list[dict[str, Any]] = []
    for selection in selections:
        pool.extend(_candidate_pool_for_ticker(selection, replay_output_root=replay_output_root, taxonomy=taxonomy))

    selected: list[dict[str, Any]] = []
    selected_keys: set[tuple] = set()
    ticker_counts: dict[str, int] = dict.fromkeys(tickers, 0)
    actual_quotas: dict[str, int] = dict.fromkeys(_STANCE_ORDER, 0)

    def _try_add(row: dict[str, Any]) -> bool:
        if row["_key"] in selected_keys:
            return False
        if ticker_counts[row["_key"][0]] >= MAX_PER_TICKER:
            return False
        if len(selected) >= count:
            return False
        selected.append(row)
        selected_keys.add(row["_key"])
        ticker_counts[row["_key"][0]] += 1
        actual_quotas[row["evidence_stance"]] += 1
        return True

    # Single unified greedy loop, re-evaluated after every pick: at each
    # step, the highest-priority still-available candidate is added, where
    # priority weighs (in order) John's fixed example, whether its ticker
    # is still below MIN_PER_TICKER, whether its stance is still below its
    # requested quota (larger shortfall first), then the section 20
    # backfill order (manual review > conflict > activation > match
    # score), spreading remaining picks across tickers, with the stable
    # hash as the final deterministic tie-break. A single combined
    # priority (rather than separate ticker-floor/stance-quota phases)
    # avoids one phase exhausting the whole `count` budget before the
    # other constraint gets a chance to run.
    def _combined_key(row: dict[str, Any]) -> tuple:
        ticker = row["_key"][0]
        is_johns_example = (
            row.get("target_alpha_id") == _JOHNS_EXAMPLE_TARGET_ALPHA
            and _JOHNS_EXAMPLE_REASON_CODE in (row.get("stance_reason_codes") or [])
        )
        below_floor = ticker_counts[ticker] < MIN_PER_TICKER
        stance = row["evidence_stance"]
        shortfall = REQUESTED_STANCE_QUOTAS[stance] - actual_quotas[stance]
        return (
            0 if is_johns_example else 1,
            0 if below_floor else 1,
            0 if shortfall > 0 else 1,
            -shortfall,
            0 if row.get("requires_manual_review") else 1,
            0 if row.get("used_in_conflict") else 1,
            0 if row.get("used_in_activation") else 1,
            -(row.get("match_score") or 0.0),
            ticker_counts[ticker],
            row["_hash"],
        )

    while len(selected) < count:
        candidates = [
            row
            for row in pool
            if row["_key"] not in selected_keys and ticker_counts[row["_key"][0]] < MAX_PER_TICKER
        ]
        if not candidates:
            break
        candidates.sort(key=_combined_key)
        _try_add(candidates[0])

    selected.sort(key=lambda r: r["_hash"])

    rows: list[dict[str, Any]] = []
    for index, row in enumerate(selected, start=1):
        sample_id = f"evrs-{index:03d}"
        rows.append(
            {
                "sample_id": sample_id,
                "sampling_version": SAMPLING_VERSION,
                "run_id": row["replay_run_id"],
                "source_run_id": row["source_run_id"],
                "replay_run_id": row["replay_run_id"],
                "ticker": row["ticker"],
                "analysis_date": row.get("analysis_date"),
                "claim_id": row.get("claim_id"),
                "source_agent_output_id": row.get("source_agent_output_id"),
                "agent": row.get("agent"),
                "claim": row.get("claim"),
                "evidence": row.get("evidence"),
                "target_alpha_id": row.get("target_alpha_id"),
                "target_alpha_name": row.get("target_alpha_name"),
                "matched_alpha_id": row.get("matched_alpha_id"),
                "matched_alpha_name": row.get("matched_alpha_name"),
                "match_status": row.get("match_status"),
                "match_score": row.get("match_score"),
                "relation": row.get("relation"),
                "direction": row.get("direction"),
                "assertion_status": row.get("assertion_status"),
                "semantic_polarity": row.get("semantic_polarity"),
                "claim_quality": row.get("claim_quality"),
                "ticker_specific": row.get("ticker_specific"),
                "evidence_stance": row.get("evidence_stance"),
                "counter_alpha_id": row.get("counter_alpha_id"),
                "stance_reason_codes": row.get("stance_reason_codes"),
                "stance_confidence_band": row.get("stance_confidence_band"),
                "requires_manual_review": row.get("requires_manual_review"),
                "evidence_fact_group_ids": row.get("evidence_fact_group_ids"),
                "fact_group_member_count": row.get("fact_group_member_count"),
                "duplicate_or_paraphrase_member": row.get("duplicate_or_paraphrase_member"),
                "used_in_activation": row.get("used_in_activation"),
                "activation_score": row.get("activation_score"),
                "used_in_conflict": row.get("used_in_conflict"),
                "conflict_ids": row.get("conflict_ids"),
                "conflict_side": row.get("conflict_side"),
                "reviewer_expected_stance": "",
                "reviewer_counter_alpha_id": "",
                "reviewer_should_be_admissible": "",
                "reviewer_confidence": "",
                "reviewer_notes": "",
                "review_status": "pending",
            }
        )

    ticker_distribution = dict.fromkeys(tickers, 0)
    stance_distribution = dict.fromkeys(_STANCE_ORDER, 0)
    manual_review_count = 0
    activation_evidence_count = 0
    conflict_evidence_count = 0
    negation_rebuttal_count = 0
    conditional_mixed_count = 0
    non_ticker_specific_count = 0
    duplicate_paraphrase_count = 0
    johns_example_included = False
    for r in rows:
        ticker_distribution[r["ticker"]] = ticker_distribution.get(r["ticker"], 0) + 1
        stance_distribution[r["evidence_stance"]] = stance_distribution.get(r["evidence_stance"], 0) + 1
        reason_codes = set(r.get("stance_reason_codes") or [])
        if r["requires_manual_review"]:
            manual_review_count += 1
        if r["used_in_activation"]:
            activation_evidence_count += 1
        if r["used_in_conflict"]:
            conflict_evidence_count += 1
        if reason_codes & _NEGATION_REBUTTAL_REASON_CODES:
            negation_rebuttal_count += 1
        if reason_codes & _CONDITIONAL_MIXED_REASON_CODES:
            conditional_mixed_count += 1
        if not r.get("ticker_specific"):
            non_ticker_specific_count += 1
        if r.get("duplicate_or_paraphrase_member"):
            duplicate_paraphrase_count += 1
        if (
            r.get("target_alpha_id") == _JOHNS_EXAMPLE_TARGET_ALPHA
            and _JOHNS_EXAMPLE_REASON_CODE in reason_codes
        ):
            johns_example_included = True

    quota_shortfalls = {
        stance: max(0, REQUESTED_STANCE_QUOTAS[stance] - actual_quotas[stance]) for stance in _STANCE_ORDER
    }
    verdict = "PASS" if len(rows) == count else "PARTIAL"

    return ReviewSampleResult(
        requested_count=count,
        actual_count=len(rows),
        sampling_version=SAMPLING_VERSION,
        classifier_version=_classifier_version(),
        rows=rows,
        ticker_selections=selections,
        requested_quotas=dict(REQUESTED_STANCE_QUOTAS),
        actual_quotas=actual_quotas,
        quota_shortfalls=quota_shortfalls,
        ticker_distribution=ticker_distribution,
        stance_distribution=stance_distribution,
        manual_review_count=manual_review_count,
        activation_evidence_count=activation_evidence_count,
        conflict_evidence_count=conflict_evidence_count,
        negation_rebuttal_count=negation_rebuttal_count,
        conditional_mixed_count=conditional_mixed_count,
        non_ticker_specific_count=non_ticker_specific_count,
        duplicate_paraphrase_count=duplicate_paraphrase_count,
        johns_example_included=johns_example_included,
        verdict=verdict,
    )


def _classifier_version() -> str:
    from comqutor_alpha.structure_engine.evidence_stance import CLASSIFIER_VERSION

    return CLASSIFIER_VERSION


# ---------------------------------------------------------------------------
# CSV / manifest / records-JSON output (section 23-25)
# ---------------------------------------------------------------------------

_FORMULA_INJECTION_PREFIXES = ("=", "+", "-", "@")


def _csv_safe_cell(value: Any) -> Any:
    """RFC 4180-safe scalar for one CSV cell -- csv.writer already handles
    quoting/escaping/multiline text; this only guards against formula
    injection (a leading =/+/-/@ interpreted as a formula by Excel/Sheets)
    by prefixing with a single quote. Lists/dicts are stringified as
    pipe-joined text (readable in a spreadsheet) or JSON, never truncated.
    The ORIGINAL, un-prefixed value is preserved verbatim in the JSON
    companion artifact -- this function only affects the .csv file."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    text = "|".join(str(item) for item in value) if isinstance(value, (list, tuple)) else str(value)
    if text.startswith(_FORMULA_INJECTION_PREFIXES):
        return "'" + text
    return text


def write_evidence_review_sample_csv(result: ReviewSampleResult, csv_path: str | Path) -> str:
    """Writes the RFC 4180 CSV (UTF-8, csv.writer's own multiline/quote
    handling) and returns its sha256. Deterministic: two calls against the
    same ``result.rows`` produce byte-identical output (row order is
    already fixed by the stable per-row hash before this function runs)."""
    import csv
    import io

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDNAMES, lineterminator="\r\n")
    writer.writeheader()
    for row in result.rows:
        writer.writerow({key: _csv_safe_cell(row.get(key)) for key in CSV_FIELDNAMES})
    raw_bytes = buffer.getvalue().encode("utf-8")
    Path(csv_path).write_bytes(raw_bytes)
    return hashlib.sha256(raw_bytes).hexdigest()


def write_evidence_review_sample_records_json(result: ReviewSampleResult, records_path: str | Path) -> None:
    """The exact, un-escaped original claim/evidence text and every field,
    as a JSON companion to the CSV -- so formula-injection quoting in the
    .csv never loses or alters the source text."""
    import json

    payload = {
        "schema_version": "evidence_review_sample_records.v1",
        "sampling_version": result.sampling_version,
        "classifier_version": result.classifier_version,
        "count": result.actual_count,
        "records": result.rows,
    }
    Path(records_path).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_evidence_review_sample_manifest(
    result: ReviewSampleResult,
    manifest_path: str | Path,
    *,
    csv_sha256: str,
    generated_at: str,
) -> None:
    import json

    source_runs = []
    artifact_hashes: dict[str, str] = {}
    for selection in result.ticker_selections:
        source_runs.append(
            {
                "ticker": selection.ticker,
                "status": selection.status,
                "source_run_id": selection.source_run_id,
                "replay_run_id": selection.replay_run_id,
                "analysis_date": selection.analysis_date,
                "reason_codes": selection.reason_codes,
            }
        )
        for name, digest in selection.source_artifact_hashes.items():
            artifact_hashes[f"{selection.ticker}:{name}"] = digest

    payload = {
        "schema_version": "evidence_review_sample_manifest.v1",
        "sampling_version": result.sampling_version,
        "classifier_version": result.classifier_version,
        "requested_count": result.requested_count,
        "actual_count": result.actual_count,
        "verdict": result.verdict,
        "ticker_distribution": result.ticker_distribution,
        "stance_distribution": result.stance_distribution,
        "requested_quotas": result.requested_quotas,
        "actual_quotas": result.actual_quotas,
        "quota_shortfalls": result.quota_shortfalls,
        "manual_review_count": result.manual_review_count,
        "activation_evidence_count": result.activation_evidence_count,
        "conflict_evidence_count": result.conflict_evidence_count,
        # Section 21 coverage targets -- informational, not gating.
        "negation_rebuttal_count": result.negation_rebuttal_count,
        "conditional_mixed_count": result.conditional_mixed_count,
        "non_ticker_specific_count": result.non_ticker_specific_count,
        "duplicate_paraphrase_count": result.duplicate_paraphrase_count,
        "johns_example_included": result.johns_example_included,
        "source_runs": source_runs,
        "artifact_hashes": artifact_hashes,
        "csv_sha256": csv_sha256,
        "generated_at": generated_at,
    }
    Path(manifest_path).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


__all__ = [
    "SAMPLING_VERSION",
    "DEFAULT_TICKERS",
    "DEFAULT_TOTAL_COUNT",
    "MIN_PER_TICKER",
    "MAX_PER_TICKER",
    "REQUESTED_STANCE_QUOTAS",
    "CSV_FIELDNAMES",
    "REVIEWER_BLANK_FIELDNAMES",
    "TickerSelection",
    "ReviewSampleResult",
    "build_evidence_review_sample",
]
