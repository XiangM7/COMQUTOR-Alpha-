# 核对说明：T2 Round 23（John 版）

结论、输入、结果和限制见 `00_先看这里.md`。本文件只说明怎么核对。核对命令分两类：

* 第 1 节的命令只用本包即可执行；
* 第 2 节的命令需要原仓库环境。

## 1. 只用本包即可执行

需要 Python 3.9 以上，不需要第三方包，也不联网。在解压后的包根目录（`00_先看这里.md` 所在目录）执行：

```bash
python3 verify_t2_package.py           # 逐项打印 PASS / FAIL
python3 verify_t2_package.py --json    # 同样的结果，JSON 格式
```

* 退出码 0 表示全部通过，1 表示至少一项不通过。
* 脚本不写任何文件，不启动服务，不发起研究或模型请求。

它检查七项：

| 项 | 内容 |
|---|---|
| 1 manifest | `package_manifest.json` 列出的每个文件都存在，大小和 sha256 一致；没有清单外的文件 |
| 2 six_inputs | Round 23 判定文件引用的六个 run，都能在 `历史输入/outputs/runs/<run_id>/` 找到。<br>• 文件列表、逐文件 sha256、目录摘要与 `历史输入/run_inventory.json` 一致。<br>• run_id 和标的在目录名、`metadata.json`、判定文件三处一致。<br>• AMD 还要与 Round 22 的哈希登记一致 |
| 3 evidence | 以下文件齐全：规则文件、diff、`effective_rules.json`、逐项判定、表格、原始测试 JUnit 和日志。<br>• 三个规则文件的 sha256 等于 `effective_rules.json` 和 `t2_files.json` 的记录。<br>• 补丁的 sha256 等于 `t2_files.json` 的记录 |
| 4 reader_edits | 改过的两份读者文件，sha256 与 `核查记录/文档修改记录.json` 一致 |
| 5 references | 读者文件里引用的文件路径都在包内存在。仓库路径（`comqutor_alpha/`、`scripts/`、`tests/` 等）单独列出，不算失败：它们的 T2 改动内容在 `t2_changes.patch` 里，其余需要原仓库 |
| 6 readme | 本 README 分开列出了两类命令 |
| 7 credentials | 对每个文件做凭据模式扫描，覆盖 API key、Bearer token、鉴权字段、带密码的数据库 URL |

**这个脚本不证明以下几件事**：
* 不重新运行验收引擎或 pytest；
* 不证明 NVDA、QQQ、SNDK、MSFT、TSM 五个输入就是 Round 23 执行时读到的字节。这五个没有历史哈希，见 `历史输入/run_inventory.md`；
* 不对研究结论做语义审核。

不用脚本也可以手工抽查：

```bash
shasum -a 256 规则文件/alpha_taxonomy_v1.yaml        # 对照 我方对应交付/round23_t2_completion_20261007/six_ticker/effective_rules.json 的 taxonomy.sha256
shasum -a 256 历史输入/outputs/runs/d5b60b8a-66b8-44c1-9f55-ee345e58c48d/conflicts.json   # 对照 历史输入/run_inventory.json 与 核查记录/历史哈希/
```

## 2. 需要原仓库环境

下面这些命令在 `我方对应交付/round23_t2_completion_20261007/README_T2.md` 里：
* 统一正式验收入口 `scripts/run_formal_acceptance.py`；
* 冻结输入重算；
* 争议台账；
* T2 快测、慢测和整套 pytest；
* 重建补丁、范围证明。

运行它们需要以下前提，**只靠本 ZIP 不能运行**：

* 仓库源码和项目依赖环境（`.venv`）。本包没有 HEAD `7a9aefa` 的源码。
* Round 23 的代码。`t2_changes.patch` 是 T2 的 37 个文件相对 HEAD `7a9aefa` 的 diff，Round 23 核对过它可以在 HEAD 上重建这 37 个文件。但 Round 23 执行时的工作区还有更早轮次未提交的改动，这些不在本包里（例如 `comqutor_alpha/source_provenance.py`）。
  * 因此“HEAD 加补丁”是否足以运行这些命令，没有验证过。
  * 仓库当前工作区已含后续改动，也不等于 Round 23 代码。
* 六个输入 run。这些命令默认读仓库的 `outputs/runs/`。三个入口都有 `--runs-root` 参数，可以指向本包的 `历史输入/outputs/runs`。本次整理没有执行这些命令。
* 整套 pytest 依赖仓库的开发环境配置。Round 23 当时的原始结果在 `test_evidence/`。

Round 23 当时是在原仓库工作区里运行这些命令的，输出就是包内的：
* `six_ticker/`、`frozen_input_recompute/`、`open_review_ledger/`；
* `*_stdout.txt`；
* `test_evidence/`。

## 3. 本包怎么做出来的

* `我方对应交付/`、`规则文件/`、`原文/` 和两份要求摘录都来自上传的 T2 包。
  * 其中 Round 23 目录与仓库原件逐文件一致。
  * 除两份读者文件外，都保持原始字节。
  * 改动逐条记在 `核查记录/文档修改记录.json`。
* `历史输入/` 的来源：
  * 五个 run 从仓库 `outputs/runs/` 按字节复制；
  * AMD 从随 T1 交付的运行归档 `round22_runs.tar.gz` 原样取出。
  * 复制前后对原件各做了一次哈希快照，结果在 `核查记录/原件前后哈希/`。
* `核查记录/credential_scan_result.json`：打包前在仓库里做的扫描。除了模式扫描，还把仓库 `.env` 中密钥类变量的值逐一与包内字节比对。结果只记变量名和命中数，不含任何值。
* 原上传的 T2 ZIP 和 T1 ZIP、Round 23 原目录、六个原 run 都没有被修改。
