# T4 Round 28：启动保护（2026-10-08）

入口：`REPORT.md`（结论、保存时点表、启动结论）。测试命令、结果、退出码和失败归因见 `TEST_REPORT.md`。

| 交付物 | 文件 |
|---|---|
| 1. 两项保护的结论、必要差异、原始测试证据 | `REPORT.md` §1/§2、`06_code/round28_code.diff`、`06_code/code_changes.json`、`test_evidence/` |
| 2. 超时后实际保留了什么、什么仍未完成 | `REPORT.md` §2、`02_timeout_preservation/`（两个真实终止探针和零调用重建） |
| 3. 新冻结配置、代码身份、预算与费用估算 | `04_refreeze/`（`frozen_config.json`、`code_snapshot/`、`web_check/`）、`REPORT.md` §3 |
| 4. 启动结论 | `REPORT.md` §4 |

## 目录
- `code_before/`：本轮每个文件第一次修改前的副本，即 Round 27 冻结时的版本，tracked diff `b5e91198…`。
- `06_code/`：本轮差异，以及修改前后的 sha256。
- `02_timeout_preservation/probe_evidence/`：真实作业超时探针。
  - `calibrate/`：校准运行；
  - `hang/`：30 秒超时，含探针服务器日志、请求日志、终止后的 run 目录、`inspect_result.json`、`rebuild/`；
  - `hang_reused_calibration_run/`：第一次计时运行与校准运行请求完全相同，被系统按指纹复用了已完成的 run，没有执行新的请求，原样保留作为说明。
- `02_timeout_preservation/cs_probe_evidence/`：内容核验中途终止探针。`*_attempt1_without_profile` 是第一次没有带执行 profile 的重建，缓存全部未命中，原样保留。
- `04_refreeze/`：8002 重启后的冻结配置、代码快照和网页检查。Round 27 的 `04_fresh_prep/` 没有改动。
- `tools/`：本轮的脚本。
  - 探针：`termination_probe/`（仅在探针进程的 `PYTHONPATH` 上生效）、`run_termination_probe.py`、`run_cs_termination_probe.py`；
  - 读取和重建：`inspect_terminated_run.py`；
  - 测试：`run_r28_tests.sh`；
  - 状态快照：`snapshot_state.py`。
- `hash_proof/`：Round 27 包、历史 run 和已验证交付包的只读证明，以及凭证扫描结果。
