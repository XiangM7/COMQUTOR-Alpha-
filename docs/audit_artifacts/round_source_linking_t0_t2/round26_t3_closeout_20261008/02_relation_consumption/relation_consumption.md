# 005／006 的关系消费：契约核对与结论

数据：
- 逐条链路：`relation_chain.json`，由 `tools/trace_relation_consumption.py` 生成，输入是修复后离线重放中 L4 实际读取的匹配记录。
- 契约断言：`tests/test_t3_closeout_relation_and_opposition_consumption.py`。

**本节没有修改任何生产代码。**

## 1. 各字段的职责和权威来源（现行契约）

| 字段 | 谁写入 | 谁读取 | 权威依据 |
|---|---|---|---|
| Alpha 原始选择 `llm_selected_alpha_id` | Alpha 分类器（LLM，v7） | Mapper 的生产门（A001 失效门、正向要求门）→ `matched_alpha` | 2026-08-21 负责人决定，LLM 是 Alpha 语义的唯一权威（见规则来源图） |
| `relation`（activation／conditional／mixed／mention／invalidation／risk_relief） | Mapper 的文字规则 `claim_semantics.alpha_relation` | 证据筛选器 `select_supporting_alpha_claims` 第 4 道门；Activation 的关系权重 `RELATION_WEIGHTS` | 权威矩阵 factor extraction 行："Factor/relation vocabulary remains deterministic authority" |
| `assertion_status`（asserted／negated／…） | Mapper 的文字规则 | 筛选器第 5 道门；Activation 中 negated 权重为 0 | 同上；Activation v2 规范（2026-07-23）："negated weight 0" |
| `evidence_stance`（LLM 方向） | `evidence_stance_llm` | 冲突准入 `conflict_admissibility`（依据 John 2026-08-05 的 B2 指示）和冲突展示；**筛选器和 Activation 都不读** | **PD-006：`NOT_APPROVED`**，原文"Evidence Stance remains deterministic shadow and cannot affect Activation or Conflict"；权威矩阵："No production authority"、"CURRENT effect is SHADOW_ONLY" |
| 来源资格 | `compute_verified_support_eligibility`，依据内容核验状态和来源链接 | 激活证据池（与筛选器同时满足才入池） | T1 验证门 |

**结论：筛选器读 Mapper 的文字规则 relation，不读 LLM 方向，这符合现行契约（PD-006），不是接线错误。**
- 本轮不能把 LLM 方向升级为激活权威，所以没有改代码。
- 已有的冲突：冲突准入实际读取了 stance（John 的 B2 指示），而 PD-006 写的是 stance 不能影响 Conflict。这是登记册与代码之间的旧冲突，本轮没有改变。

## 2. 005 和 006 沿生产路径

| 环节 | t3v3-005 | t3v3-006 |
|---|---|---|
| Alpha 原始选择 → 生产门后 | A304 → A304，没有被门否决 | A304 → A304 |
| Mapper relation（筛选器读取） | `mention`（文字规则把 "does not immunize" 判为否定） | `mention`（"not a forward EPS of $15.72" 判为否定） |
| `assertion_status` | `negated` | `negated` |
| 确定性匹配分数（Activation 权重） | 0.0（LLM 选中但词汇分为 0） | 0.0 |
| LLM 方向 | supports_alpha | supports_alpha |
| 来源资格 | 修复前 NOT_REVIEWED（L1 被拒）；修复后 SUPPORT_STATUS_NOT_RESOLVED（模型自己判 CONDITIONAL） | ELIGIBLE |
| 筛选器 | 第 4 道门排除：RELATION_NOT_SUPPORTING | 第 4 道门排除：RELATION_NOT_SUPPORTING |
| 如果 relation 门放行，**仍会被以下门排除** | 第 5 道门 `assertion negated`；来源资格不满足（CONDITIONAL 不算直接支持）；分数 0.0，入池也不加权重 | 第 5 道门 `assertion negated`；分数 0.0，入池也不加权重 |
| 复核人 | A304 支持，单条语义资格成立 | A304 支持，单条语义资格成立 |

只改 relation 这一个字段，这两条仍然进不了激活池。要让它们入池，需要同时决定以下三项，不能只改其中一项：

- LLM 方向能否覆盖文字规则的 relation；
- LLM 方向能否覆盖文字规则的 negated；
- LLM 选中的匹配如何赋予权重（目前权重来自词汇分，见第 19 轮记录）。

## 3. 反向、背景和引用的处理

| 情形 | 样本 | 现行行为 | 结论 |
|---|---|---|---|
| 文字规则判为 invalidation（失效） | t3v3-003（对 A001） | 筛选器排除 | 正常排除 |
| 文字规则判为 risk_relief（风险缓解） | t3v3-039（对 A501） | 筛选器排除 | 正常排除，反向证据没有变成正向支持 |
| **LLM 判为 opposes_alpha，但文字规则判 activation** | t3v3-037、t3v3-040（对 A501，复核人同样判为反对） | **筛选器全部 5 道门都通过**；只因来源链接无效（SOURCE_LINK_NOT_VALID）才没有入池 | **发现未修，产品口径待决定**：如果来源链接有效，反向证据会作为正向支持进入 A501 激活池 |
| **LLM 判为 neutral_background，但文字规则判 activation** | t3v3-038 | 同上 | 同上 |
| 内容核验为 BACKGROUND、CITATION_ONLY、CONDITIONAL、OPPOSES 或 INSUFFICIENT | 用真实 006 请求加构造回复测试 | 来源资格一律不合格 | 已验证：背景、引用、条件和反驳不会成为已验证支持 |
| LLM 判 supports_alpha，但文字规则判 mention 或 negated | 005、006 | 排除 | 已验证：supports 不会跳过 relation、assertion 和来源门 |

**这里没有声称"反向证据一定不会成为正向支持"。** 第 3 行和第 4 行说明，目前唯一的保护是文字规则：
- 文字规则漏判了 "low & falling" 和 "odds are 8% and falling" 这类低衰退概率表述；
- 修复它要么提升 LLM 方向的权威（PD-006 未批准），要么改确定性语义词表（同样未批准）；
- 两种都不在本轮权限内。

## 4. 需要负责人决定的消费规则（具体选项）

| 编号 | 规则 | 影响本次样本 | 需要改变的契约 |
|---|---|---|---|
| R-1 | LLM 方向对（claim，匹配的 Alpha）为 opposes_alpha、neutral_background 或 mentions_alpha 时，该 claim 不进入这个 Alpha 的正向激活池（只减不加，其他门不变） | 037、038、040 将来即使链接有效也不会入池；005、006 不受影响 | PD-006（stance 开始影响 Activation，即使只做排除）；Addendum A |
| R-2 | LLM 方向为 supports_alpha 时，可以覆盖文字规则的 mention 或 negated；来源、质量、角色等门不变 | 005、006 将通过第 4、5 道门；005 仍被来源资格拦下 | PD-006；Activation v2 中 negated 权重为 0 的规定 |
| R-3 | 保持文字规则为唯一权威，但扩充风险缓解的确定性词表（覆盖 "low & falling"、"odds … falling" 等） | 037、040 将被判为 risk_relief 后排除 | 语义词表变更（负向和条件类别已批准，具体词表未批准，见规则来源图） |
| R-4 | 维持现状 | 无 | 无，但第 3 节的风险仍然存在 |

## 5. A001 门（只核对并记录）

| 样本 | 原始选择 | 门 | 原因（原样） | 最终结果 | 复核人 |
|---|---|---|---|---|---|
| t3v3-019 | A001 | `alpha_specific_invalidation_override=True` | "alpha-specific invalidation evidence explicitly contradicts this Alpha's own core thesis; overriding semantic classifier selection to no_match" | SELECTED_BUT_NOT_MATCHED | A001，反对 |
| t3v3-027R | A001 | 同上 | 同上 | SELECTED_BUT_NOT_MATCHED | A001，仅提及 |
| t3v3-028 | A001 | 同上 | 同上 | SELECTED_BUT_NOT_MATCHED | A001，反对 |

**T3 计分侧**：原始选择、门否决和原因都逐条保留。正式计分把门否决单独列一列（SELECTED_BUT_NOT_MATCHED），没有算作 NONE；补充视角另外报告了门前的原始选择。

**生产侧（发现未修）**：`alpha_mapper.compute_alpha_classification_completion` 把"LLM 选中、没有失败原因、`matched_alpha` 为空"的匹配记为 `valid_none_count`。上面 3 条在这个读时指标里都会被算成"模型有效 NONE"。
- 这个指标只在 API 读取时计算（`routes_research.py`），不写入各 run 的 `outputs/runs/<run_id>/summary.json`。
- 按本轮"只核对并记录"的要求，没有修改。
- 最小修复方向：新增 `gate_overridden_selection_count`，并把这类匹配从 `valid_none_count` 中剔除。这会改变 API 响应，需要同步修改前端类型。
