# alpha-0.87

## deepmemory 逐模块自检 · 第 6 轮（weights 权重）

### 🔴 发现并修复：`store.touch_memory()` 从未被调用 → 访问频率维度完全失效
- `weights` 的打分公式是
  `score = base_importance_weight×importance + recency_weight×0.5^(age/halflife) + access_weight×min(1, access_count/cap)`；
- `store.touch_memory()` 已正确实现（`UPDATE memories SET last_accessed_at=?, access_count=access_count+1`），
  但**全仓没有任何地方调用它** → `access_count` 恒为 0 → **`access_weight`（0.15）这一维永远是 0**；
- **实测证据**：检索**命中**了目标记忆，前后 `access_count` 仍是 **0 → 0**；
- 也就是说"**经常被想起的记忆更容易被想起**"这个拟人特性**完全没生效**。
- **修复**：在 `RetrievalEngine.search()` 返回前，对本次命中项调用 `store.touch_memory()`；
  **管理视角（`admin_read_all`，如面板浏览）不计入**，避免后台翻看污染权重。
- **修复后实测**：命中前 0 → 检索后 **1** ✅

### 权重实现的数学验证（14/14）
| 验证 | 结果 |
|---|---|
| 配置：weights 9 项全部有代码读取 | ✅ |
| **新近度半衰期**：0 天 = 1.0000、**30 天 = 0.5000**、**60 天 = 0.2500**（半衰期语义精确） | ✅ |
| **访问封顶**：0 次=0、3 次=0.300、10 次=1.000、**99 次仍为 1.000**（cap 生效） | ✅ |
| **综合基础分**：`_base_score` = 0.6500，与公式 `1.0×0.45 + 0.25×0.5 + 0.15×0.5` 完全一致 | ✅ |
| 排序：新记录 > 旧记录；常访问 > 不常访问 | ✅ |
| **访问计数更新**（本轮修复项）：命中后 `access_count` 0 → 1 | ✅ |
| 门槛/加分/置信度三项配置都有读取点（`min_importance_for_injection` / `manual_importance_boost` / `min_confidence`） | ✅ |

### 行为影响说明
本次修复后，**检索会真正累积访问计数**，因此"经常被召回的记忆"在后续排序中权重会逐步上升
（最多到 `access_count_cap=10` 封顶，即 0.15 分）。这属于**恢复设计意图**，改动幅度很小且有上限。
