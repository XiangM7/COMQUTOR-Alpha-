# T2 规则执行：Round 23 交付（John 版）

* **收件人**：John（项目负责人、验收人）
* **交付方**：COMQUTOR Alpha 工程侧（Xiang Mao）。Round 23 的代码、结果、报告和本整理版，都是工程侧用 AI 编码代理（Claude Code）在本项目仓库中生成的。
* **版本**：Round 23，目录是 `我方对应交付/round23_t2_completion_20261007/`。
  * 六标的判定的执行编号是 `t2-six-ticker-20261007`，生成于 2026-10-08T02:16:58Z。
  * 代码：仓库 HEAD `7a9aefa` 之上未提交的工作区。T2 的改动整理为 `t2_changes.patch`。没有 commit，局限见第 4 节第 8 条。
* **本版整理（2026-10-09）**：补入六个标的的历史输入 run 目录，并把读者文件改为面向 John 的版本。
  * 代码、规则、taxonomy、Gold、评分和研究结果都没有改。
  * 没有发送任何 Provider、模型、搜索或取数请求。
  * Round 23 的判定原样保留，没有重新计算。

**本文件是唯一入口。** 补齐输入文件只是让交付内容齐全，不代表 T2 的验收条款已经通过。本包不含 John 的签收。

任务单原文在 `原文/`，T2 要求逐字摘录在 `01_John对T2的要求.md`，签收标准逐字摘录在 `02_签收标准.md`。

## 1. Round 23 改了什么

代码 diff 是 `我方对应交付/round23_t2_completion_20261007/t2_changes.patch`：
* 相对 HEAD `7a9aefa`，涉及 37 个文件，增 5,958 行、删 172 行；
* 逐文件 sha256 在 `t2_files.json`。

| 部分 | 改动 |
|---|---|
| taxonomy | 补入 A102↔A304、A201↔A304 两组关系（互为声明，权重 0.75）。新增 `content_version: "1.1.0"` 和 `content_change_log`。`schema_version` 未改 |
| 规则文件 v0.2 | 把 5 对冲突补进 `allowed_conflicts`（QQQ 2 对、MSFT 2 对、TSM 1 对）。John 冻结基线的 16 条“标的—允许冲突”由此全部进入执行用规则文件（此前 11/16）。文件里声明了 `taxonomy_content_version` |
| 验收引擎 `acceptance_engine.py` | `effective_rules()` 的校验：<br>• 用调用方指定的 taxonomy 校验 label；<br>• 核对内容版本；<br>• 拒绝引擎未实现的规则键；<br>• v0.1、v0.2 两份占优规则不一致时报错。<br>`run_formal_acceptance()`：<br>• 没有声明规则的标的报配置错误；<br>• 总判定只跟随六个规则族；<br>• 输出 `coverage.pass_is_vacuous` |
| 统一入口 | `scripts/run_formal_acceptance.py`：显式读取规则文件。输出三样：`effective_rules`、逐条判定 JSON、只从该 JSON 渲染的表格 |
| 生产写入 | 规则文件有问题时写 `config_error` 产物，意外失败时写 `execution_error` 产物。两种情况下 run 本身都照常完成 |
| 新工具 | 冻结输入重算：只重跑确定性冲突检测。另有 NVDA、QQQ 争议台账 |
| 测试 | 新增 6 个测试文件。Gold 与研究分离的守护测试扩到整个 `comqutor_alpha` 和 `tradingagents`。改正了 T2 造成的 5 处断言，没有删断言，也没有加 skip |

审计时复现并修掉了 11 个缺陷，逐条列在报告 §2，每条都有对应测试。两个例子：
* 不在 label 里的标的，原来会得到 `pass`；
* 生产路径的规则文件损坏时，原来不写任何产物。

## 2. 用了哪六个历史 run

Round 23 的判定属于 Type A 重新评估：读取各 run 当时已保存的产物，只执行验收判定层。不调用 Provider，不重放，不写 run 目录。

六个输入 run 现在都在包内 `历史输入/outputs/runs/<run_id>/`。

| 标的 | run_id | run 创建时间（UTC） | 文件数 | 包内副本来源 | 历史哈希 |
|---|---|---|---|---|---|
| NVDA | `ded99ecd-a186-4a90-859e-0f1a0efa43db` | 2026-09-17 | 23 | 仓库 `outputs/runs/` 原件 | 无 |
| QQQ | `0d890564-2479-4361-94e8-25c48af3b9a8` | 2026-09-17 | 23 | 仓库 `outputs/runs/` 原件 | 无 |
| SNDK | `e8e0f398-7b26-4462-8135-a1410ea5b335` | 2026-09-04 | 23 | 仓库 `outputs/runs/` 原件 | 无 |
| MSFT | `64568bfb-fe0c-453c-9872-831a8dc339a0` | 2026-09-10 | 23 | 仓库 `outputs/runs/` 原件 | 无 |
| TSM | `fc09821e-c7cf-40a7-bd76-c98172e16992` | 2026-09-09 | 23 | 仓库 `outputs/runs/` 原件 | 无 |
| AMD | `d5b60b8a-66b8-44c1-9f55-ee345e58c48d` | 2026-09-21 | 24 | 随 T1 交付的运行归档 `round22_runs.tar.gz`（原样复用） | Round 22 有登记，逐文件 24/24 一致 |

身份核对的结果在 `历史输入/run_inventory.md`，逐文件大小和 sha256 在 `历史输入/run_inventory.json`：

* 每个 run 的 run_id 和标的在四处一致：目录名、run 自己的 `metadata.json`、判定文件的 `inputs.runs`、判定文件的 `tickers.<标的>.run_id`。
* Round 23 记录这六个 run 的 `artifact_completeness` 都是 pass，`artifact_missing_files` 都为空。
* 包内副本与仓库当前原件逐文件 sha256 一致。
* 复制前后各对原件做了一次哈希快照，两次相同。快照在 `核查记录/原件前后哈希/`。
* **AMD**：与 Round 22 发布清单中的登记一致，逐文件和整体摘要都对得上。Round 22 早于 Round 23。登记记录原件在 `核查记录/历史哈希/`。
* **其余五个 run 没有任何历史哈希。** Round 23 没有记录输入 run 的哈希，Round 22 清单也没有登记这五个 run。
  * 因此只能证明包内副本与当前原件一致。
  * 不能证明它们就是 Round 23 执行时读到的字节，也不能当作“执行时已冻结”。
  * 原件中最新的文件修改时间都早于 Round 23 执行时间。修改时间可以被改写，所以这只是旁证。
* **更正**：Round 23 的 `final_scope_proofs.py` 写着“六个固定 run 都在 Round 22 登记的 16 个 run 里”。实际只有 AMD 在其中，所以那项“登记目录未变”的检查只覆盖了 AMD。

## 3. 实际结果

以下是 Round 23 的原判定，没有重新计算。**六个标的全部是 `needs_review`**，没有 `fail`，也没有 `pass`。

| 标的 | 主冲突 | 已准入冲突 | 复核原因 |
|---|---|---|---|
| NVDA | A304__A601 | A304__A601 | 软漏检 A101__A304、A301__A304（有证据、立场可靠，但没有准入）。A304__A601 已准入但未声明，属于 John 点名的待审核项 |
| QQQ | A003__A501 | A003__A501、A304__A601、A501__A601 | 软漏检 A001__A501。A501__A601 已准入但未声明 |
| SNDK | 无 | 无 | 软漏检 A301__A304 |
| MSFT | A301__A304 | A301__A304、A304__A601 | A304__A601 已准入但未声明 |
| TSM | A101__A304 | A101__A304、A301__A304、A304__A601 | A304__A601 已准入但未声明 |
| AMD | A301__A304 | A101__A304、A301__A304、A304__A601 | A304__A601 已准入但未声明 |

逐条判定在 `six_ticker/formal_acceptance_verdicts.json`，表格在 `six_ticker/formal_acceptance_tables.md`，有效规则在 `six_ticker/effective_rules.json`。三个文件都在 Round 23 目录下。

其他真实数据结果（详见报告 §3）：

* **John 冻结基线的 16 条**：16/16 都在规则文件里。各 run 实际看到的状态（admitted、candidate 或 not_reached）列在表格 §5。
* **冻结输入重算 A102__A304、A201__A304**：只重跑确定性冲突检测，零模型调用。6 个标的 × 2 对，共 12 次评估：
  * 2 次准入，都是 A201__A304，分别在 TSM 和 AMD；
  * 7 次停在候选；
  * 3 次没有进入仲裁。
  * 两个标的的主冲突都没有变。原有冲突的准入集合与 run 保存的一致。
* **争议台账**：
  * NVDA 有 18 条、QQQ 有 7 条未关闭条目。
  * 没有任何复核决定记录，没有条目被关闭。
  * 第一条未关闭条目之后，NVDA 又有 3 个 PASS run，它们关闭的条目数是 0。
  * 其中最新的 NVDA Fresh `034a0a60` 是空 PASS：没有任何声明的规则有证据可检验。
* **生产写入样本**：对 AMD 派生 run `dependency-20261007T220450Z-33128621` 离线计算一遍，结果是 `pass`，但 `pass_is_vacuous: true`。
  * 原因：声明的 3 个冲突对都没有两边的支持证据，没有准入任何冲突。
  * 所以这个 PASS 不能读成“规则被验证过”。
* **哪些规则族在真实数据上触发过**：6 类里有 4 类。
  * 触发过：`should_detect_if_supported`、`conditional_only`、`allowed_main_conflicts`、`do_not_force`。
  * 没触发过：`must_detect_if_evidence_present`、`forbidden_dominant_without_strong_evidence`。这两类只有合成测试。

测试结果的原始 JUnit 和日志在 `test_evidence/`：

* **T2 的 16 个测试文件**（整套中共 239 项）：237 通过、2 失败。
  * 两个失败都在第 15 轮基线里：一个写死了旧 HEAD，另一个是 alpha_mapper 的字节钉扎。
  * T2 快测在最终代码上单独再跑一遍：110 通过、1 失败。失败的是上面的第二个。
* **整套测试**（5,185 项，48 分 53 秒）：5,088 通过、38 失败、3 个 error、56 跳过。与第 15 轮基线逐项对比：
  * 40 个失败在基线内；
  * 2 个基线失败转绿；
  * 1 个失败在基线外：`test_evidence_review_sample::test_58_sample_rows_trace_back_to_real_artifacts`。
    * 归因是 AMD 派生 run 的声明 ID 前缀，不是 T2 代码，见 `NEW_failure_attribution.md`。
    * 这个失败没有修。
* **合成测试与真实数据分开**：场景 1、2、4、6 的最终状态、各条错误路径、生产写入的可见产物，都由合成 fixture 证明。fixture 在测试模块的文档字符串里明确标注，不计为真实市场验证。

## 4. 这个版本还有哪些限制

1. **规则未获批准**：v0.2 规则文件的状态是 `provisional_ai_predicted`，评估模式 `shadow`，产品负责人批准为 `pending`。本包的判定都是临时规则下的判定，不是 John 批准的正式判定。
2. **两类规则只有合成测试**：六个标的的 `required_conflicts` 全为空，所以 `must_detect_if_evidence_present` 在真实数据上不会触发。`forbidden_dominant_without_strong_evidence` 在六个 run 中也没有触发。
3. **没有 Alpha 层漏检判定**：
   * 场景 1（必须识别的 Alpha）和场景 2 都按冲突对实现和测试。
   * 包内 `规则文件/` 的 label 文件里其实有各标的的 Alpha 列表：v0.1 的 `expected_positive_alphas` 等字段，v0.2 的 `positive_alphas` 等字段。Round 23 没有用这些列表做判定。
   * 报告 §6 原句说“任何规则文件里都没有”。原句保留，旁边加了读者注。
4. **A102__A304、A201__A304 的结果只在冻结输入重算里**：
   * Type A 判定读的是 run 当时保存的 `conflicts.json`，这两对在其中是 `not_reached`。
   * 这些 run 早于来源关联，验证型证据闸门是关闭的。重算结果说明闸门如何处理这两对新关系，不说明证据已经核验。
5. **有一条规则声明了但没有评估**：NVDA 的 `run_bound_expectations` 没有任何规则族评估它，见 `effective_rules.json` 的 `declared_but_not_evaluated`。
6. **两套汇总并存**：A4 回归报告（`scripts/run_regression.py`）仍是另一套汇总，不读统一入口。验收表以统一入口的输出为准。
7. **需要 John 决定的问题**（报告 §6）：
   * 16 条是否都归入 `allowed_conflicts`？现在有 10 条在 `conditional_conflicts`。若全部归入 allowed：
     * SNDK 会从 `needs_review` 变成 `pass`；
     * NVDA、QQQ 的软漏检复核会消失，但两者仍是 `needs_review`。
   * 场景 1 的粒度：指必须出现的冲突对，还是必须被激活的 Alpha？
   * 规则文件的批准。
8. **没有完整代码基线**：没有 commit，包内也没有 HEAD `7a9aefa` 的源码。
   * `t2_changes.patch` 只含 T2 的 37 个文件，Round 23 核对过它可以在 HEAD 上重建这 37 个文件。
   * Round 23 执行时的工作区还有更早轮次未提交的改动，这些不在本包里。例如 T1 的 `comqutor_alpha/source_provenance.py` 未被 git 跟踪，也不在补丁里。
   * 因此“HEAD 加补丁”是否足以运行 Round 23 的命令，Round 23 和本次整理都没有验证。
   * 仓库当前工作区已含后续改动，直接运行的也不是 Round 23 代码。
9. **五个输入 run 没有执行时的哈希**，详见第 2 节。
10. **本包只补入了六标的判定的输入**。报告和台账还提到其他 run，它们的目录不在本包里：
    * 不在本包的 run：
      * 争议台账涉及的 NVDA 18 个和 QQQ 11 个 run；
      * 冻结输入重算提到的另一个 MSFT run `6cd2566d`；
      * NVDA Fresh `034a0a60`；
      * AMD 派生 run `dependency-20261007T220450Z-33128621`。
    * 其中 `034a0a60` 和 `dependency-20261007T220450Z-33128621` 在 T1 的运行归档里。
    * 这些 run 的判定结果文件都在包内。
11. **还有未修的测试问题**：与 T2 无关的既有钉扎（alpha_mapper 等）仍是红的。整套测试的 1 个基线外失败没有修。
12. **技术证据保持原始字节，没有编辑**：
    * `final_scope_proofs.json` 仍记录 Round 23 当时的本地服务检查；
    * `t2_files.json` 的 `commit` 字段保留当时“未 commit”的原文。
    * 这些是执行记录，不是给读者的操作要求。
    * 本版只改了两份读者文件（报告与 `README_T2.md`），逐条改动和原 sha256 在 `核查记录/文档修改记录.json`。

## 5. 怎么核对

* **只用本包**：在解压后的包根目录运行 `python3 verify_t2_package.py`。
  * 只需要 Python 3.9 以上的标准库。
  * 不联网，不写任何文件。
  * 它检查以下内容：
    * 全部文件的哈希；
    * 六个输入 run 的位置、文件数、逐文件 sha256 和 run_id 身份；
    * AMD 与 Round 22 的登记；
    * 规则文件与 `effective_rules.json` 记录的 sha256；
    * 规则、diff、判定和原始测试日志是否齐全；
    * 报告引用的包内文件是否存在；
    * 凭据模式扫描。
* **需要原仓库环境**：`我方对应交付/round23_t2_completion_20261007/README_T2.md` 里的命令，包括统一入口、冻结输入重算、争议台账、pytest 和重建补丁。

两类命令的区别和具体步骤见 `README.md`。

## 6. 包内目录

| 位置 | 内容 |
|---|---|
| `00_先看这里.md` | 本文件，唯一入口 |
| `README.md` | 核对命令。分两类：只用本包即可执行的，和需要原仓库环境的 |
| `verify_t2_package.py` | 包内完整性与身份核对脚本，只用标准库 |
| `package_manifest.json` | 本包全部文件的大小和 sha256（不含 manifest 自身） |
| `01_John对T2的要求.md`、`02_签收标准.md`、`原文/` | John 的要求原文 |
| `规则文件/` | 被评估的规则文件副本：taxonomy、label v0.2 与 v0.1、John 冻结基线 |
| `我方对应交付/round23_t2_completion_20261007/` | Round 23 交付：<br>• 报告 `01_中文简明验收报告_T2.md`；<br>• `README_T2.md`；<br>• 六标的判定；<br>• 冻结输入重算；<br>• 争议台账；<br>• diff；<br>• 原始测试日志；<br>• 范围证明 |
| `历史输入/outputs/runs/` | 六个输入 run 的完整目录，原始字节 |
| `历史输入/run_inventory.md`、`.json` | 六个 run 的身份与哈希清单 |
| `核查记录/` | 文档修改记录、AMD 的历史哈希记录、原件前后哈希快照、凭据扫描结果 |
