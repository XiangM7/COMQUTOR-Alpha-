#!/usr/bin/env python3
"""Round 18: re-qualify evidence eligibility from ALREADY-SAVED results and recompute through the production chain.

ZERO Provider / search / data-fetch calls. The new `requal-*` execution is based on the recovery run
(`recovery-20261007T053635Z-26d6cd1a`) with the original research run recorded as root. It reuses the saved
classification (alpha_matches verbatim, including the deterministic stance -- direction was never obtained) and the saved
content verification (structured records verbatim). The only artifact that differs is a COPY of source_registry.json, which
gains a versioned `availability` record on each undated live financial data snapshot, produced by a verified transform;
the original registry is never touched. Eligibility is then decided by the (fixed) production function and the existing
scoring / exposure / conflict chain recomputes.

--dry-run  : eligibility before/after for every claim, no write.
--execute  : build the execution (writes only the new directory and its rows in the isolated test database).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import socket
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))
HERE = Path(__file__).resolve().parent

ROOT_RUN_ID = "c904d4cc-dc09-495c-aec5-b056979948e1"
PARENT_RUN_ID = "recovery-20261007T053635Z-26d6cd1a"
OUTPUT_ROOT = (REPO_ROOT / "outputs" / "runs").resolve()
ROOT_DIR, PARENT_DIR = OUTPUT_ROOT / ROOT_RUN_ID, OUTPUT_ROOT / PARENT_RUN_ID
LOOP_ALPHAS = None  # all MVP alphas


def jload(path: Path):
    return json.loads(Path(path).read_text())


def load_inputs():
    return {
        "metadata": jload(ROOT_DIR / "metadata.json"),
        "records": jload(PARENT_DIR / "structured_agent_outputs.json")["records"],
        "registry": jload(PARENT_DIR / "source_registry.json"),
        "matches_payload": jload(PARENT_DIR / "alpha_matches.json"),
    }


# ---------------------------------------------------------------------------
# The verified registry transform + independent time evidence
# ---------------------------------------------------------------------------


def time_evidence(inputs) -> dict:
    """NON-gating corroboration read from the ORIGINAL run's raw records: the gate itself depends only on the registry's own
    fields (so a future run is judged identically); this shows the records do not contradict it."""
    metadata = inputs["metadata"]
    calls = [json.loads(line) for line in (ROOT_DIR / "tradingagents_llm_calls.jsonl").read_text().splitlines() if line.strip()]
    raw = jload(ROOT_DIR / "raw_agent_outputs.json")
    raw_text = {a["agent"]: a.get("raw_output") or "" for a in raw["agent_outputs"]}
    registry_written = {s.get("retrieved_at") for s in inputs["registry"]["sources"]}
    per_source = {}
    for source in inputs["registry"]["sources"]:
        if source.get("published_at") or source.get("source_type") != "financial":
            continue
        per_source[source["source_id"]] = {
            "title": source.get("title"),
            "observation_date_period_end_NOT_USED": source.get("observation_date"),
            "fragment_marker_present_in_saved_fundamentals_report": (source.get("fragment_id") or "") in raw_text.get("fundamental_agent", ""),
            "sha256_of_saved_excerpt_equals_content_hash": hashlib.sha256((source.get("excerpt") or "").encode()).hexdigest() == source.get("content_hash"),
        }
    return {
        "analysis_date": metadata["analysis_date"],
        "raw_outputs_and_metadata_created_at": metadata["created_at"],
        "registry_retrieved_at_values": sorted(registry_written),
        "registry_retrieved_at_is": "the writer's own UTC clock at output-save time (tradingagents_output_writer: retrieved_at=created_at), AFTER the agent graph finished -- an upper bound on every capture moment, not the per-tool-call time",
        "tradingagents_llm_call_window_utc": {"first_started_at": calls[0]["started_at"], "last_completed_at": calls[-1]["completed_at"], "calls": len(calls)},
        "fundamentals_snapshot_exact_capture_time": {
            "title_time_local_naive": "2026-10-06 10:37:04.790990 (America/Los_Angeles)", "as_utc": "2026-10-06T17:37:04.790990Z",
            "next_llm_call_started_at": next((c["started_at"] for c in calls if c["started_at"] > "2026-10-06T17:37:04.79"), None),
            "note": "the only source with an exact capture time; it falls inside the same call window and 8 ms before the LLM call that consumed it",
        },
        "undated_financial_snapshots": per_source,
    }


def make_registry_transform(analysis_date: str):
    from comqutor_alpha.source_provenance import (
        AVAILABILITY_ANNOTATION_DERIVED_FROM_SAVED_REGISTRY, SOURCE_AVAILABILITY_VERSION, annotate_sources_availability)

    def transform(registry):
        original_sources = registry["sources"]
        annotated, summary = annotate_sources_availability(
            original_sources, analysis_date, mode=AVAILABILITY_ANNOTATION_DERIVED_FROM_SAVED_REGISTRY)
        stripped = [{k: v for k, v in s.items() if k != "availability"} for s in annotated]
        out = dict(registry)
        out["sources"] = annotated
        return out, {
            "transformation": "availability_annotated",
            "version": SOURCE_AVAILABILITY_VERSION,
            "annotation_mode": AVAILABILITY_ANNOTATION_DERIVED_FROM_SAVED_REGISTRY,
            "analysis_date_used": analysis_date,
            "current_time_used": False,
            "content_equal_apart_from_declared_additions": stripped == original_sources,
            "declared_additions": "sources[*].availability on undated live financial data snapshots only",
            "published_at_untouched": all(a.get("published_at") == o.get("published_at") for a, o in zip(annotated, original_sources)),
            "annotated_sources": summary,
        }

    return transform


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


def eligibility_rows(inputs):
    from comqutor_alpha.source_provenance import (AVAILABILITY_ANNOTATION_DERIVED_FROM_SAVED_REGISTRY, annotate_sources_availability,
                                                  compute_verified_support_eligibility)
    sources_before = inputs["registry"]["sources"]
    sources_after, _ = annotate_sources_availability(sources_before, inputs["metadata"]["analysis_date"], mode=AVAILABILITY_ANNOTATION_DERIVED_FROM_SAVED_REGISTRY)
    # "before" = the PRE-CHANGE code's saved result for every claim (before_eligibility_all_975_claims.json, taken before any edit);
    # "intermediate" = the fixed binding logic on the UNCHANGED registry; "after" = fixed logic on the annotated registry.
    before_saved = jload(HERE / "before_eligibility_all_975_claims.json")
    inputs["intermediate"] = {r["claim_id"]: compute_verified_support_eligibility(r, sources_before) for r in inputs["records"]}
    out = {}
    for record in inputs["records"]:
        out[record["claim_id"]] = (before_saved[record["claim_id"]], compute_verified_support_eligibility(record, sources_after))
    return out


def run_dry_run() -> int:
    inputs = load_inputs()
    rows = eligibility_rows(inputs)
    moved = {cid: (b["reason_code"], a["reason_code"]) for cid, (b, a) in rows.items() if b["reason_code"] != a["reason_code"]}
    print("claims whose eligibility changes (original code -> fixed code + availability):", len(moved), dict(Counter(moved.values())))
    print("binding fix alone (registry unchanged):", dict(Counter((rows[c][0]["reason_code"], inputs["intermediate"][c]["reason_code"]) for c in moved)))
    print("eligible before:", sum(1 for b, _ in rows.values() if b["eligible"]), "after:", sum(1 for _, a in rows.values() if a["eligible"]))
    print("no write was made")
    return 0


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


class ZeroCallTrap:
    """Fails closed on any Provider path while the recompute runs, and counts attempts."""

    def __enter__(self):
        import httpx

        from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

        self.attempts: list[str] = []
        self._saved = []

        def block(name):
            def _raise(*a, **k):
                self.attempts.append(name)
                raise AssertionError(f"zero-call guard: {name}")
            return _raise

        def patch(obj, attr, name):
            self._saved.append((obj, attr, getattr(obj, attr)))
            setattr(obj, attr, block(name))

        patch(httpx.HTTPTransport, "handle_request", "httpx.HTTPTransport.handle_request")
        patch(httpx.Client, "send", "httpx.Client.send")
        for method in ("invoke_json", "invoke_json_with_trace", "invoke_prebuilt_json_prompt"):
            patch(Week2LLMGateway, method, f"Week2LLMGateway.{method}")
        real_getaddrinfo = socket.getaddrinfo

        def guarded_getaddrinfo(host, *a, **k):
            if str(host) not in ("localhost", "127.0.0.1", "::1"):
                self.attempts.append(f"getaddrinfo:{host}")
                raise AssertionError(f"zero-call guard: DNS lookup for {host}")
            return real_getaddrinfo(host, *a, **k)

        self._saved.append((socket, "getaddrinfo", real_getaddrinfo))
        socket.getaddrinfo = guarded_getaddrinfo
        return self

    def __exit__(self, *exc):
        for obj, attr, original in reversed(self._saved):
            setattr(obj, attr, original)
        return False


def run_execute(execution_id: str | None) -> int:
    from dotenv import dotenv_values
    from sqlalchemy.engine import make_url

    test_url = dotenv_values(REPO_ROOT / ".env").get("COMQUTOR_TEST_DATABASE_URL")
    name = make_url(test_url).database if test_url else ""
    if not name or not name.endswith("_test"):
        print("BLOCKED: no isolated *_test database configured", file=sys.stderr)
        return 1
    os.environ["COMQUTOR_DATABASE_URL"] = test_url
    os.environ["COMQUTOR_REQUIRE_DATABASE_NAME"] = name

    from comqutor_alpha.classification_recovery import (
        REQUALIFICATION_EXECUTION_MODE, REQUALIFICATION_EXECUTION_TYPE, REQUALIFICATION_LINEAGE_FILENAME,
        finalize_classification_recovery_execution, new_requalification_execution_id, snapshot_directory_hashes)
    from comqutor_alpha.storage.db.repository import build_write_repository_from_env

    execution_id = execution_id or new_requalification_execution_id()
    if not execution_id.startswith("requal-") or (OUTPUT_ROOT / execution_id).exists():
        print(f"BLOCKED: bad or existing execution id {execution_id}", file=sys.stderr)
        return 1
    inputs = load_inputs()
    rows = eligibility_rows(inputs)
    changed = {cid for cid, (b, a) in rows.items() if b["reason_code"] != a["reason_code"]}
    claim_sources = {cid: ("eligibility_requalified" if cid in changed else "unchanged_from_parent") for cid in rows}
    protected_before = {"root": snapshot_directory_hashes(ROOT_DIR), "parent": snapshot_directory_hashes(PARENT_DIR)}
    (HERE / "root_run_hashes_before_requalification.json").write_text(json.dumps(protected_before["root"], indent=1, sort_keys=True))
    (HERE / "parent_run_hashes_before_requalification.json").write_text(json.dumps(protected_before["parent"], indent=1, sort_keys=True))
    evidence = time_evidence(inputs)
    repository = build_write_repository_from_env(str(OUTPUT_ROOT))
    payload = copy.deepcopy(inputs["matches_payload"])

    with ZeroCallTrap() as trap:
        finalized = finalize_classification_recovery_execution(
            PARENT_RUN_ID, execution_id, assembled_alpha_matches=payload,
            recovery_provenance={"checkpoint_origin": "real", "claim_sources": claim_sources,
                                 "note": "alpha_matches / structured records reused verbatim; only a copy of the registry is annotated"},
            output_root=OUTPUT_ROOT, graph_repository=repository,
            execution_type=REQUALIFICATION_EXECUTION_TYPE, execution_mode=REQUALIFICATION_EXECUTION_MODE,
            lineage_filename=REQUALIFICATION_LINEAGE_FILENAME, assembled_transformation="reused_verbatim_from_parent", root_run_id=ROOT_RUN_ID,
            artifact_transforms={"source_registry.json": make_registry_transform(inputs["metadata"]["analysis_date"])},
            lineage_extras={"completeness": {
                "classification": "inherited verbatim: 162 matched, 748 model NONE (incl. the 2 original), 64 model selections overridden to no_match by mapper gates, 1 timed out (unresolved, not retried)",
                "direction": "NOT obtained (the one attempt timed out at 45 s); stance in alpha_matches is the production deterministic classifier, not a model result",
                "downstream_evaluation": "recomputed by the production chain from the saved results; see evidence_eligibility_requalification.json",
            }, "time_evidence": evidence})
    zero_call = {"attempted_provider_or_network_calls": len(trap.attempts), "attempts": trap.attempts}
    print("finalized:", json.dumps(finalized, default=str)[:600])
    if finalized.get("status") != "ok":
        return 3

    sys.path.insert(0, str(HERE))
    from analyze_requalification import build_results  # noqa: E402

    results = build_results(execution_id, inputs, rows, evidence, zero_call)
    from comqutor_alpha.api.artifact_export import build_and_write_artifact_manifest
    from comqutor_alpha.classification_recovery import REQUALIFICATION_RESULTS_FILENAME
    from comqutor_alpha.storage.file_store import save_json_record

    save_json_record(execution_id, REQUALIFICATION_RESULTS_FILENAME, results, output_root=OUTPUT_ROOT)
    build_and_write_artifact_manifest(run_id=execution_id, ticker=inputs["metadata"]["ticker"], output_root=OUTPUT_ROOT)
    after = {"root": snapshot_directory_hashes(ROOT_DIR) == protected_before["root"], "parent": snapshot_directory_hashes(PARENT_DIR) == protected_before["parent"]}
    (HERE / f"requalification_execution_report_{execution_id}.json").write_text(json.dumps({
        "execution_id": execution_id, "finalized": finalized, "zero_call": zero_call, "protected_runs_unchanged": after,
        "summary": results["summary"]}, indent=2, default=str))
    print("protected runs unchanged:", after, "| zero-call attempts:", zero_call["attempted_provider_or_network_calls"])
    print("execution_id:", execution_id)
    return 0 if all(after.values()) and zero_call["attempted_provider_or_network_calls"] == 0 else 4


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--execution-id", default=None)
    args = parser.parse_args()
    sys.exit(run_execute(args.execution_id) if args.execute else run_dry_run())
