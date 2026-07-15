# W4.3 Gate Contract — Pipeline / API Integration

审查日期：2026-07-15

本文档是 W4.3 任务指令的唯一交付物之一，按指令要求"只记录本指令定义的
输入、输出、错误语义、范围和 Acceptance criteria"，不新增、不推断、
不替本指令做规格决策。本文档写作时发现该指令与仓库既有
**SPEC-FROZEN** 规格（`docs/week4_spec_freeze_audit.md` 第 14 节）之间
存在真实冲突（见文末《Blocking Conflict》一节）。按本次任务指令的明文
要求："若仓库现有冻结规格与本指令存在真实冲突，停止实现并报告...
不得自行猜测或修改 taxonomy/公式来绕过冲突"，本次会话在写完本文档后
**停止实现**，不创建/修改任何 `.py` 测试或产品代码文件。

---

## 1. Scope（本指令定义）

集成范围：

- Week 3 Structure Graph + Alpha activation（已通过验收，只读输入）
- W4.1 deterministic Conflict Detector（`detect_alpha_conflicts()`，已实现，不重新设计）
- W4.2 activation/conflict persistence（`persist_week4_results()` /
  `get_week4_conflict_result()`，已实现，不重新设计）

本任务只负责把以上三者接入同一条 research pipeline，并提供：

- 稳定的 `GET /api/research/{run_id}/conflicts`
- 稳定的 `GET /api/research/{run_id}/agent-outputs`
- canonical research response 新增字段

明确**不**重新设计 W4.1/W4.2 内部逻辑、公式、taxonomy、schema、
persistence reconstruction、repository contract、migration。

### 1.1 允许修改的文件

- `docs/w4_3_gate_contract.md`
- `comqutor_alpha/api/routes_research.py`
- `comqutor_alpha/api/agent_output_reader.py`（可新建）
- `comqutor_alpha/conflict_engine/pipeline.py`（可新建）
- `comqutor_alpha/api/__init__.py`（仅确有导出需要时）
- `comqutor_alpha/conflict_engine/__init__.py`（仅确有导出需要时）
- `tests/test_week4_pipeline_api.py`（可新建）
- `tests/test_agent_outputs_api.py`（可新建）
- 现有 API/pipeline 测试文件，仅用于更新 W4.3 后的稳定契约断言

### 1.2 Out of scope（不得修改）

alpha taxonomy 或任何 conflict pair、contradiction weights、conflict
formula/level threshold/evidence-strength 公式、main-conflict
arbitration、activation formula、W4.1 detector 内部逻辑、W4.2 schema
validation 和 persistence reconstruction、database schema、migrations
0001/0002、`repository.py`（除非发现可复现的现有 bug，且发现后必须先
停止并报告，不得顺手修改）、`agent_outputs` database table、
`research_runs` table、Exposure Engine、
`entity_alpha_exposure_seed.yaml`、MSFT A102/A304 规格、
authentication/authorization/tenant ownership、真实 HTTP TradingAgents
execution、provider config/API key payload/job queue/background
worker、Graph API 的既有 stateless 重构、`tradingagents/`、README/
license/branding、`docs/current_system_state.md`、全仓库 Ruff 或全仓库
format。

---

## 2. Pipeline Orchestration Contract（本指令定义）

1. Week 4 必须仅在 Week 3 成功生成并持久化 graph 后执行。
2. 不得重新计算 activation；直接使用本次 Week 3 graph payload 中的
   `graph_payload["activation"]`。
3. Conflict Detector 输入必须为：`run_id`、`ticker`、
   `graph_payload["activation"]`、`alpha_matches.json` 中的
   `matches`、正式 taxonomy loader 的默认结果；调用现有
   `detect_alpha_conflicts(...)`。
4. 使用与 Week 3 相同的 injected repository seam
   （`run_research_request()` 已有的 `graph_repository` 参数），不得为
   Week 4 再创建第二套 repository abstraction 或重复数据库连接。
5. 使用现有 `repository.persist_week4_results(run_id=..., ticker=...,
   activation_payload=..., conflict_payload=...)`。
6. Week 4 persistence 成功后，数据库必须同时包含：当前 run 的
   `alpha_activations`；当前 run 的所有 taxonomy-declared conflict
   candidates；admitted/suppressed/rejected outcomes；main conflict
   标记和 rank。
7. 不创建 conflict JSON artifact；W4.3 conflicts 的 source of truth 是
   W4.2 database persistence，不是本地 `conflicts.json`。
8. Week 4 失败不能删除或损坏已经成功完成的 Week 1–3 数据。失败语义：

   | Week 3 | Week 4 | research status | structure_graph_status | conflict_status |
   |---|---|---|---|---|
   | 成功 | 成功 | `completed` | `ready` | `ready` |
   | 成功 | 失败 | `partial` | `ready` | `not_ready` |
   | 失败 | 不执行 | `partial` | `not_ready` | `not_ready` |

9. Week 4 pipeline 异常必须被安全降级。允许新增
   `error_logs/week4_pipeline_errors.jsonl`，其中只允许写 `run_id`、
   `stage`、稳定 `error_code`、`created_at`；不得保存 exception text、
   traceback、DSN、host、username、password、本地绝对路径、raw agent
   output、provider response。默认 WARNING 日志同样不得输出原始异常
   文本。

---

## 3. Canonical Research Response Contract（本指令定义）

保持现有 `artifacts` 字典的 key 和语义完全不变。只增加以下顶层字段：
`dominant_alphas`、`main_conflict`、`conflict_status`、`summary`。

1. **dominant_alphas**：必须直接来自 persisted Structure Graph 的
   `dominant_alphas`，不得重新计算或自行排序。
2. **main_conflict**：必须来自 persisted W4 conflict result。有
   admitted conflict 时为最高排名 conflict；无 admitted conflict 但
   W4 已成功时为 `null`；W4 未就绪时为 `null`。
3. **conflict_status**：只允许 `ready` / `not_ready`。数据库中已经
   成功持久化并可重建完整 conflict result 时为 `ready`。
4. **summary**：deterministic、无 LLM、无网络调用的标准文案，精确
   规则：
   - `conflict_status != ready`：
     `"Conflict analysis is not ready for this research run."`
   - `main_conflict` 非 null：使用 `main_conflict["explanation"]` 的
     原值。
   - `main_conflict` 为 null，`dominant_alphas` 非空：
     `"Dominant Alpha structures were identified, but no
     taxonomy-declared conflict was admitted for this research run."`
   - `main_conflict` 为 null，`dominant_alphas` 为空：
     `"No dominant Alpha structure or admitted conflict was identified
     for this research run."`
   - summary 不得生成 Buy/Sell/Hold、仓位比例、价格目标或投资建议。
5. `POST /api/research` 与 `GET /api/research/{run_id}` 对同一已完成
   run 应返回一致的 `dominant_alphas`/`main_conflict`/
   `conflict_status`/`summary`；不得依赖 POST 时保存在内存里的临时
   结果。

---

## 4. Conflicts API Contract（本指令定义）

`GET /api/research/{run_id}/conflicts`

成功响应：

```json
{
  "run_id": "...",
  "ticker": "...",
  "status": "ok",
  "schema_version": "...",
  "formula_version": "...",
  "conflicts": [...],
  "main_conflict": {} ,
  "arbitration": {}
}
```

要求：直接调用 read-only repository 的
`get_week4_conflict_result(run_id)`；不得重新运行 detector；不得读取
`alpha_matches.json` 或 `structure_graph.json`；不得调用
TradingAgents、LLM 或网络；不得执行 migration、DDL 或任何写入；不得先
检查本地 run directory 是否存在；即使本地 run directory 已删除，只要
数据库记录存在，仍应成功返回；返回内容必须等于 W4.2 deterministic
reconstruction，只允许增加顶层 `status="ok"`。

稳定错误码：`INVALID_RUN_ID`（run_id 非法）、`CONFLICTS_NOT_READY`
（repository 返回 `None`）、`CONFLICTS_UNAVAILABLE`（DB 连接/读取
失败）、`CONFLICTS_CORRUPTED`（W4.2 reconstruction 报数据损坏或
schema 不一致）。错误响应不得包含原始异常、DSN、路径或数据库信息。

---

## 5. Agent Outputs API Contract（RESOLVED — STRUCTURED_ONLY，见第 7 节裁决）

**本节已被规格负责人裁决替换（2026-07-15），取代本文档最初起草时记录的
"本指令原文"版本（该版本已完整保留在第 7 节作为冲突发现的审计记录，
未被删除或倒改）。当前生效契约如下。**

`GET /api/research/{run_id}/agent-outputs`

当前 W4.3 继续使用 file-backed **structured** artifact，不新增
`agent_outputs` 数据库表。必须通过独立 reader/service
`comqutor_alpha/api/agent_output_reader.py`；route 不得直接调用
`Path.read_text()`，不得自行复制 JSON parsing、validation 或文件布局
逻辑。

唯一数据源：`structured_agent_outputs.json`。**Reader 不得读取
`raw_agent_outputs.json`，即使该文件存在也不得打开。**

成功响应（已裁决版本）：

```json
{
  "run_id": "...",
  "ticker": "...",
  "status": "ok",
  "schema_version": "...",
  "structured_agent_outputs": [],
  "count": 0
}
```

数据来源：`structured_agent_outputs.json` 顶层 `records`。

要求：

1. `structured_agent_outputs` 直接来自 `structured_agent_outputs.json`
   顶层 `records`，保持原始顺序。
2. 保留现有 structured record 中实际存在的字段（`claim_id`、
   `source_agent_output_id`、`agent`、`claim`、`evidence`、`entities`、
   `factors`、`direction`、`confidence`、`source_type`、
   `assertion_status`、`semantic_polarity` 等）；仅保留 artifact 中
   实际存在的字段，不伪造缺失字段，不隐藏现有 provenance 字段。
3. 验证：payload 必须是 dict；`payload.run_id` 必须等于请求
   `run_id`；`ticker` 必须为非空字符串；`records` 必须是 list、每项
   必须是 dict；`schema_version` 必须为非空字符串。
4. 响应不得包含：`raw_agent_outputs`、`raw_output`、
   `raw_schema_version`、`raw_count`、完整 analyst report、bull/bear
   debate transcript、investment plan transcript、risk debate
   transcript、final trade decision transcript、本地文件路径。
5. 不调用 LLM、TradingAgents、provider 或网络；不新增数据库表、
   migration 或双写逻辑。

稳定错误码：`INVALID_RUN_ID`、`RUN_NOT_FOUND`、
`AGENT_OUTPUTS_NOT_READY`、`AGENT_OUTPUTS_CORRUPTED`、
`AGENT_OUTPUTS_UNAVAILABLE`。

错误语义：run_id 非法 → `INVALID_RUN_ID`；run directory 不存在 →
`RUN_NOT_FOUND`；`structured_agent_outputs.json` 不存在 →
`AGENT_OUTPUTS_NOT_READY`；JSON 无法解析、shape 错误、run_id
mismatch、schema_version 错误或 `records` 非 list →
`AGENT_OUTPUTS_CORRUPTED`；安全读取过程中出现其他存储错误 →
`AGENT_OUTPUTS_UNAVAILABLE`。错误响应不得包含异常原文、绝对路径或
artifact 内容。

---

## 6. Acceptance Criteria（本指令定义）

1. 一次成功 research request 自动完成 Week 1–4。
2. W4.1 detector 只在 Week 3 成功后调用一次。
3. W4.2 persistence 使用同一 `run_id`、`ticker` 和 activation
   snapshot。
4. POST 与 GET research response 提供一致的
   `dominant_alphas`/`main_conflict`/`conflict_status`/`summary`。
5. `/conflicts` 只读数据库，不依赖本地 run directory。
6. `/agent-outputs` 通过独立 file-backed reader。
7. `artifacts` 字典未改变。
8. W4.1/W4.2 公式、taxonomy、migration 和 repository contract 未
   改变。
9. Week 3 PostgreSQL integration 全部通过、0 skipped。
10. W4.2 PostgreSQL integration 全部通过、0 skipped。
11. 完整 offline suite 0 failed。
12. 产品代码中没有新增 LLM、provider、network 或 real-run 行为。
13. 没有全仓库格式化。
14. 没有修改 `docs/current_system_state.md`。

---

## 7. Blocking Conflict — Agent Outputs Raw Exposure

**分类：真实冲突，本次会话不裁决，停止实现。**

### 7.1 冲突文件与条款

`docs/week4_spec_freeze_audit.md` 第 14 节（Database Delta）：

> `agent-outputs` endpoint 的 raw/structured 暴露风险？**APPROVED —
> SPEC-FROZEN FOR W4.1**（2026-07-14 closure）：`/agent-outputs`
> **默认 structured-only**（`structured_agent_outputs.json` 的 claim
> 级结果），**不**暴露完整 raw transcript。`raw_agent_outputs.json`
> 目前是内部产物，从未通过任何现有 endpoint 直接对外暴露原文；这个
> 批准延续了这一现状，也延续了本次任务反复强调的"Week 4 不应重新
> 解析/暴露原始自由文本"的精神。是否在未来提供一个显式、额外的 raw
> 暴露开关（而非默认行为）不在本次批准范围内，若需要应作为单独决策
> 处理。

该条款标注为 **APPROVED — SPEC-FROZEN FOR W4.1**（不是 PROPOSED，是
已经过规格负责人正式批准、冻结为 W4.1/W4.2/W4.3 实现基线的条款）。

### 7.2 本指令与冻结规格的差异

本次 W4.3 任务指令第五节"Agent Outputs API"明确要求：

> 成功响应：
> ```
> { ... "raw_agent_outputs": [...], "structured_agent_outputs": [...],
> "raw_count": 0, "structured_count": 0 }
> ```
> 数据来源：raw_agent_outputs.json 中的 agent_outputs

即本指令要求 `/agent-outputs` **默认返回完整 `raw_agent_outputs`**
数组，与冻结规格"默认 structured-only，不暴露完整 raw transcript"
直接矛盾——不是可以并存的两种描述粒度，是同一个默认响应形状的"暴露"
与"不暴露"之间的直接对立。

本次审计已直接读取
`comqutor_alpha/adapters/tradingagents_output_writer.py::
build_raw_agent_output_record()`（`raw_agent_outputs.json` 的
`agent_outputs` 数组正是由此函数生成）确认：每条记录的 `raw_output`
字段就是冻结规格所指的"完整 raw transcript"本身——market/sentiment/
news/fundamentals 分析师报告全文、bull/bear researcher 完整辩论历史、
research manager 的 `investment_plan` 全文、trader 计划全文等，单条
最长可达 `MAX_RAW_OUTPUT_CHARS = 50000` 字符（超长时才截断，见
`_truncate_raw_output`）。这不是元数据或摘要，是自由文本原文，与
冻结规格描述的"raw transcript"完全一致。

### 7.3 为何不能自行裁决

- 若按本指令实现（默认暴露 `raw_agent_outputs`），直接违反一条已经
  规格负责人正式批准、标注 `APPROVED — SPEC-FROZEN FOR W4.1` 的冻结
  条款——这不属于本次任务"只负责集成现有模块，不重新设计 W4.1/W4.2"
  的授权范围，也不属于本次允许修改的文件列表（不包含
  `docs/week4_spec_freeze_audit.md` 本身的内容变更权限之外的规格
  推翻权）。
- 若按冻结规格实现（默认 structured-only，不返回 `raw_agent_outputs`
  或将其置空/隐藏），则直接违反本次任务指令第五节明确写出的响应
  schema 与验收标准（"验证两个 payload 都是 dict"、"数据来源：
  raw_agent_outputs.json 中的 agent_outputs"等要求默认必须读取并
  返回 raw 内容）。
- 两者互斥，且都非本次会话的裁决权限——按本次任务指令原文"不得自行
  猜测或修改 taxonomy/公式来绕过冲突"的同一精神，此处属于"绕过一条
  已批准的 API 暴露面规格冻结条款"的同类风险，本次会话不代为决定。

### 7.4 未实施的后续影响

由于本冲突直接落在"允许修改文件"清单中的
`comqutor_alpha/api/agent_output_reader.py`（新建）与
`comqutor_alpha/api/routes_research.py`（新增 `/agent-outputs`
route）之上，且该 route 是本次任务四个交付物之一，本次会话在提交本
Gate Contract 文档后**停止后续实现**：

- 未创建 `comqutor_alpha/api/agent_output_reader.py`
- 未修改 `comqutor_alpha/api/routes_research.py`
- 未创建 `comqutor_alpha/conflict_engine/pipeline.py`
- 未创建 `tests/test_week4_pipeline_api.py` / `tests/test_agent_outputs_api.py`
- 未运行任何 Validation commands（既有测试套件未被触碰，无需重新
  验证）
- 工作树中除本文档外无其他文件变更

Pipeline orchestration（第 2 节）、canonical research response（第 3
节）、conflicts API（第 4 节）三部分本身与现有冻结规格**没有**发现
冲突，具备独立实现条件；但由于本任务是一次性交付四个耦合的交付物
（pipeline + canonical response + conflicts API + agent-outputs
API），且 acceptance criteria 第 6 条要求 POST/GET 一致性建立在
Week 1–4 全链路（含 agent-outputs 契约）之上，本次会话选择在报告
冲突后整体停止，等待关于 agent-outputs 暴露面的裁决，而不是先实现
其余三项、把 agent-outputs 单独悬空——后者会造成"部分合并、部分阻塞"
的中间状态，其本身也需要产品/工程判断是否可接受，同样不应由本次
会话自行决定。

### 7.5 需要人工裁决的问题

1. 是否修改冻结规格（`docs/week4_spec_freeze_audit.md` 第 14 节），
   正式批准 `/agent-outputs` 默认暴露完整 `raw_agent_outputs`（与
   本次任务指令一致）？
2. 或者修改本次任务指令，让 `/agent-outputs` 默认 structured-only、
   `raw_agent_outputs` 改为不返回/需要显式开关（与冻结规格一致）？
3. 或者采用某种两者都未明确排除的折中（例如显式 opt-in query
   parameter），但这属于新的规格提案，需要规格负责人批准后才能
   实施，不属于本次会话的裁决权限。

### 7.6 规格负责人裁决（2026-07-15）

**裁决结果：遵守 `docs/week4_spec_freeze_audit.md` 已批准并冻结的接口
边界（对应第 7.5 节选项 2）。**

- `GET /api/research/{run_id}/agent-outputs` 默认只返回 structured
  claim-level outputs。
- 不得返回 `raw_agent_outputs.json` 中的 `raw_output`。
- W4.3 不新增 `raw=true`、`include_raw`、`debug`、`admin` 或其他
  opt-in 开关。
- raw transcript 的授权、脱敏、审计和专用访问接口留待后续独立规格，
  不属于 W4.3。

字段：

```
Resolution: STRUCTURED_ONLY
raw transcript exposure: OUT_OF_SCOPE
W4.3 Entry: READY
```

本节之上第 7.1–7.5 节记录的原始冲突发现（本次任务指令最初要求默认
暴露 `raw_agent_outputs`，与冻结规格直接对立）**予以保留，不删除、
不倒改，作为该冲突确实发生过的审计记录**。第 5 节已更新为反映本次
裁决后的、当前生效的 Agent Outputs API 契约；第 5 节标题明确注明
"RESOLVED"，读者应以第 5 节为实现依据，第 7.1–7.5 节仅作历史留痕。

裁决后，Pipeline Integration、Conflicts API、Canonical Research
Response 三项不再因本次冲突继续被阻塞——它们本身与冻结规格无冲突
（见第 7.4 节），此前选择与 Agent Outputs API 一并停止仅是因为四个
交付物耦合、且裁决权限不在本次会话；裁决完成后该耦合考量已解除，四项
可继续实现。

---

## 8. Verdict

```
W4.3 Gate Contract: FROZEN (RESOLVED — STRUCTURED_ONLY)
W4.3 Pipeline Integration: see docs/w4_3_gate_contract.md 更新记录 / 最终交付报告
W4.3 Conflicts API: see 最终交付报告
W4.3 Agent Outputs API: see 最终交付报告（契约为 STRUCTURED_ONLY，第 5 节）
W4.3 Canonical Research Response: see 最终交付报告
Formal Week 4 Integration Gate: see 最终交付报告

Exposure Engine: BLOCKED_BY_SEED (unchanged, unrelated to this session)
MSFT Golden Gate: BLOCKED_BY_SPEC_CONFLICT (unchanged, unrelated to this session)
```

（本文档只记录契约与冲突裁决过程；逐项 PASS/FAIL 判定与测试结果见
本次会话对用户的最终回复，不在此处重复维护，避免两处判定不同步。）
