# 当前系统状态记录

## 1. 项目仓库信息

项目仓库：

https://github.com/XiangM7/COMQUTOR-Alpha-

当前工作分支：

comqutor-structure-layer

当前基础代码版本：

85946c2f60768ab2dae23a5a36cd927662feef94

说明：

这个分支是基于 TradingAgents fork 后建立的结构层开发分支。当前阶段还没有正式改动 TradingAgents 的核心逻辑，主要目的是先记录系统能否正常启动、如何运行、输出结果在哪里，以及后续接入 COMQUTOR Structure Intelligence Engine 前的基础状态。

---

## 2. Python 运行环境

当前使用的 Python 版本：

Python 3.12.13

当前使用的 Python 路径：

/opt/miniconda3/envs/tradingagents/bin/python

当前使用的 Conda 环境：

tradingagents

说明：

本项目当前是在 `tradingagents` 这个 Conda 环境里运行的。系统自带的全局 `python3` 不是主要运行环境，里面不一定安装了本项目需要的全部依赖。

---

## 3. 依赖情况

项目依赖主要写在 `pyproject.toml` 里。

主要依赖包括：

- tradingagents==0.3.0
- python>=3.10
- langchain-core>=0.3.81
- langchain-anthropic>=0.3.15
- langchain-openai>=0.3.23
- langgraph>=0.4.8
- pandas>=2.3.0
- python-dotenv>=1.0.0
- questionary>=2.1.0
- rich>=14.0.0
- typer>=0.21.0
- stockstats>=0.6.5
- yfinance>=1.4.1

当前环境的依赖快照记录在：

docs/requirements_baseline.txt

说明：

`requirements_baseline.txt` 用来记录当前能跑通 TradingAgents 时的 Python 包状态，方便以后如果环境坏了，可以对照恢复。

---

## 4. LLM 配置情况

当前本地使用的是 Anthropic / Claude API。

本地 `.env` 文件中配置了：

ANTHROPIC_API_KEY

重要说明：

`.env` 文件里包含 API Key，不能提交到 GitHub。这个文件必须保留在本地，不能上传。

当前注意点：

TradingAgents 默认可能会使用 OpenAI 配置。如果要使用 Claude，需要在 CLI 运行时手动选择 Anthropic，或者在 `.env` 里明确配置：

ANTHROPIC_API_KEY=your_key_here
TRADINGAGENTS_LLM_PROVIDER=anthropic

可选配置：

TRADINGAGENTS_OUTPUT_LANGUAGE=Chinese
TRADINGAGENTS_MAX_DEBATE_ROUNDS=1
TRADINGAGENTS_MAX_RISK_ROUNDS=1

说明：

目前这一步的重点不是优化模型效果，而是确认 TradingAgents 能够在当前环境中正常调用 LLM，并生成完整股票分析报告。

---

## 5. 运行命令

进入项目目录后，先激活环境：

conda activate tradingagents

启动 TradingAgents 交互式命令：

tradingagents

也可以使用源码方式启动：

python -m cli.main

说明：

`tradingagents` 是主要启动方式。运行后，系统会进入交互式界面，让用户选择股票代码、分析师类型、模型供应商、推理强度等参数。

---

## 6. 已测试股票

| 股票代码 | 分析日期 | 使用的分析模块 | 最终动作 | 报告目录 |
|---|---|---|---|---|
| NVDA | 2026-06-30 | market, news | BUY | reports/NVDA_20260630_142758/ |
| AAPL | 2026-06-30 | market, social, news, fundamentals | HOLD | reports/AAPL_20260630_154758/ |

说明：

这两个报告是当前 baseline 阶段保留下来的原始 TradingAgents 输出文件。它们被放在同一个 `reports/` 文件夹下面，方便后续查看和作为结构层输入样例。

---

## 7. 报告输出位置

NVDA 完整报告：

reports/NVDA_20260630_142758/complete_report.md

NVDA 分阶段报告：

reports/NVDA_20260630_142758/1_analysts/
reports/NVDA_20260630_142758/2_research/
reports/NVDA_20260630_142758/3_trading/
reports/NVDA_20260630_142758/4_risk/
reports/NVDA_20260630_142758/5_portfolio/

AAPL 完整报告：

reports/AAPL_20260630_154758/complete_report.md

AAPL 分阶段报告：

reports/AAPL_20260630_154758/1_analysts/
reports/AAPL_20260630_154758/2_research/
reports/AAPL_20260630_154758/3_trading/
reports/AAPL_20260630_154758/4_risk/
reports/AAPL_20260630_154758/5_portfolio/


说明：

`reports/` 里的内容是已经整理好的股票分析报告，可以在 GitHub 分支中查看。

`.tradingagents/logs/` 是本机运行日志，主要用于本地排查问题，不是主要交付内容。

---

## 8. 当前已知问题
1. TradingAgents 需要连接 LLM API，例如 Anthropic / Claude 或 OpenAI。
2. 使用 LLM API 会产生费用，所以测试时需要控制分析师数量和推理强度。
3. `.env` 文件包含 API Key，不能上传到 GitHub。
4. TradingAgents 默认配置可能会选择 OpenAI，如果使用 Claude，需要明确选择 Anthropic。
5. FRED 宏观数据需要额外配置 `FRED_API_KEY`，目前不是必须项。
6. Reddit 数据源有时会出现 HTTP 429 Too Many Requests，说明请求过多或被限流。
7. High reasoning effort 成本更高、速度更慢，baseline 测试阶段建议使用 Low 或 Medium。
8. 当前报告是 TradingAgents 的原始输出，后续 Structure Intelligence Engine 需要从这些报告中提取结构化信息。
---

## 9. 当前阶段结论

当前 `comqutor-structure-layer` 分支已经完成 TradingAgents baseline 的基础记录。

目前已经确认：

1. 项目可以在本地 Conda 环境中启动。
2. LLM provider 可以通过 Anthropic / Claude 调用。
3. NVDA 和 AAPL 已经完成测试运行。
4. 两个股票的原始报告已经统一放在 `reports/` 文件夹下。
5. 当前系统状态和启动方式已经记录在 `docs/` 目录中。
