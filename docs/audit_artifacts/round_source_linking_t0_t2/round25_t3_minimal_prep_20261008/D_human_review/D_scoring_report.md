# T3 40 条定向联合验证：人工复核后的计分结果

- **执行**：`t3joint-20261008T170322Z-bd99811e`，系统预测见 `C_execution_report.md`。
- **复核人**：Xiang Mao，角色 `PROJECT_OWNER_HUMAN_REVIEWER`。40 条都已判定，确认时间 2026-10-08 11:28:05 PDT（18:28:05Z）。
- **计分**：
  - 正式结果用冻结驱动的 `score` 命令，驱动未改动，产出 `score_result_official.json`。
  - 补充视角由 `tools/score_review_supplement.py` 生成，产出 `score_supplement.json`，复用同一个打分函数。
  - 两者都在网络陷阱下运行，外网尝试 0 次。

**这些数字衡量的是系统与项目负责人复核结果的一致程度。** 它们不是 John 的验收，也不是盲审下的独立测量，不宣称 T3 或任何 Alpha 通过。原因有三：

1. 复核人没有声明"复核前未看过系统输出"（40 条的 `attests_no_prior_view_of_system_outputs` 都是 `false`）。
2. 复核在预测完成（17:55:25Z）和执行报告交付之后进行。执行报告已经点名披露了部分系统答案：
   - t3v3-019、027R、028 选 A001 后被生产门否决；
   - t3v3-003 反对 A001；
   - t3v3-037、039、040 反对 A501；
   - t3v3-038 判为中性背景；
   - t3v3-006 的资格判断。
   这些样本上的一致不能当作独立证据。
3. 这 40 条是按边界格定向抽取的诊断样本，不代表市场分布，也不是 80% 目标的复测口径。

## 1. 接收核对（`intake_check.json`）

| 项目 | 结果 |
|---|---|
| 表单身份 | 40 条，顺序不变。除 `judgments` 外，每条的声明、上下文、材料都与 `review_form_v4.json`（`6842817f…`）逐字段相同。顶层只改了 `instructions` 说明文字 |
| 判定完整性 | 每条五项判定都已填写，取值都在表单词表内，没有被跳过或判为无效的条目 |
| taxonomy | 复核人使用的文件哈希为 `c6d523be…`，与本次执行冻结代码快照（`code_snapshot_partB/file_hashes.json`）记录的哈希相同。复核说明里"未能核实完整文件身份"这一项，现在可以确认一致 |
| 补充件 | 三个市场原始响应文件的 sha256 与补充件记录相同，市场查找响应也相同。复核说明里"原始响应 hash 无法独立核对"这一项，现在已核对 |
| 复核人引用的日价格 | 8 个点（美国 09-25、09-28、10-02、10-05，英国 10-05，日本 10-02、10-04、10-05）都与原始数据一致 |
| 复核人的数值复算 | 16 项按同样的输入重算，都与复核说明的数值一致 |

## 2. L2 Alpha（John 要求的指标）

40 条都参与计分：复核人没有选 UNABLE_TO_JUDGE，系统调用失败 0 次，弃权 0 次。

| 视角 | 准确率 | 非 NONE 精确率 | 非 NONE 召回率 |
|---|---|---|---|
| **正式：经过生产门之后**（门否决记为 SELECTED_BUT_NOT_MATCHED） | **65.0%**（26/40） | **85.7%**（18/21） | **58.1%**（18/31） |
| 补充：模型原始选择（不计生产门） | 72.5%（29/40） | 87.5%（21/24） | 67.7%（21/31） |

两者只差 3 条：t3v3-019、027R、028。复核人判为 A001，模型也选了 A001，但被 A001 的 `alpha_specific_invalidation` 门否决。复核人明确说明不把这个门的覆盖当作参考真值，所以两个视角都列出。

**样本量很小，区间很宽。** 下面的区间是我补充的 Wilson 95% 区间，不属于 John 要求的指标：
- 正式准确率：49.5%–77.9%；
- 原始准确率：57.2%–83.9%。

**混淆矩阵**：行是复核人，列是系统，取正式视角。

| 复核人 \ 系统 | A304 | A001 | A101 | A102 | A501 | NONE | 门否决 | 合计 |
|---|---|---|---|---|---|---|---|---|
| A304 | 7 | 1 | | | | 7 | | 15 |
| A001 | | | | | | 1 | 3 | 4 |
| A101 | | | 3 | | | | | 3 |
| A103 | | | 1 | | | | | 1 |
| A102 | | | | 4 | | | | 4 |
| A501 | | | | | 4 | | | 4 |
| NONE | | | 1 | | | 8 | | 9 |
| 合计 | 7 | 1 | 5 | 4 | 4 | 16 | 3 | 40 |

**分格**（正式 / 原始）：

| 格 | 正式 | 原始 |
|---|---|---|
| A304 边界 | 7/16 | 7/16 |
| A101/A103 | 5/8 | 6/8 |
| A001 | 2/4 | 4/4 |
| A003 | 4/4 | 4/4（全部为 NONE，与复核一致） |
| A102 | 4/4 | 4/4 |
| A501 | 4/4 | 4/4 |

**正式视角下的 14 条不一致：**

| 类型 | 样本 | 说明 |
|---|---|---|
| 复核 A304，系统 NONE | 001、007、009、011、012、014、015 | 最主要的误差来源：复核人判为 A304 的 15 条里漏了 7 条。复核人自己标注 001、009 存在语义边界 |
| 复核 A304，系统 A001 | 003 | 系统判为反对 A001 |
| 复核 A001，系统 NONE | 016 | |
| 复核 A001，生产门否决 | 019、027R、028 | 原始选择与复核一致 |
| 复核 NONE，系统 A101 | 022R | |
| 复核 A103，系统 A101 | 024R | 复核人标注 A101 或 NONE 也"可讨论" |

另有历史对照（不是准确率）：33 条有历史答案的样本中，30 条本次原始选择与历史相同。

## 3. L1 来源→claim

- **系统给出结论的 11 条**：与复核人一致 6 条，一致率 **54.5%**。不一致的 5 条，系统都比复核人严：
  - 012、013、016：系统判证据不足（INSUFFICIENT），复核人判 CONDITIONAL；
  - 014：系统判 BACKGROUND，复核人判 SUPPORTS；
  - 030：系统判 CONDITIONAL，复核人判 SUPPORTS。
- **生产校验拒绝的 6 条**（回复引用的原文或数据在候选材料里找不到）：
  - 复核人判 SUPPORTS 3 条：005、029、031，复核人都认为声明忠实于材料。这 3 条的失败出在系统一侧，不是材料不足；
  - 复核人判 CONDITIONAL 3 条：002、015、019。
- **生产不核查的 23 条**（15 条没有链接，8 条链接 TIME_INVALID）：复核人判 CONDITIONAL 18、SUPPORTS 2（010、039）、CITATION_ONLY 1（027R），2 条无法判断（032、036）。
- **复核人的来源忠实性判定**：
  - FAITHFUL 8、MINOR_DEVIATION 1（039）、MATERIAL_DEVIATION 1（026，股价与均线对象错配）、UNABLE_TO_JUDGE 30；
  - 大多数无法判断的原因相同：复合句里有一部分没有材料支持，而不是声明错误。

## 4. L3 方向

只比较复核人与系统选了同一 Alpha、且系统有 LLM 方向的样本：

- 比较 18 条，一致 18 条（**100%**）；
- 其中 037–040 的方向在复核前已披露，见文首第 2 条；
- 另外 3 条两边选的 Alpha 不同（003、022R、024R），19 条系统没有 Alpha，都不比较。

## 5. L4 单条证据资格

比较 18 条，一致 15 条（83.3%）。**这个比例不能当作资格判断准确。** 系统对全部 21 条都判"不进入"，这 15 条一致都是双方同判"不合格"。

复核人判为合格（QUALIFIES）的 4 条，系统一条也没有判合格：

| 样本 | 复核 | 系统 | 系统在哪一步没通过 |
|---|---|---|---|
| 005 | A304 支持，合格 | A304 支持 | L1 回复被生产校验拒绝（复核人判忠实），所以已验证支持门判 NOT_REVIEWED；选择器又以 RELATION_NOT_SUPPORTING 排除 |
| 006 | A304 支持，合格 | A304 支持，已验证支持门 ELIGIBLE | 只被选择器以 RELATION_NOT_SUPPORTING 排除 |
| 014 | A304 支持，合格 | Alpha 为 NONE | 在 L2 就漏掉了，没有资格判断 |
| 039 | A501 反对，合格 | A501 反对 | 激活池只收支持证据，这条在定义上就进不去；另外没有有效来源链接，采集的材料不属于原 run |

复核人的 R4 只判断单条语义资格，不代表通过了生产的时间、哈希、角色、去重、权重或冲突门。所以 039 这一条的差异主要来自两边定义不同。

## 6. 发现（只报告，本轮不改）

1. **A304 召回偏低**：复核人判为 A304 的 15 条里，系统有 7 条给了 NONE。系统在 A304 上偏保守：选中时基本选对，非 NONE 精确率高，但漏得多。
2. **A001 门与复核口径冲突**：3 条反对或提及 A001 的声明，被 `alpha_specific_invalidation` 整条否决。复核人认为这类声明应该保留 A001 关联，并标注反对或提及方向。
3. **L1 校验误拒**：6 条生产校验拒绝的回复里，有 3 条复核人判为忠实且支持。
4. **选择器与方向任务不一致**：选择器的 relation 读的是 Alpha Mapper 自己给出的 relation 字段（`relation_for_match`），不是方向任务的 LLM 结果。005 和 006 的 LLM 方向都是 supports_alpha，复核人也判支持，但都被这个字段排除。

是否修改、怎么修改，由负责人或 John 决定。本轮没有改 prompt、taxonomy、生产门或评分，也没有重测。

## 7. 文件与复现

- `review_form_v4_Xiang_Mao_HUMAN_REVIEWED.json`（`433bd701…`）和 `T3_Xiang_Mao_review_explanations.md`（`844a1db8…`）：复核人上传文件的逐字节副本。
- `intake_check.json`、`score_result_official.json`、`score_supplement.json`。其中 `score_supplement.json` 的 `per_sample` 字段逐条列出复核判定和系统各环结果。

```bash
source .venv/bin/activate
P=docs/audit_artifacts/round_source_linking_t0_t2/round25_t3_minimal_prep_20261008; D=docs/audit_artifacts/round_source_linking_t0_t2
E=outputs/t3_joint_evaluations/t3joint-20261008T170322Z-bd99811e; R=$P/D_human_review
python $P/tools/run_with_network_trap.py $D/t3_joint_sample_driver.py score --predictions $E/joint_predictions.jsonl \
  --review-form $R/review_form_v4_Xiang_Mao_HUMAN_REVIEWED.json --history $P/B3_budget/historical_alpha_answers_COMPARISON_ONLY.json --out /tmp/score.json
python $P/tools/run_with_network_trap.py $P/tools/score_review_supplement.py --predictions $E/joint_predictions.jsonl \
  --review-form $R/review_form_v4_Xiang_Mao_HUMAN_REVIEWED.json --original-form $P/B1_samples_v4/review_form_v4.json \
  --addendum $P/C_execution_results/review_materials_frozen_ADDENDUM.json --materials-dir $E-materials --run-summary $E/run_summary.json \
  --code-file-hashes $P/code_snapshot_partB/file_hashes.json --out-dir /tmp/supplement   # 两个结果文件已存在时拒绝覆盖
```

本轮没有发出任何 Provider、搜索或取数请求，原 run 和执行目录都只读。
