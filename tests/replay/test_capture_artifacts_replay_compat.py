"""T1 closeout (Round 22): a run that carries the two additive capture artifacts still replays exactly, and a run without them
(every historical run) is read exactly as before.

``derived_inputs.json`` / ``provider_response_audit.json`` are present-only extras of a LIVE run's directory: the exact
semantic replay snapshots the source directory, checks the artifact manifest's hashes and replays from the saved semantic
artifacts only. This proves the extras neither break that nor get copied into (or read by) the replay -- using the same
offline fixture run the other replay tests use. Synthetic payloads; zero Provider calls.
"""

from __future__ import annotations

import json
from pathlib import Path

from comqutor_alpha.api.artifact_export import build_and_write_artifact_manifest
from comqutor_alpha.capture_artifacts import (
    DERIVED_INPUTS_FILENAME,
    PROVIDER_RESPONSE_AUDIT_FILENAME,
    build_derived_inputs_artifact,
    build_provider_response_artifact,
)
from comqutor_alpha.replay.exact_semantic import run_exact_semantic_replay
from comqutor_alpha.replay.source_bundle import load_exact_semantic_source_bundle, verify_source_bundle_unchanged
from comqutor_alpha.storage.file_store import save_json_record
from tests.replay.conftest import file_tree_snapshot


def _add_capture_artifacts(source: Path) -> None:
    run_id = source.name
    ticker = json.loads((source / "metadata.json").read_text(encoding="utf-8"))["ticker"]
    series = {
        "time_index": {"name": "Date", "format": "YYYY-MM-DD", "timezone_assumed": "America/New_York", "order": "ascending"},
        "columns": ["Open", "High", "Low", "Close", "Volume"],
        "rows": [["2026-06-29", 1.0, 2.0, 0.5, 1.5, 10], ["2026-06-30", 1.5, 2.5, 1.0, 2.0, 12]],
    }
    from comqutor_alpha.capture_artifacts import series_sha256

    series.update({"row_count": 2, "first_date": "2026-06-29", "last_date": "2026-06-30", "sha256": series_sha256(series)})
    inputs = build_derived_inputs_artifact(
        run_id=run_id, ticker=ticker,
        entries=[{"input_id": "src_synthetic#ohlcv_window", "source_id": "src_synthetic", "kind": "ohlcv_window", "series": series,
                  "method": {"indicators": []}, "outputs": {"indicators": {}}}],
    )
    audit = build_provider_response_artifact(run_id=run_id, ticker=ticker, entries=[])
    save_json_record(run_id, DERIVED_INPUTS_FILENAME, inputs, output_root=source.parent)
    save_json_record(run_id, PROVIDER_RESPONSE_AUDIT_FILENAME, audit, output_root=source.parent)
    build_and_write_artifact_manifest(run_id=run_id, ticker=ticker, output_root=source.parent)  # lists them, with their real hashes


def test_a_live_run_with_the_new_artifacts_loads_and_replays_exactly_and_the_extras_are_not_copied(tmp_path: Path, eligible_live_source: Path) -> None:
    before_plain = load_exact_semantic_source_bundle(eligible_live_source)
    plain_files = {f.relative_path for f in before_plain.source_files}
    assert DERIVED_INPUTS_FILENAME not in plain_files  # a run without them is read exactly as before

    _add_capture_artifacts(eligible_live_source)
    bundle = load_exact_semantic_source_bundle(eligible_live_source)
    assert {f.relative_path for f in bundle.source_files} >= {DERIVED_INPUTS_FILENAME, PROVIDER_RESPONSE_AUDIT_FILENAME}
    assert verify_source_bundle_unchanged(bundle) is True

    snapshot = file_tree_snapshot(eligible_live_source)
    output_root = tmp_path / "exact-replays"
    result = run_exact_semantic_replay(eligible_live_source, output_root, replay_id="exact-replay-with-capture-artifacts")
    replay_dir = output_root / "exact-replay-with-capture-artifacts"

    assert result.status == "completed" and result.provider_calls == 0 and result.market_data_calls == 0
    assert file_tree_snapshot(eligible_live_source) == snapshot  # the source run is still read-only
    assert not (replay_dir / DERIVED_INPUTS_FILENAME).exists() and not (replay_dir / PROVIDER_RESPONSE_AUDIT_FILENAME).exists()
    binding = json.loads((replay_dir / "semantic_binding_audit.json").read_text(encoding="utf-8"))
    assert binding["final_status"] == "PASS"
