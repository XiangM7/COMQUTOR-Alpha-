# Round 22 交付 README（可复制执行）

本目录是 T1 收尾（第 22 轮）的唯一入口。所有命令都在**仓库根目录**运行，路径都是仓库相对路径（不含任何个人机器路径）。除第 5 步外，**不调用任何 Provider / 搜索 / 取数**，不写 `outputs/`，不 commit / push。

```bash
cd <仓库根目录>
source .venv/bin/activate
R22=docs/audit_artifacts/round_source_linking_t0_t2/round22_t1_closeout_20261007
R21=docs/audit_artifacts/round_source_linking_t0_t2/round21_t1_minimal_closure_20261007
```

## 本目录有什么

| 文件 | 内容 |
|---|---|
| `01_中文简明验收报告_收尾版.md` | 验收报告（五项工程成果 / 真实验证覆盖 / 剩余材料缺口）。**以它为准**；第 21 轮报告顶部已加勘误指向它 |
| `release_manifest_v2.json` | 新的交付身份清单：原始运行与各派生执行 → 代码 / 输入 / 模型 / 规则 / 日志（旧清单 `../release_manifest.json` 原样保留） |
| `code_snapshots/S0_before_round22/`、`S1_final/` | **真实代码内容**：HEAD + 完整未提交差异（`tracked_diff_vs_HEAD.patch`）+ 未跟踪源码全文（`untracked_source/`）+ 规则文件（`rule_files/`）。S0 = 本轮改动之前（即 `dependency-…33128621` 执行时的代码），S1 = 交付时 |
| `round22_changes.patch` | S0 → S1 的精确差异（本轮改了什么） |
| `run_identity_files/<run_id>/`、`run_directory_hashes/` | 每个 run 的身份文件原文副本；整个 run 目录逐文件 hash |
| `coverage_mapping_34.json`、`report_numbers.json`、`john_spot_check_sample.*` | 报告引用的数字 / 34 条问题类型覆盖映射 / John 抽查参考表（仅供参考，不是门槛） |
| `browser_walkthrough_round22_conflict*` | Conflict 页浏览器核对（历史 run d5b60b8a）：截图 + 结果 JSON |
| `test_evidence/` | 本轮测试的原始输出与基线对照 |

## 1. 只读查看实例（API 8001 + 前端 5176）

不设置真实执行 / LLM 开关，只连隔离的 `*_test` 数据库，不会发起任何研究任务。**必须用 `127.0.0.1`，不能用 `localhost`**（API 的跨域只放行 `http://127.0.0.1:5176`）。

```bash
bash $R21/start_viewer_api.sh                      # 终端 1：API（日志输出到终端）
cd frontend && VITE_COMQUTOR_API_BASE_URL=http://127.0.0.1:8001 npx vite --host 127.0.0.1 --port 5176 --strictPort   # 终端 2
curl -s http://127.0.0.1:8001/ready                # 应显示 "real_execution":"disabled"
```

页面（execution `dependency-20261007T220450Z-33128621`）：
`http://127.0.0.1:5176/runs/dependency-20261007T220450Z-33128621/structure`（A301 → Evidence → View basis）、
`.../research`（Key conclusions）。

历史冲突页：隔离库里**没有**历史 run `d5b60b8a-…` 的冲突行（冲突路由只读数据库），所以该 run 的冲突页数据由浏览器脚本用该 run **自己保存的 `conflicts.json`** 提供（见 `browser_walkthrough_round22_conflict.mjs` 与结果 JSON 里的披露）；其中 “View basis” 调用的追溯路由是真实 API，直接读该 run 的已保存文件：

```bash
curl -s "http://127.0.0.1:8001/api/research/d5b60b8a-66b8-44c1-9f55-ee345e58c48d/evidence-trace?claim_id=d5b60b8a-66b8-44c1-9f55-ee345e58c48d%3Abull_researcher%3Ainvestment_debate_state.bull_history%3Aclaim%3A107" | python3 -m json.tool | head -60
```

## 2. 零调用回放 / 复算（离线）

```bash
python $R22/prove_s0_is_the_code_of_dependency_final.py   # 在 Round 22 目录里重跑一次现行管线的离线重算（陷阱：任何 Provider/网络调用即中止），并核对代码身份
```

## 3. 验证脚本（全部只读）

```bash
python $R22/verify_snapshot.py $R22/code_snapshots/S1_final --against-working-tree   # 快照可由 HEAD + 补丁 + 副本重建，且与工作树一致
python $R22/verify_release_manifest_v2.py                                            # 清单里每个 hash / 副本 / 快照 / run 目录逐一核对
python $R22/diff_snapshots.py $R22/code_snapshots/S0_before_round22 $R22/code_snapshots/S1_final /tmp/round22_changes_check.patch   # 重建 S0→S1 差异
python $R22/credential_scan.py                                                       # 本轮产出与改动代码的密钥扫描（.env 密钥值只在内存里精确匹配，不落盘）
python $R22/build_report_data.py                                                     # 重新生成报告引用的数字、34 条覆盖映射、John 抽查参考表
# 第 21 轮的两个验证（会重写各自的结果 JSON，内容等价）：
python $R21/verify_amd34_list_intact.py                                              # AMD 34 条清单完整、可从历史运行独立重导出
python $R21/verify_claim31_chain.py                                                  # 声明 31 的 11 个环节（需要第 1 步的 API；对第 22 轮新增的字段只忽略、不改变原字段的逐项比较）
```

从快照手工重建代码树（不动仓库；与 `verify_snapshot.py` 做的是同一件事）：

```bash
S=$R22/code_snapshots/S1_final
T=$(mktemp -d)
git archive HEAD -- $(python3 -c "import json;print(' '.join(p for p,v in json.load(open('$S/file_hashes.json')).items() if v['class']=='tracked_differs_from_HEAD'))") | tar -x -C "$T"
git -C "$T" apply "$PWD/$S/tracked_diff_vs_HEAD.patch"      # 已跟踪文件：HEAD + 完整未提交差异
cp -R $S/untracked_source/. "$T"/                           # 未跟踪源码：全文副本
# 逐文件核对（与 file_hashes.json 一致即重建正确）
python3 -c "
import hashlib, json, pathlib
T = pathlib.Path('$T'); h = json.load(open('$S/file_hashes.json'))
bad = [p for p, v in h.items() if v['class'] != 'rule_file' and hashlib.sha256((T / p).read_bytes()).hexdigest() != v['sha256']]
print('rebuilt', len(h), 'entries; mismatches:', bad)"
```

## 4. 测试（只跑受影响的）

```bash
# 后端：本轮新增 + 与之相关
python -m pytest tests/test_t1_closeout_capture_artifacts.py tests/test_t1_closeout_conflict_basis.py \
  tests/test_t1_closure_grounding_dependency_trace.py tests/replay/test_capture_artifacts_replay_compat.py -q
# 与已记录的基线失败（第 15 轮 42 条，均已归因）比较；任何不在基线内的失败会被列出
python -m pytest <受影响文件…> -q --junitxml=/tmp/r22.junit.xml ; python $R22/compare_with_baseline.py /tmp/r22.junit.xml
# 前端
(cd frontend && npx vitest run && npx tsc -b && npx eslint src)
# PostgreSQL 集成（把 COMQUTOR_TEST_DATABASE_URL 指向以 _test 结尾的隔离库，不要打印它）
python -m pytest tests/test_t1_market_source_fields_postgres_integration.py tests/test_week4_postgres_persistence.py -q
```

本轮实际运行的命令、退出码与原始输出在 `test_evidence/`。

## 5. 下一次真实取数时（本轮没有做）

本轮的取数层改动只有**离线测试**证明。下一次真实运行会额外写出两个 present-only 产物（旧 run 没有，也不会被补写）：

* `derived_inputs.json`：技术指标的**完整输入窗口**（每一行 OHLCV、时间索引、列、单位、升序）+ 方法 / 版本 / 指标定义 / 数据处理设置；`comqutor_alpha/capture_artifacts.py: recompute_derived_inputs()` 只凭它复算指标；
* `provider_response_audit.json`：脱敏后的**供应商原始响应**（新闻）及解析器读了哪些字段；用来区分“供应商没给摘要”与“解析没读到该字段”。

要验证它们在真实供应商上的行为，需要单独授权一次最小取数（一个标的、一次新闻 + 一次行情，**不**启动研究 Agent）；本轮没有发送任何真实取数请求。

## 6. 把被登记的 run 目录一起打包

清单用“仓库相对路径 + 逐文件 digest”绑定 `outputs/runs/` 下的 run（合计约 190 MB，不复制进 `docs/`）。需要随清单一起交付内容时：

```bash
bash $R22/package_runs.sh /tmp/round22_runs.tar.gz       # 解包后运行 verify_release_manifest_v2.py 即可核对
```

## 7. 重新生成快照与清单

```bash
python $R22/snapshot_working_tree.py $R22/code_snapshots/S2_new          # 新的代码快照（目标目录必须为空）
python $R22/build_release_manifest_v2.py --s0 $R22/code_snapshots/S0_before_round22 --s1 $R22/code_snapshots/S2_new
```

## 已知限制

* 没有任何 commit：代码身份由快照（HEAD `7a9aefa` + 完整未提交差异 + 未跟踪源码）绑定；**只有 `dependency-…33128621` 有代码快照**，其余执行的执行时代码标 `UNKNOWN_NO_SNAPSHOT_AT_EXECUTION`，不用今天的代码补写。
* 抓取时间只有“注册表写入时间上界”；原始供应商响应、技术指标输入序列在**既有 run 里都没有保存**（不回填）。
* 历史冲突页的数据来自浏览器层拦截（见第 1 步）；真实 admitted conflict 在新流程的 run 里不存在，所以正向展示用**明确标注的 fixture**验证。
* 这些证据不构成 John 的签收，也不代表 T1 通过。
