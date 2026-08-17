#!/usr/bin/env python3
"""Provider-zero verifier for Phase 1 v4 Canary diagnosis and repair."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.api.routes_research import build_research_response  # noqa: E402
from comqutor_alpha.storage.file_store import ALLOWED_ARTIFACT_PATHS  # noqa: E402
from comqutor_alpha.structure_engine.structured_output_live_shadow import (  # noqa: E402
    verify_live_shadow_exact_replay,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v4 import (  # noqa: E402
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256,
)
from comqutor_alpha.structure_engine.structured_output_shadow_provider import (  # noqa: E402
    SHADOW_WEEK2_ERROR_LOG_ARTIFACT_PATH,
)
from comqutor_alpha.structure_engine.week2_llm import (  # noqa: E402
    ERROR_LOG_ARTIFACT_PATH,
    Week2LLMGateway,
)

STATE_DIR = REPO_ROOT / "docs/audit_artifacts/phase1_master"
STATE_PATH = STATE_DIR / "phase1_master_state.json"
DIAGNOSIS_PATH = STATE_DIR / "phase1_v4_live_shadow_canary_failure_diagnosis.json"
VERIFICATION_PATH = STATE_DIR / "phase1_v4_live_shadow_canary_repair_verification.json"
CANARY_ROOT = REPO_ROOT / "outputs/canaries/phase1-v4-live-shadow-canary-20260810T213811Z"
RUN_ID = "phase1-v4-canary-20260810t213811z"
SHADOW_RUN_DIR = CANARY_ROOT / "shadow" / RUN_ID

ORIGINAL_HASHES = {
    STATE_DIR / "phase1_v4_live_shadow_canary_report.md": "309d7fb617ac2f1a119ec97406633b7864eb1823411e9bb6ee343b4bb713aed6",
    STATE_DIR / "phase1_v4_live_shadow_canary_report.json": "000ff457c54d8e9e90ed370f0cd7f25d3090bf355ff9445bc843f44946e01850",
    STATE_DIR / "phase1_v4_live_shadow_canary_execution_contract.json": "b2bd316a8ba1b7c957d1b89add98a5e5cc099dadf282b6d039b94089c6d6e7ce",
    STATE_DIR / "phase1_v4_live_shadow_canary_runtime_result.json": "b141e64a858c02906ba15327f069bccca87981fe8a894c4d153833040b62b5e9",
    STATE_DIR / "phase1_v4_live_shadow_canary_pre_provider_incident.json": "10f17c9cd4fb1576be3b72b10fb70acf14fd217eda0268bce2d9a2ecaebb8943",
    SHADOW_RUN_DIR / "structured_adapter_shadow_runtime/llm_semantic_calls.jsonl": "b04e92bddbca59625a9170fa3210561bd53750b39a062b570b09c821e6179742",
    SHADOW_RUN_DIR / "structured_adapter_shadow_validation.json": "42de9b5fd6b868d0c03386987a1472bb7f737791a26c944b2f876221ed4ec756",
    SHADOW_RUN_DIR / ERROR_LOG_ARTIFACT_PATH: "8c48b58d78394d43b6e0dd29b5ec2d5b56eee1339cba8a4898ed9e219c7dbfed",
}
LEDGER_HASHES = {
    STATE_DIR / "phase1_global_provider_call_ledger.jsonl": "a56e6774a586bcdc0d534ca1672b2931dd470c6eeb1d6ce6bb92dc7e6f17b156",
    STATE_DIR / "provider_call_ledger.json": "881a85baf82ba1a7c045ba7b87eaad58a016ffa47e9a42936d8377ed9f0c7c40",
}
SENSITIVE_PATTERNS = (
    re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)authorization\s*[:=]\s*bearer\s+\S+"),
    re.compile(r'(?i)"(?:api[_-]?key|password|secret)"\s*:\s*"(?!\[REDACTED\])[^"\s]{6,}"'),
    re.compile(r"(?i)(?:chain[_-]?of[_-]?thought|<thinking>)"),
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _semantic_records() -> list[dict[str, Any]]:
    path = SHADOW_RUN_DIR / "structured_adapter_shadow_runtime/llm_semantic_calls.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _sensitive_scan(paths: list[Path]) -> tuple[bool, str]:
    violations = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(text) for pattern in SENSITIVE_PATTERNS):
            violations.append(path.name)
    return not violations, "clean" if not violations else f"violations={violations}"


def main() -> int:
    state = _load(STATE_PATH)
    diagnosis = _load(DIAGNOSIS_PATH)
    verification = _load(VERIFICATION_PATH)
    validation = _load(SHADOW_RUN_DIR / "structured_adapter_shadow_validation.json")
    technical = next(item for item in validation["reports"] if item["agent"] == "market_agent")
    technical_call = _semantic_records()[-1]
    replay = verify_live_shadow_exact_replay(SHADOW_RUN_DIR)

    with tempfile.TemporaryDirectory(prefix="comqutor-shadow-isolation-") as temp_dir:
        output_root = Path(temp_dir)
        gateway = Week2LLMGateway(
            object(),
            run_id="offline-shadow-isolation",
            output_root=output_root,
            error_log_artifact_path=SHADOW_WEEK2_ERROR_LOG_ARTIFACT_PATH,
        )
        gateway._log("structured_claim_shadow", "WEEK2_LLM_VALIDATION_FAILED", 1)
        response = build_research_response("offline-shadow-isolation", output_root=output_root)
        shadow_log_exists = (
            output_root / "offline-shadow-isolation" / SHADOW_WEEK2_ERROR_LOG_ARTIFACT_PATH
        ).exists()
        canonical_log_exists = (
            output_root / "offline-shadow-isolation" / ERROR_LOG_ARTIFACT_PATH
        ).exists()

    scan_ok, scan_detail = _sensitive_scan(
        [
            DIAGNOSIS_PATH,
            STATE_DIR / "phase1_v4_live_shadow_canary_failure_diagnosis.md",
            VERIFICATION_PATH,
            STATE_DIR / "phase1_v4_live_shadow_canary_repair_verification.md",
        ]
    )

    checks: list[tuple[str, Callable[[], tuple[bool, str]]]] = [
        (
            "original_canary_artifacts_immutable",
            lambda: (
                all(_sha256(path) == expected for path, expected in ORIGINAL_HASHES.items()),
                f"files={len(ORIGINAL_HASHES)}",
            ),
        ),
        (
            "provider_ledgers_unchanged",
            lambda: (
                all(_sha256(path) == expected for path, expected in LEDGER_HASHES.items())
                and state.get("cumulative_logical_calls") == 95
                and state.get("cumulative_provider_attempts") == 102,
                "logical=95 attempts=102",
            ),
        ),
        (
            "shadow_error_namespace_isolated",
            lambda: (
                SHADOW_WEEK2_ERROR_LOG_ARTIFACT_PATH in ALLOWED_ARTIFACT_PATHS
                and shadow_log_exists
                and not canonical_log_exists
                and response["artifacts"]["week2_llm_error_logs"] is False,
                f"shadow={shadow_log_exists} canonical={canonical_log_exists}",
            ),
        ),
        (
            "technical_ambiguity_reproduced_from_record",
            lambda: (
                technical["resolution_log"][0]
                == {
                    "claim_index": 0,
                    "quote_index": 0,
                    "status": "AMBIGUOUS_MULTIPLE_MATCH",
                    "match_count": 2,
                }
                and technical["accepted"] is False
                and technical["reason_codes"] == ["SHADOW_SOURCE_SPAN_INVALID"],
                "claim=0 quote=0 exact_matches=2 rejected",
            ),
        ),
        (
            "rejected_proposal_forensic_gap_recorded",
            lambda: (
                technical_call["raw_output_text"] is None
                and technical_call["raw_output_sha256"] is None
                and technical_call["validated_output"] is None
                and diagnosis["FAILURE_B_ROOT_CAUSE"]["supporting_quote"]
                == "UNRECOVERABLE_NOT_PERSISTED",
                "raw and validated rejected payload absent; no guessed quote",
            ),
        ),
        (
            "resolver_and_prompt_unchanged",
            lambda: (
                diagnosis["FAILURE_B_CLASSIFICATION"]
                == "B1_EXPECTED_SAFE_AMBIGUOUS_REJECTION"
                and diagnosis["FAILURE_B_FIX_OR_NO_FIX"]["fix"] == "NONE"
                and diagnosis["FAILURE_B_FIX_OR_NO_FIX"]["resolver_strictness_weakened"]
                is False
                and STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256
                == "1de0d3dad615946b4670cc7458a75fccbeffdbdcb3cefe54d00097c3d4478b3a",
                "B1; resolver fix=NONE; prompt v4 hash frozen",
            ),
        ),
        (
            "exact_replay_remains_provider_zero",
            lambda: (
                replay["status"] == "PASS"
                and replay["accepted_report_count"] == 3
                and replay["provider_calls"] == 0,
                f"status={replay['status']} accepted={replay['accepted_report_count']} calls={replay['provider_calls']}",
            ),
        ),
        (
            "state_and_repair_outcome_honest",
            lambda: (
                state["production_authority"] == "LEGACY_ADAPTER"
                and state["live_shadow_canary_result"]["status"] == "FAIL"
                and state["live_shadow_canary_failure_repair"]["canary_failure_repair"]
                == "PARTIAL"
                and state["live_shadow_canary_failure_repair"]["ready_for_recanary"] is False
                and verification["production_cutover"] == "NOT_RUN",
                "original FAIL; repair PARTIAL; recanary NO; Legacy authority",
            ),
        ),
        ("new_artifact_sensitive_content_scan", lambda: (scan_ok, scan_detail)),
    ]

    failed = 0
    for name, check in checks:
        ok, detail = check()
        failed += int(not ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    print(f"TOTAL={len(checks)} PASS={len(checks) - failed} FAIL={failed}")
    print("PHASE1_V4_CANARY_REPAIR_VERIFIER: " + ("PASS" if failed == 0 else "FAIL"))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
