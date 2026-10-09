#!/usr/bin/env python3
"""T3 closeout: compare the working tree's code identity with the identity pinned in the execution's signed plan (zero network).

Before the closeout changes this must be equal (the closeout starts from exactly the code the execution ran); after them it must differ
ONLY in the files the closeout changed -- the execution itself stays interpreted under its frozen identity.

    python check_execution_code_identity.py --out hash_proof/code_identity_before_changes.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
DRIVER = REPO / "docs/audit_artifacts/round_source_linking_t0_t2/t3_joint_sample_driver.py"
PLAN = REPO / ("docs/audit_artifacts/round_source_linking_t0_t2/round25_t3_minimal_prep_20261008/B4_execution/"
               "authorized_plan_SIGNED_t3joint-20261008T170322Z-bd99811e.json")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    spec = importlib.util.spec_from_file_location("t3_joint_driver_identity", DRIVER)
    assert spec is not None and spec.loader is not None
    driver = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = driver
    spec.loader.exec_module(driver)
    pinned = json.loads(PLAN.read_text(encoding="utf-8"))["code_identity"]
    now = driver.code_identity()
    differing = sorted(k for k in set(now) | set(pinned) if now.get(k) != pinned.get(k))
    doc = {"equals_execution_plan": not differing, "differing_keys": differing, "pinned": pinned, "now": now}
    Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"equals_execution_plan": not differing, "differing_keys": differing}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
