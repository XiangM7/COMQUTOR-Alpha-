# Round 31：T4 最小交付包

| 项 | 位置 / 值 |
|---|---|
| 交付 ZIP | `T4_delivery_round31_20261009.zip` |
| ZIP 大小 | 30,827,964 字节 |
| ZIP 内容 | 255 个文件，解压后 178,508,094 字节 |
| ZIP sha256 | `6f11b68844598b12e31ba36d0a2e756b133a1e17be76593eefebf1af555ec89b` |
| 解压后的入口 | `T4_delivery/00_T4交付主报告.md`、`T4_delivery/README.md` |
| 打包前的目录 | `T4_delivery/`，与 ZIP 内容相同 |
| 解压验证 | `unzip_verification/run_unzip_verification.sh` |
| 解压验证记录 | `unzip_verification/verification_log.txt`（每条命令、完整输出和退出码）；`verify_package_result.json`；`verify_regenerate_result.json` |
| 原件前后哈希 | `hash_proof/state_before.json`（本轮开始前）、`hash_proof/state_after.json`（解压验证时）：1218 个受保护文件没有变化，tracked diff 没有变化 |

解压验证就在本目录之外的一个新临时目录里进行，从仓库根目录运行：
```
bash docs/audit_artifacts/round_source_linking_t0_t2/round31_t4_delivery_20261009/unzip_verification/run_unzip_verification.sh
```
脚本里的 `snapshot_state.py --out` 拒绝覆盖已有文件。重跑前要换一个输出文件名，否则第 6b 步会报 "refusing: output exists"。
