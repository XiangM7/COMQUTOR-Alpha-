# 阶段A：AMD 正式评分实际阻塞追踪（2026-10-06）

零外部调用，未改代码、未启动 Fresh Run。输入哈希见 `00_input_hashes.txt`；
完整逐 Alpha/逐冲突数据见 `01_per_alpha_per_conflict_staged_trace.json`。

## A.1 确认真实 run

`1bad76a7-72ac-4c8b-8189-2e5c0f1a6105`，ticker=AMD，analysis_date=2026-10-05，
llm_provider=deepseek，selected_analysts=[news, fundamentals]——完整 ID、
metadata、全部24个文件均已核实存在，未凭摘要替换。

当前代码 HEAD=`7a9aefa`（未变），300个文件处于未提交修改/新增状态
（本轮累积的真实工作状态，非本次新引入）。

## A.3 真实调用点核查（不是"调用 wrapper 证明应该接通"）

直接读代码，沿调用链追到底：`routes_research.py:3476`
`week2_llm_gateway = build_server_week2_llm_gateway(...)`（真实生产
Gateway，和 alpha_classifier 用的是同一个）→ `_run_week1_week2_artifact_
pipeline` → `save_structured_agent_outputs(run_dir, llm_gateway=llm_gateway)`
→ `adapt_run_outputs(..., llm_gateway=llm_gateway)` → 第九轮的
`apply_llm_content_support_verification(records, sources, llm_gateway=
llm_gateway)`。**确认：这条路径是真实生产入口会走到的，不是只能被测试
手动调用的孤立函数。**

但是——直接读取 AMD 这个 run 自己已保存的 `structured_agent_outputs.json`
的 `metadata` 字段，确认：**没有 `content_support_llm` 统计字段，没有一条
记录带 `content_support_llm_detail`，`evidence_cutoff_at` 也是 `None`**。
这证明：这份已保存的真实数据，是在第七轮（时间修复）和第九轮（LLM 核验）
代码写出来**之前**产生的——AMD 这次 Fresh Run 本身跑在 10:36-10:47，
早于这几轮修复。**第九轮的 LLM 任务从未真正对这份 AMD 数据执行过一次**，
无论是真实调用还是固定响应模拟。

## A.4 逐 Alpha 真实链路漏斗（全部10个 Alpha，真实数字）

| 阶段 | 数量 |
|---|---|
| 被分类器真实匹配到某个 Alpha（跨全部10个 Alpha 求和） | 113 |
| 其中来源可定位（source_link_status=VALID） | 20 |
| 其中内容支持已验证（content_support_status=SUPPORTS） | **0** |

**20 条里没有一条被验证**，全部停在 `PENDING_REVIEW`，
`content_support_method=UNVERIFIED_OFFLINE_CONTENT_MATCH`（原始未核验
标记）。以 A304 为例（36匹配→7可定位）：7条里5条是 analytical、2条
context_only，**全部**卡在 PENDING_REVIEW——这正是第九轮21条分析性
声明里已经点名的那批真实 claim_id（如 `fundamentals_report:claim:29/107`、
`bull_history:claim:61`、`investment_plan:claim:8`、
`aggressive_history:claim:17`）。

**这就是真实的第一个阻塞点**：不是"context_only 被挡住"（第八轮已查清、
且本身是正确设计，不需要修），是**第九轮能处理的那批真实、已来源可
定位的分析性声明，从未被实际核验过一次**——machinery 是真的（A.3已
证实接线正确），只是从未执行。全部10个 Alpha 的 `official_v2_verified`
状态因此清一色 `candidate`/分数0/方向`unknown`，`exposure_adjusted_score`
查无记录（`entity_alpha_exposures.json` 里没有任何一个 Alpha 的条目——
侧面印证零条正式证据，Exposure 阶段无事可做）。

## A.5 逐候选冲突真实追踪（全部8对）

8对候选冲突，`admissibility` 全部为 `null`，`reason_codes` 全部含
`DIRECTION_ROLE_UNRESOLVED`（2对额外带 `MISSING_LEFT_EVIDENCE`，2对带
`MISSING_RIGHT_EVIDENCE`）——根因已在第七轮查清并在此确认未变：官方层
(v2_verified) 10个 Alpha 的 `direction` 全部是 `unknown`（上面 A.4 的 0
条验证直接导致），`resolve_bull_bear` 两侧都拿不到正/负方向时返回
`None`，代码在到达真正的可采性判定函数（`evaluate_conflict_
admissibility_verified`）**之前**就提前返回——不是"跑了可采性判断，
判定不可采"，是这个函数**从未被调用过**。完整8对的
`qualifying_count`/`reason_codes` 见 JSON，6/8对实际有非零的原始
(raw)合格候选证据（如 A301 vs A304：12 对 18），只有2对（A003/A501、
A102/A304）是真的一侧零候选。

## A.6 第九轮21条声明的候选材料完整性核查

真实来源注册表里确认有4条 financial 来源（利润表、现金流量表、资产
负债表、.info估值快照），21条声明全部只链接到.info估值快照这一条。
检查这21条声明自己的数字是否也出现在另外3条来源里（怀疑候选集合
是否漏掉了 Agent 实际看过的材料）——**查到的数值重合（0.64/0.7/0.3/0.37
这几个小数）经核实是真实的巧合碰撞，不是真实跨来源引用**：这类
0-1范围的小数（如税率、PEG比值）在财务字段里本来就密集，数值相同不
代表指的是同一件事。**没有找到可靠证据证明现有候选集合遗漏了 Agent
真实看过的材料**——21条的真实问题不是"候选来源选错了"，是这些声明
自己的论断（"便宜""贵""风险""拐点"）本身不是任何单一已保存来源能
直接证实的内容,这是一个语义判断问题,不是材料遗漏问题。

## 小结：真实第一阻塞点（供阶段B使用）

**不是材料缺失，不是实现错误，是验证从未执行**：20条已经真实、来源
可定位、其中多条是分析性的声明，正等着第九轮的 LLM 核验任务去处理，
这套任务代码是真的、接线是真的（A.3已证实），但对这份 AMD 数据从未
跑过一次——无论是真实模型还是固定响应测试。阶段B要补的，就是先用
固定响应把这条路径在真实生产入口上跑通一次（照抄已经证明有效的
`test_scenario_d_...`模式，换成我们自己的核验函数），而不是去动
claim_quality 或 taxonomy。

是否继续阶段B（照此建好正向/反向真实接线测试）？
