# alpha-0.94

## P1-9：新事实取代旧事实（不删、可恢复）

**问题**：`memories` 表**早就有**三个字段：

```sql
lifecycle TEXT,          -- active / archived / decayed
supersedes_id TEXT,      -- 被谁取代
merged_count INTEGER     -- 合并了几次
```

但 `supersedes_id` **从来没被写过**，`lifecycle` 也从没出现过 `superseded`。
于是「我不吃辣」和「我现在能吃辣了」会**同时在库里**，检索时两条都出来，
她就会说自相矛盾的话。

## 本轮补上「标记取代」

`bridge` 新增：

```python
def mark_superseded(self, old_id: str, new_id: str = "") -> bool
```

- 把旧条 `lifecycle` 改成 **`superseded`**；
- 若有新条，`supersedes_id` 指回去（形成链路，能追溯"哪条取代了哪条"）；
- **不删** —— 面板还能看到、可恢复。

## 为什么用 update 而不是 delete

删除是不可逆的。记忆是长期资产，宁可标"过时"也不删 ——
万一判错了（LLM 把"补充"判成"冲突"），还能恢复。

## 验证

`audit_94` 的 A/B 组：表结构三字段都在、`mark_superseded` 存在、
标的是 `superseded`、写了 `supersedes_id`、用的是 update 而不是删除。
