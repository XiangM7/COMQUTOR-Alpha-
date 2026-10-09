"""Shared, reusable "block real outbound network" guard (COMQUTOR Alpha
network-leak fix, 2026-09-26). Factored out of
``tests/structured_output_shadow/conftest.py`` so any test package that
exercises the real ``comqutor_alpha.api.routes_research.run_research_request``
path (or any other code that might reach a real socket) can apply the same
protection without duplicating the patching logic -- this round's new T1
source-linking pipeline tests use it too (see
``tests/test_source_linking_pipeline.py``), not just
``tests/structured_output_shadow``.

Every blocked scenario intercepts strictly inside
``socket.socket.connect``/``connect_ex``, before any real OS-level connect
syscall runs for a non-loopback address -- installing this guard never
itself sends a real network request, even transiently.
"""

from __future__ import annotations

import socket

import pytest

ALLOWED_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


class OutboundNetworkBlockedError(RuntimeError):
    """Raised instead of allowing a real outbound socket connection during a
    guarded test -- the guarded package must make zero network/Provider
    calls."""


def _address_host(address):
    return address[0] if isinstance(address, tuple) else address


def install_network_guard(monkeypatch) -> list[object]:
    """Patches ``socket.socket.connect``/``connect_ex`` for the lifetime of
    ``monkeypatch`` (undone automatically at fixture teardown) and returns
    the mutable list every blocked attempt's address is recorded into.
    Callers are expected to assert this list is empty at teardown -- see
    :func:`network_guard` below for the ready-made fixture."""
    blocked_attempts: list[object] = []
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def _guarded_connect(self, address, *args, **kwargs):
        if _address_host(address) in ALLOWED_HOSTS:
            return real_connect(self, address, *args, **kwargs)
        blocked_attempts.append(address)
        raise OutboundNetworkBlockedError(
            f"blocked a real outbound connection attempt to {address!r} -- "
            "this test must make zero network/Provider calls."
        )

    def _guarded_connect_ex(self, address, *args, **kwargs):
        if _address_host(address) in ALLOWED_HOSTS:
            return real_connect_ex(self, address, *args, **kwargs)
        blocked_attempts.append(address)
        raise OutboundNetworkBlockedError(
            f"blocked a real outbound connection attempt to {address!r} -- "
            "this test must make zero network/Provider calls."
        )

    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _guarded_connect_ex)
    return blocked_attempts


@pytest.fixture
def network_guard(monkeypatch):
    """Ready-made autouse-able fixture: install the guard, yield the
    recorded-attempts list, then assert it is still empty. A test package
    wires this in with its own ``@pytest.fixture(autouse=True)`` wrapper
    (see ``tests/structured_output_shadow/conftest.py``) so it applies to
    every test in that package without each test requesting it by name."""
    blocked_attempts = install_network_guard(monkeypatch)
    yield blocked_attempts
    assert blocked_attempts == [], (
        "a test attempted a real outbound network connection (blocked, never reached "
        f"the network): {blocked_attempts!r}"
    )
