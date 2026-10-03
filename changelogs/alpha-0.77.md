# alpha-0.77

## 重排模型下拉数据源修正（与 storyteller alpha-0.134 配套）

- **重排列表**：AstrBot v4.27 的 Context **没有** `get_all_rerank_providers` 接口，此前 `_rerank_provider_options`
  降级到 LLM 列表（`get_all_providers`）——下拉里会出现对话模型，用户选了必然失败。
  现改为三级兜底：专用接口（若存在）→ `provider_manager.rerank_provider_insts` → `inst_map`
  按 `provider_type` 含 rerank 过滤，只展示真正的重排模型（如 bge-reranker 等独立配置）。
- **嵌入列表**：确认原本就按分类接口（`get_all_embedding_providers`）读取，无需改动。
- 版本备份：`astrbot_plugin_deepmemory_alpha-0.77`。