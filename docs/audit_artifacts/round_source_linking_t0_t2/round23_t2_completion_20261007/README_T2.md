# Round 23 / T2 交付 README（可复制执行）

本目录是 T2（完成规则执行）收尾的入口。命令都在**仓库根目录**运行，路径都是仓库相对路径。除第 4 节里的整套测试外，每条命令都只读 `outputs/runs/`，**不调用任何 Provider / 搜索 / 取数 / 模型**，不写 `outputs/`，不 commit / push。

```bash
cd <仓库根目录>
source .venv/bin/activate
R23=docs/audit_artifacts/round_source_linking_t0_t2/round23_t2_completion_20261007
```

## 本目录有什么

| 文件 / 目录 | 内容 |
|---|---|
| `01_中文简明验收报告_T2.md` | 验收报告：对照 John 任务单 T2 逐项；区分「机制（合成测试）」「真实数据」「剩余缺口 / 待 John 定」。**以它为准** |
| `six_ticker/` | **六个历史标的的逐条规则判定**（统一入口 `scripts/run_formal_acceptance.py` 的输出）：`formal_acceptance_verdicts.json`（全部结果）、`formal_acceptance_tables.md`（所有表格，只从该 JSON 渲染）、`effective_rules.json`（解析后的有效规则） |
| `frozen_input_recompute/` | 冻结输入重算：只重跑确定性的冲突检测，看 `A102__A304` / `A201__A304` 在真实历史输入上被评估成什么 |
| `open_review_ledger/` | NVDA / QQQ 未关闭争议台账（每个保存的 run 的判定 + 每条复核原因；后来的 PASS 不关闭任何条目） |
| `scenario_map.md` | John 的 7 个必测场景 → 证明它们的测试（源数据 `docs/specs/t2_acceptance_scenario_map.json`，由测试保证引用的测试都真实存在） |
| `t2_changes.patch`、`t2_files.json` | **T2 专属 diff**（相对真实 HEAD `7a9aefa`；没有 commit）与文件清单、逐文件 sha256；已验证可由 `git archive HEAD` + 补丁重建 |
| `test_evidence/` | 整套测试的原始 JUnit / 日志、与第 15 轮基线的对比（含 1 个基线外失败的归因 `NEW_failure_attribution.md`）、T2 测试汇总 |
| `final_scope_proofs.json` | 范围证明：HEAD 未变、冻结文件与 HEAD 相同、16 个登记 run 目录 digest 不变、`outputs/` 文件数不变、三个入口的**零网络调用陷阱**、用户服务仍在监听 |
| `credential_scan_result.json` | 密钥扫描（`.env` 密钥值只在内存里精确匹配，不落盘） |
| 脚本 | `build_t2_patch.py`、`final_scope_proofs.py`、`credential_scan.py`、`summarize_test_evidence.py`、`render_scenario_map.py` |

规则文件本身（被评估的对象）：`comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml`（`content_version` 1.1.0，附 `content_change_log`）、`comqutor_alpha/config/j2_provisional_regression_labels_v0.2.yaml`（附 `content_change_log`）；John 的冻结基线：`docs/audit_artifacts/v0_2_john_frozen_gold_baseline.yaml`（只读）。

## 1. 统一正式验收入口（六个历史标的的逐条判定）

```bash
python scripts/run_formal_acceptance.py --out-dir /tmp/t2_six_ticker                  # 默认：六个固定的历史 run
python scripts/run_formal_acceptance.py --out-dir /tmp/t2_amd --run AMD=<run_id>        # 指定 run
python scripts/run_formal_acceptance.py --out-dir /tmp/t2_x --taxonomy <taxonomy.yaml> --labels-v2 <labels_v0.2.yaml> --labels-v1 <labels_v0.1.yaml>
```

* **显式读取你指定的规则文件**：不指定才用仓库默认文件；任何一个文件缺失 / 损坏 / 与 taxonomy 不兼容 / 版本不符 / 含引擎没实现的规则键 → 每个标的的判定都是 `config_error` 加具体原因码，**不会改成 NOT_APPLICABLE 后继续 PASS**。
* `--out-dir` 必须是新目录或空目录（已有文件会拒绝，退出码 2）：已交付的判定文件不会被覆盖。
* 退出码：0 全部评估 | 2 目录已有文件 | 3 有 run 找不到或有 `config_error`。
* 三个输出文件来自**同一份结果文档**：表格只从 JSON 渲染（有测试保证渲染时不调用引擎、不读 run 目录）。

## 2. 冻结输入重算（T0 的第二种执行类型）

```bash
python scripts/recompute_conflicts_frozen_inputs.py --out-dir /tmp/t2_recompute         # 默认：同样六个 run
```

只重跑确定性冲突检测（读 run 自己保存的 `alpha_activations.json` + `alpha_matches.json`，用**当前 taxonomy**），把结果放在 run 自己保存的 `conflicts.json` 旁边。零模型调用，不写 run 目录。这些 run 早于来源关联，所以验证型证据闸门保持关闭（与它们当初写 `conflicts.json` 时一致）。

## 3. NVDA / QQQ 争议台账

```bash
python scripts/build_open_review_ledger.py --out-dir /tmp/t2_ledger                     # 默认 NVDA QQQ；--tickers 可加别的
python scripts/build_open_review_ledger.py --out-dir /tmp/t2_ledger2 --closure-records records.json   # 有复核决定记录时
```

一个条目只有被一条**记录在案的复核决定**关闭（谁、何时、对哪个 run 的哪条规则）。目前没有任何这样的记录，所以没有任何条目被关闭；后来的 PASS 不关闭任何条目。

## 4. 测试

```bash
# T2 的快测（引擎、错误路径、守护、入口、重算、台账、场景映射、生产接入、MSFT 重放）
python -m pytest tests/test_acceptance_engine.py tests/test_t2_acceptance_engine_qualified_evidence_scenarios.py \
  tests/test_t2_architecture_replay_never_shown_as_pass_or_no_conflict.py tests/test_t2_rule_config_errors.py \
  tests/test_t2_scenario_map_points_at_real_tests.py tests/test_formal_acceptance_artifact_production_wiring.py \
  tests/test_formal_acceptance_report.py tests/test_no_gold_label_import_in_research_path.py \
  tests/test_label_v2_covers_john_frozen_baseline.py tests/test_frozen_input_conflict_recompute.py \
  tests/test_open_review_ledger.py tests/test_msft_a102_a304_taxonomy_adjudication.py \
  tests/test_v0_1_3_offline_replay_proof.py -q -p no:cacheprovider
# 慢测（会整套回放六个标的，约 10 分钟）
python -m pytest tests/test_a4_regression_runner.py tests/test_j3_semantic_benchmark_j2_v0_2.py tests/test_week4_golden_closure.py -q -p no:cacheprovider
# 整套（约 45 分钟）并与第 15 轮基线对比：任何不在基线里的失败都会被列为 NEW
python -m pytest -q -p no:cacheprovider --junitxml=/tmp/t2_full.junit.xml
python $R23/summarize_test_evidence.py /tmp/t2_full.junit.xml --out /tmp/t2_test_summary.json
```

测试里的合成 fixture 都在模块文档字符串里**明确标注**，不计为真实市场验证；真实数据上的判定来自第 1–3 节的入口。

## 5. 重建 T2 补丁、范围证明、密钥扫描

```bash
python $R23/build_t2_patch.py                      # 写 t2_changes.patch / t2_files.json，并在临时目录用 git archive HEAD + 补丁重建、核对
python $R23/final_scope_proofs.py --outputs-file-count-before <N>   # N = 整套测试开始前 find outputs -type f | wc -l
python $R23/credential_scan.py
python $R23/render_scenario_map.py                 # 由 docs/specs/t2_acceptance_scenario_map.json 重新生成 scenario_map.md
```

## 已知限制

* **没有 commit**（按指示）：代码身份 = 真实 HEAD `7a9aefa` + `t2_changes.patch`（逐文件 sha256 在 `t2_files.json`）。
* v0.2 规则文件仍是 `provisional / shadow / formal_product_owner_approval: pending`：本目录的判定是**临时规则下的判定**，不是 John 批准的正式判定；`required_conflicts` 对六个标的全为空，所以 `must_detect_if_evidence_present` 在真实数据上没有触发过（只有合成测试）。
* 六个历史标的的 Type A 判定读的是各 run **当时保存**的 `conflicts.json`，A102__A304 / A201__A304 在其中是 `not_reached`；它们在真实输入上的结果见 `frozen_input_recompute/`。
* 待 John 定的问题见报告 §6。
