# Round 25 / T3 最小验证准备：材料包入口

## 人工复核与计分（2026-10-08，最新）

**入口：`D_human_review/D_scoring_report.md`。** 复核人为 Xiang Mao（项目负责人），40 条全部判定。计分不调用网络，冻结驱动未改。

- **Alpha 正式结果（经过生产门之后）**：准确率 65.0%（26/40），非 NONE 精确率 85.7%，召回率 58.1%。
- **Alpha 补充结果（模型原始选择）**：准确率 72.5%，精确率 87.5%，召回率 67.7%。两者只差 3 条被 A001 门否决的样本。
- **其他三环**：
  - L1 在系统有结论的 11 条上一致 6 条；
  - L3 在可比的 18 条上全部一致；
  - L4 可比的 18 条中 15 条双方都判"不合格"。复核人判合格的 4 条，系统一条也没有判合格。
- **口径限制**：
  - 复核非盲：复核人未声明没看过系统输出，复核在执行报告之后进行；
  - 不是 John 验收；
  - 定向样本，不是 80% 目标的复测口径；
  - 不宣称 T3 通过。

## 执行结果（2026-10-08，execution `t3joint-20261008T170322Z-bd99811e`）

**入口：`C_execution_report.md`。** 汇总在 `C_execution_results/`，原始产物在 `outputs/t3_joint_evaluations/t3joint-20261008T170322Z-bd99811e[-materials]/`。

- 请求：模型请求 60 次（内容核验 17、Alpha 40、方向 3），采集 4 次；全部 HTTP 200；没有截断、unknown 或重试，守卫没有触发。
- Alpha：21 条匹配、16 条 NONE、3 条被生产门否决。
- 内容核验：11 条得到结论、6 条被生产校验拒绝、23 条生产不核查。
- 单条证据资格：没有一条进入激活池。
- 原 run 和历史材料共 128 个文件哈希不变。
- 参考判定待复核，**没有计算准确率**；不宣称 T3 通过。

## 第二部分（最新，以此为准）：40 条定向联合验证的执行准备

**入口：`B_execution_proposal.md`。** 这是一份完整、可直接授权的执行清单，对应六项要求：

| # | 交付 | 文件 |
|---|---|---|
| 1 | 冻结的 40 条清单、来源与精确剩余缺口 | `B1_samples_sources_and_gaps.md`、`B1_samples_v4/` |
| 2 | 当前产品配置与拟执行配置的差异 | `B2_config_differences.md`、`B2_config/actual_request_shapes.json` |
| 3 | 各任务及总请求上限 | `B3_budget/`：`budget.json`、`request_sizing.json`、`historical_alpha_answers_COMPARISON_ONLY.json` |
| 4 | 启动命令、预检和停止条件 | `B_execution_proposal.md` 第 4 节；`B4_execution/`：冻结请求、未签署计划模板、预检演练报告 |
| 5 | 必要 diff 与零调用测试结果 | `B5_driver/`（77 passed，外网尝试 0 次） |
| 6 | 隐藏系统答案的复核表及复核人待确认项 | `B1_samples_v4/review_form_v4.json`、`B1_reviewer_instructions_v4.md`；`B_execution_proposal.md` 第 6 节 |

第二部分的要点：
- 40 条 Alpha **全部为新预测**（上限 40）；33 条已保存的生产答案只作历史对照。
- 内容核验 17 次，复用 0 条；方向最多 13 次。预测合计 ≤70 次，另行授权的采集 ≤4 次。
- 材料状态：27 条 COMPLETE、7 条 PARTIAL、4 条待采集、2 条没有可核对事实。**来源环未完成。**
- 发送守卫、检查点和发送前演练会阻止任何与冻结内容不符的请求。

**第二部分取代的第一部分内容：**
- `06_execution_proposal.md` 中"复用 33 条历史答案 + 7 条新请求"的方案，以及该方案的 29 次预算，已作废；
- `04_joint_sample/`（v3）的复核表由 `B1_samples_v4/`（v4）取代；
- 第一部分 `06` 的其余事实性内容（超时数据、更正）仍然有效。

---

## 第一部分（2026-10-08 上午）

本目录是 T3 的离线准备批次，交给项目负责人和 John。**这是材料索引和执行提案，不是签收。**
- 不宣称 T3 通过。
- 不把开发集成绩当作独立验证。
- 不追加 H2 重测或新的 Fresh。

**本轮边界：**
- 零 Provider、搜索、取数和模型调用：所有生成步骤和测试都在网络陷阱下运行，外网尝试 0 次。
- 不启动 Fresh，不改部署环境或服务（8000/5175 未动）。
- 不 commit / push。
- 未修改 taxonomy 含义、评分阈值、Gold 答案或 80% 目标，也没有新增生产人工审核要求。
- 生产代码（`comqutor_alpha/`）未改。

**下一步是等待真实执行授权**（`06_execution_proposal.md`）。

## 六项交付

| # | 交付 | 文件 |
|---|---|---|
| 1 | 四步配置对照（历史评估 / 各真实运行 / 拟冻结，分列） | `01_config_comparison.md`、`01_config_comparison.json` |
| 2 | 旧样本暴露台账与标签身份台账 | `02_exposure_and_label_ledger.md`、`.json` |
| 3 | A304 五类情形映射与 A101/A103 歧义记录 | `03_a304_five_situations_and_a101_a103.md`、`.json` |
| 4 | 新 40 条样本清单、来源与缺口、盲审表单 | `04_samples_sources_and_gaps.md`（系统侧，不给复核人）；`04_joint_sample/`（冻结清单、表单、工作表）；`04_reviewer_instructions.md`（给复核人）；`04_joint_sample_pool_scan.json` |
| 5 | 五环驱动的必要改动与零调用测试结果 | `05_driver/README.md`、`t3_joint_verification_driver.round25.diff`、`driver_files.json`、`driver_copies/`、`freeze_identity.json`、`test_evidence/` |
| 6 | 统一真实请求预算与执行提案 | `06_execution_proposal.md`；`06_proposal/`（`budget.json`、`request_sizing_zero_call.json`、`stance_timeout_evidence.json`、`authorized_plan_TEMPLATE.json`，模板未签署） |

其他：
- `code_snapshot/`：代码身份，即 HEAD `7a9aefa`、完整工作区差异、未跟踪源码副本和哈希。
- `tools/`：本轮全部脚本。
- `credential_scan_result.json`：密钥扫描结果。

## 关键事实

1. **v7（当前生产 Alpha prompt）没有合格的人工参考评估。**
   - 82.67%（Candidate-3）和 87.23%（H2）是 Anthropic 模型测出来的，不算给 DeepSeek。
   - v6 的诊断成绩只属于 v6。
   - v7 只做过 19 条开发验证，对照的是 AI 意见。
   - 之前 40 条的方向结果只作为定向诊断。
2. **旧 40 条样本：**
   - 21 条用于修复，转入开发回归：19 条 v7 开发样本，加上 gold-dev-068、prod-run-008。
   - 2 条无法确认。
   - 17 条只做过预测或分析，**不声称是独立盲测，也不认定失效**。
   - 10-05 导入的标签身份未记录：没有授权和批准记录，不能说它满足 John 的参考标准。
   - 11 条历史 Gold 分歧只列出，不裁定。
3. **新 40 条样本（16/8/4/4/4/4）：**
   - 25 条完整链：来源都是数据行。
   - 15 条部分链：A102 和 A501 全部没有来源正文，原因是 news 来源没有保存正文。**来源忠实性环在这些格没有原始依据，不能说"来源环已完成"**。
   - 关键结论 7 条；在保存 run 里进入过冲突原始池的 11 条。
   - 标的集中：AMD 33 条、NVDA 7 条。
4. **执行提案：** 总共最多 29 个请求（内容核查 17、Alpha 7、方向 ≤5）。33 条 Alpha 复用已保存的生产答案，按哈希逐项绑定，重放结果与原 run 一致。两层重试都为 0，不用缓存，失败只记录不重跑。
5. **范围外的生产问题（只报告，未修）：**
   - 内容核查任务不进调用账本（`SEMANTIC_TASKS` 缺登记）。
   - 生产默认 5 条一批会超出 6 万字符输入上限。
   - 旧账本的耗时字段在部分 run 里不可靠。
   - **更正：** 第 17 轮"方向成功批次最长 657 s"不成立。已保存数据中没有任何方向请求在 45 s 之后完成。

## 需要负责人决定（详见 06 第 7 节）

| 编号 | 事项 | 建议 |
|---|---|---|
| D1 | Alpha 复用 33 条已保存答案 | 复用 |
| D2 | Alpha 输出上限 | 不发送；4,096 为备选 |
| D3 | 方向超时 | 120 s；45 s 以上没有数据 |
| D4 | 内容核查改为单条发送 | 是 |
| D5 | 内容核查输出上限 | 不发送 |
| D6 | 内容核查超时 | 120 s |
| D7 | 复核人 | John 或 John 指定的人，复核另行安排 |

## 复现（仓库根目录；全部零调用）

```bash
source .venv/bin/activate
P=docs/audit_artifacts/round_source_linking_t0_t2/round25_t3_minimal_prep_20261008; D=docs/audit_artifacts/round_source_linking_t0_t2
python $P/tools/build_config_comparison.py --out /tmp/r25_01.json          # 与 01_config_comparison.json 相同
python $P/tools/build_exposure_ledger.py --out /tmp/r25_02.json            # 与 02 相同
python $P/tools/build_a304_mapping.py --out /tmp/r25_03.json               # 与 03 相同
python $P/tools/scan_joint_pool.py --out /tmp/r25_scan.json                # 与 04_joint_sample_pool_scan.json 相同
python $P/tools/select_joint_sample.py --out-dir /tmp/r25_04               # 三个文件与 04_joint_sample/ 逐字节相同
python $P/tools/run_with_network_trap.py $D/t3_joint_sample_driver.py sizing --manifest $P/04_joint_sample/joint_sample_v3_manifest.json --out /tmp/r25_sizing.json
python $P/tools/stance_timeout_evidence.py --out /tmp/r25_stance.json
bash $P/tools/run_affected_tests.sh final                                  # 受影响测试，带网络陷阱；输出写入 05_driver/test_evidence/
```

本目录内的 `__pycache__` 已清理。历史 run、第 17 轮至第 24 轮的目录和历史 Gold 都只读，未改。
