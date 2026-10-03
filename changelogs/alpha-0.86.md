# alpha-0.86

## deepmemory 逐模块自检 · 第 5 轮（retrieval 检索）

### 发现并修复：`retrieval.rerank_candidate_multiplier` 是死配置
- 该项描述「重排候选倍率」（默认 5），但代码里**只有**固定的
  `candidate_limit = retrieval.rerank_candidate_limit`（默认 32），**倍率从未被读取**
  （全仓检索 `candidate_multiplier|candidate_limit|rerank_candidate` 只有 477/478 两行，
  只用到 limit）→ 属"声明了却不生效"（本次审计发现的**第 6 个**）。
- **修复**：让倍率真正生效 —— 候选数 = `min(rerank_candidate_limit, top_k × multiplier)`，
  两个配置各司其职（倍率决定"取多少"、limit 作为上限）。
- **影响面**：`mode=auto` 且未启用向量召回、或未配置重排模型时，该段根本不执行
  → 对现有行为**零影响**（你的环境正是这两种情形）。

### 检索引擎实测（12/12）
在**临时副本**上走真实代码路径（`MemoryStore.upsert_memory` → `RetrievalEngine.search`）：
| 验证 | 结果 |
|---|---|
| 配置：14 项全部有代码读取（修复后） | ✅ |
| 召回：「我喜欢喝什么」→ 0.935、「离心机」→ 0.958、「周末」→ 0.910（`reason=keyword`） | ✅ |
| **排序**：最相关的一条排在首位 | ✅ |
| **隔离**：私聊检索**不会**召回其它会话的私密记忆（实测 0 条泄漏） | ✅ |
| **降级**：未配嵌入模型时 `resolve_provider → None`、`embed → 0 维`，**不抛异常**，关键词路径照常召回 | ✅ |
| 边界：空查询 / 纯符号 / 超长查询均不崩 | ✅ |

### 说明
`retrieval.mode` 的 `auto` 语义：`mode=rerank` 强制重排；`auto` 且启用向量召回时也重排。
你的 `embedding_provider_id` 与 `rerank_provider_id` 均为空 → 当前走**纯关键词检索**（实测可用）。
若要开启向量/重排，需分别配置嵌入模型与重排模型 Provider。
