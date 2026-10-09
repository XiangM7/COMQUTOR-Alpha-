#!/usr/bin/env python3
"""T4 round 33 (2026-10-09): assemble the John-version package directory from read-only sources (standard library only).

  * round32/  <- every file of the Round 32 ZIP's T4_final/ (ZIP sha256 checked first; each file checked against the Round 32
                 manifest), except the three files this version's report supersedes; two reader documents get the John-reader
                 edits in EDITS (logged with original / new sha256)
  * round33/  <- this round's 01_d1/, 02_viewer/, 03_not_sent_reconcile/, tools/; records/ (edit log, before / after hashes)
  * root      <- the John report and README (john_docs/), verify_package33.py, report_figures.json (Round 32's 61 figures with
                 their recorded values and citations + this round's figures, each citation checked against the report)

Writes only under --pkg (refuses to overwrite). Never writes into the Round 32 directory, the runs or any ZIP.

    python3 tools/build_package33.py --pkg T4_final_r33 --state-before hash_proof/state_before.json --state-after hash_proof/state_after_build.json
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

sys.dont_write_bytecode = True  # importing the package's verify_package33.py must not leave a __pycache__ in the package
BASE = Path(__file__).resolve().parent.parent
R32_ZIP = BASE.parent / "round32_t4_closure_20261009" / "T4_final_round32_20261009.zip"
R32_ZIP_SHA256 = "2597f909dfff74b0af08fb5d15b36e5cdca40d8382d398b91680742dae4f51cf"
PREFIX = "T4_final/"
SUPERSEDED = {
    "00_T4最终交付报告.md": "Round 32 main report (addressed to the project owner and John); superseded by this version's John-only report, which carries its content",
    "README.md": "Round 32 package README; superseded by this version's README",
    "report_figures.json": "Round 32 figure ledger tied to the Round 32 report; its 61 figures (ids, values, citations) are carried into this version's report_figures.json",
}
EDITS = [
    ("05_stage_disclosure/结构抽取与降级披露.md",
     """**发现的工程缺陷（未修，列为决定项）**：
- 适配器校验器 `_validate_llm_batch_enrichment` 要求每条回复必须恰好有 9 个字段，其中包括 `cited_source_id`。
- 但冻结的任务说明（prompt `week2.claim_batch_enrichment.v1`，sha256 `c6822099…`）只要求 8 个字段，**从未要求 `cited_source_id`**。线路审计中发出的请求原文也没有这个字段名。
- 因此严格按 prompt 作答的回复必然被拒：
  - attempt 8 的 30 条和晚到的 attempt 2 的 64 条，每条都是 8 个字段，校验失败点都是 `enrichment item fields do not match the strict schema`；
  - 第一次 Fresh 的 5 个返回也都是这样被拒的。
- 换句话说，**只要这个不一致存在，适配器富集永远走回退**。
- 本轮没有修，原因：
  - 修复（让校验器接受没有 `cited_source_id` 的回复，或改 prompt）会改变 Alpha 分类的输入。Alpha 分类请求里带有 factors 和 direction。
  - 第二次 Fresh 保存的 Alpha 回复对应的是确定性回退的输入；修复后同一批 claim 的请求正文会变，无法用已保存的真实回复离线复现，必须用新的真实调用才能观察。
  - 这会改变研究结果，不属于"不改研究答案的工程修复"；改 prompt 本轮也被禁止。
  - 决定项和所需验证见主报告"需要负责人决定的事项"。
""",
     """**发现的工程缺陷 D1（未修复）**：
- 适配器校验器 `_validate_llm_batch_enrichment` 要求每条回复必须恰好有 9 个字段，其中包括 `cited_source_id`。
- 但冻结的任务说明（prompt `week2.claim_batch_enrichment.v1`，sha256 `c6822099…`）只要求 8 个字段，**从未要求 `cited_source_id`**。线路审计中发出的请求原文也没有这个字段名。
- attempt 8 的 30 条和晚到的 attempt 2 的 64 条，每条都是 8 个字段，校验失败点都是 `enrichment item fields do not match the strict schema`。
- 离线定位、能证明与不能证明的范围、修复为什么超出当前边界，见 `round33/01_d1/D1_离线定位.md`。该文更正了本段原有的两处说法：
  - “严格按 prompt 作答的回复必然被拒，适配器富集永远走回退”只对严格 8 字段的回复成立；
  - “第一次 Fresh 的 5 个返回也都是这样被拒的”只说明第一失败点，其中 2 批即使补了字段也会因 direction 不合法被拒。
""",
     "John 版：去掉“列为决定项”“需要负责人决定”的对内措辞和不再适用的验证建议；指向本版 D1 定位，并标出被更正的两处说法。事实（字段、prompt、失败点）保留"),
    ("01_regressions/回归失败分析.md",
     "- 登记本身有 Round 26 的记录。Round 26 是负责人授权的 T3 收尾轮。\n",
     "- 登记本身有 Round 26（T3 收尾轮）的记录。\n",
     "John 版：去掉内部授权措辞；登记的出处（Round 26 记录）保留"),
    ("01_regressions/回归失败分析.md",
     "**不需要负责人决定的事项**：没有改任何冻结哈希；",
     "**冻结哈希**：没有改任何冻结哈希；",
     "John 版：去掉对内的决定措辞；事实不变"),
]
# this round's figures: id -> verbatim citation in the report (values come from verify_package33.r33_figures())
R33_CITED = {
    "r33.d1.fresh2.timeouts": "7 次超时（attempt 1–7）",
    "r33.d1.fresh2.not_sent_chars": "1 次未发送：输入 61,127 字符",
    "r33.d1.fresh2.rejected_in_time_segments": "1 次有回复后校验失败：attempt 8，30 段",
    "r33.d1.fresh2.control_in_time": "按时返回的一批整批通过（30/30）",
    "r33.d1.fresh2.control_late": "晚到的一批整批通过（64/64）",
    "r33.d1.fresh2.requests_identical": "重建的请求与当时发出的正文逐字节相同",
    "r33.d1.fresh1.replies_whole_pass_with_null": "补 null 后 3 批整批通过",
    "r33.d1.fresh1.replies_still_rejected": "另 2 批各有 2 条 `invalid direction`",
    "r33.d1.network_attempts": "网络陷阱拦截外部调用 0 次",
    "r33.reconcile.ledger": "账本 1220 条 = 实际发送 1204 + 同 run 缓存命中 10 + 本地拒绝 6",
    "r33.reconcile.sent": "账本 1220 条 = 实际发送 1204 + 同 run 缓存命中 10 + 本地拒绝 6",
    "r33.reconcile.cache_hits": "账本 1220 条 = 实际发送 1204 + 同 run 缓存命中 10 + 本地拒绝 6",
    "r33.reconcile.refused": "账本 1220 条 = 实际发送 1204 + 同 run 缓存命中 10 + 本地拒绝 6",
    "r33.reconcile.budget": "HTTP 尝试 1204 = 网关预算占用 1204 = 线路审计请求 1204",
    "r33.reconcile.replies": "回复 1198 行",
    "r33.reconcile.malformed_labels": "内容核验的 `malformed_response` 标签原来共 8 条：5 条未发送，3 条是模型确实返回了不合格的回复",
    "r33.reconcile.real_malformed": "内容核验的 `malformed_response` 标签原来共 8 条：5 条未发送，3 条是模型确实返回了不合格的回复",
    "r33.reconcile.consistent_statements": "其余 11 条报告原句与记录一致",
    "r33.viewer.export_sha256": "`49bd4650b60a8c9f6bf5b3d57d3baecba196889a1bfb70c1f4329ecd1b79cef3`",
    "r33.viewer.blocked": "非 GET 请求拦截 0 次，没有点击 Start Research，36 个 API 请求都是 GET",
    "r33.viewer.api_gets": "非 GET 请求拦截 0 次，没有点击 Start Research，36 个 API 请求都是 GET",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def copy_tree(src: Path, dst: Path) -> int:
    n = 0
    for p in sorted(src.rglob("*")):
        if p.is_file() and p.name != ".DS_Store" and "__pycache__" not in p.parts:
            target = dst / p.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
            n += 1
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkg", required=True)
    ap.add_argument("--state-before", required=True)
    ap.add_argument("--state-after", required=True)
    args = ap.parse_args(argv)
    pkg = Path(args.pkg)
    if pkg.exists():
        raise SystemExit(f"{pkg} exists; refusing to overwrite")
    if sha(R32_ZIP.read_bytes()) != R32_ZIP_SHA256:
        raise SystemExit("Round 32 ZIP sha256 differs from the delivered value")

    r32 = pkg / "round32"
    with zipfile.ZipFile(R32_ZIP) as z:
        manifest32 = json.loads(z.read(PREFIX + "manifest.json"))
        recorded = {f["path"]: f["sha256"] for f in manifest32["files"]}
        figures32 = json.loads(z.read(PREFIX + "report_figures.json"))
        originals = {}
        for info in z.infolist():
            name = info.filename
            if not info.flag_bits & 0x800:
                name = name.encode("cp437").decode("utf-8")
            if name.endswith("/") or not name.startswith(PREFIX) or name.rsplit("/", 1)[-1] == ".DS_Store":
                continue
            rel = name[len(PREFIX):]
            data = z.read(info)
            if rel != "manifest.json" and recorded.get(rel) != sha(data):
                raise SystemExit(f"Round 32 ZIP member differs from its own manifest: {rel}")
            originals[rel] = data
            if rel in SUPERSEDED:
                continue
            (r32 / rel).parent.mkdir(parents=True, exist_ok=True)
            (r32 / rel).write_bytes(data)

    edited: dict[str, dict] = {}
    for rel, old, new, reason in EDITS:
        path = r32 / rel
        text = path.read_text(encoding="utf-8")
        if text.count(old) != 1:
            raise SystemExit(f"edit anchor not found exactly once in {rel}")
        path.write_text(text.replace(old, new), encoding="utf-8")
        entry = edited.setdefault(rel, {"round32_path": rel, "original_sha256": sha(originals[rel]), "changes": []})
        entry["changes"].append({"removed_or_replaced": old, "now": new, "reason": reason})
    for entry in edited.values():
        entry["new_sha256"] = sha((r32 / entry["round32_path"]).read_bytes())

    for name in ("00_T4最终交付报告.md", "README.md"):
        shutil.copy2(BASE / "john_docs" / name, pkg / name)
    r33 = pkg / "round33"
    counts = {d: copy_tree(BASE / d, r33 / d) for d in ("01_d1", "02_viewer", "03_not_sent_reconcile", "tools")}
    shutil.copy2(BASE / "tools" / "verify_package33.py", pkg / "verify_package33.py")
    records = r33 / "records"
    (records / "原件前后哈希").mkdir(parents=True)
    shutil.copy2(args.state_before, records / "原件前后哈希" / "state_before.json")
    shutil.copy2(args.state_after, records / "原件前后哈希" / "state_after.json")
    shutil.copy2(BASE / "hash_proof" / "README.md", records / "原件前后哈希" / "README.md")
    (records / "文档修改记录.json").write_text(json.dumps({
        "recipient": "John",
        "written_at": datetime.now(UTC).isoformat(),
        "round32_zip": {"file": "T4_final_round32_20261009.zip", "sha256": R32_ZIP_SHA256, "modified": False},
        "edited_documents": list(edited.values()),
        "superseded_not_copied": [{"round32_path": rel, "original_sha256": sha(originals[rel]), "reason": why} for rel, why in SUPERSEDED.items()],
        "kept_verbatim_on_purpose": [
            "07_demo/视频场景索引.md: states that Xiang Mao started both Fresh runs on the web page -- the operator's identity is a fact, kept",
            "references/T4_delivery_round31_20261009.zip: the Round 31 package, nested byte-identical (its main report's '6 个请求输入超限，且被标成 malformed_response' is corrected in this version's report, section 8)",
        ],
        "note": "Every other file in round32/ is byte-identical to the Round 32 ZIP (round32/manifest.json is that package's own manifest).",
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    spec = importlib.util.spec_from_file_location("verify_package33", pkg / "verify_package33.py")
    verify = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verify)
    values33 = verify.r33_figures()
    report = (pkg / "00_T4最终交付报告.md").read_text(encoding="utf-8")
    cited = dict(R33_CITED)
    for key, value in values33.items():
        if key.startswith("r33.reconcile.row."):
            cited[key] = f"| {key.rsplit('.', 1)[1]} | {value:,} |"
    figures = [{"id": f["id"], "value": f["value"], "cited_as": f["cited_as"], "source": "round32 (rebuilt by round32/tools/rebuild_stats32.py)"} for f in figures32["figures"]]
    figures += [{"id": key, "value": values33[key], "cited_as": cited[key], "source": "round33 result files"} for key in sorted(cited)]
    missing = [f["id"] for f in figures if f["cited_as"] not in report]
    if missing or set(values33) != set(cited):
        raise SystemExit(f"figures not cited in the report: {missing}; uncited ids: {set(values33) ^ set(cited)}")
    (pkg / "report_figures.json").write_text(json.dumps({
        "schema": "t4.round33.report_figures.v1", "report_file": "00_T4最终交付报告.md",
        "how_checked": "verify_package33.py check 3 rebuilds every value offline and checks that cited_as appears verbatim in the report",
        "figures": figures}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"round32_files": len(originals) - len(SUPERSEDED), "superseded_not_copied": sorted(SUPERSEDED), "edited": sorted(edited),
                      "round33_files": counts, "figures": {"round32": len(figures32["figures"]), "round33": len(cited)}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
