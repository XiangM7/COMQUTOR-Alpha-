# W5 Local Demo Runbook

## 启动与关闭

在仓库根目录运行：`./scripts/run_w5_demo.sh`

脚本会在 `.demo/w5/` 中创建隔离的 SQLite 数据库和 run artifacts，验证
NVDA、QQQ cache 后启动 API 与前端。默认页面是
`http://127.0.0.1:5175/research`，API 是 `http://127.0.0.1:8001`。

按 `Ctrl+C` 关闭脚本启动的 API 和前端。脚本不会终止启动前已经存在的
进程；默认端口被占用时会安全退出。需要避开已有服务时，可显式指定本地
端口：`COMQUTOR_API_PORT=18001 COMQUTOR_FRONTEND_PORT=15173 ./scripts/run_w5_demo.sh`

## Demo 输入

NVDA：

- Ticker：`NVDA`
- Analysis date：`2026-06-30`
- Analysts：Market、News、Fundamentals、Sentiment

QQQ：

- Ticker：`QQQ`
- Analysis date：`2026-06-30`
- Analysts：Market、News、Fundamentals、Sentiment

不要启用 Force refresh。两次提交都应复用预先生成的 completed cache。
MSFT 当前是 `BLOCKED_BY_SPEC_CONFLICT`，不用于成功演示。

## 3–5 分钟演示顺序

1. **Research**：提交 NVDA，说明 agent evidence 被转换为 structured claims；
   展示 completed 状态、canonical summary 和可追溯的 analyst findings。
2. **Structure Graph**：展示 Alpha activation、dominant structures，以及可点击、
   可键盘选择的结构节点。
3. **Conflict Radar**：展示 A101 与 A304 的 bull/bear structure conflict，继续
   展示两侧 claim 和 evidence traceability。
4. 返回 Research，提交 QQQ；展示 A001/A003 与 A501 的 admitted conflicts，
   强调 main conflict 来自后端 arbitration。

COMQUTOR 不只是生成一段摘要，而是把证据映射成结构、Activation 和
Conflict，并保留 claim-level traceability。

## Demo 边界

- Demo 使用批准的 deterministic offline fixtures，不是实时市场研究。
- Demo 不调用真实 TradingAgents、LLM、行情、新闻或付费 Provider。
- 页面不收集 API key、provider、model 或运行配置。
- 输出不构成投资建议，也不保证收益。
- 当前没有 public deployment、authentication、authorization 或 tenant ownership。
