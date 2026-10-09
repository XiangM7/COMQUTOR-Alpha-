#!/usr/bin/env python3
"""Runs one of the repository's command-line entries IN-PROCESS with every outbound network entry point replaced by a counting stub that raises, and prints
the count of attempted calls (0 expected: the entries read saved files only).

    python run_with_network_trap.py run_formal_acceptance.py --out-dir <new dir> [entry arguments ...]
    python run_with_network_trap.py build_open_review_ledger.py --out-dir <new dir>

The script name is resolved under scripts/ of the repository this file sits in (found by walking up to the directory that holds comqutor_alpha/)."""
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
spec = importlib.util.spec_from_file_location("trapped_cli", REPO / "scripts" / script)
module = importlib.util.module_from_spec(spec)
sys.modules["trapped_cli"] = module
spec.loader.exec_module(module)
code = module.main(args)
print(f"exit code: {code} | network attempts: {len(attempts)}")
sys.exit(code if not attempts else 99)
