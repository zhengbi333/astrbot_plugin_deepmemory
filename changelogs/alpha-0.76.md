# alpha-0.76

## Token 记账与桥接上报（与陪伴插件 alpha-0.125 配套）

- **自身 LLM 调用记账**：新增 `core/token_usage.py`——每次文本/识图/嵌入/重排调用后记一笔
  （任务 + 模型 + 入/出 token + 调用次数）：提供方返回真实 `usage` 时记真实值，缺失时按字符
  估算（汉字每字约 1 token、其余约 4 字符 1 token，纯本地规则、不额外调 LLM）；按日聚合、
  滚动保留 90 天、最近 200 笔明细（写盘节流 3 秒）。
- **覆盖范围**：阶段总结/问答等（按配置前缀记账）、链接要点（link_point）、文档摘要
  （document）、图片/动图转述（vision）、向量嵌入（embed）、语义重排（rerank）、模型测试
  （test）。嵌入/重排通过注入 `note_usage` 回调记账，不改任何调用逻辑。
- **桥接上报**：`bridge.token_stats()` 只读接口（零副作用），供陪伴插件 Token 页读取
  「记忆插件单独调用」统计；未记账时返回空结构，不影响任何既有行为。
- 对齐说明：统计结构（total/today/month/by_task/by_model/recent）与陪伴插件 Token 页约定一致，
  由陪伴插件页面统一展示三来源（AstrBot 主链 / 记忆插件 / 陪伴插件）。

## 说明

- 单独使用本插件行为不变；新功能仅在统计数据层面。
- 版本备份：`astrbot_plugin_deepmemory_alpha-0.76`。