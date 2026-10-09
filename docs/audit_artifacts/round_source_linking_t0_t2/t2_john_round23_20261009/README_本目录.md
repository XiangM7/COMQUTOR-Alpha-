# T2 Round 23 John 版：工作目录索引（2026-10-09）

| 项 | 位置 / 值 |
|---|---|
| 交付 ZIP | `T2_John_round23_20261009.zip`（8,597,651 字节，193 个文件，解压后约 162 MB） |
| ZIP sha256 | `9fb8bdb9d0b357dc74702f02f2d827ceb3f056cca562e1775b009c56b2b47a4e` |
| 解压后入口 | `T2_John_round23/00_先看这里.md`（唯一入口）、`T2_John_round23/README.md`（核对命令） |
| 打包前目录 | `T2_John_round23/`，与 ZIP 内容逐文件一致 |
| 构建日志 | `build_log.txt`：命令、完整输出、退出码。构建脚本是 `tools/run_build.sh` |
| 解压验证 | `unzip_verification/verification_log.txt`，以及 `verify_t2_package_result.json`、`credential_scan_unzipped.json`。验证脚本是 `tools/run_unzip_verification.sh` |
| 原件前后哈希 | `hash_proof/`：<br>• `state_before.json`：复制前；<br>• `state_after_copy.json`：复制后；<br>• `state_after_zip.json`：打包和解压验证后。<br>两次比较都是 `all_unchanged = True` |
| 保留未动的旧件 | 上传的 `~/Desktop/t2.zip`（sha256 `2f772bb5…`）、`~/Desktop/t1.zip`、T1 运行归档、`~/Desktop/COMQUTOR_John_T1_T2_reviewed.zip`、仓库 Round 23 目录、六个原 run |
