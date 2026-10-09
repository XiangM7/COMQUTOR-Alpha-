# D1 修复补充包（Round 34，2026-10-09）

收件人：John。入口是 `00_D1修复附录.md`。本包只补充 D1 的修复材料，T4 最终交付包（Round 33）保持不变。

## 目录

| 路径 | 内容 |
|---|---|
| `00_D1修复附录.md` | 附录：契约修复、离线工程验证、尚未进行的真实模型验证，分开说明 |
| `01_before_after/` | 第二次 Fresh 的两份真实回复在修复前、修复后走生产路径的结果（JSON 和运行日志），以及 9 批请求的输入大小 |
| `02_code/` | `round34_d1_changes.diff`：最小 diff。`changed_files.json`：文件清单、前后 sha256 和代码身份。`prompt_versions.json`：新旧 prompt 全文、版本号和身份哈希 |
| `03_tests/` | 测试命令、日志、JUnit、网络陷阱结果；冻结哈希钉测试修复前后的状态 |
| `04_production_entry/` | 真实生产入口使用新 prompt 的证明 |
| `05_hash_proof/` | 本轮前后的原件哈希快照和说明 |
| `credential_scan_result.json` | 打包前的凭据扫描：模式扫描，加上仓库 `.env` 中密钥值的比对。只记变量名 |
| `tools/` | 本轮脚本 |
| `verify_d1_fix.py` | 包内核对脚本 |

## 1. 只用本包即可执行的检查

需要 Python 3.9 以上的标准库。不需要仓库、API key 或数据库，不联网，不写文件。在解压后的本目录运行：

```bash
python3 verify_d1_fix.py
```

全部通过时退出码为 0。它检查七项：
1. 文件哈希；
2. 新旧 prompt 身份能从保存的原文重算出来，并与回放登记一致；v1 等于两次 Fresh 记录的值；
3. 修复前后两份真实回复的结论，以及各批输入大小的变化；
4. 测试组 0 失败、0 次外部连接，运行期间代码未变，且就是记录的最终代码；冻结哈希钉测试修复前后是同一项失败；
5. diff 与文件清单一致；
6. 文档引用的文件都在包内；
7. 凭据扫描。

## 2. 需要原仓库环境的命令

以下命令在仓库根目录运行，需要：
- 仓库处于 `02_code/changed_files.json` 记录的最终代码身份；
- 项目的 `.venv`；
- 第二次 Fresh 的原 run 目录 `outputs/t4_runs/12591384-0b26-470d-a99d-a49c00be440b`。

这些命令都不发送外部请求。

```bash
R34=docs/audit_artifacts/round_source_linking_t0_t2/round34_t4_d1_contract_fix_20261009
source .venv/bin/activate
python $R34/tools/run_with_network_trap.py $R34/tools/d1_before_after.py --label recheck --out /tmp/d1_recheck.json
python -m pytest tests/test_t4_round34_d1_adapter_citation_contract.py -q
```

- **第一条**：在当前代码上重做两份真实回复的复现。最后一行应为 `network attempts: 0`。
- **第二条**：只跑本轮新增的测试。
- **完整测试组**：清单和命令见 `03_tests/d1_command.txt`，可以照抄运行。原测试记录是用 `tools/run_r34_tests.sh` 生成的，这个脚本会把结果写回仓库中本轮的 `03_tests/` 目录。
