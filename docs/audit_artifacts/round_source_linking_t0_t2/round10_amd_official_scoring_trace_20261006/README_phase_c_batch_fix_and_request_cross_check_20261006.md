# 阶段C修复与5次真实请求逐次核对（2026-10-06，本轮零新增Provider调用）

本轮严格按要求：只修配置传导及补充测试，不改prompt/模型/样本/评分规则；
**本轮未发送任何新的真实Provider请求**（全部验证基于固定/假响应，在
Provider边界处打桩，真实重试循环/预算计数器/客户端参数均为真实生产代码）。

> **2026-10-06 同日更正**：下文第三、四、五节有两处表述需要更正，更正
> 原因见本目录
> `README_phase_c_request_response_audit_and_single_claim_proposal_20261006.md`：
> (a) 第五节"不要用剩余16次额度跑剩下16条claim"一句把"预算剩余16次"
> 和"21条claim里有16条尚未发送"混为一谈——**事实并非如此：21条
> claim在第一次真实执行时已经全部随5次批量请求发送过，全部截断，
> 没有任何一条是"尚未发送"的**，剩余16次只是21次全局调用预算里还
> 没被消耗的调用额度，不是未发送的claim数。(b) "真实、更深层的原因
> 很可能与本任务自身的输出结构复杂度有关"一句把候选解释写得过于
> 确定；本轮已查到一个证据更充分、来源更明确的候选解释（DeepSeek
> 官方文档确认`reasoning_effort`默认值为`"high"`，且代码确认这条
> 调用链从未显式设置过这个参数），但这仍然只是**候选解释**，不是
> 已确认根因，两处原文保留在下方作为历史记录，更正说明以本提示为准。

---

## 一、脚本修复（diff）

### 1. `comqutor_alpha/structure_engine/content_support_llm.py`

真实根因（已用零成本测试单独隔离确认，见下文回归日志）：
`chunk_items(items, size: int = BATCH_SIZE)` 的默认值在**函数定义时**
绑定一次；脚本事后重新赋值 `csl_module.BATCH_SIZE = 1` 这个模块属性，
对已经绑定好的默认值**没有任何效果**——这是 Python 语言层面的行为，
不是本模块特有的bug。

修复：给 `apply_llm_content_support_verification` 新增一个真实的函数
参数（不是模块全局变量）：

```python
def apply_llm_content_support_verification(
    records: Sequence[Mapping[str, Any]],
    sources: list[dict[str, Any]] | None,
    *,
    llm_gateway: Any = None,
    batch_size: int | None = None,   # 新增
) -> tuple[list[dict[str, Any]], ContentSupportRunStats]:
    ...
    effective_batch_size = batch_size if batch_size is not None else BATCH_SIZE
    for batch in chunk_items(items, size=effective_batch_size):   # 显式传size=
        _process_batch(batch, llm_gateway, stats, results_by_claim_id)
```

此文件此前从未提交（`git status` 显示为 `??` 未跟踪文件），因此没有
可比对的历史版本，上面展示的是修复后的真实当前内容，而非git diff。

### 2. `03_phase_c_execution_script.py`（真实阶段C执行脚本本体）

```diff
-    from comqutor_alpha.structure_engine.content_support_llm import (
-        apply_llm_content_support_verification,
-        chunk_items,
-    )
-
-    # Force batch_size=1 for this run only ...
-    import comqutor_alpha.structure_engine.content_support_llm as csl_module
-    original_batch_size = csl_module.BATCH_SIZE
-    csl_module.BATCH_SIZE = 1
-    try:
-        updated_records, stats = apply_llm_content_support_verification(
-            snapshot["records"], snapshot["sources"], llm_gateway=gateway
-        )
-    finally:
-        csl_module.BATCH_SIZE = original_batch_size
+    from comqutor_alpha.structure_engine.content_support_llm import (
+        apply_llm_content_support_verification,
+    )
+
+    updated_records, stats = apply_llm_content_support_verification(
+        snapshot["records"], snapshot["sources"], llm_gateway=gateway, batch_size=1
+    )
```

此文件同样未提交（`??` 未跟踪）。修复后已用**零成本dry-run**（不带
`--execute`）实际跑过一遍真实脚本，确认：

```
PREFLIGHT: re-annotation artifact + original metadata hashes match exactly.
PREFLIGHT: all 21 claims are source_link_status=VALID ...
LIVE CHECK: real gateway constructed -- provider=deepseek, model=deepseek-v4-flash, max_retries=0, max_calls=21, DEEPSEEK_API_KEY present=True
DRY RUN (zero cost): build_content_support_request_items would submit 21/21 claims.
BLOCKED: pass --execute to actually make Provider calls. All preflight checks passed; zero Provider calls made.
```

真实脚本改动后仍能正常导入、解析、通过全部preflight，且在没有
`--execute`时真实拒绝发送——零Provider调用。

---

## 二、零调用回归日志（固定/假响应，Provider边界打桩）

新增测试文件：`tests/test_content_support_llm_phase_c_batch_size_fix.py`
（6个测试，全部使用**真实** `Week2LLMGateway` 类包一个假的底层model
对象——真实重试循环、真实 `_reserve_call()` 预算计数器都被真实执行，
只有最底层 `.invoke()` 从不发出真实HTTP请求）：

| 测试 | 验证点 |
|---|---|
| `test_batch_size_one_produces_21_single_claim_requests_not_5` | 21条真实AMD claim + `batch_size=1` → 真实21次独立调用，每次请求体恰好1条claim |
| `test_chunk_items_own_default_is_bound_at_definition_time_not_read_live` | 直接在`chunk_items`上隔离复现真实根因，复现出与真实付费执行完全相同的 `[5,5,5,5,1]` 批次形状 |
| `test_candidate_scope_stays_within_the_single_claim_when_batch_size_one` | 每条单claim请求的候选来源只包含该claim自己的source，无串位 |
| `test_global_budget_cap_stops_sending_once_exhausted_real_gateway` | 真实`max_calls=5`时，21条里只有5条真实调用`.invoke()`，其余16条走`FALLBACK_BUDGET_EXHAUSTED`，从未到达Provider边界 |
| `test_max_retries_zero_means_exactly_one_real_attempt_per_claim` | 真实`max_retries=0`，验证失败的模型仍只被调用1次，无重试 |
| `test_every_real_attempt_is_saved_independently_in_the_attempt_log` | 21次尝试全部独立写入`attempt_log`，逐条含`request_control`/`provider_response_metadata` |

实际运行（使用项目`.venv`，解决了此前`ModuleNotFoundError: networkx`
的环境问题）：

```
$ .venv/bin/python -m pytest tests/test_content_support_llm.py \
    tests/test_content_support_llm_production_wiring.py \
    tests/test_content_support_llm_phase_c_batch_size_fix.py -v

...
33 passed in 5.99s
```

17个既有测试（`test_content_support_llm.py` 11个 + 生产接线
`test_content_support_llm_production_wiring.py` 10个，实为9个新增1个
在本次之前已存在）与新增6个，**零回归**。全程零真实Provider调用。

---

## 三、5次已发送真实请求逐次核对（直接重新读取`04_phase_c_real_results.json`，非离线复现）

| # | claim数 | claim_id（含agent/字段/序号） | input tokens | output tokens | reasoning_tokens | finish_reason |
|---|---|---|---|---|---|---|
| 1 | 5 | aggressive_risk_analyst:17, bear_researcher:54, conservative_risk_analyst:24, neutral_risk_analyst:16, research_manager:8 | 6617 | 4096 | 4096 | length |
| 2 | 5 | fundamental_agent:28, conservative_risk_analyst:31, aggressive_risk_analyst:42, conservative_risk_analyst:48, fundamental_agent:29 | 6639 | 4096 | 4096 | length |
| 3 | 5 | bear_researcher:53, portfolio_manager:8, neutral_risk_analyst:9, bull_researcher:61, research_manager:7 | 6596 | 4096 | 4096 | length |
| 4 | 5 | portfolio_manager:12, portfolio_manager:38, bull_researcher:13, fundamental_agent:119, fundamental_agent:107 | 6525 | 4096 | 4096 | length |
| **5** | **1** | **bear_researcher:66** | **1923** | **4096** | **4096** | **length** |

（`completion_tokens_details.reasoning_tokens` 字段直接取自
`provider_response_metadata.raw_usage`，刚重新读取原文件确认，非推算。）

5条真实请求的claim数之和 = 5+5+5+5+1 = 21，与`requested_count=21`、
`real_provider_attempts=5`一致，没有claim被跳过或重复发送。

**明确撤回此前归因**：第5次请求只有**1条**claim、输入仅1923
token（远小于前4次的约6600 token），但同样在`output_tokens=4096,
reasoning_tokens=4096`时被截断，JSON输出为零。这说明**此前"仅因
5条批量导致截断"的确定性归因是错误的，现予撤回**。真实情况是：
即使单条claim、远更小的输入，模型的推理过程本身仍然在4096 token
预算内吃满，没有剩余空间输出结构化JSON结果。真实、更深层的原因很
可能与本任务自身的输出结构复杂度有关（status/used_source_id/
used_location/supporting_quote_or_data/rationale/
supported_proposition/unsupported_remainder 七个字段，比第三轮单
字段Alpha-ID分类任务重得多），而不是单纯的批量大小问题。

**证据缺口（明确披露，不用离线复现冒充历史记录）**：`attempt_log`
里为每次真实请求保存的是**响应侧**信息（`token_usage`/
`request_control`/`provider_response_metadata`），**真实发送的请求正文
（完整prompt/items payload）当时没有被保存**。本报告第三节表格中的
claim_id列表来自`attempt_log.claim_ids`（这是真实保存下来的，可信），
但请求正文本身的完整内容无法逐字回放核对——这是一个真实、现存的记录
缺口，不是本轮能补救的（时间回溯不可行），仅如实披露。

---

## 四、剩余风险（供下一次执行前参考，本轮不据此发起新调用）

1. **最关键风险：batch_size修复是必要但未必充分的条件。** 第5次真实
   请求已经证明，单条claim、1923 token输入时依然在4096 token内被推理
   耗尽。如果本任务本身的推理需求结构性地超过4096 token，那么即使本轮
   修复使下一次真正做到"21次请求、每次1条"，仍然可能**全部21次继续
   截断**，不能把"批量改对"误当作"问题已解决"的证据。
2. 尚未验证提高`max_tokens`（例如到8192或更高）是否能解决——这需要
   新的真实调用才能验证，且会改变本轮被明确禁止修改的参数（本轮未做，
   仅记录为待确认风险）。
3. 尚未排查是否可以通过精简prompt本身的输出字段要求（如去掉
   `rationale`等非结构性字段）降低推理负担——这类改动属于"改prompt"，
   按本轮授权范围不能做,只记录为后续可能方向。
4. 真实请求正文未保存的缺口（见第三节）意味着无法对"为什么推理吃满
   4096"做逐字复盘，只能从响应侧usage数据反推,下一次执行前如可能，
   应考虑同时保存请求正文本身，以便真正定位。
5. 本轮未运行独立重算（avoiding使用失败状态冒充证据），AMD评分、
   Alpha激活、Conflict形成**均未发生**，不在本报告中做任何相关宣称。

---

## 五、下一步新执行方案（提案，未经新授权不执行，不使用剩余16次额度重试已发送的5条）

鉴于上述风险2未验证前贸然重跑大概率重复截断、浪费预算，建议**不要
直接用剩余16次额度去跑剩下16条claim**，而是先用**1次**真实调用（从
预算中新增,不是复用已发送的5条）在例如`max_tokens=8192`下重试其中
一条已知结构最简单的claim（如第5次那条单claim请求本身），验证"提高
输出上限"这一个变量是否能解决截断。这改变了`max_tokens`参数，按本轮
授权必须先取得你的新授权才能执行，本轮本身**不会**发起。

---

本轮确认：零新增Provider请求；无AMD分数恢复/Alpha激活/Conflict形成
宣称；未重跑独立重算；未使用剩余16次额度重试任何已发送声明。
