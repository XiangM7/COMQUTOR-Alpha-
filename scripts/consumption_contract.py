#!/usr/bin/env python3
"""Operator entry: recompute a SAVED run under an explicitly chosen evidence contract, and roll it back (no hand-edited metadata).

This is a recomputation of saved inputs -- NOT a Fresh Run. A fail-closed guard blocks every Provider / network path (HTTP transports,
the Week2 LLM gateway, non-loopback DNS) while it runs; the database must be an isolated ``*_test`` database named explicitly
(``COMQUTOR_DATABASE_URL`` + ``COMQUTOR_REQUIRE_DATABASE_NAME``); the output root must be OUTSIDE the repository's ``outputs/`` tree.

  copy-saved-run --run-dir <saved run dir> --output-root <verification root>
  derive   --source-run <run id> --output-root <root> --contract v2|legacy [--execution-id <id>]
  rollback --execution <execution id> --output-root <root>
  status   --execution <execution id> --output-root <root>
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha import consumption_recompute as cr  # noqa: E402


class ZeroCallGuard:
    """Fails closed on any Provider / network path and counts the attempts (loopback DNS stays allowed for the local test database)."""

    def __enter__(self):
        import httpx  # noqa: PLC0415

        from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway  # noqa: PLC0415

        self.attempts: list[str] = []
        self._saved: list[tuple[object, str, object]] = []

        def block(name):
            def _raise(*_a, **_k):
                self.attempts.append(name)
                raise AssertionError(f"zero-call guard: {name}")
            return _raise

        def patch(obj, attr, name):
            self._saved.append((obj, attr, getattr(obj, attr)))
            setattr(obj, attr, block(name))

        patch(httpx.HTTPTransport, "handle_request", "httpx.HTTPTransport.handle_request")
        patch(httpx.Client, "send", "httpx.Client.send")
        for method in ("invoke_json", "invoke_json_with_trace", "invoke_prebuilt_json_prompt"):
            if hasattr(Week2LLMGateway, method):
                patch(Week2LLMGateway, method, f"Week2LLMGateway.{method}")
        real_getaddrinfo = socket.getaddrinfo

        def guarded(host, *a, **k):
            if str(host) not in ("localhost", "127.0.0.1", "::1"):
                self.attempts.append(f"getaddrinfo:{host}")
                raise AssertionError(f"zero-call guard: DNS lookup for {host}")
            return real_getaddrinfo(host, *a, **k)

        self._saved.append((socket, "getaddrinfo", real_getaddrinfo))
        socket.getaddrinfo = guarded
        return self

    def __exit__(self, *exc):
        for obj, attr, original in reversed(self._saved):
            setattr(obj, attr, original)
        return False


def _repository(output_root: str):
    cr.require_isolated_test_database()
    from comqutor_alpha.storage.db.repository import (
        build_write_repository_from_env,  # noqa: PLC0415
    )

    return build_write_repository_from_env(str(output_root))


def _status(execution_id: str, output_root: str) -> dict:
    root = Path(output_root).expanduser().resolve()
    run_dir = root / execution_id

    def load(name):
        path = run_dir / name
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    metadata = load("metadata.json") or {}
    graph = load("structure_graph.json") or {}
    summary = graph.get("evidence_consumption") or {}
    return {
        "execution_run_id": execution_id,
        "execution_type": metadata.get("execution_type"),
        "based_on_run_id (source identity)": metadata.get("based_on_run_id"),
        "root_research_run_id": metadata.get("root_research_run_id"),
        "alpha_evidence_consumption": metadata.get("alpha_evidence_consumption"),
        "stance_ledger_binding (declared)": metadata.get("stance_ledger_binding"),
        "saved_input_recompute": metadata.get("saved_input_recompute"),
        "consumption_summary": {k: summary.get(k) for k in ("contract", "positive_admission", "stance", "ledger", "attribution") if k in summary} or None,
        "rollback_record": load("consumption_rollback.json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p_copy = sub.add_parser("copy-saved-run")
    p_copy.add_argument("--run-dir", required=True)
    p_copy.add_argument("--output-root", required=True)
    p_derive = sub.add_parser("derive")
    p_derive.add_argument("--source-run", required=True)
    p_derive.add_argument("--output-root", required=True)
    p_derive.add_argument("--contract", required=True, choices=sorted(cr.CONTRACT_CHOICES), help="explicit operator choice; there is no default")
    p_derive.add_argument("--execution-id")
    p_rollback = sub.add_parser("rollback")
    p_rollback.add_argument("--execution", required=True)
    p_rollback.add_argument("--output-root", required=True)
    p_status = sub.add_parser("status")
    p_status.add_argument("--execution", required=True)
    p_status.add_argument("--output-root", required=True)
    args = parser.parse_args()
    try:
        if args.command == "copy-saved-run":
            result = cr.copy_saved_run(args.run_dir, args.output_root)
        elif args.command == "status":
            result = _status(args.execution, args.output_root)
        else:
            cr.refuse_real_outputs(args.output_root)
            repository = _repository(args.output_root)
            with ZeroCallGuard() as guard:
                if args.command == "derive":
                    result = cr.derive_consumption_execution(args.source_run, contract=args.contract, output_root=args.output_root,
                                                             graph_repository=repository, execution_id=args.execution_id)
                else:
                    result = cr.rollback_consumption_execution(args.execution, output_root=args.output_root, graph_repository=repository)
            result["zero_call_guard_attempts"] = guard.attempts
            if guard.attempts:
                result["status"] = "failed"
                result["error_code"] = "ZERO_CALL_GUARD_TRIGGERED"
    except ValueError as exc:
        result = {"status": "refused", "error_code": str(exc).split(":", 1)[0], "detail": str(exc)}
    print(json.dumps(result, indent=1, ensure_ascii=False, default=str))
    return 0 if result.get("status") in ("ok", None) or args.command == "status" else 1


if __name__ == "__main__":
    raise SystemExit(main())
