# John T3 要求逐条对应表

John 原文来自 `COMQUTOR Alpha 下一轮开发任务单.docx` 的第五节"T3：核对实际模型，并修复最有影响的语义错误"，以及第七节"最终交付与签收标准"，引用时逐字照抄。

状态只说明这份包对每条要求交付了什么，**不代表 John 已签收**。下表中的路径若没有写前缀，都相对于 `docs/audit_artifacts/round_source_linking_t0_t2/`。

## 第五节 1："先确认验证与产品使用的是不是同一配置"

| John 原文 | 交付 | 文件 | 状态 |
|---|---|---|---|
| "请提交如下配置对照……Structured Adapter／Alpha Classifier（注明 batch／单条路径）／Polarity Classifier／Structure Extractor" | 四步配置对照，三类配置分列（历史评估、各真实运行、拟冻结）；本次执行没有调用 Structured Adapter 和 Structure Extractor，已写明 | `round25…/01_config_comparison.md`、`.json` | 已交付 |
| 同上，"实际产品配置／对应验证配置／是否一致" | 三个实测任务的三列对照：现行部署、执行时冻结配置、新 profile；profile 与执行配置逐项相同，现行部署与执行配置在超时、批次、重试、审计上不同 | `round26…/03_task_profile/task_profile.md`、`config_before_after.json`；`round25…/B2_config_differences.md` | 已交付 |
| "若产品 Alpha 分类配置不同，应使用当前部署配置进行验证。不能把另一配置的成绩直接算到产品头上。" | 成绩只归属于执行时的冻结配置。Alpha 与现行部署的差别只有重试（部署 1，执行 0）和审计开关，模型、prompt、单条路径、超时和并发都相同。可选的 profile 已接入；用现行部署配置做真实验证属于 T4 | 主报告第 2 节；`task_profile.md` | **部分**：真实部署配置验证未做，需要真实请求（T4） |

## 第五节 2："修复顺序"

| John 原文 | 交付 | 文件 | 状态 |
|---|---|---|---|
| "先处理 A304 误报，再检查 A101／A103 的边界……请从原始错误样本检查，不要仅靠调整全局阈值" | 原始错误样本逐条对应到五种情形和 v7 条款；v7 修改差异和裁定记录；本次 40 条中的 A304、A101／A103 误差也对应到同一套问题 | `round25…/03_a304_five_situations_and_a101_a103.md`；`alpha_classifier_prompt_v7_diff.patch`；`t3live_20261001T014648Z_1fb9c9d5_prompt_v7_adjudication.md`；`round26…/04_reports/a304_a101_a103_correspondence.md` | 已交付；本轮没有再调 prompt |
| "重点区分：提到了估值、讨论估值风险、反驳估值风险、提出条件性风险、已有数据支持估值压缩" | 五种情形与 v7 条款的映射；新误差主要集中在 S4（条件性）和 S3（反驳） | 同上 | 已交付 |
| "保持现有 Taxonomy 的定义；发现定义确有歧义时单独提出……也不能通过全部不输出 A304 来'解决'误报" | taxonomy 没有改动，哈希与执行冻结快照一致（`c6d523be…`）；歧义单独列为 A304-Q1 至 Q4、A101/A103-Q5 至 Q7；A304 仍在正常输出（原始选择 7 次） | `round25…/D_human_review/intake_check.json`；`issue_list.md` P-3 | 已交付；语义问题待 John 裁定 |

## 第五节 3："增加一组有限的联合复核"

| John 原文 | 交付 | 文件 | 状态 |
|---|---|---|---|
| 40 条：A304 边界 16，A101／A103 8，A001、A003、A102、A501 各 4 | v4 冻结清单，各格数量与要求一致；3 条替换都有记录 | `round25…/B1_samples_v4/`（manifest、复核表、替换记录） | 已交付 |
| "样本应附原始来源片段、适用对象和时间" | 复核表逐条附材料（数据行、字段、新闻标题、市场数据行）和时间依据；037 至 040 另外采集的材料在预测前已固定 | `review_form_v4.json`；`round25…/C_execution_results/review_materials_frozen_ADDENDUM.json` | 已交付；材料限制见 `issue_list.md` M-1、M-2 |
| "预测前固定样本和配置" | 签署计划固定了代码身份、prompt 身份、冻结请求和配置；发送守卫逐个比对请求；本轮再次核对，代码身份与签署计划一致 | `round25…/B4_execution/`；`round26…/hash_proof/code_identity_before_changes.json` | 已交付 |
| "参考判定由 John 或指定复核人完成，审核时不展示系统答案" | 复核人是 Xiang Mao（项目负责人）；没有声明未看过系统输出；部分系统答案在复核前已披露 | `round25…/D_human_review/` | **未完全满足**：复核非盲，复核人资格待决定（`issue_list.md` P-6） |
| "不能自行标记 john_approved=true" | 包内没有任何 John 批准标记；授权人写的是项目负责人 | 签署计划；复核表 | 已遵守 |
| 每条联合检查：来源内容 → claim 是否忠实 → Alpha 是否正确 → 支持／反对方向 → 是否进入 activation／admitted conflict | 逐条五环结果；本轮补充了关系消费链路和来源资格 | `round25…/C_execution_results/per_sample_results.jsonl`；`D_human_review/score_supplement.json`；`round26…/02_relation_consumption/relation_chain.json` | 已交付；冲突准入只给了单条资格，run 级冲突不在本集合范围内 |
| "总体准确率、非 NONE 精确率、召回率、各类样本量、混淆矩阵、弃权及调用失败数。不能把解析失败当作正确的 NONE" | 正式计分全部给出；门否决单独列出；调用失败 0 次，弃权 0 次 | `round25…/D_human_review/score_result_official.json` | 已交付 |
| "不追溯改变原定 80% 目标……保留真实成绩；已用于修复的样本转入开发回归，不再称独立盲测" | 不用这 40 条判定 80% 目标；正式成绩不变；引用修复用到的样本标为开发回归，开发回归视角单独存放 | 主报告第 2、3 节；`05_offline_replay/after_all_fixes/score_DEV_REGRESSION_VIEW_not_official.json` | 已交付 |

## 第七节："最终交付与签收标准"（只列 T3 相关部分）

| John 原文 | 交付 | 状态 |
|---|---|---|
| 代码与配置："commit、diff、实际有效规则、taxonomy、运行配置" | 按指示没有 commit；提供代码身份（HEAD 加 tracked diff 哈希）、本轮最小 diff、改动前副本、taxonomy 哈希、实测运行配置 | **commit 未做**（按指示），其余已交付 |
| 测试与语义验证："原始样本、逐条预测、审核记录、自动生成的统计、测试日志" | 都在 ZIP 中，见 README | 已交付 |
| 实际运行："完整 artifacts、原始调用记录" | 执行目录（检查点、请求与回复审计、账本、预测）和采集材料目录都在包内；PostgreSQL 和 Fresh Run 属于 T4 | T3 部分已交付 |
| 使用证明："Demo 视频和一份可复制执行的 README" | README 给出可执行的零网络复现命令；Demo 按本轮指示不处理 | README 已交付；Demo 不在本轮 |
| "改了哪段代码？用什么输入运行？实际结果是什么？还有什么没有通过？" | 主报告第 1 节 | 已交付 |
