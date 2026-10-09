from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _sha(path: str) -> str:
    return hashlib.sha256((REPO_ROOT / path).read_bytes()).hexdigest()


def test_canonical_development_plan_is_unchanged():
    assert _sha("docs/specs/COMQUTOR_Alpha_Development_Plan_v1.0.docx") == (
        "cabf3381aaa633b7b88035ab6df2d7dac0def3d5ddd337f6384f23f4c439a8d9"
    )


def test_current_semantic_components_match_approved_phase1_master_baseline():
    # week2_llm.py / alpha_mapper.py hashes updated for the separately-
    # authorized Step 5A (v0.1.2.1) execution-capacity repair: single-claim
    # semantics restored as the production default (multi-claim batching
    # evaluated and DEFERRED after proving unreliable against the
    # configured Provider -- the code path is kept, offline-tested, but
    # unused by default), a workload-aware call-budget formula, controlled
    # bounded concurrency for independent single-claim calls, and an
    # evidence-based default timeout -- see docs/audit_artifacts/
    # week2_runtime_capacity_root_cause_v0.1.2.1.json and
    # week2_runtime_capacity_repair_v0.1.2.1.md. structured_output_adapter.py
    # and structure_extractor.py are untouched by that repair; their
    # hashes are unchanged.
    #
    # week2_llm.py hash updated again for the separately-authorized v0.1.3
    # Provider Final-Orphan Reliability Fix, Phase 1 (Option C): a
    # component-specific retry-count increase for evidence_stance_classifier
    # only (see docs/audit_artifacts/v0_1_3_evidence_stance_retry_fix.md and
    # v0_1_3_provider_final_orphan_reliability_audit.md). alpha_mapper.py,
    # structured_output_adapter.py, and structure_extractor.py are untouched
    # by this fix; their hashes are unchanged.
    #
    # structured_output_adapter.py hash updated for the separately-authorized
    # T1 source-linking chain (COMQUTOR Alpha next-round task, 2026-09-26,
    # re-pinned 2026-09-28 for the Part One/Two follow-up): adapt_run_outputs
    # now loads this run's own source_registry.json/metadata.json and
    # threads sources/evidence_cutoff through to a new _annotate_source_link
    # step (comqutor_alpha.source_provenance.match_evidence_to_source_
    # candidates + validate_source_reference); the 2026-09-28 follow-up
    # additionally threads a real Agent-input/output citation contract
    # through _llm_batch_enrichment/_validate_llm_batch_enrichment (a new
    # candidate_sources request field + cited_source_id response field,
    # scope-checked against exactly what THIS batch's own request offered,
    # never the whole run registry) -- see tests/test_t1_source_linking_
    # pipeline.py's TestAgentInputCarriesRealSourceIds for the dedicated
    # coverage of that change. This re-pin is honestly labeled as "the
    # baseline was updated to match this authorized code change" only -- it
    # is NOT, by itself, evidence that the change's behavior is correct or
    # that any human has reviewed/approved it; that is what the dedicated
    # test suites above are for. week2_llm.py, alpha_mapper.py, and
    # structure_extractor.py are untouched by this change; their own hashes
    # below are NOT updated by this entry (week2_llm.py/alpha_mapper.py's
    # current mismatch is separately-tracked, pre-existing drift from the
    # Alpha Mapper Authority Migration, unrelated to and predating this
    # round's own work -- not fixed here; reproduced directly via
    # map_claim_to_alpha(record, taxonomy, llm_gateway=None) returning
    # "unavailable" for ANY claim, independent of this round's changes).
    expected = {
        "comqutor_alpha/structure_engine/structured_output_adapter.py": "9e6995707bfa8ce4975eb58f5bb4b4fa6100a2bdbf8b50b5b4ad97c200215a3c",
        "comqutor_alpha/structure_engine/week2_llm.py": "5c9106a3e51c63ffbff957c2dee6778442cc503fb00eccba049f35e7669569b1",
        "comqutor_alpha/structure_engine/alpha_mapper.py": "506a228eb10e0b77b2058c9eaa327ae0ec44ba36b1515e5e6400187ffe65a6fd",
        "comqutor_alpha/structure_engine/structure_extractor.py": "5254cdf157c7d5ed88a7b06db34a9f0e3104259dde4fe5c52ecd922710fec416",
    }
    assert {path: _sha(path) for path in expected} == expected


def test_acceptance_fixtures_are_source_classified_and_traceable():
    payload = json.loads(
        (REPO_ROOT / "docs/audit_artifacts/phase1a/development_plan_acceptance_fixture_index.json").read_text()
    )
    assert payload["canonical_sha256"] == "cabf3381aaa633b7b88035ab6df2d7dac0def3d5ddd337f6384f23f4c439a8d9"
    assert all(item["classification"] == "SOURCE_FROZEN" for item in payload["fixtures"])
    assert payload["invented_source_frozen_examples"] == 0


def test_phase1a_has_no_files_under_historical_outputs():
    for root in (REPO_ROOT / "outputs/runs", REPO_ROOT / "outputs/replays"):
        assert not any("phase1a" in path.name.casefold() for path in root.rglob("*"))
