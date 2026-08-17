"""Provider-zero Phase 1 human-review packet construction.

This module reads already-persisted accepted Shadow artifacts and renders a
self-contained, one-row-per-claim review CSV plus a local HTML view.  It has
no Provider, gateway, cache, network, Redis, or database dependencies.
"""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import os
import re
import uuid
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PACKET_SCHEMA_VERSION = "comqutor.phase1.human_review_packet.v2"
VERIFICATION_SCHEMA_VERSION = "comqutor.phase1.human_review_packet_verification.v1"
PROVENANCE_FAILURE = "HUMAN_REVIEW_PACKET_PROVENANCE_FAILURE"
COVERAGE_FAILURE = "HUMAN_REVIEW_PACKET_COVERAGE_FAILURE"

EXPECTED_TICKERS = ("NVDA", "QQQ", "MSFT", "SNDK", "TSM", "AMD")
EXPECTED_DIRECTORY_FAMILIES = ("fundamental", "news", "sentiment", "technical")
EXPECTED_AGENTS = (
    "fundamental_agent",
    "news_agent",
    "sentiment_agent",
    "market_agent",
)

REVIEW_FIELDS = (
    "semantic_fidelity",
    "claim_boundary",
    "evidence_correctness",
    "entity_correctness",
    "factor_correctness",
    "direction_correctness",
    "critical_error_type",
    "overall_disposition",
    "severity",
    "reviewer",
    "review_timestamp",
    "notes",
)

CSV_FIELDS = (
    "review_row_id",
    "ticker",
    "agent",
    "report_family",
    "claim_ordinal",
    "source_run_id",
    "evaluation_run_id",
    "agent_output_id",
    "source_report_sha256",
    "shadow_claim_id",
    "legacy_record_id",
    "claim_text",
    "shadow_evidence_text",
    "source_span_start",
    "source_span_end",
    "source_evidence_text",
    "source_spans",
    "source_context_before",
    "source_context_after",
    "entities",
    "factors",
    "direction",
    "confidence",
    "legacy_claim_text",
    "legacy_evidence_text",
    *REVIEW_FIELDS,
)

ALLOWED_REVIEW_VALUES = {
    "semantic_fidelity": ("PASS", "MINOR", "FAIL"),
    "claim_boundary": ("PASS", "MINOR", "FAIL"),
    "evidence_correctness": ("PASS", "PARTIAL", "FAIL"),
    "entity_correctness": ("PASS", "MINOR", "FAIL", "NA"),
    "factor_correctness": ("PASS", "MINOR", "FAIL", "NA"),
    "direction_correctness": ("PASS", "MINOR", "FAIL", "NA"),
    "critical_error_type": (
        "NONE",
        "NEGATION_REVERSAL",
        "ATTRIBUTION_LOSS",
        "FABRICATED_CLAIM",
        "FABRICATED_EVIDENCE",
        "IDENTITY_ERROR",
        "OTHER",
    ),
    "overall_disposition": ("ACCEPT", "ACCEPT_WITH_MINOR_ISSUE", "REJECT"),
    "severity": ("NONE", "MINOR", "MAJOR", "CRITICAL"),
}

_SECRET_PATTERNS = (
    re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"authorization\s*:\s*(?:bearer|basic)\s+\S+", re.IGNORECASE),
    re.compile(r"ANTHROPIC_API_KEY\s*=\s*\S+", re.IGNORECASE),
)


class HumanReviewPacketError(RuntimeError):
    """Fail-closed packet construction error with a stable reason code."""

    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(f"{reason_code}: {detail}")
        self.reason_code = reason_code
        self.detail = detail


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HumanReviewPacketError(
            PROVENANCE_FAILURE,
            f"unreadable_json:{path}:{type(exc).__name__}",
        ) from exc


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _json_cell(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _legacy_id(record: Mapping[str, Any], index: int) -> str:
    for key in ("claim_id", "record_id", "agent_output_id"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    material = f"{index}\n{record.get('claim', '')}\n{record.get('evidence', '')}"
    return f"legacy-navigation-{hashlib.sha256(material.encode()).hexdigest()[:20]}"


def _unambiguous_legacy_matches(
    comparison: Mapping[str, Any],
    legacy_records: Sequence[Mapping[str, Any]],
    shadow_claim_ids: set[str],
) -> dict[str, Mapping[str, Any]]:
    legacy_by_id = {
        _legacy_id(record, index): record for index, record in enumerate(legacy_records)
    }
    shadow_to_legacy: dict[str, set[str]] = defaultdict(set)
    legacy_to_shadow: dict[str, set[str]] = defaultdict(set)
    for overlap in comparison.get("exact_text_overlaps") or []:
        if not isinstance(overlap, Mapping):
            continue
        legacy_id = str(overlap.get("legacy_record_id") or "")
        shadow_id = str(overlap.get("shadow_claim_id") or "")
        if legacy_id not in legacy_by_id or shadow_id not in shadow_claim_ids:
            continue
        shadow_to_legacy[shadow_id].add(legacy_id)
        legacy_to_shadow[legacy_id].add(shadow_id)

    matches: dict[str, Mapping[str, Any]] = {}
    for shadow_id, legacy_ids in shadow_to_legacy.items():
        if len(legacy_ids) != 1:
            continue
        legacy_id = next(iter(legacy_ids))
        if len(legacy_to_shadow[legacy_id]) == 1:
            matches[shadow_id] = legacy_by_id[legacy_id]
    return matches


def _span_text(spans: Sequence[Mapping[str, Any]]) -> str:
    if len(spans) == 1:
        return str(spans[0]["exact_quote"])
    return "\n\n".join(
        f"[SPAN {index} {span['start']}:{span['end']}]\n{span['exact_quote']}"
        for index, span in enumerate(spans, start=1)
    )


def _span_context(
    report_text: str,
    spans: Sequence[Mapping[str, Any]],
    *,
    context_chars: int,
    before: bool,
) -> str:
    excerpts: list[str] = []
    for index, span in enumerate(spans, start=1):
        start = int(span["start"])
        end = int(span["end"])
        excerpt = (
            report_text[max(0, start - context_chars) : start]
            if before
            else report_text[end : min(len(report_text), end + context_chars)]
        )
        if len(spans) == 1:
            return excerpt
        excerpts.append(f"[SPAN {index} {start}:{end}]\n{excerpt}")
    return "\n\n".join(excerpts)


def _validate_spans(
    *,
    report_text: str,
    spans: Any,
    report_dir: Path,
    shadow_claim_id: str,
) -> list[dict[str, Any]]:
    if not isinstance(spans, list) or not spans:
        raise HumanReviewPacketError(
            PROVENANCE_FAILURE,
            f"missing_source_spans:{report_dir}:{shadow_claim_id}",
        )
    validated: list[dict[str, Any]] = []
    for index, raw_span in enumerate(spans):
        if not isinstance(raw_span, Mapping):
            raise HumanReviewPacketError(
                PROVENANCE_FAILURE,
                f"invalid_source_span:{report_dir}:{shadow_claim_id}:{index}",
            )
        start = raw_span.get("start")
        end = raw_span.get("end")
        exact_quote = raw_span.get("exact_quote")
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or not isinstance(exact_quote, str)
            or start < 0
            or end <= start
            or end > len(report_text)
            or report_text[start:end] != exact_quote
        ):
            raise HumanReviewPacketError(
                PROVENANCE_FAILURE,
                f"source_span_mismatch:{report_dir}:{shadow_claim_id}:{index}:{start}:{end}",
            )
        validated.append({"start": start, "end": end, "exact_quote": exact_quote})
    return validated


def _canonical_input_paths(report_dirs: Sequence[Path]) -> list[Path]:
    names = (
        "shadow_bundle.json",
        "source_report_snapshot.json",
        "report_result.json",
        "validation_report.json",
        "legacy_claims_snapshot.json",
        "legacy_vs_shadow_comparison.json",
    )
    return [report_dir / name for report_dir in report_dirs for name in names]


def _combined_file_hash(paths: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def collect_review_rows(
    evaluation_dir: Path,
    *,
    context_chars: int = 350,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Collect and validate exactly one self-contained row per accepted Claim."""

    if not 250 <= context_chars <= 500:
        raise ValueError("context_chars must be between 250 and 500")

    metadata = _read_json(evaluation_dir / "evaluation_metadata.json")
    if (
        not isinstance(metadata, Mapping)
        or metadata.get("prompt_version")
        != "structured_adapter.claim_extraction_shadow.v2"
        or not isinstance(metadata.get("prompt_sha256"), str)
        or not metadata.get("prompt_sha256")
    ):
        raise HumanReviewPacketError(
            PROVENANCE_FAILURE,
            "evaluation_metadata_prompt_v2_identity_invalid",
        )

    report_dirs = sorted(
        (path.parent for path in evaluation_dir.glob("reports/*/*/shadow_bundle.json")),
        key=lambda path: (
            EXPECTED_TICKERS.index(path.parent.name)
            if path.parent.name in EXPECTED_TICKERS
            else len(EXPECTED_TICKERS),
            EXPECTED_DIRECTORY_FAMILIES.index(path.name)
            if path.name in EXPECTED_DIRECTORY_FAMILIES
            else len(EXPECTED_DIRECTORY_FAMILIES),
        ),
    )
    expected_keys = {
        (ticker, family)
        for ticker in EXPECTED_TICKERS
        for family in EXPECTED_DIRECTORY_FAMILIES
    }
    actual_keys = {
        (report_dir.parent.name, report_dir.name) for report_dir in report_dirs
    }
    if actual_keys != expected_keys or len(report_dirs) != 24:
        missing = sorted(expected_keys - actual_keys)
        unexpected = sorted(actual_keys - expected_keys)
        raise HumanReviewPacketError(
            COVERAGE_FAILURE,
            f"report_coverage:count={len(report_dirs)}:missing={missing}:unexpected={unexpected}",
        )

    rows: list[dict[str, str]] = []
    seen_claim_ids: set[str] = set()
    reports_seen: set[tuple[str, str]] = set()
    claims_by_ticker: Counter[str] = Counter()
    claims_by_agent: Counter[str] = Counter()
    total_spans = 0
    multi_span_claims = 0
    claims_with_factors = 0
    claims_with_direction = 0
    claims_with_non_unknown_direction = 0
    unambiguous_legacy_matches = 0

    for report_dir in report_dirs:
        required_paths = _canonical_input_paths([report_dir])
        missing_paths = [str(path) for path in required_paths if not path.is_file()]
        if missing_paths:
            raise HumanReviewPacketError(
                PROVENANCE_FAILURE,
                f"missing_canonical_artifacts:{missing_paths}",
            )

        bundle = _read_json(report_dir / "shadow_bundle.json")
        source = _read_json(report_dir / "source_report_snapshot.json")
        report_result = _read_json(report_dir / "report_result.json")
        validation = _read_json(report_dir / "validation_report.json")
        legacy_records = _read_json(report_dir / "legacy_claims_snapshot.json")
        comparison = _read_json(report_dir / "legacy_vs_shadow_comparison.json")
        if not all(
            isinstance(item, Mapping)
            for item in (bundle, source, report_result, validation, comparison)
        ) or not isinstance(legacy_records, list):
            raise HumanReviewPacketError(
                PROVENANCE_FAILURE,
                f"canonical_artifact_shape:{report_dir}",
            )

        ticker = str(bundle.get("ticker") or "")
        agent = str(bundle.get("agent") or "")
        family = report_dir.name
        if ticker != report_dir.parent.name or agent not in EXPECTED_AGENTS:
            raise HumanReviewPacketError(
                PROVENANCE_FAILURE,
                f"report_identity_mismatch:{report_dir}:{ticker}:{agent}",
            )
        if (
            report_result.get("provider_status") != "success"
            or report_result.get("validation_status") != "accepted"
            or report_result.get("shadow_status") != "accepted"
            or report_result.get("validation_accepted") is not True
            or validation.get("status") != "accepted"
            or validation.get("valid") is not True
        ):
            raise HumanReviewPacketError(
                PROVENANCE_FAILURE,
                f"report_not_accepted:{report_dir}",
            )

        report_text = source.get("report_text")
        if not isinstance(report_text, str):
            raise HumanReviewPacketError(
                PROVENANCE_FAILURE,
                f"source_report_not_text:{report_dir}",
            )
        report_sha256 = _sha256_bytes(report_text.encode("utf-8"))
        identity_values = {
            str(bundle.get("source_report_sha256") or ""),
            str(source.get("report_sha256") or ""),
            report_sha256,
        }
        if len(identity_values) != 1:
            raise HumanReviewPacketError(
                PROVENANCE_FAILURE,
                f"source_report_hash_mismatch:{report_dir}",
            )
        if (
            bundle.get("agent_output_id") != source.get("agent_output_id")
            or bundle.get("ticker") != source.get("ticker")
            or bundle.get("agent") != source.get("agent")
            or bundle.get("prompt_version") != report_result.get("prompt_version")
            or bundle.get("prompt_sha256") != report_result.get("prompt_sha256")
            or bundle.get("prompt_version") != metadata.get("prompt_version")
            or bundle.get("prompt_sha256") != metadata.get("prompt_sha256")
        ):
            raise HumanReviewPacketError(
                PROVENANCE_FAILURE,
                f"bundle_source_result_identity_mismatch:{report_dir}",
            )

        claims = bundle.get("claims")
        if not isinstance(claims, list):
            raise HumanReviewPacketError(
                PROVENANCE_FAILURE,
                f"claims_not_list:{report_dir}",
            )
        shadow_claim_ids = {
            str(claim.get("shadow_claim_id") or "")
            for claim in claims
            if isinstance(claim, Mapping)
        }
        legacy_matches = _unambiguous_legacy_matches(
            comparison,
            [record for record in legacy_records if isinstance(record, Mapping)],
            shadow_claim_ids,
        )

        for claim_index, claim in enumerate(claims, start=1):
            if not isinstance(claim, Mapping):
                raise HumanReviewPacketError(
                    PROVENANCE_FAILURE,
                    f"claim_not_object:{report_dir}:{claim_index}",
                )
            shadow_claim_id = str(claim.get("shadow_claim_id") or "")
            claim_text = claim.get("claim")
            if not shadow_claim_id or not isinstance(claim_text, str):
                raise HumanReviewPacketError(
                    PROVENANCE_FAILURE,
                    f"claim_identity_or_text_missing:{report_dir}:{claim_index}",
                )
            if shadow_claim_id in seen_claim_ids:
                raise HumanReviewPacketError(
                    COVERAGE_FAILURE,
                    f"duplicate_shadow_claim_id:{shadow_claim_id}",
                )
            seen_claim_ids.add(shadow_claim_id)

            spans = _validate_spans(
                report_text=report_text,
                spans=claim.get("source_spans"),
                report_dir=report_dir,
                shadow_claim_id=shadow_claim_id,
            )
            total_spans += len(spans)
            multi_span_claims += int(len(spans) > 1)
            claims_with_factors += int(bool(claim.get("factors")))
            direction = claim.get("direction")
            claims_with_direction += int(direction not in (None, ""))
            claims_with_non_unknown_direction += int(
                direction not in (None, "", "unknown")
            )

            legacy = legacy_matches.get(shadow_claim_id)
            legacy_record_id = ""
            legacy_claim_text = ""
            legacy_evidence_text = ""
            if legacy is not None:
                legacy_index = next(
                    index
                    for index, record in enumerate(legacy_records)
                    if record is legacy
                )
                legacy_record_id = _legacy_id(legacy, legacy_index)
                legacy_claim_text = str(legacy.get("claim") or "")
                legacy_evidence_text = str(legacy.get("evidence") or "")
                unambiguous_legacy_matches += 1

            material = (
                f"{source.get('source_run_id', '')}\0"
                f"{bundle.get('agent_output_id', '')}\0{shadow_claim_id}"
            )
            row = {
                "review_row_id": (
                    "phase1-review-v2-"
                    f"{hashlib.sha256(material.encode()).hexdigest()[:24]}"
                ),
                "ticker": ticker,
                "agent": agent,
                "report_family": family,
                "claim_ordinal": str(claim_index),
                "source_run_id": str(source.get("source_run_id") or ""),
                "evaluation_run_id": str(bundle.get("run_id") or ""),
                "agent_output_id": str(bundle.get("agent_output_id") or ""),
                "source_report_sha256": report_sha256,
                "shadow_claim_id": shadow_claim_id,
                "legacy_record_id": legacy_record_id,
                "claim_text": claim_text,
                "shadow_evidence_text": str(claim.get("evidence") or ""),
                "source_span_start": ";".join(str(span["start"]) for span in spans),
                "source_span_end": ";".join(str(span["end"]) for span in spans),
                "source_evidence_text": _span_text(spans),
                "source_spans": _span_text(spans),
                "source_context_before": _span_context(
                    report_text,
                    spans,
                    context_chars=context_chars,
                    before=True,
                ),
                "source_context_after": _span_context(
                    report_text,
                    spans,
                    context_chars=context_chars,
                    before=False,
                ),
                "entities": _json_cell(claim.get("entities") or []),
                "factors": _json_cell(claim.get("factors") or []),
                "direction": str(direction or ""),
                "confidence": str(claim.get("confidence", "")),
                "legacy_claim_text": legacy_claim_text,
                "legacy_evidence_text": legacy_evidence_text,
                **dict.fromkeys(REVIEW_FIELDS, ""),
            }
            rows.append(row)
            claims_by_ticker[ticker] += 1
            claims_by_agent[agent] += 1
            reports_seen.add((ticker, family))

    rows.sort(
        key=lambda row: (
            EXPECTED_TICKERS.index(row["ticker"]),
            EXPECTED_DIRECTORY_FAMILIES.index(row["report_family"]),
            int(row["claim_ordinal"]),
        )
    )
    if len(rows) != len(seen_claim_ids):
        raise HumanReviewPacketError(
            COVERAGE_FAILURE,
            f"row_claim_count_mismatch:{len(rows)}:{len(seen_claim_ids)}",
        )
    if reports_seen != expected_keys:
        raise HumanReviewPacketError(
            COVERAGE_FAILURE,
            f"reports_not_represented_by_claims:{sorted(expected_keys - reports_seen)}",
        )

    metrics = {
        "total_reports": len(report_dirs),
        "total_claims": len(rows),
        "total_source_spans": total_spans,
        "claims_by_ticker": dict(sorted(claims_by_ticker.items())),
        "claims_by_agent": dict(sorted(claims_by_agent.items())),
        "claims_with_multiple_spans": multi_span_claims,
        "claims_with_factors": claims_with_factors,
        "claims_with_direction": claims_with_direction,
        "claims_with_non_unknown_direction": claims_with_non_unknown_direction,
        "claims_with_unambiguous_legacy_match": unambiguous_legacy_matches,
        "context_char_limit_each_side": context_chars,
    }
    return rows, metrics


def render_review_csv(rows: Sequence[Mapping[str, str]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})
    return buffer.getvalue()


def _html_text(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def render_review_html(
    rows: Sequence[Mapping[str, str]],
    metrics: Mapping[str, Any],
) -> str:
    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        "<title>Phase 1 Human Review Packet v2</title>",
        """<style>
body{font-family:system-ui,-apple-system,sans-serif;margin:0;background:#f4f6f8;color:#18202a}
header.top{position:sticky;top:0;background:#14213d;color:#fff;padding:1rem 1.4rem;z-index:2}
main{max-width:1100px;margin:auto;padding:1rem}.summary,.claim{background:#fff;border:1px solid #ccd4dd;border-radius:10px;margin:1rem 0;padding:1rem;box-shadow:0 2px 8px #0001}
.claim h2{margin-top:0;font-size:1.15rem}.badge{display:inline-block;background:#e8eef7;border-radius:999px;padding:.2rem .6rem;margin-right:.35rem}
.label{font-weight:700;color:#344966;margin-top:.8rem}.context,.evidence,.claim-text,.legacy{white-space:pre-wrap;font-family:ui-monospace,monospace;border-radius:6px;padding:.8rem;overflow-wrap:anywhere}
.context{background:#f6f8fa}.evidence{background:#fff4cc;border-left:5px solid #d99b00}.claim-text{background:#eaf7ef;border-left:5px solid #25834a}.legacy{background:#f2edff;border-left:5px solid #7554b3}
.semantics,.review{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:.5rem}.cell{border:1px solid #d7dde5;border-radius:6px;padding:.55rem;overflow-wrap:anywhere}.blank{display:block;border-bottom:1px solid #333;min-height:1.2rem;margin-top:.35rem}
.allowed{font-size:.78rem;color:#586574}.span{margin:1rem 0;padding:.8rem;border:1px dashed #9aa7b5;border-radius:7px}.nav a{color:#dbeafe;margin-right:.7rem}code{white-space:pre-wrap}@media print{header.top{position:static}.claim{break-inside:avoid;box-shadow:none}}
</style></head><body>""",
        '<header class="top"><strong>Phase 1 Human Review Packet v2</strong>',
        '<div class="nav">',
        *(
            f'<a href="#{_html_text(ticker)}">{_html_text(ticker)}</a>'
            for ticker in EXPECTED_TICKERS
        ),
        "</div></header><main>",
        '<section class="summary"><h1>Review summary</h1>',
        f"<p>Reports: {_html_text(metrics['total_reports'])} · "
        f"Claims: {_html_text(metrics['total_claims'])} · "
        f"Source spans: {_html_text(metrics['total_source_spans'])} · "
        f"Multi-span claims: {_html_text(metrics['claims_with_multiple_spans'])}</p>",
        "<p>The CSV is the canonical review input. This HTML is a local, "
        "read-only inspection aid. Legacy content is comparison context, not gold.</p></section>",
    ]

    previous_ticker = None
    claim_numbers: Counter[tuple[str, str]] = Counter()
    for row in rows:
        ticker = row["ticker"]
        agent = row["agent"]
        if ticker != previous_ticker:
            parts.append(f'<h1 id="{_html_text(ticker)}">{_html_text(ticker)}</h1>')
            previous_ticker = ticker
        claim_numbers[(ticker, agent)] += 1
        number = claim_numbers[(ticker, agent)]
        parts.extend(
            [
                f'<article class="claim" id="{_html_text(row["review_row_id"])}">',
                f"<h2>{_html_text(ticker)} | {_html_text(agent)} | Claim {number}</h2>",
                f'<span class="badge">{_html_text(row["shadow_claim_id"])}</span>',
                f'<span class="badge">source run: {_html_text(row["source_run_id"])}</span>',
                '<div class="label">SOURCE CONTEXT BEFORE</div>',
                f'<div class="context">{_html_text(row["source_context_before"])}</div>',
                '<div class="label">&gt;&gt;&gt; EVIDENCE</div>',
                f'<div class="evidence">{_html_text(row["source_spans"])}</div>',
                '<div class="label">&lt;&lt;&lt; SOURCE CONTEXT AFTER</div>',
                f'<div class="context">{_html_text(row["source_context_after"])}</div>',
                '<div class="label">SHADOW CLAIM</div>',
                f'<div class="claim-text">{_html_text(row["claim_text"])}</div>',
                '<div class="label">STRUCTURED SEMANTICS</div><div class="semantics">',
                f'<div class="cell"><strong>Entities</strong><br>{_html_text(row["entities"])}</div>',
                f'<div class="cell"><strong>Factors</strong><br>{_html_text(row["factors"])}</div>',
                f'<div class="cell"><strong>Direction</strong><br>{_html_text(row["direction"])}</div>',
                f'<div class="cell"><strong>Confidence</strong><br>{_html_text(row["confidence"])}</div>',
                "</div>",
            ]
        )
        if row["legacy_record_id"]:
            parts.extend(
                [
                    '<div class="label">UNAMBIGUOUS LEGACY COMPARISON (NOT GOLD)</div>',
                    f'<div class="legacy"><strong>{_html_text(row["legacy_record_id"])}</strong>\n\n'
                    f'{_html_text(row["legacy_claim_text"])}\n\nEvidence: '
                    f'{_html_text(row["legacy_evidence_text"])}</div>',
                ]
            )
        parts.append('<div class="label">HUMAN REVIEW — fill the CSV, not this HTML</div>')
        parts.append('<div class="review">')
        for field in REVIEW_FIELDS:
            allowed = ALLOWED_REVIEW_VALUES.get(field)
            allowed_text = f"Allowed: {' / '.join(allowed)}" if allowed else "Free text"
            parts.append(
                f'<div class="cell"><strong>{_html_text(field.replace("_", " ").title())}</strong>'
                '<span class="blank"></span>'
                f'<span class="allowed">{_html_text(allowed_text)}</span></div>'
            )
        parts.append("</div></article>")
    parts.append("</main></body></html>\n")
    return "".join(parts)


def render_review_instructions(metrics: Mapping[str, Any]) -> str:
    allowed_lines = "\n".join(
        f"- `{field}`: " + ", ".join(f"`{value}`" for value in values)
        for field, values in ALLOWED_REVIEW_VALUES.items()
    )
    return f"""# Phase 1 Human Review Instructions — packet v2

This packet contains one row for every persisted accepted Shadow Claim: **{metrics['total_claims']} claims across {metrics['total_reports']} reports**. Complete `phase1_human_review_v2.csv`; the HTML file is a local inspection aid. Do not edit claim, evidence, identity, context, or structured-semantic columns.

## What to judge

### Semantic fidelity

Does the Shadow Claim faithfully represent what the source report says?

### Claim boundary

Did the model split or merge the statement appropriately? Mark a problem when a Claim is too broad, too narrow, or combines meanings that should be reviewed separately.

### Evidence correctness

Does every quoted source span actually support the Claim? `PARTIAL` means some, but not all, of the Claim is supported by the cited evidence.

### Entity correctness

Are the extracted entities correct for this Claim?

### Factor correctness

Are the mapped factor candidates semantically appropriate for this Claim?

### Direction correctness

Does `positive`, `negative`, `neutral`, or `unknown` preserve the source meaning?

## Critical errors

- `NEGATION_REVERSAL`: “not expected to increase” becomes “expected to increase.”
- `ATTRIBUTION_LOSS`: “Analysts believe X may happen” becomes “X will happen.”
- `FABRICATED_CLAIM`: the Claim asserts information absent from the source.
- `FABRICATED_EVIDENCE`: the cited span does not contain or support the asserted information.
- `IDENTITY_ERROR`: a company, person, security, product, or other identity is wrong.
- `OTHER`: another critical semantic error; explain it in `notes`.
- `NONE`: no critical error.

## Allowed values

{allowed_lines}

`reviewer` and `review_timestamp` are free-text fields; use an identifiable reviewer name and an ISO-8601 timestamp. `notes` is optional free text. All reviewer fields are intentionally blank in the generated packet and must be completed only by a human.

## Source spans and context

`source_span_start` and `source_span_end` are zero-based, end-exclusive offsets. For multi-span Claims, semicolon-separated offsets align by position, and `source_spans` labels every exact quote. Context is an exact, deterministic excerpt from the persisted original report, bounded to {metrics['context_char_limit_each_side']} characters on each side of each span. It is not an LLM summary.

## Legacy comparison

Legacy fields are populated only for a one-to-one exact overlap recorded in the persisted comparison artifact. They are comparison context only. The reviewer is not judging whether Shadow agrees with Legacy, and Legacy disagreement does not automatically make Shadow wrong. Blank Legacy fields mean no unambiguous exact match exists.
"""


def _secret_findings(texts: Mapping[str, str]) -> list[str]:
    findings: list[str] = []
    for name, text in texts.items():
        for pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(f"{name}:{pattern.pattern}")
    return findings


def build_review_packet(
    evaluation_dir: Path,
    *,
    master_state_path: Path,
    context_chars: int = 350,
) -> dict[str, Any]:
    """Build v2 artifacts atomically without mutating canonical inputs/state."""

    evaluation_dir = evaluation_dir.resolve()
    master_state_path = master_state_path.resolve()
    original_csv = evaluation_dir / "phase1_human_review.csv"
    if not original_csv.is_file():
        raise HumanReviewPacketError(
            PROVENANCE_FAILURE,
            f"original_review_csv_missing:{original_csv}",
        )
    state = _read_json(master_state_path)
    if not isinstance(state, Mapping) or state.get("current_state") != "WAITING_FOR_HUMAN_REVIEW":
        raise HumanReviewPacketError(
            PROVENANCE_FAILURE,
            f"master_state_not_waiting:{state.get('current_state') if isinstance(state, Mapping) else None}",
        )
    if Path(str(state.get("evaluation_dir") or "")).name != evaluation_dir.name:
        raise HumanReviewPacketError(
            PROVENANCE_FAILURE,
            "master_state_evaluation_dir_mismatch",
        )
    evaluation_metadata = _read_json(evaluation_dir / "evaluation_metadata.json")
    if not isinstance(evaluation_metadata, Mapping):
        raise HumanReviewPacketError(
            PROVENANCE_FAILURE,
            "evaluation_metadata_not_object",
        )

    report_dirs = sorted(path.parent for path in evaluation_dir.glob("reports/*/*/shadow_bundle.json"))
    canonical_paths = [
        evaluation_dir / "evaluation_metadata.json",
        *_canonical_input_paths(report_dirs),
    ]
    canonical_hash_before = _combined_file_hash(canonical_paths)
    original_csv_hash_before = _sha256_file(original_csv)
    state_hash_before = _sha256_file(master_state_path)
    provider_ledger_paths = [
        path
        for path in (
            master_state_path.parent / "provider_call_ledger.json",
            master_state_path.parent / "phase1_global_provider_call_ledger.jsonl",
        )
        if path.is_file()
    ]
    provider_ledger_hashes_before = {
        str(path): _sha256_file(path) for path in provider_ledger_paths
    }

    rows, metrics = collect_review_rows(
        evaluation_dir,
        context_chars=context_chars,
    )
    csv_text = render_review_csv(rows)
    html_text = render_review_html(rows, metrics)
    instructions_text = render_review_instructions(metrics)
    output_texts = {
        "phase1_human_review_v2.csv": csv_text,
        "phase1_human_review_v2.html": html_text,
        "phase1_human_review_instructions.md": instructions_text,
    }
    secret_findings = _secret_findings(output_texts)
    if secret_findings:
        raise HumanReviewPacketError(
            PROVENANCE_FAILURE,
            f"secret_pattern_detected:{secret_findings}",
        )

    csv_path = evaluation_dir / "phase1_human_review_v2.csv"
    html_path = evaluation_dir / "phase1_human_review_v2.html"
    instructions_path = evaluation_dir / "phase1_human_review_instructions.md"
    _atomic_write_text(csv_path, csv_text)
    _atomic_write_text(html_path, html_text)
    _atomic_write_text(instructions_path, instructions_text)

    parsed_rows = list(csv.DictReader(io.StringIO(csv_path.read_text(encoding="utf-8"))))
    expected_by_id = {row["review_row_id"]: row for row in rows}
    parsed_by_id = {row["review_row_id"]: row for row in parsed_rows}
    claim_text_matches = all(
        parsed_by_id.get(row_id, {}).get("claim_text") == expected["claim_text"]
        for row_id, expected in expected_by_id.items()
    )
    immutable_fields_match = all(
        parsed_by_id.get(row_id) is not None
        and all(
            parsed_by_id[row_id].get(field) == expected[field]
            for field in CSV_FIELDS
            if field not in REVIEW_FIELDS
        )
        for row_id, expected in expected_by_id.items()
    )
    all_review_fields_blank = all(
        all(row.get(field, "") == "" for field in REVIEW_FIELDS)
        for row in parsed_rows
    )

    original_csv_hash_after = _sha256_file(original_csv)
    state_hash_after = _sha256_file(master_state_path)
    canonical_hash_after = _combined_file_hash(canonical_paths)
    provider_ledger_hashes_after = {
        str(path): _sha256_file(path) for path in provider_ledger_paths
    }
    checks = {
        "all_24_reports_represented": metrics["total_reports"] == 24,
        "all_accepted_shadow_claims_represented_exactly_once": (
            len(parsed_rows) == metrics["total_claims"] == len(expected_by_id)
        ),
        "no_duplicate_review_row_id": len(parsed_rows) == len(parsed_by_id),
        "no_duplicate_shadow_claim_id": len(parsed_rows)
        == len({row["shadow_claim_id"] for row in parsed_rows}),
        "every_source_span_resolves_exactly": True,
        "every_claim_text_matches_persisted_shadow_output": claim_text_matches,
        "all_immutable_fields_match_builder_source": immutable_fields_match,
        "all_human_review_fields_blank": all_review_fields_blank,
        "original_csv_preserved": original_csv_hash_before == original_csv_hash_after,
        "master_state_unchanged": state_hash_before == state_hash_after,
        "canonical_evaluation_artifacts_unchanged": (
            canonical_hash_before == canonical_hash_after
        ),
        "provider_ledgers_unchanged": (
            provider_ledger_hashes_before == provider_ledger_hashes_after
        ),
        "no_api_keys_authorization_headers_or_secrets": not secret_findings,
        "provider_calls_zero": True,
        "state_waiting_for_human_review": state.get("current_state")
        == "WAITING_FOR_HUMAN_REVIEW",
        "semantic_quality_unproven": evaluation_metadata.get("semantic_quality")
        == "UNPROVEN",
        "human_review_pending": (
            evaluation_metadata.get("human_labels_created") is False
            and state.get("current_state") == "WAITING_FOR_HUMAN_REVIEW"
        ),
        "production_authority_legacy_adapter": evaluation_metadata.get(
            "production_authority"
        )
        == "LEGACY_ADAPTER",
        "prompt_v2_unchanged": (
            evaluation_metadata.get("prompt_version")
            == state.get("prompt_version_in_use")
            == "structured_adapter.claim_extraction_shadow.v2"
            and evaluation_metadata.get("prompt_sha256")
            == state.get("prompt_sha256_in_use")
        ),
    }
    if not all(checks.values()):
        raise HumanReviewPacketError(
            PROVENANCE_FAILURE,
            f"post_write_verification_failed:{[key for key, value in checks.items() if not value]}",
        )

    verification = {
        "schema_version": VERIFICATION_SCHEMA_VERSION,
        "packet_schema_version": PACKET_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "evaluation_dir": str(evaluation_dir),
        "source_artifacts": {
            "canonical_input_file_count": len(canonical_paths),
            "canonical_combined_sha256": canonical_hash_after,
            "original_csv_path": str(original_csv),
            "original_csv_sha256": original_csv_hash_after,
            "master_state_path": str(master_state_path),
            "master_state_sha256": state_hash_after,
            "provider_ledger_sha256": provider_ledger_hashes_after,
        },
        "coverage": {
            **metrics,
            "canonical_accepted_claim_count": metrics["total_claims"],
            "review_v2_row_count": len(parsed_rows),
        },
        "checks": checks,
        "outputs": {
            "csv": str(csv_path),
            "csv_sha256": _sha256_file(csv_path),
            "html": str(html_path),
            "html_sha256": _sha256_file(html_path),
            "instructions": str(instructions_path),
            "instructions_sha256": _sha256_file(instructions_path),
        },
        "provider_calls": 0,
        "state": "WAITING_FOR_HUMAN_REVIEW",
        "semantic_quality": "UNPROVEN",
        "human_review": "PENDING",
        "production_authority": "LEGACY_ADAPTER",
        "final_status": "PASS",
    }
    verification_text = json.dumps(
        verification,
        ensure_ascii=False,
        indent=2,
    ) + "\n"
    if _secret_findings({"phase1_human_review_packet_verification.json": verification_text}):
        raise HumanReviewPacketError(
            PROVENANCE_FAILURE,
            "secret_pattern_detected_in_verification",
        )
    verification_path = evaluation_dir / "phase1_human_review_packet_verification.json"
    _atomic_write_text(verification_path, verification_text)
    verification["outputs"]["verification"] = str(verification_path)
    return verification


__all__ = [
    "ALLOWED_REVIEW_VALUES",
    "COVERAGE_FAILURE",
    "CSV_FIELDS",
    "EXPECTED_AGENTS",
    "EXPECTED_DIRECTORY_FAMILIES",
    "EXPECTED_TICKERS",
    "HumanReviewPacketError",
    "PACKET_SCHEMA_VERSION",
    "PROVENANCE_FAILURE",
    "REVIEW_FIELDS",
    "VERIFICATION_SCHEMA_VERSION",
    "build_review_packet",
    "collect_review_rows",
    "render_review_csv",
    "render_review_html",
    "render_review_instructions",
]
