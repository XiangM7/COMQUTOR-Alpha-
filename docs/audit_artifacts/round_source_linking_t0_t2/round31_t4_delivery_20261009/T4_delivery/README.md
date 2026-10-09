# T4 最小交付包（Round 31，2026-10-09）

**入口**：`00_T4交付主报告.md`。主报告开头先回答四个问题，然后是 John 的 T4 四项对照表。

## 目录

| 路径 | 内容 |
|---|---|
| `00_T4交付主报告.md` | 主报告 + John T4 对照表 |
| `report_figures.json` | 主报告引用的每个数字，附上它在报告中的原文 |
| `manifest.json` | 包内每个文件（除自身）的大小和 sha256 |
| `runs/12591384-0b26-470d-a99d-a49c00be440b/` | 第二次 Fresh 的完整 run 目录副本（逐字节），含账本、线路审计、`formal_acceptance.json` |
| `runs/fa642639-8d93-4f9a-9de1-2c4d789eade8/` | 第一次 Fresh 的完整 run 目录副本 |
| `run_records/run2_12591384/`、`run_records/run1_fa642639/` | 每次 run 的身份与配置（`identity_and_config.json`）、API Export ZIP、页面下载 ZIP、运行后的接口响应、数据库核对、监测日志、原报告副本 |
| `ledgers/run2_12591384/`、`ledgers/run1_fa642639/` | 逐 claim 清单（`claims.csv/json`）、关键结论（`key_conclusions.*`）、SUPPORTS 采用情况（`supports.*`）、统计（`stats.json`） |
| `usage_cost/` | 调用、usage 与费用核对（`调用与费用核对.md` 和两份 JSON） |
| `code_identity/` | 两次 Fresh 的代码快照（tracked diff、未跟踪运行源码 tar、文件清单）、Round 28 冻结配置、Round 28 改动清单 |
| `tests/` | `测试证据索引.md`，以及 Round 27 / 28 测试日志副本（PG、单元、前端、PG 链路、Replay / ESLint） |
| `video/` | `视频场景索引.md`、`scene_index.json`、三段原视频、带章节和字幕的副本、字幕文件、逐场景截图 |
| `references/prior_packages.json` | 引用的 T1 / T2 / T3 包和 Round 27–30 报告，只有路径和 sha256，没有重新打包 |
| `tools/` | 生成和验证本包所用的全部脚本 |

## 验证（解压后在包根目录运行）

只需要 Python 3.11 或更新版本的标准库。不需要仓库、API key、数据库，不联网，不会启动研究。

```bash
python3 tools/verify_package.py
python3 tools/rebuild_stats.py
python3 tools/scan_credentials.py
```

`verify_package.py` 做六项检查，全部通过时退出码为 0：

| # | 检查 |
|---|---|
| 1 | 每个文件的 sha256 与 `manifest.json` 一致，没有清单外的文件 |
| 2 | 报告里引用的包内路径都存在；README 命令不含绝对路径和占位符 |
| 3 | `rebuild_stats.py` 从原始 run 文件和清单离线重算报告中的 70 个数字，并逐个核对它们在报告中的原文 |
| 4 | 两次 run 的 Export：20 个文件，与 run 目录逐字节一致；页面下载的 ZIP 哈希相同；第二次 Fresh 的 ZIP 哈希等于 Round 30 当时记录的值 |
| 5 | 凭据和授权头扫描，包括压缩包内的文件 |
| 6 | 代码快照能重算出两次 run 记录的代码身份；run 的实际配置等于冻结配置 |

如果本机装有 ffmpeg，还会额外核对：章节副本的视频流与原件相同。

## 在仓库内验证（包位于原位置时，从仓库根目录运行）

```bash
python3 docs/audit_artifacts/round_source_linking_t0_t2/round31_t4_delivery_20261009/T4_delivery/tools/verify_package.py --env .env --regenerate-ledgers
python3 docs/audit_artifacts/round_source_linking_t0_t2/round31_t4_delivery_20261009/T4_delivery/tools/snapshot_state.py --out docs/audit_artifacts/round_source_linking_t0_t2/round31_t4_delivery_20261009/hash_proof/state_recheck.json --compare docs/audit_artifacts/round_source_linking_t0_t2/round31_t4_delivery_20261009/hash_proof/state_before.json
```

- 第一条在六项检查之外再做两件事：
  - 用 `.env` 中的真实值做一遍凭据扫描，只输出键名，不输出值；
  - 用生产代码重建两份 claim 清单，与包内逐字节比较。这一步需要仓库处于同一代码身份，脚本会报告当前仓库是否一致。
- 第二条核对原始 run 目录和受保护目录在本轮前后的哈希。`--out` 指向的文件已存在时，脚本会拒绝写入；再次运行时换一个新文件名。

## 生成方式（复现用，从仓库根目录运行；会覆盖包内同名文件）

```bash
.venv/bin/python docs/audit_artifacts/round_source_linking_t0_t2/round31_t4_delivery_20261009/T4_delivery/tools/run_with_network_trap.py docs/audit_artifacts/round_source_linking_t0_t2/round31_t4_delivery_20261009/T4_delivery/tools/build_claim_ledger.py --run-dir docs/audit_artifacts/round_source_linking_t0_t2/round31_t4_delivery_20261009/T4_delivery/runs/12591384-0b26-470d-a99d-a49c00be440b --out-dir docs/audit_artifacts/round_source_linking_t0_t2/round31_t4_delivery_20261009/T4_delivery/ledgers/run2_12591384
.venv/bin/python docs/audit_artifacts/round_source_linking_t0_t2/round31_t4_delivery_20261009/T4_delivery/tools/run_with_network_trap.py docs/audit_artifacts/round_source_linking_t0_t2/round31_t4_delivery_20261009/T4_delivery/tools/build_usage_reconciliation.py --run-dir docs/audit_artifacts/round_source_linking_t0_t2/round31_t4_delivery_20261009/T4_delivery/runs/12591384-0b26-470d-a99d-a49c00be440b --out docs/audit_artifacts/round_source_linking_t0_t2/round31_t4_delivery_20261009/T4_delivery/usage_cost/usage_reconciliation_run2_12591384.json
python3 docs/audit_artifacts/round_source_linking_t0_t2/round31_t4_delivery_20261009/T4_delivery/tools/build_run_identity.py --run-dir docs/audit_artifacts/round_source_linking_t0_t2/round31_t4_delivery_20261009/T4_delivery/runs/12591384-0b26-470d-a99d-a49c00be440b --records docs/audit_artifacts/round_source_linking_t0_t2/round31_t4_delivery_20261009/T4_delivery/run_records/run2_12591384 --out docs/audit_artifacts/round_source_linking_t0_t2/round31_t4_delivery_20261009/T4_delivery/run_records/run2_12591384/identity_and_config.json
python3 docs/audit_artifacts/round_source_linking_t0_t2/round31_t4_delivery_20261009/T4_delivery/tools/build_video_chapters.py
python3 docs/audit_artifacts/round_source_linking_t0_t2/round31_t4_delivery_20261009/T4_delivery/tools/build_references.py
python3 docs/audit_artifacts/round_source_linking_t0_t2/round31_t4_delivery_20261009/T4_delivery/tools/build_manifest.py
```

- 第一次 Fresh 用同样的命令，把 run_id 换成 `fa642639-8d93-4f9a-9de1-2c4d789eade8`，目录名换成 `run1_fa642639`。
- `build_claim_ledger.py` 和 `build_usage_reconciliation.py` 调用仓库的生产代码，在网络陷阱下运行。本轮记录到的外发尝试为 0。
- `build_video_chapters.py` 需要本机 ffmpeg。

## 本包不自包含

以下文件不在包内，只列路径和 sha256，详见 `references/prior_packages.json` 和 `manifest.json` 的 `not_in_package`：

| 文件 | 位置 |
|---|---|
| T1 交付包 | `~/Desktop/t1.zip` |
| T2 交付包 | `~/Desktop/t2.zip` |
| T3 交付包 | `~/Desktop/T3_delivery_t3joint-20261008T170322Z-bd99811e.zip`，与仓库 `round26_t3_closeout_20261008/delivery/` 中的副本哈希相同 |
| John 的任务单 | `~/Downloads/COMQUTOR Alpha 下一轮开发任务单.docx` |

这些都是 Xiang Mao 本机的文件，需要时由负责人另行提供。

另外，用生产代码重建 claim 清单需要仓库在 `code_identity/` 记录的代码身份下。
