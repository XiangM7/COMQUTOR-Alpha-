# 六个历史输入 run：包内清单

Round 23 六标的判定（`我方对应交付/round23_t2_completion_20261007/six_ticker/formal_acceptance_verdicts.json`，执行 `t2-six-ticker-20261007`，类型 A_REEVALUATION，生成于 2026-10-08T02:16:58Z）读取的六个 run，原样放在本目录 `outputs/runs/<run_id>/`。逐文件大小与 sha256 见 `run_inventory.json`。

目录摘要算法与 Round 22 发布清单相同：对排序后的文件，取 `相对路径<TAB>sha256` 逐行拼接后的 sha256。

| 标的 | run_id | 包内位置 | 文件数 | 字节数 | 目录摘要 sha256 | 来源 | run_id 与 Round 23 判定一致 | 复制件 = 当前原件 | 原件复制前后不变 | 历史哈希 |
|---|---|---|---|---|---|---|---|---|---|---|
| NVDA | `ded99ecd-a186-4a90-859e-0f1a0efa43db` | `历史输入/outputs/runs/ded99ecd-a186-4a90-859e-0f1a0efa43db/` | 23 | 30,610,167 | `7f262d406572f9d4c6070f281af2a4b9a832ccc8181d5bb0f931817d94df20d5` | 仓库 `outputs/runs/` | 是 | 是 | 是 | 无 |
| QQQ | `0d890564-2479-4361-94e8-25c48af3b9a8` | `历史输入/outputs/runs/0d890564-2479-4361-94e8-25c48af3b9a8/` | 23 | 28,821,547 | `9fe3b1f5e52a687663e83272cbbcf8b1b60e74c9b6084bbd81822d8a342df891` | 仓库 `outputs/runs/` | 是 | 是 | 是 | 无 |
| SNDK | `e8e0f398-7b26-4462-8135-a1410ea5b335` | `历史输入/outputs/runs/e8e0f398-7b26-4462-8135-a1410ea5b335/` | 23 | 25,032,438 | `a8a1d82895249d3542273738c77743f357a30be202e0768208b9e92beb9f6f3e` | 仓库 `outputs/runs/` | 是 | 是 | 是 | 无 |
| MSFT | `64568bfb-fe0c-453c-9872-831a8dc339a0` | `历史输入/outputs/runs/64568bfb-fe0c-453c-9872-831a8dc339a0/` | 23 | 29,752,980 | `1dc0920ccc23efb1e64e1510f9a4bd91d00b17bc9e84a3f013fb7f7e9c8b98e5` | 仓库 `outputs/runs/` | 是 | 是 | 是 | 无 |
| TSM | `fc09821e-c7cf-40a7-bd76-c98172e16992` | `历史输入/outputs/runs/fc09821e-c7cf-40a7-bd76-c98172e16992/` | 23 | 23,820,241 | `884d0172465f60463e2e1a6e437d52a74a26396628fa7113fde757a904d7083e` | 仓库 `outputs/runs/` | 是 | 是 | 是 | 无 |
| AMD | `d5b60b8a-66b8-44c1-9f55-ee345e58c48d` | `历史输入/outputs/runs/d5b60b8a-66b8-44c1-9f55-ee345e58c48d/` | 24 | 28,578,305 | `9298b7a6c3780c96c20d0980f3785833b3d780668f03eb042b6f819ae5d63027` | T1 运行归档 `round22_runs.tar.gz` | 是 | 是 | 是 | 有（Round 22）：摘要一致，逐文件 24/24 |

合计 6 个 run、139 个文件、166,615,678 字节。

## 各列的含义与证明力

* **run_id 与 Round 23 判定一致**：目录名、run 自己的 `metadata.json`（run_id、ticker）、判定文件的 `inputs.runs` 与 `tickers.<标的>.run_id` 四处相同。Round 23 记录这六个 run 的 `artifact_completeness` 均为 pass、`artifact_missing_files` 均为空。
* **复制件 = 当前原件**：包内每个文件与仓库 `outputs/runs/<run_id>/` 中的原件逐文件 sha256 相同，文件集合也相同。
* **原件复制前后不变**：复制前、复制后各对原件做一次哈希快照（`核查记录/原件前后哈希/`），两次相同。
* **历史哈希（AMD）**：Round 22 发布清单（2026-10-07，早于 Round 23 执行）登记了 AMD 这个 run 的 24 个文件。包内副本取自随 T1 交付的运行归档（归档 sha256 `cd19e0663435c421e277c7fc02e6078c631bb87e5ffeb8243d2f94ea3a1c9d11`），与该登记逐文件、整体摘要都一致，也与仓库当前原件一致。归档里每个文件旁边的 macOS `._` 元数据条目（26 个）不是 run 文件，没有放入。
* **历史哈希（其余五个）**：Round 23 没有记录输入 run 的哈希，Round 22 清单也没有登记这五个 run，此前没有任何记录给它们做过哈希。因此这里**只能证明包内副本与当前原件一致**，不能证明它们就是 Round 23 执行时读到的字节，也不能写成“执行时已冻结”。
* **旁证（不作为证明）**：六个原件目录里最新的文件修改时间都早于 Round 23 执行时间（见 JSON 的 `supplementary_mtime_check`）；修改时间可以被改写，只作参考。
* **更正**：Round 23 的 `final_scope_proofs.py` 文档字符串说“六个固定 run 都在 Round 22 登记的 16 个 run 里”。实际只有 AMD 在其中（`核查记录/历史哈希/round22_release_manifest_v2_excerpt.json`），所以那项“登记目录未变”的检查只覆盖了 AMD。
