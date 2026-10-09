# Round 24 / T2 已确认缺口收口 — 材料包入口（可复制执行）

本目录是 T2 第 24 轮的入口，**接在第 23 轮之后**：第 23 轮目录（`../round23_t2_completion_20261007/`）按指示保持**只读、原样不动**，它的判定在这里叫“原判定”。本目录的新结果全部放在这里，不覆盖任何历史结果。**这是材料索引，不是签收**：不宣布 T2 已通过，也不宣布 John 已签收。

命令都在**仓库根目录**运行。除“测试”一节外，每条命令都只读 `outputs/runs/`，**不调用任何 Provider / 搜索 / 取数 / 模型**，不写 `outputs/`，不 commit / push。

```bash
cd <仓库根目录>
source .venv/bin/activate
R24=docs/audit_artifacts/round_source_linking_t0_t2/round24_t2_gap_closure_20261007
```

## 本目录有什么

| 文件 / 目录 | 内容 |
|---|---|
| `01_中文简明验收报告_T2.md` | 验收报告（**以它为准**）：按指令六部分逐项；更正第 23 报告的错误表述；覆盖状态；区分历史输入上的规则判定 / 合成工程证明 / John 签收；待负责人决定的事项 |
| `provenance/alpha_rule_provenance.{md,json}` | 本轮执行的 5 条契约规则：契约原始记录、John 决定原文（按段落从会话记录里摘出，不是重打）、冻结触发、完整性备注（N1–N8） |
| `six_ticker/` | **六个固定历史 run（第 23 轮同一批）的新判定**：`formal_acceptance_verdicts.json`、`formal_acceptance_tables.md`、`effective_rules.json`（统一入口 `scripts/run_formal_acceptance.py` 的输出） |
| `before_after/six_ticker_comparison/` | 六个固定 run：原判定 → 新判定，逐项（规则及批准依据、触发及证据、Alpha 识别／等级、Conflict 实际结果与 B2 拒绝原因、blocking 影响、不可评估／仅诊断） |
| `before_after/research_facts_unchanged.json` | 六个固定 run：第 23 轮与本轮入口从保存的 run 里读到的研究事实（run id、准入／候选冲突、主冲突、Alpha 等级与分数）逐项相同，以及六个 run 目录的内容哈希 |
| `before_after/delta_all_saved_runs.{json,md}` | 六个标的**全部 76 个已保存 run**，第 23 轮引擎 vs 本轮引擎的判定差异及原因（含 `old_` / `new_verdicts_all_saved_runs.json` 原始快照） |
| `matrix_bound_runs/` | 冻结触发矩阵**实际绑定**的六个 run（John 的 Step-4 权威 run）用同一入口评估：契约规则在这里有真实触发，并复现 John 的 Step-4 行 |
| `open_review_ledger/` | NVDA / QQQ 争议台账（新）：诊断与“无法评估”与待复核条目分开列出，不当成争议 |
| `offline_repro/conflict_pair_defect/` | 同一批合成输入（真实检测器 + 真实 B2）在第 23 轮引擎与本轮引擎下的结果对照（8 个案例） |
| `offline_repro/whatif_required_pairs/` | 受控的 what-if：把四条 conditional 对（NVDA A101__A304、A301__A304，SNDK A201__A304，MSFT A102__A304）声明为 required（**未批准**），看真实保存 run 上两个引擎各怎么判 |
| `scenario_map.md` | John 的 7 个必测场景 → 证明它们的测试，含夹具类型、**本轮实际结果**与覆盖状态（源数据 `docs/specs/t2_acceptance_scenario_map.json`） |
| `test_evidence/` | 原始命令、日志、退出码、JUnit、网络陷阱报告：`BEFORE_*`（第一次编辑之前）、`FINAL_*`（最终代码：受影响测试、上游被引用测试、生产完成路径）、`NEWTESTS_ON_ROUND23_CODE_*`（最终测试放到第 23 轮代码上）、`summary_*`（与第 23 轮全量结果的逐测试对比）；`interim_before_composite_change/` 是组合规则修改之前的一轮中间结果，保留但不作为最终证据 |
| `t2_changes.patch`、`t2_files.json` | **T2 全部改动相对真实 HEAD `7a9aefa`**（第 23 + 24 轮合计；没有 commit）与逐文件 sha256；已验证可由 `git archive HEAD` + 补丁重建 |
| `round24_delta.patch`、`round24_delta.json` | **只含本轮**的改动（第 23 轮状态 → 现在），已验证可由第 23 轮状态 + 补丁重建 |
| `round23_state_of_changed_files/` | 本轮改动过的文件在第 23 轮结束时的样子（改动前复制，已对第 23 轮自己记录的 sha256 核对） |
| `final_scope_proofs.json`、`credential_scan_result.json` | 范围证明（HEAD 未变、评分／B2／等级模块与 HEAD 相同、本轮起变化的文件恰为 delta 清单、`outputs/` 与第 23 轮目录未变、冻结输入 sha256 未变、三个入口零网络调用、服务仍在监听）与密钥扫描 |
| `tools/` | 本轮用到的脚本（快照、对比、研究事实核对、溯源、渲染、补丁、范围证明、密钥扫描、网络陷阱） |

规则文件本身：John 的冻结契约 `docs/audit_artifacts/v0_2_gold_operational_contract.json`（sha256 `e2df7139…`，与冻结清单一致）、冻结清单 `v0_2_gold_freeze_manifest.json`、冻结触发矩阵 `v0_2_evidence_trigger_matrix.json`（sha256 `3e8e7402…`）、John 的冻结基线 `v0_2_john_frozen_gold_baseline.yaml`；被评估的标签与 taxonomy（`j2_provisional_regression_labels_v0.2.yaml`、`alpha_taxonomy_v1.yaml`）**本轮未改**。

## 1. 统一正式验收入口

```bash
python scripts/run_formal_acceptance.py --out-dir /tmp/t2r24_six                                   # 默认：六个固定历史 run
python scripts/run_formal_acceptance.py --out-dir /tmp/t2r24_bound \
  --run NVDA=57d7b4c4-dbb9-4134-b962-ee2a873941cc --run MSFT=43472ace-454f-4c69-892c-adca91c25be7   # 冻结触发矩阵绑定的 run
python scripts/run_formal_acceptance.py --out-dir /tmp/t2r24_x --gold-contract <contract.json> \
  --gold-freeze-manifest <manifest.json> --trigger-matrix <matrix.json>                            # 显式指定 John 的冻结输入
python $R24/tools/run_with_network_trap.py run_formal_acceptance.py --out-dir /tmp/t2r24_trap      # 同上，但任何联网尝试都会被计数并报错
```

* 任何一个规则文件（taxonomy、标签、**Gold 契约、冻结清单、触发矩阵**）缺失 / 损坏 / 版本不符 / 不是冻结的那份文件（sha256 与冻结清单不符）/ 缺少本入口要执行的契约规则 → 每个标的的判定都是 `config_error` 加原因码，不会改成 NOT_APPLICABLE 继续 PASS。
* 默认文件位置：优先仓库内的 `docs/audit_artifacts/…`；容器镜像里包装在虚拟环境、仓库副本在工作目录，因此找不到时再找 `<cwd>/docs/audit_artifacts/…`（同一份字节，同样核对 sha256）；都没有就报错并写出期望位置。
* `--out-dir` 必须是新目录或空目录；退出码 0 全部评估 | 2 目录已有文件 | 3 有 run 找不到或有 `config_error`。
* 表格只从 JSON 渲染（有测试保证渲染时不调用引擎、不读 run 目录，且改 JSON 表格就跟着变）。

## 2. 全部已保存 run 的前后对比

```bash
python $R24/tools/snapshot_all_saved_run_verdicts.py --out /tmp/new.json                           # 当前代码对 76 个已保存 run 的判定快照
python $R24/tools/compare_verdict_snapshots.py --before $R24/before_after/old_verdicts_all_saved_runs.json --after /tmp/new.json \
  --out-json /tmp/delta.json --out-md /tmp/delta.md
python $R24/tools/build_six_ticker_comparison.py --original docs/audit_artifacts/round_source_linking_t0_t2/round23_t2_completion_20261007/six_ticker/formal_acceptance_verdicts.json \
  --new $R24/six_ticker/formal_acceptance_verdicts.json --out-dir /tmp/cmp
python $R24/offline_repro/repro_before_after.py --round23-engine $R24/round23_state_of_changed_files/comqutor_alpha/regression/acceptance_engine.py --out-dir /tmp/repro
python scripts/build_open_review_ledger.py --out-dir /tmp/ledger
python $R24/tools/research_facts_unchanged.py --round23 docs/audit_artifacts/round_source_linking_t0_t2/round23_t2_completion_20261007/six_ticker/formal_acceptance_verdicts.json \
  --round24 $R24/six_ticker/formal_acceptance_verdicts.json --out /tmp/rf.json      # 研究事实两轮逐项相同 + 六个 run 目录的内容哈希
```

## 3. 测试

命令、退出码、JUnit 与网络陷阱报告都保存在 `test_evidence/`（`*.command.txt`、`*.exitcode`、`*.junit.xml`、`*_net_trap.json`）；每组测试的文件清单也在那里（`BEFORE_TEST_FILES.txt`、`AFFECTED_TEST_FILES.txt`、`UPSTREAM_CITED_NODES.txt`、`PIPELINE_TEST_FILES.txt`）。网络陷阱是 `tools/net_trap_plugin.py`（pytest 插件：非回环地址的 connect / getaddrinfo / urlopen 一律报错并计数）。**只跑受影响的测试，不跑默认全量回归。**

```bash
# 受影响的 16 个文件（约 4 分钟）
PYTHONPATH=$R24/tools NET_TRAP_REPORT=/tmp/net.json python -m pytest -p net_trap_plugin $(cat $R24/test_evidence/AFFECTED_TEST_FILES.txt) -q -p no:cacheprovider --junitxml=/tmp/affected.xml
# 场景映射引用、但上面没覆盖的 10 个上游测试（几秒）
PYTHONPATH=$R24/tools NET_TRAP_REPORT=/tmp/net2.json python -m pytest -p net_trap_plugin $(cat $R24/test_evidence/UPSTREAM_CITED_NODES.txt) -q -p no:cacheprovider --junitxml=/tmp/upstream.xml
# 走真实研究完成路径的 60 个文件（约 28 分钟）
PYTHONPATH=$R24/tools NET_TRAP_REPORT=/tmp/net3.json python -m pytest -p net_trap_plugin $(cat $R24/test_evidence/PIPELINE_TEST_FILES.txt) -q -p no:cacheprovider --junitxml=/tmp/pipeline.xml
python $R24/tools/summarize_junit.py --junit /tmp/affected.xml --junit /tmp/upstream.xml \
  --baseline-junit docs/audit_artifacts/round_source_linking_t0_t2/round23_t2_completion_20261007/test_evidence/full_suite_AFTER.junit.xml --out-json /tmp/s.json --out-md /tmp/s.md
python $R24/tools/render_scenario_map.py --junit /tmp/affected.xml --junit /tmp/upstream.xml --junit /tmp/pipeline.xml --out /tmp/scenario_map.md
```

`NEWTESTS_ON_ROUND23_CODE_*` 是把最终测试放到第 23 轮代码上跑的结果：临时目录里放第 23 轮的 `comqutor_alpha/` 与 `scripts/`（用 `round23_state_of_changed_files/` 还原，不含 `gold_contract_rules.py`）加最终的 `tests/`，`outputs/` 与 `docs/` 用符号链接读仓库的；可重复：`bash $R24/tools/run_newtests_on_round23_code.sh <新的输出目录>`（不写仓库；结果 3 个文件无法导入、19 失败、49 通过），命令全文在 `NEWTESTS_ON_ROUND23_CODE.command.txt`。

测试里的合成 fixture 都在模块文档字符串里**明确标注**；受控修改（把一条真实记录手工改成 B2 做不出的状态）只用来证明检查**能**发现异常，不说成生产 B2 的真实结果。

## 4. 补丁、范围证明、密钥扫描

```bash
python $R24/tools/build_t2_patch.py          # t2_changes.patch / t2_files.json，并用 git archive HEAD + 补丁在临时目录重建核对
python $R24/tools/build_round24_delta.py     # round24_delta.patch / round24_delta.json（第 23 轮状态 → 现在）
python $R24/tools/final_scope_proofs.py --outputs-file-count-before 3253
python $R24/tools/credential_scan.py
python $R24/tools/check_report_numbers.py     # 报告里引用的数字／事实逐项从 JSON 重新推出，写 report_numbers_check.json
python $R24/tools/build_provenance.py --transcript <会话记录 .jsonl> --out-dir /tmp/prov    # 溯源文档（需要会话记录文件）
```

## 已知限制

* **没有 commit**（按指示）：代码身份 = 真实 HEAD `7a9aefa` + `t2_changes.patch`。
* 本入口只执行契约的 **5 条**规则（3 条 Alpha must_detect + NVDA / AMD 两个 composite）；契约的另外 14 条**未执行**（`effective_rules.gold_contract.rules_not_in_effect`）。因此 QQQ、SNDK、TSM 的 `pass` 只覆盖入口执行的内容（`coverage.pass_scope_note`）。
* 同一输入换 run id 回放：研究事实逐项不变，但契约规则的触发绑定 run id，所以变成 `not_evaluable`（有测试）。
* 冻结触发矩阵只对每个标的的**一个 run** 有触发；其它 run 没有已批准且可执行的触发判定方法 → `not_evaluable`（PD-018）。矩阵只记录 run id 和输入文件名，**没有输入文件的哈希**，所以绑定靠 run id。
* 契约 markdown 的哈希与冻结清单记录的不同（John 2026-09-15 要求清理重写）；JSON 本体与冻结哈希一致，入口不读 markdown。
* 两个没通过的测试都是更早就红的，本轮前后失败值完全相同，T2 的文件不在它们的代码路径上，我没有改它们（逐个分析见报告 §8.4）：`test_msft_a102_a304_taxonomy_adjudication::…test_a6_b1_b2_b3_b4_invariant_modules_are_byte_identical`（`alpha_mapper.py` 的钉扎哈希）和 `test_b2_admissibility_integration::test_b2_result_is_computed_once_and_identical_across_detector_db_and_export`（存储层现在保留 `evidence_qualification`，测试仍按“暂不持久化”去掉它）。
* 待负责人决定的事项：`docs/specs/product_decisions_and_unknowns.md` 的 PD-018 … PD-021。
