"""P4 phase 2 (2026-10-12): the small-sample evaluation preparation -- real sample, blind review packet, offline plan.

The sample tests read the ORIGINAL saved runs (skipped when the local run data is absent) and assert properties of the selection, never
a label. The plan tests use the saved real ledgers for the measured basis where they exist, and explicitly labelled TEST DATA records
for the arithmetic of the measurement. Nothing here calls a model or the network.
"""

from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from comqutor_alpha import alpha_relevance_eval_prep as ep
from comqutor_alpha.alpha_library.alpha_relevance_elements import (
    load_relevance_definitions,
    sha256_canonical_json,
)
from comqutor_alpha.structure_engine import alpha_relevance_llm as rl
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFS = load_relevance_definitions()
A9 = REPO_ROOT / "docs/audit_artifacts/round_source_linking_t0_t2/round36_t1_migration_20261010/followup_20261011/A9_criterion/alpha_tier_fixtures_v2.json"
RUNS = sorted(p for root in ep.SAVED_RUN_ROOTS if root.is_dir() for p in root.iterdir() if p.is_dir() and ep.is_original_run_dir(p))
STANCE_LEDGERS = [REPO_ROOT / "outputs/t4_runs/12591384-0b26-470d-a99d-a49c00be440b/llm_semantic_calls.jsonl",
                  REPO_ROOT / "outputs/t4_runs/fa642639-8d93-4f9a-9de1-2c4d789eade8/llm_semantic_calls.jsonl"]
needs_runs = pytest.mark.skipif(len(RUNS) < 50 or not A9.is_file(), reason="the saved runs / A9 material are not present (local data)")


@pytest.fixture(scope="module")
def pool():
    if len(RUNS) < 50 or not A9.is_file():
        pytest.skip("the saved runs / A9 material are not present (local data)")
    return ep.scan_candidates(RUNS, DEFS, a9_fixtures_path=A9)


@pytest.fixture(scope="module")
def manifest(pool):
    return ep.build_manifest(ep.select_sample(pool), DEFS, pool_runs=[r.name for r in RUNS])


# ----------------------------------------------------------------------------------------------------------- sample
@needs_runs
def test_the_sample_is_real_saved_pairs_with_their_source_identity_and_hashes(manifest):
    samples = manifest["samples"]
    assert manifest["sample_count"] == len(samples) == 60 and manifest["content_sha256"] == ep.manifest_content_sha256(manifest)
    assert [s["sample_id"] for s in samples] == [f"S{i:03d}" for i in range(1, 61)]
    assert len({(s["claim_id"], s["target_alpha_id"]) for s in samples}) == 60
    assert len({(s["claim_text_sha256"], s["target_alpha_id"]) for s in samples}) == 60
    for s in samples:
        source = ep._run_path(s["source_run_id"])  # noqa: SLF001
        assert source is not None and ep.is_original_run_dir(source)  # never a derived execution
        assert s["claim_text_sha256"] == rl.claim_text_sha256({"claim": s["claim_text"]})
        assert s["alpha_definition_sha256"] == DEFS[s["target_alpha_id"]].sha256
    assert ep.verify_manifest_sources(manifest) == []  # every pair re-read from its saved run: same text, same matched Alpha
    changed = [dict(s) for s in samples[:3]]
    changed[0]["target_alpha_id"] = next(a for a in DEFS if a != changed[0]["target_alpha_id"])
    changed[1]["claim_text"] = changed[1]["claim_text"] + " (edited)"
    changed[2]["source_run_id"] = "00000000-0000-0000-0000-000000000000"
    assert ep.verify_manifest_sources({"samples": changed}) == [
        {"sample_id": "S001", "problem": "SOURCE_MATCH_CHANGED"}, {"sample_id": "S002", "problem": "SOURCE_TEXT_CHANGED"},
        {"sample_id": "S003", "problem": "SOURCE_RUN_MISSING"}]


@needs_runs
def test_the_selection_respects_quotas_spread_and_reports_every_shortfall(pool, manifest):
    primary = Counter(s["selection"]["primary_stratum"] for s in manifest["samples"])
    assert all(primary[s] <= q for s, q in ep.DEFAULT_QUOTAS.items())
    assert {sh["stratum"] for sh in manifest["shortfalls"]} == {s for s, q in ep.DEFAULT_QUOTAS.items() if primary[s] < q}
    assert max(Counter(s["source_run_id"] for s in manifest["samples"]).values()) <= ep.MAX_PER_RUN
    alphas = Counter(s["target_alpha_id"] for s in manifest["samples"])
    assert all(alphas[a] >= ep.PER_ALPHA_MIN for a in {c.alpha_id for c in pool})
    # every documented ambiguity (A9 disputed item on its own saved Alpha) is in; selection is deterministic
    assert sorted(s["selection"]["a9_disputed_id"] for s in manifest["samples"] if s["selection"]["a9_disputed_id"]) == \
        sorted(d["id"] for d in json.loads(A9.read_text(encoding="utf-8"))["disputed"] if d["source"]["saved_matched_alpha"] == d["alpha_id"])
    again = ep.build_manifest(ep.select_sample(pool), DEFS, pool_runs=[r.name for r in RUNS])
    assert again["content_sha256"] == manifest["content_sha256"]
    # boundary coverage lists every boundary element, zero rows included (a gap is reported, never filled)
    coverage = manifest["boundary_element_coverage"]
    assert len(coverage["identity_dependent_strong"]) == 11 and len(coverage["shadowed_confirmation"]) == 7 and len(coverage["relation"]) == 4
    for elements in coverage.values():
        assert all(0 <= c["selected"] <= c["available"] or c["available"] == 0 and c["selected"] == 0 for c in elements.values())


def test_the_repeat_round_is_described_from_its_actual_batches():
    round1 = [{"batch_id": "B01", "alpha_id": "A001", "items": 4}, {"batch_id": "B02", "alpha_id": "A001", "items": 3},
              {"batch_id": "B03", "alpha_id": "A301", "items": 4}, {"batch_id": "B04", "alpha_id": "A301", "items": 2}]
    first_of_each = [dict(round1[0], batch_id="RB01"), dict(round1[2], batch_id="RB03")]
    assert ep.repeat_description(round1, first_of_each) == "identical repeat of the first round-1 batch of each Alpha (2 batches, 8 pairs; consistency)"
    assert ep.repeat_description(round1, [dict(round1[1], batch_id="RB02")]) == "identical repeat of round-1 batches B02 (1 batches, 3 pairs; consistency)"


def test_shortfalls_are_reported_not_filled():
    text = "TEST DATA: bookings accelerated sharply this quarter."
    candidate = ep.Candidate(run_id="TEST-DATA-run", run_path="", alpha_matches_sha256="0" * 64, claim_id="TEST-DATA-run:a:r:claim:1", alpha_id="A301",
                             ticker="NVDA", agent="a", text=text, text_sha256=rl.claim_text_sha256({"claim": text}),
                             features=ep.lexical_features(text, DEFS["A301"], ep.build_lexicon(DEFS["A301"])), strata={ep.STRATUM_ORDINARY})
    selection = ep.select_sample([candidate], quotas={ep.STRATUM_RELATION: 3, ep.STRATUM_ORDINARY: 2})
    assert [c.claim_id for c, _ in selection.selected] == [candidate.claim_id]
    assert selection.shortfalls == [{"stratum": ep.STRATUM_RELATION, "target": 3, "selected": 0, "available_unique_pairs": 0},
                                    {"stratum": ep.STRATUM_ORDINARY, "target": 2, "selected": 1, "available_unique_pairs": 1}]


# ----------------------------------------------------------------------------------------------------------- blind review packet
@needs_runs
def test_the_blind_sheet_shows_claim_and_definition_only_with_every_answer_empty(manifest):
    text = ep.render_csv(ep.blind_review_rows(manifest, DEFS), ep.REVIEW_COLUMNS)
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    assert list(rows[0]) == list(ep.REVIEW_COLUMNS) and len(rows) == 60
    by_id = {s["sample_id"]: s for s in manifest["samples"]}
    for row in rows:
        assert row["claim_text"] == by_id[row["sample_id"]]["claim_text"] and row["target_alpha_id"] == by_id[row["sample_id"]]["target_alpha_id"]
        assert row["review_status"] == ep.REVIEW_STATUS_PENDING
        assert all(row[c] == "" for c in ep.REVIEW_FILL_COLUMNS if c != "review_status")
    lowered = text.lower()
    for marker in (*[s.lower() for s in ep.STRATUM_PRIORITY], "draft", "a9", "simulated", "expected_tier", "matched_alpha", "fixture"):
        assert marker not in lowered, marker
    definitions = ep.render_definitions_markdown(manifest, DEFS)
    for alpha in {s["target_alpha_id"] for s in manifest["samples"]}:
        assert f"## {alpha}" in definitions and DEFS[alpha].sha256 in definitions
    assert "UNRESOLVED" in ep.REVIEW_INSTRUCTIONS and "CONFIRMED" in ep.REVIEW_INSTRUCTIONS


@needs_runs
def test_engineering_drafts_are_separate_marked_and_only_from_documented_material(manifest):
    drafts = ep.draft_label_rows(manifest, A9)
    assert {d["status"] for d in drafts} == {"ENGINEERING DRAFT - NOT A REFERENCE ANSWER"}
    with_tier = [d for d in drafts if d["engineering_draft_tier"]]
    assert with_tier and all(d["draft_source"].startswith("round-36 A9") for d in with_tier)
    assert all(d["draft_source"] == "none" for d in drafts if not d["engineering_draft_tier"])


# ----------------------------------------------------------------------------------------------------------- plan
def _stance_record(call_id: str, payload: dict[str, Any], *, input_tokens: int, output_tokens: int, mode: str = "live", identity: str | None = None,
                   returned_model: str | None = None) -> str:
    return json.dumps({"run_id": "TEST-DATA-run", "call_id": call_id, "task": ep.REFERENCE_TASK, "execution_mode": mode, "provider": "deepseek",
                       "model": "deepseek-v4-flash", "prompt_sha256": identity or Week2LLMGateway.prompt_identity_sha256(ep.REFERENCE_TASK),
                       "input_payload": payload, "validation_status": "accepted", "latency_ms": 20000.0,
                       "token_usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
                       "provider_response": {"raw_usage": {"completion_tokens_details": {"reasoning_tokens": output_tokens // 2}}, "finish_reason": "stop",
                                             **({"response_model": returned_model} if returned_model else {})},
                       "request_control": {"max_tokens_value": 1000, "request_model": "deepseek-v4-flash"}})


def test_the_measurement_rebuilds_prompts_exactly_and_deduplicates(tmp_path):
    payload = {"items": [{"evidence_id": "TEST-DATA", "text": "TEST DATA"}] * 4}
    prompt_chars = len(Week2LLMGateway._provider_prompt_prefix(ep.REFERENCE_TASK) + json.dumps(payload, ensure_ascii=False))  # noqa: SLF001
    lines = [_stance_record("c1", payload, input_tokens=prompt_chars // 4, output_tokens=4000, returned_model="TEST-DATA-served-name"),
             _stance_record("c2", payload, input_tokens=prompt_chars // 4, output_tokens=1200),  # 1200 billed against a cap of 1000
             _stance_record("c3", payload, input_tokens=10, output_tokens=10, mode="test"),  # not live: ignored
             _stance_record("c4", payload, input_tokens=10, output_tokens=10, identity="0" * 64)]  # another prompt identity: excluded
    ledger = tmp_path / "TEST-DATA-ledger.jsonl"
    ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
    measured = ep.measure_reference_ledgers([ledger, ledger], [ledger, ledger])  # the same file twice: counted once
    stance = measured["stance"]
    assert stance["calls"] == 2 and stance["excluded"] == {"prompt_identity_differs": 1}
    assert stance["chars_per_input_token"]["median"] == round(prompt_chars / (prompt_chars // 4), 3)
    assert stance["output_tokens_per_item"]["max"] == 1000.0 and stance["reasoning_share_of_output"]["median"] == 0.5
    assert stance["latency_seconds_per_item"]["median"] == 5.0
    cap = measured["max_tokens_enforcement"]
    assert cap["calls"] == 3 and cap["calls_over_cap"] == 2  # c1 and c2 exceed 1000 (the c4 identity does not matter here)
    # every live call of the ledger counts once for the names: requested vs. what the provider returned (c3 is not live)
    assert measured["model_names_observed"]["pairs"] == [
        {"requested": "deepseek-v4-flash", "returned_by_provider": None, "calls": 2},
        {"requested": "deepseek-v4-flash", "returned_by_provider": "TEST-DATA-served-name", "calls": 1}]


def _test_manifest() -> dict[str, Any]:
    texts = [("TEST DATA: bookings accelerated.", "A301"), ("TEST DATA: margins held.", "A301"), ("TEST DATA: revenue grew.", "A301"),
             ("TEST DATA: guidance raised.", "A301"), ("TEST DATA: EPS revised up.", "A301"), ("TEST DATA: retail chatter.", "A601"),
             ("TEST DATA: the Fed held.", "A001")]
    samples = [{"sample_id": f"S{i:03d}", "claim_id": f"TEST-DATA-run:a:r:claim:{i}", "ticker": "NVDA", "target_alpha_id": alpha, "claim_text": text,
                "claim_text_sha256": rl.claim_text_sha256({"claim": text}), "alpha_definition_sha256": DEFS[alpha].sha256,
                "selection": {"primary_stratum": ep.STRATUM_ORDINARY}} for i, (text, alpha) in enumerate(texts, start=1)]
    body = {"schema": ep.SAMPLE_SCHEMA, "test_data": True, "sample_count": len(samples), "samples": samples}
    return {**body, "content_sha256": sha256_canonical_json(body)}


TEST_REFERENCE = {"stance": {"chars_per_input_token": {"median": 4.0, "min": 3.5, "max": 4.5}, "output_tokens_per_item": {"median": 800.0, "max": 1300.0},
                             "latency_seconds_per_item": {"median": 10.0, "max": 20.0}}, "max_tokens_enforcement": {}, "sources": []}


def test_the_plan_counts_every_request_repeats_identical_payloads_and_freezes_pending_thresholds():
    manifest = _test_manifest()
    plan = ep.build_plan(manifest, DEFS, manifest_file_sha256="0" * 64, reference=TEST_REFERENCE, provider="deepseek", model="deepseek-v4-flash",
                         batch_size=4, repeat_every=2, timeout_seconds=300.0, max_output_tokens=16384, repo_root=REPO_ROOT)
    round1, round2 = plan["rounds"][0]["batches"], plan["rounds"][1]["batches"]
    assert [b["sample_ids"] for b in round1] == [["S007"], ["S001", "S002", "S003", "S004"], ["S005"], ["S006"]]  # by Alpha, then chunked
    assert [b["batch_id"] for b in round2] == ["RB01", "RB03"] and [b["payload_sha256"] for b in round2] == [round1[0]["payload_sha256"], round1[2]["payload_sha256"]]
    # B03 is the SECOND batch of A301 here, so the plan names the batches instead of claiming "the first batch of each Alpha"
    assert plan["rounds"][1]["purpose"] == "identical repeat of round-1 batches B01, B03 (2 batches, 2 pairs; consistency)"
    assert plan["requests"]["repeat_batches"] == [{"batch_id": "RB01", "repeats": "B01", "alpha_id": "A001", "pairs": 1},
                                                  {"batch_id": "RB03", "repeats": "B03", "alpha_id": "A301", "pairs": 1}]
    assert plan["model_identity"]["request_model"] == "deepseek-v4-flash" and "does not pin" in plan["model_identity"]["pinning"]
    assert plan["request_cap"] == plan["requests"]["total"] == 6 and plan["requests"]["repeat_subset_samples"] == ["S005", "S007"]
    assert plan["plan_sha256"] == ep.plan_content_sha256(plan) and plan["status"] == "PLANNED_NOT_EXECUTED"
    noted = ep.build_plan(manifest, DEFS, manifest_file_sha256="0" * 64, reference=TEST_REFERENCE, provider="deepseek", model="deepseek-v4-flash",
                          batch_size=4, repeat_every=2, timeout_seconds=300.0, max_output_tokens=16384, repo_root=REPO_ROOT,
                          model_identity_note={"documented_serving_model": {"name": "TEST-DATA"}})
    assert noted["model_identity"]["documented_serving_model"] == {"name": "TEST-DATA"} and noted["rounds"] == plan["rounds"]
    assert plan["quality_thresholds"]["status"] == "PENDING_OWNER_CONFIRMATION"
    assert plan["quality_thresholds_sha256"] == sha256_canonical_json(plan["quality_thresholds"])
    assert plan["stop_conditions"]["request_cap"] == 6 and plan["stop_conditions"]["max_retries"] == 0
    assert plan["stop_conditions"]["wall_clock_limit_minutes"] == 6 * 300 // 60 + 10
    total = plan["estimates"]["total"]
    chars = sum(b["prompt_chars"] for r in plan["rounds"] for b in r["batches"])
    assert total["input_tokens"] == {"central": round(chars / 4.0), "low": round(chars / 4.5), "high": round(chars / 3.5)}
    assert total["output_tokens"]["hard_bound"] == 6 * 16384 and total["output_tokens"]["central"] == round(9 * 800)
    assert plan["cost_estimate"]["hard_bound_usd_peak"] == ep.usd([0.30, 1.20], total["input_tokens"]["high"], 6 * 16384)
    assert set(plan["code_identity"]["files"]) == set(ep.CODE_IDENTITY_FILES)
    assert any("SIMULATED" in u for u in plan["unknowns"])  # phase 1's simulated calls are never a basis
    auth = ep.authorization_template(plan)
    assert (auth["live_authorized"], auth["max_cost_usd"], auth["quality_thresholds_confirmed"]) == (False, None, False)
    assert auth["max_requests"] == 6 and auth["plan_sha256"] == plan["plan_sha256"]
    rehearsal = ep.rehearsal_authorization(plan, authorized_by="TEST", authorized_at="2026-10-12T00:00:00+00:00", valid_until="2026-10-13T00:00:00+00:00")
    assert rehearsal["mode"] == "SIMULATED_REHEARSAL" and rehearsal["live_authorized"] is False


@pytest.mark.skipif(not all(p.is_file() for p in STANCE_LEDGERS), reason="the saved NVDA Fresh Run ledgers are not present (local data)")
def test_the_real_basis_is_measured_from_saved_live_ledgers():
    measured = ep.measure_reference_ledgers(STANCE_LEDGERS, [])
    names = {p["returned_by_provider"] for p in measured["model_names_observed"]["pairs"]}
    assert {p["requested"] for p in measured["model_names_observed"]["pairs"]} == {"deepseek-v4-flash"} and "deepseek-flash" in names
    stance = measured["stance"]
    assert measured["reference_provider_models"] == ["deepseek/deepseek-v4-flash"] and stance["calls"] == 37 and stance["excluded"] == {}
    assert 3.5 <= stance["chars_per_input_token"]["min"] <= stance["chars_per_input_token"]["median"] <= stance["chars_per_input_token"]["max"] <= 4.8
    assert stance["output_tokens_per_item"]["median"] > 0 and stance["reasoning_share_of_output"]["median"] > 0.5


# ----------------------------------------------------------------------------------------------------------- operator CLI
@needs_runs
def test_the_offline_cli_builds_the_packet_and_plan_into_new_folders_only(tmp_path, manifest):
    manifest_path = tmp_path / "sample_manifest.json"
    ep.write_json(manifest_path, manifest)
    cli = [sys.executable, str(REPO_ROOT / "scripts" / "alpha_relevance_eval.py")]
    review = subprocess.run([*cli, "build-review", "--manifest", str(manifest_path), "--out-dir", str(tmp_path / "out")], capture_output=True, text=True, check=False)
    assert review.returncode == 0, review.stderr
    assert sorted(p.name for p in (tmp_path / "out" / "review").iterdir()) == ["README_盲审说明.md", "blind_review_sheet_A.csv", "blind_review_sheet_B.csv", "review_definitions.md"]
    assert (tmp_path / "out" / "engineering_draft" / "engineering_draft_labels_DRAFT.csv").is_file()
    again = subprocess.run([*cli, "build-review", "--manifest", str(manifest_path), "--out-dir", str(tmp_path / "out")], capture_output=True, text=True, check=False)
    assert again.returncode != 0 and "FileExistsError" in again.stderr  # never overwrites an earlier packet
    tampered = dict(manifest, sample_count=59)
    ep.write_json(tmp_path / "tampered.json", tampered)
    refused = subprocess.run([*cli, "build-plan", "--manifest", str(tmp_path / "tampered.json"), "--out-dir", str(tmp_path / "p")], capture_output=True, text=True, check=False)
    assert refused.returncode == 1 and json.loads(refused.stdout)["error_code"] == "MANIFEST_HASH_MISMATCH"
