"""Alpha Memory Implementation Step 3 -- historical observation +
recurrence memory tests (atomic edge phi as the primary matching unit;
whole-Alpha aggregate fingerprint retained only as a secondary diagnostic;
instability-signal diagnostics; positive-observation-only recurrence).

Pure, offline, deterministic. Zero Provider calls, zero TradingAgents
calls. Every run fixture is synthetic, written to tmp_path.
"""

from __future__ import annotations

import json

from comqutor_alpha.memory.history_reader import (
    build_phi_structures,
    detect_alpha_attribution_variance,
    detect_edge_type_variance,
    find_prior_phi_edge_observations,
    find_ticker_run_ids,
    load_aggregate_fingerprints_for_run,
    load_phi_edges_for_run,
    summarize_alpha_memory,
    summarize_phi_edge_history,
)


def _write_json(path, name, payload):
    (path / name).write_text(json.dumps(payload), encoding="utf-8")


def _edge(source, target, edge_type, alpha_ids):
    return {"source": source, "target": target, "edge_type": edge_type, "alpha_ids": list(alpha_ids)}


def _write_run(
    tmp_path, run_id, *, ticker, edges, created_at=None, taxonomy_sha256="deadbeef", artifact_completeness=None
):
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    metadata = {"run_id": run_id, "ticker": ticker}
    if created_at is not None:
        metadata["created_at"] = created_at
    _write_json(run_dir, "metadata.json", metadata)
    _write_json(run_dir, "structure_graph.json", {"ticker": ticker, "run_id": run_id, "edges": edges})
    _write_json(
        run_dir,
        "tradingagents_comqutor_vocabulary_snapshot.json",
        {"taxonomy_version": "structure_engine.factor_aliases.v1", "taxonomy_sha256": taxonomy_sha256},
    )
    if artifact_completeness is not None:
        _write_json(run_dir, "artifact_manifest.json", {"artifact_completeness": artifact_completeness})
    return run_dir


_ONE_EDGE = [_edge("ai_demand", "gpu_shortage", "causal", ["A101"])]


# ---------------------------------------------------------------------------
# 1. phi absent from all prior runs -> has_prior_observation False,
# is_recurring False, prior_observation_count 0.
# ---------------------------------------------------------------------------


def test_phi_absent_from_all_prior_runs(tmp_path):
    _write_run(tmp_path, "run-1", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-01T00:00:00Z")
    phi = load_phi_edges_for_run(run_id="run-1", output_root=tmp_path)
    summary = summarize_phi_edge_history(phi_edge=phi[0], current_run_id="run-1", output_root=tmp_path)
    assert summary["has_prior_observation"] is False
    assert summary["is_recurring"] is False
    assert summary["prior_observation_count"] == 0
    assert summary["total_observation_count"] == 1


# ---------------------------------------------------------------------------
# 2. phi appears in one prior run -> recurring True, count 1.
# ---------------------------------------------------------------------------


def test_phi_appears_in_one_prior_run_is_recurring(tmp_path):
    _write_run(tmp_path, "run-1", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-01T00:00:00Z")
    _write_run(tmp_path, "run-2", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-10T00:00:00Z")
    phi2 = load_phi_edges_for_run(run_id="run-2", output_root=tmp_path)
    summary = summarize_phi_edge_history(phi_edge=phi2[0], current_run_id="run-2", output_root=tmp_path)
    assert summary["is_recurring"] is True
    assert summary["has_prior_observation"] is True
    assert summary["prior_observation_count"] == 1
    assert summary["total_observation_count"] == 2


# ---------------------------------------------------------------------------
# 3. phi appears in N distinct prior runs -> count N.
# ---------------------------------------------------------------------------


def test_phi_appears_in_n_distinct_prior_runs(tmp_path):
    for i in range(1, 4):
        _write_run(tmp_path, f"run-{i}", ticker="NVDA", edges=_ONE_EDGE, created_at=f"2026-08-{i:02d}T00:00:00Z")
    _write_run(tmp_path, "run-4", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-04T00:00:00Z")
    phi4 = load_phi_edges_for_run(run_id="run-4", output_root=tmp_path)
    summary = summarize_phi_edge_history(phi_edge=phi4[0], current_run_id="run-4", output_root=tmp_path)
    assert summary["prior_observation_count"] == 3
    assert set(summary["prior_run_ids"]) == {"run-1", "run-2", "run-3"}


# ---------------------------------------------------------------------------
# 4. Duplicate same phi within one run counts once (dedup by (run_id, phi_id)).
# ---------------------------------------------------------------------------


def test_duplicate_edge_producing_the_same_phi_within_one_run_counts_once(tmp_path):
    # Two structurally-duplicate edges (same source/type/target/alpha) --
    # compute_phi_edges already de-duplicates within a run; this proves
    # find_prior_phi_edge_observations ALSO never double-counts a run.
    duplicate_edges = [
        _edge("ai_demand", "gpu_shortage", "causal", ["A101"]),
        _edge("ai_demand", "gpu_shortage", "causal", ["A101"]),
    ]
    _write_run(tmp_path, "run-1", ticker="NVDA", edges=duplicate_edges, created_at="2026-08-01T00:00:00Z")
    _write_run(tmp_path, "run-2", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-10T00:00:00Z")

    phi1 = load_phi_edges_for_run(run_id="run-1", output_root=tmp_path)
    assert len(phi1) == 1  # already deduplicated at the identity layer

    phi2 = load_phi_edges_for_run(run_id="run-2", output_root=tmp_path)
    observations = find_prior_phi_edge_observations(
        phi_id=phi2[0]["phi_id"], ticker="NVDA", current_run_id="run-2", output_root=tmp_path
    )
    assert len(observations) == 1  # one run, counted once -- never twice for its duplicate edges
    assert observations[0]["run_id"] == "run-1"


# ---------------------------------------------------------------------------
# 5. Current run never counts as history.
# ---------------------------------------------------------------------------


def test_current_run_never_counts_as_its_own_history(tmp_path):
    _write_run(tmp_path, "run-1", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-01T00:00:00Z")
    phi = load_phi_edges_for_run(run_id="run-1", output_root=tmp_path)
    observations = find_prior_phi_edge_observations(
        phi_id=phi[0]["phi_id"], ticker="NVDA", current_run_id="run-1", output_root=tmp_path
    )
    assert observations == []


def test_find_ticker_run_ids_excludes_current_run_and_filters_by_ticker(tmp_path):
    _write_run(tmp_path, "run-nvda-1", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-01T00:00:00Z")
    _write_run(tmp_path, "run-nvda-2", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-10T00:00:00Z")
    _write_run(tmp_path, "run-amd-1", ticker="AMD", edges=_ONE_EDGE, created_at="2026-08-05T00:00:00Z")
    result = find_ticker_run_ids(ticker="NVDA", output_root=tmp_path, exclude_run_id="run-nvda-2")
    assert result == ["run-nvda-1"]


# ---------------------------------------------------------------------------
# 6/7/8/9. Different ticker/alpha/edge_type/taxonomy does not count.
# ---------------------------------------------------------------------------


def test_different_ticker_does_not_count(tmp_path):
    _write_run(tmp_path, "run-nvda", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-01T00:00:00Z")
    _write_run(tmp_path, "run-amd", ticker="AMD", edges=_ONE_EDGE, created_at="2026-08-10T00:00:00Z")
    phi_amd = load_phi_edges_for_run(run_id="run-amd", output_root=tmp_path)
    summary = summarize_phi_edge_history(phi_edge=phi_amd[0], current_run_id="run-amd", output_root=tmp_path)
    assert summary["is_recurring"] is False  # NVDA's identical edge never counts for AMD


def test_different_alpha_does_not_count(tmp_path):
    _write_run(tmp_path, "run-1", ticker="NVDA", edges=[_edge("ai_demand", "gpu_shortage", "causal", ["A101"])], created_at="2026-08-01T00:00:00Z")
    _write_run(tmp_path, "run-2", ticker="NVDA", edges=[_edge("ai_demand", "gpu_shortage", "causal", ["A103"])], created_at="2026-08-10T00:00:00Z")
    phi2 = load_phi_edges_for_run(run_id="run-2", output_root=tmp_path)
    summary = summarize_phi_edge_history(phi_edge=phi2[0], current_run_id="run-2", output_root=tmp_path)
    assert summary["is_recurring"] is False


def test_different_edge_type_does_not_count(tmp_path):
    _write_run(tmp_path, "run-1", ticker="NVDA", edges=[_edge("ai_demand", "gpu_shortage", "causal", ["A101"])], created_at="2026-08-01T00:00:00Z")
    _write_run(tmp_path, "run-2", ticker="NVDA", edges=[_edge("ai_demand", "gpu_shortage", "supportive", ["A101"])], created_at="2026-08-10T00:00:00Z")
    phi2 = load_phi_edges_for_run(run_id="run-2", output_root=tmp_path)
    summary = summarize_phi_edge_history(phi_edge=phi2[0], current_run_id="run-2", output_root=tmp_path)
    assert summary["is_recurring"] is False


def test_different_taxonomy_version_does_not_count(tmp_path):
    _write_run(tmp_path, "run-1", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-01T00:00:00Z", taxonomy_sha256="old-hash")
    _write_run(tmp_path, "run-2", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-10T00:00:00Z", taxonomy_sha256="new-hash")
    phi2 = load_phi_edges_for_run(run_id="run-2", output_root=tmp_path)
    summary = summarize_phi_edge_history(phi_edge=phi2[0], current_run_id="run-2", output_root=tmp_path)
    assert summary["is_recurring"] is False


# ---------------------------------------------------------------------------
# 10/11/12. Chronology: real timestamps only, never fabricated.
# ---------------------------------------------------------------------------


def test_first_seen_comes_from_earliest_actual_metadata(tmp_path):
    _write_run(tmp_path, "run-1", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-01T00:00:00Z")
    _write_run(tmp_path, "run-2", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-10T00:00:00Z")
    _write_run(tmp_path, "run-3", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-20T00:00:00Z")
    phi3 = load_phi_edges_for_run(run_id="run-3", output_root=tmp_path)
    summary = summarize_phi_edge_history(phi_edge=phi3[0], current_run_id="run-3", output_root=tmp_path)
    assert summary["first_seen"] == "2026-08-01T00:00:00Z"


def test_first_seen_for_a_first_seen_structure_is_the_current_run_own_timestamp(tmp_path):
    """No prior observation exists -- first_seen must be THIS run's own
    real timestamp (this run genuinely is the first sighting), never None
    and never a different run's timestamp."""
    _write_run(tmp_path, "run-1", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-01T00:00:00Z")
    phi1 = load_phi_edges_for_run(run_id="run-1", output_root=tmp_path)
    summary = summarize_phi_edge_history(phi_edge=phi1[0], current_run_id="run-1", output_root=tmp_path)
    assert summary["first_seen"] == "2026-08-01T00:00:00Z"
    assert summary["current_seen_at"] == "2026-08-01T00:00:00Z"
    assert summary["last_seen_prior"] is None


def test_last_seen_prior_comes_from_latest_actual_prior_observation(tmp_path):
    _write_run(tmp_path, "run-1", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-01T00:00:00Z")
    _write_run(tmp_path, "run-2", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-10T00:00:00Z")
    _write_run(tmp_path, "run-3", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-20T00:00:00Z")
    phi3 = load_phi_edges_for_run(run_id="run-3", output_root=tmp_path)
    summary = summarize_phi_edge_history(phi_edge=phi3[0], current_run_id="run-3", output_root=tmp_path)
    assert summary["last_seen_prior"] == "2026-08-10T00:00:00Z"  # NOT run-3's own timestamp
    assert summary["current_seen_at"] == "2026-08-20T00:00:00Z"


def test_missing_timestamps_are_not_fabricated(tmp_path):
    _write_run(tmp_path, "run-1", ticker="NVDA", edges=_ONE_EDGE, created_at=None)
    _write_run(tmp_path, "run-2", ticker="NVDA", edges=_ONE_EDGE, created_at=None)
    phi2 = load_phi_edges_for_run(run_id="run-2", output_root=tmp_path)
    summary = summarize_phi_edge_history(phi_edge=phi2[0], current_run_id="run-2", output_root=tmp_path)
    assert summary["prior_run_ids"] == ["run-1"]
    assert summary["is_recurring"] is True  # recurrence never depends on timestamp availability
    assert summary["first_seen"] is None
    assert summary["last_seen_prior"] is None
    assert summary["current_seen_at"] is None


# ---------------------------------------------------------------------------
# 13. Atomic recurrence can exist while aggregate fingerprint differs.
# ---------------------------------------------------------------------------


def test_aggregate_fingerprints_differ_while_atomic_phi_still_matches(tmp_path):
    run1_edges = [
        _edge("ai_capex", "gpu_demand", "causal", ["A101"]),
        _edge("gpu_demand", "nvda_revenue_growth", "supportive", ["A101"]),
    ]
    run2_edges = [
        _edge("ai_capex", "gpu_demand", "causal", ["A101"]),  # shared
        _edge("rate_cut_cycle", "valuation_risk", "conflicting", ["A101"]),  # extra edge -> different whole set
    ]
    _write_run(tmp_path, "run-1", ticker="NVDA", edges=run1_edges, created_at="2026-08-01T00:00:00Z")
    _write_run(tmp_path, "run-2", ticker="NVDA", edges=run2_edges, created_at="2026-08-10T00:00:00Z")

    fp1 = load_aggregate_fingerprints_for_run(run_id="run-1", output_root=tmp_path)
    fp2 = load_aggregate_fingerprints_for_run(run_id="run-2", output_root=tmp_path)
    assert fp1[0]["aggregate_fingerprint_id"] != fp2[0]["aggregate_fingerprint_id"]

    phi1 = load_phi_edges_for_run(run_id="run-1", output_root=tmp_path)
    phi2 = load_phi_edges_for_run(run_id="run-2", output_root=tmp_path)
    shared_ids_1 = {p["phi_id"] for p in phi1}
    shared_ids_2 = {p["phi_id"] for p in phi2}
    assert shared_ids_1 & shared_ids_2


# ---------------------------------------------------------------------------
# 14/15. Instability-signal diagnostics cannot create/remove recurrence.
# ---------------------------------------------------------------------------


def test_alpha_attribution_variance_cannot_create_recurrence(tmp_path):
    """run-1 links (ai_capex,gpu_demand) to A101+A103; run-2 links the
    identical edge to A101 only. This IS an attribution-variance case, but
    it must NOT cause A103's phi (which genuinely has no prior observation
    in run-2's world) to be reported as recurring."""
    _write_run(tmp_path, "run-1", ticker="NVDA", edges=[_edge("ai_capex", "gpu_demand", "causal", ["A101", "A103"])], created_at="2026-08-01T00:00:00Z")
    _write_run(tmp_path, "run-2", ticker="NVDA", edges=[_edge("ai_capex", "gpu_demand", "causal", ["A101"])], created_at="2026-08-10T00:00:00Z")

    signals = detect_alpha_attribution_variance(ticker="NVDA", output_root=tmp_path)
    assert len(signals) == 1  # variance genuinely detected

    phi2 = load_phi_edges_for_run(run_id="run-2", output_root=tmp_path)
    a101 = next(p for p in phi2 if p["alpha_id"] == "A101")
    a101_summary = summarize_phi_edge_history(phi_edge=a101, current_run_id="run-2", output_root=tmp_path)
    assert a101_summary["is_recurring"] is True  # A101's own edge genuinely recurs

    # A103 does not even exist as a current phi in run-2 (it only had
    # alpha_ids=["A101"]) -- attribution variance being detected elsewhere
    # must not conjure up an A103 recurrence that was never observed here.
    assert all(p["alpha_id"] != "A103" for p in phi2)


def test_edge_type_variance_cannot_create_recurrence(tmp_path):
    _write_run(tmp_path, "run-1", ticker="NVDA", edges=[_edge("ai_capex", "gpu_demand", "causal", ["A101"])], created_at="2026-08-01T00:00:00Z")
    _write_run(tmp_path, "run-2", ticker="NVDA", edges=[_edge("ai_capex", "gpu_demand", "supportive", ["A101"])], created_at="2026-08-10T00:00:00Z")

    signals = detect_edge_type_variance(ticker="NVDA", output_root=tmp_path)
    assert len(signals) == 1  # variance genuinely detected

    phi2 = load_phi_edges_for_run(run_id="run-2", output_root=tmp_path)
    summary = summarize_phi_edge_history(phi_edge=phi2[0], current_run_id="run-2", output_root=tmp_path)
    assert summary["is_recurring"] is False  # causal != supportive -- the variance signal did not bridge them


# ---------------------------------------------------------------------------
# Run eligibility (Section E): a run whose OWN persisted artifact_manifest
# already marks it incomplete is excluded from history; a run with no
# manifest at all is not excluded on that basis alone.
# ---------------------------------------------------------------------------


def test_run_marked_incomplete_by_its_own_manifest_is_excluded_from_history(tmp_path):
    _write_run(tmp_path, "run-1", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-01T00:00:00Z", artifact_completeness="fail")
    _write_run(tmp_path, "run-2", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-10T00:00:00Z")
    phi2 = load_phi_edges_for_run(run_id="run-2", output_root=tmp_path)
    summary = summarize_phi_edge_history(phi_edge=phi2[0], current_run_id="run-2", output_root=tmp_path)
    assert summary["is_recurring"] is False  # run-1 excluded despite sharing the identical edge
    assert summary["prior_run_ids"] == []


def test_run_with_no_manifest_at_all_is_not_excluded_on_that_basis_alone(tmp_path):
    _write_run(tmp_path, "run-1", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-01T00:00:00Z")  # no manifest written
    _write_run(tmp_path, "run-2", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-10T00:00:00Z")
    phi2 = load_phi_edges_for_run(run_id="run-2", output_root=tmp_path)
    summary = summarize_phi_edge_history(phi_edge=phi2[0], current_run_id="run-2", output_root=tmp_path)
    assert summary["is_recurring"] is True
    assert summary["prior_run_ids"] == ["run-1"]


def test_run_marked_pass_by_its_own_manifest_is_included(tmp_path):
    _write_run(tmp_path, "run-1", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-01T00:00:00Z", artifact_completeness="pass")
    _write_run(tmp_path, "run-2", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-10T00:00:00Z")
    phi2 = load_phi_edges_for_run(run_id="run-2", output_root=tmp_path)
    summary = summarize_phi_edge_history(phi_edge=phi2[0], current_run_id="run-2", output_root=tmp_path)
    assert summary["is_recurring"] is True


# ---------------------------------------------------------------------------
# 16. Recurrence ratio is deterministic and descriptive only.
# ---------------------------------------------------------------------------


def test_alpha_level_recurrence_summary_is_descriptive_only(tmp_path):
    run1_edges = [_edge("ai_capex", "gpu_demand", "causal", ["A101"])]
    run2_edges = [
        _edge("ai_capex", "gpu_demand", "causal", ["A101"]),  # recurs from run-1
        _edge("rate_cut_cycle", "valuation_risk", "conflicting", ["A101"]),  # first-seen in run-2
    ]
    _write_run(tmp_path, "run-1", ticker="NVDA", edges=run1_edges, created_at="2026-08-01T00:00:00Z")
    _write_run(tmp_path, "run-2", ticker="NVDA", edges=run2_edges, created_at="2026-08-10T00:00:00Z")

    structure_graph = json.loads((tmp_path / "run-2" / "structure_graph.json").read_text())
    vocab = json.loads((tmp_path / "run-2" / "tradingagents_comqutor_vocabulary_snapshot.json").read_text())
    phi_structures = build_phi_structures(
        current_run_id="run-2", structure_graph=structure_graph, vocabulary_snapshot=vocab, output_root=tmp_path
    )
    summary = summarize_alpha_memory(phi_structures)
    a101 = next(s for s in summary if s["alpha_id"] == "A101")
    assert a101["current_phi_count"] == 2
    assert a101["recurring_phi_count"] == 1
    assert a101["first_seen_phi_count"] == 1
    assert a101["recurrence_ratio"] == 0.5
    assert a101["prior_observation_total"] == 1
    assert "score" not in a101
    assert "weight" not in a101
    assert "confidence" not in a101

    # deterministic repeated computation
    summary_again = summarize_alpha_memory(phi_structures)
    assert summary == summary_again


def test_recurrence_ratio_omitted_or_zero_when_no_current_phi():
    summary = summarize_alpha_memory([])
    assert summary == []


# ---------------------------------------------------------------------------
# Instability signals: unchanged guarantees from Step 2 (retained).
# ---------------------------------------------------------------------------


def test_alpha_attribution_variance_is_detected_and_does_not_merge_phi_ids(tmp_path):
    _write_run(tmp_path, "run-1", ticker="NVDA", edges=[_edge("ai_capex", "gpu_demand", "causal", ["A101", "A103"])], created_at="2026-08-01T00:00:00Z")
    _write_run(tmp_path, "run-2", ticker="NVDA", edges=[_edge("ai_capex", "gpu_demand", "causal", ["A101"])], created_at="2026-08-10T00:00:00Z")
    signals = detect_alpha_attribution_variance(ticker="NVDA", output_root=tmp_path)
    assert len(signals) == 1
    variant_alpha_sets = {tuple(v["alpha_ids"]) for v in signals[0]["observed_variants"]}
    assert ("A101",) in variant_alpha_sets
    assert ("A101", "A103") in variant_alpha_sets
    assert not any("correct" in variant for variant in signals[0]["observed_variants"])


def test_no_alpha_attribution_variance_when_all_runs_agree(tmp_path):
    _write_run(tmp_path, "run-1", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-01T00:00:00Z")
    _write_run(tmp_path, "run-2", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-10T00:00:00Z")
    assert detect_alpha_attribution_variance(ticker="NVDA", output_root=tmp_path) == []


def test_edge_type_variance_is_detected_and_does_not_merge_phi_ids(tmp_path):
    _write_run(tmp_path, "run-1", ticker="NVDA", edges=[_edge("ai_capex", "gpu_demand", "causal", ["A101"])], created_at="2026-08-01T00:00:00Z")
    _write_run(tmp_path, "run-2", ticker="NVDA", edges=[_edge("ai_capex", "gpu_demand", "supportive", ["A101"])], created_at="2026-08-10T00:00:00Z")
    signals = detect_edge_type_variance(ticker="NVDA", output_root=tmp_path)
    assert len(signals) == 1
    observed_types = {v["edge_type"] for v in signals[0]["observed_variants"]}
    assert observed_types == {"causal", "supportive"}


def test_no_edge_type_variance_when_all_runs_agree(tmp_path):
    _write_run(tmp_path, "run-1", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-01T00:00:00Z")
    _write_run(tmp_path, "run-2", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-10T00:00:00Z")
    assert detect_edge_type_variance(ticker="NVDA", output_root=tmp_path) == []


# ---------------------------------------------------------------------------
# 21. Repeated offline execution is deterministic.
# ---------------------------------------------------------------------------


def test_repeated_execution_of_the_reader_is_deterministic(tmp_path):
    _write_run(tmp_path, "run-1", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-01T00:00:00Z")
    _write_run(tmp_path, "run-2", ticker="NVDA", edges=_ONE_EDGE, created_at="2026-08-10T00:00:00Z")
    phi2 = load_phi_edges_for_run(run_id="run-2", output_root=tmp_path)
    phi_id = phi2[0]["phi_id"]
    first = find_prior_phi_edge_observations(phi_id=phi_id, ticker="NVDA", current_run_id="run-2", output_root=tmp_path)
    second = find_prior_phi_edge_observations(phi_id=phi_id, ticker="NVDA", current_run_id="run-2", output_root=tmp_path)
    assert first == second
    summary_first = summarize_phi_edge_history(phi_edge=phi2[0], current_run_id="run-2", output_root=tmp_path)
    summary_second = summarize_phi_edge_history(phi_edge=phi2[0], current_run_id="run-2", output_root=tmp_path)
    assert summary_first == summary_second


def test_run_with_no_structure_graph_degrades_to_empty_never_crashes(tmp_path):
    run_dir = tmp_path / "run-incomplete"
    run_dir.mkdir()
    _write_json(run_dir, "metadata.json", {"run_id": "run-incomplete", "ticker": "NVDA"})
    assert load_phi_edges_for_run(run_id="run-incomplete", output_root=tmp_path) == []
    assert load_aggregate_fingerprints_for_run(run_id="run-incomplete", output_root=tmp_path) == []
