# T3 交付包（execution `t3joint-20261008T170322Z-bd99811e`）：可执行 README

**入口**：先看主报告 `00_T3_main_report.md`。在 ZIP 里，它位于 `docs/audit_artifacts/round_source_linking_t0_t2/round26_t3_closeout_20261008/00_T3_main_report.md`。

## 1. 包里有什么（ZIP 内路径与仓库内路径相同）

| 内容 | 路径 |
|---|---|
| 收尾目录：报告、诊断、重放、配置、测试日志、哈希证明、工具 | `docs/audit_artifacts/round_source_linking_t0_t2/round26_t3_closeout_20261008/` |
| Round 25 整包：40 条冻结样本、材料、冻结请求、签署计划、执行结果、人工复核文件、正式计分、补充视角 | `docs/audit_artifacts/round_source_linking_t0_t2/round25_t3_minimal_prep_20261008/` |
| 真实请求与回复、检查点、账本、逐条预测 | `outputs/t3_joint_evaluations/t3joint-20261008T170322Z-bd99811e/` |
| 采集的市场材料和原始响应 | `outputs/t3_joint_evaluations/t3joint-20261008T170322Z-bd99811e-materials/` |
| 样本来源：3 个原 run 的结构化输出、来源登记和行情快照 | `outputs/runs/<run_id>/{structured_agent_outputs,source_registry,market_data_snapshot}.json` |
| 冻结驱动（未改动） | `docs/audit_artifacts/round_source_linking_t0_t2/t3_{joint_sample,diagnostic_evaluation,joint_verification}_driver.py` |
| v7 修改记录、A304 根因分析、配置对照等已有材料 | 同目录下的 `alpha_classifier_prompt_v7_diff.patch`、`t3live_…_prompt_v7_adjudication.md` 等 |
| 契约依据 | `docs/specs/product_decisions_and_unknowns.md`、`docs/specs/semantic_authority_matrix.csv` |
| 本轮代码：改动后的生产文件、新测试、最小 diff | `code/after/…`、`code/diff/` |
| 改动前副本 | 收尾目录下的 `code_before/` |
| 逐文件 SHA256、依赖说明 | `SHA256SUMS.txt`、`MANIFEST.json`、`dependencies.txt` |

**不包含**：`.env`、任何凭据或鉴权头（请求审计中鉴权头已写为 `REDACTED`）、与 T3 无关的项目文件。

## 2. 环境

- **代码**：仓库 HEAD `7a9aefa`，加上工作区改动（本轮没有 commit），即 `hash_proof/code_identity_after_changes.json` 记录的身份。
  - 本轮改动的文件在 `code/after/` 和 `code/diff/closeout_minimal.diff` 里。
  - 收尾目录下的 `code_before/` 是改动前的副本，已与执行冻结快照核对过哈希。
- **Python**：仓库自带的 `.venv`（版本和包列表见 `dependencies.txt`，由 `pip freeze` 生成）。
- **运行位置**：所有命令都在仓库根目录运行，因为工具和驱动会从仓库导入 `comqutor_alpha`。ZIP 只提供输入和预期输出。
- **网络**：每条命令都包在网络陷阱里（`tools/run_with_network_trap.py`）。命令末尾会打印 `network attempts: 0`，有任何外网尝试都会失败。

```bash
cd <仓库根目录>
source .venv/bin/activate
U=<ZIP 解压目录>
X=docs/audit_artifacts/round_source_linking_t0_t2/round26_t3_closeout_20261008
R25=docs/audit_artifacts/round_source_linking_t0_t2/round25_t3_minimal_prep_20261008
E=outputs/t3_joint_evaluations/t3joint-20261008T170322Z-bd99811e
```

## 3. 复现命令（全部零网络）

**3.1 校验包内文件**

```bash
(cd "$U" && shasum -a 256 -c --quiet SHA256SUMS.txt && echo "all files match")   # 只打印不一致的文件
```

**3.2 复现正式计分**：输入取自解压包，输出与包内的正式计分逐字节比较。

```bash
rm -f /tmp/t3_score.json   # 工具不覆盖已有输出
python $X/tools/run_with_network_trap.py docs/audit_artifacts/round_source_linking_t0_t2/t3_joint_sample_driver.py score \
  --predictions "$U/$E/joint_predictions.jsonl" \
  --review-form "$U/$R25/D_human_review/review_form_v4_Xiang_Mao_HUMAN_REVIEWED.json" \
  --history "$U/$R25/B3_budget/historical_alpha_answers_COMPARISON_ONLY.json" --out /tmp/t3_score.json
cmp /tmp/t3_score.json "$U/$R25/D_human_review/score_result_official.json" && echo "official score reproduced"
```

**3.3 复现补充视角**（原始选择、分格、逐条对照，以及接收核对）

```bash
rm -rf /tmp/t3_supplement
python $X/tools/run_with_network_trap.py $R25/tools/score_review_supplement.py --predictions $E/joint_predictions.jsonl \
  --review-form $R25/D_human_review/review_form_v4_Xiang_Mao_HUMAN_REVIEWED.json --original-form $R25/B1_samples_v4/review_form_v4.json \
  --addendum $R25/C_execution_results/review_materials_frozen_ADDENDUM.json --materials-dir $E-materials --run-summary $E/run_summary.json \
  --code-file-hashes $R25/code_snapshot_partB/file_hashes.json --out-dir /tmp/t3_supplement
cmp /tmp/t3_supplement/score_supplement.json $R25/D_human_review/score_supplement.json && echo "supplement reproduced"
```

**3.4 离线重放**：用保存的真实回复走一遍生产预测路径，只替换 HTTP transport。

```bash
rm -rf /tmp/t3_replay
python $X/tools/run_with_network_trap.py $X/tools/replay_execution_offline.py --work-dir /tmp/t3_replay
# 当前代码上应打印：saved_responses_used 60, requests_without_saved_answer 0, guard_tripped null, differences 6
# 这 6 处与 $X/05_offline_replay/after_all_fixes/replay_summary.json 相同；修复前的代码上 differences 为 0（见 before_fix/）
```

**3.5 六条引用拒绝的逐条诊断，以及关系消费链路**

```bash
python $X/tools/run_with_network_trap.py $X/tools/diagnose_citation_rejections.py --out /tmp/six.json
python $X/tools/run_with_network_trap.py $X/tools/trace_relation_consumption.py --replay-dir /tmp/t3_replay \
  --review-form $R25/D_human_review/review_form_v4_Xiang_Mao_HUMAN_REVIEWED.json --out /tmp/relation_chain.json
```

**3.6 配置对照**：从生产网关实测读回。

```bash
python $X/tools/run_with_network_trap.py $X/tools/build_config_comparison.py --out-json /tmp/config.json   # 应打印 profile_equals_execution: true
```

**3.7 受影响测试**：日志、JUnit、退出码写入 `test_evidence/`；用新标签运行，不会覆盖已有结果。

```bash
bash $X/tools/run_affected_tests.sh rerun
# 本包记录的结果：704 passed，4 failed，1 skipped，外网尝试 0 次；4 个失败的归因见 test_evidence/README.md
```

**3.8 原产物未变证明**

```bash
rm -f /tmp/after.json
python $X/tools/run_with_network_trap.py $X/tools/hash_readonly_inputs.py --out /tmp/after.json --compare $X/hash_proof/readonly_inputs_before.json
# 应打印 "unchanged": true
```

## 4. 选用本次验证的配置（产品 profile）

```bash
export COMQUTOR_WEEK2_LLM_PROFILE=t3_verified_20261008
```

- 取值和作用范围见 `03_task_profile/task_profile.md`。
- 不设置时行为不变。
- 这个 profile 不改变模型、prompt、taxonomy 或判断标准。
- 选用后的真实产品运行证明属于 T4，本包没有提供。

## 5. 证明范围

- 正式成绩只有一份：Round 25 `D_human_review/score_result_official.json`，本轮没有改动。
- 离线重放、固定 HTTP 响应和构造夹具只证明接线和规则，不是新的真实模型验证。
- 复核非盲，复核人是项目负责人，指标表示与这位复核人判断的一致程度。
- 这份包不等于 John 签收。
