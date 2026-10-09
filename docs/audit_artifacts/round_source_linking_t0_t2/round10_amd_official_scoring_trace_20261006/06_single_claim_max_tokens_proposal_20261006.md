# 单条声明 max_tokens 验证提案（2026-10-06）—— 本轮不执行，需新授权

## 目的

只验证一件事：在原任务、原推理配置完全不变的前提下，仅将输出上限从
4096提高到8192，是否能让第五次真实请求当时失败的那同一条claim完成
核验。不是为了恢复AMD分数、不是为了推进Alpha激活或Conflict形成。

## 为什么是这一条，不换样本

第五次真实请求是全部5次里**唯一**只含1条claim、输入token也最小
（1923 token）的一次，但依然在`output_tokens=4096,
reasoning_tokens=4096`时被截断——这是目前唯一已知"小输入也会截断"
的真实样本，换成任何其他claim都不能验证同一个问题。

## 冻结材料（发送前核对，不自行补猜）

- **claim_id（完整，逐字）**：
  `1bad76a7-72ac-4c8b-8189-2e5c0f1a6105:bear_researcher:investment_debate_state.bear_history:claim:66`
- **claim原文**：`"The stock is 37% above its 200-day average with a beta of 2.45 — maximum downside convexity."`
- **所属原始AMD run_id**：`1bad76a7-72ac-4c8b-8189-2e5c0f1a6105`
- **候选来源**：`src_5bd8a947130d1949`（Yahoo Finance，AMD fundamentals snapshot 2026-10-05 10:34:46）
  `content_hash=b57536c2e47f254acda82743e997a4e4f000917f38af29a8d15c3b665e340abd`
- **prompt任务/版本**：`LLM_TASK_NAME="content_support_verification"`，
  `LLM_METHOD_VERSION="content_support.llm.v1"`，
  当前代码的prompt身份哈希
  `prompt_sha256=91679705349a2f336b10d3de28079aebd6411cd18fe2165a81c5ee6e5721590f`
  （直接调用`Week2LLMGateway.prompt_identity_sha256("content_support_verification")`
  现场取得，非手写）
- **模型**：`deepseek-v4-flash`
- **batch_size**：1
- **客户端层重试**：0（`build_server_week2_llm_gateway`无条件写死，已在阶段B确认）
- **应用层重试**：`COMQUTOR_WEEK2_LLM_MAX_RETRIES=0`
- **新执行的全局请求上限**：1（新`execution_id`，独立于原21次预算）
- **唯一拟改变的参数**：`max_tokens: 4096 → 8192`
- **不改动**：thinking/reasoning_effort（代码里从未显式设置过，见下方
  "已知但本轮不处理的候选解释"）、输出字段要求（status/
  used_source_id/used_location/supporting_quote_or_data/rationale/
  supported_proposition/unsupported_remainder 七个字段原样保留）、
  prompt文本、模型、taxonomy、评分规则

## 明确的证据缺口（如实声明，不假装能逐字复现历史请求）

第一次真实执行没有保存请求正文本身（本轮才新增这个能力），因此：
**无法证明新请求与当时真正发出的那次请求逐字完全一致**。只能证明：
冻结的claim文本/候选来源内容哈希/任务版本号/可核实的客户端配置
（模型、retries、batch_size）与当时一致——这是"配置一致性"，不是
"历史请求逐字复现"，报告中不得混为一谈。

## 实际执行命令（本轮不运行）

复用已修复、已通过零成本测试验证的真实脚本本身（新增的
`--max-calls`/`--max-tokens`/`--target-claim-id`参数就是为这个场景
加的，不是另写一个平行脚本）：

```bash
python docs/audit_artifacts/round_source_linking_t0_t2/round10_amd_official_scoring_trace_20261006/03_phase_c_execution_script.py \
  --execute \
  --max-calls 1 \
  --max-tokens 8192 \
  --target-claim-id "1bad76a7-72ac-4c8b-8189-2e5c0f1a6105:bear_researcher:investment_debate_state.bear_history:claim:66"
```

结果保存到新的 `executions/<execution_id>.json`，绝不覆盖
`04_phase_c_real_results.json`（已修复的历史保护机制，见主报告）。
这一次执行现在会**自动**启用请求/响应双向审计（
`enable_request_response_audit`默认`True`），因此这次（无论成败）都会
留下真实、逐字的请求/响应落盘记录，不会再出现"历史请求正文未保存"
的缺口。

## 预先固定的判定规则（写入此提案，执行时必须照办）

1. 无论成功、截断、超时、认证错误还是解析失败，这次最多发送**一次**
   真实请求，随后停止——不因为失败就自动重试，也不因为成功就顺带
   发起别的请求。
2. 若返回了完整JSON且通过协议校验：这**只**证明这一条claim在
   `max_tokens=8192`下完成了核验，**不能**据此推断其余20条也会成功，
   也**不能**仅凭协议有效就宣布语义判断正确——必须再跑现有的真实性
   校验（来源是否在候选集合内、引用内容是否真实存在于来源原文），
   通过后才能视为"核验通过"；仍然不能据此把`content_support_status`
   自动置为最终`eligible=True`，不得回填`HUMAN_REVIEWED`。
3. 若仍然截断：保存结果，停止，不自动提高到更大上限、不换模型、不
   关闭thinking、不改prompt重试。
4. 若返回`SUPPORTS`等有效判断：保留依据（used_source_id/
   supporting_quote_or_data/rationale），按既有真实性校验机制核实；
   不直接写`eligible=True`，不填`HUMAN_REVIEWED`。
5. 不自动启动剩余20条的核验，也不自动触发AMD整轮重算。

## 已知但本轮不处理的候选解释（供下一轮参考，不在本提案范围内）

查阅DeepSeek官方API文档（api-docs.deepseek.com/api/create-chat-completion，
本轮现场核实）确认：`thinking.reasoning_effort`的**文档默认值是
"high"**。直接读代码确认：`build_server_week2_llm_gateway`→
`create_llm_client`整条路径**从未**在`client_kwargs`里设置过
`reasoning_effort`或`thinking`（`tradingagents/llm_clients/
openai_client.py`的`_supports_reasoning_effort`只匹配原生OpenAI的
`gpt-5`/`o[1-9]`系列模型名，DeepSeek永远不满足，这一点可直接读代码
确认，不依赖对历史请求正文的回放）。这意味着这5次真实请求在构造上
就不可能显式设置过`reasoning_effort`，服务端极可能采用了文档默认的
"high"推理强度——这是**目前最有代码和文档依据支持的候选解释**，但
不是通过保存下来的历史请求正文直接观测到的，因此只作为候选记录，
不作为本提案要验证或本轮要确认的根因。若本次`max_tokens=8192`提案
仍然截断，`reasoning_effort`很可能是下一步更值得单独验证的变量——
但那将是一次新的、范围不同的提案，需要单独授权，本提案不包含。

## 授权声明

这是一次需要新授权的真实付费请求，不是对原21次额度中剩余16次的
自动延续或默认沿用。原21次额度中已发送的5次失败请求，**不会**被
这次新的1次请求当作"重试"计入或替代。
