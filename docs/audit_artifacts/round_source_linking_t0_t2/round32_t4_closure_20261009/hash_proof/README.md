# 受保护文件前后哈希（Round 32）

**快照**：
- `state_before.json`：本轮开始前（2026-10-09T19:0xZ）。
- `state_after.json`：解压验证时，与 `state_before.json` 比较。

**比较结果**：1481 个受保护文件中 1479 个不变，缺失 0、新增 0。不变的部分包括：
- 两次 Fresh 的 run 目录；
- Round 27–31 的全部材料，含 Round 31 交付包和 ZIP，以及 Round 29 / 30 的旧 Export ZIP；
- 历史 run 和 T3 执行。

**有变化的 2 个文件**都是仍在运行的服务（8002 / 5177）自己追加的日志，不是本轮写入的：

| 文件 | 追加了什么 | 原因 |
|---|---|---|
| `round27_t4_phase_a_20261008/05_demo/t4_web_5177.log`（5177 的 Vite 开发服务日志） | `hmr update` 行 | 本轮修改了 `frontend/src` 里的文件，5177 的 Vite 监视工作区，记录热更新。**副作用**：之后打开 5177 页面看到的是最终前端代码；8002 是 Fresh 代码，响应里没有 `stage_disclosure`，所以新面板在那里不显示任何内容 |
| `round28_t4_launch_protection_20261008/04_refreeze/instance_fresh_start.log`（8002 的访问日志） | 只读 GET：`/ready`、`/api/research?limit=10`、第二次 Fresh 的详情 / 状态 / 证据追溯、`t4-simulated-interrupted-20261008` 的状态 | 来自打开 5177 页面的另一个客户端，不是本轮的录屏或脚本 |

关于 8002 的来源，核对过三点：
- 本轮录屏只访问 8005，录到的证据追溯 claim 是 final_trade_decision 7 和 16、trader_investment_plan 5；8002 日志里的 final_trade_decision claim 15 不在其中；
- 8002 日志里始终只有 2 个 `POST /api/research`，都是负责人发起的两次 Fresh；
- 8002 期间没有新的研究任务。

本轮没有停止、重启或改配置 8000、8001、8002、5175、5176、5177。
