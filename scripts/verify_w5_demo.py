#!/usr/bin/env python3
"""Verify the isolated W5 demo artifacts, database cache, and API read contracts."""

from __future__ import annotations

import importlib

_seed = importlib.import_module("scripts.seed_w5_demo" if __package__ else "seed_w5_demo")
DemoSeedError = _seed.DemoSeedError
_parser = _seed._parser
resolve_demo_targets = _seed.resolve_demo_targets
verify_w5_demo = _seed.verify_w5_demo


def main() -> int:
    args = _parser("Verify isolated W5 NVDA and QQQ demo runs.").parse_args()
    try:
        targets = resolve_demo_targets(
            args.output_root,
            args.database_url,
            allow_unsafe_target=args.allow_unsafe_target,
        )
        results = verify_w5_demo(targets)
    except (DemoSeedError, FileNotFoundError, ValueError) as exc:
        print(f"W5_DEMO_VERIFY_FAILED: {exc}")
        return 1

    print("W5_DEMO_VERIFY_OK")
    for result in results:
        print(
            f"{result['ticker']}: status={result['status']} "
            f"graph={result['structure_graph_status']} "
            f"conflicts={result['conflict_status']} "
            f"main_conflict={result['main_conflict']}"
        )
    print("live_provider_used=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
