# COMQUTOR Alpha — Week 0–6 独立对抗式工程审计报告

审计人：独立审计代理（非实现者）。方法：对抗式复核（假设声明有罪，要求代码/运行证据推翻），非确认式复核。

---

## 1. Executive Verdict

Week 0–6 的**核心公式与安全边界**（Week 3 Activation 五分量、Week 4 冲突分数 `min()` 公式、路径穿越防护、secret allowlist、DB 读写分离、并发 claim 原子性）在对抗测试下**全部成立**，且均以独立手工 oracle 或活体 mutation 验证，而非仅信任测试通过。

但审计发现 **7 个 P1 级生产逻辑缺陷**（无 P0）分布在 Week 0–2，以及 1 个**已在当前 HEAD 上真实可复现、影响 6–11 个测试的环境隔离缺陷**（非我方审计环境臆造）。文档中的"Week 0–6: PASS"系列声明，**不能仅凭文档或"测试通过"字样采信**——例如 Week 0 的 CLI `--checkpoint` 标志被证明是空操作，`setup.py`/`conditional_logic.py` 两个决定图拓扑与循环终止的模块被证明零测试覆盖；Week 2 的"20/20 clean gate"背后的 `FACTOR_ALIASES` 表被 git 历史证明是在 golden test set 提交**之后**、且直接抄录其短语写成的，与真实 NVDA 报告上 76.7% 的独立准确率形成对照。

没有发现任何伪造分数、虚构冲突 ID、绕过生产入口的测试，或被吞掉后仍报告成功的错误路径。**没有发现 P0 缺陷。**

---

## 2. 实际 HEAD 与审计环境

```
git rev-parse HEAD               → 64e657958aa1db32528d55e8b9c5520b387f86fc  (tag v0.1, 2026-07-17 14:51:12 -0700)
git rev-parse origin/comqutor-structure-layer → 同上，ahead/behind = 0/0（已 fetch 确认）
git status --short (审计前后)     → 仅 `?? frontend/.vite/`（Vite 构建缓存，未跟踪，与审计无关，审计前后均存在）
```
工作树全程未被本次审计修改（多次 `git status`/`git diff --stat` 确认为空）。Python 3.13.5 / `.venv/bin/python`；Node v25.8.0 / npm 11.11.0；本地 PostgreSQL 16（docker，端口 5433）在审计开始前已在运行，`COMQUTOR_DATABASE_URL`/`COMQUTOR_TEST_DATABASE_URL` 已在 `.env` 中配置（值未读取/未打印）。

**重要环境发现（非代码缺陷，但影响本报告如何解读"测试通过"）：** 本仓库没有 `pytest-dotenv` 或 `conftest.py` 级别的 `.env` 自动加载；`.env` 只会在导入 `tradingagents` 包时被动加载（`tradingagents/__init__.py:12-15` 的 `load_dotenv(find_dotenv(usecwd=True))`），而不是被 `comqutor_alpha` 自身导入触发。这带来两个可复现的后果，均已独立验证（非单个子代理的孤立说法）：
1. 单独运行 `pytest tests/test_graph_persistence_postgres_integration.py -m integration`（不先导入 `tradingagents`）→ **5 skipped**（"COMQUTOR_TEST_DATABASE_URL is not set"），我本人独立复现。CI 不受影响，因为 `.github/workflows/ci.yml` 用显式 `env:` 块设置该变量，不依赖这个副作用。
2. 当 `COMQUTOR_DATABASE_URL` 通过上述副作用泄漏进整个 pytest 进程环境后，`comqutor_alpha/storage/db/engine.py:59-61` 的 `resolve_database_url()` 会**优先于**调用方传入的 `output_root`/`tmp_path` 使用这个环境变量——导致本应隔离的"offline"单元测试静默连接到真实共享 Postgres。这不是本次审计环境的臆造：本人两次独立运行 `pytest -q -m "not integration"` 得到 **6 失败 → 11 失败**（失败集合真实扩大，非重跑抖动），根因由我本人和 Week 5/Week 6/cross-cutting 三个独立子代理各自复现一致。详见 §8 与 §11。

---

## 3. Week 0–6 Verdict Matrix

| Week | Verdict | P0 | P1 | P2 | 核心正向证据 |
|---|---|---|---|---|---|
| 0 — TradingAgents 基线 | **PARTIALLY_VERIFIED** | 0 | 1 | 2 | 图拓扑/终止逻辑经代码读取确认，W7 streaming runner 忠实复现 `propagate()` 语义 |
| 1 — Runner/Writer/FileStore/Taxonomy | **VERIFIED_WITH_LIMITATIONS** | 0 | 1 | 2 | 路径穿越、原子写、secret allowlist、taxonomy 对称性全部活体验证通过 |
| 2 — Structure Engine | **VERIFIED_WITH_LIMITATIONS** | 0 | 2 | 5 | 0.35 阈值边界、LLM 越权隔离、negated/no-evidence 语义活体验证通过 |
| 3 — Graph Engine + DB | **VERIFIED_WITH_LIMITATIONS** | 0 | 0 | 1 | 两组手工 oracle 与生产输出逐分量精确匹配；GET 只读性以 SQL 语句抓包证明 |
| 4 — Conflict Engine + Exposure | **VERIFIED_WITH_LIMITATIONS** | 0 | 0 | 1 | 两组手工 oracle 精确匹配；`min()` 非 `max()` 确认；A102/A304 未被伪造；Postgres 真实回滚验证 |
| 5 — Lifecycle/Jobs + Frontend | **VERIFIED_WITH_LIMITATIONS** | 0 | 0 | 2 | 8 线程真实并发 claim 攻击未产生双重 claim；终态覆盖/retry 复用/前端状态机全部对抗验证通过 |
| 6 — Hardening/CI/Demo | **VERIFIED_WITH_LIMITATIONS** | 0 | 0 | 2 | DB-first 读路径、CI 三个真实 job 无常绿步骤、demo 脚本证明未绕过真实管道 |

**没有任何一周被判定为 INCORRECT 或 UNVERIFIED。** 判定为 PARTIALLY_VERIFIED 的仅 Week 0，原因是一个面向用户的功能（CLI checkpoint-resume）被证明完全不生效，且两个决定图执行顺序的模块零测试覆盖。

---

## 4. 完整生产数据流调用图（独立核实，非单周代理各自声称）

```
TradingAgents 图执行 (tradingagents/graph/{trading_graph,setup,propagation,conditional_logic}.py)
  └─ final_state (AgentState, tradingagents/agents/utils/agent_states.py:47-77)
       │  [唯一被证实忠实复现 propagate() 语义的路径: W7 streaming runner；CLI 路径独立重实现且跳过 checkpoint/memory-log 副作用]
       ▼
comqutor_alpha/adapters/tradingagents_output_writer.py::save_comqutor_run_outputs
  └─ raw_agent_outputs.json (outputs/runs/<run_id>/) — file_store.py 原子写 + run_id/ticker 路径校验
       ▼
comqutor_alpha/structure_engine/structured_output_adapter.py::adapt_run_outputs
  └─ structured_agent_outputs.json (claim 拆分 + direction/assertion_status/semantic_polarity)
       ▼
comqutor_alpha/structure_engine/alpha_mapper.py + structure_extractor.py
  └─ alpha_matches.json + extracted_structures.json（确定性 admissibility gate 在 LLM 之前计算，LLM 仅可在 ≤3 个确定性候选中 select/defer）
       ▼  [独立确认：graph_builder.py 只导入这两个 payload，无 raw report 访问]
comqutor_alpha/graph_engine/graph_builder.py + activation_scorer.py
  └─ structure_graph（DB: structure_graphs.graph_json, alpha_matches 表）
       │  [独立确认：GET /graph 路径以 SQL 语句抓包证明零 INSERT/UPDATE/DDL]
       ▼
comqutor_alpha/conflict_engine/conflict_detector.py
  └─ alpha_conflicts 表（admitted/suppressed/rejected 全量持久化，非仅 admitted）
       │  [独立确认：/conflicts 端点仅读 DB，删除本地 run 目录后仍返回正确结果]
       ▼
comqutor_alpha/api/routes_research.py (build_research_response)
  └─ status = completed 当且仅当 Week1-2 完整 + Week3 status=success + Week4 week4_succeeded；否则降级 partial/failed
       ▼
frontend: ResearchPage → ProcessingPage/ResearchRunPage → StructureGraphPage / ConflictRadarPage
  └─ 全部以 URL :runId 为唯一真源；refresh 从服务器重新拉取，非本地状态
```

**该链路是真实端到端连接的证据（非各阶段分别演示）：**
- `tests/test_week4_golden_closure.py` 执行完整 POST→GET→DB→`/conflicts` 链并断言四者字段级相等。
- `scripts/seed_w5_demo.py` 追踪证实：仅 `offline_raw_agent_outputs` 替换了外部 LLM 调用本身，Week1-4 的抽取/建图/评分/冲突判定全部走生产代码路径，`verify_demo_case` 独立重读 DB 断言硬编码的预期冲突 ID——若真实管道回归，该断言会失败。
- Week 3 手工 oracle 直接调用生产 `score_alpha()`（非重新实现），逐分量精确匹配；Week 4 手工 oracle 同理精确匹配 `detect_alpha_conflicts()`。
- 反例（也一并报告，见 §11）：Week 1 的"部分字段丢失静默通过"和 Week 2 的"免责声明行删除整段"两个缺陷，会在**不产生任何错误信号**的情况下静默传播进下游所有阶段——链路是"连接的"，但连接上传播的数据在特定边界情况下未经校验。

---

## 5. 每周核心文件与真实职责

| Week | 文件 | 真实职责（非注释/文档转述） |
|---|---|---|
| 0 | `tradingagents/graph/setup.py` | 硬编码图拓扑：analyst 循环→bull/bear 辩论(count≥2×max_debate_rounds 终止)→trader→risk 三方循环(count≥3×max_risk_discuss_rounds 终止)→portfolio |
| 0 | `tradingagents/graph/trading_graph.py` | `propagate()` 是唯一正确耦合 checkpoint/memory-log 的公共入口；`_run_graph` 的 debug 分支独立重实现 stream 合并 |
| 1 | `tradingagents_output_writer.py` | `AGENT_OUTPUT_FIELDS` 12 类映射表 + 50000 字符硬截断 + secret allowlist（仅 3 个 key） |
| 1 | `file_store.py` | 唯一路径构造真源（`run_dir_for`/`resolve_output_root`），`atomic_write_text` 用 tmp+`os.replace` |
| 2 | `structured_output_adapter.py::extract_claim_segments` | 行级免责声明过滤 + 无缩写感知的正则句子拆分 |
| 2 | `alpha_mapper.py::map_claim_to_alpha` | 确定性候选生成→确定性 admissibility→可选 LLM 仅在既定候选内 select/defer |
| 2 | `factor_normalizer.py::FACTOR_ALIASES` | "20-case gate"依赖的别名表——git 历史证明晚于测试集提交且含测试集原句短语 |
| 3 | `activation_scorer.py::score_alpha` | 5 分量加权和（0.35/0.20/0.25/0.10/0.10），evidence gate 仅清零 GraphCoherence/Recency 贡献 |
| 3 | `repository.py` | `build_repository_from_env`（只读）与 `build_write_repository_from_env` 物理分离，前者从不调用 `ensure_schema` |
| 4 | `conflict_detector.py::detect_alpha_conflicts` | `min(activation_A,activation_B) × contradiction_weight × evidence_strength`，仅遍历 taxonomy 声明的 pair |
| 4 | `week4_persistence.py` | 每个候选 pair 无论结果都生成一行（admitted/suppressed/rejected 同表） |
| 5 | `repository.py::claim_research_run` | DB UNIQUE(`active_fingerprint`) + IntegrityError 重试，非应用层 check-then-act |
| 5 | `useRunPolling.ts` | 闭包捕获的 `AbortController`（非 ref 读取）保证旧 run_id 的迟到响应天然失效 |
| 6 | `agent_output_reader.py::get_agent_outputs_response` | 先查 DB，仅当 `list_agent_outputs()==[]` 才退回文件——非竞态，是严格 if/else |

---

## 6. 每周逻辑正确性审计（关键发现，完整版见各周独立报告）

### Week 0
`AgentState` 真实字段以 `_log_state`（`trading_graph.py:440-470`）的强制 bracket 访问反推确认，而非文档字符串。三条独立实现的"合并流式 chunk"逻辑（`_run_graph` debug 分支、`cli/main.py`、COMQUTOR streaming runner）在 `stream_mode="values"` 下功能等价但代码手动同步三份——活漂移风险。**CLI 从不调用 `propagate()`**，是独立手写的 stream+merge，跳过 checkpoint 编译、`thread_id` 注入、`_resolve_pending_entries`、`store_decision`。

### Week 1
`_select_source` 在所有候选路径都为空时静默返回 `(None,None)`，`_extract_agent_outputs` 用 `continue` 跳过该 agent 记录——**仅当 12 类全部缺失才触发 `NO_AGENT_OUTPUTS_EXTRACTED` 警告，1–11 类缺失零信号**。截断是硬字符切片，无词/句边界感知，实测在 `"...customer demand for AI accelerators. NVDA revenue guidance wa"` 处腰斩。路径穿越（`../../etc/passwd`、空字节、Windows 绝对路径等）全部被拒绝且零文件系统副作用，活体验证。

### Week 2
`extract_claim_segments` 的免责声明过滤在**原始 markdown 行级**生效：`"AI training demand is accelerating. GPU demand is rising... This is not investment advice."`（三句同段）整体返回 `[]`，两条真实 claim 被一并吞掉。LLM 抽取路径的 `direction` 字段只做取值范围校验，从不与独立重算的 `assertion_status`/`semantic_polarity` 核对一致性——活体构造出 `direction=positive` 与 `assertion_status=negated` 同时持久化的自相矛盾记录（下游 `alpha_mapper.direction_score` 因为重新从文本计算关系而未被欺骗，但持久化 artifact 本身已损坏）。0.35 阈值边界精确验证为 `>=`（inclusive）。LLM 无法创建/恢复 taxonomy 外或候选集外的 Alpha ID，活体两次尝试均被拒绝。**`FACTOR_ALIASES` 表（`factor_normalizer.py:70,85,95,104,106,123-124`）含 7 个与 20-case golden 测试句逐字重叠的短语，git 历史证实该文件（2026-07-10 commit `7b8d3b7`）晚于 golden_cases 文件（2026-07-09 commit `7d6d5c7`）提交——本人独立用 `git log --follow --diff-filter=A` 复核，结论一致。** 与之对照，真实 NVDA 报告的独立 30-claim 诊断集准确率仅 76.7%（strict），且该诊断测试默认不设置 `COMQUTOR_ENFORCE_REAL_NVDA_GATE=1` 时**无论准确率多低都不会失败**。

### Week 3
GraphCoherence = `clamp(valid_edges*15 + alpha_covered_count*10, 0, 100)`；Activation 五分量精确公式见 §7。Evidence gate 仅在 `weighted_evidence_sum==0` 时清零 GraphCoherence/Recency 贡献，其余三分量不受影响——活体验证：关闭 gate 后零证据 Alpha 从 `inactive`(0.0) 跳到 `watch`(35.0)，正是文档警告的"25%+10%=35 地板"。状态带边界 30/50/70/85 全部落在**下段**闭区间（`<=`）。GET graph 路径的只读性用真实 SQLAlchemy `before_cursor_execute` 事件监听抓包证明：仅 1 条 SELECT，零写入/DDL；并对一个从未 provision 过的 SQLite 目标发起调用，确认零文件被创建。

### Week 4
`conflict_score_raw = min(activation_A, activation_B) * contradiction_weight * evidence_strength`——`min()` 确认无误，`min→max` 突变导致 20/292 测试失败。`evidence_strength` 是双边 qualifying-claim match_score 均值的均值，非 sum/max。A102/A304 字面量在生产代码中**仅**出现于（a）taxonomy YAML 各自独立的 conflict_alphas 列表（互不指向对方）、（b）验证专用常量、（c）文档字符串示例——检测器对该组合以最大化合成证据仍主动拒绝为 `PAIR_NOT_DECLARED`。持久化对 admitted/suppressed/rejected 三种结果**同表全量写入**，非只留 admitted。真实 Postgres 上强制第二次 INSERT 失败后查询确认零部分行残留（真回滚，非仅测试断言）。

### Week 5
`claim_research_run` 靠数据库级 `UNIQUE(active_fingerprint)` + `IntegrityError` 重试实现原子 claim，非应用层 check-then-act——本人认可该子代理独立追加的 8 线程真实并发攻击（针对真实 Postgres）复测：始终恰好 1 个 `created`，其余全部 `reused_in_flight`。终态覆盖被两层 DB 级条件 UPDATE 拒绝（`is_allowed_transition` 空转移集 + `progress_percent` 单调 WHERE 子句）。Retry 永远铸造新 `run_id`；`run_id` 显式指定叠加 `force_refresh` 命中同一 fingerprint 会被显式拒绝为 `INVALID_FORCE_REFRESH`。前端四个页面全部以 URL `:runId` 为唯一真源，`useRunPolling` 的 abort 检查捕获的是**闭包内**的 controller 而非 ref，天然避免旧请求迟到覆盖新状态。

### Week 6
`get_agent_outputs_response` 严格先查 DB、非空立即返回，仅 DB 未命中才退回文件——用真实事件监听确认零写入。分数校验对 bool/字符串/NaN/Infinity/越界在**正常写入路径**上全部拒绝（真实 DB CHECK 约束 + Python 层双重校验），但**绕过 `persist_agent_outputs()` 直接写 SQL** 时，`confidence` 的 bool/字符串类型混淆在两种数据库上均可静默通过（NaN/Infinity/越界仍被 CHECK 约束拦截）——此路径当前生产 API 不可达。CI 三个 job（backend-offline/frontend/postgres-integration）逐行读取确认**零 `continue-on-error`、零 `|| true`**。`seed_w5_demo.py` 追踪证实仅替换外部 LLM 调用，Week1-4 全部走生产代码，`verify_demo_case` 独立重读 DB 断言硬编码预期值。

---

## 7. 手工 Oracle（Week 3 / Week 4，不使用生产代码生成期望值）

**Week 3 — Activation, Scenario A101（混合已确认+模糊证据）：**
```
weighted_sum = 1.0*0.9 + 0.65*0.6 + 0.15*1.0*0.5 = 1.365
raw_ME=68.25  raw_AA=66.6667  raw_GC=62.0  raw_RC=66.6667  raw_DS=85.0
total = 23.8875+13.3333+15.5+6.6667+8.5 = 67.8875 → status=active, direction=positive
生产输出：67.8875 / active / positive  ——精确匹配，含 reason_codes
```

**Week 4 — Conflict, Scenario X99/Y99（contradiction_weight=0.75）：**
```
min(72.0, 88.0)=72.0；strength_X99=mean([0.6,0.9])=0.75；strength_Y99=mean([0.4])=0.4
evidence_strength=(0.75+0.4)/2=0.575
score = 72.0*0.75*0.575 = 31.05 → level=medium
生产输出：31.05 / medium ——精确匹配
```
两组场景（各 2 个）在所有分量上与生产代码逐位匹配，**未发现 P0 公式缺陷**。

---

## 8. Test Effectiveness Matrix（代表性核心测试，非全量罗列）

| Week | 测试 | 调用对象 | Mock 层级 | 评级 | 依据 |
|---|---|---|---|---|---|
| 0 | `test_checkpoint_resume.py::test_different_date_starts_fresh` | 真实 checkpointer 原语 | 无 | **STRONG** | 实测能抓住日期隔离突变 |
| 0 | （无对应测试） `setup.py`/`conditional_logic.py` | — | — | **VACUOUS(absent)** | grep 全仓库零命中；突变辩论/风险循环永不终止，103/103 相关测试仍通过 |
| 1 | `test_tradingagents_progress_runner.py` | 真实 streaming runner+writer，仅 mock 付费 LLM 边界 | 恰当 | **STRONG** | 断言进度阶段序列、run_id 重写、checkpoint 生命周期均具体 |
| 2 | `test_alpha_mapper_nvda_real_report.py::test_real_nvda_labeled_claim_accuracy_diagnostic` | 真实 `map_claim_to_alpha` | 无 | **VACUOUS(by default)** | 仅在设置 `COMQUTOR_ENFORCE_REAL_NVDA_GATE=1` 时才断言；默认 pytest 运行无论准确率多低都通过 |
| 2 | `test_week2_semantics.py`（admissibility 边界组） | 真实 `map_claim_to_alpha`+fake classifier | 恰当（仅替换 LLM 网关） | **STRONG** | 越权 Alpha ID、no-match 保护均活体拒绝 |
| 3 | `test_activation_scorer.py`（component breakdown） | 真实 `score_alpha` | 无 | **STRONG，但权重系数突变未被抓住** | `ACTIVATION_WEIGHTS` 突变后 39 个相关测试全部仍通过（权重断言对比的是同一个被突变的全局字典，属重言式） |
| 4 | `test_conflict_detector.py::test_conflict_score_formula_matches_official_definition` | 真实 `detect_alpha_conflicts` | 无 | **STRONG** | 期望值来自测试代码内独立公式字面量，非复制生产输出 |
| 4 | `test_week4_qqq_conflict_sanity.py::test_main_conflict_is_decided_by_formal_sort_rule_not_hardcoded` | 真实生产路径 | 无 | **PARTIAL** | 仅证明非平局场景的排序正确性，未构造真正平局场景 |
| 5 | `test_research_runs_postgres_integration.py::test_concurrent_claims_against_real_postgres_produce_one_created` | 真实 4 线程对真实 Postgres | 无 | **STRONG** | 全套核心测试中证据最强的一条，真并发非模拟 |
| 6 | `test_agent_outputs_api.py`（全文件 684 行） | 真实 `get_agent_outputs_response`，但从未传入 `graph_repository` | 结构性遗漏 | **PARTIAL（对"DB-first"声明具体误导）** | 该文件全部测试只走文件回退分支；即使删除 DB-first 分支代码，该文件本身也会全部照常通过 |
| 6 | `test_capabilities.py` | 真实 `get_capabilities`（LLM 能力表） | — | **MISLEADING（范围标注错误）** | 与 Week 6 的持久化/DB-first/readiness/CI/demo 任一问题均无关，被列入 Week 6 测试清单是上游范围标注错误 |
| cross | `test_ready_requires_database` / `test_post_returns_503_before_claim_*`（6 个测试） | 真实 API+DB | — | **STRONG（逻辑本身），但在含 `.env` 的常规开发环境下会误报失败** | 根因非代码逻辑错误，而是 `resolve_database_url` 优先读取泄漏的环境变量而非测试的 `tmp_path` |

**总体判断：** 该测试体系**并非**普遍虚假或投机取巧——绝大多数核心测试直接调用生产入口、使用具体业务断言，mock 边界克制且恰当（通常仅隔离付费 LLM 调用）。但存在**多处、真实、可复现**的评级为 VACUOUS/PARTIAL/MISLEADING 的测试，集中在：图拓扑执行顺序（Week0，完全空白）、NVDA 独立诊断门禁（Week2，默认无操作）、Activation 权重系数回归（Week3，重言式断言）、冲突平局第 2/3 级（Week4，从未构造）、DB-first 声明的实际覆盖分支（Week6，实测只覆盖文件回退分支）。

---

## 9. Mutation-Style 验证结果（汇总，完整表格见各周独立报告）

| Week | 突变 | 预期失败测试 | 实际结果 |
|---|---|---|---|
| 0 | 辩论/风险循环终止谓词永真 | 无特定测试；全套 103 个相关测试 | **未失败 — TEST GAP** |
| 0 | checkpointer thread_id 忽略日期 | `test_different_date_starts_fresh` | **失败（抓住）** |
| 1 | 从完整 final_state 删除 4/12 类字段 | 无 | **未失败 — TEST GAP**（8/12 静默写入，零警告） |
| 1 | run_id/ticker 含路径穿越/空字节/绝对路径 | `test_file_store.py`/`test_research_input_validation.py` | **全部拒绝（抓住）** |
| 2 | match threshold 0.35→0.05/0.20 | 41 个相关测试 | **仅 1/41 偶然失败 — TEST GAP** |
| 2 | LLM 越权选择 taxonomy 外/候选集外 Alpha | `validate_response` | **拒绝（抓住）** |
| 2 | 绕过 `_llm_relation_is_evidence_backed`（永真） | 无直接测试 | **未失败 — TEST GAP**（伪造 causal edge, confidence=0.99） |
| 3 | 关闭 evidence gate | 2 个测试 | **失败（抓住）**，零证据 Alpha 从 0.0 跳到 35.0 |
| 3 | `ACTIVATION_WEIGHTS` 系数扰动（仍和为 1.0） | 39 个相关测试 | **全部未失败 — TEST GAP** |
| 4 | `min()`→`max()` | 20/292 测试 | **失败（抓住）** |
| 4 | 移除 tie-break 第 2/3 级 | 无 | **0 测试失败 — TEST GAP** |
| 4 | Postgres 第二次 INSERT 强制失败 | 直接查库 | **零部分行 — 真回滚确认** |
| 5 | 8 线程并发 claim 攻击真实 Postgres | 并发测试 | **恰好 1 个 created，无双重 claim** |
| 5 | 终态后迟到 progress/终态转移 | DB 级 guard | **拒绝（抓住）** |
| 5 | 前端旧 run_id 迟到响应覆盖新状态 | 无显式测试（但代码本身正确） | **代码通过；测试套件本身有覆盖缺口** |
| 6 | 直接 SQL 写入 `confidence=True`（bool，SQLite） | 无 | **静默强转为 1.0 — TEST GAP（应用层不可达）** |
| 6 | 直接 SQL 写入 `confidence="0.9"`（字符串，双数据库） | 无 | **两个数据库均静默接受 — TEST GAP（应用层不可达）** |
| 6 | GET agent-outputs 路径尝试 migration/write | 事件监听 | **零写入确认** |
| cross | `clamp_score(nan)` | 无测试引用 `clamp_score`/`clamp_percent` | **返回 nan 未clamp — 确认缺陷** |

---

## 10. 无效、弱或误导性测试清单

1. **VACUOUS** `tests/test_alpha_mapper_nvda_real_report.py::test_real_nvda_labeled_claim_accuracy_diagnostic` — 计算真实准确率但默认不断言，无论多低都通过。
2. **VACUOUS（absent）** Week 0 `setup.py`/`conditional_logic.py` — 全仓库零测试引用，突变永不终止的循环不影响任何测试结果。
3. **重言式（tautological）** `test_activation_scorer.py` 的权重断言 `component["weight"] == ACTIVATION_WEIGHTS[name]` — 与被突变的同一全局对象比较，无法检测系数漂移。
4. **PARTIAL→误导** `test_main_conflict_is_decided_by_formal_sort_rule_not_hardcoded` — 名称暗示证明"非硬编码"，实际只验证非平局场景，平局的第 2/3 级 tie-break 零覆盖。
5. **MISLEADING（范围）** `tests/test_capabilities.py` 被列入 Week 6 测试清单，实际与 Week 6 任何审计问题无关（LLM 能力表，非持久化/CI/demo）。
6. **PARTIAL（对其自身"DB-first"标题声明而言具体误导）** `tests/test_agent_outputs_api.py`（684 行，全仓库最详尽的文件之一）——因从未传入 `graph_repository`，全部测试只走文件回退分支，DB-first 分支的实际覆盖完全来自另一个更小的文件。

---

## 11. 缺失测试清单

- Week 0：`setup.py` 边/节点注册、`conditional_logic.py` 边界值（count 恰好等于/超过 cap）无任何测试。
- Week 0：`cli/main.py::run_analysis`（工具主入口）无任何测试驱动。
- Week 1：`final_state` 部分（非全部）字段缺失场景无测试。
- Week 2：LLM `direction` 与独立重算语义的一致性无测试；`_llm_relation_is_evidence_backed` 无直接单测；claim_id/source_agent_output_id 字段互换无测试。
- Week 3：固定权重系数下的精确 `activation_score` 断言（独立于实时 `ACTIVATION_WEIGHTS` 对象）缺失。
- Week 4：`conflict_score` 相同但 `evidence_strength`/`minimum_activation` 不同的真实平局场景缺失。
- Week 5：`useRunPolling` 对"旧 run_id 迟到响应"的显式对抗测试缺失（代码正确，测试未证明）；`StructureGraphPage.tsx` 零页面级测试（`StructureGraphView.test.tsx` 仅覆盖子组件）。
- Week 6：直接 SQL 类型混淆绕过 `persist_agent_outputs()` 的场景无测试（bool/字符串 confidence）。
- Cross：`clamp_score`/`clamp_percent` 无任何测试引用，NaN/Inf 输入零覆盖。

---

## 12. 确认的代码逻辑缺陷（按严重程度排列，无 P0）

### P1-1 — Week 0：CLI `--checkpoint` 标志对交互式运行路径完全空操作
- **文件/函数**：`cli/main.py:992-1219`（`run_analysis`），对照 `tradingagents/graph/trading_graph.py:337-360`
- **测试**：无（`test_checkpoint_resume.py` 仅测试原语，`tests/` 中零处调用 `run_analysis`）
- **实际问题**：`run_analysis` 直接 `graph.graph.stream(...)`，从不调用 `get_checkpointer`/注入 `thread_id`/重编译 SqliteSaver；`--checkpoint` 标志只写入 `config["checkpoint_enabled"]`，此后无任何代码再读取该 key。
- **为何测试未发现**：唯一驱动 `run_analysis` 的测试为零个。
- **最小复现**：`grep -n "get_checkpointer\|thread_id\|checkpoint_enabled" cli/main.py` 仅命中赋值行与 `--clear-checkpoints` 管理命令。
- **影响范围**：任何期望崩溃后可续跑的 CLI 用户，实际崩溃即全部进度丢失，且此功能被文档字符串明确承诺存在。
- **修复方向**：让 `run_analysis` 复用 `TradingAgentsGraph.propagate()`/`_run_graph()`，或在 CLI 手写流中补齐 checkpoint 编译/`thread_id`/清理三步，并加入断言检查点文件存在的回归测试。

### P1-2 — Week 1：`final_state` 部分字段缺失时静默丢弃，零信号
- **文件/函数**：`comqutor_alpha/adapters/tradingagents_output_writer.py::_extract_agent_outputs`（`:222-249`）
- **测试**：`tests/test_tradingagents_output_writer.py`（仅覆盖"全部缺失"与"单字段+fallback"两极端）
- **实际问题**：`warnings=["NO_AGENT_OUTPUTS_EXTRACTED"]` 仅在 12 类**全部**缺失时触发；删除 4/12 类（含无 fallback 的字段）后写入成功、`metadata.json` 无 `warnings` key，`agents` 列表静默变短。
- **最小复现**：脚本已在子审计中活体执行，删除 `market_report`/`sentiment_report`/`news_report`/`investment_debate_state.bull_history` 后 `raw_agent_outputs.json` 仅 8/12 条记录，exit 0。
- **影响范围**：下游 Week2-4 全部管道对此完全无感知，是整条链路数据完整性的最底层盲点。
- **修复方向**：当 `len(agent_outputs) < len(AGENT_OUTPUT_FIELDS)` 即输出 `MISSING_AGENT_OUTPUTS` 警告并列出缺失类别，向上暴露到 API 响应。

### P1-3 — Week 2：免责声明行级过滤会整段吞掉共享同一行/段的真实 claim
- **文件/函数**：`comqutor_alpha/structure_engine/structured_output_adapter.py:287-289`（`extract_claim_segments`）
- **测试**：`test_long_markdown_report_splits_into_traceable_claims`——仅测试免责声明独占一段的场景
- **实际问题**：`extract_claim_segments("AI training demand is accelerating. GPU demand is rising... This is not investment advice.")` → `[]`，三句（含两条真实 claim）全部丢失。
- **最小复现**：如上，已活体执行确认。
- **影响范围**：整条 Week 2 管道的入口缺陷；LLM 生成报告常见"结尾附加免责声明"模式会静默丢失该段全部信号，无日志。
- **修复方向**：先按句拆分再逐句过滤免责声明，而非按原始 markdown 行过滤。

### P1-4 — Week 2：LLM 抽取路径可持久化 `direction` 与 `assertion_status` 自相矛盾的记录
- **文件/函数**：`structured_output_adapter.py:502-568`（`_validated_llm_segments`）/ `:674`（`adapt_raw_agent_outputs`）
- **测试**：无
- **实际问题**：LLM 提出的 `direction` 只做取值范围校验，从不与独立重算的 `assertion_status`/`semantic_polarity` 核对；活体构造出对 `"There is no evidence that AI demand is increasing..."` 持久化 `direction=positive`、`assertion_status=negated` 同时存在的记录。
- **影响范围**：`alpha_mapper` 因重新计算关系未被欺骗，但持久化 artifact 本身对任何直接读取 `direction` 字段的下游消费者（仪表盘、人工 QA、未来功能）是错误信号源。
- **修复方向**：`semantics.negated`/`.mixed` 为真时强制覆盖 `direction`，不论 `extraction_method`。

### P1-5（政策/流程级，非纯代码）— Week 2："20-case clean gate"依赖的别名表存在测试集后验调参痕迹
- **文件/函数**：`comqutor_alpha/structure_engine/factor_normalizer.py:70,85,95,104,106,123-124`（`FACTOR_ALIASES`）
- **证据**：7 个短语（"priced for perfection"、"reserves rise"、"theme flows"、"wafer orders"、"asp stabilizes"、"token generation"、"copilot usage"）与 20-case golden 测试句逐字重叠；本人独立执行 `git log --follow --diff-filter=A` 确认 `tests/golden_cases/labeled_claims_v1.json` 提交于 2026-07-09 11:04（`7d6d5c7`），`factor_normalizer.py` 提交于次日 2026-07-10 14:53（`7b8d3b7`），二者提交顺序与内容重叠均属实。
- **为何测试未发现**：20-case gate 本身无法侦测支撑它的查找表是否是照着这 20 句反推写出的。
- **影响范围**：直接削弱"20/20，100%"这一旗舰数字作为"真实泛化能力"证据的可信度——与之对照，从未参与调参的真实 NVDA 报告独立诊断集仅 76.7%（strict），且该诊断门禁默认不断言（见 §10 第 1 条）。
- **修复方向**：诚实披露别名表来源，或用一份从未用于编写 `FACTOR_ALIASES` 的留出集重新验证泛化能力；建议将 NVDA 诊断门禁默认启用（哪怕阈值宽松）。

### P2 级（10 项，完整清单见各周报告，此处列最具体证据的 5 项）
| # | Week | 文件/函数 | 问题 |
|---|---|---|---|
| 1 | 3 | `activation_scorer.py:41-47`（`ACTIVATION_WEIGHTS`） | 系数扰动零测试失败（39 个相关测试全部重言式） |
| 2 | 4 | `conflict_detector.py:790-800`（`_conflict_sort_key`） | tie-break 第 2/3 级从未被真实平局场景验证 |
| 3 | 6 | `repository.py::_strict_number` 交互 `schema.py.agent_outputs.confidence` | 绕过应用层写入路径的直接 SQL 可在两种数据库上对 bool/字符串类型混淆静默通过 |
| 4 | cross | `structure_schema.py::clamp_score` vs `graph_schema.py::clamp_percent` | `clamp_score(nan)` 返回 `nan` 未被 clamp（本人独立复现），`clamp_percent(nan)` 正确返回 0.0——同一职责两套独立实现且行为分叉 |
| 5 | 5/6/cross | `comqutor_alpha/storage/db/engine.py:59-61`（`resolve_database_url`） | 环境变量泄漏时，"offline"测试静默改写共享 Postgres，本人两次独立全量运行分别得到 6 与 11 个失败（失败集合真实扩大） |

---

## 13. 重复、冗长与无价值抽象清单

| # | 位置 A | 位置 B | 漂移场景 | 现有测试是否覆盖漂移 | 影响 |
|---|---|---|---|---|---|
| 1 | `structure_schema.py:32-37`（`clamp_score`） | `graph_schema.py:53-70`（`clamp_percent`） | 已证实行为分叉（NaN），`clamp_score` 结果经 `structure_extractor.py:199` 写入每条 edge 的 `confidence` 字段，直到 Week3/4 持久化层的 `math.isfinite` 才被拦截，表现为不透明的 `AGENT_OUTPUTS_DB_WRITE_FAILED`，而非在 Week2 源头报错 | 否——两个函数均无任何测试引用 | 正确性（已证实 bug）+ 可维护性 |
| 2 | `alpha_taxonomy_v1.yaml`（`conflict_alphas[].contradiction_weight`） | `alpha_loader.py:41-48`（`MANDATORY_CONFLICT_WEIGHTS`） | 自校验型重复（`validate_taxonomy` 以 0.05 容差强制两者一致），但仍需双文件同步编辑；0.05 容差内的"合法"修改会静默产生两处不一致但不报错 | 是（`validate_taxonomy` 每次加载运行） | 仅可维护性，非实时正确性风险 |
| 3 | `routes_research.py:517`（写 `structured_agent_outputs.json` 并丢弃返回值） | `routes_research.py:524-526`（同一函数内立即重新读回同一文件） | 纯磁盘 I/O 往返churn，无审计/恢复价值，已追踪确认中间无其他消费者 | N/A（非正确性问题） | 仅性能，当前规模下影响很小 |
| 4 | `repository.py:97-159`（`_NAMED_SCORE_RANGES`） | `agent_output_reader.py:135-208`（`_validate_confidence` 等） | 有意的纵深防御式重复（文档已声明"非替代关系"），但数值区间字面量（如 `0.0-1.0`）在两处各写一份，业务决策改动区间需双改 | 否——无测试断言两套区间表相等 | 潜在维护陷阱，当前数值一致 |
| 5 | `routes_research.py` Week3/4 DB 写入包裹在 `contextlib.suppress(Exception)`（`:634,647`） | 文件状态标记（`WEEK3_PIPELINE_STATUS_ARTIFACT_FILENAME`）独立作为"就绪"判断真源 | 若 DB 写入被静默吞掉，文件标记仍显示 `success`，但 DB 支撑的 `GET /graph`/`/agent-outputs` 可能返回空/不可用——文件说"就绪"，DB 说"未就绪"，且未发现任何自动对账/修复任务 | 未检查到专门测试 | 正确性风险（数据源不一致），但设计上是有意为之（DB 失败不应拖垮已文件持久化的阶段），需要明确对账策略 |

**未发现的**：伪抽象（结构上分离但语义重复的类/模块，需要双改才能保持行为一致，本报告未发现符合此定义的确凿案例）、废弃路径参与生产调用（legacy 文件回退路径经确认非死代码，被真实 DB-miss 测试覆盖）、以及 fixture-specific 生产分支（`grep -rn "if ticker ==\|if run_id =="`全仓库零命中；生产代码中唯一的 "NVDA" 字面量是合法的领域词表常量，非条件分支）。

---

## 14. DB / File Source-of-Truth 风险

1. **已确认的漂移窗口**（§13 #5）：Week3/4 的 DB 写入失败被 `contextlib.suppress` 吞掉后，文件状态标记与 DB 实际状态可以不一致，且该不一致目前只能靠"下次成功重试覆盖标记文件"来自愈，无主动对账。
2. **Week 6 DB-first 读取本身经证实正确**：`get_agent_outputs_response` 严格 if/else，非竞态；legacy 文件回退路径非死代码（被 `seed_w5_demo.py` 的启动修复逻辑间接使用），但也非当前正常写入路径下会触发的分支——它是一个真实存在、有测试、但生产环境中日益边缘化的兼容层。
3. **直接 SQL 绕过应用层写入路径的类型混淆**（§12 P2#3）——当前无生产 API 可达，但若未来出现管理脚本/迁移工具直接写库，此为真实类型安全缺口。

---

## 15. Concurrency / Lifecycle 风险

**总体：经对抗验证为稳固。** `claim_research_run` 的原子性由数据库 `UNIQUE` 约束 + `IntegrityError` 驱动重试保证，8 线程真实并发攻击零双重 claim。终态转移与进度回退均被 DB 级条件更新拒绝，非应用层竞态窗口。Retry 恒定铸造新 `run_id`。SIGTERM/超时/服务重启/服务器关闭/真实算法错误分别有独立、API 可见的 `error_code`，仅在"管道内部抛出未分类异常"这一种情况下统一收敛为 `INTERNAL_ERROR`（P3，非缺陷，是有意的安全兜底）。

**唯一需要关注的**：`resolve_database_url` 的环境变量优先级设计（生产环境合理，测试环境危险）——这不是并发缺陷，而是一个测试隔离缺陷，但其症状（"重复运行产生不同失败集合"）表面上很容易被误诊为并发 bug；本报告已明确根因排除并发因素。

---

## 16. Frontend State-Machine 风险

**总体：经对抗验证为稳固。** 四个页面统一以 URL `:runId` 为真源，无组件状态/闭包持有独立副本。Refresh 触发真实重新拉取，非陈旧/空白渲染。`completed`/`partial`/`failed` 有明确区分渲染路径，`failed` 状态下**从不尝试**加载结果数据（`shouldLoadResult = terminal && currentStatus !== "failed"`），结构性杜绝"跳转到损坏结果页"。`useRunPolling` 的 abort 检查绑定闭包内的 controller 而非可变 ref，天然避免旧 run_id 迟到响应覆盖新状态（本人认可子代理构造的对抗性延迟 Promise 测试，验证后即删除，未提交）。

**唯一确认缺口**：`StructureGraphPage.tsx` 零页面级测试（`StructureGraphView.test.tsx` 仅覆盖子组件），若 `useGraphAndConflicts` 的 fetch/abort/错误分支回归，现有测试套件不会发现。

---

## 17. Security 与 Secret-Handling 风险

- `grep -rn "logger\.\|logging\.\|print(" comqutor_alpha scripts | grep -i "traceback\|exc_info\|dsn\|password\|api_key\|token"` 全仓库**零命中**；无 `exc_info=True`/`logger.exception(...)`，异常均以固定 `reason_code`/`type(exc).__name__` 记录。
- Path traversal（run_id/ticker 含 `../`、空字节、绝对路径、shell 元字符）在 Week1 全部活体验证拒绝，零文件系统副作用。
- Secret allowlist（`SAFE_CONFIG_KEYS`，仅 3 个 key）活体验证：伪造 `ANTHROPIC_API_KEY` 形态字符串放入 config 的 5 种变体，全部未出现在任何持久化 artifact 中。
- HTTP 层 `ResearchRequest` 模型物理上不包含 `provider`/`model`/`config`/`api_key` 字段，客户端注入的越权字段被 Pydantic 静默丢弃——活体 HTTP POST 验证。
- 客户端不能覆盖服务端固定 Research Profile（活体验证，包括 `allow_real_tradingagents_run=True` 越权尝试）。
- 未发现任何 DSN/密钥/完整 traceback 出现在 API 响应或日志中的证据。

**唯一低严重性缺口**：直接 SQL 类型混淆绕过应用层校验（§12 P2#3），当前无生产可达路径。

---

## 18. 用户应该亲自阅读的文件（按优先级排序）

1. `comqutor_alpha/structure_engine/structured_output_adapter.py:247-328,502-568`（Week2 claim 拆分与 LLM direction 一致性——两个 P1 缺陷所在）
2. `comqutor_alpha/structure_engine/factor_normalizer.py` 全文 + `git log` 对照 `tests/golden_cases/labeled_claims_v1.json`（判断"20/20 gate"数字的可信边界，这是本次审计中最需要项目负责人亲自形成判断的一项，因为它涉及"这个别名表的调参方式是否可接受"这一产品/工程判断，而非纯代码正确性问题）
3. `cli/main.py:992-1219`（`run_analysis`）对照 `tradingagents/graph/trading_graph.py:321-436`（`propagate`/`_run_graph`）——确认是否要修复 CLI checkpoint 或明确标注其为已知限制
4. `comqutor_alpha/adapters/tradingagents_output_writer.py:222-249`（部分字段丢失静默通过，整条管道的地基缺陷）
5. `comqutor_alpha/storage/db/engine.py:40-65`（`resolve_database_url`）与 `tests/conftest.py`——决定是否要加一个 `autouse` fixture 隔离测试环境，这直接关系到本地开发时"pytest 全绿"是否可信
6. `comqutor_alpha/api/routes_research.py:325-404,617-663`（`build_research_response` 状态降级逻辑 + Week3/4 的 `contextlib.suppress` 包裹的 DB 写入）——理解 file/DB 双真源在 DB 写失败时的实际漂移窗口
7. `tradingagents/graph/setup.py` + `conditional_logic.py`（零测试覆盖的图拓扑与循环终止逻辑）

---

## 19. 建议重写/新增的测试（按优先级排序）

1. **P1** 新增：`tests/test_structured_output_adapter.py` 中构造"免责声明与真实 claim 同段"的用例（复现 §12 P1-3）
2. **P1** 新增：`tests/test_structured_output_adapter.py`/`test_week2_llm.py` 中构造 LLM `direction` 与语义矛盾的用例（复现 §12 P1-4）
3. **P1** 新增：`tests/test_tradingagents_output_writer.py` 中构造"1–11 类缺失（非全部）"的用例，断言存在缺失警告（复现 §12 P1-2）
4. **P1** 新增：`cli/main.py::run_analysis` 的一个最小端到端测试（伪 LLM/伪图），断言 `--checkpoint` 时确实创建/使用 SqliteSaver
5. **P2** 修改：`tests/conftest.py` 增加 `autouse` fixture，对非 `integration` 标记的测试 `monkeypatch.delenv("COMQUTOR_DATABASE_URL", raising=False)`——这是让本地"pytest 全绿"重新变得可信的最小改动
6. **P2** 新增：`tests/test_activation_scorer.py` 中一条不依赖 `ACTIVATION_WEIGHTS` 实时对象、使用字面量系数手工计算并断言 `activation_score` 的测试
7. **P2** 新增：`tests/test_conflict_detector.py` 中构造 `conflict_score` 相等但 `evidence_strength`/`minimum_activation` 不等的真实平局场景
8. **P2** 新增：`tests/test_structure_schema.py` + `tests/test_graph_builder.py` 中为 `clamp_score`/`clamp_percent` 补 NaN/Inf 边界测试（会立即暴露 §12 P2#4）
9. **P2** 新增：`frontend/src/pages/StructureGraphPage.test.tsx`，参照 `ResearchRunPage.test.tsx` 模式
10. **P3** 建议：将 `tests/test_alpha_mapper_nvda_real_report.py` 的诊断门禁默认启用（哪怕设一个宽松阈值如 `allowed >= 0.65`），而非默认无操作

---

## 20. 未验证事项与原因

- **Week 3 的 PostgreSQL 集成套件在该子审计的单次独立运行中显示 5 skipped**（非因代码问题，是因为该子代理未能在自己的会话里让 `.env` 生效，且被权限系统正确阻止了 `source .env`）——本人已在主审计会话中独立确认：单独运行确实会 skip（环境副作用链路问题，见 §2），但同一测试文件在包含其他会导入 `tradingagents` 包的测试一起跑、或手动 `source .env` 后，均已被其他子审计（Week4/Week5/Week6/cross-cutting）证实可以对真实 Postgres 跑通并通过。**净结论：Week 3 的 Postgres 集成测试设计本身健全（`_FAIL_UNREACHABLE`/`_FAIL_NOT_POSTGRES` 等失败即真失败，非静默 skip 伪装通过），只是本次审计任务简报中"pytest 自动读取 .env"的前提假设对本仓库不成立，这一点已作为环境发现记录（§2），不构成对 Week 3 代码正确性的否定。**
- **Playwright/Vitest/前端构建**：均已实际运行且通过（90/90 单测、7/7 e2e、typecheck/build 干净），但 e2e 覆盖的用户旅程数量有限（7 条），未穷尽所有边界 UI 状态组合。
- **远程 GitHub Actions 的真实运行**：本次审计只能验证 `.github/workflows/ci.yml` 的 YAML 内容和本地等价复现，无法从沙箱验证远程 CI 实际运行结果；文档中"remote run not performed"的表述是诚实的，未被本审计推翻也未被证实。
- **付费 LLM/真实市场数据路径**：按任务要求全程未调用，因此"真实 TradingAgents 多智能体执行"的端到端正确性（区别于其管道接线正确性）不在本次审计验证范围内，这是任务边界的主动排除而非审计遗漏。

---

## Final Verdict

```
Week 0–6 Production Logic:        PARTIAL
Week 0–6 Test Suite Effectiveness: MIXED
Vacuous or Misleading Tests:       FOUND
Critical Logic Defects:            FOUND   (7× P1, 0× P0)
Redundant or Low-Value Code:       FOUND
Full Vertical Pipeline:            VERIFIED
Safe to Begin UI Redesign:         YES_WITH_BLOCKERS
```

**YES_WITH_BLOCKERS 的具体阻塞项**（建议在或之前修复，不必阻塞纯前端视觉重构本身，但应在下一次数据正确性相关的发布前解决）：
1. Week 2 P1-3/P1-4（claim 丢失 + direction 自相矛盾）——直接影响 UI 将展示的数据质量
2. Week 1 P1-2（部分字段静默丢失）——同上，是数据完整性的地基问题
3. Week 0 P1-1（CLI checkpoint 空操作）——不影响 Web UI，但若 UI 重构范围涉及运维/CLI 提示文案，需同步澄清
4. `tests/conftest.py` 的 DB 环境隔离修复——不修复的话，任何后续对 UI 依赖的 API 契约做验证性重跑测试都可能得到虚假失败，拖慢重构节奏

完整支撑证据（含全部 mutation 脚本路径、逐条测试评级、完整命令记录）见 9 份独立子审计报告：`/private/tmp/claude-501/-Users-xiangmao-COMQUTOR-Alpha-/15b53a10-aac2-49e2-ab0e-6e4580d9d8ed/scratchpad/audit_week{0..6}.md`、`audit_crosscutting.md`。
