#!/usr/bin/env python3
"""T3 closeout: build the single T3 delivery ZIP (zero network).

Contents keep their repository-relative paths, except this round's code, which goes under code/ (after/, diff/, reference/) so that the
unpacked tree is never mistaken for a code checkout. Adds dependencies.txt (python version + pip freeze), MANIFEST.json and SHA256SUMS.txt
(every file but SHA256SUMS.txt itself). Never includes .env, caches or the delivery directory itself.

    python build_delivery_zip.py --out <closeout>/delivery/T3_delivery_<execution>.zip
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
EXECUTION_ID = "t3joint-20261008T170322Z-bd99811e"
D = "docs/audit_artifacts/round_source_linking_t0_t2"
CLOSEOUT = f"{D}/{HERE.parent.name}"
RUNS = ("034a0a60-430e-41f8-8321-03a11389707a", "1bad76a7-72ac-4c8b-8189-2e5c0f1a6105", "c904d4cc-dc09-495c-aec5-b056979948e1")
DIRECTORIES = (CLOSEOUT, f"{D}/round25_t3_minimal_prep_20261008", f"outputs/t3_joint_evaluations/{EXECUTION_ID}",
               f"outputs/t3_joint_evaluations/{EXECUTION_ID}-materials")
FILES = (
    *(f"outputs/runs/{run}/{name}.json" for run in RUNS for name in ("structured_agent_outputs", "source_registry", "market_data_snapshot")),
    f"{D}/t3_joint_sample_driver.py", f"{D}/t3_diagnostic_evaluation_driver.py", f"{D}/t3_joint_verification_driver.py",
    f"{D}/alpha_classifier_prompt_v7_diff.patch", f"{D}/t3live_20261001T014648Z_1fb9c9d5_prompt_v7_adjudication.md",
    f"{D}/t3_prompt_v7_limited_verification_final_index.md", f"{D}/t3_a304_a101_a103_root_cause_analysis_2026-09-29.md",
    f"{D}/t3_model_config_comparison_2026-09-30.md",
    "docs/specs/product_decisions_and_unknowns.md", "docs/specs/semantic_authority_matrix.csv",
)
CODE_AFTER = (
    "comqutor_alpha/structure_engine/content_support_llm.py", "comqutor_alpha/structure_engine/week2_llm.py",
    "comqutor_alpha/structure_engine/structured_output_adapter.py", "comqutor_alpha/structure_engine/week2_execution_profile.py",
    "comqutor_alpha/llm_runtime/contracts.py", "comqutor_alpha/replay/source_bundle.py",
    "tests/test_t3_closeout_content_support_citation_and_ledger.py", "tests/test_week2_execution_profile.py",
    "tests/test_t3_closeout_relation_and_opposition_consumption.py",
)
CODE_REFERENCE = ("comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml",)
EXCLUDED_PARTS = {"__pycache__", ".DS_Store", "delivery"}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def collect() -> dict[str, Path]:
    entries: dict[str, Path] = {}
    for directory in DIRECTORIES:
        for path in sorted((REPO / directory).rglob("*")):
            rel = path.relative_to(REPO)
            if path.is_file() and not (set(rel.parts) & EXCLUDED_PARTS) and path.suffix != ".pyc":
                entries[rel.as_posix()] = path
    for rel in FILES:
        entries[rel] = REPO / rel
    for rel in CODE_AFTER:
        entries[f"code/after/{rel}"] = REPO / rel
    for rel in CODE_REFERENCE:
        entries[f"code/reference/{rel}"] = REPO / rel
    for name in ("closeout_minimal.diff", "closeout_tests_new.diff"):
        entries[f"code/diff/{name}"] = REPO / CLOSEOUT / "06_code" / name
    missing = [rel for rel, path in entries.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing package inputs: {missing}")
    if any(Path(rel).name == ".env" for rel in entries):
        raise ValueError(".env must never be packaged")
    return entries


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out).resolve()
    if out.exists():
        print("refusing: output exists", out, file=sys.stderr)
        return 2
    entries = collect()
    freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True, check=True).stdout
    generated = {
        "README.md": (REPO / CLOSEOUT / "README.md").read_bytes(),
        "dependencies.txt": (f"python {platform.python_version()} ({sys.executable.replace(str(REPO), '<repo>')})\n"
                             f"platform {platform.platform()}\n# pip freeze of the repository .venv\n{freeze}").encode(),
    }
    blobs = {rel: path.read_bytes() for rel, path in entries.items()}
    blobs.update(generated)
    manifest = {"built_at": datetime.now(timezone.utc).isoformat(), "execution_id": EXECUTION_ID,
                "main_report": f"{CLOSEOUT}/00_T3_main_report.md", "file_count": len(blobs),
                "files": {rel: {"sha256": _sha(data), "bytes": len(data)} for rel, data in sorted(blobs.items())}}
    blobs["MANIFEST.json"] = (json.dumps(manifest, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    sums = "".join(f"{_sha(data)}  {rel}\n" for rel, data in sorted(blobs.items()))
    blobs["SHA256SUMS.txt"] = sums.encode("utf-8")
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel in sorted(blobs):
            info = zipfile.ZipInfo(rel, date_time=(2026, 10, 8, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, blobs[rel])
    print(json.dumps({"zip": str(out.relative_to(REPO)), "files": len(blobs), "zip_bytes": out.stat().st_size, "zip_sha256": _sha(out.read_bytes())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
