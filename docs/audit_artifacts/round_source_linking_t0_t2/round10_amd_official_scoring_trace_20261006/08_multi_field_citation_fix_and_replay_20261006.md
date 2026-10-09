# 多字段引用校验修复 + 真实单claim响应离线重放（2026-10-06）

本轮零新增Provider调用。全部验证基于已保存的真实单claim响应
（`execution_id=phase-c-20261005T233842Z-1b2550ac`）离线重放，不重新
调用模型，不运行其余20条，不重算AMD。原请求/响应/历史run全部只读，
未修改（见文末哈希核对）。

---

## 一、纠正上一份报告的归因

上一份报告（`07_single_claim_execution_result_20261006.md`）把问题
简化成"唯一阻塞是引用匹配,不是模型判断问题"——**这个表述现予撤回**。
真实情况是两个独立问题：

1. **多字段真实引用被现有整串匹配错误拒绝**——这是一个真实bug，
   本轮已修复（见第二节）。
2. **原claim本身存在未被支持、且被模型正确指出的部分**——Provider
   返回的`status="SUPPORTS"`只是模型对"自己能验证的那部分"给出的
   原始判断，不等于整条原始claim都成立。`unsupported_remainder`
   非空时，必须执行已有的部分支持降级规则（见第三节）——这件事
   在上一份报告里完全没有执行到，因为该claim在降级逻辑之前就已经
   被引用匹配挡住了，不是"降级机制失效"，而是"根本没跑到降级那一步"。

---

## 二、修复多字段引用校验（最小diff）

### 根因

`comqutor_alpha/structure_engine/content_support_llm.py`原有的
`_data_field_found`把`supporting_quote_or_data`整串当成**一个**待查值，
去`data_snapshot`的每个叶子节点找相等/包含关系。真实响应把三个数字
合并成一句话："beta: 2.454; fifty_day_average: 513.5342; two_hundred_
day_average: 374.7236"——这句话整体不等于、也不包含在任何单个叶子
（每个叶子只是一个数字,如`2.454`）里,因此被错误拒绝,即使三个数字
各自都真实存在。

### 修复（新增函数，不改动既有单字段/文本引文逻辑）

```python
def _resolve_candidate_path(candidate: Mapping[str, Any], path: str) -> Any:
    """按点分路径（如"data_snapshot.beta"）直接在candidate上解析，
    任何一段不存在就返回_MISSING_PATH——不去别处找同名字段。"""
    node: Any = candidate
    for segment in path.strip().split("."):
        segment = segment.strip()
        if not segment or not isinstance(node, Mapping) or segment not in node:
            return _MISSING_PATH
        node = node[segment]
    return node

def _values_match(claimed_text: str, real_value: Any) -> bool:
    """机械相等比较（字符串相等或数值在浮点误差内相等），不做模糊/
    语义匹配。"""
    ...

def _multi_field_citation_valid(candidate, used_location, quote_or_data) -> bool | None:
    """按";"切分used_location和supporting_quote_or_data，逐项核对
    (路径, 值)绑定；段数<2或两边段数不一致时返回None（交给既有单值
    逻辑处理，不新增放宽）；任意一段路径未知或值不符，整条引用判定
    为False——不会丢掉错误段、只保留正确段再放行。"""
    paths = [p.strip() for p in used_location.split(";") if p.strip()]
    quotes = [q.strip() for q in quote_or_data.split(";") if q.strip()]
    if len(paths) < 2 or len(paths) != len(quotes):
        return None
    for path, quote_segment in zip(paths, quotes, strict=True):
        claimed_value = quote_segment.split(":", 1)[-1].strip() if ":" in quote_segment else quote_segment
        resolved = _resolve_candidate_path(candidate, path)
        if resolved is _MISSING_PATH or not _values_match(claimed_value, resolved):
            return False
    return True
```

`_validate_response_item`里的接入点（原有的`_quote_found_in_excerpt`/
`_data_field_found`调用保持不变，仅在"看起来像多字段引用"时优先走
新逻辑）：

```python
multi_field_result = _multi_field_citation_valid(candidate, used_location, quote_or_data)
if multi_field_result is not None:
    found = multi_field_result
else:
    found = _quote_found_in_excerpt(quote_or_data, excerpt) or _data_field_found(
        quote_or_data, candidate.get("data_snapshot")
    )
```

**没有使用模糊/语义匹配，没有批量搜索整个registry**——路径必须按
candidate自己的结构逐段精确解析，值必须机械相等（或数值误差内相等）。

### 定向测试日志（11个新测试，全部基于已保存的真实数据，零新增调用）

```
$ .venv/bin/python -m pytest tests/test_content_support_llm_multi_field_citation.py -v
...
11 passed in 0.24s
```

| 测试 | 验证点 |
|---|---|
| `test_real_three_field_citation_each_field_locatable_and_correct` | 真实响应的三个字段引用全部可定位、值正确 |
| `test_wrong_field_value_binding_is_rejected_not_silently_dropped` | 把fifty_day_average的真实值错配给beta路径——拒绝 |
| `test_coincidentally_matching_value_in_a_different_field_does_not_pass` | 数字在别的真实字段里存在，但不在claimed路径——拒绝（直接针对"碰巧相同"场景）|
| `test_unknown_path_is_rejected` | 路径不存在——拒绝 |
| `test_source_reference_outside_allowed_candidates_still_rejected` | 伪造`used_source_id`——仍被既有`FALLBACK_SOURCE_NOT_IN_CANDIDATES`拒绝 |
| `test_mismatched_segment_counts_still_rejected_not_silently_passed` | 3个路径对2个引用值——段数不一致，仍被拒绝 |
| `test_existing_single_field_citation_still_works_no_regression` | 既有单字段引用逻辑无回归 |
| `test_existing_text_excerpt_citation_still_works_no_regression` | 既有文本摘录引用逻辑无回归 |
| `test_original_claim_text_and_claim_id_never_altered` | 原claim文本/claim_id全程未被修改 |
| `test_partial_unsupported_remainder_downgrades_to_conditional_not_supports` | 见第三节 |
| `test_conditional_status_is_not_eligible_as_formal_evidence_real_function` | 见第三节 |

与既有40个测试一并跑（content_support全家桶，含本轮之前新增的
batch_size修复、transport审计测试）：

```
$ .venv/bin/python -m pytest tests/test_content_support_llm.py \
    tests/test_content_support_llm_production_wiring.py \
    tests/test_content_support_llm_phase_c_batch_size_fix.py \
    tests/test_phase_c_script_transport_level_fixed_response.py \
    tests/test_content_support_llm_multi_field_citation.py -v
...
51 passed in 10.00s
```

---

## 三、验证既有部分支持降级机制——确认正确执行，无需额外修复

按你的要求"如果真实代码已经存在部分支持降级机制，本轮优先验证它；
只有复现其未正确执行时，才修那个具体断点"——**真实代码里确实已有
`_effective_content_support_status`**（Section 5注释明确写明：带非空
`unsupported_remainder`的SUPPORTS判断永远不会被升级为完整SUPPORTS,
而是记为CONDITIONAL）。本轮做的是**用真实保存的响应,通过真实、未
改动的`_process_batch`函数完整重放一遍**（不是我自己拼装调用顺序,
是调用生产代码本身），验证结果：

| 项目 | 重放结果 |
|---|---|
| Provider原始`status`字段 | `SUPPORTS` |
| `unsupported_remainder` | `"The stock itself is 37% above its 200-day average and this is maximum downside convexity."`（非空）|
| 修复后`content_support_llm_fallback_reason` | `None`（引用验证通过）|
| **最终`content_support_status`** | **`CONDITIONAL`**（已验证真实降级，不是SUPPORTS）|
| `content_support_llm_detail.llm_status`（原始模型判断,单独保留） | `SUPPORTS` |
| 真实`compute_verified_support_eligibility()`返回 | `{"eligible": false, "reason_code": "SUPPORT_STATUS_NOT_RESOLVED"}` |

**结论：降级机制和资格函数本身都正确执行，不需要额外修复**——第一次
报告之所以没看到这个结果，是因为该claim在降级逻辑运行之前就已经被
（有bug的）引用匹配挡住了，根本没走到这一步，不是机制本身坏了。

原claim文本/claim_id全程未变（已用`test_original_claim_text_and_
claim_id_never_altered`确认）；模型纠正后的命题
（"50日均线比200日均线高约37%"）**没有、也不会**替换原claim的
"股价比200日均线高约37%"——两者在`content_support_llm_detail`里
分别保存为`supported_proposition`/原始`claim`字段，从未互相覆盖，
本轮也没有新增任何"安全拆句"机制去尝试合并或替换它们。

---

## 四、本例修复前后对照

| | 修复前（上一份报告） | 修复后（本轮重放） |
|---|---|---|
| Provider原始状态 | SUPPORTS（finish_reason=stop，未截断） | 同左，未变（复用同一真实响应，未重新调用模型） |
| 引用校验结果 | 拒绝（`quote_or_data_not_found`） | 通过（三个字段路径+值逐一核对成功） |
| 最终`content_support_status` | `PENDING_REVIEW`（未变，被引用校验挡住） | `CONDITIONAL`（真实降级，既不是SUPPORTS也不是PENDING_REVIEW） |
| `compute_verified_support_eligibility` | 未执行到（记录未变,仍是PENDING_REVIEW的既有资格判定) | `eligible=False, reason_code=SUPPORT_STATUS_NOT_RESOLVED` |
| 是否进入正式证据池 | 否 | **否**——CONDITIONAL不计入`_RESOLVED_SUPPORT_STATUSES`，不构成正式证据 |

**两种情况下这条claim都不是正式证据**——修复前是因为引用校验的bug
把它挡在PENDING_REVIEW；修复后是因为原claim本身确有不被支持的部分,
按既有规则正确降级为CONDITIONAL后依然不计入正式证据。结果没有变成
"通过"，只是阻塞原因从一个bug变成了一个真实、正确的业务规则判定。

---

## 五、下一批执行前仍存在的具体问题

1. 本次修复只处理了"多个真实数字合并成一句话引用"这一种真实模式
   （已在真实响应中观察到）。如果未来某条claim用其他组合方式
   （例如混合文本摘录+数字，或路径分隔符不是分号）引用多个字段,
   现有`_multi_field_citation_valid`的分隔/解析方式可能不适用——需要
   在拿到真实样本后再扩展，本轮不臆测扩展范围。
2. 第四轮报告（round10第一份报告）提到的"reasoning_effort默认high"
   候选解释依然只是候选，本轮未做任何验证或改动。
3. 其余20条claim尚未核验，是否会出现同样的多字段引用模式、是否会
   触发CONDITIONAL降级、各自的资格判定结果，均未知——本轮明确不
   推断,不外推。
4. 本轮未修改评分阈值、prompt、taxonomy、人工审核策略，未commit/push。

---

## 六、历史文件哈希核对（执行前后，全部一致）

`outputs/runs/1bad76a7-...metadata.json`/`structured_agent_outputs.json`、
`automated-eligibility-reeval-.../structured_agent_outputs.json`/
`source_registry.json`、`04_phase_c_real_results.json`——全部与本轮
开始前的记录哈希一致，未被本轮任何操作修改。真实单claim执行的结果
文件（`executions/phase-c-20261005T233842Z-1b2550ac.json`）和真实
请求/响应审计日志同样保持只读，未被本轮的离线重放覆盖或修改
（重放只读取,从未写回这些文件）。
