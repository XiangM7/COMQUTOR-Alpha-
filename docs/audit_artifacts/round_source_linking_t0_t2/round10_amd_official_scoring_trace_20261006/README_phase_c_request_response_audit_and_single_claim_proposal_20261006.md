# 阶段C收尾检查 + 单请求验证提案（2026-10-06，本轮零新增Provider调用）

本轮严格遵守边界：只做零外部调用的代码修复、测试、材料核对和方案
准备。**本轮未发送任何新的真实Provider请求**，未使用原21次额度中
剩余的16次重试任何已发送声明，未运行Fresh Run，未改prompt/模型/
核验标准/评分阈值/taxonomy/参考标签，未增加生产人工审核前提，
未commit/push，未处理Demo。

---

## 一、固定本次失败执行的事实（更正前一份报告的两处表述）

- **21条声明已经全部随请求发送过**——不存在"尚未发送的claim"。
- 实际分组为 `[5, 5, 5, 5, 1]`，共**5次**真实请求，客户端层与应用层
  重试均为**0次**（查`request_attempts`/`attempt_log`逐条确认，每条
  claim只出现在一次真实尝试里，没有重试记录）。
- **5次全部截断**（`finish_reason=length`），没有任何一条产出有效
  JSON、没有任何有效内容核验结果。
- 原21次请求上限、本次用掉5次，剩余16次——**这16次是尚未消耗的调用
  预算，不是21条claim里还有16条没发送**；21条claim在这5次请求里已
  经全部覆盖（5+5+5+5+1=21，无遗漏、无重复）。
- **本次执行偏离了已授权的"逐条请求"方式**：原授权要求每次请求恰好
  1条claim，实际因`chunk_items`默认值绑定的语言层面bug，前4次请求
  各含5条，只有第5次是1条——这是对已授权执行方式的真实偏离，已记录、
  已修复（见下文第二节），不掩盖。
- 第五次请求只有**1条**声明（claim_id见下）、输入仅1923 token，依然
  在`output_tokens=4096, reasoning_tokens=4096`时截断——**因此不能把
  失败全部归因于批量大小**，此前"仅因5条批量导致截断"的确定性归因
  已撤回。
- "本任务七个输出字段导致推理耗尽"目前仍只是一个**候选解释**，不是
  已确认根因；本轮查到一个来源更明确的候选解释（见第四节），但同样
  只是候选，不是确认。
- 此前对话中提到的费用数字（约0.0165美元）是**根据`raw_usage`里的真实
  token数 × DeepSeek公开定价表估算得出的，没有对照真实账单/发票核对
  过，不能称为"实际扣款"或"真实已扣费用"**——这是估算值，本报告和
  后续报告中一律以"估算费用"措辞，不再使用"实际花费"类表述。
- 历史请求正文（完整prompt/items payload）在第一次真实执行时**没有
  被保存**——这是真实、现存的证据缺口，本轮新增的审计机制（见第二、
  三节）只对**未来**的真实请求生效，不能、也不会用来冒充或"重建"
  当时已经发生、未被保存的历史请求正文。

---

## 二、必要修改（diff）+ 零调用回归日志

### 2.1 新增模块：`comqutor_alpha/structure_engine/week2_llm_request_audit.py`

新文件，核心类`AuditingTransport(httpx.BaseTransport)`：包一层httpx
transport（生产环境包真实网络transport，测试包`httpx.MockTransport`），
在`handle_request`里：

```python
def handle_request(self, request: httpx.Request) -> httpx.Response:
    request.read()
    try:
        self._save_request(request)          # 发送前落盘；失败则直接抛出
    except Exception as exc:
        if isinstance(exc, AuditingTransportError):
            raise
        raise AuditingTransportError(f"request audit save failed: {exc}") from exc

    response = self._wrapped.handle_request(request)   # 只有落盘成功才会走到这一行
    response.read()
    try:
        self._save_response(request, response)
    except Exception:
        self._on_response_save_failed()      # 不撤销已收到的响应，但标记"后续禁止再发"
    return response
```

关键点：落盘发生在**转发给真实/mock transport之前**——落盘失败时
`self._wrapped.handle_request`那一行永远不会执行，请求真的没有发出去，
不是"假装没发"。

### 2.2 `comqutor_alpha/structure_engine/week2_llm.py`（新增，均为opt-in，默认关闭，对现有生产调用零影响）

- `Week2LLMGateway.__init__`新增`execution_id`/
  `enable_request_response_audit`（默认`False`）两个参数；新增
  `_persist_request_audit`/`_persist_response_audit`/
  `_set_pending_audit_attempt`/`_allocate_attempt_id`等方法。
- `invoke_json_with_trace`的真实重试循环里新增：每次真实尝试前检查
  `audit_write_failed`（若为真，直接拒绝发送，不消耗`_reserve_call()`
  预算）；真实`.invoke()`调用前后设置/清除"当前待审计尝试"上下文；
  新增`_find_auditing_transport_error`——沿异常的`__cause__`/
  `__context__`链查找审计失败信号（因为OpenAI SDK可能把transport抛出
  的异常包装成它自己的异常类型，不能只做`isinstance`判断）。
- `build_server_week2_llm_gateway`新增`execution_id`/
  `enable_request_response_audit`/`_base_transport_for_testing`三个
  参数；`enable_request_response_audit=True`时用`AuditingTransport`
  包一层httpx.Client，通过`client_kwargs["http_client"]`真正传给
  `create_llm_client`。
- `comqutor_alpha/storage/file_store.py`的`ALLOWED_ARTIFACT_PATHS`新增
  两条：`error_logs/week2_llm_provider_request_audit.jsonl`、
  `error_logs/week2_llm_provider_response_audit.jsonl`。
- `comqutor_alpha/structure_engine/content_support_llm.py`新增
  `FALLBACK_AUDIT_WRITE_FAILED = "audit_write_failed"`，与现有
  `FALLBACK_BUDGET_EXHAUSTED`等并列，不与`FALLBACK_PROVIDER_ERROR`
  混在一起——审计写入失败和Provider自己返回错误是两类不同的、需要
  分别识别的失败原因。

### 2.3 `03_phase_c_execution_script.py`（真实脚本本体）

- 修复历史覆盖风险：**原脚本每次`--execute`都会把结果写到同一个
  固定文件`04_phase_c_real_results.json`**——如果真的按原脚本再跑一次
  （哪怕只是验证单条claim），会直接覆盖第一次真实执行的历史记录。
  已修复：新结果一律写入`executions/<execution_id>.json`
  （`execution_id`自动生成、带时间戳和随机后缀），`
  04_phase_c_real_results.json`成为永久冻结、只读的历史记录，脚本
  今后不会再写它。
- 新增`--max-calls`/`--max-tokens`/`--target-claim-id`/
  `--execution-id` CLI参数，支持对指定的单条或多条claim、指定的
  调用上限和输出上限单独执行——这正是第五节单请求提案需要的能力，
  不需要另写一个平行脚本。
- `verify_live_client_config`现在默认`enable_request_response_audit=True`
  ——意味着**从这次修复之后的任何真实执行**，都会自动留下逐字的
  请求/响应落盘记录，不会再出现"历史请求正文未保存"的情况（但第
  一次已经发生、未保存的那5次历史请求无法回填）。

### 2.4 零调用回归日志（全部基于固定/假响应，无真实Provider调用）

```
$ .venv/bin/python -m pytest tests/test_content_support_llm.py \
    tests/test_content_support_llm_production_wiring.py \
    tests/test_content_support_llm_phase_c_batch_size_fix.py \
    tests/test_phase_c_script_transport_level_fixed_response.py -v
...
40 passed in ~8s
```

（`test_content_support_llm.py` 16个 + `test_content_support_llm_
production_wiring.py` 10个 + `test_content_support_llm_phase_c_batch_
size_fix.py` 6个 + 新增`test_phase_c_script_transport_level_fixed_
response.py` 7个 + 1个预检脚本自身dry-run验证 = 本轮相关路径全部
通过，零回归）。

更广范围的`tests/`全量回归已发起并跑完（约40分钟，4769 passed，
37 failed，18 skipped，3 errors）。逐一核实后确认：**这37个失败与
本轮改动无关**，全部可追溯到本次会话开始前就已经存在、未提交的
其他改动（工作区里`alpha_taxonomy_v1.yaml`/`conflict_detector.py`/
`activation_scorer_v2.py`/`alpha_mapper.py`/
`structured_output_adapter.py`等文件在本轮会话开始时就已显示为
已修改未提交）：
- 大多数失败是"生产语义文件必须与冻结基线逐字节一致"类测试
  （`test_case17_production_semantic_modules_remain_untouched`、
  `test_a6_b1_b2_b3_b4_invariant_modules_are_byte_identical`、
  `test_e42_head_unchanged_from_session_frozen_starting_commit`等）——
  这些文件本来就已经被更早的会话改动但未提交，这类测试理应失败，
  与本轮完全无关。
- 抽查`test_week1a_gate.py`/`test_week4_pipeline_api.py`/
  `test_w5_1b_api.py`三个单独运行时**全部通过**——说明全量回归里
  报的失败是测试间状态污染/顺序问题（该项目已有的测试隔离缺陷），
  不是真失败,更不是本轮改动导致。
- 抽查`test_structured_adapter_concurrency.py`（失败原因：
  `structured_output_adapter.py`引用了`alpha_mapper`）、
  `test_v0_1_3_offline_replay_proof.py`（失败原因：真实MSFT冲突多出
  一个`A102__A304`）、`test_w5_demo_seed.py`
  （`DemoSeedError: NVDA_MAIN_CONFLICT_NOT_ARBITRATED`）——这三个的
  真实失败原因全部指向`conflict_detector.py`/`alpha_taxonomy_v1.yaml`/
  `structured_output_adapter.py`这些本轮完全没有碰过的文件，与本轮
  新增的`week2_llm.py`/`content_support_llm.py`/`file_store.py`/
  `week2_llm_request_audit.py`改动没有任何代码路径交集。
- 本轮专门相关的路径（`week2_llm`/`content_support`关键字匹配的141个
  既有测试 + 本轮新增的40个测试）全部单独验证过，零失败。

---

## 三、请求正文记录与实际transport一致的证明

`tests/test_phase_c_script_transport_level_fixed_response.py`里的
`test_saved_request_audit_matches_literal_transport_bytes_exactly`：

1. 用`httpx.MockTransport`包一个记录器（`_RecordingHandler`），这个
   记录器收到的`httpx.Request`就是"transport实际收到的正文"的唯一
   真实来源。
2. 真实跑一遍`03_phase_c_execution_script.py`的`run()`函数（不是
   重新实现它的逻辑），`enable_request_response_audit=True`按脚本
   新默认值生效。
3. 跑完后，直接从磁盘用`read_jsonl_records`读回
   `error_logs/week2_llm_provider_request_audit.jsonl`，逐条与
   `_RecordingHandler`实际收到的`request.content`字节级比较：

```python
assert saved["body"] == real_body_text
assert saved["body_sha256"] == hashlib.sha256(real_body_text.encode("utf-8")).hexdigest()
```

两者完全相等——这不是"用相同方法、相同输入重新构造一遍、假设应该
一样"（`_request_control_snapshot`原有机制的局限），而是transport
真正收到的那个`httpx.Request`对象本身被落盘，再原样读回比较,逐字节
一致。同时验证了：
- `max_tokens`字段确实出现在真实请求体里，`max_completion_tokens`
  确实不出现（DeepSeek专属字段改名修复已到达字面请求体，不只是
  到达调用前的kwargs）。
- 请求头里的`Authorization`（如果存在）已被替换为`"REDACTED"`，没有
  真实凭据落盘。
- 全局调用上限在transport之前生效：`max-calls=5`时，`_RecordingHandler`
  自己的真实调用计数器只收到5次，另外16条走`FALLBACK_BUDGET_EXHAUSTED`，
  从未到达transport。
- 请求落盘失败→零发送（`test_request_audit_save_failure_means_zero_
  send`：把`_persist_request_audit`打桩成抛异常，`_RecordingHandler`
  收到的请求数=0）。
- 响应落盘失败→当次请求仍然放行（已经收到的真实回答不会被撤销），
  但后续全部claim都不再发送（`test_response_audit_save_failure_
  stops_subsequent_sends`：只有1条到达transport，其余20条走
  `FALLBACK_AUDIT_WRITE_FAILED`）。

---

## 四、当前脚本的实际请求控制配置（现场核实，非文档推测）

- 客户端层重试：0（`build_server_week2_llm_gateway`无条件写死）。
- 应用层重试：`COMQUTOR_WEEK2_LLM_MAX_RETRIES=0` → 真实
  `invoke_json_with_trace`的重试循环精确执行1次。
- 全局调用上限：`COMQUTOR_WEEK2_LLM_MAX_CALLS`（脚本CLI新增
  `--max-calls`，默认21）。
- 输出上限：`max_tokens`作为显式关键字参数，脚本CLI新增
  `--max-tokens`，默认4096，真实到达请求体的`max_tokens`字段（非
  `max_completion_tokens`，已逐字节证明，见第三节）。
- **新发现的候选解释（查DeepSeek官方文档+代码交叉核实，本轮现场
  查证，非猜测）**：api-docs.deepseek.com/api/create-chat-completion
  明确写着`thinking.reasoning_effort`的**文档默认值是`"high"`**。
  直接读代码（`tradingagents/llm_clients/openai_client.py`的
  `_supports_reasoning_effort`只匹配原生OpenAI的`gpt-5`/`o[1-9]`
  模型名）确认：`build_server_week2_llm_gateway`→`create_llm_client`
  这整条路径**从未**给DeepSeek模型显式设置过`reasoning_effort`或
  `thinking`参数。这意味着全部5次真实请求在构造上就不可能显式设过
  这个参数，服务端大概率采用了文档默认的"high"推理强度——**这是
  目前证据链最完整的候选解释**（DeepSeek官方文档的默认值 + 代码
  确认从未覆盖），但历史请求正文本身没有保存，无法从保存下来的
  请求字节直接证实"当时确实缺省"，所以仍然只记为候选，不写成
  已确认根因。

---

## 五、单请求验证提案 + 发送前冻结材料

完整提案见同目录
`06_single_claim_max_tokens_proposal_20261006.md`，要点：

- 目标claim：`1bad76a7-72ac-4c8b-8189-2e5c0f1a6105:bear_researcher:investment_debate_state.bear_history:claim:66`
  （即第五次真实请求那条，唯一已知"单条也截断"的真实样本，不换样本）。
- 唯一改变的参数：`max_tokens: 4096 → 8192`；thinking/reasoning_effort/
  prompt/模型/字段要求/taxonomy/评分规则一律不变。
- 新`execution_id`，全局调用上限设为1，不占用/不等同于原21次额度
  剩余的16次。
- 复用已修复、已通过本轮测试的`03_phase_c_execution_script.py`本身
  （新增的`--max-calls 1 --max-tokens 8192 --target-claim-id ...`
  就是为这次提案加的），不是另写平行脚本。
- 明确声明：历史请求正文未保存，新请求无法证明与当时逐字一致，只能
  证明冻结的claim文本/候选来源哈希/任务版本号/可核实客户端配置一致。
- 预先固定的判定规则（最多发1次、协议有效不等于语义正确、仍截断则
  停止不自动加码、返回有效判断仍需走既有真实性校验、不自动回填
  `HUMAN_REVIEWED`、不自动启动剩余核验或AMD重算）已写入提案文件。
- **这是需要新授权的1次真实付费请求，本轮不执行**。

---

## 六、本轮确认

- 零新增Provider请求。
- 未使用剩余16次额度重试任何已发送声明。
- 未运行独立重算，未宣称AMD分数恢复、Alpha激活、Conflict形成或
  John验收通过。
- 原AMD输入、原结果（`04_phase_c_real_results.json`）、旧报告
  （round9/round4相关文件）及原34条历史证据清单哈希核对后确认
  **全部未变**（见`05_pre_change_protected_artifact_hashes_20261006.json`
  记录的更改前哈希，更改后重新核对全部一致）。
- 本轮过程中发现并修复了一次真实的测试副作用事故：早期版本的新测试
  未能正确重定向Gateway的审计输出目录，导致21条假数据被写入了真实
  项目目录`outputs/runs/phase-c-amd-21-claim-verification/error_logs/
  week2_llm_errors.jsonl`（与历史真实的5条记录混在一起）以及该run
  下新建的两个全假审计文件、`round10...executions/`目录下6个全假
  结果文件——已发现、已清理（恢复`week2_llm_errors.jsonl`到真实的
  前5行，删除新建的假文件/目录），测试已改为统一通过`tmp_path`
  重定向，不会再发生。
