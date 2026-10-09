#!/usr/bin/env python3
"""T2 John version (2026-10-09): write the in-package inventory of the six Round 23 input runs.

Standard library only; reads the package copy, the Round 23 verdict file inside the package, the Round 22 hash record inside
the package and the two original-hash snapshots (hash_proof/state_before.json, state_after_copy.json); writes
<pkg>/历史输入/run_inventory.json and run_inventory.md, and copies the two snapshots to <pkg>/核查记录/原件前后哈希/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
R23_NAME = "round23_t2_completion_20261007"
T1_ARCHIVE_LABEL = "~/Desktop/t1/我方对应交付/运行产物打包/round22_runs.tar.gz (T1 run archive)"
T1_ARCHIVE_IN_PACKAGE = "t1/我方对应交付/运行产物打包/round22_runs.tar.gz"
DIGEST_ALGORITHM = 'sha256 of "\\n".join(f"{relative_path}\\t{sha256}") over the sorted files (Round 22 release manifest run_digest)'


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_digest(per_file: dict[str, str]) -> str:
    return hashlib.sha256("\n".join(f"{rel}\t{per_file[rel]}" for rel in sorted(per_file)).encode()).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkg", required=True)
    args = ap.parse_args(argv)
    pkg = Path(args.pkg)
    before = json.loads((BASE / "hash_proof/state_before.json").read_text(encoding="utf-8"))
    after = json.loads((BASE / "hash_proof/state_after_copy.json").read_text(encoding="utf-8"))
    verdicts = json.loads((pkg / "我方对应交付" / R23_NAME / "six_ticker/formal_acceptance_verdicts.json").read_text(encoding="utf-8"))
    r22 = json.loads((pkg / "核查记录/历史哈希/round22_run_directory_hashes_d5b60b8a.json").read_text(encoding="utf-8"))
    r22_excerpt = json.loads((pkg / "核查记录/历史哈希/round22_release_manifest_v2_excerpt.json").read_text(encoding="utf-8"))
    generated_at = verdicts["generated_at"]

    runs = []
    for ticker, run_id in verdicts["inputs"]["runs"].items():
        rel_dir = f"历史输入/outputs/runs/{run_id}"
        copy_dir = pkg / rel_dir
        files = sorted(p for p in copy_dir.rglob("*") if p.is_file())
        per_file = {p.relative_to(copy_dir).as_posix(): sha256_file(p) for p in files}
        meta = json.loads((copy_dir / "metadata.json").read_text(encoding="utf-8"))
        verdict = verdicts["tickers"][ticker]
        label = f"outputs/runs/{run_id}"
        orig_before, orig_after = before["directories"][label], after["directories"][label]
        entry = {
            "ticker": ticker,
            "run_id": run_id,
            "package_path": rel_dir,
            "file_count": len(files),
            "total_bytes": sum(p.stat().st_size for p in files),
            "directory_digest_sha256": run_digest(per_file),
            "files": [{"path": rel, "size": (copy_dir / rel).stat().st_size, "sha256": per_file[rel]} for rel in sorted(per_file)],
            "identity": {
                "directory_name_equals_run_id": copy_dir.name == run_id,
                "metadata_run_id": meta.get("run_id"),
                "metadata_ticker": meta.get("ticker"),
                "metadata_created_at": meta.get("created_at"),
                "round23_inputs_runs_run_id": verdicts["inputs"]["runs"][ticker],
                "round23_verdict_run_id": verdict["run_id"],
                "round23_verdict_ticker": verdict["ticker"],
                "all_match": copy_dir.name == run_id == meta.get("run_id") == verdict["run_id"] and meta.get("ticker") == ticker == verdict["ticker"],
                "round23_artifact_completeness": verdict["artifact_completeness"],
                "round23_artifact_missing_files": verdict["artifact_missing_files"],
                "round23_formal_status": verdict["verdict"]["formal_status"],
            },
            "original_in_repository": {
                "path": label,
                "file_count": orig_before["file_count"],
                "digest_before_copy": orig_before["digest_sha256"],
                "digest_after_copy": orig_after["digest_sha256"],
                "unchanged_by_copy": orig_before["digest_sha256"] == orig_after["digest_sha256"],
                "copy_equals_original_per_file": per_file == orig_before["per_file_sha256"],
                "oldest_mtime_utc": orig_before["oldest_mtime_utc"],
                "newest_mtime_utc": orig_before["newest_mtime_utc"],
            },
            "supplementary_mtime_check": {
                "round23_generated_at": generated_at,
                "all_original_files_older_than_round23_execution": orig_before["newest_mtime_utc"] < generated_at.replace("Z", "+00:00"),
                "note": "File modification times can be rewritten; this is circumstantial only, not a proof of the bytes Round 23 read.",
            },
        }
        if ticker == "AMD":
            arch_b, arch_a = before["t1_archive_amd_members"], after["t1_archive_amd_members"]
            entry["copied_from"] = {
                "kind": "T1 run archive (reused, as delivered with the T1 package)",
                "archive": T1_ARCHIVE_IN_PACKAGE,
                "archive_sha256_before": before["files"][T1_ARCHIVE_LABEL]["sha256"],
                "archive_sha256_after": after["files"][T1_ARCHIVE_LABEL]["sha256"],
                "archive_unchanged": before["files"][T1_ARCHIVE_LABEL]["sha256"] == after["files"][T1_ARCHIVE_LABEL]["sha256"],
                "member_prefix": f"outputs/runs/{run_id}/",
                "archive_member_digest_sha256": arch_b["digest_sha256"],
                "copy_equals_archive_members_per_file": per_file == arch_b["per_file_sha256"],
                "appledouble_members_skipped": arch_b["appledouble_members_excluded"],
                "appledouble_note": "macOS '._<name>' metadata entries the archiver added next to each file; not run files, not evidence.",
            }
            matches = sum(1 for rel, h in r22["files"].items() if per_file.get(rel) == h)
            entry["historical_hash"] = {
                "exists": True,
                "record": "核查记录/历史哈希/round22_run_directory_hashes_d5b60b8a.json (+ round22_release_manifest_v2_excerpt.json)",
                "recorded_by": "Round 22 release manifest v2 (2026-10-07, before Round 23 ran)",
                "recorded_file_count": r22["file_count"],
                "recorded_directory_digest_sha256": r22_excerpt["amd_directory_entry"]["directory_digest_sha256"],
                "digest_matches": run_digest(per_file) == r22_excerpt["amd_directory_entry"]["directory_digest_sha256"],
                "per_file_matches": f"{matches}/{len(r22['files'])}",
                "file_set_equal": set(per_file) == set(r22["files"]),
                "statement": "The package copy is byte-identical to the directory hashed by Round 22 before Round 23 ran.",
            }
        else:
            entry["copied_from"] = {"kind": "repository outputs/runs (byte copy, modification times kept)", "path": label}
            entry["historical_hash"] = {
                "exists": False,
                "record": None,
                "statement": "Round 23 recorded no hash of its input runs, and the Round 22 manifest does not register this run; no earlier "
                             "record hashes it. This only proves the package copy equals the current original in outputs/runs; it cannot "
                             "prove these are the exact bytes Round 23 read, and is not written up as frozen at execution time.",
            }
        runs.append(entry)

    doc = {
        "written_at": datetime.now(UTC).isoformat(),
        "recipient": "John",
        "scope": "The six input runs of Round 23 six_ticker/formal_acceptance_verdicts.json (execution t2-six-ticker-20261007, A_REEVALUATION, generated "
                 + generated_at + ").",
        "directory_digest_algorithm": DIGEST_ALGORITHM,
        "round23_final_scope_proofs_note": "Round 23 final_scope_proofs.py says the six pinned runs are among the 16 run directories registered by the "
                                           "Round 22 manifest. Only AMD is registered (see 核查记录/历史哈希/round22_release_manifest_v2_excerpt.json); "
                                           "that check therefore covered AMD only.",
        "summary": {
            "runs": len(runs),
            "all_present": all(r["file_count"] > 0 for r in runs),
            "all_identity_match": all(r["identity"]["all_match"] for r in runs),
            "all_copies_equal_current_original": all(r["original_in_repository"]["copy_equals_original_per_file"] for r in runs),
            "all_originals_unchanged_by_copy": all(r["original_in_repository"]["unchanged_by_copy"] for r in runs),
            "runs_with_historical_hash": [r["ticker"] for r in runs if r["historical_hash"]["exists"]],
            "historical_hash_matches": {r["ticker"]: r["historical_hash"]["digest_matches"] for r in runs if r["historical_hash"]["exists"]},
            "runs_without_historical_hash": [r["ticker"] for r in runs if not r["historical_hash"]["exists"]],
            "total_files": sum(r["file_count"] for r in runs),
            "total_bytes": sum(r["total_bytes"] for r in runs),
        },
        "runs": runs,
    }
    out_dir = pkg / "历史输入"
    (out_dir / "run_inventory.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    lines = [
        "# 六个历史输入 run：包内清单",
        "",
        f"Round 23 六标的判定（`我方对应交付/{R23_NAME}/six_ticker/formal_acceptance_verdicts.json`，执行 `t2-six-ticker-20261007`，"
        f"类型 A_REEVALUATION，生成于 {generated_at}）读取的六个 run，原样放在本目录 `outputs/runs/<run_id>/`。"
        "逐文件大小与 sha256 见 `run_inventory.json`。",
        "",
        "目录摘要算法与 Round 22 发布清单相同：对排序后的文件，取 `相对路径<TAB>sha256` 逐行拼接后的 sha256。",
        "",
        "| 标的 | run_id | 包内位置 | 文件数 | 字节数 | 目录摘要 sha256 | 来源 | run_id 与 Round 23 判定一致 | 复制件 = 当前原件 | 原件复制前后不变 | 历史哈希 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in runs:
        src = "T1 运行归档 `round22_runs.tar.gz`" if r["ticker"] == "AMD" else "仓库 `outputs/runs/`"
        hist = (f"有（Round 22）：摘要{'一致' if r['historical_hash']['digest_matches'] else '**不一致**'}，逐文件 {r['historical_hash']['per_file_matches']}"
                if r["historical_hash"]["exists"] else "无")
        lines.append(f"| {r['ticker']} | `{r['run_id']}` | `{r['package_path']}/` | {r['file_count']} | {r['total_bytes']:,} | `{r['directory_digest_sha256']}` | {src} | "
                     f"{'是' if r['identity']['all_match'] else '**否**'} | {'是' if r['original_in_repository']['copy_equals_original_per_file'] else '**否**'} | "
                     f"{'是' if r['original_in_repository']['unchanged_by_copy'] else '**否**'} | {hist} |")
    s = doc["summary"]
    lines += [
        "",
        f"合计 {s['runs']} 个 run、{s['total_files']} 个文件、{s['total_bytes']:,} 字节。",
        "",
        "## 各列的含义与证明力",
        "",
        "* **run_id 与 Round 23 判定一致**：目录名、run 自己的 `metadata.json`（run_id、ticker）、判定文件的 `inputs.runs` 与 `tickers.<标的>.run_id` 四处相同。"
        "Round 23 记录这六个 run 的 `artifact_completeness` 均为 pass、`artifact_missing_files` 均为空。",
        "* **复制件 = 当前原件**：包内每个文件与仓库 `outputs/runs/<run_id>/` 中的原件逐文件 sha256 相同，文件集合也相同。",
        "* **原件复制前后不变**：复制前、复制后各对原件做一次哈希快照（`核查记录/原件前后哈希/`），两次相同。",
        "* **历史哈希（AMD）**：Round 22 发布清单（2026-10-07，早于 Round 23 执行）登记了 AMD 这个 run 的 24 个文件。包内副本取自随 T1 交付的运行归档"
        f"（归档 sha256 `{runs[-1]['copied_from']['archive_sha256_before']}`），与该登记逐文件、整体摘要都一致，也与仓库当前原件一致。"
        f"归档里每个文件旁边的 macOS `._` 元数据条目（{runs[-1]['copied_from']['appledouble_members_skipped']} 个）不是 run 文件，没有放入。",
        "* **历史哈希（其余五个）**：Round 23 没有记录输入 run 的哈希，Round 22 清单也没有登记这五个 run，此前没有任何记录给它们做过哈希。"
        "因此这里**只能证明包内副本与当前原件一致**，不能证明它们就是 Round 23 执行时读到的字节，也不能写成“执行时已冻结”。",
        "* **旁证（不作为证明）**：六个原件目录里最新的文件修改时间都早于 Round 23 执行时间（见 JSON 的 `supplementary_mtime_check`）；修改时间可以被改写，只作参考。",
        "* **更正**：Round 23 的 `final_scope_proofs.py` 文档字符串说“六个固定 run 都在 Round 22 登记的 16 个 run 里”。实际只有 AMD 在其中"
        "（`核查记录/历史哈希/round22_release_manifest_v2_excerpt.json`），所以那项“登记目录未变”的检查只覆盖了 AMD。",
        "",
    ]
    (out_dir / "run_inventory.md").write_text("\n".join(lines), encoding="utf-8")

    snap_dir = pkg / "核查记录" / "原件前后哈希"
    snap_dir.mkdir(parents=True, exist_ok=True)
    for name in ("state_before.json", "state_after_copy.json"):
        shutil.copy2(BASE / "hash_proof" / name, snap_dir / name)
    print(json.dumps(s, ensure_ascii=False, indent=1))
    ok = s["all_present"] and s["all_identity_match"] and s["all_copies_equal_current_original"] and s["all_originals_unchanged_by_copy"] and all(s["historical_hash_matches"].values())
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
