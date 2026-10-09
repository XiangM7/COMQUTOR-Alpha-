# B5 驱动改动与零调用测试（第二部分）

## 改动

| 文件 | 第二部分改动 | diff |
|---|---|---|
| `docs/audit_artifacts/round_source_linking_t0_t2/t3_joint_sample_driver.py` | 重写 | `t3_joint_sample_driver.partA_to_partB.diff` |
| `tests/test_t3_joint_sample_driver.py` | 重写，26 个测试 | `test_t3_joint_sample_driver.partA_to_partB.diff` |
| `t3_joint_verification_driver.py` | 未改（第一部分的两处最小修复仍见 `05_driver/t3_joint_verification_driver.round25.diff`） | — |
| `comqutor_alpha/`（生产代码） | **未改** | — |

驱动重写的内容：

- **Alpha 不再复用历史答案。** 删除"33 条重放充当本次预测"；40 条 Alpha 全部是新请求，L2 的 `answer_source` 固定为 `NEW_REQUEST_THIS_EXECUTION`。历史答案改由 `history` 子命令导出，并标明仅作对照。
- **真实客户端构造** `build_task_gateways`：每个任务一个生产网关，客户端由 tradingagents `create_llm_client` 创建。传输层从外到内依次是：发送守卫、生产 `AuditingTransport`、网络。生产请求和回复审计开启；每个任务写在自己的目录里，避免跨任务写同一文件时丢行。
- **发送守卫** `SendGuard` 和 `GuardTransport`：核对 URL、请求字段、模型、prompt 前缀、冻结的输入哈希和方向批次形状。
  - 不符就不发送，并停止之后所有任务的发送。
  - 遇到 400/401/403/404/422/429、请求审计保存失败或回复审计保存失败，也停止后续发送。
  - 拒绝时抛出的错误是生产 `AuditingTransportError` 的子类，因此网关按"未发送"记录（`audit_unavailable`，不算一次 provider 调用）。
- **检查点** `Checkpoint`：每次发出前和返回后各写一次，fsync 落盘。`status` 汇总已发送、未发送、成功、失败、unknown；unknown 不自动重发；执行目录已存在就拒绝。
- **请求冻结、预检与演练**：
  - `freeze` 生成冻结请求和未签署的计划模板；
  - `preflight` 做全部计划检查，并用固定回复把整条管线完整演练一遍，零网络；
  - `predict` 发送前会重新推导输入、核对代码身份，再演练一次，通过后才发送。
- **采集** `collect`：只在计划的 collection 部分已授权时运行。1 次 Gamma 搜索加 3 次日线价格历史请求；遇到第一个错误就停止，不重复采集。
- **计分**：
  - L1 新增"生产没有核查的原因 × 复核结论"交叉统计，以及按材料状态的忠实性分布；
  - L2 可附历史对照的一致率，只作参考，不计入准确率。

## 冻结身份

| 项目 | 值 |
|---|---|
| HEAD | `7a9aefa5` |
| 已跟踪文件完整差异 | sha256 `ed8ea188…`（与第一部分快照相同：本轮没有改动已跟踪文件） |
| 未跟踪运行时源码 | 22 个文件，sha256 `cbedbcfc…` |
| 驱动 | `ab67368a…` |
| 诊断驱动 | `4918b32c…` |

文件哈希见 `driver_files.json`，代码快照见 `../code_snapshot_partB/`，冻结计划见 `../B4_execution/authorized_plan_TEMPLATE.json`。

## 测试结果

完整证据见 `test_evidence/`：`command_final.txt`、`pytest_final.log`、`exitcode_final.txt`、`junit_final.xml`、`net_trap_final.json`、`summary_final.md`。

- 运行范围是受影响的 3 个测试文件：新驱动测试，以及旧联合驱动、诊断驱动的测试。
- 结果：**77 passed，退出码 0；网络陷阱拦截的外网尝试 0 次，回环连接 0 次**。
- `ruff check` 覆盖本轮的 Python 文件，全部通过。

预检演练（`../B4_execution/preflight_report_TEMPLATE_rehearsal.json`）：

- 计划检查通过（未检查授权）；冻结请求与重新推导结果一致。
- 演练通过：内容核验 17 次、Alpha 40 次、方向 5 次，62 次全部返回成功。
- 每次发送都有请求审计和回复审计；Alpha 和方向另有账本记录；没有任何请求被拒。

**固定回复只证明管线可用，不证明语义质量。** 方向在演练里只发了 5 次，是因为演练给所有 Alpha 都回答 A304，其中多数被生产门槛否决。真实执行的方向请求数取决于真实的 Alpha 答案，上限 13。

## 26 个新测试证明的事

1. 真实客户端发出的请求正好是冻结形状：URL、三个字段、模型、`stream=false`、没有 max_tokens 或 thinking 一类参数、SDK 重试 0；客户端和网关的超时、重试、上限与配置一致；网关预留数等于发出数；没有写回已保存的 run。
2. 每次发送都留下任务、claim、attempt、原始请求和回复、模型、prompt 版本（检查点）、输入哈希、usage；授权头一律脱敏。
3. 40 条 Alpha 全部是新请求；历史答案只是对照。
4. 输出上限一类的字段漂移：请求不发出，守卫只触发一次，之后全部停止；拒绝不会变成 NONE。
5. 冻结之后被改动的输入不发出。
6. 401 之后不再发送任何请求；Alpha 和方向记为 `NOT_REACHED_GUARD_TRIPPED`。
7. 请求审计保存失败时不发送，并停止后续发送。
8. 回复审计保存失败时，之后不再发送。
9. 超时记为传输失败，不当成 NONE，不触发停止，不重试。
10. 方向失败记为任务失败，确定性基线不冒充 LLM 结果，冲突侧资格为"未定"。
11. 请求上限精确。
12. unknown 被如实报告，且不会被重发。
13. 计划未签署、sha 不符、匿名授权、样本漂移、冻结请求漂移、prompt 漂移、代码漂移，都会在构建任何网关之前被拒绝。
14. 完整授权执行会先演练、再写出全部产物；同一执行再次运行会被拒绝（不续跑）。
15. 采集：1 次搜索加每个市场 1 次请求，回复原样保存并带哈希。
16. 采集遇到第一个错误就停止；缺少的市场不会再搜索。
17. 采集只在计划授权后运行，并且不重复。
18. v4 样本和材料可以逐字节重建。
19. 方向上限 13 正好等于新 Alpha 答案的最坏情况；内容核验 17 次、复用 0 条；生产默认批大小有 3 批会超限。
20. 复核表不含系统答案。
21–26. 计分：没有复核人身份的判断不计分；每环用自己的分母，未被核查的样本按原因单列；词表外的值单独报告；复核表与预测不一致时拒绝计分；旧驱动的两处修复仍然有效；网关类确实是生产类。
