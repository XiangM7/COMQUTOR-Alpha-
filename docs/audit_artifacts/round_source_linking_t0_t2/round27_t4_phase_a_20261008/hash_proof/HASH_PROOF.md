# 只读产物与代码身份证明

命令：`python tools/snapshot_state.py --out hash_proof/state_after.json --compare hash_proof/state_before.json`（输出见 `compare_stdout.txt`）

## 只读产物
- 723 个只读文件**全部未变**（`read_only_unchanged: true`）。
- 覆盖范围：
  - NVDA `034a0a60`、AMD `1bad76a7`、`c904d4cc`；
  - recovery／requal／dependency／direction 各次派生执行；
  - T3 执行目录和材料目录；
  - 第 25、26 轮整个包。

## 不在上述清单中的两个源
- **SNDK 基准 run `52c23371`**：落库前复制，复制件与原件逐字节相同、原件未变（`01_postgres/frozen_runs_persisted.json`）。
- **Replay 源 run `e434f80b`**：复现前后哈希相同（`02_replay_eslint/replay_test_reproduction.json`）。

## 代码身份
| 项 | 值 |
|---|---|
| HEAD | `7a9aefa`，未变 |
| tracked diff（开始前） | `cb81f23f…` |
| tracked diff（最终） | `b5e91198…` |
| 新增 untracked 运行源码 | `comqutor_alpha/run_environment.py`、`comqutor_alpha/llm/run_usage_report.py` |
| 修改过的 untracked 文件（本轮之前就是 untracked） | `classification_recovery.py`、`llm/cost_basis.py`、`frontend/src/utils/serverStatus.ts` 及其测试 |

逐文件改动前后的 sha256 见 `06_code/code_changes.json`。

## 凭证扫描
- 命令：`python tools/scan_credentials.py --out hash_proof/credential_scan_result.json`。
- 扫描范围：本目录全部文件，包括 ZIP 和 tar.gz 的成员，共 325 个。
- 比对对象：`.env` 中的密钥值和数据库密码。
- 结果：**0 处命中**。
- 唯一一次命中出现在 `test_evidence/pg_attempt1_test_expectation_bug.log`：pytest 的 traceback 打印了测试库 DSN。已把其中的数据库密码替换为 `***REDACTED***`，见 `TEST_REPORT.md` §3。
