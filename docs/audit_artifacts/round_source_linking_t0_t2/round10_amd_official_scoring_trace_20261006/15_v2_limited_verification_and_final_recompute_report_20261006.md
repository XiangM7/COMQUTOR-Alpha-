# v2内容核验有限真实验证 + 独立重算最终报告（2026-10-06）

本轮新增授权6次真实Provider请求，实际发送**恰好6次**，无超发、无重试。
独立重算随后完成。全程保留历史成果，未重启任何诊断轮次。

---

## 一、发送前零调用核对发现并修复的2处真实契约缺口

重读John T1原文、v2报告与实际代码后，发现v2契约本身有2处会不必要地
挡住合理判断的格式性限制，确认后已修复，升版为**v2.1**（v2自身
从未被发送给真实Provider——全部21条历史真实响应都是v1形状——因此
v2.1在v2从未实际使用过的情况下安全接替，身份不冲突）：

1. **GROUNDED_INFERENCE被强制要求非空assumptions**：v2原设计认为
   "推论定义上必然需要假设"，但真实情况并非如此——例如"beta=2.45
   意味着高波动性"直接来自beta的数学定义，不需要额外假设。强制
   要求非空`inference_assumptions`会逼模型编造一个不存在的假设，
   或让一个合理推论被拒绝。**已修复**：`inference_assumptions`
   对GROUNDED_INFERENCE可以合法为空；`inference_facts`仍然对
   DERIVED_CALCULATION/GROUNDED_INFERENCE两者都必须非空（真实推论
   仍必须引用真实事实)。
2. **NON_MATERIAL可以是空洞标签**："便宜""风险最大""应减仓"这类
   表述可能就是核心结论，不能默认判NON_MATERIAL却不给理由。
   **已修复**：判定NON_MATERIAL时必须给出非空rationale，否则记为
   `FALLBACK_INTERNAL_CONTRADICTION`。

两处修复都改了prompt原文，因此版本冻结为新身份
`content_support.llm.v2.1`（`output_schema_version`同步升版），
v2自身的文本和身份保留在代码注释和历史记录里，不回填、不混用。

4个新增定向测试（含"推论无需假设仍通过""NON_MATERIAL无理由判为
矛盾"的真实复现）+既有66个测试全部通过(70 passed)。另有1个
`test_week2_llm.py`里的并发时序测试间歇性失败（`test_concurrent_
success_timeout_and_retry_all_preserve_their_own_attempts`）——
已确认是真实存在的、与本轮改动无关的线程调度时序flaky测试（独立
重跑3次全部通过），不是本轮引入的回归。

冻结后，本轮执行全程未再根据结果修改判断标准。

---

## 二、固定六条真实声明（程序核对，无猜测匹配）

| 简称 | 完整claim_id末段 | Agent | 候选来源 |
|---|---|---|---|
| aggressive:42 | aggressive_risk_analyst:...claim:42 | aggressive_risk_analyst | src_5bd8a947130d1949 |
| fundamental:29 | fundamental_agent:...claim:29 | fundamental_agent | 同上 |
| portfolio:38 | portfolio_manager:...claim:38 | portfolio_manager | 同上 |
| fundamental:119 | fundamental_agent:...claim:119 | fundamental_agent | 同上 |
| bull:61 | bull_researcher:...claim:61 | bull_researcher | 同上 |
| bear:66 | bear_researcher:...claim:66 | bear_researcher | 同上（已知实质错误对照） |

全部6条程序核对确认在已知的21条清单内，未凭简称猜测匹配；
`bear:54`本轮**未**作为付费样本，只在第一节测试回归里离线复用。
来源范围沿用已核实候选（`src_5bd8a947130d1949`），未批量挂载
registry，未用后抓材料补旧声明。

---

## 三、发送前真实执行路径验证（零调用）

- Dry-run（无`--execute`）：全部6条claim确认在21条清单内，
  `source_link_status=VALID`，candidate content_hash匹配；
  `LIVE CHECK`确认真实gateway：`max_retries=0, max_calls=6`。
- 零成本直接验证：`_request_control_snapshot`确认真实序列化字段
  `max_tokens_field=max_tokens, max_tokens_value=8192`（非
  `max_completion_tokens`）。
- `gateway._audit_enabled=True`——AuditingTransport确认挂载。
- 复用已有`test_phase_c_script_transport_level_fixed_response.py`
  （7个测试，走真实脚本+真实transport打桩）确认：单claim单请求、
  候选不串位、请求落盘失败则零发送、响应落盘失败则停止后续发送—
  —全部仍然通过，证明这套安全机制在v2.1契约下继续真实生效。
- 执行前哈希核对：原run全部文件、reeval run、`04_phase_c_real_
  results.json`、原34条清单——全部与此前记录一致。

---

## 四、真实执行结果（逐条，Provider原始 vs 最终有效状态）

```
real_provider_attempts=6（精确等于授权上限，无重试、无超发）
```

| 声明 | Provider状态 | finish_reason | usage(in/out) | 最终状态 |
|---|---|---|---|---|
| aggressive:42 | success | stop | 3036/5710 | **CONDITIONAL** |
| fundamental:29 | provider_error | length（截断） | 3042/8192 | PENDING_REVIEW |
| bull:61 | success | stop | 2995/7619 | **CONDITIONAL** |
| portfolio:38 | provider_error | length（截断） | 3021/8192 | PENDING_REVIEW |
| fundamental:119 | success | stop | 3031/7560 | **CONDITIONAL** |
| bear:66 | provider_error | length（截断） | 2999/8192 | PENDING_REVIEW |

**3条完整回答，3条8192仍截断**（`fundamental:29`/`portfolio:38`/
`bear:66`——与上一轮截断模式一致，具体根因仍未深挖，不在本轮边界内）。

### 3条完整回答的真实support_basis/推论/materiality（逐字摘录）

**aggressive:42**（直接事实+策略建议）：`support_basis=DIRECT_FACT`，
支持部分="50日均线是$513.53"，未支持部分="持有满仓、卖covered
call、逢低加仓的策略建议"，`materiality=MATERIAL`——模型理由：
策略建议部分不是候选材料能确认的内容,是claim的核心行动建议,
实质性缺失依据。**撤回上一轮报告里"可能过严"的推测**——真实v2.1
判断认为这条不是过严误判,是真实、合理的实质性缺口。

**fundamental:119**（真实GROUNDED_INFERENCE案例）：
`support_basis=GROUNDED_INFERENCE`，`inference_facts=["beta=2.454"
来自data_snapshot.beta","beta字段单位是ratio"]`，`inference_
assumptions=["假设beta比率高于1代表相对大盘的高波动性"]`——模型
用真实事实+明示假设,合理地支持了"高波动性"这个结论,**v2.1机制
按设计正确工作**。但claim里"会放大半导体/AI主题的任何波动"是另一个
独立的、主题特定的因果外推,候选材料不支持,`materiality=MATERIAL`,
整体仍为CONDITIONAL。**上一轮"可能过严"的推测部分正确**（推论机制
确实该用上了）**但整体资格结论不变**——因为claim里还有另一块真实
缺依据的部分。

**bull:61**：`support_basis=DIRECT_FACT`（PEG=0.64本身是直接事实），
未支持部分="如果ramp兑现就便宜,Q2财报说在正轨上"，
`materiality=MATERIAL`——模型明确说"便宜"这个估值结论和"Q2财报"
这个独立事实声明都不是候选材料（一份估值快照）能确认的。**撤回
上一轮"可能是合理推论"的推测**——真实v2.1判断没有把"如果ramp兑现
就便宜"当作GROUNDED_INFERENCE处理,而是正确地把"便宜"本身当作
需要真实依据的核心结论,候选材料给不出,判定材料性缺口。

### 3条截断的声明

`fundamental:29`/`portfolio:38`/`bear:66`——零有效内容,保存后继续
下一条,未重试。`bear:66`额外做了一次**明确标注为离线重放**的
零成本处理：把它2026-10-05的真实原始回答（已通过真实wire-level
审计日志取得，非手写）重新喂给当前、未改动的`_process_batch`——
结果是`FALLBACK_INTERNAL_CONTRADICTION`（那条旧回答是v1形状，缺
v2.1必需字段，当前代码正确拒绝把旧答案当新判断,不回填、不冒充)。
**`bear:66`的真实v2.1状态目前仍然是未解决的**——两次真实尝试
（原始+本轮重试）都没能产出可用的v2.1判断,需要新的真实调用才能
确定,本轮未做、也不在本轮授权范围内。

### 分层统计（不同层级分别统计）

- 计划条数：6｜发送前拒绝：0｜实际请求：6｜协议有效：3｜截断：3
- 内容核验通过（无fallback）：3｜资格通过（eligible=True）：**0**
- usage缺失：0（6条全部有完整token_usage）

---

## 五、独立重算（修正了一处真实的历史记录错误）

### 5.1 发现并修正：上一轮重算用错了claim:66的数据

核对时发现：上一次独立重算（`review-20261006T001911Z-14407742`）
直接用了`claim:66`在磁盘上的**原始、被拒绝的**记录
（`PENDING_REVIEW`/`quote_or_data_not_found`，2026-10-05第一次
真实执行当时被多字段引用bug挡住的那个结果），**不是**后来离线
验证过的、修复后的CONDITIONAL结果——因为那个修复后的结果当时只在
一个单元测试里内存演算过，从未真正落盘成一个execution产物。
这是我自己的一处真实错误，已经在本轮的重算脚本里修正：现在
明确调用一次**标注清楚的零成本离线重放**（见上节），得到的真实
结果是`FALLBACK_INTERNAL_CONTRADICTION`（而不是CONDITIONAL——
因为现在的代码同时跑v2.1结构检查，旧答案缺字段）。**这意味着
上一轮报告里"claim:66在重算里是CONDITIONAL"这句话本身是不准确的，
现予更正：claim:66在所有已完成的真实重算里，实际状态都是
PENDING_REVIEW。**

### 5.2 每条claim的数据来源（逐条选取"最新真实有效结果"，失败重试
不抹掉之前的真实成功）

| claim | 本轮使用的execution | 版本 | 说明 |
|---|---|---|---|
| aggressive:42 | phase-c-20261006T034452Z-1ab992d0（本轮） | v2.1 | 本轮真实验证通过 |
| fundamental:29 | phase-c-20261006T000643Z-bb63dfd7（上一轮） | v1 | 本轮重试截断，保留上一轮真实v1结果，不抹除 |
| portfolio:38 | phase-c-20261006T000643Z-bb63dfd7（上一轮） | v1 | 同上 |
| fundamental:119 | phase-c-20261006T034452Z-1ab992d0（本轮） | v2.1 | 本轮真实验证通过 |
| bull:61 | phase-c-20261006T034452Z-1ab992d0（本轮） | v2.1 | 本轮真实验证通过 |
| bear:66 | phase-c-20261005T233842Z-1b2550ac（原始，离线重放） | v2.1重放 | 见5.1，结果PENDING_REVIEW |
| 其余14条 | phase-c-20261006T000643Z-bb63dfd7（上一轮） | v1 | 本轮未涉及，不变 |

### 5.3 真实执行

`based_on_run_id=1bad76a7-72ac-4c8b-8189-2e5c0f1a6105`（真原始run），
`alpha_matches.json`/`extracted_structures.json`原样复制自真原始run,
执行前设置`COMQUTOR_WEEK2_LLM_ENABLED=0`硬性阻断任何意外真实调用。
新execution：`review-20261006T035335Z-3d569e97`，
`_run_week3_graph_pipeline`真实运行，`outcome=success`。

### 5.4 "无匹配"真实原因核实（不是用核验状态推断Alpha分类是否执行）

直接读取真实`alpha_matches.json`（原始run产出，与内容核验完全独立
的真实分类结果）：

| claim | matched_alpha | 真实原因 |
|---|---|---|
| aggressive:42 | None | Alpha分类**已执行**，对全部Alpha评分为0——不是"未执行"，是真实执行后判定不匹配 |
| fundamental:29 | **A304** | 已匹配，score=0.0961 |
| portfolio:38 | None | 已执行，评分0 |
| fundamental:119 | None | 已执行，评分0 |
| bull:61 | **A304** | 已匹配，score=0.052 |
| bear:66 | None | 已执行，评分0 |

`identify_claims_needing_alpha_reclassification`（本轮前已接线的
纯检测函数）对本轮真实v2.1数据运行：**仅`bull:61`被标记**（已匹配
A304且真实MATERIAL未支持余项）——但`bull:61`本身未通过内容核验
（CONDITIONAL），从未进入过正式证据池，所以这个重新分类信号目前
不影响任何真实分数（如果未来某条claim同时满足"eligible=True"且
"MATERIAL remainder"，才需要真正触发重新分类，本轮没有这种claim）。

---

## 六、完整漏斗（逐Alpha、逐冲突，不止写"还是零分"）

### 逐Alpha漏斗（本轮6条 + 已知的1条eligible声明）

| claim | 来源可定位 | 内容核验通过 | claim质量合格 | Alpha匹配 | 去重后正式证据 | 方向 | Exposure贡献 | activation_level | active/dominant |
|---|---|---|---|---|---|---|---|---|---|
| aggressive:42 | ✓VALID | ✗CONDITIONAL | ✓analytical | ✗None | — | — | 0 | — | 否 |
| fundamental:29 | ✓VALID | ✗PENDING(截断) | ✓analytical | ✓A304 | — | — | 0 | — | 否 |
| portfolio:38 | ✓VALID | ✗PENDING(截断) | ✓analytical | ✗None | — | — | 0 | — | 否 |
| fundamental:119 | ✓VALID | ✗CONDITIONAL | ✓analytical | ✗None | — | — | 0 | — | 否 |
| bull:61 | ✓VALID | ✗CONDITIONAL | ✓analytical | ✓A304 | — | — | 0 | — | 否 |
| bear:66 | ✓VALID | ✗PENDING(矛盾/截断) | ✓analytical | ✗None | — | — | 0 | — | 否 |
| **bull:13(PEG,已知)** | ✓VALID | **✓SUPPORTS** | ✓analytical | ✗None | **从未进入**（无Alpha匹配） | — | 0 | — | 否 |

**6条全部在"内容核验通过"这一步停下；唯一真正通过内容核验的
`bull:13`在"Alpha匹配"这一步停下**——没有任何一条走到"去重"/"分数"/
"active"阶段，因为前置条件没有一条同时满足。

### 逐候选冲突（A304候选对，仅有的涉及本轮claim的Alpha）

A304方向：`fundamental:29`/`bull:61`匹配但均未通过内容核验→0条
独立合格证据→未进入可采性函数评估→真实`conflicts.json`与原始run
逐字节相同（已用序关键字忽略的规范化比较核对，无差异）——没有
因本轮新增任何候选冲突评估、拒绝原因与原始run完全相同。

### 明确分层（任何一项通过都不能代替后续项目）

1. 内容核验通过：3/6（aggressive:42/fundamental:119/bull:61）
2. 进入正式证据池：0/6
3. 贡献分数：0/6
4. 达到active：0/6
5. 形成admitted Conflict：0（本轮涉及的候选对不变）

**activation/conflict结果与原始run语义完全相同（已用真实diff核对），
零净变化**——与上一轮20条执行的结论一致。

---

## 七、逐项未完成证明核实（不冒充完成）

- **正式active**：`test_2_full_qualified_set_meets_activation_
  condition_alpha_activates`——重新核对其真实断言：
  `official["activation_level"]=="candidate"`，
  `ALPHA_ID not in graph["active_alphas"]`——**这个测试证明的是
  candidate/被capped状态，不是active**，不能当作active证明使用。
  **真实active的完整、无注入fixture证明——本轮仍未完成**。
- **自动去重生成端**：仍未核实真实抽取流程本身（而非本模块的
  消费端)是否会主动检测跨Agent同一事实——本轮未涉及，保持上一轮
  已如实标注的"未执行"状态。
- **API/Export**：本轮针对**这次新recompute**
  （`review-20261006T035335Z-3d569e97`）重新真实核对：
  `get_run_export_bundle`返回真实200/`application/zip`/真实ZIP
  字节；解压后`structured_agent_outputs.json`/`alpha_activations.
  json`/`conflicts.json`与磁盘逐字节相同；专门核对`aggressive:42`
  在ZIP里的`support_basis=DIRECT_FACT`/`materiality=MATERIAL`与
  磁盘一致。**这是本轮真实完成的新验证**，不同于读磁盘JSON。
- **UI**：**本轮未做浏览器走查**，如实声明未执行，不称为比上述
  API/Export核对更强的证据。

---

## 八、历史保护

原AMD run全部文件（`metadata.json`/`structured_agent_outputs.json`/
`alpha_matches.json`/`extracted_structures.json`/`alpha_activations.
json`/`conflicts.json`）、reeval run、`04_phase_c_real_results.json`、
原34条清单——执行前后哈希核对**全部一致**。原34条历史清单继续保持
完整，新run不替代其验收；历史采用（原34条自己的）、当前资格
（本轮核实的）、独立重算实际采用（本次recompute的真实产出）三者
分开记录，未执行的项目不代入已采用。

---

## 九、费用与usage

本轮6次真实请求：`input=18124, output=45465`token，估算费用
≈**$0.0300**（基于真实usage×DeepSeek非高峰公开定价，未对照真实
账单，不称为"实际扣款"）。usage缺失：0。

---

## 十、如果结果仍为空——逐项具体原因（不写"证据不足"了事）

- **材料不足**：0条——候选来源真实存在且内容真实可核实。
- **实质不支持（真实v2.1判断，非猜测）**：3条（aggressive:42的
  策略建议、fundamental:119的"放大AI主题"因果外推、bull:61的
  "便宜"估值结论+独立Q2事实声明）——均有具体、真实的rationale
  说明为什么材料性缺失。
  **本轮明确撤回上一份报告里对这3条"可能被v1过严规则阻挡"的推测
  ——真实v2.1判断（更宽松、允许合理推论、不强制要求无谓假设）依然
  独立得出相同的材料性缺口判断，证明v1的"过严"不是这3条的真实
  阻塞原因。**
- **核验失败（截断）**：3条（fundamental:29/portfolio:38/bear:66），
  8192 token仍不够，具体字段级归因未做。
- **Alpha匹配未完成或不适用**：不适用——全部6条的Alpha分类均已
  真实执行完毕（非"未执行"），只是评分结果为0或匹配到的Alpha本身
  未获得合格证据。
- **claim质量**：6条全部`claim_quality=analytical`，不是质量问题。
- **方向未解析**：不适用，未到达需要方向判断的阶段。
- **去重/分数/结构/Exposure条件**：不适用，0条claim进入过这些
  阶段。

**具体断点**（若要让这类声明有机会真正贡献分数）：需要同时解决
两个独立问题——(1) 截断问题（3/6条）仍未查明具体根因，(2) 即使
核验通过，这批claim的Alpha匹配命中率本身就很低（6条里只有2条
匹配到任何Alpha）。这不是实现缺陷，是这批材料（AMD基本面快照）
与这批claim（分析师对该快照的解读/策略建议）同Alpha关键词库的
真实重合度问题，需要专门调查后才能给出具体输入建议，本轮不臆测。

---

本轮6次新增请求与独立重算已经结束，按授权停止。不循环调prompt，
不承诺必须非零，不宣布T1或John整体验收通过。
