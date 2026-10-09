"""pytest plugin: every outbound (non-loopback) network entry point raises and is counted. Loopback is allowed and counted separately.
Usage: PYTHONPATH=<dir of this file> NET_TRAP_REPORT=<json path> python -m pytest -p net_trap_plugin ..."""
import json
import os
import socket
import urllib.request

_LOOPBACK = {None, "", "localhost", "127.0.0.1", "::1", "0.0.0.0"}
blocked, loopback = [], []

def _host(address):
    if isinstance(address, tuple) and address:
        return address[0]
    return address

def _wrap_connect(original, name):
    def stub(self, address, *a, **k):
        host = _host(address)
        if host in _LOOPBACK or (isinstance(host, str) and host.startswith("127.")):
            loopback.append(f"{name}:{host}")
            return original(self, address, *a, **k)
        blocked.append(f"{name}:{host}")
        raise RuntimeError(f"network attempted ({name}) -> {host}")
    return stub

_orig_connect, _orig_connect_ex = socket.socket.connect, socket.socket.connect_ex
_orig_gai, _orig_cc, _orig_urlopen = socket.getaddrinfo, socket.create_connection, urllib.request.urlopen

def _gai(host, *a, **k):
    if host in _LOOPBACK or (isinstance(host, str) and host.startswith("127.")):
        loopback.append(f"getaddrinfo:{host}")
        return _orig_gai(host, *a, **k)
    blocked.append(f"getaddrinfo:{host}")
    raise RuntimeError(f"network attempted (getaddrinfo) -> {host}")

def _cc(address, *a, **k):
    host = _host(address)
    if host in _LOOPBACK or (isinstance(host, str) and host.startswith("127.")):
        loopback.append(f"create_connection:{host}")
        return _orig_cc(address, *a, **k)
    blocked.append(f"create_connection:{host}")
    raise RuntimeError(f"network attempted (create_connection) -> {host}")

def _urlopen(*a, **k):
    blocked.append("urlopen")
    raise RuntimeError("network attempted (urlopen)")

socket.socket.connect = _wrap_connect(_orig_connect, "connect")
socket.socket.connect_ex = _wrap_connect(_orig_connect_ex, "connect_ex")
socket.getaddrinfo = _gai
socket.create_connection = _cc
urllib.request.urlopen = _urlopen

def pytest_sessionfinish(session, exitstatus):
    path = os.environ.get("NET_TRAP_REPORT")
    report = {"blocked_attempts": len(blocked), "blocked": blocked[:50], "loopback_connections_allowed": len(loopback), "pytest_exitstatus": int(exitstatus)}
    if path:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1)
    print("\n[net_trap] blocked outbound attempts:", len(blocked), "| loopback allowed:", len(loopback))
