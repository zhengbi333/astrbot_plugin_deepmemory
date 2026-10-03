# alpha-0.88

## deepmemory 逐模块自检 · 第 8 轮（decay 衰减）

### 衰减机制实测
`decay` 12 项配置；候选筛选由 `store.list_decay_candidates()` 的 SQL 一次判完，五个条件：
`lifecycle='active'` + `importance <= decay_max_importance(0.7)` + `access_count <= decay_max_access_count(3)`
+ `created_at <= now-120 天` + `last_accessed_at <= now-60 天`（或从未访问）；
排序 `importance ASC, created_at ASC`。

| 验证 | 结果 |
|---|---|
| **候选筛选六情形**：太新 ✗ / 重要度 0.95 ✗ / **访问 9 次 ✗** / 最近访问过 ✗ / 又老又未访问 ✓ / 老且久未访问 ✓ | ✅ |
| **访问保护**：`access_count>=5` 的老记忆**不会**被列为候选（第 32 轮修 `touch_memory` 的直接收益） | ✅ |
| `decay_records` 可调用（每日减权路径） | ✅ |
| **闭环**：归档后 `lifecycle='archived'` → `visibility_filter` 判**不可见**（衰减→归档→隐身成立） | ✅ |
| 开关：`decay.enabled=False` 可读 | ✅ |

### 修正：`decay.decay_provider_id` 是「声明了却不生效」的配置（第 8 个）
- hint 写「compress 模式使用的 LLM 提供商；留空使用总结模型/当前会话模型」，
  但**全仓没有任何读取 `decay.decay_provider_id` 的地方**；
- 实际行为：**compress 模式始终用「总结模型 / 当前会话模型」**，指定别的模型不生效；
- archive / delete 本就不需要模型 → 你当前的 `decay_mode="archive"` 不受影响；
- **处置**：如实改写 hint。未贸然实现 compress 的独立模型选择（属功能扩展，且你暂未使用 compress）。
