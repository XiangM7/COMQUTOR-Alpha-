#!/usr/bin/env python3
"""Round 22: regenerate the frontend's REAL-response fixtures for the Conflict-page "View basis" tests from the current backend.

* ``evidence_trace_conflict_legacy_claim_107.json`` -- a claim of the HISTORICAL admitted conflict A301__A304 (REAL saved data of run
  d5b60b8a-..., trimmed; see build_legacy_conflict_fixture.py), as the production route serves it.
* ``evidence_trace_conflict_positive_FIXTURE_claim_31.json`` -- the real claim 31 under a HAND-WRITTEN conflict: explicitly a FIXTURE
  (no verified real admitted conflict exists in any run).

Offline; writes only the fixture files; no Provider / search / fetch call is possible here.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

import test_t1_closeout_conflict_basis as t  # noqa: E402

from comqutor_alpha.api.evidence_trace import get_evidence_trace_response  # noqa: E402

OUT = REPO / "frontend" / "src" / "api" / "__fixtures__"

with tempfile.TemporaryDirectory(prefix="conflict_fixture_regen_") as tmp:
    root = Path(tmp)
    t._write_legacy_run(root)
    t._write_positive_fixture_run(root)
    legacy = get_evidence_trace_response(t.LEGACY_RUN_ID, root, claim_id=t.CLAIMS["counter"])  # claim 90: bear AND counter evidence
    positive = get_evidence_trace_response(t.FIXTURE_RUN_ID, root, claim_id=t.FIXTURE_CLAIM)
    assert legacy["status"] == "ok" and positive["status"] == "ok"
    (OUT / "evidence_trace_conflict_legacy_claim_90.json").write_text(json.dumps(legacy, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (OUT / "evidence_trace_conflict_positive_FIXTURE_claim_31.json").write_text(json.dumps(positive, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({"legacy_claim": t.CLAIMS["counter"], "positive_fixture_claim": t.FIXTURE_CLAIM}, indent=1))
