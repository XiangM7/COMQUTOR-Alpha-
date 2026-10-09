# T4 最终交付包（Round 32，2026-10-09）

入口：`00_T4最终交付报告.md`。报告先给出五个停止条件的逐条结果，然后是 John T4 四项要求的逐条关闭表。

## 目录

| 路径 | 内容 |
|---|---|
| `00_T4最终交付报告.md` | 最终报告：停止条件、关闭表、本轮修复、验证结果、决定项、限制 |
| `report_figures.json` | 报告引用的每个数字，附上它在报告中的原文 |
| `manifest.json` | 包内每个文件（除自身）的大小和 sha256 |
| `01_regressions/` | 两个回归失败：分析（`回归失败分析.md`），以及在 HEAD、Fresh 代码快照、修复前工作区、修复后工作区、负对照上的复现日志 |
| `02_code/` | 最终代码身份、相对 HEAD 的完整 tracked diff、未跟踪运行源码 tar 和清单、本轮相对 Fresh 代码的改动（`round32_changes.diff`、`code_changes.json`）；`superseded_first_freeze/` 是第一次冻结 |
| `03_not_sent/` | 未发送请求的修复说明和历史误标附录（`not_sent_appendix.json`） |
| `03_postgres/` | 最终代码上的 PostgreSQL 链路：建库、迁移、重启前后快照与比较、Export、一致性、实例日志 |
| `04_tests/` | 最终代码上的测试：new、replay、pg、affected、frontend 的原始日志、JUnit、命令、代码身份、外网陷阱结果；`probe_run_before_test_fix/` 是第一次冻结上的试跑 |
| `05_stage_disclosure/` | 结构抽取和适配器的定位、降级披露说明；最终代码对两次 Fresh 的读时披露 |
| `05_replay/` | 派生验证执行（最终代码消费第二次 Fresh 已保存的真实回复）的报告和逐字段对照；`superseded_attempt1..3/` 是过程中被取代的尝试及原因 |
| `06_frozen_checks/` | AMD 34 项引用核对、QQQ 冻结输入正式验收、SNDK 历史无主冲突核对 |
| `07_demo/` | 最终版本演示视频（烧录字幕）、场景表、截图、页面下载的 Export、视频索引、录制器 |
| `runs/<派生执行 id>/` | 派生验证执行的完整目录副本 |
| `references/T4_delivery_round31_20261009.zip` | Round 31 已验证交付包，原样副本（sha256 `6f11b688…`），内含两次 Fresh 的完整目录、逐 claim 清单、用量和费用 |
| `references/prior_packages.json` | T1 / T2 / T3 和 Round 27–31 材料：只有路径和 sha256 |
| `tools/` | 本轮全部脚本 |

## 验证（解压后在 `T4_final/` 目录运行）

只需要 Python 3.11 或更新版本的标准库。不需要仓库、API key 或数据库，不联网，不会启动研究。

```bash
python3 tools/verify_package32.py
python3 tools/rebuild_stats32.py
python3 tools/scan_credentials.py
```

`verify_package32.py` 做六项检查，全部通过时退出码为 0：

| # | 检查 |
|---|---|
| 1 | 每个文件的 sha256 与 manifest 一致 |
| 2 | 报告引用的包内路径都存在；README 命令可用，且不含绝对路径或占位符 |
| 3 | 从包内原始文件离线重算报告中的全部数字 |
| 4 | 嵌套的 Round 31 ZIP 哈希正确；派生执行的 Export 与其目录逐字节一致，并含 `stage_disclosure.json`；演示中页面下载的 ZIP 等于第二次 Fresh 的 Export 哈希 |
| 5 | 凭据和授权头扫描 |
| 6 | 最终代码快照能重算出实例和测试所记录的代码身份 |

## 在仓库内复现（从仓库根目录运行）

```bash
python3 docs/audit_artifacts/round_source_linking_t0_t2/round32_t4_closure_20261009/T4_final/tools/verify_package32.py --env .env
python3 docs/audit_artifacts/round_source_linking_t0_t2/round32_t4_closure_20261009/T4_final/tools/snapshot_state.py --out docs/audit_artifacts/round_source_linking_t0_t2/round32_t4_closure_20261009/hash_proof/state_recheck.json --compare docs/audit_artifacts/round_source_linking_t0_t2/round32_t4_closure_20261009/hash_proof/state_before.json
bash docs/audit_artifacts/round_source_linking_t0_t2/round32_t4_closure_20261009/tools/reproduce_regressions.sh R_recheck_worktree worktree
```

- 第一条：在标准检查之外，再用 `.env` 中的真实值做凭据扫描，只输出键名。
- 第二条：比较原始 run、旧 ZIP 和受保护目录在本轮前后的哈希。`--out` 指向的文件已存在时会拒绝写入，再次运行时请换一个文件名。
- 第三条：在当前工作区上重跑两个回归测试，结果写入包外 `round32_t4_closure_20261009/01_regressions/R_recheck_worktree.log`。这里用包外原位置的同名脚本，因为 shell 脚本按固定层级定位仓库；包内 `tools/` 中是它的副本。
- 测试组、PostgreSQL 链路、派生执行和演示的原始命令写在各自的日志里（`04_tests/*_command.txt`、`03_postgres/`、`05_replay/replay_stdout.txt`、`07_demo/`）。复现需要本机的 PostgreSQL 和本轮建的独立库，见 `tools/create_r32_databases.py`、`tools/start_r32_instance.sh`。

## 不自包含的部分

- T1、T2、T3 交付包和 John 的任务单在包外，只列了路径和哈希（`references/prior_packages.json`）。
- 重跑测试、PostgreSQL 链路和派生执行需要仓库处于 `02_code/` 记录的代码身份，并能访问本机 PostgreSQL。
