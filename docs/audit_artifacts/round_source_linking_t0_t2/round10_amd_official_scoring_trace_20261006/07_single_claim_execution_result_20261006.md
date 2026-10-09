# 单claim max_tokens=8192验证：真实执行结果（2026-10-06）

**本次执行**：1次真实、已付费的Provider调用，`execution_id=
phase-c-20261005T233842Z-1b2550ac`，结果保存于
`executions/phase-c-20261005T233842Z-1b2550ac.json`（新目录，
`04_phase_c_real_results.json`等全部历史文件执行前后哈希核对一致，
未被覆盖）。目标claim、候选来源、prompt版本、模型、batch_size=1、
两层重试=0、全局上限=1 均与
`06_single_claim_max_tokens_proposal_20261006.md`冻结材料逐项核对
一致（claim_id、claim原文、候选`src_5bd8a947130d1949`及其
`content_hash`，执行前已用零成本检查逐一确认）。发送前确认
`AuditingTransport`已挂载（`gateway._audit_enabled=True`）、真实
序列化请求体字段确为`max_tokens=8192`（非`max_completion_tokens`）、
请求只含这一条claim——全部满足后才发送，全程只发了这1次。

---

## 一、模型是否产生完整且协议有效的回答？—— 是

- `finish_reason="stop"`（不是`"length"`，**未截断**）。
- `completion_tokens=7300`（其中`reasoning_tokens=7036`），在
  `max_tokens=8192`预算内完整结束，没有触顶。
- 响应内容是合法JSON，包含全部7个必需字段，`claim_id`与请求完全一致,
  `status="SUPPORTS"`是合法词表值，`used_source_id`命中了请求里唯一
  允许的候选来源——`Week2LLMGateway`层面`provider_status="success"`,
  `validation_accepted=true`（批次结构校验通过）。
- 真实请求/响应正文已通过本轮新增的`AuditingTransport`逐字落盘
  （`outputs/runs/phase-c-amd-21-claim-verification/error_logs/
  week2_llm_provider_request_audit.jsonl`/
  `..._response_audit.jsonl`），本结论直接来自重新读取这份真实落盘
  记录，不是复述`attempt_log`摘要。

模型的真实回答原文：

```json
{
  "claim_id": "1bad76a7-72ac-4c8b-8189-2e5c0f1a6105:bear_researcher:investment_debate_state.bear_history:claim:66",
  "status": "SUPPORTS",
  "used_source_id": "src_5bd8a947130d1949",
  "used_location": "data_snapshot.beta; data_snapshot.fifty_day_average; data_snapshot.two_hundred_day_average",
  "supporting_quote_or_data": "beta: 2.454; fifty_day_average: 513.5342; two_hundred_day_average: 374.7236",
  "rationale": "The candidate reports beta 2.454 (rounds to 2.45) and contains 50-day and 200-day averages whose relationship is mechanically confirmed as 0.37. It does not state the current stock price or any downside-convexity assessment.",
  "supported_proposition": "AMD's beta is 2.45, and the 50-day average is about 37% above the 200-day average.",
  "unsupported_remainder": "The stock itself is 37% above its 200-day average and this is maximum downside convexity."
}
```

---

## 二、回答是否具有可核对的材料依据？—— 实质上有，但自动校验按现行规则判定未通过

**重新直接核对**（不是信任模型自称）：调用项目真实的
`_data_field_found`函数，逐一核对模型引用的三个数字——`beta=2.454`、
`fifty_day_average=513.5342`、`two_hundred_day_average=374.7236`——
在真实`source_registry.json`的`data_snapshot`里**全部真实存在，
数值完全吻合**。模型的`rationale`在实质内容上是准确的，而且比原始
claim更精确：它指出原始claim把"50日均线相对200日均线高37%"和
"股价本身相对200日均线高37%"混为一谈，并明确标出"maximum downside
convexity"是原始claim里源数据不支持的主观判断——这是一次真实、
有实质根据、而且比原claim更严谨的核验。

**但自动化的`content_support_llm_fallback_reason`判定为
`"quote_or_data_not_found"`，已用真实代码重放精确复现**：

- `_quote_found_in_excerpt`要求`supporting_quote_or_data`整串作为
  一个子字符串出现在来源原始excerpt文本里——模型给的是整合后的
  "beta: 2.454; fifty_day_average: 513.5342; two_hundred_day_average:
  374.7236"，excerpt原文是"...Beta=2.454...50 Day Average=
  513.5342...200 Day Average=374.7236..."，格式（冒号vs等号、字段名
  拼写）不同，整串匹配失败。
- `_data_field_found`把`supporting_quote_or_data`整串当成**一个**
  待查值，去`data_snapshot`的每个叶子节点里找相等或包含关系——
  `data_snapshot`里每个叶子是**单个**数字（如`beta=2.454`），模型把
  三个数字拼成一句话一起提交，整句话不会等于或包含在任何单个叶子
  的字符串化结果里，因此也失败。真实重放证实：**把这三个数字单独
  拆开逐一核对，每一个都能在`data_snapshot`里精确命中**（已用真实
  代码在三次独立调用里分别验证为`True`）。

即：**这不是幻觉/编造，是当前自动校验函数只支持"单条引用对单个
数值"的匹配粒度，不支持模型把多个支撑数字合并成一句话引用**——
一个真实、具体、已confirmed的现行规则限制，不是本次新发现的bug,
也不是本轮授权修复的范围（本轮未改任何prompt/校验规则）。

---

## 三、该条是否具备正式证据资格，以及阻塞原因？—— 不具备，阻塞原因已精确定位

- `content_support_status`保持原值`"PENDING_REVIEW"`，**未被回填为
  任何形式的"已通过"**；未写入`eligible=True`；未填写
  `HUMAN_REVIEWED`；记录里新增的唯一字段是
  `content_support_llm_fallback_reason="quote_or_data_not_found"`，
  如实记录了自动核验的真实拒绝原因，不是把失败悄悄转成`NONE`或
  `SUPPORTS`。
- **阻塞原因**：不是材料真实性问题（材料真实、已核对），不是模型
  推理质量问题（推理结果比原claim更精确），而是现行
  `_quote_found_in_excerpt`/`_data_field_found`两个真实校验函数的
  匹配粒度——只认"单一值完整匹配"，不认"模型把多个真实数字合并成
  一句话引用"这种真实但格式不同的引用方式。这条claim目前因此停留
  在`PENDING_REVIEW`，不能被判定为正式、可计入评分的证据。

---

## 四、本轮未做、不宣称的事项（按授权原样执行）

- 未运行剩余20条的核验，未对AMD做任何重算。
- 未因为这次"未截断"的结果就自动提高上限或改配置去跑其他claim。
- 不宣称Alpha激活、Conflict形成或T1验收通过——这1条claim目前仍是
  `PENDING_REVIEW`，没有任何claim因本次执行变为正式证据。
- 估算费用：`input_tokens=1923, output_tokens=7300` ×
  DeepSeek非高峰公开定价（输入0.15、输出0.60美元/百万token）
  ≈ **0.0047美元（估算值，未经真实账单核对，不称为"实际扣款"）**。
- 执行前后，`04_phase_c_real_results.json`及原AMD run全部相关文件的
  哈希已重新核对，**全部未变**。

## 五、对上一轮"风险1"的部分回应（如实报告，不夸大结论）

上一轮报告的最大风险是"batch_size修复是必要但未必充分条件，单条
claim在4096下也可能继续截断"。这次真实执行证明：**同一条claim在
`max_tokens=8192`下确实不再截断**，完整产出了结构化回答
（`completion_tokens=7300`，远超4096但在8192预算内完成）。这只
证明了"这一条claim、这一次调用"在这个配置下走完了全流程——**不能
据此推断其余20条也会在8192下全部成功**，更不能把"模型给出了SUPPORTS
判断"直接等同于"这条claim现在是正式证据"（见第三节，实际仍被真实
校验规则挡在`PENDING_REVIEW`）。
