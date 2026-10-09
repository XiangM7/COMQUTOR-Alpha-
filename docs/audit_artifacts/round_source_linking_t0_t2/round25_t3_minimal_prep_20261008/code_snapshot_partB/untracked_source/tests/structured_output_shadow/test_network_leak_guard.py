"""Formal regression coverage for this package's two conftest.py network-
leak guards (added for the COMQUTOR Alpha network-leak fix, 2026-09-26 --
see tests/structured_output_shadow/conftest.py and tests/_network_guard.py).
Promotes the throwaway verification probe used while diagnosing the real
Yahoo Finance connection into permanent test coverage.

Every scenario below intercepts strictly inside
socket.socket.connect/connect_ex, before any real OS-level connect syscall
runs for a non-loopback address -- no test here ever sends a real network
request, even transiently, including the "swallowed exception" scenario
(its nested pytest subprocess is itself protected by this same package's
conftest.py, so the blocked connect() call inside it never reaches a
syscall either).
"""

from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path

import pytest

from comqutor_alpha.data_sanity.pipeline import run_data_sanity_stage
from comqutor_alpha.storage.file_store import save_json_record
from tests._network_guard import OutboundNetworkBlockedError

REPO_ROOT = Path(__file__).resolve().parents[2]
_NEVER_DIALED_ADDRESS = ("93.184.216.34", 443)


def test_unexpected_outbound_connection_is_blocked_immediately(network_guard):
    with pytest.raises(OutboundNetworkBlockedError) as exc_info:
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(_NEVER_DIALED_ADDRESS)
    assert "blocked a real outbound connection attempt" in str(exc_info.value)
    assert _NEVER_DIALED_ADDRESS in network_guard
    # This test deliberately triggers and acknowledges one blocked attempt
    # -- clear it so the fixture's own teardown assertion (which exists to
    # catch attempts no test acknowledged) does not also fail this
    # otherwise-passing test. An unacknowledged attempt anywhere else still
    # fails via that same teardown (see the swallowed-exception test below).
    network_guard.clear()


def test_swallowing_the_exception_still_fails_the_test_via_teardown():
    """Reproduces the exact production shape that hid the original leak
    (comqutor_alpha/api/routes_research.py's own
    ``with contextlib.suppress(Exception): run_data_sanity_stage(...)``)
    inside a NESTED pytest process that lives (transiently) under this same
    package, so it inherits this directory's conftest.py guard -- proving
    the outer teardown assertion fails the run even though the inner code
    path swallows the exception and never lets it surface on its own.
    """
    probe_path = Path(__file__).parent / "_tmp_probe_swallowed_network_leak.py"
    probe_path.write_text(
        "import contextlib\n"
        "import socket\n"
        "\n"
        "\n"
        "def test_probe_swallows_a_blocked_connection():\n"
        "    with contextlib.suppress(Exception):\n"
        "        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(('93.184.216.34', 443))\n"
        "    assert True  # the test BODY sees no failure -- only conftest teardown should catch this\n",
        encoding="utf-8",
    )
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(probe_path), "-q"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
    finally:
        probe_path.unlink(missing_ok=True)

    assert result.returncode != 0, (
        "a probe test that swallows a blocked-connection exception must still fail the "
        f"suite (via the network_guard fixture's own teardown assertion) -- got:\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "attempted a real outbound network connection" in result.stdout


def test_fixed_market_data_provider_is_used_when_data_sanity_is_enabled(tmp_path, monkeypatch):
    """Even if COMQUTOR_DATA_SANITY_ENABLED is genuinely true for a test in
    this package, run_data_sanity_stage must use the fixed, no-network
    provider injected by conftest.py's _fixed_market_data_provider fixture
    -- never the real YFinanceMarketDataProvider."""
    monkeypatch.setenv("COMQUTOR_DATA_SANITY_ENABLED", "true")
    run_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    save_json_record(
        run_id, "metadata.json", {"ticker": "NVDA", "analysis_date": "2026-08-10"}, output_root=str(tmp_path)
    )
    save_json_record(
        run_id, "raw_agent_outputs.json", {"ticker": "NVDA", "agent_outputs": []}, output_root=str(tmp_path)
    )

    result = run_data_sanity_stage(run_id, str(tmp_path))

    assert result["provider_version"] == "test-fixture-no-network"
    assert result["status"] != "disabled"
