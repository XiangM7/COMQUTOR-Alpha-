"""Tests for v0.1.3 Measurement Foundation, Part B: recorder_health_diagnostics.

Pure, offline, deterministic -- no Provider call, no ticker run, no
filesystem mutation of any run artifact. Covers task section 28 A-J plus a
real-data regression test against the persisted TSM launcher log."""

from __future__ import annotations

from pathlib import Path

import pytest

from comqutor_alpha.regression import provider_health_diagnostics as phd
from comqutor_alpha.regression import recorder_health_diagnostics as rhd

REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_LOG_PATH = Path("/tmp/comqutor_live_start.log")
NEW_TSM_RUN_ID = "0aeea938-97a8-49c8-97e1-409f6dadad30"
NEW_TSM_RUN_DIR = REPO_ROOT / "outputs" / "runs" / NEW_TSM_RUN_ID


def _log_line(run_id: str, reason_code: str, exc_type: str) -> str:
    return f"semantic runtime degraded (run_id={run_id}, reason_code={reason_code}, exc_type={exc_type})"


# --- A. zero recorder events -> RECORDER_HEALTHY --------------------------


def test_zero_recorder_events_is_healthy():
    log_text = _log_line("r1", "SEMANTIC_CACHE_WRITE_FAILED", "OSError") + "\n"
    result = rhd.compute_recorder_health_diagnostics(ticker="TSM", run_id="r1", log_text=log_text)
    assert result["recorder_failure_events"] == 0
    assert result["recorder_health"] == rhd.RECORDER_HEALTHY


def test_no_log_source_reports_unavailable_not_a_fabricated_zero():
    result = rhd.compute_recorder_health_diagnostics(ticker="TSM", run_id="r1")
    assert result["recorder_failure_events"] is None
    assert result["recorder_health"] is None
    assert result["recorder_source_durability"] == rhd.SOURCE_UNAVAILABLE


# --- B. one recorder failure -> RECORDER_DEGRADED --------------------------


def test_one_recorder_failure_is_degraded():
    log_text = _log_line("r1", "SEMANTIC_RECORDER_APPEND_FAILED", "RecorderIntegrityError") + "\n"
    result = rhd.compute_recorder_health_diagnostics(ticker="TSM", run_id="r1", log_text=log_text)
    assert result["recorder_failure_events"] == 1
    assert result["recorder_health"] == rhd.RECORDER_DEGRADED


# --- C. 247 events counted correctly ---------------------------------------


def test_247_synthetic_events_counted_correctly():
    lines = [_log_line("r1", "SEMANTIC_RECORDER_APPEND_FAILED", "RecorderIntegrityError") for _ in range(247)]
    log_text = "\n".join(lines) + "\n"
    result = rhd.compute_recorder_health_diagnostics(ticker="TSM", run_id="r1", log_text=log_text)
    assert result["recorder_failure_events"] == 247
    assert result["recorder_failure_error_types"] == {"RecorderIntegrityError": 247}


def test_filters_by_run_id_ignores_other_runs_in_same_log():
    log_text = "\n".join(
        [
            _log_line("r1", "SEMANTIC_RECORDER_APPEND_FAILED", "RecorderIntegrityError"),
            _log_line("r2", "SEMANTIC_RECORDER_APPEND_FAILED", "RecorderIntegrityError"),
            _log_line("r2", "SEMANTIC_RECORDER_APPEND_FAILED", "RecorderIntegrityError"),
        ]
    )
    result = rhd.compute_recorder_health_diagnostics(ticker="TSM", run_id="r1", log_text=log_text)
    assert result["recorder_failure_events"] == 1


def test_unrelated_reason_codes_are_not_counted_as_recorder_failures():
    log_text = "\n".join(
        [
            _log_line("r1", "SEMANTIC_RECORDER_INITIALIZATION_FAILED", "OSError"),
            _log_line("r1", "SEMANTIC_CACHE_WRITE_FAILED", "OSError"),
            _log_line("r1", "SEMANTIC_MANIFEST_FINALIZATION_FAILED", "OSError"),
        ]
    )
    result = rhd.compute_recorder_health_diagnostics(ticker="TSM", run_id="r1", log_text=log_text)
    assert result["recorder_failure_events"] == 0
    assert result["recorder_health"] == rhd.RECORDER_HEALTHY


# --- G. canonical semantic losses remain zero -------------------------------


def test_canonical_semantic_losses_always_zero_under_current_architecture():
    log_text = "\n".join(_log_line("r1", "SEMANTIC_RECORDER_APPEND_FAILED", "RecorderIntegrityError") for _ in range(50))
    result = rhd.compute_recorder_health_diagnostics(ticker="TSM", run_id="r1", log_text=log_text)
    assert result["canonical_semantic_losses"] == 0
    assert result["architecture_role"] == rhd.ARCHITECTURE_ROLE_AUDIT_TRACE_ONLY


# --- H. ephemeral source reported honestly ----------------------------------


def test_ephemeral_source_reported_honestly():
    result = rhd.compute_recorder_health_diagnostics(
        ticker="TSM", run_id="r1", log_text=_log_line("r1", "SEMANTIC_RECORDER_APPEND_FAILED", "RecorderIntegrityError")
    )
    assert result["recorder_source_durability"] == rhd.SOURCE_EPHEMERAL_LOG_ONLY


# --- I. unknown claim attribution remains unknown/null ----------------------


def test_claim_level_attribution_remains_unknown():
    log_text = _log_line("r1", "SEMANTIC_RECORDER_APPEND_FAILED", "RecorderIntegrityError")
    result = rhd.compute_recorder_health_diagnostics(ticker="TSM", run_id="r1", log_text=log_text)
    assert result["recorder_failure_components"] is None
    assert result["recorder_traceability_unknown_count"] == 1


# --- D/E/F. recorder failure never becomes a Provider failure/orphan/impact -


def test_recorder_events_do_not_become_provider_failures():
    recorder_result = rhd.compute_recorder_health_diagnostics(
        ticker="TSM",
        run_id="r1",
        log_text="\n".join(_log_line("r1", "SEMANTIC_RECORDER_APPEND_FAILED", "RecorderIntegrityError") for _ in range(10)),
    )
    provider_result = {
        "provider_health": "PROVIDER_HEALTHY",
        "provider_failure_events": 0,
        "provider_final_orphans_total": 0,
        "impacted_alpha_ids": [],
    }
    separation = rhd.assert_recorder_provider_separation(recorder_result, provider_result)
    assert separation["recorder_events_counted_as_provider_failures"] is False
    assert separation["recorder_events_counted_as_provider_orphans"] is False
    assert separation["recorder_events_create_impacted_alpha"] is False
    assert separation["provider_health_independent_value"] == "PROVIDER_HEALTHY"
    assert separation["provider_failure_events_independent_value"] == 0
    assert separation["impacted_alpha_ids_independent_value"] == []


def test_separation_holds_even_when_provider_is_independently_degraded():
    """The invariant is that recorder counts never LEAK INTO Provider's own
    numbers -- not that Provider must be healthy. A run can independently
    have both real Provider failures AND recorder failures; this test
    proves the two remain separately-attributed values, never summed."""
    recorder_result = rhd.compute_recorder_health_diagnostics(
        ticker="TSM",
        run_id="r1",
        log_text="\n".join(_log_line("r1", "SEMANTIC_RECORDER_APPEND_FAILED", "RecorderIntegrityError") for _ in range(247)),
    )
    provider_result = {
        "provider_health": "PROVIDER_DEGRADED",
        "provider_failure_events": 117,
        "provider_final_orphans_total": 42,
        "impacted_alpha_ids": ["A101"],
    }
    separation = rhd.assert_recorder_provider_separation(recorder_result, provider_result)
    assert recorder_result["recorder_failure_events"] == 247
    assert separation["provider_failure_events_independent_value"] == 117
    assert separation["provider_final_orphans_independent_value"] == 42
    assert separation["impacted_alpha_ids_independent_value"] == ["A101"]
    assert separation["recorder_events_create_impacted_alpha"] is False


# --- J. recorder metrics do not mutate Alpha artifacts ----------------------


@pytest.mark.skipif(not NEW_TSM_RUN_DIR.is_dir(), reason="TSM run artifacts not present in this environment")
def test_recorder_diagnostics_never_touch_run_artifacts():
    import hashlib

    hashes_before = {}
    for name in ("structure_graph.json", "alpha_matches.json", "run_audit.json"):
        path = NEW_TSM_RUN_DIR / name
        if path.is_file():
            hashes_before[name] = hashlib.sha256(path.read_bytes()).hexdigest()

    rhd.compute_recorder_health_diagnostics(ticker="TSM", run_id=NEW_TSM_RUN_ID, log_path=str(LIVE_LOG_PATH) if LIVE_LOG_PATH.is_file() else None, log_text=None if LIVE_LOG_PATH.is_file() else "")

    for name, before in hashes_before.items():
        path = NEW_TSM_RUN_DIR / name
        after = hashlib.sha256(path.read_bytes()).hexdigest()
        assert before == after


# --- Real-data regression: new TSM run's 247-event fixture -----------------


@pytest.mark.skipif(not LIVE_LOG_PATH.is_file(), reason="ephemeral launcher log not present in this environment")
def test_new_tsm_run_recorder_fixture_matches_prior_audit():
    result = rhd.compute_recorder_health_diagnostics(
        ticker="TSM", run_id=NEW_TSM_RUN_ID, log_path=str(LIVE_LOG_PATH)
    )
    assert result["recorder_failure_events"] == 247
    assert result["recorder_health"] == rhd.RECORDER_DEGRADED
    assert result["canonical_semantic_losses"] == 0
    assert result["recorder_source_durability"] == rhd.SOURCE_EPHEMERAL_LOG_ONLY


@pytest.mark.skipif(
    not LIVE_LOG_PATH.is_file() or not NEW_TSM_RUN_DIR.is_dir(),
    reason="ephemeral launcher log or TSM run artifacts not present in this environment",
)
def test_new_tsm_recorder_failures_do_not_alter_provider_impacted_alpha_ids():
    provider_result = phd.compute_provider_health_diagnostics(
        run_dir=NEW_TSM_RUN_DIR, ticker="TSM", run_id=NEW_TSM_RUN_ID
    )
    recorder_result = rhd.compute_recorder_health_diagnostics(
        ticker="TSM", run_id=NEW_TSM_RUN_ID, log_path=str(LIVE_LOG_PATH)
    )
    assert recorder_result["recorder_failure_events"] == 247
    # The prior audit's established, independently-confirmed value -- recorder
    # failures (247 of them) do not change this in any way.
    assert provider_result["impacted_alpha_ids"] == ["A101"]
