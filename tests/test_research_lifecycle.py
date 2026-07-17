"""W5.1A: research_lifecycle.py unit tests.

Covers the pure/deterministic pieces: request fingerprint construction,
lifecycle state machine constants/transitions, run-history cursor codec,
and the API server entrypoint's import/config-resolution safety. Repository
(claim/mark/list) and HTTP-level behavior are covered in
tests/test_research_runs_persistence.py and tests/test_research_runs_api.py
respectively.
"""

from __future__ import annotations

import math

import pytest

import comqutor_alpha.api.server as api_server
from comqutor_alpha.research_lifecycle import (
    ACTIVE_RESEARCH_RUN_STATUSES,
    DEFAULT_SELECTED_ANALYSTS,
    RESEARCH_RUN_STATUSES,
    SERVER_UNCONFIGURED_IDENTITY,
    TERMINAL_RESEARCH_RUN_STATUSES,
    ResearchLifecycleError,
    build_research_request_fingerprint,
    build_research_request_identity,
    decode_run_history_cursor,
    encode_run_history_cursor,
    is_allowed_transition,
)

_OFFLINE_PAYLOAD = [
    {"agent": "news_agent", "raw_output": "AI capex is rising and driving GPU demand."},
]


def _base_payload(**overrides):
    payload = {
        "ticker": "NVDA",
        "analysis_date": "2026-06-30",
        "offline_raw_agent_outputs": _OFFLINE_PAYLOAD,
    }
    payload.update(overrides)
    return payload


def _fingerprint(**overrides):
    return build_research_request_fingerprint(build_research_request_identity(_base_payload(**overrides)))


# ---------------------------------------------------------------------------
# A. Fingerprint
# ---------------------------------------------------------------------------


def test_identical_request_produces_identical_fingerprint():
    assert _fingerprint() == _fingerprint()


def test_selected_analysts_order_does_not_affect_fingerprint():
    f1 = _fingerprint(selected_analysts=["market", "news", "fundamentals"])
    f2 = _fingerprint(selected_analysts=["fundamentals", "news", "market"])
    assert f1 == f2


def test_duplicate_analysts_do_not_change_fingerprint():
    f1 = _fingerprint(selected_analysts=["market", "news"])
    f2 = _fingerprint(selected_analysts=["market", "news", "market", "news"])
    assert f1 == f2


def test_run_id_does_not_affect_fingerprint():
    f1 = _fingerprint()
    f2 = _fingerprint(run_id="explicit-run-id-123")
    assert f1 == f2


def test_force_refresh_does_not_affect_fingerprint():
    f1 = _fingerprint(force_refresh=False)
    f2 = _fingerprint(force_refresh=True)
    assert f1 == f2


def test_ticker_change_changes_fingerprint():
    assert _fingerprint(ticker="NVDA") != _fingerprint(ticker="QQQ")


def test_analysis_date_change_changes_fingerprint():
    assert _fingerprint(analysis_date="2026-06-30") != _fingerprint(analysis_date="2026-07-01")


def test_offline_payload_content_change_changes_fingerprint():
    f1 = _fingerprint(offline_raw_agent_outputs=[{"agent": "news_agent", "raw_output": "A"}])
    f2 = _fingerprint(offline_raw_agent_outputs=[{"agent": "news_agent", "raw_output": "B"}])
    assert f1 != f2


def test_execution_mode_change_changes_fingerprint():
    # offline (offline_raw_agent_outputs present) vs real (absent).
    f_offline = _fingerprint()
    identity_real = build_research_request_identity({"ticker": "NVDA", "analysis_date": "2026-06-30"})
    f_real = build_research_request_fingerprint(identity_real)
    assert f_offline != f_real


def test_pipeline_identity_change_changes_fingerprint(monkeypatch):
    import comqutor_alpha.research_lifecycle as lifecycle

    identity_before = build_research_request_identity(_base_payload())
    f_before = build_research_request_fingerprint(identity_before)

    original = lifecycle._pipeline_identity

    def patched():
        result = dict(original())
        result["graph_schema_version"] = "week3.structure_graph.v999-test"
        return result

    monkeypatch.setattr(lifecycle, "_pipeline_identity", patched)
    identity_after = build_research_request_identity(_base_payload())
    f_after = build_research_request_fingerprint(identity_after)
    assert f_before != f_after


def test_fingerprint_is_stable_sha256_hex():
    fingerprint = _fingerprint()
    assert isinstance(fingerprint, str)
    assert len(fingerprint) == 64
    int(fingerprint, 16)  # raises if not valid hex


def test_identity_never_contains_secrets_or_raw_payload_markers():
    identity = build_research_request_identity(_base_payload())
    serialized = str(identity)
    for forbidden in ("api_key", "secret", "password", "DROP TABLE", "/Users/", "postgresql://"):
        assert forbidden not in serialized
    assert "run_id" not in identity
    assert "force_refresh" not in identity


def test_identity_offline_digest_does_not_store_raw_offline_payload():
    identity = build_research_request_identity(_base_payload())
    assert identity["offline_input_digest"] is not None
    assert len(identity["offline_input_digest"]) == 64
    assert "AI capex is rising" not in str(identity)


def test_real_execution_mode_uses_server_unconfigured_identity_by_default():
    identity = build_research_request_identity({"ticker": "NVDA", "analysis_date": "2026-06-30"})
    assert identity["execution_mode"] == "real"
    assert identity["provider_identity"] == SERVER_UNCONFIGURED_IDENTITY
    assert identity["model_identity"] == SERVER_UNCONFIGURED_IDENTITY


def test_server_execution_identity_is_never_read_from_http_payload():
    # Even if a caller stuffs provider/model directly into the payload dict,
    # only the dedicated server_execution_identity kwarg is trusted.
    identity = build_research_request_identity(
        {
            "ticker": "NVDA",
            "analysis_date": "2026-06-30",
            "provider_identity": "should-be-ignored",
            "model_identity": "should-be-ignored",
        }
    )
    assert identity["provider_identity"] == SERVER_UNCONFIGURED_IDENTITY
    assert identity["model_identity"] == SERVER_UNCONFIGURED_IDENTITY


def test_omitted_selected_analysts_uses_default_set():
    identity = build_research_request_identity(_base_payload(selected_analysts=None))
    assert identity["selected_analysts"] == list(DEFAULT_SELECTED_ANALYSTS)


def test_invalid_ticker_raises_value_error():
    with pytest.raises(ValueError):
        build_research_request_identity({"ticker": "'; DROP TABLE research_runs;--"})


# ---------------------------------------------------------------------------
# B. Lifecycle state machine
# ---------------------------------------------------------------------------


def test_research_run_statuses_are_exactly_five():
    assert {"queued", "running", "completed", "partial", "failed"} == RESEARCH_RUN_STATUSES


def test_terminal_and_active_statuses_partition_all_statuses():
    assert TERMINAL_RESEARCH_RUN_STATUSES | ACTIVE_RESEARCH_RUN_STATUSES == RESEARCH_RUN_STATUSES
    assert set() == TERMINAL_RESEARCH_RUN_STATUSES & ACTIVE_RESEARCH_RUN_STATUSES


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        ("queued", "running"),
        ("queued", "failed"),
        ("running", "completed"),
        ("running", "partial"),
        ("running", "failed"),
    ],
)
def test_allowed_transitions(from_status, to_status):
    assert is_allowed_transition(from_status, to_status)


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        ("completed", "running"),
        ("partial", "running"),
        ("failed", "running"),
        ("completed", "completed"),
        ("partial", "failed"),
        ("failed", "completed"),
        ("queued", "completed"),
        ("queued", "partial"),
        ("queued", "queued"),
        ("running", "queued"),
        ("running", "running"),
    ],
)
def test_forbidden_transitions(from_status, to_status):
    assert not is_allowed_transition(from_status, to_status)


def test_no_transition_out_of_any_terminal_status():
    for terminal_status in TERMINAL_RESEARCH_RUN_STATUSES:
        for candidate in RESEARCH_RUN_STATUSES:
            assert not is_allowed_transition(terminal_status, candidate)


# ---------------------------------------------------------------------------
# Run history cursor codec
# ---------------------------------------------------------------------------


def test_cursor_round_trips():
    encoded = encode_run_history_cursor("2026-06-30T00:00:00+00:00", "run-123")
    decoded = decode_run_history_cursor(encoded)
    assert decoded == ("2026-06-30T00:00:00+00:00", "run-123")


def test_invalid_cursor_raises_lifecycle_error():
    with pytest.raises(ResearchLifecycleError) as exc_info:
        decode_run_history_cursor("not-a-valid-cursor")
    assert exc_info.value.reason_code == "INVALID_CURSOR"


def test_malformed_json_cursor_raises_lifecycle_error():
    with pytest.raises(ResearchLifecycleError):
        decode_run_history_cursor('{"not": "a tuple"}')


# ---------------------------------------------------------------------------
# H. API server entrypoint safety
# ---------------------------------------------------------------------------


def test_server_module_import_does_not_start_uvicorn():
    # If import had side effects starting a server, this module-level
    # import (already executed at the top of this file) would have hung or
    # bound a port. Reaching this line at all is the proof.
    assert api_server.main is not None


def test_default_host_is_localhost(monkeypatch):
    monkeypatch.delenv("COMQUTOR_API_HOST", raising=False)
    assert api_server._resolve_host() == "127.0.0.1"


def test_default_port_is_8000(monkeypatch):
    monkeypatch.delenv("COMQUTOR_API_PORT", raising=False)
    assert api_server._resolve_port() == 8000


def test_invalid_port_fails_safely_not_with_a_raw_traceback(monkeypatch):
    monkeypatch.setenv("COMQUTOR_API_PORT", "not-a-port")
    with pytest.raises(api_server.ServerConfigurationError) as exc_info:
        api_server._resolve_port()
    assert exc_info.value.reason_code == "INVALID_COMQUTOR_API_PORT"


def test_out_of_range_port_fails_safely(monkeypatch):
    monkeypatch.setenv("COMQUTOR_API_PORT", "99999")
    with pytest.raises(api_server.ServerConfigurationError):
        api_server._resolve_port()


def test_host_env_override_is_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("COMQUTOR_API_HOST", "0.0.0.0")
    assert api_server._resolve_host() == "0.0.0.0"


def test_math_module_available_for_offline_digest_edge_cases():
    # Sanity: fingerprint helpers must tolerate NaN/Infinity inside offline
    # payload content without crashing the digest itself (canonical JSON
    # dumps floats -- json.dumps rejects real NaN/Infinity by default unless
    # allow_nan, which is the default True; this just confirms no crash).
    identity = build_research_request_identity(
        _base_payload(offline_raw_agent_outputs=[{"agent": "news_agent", "raw_output": "x", "score": math.nan}])
    )
    assert identity["offline_input_digest"] is not None
