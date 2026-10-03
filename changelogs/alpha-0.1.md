# alpha-0.1（2026-08-07）

## 新增

- 首个可用版本：长期记忆中枢「为你篆刻的历史」。
- WebUI 仪表盘：总览 / 记忆库 / 人格 / 用户 / 检索测试 / 时间线 / 导入导出 / 维护 / 设置。
- 按人格与按用户双层记忆隔离，跨用户/跨群/公共可见性开关。
- 混合检索：FTS5（trigram 中文子串）+ Embedding 语义召回 + Rerank 二阶段重排，失败自动回退。
- 记忆权重：重要度、置信度、新鲜度半衰期、访问频率等多因子排序，因子全部可配置。
- 自然衰减：compress（LLM 压缩）/ archive / delete 三种方式，阈值可配。
- LLM 阶段总结：按条数/间隔分钟触发，主备模型回退。
- 批量导入导出：JSONL / JSON 全字段档案，导入前自动备份。
- 主链记忆注入 + `deepmem_recall` / `deepmem_remember` LLM 工具。
- `/deepmem` 命令组（status / search / add / recent / summarize / delete / personas / persona / maintenance / export / help）。
- 公共桥接接口 `get_deepmemory_bridge()`，供陪伴插件调用。
- 设置页：11 个配置模块可视化编辑，运行时可持久化。

## 修复

- 页面 API 在旧版 AstrBot（无 `astrbot.api.web`）下全部 500 的问题：统一异步响应助手，兼容新旧两套 API。
- 页面加载失败后无限转圈：改为错误卡片 + 重试/刷新按钮。
- 时间线衰减 SQL 中 TEXT/INTEGER 比较导致的候选漏选。

## 说明

- 使用 SQLite FTS5 trigram 分词器（SQLite >= 3.34），旧环境自动回退 unicode61 + LIKE 兜底。
