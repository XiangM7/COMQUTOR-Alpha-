# 本版前后的原件哈希

- `state_before.json`：本版开始时（2026-10-09T21:50Z）。
- `state_after.json`：组装交付包之前，与 `state_before.json` 比较。

两份快照都记录了代码身份和 2034 个受保护文件的 sha256。受保护文件包括：
- 两次 Fresh 的 run 目录；
- Round 25–32 的材料，含 Round 31、Round 32 的交付包和 ZIP；
- Round 32 两个实例的输出目录；
- 历史 run 和 T3 执行。

**结果**：
- 代码身份不变：tracked diff `6cdd51e3…`，未跟踪源码没有增加、删除或修改。本版没有改代码。
- 受保护文件缺失 0、新增 0，有变化的只有 1 个：`round28_t4_launch_protection_20261008/04_refreeze/instance_fresh_start.log`。

**这个文件为什么变了**：
- 它是 8002 实例自己追加的访问日志，不是本版写入的。
- 本版为了核对 8002 的代码版本，对它发了 3 个只读 GET：`/ready`、`/api/research?limit=10`、第二次 Fresh 的详情。日志末尾的 3 行就是这 3 个请求。
- 整个日志中只有 2 个 `POST /api/research`，即两次 Fresh 的启动。本版没有向 8002 发送任何非 GET 请求，也没有停止、重启或修改它的配置。
