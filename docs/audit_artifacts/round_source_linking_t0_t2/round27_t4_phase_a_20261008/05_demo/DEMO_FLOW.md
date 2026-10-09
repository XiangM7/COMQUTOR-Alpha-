# E. 演示录制：流程与冻结部分的走查证据（T4 Phase A）

## 录制器

`05_demo/t4_demo_recorder.mjs`（新写，旧的 `scripts/w6_demo_recorder.mjs` 未改动）。

- **只走现有页面**：使用系统 Google Chrome（playwright-core 指定 `executablePath`），无头模式。
- **不提交研究是强制约束，不只是约定：**
  - 发往 API 的所有非 GET 请求都被拦截并记录，包括 POST /api/research、复核提交和 replay；
  - 发往非回环主机的请求一律拦截；
  - 录制器不在 Ticker 输入框里打字，也不点 "Start research"；
  - 结束时只要拦截记录不为空，退出码就是 3。
- **视频**：Playwright 自带的录像需要另外下载一个 ffmpeg 构建，本轮不做外部下载。改用 Chrome 自己的 DevTools screencast 帧，按每帧的时间戳，用本机 `/opt/homebrew/bin/ffmpeg` 合成 H.264 MP4。
- **画面底部的深色条是录制标注**（标签、场景、run_id、代码身份、数据库），不是产品界面。

命令：
```
node 05_demo/t4_demo_recorder.mjs --base http://127.0.0.1:5177 --api http://127.0.0.1:8002 --out 05_demo/recording_frozen --label FROZEN
```

## 冻结部分：已录（`recording_frozen/`）

- 实例：T4 verify 模式（8002，真实执行关闭，PostgreSQL `comqutor_alpha_t4_test`），前端 5177。
- 代码身份：`7a9aefa+uncommitted`，tracked diff `b5e91198…`，untracked `a61cb62c…`。这是最终代码，与 Fresh 实例冻结时相同，见 `04_fresh_prep/frozen_config.json`。
- 结果：12 个场景全部完成；拦截的非 GET 请求 0 次，研究提交尝试 0 次。
- 视频 `t4_demo_frozen.mp4`，约 160 秒，1413 帧。
- 截图在 `screens/`，逐场景记录在 `scenes.json`。

| 场景 | 内容 | 对应要求 |
|---|---|---|
| 01_instance | Research 页的状态行显示 PostgreSQL 库名和代码身份 | 代码版本、实例身份 |
| 02_history_reopen | Recent runs（从 PostgreSQL 读取）→ 重开 AMD 重评 run | 历史重开 |
| 03_research_summary | partial run：分类不完整（975 次中 1 次失败），结论没有被夸大 | 部分完成 |
| 04_key_conclusion_source | 关键结论 → 四项独立检查 → 依据的已保存来源片段（市场快照中 RSI 72.95：保存值、claim 中写法、核验方法和理由、在报告中的位置） | 关键结论 → 来源片段 |
| 05_structure_graph | Structure Graph：因子节点、分数、节点详情 | Structure Graph |
| 06_calculation_basis | A301 Revenue Expansion → Evidence → View basis：已保存的 Total Revenue 行、保存值与 claim 写法、核验依据 | 计算依据 |
| 07_conflict_radar | Conflict Radar：无准入的主冲突；候选和被拒的冲突对及原因 | 无主冲突 |
| 08_sndk_no_main_conflict | SNDK 历史 run（冻结）：无主冲突，已验证证据不足 | 历史无主冲突 |
| 09_nvda_frozen_recompute | NVDA 冻结输入重算（10-02 agent 输出；verify 实例上语义 LLM 关闭）：证据不足 | 冻结标签 |
| 10_simulated_empty_input | **模拟**：有意提交一份空 agent 输出 → 0 条 claim，证据不足（状态为 completed，见发现） | 证据不足 |
| 11_simulated_failure | **模拟**失败：运行中有意重启实例 → failed，`SERVER_SHUTDOWN`，没有续跑 | 失败 |
| 12_export | Export research：页面下载的 ZIP | Export |

Export 核对（`recording_frozen/export_check.json`）：
- ZIP 共 17 个条目，与 run 目录逐字节一致；
- ZIP 的 sha256 `2836e0ca…`，与 PostgreSQL 验证中 API 导出的哈希相同。

## 录制中发现、但不属于产品缺陷的问题

- "View basis" 第一次看起来"点开后又自己关上"。原因是录制器的定位器：点开后按钮文字变成 "Hide basis"，`View basis` 定位器重新匹配到下一条尚未展开的按钮。改成定位 "Hide basis" 后正常，产品没有问题。
- AMD 页面完全加载约需 8 秒（agent-outputs 接口约 6 秒），录制器因此加长了等待。

## Fresh 部分：负责人点击之后才录

- 本轮没有录 Fresh 部分，也不会代为提交。
- 负责人在 `http://127.0.0.1:5177/research` 亲自点击 Start Research 并告知"已启动"之后，我才会做下面三件事，同样只做 GET，不提交：
  1. 确认 run_id；
  2. 用同一个录制器、换 `--label FRESH` 和该 run 的 id，走查处理页、结果页、Structure Graph、Conflict Radar、Export；
  3. 如果是 partial 或 failed，如实录下状态。
