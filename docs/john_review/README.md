# 给 John 的检查材料（入口）

本目录只放各任务的**入口文档**。完整证据（运行目录、请求和响应审计、测试日志、交付 ZIP）保存在工程侧本地，**不放进本仓库**。

| 任务 | 本目录的入口文档 | 完整交付包（另行提供，不在仓库中） | 交付包 sha256 |
|---|---|---|---|
| T1 | `T1_entry.md` | `COMQUTOR_John_T1_T2_reviewed.zip`（其中 T2 部分已被下面 T2 一行的包取代） | `7290cdc443a84aadecbf8c185a831b91dd903b6e8527ac8ab88a4501a8225f46` |
| T2 | `T2_entry.md` | `T2_John_round23_20261009.zip` | `9fb8bdb9d0b357dc74702f02f2d827ceb3f056cca562e1775b009c56b2b47a4e` |
| T3 | 入口文档在交付包内 | `T3_delivery_t3joint-20261008T170322Z-bd99811e.zip` | `ce4216183ea0f9c98cf753a0caf7ddf4498ec0130b117cd85bbec100d67c09b3` |
| T4 | `T4_final_report.md`、`T4_D1_fix_appendix.md` | `T4_final_round33_20261009.zip`、`T4_D1_fix_round34_20261009.zip` | `62a0867ce1da71feaced2cd942a17829c7ad3ae2523c69463dbb08ed9b00b8ba`、`552e7f9eac1bf5b6ae5fb48aaf75c8741305b4c0d5286c59857683cc2b9897ac` |

## 怎么使用

- **文档**：入口文档与各交付包内的同名文件逐字节相同。文中的“本包”“`我方对应交付/…`”等路径，指的是对应的交付 ZIP 内部，不是本仓库。
- **核对交付包**：拿到 ZIP 后，用上表的 sha256 核对（`shasum -a 256 <文件>`）。T1（评审版）、T2、T4 的交付包内附有只用标准库的核对脚本，用法见各自的 README。
- **代码**：本仓库当前分支就是被验收的代码。入口文档写于代码提交之前，文中“未 commit”“HEAD `7a9aefa` 加补丁”描述的是写文档时的状态，现在这些改动已经是本分支上的提交。

## 入口文档的原始位置

| 本目录文件 | 来源 |
|---|---|
| `T1_entry.md` | `COMQUTOR_John_T1_T2_reviewed.zip` 内的 `COMQUTOR_John_T1_T2/T1/00_先看这里.md` |
| `T2_entry.md` | `T2_John_round23_20261009.zip` 内的 `00_先看这里.md` |
| `T4_final_report.md` | `T4_final_round33_20261009.zip` 内的 `00_T4最终交付报告.md` |
| `T4_D1_fix_appendix.md` | `T4_D1_fix_round34_20261009.zip` 内的 `00_D1修复附录.md` |
