# T4 最终交付包（Round 33，2026-10-09）

收件人：John。唯一入口是 `00_T4最终交付报告.md`。

## 目录

| 路径 | 内容 |
|---|---|
| `00_T4最终交付报告.md` | 最终报告：本版三项、四项要求关闭表、沿用的 Round 32 结果、更正、未关闭项 |
| `report_figures.json` | 报告引用的每个数字及其原文：沿用 Round 32 的 61 个，加本版新增的数字 |
| `manifest.json` | 包内每个文件（除自身）的大小和 sha256 |
| `verify_package33.py` | 包内核对脚本 |
| `round33/01_d1/` | D1 离线定位：说明、第二次 Fresh 的逐批复现结果、第一次 Fresh 的补充结果、运行日志 |
| `round33/02_viewer/` | 最终查看入口：实例与代码身份核对、只读页面核对的截图、Export 下载和结果 |
| `round33/03_not_sent_reconcile/` | “6 次拒绝／5 条更正”逐条对账和运行日志 |
| `round33/tools/` | 本版脚本 |
| `round33/records/` | 读者文档修改记录、本版前后原件哈希、凭据扫描结果 |
| `round32/` | Round 32 交付材料：回归、代码身份与 diff、未发送修复、PostgreSQL、测试、replay、阶段披露、冻结数据检查、演示视频、派生执行目录、Round 31 包、脚本。除报告第 8 节所列的改动外，与 Round 32 的 ZIP 逐字节相同 |

## 1. 只用本包即可执行的检查

需要 Python 3.11 或更新版本的标准库。不需要仓库、API key 或数据库，不联网，不启动服务，也不发起研究。在解压后的本目录运行：

```bash
python3 verify_package33.py
```

全部通过时退出码为 0，任一项失败时为 1。检查项如下：

| # | 检查 |
|---|---|
| 1 | 每个文件的 sha256 与 `manifest.json` 一致，没有清单外文件 |
| 2 | `round32/` 中的每个文件，要么与 Round 32 原清单（`round32/manifest.json`）记录的 sha256 相同，要么是修改记录中列出的改写文件；没有复制的文件只限修改记录列出的 3 个 |
| 3 | 报告中的全部数字可以离线重算：Round 32 的 61 个数字用 `round32/tools/rebuild_stats32.py` 的重算函数，读 `round32/` 中的原始文件；本版数字读 `round33/` 中的结果文件。每个数字的原文都必须出现在报告里 |
| 4 | 本版三项的结论与原始结果一致：<br>• D1 的逐批结果和网络陷阱计数；<br>• 对账的平衡关系与逐条记录；<br>• 查看入口的代码身份、Export sha256、阶段披露与 Round 32 副本一致，拦截请求数为 0 |
| 5 | 读者文档中引用的文件都能在包内找到（包括 Round 31 嵌套 ZIP 内的 run 文件）；仓库路径单独列出，不算失败 |
| 6 | 凭据和授权头扫描 |

## 2. 需要原仓库环境的命令

以下命令在仓库根目录运行，需要：
- 仓库处于 `round32/02_code/` 记录的最终代码身份；
- 项目的 `.venv`；
- 本机 PostgreSQL；
- 第二次 Fresh 的原 run 目录 `outputs/t4_runs/12591384-0b26-470d-a99d-a49c00be440b`。

这些命令都不发送任何外部请求。

```bash
R33=docs/audit_artifacts/round_source_linking_t0_t2/round33_t4_closeout_20261009
source .venv/bin/activate
python $R33/tools/run_with_network_trap.py $R33/tools/d1_offline_reproduction.py --run 12591384-0b26-470d-a99d-a49c00be440b --out /tmp/d1_recheck.json
python3 $R33/tools/run_with_network_trap.py $R33/tools/reconcile_not_sent.py --out-json /tmp/reconcile.json --out-md /tmp/reconcile.md
bash docs/audit_artifacts/round_source_linking_t0_t2/round32_t4_closure_20261009/tools/start_r32_instance.sh demo
(cd frontend && VITE_COMQUTOR_API_BASE_URL=http://127.0.0.1:8005 npx vite --host 127.0.0.1 --port 5179 --strictPort)
node $R33/tools/viewer_check.mjs --base http://127.0.0.1:5179 --api http://127.0.0.1:8005 --out /tmp/viewer_check
```

- **第一、二条**：分别重做 D1 的离线复现和“6 次／5 条”对账，都在网络陷阱下运行，输出最后一行应为 `network attempts: 0`。
- **第三、四条**：启动最终查看入口，即只读实例 8005 和前端 5179。启动后在浏览器打开 `http://127.0.0.1:5179`。
- **第五条**：只读核对第二次 Fresh 的阶段披露、历史重开和 Export。它会拦截所有非 GET 请求，也不会点击 Start Research。
- **Round 32 的测试、PostgreSQL 链路、派生执行和演示**：命令写在各自的日志里（`round32/04_tests/*_command.txt`、`round32/03_postgres/`、`round32/05_replay/replay_stdout.txt`、`round32/07_demo/`）。

## 不自包含的部分

- T1、T2、T3 交付包和 John 的任务单不在本包内，只列了路径和哈希（`round32/references/prior_packages.json`）。
- 重跑测试和启动查看入口需要仓库和本机 PostgreSQL。
- `round32/tools/verify_package32.py` 是针对原 Round 32 ZIP 的核对脚本。原 ZIP 中的主报告、README 和 `report_figures.json` 已被本包取代，没有复制，所以这个脚本在本包里会报告这 3 个文件缺失。本包请使用 `verify_package33.py`。
