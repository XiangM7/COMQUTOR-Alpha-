#!/usr/bin/env python3
"""Operator entry for the experimental Alpha relevance judgment (P4) -- default off.

Phase 1: ``judge`` runs ``comqutor_alpha.alpha_relevance_experiment.judge_run_relevance`` on ONE saved run directory OUTSIDE the
repository's ``outputs/`` tree (a verification copy). The experiment configuration must be named explicitly -- there is no default -- and
the only enabled configuration uses the SIMULATED gateway, whose answers are TEST DATA (never a model judgment).

Phase 2 (2026-10-12): ``run-plan`` executes a frozen small-sample evaluation plan once, through ``run_relevance_evaluation_plan``. The
mode must be chosen explicitly: ``SIMULATED_REHEARSAL`` (simulated provider, TEST DATA) or ``LIVE`` (real model requests; refused
unless the authorization file is signed for exactly this plan and manifest, not expired and not used before).

A network guard runs around every command. It refuses every non-loopback connection, DNS lookup and HTTP transport, except in a LIVE
``run-plan``, where only the configured provider host may be resolved and connected to. Every refused attempt is reported. No database is
used.

  judge    --run <run id> --output-root <root> --experiment p4_relevance_simulated_20261012
  status   --run <run id> --output-root <root>
  run-plan --mode SIMULATED_REHEARSAL|LIVE --plan <json> --manifest <json> --authorization <json> --eval-root <dir>
           --experiment p4_relevance_live_small_sample_20261012
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha import alpha_relevance_experiment as ex  # noqa: E402

_LOOPBACK = ("localhost", "127.0.0.1", "::1")


class NetworkGuard:
    """Fails closed on every outbound path (HTTP transports, non-loopback DNS and socket connects) and counts the attempts. The
    gateway itself stays usable: its provider is the in-process simulated one. With ``allowed_hosts`` (LIVE run-plan only), HTTP stays
    possible but only those host names may be resolved, and only the addresses they resolved to may be connected to."""

    def __init__(self, allowed_hosts: tuple[str, ...] = ()) -> None:
        self.allowed_hosts = tuple(h.lower() for h in allowed_hosts if h)

    def __enter__(self):
        import httpx  # noqa: PLC0415

        self.attempts: list[str] = []
        self.allowed: list[str] = []
        self._saved: list[tuple[object, str, object]] = []
        allowed_addresses: set[str] = set()

        def patch(obj, attr, replacement):
            self._saved.append((obj, attr, getattr(obj, attr)))
            setattr(obj, attr, replacement)

        def block(name):
            def _raise(*_a, **_k):
                self.attempts.append(name)
                raise AssertionError(f"network guard: {name}")
            return _raise

        if not self.allowed_hosts:
            patch(httpx.HTTPTransport, "handle_request", block("httpx.HTTPTransport.handle_request"))
            patch(httpx.Client, "send", block("httpx.Client.send"))
        real_getaddrinfo, real_connect = socket.getaddrinfo, socket.socket.connect

        def guarded_getaddrinfo(host, *a, **k):
            name = str(host).lower()
            if name in _LOOPBACK:
                return real_getaddrinfo(host, *a, **k)
            if name in self.allowed_hosts:
                result = real_getaddrinfo(host, *a, **k)
                allowed_addresses.update(str(info[4][0]) for info in result)
                self.allowed.append(f"getaddrinfo:{host}")
                return result
            self.attempts.append(f"getaddrinfo:{host}")
            raise AssertionError(f"network guard: DNS lookup for {host}")

        def guarded_connect(sock, address):
            host = address[0] if isinstance(address, tuple) else str(address)
            if isinstance(address, tuple) and str(host) not in _LOOPBACK and str(host) not in allowed_addresses:
                self.attempts.append(f"connect:{host}")
                raise AssertionError(f"network guard: connect to {host}")
            return real_connect(sock, address)

        patch(socket, "getaddrinfo", guarded_getaddrinfo)
        patch(socket.socket, "connect", guarded_connect)
        return self

    def __exit__(self, *exc):
        for obj, attr, original in reversed(self._saved):
            setattr(obj, attr, original)
        return False


def _status(run_id: str, output_root: str) -> dict:
    from comqutor_alpha.graph_engine.alpha_relevance_judgment import (
        verify_relevance_judgments,  # noqa: PLC0415
    )
    from comqutor_alpha.storage.file_store import (  # noqa: PLC0415
        load_json_record_if_exists,
        run_dir_for,
        validate_run_id_for_path,
    )

    safe = validate_run_id_for_path(run_id)
    matches = (load_json_record_if_exists(safe, "alpha_matches.json", output_root=output_root) or {}).get("matches") or []
    metadata = load_json_record_if_exists(safe, "metadata.json", output_root=output_root) or {}
    verification = verify_relevance_judgments(run_dir_for(safe, output_root), run_id=safe, ticker=str(metadata.get("ticker") or ""), matches=matches)
    return {"status": "ok", "run_id": safe, "relevance_judgments": verification.summary()}


def _live_provider_hosts() -> tuple[str, ...]:
    """LIVE only: load the repository .env (values are never printed) and return the configured provider host."""
    try:
        from dotenv import load_dotenv  # noqa: PLC0415
    except ImportError:
        load_dotenv = None
    if load_dotenv is not None and (REPO_ROOT / ".env").is_file():
        load_dotenv(REPO_ROOT / ".env", override=False)
    from comqutor_alpha.structure_engine.week2_llm import (
        resolve_server_week2_settings,  # noqa: PLC0415
    )
    from tradingagents.llm_clients.openai_client import (
        OPENAI_COMPATIBLE_PROVIDERS,  # noqa: PLC0415
    )

    settings = resolve_server_week2_settings()
    base_url = settings.get("base_url") or getattr(OPENAI_COMPATIBLE_PROVIDERS.get(str(settings.get("provider"))), "base_url", None)
    host = urlparse(str(base_url or "")).hostname
    return (host,) if host else ()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p_judge = sub.add_parser("judge")
    p_judge.add_argument("--run", required=True)
    p_judge.add_argument("--output-root", required=True)
    p_judge.add_argument("--experiment", required=True, choices=sorted(ex.EXPERIMENT_CONFIGS), help="explicit experiment configuration; there is no default")
    p_status = sub.add_parser("status")
    p_status.add_argument("--run", required=True)
    p_status.add_argument("--output-root", required=True)
    p_plan = sub.add_parser("run-plan")
    p_plan.add_argument("--mode", required=True, choices=ex.EVAL_MODES, help="explicit: SIMULATED_REHEARSAL or LIVE; there is no default")
    p_plan.add_argument("--plan", required=True)
    p_plan.add_argument("--manifest", required=True)
    p_plan.add_argument("--authorization", required=True)
    p_plan.add_argument("--eval-root", required=True)
    p_plan.add_argument("--experiment", required=True, choices=sorted(ex.EVALUATION_CONFIGS))
    args = parser.parse_args()
    allowed: tuple[str, ...] = ()
    if args.command == "run-plan" and args.mode == ex.EVAL_MODE_LIVE:
        allowed = _live_provider_hosts()
        if not allowed:
            print(json.dumps({"status": "failed", "error_code": "LIVE_PROVIDER_HOST_UNKNOWN"}, indent=1))
            return 1
    result: dict[str, Any]
    with NetworkGuard(allowed) as guard:
        try:
            if args.command == "judge":
                result = ex.judge_run_relevance(args.run, output_root=args.output_root, config=ex.EXPERIMENT_CONFIGS[args.experiment])
            elif args.command == "run-plan":
                result = ex.run_relevance_evaluation_plan(plan_path=args.plan, manifest_path=args.manifest, authorization_path=args.authorization,
                                                          eval_root=args.eval_root, mode=args.mode, config=ex.EVALUATION_CONFIGS[args.experiment])
            else:
                result = _status(args.run, args.output_root)
        except ValueError as exc:
            result = {"status": "failed", "error_code": str(exc).split(":", 1)[0]}
    result["network_guard_attempts"] = guard.attempts
    result["network_guard_allowed_hosts"] = list(allowed)
    print(json.dumps(result, indent=1, ensure_ascii=False, default=str))
    return 0 if result.get("status") in ("ok", "disabled") and not guard.attempts else 1


if __name__ == "__main__":
    raise SystemExit(main())
