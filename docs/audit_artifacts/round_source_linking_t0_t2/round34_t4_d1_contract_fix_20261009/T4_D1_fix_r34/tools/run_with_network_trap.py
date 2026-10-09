#!/usr/bin/env python3
"""Runs one of the repository's command-line entries IN-PROCESS with every outbound network entry point replaced by a counting stub that raises, and prints
the count of attempted calls (0 expected: the entries read saved files only).

    python run_with_network_trap.py <path to a script with main(argv)> [entry arguments ...]

(Round 25 copy of the Round 24 tool: takes a script PATH -- relative to the repository root or absolute -- instead of a name under scripts/.)"""
import importlib.util
import socket
import sys
import urllib.request
from pathlib import Path

REPO = next(p for p in Path(__file__).resolve().parents if (p / "comqutor_alpha").is_dir())
sys.path.insert(0, str(REPO))

attempts: list[str] = []


def refuse(name):
    def stub(*_a, **_k):
        attempts.append(name)
        raise RuntimeError("network attempted: " + name)

    return stub


socket.socket.connect = refuse("socket.connect")
socket.socket.connect_ex = refuse("socket.connect_ex")
socket.create_connection = refuse("socket.create_connection")
socket.getaddrinfo = refuse("socket.getaddrinfo")
urllib.request.urlopen = refuse("urllib.request.urlopen")

script, args = sys.argv[1], sys.argv[2:]
spec = importlib.util.spec_from_file_location("trapped_cli", script if Path(script).is_absolute() else REPO / script)
module = importlib.util.module_from_spec(spec)
sys.modules["trapped_cli"] = module
spec.loader.exec_module(module)
code = module.main(args)
print(f"exit code: {code} | network attempts: {len(attempts)}")
sys.exit(code if not attempts else 99)
