# Round 33：T4 收尾三项（D1 离线定位、最终查看入口、“6 次／5 条”对账）

| 项 | 位置 / 值 |
|---|---|
| 交付 ZIP | `T4_final_round33_20261009.zip`：46,743,357 字节，216 个文件，解压后约 117 MB |
| ZIP sha256 | `62a0867ce1da71feaced2cd942a17829c7ad3ae2523c69463dbb08ed9b00b8ba` |
| 解压后的入口 | `T4_final_r33/00_T4最终交付报告.md`（收件人 John）、`T4_final_r33/README.md` |
| 构建 | `tools/run_build33.sh`；命令、完整输出和退出码在 `build_log.txt` |
| 解压验证 | `tools/run_unzip_verification33.sh`；记录在 `unzip_verification/verification_log.txt`（失败命令 0）、`verify_package33_result.json`、`credential_scan_unzipped.json` |
| 原件前后哈希 | `hash_proof/`：<br>• `state_before.json`：本轮开始；<br>• `state_after_build.json`：打包前；<br>• `state_after_zip.json`：解压验证后；<br>• `README.md`：说明唯一有变化的 8002 访问日志 |
| 本轮工作目录 | `01_d1/`、`02_viewer/`、`03_not_sent_reconcile/`、`tools/`、`john_docs/`（报告和 README 的源文件）。前三个目录与包内 `round33/` 下的同名目录相同 |
| 最终查看入口（本机，正在运行） | 前端 `http://127.0.0.1:5179` → API `http://127.0.0.1:8005`，最终代码 `6cdd51e3…` / `10ee7518…`，只读。日志在 `02_viewer/instance_8005.log`、`02_viewer/web_5179.log` |
| 代码 | 本轮没有改生产代码，最终代码仍是 Round 32 冻结的版本 |
| 保留未动的旧件 | Round 32 目录和 ZIP（sha256 `2597f909…`）、Round 31 包、两次 Fresh 的 run、8002 / 5177 服务 |
