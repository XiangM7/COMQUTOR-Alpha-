# Round 34：D1 适配器输出契约修复

| 项 | 位置 / 值 |
|---|---|
| D1 补充包 ZIP | `T4_D1_fix_round34_20261009.zip`：304,761 字节，37 个文件 |
| ZIP sha256 | `552e7f9eac1bf5b6ae5fb48aaf75c8741305b4c0d5286c59857683cc2b9897ac` |
| 解压后的入口 | `T4_D1_fix_r34/00_D1修复附录.md`（收件人 John）、`T4_D1_fix_r34/README.md` |
| prompt | v1 `c6822099…` 退役，原文保留供回放；v2 `fc01ae0d261f63bf081610a22c99486186d10677d94ddbabb21f2fa602d4f628` |
| 最终代码身份 | tracked `0070cdf44b9717c8ce751f22224f84afe8d24abce21c19ff501b9426cb9fa8f3` / untracked `10ee75185ae8032bc9bdf304152a87c1d22db08120cdd546d31925277e21f0f6`，未 commit |
| 改动文件 | 6 个，最小 diff 见 `02_code/round34_d1_changes.diff`：<br>• `week2_llm.py`<br>• `structured_output_adapter.py`<br>• `replay/source_bundle.py`<br>• 规格文档的版本表<br>• `tests/test_t1_source_linking_pipeline.py`<br>• 新增 `tests/test_t4_round34_d1_adapter_citation_contract.py` |
| 修复前 / 修复后的复现 | `01_before_after/`：两份第二次 Fresh 的真实回复，修复前后都被拒，因为缺字段 |
| 测试 | `03_tests/`：<br>• d1 组 482 passed、1 skipped、0 failed，网络陷阱 0 次；<br>• 冻结钉测试修复前后是同一项既有失败 |
| 构建 / 解压验证 | `build_log.txt`；`unzip_verification/verification_log.txt`，失败命令 0 |
| 原件前后哈希 | `hash_proof/`：2295 个受保护文件全部不变，包括两次 Fresh、Round 33 的包和 ZIP |
| 没有动的 | Round 33 包和 ZIP、两次 Fresh 的请求、回复和结果、所有服务（8005 内存中仍是修复前的代码，没有重启） |
