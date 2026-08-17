#!/usr/bin/env python3
"""Build the Provider-zero Phase 1 human-review packet v3 (evidence-alignment fix)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.evaluation.phase1_human_review_packet_v3 import (  # noqa: E402
    HumanReviewPacketError,
    build_review_packet,
)

MASTER_STATE_PATH = REPO_ROOT / "docs/audit_artifacts/phase1_master/phase1_master_state.json"


def _evaluation_dir_from_state(state_path: Path) -> Path:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    relative = state.get("evaluation_dir")
    if not isinstance(relative, str) or not relative:
        raise ValueError("phase1_master_state.json has no evaluation_dir")
    return (REPO_ROOT / relative).resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evaluation-dir",
        type=Path,
        default=None,
        help="Defaults to phase1_master_state.json evaluation_dir.",
    )
    parser.add_argument("--context-chars", type=int, default=350)
    args = parser.parse_args(argv)

    evaluation_dir = (
        args.evaluation_dir.resolve()
        if args.evaluation_dir is not None
        else _evaluation_dir_from_state(MASTER_STATE_PATH)
    )
    try:
        verification = build_review_packet(
            evaluation_dir,
            master_state_path=MASTER_STATE_PATH,
            context_chars=args.context_chars,
        )
    except HumanReviewPacketError as exc:
        print(exc.reason_code)
        print(exc.detail)
        print("HUMAN_REVIEW_PACKET_V3_READY=NO")
        print("PROVIDER_CALLS=0")
        return 2

    coverage = verification["coverage"]
    outputs = verification["outputs"]
    print("HUMAN_REVIEW_PACKET_V3_READY=YES")
    print(f"REPORTS_INCLUDED={coverage['total_reports']}")
    print(f"CLAIMS_INCLUDED={coverage['total_claims']}")
    print(f"CSV:\n{outputs['csv']}")
    print(f"HTML:\n{outputs['html']}")
    print(f"INSTRUCTIONS:\n{outputs['instructions']}")
    print("PROVIDER_CALLS=0")
    print("STATE=WAITING_FOR_HUMAN_REVIEW")
    print("SEMANTIC_QUALITY=UNPROVEN_V3")
    print("HUMAN_REVIEW=PENDING_V3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
