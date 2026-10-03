# alpha-0.89

## deepmemory 逐模块自检 · 第 9 轮（maintenance 维护）

### 🔴 发现并修复：保留策略因 SQL 类型比较陷阱**完全失效**
`store.delete_timeline_older_than()` 与 `store.delete_injection_logs_older_than()` 的判定是：
```sql
strftime('%s', occurred_at) <= strftime('%s','now') - ?
```
- `strftime()` 返回 **TEXT**（如 `'1783269195'`），而右边 `strftime('%s','now') - ?` 是**数字**（`1788453195`）；
- SQLite 的类型排序是 NULL < INTEGER/REAL < **TEXT** → `TEXT <= INTEGER` **永远为假**；
- 后果：**`maintenance.retention_timeline_days` 从未删掉任何一行**，注入日志同样永不清理
  → 长期使用时间线/日志表无限膨胀（你当前 13 条都未总结，所以还没暴露）。

**证据（同一条件的对照）**：
| 写法 | 命中行数 |
|---|---|
| 旧：`strftime(...) <= strftime(...,'now') - 2592000` | **0** |
| 新：`CAST(strftime(...) AS INTEGER) <= CAST(strftime(...,'now') AS INTEGER) - 2592000` | **1** |

**修复**：两处判定**两侧都 CAST 成 INTEGER**（与 `list_decay_candidates` 里已有的正确写法保持一致）。
修复后实测：90 天前的**已总结**时间线被删除、**未总结**的保留；注入日志清理同时生效（一次清掉 8 条）。

### 维护模块其余验证（14/14）
| 验证 | 结果 |
|---|---|
| 配置：maintenance 5 项全部有代码读取 | ✅ |
| **每日减权**：`importance` 0.8 → 0.792（1%/天），报告含 rate/threshold/processed | ✅ |
| 维护集成：`run_maintenance()` 返回 `daily_decay`/`decay`/`retention` 三段，`last_maintenance_at` 落库 | ✅ |
| **保留策略**（修复项）：超期已总结删除、未总结保留 | ✅ |
| **归档恢复闭环**：归档 → 不可见 → `update_memory_fields(lifecycle="active")` → 重新可见 | ✅ |
| 开关：`auto_maintenance_enabled=False` 时不启动后台维护任务 | ✅ |

### 关于「归档可在维护页恢复」
schema 里这句话**成立**，但入口不在维护页：前端在**记忆列表**提供 lifecycle 选择器
（活跃/归档/衰减），编辑记忆时提交 `/memory/update`（其字段白名单含 `lifecycle`）即可恢复。
本轮实测了完整闭环（归档→改回 active→重新可见）。
