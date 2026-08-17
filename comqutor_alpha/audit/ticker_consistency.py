"""Ticker Consistency Audit -- the single, shared implementation.

Verifies that one run's `metadata`, `raw_agent_outputs`,
`structured_agent_outputs`, `alpha_matches`, `structure_graph`,
`entity_alpha_exposures`, `conflicts`, `summary`, and `run_audit`
artifacts (whichever are supplied -- callers pass only what they have)
all agree on the same ticker, both at each artifact's own top level and
in nested per-record fields where those fields exist.

API routes, Run Audit v2, Architecture Replay, and any CLI all call
``audit_ticker_consistency`` here -- never a locally re-implemented copy
of the same check (see the sprint boundary: "不得在 API、Run Audit、
Replay 和 CLI 中各复制一套 ticker 检查逻辑").

Every conclusion is derived from the artifacts actually passed in --
nothing here guesses, and a missing/unreadable artifact is reported as
exactly that, never silently skipped without a trace.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Reason codes
# ---------------------------------------------------------------------------

REASON_TICKER_MISMATCH = "TICKER_MISMATCH"
REASON_TICKER_FIELD_MISSING = "TICKER_FIELD_MISSING"
REASON_TICKER_FIELD_INVALID = "TICKER_FIELD_INVALID"
REASON_RUN_ID_MISMATCH = "RUN_ID_MISMATCH"
REASON_ARTIFACT_MISSING = "ARTIFACT_MISSING"
REASON_ARTIFACT_UNREADABLE = "ARTIFACT_UNREADABLE"
REASON_FOREIGN_TICKER_ENTITY = "FOREIGN_TICKER_ENTITY"
REASON_FOREIGN_TICKER_NODE_LABEL = "FOREIGN_TICKER_NODE_LABEL"
REASON_FOREIGN_TICKER_EVIDENCE = "FOREIGN_TICKER_EVIDENCE"
REASON_FOREIGN_TICKER_SOURCE_LINEAGE = "FOREIGN_TICKER_SOURCE_LINEAGE"
REASON_API_RUN_TICKER_MISMATCH = "API_RUN_TICKER_MISMATCH"
REASON_FRONTEND_SELECTED_RUN_MISMATCH = "FRONTEND_SELECTED_RUN_MISMATCH"
REASON_FRONTEND_CACHE_KEY_INCOMPLETE = "FRONTEND_CACHE_KEY_INCOMPLETE"
REASON_REPLAY_ARTIFACT_IDENTITY_MISMATCH = "REPLAY_ARTIFACT_IDENTITY_MISMATCH"

# Replay-local artifacts whose own top-level "run_id" field must equal
# this replay's run_id (never the source run's) -- see
# build_replay_identity_consistency. "metadata.json" is checked
# separately (it must carry BOTH the replay's own run_id/replay_run_id
# AND preserve source_run_id -- the one artifact that legitimately
# mentions the source at all).
REPLAY_IDENTITY_ARTIFACT_FILENAMES = (
    "structured_agent_outputs.json",
    "alpha_matches.json",
    "extracted_structures.json",
    "structure_graph.json",
    "alpha_activations.json",
    "evidence_facts.json",
    "conflicts.json",
    "conflict_results.json",
    "entity_alpha_exposures.json",
    "summary.json",
    "run_audit.json",
    "artifact_manifest.json",
)

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"

STATUS_PASS = "pass"
STATUS_FAIL = "fail"

# A conservative, explicit watchlist of ticker symbols this repo's runs are
# known to use (see evaluation/manifests/mvp_cases.yaml's candidate list
# plus tickers with real runs on disk) -- foreign-ticker scanning is
# deliberately bounded to this set rather than an unbounded regex over any
# 1-5 letter uppercase word, which would false-positive constantly on
# ordinary acronyms (AI, EPS, YOY, GPU, ...).
DEFAULT_TICKER_WATCHLIST = frozenset(
    {
        "NVDA", "AMD", "MSFT", "GOOGL", "AMZN", "AVGO", "TSM", "SMCI", "QQQ",
        "SPY", "SNDK", "MU",
    }
)

# Fields whose value is never a legitimate ticker, no matter how it was set.
_INVALID_TICKER_VALUES = {"", "UNKNOWN", "NULL", "NONE"}


def normalize_ticker_for_audit(raw: Any) -> str | None:
    """Safe normalization only: strip whitespace, uppercase. Never applies
    a symbol-alias mapping (see boundary: "不得进行未经批准的 symbol alias
    映射"). Returns ``None`` for anything that isn't a legitimate ticker
    string (``null``, ``""``, ``"unknown"``, non-string)."""
    if not isinstance(raw, str):
        return None
    normalized = raw.strip().upper()
    if not normalized or normalized in _INVALID_TICKER_VALUES:
        return None
    return normalized


def resolve_expected_ticker(
    *,
    orchestrator_ticker: Any = None,
    db_run_ticker: Any = None,
    metadata_ticker: Any = None,
    raw_agent_outputs_ticker: Any = None,
) -> tuple[str | None, str | None]:
    """Resolves the single authoritative ``expected_ticker`` for a run, in
    priority order (section 3.1): orchestrator > DB run record > metadata >
    raw_agent_outputs. Never falls back to "whatever most artifacts agree
    on" -- that would let a majority-wrong ticker masquerade as correct.
    Returns ``(expected_ticker, expected_ticker_source)``; both ``None``
    when no source supplied a valid ticker."""
    for value, source in (
        (orchestrator_ticker, "run_orchestrator"),
        (db_run_ticker, "run_repository"),
        (metadata_ticker, "metadata"),
        (raw_agent_outputs_ticker, "raw_agent_outputs"),
    ):
        normalized = normalize_ticker_for_audit(value)
        if normalized is not None:
            return normalized, source
    return None, None


def _finding(
    *,
    code: str,
    artifact: str,
    json_path: str,
    expected_ticker: str | None,
    actual_ticker: Any,
    run_id: str,
    severity: str,
    detail: str | None = None,
) -> dict[str, Any]:
    entry = {
        "code": code,
        "artifact": artifact,
        "json_path": json_path,
        "expected_ticker": expected_ticker,
        "actual_ticker": actual_ticker,
        "run_id": run_id,
        "severity": severity,
    }
    if detail:
        entry["detail"] = detail
    return entry


# ---------------------------------------------------------------------------
# Per-artifact top-level + nested field specs.
#
# Each entry: (artifact_key, display_name, top_level_required,
#              nested_records_path, nested_ticker_field, nested_required)
#
# top_level_required=True means: if the artifact is present, its own
# top-level ticker field must exist and be valid (an artifact-wrapper
# contract every artifact writer has always honored) -- missing is an
# error, not a warning.
#
# nested_required=True means the nested field is part of the CURRENT
# formal per-record contract (structured_agent_outputs.records[*].ticker,
# alpha_matches.matches[*].ticker are both confirmed real, populated
# fields in the current schema) -- missing on a record is an error.
# nested_required=False means the nested field is optional/legacy --
# missing is a warning, never fabricated.
# ---------------------------------------------------------------------------

_ARTIFACT_SPECS: tuple[tuple[str, str, bool, str | None, str, bool], ...] = (
    ("metadata", "metadata.json", True, None, "ticker", False),
    ("raw_agent_outputs", "raw_agent_outputs.json", True, None, "ticker", False),
    ("structured_agent_outputs", "structured_agent_outputs.json", True, "records", "ticker", True),
    ("evidence_facts", "evidence_facts.json", True, "groups", "ticker", False),
    ("alpha_matches", "alpha_matches.json", True, "matches", "ticker", True),
    ("structure_graph", "structure_graph.json", True, None, "ticker", False),
    ("alpha_activations", "alpha_activations.json", True, None, "ticker", False),
    ("entity_alpha_exposures", "entity_alpha_exposures.json", True, "records", "ticker", True),
    ("conflicts", "conflicts.json", True, "conflicts", "ticker", False),
    ("summary", "summary.json", True, None, "ticker", False),
    ("run_audit", "run_audit.json", True, None, "ticker", False),
    ("artifact_manifest", "artifact_manifest.json", False, None, "ticker", False),
)


def _audit_run_id_field(record: Any, expected_run_id: str, artifact: str, json_path: str) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        return None
    run_id_value = record.get("run_id")
    if run_id_value in (None, ""):
        return None
    if str(run_id_value) != expected_run_id:
        return {
            "artifact": artifact,
            "json_path": json_path,
            "expected_run_id": expected_run_id,
            "actual_run_id": run_id_value,
        }
    return None


def _audit_artifact(
    *,
    artifact_key: str,
    display_name: str,
    top_level_required: bool,
    nested_records_path: str | None,
    nested_field: str,
    nested_required: bool,
    payload: Any,
    expected_ticker: str,
    run_id: str,
) -> tuple[list[dict], list[dict], list[dict], int, int, int]:
    """Returns (inconsistencies, warnings, run_id_mismatches,
    checked_artifact_increment, checked_field_count, missing_required_count)."""
    inconsistencies: list[dict] = []
    warnings: list[dict] = []
    run_id_mismatches: list[dict] = []
    checked_field_count = 0
    missing_required_count = 0

    if payload is _ARTIFACT_MISSING:
        if top_level_required:
            warnings.append(
                _finding(
                    code=REASON_ARTIFACT_MISSING,
                    artifact=display_name,
                    json_path="$",
                    expected_ticker=expected_ticker,
                    actual_ticker=None,
                    run_id=run_id,
                    severity=SEVERITY_WARNING,
                    detail="artifact not supplied to this audit call (absent or not yet generated)",
                )
            )
        return inconsistencies, warnings, run_id_mismatches, 0, 0, 0
    if payload is _ARTIFACT_UNREADABLE:
        warnings.append(
            _finding(
                code=REASON_ARTIFACT_UNREADABLE,
                artifact=display_name,
                json_path="$",
                expected_ticker=expected_ticker,
                actual_ticker=None,
                run_id=run_id,
                severity=SEVERITY_WARNING,
                detail="artifact content could not be parsed",
            )
        )
        return inconsistencies, warnings, run_id_mismatches, 1, 0, 0
    if not isinstance(payload, dict):
        warnings.append(
            _finding(
                code=REASON_ARTIFACT_UNREADABLE,
                artifact=display_name,
                json_path="$",
                expected_ticker=expected_ticker,
                actual_ticker=None,
                run_id=run_id,
                severity=SEVERITY_WARNING,
                detail=f"artifact payload is not a JSON object (got {type(payload).__name__})",
            )
        )
        return inconsistencies, warnings, run_id_mismatches, 1, 0, 0

    checked_field_count += 1
    top_actual = payload.get("ticker")
    top_normalized = normalize_ticker_for_audit(top_actual)
    if top_normalized is None:
        if artifact_key in ("ticker",):  # unreachable, kept for clarity of intent
            pass
        if top_level_required:
            missing_required_count += 1
            inconsistencies.append(
                _finding(
                    code=REASON_TICKER_FIELD_MISSING if "ticker" not in payload else REASON_TICKER_FIELD_INVALID,
                    artifact=display_name,
                    json_path="$.ticker",
                    expected_ticker=expected_ticker,
                    actual_ticker=top_actual,
                    run_id=run_id,
                    severity=SEVERITY_ERROR,
                )
            )
    elif top_normalized != expected_ticker:
        inconsistencies.append(
            _finding(
                code=REASON_TICKER_MISMATCH,
                artifact=display_name,
                json_path="$.ticker",
                expected_ticker=expected_ticker,
                actual_ticker=top_actual,
                run_id=run_id,
                severity=SEVERITY_ERROR,
            )
        )

    if mismatch := _audit_run_id_field(payload, run_id, display_name, "$.run_id"):
        run_id_mismatches.append(mismatch)

    if nested_records_path is not None:
        records = payload.get(nested_records_path)
        if isinstance(records, list):
            for i, record in enumerate(records):
                if not isinstance(record, dict):
                    continue
                json_path = f"$.{nested_records_path}[{i}].{nested_field}"
                if nested_field not in record:
                    if nested_required:
                        missing_required_count += 1
                        inconsistencies.append(
                            _finding(
                                code=REASON_TICKER_FIELD_MISSING,
                                artifact=display_name,
                                json_path=json_path,
                                expected_ticker=expected_ticker,
                                actual_ticker=None,
                                run_id=run_id,
                                severity=SEVERITY_ERROR,
                            )
                        )
                    else:
                        warnings.append(
                            _finding(
                                code=REASON_TICKER_FIELD_MISSING,
                                artifact=display_name,
                                json_path=json_path,
                                expected_ticker=expected_ticker,
                                actual_ticker=None,
                                run_id=run_id,
                                severity=SEVERITY_WARNING,
                                detail="optional/legacy nested ticker field not present on this record",
                            )
                        )
                    continue
                checked_field_count += 1
                nested_actual = record.get(nested_field)
                nested_normalized = normalize_ticker_for_audit(nested_actual)
                if nested_normalized is None:
                    severity = SEVERITY_ERROR if nested_required else SEVERITY_WARNING
                    target = inconsistencies if nested_required else warnings
                    target.append(
                        _finding(
                            code=REASON_TICKER_FIELD_INVALID,
                            artifact=display_name,
                            json_path=json_path,
                            expected_ticker=expected_ticker,
                            actual_ticker=nested_actual,
                            run_id=run_id,
                            severity=severity,
                        )
                    )
                elif nested_normalized != expected_ticker:
                    inconsistencies.append(
                        _finding(
                            code=REASON_TICKER_MISMATCH,
                            artifact=display_name,
                            json_path=json_path,
                            expected_ticker=expected_ticker,
                            actual_ticker=nested_actual,
                            run_id=run_id,
                            severity=SEVERITY_ERROR,
                        )
                    )
                if mismatch := _audit_run_id_field(record, run_id, display_name, f"$.{nested_records_path}[{i}].run_id"):
                    run_id_mismatches.append(mismatch)

    return inconsistencies, warnings, run_id_mismatches, 1, checked_field_count, missing_required_count


# Sentinels distinguishing "artifact not supplied to this call" (never
# generated / not this caller's concern) from "supplied but failed to
# parse" -- both are reported, never conflated.
_ARTIFACT_MISSING = object()
_ARTIFACT_UNREADABLE = object()


# ---------------------------------------------------------------------------
# Foreign ticker contamination scan
# ---------------------------------------------------------------------------

def _text_mentions_ticker(text: str, ticker: str) -> bool:
    return re.search(rf"\b{re.escape(ticker)}\b", text, flags=re.IGNORECASE) is not None


def scan_foreign_ticker_entities(
    *,
    expected_ticker: str,
    run_id: str,
    structure_graph: Any = None,
    structured_agent_outputs: Any = None,
    summary: Any = None,
    watchlist: frozenset[str] = DEFAULT_TICKER_WATCHLIST,
) -> list[dict[str, Any]]:
    """Conservative foreign-ticker scan (section 3.5). Never deletes or
    excludes a claim; only reports a finding with enough context for a
    human to judge. Real research reports routinely and legitimately name
    peer/supply-chain companies (e.g. a TSM report naming NVDA/AMD as
    foundry customers) without any "compared to"-style phrasing, so
    ``foreign_entity_context`` is derived structurally, never from a
    narrow keyword regex that would misclassify ordinary industry
    commentary as contamination:

    - ``co_mentioned_with_subject`` (severity ``warning``, kept): the
      claim's own entities (or text) also name this run's own subject
      ticker -- the foreign ticker is legitimately part of the same
      claim's context, exactly the "legitimate comparison" case the
      sprint spec calls out. Never hard-fails the audit by itself.
    - ``subject_absent`` (severity ``error``): the claim's entities name
      *only* a foreign ticker, never this run's own subject at all --
      the closest structural signal to "foreign entity incorrectly
      treated as the subject" the spec describes; escalated because it
      cannot be a peer-comparison sentence about the actual subject.
    - A graph *node label* naming a foreign ticker is always ``error``
      severity regardless of context: a node label is never a
      "comparison" aside, it *is* the graph's subject.
    - Edge evidence text mentioning a foreign ticker is always
      ``warning``: the edge's own source/target factor nodes are already
      correctly scoped to this run's subject graph, so evidence text
      merely citing a peer by name is normal industry context, not proof
      the edge itself is mislabeled.
    """
    findings: list[dict[str, Any]] = []
    other_tickers = {t for t in watchlist if t != expected_ticker}
    if not other_tickers:
        return findings

    if isinstance(structure_graph, dict):
        for node in structure_graph.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            label = str(node.get("label") or node.get("id") or "")
            for foreign in other_tickers:
                if _text_mentions_ticker(label, foreign):
                    findings.append(
                        _finding(
                            code=REASON_FOREIGN_TICKER_NODE_LABEL,
                            artifact="structure_graph.json",
                            json_path=f"$.nodes[?(@.id=={node.get('id')!r})].label",
                            expected_ticker=expected_ticker,
                            actual_ticker=foreign,
                            run_id=run_id,
                            severity=SEVERITY_ERROR,
                            detail=f"node label {label!r} names a different ticker than this run's subject ({expected_ticker})",
                        )
                    )
        for i, edge in enumerate(structure_graph.get("edges") or []):
            if not isinstance(edge, dict):
                continue
            for evidence_text in edge.get("evidence") or []:
                if not isinstance(evidence_text, str):
                    continue
                for foreign in other_tickers:
                    if _text_mentions_ticker(evidence_text, foreign):
                        findings.append(
                            _finding(
                                code=REASON_FOREIGN_TICKER_EVIDENCE,
                                artifact="structure_graph.json",
                                json_path=f"$.edges[{i}].evidence",
                                expected_ticker=expected_ticker,
                                actual_ticker=foreign,
                                run_id=run_id,
                                severity=SEVERITY_WARNING,
                                detail="foreign_entity_context=edge_evidence_mention (source/target nodes remain subject-scoped)",
                            )
                        )

    if isinstance(structured_agent_outputs, dict):
        records = structured_agent_outputs.get("records")
        if isinstance(records, list):
            for i, record in enumerate(records):
                if not isinstance(record, dict):
                    continue
                entities = record.get("entities")
                claim_text = str(record.get("claim") or "")
                if isinstance(entities, list) and entities:
                    entity_ticker_set = {str(e).strip().upper() for e in entities if isinstance(e, str)}
                    entity_tickers = entity_ticker_set & other_tickers
                    subject_present = expected_ticker in entity_ticker_set or _text_mentions_ticker(
                        claim_text, expected_ticker
                    )
                    for foreign in entity_tickers:
                        if not subject_present:
                            # A claim whose only recognizable entity is a
                            # different, watchlisted ticker and never
                            # mentions this run's own subject at all --
                            # the closest structural match to "foreign
                            # entity incorrectly treated as the subject"
                            # (spec example B).
                            findings.append(
                                _finding(
                                    code=REASON_FOREIGN_TICKER_ENTITY,
                                    artifact="structured_agent_outputs.json",
                                    json_path=f"$.records[{i}].entities",
                                    expected_ticker=expected_ticker,
                                    actual_ticker=foreign,
                                    run_id=run_id,
                                    severity=SEVERITY_ERROR,
                                    detail=(
                                        f"claim_id={record.get('claim_id')!r} foreign_entity_context=subject_absent "
                                        f"(entities contain only {foreign!r}, never {expected_ticker!r})"
                                    ),
                                )
                            )
                        else:
                            # Legitimate comparison/industry-relationship
                            # case (spec example A) -- the subject ticker
                            # is co-mentioned, so this stays a kept,
                            # informational finding, never an audit
                            # failure by itself.
                            findings.append(
                                _finding(
                                    code=REASON_FOREIGN_TICKER_ENTITY,
                                    artifact="structured_agent_outputs.json",
                                    json_path=f"$.records[{i}].entities",
                                    expected_ticker=expected_ticker,
                                    actual_ticker=foreign,
                                    run_id=run_id,
                                    severity=SEVERITY_WARNING,
                                    detail=f"claim_id={record.get('claim_id')!r} foreign_entity_context=co_mentioned_with_subject",
                                )
                            )

    if isinstance(summary, dict):
        for key in ("headline", "summary_text", "narrative"):
            text = summary.get(key)
            if isinstance(text, str):
                for foreign in other_tickers:
                    if _text_mentions_ticker(text, foreign):
                        findings.append(
                            _finding(
                                code=REASON_FOREIGN_TICKER_EVIDENCE,
                                artifact="summary.json",
                                json_path=f"$.{key}",
                                expected_ticker=expected_ticker,
                                actual_ticker=foreign,
                                run_id=run_id,
                                severity=SEVERITY_WARNING,
                                detail="foreign_entity_context=summary_text_mention",
                            )
                        )

    return findings


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def audit_ticker_consistency(
    *,
    run_id: str,
    expected_ticker: str,
    expected_ticker_source: str = "unspecified",
    artifacts: dict[str, Any],
    watchlist: frozenset[str] = DEFAULT_TICKER_WATCHLIST,
) -> dict[str, Any]:
    """Single, shared Ticker Consistency Audit entry point.

    ``artifacts`` maps artifact_key (see ``_ARTIFACT_SPECS``, e.g.
    "metadata", "structured_agent_outputs", "alpha_matches", ...) to
    either the parsed JSON dict, ``None``/absent (not supplied to this
    call), or the string ``"__UNREADABLE__"`` (supplied but failed to
    parse). A caller only ever passes the artifacts it actually has --
    passing fewer than the full set is legitimate (e.g. Replay may not
    have a DB-backed conflicts payload) and only degrades the corresponding
    checks to a reported gap, never a crash.

    ``expected_ticker`` must already be resolved (see
    ``resolve_expected_ticker``) and normalized -- this function does not
    re-derive it, so the same expected value is guaranteed to be used for
    every field checked here.
    """
    normalized_expected = normalize_ticker_for_audit(expected_ticker)
    if normalized_expected is None:
        raise ValueError("INVALID_EXPECTED_TICKER: expected_ticker must be a non-empty ticker string")

    all_inconsistencies: list[dict] = []
    all_warnings: list[dict] = []
    all_run_id_mismatches: list[dict] = []
    checked_artifact_count = 0
    checked_field_count = 0
    missing_required_ticker_field_count = 0

    for artifact_key, display_name, top_level_required, nested_path, nested_field, nested_required in _ARTIFACT_SPECS:
        raw_payload = artifacts.get(artifact_key, _ARTIFACT_MISSING)
        if raw_payload == "__UNREADABLE__":
            raw_payload = _ARTIFACT_UNREADABLE
        elif raw_payload is None and artifact_key in artifacts:
            # Explicitly supplied as None (e.g. caller has no such
            # artifact for this run at all) -- treated the same as "not
            # supplied".
            raw_payload = _ARTIFACT_MISSING

        (
            inconsistencies,
            warnings,
            run_id_mismatches,
            artifact_increment,
            field_count,
            missing_count,
        ) = _audit_artifact(
            artifact_key=artifact_key,
            display_name=display_name,
            top_level_required=top_level_required,
            nested_records_path=nested_path,
            nested_field=nested_field,
            nested_required=nested_required,
            payload=raw_payload,
            expected_ticker=normalized_expected,
            run_id=run_id,
        )
        all_inconsistencies.extend(inconsistencies)
        all_warnings.extend(warnings)
        all_run_id_mismatches.extend(run_id_mismatches)
        checked_artifact_count += artifact_increment
        checked_field_count += field_count
        missing_required_ticker_field_count += missing_count

    foreign_entity_findings = scan_foreign_ticker_entities(
        expected_ticker=normalized_expected,
        run_id=run_id,
        structure_graph=artifacts.get("structure_graph"),
        structured_agent_outputs=artifacts.get("structured_agent_outputs"),
        summary=artifacts.get("summary"),
        watchlist=watchlist,
    )
    # A node-label / unclassified-entity foreign finding is severe enough
    # to also fail the overall audit (never silently informational); a
    # "comparison"-classified finding stays a warning-level signal only.
    hard_foreign_findings = [f for f in foreign_entity_findings if f["severity"] == SEVERITY_ERROR]

    overall_status = STATUS_FAIL if (all_inconsistencies or hard_foreign_findings) else STATUS_PASS

    return {
        "ticker_consistency": overall_status,
        "expected_ticker": normalized_expected,
        "expected_ticker_source": expected_ticker_source,
        "checked_artifact_count": checked_artifact_count,
        "checked_field_count": checked_field_count,
        "missing_required_ticker_field_count": missing_required_ticker_field_count,
        "inconsistencies": all_inconsistencies,
        "warnings": all_warnings,
        "foreign_entity_findings": foreign_entity_findings,
        "run_identity_diagnostics": {
            "expected_run_id": run_id,
            "mismatch_count": len(all_run_id_mismatches),
            "mismatches": all_run_id_mismatches,
        },
    }


# ---------------------------------------------------------------------------
# Architecture Replay identity validator
# ---------------------------------------------------------------------------


def build_replay_identity_consistency(
    *,
    source_run_id: str,
    replay_run_id: str,
    artifacts: dict[str, Any],
) -> dict[str, Any]:
    """Validates the Architecture Replay identity contract: every
    replay-local regenerated artifact must carry ``replay_run_id`` as its
    own top-level (and, where applicable, nested per-record) run identity
    -- never ``source_run_id``, which belongs only in ``metadata.json``'s
    lineage fields.

    ``artifacts`` maps filename (see ``REPLAY_IDENTITY_ARTIFACT_FILENAMES``,
    plus ``"metadata.json"``) to the parsed JSON dict for whichever
    artifacts the caller actually has -- an artifact not supplied is
    simply not checked (never a crash, never a fabricated pass).

    If any replay-local artifact instead carries ``source_run_id`` (the
    exact defect this validator exists to catch -- see
    ``REASON_REPLAY_ARTIFACT_IDENTITY_MISMATCH``), ``identity_consistency``
    is ``"fail"``; the caller (``run_structure_replay``) must then never
    report the replay as ``"completed"`` and never let
    ``artifact_manifest.json``'s ``artifact_completeness`` read ``"pass"``.
    """
    artifact_run_ids: dict[str, Any] = {}
    mismatched_artifacts: list[str] = []
    for filename in REPLAY_IDENTITY_ARTIFACT_FILENAMES:
        payload = artifacts.get(filename)
        if not isinstance(payload, dict):
            continue
        actual = payload.get("run_id")
        artifact_run_ids[filename] = actual
        if actual != replay_run_id:
            mismatched_artifacts.append(filename)

    nested_record_mismatch_count = 0
    for filename, nested_key in (
        ("structured_agent_outputs.json", "records"),
        ("alpha_matches.json", "matches"),
        ("entity_alpha_exposures.json", "records"),
    ):
        payload = artifacts.get(filename)
        if not isinstance(payload, dict):
            continue
        records = payload.get(nested_key)
        if not isinstance(records, list):
            continue
        for record in records:
            if isinstance(record, dict) and record.get("run_id") not in (None, replay_run_id):
                nested_record_mismatch_count += 1

    metadata = artifacts.get("metadata.json")
    metadata = metadata if isinstance(metadata, dict) else {}
    metadata_preserves_source_run_id = metadata.get("source_run_id") == source_run_id
    metadata_uses_replay_identity = (
        metadata.get("run_id") == replay_run_id and metadata.get("replay_run_id") == replay_run_id
    )

    identity_consistency = (
        STATUS_PASS
        if (
            not mismatched_artifacts
            and nested_record_mismatch_count == 0
            and metadata_preserves_source_run_id
            and metadata_uses_replay_identity
        )
        else STATUS_FAIL
    )

    return {
        "source_run_id": source_run_id,
        "replay_run_id": replay_run_id,
        "artifact_run_ids": artifact_run_ids,
        "mismatched_artifacts": mismatched_artifacts,
        "nested_record_mismatch_count": nested_record_mismatch_count,
        "metadata_preserves_source_run_id": metadata_preserves_source_run_id,
        "metadata_uses_replay_identity": metadata_uses_replay_identity,
        "identity_consistency": identity_consistency,
    }


__all__ = [
    "DEFAULT_TICKER_WATCHLIST",
    "STATUS_PASS",
    "STATUS_FAIL",
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "REASON_TICKER_MISMATCH",
    "REASON_TICKER_FIELD_MISSING",
    "REASON_TICKER_FIELD_INVALID",
    "REASON_RUN_ID_MISMATCH",
    "REASON_ARTIFACT_MISSING",
    "REASON_ARTIFACT_UNREADABLE",
    "REASON_FOREIGN_TICKER_ENTITY",
    "REASON_FOREIGN_TICKER_NODE_LABEL",
    "REASON_FOREIGN_TICKER_EVIDENCE",
    "REASON_FOREIGN_TICKER_SOURCE_LINEAGE",
    "REASON_API_RUN_TICKER_MISMATCH",
    "REASON_FRONTEND_SELECTED_RUN_MISMATCH",
    "REASON_FRONTEND_CACHE_KEY_INCOMPLETE",
    "REASON_REPLAY_ARTIFACT_IDENTITY_MISMATCH",
    "REPLAY_IDENTITY_ARTIFACT_FILENAMES",
    "normalize_ticker_for_audit",
    "resolve_expected_ticker",
    "scan_foreign_ticker_entities",
    "audit_ticker_consistency",
    "build_replay_identity_consistency",
]
