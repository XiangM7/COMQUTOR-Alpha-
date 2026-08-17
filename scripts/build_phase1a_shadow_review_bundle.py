"""Build an explicit offline Phase 1A review bundle.

The command never constructs a Provider.  Without ``--fixture-output`` it
only emits source/candidate/review-input material with status NOT_GENERATED.
Historical ``outputs/runs`` and ``outputs/replays`` are always read-only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.structure_engine.structured_output_shadow import (  # noqa: E402
    StructuredOutputShadowParser,
    build_candidate_segments,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt import (  # noqa: E402
    STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
)
from comqutor_alpha.structure_engine.structured_output_shadow_review import (  # noqa: E402
    build_blank_review_rows,
    compare_legacy_and_shadow,
    render_blank_review_csv,
)
from comqutor_alpha.structure_engine.structured_output_shadow_schema import (  # noqa: E402
    build_shadow_bundle,
    sha256_text,
)

TARGET_TICKERS = ("NVDA", "QQQ", "MSFT", "SNDK", "TSM", "AMD")
TARGET_AGENT_FAMILIES = ("fundamental", "news", "sentiment", "technical")
AGENT_FAMILY = {
    "fundamental_agent": "fundamental",
    "fundamentals_agent": "fundamental",
    "news_agent": "news",
    "sentiment_agent": "sentiment",
    "technical_agent": "technical",
    "market_agent": "technical",
}


class FixtureSemanticInvoker:
    """Returns a pre-supplied fixture; it cannot perform external I/O."""

    def __init__(self, fixture: Mapping[str, Any]) -> None:
        self.fixture = deepcopy(dict(fixture))
        self.call_count = 0

    def invoke(self, *, prompt: str, request: Mapping[str, Any]) -> dict[str, Any]:
        del prompt, request
        self.call_count += 1
        return deepcopy(self.fixture)


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def validate_output_directory(raw_path: str | Path) -> Path:
    """Resolve an explicit output and reject traversal/historical trees."""

    raw = Path(raw_path)
    if ".." in raw.parts:
        raise ValueError("output directory traversal is forbidden")
    resolved = raw.expanduser().resolve()
    forbidden = (REPO_ROOT / "outputs/runs").resolve(), (REPO_ROOT / "outputs/replays").resolve()
    if any(resolved == root or _inside(resolved, root) for root in forbidden):
        raise ValueError("Phase 1A review bundles cannot be written to historical outputs")
    return resolved


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_evaluation_corpus_inventory() -> tuple[dict[str, Any], str]:
    """Read-only scan of historical runs; return inventory JSON and coverage CSV."""

    reports: list[dict[str, Any]] = []
    malformed_artifacts: list[dict[str, str]] = []
    for raw_path in sorted((REPO_ROOT / "outputs/runs").glob("*/raw_agent_outputs.json")):
        relative_path = raw_path.relative_to(REPO_ROOT).as_posix()
        try:
            payload = _load_json(raw_path)
        except (OSError, json.JSONDecodeError) as exc:
            malformed_artifacts.append(
                {"report_path": relative_path, "exclusion_reason": type(exc).__name__}
            )
            continue
        if not isinstance(payload, Mapping):
            malformed_artifacts.append(
                {"report_path": relative_path, "exclusion_reason": "ROOT_NOT_OBJECT"}
            )
            continue
        ticker = str(payload.get("ticker") or "").upper()
        if ticker not in TARGET_TICKERS:
            continue
        source_run_id = str(payload.get("run_id") or raw_path.parent.name)
        for raw_record in payload.get("agent_outputs") or []:
            if not isinstance(raw_record, Mapping):
                continue
            agent = str(raw_record.get("agent") or "").lower()
            family = AGENT_FAMILY.get(agent)
            if family is None:
                continue
            report = raw_record.get("raw_output")
            malformed = not isinstance(report, str)
            report_text = report if isinstance(report, str) else ""
            required_metadata = all(
                isinstance(raw_record.get(field), str) and bool(raw_record.get(field))
                for field in ("run_id", "ticker", "agent", "agent_output_id")
            )
            empty = not report_text.strip()
            eligible = not malformed and not empty and required_metadata
            exclusion_reasons = []
            if malformed:
                exclusion_reasons.append("REPORT_NOT_STRING")
            if empty:
                exclusion_reasons.append("REPORT_EMPTY")
            if not required_metadata:
                exclusion_reasons.append("REQUIRED_METADATA_MISSING")
            agent_output_id = str(raw_record.get("agent_output_id") or "")
            reports.append(
                {
                    "source_run_id": source_run_id,
                    "ticker": ticker,
                    "agent": agent,
                    "agent_family": family,
                    "agent_output_id": agent_output_id,
                    "report_path": f"{relative_path}#{agent_output_id}",
                    "raw_agent_outputs_path": relative_path,
                    "report_sha256": hashlib.sha256(report_text.encode()).hexdigest(),
                    "report_length": len(report_text),
                    "empty": empty,
                    "malformed": malformed,
                    "required_metadata_exists": required_metadata,
                    "eligible_for_phase1_shadow": eligible,
                    "exclusion_reason": "|".join(exclusion_reasons) or None,
                }
            )

    coverage_rows: list[dict[str, Any]] = []
    for ticker in TARGET_TICKERS:
        for family in TARGET_AGENT_FAMILIES:
            candidates = [
                report
                for report in reports
                if report["ticker"] == ticker and report["agent_family"] == family
            ]
            eligible = [report for report in candidates if report["eligible_for_phase1_shadow"]]
            coverage_rows.append(
                {
                    "ticker": ticker,
                    "agent_family": family,
                    "target_slot": True,
                    "candidate_report_count": len(candidates),
                    "eligible_report_count": len(eligible),
                    "slot_covered": bool(eligible),
                    "selected_agent_output_id": eligible[0]["agent_output_id"] if eligible else "",
                    "exclusion_summary": "" if eligible else "NO_ELIGIBLE_REPORT",
                }
            )
    covered_slots = sum(bool(row["slot_covered"]) for row in coverage_rows)
    available_families = sorted(
        {
            report["agent_family"]
            for report in reports
            if report["eligible_for_phase1_shadow"]
        }
    )
    if len(available_families) < len(TARGET_AGENT_FAMILIES):
        readiness = "NO"
    elif covered_slots == len(coverage_rows):
        readiness = "YES"
    else:
        readiness = "PARTIAL"
    inventory = {
        "schema_version": "comqutor.phase1a.evaluation_corpus_inventory.v1",
        "scan_mode": "read_only",
        "source_root": "outputs/runs",
        "target_tickers": list(TARGET_TICKERS),
        "target_agent_families": list(TARGET_AGENT_FAMILIES),
        "target_slot_count": len(coverage_rows),
        "covered_slot_count": covered_slots,
        "eligible_report_count": sum(
            bool(report["eligible_for_phase1_shadow"]) for report in reports
        ),
        "excluded_report_count": sum(
            not report["eligible_for_phase1_shadow"] for report in reports
        ),
        "available_agent_families": available_families,
        "phase1b_evaluation_corpus_ready": readiness,
        "phase1a_harness_blocked": False,
        "reports": reports,
        "malformed_source_artifacts": malformed_artifacts,
        "coverage": coverage_rows,
    }
    buffer = io.StringIO(newline="")
    fields = (
        "ticker",
        "agent_family",
        "target_slot",
        "candidate_report_count",
        "eligible_report_count",
        "slot_covered",
        "selected_agent_output_id",
        "exclusion_summary",
    )
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(coverage_rows)
    return inventory, buffer.getvalue()


def write_evaluation_corpus_inventory(output_dir: str | Path) -> dict[str, Any]:
    """Write generated audit inventory only to an explicit non-historical directory."""

    destination = validate_output_directory(output_dir)
    inventory, coverage_csv = build_evaluation_corpus_inventory()
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "evaluation_corpus_inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (destination / "evaluation_corpus_coverage.csv").write_text(
        coverage_csv, encoding="utf-8"
    )
    return inventory


def _load_source_run(source_run: Path) -> tuple[list[dict[str, Any]], Any]:
    source_run = source_run.expanduser().resolve()
    raw_path = source_run / "raw_agent_outputs.json"
    if not raw_path.is_file():
        raise ValueError("source run must contain raw_agent_outputs.json")
    raw = _load_json(raw_path)
    if not isinstance(raw, Mapping) or not isinstance(raw.get("agent_outputs"), list):
        raise ValueError("raw_agent_outputs.json has no agent_outputs list")
    structured_path = source_run / "structured_agent_outputs.json"
    legacy = _load_json(structured_path) if structured_path.is_file() else {"records": []}
    return [dict(item) for item in raw["agent_outputs"] if isinstance(item, Mapping)], legacy


def _load_corpus_manifest(path: Path) -> tuple[list[dict[str, Any]], Any]:
    manifest = _load_json(path.expanduser().resolve())
    if not isinstance(manifest, Mapping):
        raise ValueError("corpus manifest must be an object")
    entries = manifest.get("reports") or manifest.get("eligible_reports") or []
    reports: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, Mapping) or entry.get("eligible_for_phase1_shadow") is False:
            continue
        raw_path_text = str(entry.get("raw_agent_outputs_path") or entry.get("report_path") or "")
        raw_path_text = raw_path_text.split("#", maxsplit=1)[0]
        raw_path = (REPO_ROOT / raw_path_text).resolve() if not Path(raw_path_text).is_absolute() else Path(raw_path_text).resolve()
        if not raw_path.is_file():
            continue
        payload = _load_json(raw_path)
        expected_id = str(entry.get("agent_output_id") or "")
        for raw_record in payload.get("agent_outputs") or []:
            if isinstance(raw_record, Mapping) and (
                not expected_id or str(raw_record.get("agent_output_id") or "") == expected_id
            ):
                reports.append(dict(raw_record))
    return reports, {"records": []}


def _legacy_for_agent(legacy_outputs: Any, raw_record: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: Sequence[Any]
    if isinstance(legacy_outputs, list):
        records = legacy_outputs
    elif isinstance(legacy_outputs, Mapping):
        records = (
            legacy_outputs.get("records")
            or legacy_outputs.get("structured_outputs")
            or legacy_outputs.get("agent_outputs")
            or []
        )
    else:
        records = []
    agent_output_id = str(raw_record.get("agent_output_id") or "")
    agent = str(raw_record.get("agent") or "")
    return [
        dict(record)
        for record in records
        if isinstance(record, Mapping)
        and (
            str(record.get("source_agent_output_id") or record.get("agent_output_id") or "")
            == agent_output_id
            or (not record.get("source_agent_output_id") and record.get("agent") == agent)
        )
    ]


def _fixture_for_record(fixtures: Any, record: Mapping[str, Any]) -> Mapping[str, Any] | None:
    if fixtures is None:
        return None
    if isinstance(fixtures, Mapping) and "claims" in fixtures:
        return fixtures
    agent_output_id = str(record.get("agent_output_id") or "")
    if isinstance(fixtures, Mapping):
        candidate = fixtures.get(agent_output_id)
        return candidate if isinstance(candidate, Mapping) else None
    if isinstance(fixtures, list):
        for candidate in fixtures:
            if isinstance(candidate, Mapping) and candidate.get("agent_output_id") == agent_output_id:
                return candidate
    return None


def build_review_bundle(
    *,
    output_dir: str | Path,
    source_run: str | Path | None = None,
    corpus_manifest: str | Path | None = None,
    fixture_output: str | Path | None = None,
) -> dict[str, Any]:
    if (source_run is None) == (corpus_manifest is None):
        raise ValueError("exactly one of source_run or corpus_manifest is required")
    destination = validate_output_directory(output_dir)
    if source_run is not None:
        raw_records, legacy_outputs = _load_source_run(Path(source_run))
        source_kind = "source_run"
    else:
        raw_records, legacy_outputs = _load_corpus_manifest(Path(corpus_manifest or ""))
        source_kind = "corpus_manifest"
    fixtures = _load_json(Path(fixture_output)) if fixture_output is not None else None

    candidate_inputs: list[dict[str, Any]] = []
    shadow_bundles: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    review_rows: list[dict[str, str]] = []
    fake_call_count = 0
    for raw_record in raw_records:
        report = raw_record.get("raw_output")
        if not isinstance(report, str):
            continue
        run_id = str(raw_record.get("run_id") or "")
        ticker = str(raw_record.get("ticker") or "")
        agent = str(raw_record.get("agent") or "")
        agent_output_id = str(raw_record.get("agent_output_id") or "")
        candidates, filtered = build_candidate_segments(report, agent_output_id=agent_output_id)
        candidate_inputs.append(
            {
                "run_id": run_id,
                "ticker": ticker,
                "agent": agent,
                "agent_output_id": agent_output_id,
                "source_report_sha256": sha256_text(report),
                "source_report": report,
                "candidate_segments": candidates,
                "filtered_candidate_reasons": filtered,
                "shadow_output_status": "NOT_GENERATED" if fixtures is None else "FIXTURE_REQUESTED",
                "shadow_only": True,
                "production_authority": False,
            }
        )
        legacy_for_agent = _legacy_for_agent(legacy_outputs, raw_record)
        fixture = _fixture_for_record(fixtures, raw_record)
        if fixture is not None:
            invoker = FixtureSemanticInvoker(fixture)
            parser = StructuredOutputShadowParser(invoker)
            shadow = parser.parse_report_shadow(
                source_report=report,
                run_id=run_id,
                ticker=ticker,
                agent=agent,
                agent_output_id=agent_output_id,
                source_metadata=raw_record,
                candidate_segments=candidates,
            )
            fake_call_count += invoker.call_count
        else:
            shadow = build_shadow_bundle(
                run_id=run_id,
                ticker=ticker,
                agent=agent,
                agent_output_id=agent_output_id,
                source_report_sha256=sha256_text(report),
                prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
                prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
                validation_summary={"status": "NOT_GENERATED", "valid": False, "reason_codes": []},
            )
        comparison = compare_legacy_and_shadow(legacy_for_agent, shadow)
        shadow_bundles.append(shadow)
        comparisons.append(comparison)
        review_rows.extend(
            build_blank_review_rows(
                comparison=comparison,
                legacy_outputs=legacy_for_agent,
                shadow_bundle=shadow,
            )
        )

    destination.mkdir(parents=True, exist_ok=True)
    status = "NOT_GENERATED" if fixtures is None else "FIXTURE_GENERATED"
    manifest = {
        "schema_version": "comqutor.phase1a.review_bundle_manifest.v1",
        "source_kind": source_kind,
        "shadow_output_status": status,
        "report_count": len(candidate_inputs),
        "fake_semantic_invoker_calls": fake_call_count,
        "provider_calls": 0,
        "network_connections": 0,
        "redis_connections": 0,
        "database_writes": 0,
        "human_labels_created": False,
        "shadow_only": True,
        "production_authority": False,
    }
    artifacts = {
        "bundle_manifest.json": manifest,
        "shadow_source_candidates.json": {"reports": candidate_inputs},
        "shadow_bundles.json": {"shadow_output_status": status, "bundles": shadow_bundles},
        "legacy_shadow_comparisons.json": {"comparisons": comparisons},
    }
    for filename, payload in artifacts.items():
        (destination / filename).write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    (destination / "blank_human_review.csv").write_text(
        render_blank_review_csv(review_rows), encoding="utf-8"
    )
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source-run")
    source.add_argument("--corpus-manifest")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--fixture-output")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = build_review_bundle(
            output_dir=args.output_dir,
            source_run=args.source_run,
            corpus_manifest=args.corpus_manifest,
            fixture_output=args.fixture_output,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"PHASE_1A_REVIEW_BUNDLE: FAIL ({type(exc).__name__}: {exc})")
        return 1
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    print("PHASE_1A_REVIEW_BUNDLE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
