#!/usr/bin/env python3
"""Round 21: regenerate the frontend's REAL-response fixtures (``frontend/src/api/__fixtures__/evidence_*.json``) from the
current backend, so the adapter / component tests exercise the contract that actually ships.

Offline and read-only apart from the four fixture files: it builds a temporary run from the trimmed copy of the saved AMD
records (``tests/fixtures/t1_closure_amd_excerpt.json``), runs the production graph pipeline on it (in-memory SQLite) and
asks the production route function for the responses -- the same way ``tests/test_t1_closure_grounding_dependency_trace.py``
builds its run. No Provider / search / fetch call is possible here.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

spec = importlib.util.spec_from_file_location("t1_closure_tests", REPO / "tests" / "test_t1_closure_grounding_dependency_trace.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)  # type: ignore[union-attr]

from comqutor_alpha.api.evidence_trace import get_evidence_trace_response  # noqa: E402

RUN_ID = "t1_closure_fixture_run"
OUT = REPO / "frontend" / "src" / "api" / "__fixtures__"
CLAIMS = {
    "evidence_trace_claim_31.json": module.FA + "31",
    "evidence_trace_claim_33.json": module.FA + "33",
    "evidence_trace_claim_10_a304.json": module.PM + "10",
}

with tempfile.TemporaryDirectory(prefix="fixture_regen_") as tmp:
    tmp_path = Path(tmp)
    run_dir = module._build_run(tmp_path, RUN_ID, contract=True)
    module._run_pipeline(run_dir)
    written = {}
    for name, claim_id in CLAIMS.items():
        response = get_evidence_trace_response(RUN_ID, tmp_path, claim_id=claim_id)
        assert response["status"] == "ok", response
        (OUT / name).write_text(json.dumps(response, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        written[name] = claim_id
    key = get_evidence_trace_response(RUN_ID, tmp_path, scope="key")
    assert key["status"] == "ok", key
    (OUT / "evidence_key_conclusions.json").write_text(json.dumps(key, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    written["evidence_key_conclusions.json"] = "scope=key"
print(json.dumps(written, indent=1))
