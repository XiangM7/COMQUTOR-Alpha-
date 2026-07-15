# 当前系统状态

审查日期：2026-07-14

## 仓库基线

- 分支：`comqutor-structure-layer`
- HEAD：`8578a07a979b0070b5321c1bc24adb78e8c7a183`
- Python：`3.13.5`
- Python 路径：`.venv/bin/python`
- 项目要求：Python `>=3.10`

## 阶段状态

| 阶段 | 状态 |
|---|---|
| Week 0 baseline | PASS |
| Week 1A output/research entry | PASS |
| Week 2 Alpha mapping / structure extraction | PASS |
| Week 3 graph / activation / persistence / graph API | PASS |
| W4.0 specification freeze | PASS |
| W4.1 deterministic conflict core | PASS |
| W4.2 activation/conflict persistence | PASS |
| W4.2 PostgreSQL verification | PASS |
| W4.3 pipeline/API integration | NOT STARTED |

这不表示 Week 4 全部完成，也不表示 COMQUTOR Alpha 已完成或已可用于公开生产部署。

## 验证结果

- `pip check`：PASS
- SQLite fallback targeted tests：`4 passed`
- Offline suite：`1035 passed, 1 skipped, 18 deselected, 0 failed`
- PostgreSQL integration：`10 passed`

## 数据库状态

- SQLite：离线和本地 fallback。
- PostgreSQL：本地开发及 integration verification 数据库。
- Migrations：`0001_create_week3_alpha_matches_and_structure_graphs`、
  `0002_create_week4_alpha_activations_and_alpha_conflicts`。
- 已实现表：`alpha_matches`、`structure_graphs`、`alpha_activations`、
  `alpha_conflicts`。
- PostgreSQL 已实际验证 JSONB、unique constraints、transaction rollback、
  replace semantics、run isolation 和同 ticker 不同 run isolation。

## 当前能力边界

- Week 1A 可安全保存 TradingAgents raw outputs，并通过 research entry 生成 run。
- Week 2 可生成 structured claims、Alpha matches 和 claim-level extracted structures。
- Week 3 可生成 Structure Graph、Alpha activation，并持久化及通过 graph API 读取。
- W4.1 可确定性生成 admitted、suppressed、rejected conflict candidates、
  evidence audit 和 main conflict。
- W4.2 可原子持久化 activation/conflict rows，并确定性重建 W4.1 conflict payload。
- Research pipeline 尚未自动调用 W4.1/W4.2 conflict persistence。

## 未完成事项

- W4.3 尚未接入 research pipeline。
- Conflicts API：未实现。
- Agent-outputs API：未实现。
- Exposure Engine：`BLOCKED_BY_SEED`。
- MSFT Golden Gate：`BLOCKED_BY_SPEC_CONFLICT`。
- Authentication、authorization、tenant ownership：未实现。
- Alpha Memory、跨 run feedback：未实现。
- Public production deployment：`NOT READY`。

`.env` 保持忽略，未修改、未提交。当前系统不是 production-ready。
