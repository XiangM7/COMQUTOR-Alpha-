#!/usr/bin/env python3
"""T2 John version (2026-10-09): assemble the package directory from read-only originals.

Standard library only. Writes only under --pkg (must not exist yet) and --staging. Never writes into outputs/, the Round 23
directory, the uploaded ZIPs or the T1 archive; no network, no services, no research.

Sources (all read-only):
  * ~/Desktop/t2.zip                      -> 01_John对T2的要求.md, 02_签收标准.md, 原文/, 规则文件/ (original bytes)
  * Round 23 directory in the repository  -> 我方对应交付/round23_t2_completion_20261007/ (byte-identical to the t2.zip copy;
                                             checked here); two reader documents then get the John-reader edits listed in EDITS
  * outputs/runs/<run_id>/ (5 runs)        -> 历史输入/outputs/runs/<run_id>/ (byte copy, mtimes kept)
  * T1 run archive round22_runs.tar.gz    -> 历史输入/outputs/runs/d5b60b8a-.../ (AMD; regular members only, macOS '._' metadata
                                             members skipped)
  * Round 22 run_directory_hashes/d5b60b8a.json -> 核查记录/历史哈希/ (original bytes; the only historical input hash record)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[5]
HOME = Path.home()
ROUND_DIR = REPO / "docs/audit_artifacts/round_source_linking_t0_t2"
R23 = ROUND_DIR / "round23_t2_completion_20261007"
R23_NAME = R23.name
T2_ZIP = HOME / "Desktop/t2.zip"
T1_ARCHIVE = HOME / "Desktop/t1/我方对应交付/运行产物打包/round22_runs.tar.gz"
T1_ARCHIVE_IN_PACKAGE = "t1/我方对应交付/运行产物打包/round22_runs.tar.gz"  # its path inside the uploaded t1.zip
R22_AMD_HASHES = ROUND_DIR / "round22_t1_closeout_20261007/run_directory_hashes/d5b60b8a-66b8-44c1-9f55-ee345e58c48d.json"
R22_MANIFEST = ROUND_DIR / "round22_t1_closeout_20261007/release_manifest_v2.json"
RUNS = {  # ticker -> run_id, exactly as Round 23 formal_acceptance_verdicts.json inputs.runs
    "NVDA": "ded99ecd-a186-4a90-859e-0f1a0efa43db",
    "QQQ": "0d890564-2479-4361-94e8-25c48af3b9a8",
    "SNDK": "e8e0f398-7b26-4462-8135-a1410ea5b335",
    "MSFT": "64568bfb-fe0c-453c-9872-831a8dc339a0",
    "TSM": "fc09821e-c7cf-40a7-bd76-c98172e16992",
    "AMD": "d5b60b8a-66b8-44c1-9f55-ee345e58c48d",
}
SKIP_NAMES = {".DS_Store"}

# John-reader edits: (file inside the Round 23 copy, old text, new text, reason). Each old text must occur exactly once.
NOTE_REPORT = (
    "> **John 版说明（2026-10-09 整理）**：本文件是 Round 23 报告的读者版，只改了面向内部的措辞（逐条见包根 "
    "`核查记录/文档修改记录.json`）；判定、数字、失败与限制都没有改。报告里说“只读 `outputs/runs/`”的六个历史 run，"
    "现已随包提供在包根 `历史输入/outputs/runs/`，清单见 `历史输入/run_inventory.md`。\n\n"
)
NOTE_README = (
    "> **John 版说明（2026-10-09 整理）**：本文件中的命令都需要**原仓库环境**——Round 23 执行时的仓库工作区代码与 `.venv`；"
    "只靠本 ZIP 不能运行。`t2_changes.patch` 只含 T2 的 37 个文件，Round 23 工作区里更早轮次未提交的改动不在本包内，"
    "“HEAD `7a9aefa` + 补丁”是否足以运行这些命令没有验证过；仓库当前工作区已含后续改动，也不等于 Round 23 代码（见包根 `README.md` 第 2 节）。"
    "只用本包即可执行的检查见包根 `README.md` 第 1 节。六个历史 run 已随包提供在包根 `历史输入/outputs/runs/`，"
    "上面三个入口都有 `--runs-root` 参数可以指向它（本次整理没有执行）。\n\n"
)
EDITS = [
    ("01_中文简明验收报告_T2.md",
     "# COMQUTOR Alpha — Round 23：T2（完成规则执行）简明验收报告\n\n",
     "# COMQUTOR Alpha — Round 23：T2（完成规则执行）简明验收报告\n\n" + NOTE_REPORT,
     "加读者说明：收件人与版本、六个输入现已随包提供"),
    ("01_中文简明验收报告_T2.md",
     "HEAD `7a9aefa`，**未 commit / push**。",
     "HEAD `7a9aefa`，**没有 commit**。",
     "删去面向内部的 push 指示；保留“没有 commit”这一事实"),
    ("01_中文简明验收报告_T2.md",
     "显式读取你指定的规则文件；",
     "显式读取调用方指定的规则文件；",
     "“你”原指内部读者，改为中性说法"),
    ("01_中文简明验收报告_T2.md",
     "label 用**你指定的那份** taxonomy 校验",
     "label 用**调用方指定的那份** taxonomy 校验",
     "“你”原指内部读者，改为中性说法"),
    ("01_中文简明验收报告_T2.md",
     "；三个入口的网络调用尝试数 0；8000／5175 以及只读 viewer 8001／5176 仍在监听同一批进程）。",
     "；三个入口的网络调用尝试数 0）。",
     "删除服务操作文字（本地服务端口监听情况）；该检查仍原样保存在技术证据 `final_scope_proofs.json` 中"),
    ("01_中文简明验收报告_T2.md",
     "## 6. 我替 John 定的几件事（依据分开写）与待 John 定\n\n| 事项 | 我定了什么 | 依据 |",
     "## 6. 实现时采用的做法（依据分开写，均需 John 确认）与待 John 定\n\n| 事项 | 采用的做法 | 依据 |",
     "“我替 John 定”是对内措辞；改为“实现时采用的做法，需 John 确认”。表内做法与依据未改"),
    ("01_中文简明验收报告_T2.md",
     "若是后者，需要 John 给出各标的的清单——现在任何规则文件里都没有。",
     "若是后者，需要 John 给出各标的的清单——现在任何规则文件里都没有。"
     "（**读者注，2026-10-09**：本包 `规则文件/` 中的 label 文件确有各标的的 Alpha 列表——v0.1 的 "
     "`expected_positive_alphas` / `expected_negative_alphas` / `conditional_alphas`，v0.2 的 `positive_alphas` / "
     "`negative_alphas` / `conditional_alphas`；v0.2 文件头注释把它们写成“该标的预期的 Alpha”，而不是“某个 run 必须激活的 "
     "Alpha”。Round 23 没有用这些列表做 Alpha 层漏检判定。原句保留，这里只补充事实。）",
     "原句与包内规则文件的事实不完全一致；保留原句并加标注，不改判定"),
    ("README_T2.md",
     "# Round 23 / T2 交付 README（可复制执行）\n\n",
     "# Round 23 / T2 交付 README（可复制执行）\n\n" + NOTE_README,
     "加读者说明：命令需要原仓库环境；包内检查见包根 README；六个输入已随包提供"),
    ("README_T2.md",
     "不写 `outputs/`，不 commit / push。",
     "不写 `outputs/`。",
     "删去面向内部的 commit / push 指示"),
    ("README_T2.md",
     "、三个入口的**零网络调用陷阱**、用户服务仍在监听 |",
     "、三个入口的**零网络调用陷阱** |",
     "删除服务操作文字；该检查仍原样保存在 `final_scope_proofs.json` 中"),
    ("README_T2.md",
     "* **显式读取你指定的规则文件**：",
     "* **显式读取调用方指定的规则文件**：",
     "“你”原指内部读者，改为中性说法"),
    ("README_T2.md",
     "* **没有 commit**（按指示）：",
     "* **没有 commit**：",
     "删去内部指示措辞“按指示”；保留“没有 commit”这一事实"),
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def run_digest(per_file: dict[str, str]) -> str:
    return sha256_bytes("\n".join(f"{rel}\t{per_file[rel]}" for rel in sorted(per_file)).encode())


def dir_hashes(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): sha256_file(p) for p in sorted(root.rglob("*")) if p.is_file()}


def extract_t2_zip(staging: Path) -> Path:
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    with zipfile.ZipFile(T2_ZIP) as z:
        for info in z.infolist():
            name = info.filename
            if not info.flag_bits & 0x800:  # macOS Archive Utility stores UTF-8 names without the UTF-8 flag
                name = name.encode("cp437").decode("utf-8")
            if name.startswith("__MACOSX/") or name.endswith("/") or name.rsplit("/", 1)[-1] in SKIP_NAMES:
                continue
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(info))
    return staging / "t2"


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def copy_tree(src: Path, dst: Path) -> int:
    n = 0
    for p in sorted(src.rglob("*")):
        if p.is_file() and p.name not in SKIP_NAMES:
            copy_file(p, dst / p.relative_to(src))
            n += 1
    return n


def extract_amd(pkg_runs: Path, run_id: str) -> dict:
    prefix = f"outputs/runs/{run_id}/"
    extracted, skipped = 0, 0
    with tarfile.open(T1_ARCHIVE, "r:gz") as t:
        for m in t.getmembers():
            if not m.isfile() or not (m.name.startswith(prefix) or m.name == f"outputs/runs/._{run_id}"):
                continue
            if m.name.rsplit("/", 1)[-1].startswith("._"):
                skipped += 1
                continue
            rel = m.name[len(prefix):]
            if ".." in Path(rel).parts or rel.startswith("/"):
                raise SystemExit(f"unsafe member {m.name}")
            target = pkg_runs / run_id / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(t.extractfile(m).read())
            os.utime(target, (m.mtime, m.mtime))
            extracted += 1
    return {"extracted": extracted, "appledouble_skipped": skipped}


def apply_edits(pkg_r23: Path, original_r23: Path) -> list[dict]:
    by_file: dict[str, list[tuple[str, str, str]]] = {}
    for rel, old, new, reason in EDITS:
        by_file.setdefault(rel, []).append((old, new, reason))
    log = []
    for rel, edits in by_file.items():
        original = (original_r23 / rel).read_bytes()
        text = original.decode("utf-8")
        changes = []
        for old, new, reason in edits:
            count = text.count(old)
            if count != 1:
                raise SystemExit(f"edit anchor occurs {count} times in {rel}: {old[:60]!r}")
            text = text.replace(old, new)
            changes.append({"removed_or_replaced": old, "now": new, "reason": reason})
        (pkg_r23 / rel).write_bytes(text.encode("utf-8"))
        log.append({"package_path": f"我方对应交付/{R23_NAME}/{rel}", "original_path_in_repository": f"docs/audit_artifacts/round_source_linking_t0_t2/{R23_NAME}/{rel}",
                    "original_sha256": sha256_bytes(original), "new_sha256": sha256_file(pkg_r23 / rel), "changes": changes})
    return log


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkg", required=True)
    ap.add_argument("--staging", required=True)
    args = ap.parse_args(argv)
    pkg, staging = Path(args.pkg), Path(args.staging)
    if pkg.exists():
        raise SystemExit(f"{pkg} already exists; refusing to overwrite")
    report: dict = {"built_at": datetime.now(UTC).isoformat(), "steps": []}

    # 1. the uploaded t2.zip: wrapper files and rule copies keep their uploaded bytes; its Round 23 copy must equal the repository's
    t2 = extract_t2_zip(staging)
    zip_r23 = dir_hashes(t2 / "我方对应交付" / R23_NAME)
    repo_r23 = dir_hashes(R23)
    if zip_r23 != repo_r23:
        raise SystemExit("Round 23 copy inside t2.zip differs from the repository directory")
    report["steps"].append({"t2_zip_sha256": sha256_file(T2_ZIP), "round23_files": len(repo_r23), "round23_copy_in_t2_zip_equals_repository": True})
    for name in ("01_John对T2的要求.md", "02_签收标准.md"):
        copy_file(t2 / name, pkg / name)
    copy_tree(t2 / "原文", pkg / "原文")
    copy_tree(t2 / "规则文件", pkg / "规则文件")

    # 2. Round 23 delivery (repository original), then the John-reader edits of two reader documents
    pkg_r23 = pkg / "我方对应交付" / R23_NAME
    n = copy_tree(R23, pkg_r23)
    edit_log = apply_edits(pkg_r23, R23)
    report["steps"].append({"round23_copied_files": n, "reader_documents_edited": [e["package_path"] for e in edit_log]})

    # the John entry and README (written for this version; templates kept in tools/john_docs/)
    for name in ("00_先看这里.md", "README.md"):
        copy_file(TOOLS / "john_docs" / name, pkg / name)

    # 3. the six historical input runs
    pkg_runs = pkg / "历史输入" / "outputs" / "runs"
    for ticker, run_id in RUNS.items():
        if ticker == "AMD":
            info = extract_amd(pkg_runs, run_id)
            report["steps"].append({"run": run_id, "ticker": ticker, "source": f"T1 archive {T1_ARCHIVE_IN_PACKAGE}", **info})
        else:
            src = REPO / "outputs" / "runs" / run_id
            if not src.is_dir():
                report["steps"].append({"run": run_id, "ticker": ticker, "missing": True})
                continue
            report["steps"].append({"run": run_id, "ticker": ticker, "source": f"outputs/runs/{run_id}", "copied": copy_tree(src, pkg_runs / run_id)})

    # 4. the only historical input-hash record (Round 22, AMD), original bytes
    copy_file(R22_AMD_HASHES, pkg / "核查记录" / "历史哈希" / "round22_run_directory_hashes_d5b60b8a.json")
    manifest = json.loads(R22_MANIFEST.read_text(encoding="utf-8"))
    excerpt = {
        "source": "docs/audit_artifacts/round_source_linking_t0_t2/round22_t1_closeout_20261007/release_manifest_v2.json",
        "source_sha256": sha256_file(R22_MANIFEST),
        "schema_version": manifest.get("schema_version"),
        "registered_run_ids": sorted(manifest["runs"]),
        "six_t2_runs_registered": {t: (rid in manifest["runs"]) for t, rid in RUNS.items()},
        "amd_directory_entry": manifest["runs"][RUNS["AMD"]]["directory"],
        "note": "Excerpt written 2026-10-09 by tools/build_package.py; values copied verbatim from the source manifest. "
                "Only AMD of the six Round 23 input runs is registered there; no earlier record hashes the other five.",
    }
    (pkg / "核查记录" / "历史哈希" / "round22_release_manifest_v2_excerpt.json").write_text(json.dumps(excerpt, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    (pkg / "核查记录").mkdir(parents=True, exist_ok=True)
    edit_doc = {
        "recipient": "John",
        "scope": "Reader documents of the Round 23 copy. Every other Round 23 file, the wrapper copies from t2.zip and all six input runs keep their original bytes.",
        "edited_documents": edit_log,
        "replaced_documents": [{
            "package_path": "00_先看这里.md",
            "original": "t2.zip: t2/00_先看这里.md",
            "original_sha256": sha256_file(t2 / "00_先看这里.md"),
            "reason": "Rewritten as the single entry for John (what Round 23 changed, the six inputs, actual results, limits). The old entry "
                      "addressed the internal reader (repository-root commands, Desktop folder locations, 'no commit (as instructed)').",
        }],
        "technical_evidence_not_edited": [
            f"我方对应交付/{R23_NAME}/final_scope_proofs.json still records the local service-port check (services_listening) made during Round 23",
            f"我方对应交付/{R23_NAME}/t2_files.json field 'commit' still reads 'none was made (instruction: no commit)'",
            f"我方对应交付/{R23_NAME}/final_scope_proofs.py docstring says the six pinned runs are among the 16 Round 22-registered runs; only AMD is (see 历史输入/run_inventory.md)",
        ],
        "uploaded_archives_modified": False,
    }
    (pkg / "核查记录" / "文档修改记录.json").write_text(json.dumps(edit_doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (TOOLS.parent / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
