#!/usr/bin/env python3
"""Read-only, Provider-zero verifier for v4.1 location hardening."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.structure_engine.structured_output_shadow import (  # noqa: E402
    build_candidate_segments,
    candidate_segment_id,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v4 import (  # noqa: E402
    FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v4_1 import (  # noqa: E402
    FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256,
    LOCATION_PROTOCOL_DELTA,
    SEMANTIC_RULE_DELTA,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_1,
)
from comqutor_alpha.structure_engine.structured_output_shadow_schema import (  # noqa: E402
    sha256_text,
)
from comqutor_alpha.structure_engine.structured_output_shadow_v4_1 import (  # noqa: E402
    RESOLUTION_CANDIDATE_LOCAL_MULTIPLE,
    RESOLUTION_CANDIDATE_LOCAL_ZERO,
    RESOLUTION_CANDIDATE_REQUIRED,
    RESOLUTION_CANDIDATE_SOURCE_MISMATCH,
    RESOLUTION_CANDIDATE_UNKNOWN,
    RESOLUTION_DISAMBIGUATED_VIA_CANDIDATE,
    StructuredOutputShadowParserV4_1,
    build_rejected_forensic_record_v4_1,
    replay_rejected_forensic_record_v4_1,
    resolve_supporting_evidence_v4_1,
)

ARTIFACT_DIR = REPO_ROOT / "docs/audit_artifacts/phase1_master"
STATE_PATH = ARTIFACT_DIR / "phase1_master_state.json"
REPORT_PATH = ARTIFACT_DIR / "phase1_v4_duplicate_quote_protocol_hardening_report.json"
MANIFEST_PATH = ARTIFACT_DIR / "phase1_v4_1_location_protocol_manifest.json"

ORIGINAL_HASHES = {
    "phase1_v4_live_shadow_canary_report.md": "309d7fb617ac2f1a119ec97406633b7864eb1823411e9bb6ee343b4bb713aed6",
    "phase1_v4_live_shadow_canary_report.json": "000ff457c54d8e9e90ed370f0cd7f25d3090bf355ff9445bc843f44946e01850",
    "phase1_v4_live_shadow_canary_execution_contract.json": "b2bd316a8ba1b7c957d1b89add98a5e5cc099dadf282b6d039b94089c6d6e7ce",
    "phase1_v4_live_shadow_canary_runtime_result.json": "b141e64a858c02906ba15327f069bccca87981fe8a894c4d153833040b62b5e9",
    "phase1_v4_live_shadow_canary_pre_provider_incident.json": "10f17c9cd4fb1576be3b72b10fb70acf14fd217eda0268bce2d9a2ecaebb8943",
    "phase1_global_provider_call_ledger.jsonl": "a56e6774a586bcdc0d534ca1672b2931dd470c6eeb1d6ce6bb92dc7e6f17b156",
    "provider_call_ledger.json": "881a85baf82ba1a7c045ba7b87eaad58a016ffa47e9a42936d8377ed9f0c7c40",
}
SENSITIVE = (
    re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)authorization\s*[:=]\s*bearer\s+\S+"),
    re.compile(r"(?i)(?:chain[_-]?of[_-]?thought|<thinking>)"),
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _fixture() -> tuple[str, str, dict[str, dict[str, Any]]]:
    quote = "Demand increased 20%."
    report = f"Section A\n{quote}\nSection B\n{quote}"
    source_hash = sha256_text(report)
    agent_output_id = "run-duplicate:news_agent:news_report"
    first = report.index(quote)
    second = report.rindex(quote)

    def candidate(candidate_id: str, start: int, end: int):
        return {
            "candidate_id": candidate_id,
            "run_id": "run-duplicate",
            "ticker": "TEST",
            "agent": "news_agent",
            "agent_output_id": agent_output_id,
            "source_report_sha256": source_hash,
            "source_start": start,
            "source_end": end,
            "candidate_text_sha256": sha256_text(report[start:end]),
        }

    ids = {
        name: candidate_segment_id(agent_output_id, index, name)
        for index, name in enumerate(("first", "second", "wide", "zero"))
    }
    manifest = {
        ids["first"]: candidate(ids["first"], first, first + len(quote)),
        ids["second"]: candidate(ids["second"], second, second + len(quote)),
        ids["wide"]: candidate(ids["wide"], 0, len(report)),
        ids["zero"]: candidate(ids["zero"], 0, report.index("\n")),
    }
    return report, quote, manifest


def _resolve(report: str, quote: str, manifest, candidate_id):
    return resolve_supporting_evidence_v4_1(
        report=report,
        evidence={"quote": quote, "candidate_id": candidate_id},
        candidate_manifest=manifest,
        source_report_sha256=sha256_text(report),
        run_id="run-duplicate",
        ticker="TEST",
        agent="news_agent",
        agent_output_id="run-duplicate:news_agent:news_report",
    )


def main() -> int:
    state = _load(STATE_PATH)
    report_artifact = _load(REPORT_PATH)
    manifest_artifact = _load(MANIFEST_PATH)
    source, quote, manifest = _fixture()
    ids = list(manifest)
    wrong_source = dict(manifest[ids[0]])
    wrong_source["source_report_sha256"] = "0" * 64
    statuses = [
        _resolve(source, quote, manifest, None).status,
        _resolve(source, quote, manifest, ids[0]).status,
        _resolve(source, quote, manifest, ids[1]).status,
        _resolve(source, quote, manifest, "unknown").status,
        _resolve(source, quote, {ids[0]: wrong_source}, ids[0]).status,
        _resolve(source, quote, {ids[2]: manifest[ids[2]]}, ids[2]).status,
        _resolve(source, quote, {ids[3]: manifest[ids[3]]}, ids[3]).status,
    ]
    expected_statuses = [
        RESOLUTION_CANDIDATE_REQUIRED,
        RESOLUTION_DISAMBIGUATED_VIA_CANDIDATE,
        RESOLUTION_DISAMBIGUATED_VIA_CANDIDATE,
        RESOLUTION_CANDIDATE_UNKNOWN,
        RESOLUTION_CANDIDATE_SOURCE_MISMATCH,
        RESOLUTION_CANDIDATE_LOCAL_MULTIPLE,
        RESOLUTION_CANDIDATE_LOCAL_ZERO,
    ]

    forensic_report = f"{quote} {quote}"
    forensic_agent_output_id = "forensic:news_agent:news_report"
    candidates, _ = build_candidate_segments(
        forensic_report, agent_output_id=forensic_agent_output_id
    )
    selected = candidates[0]["candidate_segment_id"]
    proposal = {
        "claims": [
            {
                "claim": quote,
                "supporting_evidence": [{"quote": quote, "candidate_id": selected}],
                "entities": [],
                "factors": [],
                "direction": "positive",
                "confidence": 0.8,
            }
        ],
        "abstentions": [],
    }
    parser = StructuredOutputShadowParserV4_1(
        lambda **_kwargs: proposal, factor_vocabulary=[]
    )
    bundle = parser.parse_report_shadow_v4_1(
        source_report=forensic_report,
        run_id="forensic",
        ticker="TEST",
        agent="news_agent",
        agent_output_id=forensic_agent_output_id,
        candidate_segments=candidates,
    )
    forensic = build_rejected_forensic_record_v4_1(
        parser=parser,
        bundle=bundle,
        provider="offline-fixture",
        model="offline-fixture",
        semantic_call_id="offline-call",
    )
    replay = (
        replay_rejected_forensic_record_v4_1(forensic, source_report=forensic_report)
        if forensic is not None
        else {"status": "FAIL", "provider_calls": 0}
    )

    artifact_paths = [REPORT_PATH, MANIFEST_PATH, REPORT_PATH.with_suffix(".md")]
    clean = all(
        not any(pattern.search(path.read_text(encoding="utf-8")) for pattern in SENSITIVE)
        for path in artifact_paths
    )
    checks = [
        (
            "frozen_prompt_identity",
            STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256
            == FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256
            and STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256
            == FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256
            and STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_1.endswith(".v4.1")
            and SEMANTIC_RULE_DELTA == "NONE"
            and LOCATION_PROTOCOL_DELTA == "DETERMINISTIC_CANDIDATE_BINDING",
        ),
        ("seven_duplicate_fixture_cases", statuses == expected_statuses),
        (
            "rejected_forensics_complete",
            forensic is not None
            and forensic["admitted_claim_count"] == 0
            and forensic["non_authoritative"] is True
            and forensic["resolver_diagnostics"][0]["candidate_local_match_count"] == 2,
        ),
        (
            "rejected_deterministic_replay_provider_zero",
            replay["status"] == "PASS" and replay["provider_calls"] == 0,
        ),
        (
            "historical_and_production_truth",
            state["live_shadow_canary_result"]["status"] == "FAIL"
            and state["semantic_quality"] == "PASS_V4"
            and state["production_authority"] == "LEGACY_ADAPTER"
            and state["duplicate_quote_protocol_hardening"]["ready_for_recanary"]
            is False,
        ),
        (
            "v4_1_manifest_honest",
            manifest_artifact["parent_prompt"]
            == "structured_adapter.claim_extraction_shadow.v4"
            and manifest_artifact["semantic_rule_delta"] == "NONE"
            and manifest_artifact["quality"]["live_provider_qualification"] == "PENDING",
        ),
        (
            "hardening_report_honest",
            report_artifact["protocol_hardening"] == "PASS"
            and report_artifact["provider_calls"] == 0
            and report_artifact["ready_for_recanary"] is False,
        ),
        (
            "original_canary_and_provider_ledgers_immutable",
            all(_sha(ARTIFACT_DIR / name) == digest for name, digest in ORIGINAL_HASHES.items()),
        ),
        ("new_artifact_sensitive_content_scan", clean),
    ]
    failed = 0
    for name, ok in checks:
        failed += int(not ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    print(f"TOTAL={len(checks)} PASS={len(checks) - failed} FAIL={failed}")
    print("PROVIDER_CALLS=0")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
