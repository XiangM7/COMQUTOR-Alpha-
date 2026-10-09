# B. Replay 测试与 ESLint 说明（T4 Phase A）

本轮**没有修改** Replay 测试、Replay 代码或这两个前端文件；下面说明它们为什么现在通过，以及证据缺口在哪里。

## 1. `test_replay_conflict_does_not_get_run_id_mismatch`

### 现状
- 当前工作区版本：在本轮受影响测试组中通过（`test_evidence/unit_run1_junit.xml`，0.14 s；最终组见 `unit_junit.xml`）。
- 测试位置：`tests/test_artifact_export_and_api.py`。该文件的最后一次提交是 `9f9b681`（2026-08-19）。这个测试函数在工作区中被改写，改写内容未提交，函数自带的说明注明是 2026-09-29。

### 两个版本的断言

| 版本 | 断言 | 在同一次 Replay 结果上 |
|---|---|---|
| HEAD `7a9aefa` | ① 所有候选对都没有 `RUN_ID_MISMATCH`；② `admitted_count > 0` | ① 成立；**② 不成立，测试失败** |
| 工作区（09-29 改写） | ① 同上；全部 claim 的 `match_status` 都是 `unavailable`；候选对仍然被评估；`admitted_count == 0` | 全部成立 |

复现：`tools/reproduce_replay_test.py` 在网络陷阱下运行，外网尝试 0 次，结果在 `replay_test_reproduction.json`。
- 用测试夹具同一条 Replay：NVDA 源 run `e434f80b`，写入新的临时目录；
- 源 run 前后哈希相同；
- 652 条 claim 全部是 `unavailable`；
- 8 个候选评估，`RUN_ID_MISMATCH` 0 次，admitted 0；
- 拒绝原因：`DIRECTION_ROLE_UNRESOLVED`、`MISSING_LEFT_EVIDENCE`、`MISSING_RIGHT_EVIDENCE`、`ZERO_EVIDENCE_STRENGTH`。

### 根因
测试名针对的是**身份问题**：Replay 自己的 run_id 与源 run 不同时，是否因此被判 `RUN_ID_MISMATCH`。
- **身份问题**：在 Sprint 1 的 Replay Identity Correction 中修复（replay_run_id 在 `detect_alpha_conflicts` 之前就改写）。证据 `docs/audit_artifacts/replay_identity_consistency.json`（2026-08-04）：7 个案例 `RUN_ID_MISMATCH` 都是 0，当时 NVDA 案例 admitted 3。
- **`admitted_count > 0` 后来失效**：原因是之后的 "Pure-LLM Alpha Production Boundary Hardening"。Architecture Replay 不带 LLM 网关（`llm_gateway=None`），每条 claim 的 Alpha 语义状态都是 UNAVAILABLE；不会伪造 NONE，也不会让确定性打分的首选冒充语义判断。因此没有 Alpha 能变成 active，也不可能有冲突被准入。在这种 Replay 模式（`RAW_REBUILD_DIAGNOSTIC`）下，0 是结构上必然的结果。
- **修复范围**：只改测试，不改产品代码（`test_artifact_export_and_api_diff_vs_HEAD.diff`）。
  - 身份断言原样保留；
  - 计数断言改为 `== 0`，并逐条检查 `match_status`，确认 0 的原因确实是语义状态不可用，而不是只信任一个计数。

### 缺失的证据（如实标注）
- **没有修复前的原始 pytest 日志**：既没有 `RUN_ID_MISMATCH` 修复前那次失败的日志，也没有 09-29 改写前 `admitted_count > 0` 失败的日志。
- 现有的只是文字记录：
  - 测试函数自带的说明；
  - `replay/pipeline.py` 的模块说明；
  - Sprint 1 的 `replay_identity_consistency.json`。
- 本轮的复现在当前代码上执行旧断言。它证明旧断言现在会失败、失败点在哪里，**不能替代**当年的原始日志。

## 2. 两项 ESLint

John 列的问题（在 HEAD 上实测，`eslint_head_versions.txt`）：

| 文件（HEAD 版本） | 问题 | 级别 | ESLint 退出码 |
|---|---|---|---|
| `src/components/ResearchForm.test.tsx:185` | `@typescript-eslint/no-unused-expressions` | error | 1 |
| `src/pages/StructureGraphPage.tsx:39`、`:51` | `react-refresh/only-export-components`：页面文件同时导出常量和函数 | warning ×2 | 0 |

### 为什么现在没有了
两个文件都已在**工作区中被改写**。这是界面改版工作留下的未提交改动，不是本轮所改。差异见 `eslint_two_files_diff_vs_HEAD.diff`。
- `ResearchForm.test.tsx`：表单改为只有一个 ticker 输入。原来的日期和分析师测试被整体替换，第 185 行的无效表达式随之消失。新测试断言：只有 1 个输入；输入 ticker 前 Start research 不可用。
- `StructureGraphPage.tsx`：`ALPHA_LEVEL_BUCKETS`、`bucketForAlpha`、`AlphaLevelBucket` 移到 `src/utils/alphaLevelBucketing.ts`，页面文件只导出组件，两条警告随之消失。这属于结构上的修正，不是用 eslint-disable 压掉警告。

### 当前输出
- `npx eslint src e2e`：退出码 0（`eslint_current_src_e2e.txt`；本轮最终复跑见 `test_evidence/frontend_eslint.log`，退出码 0）。

### 相关测试（只跑相关的）
- vitest：`serverStatus.test.ts`、`App.test.tsx`、`ResearchPage.test.tsx`、`adapters.test.ts`，4 个文件 63 个测试全部通过（`test_evidence/frontend_vitest_affected.log`）；
- TypeScript 类型检查：退出码 0（`frontend_typecheck.log`）。

### 缺口
- 这两个文件的改写人和改写时间，没有提交记录可查（未提交）。
- ESLint 对改写前版本的输出是本轮在 HEAD 版本上重新跑出来的，不是当时保存的输出。
