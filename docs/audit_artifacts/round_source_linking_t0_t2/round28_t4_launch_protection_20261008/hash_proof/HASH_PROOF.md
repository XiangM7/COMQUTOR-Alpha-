# 只读证明（Round 28）

命令：`python tools/snapshot_state.py --out hash_proof/state_after.json --compare hash_proof/state_before.json`（输出见 `compare_stdout.txt`）

## 只读文件（888 个）
覆盖范围：
- 历史 run：NVDA `034a0a60`、AMD `1bad76a7`／`c904d4cc`，以及各次派生执行；
- T3 执行目录和材料目录；
- 第 25、26、27 轮的整个包。

结果：
- 887 个未变；
- 1 个变化：`round27_t4_phase_a_20261008/04_fresh_prep/instance_fresh_start.log`。这是 Round 27 实例自己的 stdout 日志，本轮正常停止该实例时被追加了 7 行（重启前的 3 次只读 GET，加 4 行关停信息）。去掉这 7 行后与本轮开始时的哈希相同，属于纯追加（`round27_log_append_check.txt`）。

Round 27 的冻结配置、代码快照和其他日志都没有改动。

## 代码身份
| 项 | 值 |
|---|---|
| HEAD | `7a9aefa`，未变 |
| tracked diff（开始前） | `b5e91198…`（Round 27 冻结） |
| tracked diff（最终） | `1b53b921…` |
| untracked 运行源码（最终） | `38ef636f…` |

在 untracked 文件中：
- `comqutor_alpha/run_provider_stop.py` 在本轮开始快照之前已经新建，所以快照把它算作"修改"，不算"新增"；
- 其余列出的 untracked 修改，是本轮之前就处于 untracked 状态的文件。

逐文件改动前后的 sha256 见 `06_code/code_changes.json`。

## 凭证扫描
- 命令：`python tools/scan_credentials.py --out hash_proof/credential_scan_result.json`。
- 范围：本轮目录全部文件，包括 ZIP 和 tar.gz 成员、探针日志、SQLite 文件，共 244 个。
- 结果：0 处命中。
